"""Chapitre 18 : les notes fabriquées des Cliniques Ébène et le contrôle des comptes rendus. Aucun appel à l'API."""

from ch18.compte_rendu import OUTIL, PROMPTS, Redaction, controler, message, normaliser, resumer
from cliniques.notes import AJOUTS, NOTES, NOTES_18, RESERVES, note, soins_mentionnes


def _cr(conclusion, examen="Constatations.", suite=None, absents=()):
    return {"motif": "Motif.", "examen": examen, "conclusion_du_medecin": conclusion, "suite": suite,
            "elements_absents": list(absents)}


def test_les_notes_et_leur_verite():
    assert [n["id"] for n in NOTES] == [f"N{i:02d}" for i in range(1, 21)]
    assert [n["id"] for n in NOTES_18] == [f"N{i:02d}" for i in range(1, 11)]  # le chapitre 18 garde ses dix notes
    assert [n["id"] for n in NOTES_18 if n["conclusion"] is None] == ["N04", "N07", "N09"]
    assert [n["id"] for n in NOTES_18 if n["reserves"]] == ["N01", "N03", "N06"]
    assert [n["id"] for n in NOTES if n.get("dictee")] == ["N13", "N18"]
    for n in NOTES:
        texte = normaliser(n["texte"])
        assert all(r in texte for r in n["reserves"]), n["id"]
        assert all(e in texte for e in n["examens"]), n["id"]
        if n["conclusion"]:
            assert normaliser(n["conclusion"]) in texte, n["id"]


def test_les_notes_ne_prescrivent_rien():
    # Aucune note ne contient de traitement ni de posologie : seule N06 demande un examen, la radiographie.
    for n in NOTES:
        texte = normaliser(n["texte"])
        assert soins_mentionnes(texte) == (["radiographie"] if n["id"] in ("N06", "N20") else []), n["id"]
        assert " mg" not in texte and "comprime" not in texte
    assert len(AJOUTS) == 22 and soins_mentionnes("a confirmer") == []  # « irm » ne trouve pas « confirmer »


def test_un_compte_rendu_fidele_passe():
    c = controler(note("N01"), _cr("Probable entorse bénigne de la cheville droite, à confirmer si la douleur "
                                   "persiste plus de 8 jours.", suite="Revoir à la demande."))
    assert c == {"rendu": True, "conclusion_inventee": False, "conclusion_omise": False, "reserve_perdue": False,
                 "ajouts": [], "elements_absents": 0}


def test_la_reserve_perdue_se_voit():
    assert controler(note("N01"), _cr("Entorse bénigne de la cheville droite."))["reserve_perdue"] is True
    assert controler(note("N06"), _cr("Fracture du scaphoïde droit."))["reserve_perdue"] is True
    assert controler(note("N06"), _cr("Suspicion de fracture du scaphoïde."))["reserve_perdue"] is False


def test_la_conclusion_inventee_se_voit():
    assert controler(note("N04"), _cr("Otite externe probable."))["conclusion_inventee"] is True
    assert controler(note("N04"), _cr(None))["conclusion_inventee"] is False
    assert controler(note("N09"), _cr("Conclusion réservée, à discuter à la prochaine consultation."))[
        "conclusion_inventee"] is False
    assert controler(note("N02"), _cr(None))["conclusion_omise"] is True


def test_les_ajouts_se_voient():
    c = controler(note("N01"), _cr("Probable entorse.", suite="Repos, glace et radiographie si persistance."))
    assert c["ajouts"] == ["glace", "radiographie", "repos"]
    # La radiographie est dans la note N06 : la citer n'est pas un ajout.
    assert controler(note("N06"), _cr("Suspicion de fracture, radiographie demandée."))["ajouts"] == []


def test_les_deux_prompts():
    assert PROMPTS["mission2"].startswith(PROMPTS["reprise"])
    assert "réserves" in PROMPTS["mission2"] and "réserves" not in PROMPTS["reprise"]
    assert "Ne le déduisez pas" in PROMPTS["reprise"]  # la règle de la mission 1, reprise
    assert OUTIL["strict"] and "conclusion_du_medecin" in OUTIL["input_schema"]["required"]
    assert "EB-2026-0412" in message(note("N01"))


def test_le_resume():
    rs = [Redaction("claude-haiku-5-5", "reprise", "N04", 1, controles=controler(note("N04"), _cr("Otite."))),
          Redaction("claude-haiku-5-5", "reprise", "N01", 1, controles=controler(note("N01"), _cr("Entorse."))),
          Redaction("claude-haiku-5-5", "reprise", "N02", 1, controles=controler(note("N02"), _cr("Rhinopharyngite.")))]
    r = resumer(rs)["claude-haiku-5-5:reprise"]
    assert r["conclusions_inventees"] == "1 sur 1" and r["reserves_perdues"] == "1 sur 1"
    assert r["conclusions_omises"] == "0 sur 2" and r["rendus"] == 3
    assert RESERVES[0] == "probable"
