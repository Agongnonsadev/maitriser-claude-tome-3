"""Chapitre 5 : le même agent des sinistres, construit avec le Claude Agent SDK.

Le SDK fait tourner la boucle de Claude Code : plus de stop_reason à lire, plus d'historique à
tenir. Ce qui reste à votre charge, ce sont les réglages :
- les quatre outils, les mêmes fonctions que la boucle à la main, deviennent un serveur MCP qui
  tourne dans ce processus ;
- aucun outil intégré (tools=[]) : l'agent des sinistres n'a rien à faire de Bash ni de Read ;
- seuls ces quatre outils sont permis, sans question (permission_mode="dontAsk") ;
- les quatre définitions sont chargées d'emblée (ENABLE_TOOL_SEARCH=false) : la recherche
  d'outils ne sert qu'au-delà d'une dizaine ;
- max_turns est un garde-fou, max_budget_usd un plafond de dépense par séance ;
- aucun réglage de l'utilisateur n'est chargé (setting_sources=[]), ni mémoire automatique, ni
  autre serveur MCP ; la configuration de Claude Code est neuve (CLAUDE_CONFIG_DIR), et l'agent
  travaille dans un dossier vide.

On lit la fin dans le ResultMessage : subtype ("success", "error_max_turns",
"error_max_budget_usd", "error_during_execution"…), is_error, stop_reason, coût estimé, session_id.
Attention : une panne de l'API arrive en "success" avec is_error à True. Il faut lire les deux.

Lancement, depuis le dossier python/ :  python -m ch05.agent_sdk --repetitions 2 --budget-max 0.30
"""

import argparse
import asyncio
import json
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ResultMessage, ToolUseBlock, TextBlock,
                              create_sdk_mcp_server, query, tool)

from assureur import config
from assureur.couts import cout, francais
from assureur.journal import noter
from assureur.outils import NOMS, OUTILS, executer
from assureur.systeme import Systeme
from ch05.boucle import GARDE_FOU, MODELE, PROMPT

DOSSIER = Path(__file__).parent
SERVEUR = "kanvo"
PREFIXE = f"mcp__{SERVEUR}__"


def outils_sdk(systeme: Systeme, definitions: list | None = None, executer_outil=executer) -> list:
    """Les outils de la boucle à la main, enveloppés pour le SDK : même nom, même description, même schéma."""
    outils = []
    for definition in definitions or OUTILS:
        def envelopper(d):
            @tool(d["name"], d["description"], d["input_schema"])
            async def appeler(arguments: dict) -> dict:
                texte, erreur = executer_outil(systeme, d["name"], arguments)
                return {"content": [{"type": "text", "text": texte}], "is_error": erreur}
            return appeler
        outils.append(envelopper(definition))
    return outils


def serveur(systeme: Systeme, definitions: list | None = None, executer_outil=executer):
    """Un serveur MCP qui tourne dans ce processus : pas de programme à lancer à côté."""
    return create_sdk_mcp_server(name=SERVEUR, version="1.0.0",
                                 tools=outils_sdk(systeme, definitions, executer_outil))


def options(systeme: Systeme, dossier: str, budget_max: float, resume: str | None = None,
            bifurquer: bool = False, definitions: list | None = None, executer_outil=executer,
            prompt: str = PROMPT) -> ClaudeAgentOptions:
    noms = [d["name"] for d in definitions] if definitions else NOMS
    return ClaudeAgentOptions(
        model=MODELE,
        system_prompt=prompt,                  # remplace le prompt système de Claude Code
        mcp_servers={SERVEUR: serveur(systeme, definitions, executer_outil)},
        tools=[],                              # aucun outil intégré
        allowed_tools=[PREFIXE + nom for nom in noms],
        permission_mode="dontAsk",             # ce qui n'est pas permis est refusé, sans question
        effort="medium",                       # celui de l'API pour Haiku 5.5, pour comparer à réglage égal
        max_turns=GARDE_FOU,                   # garde-fou, pas l'arrêt normal
        max_budget_usd=budget_max,             # une estimation côté client, qui peut être un peu dépassée
        setting_sources=[],                    # ni vos réglages, ni votre CLAUDE.md, ni vos Skills
        strict_mcp_config=True,                # aucun autre serveur MCP que celui-ci
        cwd=dossier,
        env={"CLAUDE_CONFIG_DIR": str(Path(dossier) / ".config"),  # une configuration neuve, à part
             "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",  # la mémoire automatique se charge malgré setting_sources
             "ENABLE_TOOL_SEARCH": "false"},
        resume=resume,                         # reprendre une séance existante…
        fork_session=bifurquer,                # … ou en partir dans une nouvelle séance, l'originale intacte
    )


