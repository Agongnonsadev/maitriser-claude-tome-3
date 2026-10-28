"""Chapitre 14 : la panne de janvier 2027, l'index qu'on n'a pas reconstruit.

L'édition 2027 des conditions et du tableau automobiles (ch14/edition_2027.py) régit les sinistres
survenus à partir du 1er janvier 2027. Le dossier source la contient ; l'index d'octobre, non. Cinq
états de la base, sur les huit questions qui dépendent de l'édition (quatre sinistres de 2026, quatre de
2027) :
- octobre, sans métadonnées : l'index d'octobre, ses passages présentés sans référence ni période, comme
  dans bien des bases documentaires ;
- octobre, sans filtre de date : l'index d'octobre, tel qu'il tournait, chaque passage avec sa période ;
- remplacee : l'index refait avec l'édition 2027 à la place de l'édition 2026 ;
- deux_editions, sans filtre de date : les deux éditions, le modèle choisit d'après la période des passages ;
- deux_editions, avec filtre de date : les deux éditions, le code choisit d'après la date du sinistre.

Le diagnostic, lui, ne coûte rien : le manifeste de l'index (l'empreinte de chaque document indexé)
comparé au dossier source dit quels documents manquent.

Lancement, depuis le dossier python/ :  python -m ch14.panne --repetitions 2 --budget-max 0.06
"""

import argparse
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import anthropic

from assureur import config
from assureur.couts import francais
from ch14.assistant import MODELE, essayer, reevaluer
from ch14.corpus import charger, decouper, ecarts, manifeste
from ch14.mesurer_recherche import BASE_OCTOBRE, questions
from ch14.recherche import IndexBM25

DOSSIER = Path(__file__).parent
AUTRES = [n for n in BASE_OCTOBRE if "auto" not in n]
BASES = {
    "octobre": BASE_OCTOBRE,
    "remplacee": AUTRES + ["cg-auto-2027", "tableau-auto-2027"],
    "deux_editions": BASE_OCTOBRE + ["cg-auto-2027", "tableau-auto-2027"],
}
# (base, stratégie de recherche, passages avec leurs métadonnées)
ETATS = [("octobre", "produit", False), ("octobre", "produit", True), ("remplacee", "produit", True),
         ("deux_editions", "produit", True), ("deux_editions", "filtre", True)]


def diagnostic() -> dict:
    """Ce que dit le manifeste de l'index d'octobre, comparé au dossier source de janvier."""
    return ecarts(manifeste(charger(BASE_OCTOBRE)), manifeste(charger()))


def resumer(essais: list[dict]) -> dict:
    resume = {}
    for b, s, m in ETATS:
        g = [e for e in essais if e["base"] == b and e["strategie"] == s and e.get("metadonnees", True) == m]
        if not g:
            continue
        de = lambda annee: [e for e in g if e["question"] in (("v2", "v4", "v6") if annee == 2026 else ("v1", "v3", "v5", "v7", "v8"))]
        resume[f"{b} / {'avec' if s == 'filtre' else 'sans'} filtre de date / {'avec' if m else 'sans'} métadonnées"] = {
            "justes": f"{sum(e['issue'] == 'juste' for e in g)}/{len(g)}",
            "sinistres_2026": f"{sum(e['issue'] == 'juste' for e in de(2026))}/{len(de(2026))}",
            "sinistres_2027": f"{sum(e['issue'] == 'juste' for e in de(2027))}/{len(de(2027))}",
            "je_ne_trouve_pas": sum(not e["trouve"] for e in g),
            "reponses_fausses": sum(e["trouve"] and e["issue"] != "juste" for e in g),
            "duree_mediane_s": round(statistics.median(e["duree_recherche_s"] + e["duree_reponse_s"] for e in g), 2),
        }
    return resume


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 14 : l'index périmé.")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--budget-max", type=float, default=0.06)
    parser.add_argument("--reevaluer", type=Path, default=None, help="renoter un fichier de résultats, sans appel")
    args = parser.parse_args()
    if args.reevaluer:
        d = reevaluer(args.reevaluer)
        d["resume"] = resumer(d["essais"])
        args.reevaluer.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(d["resume"], ensure_ascii=False, indent=1))
        return
    print("Diagnostic par le manifeste :", json.dumps(diagnostic(), ensure_ascii=False))
    qs = questions("editions")
    taches = [(b, s, m, q) for b, s, m in ETATS for q in qs for _ in range(args.repetitions)]
    if len(taches) * 0.0005 > args.budget_max:   # large : 0,0005 $ par réponse, à cinq passages
        raise SystemExit("Estimation au-dessus du plafond.")
    client = anthropic.Anthropic()
    index = {b: IndexBM25(decouper(charger(noms))) for b, noms in BASES.items()}
    with ThreadPoolExecutor(max_workers=6) as pool:
        essais = list(pool.map(lambda t: essayer(client, index[t[0]], t[3], t[1], 5, "structure", False, t[0], t[2]), taches))
    resume = resumer(essais)
    print(json.dumps(resume, ensure_ascii=False, indent=1))
    depense = sum(e["dollars"] for e in essais)
    print(f"Dépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / "resultats" / f"panne-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "diagnostic": diagnostic(),
                                  "depense_dollars": round(depense, 6), "resume": resume, "essais": essais},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
