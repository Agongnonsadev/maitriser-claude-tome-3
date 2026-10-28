# -*- coding: utf-8 -*-
# Tests de l'echeancier, ecrits avant la correction du ticket DSI-2026-031 (Yao, octobre 2026).
# La comptabilite veut des quittances egales au franc inferieur, et le reliquat sur la premiere.
from quittances.echeancier import echeancier, total


def montants(lignes):
    return [m for _, m in lignes]


def test_mensuel_du_ticket():
    lignes = echeancier(134318, '15/01/2026', 'mensuel')
    assert montants(lignes) == [11195] + [11193] * 11
    assert total(lignes) == 134318


def test_mensuel_reliquat_au_dela_de_la_moitie():
    assert montants(echeancier(100006, '01/03/2026', 'mensuel')) == [8343] + [8333] * 11


def test_trimestriel():
    assert montants(echeancier(100003, '01/03/2026', 'trimestriel')) == [25003, 25000, 25000, 25000]


def test_annuel_inchange():
    assert echeancier(60000, '10/05/2026', 'annuel') == [('10/05/2026', 60000)]


def test_dates_inchangees():
    dates = [d for d, _ in echeancier(134318, '15/01/2026', 'mensuel')]
    assert dates[:3] == ['15/01/2026', '15/02/2026', '15/03/2026'] and len(dates) == 12
