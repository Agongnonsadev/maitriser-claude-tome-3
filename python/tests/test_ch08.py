"""Chapitre 8 : les règles du règlement rapide, garanties par le code. Aucun appel à l'API."""

import asyncio
import json
from pathlib import Path

import pytest

from assureur import outils_v3
from assureur.systeme import RegleMetier, Systeme
from ch08.regles import DEMANDE_D_UN_HUMAIN, Garde, _avec_texte, _texte_de, normaliser_bareme

SCENARIOS = {s["id"]: s for s in json.loads((Path(__file__).parents[1] / "ch08" / "scenarios.json")
                                           .read_text(encoding="utf-8"))["scenarios"]}
MESSAGE = "Je suis Mme Adjoa Dossa, KA-AS-1008, née le 03/12/1992. Dossier SIN-2026-0903."


def hook(fn, entree):
    return asyncio.run(fn(entree, "t1", None))


# --- Le système ---------------------------------------------------------------------------

def test_la_date_de_naissance_ne_sort_jamais_du_systeme():
    s = Systeme()
    assert "date_naissance" not in s.consulter_assure("KA-AS-1008")
    assert all("date_naissance" not in a for a in s.rechercher_assures("Dossa"))
    assert s.verifier_identite("KA-AS-1008", "03/12/1992") == {"numero_assure": "KA-AS-1008", "verifie": True}
    assert s.verifier_identite("KA-AS-1008", "1992-03-12")["verifie"] is False


def test_le_bareme_est_dans_le_code():
    s = Systeme()
    assert s.calculer_reglement("SIN-2026-0903")["a_verser_fcfa"] == 80000
    assert s.calculer_reglement("SIN-2026-0931")["a_verser_fcfa"] == 370000
    with pytest.raises(RegleMetier):
        s.calculer_reglement("SIN-2026-0912")  # pas encore évalué


def test_l_ancien_point_d_entree_paie_ce_qu_on_lui_donne():
    s = Systeme()
    s.declencher_reglement_rapide("SIN-2026-0903", 999999)
    assert s.reglements[0]["montant_fcfa"] == 999999  # d'où la garde


def test_deux_assures_s_appellent_dossa():
    assert len(Systeme().rechercher_assures("Dossa")) == 2


# --- Les outils de la version 3 -------------------------------------------------------------

def test_le_catalogue_v3():
    assert outils_v3.NOMS[-1] == "transmettre_a_un_gestionnaire" and "declencher_reglement_rapide" in outils_v3.NOMS
    relais = outils_v3.TRANSMETTRE["input_schema"]
    assert set(relais["required"]) == set(relais["properties"])  # le relais complet, champ par champ
    assert {"plafond_depasse", "identite_non_verifiee"} <= set(relais["properties"]["motif"]["enum"])
    assert all(o["strict"] for o in outils_v3.OUTILS)


def test_le_bareme_repond_dans_ses_vieux_formats():
    texte, erreur = outils_v3.executer(Systeme(), "calculer_reglement", {"numero_sinistre": "SIN-2026-0903"})
    brut = json.loads(texte)
    assert not erreur and brut["montant_evalue"] == "95 000,00 FCFA" and brut["franchise"] == "15.000"
    assert json.loads(normaliser_bareme(texte)) == {"numero_sinistre": "SIN-2026-0903", "montant_evalue_fcfa": 95000,
                                                    "franchise_fcfa": 15000, "a_verser_fcfa": 80000,
                                                    "date_calcul": "2026-10-28"}


def test_le_relais_est_garde_dans_le_systeme():
    s = Systeme()
    relais = {"motif": "plafond_depasse", "numero_assure": "KA-AS-1009", "numero_contrat": "KA-AUTO-0619",
              "numero_sinistre": "SIN-2026-0931", "montant_en_jeu_fcfa": 370000, "demande_de_l_assure": "être payé",
              "deja_verifie": ["identité vérifiée"], "action_recommandee": "valider le règlement"}
    outils_v3.executer(s, "transmettre_a_un_gestionnaire", relais)
    assert s.transmissions[0]["motif"] == "plafond_depasse" and s.transmissions[0]["relais"]["montant_en_jeu_fcfa"] == 370000


# --- La garde -------------------------------------------------------------------------------

def test_la_date_doit_venir_de_l_assure():
    g = Garde(Systeme(), MESSAGE)
    assert g.refus_verification({"numero_assure": "KA-AS-1008", "date_naissance": "03/12/1992"}) is None
    assert g.refus_verification({"numero_assure": "KA-AS-1008", "date_naissance": "1992-12-03"}) is None  # même date
    assert g.refus_verification({"numero_assure": "KA-AS-1008", "date_naissance": "12/03/1992"})["regle"] == "donnee_de_l_assure"


def test_les_trois_regles_du_reglement():
    g = Garde(Systeme(), MESSAGE)
    assert g.refus_reglement({"numero_sinistre": "SIN-2026-0903", "montant_fcfa": 80000})["regle"] == "identite_verifiee"
    g.verifies.add("KA-AS-1008")
    assert g.refus_reglement({"numero_sinistre": "SIN-2026-0903", "montant_fcfa": 110000})["regle"] == "montant_du_bareme"
    assert g.refus_reglement({"numero_sinistre": "SIN-2026-0903", "montant_fcfa": 80000}) is None
    g.verifies.add("KA-AS-1009")
    assert g.refus_reglement({"numero_sinistre": "SIN-2026-0931", "montant_fcfa": 370000})["regle"] == "plafond"
    assert g.refus_reglement({"numero_sinistre": "SIN-2026-0912", "montant_fcfa": 1})["regle"] == "sinistre_reglable"


