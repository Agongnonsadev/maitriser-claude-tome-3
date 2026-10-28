"""Chapitre 10 : le système d'études face aux pannes et aux chiffres qui se contredisent.

Cinq scénarios, sur les documents du chapitre 9 et un septième (ch10/documents/SOUS-07), qui donne un
autre rapport sinistres/primes que le réassureur (109 % contre 116 %) et le cumul de la zone C à une
autre date (24,8 Md au 30 septembre, contre 23,1 Md au 30 juin) :
- normal : aucune panne ; les deux désaccords doivent rester visibles, chacun avec sa source et sa date ;
- panne-passagere : la première lecture de la note du réassureur (SOUS-03) échoue ; l'analyste doit
  réessayer sur place, et le coordinateur n'a rien à savoir ;
- panne-persistante : SOUS-03 ne se lit jamais ; l'étude doit continuer, le rapport dire ce qui manque,
  et rien de la note ne doit apparaître (le plafond de 30 milliards, la part conservée portée à 35 %) ;
- web-indisponible : toute recherche web échoue ; le rapport doit le dire, et ne citer aucune adresse ;
- ouidah : une question sur une commune hors du portefeuille ; « aucune donnée » est un résultat vide
  valide, pas une panne.

Deux variantes :
- v1 : le système du chapitre 9, tel quel ;
- v2 : les sous-agents de ch10/sous_agents_v2.py, le prompt de ch10/prompts/coordinateur_v2.md, et un
  hook qui joint au synthétiseur et au rédacteur les résultats complets des sous-agents précédents.

Lancement, depuis le dossier python/ :
    python -m ch10.etudes_v2 --scenarios normal panne-persistante --variantes v2 --repetitions 2
"""

import argparse
import asyncio
import json
import re
import statistics
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from assureur import config, documents
from assureur.couts import francais
from ch05.boucle import MODELE
from ch09 import etudes as etudes_v1
from ch09.sous_agents import definitions as definitions_v1
from ch09.suivi import AGENT, Suivi, _refus
from ch10.sous_agents_v2 import definitions as definitions_v2

DOSSIER = Path(__file__).parent
PROMPT_V2 = (DOSSIER / "prompts" / "coordinateur_v2.md").read_text(encoding="utf-8")
QUESTION_LARGE = etudes_v1.QUESTIONS["q1-inondation"]["texte"]

# Des motifs à relire : ils repèrent dans le rapport et la réponse ce que chaque scénario attend.
NOTE_ILLISIBLE = (r"(SOUS-03|note du r[ée]assureur)[^\n]{0,200}(indisponible|pas pu|n'a pas été lu|non lu|inaccessible|"
                  r"échec|erreur|panne|pas été consult)|(indisponible|pas pu|inaccessible|échec|erreur|panne)[^\n]{0,200}"
                  r"(SOUS-03|note du r[ée]assureur)")
WEB_ILLISIBLE = (r"(web|sources? publiques?|recherche)[^\n]{0,200}(indisponible|pas pu|échec|échou|erreur|n'a pas abouti|"
                 r"délai|panne)|(indisponible|échec|échou|erreur|panne|délai)[^\n]{0,200}(web|sources? publiques?)")
SCENARIOS = {
    "normal": {"question": QUESTION_LARGE, "pannes": {}, "web_indisponible": False, "attendus": {
        "sp_109_et_116": [r"109\s?%", r"116\s?%"],
        "cumul_aux_deux_dates": [r"23,1", r"24,8", r"30 juin|2026-06-30|30/06", r"30 septembre|2026-09-30|30/09"],
        "couverture": [r"[Cc]ouverture"]}},
    "panne-passagere": {"question": QUESTION_LARGE, "pannes": {"SOUS-03": 1}, "web_indisponible": False, "attendus": {
        "note_lue": [r"30 milliards|30 Md|30 000 000 000"]}},
    "panne-persistante": {"question": QUESTION_LARGE, "pannes": {"SOUS-03": -1}, "web_indisponible": False,
                          "attendus": {"lacune_signalee": [NOTE_ILLISIBLE]},
                          "interdits": {"contenu_de_la_note": r"30 milliards|30 Md|30 000 000 000|20 % à 35 %"}},
    "web-indisponible": {"question": QUESTION_LARGE, "pannes": {}, "web_indisponible": True,
                         "attendus": {"lacune_signalee": [WEB_ILLISIBLE]},
                         "interdits": {"adresse_web": r"https?://"}},
    "ouidah": {"question": "Quelle a été la sinistralité inondation de nos contrats habitation à Ouidah en 2025 ?",
               "pannes": {}, "web_indisponible": False,
               "attendus": {"vide_valide": [r"Ouidah", r"aucun|aucune|pas de donn|ne couvre|ne couvrent|hors du p"]},
               "interdits": {"panne_annoncee": r"indisponible|panne|délai dépassé"}},
}


