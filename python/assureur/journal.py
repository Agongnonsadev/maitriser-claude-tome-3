"""Noter chaque appel dans un journal : de quoi retrouver une requête et suivre les coûts.

Une ligne JSON par appel : l'identifiant de la requête (à donner au support d'Anthropic en
cas de problème), le modèle, les tokens et le coût. Jamais la clé d'API, jamais le contenu
des messages : dans une vraie mission, ce sont des données du client.
"""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from assureur import config
from assureur.couts import Cout

# Plusieurs fils peuvent noter en même temps (chapitre 11) : sans verrou, des lignes se perdent.
_VERROU = threading.Lock()


def noter(identifiant: str | None, modele: str, cout: Cout, chemin: str | None = None, **details) -> dict:
    """details : ce qui aide à relire le journal (chapitre, cas d'usage…). Les valeurs None ne sont pas écrites."""
    ligne = {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "requete": identifiant,
        "modele": modele,
        "tokens_entree": cout.entree,
        "tokens_ecriture_cache": cout.ecriture_cache,
        "tokens_lecture_cache": cout.lecture_cache,
        "tokens_sortie": cout.sortie,
        "tokens_reflexion": cout.reflexion,
        "cout_dollars": round(cout.dollars, 6),
    }
    ligne.update({cle: valeur for cle, valeur in details.items() if valeur is not None})
    fichier = Path(chemin or config.JOURNAL)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    with _VERROU, fichier.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    return ligne
