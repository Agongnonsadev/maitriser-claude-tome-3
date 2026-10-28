"""Le serveur MCP du système de gestion de Kanvô Assurances (fictif) : le catalogue du chapitre 6, servi par MCP.

- Les cinq outils de assureur/outils_v2.py : mêmes noms, mêmes descriptions, mêmes erreurs structurées,
  levées en ToolError (le client reçoit un résultat marqué isError, dont le texte est l'erreur en JSON).
- Une ressource, kanvo://referentiel : les numéros, le modèle de données et le vocabulaire du système.
  Les instructions du serveur la signalent au client.
- Les droits. Le serveur lit le jeton du compte de service dans KANVO_JETON, jamais dans un fichier du
  dépôt, et retrouve ses portées dans le registre de la DSI (KANVO_JETONS, des empreintes seulement).
  Il n'expose que les outils que ces portées permettent, et vérifie la portée à chaque appel.
- Chaque appel est noté dans le journal d'audit (KANVO_AUDIT) : compte, outil, issue. Pas les données.

Deux réglages servent aux mesures du chapitre 7 : KANVO_DESCRIPTIONS=courtes remplace les descriptions
par une ligne, KANVO_RESSOURCE=non retire le référentiel.

Lancement, en stdio :  python -m assureur.serveur_mcp
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from assureur import jetons, outils_v2
from assureur.systeme import Systeme

VERSION = "0.7.0"
PORTEE = {
    "trouver_assure": "sinistres:lecture",
    "consulter_contrat": "sinistres:lecture",
    "lister_sinistres_du_contrat": "sinistres:lecture",
    "consulter_sinistre": "sinistres:lecture",
    "transmettre_a_un_gestionnaire": "transmissions:ecriture",
}
DESCRIPTIONS = {
    "riches": {o["name"]: o["description"] for o in outils_v2.OUTILS},
    "courtes": {  # ce qu'on écrit quand on va vite : la variante mesurée au chapitre 7
        "trouver_assure": "Trouve un assuré.",
        "consulter_contrat": "Consulte un contrat.",
        "lister_sinistres_du_contrat": "Liste des sinistres.",
        "consulter_sinistre": "Consulte un sinistre.",
        "transmettre_a_un_gestionnaire": "Transmet à un gestionnaire.",
    },
}
REFERENTIEL = """# Référentiel du système de gestion de Kanvô Assurances (fictif)

## Les numéros
- Assuré : KA-AS- suivi de 4 chiffres (KA-AS-1002).
- Contrat : KA-AUTO-, KA-HAB- ou KA-SANTE- suivi de 4 chiffres (KA-HAB-0264).
- Sinistre : SIN-, l'année sur 4 chiffres, un tiret, 4 chiffres (SIN-2026-0912).

## Les données
- Un assuré : numéro, nom, ville, liste de ses contrats.
- Un contrat : numéro, assuré, type (automobile, habitation, santé), formule, statut (actif, suspendu,
  résilié), garanties (couverte ou non, franchise, conditions).
- Un sinistre : numéro, contrat, date, nature, statut, prochaine étape, équipe en charge.

## Les statuts d'un sinistre
- déclaré : enregistré, pas encore étudié.
- expertise planifiée : un expert doit passer ; la date est dans la prochaine étape.
- rapport d'expertise reçu : le gestionnaire étudie le rapport.
- en attente de pièces : le dossier attend un document de l'assuré, nommé dans la prochaine étape.
- clos : traité.
- archivé : clos depuis plus de cinq ans ; seul un gestionnaire peut le rouvrir et le consulter.

## Les équipes
- Équipe automobile 1 et 2, équipe habitation : les sinistres auto et habitation.
- Équipe santé : les contrats santé, hors des droits des comptes de service des sinistres.

