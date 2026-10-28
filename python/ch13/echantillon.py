"""Chapitre 13 : mettre le prompt au point sur un échantillon, avant le lot.

Soixante-dix constats de l'archive, dix par difficulté, tirés au hasard (graine fixe), passent par l'API
synchrone avec chaque version du prompt. On compte, par difficulté, les champs justes et les documents
sans faute, deux fois : sur la sortie brute du modèle, puis après la correction des plaques par le code
(normaliser_plaque). C'est le taux de documents qui passent le contrôle qui fixera le nombre de
documents à renvoyer après le lot.

Lancement, depuis le dossier python/ :  python -m ch13.echantillon --versions v1 v2 --budget-max 0.10
Renoter un fichier sans appel :          python -m ch13.echantillon --reevaluer ch13/resultats/<fichier>.json
"""

import argparse
import json
import random
import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import anthropic

from assureur import config
from assureur.couts import cout, francais
from assureur.journal import noter
from ch13.archive import DIFFICULTES, fabriquer
from ch13.extraction import MODELE, evaluer, lire, parametres

DOSSIER = Path(__file__).parent


def tirer(archive: list[dict], par_difficulte: int = 10) -> list[dict]:
    r, choix = random.Random(130), []
    for d, _ in DIFFICULTES:
        choix += r.sample([c for c in archive if c["difficulte"] == d], par_difficulte)
    return choix


def extraire(client, version: str, document: dict, modele: str = MODELE) -> dict:
    r = client.messages.create(**parametres(version, document["texte"], modele))
    c = cout(modele, r.usage)
    noter(getattr(r, "_request_id", None), modele, c, chapitre="13", etape="echantillon", cas=f"{version}:{document['id']}")
    return {"version": version, "modele": modele, "document": document["id"], "difficulte": document["difficulte"],
            "arguments": lire(r), "stop_reason": r.stop_reason, "cout_dollars": c.dollars,
            "lecture_cache": c.lecture_cache, "sortie": c.sortie}


def noter_essais(essais: list[dict], archive: dict[str, dict]) -> None:
    """Ajoute à chaque essai son évaluation brute et son évaluation après correction par le code."""
    for e in essais:
        e["brut"] = evaluer(archive[e["document"]], e["arguments"])
        e["corrige"] = evaluer(archive[e["document"]], e["arguments"], corriger=True)


def resumer(essais: list[dict], cle: str) -> dict:
    lignes = {}
    for v in dict.fromkeys(e["version"] for e in essais):
        g = [e for e in essais if e["version"] == v]
        par_difficulte = defaultdict(lambda: [0, 0, 0, 0])   # champs justes, champs, sans faute, documents
        for e in g:
            x, ev = par_difficulte[e["difficulte"]], e[cle]
            x[0] += sum(i == "juste" for i in ev["issues"].values())
            x[1] += len(ev["issues"])
            x[2] += ev["reussi"] and all(i == "juste" for i in ev["issues"].values())
            x[3] += 1
        lignes[v] = {
            "champs_justes": round(sum(x[0] for x in par_difficulte.values()) / sum(x[1] for x in par_difficulte.values()), 3),
            "documents_sans_faute": sum(x[2] for x in par_difficulte.values()),
            "documents": len(g),
            "par_difficulte": {d: {"champs_justes": round(x[0] / x[1], 3), "documents_sans_faute": x[2], "sur": x[3]}
                               for d, x in par_difficulte.items()},
            "erreurs_de_controle": sum(bool(e[cle]["erreurs"]) for e in g),
            "cout_par_document": statistics.mean(e["cout_dollars"] for e in g),
        }
    return lignes


def afficher(resume: dict) -> None:
    for cle in ("brut", "corrige"):
        print(f"--- {cle}")
        for v, r in resume[cle].items():
            print(f"{v} : {r['champs_justes']:.1%} de champs justes, {r['documents_sans_faute']} documents sans faute "
                  f"sur {r['documents']}, {r['erreurs_de_controle']} refusés par le contrôle")
            print("     " + " ; ".join(f"{d} {x['documents_sans_faute']}/{x['sur']}" for d, x in r["par_difficulte"].items()))


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 13 : le prompt mis au point sur un échantillon.")
    parser.add_argument("--versions", nargs="*", default=["v1", "v2"])
    parser.add_argument("--modele", default=MODELE)
    parser.add_argument("--budget-max", type=float, default=0.10)
    parser.add_argument("--reevaluer", type=Path, default=None,
                        help="renoter un fichier de résultats avec la notation et la correction actuelles, sans appel")
    args = parser.parse_args()
    archive = {c["id"]: c for c in fabriquer()}
    if args.reevaluer:
        d = json.loads(args.reevaluer.read_text(encoding="utf-8"))
        for e in d["essais"]:
            for k in ("issues", "erreurs", "confiance", "reussi"):
                e.pop(k, None)
        noter_essais(d["essais"], archive)
        d["resume"] = {cle: resumer(d["essais"], cle) for cle in ("brut", "corrige")}
        args.reevaluer.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        afficher(d["resume"])
        return

    echantillon = tirer(list(archive.values()))
    # Large : 0,0006 $ par document pour Haiku 5.5, vingt fois plus pour Sonnet 5.5 (assureur/couts.py).
    if len(echantillon) * len(args.versions) * 0.0006 * (20 if args.modele != MODELE else 1) > args.budget_max:
        raise SystemExit("Estimation au-dessus du plafond.")
    client = anthropic.Anthropic()
    with ThreadPoolExecutor(max_workers=6) as pool:
        essais = list(pool.map(lambda t: extraire(client, *t, args.modele), [(v, d) for v in args.versions for d in echantillon]))
    noter_essais(essais, archive)
    depense = sum(e["cout_dollars"] for e in essais)
    resume = {cle: resumer(essais, cle) for cle in ("brut", "corrige")}
    afficher(resume)
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    suffixe = "" if args.modele == MODELE else f"-{args.modele.removeprefix('claude-')}"
    sortie = DOSSIER / "resultats" / f"echantillon-{'-'.join(args.versions)}{suffixe}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": args.modele, "depense_dollars": round(depense, 6),
                                  "resume": resume, "essais": essais}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
