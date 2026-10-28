# Activation Claude Code de 30 jours — équipe applications de la DSI de Kanvô Assurances

*Exemple fictif : Kanvô Assurances, son équipe et son logiciel des contrats sont inventés pour le livre. Les valeurs entre crochets se mesurent avant le lancement : ce plan ne les invente pas.*

## 1. Qualification

| Critère | Ce que Yao a relevé | Verdict |
|---|---|---|
| Volume | Six développeurs ; les évolutions du logiciel des contrats arrivent chaque semaine, avec les notes de l'actuariat | Suffisant |
| Complexité | Un logiciel de 2011, sans tests, aux arrondis différents d'un module à l'autre | Le gain se joue sur la compréhension du code |
| Mesurabilité | Délai d'une évolution, anomalies trouvées en recette, temps passé à relire | Mesurable avant et après |
| Maturité | Deux développeurs ont déjà essayé Claude Code chez eux ; aucun cadre d'équipe | Relais disponibles |

**Gain visé :** structurel, pas marginal. Une évolution livrée avec ses tests sur un logiciel que personne n'ose toucher, plutôt que quelques minutes gagnées par jour.

## 2. Situation de départ (semaine 0, avant le lancement)

- Délai moyen entre une note de l'actuariat et sa mise en production : [à mesurer sur les six dernières notes].
- Anomalies trouvées en recette par évolution : [à mesurer].
- Part du code couverte par des tests : 0 %.
- Temps de prise en main d'un nouveau développeur : [à demander au dernier arrivé].

## 3. Cohorte, périmètre, durée, critères

- **Cohorte :** quatre développeurs de l'équipe applications, dont la dernière arrivée, et un relais interne.
- **Périmètre :** le logiciel des contrats seulement. Ni la base de production, ni les tarifs, ni les données des assurés.
- **Durée :** 30 jours, du lancement à la démonstration à la DSI.
- **Critères de réussite, fixés avec M. Ahouansou :**
  - le délai d'une évolution baisse, contre la situation de départ ;
  - aucune anomalie de montant en recette sur les évolutions faites avec Claude Code ;
  - chaque évolution arrive avec ses tests ;
  - la dépense reste sous le plafond du pilote.

## 4. Configuration d'équipe (avant le lancement)

- `CLAUDE.md` du dépôt, court, versionné avec le code ; les règles d'un dossier dans `.claude/rules/`, chargées pour leurs seuls fichiers.
- Permissions partagées dans `.claude/settings.json` : jamais d'écriture dans `tarifs/`, jamais de lecture de `donnees/`.
- Une Skill d'équipe, `/verifier-arrondis`, qui tourne à part et ne modifie rien.
- Plafond de dépense du pilote sur l'espace de travail Claude Code de la Console : [montant fixé par la DSI].
- Postes derrière le proxy de Kanvô : `HTTPS_PROXY` dans la configuration gérée, et non sur chaque poste.

## 5. Rythme hebdomadaire

| Semaine | Ce que l'équipe fait | Ce que Yao mesure |
|---|---|---|
| 1 | Configuration d'équipe ; premières évolutions supervisées, relues par Yao | Les consignes reçues par chacun (`/memory`) ; les écarts aux règles |
| 2 | Cartographie de l'ancien logiciel et premiers tests (chapitre 16) | Le temps passé à comprendre un module |
| 3 | Évolutions déléguées, avec plan écrit ; revue automatique des demandes de fusion (chapitre 17) | Les constats de revue acceptés et rejetés |
| 4 | Mesure contre la situation de départ ; préparation de la démonstration | Les critères de la section 3 |

Chaque vendredi, trente minutes : ce qui a marché, ce qui a coincé, une consigne à ajouter ou à retirer du `CLAUDE.md`.

## 6. Relais

- Un relais interne par équipe, qui reçoit les questions et propose les changements de configuration.
- Le `CLAUDE.md` et les règles sont l'infrastructure du déploiement : une consigne qui n'est que dans la tête de Yao, ou dans son dossier personnel, n'existe pas pour l'équipe.

## 7. Démonstration du 30e jour et passation

- Démonstration à la DSI : une évolution réelle, de la note de l'actuariat à la recette, avec ses tests ; les chiffres contre la situation de départ.
- Passation : la configuration, le plan de relais et la note de passation (chapitre 17).

## 8. Échecs à éviter

- Des consignes gardées dans des fichiers personnels.
- Un `CLAUDE.md` si long qu'il n'est plus suivi.
- Une démonstration sans situation de départ : un gain qu'on ne peut pas chiffrer.
- Des droits trop larges dès le premier jour.
