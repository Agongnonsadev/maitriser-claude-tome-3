# Les missions de Yao — code d'accompagnement du Tome 3

Code des exemples de *Maîtriser Claude, Tome 3 — Déployer l'IA en entreprise avec Claude* (Botlyx Academy). Yao, Nokoué Conseil, Kanvô Assurances et les Cliniques Ébène sont fictifs, comme toutes les données de ce dépôt : contrats, déclarations, constats, comptes rendus et protocoles sont fabriqués pour le livre.

C'est le dépôt d'accompagnement du livre. Son adresse est donnée sur la page d'accompagnement, academy.botlyx.com/livres/tome-3, avec les mises à jour du livre.

Le code est publié sous licence MIT (fichier `LICENSE`) : vous pouvez le reprendre dans vos projets, même commerciaux, en gardant la mention de copyright. Le texte du livre n'est pas concerné.

## Organisation

```
python/
├── assureur/   ← mission 1, Kanvô Assurances : réglages, coûts, journal des appels,
│                 système de gestion simulé (systeme.py, donnees/), outils de l'agent, prompts/
├── cliniques/  ← mission 2, Cliniques Ébène : notes de consultation fabriquées (notes.py), sans traitement ni
│                 posologie, et ce qu'on sait de chacune
├── ch02/       ← chiffrer un cas d'usage avant de concevoir (kanvo.json, chiffrer.py, resultats/)
├── ch03/       ← le banc de décision : modèle et réflexion de chaque étape (cas.json, banc.py, resultats/)
├── ch05/       ← l'agent des sinistres v1 : la boucle à la main, l'Agent SDK, les bifurcations
├── ch06/       ← le catalogue d'outils : celui de la DSI, celui de Yao (assureur/outils_v2.py), leurs mesures
├── ch07/       ← le serveur MCP (assureur/serveur_mcp.py) : jetons, dépôt fictif de la DSI et son .mcp.json, mesures
├── ch08/       ← l'agent des sinistres v2 : outils v3 (assureur/outils_v3.py), la garde (regles.py), scénarios
├── ch09/       ← le système d'études de la souscription : coordinateur, quatre sous-agents (sous_agents.py),
│                 suivi et bornes (suivi.py), prompts/, questions ; documents dans assureur/donnees/souscription/
├── ch10/       ← les pannes et la provenance (etudes_v2.py, sous_agents_v2.py, un 7e document dans documents/),
│                 et l'agent des sinistres sur 40 tours (conversation.py, conversation.json)
├── ch11/       ← le tri des déclarations : quatre versions du prompt (bibliothèque de assureur/prompts/,
│                 registre bibliotheque.json et modules/, code assureur/bibliotheque.py), 32 déclarations
├── ch12/       ← l'extraction des documents de sinistre : 36 documents fabriqués (fabriquer.py, documents/,
│                 verite.json), outils et schémas (schemas.py), contrôle, relance et notation (extraire.py)
├── ch13/       ← l'archive des constats : 1 100 constats fabriqués en mémoire (archive.py), extraction et
│                 correction des plaques (extraction.py), échantillon (echantillon.py), lots, suivi et renvoi
│                 (lot.py), relecture (relecture.py), calibrage et surveillance (calibrage.py)
├── ch14/       ← l'assistant documentaire : documents fictifs (documents/, l'édition 2027 par edition_2027.py),
│                 découpages et manifeste (corpus.py), recherche (recherche.py), questions.json, mesure du
│                 rappel (mesurer_recherche.py), assistant (assistant.py), index périmé (panne.py)
├── ancien_logiciel/ ← le logiciel des contrats de la DSI de Kanvô (partie 5) : écrit pour le livre, « à l'ancienne »,
│                 sans tests ; un modèle à ne pas suivre, que les chapitres 15 à 17 configurent, testent et relisent
├── ch15/       ← Claude Code pour une équipe : configurations (configuration/ : le CLAUDE.md personnel de Yao,
│                 celui du dépôt, puis la configuration d'équipe avec règles, Skill et permissions), séances mesurées
│                 (seances.py), hook InstructionsLoaded (noter_instructions.py), plan d'activation de 30 jours
├── ch16/       ← l'ancien logiciel, compris puis modifié : séances mesurées (seances.py : la carte, les appelants,
│                 la reprise, le ticket DSI-2026-031, la branche moto), contrôles cachés (controles.py), données
│                 fictives (donnees/), solutions de référence (reference/), manifeste du chantier des tests
├── ch17/       ← la revue des demandes de fusion en mode non interactif (revue.py), deux demandes fictives
│                 (demandes/), leurs défauts posés (defauts.json, jamais montré à Claude)
├── ch18/       ← mission 2 : la chaîne de la mission 1 reprise pour les comptes rendus (compte_rendu.py),
│                 le dossier de découverte et d'architecture (dossier-mission-2.md), son contradicteur
├── ch19/       ← le banc d'évaluation des comptes rendus (banc.py : étalonner le juge, essai A/B, barrière),
│                 l'hypothèse écrite avant l'essai (hypothese.md) ; jeu d'étalonnage dans cliniques/etalonnage.py
├── ch20/       ← la pile de sûreté de l'assistant (pile.py : filtres, autorisation des outils, échec fermé,
│                 battements) ; dossiers et pièces jointes piégées dans cliniques/dossiers.py
├── ch21/       ← la conformité : registre des risques, texte au patient, mesure des écarts entre groupes
│                 de notes (biais.py, sans appel)
├── ch22/       ← l'exploitation sur trois cliniques (exploitation.py : temps découpé, disjoncteur, repli,
│                 file, tableau de bord) ; la répétition de la migration au banc du chapitre 19 (migration.py)
├── ch23/       ← le pilote de six semaines, fabriqué pour le livre, et son bilan (pilote.py : témoins,
│                 différence des différences, déclencheurs de revue, retour sur investissement ; sans appel)
├── ch24/       ← la passation aux Cliniques Ébène (document-de-passation.md) et son vérificateur
│                 (verifier_passation.py) ; le dossier de preuves de Yao (dossier-de-preuves-yao.md)
└── tests/      ← un fichier par chapitre ; aucun test n'appelle l'API
```

