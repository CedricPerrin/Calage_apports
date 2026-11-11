"""
La fenetre confie ses refus de composition a noyau.py : le fil qui les relie.

src/test_refus_composition.py eprouve les refus SANS QGIS. Ici, sous QGIS, on
verifie le raccord : la fenetre passe a noyau.refus_avant_composition ce que
portent ses widgets, et affiche le motif rendu, tel quel. Sans ce test, un
argument mal branche (le prefixe a la place du dossier) ne se verrait qu'a
l'usage.

    QT_QPA_PLATFORM=offscreen python3 -m pytest src/test_composition_fenetre.py -q
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("qgis.core")

from qgis.core import QgsApplication  # noqa: E402
from qgis.PyQt.QtCore import QSettings  # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow  # noqa: E402

from calage_apports import plugin  # noqa: E402


@pytest.fixture(scope="module")
def qgis_app(tmp_path_factory):
    if os.environ.get("QGIS_PREFIX_PATH"):
        QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication.instance() or QgsApplication([], True)
    app.initQgis()
    app.setOrganizationName("ISL-UX-tests")
    app.setApplicationName("calage-composition")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path_factory.mktemp("settings")))
    yield app
    app.processEvents()
    app.exitQgis()


@pytest.fixture
def fenetre(qgis_app, monkeypatch):
    principale = QMainWindow()
    dialogue = plugin.DialogueParametrage(
        SimpleNamespace(mainWindow=lambda: principale))
    dialogue.critiques = []
    monkeypatch.setattr(
        plugin.QMessageBox, "critical",
        staticmethod(lambda parent, titre, texte, *a, **k:
                     dialogue.critiques.append((titre, texte))))
    monkeypatch.setattr(plugin, "journaliser", lambda *a, **k: None)
    yield dialogue
    dialogue.deleteLater()
    principale.deleteLater()
    qgis_app.processEvents()


def test_une_fenetre_vide_dit_le_premier_manque_de_noyau(fenetre):
    fenetre._composer_et_controler_interne()

    assert len(fenetre.critiques) == 1
    titre, texte = fenetre.critiques[0]
    assert titre.endswith("— échec")
    assert texte == plugin.noyau.refus_avant_composition(
        projet_choisi=False, plan_choisi=False, prefixe_scenario="",
        couches_chargees=False, axe_choisi=False, dossier_sortie="")
    assert "DÉJÀ été réécrite" not in texte, "rien n'a ete ecrit"


def test_la_fenetre_passe_a_noyau_ce_que_portent_ses_widgets(
        fenetre, monkeypatch):
    recu = {}

    def refus(**saisie):
        recu.update(saisie)
        return "refus d'essai"

    monkeypatch.setattr(plugin.noyau, "refus_avant_composition", refus)
    ecrit = []
    monkeypatch.setattr(fenetre, "_ecrire_dans_geometrie",
                        lambda: ecrit.append(True))
    fenetre.edit_prefixe_scenario.setText("  Riviere-Q100 ")
    fenetre.edit_dossier_sortie.setText("  D:/calage/sortie  ")

    fenetre._composer_et_controler_interne()

    assert recu == {"projet_choisi": False, "plan_choisi": False,
                    "prefixe_scenario": "  Riviere-Q100 ",
                    "couches_chargees": False, "axe_choisi": False,
                    "dossier_sortie": "D:/calage/sortie"}
    assert [texte for _, texte in fenetre.critiques] == ["refus d'essai"]
    assert not ecrit, "la geometrie a ete ecrite malgre le refus"


# ---------------------------------------------------------------------------
# FILET DE LA COMPOSITION, AU BORD DE noyau.py. Ecrit le 11/11/2026 sur le
# code INCHANGE, avant que la composition ne passe dans noyau.py (etape B) :
# tout ce que la fenetre demande a noyau.py, dans l'ordre, avec ses
# arguments, et ce qu'elle retient a chaque instant (paquet, appariement,
# classeur) — y compris quand une etape echoue en chemin. La reference
# (reference_composition_fenetre.json) se refige par :
#
#     QT_QPA_PLATFORM=offscreen python3 src/test_composition_fenetre.py --figer
# ---------------------------------------------------------------------------
import json  # noqa: E402

REFERENCE = Path(__file__).with_name("reference_composition_fenetre.json")

APPARIEMENT = {"paires": [("A1", "S1"), ("A2", "S2")], "sans_apport": [],
               "partagees": {}, "sens": "amont_aval", "sens_deduit": None,
               "pk_sections": {"S1": 100.0, "S2": 900.0},
               "pk_apports": {"A1": 50.0, "A2": 500.0}}

CAS_COMPOSITION = {
    "nominal": {},
    "section_sans_apport": {
        "appariement": dict(APPARIEMENT, sans_apport=[("S3", 1500.0)])},
    "injection_partagee": {
        "appariement": dict(APPARIEMENT, partagees={"A1": ["S1", "S2"]})},
    "appariement_en_echec": {"echec": "apparier_paquet"},
    "classeur_en_echec": {"echec": "preparer_classeur"},
    "controle_en_echec": {"echec": "controler_paquet"},
    "ecriture_geometrie_en_echec": {"echec": "_ecrire_dans_geometrie"},
    "sous_dossiers_saisis": {"sous_dossiers": ("res_Q100", "suivi_Q100")},
    "une_pente_et_un_motif": {"pentes": ({"A1": 0.004}, "A2 hors profil")},
}


def _neutre(valeur, tmp):
    """Un objet rendu comparable d'une execution a l'autre."""
    if isinstance(valeur, dict):
        return {str(c): _neutre(v, tmp) for c, v in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [_neutre(v, tmp) for v in valeur]
    if isinstance(valeur, Path):
        valeur = str(valeur)
    if isinstance(valeur, str):
        return valeur.replace(str(tmp), "<TMP>").replace("\\", "/")
    if valeur is None or isinstance(valeur, (bool, int, float)):
        return valeur
    return f"<{getattr(valeur, 'nom', type(valeur).__name__)}>"


def jouer_composition(nom, fenetre, monkeypatch, tmp):
    """Joue la composition d'un cas ; rend la trace de ce qui s'y passe."""
    cas = CAS_COMPOSITION[nom]
    sortie = tmp / "sortie"
    trace = []

    def etat():
        return {"paquet": _neutre(fenetre.paquet, tmp),
                "appariement": (None if fenetre.appariement is None
                                else sorted(fenetre.appariement)),
                "classeur": _neutre(fenetre.classeur, tmp)}

    def doublure(nom_appel, rendu):
        def appel(*arguments, **nommes):
            trace.append({"appel": nom_appel,
                          "arguments": _neutre(arguments, tmp),
                          "nommes": _neutre(nommes, tmp), "avant": etat()})
            if cas.get("echec") == nom_appel:
                raise RuntimeError(f"echec simule de {nom_appel}")
            return rendu(*arguments, **nommes) if callable(rendu) else rendu
        return appel

    def couche(nom_couche):
        return SimpleNamespace(nom=nom_couche, featureCount=lambda: 1)

    noyau = plugin.noyau
    vrais_parametres = noyau.parametres_calage
    paquet = {"sections": str(sortie / "sections.shp"),
              "apports": str(sortie / "apports.shp"),
              "axe": str(sortie / "axe.shp")}
    for cible, nom_appel, rendu in (
            (noyau, "composer_paquet", paquet),
            (noyau, "parametres_calage", vrais_parametres),
            (noyau, "apparier_paquet", cas.get("appariement", APPARIEMENT)),
            (noyau, "pentes_locales_apports",
             cas.get("pentes", ({"A1": 0.004, "A2": 0.002}, ""))),
            (noyau, "preparer_classeur", sortie / "donnees_calage_R-Q100.xlsx"),
            (noyau, "controler_paquet",
             ([("AVERTISSEMENT", "une anomalie")], "tableau des PK", None)),
            (plugin, "couche_vers_gdf",
             lambda c, **k: f"gdf de {c.nom}"),
            (plugin, "etiqueter_pk_sur_carte", None)):
        monkeypatch.setattr(cible, nom_appel, doublure(nom_appel, rendu))
    for methode, rendu in (
            ("_ecrire_dans_geometrie", "compte rendu de l'ecriture"),
            ("_rendre_compte_du_controle", None), ("_maj_resume", None),
            ("_maj_onglet_validation", None), ("_calage_en_cours", None)):
        monkeypatch.setattr(fenetre, methode, doublure(methode, rendu))

    # LES CHAMPS D'ABORD, L'ETAT ENSUITE : saisir un texte reveille des
    # temoins de la fenetre, qui liraient de fausses couches.
    fenetre.edit_projet_hecras.setText(str(tmp / "modele" / "Essai.prj"))
    fenetre.edit_prefixe_scenario.setText(" R-Q100 ")
    fenetre.edit_dossier_sortie.setText(f"  {sortie}  ")
    resultats, suivi = cas.get("sous_dossiers", ("", ""))
    fenetre.edit_sous_dossier_resultats.setText(resultats)
    fenetre.edit_sous_dossier_suivi.setText(suivi)
    fenetre.info_projet = {"nom_projet": "Essai"}
    fenetre.version_hecras = "6.6"
    fenetre.crs_modele = "EPSG:2154"
    fenetre.couche_sections = couche("sections")
    fenetre.couche_injections = couche("injections")
    plan = {"numero": "03", "geometrie": "02", "unsteady": "04", "fenetre": {}}
    fenetre.combo_plan.currentData = lambda *a: plan
    fenetre.combo_axe.currentLayer = lambda: couche("axe")
    fenetre.paquet, fenetre.appariement, fenetre.classeur = None, None, None

    fenetre._composer_et_controler_interne()

    return {"trace": trace, "apres": etat(),
            "boites": _neutre(fenetre.critiques, tmp),
            "dossiers": sorted(p.relative_to(tmp).as_posix()
                               for p in tmp.rglob("*") if p.is_dir())}


@pytest.fixture(scope="module")
def reference():
    assert REFERENCE.is_file(), (
        f"{REFERENCE.name} absent : le figer avec « --figer ».")
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def test_la_reference_couvre_les_cas_et_eux_seuls(reference):
    assert sorted(reference) == sorted(CAS_COMPOSITION)


@pytest.mark.parametrize("nom", sorted(CAS_COMPOSITION))
def test_la_composition_demande_a_noyau_ce_que_la_reference_a_enregistre(
        nom, fenetre, monkeypatch, tmp_path, reference):
    obtenu = jouer_composition(nom, fenetre, monkeypatch, tmp_path)

    assert json.loads(json.dumps(obtenu)) == reference[nom]


if __name__ == "__main__" and "--figer" in sys.argv:
    import tempfile

    _app = QgsApplication([], True)
    _app.initQgis()
    _rendus = {}
    for _nom in sorted(CAS_COMPOSITION):
        _principale = QMainWindow()
        _fenetre = plugin.DialogueParametrage(
            SimpleNamespace(mainWindow=lambda: _principale))
        _fenetre.critiques = []
        _pose = pytest.MonkeyPatch()
        _pose.setattr(plugin.QMessageBox, "critical", staticmethod(
            lambda parent, titre, texte, *a, **k:
            _fenetre.critiques.append((titre, texte))))
        _pose.setattr(plugin, "journaliser", lambda *a, **k: None)
        with tempfile.TemporaryDirectory() as _tmp:
            _rendus[_nom] = jouer_composition(_nom, _fenetre, _pose, Path(_tmp))
        _pose.undo()
    REFERENCE.write_text(json.dumps(_rendus, ensure_ascii=False, indent=1,
                                    sort_keys=True) + "\n", encoding="utf-8")
    print(f"REFERENCE REECRITE : {REFERENCE.name} ({len(_rendus)} cas). "
          f"Relire le diff avant de committer.")
