"""Barre d'outils « CPN », commune aux extensions QGIS de la maison.

Demande de l'ingénieur du 23/10/2026 : « pour l'ensemble des plugins, fais en sorte qu'ils
s'affichent dans la barre d'outils CPN ».

Chaque extension en garde une **copie identique** (``<paquet>/cpn.py``) : changer l'une, c'est
changer toutes (``D:\\1-Dev\\CLAUDE.md``, « Coordination entre plugins »). Aucune extension
n'importe une autre : la première chargée crée la barre, les suivantes la retrouvent par son nom
d'objet, la dernière déchargée la retire.
"""

from __future__ import annotations

from typing import Any

from qgis.PyQt.QtWidgets import QMenu, QToolBar

#: Nom d'objet de la barre : QGIS retient par lui sa place et sa visibilité d'une session à
#: l'autre, et chaque extension retrouve par lui la barre déjà créée.
NOM_OBJET = "CPN"
#: Titre de la barre, dans Vue → Barres d'outils.
TITRE = "CPN"


def _barre(iface: Any) -> QToolBar | None:
    fenetre = iface.mainWindow()
    return None if fenetre is None else fenetre.findChild(QToolBar, NOM_OBJET)


def ajouter(iface: Any, action: Any) -> None:
    """Pose ``action`` dans la barre « CPN », créée si aucune extension ne l'a encore fait.

    Une interface qui ne sait pas créer de barre (la doublure des tests) reçoit le bouton dans la
    barre « Extensions » de QGIS.
    """
    creer = getattr(iface, "addToolBar", None)
    if creer is None or iface.mainWindow() is None:
        iface.addToolBarIcon(action)
        return
    barre = _barre(iface)
    if barre is None:
        # La barre naît enfant de la fenêtre, puis QGIS l'accueille avec sa case du menu Vue. Pas
        # ``iface.addToolBar(TITRE)`` : la barre qu'il rend appartient à Python (SIP_FACTORY) et
        # meurt, bouton compris, à la sortie de cette fonction (constat du 23/10/2026 sous
        # QGIS 3.44.14 : aucune barre à l'écran, alors que les doublures des tests passaient).
        barre = QToolBar(TITRE, iface.mainWindow())
        barre.setObjectName(NOM_OBJET)
        creer(barre)
    barre.addAction(action)


def retirer(iface: Any, action: Any) -> None:
    """Retire ``action`` de la barre « CPN ». La dernière extension retire aussi la barre et sa case
    du menu Vue → Barres d'outils : ``removeToolBar`` ne détruit rien et laisse la case, qu'un
    rechargement doublerait (leçon de Calage des apports)."""
    barre = _barre(iface)
    if barre is None:
        iface.removeToolBarIcon(action)  # doublure des tests, ou barre « Extensions »
        return
    barre.removeAction(action)
    if barre.actions():
        return
    fenetre = iface.mainWindow()
    bascule = barre.toggleViewAction()
    for menu in fenetre.findChildren(QMenu):
        if bascule in menu.actions():
            menu.removeAction(bascule)
    fenetre.removeToolBar(barre)
    barre.setObjectName("")  # une extension rechargée avant la destruction ne la retrouve plus
    barre.deleteLater()
