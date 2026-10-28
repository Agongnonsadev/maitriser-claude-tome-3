"""Chapitre 14 : les documents de la base documentaire, et deux façons de les découper.

Les documents (ch14/documents/) sont fictifs : conditions générales automobile et habitation, tableaux
des garanties, procédures de la direction des sinistres, et l'export des dossiers que la DSI avait déposé
dans le dossier partagé. Chaque document porte dans son en-tête sa référence et, pour les conditions et
les tableaux, la période des sinistres qu'il régit.

- decouper_naif : des fenêtres de taille fixe, avec chevauchement, sans regarder la forme du document ;
- decouper_structure : un article par morceau, avec son titre et son chapitre ; une ligne de tableau par
  morceau, réécrite en phrase avec le nom de chaque colonne ; une procédure par morceau ; une ligne de
  l'export par dossier. Chaque morceau garde ses métadonnées : produit, type, référence, période.

Une « unité » est ce qu'une question attend : un article, une ligne de tableau, une procédure, un dossier.
Un morceau couvre une unité s'il en contient assez pour répondre : pour une ligne de tableau, la ligne
ET l'en-tête qui nomme les colonnes.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DOSSIER = Path(__file__).parent / "documents"
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


@dataclass
class Document:
    nom: str
    reference: str
    produit: str          # auto, habitation, sinistres
    genre: str            # conditions, tableau, procedures, export
    debut: date | None    # période des sinistres régis, pour les conditions et les tableaux
    fin: date | None
    texte: str


@dataclass
class Unite:
    identifiant: str
    besoins: list[tuple[int, int]]   # les passages du texte qu'il faut avoir pour répondre


@dataclass
class Morceau:
    identifiant: str
    reference: str
    produit: str
    genre: str
    debut: date | None
    fin: date | None
    titre: str
    texte: str
    unites: list[str] = field(default_factory=list)

    def pour_la_recherche(self) -> str:
        return f"{self.titre}\n{self.texte}"

    def pour_le_modele(self) -> str:
        periode = ""
        if self.debut:
            periode = f" ; sinistres survenus du {_date_fr(self.debut)} au {_date_fr(self.fin)}" if self.fin \
                else f" ; sinistres survenus à partir du {_date_fr(self.debut)}"
        return f'<passage id="{self.identifiant}" source="{self.reference}{periode}">\n{self.titre}\n{self.texte}\n</passage>'


def _date_fr(d: date) -> str:
    return f"{'1er' if d.day == 1 else d.day} {MOIS[d.month - 1]} {d.year}"


def _lire_date(texte: str) -> date:
    j, m, a = re.match(r"(1er|\d{1,2}) (\w+) (\d{4})", texte).groups()
    return date(int(a), MOIS.index(m) + 1, 1 if j == "1er" else int(j))


def lire(chemin: Path) -> Document:
    texte = chemin.read_text(encoding="utf-8")
    reference = re.search(r"référence ([A-Z0-9-]+)\.", texte).group(1)
    nom = chemin.stem
    produit = "auto" if "auto" in nom else "habitation" if "habitation" in nom else "sinistres"
    genre = next(g for g, motif in (("conditions", "cg-"), ("tableau", "tableau-"), ("procedures", "procedures"),
                                    ("export", "export")) if nom.startswith(motif))
    debut = fin = None
    m = re.search(r"sinistres survenus du (.+?) au (.+?)[.,]", texte)
    if m:
        debut, fin = _lire_date(m.group(1)), _lire_date(m.group(2))
    else:
        m = re.search(r"sinistres survenus à partir du (.+?)[.,]", texte)
        if m:
            debut = _lire_date(m.group(1))
    return Document(nom, reference, produit, genre, debut, fin, texte)


def charger(noms: list[str] | None = None, dossier: Path = DOSSIER) -> list[Document]:
    chemins = sorted(dossier.glob("*.md"))
    return [lire(c) for c in chemins if noms is None or c.stem in noms]


def manifeste(documents: list[Document]) -> dict[str, str]:
    """L'empreinte de chaque document indexé : ce qu'on compare au dossier source pour savoir si l'index
    est à jour (étape 6)."""
    return {d.nom: hashlib.sha256(d.texte.encode("utf-8")).hexdigest()[:16] for d in documents}


def ecarts(index: dict[str, str], source: dict[str, str]) -> dict[str, list[str]]:
    return {"absents_de_l_index": sorted(set(source) - set(index)),
            "modifies": sorted(n for n in set(source) & set(index) if source[n] != index[n]),
            "retires_de_la_source": sorted(set(index) - set(source))}


# --- Les unités : ce qu'une question attend ------------------------------------------------------

def _lignes(texte: str):
    debut = 0
    for ligne in texte.split("\n"):
        yield debut, debut + len(ligne), ligne
        debut += len(ligne) + 1


def _cle(texte: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", texte.lower().translate(str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")))
    return s.strip("-")


def unites(doc: Document) -> list[Unite]:
    resultat = []
    lignes = list(_lignes(doc.texte))
    if doc.genre in ("conditions", "procedures"):
        motif = r"### Article (\d+) — " if doc.genre == "conditions" else r"## Procédure (\d+) — "
        prefixe = "art" if doc.genre == "conditions" else "proc"
        titres = [(a, l, re.match(motif, l).group(1)) for a, b, l in lignes if re.match(motif, l)]
        for i, (a, l, n) in enumerate(titres):
            fin = titres[i + 1][0] if i + 1 < len(titres) else len(doc.texte)
            suivant = re.search(r"\n## ", doc.texte[a + 1:fin])   # un titre de chapitre qui suit
            fin = a + 1 + suivant.start() if suivant else fin
            resultat.append(Unite(f"{doc.reference}:{prefixe}-{n}", [(a, fin)]))
    else:
        tableau = [(a, b, l) for a, b, l in lignes if l.startswith("|")]
        entete = tableau[0]
        for a, b, l in tableau[2:]:
            nom = l.strip("|").split("|")[0].strip()
            resultat.append(Unite(f"{doc.reference}:{_cle(nom)}", [(entete[0], entete[1]), (a, b)]))
    return resultat


# --- Les deux découpages -------------------------------------------------------------------------

def _meta(doc: Document) -> dict:
    return {"reference": doc.reference, "produit": doc.produit, "genre": doc.genre, "debut": doc.debut, "fin": doc.fin}


def decouper_naif(doc: Document, taille: int = 1000, chevauchement: int = 200) -> list[Morceau]:
    """Des fenêtres de `taille` caractères, qui se chevauchent : la méthode qu'on trouve partout."""
    morceaux, debut, n = [], 0, 1
    us = unites(doc)
    while debut < len(doc.texte):
        fin = min(debut + taille, len(doc.texte))
        couvertes = [u.identifiant for u in us if all(_couvre(debut, fin, s) for s in u.besoins)]
        morceaux.append(Morceau(f"{doc.reference}#f{n}", titre=f"{doc.reference}, extrait {n}",
                                texte=doc.texte[debut:fin], unites=couvertes, **_meta(doc)))
        if fin == len(doc.texte):
            break
        debut, n = fin - chevauchement, n + 1
    return morceaux


