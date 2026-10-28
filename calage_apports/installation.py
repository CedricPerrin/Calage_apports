"""Installation hors du fil graphique, détenue par le gestionnaire de QGIS."""

from pathlib import Path

from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsTask
from qgis.PyQt.QtCore import QSettings, pyqtSignal

from . import noyau


def installation_en_cours():
    """Retrouve aussi une installation après fermeture/réouverture du dialogue."""
    for tache in QgsApplication.taskManager().tasks():
        if tache.property("calageInstallation") and tache.isActive():
            return tache
    return None


class TacheInstallation(QgsTask):
    phase = pyqtSignal(str)
    resultat = pyqtSignal(object, str, str)

    def __init__(self, base, cible, cle_reglage):
        # pip ne fournit pas ici d'arrêt transactionnel : pas de faux bouton Annuler.
        super().__init__("Installation Python HEC-RAS", QgsTask.Flags(0))
        self.setProperty("calageInstallation", True)
        self.base = str(base)
        self.cible = Path(cible)
        self.cle_reglage = cle_reglage
        self.lignes = []
        self.chemin = None
        self.message = "Installation non exécutée."

    def _journal(self, ligne):
        self.lignes.append(ligne)
        self.phase.emit(ligne)

    def run(self):
        try:
            self.chemin, self.message = noyau.installer_interpreteur(
                self.base, self._journal, cible=self.cible)
        except Exception as erreur:  # noqa: BLE001 — aucune exception ne traverse le worker QGIS
            self.message = f"Installation interrompue : {erreur}"
            return False
        return self.chemin is not None

    def finished(self, succes):
        # QGIS appelle finished sur le fil graphique. Aucun widget n'est détenu
        # par cette tâche : fermer ou décharger le dialogue ne détruit pas pip.
        chemin = self.chemin if succes else None
        if chemin is not None:
            noyau.restaurer_interpreteur(chemin)
            QSettings().setValue(self.cle_reglage, str(chemin))
        journal = "\n".join(self.lignes)
        QgsMessageLog.logMessage(
            f"{journal}\n{self.message}", "Calage des apports",
            Qgis.MessageLevel.Success if chemin else Qgis.MessageLevel.Critical)
        self.resultat.emit(chemin, self.message, journal)


class TacheRecherchePython(QgsTask):
    """Recherche seule : aucune installation ni publication de réglage."""
    phase = pyqtSignal(str)
    resultat = pyqtSignal(object, str, str)

    def __init__(self, cible):
        super().__init__("Recherche des interpréteurs Python", QgsTask.Flag.CanCancel)
        self.setProperty("calageInstallation", True)
        self.cible = Path(cible)
        self.lignes = []
        self.candidats = None
        self.message = "Recherche non exécutée."

    def _journal(self, ligne):
        self.lignes.append(ligne)
        self.phase.emit(ligne)

    def run(self):
        try:
            self._journal("Recherche des interpréteurs Python…")
            self.candidats = noyau.pythons_candidats(self._journal, self.isCanceled)
            self.message = ("Recherche annulée." if self.isCanceled() else
                            f"{len(self.candidats)} interpréteur(s) utilisable(s).")
            return not self.isCanceled()
        except Exception as erreur:  # noqa: BLE001 — frontière du worker QGIS
            self.message = f"Recherche interrompue : {erreur}"
            return False

    def finished(self, succes):
        candidats = self.candidats if succes and not self.isCanceled() else None
        journal = "\n".join(self.lignes)
        QgsMessageLog.logMessage(
            f"{journal}\n{self.message}", "Calage des apports",
            Qgis.MessageLevel.Info if candidats is not None else Qgis.MessageLevel.Warning)
        self.resultat.emit(candidats, self.message, journal)
