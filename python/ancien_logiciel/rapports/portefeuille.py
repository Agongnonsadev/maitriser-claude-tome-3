# -*- coding: utf-8 -*-
# Rapport du portefeuille pour la direction. AB 2016
import config
from base import requetes
from util.divers import montant_contrat
from util.montants import format_fcfa


def resume_branche(branche):
    contrats = requetes.contrats_branche(branche)
    total = 0
    for c in contrats:
        total = total + montant_contrat(c[0])
    return {'branche': branche, 'nombre': len(contrats), 'primes': total}


def rapport():
    lignes = []
    for b in config.BRANCHES:
        r = resume_branche(b)
        lignes.append(r)
    return lignes


def afficher():
    print('PORTEFEUILLE KANVO ASSURANCES - contrats actifs')
    for r in rapport():
        print('%-12s %5d contrats  %s' % (config.LIBELLES[r['branche']], r['nombre'], format_fcfa(r['primes'])))
