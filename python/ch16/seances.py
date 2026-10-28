"""Chapitre 16 : comprendre et faire évoluer l'ancien logiciel des contrats, mesuré en séances de Claude Code.

Chaque séance est une vraie séance de Claude Code (celui qu'embarque le Claude Agent SDK, avec son prompt
système), sur une copie neuve de ancien_logiciel/ avec la configuration d'équipe du chapitre 15
(ch15/configuration/projet-v2), sur le poste de Mme Adanlé : un dossier personnel vide. Cinq tâches :
- carte : la carte du logiciel dans notes/carte.md, lue dans la conversation (direct) ou par le sous-agent
  Explore (explore) ; on mesure le contexte de la conversation principale et huit faits dans la carte ;
- appelants : ce qui dépend de prime_du_contrat, à travers le module d'enveloppe util/divers.py ;
- reprise : une séance de la carte, puis echeancier.py corrigé, puis la même question de trois façons :
  la séance reprise telle quelle, reprise en signalant le changement, ou une séance neuve avec la carte ;
  chaque reprise part d'une bifurcation (fork_session) de la même séance, qui reste intacte ;
- defaut : le ticket DSI-2026-031 (le total des quittances perd le reliquat), demandé en prose, avec la règle de
  la comptabilité, avec trois exemples, ou avec les tests de Yao à faire passer (Bash limité à pytest) ;
- evolution : la branche moto (note de l'actuariat n° 2026-21), en exécution directe ou en mode plan puis
  exécution du plan dans la même séance reprise.

Après chaque séance, le code relève ce qu'elle a fait (fichiers modifiés, lus, outils, contexte) et lance les
contrôles cachés (ch16/controles.py) dans la copie. Claude ne les voit jamais.

Lancement, depuis le dossier python/ :
    python -m ch16.seances --taches carte appelants --repetitions 3 --budget-max 0.40
    python -m ch16.seances --reevaluer ch16/resultats/<fichier>.json   # gratuit : relit sans rien relancer
"""

import argparse
import asyncio
import difflib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import Cout, francais
from assureur.journal import noter
from ch15.seances import ANCIEN, CONFIGURATIONS, empreinte, recalculer

DOSSIER = Path(__file__).parent
EQUIPE = CONFIGURATIONS / "projet-v2"   # la configuration d'équipe du chapitre 15
DONNEES = DOSSIER / "donnees"
REFERENCE = DOSSIER / "reference"
CONTROLES = DOSSIER / "controles.py"
MODELE = "claude-haiku-5-5"
GARDE_FOU = 40  # tours au plus : un garde-fou, pas l'arrêt normal

LECTURE = ["Read", "Grep", "Glob"]
ECRITURE = LECTURE + ["Edit", "Write"]

CARTE = (
    "Vous découvrez ce logiciel, et l'équipe veut y ajouter des tests. Commencez par en faire la carte : le rôle "
    "de chaque dossier, les points d'entrée, le chemin d'un contrat de sa création à ses quittances, et chaque "
    "endroit où un montant est arrondi, avec la façon dont il l'est. Écrivez la carte dans notes/carte.md, en "
    "moins de 80 lignes. Ne modifiez aucun autre fichier.")
EXPLORE = " Confiez la lecture du code au sous-agent Explore, et gardez dans la conversation sa synthèse."

APPELANTS = (
    "Le calcul de prime_du_contrat, dans contrats/contrat.py, va changer. Avant d'y toucher : quelles fonctions "
    "du logiciel en dépendent, directement ou par un intermédiaire ? Pour chacune, donnez le fichier et le chemin "
    "d'appel depuis prime_du_contrat. Ne modifiez rien.")

QUESTION = (
    "Pour la revue de demain : le total des 12 quittances mensuelles d'un contrat est-il égal à sa prime "
    "annuelle ? Répondez par oui ou par non sur la première ligne, puis en une phrase pourquoi.")
PREVENUE = "Depuis votre carte, quittances/echeancier.py a été modifié (ticket DSI-2026-031). "
NEUVE = ("Voici la carte du logiciel, établie hier par une autre séance :\n\n{carte}\n\n"
         "Depuis, quittances/echeancier.py a été modifié (ticket DSI-2026-031). ")

