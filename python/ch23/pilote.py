"""Chapitre 23 : le pilote de six semaines à la clinique de Cotonou, et son bilan à la direction médicale.

Tout ce que ce script produit est fabriqué pour le livre, et dit comme tel : les médecins, leurs temps, l'adoption,
les corrections, les incidents et les coûts de la mission. Les seuls prix réels sont ceux des appels à l'API, mesurés
aux chapitres 20 et 22. Le script ne fait aucun appel : il fabrique les comptes rendus d'un pilote à partir de
paramètres écrits ci-dessous, puis il les analyse comme on analyserait ceux d'un vrai pilote.

Le plan du pilote :
- la question : l'assistant rend-il du temps aux médecins, sans perte de qualité ?
- la cohorte : huit médecins volontaires de Cotonou ; les témoins : six médecins de la même clinique, sans l'assistant ;
- la situation de départ : deux semaines mesurées avant le pilote, de la même façon ;
- la durée : six semaines, pour traverser la courbe en J ;
- les critères, écrits avant avec la direction médicale (CRITERES).

Lancement, depuis le dossier python/ :
    python -m ch23.pilote          # gratuit : écrit le bilan dans ch23/resultats/pilote-<graine>.json
"""

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

from assureur import config
from assureur.couts import francais

DOSSIER = Path(__file__).parent

# --- Le pilote fabriqué ------------------------------------------------------------------------------
SEMAINES_AVANT, SEMAINES_PILOTE = [-2, -1], [1, 2, 3, 4, 5, 6]
COHORTE = [f"M{i}" for i in range(1, 9)]
TEMOINS = [f"T{i}" for i in range(1, 7)]
DICTENT = {"M7", "M8"}                    # ces deux médecins dictent leurs notes
COMPTES_RENDUS_PAR_SEMAINE = 20           # par médecin
# Le temps d'un compte rendu avec le brouillon, rapporté au temps sans lui, semaine par semaine : la courbe en J.
EFFET = {1: 0.95, 2: 1.15, 3: 0.75, 4: 0.62, 5: 0.55, 6: 0.52}
# La part des comptes rendus de la cohorte partis du brouillon.
ADOPTION = {1: 0.60, 2: 0.55, 3: 0.75, 4: 0.82, 5: 0.88, 6: 0.92}
# La part des brouillons que le médecin corrige avant de valider (style compris).
CORRECTION = {1: 0.25, 2: 0.22, 3: 0.18, 4: 0.15, 5: 0.12, 6: 0.11}
# Un autre changement, pour tous : le nouveau modèle de dossier du logiciel, installé en semaine 3.
AUTRE_CHANGEMENT = {-2: 1.0, -1: 1.0, 1: 1.0, 2: 1.0, 3: 0.92, 4: 0.92, 5: 0.92, 6: 0.92}
# Semaine 4 : la DSI change le réglage de la transcription des dictées ; il est rétabli en semaine 5.
SEMAINE_TRANSCRIPTION = 4

# --- Les critères, écrits avant le pilote avec la direction médicale -----------------------------------
CRITERES = {
    "gain_net_min": 0.30,            # temps par compte rendu, semaines 5 et 6 contre la situation de départ, net des témoins
    "conclusions_inventees_max": 0,  # signalées par les médecins dans les comptes rendus validés
    "adoption_min": 0.70,            # part des comptes rendus de la cohorte partis du brouillon, en semaine 6
    "niveau_de_service": 0.95,       # part des brouillons prêts en moins de 30 s, chaque jour (chapitre 22 : 95e
                                     # centile mesuré de 23,5 s, maximum 27,5 s)
}
# Les déclencheurs de revue : un seul suffit. Un médecin déclenche quand il corrige plus du double des autres
# médecins de la cohorte la même semaine, sur au moins 10 brouillons : un seuil fixe sonnerait sur le bruit.
DECLENCHEUR_RAPPORT, DECLENCHEUR_MINIMUM = 2.0, 10

