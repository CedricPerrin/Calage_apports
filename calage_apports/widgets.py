"""
Widgets peints de la fenêtre du plugin, et le vocabulaire qu'ils partagent avec elle.

Sortis de plugin.py le 10/11/2026 (docs/decoupage_dialogue.md), code déplacé à
l'identique. CourbeComparaison et sa fenêtre de crue (_fenetre_crue, SEUIL_CRUE,
MARGE_CRUE_H) les ont rejoints en phase 2 : test_plugin_qgis.py compare cette
fenêtre à celle de livrables.py dans le fichier qui définit _fenetre_crue.

Ce module n'importe pas plugin.py : c'est plugin.py qui l'importe, et qui
ré-exporte ce que le banc y lit par son nom.
"""

from qgis.PyQt.QtCore import QEvent, QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
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


# Fenetre de crue : bornes hors desquelles il ne se passe rien d'interessant.
#
# LA REGLE EXISTE EN DEUX EXEMPLAIRES, ET C'EST ASSUME. Le plugin la traite
# dans un paintEvent rafraichi toutes les deux secondes ; livrables.py la
# traite sur des tableaux numpy, pour une figure matplotlib. Fusionner les
# deux ferait entrer matplotlib — et la chaine entiere — dans le fil
# graphique de QGIS, pour cadrer un trace de deux courbes.
#
# CE QUI EST INTERDIT, C'EST QU'ELLES DIVERGENT. Les deux valeurs sont donc
# NOMMEES des deux cotes, et test_plugin_qgis.py verifie qu'elles sont
# egales : le jour ou l'une bouge, le banc le dit, au lieu de laisser la
# courbe du suivi et la figure du livrable cadrer deux fenetres differentes
# sans que rien ne le signale.
SEUIL_CRUE = 0.02      # fraction du debit de pointe sous laquelle on coupe
MARGE_CRUE_H = 0.5     # heures conservees de part et d'autre


def _fenetre_crue(tc, qc, ts, qs, q_max, seuil=SEUIL_CRUE,
                  marge_h=MARGE_CRUE_H):
    """
    Bornes temporelles ou la crue est effectivement significative.

    L'hydrogramme saisi peut couvrir 24 h alors que la crue elle-meme ne
    dure que quelques heures : le trace ne doit pas s'etendre au-dela de ce
    qui se passe reellement, sous peine d'ecraser la courbe contre l'axe.
    Seuil relatif au pic (2 %) plutot qu'un debit de base absolu, pour
    marcher aussi bien sur un petit affluent que sur un cours d'eau majeur.
    """
    borne_totale = (min(min(tc), min(ts)), max(max(tc), max(ts)))
    seuil_q = seuil * q_max
    instants = [t for t, q in zip(tc, qc) if q >= seuil_q]
    instants += [t for t, q in zip(ts, qs) if q >= seuil_q]
    if not instants:
        return borne_totale
    t_debut = max(min(instants) - marge_h, borne_totale[0])
    t_fin = min(max(instants) + marge_h, borne_totale[1])
    return t_debut, t_fin


