"""Chapitre 13 : l'archive entière en un lot, par la Message Batches API.

Trois commandes, depuis le dossier python/ :
  python -m ch13.lot envoyer --version v3 --budget-max 0.60
      prépare une requête par constat (custom_id = l'identifiant du document), estime le coût, envoie le
      lot et écrit son état dans ch13/resultats/lot-<identifiant>.json ;
  python -m ch13.lot suivre ch13/resultats/lot-<identifiant>.json --attendre
      interroge le lot jusqu'à sa fin, puis télécharge les résultats, les associe aux documents par
      custom_id (l'ordre n'est pas garanti), corrige les plaques, contrôle et note chaque extraction ;
  python -m ch13.lot renvoyer ch13/resultats/lot-<identifiant>.json --budget-max 0.05
      envoie un second lot avec les seuls échecs : les requêtes en erreur ou expirées, telles quelles, et
      les extractions refusées par le contrôle, avec la réponse du modèle et les erreurs à corriger.

Le lot coûte la moitié du prix de l'API synchrone (REMISE_LOT dans assureur/couts.py).
"""

import argparse
import json
import re
import statistics
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from assureur import config
from assureur.couts import cout, francais
from assureur.journal import noter
from ch13.archive import fabriquer
from ch13.echantillon import tirer
from ch13.extraction import MODELE, evaluer, parametres

DOSSIER = Path(__file__).parent / "resultats"
# Coût moyen d'une extraction synchrone mesuré sur l'échantillon (0,0410 $ pour 70 documents en v3),
# arrondi au-dessus : l'estimation d'un lot est la moitié, avec une marge de 50 %.
COUT_SYNCHRONE = 0.0006


def requete(version: str, document: dict, messages: list | None = None, modele: str = MODELE,
            cache: str | None = "prefixe") -> dict:
    p = parametres(version, document["texte"], modele, cache)
    if messages:
        p["messages"] = messages
    return {"custom_id": document["id"], "params": p}


def envoyer(client, requetes: list[dict], etat: dict) -> Path:
    lot = client.messages.batches.create(requests=requetes)
    etat |= {"lot": lot.id, "cree": lot.created_at.isoformat(), "expire": lot.expires_at.isoformat(),
             "requetes": len(requetes)}
    chemin = DOSSIER / f"lot-{lot.id}.json"
    chemin.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Lot {lot.id} envoyé : {len(requetes)} requêtes. État : {chemin}")
    return chemin


def recuperer(client, chemin: Path, attendre: bool, intervalle: int = 60) -> dict:
    etat = json.loads(chemin.read_text(encoding="utf-8"))
    while True:
        lot = client.messages.batches.retrieve(etat["lot"])
        n = lot.request_counts
        print(f"{datetime.now():%H:%M:%S} {lot.processing_status} : {n.processing} en cours, {n.succeeded} réussies, "
              f"{n.errored} en erreur, {n.expired} expirées, {n.canceled} annulées")
        if lot.processing_status == "ended" or not attendre:
            break
        time.sleep(intervalle)
    if lot.processing_status != "ended":
        return etat
    archive = {c["id"]: c for c in fabriquer()}
    resultats, depense = [], 0.0
    for r in client.messages.batches.results(etat["lot"]):
        doc = archive[r.custom_id]
        e = {"document": doc["id"], "difficulte": doc["difficulte"], "mois": doc["mois"], "statut": r.result.type}
        if r.result.type == "succeeded":
            m = r.result.message
            c = cout(etat["modele"], m.usage, lot=True)
            depense += c.dollars
            noter(None, etat["modele"], c, chapitre="13", etape=etat["etape"], cas=f"{etat['lot']}:{doc['id']}")
            appel = next((b for b in m.content if b.type == "tool_use"), None)
            e |= {"arguments": appel.input if appel else None, "tool_use_id": appel.id if appel else None,
                  "stop_reason": m.stop_reason, "cout_dollars": c.dollars, "lecture_cache": c.lecture_cache,
                  "ecriture_cache": c.ecriture_cache, "entree": c.entree, "sortie": c.sortie}
            e |= evaluer(doc, e["arguments"], corriger=True)
        elif r.result.type == "errored":
            e["erreur_api"] = r.result.error.error.type
        resultats.append(e)
    etat |= {"termine": lot.ended_at.isoformat(), "duree_minutes": round((lot.ended_at - lot.created_at).total_seconds() / 60, 1),
             "depense_dollars": round(depense, 6), "resultats": sorted(resultats, key=lambda e: e["document"])}
    chemin.write_text(json.dumps(etat, ensure_ascii=False, indent=1), encoding="utf-8")
    return etat


def echecs(etat: dict) -> list[dict]:
    """Ce qu'il faut renvoyer : les requêtes qui n'ont pas abouti, et les extractions refusées par le contrôle."""
    return [e for e in etat["resultats"] if e["statut"] != "succeeded" or not e["reussi"]]


