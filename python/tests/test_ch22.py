"""Chapitre 22 : le disjoncteur, le repli, la file et le tableau de bord, avec un faux client. Aucun appel à l'API."""

import random
from types import SimpleNamespace as NS

import pytest

from ch22 import exploitation as ex
from ch22.exploitation import Disjoncteur, centile, tableau, temps_local

USAGE = NS(input_tokens=1000, output_tokens=400, cache_read_input_tokens=0, cache_creation_input_tokens=0,
           cache_creation=None, output_tokens_details=None)


@pytest.fixture(autouse=True)
def journal_temporaire(monkeypatch, tmp_path):
    monkeypatch.setattr("assureur.config.JOURNAL", str(tmp_path / "j.jsonl"))


class Faux:
    def __init__(self, en_panne: bool):
        self.en_panne, self.messages = en_panne, self

    def create(self, **k):
        if self.en_panne:
            raise ConnectionError("injoignable")
        cr = {"motif": "M.", "examen": "E.", "conclusion_du_medecin": None, "suite": None, "elements_absents": []}
        return NS(id="r", usage=USAGE, content=[NS(type="tool_use", input=cr)])


def test_le_disjoncteur():
    d = Disjoncteur(3)
    d.echec(), d.echec()
    assert not d.ouvert
    d.echec()
    assert d.ouvert and d.ouvertures == 1
    d.succes()
    assert not d.ouvert and d.echecs == 0


def test_le_delai_local_de_dakar_le_lundi():
    rng = random.Random(1)
    lent = [temps_local(rng, "Dakar", ex.JOURNEES["lundi"]) for _ in range(20)]
    normal = [temps_local(rng, "Cotonou", ex.JOURNEES["lundi"]) for _ in range(20)]
    assert min(lent) > 5 and max(normal) < 1.5


def test_une_journee_de_panne_ne_perd_aucune_note(monkeypatch):
    monkeypatch.setattr(ex, "client", lambda injoignable: Faux(injoignable))
    lignes, alertes, depense = ex.journee("mardi", random.Random(2), 1.0)
    abidjan = [l for l in lignes if l["site"] == "Abidjan" and l["issue"] != "file_traitee"]
    echecs = [l for l in abidjan if l["issue"] == "echec"]
    replis = [l for l in abidjan if l["issue"] == "repli"]
    traitees = [l for l in lignes if l["site"] == "Abidjan" and l["issue"] == "file_traitee"]
    assert len(echecs) == 3 and len(replis) == len(abidjan) - 3     # trois échecs, puis le disjoncteur ouvert
    assert len(traitees) == len(abidjan)                             # la file est traitée : rien de perdu
    assert alertes == ["Abidjan : disjoncteur ouvert 1 fois"] and depense > 0


def lignes_du_lundi(api_s: list[float]) -> list[dict]:
    lignes = []
    for site, local in (("Cotonou", 0.4), ("Abidjan", 0.4), ("Dakar", 6.0)):
        for i in range(6):
            t = api_s[(len(lignes)) % len(api_s)]
            lignes.append({"jour": "lundi", "site": site, "consultation": f"{site}{i}", "t_local_s": local,
                           "t_api_s": t, "t_total_s": local + t, "issue": "brouillon", "cout_dollars": 0.0004})
    return lignes


def test_le_tableau_de_bord_trouve_une_cause_locale():
    bord = tableau(lignes_du_lundi([5.0]))
    assert bord["tableau"]["lundi"]["sites"]["Dakar"]["t_total_p50_s"] == 11.0
    assert [a for a in bord["alertes"] if "cause locale" in a] == [
        "lundi Dakar : temps local médian 6,00 s (autres cliniques : 0,40 et 0,40 s) ; cause locale, avant l'appel à l'API"]
    assert not any("côté API" in a for a in bord["alertes"])


def test_une_traine_de_l_api_n_accuse_pas_les_cliniques():
    bord = tableau(lignes_du_lundi([5.0, 5.0, 25.0]))      # un appel sur trois au-delà de 10 s, partout
    assert bord["tableau"]["lundi"]["api"]["lents"] == 6
    assert any(a.startswith("lundi : 6 appels à l'API sur 18") and "Abidjan, Cotonou, Dakar" in a
               for a in bord["alertes"])
    assert sum("cause locale" in a for a in bord["alertes"]) == 1       # Dakar seulement


def test_le_centile():
    assert centile([1, 2, 3, 4, 100], 0.95) == 100 and centile([None, 2.0], 0.5) == 2.0 and centile([], 0.5) is None


def test_la_migration_note_ses_appels_au_chapitre_22(monkeypatch, tmp_path):
    import json
    from ch19 import banc
    from cliniques.notes import NOTES
    monkeypatch.setattr(banc, "CHAPITRE", "22")
    cr, dollars, _ = banc.rediger(Faux(False), "claude-sonnet-5-5", banc.BRAS["B"], NOTES[0])
    ligne = json.loads((tmp_path / "j.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert cr and dollars > 0 and ligne["chapitre"] == "22" and ligne["etape"] == "redaction"