# --- Les coûts et la valeur, fictifs sauf le prix des appels -------------------------------------------
COUT_REQUETE_DOLLARS = 0.001         # pile de sûreté comprise (chapitre 20, mesuré)
VOLUME_MOIS_CLINIQUE = 1200          # comptes rendus par mois à Cotonou (volume fictif du chapitre 22)
VALEUR_HEURE_MEDECIN_FCFA = 15_000   # fixée par la direction pour le bilan
HONORAIRES_PILOTE_FCFA = 4_500_000   # la mission de Nokoué Conseil pour le pilote
JOURS_DSI, COUT_JOUR_DSI_FCFA = 12, 60_000
HEURES_FORMATION_PAR_MEDECIN = 2
EXPLOITATION_MOIS_FCFA = 150_000     # astreinte et suivi du tableau de bord, après le pilote


def fabriquer(graine: int) -> tuple[list[dict], list[dict]]:
    """Les comptes rendus du pilote, un par ligne, et la part des brouillons prêts à temps, jour par jour."""
    rng = random.Random(graine)
    base = {m: rng.uniform(11.0, 17.0) for m in COHORTE + TEMOINS}       # minutes, propre à chaque médecin
    lignes = []
    for semaine in SEMAINES_AVANT + SEMAINES_PILOTE:
        for m in COHORTE + TEMOINS:
            for i in range(COMPTES_RENDUS_PAR_SEMAINE):
                pilote = m in COHORTE and semaine > 0
                adoption, effet, correction = ADOPTION.get(semaine, 0), EFFET.get(semaine, 1), CORRECTION.get(semaine, 0)
                if pilote and m in DICTENT and semaine == SEMAINE_TRANSCRIPTION:
                    effet, correction = 0.90, 0.55
                utilise = pilote and rng.random() < adoption
                minutes = base[m] * AUTRE_CHANGEMENT[semaine] * (effet if utilise else 1.0) * rng.lognormvariate(0, 0.25)
                lignes.append({"semaine": semaine, "medecin": m, "groupe": "cohorte" if m in COHORTE else "temoins",
                               "dicte": m in DICTENT, "brouillon": utilise, "minutes": round(minutes, 1),
                               "corrige": utilise and rng.random() < correction, "conclusion_inventee": False})
    jours = []
    for semaine in SEMAINES_PILOTE:
        for jour in ("lundi", "mardi", "mercredi", "jeudi", "vendredi"):
            part = 0.91 if (semaine, jour) == (3, "jeudi") else rng.uniform(0.96, 1.0)
            jours.append({"semaine": semaine, "jour": jour, "a_temps": round(part, 3)})
    return lignes, jours


def mediane(lignes: list[dict]) -> float:
    return round(statistics.median(l["minutes"] for l in lignes), 1) if lignes else None


def par_semaine(lignes: list[dict]) -> list[dict]:
    resultat = []
    for s in SEMAINES_AVANT + SEMAINES_PILOTE:
        c = [l for l in lignes if l["semaine"] == s and l["groupe"] == "cohorte"]
        t = [l for l in lignes if l["semaine"] == s and l["groupe"] == "temoins"]
        b = [l for l in c if l["brouillon"]]
        resultat.append({"semaine": s, "cohorte_min": mediane(c), "temoins_min": mediane(t),
                         "adoption": round(len(b) / len(c), 2) if s > 0 else None,
                         "corrections": round(sum(l["corrige"] for l in b) / len(b), 2) if b else None})
    return resultat


def changement_par_medecin(lignes: list[dict], groupe: list[str]) -> dict[str, float]:
    """Pour chaque médecin : sa médiane des semaines 5 et 6, rapportée à celle de sa situation de départ, moins 1."""
    r = {}
    for m in groupe:
        avant = mediane([l for l in lignes if l["medecin"] == m and l["semaine"] in SEMAINES_AVANT])
        apres = mediane([l for l in lignes if l["medecin"] == m and l["semaine"] in (5, 6)])
        r[m] = apres / avant - 1
    return r


