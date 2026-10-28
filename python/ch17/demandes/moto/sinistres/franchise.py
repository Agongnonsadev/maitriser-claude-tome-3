# -*- coding: utf-8 -*-
# Franchises par branche et par garantie. KS 2011
FRANCHISES = {
    'AUTO': {'collision': 50000, 'vol_incendie': 75000, 'bris_de_glace': 10000, 'tous_risques': 100000},
    'HAB': {'degat_des_eaux': 25000, 'incendie': 50000, 'vol': 40000},
    'SANTE': {},
    'MOTO': {'collision': 20000, 'vol': 30000},
}


def calcul_franchise(branche, garantie, montant_dommage):
    f = FRANCHISES.get(branche, {}).get(garantie, 0)
    if montant_dommage <= f:
        return montant_dommage
    return f


def montant_indemnise(branche, garantie, montant_dommage):
    return montant_dommage - calcul_franchise(branche, garantie, montant_dommage)
