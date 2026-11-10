# -*- coding: utf-8 -*-
"""
Filet de la peinture de l'etape Suivi : PageSuivi._peindre_suivi et
CourbeComparaison.paintEvent, figes avant leur decoupage (11/2026).

CE QUI EST FIGE. Pour chaque scenario, l'ETAT COMPLET de la page apres la
peinture : chaque widget (classe, nom, masque ou non, actif ou non, texte,
infobulle, valeur, feuille de style, nom et description accessibles), chaque
cellule du tableau (texte, couleurs, gras, alignement, ordre affiche), ce
qu'on a passe au ruban, aux jauges et a la courbe, et la SUITE DES ORDRES
DE PEINTURE de ces trois widgets (stylos, pinceaux, textes, polylignes
ramenees a leur cadre). S'y ajoutent, sur le poste de reference seulement,
la geometrie et l'empreinte des images rendues.

POURQUOI DEUX NIVEAUX. Une image depend de la police installee, de FreeType
et de la version de Qt : elle ne se compare au pixel pres que sur un poste
identique a celui qui a fige la reference (signature « poste » de la
reference). Ailleurs — la CI joue QGIS 3.44 et 4.2 dans des images Docker —,
le test compare tout le reste et le DIT par un avertissement. Les ordres de
peinture, eux, ne dependent pas de la police : ils restent compares partout.

LES ETATS SONT ECRITS PAR LE VRAI src/suivi.py (classe Suivi), comme dans
src/bancs/banc_suivi.py, l'horloge et le PID figes A LA SOURCE ; seules les
figures et classeurs (matplotlib, openpyxl), que la page ne lit pas, sont
court-circuites : _produire n'ecrit que l'etat machine. Le dossier surveille
est un chemin RELATIF au dossier temporaire du scenario : aucun chemin
variable n'entre dans ce qui est compare.

A lancer sous le Python de QGIS, hors ecran :

    QT_QPA_PLATFORM=offscreen python3 -m pytest src/test_peinture_suivi.py

PEINTURE_SUIVI_REGENERER=1 reecrit la reference (sur le code SAIN
seulement). PEINTURE_SUIVI_AUTRE_POSTE=1 simule un poste etranger : les
images et la geometrie ne sont plus comparees.
"""
import copy
import difflib
import hashlib
import json
import os
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC = Path(__file__).resolve().parent
RACINE = SRC.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(SRC))

# ORDRE IMPOSE : qgis.core avant tout le reste (voir test_plugin_qgis.py).
from qgis.core import QgsApplication  # noqa: E402
from qgis.PyQt.QtCore import QT_VERSION_STR, QPointF, QRectF, Qt  # noqa: E402
from qgis.PyQt.QtGui import (QBrush, QColor, QFont, QFontInfo,  # noqa: E402
                             QFontMetrics, QImage, QPainter, QPalette, QPen)
from qgis.PyQt.QtWidgets import (QAbstractButton, QAbstractSpinBox,  # noqa: E402
                                 QApplication, QGroupBox, QLabel,
                                 QProgressBar, QScrollBar, QTextEdit,
                                 QWidget)

REFERENCE = SRC / "reference_peinture_suivi.json"
REGENERER = os.environ.get("PEINTURE_SUIVI_REGENERER") == "1"
AUTRE_POSTE = os.environ.get("PEINTURE_SUIVI_AUTRE_POSTE") == "1"

# L'instant de toutes les peintures, et le PID que publie le « calage ».
INSTANT = datetime(2026, 11, 10, 14, 30, 0)
PID_CALAGE = 4242
PID_LANCE = 5151
POLICE = "DejaVu Sans"
TAILLE_PAGE = (900, 1500)


# ---------------------------------------------------------------------------
# Application, theme et police
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qgis_app(tmp_path_factory):
    if os.environ.get("QGIS_PREFIX_PATH"):
        QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication.instance() or QgsApplication([], True)
    app.initQgis()
    # Fusion partout : le style natif change d'un poste a l'autre.
    QApplication.setStyle("Fusion")
    yield app
    app.processEvents()


def _palette(theme):
    """Palette FIXE, construite ici : celle du style varie avec Qt."""
    if theme == "sombre":
        fond, texte, base = "#353535", "#f0f0f0", "#232323"
    else:
        fond, texte, base = "#efefef", "#1a1a1a", "#ffffff"
    pal = QPalette(QColor(fond), QColor(fond))
    for role, valeur in ((QPalette.ColorRole.WindowText, texte),
                         (QPalette.ColorRole.Text, texte),
                         (QPalette.ColorRole.ButtonText, texte),
                         (QPalette.ColorRole.Base, base),
                         (QPalette.ColorRole.AlternateBase, fond),
                         (QPalette.ColorRole.ToolTipBase, base),
                         (QPalette.ColorRole.ToolTipText, texte),
                         (QPalette.ColorRole.Highlight, "#2e7176"),
                         (QPalette.ColorRole.HighlightedText, "#ffffff")):
        pal.setColor(role, QColor(valeur))
    return pal


def _appliquer_poste(theme, points):
    """Palette et police de l'application, comme QGIS les poserait."""
    QApplication.setPalette(_palette(theme))
    QApplication.setFont(QFont(POLICE, points))


def _feuille(points):
    """La feuille que le dialogue pose (DialogueParametrage._actualiser_style)."""
    from calage_apports.interface import feuille
    return feuille(QApplication.palette(), max(10.0, float(points)))


def _entier(valeur):
    """Valeur entiere d'une enumeration Qt, en Qt 5 comme en Qt 6."""
    valeur = getattr(valeur, "value", valeur)
    try:
        return int(valeur)
    except TypeError:
        return str(valeur)


def _argb(couleur):
    return QColor(couleur).name(QColor.NameFormat.HexArgb)


def _empreinte_image(image):
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    brut = image.constBits()
    brut.setsize(image.sizeInBytes())
    return hashlib.sha256(bytes(brut)).hexdigest()[:20]


