# Note de passation — mission 1, Kanvô Assurances, activation Claude Code de l'équipe applications

*Exemple fictif : Kanvô Assurances, son équipe et ses noms sont inventés pour le livre. Les valeurs entre crochets se remplissent sur la mission.*

**De :** Yao, Forward Deployed Engineer, Nokoué Conseil
**À :** le relais de l'équipe applications, et M. Ahouansou, directeur des systèmes d'information
**Date :** [jour 30]

## 1. Ce qui est en place

| Élément | Où | Qui en répond |
|---|---|---|
| Le `CLAUDE.md` du dépôt et les règles par chemin | `CLAUDE.md`, `.claude/rules/` | Le relais |
| Les interdits de l'équipe | `.claude/settings.json` | Le relais, avec la DSI |
| La Skill `/verifier-arrondis` | `.claude/skills/verifier-arrondis/` | Le relais |
| La carte du logiciel | `notes/carte.md` | Toute l'équipe, à chaque évolution |
| Les tests de l'échéancier, et le manifeste du chantier des tests | `tests/`, `notes/manifeste-tests.json` | [le développeur désigné] |
| La revue des demandes de fusion | La chaîne d'intégration continue ; les critères dans le `CLAUDE.md` | Le relais |
| Le plafond de dépense | L'espace de travail Claude Code de la Console | La DSI |

## 2. Comment le faire vivre

- **Chaque vendredi**, trente minutes : les constats de revue rejetés, regroupés par `detected_pattern` ; une règle à réécrire, ou à couper le temps de la réécrire.
- **Une nouvelle convention** entre dans le dépôt par une demande de fusion, relue par le relais.
- **Chaque arrivée** commence par `/memory` sur son poste, avec le relais.
- **Chaque correction de montant** arrive avec ses exemples, ou ses tests.

## 3. Ce qui reste à faire

- Le chantier des tests : [modules restants, d'après le manifeste].
- Les arrondis anciens (`int()`, `round()`) : ils attendent le ticket DSI-2019-114 ; leur correction change des primes déjà facturées.
- La liste de branches de `numeros.valide()`, à faire lire dans `config.BRANCHES`.
- [La décision sur la revue de nuit.]

## 4. Ce qu'il ne faut pas faire

- Écrire une consigne d'équipe dans un dossier personnel.
- Laisser la revue tourner avec une règle qui déclenche à tort : l'équipe cesse de la lire.
- Approuver un plan sans avoir répondu à ses questions.
- Reprendre une séance sans dire ce qui a changé depuis.
- Ouvrir `tarifs/` ou `donnees/` à Claude Code : les refus de `.claude/settings.json` restent.

## 5. Les chiffres du jour 30

Voir `bilan-30-jours.md` : les critères contre la situation de départ, ce que l'activation a coûté, les échecs évités avec leur preuve.

## 6. Contacts

- Le relais : [nom].
- Nokoué Conseil, pour la suite : [contact].
