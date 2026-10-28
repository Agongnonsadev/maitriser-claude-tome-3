# -*- coding: utf-8 -*-
# Echeancier des quittances selon le fractionnement. AB 2013
# SA 2026 (ticket DSI-2026-031) : les quittances au franc inferieur, le reliquat sur la premiere,
# pour que leur total soit egal a la prime annuelle.
from util import dates

NB_ECHEANCES = {'annuel': 1, 'trimestriel': 4, 'mensuel': 12}


def echeancier(prime_annuelle, date_effet, fractionnement='annuel'):
    n = NB_ECHEANCES.get(fractionnement, 1)
    pas = 12 // n
    montant = prime_annuelle // n
    reliquat = prime_annuelle - montant * n
    lignes = []
    for i in range(n):
        lignes.append((dates.ajouter_mois(date_effet, i * pas), montant + (reliquat if i == 0 else 0)))
    return lignes


def total(lignes):
    t = 0
    for echeance, montant in lignes:
        t = t + montant
    return t
