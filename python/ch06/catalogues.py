"""Chapitre 6 : les variantes comparées. Une seule chose change à la fois.

- dsi : l'enveloppe livrée par la DSI (ch06/catalogue_dsi.py), avec le prompt du chapitre 5 ;
- yao : le catalogue réécrit par Yao (assureur/outils_v2.py), même prompt ;
- yao-consigne-contrat : le même catalogue, et une phrase de plus dans le prompt, demandée par la
  direction des sinistres. Elle mesure l'effet d'un mot du prompt sur le choix d'outil ;
- yao-motif-strict : le même catalogue, mais le format du numéro de sinistre imposé par le schéma
  strict (un motif) au lieu d'être vérifié par le code.
"""

import copy
import re
from dataclasses import dataclass
from typing import Callable

from assureur import outils_v2
from ch05.boucle import PROMPT
from ch06 import catalogue_dsi

CONSIGNE_CONTRAT = "Avant de répondre, vérifiez toujours le contrat de l'assuré."

# La réponse dit qu'il n'existe pas de dossier : une fausse conclusion si le dossier existe.
INTROUVABLE = re.compile(r"aucun (dossier|sinistre)|pas de (dossier|sinistre)|(n'ai|ne trouve) (pas|aucun|trouvé aucun)"
                         r"|introuvable|n'existe pas", re.IGNORECASE)


@dataclass(frozen=True)
class Variante:
    nom: str
    famille: str          # « dsi » ou « yao » : la clé des outils attendus dans les demandes
    outils: list
    executer: Callable
    prompt: str


def _avec_motif_strict() -> list:
    outils = copy.deepcopy(outils_v2.OUTILS)
    for outil in outils:
        if outil["name"] == "consulter_sinistre":
            outil["input_schema"]["properties"]["numero_sinistre"]["pattern"] = r"^SIN-\d{4}-\d{4}$"
    return outils


VARIANTES = {v.nom: v for v in [
    Variante("dsi", "dsi", catalogue_dsi.OUTILS, catalogue_dsi.executer, PROMPT),
    Variante("yao", "yao", outils_v2.OUTILS, outils_v2.executer, PROMPT),
    Variante("yao-consigne-contrat", "yao", outils_v2.OUTILS, outils_v2.executer,
             PROMPT.rstrip() + "\n\n" + CONSIGNE_CONTRAT + "\n"),
    Variante("yao-motif-strict", "yao", _avec_motif_strict(), outils_v2.executer, PROMPT),
]}


def premier_appel(conduite) -> list[str]:
    """Les outils demandés dans la première réponse qui en demande ; [] si aucun outil n'est appelé."""
    return next((t.outils for t in conduite.tours if t.outils), [])


def premier_juste(premier: list[str], attendus: list[str]) -> bool:
    return ("aucun" in attendus) if not premier else any(o in attendus for o in premier)
