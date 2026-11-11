"""
Les refus de la composition, et la composition elle-meme, SANS QGIS.

Ils vivaient dans la fenetre (plugin._composer_et_controler_interne), ou seul
le banc sous QGIS pouvait les eprouver. Depuis le 11/11/2026 ils sont dans
noyau.py : la fenetre lit ses widgets, noyau decide, la fenetre affiche.
Premier pas d'une frontiere voulue pour un outil partage et durable — celui
qui modifie la composition doit pouvoir le verifier en une seconde.

LES TEXTES ATTENDUS SONT CEUX QUE LA FENETRE PORTAIT, mot pour mot : ce
deplacement ne change rien de ce que lit l'utilisateur.

ETAPE B (meme jour) : noyau.composer_classeur enchaine parametres,
appariement, pentes, Excel des objectifs, sous-dossiers et controle. Il est
eprouve ici de deux facons : avec des doublures (l'ordre, ce que « suivre »
recoit et quand, les valeurs par defaut, ce qui survit a un echec), puis POUR
DE VRAI, sur un paquet compose depuis des couches fabriquees.

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


# --- noyau.composer_classeur, avec des doublures --------------------------------

SAISIE = dict(
    dossier_projet="D:/modele", nom_projet="Essai", version_hecras="6.6",
    nom_zone_2d="", numero_plan="03", numero_geometrie="02",
    numero_unsteady="04", mode_selection="plan",
    nom_clone_geometrie="Geometrie_calage", premier_apport="",
    prefixe_scenario="R-Q100", elaguer_etapes=False, sens_axe="amont_aval",
    pk_origine_m=0.0, nb_max_iterations=6, tolerance_volume_pct=5.0,
    tolerance_pic_pct=2.0, bilan_masse_max_pct=5.0,
    sous_dossier_resultats="", sous_dossier_suivi="", fenetre={})

PAQUET = {"sections": "s.shp", "apports": "a.shp", "axe": "axe.shp"}
BON = {"paires": [("A1", "S1")], "sans_apport": [], "partagees": {},
       "pk_apports": {"A1": 50.0}}


class _Journal(list):
    """Les etapes jouees, dans l'ordre ; « recus » : leurs arguments."""

    def __init__(self):
        super().__init__()
        self.recus = {}


def _doubler(monkeypatch, tmp_path, appariement=BON, echec=None):
    """Remplace les etapes de noyau par des temoins ; rend leur journal."""
    journal = _Journal()

    def temoin(nom, rendu):
        def appel(*arguments, **nommes):
            journal.append(nom)
            journal.recus[nom] = (arguments, nommes)
            if echec == nom:
                raise RuntimeError(f"echec de {nom}")
            return rendu
        return appel

    for nom, rendu in (
            ("apparier_paquet", appariement),
            ("pentes_locales_apports", ({"A1": 0.004}, "motif")),
            ("preparer_classeur", tmp_path / "sortie" / "donnees.xlsx"),
            ("controler_paquet", (["anomalie"], "tableau", None))):
        monkeypatch.setattr(noyau, nom, temoin(nom, rendu))
    return journal


def _composer(tmp_path, suivre=None, **saisie):
    saisie = dict(SAISIE, dossier_sortie=str(tmp_path / "sortie"), **saisie)
    return noyau.composer_classeur(saisie, PAQUET, suivre=suivre)


def test_la_composition_enchaine_les_etapes_et_rend_tout(
        monkeypatch, tmp_path):
    journal = _doubler(monkeypatch, tmp_path)

    c = _composer(tmp_path)

    assert journal == ["apparier_paquet", "pentes_locales_apports",
                       "preparer_classeur", "controler_paquet"]
    assert c.appariement is BON and c.pentes == {"A1": 0.004}
    assert c.motif_pentes == "motif"
    assert c.classeur == str(tmp_path / "sortie" / "donnees.xlsx")
    assert isinstance(c.classeur, str), "Qt refuse un Path"
    assert (c.anomalies, c.tableau, c.prolongation) == (
        ["anomalie"], "tableau", None)
    assert c.parametres["Plan_reference"] == "p03"
    # CE QUE CHAQUE ETAPE RECOIT : le paquet, le sens et l'origine des PK ;
    # pour les pentes, la geometrie du plan, l'axe et les PK des apports.
    sortie = str(tmp_path / "sortie")
    assert journal.recus["apparier_paquet"] == (
        (PAQUET,), {"sens": "amont_aval", "pk_origine": 0.0})
    assert journal.recus["pentes_locales_apports"] == (
        ("D:/modele", "Essai", "g02", "axe.shp", "", {"A1": 50.0}), {})
    assert journal.recus["preparer_classeur"] == (
        (sortie, [("A1", "S1")], PAQUET),
        {"parametres": c.parametres, "pentes": {"A1": 0.004}})
    assert journal.recus["controler_paquet"] == ((c.classeur,), {})


