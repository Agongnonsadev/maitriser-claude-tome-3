# Document de passation — le compte rendu assisté des Cliniques Ébène

*Exemple fictif : les Cliniques Ébène, leurs équipes et leurs rôles sont inventés pour le livre. Les fichiers et les commandes cités sont ceux du dépôt ; `python -m ch24.verifier_passation ch24/document-de-passation.md` vérifie qu'ils existent. Version remise à la DSI et au centre d'excellence à la fin de la mission 2.*

## 1. Ce que fait la solution

Après la consultation, le médecin dépose ses notes. Claude Haiku 5.5 en rédige un brouillon de compte rendu, avec le prompt B ; les contrôles du code vérifient que rien n'est inventé ni perdu ; la pile de sûreté filtre les pièces jointes et la sortie ; le médecin corrige et valide. Rien ne part vers un hôpital partenaire sans lui.

| Pièce | Où | Ce qu'elle décide |
|---|---|---|
| Le dossier de découverte et d'architecture | `ch18/dossier-mission-2.md` | Le besoin, les parties prenantes, l'architecture, et ce que le contradicteur y a changé |
| La rédaction et les contrôles du code | `ch18/compte_rendu.py` | L'outil strict, le prompt, les contrôles |
| Le banc et la barrière | `ch19/banc.py`, `ch19/hypothese.md` | Aucun changement ne part sans passer la barrière |
| La pile de sûreté | `ch20/pile.py` | Filtres, autorisation des outils, échec fermé, battements |
| Le registre des risques, le texte au patient | `ch21/registre-des-risques.md`, `ch21/texte-au-patient.md` | Chaque obligation, son contrôle, son responsable, sa preuve |
| L'exploitation | `ch22/exploitation.py` | Le journal, le disjoncteur, le repli, la file, le tableau de bord |
| La migration du modèle | `ch22/migration.py` | Le remplaçant passe le banc avant le préavis |
| Le pilote | `ch23/pilote.py` | Le bilan, les déclencheurs de revue |

## 2. Les gestes de tous les jours

| Geste | Commande | Quand |
|---|---|---|
| Lire le tableau de bord | `python -m ch22.exploitation --tableau ch22/resultats/exploitation-<date>.json` | Chaque matin, par l'astreinte |
| Passer un changement à la barrière | `python -m ch19.banc barriere ch19/resultats/<essai>.json --bras B --seuil 0.10` | Avant tout changement de prompt, de modèle ou de transcription |
| Lancer les tests | `python -m pytest` | Avant chaque livraison |
| Mesurer les écarts entre groupes | `python -m ch21.biais ch19/resultats/<essai>.json` | Chaque mois, au centre d'excellence |
| Vérifier cette passation | `python -m ch24.verifier_passation ch24/document-de-passation.md` | À chaque mise à jour du dépôt |

## 3. Ce que l'équipe diagnostique seule

| Ce que montre le tableau de bord | Ce que cela veut dire | Le geste |
|---|---|---|
| Temps local médian d'une clinique au-delà de 2 s | La cause est avant l'appel : réseau, poste, mandataire | Ticket au réseau de la clinique |
| Plus d'un quart des appels de la journée au-delà de 10 s, dans toutes les cliniques | La traîne de l'API | Lire la page d'état ; rien à changer si le repli tient |
| Disjoncteur ouvert, replis | L'API ne répond plus depuis un site | Vérifier que la file se vide au retour ; prévenir les médecins |
| Un médecin corrige plus du double des autres | Quelque chose a changé pour lui : transcription, type de notes | Revue avec le relais ; chercher ce qui a changé cette semaine-là |
| Une couche de la pile se tait | Un contrôle coupé | La rétablir ; l'échec fermé envoie les consultations en relecture en attendant |
| Le modèle passe *Deprecated* | Un retrait est annoncé | Passer le remplaçant recommandé au banc avec `ch22/migration.py` |
| La barrière refuse un changement | Le changement n'est pas assez bon pour partir | Ne pas le livrer |

## 4. Quand appeler Nokoué Conseil

- Une conclusion inventée signalée par un médecin : la clinique est coupée sur-le-champ, puis on appelle.
- La barrière refuse deux fois de suite le même changement.
- Un nouvel usage : ordonnances, courriers aux patients, une autre langue.
- Un nouveau pays, un nouveau partenaire, une nouvelle loi.
- Un modèle annoncé au retrait dont aucun remplaçant ne passe la barrière.

## 5. La configuration de l'équipe

Le dépôt de l'assistant porte son `CLAUDE.md`, pour l'équipe de la DSI qui le maintient avec Claude Code (chapitre 15). Il dit :
- les prompts sont versionnés, et un changement de prompt passe la barrière du banc ;
- un changement de modèle, de réglage ou de transcription aussi ;
- le journal ne contient jamais le texte d'une note ni le nom d'un patient ;
- les tests ne font aucun appel à l'API, et écrivent dans un journal temporaire.

## 6. Les relais, et le centre d'excellence

- Les deux relais de Cotonou, dont un médecin qui dicte : ils forment les relais d'Abidjan et de Dakar.
- Le centre d'excellence : les relais, la DSI, la direction médicale. Il se réunit chaque semaine pendant l'expansion, puis chaque mois.
- L'astreinte de la DSI suit le tableau de bord.

## 7. Ce qui reste ouvert

- Le niveau de service suivi sur la semaine : à décider avec la direction médicale.
- Le réseau de la clinique de Dakar, avant son ouverture.
- La situation de départ d'Abidjan et de Dakar, à mesurer avant l'assistant.
- L'identifiant de requête du SDK, à ajouter au journal.