def signature_poste():
    """
    Ce qui doit etre identique pour que deux images se comparent au pixel.

    La famille demandee ne suffit pas : on en mesure les metriques et on rend
    un echantillon de texte, ce qui capte FreeType et l'anticrenelage.
    """
    signature = {"qt": QT_VERSION_STR, "plateforme": QApplication.platformName(),
                 "style": QApplication.style().objectName()}
    for points in (9, 13):
        police = QFont(POLICE, points)
        m = QFontMetrics(police)
        image = QImage(160, 40, QImage.Format.Format_ARGB32)
        image.fill(QColor("#ffffff"))
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(police)
        p.drawText(QRectF(0, 0, 160, 40), _entier(Qt.AlignmentFlag.AlignCenter),
                   "Calé — 1 234,5 m³/s ✔")
        p.end()
        signature[f"{points}pt"] = {
            "famille": QFontInfo(police).family(),
            "metriques": [m.height(), m.lineSpacing(),
                          m.horizontalAdvance("Calage terminé — conforme 0123")],
            "echantillon": _empreinte_image(image)}
    if AUTRE_POSTE:
        signature["simule"] = "autre poste"
    return signature


# ---------------------------------------------------------------------------
# Le peintre qui consigne : ordres de peinture des widgets peints
# ---------------------------------------------------------------------------

def _r(v):
    return round(float(v), 2)


def _decrire_pinceau(arg):
    if isinstance(arg, QPen):
        return ["stylo", _argb(arg.color()), _r(arg.widthF()), _entier(arg.style())]
    if isinstance(arg, QBrush):
        return ["brosse", _argb(arg.color()), _entier(arg.style())]
    if isinstance(arg, QColor):
        return ["couleur", _argb(arg)]
    if isinstance(arg, (str, Qt.GlobalColor)):
        return ["couleur", _argb(QColor(arg))]
    return ["style", _entier(arg)]


def _decrire_forme(args):
    """Coordonnees d'un ordre de dessin : rectangle, points ou nombres."""
    rendu = []
    for a in args:
        if isinstance(a, QRectF):
            rendu.append([_r(a.x()), _r(a.y()), _r(a.width()), _r(a.height())])
        elif isinstance(a, QPointF):
            rendu.append([_r(a.x()), _r(a.y())])
        elif isinstance(a, (int, float)):
            rendu.append(_r(a))
    return rendu


class PeintreTrace(QPainter):
    """
    QPainter qui consigne ses ordres, en deux colonnes :
    - « portable » : ce qui ne depend pas de la police du poste — l'ordre,
      les couleurs, les textes, et les polylignes RAMENEES A LEUR CADRE
      (le rectangle de decoupe courant), ou elles se lisent en fractions ;
    - « complet » : la meme chose avec les coordonnees en pixels.
    """
    portable = None
    complet = None

    def _noter(self, portable, coords=None):
        if PeintreTrace.portable is None:
            return
        PeintreTrace.portable.append(portable)
        PeintreTrace.complet.append(portable + ([coords] if coords is not None else []))

    def setRenderHint(self, *a):                            # noqa: N802
        self._noter(["rendu", [_entier(x) for x in a]])
        return super().setRenderHint(*a)

    def setPen(self, arg):                                  # noqa: N802
        self._noter(["setPen"] + _decrire_pinceau(arg))
        return super().setPen(arg)

    def setBrush(self, arg):                                # noqa: N802
        self._noter(["setBrush"] + _decrire_pinceau(arg))
        return super().setBrush(arg)

    def setFont(self, police):                              # noqa: N802
        self._noter(["setFont", _r(police.pointSizeF()), police.bold()])
        return super().setFont(police)

    def translate(self, *a):
        self._noter(["translate"], _decrire_forme(a))
        return super().translate(*a)

    def drawText(self, *a):                                 # noqa: N802
        # (rect, drapeaux, texte) ou (x, y, l, h, drapeaux, texte).
        drapeaux = _entier(a[-2]) if len(a) in (3, 6) else None
        self._noter(["drawText", a[-1], drapeaux],
                    _decrire_forme(a[:-2] if drapeaux is not None else a[:-1]))
        return super().drawText(*a)

    def drawLine(self, *a):                                 # noqa: N802
        self._noter(["drawLine"], _decrire_forme(a))
        return super().drawLine(*a)

    def drawRect(self, *a):                                 # noqa: N802
        self._noter(["drawRect"], _decrire_forme(a))
        return super().drawRect(*a)

    def drawRoundedRect(self, *a):                          # noqa: N802
        self._noter(["drawRoundedRect"], _decrire_forme(a))
        return super().drawRoundedRect(*a)

    def setClipRect(self, rect, *a):                        # noqa: N802
        self._cadre = QRectF(rect)
        self._noter(["setClipRect"], _decrire_forme([rect]))
        return super().setClipRect(rect, *a)

    def setClipping(self, actif):                           # noqa: N802
        self._noter(["setClipping", bool(actif)])
        return super().setClipping(actif)

    def drawPolyline(self, polygone):                       # noqa: N802
        cadre = getattr(self, "_cadre", None)
        points = [polygone.at(i) for i in range(polygone.count())]

        def fraction(v, origine, etendue):
            # DEUX ARRONDIS : le premier efface le bruit flottant (la marge de
            # gauche suit la police), le second ne tombe donc plus jamais de
            # part et d autre d une demi-unite selon le poste.
            return round(round((v - origine) / etendue, 9), 4) if etendue else None

        relatifs = ([[fraction(p.x(), cadre.x(), cadre.width()),
                      fraction(p.y(), cadre.y(), cadre.height())] for p in points]
                    if cadre is not None else None)
        self._noter(["drawPolyline", len(points), relatifs],
                    [[_r(p.x()), _r(p.y())] for p in points])
        return super().drawPolyline(polygone)

    def end(self):
        self._noter(["end"])
        return super().end()


def _peindre(widget, taille=None):
    """Rend un widget, et rend (ordres portables, ordres complets, image)."""
    if taille is not None:
        widget.resize(*taille)
    PeintreTrace.portable, PeintreTrace.complet = [], []
    try:
        image = widget.grab().toImage()
    finally:
        portable, complet = PeintreTrace.portable, PeintreTrace.complet
        PeintreTrace.portable = PeintreTrace.complet = None
    return portable, complet, image


