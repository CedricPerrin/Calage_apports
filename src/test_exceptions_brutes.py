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
import types
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

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



def test_correspondance_sans_nom_apport(tmp_path):
    # Le jumeau du precedent, une ligne plus haut dans _correspondance
    # (retouche de l'arbitre, 11/11/2026).
    corr = tcd._avec(tcd.CORR, **{tcd.COL_APPORT: tcd._SUPPRIMER})
    anomalies = _anomalies(tcd._modele(tmp_path, corr=corr))
    assert anomalies == [(
        tcd.cd.ERREUR,
        "feuille Correspondance illisible : colonne 'Nom_Apport' absente")]

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


# ===========================================================================
# Second lot : les defauts restes ouverts apres le premier
# ===========================================================================

# --- 1. _correspondance : Ordre non numerique, hors controler_template ---------

MSG_ORDRE_ILLISIBLE = ("feuille Correspondance illisible : colonne Ordre : "
                       "valeur non numerique 'deux' (ligne 3)")


def test_ordre_non_numerique_contre_modele(tmp_path):
    corr = tcd._avec(tcd.CORR, Ordre=[1, "deux", 3])
    anomalies = _anomalies(tcd._modele(tmp_path, corr=corr))
    assert anomalies == [(tcd.cd.ERREUR, MSG_ORDRE_ILLISIBLE)]


def test_ordre_non_numerique_geometrie(tmp_path):
    corr = tcd._avec(tcd.CORR, Ordre=[1, "deux", 3])
    anomalies = _anomalies(tcd._geo(tmp_path, corr=corr))
    assert anomalies == [(tcd.cd.ERREUR, MSG_ORDRE_ILLISIBLE)]


# --- 2. _cibles_depuis_classeur : colonnes et feuilles absentes ----------------

def _classeur_pour_caler(dossier, corr, cibles):
    """Ecrit donnees.xlsx ; une feuille None n'est pas ecrite du tout."""
    import pandas as pd

    with pd.ExcelWriter(dossier / "donnees.xlsx", engine="openpyxl") as w:
        for nom, contenu in (("Correspondance", corr), ("Cibles", cibles)):
            if contenu is not None:
                pd.DataFrame(contenu).to_excel(w, sheet_name=nom, index=False)
    # ni classeur ni feuille Parametres a ecrire : jouer() ne fabrique que le
    # JSON des parametres et le projet.
    sc = dict(tpc.BASE, classeur=False)
    return sc


def _entetes(contenu):
    return str(list(contenu))


@pytest.mark.parametrize("colonne", [tpc.COL_APPORT, tpc.COL_SECTION,
                                     tpc.COL_CIBLE])
def test_caler_correspondance_sans_colonne(tmp_path, capsys, colonne):
    corr = tpc._avec(tpc.CORR, **{colonne: tpc._SUPPRIMER})
    sc = _classeur_pour_caler(tmp_path, corr, tpc.CIBLES)
    erreur = _reponse_refusee(sc, tmp_path, capsys)
    nom = colonne.split(" ")[0]
    assert erreur == (
        f"classeur de saisie inexploitable : la feuille Correspondance n'a "
        f"pas de colonne « {nom} » (en-tete de la ligne 1). En-tetes "
        f"trouves : "
        f"{_entetes(corr)}")


@pytest.mark.parametrize("absente", ["Correspondance", "Cibles"])
def test_caler_feuille_absente(tmp_path, capsys, absente):
    corr = None if absente == "Correspondance" else tpc.CORR
    cibles = None if absente == "Cibles" else tpc.CIBLES
    sc = _classeur_pour_caler(tmp_path, corr, cibles)
    erreur = _reponse_refusee(sc, tmp_path, capsys)
    autre = "Cibles" if absente == "Correspondance" else "Correspondance"
    assert erreur == (
        f"classeur de saisie inexploitable : le classeur n'a pas de feuille "
        f"« {absente} » (feuilles trouvees : ['{autre}'])")


def _reponse_refusee(sc, tmp_path, capsys):
    rendu = tpc.jouer(sc, tmp_path, capsys)
    assert rendu["exception"] is None, (
        f"exception brute : {rendu['exception']}")
    assert rendu["code"] == 1 and rendu["reponse"]["ok"] is False
    return rendu["reponse"]["erreur"]


