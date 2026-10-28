"""Chapitre 13 : l'archive des constats, fabriquée.

Kanvô Assurances reçoit environ 1 100 constats par mois (chapitre 2) ; deux ans d'archive en font
26 400. Le script fabrique un mois d'archive, 1 100 constats datés d'octobre 2024 à septembre 2026, et
leur vérité. Comme une vraie archive numérisée, une partie est abîmée :
- ocr : des lettres et des chiffres confondus dans une plaque (B et 8, O et 0, S et 5, I et 1). La plaque
  se retrouve en appliquant le motif « AA 9999 AA » ;
- plaque_partielle : un chiffre effacé (« ? ») : la plaque n'est pas lisible, la vérité est null ;
- heure_double : l'heure du formulaire et celle du récit diffèrent ; la vérité est celle du formulaire,
  la case prévue pour ;
- blesses_contradictoire : la case « non » est cochée, mais le récit parle d'un passager blessé ; la
  vérité est « unclear » ;
- assureur_abrege : « Lag. Ass. », « ATACORA GAR. » ; la vérité est le nom de l'assureur ;
- manquant : l'heure ou l'assureur de B n'est pas rempli ; la vérité est null.
Les autres constats sont propres. Le script est déterministe : il rend toujours la même archive.

Les constats viennent en mémoire (fabriquer()) : l'archive n'est pas versionnée, elle se refabrique.
"""

import random

from ch12.fabriquer import ASSUREURS_B, LIEUX, NOMS, ecrire_date, ecrire_plaque, plaque

TAILLE = 1100
DIFFICULTES = [("propre", 55), ("ocr", 12), ("plaque_partielle", 8), ("heure_double", 7),
               ("blesses_contradictoire", 6), ("assureur_abrege", 7), ("manquant", 5)]
ABREGES = {"Lagune Assurances": "Lag. Ass.", "Atacora Garantie": "ATACORA GAR.", "Ouémé Mutuelle": "Ouémé Mut."}
CONFUSIONS = {"B": "8", "O": "0", "S": "5", "I": "1", "8": "B", "0": "O", "5": "S", "1": "I"}


def _abimer(p: str, r: random.Random) -> str:
    """Une ou deux confusions de numérisation, là où la lettre ou le chiffre s'y prête."""
    caracteres = list(p)
    positions = [i for i, c in enumerate(caracteres) if c in CONFUSIONS]
    for i in r.sample(positions, min(len(positions), r.randint(1, 2))):
        caracteres[i] = CONFUSIONS[caracteres[i]]
    return "".join(caracteres)


def _plaque_confondable(r: random.Random) -> str:
    """Une plaque qui contient au moins une lettre ou un chiffre confondable."""
    while True:
        p = plaque(r)
        if any(c in CONFUSIONS for c in p):
            return p


def constat(numero: int, r: random.Random) -> dict:
    difficulte = r.choices([d for d, _ in DIFFICULTES], weights=[p for _, p in DIFFICULTES])[0]
    annee, mois = r.choice([(2024, m) for m in (10, 11, 12)] + [(2025, m) for m in range(1, 13)] +
                           [(2026, m) for m in range(1, 10)])
    date = f"{annee}-{mois:02d}-{r.randint(1, 28):02d}"
    heure = f"{r.randint(6, 21):02d}:{r.choice(['00', '10', '20', '30', '40', '50'])}"
    v = {"type": "constat", "date_accident": date, "heure": heure, "blesses": r.choice(["non"] * 8 + ["oui"]),
         "plaque_a": _plaque_confondable(r), "contrat_a": f"KA-AUTO-{r.randint(1000, 9999)}",
         "plaque_b": _plaque_confondable(r), "assureur_b": r.choice(ASSUREURS_B)}
    (nom_a, nom_b), lieu = r.sample(NOMS, 2), r.choice(LIEUX)
    ecrite_a, ecrite_b = ecrire_plaque(v["plaque_a"], numero), ecrire_plaque(v["plaque_b"], numero + 1)
    assureur_b, heure_ecrite, recit = v["assureur_b"], heure.replace(":", " h "), ""
    if difficulte == "ocr":
        if r.random() < 0.5:
            ecrite_a = _abimer(v["plaque_a"], r)
        else:
            ecrite_b = _abimer(v["plaque_b"], r)
    elif difficulte == "plaque_partielle":
        chiffres = [i for i, c in enumerate(v["plaque_b"]) if c.isdigit()]
        p = list(v["plaque_b"])
        p[r.choice(chiffres)] = "?"
        ecrite_b, v["plaque_b"] = "".join(p), None
    elif difficulte == "heure_double":
        h = int(heure.split(":")[0])
        recit = f"Observations : l'accident s'est produit vers {h + 1} h, à la sortie du travail."
    elif difficulte == "blesses_contradictoire":
        v["blesses"] = "unclear"
        recit = "Observations : le passager du véhicule B se plaint de douleurs au cou."
    elif difficulte == "assureur_abrege":
        assureur_b = ABREGES[v["assureur_b"]]
    elif difficulte == "manquant":
        if r.random() < 0.5:
            v["heure"], heure_ecrite = None, "____"
        else:
            v["assureur_b"], assureur_b = None, "____________"
    cases = "[ ] oui  [X] non" if v["blesses"] in ("non", "unclear") else "[X] oui  [ ] non"
    style = numero % 3
    if style == 0:
        texte = f"""CONSTAT AMIABLE D'ACCIDENT AUTOMOBILE
1. Date de l'accident : {ecrire_date(date, numero)}      Heure : {heure_ecrite}
2. Lieu : {lieu}
3. Blessés, même légers : {cases}
VÉHICULE A
   Conducteur : {nom_a}
   Société d'assurance : Kanvô Assurances      Contrat n° {v["contrat_a"]}
   Immatriculation : {ecrite_a}
VÉHICULE B
   Conducteur : {nom_b}
   Société d'assurance : {assureur_b}
   Immatriculation : {ecrite_b}
{recit}"""
    elif style == 1:
        texte = f"""Constat rempli à la main, transcrit par l'agence :
date : {ecrire_date(date, numero + 2)} / heure : {"(non remplie)" if heure_ecrite == "____" else heure_ecrite}
lieu : {lieu}
véh. A : {ecrite_a}, assuré chez Kanvô, police {v["contrat_a"]}, conducteur {nom_a}
véh. B : {ecrite_b}, assurance : {"(case vide)" if assureur_b.startswith("_") else assureur_b}, conducteur {nom_b}
blessés : {cases}
{recit}"""
    else:
        texte = f"""Télécopie reçue — constat amiable, page 1/1
DATE {ecrire_date(date, numero + 4)}  HEURE {heure_ecrite}  LIEU {lieu.upper()}
BLESSÉS : {cases}
A : {nom_a.upper()} / KANVÔ ASSURANCES / CONTRAT {v["contrat_a"]} / IMMAT {ecrite_a.upper()}
B : {nom_b.upper()} / {assureur_b.upper()} / IMMAT {ecrite_b.upper()}
{recit}"""
    return {"id": f"arch-{numero:04d}", "texte": texte.strip(), "verite": v, "difficulte": difficulte,
            "mois": date[:7]}


def fabriquer(taille: int = TAILLE) -> list[dict]:
    r = random.Random(13)
    return [constat(i, r) for i in range(1, taille + 1)]


if __name__ == "__main__":
    from collections import Counter
    archive = fabriquer()
    print(len(archive), Counter(c["difficulte"] for c in archive))
    for c in archive[:6]:
        print(f"--- {c['id']} ({c['difficulte']})\n{c['texte']}")
