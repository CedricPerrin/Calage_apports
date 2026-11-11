"""
Caracterisation de criteres.diagnostiquer() : ce qu'elle rend, fige au bit
pres.

POURQUOI. diagnostiquer() prononce le verdict de chaque essai — volume,
pointe, forme, decalage, couverture, fenetre jugee, alertes, reserves. Trois
de ses defauts sont partis chez un client avant d'etre vus (la fenetre lue sur
la mauvaise base de temps, le decalage compte deux fois dans la couverture, le
biais du KGE trace sous le nom du volume) : aucun ne levait d'exception, tous
rendaient des nombres plausibles. Le banc (src/bancs/banc_criteres.py) verifie
des BANDES ; ce fichier fige la VALEUR, pour qu'un remaniement ne deplace rien.

DEUX FILETS, DANS UNE SEULE REFERENCE :
  - des scenarios NOMMES, un par branche, par alerte, par reserve et par cas
    limite qui a deja coute — le Diagnostic entier y est fige, champ par
    champ, ou l'exception quand la fonction en leve une ;
  - un LOT de quelques centaines d'entrees tirees par un generateur
    congruentiel ecrit ici (ni numpy.random, ni fonction transcendante : les
    memes entrees, au bit pres, sur tout poste et toute version de numpy). De
    chacune on garde le resume lisible et l'empreinte du Diagnostic entier.
Les entrees sont relues apres l'appel : diagnostiquer() ne doit pas y toucher.

AU BIT PRES, SUR LE SOCLE QUI A FIGE. Les flottants sont ecrits par
float.hex(). Ailleurs (autre numpy, autre systeme, autre machine) le dernier
bit d'une interpolation ou d'une correlation peut differer : le test se
REPLIE, et le DIT par un avertissement. Le repli compare les grandeurs
calculees a 1e-9 pres en relatif, et EXACTEMENT tout le reste — verdicts,
textes des alertes, exceptions, ce que le Diagnostic recopie de ses entrees.
Ce qu'il ne voit pas : un ecart sous 1e-9, par construction. Ce qui peut le
faire echouer a tort : un nombre qui tombe sur une frontiere d'arrondi dans
le texte d'une alerte, un rapport pose exactement sur un seuil, deux maxima
egaux dont le premier change. Avant de remanier diagnostiquer() sur un autre
poste, refiger la reference SUR LE CODE D'ORIGINE.

CE TEST NE DIT PAS CE QUE LE CODE DEVRAIT FAIRE : il enregistre ce qu'il fait.

    python -m pytest src/test_caracterisation_diagnostic.py
    python src/test_caracterisation_diagnostic.py --figer   (reecrit la reference)
"""
import dataclasses
import hashlib
import json
import platform
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import criteres as cr

REFERENCE = Path(__file__).resolve().parent / "reference_diagnostic.json"


# ---------------------------------------------------------------------------
# Figer une valeur
# ---------------------------------------------------------------------------

def _figer(v):
    """
    Forme JSON d'une valeur, sans perte : le type y est, les flottants sont en
    hexadecimal, les tableaux en empreinte. Un type inconnu LEVE.
    """
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, np.bool_):
        return f"np.bool:{bool(v)}"
    if isinstance(v, np.floating):          # avant float : np.float64 en herite
        return f"{type(v).__name__}:{float(v).hex()}"
    if isinstance(v, np.integer):
        return f"{type(v).__name__}:{int(v)}"
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return f"f:{v.hex()}"
    if isinstance(v, np.ndarray):
        a = np.ascontiguousarray(v)
        return (f"nd:{a.dtype}:{'x'.join(map(str, a.shape))}:"
                f"{hashlib.sha256(a.tobytes()).hexdigest()[:24]}")
    if isinstance(v, tuple):
        return {"tuple": [_figer(x) for x in v]}
    if isinstance(v, list):
        return [_figer(x) for x in v]
    if isinstance(v, dict):
        return {"dict": {str(k): _figer(x) for k, x in v.items()}}
    if isinstance(v, BaseException):
        return {"exception": type(v).__name__, "message": str(v)}
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        fige = {"classe": type(v).__name__}
        for champ in dataclasses.fields(v):
            fige[champ.name] = _figer(getattr(v, champ.name))
        return fige
    raise TypeError(f"valeur non figeable : {type(v).__name__}")


def _jouer(arguments, nommes):
    """
    Appelle diagnostiquer() et rend ce qu'on en fige : le Diagnostic entier,
    son verdict et son resume — ou l'exception. Verifie au passage que les
    entrees n'ont pas ete modifiees.
    """
    avant = json.dumps(_figer([list(arguments), nommes]), sort_keys=True)
    with warnings.catch_warnings():
        # numpy previent (division par zero, moyenne d'un tableau vide) sur
        # les entrees degenerees : c'est le sujet, pas un incident.
        warnings.simplefilter("ignore")
        try:
            d = cr.diagnostiquer(*arguments, **nommes)
        except Exception as e:                              # noqa: BLE001
            fige = {"leve": _figer(e)}
        else:
            fige = {"diagnostic": _figer(d), "converge": _figer(d.converge),
                    "resume": d.resume()}
    apres = json.dumps(_figer([list(arguments), nommes]), sort_keys=True)
    fige["entrees_intactes"] = avant == apres
    return fige


# ---------------------------------------------------------------------------
# Scenarios nommes
# ---------------------------------------------------------------------------

def _hydro(t, pic, t_pic=6.0, forme=2.5):
    """Le meme que celui du banc de criteres.py."""
    t = np.maximum(np.asarray(t, dtype=float), 1e-3)
    return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))


T = np.linspace(0.01, 30, 400)
CIBLE = _hydro(T, pic=100.0)

