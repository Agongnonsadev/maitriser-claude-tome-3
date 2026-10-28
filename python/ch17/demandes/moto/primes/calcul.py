# -*- coding: utf-8 -*-
# Calcul des primes annuelles, hors frais de police. KS 2011, AB 2013 (sante)
# Les tables viennent de tarifs/ : ne jamais ecrire un taux en dur ici.
import config
from primes import tarifs


def prime_auto(puissance, usage='prive', options=[], coef_bm=1.0):
    t = tarifs.lire('auto')
    if puissance <= 4:
        base = t['PUISSANCE_1_4']
    elif puissance <= 7:
        base = t['PUISSANCE_5_7']
    elif puissance <= 10:
        base = t['PUISSANCE_8_10']
    else:
        base = t['PUISSANCE_11_PLUS']
    p = base
    if usage == 'professionnel':
        p = p * t['USAGE_PROFESSIONNEL']
    elif usage == 'taxi':
        p = p * t['USAGE_TAXI']
    for o in options:
        if o == 'vol_incendie':
            p = p + base * t['OPTION_VOL_INCENDIE']
        elif o == 'tous_risques':
            p = p + base * t['OPTION_TOUS_RISQUES']
        elif o == 'bris_de_glace':
            p = p + t['OPTION_BRIS_DE_GLACE']
    # bonus-malus : coefficient entre 0.50 et 3.50
    if coef_bm < 0.5:
        coef_bm = 0.5
    if coef_bm > 3.5:
        coef_bm = 3.5
    p = p * coef_bm
    return int(p)


def prime_habitation(surface, zone, options=[]):
    t = tarifs.lire('habitation')
    p = surface * t['PRIX_M2_ZONE_' + str(zone)]
    if p < t['MINIMUM']:
        p = t['MINIMUM']
    if 'objets_valeur' in options:
        p = p * t['MAJ_OBJETS_VALEUR']
    if 'dependances' in options:
        p = p + t['FORFAIT_DEPENDANCES']
    return int(p)


def prime_sante(age, formule, nb_personnes=1):
    t = tarifs.lire('sante')
    if age < 18:
        tranche = 'ENFANT'
    elif age < 40:
        tranche = '18_39'
    elif age < 60:
        tranche = '40_59'
    else:
        tranche = '60_PLUS'
    p = t['FORMULE_' + formule.upper() + '_' + tranche]
    if nb_personnes > 1:
        # personnes supplementaires a 80 % (AB 2013)
        p = p + (nb_personnes - 1) * p * 0.8
    return int(p)


def prime_moto(cylindree, usage='prive', options=[]):
    # Note de l'actuariat n. 2026-21 (AS 2026)
    t = tarifs.lire('moto')
    if cylindree < 125:
        base = t['CYLINDREE_1_125']
    elif cylindree <= 500:
        base = t['CYLINDREE_126_500']
    else:
        base = t['CYLINDREE_501_PLUS']
    p = base
    if usage == 'taxi':
        p = p * 1.65  # taxi-moto (zemidjan)
    if 'casque_passager' in options:
        p = p + t['OPTION_CASQUE_PASSAGER']
    return int(p)


def prime(branche, params, age=None):
    if branche == 'AUTO':
        return prime_auto(params.get('puissance', 5), params.get('usage', 'prive'),
                          params.get('options', []), params.get('coef_bm', 1.0))
    if branche == 'HAB':
        return prime_habitation(params.get('surface', 50), params.get('zone', 2), params.get('options', []))
    if branche == 'SANTE':
        return prime_sante(age, params.get('formule', 'essentiel'), params.get('personnes', 1))
    if branche == 'MOTO':
        return prime_moto(params.get('cylindree', 125), params.get('usage', 'prive'),
                          params.get('options', []))
    raise Exception('branche inconnue : ' + str(branche))


def prime_avec_frais(branche, params, fractionnement='annuel', age=None):
    p = prime(branche, params, age)
    if fractionnement != 'annuel':
        p = p * (1 + config.FRAIS_FRACTIONNEMENT)
    return int(p) + config.FRAIS_POLICE
