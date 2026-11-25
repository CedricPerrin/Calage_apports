"""Barre de messages d'un panneau : chaque message se lit en entier.

Commune aux extensions de la maison qui posent une ``QgsMessageBar`` dans leur panneau
(décision de l'ingénieur du 25/11/2026 : « copie commune »). Chaque extension en garde
une **copie identique** (``<paquet>/barre.py``), comme ``cpn.py`` : changer l'une,
c'est changer toutes (``D:\\1-Dev\\CLAUDE.md``, « Coordination entre plugins »).
L'origine est celle de Plemmyra, testée par ``tests/gui/test_plugin.py``
(``test_la_barre_du_dock_montre_tout_le_message``). Un panneau la branche une fois,
juste après avoir créé sa barre : ``barre.suivre(self.barre)``.

QGIS borne le texte de chaque message à 1,75 em de haut (``min-height`` et
``max-height`` de la feuille de style du ``QTextBrowser`` de ``QgsMessageBarItem``) :
une ligne, pour la barre de la fenêtre. Dans un panneau de 345 à 420 px, le texte
passe à la ligne et ne montrait que deux demi-lignes (recette CPN du 24/11/2026, P4,
QGIS 3.44.14 ; sonde du 25/11/2026 : même défaut dans huit panneaux). Ici, la hauteur
du texte suit celle de son document, sans toucher à la feuille de style. Toutes les
lignes tiennent en 88 caractères : la copie passe le formateur de chaque dépôt.
"""

from __future__ import annotations

import math
import traceback
from typing import Any

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QEvent, QObject, Qt
from qgis.PyQt.QtWidgets import QTextBrowser, QWidget

#: Paquet de l'extension qui porte cette copie, onglet de ses erreurs au journal.
EXTENSION = __name__.rpartition(".")[0] or __name__


def suivre(barre: Any) -> None:
    """Chaque message posé dans ``barre`` (une ``QgsMessageBar``) se lit en entier."""
    barre.widgetAdded.connect(message_entier)


def message_entier(item: QWidget) -> None:
    """Le texte d'un message (``QgsMessageBarItem``) se lit en entier
    (:class:`TexteEntier`). Slot de ``widgetAdded`` : il ne lève jamais."""
    try:
        texte = item.findChild(QTextBrowser)
        if texte is not None:
            TexteEntier(texte)
    except Exception:
        _journal()


class TexteEntier(QObject):
    """La hauteur du texte d'un message suit celle de son document, à chaque
    changement de largeur ou de texte. La feuille de style de QGIS repose sa borne à
    chaque polissage (``Polish``, ``StyleChange``) : le filtre remet la hauteur juste
    derrière elle. Enfant du texte : il vit et meurt avec lui."""

    def __init__(self, texte: QTextBrowser) -> None:
        super().__init__(texte)
        self.texte = texte
        texte.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        texte.installEventFilter(self)
        mise_en_page = texte.document().documentLayout()
        # Une fermeture, pas la méthode liée : reliée par self.ajuster, la hauteur ne
        # suivait plus la largeur dans le dock de Plemmyra (test rouge, 25/11/2026).
        mise_en_page.documentSizeChanged.connect(lambda *_taille: self.ajuster())
        self.ajuster()

    def ajuster(self) -> None:
        """Hauteur du texte : celle de son document, marges comprises. Slot : il ne
        lève jamais."""
        try:
            marges = self.texte.contentsMargins()
            hauteur = math.ceil(self.texte.document().size().height())
            self.texte.setFixedHeight(hauteur + marges.top() + marges.bottom())
        except Exception:
            _journal()

    def eventFilter(self, _objet: QObject, evenement: QEvent) -> bool:  # noqa: N802
        """Après chaque polissage du texte, la hauteur de son document."""
        if evenement.type() in (QEvent.Type.Polish, QEvent.Type.StyleChange):
            self.ajuster()
        return False


def _journal() -> None:
    """La trace d'une erreur, au journal des messages, onglet de l'extension."""
    niveau = Qgis.MessageLevel.Critical
    QgsMessageLog.logMessage(traceback.format_exc(), EXTENSION, niveau)
