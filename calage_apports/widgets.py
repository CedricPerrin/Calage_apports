"""
Widgets peints de la fenêtre du plugin, et le vocabulaire qu'ils partagent avec elle.

Sortis de plugin.py le 10/11/2026 (docs/decoupage_dialogue.md), code déplacé à
l'identique. CourbeComparaison reste dans plugin.py : test_plugin_qgis.py relit
dans le TEXTE de plugin.py la fenêtre de crue qu'elle emploie (_fenetre_crue,
SEUIL_CRUE, MARGE_CRUE_H), pour la comparer à celle de livrables.py.

Ce module n'importe pas plugin.py : c'est plugin.py qui l'importe, et qui
ré-exporte ce que le banc y lit par son nom.
"""

from qgis.PyQt.QtCore import QEvent, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from qgis.PyQt.QtWidgets import QApplication, QProgressBar, QSizePolicy, QWidget

from . import registre


# UN CINQUIEME STATUT, QUI NE VIENT PAS DE LA CHAINE : « repris » designe
# un apport que le calage PRECEDENT a cale et que celui-ci ne refait pas.
# Il est pose par l'affichage (_suivi_precedent) a partir du suivi
# archive ; suivi.py ne connait que les quatre autres.
STATUT_REPRIS = "repris"

# LA COULEUR NE PORTE JAMAIS SEULE LE SENS. Une part notable de la population
# distingue mal le rouge du vert ; un statut lisible uniquement a sa teinte
# est illisible pour elle. Chaque etat porte donc AUSSI un glyphe, et les
# quatre teintes different par la clarte autant que par la teinte.
GLYPHE_STATUT = {
    "validé": "✔",
    "en cours": "▶",
    "échoué": "✕",
    "en attente": "·",
    # MEME GLYPHE QUE « validé », ET C'EST VOULU : ces apports SONT cales.
    # Ce qui les distingue est le calage auquel ils appartiennent, et
    # c'est la teinte qui le porte — vert pour celui-ci, ardoise pour
    # celui d'avant. Inventer un sixieme signe pour « cale ailleurs »
    # demanderait de l'apprendre.
    STATUT_REPRIS: "✔",
}


def _taille_police(widget, facteur):
    """
    Taille de police, en points, d'un texte dessine au QPainter.

    LES WIDGETS PEINTS SUIVENT LA POLICE DU POSTE COMME LE RESTE DE LA
    FENETRE (0.8.5). Ils ecrivaient 7,5, 8 et 11 pt en dur : a 13 pt — le cas
    du banc — ou sous le reglage Windows « Taille du texte », tout le
    formulaire grandissait et eux restaient a 7,5 pt. La taille est donc une
    FRACTION de celle du widget, que la feuille de style pose sur tout
    QWidget. Repli sur la police de l'application, puis sur 10 pt, si la
    police est exprimee en pixels (pointSizeF() rend alors -1).
    """
    base = widget.font().pointSizeF()
    if base <= 0:
        base = QApplication.font().pointSizeF()
    if base <= 0:
        base = 10.0
    return base * facteur


# LES TROIS GRAPHIQUES DU SUIVI SE DESSINENT SUR LA CARTE DU REGISTRE COMMUN
# (23/10/2026, esthetique commune des extensions ISL : « Teintes ISL
# nuancees », registre.py en copie identique de celui de Rhoe). Carte blanche
# a bordure grise fine et coins de 6 px, encre foncee, DANS LES DEUX THEMES,
# comme les graphiques de Rhoe et de Hyetos : le remappage sombre de la 0.8.5
# (C1) ne vaut plus pour l'interieur des graphiques. Il vaut toujours pour le
# reste de la fenetre — tableau, bannieres, textes — que le registre ne
# colore jamais.
#   LE REGISTRE N'A NI VERT NI ROUGE. Une teinte par statut, prise chez lui :
# l'accent pour ce que CE calage a cale (et pour l'apport en cours, que son
# trait souligne), l'ocre d'alerte pour l'echec, le neutre fonce pour ce qui
# attend et pour ce que le calage PRECEDENT avait cale. Le glyphe, le
# remplissage et le trait portent le sens ; la teinte le confirme.
TEINTE_STATUT = {
    "validé": registre.ACCENT,
    "en cours": registre.ACCENT,
    "échoué": registre.ALERTE,
    "en attente": registre.NEUTRE_FONCE,
    STATUT_REPRIS: registre.NEUTRE_FONCE,
}
# OPACITE DU FOND D'UN SEGMENT ACHEVE : une teinte claire sous une encre
# foncee. Blanc sur l'accent plein ne rendait que 3,9:1, sous les 4,5:1 d'un
# texte de 7,5 pt ; l'encre sur ces fonds clairs depasse 7:1. L'apport en
# cours, plus soutenu, se trouve d'un coup d'oeil.
OPACITE_SEGMENT = {"en cours": 150}
OPACITE_SEGMENT_DEFAUT = 80

