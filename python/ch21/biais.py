"""Chapitre 21 : chercher des résultats inégaux entre groupes de notes, sur les comptes rendus déjà jugés au chapitre 19.

Aucun appel : le script relit un essai jugé (ch19/resultats/ab-rejuge-…json) et compare, groupe par groupe, la part
des comptes rendus à corriger : les dictées transcrites contre les notes tapées, les notes sans conclusion, les
notes avec réserves, chaque clinique contre les deux autres. Pour chaque groupe, l'intervalle de Wilson et le test
exact de Fisher ; puis, pour un écart qui ressort, la décomposition note par note : un groupe peut sembler moins bien
servi parce qu'il contient deux notes difficiles, pas à cause de ce qui le définit.

Lancement, depuis le dossier python/ :
    python -m ch21.biais ch19/resultats/ab-rejuge-<date>.json
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from ch19.banc import a_corriger, fisher_bilateral, wilson
from cliniques.notes import note

DOSSIER = Path(__file__).parent

GROUPES = {
    "dictée transcrite": lambda n: bool(n.get("dictee")),
    "note sans conclusion": lambda n: n["conclusion"] is None,
    "conclusion avec réserves": lambda n: bool(n["reserves"]),
    "clinique de Cotonou": lambda n: n["clinique"] == "Cotonou",
    "clinique d'Abidjan": lambda n: n["clinique"] == "Abidjan",
    "clinique de Dakar": lambda n: n["clinique"] == "Dakar",
}


def comparer(comptes_rendus: list[dict], groupe: str) -> dict:
    f = GROUPES[groupe]
    dedans = [c for c in comptes_rendus if f(note(c["note"]))]
    dehors = [c for c in comptes_rendus if not f(note(c["note"]))]
    k1, k2 = sum(a_corriger(c) for c in dedans), sum(a_corriger(c) for c in dehors)
    return {
        "groupe": groupe,
        "notes": sorted({c["note"] for c in dedans}),
        "dans_le_groupe": f"{k1} sur {len(dedans)}", "part": round(k1 / max(len(dedans), 1), 3),
        "intervalle": wilson(k1, len(dedans)),
        "hors_du_groupe": f"{k2} sur {len(dehors)}", "part_hors": round(k2 / max(len(dehors), 1), 3),
        "fisher_p": fisher_bilateral(k1, len(dedans), k2, len(dehors)),
        "par_note": {n: sum(a_corriger(c) for c in dedans if c["note"] == n)
                     for n in sorted({c["note"] for c in dedans})},
    }


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 21 : des résultats inégaux entre groupes de notes ?")
    parser.add_argument("essai", help="un essai jugé du chapitre 19 (ab-rejuge-…json)")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    d = json.loads(Path(args.essai).read_text(encoding="utf-8"))
    resultats = [comparer(d["comptes_rendus"], g) for g in GROUPES]
    for r in resultats:
        print(f"{r['groupe']} : {r['dans_le_groupe']} {r['intervalle']} contre {r['hors_du_groupe']}, "
              f"p = {r['fisher_p']} ; par note {r['par_note']}")
    sortie = DOSSIER / "resultats" / f"biais-{date.today().isoformat()}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "source": args.essai, "comparaisons": len(resultats),
                                  "groupes": resultats}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
