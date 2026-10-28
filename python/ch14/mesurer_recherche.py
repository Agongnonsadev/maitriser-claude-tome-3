"""Chapitre 14 : le rappel de la recherche, par découpage, par stratégie et par genre de question.

Une question est retrouvée à k si l'un des k premiers morceaux couvre une des unités qu'elle attend. Les
questions dont la base ne contient pas la réponse (genre « absent ») ne comptent pas dans le rappel.

La base est celle d'octobre 2026 : conditions et tableaux de l'édition 2026, procédures, export des
dossiers que la DSI avait déposé dans le dossier partagé.

Lancement, depuis le dossier python/ :
  python -m ch14.mesurer_recherche --strategies bm25 filtre                 (gratuit)
  python -m ch14.mesurer_recherche --strategies reecriture reclassement --budget-max 0.10
"""

import argparse
import json
import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import anthropic

from assureur import config
from assureur.couts import francais
from ch14.corpus import charger, decouper
from ch14.recherche import IndexBM25, chercher

DOSSIER = Path(__file__).parent
BASE_OCTOBRE = ["cg-auto-2026", "cg-habitation-2026", "tableau-auto-2026", "tableau-habitation-2026",
                "procedures-sinistres", "export-sinistres-2026-10-20"]
K = (1, 3, 5)


def questions(jeu: str = "questions") -> list[dict]:
    return json.loads((DOSSIER / "questions.json").read_text(encoding="utf-8"))[jeu]


def retrouvee(morceaux, attendus: list[str], k: int) -> bool:
    return any(set(m.unites) & set(attendus) for m in morceaux[:k])


def mesurer(client, index, q: dict, strategie: str, decoupage: str) -> dict:
    d = date.fromisoformat(q["date"]) if q.get("date") else None
    r = chercher(client, index, q["question"], strategie, max(K), q.get("produit"), d, cas=f"{strategie}:{q['id']}")
    return {"question": q["id"], "genre": q["genre"], "strategie": strategie, "decoupage": decoupage,
            "trouves": [m.identifiant for m in r["morceaux"]],
            **{f"rappel_{k}": retrouvee(r["morceaux"], q["attendus"], k) for k in K},
            "duree_s": round(r["duree_s"], 3), "dollars": r["dollars"]}


def resumer(essais: list[dict]) -> dict:
    lignes = {}
    for cle in dict.fromkeys((e["decoupage"], e["strategie"]) for e in essais):
        g = [e for e in essais if (e["decoupage"], e["strategie"]) == cle and e["genre"] != "absent"]
        par_genre = defaultdict(list)
        for e in g:
            par_genre[e["genre"]].append(e)
        lignes[" / ".join(cle)] = {
            **{f"rappel_{k}": round(sum(e[f"rappel_{k}"] for e in g) / len(g), 3) for k in K},
            "par_genre_rappel_5": {genre: f"{sum(e['rappel_5'] for e in x)}/{len(x)}" for genre, x in par_genre.items()},
            "duree_mediane_s": round(statistics.median(e["duree_s"] for e in g), 3),
            "dollars_par_question": round(statistics.mean(e["dollars"] for e in g), 6),
        }
    return lignes


def reevaluer(chemin: Path) -> dict:
    """Recompte le rappel d'un fichier de résultats avec les questions actuelles, sans appel."""
    d = json.loads(chemin.read_text(encoding="utf-8"))
    qs = {q["id"]: q for q in questions()}
    docs = charger(BASE_OCTOBRE)
    morceaux = {m.identifiant: m for methode in ("naif", "structure") for m in decouper(docs, methode)}
    for e in d["essais"]:
        trouves = [morceaux[i] for i in e["trouves"]]
        e.update({f"rappel_{k}": retrouvee(trouves, qs[e["question"]]["attendus"], k) for k in K})
    d["resume"] = resumer(d["essais"])
    chemin.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 14 : le rappel de la recherche.")
    parser.add_argument("--strategies", nargs="*", default=["bm25", "filtre"])
    parser.add_argument("--decoupages", nargs="*", default=["naif", "structure"])
    parser.add_argument("--budget-max", type=float, default=0.10)
    parser.add_argument("--reevaluer", type=Path, default=None, help="recompter un fichier de résultats, sans appel")
    args = parser.parse_args()
    if args.reevaluer:
        print(json.dumps(reevaluer(args.reevaluer)["resume"], ensure_ascii=False, indent=1))
        return
    qs = questions()
    payantes = [s for s in args.strategies if s in ("reecriture", "reclassement")]
    estimation = len(qs) * len(args.decoupages) * sum(0.0004 if s == "reecriture" else 0.0012 for s in payantes)
    if estimation > args.budget_max:
        raise SystemExit(f"Estimation large de {francais(estimation, 3)} $ au-dessus du plafond.")
    client = anthropic.Anthropic() if payantes else None
    docs = charger(BASE_OCTOBRE)
    essais = []
    for decoupage in args.decoupages:
        index = IndexBM25(decouper(docs, decoupage))
        for s in args.strategies:
            with ThreadPoolExecutor(max_workers=6 if s in payantes else 1) as pool:
                essais += list(pool.map(lambda q: mesurer(client, index, q, s, decoupage), qs))
    resume = resumer(essais)
    print(json.dumps(resume, ensure_ascii=False, indent=1))
    depense = sum(e["dollars"] for e in essais)
    print(f"Dépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / "resultats" / f"recherche-{'-'.join(args.strategies)}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "depense_dollars": round(depense, 6), "resume": resume,
                                  "essais": essais}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