class SuiviV2(Suivi):
    """Le suivi du chapitre 9, avec deux ajouts : une panne simulée de la recherche web, et les résultats
    complets joints par le code aux demandes du synthétiseur et du rédacteur (updatedInput)."""

    def __init__(self, definitions: dict, web_indisponible: bool = False, joindre: bool = True, **bornes):
        super().__init__(definitions, **bornes)
        self.web_indisponible, self.joindre = web_indisponible, joindre
        self.annexes: list[dict] = []

    def rendus(self, types: set[str]) -> list[tuple[str, str]]:
        return [(sa["type"], sa["dernier_message"]) for sa in self.sous_agents()
                if sa["type"] in types and sa["fin"] is not None and sa["dernier_message"].strip()]

    async def avant_outil(self, entree, tool_use_id, contexte) -> dict:
        reponse = await super().avant_outil(entree, tool_use_id, contexte)
        if reponse:
            return reponse
        if entree.get("agent_id") and entree["tool_name"] == "WebSearch" and self.web_indisponible:
            self.evenements[-1].update(refuse=True, panne=True)
            return _refus("Erreur passagère : le service de recherche web n'a pas répondu (délai dépassé). "
                          "Réessayable.")
        if not self.joindre or entree.get("agent_id") or entree["tool_name"] not in AGENT:
            return {}
        cible = entree["tool_input"].get("subagent_type")
        recherches = self.rendus({"chercheur-web", "analyste-documents"})
        if cible == "synthetiseur":
            sources = recherches
        elif cible == "redacteur":     # la dernière synthèse, sinon les recherches
            sources = self.rendus({"synthetiseur"})[-1:] or recherches
        else:
            sources = []
        if not sources:
            return {}
        annexe = "\n\n---\nRésultats complets joints par le système, tels que les sous-agents les ont rendus :\n\n"
        annexe += "\n\n".join(f"### {t}\n{m}" for t, m in sources)
        demande = dict(entree["tool_input"])
        demande["prompt"] = demande.get("prompt", "") + annexe
        self.delegations[-1]["prompt"] = demande["prompt"]   # ce que le sous-agent reçoit vraiment
        self.annexes.append({"pour": cible, "resultats": [t for t, _ in sources], "caracteres": len(annexe)})
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                       "updatedInput": demande}}


def evaluer(scenario: dict, e: etudes_v1.Etude, bibliotheque: documents.Bibliotheque, suivi: SuiviV2) -> dict:
    texte = e.rapport + "\n" + e.reponse
    attendus = {nom: all(re.search(m, texte, re.IGNORECASE) for m in motifs)
                for nom, motifs in scenario["attendus"].items()}
    interdits = {nom: bool(re.search(m, texte, re.IGNORECASE)) for nom, m in scenario.get("interdits", {}).items()}
    lectures_note = sum(1 for ev in suivi.evenements if ev["evenement"] == "outil"
                        and ev["outil"].endswith("lire_document") and "SOUS-03" in ev["entree"].upper())
    erreurs_rendues = sum(bool(re.search(r'"erreurs"\s*:\s*\[\s*\{', sa["dernier_message"]))
                          for sa in suivi.sous_agents())
    return {"attendus": attendus, "interdits": interdits, "rapport": bool(e.rapport),
            "echecs_simules": list(bibliotheque.echecs), "lectures_de_sous_03": lectures_note,
            "pannes_web": sum(1 for ev in suivi.evenements if ev.get("panne")),
            "sous_agents_avec_erreurs_rendues": erreurs_rendues, "annexes": suivi.annexes,
            "relances": [d["type"] for d in e.delegations].count("analyste-documents") - 1}


