"""Chapitre 17 : la revue automatique des demandes de fusion, par Claude Code en mode non interactif.

Les revues se lancent comme dans une chaîne d'intégration continue : le Claude Code qu'embarque le Claude Agent
SDK, en ligne de commande, avec -p, --output-format json et --json-schema, le diff sur l'entrée standard, les
outils de lecture seulement (--permission-mode dontAsk). Le dépôt relu est une copie de l'ancien logiciel avec
la configuration d'équipe du chapitre 15, dans l'état de la demande de fusion.

Deux demandes de fusion, fictives, écrites pour le livre (ch17/demandes/) :
- moto : la branche moto, avec cinq défauts posés exprès (ch17/defauts.json, jamais montré à Claude) ;
- echeancier : la correction du ticket DSI-2026-031 et ses tests, sans défaut posé.

Quatre mesures :
- criteres : la même revue avec une consigne vague, une consigne « prudente », ou les critères écrits dans le
  CLAUDE.md du dépôt ;
- passes : une passe par fichier, puis une passe d'intégration, contre une seule passe ;
- relance : après un deuxième commit qui corrige deux défauts, la revue relancée avec ou sans ses constats
  précédents ;
- autorevue : la séance qui a écrit la majoration du chapitre 15 relit son propre changement, contre une
  instance indépendante qui relit le même diff.

Lancement, depuis le dossier python/ :
    python -m ch17.revue --mesures criteres --repetitions 3 --budget-max 0.40
    python -m ch17.revue --reevaluer ch17/resultats/<fichier>.json   # gratuit : relit sans rien relancer
"""

import argparse
import asyncio
import difflib
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from assureur import config
from assureur.couts import Cout, francais
from assureur.journal import noter
from ch15 import seances as ch15
from ch15.seances import ANCIEN, empreinte, recalculer
from ch16.seances import EQUIPE, LECTURE, normaliser

DOSSIER = Path(__file__).parent
DEMANDES = DOSSIER / "demandes"
DEFAUTS = json.loads((DOSSIER / "defauts.json").read_text(encoding="utf-8"))
MODELE = "claude-haiku-5-5"
GARDE_FOU = 25


def claude_embarque() -> Path:
    """Le Claude Code qu'embarque claude-agent-sdk (et non celui du poste, peut-être d'une autre version)."""
    import claude_agent_sdk
    dossier = Path(claude_agent_sdk.__file__).parent / "_bundled"
    return dossier / ("claude.exe" if os.name == "nt" else "claude")


CATEGORIES = ["bogue", "securite", "conception", "style", "autre"]
SCHEMA = {
    "type": "object",
    "properties": {"constats": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "fichier": {"type": "string"},
            "ligne": {"type": "integer"},
            "categorie": {"type": "string", "enum": CATEGORIES},
            "gravite": {"type": "string", "enum": ["bloquant", "a_corriger", "remarque"]},
            "description": {"type": "string"},
            "detected_pattern": {"type": "string", "description": "le motif de code qui a déclenché le constat"},
            "confiance": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["fichier", "ligne", "categorie", "gravite", "description", "detected_pattern", "confiance"],
    }}},
    "required": ["constats"],
}
SCHEMA_RELANCE = json.loads(json.dumps(SCHEMA))
SCHEMA_RELANCE["properties"]["constats"]["items"]["properties"]["statut"] = {
    "type": "string", "enum": ["nouveau", "toujours_ouvert"]}
SCHEMA_RELANCE["properties"]["constats"]["items"]["required"].append("statut")