# ---------------------------------------------------------------------------
# Releve de l'etat complet de la page
# ---------------------------------------------------------------------------

def _json(v):
    """Forme canonique, NaN compris (json les ecrit, l'egalite les rate)."""
    return json.loads(json.dumps(v, ensure_ascii=False, default=str))


def _empreinte(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False,
                                     default=str).encode()).hexdigest()[:20]


# Les enfants internes de Qt (ascenseurs, coins, boutons de repli...) changent
# d'une version de Qt a l'autre : ils ne vont qu'au releve « poste ».
def _interne(w, page):
    while w is not None and w is not page:
        if (w.objectName().startswith("qt_") or isinstance(w, QScrollBar)
                or w.objectName() == "collapseButton"
                or type(w).__name__ in ("QgsGroupBoxCollapseButton",
                                        "QHeaderView", "QTableCornerButton",
                                        "QAbstractButton", "QFocusFrame")):
            return True
        w = w.parentWidget()
    return False


def _decrire_widget(w):
    d = {"classe": type(w).__name__, "nom": w.objectName(),
         "masque": w.isHidden(), "actif": w.isEnabled(),
         "infobulle": w.toolTip(), "style": w.styleSheet(),
         "nom_accessible": w.accessibleName(),
         "description_accessible": w.accessibleDescription()}
    role = w.property("role")
    if role is not None:
        d["role"] = role
    if isinstance(w, QLabel):
        d["texte"] = w.text()
        d["texte_rendu"] = QLabel.text(w)
        d["format"] = _entier(w.textFormat())
    if isinstance(w, QAbstractButton):
        d["texte"] = w.text()
    if isinstance(w, QGroupBox):
        d["titre"] = w.title()
        if hasattr(w, "isCollapsed"):
            d["replie"] = w.isCollapsed()
    if isinstance(w, QProgressBar):
        d["valeur"] = w.value()
        d["texte"] = w.text()
    if isinstance(w, QTextEdit):
        d["texte"] = w.toPlainText()
    if isinstance(w, QAbstractSpinBox):
        d["texte"] = w.text()
    return d


def _decrire_table(t):
    entete = t.horizontalHeader()
    vertical = t.verticalHeader()
    cellules = []
    for r in range(t.rowCount()):
        ligne = []
        for c in range(t.columnCount()):
            it = t.item(r, c)
            if it is None:
                ligne.append(None)
                continue
            # [texte, encre, style d'encre, style de fond, gras, alignement,
            #  infobulle] : une liste, la reference en compte des milliers.
            ligne.append([it.text(), _argb(it.foreground().color()),
                          _entier(it.foreground().style()),
                          _entier(it.background().style()), it.font().bold(),
                          _entier(it.textAlignment()), it.toolTip()])
        cellules.append(ligne)
    return {"lignes": t.rowCount(), "colonnes": t.columnCount(),
            "entetes": [t.horizontalHeaderItem(c).text() if t.horizontalHeaderItem(c)
                        else None for c in range(t.columnCount())],
            "ordre_affiche": [vertical.logicalIndex(p) for p in range(t.rowCount())],
            "tri": [entete.isSortIndicatorShown(), entete.sortIndicatorSection(),
                    _entier(entete.sortIndicatorOrder())],
            "cellules": cellules}


def _resumer(v):
    """Les longues series de nombres, par leur longueur et leur empreinte."""
    if isinstance(v, dict):
        return {k: _resumer(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        if len(v) > 6 and all(_numerique(x) or (isinstance(x, (list, tuple))
                                                 and all(map(_numerique, x)))
                              for x in v):
            return {"n": len(v), "empreinte": _empreinte(_json(v))}
        return [_resumer(x) for x in v]
    return v


def _numerique(x):
    return x is None or (isinstance(x, (int, float)) and not isinstance(x, bool))


def widgets_portables(page):
    """La description de chaque widget de la page, hors enfants internes de Qt."""
    return [_decrire_widget(w) for w in page.findChildren(QWidget)
            if not _interne(w, page)]


def releve_page(page, neuve):
    """
    (portable, poste) : l'etat complet de la page apres peinture.

    Les widgets sont decrits PAR DIFFERENCE avec la page neuve (« neuve »,
    relevee avant le scenario, et elle-meme figee par test_page_neuve) : la
    reference garde ainsi ce que la peinture a change, sans recopier quarante
    fois les libelles qu'elle ne touche pas.
    """
    page.layout().activate()
    QApplication.processEvents()
    widgets, geometrie = [], []
    for w in page.findChildren(QWidget):
        g = w.geometry()
        geometrie.append([type(w).__name__, w.objectName(), g.x(), g.y(),
                          g.width(), g.height(), w.isVisible()])
        if isinstance(w, QScrollBar):
            geometrie.append([w.minimum(), w.maximum(), w.value()])
        if _interne(w, page):
            continue
        widgets.append(_decrire_widget(w))
    assert len(widgets) == len(neuve), "la peinture a cree ou detruit des widgets"
    changes = {}
    for i, (avant, apres) in enumerate(zip(neuve, widgets)):
        ecarts = {k: v for k, v in apres.items() if avant.get(k) != v}
        if ecarts:
            changes[f"{i:02d} {apres['classe']} {apres['nom']}".strip()] = ecarts
    table = page.table_suivi
    portable = {
        "widgets": changes,
        "table": _decrire_table(table),
        "ruban": {"apports": _resumer(page.ruban_apports.apports),
                  "en_cours": page.ruban_apports.en_cours},
        "jauges": {cle: {"libelle": j.libelle, "tolerance": j.tolerance,
                         "valeur": j.valeur, "lecture": list(j.lecture())}
                   for cle, j in page.jauges.items()},
        "courbe": {"courbes": _resumer(page.courbe_suivi.courbes),
                   "precedentes": _resumer(page.courbe_suivi.precedentes)},
        "ordres": {},
    }
    poste = {"geometrie": _empreinte(geometrie),
             "colonnes": [table.columnWidth(c) for c in range(table.columnCount())]}
    peints = [("ruban", page.ruban_apports), ("courbe", page.courbe_suivi)]
    peints += [(f"jauge_{cle}", j) for cle, j in page.jauges.items()]
    for nom, w in peints:
        ordres, complet, image = _peindre(w)
        portable["ordres"][nom] = _resumer(ordres)
        poste[f"ordres_{nom}"] = _empreinte(complet)
        poste[f"image_{nom}"] = _empreinte_image(image)
    poste["image_page"] = _empreinte_image(page.grab().toImage())
    return _json(portable), poste


# ---------------------------------------------------------------------------
# Atelier : un dossier de suivi ecrit par le vrai Suivi, un faux dialogue
# ---------------------------------------------------------------------------

class Horloge(datetime):
    """datetime dont now() rend l'instant du scenario."""
    instant = INSTANT

    @classmethod
    def now(cls, tz=None):
        return cls.instant


def _hydrogramme(t, pic, t_pic=6.0, forme=2.5):
    import numpy as np
    t = np.maximum(np.asarray(t, dtype=float), 1e-3)
    return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))


