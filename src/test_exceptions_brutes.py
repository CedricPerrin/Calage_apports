"""
Des saisies fautives doivent rendre une ANOMALIE (ou une reponse « ok: false »)
qui dit quoi corriger et ou, jamais une exception Python brute.

    python -m pytest src/test_exceptions_brutes.py -q

Contrairement a test_controle_donnees.py et test_pont_caler.py, qui
enregistrent ce que le code FAIT, ce test dit ce qu'il DOIT faire : un classeur
ou un fichier de parametres mal rempli est lu par un ingenieur hydraulicien,
pas par un developpeur. Les entrees sont fabriquees avec les memes outils que
ces deux filets, dont on reprend les fonctions.
"""
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

import test_controle_donnees as tcd  # noqa: E402
import test_pont_caler as tpc  # noqa: E402


def _anomalies(rendu):
    """Les (niveau, message) d'un rendu de test_controle_donnees, apres avoir
    constate qu'aucune exception n'a ete levee."""
    assert "exception" not in rendu, (
        f"exception brute : {rendu['exception']} : {rendu['message']!r}")
    return [tuple(a) for a in rendu["rendu"]["anomalies"]]


# --- 1. Ordre non numerique ---------------------------------------------------

def test_ordre_non_numerique(tmp_path):
    corr = tcd._avec(tcd.CORR, Ordre=[1, "deux", 3])
    anomalies = _anomalies(tcd._tpl(tmp_path, corr=corr))
    assert anomalies == [(
        tcd.cd.ERREUR,
        "feuille Correspondance, colonne Ordre : valeur non numerique "
        "'deux' (ligne 3) ; la colonne doit etre la suite 1..3 sans trou "
        "ni doublon.")]


# --- 2. JSON de parametres corrompu -------------------------------------------

def test_parametres_json_corrompu(tmp_path):
    anomalies = _anomalies(tcd._tpl(tmp_path, json_brut="{ pas du json"))
    assert len(anomalies) == 1
    niveau, message = anomalies[0]
    assert niveau == tcd.cd.ERREUR
    assert message.startswith("parametres du calage illisibles : ")
    assert "donnees.json" in message          # QUEL fichier corriger
    assert "ligne 1" in message               # OU dans ce fichier
    assert "Expecting" not in message         # pas le jargon de json


# --- 3. colonne Nom_Section absente -------------------------------------------

def test_correspondance_sans_nom_section(tmp_path):
    corr = tcd._avec(tcd.CORR, **{tcd.COL_SECTION: tcd._SUPPRIMER})
    anomalies = _anomalies(tcd._modele(tmp_path, corr=corr))
    assert anomalies == [(
        tcd.cd.ERREUR,
        "feuille Correspondance illisible : colonne 'Nom_Section' absente")]


# --- 4. import de pilote_hecras impossible ------------------------------------

def test_fenetre_sans_pilote(tmp_path):
    # Sans le pilote, la fenetre ne peut pas etre jugee : le controle du
    # classeur reste utilisable (il tourne aussi depuis QGIS), sans anomalie.
    with tcd._bloquer("pilote_hecras"):
        rendu = tcd._tpl(tmp_path, params=tcd._avec(
            tcd.PARAMS, Simulation_debut="13/10/2014 00:00",
            Simulation_fin="x"))
    assert _anomalies(rendu) == []


# --- 5. Sens_axe nul ----------------------------------------------------------

@pytest.mark.parametrize("nul", [None, float("nan")])
def test_sens_axe_nul(tmp_path, nul):
    # NaN passe par json_nan : le JSON ecrit par parametres.ecrire n'en porte pas.
    rendu = tcd._geo(tmp_path, json_nan=nul is not None, Sens_axe=nul)
    anomalies = _anomalies(rendu)
    assert anomalies == [(
        tcd.cd.ERREUR,
        "Sens_axe : valeur manquante ; valeurs admises ['amont_aval', "
        "'aval_amont'].")]


# --- 6. commande_caler : classeur absent, Cibles sans Temps_h ------------------

def _jouer(nom, tmp_path, capsys):
    rendu = tpc.jouer(tpc.CAS[nom], tmp_path, capsys)
    assert rendu["exception"] is None, (
        f"exception brute : {rendu['exception']}")
    assert rendu["code"] == 1
    assert rendu["reponse"]["ok"] is False
    return rendu["reponse"]["erreur"]


def test_caler_classeur_absent(tmp_path, capsys):
    erreur = _jouer("classeur/absent", tmp_path, capsys)
    assert erreur.startswith("classeur de saisie introuvable : ")
    assert "donnees.xlsx" in erreur


def test_caler_cibles_sans_temps_h(tmp_path, capsys):
    erreur = _jouer("classeur/sans_temps_h", tmp_path, capsys)
    assert "Temps_h" in erreur and "feuille Cibles" in erreur
