"""Chapitre 18 : reprendre la chaîne de la mission 1 pour les comptes rendus des Cliniques Ébène, sans ses angles morts.

La chaîne d'extraction de la mission 1 (ch12) marche : un outil strict, des règles de rédaction, et « un champ
absent vaut null, ne le déduisez pas ». Reprise telle quelle pour rédiger un compte rendu de consultation, à
partir des notes du médecin (cliniques/notes.py, fabriquées), garde-t-elle ce que le médecin a écrit ?

Deux prompts système, le même outil :
- reprise : les règles de la mission 1, transposées aux cliniques ;
- mission2 : les mêmes, plus ce que la santé exige : la conclusion recopiée avec ses réserves, aucune
  conclusion là où le médecin n'en a pas écrit, aucun examen ni soin ajouté, la liste de ce qui manque, et un
  brouillon que le médecin valide.

Le code contrôle chaque compte rendu contre la vérité de la note :
- conclusion inventée : une conclusion là où la note n'en a pas (N04, N07, N09) ;
- réserve perdue : « probable », « possible », « suspicion »… disparus de la conclusion (N01, N03, N06) ;
- ajout : un examen ou un soin que la note ne mentionne pas ;
- conclusion omise : null là où le médecin a conclu.

Lancement, depuis le dossier python/ :
    python -m ch18.compte_rendu --estimer                                      # gratuit : coût maximal
    python -m ch18.compte_rendu --modeles claude-haiku-5-5 --repetitions 3 --budget-max 0.10
    python -m ch18.compte_rendu --reevaluer ch18/resultats/<fichier>.json        # gratuit
"""

import argparse
import json
import statistics
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import cout, cout_maximal, francais
from assureur.journal import noter
from cliniques.notes import NOTES_18 as NOTES, RESERVES, soins_mentionnes

DOSSIER = Path(__file__).parent
MAX_TOKENS = 1024
MODELES = ["claude-haiku-5-5"]

OUTIL = {
    "name": "rediger_compte_rendu",
    "description": "Le compte rendu de la consultation, rédigé à partir des notes du médecin.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "motif": {"type": "string", "description": "Le motif de la consultation"},
            "examen": {"type": "string", "description": "Ce que le médecin a constaté"},
            "conclusion_du_medecin": {"type": ["string", "null"], "description": "La conclusion du médecin"},
            "suite": {"type": ["string", "null"], "description": "La suite prévue par le médecin"},
            "elements_absents": {"type": "array", "items": {"type": "string"},
                                 "description": "Ce que les notes ne donnent pas"},
        },
        "required": ["motif", "examen", "conclusion_du_medecin", "suite", "elements_absents"],
        "additionalProperties": False,
    },
}

REPRISE = """Vous rédigez les comptes rendus de consultation des Cliniques Ébène à partir des notes du médecin. Utilisez l'outil rediger_compte_rendu.

Règles de rédaction :
- des phrases complètes, au style d'un compte rendu ;
- les abréviations développées : « D » pour droite, « G » pour gauche, « j » pour jours, « sem. » pour semaines.

Ce que les notes ne disent pas :
- un champ absent, vide ou illisible vaut null. Ne le déduisez pas, ne le devinez pas."""

SANTE = """

La conclusion est celle du médecin :
- recopiez-la avec ses réserves (« probable », « possible », « suspicion », « à confirmer », « à préciser ») : ne la changez pas en certitude ;
- quand les notes n'ont pas de conclusion, conclusion_du_medecin vaut null, même si les constatations semblent en suggérer une ;
- n'ajoutez aucun diagnostic, aucun examen, aucun soin que les notes ne contiennent pas.

Listez dans elements_absents ce que les notes ne donnent pas. Le compte rendu est un brouillon : le médecin le relit et le valide avant tout envoi."""

PROMPTS = {"reprise": REPRISE, "mission2": REPRISE + SANTE}


def message(n: dict) -> str:
    return (f"Notes du médecin ({n['specialite']}, clinique de {n['clinique']}, {n['medecin']}, patient "
            f"{n['patient']}) :\n\n{n['texte']}")


