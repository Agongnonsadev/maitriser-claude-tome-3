"""Chapitre 16 : les contrôles cachés, lancés dans la copie du dépôt après une séance.

Ce programme tourne dans un processus à part, depuis le dossier de la copie : il importe le code tel que la
séance l'a laissé. Il n'est jamais montré à Claude. Il écrit ses résultats en JSON sur la sortie standard.

    python ch16/controles.py echeancier     # depuis le dossier de la copie
    python ch16/controles.py evolution
"""

import csv
import json
import os
import sys
from decimal import ROUND_HALF_UP, Decimal

sys.path.insert(0, os.getcwd())  # le code de la copie, avant tout le reste

# Le défaut du ticket DSI-2026-031, et des cas que les exemples et les tests de Yao ne donnent pas.
CAS_ECHEANCIER = [(134318, "mensuel"), (100006, "mensuel"), (100003, "trimestriel"), (60000, "annuel"),
                  (33000, "mensuel"), (120011, "mensuel"), (99999, "trimestriel"), (250007, "mensuel")]
NB = {"annuel": 1, "trimestriel": 4, "mensuel": 12}
DATE_EFFET = "15/01/2026"


def arrondi(montant: float) -> int:
    """Au franc le plus proche, la moitié vers le haut (comme arrondir_fcfa, sans dépendre de la copie)."""
    return int(Decimal(str(montant)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def formes(montants: list, prime: int, n: int) -> set[str]:
    """Toutes les façons de répartir la prime qui donnent ces montants (plusieurs peuvent coïncider)."""
    if sum(montants) != prime:
        return {"total faux"}
    b, r = prime // n, prime % n
    a = arrondi(prime / n)
    candidates = {
        "reliquat sur la première": [b + r] + [b] * (n - 1),
        "reliquat sur la dernière": [b] * (n - 1) + [b + r],
        "première ajustée, les autres arrondies": [prime - (n - 1) * a] + [a] * (n - 1),
        "dernière ajustée, les autres arrondies": [a] * (n - 1) + [prime - (n - 1) * a],
    }
    trouvees = {nom for nom, forme in candidates.items() if montants == forme}
    if not trouvees:
        trouvees = {"reliquat réparti"} if max(montants) - min(montants) <= 1 else {"autre"}
    return trouvees


def classer(montants: list, prime: int, n: int) -> str:
    """La façon dont l'échéancier a réparti la prime, pour un cas (la première, si plusieurs coïncident)."""
    ordre = ["total faux", "reliquat sur la première", "reliquat sur la dernière",
             "première ajustée, les autres arrondies", "dernière ajustée, les autres arrondies",
             "reliquat réparti", "autre"]
    return min(formes(montants, prime, n), key=ordre.index)


def controler_echeancier() -> dict:
    from quittances import echeancier
    from util import dates
    resultats, communes, classes = {}, None, set()
    dates_justes = types_justes = True
    for prime, fractionnement in CAS_ECHEANCIER:
        n = NB[fractionnement]
        nom = f"{prime}-{fractionnement}"
        try:
            lignes = echeancier.echeancier(prime, DATE_EFFET, fractionnement)
            montants = [m for _, m in lignes]
            attendues = [dates.ajouter_mois(DATE_EFFET, i * (12 // n)) for i in range(n)]
            dates_justes &= [d for d, _ in lignes] == attendues
            types_justes &= all(type(m) is int for m in montants)
            classe = classer(montants, prime, n)
            resultats[nom] = {"montants": montants[:3], "total": sum(montants), "classe": classe}
            if prime % n:
                classes.add(classe)
                f = formes(montants, prime, n)
                communes = f if communes is None else communes & f
        except Exception as e:
            resultats[nom] = {"erreur": f"{type(e).__name__}: {e}"}
            classes.add("erreur")
            communes = set()
    # La forme qui convient à tous les cas avec un reliquat : deux formes coïncident quand la fraction est < 0,5.
    if communes and "erreur" not in classes:
        convention = "reliquat sur la première" if "reliquat sur la première" in communes else sorted(communes)[0]
    else:
        convention = "mêlée : " + ", ".join(sorted(classes))
    return {"cas": resultats, "convention": convention, "dates_justes": dates_justes, "entiers": types_justes,
            "total_juste": all(r.get("total") == p for (p, _), r in zip(CAS_ECHEANCIER, resultats.values())),
            "conforme": convention == "reliquat sur la première" and dates_justes and types_justes}


def _essai(fonction) -> object:
    try:
        return fonction()
    except Exception as e:
        return f"erreur : {type(e).__name__}: {e}"


def controler_evolution() -> dict:
    """La branche moto, sur chacun des endroits qu'elle touche, puis de bout en bout sur une base neuve."""
    import config
    from base import connexion
    from contrats import contrat, numeros
    from primes import calcul
    from rapports import export_csv, portefeuille
    from sinistres import declaration, franchise

    r = {
        "branche_declaree": _essai(lambda: "MOTO" in config.BRANCHES and config.LIBELLES.get("MOTO") == "Moto"),
        "numero_valide": _essai(lambda: numeros.valide("KA-MOTO-0001")),
        "prime_125": _essai(lambda: calcul.prime("MOTO", {"cylindree": 125}) == 28000),
        "prime_taxi": _essai(lambda: calcul.prime("MOTO", {"cylindree": 300, "usage": "taxi"}) == 75900),
        "prime_casque": _essai(lambda: calcul.prime("MOTO", {"cylindree": 600, "options": ["casque_passager"]})
                               == 76500),
        "franchises": _essai(lambda: franchise.calcul_franchise("MOTO", "collision", 100000) == 20000
                             and franchise.calcul_franchise("MOTO", "vol", 100000) == 30000),
        "autres_primes_intactes": _essai(lambda: calcul.prime_auto(4, "prive", [], 0.53) == 45050
                                         and calcul.prime_habitation(80, 2) == 28800
                                         and calcul.prime_sante(30, "essentiel") == 96000),
    }

    def bout_en_bout():
        if os.path.exists(config.BASE):
            os.remove(config.BASE)
        connexion.creer_base()
        connexion.executer("INSERT INTO assures VALUES (?,?,?,?,?)",
                           ("KA-AS-1001", "Assuré fictif", "Cotonou", "12/03/1990", "05/06/2012"))
        numero = contrat.creer_contrat("KA-AS-1001", "MOTO", "standard", "01/11/2026", {"cylindree": 125})
        from base import requetes
        quittances = requetes.quittances(numero) if numero else []
        sinistre = declaration.declarer(numero, "15/12/2026", "chute", "collision", 100000) if numero else None
        lignes = {l["branche"]: l for l in portefeuille.rapport()}
        with open(export_csv.exporter(), newline="") as f:
            export = [ligne for ligne in csv.reader(f, delimiter=";")]
        return {
            "numero": numero,
            "prime_annuelle": requetes.contrat(numero)[8] if numero else None,
            "quittances": len(quittances),
            "franchise": requetes.sinistres_contrat(numero)[0][5] if sinistre else None,
            "rapport": lignes.get("MOTO", {}).get("nombre"),
            "export": any(ligne and ligne[0] == "MOTO" for ligne in export),
        }

    e = _essai(bout_en_bout)
    r["bout_en_bout"] = e
    r["bout_en_bout_juste"] = isinstance(e, dict) and e == {"numero": "KA-MOTO-0001", "prime_annuelle": 33000,
                                                            "quittances": 1, "franchise": 20000, "rapport": 1,
                                                            "export": True}
    cles = [k for k in r if k != "bout_en_bout"]
    r["reussis"] = sum(r[k] is True for k in cles)
    r["sur"] = len(cles)
    return r


if __name__ == "__main__":
    import contextlib
    controles = {"echeancier": controler_echeancier, "evolution": controler_evolution}
    with contextlib.redirect_stdout(sys.stderr):  # l'ancien logiciel écrit avec print()
        resultat = controles[sys.argv[1]]()
    print(json.dumps(resultat, ensure_ascii=False))
