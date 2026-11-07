"""Bouton « Retour », commun aux extensions QGIS de la maison.

Demande de l'ingénieur du 07/11/2026 : « Pour tous les plugins, rajoute une petite
icône qui permet de faire un retour ». Chaque retour devient un fichier Markdown du
dossier commun ``DOSSIER``.

Chaque extension en garde une **copie identique** (``<paquet>/retour.py``), comme
``cpn.py`` : changer l'une, c'est changer toutes (``D:\\1-Dev\\CLAUDE.md``,
« Coordination entre plugins »). L'origine est celle de Rhoé, testée par
``tests/gui/test_retour.py``. L'extension se reconnaît par le paquet de ce module ;
son nom et sa version viennent de son ``metadata.txt``. Une fenêtre pose le bouton
par ``retour.bouton(parent)``.

Un retour ne se perd pas : si le partage ne répond pas, il est gardé dans le profil
QGIS, et le message dit où. Aucune touche n'envoie : Entrée passe à la ligne, seul
le bouton « Envoyer » écrit. Toutes les lignes tiennent en 88 caractères : la copie
passe ainsi le formateur de chaque dépôt (88, 96 ou 100 caractères).
"""

from __future__ import annotations

import datetime as dt
import getpass
import platform
import re
from pathlib import Path
from typing import Any

from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

#: Dossier commun des retours, choisi par l'ingénieur le 07/11/2026. Un chemin UNC,
#: jamais une lettre de lecteur : elle diffère d'un poste à l'autre.
DOSSIER = Path(r"\\sudouest\repisl\ISL-SO\13-PIO\3 - Outils\Retour")
#: Icône du thème de QGIS : une bulle de dialogue, qui suit le thème clair ou sombre.
ICONE = "/mMessageLog.svg"
#: Paquet de l'extension qui porte cette copie : ``rhoe``, ``hyetos``…
EXTENSION = __name__.rpartition(".")[0] or __name__


def nom_fichier(moment: dt.datetime, extension: str, auteur: str) -> str:
    """``2026-11-07_211530_rhoe_dupont.md`` : trié par date, lisible sans l'ouvrir."""
    propre = re.sub(r"[^\w.-]+", "_", auteur).strip("_") or "inconnu"
    return f"{moment:%Y-%m-%d_%H%M%S}_{extension}_{propre}.md"


def texte(commentaire: str, entete: dict[str, str], titre: str) -> str:
    """Le contenu du fichier : un titre, le contexte en liste, puis le commentaire."""
    lignes = [f"# Retour sur {titre}", ""]
    lignes += [f"- {cle} : {valeur}" for cle, valeur in entete.items()]
    lignes += ["", "## Commentaire", "", commentaire.strip(), ""]
    return "\n".join(lignes)


def ecrire(dossiers: list[Path], nom: str, contenu: str) -> Path:
    """Écrit ``contenu`` sous ``nom`` dans le premier dossier qui l'accepte.

    Rien n'est écrasé : un nom déjà pris reçoit un suffixe ``_2``, ``_3``… Un dossier
    injoignable, sans droit d'écriture ou impossible à créer passe la main au
    suivant. Lève la dernière ``OSError`` si aucun dossier n'accepte.
    """
    erreur: OSError | None = None
    base = Path(nom)
    for dossier in dossiers:
        try:
            dossier.mkdir(parents=True, exist_ok=True)
            rang = 1
            while True:
                suffixe = "" if rang == 1 else f"_{rang}"
                chemin = dossier / f"{base.stem}{suffixe}{base.suffix}"
                try:
                    with chemin.open("x", encoding="utf-8", newline="\n") as fichier:
                        fichier.write(contenu)
                    return chemin
                except FileExistsError:
                    rang += 1
        except OSError as exc:
            erreur = exc
    raise erreur or OSError("aucun dossier de retour")


def _meta(cle: str) -> str:
    from qgis.utils import pluginMetadata

    valeur = pluginMetadata(EXTENSION, cle)
    return "" if valeur in ("", "__error__") else str(valeur)


def _titre() -> str:
    return f"{_meta('name') or EXTENSION} {_meta('version')}".strip()


