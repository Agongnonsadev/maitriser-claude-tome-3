"""Chapitre 14 : l'assistant des gestionnaires, qui répond à partir des passages trouvés, et les cite.

Claude Haiku 5.5, sans réflexion, rend sa réponse par l'outil `repondre` : trouvé ou non, la réponse, et
les identifiants des passages qu'il a utilisés. Le code note chaque réponse :
- juste : la base contient la réponse, le modèle l'a trouvée, chaque fait attendu est dans la réponse, et
  une des sources citées couvre une unité attendue ;
- « je ne trouve pas » juste : la base ne contient pas la réponse, et le modèle le dit ;
- sinon, fausse, avec la raison : fait manquant, source absente, réponse inventée, réponse manquée.

Avec `systeme=True`, l'assistant a aussi l'outil `consulter_sinistre`, qui lit le dossier dans le logiciel
de gestion simulé (assureur/systeme.py) : l'état d'un dossier se lit en direct, pas dans un index.

Lancement, depuis le dossier python/ :
  python -m ch14.assistant --decoupages naif structure --strategie filtre --k 5
  python -m ch14.assistant --strategie filtre --k 3 5 10 20
  python -m ch14.assistant --strategie reclassement --k 3
  python -m ch14.assistant --jeu etat --strategie filtre --k 5 --systeme sans avec
"""

import argparse
import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import anthropic

from assureur import config
from assureur.couts import cout, francais
from assureur.journal import noter
from assureur.systeme import Systeme
from ch14.corpus import charger, decouper
from ch14.mesurer_recherche import BASE_OCTOBRE, questions
from ch14.recherche import IndexBM25, chercher

DOSSIER = Path(__file__).parent
MODELE = "claude-haiku-5-5"
MAX_TOKENS = 700

PROMPT = """Vous assistez les gestionnaires de sinistres de Kanvô Assurances. Vous répondez à leurs questions à partir des seuls passages fournis : conditions générales, tableaux des garanties, procédures internes, et tout autre document de la base.

Règles :
- appuyez chaque affirmation sur un passage, et donnez dans sources les identifiants des passages utilisés ;
- si les passages ne contiennent pas la réponse, trouve vaut false : dites ce que vous n'avez pas trouvé, sans compléter avec vos connaissances ;
- chaque passage indique la période des sinistres que régit son document. Quand la date du sinistre est connue, appliquez le document de cette période ; si deux éditions se contredisent et que la date n'est pas connue, donnez les deux, avec leur période ;
- répondez en trois phrases au plus, avec les montants et les délais exacts."""

REGLE_ETAT = """
- l'état d'un dossier de sinistre (statut, prochaine étape, pièces attendues) se lit dans le logiciel de gestion avec consulter_sinistre, jamais dans un document : un export ou une copie peut être périmé."""

REPONDRE = {
    "name": "repondre",
    "description": "Rend la réponse au gestionnaire.",
    "input_schema": {"type": "object", "properties": {
        "trouve": {"type": "boolean", "description": "true si les passages, ou le logiciel de gestion, contiennent la réponse"},
        "reponse": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}, "description": "Identifiants des passages utilisés, ou « logiciel de gestion »"}},
        "required": ["trouve", "reponse", "sources"], "additionalProperties": False},
}

CONSULTER = {
    "name": "consulter_sinistre",
    "description": "Lit un dossier de sinistre dans le logiciel de gestion, à l'instant : statut, prochaine étape, gestionnaire.",
    "input_schema": {"type": "object", "properties": {"numero_sinistre": {"type": "string", "description": "Par exemple SIN-2026-0912"}},
                     "required": ["numero_sinistre"], "additionalProperties": False},
}


def contexte(q: dict) -> str:
    lignes = []
    if q.get("produit"):
        lignes.append(f"Produit du dossier : {q['produit']}.")
    if q.get("date"):
        lignes.append(f"Date du sinistre : {q['date']}.")
    return "\n".join(lignes)


def anonyme(i: int, m) -> str:
    """Un passage sans métadonnées, comme dans bien des bases documentaires : ni référence, ni période."""
    titre = m.titre.split(", ", 1)[1] if ", " in m.titre else m.titre
    return f'<passage id="p{i}">\n{titre}\n{m.texte}\n</passage>'


