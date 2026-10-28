---
paths:
  - "primes/**"
  - "quittances/**"
  - "contrats/**"
---

# Les montants

- Les montants sont des entiers en FCFA. Tout nouveau calcul de montant passe par `arrondir_fcfa()` de `util/montants.py` : jamais `int()`, qui tronque, ni `round()`, qui arrondit au pair.
- Ne corrigez pas les arrondis existants sans ticket : leur correction change des primes déjà facturées (ticket DSI-2019-114).