class DialogueFactice:
    """Ce que PageSuivi lit sur le dialogue (voir sa docstring), et rien d'autre."""

    def __init__(self, atelier):
        self._atelier = atelier
        self.pid_lance = None
        self.instant_lance = None
        self.journal_lance = None
        self.classeur = None
        self._cle_journal_lu = None
        self.signalements = []

    def _dossier_suivi(self):
        return self._atelier.surveille

    def _origine_dossier_suivi(self):
        return self._atelier.origine

    def _detail_desaccord_suivi(self, dossier):
        return self._atelier.desaccord

    def _signaler(self, *a):
        self.signalements.append(a)


class Atelier:
    def __init__(self, page, dialogue):
        self.page = page
        self.dialogue = dialogue
        self.dossier = Path("calage") / "suivi"
        self.surveille = self.dossier
        self.origine = "Excel lancé"
        self.desaccord = ""
        self.vivants = {}
        self.appels_vivant = []
        self.releves = []
        self.neuve = widgets_portables(page)

    # -- horloge ----------------------------------------------------------
    def a(self, minutes):
        """Place l'horloge a INSTANT + minutes (negatif : avant la peinture)."""
        Horloge.instant = INSTANT + timedelta(minutes=minutes)

    # -- etats ecrits par le vrai suivi -----------------------------------
    def suivi(self, apports, sections=None, tolerances=None, minutes=-60):
        import suivi as module_suivi
        self.a(minutes)
        s = module_suivi.Suivi(self.dossier, apports,
                               sections or [f"S_{a}" for a in apports],
                               tolerances=tolerances)
        # L'ETAT MACHINE SEUL : figures et classeurs ne sont pas lus par la page.
        s._produire = lambda series=None: s._ecrire_etat()
        return s

    def essai(self, s, i, volume, pic, forme=0.97, decalage=0.0, series=True,
              minutes=None):
        if minutes is not None:
            self.a(minutes)
        serie = None
        if series:
            import numpy as np
            t = np.linspace(0.0, 24.0, 97)
            qc = _hydrogramme(t, 40.0 + 15.0 * i)
            qs = _hydrogramme(t - 0.25 * (i % 3), (40.0 + 15.0 * i) * pic)
            serie = (t, qc, t, qs)
        s.enregistrer_essai(i, 1.0 + 0.1 * i, volume, pic, forme, decalage,
                            series=serie, decalage_correction=decalage)

    def valider(self, s, i, volume=1.001, pic=0.998, minutes=None, duree_s=1800.0):
        if minutes is not None:
            self.a(minutes)
        diag = SimpleNamespace(rapport_volume=volume, rapport_pic=pic, r=0.991,
                               decalage_h=0.25)
        s.valider_apport(i, diag, duree_s=duree_s)

    def caler(self, s, i, minutes=None):
        """Un apport mene jusqu'a validation, en deux essais."""
        s.commencer_apport(i)
        self.essai(s, i, 0.95, 0.93, minutes=minutes)
        self.essai(s, i, 1.001, 0.998)
        self.valider(s, i)

    def etat(self):
        return json.loads((self.dossier / "avancement.json").read_text(encoding="utf-8"))

    def reecrire(self, etat=None, brut=None):
        chemin = self.dossier / "avancement.json"
        if brut is None:
            brut = json.dumps(etat, ensure_ascii=False, indent=1)
        chemin.write_text(brut, encoding="utf-8")

    def retoucher(self, **champs):
        etat = self.etat()
        etat.update(champs)
        self.reecrire(etat)
        return etat

    # -- peinture ----------------------------------------------------------
    def peindre(self, minutes=0):
        self.a(minutes)
        del self.appels_vivant[:]
        self.page._peindre_suivi()
        portable, poste = releve_page(self.page, self.neuve)
        portable["processus_vivant"] = list(self.appels_vivant)
        portable["signalements"] = [list(map(str, s)) for s in self.dialogue.signalements]
        self.releves.append((portable, poste))


# ---------------------------------------------------------------------------
# Scenarios de la page
# ---------------------------------------------------------------------------

def sc_aucun_dossier(at):
    at.surveille = None
    at.peindre()


def sc_dossier_vide(at):
    at.dossier.mkdir(parents=True)
    at.origine = "étape Paramètres"
    at.peindre()


def _lance(at, secondes, vivant, journal=True):
    at.dossier.mkdir(parents=True)
    d = at.dialogue
    d.pid_lance = PID_LANCE
    d.instant_lance = INSTANT - timedelta(seconds=secondes)
    d.journal_lance = str(Path("calage") / "calage_20261110.log") if journal else None
    at.vivants[PID_LANCE] = vivant


def sc_lance_sans_etat_avant_delai(at):
    _lance(at, 30, False)
    at.peindre()


def sc_lance_sans_etat_apres_delai_vivant(at):
    _lance(at, 300, True)
    at.peindre()


def sc_lance_sans_etat_apres_delai_inconnu(at):
    _lance(at, 300, None, journal=False)
    at.peindre()


def sc_lance_sans_instant(at):
    _lance(at, 0, False)
    at.dialogue.instant_lance = None
    at.peindre()


def sc_mort_au_demarrage(at):
    _lance(at, 300, False)
    at.peindre()


