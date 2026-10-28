# -*- coding: utf-8 -*-
# Creation, avenants et resiliation des contrats. KS 2011, AB 2013
from base import requetes
from contrats import numeros
from primes import calcul, prorata
from quittances import echeancier
from util import dates
from util.divers import *


def creer_contrat(assure, branche, formule, date_effet, params, fractionnement='annuel'):
    a = requetes.assure(assure)
    if a == None:
        print('Assure inconnu : %s' % assure)
        return None
    age = None
    if branche == 'SANTE':
        age = dates.age(a[3], date_effet)
    c = {}
    c['numero'] = numeros.prochain_numero(branche)
    c['assure'] = assure
    c['branche'] = branche
    c['formule'] = formule
    c['date_effet'] = date_effet
    c['date_fin'] = dates.ajouter_un_an(date_effet)
    c['statut'] = 'actif'
    c['fractionnement'] = fractionnement
    c['prime_annuelle'] = calcul.prime_avec_frais(branche, params, fractionnement, age)
    c['parametres'] = texte_parametres(params)
    requetes.enregistrer_contrat(c)
    for echeance, montant in echeancier.echeancier(c['prime_annuelle'], c['date_effet'], fractionnement):
        requetes.enregistrer_quittance(c['numero'], echeance, montant)
    log('contrat cree', c['numero'], c['prime_annuelle'])
    return c['numero']


def prime_du_contrat(numero):
    c = requetes.contrat(numero)
    if c == None:
        return 0
    return c[8]


def recalculer_prime(numero, a_la_date):
    c = requetes.contrat(numero)
    params = parametres(c[9])
    age = None
    if c[2] == 'SANTE':
        a = requetes.assure(c[1])
        age = dates.age(a[3], a_la_date)
    p = calcul.prime_avec_frais(c[2], params, c[7], age)
    requetes.maj_prime(numero, p)
    return p


def avenant(numero, nouveaux_params, a_la_date):
    c = requetes.contrat(numero)
    params = parametres(c[9])
    for cle in nouveaux_params:
        params[cle] = nouveaux_params[cle]
    from base.connexion import executer
    executer("UPDATE contrats SET parametres = ? WHERE numero = ?", (texte_parametres(params), numero))
    return recalculer_prime(numero, a_la_date)


def resilier(numero, date_resiliation):
    c = requetes.contrat(numero)
    if c == None or c[6] != 'actif':
        return 0
    rembourse = prorata.remboursement(c[8], c[4], c[5], date_resiliation)
    requetes.maj_statut(numero, 'resilie', date_resiliation)
    log('resiliation', numero, rembourse)
    return rembourse
