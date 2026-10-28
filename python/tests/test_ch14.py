"""Chapitre 14 : la base documentaire, ses découpages, ses filtres, le manifeste et la notation des réponses.
Aucun appel à l'API."""

import json
import re
from datetime import date

from ch14 import edition_2027
from ch14.assistant import anonyme, noter_reponse
from ch14.corpus import DOSSIER, charger, decouper, decouper_naif, decouper_structure, ecarts, manifeste, unites
from ch14.mesurer_recherche import BASE_OCTOBRE, questions
from ch14.panne import BASES, diagnostic
from ch14.recherche import IndexBM25, chercher, filtre


def _doc(nom):
    return next(d for d in charger() if d.nom == nom)


def test_l_edition_2027_se_refabrique_a_l_identique():
    for nom, texte in edition_2027.fabriquer().items():
        assert (DOSSIER / nom).read_text(encoding="utf-8") == texte
    assert "plafonnée à 40 %" in _doc("cg-auto-2027").texte and "plafonnée à 50 %" in _doc("cg-auto-2026").texte


def test_les_documents_et_leurs_periodes():
    docs = {d.nom: d for d in charger()}
    assert len(docs) == 8
    assert (docs["cg-auto-2026"].debut, docs["cg-auto-2026"].fin) == (date(2026, 1, 1), date(2026, 12, 31))
    assert (docs["cg-auto-2027"].debut, docs["cg-auto-2027"].fin) == (date(2027, 1, 1), None)
    assert docs["procedures-sinistres"].debut is None and docs["procedures-sinistres"].produit == "sinistres"
    assert docs["tableau-habitation-2026"].produit == "habitation" and docs["tableau-habitation-2026"].genre == "tableau"


def test_le_decoupage_structure_suit_la_forme_des_documents():
    docs = charger(BASE_OCTOBRE)
    morceaux = decouper(docs, "structure")
    assert len(morceaux) == 69 and all(len(m.unites) == 1 for m in morceaux)
    ligne = next(m for m in morceaux if m.identifiant == "TG-AUTO-2026:vol")
    assert "formule Tiers étendu : comprise, franchise 75 000" in ligne.texte
    article = next(m for m in morceaux if m.identifiant == "CG-AUTO-2026:art-17")
    assert article.titre.startswith("CG-AUTO-2026, Article 17 — Déclaration du sinistre (Chapitre IV")
    assert "sinistres survenus du 1er janvier 2026 au 31 décembre 2026" in article.pour_le_modele()


def test_les_fenetres_perdent_l_en_tete_des_tableaux():
    tableau = _doc("tableau-auto-2026")
    couvertes = {u for m in decouper_naif(tableau) for u in m.unites}
    perdues = [u.identifiant.split(":")[1] for u in unites(tableau) if u.identifiant not in couvertes]
    assert perdues == ["vol", "incendie", "bris-de-glace", "assistance", "garantie-du-conducteur"]
    assert len(decouper(charger(BASE_OCTOBRE), "naif")) == 28


def test_le_manifeste_dit_ce_qui_manque_a_l_index():
    assert diagnostic() == {"absents_de_l_index": ["cg-auto-2027", "tableau-auto-2027"], "modifies": [],
                            "retires_de_la_source": []}
    index = manifeste(charger(["cg-auto-2026"]))
    source = {**index, "cg-auto-2026": "autre"}
    assert ecarts(index, source)["modifies"] == ["cg-auto-2026"]
    assert set(BASES["deux_editions"]) == set(BASE_OCTOBRE) | {"cg-auto-2027", "tableau-auto-2027"}


def test_les_filtres_de_produit_et_de_periode():
    morceaux = {m.identifiant: m for m in decouper(charger())}
    garder = filtre("habitation", None)
    assert garder(morceaux["TG-HAB-2026:vol"]) and garder(morceaux["PROC-SIN:proc-7"])
    assert not garder(morceaux["TG-AUTO-2026:vol"])
    janvier = filtre("auto", date(2027, 1, 12))
    assert janvier(morceaux["TG-AUTO-2027:bris-de-glace"]) and not janvier(morceaux["TG-AUTO-2026:bris-de-glace"])
    assert filtre("auto", date(2026, 11, 3))(morceaux["TG-AUTO-2026:bris-de-glace"])


def test_la_date_ne_sert_pas_de_mot_a_chercher():
    index = IndexBM25(decouper(charger(BASES["deux_editions"])))
    r = chercher(None, index, "Vol survenu le 10 décembre 2026 : de combien de jours l'assuré disposait-il pour le déclarer ?",
                 "filtre", 5, "auto", date(2026, 12, 10))
    assert "CG-AUTO-2026:art-17" in [m.identifiant for m in r["morceaux"]] and r["dollars"] == 0


def test_le_jeu_de_questions():
    toutes = {u.identifiant for d in charger() for u in unites(d)}
    for jeu in ("questions", "etat", "editions"):
        for q in questions(jeu):
            assert set(q["attendus"]) <= toutes, q["id"]
            assert bool(q["attendus"]) == q["trouve"]
            for f in q["faits"]:
                re.compile(f)
    assert len(questions()) == 40 and len(questions("etat")) == 4 and len(questions("editions")) == 8
    exclusion = next(q for q in questions("editions") if q["id"] == "v8")["faits"][0]
    assert not re.search(exclusion, "Le vol peut être garanti : les passages ne prévoient pas d'exclusion.", re.I)
    assert re.search(exclusion, "Non : l'article 14 exclut ce vol.", re.I)


def test_la_notation_des_reponses():
    morceaux = {m.identifiant: m for m in decouper(charger())}
    q = next(x for x in questions() if x["id"] == "q21")
    passages = [morceaux["TG-AUTO-2026:vol"], morceaux["CG-AUTO-2026:art-8"]]
    juste = {"trouve": True, "reponse": "Franchise de 75 000 FCFA.", "sources": ["TG-AUTO-2026:vol"]}
    assert noter_reponse(q, juste, passages)["issue"] == "juste"
    assert noter_reponse(q, {**juste, "sources": ["CG-AUTO-2026:art-8"]}, passages)["issue"] == "source_absente"
    assert noter_reponse(q, {**juste, "reponse": "Franchise de 100 000 FCFA."}, passages)["issue"] == "fait_manquant"
    assert noter_reponse(q, {**juste, "trouve": False}, passages)["issue"] == "manquee"
    absent = next(x for x in questions() if x["id"] == "q39")
    assert noter_reponse(absent, {"trouve": True, "reponse": "Le 21 00 00 00.", "sources": []}, [])["issue"] == "inventee"
    etat = next(x for x in questions("etat") if x["id"] == "e1")
    assert noter_reponse(etat, {"trouve": True, "reponse": "Passage de l'expert le 29 octobre.",
                                "sources": ["logiciel de gestion"]}, [])["issue"] == "juste"


def test_un_passage_anonyme_n_a_ni_reference_ni_periode():
    m = next(x for x in decouper_structure(_doc("cg-auto-2026")) if x.identifiant == "CG-AUTO-2026:art-21")
    texte = anonyme(3, m)
    assert texte.startswith('<passage id="p3">\nArticle 21') and "2026" not in texte
    assert json.dumps(texte)
