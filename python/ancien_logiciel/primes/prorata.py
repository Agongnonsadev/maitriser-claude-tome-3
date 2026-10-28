# -*- coding: utf-8 -*-
# Remboursement au prorata en cas de resiliation. KS 2012
from util import dates


def remboursement(prime_annuelle, date_effet, date_fin, date_resiliation):
    """Part de prime non consommee, a rembourser a l'assure."""
    total = dates.jours_entre(date_effet, date_fin)
    restant = dates.jours_entre(date_resiliation, date_fin)
    if restant <= 0 or total <= 0:
        return 0
    return round(prime_annuelle * restant / total)