# --- § 7 du banc : une mini-crue avant l'evenement cale ---------------------
_T48 = np.linspace(0.0, 48.0, 481)
_PRINCIPAL = _hydro(_T48 - 24.0, pic=100.0, t_pic=6.0, forme=3.0)
_CIBLE7 = _hydro(_T48, pic=20.0, t_pic=4.0, forme=3.0) + _PRINCIPAL
_CALC7 = _hydro(_T48, pic=40.0, t_pic=4.0, forme=3.0) + _PRINCIPAL
# --- § 7 bis : un transitoire de demarrage plus haut que l'evenement --------
_CALC7B = (_hydro(_T48 - 25.5, pic=100.0, t_pic=6.0, forme=3.0)
           + _hydro(_T48, pic=160.0, t_pic=4.0, forme=3.0))
# --- § 7 ter : la fenetre ferme dans la decrue, le modele deverse ensuite ---
_CIBLE7T = _hydro(_T48, pic=100.0, t_pic=6.0, forme=3.0)
_CALC7T = _CIBLE7T + 12.0 * np.exp(-((_T48 - 22.0) / 7.0) ** 2)
# --- § 7 ter bis : le modele repond 4,6 h AVANT la cible (22/09/2026) -------
_TC80 = np.linspace(0.0, 80.0, 1601)
_TS20 = np.linspace(0.0, 20.5, 411)
_CIBLE80 = _hydro(_TC80, pic=120.0, t_pic=9.5, forme=2.0)
_CALC20 = _hydro(_TS20 + 4.6, pic=120.0, t_pic=9.5, forme=2.0)
# --- § 7 quinquies : la fenetre est en temps de SIMULATION (08/09/2026) -----
_TQ = np.arange(0.0, 40.0 + 1e-9, 0.1)
_CQ = 3.25 * np.exp(-0.5 * ((_TQ - 0.5) / 1.2) ** 2) + 0.05
_SQ = np.interp(_TQ - 2.6, _TQ, _CQ)
# --- un evenement etroit, pour les decalages plus longs que la fenetre ------
_T40 = np.linspace(0.0, 40.0, 401)


def _bosse(t, centre, largeur=1.0, pic=50.0):
    return pic * np.exp(-0.5 * ((np.asarray(t, dtype=float) - centre)
                                / largeur) ** 2)


def _retarde(heures, t=T, q=CIBLE):
    """La meme serie, lue « heures » plus tard (valeur de bord au-dela)."""
    return np.interp(t - heures, t, q)


def _avec_nan(q, rang):
    q = np.array(q, dtype=float)
    q[rang] = float("nan")
    return q


def _cas(*arguments, **nommes):
    return arguments, nommes


