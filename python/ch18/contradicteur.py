"""Chapitre 18 : faire relire le dossier de la mission 2 par un contradicteur, avant le comité d'éthique.

Claude lit ch18/dossier-mission-2.md dans le rôle d'un membre exigeant du comité d'éthique, et rend ses
questions en sortie structurée (output_config.format, un schéma JSON) : la question, pourquoi elle compte, ce que le dossier en dit (une citation, ou
null s'il n'en dit rien), et son thème. Plusieurs tirages : on garde ce qui revient, pas ce qu'un seul tirage a
pensé. Le contradicteur aide à préparer la séance ; il ne remplace pas le comité.

Lancement, depuis le dossier python/ :
    python -m ch18.contradicteur --tirages 3 --budget-max 0.15
"""

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import cout, francais
from assureur.journal import noter

DOSSIER = Path(__file__).parent
MODELE = "claude-sonnet-5-5"
THEMES = ["patient", "medecin", "donnees", "securite", "equite", "gouvernance", "autre"]

OUTIL = {
    "name": "poser_les_questions",
    "description": "Les questions du comité d'éthique sur le dossier.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"questions": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "pourquoi": {"type": "string", "description": "Pourquoi le comité la pose"},
                "ce_que_dit_le_dossier": {"type": ["string", "null"],
                                          "description": "Une citation du dossier qui y répond, ou null"},
                "theme": {"type": "string", "enum": THEMES},
            },
            "required": ["question", "pourquoi", "ce_que_dit_le_dossier", "theme"],
            "additionalProperties": False,
        }}},
        "required": ["questions"],
        "additionalProperties": False,
    },
}

SYSTEME = """Vous êtes membre du comité d'éthique d'un groupe de cliniques privées. On vous présente le dossier d'un projet : un assistant qui rédige le brouillon des comptes rendus de consultation à partir des notes du médecin.

Posez les questions qu'un comité exigeant poserait avant d'autoriser un pilote, d'abord celles auxquelles le dossier ne répond pas. Pour chacune, dites ce que le dossier en dit, en le citant, ou null s'il n'en dit rien. Huit questions au plus."""


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 18 : le contradicteur du dossier de la mission 2.")
    parser.add_argument("--tirages", type=int, default=3)
    parser.add_argument("--modele", default=MODELE)
    parser.add_argument("--budget-max", type=float, default=0.15)
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    import anthropic
    client = anthropic.Anthropic()
    dossier = (DOSSIER / "dossier-mission-2.md").read_text(encoding="utf-8")
    tirages, depense = [], 0.0
    for i in range(1, args.tirages + 1):
        if args.budget_max - depense < 0.03:
            print("Arrêt : plafond presque atteint.")
            break
        # Claude Sonnet 5.5 refuse un outil imposé (tool_choice « tool » ou « any » : erreur 400) : la forme de la
        # réponse passe par les sorties structurées, avec le même schéma.
        r = client.messages.create(model=args.modele, max_tokens=4000, system=SYSTEME,
                                   output_config={"format": {"type": "json_schema", "schema": OUTIL["input_schema"]}},
                                   messages=[{"role": "user", "content": dossier}])
        k = cout(args.modele, r.usage)
        noter(r.id, args.modele, k, chapitre="18", etape="contradicteur", cas=f"tirage {i}")
        depense += k.dollars
        texte = "".join(b.text for b in r.content if b.type == "text")
        try:
            questions = json.loads(texte).get("questions", [])
        except json.JSONDecodeError:
            questions = []
            print(f"Tirage {i} : réponse illisible ({r.stop_reason})")
        tirages.append({"tirage": i, "cout_dollars": round(k.dollars, 6), "questions": questions})
        sans = [q for q in questions if not q.get("ce_que_dit_le_dossier")]
        print(f"Tirage {i} : {len(questions)} questions, dont {len(sans)} sans réponse dans le dossier ; "
              f"{francais(k.dollars, 4)} $")
    themes = Counter(q["theme"] for t in tirages for q in t["questions"] if not q.get("ce_que_dit_le_dossier"))
    sortie = DOSSIER / "resultats" / f"contradicteur-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": args.modele,
                                  "depense_dollars": round(depense, 6), "themes_sans_reponse": dict(themes),
                                  "tirages": tirages}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Thèmes des questions sans réponse : {dict(themes)}")
    print(f"Dépense : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA) ; résultats : {sortie}")


if __name__ == "__main__":
    principal()
