"""Chapitre 7 : Claude Code dans le dépôt de l'équipe informatique, simulé par l'Agent SDK.

Le dépôt (ch07/depot_dsi) contient un export du logiciel de gestion daté du 15 octobre, et un .mcp.json
qui branche le serveur MCP de Kanvô Assurances, en direct. Le jeton vient de l'environnement :
le .mcp.json ne contient que ${KANVO_JETON}. Les séances de l'Agent SDK chargent les serveurs du
projet sans demander (setting_sources=["project"]) ; Claude Code, en séance interactive, demanderait
d'abord l'accord.

Le prompt système est celui de Claude Code (preset claude_code). L'agent a Read, Grep et Glob, les deux
outils des ressources MCP, et les outils du serveur. On mesure, pour chaque question :
- la première source consultée : le serveur, un fichier du dépôt, ou le référentiel du serveur ;
- si la réponse est à jour ou périmée (l'export a douze jours) ;
- le nombre d'appels.
Trois variantes du serveur : descriptions d'une ligne, descriptions riches, et descriptions riches sans
le référentiel kanvo://referentiel.

Lancement, depuis le dossier python/ :  python -m ch07.poste_dsi --repetitions 2 --budget-max 0.20
"""

import argparse
import asyncio
import json
import re
import shutil
import statistics
import sys
import tempfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions

from assureur import config
from assureur.couts import francais
from assureur.jetons import creer_registre
from ch05.agent_sdk import PREFIXE, executer_seance
from ch05.boucle import MODELE

DOSSIER = Path(__file__).parent
DEPOT = DOSSIER / "depot_dsi"
INTEGRES = ["Read", "Grep", "Glob", "ListMcpResourcesTool", "ReadMcpResourceTool"]


def source(outil: str) -> str:
    if outil in ("ListMcpResourcesTool", "ReadMcpResourceTool"):
        return "ressource"
    if outil in ("Read", "Grep", "Glob"):
        return "fichier"
    return "mcp"


def classer(reponse: str, question: dict) -> str:
    if any(re.search(m, reponse, re.IGNORECASE) for m in question["a_jour"]):
        return "à jour"
    if any(re.search(m, reponse, re.IGNORECASE) for m in question["perime"]):
        return "périmé"
    return "à relire"


def options(depot: str, jeton: str, registre: Path, budget_max: float, descriptions: str, ressource: str,
            audit: Path, configuration: Path | None = None) -> ClaudeAgentOptions:
    """configuration : le dossier de Claude Code (CLAUDE_CONFIG_DIR), à côté du dépôt et jamais dedans,
    sinon ses fichiers de séance deviennent des fichiers du dépôt, que Grep et Glob trouvent."""
    configuration = configuration or Path(depot).parent / "config"
    return ClaudeAgentOptions(
        model=MODELE,
        system_prompt={"type": "preset", "preset": "claude_code"},  # le prompt de Claude Code, tel quel
        tools=INTEGRES,
        allowed_tools=INTEGRES + [PREFIXE + "*"],
        permission_mode="dontAsk",
        effort="medium",
        max_turns=12,
        max_budget_usd=budget_max,
        setting_sources=["project"],       # le .mcp.json du dépôt, et rien de l'utilisateur
        cwd=depot,
        env={"CLAUDE_CONFIG_DIR": str(configuration), "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
             "ENABLE_TOOL_SEARCH": "false",
             # lus par le .mcp.json : ${KANVO_JETON}, ${KANVO_JETONS}…
             "KANVO_PYTHON": sys.executable, "KANVO_JETON": jeton, "KANVO_JETONS": str(registre),
             "KANVO_AUDIT": str(audit), "KANVO_DESCRIPTIONS": descriptions, "KANVO_RESSOURCE": ressource},
    )


async def lancer(plan: dict, questions: dict, variantes: list[str], repetitions: int, budget_max: float):
    essais, depense = [], 0.0
    with tempfile.TemporaryDirectory() as racine:
        registre = Path(racine) / "registre" / "jetons.json"
        jeton = creer_registre(registre)["tableau-de-bord"]  # le compte de l'équipe : lecture seule
        for nom in variantes:
            v = plan[nom]
            for repetition in range(1, repetitions + 1):
                for qid in v["questions"]:
                    if budget_max - depense < 0.01:
                        print(f"Arrêt avant {nom}:{qid} : plafond presque atteint.")
                        return essais, depense
                    q = questions[qid]
                    with tempfile.TemporaryDirectory() as dossier:
                        depot = Path(dossier) / "depot"
                        shutil.copytree(DEPOT, depot)
                        audit = Path(dossier) / "audit.jsonl"
                        s = await executer_seance(q["texte"], options(str(depot), jeton, registre, budget_max - depense,
                                                                      v["descriptions"], v["ressource"], audit),
                                                  cas=f"dsi-{nom}:{qid}", repetition=repetition, chapitre="07")
                        lu = [json.loads(l) for l in audit.read_text(encoding="utf-8").splitlines()] if audit.exists() else []
                    depense += s.cout_dollars
                    sources = [source(o) for o in s.outils]
                    essais.append({"variante": nom, "question": qid, "repetition": repetition, "fin": s.fin,
                                   "erreur": s.erreur, "appels": s.appels, "premiere_source": sources[0] if sources else "aucune",
                                   "sources": dict(Counter(sources)), "nombre_appels": len(s.outils),
                                   "serveur_appele": bool(lu), "classement": classer(s.reponse, q),
                                   "reponse": s.reponse, "cout_dollars": s.cout_dollars, "latence_s": s.latence_s})
    return essais, depense


def resumer(essais: list[dict]) -> list[dict]:
    lignes = []
    for nom in dict.fromkeys(e["variante"] for e in essais):
        for qid in dict.fromkeys(e["question"] for e in essais if e["variante"] == nom):
            g = [e for e in essais if e["variante"] == nom and e["question"] == qid]
            lignes.append({"variante": nom, "question": qid, "seances": len(g),
                           "premieres_sources": dict(Counter(e["premiere_source"] for e in g)),
                           "classement": dict(Counter(e["classement"] for e in g)),
                           "appels_moyens": statistics.mean(e["nombre_appels"] for e in g),
                           "cout_moyen": statistics.mean(e["cout_dollars"] for e in g)})
    return lignes


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 7 : Claude Code dans le dépôt de l'équipe informatique.")
    parser.add_argument("--variantes", nargs="+", default=["courtes", "riches", "sans-referentiel"])
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--budget-max", type=float, default=0.20)
    args = parser.parse_args()
    donnees = json.loads((DOSSIER / "questions_dsi.json").read_text(encoding="utf-8"))
    questions = {q["id"]: q for q in donnees["questions"]}
    essais, depense = asyncio.run(lancer(donnees["variantes"], questions, args.variantes, args.repetitions,
                                         args.budget_max))
    for l in resumer(essais):
        print(f"{l['variante']:<17} {l['question']} : première source {l['premieres_sources']} ; {l['classement']} ; "
              f"{francais(l['appels_moyens'], 1)} appels ; {francais(l['cout_moyen'], 5)} $")
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / "resultats" / f"poste-dsi-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "repetitions": args.repetitions,
                                  "depense_dollars": round(depense, 6), "resume": resumer(essais), "essais": essais},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
