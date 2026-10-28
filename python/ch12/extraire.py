"""Chapitre 12 : la chaîne d'extraction des documents, ses contrôles et ses relances.

Pour chaque document, une étape d'extraction (un appel à Claude, outils stricts de ch12/schemas.py), puis
une validation par le code, puis au plus une relance :
- la validation vérifie les formats (dates, heures, immatriculations, numéros, montants) et le calcul
  du total d'une facture. Ces erreurs se corrigent : on relance une fois, en renvoyant le document,
  l'extraction et la liste des erreurs, avec l'outil imposé ;
- une facture dont les lignes ne font pas le total déclaré est un conflit dans la source : on ne relance
  pas, on la signale à un gestionnaire ;
- un champ absent du document n'est pas une erreur : il vaut null.
La variante « exiger » montre l'erreur inverse : un contrôle qui exige la plaque du véhicule B, même quand
le constat ne la donne pas, et relance pour l'obtenir.

Variantes :
- naif : schéma naïf, prompt d'une phrase, tool_choice « auto » ;
- soigne : schéma soigné, règles de normalisation, tool_choice « any » ;
- exemples : le même, avec deux exemples de documents difficiles ;
- exiger : comme « soigne », avec le contrôle qui exige la plaque de B ;
- sans-autre : comme « soigne », mais sans l'outil des documents non reconnus : « any » oblige alors
  Claude à classer un courrier d'avocat dans l'un des trois types.

On note chaque champ contre la vérité de ch12/verite.json : juste, faux, inventé (une valeur là où le
document est muet), substitut (« illisible », « inconnu » à la place de null), omis (null là où le
document donne la valeur). Puis la précision par type de document et par champ.

Lancement, depuis le dossier python/ :
    python -m ch12.extraire --variantes naif soigne exemples --repetitions 2 --budget-max 0.30
    python -m ch12.extraire --variantes exiger --repetitions 2 --budget-max 0.10
"""

import argparse
import json
import re
import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import anthropic

from assureur import config
from assureur.couts import cout, francais
from assureur.journal import noter
from ch05.boucle import MODELE
from ch12.schemas import TYPES, outils, prompt

DOSSIER = Path(__file__).parent
VERITE = {d["id"]: d["verite"] for d in json.loads((DOSSIER / "verite.json").read_text(encoding="utf-8"))["documents"]}
DOCUMENTS = {i: (DOSSIER / "documents" / f"{i}.txt").read_text(encoding="utf-8").strip() for i in VERITE}
MAX_TOKENS = 1500
AUJOURD_HUI = "2026-10-27"
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
SUBSTITUTS = re.compile(r"^\s*$|illisible|inconnu|unknown|non (renseign|indiqu|précis|lisible)|n/?a|aucun|absent|non communiqu",
                        re.IGNORECASE)


# --- La validation par le code ----------------------------------------------------------------------

def _date_valide(valeur: str) -> bool:
    try:
        return re.fullmatch(r"\d{4}-\d{2}-\d{2}", valeur) is not None and "2020-01-01" <= \
            date.fromisoformat(valeur).isoformat() <= AUJOURD_HUI
    except ValueError:
        return False


def valider(outil: str, a: dict, exiger: bool = False, requis: list[str] | None = None) -> tuple[list[str], bool]:
    """(les erreurs à corriger par une relance, True si la source elle-même est en conflit).

    requis : les champs que le schéma exige. L'outil est strict, mais une relance a rendu une fois une
    facture sans ses lignes ni son total : le code vérifie quand même."""
    erreurs, conflit = [], False
    erreurs += [f"{champ} : champ manquant." for champ in (requis or []) if champ not in a]

    def verifier(champ, valeur, motif, attendu):
        if valeur is not None and not re.fullmatch(motif, str(valeur)):
            erreurs.append(f"{champ} : « {valeur} » n'est pas au format {attendu}.")

    for champ in ("date_accident", "date_facture", "date_expertise"):
        if a.get(champ) is not None and not _date_valide(a[champ]):
            erreurs.append(f"{champ} : « {a[champ]} » n'est pas une date AAAA-MM-JJ entre 2020 et aujourd'hui.")
    verifier("heure", a.get("heure"), r"([01]\d|2[0-3]):[0-5]\d", "HH:MM")
    plaque = r"[A-Z]{2} \d{4} [A-Z]{2}"
    for nom in ("vehicule_a", "vehicule_b"):
        if isinstance(a.get(nom), dict):
            verifier(f"{nom}.plaque", a[nom].get("plaque"), plaque, "AA 9999 AA")
    verifier("plaque", a.get("plaque"), plaque, "AA 9999 AA")
    verifier("numero_sinistre", a.get("numero_sinistre"), r"SIN-\d{4}-\d{4}", "SIN-AAAA-NNNN")
    vetuste = a.get("vetuste_pct")
    if vetuste is not None and not 0 <= vetuste <= 100:
        erreurs.append(f"vetuste_pct : {vetuste} n'est pas un pourcentage.")
    if outil == "extraire_facture" and a.get("lignes"):
        somme = sum(l["montant_fcfa"] for l in a["lignes"])
        if "total_calcule_fcfa" in a and a["total_calcule_fcfa"] != somme:
            erreurs.append(f"total_calcule_fcfa : {a['total_calcule_fcfa']} ne fait pas la somme des lignes ({somme}).")
        if a.get("total_declare_fcfa") is not None:
            conflit = a["total_declare_fcfa"] != somme
            if "incoherence" in a and a["incoherence"] != conflit:
                erreurs.append(f"incoherence : vaut {a['incoherence']}, alors que le total déclaré "
                               f"{'diffère de' if conflit else 'égale'} la somme des lignes.")
    if exiger and outil == "extraire_constat" and (a.get("vehicule_b") or {}).get("plaque") is None:
        erreurs.append("vehicule_b.plaque : la plaque du véhicule B est obligatoire.")
    return erreurs, conflit


