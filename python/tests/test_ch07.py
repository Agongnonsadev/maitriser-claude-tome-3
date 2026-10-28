"""Chapitre 7 : le serveur MCP de Kanvô Assurances, ses droits, sa configuration d'équipe. Aucun appel à l'API."""

import asyncio
import json
import re
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import Client

from assureur import outils_v2
from assureur.jetons import COMPTES, creer_registre, empreinte, identifier
from assureur.serveur_mcp import DESCRIPTIONS, PORTEE, construire
from assureur.systeme import Systeme

ICI = Path(__file__).parents[1] / "ch07"
TOUT = {"sinistres:lecture", "transmissions:ecriture"}


def avec_client(serveur, fn):
    async def _():
        async with Client(serveur, raise_exceptions=True) as client:
            return await fn(client)
    return asyncio.run(_())


# --- Les jetons ------------------------------------------------------------------------------

def test_le_registre_ne_garde_que_des_empreintes(tmp_path):
    chemin = tmp_path / "jetons.json"
    jetons = creer_registre(chemin)
    texte = chemin.read_text(encoding="utf-8")
    assert all(j not in texte for j in jetons.values())  # aucun jeton en clair
    assert empreinte(jetons["agent-sinistres"]) in texte
    assert identifier(jetons["tableau-de-bord"], chemin) == ("tableau-de-bord", set(COMPTES["tableau-de-bord"]))
    assert identifier("kanvo_faux", chemin) is None and identifier(None, chemin) is None


def test_aucun_compte_n_a_encore_l_indemnisation():
    assert all("indemnisations:ecriture" not in p for p in COMPTES.values())


# --- Le serveur : ce qu'il montre dépend du compte -------------------------------------------

def test_chaque_compte_ne_voit_que_les_outils_de_ses_portees():
    noms = lambda portees: avec_client(construire("x", portees), lambda c: c.list_tools())
    assert [t.name for t in noms(TOUT).tools] == outils_v2.NOMS
    lecture = [t.name for t in noms({"sinistres:lecture"}).tools]
    assert "transmettre_a_un_gestionnaire" not in lecture and len(lecture) == 4


def test_le_serveur_reprend_le_catalogue_du_chapitre_6():
    outils = avec_client(construire("x", TOUT), lambda c: c.list_tools()).tools
    assert {t.name: t.description for t in outils} == DESCRIPTIONS["riches"]
    schema = next(t for t in outils if t.name == "transmettre_a_un_gestionnaire").input_schema
    assert schema["properties"]["motif"]["enum"] == outils_v2.MOTIFS
    assert next(t for t in outils if t.name == "consulter_sinistre").annotations.read_only_hint is True


def test_les_descriptions_courtes_tiennent_en_une_ligne():
    outils = avec_client(construire("x", TOUT, descriptions="courtes"), lambda c: c.list_tools()).tools
    assert all(len(t.description) < 40 for t in outils)


def test_un_appel_rend_le_systeme_en_direct(tmp_path):
    audit = tmp_path / "audit.jsonl"
    r = avec_client(construire("agent-sinistres", TOUT, audit=str(audit)),
                    lambda c: c.call_tool("consulter_sinistre", {"numero_sinistre": "SIN-2026-0912"}))
    assert not r.is_error and json.loads(r.content[0].text)["statut"] == "expertise planifiée"
    ligne = json.loads(audit.read_text(encoding="utf-8"))
    assert ligne["compte"] == "agent-sinistres" and ligne["outil"] == "consulter_sinistre" and ligne["issue"] == "ok"
    assert "SIN-2026-0912" not in audit.read_text(encoding="utf-8")  # le journal ne garde pas les données


@pytest.mark.parametrize("outil, arguments", [
    ("trouver_assure", {"nom": "M. Zinsou"}), ("trouver_assure", {"numero_assure": "KA-AS-1006"}),
    ("consulter_contrat", {"numero_contrat": "KA-AUTO-0731"}),
    ("lister_sinistres_du_contrat", {"numero_contrat": "KA-AUTO-0731"}),
    ("consulter_sinistre", {"numero_sinistre": "SIN-2026-0788"}),
    ("transmettre_a_un_gestionnaire", {"motif": "hors_perimetre", "resume": "r", "numero_contrat": "KA-AUTO-0731"}),
])
def test_chaque_outil_repond_comme_au_chapitre_6(outil, arguments):
    r = avec_client(construire("x", TOUT), lambda c: c.call_tool(outil, arguments))
    attendu, _ = outils_v2.executer(Systeme(), outil, arguments)
    assert not r.is_error and json.loads(r.content[0].text) == json.loads(attendu)


