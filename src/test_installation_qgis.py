"""Gestionnaire QgsTask réel et cycle du dialogue, sans pip ni modèle métier."""
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSettings, QTimer
from qgis.PyQt.QtTest import QTest
from qgis.PyQt.QtWidgets import QMainWindow
from calage_apports import installation, plugin


@pytest.fixture(scope="module")
def qgis_app(tmp_path_factory):
    QgsApplication.setPrefixPath("/usr", True)
    app = QgsApplication.instance() or QgsApplication([], True)
    app.initQgis()
    app.setOrganizationName("ISL-UX-tests")
    app.setApplicationName("calage-test")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                      str(tmp_path_factory.mktemp("settings")))
    yield app
    app.processEvents()
    app.exitQgis()


def attendre(app, condition, secondes=5):
    limite = time.monotonic() + secondes
    while not condition() and time.monotonic() < limite:
        app.processEvents()
        QTest.qWait(10)
    assert condition(), "La tâche ou l'interface n'a pas répondu dans le délai."


@pytest.mark.parametrize("issue", ["succes", "echec", "exception"])
def test_gestionnaire_reste_reactif_et_ne_publie_que_le_succes(
        qgis_app, monkeypatch, tmp_path, issue):
    demarre, terminer = threading.Event(), threading.Event()
    python = tmp_path / "python"
    cle = "installation-test/" + issue
    QSettings().setValue(cle, "precedent")
    publications, resultats, battements = [], [], []

    def installer(base, journal, *, cible):
        assert threading.current_thread() is not threading.main_thread()
        assert cible == tmp_path
        journal("pip simulé, tâche QGIS réelle")
        demarre.set()
        if not terminer.wait(8):
            raise TimeoutError("Le test n'a pas libéré la tâche")
        if issue == "exception":
            raise RuntimeError("incident simulé")
        return (python, "vérifié") if issue == "succes" else (None, "pip inaccessible")

    def publier(chemin):
        assert threading.current_thread() is threading.main_thread()
        publications.append(chemin)

    monkeypatch.setattr(installation.noyau, "installer_interpreteur", installer)
    monkeypatch.setattr(installation.noyau, "restaurer_interpreteur", publier)
    tache = installation.TacheInstallation("python_base", tmp_path, cle)
    tache.resultat.connect(lambda *r: resultats.append(r))
    minuteur = QTimer()
    minuteur.timeout.connect(lambda: battements.append(True))
    minuteur.start(10)
    QgsApplication.taskManager().addTask(tache)
    try:
        attendre(qgis_app, lambda: demarre.is_set() and len(battements) >= 3)
        assert installation.installation_en_cours() is tache
        assert QSettings().value(cle) == "precedent"
        assert publications == []
    finally:
        terminer.set()
        attendre(qgis_app, lambda: len(resultats) == 1)
        minuteur.stop()
    assert publications == ([python] if issue == "succes" else [])
    assert QSettings().value(cle) == (str(python) if issue == "succes" else "precedent")
    assert resultats[0][0] == (python if issue == "succes" else None)
    assert "pip simulé" in resultats[0][2]
    attendre(qgis_app, lambda: installation.installation_en_cours() is None)


def test_fermeture_reouverture_et_dechargement_pendant_installation(
        qgis_app, monkeypatch, tmp_path):
    terminer, demarre = threading.Event(), threading.Event()
    appels, resultats = [], []

    def installer(base, journal, *, cible):
        appels.append(cible)
        journal("Attente du téléchargement simulé")
        demarre.set()
        if not terminer.wait(12):
            raise TimeoutError("test interrompu")
        return None, "réseau indisponible"

    monkeypatch.setattr(installation.noyau, "installer_interpreteur", installer)
    principale = QMainWindow()
    iface = SimpleNamespace(mainWindow=lambda: principale)
    premier = plugin.DialogueParametrage(iface)
    premier.show()
    tache = installation.TacheInstallation("python_base", tmp_path, "cycle-test")
    tache.resultat.connect(lambda *r: resultats.append(r))
    premier._suivre_installation(tache)
    QgsApplication.taskManager().addTask(tache)
    second = None
    try:
        attendre(qgis_app, demarre.is_set)
        assert all(not bouton.isEnabled() for bouton in premier._commandes_poste)
        premier.close()
        premier.show()
        premier._reprendre_installation()
        assert premier._tache_installation is tache
        # Un second clic ne demande aucun chemin et ne lance pas de second worker.
        premier._installer_interpreteur()
        assert len(appels) == 1
        greffon = plugin.PluginCalage(iface)
        greffon.fenetre = premier
        greffon.unload()
        assert premier._tache_installation is None
        assert installation.installation_en_cours() is tache
        second = plugin.DialogueParametrage(iface)
        attendre(qgis_app, lambda: second._tache_installation is tache)
        assert all(not bouton.isEnabled() for bouton in second._commandes_poste)
        second.close()  # finir sans réouvrir de boîte modale ou de fenêtre
    finally:
        terminer.set()
        attendre(qgis_app, lambda: len(resultats) == 1)
        if second is not None:
            attendre(qgis_app, lambda: second._tache_installation is None)
            assert all(bouton.isEnabled() for bouton in second._commandes_poste)
            assert not second.isVisible()
            assert not hasattr(second, "_erreur_installation")
            second.deleteLater()
        premier.deleteLater()
        principale.deleteLater()
        qgis_app.processEvents()