# --- La notation contre la vérité ---------------------------------------------------------------------

def _plaque(v):
    return re.sub(r"[^A-Z0-9]", "", str(v).upper()) if v is not None else None


def _date(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s):
        return s
    if m := re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", s):
        j, mo, a = m.groups()
        return f"{('20' + a) if len(a) == 2 else a}-{int(mo):02d}-{int(j):02d}"
    if m := re.fullmatch(r"(\d{1,2}) (\w+) (\d{4})", s):
        if m.group(2) in MOIS:
            return f"{m.group(3)}-{MOIS.index(m.group(2)) + 1:02d}-{int(m.group(1)):02d}"
    return s


def _heure(v):
    if v is None:
        return None
    m = re.search(r"(\d{1,2})\s*[h:]\s*(\d{2})?", str(v))
    return f"{int(m.group(1)):02d}:{m.group(2) or '00'}" if m else str(v)


def _issue(verite, extrait, egal) -> str:
    if verite is None:
        if extrait is None:
            return "juste"
        return "substitut" if isinstance(extrait, str) and SUBSTITUTS.search(extrait) else "invente"
    if extrait is None:
        return "omis"
    return "juste" if egal(verite, extrait) else "faux"


def noter_champs(verite: dict, outil: str | None, a: dict | None) -> dict:
    """L'issue de chaque champ noté, et celle du type."""
    t = verite["type"]
    issues = {"type": "juste" if outil and TYPES.get(outil) == t else "faux"}
    if a is None or TYPES.get(outil) != t:
        return issues
    same = lambda x, y: x == y
    if t == "constat":
        va, vb = a.get("vehicule_a") or {}, a.get("vehicule_b") or {}
        blesses = a.get("blesses")
        if isinstance(blesses, bool):
            blesses = "oui" if blesses else "non"
        issues |= {
            "date_accident": _issue(verite["date_accident"], a.get("date_accident"), lambda x, y: x == _date(y)),
            "heure": _issue(verite["heure"], a.get("heure"), lambda x, y: x == _heure(y)),
            "blesses": _issue(verite["blesses"], blesses, same),
            "plaque_a": _issue(verite["plaque_a"], va.get("plaque"), lambda x, y: _plaque(x) == _plaque(y)),
            "contrat_a": _issue(verite["contrat_a"], va.get("numero_contrat"), lambda x, y: x in str(y)),
            "plaque_b": _issue(verite["plaque_b"], vb.get("plaque"), lambda x, y: _plaque(x) == _plaque(y)),
            "assureur_b": _issue(verite["assureur_b"], vb.get("assureur"), lambda x, y: x.split()[0].lower() in str(y).lower()),
        }
    elif t == "facture":
        lignes = a.get("lignes") or []
        issues |= {
            "numero_facture": _issue(verite["numero_facture"], a.get("numero_facture"), lambda x, y: x in str(y)),
            "date_facture": _issue(verite["date_facture"], a.get("date_facture"), lambda x, y: x == _date(y)),
            "plaque": _issue(verite["plaque"], a.get("plaque"), lambda x, y: _plaque(x) == _plaque(y)),
            "total_declare": _issue(verite["total_declare"], a.get("total_declare_fcfa"), same),
            "lignes": _issue(verite["somme_lignes"], sum(l["montant_fcfa"] for l in lignes) if lignes else None, same),
        }
    elif t == "rapport_expert":
        conclusion = a.get("conclusion")
        if isinstance(conclusion, bool):
            conclusion = "reparable" if conclusion else "irreparable"
        issues |= {
            "numero_sinistre": _issue(verite["numero_sinistre"], a.get("numero_sinistre"), same),
            "date_expertise": _issue(verite["date_expertise"], a.get("date_expertise"), lambda x, y: x == _date(y)),
            "plaque": _issue(verite["plaque"], a.get("plaque"), lambda x, y: _plaque(x) == _plaque(y)),
            "montant_evalue": _issue(verite["montant_evalue"], a.get("montant_evalue_fcfa"), same),
            "vetuste_pct": _issue(verite["vetuste_pct"], a.get("vetuste_pct"), same),
            "conclusion": _issue(verite["conclusion"], conclusion, same),
        }
    return issues


