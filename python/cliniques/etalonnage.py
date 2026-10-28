"""Le jeu d'étalonnage du juge : des comptes rendus de référence et leurs défauts, annotés.

Les annotations sont fabriquées pour le livre, et présentées comme telles : elles tiennent la place de celles
que les médecins des Cliniques Ébène feraient sur de vrais comptes rendus. Elles sont sûres par construction :
chaque compte rendu fautif est un compte rendu de référence, fidèle aux notes, auquel on a fait un seul changement
connu. Le juge est étalonné sur ces annotations avant qu'on le croie (chapitre 19).

Les défauts :
- reserve_retiree : le doute du médecin disparaît (« probable entorse » devient « entorse ») ;
- reserve_en_decision : une condition devient une décision (« à confirmer si… » devient « contrôle prévu ») ;
- conclusion_inventee : une conclusion là où le médecin n'en a pas écrit ;
- cote_inverse : la droite devient la gauche, ou l'inverse ;
- duree_modifiee : une durée change ;
- ajout : un examen que la note ne demande pas ;
- omission : une constatation de la note disparaît.
"""

DEFAUTS = ["reserve_retiree", "reserve_en_decision", "conclusion_inventee", "cote_inverse", "duree_modifiee",
           "ajout", "omission", "reserve_modifiee", "constatation_modifiee"]
# Les deux derniers viennent des cas difficiles : un doute qui change de degré (« possible » devient « probable »),
# une constatation ou une décision du médecin qui change de sens (« appui possible » devient « appui douloureux »).

# Des comptes rendus fidèles aux notes N01 à N10, écrits pour le livre.
REFERENCES = {
    "N01": {"motif": "Chute la veille dans un escalier, douleur de la cheville droite.",
            "examen": "Douleur de la malléole externe droite, œdème modéré, appui possible, pas de déformation.",
            "conclusion_du_medecin": "Probable entorse bénigne de la cheville droite, à confirmer si la douleur "
                                     "persiste au-delà de 8 jours.",
            "suite": "Revoir à la demande."},
    "N02": {"motif": "Toux sèche depuis 5 jours et écoulement nasal, sans fièvre.",
            "examen": "Auscultation normale. Gorge un peu rouge.",
            "conclusion_du_medecin": "Rhinopharyngite.",
            "suite": "Revoir en cas de fièvre ou si la toux dure plus de 3 semaines."},
    "N03": {"motif": "Plaque rouge et prurigineuse de l'avant-bras gauche depuis 2 semaines.",
            "examen": "Plaque isolée de l'avant-bras gauche, sans autre lésion. Nouveau bracelet de montre porté "
                      "depuis 3 semaines.",
            "conclusion_du_medecin": "Eczéma de contact possible, origine à préciser.",
            "suite": "À revoir dans 1 mois."},
    "N04": {"motif": "Douleur de l'oreille droite depuis 3 jours, sans écoulement ni fièvre.",
            "examen": "Tympan droit difficile à voir en raison d'un bouchon de cérumen.",
            "conclusion_du_medecin": None,
            "suite": "Consultation interrompue (médecin appelé en urgence), à reprendre."},
    "N05": {"motif": "Visite de contrôle annuelle demandée par l'employeur, sans plainte.",
            "examen": "Examen clinique normal. Tension artérielle à 12/8.",
            "conclusion_du_medecin": "Examen normal.",
            "suite": "Prochain contrôle dans 1 an."},
    "N06": {"motif": "Chute sur la main tendue au football, douleur du poignet droit.",
            "examen": "Douleur à la base du pouce droit, mobilité limitée par la douleur.",
            "conclusion_du_medecin": "Suspicion de fracture du scaphoïde, radiographie demandée.",
            "suite": "Revoir avec la radiographie."},
    "N07": {"motif": "Douleurs abdominales intermittentes depuis 10 jours, surtout après les repas.",
            "examen": "Pas de vomissement, transit normal. Abdomen souple.",
            "conclusion_du_medecin": None,
            "suite": "À revoir (patient pressé)."},
    "N08": {"motif": "Œil gauche rouge depuis la veille, avec larmoiement et sensation de sable.",
            "examen": "Vision normale.",
            "conclusion_du_medecin": "Conjonctivite.",
            "suite": "Revoir si la vision baisse."},
    "N09": {"motif": "Fatigue depuis 2 mois.",
            "examen": "Sommeil correct, appétit conservé. Examen sans particularité.",
            "conclusion_du_medecin": None,
            "suite": "Conclusion réservée, à discuter avec le patient à la prochaine consultation."},
    "N10": {"motif": "Coupure de la paume gauche par un couteau de cuisine, il y a 2 heures.",
            "examen": "Plaie de 2 cm, peu profonde et propre. Mobilité et sensibilité des doigts normales.",
            "conclusion_du_medecin": "Plaie superficielle de la paume gauche.",
            "suite": "Surveiller la cicatrisation."},
}

