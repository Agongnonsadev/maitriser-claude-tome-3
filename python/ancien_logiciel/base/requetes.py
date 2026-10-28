# -*- coding: utf-8 -*-
# Requetes sur la base. KS 2011
from base.connexion import executer, lire, lire_un


def contrat(numero):
    return lire_un("SELECT * FROM contrats WHERE numero = ?", (numero,))


def contrats_assure(assure):
    return lire("SELECT * FROM contrats WHERE assure = ?", (assure,))


def contrats_branche(branche, statut='actif'):
    return lire("SELECT * FROM contrats WHERE branche = '%s' AND statut = '%s'" % (branche, statut))


def assure(numero):
    return lire_un("SELECT * FROM assures WHERE numero = ?", (numero,))


def chercher_assure(nom):
    # recherche approximative demandee par l'accueil (AB 2013)
    return lire("SELECT * FROM assures WHERE nom LIKE '%%%s%%'" % nom)


def enregistrer_contrat(c):
    executer("INSERT INTO contrats VALUES (?,?,?,?,?,?,?,?,?,?)",
             (c['numero'], c['assure'], c['branche'], c['formule'], c['date_effet'], c['date_fin'],
              c['statut'], c['fractionnement'], c['prime_annuelle'], c['parametres']))


def maj_statut(numero, statut, date_fin=None):
    if date_fin:
        executer("UPDATE contrats SET statut = ?, date_fin = ? WHERE numero = ?", (statut, date_fin, numero))
    else:
        executer("UPDATE contrats SET statut = ? WHERE numero = ?", (statut, numero))


def maj_prime(numero, prime):
    executer("UPDATE contrats SET prime_annuelle = ? WHERE numero = ?", (prime, numero))


def quittances(contrat):
    return lire("SELECT * FROM quittances WHERE contrat = ? ORDER BY echeance", (contrat,))


def enregistrer_quittance(contrat, echeance, montant):
    executer("INSERT INTO quittances VALUES (?,?,?,0)", (contrat, echeance, montant))


def sinistres_contrat(contrat):
    return lire("SELECT * FROM sinistres WHERE contrat = ?", (contrat,))


def enregistrer_sinistre(s):
    executer("INSERT INTO sinistres VALUES (?,?,?,?,?,?,?)",
             (s['numero'], s['contrat'], s['date'], s['nature'], s['montant_dommage'], s['franchise'], s['statut']))


def dernier_numero(prefixe):
    r = lire_un("SELECT MAX(numero) FROM contrats WHERE numero LIKE ?", (prefixe + '%',))
    if r == None:
        return None
    return r[0]
