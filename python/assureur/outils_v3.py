"""Les outils de l'agent des sinistres, version 3 : le catalogue du chapitre 6, et ce qu'ajoute le chapitre 8.

- verifier_identite : oui ou non, à partir du numéro d'assuré et de la date de naissance ;
- calculer_reglement : le barème de l'ancien logiciel. Il répond dans ses vieux formats (montants en
  texte, date en secondes depuis 1970) : un hook PostToolUse les normalise avant que Claude les lise ;
- declencher_reglement_rapide : le règlement d'un sinistre évalué. L'ancien point d'entrée paie le montant
  qu'on lui donne ; ce sont les hooks du chapitre 8 qui garantissent les règles ;
- transmettre_a_un_gestionnaire, version 3 : le relais est structuré, champ par champ, pour un gestionnaire
  qui n'a pas la conversation sous les yeux.
"""

import json

from assureur import outils_v2
from assureur.outils_v2 import _objet, erreur
from assureur.systeme import Indisponible, Interdit, Introuvable, RegleMetier, Systeme

PLAFOND_FCFA = 150_000  # le règlement rapide de l'agent ; au-delà, un gestionnaire décide
MOTIFS = outils_v2.MOTIFS + ["plafond_depasse", "identite_non_verifiee"]
DATE_DU_CALCUL = 1793145600  # le 28 octobre 2026, en secondes depuis 1970 : le format de l'ancien barème


def _texte_ou_rien(description: str) -> dict:
    return {"type": ["string", "null"], "description": description}


TRANSMETTRE = {
    "name": "transmettre_a_un_gestionnaire",
    "description": (
        "Transmet la demande à un gestionnaire, qui rappellera l'assuré. Choisissez le motif dans la liste : "
        "l'assuré demande à parler à quelqu'un (demande_d_un_humain) ; la demande sort des sinistres auto et "
        "habitation (hors_perimetre) ; le système ne répond toujours pas (systeme_indisponible) ; un accès est "
        "refusé (acces_refuse) ; le dossier est archivé (dossier_archive) ; le règlement dépasse le plafond de "
        "l'agent (plafond_depasse) ; l'identité de l'assuré n'a pas pu être vérifiée (identite_non_verifiee). "
        "Le gestionnaire n'a pas la conversation : remplissez chaque champ, avec null quand une information "
        "manque, et recommandez une action précise."),
    "strict": True,
    "input_schema": _objet({
        "motif": {"type": "string", "enum": MOTIFS},
        "numero_assure": _texte_ou_rien("KA-AS-…, si on le connaît"),
        "numero_contrat": _texte_ou_rien("Si on le connaît"),
        "numero_sinistre": _texte_ou_rien("SIN-AAAA-NNNN, si on le connaît"),
        "montant_en_jeu_fcfa": {"type": ["integer", "null"], "description": "Le montant en cause, s'il y en a un"},
        "demande_de_l_assure": {"type": "string", "description": "Ce que veut l'assuré, en une ou deux phrases"},
        "deja_verifie": {"type": "array", "items": {"type": "string"},
                         "description": "Ce que l'agent a déjà vérifié, et le résultat"},
        "action_recommandee": {"type": "string", "description": "Ce que le gestionnaire devrait faire"},
    }, ["motif", "numero_assure", "numero_contrat", "numero_sinistre", "montant_en_jeu_fcfa",
        "demande_de_l_assure", "deja_verifie", "action_recommandee"]),
}

