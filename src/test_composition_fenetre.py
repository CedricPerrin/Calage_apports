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
