"""Chapitre 11 : le tri des déclarations, quatre versions du prompt, deux modèles.

Trente-deux déclarations fictives (ch11/declarations.json), chacune avec son tri attendu : sa branche,
et si elle va dans la file des urgences. Les quatre versions viennent de la bibliothèque de prompts
(assureur/prompts/bibliotheque.json) :
- v1 : « Soyez prudent : mieux vaut une déclaration urgente de trop » ;
- v2 : « Seulement si vous êtes sûr » ;
- v3 : des critères explicites, ce qui est urgent et ce qui ne l'est pas ;
- v4 : les mêmes critères, et trois exemples de cas difficiles avec leur raisonnement.

Pour chaque version, on compte les fausses urgences (une déclaration non urgente envoyée dans la file),
les urgences manquées, les branches justes, les réponses au bon format, et la stabilité : la même
décision d'une répétition à l'autre. Sans réflexion, comme le tri des constats du chapitre 3.

Lancement, depuis le dossier python/ :
    python -m ch11.tri --estimer                                          # gratuit : coût maximal
    python -m ch11.tri --modeles claude-haiku-5-5 --versions 1 2 3 4 --repetitions 3 --budget-max 0.20
"""

import argparse
import json
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import anthropic

from assureur import bibliotheque, config
from assureur.couts import cout, cout_maximal, francais
from assureur.journal import noter

DOSSIER = Path(__file__).parent
DECLARATIONS = json.loads((DOSSIER / "declarations.json").read_text(encoding="utf-8"))["declarations"]
PROMPT = "tri-declarations"
MAX_TOKENS = 300
BRANCHES = {"auto", "habitation", "sante", "autre"}
# Sans réflexion. Sonnet 5.5 refuse « disabled » : son réglage le plus bas supprime la réflexion avant la
# réponse (chapitre 3).
SANS_REFLEXION = {"claude-sonnet-5-5": {"type": "between_tools"}}


def demande(texte: str) -> str:
    return f"Déclaration : « {texte} »"


def lire(texte: str) -> tuple[dict | None, bool]:
    """(la décision, True si la réponse est exactement au format demandé). La décision est lue même hors
    format, quand un objet JSON se trouve dans le texte : on mesure le format à part."""
    brut = texte.strip()
    try:
        d = json.loads(brut)
        au_format = isinstance(d, dict) and d.get("branche") in BRANCHES and isinstance(d.get("urgent"), bool) \
            and isinstance(d.get("motif"), str)
        return d, au_format
    except json.JSONDecodeError:
        trouve = re.search(r"\{.*\}", brut, re.DOTALL)
        if trouve:
            try:
                return json.loads(trouve.group(0)), False
            except json.JSONDecodeError:
                pass
        return None, False


def trier(client, modele: str, version: str, declaration: dict, repetition: int) -> dict:
    systeme = bibliotheque.assembler(PROMPT, version)
    r = client.messages.create(model=modele, max_tokens=MAX_TOKENS, system=systeme, cache_control={"type": "ephemeral"},
                               thinking=SANS_REFLEXION.get(modele, {"type": "disabled"}),
                               messages=[{"role": "user", "content": demande(declaration["texte"])}])
    c = cout(modele, r.usage)
    noter(getattr(r, "_request_id", None), modele, c, chapitre="11", etape="tri", cas=f"v{version}:{declaration['id']}")
    texte = "".join(b.text for b in r.content if b.type == "text")
    d, au_format = lire(texte)
    return {"modele": modele, "version": version, "declaration": declaration["id"], "repetition": repetition,
            "reponse": texte, "au_format": au_format, "urgent": d.get("urgent") if d else None,
            "branche": d.get("branche") if d else None, "motif": d.get("motif") if d else None,
            "attendu_urgent": declaration["urgent"], "attendu_branche": declaration["branche"],
            "cout_dollars": c.dollars, "tokens_entree": c.entree + c.lecture_cache + c.ecriture_cache}


