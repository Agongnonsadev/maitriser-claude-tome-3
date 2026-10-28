"""Chapitre 2 : chiffrer un cas d'usage avant de concevoir quoi que ce soit.

Pour chaque cas d'usage du fichier, et chaque modèle candidat :
1. compter les tokens d'entrée des exemples (count_tokens, gratuit) : le prompt système d'un
   côté, le message de l'utilisateur de l'autre ;
2. mesurer les tokens de sortie sur les mêmes exemples (--mesurer : de vrais appels, payants),
   ou reprendre la sortie supposée du fichier ;
3. calculer le coût d'une unité de travail (une déclaration, un constat) et le coût mensuel,
   puis appliquer la marge.

Une conversation renvoie tout son historique à chaque tour, puisque l'API ne garde rien d'un
appel à l'autre : l'entrée grandit de tour en tour (voir entrees_par_tour).

C'est un ordre de grandeur pour décider, pas un devis : le prototype n'a ni outils ni garde-fous,
qui ajouteront des tokens. La marge est là pour ça ; les chapitres suivants mesurent le vrai système.

Lancement, depuis le dossier python/ :
    python -m ch02.chiffrer ch02/kanvo.json                              # gratuit : comptage seulement
    python -m ch02.chiffrer ch02/kanvo.json --mesurer --budget-max 0.20  # quelques vrais appels
"""

import argparse
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from assureur import config
from assureur.couts import cout, cout_maximal, cout_tokens, francais
from assureur.journal import noter

DOSSIER = Path(__file__).parent


def entrees_par_tour(systeme: int, message: int, reponse: int, tours: int) -> list[int]:
    """Les tokens d'entrée de chaque tour d'une conversation de `tours` tours.

    Au tour k (à partir de 1), la requête contient le prompt système, les k - 1 échanges
    précédents (un message et une réponse chacun) et le nouveau message.
    """
    return [systeme + (k - 1) * (message + reponse) + message for k in range(1, tours + 1)]


def cout_unite(modele: str, systeme: int, message: int, reponse: int, tours: int) -> float:
    """Le coût en dollars d'une unité de travail : la somme des requêtes de tous ses tours."""
    return sum(cout_tokens(modele, entree, reponse) for entree in entrees_par_tour(systeme, message, reponse, tours))


@dataclass
class Chiffrage:
    cas: str
    nom: str
    modele: str
    unite: str
    unites_par_mois: int
    tours: int
    tokens_systeme: int        # le prompt système, compté
    tokens_message: int        # un message de l'utilisateur, moyenne comptée sur les exemples
    tokens_reponse: int        # une réponse : moyenne mesurée, ou sortie supposée
    reponse_mesuree: bool
    tokens_reflexion: int      # dans la réponse mesurée, réflexion comprise dans tokens_reponse
    reponses_coupees: int      # arrêtées par max_tokens : leur sortie est sous-estimée
    cout_unite: float
    cout_mois: float
    cout_mois_avec_marge: float


class BudgetDepasse(Exception):
    """Le prochain appel de mesure pourrait faire dépasser --budget-max : on s'arrête avant."""


def compter(client, modele: str, systeme: str, exemple: str) -> tuple[int, int]:
    """(tokens du prompt système, tokens du message) pour un exemple, par deux comptages gratuits."""
    messages = [{"role": "user", "content": exemple}]
    avec = client.messages.count_tokens(model=modele, system=systeme, messages=messages).input_tokens
    sans = client.messages.count_tokens(model=modele, messages=messages).input_tokens
    return avec - sans, sans


