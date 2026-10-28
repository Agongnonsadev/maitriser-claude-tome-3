---
paths:
  - "tarifs/**"
  - "primes/**"
---

# Les tarifs

- Les fichiers de `tarifs/` viennent de l'actuariat : ne jamais les modifier. Un taux nouveau arrive par une note de l'actuariat, que la DSI reporte elle-même.
- Le code lit les taux dans `tarifs/` avec `primes/tarifs.py` : jamais de taux écrit en dur.
