# Essai A/B des comptes rendus — hypothèse écrite avant l'essai

*Écrite le 28 octobre 2026, après l'étalonnage du juge et avant le premier compte rendu de l'essai. Exemple fictif pour les Cliniques Ébène ; les notes sont fabriquées (`cliniques/notes.py`).*

## Les deux bras

- **A** : le prompt `mission2` du chapitre 18 (conclusion recopiée avec ses réserves, rien d'ajouté, brouillon validé par le médecin).
- **B** : le même, avec trois règles de fidélité du détail : la réserve reste dans la conclusion avec sa condition, jamais en décision de suivi ; les côtés, les durées et les chiffres recopiés exactement ; chaque constatation gardée, même brève.

Même modèle pour les deux (Claude Haiku 5.5, outil imposé), mêmes vingt notes, trois fois chacune.

## L'hypothèse

B réduit la part des comptes rendus à corriger. Le défaut visé est celui que le chapitre 18 a vu dans un brouillon et qu'aucun contrôle du code ne voyait : une réserve du médecin déplacée en décision de suivi.

## La mesure

Un compte rendu est à corriger si le juge étalonné (Claude Haiku 5.5, version v2, 100 % d'accord avec les annotations sur 90 jugements) le dit, ou si un contrôle du code du chapitre 18 le signale.

## La règle de décision, fixée avant l'essai

- B est adopté si sa part de comptes rendus à corriger est plus basse, avec un test exact de Fisher bilatéral à p < 0,05.
- Sinon, A reste en place : il est plus court, et l'essai n'a pas montré mieux. Un écart non significatif ne prouve pas que les deux se valent.

## La taille

60 comptes rendus par bras (20 notes, 3 fois). Avec un risque de 5 % et une puissance de 80 % :
- une baisse de 25 % à 5 % demande 49 comptes rendus par bras : l'essai la verrait ;
- une baisse de 20 % à 5 % en demande 76, une baisse de 15 % à 5 %, 141 : l'essai ne permettrait pas de conclure.

Les comptes rendus d'une même note ne sont pas indépendants : trois tirages d'une note pèsent moins que trois notes. La lecture regardera aussi les défauts note par note.
