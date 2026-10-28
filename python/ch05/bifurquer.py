"""Chapitre 5 : reprendre et bifurquer une séance de l'agent des sinistres (Claude Agent SDK).

1. Le tronc : Mme Akplogan demande où en est son dossier. L'agent consulte le système et répond.
2. Deux jours plus tard, le système a changé : l'expert est passé, son rapport est arrivé. Les
   résultats d'outils gardés dans la séance sont donc périmés.
3. L'assurée revient, avec l'un de deux messages : un message neutre (« où en est mon dossier ? »)
   ou un message qui laisse deviner le changement (« l'expert est passé hier »). Pour chacun,
   trois façons de lui répondre :
   - A, bifurcation sans rien signaler : la séance reprend avec ses anciens résultats ;
   - B, bifurcation avec un signalement : on dit à la séance reprise ce qui a pu changer ;
   - C, nouvelle séance, partie d'un résumé de l'échange : pas d'anciens résultats du tout.
   A et B partent du tronc par fork_session : chacune a son propre session_id, et le tronc reste
   intact. La bifurcation copie l'historique, pas le système : le changement vaut pour toutes.

Le coût qu'annonce le SDK pour une séance reprise ou bifurquée comprend celui du tronc : le coût
propre d'une branche est la différence. Additionner les total_cost_usd compterait le tronc
plusieurs fois.

Lancement, depuis le dossier python/ :  python -m ch05.bifurquer --budget-max 0.10
"""

import argparse
import asyncio
import json
import tempfile
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import francais
from assureur.systeme import Systeme
from ch05.agent_sdk import Seance, seance

DOSSIER = Path(__file__).parent

TRONC = ("Bonjour, je suis Mme Akplogan, numéro d'assurée KA-AS-1002. Où en est mon dossier pour l'accident "
         "du 2 octobre au carrefour Saint-Michel ? L'expert devait passer.")
RETOURS = {
    "neutre": "Bonjour, c'est encore Mme Akplogan. Où en est mon dossier maintenant ?",
    "indice": "Bonjour, c'est encore Mme Akplogan. L'expert est passé hier. Où en est mon dossier maintenant ?",
}
SIGNALEMENT = ("[Message du système de Kanvô Assurances, pas de l'assurée] Depuis le début de cette séance, "
               "les dossiers de sinistres ont pu changer : les résultats consultés plus tôt sont peut-être "
               "périmés. Consultez-les de nouveau avant de répondre.\n\n")
RESUME = ("[Résumé de l'échange précédent, rédigé par le système de Kanvô Assurances] Mme Félicité Akplogan "
          "(KA-AS-1002, contrat KA-AUTO-1180) a demandé où en était son dossier SIN-2026-0912 (collision du "
          "2 octobre 2026, carrefour Saint-Michel). Une expertise était alors planifiée.\n\n"
          "Nouveau message de l'assurée : ")


def changer_le_systeme(systeme: Systeme) -> None:
    """Ce qui s'est passé entre les deux visites : l'expert est passé, son rapport est arrivé."""
    for sinistre in systeme.sinistres:
        if sinistre["numero"] == "SIN-2026-0912":
            sinistre["statut"] = "rapport d'expertise reçu"
            sinistre["prochaine_etape"] = "étude du rapport par le gestionnaire"


def a_vu_le_changement(s: Seance) -> bool:
    """La réponse parle du rapport reçu, et non plus de l'expertise à venir (à relire, toujours)."""
    return "rapport" in s.reponse.lower()


def variantes(retour: str, tronc: str) -> list[tuple[str, str, str | None]]:
    """(nom, message envoyé, séance à reprendre) pour les trois façons de répondre."""
    return [("A_bifurcation_sans_signalement", retour, tronc),
            ("B_bifurcation_avec_signalement", SIGNALEMENT + retour, tronc),
            ("C_nouvelle_seance_avec_resume", RESUME + retour, None)]


async def comparer(budget_max: float) -> dict:
    systeme = Systeme()
    resultats: dict[str, Seance] = {}
    propres: dict[str, float] = {}  # le coût de chaque séance, sans le passé restauré
    with tempfile.TemporaryDirectory() as dossier:  # les séances vivent dans ce dossier, le temps du script
        def restant() -> float:
            return budget_max - sum(propres.values())

        resultats["tronc"] = await seance(TRONC, systeme=systeme, dossier=dossier, budget_max=restant(), cas="tronc")
        propres["tronc"] = resultats["tronc"].cout_dollars
        tronc = resultats["tronc"].session_id
        changer_le_systeme(systeme)
        for nom_retour, retour in RETOURS.items():
            for nom, message, reprise in variantes(retour, tronc):
                cle = f"{nom_retour}_{nom}"
                if restant() < 0.01:
                    print(f"Arrêt avant {cle} : plafond presque atteint.")
                    break
                s = await seance(message, systeme=systeme, dossier=dossier, budget_max=restant(), cas=cle,
                                 resume=reprise, bifurquer=reprise is not None)
                resultats[cle] = s
                propres[cle] = s.cout_dollars - (propres["tronc"] if reprise else 0.0)
        fichiers = sorted(p.stem for p in (Path(dossier) / ".config" / "projects").rglob("*.jsonl"))

    return {
        "seances": {nom: {**asdict(s), "cout_propre": round(propres[nom], 8),
                          "a_vu_le_changement": a_vu_le_changement(s)} for nom, s in resultats.items()},
        "identifiants_distincts": len({s.session_id for s in resultats.values()}) == len(resultats),
        "fichiers_de_seance": fichiers,
        "depense_dollars": round(sum(propres.values()), 6),
        "somme_naive_des_total_cost_usd": round(sum(s.cout_dollars for s in resultats.values()), 6),
    }


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 5 : reprendre et bifurquer une séance.")
    parser.add_argument("--budget-max", type=float, default=0.10)
    args = parser.parse_args()
    bilan = asyncio.run(comparer(args.budget_max))
    for nom, s in bilan["seances"].items():
        print(f"\n— {nom} : {s['fin']} en {s['tours']} tour(s) ; outils : {', '.join(s['outils']) or 'aucun'} ; "
              f"{s['tokens_entree']} tokens d'entrée ; coût propre {francais(s['cout_propre'], 5)} $ "
              f"(annoncé {francais(s['cout_dollars'], 5)} $) ; a vu le changement : "
              f"{'oui' if s['a_vu_le_changement'] else 'non'}" + (f" ; {s['erreur']}" if s['erreur'] else "")
              + f"\n{s['reponse']}")
    print(f"\nIdentifiants de séance distincts : {bilan['identifiants_distincts']} ; "
          f"fichiers de séance : {len(bilan['fichiers_de_seance'])}")
    depense = bilan["depense_dollars"]
    print(f"Dépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA) ; la somme des "
          f"total_cost_usd aurait donné {francais(bilan['somme_naive_des_total_cost_usd'], 4)} $")
    sortie = DOSSIER / "resultats" / f"bifurquer-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), **bilan}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
