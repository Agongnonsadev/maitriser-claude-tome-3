"""Les documents internes de la souscription, et les outils qui les lisent (chapitre 9).

Six documents fictifs, dans donnees/souscription/ : la sinistralité de l'option inondation, le guide
de souscription, la note du réassureur, le compte rendu du comité, les vols de deux-roues, et une
ancienne étude. Chacun porte un en-tête (identifiant, titre, service, date, objet) et des sections.

Les outils rendent le contenu séparé de ses métadonnées : le document, sa date, la section. C'est ce
qui permet de garder la source de chaque affirmation jusqu'au rapport (chapitre 10).

Ces outils sont contraints plutôt que génériques : lire_document ne prend qu'un identifiant du
catalogue, jamais un chemin de fichier. L'analyste ne peut rien lire d'autre que ces documents.

Au chapitre 10, la bibliothèque reçoit des documents en plus (supplements), et des pannes simulées :
pannes={"SOUS-03": 1} fait échouer la première lecture de SOUS-03 (une erreur passagère), et
pannes={"SOUS-03": -1} toutes (une panne qui dure).
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from assureur.outils_v2 import _objet, erreur

DOSSIER = Path(__file__).parent / "donnees" / "souscription"
IDENTIFIANT = r"^SOUS-\d{2}$"


@dataclass
class Document:
    document: str
    titre: str
    service: str
    date: str
    objet: str
    sections: list[dict]   # {"section": "2. Évolution annuelle", "texte": "…"}


def lire_fichier(chemin: Path) -> Document:
    texte = chemin.read_text(encoding="utf-8").replace("\r\n", "\n")
    entete, corps = re.match(r"^---\n(.*?)\n---\n(.*)$", texte, re.DOTALL).groups()
    meta = dict(ligne.split(": ", 1) for ligne in entete.splitlines())
    sections = [{"section": titre.strip(), "texte": contenu.strip()}
                for titre, contenu in re.findall(r"^## (.+?)\n(.*?)(?=^## |\Z)", corps, re.MULTILINE | re.DOTALL)]
    return Document(meta["document"], meta["titre"], meta["service"], meta["date"], meta["objet"], sections)


@dataclass
class Bibliotheque:
    """Les documents de la souscription, et les rapports que le rédacteur y dépose."""
    dossier: Path = DOSSIER
    documents: dict[str, Document] = field(default_factory=dict)
    rapports: list[dict] = field(default_factory=list)
    lectures: list[str] = field(default_factory=list)   # chaque document lu, dans l'ordre
    supplements: tuple[Path, ...] = ()                  # d'autres dossiers de documents
    pannes: dict[str, int] = field(default_factory=dict)  # document -> échecs à venir (-1 : toujours)
    echecs: list[str] = field(default_factory=list)     # chaque lecture échouée, dans l'ordre

    def __post_init__(self):
        if not self.documents:
            fichiers = sorted(f for d in (self.dossier, *self.supplements) for f in d.glob("SOUS-*.md"))
            self.documents = {d.document: d for d in map(lire_fichier, fichiers)}

    def en_panne(self, identifiant: str) -> bool:
        """Vrai si cette lecture doit échouer ; décompte les pannes passagères."""
        reste = self.pannes.get(identifiant, 0)
        if reste == 0:
            return False
        if reste > 0:
            self.pannes[identifiant] = reste - 1
        self.echecs.append(identifiant)
        return True

    def lister(self) -> list[dict]:
        return [{"document": d.document, "titre": d.titre, "service": d.service, "date": d.date, "objet": d.objet}
                for d in self.documents.values()]

    def lire(self, identifiant: str) -> dict:
        d = self.documents[identifiant]
        self.lectures.append(identifiant)
        return {"document": d.document, "titre": d.titre, "service": d.service, "date": d.date,
                "sections": d.sections}

    def enregistrer_rapport(self, titre: str, contenu: str) -> dict:
        numero = f"RAP-{len(self.rapports) + 1:03d}"
        self.rapports.append({"rapport": numero, "titre": titre, "contenu": contenu})
        return {"rapport": numero, "caracteres": len(contenu)}


OUTILS = [
    {
        "name": "lister_documents",
        "description": (
            "Liste les documents internes de la souscription de Kanvô Assurances : identifiant (SOUS- suivi de "
            "2 chiffres), titre, service, date et objet de chacun. À appeler en premier, pour choisir les "
            "documents à lire. Ne rend pas leur contenu (lire_document)."),
        "strict": True,
        "input_schema": _objet({}, []),
    },
    {
        "name": "lire_document",
        "description": (
            "Lit un document interne de la souscription, par son identifiant (SOUS- suivi de 2 chiffres, donné "
            "par lister_documents). Rend ses métadonnées (titre, service, date) et son contenu section par "
            "section : citez le document et la section de chaque chiffre que vous reprenez. Ne lit ni un "
            "chemin de fichier, ni une adresse web."),
        "strict": True,
        "input_schema": _objet({"document": {"type": "string", "description": "Par exemple SOUS-01"}}, ["document"]),
    },
    {
        "name": "enregistrer_rapport",
        "description": (
            "Enregistre le rapport final d'une étude, en Markdown, dans l'espace de la souscription. Rend le "
            "numéro du rapport (RAP- suivi de 3 chiffres). À appeler une fois, quand le rapport est complet."),
        "strict": True,
        "input_schema": _objet({"titre": {"type": "string"}, "contenu": {"type": "string",
                                "description": "Le rapport complet, en Markdown, sources comprises"}},
                               ["titre", "contenu"]),
    },
]
NOMS = [o["name"] for o in OUTILS]


def executer(bibliotheque: Bibliotheque, nom: str, arguments: dict) -> tuple[str, bool]:
    """Exécute un outil ; rend (le résultat en JSON, True si c'est une erreur)."""
    if nom == "lister_documents":
        return json.dumps({"documents": bibliotheque.lister()}, ensure_ascii=False), False
    if nom == "lire_document":
        identifiant = (arguments.get("document") or "").strip().upper()
        if not re.match(IDENTIFIANT, identifiant):
            return erreur("validation", False, f"« {arguments.get('document')} » n'est pas un identifiant de "
                          "document (SOUS- suivi de 2 chiffres).", "Prenez l'identifiant dans lister_documents.")
        if identifiant not in bibliotheque.documents:
            return erreur("metier", False, f"Aucun document {identifiant}.",
                          "Prenez l'identifiant dans lister_documents.")
        if bibliotheque.en_panne(identifiant):
            return erreur("passagere", True, f"Le serveur documentaire n'a pas répondu pour {identifiant} "
                          "(délai dépassé).", "Réessayez une fois. Si l'erreur persiste, continuez sans ce document "
                          "et signalez-le.")
        return json.dumps(bibliotheque.lire(identifiant), ensure_ascii=False), False
    if nom == "enregistrer_rapport":
        if not (arguments.get("contenu") or "").strip():
            return erreur("validation", False, "Le rapport est vide.", "Enregistrez le rapport complet.")
        return json.dumps(bibliotheque.enregistrer_rapport(arguments.get("titre", ""), arguments["contenu"]),
                          ensure_ascii=False), False
    return erreur("validation", False, f"Outil inconnu : {nom}.", "Utilisez un outil de la liste.")