def test_un_sous_dossier_vide_prend_son_nom_par_defaut(monkeypatch, tmp_path):
    _doubler(monkeypatch, tmp_path)

    c = _composer(tmp_path)

    assert c.parametres["Sous_dossier_resultats"] == "resultats_finaux"
    assert c.parametres["Sous_dossier_suivi"] == "suivi"
    assert (tmp_path / "sortie" / "resultats_finaux").is_dir()
    assert (tmp_path / "sortie" / "suivi").is_dir()


def test_un_sous_dossier_saisi_est_respecte(monkeypatch, tmp_path):
    _doubler(monkeypatch, tmp_path)

    c = _composer(tmp_path, sous_dossier_resultats="res_Q100",
                  sous_dossier_suivi="suivi_Q100")

    assert c.parametres["Sous_dossier_resultats"] == "res_Q100"
    assert (tmp_path / "sortie" / "res_Q100").is_dir()
    assert (tmp_path / "sortie" / "suivi_Q100").is_dir()
    assert not (tmp_path / "sortie" / "resultats_finaux").exists()


def test_suivre_recoit_l_appariement_puis_le_classeur_des_qu_ils_existent(
        monkeypatch, tmp_path):
    journal = _doubler(monkeypatch, tmp_path)
    recus = []

    _composer(tmp_path, suivre=lambda nom, valeur: recus.append(
        (nom, list(journal))))

    assert recus == [
        ("appariement", ["apparier_paquet"]),
        ("classeur", ["apparier_paquet", "pentes_locales_apports",
                      "preparer_classeur"])]


def test_un_appariement_refuse_est_rendu_avant_le_refus(monkeypatch, tmp_path):
    refuse = dict(BON, sans_apport=[("S9", 1.0)])
    journal = _doubler(monkeypatch, tmp_path, appariement=refuse)
    recus = {}

    with pytest.raises(ValueError) as erreur:
        _composer(tmp_path, suivre=recus.__setitem__)

    assert str(erreur.value) == noyau.refus_appariement(refuse)
    assert recus == {"appariement": refuse}
    assert journal == ["apparier_paquet"], "rien n'est ecrit apres un refus"
    assert not (tmp_path / "sortie").exists()


def test_un_classeur_ecrit_est_rendu_meme_si_son_controle_leve(
        monkeypatch, tmp_path):
    _doubler(monkeypatch, tmp_path, echec="controler_paquet")
    recus = {}

    with pytest.raises(RuntimeError):
        _composer(tmp_path, suivre=recus.__setitem__)

    assert recus["classeur"] == str(tmp_path / "sortie" / "donnees.xlsx")


def test_la_saisie_de_l_appelant_n_est_pas_modifiee(monkeypatch, tmp_path):
    _doubler(monkeypatch, tmp_path)
    saisie = dict(SAISIE, dossier_sortie=str(tmp_path / "sortie"))
    avant = dict(saisie)

    noyau.composer_classeur(saisie, PAQUET)

    assert saisie == avant


# --- noyau.composer_classeur, pour de vrai --------------------------------------

def test_la_composition_reelle_rend_un_classeur_et_ses_controles(tmp_path):
    """Des couches fabriquees, aucun modele HEC-RAS : le paquet est compose,
    apparie, le classeur ecrit et controle — sans QGIS, en une seconde."""
    np = pytest.importorskip("numpy")
    gpd = pytest.importorskip("geopandas")
    pytest.importorskip("openpyxl")
    from shapely.geometry import LineString

    xs = np.linspace(0, 8000, 60)

    def transversale(x, demi=400.0):
        y = 300 * np.sin(x / 1400)
        return LineString([(500000 + x, 6200000 + y - demi),
                           (500000 + x, 6200000 + y + demi)])

    def couche(noms, abscisses, demi):
        return gpd.GeoDataFrame(
            {"nom": noms}, crs="EPSG:2154",
            geometry=[transversale(x, demi) for x in abscisses])

    axe = gpd.GeoDataFrame(
        {"nom": ["Axe"]}, crs="EPSG:2154",
        geometry=[LineString(zip(500000 + xs,
                                 6200000 + 300 * np.sin(xs / 1400)))])
    sortie = tmp_path / "sortie"
    paquet = noyau.composer_paquet(
        sortie, couche(["S1", "S2"], (900, 5100), 400.0),
        couche(["A1", "A2"], (200, 4300), 250.0), axe)
    suivis = {}

    c = noyau.composer_classeur(
        dict(SAISIE, dossier_projet=str(tmp_path / "modele"),
             dossier_sortie=str(sortie)),
        paquet, suivre=suivis.__setitem__)

    assert c.appariement["paires"] == [("A1", "S1"), ("A2", "S2")]
    assert Path(c.classeur).is_file() and Path(c.classeur).suffix == ".xlsx"
    assert suivis == {"appariement": c.appariement, "classeur": c.classeur}
    assert (sortie / "resultats_finaux").is_dir() and (sortie / "suivi").is_dir()
    # Aucun modele HEC-RAS ici : la pente n'est pas calculable, ET C'EST DIT.
    assert c.pentes == {} and c.motif_pentes
    # Le controle a tourne : les cibles ne sont pas encore saisies.
    assert c.anomalies, "un classeur sans cible doit avoir des anomalies"