TICKET = (
    "Ticket DSI-2026-031, ouvert par la comptabilité : le contrat KA-AUTO-0412, payé par mois, a 12 quittances "
    "de 11 193 FCFA, soit 134 316 FCFA, pour une prime annuelle de 134 318 FCFA. Tous les contrats fractionnés "
    "ont un écart de ce genre. Corrigez quittances/echeancier.py : le total des quittances doit être égal à la "
    "prime annuelle.")
REGLE = " La comptabilité veut le reliquat sur la première quittance."
EXEMPLES = (
    " Exemples attendus (montants des quittances, dans l'ordre) :\n"
    "- echeancier(134318, '15/01/2026', 'mensuel') : 11 195, puis onze fois 11 193 ;\n"
    "- echeancier(100006, '01/03/2026', 'mensuel') : 8 343, puis onze fois 8 333 ;\n"
    "- echeancier(100003, '01/03/2026', 'trimestriel') : 25 003, 25 000, 25 000, 25 000.")
TESTS = (" Yao a écrit les tests dans tests/test_echeancier.py : faites-les passer sans les modifier. "
         "Lancez-les avec : python -m pytest tests/test_echeancier.py")

EVOLUTION = (
    "Note de l'actuariat n° 2026-21 : Kanvô ouvre une branche moto, code MOTO, libellé « Moto ». Le tarif est "
    "dans tarifs/moto.txt, déjà reporté par la DSI. La prime dépend de la cylindrée (paramètre cylindree, en cm³), "
    "elle est majorée pour un usage taxi-moto (usage taxi), et l'option casque_passager s'y ajoute. Franchises : "
    "collision 20 000 FCFA, vol 30 000 FCFA. Un contrat moto doit pouvoir être créé et numéroté (KA-MOTO-0001), "
    "tarifé, recevoir ses quittances, déclarer un sinistre, et figurer au rapport du portefeuille comme à l'export.")
EXECUTER = "Le plan est approuvé : exécutez-le."

VARIANTES = {
    "carte": ["direct", "explore"],
    "appelants": ["seule"],
    "reprise": ["reprise", "prevenue", "neuve"],
    "defaut": ["prose", "regle", "exemples", "tests"],
    "evolution": ["direct", "plan"],
}


@dataclass
class Seance:
    tache: str
    variante: str
    repetition: int
    fin: str = "exception"          # subtype du dernier ResultMessage ; « erreur:… » si is_error
    reponse: str = ""
    tours: int = 0
    cout_dollars: float = 0.0       # total_cost_usd, estimé par Claude Code (somme des parties)
    cout_recalcule: float = 0.0     # le même usage, chiffré avec assureur/couts.py
    model_usage: dict = field(default_factory=dict)
    outils: list[str] = field(default_factory=list)            # de la conversation principale
    outils_sous_agent: list[str] = field(default_factory=list)
    lectures: list[str] = field(default_factory=list)          # fichiers lus (Read), conversation principale
    lectures_sous_agent: list[str] = field(default_factory=list)
    commandes: list[str] = field(default_factory=list)         # Bash
    contexte_final: int = 0         # tokens d'entrée de la dernière requête de la conversation principale
    contexte_max: int = 0
    fichiers_modifies: list[str] = field(default_factory=list)  # d'après les fichiers, pas les outils
    plan: str = ""                  # l'entrée de l'outil ExitPlanMode, en mode plan
    controles: dict = field(default_factory=dict)
    session_id: str | None = None
    parties: int = 0                # appels à query() : 2 pour un plan suivi de son exécution
    latence_s: float = 0.0
    erreur: str | None = None


def normaliser(texte: str) -> str:
    """En minuscules, sans accents : les contrôles de texte ne dépendent pas de la typographie."""
    return "".join(c for c in unicodedata.normalize("NFD", texte.lower()) if unicodedata.category(c) != "Mn")


def _lignes(texte: str) -> list[str]:
    return [l for l in normaliser(texte).splitlines() if l.strip()]


