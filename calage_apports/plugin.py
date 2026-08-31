# -*- coding: utf-8 -*-
"""
Enveloppe QGIS du plugin « Calage des apports ».

Ce fichier est volontairement mince : il presente des couches, recueille des
choix, et delegue tout le reste a noyau.py — qui delegue lui-meme a la chaine
de calage. Aucune regle de controle n'est ecrite ici, sans quoi elle
existerait en deux exemplaires et divergerait.

UNE SEULE PORTE D'ENTREE : une fenetre non modale en six onglets, qui suit
l'ordre reel des decisions — modele et ecriture des objets, axe et precision
attendue, sorties, cibles et lancement, suivi du calcul, aide. Ce que QGIS
apporte ici et qu'aucun script ne remplace : voir les sections et les
injections du modele sur la carte, et y dessiner celles qui manquent.

Les calculs longs ne passent jamais par ici : un calage represente des heures
et figerait l'interface.
"""

import functools
import os
import traceback
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsMapLayerProxyModel,
    QgsMeshLayer,
    QgsMessageLog,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox
from qgis.PyQt.QtCore import QMetaType, QSettings, Qt, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import noyau

DOSSIER = os.path.dirname(__file__)


# ---------------------------------------------------------------------------
# Types de champ, et leur compatibilite entre versions de QGIS
#
# QgsField n'accepte QMetaType.Type que depuis QGIS 3.38 ; avant, il attend
# QVariant.Type. metadata.txt annonce qgisMinimumVersion=3.34, et l'ecriture
# directe en QMetaType rendait cette promesse FAUSSE : sur une 3.34 ou une
# 3.36 — des LTR encore installees en entreprise — l'extension s'installait,
# s'ouvrait, et « Charger les couches du modele » levait un TypeError. On
# essaie donc le type moderne, et l'on retombe sur l'ancien, qui reste accepte
# des versions recentes.
#
# L'essai porte sur la CONSTRUCTION REELLE d'un QgsField, jamais sur un
# numero de version : c'est la seule chose qui reponde a la question posee, et
# elle vaut aussi pour les distributions qui retro-portent.
try:
    QgsField("_essai_de_type", QMetaType.Type.QString)
    TYPE_CHAMP_TEXTE = QMetaType.Type.QString
    TYPE_CHAMP_REEL = QMetaType.Type.Double
except TypeError:                                            # QGIS < 3.38
    from qgis.PyQt.QtCore import QVariant
    TYPE_CHAMP_TEXTE = QVariant.String
    TYPE_CHAMP_REEL = QVariant.Double


# ---------------------------------------------------------------------------
# Convention de nommage
#
# Les noms doivent correspondre EXACTEMENT a ceux de la geometrie HEC-RAS :
# c'est par eux que le classeur, le fichier Unsteady Flow et les resultats se
# rejoignent. La convention ne peut donc etre qu'une aide au moment de CREER
# un objet, jamais un renommage impose a l'existant.
#
# Elle separe les ROLES, et ne cherche pas a lier un apport a sa section par
# le nom : l'appariement est geometrique (premiere injection en amont), et
# deux sources de verite finiraient par diverger. Le numero d'une section n'a
# donc pas a reprendre celui de son apport — l'onglet 4 affiche le lien
# reellement calcule.
# ---------------------------------------------------------------------------

PREFIXE_APPORT = "A"        # apports a caler          : A1, A2...
PREFIXE_SECTION = "SC"      # sections de controle     : SC1, SC2...
# IN_... et OUT_... restent aux entrees permanentes et aux exutoires, qui ne
# sont pas cales : c'est deja l'usage du modele d'essai, et il est parlant.

CONVENTION_NOMS = (
    "Objets sans nom : nommés <b>A1, A2…</b> (apports) et <b>SC1, SC2…</b> "
    "(sections). Le numéro d'une section ne reprend pas celui de son apport — "
    "l'appariement est géométrique, et le lien réel s'affiche à l'onglet 4."
)
INFOBULLE_CONVENTION = (
    "A1, A2… apports à caler ; SC1, SC2… sections de contrôle ; IN_… entrées "
    "permanentes ; OUT_… exutoires. Les noms doivent correspondre exactement "
    "à ceux de la géométrie HEC-RAS : la convention n'est appliquée qu'aux "
    "objets créés sans nom, et ne renomme jamais l'existant."
)


# ---------------------------------------------------------------------------
# Conversion QGIS <-> chaine de calage
# ---------------------------------------------------------------------------

def couche_vivante(couche):
    """
    Retourne la couche si son objet C++ existe encore, None sinon.

    Une couche memoire retiree du projet QGIS laisse derriere elle une
    reference Python qui semble valide mais dont l'objet sous-jacent est
    detruit : y toucher leve « wrapped C/C++ object has been deleted ».
    Le cas est devenu courant depuis que la fenetre n'est plus modale — on
    peut desormais supprimer une couche pendant qu'elle est ouverte, ce qui
    est precisement l'interet d'une fenetre non modale.
    """
    if couche is None:
        return None
    try:
        couche.featureCount()
    except RuntimeError:
        return None
    return couche


# ---------------------------------------------------------------------------
# Presentation des couches du modele
#
# Les styles sont livres AVEC le plugin (dossier styles/) et non lus dans un
# dossier de travail : un chemin exterieur ferait dependre l'apparence du poste
# sur lequel le plugin tourne, et le premier collegue a l'installer verrait des
# couches sans style, sans comprendre pourquoi.
# ---------------------------------------------------------------------------

DOSSIER_STYLES = os.path.join(DOSSIER, "styles")

# Ordre d'affichage, du HAUT vers le bas de la legende. Les lignes passent
# devant le maillage, qui passe devant l'emprise : dessine dans l'autre sens,
# le maillage masquerait les objets que l'on vient precisement verifier.
STYLES = {
    "injections": "injections.qml",
    "sections": "sections.qml",
    "maillage": "maillage.qml",
}


def appliquer_style(couche, nom_style):
    """
    Applique un style livre avec le plugin. Retourne (applique, message).

    Un style absent ou refuse ne doit JAMAIS empecher le chargement : la
    couche reste exploitable avec le style par defaut de QGIS, et le calage
    ne depend pas de son apparence.
    """
    couche = couche_vivante(couche) if hasattr(couche, "featureCount") else couche
    if couche is None:
        return False, "couche absente"
    chemin = os.path.join(DOSSIER_STYLES, STYLES.get(nom_style, ""))
    if not os.path.isfile(chemin):
        return False, f"style {nom_style} introuvable"
    try:
        message, ok = couche.loadNamedStyle(chemin)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    if ok:
        couche.triggerRepaint()
    return bool(ok), (message or "").strip()


def appliquer_styles(injections, sections, maillage):
    """Style de chacune des trois couches ; retourne les echecs eventuels."""
    echecs = []
    for couche, nom in ((injections, "injections"), (sections, "sections"),
                        (maillage, "maillage")):
        if couche is None:
            continue
        ok, message = appliquer_style(couche, nom)
        if not ok:
            echecs.append(f"{nom} : {message}")

    # AUCUN GROUPE DE DONNEES ACTIF sur le maillage : on veut le maillage nu.
    # Par defaut MDAL active le premier groupe trouve — souvent une altitude de
    # fond — et le modele disparait sous un aplat colore, alors que ce qu'on
    # vient verifier ici, c'est la position des lignes vis-a-vis des mailles.
    if maillage is not None:
        try:
            reglages = maillage.rendererSettings()
            reglages.setActiveScalarDatasetGroup(-1)
            reglages.setActiveVectorDatasetGroup(-1)
            maillage.setRendererSettings(reglages)
            maillage.triggerRepaint()
        except Exception as e:
            echecs.append(f"maillage (groupe actif) : {type(e).__name__}: {e}")
    return echecs


def ordonner_couches(projet, couches):
    """
    Impose l'ordre de la legende, du haut vers le bas.

    Les couches sont ajoutees au projet SANS entrer dans la legende, puis
    inserees ici a leur rang. Se reposer sur l'ordre d'appel a addMapLayer()
    reviendrait a coder l'ordre a l'envers et sans le dire : un jour ou
    l'autre, quelqu'un deplacerait deux lignes et l'affichage changerait.
    """
    racine = projet.layerTreeRoot()
    rang = 0
    for couche in couches:
        if couche is None:
            continue
        try:
            existant = racine.findLayer(couche.id())
            if existant is not None:
                racine.removeChildNode(existant)
            racine.insertLayer(rang, couche)
            rang += 1
        except (RuntimeError, AttributeError):
            # Couche detruite entre-temps : l'affichage n'est pas une raison
            # d'interrompre le chargement.
            continue
    return rang


def couche_vers_gdf(couche, champ_nom=None, selection_seule=False,
                    prefixe_defaut=None, noms_pris=()):
    """
    Convertit une couche vectorielle QGIS en GeoDataFrame normalise
    ('nom', 'geometry'), sans passer par un fichier intermediaire.

    Les MultiLineString a une seule partie sont ramenees a une LineString ;
    au-dela, la geometrie est refusee, car un PK n'y a pas de sens.

    prefixe_defaut : nomme les entites SANS nom selon la convention retenue
        (voir CONVENTION_NOMS). A defaut, elles heritaient du nom de la
        couche suivi d'un numero — lisible, mais qui ne dit pas le role de
        l'objet dans le calage.
    noms_pris : noms deja utilises dans le modele, a ne pas reprendre. Deux
        objets homonymes dans une geometrie HEC-RAS rendraient l'appariement
        indecidable.
    """
    import geopandas as gpd
    from shapely import wkt as shapely_wkt

    if couche is None:
        raise ValueError("aucune couche designee")
    if couche.geometryType() != QgsWkbTypes.LineGeometry:
        raise ValueError(f"« {couche.name()} » n'est pas une couche de lignes")

    champs = [f.name() for f in couche.fields()]
    if champ_nom is None:
        champ_nom = next((c for c in ("nom", "Nom", "NOM", "name", "Name",
                                      "NAME", "id", "Id", "ID") if c in champs),
                         None)

    entites = couche.selectedFeatures() if selection_seule else couche.getFeatures()
    noms, geometries = [], []
    occupes = {str(n).strip() for n in noms_pris}
    compteur = 0

    def nom_automatique():
        """Prochain nom libre suivant la convention, ex. A1, A2, SC1..."""
        nonlocal compteur
        while True:
            compteur += 1
            propose = f"{prefixe_defaut}{compteur}"
            if propose not in occupes:
                occupes.add(propose)
                return propose

    for i, entite in enumerate(entites):
        geometrie = entite.geometry()
        if geometrie is None or geometrie.isEmpty():
            continue
        forme = shapely_wkt.loads(geometrie.asWkt())
        if forme.geom_type == "MultiLineString":
            if len(forme.geoms) != 1:
                raise ValueError(
                    f"« {couche.name() } » : une entite comporte "
                    f"{len(forme.geoms)} parties ; une polyligne simple est "
                    f"attendue")
            forme = forme.geoms[0]
        valeur = entite[champ_nom] if champ_nom else None
        if valeur not in (None, "") and str(valeur).strip():
            noms.append(str(valeur).strip())
        elif prefixe_defaut:
            noms.append(nom_automatique())
        else:
            noms.append(f"{couche.name()}_{i + 1:02d}")
        geometries.append(forme)

    if not geometries:
        raise ValueError(f"« {couche.name()} » : aucune entite exploitable"
                         + (" dans la selection" if selection_seule else ""))

    return gpd.GeoDataFrame({"nom": noms}, geometry=geometries,
                            crs=couche.crs().authid() or None)


def gdf_vers_couche(gdf, nom_couche, crs_authid):
    """Cree une couche memoire QGIS a partir d'un GeoDataFrame."""
    couche = QgsVectorLayer(f"LineString?crs={crs_authid}", nom_couche, "memory")
    fournisseur = couche.dataProvider()

    champs = QgsFields()
    champs.append(QgsField("nom", TYPE_CHAMP_TEXTE))
    for colonne in gdf.columns:
        if colonne in ("nom", "geometry"):
            continue
        type_qt = (TYPE_CHAMP_REEL
                   if gdf[colonne].dtype.kind in "fi" else TYPE_CHAMP_TEXTE)
        champs.append(QgsField(str(colonne)[:10], type_qt))
    fournisseur.addAttributes(champs)
    couche.updateFields()

    entites = []
    for _, ligne in gdf.iterrows():
        entite = QgsFeature(couche.fields())
        entite.setGeometry(QgsGeometry.fromWkt(ligne["geometry"].wkt))
        entite["nom"] = str(ligne["nom"])
        for colonne in gdf.columns:
            if colonne in ("nom", "geometry"):
                continue
            valeur = ligne[colonne]
            entite[str(colonne)[:10]] = (float(valeur)
                                         if isinstance(valeur, (int, float))
                                         else str(valeur))
        entites.append(entite)
    fournisseur.addFeatures(entites)
    couche.updateExtents()
    return couche


def construire_couche_lignes_depuis_wkt(nom_couche, entites, crs_authid):
    """
    Cree une couche MEMOIRE QGIS de lignes a partir d'entites {"nom", "wkt"},
    telles que renvoyees par noyau.charger_couches_modele().

    Une couche memoire est TOUJOURS editable : c'est ce qui permet de
    dessiner de nouvelles sections directement sur la carte, par-dessus ce
    qui existe deja dans la geometrie HEC-RAS.
    """
    couche = QgsVectorLayer(f"LineString?crs={crs_authid}", nom_couche, "memory")
    fournisseur = couche.dataProvider()
    fournisseur.addAttributes([QgsField("nom", TYPE_CHAMP_TEXTE)])
    couche.updateFields()
    objets = []
    for entite in entites:
        f = QgsFeature(couche.fields())
        f.setGeometry(QgsGeometry.fromWkt(entite["wkt"]))
        f["nom"] = str(entite["nom"])
        objets.append(f)
    if objets:
        fournisseur.addFeatures(objets)
    couche.updateExtents()
    return couche


def construire_couche_polygones_depuis_wkt(nom_couche, entites, crs_authid):
    """Meme principe que ci-dessus, pour l'emprise (perimetre de zone 2D)."""
    couche = QgsVectorLayer(f"Polygon?crs={crs_authid}", nom_couche, "memory")
    fournisseur = couche.dataProvider()
    fournisseur.addAttributes([QgsField("zone", TYPE_CHAMP_TEXTE)])
    couche.updateFields()
    objets = []
    for entite in entites:
        f = QgsFeature(couche.fields())
        f.setGeometry(QgsGeometry.fromWkt(entite["wkt"]))
        f["zone"] = str(entite["zone"])
        objets.append(f)
    if objets:
        fournisseur.addFeatures(objets)
    couche.updateExtents()
    return couche


# ---------------------------------------------------------------------------
# Charte graphique ISL Ingenierie
#
# Couleurs RELEVEES sur les visuels de la charte (charte/), pas devinees :
#   - le pictogramme du domaine « Prevention des inondations & ouvrages de
#     protection » — celui de ce projet — donne le teal d'accent ;
#   - la frise institutionnelle donne le bleu ardoise.
# Typographie de la charte : Helvetica Neue. Elle n'est pas installee de
# serie sous Windows ; Arial en est le substitut metrique usuel, d'ou la
# pile de replis.
#
# Le style reste VOLONTAIREMENT RETENU : il ne fixe que des couleurs de
# texte et de bordure, jamais de fond, hormis le bouton principal. QGIS se
# decline en theme clair ET sombre, et un fond impose casserait le second.
# ---------------------------------------------------------------------------

NOM_PLUGIN = "Calage des apports"
EDITEUR = "ISL Ingénierie"

# Pente de la ligne d'energie d'un apport CREE (« Flow Hydrograph Slope »).
#
# ELLE NE SE SAISIT NULLE PART, contrairement a ce que ce commentaire a
# longtemps promis : aucun champ ne lui a jamais correspondu a l'onglet 1.
# Elle ne sert qu'a donner sa pente a une injection au moment ou on l'ecrit
# dans l'Unsteady Flow, faute de mieux. La pente REELLE de chaque apport est
# calculee sur le profil en long et pre-remplie par apport dans le classeur
# (noyau.pentes_locales_apports) : c'est la, et seulement la, qu'elle se lit
# et se corrige.
PENTE_APPORT_DEFAUT = 0.01

# Titre de la copie de travail de la geometrie. Ce n'est PLUS un champ de
# l'interface : le clonage ne se pilote pas, il n'a lieu que si la geometrie
# est surchargee a l'onglet 1, et l'utilisateur n'avait rien a decider ici.
# Le parametre reste ecrit dans le classeur, ou le pont le relit.
NOM_CLONE_GEOMETRIE_DEFAUT = "Geometrie_calage"

# Precision attendue, en fraction de la cible. Ce sont les valeurs par defaut
# de la chaine (Configuration) : les redire ici en dur les ferait diverger le
# jour ou la methode changerait.
#
# Elles servent DEUX FOIS : a proposer une valeur de depart a l'onglet 2, et a
# colorer les jauges du suivi quand l'etat publie ne porte pas ses propres
# seuils. La forme ne se saisit pas — elle ne se negocie pas de la meme facon —
# mais elle se juge, d'ou sa presence ici.
TOLERANCE_VOLUME_DEFAUT = 0.05
TOLERANCE_PIC_DEFAUT = 0.02
TOLERANCE_FORME_DEFAUT = 0.03

# Fenetre de crue : bornes hors desquelles il ne se passe rien d'interessant.
#
# LA REGLE EXISTE EN DEUX EXEMPLAIRES, ET C'EST ASSUME. Le greffon la traite
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


ISL_TEAL = "#3A8D94"          # institutionnel (Pantone 5483 C)
ISL_TEAL_SOMBRE = "#2E7176"
ISL_ARDOISE = "#608098"       # frise institutionnelle
ISL_ARDOISE_CLAIR = "#9BAEB7"  # institutionnel (Pantone 7543 C)
# Hors charte, et volontairement : la charte n'a pas de couleur d'etat, et
# reserver le teal institutionnel a l'erreur le banaliserait. Ces deux tons
# ne servent QU'A dire si une saisie est fautive ou une etape franchie.
ISL_ROUGE = "#A03028"
ISL_VERT = "#3E7A5E"
POLICE_ISL = '"Helvetica Neue", "Helvetica", "Arial", sans-serif'

# Deux registres de texte, et deux seulement, en plus des libelles de champs :
#   AIDE — une phrase grise sous un groupe, qui explique un choix ;
#   ETAT — le compte rendu de ce qui vient d'etre fait, encadre.
# Les distinguer par un ROLE plutot que par une feuille de style ecrite a
# chaque endroit evite qu'un texte d'aide finisse en corps de texte, ce qui
# etait arrive : la propriete etait posee, mais aucune regle ne la lisait.
ROLE_AIDE = "aide"
ROLE_ETAT = "etat"

STYLE_ISL = f"""
QDialog {{ font-family: {POLICE_ISL}; }}

/* --- Onglets ---------------------------------------------------------
   Le gras n'est PAS demande ici mais sur la police de la barre elle-meme
   (voir __init__). Une feuille de style ne change que le rendu,
   pas le calcul de largeur : Qt mesurait les libelles en maigre puis les
   dessinait en gras, et « 2. Profil en long » se retrouvait rogne.
   Styliser un onglet fait par ailleurs basculer Qt sur le modele de boite ;
   le remplissage est donc fixe ici, sinon le libelle colle aux bords. */
QTabWidget::pane {{
    border: 1px solid palette(mid);
    border-radius: 4px;
    top: -1px;
}}
QTabBar::tab {{
    padding: 8px 16px;
    margin-right: 2px;
    border-bottom: 3px solid transparent;
}}
QTabBar::tab:selected {{
    color: {ISL_TEAL};
    border-bottom: 3px solid {ISL_TEAL};
}}
QTabBar::tab:hover:!selected {{ color: {ISL_ARDOISE}; }}

/* --- Cadres ---------------------------------------------------------- */
QGroupBox {{
    border: 1px solid palette(mid);
    border-radius: 4px;
    margin-top: 13px;
    padding: 12px 10px 8px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {ISL_ARDOISE};
    font-weight: bold;
}}

/* --- Saisies ---------------------------------------------------------
   QLineEdit seulement. Les listes deroulantes et les compteurs portent des
   sous-controles — fleche, boutons haut/bas — que le moindre reglage de
   bordure fait basculer sur un rendu maison, au risque de perdre la
   fleche. Ils restent natifs, donc identiques au reste de QGIS. */
QLineEdit {{
    border: 1px solid palette(mid);
    border-radius: 3px;
    padding: 4px 6px;
    selection-background-color: {ISL_TEAL};
}}
QLineEdit:focus {{ border: 1px solid {ISL_TEAL}; }}

/* --- Boutons ---------------------------------------------------------- */
QPushButton {{
    border: 1px solid palette(mid);
    border-radius: 3px;
    padding: 5px 14px;
}}
QPushButton:hover {{ border-color: {ISL_ARDOISE}; color: {ISL_ARDOISE}; }}
QPushButton:disabled {{ color: palette(mid); }}
QPushButton#boutonPrincipal {{
    background-color: {ISL_TEAL};
    color: white;
    border: 1px solid {ISL_TEAL};
    padding: 7px 18px;
    font-weight: bold;
}}
QPushButton#boutonPrincipal:hover {{
    background-color: {ISL_TEAL_SOMBRE};
    border-color: {ISL_TEAL_SOMBRE};
    color: white;
}}
QPushButton#boutonPrincipal:disabled {{
    background-color: palette(mid); border-color: palette(mid);
}}
/* Seconde action forte — le lancement du calage. Meme poids que l'action
   principale, sans le fond plein : les deux ne sont jamais a portee de clic
   au meme moment, et deux aplats teal se disputeraient l'oeil. */
QPushButton#boutonAccent {{
    color: {ISL_TEAL};
    border: 1px solid {ISL_TEAL};
    padding: 6px 16px;
    font-weight: bold;
}}
QPushButton#boutonAccent:hover {{
    background-color: {ISL_TEAL}; color: white;
}}

/* --- Textes d'accompagnement -----------------------------------------
   Aucun fond n'est impose ailleurs qu'ici, et ceux-ci viennent de la
   palette : QGIS se decline en theme clair ET sombre, une couleur en dur
   casserait le second. */
QLabel[role="aide"] {{
    color: {ISL_ARDOISE};
    font-size: 8pt;
    padding: 1px 0 3px 0;
}}
QLabel[role="etat"] {{
    background-color: palette(alternate-base);
    border-left: 3px solid {ISL_ARDOISE};
    border-radius: 2px;
    padding: 7px 9px;
}}
QLabel#filConducteur {{
    background-color: palette(alternate-base);
    border-radius: 3px;
    padding: 6px 10px;
}}
QTextEdit#resume {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 8pt;
    border: 1px solid palette(mid);
    border-radius: 3px;
}}
QTextBrowser {{ border: none; }}

/* --- Suivi en temps reel ---------------------------------------------
   La banniere porte sa couleur elle-meme, selon l'etat : elle est le seul
   endroit du plugin ou un aplat de couleur dit quelque chose. */
QLabel#banniereSuivi {{ font-family: {POLICE_ISL}; }}
QProgressBar {{
    border: 1px solid palette(mid);
    border-radius: 3px;
    height: 22px;
    text-align: center;
    font-weight: bold;
    background-color: palette(alternate-base);
}}
QProgressBar::chunk {{
    background-color: {ISL_TEAL};
    border-radius: 2px;
}}
QTableWidget {{
    border: 1px solid palette(mid);
    border-radius: 3px;
    gridline-color: palette(midlight);
}}
QHeaderView::section {{
    background-color: palette(alternate-base);
    color: {ISL_ARDOISE};
    font-weight: bold;
    border: none;
    border-bottom: 2px solid {ISL_ARDOISE};
    padding: 5px 6px;
}}
"""


