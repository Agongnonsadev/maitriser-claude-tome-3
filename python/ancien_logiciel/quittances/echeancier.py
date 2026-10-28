# -*- coding: utf-8 -*-
# Echeancier des quittances selon le fractionnement. AB 2013
from util import dates

NB_ECHEANCES = {'annuel': 1, 'trimestriel': 4, 'mensuel': 12}


def echeancier(prime_annuelle, date_effet, fractionnement='annuel'):
    n = NB_ECHEANCES.get(fractionnement, 1)
    pas = 12 // n
    montant = int(prime_annuelle / n)
    lignes = []
    for i in range(n):
        lignes.append((dates.ajouter_mois(date_effet, i * pas), montant))
    return lignes


def total(lignes):
    t = 0
    for echeance, montant in lignes:
        t = t + montant
    return t
