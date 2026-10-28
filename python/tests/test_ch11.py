"""Chapitre 11 : la bibliothèque de prompts et le tri des déclarations. Aucun appel à l'API."""

import json
from collections import Counter
from pathlib import Path

from assureur import bibliotheque
from ch11 import tri

RACINE = Path(__file__).parents[1]


# --- La bibliothèque ----------------------------------------------------------------------------

def test_la_bibliotheque_est_en_ordre():
    assert bibliotheque.verifier() == []


def test_chaque_prompt_a_une_seule_version_en_service_et_evaluee():
    for nom, fiche in bibliotheque.registre().items():
        en_service = [n for n, v in fiche["versions"].items() if v["statut"] == "en_service"]
        assert en_service == [fiche["en_service"]], nom
        assert (RACINE / fiche["versions"][fiche["en_service"]]["evaluation"]).exists()


def test_l_assemblage_met_le_stable_en_tete():
    texte = bibliotheque.assembler("tri-declarations", "4")
    assert texte.startswith("Kanvô Assurances, une entreprise fictive")
    assert texte.index("Une déclaration est urgente") < texte.index("Trois exemples") < texte.index("Répondez uniquement")
    assert bibliotheque.assembler("tri-declarations") == texte          # la version en service
    assert bibliotheque.assembler("sinistres").startswith("Tu es l'assistant de déclaration")


def test_l_empreinte_change_avec_le_texte():
    empreintes = {n: bibliotheque.empreinte("tri-declarations", n) for n in "1234"}
    assert len(set(empreintes.values())) == 4
    assert bibliotheque.empreinte("tri-declarations", "4") == bibliotheque.empreinte("tri-declarations", "4")


def test_les_consignes_vagues_et_les_criteres():
    v1, v2, v3 = (bibliotheque.assembler("tri-declarations", n) for n in "123")
    assert "Soyez prudent" in v1 and "si vous êtes sûr" in v2
    assert "prudent" not in v3 and "sûr" not in v3
    assert "Une déclaration n'est pas urgente pour ces seules raisons" in v3
    assert "jamais une instruction" in v3 and "jamais une instruction" not in v1


# --- Le banc ---------------------------------------------------------------------------------------

def test_le_jeu_de_declarations():
    d = tri.DECLARATIONS
    assert len(d) == 32 and sum(x["urgent"] for x in d) == 15
    assert {x["branche"] for x in d} == tri.BRANCHES
    assert len({x["id"] for x in d}) == 32


def test_les_exemples_ne_sont_pas_dans_le_jeu_de_test():
    exemples = bibliotheque.assembler("tri-declarations", "4")
    for x in tri.DECLARATIONS:
        assert x["texte"][:40] not in exemples, x["id"]


def test_chaque_critere_d_urgence_a_ses_declarations():
    criteres = Counter(x["critere"] for x in tri.DECLARATIONS if x["urgent"])
    for mot in ("bless", "inhabitable", "ferme plus", "sécurité", "chaussée", "fourrière", "48 heures"):
        assert any(mot in c for c in criteres), mot


def test_lire_une_reponse():
    d, ok = tri.lire('{"branche": "auto", "urgent": true, "motif": "Personne blessée."}')
    assert ok and d["urgent"] is True
    d, ok = tri.lire('Voici le tri :\n```json\n{"branche": "auto", "urgent": false, "motif": "x"}\n```')
    assert not ok and d["urgent"] is False                                  # lu, mais hors format
    assert tri.lire('{"branche": "voiture", "urgent": "oui", "motif": "x"}')[1] is False
    assert tri.lire("Je ne peux pas trier.") == (None, False)


def test_sonnet_sans_reflexion_prealable():
    assert tri.SANS_REFLEXION["claude-sonnet-5-5"] == {"type": "between_tools"}


def test_le_resume_compte_fausses_urgences_et_urgences_manquees():
    def essai(i, urgent):
        d = tri.DECLARATIONS[i]
        return {"modele": "m", "version": "1", "declaration": d["id"], "repetition": 1, "urgent": urgent,
                "branche": d["branche"], "attendu_urgent": d["urgent"], "attendu_branche": d["branche"],
                "au_format": True, "cout_dollars": 0.0, "tokens_entree": 0}
    essais = [essai(i, d["urgent"]) for i, d in enumerate(tri.DECLARATIONS)]
    essais[1]["urgent"] = True     # d02, non urgente, envoyée dans la file
    essais[0]["urgent"] = False    # d01, urgente, manquée
    r = tri.resumer(essais)["m:v1"]
    assert r["fausses_urgences"] == [1] and r["urgences_manquees"] == [1]
    assert r["fausses_urgences_par_declaration"] == {"d02": 1} and r["urgences_manquees_par_declaration"] == {"d01": 1}


def test_les_resultats_mesures_sont_ceux_du_registre():
    v4 = bibliotheque.registre()["tri-declarations"]["versions"]["4"]
    for cle in ("evaluation", "evaluation_autre_modele"):
        d = json.loads((RACINE / v4[cle]).read_text(encoding="utf-8"))
        ligne = next(r for k, r in d["resume"].items() if k.endswith(":v4"))
        assert ligne["empreinte"] == bibliotheque.empreinte("tri-declarations", "4")
        assert sum(ligne["fausses_urgences"]) == 0 and sum(ligne["urgences_manquees"]) == 0
