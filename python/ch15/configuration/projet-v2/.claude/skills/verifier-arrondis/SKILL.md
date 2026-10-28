---
name: verifier-arrondis
description: Relève, dans un dossier du logiciel des contrats, les calculs de montants et l'arrondi que chacun utilise. À lancer avant une revue, ou quand on demande si les arrondis sont conformes.
argument-hint: "[dossier]"
allowed-tools: Read Grep Glob
context: fork
background: false
---

Relevez, dans le dossier `$ARGUMENTS` (tout le dépôt s'il est vide), chaque calcul qui produit un montant en FCFA.

Pour chacun, donnez une ligne : fichier, numéro de ligne, fonction, arrondi utilisé (`arrondir_fcfa`, `int`, `round`, ou aucun).

Terminez par le compte de chaque sorte d'arrondi. Ne modifiez aucun fichier.
