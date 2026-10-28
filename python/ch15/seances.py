"""Chapitre 15 : la configuration de Claude Code pour une équipe, mesurée sur l'ancien logiciel des contrats.

Chaque séance est une vraie séance de Claude Code (celui qu'embarque le Claude Agent SDK, avec son prompt
système), lancée sur une copie neuve de ancien_logiciel/, avec la configuration d'une variante :
- personnel : les consignes sont dans le CLAUDE.md personnel de Yao (~/.claude/CLAUDE.md), pas dans le dépôt ;
- nouveau : le même dépôt, chez une nouvelle développeuse dont le dossier personnel est vide ;
- projet : les consignes recopiées dans le CLAUDE.md du dépôt (configuration/projet-v1) ;
- regles : la configuration d'équipe (configuration/projet-v2) : un CLAUDE.md court, des règles par chemin
  dans .claude/rules/, une Skill, des permissions partagées.

Le dossier personnel est simulé par CLAUDE_CONFIG_DIR : c'est lui qui tient lieu de ~/.claude. Un hook
InstructionsLoaded, posé dans .claude/settings.local.json (réglage local, hors du dépôt partagé), note chaque
fichier d'instructions chargé, sa portée et la raison du chargement (ch15/noter_instructions.py).

Après la séance, le code relève ce qu'elle a fait : les fichiers modifiés, l'arrondi des lignes ajoutées, les
tarifs intacts, le calcul de la majoration sur des cas choisis, et les fichiers d'instructions chargés.

Lancement, depuis le dossier python/ :
    python -m ch15.seances --variantes personnel nouveau projet regles --taches majoration --repetitions 3 --budget-max 0.60
    python -m ch15.seances --reevaluer ch15/resultats/<fichier>.json   # gratuit : relit sans rien relancer
"""

import argparse
import asyncio
import difflib
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import Cout, francais, tarif
from assureur.journal import noter

DOSSIER = Path(__file__).parent
ANCIEN = DOSSIER.parent / "ancien_logiciel"
CONFIGURATIONS = DOSSIER / "configuration"
NOTER = DOSSIER / "noter_instructions.py"
MODELE = "claude-haiku-5-5"
GARDE_FOU = 30  # tours au plus : un garde-fou, pas l'arrêt normal

VARIANTES = {
    "personnel": {"utilisateur": "yao", "projet": None},
    "nouveau": {"utilisateur": None, "projet": None},
    "projet": {"utilisateur": None, "projet": "projet-v1"},
    "regles": {"utilisateur": None, "projet": "projet-v2"},
}

TACHES = {
    "majoration": (
        "L'actuariat a publié la note n° 2026-17 : une majoration des jeunes conducteurs, dont les taux sont "
        "déjà dans tarifs/auto.txt. Ajoutez-la au calcul de la prime automobile, dans primes/calcul.py, avec un "
        "nouveau paramètre annees_permis (None quand on ne le connaît pas). Ne touchez pas aux autres fonctions."),
    "resilies": (
        "Dans rapports/portefeuille.py, ajoutez au rapport le nombre de contrats résiliés de chaque branche, à "
        "côté du nombre de contrats actifs."),
    "arrondis": "/verifier-arrondis primes",
}

# Les cas du calcul, et ce que donne le code d'origine. « jeune_demi » vaut exactement 56 312,5 FCFA après
# majoration : arrondi au franc (la règle), 56 313 ; tronqué par int() ou arrondi au pair par round(), 56 312.
CAS = {
    "jeune_demi": {"puissance": 4, "usage": "prive", "options": [], "coef_bm": 0.53, "annees_permis": 1},
    "confirme": {"puissance": 4, "usage": "prive", "options": [], "coef_bm": 0.53, "annees_permis": 5},
    "limite": {"puissance": 4, "usage": "prive", "options": [], "coef_bm": 0.53, "annees_permis": 2},
    "inconnu": {"puissance": 4, "usage": "prive", "options": [], "coef_bm": 0.53},
    "jeune_7cv": {"puissance": 7, "usage": "prive", "options": ["vol_incendie"], "coef_bm": 0.95, "annees_permis": 1},
    "existant_taxi": {"puissance": 4, "usage": "taxi", "options": [], "coef_bm": 0.73},
}
ATTENDU = {"jeune_demi": 56313, "confirme": 45050, "limite": 45050, "inconnu": 45050, "jeune_7cv": 156940,
           "existant_taxi": 114792}
JEUNE_TRONQUE = 56312        # int() ou round()
SANS_MAJORATION = 45050


