# -*- coding: utf-8 -*-
"""Présentation Qt : thèmes, typographie et textes d'état lisibles."""

import re

from qgis.PyQt.QtCore import QEvent
from qgis.PyQt.QtGui import QPalette
from qgis.PyQt.QtWidgets import QLabel, QTextBrowser


COULEURS_SOMBRES = {
    "#3a8d94": "#7CC4C8", "#2e7176": "#7CC4C8",
    "#608098": "#BBCAD2", "#526b7a": "#BBCAD2",
    "#9baeb7": "#BBCAD2", "#a03028": "#F29D97",
    "#3e7a5e": "#91CDAA", "#386f55": "#91CDAA",
}


def sombre(widget):
    return widget.palette().color(QPalette.ColorRole.Window).lightness() < 128


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


class Manuel(QTextBrowser):
    def setHtml(self, texte):  # noqa: N802
        self._html_original = texte
        super().setHtml(texte_theme(texte, self))

    def changeEvent(self, evenement):  # noqa: N802
        super().changeEvent(evenement)
        if evenement.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange):
            texte = getattr(self, "_html_original", None)
            if texte is not None:
                position = self.verticalScrollBar().value()
                super().setHtml(texte_theme(texte, self))
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
QTabBar::tab {{ padding: 8px 12px; border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ color: {accent}; border-bottom-color: {accent}; }}
QTabBar::tab:focus {{ border-bottom-color: palette(highlight); }}
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
