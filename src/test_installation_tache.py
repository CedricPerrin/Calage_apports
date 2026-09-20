"""Contrat du worker avec Qt réel ; pas une recette du gestionnaire QGIS.

À lancer dans Python QGIS : python -m pytest src/test_installation_tache.py.
Aucun téléchargement : l'installeur et les réglages du poste sont isolés.
"""
import threading

import pytest

pytest.importorskip("qgis.core")
from qgis.PyQt.QtCore import QObject, pyqtSlot
from qgis.PyQt.QtWidgets import QApplication
from calage_apports import installation


@pytest.mark.parametrize("issue", ["succes", "echec", "exception"])
def test_le_worker_ne_publie_que_les_resultats_verifies(monkeypatch, tmp_path, issue):
    app = QApplication.instance() or QApplication([])
    reglages = {"interpreteur": "precedent"}
    class Reglages:
        def setValue(self, cle, valeur):
            assert threading.current_thread() is threading.main_thread()
            reglages[cle] = valeur
    monkeypatch.setattr(installation, "QSettings", Reglages)
    monkeypatch.setattr(installation.noyau, "restaurer_interpreteur", lambda chemin: True)
    cible = tmp_path / "cible_confirmee"
    python = cible / "python"
    observe = []
    def installer(base, journal, *, cible):
        assert threading.current_thread() is not threading.main_thread()
        observe.append((base, cible))
        journal("Installation des paquets")
        if issue == "exception":
            raise RuntimeError("incident simulé")
        return (python, "vérifié") if issue == "succes" else (None, "pip a échoué")
    monkeypatch.setattr(installation.noyau, "installer_interpreteur", installer)
    tache = installation.TacheInstallation("python_base", cible, "interpreteur")
    class Recepteur(QObject):
        def __init__(self):
            super().__init__()
            self.phases = []
        @pyqtSlot(str)
        def recevoir(self, texte):
            assert threading.current_thread() is threading.main_thread()
            self.phases.append(texte)
    recepteur = Recepteur()
    tache.phase.connect(recepteur.recevoir)
    resultats = []
    tache.resultat.connect(lambda *resultat: resultats.append(resultat))
    verdict = []
    thread = threading.Thread(target=lambda: verdict.append(tache.run()))
    thread.start()
    thread.join(timeout=3)
    assert not thread.is_alive()
    app.processEvents()
    assert recepteur.phases == ["Installation des paquets"]
    assert observe == [("python_base", cible)]
    assert reglages["interpreteur"] == "precedent"
    tache.finished(verdict[0])
    assert len(resultats) == 1
    assert verdict == [issue == "succes"]
    assert reglages["interpreteur"] == (str(python) if issue == "succes" else "precedent")
    assert resultats[0][0] == (python if issue == "succes" else None)
    assert "Installation des paquets" in resultats[0][2]
