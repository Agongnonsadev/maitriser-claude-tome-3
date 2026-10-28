"""Chapitre 9 : le système d'études de la souscription, coordinateur et sous-agents. Aucun appel à l'API."""

import asyncio
import json
import re

import pytest

from assureur import documents

pytest.importorskip("claude_agent_sdk")

from ch09 import etudes  # noqa: E402
from ch09.sous_agents import OUTILS_DU_ROLE, PREFIXE, definitions  # noqa: E402
from ch09.suivi import Suivi  # noqa: E402


def hook(fn, entree):
    return asyncio.run(fn(entree, "t1", None))


def refuse(reponse: dict) -> bool:
    return reponse.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


# --- Les documents internes ----------------------------------------------------------------

def test_les_six_documents_et_leurs_metadonnees():
    b = documents.Bibliotheque()
    assert [d["document"] for d in b.lister()] == [f"SOUS-0{i}" for i in range(1, 7)]
    assert all(d["date"] and d["titre"] and d["objet"] for d in b.lister())


def test_le_contenu_est_separe_de_ses_metadonnees():
    texte, erreur = documents.executer(documents.Bibliotheque(), "lire_document", {"document": "sous-03"})
    lu = json.loads(texte)
    assert not erreur and lu["document"] == "SOUS-03" and lu["date"] == "2026-09-15"
    assert [s["section"] for s in lu["sections"]][1] == "2. Les demandes pour le renouvellement"
    assert "30 milliards" in lu["sections"][1]["texte"]


def test_les_chiffres_du_corpus_se_tiennent():
    """Les totaux des tableaux fabriqués : par zone et par commune, on retrouve l'année 2025."""
    b = documents.Bibliotheque()
    sections = {s["section"]: s["texte"] for s in b.documents["SOUS-01"].sections}
    assert "| 2025 | 5 350 | 446 |" in sections["2. Évolution annuelle"]
    assert 2000 + 2140 + 1210 == 5350 and 39 + 139 + 268 == 446 and 24 + 108 + 260 == 392
    assert 3280 + 1520 + 550 == 5350 and 301 + 118 + 27 == 446 and 268 + 99 + 25 == 392
    assert round(620 / 1520 * 100) == 41 and round(71 / 620 * 100, 1) == 11.5


@pytest.mark.parametrize("identifiant", ["../../systeme.json", "C:/Windows/win.ini", "SOUS-1", "SOUS-09"])
def test_lire_document_ne_lit_que_le_catalogue(identifiant):
    texte, erreur = documents.executer(documents.Bibliotheque(), "lire_document", {"document": identifiant})
    assert erreur and json.loads(texte)["erreur"]["categorie"] in ("validation", "metier")


def test_un_rapport_vide_est_refuse_et_un_rapport_complet_numerote():
    b = documents.Bibliotheque()
    assert documents.executer(b, "enregistrer_rapport", {"titre": "x", "contenu": " "})[1]
    texte, erreur = documents.executer(b, "enregistrer_rapport", {"titre": "Étude", "contenu": "# Étude"})
    assert not erreur and json.loads(texte)["rapport"] == "RAP-001" and b.rapports[0]["titre"] == "Étude"


# --- Les sous-agents -------------------------------------------------------------------------

def test_chaque_sous_agent_n_a_que_les_outils_de_son_role():
    for nom, definition in definitions().items():
        assert set(definition.tools) == OUTILS_DU_ROLE[nom]
        assert "Agent" not in definition.tools and "Task" not in definition.tools
        assert definition.maxTurns and definition.model == etudes.MODELE


def test_chaque_sous_agent_rend_contenu_et_metadonnees():
    d = definitions()
    assert '"url"' in d["chercheur-web"].prompt and '"date_publication"' in d["chercheur-web"].prompt
    assert '"document"' in d["analyste-documents"].prompt and '"section"' in d["analyste-documents"].prompt
    assert '"conteste"' in d["synthetiseur"].prompt and '"manque"' in d["synthetiseur"].prompt


# --- Le suivi et les bornes -----------------------------------------------------------------

