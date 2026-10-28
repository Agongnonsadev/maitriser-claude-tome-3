"""Chapitre 9 : le système d'études de la souscription, un coordinateur et quatre sous-agents.

Le coordinateur est l'agent principal de la séance. Il n'a qu'un outil à lui, Agent, par lequel il
délègue aux sous-agents de ch09/sous_agents.py ; tout autre outil lui est refusé par un hook. Les
sous-agents ne se parlent pas : chacun reçoit ce que le coordinateur écrit dans son prompt, et lui rend
son résultat. C'est l'architecture en étoile.

Les bornes, toutes posées par le code :
- profondeur : CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1, aucun sous-agent ne lance de sous-agent ;
- nombre : au plus 4 sous-agents en même temps (CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS), et au plus
  8 par étude (le hook du suivi) ;
- dépense : max_budget_usd, qui compte aussi les sous-agents ;
- le sous-agent généraliste intégré et la bifurcation sont retirés : seuls les quatre rôles existent ;
- le chercheur web fait au plus 4 recherches (le hook du suivi).

Pour chaque étude, on relève la chronologie (qui a travaillé, quand, en même temps ou non), les outils
de chaque sous-agent, ce que le coordinateur a transmis au synthétiseur, les aspects de la question que
couvre la réponse, et le coût.

Lancement, depuis le dossier python/ :  python -m ch09.etudes --questions q1-inondation --budget-max 0.30
"""

import argparse
import asyncio
import json
import re
import shutil
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, HookMatcher, ResultMessage, SystemMessage,
                              TextBlock, ToolUseBlock, create_sdk_mcp_server, query)

from assureur import config, documents
from assureur.couts import Cout, francais
from assureur.journal import noter
from ch05.agent_sdk import outils_sdk
from ch05.boucle import MODELE
from ch09.sous_agents import PREFIXE, definitions
from ch09.suivi import AGENT, Suivi

DOSSIER = Path(__file__).parent
PROMPTS = {nom: (DOSSIER / "prompts" / f"coordinateur_{nom}.md").read_text(encoding="utf-8")
           for nom in ("objectifs", "procedure")}
# La variante « séquentielle » : le même prompt, une ligne changée, pour mesurer ce que rapporte le parallélisme.
PARALLELE = "- Lancez dans une même réponse les sous-agents qui ne dépendent pas l'un de l'autre."
SEQUENTIEL = "- Lancez les sous-agents un par un : attendez le résultat de chacun avant d'appeler le suivant."
assert PARALLELE in PROMPTS["objectifs"]
PROMPTS["sequentiel"] = PROMPTS["objectifs"].replace(PARALLELE, SEQUENTIEL)
QUESTIONS = {q["id"]: q for q in json.loads((DOSSIER / "questions.json").read_text(encoding="utf-8"))["questions"]}
GARDE_FOU = 25          # tours du coordinateur au plus


def options(bibliotheque: documents.Bibliotheque, suivi: Suivi, agents: dict, dossier: str, configuration: str,
            budget_max: float, prompt: str, attendre: bool = False) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=MODELE,
        system_prompt=prompt,
        agents=agents,
        mcp_servers={"etudes": create_sdk_mcp_server(name="etudes", version="1.0.0", tools=outils_sdk(
            bibliotheque, documents.OUTILS, documents.executer))},
        # Les outils intégrés de la séance. Un sous-agent ne reçoit que des outils de la séance : la recherche
        # web doit y figurer pour que le chercheur web l'ait ; le hook la refuse au coordinateur.
        tools=["Agent", "WebSearch"],
        allowed_tools=["Agent", "WebSearch", *(PREFIXE + nom for nom in documents.NOMS)],
        disallowed_tools=["Agent(fork)"],      # pas de bifurcation : elle copierait toute la conversation
        permission_mode="dontAsk",
        effort="medium",
        max_turns=GARDE_FOU,
        max_budget_usd=budget_max,             # compte aussi les requêtes des sous-agents
        setting_sources=[],
        strict_mcp_config=True,
        cwd=dossier,
        env={"CLAUDE_CONFIG_DIR": configuration, "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
             "ENABLE_TOOL_SEARCH": "false",
             "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",       # aucun sous-agent ne lance de sous-agent
             "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "4",
             "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",    # pas de sous-agent généraliste, qui aurait tout
             **({"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"} if attendre else {})},
        hooks={
            "PreToolUse": [HookMatcher(hooks=[suivi.avant_outil])],
            "PostToolUse": [HookMatcher(hooks=[suivi.apres_outil])],
            "SubagentStart": [HookMatcher(hooks=[suivi.debut_sous_agent])],
            "SubagentStop": [HookMatcher(hooks=[suivi.fin_sous_agent])],
        },
    )


