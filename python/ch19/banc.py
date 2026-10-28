"""Chapitre 19 : le banc d'évaluation des comptes rendus, avec les annotations des médecins.

Trois usages :
- etalonner : le juge (Claude, sorties structurées) lit chaque compte rendu annoté de cliniques/etalonnage.py et
  dit s'il est fidèle aux notes ; on mesure son accord avec les annotations, par défaut. Les annotations sont
  fabriquées pour le livre (des références fidèles, et un seul changement connu par compte rendu fautif) ;
- ab : deux versions du prompt de rédaction, sur les vingt notes, plusieurs fois ; chaque compte rendu passe les
  contrôles du code (chapitre 18) et le juge étalonné ; l'hypothèse est écrite avant (ch19/hypothese.md) ;
- barriere : relit un fichier de résultats et refuse (code de sortie 1) une version qui passe le seuil. Gratuit :
  c'est l'étape que la chaîne d'intégration continue lance avant tout changement de prompt ou de modèle.

Lancement, depuis le dossier python/ :
    python -m ch19.banc etalonner --modele claude-haiku-5-5 --juges v1 v2 --repetitions 2 --budget-max 0.10
    python -m ch19.banc ab --juge-modele claude-haiku-5-5 --juge v2 --repetitions 3 --budget-max 0.40
    python -m ch19.banc barriere ch19/resultats/<fichier>.json --bras B --seuil 0.10       # gratuit
"""

import argparse
import json
import math
import statistics
import sys
import time
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import cout, francais
from assureur.journal import noter
from ch18.compte_rendu import OUTIL, PROMPTS as PROMPTS_18, choix_outil, controler, message
from cliniques.etalonnage import DEFAUTS, paires
from cliniques.notes import NOTES, note

DOSSIER = Path(__file__).parent
MAX_TOKENS = 1024
CHAPITRE = "19"         # le chapitre noté au journal ; le chapitre 22 réutilise le banc pour une migration

JUGE_V1 = """Vous relisez des comptes rendus de consultation, rédigés à partir des notes d'un médecin. Dites si le compte rendu est fidèle aux notes."""

JUGE_V2 = """Vous relisez un compte rendu de consultation, rédigé à partir des notes d'un médecin, avant que le médecin le valide. Comparez-le aux notes, phrase par phrase.

Le compte rendu est à corriger s'il :
- retire un doute du médecin (« probable », « possible », « suspicion », « à préciser ») ou le change en certitude ;
- change une condition en décision : « à confirmer si la douleur persiste » ne devient pas « contrôle prévu » ;
- donne une conclusion là où les notes n'en ont pas ;
- change un côté (droite, gauche), une durée ou un chiffre ;
- ajoute un examen, un soin ou un diagnostic que les notes ne contiennent pas ;
- omet une constatation des notes.

Une reformulation fidèle n'est pas un défaut : développer une abréviation, réordonner, écrire des phrases complètes. Le compte rendu est fidèle s'il ne fait aucune de ces erreurs."""

JUGES = {"v1": JUGE_V1, "v2": JUGE_V2}

SCHEMA_VERDICT = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["fidele", "a_corriger"]},
        "defauts": {"type": "array", "items": {"type": "string", "enum": DEFAUTS + ["autre"]}},
        "explication": {"type": "string"},
    },
    "required": ["verdict", "defauts", "explication"],
    "additionalProperties": False,
}

# Le bras B de l'essai : le prompt du chapitre 18, avec la fidélité du détail.
FIDELITE = """

La fidélité du détail :
- gardez chaque réserve dans la conclusion, avec la condition que le médecin a écrite : « à confirmer si la douleur persiste » reste une condition, jamais une décision de suivi ;
- recopiez exactement les côtés (droite, gauche), les durées et les chiffres ;
- gardez chaque constatation des notes, même brève."""

BRAS = {"A": PROMPTS_18["mission2"], "B": PROMPTS_18["mission2"] + FIDELITE}


