"""Chapitre 14 : l'édition 2027 des conditions automobiles, fabriquée à partir de l'édition 2026.

La direction juridique de Kanvô Assurances publie une nouvelle édition des conditions générales et du
tableau des garanties automobiles, applicable aux sinistres survenus à partir du 1er janvier 2027. Le
script la fabrique en appliquant à l'édition 2026 la liste des changements ci-dessous : c'est le panneau
de l'étape 6 du chapitre, l'index qu'on n'a pas reconstruit. Il est déterministe.

Lancement, depuis le dossier python/ :  python -m ch14.edition_2027
"""

from pathlib import Path

DOSSIER = Path(__file__).parent / "documents"

CHANGEMENTS = {
    "cg-auto": [
        ("édition 2026 — référence CG-AUTO-2026.", "édition 2027 — référence CG-AUTO-2027."),
        ("Applicables aux sinistres survenus du 1er janvier 2026 au 31 décembre 2026.",
         "Applicables aux sinistres survenus à partir du 1er janvier 2027."),
        ("dans la limite de 50 kilomètres", "dans la limite de 100 kilomètres"),
        ("le vol commis alors que les clés étaient sur le véhicule ou à l'intérieur ;",
         "le vol commis alors que les clés étaient sur le véhicule ou à l'intérieur ; le vol commis alors que la "
         "carte grise était laissée dans le véhicule ;"),
        ("En cas de vol, ce délai est réduit à deux jours ouvrés.", "En cas de vol, ce délai est réduit à trois jours ouvrés."),
        ("plafonnée à 50 %", "plafonnée à 40 %"),
    ],
    "tableau-auto": [
        ("édition 2026 — référence TG-AUTO-2026.", "édition 2027 — référence TG-AUTO-2027."),
        ("Applicable aux sinistres survenus du 1er janvier 2026 au 31 décembre 2026, avec les conditions générales CG-AUTO-2026.",
         "Applicable aux sinistres survenus à partir du 1er janvier 2027, avec les conditions générales CG-AUTO-2027."),
        ("| Bris de glace | En option, franchise 15 000 | Non couverte | Comprise, franchise 15 000 |",
         "| Bris de glace | En option, franchise 25 000 | Non couverte | Comprise, franchise 25 000 |"),
        ("| Vol | Comprise, franchise 75 000 |", "| Vol | Comprise, franchise 100 000 |"),
        ("Comprise, remorquage 50 km", "Comprise, remorquage 100 km"),
    ],
}


def fabriquer() -> dict[str, str]:
    textes = {}
    for nom, changements in CHANGEMENTS.items():
        texte = (DOSSIER / f"{nom}-2026.md").read_text(encoding="utf-8")
        for avant, apres in changements:
            assert texte.count(avant) == 1, f"{nom} : « {avant[:50]} » doit apparaître une fois"
            texte = texte.replace(avant, apres)
        textes[f"{nom}-2027.md"] = texte
    return textes


if __name__ == "__main__":
    for nom, texte in fabriquer().items():
        (DOSSIER / nom).write_text(texte, encoding="utf-8", newline="\n")
        print(f"Écrit : {nom}")