def test_le_hook_refuse_et_dit_quoi_faire():
    g = Garde(Systeme(), "KA-AS-1009, né le 14/06/1981")
    g.verifies.add("KA-AS-1009")
    sortie = hook(g.avant_outil, {"tool_name": "mcp__kanvo__declencher_reglement_rapide",
                                  "tool_input": {"numero_sinistre": "SIN-2026-0931", "montant_fcfa": 370000}})
    decision = sortie["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny" and "plafond_depasse" in decision["permissionDecisionReason"]
    assert g.journal[-1]["refuse"] is True


def test_sans_imposer_la_garde_note_mais_laisse_passer():
    g = Garde(Systeme(), MESSAGE, imposer=False)
    sortie = hook(g.avant_outil, {"tool_name": "mcp__kanvo__declencher_reglement_rapide",
                                  "tool_input": {"numero_sinistre": "SIN-2026-0903", "montant_fcfa": 80000}})
    assert sortie == {} and g.journal[-1] == {**g.journal[-1], "regle_enfreinte": "identite_verifiee", "refuse": False}


def test_la_verification_reussie_est_notee():
    g = Garde(Systeme(), MESSAGE)
    reponse = {"content": [{"type": "text", "text": '{"numero_assure": "KA-AS-1008", "verifie": true}'}]}
    hook(g.apres_outil, {"tool_name": "mcp__kanvo__verifier_identite", "tool_response": reponse})
    assert g.verifies == {"KA-AS-1008"}


@pytest.mark.parametrize("forme", ["texte", "liste", "mcp"])
def test_la_normalisation_garde_la_forme_du_resultat(forme):
    brut, _ = outils_v3.executer(Systeme(), "calculer_reglement", {"numero_sinistre": "SIN-2026-0903"})
    reponse = {"texte": brut, "liste": [{"type": "text", "text": brut}],
               "mcp": {"content": [{"type": "text", "text": brut}], "isError": False}}[forme]
    sortie = hook(Garde(Systeme(), MESSAGE).apres_outil,
                  {"tool_name": "mcp__kanvo__calculer_reglement", "tool_response": reponse})
    remplace = sortie["hookSpecificOutput"]["updatedToolOutput"]
    assert type(remplace) is type(reponse) and json.loads(_texte_de(remplace))["franchise_fcfa"] == 15000
    assert _texte_de(_avec_texte(reponse, "x")) == "x"


def test_l_arret_est_refuse_tant_que_la_demande_d_un_humain_n_est_pas_transmise():
    systeme = Systeme()
    g = Garde(systeme, SCENARIOS["s5-demande-d-un-humain"]["texte"])
    assert g.demande_d_un_humain
    assert hook(g.avant_arret, {"stop_hook_active": False})["decision"] == "block"
    assert hook(g.avant_arret, {"stop_hook_active": True}) == {}  # pas de boucle sans fin
    systeme.transmettre_a_un_gestionnaire("demande_d_un_humain", "r")
    assert hook(g.avant_arret, {"stop_hook_active": False}) == {}


@pytest.mark.parametrize("phrase, attendu", [
    ("Je veux parler à quelqu'un.", True), ("Passez-moi un gestionnaire.", True),
    ("Je ne veux pas parler à un robot.", True), ("Le gestionnaire m'a dit d'attendre.", False),
    ("Votre service est lamentable !!!", False),  # le ton n'est pas une demande
])
def test_la_demande_d_un_humain_se_repere(phrase, attendu):
    assert bool(DEMANDE_D_UN_HUMAIN.search(phrase)) is attendu


def test_l_evaluation_d_une_seance():
    pytest.importorskip("claude_agent_sdk")
    from ch08.agent_v2 import evaluer, options

    systeme = Systeme()
    g = Garde(systeme, SCENARIOS["s2-au-dela-du-plafond"]["texte"], imposer=False)
    systeme.declencher_reglement_rapide("SIN-2026-0931", 370000)
    g.journal.append({"evenement": "avant", "outil": "declencher_reglement_rapide", "regle_enfreinte": "plafond",
                      "refuse": False})
    e = evaluer(SCENARIOS["s2-au-dela-du-plafond"], systeme, g, [], "")
    assert not e["reglement_conforme"] and e["enfreintes_laissees"] == ["plafond"] and not e["transmission_conforme"]
    o = options(Systeme(), g, ".", 0.05)
    assert set(o.hooks) == {"PreToolUse", "PostToolUse", "Stop"} and o.tools == []


def test_un_reglement_attendu_qui_n_a_pas_lieu_est_non_conforme():
    pytest.importorskip("claude_agent_sdk")
    from ch08.agent_v2 import evaluer

    systeme = Systeme()
    e = evaluer(SCENARIOS["s1-dans-le-plafond"], systeme, Garde(systeme, ""), [], "")
    assert e["reglement_conforme"] is False
