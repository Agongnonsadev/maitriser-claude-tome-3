"""Chapitre 10 : l'agent des sinistres sur une conversation de 40 tours.

Une conversation fictive, écrite d'avance (ch10/conversation.json) : M. Kiki donne au fil des tours des
faits que seul lui connaît (le devis du garage, la voiture de location, sa date limite, un pare-brise,
ses dates de déplacement), pose des questions qui font appeler des outils, puis demande au 40e tour un
point complet. On compte les faits que ce point retrouve. Quatre façons de tenir le contexte :
- historique : toute la conversation repart à chaque appel ;
- resume : tous les 10 tours, la conversation est remplacée par un résumé, comme le font beaucoup
  d'applications pour économiser des tokens ;
- resume-faits : le même résumé, plus un bloc « faits du dossier » tenu à jour à part, et placé dans le
  prompt système, hors de l'historique résumé ;
- nouvelle-seance : après resume-faits, une séance neuve qui ne reçoit que le bloc de faits, et la
  question du point : la mémoire d'une séance à l'autre.

L'agent est celui du chapitre 8 (outils v3, prompt sinistres_v2.md), en boucle écrite à la main avec
l'API : il faut maîtriser l'historique pour le résumer. Le cache automatique (cache_control au niveau de
la requête) garde le préfixe commun d'un appel à l'autre.

Lancement, depuis le dossier python/ :  python -m ch10.conversation --repetitions 2 --budget-max 0.60
"""

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

import anthropic

from assureur import config, outils_v3
from assureur.couts import cout, francais
from assureur.journal import noter
from assureur.systeme import Systeme
from ch05.boucle import MODELE

DOSSIER = Path(__file__).parent
SCRIPT = json.loads((DOSSIER / "conversation.json").read_text(encoding="utf-8"))
PROMPT = (DOSSIER.parent / "assureur" / "prompts" / "sinistres_v2.md").read_text(encoding="utf-8")
MAX_TOKENS = 4096
GARDE_FOU = 10        # appels au plus pour un tour de l'assuré
TOUS_LES = 10         # le résumé tombe après les tours 10, 20 et 30
SANS_REFLEXION = {"thinking": {"type": "disabled"}}

RESUMER = ("Résumez cette conversation entre un assuré et l'agent des sinistres de Kanvô Assurances, en un "
           "court paragraphe, pour que l'agent puisse la poursuivre.")
FAITS = ("Voici le bloc des faits du dossier, puis la suite de la conversation. Mettez le bloc à jour. Une ligne "
         "courte par fait : chaque montant, date, numéro et statut, et chaque attente ou contrainte exprimée par "
         "l'assuré, avec sa valeur exacte et qui l'a donnée. Ne supprimez un fait que s'il a été corrigé, et "
         "dites alors par quoi. Rendez uniquement le bloc, en liste Markdown.")


@dataclass
class Conversation:
    variante: str
    repetition: int
    point: str = ""                              # la réponse du 40e tour
    faits_retrouves: dict = field(default_factory=dict)
    resumes: list = field(default_factory=list)
    bloc_faits: str = ""
    coupes: list = field(default_factory=list)   # les appels arrêtés par max_tokens : leur texte est tronqué
    appels: int = 0
    tokens_dernier_appel: int = 0               # entrée, cache compris
    tokens_max: int = 0
    part_sorties_outils: float | None = None    # dans l'historique final (variante historique)
    cout_dollars: float = 0.0
    latence_s: float = 0.0
    erreur: str | None = None


def _texte(contenu) -> str:
    return "".join(b.text for b in contenu if b.type == "text").strip()


