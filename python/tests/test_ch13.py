"""Chapitre 13 : l'archive, la correction des plaques, les requêtes d'un lot, le renvoi des échecs, la relecture
et le calibrage de la confiance. Aucun appel à l'API."""

import json
import re
from collections import Counter

from ch13 import calibrage, lot, relecture
from ch13.archive import DIFFICULTES, fabriquer
from ch13.echantillon import tirer
from ch13.extraction import CHAMPS, evaluer, normaliser, normaliser_plaque, outil, parametres, prompt


def test_l_archive_se_refabrique_a_l_identique():
    a, b = fabriquer(), fabriquer()
    assert a == b and len(a) == 1100
    assert len({c["id"] for c in a}) == 1100
    assert {c["difficulte"] for c in a} == {d for d, _ in DIFFICULTES}
    assert all(c["verite"]["plaque_b"] is None for c in a if c["difficulte"] == "plaque_partielle")
    assert all(c["verite"]["blesses"] == "unclear" for c in a if c["difficulte"] == "blesses_contradictoire")
    assert min(c["mois"] for c in a) == "2024-10" and max(c["mois"] for c in a) == "2026-09"


def test_l_echantillon_prend_dix_documents_par_difficulte():
    e = tirer(fabriquer())
    assert len(e) == 70 and e == tirer(fabriquer())
    assert set(Counter(c["difficulte"] for c in e).values()) == {10}


def test_le_code_corrige_les_plaques_selon_la_position():
    assert normaliser_plaque("RX 9I25 BT") == "RX 9125 BT"
    assert normaliser_plaque("ET 855B SZ") == "ET 8558 SZ"
    assert normaliser_plaque("DE 9999 8P") == "DE 9999 BP"
    assert normaliser_plaque("GN-6312-XJ") == "GN 6312 XJ"
    assert normaliser_plaque("fy2839hf") == "FY 2839 HF"
    assert normaliser_plaque("ZW 48?3 SG") is None            # un caractère illisible : null
    assert normaliser_plaque("UZ 919 DH") == "UZ 919 DH"      # trop court : laissé tel quel, le contrôle le refusera
    assert normaliser_plaque(None) is None


def test_la_correction_ne_touche_que_les_plaques_et_ne_modifie_pas_l_original():
    a = {"date_accident": "2026-01-02", "vehicule_a": {"plaque": "UZ 919I DH", "numero_contrat": "KA-AUTO-1725"},
         "vehicule_b": {"plaque": "CX 8485-CR", "assureur": "Atacora Garantie"}}
    n = normaliser(a)
    assert n["vehicule_a"]["plaque"] == "UZ 9191 DH" and n["vehicule_b"]["plaque"] == "CX 8485 CR"
    assert a["vehicule_a"]["plaque"] == "UZ 919I DH" and n["date_accident"] == a["date_accident"]


def test_l_evaluation_corrigee_rend_juste_une_plaque_abimee():
    doc = next(c for c in fabriquer() if c["difficulte"] == "ocr")
    v = doc["verite"]
    p = v["plaque_a"]
    abimee = (p[:3] + {"1": "I", "0": "O", "5": "S", "8": "B"}.get(p[3], "I") + p[4:]).replace(" ", "-")
    arguments = {"date_accident": v["date_accident"], "heure": v["heure"], "lieu": "x", "blesses": v["blesses"],
                 "vehicule_a": {"plaque": abimee, "numero_contrat": v["contrat_a"]},
                 "vehicule_b": {"plaque": v["plaque_b"], "assureur": v["assureur_b"]},
                 "confiance": {c: 0.9 for c in CHAMPS}}
    if p[3] in "1058":
        assert evaluer(doc, arguments, corriger=True)["issues"]["plaque_a"] == "juste"
    assert evaluer(doc, arguments)["erreurs"]   # sans la correction, le contrôle refuse le format


def test_les_versions_du_prompt():
    assert "Les factures" not in prompt("v1") and "constats amiables de l'archive" in prompt("v1")
    assert "corrigez selon la position" in prompt("v2")
    assert "recopiez chaque immatriculation" in prompt("v3") and "corrigez selon la position" not in prompt("v3")
    assert prompt("v4").startswith(prompt("v3").split("\n\nLa confiance")[0]) and "jour, mois, année" in prompt("v4")
    assert all("La confiance" in prompt(v) for v in ("v1", "v2", "v3", "v4"))


