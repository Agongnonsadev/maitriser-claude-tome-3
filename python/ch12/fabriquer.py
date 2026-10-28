"""Chapitre 12 : fabriquer les documents de l'extraction, et leur vérité.

Trente-six documents fictifs, tels que les rend la numérisation : douze constats amiables, douze factures
de garage, dix rapports d'expert, et deux documents qui ne sont rien de tout cela. Les mises en page, les
formats de date et de montant changent d'un document à l'autre ; certains champs sont absents ou
illisibles ; deux factures ont des lignes qui ne font pas le total.

Le script est déterministe (graine fixe) : il réécrit ch12/documents/ et ch12/verite.json à l'identique.
Lancement, depuis le dossier python/ :  python -m ch12.fabriquer
"""

import json
import random
from pathlib import Path

DOSSIER = Path(__file__).parent
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
NOMS = ["M. Koffi Agbo", "Mme Rosine Houngbo", "M. Serge Dossou-Gbété", "Mme Pélagie Ahyi", "M. Romuald Sossou",
        "Mme Clarisse Tossou", "M. Firmin Zannou", "Mme Odile Kpossou", "M. Edgard Hounkpè", "Mme Nadège Adjaho",
        "M. Bertin Akakpo", "Mme Viviane Gnonlonfoun"]
ASSUREURS_B = ["Lagune Assurances", "Atacora Garantie", "Ouémé Mutuelle"]  # fictifs, comme Kanvô
LIEUX = ["carrefour de l'Étoile rouge, Cotonou", "boulevard de la Marina, Cotonou", "pont de Fidjrossè",
         "route de Porto-Novo, à hauteur de Sèmè-Podji", "carrefour Vêdoko, Cotonou", "rond-point de Godomey",
         "avenue Steinmetz, Cotonou", "voie express, sortie Akpakpa"]
GARAGES = ["Garage de Houéyiho", "Atelier Akpakpa Auto", "Garage du Carrefour Vêdoko", "Mécanique générale Gbégamey"]
PIECES = [("Pare-chocs arrière", 85000), ("Feu arrière gauche", 32500), ("Hayon, redressage", 60000),
          ("Peinture, deux éléments", 95000), ("Main-d'œuvre, 6 heures", 48000), ("Phare avant droit", 41000),
          ("Aile avant gauche", 72000), ("Radiateur", 118000), ("Rétroviseur droit", 27500),
          ("Main-d'œuvre, 3 heures", 24000), ("Calandre", 39000), ("Portière avant droite", 135000)]
EXPERTS = ["Cabinet Expertises Lokossa", "Bureau d'expertise automobile Agontinkon", "Expert agréé A. Hounsou"]


def plaque(r: random.Random) -> str:
    lettres = "ABCDEFGHJKLMNPRSTUVWXYZ"
    return f"{r.choice(lettres)}{r.choice(lettres)} {r.randint(1000, 9999)} {r.choice(lettres)}{r.choice(lettres)}"


def ecrire_plaque(p: str, style: int) -> str:
    a, b, c = p.split()
    return [p, f"{a}-{b}-{c}", f"{a}{b}{c}".lower(), f"{a} {b}-{c}"][style % 4]


def ecrire_date(iso: str, style: int) -> str:
    a, m, j = iso.split("-")
    return [f"{j}/{m}/{a}", f"{int(j)} {MOIS[int(m) - 1]} {a}", f"{j}-{m}-{a[2:]}", iso, f"{j}.{m}.{a}"][style % 5]


def ecrire_montant(n: int, style: int) -> str:
    espace = f"{n:,}".replace(",", " ")
    point = f"{n:,}".replace(",", ".")
    return [f"{espace} FCFA", f"{point} F CFA", f"{n} F", f"{espace}", f"{espace} francs CFA"][style % 5]


