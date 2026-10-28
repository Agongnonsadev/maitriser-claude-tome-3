"""Chapitre 24 : le vérificateur de passation. Aucun appel à l'API."""

from ch24.verifier_passation import RACINE, renvois, verifier


def test_les_renvois_sont_relevés():
    chemins, modules = renvois("Voir `ch19/banc.py`, puis `python -m ch19.banc barriere x`.")
    assert chemins == ["ch19/banc.py"] and modules == ["ch19.banc"]


def test_un_renvoi_casse_se_voit(tmp_path):
    (tmp_path / "ch99").mkdir()
    (tmp_path / "ch99" / "outil.py").write_text("", encoding="utf-8")
    texte = "`ch99/outil.py`, `ch99/disparu.py`, `ch99/resultats/<date>.json` et `python -m ch98.absent`."
    assert verifier(texte, tmp_path) == ["fichier introuvable : ch99/disparu.py",
                                         "fichier introuvable : ch99/resultats/<date>.json",
                                         "module introuvable : python -m ch98.absent"]


def test_la_passation_du_depot_ne_ment_pas():
    texte = (RACINE / "ch24" / "document-de-passation.md").read_text(encoding="utf-8")
    assert verifier(texte) == []
