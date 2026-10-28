"""Chapitre 17 : les demandes de fusion fictives, leurs défauts posés et la lecture des revues.
Aucun appel à l'API : les revues de Claude Code ne sont pas lancées ici."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ch17.revue import (ANCIEN, CORRIGES, CRITERES, CRITERES_V2, DEFAUTS, DEMANDES, MESURES, SCHEMA, SCHEMA_RELANCE, Revue,
                        claude_embarque, deuxieme_commit, diff_demande, fichiers_modifies, preparer, rapprocher,
                        resumer, vise)

CONTROLES = Path(__file__).parent.parent / "ch16" / "controles.py"


def _controler(depot: Path, quoi: str) -> dict:
    sortie = subprocess.run([sys.executable, str(CONTROLES), quoi], cwd=depot, capture_output=True, text=True,
                            encoding="utf-8", timeout=60,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    assert sortie.returncode == 0, sortie.stderr
    return json.loads(sortie.stdout)


# --- Les demandes de fusion ------------------------------------------------------------------------

def test_la_demande_moto_touche_cinq_fichiers_et_ajoute_le_tarif():
    assert sorted(fichiers_modifies(ANCIEN, DEMANDES / "moto")) == [
        "base/requetes.py", "config.py", "primes/calcul.py", "rapports/portefeuille.py",
        "sinistres/franchise.py", "tarifs/moto.txt"]
    diff = diff_demande(ANCIEN, DEMANDES / "moto")
    assert "--- /dev/null" in diff and "+    return int(p)" in diff and "p * 1.65" in diff
    assert "numeros.py" not in diff  # D2 : l'oubli ne se voit pas dans le diff


def test_les_defauts_poses_se_voient_au_controle(tmp_path):
    depot, _ = preparer(tmp_path, [DEMANDES / "moto"], None)
    r = _controler(depot, "evolution")
    assert r["numero_valide"] is False          # D2
    assert r["prime_125"] is False              # D5 : 125 cm³ tombe dans la tranche suivante
    assert r["prime_taxi"] is True              # D4 : le taux en dur donne le même montant, aujourd'hui
    assert r["autres_primes_intactes"] is True and r["bout_en_bout_juste"] is False


def test_le_deuxieme_commit_corrige_d1_et_d3_seulement(tmp_path):
    v2 = deuxieme_commit(tmp_path)
    calcul = (v2 / "primes" / "calcul.py").read_text(encoding="utf-8")
    requetes = (v2 / "base" / "requetes.py").read_text(encoding="utf-8")
    moto = calcul.split("def prime_moto")[1].split("\ndef ")[0]
    assert "return arrondir_fcfa(p)" in moto and "int(" not in moto
    assert "p * 1.65" in calcul and "cylindree < 125" in calcul           # D4 et D5 restent
    assert "% cylindree_min" not in requetes and "LIKE ?" in requetes
    assert CORRIGES == ["D1", "D3"]
    depot, _ = preparer(tmp_path / "c2", [v2], None)
    assert _controler(depot, "evolution")["prime_125"] is False


def test_la_demande_de_l_echeancier_est_conforme(tmp_path):
    depot, _ = preparer(tmp_path, [DEMANDES / "echeancier"], None)
    assert _controler(depot, "echeancier")["conforme"] is True
    assert DEFAUTS["echeancier"] == []


def test_les_criteres_ne_vont_que_dans_le_claude_md_des_revues_avec_criteres(tmp_path):
    avec, personnel = preparer(tmp_path / "a", [DEMANDES / "moto"], CRITERES_V2)
    sans, _ = preparer(tmp_path / "b", [DEMANDES / "moto"], None)
    assert "Revue automatique" in (avec / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Revue automatique" not in (sans / "CLAUDE.md").read_text(encoding="utf-8")
    assert list(personnel.iterdir()) == []
    assert "valide" not in CRITERES and "numeros" not in CRITERES  # les critères ne trahissent pas D2
    assert "virgule flottante" in (avec / "CLAUDE.md").read_text(encoding="utf-8")


def test_la_version_2_ne_change_que_la_regle_des_montants():
    avant = [l for l in CRITERES.splitlines() if l not in CRITERES_V2.splitlines()]
    assert avant == ["- un nouveau montant qui ne passe pas par `arrondir_fcfa()` ;"]
    assert "`//`" in CRITERES_V2


def test_d6_le_filtre_like_ne_fait_pas_au_dessus():
    # Le défaut relevé par la revue d'essai, vérifié : LIKE garde les cylindrées qui commencent par le seuil.
    import sqlite3
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE contrats (numero TEXT, branche TEXT, parametres TEXT)")
    c.executemany("INSERT INTO contrats VALUES (?, 'MOTO', ?)",
                  [("A", "cylindree=300"), ("B", "cylindree=600"), ("C", "cylindree=3000"), ("D", "cylindree=125")])
    sql = "SELECT numero FROM contrats WHERE branche = 'MOTO' AND parametres LIKE '%%cylindree=%d%%'" % 300
    assert [r[0] for r in c.execute(sql)] == ["A", "C"]  # 600 manque, 3000 passe
    assert any(d["id"] == "D6" and "origine" in d for d in DEFAUTS["moto"])


def test_les_schemas():
    item = SCHEMA["properties"]["constats"]["items"]
    assert "detected_pattern" in item["required"] and "confiance" in item["required"]
    assert "statut" in SCHEMA_RELANCE["properties"]["constats"]["items"]["required"]
    assert "statut" not in item["properties"]  # la copie n'a pas touché au schéma de base


def test_claude_code_embarque_existe():
    assert claude_embarque().exists()


# --- Les constats et les défauts --------------------------------------------------------------------

CONSTATS = [
    {"fichier": "primes/calcul.py", "ligne": 96, "description": "prime_moto tronque avec int() au lieu de arrondir_fcfa",
     "detected_pattern": "return int(p)"},
    {"fichier": "ancien_logiciel/contrats/numeros.py", "ligne": 22,
     "description": "valide() a une liste de branches codée en dur", "detected_pattern": "('AUTO', 'HAB', 'SANTE')"},
    {"fichier": "base/requetes.py", "ligne": 20, "description": "Requête formatée avec % : injection SQL",
     "detected_pattern": "% cylindree_min"},
    {"fichier": "primes/calcul.py", "ligne": 89, "description": "Taux taxi écrit en dur", "detected_pattern": "p * 1.65"},
    {"fichier": "primes/calcul.py", "ligne": 84, "description": "Une moto de 125 cm³ tombe dans la tranche 126-500",
     "detected_pattern": "cylindree < 125"},
    {"fichier": "rapports/portefeuille.py", "ligne": 12, "description": "Variable renommée",
     "detected_pattern": "total_primes"},
]


def test_chaque_constat_vise_son_defaut():
    trouves, hors = rapprocher(CONSTATS, "moto")
    assert trouves == ["D1", "D2", "D3", "D4", "D5"] and hors == 1  # D6 : aucun constat ne le vise ici


def test_un_constat_sur_un_autre_fichier_ne_vise_pas_le_defaut():
    d1 = DEFAUTS["moto"][0]
    assert not vise({"fichier": "quittances/echeancier.py", "description": "int() tronque"}, d1)
    assert vise({"fichier": "C:\\tmp\\depot\\primes\\calcul.py", "description": "Tronque."}, d1)


def test_le_resume_des_revues():
    revues = [
        Revue("criteres", "criteres", "moto", 1, structures=1, constats=CONSTATS, defauts_trouves=["D1", "D2"],
              hors_defauts=1),
        Revue("criteres", "criteres", "echeancier", 1, structures=1, constats=[CONSTATS[5]], hors_defauts=1),
        Revue("relance", "avec", "moto", 1, constats=[{**CONSTATS[3], "statut": "toujours_ouvert"}],
              controles={"sur_corriges": 0, "doublons": 0, "publies": 0, "toujours_ouverts": 1}),
        Revue("autorevue", "meme_seance", "majoration", 1, controles={"code_tronque": True,
                                                                      "troncature_signalee": False}),
    ]
    r = resumer(revues)
    assert r["criteres:criteres:moto"]["defauts"]["D2"] == 1 and r["criteres:criteres:moto"]["defauts"]["D3"] == 0
    assert "defauts" not in r["criteres:criteres:echeancier"]
    assert r["relance:avec:moto"]["toujours_ouverts"] == 1
    assert r["autorevue:meme_seance:majoration"]["troncature_signalee"] == 0
    assert Revue(**json.loads(json.dumps(revues[0].__dict__))) == revues[0]


def test_les_mesures():
    assert MESURES["criteres"] == ["vague", "prudente", "criteres", "criteres_v2"] and "par_fichier" in MESURES["passes"]
