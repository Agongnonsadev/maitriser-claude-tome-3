"""Chapitre 5 : la boucle agentique de l'agent des sinistres, écrite à la main avec l'API.

C'est stop_reason qui conduit la boucle, et rien d'autre :
- "tool_use" : Claude demande un ou plusieurs outils. Le code les exécute tous, renvoie tous les
  résultats dans un seul message, et relance ;
- "end_turn" : Claude a fini. La boucle s'arrête, et sa dernière réponse part vers l'assuré ;
- toute autre valeur (max_tokens, refusal…) : une erreur, traitée comme telle.
Le texte de Claude ne décide jamais de l'arrêt : une réponse peut contenir du texte ET demander
un outil. Le plafond de tours est un garde-fou : s'il est atteint, c'est une erreur à examiner,
pas une fin normale.

Lancement, depuis le dossier python/ :
    python -m ch05.boucle --estimer                            # gratuit : coût maximal
    python -m ch05.boucle --repetitions 2 --budget-max 0.20
    python -m ch05.boucle --cas d5 h3 --repetitions 1          # quelques déclarations seulement
    python -m ch05.boucle --reglage sans-reflexion --repetitions 1 --budget-max 0.05
"""

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import cout, cout_maximal, francais
from assureur.journal import noter
from assureur.outils import OUTILS, executer
from assureur.systeme import Systeme

DOSSIER = Path(__file__).parent
PROMPT = (DOSSIER.parent / "assureur" / "prompts" / "sinistres_v1.md").read_text(encoding="utf-8")
MODELE = "claude-haiku-5-5"  # fiche de décision n° 3 du chapitre 3 : réglage par défaut
MAX_TOKENS = 2048            # la réflexion compte dans max_tokens : de la marge
GARDE_FOU = 10               # tours au plus ; jamais atteint quand tout va bien
REGLAGES = {"defaut": {}, "sans-reflexion": {"thinking": {"type": "disabled"}}}  # comme au chapitre 3


@dataclass
class Tour:
    numero: int
    stop_reason: str
    outils: list[str]
    avec_texte: bool        # la réponse contenait aussi du texte
    erreurs_outils: int
    tokens_entree: int
    tokens_sortie: int
    tokens_reflexion: int
    cout_dollars: float
    latence_s: float        # l'appel à l'API seul, sans le comptage des tokens
    texte: str = ""         # le texte de la réponse, quand il y en a
    entrees: list = field(default_factory=list)  # les arguments de chaque appel d'outil


@dataclass
class Conduite:
    cas: str
    repetition: int
    fin: str                # "end_turn", ou "erreur:<raison>"
    reponse: str            # le texte final, celui que l'assuré lit
    tours: list[Tour] = field(default_factory=list)
    transmissions: int = 0

    @property
    def cout_dollars(self) -> float:
        return sum(t.cout_dollars for t in self.tours)

    @property
    def latence_s(self) -> float:
        return round(sum(t.latence_s for t in self.tours), 2)

    @property
    def outils(self) -> list[str]:
        return [nom for t in self.tours for nom in t.outils]


class BudgetDepasse(Exception):
    pass


def _texte(contenu) -> str:
    return "".join(b.text for b in contenu if b.type == "text").strip()


def conduire(client, declaration: str, *, systeme: Systeme | None = None, prompt: str = PROMPT,
             modele: str = MODELE, max_tokens: int = MAX_TOKENS, garde_fou: int = GARDE_FOU,
             options: dict | None = None, budget_restant: float | None = None, journal: str | None = None,
             cas: str = "", repetition: int = 1, outils: list | None = None, executer_outil=executer,
             chapitre: str = "05") -> Conduite:
    """Fait tourner l'agent sur une déclaration, jusqu'à end_turn ou une erreur traitée."""
    systeme = systeme or Systeme()
    outils = OUTILS if outils is None else outils
    avant = len(systeme.transmissions)
    messages = [{"role": "user", "content": declaration}]
    conduite = Conduite(cas, repetition, "erreur:garde_fou", "")

    for numero in range(1, garde_fou + 1):
        if budget_restant is not None:  # le plafond se vérifie avant l'appel, le comptage est gratuit
            entree = client.messages.count_tokens(model=modele, system=prompt, tools=outils,
                                                  messages=messages).input_tokens
            if conduite.cout_dollars + cout_maximal(modele, entree, max_tokens) > budget_restant:
                raise BudgetDepasse(f"Arrêt avant le tour {numero} de {cas or 'la déclaration'} : plafond atteint.")

        debut = time.perf_counter()
        reponse = client.messages.create(model=modele, max_tokens=max_tokens, system=prompt, tools=outils,
                                         messages=messages, **(options or {}))
        latence = round(time.perf_counter() - debut, 2)
        c = cout(modele, reponse.usage)
        noter(getattr(reponse, "_request_id", None), modele, c, chemin=journal, chapitre=chapitre, etape="boucle",
              cas=cas or None, tour=numero, stop_reason=reponse.stop_reason)
        appels = [b for b in reponse.content if b.type == "tool_use"]
        tour = Tour(numero, reponse.stop_reason, [a.name for a in appels], bool(_texte(reponse.content)), 0,
                    c.entree + c.lecture_cache + c.ecriture_cache, c.sortie, c.reflexion, c.dollars, latence,
                    _texte(reponse.content), [a.input for a in appels])
        conduite.tours.append(tour)

        if reponse.stop_reason == "tool_use":
            # Tout le contenu repart dans l'historique, réflexion comprise, puis tous les résultats
            # dans UN message, dans l'ordre des demandes.
            messages.append({"role": "assistant", "content": reponse.content})
            resultats = []
            for appel in appels:
                texte, erreur = executer_outil(systeme, appel.name, appel.input)
                tour.erreurs_outils += erreur
                resultats.append({"type": "tool_result", "tool_use_id": appel.id, "content": texte,
                                  "is_error": erreur})
            messages.append({"role": "user", "content": resultats})
            continue

        if reponse.stop_reason == "end_turn":
            conduite.fin, conduite.reponse = "end_turn", _texte(reponse.content)
        else:  # max_tokens, refusal… : la réponse est inutilisable, on le dit
            conduite.fin = f"erreur:{reponse.stop_reason}"
        break

    conduite.transmissions = len(systeme.transmissions) - avant
    return conduite


