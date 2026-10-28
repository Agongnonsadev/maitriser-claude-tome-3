"""Chapitre 5 : la boucle, les outils, les réglages de l'Agent SDK. Aucun appel à l'API : un faux client répond."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from assureur.outils import NOMS, OUTILS, executer
from assureur.systeme import Introuvable, Systeme
from ch05.boucle import BudgetDepasse, conduire, resumer

DECLARATIONS = json.loads((Path(__file__).parents[1] / "ch05" / "declarations.json").read_text(encoding="utf-8"))


# --- Le système simulé et les outils --------------------------------------------------------

def test_le_systeme_retrouve_un_assure_par_son_numero_ou_son_contrat():
    s = Systeme()
    assert s.consulter_assure(numero_assure="ka-as-1002")["nom"] == "Mme Félicité Akplogan"
    assert s.consulter_assure(numero_contrat="KA-AUTO-0410")["numero"] == "KA-AS-1003"
    with pytest.raises(Introuvable):
        s.consulter_assure(numero_contrat="KA-AUTO-9999")
    with pytest.raises(Introuvable):
        s.consulter_assure()


def test_un_contrat_sans_sinistre_rend_une_liste_vide():
    s = Systeme()
    assert s.consulter_sinistres("KA-AUTO-0193") == []
    assert s.consulter_sinistres("KA-AUTO-1180")[0]["statut"] == "expertise planifiée"


def test_le_systeme_n_est_pas_modifie_par_ce_qu_on_lit():
    s = Systeme()
    s.consulter_contrat("KA-AUTO-0193")["statut"] = "résilié"
    assert s.consulter_contrat("KA-AUTO-0193")["statut"] == "actif"


def test_les_quatre_outils_sont_bien_definis():
    assert NOMS == ["consulter_assure", "consulter_contrat", "consulter_sinistres", "transmettre_a_un_gestionnaire"]
    for outil in OUTILS:
        schema = outil["input_schema"]
        assert schema["type"] == "object" and outil["description"]
        assert set(schema.get("required", [])) <= set(schema["properties"])


def test_executer_rend_le_resultat_ou_une_erreur_marquee():
    s = Systeme()
    texte, erreur = executer(s, "consulter_contrat", {"numero_contrat": "KA-HAB-0264"})
    assert not erreur and json.loads(texte)["garanties"]["vol"]["condition"] == "avec effraction constatée"
    assert executer(s, "consulter_contrat", {"numero_contrat": "KA-HAB-0000"})[1] is True
    assert executer(s, "consulter_contrat", {})[1] is True
    assert executer(s, "resilier_contrat", {"numero_contrat": "KA-HAB-0264"}) == ("Outil inconnu : resilier_contrat.", True)
    texte, erreur = executer(s, "transmettre_a_un_gestionnaire", {"motif": "Demande d'un humain", "resume": "Vol de moto"})
    assert not erreur and json.loads(texte)["numero"] == "TR-0001" and len(s.transmissions) == 1


# --- La boucle écrite à la main --------------------------------------------------------------

def texte(t):
    return SimpleNamespace(type="text", text=t)


def appel(nom, entree, identifiant):
    return SimpleNamespace(type="tool_use", name=nom, input=entree, id=identifiant)


def reponse(stop_reason, *blocs):
    usage = SimpleNamespace(input_tokens=900, output_tokens=200, cache_read_input_tokens=0,
                            cache_creation_input_tokens=0, cache_creation=None,
                            output_tokens_details=SimpleNamespace(thinking_tokens=80))
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocs), usage=usage, _request_id="req_faux")


class FauxClient:
    """Rejoue des réponses écrites d'avance et garde chaque requête pour qu'on la vérifie."""

    def __init__(self, *reponses, toujours=None):
        self.messages = self
        self.reponses, self.toujours = list(reponses), toujours
        self.requetes = []

    def count_tokens(self, model, system, tools, messages):
        return SimpleNamespace(input_tokens=1500)

    def create(self, **requete):
        self.requetes.append({**requete, "messages": list(requete["messages"])})
        return self.toujours or self.reponses.pop(0)


def test_une_reponse_avec_du_texte_et_un_outil_ne_finit_pas_la_boucle(tmp_path):
    client = FauxClient(
        reponse("tool_use", texte("Je consulte votre contrat."), appel("consulter_contrat", {"numero_contrat": "KA-AUTO-0193"}, "t1")),
        reponse("end_turn", texte("Votre contrat KA-AUTO-0193 est actif. Quand l'accident a-t-il eu lieu ?")),
    )
    c = conduire(client, "Mon pare-chocs est enfoncé, police KA-AUTO-0193.", journal=str(tmp_path / "j.jsonl"))
    assert c.fin == "end_turn" and len(c.tours) == 2
    assert c.reponse.startswith("Votre contrat") and c.tours[0].avec_texte
    deuxieme = client.requetes[1]["messages"]
    assert [m["role"] for m in deuxieme] == ["user", "assistant", "user"]
    resultat = deuxieme[2]["content"][0]
    assert resultat["type"] == "tool_result" and resultat["tool_use_id"] == "t1" and resultat["is_error"] is False


def test_plusieurs_outils_d_un_coup_rendent_un_seul_message_de_resultats(tmp_path):
    client = FauxClient(
        reponse("tool_use", appel("consulter_contrat", {"numero_contrat": "KA-AUTO-1180"}, "a"),
                appel("consulter_sinistres", {"numero_contrat": "KA-AUTO-1180"}, "b")),
        reponse("end_turn", texte("Votre dossier est en cours d'expertise.")),
    )
    conduire(client, "Où en est mon dossier ?", journal=str(tmp_path / "j.jsonl"))
    resultats = client.requetes[1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in resultats] == ["a", "b"]


def test_une_erreur_d_outil_revient_a_claude_marquee_comme_erreur(tmp_path):
    client = FauxClient(
        reponse("tool_use", appel("consulter_contrat", {"numero_contrat": "KA-AUTO-9999"}, "t1")),
        reponse("end_turn", texte("Je ne trouve pas ce contrat. Pouvez-vous vérifier le numéro ?")),
    )
    c = conduire(client, "Police KA-AUTO-9999.", journal=str(tmp_path / "j.jsonl"))
    assert client.requetes[1]["messages"][2]["content"][0]["is_error"] is True
    assert c.tours[0].erreurs_outils == 1 and c.fin == "end_turn"


def test_une_reponse_coupee_est_une_erreur_et_n_est_pas_envoyee(tmp_path):
    client = FauxClient(reponse("max_tokens", texte("Votre contrat couvre")))
    c = conduire(client, "Mon camion a brûlé.", journal=str(tmp_path / "j.jsonl"))
    assert c.fin == "erreur:max_tokens" and c.reponse == "" and len(client.requetes) == 1


def test_le_garde_fou_arrete_une_boucle_sans_fin(tmp_path):
    client = FauxClient(toujours=reponse("tool_use", appel("consulter_sinistres", {"numero_contrat": "KA-AUTO-1180"}, "t")))
    c = conduire(client, "Où en est mon dossier ?", garde_fou=4, journal=str(tmp_path / "j.jsonl"))
    assert c.fin == "erreur:garde_fou" and len(client.requetes) == 4


def test_le_plafond_arrete_avant_l_appel(tmp_path):
    client = FauxClient(reponse("end_turn", texte("Bonjour.")))
    with pytest.raises(BudgetDepasse):
        conduire(client, "Bonjour", budget_restant=0.0000001, journal=str(tmp_path / "j.jsonl"))
    assert client.requetes == []


def test_la_transmission_est_comptee(tmp_path):
    client = FauxClient(
        reponse("tool_use", appel("transmettre_a_un_gestionnaire", {"motif": "L'assuré demande un humain",
                                                                    "resume": "Vol de moto, dossier bloqué"}, "t1")),
        reponse("end_turn", texte("Un gestionnaire va vous rappeler.")),
    )
    systeme = Systeme()
    c = conduire(client, "Je veux parler à quelqu'un.", systeme=systeme, journal=str(tmp_path / "j.jsonl"))
    assert c.transmissions == 1 and systeme.transmissions[0]["motif"] == "L'assuré demande un humain"


def test_le_resume_compte_les_arrets_prematures_qu_aurait_causes_le_texte(tmp_path):
    avec_texte = FauxClient(
        reponse("tool_use", texte("Je regarde."), appel("consulter_contrat", {"numero_contrat": "KA-AUTO-0410"}, "t1")),
        reponse("end_turn", texte("Votre contrat couvre l'incendie, avec une franchise.")),
    )
    sans_texte = FauxClient(reponse("end_turn", texte("Ce n'est pas mon rôle.")))
    journal = str(tmp_path / "j.jsonl")
    conduites = [conduire(avec_texte, "x", cas="d5", journal=journal), conduire(sans_texte, "y", cas="h1", journal=journal)]
    r = resumer(conduites, DECLARATIONS["declarations"])
    assert r["arrets_premature_si_texte"] == 1 and r["garde_fou_atteint"] == 0
    assert r["outils_attendus_appeles"] == 2 and r["hors_sujet_sans_outil"] == 1


def test_les_dix_declarations_dont_trois_hors_sujet():
    d = DECLARATIONS["declarations"]
    assert len(d) == 10 and sum(not x["sujet"] for x in d) == 3
    assert all(set(x["outils_attendus"]) <= set(NOMS) for x in d)


# --- L'Agent SDK (ces tests sautent si le SDK n'est pas installé) --------------------------

def test_les_reglages_de_l_agent_sdk(tmp_path):
    pytest.importorskip("claude_agent_sdk")
    from ch05.agent_sdk import PREFIXE, options

    o = options(Systeme(), str(tmp_path), budget_max=0.05)
    assert o.tools == [] and o.permission_mode == "dontAsk" and o.setting_sources == []
    assert o.allowed_tools == [PREFIXE + nom for nom in NOMS]
    assert o.env["ENABLE_TOOL_SEARCH"] == "false" and o.env["CLAUDE_CONFIG_DIR"].startswith(str(tmp_path))
    assert o.env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1" and o.strict_mcp_config is True
    assert o.max_turns == 10 and o.max_budget_usd == 0.05 and o.resume is None and o.fork_session is False
    reprise = options(Systeme(), str(tmp_path), 0.05, resume="seance-1", bifurquer=True)
    assert reprise.resume == "seance-1" and reprise.fork_session is True


def test_les_outils_du_sdk_appellent_le_meme_systeme():
    pytest.importorskip("claude_agent_sdk")
    from ch05.agent_sdk import outils_sdk

    systeme = Systeme()
    outils = {o.name: o for o in outils_sdk(systeme)}
    assert list(outils) == NOMS
    assert outils["consulter_contrat"].input_schema == OUTILS[1]["input_schema"]
    rendu = asyncio.run(outils["consulter_contrat"].handler({"numero_contrat": "KA-AUTO-9999"}))
    assert rendu["is_error"] is True
    asyncio.run(outils["transmettre_a_un_gestionnaire"].handler({"motif": "m", "resume": "r"}))
    assert len(systeme.transmissions) == 1


def test_le_systeme_change_entre_deux_visites():
    pytest.importorskip("claude_agent_sdk")
    from ch05.bifurquer import changer_le_systeme

    systeme = Systeme()
    changer_le_systeme(systeme)
    assert systeme.consulter_sinistres("KA-AUTO-1180")[0]["statut"] == "rapport d'expertise reçu"


def test_le_reglage_sans_reflexion_part_dans_chaque_requete(tmp_path):
    from ch05.boucle import REGLAGES

    client = FauxClient(
        reponse("tool_use", appel("consulter_contrat", {"numero_contrat": "KA-AUTO-0193"}, "t1")),
        reponse("end_turn", texte("Votre contrat est actif.")),
    )
    conduire(client, "Police KA-AUTO-0193.", options=REGLAGES["sans-reflexion"], journal=str(tmp_path / "j.jsonl"))
    assert all(r["thinking"] == {"type": "disabled"} for r in client.requetes) and len(client.requetes) == 2


def test_une_panne_de_l_api_rendue_en_success_est_une_erreur(tmp_path, monkeypatch):
    pytest.importorskip("claude_agent_sdk")
    from claude_agent_sdk import ResultMessage

    import ch05.agent_sdk as module

    async def fausse_query(prompt, options):
        yield ResultMessage(subtype="success", duration_ms=1000, duration_api_ms=0, is_error=True, num_turns=1,
                            session_id="s1", stop_reason="stop_sequence", total_cost_usd=0.0,
                            usage={"input_tokens": 0, "output_tokens": 0},
                            result="API Error: Can't reach the API server")
        raise RuntimeError("Claude Code returned an error result")

    monkeypatch.setattr(module, "query", fausse_query)
    # config.JOURNAL est lu à l'import : changer KANVO_JOURNAL ici arriverait trop tard, et la ligne de cette
    # fausse séance entrerait dans journal/appels.jsonl.
    monkeypatch.setattr("assureur.config.JOURNAL", str(tmp_path / "j.jsonl"))
    s = asyncio.run(module.seance("Bonjour", systeme=Systeme(), dossier=str(tmp_path), budget_max=0.01))
    assert s.fin == "erreur:success" and s.reponse == "" and "API Error" in s.erreur


def test_les_trois_facons_de_repondre_apres_un_changement():
    pytest.importorskip("claude_agent_sdk")
    from ch05.bifurquer import RESUME, SIGNALEMENT, variantes

    v = variantes("Où en est mon dossier ?", "tronc-1")
    assert [reprise for _, _, reprise in v] == ["tronc-1", "tronc-1", None]
    assert v[1][1].startswith(SIGNALEMENT) and v[2][1].startswith(RESUME)
