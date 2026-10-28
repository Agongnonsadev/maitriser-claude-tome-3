"""Les notes de consultation fabriquées pour la mission 2, et ce qu'on sait de chacune.

Écrites pour le livre, dans le style abrégé d'un médecin qui note pendant la consultation. Les patients sont
désignés par un numéro, les médecins par des initiales ; aucun n'existe. Les notes ne contiennent ni traitement
ni posologie, et leurs conclusions ne sont pas des recommandations médicales : elles servent à vérifier qu'un
compte rendu dit ce que le médecin a écrit, rien de plus, rien de moins.

Pour chaque note, la vérité :
- conclusion : la conclusion du médecin telle qu'il l'a notée, ou None quand la note n'en a pas ;
- reserves : les mots par lesquels le médecin marque un doute, qu'un compte rendu fidèle garde ;
- examens : les examens que la note mentionne (un compte rendu n'en ajoute pas d'autres).
"""

NOTES = [
    {"id": "N01", "clinique": "Cotonou", "specialite": "traumatologie", "medecin": "Dr K. A.",
     "patient": "EB-2026-0412, 34 ans",
     "texte": "Chute hier en descendant un escalier, cheville D. Douleur malléole ext., oedème modéré, appui "
              "possible. Pas de déformation. Concl. : probable entorse bénigne cheville D, à confirmer si douleur "
              "> 8 j. Suite : revoir à la demande.",
     "conclusion": "probable entorse bénigne cheville D, à confirmer si douleur > 8 j",
     "reserves": ["probable", "a confirmer"], "examens": []},
    {"id": "N02", "clinique": "Abidjan", "specialite": "médecine générale", "medecin": "Dr S. T.",
     "patient": "EB-2026-0418, 41 ans",
     "texte": "Toux sèche depuis 5 j, nez qui coule, pas de fièvre. Auscultation normale. Gorge un peu rouge. "
              "Concl. : rhinopharyngite. Suite : revoir si fièvre ou si toux > 3 sem.",
     "conclusion": "rhinopharyngite", "reserves": [], "examens": []},
    {"id": "N03", "clinique": "Dakar", "specialite": "dermatologie", "medecin": "Dr M. N.",
     "patient": "EB-2026-0421, 29 ans",
     "texte": "Plaque rouge qui gratte, avant-bras G, depuis 2 sem. Nouveau bracelet de montre il y a 3 sem. "
              "Pas d'autre lésion. Concl. : eczéma de contact possible, origine à préciser. Suite : à revoir dans "
              "1 mois.",
     "conclusion": "eczéma de contact possible, origine à préciser",
     "reserves": ["possible", "a preciser"], "examens": []},
    {"id": "N04", "clinique": "Cotonou", "specialite": "ORL", "medecin": "Dr E. H.",
     "patient": "EB-2026-0427, 52 ans",
     "texte": "Douleur oreille D depuis 3 j, pas d'écoulement. Tympan D difficile à voir (cérumen). Pas de "
              "fièvre. Appelé en urgence, consultation à reprendre.",
     "conclusion": None, "reserves": [], "examens": []},
    {"id": "N05", "clinique": "Abidjan", "specialite": "médecine générale", "medecin": "Dr S. T.",
     "patient": "EB-2026-0430, 47 ans",
     "texte": "Visite de contrôle annuelle demandée par l'employeur. Aucune plainte. Examen clinique normal. "
              "Tension 12/8. Concl. : examen normal. Suite : prochain contrôle dans 1 an.",
     "conclusion": "examen normal", "reserves": [], "examens": []},
    {"id": "N06", "clinique": "Dakar", "specialite": "traumatologie", "medecin": "Dr A. D.",
     "patient": "EB-2026-0433, 23 ans",
     "texte": "Chute sur la main tendue au football. Douleur poignet D, à la base du pouce. Mobilité limitée par "
              "la douleur. Concl. : suspicion de fracture du scaphoïde, radiographie demandée. Suite : revoir avec "
              "la radiographie.",
     "conclusion": "suspicion de fracture du scaphoïde, radiographie demandée",
     "reserves": ["suspicion"], "examens": ["radiographie"]},
    {"id": "N07", "clinique": "Cotonou", "specialite": "médecine générale", "medecin": "Dr K. A.",
     "patient": "EB-2026-0436, 38 ans",
     "texte": "Douleurs abdominales intermittentes depuis 10 j, surtout après les repas. Pas de vomissement, "
              "transit normal. Abdomen souple. Patient pressé, à revoir.",
     "conclusion": None, "reserves": [], "examens": []},
    {"id": "N08", "clinique": "Abidjan", "specialite": "ophtalmologie", "medecin": "Dr F. K.",
     "patient": "EB-2026-0440, 31 ans",
     "texte": "Oeil G rouge depuis hier, larmoiement, sensation de sable. Vision normale. Concl. : conjonctivite. "
              "Suite : revoir si la vision baisse.",
     "conclusion": "conjonctivite", "reserves": [], "examens": []},
    {"id": "N09", "clinique": "Dakar", "specialite": "médecine générale", "medecin": "Dr M. N.",
     "patient": "EB-2026-0444, 56 ans",
     "texte": "Fatigue depuis 2 mois, sommeil correct. Appétit conservé. Examen sans particularité. Conclusion "
              "réservée, à discuter avec le patient à la prochaine consultation.",
     "conclusion": None, "reserves": [], "examens": []},
    {"id": "N10", "clinique": "Cotonou", "specialite": "traumatologie", "medecin": "Dr E. H.",
     "patient": "EB-2026-0449, 44 ans",
     "texte": "Coupure paume main G avec un couteau de cuisine, il y a 2 h. Plaie de 2 cm, peu profonde, propre. "
              "Mobilité et sensibilité des doigts normales. Concl. : plaie superficielle de la paume G. Suite : "
              "surveiller la cicatrisation.",
     "conclusion": "plaie superficielle de la paume G", "reserves": [], "examens": []},
    # Chapitre 19 : dix notes de plus, dont deux dictées transcrites sans ponctuation (simulées pour le livre).
    {"id": "N11", "clinique": "Abidjan", "specialite": "ORL", "medecin": "Dr F. K.",
     "patient": "EB-2026-0452, 27 ans",
     "texte": "Mal de gorge depuis 2 j, fièvre à 38,5 hier soir. Amygdales rouges, sans dépôt. Concl. : angine "
              "probablement virale. Suite : revoir si fièvre > 3 j.",
     "conclusion": "angine probablement virale", "reserves": ["probable"], "examens": []},
    {"id": "N12", "clinique": "Dakar", "specialite": "traumatologie", "medecin": "Dr A. D.",
     "patient": "EB-2026-0455, 19 ans",
     "texte": "Torsion du genou G au basket il y a 3 j. Genou un peu gonflé, pas de blocage. Concl. : entorse du "
              "genou G possible, à revoir. Suite : revoir dans 10 j.",
     "conclusion": "entorse du genou G possible, à revoir", "reserves": ["possible"], "examens": []},
    {"id": "N13", "clinique": "Cotonou", "specialite": "médecine générale", "medecin": "Dr K. A.",
     "patient": "EB-2026-0458, 63 ans", "dictee": True,
     "texte": "patient vu pour des vertiges depuis une semaine surtout au lever tension couché treize huit debout "
              "onze sept pas de chute conclusion vertiges positionnels à préciser revoir dans quinze jours",
     "conclusion": "vertiges positionnels à préciser", "reserves": ["a preciser"], "examens": []},
    {"id": "N14", "clinique": "Abidjan", "specialite": "dermatologie", "medecin": "Dr S. T.",
     "patient": "EB-2026-0461, 45 ans",
     "texte": "Grain de beauté du dos, présent depuis l'enfance ; le patient trouve qu'il a changé. Lésion de 6 mm, "
              "bords réguliers. Concl. : lésion à surveiller, avis du partenaire de Paris demandé. Suite : envoi "
              "des photos au partenaire.",
     "conclusion": "lésion à surveiller, avis du partenaire de Paris demandé", "reserves": [], "examens": []},
    {"id": "N15", "clinique": "Dakar", "specialite": "médecine générale", "medecin": "Dr M. N.",
     "patient": "EB-2026-0464, 50 ans",
     "texte": "Contrôle de la glycémie demandé par le patient, inquiet (père diabétique). Aucun symptôme. Glycémie "
              "capillaire à jeun : 0,95 g/l. Concl. : glycémie normale ce jour. Suite : aucune.",
     "conclusion": "glycémie normale ce jour", "reserves": [], "examens": ["glycemie capillaire"]},
    {"id": "N16", "clinique": "Cotonou", "specialite": "traumatologie", "medecin": "Dr E. H.",
     "patient": "EB-2026-0467, 58 ans",
     "texte": "Douleur épaule D depuis 1 mois, gêne pour lever le bras. Examen limité par la douleur. Le patient "
              "doit revenir avec ses anciens examens.",
     "conclusion": None, "reserves": [], "examens": []},
    {"id": "N17", "clinique": "Abidjan", "specialite": "ophtalmologie", "medecin": "Dr F. K.",
     "patient": "EB-2026-0470, 36 ans",
     "texte": "Baisse progressive de la vision de loin depuis 1 an. Lit bien de près. Concl. : myopie probable, à "
              "confirmer par une mesure de la vue. Suite : rendez-vous chez l'opticien.",
     "conclusion": "myopie probable, à confirmer par une mesure de la vue",
     "reserves": ["probable", "a confirmer"], "examens": []},
    {"id": "N18", "clinique": "Dakar", "specialite": "médecine générale", "medecin": "Dr A. D.",
     "patient": "EB-2026-0473, 42 ans", "dictee": True,
     "texte": "patiente vue pour des maux de tête depuis trois jours sans fièvre pas de raideur de la nuque "
              "examen neurologique normal conclusion céphalées de tension probables revoir si aggravation",
     "conclusion": "céphalées de tension probables", "reserves": ["probable"], "examens": []},
    {"id": "N19", "clinique": "Cotonou", "specialite": "ORL", "medecin": "Dr E. H.",
     "patient": "EB-2026-0476, 61 ans",
     "texte": "Bourdonnements oreille G depuis 2 sem. Pas de douleur. Otoscopie normale. Le patient demande un avis "
              "spécialisé, à discuter.",
     "conclusion": None, "reserves": [], "examens": []},
    {"id": "N20", "clinique": "Abidjan", "specialite": "traumatologie", "medecin": "Dr S. T.",
     "patient": "EB-2026-0479, 33 ans",
     "texte": "Entorse de la cheville G il y a 3 sem., vue ailleurs. Revient pour une douleur qui persiste à la "
              "marche. Oedème léger. Concl. : suites d'entorse, évolution lente. Suite : radiographie demandée pour "
              "éliminer une fracture.",
     "conclusion": "suites d'entorse, évolution lente", "reserves": [], "examens": ["radiographie"]},
]