@dataclass
class Etude:
    question: str
    variante: str
    repetition: int
    fin: str = "exception"
    reponse: str = ""
    rapport: str = ""
    outils_seance: list = field(default_factory=list)   # la liste d'outils du message system:init
    delegations: list = field(default_factory=list)     # type, description, prompt de chaque appel Agent
    reponses_multi_agents: int = 0     # réponses du coordinateur qui lancent plusieurs sous-agents d'un coup
    nom_outil: list = field(default_factory=list)       # le nom de l'outil dans les blocs tool_use : Agent ou Task
    textes_coordinateur: list = field(default_factory=list)
    sous_agents: list = field(default_factory=list)     # la chronologie de chaque sous-agent
    simultanes_max: int = 0
    documents_lus: list = field(default_factory=list)
    recherches_web: int = 0
    hors_role: list = field(default_factory=list)       # (type de sous-agent, outil) hors de son rôle
    refus: list = field(default_factory=list)
    aspects: dict = field(default_factory=dict)
    transmis_au_synthetiseur: dict = field(default_factory=dict)
    evenements_taches: list = field(default_factory=list)
    tours: int = 0
    cout_dollars: float = 0.0     # total_cost_usd du dernier ResultMessage : il cumule toute la séance
    model_usage: dict = field(default_factory=dict)
    duree_s: float = 0.0          # duration_ms du dernier ResultMessage : son segment seulement
    latence_s: float = 0.0        # mesurée par nous, du lancement à la fin du flux
    # Chaque ResultMessage. Un sous-agent en arrière-plan en fait arriver un premier avant la fin de son
    # travail (« je ne peux pas encore conclure »), puis un second quand le coordinateur a repris.
    resultats: list = field(default_factory=list)
    erreur: str | None = None


def sources_citees(texte: str) -> set[str]:
    """Les sources qu'un texte cite : identifiants de documents internes et adresses web."""
    return set(re.findall(r"SOUS-\d{2}", texte)) | {u.rstrip(".,;)]\"'") for u in re.findall(r"https?://[^\s\"'<>]+", texte)}


def transmis_au_synthetiseur(suivi: Suivi) -> dict:
    """Pour chaque appel au synthétiseur : les sources trouvées avant lui, et celles que son prompt contient."""
    resultats = []
    for d in suivi.delegations:
        if d.get("subagent_type") != "synthetiseur":
            continue
        trouvees = set()
        for sa in suivi.sous_agents():
            if sa["type"] in ("chercheur-web", "analyste-documents") and sa["fin"] is not None and sa["fin"] <= d["t"]:
                trouvees |= sources_citees(sa["dernier_message"])
        recues = sources_citees(d.get("prompt", "")) & trouvees
        resultats.append({"t": d["t"], "sources_trouvees": len(trouvees), "sources_transmises": len(recues),
                          "manquantes": sorted(trouvees - recues), "longueur_prompt": len(d.get("prompt", ""))})
    return {"appels": resultats}


