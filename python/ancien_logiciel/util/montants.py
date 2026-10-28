# -*- coding: utf-8 -*-
# Montants en FCFA.
# AB 2019 : apres l'incident des quittances a 0,5 FCFA (mars 2019), TOUT nouveau calcul de montant
# doit passer par arrondir_fcfa(). int() tronque (on perd des francs), round() arrondit au pair
# (round(2.5) == 2) : les deux ont donne des ecarts avec la comptabilite.
# Les anciens calculs (primes, prorata) n'ont pas ete repris : voir le ticket DSI-2019-114.
from decimal import Decimal, ROUND_HALF_UP


def arrondir_fcfa(montant):
    """Arrondit au franc le plus proche, la moitie vers le haut : 2,5 -> 3. Rend un int."""
    return int(Decimal(str(montant)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def format_fcfa(montant):
    """12500 -> '12 500 FCFA'"""
    s = '%d' % montant
    groupes = []
    while len(s) > 3:
        groupes.insert(0, s[-3:])
        s = s[:-3]
    groupes.insert(0, s)
    return ' '.join(groupes) + ' FCFA'


def pourcentage(montant, taux):
    # utilise par les rapports seulement
    return montant * taux / 100.0
