"""Chapitre 14 : chercher dans la base documentaire, selon la forme des données et des questions.

- IndexBM25 : la recherche lexicale, en Python pur (le Tome 2, chapitre 11, la présente en détail) ;
- filtrer : les métadonnées avant la recherche : le produit du dossier, et la période des sinistres que
  régit le document, comparée à la date du sinistre ;
- reecrire : Claude Haiku 5.5 reformule la question du gestionnaire avec les mots des conditions générales,
  et chaque reformulation interroge l'index. C'est la recherche « par le sens » de ce chapitre : Kanvô
  Assurances n'a pas encore choisi de fournisseur d'embeddings (voir l'index de vecteurs du Tome 2) ;
- fusionner : la fusion des rangs (reciprocal rank fusion) ;
- reclasser : Claude Haiku 5.5 relit les vingt meilleurs candidats et garde les plus utiles.

Chaque appel à Claude est journalisé, avec son coût ; la durée de chaque étape est mesurée.
"""

import math
import re
import time
import unicodedata
from collections import Counter
from datetime import date

from assureur.couts import cout
from assureur.journal import noter
from ch14.corpus import MOIS, Morceau

MODELE = "claude-haiku-5-5"

MOTS_VIDES = set("""
a au aux avec ce ces cet cette d dans de des du elle en est et etre il ils j je l la le les leur
leurs lui m ma mais me mes mon n ne nos notre nous on ou par pas pour qu que quel quelle quelles
quels qui s sa se ses si son sont sur t ta te tes ton tu un une vos votre vous y c ca est-ce
""".split())

Classement = list[tuple[Morceau, float]]


def mots(texte: str) -> list[str]:
    """Minuscules, sans accents, sans mots vides, un pluriel simple ramené au singulier."""
    sans_accents = unicodedata.normalize("NFD", texte).encode("ascii", "ignore").decode().lower()
    resultat = []
    for mot in re.findall(r"[a-z0-9]+", sans_accents):
        if mot in MOTS_VIDES:
            continue
        if len(mot) > 3 and mot[-1] in "sx":
            mot = mot[:-1]
        resultat.append(mot)
    return resultat


class IndexBM25:
    def __init__(self, morceaux: list[Morceau], k1: float = 1.5, b: float = 0.75):
        self.morceaux, self.k1, self.b = morceaux, k1, b
        self.termes = [Counter(mots(m.pour_la_recherche())) for m in morceaux]
        self.longueurs = [sum(t.values()) for t in self.termes]
        self.moyenne = sum(self.longueurs) / len(morceaux) if morceaux else 0
        frequences = Counter(mot for t in self.termes for mot in t)
        n = len(morceaux)
        self.idf = {mot: math.log(1 + (n - f + 0.5) / (f + 0.5)) for mot, f in frequences.items()}

    def chercher(self, question: str, k: int = 5, garder=None) -> Classement:
        q = mots(question)
        scores = []
        for i, m in enumerate(self.morceaux):
            if garder and not garder(m):
                continue
            s, norme = 0.0, 1 - self.b + self.b * self.longueurs[i] / self.moyenne
            for mot in q:
                f = self.termes[i].get(mot, 0)
                if f:
                    s += self.idf[mot] * f * (self.k1 + 1) / (f + self.k1 * norme)
            if s > 0:
                scores.append((m, s))
        return sorted(scores, key=lambda x: -x[1])[:k]


def filtre(produit: str | None = None, date_sinistre: date | None = None):
    """Garder les morceaux du bon produit (les procédures et l'export valent pour tous), et ceux dont la
    période contient la date du sinistre. Sans produit ni date, tout passe."""
    def garder(m: Morceau) -> bool:
        if produit and m.produit not in (produit, "sinistres"):
            return False
        if date_sinistre and m.debut:
            if date_sinistre < m.debut or (m.fin and date_sinistre > m.fin):
                return False
        return True
    return garder


def fusionner(*classements: Classement, k: int = 60, garder: int = 5) -> Classement:
    scores, par_id = {}, {}
    for classement in classements:
        for rang, (m, _) in enumerate(classement, start=1):
            scores[m.identifiant] = scores.get(m.identifiant, 0.0) + 1 / (k + rang)
            par_id[m.identifiant] = m
    return [(par_id[i], s) for i, s in sorted(scores.items(), key=lambda x: -x[1])[:garder]]


OUTIL_REECRITURE = {
    "name": "requetes",
    "description": "Rend les requêtes de recherche.",
    "input_schema": {"type": "object", "properties": {"requetes": {"type": "array", "items": {"type": "string"}}},
                     "required": ["requetes"], "additionalProperties": False},
}

