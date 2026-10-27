# -*- coding: utf-8 -*-
"""Présentation Qt : thèmes, typographie et textes d'état lisibles."""

import re

from qgis.PyQt.QtCore import QEvent, Qt
from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QLabel, QTableWidget, QTextBrowser

from . import lexique


COULEURS_SOMBRES = {
    "#3a8d94": "#7CC4C8", "#2e7176": "#7CC4C8",
    "#608098": "#BBCAD2", "#526b7a": "#BBCAD2",
    "#9baeb7": "#BBCAD2", "#a03028": "#F29D97",
    "#3e7a5e": "#91CDAA", "#386f55": "#91CDAA",
}


def sombre(widget):
    return widget.palette().color(QPalette.ColorRole.Window).lightness() < 128


def couleur(nom_hex, widget):
    """
    La couleur de charte à employer sur CE widget : remappée s'il est sombre.

    Les textes riches passent par texte_theme ; les widgets dessinés au
    QPainter — ruban, jauges, courbe du suivi — et le tableau du suivi
    n'y passaient pas et gardaient les teintes du thème clair sur le fond
    Night Mapping : l'ardoise y tombait à 2,3:1, le rouge à 1,8:1
    (docs/ergonomie_2026-09-17.md, C1). Même table que texte_theme, pour que
    les deux ne divergent pas ; une couleur qui n'y figure pas est rendue
    telle quelle.
    """
    if sombre(widget):
        nom_hex = COULEURS_SOMBRES.get(nom_hex.lower(), nom_hex)
    return QColor(nom_hex)


def texte_theme(texte, widget):
    """Adapter les couleurs du texte riche sans toucher aux données affichées."""
    if not sombre(widget):
        return texte
    # Ne remplacer que les déclarations CSS : un nom de fichier peut lui
    # aussi contenir « #A03028 » et doit rester copiable à l'identique.
    texte = re.sub(r"(?<![-\w])(color\s*:\s*)(#[0-9a-fA-F]{6})\b",
                   lambda m: m[1] + COULEURS_SOMBRES.get(m[2].lower(), m[2]),
                   texte, flags=re.IGNORECASE)
    return re.sub(r"<a\s+href=", '<a style="color:#7CC4C8" href=', texte)


class Etiquette(QLabel):
    """Garder les états HTML lisibles, même après un changement de thème."""

    def __init__(self, texte="", parent=None):
        super().__init__(parent)
        self._texte_original = texte
        self.setText(texte)

    def setText(self, texte):  # noqa: N802
        self._texte_original = texte
        super().setText(texte_theme(texte, self))

    def changeEvent(self, evenement):  # noqa: N802
        super().changeEvent(evenement)
        if evenement.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            texte = getattr(self, "_texte_original", "")
            super().setText(texte_theme(texte, self))


class EtiquetteLexique(Etiquette):
    """
    Texte d'aide ou ligne d'etat dont chaque terme du lexique est un lien
    discret, a la couleur du texte et sans soulignement (27/10/2026, comme
    Plemmyra, Hyetos et Rhoe) : le survol montre les definitions, le clic
    emet linkActivated(« terme:<cle> »), que la fenetre suit vers l'aide.
    text() rend le texte donne, sans les liens : le code et le banc le
    relisent tel quel. Sans terme, le texte s'affiche comme avant.
    """

    _format = None       # format d'avant le texte riche, rendu sans terme
    _definitions = ""

    def text(self):
        return getattr(self, "_texte_original", "")

    def setText(self, texte):  # noqa: N802
        self._texte_original = texte
        self._afficher()

    def changeEvent(self, evenement):  # noqa: N802
        QLabel.changeEvent(self, evenement)
        if evenement.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            self._afficher()

    def _afficher(self):
        texte = getattr(self, "_texte_original", "")
        lie = lexique.lier(texte)
        definitions = lexique.resume(texte) if f'href="{lexique.PREFIXE}' in lie else ""
        # Une infobulle posee par l'appelant n'est pas remplacee.
        if self.toolTip() in ("", self._definitions):
            self.setToolTip(definitions)
        self._definitions = definitions
        self.setAccessibleDescription(definitions)
        if definitions:
            if self._format is None:
                self._format = self.textFormat()
            self.setTextFormat(Qt.TextFormat.RichText)
            # La couleur du libelle, feuille de style comprise (role « aide »).
            texte = lexique.liens_discrets(
                lie, self.palette().color(QPalette.ColorRole.WindowText).name())
        elif self._format is not None:
            self.setTextFormat(self._format)
            self._format = None
        QLabel.setText(self, texte_theme(texte, self))


