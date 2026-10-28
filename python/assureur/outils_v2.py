"""Les outils de l'agent des sinistres, version 2 : le catalogue réécrit par Yao au chapitre 6.

Ce qui change par rapport à l'enveloppe livrée par la DSI (ch06/catalogue_dsi.py) :
- un outil par question, au nom précis : on ne « recherche » plus un « dossier » qui peut être
  celui de l'assuré ou celui d'un sinistre ;
- des descriptions qui disent ce que fait l'outil, quand s'en servir et quand ne pas s'en servir,
  les formats attendus, ce qu'il ne rend pas, et la frontière avec son voisin ;
- des entrées contraintes (strict: true, motif choisi dans une liste) plutôt qu'un texte libre ;
- des erreurs structurées : catégorie, réessayable ou non, conseil pour la suite. Une erreur n'est
  jamais déguisée en résultat vide, et un résultat vide valide est dit comme tel ;
- aucun outil hors du rôle : la résiliation reste à l'agence.

Les formats des numéros sont décrits dans le texte et vérifiés par le code, pas imposés par le
schéma : un schéma strict avec un motif obligerait Claude à produire un numéro bien formé, même
quand l'assuré en a donné un faux (voir ch06/erreurs.py, réglage « motif-strict »).
"""

import json
import re

from assureur.systeme import Indisponible, Interdit, Introuvable, RegleMetier, Systeme

FORMATS = {
    "numero_assure": (r"^KA-AS-\d{4}$", "KA-AS- suivi de 4 chiffres"),
    "numero_contrat": (r"^KA-(AUTO|HAB|SANTE)-\d{4}$", "KA-AUTO-, KA-HAB- ou KA-SANTE- suivi de 4 chiffres"),
    "numero_sinistre": (r"^SIN-\d{4}-\d{4}$", "SIN-AAAA-NNNN"),
}

MOTIFS = ["demande_d_un_humain", "hors_perimetre", "systeme_indisponible", "acces_refuse", "dossier_archive"]


def _objet(proprietes: dict, requis: list[str]) -> dict:
    return {"type": "object", "properties": proprietes, "required": requis, "additionalProperties": False}


OUTILS = [
    {
        "name": "trouver_assure",
        "description": (
            "Retrouve un assuré de Kanvô Assurances et la liste de ses contrats. Donnez un seul critère : son "
            "numéro d'assuré (KA-AS- suivi de 4 chiffres), le numéro d'un de ses contrats, ou son nom. "
            "Utilisez-le en premier quand l'assuré se présente par son nom ou son numéro d'assuré, ou parle de "
            "« son dossier » sans numéro de sinistre : il donne les numéros de contrat dont les autres outils "
            "ont besoin. Il ne rend ni les garanties (consulter_contrat) ni les sinistres "
            "(lister_sinistres_du_contrat). Un nom peut désigner plusieurs assurés : demandez alors un numéro."),
        "strict": True,
        "input_schema": _objet({
            "numero_assure": {"type": "string", "description": "Par exemple KA-AS-1002"},
            "numero_contrat": {"type": "string", "description": "Par exemple KA-AUTO-0193"},
            "nom": {"type": "string", "description": "Nom ou prénom et nom, tels que l'assuré les donne"},
        }, []),
    },
    {
        "name": "consulter_contrat",
        "description": (
            "Lit un contrat : formule, bien assuré, statut, et pour chaque garantie si elle est couverte, avec sa "
            "franchise et ses conditions. Prend un numéro de contrat (KA-AUTO-, KA-HAB- ou KA-SANTE- suivi de "
            "4 chiffres), jamais un numéro d'assuré ni un numéro de sinistre. À consulter avant de dire à "
            "l'assuré ce que son contrat couvre. Il ne dit rien des sinistres déjà déclarés. Les contrats santé "
            "sont réservés à l'équipe santé : l'outil renvoie alors une erreur de permission."),
        "strict": True,
        "input_schema": _objet({"numero_contrat": {"type": "string", "description": "Par exemple KA-HAB-0264"}},
                               ["numero_contrat"]),
    },
    {
        "name": "lister_sinistres_du_contrat",
        "description": (
            "Liste les dossiers de sinistre (SIN-AAAA-NNNN) déclarés sur un contrat, ouverts, clos ou archivés : "
            "date, nature, statut, prochaine étape, équipe en charge. Prend un numéro de contrat. Si l'assuré ne "
            "donne que son numéro d'assuré ou son nom, trouvez d'abord ses contrats avec trouver_assure. Une "
            "liste vide est un résultat valide : aucun sinistre n'est enregistré sur ce contrat. Une erreur, "
            "elle, ne veut jamais dire qu'il n'y a aucun sinistre."),
        "strict": True,
        "input_schema": _objet({"numero_contrat": {"type": "string", "description": "Par exemple KA-AUTO-1180"}},
                               ["numero_contrat"]),
    },
    {
        "name": "consulter_sinistre",
        "description": (
            "Lit un dossier de sinistre par son numéro, de la forme SIN-AAAA-NNNN (par exemple SIN-2026-0912) : "
            "contrat, date, nature, statut, prochaine étape, équipe en charge. Utilisez-le quand l'assuré cite un "
            "numéro de sinistre ; sans numéro, passez par lister_sinistres_du_contrat. Recopiez le numéro tel "
            "que l'assuré l'a donné : s'il est mal formé, l'outil le dit, et il faut demander à l'assuré de le "
            "vérifier, sans le corriger vous-même."),
        "strict": True,
        "input_schema": _objet({"numero_sinistre": {"type": "string", "description": "Tel que l'assuré l'a écrit"}},
                               ["numero_sinistre"]),
    },
    {
        "name": "transmettre_a_un_gestionnaire",
        "description": (
            "Transmet la demande à un gestionnaire, qui rappellera l'assuré. Choisissez le motif dans la liste : "
            "l'assuré demande à parler à quelqu'un (demande_d_un_humain) ; la demande sort des sinistres auto et "
            "habitation, comme une résiliation ou une souscription (hors_perimetre) ; le système ne répond "
            "toujours pas après une nouvelle tentative (systeme_indisponible) ; un accès est refusé "
            "(acces_refuse) ; le dossier est archivé (dossier_archive). Le résumé doit permettre au gestionnaire "
            "de comprendre la demande sans relire la conversation : qui, quoi, quels numéros, ce qui a déjà été "
            "vérifié."),
        "strict": True,
        "input_schema": _objet({
            "motif": {"type": "string", "enum": MOTIFS},
            "resume": {"type": "string", "description": "Ce que veut l'assuré, ses numéros, ce qui est déjà vérifié"},
            "numero_contrat": {"type": "string", "description": "Si on le connaît"},
        }, ["motif", "resume"]),
    },
]