Chaque appel à l'API est noté dans `journal/appels.jsonl` (identifiant de requête, modèle, tokens, coût), jamais le contenu des messages. Une séance de l'Agent SDK y tient une ligne, avec son identifiant de séance : le SDK ne donne pas celui de chaque requête. Au chapitre 9, une séance dont un sous-agent tourne en arrière-plan en tient deux, au coût cumulé : pour le total d'une séance, ne gardez que sa dernière ligne. Ce dossier est exclu de Git.

Au chapitre 9, le chercheur web interroge le vrai web : ses résultats changent d'un jour à l'autre, et les fichiers de `ch09/resultats/` contiennent les adresses et de courts extraits des pages qu'il a trouvées. Ces pages ne sont ni vérifiées ni reprises par le livre.

## Installer

Python 3.10 ou plus récent. Depuis le dossier `python/` :

```bash
python -m venv .venv
source .venv/bin/activate        # sous Windows : .venv\Scripts\Activate.ps1
pip install -e ".[tests]"
pip install -e ".[agents]"       # à partir du chapitre 5 : le Claude Agent SDK
pip install -e ".[serveur]"      # chapitre 7 : le SDK MCP (déjà installé avec le précédent)
python -m pytest                 # gratuit : aucun test n'appelle l'API
```

Le Claude Agent SDK embarque le binaire de Claude Code : rien d'autre à installer. Ses tests sautent s'il est absent.

La clé d'API se lit dans la variable d'environnement `ANTHROPIC_API_KEY`, jamais dans un fichier du dépôt. Fixez une limite de dépense mensuelle sur votre compte avant le premier script payant.

## Lancer les exemples