def difference_des_differences(cohorte: dict[str, float], temoins: dict[str, float]) -> float:
    """Le changement moyen de la cohorte moins celui des témoins : ce qui revient à l'assistant."""
    return statistics.mean(cohorte.values()) - statistics.mean(temoins.values())


def intervalle_bootstrap(cohorte: dict[str, float], temoins: dict[str, float], tirages: int = 4000,
                         graine: int = 0) -> tuple[float, float]:
    """Intervalle à 95 % de la différence des différences, en tirant les médecins avec remise."""
    rng = random.Random(graine)
    c, t = list(cohorte.values()), list(temoins.values())
    valeurs = sorted(statistics.mean(rng.choices(c, k=len(c))) - statistics.mean(rng.choices(t, k=len(t)))
                     for _ in range(tirages))
    return round(valeurs[int(0.025 * tirages)], 3), round(valeurs[int(0.975 * tirages) - 1], 3)


def declencheurs(lignes: list[dict], jours: list[dict]) -> list[str]:
    alertes = []
    for s in SEMAINES_PILOTE:
        for m in COHORTE:
            b = [l for l in lignes if l["semaine"] == s and l["medecin"] == m and l["brouillon"]]
            autres = [l for l in lignes if l["semaine"] == s and l["groupe"] == "cohorte" and l["medecin"] != m
                      and l["brouillon"]]
            if len(b) < DECLENCHEUR_MINIMUM or not autres:
                continue
            part, part_autres = sum(l["corrige"] for l in b) / len(b), sum(l["corrige"] for l in autres) / len(autres)
            if part > DECLENCHEUR_RAPPORT * part_autres:
                alertes.append(f"semaine {s} : {m} corrige {sum(l['corrige'] for l in b)} brouillons sur {len(b)} "
                               f"({francais(100 * part, 0)} %, les autres {francais(100 * part_autres, 0)} %)")
    for j in jours:
        if j["a_temps"] < CRITERES["niveau_de_service"]:
            alertes.append(f"semaine {j['semaine']}, {j['jour']} : {francais(100 * j['a_temps'], 0)} % des brouillons "
                           f"à temps (niveau de service : {francais(100 * CRITERES['niveau_de_service'], 0)} %)")
    if any(l["conclusion_inventee"] for l in lignes):
        alertes.append("conclusion inventée signalée : arrêt immédiat")
    return alertes