# Les critères de revue de l'équipe, ajoutés au CLAUDE.md du dépôt pour les revues « avec critères ».
CRITERES = """
## Revue automatique des demandes de fusion

Signalez seulement, dans le code que la demande ajoute ou modifie, et dans ce qu'il rend faux ailleurs :
- un nouveau montant qui ne passe pas par `arrondir_fcfa()` ;
- une requête SQL construite avec `%` ou par concaténation, au lieu de paramètres `?` ;
- un taux ou un barème écrit dans le code au lieu d'être lu dans `tarifs/`, ou un fichier de `tarifs/` modifié ;
- une erreur de logique : une borne, une condition, un cas oublié ;
- un endroit du logiciel, hors des fichiers modifiés, que le changement rend incohérent.

Ne signalez pas :
- le style, les noms, les commentaires, la mise en forme ;
- les motifs anciens du logiciel que le code nouveau reprend sans risque (`== None`, `options=[]`, `except:`) ;
- les arrondis existants, hors du changement : leur correction attend un ticket (DSI-2019-114).

Gravité : `bloquant` quand un montant, une donnée ou la sécurité devient faux ; `a_corriger` sinon.
Pour chaque constat, `detected_pattern` cite le motif de code qui l'a déclenché, par exemple `return int(p)`.
"""

# La version 2, après la première revue d'essai : la règle des montants visait aussi des calculs exacts
# (`prime_annuelle // n`, un entier divisé par un entier). Elle ne vise plus que les calculs en virgule flottante.
CRITERES_V2 = CRITERES.replace(
    "- un nouveau montant qui ne passe pas par `arrondir_fcfa()` ;\n",
    "- un nouveau montant calculé en virgule flottante (division `/`, multiplication par un taux décimal) qui ne\n"
    "  passe pas par `arrondir_fcfa()` ; un calcul en entiers (`//`, `%`, une somme d'entiers) n'en a pas besoin ;\n")

ENTETE = {
    "moto": "Demande de fusion n° 214 : branche moto (note de l'actuariat n° 2026-21).",
    "echeancier": "Demande de fusion n° 209 : total des quittances égal à la prime (ticket DSI-2026-031).",
}
VAGUE = "Relisez la demande de fusion dont le diff arrive sur l'entrée standard, et signalez les problèmes."
PRUDENTE = VAGUE + " Ne signalez que les problèmes dont vous êtes sûr, avec une confiance élevée."
AVEC_CRITERES = ("Relisez la demande de fusion dont le diff arrive sur l'entrée standard, selon les critères "
                 "de revue du CLAUDE.md.")
PAR_FICHIER = ("Relisez ce fichier de la demande de fusion, dont le diff arrive sur l'entrée standard, selon les "
               "critères de revue du CLAUDE.md. Ne relevez que ce qui se voit dans ce fichier.")
INTEGRATION = ("Relisez la demande de fusion entière, dont le diff arrive sur l'entrée standard, selon les "
               "critères de revue du CLAUDE.md, mais seulement pour ce qui ne se voit qu'entre plusieurs fichiers : "
               "un appel, une liste, une donnée qui passe d'un fichier à l'autre, un endroit que le changement "
               "rend incohérent. Les constats propres à un seul fichier sont déjà relevés.")
RELANCE = ("Relisez la demande de fusion dont le diff arrive sur l'entrée standard, selon les critères de revue du "
           "CLAUDE.md. Un deuxième commit est arrivé depuis la revue précédente, dont voici les constats :\n\n"
           "{precedents}\n\nNe rendez que les constats nouveaux, ou ceux de la revue précédente qui sont toujours "
           "ouverts ; marquez chacun « nouveau » ou « toujours_ouvert ». Ne reprenez pas un constat corrigé.")
AUTOREVUE = ("Relisez maintenant le changement que vous venez de faire, comme le ferait la revue de l'équipe, "
             "selon ces critères :\n{criteres}\nRendez vos constats.")
INDEPENDANTE = ("Relisez le changement de primes/calcul.py dont le diff est ci-dessous, comme le ferait la revue de "
                "l'équipe, selon ces critères :\n{criteres}\nRendez vos constats.\n\n{diff}")

MESURES = {
    "criteres": ["vague", "prudente", "criteres", "criteres_v2"],
    "passes": ["une_passe", "par_fichier"],
    "relance": ["sans", "avec"],
    "autorevue": ["meme_seance", "independante"],
}


