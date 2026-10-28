"""Chapitre 13 : l'extraction d'un constat de l'archive, avec une confiance par champ.

L'outil est celui du chapitre 12 (schéma soigné), avec un objet de plus : la confiance de Claude dans
chaque champ, entre 0 et 1. Le type des documents de l'archive est connu : l'outil est imposé
(tool_choice de type « tool »), et la réflexion coupée, comme pour tous les constats (chapitre 3).

Trois versions du prompt, mises au point sur un échantillon avant le lot :
- v1 : les règles du chapitre 12 ;
- v2 : plus les règles tirées des erreurs de l'échantillon, dont « corrigez les confusions de
  numérisation dans les immatriculations ». Elle a fabriqué des plaques plausibles et fausses ;
- v3 : le modèle recopie les immatriculations telles qu'elles sont écrites, et le code les corrige selon
  la position (normaliser_plaque) ; les autres règles de la v2 restent ;
- v4 : la v3, plus l'ordre jour, mois, année des dates, trouvé en surveillant le lot de la v3.
"""

from ch12.extraire import noter_champs, valider
from ch12.schemas import REGLES, _objet, outils

MODELE = "claude-haiku-5-5"
MAX_TOKENS = 1200
CHAMPS = ["date_accident", "heure", "blesses", "plaque_a", "contrat_a", "plaque_b", "assureur_b"]


def outil() -> dict:
    constat = next(o for o in outils("soigne") if o["name"] == "extraire_constat")
    schema = {**constat["input_schema"]}
    proprietes = dict(schema["properties"])
    proprietes["confiance"] = _objet({c: {"type": "number", "description": "Entre 0 et 1"} for c in CHAMPS})
    return {**constat, "input_schema": _objet(proprietes)}


CONFIANCE = """

La confiance : pour chaque champ, donnez dans confiance un nombre entre 0 et 1, la probabilité que votre valeur soit juste, null compris. Baissez-la quand le document est abîmé, contradictoire ou abrégé."""

REGLES_V2 = """

Règles tirées des erreurs d'un échantillon de l'archive :
- une immatriculation suit le motif « AA 9999 AA » : deux lettres, quatre chiffres, deux lettres. Dans un document numérisé, 8 et B, 0 et O, 5 et S, 1 et I se confondent : corrigez selon la position. Un caractère illisible, comme « ? », rend l'immatriculation illisible : null ;
- l'heure est celle de la case Heure ; une heure donnée dans le récit ne la remplace pas ;
- si la case des blessés dit « non » mais que le récit parle d'une personne blessée ou qui souffre, les blessés valent « unclear » ;
- les assureurs du véhicule B s'écrivent en entier : Lagune Assurances, Atacora Garantie, Ouémé Mutuelle. Une abréviation qui désigne clairement l'un d'eux donne son nom complet."""


REGLES_V3 = """

Règles tirées des erreurs d'un échantillon de l'archive :
- recopiez chaque immatriculation telle qu'elle est écrite, séparateurs et confusions compris : le système la corrige lui-même. Si un caractère est illisible, comme « ? », l'immatriculation vaut null ;
- l'heure est celle de la case Heure ; une heure donnée dans le récit ne la remplace pas ;
- si la case des blessés dit « non » mais que le récit parle d'une personne blessée ou qui souffre, les blessés valent « unclear » ;
- les assureurs du véhicule B s'écrivent en entier : Lagune Assurances, Atacora Garantie, Ouémé Mutuelle. Une abréviation qui désigne clairement l'un d'eux donne son nom complet."""

# La v4 ajoute une règle trouvée en surveillant le lot de la v3 : les dates écrites avec trois nombres de deux
# chiffres (« 25-08-26 ») étaient lues année-mois-jour une fois sur dix, avec une confiance de 0,8 ou plus.
REGLES_V4 = REGLES_V3 + """
- les dates sont écrites jour, mois, année. Avec une année sur deux chiffres, « 25-08-26 » est le 25 août 2026, jamais le 26 août 2025."""

# Une immatriculation : deux lettres, quatre chiffres, deux lettres. Le code corrige les confusions de
# numérisation selon la position, ce que le modèle faisait mal (étape 2 du chapitre).
VERS_LETTRE = {"8": "B", "0": "O", "5": "S", "1": "I"}
VERS_CHIFFRE = {v: k for k, v in VERS_LETTRE.items()}


