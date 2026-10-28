---
paths:
  - "base/**"
  - "rapports/**"
---

# La base

- Les requêtes SQL prennent des paramètres `?`, jamais un texte formaté avec `%` : deux fonctions anciennes de `base/requetes.py` le font encore, ne les imitez pas.
- Les données de la base de production sont celles des assurés : on ne les copie ni dans le code, ni dans une conversation.