# ---------------------------------------------------------------------------
# Suivi en temps reel — couleurs d'etat
#
# Un calage dure des heures. Ce qui manquait n'est pas l'information — suivi.py
# l'ecrit depuis toujours — mais un endroit ou la voir : le calcul s'arretait
# sans donner de nouvelles. Ces quatre couleurs sont le vocabulaire de
# l'affichage, et il n'y en a pas d'autre.
# ---------------------------------------------------------------------------

COULEUR_STATUT = {
    "validé": ISL_VERT,
    "en cours": ISL_TEAL,
    "échoué": ISL_ROUGE,
    "en attente": ISL_ARDOISE_CLAIR,
}

# LA COULEUR NE PORTE JAMAIS SEULE LE SENS. Une part notable de la population
# distingue mal le rouge du vert ; un statut lisible uniquement a sa teinte
# est illisible pour elle. Chaque etat porte donc AUSSI un glyphe, et les
# quatre teintes different par la clarte autant que par la teinte.
GLYPHE_STATUT = {
    "validé": "✔",
    "en cours": "▶",
    "échoué": "✕",
    "en attente": "·",
}


class RubanApports(QWidget):
    """
    Une bande de segments, un par apport, coloree selon son statut.

    C'est la vue d'ensemble : sur douze apports, savoir en un coup d'oeil que
    huit sont valides, un en cours et trois en attente vaut mieux que douze
    lignes de texte. L'apport en cours est souligne d'un trait epais.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.apports = []
        self.en_cours = None
        self.setMinimumHeight(46)
        self.setSizePolicy(self.sizePolicy().Expanding,
                           self.sizePolicy().Fixed)

    def actualiser(self, apports, en_cours):
        self.apports = apports or []
        self.en_cours = en_cours
        self.update()

    def paintEvent(self, evenement):                        # noqa: N802
        from qgis.PyQt.QtGui import QColor, QPainter

        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.apports:
            peintre.setPen(QColor(ISL_ARDOISE_CLAIR))
            peintre.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "aucun calage suivi")
            peintre.end()
            return

        n = len(self.apports)
        marge, ecart = 1, 3
        largeur = (self.width() - 2 * marge - ecart * (n - 1)) / n
        hauteur = self.height() - 18
        for i, apport in enumerate(self.apports):
            statut = apport.get("statut")
            x = marge + i * (largeur + ecart)
            couleur = QColor(COULEUR_STATUT.get(statut, ISL_ARDOISE_CLAIR))
            # CE QUI EST FAIT est plein ; CE QUI RESTE est un simple contour.
            # La difference se voit sans distinguer les teintes — c'est la
            # clarte qui porte l'information, la couleur ne fait que la
            # confirmer.
            acheve = statut in ("validé", "échoué", "en cours")
            if acheve:
                peintre.setPen(Qt.PenStyle.NoPen)
                peintre.setBrush(couleur)
            else:
                stylo = peintre.pen()
                stylo.setColor(couleur)
                stylo.setWidth(1)
                peintre.setPen(stylo)
                peintre.setBrush(Qt.BrushStyle.NoBrush)
            peintre.drawRoundedRect(int(x), 0, int(largeur), int(hauteur), 3, 3)
            # Le segment en cours porte un trait epais : c'est celui qu'on
            # cherche des yeux en revenant voir le calcul.
            if i == self.en_cours:
                peintre.setPen(Qt.PenStyle.NoPen)
                peintre.setBrush(QColor(ISL_TEAL_SOMBRE))
                peintre.drawRoundedRect(int(x), int(hauteur) + 2,
                                        int(largeur), 4, 2, 2)
            if largeur > 30:
                peintre.setPen(QColor("#FFFFFF" if acheve else ISL_ARDOISE))
                police = peintre.font()
                police.setPointSizeF(7.5)
                police.setBold(True)
                peintre.setFont(police)
                peintre.drawText(
                    int(x), 0, int(largeur), int(hauteur), Qt.AlignmentFlag.AlignCenter,
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
        # 56 px, mesures a l'ecran : en dessous, le libelle et la valeur sont
        # rognes a mi-hauteur par le remplissage du QGroupBox.
        self.setMinimumHeight(56)

    def actualiser(self, valeur_pct):
        self.valeur = valeur_pct
        self.update()

    def paintEvent(self, evenement):                        # noqa: N802
        from qgis.PyQt.QtGui import QColor, QPainter

        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        police = peintre.font()
        police.setPointSizeF(8.0)
        peintre.setFont(police)

        peintre.setPen(QColor(ISL_ARDOISE))
        peintre.drawText(0, 2, self.width(), 16,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.libelle)
        texte = ("—" if self.valeur is None else f"{self.valeur:.1f} %")
        police.setBold(True)
        police.setPointSizeF(11.0)
        peintre.setFont(police)
        conforme = (self.valeur is not None
                    and abs(self.valeur - 100.0) <= self.tolerance)
        peintre.setPen(QColor(ISL_VERT if conforme else
                              (ISL_ARDOISE_CLAIR if self.valeur is None
                               else ISL_ROUGE)))
        peintre.drawText(0, 18, self.width(), 20,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, texte)

        # Piste : +/- 10 % autour de la cible, ce qui cadre l'ecart utile.
        haut, hauteur, etendue = 42, 12, 10.0
        peintre.setPen(Qt.PenStyle.NoPen)
        # La piste doit se VOIR : sans elle, on ne lit qu'un trait rouge sans
        # savoir sur quelle etendue il se situe.
        peintre.setBrush(QColor("#00000024"))
        peintre.drawRoundedRect(0, haut, self.width(), hauteur, 3, 3)
        centre = self.width() / 2.0

        demi = self.tolerance / etendue * (self.width() / 2.0)
        peintre.setBrush(QColor(ISL_VERT + "33"))
        peintre.drawRect(int(centre - demi), haut, int(2 * demi), hauteur)

        if self.valeur is not None:
            ecart = max(-etendue, min(etendue, self.valeur - 100.0))
            largeur = ecart / etendue * (self.width() / 2.0)
            peintre.setBrush(QColor(ISL_VERT if conforme else ISL_ROUGE))
            x = centre if largeur >= 0 else centre + largeur
            peintre.drawRoundedRect(int(x), haut + 2, max(int(abs(largeur)), 2),
                                    hauteur - 4, 2, 2)
        peintre.setPen(QColor(ISL_ARDOISE))
        peintre.drawLine(int(centre), haut - 2, int(centre), haut + hauteur + 2)
        peintre.end()


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.courbes = None
        self.setMinimumHeight(190)

    def actualiser(self, courbes):
        self.courbes = courbes or None
        self.update()

    def paintEvent(self, evenement):                        # noqa: N802
        from qgis.PyQt.QtGui import QColor, QPainter, QPen, QPolygonF
        from qgis.PyQt.QtCore import QPointF

        peintre = QPainter(self)
        peintre.setRenderHint(QPainter.RenderHint.Antialiasing)
        police = peintre.font()
        police.setPointSizeF(7.5)
        peintre.setFont(police)

        if not self.courbes:
            # Message EXPLICITE sur ce qu'on attend : « au premier essai » se
            # lisait comme une panne au bout de la troisieme heure de calcul.
            peintre.setPen(QColor(ISL_ARDOISE_CLAIR))
            peintre.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "calcul HEC-RAS en cours — la courbe apparaît dès qu'un "
                "essai est évalué")
            peintre.end()
            return

        tc = self.courbes.get("temps_cible") or []
        qc = self.courbes.get("debit_cible") or []
        ts = self.courbes.get("temps_calcule") or []
        qs = self.courbes.get("debit_calcule") or []
        if len(tc) < 2 or len(ts) < 2:
            peintre.end()
            return

        gauche, droite, haut, bas = 46, 8, 8, 22
        largeur = max(self.width() - gauche - droite, 10)
        hauteur = max(self.height() - haut - bas, 10)
        q_max = max(max(qc), max(qs)) or 1.0
        t_min, t_max = _fenetre_crue(tc, qc, ts, qs, q_max)
        etendue_t = (t_max - t_min) or 1.0

        def point(t, q):
            return QPointF(gauche + largeur * (t - t_min) / etendue_t,
                           haut + hauteur * (1.0 - q / (1.08 * q_max)))

        # Repere discret : trois graduations de debit, l'axe des temps.
        peintre.setPen(QPen(QColor(ISL_ARDOISE_CLAIR), 1, Qt.PenStyle.DotLine))
        for fraction in (0.25, 0.5, 0.75, 1.0):
            y = haut + hauteur * (1.0 - fraction / 1.08)
            peintre.drawLine(gauche, int(y), gauche + largeur, int(y))
        peintre.setPen(QColor(ISL_ARDOISE))
        for fraction in (0.5, 1.0):
            y = haut + hauteur * (1.0 - fraction / 1.08)
            peintre.drawText(0, int(y) - 7, gauche - 5, 14,
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"{fraction * q_max:.0f}")
        peintre.drawText(0, haut + hauteur - 6, gauche - 5, 14,
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "m³/s")
        peintre.drawText(gauche, haut + hauteur + 2, largeur, 14,
                         Qt.AlignmentFlag.AlignLeft, f"{t_min:.0f} h")
        peintre.drawText(gauche, haut + hauteur + 2, largeur, 14,
                         Qt.AlignmentFlag.AlignRight, f"{t_max:.0f} h")

        for temps, debits, couleur, style, epaisseur in (
                (tc, qc, ISL_ARDOISE, Qt.PenStyle.DashLine, 1.6),
                (ts, qs, ISL_TEAL, Qt.PenStyle.SolidLine, 2.0)):
            peintre.setPen(QPen(QColor(couleur), epaisseur, style))
            peintre.drawPolyline(QPolygonF(
                [point(t, q) for t, q in zip(temps, debits)]))

        # Legende, en haut a droite : deux traits et deux mots, pas un cadre.
        # Le libelle de la cible DIT son decalage des qu'il n'est pas nul —
        # sans quoi le lecteur croirait les deux courbes sur la meme origine
        # des temps, et jugerait un calage juste sur une superposition qui ne
        # lui est pas comparable.
        decalage = float(self.courbes.get("decalage_h") or 0.0)
        libelle_cible = ("cible" if abs(decalage) < 0.005
                         else f"cible décalée de {decalage:+.2f} h")
        largeur_cible = 24 + 6 * len(libelle_cible)
        x_mesure = gauche + largeur - 56
        x_cible = x_mesure - largeur_cible
        peintre.setPen(QPen(QColor(ISL_ARDOISE), 1.6, Qt.PenStyle.DashLine))
        peintre.drawLine(x_cible, haut + 6, x_cible + 18, haut + 6)
        peintre.setPen(QColor(ISL_ARDOISE))
        peintre.drawText(x_cible + 22, haut, largeur_cible - 22, 14,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, libelle_cible)
        peintre.setPen(QPen(QColor(ISL_TEAL), 2.0))
        peintre.drawLine(x_mesure, haut + 6, x_mesure + 18, haut + 6)
        peintre.setPen(QColor(ISL_TEAL))
        peintre.drawText(x_mesure + 22, haut, 40, 14,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "mesuré")
        peintre.end()


def duree_lisible(secondes):
    """« 2 h 14 » plutot que « 8040 s » : c'est ce qu'on lit d'un coup d'oeil."""
    if secondes is None:
        return "—"
    secondes = int(secondes)
    if secondes < 60:
        return f"{secondes} s"
    if secondes < 3600:
        return f"{secondes // 60} min"
    return f"{secondes // 3600} h {(secondes % 3600) // 60:02d}"


# ---------------------------------------------------------------------------
# Journal
#
# CE QUI EST AFFICHE NE CHANGE PAS. Les boites continuent de dire str(e) —
# c'est souvent un message ecrit POUR l'utilisateur, et c'est bien ce qu'il
# doit lire. Ce qui manquait est ailleurs : quand l'exception n'a PAS ete
# ecrite pour lui, « 'Nom_zone_2D' » etait tout ce qui restait d'un KeyError,
# et rien n'en gardait trace. Un incident survenu sur un autre poste n'etait
# donc pas instruisable.
#
# Le projet s'est deja fait prendre : la colonne des pentes est restee vide a
# CHAQUE composition pendant des semaines, sur un ImportError avale par un
# except muet — voir noyau.pentes_locales_apports. C'est cette panne-la, celle
# qui ne dit rien, que le journal rend visible.
# ---------------------------------------------------------------------------

def journaliser(contexte, exception=None):
    """
    Ecrit dans le panneau Journal de QGIS, sous l'etiquette du plugin.

    A appeler DEPUIS un bloc except : format_exc() y lit l'exception courante.
    Sans exception, journalise le seul contexte — pour un echec qui ne leve
    pas, comme un style que QGIS refuse de charger.

    NE LEVE JAMAIS : un journal qui echoue n'a pas a emporter son appelant.
    """
    try:
        if exception is not None:
            contexte = (f"{contexte} — {type(exception).__name__}: {exception}"
                        f"\n{traceback.format_exc()}")
        QgsMessageLog.logMessage(contexte, NOM_PLUGIN,
                                 Qgis.MessageLevel.Critical)
    except Exception:                                       # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Sablier
#
# LES CALCULS LONGS RESTENT OU ILS SONT. « Composer et controler » enchaine
# trois lancements de sous-processus — chacun demarre un interpreteur qui
# importe h5py et ras-commander — puis l'ecriture de trois shapefiles et d'un
# classeur, puis tous les controles. Tout cela sur le fil graphique, et c'est
# assume : noyau.py n'expose que des operations de quelques secondes, et le
# calage lui-meme part en processus detache.
#
# CE QUI MANQUAIT N'EST PAS LA VITESSE, C'EST LE SIGNAL. Passe quelques
# secondes sans repeindre, Windows grise la fenetre et ajoute « (Ne repond
# pas) » a son titre : rien ne distinguait un greffon qui travaille d'un
# greffon plante, et l'on fermait QGIS au milieu d'une ecriture dans la
# geometrie.
#
# EN DECORATEUR, ET NON EN BLOC « with » : la restitution est ainsi garantie
# par un finally sans avoir a reindenter cent lignes, et surtout on ne peut
# pas l'oublier — un sablier non rendu reste sur TOUT QGIS jusqu'a la fin de
# la session, ce qui serait pire que pas de sablier du tout.
#
# L'ENVELOPPE NE PREND QUE self, ET C'EST VITAL. Ecrite « (self, *args) »,
# elle faisait tomber QGIS. PyQt decide du nombre d'arguments a transmettre a
# un slot d'apres la signature de l'appelable : une enveloppe *args passe pour
# tout accepter, et clicked(bool) lui transmet alors son « checked ». Les cinq
# methodes decorees ne prennent que self — methode(self, False) levait donc
# TypeError DANS un slot Qt, ce que PyQt >= 5.5 traite par abort(). Mesure sur
# PyQt 5.15.11 : une enveloppe *args recoit (False,), une enveloppe (self) ne
# recoit rien. Le banc d'essai ne pouvait pas le voir — il appelle les
# methodes directement, jamais par le signal.
#
# COROLLAIRE : ce decorateur ne convient qu'aux methodes SANS argument. C'est
# le cas des cinq, et ce sont toutes des slots.
# ---------------------------------------------------------------------------

def avec_sablier(methode):
    """Curseur d'attente pendant toute la methode, rendu quoi qu'il arrive."""
    @functools.wraps(methode)
    def enveloppe(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._sablier_pose = True
        try:
            return methode(self)
        finally:
            if getattr(self, "_sablier_pose", False):
                QApplication.restoreOverrideCursor()
                self._sablier_pose = False
    return enveloppe


def rendre_la_main(fenetre):
    """
    Retire le sablier avant une boite que l'utilisateur va LIRE.

    UN SEUL restore PAR set, ET C'EST LA RAISON DU DRAPEAU. Un
    restoreOverrideCursor() de trop n'est inoffensif que si la pile est VIDE ;
    sinon il depile le curseur courant, fut-il pose par QGIS lui-meme. Rendre
    la main ici PUIS laisser le finally du decorateur restaurer une seconde
    fois aurait donc pu retirer le curseur de quelqu'un d'autre.
    """
    if getattr(fenetre, "_sablier_pose", False):
        QApplication.restoreOverrideCursor()
        fenetre._sablier_pose = False


def sans_sablier(fenetre):
    """
    Suspend le sablier le temps d'une boite qui ATTEND L'UTILISATEUR.

    Un selecteur de fichier ou une question oui/non peut rester ouvert
    plusieurs minutes : le sablier y designerait un calcul qui n'a pas lieu,
    et c'est l'utilisateur qu'on attend. Il est repose a la fermeture de la
    boite, le travail n'etant pas fini pour autant.

    S'emploie en bloc « with » a l'INTERIEUR d'une methode decoree par
    @avec_sablier ; hors d'une telle methode, ne fait rien.
    """
    return _SablierSuspendu(fenetre)


class _SablierSuspendu:
    def __init__(self, fenetre):
        self.fenetre = fenetre
        self.etait_pose = False

    def __enter__(self):
        self.etait_pose = getattr(self.fenetre, "_sablier_pose", False)
        if self.etait_pose:
            QApplication.restoreOverrideCursor()
            self.fenetre._sablier_pose = False
        return self

    def __exit__(self, *_):
        if self.etait_pose:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.fenetre._sablier_pose = True
        return False


# ---------------------------------------------------------------------------
# Fabriques de widgets — un seul endroit ou se decide l'apparence d'un texte
# d'aide, d'un compte rendu ou d'un formulaire. Ecrite a la main a chaque
# fois, la mise en forme finissait par differer d'un onglet a l'autre.
# ---------------------------------------------------------------------------

def texte_aide(contenu, infobulle=None):
    """Phrase d'accompagnement : grise, plus petite, jamais indispensable."""
    label = QLabel(contenu)
    label.setWordWrap(True)
    label.setProperty("role", ROLE_AIDE)
    if infobulle:
        label.setToolTip(infobulle)
    return label


def texte_etat(contenu=""):
    """
    Compte rendu d'une action, selectionnable a la souris.

    MASQUE tant qu'il n'a rien a dire : un cadre vide sous chaque bouton
    donnait a croire qu'il manquait quelque chose.
    """
    label = QLabel(contenu)
    label.setWordWrap(True)
    label.setProperty("role", ROLE_ETAT)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setVisible(bool(contenu))
    return label


def dire(label, contenu):
    """Renseigne un compte rendu, et le fait apparaitre ou disparaitre."""
    label.setText(contenu)
    label.setVisible(bool(contenu))


def formulaire(parent=None):
    """QFormLayout au rythme commun ; les champs occupent toute la largeur."""
    f = QFormLayout(parent) if parent is not None else QFormLayout()
    f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    f.setHorizontalSpacing(12)
    f.setVerticalSpacing(7)
    return f


# ---------------------------------------------------------------------------
# Aide affichee dans la fenetre. Reprend le mode operatoire de la note
# methodologique : une aide qu'il faut aller chercher ailleurs n'est pas lue.
#
# Elle a ete RAMENEE A CE QUI SE DECIDE DEVANT L'ECRAN. Tout ce qui explique
# pourquoi la methode est ainsi — hypotheses de validite, justification des
# tolerances, comparaison au guide — est dans la note, et l'y redire en
# double garantissait qu'un des deux textes finisse par mentir. Une aide
# qu'on fait defiler n'est pas lue davantage qu'une aide absente.
# ---------------------------------------------------------------------------

