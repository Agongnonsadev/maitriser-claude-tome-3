"""Chapitre 23 : le pilote fabriqué et son bilan. Aucun appel à l'API."""

from ch23 import pilote as p


def ligne(semaine, medecin, corrige, brouillon=True, minutes=10.0):
    return {"semaine": semaine, "medecin": medecin, "groupe": "cohorte" if medecin.startswith("M") else "temoins",
            "dicte": False, "brouillon": brouillon, "minutes": minutes, "corrige": corrige, "conclusion_inventee": False}


def test_le_pilote_fabrique_est_reproductible():
    assert p.fabriquer(23) == p.fabriquer(23) and p.fabriquer(23) != p.fabriquer(24)


def test_la_difference_des_differences():
    assert round(p.difference_des_differences({"M1": -0.5, "M2": -0.3}, {"T1": -0.1, "T2": -0.1}), 3) == -0.3


def test_l_intervalle_entoure_l_estimation():
    c, t = {f"M{i}": -0.4 - 0.02 * i for i in range(8)}, {f"T{i}": -0.05 - 0.01 * i for i in range(6)}
    bas, haut = p.intervalle_bootstrap(c, t, tirages=1000)
    assert bas <= p.difference_des_differences(c, t) <= haut


def test_le_declencheur_compare_aux_autres_et_ignore_les_petits_nombres():
    lignes = [ligne(4, "M1", i < 6) for i in range(12)]                     # 50 % sur 12
    lignes += [ligne(4, "M2", i < 2) for i in range(20)]                    # 10 % sur 20
    lignes += [ligne(4, "M3", True) for _ in range(3)]                      # 100 %, mais sur 3
    alertes = p.declencheurs(lignes, [])
    assert len(alertes) == 1 and alertes[0].startswith("semaine 4 : M1 corrige 6 brouillons sur 12")


def test_le_bilan_dit_aussi_ce_qui_n_a_pas_marche():
    lignes, jours = p.fabriquer(23)
    b = p.bilan(lignes, jours, 23)
    assert b["fabrique"] and b["criteres"]["gain_net"]["atteint"] and b["criteres"]["adoption_semaine_6"]["atteint"]
    assert not b["criteres"]["niveau_de_service"]["atteint"]                # un jeudi à 91 %
    creux = next(s for s in b["semaines"] if s["semaine"] == 2)
    assert creux["cohorte_min"] > b["situation_de_depart_min"]             # la courbe en J
    assert b["gain_naif"] > b["gain_net"]                                   # les témoins ont gagné aussi
    assert b["premiere_annee"]["prudent"]["valeur_fcfa"] < b["premiere_annee"]["valeur_fcfa"]
