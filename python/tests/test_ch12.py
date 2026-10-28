"""Chapitre 12 : l'extraction structurée, ses schémas, ses contrôles et sa notation. Aucun appel à l'API."""

import json
from pathlib import Path

import pytest

from ch12 import extraire, fabriquer
from ch12.schemas import outils, prompt

DOSSIER = Path(__file__).parents[1] / "ch12"


def test_les_documents_se_refabriquent_a_l_identique():
    for d in fabriquer.fabriquer():
        assert (DOSSIER / "documents" / f"{d['id']}.txt").read_text(encoding="utf-8").strip() == d["texte"].strip()
        assert extraire.VERITE[d["id"]] == d["verite"]


def test_le_corpus():
    types = [v["type"] for v in extraire.VERITE.values()]
    assert (types.count("constat"), types.count("facture"), types.count("rapport_expert"), types.count("autre")) == (12, 12, 10, 2)
    factures = [v for v in extraire.VERITE.values() if v["type"] == "facture"]
    assert sorted(v["incoherence"] for v in factures) == [False] * 10 + [True] * 2
    assert all((v["somme_lignes"] != v["total_declare"]) == v["incoherence"] for v in factures)
    muets = sum(x is None for v in extraire.VERITE.values() for x in v.values())
    assert muets == 10   # 2 heures, 5 plaques, 1 assureur, 2 vétustés : ce que les documents taisent


def test_le_schema_soigne_reste_sous_la_limite_des_unions():
    unions = sum(json.dumps(o["input_schema"]).count('"type": [') for o in outils("soigne"))
    assert unions == 15 <= 16
    assert all('"type": [' not in json.dumps(o["input_schema"]) for o in outils("naif"))
    assert all(o["strict"] for v in ("naif", "soigne") for o in outils(v))


def test_chaque_objet_strict_exige_tous_ses_champs():
    def objets(s):
        if isinstance(s, dict):
            if s.get("type") == "object":
                yield s
            for v in s.values():
                yield from objets(v)
    for o in outils("soigne"):
        for obj in objets(o["input_schema"]):
            assert set(obj["required"]) == set(obj["properties"]) and obj["additionalProperties"] is False


def test_les_prompts():
    assert "null" not in prompt("naif") and "AAAA-MM-JJ" in prompt("soigne")
    assert prompt("exemples").startswith(prompt("soigne")) and "Garage Saint-Michel" in prompt("exemples")
    for texte in extraire.DOCUMENTS.values():   # les exemples ne viennent pas du corpus
        assert "Saint-Michel" not in texte and "rue des Cheminots" not in texte


@pytest.mark.parametrize("valeur, attendu", [("16/10/2026", "2026-10-16"), ("16 octobre 2026", "2026-10-16"),
                                             ("16-10-26", "2026-10-16"), ("16.10.2026", "2026-10-16"),
                                             ("2026-10-16", "2026-10-16")])
def test_lire_une_date(valeur, attendu):
    assert extraire._date(valeur) == attendu


def test_la_validation_distingue_format_conflit_et_champ_manquant():
    facture = {"numero_facture": "F-1", "date_facture": "16/10/2026", "garage": "G", "plaque": "AB-1234-CD",
               "lignes": [{"designation": "x", "montant_fcfa": 100}, {"designation": "y", "montant_fcfa": 50}],
               "total_declare_fcfa": 200, "total_calcule_fcfa": 140, "incoherence": False}
    erreurs, conflit = extraire.valider("extraire_facture", facture, requis=extraire.requis("soigne", "extraire_facture"))
    assert conflit is True                                     # la source : 150 de lignes, 200 déclarés
    assert any("date_facture" in e for e in erreurs) and any("plaque" in e for e in erreurs)
    assert any("total_calcule_fcfa" in e for e in erreurs) and any("incoherence" in e for e in erreurs)
    manque = {k: facture[k] for k in ("numero_facture", "date_facture", "garage", "plaque")}
    assert len([e for e in extraire.valider("extraire_facture", manque,
                                            requis=extraire.requis("soigne", "extraire_facture"))[0]
                if "manquant" in e]) == 4


def test_un_champ_absent_n_est_pas_une_erreur_sauf_si_on_l_exige():
    constat = {"date_accident": "2026-10-16", "heure": None, "lieu": "x", "blesses": "unclear",
               "vehicule_a": {"plaque": "AB 1234 CD", "numero_contrat": "KA-AUTO-1234"},
               "vehicule_b": {"plaque": None, "assureur": None}}
    assert extraire.valider("extraire_constat", constat) == ([], False)
    assert extraire.valider("extraire_constat", constat, exiger=True)[0] == [
        "vehicule_b.plaque : la plaque du véhicule B est obligatoire."]


def test_la_notation_des_issues():
    v = extraire.VERITE["constat-04"]          # plaque de B illisible
    base = {"date_accident": v["date_accident"], "heure": v["heure"], "lieu": "x", "blesses": v["blesses"],
            "vehicule_a": {"plaque": v["plaque_a"].replace(" ", "-"), "numero_contrat": v["contrat_a"]},
            "vehicule_b": {"plaque": None, "assureur": v["assureur_b"]}}
    assert set(extraire.noter_champs(v, "extraire_constat", base).values()) == {"juste"}   # le format n'est pas noté ici
    for valeur, issue in (("illisible", "substitut"), ("<UNKNOWN>", "substitut"), ("", "substitut"),
                          ("BD 3318 RB", "invente")):
        a = json.loads(json.dumps(base))
        a["vehicule_b"]["plaque"] = valeur
        assert extraire.noter_champs(v, "extraire_constat", a)["plaque_b"] == issue
    r = extraire.VERITE["rapport-03"]          # vétusté non mentionnée
    a = {"numero_sinistre": r["numero_sinistre"], "date_expertise": r["date_expertise"], "plaque": r["plaque"],
         "montant_evalue_fcfa": r["montant_evalue"], "vetuste_pct": 0, "conclusion": True, "expert": "x"}
    issues = extraire.noter_champs(r, "extraire_rapport_expert", a)
    assert issues["vetuste_pct"] == "invente" and issues["conclusion"] == "juste"   # le booléen naïf, lu « réparable »
    assert extraire.noter_champs(extraire.VERITE["autre-01"], "extraire_constat", {})["type"] == "faux"


def test_les_resultats_mesures():
    f = sorted((DOSSIER / "resultats").glob("extraction-naif-soigne-exemples-exiger-*.json"))[-1]
    r = json.loads(f.read_text(encoding="utf-8"))["resume"]
    assert r["soigne"]["precision_globale"] == 1.0 and r["soigne"]["inventions"] == 0
    assert r["naif"]["inventions"] == 4 and r["naif"]["sans_outil"] == 4
    assert r["exiger"]["substituts"] == 6
