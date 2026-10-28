"""Chapitre 9 : un outil hors du rôle. Le synthétiseur, avec ou sans la recherche web.

On rejoue au synthétiseur, seul, la demande que le coordinateur lui a écrite dans une étude réelle : la
question, et les résultats complets de l'analyste et du chercheur web. Trois variantes :
- sans : le synthétiseur n'a aucun outil, comme dans le système ;
- avec-web : il a aussi la recherche web, « au cas où » ; son prompt dit toujours qu'il ne cherche rien ;
- avec-web-neutre : la recherche web, et un prompt qui ne dit plus rien de la recherche. C'est le cas d'une
  équipe qui ajoute l'outil sans relire le prompt.
On compte ses recherches, et les adresses qu'il cite sans qu'elles figurent dans la demande : des sources
que ni le chercheur web ni le coordinateur n'ont vues.

Lancement, depuis le dossier python/ :  python -m ch09.hors_role --repetitions 3 --budget-max 0.15
"""

import argparse
import asyncio
import json
import shutil
import statistics
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher, ResultMessage, query

from assureur import config
from assureur.couts import Cout, francais
from assureur.journal import noter
from ch05.boucle import MODELE
from ch09.etudes import sources_citees
from ch09.sous_agents import SYNTHETISEUR

DOSSIER = Path(__file__).parent
INTERDIT = " Vous croisez les résultats qu'on vous donne dans la demande, et rien d'autre : vous ne cherchez rien vous-même."
assert INTERDIT in SYNTHETISEUR
VARIANTES = {
    "sans": ([], SYNTHETISEUR),
    "avec-web": (["WebSearch"], SYNTHETISEUR),
    "avec-web-neutre": (["WebSearch"], SYNTHETISEUR.replace(INTERDIT, " Vous croisez les résultats qu'on vous donne dans la demande.")),
}


def demande_du_coordinateur(fichier: Path | None = None) -> tuple[str, str]:
    """La première demande au synthétiseur trouvée dans les résultats du chapitre (le plus récent d'abord)."""
    fichiers = [fichier] if fichier else sorted((DOSSIER / "resultats").glob("*.json"),
                                                key=lambda f: f.stat().st_mtime, reverse=True)
    for f in fichiers:
        for e in json.loads(f.read_text(encoding="utf-8")).get("etudes", []):
            for d in e["delegations"]:
                if d["type"] == "synthetiseur":
                    return d["prompt"], f.name
    raise SystemExit("Aucune demande au synthétiseur dans ch09/resultats : lancez d'abord ch09.etudes.")


async def seance(demande: str, variante: str, budget_max: float) -> dict:
    recherches = []

    async def noter_recherche(entree, tool_use_id, contexte) -> dict:
        recherches.append(entree["tool_input"].get("query"))
        if len(recherches) > 4:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": "Plafond de 4 recherches atteint."}}
        return {}

    outils, prompt = VARIANTES[variante]
    dossier, configuration = tempfile.mkdtemp(), tempfile.mkdtemp()
    r = {"variante": variante, "fin": "exception", "recherches": recherches}
    debut = time.perf_counter()
    try:
        async for m in query(prompt=demande, options=ClaudeAgentOptions(
                model=MODELE, system_prompt=prompt, tools=outils, allowed_tools=outils,
                permission_mode="dontAsk", effort="medium", max_turns=6, max_budget_usd=budget_max,
                setting_sources=[], strict_mcp_config=True, cwd=dossier,
                env={"CLAUDE_CONFIG_DIR": configuration, "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                     "ENABLE_TOOL_SEARCH": "false"},
                hooks={"PreToolUse": [HookMatcher(matcher="^WebSearch$", hooks=[noter_recherche])]})):
            if isinstance(m, ResultMessage):
                r.update(fin=m.subtype, reponse=m.result or "", cout_dollars=m.total_cost_usd or 0.0,
                         duree_s=m.duration_ms / 1000)
                noter(None, MODELE, Cout(m.total_cost_usd or 0.0), chapitre="09", etape="hors_role",
                      cas=r["variante"], seance=m.session_id, subtype=m.subtype, cout_sdk=m.total_cost_usd)
    except Exception as erreur:
        r["erreur"] = f"{type(erreur).__name__}: {erreur}"
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
        shutil.rmtree(configuration, ignore_errors=True)
    r["latence_s"] = round(time.perf_counter() - debut, 1)
    citees = sources_citees(r.get("reponse", ""))
    r["sources_citees"] = len(citees)
    r["sources_ajoutees"] = sorted(citees - sources_citees(demande))   # absentes de la demande
    return r


async def lancer(demande: str, variantes: list[str], repetitions: int, budget_max: float) -> tuple[list[dict], float]:
    seances, depense = [], 0.0
    for variante in variantes:
        for repetition in range(1, repetitions + 1):
            if budget_max - depense < 0.01:
                print("Arrêt : plafond presque atteint.")
                return seances, depense
            r = await seance(demande, variante, min(0.05, budget_max - depense))
            r["repetition"] = repetition
            depense += r.get("cout_dollars", 0.0)
            seances.append(r)
            print(f"{r['variante']} #{repetition} : {r['fin']} ; {len(r['recherches'])} recherche(s) ; "
                  f"{len(r['sources_ajoutees'])} source(s) absente(s) de la demande ; "
                  f"{francais(r.get('cout_dollars', 0.0), 4)} $" + (f" ; {r['erreur']}" if r.get("erreur") else ""))
    return seances, depense


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 9 : le synthétiseur, avec ou sans la recherche web.")
    parser.add_argument("--variantes", nargs="*", default=list(VARIANTES), choices=list(VARIANTES))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--budget-max", type=float, default=0.15)
    parser.add_argument("--resultats", type=Path, default=None, help="le fichier d'études où prendre la demande")
    args = parser.parse_args()

    demande, source = demande_du_coordinateur(args.resultats)
    seances, depense = asyncio.run(lancer(demande, args.variantes, args.repetitions, args.budget_max))
    resume = {v: {"seances": sum(s["variante"] == v for s in seances),
                  "avec_recherche": sum(bool(s["recherches"]) for s in seances if s["variante"] == v),
                  "recherches": [len(s["recherches"]) for s in seances if s["variante"] == v],
                  "sources_ajoutees": [len(s["sources_ajoutees"]) for s in seances if s["variante"] == v],
                  "cout_moyen": statistics.mean(s.get("cout_dollars", 0.0) for s in seances if s["variante"] == v)}
              for v in dict.fromkeys(s["variante"] for s in seances)}
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense estimée par le SDK : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / "resultats" / f"hors-role-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "demande_prise_dans": source,
                                  "longueur_demande": len(demande), "depense_dollars": round(depense, 6),
                                  "resume": resume, "seances": seances}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