# Marge interieure de la carte, en hauteurs de ligne de la police du widget.
MARGE_CARTE = 0.45


def _carte(widget):
    """
    Peintre d'un graphique sur sa carte claire (fond, bordure et coins du
    registre), quel que soit le theme de l'hote ; rend aussi la zone de
    dessin, marges otees.
    """
    peintre = QPainter(widget)
    peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
    peintre.setPen(QPen(QColor(registre.BORDURE), 1))
    peintre.setBrush(QColor(registre.FOND))
    peintre.drawRoundedRect(QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                            registre.RAYON_PX, registre.RAYON_PX)
    marge = _marge_carte(widget)
    return peintre, QRectF(marge, marge, widget.width() - 2 * marge,
                           widget.height() - 2 * marge)


def _marge_carte(widget):
    return round(MARGE_CARTE * widget.fontMetrics().lineSpacing())


def compte(nombre, singulier, pluriel=None):
    """« 1 section », « 3 sections » : le nombre et son nom accordes."""
    return f"{nombre} {singulier if nombre < 2 else pluriel or singulier + 's'}"


def nombre(valeur, decimales=1, signe=False, milliers=False):
    """« 99,9 », « +0,35 », « 1 234,5 » : la virgule de l'interface, et
    l'espace fine insecable des milliers. Pour l'ecran seulement : les
    fichiers (Excel, JSON, HEC-RAS) gardent le point."""
    texte = format(valeur, f"{'+' if signe else ''}{',' if milliers else ''}.{decimales}f")
    return texte.replace(",", "\u202f").replace(".", ",")


