"""Chapitre 7 : l'agent des sinistres branché sur le serveur MCP de Kanvô Assurances, en processus séparé.

Au chapitre 6, les outils tournaient dans le processus de l'agent. Ici, l'agent les reçoit d'un serveur
MCP lancé à côté (stdio), avec le jeton de son compte de service : c'est le montage de production. Les
vingt demandes du chapitre 6 vérifient que rien ne se perd en chemin, et mesurent ce que coûte le
serveur séparé.

Les jetons de la mesure sont créés dans un dossier temporaire, passés au serveur par l'environnement,
et ne sont jamais affichés.

Lancement, depuis le dossier python/ :  python -m ch07.agent_mcp --budget-max 0.05
"""

import argparse
import asyncio
import json
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
from assureur.systeme import Systeme
from ch05.agent_sdk import PREFIXE, SERVEUR, executer_seance
from ch05.boucle import GARDE_FOU, MODELE, PROMPT
from ch06.catalogues import VARIANTES
from ch06.choix import evaluer

DOSSIER = Path(__file__).parent
DEMANDES = DOSSIER.parent / "ch06" / "demandes.json"


def serveur_stdio(jeton: str, registre: Path, audit: Path | None = None, **reglages: str) -> dict:
    """La configuration d'un serveur MCP lancé en processus séparé : la commande, et son environnement."""
    env = {"KANVO_JETON": jeton, "KANVO_JETONS": str(registre), **{f"KANVO_{k.upper()}": v for k, v in reglages.items()}}
    if audit:
        env["KANVO_AUDIT"] = str(audit)
    return {"type": "stdio", "command": sys.executable, "args": ["-m", "assureur.serveur_mcp"], "env": env}


def options(jeton: str, registre: Path, dossier: str, budget_max: float, audit: Path | None = None) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODELE,
        system_prompt=PROMPT,
        mcp_servers={SERVEUR: serveur_stdio(jeton, registre, audit)},
        tools=[],
        allowed_tools=[PREFIXE + "*"],      # tout ce que le serveur expose : il n'expose que les portées du jeton
        permission_mode="dontAsk",
        effort="medium",
        max_turns=GARDE_FOU,
        max_budget_usd=budget_max,
        setting_sources=[],
        strict_mcp_config=True,
        cwd=dossier,
        env={"CLAUDE_CONFIG_DIR": str(Path(dossier) / ".config"), "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
             "ENABLE_TOOL_SEARCH": "false"},
    )


async def lancer(demandes: list[dict], budget_max: float) -> tuple[list[dict], float, list[dict]]:
    variante = VARIANTES["yao"]  # les outils attendus du chapitre 6, pour le même catalogue
    essais, depense = [], 0.0
    with tempfile.TemporaryDirectory() as racine:
        registre = Path(racine) / "registre" / "jetons.json"
        audit = Path(racine) / "audit.jsonl"
        jeton = creer_registre(registre)["agent-sinistres"]
        for d in demandes:
            if budget_max - depense < 0.01:
                print(f"Arrêt avant {d['id']} : plafond presque atteint.")
                break
            with tempfile.TemporaryDirectory() as dossier:
                s = await executer_seance(d["texte"], options(jeton, registre, dossier, budget_max - depense, audit),
                                          cas=f"mcp:{d['id']}", chapitre="07")
            depense += s.cout_dollars
            essais.append({"demande": d["id"], "fin": s.fin, "outils": s.outils, "appels": s.appels,
                           "reponse": s.reponse, "cout_dollars": s.cout_dollars, "latence_s": s.latence_s,
                           "duree_s": s.duree_s, "erreur": s.erreur,
                           **evaluer(variante, d, s.outils[:1], s.outils, s.reponse, Systeme())})
        journal_audit = [json.loads(l) for l in audit.read_text(encoding="utf-8").splitlines()] if audit.exists() else []
    return essais, depense, journal_audit


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 7 : l'agent des sinistres par le serveur MCP.")
    parser.add_argument("--budget-max", type=float, default=0.05)
    parser.add_argument("--demandes", nargs="*")
    args = parser.parse_args()
    demandes = json.loads(DEMANDES.read_text(encoding="utf-8"))["demandes"]
    demandes = [d for d in demandes if not args.demandes or d["id"] in args.demandes]
    essais, depense, audit = asyncio.run(lancer(demandes, args.budget_max))
    resume = {
        "seances": len(essais), "fins": dict(Counter(e["fin"] for e in essais)),
        "premier_choix_juste": sum(e["premier_juste"] for e in essais) / len(essais),
        "fausses_conclusions": sum(e["fausse_conclusion"] for e in essais),
        "appels_moyens": statistics.mean(e["nombre_appels"] for e in essais),
        "cout_moyen": statistics.mean(e["cout_dollars"] for e in essais),
        "latence_mediane_s": statistics.median(e["latence_s"] for e in essais),
        "duree_mediane_s": statistics.median(e["duree_s"] for e in essais),
        "audit": dict(Counter(f"{l['compte']}:{l['outil']}:{l['issue']}" for l in audit)),
    }
    for e in essais:
        print(f"{e['demande']} : {e['fin']} ; {', '.join(e['outils']) or 'aucun outil'} ; "
              f"{'bon' if e['premier_juste'] else 'MAUVAIS'} premier choix ; {francais(e['cout_dollars'], 5)} $")
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / "resultats" / f"agent-mcp-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "depense_dollars": round(depense, 6),
                                  "resume": resume, "essais": essais}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