NOMS = [o["name"] for o in OUTILS]


def erreur(categorie: str, reessayable: bool, detail: str, conseil: str) -> tuple[str, bool]:
    """Une erreur structurée : ce que Claude doit savoir pour choisir la suite, et quoi dire à l'assuré."""
    return json.dumps({"erreur": {"categorie": categorie, "reessayable": reessayable, "detail": detail,
                                  "conseil": conseil}}, ensure_ascii=False), True


def _verifier(champ: str, valeur: str) -> tuple[str, bool] | None:
    motif, forme = FORMATS[champ]
    if not re.match(motif, valeur.strip().upper().replace(" ", "")):
        return erreur("validation", False, f"« {valeur} » n'a pas la forme attendue ({forme}).",
                      "Demandez à l'assuré de vérifier ce numéro. Ne le corrigez pas vous-même.")
    return None


def executer(systeme: Systeme, nom: str, arguments: dict) -> tuple[str, bool]:
    """Exécute un outil ; rend (le résultat en JSON, True si c'est une erreur)."""
    for champ in FORMATS:
        if arguments.get(champ) and (probleme := _verifier(champ, arguments[champ])):
            return probleme
    try:
        if nom == "trouver_assure":
            criteres = [c for c in ("numero_assure", "numero_contrat", "nom") if arguments.get(c)]
            if len(criteres) != 1:
                return erreur("validation", False, "Donnez exactement un critère : numéro d'assuré, numéro de "
                              "contrat ou nom.", "Reformulez l'appel avec un seul critère.")
            if arguments.get("nom"):
                assures = systeme.rechercher_assures(arguments["nom"])
                resultat = {"assures": assures, "note": None if assures else "Aucun assuré ne porte ce nom."}
            else:
                resultat = {"assures": [systeme.consulter_assure(arguments.get("numero_assure"),
                                                                 arguments.get("numero_contrat"))]}
        elif nom == "consulter_contrat":
            resultat = systeme.consulter_contrat(arguments["numero_contrat"])
        elif nom == "lister_sinistres_du_contrat":
            sinistres = systeme.consulter_sinistres(arguments["numero_contrat"])
            resultat = {"sinistres": sinistres,
                        "note": None if sinistres else "Aucun sinistre n'est enregistré sur ce contrat."}
        elif nom == "consulter_sinistre":
            resultat = systeme.consulter_sinistre(arguments["numero_sinistre"])
        elif nom == "transmettre_a_un_gestionnaire":
            resultat = systeme.transmettre_a_un_gestionnaire(arguments["motif"], arguments["resume"],
                                                             arguments.get("numero_contrat"))
        else:
            return erreur("validation", False, f"Outil inconnu : {nom}.", "Utilisez un des outils fournis.")
    except Introuvable as e:
        return erreur("validation", False, str(e), "Demandez à l'assuré de vérifier ce numéro.")
    except Indisponible as e:
        return erreur("passagere", True, str(e),
                      "Réessayez une fois. Si l'erreur revient, dites à l'assuré que le système est momentanément "
                      "indisponible et transmettez avec le motif systeme_indisponible. N'en concluez pas qu'il "
                      "n'existe aucun dossier.")
    except Interdit as e:
        return erreur("permission", False, str(e),
                      "Ne réessayez pas. Dites à l'assuré que sa demande relève d'une autre équipe et transmettez "
                      "avec le motif acces_refuse.")
    except RegleMetier as e:
        return erreur("metier", False, str(e),
                      "Ne réessayez pas. Expliquez la situation à l'assuré et transmettez avec le motif "
                      "dossier_archive.")
    return json.dumps(resultat, ensure_ascii=False), False