def test_une_erreur_structuree_arrive_en_is_error():
    r = avec_client(construire("x", TOUT), lambda c: c.call_tool("consulter_contrat", {"numero_contrat": "KA-SANTE-0318"}))
    assert r.is_error
    erreur = json.loads(r.content[0].text[r.content[0].text.index("{"):])["erreur"]
    assert erreur["categorie"] == "permission" and erreur["reessayable"] is False


def test_une_transmission_ecrit_dans_le_systeme():
    systeme = Systeme()
    avec_client(construire("agent-sinistres", TOUT, systeme=systeme),
                lambda c: c.call_tool("transmettre_a_un_gestionnaire", {"motif": "demande_d_un_humain", "resume": "r"}))
    assert systeme.transmissions[0]["motif"] == "demande_d_un_humain"


def test_le_referentiel_et_ce_que_disent_les_instructions():
    serveur = construire("x", {"sinistres:lecture"})
    ressources = avec_client(serveur, lambda c: c.list_resources()).resources
    assert [str(r.uri) for r in ressources] == ["kanvo://referentiel"]
    texte = avec_client(serveur, lambda c: c.read_resource("kanvo://referentiel")).contents[0].text
    assert "cinq ans" in texte and "SIN-" in texte
    assert "kanvo://referentiel" in construire("x", TOUT).instructions
    sans = construire("x", TOUT, ressource=False)
    assert avec_client(sans, lambda c: c.list_resources()).resources == [] and "referentiel" not in sans.instructions


def test_toute_portee_est_connue():
    assert set(PORTEE) == set(outils_v2.NOMS)


# --- La configuration d'équipe -------------------------------------------------------------

def test_le_mcp_json_du_depot_ne_contient_aucun_secret():
    texte = (ICI / "depot_dsi" / ".mcp.json").read_text(encoding="utf-8")
    config = json.loads(texte)["mcpServers"]["kanvo"]
    assert config["env"]["KANVO_JETON"] == "${KANVO_JETON}" and config["env"]["KANVO_JETONS"] == "${KANVO_JETONS}"
    assert not re.search(r"kanvo_[A-Za-z0-9_-]{20,}", texte)  # aucun jeton en clair


def test_l_export_du_depot_est_perime():
    export = (ICI / "depot_dsi" / "exports" / "sinistres-2026-10-15.csv").read_text(encoding="utf-8")
    assert "SIN-2026-0912;KA-AUTO-1180;2026-10-02;Collision avec une moto, carrefour Saint-Michel;déclaré" in export
    assert Systeme().consulter_sinistre("SIN-2026-0912")["statut"] == "expertise planifiée"


def test_les_options_du_poste_et_de_l_agent(tmp_path):
    pytest.importorskip("claude_agent_sdk")
    from ch07.agent_mcp import options as options_agent
    from ch07.poste_dsi import INTEGRES, classer, options as options_poste, source

    a = options_agent("jeton", tmp_path / "r.json", str(tmp_path), 0.05)
    serveur = a.mcp_servers["kanvo"]
    assert a.tools == [] and serveur["args"] == ["-m", "assureur.serveur_mcp"] and serveur["env"]["KANVO_JETON"] == "jeton"
    p = options_poste(str(tmp_path), "jeton", tmp_path / "r.json", 0.05, "courtes", "oui", tmp_path / "a.jsonl")
    assert p.setting_sources == ["project"] and p.tools == INTEGRES and p.mcp_servers == {}  # vient du .mcp.json
    assert p.system_prompt == {"type": "preset", "preset": "claude_code"} and p.env["KANVO_DESCRIPTIONS"] == "courtes"
    assert Path(p.env["CLAUDE_CONFIG_DIR"]).parent == tmp_path.parent  # à côté du dépôt, pas dedans
    assert [source(o) for o in ("Grep", "ReadMcpResourceTool", "consulter_sinistre")] == ["fichier", "ressource", "mcp"]
    q1 = json.loads((ICI / "questions_dsi.json").read_text(encoding="utf-8"))["questions"][0]
    assert classer("Le statut est « expertise planifiée ».", q1) == "à jour"
    assert classer("D'après l'export, le statut est « déclaré ».", q1) == "périmé"
