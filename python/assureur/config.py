"""Réglages communs, lus dans l'environnement quand ils existent.

La clé d'API n'apparaît jamais ici : le SDK la lit lui-même dans la variable
d'environnement ANTHROPIC_API_KEY.
"""

import os

# Taux de conversion du livre (1 $ = 570 FCFA ≈ 0,87 €).
TAUX_FCFA = float(os.environ.get("KANVO_TAUX_FCFA", "570"))
TAUX_EUR = float(os.environ.get("KANVO_TAUX_EUR", "0.87"))

# Chaque appel est noté ici : identifiant de requête, modèle, tokens, coût. Hors du dépôt.
JOURNAL = os.environ.get("KANVO_JOURNAL", "journal/appels.jsonl")
