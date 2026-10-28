"""Chapitre 10 : erreurs entre agents, provenance, longues conversations. Aucun appel à l'API."""

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from assureur import documents

pytest.importorskip("claude_agent_sdk")

from ch09.etudes import Etude  # noqa: E402
from ch09.sous_agents import definitions as definitions_v1  # noqa: E402
from ch10 import conversation, etudes_v2  # noqa: E402
from ch10.sous_agents_v2 import definitions as definitions_v2  # noqa: E402

SUPPLEMENTS = (Path(__file__).parents[1] / "ch10" / "documents",)


def hook(fn, entree):
    return asyncio.run(fn(entree, "t1", None))


# --- Les documents, les pannes ----------------------------------------------------------------

def test_le_septieme_document_contredit_le_reassureur_et_date_le_cumul():
    b = documents.Bibliotheque(supplements=SUPPLEMENTS)
    assert sorted(b.documents) == [f"SOUS-0{i}" for i in range(1, 8)]
    texte = " ".join(s["texte"] for s in b.documents["SOUS-07"].sections)
    assert "109 %" in texte and "23,1" in texte and "24,8" in texte and "30 milliards" not in texte
    note = " ".join(s["texte"] for s in b.documents["SOUS-03"].sections)
    assert "116 %" in note and "30 milliards" in note and "35 %" in note


def test_le_chapitre_9_ne_voit_pas_le_septieme_document():
    assert "SOUS-07" not in documents.Bibliotheque().documents


def test_une_panne_passagere_echoue_une_fois():
    b = documents.Bibliotheque(pannes={"SOUS-03": 1})
    texte, erreur = documents.executer(b, "lire_document", {"document": "SOUS-03"})
    assert erreur
    assert json.loads(texte)["erreur"]["categorie"] == "passagere" and json.loads(texte)["erreur"]["reessayable"]
    assert not documents.executer(b, "lire_document", {"document": "SOUS-03"})[1]
    assert b.echecs == ["SOUS-03"] and b.lectures == ["SOUS-03"]


def test_une_panne_persistante_ne_cede_jamais():
    b = documents.Bibliotheque(pannes={"SOUS-03": -1})
    assert all(documents.executer(b, "lire_document", {"document": "SOUS-03"})[1] for _ in range(5))
    assert not documents.executer(b, "lire_document", {"document": "SOUS-01"})[1]


# --- Les sous-agents et le coordinateur, version 2 ---------------------------------------------

def test_la_version_2_garde_les_roles_et_les_outils():
    v1, v2 = definitions_v1(), definitions_v2()
    assert v1.keys() == v2.keys()
    for nom in v1:
        assert v1[nom].tools == v2[nom].tools and v1[nom].description == v2[nom].description


def test_chaque_sous_agent_dit_ses_erreurs_et_la_synthese_sa_couverture():
    d = definitions_v2()
    for nom in ("chercheur-web", "analyste-documents"):
        assert '"erreurs"' in d[nom].prompt and "réessaie une fois" in d[nom].prompt
        assert "n'est pas une erreur" in d[nom].prompt
    assert '"conflits"' in d["analyste-documents"].prompt
    assert '"couverture"' in d["synthetiseur"].prompt and "indisponible n'est pas une absence" in d["synthetiseur"].prompt
    assert "Couverture" in d["redacteur"].prompt and "tableau" in d["redacteur"].prompt


def test_le_prompt_du_coordinateur_version_2():
    p = etudes_v2.PROMPT_V2
    assert "Cotonou, au Bénin" in p and "rapport enregistré" in p
    assert "n'arrêtez jamais l'étude pour une seule source" in p and "le système joint lui-même" in p


# --- La panne web et les résultats joints -------------------------------------------------------

def test_la_panne_web_refuse_chaque_recherche_et_le_note():
    s = etudes_v2.SuiviV2(definitions_v2(), web_indisponible=True)
    hook(s.debut_sous_agent, {"agent_id": "w", "agent_type": "chercheur-web"})
    r = hook(s.avant_outil, {"tool_name": "WebSearch", "tool_input": {"query": "q"}, "agent_id": "w",
                             "agent_type": "chercheur-web"})
    assert r["hookSpecificOutput"]["permissionDecision"] == "deny" and "Réessayable" in \
        r["hookSpecificOutput"]["permissionDecisionReason"]
    assert s.evenements[-1]["panne"] and s.evenements[-1]["refuse"]


def _suivi_avec_resultats(joindre=True):
    s = etudes_v2.SuiviV2(definitions_v2(), joindre=joindre)
    for agent_id, type_, message in (("a", "analyste-documents", '{"resultats": [{"document": "SOUS-07"}]}'),
                                     ("b", "chercheur-web", '{"resultats": [{"url": "https://exemple.org/x"}]}')):
        hook(s.debut_sous_agent, {"agent_id": agent_id, "agent_type": type_})
        hook(s.fin_sous_agent, {"agent_id": agent_id, "agent_type": type_, "last_assistant_message": message})
    return s