def normaliser_plaque(valeur: str | None) -> str | None:
    if valeur is None:
        return None
    brut = "".join(c for c in valeur.upper() if c.isalnum() or c == "?")
    if "?" in brut or len(brut) != 8:
        return None if "?" in brut else valeur
    p = [VERS_LETTRE.get(c, c) if i in (0, 1, 6, 7) else VERS_CHIFFRE.get(c, c) for i, c in enumerate(brut)]
    p = "".join(p)
    if not (p[:2].isalpha() and p[2:6].isdigit() and p[6:].isalpha()):
        return valeur
    return f"{p[:2]} {p[2:6]} {p[6:]}"


def normaliser(arguments: dict | None) -> dict | None:
    if arguments is None:
        return None
    a = json_copie(arguments)
    for v in ("vehicule_a", "vehicule_b"):
        if isinstance(a.get(v), dict):
            a[v]["plaque"] = normaliser_plaque(a[v].get("plaque"))
    return a


def json_copie(x):
    import json
    return json.loads(json.dumps(x))


def prompt(version: str) -> str:
    """Les règles du chapitre 12, ramenées aux constats : ni le choix d'outil, ni les factures."""
    avant, apres = ("Utilisez l'outil qui correspond au document ; un document qui n'est ni un constat, ni une facture, "
                    "ni un rapport d'expert va dans document_non_reconnu."), "Les documents sont des constats amiables de l'archive."
    coupure = "\n\nLes factures :"
    assert avant in REGLES and coupure in REGLES
    texte = REGLES.replace(avant, apres).split(coupure)[0]
    return texte + {"v1": "", "v2": REGLES_V2, "v3": REGLES_V3, "v4": REGLES_V4}[version] + CONFIANCE


def parametres(version: str, texte: str, modele: str = MODELE, cache: str = "prefixe") -> dict:
    """Les paramètres d'une requête, pour l'API synchrone comme pour un lot.

    cache : « prefixe », le point d'arrêt à la fin du prompt système, après l'outil : le préfixe commun à
    tous les documents. « automatique », le cache automatique du chapitre 10 : son point d'arrêt suit la fin
    du prompt, donc le document, différent à chaque requête ; mesuré au chapitre 13, il écrit à chaque
    requête et n'est jamais lu. None : sans cache."""
    systeme = prompt(version)
    if cache == "prefixe":
        systeme = [{"type": "text", "text": systeme, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    p = {"model": modele, "max_tokens": MAX_TOKENS, "system": systeme, "tools": [outil()],
         "messages": [{"role": "user", "content": f"Document :\n\n{texte}"}]}
    if cache == "automatique":
        p["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
    if modele == MODELE:
        p |= {"tool_choice": {"type": "tool", "name": "extraire_constat"}, "thinking": {"type": "disabled"}}
    else:
        # Sonnet 5.5 refuse le choix forcé (chapitre 6) et la réflexion coupée (chapitre 11) : un seul outil,
        # en « auto », et son réglage le plus bas.
        p |= {"tool_choice": {"type": "auto"}, "thinking": {"type": "between_tools"}}
    return p


def lire(message) -> dict | None:
    """Les arguments de l'appel d'outil, ou None si le message n'en contient pas."""
    contenu = message["content"] if isinstance(message, dict) else message.content
    for b in contenu:
        genre = b["type"] if isinstance(b, dict) else b.type
        if genre == "tool_use":
            return b["input"] if isinstance(b, dict) else b.input
    return None


def evaluer(document: dict, arguments: dict | None, corriger: bool = False) -> dict:
    """Les issues de chaque champ, les erreurs du contrôle, et la confiance déclarée. corriger : les plaques
    passent d'abord par normaliser_plaque."""
    if corriger:
        arguments = normaliser(arguments)
    if arguments is None:
        return {"reussi": False, "issues": {}, "erreurs": ["aucun appel d'outil"], "confiance": {}}
    requis = outil()["input_schema"]["required"]
    erreurs, _ = valider("extraire_constat", arguments, requis=requis)
    issues = noter_champs(document["verite"], "extraire_constat", arguments)
    issues.pop("type", None)
    confiance = arguments.get("confiance") or {}
    return {"reussi": not erreurs, "issues": issues, "erreurs": erreurs,
            "confiance": {c: confiance.get(c) for c in CHAMPS}}
