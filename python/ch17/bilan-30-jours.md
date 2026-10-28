# Bilan de l'activation Claude Code de 30 jours — équipe applications de la DSI de Kanvô Assurances

*Exemple fictif : Kanvô Assurances, son équipe et son logiciel des contrats sont inventés pour le livre. Les valeurs entre crochets se mesurent sur la mission, de la même façon qu'au premier jour (`ch15/plan-activation.md`) : ce bilan ne les invente pas. Les autres chiffres viennent des séances mesurées des chapitres 15 à 17, le 27 et le 28 octobre 2026, avec Claude Haiku 5.5 sauf mention contraire.*

## 1. Les critères de réussite, contre la situation de départ

| Critère (fixé avec M. Ahouansou) | Semaine 0 | Jour 30 | Atteint ? |
|---|---|---|---|
| Délai entre une note de l'actuariat et sa mise en production | [à mesurer] | [à mesurer] | [à juger] |
| Anomalies de montant trouvées en recette, sur les évolutions faites avec Claude Code | [à mesurer] | [à mesurer] | [à juger] |
| Évolutions livrées avec leurs tests | 0 % du code couvert | [à mesurer] | [à juger] |
| Dépense sous le plafond du pilote | Plafond : [montant fixé par la DSI] | [à relever dans la Console] | [à juger] |
| Prise en main d'un nouveau développeur | [à demander au dernier arrivé] | [à demander à Mme Adanlé] | [à juger] |

## 2. Ce que l'activation a mis en place, et ce qu'on en a mesuré

| En place | Mesuré dans le livre |
|---|---|
| La configuration d'équipe dans le dépôt (chapitre 15) | Sur le poste de la nouvelle développeuse : prime arrondie au franc 0 fois sur 5 avec les consignes dans le dossier personnel de Yao, 5 fois sur 5 avec les consignes dans le dépôt |
| La carte du logiciel (chapitre 16) | Huit faits sur huit dans chaque carte ; reprise après un changement : 0 réponse juste sur 4 sans avertissement, 4 sur 4 en signalant le fichier modifié |
| La méthode pour les défauts (chapitre 16) | Ticket DSI-2026-031 : 0 séance conforme sur 8 avec une phrase, 9 sur 9 avec trois exemples ou des tests |
| Les évolutions, directes ou en mode plan (chapitre 16) | Branche moto : 8 contrôles sur 8 dans les 7 séances |
| La revue de chaque demande de fusion (chapitre 17) | Critères, version 2 : 5,6 défauts sur six en moyenne, aucun constat sur une demande sans défaut ; relance avec les constats précédents : aucun doublon |

## 3. Ce que l'activation a coûté

- Les séances de mesure des chapitres 15 à 17 : 1,48 $, avec Claude Haiku 5.5 et quelques séances de Claude Sonnet 5.5 au chapitre 15.
- Une revue de demande de fusion : environ 0,006 $ ; une évolution en exécution directe : environ 0,014 $.
- L'usage réel de l'équipe pendant les 30 jours : [à relever sur l'espace de travail Claude Code de la Console].
- Le temps de Yao et du relais : [à relever].

## 4. Les échecs évités, avec leur preuve

| Échec | Ce qui l'a montré | Ce qui l'évite |
|---|---|---|
| Une convention qui n'arrive pas au nouveau venu | Chapitre 15 : 0 fois sur 5 | Le `CLAUDE.md` et les règles du dépôt |
| Une règle de répartition comprise de travers | Chapitre 16 : 0 conforme sur 8 avec une phrase | Des exemples exacts, ou les tests d'abord |
| Une séance reprise qui croit son passé | Chapitre 16 : 0 réponse juste sur 4 | Signaler les fichiers modifiés, ou repartir de la carte |
| Un plan approuvé avec ses questions ouvertes | Chapitre 16 : un plan a appliqué sa propre recommandation | Répondre aux questions avant d'approuver |
| Une revue qui crie au loup | Chapitre 17 : 4,3 constats sur une demande sans défaut avec une consigne vague | Des critères, corrigés d'après les `detected_pattern` |
| Des commentaires répétés à chaque commit | Chapitre 17 : 11 doublons sur trois relances | Les constats précédents dans la relance |

## 5. La suite

- Étendre la cohorte à toute l'équipe applications : [date, décidée avec la DSI].
- Le chantier des tests continue, d'après son manifeste (`ch16/manifeste-tests.json`).
- La revue de fond, la nuit, par la Message Batches API : [à décider].
