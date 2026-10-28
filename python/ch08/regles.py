"""Chapitre 8 : les règles du règlement rapide, garanties par le code (hooks de l'Agent SDK).

Une consigne se suit le plus souvent. Une règle qui engage de l'argent doit se suivre toujours : elle va
dans le code, ici dans des hooks que l'agent ne peut pas contourner.

- PreToolUse sur verifier_identite : la date de naissance doit venir de l'assuré. Si elle n'apparaît pas
  dans ses messages, l'appel est refusé : l'agent ne peut pas deviner, ni corriger, une identité.
- PostToolUse sur verifier_identite : le code note quels assurés sont vérifiés dans la séance.
- PostToolUse sur calculer_reglement : les vieux formats du barème (montants en texte, date en secondes)
  sont normalisés avant que Claude les lise.
- PreToolUse sur declencher_reglement_rapide : identité vérifiée, montant du barème, plafond de 150 000 FCFA.
  Sinon l'appel est refusé, et la raison dit à Claude quoi faire : transmettre, avec quel motif.
- Stop : si l'assuré a demandé à parler à quelqu'un et qu'aucune transmission n'est partie, l'arrêt est
  refusé une fois, avec la consigne de transmettre.

La Garde note chaque décision, pour la mesure et pour l'audit.
"""

import json
import re
from datetime import datetime, timezone

from assureur.outils_v3 import PLAFOND_FCFA
from assureur.systeme import ErreurSysteme, Systeme

PREFIXE = "mcp__kanvo__"
DEMANDE_D_UN_HUMAIN = re.compile(
    r"parler (à|avec) (quelqu'un|un humain|une personne|un conseiller|un gestionnaire)|passez-moi (un|une|quelqu)"
    r"|(pas|plus) (parler )?(à|avec|d') ?(un robot|une machine)|un vrai conseiller", re.IGNORECASE)


def _texte_de(reponse) -> str:
    """Le texte d'un résultat d'outil, quelle que soit sa forme (texte, liste de blocs, résultat MCP)."""
    if isinstance(reponse, str):
        return reponse
    if isinstance(reponse, dict):
        return _texte_de(reponse.get("content", reponse.get("text", "")))
    if isinstance(reponse, list):
        return "".join(_texte_de(b) for b in reponse)
    return ""


def _avec_texte(reponse, texte: str):
    """La même forme de résultat, avec un autre texte."""
    if isinstance(reponse, str):
        return texte
    if isinstance(reponse, dict) and isinstance(reponse.get("content"), list):
        return {**reponse, "content": [{"type": "text", "text": texte}]}
    if isinstance(reponse, list):
        return [{"type": "text", "text": texte}]
    return {"content": [{"type": "text", "text": texte}]}


def formes_de_date(iso: str) -> set[str]:
    annee, mois, jour = iso.split("-")
    return {iso, f"{jour}/{mois}/{annee}", f"{int(jour)}/{int(mois)}/{annee}", f"{jour}-{mois}-{annee}"}


def normaliser_bareme(texte: str) -> str:
    """{"montant_evalue": "95 000,00 FCFA", "franchise": "15.000", "date_calcul": 1761609600} -> entiers et date ISO."""
    donnees = json.loads(texte)
    entier = lambda v: v if isinstance(v, int) else int(re.sub(r"\D", "", str(v).split(",")[0]))
    propre = {"numero_sinistre": donnees["sinistre"], "montant_evalue_fcfa": entier(donnees["montant_evalue"]),
              "franchise_fcfa": entier(donnees["franchise"]), "a_verser_fcfa": entier(donnees["a_verser"]),
              "date_calcul": datetime.fromtimestamp(donnees["date_calcul"], tz=timezone.utc).date().isoformat()}
    return json.dumps(propre, ensure_ascii=False)


def _refus(evenement: str, raison: dict) -> dict:
    return {"hookSpecificOutput": {"hookEventName": evenement, "permissionDecision": "deny",
                                   "permissionDecisionReason": json.dumps(raison, ensure_ascii=False)}}