def test_l_outil_ajoute_la_confiance_sans_depasser_les_unions():
    o = outil()
    assert set(o["input_schema"]["properties"]["confiance"]["properties"]) == set(CHAMPS)
    assert json.dumps(o["input_schema"]).count('"type": [') <= 16


def test_le_point_d_arret_du_cache_suit_le_prefixe_commun():
    p = parametres("v3", "Document A")
    assert p["system"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"} and "cache_control" not in p
    assert p["tool_choice"] == {"type": "tool", "name": "extraire_constat"} and p["thinking"] == {"type": "disabled"}
    auto = parametres("v3", "Document A", cache="automatique")
    assert isinstance(auto["system"], str) and auto["cache_control"]["type"] == "ephemeral"
    assert "cache_control" not in parametres("v3", "Document A", cache=None) and isinstance(parametres("v3", "x", cache=None)["system"], str)
    # Deux documents partagent tout, sauf le message : c'est ce que le point d'arrêt du préfixe met en cache.
    b = parametres("v3", "Document B")
    assert p["system"] == b["system"] and p["tools"] == b["tools"] and p["messages"] != b["messages"]
    sonnet = parametres("v3", "Document A", "claude-sonnet-5-5")
    assert sonnet["tool_choice"] == {"type": "auto"} and sonnet["thinking"] == {"type": "between_tools"}


def test_les_requetes_d_un_lot():
    r = [lot.requete("v3", d) for d in fabriquer()]
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", x["custom_id"]) for x in r)
    assert len({x["custom_id"] for x in r}) == len(r)
    taille = sum(len(json.dumps(x, ensure_ascii=False).encode("utf-8")) for x in r)
    assert taille < 256 * 10**6 / 20   # l'archive de deux ans (24 fois plus) tiendrait sous 256 Mo


def test_le_renvoi_ne_prend_que_les_echecs():
    etat = {"resultats": [{"document": "arch-0001", "statut": "succeeded", "reussi": True},
                          {"document": "arch-0002", "statut": "succeeded", "reussi": False},
                          {"document": "arch-0003", "statut": "errored"},
                          {"document": "arch-0004", "statut": "expired"}]}
    assert [e["document"] for e in lot.echecs(etat)] == ["arch-0002", "arch-0003", "arch-0004"]


def test_la_relecture_independante_ne_voit_ni_le_prompt_ni_la_confiance():
    doc = fabriquer()[0]
    arguments = {"date_accident": "2026-01-01", "vehicule_a": {"plaque": "AB-1234-CD", "numero_contrat": "x"},
                 "vehicule_b": {"plaque": None, "assureur": None}, "confiance": {"date_accident": 0.9}}
    ind = relecture.independante(doc, arguments)
    texte = ind["messages"][0]["content"]
    assert "confiance" not in texte and "AB 1234 CD" in texte and ind["system"] == relecture.RELECTEUR
    assert [t["name"] for t in ind["tools"]] == ["signaler"]
    auto = relecture.auto(doc, arguments)
    assert auto["system"] == prompt("v2") and auto["messages"][1]["content"][0]["input"] == arguments
    assert relecture.CONSIGNE in auto["messages"][2]["content"][1]["text"] and relecture.CONSIGNE in texte
    assert relecture.SIGNALER["input_schema"]["required"] == CHAMPS


def test_le_calibrage():
    assert calibrage.tranche(0.84) == 0.8 and calibrage.tranche(0.9) == 0.9 and calibrage.tranche(None) == 0.0
    table = {"date_accident": {0.8: (11, 10), 0.85: (4, 4), 0.9: (316, 316)}, "heure": {0.9: (330, 330)}}
    assert calibrage.seuils(table) == {"date_accident": 0.85, "heure": 0.0}
    e = {"reussi": True, "arguments": {"blesses": "unclear", "vehicule_a": {"plaque": "AB 1234 CD"},
                                       "vehicule_b": {"plaque": "EF 5678 GH"}}}
    assert calibrage.par_regle(e)
    e["arguments"]["blesses"] = "non"
    assert not calibrage.par_regle(e)
    e["arguments"]["vehicule_b"]["plaque"] = "EF 56?8 GH"
    assert calibrage.par_regle(e)   # illisible : null après la correction, donc au gestionnaire


def test_les_formes_de_date_sont_observables():
    formes = Counter(calibrage.forme_de_date(c["texte"]) for c in fabriquer())
    assert set(formes) == {"jj-mm-aa", "aaaa-mm-jj", "jj/mm/aaaa", "jj.mm.aaaa", "en lettres"}
    assert formes["jj-mm-aa"] == 219
