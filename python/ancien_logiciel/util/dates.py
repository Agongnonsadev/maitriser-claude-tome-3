# -*- coding: utf-8 -*-
# Dates au format jj/mm/aaaa. KS 2011
import datetime

import config


def lire(texte):
    try:
        return datetime.datetime.strptime(texte, config.FORMAT_DATE).date()
    except:
        return None


def ecrire(d):
    return d.strftime(config.FORMAT_DATE)


def jours_entre(debut, fin):
    return (lire(fin) - lire(debut)).days


def ajouter_mois(texte, n):
    d = lire(texte)
    mois = d.month - 1 + n
    annee = d.year + mois // 12
    mois = mois % 12 + 1
    jour = min(d.day, 28)  # simplification KS : pas de 29, 30, 31
    return ecrire(datetime.date(annee, mois, jour))


def ajouter_un_an(texte):
    d = lire(texte)
    try:
        return ecrire(d.replace(year=d.year + 1))
    except ValueError:  # 29 fevrier
        return ecrire(d.replace(year=d.year + 1, day=28))


def age(date_naissance, a_la_date):
    n = lire(date_naissance)
    d = lire(a_la_date)
    a = d.year - n.year
    if (d.month, d.day) < (n.month, n.day):
        a = a - 1
    return a


def annees_depuis(texte, a_la_date):
    return age(texte, a_la_date)