def bilan(lignes: list[dict], jours: list[dict], graine: int) -> dict:
    semaines = par_semaine(lignes)
    cohorte, temoins = changement_par_medecin(lignes, COHORTE), changement_par_medecin(lignes, TEMOINS)
    net = difference_des_differences(cohorte, temoins)
    avant = mediane([l for l in lignes if l["groupe"] == "cohorte" and l["semaine"] in SEMAINES_AVANT])
    apres = mediane([l for l in lignes if l["groupe"] == "cohorte" and l["semaine"] in (5, 6)])
    naif = apres / avant - 1
    adoption6 = next(s["adoption"] for s in semaines if s["semaine"] == 6)
    criteres = {
        "gain_net": {"valeur": round(-net, 3), "seuil": CRITERES["gain_net_min"], "atteint": -net >= CRITERES["gain_net_min"]},
        "conclusions_inventees": {"valeur": sum(l["conclusion_inventee"] for l in lignes), "seuil": 0,
                                  "atteint": not any(l["conclusion_inventee"] for l in lignes)},
        "adoption_semaine_6": {"valeur": adoption6, "seuil": CRITERES["adoption_min"],
                               "atteint": adoption6 >= CRITERES["adoption_min"]},
        "niveau_de_service": {"valeur": f"{sum(j['a_temps'] >= CRITERES['niveau_de_service'] for j in jours)} jours "
                                        f"sur {len(jours)}", "seuil": CRITERES["niveau_de_service"],
                              "atteint": all(j["a_temps"] >= CRITERES["niveau_de_service"] for j in jours)},
    }
    # La valeur, et ce qu'elle coûte, sur la première année, à l'échelle de la clinique.
    minutes_gagnees = avant * -net
    heures_an = minutes_gagnees * VOLUME_MOIS_CLINIQUE * 12 * adoption6 / 60
    creux = [s for s in semaines if s["semaine"] == 2][0]
    heures_creux = (creux["cohorte_min"] - avant) * len(COHORTE) * COMPTES_RENDUS_PAR_SEMAINE / 60
    couts = {"honoraires_pilote": HONORAIRES_PILOTE_FCFA, "dsi": JOURS_DSI * COUT_JOUR_DSI_FCFA,
             "formation": len(COHORTE) * HEURES_FORMATION_PAR_MEDECIN * VALEUR_HEURE_MEDECIN_FCFA,
             "creux_semaine_2": round(heures_creux * VALEUR_HEURE_MEDECIN_FCFA),
             "api_an": round(VOLUME_MOIS_CLINIQUE * 12 * COUT_REQUETE_DOLLARS * config.TAUX_FCFA),
             "exploitation_an": 12 * EXPLOITATION_MOIS_FCFA}
    total = sum(couts.values())
    valeur = round(heures_an * VALEUR_HEURE_MEDECIN_FCFA)
    # La cohorte est volontaire : si les autres médecins ne gagnaient que la moitié, que resterait-il ?
    part_prudente = (len(COHORTE) + 0.5 * len(TEMOINS)) / (len(COHORTE) + len(TEMOINS))
    valeur_prudente = round(valeur * part_prudente)
    return {
        "graine": graine, "fabrique": True, "semaines": semaines,
        "situation_de_depart_min": avant, "semaines_5_6_min": apres, "gain_naif": round(-naif, 3),
        "changement_cohorte": {m: round(v, 3) for m, v in cohorte.items()},
        "changement_temoins": {m: round(v, 3) for m, v in temoins.items()},
        "temoins_moyen": round(statistics.mean(temoins.values()), 3),
        "gain_net": round(-net, 3), "intervalle_95": [round(-x, 3) for x in reversed(intervalle_bootstrap(cohorte, temoins))],
        "criteres": criteres, "declencheurs": declencheurs(lignes, jours),
        "premiere_annee": {"minutes_gagnees_par_compte_rendu": round(minutes_gagnees, 1), "heures_rendues": round(heures_an),
                           "valeur_fcfa": valeur, "couts_fcfa": couts, "total_couts_fcfa": total,
                           "retour_sur_investissement": round((valeur - total) / total, 2),
                           "prudent": {"heures_rendues": round(heures_an * part_prudente), "valeur_fcfa": valeur_prudente,
                                       "retour_sur_investissement": round((valeur_prudente - total) / total, 2)},
                           "mois_pour_rembourser": math.ceil((total - couts["exploitation_an"] - couts["api_an"])
                                                             / (valeur / 12 - couts["exploitation_an"] / 12
                                                                - couts["api_an"] / 12))},
    }


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 23 : le pilote fabriqué et son bilan. Aucun appel.")
    parser.add_argument("--graine", type=int, default=23)
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    lignes, jours = fabriquer(args.graine)
    b = bilan(lignes, jours, args.graine)
    sortie = DOSSIER / "resultats" / f"pilote-{args.graine}.json"
    sortie.parent.mkdir(exist_ok=True)
    # Les 2 240 comptes rendus fabriqués ne sont pas gardés : la graine les refait à l'identique.
    sortie.write_text(json.dumps({**b, "jours": jours}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(b, ensure_ascii=False, indent=2))
    print(f"\nChiffres fabriqués pour le livre ; {sortie}")


if __name__ == "__main__":
    principal()
