"""Chapitre 13 : calibrer la confiance par champ, et en tirer la file de relecture des gestionnaires.

La confiance que Claude déclare n'est pas une probabilité : elle se calibre sur un jeu étiqueté. Ici, les
gestionnaires ont vérifié 400 constats du lot, tirés au hasard (graine fixe) : c'est le jeu de calibrage.
Les 700 autres servent à vérifier que les seuils tiennent sur des documents qu'ils n'ont pas vus.

1. Le tableau de calibrage : pour chaque champ et chaque tranche de confiance, la part de valeurs justes.
2. Deux règles qui ne dépendent pas de la confiance : une plaque illisible (null) et des blessés « unclear »
   vont toujours au gestionnaire, parce qu'il faut un humain pour les résoudre, même quand ils sont justes.
3. Le seuil de chaque champ : la plus basse borne de tranche au-dessus de laquelle les valeurs du jeu de
   calibrage sont justes à CIBLE près. Un document dont un champ passe sous son seuil va en relecture.
4. Sur les 700 autres : la taille de la file, les erreurs qu'elle attrape, celles qui passent.

Lancement, depuis le dossier python/ :  python -m ch13.calibrage ch13/resultats/lot-<identifiant>.json
"""

import argparse
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path

from ch13.archive import fabriquer
from ch13.extraction import CHAMPS, normaliser

BORNES = [0.0, 0.5, 0.7, 0.8, 0.85, 0.9]
CIBLE = 0.999
TAILLE_CALIBRAGE = 400
CHEMINS = {"plaque_a": ("vehicule_a", "plaque"), "contrat_a": ("vehicule_a", "numero_contrat"),
           "plaque_b": ("vehicule_b", "plaque"), "assureur_b": ("vehicule_b", "assureur")}


def valeur(arguments: dict, champ: str):
    a = normaliser(arguments)
    if champ in CHEMINS:
        objet, cle = CHEMINS[champ]
        return (a.get(objet) or {}).get(cle)
    return a.get(champ)


def tranche(confiance: float | None) -> float:
    return max(b for b in BORNES if (confiance or 0) >= b)


def par_regle(e: dict) -> bool:
    """Ce qui va au gestionnaire quelle que soit la confiance, y compris ce que le contrôle refuse encore."""
    return (not e["reussi"] or valeur(e["arguments"], "plaque_a") is None or valeur(e["arguments"], "plaque_b") is None
            or e["arguments"].get("blesses") == "unclear")


FORMES_DE_DATE = [("jj-mm-aa", r"(?<!\d)\d\d-\d\d-\d\d(?!\d)"), ("aaaa-mm-jj", r"\d{4}-\d\d-\d\d"),
                  ("jj/mm/aaaa", r"\d\d/\d\d/\d{4}"), ("jj.mm.aaaa", r"\d\d\.\d\d\.\d{4}"), ("en lettres", r"\d{1,2} [a-zéû]+ \d{4}")]


def forme_de_date(texte: str) -> str:
    """La forme d'écriture de la date, lisible dans le document : une strate observable, sans la vérité."""
    return next((nom for nom, motif in FORMES_DE_DATE if re.search(motif, texte)), "autre")


def surveiller(acceptes: list[dict], archive: dict, par_strate: int = 20) -> list[tuple]:
    """Les documents acceptés sans relecture, par forme de date ; et, pour un échantillon de par_strate documents
    dans chaque strate, la probabilité d'y voir au moins une erreur (loi hypergéométrique)."""
    strates = defaultdict(list)
    for e in acceptes:
        strates[forme_de_date(archive[e["document"]]["texte"])].append(e)
    lignes = []
    for nom, docs in sorted(strates.items()):
        n, k = len(docs), sum(any(i != "juste" for i in e["issues"].values()) for e in docs)
        m = min(par_strate, n)
        p = 1 - math.comb(n - k, m) / math.comb(n, m)
        lignes.append((nom, n, k, round(k / n, 4), round(p, 3)))
    return lignes


def separer(resultats: list[dict]) -> tuple[list[dict], list[dict]]:
    ok = [e for e in resultats if e["statut"] == "succeeded" and e["arguments"] is not None]
    etiquetes = set(x["document"] for x in random.Random(131).sample(ok, TAILLE_CALIBRAGE))
    return [e for e in ok if e["document"] in etiquetes], [e for e in ok if e["document"] not in etiquetes]


