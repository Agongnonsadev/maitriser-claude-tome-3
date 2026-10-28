# -*- coding: utf-8 -*-
# Connexion unique a la base. KS 2011
import os
import sqlite3

import config

_cnx = None


def cnx():
    global _cnx
    if _cnx == None:
        if not os.path.exists(os.path.dirname(config.BASE)):
            os.makedirs(os.path.dirname(config.BASE))
        _cnx = sqlite3.connect(config.BASE)
    return _cnx


def executer(sql, params=()):
    c = cnx().cursor()
    c.execute(sql, params)
    cnx().commit()
    return c


def lire(sql, params=()):
    return cnx().execute(sql, params).fetchall()


def lire_un(sql, params=()):
    r = lire(sql, params)
    if len(r) > 0:
        return r[0]
    return None


def creer_base():
    f = open(os.path.join(config.REP, 'base', 'schema.sql'))
    sql = f.read()
    f.close()
    cnx().executescript(sql)
    cnx().commit()
