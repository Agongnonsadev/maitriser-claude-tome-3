"""Chapitre 13 : relire une extraction. Auto-relecture contre relecture par une instance indépendante.

Les extractions relues sont celles du prompt v2 sur l'échantillon : treize documents y gardent au moins
un champ faux après la correction du code, des immatriculations « corrigées » à tort et des
immatriculations lisibles mises à null. Ce sont de vraies erreurs du modèle, pas des erreurs fabriquées.

Deux relectures, avec la même consigne et le même outil (signaler) ; seul le contexte change :
- auto : la conversation de l'extraction continue. Le modèle a sous les yeux le prompt v2, le document et
  son propre appel d'outil, et on lui demande de se relire ;
- independante : une nouvelle conversation, un prompt de relecteur, le document et l'extraction en JSON.
  Le relecteur ne voit ni le prompt qui l'a produite ni la confiance déclarée.

On compte, pour chaque relecture, les champs faux signalés, les champs faux manqués, et les fausses
alertes (un champ juste signalé comme faux).

Lancement, depuis le dossier python/ :
  python -m ch13.relecture ch13/resultats/echantillon-v1-v2-<date>.json --budget-max 0.12
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

import anthropic

from assureur import config
from assureur.couts import cout, francais
from assureur.journal import noter
from ch13.archive import fabriquer
from ch13.extraction import CHAMPS, MAX_TOKENS, MODELE, normaliser, outil, prompt

DOSSIER = Path(__file__).parent / "resultats"

# Première version, abandonnée : un tableau champs_faux (les noms des champs faux). Haiku 5.5 y a mis
# presque tous les champs, justes compris : 56 fausses alertes en auto-relecture, 81 en relecture
# indépendante, sur 57 documents justes. La version gardée fait écrire, pour chaque champ, ce que le
# document dit, avant le verdict : la relecture compare au lieu de lister.
SIGNALER = {
    "name": "signaler",
    "description": "Rend le résultat de la relecture, champ par champ : ce que dit le document, puis le verdict. "
                   "plaque_a et contrat_a sont dans vehicule_a ; plaque_b et assureur_b dans vehicule_b.",
    "input_schema": {
        "type": "object",
        "properties": {c: {"type": "object",
                           "properties": {"dans_le_document": {"type": ["string", "null"],
                                                               "description": "La valeur telle que le document la donne, null s'il ne la donne pas lisiblement"},
                                          "verdict": {"type": "string", "enum": ["conforme", "different"]}},
                           "required": ["dans_le_document", "verdict"], "additionalProperties": False}
                       for c in CHAMPS},
        "required": CHAMPS,
        "additionalProperties": False,
    },
}

# Deuxième version, remplacée par la troisième : la consigne sans les règles de l'extraction. Les deux
# relectures ont alors compté comme fausses les immatriculations à « ? » mises à null et les blessés
# « unclear » d'un récit contradictoire : 27 et 25 fausses alertes. Le relecteur indépendant ne reçoit
# pas le contexte de l'extraction, mais il doit recevoir ses critères.
CONSIGNE = """Relisez l'extraction champ par champ contre le document. Pour chaque champ, écrivez d'abord dans dans_le_document la valeur que donne le document, puis le verdict : « conforme » si l'extraction dit la même chose, « different » sinon, y compris pour une valeur mise à null alors que le document la donne lisiblement. Dans un document numérisé, 8 et B, 0 et O, 5 et S, 1 et I se confondent ; une immatriculation suit le motif deux lettres, quatre chiffres, deux lettres. Une différence de format seulement (espaces, tirets, majuscules, date écrite autrement, heure écrite « 13 h 20 » au lieu de « 13:20 ») reste conforme : le système normalise les formats.

Les règles de l'extraction, qui sont conformes :
- une immatriculation qui contient un caractère illisible, comme « ? », vaut null ;
- l'heure est celle de la case Heure, même si le récit en donne une autre ;
- si la case des blessés dit « non » mais que le récit parle d'une personne blessée ou qui souffre, les blessés valent « unclear » ;
- un assureur abrégé, comme « Lag. Ass. », s'écrit en entier : Lagune Assurances, Atacora Garantie, Ouémé Mutuelle."""

RELECTEUR = """Vous relisez, pour Kanvô Assurances, des extractions de constats amiables d'accident faites par un autre système. Vous ne les avez pas produites. Votre rôle est de trouver les champs faux, sans rien corriger vous-même."""


def _demande(messages: list, systeme: str, tools: list) -> dict:
    return {"model": MODELE, "max_tokens": MAX_TOKENS, "system": systeme, "tools": tools, "messages": messages,
            "tool_choice": {"type": "tool", "name": "signaler"}, "thinking": {"type": "disabled"}}


