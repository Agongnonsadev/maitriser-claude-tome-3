# Registre des risques — compte rendu assisté des Cliniques Ébène

*Exemple fictif : les Cliniques Ébène et leur organisation sont inventées pour le livre. Les textes cités ont été lus le 28 octobre 2026, dans leur version publiée ce jour-là ; ce registre n'est pas un avis juridique. Chaque ligne se relit avec le délégué à la protection des données des cliniques et un juriste de chaque pays.*

Chaque obligation a son contrôle, son responsable et sa preuve. Une obligation sans preuve n'est pas tenue : elle est espérée.

## 1. Les données de santé

| Obligation | Texte | Contrôle | Responsable | Preuve |
|---|---|---|---|---|
| Les données de santé ne se traitent que dans les cas prévus | Bénin : Code du numérique, art. 394 (interdiction, et ses exceptions, dont les soins sous la surveillance d'un professionnel de santé) ; Côte d'Ivoire : loi n° 2013-450, art. 21 ; Sénégal : loi n° 2008-12, art. 40 et 43 ; Union européenne : RGPD, art. 9 | Finalité écrite : rédiger le compte rendu d'une consultation, sous la responsabilité du médecin | Délégué à la protection des données | La fiche de traitement, signée |
| Une autorisation préalable avant le premier patient | Bénin : art. 407 (APDP) ; Côte d'Ivoire : art. 7 (ARTCI) ; Sénégal : art. 20 pour la recherche et les données génétiques, [régime de la finalité de soins à confirmer avec la CDP] | Pas de pilote sans l'autorisation de chaque pays | Délégué à la protection des données | Les autorisations, ou les récépissés |
| La collecte auprès de la personne | Sénégal : art. 44 | Les notes viennent de la consultation ; les pièces jointes de tiers sont signalées (chapitre 20) | Direction médicale | Le circuit des pièces jointes |

## 2. Les transferts

| Obligation | Texte | Contrôle | Responsable | Preuve |
|---|---|---|---|---|
| Un transfert hors du pays demande une protection équivalente, et l'accord de l'autorité | Bénin : art. 391 et 407 ; Côte d'Ivoire : art. 7 et 26 ; Sénégal : art. 49 (information préalable de la CDP) | La cartographie des flux : l'inférence de l'API a lieu hors des trois pays (`inference_geo` vaut `global` ou `us`) | Délégué à la protection des données, DSI | Les autorisations de transfert ; la cartographie signée |
| Les comptes rendus envoyés aux partenaires français | RGPD, chapitre V (art. 44 et suivants) | Le contrat avec chaque partenaire ; l'envoi par le médecin, après validation (chapitre 20) | Direction médicale | Les contrats ; le journal des envois |
| L'hébergement des données de santé en France | Code de la santé publique, art. L. 1111-8 : l'hébergeur est titulaire d'un certificat de conformité | Les partenaires reçoivent les comptes rendus dans leur système d'information, sur un hébergement certifié | Partenaires | Le certificat de leur hébergeur |
| La conservation chez le fournisseur | Conditions du fournisseur : non-conservation (ZDR) sur demande, par organisation (chapitre 18) | ZDR demandée et obtenue avant le pilote ; ni traitement par lots, ni Files API | DSI | L'accord de non-conservation |

## 3. L'outil

| Obligation | Texte | Contrôle | Responsable | Preuve |
|---|---|---|---|---|
| Aucune décision fondée sur le seul traitement automatisé | Côte d'Ivoire : art. 25 | Le médecin valide chaque compte rendu ; rien n'entre au dossier sans lui | Direction médicale | Le journal des validations |
| Le règlement européen sur l'IA, pour des sorties utilisées dans l'Union | Règlement (UE) 2024/1689, art. 2.1 c) ; dates du règlement (UE) 2026/1744 : 2 décembre 2027 (annexe III), 2 août 2028 (annexe I) | La qualification du système (haut risque ou non), écrite avec un juriste ; la finalité déclarée : rédiger, jamais diagnostiquer | Juriste, DSI | La note de qualification |
| La confidentialité et la sécurité | Côte d'Ivoire : art. 19 ; RGPD, art. 32 [à relire] | La pile de sûreté (chapitre 20) | DSI | Les tests ; le tableau de bord |
| Le sous-traitant offre des garanties suffisantes | Côte d'Ivoire : art. 20 | Le contrat avec le fournisseur de l'IA et avec l'hébergeur | DSI | Les contrats |

## 4. Les personnes

| Obligation | Texte | Contrôle | Responsable | Preuve |
|---|---|---|---|---|
| L'information du patient, au plus tard lors de la collecte | Côte d'Ivoire : art. 28 ; Bénin : art. 415 ; [Sénégal : article à relire] ; RGPD pour les données reçues par les partenaires | Le texte au patient (`texte-au-patient.md`), remis à l'accueil | Délégué à la protection des données | Le texte, et sa version |
| L'analyse d'impact | RGPD, art. 35, pour les partenaires ; [équivalents locaux à relire] | Une analyse avant le pilote, mise à jour à chaque changement de modèle | Délégué à la protection des données | L'analyse, datée |
| Des résultats égaux d'un groupe de patients à l'autre | Exigence éthique du comité ; pas d'article cité ici | La mesure par groupe de notes (`ch21/biais.py`), à chaque version | Yao, puis la DSI | Le rapport de la mesure |

## 5. Ce que le registre ne dit pas encore

- Le régime sénégalais exact pour une finalité de soins (déclaration ou autorisation), à confirmer avec la CDP.
- Les équivalents locaux de l'analyse d'impact.
- La qualification du système au regard du règlement européen sur l'IA.