## Les erreurs des outils
Catégories passagere (réessayer une fois), validation (faire vérifier le numéro), metier (expliquer,
transmettre) et permission (expliquer, transmettre). Chaque erreur porte un conseil pour la suite.
"""


def _instructions(ressource: bool) -> str:
    texte = "Système de gestion de Kanvô Assurances (fictif) : assurés, contrats, sinistres, en direct."
    if ressource:
        texte += (" Le référentiel kanvo://referentiel décrit les numéros, les données, les statuts et les équipes : "
                  "lisez-le plutôt que d'explorer.")
    return texte


def _audit(chemin: str | None, compte: str, outil: str, issue: str) -> None:
    if not chemin:
        return
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "compte": compte,
                            "outil": outil, "issue": issue}, ensure_ascii=False) + "\n")


def construire(compte: str, portees: set[str], descriptions: str = "riches", ressource: bool = True,
               systeme: Systeme | None = None, audit: str | None = None) -> MCPServer:
    """Le serveur d'un compte : seuls les outils de ses portées existent pour lui."""
    systeme = systeme or Systeme()
    serveur = MCPServer("kanvo", title="Kanvô Assurances (fictif)", version=VERSION,
                        instructions=_instructions(ressource))

    def appeler(outil: str, **arguments) -> str:
        if PORTEE[outil] not in portees:  # défense en profondeur : l'outil n'est pas listé, mais on revérifie
            _audit(audit, compte, outil, "refusé")
            raise ToolError(outils_v2.erreur("permission", False, f"Le compte {compte} n'a pas la portée {PORTEE[outil]}.",
                                             "Ne réessayez pas ; transmettez avec le motif acces_refuse.")[0])
        texte, est_erreur = outils_v2.executer(systeme, outil, {k: v for k, v in arguments.items() if v is not None})
        _audit(audit, compte, outil, "erreur" if est_erreur else "ok")
        if est_erreur:
            raise ToolError(texte)
        return texte

    def trouver_assure(
        numero_assure: Annotated[str | None, Field(description="Par exemple KA-AS-1002")] = None,
        numero_contrat: Annotated[str | None, Field(description="Par exemple KA-AUTO-0193")] = None,
        nom: Annotated[str | None, Field(description="Nom ou prénom et nom, tels que l'assuré les donne")] = None,
    ) -> str:
        return appeler("trouver_assure", numero_assure=numero_assure, numero_contrat=numero_contrat, nom=nom)

    def consulter_contrat(numero_contrat: Annotated[str, Field(description="Par exemple KA-HAB-0264")]) -> str:
        return appeler("consulter_contrat", numero_contrat=numero_contrat)

    def lister_sinistres_du_contrat(numero_contrat: Annotated[str, Field(description="Par exemple KA-AUTO-1180")]) -> str:
        return appeler("lister_sinistres_du_contrat", numero_contrat=numero_contrat)

    def consulter_sinistre(numero_sinistre: Annotated[str, Field(description="Tel que l'assuré l'a écrit")]) -> str:
        return appeler("consulter_sinistre", numero_sinistre=numero_sinistre)

    def transmettre_a_un_gestionnaire(
        motif: Literal["demande_d_un_humain", "hors_perimetre", "systeme_indisponible", "acces_refuse",
                       "dossier_archive"],
        resume: Annotated[str, Field(description="Ce que veut l'assuré, ses numéros, ce qui est déjà vérifié")],
        numero_contrat: Annotated[str | None, Field(description="Si on le connaît")] = None,
    ) -> str:
        return appeler("transmettre_a_un_gestionnaire", motif=motif, resume=resume, numero_contrat=numero_contrat)

    lecture = ToolAnnotations(read_only_hint=True, open_world_hint=False)
    ecriture = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False,
                               open_world_hint=False)
    for fn in (trouver_assure, consulter_contrat, lister_sinistres_du_contrat, consulter_sinistre,
               transmettre_a_un_gestionnaire):
        if PORTEE[fn.__name__] in portees:
            serveur.add_tool(fn, name=fn.__name__, description=DESCRIPTIONS[descriptions][fn.__name__],
                             annotations=lecture if PORTEE[fn.__name__].endswith(":lecture") else ecriture,
                             structured_output=False)

    if ressource:
        @serveur.resource("kanvo://referentiel", name="referentiel", title="Référentiel du système de gestion",
                          description="Les numéros, le modèle de données, les statuts et les équipes de Kanvô "
                                      "Assurances.", mime_type="text/markdown")
        def referentiel() -> str:
            _audit(audit, compte, "kanvo://referentiel", "lu")
            return REFERENTIEL

    return serveur


def principal() -> None:
    identite = jetons.identifier(os.environ.get("KANVO_JETON"), Path(os.environ.get("KANVO_JETONS", "")))
    if identite is None:
        print("Jeton absent ou inconnu : réglez KANVO_JETON et KANVO_JETONS (chapitre 7).", file=sys.stderr)
        sys.exit(1)
    compte, portees = identite
    construire(compte, portees, descriptions=os.environ.get("KANVO_DESCRIPTIONS", "riches"),
               ressource=os.environ.get("KANVO_RESSOURCE", "oui") != "non",
               audit=os.environ.get("KANVO_AUDIT")).run("stdio")


if __name__ == "__main__":
    principal()
