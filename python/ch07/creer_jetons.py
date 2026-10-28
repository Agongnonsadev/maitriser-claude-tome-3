"""Chapitre 7 : créer les jetons des comptes de service, comme le ferait la DSI.

Le registre (les empreintes seulement) va dans ~/.kanvo/jetons.json, hors du dépôt. Les jetons s'affichent
une fois : rangez-les dans votre gestionnaire de secrets, ou dans votre environnement, puis fermez le
terminal. Ils ne sont écrits nulle part ailleurs.

Lancement, depuis le dossier python/ :  python -m ch07.creer_jetons
"""

import argparse
from pathlib import Path

from assureur.jetons import COMPTES, creer_registre


def principal() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registre", type=Path, default=Path.home() / ".kanvo" / "jetons.json")
    args = parser.parse_args()
    jetons = creer_registre(args.registre)
    print(f"Registre des empreintes : {args.registre}\n")
    for compte, jeton in jetons.items():
        print(f"{compte} ({', '.join(COMPTES[compte])}) : {jeton}")
    print(f"\nPour Claude Code, dans votre environnement (pas dans le dépôt) :\n"
          f"  KANVO_JETONS={args.registre}\n  KANVO_JETON=<le jeton du compte tableau-de-bord>")


if __name__ == "__main__":
    principal()