def test_le_coordinateur_ne_fait_que_deleguer():
    s = Suivi(definitions())
    assert refuse(hook(s.avant_outil, {"tool_name": "WebSearch", "tool_input": {"query": "x"}}))
    assert refuse(hook(s.avant_outil, {"tool_name": PREFIXE + "lire_document", "tool_input": {"document": "SOUS-01"}}))
    assert not refuse(hook(s.avant_outil, {"tool_name": "Agent", "tool_input": {
        "subagent_type": "analyste-documents", "description": "d", "prompt": "p"}}))
    assert len(s.delegations) == 1


def test_seuls_les_quatre_roles_existent():
    s = Suivi(definitions())
    for type_demande in ("general-purpose", "fork", None):
        assert refuse(hook(s.avant_outil, {"tool_name": "Agent", "tool_input": {"subagent_type": type_demande}}))
    assert s.delegations == []


def test_le_plafond_de_sous_agents_par_etude():
    s = Suivi(definitions(), max_sous_agents=2)
    entree = {"tool_name": "Task", "tool_input": {"subagent_type": "chercheur-web", "prompt": "p"}}
    assert [refuse(hook(s.avant_outil, entree)) for _ in range(3)] == [False, False, True]
    raison = hook(s.avant_outil, entree)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Terminez avec les résultats obtenus" in raison


def test_un_sous_agent_hors_de_ses_outils_et_le_plafond_de_recherches():
    s = Suivi(definitions(), max_recherches=2)
    hook(s.debut_sous_agent, {"agent_id": "a1", "agent_type": "synthetiseur"})
    assert refuse(hook(s.avant_outil, {"tool_name": "WebSearch", "tool_input": {}, "agent_id": "a1",
                                       "agent_type": "synthetiseur"}))
    hook(s.debut_sous_agent, {"agent_id": "a2", "agent_type": "chercheur-web"})
    web = {"tool_name": "WebSearch", "tool_input": {"query": "q"}, "agent_id": "a2", "agent_type": "chercheur-web"}
    assert [refuse(hook(s.avant_outil, web)) for _ in range(3)] == [False, False, True]


def test_une_definition_elargie_par_megarde_se_voit_au_journal():
    agents = definitions()
    agents["synthetiseur"].tools = ["WebSearch"]
    s = Suivi(agents)
    hook(s.debut_sous_agent, {"agent_id": "a1", "agent_type": "synthetiseur"})
    assert not refuse(hook(s.avant_outil, {"tool_name": "WebSearch", "tool_input": {}, "agent_id": "a1",
                                           "agent_type": "synthetiseur"}))
    assert s.evenements[-1]["hors_role"] is True


def test_la_chronologie_dit_ce_qui_a_tourne_en_meme_temps():
    s = Suivi(definitions())
    s.evenements = [{"t": 1.0, "evenement": "debut", "agent_id": "a", "agent_type": "analyste-documents"},
                    {"t": 2.0, "evenement": "debut", "agent_id": "b", "agent_type": "chercheur-web"},
                    {"t": 3.0, "evenement": "outil", "agent_id": "b", "agent_type": "chercheur-web",
                     "outil": "WebSearch", "refuse": False},
                    {"t": 30.0, "evenement": "fin", "agent_id": "a", "agent_type": "analyste-documents",
                     "dernier_message": "SOUS-01"},
                    {"t": 40.0, "evenement": "fin", "agent_id": "b", "agent_type": "chercheur-web",
                     "dernier_message": "https://exemple.org/a"},
                    {"t": 41.0, "evenement": "debut", "agent_id": "c", "agent_type": "synthetiseur"},
                    {"t": 50.0, "evenement": "fin", "agent_id": "c", "agent_type": "synthetiseur",
                     "dernier_message": ""}]
    lignes = {l["agent_id"]: l for l in s.sous_agents()}
    assert s.simultanes_max() == 2
    assert lignes["a"]["duree"] == 29.0 and lignes["b"]["outils"] == ["WebSearch"]