def _couvre(debut: int, fin: int, s: tuple[int, int], part: float = 0.8) -> bool:
    """La fenêtre contient-elle au moins `part` du passage ? Un article coupé au milieu ne répond plus."""
    a, b = s
    return (min(fin, b) - max(debut, a)) >= part * (b - a)


def decouper_structure(doc: Document) -> list[Morceau]:
    """Un morceau par unité, avec ce qu'il faut pour le comprendre seul."""
    morceaux = []
    if doc.genre in ("conditions", "procedures"):
        chapitre = ""
        for u in unites(doc):
            a, b = u.besoins[0]
            avant = doc.texte[:a]
            chapitres = re.findall(r"\n## (Chapitre .+)", avant)
            chapitre = chapitres[-1] if chapitres else ""
            bloc = doc.texte[a:b].strip()
            titre_ligne, corps = bloc.split("\n", 1)
            titre = titre_ligne.lstrip("# ").strip()
            titre = f"{doc.reference}, {titre}" + (f" ({chapitre})" if chapitre else "")
            morceaux.append(Morceau(u.identifiant, titre=titre, texte=corps.strip(), unites=[u.identifiant], **_meta(doc)))
    else:
        lignes = [l for _, _, l in _lignes(doc.texte) if l.startswith("|")]
        colonnes = [c.strip() for c in lignes[0].strip("|").split("|")]
        intitule = doc.texte.split("\n", 1)[0].lstrip("# ").strip()
        for u, l in zip(unites(doc), lignes[2:]):
            cellules = [c.strip() for c in l.strip("|").split("|")]
            if doc.genre == "tableau":
                texte = " ; ".join(f"formule {col} : {val.lower()}" for col, val in zip(colonnes[1:], cellules[1:])) + "."
                titre = f"{doc.reference}, {intitule}, garantie {cellules[0]}"
            else:
                texte = " ; ".join(f"{col} : {val}" for col, val in zip(colonnes[1:], cellules[1:])) + "."
                titre = f"{doc.reference}, {intitule}, dossier {cellules[0]}"
            morceaux.append(Morceau(u.identifiant, titre=titre, texte=texte, unites=[u.identifiant], **_meta(doc)))
    return morceaux


def decouper(documents: list[Document], methode: str = "structure") -> list[Morceau]:
    f = decouper_structure if methode == "structure" else decouper_naif
    return [m for d in documents for m in f(d)]


if __name__ == "__main__":
    docs = charger()
    for d in docs:
        print(d.nom, d.reference, d.produit, d.genre, d.debut, d.fin, len(d.texte))
    for methode in ("naif", "structure"):
        ms = decouper(docs, methode)
        print(methode, len(ms), "morceaux ;", sum(not m.unites for m in ms), "sans unité entière")
    print(decouper_structure(docs[[d.nom for d in docs].index("tableau-auto-2026")])[4].pour_le_modele())