class RubanApports(QWidget):
    """
    Une bande de segments, un par apport, teintee selon son statut.

    C'est la vue d'ensemble : sur douze apports, savoir en un coup d'oeil que
    huit sont valides, un en cours et trois en attente vaut mieux que douze
    lignes de texte. L'apport en cours est souligne d'un trait epais.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.apports = []
        self.en_cours = None
        self._ajuster_hauteur()
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        # CE QUE LE LECTEUR D'ECRAN DIT D'UN WIDGET PEINT (0.8.5) : sans nom,
        # Qt l'expose a UI Automation comme un objet muet. Le detail suit
        # chaque actualisation, dans la description.
        self.setAccessibleName("Avancement par apport")
        self.setAccessibleDescription("aucun calage suivi")

    def _ajuster_hauteur(self):
        # Deux lignes de la police du widget — le segment, puis son trait —,
        # leurs marges, et celles de la carte.
        self.setMinimumHeight(2 * self.fontMetrics().height() + 14
                              + 2 * _marge_carte(self))

    def changeEvent(self, evenement):                       # noqa: N802
        super().changeEvent(evenement)
        if evenement.type() == QEvent.Type.FontChange:
            self._ajuster_hauteur()

    def actualiser(self, apports, en_cours):
        self.apports = apports or []
        self.en_cours = en_cours
        comptes = {}
        for apport in self.apports:
            statut = apport.get("statut") or "sans statut"
            comptes[statut] = comptes.get(statut, 0) + 1
        self.setAccessibleDescription(
            "aucun calage suivi" if not self.apports else
            compte(len(self.apports), "apport") + " : "
            + ", ".join(f"{n} {statut}" for statut, n in comptes.items()))
        self.update()

    def paintEvent(self, evenement):                        # noqa: N802
        peintre, zone = _carte(self)
        if not self.apports:
            peintre.setPen(QColor(registre.TEXTE_SECONDAIRE))
            peintre.drawText(zone, Qt.AlignmentFlag.AlignCenter,
                             "aucun calage suivi")
            peintre.end()
            return

        n = len(self.apports)
        ecart = 3
        largeur = (zone.width() - ecart * (n - 1)) / n
        hauteur = zone.height() - 8
        police = peintre.font()
        police.setPointSizeF(_taille_police(self, 0.75))
        police.setBold(True)
        peintre.setFont(police)
        for i, apport in enumerate(self.apports):
            statut = apport.get("statut")
            segment = QRectF(zone.left() + i * (largeur + ecart), zone.top(),
                             largeur, hauteur)
            teinte = QColor(TEINTE_STATUT.get(statut, registre.NEUTRE_FONCE))
            # CE QUI EST FAIT est teinte ; CE QUI RESTE est un simple contour.
            # La difference se voit sans distinguer les teintes — c'est le
            # remplissage qui porte l'information, la couleur ne fait que la
            # confirmer.
            acheve = statut in ("validé", "échoué", "en cours",
                                STATUT_REPRIS)
            if acheve:
                fond = QColor(teinte)
                fond.setAlpha(OPACITE_SEGMENT.get(statut, OPACITE_SEGMENT_DEFAUT))
                peintre.setBrush(fond)
            else:
                peintre.setBrush(Qt.BrushStyle.NoBrush)
            peintre.setPen(QPen(teinte, 1.5))
            peintre.drawRoundedRect(segment.adjusted(0.75, 0.75, -0.75, -0.75),
                                    3, 3)
            # Le segment en cours porte un trait epais : c'est celui qu'on
            # cherche des yeux en revenant voir le calcul.
            if i == self.en_cours:
                peintre.setPen(Qt.PenStyle.NoPen)
                peintre.setBrush(QColor(registre.ACCENT))
                peintre.drawRoundedRect(
                    QRectF(segment.left(), segment.bottom() + 3, largeur, 4), 2, 2)
            if largeur > 30:
                peintre.setPen(QColor(registre.ENCRE if acheve
                                      else registre.TEXTE_SECONDAIRE))
                peintre.drawText(
                    segment, Qt.AlignmentFlag.AlignCenter,
                    f"{GLYPHE_STATUT.get(statut, '')} "
                    f"{str(apport.get('apport', ''))[:8]}")
        peintre.end()


class JaugeAtteinte(QWidget):
    """
    Barre d'atteinte d'une grandeur, en pourcentage de la cible.

    Le repere des 100 % est TRACE, et la barre part de la : un calage a 103 %
    et un calage a 97 % sont deux depassements de meme ampleur, et une barre
    partant de zero les rendrait incomparables. La tolerance est figuree par
    une zone claire — dedans, c'est conforme.
    """

    def __init__(self, libelle, tolerance_pct=2.0, parent=None):
        super().__init__(parent)
        self.libelle = libelle
        self.tolerance = tolerance_pct
        self.valeur = None
        # La hauteur suit les deux polices de la jauge (0.8.5). Elle etait
        # ecrite « 56 px, mesures a l'ecran » : en dessous, le libelle et la
        # valeur sont rognes a mi-hauteur par le remplissage du QGroupBox —
        # et a 13 pt, 56 px ne suffisaient plus.
        self._ajuster_hauteur()
        self.setAccessibleName(f"Atteinte de la cible — {libelle}")
        self.setAccessibleDescription(f"{libelle} : pas encore évalué")

    def _metriques(self):
        """(h_libelle, h_valeur, haut de la piste, h_piste), derives des polices."""
        petite, grande = QFont(self.font()), QFont(self.font())
        petite.setPointSizeF(_taille_police(self, 0.8))
        grande.setPointSizeF(_taille_police(self, 1.1))
        grande.setBold(True)
        h_libelle = QFontMetrics(petite).height()
        h_valeur = QFontMetrics(grande).height()
        haut_piste = 2 + h_libelle + h_valeur + 6
        return h_libelle, h_valeur, haut_piste, max(12, round(0.75 * h_libelle))

    def _ajuster_hauteur(self):
        _, _, haut_piste, h_piste = self._metriques()
        self.setMinimumHeight(haut_piste + h_piste + 4 + 2 * _marge_carte(self))

    def changeEvent(self, evenement):                       # noqa: N802
        super().changeEvent(evenement)
        if evenement.type() == QEvent.Type.FontChange:
            self._ajuster_hauteur()

    def lecture(self):
        """(texte affiche, conforme) — conforme vaut None tant que rien n'est evalue."""
        if self.valeur is None:
            return "—", None
        return f"{nombre(self.valeur)} %", abs(self.valeur - 100.0) <= self.tolerance

    def actualiser(self, valeur_pct):
        self.valeur = valeur_pct
        texte, conforme = self.lecture()
        self.setAccessibleDescription(
            f"{self.libelle} : pas encore évalué" if conforme is None else
            f"{self.libelle} : {texte}, "
            + ("conforme" if conforme else "hors tolérance"))
        self.update()

    def paintEvent(self, evenement):                        # noqa: N802
        peintre, zone = _carte(self)
        peintre.translate(zone.topLeft())
        largeur = round(zone.width())
        h_libelle, h_valeur, haut, hauteur = self._metriques()
        police = peintre.font()
        police.setPointSizeF(_taille_police(self, 0.8))
        peintre.setFont(police)

        peintre.setPen(QColor(registre.TEXTE_SECONDAIRE))
        peintre.drawText(0, 2, largeur, h_libelle,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.libelle)
        texte, conforme = self.lecture()
        police.setBold(True)
        police.setPointSizeF(_taille_police(self, 1.1))
        peintre.setFont(police)
        # LE VERDICT NE TIENT PAS A LA SEULE COULEUR : « ✔ » dans la
        # tolerance, « ⚠ » au-dela, a l'encre ou a l'ocre d'alerte du registre.
        if conforme is None:
            peintre.setPen(QColor(registre.TEXTE_SECONDAIRE))
        else:
            peintre.setPen(QColor(registre.ENCRE if conforme else registre.ALERTE))
            texte = f"{'✔' if conforme else '⚠'} {texte}"
        peintre.drawText(0, 2 + h_libelle, largeur, h_valeur,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, texte)

        # Piste : +/- 10 % autour de la cible, ce qui cadre l'ecart utile.
        # Elle doit se VOIR : sans elle, on ne lit qu'un trait sans savoir sur
        # quelle etendue il se situe. (Elle ne s'est longtemps pas vue du tout :
        # QColor lit « #AARRGGBB », pas « #RRGGBBAA » — l'alpha se pose par
        # setAlpha(), jamais par concatenation ; trouve le 08/09/2026.)
        etendue = 10.0
        peintre.setPen(Qt.PenStyle.NoPen)
        peintre.setBrush(QColor(registre.GRILLE))
        peintre.drawRoundedRect(0, haut, largeur, hauteur, 3, 3)
        centre = largeur / 2.0

        demi = self.tolerance / etendue * (largeur / 2.0)
        bande = QColor(registre.ACCENT)
        bande.setAlpha(70)
        peintre.setBrush(bande)
        peintre.drawRect(int(centre - demi), haut, int(2 * demi), hauteur)

        if self.valeur is not None:
            ecart = max(-etendue, min(etendue, self.valeur - 100.0))
            barre = ecart / etendue * (largeur / 2.0)
            peintre.setBrush(QColor(registre.ACCENT if conforme else registre.ALERTE))
            x = centre if barre >= 0 else centre + barre
            peintre.drawRoundedRect(int(x), haut + 2, max(int(abs(barre)), 2),
                                    hauteur - 4, 2, 2)
        peintre.setPen(QColor(registre.NEUTRE_FONCE))
        peintre.drawLine(int(centre), haut - 2, int(centre), haut + hauteur + 2)
        peintre.end()


class BarreTexte(QProgressBar):
    """
    Barre de progression toujours assez large pour son texte.

    La largeur que Qt propose a une QProgressBar ne tient pas compte de son
    texte : a 13 pt, « Préparation 1/4 » se lisait « réparation 1/ » au bas
    de la fenetre (23/10/2026). La largeur suit donc le texte le plus long
    que la barre peut ecrire, dans sa police du moment.
    """

    def sizeHint(self):                                     # noqa: N802
        taille = super().sizeHint()
        plein = str(self.maximum())
        texte = self.format().replace("%v", plein).replace("%m", plein)
        metriques = self.fontMetrics()
        taille.setWidth(max(taille.width(), metriques.horizontalAdvance(texte)
                            + 4 * metriques.averageCharWidth()))
        return taille

    minimumSizeHint = sizeHint
