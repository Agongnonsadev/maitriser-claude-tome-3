# -*- coding: utf-8 -*-
# Lecture des tables de tarifs fournies par l'actuariat (dossier tarifs/). KS 2011
import os

import config

_cache = {}


def lire(nom):
    if nom in _cache:
        return _cache[nom]
    t = {}
    f = open(os.path.join(config.TARIFS, nom + '.txt'))
    for ligne in f.readlines():
        ligne = ligne.strip()
        if ligne == '' or ligne.startswith('#'):
            continue
        cle, valeur = ligne.split(';')
        if '.' in valeur:
            t[cle] = float(valeur)
        else:
            t[cle] = int(valeur)
    f.close()
    _cache[nom] = t
    return t


def vider_cache():
    global _cache
    _cache = {}
