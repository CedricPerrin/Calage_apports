"""
Ce que pilote_hecras.bilan_masse_recalcule DOIT faire devant un echantillon
aberrant a une condition limite.

Cas reel du 13/11/2026 (Ard_aval, apport ARD07, essai 2) : HEC-RAS 7.0.2 a
rendu un bilan de masse de +27,52 % sur un calcul sain. La serie de la
condition limite ARD07 valait 386 032 m3/s a la derniere sortie, pour 44,8
au plus ailleurs ; HEC-RAS avait compte le volume de l'apport une seconde
fois en sortie. Le bilan refait sur les series tombait a -0,02 %, et le
calage s'etait arrete sur ARD07.

Les .hdf sont FABRIQUES avec h5py, sur la structure lue par la fonction.
Verifie aussi sur les vrais .pNN.hdf du calage Ard_aval (p02, p16 a p24) :
ecart au chiffre de HEC-RAS inferieur a 0,04 point sur les calculs sains.

    python -m pytest src/test_bilan_masse_artefact.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pytest

h5py = pytest.importorskip("h5py")

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

import pilote_hecras as pilote  # noqa: E402

SERIES = pilote.CHEMIN_SERIES_HDF
JOURS = np.linspace(0.0, 1.0, 241)                 # 24 h, sortie a 6 min
SECONDES = JOURS * 86400.0
ENTREE = 40.0 * np.exp(-((JOURS * 24 - 8) / 3) ** 2) + 1.0
SORTIE = 40.0 * np.exp(-((JOURS * 24 - 10) / 3) ** 2) + 1.0


def _volume(q):
    return float(np.trapezoid(q, SECONDES)) / 1000.0


def _hdf(chemin, entree, sortie, v_in=None, cum_out=None, ecart_fin=0.0):
    """
    Resultats d'une zone 2D a une entree (« AMONT », hydrogramme de debit) et
    une sortie (« AVAL », hydrogramme de cote). « v_in » est le volume
    reellement injecte (celui de la serie par defaut). Le volume final est
    celui que la conservation donne, plus « ecart_fin » (milliers de m3) ;
    « cum_out » est la sortie que HEC-RAS AFFICHE, juste par defaut.
    """
    v_debut = 200.0
    if v_in is None:
        v_in = _volume(entree)
    v_out = _volume(sortie)
    v_fin = v_debut + v_in - v_out + ecart_fin
    if cum_out is None:
        cum_out = v_out
    erreur = v_fin + cum_out - v_debut - v_in          # signe de HEC-RAS
    with h5py.File(chemin, "w") as h:
        resume = h.require_group("Results/Unsteady/Summary/Volume Accounting")
        resume.attrs["Volume Starting"] = v_debut
        resume.attrs["Volume Ending"] = v_fin
        resume.attrs["Error Percent"] = 100.0 * erreur / (v_debut + v_in)
        resume.attrs["Vol Accounting in"] = b"1000 m^3"
        h.require_group("Event Conditions/Unsteady/Boundary Conditions/"
                        "Flow Hydrographs/2D: Zone BCLine: AMONT")
        h.require_group("Event Conditions/Unsteady/Boundary Conditions/"
                        "Stage Hydrographs/2D: Zone BCLine: AVAL")
        h.create_dataset(f"{SERIES}/Time", data=JOURS)
        cl = h.require_group(f"{SERIES}/2D Flow Areas/Zone/Boundary Conditions")
        cl.create_dataset("AMONT", data=np.column_stack([0 * JOURS, entree]))
        cl.create_dataset("AMONT - Flow per Cell", data=entree[:, None])
        cl.create_dataset("AVAL", data=np.column_stack([0 * JOURS, sortie]))
    return chemin


def test_calcul_sain_concorde_avec_hecras(tmp_path):
    r = pilote.bilan_masse_recalcule(_hdf(tmp_path / "a.hdf", ENTREE, SORTIE))
    assert r["aberrants"] == []
    assert abs(r["pct"]) < 1e-6
    assert abs(r["pct"] - r["pct_hecras"]) < 1e-6


def test_echantillon_aberrant_ecarte(tmp_path):
    """Le cas ARD07 : pic final absurde, sortie HEC-RAS gonflee d'autant."""
    entree = ENTREE.copy()
    entree[-1] = 386032.0
    v_in = _volume(ENTREE)
    hdf = _hdf(tmp_path / "b.hdf", entree, SORTIE, v_in=v_in,
               cum_out=_volume(SORTIE) + v_in)
    r = pilote.bilan_masse_recalcule(hdf)
    assert r["pct_hecras"] > 5.0                       # ce qui arretait le calage
    assert len(r["aberrants"]) == 1
    nom, t_h, q, plafond = r["aberrants"][0]
    assert nom == "AMONT" and q == pytest.approx(386032.0)
    assert t_h == pytest.approx(24.0)
    assert abs(r["pct"]) < 0.05


def test_vraie_perte_reste_visible(tmp_path):
    """Un artefact ne blanchit pas une perte d'eau reelle."""
    entree = ENTREE.copy()
    entree[-1] = 386032.0
    v_in = _volume(ENTREE)
    hdf = _hdf(tmp_path / "c.hdf", entree, SORTIE, v_in=v_in,
               ecart_fin=-0.10 * v_in)
    r = pilote.bilan_masse_recalcule(hdf)
    assert r["aberrants"]
    assert abs(r["pct"]) > 5.0


def test_sortie_jamais_filtree(tmp_path):
    """Seuls les hydrogrammes de DEBIT sont filtres : une sortie reste brute."""
    sortie = SORTIE.copy()
    sortie[-1] = 5000.0
    r = pilote.bilan_masse_recalcule(_hdf(tmp_path / "d.hdf", ENTREE, sortie))
    assert r["aberrants"] == []


def test_fichier_sans_bilan(tmp_path):
    chemin = tmp_path / "e.hdf"
    with h5py.File(chemin, "w") as h:
        h.require_group("Results/Summary")
    assert pilote.bilan_masse_recalcule(chemin) is None
    assert pilote.bilan_masse_recalcule(tmp_path / "absent.hdf") is None