CONSIGNE_REECRITURE = """Un gestionnaire de sinistres de Kanvô Assurances pose une question. Écrivez trois requêtes de recherche pour retrouver la réponse dans les conditions générales, les tableaux des garanties et les procédures internes, avec les mots qu'emploient ces documents : garanties, exclusions, franchises, plafonds, délais, déclaration, expertise, indemnité. Ne répondez pas à la question."""

OUTIL_RECLASSEMENT = {
    "name": "pertinents",
    "description": "Rend les identifiants des passages utiles, du plus utile au moins utile.",
    "input_schema": {"type": "object", "properties": {"identifiants": {"type": "array", "items": {"type": "string"}}},
                     "required": ["identifiants"], "additionalProperties": False},
}


def _appeler(client, outil: dict, contenu: str, cas: str, systeme: str | None = None, max_tokens: int = 400):
    debut = time.perf_counter()
    p = {"model": MODELE, "max_tokens": max_tokens, "tools": [outil], "thinking": {"type": "disabled"},
         "tool_choice": {"type": "tool", "name": outil["name"]}, "messages": [{"role": "user", "content": contenu}]}
    if systeme:
        p["system"] = systeme
    r = client.messages.create(**p)
    duree = time.perf_counter() - debut
    c = cout(MODELE, r.usage)
    noter(getattr(r, "_request_id", None), MODELE, c, chapitre="14", etape=outil["name"], cas=cas)
    appel = next(b for b in r.content if b.type == "tool_use")
    return appel.input, c.dollars, duree


def reecrire(client, question: str, cas: str = "") -> tuple[list[str], float, float]:
    entree, dollars, duree = _appeler(client, OUTIL_REECRITURE, f"{CONSIGNE_REECRITURE}\n\nQuestion : {question}", cas)
    return [r for r in entree.get("requetes", []) if isinstance(r, str)][:3], dollars, duree


def reclasser(client, question: str, candidats: list[Morceau], garder: int = 5, cas: str = "") -> tuple[list[Morceau], float, float]:
    """Un identifiant inconnu est écarté : le code ne croit pas sur parole une liste produite par un modèle."""
    if not candidats:
        return [], 0.0, 0.0
    passages = "\n\n".join(m.pour_le_modele() for m in candidats)
    contenu = (f"{passages}\n\nQuestion d'un gestionnaire : {question}\n\nDonnez les identifiants des {garder} passages "
               "au plus qui aident à répondre, du plus utile au moins utile. Si aucun n'aide, une liste vide.")
    entree, dollars, duree = _appeler(client, OUTIL_RECLASSEMENT, contenu, cas,
                                      "Vous classez des passages de la documentation de Kanvô Assurances. Vous ne répondez pas à la question.")
    par_id = {m.identifiant: m for m in candidats}
    choisis = [i for i in entree.get("identifiants", []) if i in par_id]
    return [par_id[i] for i in dict.fromkeys(choisis)][:garder], dollars, duree


def chercher(client, index: IndexBM25, question: str, strategie: str, k: int = 5, produit: str | None = None,
             date_sinistre: date | None = None, cas: str = "") -> dict:
    """Une recherche complète, avec sa durée et son coût.

    strategie : « bm25 », « produit » (bm25, filtré sur le produit seul), « filtre » (bm25, filtré sur le
    produit et la période), « reecriture » (filtre, plus trois reformulations fusionnées), « reclassement »
    (réécriture, puis Claude garde les k meilleurs parmi vingt)."""
    debut, dollars, appels = time.perf_counter(), 0.0, 0
    garder = None if strategie == "bm25" else filtre(produit, None if strategie == "produit" else date_sinistre)
    if date_sinistre:
        # Une date est un critère, pas un mot à chercher : « 10 décembre 2026 » faisait remonter l'export des
        # dossiers, plein de dates, devant l'article qui répond (mesuré à l'étape 6 du chapitre).
        question = re.sub(r"\b(1er|\d{1,2}) (" + "|".join(MOIS) + r") \d{4}\b|\b\d{4}-\d{2}-\d{2}\b", " ", question)
    if strategie in ("bm25", "produit", "filtre"):
        resultats = [m for m, _ in index.chercher(question, k, garder)]
    else:
        requetes, d, _ = reecrire(client, question, cas)
        dollars, appels = dollars + d, appels + 1
        classements = [index.chercher(q, 20, garder) for q in [question, *requetes]]
        candidats = [m for m, _ in fusionner(*classements, garder=20 if strategie == "reclassement" else k)]
        if strategie == "reclassement":
            resultats, d, _ = reclasser(client, question, candidats, k, cas)
            dollars, appels = dollars + d, appels + 1
        else:
            resultats = candidats[:k]
    return {"morceaux": resultats, "duree_s": time.perf_counter() - debut, "dollars": dollars, "appels": appels}
