"""La bibliothèque de prompts de Kanvô Assurances (chapitre 11) : des prompts versionnés, assemblés,
évalués comme du code.

Le registre (prompts/bibliotheque.json) donne, pour chaque prompt, son rôle, son modèle, ses réglages,
la version en service et ses versions. Une version est un fichier, ou une suite de modules
(prompts/modules/) que le code assemble dans l'ordre du registre : le contexte de l'entreprise d'abord,
puis la tâche, les critères, les exemples, le format. Les parties stables en tête gardent le préfixe
commun que le cache réutilise d'un appel à l'autre.

Règles vérifiées par les tests (tests/test_ch11.py) :
- chaque module et chaque fichier cité existe ;
- la version en service a une évaluation, et le fichier de cette évaluation existe ;
- l'empreinte d'une version (SHA-256 du texte assemblé) se note avec chaque mesure : on sait toujours
  quel texte exact a été évalué.
"""

import hashlib
import json
from pathlib import Path

DOSSIER = Path(__file__).parent / "prompts"
RACINE = Path(__file__).parents[1]          # le dossier python/, d'où partent les chemins des évaluations


def registre() -> dict:
    return json.loads((DOSSIER / "bibliotheque.json").read_text(encoding="utf-8"))["prompts"]


def version(nom: str, numero: str | None = None) -> tuple[str, dict]:
    """(numéro, fiche) d'une version ; sans numéro, la version en service."""
    fiche = registre()[nom]
    numero = numero or fiche["en_service"]
    if numero is None:
        raise ValueError(f"Le prompt {nom!r} n'a pas de version en service : donnez un numéro.")
    return numero, fiche["versions"][numero]


def assembler(nom: str, numero: str | None = None) -> str:
    """Le texte d'une version : son fichier, ou ses modules, dans l'ordre, séparés par une ligne vide."""
    _, v = version(nom, numero)
    if "fichier" in v:
        return (DOSSIER / v["fichier"]).read_text(encoding="utf-8").strip()
    return "\n\n".join((DOSSIER / "modules" / f"{m}.md").read_text(encoding="utf-8").strip() for m in v["modules"])


def empreinte(nom: str, numero: str | None = None) -> str:
    return hashlib.sha256(assembler(nom, numero).encode("utf-8")).hexdigest()[:12]


def verifier() -> list[str]:
    """Les problèmes de la bibliothèque ; une liste vide si tout est en ordre."""
    problemes = []
    for nom, fiche in registre().items():
        for numero, v in fiche["versions"].items():
            fichiers = [DOSSIER / v["fichier"]] if "fichier" in v else [DOSSIER / "modules" / f"{m}.md"
                                                                           for m in v["modules"]]
            problemes += [f"{nom} v{numero} : {f.name} manque" for f in fichiers if not f.exists()]
        service = fiche.get("en_service")
        if service is not None:
            v = fiche["versions"][service]
            if v.get("statut") != "en_service":
                problemes.append(f"{nom} : la version {service} est en service mais marquée {v.get('statut')!r}")
            if not v.get("evaluation"):
                problemes.append(f"{nom} : la version en service {service} n'a pas d'évaluation")
            elif not (RACINE / v["evaluation"]).exists():
                problemes.append(f"{nom} : l'évaluation {v['evaluation']} est introuvable")
        if sum(v.get("statut") == "en_service" for v in fiche["versions"].values()) > 1:
            problemes.append(f"{nom} : plusieurs versions en service")
    return problemes