def texte_cr(cr: dict) -> str:
    return (f"Motif : {cr.get('motif')}\nExamen : {cr.get('examen')}\n"
            f"Conclusion du médecin : {cr.get('conclusion_du_medecin') or 'aucune'}\nSuite : {cr.get('suite') or 'aucune'}")


def entree_du_juge(n: dict, entete: bool) -> str:
    """Ce que le juge lit des notes. Avec entete=True, exactement ce que le rédacteur a reçu (message(n)) : la
    spécialité, la clinique, le médecin et l'âge du patient compris. Sans l'en-tête (première version du banc),
    le juge prenait l'âge recopié par le rédacteur pour un ajout."""
    return message(n) if entete else f"Notes du médecin :\n{n['texte']}"


def juger(client, modele: str, version: str, n: dict, cr: dict, entete: bool = True) -> tuple[dict | None, float]:
    """Le verdict du juge, en sortie structurée (output_config.format)."""
    contenu = f"{entree_du_juge(n, entete)}\n\nCompte rendu à relire :\n{texte_cr(cr)}"
    r = client.messages.create(model=modele, max_tokens=MAX_TOKENS, system=JUGES[version],
                               output_config={"format": {"type": "json_schema", "schema": SCHEMA_VERDICT}},
                               messages=[{"role": "user", "content": contenu}])
    k = cout(modele, r.usage)
    noter(r.id, modele, k, chapitre=CHAPITRE, etape="juge", cas=f"{version}:{n['id']}")
    texte = "".join(b.text for b in r.content if b.type == "text")
    try:
        return json.loads(texte), k.dollars
    except json.JSONDecodeError:
        return None, k.dollars


# --- L'étalonnage -----------------------------------------------------------------------------------

def mesurer_accord(jugements: list[dict]) -> dict:
    """L'accord du juge avec les annotations : sensibilité sur les fautifs, spécificité sur les fidèles."""
    fautifs = [j for j in jugements if j["annotation"] == "a_corriger"]
    fideles = [j for j in jugements if j["annotation"] == "fidele"]
    vus = lambda js: sum(j["verdict"] == "a_corriger" for j in js)
    par_defaut = {}
    for d in DEFAUTS:
        js = [j for j in fautifs if j["defaut"] == d]
        if js:
            par_defaut[d] = f"{vus(js)} sur {len(js)}"
    lisibles = [j for j in jugements if j["verdict"] in ("fidele", "a_corriger")]
    durs = [j for j in jugements if j.get("difficile")]
    return {
        "difficiles": {"sensibilite": f"{vus([j for j in durs if j['annotation'] == 'a_corriger'])} sur "
                                      f"{sum(j['annotation'] == 'a_corriger' for j in durs)}",
                       "specificite": f"{sum(j['verdict'] == 'fidele' for j in durs if j['annotation'] == 'fidele')} sur "
                                      f"{sum(j['annotation'] == 'fidele' for j in durs)}"},
        "jugements": len(jugements),
        "illisibles": len(jugements) - len(lisibles),
        "accord": round(sum((j["verdict"] == j["annotation"]) for j in lisibles) / max(len(lisibles), 1), 3),
        "sensibilite": f"{vus(fautifs)} sur {len(fautifs)}",
        "specificite": f"{sum(j['verdict'] == 'fidele' for j in fideles)} sur {len(fideles)}",
        "par_defaut": par_defaut,
        "faux_negatifs": sorted({f"{j['note']}:{j['defaut']}" for j in fautifs if j["verdict"] != "a_corriger"}),
        "faux_positifs": sorted({j["note"] for j in fideles if j["verdict"] != "fidele"}),
    }


