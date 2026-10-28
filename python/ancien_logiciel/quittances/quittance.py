# -*- coding: utf-8 -*-
# Impression des quittances (texte, imprimante de l'agence). AB 2013, AB 2019 (arrondi)
import config
from base import requetes
from util.montants import arrondir_fcfa, format_fcfa


def texte_quittance(contrat, echeance, montant, nom_assure):
    lignes = []
    lignes.append('KANVO ASSURANCES - QUITTANCE')
    lignes.append('Contrat : %s' % contrat)
    lignes.append('Assure  : %s' % nom_assure)
    lignes.append('Echeance: %s' % echeance)
    lignes.append('Montant : %s' % format_fcfa(arrondir_fcfa(montant)))
    lignes.append('Devise  : %s' % config.DEVISE)
    return '\n'.join(lignes)


def imprimer_quittances(contrat):
    c = requetes.contrat(contrat)
    a = requetes.assure(c[1])
    for q in requetes.quittances(contrat):
        print(texte_quittance(contrat, q[1], q[2], a[1]))
        print('-' * 40)
