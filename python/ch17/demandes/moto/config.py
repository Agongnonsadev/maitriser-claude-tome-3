# -*- coding: utf-8 -*-
# Configuration generale du logiciel des contrats.
# KS 2011, modif AB 2013 (sante)
# AS 2026 : branche moto (note de l'actuariat n. 2026-21)
import os

REP = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(REP, 'donnees', 'contrats.db')
TARIFS = os.path.join(REP, 'tarifs')
EXPORTS = os.path.join(REP, 'exports')

DEVISE = 'FCFA'
FRAIS_POLICE = 5000          # frais de police, ajoutes une fois par an
FRAIS_FRACTIONNEMENT = 0.03  # +3 % si paiement mensuel ou trimestriel
ANNEE_COURANTE = 2016        # a mettre a jour chaque annee !!!
FORMAT_DATE = '%d/%m/%Y'
DEBUG = 0

BRANCHES = ['AUTO', 'HAB', 'SANTE', 'MOTO']
LIBELLES = {'AUTO': 'Automobile', 'HAB': 'Habitation', 'SANTE': 'Sante', 'MOTO': 'Moto'}
