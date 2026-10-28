"""Chapitre 6 : mesurer le choix d'outil sur vingt demandes ambiguës, catalogue par catalogue.

Pour chaque conduite (la boucle du chapitre 5, Claude Haiku 5.5, réglage par défaut) :
- le premier outil demandé est-il l'un des outils attendus ? C'est le taux de bon premier choix ;
- combien d'appels d'outils au total ;
- un outil interdit a-t-il été appelé (la résiliation) ?
- la réponse affirme-t-elle qu'il n'existe aucun dossier, alors qu'il en existe un ? C'est une
  fausse conclusion, la conséquence la plus grave d'un mauvais choix.
Les réponses se relisent ensuite : les motifs cherchés dans le texte sont grossiers.

Lancement, depuis le dossier python/ :
    python -m ch06.choix --estimer
    python -m ch06.choix --variantes dsi yao --repetitions 3 --budget-max 0.30
    python -m ch06.choix --variantes yao-consigne-contrat --repetitions 3 --budget-max 0.15
    python -m ch06.choix --variantes yao --sdk --repetitions 1 --budget-max 0.05   # le même catalogue, par l'Agent SDK
"""

import argparse
import asyncio
import json
import statistics
import tempfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import cout_maximal, francais
from assureur.systeme import Systeme
from ch05.boucle import MAX_TOKENS, MODELE, BudgetDepasse, conduire
from ch06.catalogues import INTROUVABLE, VARIANTES, premier_appel, premier_juste

DOSSIER = Path(__file__).parent


def evaluer(variante, demande: dict, premier: list[str], outils: list[str], reponse: str, systeme: Systeme) -> dict:
    attendus = demande["attendus"][variante.famille]
    dit_introuvable = bool(INTROUVABLE.search(reponse))
    return {
        "premier": premier,
        "premier_juste": premier_juste(premier, attendus),
        "nombre_appels": len(outils),
        "interdit_appele": any(o in demande.get("interdits", []) for o in outils),
        "resiliations": len(systeme.resiliations),
        "dit_introuvable": dit_introuvable,
        "fausse_conclusion": dit_introuvable and demande["dossier_existe"] is True,
    }


def lancer(client, demandes: list[dict], variantes: list[str], repetitions: int, budget_max: float,
           journal: str | None = None) -> tuple[list[dict], float]:
    essais, depense = [], 0.0
    for nom in variantes:
        v = VARIANTES[nom]
        for repetition in range(1, repetitions + 1):
            for d in demandes:
                systeme = Systeme()
                c = conduire(client, d["texte"], systeme=systeme, prompt=v.prompt, outils=v.outils,
                             executer_outil=v.executer, budget_restant=budget_max - depense, journal=journal,
                             cas=f"{nom}:{d['id']}", repetition=repetition, chapitre="06")
                depense += c.cout_dollars
                essais.append({"variante": nom, "demande": d["id"], "repetition": repetition, "fin": c.fin,
                               "tours": len(c.tours), "outils": c.outils, "reponse": c.reponse,
                               "appels": [{"outil": o, "entree": e} for t in c.tours for o, e in zip(t.outils, t.entrees)],
                               "cout_dollars": c.cout_dollars, "latence_s": c.latence_s,
                               **evaluer(v, d, premier_appel(c), c.outils, c.reponse, systeme)})
    return essais, depense


async def lancer_sdk(demandes: list[dict], nom: str, repetitions: int, budget_max: float) -> tuple[list[dict], float]:
    from ch05.agent_sdk import seance

    v = VARIANTES[nom]
    essais, depense = [], 0.0
    for repetition in range(1, repetitions + 1):
        for d in demandes:
            if budget_max - depense < 0.01:
                print(f"Arrêt avant {d['id']} : plafond presque atteint.")
                return essais, depense
            systeme = Systeme()
            with tempfile.TemporaryDirectory() as dossier:
                s = await seance(d["texte"], systeme=systeme, dossier=dossier, budget_max=budget_max - depense,
                                 cas=f"sdk-{nom}:{d['id']}", repetition=repetition, definitions=v.outils,
                                 executer_outil=v.executer, prompt=v.prompt, chapitre="06")
            depense += s.cout_dollars
            premier = s.outils[:1]  # le SDK rend les blocs dans l'ordre : le premier outil appelé
            essais.append({"variante": f"sdk-{nom}", "demande": d["id"], "repetition": repetition, "fin": s.fin,
                           "tours": s.tours, "outils": s.outils, "reponse": s.reponse, "cout_dollars": s.cout_dollars,
                           "latence_s": s.latence_s, **evaluer(v, d, premier, s.outils, s.reponse, systeme)})
    return essais, depense