# Huit faits que la carte doit contenir, cherchés ligne par ligne : un repère, pas une note de qualité.
FAITS_CARTE = {
    "point d'entrée lancer.py": lambda L: any("lancer.py" in l for l in L),
    "échéancier qui tronque": lambda L: any("echeancier" in l and ("int(" in l or "tronqu" in l) for l in L),
    "prorata arrondi au pair": lambda L: any("prorata" in l and ("round(" in l or "pair" in l) for l in L),
    "quittance par arrondir_fcfa": lambda L: any("quittance" in l and "arrondir_fcfa" in l for l in L),
    "primes qui tronquent": lambda L: any(("calcul" in l or "prime_" in l) and ("int(" in l or "tronqu" in l)
                                          and "echeancier" not in l for l in L),
    "création du contrat": lambda L: any("creer_contrat" in l for l in L),
    "lecture des tarifs": lambda L: any("tarifs.py" in l or "tarifs.lire" in l for l in L),
    "les sept dossiers": lambda L: all(any(d in l for l in L) for d in
                                       ("base", "contrats", "primes", "quittances", "sinistres", "rapports", "util")),
}

# Ce qui dépend de prime_du_contrat : l'enveloppe, puis le rapport, l'export et le menu.
APPELS = {
    "util/divers.py montant_contrat": lambda t: "montant_contrat" in t,
    "rapports/portefeuille.py resume_branche": lambda t: "resume_branche" in t,
    "rapports/export_csv.py exporter": lambda t: "exporter" in t or "export_csv" in t,
    "lancer.py main": lambda t: "lancer" in t,
}


def faits_carte(texte: str) -> dict[str, bool]:
    lignes = _lignes(texte)
    return {nom: bool(f(lignes)) for nom, f in FAITS_CARTE.items()}


def appels_trouves(reponse: str) -> dict[str, bool]:
    t = normaliser(reponse)
    return {nom: bool(f(t)) for nom, f in APPELS.items()}


def premiere_ligne(reponse: str) -> str:
    for l in reponse.splitlines():
        l = normaliser(l).strip(" *#>-_:.")
        if l:
            return l
    return ""


def repond_oui(reponse: str) -> bool | None:
    l = premiere_ligne(reponse)
    if l.startswith("oui"):
        return True
    if l.startswith("non"):
        return False
    return None


def hors_plan(fichiers: list[str], plan: str) -> list[str]:
    """Les fichiers modifiés dont le plan ne parle pas : ni leur nom, ni leur nom sans extension comme mot
    (un plan dit souvent « echeancier() » plutôt que « quittances/echeancier.py »)."""
    import re
    p = normaliser(plan)
    return [f for f in fichiers if normaliser(Path(f).name) not in p
            and not re.search(rf"\b{re.escape(normaliser(Path(f).stem))}\b", p)]


def prompt_de(tache: str, variante: str) -> str:
    if tache == "carte":
        return CARTE + (EXPLORE if variante == "explore" else "")
    if tache == "appelants":
        return APPELANTS
    if tache == "defaut":
        return TICKET + {"prose": "", "regle": REGLE, "exemples": REGLE + EXEMPLES, "tests": REGLE + TESTS}[variante]
    if tache == "evolution":
        return EVOLUTION
    raise ValueError(tache)


def outils_de(tache: str, variante: str) -> list[str]:
    """Les outils permis sans question ; en mode dontAsk, tout le reste (Bash compris) est refusé."""
    if tache == "carte":
        return ECRITURE + (["Agent"] if variante == "explore" else [])
    if tache in ("appelants", "reprise"):
        return LECTURE
    if tache == "defaut":
        return ECRITURE + (["Bash(python -m pytest *)"] if variante == "tests" else [])
    if tache == "evolution":
        return ECRITURE + ["Agent"]
    raise ValueError(tache)


def preparer(tache: str, variante: str, dossier: Path) -> tuple[Path, Path]:
    """Une copie neuve du dépôt, avec la configuration d'équipe, et un dossier personnel vide."""
    depot = dossier / "depot"
    shutil.copytree(ANCIEN, depot, ignore=shutil.ignore_patterns("__pycache__", "*.db"))
    shutil.copytree(EQUIPE, depot, dirs_exist_ok=True)
    if tache == "evolution":
        shutil.copy(DONNEES / "moto.txt", depot / "tarifs" / "moto.txt")
    if tache == "defaut" and variante == "tests":
        (depot / "tests").mkdir()
        shutil.copy(DONNEES / "test_echeancier.py", depot / "tests" / "test_echeancier.py")
    personnel = dossier / "personnel"  # tient lieu de ~/.claude : celui de Mme Adanlé, vide
    personnel.mkdir()
    return depot, personnel