# --- L'appel, la validation, la relance -------------------------------------------------------------

def appeler(client, variante: str, messages: list, choix: dict, cas: str):
    texte_prompt = {"naif": "naif", "exemples": "exemples"}.get(variante, "soigne")
    liste = outils("naif" if variante == "naif" else "soigne")
    if variante == "sans-autre":   # « any » sans outil pour ce qui n'est ni constat, ni facture, ni rapport
        liste = [o for o in liste if o["name"] != "document_non_reconnu"]
    r = client.messages.create(model=MODELE, max_tokens=MAX_TOKENS, system=prompt(texte_prompt),
                               tools=liste, tool_choice=choix,
                               thinking={"type": "disabled"}, cache_control={"type": "ephemeral"}, messages=messages)
    c = cout(MODELE, r.usage)
    noter(getattr(r, "_request_id", None), MODELE, c, chapitre="12", etape="extraction", cas=cas)
    appel = next((b for b in r.content if b.type == "tool_use"), None)
    return r, appel, c.dollars


def requis(variante: str, outil: str) -> list[str]:
    return next(o for o in outils("naif" if variante == "naif" else "soigne") if o["name"] == outil)["input_schema"]["required"]


def extraire(client, variante: str, doc_id: str, repetition: int) -> dict:
    messages = [{"role": "user", "content": f"Document :\n\n{DOCUMENTS[doc_id]}"}]
    choix = {"type": "auto"} if variante == "naif" else {"type": "any"}
    r, appel, depense = appeler(client, variante, messages, choix, f"{variante}:{doc_id}")
    e = {"variante": variante, "document": doc_id, "repetition": repetition, "stop_reason": r.stop_reason,
         "outil": appel.name if appel else None, "arguments": appel.input if appel else None,
         "texte_sans_outil": "".join(b.text for b in r.content if b.type == "text") if not appel else None}
    e["erreurs"], e["conflit_source"] = valider(e["outil"], e["arguments"], variante == "exiger",
                                                requis(variante, e["outil"])) if appel else ([], False)
    e["issues"] = noter_champs(VERITE[doc_id], e["outil"], e["arguments"])
    e["relance"], e["arguments_apres"], e["erreurs_apres"], e["issues_apres"] = False, None, None, None
    e["stop_reason_apres"], e["champs_manquants_apres"] = None, None
    if appel and e["erreurs"] and variante != "naif":
        messages += [{"role": "assistant", "content": r.content},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": appel.id, "is_error": True,
                                                   "content": "Erreurs de validation :\n- " + "\n- ".join(e["erreurs"])
                                                   + "\nCorrigez ces champs, et rappelez l'outil avec tous ses arguments."}]}]
        r2, appel2, d2 = appeler(client, variante, messages, {"type": "tool", "name": appel.name}, f"{variante}:{doc_id}:relance")
        depense += d2
        e["relance"] = True
        e["stop_reason_apres"] = r2.stop_reason
        if appel2:
            e["champs_manquants_apres"] = sorted(set(requis(variante, appel2.name)) - set(appel2.input))
            e["arguments_apres"] = appel2.input
            e["erreurs_apres"], e["conflit_source"] = valider(appel2.name, appel2.input, variante == "exiger",
                                                              requis(variante, appel2.name))
            e["issues_apres"] = noter_champs(VERITE[doc_id], appel2.name, appel2.input)
    e["cout_dollars"] = depense
    return e