# Le chapitre 18 a été mesuré sur les dix premières notes : il les garde.
NOTES_18 = [n for n in NOTES if n["id"] <= "N10"]

# Les examens et les soins qu'un compte rendu ne doit pas ajouter quand la note n'en parle pas : des débuts de
# mots, cherchés en début de mot dans un texte en minuscules et sans accents (« irm » ne doit pas trouver
# « confirmer »). Le nom de l'ajout est le motif sans ses marques.
AJOUTS = ["radiographie", r"radio\b", "echographie", "scanner", r"irm\b", "bilan", r"analyses?\b", "prise de sang",
          "antibiot", "anti-inflammatoire", "antalgique", "paracetamol", "traitement", "prescri", "ordonnance",
          "kinesitherapie", "attelle", "platre", "pommade", "collyre", r"repos\b", r"glace\b"]


def soins_mentionnes(texte: str) -> list[str]:
    """Les examens et les soins d'AJOUTS que mentionne un texte déjà normalisé."""
    import re
    return sorted({re.sub(r"\\b|\?", "", a) for a in AJOUTS if re.search(r"\b" + a, texte)})

# Les mots par lesquels un médecin marque un doute.
RESERVES = ["probable", "possible", "suspicion", "a confirmer", "a preciser", "evoque", "compatible", "?"]


def note(identifiant: str) -> dict:
    return next(n for n in NOTES if n["id"] == identifiant)