@dataclass
class Revue:
    mesure: str
    variante: str
    demande: str
    repetition: int
    fin: str = "exception"
    appels: int = 0                 # appels à Claude Code (une passe par fichier en fait plusieurs)
    tours: int = 0
    cout_dollars: float = 0.0       # total_cost_usd, estimé par Claude Code
    cout_recalcule: float = 0.0
    model_usage: dict = field(default_factory=dict)
    structures: int = 0             # appels qui ont rendu un structured_output valide
    constats: list[dict] = field(default_factory=list)
    defauts_trouves: list[str] = field(default_factory=list)
    hors_defauts: int = 0           # constats qui ne visent aucun défaut posé
    precedents: list[dict] = field(default_factory=list)   # relance : les constats du premier commit
    controles: dict = field(default_factory=dict)
    version: str = ""
    latence_s: float = 0.0
    erreur: str | None = None


# --- Les dépôts et les diffs ------------------------------------------------------------------------

def _fichiers_code(dossier: Path) -> dict[str, str]:
    return {p.relative_to(dossier).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(dossier.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def diff_demande(base: Path, demande: Path) -> str:
    """Le diff de la demande : chaque fichier de la demande comparé à celui de la base (absent s'il est nouveau)."""
    morceaux = []
    for chemin, nouveau in _fichiers_code(demande).items():
        ancien = (base / chemin).read_text(encoding="utf-8") if (base / chemin).exists() else ""
        if ancien == nouveau:
            continue
        lignes = difflib.unified_diff(ancien.splitlines(), nouveau.splitlines(),
                                      "/dev/null" if not ancien else f"a/{chemin}", f"b/{chemin}", lineterm="", n=3)
        morceaux.append(f"diff --git a/{chemin} b/{chemin}\n" + "\n".join(lignes))
    return "\n".join(morceaux) + "\n"


def fichiers_modifies(base: Path, demande: Path) -> list[str]:
    return [c for c, t in _fichiers_code(demande).items()
            if not (base / c).exists() or (base / c).read_text(encoding="utf-8") != t]


def preparer(dossier: Path, demandes: list[Path], criteres: str | None) -> tuple[Path, Path]:
    """La copie du dépôt dans l'état des demandes (superposées dans l'ordre), et un dossier personnel vide."""
    depot = dossier / "depot"
    shutil.copytree(ANCIEN, depot, ignore=shutil.ignore_patterns("__pycache__", "*.db"))
    shutil.copytree(EQUIPE, depot, dirs_exist_ok=True)
    for d in demandes:
        shutil.copytree(d, depot, dirs_exist_ok=True)
    if criteres:
        with open(depot / "CLAUDE.md", "a", encoding="utf-8") as f:
            f.write(criteres)
    personnel = dossier / "personnel"
    personnel.mkdir()
    return depot, personnel


# --- Les constats et les défauts --------------------------------------------------------------------

def vise(constat: dict, defaut: dict) -> bool:
    fichier = normaliser(str(constat.get("fichier", ""))).replace("\\", "/")
    texte = normaliser(" ".join(str(constat.get(k, "")) for k in ("description", "detected_pattern")))
    return any(fichier.endswith(f) for f in defaut["fichiers"]) and any(m in texte for m in defaut["mots"])


def rapprocher(constats: list[dict], demande: str) -> tuple[list[str], int]:
    """Les défauts posés que les constats visent, et le nombre de constats qui n'en visent aucun."""
    defauts = DEFAUTS.get(demande, [])
    trouves = [d["id"] for d in defauts if any(vise(c, d) for c in constats)]
    hors = sum(not any(vise(c, d) for d in defauts) for c in constats)
    return trouves, hors


# --- Les appels -------------------------------------------------------------------------------------

def _ajouter_usage(r: Revue, usage: dict) -> None:
    for nom, u in (usage or {}).items():
        total = r.model_usage.setdefault(nom, {})
        for k, v in u.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                total[k] = total.get(k, 0) + v


def appeler(r: Revue, prompt: str, entree: str, depot: Path, personnel: Path, modele: str, budget: float,
            schema: dict = SCHEMA) -> list[dict] | None:
    """Un appel de Claude Code en mode non interactif, comme dans la chaîne d'intégration continue."""
    commande = [str(claude_embarque()), "-p", prompt, "--output-format", "json", "--json-schema", json.dumps(schema),
                "--model", modele, "--permission-mode", "dontAsk", "--permission-prompts", "none",
                "--allowedTools", ",".join(LECTURE), "--max-turns", str(GARDE_FOU),
                "--max-budget-usd", f"{max(budget, 0.01):.4f}"]
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(personnel), "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
    r.appels += 1
    sortie = subprocess.run(commande, cwd=depot, input=entree, capture_output=True, text=True, encoding="utf-8",
                            timeout=900, env=env)
    try:
        d = json.loads(sortie.stdout)
    except json.JSONDecodeError:
        r.erreur = (sortie.stderr.strip().splitlines() or ["sortie illisible"])[-1][:300]
        return None
    r.fin = d.get("subtype", r.fin) if not d.get("is_error") else f"erreur:{d.get('subtype')}"
    r.tours += d.get("num_turns", 0) or 0
    r.cout_dollars += d.get("total_cost_usd", 0.0) or 0.0
    _ajouter_usage(r, d.get("modelUsage", {}))
    r.cout_recalcule = recalculer(r.model_usage)
    noter(None, modele, Cout(d.get("total_cost_usd", 0.0) or 0.0), chapitre="17", etape="revue",
          cas=f"{r.mesure}:{r.variante}:{r.demande}", seance=d.get("session_id"), subtype=d.get("subtype"),
          tours=d.get("num_turns"), cout_sdk=d.get("total_cost_usd"))
    so = d.get("structured_output")
    if isinstance(so, dict) and isinstance(so.get("constats"), list):
        r.structures += 1
        return so["constats"]
    r.erreur = r.erreur or "pas de structured_output"
    return None


def version() -> str:
    try:
        return subprocess.run([str(claude_embarque()), "--version"], capture_output=True, text=True,
                              timeout=60).stdout.strip()
    except Exception as e:
        return f"inconnue ({type(e).__name__})"


def _conclure(r: Revue, demande: str) -> None:
    r.defauts_trouves, r.hors_defauts = rapprocher(r.constats, demande)


def revue_simple(variante: str, demande: str, repetition: int, modele: str, budget: float,
                 mesure: str = "criteres") -> Revue:
    """Une revue en une passe : vague, prudente, ou avec les critères du CLAUDE.md."""
    r = Revue(mesure, variante, demande, repetition)
    dossier = Path(tempfile.mkdtemp(prefix="kanvo-ch17-"))
    debut = time.perf_counter()
    try:
        texte = {"vague": None, "prudente": None, "criteres": CRITERES}.get(variante, CRITERES_V2)
        depot, personnel = preparer(dossier, [DEMANDES / demande], texte)
        entree = ENTETE[demande] + "\n\n" + diff_demande(ANCIEN, DEMANDES / demande)
        prompt = {"vague": VAGUE, "prudente": PRUDENTE}.get(variante, AVEC_CRITERES)
        r.constats = appeler(r, prompt, entree, depot, personnel, modele, budget) or []
        _conclure(r, demande)
    finally:
        r.latence_s = round(time.perf_counter() - debut, 1)
        shutil.rmtree(dossier, ignore_errors=True)
    return r


def revue_par_fichier(demande: str, repetition: int, modele: str, budget: float) -> Revue:
    """Une passe par fichier modifié, puis une passe d'intégration sur tout le diff."""
    r = Revue("passes", "par_fichier", demande, repetition)
    dossier = Path(tempfile.mkdtemp(prefix="kanvo-ch17-"))
    debut = time.perf_counter()
    try:
        depot, personnel = preparer(dossier, [DEMANDES / demande], CRITERES_V2)
        source = DEMANDES / demande
        for chemin in fichiers_modifies(ANCIEN, source):
            if budget - r.cout_dollars < 0.01:
                break
            seul = dossier / "seul"
            shutil.rmtree(seul, ignore_errors=True)
            (seul / chemin).parent.mkdir(parents=True)
            shutil.copy(source / chemin, seul / chemin)
            constats = appeler(r, PAR_FICHIER, ENTETE[demande] + "\n\n" + diff_demande(ANCIEN, seul), depot,
                               personnel, modele, budget - r.cout_dollars) or []
            r.constats += [{**c, "passe": chemin} for c in constats]
        if budget - r.cout_dollars >= 0.01:
            constats = appeler(r, INTEGRATION, ENTETE[demande] + "\n\n" + diff_demande(ANCIEN, source), depot,
                               personnel, modele, budget - r.cout_dollars) or []
            r.constats += [{**c, "passe": "integration"} for c in constats]
        _conclure(r, demande)
    finally:
        r.latence_s = round(time.perf_counter() - debut, 1)
        shutil.rmtree(dossier, ignore_errors=True)
    return r


def deuxieme_commit(dossier: Path) -> Path:
    """La demande moto après un deuxième commit, qui corrige D1 (arrondi) et D3 (requête SQL)."""
    v2 = dossier / "moto-v2"
    shutil.copytree(DEMANDES / "moto", v2)
    calcul = v2 / "primes" / "calcul.py"
    t = calcul.read_text(encoding="utf-8")
    t = t.replace("from primes import tarifs\n", "from primes import tarifs\nfrom util.montants import arrondir_fcfa\n", 1)
    t = t.replace("        p = p + t['OPTION_CASQUE_PASSAGER']\n    return int(p)\n",
                  "        p = p + t['OPTION_CASQUE_PASSAGER']\n    return arrondir_fcfa(p)\n", 1)
    calcul.write_text(t, encoding="utf-8", newline="\n")
    requetes = v2 / "base" / "requetes.py"
    t = requetes.read_text(encoding="utf-8")
    t = t.replace("""    return lire("SELECT * FROM contrats WHERE branche = 'MOTO' AND parametres LIKE '%%cylindree=%d%%'" % cylindree_min)""",
                  """    return lire("SELECT * FROM contrats WHERE branche = 'MOTO' AND parametres LIKE ?",
                ('%cylindree=' + str(cylindree_min) + '%',))""", 1)
    requetes.write_text(t, encoding="utf-8", newline="\n")
    return v2


CORRIGES = ["D1", "D3"]  # les défauts que le deuxième commit corrige


def controles_relance(r: Revue) -> dict:
    """Ce que la CI publierait après la relance, d'après les constats du premier commit (r.precedents)."""
    ouverts = [d for d in DEFAUTS["moto"] if d["id"] not in CORRIGES]
    corriges = [d for d in DEFAUTS["moto"] if d["id"] in CORRIGES]
    deja = set(rapprocher(r.precedents, "moto")[0])
    publies = [c for c in r.constats if c.get("statut", "nouveau") == "nouveau"]
    return {
        # un constat sur un défaut corrigé, qui ne vise aucun défaut encore ouvert : la CI le publierait à tort
        # (D6, toujours là, parle aussi du « % » de la requête : un constat sur D6 n'est pas un constat sur D3)
        "sur_corriges": sum(any(vise(c, d) for d in corriges) and not any(vise(c, d) for d in ouverts)
                            for c in r.constats),
        # un constat publié comme nouveau sur un défaut ouvert déjà signalé au premier commit : un doublon
        "doublons": sum(any(vise(c, d) for d in ouverts if d["id"] in deja) for c in publies),
        "publies": len(publies),
        "toujours_ouverts": sum(c.get("statut") == "toujours_ouvert" for c in r.constats),
    }


def relance(repetition: int, modele: str, budget: float, variantes: list[str]) -> list[Revue]:
    """La revue du premier commit, puis celle du deuxième, sans ou avec les constats du premier."""
    revues = []
    dossier = Path(tempfile.mkdtemp(prefix="kanvo-ch17-relance-"))
    try:
        premiere = Revue("relance", "premier_commit", "moto", repetition)
        t0 = time.perf_counter()
        depot, personnel = preparer(dossier / "c1", [DEMANDES / "moto"], CRITERES_V2)
        premiere.constats = appeler(premiere, AVEC_CRITERES, ENTETE["moto"] + "\n\n" +
                                    diff_demande(ANCIEN, DEMANDES / "moto"), depot, personnel, modele, budget) or []
        _conclure(premiere, "moto")
        premiere.latence_s = round(time.perf_counter() - t0, 1)
        revues.append(premiere)
        v2 = deuxieme_commit(dossier)
        entree = ENTETE["moto"] + "\n\n" + diff_demande(ANCIEN, v2)
        depense = premiere.cout_dollars
        for variante in variantes:
            if budget - depense < 0.01:
                break
            r = Revue("relance", variante, "moto", repetition, precedents=premiere.constats)
            t0 = time.perf_counter()
            depot, personnel = preparer(dossier / variante, [v2], CRITERES_V2)
            if variante == "avec":
                precedents = json.dumps([{k: c.get(k) for k in ("fichier", "ligne", "description")}
                                         for c in premiere.constats], ensure_ascii=False, indent=1)
                r.constats = appeler(r, RELANCE.format(precedents=precedents), entree, depot, personnel, modele,
                                     budget - depense, SCHEMA_RELANCE) or []
            else:
                r.constats = appeler(r, AVEC_CRITERES, entree, depot, personnel, modele, budget - depense) or []
            _conclure(r, "moto")
            r.controles = controles_relance(r)
            r.latence_s = round(time.perf_counter() - t0, 1)
            depense += r.cout_dollars
            revues.append(r)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
    return revues


async def autorevue(repetition: int, modele: str, budget: float, variantes: list[str]) -> list[Revue]:
    """La majoration du chapitre 15 écrite sur le poste de Mme Adanlé, puis relue par la même séance ou par une autre."""
    from claude_agent_sdk import ResultMessage, query
    revues = []
    dossier = Path(tempfile.mkdtemp(prefix="kanvo-ch17-autorevue-"))
    try:
        journal = dossier / "instructions.jsonl"
        depot, personnel = ch15.preparer("nouveau", dossier, journal)
        avant = (depot / "primes" / "calcul.py").read_text(encoding="utf-8")
        ecriture = Revue("autorevue", "ecriture", "majoration", repetition)
        t0 = time.perf_counter()
        session = None

        async def interroger(r: Revue, prompt: str, resume: str | None, schema: dict | None) -> str | None:
            options = ch15.options(depot, personnel, modele, budget - sum(x.cout_dollars for x in revues) - r.cout_dollars)
            options.resume = resume
            if schema:
                options.output_format = {"type": "json_schema", "schema": schema}
                options.allowed_tools = LECTURE
            r.appels += 1
            session_id = None
            try:
                async for m in query(prompt=prompt, options=options):
                    if isinstance(m, ResultMessage):
                        session_id = m.session_id
                        r.fin = m.subtype if not m.is_error else f"erreur:{m.subtype}"
                        r.tours += m.num_turns
                        r.cout_dollars += m.total_cost_usd or 0.0
                        _ajouter_usage(r, m.model_usage or {})
                        r.cout_recalcule = recalculer(r.model_usage)
                        noter(None, modele, Cout(m.total_cost_usd or 0.0), chapitre="17", etape="autorevue",
                              cas=f"{r.variante}", seance=m.session_id, subtype=m.subtype, tours=m.num_turns,
                              cout_sdk=m.total_cost_usd)
                        so = m.structured_output
                        if schema and isinstance(so, dict) and isinstance(so.get("constats"), list):
                            r.structures += 1
                            r.constats = so["constats"]
                        # pas de return ici : sortir de la boucle de query() en plein vol le referme mal
            except Exception as e:
                r.erreur = f"{type(e).__name__}: {e}"
            return session_id

        session = await interroger(ecriture, ch15.TACHES["majoration"], None, None)
        apres = (depot / "primes" / "calcul.py").read_text(encoding="utf-8")
        calculs = ch15.calculer(depot)
        ecriture.controles = {"jeune_demi": calculs.get("jeune_demi"),
                              "tronque": calculs.get("jeune_demi") == ch15.JEUNE_TRONQUE}
        ecriture.latence_s = round(time.perf_counter() - t0, 1)
        revues.append(ecriture)
        diff = "\n".join(difflib.unified_diff(avant.splitlines(), apres.splitlines(), "a/primes/calcul.py",
                                              "b/primes/calcul.py", lineterm=""))
        criteres = CRITERES_V2.split("\n", 3)[3]  # sans le titre ni la ligne vide qui le suit
        for variante in variantes:
            if not session or budget - sum(x.cout_dollars for x in revues) < 0.01:
                break
            r = Revue("autorevue", variante, "majoration", repetition)
            t0 = time.perf_counter()
            if variante == "meme_seance":
                await interroger(r, AUTOREVUE.format(criteres=criteres), session, SCHEMA)
            else:
                await interroger(r, INDEPENDANTE.format(criteres=criteres, diff=diff), None, SCHEMA)
            texte = [normaliser(" ".join(str(c.get(k, "")) for k in ("description", "detected_pattern")))
                     for c in r.constats]
            r.controles = {"code_tronque": ecriture.controles["tronque"],
                           "troncature_signalee": any(("int(" in t or "tronqu" in t or "arrondir_fcfa" in t)
                                                      for t in texte)}
            r.latence_s = round(time.perf_counter() - t0, 1)
            revues.append(r)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
    return revues


# --- Le résumé --------------------------------------------------------------------------------------

def _compte(valeurs) -> dict:
    valeurs = list(valeurs)
    return {str(v): valeurs.count(v) for v in dict.fromkeys(valeurs)}


def resumer(revues: list[Revue]) -> dict:
    groupes: dict[str, list[Revue]] = {}
    for r in revues:
        groupes.setdefault(f"{r.mesure}:{r.variante}:{r.demande}", []).append(r)
    resume = {}
    for cle, rs in groupes.items():
        defauts = [d["id"] for d in DEFAUTS.get(rs[0].demande, [])]
        x = {
            "revues": len(rs),
            "fins": _compte(r.fin for r in rs),
            "appels": sum(r.appels for r in rs),
            "structures": sum(r.structures for r in rs),
            "cout_total": round(sum(r.cout_dollars for r in rs), 6),
            "cout_moyen": round(statistics.mean(r.cout_dollars for r in rs), 6),
            "cout_recalcule_total": round(sum(r.cout_recalcule for r in rs), 6),
            "constats_moyens": round(statistics.mean(len(r.constats) for r in rs), 1),
            "hors_defauts_moyens": round(statistics.mean(r.hors_defauts for r in rs), 1),
            "latence_mediane_s": statistics.median(r.latence_s for r in rs),
        }
        if defauts:
            x["defauts"] = {d: sum(d in r.defauts_trouves for r in rs) for d in defauts}
            x["defauts_trouves_moyens"] = round(statistics.mean(len(r.defauts_trouves) for r in rs), 1)
        if rs[0].mesure == "relance" and rs[0].controles:
            for k in ("sur_corriges", "doublons", "publies", "toujours_ouverts"):
                x[k] = sum(r.controles.get(k, 0) for r in rs)
        if rs[0].mesure == "autorevue":
            for k in ("tronque", "troncature_signalee", "code_tronque"):
                if k in rs[0].controles:
                    x[k] = sum(bool(r.controles.get(k)) for r in rs)
        x["gravites"] = _compte(c.get("gravite") for r in rs for c in r.constats)
        resume[cle] = x
    return resume


def _afficher(r: Revue) -> None:
    print(f"{r.mesure}:{r.variante}:{r.demande} #{r.repetition} : {r.fin}, {r.appels} appel(s), {r.tours} tours, "
          f"{francais(r.cout_dollars, 4)} $, {r.latence_s} s ; {len(r.constats)} constats, défauts "
          f"{','.join(r.defauts_trouves) or 'aucun'}, hors défauts {r.hors_defauts}"
          + (f" ; {r.controles}" if r.controles else "") + (f" ; {r.erreur}" if r.erreur else ""))


def lancer(mesures: list[str], variantes: list[str] | None, repetitions: int, modele: str,
           budget_max: float) -> tuple[list[Revue], float]:
    revues, depense = [], 0.0
    v = version()
    for repetition in range(1, repetitions + 1):
        for mesure in mesures:
            choisies = [x for x in MESURES[mesure] if not variantes or x in variantes]
            if budget_max - depense < 0.02:
                print(f"Arrêt avant {mesure} #{repetition} : plafond presque atteint.")
                return revues, depense
            restant = budget_max - depense
            if mesure == "criteres":
                nouvelles = [revue_simple(x, d, repetition, modele, restant / (2 * len(choisies)))
                             for x in choisies for d in ("moto", "echeancier")]
            elif mesure == "passes":
                nouvelles = [revue_simple("une_passe", "moto", repetition, modele, restant / 2, "passes")
                             if x == "une_passe" else revue_par_fichier("moto", repetition, modele, restant / 2)
                             for x in choisies]
            elif mesure == "relance":
                nouvelles = relance(repetition, modele, restant, choisies)
            else:
                nouvelles = asyncio.run(autorevue(repetition, modele, restant, choisies))
            for r in nouvelles:
                r.version = v
                _afficher(r)
            revues += nouvelles
            depense += sum(r.cout_dollars for r in nouvelles)
    return revues, depense


def principal() -> None:
    parser = argparse.ArgumentParser(description="Chapitre 17 : la revue automatique des demandes de fusion.")
    parser.add_argument("--mesures", nargs="+", choices=list(MESURES), default=["criteres"])
    parser.add_argument("--variantes", nargs="+")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--modele", default=MODELE)
    parser.add_argument("--budget-max", type=float, default=0.20)
    parser.add_argument("--reevaluer", help="relire un fichier de résultats, sans rien relancer")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")

    if args.reevaluer:
        donnees = json.loads(Path(args.reevaluer).read_text(encoding="utf-8"))
        revues = [Revue(**r) for r in donnees["revues"]]
        for r in revues:  # les défauts se rapprochent à nouveau, avec defauts.json tel qu'il est
            if r.demande in DEFAUTS:
                _conclure(r, r.demande)
            if r.mesure == "relance" and r.variante in ("sans", "avec"):
                r.controles = controles_relance(r)
        print(json.dumps(resumer(revues), ensure_ascii=False, indent=2))
        return

    revues, depense = lancer(args.mesures, args.variantes, args.repetitions, args.modele, args.budget_max)
    if not revues:
        return
    resume = resumer(revues)
    nom = "-".join(args.mesures) + "-" + args.modele.removeprefix("claude-")
    sortie = DOSSIER / "resultats" / f"{nom}-{datetime.now():%Y-%m-%d-%H%M}.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps({"date": date.today().isoformat(), "modele": args.modele, "mesures": args.mesures,
                                  "variantes": args.variantes, "repetitions": args.repetitions,
                                  "depense_dollars": round(depense, 6), "resume": resume,
                                  "revues": [asdict(r) for r in revues]},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(resume, ensure_ascii=False, indent=2))
    print(f"\nDépense estimée par Claude Code : {francais(depense, 4)} $ (≈ {francais(depense * config.TAUX_FCFA, 1)} FCFA)")
    print(f"Résultats : {sortie}")


if __name__ == "__main__":
    principal()
