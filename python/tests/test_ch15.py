"""Chapitre 15 : l'ancien logiciel des contrats, la configuration d'équipe et la lecture des séances.
Aucun appel à l'API : les séances de Claude Code ne sont pas lancées ici."""

import json
import re
import shutil
import subprocess
import sys

import pytest

from ch15.seances import (ANCIEN, ATTENDU, CONFIGURATIONS, NOTER, VARIANTES, Seance, arrondi, calculer, conforme,
                          lignes_ajoutees, lire_instruction, preparer, resumer)


def _en_tete(texte: str) -> str:
    m = re.match(r"---\n(.*?)\n---\n", texte, re.S)
    assert m, "en-tête YAML attendu"
    return m.group(1)


# --- L'ancien logiciel ------------------------------------------------------------------------------

def test_l_ancien_logiciel_calcule_les_primes_d_origine(tmp_path):
    depot = tmp_path / "depot"
    shutil.copytree(ANCIEN, depot)
    calculs = calculer(depot)
    # Sans le paramètre annees_permis, les cas « jeune » échouent ; les autres donnent le code d'origine.
    assert calculs["inconnu"] == 45050 and calculs["existant_taxi"] == ATTENDU["existant_taxi"]
    assert str(calculs["jeune_demi"]).startswith("erreur : TypeError")


def test_l_ancien_logiciel_tourne_sur_une_base_neuve(tmp_path):
    depot = tmp_path / "depot"
    shutil.copytree(ANCIEN, depot)
    sortie = subprocess.run([sys.executable, "lancer.py", "creer-base"], cwd=depot, capture_output=True, text=True)
    assert sortie.returncode == 0 and (depot / "donnees" / "contrats.db").exists()


# --- La configuration d'équipe ------------------------------------------------------------------------

def test_les_claude_md_restent_courts_et_importent_le_lisezmoi():
    for nom in ("projet-v1", "projet-v2"):
        texte = (CONFIGURATIONS / nom / "CLAUDE.md").read_text(encoding="utf-8")
        assert len(texte.splitlines()) < 200 and "@LISEZMOI.txt" in texte


def test_chaque_regle_ne_se_charge_que_pour_ses_dossiers():
    regles = sorted((CONFIGURATIONS / "projet-v2" / ".claude" / "rules").glob("*.md"))
    assert [r.stem for r in regles] == ["base", "montants", "tarifs"]
    for r in regles:
        assert "paths:" in _en_tete(r.read_text(encoding="utf-8"))


def test_la_regle_des_montants_a_quitte_le_claude_md_d_equipe():
    claude = (CONFIGURATIONS / "projet-v2" / "CLAUDE.md").read_text(encoding="utf-8")
    montants = (CONFIGURATIONS / "projet-v2" / ".claude" / "rules" / "montants.md").read_text(encoding="utf-8")
    assert "arrondir_fcfa" not in claude and "arrondir_fcfa" in montants


def test_la_skill_tourne_a_part_et_ne_modifie_rien():
    texte = (CONFIGURATIONS / "projet-v2" / ".claude" / "skills" / "verifier-arrondis" / "SKILL.md").read_text(
        encoding="utf-8")
    en_tete = _en_tete(texte)
    assert "context: fork" in en_tete and "argument-hint:" in en_tete
    assert re.search(r"allowed-tools: Read Grep Glob\n", en_tete)  # ni Edit, ni Write, ni Bash


def test_les_permissions_d_equipe_portent_sur_edit_et_non_sur_write():
    # Une règle Write(chemin) est acceptée par Claude Code mais ne s'applique jamais : c'est Edit(chemin).
    reglages = json.loads((CONFIGURATIONS / "projet-v2" / ".claude" / "settings.json").read_text(encoding="utf-8"))
    refus = reglages["permissions"]["deny"]
    assert "Edit(tarifs/**)" in refus and not any(r.startswith("Write(") for r in refus)


# --- Les séances : préparation et lecture --------------------------------------------------------------

