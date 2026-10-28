"""Le système de gestion de Kanvô Assurances, simulé : assurés, contrats, sinistres.

Les données sont fabriquées (donnees/systeme.json). Le vrai système de l'assureur est un ancien
logiciel que l'agent consultera par un serveur MCP (chapitre 7) ; ici, de simples fonctions
Python, que la boucle appelle quand Claude le demande.

Comme le vrai, il peut refuser ou échouer, et chaque refus a sa cause (chapitre 6) :
- Introuvable : le numéro n'existe pas ;
- Indisponible : le logiciel ne répond pas (une panne simulée, réglée par `pannes`) ;
- Interdit : le compte de service de l'agent n'a pas ce droit (les contrats santé) ;
- RegleMetier : une règle de gestion l'empêche (un dossier archivé).

Trois actions modifient le système : transmettre une demande à un gestionnaire ; résilier un
contrat, que la DSI expose mais que l'agent des sinistres n'a pas à faire ; et le règlement rapide
d'un sinistre évalué (chapitre 8). Elles sont notées dans `transmissions`, `resiliations` et
`reglements`, ce qui permet de vérifier ce qui a eu lieu.

La date de naissance d'un assuré ne sort jamais du système : elle sert seulement à vérifier son
identité (verifier_identite répond oui ou non).
"""

import copy
import json
import unicodedata
from pathlib import Path

DONNEES = Path(__file__).parent / "donnees" / "systeme.json"


class ErreurSysteme(Exception):
    """Toute erreur rendue par le système de gestion."""


class Introuvable(ErreurSysteme):
    """Le numéro donné n'existe pas dans le système."""


class Indisponible(ErreurSysteme):
    """Le logiciel ne répond pas. Passager : une nouvelle tentative peut réussir."""


class Interdit(ErreurSysteme):
    """Le compte de service de l'agent n'a pas ce droit."""


class RegleMetier(ErreurSysteme):
    """Une règle de gestion empêche l'opération."""


CIVILITES = {"m", "mme", "mlle", "mr", "monsieur", "madame", "mademoiselle"}


def _public(assure: dict) -> dict:
    """Ce qu'on peut montrer d'un assuré : tout, sauf sa date de naissance."""
    return {k: copy.deepcopy(v) for k, v in assure.items() if k != "date_naissance"}


def _sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte.lower()) if unicodedata.category(c) != "Mn")