async def lancer(scenarios: list[str], variantes: list[str], repetitions: int, budget_max: float,
                 budget_etude: float) -> tuple[list[dict], float]:
    essais, depense = [], 0.0
    for variante in variantes:
        for repetition in range(1, repetitions + 1):
            for nom in scenarios:
                restant = budget_max - depense
                if restant < 0.02:
                    print(f"Arrêt avant {variante}:{nom} #{repetition} : plafond presque atteint.")
                    return essais, depense
                sc = SCENARIOS[nom]
                agents = definitions_v2() if variante == "v2" else definitions_v1()
                bibliotheque = documents.Bibliotheque(supplements=(DOSSIER / "documents",), pannes=dict(sc["pannes"]))
                suivi = SuiviV2(agents, web_indisponible=sc["web_indisponible"], joindre=(variante == "v2"))
                question = {"id": nom, "texte": sc["question"], "aspects": {}}
                e = await etudes_v1.etudier(question, variante=variante, repetition=repetition,
                                            budget_max=min(budget_etude, restant),
                                            prompt=PROMPT_V2 if variante == "v2" else etudes_v1.PROMPTS["objectifs"],
                                            agents=agents, bibliotheque=bibliotheque, suivi=suivi, chapitre="10")
                depense += e.cout_dollars
                ev = evaluer(sc, e, bibliotheque, suivi)
                essais.append({"variante": variante, "scenario": nom, "repetition": repetition, **ev,
                               "etude": asdict(e)})
                ok = sum(ev["attendus"].values()), len(ev["attendus"])
                print(f"{variante}:{nom} #{repetition} : {e.fin} ; sous-agents : "
                      f"{', '.join(d['type'] or '?' for d in e.delegations)} ; attendus {ok[0]}/{ok[1]} ; "
                      f"interdits présents : {[k for k, v in ev['interdits'].items() if v] or 'aucun'} ; "
                      f"{francais(e.cout_dollars, 4)} $ ; {francais(e.latence_s, 0)} s"
                      + (f" ; {e.erreur}" if e.erreur else ""))
    return essais, depense


def resumer(essais: list[dict]) -> dict:
    lignes = {}
    for cle in dict.fromkeys((x["variante"], x["scenario"]) for x in essais):
        g = [x for x in essais if (x["variante"], x["scenario"]) == cle]
        lignes[f"{cle[0]}:{cle[1]}"] = {
            "etudes": len(g),
            "fins": [x["etude"]["fin"] for x in g],
            "attendus": [x["attendus"] for x in g],
            "interdits_presents": [[k for k, v in x["interdits"].items() if v] for x in g],
            "rapport": [x["rapport"] for x in g],
            "lectures_de_sous_03": [x["lectures_de_sous_03"] for x in g],
            "sous_agents_avec_erreurs_rendues": [x["sous_agents_avec_erreurs_rendues"] for x in g],
            "cout_moyen": statistics.mean(x["etude"]["cout_dollars"] for x in g),
            "latence_mediane_s": statistics.median(x["etude"]["latence_s"] for x in g),
        }
    return lignes


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 10 : le système d'études face aux pannes.")
    parser.add_argument("--scenarios", nargs="*", default=list(SCENARIOS), choices=list(SCENARIOS))
    parser.add_argument("--variantes", nargs="*", default=["v2"], choices=["v1", "v2"])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--budget-max", type=float, default=0.50)
    parser.add_argument("--budget-etude", type=float, default=0.30)
    parser.add_argument("--fichier", default=None)
    parser.add_argument("--reevaluer", type=Path, default=None,
                        help="réévaluer un fichier de résultats avec les motifs actuels, sans appel")
    args = parser.parse_args()
    if args.reevaluer:
        d = json.loads(args.reevaluer.read_text(encoding="utf-8"))
        for x in d["essais"]:
            texte = x["etude"]["rapport"] + "\n" + x["etude"]["reponse"]
            sc = SCENARIOS[x["scenario"]]
            x["attendus"] = {nom: all(re.search(m, texte, re.IGNORECASE) for m in motifs)
                             for nom, motifs in sc["attendus"].items()}
            x["interdits"] = {nom: bool(re.search(m, texte, re.IGNORECASE)) for nom, m in sc.get("interdits", {}).items()}
            print(f"{x['variante']}:{x['scenario']} #{x['repetition']} : {x['attendus']} {x['interdits']}")
        d["resume"] = resumer(d["essais"])
        args.reevaluer.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    essais, depense = asyncio.run(lancer(args.scenarios, args.variantes, args.repetitions, args.budget_max,
                                         args.budget_etude))
    resume = resumer(essais) if essais else {}
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense estimée par le SDK : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    nom = args.fichier or f"etudes-v2-{'-'.join(args.variantes)}"
    sortie = DOSSIER / "resultats" / f"{nom}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "depense_dollars": round(depense, 6),
                                  "resume": resume, "essais": essais}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
