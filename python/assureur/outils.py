"""Les quatre outils de l'agent des sinistres, version 1 : leur définition et leur exécution.

Les définitions suivent le format de l'API (name, description, input_schema). La boucle écrite à
la main (ch05/boucle.py) les passe telles quelles ; la version Agent SDK (ch05/agent_sdk.py) les
enveloppe dans un serveur MCP, sans rien y changer : mêmes noms, mêmes descriptions, mêmes schémas.

Ces descriptions sont un premier jet. Le chapitre 6 les reprend, mesure à l'appui, et structure
les erreurs ; ici, une erreur est un simple message, marqué comme erreur.
"""

import json

from assureur.systeme import ErreurSysteme, Systeme

OUTILS = [
    {
        "name": "consulter_assure",
        "description": "Retrouve un assuré de Kanvô Assurances par son numéro d'assuré (KA-AS-…) ou par le "
                       "numéro d'un de ses contrats. Rend son nom, sa ville et la liste de ses contrats.",
        "input_schema": {
            "type": "object",
            "properties": {
                "numero_assure": {"type": "string", "description": "Numéro d'assuré, par exemple KA-AS-1002"},
                "numero_contrat": {"type": "string", "description": "Numéro de contrat, par exemple KA-AUTO-0193"},
            },
        },
    },
    {
        "name": "consulter_contrat",
        "description": "Lit un contrat : formule, bien assuré, statut, et pour chaque garantie si elle est "
                       "couverte, avec sa franchise et ses conditions. À consulter avant de parler des "
                       "garanties d'un assuré.",
        "input_schema": {
            "type": "object",
            "properties": {"numero_contrat": {"type": "string", "description": "Par exemple KA-HAB-0264"}},
            "required": ["numero_contrat"],
        },
    },
    {
        "name": "consulter_sinistres",
        "description": "Liste les sinistres déjà déclarés sur un contrat, ouverts ou clos : date, nature, "
                       "statut, prochaine étape, équipe en charge. Une liste vide signifie qu'aucun sinistre "
                       "n'est enregistré sur ce contrat.",
        "input_schema": {
            "type": "object",
            "properties": {"numero_contrat": {"type": "string"}},
            "required": ["numero_contrat"],
        },
    },
    {
        "name": "transmettre_a_un_gestionnaire",
        "description": "Transmet la demande à un gestionnaire, qui rappellera l'assuré. À utiliser quand "
                       "l'assuré demande à parler à quelqu'un, ou quand la demande dépasse la déclaration "
                       "d'un sinistre. Le résumé doit permettre au gestionnaire de comprendre la demande "
                       "sans relire la conversation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "motif": {"type": "string", "description": "Pourquoi la demande est transmise, en une phrase"},
                "resume": {"type": "string", "description": "Ce que veut l'assuré et ce qu'on sait déjà"},
                "numero_contrat": {"type": "string", "description": "Si on le connaît"},
            },
            "required": ["motif", "resume"],
        },
    },
]

NOMS = [o["name"] for o in OUTILS]


def executer(systeme: Systeme, nom: str, arguments: dict) -> tuple[str, bool]:
    """Exécute un outil ; rend (le résultat en JSON, True si c'est une erreur)."""
    try:
        if nom == "consulter_assure":
            resultat = systeme.consulter_assure(arguments.get("numero_assure"), arguments.get("numero_contrat"))
        elif nom == "consulter_contrat":
            resultat = systeme.consulter_contrat(arguments["numero_contrat"])
        elif nom == "consulter_sinistres":
            resultat = systeme.consulter_sinistres(arguments["numero_contrat"])
        elif nom == "transmettre_a_un_gestionnaire":
            resultat = systeme.transmettre_a_un_gestionnaire(arguments["motif"], arguments["resume"],
                                                             arguments.get("numero_contrat"))
        else:
            return f"Outil inconnu : {nom}.", True
    except ErreurSysteme as erreur:  # version 1 : le message seul, sans sa catégorie (chapitre 6)
        return str(erreur), True
    except KeyError as erreur:
        return f"Paramètre manquant : {erreur.args[0]}.", True
    return json.dumps(resultat, ensure_ascii=False), False
