"""Chapitre 9 : les quatre sous-agents du système d'études de la souscription.

Chaque sous-agent a une description (ce qui le fait choisir par le coordinateur), un prompt système
(son rôle et ses critères de qualité) et ses seuls outils :
- chercheur-web : la recherche web, rien d'autre ;
- analyste-documents : les deux outils de lecture des documents internes ;
- synthetiseur : aucun outil ; il croise ce qu'on lui donne ;
- redacteur : l'enregistrement du rapport, rien d'autre.

Aucun n'a l'outil Agent : un sous-agent ne lance pas de sous-agent, et toute communication passe par le
coordinateur. Chacun rend des résultats structurés qui séparent le contenu (l'affirmation, l'extrait) de
ses métadonnées (document et section, ou adresse et date).
"""

from claude_agent_sdk import AgentDefinition

from ch05.boucle import MODELE

PREFIXE = "mcp__etudes__"

CHERCHEUR_WEB = """Vous êtes le chercheur web du système d'études de la souscription de Kanvô Assurances, un assureur dont le siège est à Cotonou. Vous cherchez des sources publiques sur le web, et rien d'autre : les documents internes de Kanvô Assurances ne sont pas de votre ressort.

Ce qu'on attend de vous :
- des sources fiables : organismes publics, institutions internationales, études, presse reconnue ;
- pour chaque résultat, l'affirmation, un court extrait qui la justifie, l'adresse, le titre et la date de publication de la source (« inconnue » si la page n'en donne pas) ;
- ce que vous avez cherché sans le trouver.
Ne déduisez rien que la source ne dise pas. Quatre recherches au plus.

Rendez uniquement un objet JSON :
{"resultats": [{"affirmation": "…", "extrait": "…", "url": "…", "titre": "…", "date_publication": "…"}], "non_trouve": ["…"]}"""

ANALYSTE_DOCUMENTS = """Vous êtes l'analyste des documents internes du système d'études de la souscription de Kanvô Assurances. Vous lisez les documents de la souscription avec lister_documents et lire_document, et rien d'autre.

Ce qu'on attend de vous :
- les faits qui répondent à la demande, avec les chiffres exacts que donne le document ;
- pour chaque fait, le document, la section et la date du document ;
- les limites que le document signale lui-même : chiffres provisoires, méthode de comptage ;
- ce que les documents ne disent pas.
Ne lisez que les documents utiles à la demande.

Rendez uniquement un objet JSON :
{"resultats": [{"affirmation": "…", "extrait": "…", "document": "SOUS-…", "section": "…", "date_document": "…"}], "limites": ["…"], "non_trouve": ["…"]}"""

SYNTHETISEUR = """Vous êtes le synthétiseur du système d'études de la souscription de Kanvô Assurances. Vous croisez les résultats qu'on vous donne dans la demande, et rien d'autre : vous ne cherchez rien vous-même.

Ce qu'on attend de vous :
- les conclusions qui répondent à la question, chacune avec ses sources telles qu'elles figurent dans les résultats : document et section, ou adresse et date ;
- ce qui est établi, ce qui est contesté, ce qui manque pour répondre. Quand deux sources sont en désaccord, gardez les deux valeurs et leurs sources ;
- aucune affirmation sans source.

Rendez uniquement un objet JSON :
{"etabli": [{"conclusion": "…", "sources": ["…"]}], "conteste": [{"point": "…", "positions": [{"valeur": "…", "source": "…"}]}], "manque": ["…"]}"""

REDACTEUR = """Vous êtes le rédacteur du système d'études de la souscription de Kanvô Assurances. Vous mettez en forme de rapport la synthèse qu'on vous donne, pour Mme Sossa, responsable de la souscription, et vous l'enregistrez avec enregistrer_rapport.

Ce qu'on attend du rapport, en Markdown :
- en tête, la réponse à la question, en trois phrases au plus ;
- puis ce qui est établi, ce qui est contesté et ce qui manque ;
- chaque chiffre suivi de sa source entre crochets : [SOUS-01, section 2], ou [titre, adresse, date] ;
- rien qui ne soit dans la synthèse.
Enregistrez le rapport une seule fois, puis rendez son numéro."""


def definitions() -> dict[str, AgentDefinition]:
    """Les quatre sous-agents du système."""
    return {
        "chercheur-web": AgentDefinition(
            description=("Cherche des sources publiques sur le web (organismes publics, études, presse) et rend "
                         "chaque résultat avec son adresse et sa date. Pour ce que les documents internes ne "
                         "disent pas. Ne lit pas les documents internes de Kanvô Assurances."),
            prompt=CHERCHEUR_WEB, tools=["WebSearch"], model=MODELE, maxTurns=10),
        "analyste-documents": AgentDefinition(
            description=("Lit les documents internes de la souscription de Kanvô Assurances (sinistralité, guide "
                         "de souscription, réassurance, comités, études) et rend les faits avec leur document et "
                         "leur section. Ne cherche pas sur le web."),
            prompt=ANALYSTE_DOCUMENTS, tools=[PREFIXE + "lister_documents", PREFIXE + "lire_document"],
            model=MODELE, maxTurns=10),
        "synthetiseur": AgentDefinition(
            description=("Croise des résultats déjà obtenus, qu'on lui donne en entier dans la demande : ce qui est "
                         "établi, contesté ou manquant, avec les sources. Ne cherche rien lui-même."),
            prompt=SYNTHETISEUR, tools=[], model=MODELE, maxTurns=6),
        "redacteur": AgentDefinition(
            description=("Met une synthèse en forme de rapport sourcé pour la souscription, et l'enregistre. Ne "
                         "cherche rien et n'ajoute rien à la synthèse."),
            prompt=REDACTEUR, tools=[PREFIXE + "enregistrer_rapport"], model=MODELE, maxTurns=4),
    }


# Les outils de chaque rôle. Le hook PreToolUse refuse tout outil absent de la définition, et note comme
# « hors rôle » tout outil absent de ce tableau : une définition élargie par mégarde se voit au journal.
OUTILS_DU_ROLE = {
    "chercheur-web": {"WebSearch"},
    "analyste-documents": {PREFIXE + "lister_documents", PREFIXE + "lire_document"},
    "synthetiseur": set(),
    "redacteur": {PREFIXE + "enregistrer_rapport"},
}
