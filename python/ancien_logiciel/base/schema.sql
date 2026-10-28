-- Schema de la base des contrats. KS 2011, AB 2013 (sante, fractionnement)
CREATE TABLE IF NOT EXISTS assures (
    numero TEXT PRIMARY KEY,      -- KA-AS-1001
    nom TEXT,
    ville TEXT,
    date_naissance TEXT,          -- jj/mm/aaaa
    date_permis TEXT              -- jj/mm/aaaa, automobile seulement
);

CREATE TABLE IF NOT EXISTS contrats (
    numero TEXT PRIMARY KEY,      -- KA-AUTO-0193
    assure TEXT,
    branche TEXT,                 -- AUTO, HAB, SANTE
    formule TEXT,
    date_effet TEXT,              -- jj/mm/aaaa
    date_fin TEXT,                -- jj/mm/aaaa
    statut TEXT,                  -- actif, resilie, suspendu
    fractionnement TEXT,          -- annuel, trimestriel, mensuel
    prime_annuelle INTEGER,       -- FCFA
    parametres TEXT               -- puissance=7;usage=prive;options=vol_incendie
);

CREATE TABLE IF NOT EXISTS quittances (
    contrat TEXT,
    echeance TEXT,                -- jj/mm/aaaa
    montant INTEGER,              -- FCFA
    payee INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sinistres (
    numero TEXT PRIMARY KEY,      -- SIN-2016-0042
    contrat TEXT,
    date_sinistre TEXT,
    nature TEXT,
    montant_dommage INTEGER,
    franchise INTEGER,
    statut TEXT
);
