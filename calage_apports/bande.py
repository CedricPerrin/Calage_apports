"""Bande verticale des étapes, commune aux extensions de la maison (décision de l'ingénieur du
23/10/2026 : « format commun du menu à gauche », la bande de Rhoé ; étendue le même jour aux
autres extensions).

Chaque extension qui l'emploie en garde une copie identique (liste : ``D:\\1-Dev\\CLAUDE.md``,
« Coordination entre plugins ») : changer l'une, c'est changer toutes.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QModelIndex, QRectF, QSize, Qt
from qgis.PyQt.QtGui import QFont, QFontMetrics, QPainter, QPalette, QResizeEvent
from qgis.PyQt.QtWidgets import (
    QApplication,
    QListWidget,
    QProxyStyle,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)


class Bande(QListWidget):
    """Bande des étapes dont le bas n'est jamais coupé (retour de l'utilisateur du 11 octobre
    2026) : numéro et nom de chaque étape quand la hauteur les contient tous ; sinon le numéro
    seul ; si la place manque encore (écran bas, échelle 150 %), la bande défile. Le numéro est
    en gras (demande du 23/10/2026 : « pour mieux différencier les menus »).

    Une entrée non sélectionnable est un intitulé de groupe (:class:`NumeroGras`), le même
    texte dans ``complets`` et ``courts``. Sans l'indicateur « activé » non plus
    (``Qt.ItemFlag.NoItemFlags``), ni la souris ni les flèches du clavier ne s'y arrêtent."""

    def __init__(self, complets: list[str], courts: list[str], largeur: int, ligne: int) -> None:
        super().__init__()
        self._textes = (complets, courts)
        self._largeur = largeur
        self._hauteurs = [int(ligne * (texte.count("\n") + 1.4)) for texte in complets]
        #: Hauteur d'une étape réduite à son numéro, en px.
        self.hauteur_courte = int(ligne * 1.4)
        self._complete: bool | None = None
        self.setItemDelegate(NumeroGras(self))

    @property
    def hauteur_complete(self) -> int:
        """Hauteur de toutes les étapes avec leur nom, cadre compris, en px."""
        return sum(self._hauteurs) + 2 * self.frameWidth()

    def resizeEvent(self, evenement: QResizeEvent) -> None:  # noqa: N802 — API Qt
        """Choisit la forme des étapes à chaque changement de hauteur."""
        super().resizeEvent(evenement)
        self.ajuster(evenement.size().height())

    def ajuster(self, hauteur: int) -> None:
        """Numéro et nom si ``hauteur`` (px, cadre compris) les contient, numéro seul sinon."""
        complete = hauteur >= self.hauteur_complete
        if complete == self._complete:
            return
        self._complete = complete
        for rang in range(self.count()):
            element = self.item(rang)
            element.setText(self._textes[0 if complete else 1][rang])
            haut = self._hauteurs[rang] if complete else self.hauteur_courte
            element.setSizeHint(QSize(self._largeur, haut))


class NumeroGras(QStyledItemDelegate):
    """Dessine une étape : sa première ligne (le numéro) en gras, le reste (le nom) dessous en
    police normale, centrés ; fond, sélection et focus restent ceux du style de l'hôte. Une entrée
    non sélectionnable est un intitulé de groupe : un filet au-dessus, son texte en petit, sans
    fond alterné."""

    def paint(self, peintre: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """Le fond par le style, puis le texte en deux polices."""
        vue = QStyleOptionViewItem(option)
        self.initStyleOption(vue, index)
        texte, vue.text = vue.text, ""
        if not index.flags() & Qt.ItemFlag.ItemIsSelectable:
            self._intitule(peintre, vue, texte)
            return
        style = vue.widget.style() if vue.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, vue, peintre, vue.widget)
        # Les styles natifs de Windows peignent la sélection en clair et y écrivent le texte
        # ordinaire : leur « texte surligné » blanc s'y lirait mal (style de QGIS sous Windows,
        # enveloppé par QGIS dans un style mandataire ; constat du 23/10/2026).
        base = style.baseStyle() if isinstance(style, QProxyStyle) else style
        natif = base.metaObject().className() in ("QWindowsVistaStyle", "QWindows11Style")
        choisi = bool(vue.state & QStyle.StateFlag.State_Selected) and not natif
        role = QPalette.ColorRole.HighlightedText if choisi else QPalette.ColorRole.Text
        # Le groupe de couleurs de l'état, comme le style : fenêtre inactive, sélection grise.
        groupe = (
            QPalette.ColorGroup.Disabled
            if not vue.state & QStyle.StateFlag.State_Enabled
            else QPalette.ColorGroup.Active
            if vue.state & QStyle.StateFlag.State_Active
            else QPalette.ColorGroup.Inactive
        )
        # ``initStyleOption`` change les « \n » en séparateurs de ligne Unicode.
        numero, _, nom = texte.replace(" ", "\n").partition("\n")
        ligne = QFontMetrics(vue.font).lineSpacing()
        bloc = ligne * (1 + (nom.count("\n") + 1 if nom else 0))
        y = vue.rect.top() + (vue.rect.height() - bloc) / 2
        gras = QFont(vue.font)
        gras.setBold(True)
        peintre.save()
        peintre.setPen(vue.palette.color(groupe, role))
        peintre.setFont(gras)
        centre = int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        peintre.drawText(QRectF(vue.rect.left(), y, vue.rect.width(), ligne), centre, numero)
        if nom:
            peintre.setFont(vue.font)
            zone = QRectF(vue.rect.left(), y + ligne, vue.rect.width(), bloc - ligne)
            peintre.drawText(zone, centre, nom)
        peintre.restore()

    @staticmethod
    def _intitule(peintre: QPainter, vue: QStyleOptionViewItem, texte: str) -> None:
        """Intitulé de groupe : filet en haut, texte en :func:`police_intitule` au centre, dans la
        couleur du texte actif (une entrée désactivée prendrait le gris de la palette, trop pâle
        pour se lire)."""
        peintre.save()
        peintre.setPen(vue.palette.color(QPalette.ColorRole.Mid))
        haut = vue.rect.top() + 1
        peintre.drawLine(vue.rect.left() + 3, haut, vue.rect.right() - 3, haut)
        actif = QPalette.ColorGroup.Active
        peintre.setPen(vue.palette.color(actif, QPalette.ColorRole.Text))
        peintre.setFont(police_intitule(vue.font))
        peintre.drawText(QRectF(vue.rect), int(Qt.AlignmentFlag.AlignCenter), texte)
        peintre.restore()


def police_intitule(police: QFont) -> QFont:
    """Police d'un intitulé de groupe : celle de la bande, en gras, agrandie de 15 % (demande du
    23/10/2026 : les intitulés « ne sont pas lisibles en l'état » à 85 %, sans gras). L'hôte
    mesure ses intitulés dans cette police pour régler la largeur de la bande."""
    grande = QFont(police)
    if grande.pointSizeF() > 0:
        grande.setPointSizeF(grande.pointSizeF() * 1.15)
    grande.setBold(True)
    return grande
