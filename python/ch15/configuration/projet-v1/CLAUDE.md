# Logiciel des contrats de Kanvô Assurances

Ancien logiciel de la DSI (2011), en Python, sans tests automatiques. Voir @LISEZMOI.txt pour l'organisation des dossiers.

## Conventions de l'équipe

- Les montants sont des entiers en FCFA. Tout nouveau calcul de montant passe par `arrondir_fcfa()` de `util/montants.py` : jamais `int()`, qui tronque, ni `round()`, qui arrondit au pair.
- Ne corrigez pas les arrondis existants sans ticket : leur correction change des primes déjà facturées (ticket DSI-2019-114).
- Les fichiers de `tarifs/` viennent de l'actuariat : ne jamais les modifier, lire les taux dedans.
- Les requêtes SQL prennent des paramètres `?`, jamais un texte formaté avec `%`.
