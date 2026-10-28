# -*- coding: utf-8 -*-
# Export CSV pour les tableaux de bord de la direction. AB 2016
import csv
import os

import config
from rapports.portefeuille import rapport


def exporter(nom='portefeuille.csv'):
    if not os.path.exists(config.EXPORTS):
        os.makedirs(config.EXPORTS)
    chemin = os.path.join(config.EXPORTS, nom)
    f = open(chemin, 'w', newline='')
    w = csv.writer(f, delimiter=';')
    w.writerow(['branche', 'nombre', 'primes_fcfa'])
    for r in rapport():
        w.writerow([r['branche'], r['nombre'], r['primes']])
    f.close()
    return chemin