def test_le_synthetiseur_recoit_les_resultats_complets_par_le_code():
    s = _suivi_avec_resultats()
    r = hook(s.avant_outil, {"tool_name": "Agent", "tool_input": {"subagent_type": "synthetiseur", "prompt": "Q"}})
    prompt = r["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert r["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert prompt.startswith("Q") and "SOUS-07" in prompt and "https://exemple.org/x" in prompt
    assert s.delegations[-1]["prompt"] == prompt and s.annexes[0]["resultats"] == ["analyste-documents", "chercheur-web"]


def test_le_redacteur_recoit_la_derniere_synthese_et_la_version_1_rien():
    s = _suivi_avec_resultats()
    hook(s.debut_sous_agent, {"agent_id": "c", "agent_type": "synthetiseur"})
    hook(s.fin_sous_agent, {"agent_id": "c", "agent_type": "synthetiseur", "last_assistant_message": '{"etabli": []}'})
    r = hook(s.avant_outil, {"tool_name": "Agent", "tool_input": {"subagent_type": "redacteur", "prompt": "R"}})
    assert '{"etabli": []}' in r["hookSpecificOutput"]["updatedInput"]["prompt"]
    v1 = _suivi_avec_resultats(joindre=False)
    assert hook(v1.avant_outil, {"tool_name": "Agent", "tool_input": {"subagent_type": "synthetiseur", "prompt": "Q"}}) == {}


# --- L'évaluation des scénarios -----------------------------------------------------------------

def test_les_motifs_des_scenarios():
    assert re.search(etudes_v2.NOTE_ILLISIBLE, "La note du réassureur (SOUS-03) n'a pas pu être lue : délai dépassé.",
                     re.IGNORECASE)
    assert not re.search(etudes_v2.NOTE_ILLISIBLE, "Le réassureur demande un zonage [SOUS-03, section 2].", re.IGNORECASE)
    assert re.search(etudes_v2.WEB_ILLISIBLE, "La recherche web a échoué (délai dépassé).", re.IGNORECASE)


def test_evaluer_un_rapport_qui_invente_le_contenu_d_une_note_illisible():
    sc = etudes_v2.SCENARIOS["panne-persistante"]
    e = Etude("panne-persistante", "v2", 1, rapport="La note du réassureur n'a pas pu être lue. Plafond de 30 milliards.")
    ev = etudes_v2.evaluer(sc, e, documents.Bibliotheque(), etudes_v2.SuiviV2(definitions_v2()))
    assert ev["attendus"]["lacune_signalee"] and ev["interdits"]["contenu_de_la_note"]


# --- La conversation de 40 tours ----------------------------------------------------------------

def test_le_script_de_la_conversation():
    assert len(conversation.SCRIPT["tours"]) == 40 and "point complet" in conversation.SCRIPT["tours"][-1]
    point = ("Devis de 412 500 FCFA du 14 octobre ; location 18 000 FCFA par jour depuis le 13 octobre ; avant le "
             "20 novembre, pour rendre la voiture ; pare-brise fissuré le 24 octobre sur la route de Porto-Novo ; "
             "Parakou du 5 au 12 novembre, par courriel ; SIN-2026-0931, 370 000 FCFA.")
    assert all(conversation.retrouves(point).values())
    assert sum(conversation.retrouves("Votre dossier SIN-2026-0931 est transmis.").values()) == 1


def test_chaque_fait_de_l_assure_est_dit_avant_le_point():
    tours = " ".join(conversation.SCRIPT["tours"][:-1])
    for nom, fait in conversation.SCRIPT["faits"].items():
        if fait["source"].startswith("assuré") and nom != "motif_limite":
            assert re.search(fait["motif"], tours, re.IGNORECASE), nom


def test_la_transcription_et_le_bloc_de_faits():
    m = [{"role": "user", "content": "Résumé de la conversation jusqu'ici : x"},
         {"role": "assistant", "content": "C'est noté."},
         {"role": "assistant", "content": [SimpleNamespace(type="text", text="Je regarde."),
                                           SimpleNamespace(type="tool_use", name="trouver_assure", input={"nom": "Kiki"})]},
         {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "1", "content": '{"ok": 1}'}]}]
    assert conversation.transcrire(m).splitlines() == [
        "Résumé de la conversation jusqu'ici : x", "Agent : Je regarde.",
        '[Appel d\'outil] trouver_assure {"nom": "Kiki"}', '[Résultat d\'outil] {"ok": 1}']
    assert conversation.avec_faits("") == conversation.PROMPT
    assert conversation.avec_faits("- devis : 412 500 FCFA").endswith("- devis : 412 500 FCFA")


def test_sans_synthese_le_redacteur_recoit_les_resultats_de_recherche():
    s = _suivi_avec_resultats()
    r = hook(s.avant_outil, {"tool_name": "Agent", "tool_input": {"subagent_type": "redacteur", "prompt": "R"}})
    prompt = r["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert "SOUS-07" in prompt and "https://exemple.org/x" in prompt
