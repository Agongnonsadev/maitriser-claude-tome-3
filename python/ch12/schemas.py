"""Chapitre 12 : les outils d'extraction, en deux versions de schéma.

Chaque type de document a son outil ; un quatrième outil reçoit ce qui n'est rien de tout cela. Claude
choisit l'outil, ce qui classe le document, et en remplit les arguments, ce qui l'extrait. Tous les
outils sont stricts (strict: true) : les arguments respectent toujours le schéma.

- naif : chaque champ est obligatoire et doit avoir une valeur ; les blessés et la conclusion de
  l'expert sont des booléens. Le schéma oblige Claude à remplir un champ que le document ne donne pas ;
- soigne : un champ absent ou illisible vaut null ; les blessés et la conclusion ont une valeur
  « unclear » ; la facture rend les lignes, le total déclaré, le total calculé et un indicateur
  d'incohérence ; le document non reconnu dit ce qu'il est.

Une requête accepte au plus 16 paramètres à type union (« string ou null ») sur l'ensemble de ses outils
stricts ; au-delà, l'API répond par une erreur 400. Seuls les champs qu'un document peut taire sont donc
nullables : 15. Le lieu, le garage et l'expert, toujours présents dans ces documents, ne le sont pas.
"""


def _objet(proprietes: dict) -> dict:
    """Un objet strict : tous les champs requis (null quand il le faut), aucun autre."""
    return {"type": "object", "properties": proprietes, "required": list(proprietes), "additionalProperties": False}


def _champ(type_: str, description: str, nul: bool) -> dict:
    return {"type": [type_, "null"] if nul else type_, "description": description}


def outils(version: str) -> list[dict]:
    nul = version == "soigne"
    texte, entier = (lambda d: _champ("string", d, nul)), (lambda d: _champ("integer", d, nul))
    present = lambda d: {"type": "string", "description": d}   # toujours donné : jamais nul
    vehicule_a = _objet({"plaque": texte("Immatriculation"), "numero_contrat": texte("Numéro de contrat Kanvô Assurances")})
    vehicule_b = _objet({"plaque": texte("Immatriculation"), "assureur": texte("Société d'assurance")})
    if nul:
        blesses = {"type": "string", "enum": ["oui", "non", "unclear"],
                   "description": "« unclear » si le document ne tranche pas"}
        conclusion = {"type": "string", "enum": ["reparable", "irreparable", "unclear"],
                      "description": "« unclear » si l'expert ne conclut pas"}
    else:
        blesses = {"type": "boolean", "description": "Vrai s'il y a des blessés"}
        conclusion = {"type": "boolean", "description": "Vrai si le véhicule est réparable"}
    facture = {"numero_facture": texte("Numéro de la facture"), "date_facture": texte("Date de la facture"),
               "garage": present("Nom du garage"), "plaque": texte("Immatriculation du véhicule"),
               "lignes": {"type": "array", "items": _objet({"designation": {"type": "string"},
                                                            "montant_fcfa": {"type": "integer"}})},
               "total_declare_fcfa": entier("Le total que la facture déclare")}
    if nul:
        facture |= {"total_calcule_fcfa": {"type": "integer", "description": "La somme des montants des lignes"},
                    "incoherence": {"type": "boolean",
                                    "description": "Vrai si le total déclaré diffère de la somme des lignes"}}
    resultat = [
        {"name": "extraire_constat", "strict": True,
         "description": "Pour un constat amiable d'accident automobile, rempli, transcrit ou raconté.",
         "input_schema": _objet({"date_accident": texte("Date de l'accident"), "heure": texte("Heure de l'accident"),
                                 "lieu": present("Lieu de l'accident"), "blesses": blesses,
                                 "vehicule_a": vehicule_a, "vehicule_b": vehicule_b})},
        {"name": "extraire_facture", "strict": True,
         "description": "Pour une facture de garage ou de réparation.",
         "input_schema": _objet(facture)},
        {"name": "extraire_rapport_expert", "strict": True,
         "description": "Pour un rapport ou un courrier d'expert automobile.",
         "input_schema": _objet({"numero_sinistre": texte("Numéro de sinistre"),
                                 "date_expertise": texte("Date de l'examen du véhicule"),
                                 "plaque": texte("Immatriculation"),
                                 "montant_evalue_fcfa": entier("Montant des dommages évalué par l'expert"),
                                 "vetuste_pct": entier("Vétusté appliquée, en pourcentage"),
                                 "conclusion": conclusion, "expert": present("Nom de l'expert ou du cabinet")})},
    ]
    if nul:
        resultat.append({"name": "document_non_reconnu", "strict": True,
                         "description": "Pour un document qui n'est ni un constat, ni une facture, ni un rapport d'expert.",
                         "input_schema": _objet({"nature": {"type": "string", "description": "Ce qu'est le document, en quelques mots"}})})
    return resultat