def resumer(etat: dict) -> None:
    res = etat["resultats"]
    ok = [e for e in res if e["statut"] == "succeeded"]
    sans_faute = [e for e in ok if e["reussi"] and all(i == "juste" for i in e["issues"].values())]
    champs = [i for e in ok for i in e["issues"].values()]
    print(f"Lot {etat['lot']} : {len(res)} résultats en {etat['duree_minutes']} minutes ; "
          f"{dict(Counter(e['statut'] for e in res))}")
    print(f"Champs justes : {sum(i == 'juste' for i in champs) / len(champs):.2%} ; documents sans faute : "
          f"{len(sans_faute)} ; refusés par le contrôle : {sum(not e['reussi'] for e in ok)}")
    print(f"Issues des champs : {dict(Counter(champs))}")
    lus = sum(e["lecture_cache"] for e in ok)
    print(f"Cache : {lus} tokens lus, {sum(e['ecriture_cache'] for e in ok)} écrits, {sum(e['entree'] for e in ok)} "
          f"hors cache ; requêtes servies par le cache : {sum(e['lecture_cache'] > 0 for e in ok)} sur {len(ok)}")
    d = etat["depense_dollars"]
    print(f"Dépense : {francais(d, 4)} $ (≈ {francais(d * config.TAUX_FCFA, 1)} FCFA), "
          f"soit {francais(statistics.mean(e['cout_dollars'] for e in ok), 6)} $ par document")


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 13 : l'archive en un lot.")
    sous = parser.add_subparsers(dest="commande", required=True)
    p = sous.add_parser("envoyer")
    p.add_argument("--version", default="v3")
    p.add_argument("--taille", type=int, default=None, help="les N premiers documents seulement")
    p.add_argument("--echantillon", action="store_true", help="les 70 documents de l'échantillon (ch13.echantillon)")
    p.add_argument("--motif", default=None, help="les documents dont le texte contient ce motif (expression régulière)")
    p.add_argument("--modele", default=MODELE)
    p.add_argument("--cache", choices=["prefixe", "automatique", "aucun"], default="prefixe")
    p.add_argument("--prechauffer", action="store_true",
                   help="une requête synchrone avant le lot, pour que le préfixe soit déjà dans le cache")
    p.add_argument("--budget-max", type=float, default=0.60)
    p = sous.add_parser("suivre")
    p.add_argument("etat", type=Path)
    p.add_argument("--attendre", action="store_true")
    p = sous.add_parser("renvoyer")
    p.add_argument("etat", type=Path)
    p.add_argument("--budget-max", type=float, default=0.05)
    args = parser.parse_args()
    client = anthropic.Anthropic()

    if args.commande == "envoyer":
        archive = tirer(fabriquer()) if args.echantillon else fabriquer()[: args.taille]
        if args.motif:
            archive = [d for d in archive if re.search(args.motif, d["texte"])]
        # Sonnet 5.5 coûte vingt fois Haiku 5.5 par token (assureur/couts.py).
        estimation = len(archive) * COUT_SYNCHRONE / 2 * 1.5 * (20 if args.modele != MODELE else 1)
        print(f"Estimation : {francais(estimation, 3)} $ pour {len(archive)} documents.")
        if estimation > args.budget_max:
            raise SystemExit("Estimation au-dessus du plafond.")
        cache = None if args.cache == "aucun" else args.cache
        etat = {"etape": "lot", "version": args.version, "modele": args.modele, "cache": args.cache, "motif": args.motif}
        if args.prechauffer:
            r = client.messages.create(**requete(args.version, archive[0], modele=args.modele, cache=cache)["params"])
            c = cout(args.modele, r.usage)
            noter(getattr(r, "_request_id", None), args.modele, c, chapitre="13", etape="prechauffage", cas=archive[0]["id"])
            etat["prechauffage"] = {"ecriture_cache": c.ecriture_cache, "lecture_cache": c.lecture_cache,
                                    "cout_dollars": c.dollars}
            print(f"Préchauffage : {c.ecriture_cache} tokens écrits dans le cache, {c.lecture_cache} lus.")
        envoyer(client, [requete(args.version, d, modele=args.modele, cache=cache) for d in archive], etat)
    elif args.commande == "suivre":
        etat = recuperer(client, args.etat, args.attendre)
        if "resultats" in etat:
            resumer(etat)
    else:
        etat = json.loads(args.etat.read_text(encoding="utf-8"))
        archive = {c["id"]: c for c in fabriquer()}
        requetes = []
        for e in echecs(etat):
            doc = archive[e["document"]]
            if e["statut"] != "succeeded" or e["arguments"] is None:
                requetes.append(requete(etat["version"], doc, modele=etat["modele"]))
                continue
            # Le renvoi garde le préfixe en cache : la conversation ne change que la fin du prompt.
            # Un lot n'exécute pas d'outil en cours de requête, mais une requête peut porter une conversation :
            # le document, la réponse refusée, et les erreurs du contrôle en tool_result.
            requetes.append(requete(etat["version"], doc, [
                {"role": "user", "content": f"Document :\n\n{doc['texte']}"},
                {"role": "assistant", "content": [{"type": "tool_use", "id": e["tool_use_id"], "name": "extraire_constat",
                                                   "input": e["arguments"]}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": e["tool_use_id"], "is_error": True,
                                              "content": "Erreurs de validation :\n- " + "\n- ".join(e["erreurs"])
                                              + "\nCorrigez ces champs, et rappelez l'outil avec tous ses arguments."}]}],
                modele=etat["modele"]))
        print(f"{len(requetes)} échecs à renvoyer.")
        if not requetes:
            return
        if len(requetes) * COUT_SYNCHRONE * 2 > args.budget_max:   # une conversation plus longue : large
            raise SystemExit("Estimation au-dessus du plafond.")
        envoyer(client, requetes, {"etape": "renvoi", "version": etat["version"], "modele": etat["modele"],
                                   "cache": "prefixe", "lot_initial": etat["lot"]})


if __name__ == "__main__":
    principal()