SCENARIOS = {
    # --- sans fenetre : l'essentiel ----------------------------------------
    "identite": lambda: _cas(T, CIBLE, T, CIBLE),
    "retard_pur_3h": lambda: _cas(T, CIBLE, T, _retarde(3.0)),
    "avance_pure_2h": lambda: _cas(T, CIBLE, T, _retarde(-2.0)),
    "apport_sous_dimensionne": lambda: _cas(T, CIBLE, T, 0.75 * CIBLE),
    "apport_sur_dimensionne_et_retarde": lambda: _cas(
        T, CIBLE, T, 1.3 * _retarde(1.5)),
    "origines_differentes": lambda: _cas(
        T + 2.0, CIBLE, np.linspace(0.0, 40.0, 500),
        _hydro(np.linspace(0.0, 40.0, 500) - 2.0, 100.0)),
    "simulation_plus_longue": lambda: _cas(
        T, CIBLE, np.linspace(0.01, 48, 700),
        _hydro(np.linspace(0.01, 48, 700), 100.0)),
    "simulation_tronquee_bloquante": lambda: _cas(
        T, CIBLE, np.linspace(0.01, 20, 300),
        _hydro(np.linspace(0.01, 20, 300), 100.0)),
    "simulation_tronquee_entre_90_et_100": lambda: _cas(
        T, CIBLE, np.linspace(0.01, 28.5, 380),
        _hydro(np.linspace(0.01, 28.5, 380), 100.0)),
    "couverture_min_a_50": lambda: _cas(
        T, CIBLE, np.linspace(0.01, 20, 300),
        _hydro(np.linspace(0.01, 20, 300), 100.0), couverture_min=0.5),
    "couverture_min_a_100": lambda: _cas(
        T, CIBLE, np.linspace(0.01, 29.9, 380),
        _hydro(np.linspace(0.01, 29.9, 380), 100.0), couverture_min=1.0),
    "fenetres_disjointes": lambda: _cas(
        T, CIBLE, np.linspace(50, 80, 300),
        _hydro(np.linspace(50, 80, 300) - 50.0, 100.0)),
    "series_qui_se_touchent_en_un_point": lambda: _cas(
        T, CIBLE, np.linspace(30, 60, 300),
        _hydro(np.linspace(30, 60, 300) - 30.0, 100.0)),
    "retard_qui_coupe_la_decrue": lambda: _cas(
        np.linspace(0.01, 12, 160), _hydro(np.linspace(0.01, 12, 160), 100.0),
        np.linspace(0.01, 12, 160),
        _hydro(np.linspace(0.01, 12, 160) - 1.6, 100.0)),
    "decalage_plus_long_que_le_recouvrement": lambda: _cas(
        np.linspace(0.0, 10.0, 101), _bosse(np.linspace(0.0, 10.0, 101), 2.0),
        np.linspace(6.0, 16.0, 101), _bosse(np.linspace(6.0, 16.0, 101), 14.0)),
    "decalage_egal_au_recouvrement": lambda: _cas(
        np.linspace(0.0, 10.0, 101), _bosse(np.linspace(0.0, 10.0, 101), 3.0),
        np.linspace(6.0, 16.0, 101), _bosse(np.linspace(6.0, 16.0, 101), 7.0)),
    "tolerances_serrees": lambda: _cas(
        T, CIBLE, T, 1.01 * CIBLE, tolerance_volume=0.005,
        tolerance_pic=0.005, r_min=0.9999),
    "tolerances_larges": lambda: _cas(
        T, CIBLE, T, 0.75 * CIBLE, tolerance_volume=0.30, tolerance_pic=0.30,
        r_min=0.5),
    "forme_differente_r_sous_le_seuil": lambda: _cas(
        T, CIBLE, T, _hydro(T, pic=100.0, t_pic=6.0, forme=0.6)),

    # --- pas de temps -------------------------------------------------------
    "cible_horaire_calcul_a_6_min": lambda: _cas(
        np.arange(0.0, 31.0, 1.0), _hydro(np.arange(0.0, 31.0, 1.0), 100.0),
        np.arange(0.0, 30.05, 0.1), _hydro(np.arange(0.0, 30.05, 0.1), 100.0)),
    "cible_a_la_minute": lambda: _cas(
        np.arange(0.0, 30.0, 1.0 / 60.0),
        _hydro(np.arange(0.0, 30.0, 1.0 / 60.0), 100.0), T, CIBLE),
    "pas_irregulier": lambda: _cas(
        np.cumsum(0.05 + 0.2 * (np.arange(150) % 5 == 0)),
        _hydro(np.cumsum(0.05 + 0.2 * (np.arange(150) % 5 == 0)), 100.0),
        T, CIBLE),
    "pas_de_recalage_au_quart_d_heure": lambda: _cas(
        T, CIBLE, T, _retarde(1.6), 0.25),
    "pas_de_recalage_fin_avec_fenetre": lambda: _cas(
        _T48, _CIBLE7, _T48, _CALC7, pas_h=0.05, fenetre=(18.0, 40.0)),

    # --- la fenetre du hydrogramme principal --------------------------------
    "mini_crue_sans_fenetre": lambda: _cas(_T48, _CIBLE7, _T48, _CALC7),
    "mini_crue_avec_fenetre": lambda: _cas(
        _T48, _CIBLE7, _T48, _CALC7, fenetre=(18.0, 40.0)),
    "pic_parasite_sans_fenetre": lambda: _cas(_T48, _CIBLE7, _T48, _CALC7B),
    "pic_parasite_avec_fenetre": lambda: _cas(
        _T48, _CIBLE7, _T48, _CALC7B, fenetre=(18.0, 40.0)),
    "perimetre_du_verdict": lambda: _cas(
        _T48, _CIBLE7T, _T48, _CALC7T, tolerance_volume=0.05,
        fenetre=(0.5, 14.0)),
    "perimetre_serie_a_peine_hors_bande": lambda: _cas(
        _T48, _CIBLE7T, _T48,
        _CIBLE7T + 5.0 * np.exp(-((_T48 - 22.0) / 7.0) ** 2),
        fenetre=(0.5, 14.0)),
    "perimetre_avec_une_fenetre_en_temps_de_simulation": lambda: _cas(
        _T48, _CIBLE7T, _T48, np.interp(_T48 - 2.0, _T48, _CALC7T),
        fenetre=(2.5, 16.0), decalage_fenetre_h=2.0),
    "perimetre_tu_quand_le_verdict_est_hors_bande": lambda: _cas(
        _T48, _CIBLE7T, _T48, 1.2 * _CALC7T, fenetre=(0.5, 14.0)),
    "fenetre_sur_toute_la_serie": lambda: _cas(
        T, CIBLE, T, CIBLE, fenetre=(0.01, 30.0)),
    "fenetre_plus_large_que_les_series": lambda: _cas(
        T, CIBLE, T, _retarde(1.0), fenetre=(-5.0, 60.0)),
    "fenetre_donnee_en_liste_d_entiers": lambda: _cas(
        _T48, _CIBLE7, _T48, _CALC7, fenetre=[18, 40]),
    "fenetre_donnee_en_tableau": lambda: _cas(
        _T48, _CIBLE7, _T48, _CALC7, fenetre=np.array([18.0, 40.0])),
    "pic_sur_le_bord_gauche_de_la_fenetre": lambda: _cas(
        _T48, _PRINCIPAL, _T48, _PRINCIPAL, fenetre=(30.0, 44.0)),
    "pic_sur_le_bord_droit_de_la_fenetre": lambda: _cas(
        _T48, _PRINCIPAL, _T48, _PRINCIPAL, fenetre=(20.0, 30.0)),
    "fenetre_hors_de_la_cible": lambda: _cas(
        T, CIBLE, np.linspace(0.01, 60, 800),
        _hydro(np.linspace(0.01, 60, 800), 100.0), fenetre=(40.0, 55.0)),
    "fenetre_hors_des_deux_series": lambda: _cas(
        T, CIBLE, T, CIBLE, fenetre=(100.0, 120.0)),
    "fenetre_entre_deux_pas": lambda: _cas(
        np.arange(0.0, 31.0, 1.0), _hydro(np.arange(0.0, 31.0, 1.0), 100.0),
        np.arange(0.0, 31.0, 1.0), _hydro(np.arange(0.0, 31.0, 1.0), 100.0),
        fenetre=(6.2, 6.8)),
    "fenetre_d_un_seul_instant": lambda: _cas(
        T, CIBLE, T, CIBLE, fenetre=(6.0, 6.0)),
    "fenetre_a_l_envers": lambda: _cas(
        T, CIBLE, T, CIBLE, fenetre=(20.0, 5.0)),
    "fenetre_plus_courte_que_le_pas_de_recalage": lambda: _cas(
        T, CIBLE, T, CIBLE, fenetre=(6.0, 6.04)),
    "fenetre_que_le_calcul_ne_couvre_qu_a_moitie": lambda: _cas(
        _T48, _CIBLE7, _T48[_T48 <= 30.0], _CALC7[_T48 <= 30.0],
        fenetre=(18.0, 40.0)),
    "fenetre_que_le_calcul_couvre_a_95": lambda: _cas(
        _T48, _CIBLE7, _T48[_T48 <= 38.9], _CALC7[_T48 <= 38.9],
        fenetre=(18.0, 40.0)),
    "fenetre_sans_recouvrement_des_series": lambda: _cas(
        T, CIBLE, np.linspace(50, 80, 300),
        _hydro(np.linspace(50, 80, 300) - 50.0, 100.0), fenetre=(5.0, 60.0)),

    # --- la fenetre en temps de simulation, et son Dt -----------------------
    "fenetre_en_temps_de_simulation_sans_son_dt": lambda: _cas(
        _TQ, _CQ, _TQ, _SQ, fenetre=(2.10, 32.70)),
    "fenetre_en_temps_de_simulation_avec_son_dt": lambda: _cas(
        _TQ, _CQ, _TQ, _SQ, fenetre=(2.10, 32.70), decalage_fenetre_h=2.6),
    "dt_de_fenetre_nul_explicite": lambda: _cas(
        _T48, _CIBLE7, _T48, _CALC7, fenetre=(18.0, 40.0),
        decalage_fenetre_h=0.0),
    "dt_de_fenetre_sans_fenetre": lambda: _cas(
        T, CIBLE, T, _retarde(3.0), decalage_fenetre_h=3.0),
    "dt_de_fenetre_qui_n_est_pas_le_decalage": lambda: _cas(
        _TQ, _CQ, _TQ, _SQ, fenetre=(2.10, 32.70), decalage_fenetre_h=1.0),
    "modele_en_avance_fenetre_simulee_en_entier": lambda: _cas(
        _TC80, _CIBLE80, _TS20, _CALC20, fenetre=(0.0, 18.0),
        decalage_fenetre_h=-4.6),
    "modele_en_avance_simulation_trop_courte": lambda: _cas(
        _TC80, _CIBLE80, _TS20[_TS20 <= 15.0], _CALC20[_TS20 <= 15.0],
        fenetre=(0.0, 18.0), decalage_fenetre_h=-4.6),
    "modele_en_avance_sans_dt_de_fenetre": lambda: _cas(
        _TC80, _CIBLE80, _TS20, _CALC20, fenetre=(0.0, 18.0)),
    "marge_de_fenetre_qui_deborde_de_la_cible": lambda: _cas(
        _TQ, _CQ, _TQ, _SQ, fenetre=(0.5, 32.70), decalage_fenetre_h=2.6),
    "decalage_plus_long_que_la_fenetre": lambda: _cas(
        _T40, _bosse(_T40, 14.0, 2.5), _T40, _bosse(_T40, 3.0, 1.0),
        fenetre=(0.0, 10.3), decalage_fenetre_h=-11.0),
    "grand_retard_sur_des_series_qui_se_recouvrent_a_peine": lambda: _cas(
        np.linspace(0.0, 10.0, 101), _bosse(np.linspace(0.0, 10.0, 101), 4.0),
        np.linspace(8.0, 18.0, 101), _bosse(np.linspace(8.0, 18.0, 101), 12.0),
        fenetre=(8.5, 17.5), decalage_fenetre_h=8.0),
    "decalage_plus_long_que_la_fenetre_et_rien_de_comparable": lambda: _cas(
        np.linspace(0.0, 10.0, 101), _bosse(np.linspace(0.0, 10.0, 101), 1.0),
        np.linspace(0.0, 10.0, 101), _bosse(np.linspace(0.0, 10.0, 101), 9.5),
        fenetre=(8.0, 10.0), decalage_fenetre_h=8.5),

    # --- reserves -----------------------------------------------------------
    "apport_peu_identifiable": lambda: _cas(
        T, CIBLE, T, CIBLE, part_apport=0.02),
    "apport_peu_identifiable_et_non_conforme": lambda: _cas(
        T, CIBLE, T, 0.75 * CIBLE, part_apport=0.02),
    "apport_qui_pese_assez": lambda: _cas(
        T, CIBLE, T, CIBLE, part_apport=0.4),
    "part_egale_a_la_tolerance": lambda: _cas(
        T, CIBLE, T, CIBLE, part_apport=0.05),
    "part_nulle_ou_negative": lambda: _cas(
        T, CIBLE, T, CIBLE, part_apport=-0.01),
    "toutes_les_alertes_ensemble": lambda: _cas(
        _T48, _CIBLE7T, _T48[_T48 <= 13.5], _CALC7T[_T48 <= 13.5],
        fenetre=(0.5, 14.0), part_apport=0.01),
    "perimetre_et_reserve_d_identifiabilite": lambda: _cas(
        _T48, _CIBLE7T, _T48, _CALC7T, fenetre=(0.5, 14.0), part_apport=0.03),

    # --- series degenerees --------------------------------------------------
    "calcul_constant": lambda: _cas(T, CIBLE, T, np.full_like(T, 12.0)),
    "calcul_nul": lambda: _cas(T, CIBLE, T, np.zeros_like(T)),
    "cible_constante": lambda: _cas(T, np.full_like(T, 12.0), T, CIBLE),
    "cible_nulle": lambda: _cas(T, np.zeros_like(T), T, CIBLE),
    "cible_nulle_avec_fenetre": lambda: _cas(
        T, np.zeros_like(T), T, CIBLE, fenetre=(2.0, 20.0)),
    "les_deux_nulles": lambda: _cas(T, np.zeros_like(T), T, np.zeros_like(T)),
    "calcul_constant_dans_la_fenetre": lambda: _cas(
        _T48, _CIBLE7, _T48, np.where(_T48 >= 17.0, 30.0, _CALC7),
        fenetre=(18.0, 40.0)),
    "nan_dans_le_calcul": lambda: _cas(T, CIBLE, T, _avec_nan(CIBLE, 80)),
    "nan_dans_la_cible": lambda: _cas(T, _avec_nan(CIBLE, 80), T, CIBLE),
    "nan_dans_le_calcul_hors_fenetre": lambda: _cas(
        _T48, _CIBLE7, _T48, _avec_nan(_CALC7, 20), fenetre=(18.0, 40.0)),
    "nan_dans_le_calcul_dans_la_fenetre": lambda: _cas(
        _T48, _CIBLE7, _T48, _avec_nan(_CALC7, 300), fenetre=(18.0, 40.0)),
    "infini_dans_le_calcul": lambda: _cas(
        T, CIBLE, T, np.where(np.arange(T.size) == 80, np.inf, CIBLE)),
    "debits_negatifs": lambda: _cas(T, CIBLE - 20.0, T, CIBLE - 25.0),
    "cible_toute_negative": lambda: _cas(T, -CIBLE - 1.0, T, -CIBLE - 2.0),
    "listes_python_et_entiers": lambda: _cas(
        [0, 1, 2, 3, 4, 5, 6, 7, 8], [0, 1, 4, 9, 6, 3, 1, 0, 0],
        [0, 1, 2, 3, 4, 5, 6, 7, 8], [0, 0, 1, 4, 9, 6, 3, 1, 0]),
    "deux_points_par_serie": lambda: _cas(
        [0.0, 10.0], [1.0, 5.0], [0.0, 10.0], [1.0, 5.0]),
    "cible_d_un_seul_point": lambda: _cas([5.0], [3.0], T, CIBLE),
    "calcul_d_un_seul_point": lambda: _cas(T, CIBLE, [5.0], [3.0]),
    "temps_decroissant": lambda: _cas(T[::-1], CIBLE[::-1], T, CIBLE),
    "cible_vide": lambda: _cas([], [], T, CIBLE),
    "calcul_vide": lambda: _cas(T, CIBLE, [], []),
    "longueurs_incoherentes": lambda: _cas(T, CIBLE[:-3], T, CIBLE),
    "pas_de_recalage_nul": lambda: _cas(T, CIBLE, T, CIBLE, 0.0),

    # --- arguments illisibles : QUELLE exception, et d'ou -------------------
    "fenetre_illisible": lambda: _cas(T, CIBLE, T, CIBLE, fenetre=("a", "b")),
    "fenetre_a_une_seule_borne": lambda: _cas(
        T, CIBLE, T, CIBLE, fenetre=(5.0,)),
    "fenetre_dont_une_borne_manque": lambda: _cas(
        T, CIBLE, T, CIBLE, fenetre=(None, 20.0)),
    "dt_de_fenetre_illisible": lambda: _cas(
        T, CIBLE, T, CIBLE, fenetre=(2.0, 20.0), decalage_fenetre_h="x"),
    "debits_illisibles": lambda: _cas(T, ["a"] * T.size, T, CIBLE),
}