def resumer(essais: list[dict]) -> list[dict]:
    lignes = []
    for nom in dict.fromkeys(e["variante"] for e in essais):
        groupe = [e for e in essais if e["variante"] == nom]
        lignes.append({
            "variante": nom, "conduites": len(groupe),
            "fins": dict(Counter(e["fin"] for e in groupe)),
            "premier_choix_juste": sum(e["premier_juste"] for e in groupe) / len(groupe),
            "demandes_mal_orientees": dict(Counter(e["demande"] for e in groupe if not e["premier_juste"])),
            "premiers_choix_faux": dict(Counter(f"{e['demande']}:{'+'.join(e['premier']) or 'aucun'}"
                                                for e in groupe if not e["premier_juste"])),
            "appels_moyens": statistics.mean(e["nombre_appels"] for e in groupe),
            "outil_interdit_appele": sum(e["interdit_appele"] for e in groupe),
            "fausses_conclusions": sum(e["fausse_conclusion"] for e in groupe),
            "cout_moyen": statistics.mean(e["cout_dollars"] for e in groupe),
            "latence_mediane_s": statistics.median(e["latence_s"] for e in groupe),
        })
    return lignes


def afficher(lignes: list[dict]) -> str:
    return "\n".join(
        f"{l['variante']:<22} bon premier choix {francais(100 * l['premier_choix_juste'], 0)} % sur {l['conduites']} ; "
        f"appels {francais(l['appels_moyens'], 2)} ; interdit appelé {l['outil_interdit_appele']} ; fausses conclusions "
        f"{l['fausses_conclusions']} ; {francais(l['cout_moyen'], 5)} $ par demande\n    mal orientées : "
        f"{l['premiers_choix_faux'] or 'aucune'}" for l in lignes)


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 6 : le choix d'outil, catalogue par catalogue.")
    parser.add_argument("--variantes", nargs="+", default=["dsi", "yao"], choices=list(VARIANTES))
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--budget-max", type=float, default=0.30)
    parser.add_argument("--demandes", nargs="*", help="ne lancer que ces demandes (leurs identifiants)")
    parser.add_argument("--sdk", action="store_true", help="passer par l'Agent SDK (une variante à la fois)")
    parser.add_argument("--estimer", action="store_true", help="gratuit : coût maximal du premier tour")
    args = parser.parse_args()

    demandes = json.loads((DOSSIER / "demandes.json").read_text(encoding="utf-8"))["demandes"]
    demandes = [d for d in demandes if not args.demandes or d["id"] in args.demandes]

    if args.sdk:
        essais, depense = asyncio.run(lancer_sdk(demandes, args.variantes[0], args.repetitions, args.budget_max))
    else:
        import anthropic

        client = anthropic.Anthropic()
        if args.estimer:
            total = 0.0
            for nom in args.variantes:
                v = VARIANTES[nom]
                for d in demandes:
                    entree = client.messages.count_tokens(model=MODELE, system=v.prompt, tools=v.outils, messages=[
                        {"role": "user", "content": d["texte"]}]).input_tokens
                    total += cout_maximal(MODELE, entree, MAX_TOKENS) * args.repetitions
            print(f"Coût maximal du premier tour : {francais(total, 4)} $ ; prévoyez trois fois plus pour les tours "
                  f"suivants, et gardez --budget-max.")
            return
        try:
            essais, depense = lancer(client, demandes, args.variantes, args.repetitions, args.budget_max)
        except BudgetDepasse as e:
            print(e)
            return

    lignes = resumer(essais)
    print(afficher(lignes))
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    etiquette = ("sdk-" if args.sdk else "") + "-".join(args.variantes)
    sortie = DOSSIER / "resultats" / f"choix-{etiquette}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "repetitions": args.repetitions,
                                  "depense_dollars": round(depense, 6), "resume": lignes, "essais": essais},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
