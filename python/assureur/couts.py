"""Convertir la consommation d'un appel (le champ usage) en dollars, en FCFA et en euros.

Prix relevés sur la page Pricing de platform.claude.com le 26 octobre 2026, en dollars par
million de tokens ; inchangés depuis les relevés du Tome 2 (19 et 22 octobre 2026).
Vérifiez-les avant de vous en servir : ils changent (annexe G, page d'accompagnement).
"""

from dataclasses import dataclass

from assureur import config


@dataclass(frozen=True)
class Tarif:
    entree: float          # tokens d'entrée hors cache
    ecriture_5m: float     # écriture dans le cache de 5 minutes
    ecriture_1h: float     # écriture dans le cache d'une heure
    lecture_cache: float   # lecture depuis le cache
    sortie: float          # tokens de sortie, réflexion comprise


TARIFS = {
    "claude-fable-5-1": Tarif(10.00, 12.50, 20.00, 0.25, 50.00),
    "claude-opus-5-5": Tarif(4.00, 5.00, 8.00, 0.20, 20.00),
    "claude-sonnet-5-5": Tarif(2.00, 2.50, 4.00, 0.10, 10.00),
    "claude-haiku-5-5": Tarif(0.10, 0.125, 0.20, 0.01, 0.50),
}

# Claude Haiku 5.5 coûte plus cher quand le prompt d'une requête dépasse 100 000 tokens.
SEUIL_LONG_PROMPT = 100_000
TARIFS_LONG_PROMPT = {
    "claude-haiku-5-5": Tarif(0.50, 0.625, 1.00, 0.05, 2.50),
}

# Message Batches API : 50 % de remise sur tous les postes (chapitre 13).
REMISE_LOT = 0.5


def tarif(modele: str, longueur_prompt: int = 0) -> Tarif:
    """Le tarif d'une requête, selon le modèle et la longueur de son prompt."""
    if modele not in TARIFS:
        raise ValueError(f"Prix inconnu pour le modèle {modele!r} : ajoutez-le dans TARIFS.")
    if longueur_prompt > SEUIL_LONG_PROMPT and modele in TARIFS_LONG_PROMPT:
        return TARIFS_LONG_PROMPT[modele]
    return TARIFS[modele]


def _lire(objet, nom, defaut=0):
    """Lit un champ, que l'usage vienne du SDK (objet) ou d'un JSON (dictionnaire)."""
    if objet is None:
        return defaut
    valeur = objet.get(nom) if isinstance(objet, dict) else getattr(objet, nom, None)
    return defaut if valeur is None else valeur


def francais(nombre: float, decimales: int) -> str:
    """0.0071 -> « 0,0071 » ; 12345.6 -> « 12 345,6 » : comme dans le livre."""
    texte = f"{nombre:,.{decimales}f}".replace(",", " ").replace(".", ",")
    return texte


@dataclass(frozen=True)
class Cout:
    dollars: float
    entree: int = 0
    ecriture_cache: int = 0
    lecture_cache: int = 0
    sortie: int = 0
    reflexion: int = 0

    @property
    def fcfa(self) -> float:
        return self.dollars * config.TAUX_FCFA

    @property
    def euros(self) -> float:
        return self.dollars * config.TAUX_EUR

    def __str__(self) -> str:
        return f"{francais(self.dollars, 4)} $ (≈ {francais(self.fcfa, 1)} FCFA ; {francais(self.euros, 4)} €)"


def cout_tokens(modele: str, entree: int, sortie: int) -> float:
    """Le coût en dollars d'une requête de `entree` tokens d'entrée (sans cache) et `sortie` tokens."""
    t = tarif(modele, entree)
    return (entree * t.entree + sortie * t.sortie) / 1_000_000


def cout_maximal(modele: str, tokens_entree: int, max_tokens: int) -> float:
    """Le coût le plus élevé possible d'un appel, avant de le lancer : l'entrée est connue
    (count_tokens, gratuit), la sortie ne dépassera pas max_tokens, réflexion comprise."""
    return cout_tokens(modele, tokens_entree, max_tokens)


def cout(modele: str, usage, lot: bool = False) -> Cout:
    """Le coût d'un appel, à partir de son champ usage. lot=True pour la Message Batches API."""
    entree = _lire(usage, "input_tokens")
    sortie = _lire(usage, "output_tokens")
    lecture = _lire(usage, "cache_read_input_tokens")
    ecriture = _lire(usage, "cache_creation_input_tokens")
    detail_ecriture = _lire(usage, "cache_creation", None)
    ecriture_1h = _lire(detail_ecriture, "ephemeral_1h_input_tokens")
    ecriture_5m = ecriture - ecriture_1h  # sans détail, tout est compté en 5 minutes
    reflexion = _lire(_lire(usage, "output_tokens_details", None), "thinking_tokens")

    # La longueur du prompt compte tous les tokens d'entrée, cache compris.
    t = tarif(modele, entree + lecture + ecriture)
    dollars = (
        entree * t.entree
        + ecriture_5m * t.ecriture_5m
        + ecriture_1h * t.ecriture_1h
        + lecture * t.lecture_cache
        + sortie * t.sortie  # output_tokens inclut déjà la réflexion
    ) / 1_000_000
    if lot:
        dollars *= REMISE_LOT
    return Cout(dollars, entree, ecriture, lecture, sortie, reflexion)
