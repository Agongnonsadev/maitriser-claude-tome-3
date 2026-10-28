"""Chapitre 3 : un premier banc pour choisir le modèle et la réflexion de chaque étape.

Deux étapes de la mission, quatre réglages, six cas par étape, plusieurs répétitions :
- l'extraction des constats, notée par le code contre la vérité. Les constats sont fabriqués,
  on sait donc ce qu'ils contiennent : champs justes, valeurs inventées là où le constat est muet,
  JSON lisible ou non ;
- la première réponse aux déclarations, contrôlée par des règles écrites dans le code :
  longueur, nombre de questions, aucune promesse, vouvoiement, passage à un gestionnaire,
  numéro de contrat demandé quand il manque.

Les prompts système sont ceux du chapitre 2, inchangés : seuls le modèle et la réflexion varient.
Ce banc éclaire une décision d'architecture. Il ne remplace pas l'évaluation du chapitre 19 :
six cas et des règles simples ne disent pas tout de la qualité d'une réponse.

Lancement, depuis le dossier python/ :
    python -m ch03.banc --estimer                          # gratuit : coût maximal du banc
    python -m ch03.banc --repetitions 2 --budget-max 0.40
"""

import argparse
import json
import re
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import cout, cout_maximal, francais
from assureur.journal import noter

DOSSIER = Path(__file__).parent
KANVO = DOSSIER.parent / "ch02" / "kanvo.json"


@dataclass(frozen=True)
class Reglage:
    nom: str
    modele: str
    options: dict = field(default_factory=dict)  # paramètres ajoutés à la requête


REGLAGES = [
    Reglage("haiku-defaut", "claude-haiku-5-5"),  # effort medium, réflexion adaptative
    Reglage("haiku-sans-reflexion", "claude-haiku-5-5", {"thinking": {"type": "disabled"}}),
    Reglage("sonnet-defaut", "claude-sonnet-5-5"),  # effort high, réflexion adaptative
    # Sonnet 5.5 refuse "disabled" : son réglage le plus bas supprime la réflexion avant la réponse.
    Reglage("sonnet-sans-reflexion-prealable", "claude-sonnet-5-5", {"thinking": {"type": "between_tools"}}),
]

MAX_TOKENS = {"constats": 2000, "declarations": 1024}


# --- Notation des constats -----------------------------------------------------------------

def lire_json(texte: str) -> tuple[dict | None, bool]:
    """(l'objet JSON de la réponse ou None, True si la réponse l'a entouré d'autre chose)."""
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut < 0 or fin < debut:
        return None, True
    try:
        objet = json.loads(texte[debut:fin + 1])
    except json.JSONDecodeError:
        return None, True
    return objet, bool(texte[:debut].strip() or texte[fin + 1:].strip())


MOIS = {"janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6, "juil": 7,
        "août": 8, "aout": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12}


def _date(valeur: str) -> str | None:
    if m := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", valeur):
        return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    if m := re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", valeur):
        return f"{int(m[3]):04d}-{int(m[2]):02d}-{int(m[1]):02d}"
    if m := re.search(r"(\d{1,2})\s+([a-zéû]+)\.?\s+(\d{4})", valeur.lower()):
        mois = next((n for prefixe, n in MOIS.items() if m[2].startswith(prefixe)), None)
        return f"{int(m[3]):04d}-{mois:02d}-{int(m[1]):02d}" if mois else None
    return None


def _heure(valeur: str) -> str | None:
    if m := re.search(r"(\d{1,2})\s*(?:h|:)\s*(\d{2})?", valeur.lower()):
        return f"{int(m[1]):02d}:{int(m[2] or 0):02d}"
    return None


def normaliser(champ: str, valeur):
    """Ramène une valeur à une forme comparable : dates ISO, heures HH:MM, plaques sans espaces."""
    if valeur is None or (isinstance(valeur, str) and valeur.strip().lower() in ("", "null", "none")):
        return None
    if champ == "blesses":
        if isinstance(valeur, bool):
            return valeur
        return {"true": True, "oui": True, "false": False, "non": False}.get(str(valeur).strip().lower(), valeur)
    texte = str(valeur)
    if champ == "date":
        return _date(texte) or texte
    if champ == "heure":
        return _heure(texte) or texte
    return re.sub(r"\s+", "", texte).upper()


def _valeur(objet: dict, chemin: str):
    for cle in chemin.split("."):
        if not isinstance(objet, dict):
            return None
        objet = objet.get(cle)
    return objet