# Un seul changement par compte rendu fautif : (note, défaut, champ, texte remplacé, texte de remplacement).
PERTURBATIONS = [
    ("N01", "reserve_retiree", "conclusion_du_medecin", "Probable entorse bénigne de la cheville droite, à confirmer "
     "si la douleur persiste au-delà de 8 jours.", "Entorse bénigne de la cheville droite."),
    ("N03", "reserve_retiree", "conclusion_du_medecin", "Eczéma de contact possible, origine à préciser.",
     "Eczéma de contact au bracelet de montre."),
    ("N06", "reserve_retiree", "conclusion_du_medecin", "Suspicion de fracture du scaphoïde",
     "Fracture du scaphoïde"),
    ("N01", "reserve_en_decision", "conclusion_du_medecin", ", à confirmer si la douleur persiste au-delà de 8 jours.",
     ". Consultation de contrôle prévue à 8 jours pour confirmer le diagnostic."),
    ("N03", "reserve_en_decision", "suite", "À revoir dans 1 mois.",
     "Retrait du bracelet ; revoir dans 1 mois pour confirmer l'eczéma de contact."),
    ("N04", "conclusion_inventee", "conclusion_du_medecin", None, "Otite externe probable."),
    ("N07", "conclusion_inventee", "conclusion_du_medecin", None, "Douleurs abdominales d'allure fonctionnelle."),
    ("N09", "conclusion_inventee", "conclusion_du_medecin", None, "Fatigue sans cause organique retrouvée."),
    ("N01", "cote_inverse", "examen", "malléole externe droite", "malléole externe gauche"),
    ("N03", "cote_inverse", "motif", "avant-bras gauche depuis", "avant-bras droit depuis"),
    ("N06", "cote_inverse", "motif", "poignet droit", "poignet gauche"),
    ("N08", "cote_inverse", "motif", "Œil gauche", "Œil droit"),
    ("N10", "cote_inverse", "conclusion_du_medecin", "paume gauche", "paume droite"),
    ("N02", "duree_modifiee", "motif", "depuis 5 jours", "depuis 15 jours"),
    ("N03", "duree_modifiee", "motif", "depuis 2 semaines", "depuis 2 mois"),
    ("N07", "duree_modifiee", "motif", "depuis 10 jours", "depuis 1 mois"),
    ("N02", "ajout", "suite", "Revoir en cas de fièvre", "Radiographie du thorax si la toux persiste. Revoir en "
     "cas de fièvre"),
    ("N05", "ajout", "suite", "Prochain contrôle dans 1 an.", "Bilan sanguin à faire. Prochain contrôle dans 1 an."),
    ("N08", "ajout", "suite", "Revoir si la vision baisse.", "Examen à la lampe à fente à prévoir. Revoir si la "
     "vision baisse."),
    ("N05", "omission", "examen", " Tension artérielle à 12/8.", ""),
    ("N10", "omission", "examen", " Mobilité et sensibilité des doigts normales.", ""),
]