@dataclass
class Seance:
    variante: str
    tache: str
    repetition: int
    fin: str = "exception"         # subtype du ResultMessage ; « erreur:… » si is_error
    reponse: str = ""
    tours: int = 0
    cout_dollars: float = 0.0      # total_cost_usd, estimé par Claude Code
    cout_recalcule: float = 0.0    # le même usage, par modèle, chiffré avec assureur/couts.py
    model_usage: dict = field(default_factory=dict)
    outils: list[str] = field(default_factory=list)
    fichiers_modifies: list[str] = field(default_factory=list)  # d'après les fichiers, pas les outils
    messages_sous_agent: int = 0   # messages émis depuis un sous-agent (parent_tool_use_id)
    instructions: list[dict] = field(default_factory=list)      # le journal du hook InstructionsLoaded
    lignes_ajoutees: list[str] = field(default_factory=list)    # dans primes/calcul.py
    calculs: dict = field(default_factory=dict)                  # les cas de CAS, après la séance
    tarifs_intacts: bool = True
    session_id: str | None = None
    latence_s: float = 0.0
    erreur: str | None = None


def empreinte(dossier: Path) -> dict[str, str]:
    """Le SHA-256 de chaque fichier d'un dossier, par chemin relatif (sans les caches de Python)."""
    return {p.relative_to(dossier).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(dossier.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def preparer(variante: str, dossier: Path, journal: Path) -> tuple[Path, Path]:
    """Une copie neuve du dépôt de la DSI et un dossier personnel, configurés pour la variante."""
    v = VARIANTES[variante]
    depot = dossier / "depot"
    shutil.copytree(ANCIEN, depot, ignore=shutil.ignore_patterns("__pycache__", "*.db"))
    if v["projet"]:
        shutil.copytree(CONFIGURATIONS / v["projet"], depot, dirs_exist_ok=True)
    personnel = dossier / "personnel"  # tient lieu de ~/.claude
    personnel.mkdir()
    if v["utilisateur"]:
        shutil.copy(CONFIGURATIONS / v["utilisateur"] / "CLAUDE.md", personnel / "CLAUDE.md")
    # Le hook de mesure, en réglage local : il ne fait pas partie de la configuration partagée.
    commande = f'"{Path(sys.executable).as_posix()}" "{NOTER.as_posix()}" "{journal.as_posix()}"'
    (depot / ".claude").mkdir(exist_ok=True)
    (depot / ".claude" / "settings.local.json").write_text(json.dumps(
        {"hooks": {"InstructionsLoaded": [{"hooks": [{"type": "command", "command": commande}]}]}},
        indent=2), encoding="utf-8")
    return depot, personnel


def options(depot: Path, personnel: Path, modele: str, budget_max: float):
    from claude_agent_sdk import ClaudeAgentOptions
    return ClaudeAgentOptions(
        model=modele,
        system_prompt={"type": "preset", "preset": "claude_code"},  # sans cela, le SDK envoie un prompt vide
        setting_sources=["user", "project", "local"],  # comme Claude Code en ligne de commande
        allowed_tools=["Read", "Edit", "Write", "Grep", "Glob", "Skill", "Agent"],
        permission_mode="dontAsk",      # ce qui n'est pas permis (Bash compris) est refusé, sans question
        effort="medium",
        max_turns=GARDE_FOU,
        max_budget_usd=budget_max,
        cwd=str(depot),
        env={"CLAUDE_CONFIG_DIR": str(personnel),       # le dossier personnel de la variante
             "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"},   # aucune mémoire automatique d'une séance à l'autre
    )


def recalculer(model_usage: dict) -> float:
    """Le coût d'une séance, modèle par modèle, avec nos tarifs (le cache écrit compté à 5 minutes)."""
    total = 0.0
    for modele, u in model_usage.items():
        try:
            t = tarif(modele)
        except ValueError:
            continue
        total += ((u.get("inputTokens", 0) or 0) * t.entree + (u.get("cacheCreationInputTokens", 0) or 0)
                  * t.ecriture_5m + (u.get("cacheReadInputTokens", 0) or 0) * t.lecture_cache
                  + (u.get("outputTokens", 0) or 0) * t.sortie) / 1_000_000
    return total


def calculer(depot: Path) -> dict:
    """Les cas de CAS, calculés par le code du dépôt après la séance, dans un processus à part."""
    programme = ("import json, sys\nsys.path.insert(0, '.')\nfrom primes import calcul\nr = {}\n"
                 f"for nom, a in json.loads({json.dumps(json.dumps(CAS))}).items():\n"
                 "    try:\n        r[nom] = calcul.prime_auto(**a)\n"
                 "    except Exception as e:\n        r[nom] = 'erreur : %s : %s' % (type(e).__name__, e)\n"
                 "print(json.dumps(r))\n")
    sortie = subprocess.run([sys.executable, "-c", programme], cwd=depot, capture_output=True, text=True,
                            timeout=60, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if sortie.returncode != 0:
        return {"erreur": sortie.stderr.strip().splitlines()[-1] if sortie.stderr.strip() else "échec"}
    return json.loads(sortie.stdout)


def lignes_ajoutees(avant: str, apres: str) -> list[str]:
    return [l[1:] for l in difflib.unified_diff(avant.splitlines(), apres.splitlines(), lineterm="", n=0)
            if l.startswith("+") and not l.startswith("+++")]


async def seance(variante: str, tache: str, repetition: int, modele: str, budget_max: float) -> Seance:
    from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock, query
    s = Seance(variante, tache, repetition)
    dossier = Path(tempfile.mkdtemp(prefix="kanvo-ch15-"))
    debut = time.perf_counter()
    try:
        journal = dossier / "instructions.jsonl"
        depot, personnel = preparer(variante, dossier, journal)
        avant = empreinte(depot)
        try:
            async for message in query(prompt=TACHES[tache], options=options(depot, personnel, modele, budget_max)):
                if isinstance(message, AssistantMessage):
                    if message.parent_tool_use_id is not None:
                        s.messages_sous_agent += 1
                    s.outils += [b.name for b in message.content if isinstance(b, ToolUseBlock)]
                elif isinstance(message, ResultMessage):
                    s.fin, s.reponse = message.subtype, message.result or ""
                    if message.is_error:
                        s.fin, s.erreur, s.reponse = f"erreur:{message.subtype}", message.result, ""
                    s.tours, s.cout_dollars, s.session_id = message.num_turns, message.total_cost_usd or 0.0, \
                        message.session_id
                    s.model_usage = dict(message.model_usage or {})
                    s.cout_recalcule = recalculer(s.model_usage)
                    noter(None, modele, Cout(s.cout_dollars), chapitre="15", etape="seance",
                          cas=f"{variante}:{tache}", seance=message.session_id, subtype=message.subtype,
                          tours=message.num_turns, cout_sdk=message.total_cost_usd)
        except Exception as erreur:  # query() lève après un ResultMessage d'erreur : on garde le résultat
            s.erreur = s.erreur or f"{type(erreur).__name__}: {erreur}"
        apres = empreinte(depot)
        s.fichiers_modifies = sorted(f for f in set(avant) | set(apres)
                                     if avant.get(f) != apres.get(f) and not f.startswith(".claude/"))
        s.tarifs_intacts = all(avant.get(f) == apres.get(f) for f in avant if f.startswith("tarifs/"))
        s.lignes_ajoutees = lignes_ajoutees((ANCIEN / "primes" / "calcul.py").read_text(encoding="utf-8"),
                                            (depot / "primes" / "calcul.py").read_text(encoding="utf-8"))
        if tache == "majoration":
            s.calculs = calculer(depot)
        if journal.exists():
            s.instructions = [lire_instruction(l, depot, personnel)
                              for l in journal.read_text(encoding="utf-8").splitlines() if l.strip()]
    finally:
        s.latence_s = round(time.perf_counter() - debut, 1)
        shutil.rmtree(dossier, ignore_errors=True)
    return s


def lire_instruction(ligne: str, depot: Path, personnel: Path) -> dict:
    """Une ligne du hook, avec des chemins lisibles : relatifs au dépôt, ou ~/.claude pour le dossier personnel."""
    d = json.loads(ligne)

    def court(chemin: str | None) -> str | None:
        if not chemin:
            return chemin
        p = Path(chemin)
        for racine, nom in ((depot, ""), (personnel, "~/.claude/")):
            try:
                return nom + p.resolve().relative_to(racine.resolve()).as_posix()
            except ValueError:
                pass
        return chemin

    return {"fichier": court(d.get("file_path")), "portee": d.get("memory_type"), "raison": d.get("load_reason"),
            "declencheur": court(d.get("trigger_file_path"))}


def arrondi(s: Seance) -> str:
    """Comment la séance a arrondi la majoration, d'après le calcul du cas « jeune_demi »."""
    v = s.calculs.get("jeune_demi")
    if v == ATTENDU["jeune_demi"]:
        return "au franc"
    if v == JEUNE_TRONQUE:
        return "tronqué ou au pair"
    if v == SANS_MAJORATION:
        return "sans majoration"
    return "erreur" if v is None or isinstance(v, str) else "autre"


def conforme(s: Seance) -> bool:
    """La majoration juste sur tous les cas, arrondie au franc, les arrondis existants et les tarifs intacts."""
    return all(s.calculs.get(k) == v for k, v in ATTENDU.items()) and s.tarifs_intacts


def resumer(seances: list[Seance]) -> dict:
    groupes: dict[str, list[Seance]] = {}
    for s in seances:
        groupes.setdefault(f"{s.variante}:{s.tache}", []).append(s)
    resume = {}
    for cle, ss in groupes.items():
        charges = {}
        for s in ss:
            for i in s.instructions:
                nom = f"{i['fichier']} ({i['portee']}, {i['raison']})"
                charges[nom] = charges.get(nom, 0) + 1
        r = {
            "seances": len(ss),
            "fins": {fin: sum(s.fin == fin for s in ss) for fin in dict.fromkeys(s.fin for s in ss)},
            "fichiers_d_instructions": charges,
            "tarifs_intacts": sum(s.tarifs_intacts for s in ss),
            "fichiers_modifies": {f: sum(f in s.fichiers_modifies for s in ss)
                                  for f in sorted({f for s in ss for f in s.fichiers_modifies})},
            "messages_sous_agent": sum(s.messages_sous_agent for s in ss),
            "cout_total": round(sum(s.cout_dollars for s in ss), 6),
            "cout_moyen": round(statistics.mean(s.cout_dollars for s in ss), 6),
            "cout_recalcule_total": round(sum(s.cout_recalcule for s in ss), 6),
            "tours_moyens": round(statistics.mean(s.tours for s in ss), 1),
            "latence_mediane_s": statistics.median(s.latence_s for s in ss),
        }
        if ss[0].tache == "majoration":
            r["arrondi"] = {a: sum(arrondi(s) == a for s in ss) for a in dict.fromkeys(arrondi(s) for s in ss)}
            r["arrondir_fcfa_dans_le_code_ajoute"] = sum(any("arrondir_fcfa" in l for l in s.lignes_ajoutees) for s in ss)
            r["conformes"] = sum(conforme(s) for s in ss)
            r["arrondis_existants_intacts"] = sum(s.calculs.get("existant_taxi") == ATTENDU["existant_taxi"] for s in ss)
        resume[cle] = r
    return resume


async def lancer(variantes: list[str], taches: list[str], repetitions: int, modele: str,
                 budget_max: float) -> tuple[list[Seance], float]:
    seances, depense = [], 0.0
    for repetition in range(1, repetitions + 1):
        for tache in taches:
            for variante in variantes:
                restant = budget_max - depense
                if restant < 0.02:
                    print(f"Arrêt avant {variante}:{tache} #{repetition} : plafond presque atteint.")
                    return seances, depense
                s = await seance(variante, tache, repetition, modele, restant)
                depense += s.cout_dollars
                seances.append(s)
                print(f"{variante}:{tache} #{repetition} : {s.fin}, {s.tours} tours, {francais(s.cout_dollars, 4)} $, "
                      f"{s.latence_s} s ; modifiés : {', '.join(s.fichiers_modifies) or 'aucun'}"
                      + (f" ; arrondi : {arrondi(s)}" if tache == "majoration" else "")
                      + (f" ; {s.erreur}" if s.erreur else ""))
    return seances, depense


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 15 : Claude Code configuré pour une équipe.")
    parser.add_argument("--variantes", nargs="+", choices=list(VARIANTES), default=list(VARIANTES))
    parser.add_argument("--taches", nargs="+", choices=list(TACHES), default=["majoration"])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--modele", default=MODELE)
    parser.add_argument("--budget-max", type=float, default=0.20)
    parser.add_argument("--reevaluer", help="relire un fichier de résultats, sans rien relancer")
    args = parser.parse_args()
    # Une console Windows en cp1252 ne sait pas écrire « ≈ » : un caractère remplacé plutôt qu'une erreur.
    sys.stdout.reconfigure(errors="replace")

    if args.reevaluer:
        donnees = json.loads(Path(args.reevaluer).read_text(encoding="utf-8"))
        seances = [Seance(**s) for s in donnees["seances"]]
        print(json.dumps(resumer(seances), ensure_ascii=False, indent=2))
        return

    seances, depense = asyncio.run(lancer(args.variantes, args.taches, args.repetitions, args.modele,
                                          args.budget_max))
    if not seances:
        return
    resume = resumer(seances)
    # Les résultats d'abord : une séance payée ne doit pas se perdre sur un affichage raté.
    nom = "-".join(args.taches) + "-" + args.modele.removeprefix("claude-")
    sortie = DOSSIER / "resultats" / f"{nom}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": args.modele,
                                  "variantes": args.variantes, "taches": args.taches,
                                  "repetitions": args.repetitions, "depense_dollars": round(depense, 6),
                                  "resume": resume, "seances": [asdict(s) for s in seances]},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense estimée par Claude Code : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