def constat(i: int, r: random.Random) -> tuple[str, dict]:
    jour = r.randint(1, 26)
    date = f"2026-{r.choice(['09', '10'])}-{jour:02d}"
    heure = f"{r.randint(6, 21):02d}:{r.choice(['00', '15', '30', '45'])}"
    sans_heure, plaque_b_illisible, sans_assureur_b = i in (2, 7), i in (3, 9, 11), i in (5,)
    blesses = "oui" if i in (4, 10) else "unclear" if i in (6,) else "non"
    v = {"type": "constat", "date_accident": date, "heure": None if sans_heure else heure, "blesses": blesses,
         "plaque_a": plaque(r), "contrat_a": f"KA-AUTO-{r.randint(1000, 9999)}", "plaque_b": plaque(r),
         "assureur_b": r.choice(ASSUREURS_B)}
    if plaque_b_illisible:
        v["plaque_b"] = None
    if sans_assureur_b:
        v["assureur_b"] = None
    (nom_a, nom_b), lieu = r.sample(NOMS, 2), r.choice(LIEUX)
    sb = "[illisible : tache d'encre]" if plaque_b_illisible else ecrire_plaque(v["plaque_b"], i)
    ab = "____________" if sans_assureur_b else v["assureur_b"]
    cases = {"oui": "[X] oui  [ ] non", "non": "[ ] oui  [X] non", "unclear": "[ ] oui  [ ] non"}[blesses]
    style = i % 3
    if style == 0:
        texte = f"""CONSTAT AMIABLE D'ACCIDENT AUTOMOBILE
1. Date de l'accident : {ecrire_date(date, i)}      Heure : {"____" if sans_heure else heure.replace(":", " h ")}
2. Lieu : {lieu}
3. Blessés, même légers : {cases}
VÉHICULE A
   Conducteur : {nom_a}
   Société d'assurance : Kanvô Assurances      Contrat n° {v["contrat_a"]}
   Immatriculation : {ecrire_plaque(v["plaque_a"], i + 1)}
VÉHICULE B
   Conducteur : {nom_b}
   Société d'assurance : {ab}
   Immatriculation : {sb}
12. Circonstances : A cochée(s) : 8 (heurtait à l'arrière) ; B cochée(s) : 1 (en stationnement)
Signatures : A et B"""
    elif style == 1:
        texte = f"""Constat rempli à la main, transcrit par l'agence :
date : {ecrire_date(date, i + 2)} / heure : {"(non remplie)" if sans_heure else "vers " + heure.replace(":", "h")}
lieu : {lieu}
véh. A : {ecrire_plaque(v["plaque_a"], i + 2)}, assuré chez Kanvô, police {v["contrat_a"]}, conducteur {nom_a}
véh. B : {sb}, assurance : {ab if not sans_assureur_b else "(case vide)"}, conducteur {nom_b}
blessés : {cases}
croquis : le véhicule B, à l'arrêt, a été touché par A en marche arrière."""
    else:
        texte = f"""Objet : constat d'accident
Le {ecrire_date(date, 1)}{"" if sans_heure else ", vers " + heure.replace(":", " h ")}, {lieu}, mon véhicule immatriculé {ecrire_plaque(v["plaque_a"], 0)} (Kanvô Assurances, contrat {v["contrat_a"]}) a heurté le véhicule de {nom_b}{", immatriculé " + sb if not plaque_b_illisible else ", dont la plaque n'est pas lisible sur notre exemplaire du constat"}{", assuré chez " + ab if not sans_assureur_b else ""}.
Blessés : {cases}
Le constat amiable a été signé par les deux conducteurs. — {nom_a}"""
    return texte, v


def facture(i: int, r: random.Random) -> tuple[str, dict]:
    lignes = r.sample(PIECES, r.randint(2, 4))
    somme = sum(m for _, m in lignes)
    incoherente = i in (3, 8)
    total = somme + (25000 if i == 3 else -15000 if i == 8 else 0)
    date = f"2026-10-{r.randint(1, 26):02d}"
    sans_plaque = i in (5, 10)
    v = {"type": "facture", "numero_facture": f"F-2026-{r.randint(100, 999)}", "date_facture": date,
         "garage": r.choice(GARAGES), "plaque": None if sans_plaque else plaque(r), "total_declare": total,
         "somme_lignes": somme, "nombre_lignes": len(lignes), "incoherence": incoherente}
    style = i % 3
    def montant(n):
        return ecrire_montant(n, i)
    corps = "\n".join(f"   {d:.<38} {montant(m)}" for d, m in lignes)
    immat = "" if sans_plaque else ecrire_plaque(v["plaque"], i)
    if style == 0:
        texte = f"""{v["garage"].upper()}
FACTURE N° {v["numero_facture"]}                 Date : {ecrire_date(date, i)}
Véhicule : {immat if immat else "—"}
Désignation
{corps}
TOTAL À PAYER : {montant(total)}"""
    elif style == 1:
        texte = f"""Facture {v["numero_facture"]} — {v["garage"]}
Émise le {ecrire_date(date, i + 1)}{"" if sans_plaque else " | Immatriculation " + immat}
TOTAL TTC : {montant(total)}
Détail des travaux :
""" + "\n".join(f"- {d} : {montant(m)}" for d, m in lignes)
    else:
        texte = f"""{v["garage"]} — réparations toutes marques
Doit : Kanvô Assurances, pour le compte de son assuré
Réf. facture : {v["numero_facture"]}   ({ecrire_date(date, i + 3)})
{"" if sans_plaque else "Véhicule " + immat}
""" + "\n".join(f"{d} | {montant(m)}" for d, m in lignes) + f"""
Arrêtée la présente facture à la somme de {montant(total)}."""
    return texte, v


