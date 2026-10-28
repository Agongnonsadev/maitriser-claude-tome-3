"""Chapitre 9 : le modèle voit-il le plafond de dépense ? Deux séances sans outil, avec et sans max_budget_usd.

Claude Code inscrit le plafond dans le contexte du modèle quand max_budget_usd est posé. Le coordinateur
en tient compte dans ses choix : il peut renoncer à une étape pour rester sous le plafond. C'est voulu,
mais il faut le savoir en réglant le plafond.

Lancement, depuis le dossier python/ :  python -m ch09.budget_visible      (environ 0,0003 $)
"""

import asyncio
import shutil
import tempfile

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from assureur.couts import Cout, francais
from assureur.journal import noter
from ch05.boucle import MODELE

QUESTION = ("Avant de répondre : votre contexte contient-il une indication de budget en dollars (plafond, "
            "dépense, reste) ? Si oui, recopiez-la mot pour mot. Si non, répondez « aucune ».")


async def seance(plafond: float | None) -> None:
    dossier, configuration = tempfile.mkdtemp(), tempfile.mkdtemp()
    try:
        async for m in query(prompt=QUESTION, options=ClaudeAgentOptions(
                model=MODELE, system_prompt="Vous êtes un assistant.", tools=[], permission_mode="dontAsk",
                max_budget_usd=plafond, max_turns=2, setting_sources=[], strict_mcp_config=True, cwd=dossier,
                env={"CLAUDE_CONFIG_DIR": configuration, "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"})):
            if isinstance(m, ResultMessage):
                noter(None, MODELE, Cout(m.total_cost_usd or 0.0), chapitre="09", etape="budget_visible",
                      cas=str(plafond), seance=m.session_id, cout_sdk=m.total_cost_usd)
                print(f"max_budget_usd={plafond} ({francais(m.total_cost_usd or 0.0, 5)} $) :\n{m.result}\n")
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
        shutil.rmtree(configuration, ignore_errors=True)


async def principal() -> None:
    await seance(0.20)
    await seance(None)


if __name__ == "__main__":
    asyncio.run(principal())