NOUVEAUX = [
    {
        "name": "verifier_identite",
        "description": (
            "Vérifie l'identité d'un assuré : son numéro d'assuré (KA-AS- suivi de 4 chiffres) et sa date de "
            "naissance, telle qu'il la donne (AAAA-MM-JJ ou JJ/MM/AAAA). Répond seulement oui ou non : l'outil ne "
            "révèle jamais la bonne date. Obligatoire avant tout règlement. Un proche qui écrit pour l'assuré "
            "n'est pas l'assuré : sans les informations de l'assuré lui-même, l'identité n'est pas vérifiée."),
        "strict": True,
        "input_schema": _objet({"numero_assure": {"type": "string"}, "date_naissance": {"type": "string"}},
                               ["numero_assure", "date_naissance"]),
    },
    {
        "name": "calculer_reglement",
        "description": (
            "Calcule le règlement d'un sinistre évalué, par le barème du système : montant évalué, franchise de la "
            "garantie, montant à verser. Prend un numéro de sinistre. Ne verse rien. Le montant à verser est le "
            "seul qu'on puisse régler : ni l'agent ni l'assuré ne le modifient."),
        "strict": True,
        "input_schema": _objet({"numero_sinistre": {"type": "string"}}, ["numero_sinistre"]),
    },
    {
        "name": "declencher_reglement_rapide",
        "description": (
            f"Déclenche le virement du règlement d'un sinistre évalué. Seulement après verifier_identite réussi pour "
            f"l'assuré du sinistre, pour le montant exact rendu par calculer_reglement, et jusqu'à "
            f"{PLAFOND_FCFA:,} FCFA. Au-delà, ou si l'identité n'est pas vérifiée, transmettez à un gestionnaire. "
            "Irréversible : le virement part.").replace(",", " "),
        "strict": True,
        "input_schema": _objet({"numero_sinistre": {"type": "string"}, "montant_fcfa": {"type": "integer"}},
                               ["numero_sinistre", "montant_fcfa"]),
    },
]

OUTILS = [o for o in outils_v2.OUTILS if o["name"] != "transmettre_a_un_gestionnaire"] + NOUVEAUX + [TRANSMETTRE]
NOMS = [o["name"] for o in OUTILS]


def _francs(n: int) -> str:
    return f"{n:,}".replace(",", " ") + ",00 FCFA"


def executer(systeme: Systeme, nom: str, arguments: dict) -> tuple[str, bool]:
    try:
        if nom == "verifier_identite":
            return json.dumps(systeme.verifier_identite(arguments["numero_assure"], arguments["date_naissance"]),
                              ensure_ascii=False), False
        if nom == "calculer_reglement":
            r = systeme.calculer_reglement(arguments["numero_sinistre"])
            # Les formats de l'ancien barème, tels quels : du texte, des points, des secondes depuis 1970.
            return json.dumps({"sinistre": r["numero_sinistre"], "montant_evalue": _francs(r["montant_evalue_fcfa"]),
                               "franchise": f"{r['franchise_fcfa']:,}".replace(",", "."), "a_verser": r["a_verser_fcfa"],
                               "date_calcul": DATE_DU_CALCUL}, ensure_ascii=False), False
        if nom == "declencher_reglement_rapide":
            return json.dumps(systeme.declencher_reglement_rapide(arguments["numero_sinistre"], arguments["montant_fcfa"]),
                              ensure_ascii=False), False
        if nom == "transmettre_a_un_gestionnaire":
            relais = {k: v for k, v in arguments.items() if k != "motif"}
            t = systeme.transmettre_a_un_gestionnaire(arguments["motif"], json.dumps(relais, ensure_ascii=False),
                                                      arguments.get("numero_contrat"))
            t["relais"] = relais
            systeme.transmissions[-1]["relais"] = relais
            return json.dumps({"numero": t["numero"], "suite": t["suite"]}, ensure_ascii=False), False
    except Introuvable as e:
        return erreur("validation", False, str(e), "Demandez à l'assuré de vérifier ce numéro.")
    except Indisponible as e:
        return erreur("passagere", True, str(e), "Réessayez une fois ; sinon, transmettez avec le motif "
                      "systeme_indisponible. N'en concluez rien sur le dossier.")
    except Interdit as e:
        return erreur("permission", False, str(e), "Ne réessayez pas ; transmettez avec le motif acces_refuse.")
    except RegleMetier as e:
        return erreur("metier", False, str(e), "Expliquez la situation à l'assuré ; transmettez si nécessaire.")
    except KeyError as e:
        return erreur("validation", False, f"Paramètre manquant : {e.args[0]}.", "Reformulez l'appel.")
    return outils_v2.executer(systeme, nom, arguments)