def _court(chemin: str | None, depot: Path) -> str:
    if not chemin:
        return ""
    try:
        return Path(chemin).resolve().relative_to(depot.resolve()).as_posix()
    except ValueError:
        return chemin


async def interroger(s: Seance, prompt: str, depot: Path, personnel: Path, modele: str, budget: float,
                     outils: list[str], mode: str = "dontAsk", resume: str | None = None, fork: bool = False) -> None:
    """Une partie de séance : un appel à query(), dont l'usage et les outils s'ajoutent à la séance."""
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, ToolUseBlock, query
    options = ClaudeAgentOptions(
        model=modele,
        system_prompt={"type": "preset", "preset": "claude_code"},  # sans cela, le SDK envoie un prompt vide
        setting_sources=["user", "project", "local"],
        allowed_tools=outils,
        permission_mode=mode,
        effort="medium",
        max_turns=GARDE_FOU,
        max_budget_usd=budget,
        cwd=str(depot),
        resume=resume,
        fork_session=fork,
        env={"CLAUDE_CONFIG_DIR": str(personnel),
             "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
             "PYTHONDONTWRITEBYTECODE": "1",
             # python et pytest : ceux de l'environnement du dépôt d'accompagnement
             "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")},
    )
    s.parties += 1
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                principal = message.parent_tool_use_id is None
                for b in message.content:
                    if not isinstance(b, ToolUseBlock):
                        continue
                    (s.outils if principal else s.outils_sous_agent).append(b.name)
                    if b.name == "Read":
                        (s.lectures if principal else s.lectures_sous_agent).append(
                            _court(b.input.get("file_path"), depot))
                    elif b.name == "Bash":
                        s.commandes.append(b.input.get("command", ""))
                    elif b.name == "ExitPlanMode":
                        s.plan = b.input.get("plan", "") or s.plan
                if principal and message.usage:
                    n = sum(message.usage.get(k, 0) or 0 for k in
                            ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
                    s.contexte_final, s.contexte_max = n, max(s.contexte_max, n)
            elif isinstance(message, ResultMessage):
                s.fin, s.reponse = message.subtype, message.result or ""
                if message.is_error:
                    s.fin, s.erreur, s.reponse = f"erreur:{message.subtype}", message.result, ""
                s.tours += message.num_turns
                s.cout_dollars += message.total_cost_usd or 0.0
                s.session_id = message.session_id
                for nom, u in (message.model_usage or {}).items():
                    total = s.model_usage.setdefault(nom, {})
                    for k, v in u.items():
                        if isinstance(v, (int, float)) and not isinstance(v, bool):
                            total[k] = total.get(k, 0) + v
                noter(None, modele, Cout(message.total_cost_usd or 0.0), chapitre="16", etape="seance",
                      cas=f"{s.tache}:{s.variante}", seance=message.session_id, subtype=message.subtype,
                      tours=message.num_turns, cout_sdk=message.total_cost_usd)
    except Exception as erreur:  # query() lève après un ResultMessage d'erreur : on garde le résultat
        s.erreur = s.erreur or f"{type(erreur).__name__}: {erreur}"
    s.cout_recalcule = recalculer(s.model_usage)


def controler(depot: Path, quoi: str) -> dict:
    """Les contrôles cachés, dans un processus à part, depuis la copie."""
    sortie = subprocess.run([sys.executable, str(CONTROLES), quoi], cwd=depot, capture_output=True, text=True,
                            encoding="utf-8", timeout=120,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
    if sortie.returncode != 0:
        lignes = sortie.stderr.strip().splitlines()
        return {"erreur": lignes[-1] if lignes else "échec"}
    return json.loads(sortie.stdout)


def difference(avant: Path, apres: Path) -> str:
    """Le diff d'un fichier, pour citer le code que la séance a écrit."""
    a = avant.read_text(encoding="utf-8").splitlines()
    b = apres.read_text(encoding="utf-8").splitlines() if apres.exists() else []
    return "\n".join(difflib.unified_diff(a, b, "avant", "apres", lineterm="", n=1))


def _modifies(avant: dict, depot: Path) -> list[str]:
    apres = empreinte(depot)
    return sorted(f for f in set(avant) | set(apres) if avant.get(f) != apres.get(f)
                  and not f.startswith(".claude/") and not f.startswith(".pytest_cache/"))


async def seance(tache: str, variante: str, repetition: int, modele: str, budget: float) -> Seance:
    """Une séance des tâches carte, appelants, defaut ou evolution (la reprise a sa propre fonction)."""
    s = Seance(tache, variante, repetition)
    dossier = Path(tempfile.mkdtemp(prefix="kanvo-ch16-"))
    debut = time.perf_counter()
    try:
        depot, personnel = preparer(tache, variante, dossier)
        avant = empreinte(depot)
        if tache == "evolution" and variante == "plan":
            await interroger(s, prompt_de(tache, variante), depot, personnel, modele, budget,
                             LECTURE + ["Agent"], mode="plan")
            if s.session_id and budget - s.cout_dollars > 0.01:
                # Sans ExitPlanMode (absent des séances de l'Agent SDK), le plan est dans le dossier des plans
                # de Claude Code ; à défaut, dans la réponse. (Lecture du fichier ajoutée après la série du
                # 28 octobre 2026 : une réponse avait résumé le rapport d'Explore au lieu du plan.)
                plans = sorted((personnel / "plans").glob("*.md"), key=lambda p: p.stat().st_mtime)
                s.plan = s.plan or (plans[-1].read_text(encoding="utf-8") if plans else s.reponse)
                await interroger(s, EXECUTER, depot, personnel, modele, budget - s.cout_dollars,
                                 outils_de(tache, variante), resume=s.session_id)
        else:
            await interroger(s, prompt_de(tache, variante), depot, personnel, modele, budget,
                             outils_de(tache, variante))
        s.fichiers_modifies = _modifies(avant, depot)
        if tache == "carte":
            carte = depot / "notes" / "carte.md"
            texte = carte.read_text(encoding="utf-8", errors="replace") if carte.exists() else ""
            s.controles = {"carte_ecrite": carte.exists(), "lignes": len(texte.splitlines()),
                           "faits": faits_carte(texte), "texte": texte,
                           "autres_fichiers_modifies": [f for f in s.fichiers_modifies if f != "notes/carte.md"]}
        elif tache == "appelants":
            s.controles = {"appels": appels_trouves(s.reponse)}
        elif tache == "defaut":
            s.controles = controler(depot, "echeancier")
            s.controles["diff"] = difference(ANCIEN / "quittances" / "echeancier.py",
                                             depot / "quittances" / "echeancier.py")
            if variante == "tests":
                s.controles["tests_intacts"] = "tests/test_echeancier.py" not in s.fichiers_modifies
            s.controles["autres_fichiers_modifies"] = [f for f in s.fichiers_modifies if
                                                       f not in ("quittances/echeancier.py",)]
        elif tache == "evolution":
            s.controles = controler(depot, "evolution")
            s.controles["tarifs_intacts"] = not any(f.startswith("tarifs/") for f in s.fichiers_modifies)
            if variante == "plan":
                s.controles["hors_plan"] = hors_plan(s.fichiers_modifies, s.plan)
    finally:
        s.latence_s = round(time.perf_counter() - debut, 1)
        shutil.rmtree(dossier, ignore_errors=True)
    return s


async def reprise(repetitions: int, modele: str, budget: float, variantes: list[str]) -> list[Seance]:
    """La séance de la carte, la correction de l'échéancier, puis la question posée de trois façons."""
    seances = []
    dossier = Path(tempfile.mkdtemp(prefix="kanvo-ch16-reprise-"))
    debut = time.perf_counter()
    try:
        depot, personnel = preparer("reprise", "base", dossier)
        base = Seance("reprise", "base", 0)
        await interroger(base, CARTE, depot, personnel, modele, budget, outils_de("carte", "direct"))
        carte = depot / "notes" / "carte.md"
        texte = carte.read_text(encoding="utf-8", errors="replace") if carte.exists() else ""
        base.controles = {"carte_ecrite": carte.exists(), "faits": faits_carte(texte), "texte": texte,
                          "lu_echeancier": "quittances/echeancier.py" in base.lectures}
        base.latence_s = round(time.perf_counter() - debut, 1)
        seances.append(base)
        if not base.session_id:
            return seances
        # La correction de Mme Adanlé est fusionnée : le fichier lu par la séance de la carte a changé.
        shutil.copy(REFERENCE / "quittances" / "echeancier.py", depot / "quittances" / "echeancier.py")
        depense = base.cout_dollars
        for repetition in range(1, repetitions + 1):
            for variante in variantes:
                if budget - depense < 0.02:
                    print(f"Arrêt avant reprise:{variante} #{repetition} : plafond presque atteint.")
                    return seances
                s = Seance("reprise", variante, repetition)
                t0 = time.perf_counter()
                if variante == "neuve":
                    await interroger(s, NEUVE.format(carte=texte) + QUESTION, depot, personnel, modele,
                                     budget - depense, LECTURE)
                else:
                    await interroger(s, (PREVENUE if variante == "prevenue" else "") + QUESTION, depot, personnel,
                                     modele, budget - depense, LECTURE, resume=base.session_id, fork=True)
                s.controles = {"premiere_ligne": premiere_ligne(s.reponse)[:80], "oui": repond_oui(s.reponse),
                               "relu_echeancier": "quittances/echeancier.py" in s.lectures}
                s.latence_s = round(time.perf_counter() - t0, 1)
                depense += s.cout_dollars
                seances.append(s)
                _afficher(s)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
    return seances


def _afficher(s: Seance) -> None:
    c = s.controles
    detail = {
        "carte": lambda: f"faits {sum(c.get('faits', {}).values())}/8, contexte {s.contexte_final}",
        "appelants": lambda: f"appels {sum(c.get('appels', {}).values())}/4",
        "reprise": lambda: f"oui={c.get('oui')}, relu={c.get('relu_echeancier')}",
        "defaut": lambda: f"{c.get('convention')}, conforme={c.get('conforme')}",
        "evolution": lambda: f"contrôles {c.get('reussis')}/{c.get('sur')}",
    }.get(s.tache, lambda: "")
    try:
        d = detail()
    except Exception:
        d = ""
    print(f"{s.tache}:{s.variante} #{s.repetition} : {s.fin}, {s.tours} tours, {francais(s.cout_dollars, 4)} $, "
          f"{s.latence_s} s ; modifiés : {', '.join(s.fichiers_modifies) or 'aucun'} ; {d}"
          + (f" ; {s.erreur}" if s.erreur else ""))


def _compte(valeurs) -> dict:
    valeurs = list(valeurs)
    return {str(v): valeurs.count(v) for v in dict.fromkeys(valeurs)}


def resumer(seances: list[Seance]) -> dict:
    groupes: dict[str, list[Seance]] = {}
    for s in seances:
        groupes.setdefault(f"{s.tache}:{s.variante}", []).append(s)
    resume = {}
    for cle, ss in groupes.items():
        r = {
            "seances": len(ss),
            "fins": _compte(s.fin for s in ss),
            "cout_total": round(sum(s.cout_dollars for s in ss), 6),
            "cout_moyen": round(statistics.mean(s.cout_dollars for s in ss), 6),
            "cout_recalcule_total": round(sum(s.cout_recalcule for s in ss), 6),
            "tours_moyens": round(statistics.mean(s.tours for s in ss), 1),
            "contexte_final_median": statistics.median(s.contexte_final for s in ss),
            "lectures_principales_moyennes": round(statistics.mean(len(s.lectures) for s in ss), 1),
            "lectures_sous_agent_moyennes": round(statistics.mean(len(s.lectures_sous_agent) for s in ss), 1),
            "sous_agent": sum(bool(s.outils_sous_agent) for s in ss),
            "fichiers_modifies": _compte(f for s in ss for f in s.fichiers_modifies),
            "latence_mediane_s": statistics.median(s.latence_s for s in ss),
        }
        tache = ss[0].tache
        if tache == "carte":
            r["faits"] = {nom: sum(s.controles.get("faits", {}).get(nom, False) for s in ss) for nom in FAITS_CARTE}
            r["faits_moyens"] = round(statistics.mean(sum(s.controles.get("faits", {}).values()) for s in ss), 1)
            r["autres_fichiers_modifies"] = sum(bool(s.controles.get("autres_fichiers_modifies")) for s in ss)
        elif tache == "appelants":
            r["appels"] = {nom: sum(s.controles.get("appels", {}).get(nom, False) for s in ss) for nom in APPELS}
            r["outils"] = _compte(o for s in ss for o in s.outils)
        elif tache == "reprise" and ss[0].variante != "base":
            r["oui"] = sum(s.controles.get("oui") is True for s in ss)
            r["non"] = sum(s.controles.get("oui") is False for s in ss)
            r["relu_echeancier"] = sum(bool(s.controles.get("relu_echeancier")) for s in ss)
        elif tache == "defaut":
            r["conventions"] = _compte(s.controles.get("convention", s.controles.get("erreur")) for s in ss)
            r["conformes"] = sum(bool(s.controles.get("conforme")) for s in ss)
            r["total_juste"] = sum(bool(s.controles.get("total_juste")) for s in ss)
            r["autres_fichiers_modifies"] = _compte(f for s in ss for f in s.controles.get("autres_fichiers_modifies", []))
            r["commandes_pytest_moyennes"] = round(statistics.mean(
                sum("pytest" in c for c in s.commandes) for s in ss), 1)
            if ss[0].variante == "tests":
                r["tests_intacts"] = sum(bool(s.controles.get("tests_intacts")) for s in ss)
        elif tache == "evolution":
            r["reussis"] = [s.controles.get("reussis") for s in ss]
            cles = [k for k in ss[0].controles if isinstance(ss[0].controles.get(k), bool)]
            r["par_controle"] = {k: sum(s.controles.get(k) is True for s in ss) for k in cles}
            if ss[0].variante == "plan":
                r["plans_obtenus"] = sum(bool(s.plan) for s in ss)
                # recalculé ici, pour qu'une relecture (--reevaluer) suive la règle du jour
                r["hors_plan"] = _compte(f for s in ss for f in hors_plan(s.fichiers_modifies, s.plan))
        resume[cle] = r
    return resume


async def lancer(taches: list[str], variantes: list[str] | None, repetitions: int, modele: str,
                 budget_max: float) -> tuple[list[Seance], float]:
    seances, depense = [], 0.0
    for tache in taches:
        choisies = [v for v in VARIANTES[tache] if not variantes or v in variantes]
        if tache == "reprise":
            ss = await reprise(repetitions, modele, budget_max - depense, choisies)
            if ss:
                _afficher(ss[0])
            seances += ss
            depense += sum(s.cout_dollars for s in ss)
            continue
        for repetition in range(1, repetitions + 1):
            for variante in choisies:
                restant = budget_max - depense
                if restant < 0.02:
                    print(f"Arrêt avant {tache}:{variante} #{repetition} : plafond presque atteint.")
                    return seances, depense
                s = await seance(tache, variante, repetition, modele, restant)
                depense += s.cout_dollars
                seances.append(s)
                _afficher(s)
    return seances, depense


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 16 : l'ancien logiciel des contrats, en séances.")
    parser.add_argument("--taches", nargs="+", choices=list(VARIANTES), default=["carte"])
    parser.add_argument("--variantes", nargs="+", help="les variantes à lancer (toutes par défaut)")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--modele", default=MODELE)
    parser.add_argument("--budget-max", type=float, default=0.20)
    parser.add_argument("--reevaluer", help="relire un fichier de résultats, sans rien relancer")
    args = parser.parse_args()
    # Une console Windows en cp1252 ne sait pas écrire « ≈ » : un caractère remplacé plutôt qu'une erreur.
    sys.stdout.reconfigure(errors="replace")

    if args.reevaluer:
        donnees = json.loads(Path(args.reevaluer).read_text(encoding="utf-8"))
        print(json.dumps(resumer([Seance(**s) for s in donnees["seances"]]), ensure_ascii=False, indent=2))
        return

    seances, depense = asyncio.run(lancer(args.taches, args.variantes, args.repetitions, args.modele,
                                          args.budget_max))
    if not seances:
        return
    resume = resumer(seances)
    # Les résultats d'abord : une séance payée ne doit pas se perdre sur un affichage raté.
    nom = "-".join(args.taches) + "-" + args.modele.removeprefix("claude-")
    sortie = DOSSIER / "resultats" / f"{nom}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": args.modele, "taches": args.taches,
                                  "variantes": args.variantes, "repetitions": args.repetitions,
                                  "depense_dollars": round(depense, 6), "resume": resume,
                                  "seances": [asdict(s) for s in seances]},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense estimée par Claude Code : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