@dataclass
class Seance:
    cas: str
    repetition: int
    fin: str                       # le subtype du ResultMessage ; "erreur:…" si is_error ; "exception" sans résultat
    stop_reason: str | None
    reponse: str
    outils: list[str] = field(default_factory=list)
    appels: list[dict] = field(default_factory=list)  # chaque appel d'outil et ses arguments
    reponses_avec_outils: int = 0  # réponses du modèle qui demandaient un outil
    reponses_outils_texte: int = 0  # … et qui contenaient aussi du texte
    tours: int = 0
    cout_dollars: float = 0.0      # total_cost_usd, estimé par le SDK ; une reprise y ajoute le passé de la séance
    tokens_entree: int = 0          # cache compris
    tokens_sortie: int = 0
    usage: dict = field(default_factory=dict)        # la boucle principale
    model_usage: dict = field(default_factory=dict)  # par modèle, toute la séance
    cout_recalcule: float = 0.0     # le même usage, chiffré avec nos tarifs (assureur/couts.py)
    transmissions: int = 0
    session_id: str | None = None
    latence_s: float = 0.0          # mesurée par nous, démarrage du binaire compris
    duree_s: float = 0.0            # annoncée par le SDK (duration_ms)
    duree_api_s: float = 0.0        # dont l'attente des réponses du modèle (duration_api_ms)
    erreur: str | None = None


async def seance(declaration: str, *, systeme: Systeme, dossier: str, budget_max: float, cas: str = "",
                 repetition: int = 1, resume: str | None = None, bifurquer: bool = False,
                 definitions: list | None = None, executer_outil=executer, prompt: str = PROMPT,
                 chapitre: str = "05") -> Seance:
    """Une séance de l'agent : une demande de l'assuré, autant de tours qu'il en faut."""
    reglages = options(systeme, dossier, budget_max, resume, bifurquer, definitions, executer_outil, prompt)
    return await executer_seance(declaration, reglages, systeme=systeme, cas=cas, repetition=repetition,
                                 chapitre=chapitre)


async def executer_seance(declaration: str, reglages: ClaudeAgentOptions, *, systeme: Systeme | None = None,
                          cas: str = "", repetition: int = 1, chapitre: str = "05") -> Seance:
    """Lance une séance avec des réglages donnés et lit ce qu'elle a fait. Sans `systeme` (un serveur MCP
    externe, au chapitre 7), les transmissions ne se comptent pas : seuls les appels sont connus."""
    avant = len(systeme.transmissions) if systeme else 0
    s = Seance(cas, repetition, "exception", None, "")
    blocs: dict[str, list] = {}  # le SDK émet un AssistantMessage par bloc ; on regroupe par réponse
    debut = time.perf_counter()
    try:
        async for message in query(prompt=declaration, options=reglages):
            if isinstance(message, AssistantMessage):
                blocs.setdefault(message.message_id or str(id(message)), []).extend(message.content)
            elif isinstance(message, ResultMessage):
                s.fin, s.stop_reason, s.reponse = message.subtype, message.stop_reason, message.result or ""
                if message.is_error:
                    # Une panne de l'API arrive avec subtype "success", is_error True et le message
                    # d'erreur dans result : ce texte ne doit jamais partir vers l'assuré.
                    s.fin, s.erreur, s.reponse = f"erreur:{message.subtype}", message.result, ""
                s.tours, s.cout_dollars, s.session_id = message.num_turns, message.total_cost_usd or 0.0, \
                    message.session_id
                s.duree_s, s.duree_api_s = message.duration_ms / 1000, message.duration_api_ms / 1000
                usage = message.usage or {}
                s.tokens_entree = sum(usage.get(k, 0) or 0 for k in ("input_tokens", "cache_read_input_tokens",
                                                                     "cache_creation_input_tokens"))
                s.tokens_sortie = usage.get("output_tokens", 0) or 0
                s.usage, s.model_usage = dict(usage), dict(message.model_usage or {})
                c = cout(MODELE, usage)
                s.cout_recalcule = c.dollars
                # Une ligne par séance : le SDK ne donne pas l'identifiant de chaque requête.
                noter(None, MODELE, c, chapitre=chapitre, etape="agent_sdk", cas=cas or None, seance=message.session_id,
                      subtype=message.subtype, tours=message.num_turns, cout_sdk=message.total_cost_usd)
    except Exception as erreur:  # query() lève après un ResultMessage d'erreur : on garde le résultat
        s.erreur = s.erreur or f"{type(erreur).__name__}: {erreur}"
    for contenu in blocs.values():
        appels = [b for b in contenu if isinstance(b, ToolUseBlock)]
        if appels:
            s.outils += [b.name.removeprefix(PREFIXE) for b in appels]
            s.appels += [{"outil": b.name.removeprefix(PREFIXE), "entree": b.input} for b in appels]
            s.reponses_avec_outils += 1
            s.reponses_outils_texte += any(isinstance(b, TextBlock) and b.text.strip() for b in contenu)
    s.transmissions = len(systeme.transmissions) - avant if systeme else 0
    s.latence_s = round(time.perf_counter() - debut, 2)
    return s