def lancer(client, declarations: list[dict], repetitions: int = 2, budget_max: float | None = None,
           journal: str | None = None, options: dict | None = None) -> tuple[list[Conduite], float]:
    conduites, depense = [], 0.0
    for repetition in range(1, repetitions + 1):
        for d in declarations:
            restant = None if budget_max is None else budget_max - depense
            c = conduire(client, d["texte"], systeme=Systeme(), options=options, budget_restant=restant,
                         journal=journal, cas=d["id"], repetition=repetition)
            depense += c.cout_dollars
            conduites.append(c)
    return conduites, depense


def resumer(conduites: list[Conduite], declarations: list[dict]) -> dict:
    """Ce que le défi demande de vérifier, plus ce que la boucle a fait."""
    attendus = {d["id"]: d for d in declarations}
    tours_outils = [t for c in conduites for t in c.tours if t.stop_reason == "tool_use"]
    return {
        "conduites": len(conduites),
        "fins": {fin: sum(c.fin == fin for c in conduites) for fin in dict.fromkeys(c.fin for c in conduites)},
        "garde_fou_atteint": sum(c.fin == "erreur:garde_fou" for c in conduites),
        "tours_max": max(len(c.tours) for c in conduites),
        "tours_moyens": statistics.mean(len(c.tours) for c in conduites),
        "tours_outils": len(tours_outils),
        "tours_outils_avec_texte": sum(t.avec_texte for t in tours_outils),
        # Une boucle qui s'arrêterait au premier texte : combien de conduites auraient fini trop tôt ?
        "arrets_premature_si_texte": sum(any(t.avec_texte and t.stop_reason == "tool_use" for t in c.tours)
                                         for c in conduites),
        "outils_attendus_appeles": sum(set(attendus[c.cas]["outils_attendus"]) <= set(c.outils) for c in conduites),
        "transmissions_conformes": sum((c.transmissions > 0) == attendus[c.cas]["transmission_attendue"]
                                       for c in conduites),
        "hors_sujet_sans_outil": sum(not c.outils for c in conduites if not attendus[c.cas]["sujet"]),
        "hors_sujet": sum(not attendus[c.cas]["sujet"] for c in conduites),
        "cout_moyen": statistics.mean(c.cout_dollars for c in conduites),
        "cout_max": max(c.cout_dollars for c in conduites),
        "latence_mediane_s": statistics.median(c.latence_s for c in conduites),
    }


def afficher(conduites: list[Conduite]) -> str:
    lignes = []
    for c in conduites:
        outils = ", ".join(c.outils) or "aucun"
        lignes.append(f"{c.cas} #{c.repetition} : {c.fin} en {len(c.tours)} tour(s) ; outils : {outils} ; "
                      f"transmissions {c.transmissions} ; {francais(c.cout_dollars, 5)} $ ; {francais(c.latence_s, 1)} s")
    return "\n".join(lignes)


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 5 : la boucle écrite à la main.")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--budget-max", type=float, default=0.20)
    parser.add_argument("--cas", nargs="*", help="ne lancer que ces déclarations (leurs identifiants)")
    parser.add_argument("--reglage", choices=list(REGLAGES), default="defaut")
    parser.add_argument("--estimer", action="store_true", help="gratuit : coût maximal du premier tour")
    args = parser.parse_args()

    import anthropic

    client = anthropic.Anthropic()
    declarations = json.loads((DOSSIER / "declarations.json").read_text(encoding="utf-8"))["declarations"]
    declarations = [d for d in declarations if not args.cas or d["id"] in args.cas]

    if args.estimer:
        total = sum(cout_maximal(MODELE, client.messages.count_tokens(
            model=MODELE, system=PROMPT, tools=OUTILS, messages=[{"role": "user", "content": d["texte"]}]
        ).input_tokens, MAX_TOKENS) for d in declarations) * args.repetitions
        print(f"Coût maximal du premier tour de chaque conduite : {francais(total, 4)} $. Les tours suivants "
              f"relisent l'historique : prévoyez trois à quatre fois plus, et gardez --budget-max.")
        return

    conduites, depense = lancer(client, declarations, args.repetitions, args.budget_max,
                                options=REGLAGES[args.reglage])
    resume = resumer(conduites, declarations)
    print(afficher(conduites))
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / "resultats" / f"boucle-{args.reglage}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "reglage": args.reglage,
                                  "repetitions": args.repetitions,
                                  "depense_dollars": round(depense, 6), "resume": resume,
                                  "conduites": [{**asdict(c), "cout_dollars": c.cout_dollars,
                                                 "latence_s": c.latence_s} for c in conduites]},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