def _enregistree(arguments: dict) -> str:
    """L'extraction telle que le système l'enregistre : plaques normalisées, sans la confiance."""
    return json.dumps({k: v for k, v in normaliser(arguments).items() if k != "confiance"}, ensure_ascii=False, indent=1)


def auto(document: dict, arguments: dict) -> dict:
    """La conversation de l'extraction, continuée : le modèle relit son propre appel d'outil, puis ce que le
    système en a enregistré."""
    identifiant = f"toolu_{document['id'].replace('-', '_')}"
    return _demande([
        {"role": "user", "content": f"Document :\n\n{document['texte']}"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": identifiant, "name": "extraire_constat", "input": arguments}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": identifiant,
                                      "content": f"Extraction enregistrée, immatriculations normalisées :\n\n{_enregistree(arguments)}"},
                                     {"type": "text", "text": CONSIGNE}]},
    ], prompt("v2"), [outil(), SIGNALER])


def independante(document: dict, arguments: dict) -> dict:
    """Une autre instance : le document et l'extraction enregistrée, sans le prompt qui l'a produite ni sa
    confiance."""
    return _demande([{"role": "user", "content": f"Document :\n\n{document['texte']}\n\nExtraction à relire :\n\n"
                                                 f"{_enregistree(arguments)}\n\n{CONSIGNE}"}],
                    RELECTEUR, [SIGNALER])


def relire(client, mode: str, document: dict, essai: dict, repetition: int = 1) -> dict:
    r = client.messages.create(**(auto if mode == "auto" else independante)(document, essai["arguments"]))
    c = cout(MODELE, r.usage)
    noter(getattr(r, "_request_id", None), MODELE, c, chapitre="13", etape="relecture", cas=f"{mode}:{document['id']}")
    appel = next((b for b in r.content if b.type == "tool_use"), None)
    signales = {c for c, v in appel.input.items() if isinstance(v, dict) and v.get("verdict") == "different"} if appel else set()
    faux = {k for k, i in essai["corrige"]["issues"].items() if i != "juste"}
    return {"mode": mode, "document": document["id"], "difficulte": document["difficulte"], "repetition": repetition,
            "faux": sorted(faux), "signales": sorted(signales), "trouves": sorted(faux & signales),
            "manques": sorted(faux - signales), "fausses_alertes": sorted(signales - faux), "cout_dollars": c.dollars,
            "sortie": appel.input if appel else None}


def resumer(relectures: list[dict]) -> dict:
    lignes = {}
    for mode in ("auto", "independante"):
        g = [x for x in relectures if x["mode"] == mode]
        faux = sum(len(x["faux"]) for x in g)
        lignes[mode] = {"champs_faux": faux, "trouves": sum(len(x["trouves"]) for x in g),
                        "manques": sum(len(x["manques"]) for x in g),
                        "fausses_alertes": sum(len(x["fausses_alertes"]) for x in g),
                        "documents_fautifs_reperes": sum(bool(x["trouves"]) for x in g if x["faux"]),
                        "documents_fautifs": sum(bool(x["faux"]) for x in g),
                        "documents_justes_signales": sum(bool(x["signales"]) for x in g if not x["faux"]),
                        "documents_justes": sum(not x["faux"] for x in g),
                        "depense_dollars": round(sum(x["cout_dollars"] for x in g), 6)}
    return lignes


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 13 : auto-relecture contre relecture indépendante.")
    parser.add_argument("echantillon", type=Path, help="un fichier de ch13.echantillon qui contient la v2")
    parser.add_argument("--version", default="v2")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--budget-max", type=float, default=0.12)
    args = parser.parse_args()
    archive = {c["id"]: c for c in fabriquer()}
    essais = [e for e in json.loads(args.echantillon.read_text(encoding="utf-8"))["essais"]
              if e["version"] == args.version and e["arguments"] is not None]
    if len(essais) * 2 * args.repetitions * 0.0008 > args.budget_max:   # large : 0,0008 $ par relecture
        raise SystemExit("Estimation au-dessus du plafond.")
    client = anthropic.Anthropic()
    with ThreadPoolExecutor(max_workers=6) as pool:
        relectures = list(pool.map(lambda t: relire(client, t[0], archive[t[1]["document"]], t[1], t[2]),
                                   [(m, e, k) for k in range(1, args.repetitions + 1)
                                    for m in ("auto", "independante") for e in essais]))
    resume = resumer(relectures)
    print(json.dumps(resume, ensure_ascii=False, indent=1))
    depense = sum(x["cout_dollars"] for x in relectures)
    print(f"\nDépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    sortie = DOSSIER / f"relecture-{args.version}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": MODELE, "source": args.echantillon.name,
                                  "depense_dollars": round(depense, 6), "resume": resume, "relectures": relectures},
                                 ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
