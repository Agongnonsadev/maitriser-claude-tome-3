"""Chapitre 19 : le jeu d'étalonnage, les statistiques de l'essai A/B et la barrière. Aucun appel à l'API."""

import json

import pytest

from ch19.banc import (BRAS, JUGES, SCHEMA_VERDICT, a_corriger, barriere, entree_du_juge, fisher_bilateral,
                       mesurer_accord, resumer_ab, taille_par_bras, wilson)
from cliniques.etalonnage import DEFAUTS, PERTURBATIONS, PERTURBATIONS_SUBTILES, REFERENCES, paires
from cliniques.notes import note


def test_le_jeu_d_etalonnage():
    p = paires()
    assert len(p) == 45 and sum(x["annotation"] == "fidele" for x in p) == 16
    assert sum(x["difficile"] for x in p) == 14 and len(paires(difficiles=False)) == 31
    assert set(x["defaut"] for x in p if x["defaut"]) == set(DEFAUTS)


def test_chaque_compte_rendu_fautif_differe_de_sa_reference_par_un_seul_champ():
    for x in paires():
        if x["annotation"] == "a_corriger":
            ref = REFERENCES[x["note"]]
            assert sum(ref[k] != x["compte_rendu"][k] for k in ref) == 1, x


def test_les_references_suivent_les_notes():
    # Les conclusions de référence sont nulles là où le médecin n'a pas conclu.
    for nid, cr in REFERENCES.items():
        assert (cr["conclusion_du_medecin"] is None) == (note(nid)["conclusion"] is None), nid
    assert len(PERTURBATIONS) == 21 and len(PERTURBATIONS_SUBTILES) == 8


def test_les_statistiques():
    assert wilson(0, 10) == (0.0, 0.278) and wilson(15, 60) == (0.158, 0.372)
    # Test exact de Fisher : valeur connue pour 1/10 contre 6/10 (bilatéral, 0,0573)
    assert fisher_bilateral(1, 10, 6, 10) == pytest.approx(0.0573, abs=1e-4)
    assert fisher_bilateral(5, 50, 5, 50) == 1.0
    assert taille_par_bras(0.25, 0.05) == 49 and taille_par_bras(0.20, 0.05) == 76


def test_a_corriger_combine_le_juge_et_le_code():
    sain = {"verdict": "fidele", "controles": {"conclusion_inventee": False, "ajouts": []}}
    assert not a_corriger(sain)
    assert a_corriger({**sain, "verdict": "a_corriger"})
    assert a_corriger({**sain, "controles": {"conclusion_inventee": True, "ajouts": []}})
    assert a_corriger({**sain, "controles": {"ajouts": ["bilan"]}})
    assert a_corriger({**sain, "verdict": None})  # un verdict illisible ne passe pas


def test_l_accord_du_juge():
    js = [{"annotation": "a_corriger", "defaut": "cote_inverse", "verdict": "a_corriger", "note": "N01", "difficile": False},
          {"annotation": "a_corriger", "defaut": "omission", "verdict": "fidele", "note": "N02", "difficile": True},
          {"annotation": "fidele", "defaut": None, "verdict": "fidele", "note": "N05", "difficile": True}]
    m = mesurer_accord(js)
    assert m["sensibilite"] == "1 sur 2" and m["specificite"] == "1 sur 1" and m["faux_negatifs"] == ["N02:omission"]
    assert m["difficiles"] == {"sensibilite": "0 sur 1", "specificite": "1 sur 1"} and m["accord"] == 0.667


def test_le_juge_lit_ce_que_le_redacteur_a_lu():
    n = note("N19")
    assert "61 ans" in entree_du_juge(n, True) and "ORL" in entree_du_juge(n, True)
    assert "61 ans" not in entree_du_juge(n, False)  # la première version du banc


def test_les_bras_et_le_juge():
    assert BRAS["B"].startswith(BRAS["A"]) and "côtés" in BRAS["B"] and "côtés" not in BRAS["A"]
    assert "omet une constatation" in JUGES["v2"] and "omet" not in JUGES["v1"]
    assert set(SCHEMA_VERDICT["properties"]["defauts"]["items"]["enum"]) == set(DEFAUTS) | {"autre"}


def _essai(tmp_path, a: int, b: int, inventee_b: bool = False):
    cs = [{"bras": bras, "note": "N01", "verdict": "a_corriger" if i < k else "fidele",
           "controles": {"conclusion_inventee": inventee_b and bras == "B" and i == 0}, "defauts": [],
           "cout_redaction": 0.0004, "cout_juge": 0.0003}
          for bras, k in (("A", a), ("B", b)) for i in range(60)]
    f = tmp_path / "essai.json"
    f.write_text(json.dumps({"comptes_rendus": cs}), encoding="utf-8")
    return f, cs


def test_le_resume_et_la_barriere(tmp_path):
    f, cs = _essai(tmp_path, 15, 3)
    r = resumer_ab(cs)
    assert r["A"]["part"] == 0.25 and r["B"]["part"] == 0.05 and r["comparaison"]["ecart_points"] == -20.0
    assert r["comparaison"]["fisher_p"] < 0.01
    assert barriere(str(f), "B", 0.10) == 0 and barriere(str(f), "A", 0.10) == 1
    f2, _ = _essai(tmp_path, 15, 3, inventee_b=True)
    assert barriere(str(f2), "B", 0.10) == 1  # une conclusion inventée suffit à refuser