def resumer(essais: list[dict]) -> dict:
    lignes = {}
    for v in dict.fromkeys(e["variante"] for e in essais):
        g = [e for e in essais if e["variante"] == v]
        finales = [(e, e["issues_apres"] or e["issues"]) for e in g]
        compte = defaultdict(lambda: defaultdict(int))
        for e, issues in finales:
            type_ = VERITE[e["document"]]["type"]
            for champ, issue in issues.items():
                compte[f"{type_}.{champ}"][issue] += 1
        def precision(filtre):
            n = sum(c[i] for k, c in compte.items() if filtre(k) for i in c)
            return round(sum(c["juste"] for k, c in compte.items() if filtre(k)) / n, 3) if n else None
        par_champ = {k: dict(c) for k, c in sorted(compte.items())}
        lignes[v] = {
            "extractions": len(g),
            "sans_outil": sum(e["outil"] is None for e in g),
            "type_juste": sum(i["type"] == "juste" for _, i in finales),
            "precision_globale": precision(lambda k: not k.endswith(".type")),
            "precision_par_type": {t: precision(lambda k, t=t: k.startswith(t + ".") and not k.endswith(".type"))
                                   for t in ("constat", "facture", "rapport_expert")},
            "inventions": sum(i == "invente" for _, iss in finales for i in iss.values()),
            "substituts": sum(i == "substitut" for _, iss in finales for i in iss.values()),
            "omissions": sum(i == "omis" for _, iss in finales for i in iss.values()),
            "avec_erreurs_de_format": sum(bool(e["erreurs"]) for e in g),
            "relances": sum(e["relance"] for e in g),
            "erreurs_restantes_apres_relance": sum(bool(e["erreurs_apres"]) for e in g if e["relance"]),
            "inventions_creees_par_la_relance": sum(
                sum(i == "invente" for i in (e["issues_apres"] or {}).values()) -
                sum(i == "invente" for i in e["issues"].values()) for e in g if e["relance"]),
            "conflits_signales": sorted({e["document"] for e in g if e["conflit_source"]}),
            "par_champ": par_champ,
            "cout_par_document": statistics.mean(e["cout_dollars"] for e in g),
        }
    return lignes


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 12 : l'extraction des documents.")
    parser.add_argument("--variantes", nargs="*", default=["naif", "soigne", "exemples"],
                        choices=["naif", "soigne", "exemples", "exiger", "sans-autre"])
    parser.add_argument("--documents", nargs="*", default=list(VERITE))
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--budget-max", type=float, default=0.30)
    parser.add_argument("--fichier", default=None)
    parser.add_argument("--reevaluer", type=Path, default=None,
                        help="renoter un fichier de résultats avec la notation et le contrôle actuels, sans appel")
    args = parser.parse_args()
    if args.reevaluer:
        d = json.loads(args.reevaluer.read_text(encoding="utf-8"))
        for e in d["essais"]:
            v = VERITE[e["document"]]
            if e["arguments"] is not None:
                e["erreurs"], e["conflit_source"] = valider(e["outil"], e["arguments"], e["variante"] == "exiger",
                                                            requis(e["variante"], e["outil"]))
            e["issues"] = noter_champs(v, e["outil"], e["arguments"])
            if e["arguments_apres"] is not None:
                e["erreurs_apres"], e["conflit_source"] = valider(e["outil"], e["arguments_apres"],
                                                                  e["variante"] == "exiger", requis(e["variante"], e["outil"]))
                e["issues_apres"] = noter_champs(v, e["outil"], e["arguments_apres"])
        d["resume"] = resumer(d["essais"])
        args.reevaluer.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({v: {k: x for k, x in r.items() if k != "par_champ"} for v, r in d["resume"].items()},
                         ensure_ascii=False, indent=1))
        return

    client = anthropic.Anthropic()
    taches = [(v, d, r) for v in args.variantes for r in range(1, args.repetitions + 1) for d in args.documents]
    # Ordre de grandeur : 2 000 tokens d'entrée et 400 de sortie par appel, une relance sur trois.
    estimation = 3 * len(taches) * 1.33 * (2000 * 0.10 + 400 * 0.50) / 1_000_000   # large : trois fois
    if estimation > args.budget_max:
        raise SystemExit(f"Estimation large de {francais(estimation, 3)} $ au-dessus du plafond.")
    with ThreadPoolExecutor(max_workers=6) as pool:
        essais = list(pool.map(lambda t: extraire(client, *t), taches))
    depense = sum(e["cout_dollars"] for e in essais)
    resume = resumer(essais)
    print(json.dumps({v: {k: x for k, x in r.items() if k != "par_champ"} for v, r in resume.items()},
                     ensure_ascii=False, indent=2))
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    nom = args.fichier or f"extraction-{'-'.join(args.variantes)}"
    sortie = DOSSIER / "resultats" / f"{nom}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "depense_dollars": round(depense, 6),
                                  "resume": resume, "essais": essais}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