# --- 3. parametres.lire : JSON corrompu, pas un objet, pas en UTF-8 ------------

def _json_en_defaut(dossier, octets):
    """Classeur sain + JSON voisin aux octets donnes."""
    chemin = tcd.classeur(dossier, params=None)
    tcd.parametres.chemin(chemin).write_bytes(octets)
    return chemin


_JSON_FAUTIFS = {
    "invalide": (b"{ pas du json",
                 "n'est pas un JSON valide (ligne 1, colonne 3). Le "
                 "corriger avant de relancer."),
    "liste": (b"[1, 2]",
              "n'est pas un objet JSON { \"Parametre\": valeur, ... }. Le "
              "corriger avant de relancer."),
    "latin1": ("{\"Nom_projet\": \"Gu\u00e9\"}".encode("latin-1"),
               "n'est pas enregistre en UTF-8. Le re-enregistrer en UTF-8 "
               "avant de relancer."),
}


def _message_json(defaut):
    return (f"parametres du calage illisibles : « donnees.json » "
            f"{_JSON_FAUTIFS[defaut][1]}")


def _sans_ras_commander():
    faux = types.ModuleType("ras_commander")
    faux.HdfBndry = faux.HdfMesh = None
    return mock.patch.dict(sys.modules, {"ras_commander": faux})


@pytest.mark.parametrize("defaut", sorted(_JSON_FAUTIFS))
@pytest.mark.parametrize("controle", ["template", "geometrie", "modele"])
def test_json_illisible_meme_message_partout(tmp_path, defaut, controle):
    chemin = _json_en_defaut(tmp_path, _JSON_FAUTIFS[defaut][0])
    try:
        with _sans_ras_commander():
            if controle == "template":
                anomalies = tcd.cd.controler_template(chemin)
            elif controle == "geometrie":
                anomalies = tcd.cd.controler_geometrie(chemin)[0]
            else:
                anomalies = tcd.cd.controler_contre_modele(chemin)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"exception brute : {type(e).__name__} : {e}")
    assert anomalies == [(tcd.cd.ERREUR, _message_json(defaut))]


@pytest.mark.parametrize("defaut", sorted(_JSON_FAUTIFS))
def test_caler_json_illisible(tmp_path, capsys, defaut):
    _json_en_defaut(tmp_path, _JSON_FAUTIFS[defaut][0])
    sc = dict(tpc.BASE, params=None)
    # Le classeur du scenario est ecrit par jouer() ; le JSON, deja la, reste.
    assert _reponse_refusee(sc, tmp_path, capsys) == _message_json(defaut)


# --- 4. cibles : valeurs manquantes, au milieu ou en fin de colonne ------------

def _avertissements(rendu):
    return [m for n, m in _anomalies(rendu) if n == tcd.cd.AVERTISSEMENT]


def test_cible_trou_au_milieu(tmp_path):
    # Index 3 de la colonne = ligne 5 de la feuille (l'en-tete est la ligne 1).
    cibles = tcd._avec(tcd.CIBLES, C2=tcd._HYDRO[:3] + [None] + tcd._HYDRO[4:])
    assert _avertissements(tcd._tpl(tmp_path, cibles=cibles)) == [
        "cible 'C2' : valeurs manquantes intercalees (ligne 5 de la feuille "
        "Cibles)"]


def test_cible_trous_au_milieu_cites_par_cinq(tmp_path):
    haut = tcd._HYDRO[:2] + [None] * 7 + tcd._HYDRO[9:]
    cibles = tcd._avec(tcd.CIBLES, C2=haut)
    assert _avertissements(tcd._tpl(tmp_path, cibles=cibles)) == [
        "cible 'C2' : valeurs manquantes intercalees (lignes 4, 5, 6, 7, 8 "
        "... de la feuille Cibles, 7 au total)"]


def test_cible_trous_en_fin(tmp_path):
    cibles = tcd._avec(tcd.CIBLES, C2=tcd._HYDRO[:9] + [None] * 3)
    assert _avertissements(tcd._tpl(tmp_path, cibles=cibles)) == [
        "cible 'C2' : 3 valeur(s) manquante(s) en fin de colonne"]