TYPES = {"extraire_constat": "constat", "extraire_facture": "facture", "extraire_rapport_expert": "rapport_expert",
         "document_non_reconnu": "autre"}

PROMPT_NAIF = ("Vous extrayez les données des documents reçus par la direction des sinistres de Kanvô Assurances. "
               "Utilisez l'outil qui correspond au document.")

REGLES = """Vous extrayez les données des documents reçus par la direction des sinistres de Kanvô Assurances. Utilisez l'outil qui correspond au document ; un document qui n'est ni un constat, ni une facture, ni un rapport d'expert va dans document_non_reconnu.

Règles de normalisation :
- les dates au format AAAA-MM-JJ, les heures au format HH:MM ;
- les montants en francs CFA, en nombre entier, sans espace ni séparateur ;
- les immatriculations en majuscules, au format « AA 9999 AA » ;
- le numéro de contrat tel qu'il est écrit, par exemple KA-AUTO-1234.

Ce que le document ne dit pas :
- un champ absent, vide ou illisible vaut null. Ne le déduisez pas, ne le devinez pas ;
- les blessés et la conclusion de l'expert valent « unclear » quand le document ne tranche pas.

Les factures : recopiez chaque ligne et le total tels que la facture les donne, sans rien corriger. Calculez la somme des lignes dans total_calcule_fcfa, et mettez incoherence à vrai si elle diffère du total déclaré."""

EXEMPLES = """

Deux exemples de documents difficiles :

Document : « Garage Saint-Michel. TOTAL : 150 000 F. Facture 2026-77 du 3 octobre 2026. Lignes : vitre arrière 120 000 F ; pose 40 000 F ; remise fidélité -10 000 F. Pas de véhicule indiqué. »
Arguments de extraire_facture : {"numero_facture": "2026-77", "date_facture": "2026-10-03", "garage": "Garage Saint-Michel", "plaque": null, "lignes": [{"designation": "Vitre arrière", "montant_fcfa": 120000}, {"designation": "Pose", "montant_fcfa": 40000}, {"designation": "Remise fidélité", "montant_fcfa": -10000}], "total_declare_fcfa": 150000, "total_calcule_fcfa": 150000, "incoherence": false}
Le total figure en tête, et la remise est une ligne négative. Le véhicule n'est pas indiqué : null.

Document : « constat transcrit — 5/9/26 — rue des Cheminots — A : AB 1234 CD, Kanvô, KA-AUTO-0042 — B : plaque effacée, Lagune Assurances — blessés : rien de coché »
Arguments de extraire_constat : {"date_accident": "2026-09-05", "heure": null, "lieu": "rue des Cheminots", "blesses": "unclear", "vehicule_a": {"plaque": "AB 1234 CD", "numero_contrat": "KA-AUTO-0042"}, "vehicule_b": {"plaque": null, "assureur": "Lagune Assurances"}}
Aucune heure n'est donnée, la plaque de B est effacée, aucune case n'est cochée : null, null, « unclear »."""


def prompt(variante: str) -> str:
    return {"naif": PROMPT_NAIF, "soigne": REGLES, "exemples": REGLES + EXEMPLES}[variante]