class TableauTriable(QTableWidget):
    """
    Double-clic sur un en-tete : lignes classees par cette colonne, croissant,
    puis decroissant, puis de nouveau dans leur ordre d'origine ; cellules
    vides ou « — » en dernier ; cases cochees en tete ; « 98,5 % » lu comme un
    nombre. Repris de Rhoe (rhoe/gui/tableau.py, triable), demande du
    27/10/2026. Seul l'ordre AFFICHE change (en-tete vertical) : le rang d'une
    ligne, que le code et le banc lisent, reste le meme. Appeler reclasser()
    apres avoir reecrit les cellules.
    """

    _tri = None          # (colonne, croissant) ; None : ordre d'origine

    def __init__(self, *args):
        super().__init__(*args)
        self.horizontalHeader().sectionDoubleClicked.connect(self._trier)
        # Qt retourne sa fleche a chaque simple clic sur un en-tete, sans rien classer.
        self.horizontalHeader().sortIndicatorChanged.connect(self._garder_fleche)

    def _trier(self, colonne):
        self._tri = None if self._tri == (colonne, False) else (
            colonne, self._tri != (colonne, True))
        self.horizontalHeader().setSortIndicatorShown(self._tri is not None)
        self._garder_fleche()
        self.reclasser()

    def _garder_fleche(self, *_signal):
        """La fleche de l'en-tete montre le classement reel."""
        if self._tri is None:
            return
        colonne, croissant = self._tri
        ordre = Qt.SortOrder.AscendingOrder if croissant else Qt.SortOrder.DescendingOrder
        entete = self.horizontalHeader()
        if (entete.sortIndicatorSection(), entete.sortIndicatorOrder()) != (colonne, ordre):
            entete.setSortIndicator(colonne, ordre)

    def _cle(self, rang, colonne):
        """Cle de classement d'une cellule : sa case, son nombre, ou son texte ; None vide."""
        cellule = self.item(rang, colonne)
        if cellule is None:
            return None
        # Qt rend toute cellule « cochable » : seule une case posee a un etat.
        if cellule.data(Qt.ItemDataRole.CheckStateRole) is not None:
            return (0, 0 if cellule.checkState() == Qt.CheckState.Checked else 1)
        texte = cellule.text().strip()
        if texte in ("", "—"):
            return None
        try:
            return (0, float(re.sub(r"[\s%]", "", texte).replace(",", ".").replace("−", "-")))
        except ValueError:
            return (1, texte.casefold())

    def reclasser(self):
        rangs = list(range(self.rowCount()))
        if self._tri is not None:
            colonne, croissant = self._tri
            cles = {rang: self._cle(rang, colonne) for rang in rangs}
            pleins = sorted((r for r in rangs if cles[r] is not None),
                            key=cles.__getitem__, reverse=not croissant)
            rangs = pleins + [r for r in rangs if cles[r] is None]
        vertical = self.verticalHeader()
        for position, rang in enumerate(rangs):
            vertical.moveSection(vertical.visualIndex(rang), position)


def _liens_discrets(texte, widget):
    """Les liens du lexique et des sources a la couleur du texte du navigateur."""
    return lexique.liens_discrets(texte, widget.palette().color(QPalette.ColorRole.Text).name())


class Manuel(QTextBrowser):
    def setHtml(self, texte):  # noqa: N802
        self._html_original = texte
        super().setHtml(texte_theme(_liens_discrets(texte, self), self))

    def changeEvent(self, evenement):  # noqa: N802
        super().changeEvent(evenement)
        if evenement.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            texte = getattr(self, "_html_original", None)
            if texte is not None:
                position = self.verticalScrollBar().value()
                super().setHtml(texte_theme(_liens_discrets(texte, self), self))
                self.verticalScrollBar().setValue(position)


def feuille(palette, taille=10):
    """Les surfaces et contrôles héritent du thème QGIS ; seul l'accent est ISL."""
    nuit = palette.color(QPalette.ColorRole.Window).lightness() < 128
    accent = "#7CC4C8" if nuit else "#2E7176"
    secondaire = "#BBCAD2" if nuit else "#526B7A"
    fond = palette.color(QPalette.ColorRole.Window).name()
    texte = palette.color(QPalette.ColorRole.WindowText).name()
    return f"""
QWidget {{ font-size: {taille:g}pt; }}
QDialog#calageFenetre {{ background: {fond}; color: {texte}; }}
QLabel[role="marque"] {{ font-size: {taille + 5:g}pt; font-weight: bold; color: {accent}; }}
QLabel[role="aide"] {{ color: {secondaire}; padding: 2px 0; }}
QLabel[role="etat"] {{ background: palette(base); padding: 8px; border: 1px solid palette(mid); }}
QLabel#filConducteur {{ padding: 8px 2px; }}
QTabWidget::pane {{ border: none; }}
QGroupBox {{ border: 1px solid palette(mid); border-radius: 3px; margin-top: 14px; padding: 12px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 9px; padding: 0 5px; color: {accent}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ min-height: 24px; }}
QLineEdit {{ padding: 2px 4px; }}
QPushButton {{ padding: 6px 12px; min-height: 20px; }}
QPushButton:focus {{ border: 2px solid palette(highlight); padding: 5px 11px; }}
QPushButton#boutonPrincipal, QPushButton#boutonControlePret {{
    background: #2E7176; color: white; border: 1px solid #2E7176;
    border-radius: 3px; font-weight: bold; padding: 7px 15px;
}}
QPushButton#boutonControlePret {{ background: #386F55; border-color: #386F55; }}
QPushButton#boutonPrincipal:hover, QPushButton#boutonControlePret:hover {{ background: #245A5E; }}
QPushButton#boutonControleAttente {{ color: {texte}; font-weight: bold; }}
QPushButton#boutonAccent {{ font-weight: bold; color: {accent}; }}
QPushButton#boutonPrincipal:focus, QPushButton#boutonControlePret:focus {{ border: 2px solid palette(highlight); padding: 6px 14px; }}
QPushButton:disabled {{ color: palette(mid); }}
QTextEdit#resume {{ border: 1px solid palette(mid); padding: 4px; }}
QTextBrowser {{ border: none; }}
QProgressBar {{ min-height: 24px; text-align: center; border: 1px solid palette(mid); background: palette(base); }}
QProgressBar::chunk {{ background: #2E7176; }}
QTableWidget {{ gridline-color: palette(mid); }}
QHeaderView::section {{ padding: 6px; background: palette(base); color: {secondaire}; font-weight: bold; }}
"""