# ---------------------------------------------------------------------------
# Le lot pseudo-aleatoire
# ---------------------------------------------------------------------------

GRAINE = 20261110
TAILLE_DU_LOT = 400


class _Hasard:
    """
    Generateur congruentiel a 64 bits (constantes de Knuth, MMIX). Ecrit ICI
    pour que le lot soit le meme partout : le flux de numpy.random n'est pas
    garanti d'une version a l'autre, celui-ci ne depend que d'entiers Python.
    """

    def __init__(self, graine):
        self._x = graine & 0xFFFFFFFFFFFFFFFF

    def reel(self):
        """Dans [0, 1) : les 53 bits de poids fort, division exacte."""
        self._x = (6364136223846793005 * self._x
                   + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return (self._x >> 11) / 9007199254740992.0

    def entre(self, bas, haut):
        return bas + (haut - bas) * self.reel()

    def entier(self, bas, haut):
        """Dans [bas, haut], bornes comprises."""
        return bas + int(self.reel() * (haut - bas + 1))

    def parmi(self, choix):
        return choix[int(self.reel() * len(choix))]

    def chance(self, p):
        return self.reel() < p


def _crue(t, bosses, base):
    """
    Somme de bosses RATIONNELLES sur un debit de base. Quatre operations
    seulement, pas d'exponentielle : le resultat est le meme, au bit pres,
    sur toute machine IEEE 754.
    """
    q = [base] * len(t)
    for pic, centre, largeur in bosses:
        ecarts = [(x - centre) / largeur for x in t]
        # u * u, et non u ** 2 : la puissance passe par la bibliotheque C.
        q = [v + pic / (1.0 + u * u) for v, u in zip(q, ecarts)]
    return q


def _axe(h, debut):
    n = h.entier(3, 260)
    pas = h.parmi([0.05, 0.1, 0.1, 0.1, 0.25, 0.5, 1.0])
    if h.chance(0.1):                       # pas irregulier
        t, x = [], debut
        for _ in range(n):
            t.append(x)
            x += pas * h.entre(0.3, 2.5)
        return t
    return [debut + k * pas for k in range(n)]


def _entree_du_lot(h):
    """Un appel a diagnostiquer(), tire au sort : (arguments, nommes)."""
    tc = _axe(h, h.entre(0.0, 6.0) if h.chance(0.5) else 0.0)
    duree = tc[-1] - tc[0]
    # UN TIERS DE CALAGES A PEU PRES JUSTES : sans eux le lot ne verrait que
    # des refus, et les branches du verdict favorable — celles qui decident
    # d'une etude — resteraient au seul soin des scenarios nommes.
    juste = h.chance(0.35)
    nature = h.reel()
    if juste:
        debut_s = tc[0]
    elif nature < 0.08:                     # axes disjoints ou presque
        debut_s = tc[-1] + h.entre(-1.0, 20.0)
    elif nature < 0.45:                     # meme origine
        debut_s = tc[0]
    else:
        debut_s = tc[0] + h.entre(-0.5, 0.5) * max(duree, 1.0)
    ts = _axe(h, debut_s)

    centre = tc[0] + h.entre(0.05, 0.95) * max(duree, 0.5)
    largeur = h.entre(0.03, 0.3) * max(duree, 0.5)
    bosses = [(h.entre(1.0, 500.0), centre, largeur)]
    for _ in range(h.entier(0, 2)):         # crues secondaires
        bosses.append((h.entre(0.5, 300.0),
                       tc[0] + h.entre(-0.2, 1.2) * max(duree, 0.5),
                       h.entre(0.02, 0.2) * max(duree, 0.5)))
    base = h.entre(0.0, 20.0) if h.chance(0.5) else 0.0
    decalage = h.parmi([0.0, 0.0, h.entre(-0.4, 0.4) * max(duree, 0.5),
                        h.entre(-3.0, 3.0), h.entre(-15.0, 15.0)])
    echelle = h.parmi([1.0, 1.0, h.entre(0.9, 1.1), h.entre(0.3, 2.5)])
    if juste:
        decalage = h.parmi([0.0, h.entre(-0.1, 0.1) * max(duree, 0.5)])
        echelle = h.entre(0.97, 1.03)
    bosses_s = [(pic * echelle, c + decalage, w) for pic, c, w in bosses]
    if not juste and h.chance(0.25):        # le modele ajoute sa propre bosse
        bosses_s.append((h.entre(0.5, 400.0),
                         ts[0] + h.entre(0.0, 1.0) * max(ts[-1] - ts[0], 0.5),
                         h.entre(0.02, 0.3) * max(duree, 0.5)))
    qc = _crue(tc, bosses, base)
    qs = _crue(ts, bosses_s,
               base if juste or h.chance(0.8) else h.entre(0.0, 30.0))

    degenere = 1.0 if juste else h.reel()
    if degenere < 0.03:
        qs = [h.entre(0.0, 50.0)] * len(ts)                 # calcul constant
    elif degenere < 0.05:
        qc = [0.0] * len(tc)                                # cible nulle
    elif degenere < 0.07:
        qs[h.entier(0, len(qs) - 1)] = float("nan")
    elif degenere < 0.08:
        qc[h.entier(0, len(qc) - 1)] = float("nan")
    elif degenere < 0.09:
        qc = [h.entre(0.0, 50.0)] * len(tc)                 # cible constante
    elif degenere < 0.10:
        tc, qc = tc[:1], qc[:1]

    nommes = {}
    if h.chance(0.65):
        f0 = tc[0] + h.entre(-0.3, 0.9) * max(duree, 0.5)
        f1 = f0 + h.entre(-0.05, 1.0) * max(duree, 0.5)
        nommes["fenetre"] = (f0, f1)
        tirage = h.reel()
        if tirage < 0.35:
            nommes["decalage_fenetre_h"] = decalage
        elif tirage < 0.5:
            nommes["decalage_fenetre_h"] = h.entre(-8.0, 8.0)
        elif tirage < 0.6:
            nommes["decalage_fenetre_h"] = 0.0
    if h.chance(0.3):
        nommes["tolerance_volume"] = h.parmi([0.005, 0.02, 0.1, 0.25])
    if h.chance(0.2):
        nommes["tolerance_pic"] = h.parmi([0.005, 0.05, 0.2])
    if h.chance(0.2):
        nommes["r_min"] = h.parmi([0.5, 0.9, 0.999])
    if h.chance(0.25):
        nommes["couverture_min"] = h.parmi([0.5, 0.75, 0.99, 1.0])
    if h.chance(0.3):
        nommes["part_apport"] = h.parmi([0.0, 0.004, 0.03, 0.2,
                                         h.entre(-0.1, 0.4)])
    if h.chance(0.15):
        nommes["pas_h"] = h.parmi([0.05, 0.25, 0.5])
    if h.chance(0.7):                       # tableaux, comme en production
        return (np.array(tc), np.array(qc), np.array(ts), np.array(qs)), nommes
    return (tc, qc, ts, qs), nommes


def _lot():
    """Les entrees du lot, dans l'ordre — toujours les memes."""
    h = _Hasard(GRAINE)
    return [_entree_du_lot(h) for _ in range(TAILLE_DU_LOT)]


# Ce que diagnostiquer() CALCULE. Le reste du Diagnostic est recopie de ses
# entrees (tolerances, fenetre, part de l'apport) ou fait de textes.
CALCULES = ("r", "decalage_h", "rapport_pic", "rapport_volume",
            "rapport_volume_serie", "part_cible_jugee")


def _empreinte(objet):
    return hashlib.sha256(
        json.dumps(objet, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:24]


def _condense(fige):
    """
    D'un cas du lot on garde les grandeurs calculees, en clair, et une
    empreinte de tout le reste : quatre cents Diagnostics entiers peseraient
    un megaoctet pour rien. Les nombres restent lisibles parce que le repli
    hors socle les compare a une tolerance pres ; une empreinte ne le
    permettrait pas.
    """
    if "leve" in fige:
        return {"leve": fige["leve"], "intactes": fige["entrees_intactes"]}
    d = fige["diagnostic"]
    return {"nombres": [d[c] for c in CALCULES],
            "converge": fige["converge"],
            "alertes": len(d["alertes"]),
            "bloquantes": len(d["alertes_bloquantes"]),
            "textes": _empreinte([d["alertes"], d["alertes_bloquantes"]]),
            "recopie": _empreinte({c: v for c, v in d.items()
                                   if c not in CALCULES
                                   and c not in ("alertes",
                                                 "alertes_bloquantes")}),
            "intactes": fige["entrees_intactes"]}


def _empreinte_des_entrees():
    """Les entrees du lot, toutes : la meme empreinte sur tout poste."""
    return _empreinte(_figer([[list(a), n] for a, n in _lot()]))


def _jouer_le_lot():
    return [_condense(_jouer(*entree)) for entree in _lot()]


# ---------------------------------------------------------------------------
# La reference
# ---------------------------------------------------------------------------

def _simd():
    """
    Les jeux d'instructions vectorielles que numpy EMPLOIE sur ce processeur.

    Ils font partie du socle (11/11/2026) : numpy choisit ses noyaux de calcul
    selon le processeur, et une somme faite avec ou sans AVX-512 differe d'un
    dernier bit. A versions egales, deux machines ne rendent donc PAS les
    memes octets ; sans cette ligne, le filet « au bit pres » echouait a tort
    sur un processeur different de celui qui a fige la reference.
    """
    try:
        from numpy._core._multiarray_umath import (__cpu_dispatch__ as cibles,
                                                   __cpu_features__ as vus)
    except ImportError:
        return "inconnu"
    return "+".join(c for c in cibles if vus.get(c)) or "base"


def _socle():
    return {"python": platform.python_version(), "numpy": np.__version__,
            "systeme": platform.system(), "machine": platform.machine(),
            "simd": _simd()}


def _meme_socle(produit_par):
    ici = _socle()
    return all(produit_par.get(c) == ici[c]
               for c in ("numpy", "systeme", "machine", "simd"))


TOLERANCE_HORS_SOCLE = 1e-9

_FLOTTANT = re.compile(r"(f|float\d+):(.+)")


def _nombre(texte):
    """(type, valeur) d'un flottant fige par _figer, ou None."""
    trouve = _FLOTTANT.fullmatch(texte) if isinstance(texte, str) else None
    if trouve is None:
        return None
    return trouve.group(1), float.fromhex(trouve.group(2))


def _proches(obtenu, attendu):
    """
    L'egalite du repli : les flottants a TOLERANCE_HORS_SOCLE pres en
    relatif (et a 1e-12 pres en absolu, pour ce qui vaut zero d'un cote),
    tout le reste — textes, booleens, structure, type des nombres —
    exactement.
    """
    if isinstance(attendu, dict):
        return (isinstance(obtenu, dict) and list(obtenu) == list(attendu)
                and all(_proches(obtenu[c], attendu[c]) for c in attendu))
    if isinstance(attendu, list):
        return (isinstance(obtenu, list) and len(obtenu) == len(attendu)
                and all(_proches(o, a) for o, a in zip(obtenu, attendu)))
    a, o = _nombre(attendu), _nombre(obtenu)
    if a is None or o is None:
        return obtenu == attendu
    if a[0] != o[0]:
        return False
    if a[1] == o[1] or (a[1] != a[1] and o[1] != o[1]):     # egaux, ou nan
        return True
    return (abs(a[1] - o[1])
            <= TOLERANCE_HORS_SOCLE * max(abs(a[1]), abs(o[1])) + 1e-12)


def _sans_derive(fige):
    """
    Hors socle, le resume ne se compare pas : il est fait des memes nombres,
    arrondis, et les nombres sont deja compares.
    """
    return {c: v for c, v in fige.items() if c != "resume"}


def _ecrire_reference():
    """UN CAS PAR LIGNE : le diff d'une reference refigee se relit."""
    def ligne(objet):
        return json.dumps(objet, ensure_ascii=False)

    scenarios = ",\n".join(
        f"  {ligne(nom)}: {ligne(_jouer(*SCENARIOS[nom]()))}"
        for nom in SCENARIOS)
    lot = ",\n".join(f"  {ligne(cas)}" for cas in _jouer_le_lot())
    a_propos = (
        "Caracterisation de criteres.diagnostiquer() : scenarios nommes et "
        "lot pseudo-aleatoire. NE PAS MODIFIER A LA MAIN : « python "
        "src/test_caracterisation_diagnostic.py --figer » le reecrit, quand "
        "le changement de comportement est VOULU.")
    REFERENCE.write_text(
        "{\n"
        f' "_a_propos": {ligne(a_propos)},\n'
        f' "_produit_par": {ligne(_socle())},\n'
        f' "graine": {GRAINE},\n'
        f' "entrees_du_lot": {ligne(_empreinte_des_entrees())},\n'
        ' "scenarios": {\n' + scenarios + "\n },\n"
        ' "lot": [\n' + lot + "\n ]\n}\n",
        encoding="utf-8")


def _lire_reference():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def _conforme(obtenu, attendu, produit_par):
    """obtenu vaut-il attendu — au bit pres ici, a la tolerance pres ailleurs ?"""
    obtenu = json.loads(json.dumps(obtenu, ensure_ascii=False))
    if _meme_socle(produit_par):
        return obtenu == attendu
    warnings.warn(
        f"reference produite sous {produit_par}, ici {_socle()} : les "
        f"grandeurs calculees sont comparees a {TOLERANCE_HORS_SOCLE:g} pres "
        f"en relatif, le reste exactement. L'identite AU BIT PRES n'est PAS "
        f"verifiee — refiger la reference sur le code d'origine avant de "
        f"remanier diagnostiquer() sur ce poste.")
    return _proches(_sans_derive(obtenu), _sans_derive(attendu))


def test_la_reference_couvre_les_scenarios_et_le_lot():
    assert REFERENCE.is_file(), (
        f"{REFERENCE.name} absent — le creer par "
        f"« python src/test_caracterisation_diagnostic.py --figer »")
    reference = _lire_reference()
    assert list(reference["scenarios"]) == list(SCENARIOS)
    assert reference["graine"] == GRAINE
    assert len(reference["lot"]) == TAILLE_DU_LOT


@pytest.mark.parametrize("nom", list(SCENARIOS))
def test_diagnostiquer_rend_ce_que_la_reference_a_enregistre(nom):
    reference = _lire_reference()
    obtenu, attendu = _jouer(*SCENARIOS[nom]()), reference["scenarios"][nom]
    assert _conforme(obtenu, attendu, reference["_produit_par"]), (
        f"\n   attendu : {json.dumps(attendu, ensure_ascii=False)}"
        f"\n   obtenu  : {json.dumps(obtenu, ensure_ascii=False)}")


def test_le_lot_pseudo_aleatoire_rend_les_memes_diagnostics():
    reference = _lire_reference()
    entrees, ecarts = _lot(), []
    for rang, (entree, attendu) in enumerate(zip(entrees, reference["lot"])):
        complet = _jouer(*entree)
        obtenu = _condense(complet)
        if not _conforme(obtenu, attendu, reference["_produit_par"]):
            ecarts.append(
                f"cas {rang}, options {sorted(entree[1])} :"
                f"\n      attendu : {json.dumps(attendu, ensure_ascii=False)}"
                f"\n      obtenu  : {json.dumps(obtenu, ensure_ascii=False)}"
                f"\n      entier  : {json.dumps(complet, ensure_ascii=False)}")
    assert not ecarts, (f"{len(ecarts)} cas sur {len(entrees)} different, "
                        f"dont :\n   " + "\n   ".join(ecarts[:3]))


def test_le_generateur_rend_toujours_le_meme_lot():
    """
    Le flux est fige par ses premieres valeurs, ecrites ici en clair : une
    retouche du generateur changerait tout le lot sans que rien ne le dise.
    """
    h = _Hasard(GRAINE)
    assert [h.reel().hex() for _ in range(3)] == PREMIERS_TIRAGES
    # ET LES ENTREES ELLES-MEMES, AU BIT PRES, MEME HORS DU SOCLE : elles ne
    # sont faites que d'additions, de produits et de divisions. Si cette
    # ligne echoue ailleurs, les ecarts du lot viennent des entrees, pas de
    # diagnostiquer().
    assert _empreinte_des_entrees() == _lire_reference()["entrees_du_lot"]


PREMIERS_TIRAGES = ["0x1.ee6a8dc1b0feep-2", "0x1.229598d4c469ep-1",
                    "0x1.720568f8e2390p-3"]


def _un_cran_plus_loin(fige):
    """Chaque flottant pousse au flottant voisin : ce qu'un autre numpy ferait."""
    if isinstance(fige, dict):
        return {c: _un_cran_plus_loin(v) for c, v in fige.items()}
    if isinstance(fige, list):
        return [_un_cran_plus_loin(v) for v in fige]
    nombre = _nombre(fige)
    if nombre is None:
        return fige
    return f"{nombre[0]}:{float(np.nextafter(nombre[1], np.inf)).hex()}"


def _conforme_ailleurs(obtenu, attendu, reference):
    """_conforme, comme si la reference venait d'un autre numpy."""
    ailleurs = {**reference["_produit_par"], "numpy": "un autre"}
    with pytest.warns(UserWarning, match="AU BIT PRES n'est PAS"):
        return _conforme(obtenu, attendu, ailleurs)


def test_le_repli_hors_socle_tolere_le_dernier_bit_et_rien_de_plus():
    """
    Le repli est joue ICI, sur un socle simule : sans cela il ne tournerait
    que la ou personne ne regarde, et un repli qui accepte tout passe aussi.
    """
    reference = _lire_reference()
    nom = "fenetre_en_temps_de_simulation_avec_son_dt"
    attendu = reference["scenarios"][nom]
    obtenu = json.loads(json.dumps(_jouer(*SCENARIOS[nom]())))

    # Le code sain passe, meme pousse d'un flottant partout.
    assert _conforme_ailleurs(obtenu, attendu, reference)
    assert _conforme_ailleurs(_un_cran_plus_loin(obtenu), attendu, reference)
    for cas in reference["lot"]:
        assert _conforme_ailleurs(_un_cran_plus_loin(cas), cas, reference)

    # Tout ecart qui compte est refuse : un millionieme sur un rapport...
    fausse = json.loads(json.dumps(obtenu))
    juste = _nombre(fausse["diagnostic"]["rapport_volume"])[1]
    fausse["diagnostic"]["rapport_volume"] = f"f:{(juste * (1 + 1e-6)).hex()}"
    assert not _conforme_ailleurs(fausse, attendu, reference)
    # ... un verdict retourne...
    fausse = json.loads(json.dumps(obtenu))
    fausse["converge"] = not fausse["converge"]
    assert not _conforme_ailleurs(fausse, attendu, reference)
    # ... un caractere dans une alerte, une bloquante qui manque.
    nom = "simulation_tronquee_bloquante"
    attendu_b = reference["scenarios"][nom]
    obtenu_b = json.loads(json.dumps(_jouer(*SCENARIOS[nom]())))
    fausse = json.loads(json.dumps(obtenu_b))
    fausse["diagnostic"]["alertes"][0] += "."
    assert not _conforme_ailleurs(fausse, attendu_b, reference)
    fausse = json.loads(json.dumps(obtenu_b))
    fausse["diagnostic"]["alertes_bloquantes"] = []
    assert not _conforme_ailleurs(fausse, attendu_b, reference)

    # Sur le socle de la reference, en revanche, un seul bit suffit.
    assert not _conforme(_un_cran_plus_loin(obtenu), attendu, _socle())


def test_aucune_entree_n_est_modifiee():
    """diagnostiquer() est une fonction pure : la reference le dit partout."""
    reference = _lire_reference()
    assert all(s["entrees_intactes"] for s in reference["scenarios"].values())
    assert all(c["intactes"] for c in reference["lot"])


if __name__ == "__main__":
    if "--figer" in sys.argv:
        _ecrire_reference()
        print(f"REFERENCE REECRITE : {REFERENCE.name} "
              f"({REFERENCE.stat().st_size / 1024:.0f} ko, "
              f"{len(SCENARIOS)} scenarios, lot de {TAILLE_DU_LOT}). Relire "
              f"le diff avant de committer : il dit ce que le changement a "
              f"deplace.")
    else:
        raise SystemExit(pytest.main([__file__, "-q"]))
