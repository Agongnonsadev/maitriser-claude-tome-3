"""Chapitre 21 : la comparaison par groupes de notes, et les documents de conformité. Aucun appel à l'API."""

import glob
import json
from pathlib import Path

from ch21.biais import GROUPES, comparer

RACINE = Path(__file__).parent.parent


def _cr(nid: str, a_corriger: bool) -> dict:
    return {"note": nid, "verdict": "a_corriger" if a_corriger else "fidele", "controles": {}}


def test_les_groupes():
    assert set(GROUPES) == {"dictée transcrite", "note sans conclusion", "conclusion avec réserves",
                            "clinique de Cotonou", "clinique d'Abidjan", "clinique de Dakar"}


def test_la_comparaison_d_un_groupe():
    cs = [_cr("N13", False), _cr("N18", False), _cr("N01", True), _cr("N02", False)]
    r = comparer(cs, "dictée transcrite")
    assert r["dans_le_groupe"] == "0 sur 2" and r["hors_du_groupe"] == "1 sur 2" and r["notes"] == ["N13", "N18"]
    assert r["par_note"] == {"N13": 0, "N18": 0}


def test_l_ecart_de_dakar_vient_de_deux_notes():
    # Sur l'essai du chapitre 19 jugé de nouveau : l'écart de la clinique de Dakar tient à N03 et N09.
    essai = sorted(glob.glob(str(RACINE / "ch19" / "resultats" / "ab-rejuge-*.json")))[-1]
    d = json.loads(Path(essai).read_text(encoding="utf-8"))
    r = comparer(d["comptes_rendus"], "clinique de Dakar")
    assert r["dans_le_groupe"] == "7 sur 36" and r["fisher_p"] < 0.05
    assert r["par_note"]["N03"] + r["par_note"]["N09"] == 6


def test_les_documents_de_conformite():
    registre = (RACINE / "ch21" / "registre-des-risques.md").read_text(encoding="utf-8")
    for texte in ("art. 394", "art. 407", "art. 7 et 26", "art. 49", "art. 9", "L. 1111-8", "2026/1744"):
        assert texte in registre, texte
    patient = (RACINE / "ch21" / "texte-au-patient.md").read_text(encoding="utf-8")
    assert "Il ne pose pas de diagnostic" in patient and "sans conséquence sur vos soins" in patient