class Agent:
    def __init__(self, client, systeme: Systeme, conv: Conversation, budget_max: float):
        self.client, self.systeme, self.conv, self.budget_max = client, systeme, conv, budget_max

    def appeler(self, etape: str, **requete):
        if self.conv.cout_dollars > self.budget_max:
            raise RuntimeError("plafond de dépense atteint")
        reponse = self.client.messages.create(model=MODELE, cache_control={"type": "ephemeral"}, **requete)
        c = cout(MODELE, reponse.usage)
        self.conv.cout_dollars += c.dollars
        self.conv.appels += 1
        entree = c.entree + c.lecture_cache + c.ecriture_cache
        if etape == "tour":
            self.conv.tokens_dernier_appel, self.conv.tokens_max = entree, max(self.conv.tokens_max, entree)
        noter(getattr(reponse, "_request_id", None), MODELE, c, chapitre="10", etape=f"conversation:{etape}",
              cas=self.conv.variante)
        if reponse.stop_reason == "max_tokens":
            self.conv.coupes.append(etape)   # un résumé ou un bloc coupé perd ses dernières lignes, sans prévenir
        return reponse

    def tour(self, messages: list, texte: str, systeme_prompt: str) -> str:
        """Un message de l'assuré, et autant d'appels qu'il en faut jusqu'à end_turn."""
        messages.append({"role": "user", "content": texte})
        for _ in range(GARDE_FOU):
            reponse = self.appeler("tour", max_tokens=MAX_TOKENS, system=systeme_prompt, tools=outils_v3.OUTILS,
                                   messages=messages)
            messages.append({"role": "assistant", "content": reponse.content})
            if reponse.stop_reason != "tool_use":
                return _texte(reponse.content)
            resultats = []
            for appel in (b for b in reponse.content if b.type == "tool_use"):
                sortie, erreur = outils_v3.executer(self.systeme, appel.name, appel.input)
                resultats.append({"type": "tool_result", "tool_use_id": appel.id, "content": sortie, "is_error": erreur})
            messages.append({"role": "user", "content": resultats})
        return "(garde-fou atteint)"

    def resumer(self, transcription: str) -> str:
        r = self.appeler("resume", max_tokens=MAX_TOKENS, messages=[{"role": "user", "content": f"{RESUMER}\n\n{transcription}"}],
                         **SANS_REFLEXION)
        return _texte(r.content)

    def mettre_a_jour_faits(self, bloc: str, transcription: str) -> str:
        r = self.appeler("faits", max_tokens=MAX_TOKENS, messages=[{"role": "user", "content": (
            f"{FAITS}\n\n## Bloc actuel\n{bloc or '(vide)'}\n\n## Suite de la conversation\n{transcription}")}],
            **SANS_REFLEXION)
        return _texte(r.content)


def transcrire(messages: list) -> str:
    """La conversation en texte : ce que disent l'assuré et l'agent, et ce que rendent les outils."""
    lignes = []
    for m in messages:
        contenu = m["content"]
        if isinstance(contenu, str):
            if contenu.startswith("Résumé de la conversation"):
                lignes.append(contenu)
            elif m["role"] == "user":
                lignes.append(f"Assuré : {contenu}")
            continue
        for b in contenu:
            genre = b.get("type") if isinstance(b, dict) else b.type
            if genre == "tool_result":
                lignes.append(f"[Résultat d'outil] {b['content']}")
            elif genre == "text" and m["role"] == "assistant":
                lignes.append(f"Agent : {b.text}")
            elif genre == "tool_use":
                lignes.append(f"[Appel d'outil] {b.name} {json.dumps(b.input, ensure_ascii=False)}")
    return "\n".join(lignes)


def avec_faits(bloc: str) -> str:
    return (PROMPT + "\n\n## Faits du dossier\nTenus à jour hors de la conversation. Ils font foi, même si "
            "l'historique a été résumé.\n\n" + bloc) if bloc else PROMPT


def retrouves(point: str) -> dict:
    return {nom: bool(re.search(f["motif"], point, re.IGNORECASE)) for nom, f in SCRIPT["faits"].items()}


def part_des_sorties(client, messages: list, systeme_prompt: str) -> float:
    """La part des sorties d'outils dans le contexte : comptage gratuit, avec et sans leur contenu."""
    plein = client.messages.count_tokens(model=MODELE, system=systeme_prompt, tools=outils_v3.OUTILS,
                                         messages=messages).input_tokens
    vides = [{**m, "content": [{**b, "content": "…"} if isinstance(b, dict) and b.get("type") == "tool_result" else b
                               for b in m["content"]]} if isinstance(m["content"], list) else m for m in messages]
    sans = client.messages.count_tokens(model=MODELE, system=systeme_prompt, tools=outils_v3.OUTILS,
                                        messages=vides).input_tokens
    return round((plein - sans) / plein, 3)