def repondre(client, q: dict, morceaux, systeme: bool = False, cas: str = "", metadonnees: bool = True) -> dict:
    """Une réponse, avec au plus deux consultations du logiciel de gestion avant elle. Sans métadonnées, les
    passages s'appellent p1, p2… et les sources citées sont ramenées à leur identifiant."""
    if metadonnees:
        passages = "\n\n".join(m.pour_le_modele() for m in morceaux) or "(aucun passage trouvé)"
    else:
        passages = "\n\n".join(anonyme(i, m) for i, m in enumerate(morceaux, start=1)) or "(aucun passage trouvé)"
    sortie = _repondre(client, q, passages, systeme, cas)
    if not metadonnees:
        noms = {f"p{i}": m.identifiant for i, m in enumerate(morceaux, start=1)}
        sortie["sources"] = [noms.get(s, s) for s in sortie.get("sources", [])]
    return sortie


def _repondre(client, q: dict, passages: str, systeme: bool, cas: str) -> dict:
    messages = [{"role": "user", "content": f"<passages>\n{passages}\n</passages>\n\n{contexte(q)}\nQuestion du gestionnaire : {q['question']}"}]
    outils = [REPONDRE, CONSULTER] if systeme else [REPONDRE]
    prompt = PROMPT + (REGLE_ETAT if systeme else "")
    debut, dollars, entree, consultations = time.perf_counter(), 0.0, 0, []
    for tour in range(3):
        choix = {"type": "any"} if systeme and tour < 2 else {"type": "tool", "name": "repondre"}
        r = client.messages.create(model=MODELE, max_tokens=MAX_TOKENS, system=prompt, tools=outils, tool_choice=choix,
                                   thinking={"type": "disabled"}, messages=messages)
        c = cout(MODELE, r.usage)
        noter(getattr(r, "_request_id", None), MODELE, c, chapitre="14", etape="reponse", cas=cas)
        dollars, entree = dollars + c.dollars, entree + c.entree + c.lecture_cache + c.ecriture_cache
        appel = next(b for b in r.content if b.type == "tool_use")
        if appel.name == "repondre":
            return {**appel.input, "consultations": consultations, "duree_s": time.perf_counter() - debut,
                    "dollars": dollars, "tokens_entree": entree}
        try:
            resultat = json.dumps(Systeme().consulter_sinistre(appel.input["numero_sinistre"]), ensure_ascii=False)
        except Exception as e:   # un dossier inconnu ou archivé : l'erreur va au modèle
            resultat = f"Erreur : {e}"
        consultations.append(appel.input["numero_sinistre"])
        messages += [{"role": "assistant", "content": r.content},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": appel.id, "content": resultat}]}]
    raise RuntimeError("pas de réponse après trois tours")


def noter_reponse(q: dict, sortie: dict, morceaux) -> dict:
    par_id = {m.identifiant: m for m in morceaux}
    cites = [s for s in sortie.get("sources", []) if s in par_id]
    source_juste = any(set(par_id[s].unites) & set(q["attendus"]) for s in cites) or (
        q["genre"] == "etat" and any("logiciel" in s.lower() for s in sortie.get("sources", [])))
    faits = [f for f in q["faits"] if not re.search(f, sortie.get("reponse", ""), re.I)]
    if not q["trouve"]:
        issue = "juste" if not sortie["trouve"] else "inventee"
    elif not sortie["trouve"]:
        issue = "manquee"
    elif faits:
        issue = "fait_manquant"
    elif not source_juste:
        issue = "source_absente"
    else:
        issue = "juste"
    return {"issue": issue, "faits_manquants": faits, "sources_citees": sortie.get("sources", [])}


def essayer(client, index, q: dict, strategie: str, k: int, decoupage: str, systeme: bool, base: str = "octobre",
            metadonnees: bool = True) -> dict:
    d = date.fromisoformat(q["date"]) if q.get("date") else None
    cas = f"{decoupage}:{strategie}:{k}:{'systeme' if systeme else 'documents'}:{q['id']}"
    r = chercher(client, index, q["question"], strategie, k, q.get("produit"), d, cas=cas)
    sortie = repondre(client, q, r["morceaux"], systeme, cas, metadonnees)
    return {"question": q["id"], "genre": q["genre"], "decoupage": decoupage, "strategie": strategie, "k": k,
            "systeme": systeme, "base": base, "metadonnees": metadonnees, "passages": [m.identifiant for m in r["morceaux"]],
            "trouve": sortie["trouve"], "reponse": sortie["reponse"], "consultations": sortie["consultations"],
            **noter_reponse(q, sortie, r["morceaux"]),
            "duree_recherche_s": round(r["duree_s"], 3), "duree_reponse_s": round(sortie["duree_s"], 3),
            "tokens_entree": sortie["tokens_entree"], "dollars": r["dollars"] + sortie["dollars"]}


def resumer(essais: list[dict]) -> dict:
    lignes = {}
    for cle in dict.fromkeys((e["base"], e["decoupage"], e["strategie"], e["k"], e["systeme"]) for e in essais):
        g = [e for e in essais if (e["base"], e["decoupage"], e["strategie"], e["k"], e["systeme"]) == cle]
        issues = {}
        for e in g:
            issues[e["issue"]] = issues.get(e["issue"], 0) + 1
        lignes[" / ".join(map(str, cle))] = {
            "justes": f"{issues.get('juste', 0)}/{len(g)}", "issues": issues,
            "par_genre": {genre: f"{sum(e['issue'] == 'juste' for e in g if e['genre'] == genre)}/{sum(e['genre'] == genre for e in g)}"
                          for genre in dict.fromkeys(e["genre"] for e in g)},
            "tokens_entree_moyens": round(statistics.mean(e["tokens_entree"] for e in g)),
            "duree_mediane_s": round(statistics.median(e["duree_recherche_s"] + e["duree_reponse_s"] for e in g), 2),
            "dollars_par_question": round(statistics.mean(e["dollars"] for e in g), 6),
        }
    return lignes


def reevaluer(chemin: Path) -> dict:
    """Renote un fichier de résultats avec les questions et la notation actuelles, sans appel."""
    d = json.loads(chemin.read_text(encoding="utf-8"))
    toutes = {q["id"]: q for jeu in ("questions", "etat", "editions") for q in questions(jeu)}
    docs = charger()
    morceaux = {m.identifiant: m for methode in ("naif", "structure") for m in decouper(docs, methode)}
    for e in d["essais"]:
        sortie = {"trouve": e["trouve"], "reponse": e["reponse"], "sources": e["sources_citees"]}
        e.update(noter_reponse(toutes[e["question"]], sortie, [morceaux[i] for i in e["passages"]]))
    return d


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 14 : l'assistant des gestionnaires.")
    parser.add_argument("--reevaluer", type=Path, default=None, help="renoter un fichier de résultats, sans appel")
    parser.add_argument("--jeu", default="questions", choices=["questions", "etat"])
    parser.add_argument("--decoupages", nargs="*", default=["structure"])
    parser.add_argument("--strategie", default="filtre")
    parser.add_argument("--k", nargs="*", type=int, default=[5])
    parser.add_argument("--systeme", nargs="*", default=["sans"], choices=["sans", "avec"])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--budget-max", type=float, default=0.20)
    args = parser.parse_args()
    if args.reevaluer:
        d = reevaluer(args.reevaluer)
        d["resume"] = resumer(d["essais"])
        args.reevaluer.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: v["justes"] for k, v in d["resume"].items()}, ensure_ascii=False, indent=1))
        return
    qs = questions(args.jeu)
    taches = [(d, k, s == "avec", q) for d in args.decoupages for k in args.k for s in args.systeme for q in qs
              for _ in range(args.repetitions)]
    # Large : 600 tokens d'entrée par passage, 400 de sortie, trois tours avec le logiciel, plus la recherche.
    recherche = 0.0012 if args.strategie in ("reecriture", "reclassement") else 0.0
    estimation = sum((3 if s else 1) * (k * 600 * 0.10 + 400 * 0.50) / 1e6 + recherche for _, k, s, _ in taches)
    if estimation > args.budget_max:
        raise SystemExit(f"Estimation large de {francais(estimation, 3)} $ au-dessus du plafond.")
    client = anthropic.Anthropic()
    docs = charger(BASE_OCTOBRE)
    index = {d: IndexBM25(decouper(docs, d)) for d in args.decoupages}
    with ThreadPoolExecutor(max_workers=6) as pool:
        essais = list(pool.map(lambda t: essayer(client, index[t[0]], t[3], args.strategie, t[1], t[0], t[2]), taches))
    resume = resumer(essais)
    print(json.dumps(resume, ensure_ascii=False, indent=1))
    depense = sum(e["dollars"] for e in essais)
    print(f"Dépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    nom = f"assistant-{args.jeu}-{'-'.join(args.decoupages)}-{args.strategie}-k{'-'.join(map(str, args.k))}-{'-'.join(args.systeme)}"
    sortie = DOSSIER / "resultats" / f"{nom}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "depense_dollars": round(depense, 6),
                                  "resume": resume, "essais": essais}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
