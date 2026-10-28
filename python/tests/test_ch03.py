"""Chapitre 3 : le banc de décision. Aucun appel à l'API : un faux client répond."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ch03.banc import (REGLAGES, BudgetDepasse, controler_declaration, lancer, lire_json, normaliser,
                       noter_constat, resumer)

CAS = json.loads((Path(__file__).parents[1] / "ch03" / "cas.json").read_text(encoding="utf-8"))
SYSTEMES = {"constats": "Extrais le constat en JSON.", "declarations": "Aide l'assuré."}


def test_le_json_se_lit_meme_entoure():
    assert lire_json('{"a": 1}') == ({"a": 1}, False)
    assert lire_json('```json\n{"a": 1}\n```') == ({"a": 1}, True)
    assert lire_json("Je ne peux pas.") == (None, True)
    assert lire_json('{"a": ') == (None, True)


@pytest.mark.parametrize("champ, valeur, attendu", [
    ("date", "14/10/2026", "2026-10-14"), ("date", "2026-10-14", "2026-10-14"),
    ("date", "5 oct. 2026", "2026-10-05"), ("date", "lundi dernier", "lundi dernier"),
    ("heure", "18 h 20", "18:20"), ("heure", "vers 9 h", "09:00"), ("heure", "07h45", "07:45"),
    ("immatriculation", "ab 4417 rb", "AB4417RB"), ("blesses", "non", False), ("blesses", True, True),
    ("numero_police", "null", None), ("numero_police", "", None),
])
def test_normaliser(champ, valeur, attendu):
    assert normaliser(champ, valeur) == attendu


def test_un_constat_parfait_et_un_constat_qui_invente():
    verite = CAS["constats"][0]["verite"]  # c1 : police et assureur de B illisibles
    parfait = {"date": "14/10/2026", "heure": "18 h 20", "blesses": False,
               "vehicule_a": {"immatriculation": "AB 4417 RB", "numero_police": "KA-AUTO-0552"},
               "vehicule_b": {"immatriculation": "BC 0918 RB", "numero_police": None, "assureur": None}}
    assert noter_constat(parfait, verite) == {"justes": 8, "total": 8, "inventions": 0, "faux": []}
    invente = {**parfait, "vehicule_b": {"immatriculation": "BC 0918 RB", "numero_police": "KA-AUTO-0000",
                                         "assureur": "Kanvô Assurances"}}
    notes = noter_constat(invente, verite)
    assert notes["inventions"] == 2 and notes["justes"] == 6


def test_un_champ_ambigu_n_est_pas_note():
    verite = CAS["constats"][1]["verite"]  # c2 : assureur de B ambigu
    assert noter_constat({}, verite)["total"] == 7


def test_les_regles_des_declarations():
    d3 = CAS["declarations"][2]  # l'assuré a payé 185 000 FCFA
    bonne = "Nous avons bien noté votre hospitalisation et les 185 000 FCFA payés. Quel est votre numéro de contrat ?"
    assert all(controler_declaration(bonne, d3).values())
    promesse = "Vous serez remboursé de 150 000 FCFA sous 10 jours. Quel est votre contrat ?"
    controles = controler_declaration(promesse, d3)
    assert controles["sans_promesse"] is False and controles["contrat_demande"] is True
    assert controler_declaration("Peux-tu m'envoyer ta facture ?", d3)["vouvoiement"] is False


def test_l_escalade_attendue():
    d4 = CAS["declarations"][3]
    assert controler_declaration("Un gestionnaire va vous rappeler aujourd'hui.", d4)["escalade"] is True
    assert controler_declaration("Pouvez-vous me redonner votre numéro de dossier ?", d4)["escalade"] is False


class FauxClient:
    def __init__(self, texte_constat='{"date": "14/10/2026"}', texte_declaration="Quel est votre contrat ?"):
        self.messages = self
        self.textes = {"constats": texte_constat, "declarations": texte_declaration}
        self.appels = []

    def count_tokens(self, model, system, messages):
        return SimpleNamespace(input_tokens=400)

    def create(self, model, max_tokens, system, messages, **options):
        self.appels.append((model, options))
        etape = "constats" if max_tokens == 2000 else "declarations"
        usage = SimpleNamespace(input_tokens=400, output_tokens=300, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0, cache_creation=None,
                                output_tokens_details=SimpleNamespace(thinking_tokens=100))
        return SimpleNamespace(usage=usage, stop_reason="end_turn", _request_id="req_faux",
                               content=[SimpleNamespace(type="text", text=self.textes[etape])])


def test_le_banc_passe_les_options_de_chaque_reglage(tmp_path):
    client = FauxClient()
    essais, depense = lancer(client, CAS, SYSTEMES, repetitions=1, journal=str(tmp_path / "j.jsonl"))
    assert len(essais) == len(REGLAGES) * (6 + 6) and depense > 0
    assert ("claude-haiku-5-5", {"thinking": {"type": "disabled"}}) in client.appels
    assert ("claude-sonnet-5-5", {"thinking": {"type": "between_tools"}}) in client.appels
    lignes = resumer(essais)
    constats = next(l for l in lignes if l["etape"] == "constats" and l["reglage"] == "haiku-defaut")
    assert constats["essais"] == 6 and constats["json_illisibles"] == 0
    declarations = next(l for l in lignes if l["etape"] == "declarations" and l["reglage"] == "sonnet-defaut")
    assert 0 < declarations["regles_respectees"] < 1  # pas d'escalade pour d4


def test_le_plafond_arrete_avant_l_appel(tmp_path):
    client = FauxClient()
    with pytest.raises(BudgetDepasse):
        lancer(client, CAS, SYSTEMES, repetitions=1, budget_max=0.000001, journal=str(tmp_path / "j.jsonl"))
    assert client.appels == []