class CourbeComparaison(QWidget):
    """
    Hydrogramme CIBLE et hydrogramme MESURE a la section, du dernier essai.

    Les trois jauges disent DE COMBIEN on s'ecarte ; elles ne disent pas OU.
    Un volume a 103 % avec une pointe a 94 % peut venir d'un pic trop bas ou
    d'une decrue trop longue — ce sont deux diagnostics opposes, et seule la
    courbe les distingue. C'est aussi ce qui permet de voir, sans attendre la
    fin, qu'un apport part de travers.

    LA CIBLE TRACEE EST LA CIBLE DECALEE DE -Δt, celle que la methode compare
    a la section et que le classeur d'iterations consigne (suivi.py la publie
    ainsi). Tracee brute, elle apparaissait translatee de Δt — 3,8 h sur le
    premier apport d'un calage reel — juste sous trois jauges affichant
    99,9 %, et l'oeil concluait a un calage faux la ou il etait juste. La
    legende NOMME le
    decalage : le taire reviendrait a laisser croire que les deux courbes sont
    sur la meme origine des temps.
    """

    _TEXTE_ATTENTE = "La comparaison apparaît après le premier essai évalué."

    def __init__(self, parent=None):
        super().__init__(parent)
        self.courbes = None
        self.precedentes = []
        self._ajuster_hauteur()
        self.setAccessibleName("Cible et débit calculé à la section")
        self.setAccessibleDescription(self._TEXTE_ATTENTE)

    def _ajuster_hauteur(self):
        # 190 px a 10 pt — la valeur qui etait ecrite en dur —, davantage
        # quand la police grandit ; 16 px est la hauteur de ligne de la
        # police de reference.
        self.setMinimumHeight(
            max(190, round(190 * self.fontMetrics().height() / 16)))

    def changeEvent(self, evenement):                       # noqa: N802
        super().changeEvent(evenement)
        if evenement.type() == QEvent.Type.FontChange:
            self._ajuster_hauteur()

    def actualiser(self, courbes, precedentes=None):
        self.courbes = courbes or None
        self.precedentes = list(precedentes or [])
        if not self.courbes:
            description = self._TEXTE_ATTENTE
        else:
            decalage = float(self.courbes.get("decalage_h") or 0.0)
            deja = sum(1 for c in self.precedentes
                       if len(c.get("debit") or []) > 1)
            description = (
                "Cible et débit calculé au dernier essai évalué"
                + (f", cible décalée de {nombre(decalage, 2, signe=True)} h"
                   if abs(decalage) >= 0.005 else "")
                + (f", {compte(deja, 'section calée', 'sections calées')} derrière"
                   if deja else ""))
        self.setAccessibleDescription(description)
        self.update()

    def paintEvent(self, evenement):                        # noqa: N802
        peintre, zone = _carte(self)
        police = peintre.font()
        police.setPointSizeF(_taille_police(self, 0.75))
        peintre.setFont(police)
        metriques = QFontMetrics(police)
        h_texte = metriques.height()

        if not self.courbes:
            # Message EXPLICITE sur ce qu'on attend : « au premier essai » se
            # lisait comme une panne au bout de la troisieme heure de calcul.
            peintre.setPen(QColor(registre.TEXTE_SECONDAIRE))
            peintre.drawText(zone, Qt.AlignmentFlag.AlignCenter,
                             self._TEXTE_ATTENTE)
            peintre.end()
            return

        tc = self.courbes.get("temps_cible") or []
        qc = self.courbes.get("debit_cible") or []
        ts = self.courbes.get("temps_calcule") or []
        qs = self.courbes.get("debit_calcule") or []
        if len(tc) < 2 or len(ts) < 2:
            peintre.end()
            return

        # LES SECTIONS DEJA CALEES ENTRENT DANS L'ECHELLE, mais PAS dans la
        # fenetre de crue : celle-ci se calcule sur la paire courante, qui est
        # ce qu'on juge. Les couper a l'echelle les ecraserait ; les laisser
        # commander la fenetre deplacerait le regard vers un apport clos.
        deja = [c for c in self.precedentes if len(c.get("debit") or []) > 1]
        courantes = [c for c in deja if not c.get("anterieur")]
        anterieures = [c for c in deja if c.get("anterieur")]

        stylo_cale, stylo_avant, stylo_cible, stylo_mesure = self._stylos()
        lignes = self._peindre_legende(
            peintre, zone, metriques, h_texte, courantes, anterieures,
            stylo_cale, stylo_avant, stylo_cible, stylo_mesure)
        q_max, gauche, haut, largeur, hauteur, t_min, t_max, etendue_t = (
            self._echelles(zone, metriques, h_texte, lignes, tc, qc, ts, qs, deja))

        def point(t, q):
            return QPointF(gauche + largeur * (t - t_min) / etendue_t,
                           haut + hauteur * (1.0 - q / (1.08 * q_max)))

        self._peindre_axes(peintre, zone, h_texte, q_max, gauche, haut, largeur,
                           hauteur, t_min, t_max)

        # DERRIERE, ET CLIPPEES. Une section calee peut deborder la fenetre de
        # crue courante : sans decoupe, sa polyligne irait ecrire par-dessus
        # les graduations et la legende.
        peintre.setClipRect(QRectF(gauche, haut, largeur, hauteur))
        self._peindre_sections_calees(peintre, deja, point, stylo_cale,
                                      stylo_avant)
        self._peindre_cible_et_calcule(peintre, tc, qc, ts, qs, point,
                                       stylo_cible, stylo_mesure)
        peintre.setClipping(False)
        peintre.end()

    @staticmethod
    def _stylos():
        """Les quatre traits : section calee, calage precedent, cible, calcule."""
        # DEUX FAMILLES DERRIERE, ET ELLES NE SE CONFONDENT PAS : ce que CE
        # calage a cale, a l'accent adouci en pointille ; ce que le PRECEDENT
        # avait cale et qu'on ne refait pas, au neutre fonce en tiret-point.
        # Deux teintes ET deux styles de trait — la teinte seule ne porte
        # jamais le sens.
        cale = QColor(registre.ACCENT)
        cale.setAlpha(130)
        stylo_cale = QPen(cale, 1.2, Qt.PenStyle.DotLine)
        stylo_avant = QPen(QColor(registre.NEUTRE_FONCE), 1.2, Qt.PenStyle.DashDotLine)
        stylo_cible = QPen(QColor(registre.ENCRE), 1.6, Qt.PenStyle.DashLine)
        stylo_mesure = QPen(QColor(registre.ACCENT), 2.2)
        return stylo_cale, stylo_avant, stylo_cible, stylo_mesure

    def _peindre_legende(self, peintre, zone, metriques, h_texte, courantes,
                         anterieures, stylo_cale, stylo_avant, stylo_cible,
                         stylo_mesure):
        """La legende, au-dessus du trace ; rend ses lignes, dont depend le haut du trace."""
        # LA LEGENDE A SES PROPRES LIGNES, AU-DESSUS DU TRACE. Posee dans le
        # trace, en haut a droite, elle passait sous les pointes des courbes
        # des que la police grandissait (13 pt : « cible décalée » coupee par le
        # pic). Le libelle de la cible DIT son decalage des qu'il n'est pas nul
        # — sans quoi le lecteur croirait les deux courbes sur la meme origine
        # des temps. La troisieme et la quatrieme entree n'apparaissent QUE
        # s'il y a quelque chose derriere : au premier apport, une legende
        # annoncant des sections calees qui n'existent pas ferait chercher des
        # courbes absentes. Les entrees passent a la ligne quand la largeur
        # manque.
        decalage = float(self.courbes.get("decalage_h") or 0.0)
        entrees = [(stylo_mesure, "calculé"),
                   (stylo_cible, "cible" if abs(decalage) < 0.005
                    else f"cible décalée de {nombre(decalage, 2, signe=True)} h")]
        if courantes:
            entrees.append((stylo_cale, compte(len(courantes), "section calée",
                                               "sections calées")))
        if anterieures:
            entrees.append((stylo_avant, compte(len(anterieures), "section")
                            + " du calage précédent"))
        lignes, x = [[]], 0.0
        for stylo, libelle in entrees:
            place = 22 + metriques.horizontalAdvance(libelle) + 14
            if lignes[-1] and x + place > zone.width():
                lignes.append([])
                x = 0.0
            lignes[-1].append((x, stylo, libelle))
            x += place
        for rang, ligne in enumerate(lignes):
            y = zone.top() + rang * (h_texte + 2)
            for x, stylo, libelle in ligne:
                gauche_entree = zone.left() + x
                peintre.setPen(stylo)
                peintre.drawLine(QPointF(gauche_entree, y + h_texte / 2),
                                 QPointF(gauche_entree + 18, y + h_texte / 2))
                peintre.setPen(QColor(registre.ENCRE))
                peintre.drawText(QRectF(gauche_entree + 22, y, zone.width(), h_texte),
                                 int(Qt.AlignmentFlag.AlignLeft
                                     | Qt.AlignmentFlag.AlignVCenter), libelle)
        return lignes

    @staticmethod
    def _echelles(zone, metriques, h_texte, lignes, tc, qc, ts, qs, deja):
        """Debit maximal, cadre du trace et fenetre de crue."""
        q_max = max([max(qc), max(qs)]
                    + [max(c["debit"]) for c in deja]) or 1.0
        # LES MARGES SUIVENT LA POLICE : la gauche loge la plus large des
        # graduations, le bas une ligne de texte, le haut la legende.
        gauche = zone.left() + max(metriques.horizontalAdvance(f"{q_max:.0f}"),
                                   metriques.horizontalAdvance("m³/s")) + 8
        haut = zone.top() + len(lignes) * (h_texte + 2) + 6
        largeur = max(zone.right() - gauche, 10)
        hauteur = max(zone.bottom() - h_texte - 4 - haut, 10)
        t_min, t_max = _fenetre_crue(tc, qc, ts, qs, max(max(qc), max(qs)) or 1.0)
        etendue_t = (t_max - t_min) or 1.0
        return q_max, gauche, haut, largeur, hauteur, t_min, t_max, etendue_t

    @staticmethod
    def _peindre_axes(peintre, zone, h_texte, q_max, gauche, haut, largeur,
                      hauteur, t_min, t_max):
        """Cadre et axes : grille des debits, graduations, bornes de temps."""
        # Repere discret : graduations de debit sur la grille fine du
        # registre, l'axe des temps.
        peintre.setPen(QPen(QColor(registre.GRILLE), 1))
        for fraction in (0.25, 0.5, 0.75, 1.0):
            y = haut + hauteur * (1.0 - fraction / 1.08)
            peintre.drawLine(QPointF(gauche, y), QPointF(gauche + largeur, y))
        peintre.setPen(QColor(registre.TEXTE_SECONDAIRE))
        a_droite = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        for fraction in (0.5, 1.0):
            y = haut + hauteur * (1.0 - fraction / 1.08)
            peintre.drawText(QRectF(zone.left(), y - h_texte / 2,
                                    gauche - zone.left() - 5, h_texte),
                             a_droite, f"{fraction * q_max:.0f}")
        peintre.drawText(QRectF(zone.left(), haut + hauteur - h_texte / 2,
                                gauche - zone.left() - 5, h_texte), a_droite, "m³/s")
        peintre.drawText(QRectF(gauche, haut + hauteur + 2, largeur, h_texte),
                         int(Qt.AlignmentFlag.AlignLeft), f"{t_min:.0f} h")
        peintre.drawText(QRectF(gauche, haut + hauteur + 2, largeur, h_texte),
                         int(Qt.AlignmentFlag.AlignRight), f"{t_max:.0f} h")

    @staticmethod
    def _peindre_sections_calees(peintre, deja, point, stylo_cale, stylo_avant):
        """Les sections deja calees, derriere la paire courante."""
        for courbe in deja:
            peintre.setPen(stylo_avant if courbe.get("anterieur") else stylo_cale)
            peintre.drawPolyline(QPolygonF(
                [point(t, q) for t, q in zip(courbe["temps"],
                                             courbe["debit"])]))

    @staticmethod
    def _peindre_cible_et_calcule(peintre, tc, qc, ts, qs, point, stylo_cible,
                                  stylo_mesure):
        """La cible, puis le calcule par-dessus."""
        for temps, debits, stylo in ((tc, qc, stylo_cible), (ts, qs, stylo_mesure)):
            peintre.setPen(stylo)
            peintre.drawPolyline(QPolygonF(
                [point(t, q) for t, q in zip(temps, debits)]))


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
