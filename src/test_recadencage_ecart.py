"""
Le re-cadencage d'une condition limite NON CALEE doit dire ce qu'il change a
sa pointe, quand le pas de travail n'est pas un diviseur de son pas d'origine.

Decision de Cedric du 11/11/2026, apres diagnostic. L'interpolation lineaire
ne retrouve les valeurs d'origine A LEURS INSTANTS que si la nouvelle grille
contient l'ancienne (30 -> 6 min). Sinon (15 -> 6, 10 -> 6, 5 -> 6 min, ou un
pas de travail plus grossier), un point d'origine tombe entre deux points
neufs et il est rabote. Mesure sur des crues realistes : le VOLUME est
conserve a mieux que 0,03 %, mais la POINTE d'une crue eclair perd jusqu'a
2,5 % a 15 -> 6 min, et jusqu'a 12 % vers un pas de 30 min.

Le calcul n'est PAS change : on garde l'interpolation, et on AFFICHE l'ecart.
  - Les apports CALES ne sont pas concernes : le calage les reecrit en
    entier a chaque essai.
  - Sous SEUIL_ECART_RECADENCAGE (1 % de la pointe), une ligne d'information.
  - Au-dessus, la ligne porte « AVERTISSEMENT » : l'etape Suivi la remonte
    alors sous sa banniere.

    python -m pytest src/test_recadencage_ecart.py -q
"""
import contextlib
import io
import sys
from pathlib import Path

import numpy as np
import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

pytest.importorskip("ras_commander")

import pilote_hecras as ph  # noqa: E402
import test_pilote_recadence as filet  # noqa: E402  (fabrique des .u02)


def crue(duree_h, montee_h, pas_min, pointe=250.0, base=5.0):
    """Montee rapide, longue decrue ; echantillonnee au pas, au centieme."""
    t = np.arange(0, duree_h + 1e-9, pas_min / 60.0)
    x = t / montee_h
    return [round(float(v), 2)
            for v in base + (pointe - base) * x ** 3 * np.exp(3 * (1 - x))]


ECLAIR_15 = crue(8, 0.75, 15)        # pointe a 45 min, donnee a 15 min
LENTE_15 = crue(48, 12.25, 15)       # pointe a 12 h 15, donnee a 15 min
ECLAIR_30 = crue(8, 1.0, 30)         # donnee a 30 min : 6 min la divise


def _ecart_independant(valeurs, pas_avant, apres, pas_apres):
    """La meme mesure, refaite ici : les deux series lues lineairement."""
    t0 = np.arange(len(valeurs)) * pas_avant
    t1 = np.arange(len(apres)) * pas_apres
    instants = np.union1d(t0, t1[t1 <= t0[-1] + 1e-9])
    return float(np.max(np.abs(np.interp(instants, t1, apres)
                               - np.interp(instants, t0, valeurs))))


# --- la mesure, dans le compte rendu -----------------------------------------

def test_le_compte_rendu_mesure_l_ecart_a_la_serie_d_origine(tmp_path):
    u = tmp_path / "ESSAI.u02"
    u.write_bytes(filet.unsteady(filet.bloc("AMONT", ECLAIR_15, "15MIN")))

    cr = ph.imposer_intervalle_apport(u, "AMONT", None, intervalle="6MIN")

    carte = ph.cartographier_hydrogrammes(u, None)["AMONT"]
    apres = ph.lire_hydrogramme_unsteady(u, carte["debut"], carte["fin"])
    attendu = _ecart_independant(ECLAIR_15, 0.25, apres, 0.1)
    assert attendu > 5.0, "le cas doit raboter la pointe pour prouver quoi que ce soit"
    # au centieme pres : le fichier est ecrit avec deux decimales
    assert cr["ecart_max"] == pytest.approx(attendu, abs=0.011)


def test_un_pas_diviseur_ne_deplace_rien(tmp_path):
    u = tmp_path / "ESSAI.u02"
    u.write_bytes(filet.unsteady(filet.bloc("AMONT", ECLAIR_30, "30MIN")))

    cr = ph.imposer_intervalle_apport(u, "AMONT", None, intervalle="6MIN")

    assert cr["ecart_max"] == pytest.approx(0.0, abs=1e-9)
    assert cr["pic_apres"] == pytest.approx(cr["pic_avant"])


# --- l'affichage --------------------------------------------------------------

def _journal(tmp_path, blocs, pas_h, apports=None, plan=None):
    cas = dict(u=filet.unsteady(*blocs), pas=pas_h)
    if apports:
        cas["apports"] = apports
    if plan:
        cas["p"] = plan
    pilote = filet._pilote(tmp_path / "jeu", cas)
    sortie = io.StringIO()
    with contextlib.redirect_stdout(sortie):
        pilote._recadencer_apports()
    return [ligne for ligne in sortie.getvalue().splitlines()
            if "pointe" in ligne]


def test_une_condition_non_calee_rabotee_est_un_avertissement(tmp_path):
    lignes = _journal(tmp_path, [filet.bloc("AMONT", ECLAIR_15, "15MIN")], 0.1)

    assert len(lignes) == 1
    ligne = lignes[0]
    assert "AVERTISSEMENT" in ligne and "« AMONT »" in ligne
    assert "15 min" in ligne and "6 min" in ligne
    # les deux pointes et l'ecart, en clair
    assert f"{max(ECLAIR_15):.2f}" in ligne
    assert "%" in ligne


def test_sous_le_seuil_l_ecart_est_dit_sans_avertissement(tmp_path):
    lignes = _journal(tmp_path, [filet.bloc("AMONT", LENTE_15, "15MIN")], 0.1)

    assert len(lignes) == 1
    assert "AVERTISSEMENT" not in lignes[0]
    assert "« AMONT »" in lignes[0] and "%" in lignes[0]


def test_un_pas_diviseur_ne_dit_rien(tmp_path):
    assert _journal(tmp_path, [filet.bloc("AMONT", ECLAIR_30, "30MIN")],
                    0.1) == []


def test_un_apport_cale_ne_dit_rien(tmp_path):
    """Le calage le reecrit en entier : son re-cadencage ne compte pas."""
    lignes = _journal(tmp_path, [filet.bloc("SUH01", ECLAIR_15, "15MIN")],
                      0.1, apports=["SUH01"])

    assert lignes == []


def test_seule_la_condition_non_calee_est_signalee(tmp_path):
    lignes = _journal(tmp_path, [filet.bloc("AMONT", ECLAIR_15, "15MIN"),
                                 filet.bloc("SUH01", ECLAIR_15, "15MIN")],
                      0.1, apports=["SUH01"])

    assert len(lignes) == 1 and "« AMONT »" in lignes[0]


def test_un_pas_de_travail_plus_grossier_est_signale(tmp_path):
    """Cible a 30 min, condition amont a 6 min : c'est le cas le plus severe."""
    fine = crue(8, 0.75, 6)
    lignes = _journal(tmp_path, [filet.bloc("AMONT", fine, "6MIN")], 0.5)

    assert len(lignes) == 1 and "AVERTISSEMENT" in lignes[0]


def test_le_seuil_est_un_pour_cent_de_la_pointe():
    assert ph.SEUIL_ECART_RECADENCAGE == 0.01