async def etudier(question: dict, *, variante: str, repetition: int, budget_max: float,
                  prompt: str, attendre: bool = False, max_sous_agents: int = 8, agents: dict | None = None,
                  bibliotheque: documents.Bibliotheque | None = None, suivi: Suivi | None = None,
                  chapitre: str = "09") -> Etude:
    """Une étude. Le chapitre 10 passe ses propres sous-agents, sa bibliothèque (pannes, documents en plus)
    et son suivi (panne de la recherche web, résultats joints au synthétiseur)."""
    agents = agents or definitions()
    bibliotheque = bibliotheque or documents.Bibliotheque()
    suivi = suivi or Suivi(agents, max_sous_agents=max_sous_agents)
    e = Etude(question["id"], variante, repetition)
    reponses: dict[str, list] = {}
    dossier, configuration = tempfile.mkdtemp(), tempfile.mkdtemp()   # la configuration hors du dossier de travail
    debut = time.perf_counter()
    try:
        async for message in query(prompt=question["texte"], options=options(
                bibliotheque, suivi, agents, dossier, configuration, budget_max, prompt, attendre)):
            if isinstance(message, SystemMessage):
                if message.subtype == "init":
                    e.outils_seance = message.data.get("tools", [])
                elif message.subtype.startswith("task"):
                    e.evenements_taches.append({"subtype": message.subtype,
                                                **{k: message.data.get(k) for k in ("task_id", "status", "description")
                                                   if message.data.get(k) is not None}})
            elif isinstance(message, AssistantMessage) and message.parent_tool_use_id is None:
                reponses.setdefault(message.message_id or str(id(message)), []).extend(message.content)
            elif isinstance(message, ResultMessage):
                e.resultats.append({"t": round(time.perf_counter() - debut, 1), "subtype": message.subtype,
                                    "tours": message.num_turns, "cout_sdk": message.total_cost_usd,
                                    "extrait": (message.result or "")[:200]})
                e.fin, e.reponse = message.subtype, message.result or ""
                if message.is_error:
                    e.fin, e.erreur, e.reponse = f"erreur:{message.subtype}", message.result, ""
                e.tours, e.cout_dollars = message.num_turns, message.total_cost_usd or 0.0
                e.model_usage, e.duree_s = dict(message.model_usage or {}), message.duration_ms / 1000
                # Une ligne par ResultMessage, au coût estimé par le SDK (cumulé sur la séance) : pour le total
                # d'une séance, ne gardez que sa dernière ligne.
                noter(None, MODELE, Cout(message.total_cost_usd or 0.0), chapitre=chapitre, etape="etude", cas=f"{variante}:{question['id']}",
                      seance=message.session_id, subtype=message.subtype, tours=message.num_turns,
                      cout_sdk=message.total_cost_usd)
    except Exception as erreur:   # query() lève après un ResultMessage d'erreur : on garde ce qu'on a
        e.erreur = e.erreur or f"{type(erreur).__name__}: {erreur}"
    finally:
        e.latence_s = round(time.perf_counter() - debut, 1)
        shutil.rmtree(dossier, ignore_errors=True)
        shutil.rmtree(configuration, ignore_errors=True)
    for contenu in reponses.values():
        e.textes_coordinateur += [b.text for b in contenu if isinstance(b, TextBlock) and b.text.strip()]
        e.nom_outil += [b.name for b in contenu if isinstance(b, ToolUseBlock) and b.name not in e.nom_outil]
    e.reponses_multi_agents = sum(sum(isinstance(b, ToolUseBlock) and b.name in AGENT for b in contenu) >= 2
                                  for contenu in reponses.values())
    e.delegations = [{"type": d.get("subagent_type"), "description": d.get("description"), "t": d["t"],
                      "prompt": d.get("prompt", ""),
                      **{k: v for k, v in d.items() if k not in ("subagent_type", "description", "t", "prompt",
                                                                 "tool_use_id")}}
                     for d in suivi.delegations]
    e.sous_agents, e.simultanes_max = suivi.sous_agents(), suivi.simultanes_max()
    e.documents_lus = bibliotheque.lectures
    e.recherches_web = sum(1 for ev in suivi.evenements if ev["evenement"] == "outil" and ev["outil"] == "WebSearch"
                           and not ev["refuse"])
    e.hors_role = [(ev["agent_type"], ev["outil"]) for ev in suivi.evenements
                   if ev["evenement"] == "outil" and ev["hors_role"]]
    e.refus = [{"par": ev["agent_type"], "outil": ev["outil"], "entree": ev["entree"]} for ev in suivi.evenements
               if ev["evenement"] == "outil" and ev["refuse"]]
    e.rapport = bibliotheque.rapports[-1]["contenu"] if bibliotheque.rapports else ""
    texte = e.rapport + "\n" + e.reponse
    e.aspects = {nom: bool(re.search(motif, texte, re.IGNORECASE)) for nom, motif in question["aspects"].items()}
    e.transmis_au_synthetiseur = transmis_au_synthetiseur(suivi)
    return e


