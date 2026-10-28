"""Chapitre 2 : le chiffrage d'un cas d'usage. Aucun appel à l'API : un faux client compte et répond."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from assureur.couts import cout_tokens
from ch02.chiffrer import BudgetDepasse, chiffrer, cout_unite, entrees_par_tour

KANVO = Path(__file__).parents[1] / "ch02" / "kanvo.json"


class FauxClient:
    """Compte un token par mot, prompt système compris, plus 5 tokens d'enveloppe ; répond en `sortie` tokens."""

    def __init__(self, sortie=200, reflexion=0, arret="end_turn"):
        self.arret = arret
        self.appels = []
        self.messages = self
        self.sortie = sortie
        self.reflexion = reflexion

    def count_tokens(self, model, messages, system=None):
        mots = sum(len(m["content"].split()) for m in messages) + (len(system.split()) if system else 0)
        return SimpleNamespace(input_tokens=mots + 5)

    def create(self, model, max_tokens, system, messages):
        self.appels.append(model)
        entree = self.count_tokens(model, messages, system).input_tokens
        usage = SimpleNamespace(input_tokens=entree, output_tokens=self.sortie, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0, cache_creation=None,
                                output_tokens_details=SimpleNamespace(thinking_tokens=self.reflexion))
        return SimpleNamespace(usage=usage, stop_reason=self.arret, _request_id="req_faux")


def test_l_entree_grandit_de_tour_en_tour():
    # Système 300, message 50, réponse 100 : tour 1 = 350, tour 2 = 350 + 150, tour 3 = 350 + 300.
    assert entrees_par_tour(300, 50, 100, 3) == [350, 500, 650]
    assert entrees_par_tour(300, 50, 100, 1) == [350]


def test_le_cout_d_une_unite_somme_ses_tours():
    attendu = sum(cout_tokens("claude-sonnet-5-5", e, 100) for e in (350, 500, 650))
    assert cout_unite("claude-sonnet-5-5", 300, 50, 100, 3) == pytest.approx(attendu)
    # À la main : entrée 1 500 tokens à 2 $, sortie 300 tokens à 10 $ le million.
    assert cout_unite("claude-sonnet-5-5", 300, 50, 100, 3) == pytest.approx((1500 * 2 + 300 * 10) / 1e6)


def test_sans_mesure_aucun_appel_payant(tmp_path):
    donnees = json.loads(KANVO.read_text(encoding="utf-8"))
    client = FauxClient()
    resultats, depense = chiffrer(donnees, client, journal=str(tmp_path / "j.jsonl"))
    assert client.appels == [] and depense == 0
    assert all(not r.reponse_mesuree for r in resultats)
    # Deux cas, deux modèles chacun.
    assert [(r.cas, r.modele) for r in resultats] == [
        ("declaration", "claude-sonnet-5-5"), ("declaration", "claude-haiku-5-5"),
        ("constats", "claude-haiku-5-5"), ("constats", "claude-sonnet-5-5")]
    declaration = resultats[0]
    assert declaration.tokens_reponse == 250  # la sortie supposée du fichier
    assert declaration.cout_mois == pytest.approx(declaration.cout_unite * 2400)
    assert declaration.cout_mois_avec_marge == pytest.approx(declaration.cout_mois * 1.5)


def test_la_mesure_remplace_la_sortie_supposee_et_se_journalise(tmp_path):
    donnees = json.loads(KANVO.read_text(encoding="utf-8"))
    journal = tmp_path / "j.jsonl"
    client = FauxClient(sortie=180, reflexion=40)
    resultats, depense = chiffrer(donnees, client, mesurer=True, budget_max=1.0, journal=str(journal))
    assert len(client.appels) == 2 * 4 + 2 * 3  # chaque exemple, pour chaque modèle
    assert all(r.reponse_mesuree and r.tokens_reponse == 180 and r.tokens_reflexion == 40 for r in resultats)
    lignes = [json.loads(l) for l in journal.read_text(encoding="utf-8").splitlines()]
    assert len(lignes) == 14 and lignes[0]["chapitre"] == "02" and lignes[0]["requete"] == "req_faux"
    assert sum(l["cout_dollars"] for l in lignes) == pytest.approx(depense, abs=1e-5)


def test_le_plafond_arrete_avant_l_appel(tmp_path):
    donnees = json.loads(KANVO.read_text(encoding="utf-8"))
    client = FauxClient()
    with pytest.raises(BudgetDepasse):
        chiffrer(donnees, client, mesurer=True, budget_max=0.000001, journal=str(tmp_path / "j.jsonl"))
    assert client.appels == []


def test_le_message_ne_compte_pas_le_prompt_systeme():
    donnees = {"marge": 1.0, "cas": [{
        "id": "x", "nom": "Essai", "unite": "dossier", "unites_par_mois": 10, "tours": 1,
        "modeles": ["claude-haiku-5-5"], "max_tokens": 100, "sortie_supposee": 10,
        "systeme": "un deux trois quatre", "exemples": ["cinq six", "sept huit neuf dix"]}]}
    r = chiffrer(donnees, FauxClient())[0][0]
    assert r.tokens_systeme == 4          # les mots du prompt système
    assert r.tokens_message == 8          # (2 + 5 + 4 + 5) / 2 : le message et son enveloppe


def test_une_reponse_coupee_est_signalee(tmp_path):
    donnees = json.loads(KANVO.read_text(encoding="utf-8"))
    resultats, _ = chiffrer(donnees, FauxClient(arret="max_tokens"), mesurer=True, budget_max=1.0,
                            journal=str(tmp_path / "j.jsonl"), seulement=["constats"])
    assert {r.cas for r in resultats} == {"constats"}
    assert all(r.reponses_coupees == 3 for r in resultats)