def _contexte(moment: dt.datetime) -> tuple[dict[str, str], list[Path]]:
    from qgis.core import Qgis, QgsApplication

    systeme = f"{platform.system()} {platform.release()} ({platform.version()})"
    entete = {
        "Date": f"{moment:%Y-%m-%d %H:%M:%S}",
        "Auteur": getpass.getuser(),
        "Poste": platform.node(),
        "Extension": f"{_titre()} ({EXTENSION})",
        "QGIS": Qgis.version(),
        "Système": systeme,
    }
    local = Path(QgsApplication.qgisSettingsDirPath()) / "retours"
    return entete, [DOSSIER, local]


class _Dialogue(QDialog):
    """Un champ et « Envoyer ». Non modal : la carte reste utilisable."""

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)
        self._titre = _titre()
        self.setObjectName(f"{EXTENSION}_retour")
        self.setWindowTitle(f"Retour sur {self._titre}")
        self.setModal(False)
        etiquette = QLabel("Remarque, idée ou défaut constaté :")
        self._champ = QPlainTextEdit()
        self._champ.setAccessibleName("Votre retour")
        self._champ.setTabChangesFocus(True)
        etiquette.setBuddy(self._champ)
        note = QLabel(
            "Enregistré dans le dossier commun des retours, avec votre identifiant, "
            "le nom du poste, la date et les versions."
        )
        note.setWordWrap(True)
        self._etat = QLabel()
        self._etat.setWordWrap(True)
        self._etat.hide()
        boutons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        accepter = QDialogButtonBox.ButtonRole.AcceptRole
        self._envoyer = boutons.addButton("Envoyer", accepter)
        self._envoyer.setEnabled(False)
        self._envoyer.setAutoDefault(False)
        boutons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        boutons.accepted.connect(self._envoyer_retour)
        boutons.rejected.connect(self.reject)
        self._champ.textChanged.connect(
            lambda: self._envoyer.setEnabled(bool(self._champ.toPlainText().strip()))
        )
        disposition = QVBoxLayout(self)
        for widget in (etiquette, self._champ, note, self._etat, boutons):
            disposition.addWidget(widget)
        self.resize(460, 300)

    def _envoyer_retour(self) -> None:
        moment = dt.datetime.now()
        entete, dossiers = _contexte(moment)
        contenu = texte(self._champ.toPlainText(), entete, self._titre)
        nom = nom_fichier(moment, EXTENSION, entete["Auteur"])
        try:
            chemin = ecrire(dossiers, nom, contenu)
        except OSError as exc:
            # Le texte reste dans le champ : l'ingénieur peut le copier ou réessayer.
            self._etat.setText(f"⚠ Retour non enregistré : {exc}.")
            self._etat.show()
            return
        _annoncer(chemin, chemin.parent != dossiers[0])
        self._champ.clear()
        self._etat.hide()
        self.accept()


def _annoncer(chemin: Path, garde_ici: bool) -> None:
    from qgis.core import Qgis
    from qgis.utils import iface

    barre = getattr(iface, "messageBar", None)
    if barre is None:
        return
    if garde_ici:
        message = f"Partage injoignable : retour gardé dans {chemin}."
        barre().pushMessage("Retour", message, Qgis.MessageLevel.Warning, 0)
    else:
        message = f"Retour enregistré : {chemin.name}"
        barre().pushMessage("Retour", message, Qgis.MessageLevel.Success, 5)


_ouvert: dict[str, Any] = {}


def ouvrir(parent: QWidget | None = None) -> None:
    """Ouvre le dialogue, jamais deux fois. « Annuler » le cache sans vider le champ :
    rouvert, il rend le texte commencé."""
    dialogue = _ouvert.get("dialogue")
    if dialogue is not None:
        try:
            dialogue.show()
            dialogue.raise_()
            dialogue.activateWindow()
            return
        except RuntimeError:  # détruit avec la fenêtre qui le portait
            pass
    dialogue = _Dialogue(parent)
    _ouvert["dialogue"] = dialogue
    dialogue.show()


def bouton(parent: QWidget) -> QToolButton:
    """La petite icône de l'en-tête d'une fenêtre ; un clic ouvre le dialogue."""
    from qgis.core import QgsApplication

    outil = QToolButton(parent)
    outil.setObjectName(f"{EXTENSION}_bouton_retour")
    outil.setIcon(QgsApplication.getThemeIcon(ICONE))
    outil.setAutoRaise(True)
    outil.setToolTip("Envoyer un retour sur cette extension…")
    outil.setAccessibleName("Envoyer un retour")
    outil.clicked.connect(lambda: ouvrir(parent))
    return outil
