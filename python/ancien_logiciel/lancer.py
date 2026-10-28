# -*- coding: utf-8 -*-
# Menu du logiciel des contrats. KS 2011, AB 2016
import sys

from base import connexion, requetes
from rapports import export_csv, portefeuille
from util.montants import format_fcfa


def usage():
    print('python lancer.py creer-base | prime <numero> | rapport | export')


def main(args):
    if len(args) == 0:
        usage()
        return 1
    if args[0] == 'creer-base':
        connexion.creer_base()
        print('Base creee.')
    elif args[0] == 'prime' and len(args) > 1:
        c = requetes.contrat(args[1])
        if c == None:
            print('Contrat inconnu.')
            return 1
        print('%s : %s par an' % (args[1], format_fcfa(c[8])))
    elif args[0] == 'rapport':
        portefeuille.afficher()
    elif args[0] == 'export':
        print(export_csv.exporter())
    else:
        usage()
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