def noter_constat(objet: dict | None, verite: dict) -> dict:
    """Champs justes, total noté, valeurs inventées (là où la vérité est null), champs faux."""
    notes = {"justes": 0, "total": 0, "inventions": 0, "faux": []}
    for champ, attendu in verite.items():
        if attendu == "__ignorer__":
            continue
        notes["total"] += 1
        obtenu = normaliser(champ.split(".")[-1], _valeur(objet, champ)) if objet else None
        if attendu is None:
            if obtenu is None:
                notes["justes"] += 1
            else:
                notes["inventions"] += 1
                notes["faux"].append(champ)
        elif objet is not None and obtenu == normaliser(champ.split(".")[-1], attendu):
            notes["justes"] += 1
        else:
            notes["faux"].append(champ)
    return notes


# --- Contrôle des déclarations --------------------------------------------------------------

PROMESSES = [
    r"\bvous (?:serez|allez être|seriez) (?:indemnisée?s?|remboursée?s?)\b",
    r"\bvous (?:recevrez|toucherez|percevrez)\b",
    r"\b(?:sous|dans un délai de|d'ici|en) \d+ (?:jours?|semaines?|heures?|mois)\b",
]
TUTOIEMENT = r"\b(?:tu|te|toi|ton|ta|tes)\b"
MONTANT = r"(\d[\d  .]*)\s?(?:FCFA|F CFA|francs)"


def _chiffres(texte: str) -> set[str]:
    return {re.sub(r"\D", "", m) for m in re.findall(MONTANT, texte, flags=re.IGNORECASE)}


def controler_declaration(reponse: str, cas: dict) -> dict:
    """Chaque règle du prompt système, vérifiée par le code : True si elle est respectée."""
    controles = {
        "longueur": len(reponse.split()) <= 120,
        "questions": reponse.count("?") <= 3,
        "sans_promesse": not any(re.search(m, reponse, flags=re.IGNORECASE) for m in PROMESSES)
        and not (_chiffres(reponse) - _chiffres(cas["texte"])),  # un montant que l'assuré n'a pas donné
        "vouvoiement": not re.search(TUTOIEMENT, reponse, flags=re.IGNORECASE),
    }
    if cas["escalade_attendue"]:
        controles["escalade"] = bool(re.search(r"gestionnaire", reponse, re.IGNORECASE)
                                     and re.search(r"rappel|rappeler|contact|joindre", reponse, re.IGNORECASE))
    if cas["contrat_a_demander"]:
        controles["contrat_demande"] = bool(re.search(r"contrat|police", reponse, re.IGNORECASE))
    return controles


# --- Le banc ---------------------------------------------------------------------------------

@dataclass
class Essai:
    etape: str
    reglage: str
    modele: str
    cas: str
    repetition: int
    reponse: str
    stop_reason: str
    tokens_entree: int
    tokens_sortie: int
    tokens_reflexion: int
    cout_dollars: float
    latence_s: float
    notes: dict


class BudgetDepasse(Exception):
    pass


def _texte(reponse) -> str:
    return "".join(getattr(b, "text", "") for b in reponse.content if getattr(b, "type", "") == "text")


def lancer(client, cas: dict, systemes: dict, reglages=REGLAGES, repetitions: int = 2,
           budget_max: float | None = None, journal: str | None = None) -> tuple[list[Essai], float]:
    essais, depense = [], 0.0
    for etape in ("constats", "declarations"):
        for reglage in reglages:
            for repetition in range(1, repetitions + 1):
                for c in cas[etape]:
                    messages = [{"role": "user", "content": c["texte"]}]
                    entree = client.messages.count_tokens(model=reglage.modele, system=systemes[etape],
                                                          messages=messages).input_tokens
                    pire = cout_maximal(reglage.modele, entree, MAX_TOKENS[etape])
                    if budget_max is not None and depense + pire > budget_max:
                        raise BudgetDepasse(f"Arrêt avant {reglage.nom} sur {c['id']} : "
                                            f"{francais(depense, 4)} $ dépensés, plafond {francais(budget_max, 2)} $.")
                    debut = time.perf_counter()
                    reponse = client.messages.create(model=reglage.modele, max_tokens=MAX_TOKENS[etape],
                                                     system=systemes[etape], messages=messages, **reglage.options)
                    latence = time.perf_counter() - debut
                    c_cout = cout(reglage.modele, reponse.usage)
                    depense += c_cout.dollars
                    texte = _texte(reponse)
                    if etape == "constats":
                        objet, enveloppe = lire_json(texte)
                        notes = {**noter_constat(objet, c["verite"]), "json_lisible": objet is not None,
                                 "json_enveloppe": enveloppe}
                    else:
                        notes = controler_declaration(texte, c)
                    noter(getattr(reponse, "_request_id", None), reglage.modele, c_cout, chemin=journal,
                          chapitre="03", etape=etape, reglage=reglage.nom, cas=c["id"], stop_reason=reponse.stop_reason)
                    essais.append(Essai(etape, reglage.nom, reglage.modele, c["id"], repetition, texte,
                                        reponse.stop_reason, c_cout.entree, c_cout.sortie, c_cout.reflexion,
                                        c_cout.dollars, round(latence, 2), notes))
    return essais, depense


