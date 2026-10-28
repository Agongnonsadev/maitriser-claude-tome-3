"""Chapitre 9 : le suivi et les bornes du système d'études, par les hooks de l'Agent SDK.

Le suivi note chaque événement avec son heure : chaque appel d'outil, et par qui (le coordinateur ou
tel sous-agent : le champ agent_id des hooks est le seul moyen fiable de les distinguer quand ils
tournent en parallèle), chaque début et chaque fin de sous-agent. On en tire la chronologie : qui a
travaillé, combien de temps, en même temps ou l'un après l'autre.

Les bornes sont imposées par le code, comme au chapitre 8 :
- le coordinateur ne fait que déléguer : tout autre outil lui est refusé ;
- il lance au plus `max_sous_agents` sous-agents par étude, et seulement ceux du système ;
- un sous-agent n'utilise que les outils de sa définition ;
- le chercheur web fait au plus `max_recherches` recherches.
Chaque refus dit à Claude quoi faire à la place.
"""

import json
import time
from collections import Counter

from ch09.sous_agents import OUTILS_DU_ROLE

AGENT = ("Agent", "Task")  # « Task » : l'ancien nom de l'outil, celui du guide d'examen


def _refus(raison: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": raison}}


def _abrege(valeur, longueur: int = 300):
    texte = valeur if isinstance(valeur, str) else json.dumps(valeur, ensure_ascii=False)
    return texte if len(texte) <= longueur else texte[:longueur] + "…"


class Suivi:
    def __init__(self, definitions: dict, max_sous_agents: int = 8, max_recherches: int = 4):
        self.definitions = definitions
        self.max_sous_agents, self.max_recherches = max_sous_agents, max_recherches
        self.debut = time.perf_counter()
        self.evenements: list[dict] = []
        self.delegations: list[dict] = []        # chaque appel de l'outil Agent, prompt complet
        self.types: dict[str, str] = {}          # agent_id -> type de sous-agent
        self.recherches: Counter = Counter()     # agent_id -> recherches web

    def _noter(self, evenement: str, **details) -> None:
        self.evenements.append({"t": round(time.perf_counter() - self.debut, 2), "evenement": evenement, **details})

    async def avant_outil(self, entree, tool_use_id, contexte) -> dict:
        outil, agent_id = entree["tool_name"], entree.get("agent_id")
        agent_type = entree.get("agent_type") or self.types.get(agent_id or "")
        refus = None
        if agent_id is None:                         # le coordinateur
            if outil not in AGENT:
                refus = (f"Vous coordonnez : vous n'utilisez pas {outil} vous-même. Déléguez à un sous-agent "
                         "par l'outil Agent, en écrivant dans son prompt tout ce dont il a besoin.")
            else:
                type_demande = entree["tool_input"].get("subagent_type")
                lances = len(self.delegations)
                if type_demande not in self.definitions:
                    refus = (f"Le sous-agent « {type_demande} » n'existe pas dans ce système. Choisissez parmi : "
                             f"{', '.join(self.definitions)}.")
                elif lances >= self.max_sous_agents:
                    refus = (f"Plafond de {self.max_sous_agents} sous-agents atteint pour cette étude. Terminez avec "
                             "les résultats obtenus, et dites ce qui reste à couvrir.")
                else:
                    self.delegations.append({"t": round(time.perf_counter() - self.debut, 2),
                                             "tool_use_id": tool_use_id, **entree["tool_input"]})
        else:                                        # un sous-agent
            permis = set(self.definitions[agent_type].tools or []) if agent_type in self.definitions else set()
            if outil not in permis:
                refus = f"L'outil {outil} n'est pas dans votre rôle. Rendez vos résultats avec vos seuls outils."
            elif outil == "WebSearch":
                self.recherches[agent_id] += 1
                if self.recherches[agent_id] > self.max_recherches:
                    refus = (f"Plafond de {self.max_recherches} recherches atteint. Rendez maintenant vos résultats, "
                             "et dites ce que vous n'avez pas trouvé.")
        hors_role = agent_id is not None and outil not in OUTILS_DU_ROLE.get(agent_type, set())
        self._noter("outil", agent_id=agent_id, agent_type=agent_type or "coordinateur", outil=outil,
                    entree=_abrege(entree["tool_input"]), refuse=bool(refus), hors_role=hors_role,
                    tool_use_id=tool_use_id)
        return _refus(refus) if refus else {}

    async def apres_outil(self, entree, tool_use_id, contexte) -> dict:
        if entree["tool_name"] in AGENT:
            self._noter("retour_agent", tool_use_id=tool_use_id, reponse=_abrege(entree.get("tool_response"), 2000))
        return {}

    async def debut_sous_agent(self, entree, tool_use_id, contexte) -> dict:
        self.types[entree["agent_id"]] = entree["agent_type"]
        self._noter("debut", agent_id=entree["agent_id"], agent_type=entree["agent_type"])
        return {}

    async def fin_sous_agent(self, entree, tool_use_id, contexte) -> dict:
        self._noter("fin", agent_id=entree["agent_id"], agent_type=entree["agent_type"],
                    dernier_message=entree.get("last_assistant_message") or "")
        return {}

    # Ce que la chronologie permet de dire.

    def sous_agents(self) -> list[dict]:
        """Chaque sous-agent lancé : type, début, fin, durée, outils appelés."""
        lignes = {}
        for e in self.evenements:
            if e["evenement"] == "debut":
                lignes[e["agent_id"]] = {"agent_id": e["agent_id"], "type": e["agent_type"], "debut": e["t"],
                                         "fin": None, "outils": [], "dernier_message": ""}
            elif e["evenement"] == "fin" and e["agent_id"] in lignes:
                lignes[e["agent_id"]].update(fin=e["t"], dernier_message=e["dernier_message"])
            elif e["evenement"] == "outil" and e.get("agent_id") in lignes:
                lignes[e["agent_id"]]["outils"].append(e["outil"] + (" (refusé)" if e["refuse"] else ""))
        for ligne in lignes.values():
            ligne["duree"] = round(ligne["fin"] - ligne["debut"], 2) if ligne["fin"] is not None else None
        return list(lignes.values())

    def simultanes_max(self) -> int:
        """Le plus grand nombre de sous-agents au travail en même temps."""
        en_cours, maximum = 0, 0
        for e in self.evenements:
            if e["evenement"] == "debut":
                en_cours += 1
                maximum = max(maximum, en_cours)
            elif e["evenement"] == "fin":
                en_cours -= 1
        return maximum