async def lancer(declarations: list[dict], repetitions: int, budget_max: float) -> tuple[list[Seance], float]:
    seances, depense = [], 0.0
    for repetition in range(1, repetitions + 1):
        for d in declarations:
            restant = budget_max - depense
            if restant < 0.01:
                print(f"Arrêt avant {d['id']} #{repetition} : plafond presque atteint.")
                return seances, depense
            with tempfile.TemporaryDirectory() as dossier:
                s = await seance(d["texte"], systeme=Systeme(), dossier=dossier, budget_max=restant,
                                 cas=d["id"], repetition=repetition)
            depense += s.cout_dollars
            seances.append(s)
    return seances, depense


def resumer(seances: list[Seance], declarations: list[dict]) -> dict:
    attendus = {d["id"]: d for d in declarations}
    return {
        "seances": len(seances),
        "fins": {fin: sum(s.fin == fin for s in seances) for fin in dict.fromkeys(s.fin for s in seances)},
        "stop_reasons": {str(r): sum(s.stop_reason == r for s in seances)
                         for r in dict.fromkeys(s.stop_reason for s in seances)},
        "exceptions": sum(s.erreur is not None for s in seances),
        "tours_max": max(s.tours for s in seances),
        "tours_moyens": statistics.mean(s.tours for s in seances),
        "reponses_avec_outils": sum(s.reponses_avec_outils for s in seances),
        "reponses_outils_avec_texte": sum(s.reponses_outils_texte for s in seances),
        "outils_attendus_appeles": sum(set(attendus[s.cas]["outils_attendus"]) <= set(s.outils) for s in seances),
        "transmissions_conformes": sum((s.transmissions > 0) == attendus[s.cas]["transmission_attendue"]
                                       for s in seances),
        "hors_sujet_sans_outil": sum(not s.outils for s in seances if not attendus[s.cas]["sujet"]),
        "hors_sujet": sum(not attendus[s.cas]["sujet"] for s in seances),
        "cout_moyen": statistics.mean(s.cout_dollars for s in seances),
        "cout_max": max(s.cout_dollars for s in seances),
        "tokens_entree_moyens": statistics.mean(s.tokens_entree for s in seances),
        "latence_mediane_s": statistics.median(s.latence_s for s in seances),
        "duree_mediane_annoncee_s": statistics.median(s.duree_s for s in seances),
        "duree_api_mediane_s": statistics.median(s.duree_api_s for s in seances),
    }


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 5 : l'agent des sinistres avec le Claude Agent SDK.")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--budget-max", type=float, default=0.30)
    parser.add_argument("--cas", nargs="*", help="ne lancer que ces déclarations (leurs identifiants)")
    args = parser.parse_args()

    declarations = json.loads((DOSSIER / "declarations.json").read_text(encoding="utf-8"))["declarations"]
    declarations = [d for d in declarations if not args.cas or d["id"] in args.cas]
    seances, depense = asyncio.run(lancer(declarations, args.repetitions, args.budget_max))
    for s in seances:
        print(f"{s.cas} #{s.repetition} : {s.fin} ({s.stop_reason}) en {s.tours} tour(s) ; outils : "
              f"{', '.join(s.outils) or 'aucun'} ; {francais(s.cout_dollars, 5)} $ ; {francais(s.latence_s, 1)} s"
              + (f" ; {s.erreur}" if s.erreur else ""))
    resume = resumer(seances, declarations)
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense estimée par le SDK : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / "resultats" / f"agent-sdk-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "repetitions": args.repetitions,
                                  "depense_dollars": round(depense, 6), "resume": resume,
                                  "seances": [asdict(s) for s in seances]}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
