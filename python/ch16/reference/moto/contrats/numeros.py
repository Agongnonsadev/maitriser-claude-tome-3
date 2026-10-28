# -*- coding: utf-8 -*-
# Numerotation des contrats : KA-AUTO-0193, KA-HAB-0045, KA-SANTE-0318. KS 2011
import config
from base import requetes


def prochain_numero(branche):
    prefixe = 'KA-' + branche + '-'
    dernier = requetes.dernier_numero(prefixe)
    if dernier == None:
        n = 1
    else:
        n = int(dernier.split('-')[2]) + 1
    return prefixe + '%04d' % n


def valide(numero):
    morceaux = numero.split('-')
    if len(morceaux) != 3:
        return False
    if morceaux[0] != 'KA':
        return False
    if morceaux[1] not in config.BRANCHES:  # la liste codee en dur ignorait les nouvelles branches
        return False
    return morceaux[2].isdigit() and len(morceaux[2]) == 4