AIDE_HTML = """
<h2>Calage des apports — mode opératoire</h2>

<p>L'outil ajuste, un par un et de l'amont vers l'aval, les hydrogrammes
injectés dans un modèle 2D HEC-RAS pour que le débit calculé à chaque section
de contrôle reproduise un hydrogramme cible.</p>

<h3>À trancher avant de commencer</h3>
<ul>
<li><b>Ordre amont → aval strict ?</b> La méthode ne s'applique pas à un
réseau bouclé, où un apport alimenterait plusieurs sections par des chemins
distincts.</li>
<li><b>Durée d'un calcul complet ?</b> C'est ce chiffre qui dimensionne
tout : compter 3 à 5 calculs par apport.</li>
<li><b>Hydrogrammes cibles disponibles</b> pour chaque section ?</li>
</ul>

<h3>Le déroulement, onglet par onglet</h3>
<ol>
<li><b>Onglet 1 — Modèle.</b> Dossier du projet, plan de référence, puis
<i>Charger les couches du modèle</i> : sections, injections et maillage
s'affichent sur la carte. Y dessiner les sections de contrôle qui manquent —
sans elles, le calage n'a aucun endroit où lire un débit. Elles sont écrites
dans la géométrie au clic sur <i>Composer et contrôler</i>, et un apport créé
reçoit du même coup son hydrogramme dans le fichier Unsteady&nbsp;Flow, sinon
il n'apporterait rien. La fenêtre de simulation n'est à corriger que si
l'Unsteady&nbsp;Flow retenu couvre une <b>autre période</b> que le plan de
référence.</li>
<li><b>Onglet 2 — Axe hydraulique.</b> Une polyligne unique, de l'amont vers
l'aval, en projection métrique : elle donne les PK et le profil en long. Puis
la précision attendue.</li>
<li><b>Onglet 3 — Résultats.</b> Dossier de résultats et dossier de suivi.</li>
<li><b>Onglet 4 — Lancer.</b> Renseigner les cibles dans le classeur, choisir
le premier apport à caler, puis lancer. Le calage tourne en arrière-plan :
QGIS reste utilisable.</li>
<li><b>Onglet 5 — Suivi.</b> Où en est le calcul, apport par apport, rafraîchi
tout seul. C'est là qu'on revient pendant les heures que dure un calage.</li>
</ol>

<h3>Comment l'apport est ajusté</h3>
<p>Une seule règle, appliquée ligne à ligne, et c'est exactement le calcul
manuel de la note méthodologique :</p>
<p align="center"><tt><b>apport(n+1) = max( 0 , apport(n) + [ cible(t−Δt) −
section(t) ] )</b></tt></p>
<p>On n'ajoute que ce qui manque. Le <b>zéro</b> est la seule contrainte de
forme : un apport ne peut qu'ajouter du débit, jamais en retirer.</p>

<p><b>Δt, le décalage de propagation.</b> Il vaut <i>instant du pic calculé
moins instant du pic cible</i>, se mesure <b>une seule fois</b> sur le calcul
de référence — tous les apports à zéro — puis reste figé pour tous les essais.
C'est la <b>cible</b> qui en est décalée avant la comparaison, jamais le
calcul : les deux écritures donnent la même courbe translatée de Δt, et la
seconde fait tomber la correction à côté de la pointe qu'elle vise. Δt est
<b>signalé, pas corrigé</b> — on renonce à reproduire l'instant du pic plutôt
que d'injecter du débit qui ne compenserait qu'un retard de propagation, et un
Δt important ne fait pas échouer un calage juste par ailleurs.</p>

<p>L'apport n'a pas à être lisse ni « physique » : ce n'est pas un hydrogramme
observé mais la <b>commande</b> d'un asservissement, et seul compte le débit
obtenu à la section. Il est calculé sur <b>toute la durée simulée</b> : la
fenêtre de l'événement principal ne restreint que le <i>jugement</i> et les
<i>figures</i>, jamais ce qui est injecté.</p>

<h3>Comment lire le résultat</h3>
<p>Tout est donné en <b>pourcentage d'atteinte de la cible</b>. Trois
exigences, satisfaites <b>en même temps</b> :</p>
<ul>
<li><b>Volume</b> — la quantité d'eau totale ;</li>
<li><b>Débit de pointe</b> — le maximum, dimensionnant pour un aléa ;</li>
<li><b>Forme</b> — concordance d'au moins 97&nbsp;%, <i>après</i> recalage
temporel.</li>
</ul>
<p>Les deux premières tolérances se règlent <b>à l'onglet 2</b> ; à défaut
elles valent 5&nbsp;% sur le volume et 2&nbsp;% sur la pointe. Une bande large
n'est pas neutre : un essai peut s'y arrêter alors que la méthode irait plus
loin. Mesuré sur un cas de recette — à ±5&nbsp;% sur la pointe, deux sections
s'arrêtaient à 95&nbsp;% ; resserrées à ±2&nbsp;%, les mêmes atteignaient
98,8 et 100,0&nbsp;%.</p>
<p>Chaque grandeur porte sa propre tolérance : un indicateur unique peut
rester flatteur alors qu'une grandeur dérive — mesuré sur un cas réel, 0,97
pour un débit de pointe à 53&nbsp;% de la cible. Le décalage temporel, lui,
n'est pas un critère mais un garde-fou : important sans défaut de volume ni
de forme, il désigne un problème de propagation que l'apport ne corrigerait
pas. C'est le <b>meilleur</b> essai qui est conservé, jamais le dernier.</p>
<p>Le classeur d'itérations, écrit dans le dossier de suivi, se <b>refait à la
main</b> : par apport, un bloc de quatre colonnes par essai — la section
obtenue, la cible décalée, leur écart, l'apport injecté — et l'apport d'un
bloc est l'apport du précédent plus son écart, ramené à zéro s'il devient
négatif.</p>

<h3>Quand la cible est hors d'atteinte</h3>
<p>Un apport ne peut qu'<b>ajouter</b> du débit : si la section reçoit déjà
plus que la cible sur toute la durée, aucun apport positif ne l'y ramène. Ce
refus est prononcé <b>avant le moindre calcul</b>, donc sans rien coûter, et
le calage le dit avec sa cause au lieu d'itérer en vain.</p>
<p>La cause la plus fréquente est un décalage d'origine des temps entre la
cible et l'événement du modèle ; il se reconnaît à ceci que le volume
s'éloigne de la cible à mesure que le débit de pointe s'en approche. Vérifier
alors le Δt annoncé en tête de chaque bloc du classeur d'itérations : c'est
le seul nombre qui rende la colonne d'écart reproductible.</p>
<p>Un excédent que la section porte déjà sur une <i>partie</i> de l'événement
n'arrête rien, mais il ne s'en va pas non plus : le zéro empêche de le
retirer, et le volume ne peut plus repasser sous 100&nbsp;%. Si cet excédent
dépasse à lui seul la tolérance de volume, la concordance est impossible par
construction — mesuré sur un cas de recette, 2,12&nbsp;% du volume cible.</p>

<h3>Nommer les objets</h3>
<p>Les noms doivent correspondre <b>exactement</b> à ceux de la géométrie
HEC-RAS : c'est par eux que le classeur, l'Unsteady&nbsp;Flow et les résultats
se rejoignent. La convention ne sert donc qu'à la création, et ne renomme
jamais l'existant : <b>A1, A2…</b> apports à caler, <b>SC1, SC2…</b> sections
de contrôle, <b>IN_…</b> entrées permanentes et <b>OUT_…</b> exutoires, ces
deux dernières n'étant pas calées.</p>
<p>Le numéro d'une section ne reprend pas celui de son apport : l'appariement
est <b>géométrique</b> — chaque section prend la première injection en amont
d'elle — et le lien réellement calculé s'affiche à l'onglet 4. Une injection
sans section en aval n'est pas calée, ce qui est normal ; une section sans
injection en amont est en revanche une erreur.</p>

<h3>Un apport créé part de zéro</h3>
<p>Il reçoit un hydrogramme <b>nul</b>, sur la base de temps du modèle. Rien
à saisir : le calage commence par un calcul sans les apports, mesure ce que
chaque section reçoit déjà, et la première estimation est la différence avec
la cible. Le classeur ne demande donc aucune forme d'apport — on y saisit ce
qu'on veut <i>obtenir à la section</i>, pas ce qu'on injecte.</p>

<h3>Pièges à connaître</h3>
<ul>
<li>Le <b>signe du débit</b> à une section dépend du sens où la ligne a été
tracée. Il est ramené en convention positive vers l'aval, et l'inversion est
signalée.</li>
<li>Une <b>ligne d'injection</b> n'a pas à coïncider avec le périmètre du
maillage : HEC-RAS la rattache aux faces les plus proches, et un écart de
l'ordre de la maille est normal.</li>
<li>Deux plans peuvent <b>partager la géométrie sans partager
l'Unsteady&nbsp;Flow</b> : une injection écrite en visant l'un est alors
absente pour l'autre, et la ligne n'apporte aucun débit.</li>
<li>Les <b>calculs longs</b> ne tournent jamais dans QGIS : HEC-RAS et QGIS
ne peuvent pas partager la même bibliothèque HDF5.</li>
</ul>

<h3>Sur un autre poste</h3>
<p>Deux emplacements, cherchés tout seuls ; le groupe <i>Paramètres du
poste</i> ci-dessous ne sert que s'ils restent introuvables : la <b>chaîne de
calage</b> (le dossier de <tt>pont_hecras.py</tt>) et l'<b>interpréteur
HEC-RAS</b> (un <tt>python.exe</tt> disposant de ras-commander et h5py,
vérifié au moment où on le désigne). Ni QGIS ni HEC-RAS n'ont à être
désignés — le premier exécute le plugin, le second est lancé par
ras-commander d'après la version lue dans le modèle.</p>

<p><i>Hypothèses de validité, justification des tolérances et livrables :
note méthodologique « methodologie_calage_amont_aval.docx », dans le dossier
de la chaîne — le détail de la correction et de Δt y figure aux § 1.4 et 1.5.
Pilotage HEC-RAS par
<b>ras-commander v0.99.1</b> (CLB Engineering Corporation) ; ses auteurs
demandent d'être cités, ce que la note de synthèse produite par la chaîne fait
d'office.</i></p>
"""


# ---------------------------------------------------------------------------
# Restitution d'un controle — partagee par la fenetre de parametrage et par
# l'action « Controler l'implantation ».
#
# Les deux voies rendaient le meme rapport, chacune avec sa copie du code de
# mise en forme. Deux copies, c'est une regle qu'on corrige d'un cote sans
# s'en apercevoir de l'autre — exactement ce que le plugin s'interdit par
# ailleurs en ne detenant aucune regle de controle en propre.
# ---------------------------------------------------------------------------

def trier_anomalies(anomalies):
    """Separe les anomalies en erreurs, avertissements et informations."""
    erreurs = [m for n, m in anomalies if n == "ERREUR"]
    informations = [m for n, m in anomalies if n == "INFO"]
    avertissements = [m for n, m in anomalies if n not in ("ERREUR", "INFO")]
    return erreurs, avertissements, informations


def texte_rapport_controle(anomalies, tableau):
    """Rapport detaille d'un controle de paquet, pret a etre affiche."""
    erreurs, avertissements, informations = trier_anomalies(anomalies)
    rapport = []
    if erreurs:
        rapport.append("ERREURS — bloquantes :\n  • " + "\n  • ".join(erreurs))
    if avertissements:
        rapport.append("Avertissements :\n  • " + "\n  • ".join(avertissements))
    if informations:
        rapport.append("Pour information :\n  • " + "\n  • ".join(informations))
    if not anomalies:
        rapport.append("Aucune anomalie : le paquet peut être exploité.")
    if tableau is not None:
        rapport.append("\nPK calculés :\n" + tableau.to_string(index=False))
    return "\n\n".join(rapport)


def rendre_redimensionnable(boite, largeur=900, hauteur=420):
    """
    Rend une QMessageBox etirable, et son detail lisible.

    Qt fige la taille d'une QMessageBox : sa disposition porte une contrainte
    de taille FIXE, et la fenetre n'a pas de poignee. Le rapport de contrôle
    s'y lisait donc par une lucarne de quelques lignes, alors qu'il compte le
    tableau des PK — plusieurs dizaines de lignes larges, dont la lecture est
    justement ce pour quoi la fenêtre s'ouvre.

    Trois gestes, tous necessaires : lever la contrainte, sans quoi la
    fenetre revient a sa taille de contenu ; poser un separateur invisible
    sur toute la largeur de la grille, sans quoi elle se retracte aussitot ;
    donner une taille minimale a la zone de detail, qui autrement reste plate
    quand la fenetre grandit.

    A appeler APRES setDetailedText() : c'est lui qui cree la zone de detail.
    Retourne la boite, pour pouvoir s'enchainer.
    """
    boite.setSizeGripEnabled(True)
    grille = boite.layout()
    if grille is not None:
        grille.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        grille.addItem(
            QSpacerItem(largeur, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding),
            grille.rowCount(), 0, 1, grille.columnCount())
    detail = boite.findChild(QTextEdit)
    if detail is not None:
        detail.setMinimumSize(largeur, hauteur)
        detail.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Le tableau des PK est aligne a la colonne : une police proportionnelle
        # en decale les colonnes et le rend illisible.
        detail.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
    return boite


def afficher_pk_sur_carte(chemins, sens, crs_defaut="EPSG:2154"):
    """
    Ajoute a la carte les couches de PK des sections et des injections.

    Montrer une incoherence d'ordre A L'ENDROIT OU ELLE EST est le seul
    apport du plugin qu'un rapport texte ne peut pas remplacer.

    chemins : dict a cles « sections », « apports », « axe ».
    """
    if not chemins.get("axe"):
        return []
    ajoutees = []
    for libelle, cle in (("Sections — PK", "sections"),
                         ("Injections — PK", "apports")):
        if not chemins.get(cle):
            continue
        gdf = noyau.pk_pour_affichage(chemins[cle], chemins["axe"], sens=sens)
        couche = gdf_vers_couche(
            gdf, libelle, gdf.crs.to_string() if gdf.crs else crs_defaut)
        QgsProject.instance().addMapLayer(couche)
        ajoutees.append(couche)
    return ajoutees


# ---------------------------------------------------------------------------
# Fenetre de parametrage — six onglets
#
# Les rangs sont NOMMES : deux methodes basculent d'onglet apres une action
# (composer amene a l'onglet 4, lancer amene au suivi), et un indice ecrit en
# dur y devenait faux au premier onglet insere — sans que rien ne le signale,
# puisque Qt affiche simplement l'onglet voisin.
# ---------------------------------------------------------------------------

ONGLET_MODELE = 0
ONGLET_LANCER = 3
ONGLET_SUIVI = 4
# Les trois autres rangs n'ont pas de nom : aucun code n'y renvoie, et une
# constante que personne ne lit finit par designer autre chose que ce qu'elle
# dit. La suite d'essais verifie que ces trois-la tombent bien sur leur onglet.