class Systeme:
    def __init__(self, chemin: Path = DONNEES, pannes: dict[str, int] | None = None):
        donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
        self.assures = {a["numero"]: a for a in donnees["assures"]}
        self.contrats = {c["numero"]: c for c in donnees["contrats"]}
        self.sinistres = list(donnees["sinistres"])
        self.pannes = dict(pannes or {})  # nom de la méthode -> nombre d'appels qui échoueront
        self.transmissions: list[dict] = []
        self.resiliations: list[dict] = []
        self.reglements: list[dict] = []

    @staticmethod
    def _numero(valeur: str) -> str:
        return valeur.strip().upper().replace(" ", "")

    def _entrer(self, methode: str) -> None:
        if self.pannes.get(methode, 0) > 0:
            self.pannes[methode] -= 1
            raise Indisponible("Le logiciel de gestion ne répond pas (délai dépassé).")

    def _contrat(self, numero_contrat: str) -> dict:
        contrat = self.contrats.get(self._numero(numero_contrat))
        if contrat is None:
            raise Introuvable(f"Aucun contrat {numero_contrat}.")
        if contrat["type"] == "santé":
            raise Interdit("Les contrats santé sont réservés à l'équipe santé : le compte de l'agent des "
                           "sinistres n'y a pas accès.")
        return contrat

    def consulter_assure(self, numero_assure: str | None = None, numero_contrat: str | None = None) -> dict:
        self._entrer("consulter_assure")
        if numero_assure:
            assure = self.assures.get(self._numero(numero_assure))
        elif numero_contrat:
            contrat = self.contrats.get(self._numero(numero_contrat))
            assure = self.assures.get(contrat["assure"]) if contrat else None
        else:
            raise Introuvable("Donnez un numéro d'assuré (KA-AS-…) ou un numéro de contrat.")
        if assure is None:
            raise Introuvable(f"Aucun assuré pour {numero_assure or numero_contrat}.")
        return _public(assure)

    def rechercher_assures(self, nom: str) -> list[dict]:
        """Les assurés dont le nom contient tous les mots cherchés, civilités ôtées, sans tenir compte des
        accents ni des majuscules : « M. Zinsou » trouve « M. Marius Zinsou »."""
        self._entrer("rechercher_assures")
        mots = [m for m in _sans_accents(nom).replace(".", " ").split() if m not in CIVILITES]
        return [_public(a) for a in self.assures.values()
                if mots and all(m in _sans_accents(a["nom"]).replace(".", " ").split() for m in mots)]

    def consulter_contrat(self, numero_contrat: str) -> dict:
        self._entrer("consulter_contrat")
        return copy.deepcopy(self._contrat(numero_contrat))

    def consulter_sinistres(self, numero_contrat: str) -> list[dict]:
        """Les sinistres d'un contrat, ouverts ou clos ; une liste vide s'il n'y en a aucun."""
        self._entrer("consulter_sinistres")
        numero = self._contrat(numero_contrat)["numero"]
        return [copy.deepcopy(s) for s in self.sinistres if s["contrat"] == numero]

    def consulter_sinistre(self, numero_sinistre: str) -> dict:
        self._entrer("consulter_sinistre")
        numero = self._numero(numero_sinistre)
        sinistre = next((s for s in self.sinistres if s["numero"] == numero), None)
        if sinistre is None:
            raise Introuvable(f"Aucun sinistre {numero_sinistre}.")
        self._contrat(sinistre["contrat"])  # même règle d'accès que pour le contrat
        if sinistre["statut"] == "archivé":
            raise RegleMetier(f"Le dossier {numero} est archivé : seul un gestionnaire peut le rouvrir et le consulter.")
        return copy.deepcopy(sinistre)

    def transmettre_a_un_gestionnaire(self, motif: str, resume: str, numero_contrat: str | None = None) -> dict:
        transmission = {"numero": f"TR-{len(self.transmissions) + 1:04d}", "motif": motif, "resume": resume,
                        "contrat": self._numero(numero_contrat) if numero_contrat else None,
                        "suite": "Un gestionnaire rappellera l'assuré."}
        self.transmissions.append(transmission)
        return dict(transmission)

    def resilier_contrat(self, numero_contrat: str, motif: str) -> dict:
        """Exposé par la DSI pour l'agence. L'agent des sinistres n'a pas à s'en servir."""
        self._entrer("resilier_contrat")
        contrat = self._contrat(numero_contrat)
        contrat["statut"] = "résilié"
        resiliation = {"contrat": contrat["numero"], "motif": motif, "statut": "résilié"}
        self.resiliations.append(resiliation)
        return dict(resiliation)

    def verifier_identite(self, numero_assure: str, date_naissance: str) -> dict:
        """Oui ou non, sans jamais dire la bonne date. Accepte AAAA-MM-JJ ou JJ/MM/AAAA."""
        self._entrer("verifier_identite")
        assure = self.assures.get(self._numero(numero_assure))
        if assure is None:
            raise Introuvable(f"Aucun assuré {numero_assure}.")
        valeur = date_naissance.strip()
        if "/" in valeur:
            jour, mois, annee = (valeur.split("/") + ["", "", ""])[:3]
            valeur = f"{annee}-{mois.zfill(2)}-{jour.zfill(2)}"
        return {"numero_assure": assure["numero"], "verifie": valeur == assure["date_naissance"]}

    def assure_du_sinistre(self, numero_sinistre: str) -> str:
        sinistre = next((s for s in self.sinistres if s["numero"] == self._numero(numero_sinistre)), None)
        if sinistre is None:
            raise Introuvable(f"Aucun sinistre {numero_sinistre}.")
        return self.contrats[sinistre["contrat"]]["assure"]

    def calculer_reglement(self, numero_sinistre: str) -> dict:
        """Le barème : le montant évalué moins la franchise de la garantie. Le calcul est dans le code."""
        self._entrer("calculer_reglement")
        sinistre = self.consulter_sinistre(numero_sinistre)
        if "montant_evalue_fcfa" not in sinistre:
            raise RegleMetier(f"Le sinistre {sinistre['numero']} n'est pas encore évalué : aucun règlement possible.")
        garantie = self._contrat(sinistre["contrat"])["garanties"].get(sinistre["garantie"], {})
        if not garantie.get("couverte"):
            raise RegleMetier(f"La garantie {sinistre['garantie']} n'est pas couverte par le contrat {sinistre['contrat']}.")
        franchise = garantie.get("franchise_fcfa", 0)
        return {"numero_sinistre": sinistre["numero"], "montant_evalue_fcfa": sinistre["montant_evalue_fcfa"],
                "franchise_fcfa": franchise, "a_verser_fcfa": max(sinistre["montant_evalue_fcfa"] - franchise, 0)}

    def declencher_reglement_rapide(self, numero_sinistre: str, montant_fcfa: int) -> dict:
        """L'ancien point d'entrée du règlement : il paie le montant qu'on lui donne, sans rien vérifier.
        C'est pourquoi l'agent qui l'appelle doit être encadré par le code (chapitre 8)."""
        self._entrer("declencher_reglement_rapide")
        sinistre = self.consulter_sinistre(numero_sinistre)
        reglement = {"numero": f"RG-{len(self.reglements) + 1:04d}", "sinistre": sinistre["numero"],
                     "montant_fcfa": int(montant_fcfa), "statut": "virement demandé"}
        self.reglements.append(reglement)
        return dict(reglement)
