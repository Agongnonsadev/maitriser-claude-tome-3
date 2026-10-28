"""Les jetons des comptes de service, tels que la DSI de Kanvô Assurances (fictive) les délivre.

Un compte de service par usage, avec ses portées, et rien de plus :
- agent-sinistres : l'agent des sinistres lit les dossiers et transmet à un gestionnaire ;
- tableau-de-bord : l'équipe informatique lit, mais ne transmet rien.
La portée indemnisations:ecriture existe déjà ; aucun compte ne l'a encore (chapitre 8).

Le registre ne contient que l'empreinte SHA-256 de chaque jeton : le jeton lui-même vit dans
l'environnement de celui qui s'en sert (un gestionnaire de secrets, en production), jamais dans
un fichier du dépôt. Volé, le registre ne donne accès à rien.
"""

import hashlib
import json
import secrets
from pathlib import Path

PORTEES = ("sinistres:lecture", "transmissions:ecriture", "indemnisations:ecriture")

COMPTES = {
    "agent-sinistres": ["sinistres:lecture", "transmissions:ecriture"],
    "tableau-de-bord": ["sinistres:lecture"],
}


def empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("utf-8")).hexdigest()


def creer_registre(chemin: Path, comptes: dict[str, list[str]] = COMPTES) -> dict[str, str]:
    """Crée un jeton par compte, écrit le registre des empreintes, et rend les jetons (à ranger aussitôt)."""
    jetons = {compte: "kanvo_" + secrets.token_urlsafe(24) for compte in comptes}
    registre = {empreinte(j): {"compte": c, "portees": comptes[c]} for c, j in jetons.items()}
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(registre, ensure_ascii=False, indent=2), encoding="utf-8")
    return jetons


def identifier(jeton: str | None, chemin: Path) -> tuple[str, set[str]] | None:
    """(compte, portées) du jeton, ou None s'il est absent ou inconnu."""
    if not jeton or not Path(chemin).exists():
        return None
    entree = json.loads(Path(chemin).read_text(encoding="utf-8")).get(empreinte(jeton))
    return (entree["compte"], set(entree["portees"])) if entree else None