class Garde:
    def __init__(self, systeme: Systeme, messages_assure: str, plafond: int = PLAFOND_FCFA, imposer: bool = True):
        self.systeme, self.plafond, self.imposer = systeme, plafond, imposer
        self.messages_assure = messages_assure
        self.demande_d_un_humain = bool(DEMANDE_D_UN_HUMAIN.search(messages_assure))
        self.verifies: set[str] = set()
        self.journal: list[dict] = []   # chaque décision, dans l'ordre

    # --- Les règles, sans l'Agent SDK : testables seules --------------------------------------

    def refus_verification(self, entree: dict) -> dict | None:
        date = str(entree.get("date_naissance", "")).strip()
        try:
            iso = date if "-" in date and len(date) == 10 else "-".join(reversed([p.zfill(2) for p in date.split("/")]))
            vient_de_l_assure = any(f in self.messages_assure for f in formes_de_date(iso))
        except ValueError:
            vient_de_l_assure = False
        if not vient_de_l_assure:
            return {"regle": "donnee_de_l_assure", "detail": "Cette date de naissance ne figure pas dans les messages "
                    "de l'assuré.", "conseil": "Demandez-la à l'assuré ; ne la devinez pas et ne la corrigez pas."}
        return None

    def refus_reglement(self, entree: dict) -> dict | None:
        numero, montant = entree.get("numero_sinistre", ""), entree.get("montant_fcfa")
        try:
            assure = self.systeme.assure_du_sinistre(numero)
            a_verser = self.systeme.calculer_reglement(numero)["a_verser_fcfa"]
        except ErreurSysteme as e:
            return {"regle": "sinistre_reglable", "detail": str(e), "conseil": "Ne déclenchez pas de règlement."}
        if assure not in self.verifies:
            return {"regle": "identite_verifiee", "detail": f"L'identité de l'assuré {assure} n'est pas vérifiée.",
                    "conseil": "Vérifiez-la avec verifier_identite, avec les informations de l'assuré lui-même ; sinon "
                               "transmettez avec le motif identite_non_verifiee."}
        if montant != a_verser:
            return {"regle": "montant_du_bareme", "detail": f"Le barème donne {a_verser} FCFA, pas {montant}.",
                    "conseil": f"Le seul montant possible est {a_verser} FCFA."}
        if montant > self.plafond:
            return {"regle": "plafond", "detail": f"{montant} FCFA dépasse le plafond de {self.plafond} FCFA.",
                    "conseil": f"Ne déclenchez pas le règlement. Transmettez à un gestionnaire avec le motif "
                               f"plafond_depasse et le montant en jeu ({montant} FCFA)."}
        return None

    # --- Les hooks ------------------------------------------------------------------------

    async def avant_outil(self, entree, tool_use_id, contexte) -> dict:
        nom = entree["tool_name"].removeprefix(PREFIXE)
        refus = None
        if nom == "verifier_identite":
            refus = self.refus_verification(entree["tool_input"])
        elif nom == "declencher_reglement_rapide":
            refus = self.refus_reglement(entree["tool_input"])
        self.journal.append({"evenement": "avant", "outil": nom, "entree": entree["tool_input"],
                             "regle_enfreinte": refus["regle"] if refus else None,
                             "refuse": bool(refus) and self.imposer})
        return _refus("PreToolUse", refus) if refus and self.imposer else {}

    async def apres_outil(self, entree, tool_use_id, contexte) -> dict:
        nom = entree["tool_name"].removeprefix(PREFIXE)
        texte = _texte_de(entree.get("tool_response"))
        if nom == "verifier_identite":
            try:
                resultat = json.loads(texte)
                if resultat.get("verifie"):
                    self.verifies.add(resultat["numero_assure"])
            except (json.JSONDecodeError, AttributeError):
                pass
            self.journal.append({"evenement": "apres", "outil": nom, "verifies": sorted(self.verifies)})
        if nom == "calculer_reglement":
            try:
                propre = normaliser_bareme(texte)
            except (json.JSONDecodeError, KeyError, ValueError):
                return {}
            self.journal.append({"evenement": "normalise", "outil": nom})
            return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                           "updatedToolOutput": _avec_texte(entree.get("tool_response"), propre)}}
        return {}

    async def avant_arret(self, entree, tool_use_id, contexte) -> dict:
        transmis = any(t["motif"] == "demande_d_un_humain" for t in self.systeme.transmissions)
        if self.imposer and self.demande_d_un_humain and not transmis and not entree.get("stop_hook_active"):
            self.journal.append({"evenement": "arret_refuse"})
            return {"decision": "block",
                    "reason": "L'assuré a demandé à parler à quelqu'un. Transmettez maintenant à un gestionnaire, avec le "
                              "motif demande_d_un_humain et un relais complet, puis dites-le-lui en une phrase."}
        return {}