@pytest.mark.parametrize("variante", list(VARIANTES))
def test_chaque_variante_prepare_son_depot_et_son_dossier_personnel(tmp_path, variante):
    depot, personnel = preparer(variante, tmp_path, tmp_path / "instructions.jsonl")
    v = VARIANTES[variante]
    assert (personnel / "CLAUDE.md").exists() == (v["utilisateur"] is not None)
    assert (depot / "CLAUDE.md").exists() == (v["projet"] is not None)
    assert (depot / ".claude" / "rules" / "montants.md").exists() == (variante == "regles")
    # Le hook de mesure vit dans le réglage local, jamais dans le settings.json partagé.
    local = json.loads((depot / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    assert NOTER.name in local["hooks"]["InstructionsLoaded"][0]["hooks"][0]["command"]


def test_le_hook_note_le_fichier_sa_portee_et_la_raison(tmp_path):
    journal = tmp_path / "j.jsonl"
    entree = {"session_id": "s", "hook_event_name": "InstructionsLoaded", "file_path": "/x/CLAUDE.md",
              "memory_type": "Project", "load_reason": "session_start", "transcript_path": "/t"}
    subprocess.run([sys.executable, str(NOTER), str(journal)], input=json.dumps(entree), text=True, check=True)
    assert json.loads(journal.read_text(encoding="utf-8")) == {"file_path": "/x/CLAUDE.md", "memory_type": "Project",
                                                               "load_reason": "session_start"}


def test_les_chemins_du_journal_deviennent_lisibles(tmp_path):
    depot, personnel = tmp_path / "depot", tmp_path / "personnel"
    depot.mkdir(), personnel.mkdir()
    ligne = json.dumps({"file_path": str(depot / ".claude" / "rules" / "montants.md"), "memory_type": "Project",
                        "load_reason": "path_glob_match", "trigger_file_path": str(depot / "primes" / "calcul.py")})
    assert lire_instruction(ligne, depot, personnel) == {"fichier": ".claude/rules/montants.md", "portee": "Project",
                                                         "raison": "path_glob_match", "declencheur": "primes/calcul.py"}
    ligne = json.dumps({"file_path": str(personnel / "CLAUDE.md"), "memory_type": "User", "load_reason": "session_start"})
    assert lire_instruction(ligne, depot, personnel)["fichier"] == "~/.claude/CLAUDE.md"


MAJORATION = """
    if annees_permis is not None and annees_permis < t['DUREE_JEUNE_CONDUCTEUR']:
        p = p * (1 + t['MAJ_JEUNE_CONDUCTEUR'])
"""


def _depot_modifie(tmp_path, arrondi_final: str):
    depot = tmp_path / "depot"
    shutil.copytree(ANCIEN, depot)
    calcul = depot / "primes" / "calcul.py"
    texte = calcul.read_text(encoding="utf-8")
    texte = texte.replace("def prime_auto(puissance, usage='prive', options=[], coef_bm=1.0):",
                          "def prime_auto(puissance, usage='prive', options=[], coef_bm=1.0, annees_permis=None):")
    texte = texte.replace("    p = p * coef_bm\n    return int(p)\n",
                          "    p = p * coef_bm\n" + MAJORATION + f"    return {arrondi_final}\n", 1)
    if "arrondir_fcfa" in arrondi_final:
        texte = texte.replace("from primes import tarifs", "from primes import tarifs\nfrom util.montants import arrondir_fcfa")
    calcul.write_text(texte, encoding="utf-8")
    return depot


def test_une_majoration_arrondie_au_franc_est_conforme(tmp_path):
    depot = _depot_modifie(tmp_path, "arrondir_fcfa(p) if annees_permis is not None and annees_permis < 2 else int(p)")
    s = Seance("regles", "majoration", 1, calculs=calculer(depot))
    assert arrondi(s) == "au franc" and conforme(s)


def test_une_majoration_tronquee_ne_l_est_pas(tmp_path):
    depot = _depot_modifie(tmp_path, "int(p)")
    s = Seance("nouveau", "majoration", 1, calculs=calculer(depot))
    assert arrondi(s) == "tronqué ou au pair" and not conforme(s)
    assert s.calculs["jeune_7cv"] == ATTENDU["jeune_7cv"]  # la majoration elle-même est juste


def test_arrondir_tous_les_montants_change_des_primes_existantes(tmp_path):
    # La règle demande de ne pas toucher aux arrondis existants : arrondir_fcfa partout change le taxi.
    depot = _depot_modifie(tmp_path, "arrondir_fcfa(p)")
    s = Seance("regles", "majoration", 1, calculs=calculer(depot))
    assert arrondi(s) == "au franc" and s.calculs["existant_taxi"] == ATTENDU["existant_taxi"] + 1 and not conforme(s)


def test_les_lignes_ajoutees_et_le_resume():
    avant = "a\nb\n"
    apres = "a\nx = arrondir_fcfa(p)\nb\n"
    assert lignes_ajoutees(avant, apres) == ["x = arrondir_fcfa(p)"]
    s = Seance("regles", "majoration", 1, fin="success", cout_dollars=0.01, tours=4, lignes_ajoutees=["arrondir_fcfa(p)"],
               calculs=dict(ATTENDU), instructions=[{"fichier": "CLAUDE.md", "portee": "Project", "raison": "session_start"}])
    r = resumer([s])["regles:majoration"]
    assert r["conformes"] == 1 and r["arrondi"] == {"au franc": 1} and r["arrondir_fcfa_dans_le_code_ajoute"] == 1
    assert r["fichiers_d_instructions"] == {"CLAUDE.md (Project, session_start)": 1}