| Chapitre | Commande | Coût |
|---|---|---|
| 2 | `python -m ch02.chiffrer ch02/kanvo.json` | Gratuit : comptage des tokens |
| 2 | `python -m ch02.chiffrer ch02/kanvo.json --mesurer --budget-max 0.20` | 0,0492 $ mesurés le 26 octobre 2026 (14 appels), plus 0,0214 $ pour remesurer les constats avec `--cas constats` |
| 3 | `python -m ch03.banc --estimer` | Gratuit : coût maximal du banc |
| 3 | `python -m ch03.banc --repetitions 2 --budget-max 0.40` | 0,2698 $ mesurés le 26 octobre 2026 (96 appels) |
| 5 | `python -m ch05.boucle --estimer` | Gratuit : coût maximal du premier tour |
| 5 | `python -m ch05.boucle --repetitions 2 --budget-max 0.20` | 0,0115 $ mesurés le 27 octobre 2026 (20 conduites, 30 appels) |
| 5 | `python -m ch05.boucle --reglage sans-reflexion --repetitions 2 --budget-max 0.05` | 0,0086 $ mesurés le 27 octobre 2026 (29 appels) |
| 5 | `python -m ch05.agent_sdk --repetitions 2 --budget-max 0.10` | 0,0086 $ mesurés le 27 octobre 2026 (20 séances) |
| 5 | `python -m ch05.bifurquer --budget-max 0.10` | 0,0025 $ mesurés le 27 octobre 2026 (un tronc, six branches) |
| 6 | `python -m ch06.choix --estimer` | Gratuit : coût maximal du premier tour |
| 6 | `python -m ch06.choix --variantes dsi yao --repetitions 3 --budget-max 0.30` | 0,0954 $ mesurés le 27 octobre 2026 (120 conduites) |
| 6 | `python -m ch06.choix --variantes yao-consigne-contrat --repetitions 3 --budget-max 0.15` | 0,0653 $ mesurés le 27 octobre 2026 (60 conduites) |
| 6 | `python -m ch06.erreurs --variantes dsi yao --repetitions 3 --budget-max 0.10` | 0,0186 $ mesurés le 27 octobre 2026 (24 conduites) |
| 6 | `python -m ch06.erreurs --variantes yao-motif-strict --situations e4-validation --repetitions 3 --budget-max 0.03` | 0,0042 $ mesurés le 27 octobre 2026 (3 conduites) |
| 6 | `python -m ch06.choix --variantes yao --sdk --repetitions 1 --budget-max 0.05` | 0,0090 $ mesurés le 27 octobre 2026 (20 séances) |
| 7 | `python -m ch07.creer_jetons` | Gratuit : vos jetons et le registre des empreintes, dans `~/.kanvo/` |
| 7 | `python -m assureur.serveur_mcp` | Gratuit : le serveur seul, en stdio (il attend `KANVO_JETON` et `KANVO_JETONS`) |
| 7 | `python -m ch07.agent_mcp --budget-max 0.05` | 0,0089 $ mesurés le 27 octobre 2026 (20 séances) |
| 7 | `python -m ch07.poste_dsi --repetitions 2 --budget-max 0.20` | 0,0220 $ mesurés le 27 octobre 2026 (24 séances) |
| 8 | `python -m ch08.agent_v2 --repetitions 3 --budget-max 0.15` | 0,0393 $ mesurés le 27 octobre 2026 (48 séances) |
| 8 | `python -m ch08.agent_v2 --fichier scenarios_stress.json --sans-reflexion --repetitions 3 --budget-max 0.06` | 0,0301 $ mesurés le 27 octobre 2026 (24 séances) |
| 8 | `python -m ch08.agent_v2 --prompt v1 --scenarios s2-au-dela-du-plafond s4-montant-gonfle s8-date-fausse s3-un-proche --repetitions 3` | 0,0214 $ mesurés le 27 octobre 2026 (24 séances) |
| 8 | `python -m ch08.agent_v2 --exercice --scenarios s2-au-dela-du-plafond --repetitions 3` | 0,0082 $ mesurés le 27 octobre 2026 (6 séances) |
| 8 | `python -m ch08.agent_v2 --variantes garde --plafond-garde 50000 --scenarios s1-dans-le-plafond --repetitions 3` | 0,0041 $ mesurés le 27 octobre 2026 (3 séances) |
| 9 | `python -m ch09.budget_visible` | 0,0004 $ mesurés le 27 octobre 2026 (2 séances sans outil) |
| 9 | `python -m ch09.etudes --questions q1-inondation --repetitions 3 --budget-max 0.60 --budget-etude 0.30` | 0,09 à 0,10 $ par étude complète, mesurés le 27 octobre 2026 ; la moitié en recherches web |
| 9 | `python -m ch09.etudes --questions q1-inondation --variantes objectifs procedure sequentiel --repetitions 3 --budget-max 1.00 --budget-etude 0.30` | 0,7828 $ mesurés le 27 octobre 2026 (9 études) |
| 9 | `python -m ch09.etudes --questions q2-motos q3-travaux --variantes objectifs procedure --repetitions 3 --budget-max 0.60 --budget-etude 0.30` | 0,5965 $ mesurés le 27 octobre 2026 (12 études) |
| 9 | `python -m ch09.hors_role --repetitions 3 --budget-max 0.15` | 0,0885 $ mesurés le 27 octobre 2026 (9 séances, trois variantes) ; il rejoue une demande prise dans `ch09/resultats/` |
| 9 | `python -m ch09.etudes --questions q1-inondation --repetitions 2 --max-sous-agents 1` puis `--budget-etude 0.02` | 0,0501 $ mesurés le 27 octobre 2026 (4 études) |
| 10 | `python -m ch10.etudes_v2 --variantes v1 --scenarios normal panne-persistante web-indisponible --repetitions 2 --budget-max 0.60` | 0,4032 $ mesurés le 27 octobre 2026 (6 études) |
| 10 | `python -m ch10.etudes_v2 --variantes v2 --repetitions 2 --budget-max 1.00` | 0,6251 $ mesurés le 27 octobre 2026 (10 études, cinq scénarios) |
| 10 | `python -m ch10.conversation --repetitions 2 --budget-max 0.40` | 0,1255 $ mesurés le 27 octobre 2026 (6 conversations de 40 tours, 2 séances neuves) |
| 10 | `python -m ch10.etudes_v2 --reevaluer <fichier>`, `python -m ch10.conversation --reevaluer <fichier>` | Gratuit : recompte un fichier de résultats avec les motifs actuels |
| 11 | `python -m ch11.tri --estimer` | Gratuit : coût maximal, par le comptage des tokens |
| 11 | `python -m ch11.tri --modeles claude-haiku-5-5 --versions 1 2 3 4 --repetitions 3 --budget-max 0.20` | 0,0335 $ mesurés le 27 octobre 2026 (384 tris) |
| 11 | `python -m ch11.tri --modeles claude-sonnet-5-5 --versions 1 3 4 --repetitions 2 --budget-max 1.00` | 0,3924 $ mesurés le 27 octobre 2026 (192 tris) |
| 12 | `python -m ch12.fabriquer` | Gratuit : réécrit les 36 documents et leur vérité, à l'identique |
| 12 | `python -m ch12.extraire --variantes naif soigne exemples exiger --repetitions 2 --budget-max 0.50` | 0,0837 $ mesurés le 27 octobre 2026 (288 extractions et leurs relances) |
| 12 | `python -m ch12.extraire --variantes sans-autre --documents autre-01 autre-02 --repetitions 3` | 0,0023 $ mesurés le 27 octobre 2026 (6 extractions) |
| 12 | `python -m ch12.extraire --reevaluer <fichier>` | Gratuit : renote un fichier de résultats avec le contrôle et la notation actuels |
| 13 | `python -m ch13.archive` | Gratuit : fabrique l'archive en mémoire et affiche ses difficultés |
| 13 | `python -m ch13.echantillon --versions v1 v2 --budget-max 0.10` | 0,0787 $ mesurés le 27 octobre 2026 (140 extractions synchrones) ; v3 : 0,0410 $ ; v4, cache sur le préfixe : 0,0163 $ |
| 13 | `python -m ch13.echantillon --reevaluer <fichier>` | Gratuit : renote un fichier, sortie brute et après correction des plaques |
| 13 | `python -m ch13.lot envoyer --version v3 --cache automatique --budget-max 0.60` | 0,3211 $ mesurés le 27 octobre 2026 (1 100 constats en lot ; le cache n'est presque jamais lu) |
| 13 | `python -m ch13.lot envoyer --version v3 --cache prefixe --prechauffer --budget-max 0.60` | 0,1283 $ mesurés le 27 octobre 2026, préchauffage compris (1 100 constats en lot) |
| 13 | `python -m ch13.lot suivre <état> --attendre` | Gratuit : interroge le lot, puis télécharge, corrige, contrôle et note les résultats |
| 13 | `python -m ch13.lot renvoyer <état> --budget-max 0.01` | 0,0004 $ mesurés le 27 octobre 2026 (3 échecs renvoyés) |
| 13 | `python -m ch13.lot envoyer --version v4 --motif "(?<!\d)\d\d-\d\d-\d\d(?!\d)" --prechauffer --budget-max 0.12` | 0,0262 $ mesurés le 27 octobre 2026, préchauffage compris (219 constats) |
| 13 | `python -m ch13.lot envoyer --version v3 --echantillon --modele claude-sonnet-5-5 --cache automatique --budget-max 0.70` | 0,3651 $ mesurés le 27 octobre 2026 (lot non fini à 51 minutes, annulé : 63 réussies facturées, 7 annulées) |
| 13 | `python -m ch13.echantillon --versions v3 --modele claude-sonnet-5-5 --budget-max 0.90` | 0,4169 $ mesurés le 27 octobre 2026 (70 extractions synchrones sur Sonnet 5.5) |
| 13 | `python -m ch13.relecture <échantillon v1-v2> --repetitions 2 --budget-max 0.23` | 0,1469 $ mesurés le 27 octobre 2026 (280 relectures, consigne finale) |
| 13 | `python -m ch13.calibrage <lot> [<renvoi> <segment>]` | Gratuit : tableau de calibrage, seuils, file de relecture, surveillance par forme de date |
| 14 | `python -m ch14.edition_2027` | Gratuit : réécrit l'édition 2027 des conditions et du tableau automobiles, à l'identique |
| 14 | `python -m ch14.corpus` | Gratuit : les documents, leurs périodes, et le nombre de morceaux de chaque découpage |
| 14 | `python -m ch14.mesurer_recherche --strategies bm25 filtre` | Gratuit : le rappel à 1, 3 et 5 des deux découpages |
| 14 | `python -m ch14.mesurer_recherche --strategies reecriture reclassement --decoupages structure --budget-max 0.10` | 0,0338 $ mesurés le 27 octobre 2026 (80 recherches) |
| 14 | `python -m ch14.assistant --decoupages naif structure --strategie filtre --k 5 --budget-max 0.10` | 0,0320 $ mesurés le 27 octobre 2026 (80 réponses) |
| 14 | `python -m ch14.assistant --strategie filtre --k 3 5 10 20 --budget-max 0.15` | 0,0658 $ mesurés le 27 octobre 2026 (160 réponses) |
| 14 | `python -m ch14.assistant --strategie reclassement --k 3 5 --budget-max 0.15` | 0,0822 $ mesurés le 27 octobre 2026 (80 réponses) |
| 14 | `python -m ch14.assistant --jeu etat --strategie filtre --k 5 --systeme sans avec --repetitions 2 --budget-max 0.05` | 0,0072 $ mesurés le 27 octobre 2026 (16 réponses) |
| 14 | `python -m ch14.panne --repetitions 2 --budget-max 0.06` | 0,0281 $ mesurés le 27 octobre 2026 (80 réponses, cinq états de la base ; une première série, avant le retrait des dates de la requête, 0,0283 $) |
| 14 | `python -m ch14.assistant --reevaluer <fichier>`, `python -m ch14.panne --reevaluer <fichier>`, `python -m ch14.mesurer_recherche --reevaluer <fichier>` | Gratuit : renote un fichier de résultats avec les questions et la notation actuelles |
| 15 | `cd ancien_logiciel && python lancer.py creer-base` | Gratuit : l'ancien logiciel des contrats, sur une base de recette vide |
| 15 | `python -m ch15.seances --variantes personnel nouveau projet regles --taches majoration --repetitions 5 --budget-max 0.40` | 0,0982 $ mesurés le 27 octobre 2026 (20 séances de Claude Code, Claude Haiku 5.5) |
| 15 | `python -m ch15.seances --variantes regles --taches resilies arrondis --repetitions 3 --budget-max 0.15` | 0,0232 $ mesurés le 27 octobre 2026 (6 séances : le rapport et la Skill d'équipe) |
| 15 | `python -m ch15.seances --modele claude-sonnet-5-5 --variantes nouveau regles --taches majoration --repetitions 3 --budget-max 0.80` | 0,2944 $ mesurés le 27 octobre 2026 (Claude Sonnet 5.5) |
| 15 | `python -m ch15.seances --reevaluer <fichier>` | Gratuit : relit un fichier de résultats, sans rien relancer |
| 16 | `python -m ch16.seances --taches carte appelants --repetitions 3 --budget-max 0.40` | 0,2268 $ mesurés le 28 octobre 2026, avec une séance d'essai de la carte (10 séances de Claude Code, Claude Haiku 5.5) |
| 16 | `python -m ch16.seances --taches reprise --repetitions 3 --budget-max 0.20` | 0,1516 $ mesurés le 28 octobre 2026, avec un essai (2 cartes, 12 reprises) |
| 16 | `python -m ch16.seances --taches defaut --repetitions 4 --budget-max 0.30` | 0,0812 $ mesurés le 28 octobre 2026, avec un essai (17 séances) |
| 16 | `python -m ch16.seances --taches evolution --repetitions 3 --budget-max 0.40` | 0,2345 $ mesurés le 28 octobre 2026, avec un essai (7 séances) |
| 16 | `python -m ch16.seances --reevaluer <fichier>` | Gratuit : relit un fichier de résultats, sans rien relancer |
| 17 | `python -m ch17.revue --mesures criteres passes relance autorevue --repetitions 3 --budget-max 1.00` | 0,3734 $ mesurés le 28 octobre 2026, avec une revue d'essai (50 revues, 68 appels de `claude -p`, Claude Haiku 5.5) |
| 17 | `python -m ch17.revue --reevaluer <fichier>` | Gratuit : relit un fichier de résultats et rapproche de nouveau les constats des défauts |
| 18 | `python -m ch18.compte_rendu --estimer --modeles claude-haiku-5-5 claude-sonnet-5-5 --repetitions 3` | Gratuit : le coût maximal |
| 18 | `python -m ch18.compte_rendu --modeles claude-haiku-5-5 --repetitions 3 --budget-max 0.10` | 0,0207 $ mesurés le 28 octobre 2026 (60 comptes rendus) |
| 18 | `python -m ch18.compte_rendu --modeles claude-sonnet-5-5 --repetitions 1 --budget-max 0.20` | 0,1249 $ mesurés le 28 octobre 2026 (20 comptes rendus, outil strict en `auto`) |
| 18 | `python -m ch18.contradicteur --tirages 3 --budget-max 0.15` | 0,1159 $ mesurés le 28 octobre 2026 (Claude Sonnet 5.5, sorties structurées) |
| 19 | `python -m ch19.banc etalonner --juges v1 v2 --repetitions 2 --budget-max 0.15` | 0,0417 $ mesurés le 28 octobre 2026 sur le jeu complet, avec `--sans-entete` (180 jugements) ; 0,0269 $ pour le jeu facile, avant les cas difficiles |
| 19 | `python -m ch19.banc etalonner --juges v2 --repetitions 2 --budget-max 0.08` | 0,0236 $ mesurés le 28 octobre 2026 (90 jugements, juge avec l'en-tête du rédacteur) |
| 19 | `python -m ch19.banc ab --juge v2 --repetitions 3 --budget-max 0.30` | 0,0817 $ mesurés le 28 octobre 2026, avec `--sans-entete` (120 comptes rendus rédigés et jugés) |
| 19 | `python -m ch19.banc rejuger <essai> --juge v2 --budget-max 0.10` | 0,0381 $ mesurés le 28 octobre 2026 (les 120 comptes rendus jugés de nouveau) |
| 19 | `python -m ch19.banc barriere <essai> --bras B --seuil 0.10` | Gratuit : code de sortie 1 si la version franchit le seuil |
| 20 | `python -m ch20.pile --configurations modele_seul pile pile_sans_filtre --repetitions 2 --budget-max 0.40` | 0,0843 $ mesurés le 28 octobre 2026 (78 requêtes de l'assistant, filtre compris) |
| 20 | `python -m ch20.pile --reevaluer <fichier>` | Gratuit : relit un fichier de résultats |
| 21 | `python -m ch21.biais ch19/resultats/ab-rejuge-<date>.json` | Gratuit : la part à corriger, groupe par groupe de notes |
| 22 | `python -m ch22.exploitation --budget-max 0.06` | 0,0220 $ mesurés le 28 octobre 2026 (trois journées, 60 brouillons ; temps local et pannes simulés) |
| 22 | `python -m ch22.exploitation --tableau ch22/resultats/exploitation-<date>.json` | Gratuit : relit le journal avec les règles du tableau de bord, écrit `tableau-<date>.json` |
| 22 | `python -m ch22.migration --candidat claude-sonnet-5-5 --repetitions 3 --budget-max 0.50` | 0,4169 $ mesurés le 28 octobre 2026 (60 brouillons de Claude Sonnet 5.5 et leurs jugements), puis la barrière |
| 23 | `python -m ch23.pilote --graine 23` | Gratuit : fabrique le pilote et écrit son bilan ; chiffres fabriqués pour le livre |
| 24 | `python -m ch24.verifier_passation ch24/document-de-passation.md` | Gratuit : code de sortie 1 si un fichier ou une commande cités n'existent pas |

## Versions vérifiées

| Chapitre | Python | SDK `anthropic` | Tests |
|---|---|---|---|
| 2 | 3.13 | 2.3.0 | 7 réussis le 26 octobre 2026 ; chiffrage lancé avec la clé de l'auteur, résultats dans `ch02/resultats/` |
| 3 | 3.13 | 2.3.0 | 19 de plus (26 au total) réussis le 26 octobre 2026 ; banc lancé avec la clé de l'auteur, réponses relues, résultats dans `ch03/resultats/` |
| 5 | 3.13 | 2.3.0, et `claude-agent-sdk` 0.2.174 (Claude Code 2.1.310 embarqué) | 20 de plus (46 au total) réussis le 27 octobre 2026 ; scripts lancés avec la clé de l'auteur, réponses relues, résultats dans `ch05/resultats/` |
| 6 | 3.13 | 2.3.0, et `claude-agent-sdk` 0.2.174 | 26 de plus (72 au total) réussis le 27 octobre 2026 ; scripts lancés avec la clé de l'auteur, fausses conclusions relues une à une, résultats dans `ch06/resultats/` |
| 7 | 3.13 | 2.3.0, `claude-agent-sdk` 0.2.174, `mcp` 2.3.0 | 19 de plus (91 au total) réussis le 27 octobre 2026 ; scripts lancés avec la clé de l'auteur, réponses relues, résultats dans `ch07/resultats/` |
| 8 | 3.13 | 2.3.0, `claude-agent-sdk` 0.2.174 | 23 de plus (114 au total) réussis le 27 octobre 2026 ; scripts lancés avec la clé de l'auteur, journaux de la garde relus, résultats dans `ch08/resultats/` |
| 9 | 3.13 | 2.3.0, `claude-agent-sdk` 0.2.174 (Claude Code 2.1.310 embarqué) | 21 de plus (135 au total) réussis le 27 octobre 2026 ; scripts lancés avec la clé de l'auteur, délégations et rapports relus, résultats dans `ch09/resultats/` |
| 10 | 3.13 | 2.3.0, `claude-agent-sdk` 0.2.174 | 16 de plus (151 au total) réussis le 27 octobre 2026 ; scripts lancés avec la clé de l'auteur, rapports et points de fin de conversation relus, résultats dans `ch10/resultats/` |
| 11 | 3.13 | 2.3.0 | 12 de plus (163 au total) réussis le 27 octobre 2026 ; banc lancé avec la clé de l'auteur, motifs relus, résultats dans `ch11/resultats/` |
| 12 | 3.13 | 2.3.0 | 14 de plus (177 au total) réussis le 27 octobre 2026 ; chaîne lancée avec la clé de l'auteur, extractions fautives relues une à une, résultats dans `ch12/resultats/` |
| 13 | 3.13 | 2.3.0 | 13 de plus (190 au total) réussis le 27 octobre 2026 ; échantillons, lots et relectures lancés avec la clé de l'auteur, erreurs relues une à une, résultats dans `ch13/resultats/` |
| 14 | 3.13 | 2.3.0 | 10 de plus (200 au total) réussis le 27 octobre 2026 ; recherches et réponses lancées avec la clé de l'auteur, réponses fausses relues une à une, résultats dans `ch14/resultats/` |
| 15 | 3.13 | 2.3.0, `claude-agent-sdk` 0.2.174 (Claude Code 2.1.310 embarqué) | 17 de plus (217 au total) réussis le 27 octobre 2026 ; séances lancées avec la clé de l'auteur, code produit et journaux du hook relus, résultats dans `ch15/resultats/` |
| 16 | 3.13 | 2.3.0, `claude-agent-sdk` 0.2.174 (Claude Code 2.1.310 embarqué) | 25 de plus (242 au total) réussis le 28 octobre 2026 ; séances lancées avec la clé de l'auteur, cartes, plans et corrections relus, résultats dans `ch16/resultats/` |
| 17 | 3.13 | 2.3.0, `claude-agent-sdk` 0.2.174 (Claude Code 2.1.310 embarqué, lancé avec `-p`) | 13 de plus (255 au total) réussis le 28 octobre 2026 ; revues lancées avec la clé de l'auteur, constats relus, résultats dans `ch17/resultats/` |
| 18 | 3.13 | 2.3.0 | 8 de plus (263 au total) réussis le 28 octobre 2026 ; appels lancés avec la clé de l'auteur, comptes rendus et questions relus, résultats dans `ch18/resultats/` |
| 19 | 3.13 | 2.3.0 | 9 de plus (272 au total) réussis le 28 octobre 2026 ; appels lancés avec la clé de l'auteur, verdicts du juge relus, résultats dans `ch19/resultats/` |
| 20 | 3.13 | 2.3.0 | 9 de plus (281 au total) réussis le 28 octobre 2026, sur un journal temporaire ; appels lancés avec la clé de l'auteur, brouillons et signalements relus, résultats dans `ch20/resultats/` |
| 21 | 3.13 | 2.3.0 | 4 de plus (285 au total) réussis le 28 octobre 2026 ; sans appel |
| 22 | 3.13 | 2.3.0 | 7 de plus (292 au total) réussis le 28 octobre 2026, sur un journal temporaire ; appels lancés avec la clé de l'auteur, tableau de bord et verdicts du juge relus, résultats dans `ch22/resultats/` |
| 23 | 3.13 | 2.3.0 | 5 de plus (297 au total) réussis le 28 octobre 2026 ; sans appel |
| 24 | 3.13 | 2.3.0 | 3 de plus (300 au total) réussis le 28 octobre 2026 ; sans appel |