def etalonner(args) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    jugements, depense = [], 0.0
    for version in args.juges:
        for repetition in range(1, args.repetitions + 1):
            for p in paires():
                if args.budget_max - depense < 0.005:
                    print("Arrêt : plafond presque atteint.")
                    return {"jugements": jugements, "depense": depense}
                verdict, dollars = juger(client, args.modele, version, note(p["note"]), p["compte_rendu"],
                                         not args.sans_entete)
                depense += dollars
                jugements.append({"juge": version, "repetition": repetition, "note": p["note"],
                                  "annotation": p["annotation"], "defaut": p["defaut"], "difficile": p["difficile"],
                                  "verdict": (verdict or {}).get("verdict"), "defauts": (verdict or {}).get("defauts"),
                                  "explication": (verdict or {}).get("explication"), "cout_dollars": dollars})
    return {"jugements": jugements, "depense": depense}


def resumer_etalonnage(jugements: list[dict]) -> dict:
    return {v: {**mesurer_accord([j for j in jugements if j["juge"] == v]),
                "cout_total": round(sum(j["cout_dollars"] for j in jugements if j["juge"] == v), 6)}
            for v in dict.fromkeys(j["juge"] for j in jugements)}


# --- L'essai A/B ------------------------------------------------------------------------------------

def rediger(client, modele: str, systeme: str, n: dict) -> tuple[dict | None, float, int]:
    r = client.messages.create(model=modele, max_tokens=MAX_TOKENS, system=systeme, tools=[OUTIL],
                               tool_choice=choix_outil(modele), messages=[{"role": "user", "content": message(n)}])
    k = cout(modele, r.usage)
    noter(r.id, modele, k, chapitre=CHAPITRE, etape="redaction", cas=n["id"])
    bloc = next((b for b in r.content if b.type == "tool_use"), None)
    return (bloc.input if bloc else None), k.dollars, k.sortie


def essai_ab(args) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    comptes_rendus, depense = [], 0.0
    for repetition in range(1, args.repetitions + 1):
        for bras in args.bras:
            for n in NOTES:
                if args.budget_max - depense < 0.01:
                    print("Arrêt : plafond presque atteint.")
                    return {"comptes_rendus": comptes_rendus, "depense": depense}
                t0 = time.perf_counter()
                cr, d1, sortie = rediger(client, args.modele, BRAS[bras], n)
                verdict, d2 = juger(client, args.juge_modele, args.juge, n, cr, not args.sans_entete) if cr \
                    else (None, 0.0)
                depense += d1 + d2
                code = controler(n, cr)
                comptes_rendus.append({
                    "bras": bras, "note": n["id"], "repetition": repetition, "compte_rendu": cr,
                    "controles": code, "verdict": (verdict or {}).get("verdict"),
                    "defauts": (verdict or {}).get("defauts"), "explication": (verdict or {}).get("explication"),
                    "cout_redaction": d1, "cout_juge": d2, "tokens_sortie": sortie,
                    "latence_s": round(time.perf_counter() - t0, 2)})
                print(f"{bras} {n['id']} #{repetition} : juge {comptes_rendus[-1]['verdict']} "
                      f"{comptes_rendus[-1]['defauts']} ; code {[k for k, v in code.items() if v is True]}")
    return {"comptes_rendus": comptes_rendus, "depense": depense}


def rejuger(args) -> dict:
    """Les comptes rendus d'un essai, jugés de nouveau sans les réécrire (après une correction du banc)."""
    import anthropic
    client = anthropic.Anthropic()
    d = json.loads(Path(args.fichier).read_text(encoding="utf-8"))
    comptes_rendus, depense = [], 0.0
    for c in d["comptes_rendus"]:
        if args.budget_max - depense < 0.005:
            print("Arrêt : plafond presque atteint.")
            break
        n = note(c["note"])
        verdict, dollars = juger(client, args.juge_modele, args.juge, n, c["compte_rendu"], True) \
            if c["compte_rendu"] else (None, 0.0)
        depense += dollars
        comptes_rendus.append({**c, "verdict_premier_banc": c["verdict"], "defauts_premier_banc": c["defauts"],
                               "verdict": (verdict or {}).get("verdict"), "defauts": (verdict or {}).get("defauts"),
                               "explication": (verdict or {}).get("explication"), "cout_juge": dollars,
                               "cout_redaction": 0.0, "cout_redaction_initial": c["cout_redaction"]})
    return {"comptes_rendus": comptes_rendus, "depense": depense, "source": args.fichier}


