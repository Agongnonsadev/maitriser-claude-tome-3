"""Chapitre 6 : les deux catalogues, les erreurs structurées, la mesure du choix. Aucun appel à l'API."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from assureur import outils_v2
from assureur.systeme import Indisponible, Interdit, RegleMetier, Systeme
from ch06 import catalogue_dsi
from ch06.catalogues import CONSIGNE_CONTRAT, INTROUVABLE, VARIANTES, premier_juste
from ch06.choix import evaluer, lancer, resumer
from ch06.erreurs import classer, nouvelles_tentatives

ICI = Path(__file__).parents[1] / "ch06"
DEMANDES = json.loads((ICI / "demandes.json").read_text(encoding="utf-8"))["demandes"]
SITUATIONS = {s["id"]: s for s in json.loads((ICI / "erreurs.json").read_text(encoding="utf-8"))["situations"]}


# --- Le système : ses refus ont une cause ---------------------------------------------------

def test_le_systeme_refuse_pour_une_raison_precise():
    s = Systeme(pannes={"consulter_sinistre": 1})
    with pytest.raises(Indisponible):
        s.consulter_sinistre("SIN-2026-0912")
    assert s.consulter_sinistre("SIN-2026-0912")["statut"] == "expertise planifiée"  # la panne est passée
    with pytest.raises(Interdit):
        s.consulter_contrat("KA-SANTE-0318")
    with pytest.raises(RegleMetier):
        s.consulter_sinistre("SIN-2019-0207")


def test_la_recherche_par_nom_ignore_accents_et_majuscules():
    assert [a["numero"] for a in Systeme().rechercher_assures("houngbedji")] == ["KA-AS-1005"]
    assert Systeme().rechercher_assures("Inconnu") == []


def test_la_resiliation_est_notee():
    s = Systeme()
    s.resilier_contrat("KA-HAB-0264", "déménagement")
    assert s.resiliations[0]["contrat"] == "KA-HAB-0264" and s.contrats["KA-HAB-0264"]["statut"] == "résilié"


# --- Le catalogue de la DSI : ses défauts, mesurés par le chapitre ----------------------------

def test_le_dossier_d_un_client_n_est_pas_un_dossier_de_sinistre_pour_la_dsi():
    texte, erreur = catalogue_dsi.executer(Systeme(), "rechercher_dossier", {"requete": "KA-AS-1006"})
    assert (texte, erreur) == ("[]", False)  # alors que l'assuré a un sinistre ouvert


def test_la_dsi_deguise_une_panne_en_liste_vide():
    s = Systeme(pannes={"consulter_sinistre": 1})
    assert catalogue_dsi.executer(s, "rechercher_dossier", {"requete": "SIN-2026-0912"}) == ("[]", False)
    assert catalogue_dsi.executer(Systeme(), "consulter_contrat", {"numero": "KA-SANTE-0318"}) == ("Erreur.", True)


def test_la_dsi_expose_la_resiliation():
    s = Systeme()
    texte, erreur = catalogue_dsi.executer(s, "resilier_contrat", {"numero": "KA-AUTO-0193", "motif": "x"})
    assert not erreur and len(s.resiliations) == 1


# --- Le catalogue de Yao ------------------------------------------------------------------

def test_le_catalogue_de_yao_est_strict_et_sans_resiliation():
    assert "resilier_contrat" not in outils_v2.NOMS and len(outils_v2.NOMS) == 5
    for outil in outils_v2.OUTILS:
        assert outil["strict"] is True and outil["input_schema"]["additionalProperties"] is False
        assert len(outil["description"].split(". ")) >= 3  # au moins trois phrases
    motif = next(o for o in outils_v2.OUTILS if o["name"] == "transmettre_a_un_gestionnaire")
    assert motif["input_schema"]["properties"]["motif"]["enum"] == outils_v2.MOTIFS


def _erreur(resultat):
    texte, est_erreur = resultat
    assert est_erreur
    return json.loads(texte)["erreur"]


@pytest.mark.parametrize("systeme, nom, arguments, categorie, reessayable", [
    (Systeme(pannes={"consulter_sinistre": 1}), "consulter_sinistre", {"numero_sinistre": "SIN-2026-0912"},
     "passagere", True),
    (Systeme(), "consulter_contrat", {"numero_contrat": "KA-SANTE-0318"}, "permission", False),
    (Systeme(), "consulter_sinistre", {"numero_sinistre": "SIN-2019-0207"}, "metier", False),
    (Systeme(), "consulter_sinistre", {"numero_sinistre": "SIN-26-912"}, "validation", False),
    (Systeme(), "consulter_sinistre", {"numero_sinistre": "SIN-2026-9999"}, "validation", False),
    (Systeme(), "trouver_assure", {"numero_assure": "KA-AS-1002", "nom": "Akplogan"}, "validation", False),
])
def test_chaque_erreur_a_sa_categorie(systeme, nom, arguments, categorie, reessayable):
    e = _erreur(outils_v2.executer(systeme, nom, arguments))
    assert e["categorie"] == categorie and e["reessayable"] is reessayable and e["conseil"]


def test_un_numero_mal_forme_n_atteint_pas_le_systeme():
    s = Systeme(pannes={"consulter_sinistre": 1})
    outils_v2.executer(s, "consulter_sinistre", {"numero_sinistre": "SIN-26-912"})
    assert s.pannes["consulter_sinistre"] == 1  # le système n'a pas été appelé


def test_une_liste_vide_est_un_resultat_et_le_dit():
    texte, erreur = outils_v2.executer(Systeme(), "lister_sinistres_du_contrat", {"numero_contrat": "KA-AUTO-0410"})
    assert not erreur and json.loads(texte) == {"sinistres": [], "note": "Aucun sinistre n'est enregistré sur ce contrat."}


def test_trouver_assure_par_nom_ou_par_numero():
    par_nom = json.loads(outils_v2.executer(Systeme(), "trouver_assure", {"nom": "Zinsou"})[0])
    assert par_nom["assures"][0]["contrats"] == ["KA-AUTO-0731"]
    par_contrat = json.loads(outils_v2.executer(Systeme(), "trouver_assure", {"numero_contrat": "KA-AUTO-1180"})[0])
    assert par_contrat["assures"][0]["numero"] == "KA-AS-1002"


# --- Les variantes et la mesure -------------------------------------------------------------

def test_une_seule_chose_change_d_une_variante_a_l_autre():
    yao, consigne, motif = VARIANTES["yao"], VARIANTES["yao-consigne-contrat"], VARIANTES["yao-motif-strict"]
    assert consigne.outils == yao.outils and consigne.prompt.endswith(CONSIGNE_CONTRAT + "\n")
    assert motif.prompt == yao.prompt and motif.outils != yao.outils
    schema = next(o for o in motif.outils if o["name"] == "consulter_sinistre")["input_schema"]
    assert schema["properties"]["numero_sinistre"]["pattern"] == r"^SIN-\d{4}-\d{4}$"
    assert "pattern" not in next(o for o in yao.outils if o["name"] == "consulter_sinistre")["input_schema"][
        "properties"]["numero_sinistre"]  # la variante n'a pas touché au catalogue de Yao


def test_le_premier_choix():
    assert premier_juste(["rechercher_client"], ["rechercher_client"])
    assert not premier_juste(["rechercher_dossier"], ["rechercher_client"])
    assert premier_juste([], ["creer_ticket", "aucun"]) and not premier_juste([], ["trouver_assure"])
    assert premier_juste(["consulter_contrat", "lister_sinistres_du_contrat"], ["lister_sinistres_du_contrat"])


@pytest.mark.parametrize("phrase", ["Je n'ai trouvé aucun dossier à votre nom.", "Il n'y a aucun sinistre enregistré.",
                                    "Je ne trouve pas de dossier SIN-26-912."])
def test_la_fausse_conclusion_se_repere(phrase):
    assert INTROUVABLE.search(phrase)


def test_evaluer_une_conduite():
    d = next(x for x in DEMANDES if x["id"] == "c06")  # un sinistre existe
    e = evaluer(VARIANTES["dsi"], d, ["rechercher_dossier"], ["rechercher_dossier"], "Vous n'avez aucun dossier ouvert.",
                Systeme())
    assert not e["premier_juste"] and e["fausse_conclusion"]
    r = next(x for x in DEMANDES if x["id"] == "c10")
    assert evaluer(VARIANTES["dsi"], r, ["resilier_contrat"], ["resilier_contrat"], "C'est fait.", Systeme())[
        "interdit_appele"]


def test_les_vingt_demandes_sont_bien_formees():
    assert len(DEMANDES) == 20 and len({d["id"] for d in DEMANDES}) == 20
    for d in DEMANDES:
        assert set(d["attendus"]["dsi"]) <= set(catalogue_dsi.NOMS) | {"aucun"}
        assert set(d["attendus"]["yao"]) <= set(outils_v2.NOMS) | {"aucun"}


class FauxClient:
    def __init__(self):
        self.messages = self
        self.requetes = []

    def count_tokens(self, **_):
        return SimpleNamespace(input_tokens=1500)

    def create(self, **requete):
        self.requetes.append(requete)
        usage = SimpleNamespace(input_tokens=1500, output_tokens=100, cache_read_input_tokens=0,
                                cache_creation_input_tokens=0, cache_creation=None,
                                output_tokens_details=SimpleNamespace(thinking_tokens=0))
        if len(self.requetes) % 2:  # un appel d'outil, puis une réponse
            bloc = SimpleNamespace(type="tool_use", name=requete["tools"][0]["name"], id="t1",
                                   input={"requete": "KA-AS-1002"} if requete["tools"][0]["name"] == "rechercher_client"
                                   else {"numero_assure": "KA-AS-1002"})
            return SimpleNamespace(stop_reason="tool_use", content=[bloc], usage=usage, _request_id="r")
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Voici.")],
                               usage=usage, _request_id="r")


def test_la_mesure_passe_chaque_catalogue_a_la_boucle(tmp_path):
    client = FauxClient()
    essais, depense = lancer(client, DEMANDES[:1], ["dsi", "yao"], 1, 1.0, journal=str(tmp_path / "j.jsonl"))
    assert [r["tools"][0]["name"] for r in client.requetes[::2]] == ["rechercher_client", "trouver_assure"]
    assert all(e["premier_juste"] for e in essais) and depense > 0
    assert [l["premier_choix_juste"] for l in resumer(essais)] == [1, 1]


def test_classer_une_reponse_d_erreur():
    panne = SITUATIONS["e1-panne"]
    assert classer("Je n'ai trouvé aucun dossier SIN-2026-0912.", panne) == "faux"
    assert classer("Le système est momentanément indisponible.", panne) == "bon"
    assert classer("Bonjour.", panne) == "à relire"
    assert classer("Votre dossier concerne la collision du carrefour Saint-Michel.", SITUATIONS["e4-validation"]) == "faux"
    assert nouvelles_tentatives(["consulter_sinistre", "consulter_sinistre", "transmettre_a_un_gestionnaire"]) == 1


def test_la_recherche_par_nom_ote_les_civilites():
    s = Systeme()
    assert [a["numero"] for a in s.rechercher_assures("M. Zinsou")] == ["KA-AS-1006"]
    assert [a["numero"] for a in s.rechercher_assures("Mme Félicité Akplogan")] == ["KA-AS-1002"]
    assert s.rechercher_assures("M.") == []
