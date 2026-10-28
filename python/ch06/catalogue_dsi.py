"""Chapitre 6 : l'enveloppe livrée par la DSI de Kanvô Assurances, telle quelle (fictive).

La DSI a exposé son ancien logiciel en cinq outils, sur le modèle de ses écrans :
- deux recherches au texte libre, rechercher_client et rechercher_dossier. Dans le métier, « dossier »
  désigne aussi bien le dossier d'un client que le dossier d'un sinistre : c'est la confusion que
  le chapitre mesure. rechercher_dossier ne trouve que des sinistres (par numéro de sinistre ou de
  contrat) ;
- des descriptions d'une ligne ;
- un outil hors du rôle de l'agent : resilier_contrat, exposé pour l'agence ;
- une gestion d'erreurs fréquente dans les enveloppes vite écrites : une recherche qui échoue
  rend une liste vide, et toute autre erreur le seul mot « Erreur ».

Ce catalogue sert de point de départ et de contre-exemple. Ne le copiez pas.
"""

import json
import re

from assureur.systeme import ErreurSysteme, Systeme

OUTILS = [
    {"name": "rechercher_client", "description": "Recherche un client.",
     "input_schema": {"type": "object", "properties": {"requete": {"type": "string"}}, "required": ["requete"]}},
    {"name": "rechercher_dossier", "description": "Recherche un dossier.",
     "input_schema": {"type": "object", "properties": {"requete": {"type": "string"}}, "required": ["requete"]}},
    {"name": "consulter_contrat", "description": "Consulte un contrat.",
     "input_schema": {"type": "object", "properties": {"numero": {"type": "string"}}, "required": ["numero"]}},
    {"name": "resilier_contrat", "description": "Résilie un contrat.",
     "input_schema": {"type": "object", "properties": {"numero": {"type": "string"}, "motif": {"type": "string"}},
                      "required": ["numero", "motif"]}},
    {"name": "creer_ticket", "description": "Crée un ticket pour un gestionnaire.",
     "input_schema": {"type": "object", "properties": {"objet": {"type": "string"}, "description": {"type": "string"}},
                      "required": ["objet", "description"]}},
]

NOMS = [o["name"] for o in OUTILS]
RECHERCHES = {"rechercher_client", "rechercher_dossier"}


def _rechercher_client(systeme: Systeme, requete: str) -> list[dict]:
    texte = requete.strip().upper().replace(" ", "")
    if re.match(r"^KA-AS-\d{4}$", texte):
        return [systeme.consulter_assure(numero_assure=texte)]
    if re.match(r"^KA-[A-Z]+-\d{4}$", texte):
        return [systeme.consulter_assure(numero_contrat=texte)]
    return systeme.rechercher_assures(requete)


def _rechercher_dossier(systeme: Systeme, requete: str) -> list[dict]:
    texte = requete.strip().upper().replace(" ", "")
    if re.match(r"^SIN-\d{4}-\d{4}$", texte):
        return [systeme.consulter_sinistre(texte)]
    if re.match(r"^KA-(AUTO|HAB|SANTE)-\d{4}$", texte):
        return systeme.consulter_sinistres(texte)
    return []  # ni un numéro de sinistre, ni un numéro de contrat : rien


def executer(systeme: Systeme, nom: str, arguments: dict) -> tuple[str, bool]:
    try:
        if nom == "rechercher_client":
            resultat = _rechercher_client(systeme, arguments["requete"])
        elif nom == "rechercher_dossier":
            resultat = _rechercher_dossier(systeme, arguments["requete"])
        elif nom == "consulter_contrat":
            resultat = systeme.consulter_contrat(arguments["numero"])
        elif nom == "resilier_contrat":
            resultat = systeme.resilier_contrat(arguments["numero"], arguments.get("motif", ""))
        elif nom == "creer_ticket":
            resultat = systeme.transmettre_a_un_gestionnaire(arguments.get("objet", ""), arguments.get("description", ""))
        else:
            return "Erreur.", True
    except (ErreurSysteme, KeyError):
        if nom in RECHERCHES:
            return "[]", False  # le défaut à ne pas reproduire : un échec déguisé en résultat vide
        return "Erreur.", True
    return json.dumps(resultat, ensure_ascii=False), False