def test_ce_que_le_coordinateur_transmet_au_synthetiseur():
    s = Suivi(definitions())
    s.evenements = [{"t": 1.0, "evenement": "debut", "agent_id": "a", "agent_type": "analyste-documents"},
                    {"t": 9.0, "evenement": "fin", "agent_id": "a", "agent_type": "analyste-documents",
                     "dernier_message": '{"document": "SOUS-01"}, {"document": "SOUS-03"}'},
                    {"t": 2.0, "evenement": "debut", "agent_id": "b", "agent_type": "chercheur-web"},
                    {"t": 8.0, "evenement": "fin", "agent_id": "b", "agent_type": "chercheur-web",
                     "dernier_message": '{"url": "https://exemple.org/crue."}'}]
    s.delegations = [{"t": 10.0, "subagent_type": "synthetiseur",
                      "prompt": "Résultats : SOUS-01 … https://exemple.org/crue"}]
    appel = etudes.transmis_au_synthetiseur(s)["appels"][0]
    assert appel["sources_trouvees"] == 3 and appel["sources_transmises"] == 2
    assert appel["manquantes"] == ["SOUS-03"]


# --- Le coordinateur -----------------------------------------------------------------------

def test_les_prompts_du_coordinateur():
    objectifs, procedure, sequentiel = (etudes.PROMPTS[n] for n in ("objectifs", "procedure", "sequentiel"))
    for prompt in (objectifs, procedure, sequentiel):
        assert "Cotonou, au Bénin" in prompt
    assert "Une bonne étude" in objectifs and "rapport enregistré" in objectifs and "1. Demandez au chercheur-web" in procedure
    assert etudes.PARALLELE in objectifs and etudes.SEQUENTIEL in sequentiel
    assert sequentiel.replace(etudes.SEQUENTIEL, etudes.PARALLELE) == objectifs


def test_les_bornes_du_systeme(tmp_path):
    agents = definitions()
    o = etudes.options(documents.Bibliotheque(), Suivi(agents), agents, str(tmp_path / "travail"),
                       str(tmp_path / "configuration"), 0.30, etudes.PROMPTS["objectifs"])
    assert o.tools == ["Agent", "WebSearch"] and o.disallowed_tools == ["Agent(fork)"]
    assert o.max_budget_usd == 0.30 and o.permission_mode == "dontAsk" and o.setting_sources == []
    assert o.env["CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH"] == "1"
    assert o.env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] == "4"
    assert o.env["CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS"] == "1"
    assert not o.env["CLAUDE_CONFIG_DIR"].startswith(o.cwd)
    assert set(o.hooks) == {"PreToolUse", "PostToolUse", "SubagentStart", "SubagentStop"}


def test_les_questions_et_leurs_aspects():
    assert set(etudes.QUESTIONS) == {"q1-inondation", "q2-motos", "q3-travaux"}
    for q in etudes.QUESTIONS.values():
        assert set(q["sous_agents_utiles"]) <= set(definitions())
    texte = "Ratio de 116 % [SOUS-01, section 2] ; zone C ; réponse au réassureur avant le 30 novembre ; " \
            "https://exemple.org ; 2026 provisoire."
    assert all(re.search(m, texte, re.IGNORECASE) for m in etudes.QUESTIONS["q1-inondation"]["aspects"].values())


# --- Le synthétiseur rejoué, avec ou sans la recherche web ----------------------------------

def test_la_demande_rejouee_est_celle_que_le_coordinateur_a_ecrite(tmp_path):
    from ch09.hors_role import demande_du_coordinateur
    fichier = tmp_path / "etudes.json"
    fichier.write_text(json.dumps({"etudes": [{"delegations": [
        {"type": "analyste-documents", "prompt": "a"},
        {"type": "synthetiseur", "prompt": "Résultats : SOUS-01 et https://exemple.org/crue"}]}]}),
        encoding="utf-8")
    demande, source = demande_du_coordinateur(fichier)
    assert demande.startswith("Résultats") and source == "etudes.json"
    assert etudes.sources_citees(demande) == {"SOUS-01", "https://exemple.org/crue"}
