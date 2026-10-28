# Dossier de preuves — Yao, Nokoué Conseil

*Exemple fictif : Yao, Nokoué Conseil, Kanvô Assurances et les Cliniques Ébène sont inventés pour le livre. Les mesures, elles, sont réelles : elles ont été faites avec Claude, sur des données fabriquées, du 26 au 28 octobre 2026, et chacune renvoie au chapitre et au code qui la refont. Un vrai dossier dit la même chose en première ligne : ce qui est réel, ce qui est anonymisé, ce que le client a autorisé à montrer.*

## En une phrase

Deux missions conduites de la découverte à la passation : l'automatisation des sinistres d'un assureur, puis le compte rendu assisté d'un groupe de cliniques dans trois pays, chacune mesurée à chaque décision.

## Six pièces

| Pièce | Le problème | Ce que j'ai décidé | Ce que j'ai mesuré | Où la voir |
|---|---|---|---|---|
| L'extraction des documents de sinistre | Des factures et des constats ressaisis à la main | Un schéma strict, des contrôles par le code, une relance, un gestionnaire pour le reste | 100 % de champs justes et aucune invention sur 72 extractions, contre 94 % et quatre inventions avec le schéma naïf ; 0,0003 $ par document | Chapitre 12 |
| L'assistant documentaire | Des gestionnaires qui cherchent la règle dans des centaines de pages | Une recherche par mots filtrée par le produit et la date, un reclassement par Claude, la réponse avec ses sources, « je ne trouve pas » quand c'est vrai | 38 réponses justes sur 40, et « je ne trouve pas » aux quatre questions sans réponse ; 0,0011 $ et 4,6 s par question | Chapitre 14 |
| La revue des demandes de fusion | Une revue qui criait au loup | Des critères corrigés d'après les constats rejetés ; les constats précédents à chaque relance | 5,6 défauts sur six en moyenne, aucun constat sur la demande sans défaut ; aucun doublon sur trois relances, contre onze | Chapitre 17 |
| Le banc avec les médecins | Savoir si un brouillon est fidèle, sans relire chaque compte rendu | Un juge étalonné sur les annotations des médecins, une barrière à chaque changement | Le juge d'accord avec les annotations sur 90 jugements sur 90 ; la version en place refusée par la barrière (13,3 % à corriger), la nouvelle acceptée (5 %) | Chapitre 19 |
| La pile de sûreté | Des pièces jointes venues d'ailleurs, et deux outils dangereux | Filtres, autorisation des outils par le code, échec fermé, un battement par couche | 14 pièces piégées sur 16 mises de côté, aucun brouillon contaminé, aucune pièce saine écartée ; un filtre coupé vu dès la première requête | Chapitre 20 |
| L'exploitation sur trois cliniques | Un « c'est lent » sans tableau de bord | Le temps découpé, des seuils tirés d'une journée ordinaire, disjoncteur, repli, file | Un lundi, une cause locale séparée d'une traîne de l'API ; une panne simulée sans note perdue ; le remplaçant du modèle passé au banc avant le préavis | Chapitre 22 |

## Ce que je sais faire, d'après ces pièces

- Faire parler un client de son besoin, et écrire ce qui a été décidé, avec ses raisons et son retour arrière.
- Choisir l'architecture la plus simple qui tienne, et la mesurer avant de la défendre.
- Construire en Python, dans les systèmes du client ; le même travail existe en TypeScript dans le dépôt du Tome 2.
- Évaluer avec les experts du métier, et ne pas faire dire à un essai plus que ses chiffres.
- Exploiter, et transmettre : la passation de la mission 2 est vérifiée par un script.

## Ce qui n'est pas dans ce dossier

- Les données des clients, leurs prompts complets et leurs résultats bruts.
- Les chiffres du pilote du chapitre 23 : ils sont fabriqués pour le livre. Dans un vrai dossier, le bilan de votre pilote prend leur place.
