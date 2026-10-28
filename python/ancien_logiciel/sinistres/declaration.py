# -*- coding: utf-8 -*-
# Enregistrement des declarations de sinistre. KS 2011
from base import requetes
from sinistres.franchise import calcul_franchise
from util import dates
from util.divers import branche_de, log

_compteur = {}


def numero_sinistre(annee):
    _compteur[annee] = _compteur.get(annee, 0) + 1
    return 'SIN-%d-%04d' % (annee, _compteur[annee])


def contrat_couvre(contrat, date_sinistre):
    c = requetes.contrat(contrat)
    if c == None:
        return False
    if c[6] != 'actif':
        return False
    d = dates.lire(date_sinistre)
    return dates.lire(c[4]) <= d and d <= dates.lire(c[5])


def declarer(contrat, date_sinistre, nature, garantie, montant_dommage):
    if not contrat_couvre(contrat, date_sinistre):
        print('Contrat %s ne couvre pas le %s' % (contrat, date_sinistre))
        return None
    s = {}
    s['numero'] = numero_sinistre(dates.lire(date_sinistre).year)
    s['contrat'] = contrat
    s['date'] = date_sinistre
    s['nature'] = nature
    s['montant_dommage'] = montant_dommage
    s['franchise'] = calcul_franchise(branche_de(contrat), garantie, montant_dommage)
    s['statut'] = 'ouvert'
    requetes.enregistrer_sinistre(s)
    log('sinistre', s['numero'])
    return s['numero']