def rapport(i: int, r: random.Random) -> tuple[str, dict]:
    date = f"2026-10-{r.randint(1, 26):02d}"
    montant = r.choice([180000, 245000, 312500, 420000, 515000, 690000, 1250000, 95000])
    vetuste = None if i in (2, 6) else r.choice([0, 10, 15, 20, 25])
    conclusion = "irreparable" if i in (4,) else "unclear" if i in (7,) else "reparable"
    v = {"type": "rapport_expert", "numero_sinistre": f"SIN-2026-{r.randint(1000, 1999)}", "date_expertise": date,
         "plaque": plaque(r), "montant_evalue": montant, "vetuste_pct": vetuste, "conclusion": conclusion,
         "expert": r.choice(EXPERTS)}
    phrase_vetuste = "" if vetuste is None else (f", vétusté de {vetuste} % déduite" if vetuste else ", sans vétusté")
    phrase_conclusion = {"reparable": "Le véhicule est réparable dans les conditions décrites.",
                         "irreparable": "Le coût des réparations dépassant la valeur du véhicule, celui-ci est "
                                        "économiquement irréparable.",
                         "unclear": "Le caractère réparable du véhicule ne pourra être confirmé qu'après démontage "
                                    "du train avant."}[conclusion]
    if i % 2 == 0:
        texte = f"""{v["expert"]}
RAPPORT D'EXPERTISE — Sinistre {v["numero_sinistre"]}
Véhicule examiné : {ecrire_plaque(v["plaque"], i)}       Date de l'examen : {ecrire_date(date, i)}
Nous avons examiné le véhicule au garage. Après analyse des dommages et des devis, nous évaluons le montant des dommages à {ecrire_montant(montant, i)}{phrase_vetuste}.
{phrase_conclusion}"""
    else:
        texte = f"""Monsieur le gestionnaire,
Suite à votre mission concernant le dossier {v["numero_sinistre"]}, j'ai procédé le {ecrire_date(date, i + 1)} à l'examen du véhicule {ecrire_plaque(v["plaque"], i + 1)}.
{phrase_conclusion} Mon évaluation s'établit à {ecrire_montant(montant, i + 2)}{phrase_vetuste}.
Veuillez agréer, Monsieur, mes salutations distinguées. {v["expert"]}"""
    return texte, v


AUTRES = [
    ("""Cabinet de Maître Adoukonou, avocat au barreau de Cotonou (fictif)
Objet : mise en demeure
Madame, Monsieur, mon client, M. Firmin Zannou, vous met en demeure de lui verser sous quinze jours l'indemnité qu'il estime due. À défaut, je saisirai la juridiction compétente.""",
     {"type": "autre", "detail": "mise en demeure d'un avocat"}),
    ("""Relevé d'informations — Kanvô Assurances
Assuré : Mme Odile Kpossou. Contrat automobile du 1er janvier 2021 au 31 décembre 2025.
Sinistres déclarés sur la période : 1, responsable à 50 %. Coefficient de bonus : 0,90.""",
     {"type": "autre", "detail": "relevé d'informations"}),
]


def fabriquer() -> list[dict]:
    r = random.Random(12)
    documents = []
    for type_, n, f in (("constat", 12, constat), ("facture", 12, facture), ("rapport", 10, rapport)):
        for i in range(n):
            texte, verite = f(i, r)
            documents.append({"id": f"{type_}-{i + 1:02d}", "texte": texte, "verite": verite})
    for i, (texte, verite) in enumerate(AUTRES, start=1):
        documents.append({"id": f"autre-{i:02d}", "texte": texte, "verite": verite})
    return documents


def principal() -> None:
    documents = fabriquer()
    dossier = DOSSIER / "documents"
    dossier.mkdir(exist_ok=True)
    for d in documents:
        (dossier / f"{d['id']}.txt").write_text(d["texte"] + "\n", encoding="utf-8")
    (DOSSIER / "verite.json").write_text(json.dumps({"_note": "Documents et vérité fabriqués par ch12/fabriquer.py "
                                                     "(fictifs).", "documents": [{"id": d["id"], "verite": d["verite"]}
                                                                                 for d in documents]},
                                                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(documents)} documents dans {dossier}")


if __name__ == "__main__":
    principal()