def a_corriger(c: dict) -> bool:
    """Un compte rendu est à corriger si le juge le dit, ou si un contrôle du code le signale."""
    k = c.get("controles") or {}
    return c.get("verdict") != "fidele" or any(k.get(x) for x in ("conclusion_inventee", "reserve_perdue",
                                                                    "conclusion_omise")) or bool(k.get("ajouts"))


def wilson(succes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = succes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    marge = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(max(0.0, centre - marge), 3), round(min(1.0, centre + marge), 3))


def fisher_bilateral(a: int, n1: int, b: int, n2: int) -> float:
    """Le test exact de Fisher, bilatéral, sur deux proportions (a sur n1 contre b sur n2)."""
    total, k = n1 + n2, a + b
    proba = lambda x: math.comb(n1, x) * math.comb(n2, k - x) / math.comb(total, k)
    observe = proba(a)
    return round(min(1.0, sum(proba(x) for x in range(max(0, k - n2), min(k, n1) + 1)
                              if proba(x) <= observe * (1 + 1e-9))), 4)


def taille_par_bras(p1: float, p2: float, alpha_z: float = 1.96, puissance_z: float = 0.8416) -> int:
    """La taille par bras pour voir p1 contre p2 (approximation normale, alpha 5 % bilatéral, puissance 80 %)."""
    pm = (p1 + p2) / 2
    n = (alpha_z * math.sqrt(2 * pm * (1 - pm)) + puissance_z * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2 \
        / (p1 - p2) ** 2
    return math.ceil(n)


def resumer_ab(comptes_rendus: list[dict]) -> dict:
    resume = {}
    for bras in dict.fromkeys(c["bras"] for c in comptes_rendus):
        cs = [c for c in comptes_rendus if c["bras"] == bras]
        k = sum(a_corriger(c) for c in cs)
        defauts = {}
        for c in cs:
            for d in c.get("defauts") or []:
                defauts[d] = defauts.get(d, 0) + 1
        resume[bras] = {
            "comptes_rendus": len(cs), "a_corriger": k, "part": round(k / len(cs), 3), "intervalle_95": wilson(k, len(cs)),
            "par_le_juge": sum(c.get("verdict") == "a_corriger" for c in cs),
            "par_le_code": sum(any((c.get("controles") or {}).get(x) for x in ("conclusion_inventee", "reserve_perdue",
                                                                              "conclusion_omise"))
                               or bool((c.get("controles") or {}).get("ajouts")) for c in cs),
            "defauts_du_juge": dict(sorted(defauts.items(), key=lambda x: -x[1])),
            "notes_a_corriger": dict(sorted({n: sum(a_corriger(c) for c in cs if c["note"] == n)
                                             for n in dict.fromkeys(c["note"] for c in cs)}.items())),
            "cout_redaction_moyen": round(statistics.mean(c["cout_redaction"] for c in cs), 6),
            "cout_juge_moyen": round(statistics.mean(c["cout_juge"] for c in cs), 6),
        }
    if "A" in resume and "B" in resume:
        a, b = resume["A"], resume["B"]
        resume["comparaison"] = {"ecart_points": round(100 * (b["part"] - a["part"]), 1),
                                 "fisher_p": fisher_bilateral(a["a_corriger"], a["comptes_rendus"],
                                                              b["a_corriger"], b["comptes_rendus"])}
    return resume


def barriere(fichier: str, bras: str, seuil: float) -> int:
    d = json.loads(Path(fichier).read_text(encoding="utf-8"))
    cs = [c for c in d["comptes_rendus"] if c["bras"] == bras]
    part = sum(a_corriger(c) for c in cs) / max(len(cs), 1)
    inventees = sum((c.get("controles") or {}).get("conclusion_inventee", False) for c in cs)
    ok = part <= seuil and inventees == 0
    print(f"Bras {bras} : {part:.1%} à corriger (seuil {seuil:.0%}), {inventees} conclusion(s) inventée(s) : "
          + ("accepté" if ok else "refusé"))
    return 0 if ok else 1


def ecrire(nom: str, donnees: dict) -> Path:
    sortie = DOSSIER / "resultats" / f"{nom}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    return sortie


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 19 : le banc d'évaluation des comptes rendus.")
    sous = parser.add_subparsers(dest="mode", required=True)
    e = sous.add_parser("etalonner")
    e.add_argument("--modele", default="claude-haiku-5-5")
    e.add_argument("--juges", nargs="+", choices=list(JUGES), default=["v1", "v2"])
    e.add_argument("--repetitions", type=int, default=1)
    e.add_argument("--budget-max", type=float, default=0.10)
    e.add_argument("--sans-entete", action="store_true", help="la première version du banc : les notes seules")
    j = sous.add_parser("rejuger")
    j.add_argument("fichier")
    j.add_argument("--juge-modele", default="claude-haiku-5-5")
    j.add_argument("--juge", choices=list(JUGES), default="v2")
    j.add_argument("--budget-max", type=float, default=0.10)
    a = sous.add_parser("ab")
    a.add_argument("--modele", default="claude-haiku-5-5", help="le modèle qui rédige")
    a.add_argument("--juge-modele", default="claude-haiku-5-5")
    a.add_argument("--juge", choices=list(JUGES), default="v2")
    a.add_argument("--bras", nargs="+", choices=list(BRAS), default=["A", "B"])
    a.add_argument("--repetitions", type=int, default=3)
    a.add_argument("--budget-max", type=float, default=0.40)
    a.add_argument("--sans-entete", action="store_true", help="la première version du banc : les notes seules")
    b = sous.add_parser("barriere")
    b.add_argument("fichier")
    b.add_argument("--bras", default="B")
    b.add_argument("--seuil", type=float, default=0.10)
    r = sous.add_parser("reevaluer")
    r.add_argument("fichier")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")

    if args.mode == "barriere":
        sys.exit(barriere(args.fichier, args.bras, args.seuil))
    if args.mode == "reevaluer":
        d = json.loads(Path(args.fichier).read_text(encoding="utf-8"))
        print(json.dumps(resumer_etalonnage(d["jugements"]) if "jugements" in d else resumer_ab(d["comptes_rendus"]),
                         ensure_ascii=False, indent=2))
        return
    if args.mode == "etalonner":
        r = etalonner(args)
        resume = resumer_etalonnage(r["jugements"])
        sortie = ecrire(f"etalonnage-{args.modele.removeprefix('claude-')}",
                        {"date": date.today().isoformat(), "modele": args.modele, "juges": args.juges,
                         "repetitions": args.repetitions, "depense_dollars": round(r["depense"], 6),
                         "resume": resume, "jugements": r["jugements"]})
    elif args.mode == "rejuger":
        r = rejuger(args)
        resume = resumer_ab(r["comptes_rendus"])
        sortie = ecrire("ab-rejuge", {"date": date.today().isoformat(), "source": r["source"],
                                      "juge_modele": args.juge_modele, "juge": args.juge, "entete": True,
                                      "depense_dollars": round(r["depense"], 6), "resume": resume,
                                      "comptes_rendus": r["comptes_rendus"]})
    else:
        r = essai_ab(args)
        resume = resumer_ab(r["comptes_rendus"])
        sortie = ecrire("ab", {"date": date.today().isoformat(), "modele": args.modele, "juge_modele": args.juge_modele,
                               "juge": args.juge, "repetitions": args.repetitions,
                               "depense_dollars": round(r["depense"], 6), "resume": resume,
                               "comptes_rendus": r["comptes_rendus"]})
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense : {francais(r['depense'], 4)} $ (≈ {francais(r['depense'] * config.TAUX_FCFA, 1)} FCFA) ; {sortie}")


if __name__ == "__main__":
    principal()