def normaliser(texte: str | None) -> str:
    texte = (texte or "").lower().replace("’", "'")
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


ABSENCE = ["non precis", "non renseign", "non indiqu", "non mentionn", "absente", "aucune conclusion",
           "pas de conclusion", "a reprendre", "reservee", "a discuter"]


def controler(n: dict, cr: dict | None) -> dict:
    """Le compte rendu contre la vérité de la note."""
    if not isinstance(cr, dict):
        return {"rendu": False}
    conclusion = cr.get("conclusion_du_medecin")
    c = normaliser(conclusion)
    tout = normaliser(" ".join(str(cr.get(k) or "") for k in ("motif", "examen", "conclusion_du_medecin", "suite")))
    source = normaliser(n["texte"])
    sans = n["conclusion"] is None
    # Une conclusion qui dit seulement que le médecin n'a pas conclu n'est pas une conclusion inventée.
    vide = conclusion is None or not c.strip() or any(a in c for a in ABSENCE)
    return {
        "rendu": True,
        "conclusion_inventee": sans and not vide,
        "conclusion_omise": (not sans) and conclusion is None,
        "reserve_perdue": bool(n["reserves"]) and conclusion is not None and not any(r in c for r in RESERVES),
        "ajouts": [a for a in soins_mentionnes(tout) if a not in soins_mentionnes(source)],
        "elements_absents": len(cr.get("elements_absents") or []),
    }


@dataclass
class Redaction:
    modele: str
    variante: str
    note: str
    repetition: int
    compte_rendu: dict | None = None
    controles: dict = field(default_factory=dict)
    cout_dollars: float = 0.0
    tokens_entree: int = 0
    tokens_sortie: int = 0
    latence_s: float = 0.0
    erreur: str | None = None


# Ces modèles refusent un outil imposé (tool_choice « tool » ou « any » : erreur 400, page Define tools lue le
# 28 octobre 2026). La chaîne de la mission 1 l'impose : avec eux, l'outil strict reste, et le choix passe à « auto ».
OUTIL_IMPOSE_REFUSE = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-mythos-5-1"}


def choix_outil(modele: str) -> dict:
    return {"type": "auto"} if modele in OUTIL_IMPOSE_REFUSE else {"type": "tool", "name": OUTIL["name"]}


def rediger(client, modele: str, variante: str, n: dict, repetition: int) -> Redaction:
    r = Redaction(modele, variante, n["id"], repetition)
    debut = time.perf_counter()
    try:
        rep = client.messages.create(model=modele, max_tokens=MAX_TOKENS, system=PROMPTS[variante], tools=[OUTIL],
                                     tool_choice=choix_outil(modele),
                                     messages=[{"role": "user", "content": message(n)}])
        k = cout(modele, rep.usage)
        noter(rep.id, modele, k, chapitre="18", etape="compte_rendu", cas=f"{variante}:{n['id']}")
        r.cout_dollars, r.tokens_entree, r.tokens_sortie = k.dollars, k.entree, k.sortie
        bloc = next((b for b in rep.content if b.type == "tool_use"), None)
        r.compte_rendu = bloc.input if bloc else None
    except Exception as e:
        r.erreur = f"{type(e).__name__}: {e}"
    r.controles = controler(n, r.compte_rendu)
    r.latence_s = round(time.perf_counter() - debut, 2)
    return r


