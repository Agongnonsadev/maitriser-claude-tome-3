# -*- coding: utf-8 -*-
# Fonctions diverses, appelees un peu partout. KS 2011, AB 2016
import config


def log(*args):
    if config.DEBUG:
        print('[LOG]', *args)


def parametres(texte):
    """'puissance=7;usage=prive;options=vol_incendie,tous_risques' -> dict"""
    d = {}
    if not texte:
        return d
    for morceau in texte.split(';'):
        if '=' in morceau:
            cle, valeur = morceau.split('=', 1)
            if cle == 'options':
                d[cle] = [o for o in valeur.split(',') if o]
            else:
                try:
                    d[cle] = int(valeur)
                except:
                    d[cle] = valeur
    return d


def texte_parametres(d):
    morceaux = []
    for cle in sorted(d):
        valeur = d[cle]
        if isinstance(valeur, list):
            valeur = ','.join(valeur)
        morceaux.append('%s=%s' % (cle, valeur))
    return ';'.join(morceaux)


def montant_contrat(numero):
    # garde pour les rapports (AB 2016) : voir contrats.contrat.prime_du_contrat
    from contrats.contrat import prime_du_contrat
    return prime_du_contrat(numero)


def branche_de(numero):
    # KA-AUTO-0193 -> AUTO
    try:
        return numero.split('-')[1]
    except:
        return '?'