def test_cible_trou_au_milieu_et_en_fin(tmp_path):
    cibles = tcd._avec(tcd.CIBLES, C2=tcd._HYDRO[:3] + [None]
                       + tcd._HYDRO[4:10] + [None] * 2)
    assert _avertissements(tcd._tpl(tmp_path, cibles=cibles)) == [
        "cible 'C2' : valeurs manquantes intercalees (ligne 5 de la feuille "
        "Cibles)",
        "cible 'C2' : 2 valeur(s) manquante(s) en fin de colonne"]


# --- 5. objets_retires -----------------------------------------------------------

def test_caler_objets_retires(tmp_path, capsys):
    rendu = tpc.jouer(tpc.CAS["nominal"], tmp_path, capsys)
    assert rendu["reponse"]["objets_retires"] == tpc.MENAGE["reliquats"]


# --- 6. commande_modele : colonne de nom absente -----------------------------------

def test_modele_sans_colonne_nom_ne_double_rien(tmp_path, capsys):
    # test_pont_lecture fabrique ses .hdf avec h5py, absent du job « noyau » :
    # ce test-ci se joue dans le job « chaine-hdf ».
    pytest.importorskip("h5py")
    import test_pont_lecture as tpl

    reponse = tpl.jouer_modele("sans_colonne_nom", tmp_path, capsys)["reponse"]
    assert [o["nom"] for o in reponse["sections"]] == ["S1", "S_\u00c9glise"]
    assert [o["nom"] for o in reponse["injections"]] == ["A1", "A2"]
    assert reponse["en_attente_pretraitement"] == []


# --- 8. Nom_zone_2D vide, plusieurs zones 2D : une erreur ----------------------
# Decision de Cedric du 11/11/2026. C'etait un avertissement, qui promettait
# « la premiere est retenue par defaut ».

def _controle_zone(tmp_path, nom_zone, zones):
    params = tcd._avec(tcd.PARAMS, Dossier_projet_HECRAS=str(tmp_path),
                       Geometrie_reference="g01", Nom_zone_2D=nom_zone)
    return _anomalies(tcd._modele(tmp_path, params=params,
                                  zones_presentes=zones,
                                  mesh=tcd._zones(zones)))


@pytest.mark.parametrize("nom_zone", ["", "  ", None, float("nan")])
def test_zone_non_nommee_et_plusieurs_zones_est_une_erreur(tmp_path, nom_zone):
    anomalies = _controle_zone(tmp_path, nom_zone, ("Z1", "Z2"))

    sur_la_zone = [(n, m) for n, m in anomalies if "Nom_zone_2D" in m]
    assert [n for n, _ in sur_la_zone] == [tcd.cd.ERREUR]
    message = sur_la_zone[0][1]
    assert "Z1" in message and "Z2" in message
    assert "retenue par defaut" not in message


def test_zone_non_nommee_et_une_seule_zone_passe(tmp_path):
    anomalies = _controle_zone(tmp_path, "", ("Zone2D",))

    assert not [m for _, m in anomalies if "Nom_zone_2D" in m]


def test_zone_nommee_parmi_plusieurs_passe(tmp_path):
    anomalies = _controle_zone(tmp_path, "Z2", ("Z1", "Z2"))

    assert not [m for _, m in anomalies if "Nom_zone_2D" in m]


# --- 9. Un trou EN TETE d'une colonne cible ------------------------------------

def test_cible_trous_en_tete(tmp_path):
    cibles = tcd._avec(tcd.CIBLES, C2=[None] * 3 + tcd._HYDRO[3:])
    assert _avertissements(tcd._tpl(tmp_path, cibles=cibles)) == [
        "cible 'C2' : 3 valeur(s) manquante(s) en debut de colonne : la "
        "cible ne commence qu'a la ligne 5 de la feuille Cibles"]


# --- 10. Un classeur qui n'est pas un .xlsx lisible, au lancement du calage -----

@pytest.mark.parametrize("contenu", [b"ceci n'est pas un classeur",
                                     b"PK\x03\x04tronque"])
def test_caler_classeur_corrompu(tmp_path, capsys, contenu):
    (tmp_path / "donnees.xlsx").write_bytes(contenu)
    erreur = _reponse_refusee(dict(tpc.BASE, classeur=False), tmp_path, capsys)

    assert erreur.startswith(
        "classeur de saisie inexploitable : « donnees.xlsx » n'est pas un "
        "classeur Excel (.xlsx) lisible")
