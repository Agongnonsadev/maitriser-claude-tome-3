"""Chapitre 24 : vérifier qu'un document de passation ne ment pas.

Une passation cite des fichiers et des commandes. Le jour où l'équipe en a besoin, un fichier déplacé ou une commande
renommée la laisse seule devant une panne. Ce script relit le document et vérifie, sans aucun appel :
- que chaque chemin cité entre accents graves (ch18/compte_rendu.py, cliniques/notes.py…) existe ;
- que chaque module lancé par « python -m » existe.
Les chemins qui contiennent un gabarit (<date>, <fichier>…) sont vérifiés jusqu'à leur dossier.

Lancement, depuis le dossier python/ :
    python -m ch24.verifier_passation ch24/document-de-passation.md       # code de sortie 1 si un renvoi est cassé
"""

import argparse
import importlib.util
import re
import sys
from pathlib import Path

RACINE = Path(__file__).parent.parent
CHEMIN = re.compile(r"`((?:ch\d\d|cliniques|assureur|tests)/[^`\s]*)`")
MODULE = re.compile(r"python -m ([\w.]+)")


def renvois(texte: str) -> tuple[list[str], list[str]]:
    return sorted(set(CHEMIN.findall(texte))), sorted(set(MODULE.findall(texte)))


def verifier(texte: str, racine: Path = RACINE) -> list[str]:
    """La liste des renvois cassés ; vide si tout existe."""
    chemins, modules = renvois(texte)
    casses = []
    for c in chemins:
        avant = c.split("<")[0]                 # un gabarit se vérifie jusqu'à son dossier
        cible = racine / avant if avant == c or avant.endswith("/") else (racine / avant).parent
        if not cible.exists():
            casses.append(f"fichier introuvable : {c}")
    for m in modules:
        if m != "pytest" and not existe(m):
            casses.append(f"module introuvable : python -m {m}")
    return casses


def existe(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:         # le paquet parent lui-même n'existe pas
        return False


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 24 : les renvois d'un document de passation existent-ils ?")
    parser.add_argument("document")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    texte = Path(args.document).read_text(encoding="utf-8")
    chemins, modules = renvois(texte)
    casses = verifier(texte)
    for c in casses:
        print(c)
    print(f"{len(chemins)} fichiers et {len(modules)} commandes cités ; {len(casses)} renvoi(s) cassé(s)")
    sys.exit(1 if casses else 0)


if __name__ == "__main__":
    principal()