def resumer(essais: list[dict]) -> dict:
    lignes = {}
    for cle in dict.fromkeys((e["modele"], e["version"]) for e in essais):
        g = [e for e in essais if (e["modele"], e["version"]) == cle]
        urgents_attendus = sum(1 for d in DECLARATIONS if d["urgent"])
        par_rep = {}
        for e in g:
            par_rep.setdefault(e["repetition"], []).append(e)
        fausses = [sum(e["urgent"] is True and not e["attendu_urgent"] for e in r) for r in par_rep.values()]
        manquees = [sum(e["urgent"] is not True and e["attendu_urgent"] for e in r) for r in par_rep.values()]
        decisions = {}
        for e in g:
            decisions.setdefault(e["declaration"], set()).add(e["urgent"])
        lignes[f"{cle[0]}:v{cle[1]}"] = {
            "empreinte": bibliotheque.empreinte(PROMPT, cle[1]),
            "repetitions": len(par_rep),
            "fausses_urgences": fausses, "sur": len(DECLARATIONS) - urgents_attendus,
            "urgences_manquees": manquees, "sur_urgentes": urgents_attendus,
            "fausses_urgences_par_declaration": dict(sorted(
                {e["declaration"]: sum(x["urgent"] is True for x in g if x["declaration"] == e["declaration"])
                 for e in g if not e["attendu_urgent"] and e["urgent"] is True}.items())),
            "urgences_manquees_par_declaration": dict(sorted(
                {e["declaration"]: sum(x["urgent"] is not True for x in g if x["declaration"] == e["declaration"])
                 for e in g if e["attendu_urgent"] and e["urgent"] is not True}.items())),
            "branches_justes": sum(e["branche"] == e["attendu_branche"] for e in g), "decisions": len(g),
            "au_format": sum(e["au_format"] for e in g),
            "declarations_instables": sorted(k for k, v in decisions.items() if len(v) > 1),
            "cout_par_declaration": statistics.mean(e["cout_dollars"] for e in g),
            "tokens_entree_moyens": statistics.mean(e["tokens_entree"] for e in g),
        }
    return lignes


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 11 : le tri des déclarations.")
    parser.add_argument("--modeles", nargs="*", default=["claude-haiku-5-5"])
    parser.add_argument("--versions", nargs="*", default=["1", "2", "3", "4"])
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--budget-max", type=float, default=0.20)
    parser.add_argument("--estimer", action="store_true", help="coût maximal, par le comptage gratuit des tokens")
    parser.add_argument("--fichier", default=None)
    args = parser.parse_args()

    client = anthropic.Anthropic()
    maximum = 0.0
    for modele in args.modeles:
        for v in args.versions:
            entree = client.messages.count_tokens(model=modele, system=bibliotheque.assembler(PROMPT, v),
                                                  messages=[{"role": "user", "content": demande(DECLARATIONS[0]["texte"])}])
            maximum += cout_maximal(modele, entree.input_tokens + 60, MAX_TOKENS) * len(DECLARATIONS) * args.repetitions
    print(f"Coût maximal : {francais(maximum, 4)} $ (plafond : {francais(args.budget_max, 2)} $)")
    if args.estimer:
        return
    if maximum > args.budget_max:
        raise SystemExit("Le coût maximal dépasse le plafond : réduisez les versions, les modèles ou les répétitions.")

    taches = [(m, v, d, r) for m in args.modeles for v in args.versions for r in range(1, args.repetitions + 1)
              for d in DECLARATIONS]
    with ThreadPoolExecutor(max_workers=6) as pool:
        essais = list(pool.map(lambda t: trier(client, *t), taches))
    depense = sum(e["cout_dollars"] for e in essais)
    resume = resumer(essais)
    print(json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    nom = args.fichier or f"tri-{'-'.join(m.replace('claude-', '') for m in args.modeles)}"
    sortie = DOSSIER / "resultats" / f"{nom}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "depense_dollars": round(depense, 6),
                                  "resume": resume, "essais": essais}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