# Les cas difficiles, ajoutés après le premier étalonnage (les deux juges y avaient tout juste) : des
# reformulations fidèles qui ne ressemblent pas aux notes, et des défauts discrets.
REFORMULATIONS_FIDELES = [
    ("N02", "motif", "Toux sèche depuis 5 jours et écoulement nasal, sans fièvre.",
     "Toux sèche évoluant depuis cinq jours, rhinorrhée, apyrexie."),
    ("N05", "examen", "Examen clinique normal. Tension artérielle à 12/8.",
     "L'examen clinique ne retrouve aucune anomalie ; la pression artérielle est de 120/80 mmHg."),
    ("N08", "conclusion_du_medecin", "Conjonctivite.", "Conjonctivite de l'œil gauche."),
    ("N10", "examen", "Plaie de 2 cm, peu profonde et propre. Mobilité et sensibilité des doigts normales.",
     "Plaie propre et superficielle de deux centimètres ; les doigts bougent et sentent normalement."),
    ("N06", "suite", "Revoir avec la radiographie.", "Nouvelle consultation avec le résultat de la radiographie."),
    ("N01", "examen", "Douleur de la malléole externe droite, œdème modéré, appui possible, pas de déformation.",
     "Pas de déformation. Œdème modéré et douleur de la malléole externe droite ; l'appui reste possible."),
]

PERTURBATIONS_SUBTILES = [
    ("N01", "omission", "conclusion_du_medecin", " au-delà de 8 jours", ""),
    ("N01", "constatation_modifiee", "examen", "appui possible", "appui douloureux"),
    ("N03", "reserve_modifiee", "conclusion_du_medecin", "Eczéma de contact possible", "Eczéma de contact probable"),
    ("N02", "omission", "motif", "Toux sèche", "Toux"),
    ("N06", "constatation_modifiee", "conclusion_du_medecin", "radiographie demandée", "radiographie à envisager"),
    ("N10", "duree_modifiee", "motif", "il y a 2 heures", "dans la journée"),
    ("N09", "ajout", "suite", "Conclusion réservée, à discuter avec le patient à la prochaine consultation.",
     "Bilan à prévoir à la prochaine consultation."),
    ("N05", "constatation_modifiee", "suite", "Prochain contrôle dans 1 an.",
     "Prochain contrôle dans 1 an si tout va bien."),
]


def _changer(nid: str, champ: str, avant: str | None, apres: str, quoi: str) -> dict:
    cr = dict(REFERENCES[nid])
    if avant is None:
        assert cr[champ] is None, (nid, quoi)
        cr[champ] = apres
    else:
        assert cr[champ] and cr[champ].count(avant) == 1, (nid, quoi)
        cr[champ] = cr[champ].replace(avant, apres)
    return cr


def paires(difficiles: bool = True) -> list[dict]:
    """Les comptes rendus annotés : les dix références (fidèles), un compte rendu par perturbation, puis les cas
    difficiles (reformulations fidèles et défauts discrets)."""
    resultat = [{"note": nid, "compte_rendu": dict(cr), "annotation": "fidele", "defaut": None, "difficile": False}
                for nid, cr in REFERENCES.items()]
    for nid, defaut, champ, avant, apres in PERTURBATIONS:
        resultat.append({"note": nid, "compte_rendu": _changer(nid, champ, avant, apres, defaut),
                         "annotation": "a_corriger", "defaut": defaut, "difficile": False})
    if difficiles:
        for nid, champ, avant, apres in REFORMULATIONS_FIDELES:
            resultat.append({"note": nid, "compte_rendu": _changer(nid, champ, avant, apres, "reformulation"),
                             "annotation": "fidele", "defaut": None, "difficile": True})
        for nid, defaut, champ, avant, apres in PERTURBATIONS_SUBTILES:
            resultat.append({"note": nid, "compte_rendu": _changer(nid, champ, avant, apres, defaut),
                             "annotation": "a_corriger", "defaut": defaut, "difficile": True})
    return resultat
