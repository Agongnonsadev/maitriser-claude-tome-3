"""Chapitre 6 : ce que l'agent fait d'une erreur, selon la façon dont l'outil la lui rend.

Quatre situations (ch06/erreurs.json) : une panne passagère, un accès refusé, un dossier archivé,
un numéro mal formé. Pour chaque conduite, la réponse finale est classée :
- « faux » si elle contient un motif mauvais : elle affirme qu'il n'existe aucun dossier, ou, pour
  le numéro mal formé, elle donne le dossier d'un autre assuré ;
- « bon » si elle contient un motif bon ;
- « à relire » sinon.
On compte aussi les nouvelles tentatives (le même outil rappelé) et les transmissions.

Lancement, depuis le dossier python/ :
    python -m ch06.erreurs --variantes dsi yao --repetitions 3 --budget-max 0.10
    python -m ch06.erreurs --variantes yao-motif-strict --situations e4-validation --repetitions 3 --budget-max 0.03
"""

import argparse
import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import francais
from assureur.systeme import Systeme
from ch05.boucle import MODELE, BudgetDepasse, conduire
from ch06.catalogues import VARIANTES

DOSSIER = Path(__file__).parent


def classer(reponse: str, situation: dict) -> str:
    if any(re.search(m, reponse, re.IGNORECASE) for m in situation["mauvais"]):
        return "faux"
    if any(re.search(m, reponse, re.IGNORECASE) for m in situation["bons"]):
        return "bon"
    return "à relire"


def nouvelles_tentatives(outils: list[str]) -> int:
    """Combien d'appels répètent un outil déjà appelé dans la même conduite."""
    return len(outils) - len(set(outils))


def lancer(client, situations: list[dict], variantes: list[str], repetitions: int, budget_max: float,
           journal: str | None = None) -> tuple[list[dict], float]:
    essais, depense = [], 0.0
    for nom in variantes:
        v = VARIANTES[nom]
        for repetition in range(1, repetitions + 1):
            for s in situations:
                systeme = Systeme(pannes=s["pannes"])
                c = conduire(client, s["texte"], systeme=systeme, prompt=v.prompt, outils=v.outils,
                             executer_outil=v.executer, budget_restant=budget_max - depense, journal=journal,
                             cas=f"{nom}:{s['id']}", repetition=repetition, chapitre="06")
                depense += c.cout_dollars
                essais.append({"variante": nom, "situation": s["id"], "repetition": repetition, "fin": c.fin,
                               "outils": c.outils, "nouvelles_tentatives": nouvelles_tentatives(c.outils),
                               "appels": [{"outil": o, "entree": e} for t in c.tours for o, e in zip(t.outils, t.entrees)],
                               "transmissions": [t["motif"] for t in systeme.transmissions],
                               "classement": classer(c.reponse, s), "reponse": c.reponse,
                               "cout_dollars": c.cout_dollars})
    return essais, depense


def resumer(essais: list[dict]) -> list[dict]:
    lignes = []
    for nom in dict.fromkeys(e["variante"] for e in essais):
        for sid in dict.fromkeys(e["situation"] for e in essais if e["variante"] == nom):
            groupe = [e for e in essais if e["variante"] == nom and e["situation"] == sid]
            lignes.append({"variante": nom, "situation": sid, "conduites": len(groupe),
                           "classement": dict(Counter(e["classement"] for e in groupe)),
                           "nouvelles_tentatives": sum(e["nouvelles_tentatives"] for e in groupe),
                           "transmissions": dict(Counter(m for e in groupe for m in e["transmissions"]))})
    return lignes


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 6 : les erreurs d'outils.")
    parser.add_argument("--variantes", nargs="+", default=["dsi", "yao"], choices=list(VARIANTES))
    parser.add_argument("--situations", nargs="*", help="ne lancer que ces situations (leurs identifiants)")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--budget-max", type=float, default=0.10)
    args = parser.parse_args()

    import anthropic

    client = anthropic.Anthropic()
    situations = json.loads((DOSSIER / "erreurs.json").read_text(encoding="utf-8"))["situations"]
    situations = [s for s in situations if not args.situations or s["id"] in args.situations]
    try:
        essais, depense = lancer(client, situations, args.variantes, args.repetitions, args.budget_max)
    except BudgetDepasse as e:
        print(e)
        return
    for l in resumer(essais):
        print(f"{l['variante']:<18} {l['situation']:<14} {l['classement']} ; nouvelles tentatives "
              f"{l['nouvelles_tentatives']} ; transmissions {l['transmissions'] or 'aucune'}")
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / "resultats" / f"erreurs-{'-'.join(args.variantes)}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "repetitions": args.repetitions,
                                  "depense_dollars": round(depense, 6), "resume": resumer(essais), "essais": essais},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