def chiffrer(donnees: dict, client, mesurer: bool = False, budget_max: float | None = None,
             journal: str | None = None, seulement: list[str] | None = None) -> tuple[list[Chiffrage], float]:
    """Chiffre chaque cas d'usage pour chacun de ses modèles. Rend les chiffrages et la dépense
    des appels de mesure (0 sans --mesurer). seulement : les identifiants des cas à traiter."""
    marge = donnees.get("marge", 1.0)
    depense = 0.0
    resultats = []
    for cas in donnees["cas"]:
        if seulement and cas["id"] not in seulement:
            continue
        for modele in cas["modeles"]:
            systemes, messages, reponses, reflexions, coupees = [], [], [], [], 0
            for exemple in cas["exemples"]:
                tokens_systeme, tokens_message = compter(client, modele, cas["systeme"], exemple)
                systemes.append(tokens_systeme)
                messages.append(tokens_message)
                if not mesurer:
                    continue
                pire = cout_maximal(modele, tokens_systeme + tokens_message, cas["max_tokens"])
                if budget_max is not None and depense + pire > budget_max:
                    raise BudgetDepasse(
                        f"Arrêt avant d'appeler {modele} sur « {cas['id']} » : {francais(depense, 4)} $ "
                        f"déjà dépensés, jusqu'à {francais(pire, 4)} $ de plus, plafond {francais(budget_max, 2)} $.")
                reponse = client.messages.create(
                    model=modele, max_tokens=cas["max_tokens"], system=cas["systeme"],
                    messages=[{"role": "user", "content": exemple}])
                c = cout(modele, reponse.usage)
                depense += c.dollars
                reponses.append(c.sortie)
                reflexions.append(c.reflexion)
                coupees += reponse.stop_reason == "max_tokens"
                noter(getattr(reponse, "_request_id", None), modele, c, chemin=journal,
                      chapitre="02", cas=cas["id"], stop_reason=reponse.stop_reason)
            systeme = round(statistics.mean(systemes))
            message = round(statistics.mean(messages))
            reponse_moyenne = round(statistics.mean(reponses)) if reponses else cas["sortie_supposee"]
            unite = cout_unite(modele, systeme, message, reponse_moyenne, cas["tours"])
            resultats.append(Chiffrage(
                cas=cas["id"], nom=cas["nom"], modele=modele, unite=cas["unite"],
                unites_par_mois=cas["unites_par_mois"], tours=cas["tours"],
                tokens_systeme=systeme, tokens_message=message, tokens_reponse=reponse_moyenne,
                reponse_mesuree=bool(reponses),
                tokens_reflexion=round(statistics.mean(reflexions)) if reflexions else 0,
                reponses_coupees=coupees,
                cout_unite=unite, cout_mois=unite * cas["unites_par_mois"],
                cout_mois_avec_marge=unite * cas["unites_par_mois"] * marge))
    return resultats, depense


def afficher(resultats: list[Chiffrage], marge: float) -> str:
    lignes = []
    for cas in dict.fromkeys(r.cas for r in resultats):
        groupe = [r for r in resultats if r.cas == cas]
        r0 = groupe[0]
        lignes.append(f"\n{r0.nom} : {francais(r0.unites_par_mois, 0)} {r0.unite}s par mois, "
                      f"{r0.tours} tour{'s' if r0.tours > 1 else ''} par {r0.unite}")
        for r in groupe:
            source = "mesurée" if r.reponse_mesuree else "supposée"
            avec_marge = r.cout_mois_avec_marge
            lignes.append(
                f"  {r.modele:<18} système {r.tokens_systeme:>4}  message {r.tokens_message:>4}  "
                f"réponse {r.tokens_reponse:>4} ({source})  "
                f"par {r.unite} {francais(r.cout_unite, 4)} $  par mois {francais(r.cout_mois, 2)} $  "
                f"avec la marge ×{francais(marge, 1)} : {francais(avec_marge, 2)} $ "
                f"(≈ {francais(avec_marge * config.TAUX_FCFA, 0)} FCFA ; {francais(avec_marge * config.TAUX_EUR, 2)} €)")
            if r.reponses_coupees:
                lignes.append(f"    ⚠ {r.reponses_coupees} réponse(s) coupée(s) par max_tokens : sortie sous-estimée, "
                              f"relevez max_tokens et remesurez.")
    return "\n".join(lignes)


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chiffrer des cas d'usage avant de concevoir.")
    parser.add_argument("fichier", type=Path)
    parser.add_argument("--mesurer", action="store_true", help="mesurer la sortie par de vrais appels (payant)")
    parser.add_argument("--budget-max", type=float, default=0.20, help="plafond des appels de mesure, en dollars")
    parser.add_argument("--cas", nargs="*", help="ne traiter que ces cas d'usage (leurs identifiants)")
    args = parser.parse_args()

    import anthropic  # ici, pour que les tests n'aient pas besoin du réseau

    donnees = json.loads(args.fichier.read_text(encoding="utf-8"))
    resultats, depense = chiffrer(donnees, anthropic.Anthropic(), mesurer=args.mesurer, budget_max=args.budget_max,
                                  seulement=args.cas)
    print(f"{donnees['client']} — {donnees.get('source', '')}")
    print(afficher(resultats, donnees.get("marge", 1.0)))
    for ecarte in donnees.get("ecartes", []):
        print(f"\nÉcarté : {ecarte['nom']}. {ecarte['raison']}")
    print(f"\nAppels de mesure : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")

    sortie = DOSSIER / "resultats" / f"chiffrage-{date.today().isoformat()}{'-mesure' if args.mesurer else ''}{''.join('-' + c for c in args.cas or [])}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({
        "date": date.today().isoformat(), "fichier": args.fichier.name, "marge": donnees.get("marge", 1.0),
        "mesure": args.mesurer, "depense_mesure_dollars": round(depense, 6),
        "chiffrages": [asdict(r) for r in resultats],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