def sc_mort_au_demarrage_sans_journal(at):
    _lance(at, 241, False, journal=False)
    at.peindre()


def _vivant(at):
    at.vivants[PID_CALAGE] = True


def sc_en_cours_premier_apport_sans_essai(at):
    _vivant(at)
    s = at.suivi(["A1", "A2", "A3"])
    s.commencer_apport(0)
    at.peindre()


def sc_en_cours_premier_apport_essai_1(at):
    _vivant(at)
    s = at.suivi(["A1", "A2", "A3"], tolerances={"volume": 0.05, "pic": 0.05, "forme": 0.1})
    s.commencer_apport(0)
    at.essai(s, 0, 1.02, 0.96, minutes=-20)
    at.peindre()


def sc_en_cours_milieu_essai_2(at):
    _vivant(at)
    s = at.suivi([f"A{i}" for i in range(1, 6)],
                 tolerances={"volume": 0.02, "pic": 0.03, "forme": 0.05})
    at.caler(s, 0, minutes=-50)
    at.caler(s, 1, minutes=-40)
    s.commencer_apport(2)
    at.essai(s, 2, 0.91, 1.07, minutes=-20)
    at.essai(s, 2, 0.985, 1.012, minutes=-10)
    at.peindre()


def sc_en_cours_dernier_essai_3(at):
    _vivant(at)
    s = at.suivi(["A1", "A2", "A3"])
    at.caler(s, 0, minutes=-50)
    at.caler(s, 1, minutes=-40)
    s.commencer_apport(2)
    for k, (v, p) in enumerate(((0.8, 0.85), (0.93, 1.11), (1.004, 0.999))):
        at.essai(s, 2, v, p, minutes=-30 + 5 * k)
    at.peindre()


def sc_en_cours_repli_sur_dernier_chiffre(at):
    """L'apport en cours n'a rien evalue : les jauges montrent le precedent."""
    _vivant(at)
    s = at.suivi(["A1", "A2", "A3"])
    at.caler(s, 0, minutes=-50)
    s.commencer_apport(1)
    at.peindre()


def sc_statuts_melanges(at):
    """Valide, echoue, en cours, en attente."""
    _vivant(at)
    s = at.suivi(["A1", "A2", "A3", "A4"])
    at.caler(s, 0, minutes=-50)
    s.commencer_apport(1)
    at.essai(s, 1, 0.7, 0.6, minutes=-40)
    s.echouer_apport(1, "A2 ne converge pas", duree_s=600.0)
    s.commencer_apport(2)
    at.essai(s, 2, 0.99, 1.0, minutes=-10)
    at.peindre()


def sc_repris(at):
    """Un calage valide trois apports, un second reprend au troisieme."""
    _vivant(at)
    s = at.suivi(["A1", "A2", "A3", "A4"], minutes=-300)
    at.caler(s, 0, minutes=-290)
    at.caler(s, 1, minutes=-280)
    at.caler(s, 2, minutes=-270)
    s.commencer_apport(3)
    at.essai(s, 3, 0.7, 0.6, minutes=-260)
    s.echouer_apport(3, "arrêt")
    s2 = at.suivi(["A3", "A4"], minutes=-60)
    s2.commencer_apport(0)
    at.essai(s2, 0, 0.97, 1.01, minutes=-30)
    at.peindre()


def sc_repris_sans_essai(at):
    """La reprise n'a encore rien ecrit d'autre que son etat initial."""
    _vivant(at)
    s = at.suivi(["A1", "A2"], minutes=-300)
    at.caler(s, 0, minutes=-290)
    at.caler(s, 1, minutes=-280)
    at.suivi(["A2"], minutes=-5)
    at.peindre()


def sc_repris_archive_illisible(at):
    _vivant(at)
    s = at.suivi(["A1"], minutes=-300)
    at.caler(s, 0, minutes=-290)
    at.suivi(["A1"], minutes=-5)
    (at.dossier / "avancement_precedent.json").write_text("{tronqu", encoding="utf-8")
    at.peindre()


def sc_termine_conforme(at):
    _vivant(at)
    s = at.suivi(["A1", "A2"])
    at.caler(s, 0, minutes=-50)
    at.caler(s, 1, minutes=-30)
    at.a(-1)
    s.conclure(True, nb_calculs=7)
    at.vivants[PID_CALAGE] = False
    at.peindre()


def sc_termine_conforme_un_calcul(at):
    s = at.suivi(["A1"])
    at.caler(s, 0, minutes=-30)
    s.conclure(True, nb_calculs=1)
    at.peindre()


def sc_termine_conforme_sans_nb_calculs(at):
    s = at.suivi(["A1"])
    at.caler(s, 0, minutes=-30)
    s.conclure(True)
    at.peindre()


def sc_termine_non_conforme(at):
    s = at.suivi(["A1", "A2", "A3"])
    at.caler(s, 0, minutes=-50)
    s.commencer_apport(1)
    at.essai(s, 1, 0.7, 0.6, minutes=-40)
    s.echouer_apport(1, "A2 non calé")
    s._consigner("figure d'avancement", RuntimeError("disque plein"))
    s._consigner("tableau", RuntimeError("verrou Excel"))
    s.conclure(False, motif="A2 non calé : volume à 70 % — réserves sur l'aval")
    at.peindre()


def sc_termine_non_conforme_sans_motif(at):
    s = at.suivi(["A1"])
    s.commencer_apport(0)
    s.echouer_apport(0, "")
    s.conclure(False)
    at.peindre()


def sc_interrompu(at):
    s = at.suivi(["A1", "A2"])
    at.caler(s, 0, minutes=-50)
    s.commencer_apport(1)
    at.essai(s, 1, 0.9, 0.9, minutes=-40)
    at.vivants[PID_CALAGE] = False
    at.peindre()


def sc_etat_precedent_perime(at):
    """Etat d'un calage precedent : debut anterieur au lancement."""
    s = at.suivi(["A1", "A2"], minutes=-600)
    at.caler(s, 0, minutes=-590)
    at.caler(s, 1, minutes=-580)
    s.conclure(True, nb_calculs=4)
    at.dialogue.pid_lance = PID_LANCE
    at.dialogue.instant_lance = INSTANT - timedelta(seconds=20)
    at.dialogue.journal_lance = str(Path("calage") / "calage.log")
    at.vivants[PID_LANCE] = True
    at.peindre()


