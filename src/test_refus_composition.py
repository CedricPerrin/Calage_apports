"""
Les refus de la composition, SANS QGIS.

Ils vivaient dans la fenetre (plugin._composer_et_controler_interne), ou seul
le banc sous QGIS pouvait les eprouver. Depuis le 11/11/2026 ils sont dans
noyau.py : la fenetre lit ses widgets, noyau decide, la fenetre affiche.
Premier pas d'une frontiere voulue pour un outil partage et durable — celui
qui modifie la composition doit pouvoir le verifier en une seconde.

LES TEXTES ATTENDUS SONT CEUX QUE LA FENETRE PORTAIT, mot pour mot : ce
deplacement ne change rien de ce que lit l'utilisateur.

    python -m pytest src/test_refus_composition.py -q
"""
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC.parent / "calage_apports"))

import noyau  # noqa: E402

COMPLET = dict(projet_choisi=True, plan_choisi=True,
               prefixe_scenario="Riviere-Q100", couches_chargees=True,
               axe_choisi=True, dossier_sortie="D:/calage/sortie")

PROJET = ("Étape Modèle : choisir d'abord le fichier .prj du projet "
          "HEC-RAS (« Choisir le projet… »).")
PLAN = "Étape Modèle : choisir un plan de référence."
PREFIXE = ("Étape Paramètres : renseigner le préfixe de scénario, cours "
           "d'eau en tête. Il nomme les plans de CE calage — "
           "« Riviere-Q100 » donne « Riviere-Q100-sans », "
           "« Riviere-Q100-A1 » et « Riviere-Q100 » —, il nomme aussi "
           "son Excel — « donnees_calage_Riviere-Q100.xlsx » —, et "
           "c'est lui qui empêche un second scénario d'effacer les "
           "plans du premier.")
COUCHES = ("Étape Modèle : cliquer sur « Charger les couches du modèle » "
           "avant de composer. Si elles avaient été chargées, c'est "
           "qu'elles ont été retirées du projet depuis — les "
           "recharger.")
AXE = "Étape Modèle : choisir la couche de l'axe hydraulique."
DOSSIER = ("Étape Paramètres : choisir le dossier de sortie, juste "
           "au-dessus du préfixe.")


def _refus(**manques):
    return noyau.refus_avant_composition(**dict(COMPLET, **manques))


# --- avant de composer --------------------------------------------------------

def test_une_saisie_complete_n_est_pas_refusee():
    assert _refus() is None


@pytest.mark.parametrize("manque, attendu", [
    (dict(projet_choisi=False), PROJET),
    (dict(plan_choisi=False), PLAN),
    (dict(prefixe_scenario=""), PREFIXE),
    (dict(prefixe_scenario="   "), PREFIXE),
    (dict(prefixe_scenario=None), PREFIXE),
    (dict(couches_chargees=False), COUCHES),
    (dict(axe_choisi=False), AXE),
    (dict(dossier_sortie=""), DOSSIER),
    (dict(dossier_sortie="  "), DOSSIER),
])
def test_chaque_manque_a_sa_phrase(manque, attendu):
    assert _refus(**manque) == attendu


@pytest.mark.parametrize("manques, attendu", [
    (dict(projet_choisi=False, plan_choisi=False, prefixe_scenario="",
          couches_chargees=False, axe_choisi=False, dossier_sortie=""),
     PROJET),
    (dict(plan_choisi=False, prefixe_scenario="", dossier_sortie=""), PLAN),
    (dict(prefixe_scenario="", couches_chargees=False, axe_choisi=False),
     PREFIXE),
    (dict(couches_chargees=False, axe_choisi=False, dossier_sortie=""),
     COUCHES),
    (dict(axe_choisi=False, dossier_sortie=""), AXE),
])
def test_le_premier_manque_est_dit_dans_l_ordre_des_etapes(manques, attendu):
    """Projet, plan, prefixe, couches, axe, dossier : l'ordre de la fenetre."""
    assert _refus(**manques) == attendu


def test_les_arguments_se_donnent_par_leur_nom():
    """Six booleens et textes en file : un appel positionnel se tromperait
    de rang sans que rien ne le dise."""
    with pytest.raises(TypeError):
        noyau.refus_avant_composition(True, True, "P", True, True, "D:/s")


# --- l'appariement ------------------------------------------------------------

def _appariement(sans_apport=(), partagees=None):
    return {"paires": [("A1", "S1")], "sans_apport": list(sans_apport),
            "partagees": partagees or {}}


def test_un_appariement_complet_n_est_pas_refuse():
    assert noyau.refus_appariement(_appariement()) is None


def test_une_section_sans_injection_en_amont_est_nommee():
    refus = noyau.refus_appariement(
        _appariement(sans_apport=[("S_Amont", 120.0), ("S_Église", 80.5)]))

    assert refus == (
        "aucune ligne d'injection en amont de : S_Amont, S_Église. "
        "Une section de contrôle sans apport en amont ne peut pas "
        "être calée. Vérifier le sens de l'axe hydraulique et la "
        "position des objets.")


def test_une_injection_partagee_est_nommee_avec_ses_sections():
    refus = noyau.refus_appariement(
        _appariement(partagees={"A1": ["S1", "S2"], "A3": ["S4", "S5"]}))

    assert refus == (
        "une même injection alimenterait plusieurs sections : "
        "« A1 » pour S1, S2; « A3 » pour S4, S5. La méthode cale un apport "
        "contre UNE cible : ajouter une injection, ou retirer une section.")


def test_la_section_sans_injection_est_dite_avant_l_injection_partagee():
    refus = noyau.refus_appariement(
        _appariement(sans_apport=[("S9", 1.0)], partagees={"A1": ["S1", "S2"]}))

    assert refus.startswith("aucune ligne d'injection en amont de : S9.")


# --- la ligne du compte rendu sur les pentes -----------------------------------

@pytest.mark.parametrize("pentes, nb, motif, attendu", [
    ({}, 3, "", "Pente des apports : 0/3 pré-remplie"),
    ({"A1": 0.01}, 3, "", "Pente des apports : 1/3 pré-remplie"),
    ({"A1": 0.01, "A2": 0.02}, 3, "", "Pente des apports : 2/3 pré-remplies"),
    ({}, 2, "geometrie non pretraitee",
     "Pente des apports : 0/2 pré-remplie — geometrie non pretraitee"),
])
def test_les_pentes_pre_remplies_se_disent_au_singulier_ou_au_pluriel(
        pentes, nb, motif, attendu):
    assert noyau.dire_pentes_pre_remplies(pentes, nb, motif) == attendu