def resumer(essais: list[Essai]) -> list[dict]:
    """Une ligne par étape et par réglage : qualité, coût moyen, latence médiane, réflexion."""
    lignes = []
    for etape in dict.fromkeys(e.etape for e in essais):
        for reglage in dict.fromkeys(e.reglage for e in essais if e.etape == etape):
            groupe = [e for e in essais if e.etape == etape and e.reglage == reglage]
            ligne = {"etape": etape, "reglage": reglage, "essais": len(groupe),
                     "cout_moyen": statistics.mean(e.cout_dollars for e in groupe),
                     "latence_mediane_s": statistics.median(e.latence_s for e in groupe),
                     "reflexion_moyenne": statistics.mean(e.tokens_reflexion for e in groupe),
                     "sortie_moyenne": statistics.mean(e.tokens_sortie for e in groupe),
                     "coupees": sum(e.stop_reason == "max_tokens" for e in groupe)}
            if etape == "constats":
                ligne["champs_justes"] = sum(e.notes["justes"] for e in groupe) / sum(e.notes["total"] for e in groupe)
                ligne["inventions"] = sum(e.notes["inventions"] for e in groupe)
                ligne["json_illisibles"] = sum(not e.notes["json_lisible"] for e in groupe)
                ligne["json_enveloppes"] = sum(e.notes["json_enveloppe"] for e in groupe)
            else:
                regles = [v for e in groupe for v in e.notes.values()]
                ligne["regles_respectees"] = sum(regles) / len(regles)
                ligne["reponses_sans_faute"] = sum(all(e.notes.values()) for e in groupe)
            lignes.append(ligne)
    return lignes


def afficher(lignes: list[dict]) -> str:
    sortie = []
    for l in lignes:
        if l["etape"] == "constats":
            qualite = (f"champs justes {francais(100 * l['champs_justes'], 0)} %, inventions {l['inventions']}, "
                       f"JSON illisibles {l['json_illisibles']}, entourés {l['json_enveloppes']}")
        else:
            qualite = (f"règles respectées {francais(100 * l['regles_respectees'], 0)} %, "
                       f"réponses sans faute {l['reponses_sans_faute']} sur {l['essais']}")
        sortie.append(f"{l['etape']:<13} {l['reglage']:<32} {qualite} ; coût moyen {francais(l['cout_moyen'], 5)} $ ; "
                      f"latence médiane {francais(l['latence_mediane_s'], 1)} s ; réflexion {francais(l['reflexion_moyenne'], 0)} "
                      f"tokens ; coupées {l['coupees']}")
    return "\n".join(sortie)


def principal() -> None:
    parser = argparse.ArgumentParser(description="Banc du chapitre 3 : modèle et réflexion par étape.")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--budget-max", type=float, default=0.40)
    parser.add_argument("--estimer", action="store_true", help="gratuit : coût maximal du banc, sans appel payant")
    parser.add_argument("--reglages", nargs="*", help="ne lancer que ces réglages (leurs noms)")
    args = parser.parse_args()

    import anthropic

    client = anthropic.Anthropic()
    cas = json.loads((DOSSIER / "cas.json").read_text(encoding="utf-8"))
    kanvo = {c["id"]: c for c in json.loads(KANVO.read_text(encoding="utf-8"))["cas"]}
    systemes = {"constats": kanvo["constats"]["systeme"], "declarations": kanvo["declaration"]["systeme"]}
    reglages = [r for r in REGLAGES if not args.reglages or r.nom in args.reglages]

    if args.estimer:
        total = 0.0
        for etape in ("constats", "declarations"):
            for r in reglages:
                for c in cas[etape]:
                    entree = client.messages.count_tokens(model=r.modele, system=systemes[etape],
                                                          messages=[{"role": "user", "content": c["texte"]}]).input_tokens
                    total += cout_maximal(r.modele, entree, MAX_TOKENS[etape]) * args.repetitions
        print(f"Coût maximal du banc : {francais(total, 4)} $ (≈ {francais(total * config.TAUX_FCFA, 0)} FCFA), "
              f"si chaque réponse atteignait max_tokens.")
        return

    essais, depense = lancer(client, cas, systemes, reglages, args.repetitions, args.budget_max)
    lignes = resumer(essais)
    print(afficher(lignes))
    print(f"\nDépense du banc : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / "resultats" / f"banc-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "repetitions": args.repetitions,
                                  "depense_dollars": round(depense, 6), "resume": lignes,
                                  "essais": [asdict(e) for e in essais]}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
