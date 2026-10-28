# Dossier de découverte et d'architecture — mission 2, Cliniques Ébène

*Exemple fictif : les Cliniques Ébène, leurs médecins, leurs patients et leurs volumes sont inventés pour le livre. Les valeurs entre crochets se mesurent sur la mission. Version 1, puis version 2 après le contradicteur (section 9), avant le comité d'éthique.*

## 1. La demande

La direction médicale des Cliniques Ébène (Cotonou, Abidjan, Dakar) veut rendre leurs soirées aux médecins. Après la consultation, chacun réécrit ses notes en compte rendu pour le dossier du patient, et pour les hôpitaux français partenaires quand un avis à distance est demandé.

- Volume : [comptes rendus par mois, par clinique].
- Temps passé par compte rendu aujourd'hui : [à mesurer sur deux semaines, avec les médecins volontaires].
- Ce qui compte pour la direction : le temps rendu, sans baisse de qualité du dossier.

## 2. Les interlocuteurs

| Interlocuteur | Ce qu'il attend | Ce qu'il craint |
|---|---|---|
| Direction médicale | Du temps rendu aux médecins, des dossiers complets | Une baisse de qualité, une plainte |
| Médecins | Un brouillon juste, à corriger vite | Un outil qui écrit à leur place ce qu'ils n'ont pas dit ; leur responsabilité engagée |
| DSI | Une intégration au logiciel du dossier patient, un coût prévisible | Un service de plus à exploiter, des données qui sortent |
| Délégué à la protection des données | Des données de santé traitées selon les lois des trois pays, et pour les partenaires français, le RGPD | Des données conservées ou traitées hors de ce qui est autorisé |
| Comité d'éthique | Un usage qui sert le patient | [à recueillir en séance] |

## 3. Ce qu'on reprend de la mission 1

| Élément de la mission 1 | Décision | Pourquoi |
|---|---|---|
| Bibliothèque de prompts versionnés (chapitre 11) | Repris | Les prompts du compte rendu se versionnent et se testent de la même façon |
| Chaîne d'extraction à outil strict (chapitre 12) | Repris, avec des contrôles propres à la santé | Mesurée sur 30 comptes rendus fabriqués : aucune conclusion inventée, aucune réserve du médecin perdue, aucun examen ajouté |
| Traitement par lots (chapitre 13) | Écarté | Le traitement par lots n'est pas éligible à la non-conservation des données |
| Assistant des conditions générales (chapitre 14) | Adapté | Un assistant sur les règles de rédaction des cliniques ; jamais sur des protocoles de soins |
| Configuration Claude Code de l'équipe (chapitre 15) | Repris | Pour l'équipe de la DSI qui intègre le service |
| Revue automatique (chapitre 17) | Reprise | Pour le code de l'intégration |

Remonté au produit de Nokoué Conseil : le schéma « outil strict, contrôles par le code, brouillon validé par un humain », et le banc des contrôles de fidélité.

## 4. L'architecture

Un **workflow fixe**, pas un agent : aucune étape n'a besoin de décider seule de la suivante.

1. Le médecin dicte ou tape ses notes, comme aujourd'hui.
2. Claude rédige un brouillon de compte rendu, par l'outil strict `rediger_compte_rendu` (`ch18/compte_rendu.py`).
3. Le code contrôle le brouillon : pas de conclusion là où le médecin n'en a pas écrit, ses réserves gardées, aucun examen ni soin ajouté.
4. Le médecin relit, corrige et valide. Rien n'entre au dossier sans sa validation.
5. Les corrections des médecins nourrissent le banc d'évaluation (chapitre 19).

Coût estimé : environ 0,0004 $ par compte rendu avec Claude Haiku 5.5, mesuré sur les notes fabriquées ; [coût mensuel, sur le volume mesuré].

## 5. Ce qu'on refuse de construire

- Le diagnostic automatique, la suggestion de traitement, le tri des patients.
- Une conclusion écrite là où le médecin n'a pas conclu.
- Un envoi aux partenaires sans la validation du médecin.

Ce refus se dit à la direction avec ses raisons : la responsabilité médicale reste au médecin, et un outil qui conclut à sa place serait un dispositif d'une autre nature, avec d'autres obligations.

## 6. Ce que la gouvernance écarte

- **La conservation des données** : la non-conservation (ZDR) se demande à Anthropic, par organisation. Elle exclut le traitement par lots et la Files API, et les modèles qui exigent 30 jours de conservation (Claude Fable 5.1, Mythos 5.1, Fable 5, Mythos 5).
- **Le lieu de l'inférence** : sur l'API, `inference_geo` vaut `global` ou `us`. Si le délégué exige un traitement en Europe pour les données envoyées aux partenaires français, la route change (chapitre 4 : Bedrock et ses profils EU).
- **La route** : à décider avec le délégué à la protection des données et la DSI, au chapitre 21.

## 7. Risques et retour arrière

| Risque | Parade |
|---|---|
| Une conclusion inventée, une réserve perdue | Les contrôles par le code ; la validation par le médecin |
| Une panne du service | Le médecin écrit seul, comme aujourd'hui |
| Une dépense qui dérape | Le plafond de l'espace de travail |

**Retour arrière :** le service se coupe par clinique ; les médecins gardent leur façon de faire.

## 8. Questions ouvertes

- La route et le lieu de l'inférence, avec le délégué à la protection des données.
- [Les questions du comité d'éthique.]

## 9. Version 2, après le contradicteur

Trois relectures du dossier par un contradicteur (`ch18/contradicteur.py`) ont posé, chaque fois, des questions que la version 1 ne traitait pas, ou mal. Chacune a désormais sa place dans la mission :

| Question | Où la mission y répond |
|---|---|
| Les patients sont-ils informés, et peuvent-ils s'y opposer ? Sur quelle base légale, dans chaque pays et pour les partenaires français ? | Le registre des risques et le texte au patient (chapitre 21), avant le pilote |
| L'outil a-t-il été essayé sur les accents, les mots des langues locales, les noms et les abréviations de chaque clinique ? | Un jeu d'évaluation de notes réelles, annotées par les médecins (chapitre 19) ; les écarts entre groupes mesurés (chapitre 21) |
| Comment sait-on que le médecin relit vraiment ? | Le taux de brouillons validés sans correction et le temps de relecture, suivis dès le premier jour du pilote (chapitre 19) |
| Les corrections des médecins sont-elles anonymisées avant le banc ? | Avant leur entrée au banc, avec un accès limité par rôle (chapitre 20) |

Mesures ajoutées depuis la version 1 : avec Claude Sonnet 5.5, l'outil imposé de la chaîne est refusé (`tool_choice` en `auto`, avec l'outil strict) ; sur vingt comptes rendus, aucun défaut, pour environ dix-huit fois le prix de Claude Haiku 5.5. Un brouillon a déplacé une réserve du médecin en décision de suivi sans qu'aucun contrôle le voie : la validation du médecin reste l'étape qui protège.