def resumer(etudes: list[Etude]) -> dict:
    lignes = {}
    for cle in dict.fromkeys((e.variante, e.question) for e in etudes):
        groupe = [e for e in etudes if (e.variante, e.question) == cle]
        utiles = set(QUESTIONS[cle[1]]["sous_agents_utiles"])
        lignes[f"{cle[0]}:{cle[1]}"] = {
            "etudes": len(groupe),
            "fins": [e.fin for e in groupe],
            "sous_agents_lances": [[d["type"] for d in e.delegations] for e in groupe],
            "sous_agents_inutiles": [sorted({d["type"] for d in e.delegations} - utiles) for e in groupe],
            "reponses_multi_agents": [e.reponses_multi_agents for e in groupe],
            "simultanes_max": [e.simultanes_max for e in groupe],
            "recherches_web": [e.recherches_web for e in groupe],
            "documents_lus": [e.documents_lus for e in groupe],
            "hors_role": [e.hors_role for e in groupe],
            "refus": [len(e.refus) for e in groupe],
            "aspects_couverts": [sum(e.aspects.values()) for e in groupe],
            "aspects": len(QUESTIONS[cle[1]]["aspects"]),
            "aspects_manques": [[a for a, ok in e.aspects.items() if not ok] for e in groupe],
            "rapport": [bool(e.rapport) for e in groupe],
            "resultats_par_etude": [len(e.resultats) for e in groupe],
            "cout_moyen": statistics.mean(e.cout_dollars for e in groupe),
            "latence_mediane_s": statistics.median(e.latence_s for e in groupe),
        }
    return lignes


async def lancer(ids: list[str], variantes: list[str], repetitions: int, budget_max: float,
                 attendre: bool, max_sous_agents: int, budget_etude: float) -> tuple[list[Etude], float]:
    etudes, depense = [], 0.0
    for variante in variantes:
        for repetition in range(1, repetitions + 1):
            for qid in ids:
                restant = budget_max - depense
                if restant < 0.02:
                    print(f"Arrêt avant {variante}:{qid} #{repetition} : plafond presque atteint.")
                    return etudes, depense
                prompt = PROMPTS.get(variante, PROMPTS["objectifs"])
                e = await etudier(QUESTIONS[qid], variante=variante, repetition=repetition,
                                  budget_max=min(budget_etude, restant), prompt=prompt, attendre=attendre,
                                  max_sous_agents=max_sous_agents)
                depense += e.cout_dollars
                etudes.append(e)
                print(f"{variante}:{qid} #{repetition} : {e.fin} ; sous-agents : "
                      f"{', '.join(d['type'] or '?' for d in e.delegations) or 'aucun'} ; "
                      f"simultanés au plus : {e.simultanes_max} ; aspects : {sum(e.aspects.values())}/{len(e.aspects)} ; "
                      f"{francais(e.cout_dollars, 4)} $ ; {francais(e.latence_s, 0)} s" + (f" ; {e.erreur}" if e.erreur else ""))
    return etudes, depense


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 9 : le système d'études de la souscription.")
    parser.add_argument("--questions", nargs="*", default=list(QUESTIONS))
    parser.add_argument("--variantes", nargs="*", default=["objectifs"],
                        choices=["objectifs", "procedure", "sequentiel"])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--budget-max", type=float, default=0.30, help="pour tout le lancement")
    parser.add_argument("--budget-etude", type=float, default=0.15, help="max_budget_usd de chaque étude")
    parser.add_argument("--attendre", action="store_true",
                        help="CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 : le coordinateur attend chaque sous-agent")
    parser.add_argument("--max-sous-agents", type=int, default=8)
    parser.add_argument("--fichier", default=None, help="nom du fichier de résultats")
    args = parser.parse_args()

    etudes, depense = asyncio.run(lancer(args.questions, args.variantes, args.repetitions, args.budget_max,
                                         args.attendre, args.max_sous_agents, args.budget_etude))
    resume = resumer(etudes) if etudes else {}
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense estimée par le SDK : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    nom = args.fichier or f"etudes-{'-'.join(args.variantes)}{'-attendre' if args.attendre else ''}"
    sortie = DOSSIER / "resultats" / f"{nom}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "variantes": args.variantes,
                                  "attendre": args.attendre, "depense_dollars": round(depense, 6), "resume": resume,
                                  "etudes": [asdict(e) for e in etudes]}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