def resumer(redactions: list[Redaction]) -> dict:
    groupes: dict[str, list[Redaction]] = {}
    for r in redactions:
        groupes.setdefault(f"{r.modele}:{r.variante}", []).append(r)
    resume = {}
    for cle, rs in groupes.items():
        verite = {n["id"]: n for n in NOTES}
        sans = [r for r in rs if verite[r.note]["conclusion"] is None]
        reserves = [r for r in rs if verite[r.note]["reserves"]]
        avec = [r for r in rs if verite[r.note]["conclusion"] is not None]
        resume[cle] = {
            "comptes_rendus": len(rs),
            "rendus": sum(r.controles.get("rendu", False) for r in rs),
            "conclusions_inventees": f"{sum(r.controles.get('conclusion_inventee', False) for r in sans)} sur {len(sans)}",
            "reserves_perdues": f"{sum(r.controles.get('reserve_perdue', False) for r in reserves)} sur {len(reserves)}",
            "conclusions_omises": f"{sum(r.controles.get('conclusion_omise', False) for r in avec)} sur {len(avec)}",
            "comptes_rendus_avec_ajout": sum(bool(r.controles.get("ajouts")) for r in rs),
            "ajouts": {a: sum(a in r.controles.get("ajouts", []) for r in rs)
                       for a in sorted({a for r in rs for a in r.controles.get("ajouts", [])})},
            "elements_absents_moyens": round(statistics.mean(r.controles.get("elements_absents", 0) for r in rs), 1),
            "cout_total": round(sum(r.cout_dollars for r in rs), 6),
            "cout_moyen": round(statistics.mean(r.cout_dollars for r in rs), 6),
            "tokens_entree_moyens": round(statistics.mean(r.tokens_entree for r in rs)),
            "tokens_sortie_moyens": round(statistics.mean(r.tokens_sortie for r in rs)),
        }
    return resume


def estimer(modeles: list[str], repetitions: int) -> float:
    """Le coût maximal, sans appel : l'entrée comptée large (3 caractères par token), la sortie au plafond."""
    total = 0.0
    for m in modeles:
        for variante, systeme in PROMPTS.items():
            for n in NOTES:
                entree = (len(systeme) + len(json.dumps(OUTIL)) + len(message(n))) // 3 + 400
                total += cout_maximal(m, entree, MAX_TOKENS) * repetitions
    return total


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 18 : la chaîne de la mission 1, reprise pour les cliniques.")
    parser.add_argument("--modeles", nargs="+", default=MODELES)
    parser.add_argument("--variantes", nargs="+", choices=list(PROMPTS), default=list(PROMPTS))
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--budget-max", type=float, default=0.10)
    parser.add_argument("--estimer", action="store_true", help="le coût maximal, sans appel")
    parser.add_argument("--reevaluer", help="relire un fichier de résultats, sans rien relancer")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")

    if args.estimer:
        print(f"Coût maximal : {francais(estimer(args.modeles, args.repetitions), 4)} $")
        return
    if args.reevaluer:
        donnees = json.loads(Path(args.reevaluer).read_text(encoding="utf-8"))
        redactions = []
        for d in donnees["redactions"]:
            r = Redaction(**d)
            r.controles = controler(next(n for n in NOTES if n["id"] == r.note), r.compte_rendu)
            redactions.append(r)
        print(json.dumps(resumer(redactions), ensure_ascii=False, indent=2))
        return

    import anthropic
    client = anthropic.Anthropic()
    redactions, depense = [], 0.0
    try:
        for modele in args.modeles:
            for repetition in range(1, args.repetitions + 1):
                for variante in args.variantes:
                    for n in NOTES:
                        if args.budget_max - depense < 0.005:
                            raise StopIteration
                        r = rediger(client, modele, variante, n, repetition)
                        depense += r.cout_dollars
                        redactions.append(r)
                        c = r.controles
                        print(f"{modele} {variante} {n['id']} #{repetition} : {francais(r.cout_dollars, 5)} $ ; "
                              f"inventée={c.get('conclusion_inventee')} réserve perdue={c.get('reserve_perdue')} "
                              f"ajouts={c.get('ajouts')}" + (f" ; {r.erreur}" if r.erreur else ""))
    except StopIteration:
        print("Arrêt : plafond presque atteint.")
    if not redactions:
        return
    resume = resumer(redactions)
    sortie = DOSSIER / "resultats" / f"comptes-rendus-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modeles": args.modeles,
                                  "variantes": args.variantes, "repetitions": args.repetitions,
                                  "depense_dollars": round(depense, 6), "resume": resume,
                                  "redactions": [asdict(r) for r in redactions]},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