def tableau(documents: list[dict]) -> dict:
    t = defaultdict(lambda: [0, 0])   # (champ, tranche) -> [valeurs, justes]
    for e in documents:
        if par_regle(e):
            continue
        for c in CHAMPS:
            x = t[(c, tranche(e["confiance"].get(c)))]
            x[0] += 1
            x[1] += e["issues"][c] == "juste"
    return {c: {b: tuple(t[(c, b)]) for b in BORNES if t[(c, b)][0]} for c in CHAMPS}


def seuils(table: dict) -> dict:
    """Pour chaque champ, la plus basse borne b telle que les valeurs de confiance >= b soient justes à CIBLE près."""
    s = {}
    for c, lignes in table.items():
        s[c] = BORNES[-1]
        for b in BORNES:
            n = sum(v[0] for k, v in lignes.items() if k >= b)
            j = sum(v[1] for k, v in lignes.items() if k >= b)
            if n and j / n >= CIBLE:
                s[c] = b
                break
    return s


def acceptes(documents: list[dict], s: dict) -> list[dict]:
    return [e for e in documents if not par_regle(e) and all((e["confiance"].get(c) or 0) >= s[c] for c in CHAMPS)]


def file_de_relecture(documents: list[dict], s: dict) -> dict:
    regle = [e for e in documents if par_regle(e)]
    reste = [e for e in documents if not par_regle(e)]
    confiance = [e for e in reste if any((e["confiance"].get(c) or 0) < s[c] for c in CHAMPS)]
    acceptes = [e for e in reste if e not in confiance]
    fautif = lambda e: any(i != "juste" for i in e["issues"].values())
    return {"documents": len(documents), "par_regle": len(regle), "refuses_par_le_controle": sum(not e["reussi"] for e in regle),
            "par_confiance": len(confiance),
            "acceptes": len(acceptes),
            "fautifs_dans_la_file": sum(fautif(e) for e in regle + confiance),
            "fautifs_acceptes": sum(fautif(e) for e in acceptes),
            "fautifs": sum(fautif(e) for e in documents),
            "champs_faux_acceptes": [(e["document"], c, e["confiance"][c]) for e in acceptes
                                     for c, i in e["issues"].items() if i != "juste"]}


def charger(lots: list[Path]) -> list[dict]:
    """Les résultats de plusieurs lots ; pour un même document, le dernier lot l'emporte (un renvoi, un segment
    retraité)."""
    par_document = {}
    for lot in lots:
        for e in json.loads(lot.read_text(encoding="utf-8"))["resultats"]:
            if e["statut"] == "succeeded":
                par_document[e["document"]] = e
    return sorted(par_document.values(), key=lambda e: e["document"])


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 13 : calibrage de la confiance et file de relecture.")
    parser.add_argument("lots", type=Path, nargs="+", help="le lot, puis ses renvois et ses segments retraités")
    args = parser.parse_args()
    resultats = charger(args.lots)
    archive = {c["id"]: c for c in fabriquer()}
    calibrage, controle = separer(resultats)
    table = tableau(calibrage)
    print(f"Tableau de calibrage ({len(calibrage)} documents étiquetés, hors règles) : valeurs justes / valeurs")
    for c, lignes in table.items():
        print(f"  {c:14}" + "  ".join(f"≥{b:<4} {v[1]}/{v[0]}" for b, v in lignes.items()))
    s = seuils(table)
    print(f"\nSeuils (cible {CIBLE:.1%}) : {s}")
    for nom, docs in (("calibrage", calibrage), ("contrôle", controle)):
        print(f"\nFile de relecture, documents de {nom} : {json.dumps(file_de_relecture(docs, s), ensure_ascii=False)}")
    print("\nSurveillance des documents acceptés (les 1 100), par forme de date : strate, acceptés, fautifs, taux, "
          "probabilité qu'un échantillon de 20 y montre une erreur")
    for ligne in surveiller(acceptes(resultats, s), archive):
        print("  ", ligne)


if __name__ == "__main__":
    principal()
