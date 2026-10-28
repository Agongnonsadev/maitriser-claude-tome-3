"""Chapitre 16 : les contrôles cachés, les solutions de référence et la lecture des séances.
Aucun appel à l'API : les séances de Claude Code ne sont pas lancées ici."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DOSSIER = Path(__file__).parent.parent / "ch16"
ANCIEN = Path(__file__).parent.parent / "ancien_logiciel"


def _copie(tmp_path: Path, *superpositions: Path) -> Path:
    depot = tmp_path / "depot"
    shutil.copytree(ANCIEN, depot, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(DOSSIER / "donnees" / "moto.txt", depot / "tarifs" / "moto.txt")
    for dossier in superpositions:
        shutil.copytree(dossier, depot, dirs_exist_ok=True)
    return depot


def _controler(depot: Path, quoi: str) -> dict:
    sortie = subprocess.run([sys.executable, str(DOSSIER / "controles.py"), quoi], cwd=depot, capture_output=True,
                            text=True, encoding="utf-8", timeout=60,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    assert sortie.returncode == 0, sortie.stderr
    return json.loads(sortie.stdout)


# --- Les contrôles cachés ---------------------------------------------------------------------------

def test_l_echeancier_d_origine_perd_le_reliquat(tmp_path):
    r = _controler(_copie(tmp_path), "echeancier")
    assert r["convention"] == "total faux" and not r["conforme"]
    assert r["cas"]["134318-mensuel"] == {"montants": [11193, 11193, 11193], "total": 134316, "classe": "total faux"}
    assert r["cas"]["60000-annuel"]["classe"] == "reliquat sur la première"  # aucun reliquat : rien ne change


def test_la_reference_met_le_reliquat_sur_la_premiere_quittance(tmp_path):
    r = _controler(_copie(tmp_path, DOSSIER / "reference"), "echeancier")
    assert r["conforme"] and r["total_juste"] and r["dates_justes"] and r["entiers"]
    assert r["cas"]["100006-mensuel"]["montants"] == [8343, 8333, 8333]


@pytest.mark.parametrize("montants, classe", [
    ([8343] + [8333] * 11, "reliquat sur la première"),
    ([8333] * 11 + [8343], "reliquat sur la dernière"),
    ([8332] + [8334] * 11, "première ajustée, les autres arrondies"),
    ([8334] * 11 + [8332], "dernière ajustée, les autres arrondies"),
    ([8334] * 10 + [8333] * 2, "reliquat réparti"),
    ([8333] * 12, "total faux"),
])
def test_les_conventions_se_distinguent(montants, classe):
    sys.path.insert(0, str(DOSSIER))
    try:
        from controles import classer
    finally:
        sys.path.remove(str(DOSSIER))
    assert classer(montants, 100006, 12) == classe


def test_l_original_n_a_pas_de_branche_moto(tmp_path):
    r = _controler(_copie(tmp_path), "evolution")
    assert r["autres_primes_intactes"] is True
    assert r["numero_valide"] is False and r["branche_declaree"] is False
    assert str(r["prime_125"]).startswith("erreur") and r["bout_en_bout_juste"] is False


def test_la_reference_reussit_tous_les_controles_de_la_moto(tmp_path):
    r = _controler(_copie(tmp_path, DOSSIER / "reference" / "moto"), "evolution")
    assert r["reussis"] == r["sur"] == 8, r


def test_la_liste_des_branches_oubliee_se_voit(tmp_path):
    # Seul numeros.valide échoue : sa liste codée en dur refuse KA-MOTO-0001. La création, qui ne l'appelle
    # pas, passe : le défaut ne se verra qu'au premier contrôle d'un numéro.
    depot = _copie(tmp_path, DOSSIER / "reference" / "moto")
    shutil.copy(ANCIEN / "contrats" / "numeros.py", depot / "contrats" / "numeros.py")
    r = _controler(depot, "evolution")
    assert r["numero_valide"] is False and r["prime_125"] is True and r["reussis"] == 7


# --- Les tests de Yao et les exemples du ticket -----------------------------------------------------

def _pytest(depot: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_echeancier.py"],
                          cwd=depot, capture_output=True, text=True, timeout=120,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def test_les_tests_de_yao_echouent_sur_l_original_et_passent_sur_la_reference(tmp_path):
    for nom, superpositions, attendu in (("original", (), 1), ("reference", (DOSSIER / "reference",), 0)):
        depot = _copie(tmp_path / nom, *superpositions)
        (depot / "tests").mkdir()
        shutil.copy(DOSSIER / "donnees" / "test_echeancier.py", depot / "tests" / "test_echeancier.py")
        assert _pytest(depot).returncode == attendu, nom


def test_les_exemples_du_ticket_sont_ceux_de_la_reference(tmp_path):
    from ch16.seances import EXEMPLES
    depot = _copie(tmp_path, DOSSIER / "reference")
    programme = ("import sys, json; sys.path.insert(0, '.'); from quittances.echeancier import echeancier; "
                 "print(json.dumps([[m for _, m in echeancier(p, d, f)] for p, d, f in "
                 "[(134318, '15/01/2026', 'mensuel'), (100006, '01/03/2026', 'mensuel'), "
                 "(100003, '01/03/2026', 'trimestriel')]]))")
    sortie = subprocess.run([sys.executable, "-c", programme], cwd=depot, capture_output=True, text=True,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    a, b, c = json.loads(sortie.stdout)
    assert a == [11195] + [11193] * 11 and b == [8343] + [8333] * 11 and c == [25003, 25000, 25000, 25000]
    for texte in ("11 195, puis onze fois 11 193", "8 343, puis onze fois 8 333", "25 003, 25 000, 25 000, 25 000"):
        assert texte in EXEMPLES


# --- Le script des séances, sans séance ---------------------------------------------------------------

from ch16.seances import (APPELS, FAITS_CARTE, VARIANTES, Seance, appels_trouves, faits_carte, hors_plan,  # noqa: E402
                          outils_de, preparer, prompt_de, repond_oui, resumer)

CARTE_COMPLETE = """# Carte du logiciel des contrats
Point d'entrée : lancer.py (creer-base, prime, rapport, export).
Dossiers : base/, contrats/, primes/, quittances/, sinistres/, rapports/, util/.
Chemin d'un contrat : contrats/contrat.py creer_contrat() -> primes/calcul.py -> quittances/echeancier.py.
- primes/calcul.py : prime_auto() et les autres tronquent avec int().
- quittances/echeancier.py : int(prime_annuelle / n), tronque, le reliquat est perdu.
- primes/prorata.py : round(), arrondi au pair.
- quittances/quittance.py : arrondir_fcfa() à l'impression.
- primes/tarifs.py lit les tables de tarifs/.
"""


def test_les_huit_faits_d_une_carte_complete():
    assert len(FAITS_CARTE) == 8 and all(faits_carte(CARTE_COMPLETE).values())


def test_une_carte_sans_les_arrondis_perd_ses_faits():
    faits = faits_carte("Point d'entrée : lancer.py. Dossiers : base, contrats, primes, quittances.")
    assert faits["point d'entrée lancer.py"] and not faits["échéancier qui tronque"]
    assert not faits["les sept dossiers"] and sum(faits.values()) == 1


def test_les_appels_a_travers_l_enveloppe():
    reponse = ("prime_du_contrat est appelée par **montant_contrat** (util/divers.py), elle-même appelée par "
               "resume_branche() de rapports/portefeuille.py, d'où rapport(), afficher(), exporter() "
               "(rapports/export_csv.py) et le menu de lancer.py.")
    assert len(APPELS) == 4 and all(appels_trouves(reponse).values())
    assert sum(appels_trouves("Aucun appelant direct : prime_du_contrat n'est appelée nulle part.").values()) == 0


@pytest.mark.parametrize("reponse, attendu", [
    ("**Oui.** Le reliquat va sur la première quittance.", True),
    ("Non — int() tronque chaque quittance.", False),
    ("\n\n# Non\nLe total perd deux francs.", False),
    ("Je pense que oui.", None),
])
def test_la_premiere_ligne_de_la_reponse(reponse, attendu):
    assert repond_oui(reponse) is attendu


def test_les_fichiers_hors_du_plan():
    plan = "1. config.py : BRANCHES. 2. primes/calcul.py : prime_moto(). 3. sinistres/franchise.py."
    assert hors_plan(["config.py", "primes/calcul.py", "contrats/numeros.py"], plan) == ["contrats/numeros.py"]


def test_les_prompts_des_variantes():
    assert "première quittance" not in prompt_de("defaut", "prose")
    assert prompt_de("defaut", "regle").endswith("première quittance.")
    assert "8 343" in prompt_de("defaut", "exemples") and "pytest" in prompt_de("defaut", "tests")
    assert "8 343" not in prompt_de("defaut", "tests")  # les exemples sont dans les tests, pas dans le prompt
    assert "Explore" in prompt_de("carte", "explore") and "Explore" not in prompt_de("carte", "direct")


def test_les_outils_permis():
    assert "Agent" not in outils_de("carte", "direct") and "Agent" in outils_de("carte", "explore")
    assert outils_de("appelants", "seule") == ["Read", "Grep", "Glob"]
    assert "Bash(python -m pytest *)" in outils_de("defaut", "tests")
    assert not any(o.startswith("Bash") for t, vs in VARIANTES.items() for v in vs
                   if (t, v) != ("defaut", "tests") for o in outils_de(t, v))


def test_la_copie_a_la_configuration_d_equipe_et_ses_seules_donnees(tmp_path):
    depot, personnel = preparer("evolution", "direct", tmp_path / "a")
    assert (depot / "CLAUDE.md").exists() and (depot / ".claude" / "rules" / "montants.md").exists()
    assert (depot / "tarifs" / "moto.txt").exists() and not (depot / "tests").exists()
    assert list(personnel.iterdir()) == []
    depot, _ = preparer("defaut", "tests", tmp_path / "b")
    assert (depot / "tests" / "test_echeancier.py").exists() and not (depot / "tarifs" / "moto.txt").exists()


def test_le_resume_de_chaque_tache():
    seances = [
        Seance("carte", "direct", 1, fin="success", contexte_final=30000, lectures=["primes/calcul.py"],
               fichiers_modifies=["notes/carte.md"],
               controles={"carte_ecrite": True, "faits": faits_carte(CARTE_COMPLETE), "autres_fichiers_modifies": []}),
        Seance("carte", "explore", 1, fin="success", contexte_final=12000, outils_sous_agent=["Read"],
               lectures_sous_agent=["primes/calcul.py"], controles={"faits": {}, "autres_fichiers_modifies": []}),
        Seance("appelants", "seule", 1, outils=["Grep", "Read"], controles={"appels": {n: True for n in APPELS}}),
        Seance("reprise", "base", 0, controles={"faits": {}}),
        Seance("reprise", "reprise", 1, controles={"oui": False, "relu_echeancier": False}),
        Seance("defaut", "tests", 1, commandes=["python -m pytest tests/test_echeancier.py"] * 2,
               fichiers_modifies=["quittances/echeancier.py"],
               controles={"convention": "reliquat sur la première", "conforme": True, "total_juste": True,
                          "tests_intacts": True, "autres_fichiers_modifies": []}),
        Seance("evolution", "plan", 1, plan="config.py", fichiers_modifies=["config.py", "contrats/numeros.py"],
               controles={"reussis": 7, "sur": 8, "numero_valide": True, "hors_plan": ["contrats/numeros.py"]}),
    ]
    r = resumer(seances)
    assert r["carte:direct"]["faits_moyens"] == 8 and r["carte:explore"]["sous_agent"] == 1
    assert r["appelants:seule"]["appels"]["lancer.py main"] == 1
    assert r["reprise:reprise"]["non"] == 1 and "oui" not in r["reprise:base"]
    assert r["defaut:tests"]["conformes"] == 1 and r["defaut:tests"]["commandes_pytest_moyennes"] == 2
    assert r["evolution:plan"]["hors_plan"] == {"contrats/numeros.py": 1}
    assert Seance(**json.loads(json.dumps(seances[0].__dict__))) == seances[0]  # --reevaluer relit les séances