class DialogueParametrage(QDialog):
    """
    Fenetre unique, en six onglets, dans l'ordre ou les choix se prennent.

      1. Modèle — projet, plan de reference, geometrie et Unsteady Flow (ceux
         du plan ou d'autres), zone 2D, fenetre de simulation. Y CHARGE LES
         COUCHES EXISTANTES de la geometrie en couches QGIS EDITABLES, pretes
         a etre dessinees ou completees par-dessus.
      2. Profil en long — l'axe hydraulique (PK et profil) et la precision
         attendue.
      3. Résultats — ou ecrire le paquet, les resultats finaux et le suivi.
      4. Lancer — ce que la derniere composition a produit, combien de cibles
         restent a saisir, les apports a determiner et le lancement.
         Recomposer au fil de l'ajustement des couches est le cas NORMAL : les
         cibles saisies a la main sont preservees d'une composition a l'autre.
      5. Suivi — ou en est le calcul, rafraichi tout seul tant que cet onglet
         est affiche.
      6. Aide — mode operatoire et diagnostic de l'environnement.

    Le bouton « Composer et contrôler », permanent en bas de la fenetre,
    ECRIT D'ABORD les couches de l'onglet 1 dans la geometrie HEC-RAS —
    TOUJOURS EN REMPLACANT l'objet de meme nom deja present, sections comme
    injections : ce que QGIS montre fait foi, il n'y a plus de choix a faire
    ni de bouton a part (_ecrire_dans_geometrie) — puis compose les fichiers
    et lance le controle complet.
    """

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle(f"{NOM_PLUGIN} — {EDITEUR}")
        self.setWindowIcon(QIcon(os.path.join(DOSSIER, "icon.png")))
        # Assez large pour que les chemins de fichiers ne soient pas tronques,
        # et redimensionnable : l'onglet 1 est dense.
        self.resize(880, 720)
        self.setMinimumSize(720, 520)

        self.info_projet = None      # resultat de noyau.lister_projet_hecras
        self.version_hecras = None   # lue dans les fichiers, jamais saisie
        self.appariement = None      # apports <-> sections, deduit des PK
        self.crs_modele = None       # authid, ex. "EPSG:2154"
        self.couche_sections = None
        self.couche_injections = None
        self.couche_perimetre = None
        self.couche_maillage = None      # maillage natif QGIS/MDAL, visuel
        self.classeur = None         # rempli si la composition reussit
        self.paquet = {}

        self.setStyleSheet(STYLE_ISL)
        agencement = QVBoxLayout(self)
        agencement.setSpacing(10)
        agencement.setContentsMargins(12, 12, 12, 12)

        agencement.addWidget(self._bandeau())
        self.onglets = QTabWidget()
        self.onglets.setDocumentMode(True)      # onglets sobres, moins encadres
        # Le gras est pose sur la POLICE de la barre, pas dans la feuille de
        # style : Qt calcule la largeur des onglets d'apres la police du
        # widget, et un gras purement decoratif faisait deborder les libelles.
        police_onglets = self.onglets.tabBar().font()
        police_onglets.setBold(True)
        self.onglets.tabBar().setFont(police_onglets)
        agencement.addWidget(self.onglets)
        # Chaque onglet vit dans une zone defilante : un ecran d'ordinateur
        # portable ne montrerait sinon qu'une partie de l'onglet 1, et les
        # boutons du bas seraient repousses hors de l'ecran.
        # Libelles COURTS : mis en gras a la selection, des intitules longs
        # debordaient de la barre, qui se mettait a defiler et tronquait le
        # premier onglet. Le detail passe en infobulle, ou il ne coute rien.
        for page, titre, infobulle in (
            (self._onglet_modele(), "1. Modèle",
             "Projet HEC-RAS, plan de référence, zone 2D, chargement des "
             "couches existantes et écriture des nouveaux objets."),
            (self._onglet_profil(), "2. Profil en long",
             "Axe hydraulique, sens, PK d'origine, précision attendue et "
             "nombre maximal d'essais."),
            (self._onglet_resultats(), "3. Résultats",
             "Dossiers de sortie et de suivi, relecture d'un hydrogramme "
             "déjà calculé, résumé de la configuration."),
            (self._onglet_validation(), "4. Lancer",
             "Correspondance sections / injections, hydrogrammes cibles "
             "restant à saisir, apports à déterminer et lancement du calage."),
            (self._onglet_suivi(), "5. Suivi",
             "Où en est le calage : apport en cours, essai, avancement, "
             "temps restant, et ce qui s'est passé quand il s'arrête."),
            (self._onglet_aide(), "Aide",
             "Mode opératoire, pièges connus et diagnostic de "
             "l'environnement."),
        ):
            zone = QScrollArea()
            zone.setWidgetResizable(True)
            zone.setFrameShape(QFrame.Shape.NoFrame)
            zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            zone.setWidget(page)
            indice = self.onglets.addTab(zone, titre)
            self.onglets.setTabToolTip(indice, infobulle)
        # Le suivi ne se relit QUE lorsqu'il est a l'ecran (voir _onglet_suivi) :
        # ce signal lui redonne la main des qu'on y revient, sans quoi il
        # afficherait l'etat vieux de la derniere visite pendant deux secondes.
        self.onglets.currentChanged.connect(self._changer_onglet)

        # Fil conducteur permanent : a tout moment on sait ou on en est et ce
        # qui vient ensuite, sans avoir a parcourir les onglets.
        self.label_fil = QLabel()
        self.label_fil.setObjectName("filConducteur")
        self.label_fil.setWordWrap(True)
        self.label_fil.setTextFormat(Qt.TextFormat.RichText)
        agencement.addWidget(self.label_fil)

        boutons = QHBoxLayout()
        boutons.setSpacing(8)
        boutons.addStretch(1)
        bouton_composer = QPushButton("Composer et contrôler")
        bouton_composer.setObjectName("boutonPrincipal")
        bouton_composer.setDefault(True)         # action principale, mise en avant
        bouton_composer.setAutoDefault(True)
        bouton_composer.setMinimumWidth(190)
        bouton_composer.setToolTip(
            "Écrit d'abord les sections et injections de l'onglet 1 dans la "
            "géométrie HEC-RAS (en remplaçant tout objet de même nom déjà "
            "présent), puis les shapefiles et le classeur, puis lance tous "
            "les contrôles et reporte les anomalies sur la carte.")
        bouton_composer.clicked.connect(self._composer_et_controler)
        bouton_fermer = QPushButton("Fermer")
        bouton_fermer.setMinimumWidth(90)
        bouton_fermer.clicked.connect(self.accept)
        boutons.addWidget(bouton_composer)
        boutons.addWidget(bouton_fermer)
        agencement.addLayout(boutons)

        self._maj_resume()
        self._maj_fil()

    def _bandeau(self):
        """
        En-tete : pictogramme du domaine, titre, sous-titre, signature, et un
        filet aux couleurs de la charte. Rappelle en permanence ce que fait
        l'outil et pour qui — sur deux lignes de texte, pas davantage.

        La signature est A DROITE et non sous le titre : elle y tient sans
        ajouter de ligne, et l'en-tete gagne la place d'autant.
        """
        cadre = QWidget()
        ligne = QHBoxLayout(cadre)
        ligne.setContentsMargins(0, 0, 0, 2)
        ligne.setSpacing(12)

        picto = QLabel()
        chemin_icone = os.path.join(DOSSIER, "icon.png")
        if os.path.exists(chemin_icone):
            picto.setPixmap(QIcon(chemin_icone).pixmap(42, 42))
        ligne.addWidget(picto, 0, Qt.AlignmentFlag.AlignVCenter)

        textes = QVBoxLayout()
        textes.setSpacing(2)
        titre = QLabel(NOM_PLUGIN)
        titre.setStyleSheet(
            f"font-size: 15pt; font-weight: bold; color: {ISL_TEAL};")
        sous_titre = QLabel(
            "Ajustement séquentiel des apports amont sur hydrogrammes cibles "
            "aval — modèles 2D HEC-RAS")
        sous_titre.setWordWrap(True)
        sous_titre.setStyleSheet(f"color: {ISL_ARDOISE};")
        textes.addWidget(titre)
        textes.addWidget(sous_titre)
        ligne.addLayout(textes, 1)

        # La signature figurait dans les seules metadonnees, invisibles une
        # fois le plugin installe. Un outil interne doit dire de qui il vient.
        signature = QLabel(EDITEUR.upper())
        signature.setStyleSheet(
            f"font-size: 8pt; letter-spacing: 2px; color: {ISL_ARDOISE};")
        ligne.addWidget(signature, 0, Qt.AlignmentFlag.AlignBottom)

        enveloppe = QWidget()
        v = QVBoxLayout(enveloppe)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(7)
        v.addWidget(cadre)
        # Filet degrade teal → ardoise : la frise de la charte, ramenee a
        # une ligne. Un aplat uni tenait la meme place sans rien evoquer.
        filet = QFrame()
        filet.setFixedHeight(3)
        filet.setStyleSheet(
            f"border: none; background-color: qlineargradient("
            f"x1:0, y1:0, x2:1, y2:0, stop:0 {ISL_TEAL}, "
            f"stop:0.55 {ISL_ARDOISE}, stop:1 {ISL_ARDOISE_CLAIR});")
        v.addWidget(filet)
        return enveloppe

    def _maj_fil(self):
        """
        Fil conducteur affiche en bas de la fenetre : ou en est-on, et quoi
        ensuite. Chaque etape est franchie ou non, sans jamais deviner —
        l'etat vient de ce qui existe reellement, pas d'un compteur interne.
        """
        etapes = [
            ("Modèle chargé", self.info_projet is not None
             and couche_vivante(self.couche_sections) is not None),
            ("Axe hydraulique",
             couche_vivante(self.combo_axe.currentLayer()) is not None),
            ("Dossier de sortie", bool(self.edit_dossier_sortie.text().strip())),
            ("Paquet composé", bool(self.classeur)),
        ]
        # Ce qui est fait passe au vert et en gras, ce qui reste au gris
        # clair : l'etat se lit d'un coup d'oeil, sans lire les libelles.
        faits = [
            (f"<span style='color:{ISL_VERT}'><b>✔ {nom}</b></span>" if ok
             else f"<span style='color:{ISL_ARDOISE_CLAIR}'>○ {nom}</span>")
            for nom, ok in etapes]
        suivante = next((nom for nom, ok in etapes if not ok), None)
        fin = (f"<b style='color:{ISL_VERT}'>tout est prêt</b> "
               f"<span style='color:{ISL_ARDOISE}'>— renseigner les cibles "
               f"puis lancer (onglet 4)</span>" if suivante is None
               else f"<span style='color:{ISL_ARDOISE}'>étape suivante : "
                    f"<b>{suivante}</b></span>")
        separateur = f"<span style='color:{ISL_ARDOISE_CLAIR}'> · </span>"
        self.label_fil.setText(separateur.join(faits)
                               + f"{separateur}&nbsp; {fin}")

    # --- Onglet 1 : Modele HEC-RAS ------------------------------------------

    def _onglet_modele(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)

        groupe_projet = QGroupBox("Projet HEC-RAS")
        f = formulaire(groupe_projet)
        ligne = QHBoxLayout()
        ligne.setSpacing(6)
        self.edit_dossier_hecras = QLineEdit()
        self.edit_dossier_hecras.setPlaceholderText(
            "Dossier contenant le fichier .prj du projet")
        bouton_parcourir = QPushButton("Parcourir…")
        bouton_parcourir.clicked.connect(self._parcourir_dossier_hecras)
        ligne.addWidget(self.edit_dossier_hecras, 1)
        ligne.addWidget(bouton_parcourir)
        f.addRow("Dossier du projet :", ligne)
        # La version de HEC-RAS n'est PAS demandee : elle est ecrite dans les
        # fichiers du modele (« Program Version= »), et la faire saisir ne
        # pourrait qu'introduire une erreur. Elle est lue et affichee avec le
        # projet, a titre d'information.
        self.label_nom_projet = QLabel("(non chargé)")
        self.label_nom_projet.setWordWrap(True)
        f.addRow("Projet détecté :", self.label_nom_projet)
        v.addWidget(groupe_projet)

        groupe_plan = QGroupBox("Plan, géométrie et Unsteady Flow")
        f2 = formulaire(groupe_plan)
        self.combo_plan = QComboBox()
        self.combo_plan.currentIndexChanged.connect(self._changer_plan)
        f2.addRow("Plan de référence :", self.combo_plan)

        self.radio_du_plan = QRadioButton(
            "Utiliser la géométrie et l'Unsteady Flow de ce plan")
        self.radio_override = QRadioButton(
            "Choisir une géométrie et un Unsteady Flow différents")
        self.radio_du_plan.setChecked(True)
        self.radio_du_plan.toggled.connect(self._maj_mode_override)
        f2.addRow(self.radio_du_plan)
        f2.addRow(self.radio_override)

        self.combo_geometrie = QComboBox()
        self.combo_unsteady = QComboBox()
        self.combo_geometrie.setEnabled(False)
        self.combo_unsteady.setEnabled(False)
        self.combo_geometrie.currentIndexChanged.connect(self._maj_resume)
        self.combo_unsteady.currentIndexChanged.connect(self._maj_resume)
        f2.addRow("Géométrie :", self.combo_geometrie)
        f2.addRow("Unsteady Flow :", self.combo_unsteady)

        self.combo_zone_2d = QComboBox()
        self.combo_zone_2d.currentIndexChanged.connect(self._maj_resume)
        f2.addRow("Zone d'écoulement 2D :", self.combo_zone_2d)
        v.addWidget(groupe_plan)

        # FENETRE DE SIMULATION.
        #
        # Le plan de calcul est toujours un clone du plan de référence : il en
        # hérite donc toutes ses tolérances numériques, ce qui est le bon
        # défaut. Mais substituer un Unsteady Flow couvrant une AUTRE période
        # ne déplace pas la fenêtre du plan — HEC-RAS calculerait alors sur
        # une période sans rapport avec les hydrogrammes, sans rien signaler.
        # D'où ce groupe. Il reste TOUJOURS saisissable : la fenêtre du plan
        # de référence peut aussi être plus large que l'événement à caler, et
        # la resserrer est le seul levier qui réduise le coût d'un calcul —
        # lequel se compte en heures, et se paie trois à cinq fois par apport.
        # Ce qui a été saisi n'est transmis que s'il DIFFÈRE du plan.
        self.groupe_fenetre = QGroupBox("Fenêtre de simulation")
        self.groupe_fenetre.setToolTip(
            "Le plan de calcul est un clone du plan de référence et en hérite "
            "la fenêtre. Substituer un Unsteady Flow couvrant une autre "
            "période ne la déplace pas : HEC-RAS calculerait à côté des "
            "hydrogrammes, sans rien signaler.")
        vf = QVBoxLayout(self.groupe_fenetre)
        vf.setSpacing(8)
        vf.addWidget(texte_aide(
            "Reprise du plan de référence — à corriger seulement si "
            "l'Unsteady Flow retenu couvre une autre période."))

        # Debut et fin sur UNE ligne, intervalles sur DEUX : six champs
        # empiles occupaient a eux seuls la moitie de l'onglet, alors qu'on
        # n'y touche presque jamais.
        self.edit_sim_debut = QLineEdit()
        self.edit_sim_fin = QLineEdit()
        for champ, exemple in ((self.edit_sim_debut, "13OCT2014,00:00"),
                               (self.edit_sim_fin, "14OCT2014,04:00")):
            champ.setPlaceholderText(exemple)
            champ.textChanged.connect(self._maj_resume)
        grille = QGridLayout()
        grille.setContentsMargins(0, 0, 0, 0)
        grille.setHorizontalSpacing(12)
        grille.setVerticalSpacing(7)
        grille.addWidget(QLabel("Début :"), 0, 0)
        grille.addWidget(self.edit_sim_debut, 0, 1)
        grille.addWidget(QLabel("Fin :"), 0, 2)
        grille.addWidget(self.edit_sim_fin, 0, 3)

        self.edits_intervalles = {}
        for rang, (cle, libelle, exemple) in enumerate((
                ("intervalle_calcul", "Calcul", "1SEC"),
                ("intervalle_sortie", "Sortie", "1MIN"),
                ("intervalle_instantane", "Détaillée", "1MIN"),
                ("intervalle_mapping", "Cartographie", "1MIN"))):
            champ = QLineEdit()
            champ.setPlaceholderText(exemple)
            champ.textChanged.connect(self._maj_resume)
            grille.addWidget(QLabel(f"{libelle} :"),
                             1 + rang // 2, 2 * (rang % 2))
            grille.addWidget(champ, 1 + rang // 2, 2 * (rang % 2) + 1)
            self.edits_intervalles[cle] = champ
        grille.setColumnStretch(1, 1)
        grille.setColumnStretch(3, 1)
        vf.addLayout(grille)
        vf.addWidget(texte_aide(
            "Format JJMMMAAAA,HH:MM — intervalles en SEC, MIN ou HOUR."))

        self.label_fenetre = texte_etat()
        vf.addWidget(self.label_fenetre)
        v.addWidget(self.groupe_fenetre)

        groupe_charger = QGroupBox("Couches existantes de la géométrie")
        v3 = QVBoxLayout(groupe_charger)
        v3.setSpacing(8)
        bouton_charger = QPushButton(
            "Charger les couches du modèle (sections, injections, emprise)")
        bouton_charger.setToolTip(
            "Ajoute à la carte, en couches ÉDITABLES, ce que la géométrie "
            "contient déjà. C'est là-dessus qu'on dessine les objets "
            "manquants.")
        bouton_charger.clicked.connect(self._charger_couches_modele)
        v3.addWidget(bouton_charger)
        self.label_couches = texte_etat()
        v3.addWidget(self.label_couches)
        v3.addWidget(texte_aide(
            "Les sections et injections existantes arrivent sur la carte, "
            "prêtes à être complétées."))
        v.addWidget(groupe_charger)

        # Ecrite AUTOMATIQUEMENT au clic sur « Composer et controler », pas
        # via une action a part : le fichier .gXX, la zone 2D et le fichier
        # Unsteady sont deja choisis juste au-dessus, et il faut que les
        # sections soient DANS le modele avant que le paquet soit compose,
        # sinon le calage n'a rien a relire. Source UNIQUE : les couches
        # chargees ci-dessus (« Charger les couches du modele »), dessinees
        # ou completees par-dessus dans QGIS — ce que QGIS montre fait foi,
        # et REMPLACE systematiquement l'objet de meme nom deja present dans
        # la geometrie HEC-RAS, sections comme injections.
        groupe_ecrire = QGroupBox("Écriture dans la géométrie")
        f3b = formulaire(groupe_ecrire)
        explication = QLabel(
            "<b>Indispensable tant que les sections de contrôle n'existent "
            "pas dans le modèle</b> — le calage n'aurait aucun endroit où "
            "lire un débit. Les dessiner ou les compléter dans les couches "
            "chargées ci-dessus : elles sont écrites automatiquement dans "
            "la géométrie HEC-RAS — en remplaçant tout objet de même nom "
            "déjà présent — au clic sur « Composer et contrôler ».")
        explication.setWordWrap(True)
        f3b.addRow(explication)
        f3b.addRow(texte_aide(CONVENTION_NOMS, INFOBULLE_CONVENTION))

        # La pente de la ligne d'energie n'est PLUS saisie ici : elle depend de
        # chaque apport, pas du lot. A la creation, la valeur provisoire
        # ci-dessous suffit — le calage la remplace par celle du classeur, ou
        # a defaut par la pente locale du fond (onglet 2, « Paramètres du
        # calage »).
        f3b.addRow(texte_aide(
            "Un apport créé reçoit son hydrogramme dans l'Unsteady Flow, et "
            "sa pente vient du classeur ou du profil en long (onglet 2)."))

        self.label_ecriture = texte_etat()
        f3b.addRow(self.label_ecriture)
        v.addWidget(groupe_ecrire)

        v.addStretch(1)
        return page

    def _groupe_copies_de_travail(self):
        groupe = QGroupBox("Apports à déterminer")
        groupe.setToolTip(
            "Quels apports ce calage doit traiter : tous, ou seulement à "
            "partir de celui choisi ici.")
        f = formulaire(groupe)

        # Les plans d'etape etant conserves, un calage interrompu au
        # vingtieme apport repart du plan de l'apport precedent : les apports
        # amont sont tenus pour cales, ni remis a zero ni retouches.
        self.combo_premier_apport = QComboBox()
        self.combo_premier_apport.setToolTip(
            "Vide : tous les apports sont calés, de l'amont vers l'aval.\n"
            "Sinon, le calage démarre à cet apport et repart du plan "
            "« Apport_<précédent> » : les apports situés en amont sont tenus "
            "pour calés et ne sont pas retouchés.\n"
            "Utile pour reprendre un calage interrompu sans refaire ce qui "
            "était déjà bon.")
        # Le nom de l'apport est porte par la DONNEE de l'entree, pas deduit du
        # libelle affiche : le decouper redonnait un nom faux des qu'il
        # contenait la fleche du libelle.
        self.combo_premier_apport.addItem("— tous, de l'amont vers l'aval —",
                                          "")
        self.combo_premier_apport.currentIndexChanged.connect(
            self._dire_premier_apport)
        f.addRow("Premier apport à caler :", self.combo_premier_apport)
        self.label_premier_apport = texte_etat()
        f.addRow(self.label_premier_apport)
        return groupe

    def _parcourir_dossier_hecras(self):
        dossier = QFileDialog.getExistingDirectory(
            self, "Dossier du projet HEC-RAS")
        if not dossier:
            return
        self.edit_dossier_hecras.setText(dossier)
        self._charger_projet_hecras(dossier)

    def _charger_projet_hecras(self, dossier):
        try:
            self.info_projet = noyau.lister_projet_hecras(dossier)
        except Exception as e:
            journaliser("Lecture du projet HEC-RAS", e)
            QMessageBox.critical(self, "Projet HEC-RAS", str(e))
            return

        # Version lue dans les fichiers, la plus recente en cas de melange :
        # un projet ancien repris avec une version recente en contient
        # plusieurs, et seule la plus recente sait toutes les relire.
        self.version_hecras, versions_vues = noyau.version_hecras_du_projet(dossier)
        installees = noyau.versions_hecras_installees()
        if not self.version_hecras:
            texte_version = " — version HEC-RAS illisible dans les fichiers"
        elif installees and self.version_hecras not in installees:
            texte_version = (f" — écrit avec HEC-RAS {self.version_hecras}, "
                             f"NON INSTALLÉE ici ({', '.join(installees)})")
        else:
            texte_version = f" — HEC-RAS {self.version_hecras}"
        if len(versions_vues) > 1:
            texte_version += (f" (fichiers écrits avec "
                              f"{', '.join(sorted(versions_vues))})")
        self.label_nom_projet.setText(
            self.info_projet["nom_projet"] + texte_version)
        self.combo_plan.clear()
        for p in self.info_projet["plans"]:
            self.combo_plan.addItem(f"p{p['numero']} — {p['titre']}", p)
        self.combo_geometrie.clear()
        for g in self.info_projet["geometries"]:
            self.combo_geometrie.addItem(f"g{g['numero']} — {g['titre']}", g)
        self.combo_unsteady.clear()
        for u in self.info_projet["unsteady"]:
            self.combo_unsteady.addItem(f"u{u['numero']} — {u['titre']}", u)
        self._remplir_fenetre_depuis_plan()
        self._maj_resume()

    def _maj_mode_override(self, _coche):
        surcharge = self.radio_override.isChecked()
        self.combo_geometrie.setEnabled(surcharge)
        self.combo_unsteady.setEnabled(surcharge)
        if surcharge:
            # Point de depart pratique : la geometrie/l'unsteady du plan choisi,
            # que l'utilisateur n'a plus qu'a changer s'il le souhaite.
            plan = self.combo_plan.currentData()
            if plan:
                self._selectionner_par_numero(self.combo_geometrie, plan.get("geometrie"))
                self._selectionner_par_numero(self.combo_unsteady, plan.get("unsteady"))
        self._maj_resume()

    def _resume_fenetre(self):
        """
        Etat de la fenetre de simulation, pour le resume et le bandeau du
        groupe. Valide la saisie au fil de la frappe : une date fausse doit se
        voir tout de suite, pas au lancement du calcul.
        """
        saisie = self.fenetre_saisie()
        if not saisie["debut"] and not saisie["fin"]:
            dire(self.label_fenetre, "")
            return []

        probleme = ""
        try:
            noyau.valider_fenetre(saisie)
        except Exception as e:
            probleme = str(e)

        if probleme:
            dire(self.label_fenetre,
                 f"<span style='color:{ISL_ROUGE}'>⚠ {probleme}</span>")
            return [f"Fenêtre de simulation : SAISIE INVALIDE — {probleme}"]

        if self._fenetre_modifiee():
            dire(self.label_fenetre,
                 f"<span style='color:{ISL_TEAL}'><b>Fenêtre modifiée</b> — "
                 f"elle sera imposée au plan de calcul.</span>")
            return [f"Fenêtre de simulation : {saisie['debut']} → "
                    f"{saisie['fin']}  (modifiée)"]

        dire(self.label_fenetre, "Identique au plan de référence.")
        return [f"Fenêtre de simulation : {saisie['debut']} → "
                f"{saisie['fin']}  (du plan)"]

    def _changer_plan(self, _index):
        self._remplir_fenetre_depuis_plan()
        self._maj_resume()

    def _remplir_fenetre_depuis_plan(self):
        """
        Recopie la fenetre du plan choisi dans les champs de saisie.

        Ecrase ce qui s'y trouve : ces champs decrivent le plan selectionne,
        pas une saisie independante. Conserver l'ancienne valeur apres un
        changement de plan afficherait la fenetre d'un plan qui n'est plus
        celui retenu — l'erreur la plus facile a ne pas voir.
        """
        plan = self.combo_plan.currentData()
        fenetre = (plan or {}).get("fenetre") or {}
        self.edit_sim_debut.setText(fenetre.get("debut", ""))
        self.edit_sim_fin.setText(fenetre.get("fin", ""))
        for cle, champ in self.edits_intervalles.items():
            champ.setText(fenetre.get(cle, ""))

    def fenetre_saisie(self):
        """Fenetre de simulation telle qu'elle est a l'ecran."""
        valeurs = {"debut": self.edit_sim_debut.text().strip(),
                   "fin": self.edit_sim_fin.text().strip()}
        for cle, champ in self.edits_intervalles.items():
            valeurs[cle] = champ.text().strip()
        return valeurs

    # Nom du parametre du classeur pour chaque cle de la fenetre. Une seule
    # table, lue par la saisie comme par la composition du paquet : deux listes
    # a tenir en accord finiraient par diverger.
    PARAMETRES_FENETRE = {
        "debut": "Simulation_debut",
        "fin": "Simulation_fin",
        "intervalle_calcul": "Intervalle_calcul",
        "intervalle_sortie": "Intervalle_sortie",
        "intervalle_instantane": "Intervalle_instantane",
        "intervalle_mapping": "Intervalle_mapping",
    }

    def _parametres_fenetre(self):
        """Fenetre a transmettre au classeur — vide si elle n'a pas bouge."""
        if not self._fenetre_modifiee():
            return {}
        saisie = self.fenetre_saisie()
        return {parametre: saisie[cle]
                for cle, parametre in self.PARAMETRES_FENETRE.items()}

    def _fenetre_modifiee(self):
        """La saisie s'ecarte-t-elle de la fenetre du plan de reference ?"""
        plan = self.combo_plan.currentData()
        origine = (plan or {}).get("fenetre") or {}
        saisie = self.fenetre_saisie()
        return any(saisie.get(c, "") != origine.get(c, "") for c in saisie)

    @staticmethod
    def _selectionner_par_numero(combo, numero):
        for i in range(combo.count()):
            if combo.itemData(i) and combo.itemData(i).get("numero") == numero:
                combo.setCurrentIndex(i)
                return

    def _geometrie_effective(self):
        if self.radio_override.isChecked() and self.combo_geometrie.currentData():
            return self.combo_geometrie.currentData()["numero"]
        plan = self.combo_plan.currentData()
        return plan["geometrie"] if plan else None

    def _unsteady_effective(self):
        if self.radio_override.isChecked() and self.combo_unsteady.currentData():
            return self.combo_unsteady.currentData()["numero"]
        plan = self.combo_plan.currentData()
        return plan["unsteady"] if plan else None

    @avec_sablier
    def _charger_couches_modele(self):
        try:
            if not self.info_projet:
                raise ValueError(
                    "choisir d'abord le dossier du projet HEC-RAS.")
            numero_geom = self._geometrie_effective()
            if not numero_geom:
                raise ValueError("choisir un plan de référence.")
            chemin_hdf = (Path(self.edit_dossier_hecras.text())
                         / f"{self.info_projet['nom_projet']}.g{numero_geom}.hdf")
            reponse = noyau.charger_couches_modele(chemin_hdf)
        except Exception as e:
            journaliser("Chargement des couches du modèle", e)
            QMessageBox.critical(self, "Chargement du modèle", str(e))
            return

        self.crs_modele = reponse.get("crs") or "EPSG:2154"
        projet = QgsProject.instance()

        def remplacer(couche_existante, fabrique, *args):
            if couche_existante is not None:
                try:
                    projet.removeMapLayer(couche_existante.id())
                except Exception:
                    pass
            # addToLegend=False : la position dans la legende est fixee plus
            # bas, explicitement. addMapLayer() empile chaque couche AU-DESSUS
            # de la precedente, si bien que l'ordre affiche serait l'inverse de
            # l'ordre de creation — dependance implicite qu'un simple
            # reordonnancement du code casserait sans bruit.
            couche = fabrique(*args)
            projet.addMapLayer(couche, False)
            return couche

        self.couche_sections = remplacer(
            self.couche_sections, construire_couche_lignes_depuis_wkt,
            "Sections de contrôle (HEC-RAS)", reponse["sections"], self.crs_modele)
        self.couche_injections = remplacer(
            self.couche_injections, construire_couche_lignes_depuis_wkt,
            "Lignes d'injection (HEC-RAS)", reponse["injections"], self.crs_modele)
        self.couche_perimetre = remplacer(
            self.couche_perimetre, construire_couche_polygones_depuis_wkt,
            "Emprise 2D (HEC-RAS)", reponse["perimetres"], self.crs_modele)

        # Maillage natif QGIS/MDAL — visuel uniquement (fond du lit, et les
        # résultats si le plan a déjà été calculé). Ne remplace pas les
        # couches ci-dessus : MDAL ne restitue ni les noms des sections de
        # contrôle ni ceux des lignes d'injection, seulement la géométrie et
        # les grandeurs calculées.
        if self.couche_maillage is not None:
            try:
                projet.removeMapLayer(self.couche_maillage.id())
            except Exception:
                pass
            self.couche_maillage = None
        maillage = QgsMeshLayer(str(chemin_hdf), "Maillage 2D (HEC-RAS)", "mdal")
        if maillage.isValid():
            projet.addMapLayer(maillage, False)
            self.couche_maillage = maillage
            groupes = maillage.datasetGroupCount()
        else:
            groupes = 0

        # Les echecs de style etaient collectes par appliquer_styles, puis
        # JETES par cet appel : un .qml refuse par QGIS ne se voyait nulle
        # part. Ils ne justifient pas d'interrompre le chargement — les
        # couches sont la, seule leur symbologie manque — mais ils meritent
        # une trace, sans quoi « les sections s'affichent en noir » reste
        # inexplicable.
        echecs_style = appliquer_styles(
            self.couche_injections, self.couche_sections, self.couche_maillage)
        if echecs_style:
            journaliser("Styles non appliqués : " + " ; ".join(echecs_style))
        ordonner_couches(projet, [self.couche_injections, self.couche_sections,
                                  self.couche_maillage, self.couche_perimetre])

        self.combo_zone_2d.clear()
        for p in reponse["perimetres"]:
            self.combo_zone_2d.addItem(p["zone"])
        # La zone 2D est indispensable — HEC-RAS y rattache sections et
        # injections, et elle leve l'ambiguite quand un meme nom de condition
        # limite existe dans plusieurs zones. Mais la plupart des modeles n'en
        # comptent qu'une : proposer alors une liste a un seul element donne a
        # croire qu'il y a un choix a faire. On la renseigne et on la verrouille.
        seule = len(reponse["perimetres"]) == 1
        self.combo_zone_2d.setEnabled(not seule)
        self.combo_zone_2d.setToolTip(
            "Ce modèle ne comporte qu'une zone d'écoulement 2D : elle est "
            "renseignée automatiquement, rien à choisir."
            if seule else
            "Ce modèle comporte plusieurs zones 2D : choisir celle à laquelle "
            "rattacher les sections et les injections.")

        # Compte rendu volontairement telegraphique : ce qui est arrive sur la
        # carte se voit sur la carte. Seul ce qui NE se voit pas — un
        # maillage absent, des objets pas encore pretraites — merite une
        # phrase, parce que rien d'autre ne le dirait.
        pretraitee = reponse.get("geometrie_pretraitee", True)
        dire(self.label_couches,
             f"<b>{len(reponse['sections'])} section(s)</b>, "
             f"<b>{len(reponse['injections'])} injection(s)</b> et "
             f"<b>{len(reponse['perimetres'])} emprise(s) 2D</b> ajoutées à "
             f"la carte, éditables."
             + ("" if reponse["sections"] else
                " Aucune section existante : la couche attend les nouvelles.")
             + (" Géométrie jamais prétraitée par HEC-RAS : maillage "
                "indisponible, contour(s) de zone 2D lu(s) directement dans "
                "le fichier géométrie. Dessiner les sections et injections "
                "manquantes, puis « Composer et contrôler » — le maillage "
                "apparaîtra au premier calcul."
                if not pretraitee else
                f" Maillage natif : {groupes} donnée(s)."
                if maillage.isValid() else
                " Maillage natif indisponible ici (MDAL) — sans effet sur la "
                "suite.")
             + (f"<br>{len(reponse['en_attente_pretraitement'])} objet(s) "
                f"écrits mais pas encore prétraités par HEC-RAS "
                f"({', '.join(reponse['en_attente_pretraitement'][:5])}) : "
                f"affichés d'après le fichier géométrie, pris en compte au "
                f"prochain calcul."
                if reponse.get("en_attente_pretraitement") else ""))
        self._maj_resume()

    # --- Onglet 2 : Profil en long et parametres ----------------------------

    def _onglet_profil(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)

        groupe_axe = QGroupBox("Axe hydraulique")
        groupe_axe.setToolTip(
            "Une polyligne unique, dessinée de l'amont vers l'aval, en "
            "projection métrique : elle donne les PK et le profil en long.")
        f = formulaire(groupe_axe)
        self.combo_axe = QgsMapLayerComboBox()
        self.combo_axe.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.champ_axe = QgsFieldComboBox()
        self.champ_axe.setLayer(self.combo_axe.currentLayer())
        self.combo_axe.layerChanged.connect(self.champ_axe.setLayer)
        self.combo_axe.layerChanged.connect(self._maj_resume)
        f.addRow("Couche de l'axe :", self.combo_axe)
        f.addRow("Champ de nom :", self.champ_axe)

        self.combo_sens_axe = QComboBox()
        self.combo_sens_axe.addItems(["amont_aval", "aval_amont"])
        self.combo_sens_axe.setToolTip(
            "amont_aval si l'axe est dessiné dans le sens de l'écoulement.")
        f.addRow("Sens de l'axe :", self.combo_sens_axe)

        self.spin_pk_origine = QDoubleSpinBox()
        self.spin_pk_origine.setRange(-1_000_000, 1_000_000)
        self.spin_pk_origine.setDecimals(1)
        self.spin_pk_origine.setSuffix(" m")
        f.addRow("PK d'origine :", self.spin_pk_origine)
        # La consigne sur l'axe est DITE UNE FOIS, en infobulle du groupe. Elle
        # figurait AUSSI en clair sous le formulaire, mot pour mot : deux
        # exemplaires d'une meme phrase se lisent comme deux consignes, et on
        # cherche en quoi elles different.
        v.addWidget(groupe_axe)

        groupe_param = QGroupBox("Précision attendue")
        f2 = formulaire(groupe_param)
        # La PRECISION ATTENDUE se saisit, en pourcentage : c'est ce que
        # l'hydraulicien juge, et cela depend de l'etude. La forme, elle, n'est
        # pas exposee — elle ne se negocie pas de la meme facon, et un
        # troisieme reglage a l'ecran donnerait a croire qu'on peut rendre un
        # calage conforme en abaissant les trois barres.
        rappel = QLabel(
            "Le calage s'arrête quand le <b>volume</b>, le <b>débit de "
            "pointe</b> et la <b>forme</b> sont conformes en même temps. "
            "Tout est rapporté en pourcentage d'atteinte de la cible.")
        rappel.setWordWrap(True)
        f2.addRow(rappel)

        self.spin_tol_volume = QDoubleSpinBox()
        self.spin_tol_volume.setRange(0.05, 20.0)
        self.spin_tol_volume.setDecimals(2)
        self.spin_tol_volume.setSingleStep(0.1)
        self.spin_tol_volume.setSuffix(" %")
        self.spin_tol_volume.setValue(100 * TOLERANCE_VOLUME_DEFAUT)
        self.spin_tol_volume.setToolTip(
            "Écart admis sur le volume, en pourcentage de la cible, jugé sur "
            "la fenêtre du hydrogramme PRINCIPAL uniquement (une mini-crue "
            "avant/après l'événement calé n'entre pas dans ce calcul). "
            "5 % est la valeur du guide.")
        f2.addRow("Précision sur le volume :", self.spin_tol_volume)

        self.spin_tol_pic = QDoubleSpinBox()
        self.spin_tol_pic.setRange(0.05, 20.0)
        self.spin_tol_pic.setDecimals(2)
        self.spin_tol_pic.setSingleStep(0.1)
        self.spin_tol_pic.setSuffix(" %")
        self.spin_tol_pic.setValue(100 * TOLERANCE_PIC_DEFAUT)
        self.spin_tol_pic.setToolTip(
            "Écart admis sur le débit de pointe. Il a sa propre tolérance "
            "parce qu'il dimensionne l'aléa : un volume juste avec une pointe "
            "fausse ne serait pas conservatif.")
        f2.addRow("Précision sur le débit de pointe :", self.spin_tol_pic)

        # CE SEUIL N'EST PAS UNE TOLERANCE DE CALAGE, et le libelle doit le
        # dire : il porte sur la CONSERVATION DE LA MASSE par HEC-RAS, pas
        # sur l'ecart a la cible. Les deux voisinent dans le meme groupe
        # parce que l'un et l'autre decident du sort d'un essai, mais les
        # confondre ferait desserrer la qualite du calcul en croyant
        # desserrer la precision demandee.
        self.spin_bilan_masse = QDoubleSpinBox()
        self.spin_bilan_masse.setRange(0.1, 50.0)
        self.spin_bilan_masse.setDecimals(2)
        self.spin_bilan_masse.setSingleStep(0.5)
        self.spin_bilan_masse.setSuffix(" %")
        self.spin_bilan_masse.setValue(noyau.BILAN_MASSE_DEFAUT)
        self.spin_bilan_masse.setToolTip(
            "QUALITÉ DU CALCUL, PAS ÉCART À LA CIBLE. Erreur de conservation "
            "que HEC-RAS rend lui-même (« volume accounting error ») : ce "
            "qu'il perd ou fabrique entre entrées, sorties et stockage. "
            "Au-delà, l'essai est REJETÉ sans être comparé à la cible — on ne "
            "corrige pas un apport pour compenser une erreur du solveur.\n\n"
            "Si un calcul dépasse ce seuil, le vrai remède est de resserrer "
            "le pas de calcul du plan, pas de desserrer ce chiffre.")
        f2.addRow("Bilan de masse admis (qualité du calcul) :",
                  self.spin_bilan_masse)

        self.spin_nb_max_essais = QSpinBox()
        self.spin_nb_max_essais.setRange(3, 50)
        self.spin_nb_max_essais.setValue(6)
        self.spin_nb_max_essais.setToolTip(
            "Garde-fou de dernier recours, non le mode d'arrêt normal : la "
            "concordance s'obtient en trois à quatre essais.")
        f2.addRow("Nombre max d'essais par apport :", self.spin_nb_max_essais)

        # L'HYPOTHESE SUR LA PENTE etait dite ici ; elle est desormais dite a
        # l'onglet 4, dans le groupe « Classeur » — c'est la qu'on ouvre le
        # fichier ou elle se lit et se corrige, et une consigne loin de son
        # objet ne se suit pas.
        v.addWidget(groupe_param)

        v.addStretch(1)
        return page

    # --- Onglet 3 : Resultats et suivi --------------------------------------

    def _onglet_resultats(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)

        groupe = QGroupBox("Répertoires")
        f = formulaire(groupe)
        ligne = QHBoxLayout()
        ligne.setSpacing(6)
        self.edit_dossier_sortie = QLineEdit()
        self.edit_dossier_sortie.setPlaceholderText(
            "Où écrire les shapefiles et le classeur")
        self.edit_dossier_sortie.textChanged.connect(self._maj_resume)
        bouton = QPushButton("Parcourir…")
        bouton.clicked.connect(self._parcourir_dossier_sortie)
        ligne.addWidget(self.edit_dossier_sortie, 1)
        ligne.addWidget(bouton)
        f.addRow("Dossier de sortie :", ligne)

        self.edit_sous_dossier_resultats = QLineEdit("resultats_finaux")
        self.edit_sous_dossier_resultats.textChanged.connect(self._maj_resume)
        f.addRow("Sous-dossier — résultats :",
                 self.edit_sous_dossier_resultats)

        self.edit_sous_dossier_suivi = QLineEdit("suivi")
        self.edit_sous_dossier_suivi.textChanged.connect(self._maj_resume)
        f.addRow("Sous-dossier — suivi :", self.edit_sous_dossier_suivi)
        f.addRow(texte_aide(
            "L'avancement se lit à l'onglet 5 pendant le calcul. Ce dossier "
            "en porte la trace sur disque — avancement.md, avancement.png et "
            "le classeur d'itérations — consultable depuis un autre poste."))
        v.addWidget(groupe)

        groupe_relire = QGroupBox("Relire un hydrogramme déjà calculé")
        groupe_relire.setToolTip(
            "Utile avant de caler : vérifier qu'une section répond, et que "
            "les apports sont bien pris en compte.")
        v3 = QVBoxLayout(groupe_relire)
        v3.setSpacing(8)
        bouton_relire = QPushButton("Choisir un fichier de résultats…")
        bouton_relire.clicked.connect(self._relire_hydrogramme)
        ligne_relire = QHBoxLayout()
        ligne_relire.addWidget(bouton_relire)
        ligne_relire.addStretch(1)
        v3.addLayout(ligne_relire)
        self.label_relecture = texte_etat()
        v3.addWidget(self.label_relecture)
        v3.addWidget(texte_aide(
            "Exporte en CSV le débit calculé à une section, ou le débit "
            "injecté à une ligne d'apport."))
        v.addWidget(groupe_relire)

        groupe_resume = QGroupBox("Résumé de la configuration")
        v2 = QVBoxLayout(groupe_resume)
        self.texte_resume = QTextEdit()
        self.texte_resume.setObjectName("resume")
        self.texte_resume.setReadOnly(True)
        self.texte_resume.setMinimumHeight(180)
        v2.addWidget(self.texte_resume)
        v.addWidget(groupe_resume, 1)

        return page

    @avec_sablier
    def _relire_hydrogramme(self):
        """Lit le débit calculé à une section ou à une injection, et l'exporte."""
        try:
            depart = self.edit_dossier_hecras.text().strip()
            with sans_sablier(self):
                plan, _ = QFileDialog.getOpenFileName(
                    self, "Fichier de résultats HEC-RAS", depart,
                    "Résultats HEC-RAS (*.hdf)")
            if not plan:
                return

            objets = noyau.lister_objets_modele(plan)
            if not objets["sections"] and not objets["apports"]:
                raise ValueError(
                    "ce fichier de résultats ne contient ni section de "
                    "contrôle ni ligne d'injection. Les créer dans l'onglet 1, "
                    "puis relancer le calcul.")

            # Relire un apport tel qu'il a ete injecte est utile pour verifier
            # qu'un hydrogramme a bien ete pris en compte.
            choix = ([(n, "Reference Lines") for n in objets["sections"]]
                     + [(f"{n}  (injection)", "Boundary Conditions")
                        for n in objets["apports"]])
            libelles = [c[0] for c in choix]
            with sans_sablier(self):
                libelle, valide = QInputDialog.getItem(
                    self, "Objet à relire",
                    "Section de contrôle ou injection :", libelles, 0, False)
            if not valide:
                return
            nom, groupe = choix[libelles.index(libelle)]
            nom = nom.split("  (injection)")[0]

            r = noyau.lire_hydrogramme(plan, nom, groupe=groupe)
            message = (
                f"« {nom} » : {r['pas_de_temps']} pas de temps sur "
                f"{r['duree_h']:.1f} h, pointe {r['pointe_m3s']:.2f} m³/s, "
                f"volume {r['volume_1000m3']:.0f} × 10³ m³.\n"
                f"Exporté dans {os.path.basename(r['fichier'])}.")
            if r.get("orientation_inversee"):
                message += ("\nLa section est tracée à contre-courant : le "
                            "débit a été ramené en convention positive vers "
                            "l'aval.")
            if r.get("ecoulement_reversible"):
                message += ("\nATTENTION : l'écoulement change de sens au "
                            "cours du temps. La méthode suppose un sens "
                            "stable — résultat à interpréter avec prudence.")
            dire(self.label_relecture, message)
            QMessageBox.information(self, "Hydrogramme relu", message)
        except Exception as e:
            journaliser("Relecture d'un hydrogramme", e)
            dire(self.label_relecture,
                 f"<span style='color:{ISL_ROUGE}'>Échec : {e}</span>")
            QMessageBox.critical(self, "Lecture", str(e))

    def _ecrire_dans_geometrie(self):
        """
        Écrit les sections et injections des couches CHARGÉES (onglet 1,
        « Charger les couches du modèle », dessinées ou complétées
        par-dessus dans QGIS) vers la géométrie HEC-RAS, et donne aux
        injections leur hydrogramme dans le fichier Unsteady Flow.

        Appelée automatiquement en tête de « Composer et contrôler », jamais
        via une action séparée : les sections doivent être DANS le modèle
        avant que le paquet soit composé, sinon le calage n'a rien à relire.

        TOUJOURS EN MODE REMPLACEMENT, sections et injections : ce que QGIS
        montre fait foi, et remplace l'objet de même nom déjà présent dans
        la géométrie HEC-RAS plutôt que de l'ignorer. Un apport qui a déjà
        son hydrogramme (calage en cours ou terminé) n'est PAS affecté par ce
        remplacement : lui seul retrace la ligne dans la géométrie, jamais le
        fichier Unsteady Flow — voir creer_injections_dans_modele.

        Reprend la géométrie, la zone 2D et l'Unsteady Flow choisis plus haut
        dans cet onglet : rien n'est redemandé. Le noyau sauvegarde les deux
        fichiers de façon horodatée avant d'écrire. Lève une exception plutôt
        que d'afficher une boîte de dialogue : l'appelant (_composer_et_
        controler) gère l'affichage des erreurs.
        """
        if not self.info_projet:
            raise ValueError("choisir d'abord le dossier du projet HEC-RAS.")
        numero_geom = self._geometrie_effective()
        if not numero_geom:
            raise ValueError("choisir un plan de référence.")
        zone = self.combo_zone_2d.currentText().strip()
        if not zone:
            raise ValueError(
                "la zone d'écoulement 2D est obligatoire : HEC-RAS y "
                "rattache sections et injections. Cliquer « Charger les "
                "couches du modèle » pour la renseigner.")

        couche_s = couche_vivante(self.couche_sections)
        couche_a = couche_vivante(self.couche_injections)
        if couche_s is None or couche_a is None:
            raise ValueError(
                "cliquer « Charger les couches du modèle » avant de "
                "composer.")

        dossier = Path(self.edit_dossier_hecras.text())
        projet = self.info_projet["nom_projet"]
        geometrie = dossier / f"{projet}.g{numero_geom}"
        unsteady = dossier / f"{projet}.u{self._unsteady_effective()}"

        # Noms deja presents dans L'UNE OU L'AUTRE couche : une entite SANS
        # NOM ne doit pas en reprendre un deja utilise par sa voisine, sous
        # peine de rendre l'appariement indecidable. Les noms deja presents
        # dans le modele, eux, ne sont plus a eviter : le remplacement est
        # desormais systematique.
        deja = set()
        for source in (couche_s, couche_a):
            deja |= {str(e["nom"]) for e in source.getFeatures() if e["nom"]}

        resume = []
        for couche, genre in ((couche_s, "sections"), (couche_a, "injections")):
            gdf = couche_vers_gdf(
                couche,
                prefixe_defaut=(PREFIXE_SECTION if genre == "sections"
                                else PREFIXE_APPORT),
                noms_pris=deja)
            deja |= set(gdf["nom"])
            if gdf.empty:
                resume.append(f"aucune couche « {genre} » à écrire")
                continue
            chemin_shp = noyau.ecrire_shp_temporaire(
                gdf, str(dossier / "_calage"), genre)
            if genre == "sections":
                reponse = noyau.creer_sections_dans_modele(
                    str(geometrie), chemin_shp, zone, remplacer=True)
                resume.append(
                    f"{reponse['creees']} section(s) : "
                    f"{', '.join(reponse['noms'][:6])}"
                    + (f" (dont {len(reponse['remplacees'])} remplacée(s))"
                       if reponse.get("remplacees") else ""))
            else:
                reponse = noyau.creer_injections_dans_modele(
                    str(geometrie), chemin_shp, zone, remplacer=True,
                    fichier_unsteady=str(unsteady),
                    pente=PENTE_APPORT_DEFAUT)
                resume.append(
                    f"{reponse['creees']} injection(s) : "
                    f"{', '.join(reponse['noms'][:6])}")
                if reponse.get("raccordes"):
                    resume.append(
                        f"hydrogramme créé dans {unsteady.name} pour : "
                        f"{', '.join(reponse['raccordes'])}")
                for a in reponse.get("avertissements", []):
                    resume.append(a)

        message = (f"Écrit dans {geometrie.name} : " + " | ".join(resume)
                   + "\n\nLe fichier prétraité (.hdf) ne les portera qu'au "
                     "prochain calcul ; « Charger les couches du modèle » "
                     "les montre dès maintenant, en lisant le fichier "
                     "texte, qui fait foi.")
        dire(self.label_ecriture, message)
        return message

    def _parcourir_dossier_sortie(self):
        dossier = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if dossier:
            self.edit_dossier_sortie.setText(dossier)

    # --- Onglet 4 : Validation et hydrogrammes cibles -----------------------

    def _onglet_validation(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)

        groupe = QGroupBox("Validation de la dernière composition")
        f = formulaire(groupe)
        self.label_validation_comptes = QLabel("(pas encore composé)")
        self.label_validation_comptes.setWordWrap(True)
        f.addRow("Apports appariés :", self.label_validation_comptes)
        self.label_validation_classeur = QLabel("(pas encore composé)")
        self.label_validation_classeur.setWordWrap(True)
        self.label_validation_classeur.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        f.addRow("Classeur :", self.label_validation_classeur)
        self.label_validation_cibles = QLabel("(pas encore composé)")
        self.label_validation_cibles.setWordWrap(True)
        f.addRow("Hydrogrammes cibles :", self.label_validation_cibles)
        v.addWidget(groupe)

        self.label_prochaine_etape = texte_etat(
            "Composer le paquet — bouton en bas de la fenêtre — pour voir "
            "apparaître ici l'étape suivante.")
        v.addWidget(self.label_prochaine_etape)

        groupe_actions = QGroupBox("Classeur")
        v_classeur = QVBoxLayout(groupe_actions)
        v_classeur.setSpacing(8)
        ligne_classeur = QHBoxLayout()
        ligne_classeur.setSpacing(8)
        bouton_ouvrir = QPushButton("Ouvrir le classeur…")
        bouton_ouvrir.setToolTip(
            "C'est dans sa feuille Cibles que se saisissent les hydrogrammes "
            "visés, une colonne par section.")
        bouton_ouvrir.clicked.connect(self._ouvrir_classeur)
        ligne_classeur.addWidget(bouton_ouvrir)
        bouton_recontroler = QPushButton(
            "Reprendre un classeur d'un calcul précédent…")
        bouton_recontroler.setToolTip(
            "Rejoue tous les contrôles sur un classeur composé lors d'une "
            "autre session, sans rien recomposer. Les chemins des shapefiles "
            "sont relus dans le classeur lui-même.")
        bouton_recontroler.clicked.connect(self._recontroler_classeur)
        ligne_classeur.addWidget(bouton_recontroler)
        ligne_classeur.addStretch(1)
        v_classeur.addLayout(ligne_classeur)

        # HYPOTHESE SUR LA PENTE, dite a cote du bouton qui ouvre le fichier
        # ou elle se corrige. Elle est desormais PRE-REMPLIE a la composition,
        # d'ou « à ajuster si besoin » : ce n'est plus une case vide a
        # comprendre, c'est une valeur proposee qu'on peut refuser.
        v_classeur.addWidget(texte_aide(
            "<b>Pente des apports</b> — colonne « Pente_m_par_m », feuille "
            "Correspondance. <b>Pré-remplie</b> à la composition : pente "
            "moyenne du fond sur ±200 m autour de l'injection, majorée de "
            "20 %. À ajuster si besoin — une valeur saisie n'est jamais "
            "écrasée par une recomposition.",
            "HEC-RAS s'en sert pour répartir le débit entre les mailles que "
            "la ligne recoupe. Une pente sous-estimée concentre l'injection "
            "au lieu de l'étaler : la majoration va dans le sens de la "
            "prudence. Elle dépend du tronçon, d'où la saisie par apport.\n"
            "Laissée vide — profil trop court ou géométrie non prétraitée — "
            "le calage la déduit lui-même, comme avant."))
        v.addWidget(groupe_actions)

        # LE CHOIX DU PREMIER APPORT PRECEDE LE BOUTON QU'IL REGLE. Il figurait
        # sous lui : on decidait de reprendre a mi-parcours apres avoir lance
        # le calcul depuis le debut. Un reglage se lit avant l'action, jamais
        # apres.
        v.addWidget(self._groupe_copies_de_travail())

        groupe_lancer = QGroupBox("Calage")
        vl = QVBoxLayout(groupe_lancer)
        vl.setSpacing(8)
        ligne_lancer = QHBoxLayout()
        bouton_lancer = QPushButton("Lancer le calage")
        bouton_lancer.setObjectName("boutonAccent")
        bouton_lancer.setMinimumWidth(190)
        bouton_lancer.setToolTip(
            "Lance la boucle séquentielle complète dans un processus "
            "détaché. QGIS reste utilisable pendant le calcul ; l'avancement "
            "se lit à l'onglet 5, qui se rafraîchit tout seul.")
        bouton_lancer.clicked.connect(self._lancer_calage)
        ligne_lancer.addWidget(bouton_lancer)
        ligne_lancer.addWidget(texte_aide(
            "En arrière-plan, plusieurs heures. QGIS reste utilisable."), 1)
        vl.addLayout(ligne_lancer)
        self.label_lancement = texte_etat()
        vl.addWidget(self.label_lancement)
        v.addWidget(groupe_lancer)

        v.addStretch(1)
        return page

    # --- Onglet 5 : Suivi en temps reel -------------------------------------

    def _onglet_suivi(self):
        """
        Ce qui se passe pendant le calcul, rafraichi tout seul.

        Le calage tourne dans un processus DETACHE : QGIS n'en sait rien.
        Cet onglet relit le fichier d'etat que suivi.py reecrit a chaque
        essai, et signale de lui-meme la fin, l'echec — et l'interruption,
        qui ne s'annonce pas.
        """
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)

        self.label_suivi_banniere = QLabel()
        self.label_suivi_banniere.setWordWrap(True)
        self.label_suivi_banniere.setTextFormat(Qt.TextFormat.RichText)
        self.label_suivi_banniere.setObjectName("banniereSuivi")
        v.addWidget(self.label_suivi_banniere)

        groupe_avancement = QGroupBox("Avancement")
        va = QVBoxLayout(groupe_avancement)
        va.setSpacing(9)
        self.ruban_apports = RubanApports()
        va.addWidget(self.ruban_apports)
        self.barre_suivi = QProgressBar()
        self.barre_suivi.setRange(0, 100)
        self.barre_suivi.setTextVisible(True)
        self.barre_suivi.setFormat("%p %")
        va.addWidget(self.barre_suivi)
        self.label_suivi_position = QLabel("—")
        self.label_suivi_position.setWordWrap(True)
        self.label_suivi_position.setTextFormat(Qt.TextFormat.RichText)
        va.addWidget(self.label_suivi_position)
        v.addWidget(groupe_avancement)

        groupe_jauges = QGroupBox("Atteinte de la cible — dernier essai évalué")
        vj = QVBoxLayout(groupe_jauges)
        vj.setSpacing(10)
        ligne_jauges = QHBoxLayout()
        ligne_jauges.setSpacing(18)
        self.jauges = {}
        for cle, libelle in (("volume_pct", "Volume"),
                             ("pic_pct", "Débit de pointe"),
                             ("forme_pct", "Forme")):
            jauge = JaugeAtteinte(libelle)
            self.jauges[cle] = jauge
            ligne_jauges.addWidget(jauge, 1)
        vj.addLayout(ligne_jauges)
        # LA COURBE SOUS LES JAUGES : les chiffres disent de combien on
        # s'ecarte, le trace dit ou. Un volume excedentaire avec une pointe
        # basse peut venir d'un pic trop faible ou d'une decrue trop longue —
        # deux diagnostics opposes que seule la courbe separe.
        # DE QUEL APPORT viennent les chiffres et les courbes affiches. Ce
        # n'est pas toujours celui qui calcule : tant que son premier essai
        # n'est pas evalue, c'est le dernier apport chiffre qui est montre.
        self.label_jauges = texte_aide("")
        vj.addWidget(self.label_jauges)
        # BILAN DE MASSE DU DERNIER CALCUL — VOISIN DES JAUGES, MAIS PAS UNE
        # QUATRIEME JAUGE. Il ne dit rien de l'atteinte de la cible : c'est
        # la conservation du solveur. Il figure ici parce que c'est lui qui
        # peut faire REJETER un essai avant toute comparaison, et qu'un arrêt
        # « qualité numérique » ne se lisait alors que dans le journal texte.
        self.label_bilan_masse = texte_aide("")
        vj.addWidget(self.label_bilan_masse)
        self.courbe_suivi = CourbeComparaison()
        vj.addWidget(self.courbe_suivi)
        vj.addWidget(texte_aide(
            "Débit à la section de contrôle au dernier essai évalué, face à "
            "l'hydrogramme visé, décalé du Δt de propagation."))
        v.addWidget(groupe_jauges)

        groupe_temps = QGroupBox("Temps")
        ft = formulaire(groupe_temps)
        self.label_suivi_ecoule = QLabel("—")
        self.label_suivi_reste = QLabel("—")
        self.label_suivi_fin = QLabel("—")
        ft.addRow("Écoulé :", self.label_suivi_ecoule)
        ft.addRow("Reste estimé :", self.label_suivi_reste)
        ft.addRow("Fin prévisible :", self.label_suivi_fin)
        ft.addRow(texte_aide(
            "Estimé d'après la durée moyenne des apports déjà achevés. "
            "L'estimation vaut ce que vaut l'hypothèse d'apports de coût "
            "comparable, mais c'est le seul chiffre qui permette de décider "
            "s'il faut attendre."))
        v.addWidget(groupe_temps)

        groupe_detail = QGroupBox("Apports")
        vd = QVBoxLayout(groupe_detail)
        self.table_suivi = QTableWidget(0, 6)
        self.table_suivi.setHorizontalHeaderLabels(
            ["Apport", "Section", "Statut", "Essais", "Volume (%)",
             "Pointe (%)"])
        self.table_suivi.verticalHeader().setVisible(False)
        self.table_suivi.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_suivi.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.table_suivi.setAlternatingRowColors(True)
        self.table_suivi.setMinimumHeight(150)
        self.table_suivi.horizontalHeader().setStretchLastSection(True)
        vd.addWidget(self.table_suivi)
        v.addWidget(groupe_detail, 1)

        ligne = QHBoxLayout()
        ligne.setSpacing(8)
        bouton_dossier = QPushButton("Ouvrir le dossier de suivi")
        bouton_dossier.clicked.connect(self._ouvrir_dossier_suivi)
        ligne.addWidget(bouton_dossier)
        bouton_figure = QPushButton("Ouvrir avancement.png")
        bouton_figure.setToolTip(
            "La figure produite par la chaîne : état de chaque apport, et "
            "volume et débit de pointe atteints face aux 100 % visés.")
        bouton_figure.clicked.connect(self._ouvrir_figure_suivi)
        ligne.addWidget(bouton_figure)
        ligne.addStretch(1)
        self.label_suivi_maj = QLabel("")
        self.label_suivi_maj.setProperty("role", ROLE_AIDE)
        ligne.addWidget(self.label_suivi_maj)
        v.addLayout(ligne)

        # RAFRAICHISSEMENT AUTOMATIQUE. Deux secondes : assez pour que l'ecran
        # suive un essai qui dure des minutes, assez peu pour ne rien couter —
        # la lecture porte sur un fichier de quelques kilo-octets.
        #
        # IL NE TOURNE QUE QUAND CET ONGLET EST A L'ECRAN. Il tournait
        # auparavant pour la duree de vie de la fenetre : relire et
        # redessiner toutes les deux secondes un onglet que personne ne
        # regarde, y compris quand aucun calage n'existe et longtemps apres
        # qu'il est termine. _changer_onglet le demarre et l'arrete ; il part
        # a l'arret, puisque la fenetre s'ouvre sur l'onglet 1.
        self.minuteur_suivi = QTimer(self)
        self.minuteur_suivi.setInterval(2000)
        self.minuteur_suivi.timeout.connect(self._rafraichir_suivi)
        self._rafraichir_suivi()
        return page

    def _changer_onglet(self, indice):
        """
        Le suivi ne se relit que lorsqu'il est visible, et se remet a jour
        immediatement quand on y arrive.
        """
        if indice == ONGLET_SUIVI:
            self._rafraichir_suivi()
            self.minuteur_suivi.start()
        else:
            self.minuteur_suivi.stop()

    # LA FENETRE N'EST PAS DETRUITE QUAND ON LA FERME : composer() la conserve
    # et la re-affiche telle quelle. Le minuteur, lui, ne s'arretait qu'au
    # changement d'onglet — une fenetre fermee DEPUIS L'ONGLET 5 continuait
    # donc de relire avancement.json et de repeindre trois widgets toutes les
    # deux secondes, pour le restant de la session QGIS.

    def hideEvent(self, evenement):                          # noqa: N802
        """Arrete le suivi des que la fenetre disparait."""
        minuteur = getattr(self, "minuteur_suivi", None)
        if minuteur is not None:
            minuteur.stop()
        super().hideEvent(evenement)

    def showEvent(self, evenement):                          # noqa: N802
        """Reprend le suivi si la fenetre revient sur l'onglet du suivi."""
        super().showEvent(evenement)
        minuteur = getattr(self, "minuteur_suivi", None)
        if minuteur is not None and self.onglets.currentIndex() == ONGLET_SUIVI:
            self._rafraichir_suivi()
            minuteur.start()

    def _dossier_suivi(self):
        racine = self.edit_dossier_sortie.text().strip()
        if not racine:
            return None
        return (Path(racine)
                / (self.edit_sous_dossier_suivi.text().strip() or "suivi"))

    def _ouvrir_dossier_suivi(self):
        dossier = self._dossier_suivi()
        if dossier is None or not dossier.is_dir():
            QMessageBox.information(
                self, "Suivi",
                "Aucun dossier de suivi : renseigner le dossier de sortie "
                "(onglet 3), puis composer le paquet.")
            return
        os.startfile(str(dossier))  # noqa: S606 (usage Windows assume)

    def _ouvrir_figure_suivi(self):
        dossier = self._dossier_suivi()
        figure = (dossier / "avancement.png") if dossier else None
        if figure is None or not figure.is_file():
            QMessageBox.information(
                self, "Suivi",
                "avancement.png n'existe pas encore : il est écrit dès le "
                "premier essai.")
            return
        os.startfile(str(figure))  # noqa: S606

    def _banniere(self, couleur, titre, detail="", glyphe=""):
        """
        Bandeau d'etat : fond NEUTRE, filet de couleur, titre colore.

        Un aplat sature sur toute la largeur criait sans rien dire de plus, et
        forcait un texte blanc qui devenait illisible des que QGIS passe en
        theme clair. Ici le fond vient de la palette — il suit donc le theme —
        et la couleur ne sert qu'a marquer : un filet a gauche et le titre.
        C'est la regle que suit tout le reste de la fenetre, et la seule qui
        tienne en theme clair comme en theme sombre.
        """
        self.label_suivi_banniere.setStyleSheet(
            f"background-color: palette(alternate-base);"
            f"border-left: 5px solid {couleur};"
            f"border-radius: 3px; padding: 12px 16px;")
        self.label_suivi_banniere.setText(
            f"<span style='font-size:13pt; font-weight:bold; color:{couleur}'>"
            f"{glyphe + '  ' if glyphe else ''}{titre}</span>"
            + (f"<br><span style='font-size:9pt; color:{ISL_ARDOISE}'>"
               f"{detail}</span>" if detail else ""))

    def _rafraichir_suivi(self):
        """
        Relit l'etat et redessine. Ne leve jamais : c'est un affichage
        periodique, et une exception dans un QTimer remonte dans la boucle
        d'evenements de QGIS.
        """
        try:
            self._peindre_suivi()
        except Exception as e:                              # noqa: BLE001
            # Le filet reste — il est necessaire. Ce qui change, c'est qu'il
            # laisse desormais un temoin : un onglet Suivi devenu muet le
            # restait jusqu'a la fin de la session, et rien, nulle part,
            # n'en donnait la raison.
            #
            # UNE SEULE FOIS PAR PANNE. Ce code s'execute toutes les deux
            # secondes tant que l'onglet est a l'ecran, et une panne de
            # peinture se repete a chaque tour : journaliser sans filtre
            # ecrivait une pile d'appels complete toutes les deux secondes et
            # rallumait d'autant le temoin du journal de QGIS. On ne rejournalise
            # que si la panne CHANGE.
            signature = f"{type(e).__name__}: {e}"
            if signature != getattr(self, "_derniere_panne_suivi", None):
                self._derniere_panne_suivi = signature
                journaliser("Rafraichissement du suivi", e)
            return

    def _peindre_suivi(self):
        dossier = self._dossier_suivi()
        etat = noyau.lire_avancement(dossier) if dossier else None

        if etat is None:
            self._banniere(
                ISL_ARDOISE_CLAIR, "Aucun calage suivi", glyphe="·",
                detail="Le suivi apparaît ici dès que le calage écrit son "
                       "premier état, quelques secondes après le lancement.")
            self.barre_suivi.setValue(0)
            self.ruban_apports.actualiser([], None)
            self.courbe_suivi.actualiser(None)
            self.label_suivi_position.setText("—")
            self.table_suivi.setRowCount(0)
            for jauge in self.jauges.values():
                jauge.actualiser(None)
            return

        apports = etat.get("apports") or []
        en_cours = etat.get("en_cours")
        # Les jauges jugent sur LES TOLERANCES DE L'ETUDE, publiees par le
        # suivi. Figees a 2 %, elles coloraient en rouge des valeurs admises
        # par une etude qui en tolere 5.
        # Les defauts sont CEUX DE LA CHAINE, repris des constantes du module :
        # ecrits en dur ici, ils divergeaient — la jauge « Volume » jugeait a
        # 0,5 % ce que la boucle admet a 5 %, et virait au rouge sur un apport
        # parfaitement conforme des que le suivi ne publiait pas ses seuils.
        tolerances = etat.get("tolerances_pct") or {}
        for cle, defaut in (("volume_pct", 100 * TOLERANCE_VOLUME_DEFAUT),
                            ("pic_pct", 100 * TOLERANCE_PIC_DEFAUT),
                            ("forme_pct", 100 * TOLERANCE_FORME_DEFAUT)):
            self.jauges[cle].tolerance = float(
                tolerances.get(cle.replace("_pct", ""), defaut))
        comptes = etat.get("comptes") or {}
        fraction = float(etat.get("fraction") or 0.0)
        self.barre_suivi.setValue(int(round(100 * fraction)))
        self.ruban_apports.actualiser(apports, en_cours)
        self.courbe_suivi.actualiser(etat.get("courbes"))

        # BANNIERE : l'etat en un mot, et sa couleur avant meme la lecture.
        if etat.get("termine"):
            if etat.get("conforme"):
                self._banniere(
                    ISL_VERT, "Calage terminé — conforme", glyphe="✔",
                    detail=f"{comptes.get('validé', 0)} apport(s) calés en "
                    f"{duree_lisible(etat.get('ecoule_s'))}"
                    + (f", {etat['nb_calculs']} calculs"
                       if etat.get("nb_calculs") else "")
                    + ". Les livrables sont dans le dossier de résultats.")
            else:
                self._banniere(
                    ISL_ROUGE, "Calage terminé — NON conforme", glyphe="✕",
                    detail=etat.get("motif_final")
                    or "voir avancement.md pour le détail.")
        else:
            vivant = noyau.processus_vivant(etat.get("pid"))
            if vivant is False:
                # LE CAS QUI MANQUAIT : plus personne n'ecrit, et rien ne le
                # disait. Le dernier etat connu reste affiche, mais il est
                # annonce comme tel.
                self._banniere(
                    ISL_ROUGE, "Calage interrompu", glyphe="⏹",
                    detail=f"Le processus {etat.get('pid')} n'existe plus et le "
                    f"calage n'a pas rendu de verdict. Dernier état connu "
                    f"ci-dessous ; le journal de lancement dit pourquoi.")
            else:
                nom = (apports[en_cours]["apport"]
                       if en_cours is not None and en_cours < len(apports)
                       else "—")
                self._banniere(
                    ISL_TEAL, "Calage en cours", glyphe="▶",
                    detail=f"Apport {(en_cours or 0) + 1} sur {etat.get('total')} — "
                    f"{nom}. Mis à jour "
                    f"{etat.get('maj', '')[11:]}.")

        # Ligne « ou en est-on », la phrase que l'on vient chercher.
        if en_cours is not None and en_cours < len(apports):
            a = apports[en_cours]
            self.label_suivi_position.setText(
                f"<b style='color:{ISL_TEAL}'>{a['apport']} → "
                f"{a['section']}</b> &nbsp;·&nbsp; essai <b>{a['essais']}</b>"
                f" &nbsp;·&nbsp; apport <b>{a['ordre']}</b> sur "
                f"<b>{etat.get('total')}</b>")
        else:
            self.label_suivi_position.setText(
                f"{comptes.get('validé', 0)} validé(s), "
                f"{comptes.get('échoué', 0)} échoué(s), "
                f"{comptes.get('en attente', 0)} en attente")

        # LES JAUGES SE REPLIENT SUR LE DERNIER APPORT CHIFFRE. Un apport dont
        # le premier essai n'est pas encore evalue — soit toute la duree de son
        # calcul HEC-RAS, environ trois heures — n'a aucun chiffre a montrer :
        # les trois jauges restaient donc vides pendant exactement les heures
        # ou on les regarde. Le repli dit de QUEL apport il s'agit, sans quoi
        # on lirait les chiffres du precedent comme ceux du calcul en cours.
        montre = (apports[en_cours]
                  if en_cours is not None and en_cours < len(apports)
                  and apports[en_cours].get("volume_pct") is not None
                  else next((a for a in reversed(apports)
                             if a.get("volume_pct") is not None), None))
        for cle, jauge in self.jauges.items():
            jauge.actualiser(montre.get(cle) if montre else None)
        self.label_jauges.setText(
            "en attente du premier essai" if montre is None
            else (f"<b>{montre['apport']} → {montre['section']}</b>, essai "
                  f"{montre['essais']}"
                  + ("" if en_cours is not None
                     and en_cours < len(apports)
                     and montre is apports[en_cours]
                     else " — dernier essai évalué ; le calcul en cours n'a "
                          "pas encore rendu le sien")))

        self._afficher_bilan_masse(etat.get("bilan_masse"))

        self.label_suivi_ecoule.setText(duree_lisible(etat.get("ecoule_s")))
        self.label_suivi_reste.setText(
            "—" if etat.get("termine") else duree_lisible(etat.get("reste_s")))
        fin = etat.get("fin") or etat.get("fin_prevue")
        self.label_suivi_fin.setText(
            (fin or "—").replace("T", " à ") if fin else "—")
        self.label_suivi_maj.setText(
            f"actualisé {etat.get('maj', '')[11:]}"
            + (f" · {etat['incidents']} incident(s)"
               if etat.get("incidents") else ""))
        self._remplir_table_suivi(apports)

    def _afficher_bilan_masse(self, bilan):
        """
        Bilan de masse du dernier calcul, sous les jauges.

        TROIS ETATS, ET LE TROISIEME COMPTE AUTANT QUE LES DEUX AUTRES :
        pas encore mesuré (aucun calcul n'a rendu la valeur), dans le seuil,
        au-delà du seuil. Le dernier explique à lui seul un calage qui
        s'arrête sans qu'aucune jauge n'ait bougé.

        Un état publié par une version ANTERIEURE du suivi n'a pas la clé :
        la ligne reste alors vide plutôt que d'annoncer une mesure absente.
        """
        if not isinstance(bilan, dict):
            self.label_bilan_masse.setText("")
            return
        try:
            pct = float(bilan["pct"])
            seuil = float(bilan["seuil_pct"])
        except (KeyError, TypeError, ValueError):
            self.label_bilan_masse.setText("")
            return
        depasse = abs(pct) > seuil
        couleur = ISL_ROUGE if depasse else ISL_VERT
        self.label_bilan_masse.setText(
            f"Bilan de masse du dernier calcul : "
            f"<b style='color:{couleur}'>{pct:+.3f} %</b> "
            f"(seuil {seuil:g} %)"
            + (" — au-delà du seuil : l'essai est rejeté sans être comparé "
               "à la cible. Resserrer le pas de calcul du plan."
               if depasse else
               " — qualité du calcul, pas écart à la cible."))

    def _remplir_table_suivi(self, apports):
        from qgis.PyQt.QtGui import QColor

        self.table_suivi.setRowCount(len(apports))
        for ligne, a in enumerate(apports):
            statut = a.get("statut", "")
            valeurs = [
                a.get("apport", ""), a.get("section", ""),
                f"{GLYPHE_STATUT.get(statut, '')}  {statut}",
                str(a.get("essais") or ""),
                "—" if a.get("volume_pct") is None else f"{a['volume_pct']} %",
                "—" if a.get("pic_pct") is None else f"{a['pic_pct']} %",
            ]
            for colonne, valeur in enumerate(valeurs):
                cellule = QTableWidgetItem(str(valeur))
                if colonne == 2:
                    cellule.setForeground(QColor(
                        COULEUR_STATUT.get(statut, ISL_ARDOISE)))
                    police = cellule.font()
                    police.setBold(True)
                    cellule.setFont(police)
                if colonne >= 3:
                    cellule.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_suivi.setItem(ligne, colonne, cellule)
        self.table_suivi.resizeColumnsToContents()

    def _onglet_aide(self):
        """
        Mode operatoire et diagnostic. Le contenu reprend la note
        methodologique : mieux vaut l'avoir sous les yeux au moment d'agir
        qu'a cote, dans un document qu'on n'ouvre pas.
        """
        page = QWidget()
        v = QVBoxLayout(page)

        texte = QTextBrowser()
        texte.setOpenExternalLinks(False)
        # Le style de l'aide suit la charte, mais ne fixe aucun fond : le
        # QTextBrowser herite ainsi du theme clair ou sombre de QGIS.
        texte.setHtml(
            f"<style>"
            f"body {{ font-family: {POLICE_ISL}; line-height: 1.5; }}"
            f"h2 {{ color: {ISL_TEAL}; font-size: 14pt; margin-bottom: 1px; }}"
            f"h3 {{ color: {ISL_ARDOISE}; font-size: 10.5pt; "
            f"      margin-top: 18px; margin-bottom: 2px; }}"
            f"p {{ margin-top: 4px; margin-bottom: 4px; }}"
            f"b {{ color: {ISL_TEAL_SOMBRE}; }}"
            f"li {{ margin-bottom: 6px; }}"
            f"tt {{ color: {ISL_ARDOISE}; }}"
            f"</style>" + AIDE_HTML)
        v.addWidget(texte, 1)

        # PARAMETRES DU POSTE.
        #
        # Deux emplacements, et deux seulement. QGIS n'a pas à être désigné :
        # le plugin s'exécute dedans. HEC-RAS non plus : il n'est jamais lancé
        # directement — ras-commander s'en charge, à partir du numéro de
        # version lu dans les fichiers du modèle.
        #
        # Ils sont trouvés tout seuls dans le cas courant. Ce groupe n'existe
        # que pour le cas contraire : sans lui, désigner l'interpréteur
        # supposait de quitter QGIS, modifier une variable d'environnement
        # système et relancer.
        groupe = QGroupBox("Paramètres du poste")
        fp = formulaire(groupe)
        fp.addRow(texte_aide(
            "Détectés automatiquement, et retenus d'une session à l'autre. "
            "À renseigner seulement si le diagnostic les signale absents."))

        self.label_chaine = QLabel("")
        self.label_chaine.setWordWrap(True)
        self.label_chaine.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bouton_chaine = QPushButton("Désigner…")
        bouton_chaine.setToolTip(
            "Dossier contenant criteres.py, geometrie.py, controle_donnees.py, "
            "livrables.py et pont_hecras.py.")
        bouton_chaine.clicked.connect(self._choisir_chaine)
        ligne_chaine = QHBoxLayout()
        ligne_chaine.addWidget(self.label_chaine, 1)
        ligne_chaine.addWidget(bouton_chaine)
        fp.addRow("Chaîne de calage :", ligne_chaine)

        self.label_interpreteur = QLabel("")
        self.label_interpreteur.setWordWrap(True)
        self.label_interpreteur.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        bouton_interp = QPushButton("Désigner…")
        bouton_interp.setToolTip(
            "python.exe d'un environnement disposant de ras-commander et "
            "h5py. C'est lui qui pilote HEC-RAS : QGIS ne peut pas le faire "
            "lui-même, sa bibliothèque HDF5 entre en conflit avec celle de "
            "h5py.")
        bouton_interp.clicked.connect(self._choisir_interpreteur)
        # DÉSIGNER SUPPOSE QU'IL EXISTE DÉJÀ. Sur un poste neuf il n'existe
        # pas, et la seule issue était de taper deux commandes dans une
        # console — ce que le message d'erreur décrivait sans le faire.
        bouton_installer = QPushButton("Installer…")
        bouton_installer.setToolTip(
            "Crée un environnement Python à côté de la chaîne de calage et y "
            "installe ras-commander et h5py. À utiliser sur un poste où "
            "aucun interpréteur convenable n'existe encore.")
        bouton_installer.clicked.connect(self._installer_interpreteur)
        ligne_interp = QHBoxLayout()
        ligne_interp.addWidget(self.label_interpreteur, 1)
        ligne_interp.addWidget(bouton_interp)
        ligne_interp.addWidget(bouton_installer)
        fp.addRow("Interpréteur HEC-RAS :", ligne_interp)

        bouton = QPushButton("Vérifier l'environnement")
        bouton.clicked.connect(self._diagnostic)
        ligne_diag = QHBoxLayout()
        ligne_diag.addWidget(bouton)
        ligne_diag.addStretch(1)
        fp.addRow(ligne_diag)
        self.label_diagnostic = texte_etat()
        fp.addRow(self.label_diagnostic)
        v.addWidget(groupe)
        self._maj_parametres_poste()
        return page

    def _maj_parametres_poste(self):
        """Reflete l'etat courant des deux emplacements."""
        chaine = noyau.trouver_chaine()
        self.label_chaine.setText(
            str(chaine) if chaine
            else f"<span style='color:{ISL_ROUGE}'>introuvable</span>")
        interp = noyau.interpreteur_hecras()
        self.label_interpreteur.setText(
            str(interp) if interp
            else f"<span style='color:{ISL_ROUGE}'>introuvable</span>")

    def _choisir_chaine(self):
        dossier = QFileDialog.getExistingDirectory(
            self, "Dossier de la chaîne de calage")
        if not dossier:
            return
        if not noyau.definir_chaine(dossier):
            QMessageBox.critical(
                self, "Dossier invalide",
                f"« {dossier} » ne contient pas la chaîne de calage.")
            return
        QSettings().setValue(PluginCalage.CLE_CHAINE, str(dossier))
        self._maj_parametres_poste()

    def _choisir_interpreteur(self):
        """
        Designe l'interpreteur, et ne l'enregistre QUE s'il pilote vraiment
        HEC-RAS. Accepter un python quelconque le ferait echouer au premier
        calcul, apres clonage — plusieurs minutes plus tard, et loin de la
        cause.
        """
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Interpréteur Python disposant de ras-commander", "",
            "Exécutable Python (python.exe python3.exe python);;"
            "Tous les fichiers (*)")
        if not chemin:
            return
        ok, message = noyau.definir_interpreteur(chemin)
        if ok:
            QSettings().setValue(PluginCalage.CLE_INTERPRETEUR, str(chemin))
            QMessageBox.information(self, "Interpréteur accepté", message)
        else:
            QMessageBox.critical(
                self, "Interpréteur inutilisable",
                f"« {chemin} » ne peut pas piloter HEC-RAS.\n\n{message}\n\n"
                f"Il lui faut ras-commander et h5py. Le python de QGIS ne "
                f"convient pas : sa bibliothèque HDF5 entre en conflit avec "
                f"celle de h5py.")
        self._maj_parametres_poste()

    @avec_sablier
    def _installer_interpreteur(self):
        """
        Cree l'environnement Python HEC-RAS, apres validation explicite.

        DEUX QUESTIONS, PAS UNE. La premiere dit OU l'on va ecrire et ce que
        l'on va telecharger — un pip install depuis un poste d'entreprise
        n'est pas un geste anodin. La seconde demande le python de BASE : il
        n'est PAS devine, parce que « python » n'existe pas forcement dans le
        PATH d'un poste Windows et que celui de QGIS ne sait pas toujours
        creer un venv utilisable. Deviner ici reviendrait a installer plusieurs
        centaines de mega-octets au mauvais endroit, avec le mauvais Python.

        SUR LE FIL GRAPHIQUE, ET C'EST ASSUME comme les cinq autres methodes
        longues : pip peut prendre plusieurs minutes, le sablier le dit, et
        introduire un thread pour cette seule operation coûterait plus que
        l'attente.
        """
        # emplacement_venv_hecras() rend TOUJOURS un chemin depuis le
        # 31/08/2026 : a cote d'une chaine externe si elle existe, dans le
        # dossier de donnees du greffon sinon. Elle rendait None dans ce
        # second cas, et le bouton refusait donc de servir sur un poste neuf
        # — le seul ou il est utile.
        cible = noyau.emplacement_venv_hecras()
        minimum = ".".join(str(n) for n in noyau.RAS_COMMANDER_MINIMUM)
        with sans_sablier(self):
            reponse = QMessageBox.question(
                self, "Installer l'environnement Python HEC-RAS",
                f"Un environnement Python va être créé dans :\n{cible}\n\n"
                f"puis ras-commander>={minimum} et h5py y seront installés "
                f"depuis PyPI (téléchargement, plusieurs minutes).\n\n"
                f"QGIS restera figé pendant l'opération.\n\nContinuer ?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No)
        if reponse != QMessageBox.StandardButton.Yes:
            return

        with sans_sablier(self):
            base, _ = QFileDialog.getOpenFileName(
                self, "Python de base (python.exe) servant à créer "
                      "l'environnement", "",
                "Exécutable Python (python.exe python3.exe python);;"
                "Tous les fichiers (*)")
        if not base:
            return

        lignes = []
        chemin, message = noyau.installer_interpreteur(base, lignes.append)
        journal = "\n".join(lignes)
        if chemin is None:
            journaliser(f"Installation de l'interpréteur HEC-RAS : {message}")
            boite = QMessageBox(self)
            boite.setIcon(QMessageBox.Icon.Critical)
            boite.setWindowTitle("Installation impossible")
            boite.setText("L'environnement Python HEC-RAS n'a pas pu être "
                          "installé.")
            boite.setDetailedText(f"{journal}\n\n{message}")
            rendre_redimensionnable(boite)
            rendre_la_main(self)
            boite.exec()
            return

        QSettings().setValue(PluginCalage.CLE_INTERPRETEUR, str(chemin))
        self._maj_parametres_poste()
        rendre_la_main(self)
        QMessageBox.information(
            self, "Environnement installé",
            f"Interpréteur HEC-RAS installé et vérifié :\n{chemin}\n\n"
            f"{message}\n\nIl est retenu d'une session à l'autre.")

    def _diagnostic(self):
        """
        Etat de l'environnement, et proposition de designer ce qui manque.

        SEUL CHEMIN DE RECUPERATION quand le plugin est installe depuis une
        archive : son dossier parent est alors le repertoire des extensions
        du profil QGIS, qui ne contient ni la chaine ni l'interpreteur.
        """
        if noyau.trouver_chaine() is None:
            reponse = QMessageBox.question(
                self, "Chaîne de calage introuvable",
                "Le dossier de la chaîne de calage n'a pas été trouvé.\n\n"
                "Installé depuis une archive, le plugin ne peut pas le "
                "deviner : il doit contenir criteres.py, geometrie.py, "
                "controle_donnees.py, livrables.py et pont_hecras.py.\n\n"
                "Le désigner maintenant ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reponse == QMessageBox.StandardButton.Yes:
                self._choisir_chaine()

        if noyau.interpreteur_hecras() is None:
            reponse = QMessageBox.question(
                self, "Interpréteur HEC-RAS introuvable",
                "Aucun interpréteur capable de piloter HEC-RAS n'a été "
                "trouvé.\n\nIl faut un python.exe SÉPARÉ de celui de QGIS, "
                "disposant de ras-commander et h5py. QGIS ne peut pas s'en "
                "charger : sa bibliothèque HDF5 entre en conflit avec celle "
                "de h5py.\n\n"
                "Si vous n'en avez pas encore, dans une invite de commandes :\n\n"
                "    python -m venv %USERPROFILE%\\venv-hecras\n"
                "    %USERPROFILE%\\venv-hecras\\Scripts\\python.exe -m pip "
                f"install \"ras-commander>="
                f"{'.'.join(str(n) for n in noyau.RAS_COMMANDER_MINIMUM)}\" "
                "h5py\n\n"
                "puis désigner ici %USERPROFILE%\\venv-hecras\\Scripts\\"
                "python.exe.\n\n"
                "Le désigner maintenant ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reponse == QMessageBox.StandardButton.Yes:
                self._choisir_interpreteur()

        disponible, messages = noyau.chaine_disponible()
        resume = ("Utilisable : " + ("oui" if disponible else "NON")
                  + "\n" + "\n".join(messages))
        dire(self.label_diagnostic, resume)
        self._maj_parametres_poste()
        QMessageBox.information(self, "Diagnostic", resume)

    @avec_sablier
    def _recontroler_classeur(self):
        """
        Rejoue les controles sur un classeur compose lors d'une autre
        session. Les chemins des shapefiles sont relus DANS le classeur, et
        non repris de la session en cours : c'est ce qui permet de revenir
        sur un paquet sans avoir a recomposer.
        """
        try:
            # str() defensif : Qt n'accepte pas un Path, et il n'y a aucun
            # moyen de savoir a la lecture d'ou vient « classeur ».
            depart = str(self.classeur
                         or self.edit_dossier_sortie.text().strip())
            with sans_sablier(self):
                classeur, _ = QFileDialog.getOpenFileName(
                    self, "Classeur de calage", depart,
                    "Classeur Excel (*.xlsx)")
            if not classeur:
                return
            self.classeur = classeur

            anomalies, tableau, prolongation = noyau.controler_paquet(
                classeur)
            erreurs, avertissements, _ = trier_anomalies(anomalies)
            chemins = noyau.chemins_du_classeur(classeur)
            afficher_pk_sur_carte(chemins, chemins["sens"])

            boite = QMessageBox(self)
            boite.setWindowTitle("Contrôle de l'implantation")
            boite.setIcon(QMessageBox.Icon.Critical if erreurs
                          else QMessageBox.Icon.Information)
            boite.setText(f"{len(erreurs)} erreur(s), "
                          f"{len(avertissements)} avertissement(s)")
            boite.setDetailedText(texte_rapport_controle(anomalies, tableau))
            rendre_la_main(self)
            boite.exec()
            self._proposer_prolongation(prolongation)
            self._maj_onglet_validation_depuis_classeur()
        except Exception as e:
            journaliser("Contrôle d'un classeur existant", e)
            QMessageBox.critical(self, "Contrôle", str(e))

    # --- premier apport a caler ---------------------------------------------

    def _premier_apport(self):
        """Apport de depart choisi, ou chaine vide pour « tous »."""
        combo = getattr(self, "combo_premier_apport", None)
        return "" if combo is None else (combo.currentData() or "")

    def _remplir_premier_apport(self):
        """
        Recharge la liste des apports depuis le classeur.

        Le choix en place est PRESERVE s'il figure toujours dans la nouvelle
        liste : recomposer un paquet ne doit pas remettre en silence le calage
        au premier apport.
        """
        combo = getattr(self, "combo_premier_apport", None)
        if combo is None or not self.classeur:
            return
        try:
            paires = noyau.apports_du_classeur(self.classeur)
        except Exception as e:                              # noqa: BLE001
            journaliser("Lecture des apports du classeur", e)
            dire(self.label_premier_apport,
                 f"(liste des apports illisible : {e})")
            return
        avant = self._premier_apport()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("— tous, de l'amont vers l'aval —", "")
        for apport, section in paires:
            combo.addItem(f"{apport} → {section}", apport)
        combo.setCurrentIndex(
            next((i for i, (a, _) in enumerate(paires, start=1) if a == avant),
                 0))
        combo.blockSignals(False)
        self._dire_premier_apport()

    def _dire_premier_apport(self, *_):
        """Enonce la conséquence du choix, en toutes lettres."""
        if not hasattr(self, "label_premier_apport"):
            return
        premier = self._premier_apport()
        if not premier:
            dire(self.label_premier_apport,
                 "Tous les apports seront calés, à partir d'un calcul de "
                 "référence « sans apport ».")
            return
        try:
            noms = [a for a, _ in noyau.apports_du_classeur(self.classeur)]
            amont = noms[:noms.index(premier)]
        except Exception as e:                              # noqa: BLE001
            journaliser("Apports en amont du premier apport", e)
            amont = []
        dire(self.label_premier_apport,
             f"Départ du plan « Apport_{amont[-1]} ». "
             f"{len(amont)} apport(s) amont tenus pour calés et non "
             f"retouchés : {', '.join(amont)}."
             if amont else
             "Premier apport de la liste : le calage part du calcul de "
             "référence « sans apport », comme sans ce réglage.")

    def _maj_onglet_validation_depuis_classeur(self):
        """Rafraichit l'onglet 4 apres un controle sur classeur existant."""
        self._remplir_premier_apport()
        try:
            etat = noyau.etat_cibles(self.classeur)
        except Exception as e:
            journaliser("État des cibles après contrôle", e)
            return
        self.label_validation_classeur.setText(str(self.classeur))
        manquantes = etat.get("manquantes") or []
        self.label_validation_cibles.setText(
            f"{etat['renseignees']}/{etat['total']} renseignée(s)"
            + (f" — manquantes : {', '.join(manquantes)}" if manquantes else ""))

    @avec_sablier
    def _lancer_calage(self):
        """
        Lance la boucle de calage complete en arriere-plan. Ne bloque JAMAIS
        QGIS : le sous-processus est detache, et le suivi (§ 4.3) est le
        moyen normal de savoir ou en est le calcul pendant qu'il tourne.
        """
        if not self.classeur:
            QMessageBox.information(
                self, "Calage",
                "Composer d'abord le paquet (bouton « Composer et "
                "contrôler »).")
            return
        try:
            etat = noyau.etat_cibles(self.classeur)
        except Exception as e:
            journaliser("État des cibles avant lancement", e)
            QMessageBox.critical(self, "Calage", str(e))
            return
        # LE PREMIER APPORT EST UN REGLAGE DE LANCEMENT, pas de composition :
        # on l'ecrit dans le classeur juste avant de partir. Sans cela, le
        # choix fait apres la composition — ou apres la reouverture d'un
        # classeur d'un calcul precedent — serait ignore en silence.
        try:
            noyau.ecrire_parametre(self.classeur, "Premier_apport",
                                   self._premier_apport())
        except Exception as e:
            journaliser("Écriture du paramètre Premier_apport", e)
            QMessageBox.critical(
                self, "Premier apport",
                f"Le premier apport à caler n'a pas pu être écrit dans le "
                f"classeur : {e}\n\nLe calage n'est pas lancé — il serait "
                f"parti sur un réglage autre que celui affiché.")
            return
        if etat["manquantes"]:
            with sans_sablier(self):
                reponse = QMessageBox.question(
                    self, "Hydrogrammes cibles incomplets",
                    f"{len(etat['manquantes'])} section(s) sans hydrogramme "
                    f"cible exploitable : {', '.join(etat['manquantes'])}.\n\n"
                    f"Le calage sur ces apports ne peut pas démarrer sans "
                    f"cible. Lancer quand même (les apports concernés seront "
                    f"ignorés) ?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No)
            if reponse != QMessageBox.StandardButton.Yes:
                return
        try:
            info = noyau.lancer_calage(self.classeur)
        except Exception as e:
            journaliser("Lancement du calage", e)
            QMessageBox.critical(self, "Lancement du calage", str(e))
            return
        # LIBELLES : « Échec au démarrage : <chemin> » se lisait comme une
        # annonce d'échec alors que le calage venait de partir. Un chemin ne
        # doit jamais être introduit par un mot qui décrit un état.
        message = (
            f"Calage lancé en arrière-plan (PID {info['pid']}).\n"
            f"Suivre l'avancement dans l'onglet 5 « Suivi », qui se rafraîchit "
            f"tout seul.\n"
            f"Journal de lancement : {info['journal']}")
        dire(self.label_lancement, message)
        QMessageBox.information(self, "Calage lancé", message)
        # On bascule sur le suivi : c'est là que la suite se passe. Le
        # changement d'onglet démarre lui-même le rafraîchissement.
        if hasattr(self, "onglets") and hasattr(self, "minuteur_suivi"):
            self.onglets.setCurrentIndex(ONGLET_SUIVI)

    def _proposer_prolongation(self, prolongation):
        """
        Offre de prolonger les hydrogrammes cibles par des ZEROS quand ils
        s'arretent avant la fin de la simulation.

        APRES LE COMPTE RENDU, JAMAIS PENDANT. Le controle vient de dire ce
        qui ne va pas ; cette question propose de le corriger. Les enchainer
        dans la meme boite melangerait un constat et une action.

        LE GESTE EST ECRIT DANS LE CLASSEUR, PAS DANS LE MODELE. On ne touche
        qu'a ce qui est a nous : une condition limite du modele source trop
        courte est signalee, jamais reparee d'office.
        """
        if not isinstance(prolongation, dict):
            return
        try:
            duree = float(prolongation["duree_h"])
        except (KeyError, TypeError, ValueError):
            return
        apports = prolongation.get("apports") or []

        with sans_sablier(self):
            reponse = QMessageBox.question(
                self, "Hydrogrammes cibles trop courts",
                f"{len(apports)} hydrogramme(s) cible(s) s'arrêtent avant la "
                f"fin de la simulation ({duree:.2f} h) : "
                f"{', '.join(apports[:8])}"
                + ("…" if len(apports) > 8 else "")
                + f".\n\nHEC-RAS refuserait de calculer.\n\n"
                f"Prolonger ces colonnes jusqu'à {duree:.2f} h en les "
                f"complétant par des ZÉROS ?\n\n"
                f"Une crue arrêtée avant la fin de sa fenêtre est retombée : "
                f"zéro est la valeur juste, et non la dernière connue. Seule "
                f"la feuille Cibles du classeur est modifiée.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No)
        if reponse != QMessageBox.StandardButton.Yes:
            return
        try:
            bilan = noyau.prolonger_cibles(self.classeur, duree)
        except Exception as e:
            journaliser("Prolongation des hydrogrammes cibles", e)
            QMessageBox.critical(
                self, "Prolongation",
                f"Les hydrogrammes cibles n'ont pas pu être prolongés : {e}\n\n"
                f"Le classeur est inchangé. Compléter la feuille Cibles à la "
                f"main, ou raccourcir la fenêtre de simulation du plan.")
            return
        QMessageBox.information(
            self, "Prolongation",
            f"{bilan['ajoutees']} pas de temps ajoutés à "
            f"{len(bilan['colonnes'])} colonne(s), de "
            f"{bilan['duree_avant_h']:.2f} h à {bilan['duree_apres_h']:.2f} h, "
            f"au pas de {60 * bilan['pas_h']:g} min.\n\n"
            f"Relancer « Composer et contrôler » pour vérifier.")

    def _ouvrir_classeur(self):
        if not self.classeur:
            QMessageBox.information(
                self, "Classeur",
                "Composer d'abord le paquet (bouton « Composer et "
                "contrôler » en bas de la fenêtre).")
            return
        try:
            os.startfile(self.classeur)  # noqa: S606 (usage Windows assume)
        except Exception as e:
            journaliser("Ouverture du classeur", e)
            QMessageBox.critical(self, "Ouverture du classeur", str(e))

    def _maj_onglet_validation(self):
        """
        Actualise l'onglet 4 apres une composition reussie : ce qui est cale,
        ce qui ne l'est pas, et combien d'hydrogrammes cibles restent a
        saisir avant de pouvoir lancer.

        NE COMPTE RIEN. L'ancien message comparait le NOMBRE de sections a
        celui des lignes d'injection et annoncait une incoherence des qu'ils
        differaient : il comptait donc comme apports les debits d'entree
        permanents et les conditions limites aval, qui n'ont pas de section
        attitree, et criait a l'erreur sur un paquet parfaitement valide.
        Seul l'appariement fait foi, et il est deja calcule.
        """
        appariement = getattr(self, "appariement", None) or {}
        paires = appariement.get("paires") or []
        hors = appariement.get("sans_section") or []
        texte = (f"{len(paires)} apport(s) à caler, appariés à leur section : "
                 + ", ".join(f"{a} → {s}" for a, s in paires[:6])
                 + ("…" if len(paires) > 6 else ""))
        if hors:
            texte += (f"\n{len(hors)} ligne(s) d'injection non calée(s), faute "
                      f"de section en aval — entrées permanentes ou exutoires : "
                      + ", ".join(n for n, _ in hors[:6])
                      + ("…" if len(hors) > 6 else ""))
        self.label_validation_comptes.setText(texte)
        self.label_validation_comptes.setWordWrap(True)
        self.label_validation_classeur.setText(str(self.classeur))
        self._remplir_premier_apport()

        try:
            etat = noyau.etat_cibles(self.classeur)
        except Exception as e:
            journaliser("État des cibles (onglet Lancer)", e)
            self.label_validation_cibles.setText(f"(illisible : {e})")
            return

        self.label_validation_cibles.setText(
            f"{etat['renseignees']} / {etat['total']} section(s) déjà "
            f"renseignée(s)"
            + (f" — manquent : {', '.join(etat['manquantes'])}"
               if etat["manquantes"] else ""))

        if etat["manquantes"]:
            dire(self.label_prochaine_etape,
                 "<b>Étape suivante</b> — ouvrir le classeur et compléter la "
                 "feuille « Cibles » pour " + ", ".join(etat["manquantes"])
                 + ", puis lancer. Recomposer plus tard préserve les "
                   "hydrogrammes déjà saisis.")
        else:
            dire(self.label_prochaine_etape,
                 f"<b style='color:{ISL_VERT}'>Tous les hydrogrammes cibles "
                 f"sont renseignés</b> — le calage peut être lancé.")
        self.onglets.setCurrentIndex(ONGLET_LANCER)

    # --- resume, mis a jour a chaque changement pertinent -------------------

    def _maj_resume(self, *_):
        """
        Rafraichit le resume. Appele par des SIGNAUX, dont certains partent
        du registre des couches de QGIS : il peut donc s'executer alors que
        la fenetre vient d'etre fermee, ou qu'une couche vient d'etre
        detruite. Ce n'est qu'un affichage — une trace dans le journal de
        QGIS pour cela serait disproportionnee.

        Le filet ne couvre QUE RuntimeError, l'erreur que Qt leve quand on
        touche un objet C++ detruit. Un except Exception attraperait aussi
        les vraies fautes de logique, et les cacherait.
        """
        try:
            self._composer_resume()
        except RuntimeError:
            return

    def _composer_resume(self):
        if not hasattr(self, "texte_resume"):
            return  # onglet 3 pas encore construit lors du tout premier appel
        if hasattr(self, "label_fil"):
            self._maj_fil()
        lignes = []
        if self.info_projet:
            lignes.append(f"Projet HEC-RAS : {self.info_projet['nom_projet']}"
                          f"  ({self.edit_dossier_hecras.text()})")
        plan = self.combo_plan.currentData()
        if plan:
            lignes.append(f"Plan de référence : p{plan['numero']} — {plan['titre']}")
        ng, nu = self._geometrie_effective(), self._unsteady_effective()
        surcharge = self.radio_override.isChecked()
        if ng:
            lignes.append(f"Géométrie : g{ng}"
                          + ("  (surchargée)" if surcharge else "  (du plan)"))
        if nu:
            lignes.append(f"Unsteady Flow : u{nu}"
                          + ("  (surchargé)" if surcharge else "  (du plan)"))
        if self.combo_zone_2d.count():
            lignes.append(f"Zone d'écoulement 2D : {self.combo_zone_2d.currentText()}")
        if hasattr(self, "label_fenetre"):
            lignes += self._resume_fenetre()
        # Les couches peuvent avoir ete retirees du projet depuis leur
        # chargement : la fenetre n'est pas modale, c'est un cas normal.
        c_sections = couche_vivante(self.couche_sections)
        c_injections = couche_vivante(self.couche_injections)
        if c_sections is not None:
            lignes.append(f"Sections de contrôle : "
                          f"{c_sections.featureCount()} entité(s)")
        if c_injections is not None:
            lignes.append(f"Lignes d'injection : "
                          f"{c_injections.featureCount()} entité(s)")

        axe = couche_vivante(
            self.combo_axe.currentLayer() if hasattr(self, "combo_axe") else None)
        lignes.append(f"Axe hydraulique : {axe.name() if axe else '(non choisi)'}")

        dossier_sortie = self.edit_dossier_sortie.text().strip()
        if dossier_sortie:
            racine = Path(dossier_sortie)
            sous_resultats = self.edit_sous_dossier_resultats.text().strip() or "resultats_finaux"
            sous_suivi = self.edit_sous_dossier_suivi.text().strip() or "suivi"
            lignes += ["", f"Paquet (SHP + classeur) : {racine}",
                      f"Résultats finaux : {racine / sous_resultats}",
                      f"Suivi (avancement) : {racine / sous_suivi}"]

        self.texte_resume.setPlainText("\n".join(lignes) if lignes
                                       else "(rien de configuré pour le moment)")

    # --- composition et controle --------------------------------------------

    @avec_sablier
    def _composer_et_controler(self):
        try:
            if not self.info_projet:
                raise ValueError(
                    "Onglet 1 : choisir d'abord le dossier du projet HEC-RAS.")
            plan = self.combo_plan.currentData()
            if plan is None:
                raise ValueError("Onglet 1 : choisir un plan de référence.")
            c_sections = couche_vivante(self.couche_sections)
            c_injections = couche_vivante(self.couche_injections)
            if c_sections is None or c_injections is None:
                raise ValueError(
                    "Onglet 1 : cliquer sur « Charger les couches du modèle » "
                    "avant de composer. Si elles avaient été chargées, c'est "
                    "qu'elles ont été retirées du projet depuis — les "
                    "recharger.")
            axe = self.combo_axe.currentLayer()
            if axe is None:
                raise ValueError(
                    "Onglet 2 : choisir la couche de l'axe hydraulique.")
            dossier_sortie = self.edit_dossier_sortie.text().strip()
            if not dossier_sortie:
                raise ValueError("Onglet 3 : choisir le dossier de sortie.")

            # Ecrit les couches QGIS dans la geometrie HEC-RAS AVANT de
            # composer le paquet : les sections doivent etre DANS le modele
            # pour que le calage ait un endroit ou lire un debit. Onglet 1,
            # ex-bouton « Ecrire dans la geometrie » — desormais automatique
            # a chaque composition, en mode remplacement systematique.
            try:
                self._ecrire_dans_geometrie()
            except Exception as e:
                dire(self.label_ecriture,
                     f"<span style='color:{ISL_ROUGE}'>Échec : {e}</span>")
                raise

            g_sections = couche_vers_gdf(c_sections)
            g_apports = couche_vers_gdf(c_injections)
            champ_axe = self.champ_axe.currentField() or None
            g_axe = couche_vers_gdf(axe, champ_nom=champ_axe)

            crs = QgsCoordinateReferenceSystem(self.crs_modele or "EPSG:2154")
            if crs.isGeographic():
                raise ValueError(
                    f"le modèle est en coordonnées géographiques "
                    f"({self.crs_modele}) : impossible de calculer des PK. "
                    f"Une projection métrique est indispensable.")

            self.paquet = noyau.composer_paquet(
                dossier_sortie, g_sections, g_apports, g_axe,
                crs_cible=self.crs_modele)

            zone = self.combo_zone_2d.currentText() or ""
            sous_resultats = (self.edit_sous_dossier_resultats.text().strip()
                              or "resultats_finaux")
            sous_suivi = self.edit_sous_dossier_suivi.text().strip() or "suivi"

            # LES NOMS DE CLE SONT DANS LE NOYAU, pas ici : la fenetre lit
            # ses widgets, le noyau tient le contrat. Voir
            # noyau.parametres_calage, qui s'eprouve en console.
            parametres = noyau.parametres_calage(
                dossier_projet=self.edit_dossier_hecras.text().strip(),
                nom_projet=self.info_projet["nom_projet"],
                version_hecras=self.version_hecras,
                nom_zone_2d=zone,
                numero_plan=plan["numero"],
                numero_geometrie=self._geometrie_effective(),
                numero_unsteady=self._unsteady_effective(),
                mode_selection=("override" if self.radio_override.isChecked()
                                else "plan"),
                nom_clone_geometrie=NOM_CLONE_GEOMETRIE_DEFAUT,
                premier_apport=self._premier_apport(),
                sens_axe=self.combo_sens_axe.currentText(),
                pk_origine_m=self.spin_pk_origine.value(),
                nb_max_iterations=self.spin_nb_max_essais.value(),
                tolerance_volume_pct=self.spin_tol_volume.value(),
                tolerance_pic_pct=self.spin_tol_pic.value(),
                bilan_masse_max_pct=self.spin_bilan_masse.value(),
                dossier_sortie=dossier_sortie,
                sous_dossier_resultats=sous_resultats,
                sous_dossier_suivi=sous_suivi,
                fenetre=self._parametres_fenetre(),
            )
            # Chaque section prend la PREMIERE injection en amont d'elle.
            # Les lignes d'injection d'un modele ne sont pas toutes des
            # apports a caler : s'y trouvent aussi les debits d'entree
            # permanents et les conditions limites aval, qui n'ont pas de
            # section attitree et ne doivent donc pas etre comptes.
            self.appariement = noyau.apparier_paquet(
                self.paquet, sens=parametres["Sens_axe"],
                pk_origine=parametres["PK_origine_m"])
            if self.appariement["sans_apport"]:
                orphelines = ", ".join(
                    n for n, _ in self.appariement["sans_apport"])
                raise ValueError(
                    f"aucune ligne d'injection en amont de : {orphelines}. "
                    f"Une section de contrôle sans apport en amont ne peut pas "
                    f"être calée. Vérifier le sens de l'axe hydraulique et la "
                    f"position des objets.")
            if self.appariement["partagees"]:
                detail = "; ".join(
                    f"« {a} » pour {', '.join(s)}"
                    for a, s in self.appariement["partagees"].items())
                raise ValueError(
                    f"une même injection alimenterait plusieurs sections : "
                    f"{detail}. La méthode cale un apport contre UNE cible : "
                    f"ajouter une injection, ou retirer une section.")

            # Pente de la ligne d'energie, PRE-REMPLIE par apport depuis le
            # profil en long du modele. C'est la valeur que le calage aurait
            # deduite d'une case vide : l'ecrire ne change aucun resultat,
            # mais rend l'hypothese lisible et corrigeable dans le classeur.
            # Vide si la geometrie n'est pas encore pretraitee par HEC-RAS.
            #
            # LE MOTIF EST AFFICHE, jamais avale. Le calcul passe par le pont
            # (h5py est inutilisable dans QGIS) : quand il n'aboutit pas, la
            # colonne reste vide, et l'utilisateur doit savoir POURQUOI plutot
            # que de croire que le pre-remplissage n'existe pas.
            pentes, motif_pentes = noyau.pentes_locales_apports(
                parametres["Dossier_projet_HECRAS"], parametres["Nom_projet"],
                parametres["Geometrie_reference"], self.paquet["axe"],
                parametres["Nom_zone_2D"],
                self.appariement.get("pk_apports"))

            # str(), PAS Path : Qt refuse un Path la ou il attend une chaine,
            # et QFileDialog.getOpenFileName leve « argument 3 has unexpected
            # type 'WindowsPath' » — ce qui rendait « Reprendre un classeur
            # d'un calcul precedent… » inutilisable des qu'un paquet venait
            # d'etre compose.
            self.classeur = str(noyau.preparer_classeur(
                dossier_sortie, self.appariement["paires"],
                self.paquet, parametres=parametres, pentes=pentes))

            # Les sous-dossiers de resultats existent des la composition :
            # l'utilisateur les voit, meme avant le premier calcul.
            (Path(dossier_sortie) / sous_resultats).mkdir(parents=True, exist_ok=True)
            (Path(dossier_sortie) / sous_suivi).mkdir(parents=True, exist_ok=True)

            anomalies, tableau, prolongation = noyau.controler_paquet(
                self.classeur)
            erreurs, avertissements, _ = trier_anomalies(anomalies)
            afficher_pk_sur_carte(self.paquet, parametres["Sens_axe"],
                                  self.crs_modele)

            boite = QMessageBox(self)
            boite.setWindowTitle("Composition et contrôle")
            boite.setIcon(QMessageBox.Icon.Critical if erreurs else QMessageBox.Icon.Information)
            boite.setText(f"Paquet composé dans {dossier_sortie}\n"
                          f"{len(erreurs)} erreur(s), "
                          f"{len(avertissements)} avertissement(s)"
                          + (f"\nPente des apports : {len(pentes)}/"
                             f"{len(self.appariement['paires'])} pré-remplie(s)"
                             + (f" — {motif_pentes}" if motif_pentes else "")))
            boite.setDetailedText(texte_rapport_controle(anomalies, tableau))
            rendre_redimensionnable(boite)
            # Le travail est fini : le compte rendu se lit sans sablier.
            rendre_la_main(self)
            boite.exec()
            self._proposer_prolongation(prolongation)
            self._maj_resume()
            self._maj_onglet_validation()
        except Exception as e:
            journaliser("Composition et contrôle du paquet", e)
            QMessageBox.critical(self, "Composition", str(e))


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------

class PluginCalage:
    """Barre d'outils « Calage des apports »."""

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.menu = f"&{NOM_PLUGIN}"
        self.paquet = {}          # chemins du dernier paquet compose
        self.classeur = None

    # --- cycle de vie QGIS -------------------------------------------------

    def initGui(self):  # noqa: N802
        self._restaurer_chaine()
        icone = QIcon(os.path.join(DOSSIER, "icon.png"))
        # UNE SEULE ENTREE. Tout tient dans la fenetre : ecriture dans la
        # geometrie (onglet 1), relecture d'un hydrogramme (onglet 3),
        # recontrole d'un classeur (onglet 4), aide et diagnostic (onglet
        # Aide). Un menu a rallonge laissait croire qu'il fallait choisir,
        # alors qu'il n'y a qu'un chemin — et ses entrees numerotees
        # suggeraient l'inverse de l'ordre reel, ou l'ecriture des sections
        # dans le modele precede la composition du paquet.
        action = QAction(icone, f"{NOM_PLUGIN}\u2026",
                         self.iface.mainWindow())
        action.setObjectName("calageApports_fenetre")
        infobulle = ("Fen\u00eatre unique : mod\u00e8le HEC-RAS, \u00e9criture des "
                     "sections et des apports, profil en long, sorties, aide, "
                     "puis lancement du calage.")
        action.setToolTip(infobulle)
        action.setStatusTip(infobulle)
        action.triggered.connect(self.composer)
        self.iface.addPluginToVectorMenu(self.menu, action)
        self.actions.append(action)

        self.barre = self.iface.addToolBar(NOM_PLUGIN)
        self.barre.setObjectName("calageApportsToolbar")
        # Une seule entree : tout le deroulement normal passe par la fenetre.
        self.barre.addAction(self.actions[0])

    def unload(self):
        """
        Defait ce que initGui a fait — l'essentiel, sinon tout.

        ET L'ENTREE DE MENU AVEC. iface.addToolBar() n'ajoute pas qu'un
        QToolBar : il place aussi son toggleViewAction() dans le menu
        Vue > Barres d'outils, que removeToolBar() ne touche pas. Une case a
        cocher « Calage des apports » y survivait donc au dechargement, et un
        rechargement en ajoutait une seconde. On retrouve l'action dans les
        menus de la fenetre principale et on l'en retire — par l'action
        elle-meme, jamais par le nom du menu, qui est un detail interne de
        QGIS.

        LA FENETRE D'ABORD. Elle est NON MODALE et conservee d'une ouverture a
        l'autre : la fermer ne la detruit pas. Elle survivait donc au
        dechargement, cablee sur un module qui n'existe plus, et son premier
        clic executait du code decharge. C'est le scenario ordinaire du
        developpement avec Plugin Reloader.

        LA BARRE D'OUTILS ENSUITE. « del self.barre » ne larguait que la
        reference Python. Selon l'annotation SIP de iface.addToolBar(), le
        QToolBar peut rester parente a la fenetre principale de QGIS : il
        survivait alors au dechargement, et chaque rechargement en ajoutait un
        second. removeToolBar() le retire de la disposition et le masque sans
        rien detruire — ce qui vaut dans les DEUX cas de figure, et n'expose
        a aucune double liberation.

        LE CHEMIN D'IMPORT ENFIN : noyau l'a modifie des son import, il n'y a
        pas de raison de le laisser modifie apres.
        """
        fenetre = getattr(self, "fenetre", None)
        if fenetre is not None:
            try:
                fenetre.close()
            except RuntimeError:
                pass                     # objet Qt deja detruit cote C++
            self.fenetre = None

        for action in self.actions:
            self.iface.removePluginVectorMenu(self.menu, action)
        self.actions = []

        barre = getattr(self, "barre", None)
        fenetre_principale = self.iface.mainWindow()
        if barre is not None:
            if fenetre_principale is not None:
                try:
                    bascule = barre.toggleViewAction()
                    for menu in fenetre_principale.findChildren(QMenu):
                        if bascule in menu.actions():
                            menu.removeAction(bascule)
                    fenetre_principale.removeToolBar(barre)
                except RuntimeError:
                    pass
            del self.barre

        noyau.detacher()

    # --- utilitaires d'interface -------------------------------------------

    def composer(self):
        """
        Ouvre la fenêtre de paramétrage.

        NON MODALE, et c'est essentiel : le travail consiste précisément à
        dessiner des sections et des lignes d'injection dans QGIS pendant que
        la fenêtre est ouverte. Une fenêtre modale bloque la carte, et
        obligerait à fermer, dessiner, rouvrir, tout resaisir. Les listes de
        couches étant des QgsMapLayerComboBox, elles voient apparaître les
        nouvelles couches sans qu'il y ait rien à rafraîchir.

        La référence est conservée sur le plugin : un QDialog affiché par
        show() et non retenu serait ramassé par le garbage collector et
        disparaîtrait aussitôt.
        """
        if getattr(self, "fenetre", None) is not None:
            try:
                self.fenetre.show()
                self.fenetre.raise_()
                self.fenetre.activateWindow()
                return
            except RuntimeError:
                self.fenetre = None      # objet Qt detruit entre-temps

        self.fenetre = DialogueParametrage(self.iface)
        self.fenetre.setModal(False)
        self.fenetre.setWindowModality(Qt.WindowModality.NonModal)
        self.fenetre.finished.connect(self._recuperer_resultats)
        self.fenetre.show()
        self.fenetre.raise_()
        self.fenetre.activateWindow()

    def _recuperer_resultats(self, *_):
        """Recupere classeur et chemins a la fermeture de la fenetre."""
        if getattr(self, "fenetre", None) is None:
            return
        if self.fenetre.classeur:
            self.classeur = self.fenetre.classeur
            self.paquet = self.fenetre.paquet

    CLE_CHAINE = "calage_apports/dossier_chaine"
    CLE_INTERPRETEUR = "calage_apports/interpreteur"

    def _restaurer_chaine(self):
        """
        Rétablit les emplacements désignés lors d'une session précédente.

        L'interpréteur est rétabli SANS le revérifier : le contrôle lance un
        sous-processus, et le faire à chaque ouverture de QGIS retarderait le
        démarrage pour un cas — un environnement devenu invalide entre deux
        sessions — que le diagnostic signale de toute façon.

        Un dossier de chaîne désigné à la main est rétabli même quand la
        détection automatique aboutit : c'est le seul moyen d'imposer une
        chaîne que le rang fixe ne retiendrait pas — la détection ne compare
        plus aucune date depuis la 0.4.0. definir_chaine() refuse un dossier
        disparu, et la détection reprend alors la main.
        """
        memorise = QSettings().value(self.CLE_CHAINE)
        if memorise:
            noyau.definir_chaine(memorise)

        if noyau.interpreteur_hecras() is None:
            noyau.restaurer_interpreteur(QSettings().value(self.CLE_INTERPRETEUR))