def converser(client, variante: str, repetition: int, budget_max: float) -> Conversation:
    conv = Conversation(variante, repetition)
    agent = Agent(client, Systeme(), conv, budget_max)
    messages, bloc, debut = [], "", time.perf_counter()
    try:
        for numero, texte in enumerate(SCRIPT["tours"], start=1):
            reponse = agent.tour(messages, texte, avec_faits(bloc))
            if numero == len(SCRIPT["tours"]):
                conv.point = reponse
            elif variante != "historique" and numero % TOUS_LES == 0:
                transcription = transcrire(messages)
                if variante == "resume-faits":
                    bloc = agent.mettre_a_jour_faits(bloc, transcription)
                resume = agent.resumer(transcription)
                conv.resumes.append(resume)
                messages = [{"role": "user", "content": f"Résumé de la conversation jusqu'ici : {resume}"},
                            {"role": "assistant", "content": "C'est noté. Je poursuis avec vous."}]
        if variante == "historique":
            conv.part_sorties_outils = part_des_sorties(client, messages, PROMPT)
    except Exception as erreur:
        conv.erreur = f"{type(erreur).__name__}: {erreur}"
    conv.bloc_faits, conv.faits_retrouves = bloc, retrouves(conv.point)
    conv.latence_s = round(time.perf_counter() - debut, 1)
    return conv


def nouvelle_seance(client, bloc: str, repetition: int, budget_max: float) -> Conversation:
    """Une séance neuve : rien que le bloc de faits, et la question du point."""
    conv = Conversation("nouvelle-seance", repetition, bloc_faits=bloc)
    agent, debut = Agent(client, Systeme(), conv, budget_max), time.perf_counter()
    try:
        conv.point = agent.tour([], SCRIPT["tours"][-1], avec_faits(bloc))
    except Exception as erreur:
        conv.erreur = f"{type(erreur).__name__}: {erreur}"
    conv.faits_retrouves, conv.latence_s = retrouves(conv.point), round(time.perf_counter() - debut, 1)
    return conv


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 10 : une conversation de 40 tours.")
    parser.add_argument("--variantes", nargs="*", default=["historique", "resume", "resume-faits"],
                        choices=["historique", "resume", "resume-faits"])
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--budget-max", type=float, default=0.60)
    parser.add_argument("--reevaluer", type=Path, default=None,
                        help="recompter les faits d'un fichier de résultats avec les motifs actuels, sans appel")
    args = parser.parse_args()
    if args.reevaluer:
        d = json.loads(args.reevaluer.read_text(encoding="utf-8"))
        for c in d["conversations"]:
            c["faits_retrouves"] = retrouves(c["point"])
            print(f"{c['variante']} #{c['repetition']} : {sum(c['faits_retrouves'].values())}/{len(c['faits_retrouves'])}"
                  f" ; manquent : {[k for k, v in c['faits_retrouves'].items() if not v]}")
        args.reevaluer.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    client, conversations, depense = anthropic.Anthropic(), [], 0.0
    for repetition in range(1, args.repetitions + 1):
        for variante in args.variantes:
            c = converser(client, variante, repetition, args.budget_max - depense)
            conversations.append(c)
            depense += c.cout_dollars
            if variante == "resume-faits" and c.bloc_faits and not c.erreur:
                n = nouvelle_seance(client, c.bloc_faits, repetition, args.budget_max - depense)
                conversations.append(n)
                depense += n.cout_dollars
    for c in conversations:
        print(f"{c.variante} #{c.repetition} : {sum(c.faits_retrouves.values())}/{len(c.faits_retrouves)} faits ; "
              f"manquent : {[k for k, v in c.faits_retrouves.items() if not v]} ; {c.appels} appels ; "
              f"dernier appel {c.tokens_dernier_appel} tokens ; {francais(c.cout_dollars, 4)} $"
              + (f" ; sorties d'outils {round(100 * c.part_sorties_outils)} % du contexte" if c.part_sorties_outils else "")
              + (f" ; coupés par max_tokens : {c.coupes}" if c.coupes else "") + (f" ; {c.erreur}" if c.erreur else ""))
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / "resultats" / f"conversation-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "depense_dollars": round(depense, 6),
                                  "conversations": [asdict(c) for c in conversations]}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