def sc_etat_precedent_perime_et_mort(at):
    s = at.suivi(["A1"], minutes=-600)
    at.caler(s, 0, minutes=-590)
    at.dialogue.pid_lance = PID_LANCE
    at.dialogue.instant_lance = INSTANT - timedelta(seconds=600)
    at.vivants[PID_LANCE] = False
    at.peindre()


def sc_etat_a_nous_a_la_seconde(at):
    """Debut ecrit a la seconde, une seconde avant le lancement : a nous."""
    _vivant(at)
    s = at.suivi(["A1"], minutes=-1)
    s.commencer_apport(0)
    at.dialogue.pid_lance = PID_LANCE
    at.dialogue.instant_lance = INSTANT - timedelta(seconds=59)
    at.peindre()


def sc_debut_illisible(at):
    _vivant(at)
    s = at.suivi(["A1", "A2"])
    s.commencer_apport(0)
    at.retoucher(debut="hier soir")
    at.dialogue.pid_lance = PID_LANCE
    at.dialogue.instant_lance = INSTANT - timedelta(seconds=20)
    at.peindre()


def sc_etat_tronque(at):
    s = at.suivi(["A1", "A2"])
    s.commencer_apport(0)
    brut = (at.dossier / "avancement.json").read_text(encoding="utf-8")
    at.reecrire(brut=brut[:len(brut) // 2])
    at.peindre()


def sc_lectures_successives(at):
    """Lu, verrouille, absent, puis relu : quatre peintures de la meme page."""
    _vivant(at)
    s = at.suivi(["A1", "A2"])
    at.caler(s, 0, minutes=-30)
    s.commencer_apport(1)
    at.peindre()
    chemin = at.dossier / "avancement.json"
    sauve = chemin.read_text(encoding="utf-8")
    chemin.unlink()
    chemin.mkdir()           # illisible : read_text leve une OSError
    at.peindre(minutes=1)
    chemin.rmdir()           # absent
    at.peindre(minutes=2)
    chemin.write_text(sauve, encoding="utf-8")
    at.peindre(minutes=3)


def sc_bilan_masse_dans_le_seuil(at):
    _vivant(at)
    s = at.suivi(["A1", "A2"])
    s.commencer_apport(0)
    at.essai(s, 0, 1.0, 1.0)
    s.noter_bilan_masse(0.0123, 0.5)
    at.peindre()


def sc_bilan_masse_depasse(at):
    _vivant(at)
    s = at.suivi(["A1"])
    s.commencer_apport(0)
    s.noter_bilan_masse(-1.25, 0.5)
    at.peindre()


def sc_bilan_masse_malforme(at):
    _vivant(at)
    s = at.suivi(["A1"])
    s.commencer_apport(0)
    at.retoucher(bilan_masse={"pct": "n/a", "seuil_pct": 1})
    at.peindre()


def sc_noms_accentues(at):
    _vivant(at)
    s = at.suivi(["Apport_Église", "Ruisseau d'Œ", "Bièvre amont"],
                 ["Pont-l'Évêque", "Confluence Saône", "Aval à Écully"])
    at.caler(s, 0, minutes=-40)
    s.commencer_apport(1)
    at.essai(s, 1, 1.03, 0.95, minutes=-10)
    at.desaccord = ("<br>L'étape Paramètres en désigne un autre — <i>D:/Études/"
                    "suivi</i> — qui n'est pas surveillé.")
    at.peindre()


def sc_un_apport(at):
    _vivant(at)
    s = at.suivi(["Unique"])
    s.commencer_apport(0)
    at.essai(s, 0, 0.99, 1.0, decalage=1.5)
    at.peindre()


def sc_douze_apports(at):
    _vivant(at)
    s = at.suivi([f"Apport_{i:02d}" for i in range(1, 13)])
    for i in range(7):
        at.caler(s, i, minutes=-120 + 10 * i)
    s.commencer_apport(7)
    s.echouer_apport(7, "non convergé")
    s.commencer_apport(8)
    at.essai(s, 8, 1.01, 0.99, decalage=-0.75)
    at.peindre()


def sc_trente_apports(at):
    _vivant(at)
    s = at.suivi([f"Affluent_{i:02d}" for i in range(1, 31)])
    for i in range(18):
        at.caler(s, i, minutes=-300 + 10 * i)
    s.commencer_apport(18)
    at.essai(s, 18, 0.98, 1.02)
    at.peindre()


def sc_cibles_manquantes(at):
    _vivant(at)
    s = at.suivi(["A1", "A2"])
    s.commencer_apport(0)
    at.essai(s, 0, 1.0, 1.0)
    etat = at.etat()
    etat["courbes"]["temps_cible"] = []
    etat["courbes"]["debit_cible"] = []
    at.reecrire(etat)
    at.peindre()


def sc_sans_courbes_avec_chiffres(at):
    _vivant(at)
    s = at.suivi(["A1", "A2"])
    s.commencer_apport(0)
    at.essai(s, 0, 1.01, 0.99, series=False)
    at.peindre()


def sc_etat_minimal(at):
    """Etat d'une version anterieure : cles absentes ou nulles."""
    _vivant(at)
    at.dossier.mkdir(parents=True)
    at.reecrire({"pid": PID_CALAGE, "en_cours": 3, "total": 2,
                 "apports": [{"apport": "A1", "section": "S1", "statut": "validé",
                              "essais": 2, "ordre": 1, "volume_pct": 100.2,
                              "pic_pct": None}],
                 "fraction": None, "comptes": None, "tolerances_pct": None})
    at.peindre()


def sc_en_cours_sans_apport_actif(at):
    """Etat initial : rien n'est en cours, rien n'est fini."""
    _vivant(at)
    at.suivi(["A1", "A2", "A3"], tolerances={"volume": 0.01})
    at.peindre()


def sc_tableau_trie(at):
    """Un tri demande par l'utilisateur survit a la peinture."""
    _vivant(at)
    s = at.suivi(["A1", "A2", "A3", "A4"])
    at.caler(s, 0, minutes=-50)
    s.commencer_apport(1)
    at.essai(s, 1, 0.9, 1.1, minutes=-40)
    s.echouer_apport(1, "x")
    at.caler(s, 2, minutes=-30)
    at.page.table_suivi.horizontalHeader().sectionDoubleClicked.emit(4)
    at.peindre()
    at.page.table_suivi.horizontalHeader().sectionDoubleClicked.emit(4)
    at.peindre(minutes=1)


SCENARIOS_PAGE = {nom[3:]: f for nom, f in sorted(globals().items())
                  if nom.startswith("sc_")}
# Theme sombre et police a 13 pt, sur les scenarios qui peignent le plus.
VARIANTES = [("sombre", 9), ("clair", 13), ("sombre", 13)]
SCENARIOS_VARIANTES = ["en_cours_milieu_essai_2", "termine_non_conforme",
                       "mort_au_demarrage", "repris", "aucun_dossier",
                       "termine_conforme", "bilan_masse_depasse"]


# ---------------------------------------------------------------------------
# Scenarios de CourbeComparaison.paintEvent, seule
# ---------------------------------------------------------------------------

def _serie(n=60, pic=50.0, debut=0.0, fin=24.0, base=0.0, dt=0.0):
    pas = (fin - debut) / max(n - 1, 1)
    temps = [round(debut + k * pas, 3) for k in range(n)]
    import math
    debits = [round(base + pic * math.exp(-((t - 8.0 - dt) / 2.0) ** 2), 3)
              for t in temps]
    return temps, debits


def _courbes(decalage=0.0, **k):
    tc, qc = _serie(**k)
    ts, qs = _serie(dt=0.4, **k)
    return {"temps_cible": tc, "debit_cible": qc, "temps_calcule": ts,
            "debit_calcule": qs, "decalage_h": decalage, "apport": "A",
            "section": "S", "statut": "en cours"}


def _precedente(nom, pic, anterieur=False, n=40):
    t, q = _serie(n=n, pic=pic)
    c = {"apport": nom, "section": f"S_{nom}", "temps": t, "debit": q}
    if anterieur:
        c["anterieur"] = True
    return c


NAN = float("nan")
SCENARIOS_COURBE = {
    "attente": (None, None, (640, 220)),
    "series_vides": ({"temps_cible": [], "debit_cible": [], "temps_calcule": [],
                      "debit_calcule": []}, None, (640, 220)),
    "une_seule_serie": (dict(_courbes(), temps_calcule=[], debit_calcule=[]),
                        None, (640, 220)),
    "cible_un_point": (dict(_courbes(), temps_cible=[1.0], debit_cible=[3.0]),
                       None, (640, 220)),
    "fenetre_de_crue": (_courbes(), None, (640, 220)),
    "sans_fenetre_de_crue": (_courbes(base=20.0), None, (640, 220)),
    "decalage_positif": (_courbes(decalage=1.5), None, (640, 220)),
    "decalage_negatif": (_courbes(decalage=-0.75), None, (640, 220)),
    "decalage_sous_le_seuil": (_courbes(decalage=0.004), None, (640, 220)),
    "une_section_calee": (_courbes(), [_precedente("P1", 30.0)], (640, 220)),
    "sections_calees_et_anterieures": (
        _courbes(decalage=2.25),
        [_precedente("P1", 30.0), _precedente("P2", 70.0),
         _precedente("R1", 20.0, anterieur=True), _precedente("R2", 90.0, anterieur=True),
         _precedente("X", 10.0, n=1), {"apport": "Y", "temps": [], "debit": []}],
        (640, 220)),
    "anterieures_seules": (_courbes(), [_precedente("R1", 20.0, anterieur=True)],
                           (640, 220)),
    "legende_a_la_ligne": (
        _courbes(decalage=-3.5),
        [_precedente("P1", 30.0), _precedente("R1", 20.0, anterieur=True)],
        (260, 220)),
    "debits_nuls": (dict(_courbes(), debit_cible=[0.0] * 60, debit_calcule=[0.0] * 60),
                    None, (640, 220)),
    "valeurs_nan": (dict(_courbes(), debit_calcule=[NAN] + _courbes()["debit_calcule"][1:]),
                    None, (640, 220)),
    "tres_grands_debits": (_courbes(pic=2.5e6), [_precedente("P1", 3.1e6)], (640, 220)),
    "widget_minuscule": (_courbes(), [_precedente("P1", 30.0)], (40, 30)),
    "widget_tres_large": (_courbes(), [_precedente("P1", 30.0)], (3000, 200)),
}


def peindre_courbe(courbes, precedentes, taille):
    from calage_apports.widgets import CourbeComparaison
    w = CourbeComparaison()
    w.setStyleSheet(_feuille(QApplication.font().pointSizeF()))
    w.actualiser(copy.deepcopy(courbes), copy.deepcopy(precedentes))
    w.setMinimumSize(0, 0)
    try:
        ordres, complet, image = _peindre(w, taille)
        erreur = None
    except Exception as e:                                  # noqa: BLE001
        ordres, complet, image, erreur = [], [], None, f"{type(e).__name__}: {e}"
    portable = _json({"description_accessible": w.accessibleDescription(),
                      "ordres": _resumer(ordres), "erreur": erreur})
    poste = {"ordres": _empreinte(complet),
             "image": _empreinte_image(image) if image is not None else None}
    w.deleteLater()
    return portable, poste


# ---------------------------------------------------------------------------
# Execution d'un scenario
# ---------------------------------------------------------------------------

@pytest.fixture()
def banc(qgis_app, monkeypatch, tmp_path_factory):
    """Rend jouer(nom, theme, points) -> liste de releves (portable, poste)."""
    import suivi as module_suivi
    from calage_apports import noyau, page_suivi, widgets
    monkeypatch.setattr(page_suivi, "datetime", Horloge)
    monkeypatch.setattr(module_suivi, "datetime", Horloge)
    monkeypatch.setattr(widgets, "QPainter", PeintreTrace)
    monkeypatch.setattr(os, "getpid", lambda: PID_CALAGE)

    def jouer_page(nom, theme="clair", points=9):
        atelier_courant = {}

        def vivant(pid):
            at = atelier_courant["at"]
            at.appels_vivant.append(pid)
            return at.vivants.get(pid)

        monkeypatch.setattr(noyau, "processus_vivant", vivant)
        monkeypatch.chdir(tmp_path_factory.mktemp("scenario"))
        _appliquer_poste(theme, points)
        Horloge.instant = INSTANT
        dialogue = DialogueFactice(None)
        page = page_suivi.PageSuivi(dialogue)
        page.setStyleSheet(_feuille(points))
        page.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        page.resize(*TAILLE_PAGE)
        page.show()
        at = Atelier(page, dialogue)
        dialogue._atelier = at
        atelier_courant["at"] = at
        try:
            SCENARIOS_PAGE[nom](at)
        finally:
            page.hide()
            page.deleteLater()
            QApplication.processEvents()
        return at.releves

    def jouer_courbe(nom, theme="clair", points=9):
        _appliquer_poste(theme, points)
        courbes, precedentes, taille = SCENARIOS_COURBE[nom]
        return [peindre_courbe(courbes, precedentes, taille)]

    def page_neuve(theme, points):
        _appliquer_poste(theme, points)
        page = page_suivi.PageSuivi(DialogueFactice(None))
        page.setStyleSheet(_feuille(points))
        rendu = _json(widgets_portables(page))
        page.deleteLater()
        QApplication.processEvents()
        return rendu

    return SimpleNamespace(page=jouer_page, courbe=jouer_courbe, neuve=page_neuve)


def _cles():
    cles = [("page", nom, "clair", 9) for nom in SCENARIOS_PAGE]
    cles += [("page", nom, theme, pts) for nom in SCENARIOS_VARIANTES
             for theme, pts in VARIANTES]
    cles += [("courbe", nom, "clair", 9) for nom in SCENARIOS_COURBE]
    cles += [("courbe", nom, theme, pts)
             for nom in ("sections_calees_et_anterieures", "legende_a_la_ligne")
             for theme, pts in VARIANTES]
    return cles


def _id(cle):
    return f"{cle[0]}:{cle[1]}:{cle[2]}:{cle[3]}pt"


# ---------------------------------------------------------------------------
# Reference
# ---------------------------------------------------------------------------

_ETAT = {"reference": None, "nouvelle": {}, "neuves": {}, "repli_annonce": False}
POSTES = [("clair", 9)] + VARIANTES


def _reference():
    if _ETAT["reference"] is None:
        if REFERENCE.is_file():
            _ETAT["reference"] = json.loads(REFERENCE.read_text(encoding="utf-8"))
        else:
            _ETAT["reference"] = {"poste": None, "scenarios": {}}
    return _ETAT["reference"]


def _diff(attendu, obtenu):
    a = json.dumps(attendu, indent=1, sort_keys=True, ensure_ascii=False).splitlines()
    b = json.dumps(obtenu, indent=1, sort_keys=True, ensure_ascii=False).splitlines()
    return "\n".join(list(difflib.unified_diff(a, b, "reference", "obtenu",
                                               lineterm="", n=2))[:80])


def _canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


@pytest.mark.parametrize("cle", _cles(), ids=_id)
def test_peinture_figee(banc, cle):
    genre, nom, theme, points = cle
    jouer = banc.page if genre == "page" else banc.courbe
    premier = jouer(nom, theme, points)
    second = jouer(nom, theme, points)
    # STABILITE DANS LE PROCESSUS : deux montages neufs, meme trace.
    assert _canon(premier) == _canon(second), (
        "Deux peintures du meme scenario different :\n"
        + _diff([p for p, _ in premier], [p for p, _ in second]))
    identifiant = _id(cle)
    portable = [p for p, _ in premier]
    poste = [q for _, q in premier]
    if REGENERER:
        _ETAT["nouvelle"][identifiant] = {"portable": portable, "poste": poste}
        return
    reference = _reference()
    assert identifiant in reference["scenarios"], (
        f"{identifiant} absent de la reference : PEINTURE_SUIVI_REGENERER=1 "
        "sur le code sain.")
    attendu = reference["scenarios"][identifiant]
    assert _canon(portable) == _canon(attendu["portable"]), (
        f"{identifiant} : la peinture a change.\n" + _diff(attendu["portable"], portable))
    if reference["poste"] == signature_poste():
        assert _canon(poste) == _canon(attendu["poste"]), (
            f"{identifiant} : images ou geometrie changees sur le poste de "
            "reference.\n" + _diff(attendu["poste"], poste))
    else:
        if not _ETAT["repli_annonce"]:
            _ETAT["repli_annonce"] = True
            warnings.warn(
                "Poste different de celui de la reference (police, Qt ou rendu) : "
                "images et geometrie NON comparees ; textes, donnees et ordres de "
                f"peinture compares. Poste : {json.dumps(signature_poste())}",
                stacklevel=1)


@pytest.mark.parametrize("theme,points", POSTES)
def test_page_neuve(banc, theme, points):
    """La page avant toute peinture : la base des releves par difference."""
    neuve = banc.neuve(theme, points)
    cle = f"{theme}:{points}pt"
    if REGENERER:
        _ETAT["neuves"][cle] = neuve
        return
    attendu = _reference()["pages_neuves"][cle]
    assert _canon(neuve) == _canon(attendu), _diff(attendu, neuve)


def test_ecrire_reference(qgis_app):
    """Dernier test : ecrit la reference si on la regenere."""
    if not REGENERER:
        pytest.skip("reference non regeneree (PEINTURE_SUIVI_REGENERER=1)")
    attendus = {_id(c) for c in _cles()}
    assert set(_ETAT["nouvelle"]) == attendus, "regenerer la reference ENTIERE"
    assert len(_ETAT["neuves"]) == len(POSTES)
    REFERENCE.write_text(json.dumps(
        {"poste": signature_poste(),
         "pages_neuves": _ETAT["neuves"],
         "scenarios": {k: _ETAT["nouvelle"][k] for k in sorted(_ETAT["nouvelle"])}},
        ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
