"""Chapitre 22 : répéter la fin de vie d'un modèle, en passant son remplaçant au banc du chapitre 19.

Le modèle en production (Claude Haiku 5.5, prompt B) a une date de retrait annoncée « pas avant » une date. Le jour
où il sera déprécié, son remplaçant devra passer la même barrière que lui. On répète la migration dès maintenant,
avec le candidat disponible : le banc du chapitre 19 tel quel (mêmes vingt notes, même prompt B, même juge v2 avec
l'en-tête du rédacteur, mêmes contrôles du code), puis la barrière au même seuil. Seul le rédacteur change.

Lancement, depuis le dossier python/ :
    python -m ch22.migration --candidat claude-sonnet-5-5 --repetitions 3 --budget-max 0.50
"""

import argparse
import json
import statistics
import sys
from argparse import Namespace
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import francais
from ch19 import banc

DOSSIER = Path(__file__).parent


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 22 : le remplaçant d'un modèle passe le banc.")
    parser.add_argument("--candidat", default="claude-sonnet-5-5")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seuil", type=float, default=0.10)
    parser.add_argument("--budget-max", type=float, default=0.50)
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    banc.CHAPITRE = "22"
    r = banc.essai_ab(Namespace(modele=args.candidat, juge_modele="claude-haiku-5-5", juge="v2", bras=["B"],
                                repetitions=args.repetitions, budget_max=args.budget_max, sans_entete=False))
    resume = banc.resumer_ab(r["comptes_rendus"])
    resume["B"]["latence_mediane_s"] = round(statistics.median(c["latence_s"] for c in r["comptes_rendus"]), 2)
    sortie = DOSSIER / "resultats" / f"migration-{args.candidat.removeprefix('claude-')}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": args.candidat, "juge": "v2",
                                  "repetitions": args.repetitions, "depense_dollars": round(r["depense"], 6),
                                  "resume": resume, "comptes_rendus": r["comptes_rendus"]},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    banc.barriere(str(sortie), "B", args.seuil)
    print(f"\nDépense : {francais(r['depense'], 4)} $ (≈ {francais(r['depense'] * config.TAUX_FCFA, 1)} FCFA) ; {sortie}")


if __name__ == "__main__":
    principal()
