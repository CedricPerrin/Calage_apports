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
import hashlib
import html
import inspect
import os
import shutil
import tempfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsFillSymbol,
    QgsFields,
    QgsGeometry,
    QgsMeshLayer,
    QgsMessageLog,
    QgsPalLayerSettings,
    QgsProject,
    QgsTextBackgroundSettings,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import (QgsCollapsibleGroupBox, QgsFieldComboBox, QgsGui,
                      QgsMapLayerComboBox, QgsMessageBar)
from qgis.PyQt.QtCore import (QEvent, QMetaType, QPointF, QRectF, QSettings,
                              QSizeF, Qt, QTimer)
from qgis.PyQt.QtGui import (QColor, QCursor, QFont, QFontDatabase, QFontMetrics,
                             QIcon, QKeySequence, QPainter, QPalette, QPen,
                             QPolygonF, QTextCursor)
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QAction,
    QApplication,
    QCheckBox,
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
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from . import cpn, lexique, materiel, noyau, registre
from .bande import Bande
from .installation import TacheInstallation, TacheRecherchePython, installation_en_cours
from .interface import Etiquette as QLabel, EtiquetteLexique, Manuel as QTextBrowser
from .interface import TableauTriable
from .interface import couleur as couleur_theme, sombre as fond_sombre
from .interface import feuille as feuille_interface

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
# Borne du titre d'un plan d'etape, copie de calage.LONGUEUR_MAX_TITRE_PLAN
# (la chaine n'est pas importable dans le processus QGIS).
LONGUEUR_MAX_TITRE = 32
# IN_... et OUT_... restent aux entrees permanentes et aux exutoires, qui ne
# sont pas cales : c'est deja l'usage du modele d'essai, et il est parlant.



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


def styler_emprise(couche):
    """
    L'emprise 2D : un CONTOUR ROUGE, AUCUN REMPLISSAGE (21/09/2026, demande
    utilisateur).

    Elle arrivait avec le style par defaut de QGIS — un aplat de couleur
    tiree au hasard — et masquait tout ce qu'on vient regarder dessous : le
    maillage, les sections de controle, les lignes d'injection. C'est un
    CONTOUR qu'on veut voir, pas une surface : l'emprise sert a savoir ou
    finit la zone de calcul.

    EN CODE, PAS EN .qml. Les trois autres couches ont un style livre parce
    qu'elles portent des etiquettes, des regles et des largeurs a regler.
    Ici il y a deux proprietes : un fichier de cent lignes de XML lie a une
    version de QGIS couterait plus qu'il ne dirait.

    Retourne (applique, message), comme appliquer_style.
    """
    couche = couche_vivante(couche)
    if couche is None:
        return False, "couche absente"
    try:
        symbole = QgsFillSymbol.createSimple({
            # « no » suffit a Qt, mais une couleur transparente en plus evite
            # qu'un theme ou un export ne rende un aplat par repli.
            "style": "no",
            "color": "0,0,0,0",
            "outline_color": "227,26,28,255",
            "outline_width": "0.6",
            "outline_style": "solid",
        })
        couche.renderer().setSymbol(symbole)
        couche.setOpacity(1.0)
        couche.triggerRepaint()
    except Exception as e:                                  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    return True, ""


def etiqueter(couche, expression):
    """
    Etiquette horizontale sur fond blanc : rectangle a angles arrondis
    (rayon 3 mm), trait gris (27/10/2026, demande utilisateur). Le nom reste
    lisible sur le maillage comme sur un fond de plan.
    """
    reglages = QgsPalLayerSettings()
    reglages.fieldName = expression
    reglages.isExpression = True
    # HORIZONTALE : une section de controle est souvent tracee en travers
    # du lit, donc presque verticale, et une etiquette parallele s'y
    # lirait mal.
    reglages.placement = Qgis.LabelPlacement.Horizontal
    fond = QgsTextBackgroundSettings()
    fond.setEnabled(True)
    fond.setType(QgsTextBackgroundSettings.ShapeType.ShapeRectangle)
    fond.setSizeType(QgsTextBackgroundSettings.SizeType.SizeBuffer)
    fond.setSize(QSizeF(1.0, 0.5))
    fond.setRadii(QSizeF(3.0, 3.0))
    fond.setFillColor(QColor(255, 255, 255))
    fond.setStrokeColor(QColor(128, 128, 128))
    fond.setStrokeWidth(0.3)
    texte = reglages.format()
    texte.setBackground(fond)
    reglages.setFormat(texte)
    couche.setLabeling(QgsVectorLayerSimpleLabeling(reglages))
    couche.setLabelsEnabled(True)
    couche.triggerRepaint()


def appliquer_styles(injections, sections, maillage, emprise=None):
    """Style de chacune des couches ; retourne les echecs eventuels."""
    echecs = []
    if emprise is not None:
        ok, message = styler_emprise(emprise)
        if not ok:
            echecs.append(f"emprise 2D : {message}")
    for couche, nom in ((injections, "injections"), (sections, "sections"),
                        (maillage, "maillage")):
        if couche is None:
            continue
        ok, message = appliquer_style(couche, nom)
        if not ok:
            echecs.append(f"{nom} : {message}")

    # LE NOM PAR DEFAUT, des le chargement ; la composition y ajoute le PK
    # (etiqueter_pk_sur_carte), avec le meme fond. APRES le .qml, qui sans
    # cela effacerait les etiquettes.
    for couche, nom in ((injections, "injections"), (sections, "sections")):
        if couche is None:
            continue
        try:
            etiqueter(couche, '"nom"')
        except Exception as e:                              # noqa: BLE001
            echecs.append(f"{nom} (étiquettes) : {type(e).__name__}: {e}")

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
        (PREFIXE_APPORT, PREFIXE_SECTION ci-dessus ; l'aide la dit en toutes
        lettres, § « Nommer les objets »). A defaut, elles heritaient du nom
        de la couche suivi d'un numero — lisible, mais qui ne dit pas le role
        de l'objet dans le calage.
    noms_pris : noms deja utilises dans le modele, a ne pas reprendre. Deux
        objets homonymes dans une geometrie HEC-RAS rendraient l'appariement
        indecidable.
    """
    import geopandas as gpd
    from shapely import wkt as shapely_wkt

    if couche is None:
        raise ValueError("aucune couche designee")
    if couche.geometryType() != Qgis.GeometryType.Line:
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
        raise ValueError(
            f"« {couche.name()} » : aucune ligne tracée"
            + (" dans la sélection" if selection_seule else "")
            + ". Vérifier le compte rendu de « Charger les couches du "
              "modèle », ou tracer les lignes dans cette couche.")

    return gpd.GeoDataFrame({"nom": noms}, geometry=geometries,
                            crs=couche.crs().authid() or None)


def _couche_memoire_depuis_wkt(nom_couche, entites, crs_authid, type_geometrie,
                               champ):
    """
    Corps commun aux deux fabriques ci-dessous, qui ne differaient que par le
    type de geometrie et le nom de l'attribut — lequel est aussi la cle portee
    par les entites (« nom » pour les lignes, « zone » pour les perimetres).

    Une couche memoire est TOUJOURS editable : c'est ce qui permet de dessiner
    de nouvelles sections directement sur la carte, par-dessus ce qui existe
    deja dans la geometrie HEC-RAS.
    """
    couche = QgsVectorLayer(f"{type_geometrie}?crs={crs_authid}", nom_couche,
                            "memory")
    fournisseur = couche.dataProvider()
    fournisseur.addAttributes([QgsField(champ, TYPE_CHAMP_TEXTE)])
    couche.updateFields()
    objets = []
    for entite in entites:
        f = QgsFeature(couche.fields())
        f.setGeometry(QgsGeometry.fromWkt(entite["wkt"]))
        f[champ] = str(entite[champ])
        objets.append(f)
    if objets:
        fournisseur.addFeatures(objets)
    couche.updateExtents()
    return couche


# LES DEUX NOMS PUBLICS SONT CONSERVES : ils sont passes PAR REFERENCE aux
# appels de _charger_couche (l. 2071-2077) et repris tels quels par
# test_plugin_qgis.py. Les remplacer par un seul appelable parametre aurait
# fait toucher cinq sites pour rien.
def construire_couche_lignes_depuis_wkt(nom_couche, entites, crs_authid):
    """
    Couche MEMOIRE QGIS de lignes a partir d'entites {"nom", "wkt"}, telles
    que renvoyees par noyau.charger_couches_modele().
    """
    return _couche_memoire_depuis_wkt(nom_couche, entites, crs_authid,
                                      "LineString", "nom")


def construire_couche_polygones_depuis_wkt(nom_couche, entites, crs_authid):
    """Meme principe, pour l'emprise (perimetre de zone 2D)."""
    return _couche_memoire_depuis_wkt(nom_couche, entites, crs_authid,
                                      "Polygon", "zone")


# LE MAILLAGE S'AFFICHE DEPUIS UNE COPIE DU .gXX.hdf, JAMAIS DEPUIS CELUI DU
# PROJET. MDAL garde le fichier ouvert tant que la couche existe, et HEC-RAS
# ne peut alors plus le reecrire : « Error writing geometry file (hdf
# version) », boite que le chien de garde de ras-commander ferme, puis un
# calcul sur l'ancien pretraitement. Reproduit le 30/10/2026 sur une copie
# d'un modele dont le .gXX.hdf avait perdu le trace de ses reference lines.
DOSSIER_COPIES_MAILLAGE = Path(tempfile.gettempdir()) / "calage_apports_maillage"


def copie_pour_maillage(chemin_hdf):
    """
    Copie du .gXX.hdf a donner a QgsMeshLayer, ou None : fichier absent
    (geometrie jamais pretraitee) ou copie impossible. Le maillage n'est
    qu'un fond de carte : sans copie, on s'en passe plutot que d'ouvrir
    l'original.

    UN NOM PAR DOSSIER ET PAR VERSION DU FICHIER. La copie precedente reste
    peut-etre ouverte par une couche que QGIS n'a pas encore detruite, et
    Windows refuse d'ecraser un fichier ouvert ; deux projets peuvent aussi
    porter le meme nom de geometrie. Les copies perimees sont effacees des
    qu'elles ne sont plus ouvertes.
    """
    chemin_hdf = Path(chemin_hdf)
    if not chemin_hdf.is_file():
        return None
    etat = chemin_hdf.stat()
    prefixe = (f"{chemin_hdf.stem}."
               f"{hashlib.md5(str(chemin_hdf.parent).encode()).hexdigest()[:8]}")
    copie = DOSSIER_COPIES_MAILLAGE / f"{prefixe}.{etat.st_mtime_ns}.hdf"
    try:
        DOSSIER_COPIES_MAILLAGE.mkdir(parents=True, exist_ok=True)
        if not copie.is_file() or copie.stat().st_size != etat.st_size:
            shutil.copyfile(chemin_hdf, copie)
    except OSError:
        return None
    for perimee in DOSSIER_COPIES_MAILLAGE.glob(f"{prefixe}.*.hdf"):
        if perimee != copie:
            try:
                perimee.unlink()
            except OSError:
                pass
    return copie


# ---------------------------------------------------------------------------
# Charte graphique ISL Ingenierie
#
# Identite ISL UX 0.1 : couleurs INSTITUTIONNELLES de charte/ :
# bleu-vert #3A8D94, ardoise #9BAEB7, gris #707173. Les variantes textuelles
# repondent au contraste ; elles ne recolorent pas le logo. Les pictogrammes
# PIO existants sont autorises, sans reprendre la palette PIO comme habillage.
# La police des controles suit le poste/QGIS ; aucune police de marque embarquee.
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
# UN SEUL BOUTON, SOUS LE PREFIXE (22/09/2026, demande utilisateur) : ecrire
# la geometrie, composer le classeur des hydrogrammes, controler — et le dire.
# Il s'appelait « Ecrire dans la geometrie HEC-RAS » depuis la 0.9.5, quand la
# composition est devenue automatique ; mais l'automatique renonce EN SILENCE
# des qu'un prealable manque, et « Ouvrir dans Excel » restait gris apres le
# prefixe sans que rien ne dise pourquoi.
BOUTON_GEOMETRIE = "Valider la géométrie et générer le fichier des hydrogrammes"
# CE QUI SE PASSE TANT QU'IL N'Y A PAS DE PAQUET — une seule phrase, dite
# aux deux endroits qui l'attendent (etape Lancer, coherence). Elle
# renvoyait a « Ecrire dans la geometrie HEC-RAS » « en bas de la fenetre » :
# le bouton est a l'etape Modele depuis la 0.9.6 et n'a plus rien a voir
# avec la composition, automatique depuis la 0.9.5 (constate le 22/09/2026
# sur le poste de calcul).
ATTENTE_PAQUET = (
    "Aucun paquet composé pour l’instant. Renseignez le modèle, ses couches "
    "et l’axe (étape Modèle), puis le préfixe de scénario (étape Paramètres) — "
    "le dossier de sortie se propose alors de lui-même —, puis cliquez "
    f"« {BOUTON_GEOMETRIE} », sous le préfixe : gris, il dit ce qui manque.")
NOM_CLONE_GEOMETRIE_DEFAUT = "Geometrie_calage"

# Precision attendue, en fraction de la cible. Ce sont les valeurs par defaut
# de la chaine (Configuration) : les redire ici en dur les ferait diverger le
# jour ou la methode changerait.
#
# Elles servent DEUX FOIS : a proposer une valeur de depart a l'onglet 2, et a
# colorer les jauges du suivi quand l'etat publie ne porte pas ses propres
# seuils. La forme ne se saisit pas — elle ne se negocie pas de la meme facon —
# mais elle se juge, d'ou sa presence ici.
# SONDER « tasklist » A CHAQUE BATTEMENT COUTE UN SOUS-PROCESSUS SUR LE FIL
# GRAPHIQUE, toutes les deux secondes, pendant toute la duree du calage. On a
# essaye de s'en passer en tenant pour vivant un avancement.json touche il y a
# moins d'une minute. DEUX RAISONS DE NE PAS LE GARDER, mesurees le 06/09/2026 :
#   - un calage mort juste apres avoir ecrit son etat etait annonce EN COURS
#     pendant cette minute. « Plus personne n'ecrit, et rien ne le dit » est
#     exactement le defaut que la banniere « Calage interrompu » repare ;
#   - et l'economie est illusoire la ou elle compterait : pendant un calcul
#     HEC-RAS de plusieurs heures, le fichier ne bouge pas davantage, donc on
#     sonde de toute facon a chaque battement.
# La friction reste, assumee : elle achete un affichage qui ne ment pas.

TOLERANCE_VOLUME_DEFAUT = 0.05
TOLERANCE_PIC_DEFAUT = 0.02
TOLERANCE_FORME_DEFAUT = 0.03

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


ISL_TEAL = "#3A8D94"          # institutionnel (Pantone 5483 C)
ISL_TEAL_SOMBRE = "#2E7176"
ISL_ARDOISE = "#526B7A"       # variante lisible sur le fond clair de QGIS
ISL_ARDOISE_CLAIR = "#526B7A"  # les étapes en attente restent lisibles
# Hors charte, et volontairement : la charte n'a pas de couleur d'etat, et
# reserver le teal institutionnel a l'erreur le banaliserait. Ces deux tons
# ne servent QU'A dire si une saisie est fautive ou une etape franchie.
ISL_ROUGE = "#A03028"
ISL_VERT = "#386F55"
ISL_VERT_SOMBRE = "#33654E"    # survol du bouton de controle, quand il est vert
POLICE_ISL = '"Helvetica Neue", "Helvetica", "Arial", sans-serif'

# Deux registres de texte, et deux seulement, en plus des libelles de champs :
#   AIDE — une phrase grise sous un groupe, qui explique un choix ;
#   ETAT — le compte rendu de ce qui vient d'etre fait, encadre.
# Les distinguer par un ROLE plutot que par une feuille de style ecrite a
# chaque endroit evite qu'un texte d'aide finisse en corps de texte, ce qui
# etait arrive : la propriete etait posee, mais aucune regle ne la lisait.
ROLE_AIDE = "aide"
ROLE_ETAT = "etat"

# Alias conserv? pour les outils de recette ; la fen?tre lit sa palette QGIS.
STYLE_ISL = feuille_interface(QApplication.palette())


# ---------------------------------------------------------------------------
# Suivi en temps reel — couleurs d'etat
#
# Un calage dure des heures. Ce qui manquait n'est pas l'information — suivi.py
# l'ecrit depuis toujours — mais un endroit ou la voir : le calcul s'arretait
# sans donner de nouvelles. Ces quatre couleurs sont le vocabulaire de
# l'affichage, et il n'y en a pas d'autre.
# ---------------------------------------------------------------------------

# UN CINQUIEME STATUT, QUI NE VIENT PAS DE LA CHAINE : « repris » designe
# un apport que le calage PRECEDENT a cale et que celui-ci ne refait pas.
# Il est pose par l'affichage (_suivi_precedent) a partir du suivi
# archive ; suivi.py ne connait que les quatre autres.
STATUT_REPRIS = "repris"

# « EN COURS » EST LE TEAL SOMBRE, PAS LE TEAL INSTITUTIONNEL (0.8.5). Ces
# teintes servent de couleur de TEXTE — colonne Statut du tableau, ligne de
# position — et « #3A8D94 » sur le fond clair de QGIS rend 3,4:1, sous les
# 4,5:1 que WCAG 1.4.3 demande a un texte de 10 pt ; « #2E7176 » rend 4,9:1.
# Le teal institutionnel reste celui des TRAITS (courbe du suivi), ou 3:1
# suffit. En theme sombre, interface.COULEURS_SOMBRES ramene les deux au
# meme « #7CC4C8 ».
COULEUR_STATUT = {
    "validé": ISL_VERT,
    "en cours": ISL_TEAL_SOMBRE,
    "échoué": ISL_ROUGE,
    "en attente": ISL_ARDOISE_CLAIR,
    STATUT_REPRIS: ISL_ARDOISE,
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


def date_lisible(iso):
    """« 24/10/2026 à 03 h 15 » depuis l'ISO de l'avancement ; le texte tel
    quel s'il ne se lit pas."""
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d/%m/%Y à %H h %M")
    except ValueError:
        return str(iso)


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

        def point(t, q):
            return QPointF(gauche + largeur * (t - t_min) / etendue_t,
                           haut + hauteur * (1.0 - q / (1.08 * q_max)))

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

        # DERRIERE, ET CLIPPEES. Une section calee peut deborder la fenetre de
        # crue courante : sans decoupe, sa polyligne irait ecrire par-dessus
        # les graduations et la legende.
        peintre.setClipRect(QRectF(gauche, haut, largeur, hauteur))
        for courbe in deja:
            peintre.setPen(stylo_avant if courbe.get("anterieur") else stylo_cale)
            peintre.drawPolyline(QPolygonF(
                [point(t, q) for t, q in zip(courbe["temps"],
                                             courbe["debit"])]))
        for temps, debits, stylo in ((tc, qc, stylo_cible), (ts, qs, stylo_mesure)):
            peintre.setPen(stylo)
            peintre.drawPolyline(QPolygonF(
                [point(t, q) for t, q in zip(temps, debits)]))
        peintre.setClipping(False)
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


def courbe_retenue(courbes):
    """
    La serie CALCULEE d'une paire publiee, au format des courbes precedentes.

    Le suivi publie deux choses de forme differente : « courbes », la paire
    cible/section que l'on regarde, et « courbes_precedentes », la famille des
    sections deja calees. Pour rejouer un calage archive, il faut les deux —
    la derniere section validee n'est que dans la premiere. None si la paire
    n'a pas ete validee : un apport en echec ou en recherche n'a pas
    d'hydrogramme retenu, et le tracer laisserait croire a un resultat.
    """
    if not courbes or courbes.get("statut") != "validé":
        return None
    return {"apport": courbes.get("apport"), "section": courbes.get("section"),
            "temps": courbes.get("temps_calcule") or [],
            "debit": courbes.get("debit_calcule") or []}


def plan_de_reprise(apports, valides, premier):
    """
    Ce qu'un lancement CONSERVE et ce qu'il PERD d'un calage precedent.

    apports : tous les apports du classeur, de l'amont vers l'aval.
    valides : ceux que le calage precedent a menes a bien.
    premier : l'apport ou la reprise doit commencer ; vide = tout recaler.

    Rend (conserves, perdus, propose) :
      conserves — deja cales et situes EN AMONT du depart : leurs plans
                  d'etape ne sont pas retouches ;
      perdus    — deja cales et situes A PARTIR du depart : leur calage sera
                  refait, et c'est ce qu'il faut dire avant de lancer ;
      propose   — par ou il serait raisonnable de reprendre quand rien n'est
                  choisi : le PREMIER apport que le calage precedent n'a pas
                  mene a bien. None s'il les a tous valides — on n'a alors
                  aucune raison d'en designer un — et None des qu'un depart
                  est choisi : on ne propose pas ce qui est deja decide.

    L'ORDRE EST CELUI DU CLASSEUR, PAS CELUI DE L'ARCHIVE. Le calage est
    sequentiel de l'amont vers l'aval, et c'est cet ordre-la, et lui seul, qui
    dit ce qui est en amont de quoi.
    """
    valides = set(valides)
    rang = apports.index(premier) if premier in apports else 0
    return ([a for a in apports[:rang] if a in valides],
            [a for a in apports[rang:] if a in valides],
            # « premier » ET NON « premier in apports » : un depart
            # choisi mais introuvable dans le classeur reste un depart
            # choisi. En proposer un second a cote afficherait deux
            # boutons « Reprendre a… » qui ne diraient pas la meme
            # chose.
            None if premier
            else next((a for a in apports if a not in valides), None))


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
# LES CALCULS LONGS RESTENT OU ILS SONT. « Ecrire, composer et controler » enchaine
# trois lancements de sous-processus — chacun demarre un interpreteur qui
# importe h5py et ras-commander — puis l'ecriture de trois shapefiles et d'un
# classeur, puis tous les controles. Tout cela sur le fil graphique, et c'est
# assume : noyau.py n'expose que des operations de quelques secondes, et le
# calage lui-meme part en processus detache.
#
# CE QUI MANQUAIT N'EST PAS LA VITESSE, C'EST LE SIGNAL. Passe quelques
# secondes sans repeindre, Windows grise la fenetre et ajoute « (Ne repond
# pas) » a son titre : rien ne distinguait un plugin qui travaille d'un
# plugin plante, et l'on fermait QGIS au milieu d'une ecriture dans la
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
    """
    Curseur d'attente pendant toute la methode, rendu quoi qu'il arrive.

    L'ENVELOPPE TRANSMET LES ARGUMENTS. Elle ne prenait que « self », et
    _composer_et_controler a recu deux mots-cles en 0.9.5 : le minuteur de
    recomposition l'appelle avec « ecrire_geometrie=False, silencieux=True »,
    ce qui rendait « TypeError: _composer_et_controler() got an unexpected
    keyword argument » — sur le poste de calcul, a la premiere recomposition
    automatique, le 22/09/2026. Jamais au banc : il n'appelait la methode que
    sans argument, et functools.wraps donnait a l'enveloppe le nom de la
    methode, si bien que le message accusait celle-ci. Ce minuteur est
    retire depuis le 24/09/2026 ; la transmission reste, sans appelant a
    mots-cles aujourd'hui.

    ET ELLE NE TRANSMET QUE CE QUE LA METHODE ACCEPTE. Deux methodes au
    sablier sont branchees sur « clicked », qui emet un booleen : PyQt le
    passe a l'enveloppe. Avec « self » seul, PyQt retombait tout seul sur
    l'appel sans argument ; avec « *args », l'enveloppe le passait a la
    methode, qui le refusait — et une exception dans un slot PyQt ne fait pas
    une boite : elle tue le processus (qFatal), sans trace. Le banc mourait
    ainsi, code 9, deux fois de suite, le 22/09/2026. On tronque donc les
    positionnels au nombre que la methode declare — c'est exactement le
    repli que PyQt faisait pour nous.
    """
    parametres = list(inspect.signature(methode).parameters.values())[1:]
    n_positionnels = sum(
        1 for p in parametres
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD))
    varargs = any(p.kind == p.VAR_POSITIONAL for p in parametres)

    @functools.wraps(methode)
    def enveloppe(self, *args, **kwargs):
        if not varargs:
            args = args[:n_positionnels]
        if getattr(self, "_installation_occupe", lambda: False)():
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self._sablier_pose = True
        try:
            return methode(self, *args, **kwargs)
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
    """
    Phrase d'accompagnement : grise, plus petite, jamais indispensable. Ses
    termes techniques renvoient au lexique de l'aide (EtiquetteLexique).
    """
    label = EtiquetteLexique(contenu)
    label.setWordWrap(True)
    label.setProperty("role", ROLE_AIDE)
    if infobulle:
        label.setToolTip(infobulle)
    return label


def texte_etat(contenu=""):
    """
    Compte rendu d'une action, selectionnable a la souris.

    MASQUE tant qu'il n'a rien a dire : un cadre vide sous chaque bouton
    donnait a croire qu'il manquait quelque chose. Ses termes techniques
    renvoient au lexique de l'aide (EtiquetteLexique), d'ou les liens.
    """
    label = EtiquetteLexique(contenu)
    label.setWordWrap(True)
    label.setProperty("role", ROLE_ETAT)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                  | Qt.TextInteractionFlag.LinksAccessibleByMouse)
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
    f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    f.setHorizontalSpacing(12)
    f.setVerticalSpacing(9)
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

# UN SOMMAIRE, PARCE QUE LE TEXTE EST LONG. Dix sections et plus de dix mille
# caracteres, sans un seul lien : le commentaire d'introduction de cet onglet
# dit lui-meme qu'« une aide qu'on fait defiler n'est pas lue davantage qu'une
# aide absente », et il n'y avait aucun moyen d'atteindre la bonne section.
# Les ancres et la liste se deduisent des <h3> ; en ajouter un impose de lui
# donner son ancre et sa ligne, sous peine d'un sommaire qui ment par omission.
AIDE_HTML = """
<h2>Calage des apports — mode opératoire</h2>

<p>L'outil ajuste, un par un et de l'amont vers l'aval, les hydrogrammes
injectés dans un modèle 2D HEC-RAS pour que le débit calculé à chaque section
de contrôle reproduise un hydrogramme cible.</p>

<p style="margin-top:14px"><b>Aller directement à :</b></p>
<ul>
<li><a href="#s1">Première utilisation — ce qu'il faut installer</a></li>
<li><a href="#s2">À trancher avant de commencer</a></li>
<li><a href="#s3">Le déroulement, étape par étape</a></li>
<li><a href="#s4">Écrire dans la géométrie</a></li>
<li><a href="#s5">Comment l'apport est ajusté</a></li>
<li><a href="#s6">Comment lire le résultat</a></li>
<li><a href="#s7">Quand la cible est hors d'atteinte</a></li>
<li><a href="#s8">Nommer les objets</a></li>
<li><a href="#s9">Un apport créé part de zéro</a></li>
<li><a href="#s10">Pièges à connaître</a></li>
<li><a href="#s11">Ce que le calage laisse dans le modèle</a></li>
<li><a href="#s12">Lexique</a></li>
</ul>

<h3><a name="s1"></a>Première utilisation — ce qu'il faut installer</h3>
<p><b>Vous n'avez pas besoin de savoir où Python est installé sur ce poste, ni
même s'il l'est.</b> Dans <i>Diagnostic et paramètres du poste</i>, au-dessus
de ce mode opératoire, cliquez <b>Vérifier l’environnement</b> : il dit ce qui manque et propose
de le poser. Deux choses, et deux seulement :</p>
<ol>
<li>La <b>chaîne de calage</b>. Elle est <i>embarquée dans l'extension</i> :
si le plugin vient de son archive, elle est déjà là et rien n'est à faire.</li>
<li>L'<b>interpréteur HEC-RAS</b>, un Python séparé de celui de QGIS. S'il
manque, le bouton <b>Installer…</b> fait tout : il cherche les Python présents
sur le poste, propose le meilleur, crée l'environnement, y pose la dizaine de
paquets nécessaires, puis <i>vérifie</i> le résultat. Compter plusieurs
centaines de Mo et quelques minutes, pendant lesquelles QGIS reste utilisable.</li>
</ol>
<p><b>Et s'il n'y a aucun Python sur le poste ?</b> Le diagnostic le dit au
lieu d'ouvrir un sélecteur de fichier devant lequel on n'a rien à répondre :
installer Python 3.9 ou plus depuis <tt>python.org</tt> en cochant <i>Add
python.exe to PATH</i>, puis relancer QGIS. Le Python livré <i>avec QGIS</i>
convient également, et le bouton le propose de lui-même.</p>
<p>Les <tt>python.exe</tt> de <tt>WindowsApps</tt> n'en sont pas : ce sont des
fichiers vides qui affichent « Python was not found ». Ils occupent le PATH
sans rien exécuter, et le plugin les écarte.</p>
<p><i>Pourquoi un second Python ?</i> QGIS et HEC-RAS ne peuvent pas partager
la même bibliothèque HDF5 : dans le processus de QGIS, <tt>import h5py</tt>
échoue, et <tt>ras-commander</tt> en dépend. Le calage tourne donc dans un
interpréteur à part. C'est une contrainte mesurée, pas un choix.</p>
<p>Ces deux emplacements sont <b>retenus d'une session à l'autre</b> : cette
étape ne se refait pas.</p>

<h3><a name="s2"></a>À trancher avant de commencer</h3>
<ul>
<li><b>Ordre amont → aval strict ?</b> C'est une <b>hypothèse du
modèle</b> : elle est posée par l'hydraulicien, une fois, avant de commencer,
et <b>rien dans la chaîne ne la vérifie</b>. La méthode ne s'applique pas à un
réseau bouclé — bras qui se rejoignent, casiers interconnectés —, où un apport
alimenterait plusieurs sections par des chemins distincts et où « section
suivante » n'aurait plus de sens. Répondre non ici, c'est engager tout le
reste : les hypothèses de validité sont au § 1.2 de la note
méthodologique.</li>
<li><b>Durée d'un calcul complet ?</b> C'est ce chiffre qui dimensionne
tout : compter 3 à 5 calculs par apport.</li>
<li><b>Hydrogrammes cibles disponibles</b> pour chaque section ?</li>
</ul>

<h3><a name="s3"></a>Le déroulement, étape par étape</h3>
<ol>
<li><b>Modèle.</b> Fichier <tt>.prj</tt> du projet HEC-RAS, plan de référence,
puis
<i>Charger les couches du modèle</i>, puis le <i>profil en long</i> : sections, injections et maillage
s'affichent sur la carte. Y dessiner les sections de contrôle qui manquent —
sans elles, le calage n'a aucun endroit où lire un débit. Elles sont écrites
dans la géométrie par <i>Valider la géométrie et générer le fichier des
hydrogrammes</i>, le bouton de l'étape <i>Paramètres</i> ; un
apport créé reçoit du même coup son hydrogramme dans le fichier
Unsteady&nbsp;Flow, sinon il n'apporterait rien. La fenêtre de simulation n'est à corriger que si l'Unsteady&nbsp;Flow
retenu couvre une <b>autre période</b> que le plan de référence.</li>
<li><b>Paramètres.</b> D'abord la <i>précision du calage</i> : les écarts
admis sur le volume et sur le débit de pointe, et le nombre maximal d'essais.
Puis le <b>dossier de sortie</b>, proposé tout seul, et le <b>préfixe de scénario</b>,
qui est <b>obligatoire</b> — il nomme les plans de ce calage-ci comme le fichier
Excel, et c'est lui qui empêche un second scénario d'effacer les plans du
premier. Commencez-le par le cours d'eau : <tt>Riviere-Q100</tt> donne
<tt>Riviere-Q100-A1</tt> ; <tt>Q100</tt> seul donnerait les mêmes plans à
deux cours d'eau calés pour la même crue. Le bouton <i>Valider la
géométrie et générer le fichier des hydrogrammes</i>, sous le préfixe,
<b>écrit, compose et contrôle</b> ; il crée alors l'Excel, et c'est dans sa
feuille <i>Cibles</i> que se saisissent les hydrogrammes visés, une colonne
par section. Lire son compte rendu avant d'aller plus loin. <b>Rien ne se
compose sans ce clic</b> : un réglage changé ensuite porte un <b>« ! »
rouge</b>, sur son champ et sur le titre de son étape, jusqu'au clic suivant
— et le lancement est refusé d'ici là.</li>
<li><b>Lancer.</b> Tout ce qui décide du lancement, dans l'ordre où il se
décide. L'appariement et l'état des cibles ; le premier apport à caler — le
plugin le demande de lui-même si un calage précédent existe ; la
<i>conservation des plans d’étape</i>,
dont une case décide du sort à la fin du calage — voir <a href="#s11">Ce que
le calage laisse dans le modèle</a>. Au-dessus du bouton, un récapitulatif dit
d'où le calage repart et ce qu'il va calculer. Puis lancer : le calage tourne
en arrière-plan, QGIS reste utilisable.</li>
<li><b>Suivi.</b> Où en est le calcul, apport par apport, rafraîchi
tout seul. C'est là qu'on revient pendant les heures que dure un calage. La
courbe y porte la cible et la section de l'apport en cours, et <b>derrière,
en vert pointillé, les sections déjà calées</b> : un calage séquentiel se lit
de l'amont vers l'aval, et c'est la <i>famille</i> de courbes qui dit si tout
se tient.</li>
<li><b>Aide et configuration.</b> Diagnostic et paramètres du poste, puis ce mode opératoire
avec son sommaire. Cette rubrique reste accessible pendant la préparation.</li>
</ol>

<p><b>Relancer un calage déjà mené.</b> Changer un réglage — le nombre
d'essais, une tolérance — puis relancer ne refait pas forcément tout. Le
plugin demande d'abord <b>par où reprendre</b>, en nommant les apports
<i>conservés</i> — déjà calés en amont, leurs plans d'étape ne sont pas
retouchés — et les apports <i>perdus</i>, dont le calage sera refait. Il
propose le premier apport que le calage précédent n'a pas validé.
<i>Tout recaler</i> repart du calcul de référence, soit plusieurs heures par
apport. La question ne se pose que s'il y a quelque chose à perdre.</p>
<p>Le <b>suivi du calage précédent est conservé</b> : ses apports restent au
ruban et au tableau, marqués <i>repris</i> en ardoise, et leurs hydrogrammes
sont tracés derrière ceux du calage en cours, en tiret-point. Un seul niveau
d'historique — le calage d'avant, pas tous les précédents.</p>

<h3><a name="s4"></a>Écrire dans la géométrie</h3>
<p><b>Indispensable tant que les sections de contrôle n'existent pas dans le
modèle</b> — le calage n'aurait aucun endroit où lire un débit. Les dessiner
ou les compléter dans les couches chargées depuis <i>Modèle</i> : elles sont écrites
dans la géométrie HEC-RAS au clic sur <i>Valider la géométrie et générer le
fichier des hydrogrammes</i>
— le bouton sous le préfixe de scénario, vert dès que tout ce qu'il consomme
est prêt, gris tant qu'il manque quelque chose —,
en <b>remplaçant tout objet de même nom</b> déjà présent, sections comme
injections. Une sauvegarde horodatée du fichier de géométrie précède
l'écriture, et le compte rendu de composition dit ce qui a été écrit.</p>
<p>La source est <b>unique</b> : ce que QGIS montre fait foi — les couches
chargées par <i>Charger les couches du modèle</i>, dessinées ou complétées
par-dessus. Il n'y a pas de bouton à part, parce que les sections doivent
être <i>dans</i> le modèle avant que le paquet soit composé, sans quoi le
calage n'aurait rien à relire.</p>
<p>Un apport créé reçoit du même coup son hydrogramme dans l'Unsteady&nbsp;Flow,
et sa pente vient du classeur (<i>Paramètres</i>) ou, à défaut, du profil en long.</p>
<p>Le fichier prétraité (<tt>.hdf</tt>) ne porte les nouveaux objets qu'au
<b>prochain calcul</b> ; <i>Charger les couches du modèle</i> les montre dès
maintenant, en lisant le fichier texte, qui fait foi.</p>

<h3><a name="s5"></a>Comment l'apport est ajusté</h3>
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

<h3><a name="s6"></a>Comment lire le résultat</h3>
<p>Tout est donné en <b>pourcentage d'atteinte de la cible</b>. Trois
exigences, satisfaites <b>en même temps</b> :</p>
<ul>
<li><b>Volume</b> — la quantité d'eau totale ;</li>
<li><b>Débit de pointe</b> — le maximum, dimensionnant pour un aléa ;</li>
<li><b>Forme</b> — concordance d'au moins 97&nbsp;%, <i>après</i> recalage
temporel.</li>
</ul>
<p>Les deux premières tolérances se règlent dans <b>Paramètres</b> ; à défaut
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
<p><b>Le verdict porte sur la fenêtre de l'événement, pas sur la crue
entière</b>, et c'est délibéré : la fenêtre existe pour cela — juger l'apport
là où l'événement se joue, sans laisser une queue de décrue peser sur le
volume. Le rapport de volume sur <i>toute</i> la série est tout de même donné,
avec la part du volume que la fenêtre retient ; quand les deux lectures
divergent, une réserve <b>non bloquante</b> le nomme, au classeur, à la note
de synthèse et au suivi. Elle <i>dit</i>, elle ne juge pas.</p>
<p>Le classeur d'itérations, écrit dans le dossier de suivi, se <b>refait à la
main</b> : par apport, un bloc de quatre colonnes par essai — la section
obtenue, la cible décalée, leur écart, l'apport injecté — et l'apport d'un
bloc est l'apport du précédent plus son écart, ramené à zéro s'il devient
négatif.</p>

<h3><a name="s7"></a>Quand la cible est hors d'atteinte</h3>
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

<h3><a name="s8"></a>Nommer les objets</h3>
<p>Les noms doivent correspondre <b>exactement</b> à ceux de la géométrie
HEC-RAS : c'est par eux que le classeur, l'Unsteady&nbsp;Flow et les résultats
se rejoignent. La convention ne sert donc qu'à la création, et ne renomme
jamais l'existant : <b>A1, A2…</b> apports à caler, <b>SC1, SC2…</b> sections
de contrôle, <b>IN_…</b> entrées permanentes et <b>OUT_…</b> exutoires, ces
deux dernières n'étant pas calées.</p>
<p>Le numéro d'une section ne reprend pas celui de son apport : l'appariement
est <b>géométrique</b> — chaque section prend la première injection en amont
d'elle — et le lien réellement calculé s'affiche dans <i>Lancer</i>. Une injection
sans section en aval n'est pas calée, ce qui est normal ; une section sans
injection en amont est en revanche une erreur.</p>

<h3><a name="s9"></a>Un apport créé part de zéro</h3>
<p>Il reçoit un hydrogramme <b>nul</b>, sur la base de temps du modèle. Rien
à saisir : le calage commence par un calcul sans les apports, mesure ce que
chaque section reçoit déjà, et la première estimation est la différence avec
la cible. Le classeur ne demande donc aucune forme d'apport — on y saisit ce
qu'on veut <i>obtenir à la section</i>, pas ce qu'on injecte.</p>

<h3><a name="s10"></a>Pièges à connaître</h3>
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

<h3><a name="s11"></a>Ce que le calage laisse dans le modèle</h3>
<p>Un plan HEC-RAS par <b>étape</b>, et son Unsteady&nbsp;Flow :
<tt>Riviere-Q100-sans</tt> d'abord — tous les apports à zéro —, puis
<tt>Riviere-Q100-A1</tt>, <tt>Riviere-Q100-A2</tt>… et, à l'arrivée, le plan
final <tt>Riviere-Q100</tt>, qui porte le préfixe seul. Un titre compte au plus
32 caractères, préfixe compris : l'étape Paramètres montre le plus long à la
frappe.</p>
<p><b>Le plan source n'est jamais touché.</b> S'il porte déjà le nom du préfixe,
le lancement est refusé. Si un autre plan porte ce nom, le lancement demande
confirmation : ce plan et ses résultats seront remplacés à la fin du calage.</p>
<p><b>Le plan final n'est pas un clone</b> : c'est le plan de la dernière
étape, retitré. Il porte donc tous les apports calés <i>et</i> ses résultats
de calcul — un clone n'emporterait pas son <tt>.hdf</tt> et serait muet dans
RAS&nbsp;Mapper.</p>
<p><b>Les étapes sont conservées</b>, et c'est voulu : elles documentent ce
qui a été obtenu apport par apport, et permettent de reprendre une séquence
interrompue sans repartir du premier. Le prix est le disque — un modèle à
trente apports garde trente et un jeux de résultats.</p>
<p>Dans <i>Lancer</i>, la case <i>Supprimer les plans d’étape après un calage
réussi</i> décide de leur sort,
<b>avant</b> le calage : cochée, la chaîne les retire à la fin ; décochée, ils
restent. L'encadré dit en toutes lettres ce qui va se passer. L'élagage ne
touche qu'aux plans d'étape du préfixe indiqué : le plan de référence, le plan
final et tout plan qui n'est pas de la chaîne restent. <b>Si le calage n'a pas
conclu</b> — aucun plan final au nom du préfixe —, il est refusé : ses étapes
sont alors tout ce qu'il en reste.</p>
<p>Oublié de cocher ? <tt>pont_hecras.py elaguer-etapes --dossier … --projet …
--plan-reference … --prefixe … --apports …</tt> le fait encore après coup, depuis une
console : sans <tt>--executer</tt>, il se contente de dire ce qui partirait.
La relecture d'un hydrogramme déjà calculé a suivi le même chemin —
<tt>pont_hecras.py hydrogramme</tt>.</p>

<p><i>Hypothèses de validité, justification des tolérances et livrables :
note méthodologique « methodologie_calage_amont_aval.docx », dans le dossier
de la chaîne — le détail de la correction et de Δt y figure aux § 1.4 et 1.5.
Pilotage HEC-RAS par
<b>ras-commander v0.99.1</b> (CLB Engineering Corporation) ; ses auteurs
demandent d'être cités, ce que la note de synthèse produite par la chaîne fait
d'office.</i></p>
"""

# LE LEXIQUE (27/10/2026, comme Plemmyra, Hyetos et Rhoe). Chaque terme
# technique de l'aide renvoie a son entree, en fin d'aide ; les textes d'aide
# et les lignes d'etat des etapes y renvoient aussi (EtiquetteLexique). Les
# liens sont discrets : couleur du texte, sans soulignement (interface.Manuel).
AIDE_HTML = (
    lexique.lier(AIDE_HTML).replace(f'href="{lexique.PREFIXE}', f'href="#{lexique.ANCRE}')
    + '\n<h3><a name="s12"></a>Lexique</h3>\n'
    "<p>Les termes techniques de l'aide et des étapes renvoient ici : le survol "
    "montre leur définition, un clic ouvre leur entrée. Une source suivie de ↗ "
    "s'ouvre dans le navigateur.</p>\n"
    + "".join(f"<p>{lexique.entree(t)}</p>\n" for t in lexique.TERMES))


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


def confirmer(parent, titre, texte, oui, non):
    """
    Une question a deux issues, nommees par des VERBES, dont le defaut est
    celle qui ne coute rien. Vrai si l'utilisateur a choisi « oui ».

    QMessageBox.question(..., Yes | No) SANS defaultButton LAISSE QT CHOISIR :
    il retient le premier bouton de role Accept — or « Oui » porte le role
    Yes, donc aucun —, et Entree va alors au premier bouton autoDefault de la
    chaine de focus, « Oui » en disposition Windows. La garde de
    DialogueParametrage.keyPressEvent ne protege pas une boite modale : c'est
    une autre fenetre. Trois questions etaient dans ce cas (0.8.5), dont
    celle qui autorise a recomposer pendant qu'un calage tourne — et dont la
    docstring promettait « non » par defaut.

    LES BOUTONS DISENT CE QU'ILS FONT — « Recomposer quand meme » plutot que
    « Oui » —, comme _confirmer_reprise le fait deja. Le refus est le bouton
    par defaut ET le bouton d'echappement : Entree, Echap et la croix disent
    tous « non ». AUCUN BOUTON CLIQUE VAUT NON, un talon de recette compris.
    """
    boite = QMessageBox(parent)
    boite.setIcon(QMessageBox.Icon.Question)
    boite.setWindowTitle(titre)
    boite.setText(texte)
    bouton_oui = boite.addButton(oui, QMessageBox.ButtonRole.AcceptRole)
    bouton_non = boite.addButton(non, QMessageBox.ButtonRole.RejectRole)
    boite.setDefaultButton(bouton_non)
    boite.setEscapeButton(bouton_non)
    boite.exec()
    return boite.clickedButton() is bouton_oui


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


# LES COUCHES DE PK DE LA 0.9.15 portaient cette marque. Il n'en est plus
# cree ; celles qu'un projet garde encore sont retirees a la composition.
MARQUE_PK = "calage_apports/pk"


def etiqueter_pk_sur_carte(chemins, sens, bases):
    """
    Etiquette les couches de base du modele : « nom — PK 1 250 m ».

    Montrer une incoherence d'ordre A L'ENDROIT OU ELLE EST est le seul
    apport du plugin qu'un rapport texte ne peut pas remplacer.

    SUR LES COUCHES DE BASE, SANS COUCHE DE PLUS (24/09/2026, demande
    utilisateur). Jusqu'a la 0.9.15, « Sections — PK » et « Injections — PK »
    doublaient les couches de base — memes objets, meme trace — et se
    lisaient comme des doublons ; le PK n'y ajoutait qu'une etiquette. Elle
    passe sur la couche de base, par une table nom -> PK figee dans
    l'expression : aucun champ n'est ajoute a une couche que l'utilisateur
    edite, et un objet trace apres la composition, sans PK, n'affiche que
    son nom jusqu'a la suivante.

    chemins : dict a cles « sections », « apports », « axe ».
    bases : dict a cles « sections », « apports » — les couches a etiqueter.
    """
    projet = QgsProject.instance()
    for ancienne in list(projet.mapLayers().values()):
        if ancienne.customProperty(MARQUE_PK):
            projet.removeMapLayer(ancienne.id())
    if not chemins.get("axe"):
        return
    for cle, couche in bases.items():
        couche = couche_vivante(couche)
        if couche is None or not chemins.get(cle):
            continue
        gdf = noyau.pk_pour_affichage(chemins[cle], chemins["axe"], sens=sens)
        gdf = gdf.dropna(subset=["pk_m"])
        table = ", ".join(
            "'{}', {:.1f}".format(str(nom).replace("'", "''"), float(pk))
            for nom, pk in zip(gdf["nom"], gdf["pk_m"]))
        etiqueter(couche,
                  "concat(\"nom\", ' — PK ' || format_number("
                  f"map_get(map({table}), \"nom\"), 0) || ' m')")


# ---------------------------------------------------------------------------
# Fenetre de parametrage — six onglets
#
# Les rangs sont NOMMES : les liens du fil conducteur, F1 et « Consulter le
# suivi » visent un onglet par son rang, et un indice ecrit en dur y devenait
# faux au premier onglet insere — sans que rien ne le signale, puisque Qt
# affiche simplement l'onglet voisin. Aucune action ne change plus d'onglet
# d'elle-meme (24/09/2026, demande utilisateur).
# ---------------------------------------------------------------------------

# COMBIEN DE TEMPS ON LAISSE AU CALAGE POUR ECRIRE SON PREMIER ETAT avant de
# le declarer mort. Il lui faut ouvrir le classeur, initialiser ras-commander
# et titrer sa premiere etape — une trentaine de secondes sur un modele leger,
# davantage sur un partage reseau. Mesure du 08/09/2026 sur un modele reel :
# 1 min 55 entre le lancement et la premiere ligne d'etape.
#   ET IL FAUT CETTE PATIENCE : le PID rendu par Popen n'est pas celui du
# calage quand l'interpreteur est un relais (voir _maj_suivi), si bien qu'il
# disparait aussitot. Sans delai, le suivi annoncait « mort au demarrage »
# trois secondes apres un lancement qui se deroulait bien.
DELAI_PREMIER_ETAT_S = 240

# LES CINQ ONGLETS QUI PORTENT UN NUMERO. « Aide et configuration » n'en a
# pas : il n'est pas une etape.
#   ILS SONT NOMMES PARCE QUE L'ORDRE A DEJA CHANGE DEUX FOIS — 0.7.0, puis
# 0.7.24 ou les deux du milieu se sont inverses. Le banc comptait « widget(1) »
# et « widget(2) » a la main : il regardait le bon widget par coincidence, et
# rien ne l'aurait averti.
ONGLET_MODELE = 0
ONGLET_OBJECTIFS = 1
ONGLET_LANCER = 2
ONGLET_SUIVI = 3
# L'AIDE A LE SIEN AUSSI (0.8.5) : F1, « Suivant » et Alt + fleche droite y
# renvoient, et son rang etait ecrit « 5 » a cinq endroits. Le jour ou un
# onglet s'insere — ou en sort, comme « Sorties » le 20 septembre 2026 — F1
# aurait ouvert autre chose et « Suivant » se serait arrete un cran trop tot,
# sans un mot. La suite d'essais verifie que les rangs nommes tombent bien
# sur leur onglet.
ONGLET_AIDE = 4
DERNIER_ONGLET = ONGLET_AIDE


def _cle_fichier(chemin):
    """(chemin, date de modification) — ce qui dit qu'un fichier a change."""
    try:
        return (str(chemin), os.path.getmtime(chemin))
    except OSError:
        return None


class DialogueParametrage(QDialog):
    """
    Fenetre unique, en six onglets, dans l'ordre ou les choix se prennent.

      1. Modèle — projet, plan de reference, geometrie et Unsteady Flow (ceux
         du plan ou d'autres), zone 2D, fenetre de simulation, axe
         hydraulique. Y CHARGE LES COUCHES EXISTANTES de la geometrie en
         couches QGIS EDITABLES, pretes a etre dessinees ou completees
         par-dessus.
      2. Paramètres — ce qu'on vise et avec quoi : la precision attendue sur
         le volume et la pointe, le prefixe de scenario, et le classeur ou se
         saisissent les hydrogrammes cibles.
      3. Lancer — ce que la derniere composition a produit, l'etat des
         cibles, les apports a determiner, OU ECRIRE le paquet, les resultats
         finaux et le suivi, et le lancement. Le dossier de sortie est ici,
         apres les objectifs : c'est un reglage DU LANCEMENT.
         Recomposer au fil de l'ajustement des couches est le cas NORMAL : les
         cibles saisies a la main sont preservees d'une composition a l'autre.
      4. Suivi — ou en est le calcul, rafraichi tout seul tant que cet onglet
         est affiche.
      Aide et configuration — mode operatoire, pieges connus, et les deux
         emplacements du poste.

    Le bouton « Ecrire dans la geometrie HEC-RAS », au bas de la fenetre
    « Fermer » — vert quand c'est le moment, gris sinon —
    ECRIT D'ABORD les couches de l'onglet 1 dans la geometrie HEC-RAS —
    TOUJOURS EN REMPLACANT l'objet de meme nom deja present, sections comme
    injections : ce que QGIS montre fait foi, il n'y a plus de choix a faire
    ni de bouton a part (_ecrire_dans_geometrie) — puis compose les fichiers
    et lance le controle complet.
    """

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self._tache_installation = None
        self._python_en_attente = None
        self._choix_python_ouvert = False
        self.setWindowTitle(f"{NOM_PLUGIN} — {EDITEUR}")
        self.setObjectName("calageFenetre")
        self.setWindowIcon(QIcon(os.path.join(DOSSIER, "icon.png")))
        # Assez large pour que les chemins de fichiers ne soient pas tronques,
        # et redimensionnable : l'onglet 1 est dense.
        #   LE HIG QGIS DIT « AUCUN DIALOGUE AU-DELA DE 580 PX DE HAUT ET 1000
        # DE LARGE » (docs.qgis.org, developers_guide/hig). L'ecart est VOULU :
        # la fenetre n'est pas un dialogue a valider en un clic mais un poste
        # de travail qu'on garde ouvert pendant qu'on dessine ; chaque etape
        # defile, et la hauteur se borne a l'ecran moins 64 px.
        self.resize(940, 760)
        self.setMinimumSize(720, 520)

        # CE QU'ON RETIENT DU DERNIER LANCEMENT, et pourquoi. _lancer_calage
        # recevait le PID et le chemin du journal, les mettait dans un texte,
        # et les perdait. Trois affichages mentaient faute de cette donnee :
        # l'onglet 5 peignait l'etat du calage PRECEDENT comme reponse au
        # lancement qui venait d'aboutir ; il promettait « quelques secondes
        # apres le lancement » y compris devant un processus mort au
        # demarrage ; et le fil conducteur ordonnait « lancer » pendant les
        # heures du calcul. Une seule donnee, trois mensonges.
        #   EN MEMOIRE, JAMAIS DANS QSettings : celui-ci est attache au PROFIL
        #   QGIS et non au projet. Restaurer un lancement d'une autre etude
        #   couterait plus cher que ce qu'on repare.
        self.pid_lance = None
        self.journal_lance = None
        # L'INSTANT DU LANCEMENT, ET C'EST LUI QUI FAIT FOI — pas le PID. Voir
        # _maj_suivi : le PID rendu par Popen n'est pas celui du calage des
        # que l'interpreteur est un relais.
        self.instant_lance = None
        self.info_projet = None      # resultat de noyau.lister_projet_hecras
        self.version_hecras = None   # lue dans les fichiers, jamais saisie
        self.appariement = None      # apports <-> sections, deduit des PK
        # DE QUEL CLASSEUR L'APPARIEMENT PARLE. La ligne du haut de l'onglet 4
        # decrit le paquet COMPOSE ; reprendre le classeur d'un autre calcul ne
        # la recalcule pas — l'appariement se deduit des PK, donc des
        # shapefiles du paquet, que la reprise n'a pas. Sans ce temoin, elle
        # continuait d'annoncer les paires du paquet precedent.
        # DE QUELLE GEOMETRIE VIENNENT LES COUCHES CHARGEES. Changer de plan,
        # ou surcharger la geometrie, n'invalide rien : la zone 2D et le CRS
        # restent ceux d'AVANT, et ils ne sont pas des comptes rendus dates —
        # ce sont des valeurs courantes, presentees comme telles au resume et
        # consommees a l'ecriture.
        self.geom_couches = None
        self.crs_modele = None       # authid, ex. "EPSG:2154"
        self.couche_sections = None
        self.couche_injections = None
        self.couche_perimetre = None
        self.couche_maillage = None      # maillage natif QGIS/MDAL, visuel
        self.classeur = None         # rempli si la composition reussit
        self.paquet = {}

        self._style_en_attente = False
        self._minuteur_style = QTimer(self)
        self._minuteur_style.setSingleShot(True)
        self._minuteur_style.timeout.connect(self._actualiser_style)
        # LE PAQUET NE SE RECOMPOSE PLUS TOUT SEUL (24/09/2026, demande
        # utilisateur). Le minuteur de la 0.9.5 partait apres 1,5 s sans
        # frappe : taper « Q100 » en marquant une pause composait « Q1 » — un
        # dossier « _calage\Q1 » avec son classeur, son JSON et ses shapefiles,
        # et la fenetre basculait dessus. Seul le bouton compose desormais ;
        # un champ que le paquet ne porte plus s'annonce par un « ! » rouge
        # (voir _temoin, _maj_temoins).
        self._temoins = []           # (cles du paquet, « ! » du champ)
        self._actualiser_style()
        QApplication.instance().installEventFilter(self)
        agencement = QVBoxLayout(self)
        agencement.setSpacing(10)
        agencement.setContentsMargins(12, 12, 12, 12)

        agencement.addWidget(self._bandeau())
        # BANDEAU DE MESSAGES NON MODAL (0.8.2). Le Cookbook PyQGIS le dit :
        # une boite de message est une mauvaise idee pour INFORMER — elle
        # interrompt pour rien. Informations, avertissements et succes
        # passent ici, avec leur niveau et leur duree ; les QMessageBox qui
        # restent sont des DECISIONS (ecrire dans la geometrie, lancer,
        # designer) ou des erreurs a lire.
        self.barre_messages = QgsMessageBar(self)
        self.barre_messages.setObjectName("barreMessages")
        self.barre_messages.hide()          # pushMessage() la fait apparaitre
        agencement.addWidget(self.barre_messages)
        # LES ETAPES DANS LA BANDE COMMUNE, A GAUCHE (23/10/2026, esthetique
        # commune des extensions ISL : la bande de Rhoe et de Hyetos, bande.py
        # en copie identique). La fenetre est une suite ordonnee — 1. Modele,
        # 2. Parametres, 3. Lancer, 4. Suivi, que « Precedent », « Suivant » et
        # le fil parcourent dans cet ordre — : c'est le cas de la bande. La
        # barre d'onglets qu'elle remplace demandait 816 px a 9 pt et 993 a
        # 13 pt pour ses cinq titres : il lui fallait un plancher de largeur, et
        # elle elidait « Aide et configuration » sous 800 px. La bande tient en
        # une colonne et ne coupe aucun titre ; quand la hauteur manque, elle
        # ne garde que les numeros, puis defile.
        #   LE QTabWidget RESTE LA PILE DES PAGES, sa barre cachee : ses titres
        # (tabText) nomment toujours les etapes pour le fil, les messages et
        # le banc.
        self.onglets = QTabWidget()
        self.onglets.setDocumentMode(True)
        self.onglets.tabBar().hide()
        # Chaque page vit dans une zone defilante : un ecran d'ordinateur
        # portable ne montrerait sinon qu'une partie de l'etape 1, et les
        # boutons du bas seraient repousses hors de l'ecran.
        #   L'ENTREE DE LA BANDE : le numero, puis le nom court dessous ; le
        # titre et le role de l'etape en infobulle, ou ils ne coutent rien.
        # « Aide et configuration » garde son nom entier sous « ? » :
        # preference de l'utilisateur, qui prime sur le titre court (la
        # configuration du poste y vit, et « Aide » seul la cachait). Il est
        # coupe « configu- / ration », comme « Hydro- / grammes » chez Rhoe :
        # en entier, ce mot elargissait la bande d'une trentaine de pixels a
        # 13 pt, pris aux pages.
        entrees = []
        for page, titre, entree, infobulle in (
            (self._onglet_modele(), "1. Modèle", "1\nModèle",
             "Projet HEC-RAS, plan de référence, zone 2D, profil en long, "
             "et chargement des couches existantes du modèle."),
            (self._onglet_objectifs(), "2. Paramètres", "2\nParamètres",
             "Précision attendue sur le volume et la pointe, nombre maximal "
             "d'essais, dossier de sortie, préfixe de scénario, l'Excel où "
             "se saisissent les hydrogrammes cibles, et ce que ces "
             "hydrogrammes portent une fois validés."),
            (self._onglet_validation(), "3. Lancer", "3\nLancer",
             "Correspondance sections / injections, état des hydrogrammes "
             "cibles, apports à déterminer, conservation des plans d'étape, "
             "cœurs de calcul, et lancement du calage."),
            (self._onglet_suivi(), "4. Suivi", "4\nSuivi",
             "Où en est le calage : apport en cours, essai, avancement, "
             "temps restant, et ce qui s'est passé quand il s'arrête."),
            (self._onglet_aide(), "Aide et configuration", "?\nAide et\nconfigu-\nration",
             "Mode opératoire, pièges connus, et les deux emplacements du "
             "poste — chaîne de calage et interpréteur HEC-RAS."),
        ):
            zone = QScrollArea()
            zone.setWidgetResizable(True)
            zone.setFrameShape(QFrame.Shape.NoFrame)
            zone.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            page.layout().setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
            zone.setWidget(page)
            self.onglets.addTab(zone, titre)
            entrees.append((entree, f"{titre} — {infobulle}"))
        self.bande = self._bande(entrees)
        self.bande.currentRowChanged.connect(self.onglets.setCurrentIndex)
        self.onglets.currentChanged.connect(self.bande.setCurrentRow)
        self.bande.setCurrentRow(self.onglets.currentIndex())
        corps = QHBoxLayout()
        corps.setSpacing(10)
        corps.addWidget(self.bande)
        corps.addWidget(self.onglets, 1)
        agencement.addLayout(corps)
        # Le suivi ne se relit QUE lorsqu'il est a l'ecran (voir _onglet_suivi) :
        # ce signal lui redonne la main des qu'on y revient, sans quoi il
        # afficherait l'etat vieux de la derniere visite pendant deux secondes.
        self.onglets.currentChanged.connect(self._changer_onglet)
        self.onglets.currentChanged.connect(self._maj_navigation)

        # Fil conducteur permanent : a tout moment on sait ou on en est et ce
        # qui vient ensuite, sans avoir a parcourir les onglets.
        self.label_fil = QLabel()
        self.label_fil.setObjectName("filConducteur")
        self.label_fil.setWordWrap(True)
        self.label_fil.setTextFormat(Qt.TextFormat.RichText)
        # LES LIENS DU FIL SE PRENNENT AUSSI AU CLAVIER (0.8.5). Un QLabel
        # riche n'accepte par defaut que la souris ; le seul repere permanent
        # de la fenetre — « Choisir le profil en long », « verifier le
        # lancement » — etait donc hors d'atteinte de Tab dans une fenetre
        # dont tout le reste se parcourt au clavier. Tab atteint le lien,
        # Entree l'active — et c'est le QLabel qui consomme Entree, pas
        # keyPressEvent : la garde ci-dessous ne voit que ce qui lui remonte.
        self.label_fil.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.label_fil.linkActivated.connect(self._aller_etape)
        agencement.addWidget(self.label_fil)

        # « CONTROLE PARAMETRAGE » EST DE RETOUR ICI (0.7.24, demande
        # utilisateur), a cote de « Fermer », ou il vivait jusqu'a la 0.7.19.
        # Il en etait parti parce qu'il restait visible depuis six onglets
        # dont cinq n'en font rien ; il y revient parce qu'il les CONSOMME —
        # et parce qu'il dit desormais quand c'est le moment, en vert ou en
        # gris. Voir _bouton_controle_parametrage.
        #   IL EST A GAUCHE DE « FERMER », ET LOIN DE LUI : c'est le seul
        # geste irreversible de la fenetre, et « Fermer » est celui qu'on
        # cherche sans regarder.
        boutons = QHBoxLayout()
        boutons.setSpacing(8)
        # LA PROGRESSION DE LA SAISIE, A COTE DU GESTE QU'ELLE PREPARE
        # (20/09/2026, demande utilisateur). ELLE NE PARLE PAS DU CALAGE :
        # celui-ci dure des heures et se lit a l'onglet Suivi. Le libelle le
        # dit — « Préparation » —, l'infobulle le redit, et la barre est au
        # BAS de la fenetre, la ou vit ce qui prepare, non dans le Suivi.
        # Elle porte son compte EN CHIFFRES : une barre remplie aux trois
        # quarts ne dit pas qu'il manque le dossier de sortie.
        self.barre_preparation = BarreTexte()
        self.barre_preparation.setObjectName("barrePreparation")
        self.barre_preparation.setFormat("Préparation %v/%m")
        self.barre_preparation.setMinimum(0)
        self.barre_preparation.setMaximum(4)
        self.barre_preparation.setValue(0)
        self.barre_preparation.setTextVisible(True)
        self.barre_preparation.setSizePolicy(QSizePolicy.Policy.Preferred,
                                             QSizePolicy.Policy.Fixed)
        boutons.addWidget(self.barre_preparation)
        boutons.addStretch(1)
        self.bouton_precedent = QPushButton("Précédent")
        self.bouton_precedent.setToolTip("Étape précédente — Alt + flèche gauche")
        self.bouton_precedent.clicked.connect(
            lambda: self.onglets.setCurrentIndex(max(0, self.onglets.currentIndex() - 1)))
        boutons.addWidget(self.bouton_precedent)
        self.bouton_suivant = QPushButton("Suivant")
        self.bouton_suivant.clicked.connect(
            lambda: self.onglets.setCurrentIndex(
                min(DERNIER_ONGLET, self.onglets.currentIndex() + 1)))
        boutons.addWidget(self.bouton_suivant)
        bouton_fermer = QPushButton("Fermer")
        bouton_fermer.setMinimumWidth(90)
        bouton_fermer.clicked.connect(self.accept)
        boutons.addWidget(bouton_fermer)
        agencement.addLayout(boutons)

        self._maj_resume()
        self._maj_fil()
        # LE RECAPITULATIF EST VIDE TANT QUE PERSONNE N'A TOUCHE AU COMBO NI
        # AU PREFIXE. Vu sur la fenetre REELLE, le 20 septembre 2026 : le
        # banc appelait _dire_reprise() a la main et ne pouvait donc pas voir
        # qu'aucun chemin ne l'appelait a l'ouverture. Un compte rendu qui
        # n'apparait qu'apres avoir touche un reglage sans rapport n'existe
        # pas pour qui ne le touche pas.
        self._dire_reprise()
        self._maj_navigation()
        self._nommer_champs()
        # Un terme clique dans un texte d'aide ou d'etat ouvre le lexique.
        for label in self.findChildren(EtiquetteLexique):
            label.linkActivated.connect(self._ouvrir_lexique)
        # Une action de fenêtre intercepte aussi les raccourcis lorsque le
        # bouton focalisé ou le navigateur d'aide consomme les touches.
        for libelle, raccourci, sens in (("Étape précédente", "Alt+Left", -1),
                                        ("Étape suivante", "Alt+Right", 1)):
            action = QAction(libelle, self)
            action.setShortcut(QKeySequence(raccourci))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(lambda _=False, pas=sens: self.onglets.setCurrentIndex(
                max(0, min(DERNIER_ONGLET, self.onglets.currentIndex() + pas))))
            self.addAction(action)
        ecran = self.screen() or QApplication.primaryScreen()
        if ecran is not None:
            disponible = ecran.availableGeometry()
            self.setMinimumWidth(min(self.minimumWidth(), disponible.width() - 32))
            self.resize(min(self.width(), disponible.width() - 32),
                        min(self.height(), disponible.height() - 64))

    def _bande(self, entrees):
        """
        Bande des etapes, comme celle de Rhoe (rhoe/gui/dock.py, _bande) :
        numero en gras, nom dessous, titre et role en infobulle et en nom
        accessible. ``entrees`` : (texte de l'entree, infobulle), dans l'ordre
        des pages.

        LA BANDE SE MESURE DANS LA POLICE QUE LA FEUILLE DE STYLE LUI POSE —
        celle de l'application, 10 pt au moins (_actualiser_style) — et non
        dans une police reduite comme chez Rhoe : la regle « QWidget » de la
        feuille l'emporterait sur setFont(), et la bande, mesuree trop
        etroite, couperait ses noms.
        """
        police = QFont(QApplication.font())
        police.setPointSizeF(max(10.0, QApplication.font().pointSizeF()))
        metrique = QFontMetrics(police)
        ligne = metrique.lineSpacing()
        complets = [texte for texte, _ in entrees]
        largeur = max(metrique.horizontalAdvance(morceau)
                      for texte in complets for morceau in texte.split("\n"))
        largeur += ligne
        # LES TEXTES SANS « ! », et ceux que la bande relit a chaque
        # changement de forme (Bande.ajuster) : _maj_temoins y pose le « ! »
        # d'une etape dont un reglage est a actualiser.
        courts = [texte.partition("\n")[0] for texte in complets]
        self._textes_bande = (list(complets), list(courts))
        self._textes_bande_vus = (complets, courts)
        bande = Bande(complets, courts, largeur, ligne)
        bande.setObjectName("bandeEtapes")
        bande.setAccessibleName("Étapes du calage des apports")
        bande.setFont(police)
        bande.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bande.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Fonds alternes de la palette : chaque numero reste lie a son nom.
        bande.setAlternatingRowColors(True)
        for rang, (texte, infobulle) in enumerate(entrees):
            element = QListWidgetItem(texte)
            element.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            element.setToolTip(infobulle)
            element.setData(Qt.ItemDataRole.AccessibleTextRole,
                            self.onglets.tabText(rang))
            bande.addItem(element)
        bande.ajuster(bande.hauteur_complete)
        # LA PLACE DE L'ASCENSEUR EST RESERVEE (27/10/2026). A 13 pt, les
        # etapes ne tiennent plus en hauteur : l'ascenseur vertical paraissait
        # et prenait 26 px aux entrees, dont le bord droit ne repondait plus
        # au clic.
        bande.setFixedWidth(largeur + 2 * bande.frameWidth()
                            + bande.verticalScrollBar().sizeHint().width())
        # Trois etapes au moins : en deca, la bande defile.
        bande.setMinimumHeight(3 * bande.hauteur_courte + 2 * bande.frameWidth())
        return bande

    def _actualiser_style(self):
        """Lire la palette réellement polie par QGIS, sans modifier son thème."""
        self._style_en_attente = False
        temoin = QTabWidget()
        temoin.ensurePolished()
        taille = max(10.0, QApplication.font().pointSizeF())
        feuille = feuille_interface(temoin.palette(), taille)
        temoin.deleteLater()
        if self.styleSheet() != feuille:
            self.setStyleSheet(feuille)

    def changeEvent(self, evenement):  # noqa: N802
        super().changeEvent(evenement)
        if (evenement.type() in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange,
                                 QEvent.Type.ApplicationFontChange)
                and hasattr(self, "_style_en_attente")
                and not self._style_en_attente):
            self._style_en_attente = True
            self._minuteur_style.start(0)

    def _signaler(self, titre, texte, niveau=Qgis.MessageLevel.Info, duree=8):
        """Information dans le bandeau, sans interrompre. duree=0 : reste."""
        self.barre_messages.pushMessage(titre, texte, level=niveau,
                                        duration=duree)

    def eventFilter(self, objet, evenement):  # noqa: N802
        # Une police posée par QSS ne reçoit pas toujours FontChange sur le
        # widget. L'événement de l'application couvre le réglage global QGIS.
        if (objet is QApplication.instance()
                and evenement.type() == QEvent.Type.ApplicationFontChange
                and not self._style_en_attente):
            self._style_en_attente = True
            self._minuteur_style.start(0)
        if (objet is QApplication.instance()
                and evenement.type() == QEvent.Type.ApplicationStateChange
                and QApplication.applicationState()
                == Qt.ApplicationState.ApplicationActive):
            # Retour d'Excel : le classeur a peut-etre change.
            self._relire_cibles_si_modifiees()
        return super().eventFilter(objet, evenement)

    def _nommer_champs(self):
        """Associer les libellés persistants aux champs, y compris les chemins."""
        # QPushButton traite Entrée avant le dialogue quand il a le focus.
        # Retirer autoDefault sur chaque bouton laisse remonter la touche
        # jusqu'à notre garde ; Espace conserve l'activation au clavier.
        for bouton in self.findChildren(QPushButton):
            bouton.setAutoDefault(False)
            bouton.setDefault(False)
        for disposition in self.findChildren(QFormLayout):
            for rang in range(disposition.rowCount()):
                etiquette = disposition.itemAt(rang, QFormLayout.ItemRole.LabelRole)
                item = disposition.itemAt(rang, QFormLayout.ItemRole.FieldRole)
                if etiquette is None or item is None or etiquette.widget() is None:
                    continue
                champ = item.widget()
                if champ is None and item.layout() is not None:
                    premier = item.layout().itemAt(0)
                    champ = premier.widget() if premier is not None else None
                if champ is not None:
                    label = etiquette.widget()
                    label.setBuddy(champ)
                    if not champ.accessibleName():
                        champ.setAccessibleName(label.text().rstrip(" :"))

    def _maj_navigation(self, *_):
        if not hasattr(self, "bouton_suivant"):
            return
        indice = self.onglets.currentIndex()
        self.bouton_precedent.setEnabled(indice > 0)
        self.bouton_suivant.setEnabled(indice < DERNIER_ONGLET)
        titre = self.onglets.tabText(min(DERNIER_ONGLET, indice + 1))
        self.bouton_suivant.setToolTip(f"Ouvrir {titre} — Alt + flèche droite")

    def _aller_etape(self, lien):
        """« 2 » ouvre l'etape ; « 1:edit_dossier_sortie » y montre aussi ce
        champ, focus compris."""
        rang, _, objet = lien.partition(":")
        if not (rang.isdigit() and int(rang) <= DERNIER_ONGLET):
            return
        self.onglets.setCurrentIndex(int(rang))
        cible = getattr(self, objet, None) if objet else None
        if isinstance(cible, QWidget):
            self.onglets.widget(int(rang)).ensureWidgetVisible(cible)
            cible.setFocus(Qt.FocusReason.OtherFocusReason)

    def keyPressEvent(self, evenement):
        """
        ENTREE N'ACTIVE AUCUN BOUTON DANS CETTE FENETRE.

        « Ecrire, composer et controler » etait le bouton par DEFAUT du dialogue
        (setDefault + setAutoDefault). Une pression sur Entree depuis
        n'importe quel champ de saisie — un chemin de dossier, une tolerance,
        le prefixe de scenario — declenchait donc _composer_et_controler(),
        qui COMMENCE par reecrire les sections et injections dans le .gXX, en
        remplacant tout objet de meme nom. Le seul geste irreversible de la
        fenetre etait cable sur la touche qu'on presse par reflexe en
        finissant de taper.

        RETIRER setDefault NE SUFFIT PAS. Qt promeut alors le premier bouton
        autoDefault visible — ici « Parcourir… » — et la touche ne fait que
        changer de cible. C'est pourquoi Entree est avalee ici.

        CE QUE CELA COUTE, ET C'EST ASSUME : Entree n'active plus aucun
        bouton, nulle part dans la fenetre. Aucun n'est pour autant hors
        d'atteinte au clavier — la tabulation y mene, la barre d'espace les
        actionne. Echap continue de fermer : QDialog le traite avant nous.
        """
        if evenement.key() == Qt.Key.Key_F1:
            self.onglets.setCurrentIndex(ONGLET_AIDE)
            evenement.accept()
            return
        if (evenement.modifiers() & Qt.KeyboardModifier.AltModifier
                and evenement.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right)):
            sens = -1 if evenement.key() == Qt.Key.Key_Left else 1
            self.onglets.setCurrentIndex(
                max(0, min(DERNIER_ONGLET, self.onglets.currentIndex() + sens)))
            evenement.accept()
            return
        if evenement.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            evenement.accept()
            return
        super().keyPressEvent(evenement)

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
        titre.setProperty("role", "marque")
        sous_titre = QLabel(
            "Préparer les apports, définir les cibles et suivre le calage HEC-RAS 2D.")
        sous_titre.setWordWrap(True)
        sous_titre.setProperty("role", ROLE_AIDE)
        textes.addWidget(titre)
        textes.addWidget(sous_titre)
        ligne.addLayout(textes, 1)

        # La signature figurait dans les seules metadonnees, invisibles une
        # fois le plugin installe. Un outil interne doit dire de qui il vient.
        signature = QLabel(EDITEUR)
        signature.setProperty("role", ROLE_AIDE)
        ligne.addWidget(signature, 0, Qt.AlignmentFlag.AlignBottom)

        enveloppe = QWidget()
        v = QVBoxLayout(enveloppe)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(7)
        v.addWidget(cadre)
        # Filet degrade teal → ardoise : la frise de la charte, ramenee a
        # une ligne. Un aplat uni tenait la meme place sans rien evoquer.
        filet = QFrame()
        filet.setFixedHeight(1)
        filet.setStyleSheet("border: none; background-color: palette(mid);")
        v.addWidget(filet)
        return enveloppe

    def _maj_fil(self):
        """
        Fil conducteur affiche en bas de la fenetre : ou en est-on, et quoi
        ensuite. Chaque etape est franchie ou non, sans jamais deviner —
        l'etat vient de ce qui existe reellement, pas d'un compteur interne.
        """
        etapes = self._etapes_preparation()
        suivante = next((nom for nom, ok in etapes if not ok), None)
        # LA BARRE DIT LA MEME CHOSE QUE LE FIL, et depuis la meme liste : deux
        # lectures de l'avancement qui divergeraient donneraient une barre
        # pleine sous un fil qui reclame encore une etape.
        barre = getattr(self, "barre_preparation", None)
        if barre is not None:
            faites = sum(bool(ok) for _, ok in etapes)
            barre.setMaximum(len(etapes))
            barre.setValue(faites)
            reste = [nom for nom, ok in etapes if not ok]
            barre.setToolTip(
                "Avancement de la SAISIE avant lancement, non du calage.\n\n"
                + ("Il reste : " + ", ".join(reste) + "."
                   if reste else "Tout est renseigné."))
            barre.setAccessibleName("Préparation avant lancement")
            barre.setAccessibleDescription(
                f"{compte(faites, 'étape')} sur {len(etapes)}"
                + (" ; il reste " + ", ".join(reste) if reste else ""))
        # LE FIL NE DIT PLUS « LANCER » PENDANT QU'UN CALAGE TOURNE. Il est le
        # seul repere permanent de la fenetre, et il continuait d'ordonner
        # « renseigner les cibles puis lancer » pendant les HEURES du calcul.
        #   LE DRAPEAU VIENT DE LA MEMOIRE, JAMAIS D'UN FICHIER : _maj_fil part
        #   de _composer_resume, declenche a CHAQUE FRAPPE dans le champ du
        #   dossier de sortie, et le classeur est le plus souvent sur un
        #   partage reseau. Y lire l'etat du calage rendrait la saisie poussive.
        if self.pid_lance:
            fin = (f"<b>Calage lancé</b> — processus {self.pid_lance}. "
                   f"<a href='{ONGLET_SUIVI}'>Voir le suivi</a>")
        elif suivante is None:
            manquantes = getattr(self, "_cibles_manquantes", None)
            fin = ("<b>Paquet composé.</b> "
                   + ("Hydrogrammes cibles renseignés : " if manquantes == []
                      else "Renseignez les hydrogrammes cibles dans l’Excel, puis ")
                   + f"<a href='{ONGLET_LANCER}:bouton_lancer'>vérifier le lancement</a>.")
        else:
            # LE LIEN MENE AU CHAMP, PAS SEULEMENT A L'ETAPE (23/10/2026) :
            # « Choisir le dossier de sortie » ouvrait l'etape Lancer, ou ce
            # dossier n'est plus depuis le 22/09/2026 (il est a l'etape
            # Parametres, au-dessus du classeur), et une page longue laissait
            # chercher le champ. « <etape>:<attribut> », lu par _aller_etape.
            sans_prefixe = not self.edit_prefixe_scenario.text().strip()
            cibles = {"Modèle chargé": (
                          (ONGLET_MODELE, "bouton_charger_couches",
                           "Charger les couches du modèle")
                          if self.info_projet is not None else
                          (ONGLET_MODELE, "edit_projet_hecras",
                           "Choisir le projet HEC-RAS")),
                      "Profil en long": (ONGLET_MODELE, "combo_axe",
                                         "Choisir la couche de l'axe du profil en long"),
                      # Le dossier se propose tout seul d'apres le prefixe :
                      # sans prefixe, c'est le prefixe qui manque.
                      "Dossier de sortie": (
                          (ONGLET_OBJECTIFS, "edit_prefixe_scenario",
                           "Renseigner le préfixe de scénario")
                          if sans_prefixe else
                          (ONGLET_OBJECTIFS, "edit_dossier_sortie",
                           "Choisir le dossier de sortie")),
                      # UN PAQUET PERIME N'EST PAS COMPOSE : le lien mene au
                      # bouton qui l'actualise (voir _etapes_preparation).
                      "Paquet composé": (ONGLET_OBJECTIFS, "bouton_composer",
                                         BOUTON_GEOMETRIE)}
            rang, objet, action = cibles[suivante]
            indice = f"{rang}:{objet}"
            # LE COMPTE A QUITTE LE FIL : la barre du bas le porte
            # desormais, et les deux se lisaient a trois centimetres l'un de
            # l'autre — « Préparation : 0/4 » au-dessus de
            # « Préparation 0/4 ». Vu sur la fenetre reelle le 20 septembre
            # 2026 ; le code ne le montrait pas. Le fil garde ce que la
            # barre ne sait pas dire : QUOI faire, et le lien pour y aller.
            fin = (f"<b>Prochaine étape :</b> "
                   f"<a href='{indice}'>{action}</a>")
        # Effets visibles avant l'action, meme sans consulter l'infobulle.
        fin += (f"<br><b>{BOUTON_GEOMETRIE} :</b> y écrit les sections et "
                "injections de l'étape 1, après sauvegarde horodatée, puis "
                "compose le paquet et le contrôle.")
        self.label_fil.setText(fin)
        # LA COHERENCE SUIT LE MEME CHEMIN QUE LE FIL : il est rafraichi par
        # tout ce qui change dans la fenetre, et c'est exactement quand il
        # faut reverifier que l'ecran et le paquet disent encore la meme
        # chose. Voir _maj_coherence.
        self._maj_coherence()
        self.label_fil.setToolTip("\n".join(
            f"{'Fait' if ok else 'À faire'} : {nom}" for nom, ok in etapes))
        # LE BOUTON SUIT LE FIL, ET PAR LE MEME CHEMIN. Le fil est deja
        # rafraichi a chaque changement d'etat qui compte ; lui accrocher le
        # bouton evite d'avoir a retrouver, un par un, tous ces changements —
        # et garantit que les deux ne se contrediront jamais a l'ecran.
        self._maj_bouton_controle()

    # --- Onglet 1 : Modele HEC-RAS ------------------------------------------

    def _onglet_modele(self):
        from qgis.gui import QgsCollapsibleGroupBox

        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(12)

        groupe_projet = QGroupBox("Projet HEC-RAS")
        f = formulaire(groupe_projet)
        ligne = QHBoxLayout()
        ligne.setSpacing(6)
        self.edit_projet_hecras = QLineEdit()
        # AFFICHEUR, PAS SAISIE. Le champ etait editable et son texte
        # indicatif invitait a le remplir — mais il n'est connecte a rien :
        # seul « Parcourir… » charge le projet. Un chemin colle a la main ne
        # chargeait donc rien, et le refus qui suivait disait « choisir
        # d'abord le dossier » devant un dossier ecrit a l'ecran.
        #   PAS de connexion a editingFinished pour autant : le signal part a
        #   chaque perte de focus, champ vide ou a demi tape compris, et
        #   _charger_projet_hecras repond par une boite critique modale. On
        #   gagnerait une erreur a chaque passage de focus.
        self.edit_projet_hecras.setReadOnly(True)
        self.edit_projet_hecras.setAccessibleName("Chemin du projet HEC-RAS")
        self.edit_projet_hecras.setToolTip(
            "Chemin du projet chargé. Utilisez « Choisir le projet… » pour changer de modèle.")
        self.edit_projet_hecras.setPlaceholderText(
            "Sélectionnez le fichier .prj de votre modèle")
        bouton_parcourir = QPushButton("Choisir le projet…")
        bouton_parcourir.setAccessibleName("Choisir le fichier projet HEC-RAS")
        bouton_parcourir.setAutoDefault(False)
        bouton_parcourir.clicked.connect(self._parcourir_projet_hecras)
        ligne.addWidget(self.edit_projet_hecras, 1)
        ligne.addWidget(self._temoin("Dossier_projet_HECRAS", "Nom_projet"))
        ligne.addWidget(bouton_parcourir)
        libelle_projet = QLabel("Fichier .prj :")
        libelle_projet.setBuddy(self.edit_projet_hecras)
        f.addRow(libelle_projet, ligne)
        # La version de HEC-RAS n'est PAS demandee : elle est ecrite dans les
        # fichiers du modele (« Program Version= »), et la faire saisir ne
        # pourrait qu'introduire une erreur. Elle est lue et affichee avec le
        # projet, a titre d'information.
        self.label_nom_projet = QLabel("Aucun modèle chargé. Choisissez un fichier .prj pour commencer.")
        self.label_nom_projet.setWordWrap(True)
        self.label_nom_projet.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f.addRow(self.label_nom_projet)
        v.addWidget(groupe_projet)

        groupe_plan = QGroupBox("Plan et fichiers de calcul")
        f2 = formulaire(groupe_plan)
        self.combo_plan = QComboBox()
        self.combo_plan.setAccessibleName("Plan de référence")
        self.combo_plan.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_plan.setMinimumContentsLength(14)
        self.combo_plan.currentIndexChanged.connect(self._changer_plan)
        f2.addRow("Plan de référence :",
                  self._avec_temoin(self.combo_plan, "Plan_reference"))

        self.radio_du_plan = QRadioButton(
            "Reprendre les fichiers du plan")
        # COURT : a 13 pt, l'ancien libelle (« Choisir une autre geometrie ou
        # un autre flux », 543 px) faisait defiler l'etape Modele de cote.
        self.radio_override = QRadioButton(
            "Choisir la géométrie et le flux")
        self.radio_du_plan.setAccessibleDescription(
            "Utiliser la géométrie et le fichier Unsteady Flow du plan de référence.")
        self.radio_override.setAccessibleDescription(
            "Choisir la géométrie et le fichier Unsteady Flow dans les listes ci-dessous.")
        self.radio_du_plan.setToolTip(self.radio_du_plan.accessibleDescription())
        self.radio_override.setToolTip(self.radio_override.accessibleDescription())
        self.radio_du_plan.setChecked(True)
        self.radio_du_plan.toggled.connect(self._maj_mode_override)
        f2.addRow(self.radio_du_plan)
        self.label_fichiers_plan = QLabel()
        self.label_fichiers_plan.setWordWrap(True)
        self.label_fichiers_plan.setTextFormat(Qt.TextFormat.PlainText)
        self.label_fichiers_plan.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label_fichiers_plan.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        f2.addRow(self.label_fichiers_plan)
        f2.addRow(self.radio_override)

        self.combo_geometrie = QComboBox()
        self.combo_unsteady = QComboBox()
        for combo, nom in ((self.combo_geometrie, "Géométrie HEC-RAS"),
                           (self.combo_unsteady, "Flux instationnaire, fichier Unsteady Flow")):
            combo.setAccessibleName(nom)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(14)
        self.combo_geometrie.setEnabled(False)
        self.combo_unsteady.setEnabled(False)
        self.combo_geometrie.currentIndexChanged.connect(self._maj_resume)
        self.combo_unsteady.currentIndexChanged.connect(self._maj_resume)
        f2.addRow("Géométrie :", self._avec_temoin(
            self.combo_geometrie, "Geometrie_reference"))
        f2.addRow("Flux instationnaire :", self._avec_temoin(
            self.combo_unsteady, "Unsteady_reference"))
        # LE LIBELLE EST CELUI DE L'ENVELOPPE qui porte le « ! », pas du combo.
        self.label_geometrie_override = f2.labelForField(
            self.combo_geometrie.parentWidget())
        self.label_unsteady_override = f2.labelForField(
            self.combo_unsteady.parentWidget())
        self.combo_unsteady.setToolTip("Fichier Unsteady Flow (.u##) utilisé pour le calcul.")
        for combo in (self.combo_plan, self.combo_geometrie, self.combo_unsteady):
            combo.currentTextChanged.connect(self._maj_resume_fichiers)
        self._maj_resume_fichiers()

        # UNE SEULE ZONE 2D, PAS DE CHOIX (27/10/2026, demande utilisateur :
        # « limité à 1 pour le moment »). Le combo n'est plus dans la fenetre :
        # il garde seulement le nom de la zone, que le chargement renseigne et
        # que le resume affiche. Un modele a plusieurs zones est refuse au
        # chargement des couches.
        self.combo_zone_2d = QComboBox()
        self.combo_zone_2d.currentIndexChanged.connect(self._maj_resume)
        # LA ZONE 2D ET LE CRS NE SONT PAS DES COMPTES RENDUS DATES : ce sont
        # des valeurs COURANTES, presentees comme telles au resume et
        # consommees a l'ecriture. Or changer de plan — ou la geometrie de
        # surcharge — ne les touche pas : elles datent alors d'une AUTRE
        # geometrie, et rien ne le disait. L'avertissement vit ici, a cote du
        # champ concerne, et non sous le compte rendu de chargement, qui parle
        # d'un passe assume.
        self.label_geom_couches = texte_etat()
        self.label_geom_couches.setWordWrap(True)
        f2.addRow(self.label_geom_couches)
        v.addWidget(groupe_plan)

        # LES COUCHES SUIVENT LE PLAN (0.7.22, demande utilisateur). C'est le
        # geste qu'on fait juste apres l'avoir choisi : le plan dit quelle
        # geometrie on lit, « Charger les couches » la met sur la carte. La
        # 0.7.19 avait glisse le profil en long entre les deux, au motif qu'il
        # decrit lui aussi le modele ; a l'usage, il separait deux gestes qui
        # s'enchainent.
        v.addWidget(self._groupe_couches_existantes())

        # L'AXE EST UN OBJET DU MODELE, pas un objectif. Il vivait a l'onglet
        # « 2. Profil en long », a cote de la precision attendue, avec
        # laquelle il n'a rien a voir : l'un se dessine sur la carte comme les
        # sections et les injections, l'autre se decide devant un tableau.
        v.addWidget(self._groupe_axe())

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
        self.groupe_fenetre = QgsCollapsibleGroupBox("Fenêtre de simulation — réglages")
        self.groupe_fenetre.setObjectName("fenetreSimulation")
        self.groupe_fenetre.setSaveCollapsedState(False)
        self.groupe_fenetre.setToolTip(
            "Le plan de calcul est un clone du plan de référence et en hérite "
            "la fenêtre. Substituer un Unsteady Flow couvrant une autre "
            "période ne la déplace pas : HEC-RAS calculerait à côté des "
            "hydrogrammes, sans rien signaler.")
        vf = QVBoxLayout(self.groupe_fenetre)
        vf.setSpacing(8)
        vf.addWidget(texte_aide(
            "Valeurs reprises du plan de référence. Ajustez la période si le flux "
            "retenu couvre un autre événement, ou pour limiter la durée du calcul."))

        # Une ligne par champ garde les dates lisibles avec une grande police.
        # Le groupe se replie ; l'état modifié ou invalide reste en dehors.
        self.edit_sim_debut = QLineEdit()
        self.edit_sim_fin = QLineEdit()
        for champ, exemple in ((self.edit_sim_debut, "13OCT2014,00:00"),
                               (self.edit_sim_fin, "14OCT2014,04:00")):
            champ.setPlaceholderText(exemple)
            champ.textChanged.connect(self._maj_resume)
        details_fenetre = formulaire()
        self.edit_sim_debut.setAccessibleName("Début de la simulation")
        self.edit_sim_fin.setAccessibleName("Fin de la simulation")
        details_fenetre.addRow("Début :", self._avec_temoin(
            self.edit_sim_debut, self.PARAMETRES_FENETRE["debut"]))
        details_fenetre.addRow("Fin :", self._avec_temoin(
            self.edit_sim_fin, self.PARAMETRES_FENETRE["fin"]))

        self.edits_intervalles = {}
        for rang, (cle, libelle, exemple) in enumerate((
                ("intervalle_calcul", "Pas de calcul", "1SEC"),
                ("intervalle_sortie", "Intervalle de sortie", "1MIN"),
                ("intervalle_instantane", "Sortie détaillée", "1MIN"),
                ("intervalle_mapping", "Cartographie", "1MIN"))):
            champ = QLineEdit()
            champ.setPlaceholderText(exemple)
            champ.setAccessibleName(libelle + " de la simulation")
            champ.setToolTip("Intervalle HEC-RAS en SEC, MIN ou HOUR. Exemple : " + exemple)
            champ.textChanged.connect(self._maj_resume)
            details_fenetre.addRow(f"{libelle} :", self._avec_temoin(
                champ, self.PARAMETRES_FENETRE[cle]))
            self.edits_intervalles[cle] = champ
        vf.addLayout(details_fenetre)
        vf.addWidget(texte_aide(
            "Format JJMMMAAAA,HH:MM — intervalles en SEC, MIN ou HOUR."))

        self.label_fenetre = texte_etat()
        v.addWidget(self.groupe_fenetre)
        # Ce label est alimenté par le résumé existant : garder son message
        # visible même lorsque les champs secondaires sont repliés.
        v.addWidget(self.label_fenetre)
        self.groupe_fenetre.setCollapsed(True)

        # LE BOUTON D'ECRITURE A QUITTE CET ONGLET (22/09/2026, demande
        # utilisateur) : il vit sous le prefixe de scenario, a l'etape
        # Objectifs, et fait de nouveau les trois gestes — ecrire la
        # geometrie, composer le classeur, controler. Voir _groupe_classeur.

        v.addStretch(1)
        return page

    def _groupe_couches_existantes(self):
        groupe_charger = QGroupBox("Couches du modèle dans QGIS")
        v3 = QVBoxLayout(groupe_charger)
        v3.setSpacing(8)
        v3.addWidget(texte_aide(
            "Sections et injections éditables, avec l'emprise du modèle. "
            "Vous pourrez compléter ces objets sur la carte."))
        bouton_charger = QPushButton(
            "Charger les couches du modèle")
        bouton_charger.setAccessibleName("Charger les sections, injections et l'emprise du modèle dans QGIS")
        bouton_charger.setAutoDefault(False)
        bouton_charger.setToolTip(
            "Ajoute à la carte, en couches ÉDITABLES, ce que la géométrie "
            "contient déjà. C'est là-dessus qu'on dessine les objets "
            "manquants.")
        bouton_charger.clicked.connect(self._charger_couches_modele)
        self.bouton_charger_couches = bouton_charger  # cible d'un lien du fil
        v3.addWidget(bouton_charger, 0, Qt.AlignmentFlag.AlignLeft)
        self.label_couches = texte_etat()
        v3.addWidget(self.label_couches)
        return groupe_charger


    # CE QUE FAIT LE BOUTON, EN UN SEUL ENDROIT. _maj_bouton_controle la
    # reprend a chaque changement d'etat, precedee d'une phrase qui dit si
    # c'est le moment : deux textes a tenir d'accord auraient diverge, comme
    # les deux boites de compte rendu avant la 0.7.17.
    _INFOBULLE_CONTROLE = (
        "Écrit d'abord les sections et injections de l'étape 1 dans la "
        "géométrie HEC-RAS (en remplaçant tout objet de même nom déjà "
        "présent, après une sauvegarde horodatée du fichier), puis les "
        "shapefiles et le classeur, puis lance tous les contrôles et "
        "reporte les anomalies sur la carte.\n"
        "C'est le seul geste irréversible de la fenêtre, et il est à passer "
        "avant de lancer.\n\n"
        "Le détail est dans « Aide et configuration », "
        "§ « Écrire dans la géométrie ».")

    def _bouton_controle_parametrage(self):
        """
        L'ACTION N'APPARTIENT A AUCUN ONGLET (0.7.24, demande utilisateur).

        Elle est redescendue au bas de la fenetre, a cote de « Fermer », ou
        elle vivait jusqu'a la 0.7.19 — et son nom se raccourcit en
        « Ecrire dans la geometrie HEC-RAS ».

        QUATRE DEMENAGEMENTS EN CINQ VERSIONS ONT FINI PAR LE DIRE : bas de
        fenetre, onglet 1 (0.7.19), onglet 4 (0.7.21), onglet 2 (0.7.22), et
        chaque fois pour une raison vraie — le plan et les couches sont a
        l'onglet 1, le compte rendu se lit a l'onglet 4, les tolerances
        s'ecrivent a l'onglet 2. Elles etaient toutes vraies parce que ce
        geste CONSOMME LES TROIS PREMIERS ONGLETS ET PREPARE LE QUATRIEME :
        le loger dans l'un d'eux obligeait a revenir en arriere depuis les
        autres. Permanent, il n'est plus au bout d'un chemin.

        CE QUI CHANGE PAR RAPPORT A LA 0.7.18, ou il etait deja la : il DIT
        desormais si c'est le moment. Vert quand tout ce qu'il consomme est
        pret, gris sinon, avec le manquant en infobulle — c'est ce qui
        repondait a l'objection d'origine, « permanent et visible depuis six
        onglets dont cinq n'en font rien ».

        IL RESTE CLIQUABLE EN GRIS, A DESSEIN. Desactive, il n'aurait aucun
        moyen de dire POURQUOI, et le compte rendu de composition nomme deja
        precisement ce qui manque — mieux qu'une infobulle sur un bouton
        mort.

        --- ce que disaient les versions precedentes -----------------------

        L'ACTION EST JUSTE AVANT LE LANCEMENT (0.7.21, demande utilisateur).

        « Ecrire, composer et controler » a d'abord vecu en bas de la fenetre,
        permanent, visible depuis les six onglets — y compris ceux ou il n'a
        rien a faire. Il est passe a l'onglet 1 en 0.7.19, au motif que le
        plan, le profil en long et les couches sont la. Mais il consomme AUSSI
        les objectifs de l'onglet 2 et les dossiers de l'onglet 3, et surtout
        CE QU'IL PRODUIT SE LIT ICI : le paquet, le classeur pre-rempli, le
        compte rendu de controle que le groupe « Validation de la derniere
        composition » resume trois lignes plus haut. Le laisser a l'onglet 1
        obligeait a revenir en arriere pour composer ce que l'onglet 4 allait
        juger.

        D'OU SON NOM : « Controle du parametrage ». « Mise a jour du modele »
        annoncait l'effet de bord — l'ecriture dans la geometrie — la ou
        l'utilisateur cherche le geste qui VERIFIE avant de lancer. L'ecriture
        reste, elle est dite par le texte de l'encadre et par l'infobulle.

        CE QUE CELA COUTE : recomposer au fil de l'ajustement des couches — le
        cas NORMAL — fait maintenant l'aller-retour 1 -> 4. En echange, on ne
        lance plus rien sans etre passe devant le compte rendu.
        """
        # L'ENCADRE ET SA PHRASE D'EXPLICATION DISPARAISSENT AVEC L'ONGLET.
        # Hors d'un onglet, il n'y a plus de place pour une ligne de texte —
        # et il n'y en a plus besoin : ce que le bouton fait vit dans son
        # infobulle, ce qu'il ecrit dans l'aide, § « Ecrire dans la
        # geometrie ». La phrase avait deja ete ramenee a une ligne le
        # 08/09 parce que sa seconde ligne sortait coupee.
        # LE BOUTON EST LE SEUL A COMPOSER (24/09/2026, demande utilisateur) :
        # la recomposition automatique des 0.9.5 a 0.9.14 composait les
        # prefixes a demi tapes. Il ecrit, compose et controle ; ce qui change
        # ensuite porte un « ! » jusqu'au clic suivant.
        # DEUX LIGNES (27/10/2026) : sur une seule, le libelle faisait 752 px
        # a 13 pt et l'etape Parametres defilait de cote. Le plancher de
        # hauteur ci-dessous compte les deux lignes : c'est lui qui manquait
        # le 08/09, quand la seconde sortait coupee.
        bouton_composer = QPushButton(BOUTON_GEOMETRIE.replace(" et ", " et\n", 1))
        bouton_composer.setAccessibleName(BOUTON_GEOMETRIE)
        self.bouton_composer = bouton_composer      # cible d'un lien du fil
        # Mise en avant par le STYLE, jamais par la touche Entree : ce bouton
        # ecrit dans la geometrie HEC-RAS. Voir keyPressEvent().
        bouton_composer.setObjectName("boutonControleAttente")
        bouton_composer.setMinimumWidth(250)
        bouton_composer.setToolTip(self._INFOBULLE_CONTROLE)
        # LE GESTE COMPLET, DE NOUVEAU (22/09/2026) : ecrire, composer,
        # controler, compte rendu. « clicked » emet un booleen ; le sablier
        # ne le transmet pas (voir avec_sablier).
        bouton_composer.clicked.connect(self._composer_et_controler)
        # SA HAUTEUR NE SE NEGOCIE PAS. Dans une fenetre trop courte, la zone
        # defilante COMPRIME le contenu au lieu de faire apparaitre une barre :
        # le dernier encadre de l'onglet passe sous sa taille utile, et ce
        # bouton-ci sortait ecrase, son libelle coupe a mi-hauteur — mesure du
        # 8 septembre, 20 px pour 31 demandes. Un plancher suffit a le
        # soustraire au partage. Il se calcule sur la police et le remplissage
        # de la feuille de style (6 px en haut, 6 en bas, 1 de bordure) :
        # sizeHint() ne vaut rien ici, le bouton n'est pas encore habille.
        bouton_composer.setMinimumHeight(
            2 * bouton_composer.fontMetrics().height() + 2 * 6 + 2 * 1)
        return bouton_composer

    def _maj_bouton_controle(self):
        """
        Le bouton dit si c'est le moment : vert quand tout ce qu'il consomme
        est pret, gris sinon, et l'infobulle nomme le manquant.

        LES ETAPES SONT CELLES DU FIL CONDUCTEUR, et c'est voulu : deux
        lectures de l'avancement qui divergeraient donneraient un bouton vert
        sous un fil qui reclame encore une etape. _maj_fil appelle donc cette
        methode, et une seule liste sert aux deux.

        LE VERT N'EST PAS LE TEAL DE « boutonPrincipal ». Le teal dit
        « action principale de la fenetre » — il le reste. Le vert dit
        « maintenant », et c'est le meme vert que les etapes franchies du fil
        conducteur, juste au-dessus : l'oeil fait le lien sans qu'on
        l'explique.
        """
        bouton = getattr(self, "bouton_controle", None)
        if bouton is None:
            return                      # appele avant la construction du bas
        manquant = [nom for nom, ok in self._etapes_avant_controle()
                    if not ok]
        pret = not manquant and not self.pid_lance
        bouton.setObjectName("boutonControlePret" if pret
                             else "boutonControleAttente")
        # Qt ne relit la feuille de style qu'a la « repolissure » : changer
        # l'objectName ne suffit pas, le bouton garderait sa couleur.
        bouton.style().unpolish(bouton)
        bouton.style().polish(bouton)
        if self.pid_lance:
            etat = ("Un calage tourne (processus "
                    f"{self.pid_lance}). Recomposer maintenant réécrirait la "
                    "géométrie et le classeur qu'il partage — la question "
                    "sera posée.")
        elif manquant:
            etat = "Il manque encore : " + ", ".join(manquant) + "."
        else:
            etat = "Tout ce que ce contrôle consomme est prêt."
        bouton.setToolTip(etat + "\n\n" + self._INFOBULLE_CONTROLE)

    def _parametres_du_paquet(self):
        """
        Les parametres du paquet DEJA COMPOSE, ou {} s'il n'y en a pas.

        RELUS SEULEMENT S'ILS ONT CHANGE — meme regle que le journal du
        suivi : un stat par appel, et cette methode est appelee a chaque
        frappe dans le dossier de sortie.
        """
        if not self.classeur:
            return {}
        try:
            import parametres as mod_parametres
            fichier = mod_parametres.chemin(self.classeur)
            st = os.stat(fichier) if fichier.is_file() else os.stat(self.classeur)
            cle = (str(fichier), st.st_size, st.st_mtime_ns)
            if cle == getattr(self, "_cle_paquet_lu", None):
                return self._paquet_lu
            self._paquet_lu = mod_parametres.lire(self.classeur)
            self._cle_paquet_lu = cle
            return self._paquet_lu
        except Exception as e:                              # noqa: BLE001
            journaliser("Lecture des parametres du paquet compose", e)
            return {}

    # Ce que la fenetre tient, et le nom que le paquet lui donne. L'ordre est
    # celui de la lecture a l'ecran : ce qu'on vient de changer d'abord.
    _COMPARES = (
        ("Prefixe_scenario", "préfixe de scénario"),
        ("Dossier_sortie", "dossier de sortie"),
        ("Sous_dossier_resultats", "sous-dossier des résultats"),
        ("Sous_dossier_suivi", "sous-dossier du suivi"),
        ("Tolerance_volume_pct", "écart de volume admis"),
        ("Tolerance_pic_pct", "écart de pointe admis"),
        ("Bilan_masse_max_pct", "erreur de bilan de masse admise"),
        ("Nb_max_iterations_par_apport", "maximum d’essais par apport"),
        ("Dossier_projet_HECRAS", "dossier du projet HEC-RAS"),
        ("Nom_projet", "projet HEC-RAS"),
        ("Plan_reference", "plan de référence"),
        # CONSOMMES A LA COMPOSITION, ET JUSQU'ICI JAMAIS COMPARES (24/09/2026,
        # demande utilisateur) : les changer apres coup ne laissait aucune trace.
        ("Geometrie_reference", "géométrie"),
        ("Unsteady_reference", "flux instationnaire"),
        ("Nom_zone_2D", "zone d’écoulement 2D"),
        ("Sens_axe", "sens du tracé de l’axe"),
        ("PK_origine_m", "PK d’origine"),
        ("Simulation_debut", "début de la simulation"),
        ("Simulation_fin", "fin de la simulation"),
        ("Intervalle_calcul", "pas de calcul"),
        ("Intervalle_sortie", "intervalle de sortie"),
        ("Intervalle_instantane", "sortie détaillée"),
        ("Intervalle_mapping", "cartographie"),
    )

    def _valeurs_de_la_fenetre(self):
        """Ce que la fenetre tient MAINTENANT, sous les cles du paquet."""
        plan = self.combo_plan.currentData() if hasattr(self, "combo_plan") else None
        geometrie, flux = self._geometrie_effective(), self._unsteady_effective()
        saisie = self.fenetre_saisie()
        return {
            **{parametre: saisie[cle]
               for cle, parametre in self.PARAMETRES_FENETRE.items()},
            "Geometrie_reference": f"g{geometrie}" if geometrie else "",
            "Unsteady_reference": f"u{flux}" if flux else "",
            "Nom_zone_2D": self.combo_zone_2d.currentText(),
            "Sens_axe": self.combo_sens_axe.currentData(),
            "PK_origine_m": self.spin_pk_origine.value(),
            "Prefixe_scenario": self.edit_prefixe_scenario.text().strip(),
            "Dossier_sortie": self.edit_dossier_sortie.text().strip(),
            "Sous_dossier_resultats":
                self.edit_sous_dossier_resultats.text().strip(),
            "Sous_dossier_suivi": self.edit_sous_dossier_suivi.text().strip(),
            "Tolerance_volume_pct": self.spin_tol_volume.value(),
            "Tolerance_pic_pct": self.spin_tol_pic.value(),
            "Bilan_masse_max_pct": self.spin_bilan_masse.value(),
            "Nb_max_iterations_par_apport": self.spin_nb_max_essais.value(),
            # LE DOSSIER VIENT DU CHAMP, PAS DE info_projet, qui ne porte que
            # le nom du projet et ses listes — c'est _dossier_projet qui sait.
            "Dossier_projet_HECRAS": str(self._dossier_projet() or ""),
            "Nom_projet": (self.info_projet or {}).get("nom_projet", ""),
            "Plan_reference": f"p{plan['numero']}" if plan else "",
        }

    @staticmethod
    def _memes_valeurs(fenetre, paquet):
        """
        Deux valeurs disent-elles la meme chose ?

        LES NOMBRES SE COMPARENT EN NOMBRES : le classeur rend 5.0 la ou le
        spin rend 5, et « 5.0 » != « 5 » aurait signale un ecart a chaque
        ouverture. Le reste se compare en texte, sans casse ni espaces de
        bord : un chemin recopie diffère souvent d'un antislash final.
        """
        if paquet is None:
            paquet = ""
        try:
            return abs(float(fenetre) - float(paquet)) < 1e-9
        except (TypeError, ValueError):
            pass
        a = str(fenetre).strip().replace("\\", "/").rstrip("/").casefold()
        b = str(paquet).strip().replace("\\", "/").rstrip("/").casefold()
        return a == b

    def _ecarts_avec_le_paquet(self):
        """
        Ce que la fenetre tient et que le paquet compose ne porte pas.

        POURQUOI CE CONTROLE (20/09/2026, demande utilisateur). Le paquet est
        un INSTANTANE : il fige le prefixe, les dossiers, les tolerances et
        le modele au moment ou l'on a clique. Rien n'empechait ensuite de
        changer le prefixe, le dossier de sortie ou la precision et de
        lancer : le calage lisait le classeur, donc les valeurs d'AVANT, et
        l'ecran montrait les autres. Les deux etaient vraies separement, et
        personne ne disait qu'elles ne parlaient plus du meme calage.

        LE CONTROLE NE CORRIGE RIEN. Recomposer est le geste de
        l'utilisateur, et recomposer efface des choses — c'est le bouton qui
        ecrit dans la geometrie. On dit l'ecart ; on ne le resout pas.

        UN ECART EST UN CHAMP CHANGE DEPUIS QUE LE PAQUET EST LA (24/09/2026).
        Differer du paquet ne suffit plus : il faut aussi differer de ce que
        l'ecran tenait quand le paquet est arrive (_valeurs_au_paquet, pose
        par le setter de « classeur »). La composition normalise des champs
        — un sous-dossier vide devient « resultats_finaux » ou « suivi » dans
        le paquet — et sans cette regle ils s'allumeraient des le clic, alors
        que personne n'y a touche.

        Rend {cle du paquet : texte de l'ecart}, dans l'ordre de _COMPARES.
        """
        paquet = self._parametres_du_paquet()
        if not paquet:
            return {}
        try:
            fenetre = self._valeurs_de_la_fenetre()
            # UNE FENETRE DE SIMULATION ABSENTE DU PAQUET EST CELLE DU PLAN :
            # la composition ne la transmet que si elle en differe
            # (_parametres_fenetre).
            origine = (self.combo_plan.currentData() or {}).get("fenetre") or {}
        except (AttributeError, RuntimeError):
            return {}           # fenetre pas encore entierement construite
        paquet = {**{parametre: origine.get(cle, "")
                     for cle, parametre in self.PARAMETRES_FENETRE.items()},
                  **paquet}
        au_paquet = getattr(self, "_valeurs_au_paquet", None) or {}
        ecarts = {}
        for cle, libelle in self._COMPARES:
            if cle not in paquet:
                continue        # paquet d'une version anterieure : on se tait
            vue, fige = fenetre.get(cle, ""), paquet.get(cle)
            if self._memes_valeurs(vue, fige):
                continue
            if cle in au_paquet and self._memes_valeurs(vue, au_paquet[cle]):
                continue        # champ que personne n'a touche depuis
            ecarts[cle] = (f"{libelle} : « {self._montrer(cle, vue)} » à l’écran, "
                           f"« {self._montrer(cle, fige)} » dans le paquet")
        return ecarts

    def _montrer(self, cle, valeur):
        """Une valeur comparee, telle qu'un humain la lit : le libelle du
        sens de l'axe, la virgule d'un nombre."""
        if valeur is None:
            return ""
        if cle == "Sens_axe":
            rang = self.combo_sens_axe.findData(valeur)
            return self.combo_sens_axe.itemText(rang) if rang >= 0 else valeur
        return format(valeur, "g").replace(".", ",") if isinstance(valeur, float) else valeur

    def _classeur_neuf_annonce(self):
        """
        Dit qu'un preFIXE CHANGE fera un classeur NEUF, donc AUX CIBLES VIDES.

        LE CAS SIGNALE LE 21 SEPTEMBRE 2026 : « changer le prefixe et
        recliquer sur parametrage supprime les apports ». Mesure faite :
        RIEN N'EST SUPPRIME — l'ancien classeur garde ses cibles, et la
        correspondance du neuf est correctement reconstruite. Mais le
        nouveau classeur nait VIDE, la fenetre bascule dessus, et « Ce que
        portent les hydrogrammes cibles » n'affiche plus rien : a l'ecran,
        c'est indiscernable d'une perte.
        ON NE RECOPIE PAS LES CIBLES de l'ancien : un Q10 n'a pas les
        hydrogrammes d'un Q100, et les reporter fabriquerait un calage faux
        qui aurait l'air juste. On DIT, et on nomme le fichier ou le travail
        se trouve encore.
        """
        if not self.classeur:
            return ""
        actuel = Path(self.classeur)
        prefixe = self.edit_prefixe_scenario.text().strip()
        try:
            futur = actuel.parent / noyau.nom_classeur(prefixe)
        except Exception:                                   # noqa: BLE001
            return ""
        if futur == actuel or futur.exists():
            return ""
        try:
            import pandas as pd
            cibles = pd.read_excel(actuel, sheet_name="Cibles")
            remplies = int(cibles.drop(columns=["Temps_h"], errors="ignore")
                           .notna().to_numpy().sum())
        except Exception as e:                              # noqa: BLE001
            journaliser("Lecture des cibles du classeur courant", e)
            return ""
        if not remplies:
            return ""
        return (f"Composer maintenant créera <b>{futur.name}</b>, un "
                f"classeur <b>neuf, aux cibles vides</b>. Les "
                f"{compte(remplies, 'valeur déjà saisie reste', 'valeurs déjà saisies restent')} dans "
                f"<b>{actuel.name}</b> — rien n’est supprimé, mais elles "
                f"ne seront pas reprises : un scénario n’a pas les "
                f"hydrogrammes d’un autre.")

    def _temoin(self, *cles):
        """
        Le « ! » rouge d'un reglage que le paquet compose ne porte plus
        (24/09/2026, demande utilisateur) : cache tant que l'ecran et le
        paquet disent la meme chose, allume par _maj_temoins.

        JAMAIS LA COULEUR SEULE : le signe porte le sens, l'infobulle et la
        description accessible disent les deux valeurs. Le rouge suit le
        theme sombre : QLabel est ici interface.Etiquette.
        """
        temoin = QLabel(f"<b style='color:{ISL_ROUGE}'>!</b>")
        temoin.setAccessibleName("Réglage à actualiser")
        temoin.setVisible(False)
        self._temoins.append((cles, temoin))
        return temoin

    def _avec_temoin(self, champ, *cles):
        """Le champ suivi de son « ! », dans une enveloppe qui lui rend le focus."""
        enveloppe = QWidget()
        ligne = QHBoxLayout(enveloppe)
        ligne.setContentsMargins(0, 0, 0, 0)
        ligne.setSpacing(6)
        ligne.addWidget(champ, 1)
        ligne.addWidget(self._temoin(*cles))
        # LE RACCOURCI DU LIBELLE VISE L'ENVELOPPE, qui le passe au champ :
        # sans ce relais, Alt+V tomberait sur un cadre qui ne prend pas le
        # focus.
        enveloppe.setFocusProxy(champ)
        return enveloppe

    def _maj_temoins(self, ecarts):
        """
        Allume le « ! » de chaque champ perime, et celui de l'entree de la
        bande de l'etape qui le porte : un champ perime sur une autre etape
        serait sinon invisible depuis celle ou l'on est.
        """
        onglets = getattr(self, "onglets", None)
        perimes = {}
        for cles, temoin in self._temoins:
            textes = [ecarts[c] for c in cles if c in ecarts]
            temoin.setVisible(bool(textes))
            detail = (f"À actualiser par « {BOUTON_GEOMETRIE} » : "
                      + " ; ".join(textes)) if textes else ""
            temoin.setToolTip(detail)
            temoin.setAccessibleDescription(detail)
            if not textes or onglets is None:
                continue
            for rang in range(onglets.count()):
                if onglets.widget(rang).isAncestorOf(temoin):
                    perimes.setdefault(rang, []).extend(
                        t.split(" : ", 1)[0] for t in textes)
        if onglets is None or getattr(self, "bande", None) is None:
            return
        # LE « ! » D'ETAPE EST SUR SON ENTREE DE LA BANDE (23/10/2026) : il
        # etait pose a droite du titre de l'onglet. Le numero le porte —
        # « 2 ! » —, l'entree passe au rouge de la charte (remappe en theme
        # sombre), l'infobulle et le nom accessible nomment les reglages ;
        # le titre de l'etape ne change pas.
        rouge = QColor(couleur_theme(ISL_ROUGE, self.bande))
        for rang in range(onglets.count()):
            reglages = perimes.get(rang)
            element = self.bande.item(rang)
            complet = element.text() == self._textes_bande_vus[0][rang]
            for vus, sans in zip(self._textes_bande_vus, self._textes_bande):
                numero, saut, nom = sans[rang].partition("\n")
                vus[rang] = f"{numero} !{saut}{nom}" if reglages else sans[rang]
            element.setText(self._textes_bande_vus[0 if complet else 1][rang])
            element.setData(Qt.ItemDataRole.ForegroundRole,
                            rouge if reglages else None)
            infobulle = element.toolTip().split("\n\nÀ actualiser")[0]
            titre = onglets.tabText(rang)
            if reglages:
                detail = "À actualiser dans cette étape : " + ", ".join(reglages) + "."
                element.setToolTip(f"{infobulle}\n\n{detail}")
                element.setData(Qt.ItemDataRole.AccessibleTextRole,
                                f"{titre} — {detail}")
            else:
                element.setToolTip(infobulle)
                element.setData(Qt.ItemDataRole.AccessibleTextRole, titre)

    def _maj_coherence(self):
        """
        Dit ce qui ne concorde plus : un « ! » sur chaque champ, et la liste a
        l'etape Lancer, ou le lancement le refuse.
        """
        ecarts = self._ecarts_avec_le_paquet()
        self._maj_temoins(ecarts)
        label = getattr(self, "label_prochaine_etape", None)
        if label is None:
            return
        if not ecarts:
            # LA SEULE VOIX DE CE CADRE (23/10/2026) : la relecture des
            # cibles y ecrivait aussi, et le texte de l'une effacait celui
            # de l'autre au rafraichissement suivant.
            manquantes = getattr(self, "_cibles_manquantes", None)
            if not self.classeur:
                dire(label, ATTENTE_PAQUET)
            elif manquantes:
                dire(label,
                     "<b>Étape suivante</b> — ouvrez l’Excel (étape "
                     "Paramètres, « Ouvrir dans Excel ») et complétez la "
                     "feuille « Cibles » pour " + ", ".join(manquantes)
                     + ", puis lancez. Recomposer plus tard préserve les "
                       "hydrogrammes déjà saisis.")
            elif manquantes == []:
                dire(label,
                     f"<b style='color:{ISL_VERT}'>Tous les hydrogrammes "
                     f"cibles sont renseignés</b> — le calage peut être lancé.")
            else:
                dire(label, "Le paquet composé dit la même chose que cet écran.")
            return
        neuf = self._classeur_neuf_annonce()
        dire(label,
             f"<b>{compte(len(ecarts), 'réglage changé', 'réglages changés')} depuis la composition —"
             f" le calage lirait le paquet, pas l’écran :</b><br>• "
             + "<br>• ".join(ecarts.values())
             + f"<br>Cliquer « {BOUTON_GEOMETRIE} » (étape Paramètres) pour "
               "les reporter : le lancement est refusé d’ici là."
             + (f"<br>{neuf}" if neuf else ""))

    def _etapes_preparation(self):
        """
        LES QUATRE ETAPES DE LA SAISIE AVANT LANCEMENT, et la seule liste qui
        les dise. Le fil conducteur les enonce, la barre du bas les compte.

        ELLES NE SONT PAS CELLES DE _etapes_avant_controle, et la difference
        est voulue : celles-ci vont jusqu'au paquet COMPOSE, qui est ce que le
        bouton PRODUIT. Les compter parmi ses prealables l'aurait laisse gris
        exactement quand il faut cliquer — voir _etapes_avant_controle.
        """
        return [
            ("Modèle chargé", self.info_projet is not None
             and couche_vivante(self.couche_sections) is not None),
            ("Profil en long",
             couche_vivante(self.combo_axe.currentLayer()) is not None),
            ("Dossier de sortie", bool(self.edit_dossier_sortie.text().strip())),
            # UN PAQUET PERIME N'EST PAS COMPOSE (24/09/2026) : la barre et le
            # fil ne disent pas « pret » tant qu'un « ! » reste allume.
            ("Paquet composé",
             bool(self.classeur) and not self._ecarts_avec_le_paquet()),
        ]

    def _etapes_avant_controle(self):
        """
        Ce que « Ecrire dans la geometrie HEC-RAS » consomme, et si c'est
        la. Partage sa
        liste avec le fil conducteur — voir _maj_bouton_controle.

        LE PAQUET COMPOSE N'EN EST PAS. C'est ce que ce bouton PRODUIT : le
        compter parmi ses prealables l'aurait laisse gris jusqu'au premier
        clic, donc gris exactement quand il faut cliquer.
        """
        # LE BOUTON COMPOSE DE NOUVEAU (22/09/2026) : il consomme donc aussi
        # l'axe, le dossier de sortie — propose tout seul des que le prefixe
        # est la — et le prefixe. Un manquant se lit dans son infobulle avant
        # le clic, et dans le refus apres.
        return [
            ("le modèle chargé", self.info_projet is not None),
            ("la zone 2D", bool(self.combo_zone_2d.currentText().strip())),
            ("les couches de sections et d'injections",
             couche_vivante(self.couche_sections) is not None
             and couche_vivante(self.couche_injections) is not None),
            ("l'axe hydraulique",
             couche_vivante(self.combo_axe.currentLayer()) is not None),
            ("le préfixe de scénario",
             bool(self.edit_prefixe_scenario.text().strip())
             if hasattr(self, "edit_prefixe_scenario") else False),
            ("le dossier de sortie",
             bool(self.edit_dossier_sortie.text().strip())
             if hasattr(self, "edit_dossier_sortie") else False),
        ]

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
            "« <préfixe>-<précédent> » : les apports situés en amont sont tenus "
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

    def _dossier_projet(self):
        """
        Le dossier du modele, deduit du .prj choisi. Chaine vide si rien.

        TOUT CE QUI SUIT TRAVAILLE SUR LE DOSSIER — la geometrie, l'Unsteady
        Flow et le .hdf sont ses voisins, nommes d'apres le projet. Mais ce
        n'est pas le dossier qu'on DESIGNE : un dossier de modele contient
        des dizaines de fichiers, et rien n'y distingue a l'oeil un projet
        HEC-RAS d'un autre. Le .prj, lui, EST le projet. On demande donc le
        fichier et l'on en deduit le reste, au lieu de demander le contenant
        et d'y chercher ce qu'on veut.
        """
        chemin = self.edit_projet_hecras.text().strip()
        return str(Path(chemin).parent) if chemin else ""

    def _parcourir_projet_hecras(self):
        # LE FICHIER, PAS LE DOSSIER. Un selecteur de dossier ne montre pas
        # ce qu'on cherche : il faut savoir d'avance lequel des dossiers
        # contient le modele, et rien a l'ecran ne le dit. Le filtre « *.prj »
        # montre les projets et masque le reste.
        depart = self._dossier_projet() or ""
        with sans_sablier(self):
            prj, _ = QFileDialog.getOpenFileName(
                self, "Fichier de projet HEC-RAS (.prj)", depart,
                "Projet HEC-RAS (*.prj);;Tous les fichiers (*)")
        if not prj:
            return
        self.edit_projet_hecras.setText(prj)
        # LE .prj, PAS SON DOSSIER : le noyau y prenait le premier projet
        # venu, pas forcement celui-ci (audit du 11/10/2026).
        self._charger_projet_hecras(prj)

    def _charger_projet_hecras(self, projet):
        try:
            self.info_projet = noyau.lister_projet_hecras(projet)
        except Exception as e:
            journaliser("Lecture du projet HEC-RAS", e)
            QMessageBox.critical(self, "Projet HEC-RAS", str(e))
            return

        # Version lue dans les fichiers, la plus recente en cas de melange :
        # un projet ancien repris avec une version recente en contient
        # plusieurs, et seule la plus recente sait toutes les relire.
        self.version_hecras, versions_vues = noyau.version_hecras_du_projet(projet)
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
        # Le modele est connu : si le prefixe l'est aussi, le dossier de
        # sortie se propose, et la composition peut partir.
        self._proposer_dossier_sortie()
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

        self._maj_resume_fichiers()

    def _maj_resume_fichiers(self, *_):
        """Présente les fichiers effectifs du plan, sans toucher aux choix.

        Les listes masquées conservent leur sélection. Hors surcharge, leurs
        anciens choix ne décrivent pas forcément le plan qui vient d'être
        sélectionné : le résumé part donc de ses numéros et de l'inventaire
        déjà chargé, sans lire de fichier.
        """
        surcharge = self.radio_override.isChecked()
        for widget in (self.combo_geometrie, self.combo_unsteady,
                       self.label_geometrie_override, self.label_unsteady_override):
            widget.setVisible(surcharge)
        self.label_fichiers_plan.setVisible(not surcharge)

        plan = self.combo_plan.currentData()
        if not plan:
            texte = "Choisissez un plan pour afficher sa géométrie et son flux."
        else:
            inventaire = self.info_projet or {}

            def fichier_du_plan(cle, collection, prefixe, combo):
                numero = plan.get(cle)
                if numero is None:
                    return "non renseigné dans le plan"
                for fichier in inventaire.get(collection, []):
                    if str(fichier.get("numero")) == str(numero):
                        titre = fichier.get("titre", "")
                        return f"{prefixe}{numero} — {titre}" if titre else f"{prefixe}{numero}"
                # Les recettes et les restaurations peuvent peupler les
                # listes avant l'inventaire : leur contenu reste une lecture.
                for index in range(combo.count()):
                    fichier = combo.itemData(index)
                    if isinstance(fichier, dict) and str(fichier.get("numero")) == str(numero):
                        return combo.itemText(index)
                return f"{prefixe}{numero}"

            geometrie = fichier_du_plan("geometrie", "geometries", "g", self.combo_geometrie)
            flux = fichier_du_plan("unsteady", "unsteady", "u", self.combo_unsteady)
            texte = f"Géométrie : {geometrie} · Flux : {flux}"
        self.label_fichiers_plan.setText(texte)
        self.label_fichiers_plan.setAccessibleName(texte)
        self.label_fichiers_plan.setToolTip(texte)

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
                 f"<span style='color:{ISL_TEAL_SOMBRE}'><b>Fenêtre modifiée</b> — "
                 f"elle sera imposée au plan de calcul.</span>")
            return [f"Fenêtre de simulation : {saisie['debut']} → "
                    f"{saisie['fin']}  (modifiée)"]

        dire(self.label_fenetre, "Identique au plan de référence.")
        return [f"Fenêtre de simulation : {saisie['debut']} → "
                f"{saisie['fin']}  (du plan)"]

    def _changer_plan(self, _index):
        self._remplir_fenetre_depuis_plan()
        self._maj_resume()
        self._dire_coeurs()
        self._dire_titres_prefixe()

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
                    "Choisir d'abord le fichier .prj du projet HEC-RAS "
                    "(« Choisir le projet… »).")
            numero_geom = self._geometrie_effective()
            if not numero_geom:
                raise ValueError("Choisir un plan de référence.")
            chemin_hdf = (Path(self._dossier_projet())
                         / f"{self.info_projet['nom_projet']}.g{numero_geom}.hdf")
            reponse = noyau.charger_couches_modele(chemin_hdf)
        except Exception as e:
            journaliser("Chargement des couches du modèle", e)
            QMessageBox.critical(self, "Chargement du modèle", str(e))
            return

        self.crs_modele = reponse.get("crs") or "EPSG:2154"
        self.geom_couches = numero_geom
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
        # Depuis une COPIE du .gXX.hdf : voir copie_pour_maillage().
        copie = copie_pour_maillage(chemin_hdf)
        maillage = QgsMeshLayer(str(copie) if copie else "",
                                "Maillage 2D (HEC-RAS)", "mdal")
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
            self.couche_injections, self.couche_sections, self.couche_maillage,
            self.couche_perimetre)
        if echecs_style:
            journaliser("Styles non appliqués : " + " ; ".join(echecs_style))
        ordonner_couches(projet, [self.couche_injections, self.couche_sections,
                                  self.couche_maillage, self.couche_perimetre])

        # La zone 2D est indispensable : HEC-RAS y rattache sections et
        # injections. Le plugin n'en gere qu'une : avec plusieurs, il n'en
        # retient aucune, et « Composer » reste bloque sur « la zone 2D ».
        zones = [p["zone"] for p in reponse["perimetres"]]
        self.combo_zone_2d.clear()
        if len(zones) == 1:
            self.combo_zone_2d.addItem(zones[0])
        refus_zones = (
            f"<b>Ce modèle comporte {len(zones)} zones d'écoulement 2D "
            f"({', '.join(zones)}) : le plugin n'en gère qu'une pour le "
            f"moment.</b> Le calage ne peut pas être lancé sur ce modèle.<br>"
            if len(zones) > 1 else "")

        # Compte rendu volontairement telegraphique : ce qui est arrive sur la
        # carte se voit sur la carte. Seul ce qui NE se voit pas — un
        # maillage absent, des objets pas encore pretraites — merite une
        # phrase, parce que rien d'autre ne le dirait.
        pretraitee = reponse.get("geometrie_pretraitee", True)
        dire(self.label_couches,
             refus_zones +
             f"<b>{compte(len(reponse['sections']), 'section')}</b>, "
             f"<b>{compte(len(reponse['injections']), 'injection')}</b> et "
             f"<b>{compte(len(reponse['perimetres']), 'emprise 2D', 'emprises 2D')}</b> ajoutées à "
             f"la carte, éditables."
             + ("" if reponse["sections"] else
                " Aucune section existante : la couche attend les nouvelles.")
             + (" Géométrie jamais prétraitée par HEC-RAS : maillage "
                "indisponible, contours de zone 2D lus directement dans "
                "le fichier géométrie. Dessiner les sections et injections "
                f"manquantes, puis cliquer « {BOUTON_GEOMETRIE} » (étape "
                "Paramètres) — le maillage apparaîtra au premier calcul."
                if not pretraitee else
                f" Maillage natif : {compte(groupes, 'donnée')}."
                if maillage.isValid() else
                " Maillage natif indisponible ici (MDAL) — sans effet sur la "
                "suite.")
             + (f"<br>{compte(len(reponse['en_attente_pretraitement']), 'objet écrit', 'objets écrits')} "
                f"mais pas encore prétraités par HEC-RAS "
                f"({', '.join(reponse['en_attente_pretraitement'][:5])}) : "
                f"affichés d'après le fichier géométrie, pris en compte au "
                f"prochain calcul."
                if reponse.get("en_attente_pretraitement") else "")
             + (f"<br><b>{compte(len(reponse['objets_illisibles']), 'objet déclaré', 'objets déclarés')} "
                f"dans {chemin_hdf.with_suffix('').name} mais illisible(s) "
                f"({', '.join(reponse['objets_illisibles'][:5])}) :</b> tracé "
                f"non reconnu, absent de la carte. Transmettre le bloc "
                f"« Reference Line Name= » ou « BC Line Name= » correspondant."
                if reponse.get("objets_illisibles") else ""))
        self._maj_resume()

    # --- Onglet 3 : Objectifs et precision -----------------------------------

    # --- Groupes deplacables ------------------------------------------------
    #
    # CHAQUE GROUPE EST BATI PAR SA PROPRE METHODE, et l'onglet ne fait que
    # les assembler. Ils ont deja change d'onglet une fois — l'axe est passe
    # au « 1. Modele », le classeur aux « Objectifs » — et ils rechangeront :
    # l'ordre des onglets suit celui des decisions, qui s'affine a l'usage.
    # Les garder soudes a leur onglet obligeait a deplacer cent lignes de
    # widgets a chaque fois, avec le risque que cela porte.

    def _groupe_axe(self):
        groupe_axe = QGroupBox("Axe du profil en long")
        groupe_axe.setToolTip(
            "Une polyligne unique, dessinée de l'amont vers l'aval, en "
            "projection métrique : elle donne les PK et le profil en long.")
        f = formulaire(groupe_axe)
        f.addRow(texte_aide(
            "Choisissez une couche contenant une seule polyligne, en projection métrique."))
        self.combo_axe = QgsMapLayerComboBox()
        self.combo_axe.setAccessibleName("Couche de l'axe hydraulique")
        self.combo_axe.setMinimumContentsLength(14)
        self.combo_axe.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo_axe.setFilters(Qgis.LayerFilter.LineLayer)
        # UNE ENTREE VIDE, SANS QUOI L'AXE EST « CHOISI » SANS QUE PERSONNE
        # NE L'AIT CHOISI. Sans elle, currentLayer() n'est jamais None des
        # qu'une couche ligne existe dans le projet — et « Charger les couches
        # du modele » en ajoute deux, fabriquees par le plugin lui-meme. Trois
        # consequences : le fil conducteur cochait « Profil en long » pour un
        # geste jamais fait, la branche « (non choisi) » du resume etait morte,
        # et le garde-fou qui refuse de composer sans axe etait inatteignable.
        # Ce que cela coute : un choix explicite, meme quand le projet n'a
        # qu'une seule couche ligne.
        #   setAllowEmptyLayer NE SUFFIT PAS : il AJOUTE l'entree vide sans la
        #   selectionner, et le combo reste sur la premiere couche ligne du
        #   projet. Mesure : sans setLayer(None), currentLayer() rend encore
        #   « Lignes d'injection (HEC-RAS) ». Le setLayer(None) tient quand des
        #   couches arrivent ENSUITE — c'est le cas reel, la fenetre s'ouvre
        #   avant que « Charger les couches du modele » n'en ajoute deux.
        self.combo_axe.setAllowEmptyLayer(True, "— choisir la couche —")
        self.combo_axe.setLayer(None)
        self.champ_axe = QgsFieldComboBox()
        self.champ_axe.setAccessibleName("Champ contenant le nom de l'axe")
        self.champ_axe.setLayer(self.combo_axe.currentLayer())
        self.combo_axe.layerChanged.connect(self.champ_axe.setLayer)
        self.combo_axe.layerChanged.connect(self._maj_resume)
        f.addRow("Couche de l'axe :", self.combo_axe)
        f.addRow("Champ du nom de l'axe :", self.champ_axe)

        self.combo_sens_axe = QComboBox()
        self.combo_sens_axe.setAccessibleName("Sens de dessin de l'axe")
        # DES MOTS A L'ECRAN, LE CODE EN DONNEE (23/10/2026) : « amont_aval »
        # s'affichait tel que le paquet l'ecrit.
        self.combo_sens_axe.addItem("De l'amont vers l'aval", "amont_aval")
        self.combo_sens_axe.addItem("De l'aval vers l'amont", "aval_amont")
        self.combo_sens_axe.setToolTip(
            "Sens dans lequel la polyligne de l'axe a été dessinée : dans le "
            "sens de l'écoulement (de l'amont vers l'aval) ou à rebours. "
            "Les PK croissent de l'amont vers l'aval.")
        f.addRow("Sens du tracé :",
                 self._avec_temoin(self.combo_sens_axe, "Sens_axe"))

        self.spin_pk_origine = QDoubleSpinBox()
        self.spin_pk_origine.setAccessibleName("PK d'origine, en mètres")
        self.spin_pk_origine.setRange(-1_000_000, 1_000_000)
        self.spin_pk_origine.setDecimals(1)
        self.spin_pk_origine.setSuffix(" m")
        f.addRow("PK d'origine :",
                 self._avec_temoin(self.spin_pk_origine, "PK_origine_m"))
        # LE SENS ET LE PK D'ORIGINE PARTENT AU PAQUET A LA COMPOSITION : les
        # changer ensuite doit allumer leur « ! », donc reveiller la
        # comparaison, comme les autres reglages composes.
        self.combo_sens_axe.currentIndexChanged.connect(self._maj_resume)
        self.spin_pk_origine.valueChanged.connect(self._maj_resume)
        return groupe_axe

    def _groupe_precision(self):
        groupe_param = QGroupBox("Précision du calage")
        f2 = formulaire(groupe_param)
        # La PRECISION ATTENDUE se saisit, en pourcentage : c'est ce que
        # l'hydraulicien juge, et cela depend de l'etude. La forme, elle, n'est
        # pas exposee — elle ne se negocie pas de la meme facon, et un
        # troisieme reglage a l'ecran donnerait a croire qu'on peut rendre un
        # calage conforme en abaissant les trois barres.
        # DEUX POURCENTAGES DE SENS CONTRAIRE, DANS LE MEME CADRE. Le rappel
        # annonçait « tout est rapporte en pourcentage d'atteinte de la
        # cible » — ou 100 % est le juste — et les deux champs sous lui
        # attendent un ECART ADMIS, ou 5 % est le juste. Un « 5 % » lu sous
        # cette phrase se comprend comme « on vise 5 % de la cible ».
        # On dit donc les deux sens, et les etiquettes nomment ce qu'elles
        # demandent au lieu de repeter le mot « precision ».
        rappel = QLabel(
            "Le volume, la pointe et la forme doivent être conformes ensemble. "
            "Saisissez les <b>écarts admis à la cible</b> : une tolérance de "
            "5 % autorise une atteinte comprise entre 95 et 105 %.")
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
        f2.addRow("Écart de &volume admis :", self._avec_temoin(
            self.spin_tol_volume, "Tolerance_volume_pct"))

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
        f2.addRow("Écart de &pointe admis :", self._avec_temoin(
            self.spin_tol_pic, "Tolerance_pic_pct"))
        f2.addRow(texte_aide(
            "Les résultats expriment l’atteinte de la cible : 100 % correspond "
            "à la cible exacte. Le critère de forme n’est pas réglable ici."))

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
        f2.addRow(QLabel("<b>Qualité du calcul HEC-RAS</b>"))
        f2.addRow("Erreur de &bilan de masse admise :",
                  self._avec_temoin(self.spin_bilan_masse,
                                    "Bilan_masse_max_pct"))
        f2.addRow(texte_aide(
            "Au-delà de ce seuil, l’essai est rejeté avant comparaison à la "
            "cible. Vérifiez le pas de calcul avant d’augmenter cette limite."))

        self.spin_nb_max_essais = QSpinBox()
        self.spin_nb_max_essais.setRange(3, 50)
        self.spin_nb_max_essais.setValue(6)
        self.spin_nb_max_essais.setToolTip(
            "Garde-fou de dernier recours, non le mode d'arrêt normal : la "
            "concordance s'obtient en trois à quatre essais.")
        f2.addRow("Maximum d’&essais par apport :", self._avec_temoin(
            self.spin_nb_max_essais, "Nb_max_iterations_par_apport"))
        # LES QUATRE REGLAGES DE PRECISION N'ETAIENT RELIES A RIEN : les
        # changer apres une composition laissait l'ecran et le paquet dire
        # deux choses differentes, en silence. Ils reveillent desormais le
        # controle de coherence, comme le prefixe et les dossiers.
        for _spin in (self.spin_tol_volume, self.spin_tol_pic,
                      self.spin_bilan_masse, self.spin_nb_max_essais):
            _spin.valueChanged.connect(self._maj_resume)

        # L'HYPOTHESE SUR LA PENTE etait dite ici ; elle est desormais dite a
        # l'onglet 4, dans le groupe « Classeur » — c'est la qu'on ouvre le
        # fichier ou elle se lit et se corrige, et une consigne loin de son
        # objet ne se suit pas.
        return groupe_param

    def _champ_prefixe_scenario(self):
        """
        LE PREFIXE, DANS LE GROUPE DU FICHIER QU'IL NOMME (21/09/2026,
        demande utilisateur).

        Il a beaucoup voyage : onglet 4 a cote de « Premier apport », puis
        onglet 3 en 0.8.4 quand il s'est mis a nommer le fichier lui-meme,
        puis au-dessus du bouton de lancement en 0.9.0 parce qu'il nomme
        aussi les plans. Il se pose ici, DANS le groupe du classeur : c'est
        la premiere chose a renseigner pour qu'il y ait un classeur, et le
        nom du fichier se lit deux lignes plus bas.

        CE N'EST PLUS UN GROUPE, mais un simple formulaire : deux cadres
        imbriques pour un champ auraient pese plus que le champ.

        LA RAISON DE L'AVOIR TENU DEHORS N'EN EST PLUS UNE. Le commentaire
        de la 0.8.4 disait « le groupe voisin se grise, un champ
        obligatoire dans un bloc desactive serait une impasse ». Verifie le
        21/09/2026 : _maj_groupe_classeur ne desactive QUE trois enfants —
        le bouton d'ouverture, la consigne et l'aide sur la pente — et
        JAMAIS le groupe. Le champ reste donc actif ici.
        """
        enveloppe = QWidget()
        enveloppe.setToolTip(
            "Nomme les plans HEC-RAS de ce calage, et le fichier Excel des "
            "hydrogrammes cibles.")
        f = formulaire(enveloppe)
        self.edit_prefixe_scenario = QLineEdit()
        # LE COURS D'EAU D'ABORD, PUIS LA CRUE (23/10/2026, demande
        # utilisateur : « propose plutot "Cours-d'eau - Q100 - ..." sinon il
        # y aura des doublons quand plusieurs cours d'eau »). « Q100 » seul
        # donnait les memes plans, le meme Excel et le meme dossier a deux
        # cours d'eau cales pour la meme crue dans un modele.
        self.edit_prefixe_scenario.setPlaceholderText(
            "Cours-d'eau-Q100 (obligatoire)")
        self.edit_prefixe_scenario.setToolTip(
            "Préfixe posé devant le titre de chaque plan créé par le "
            "calage : « Riviere-Q100 » donne « Riviere-Q100-sans », "
            "« Riviere-Q100-A1 » et, à l'arrivée, le plan final "
            "« Riviere-Q100 ».\n\n"
            "OBLIGATOIRE, et c'est pour cela : sans lui, le calage du Q10 "
            "REMPLACERAIT les plans du Q100, qui porteraient exactement les "
            "mêmes titres. Le cours d'eau en tête fait de même pour deux "
            "cours d'eau d'un même modèle.\n\n"
            "Il nomme aussi le fichier Excel des objectifs et le dossier de "
            "sortie proposé : deux scénarios ont donc deux classeurs, et "
            "composer l'un n'écrase pas l'autre.\n\n"
            "Le séparateur « - » est ajouté tout seul : « Riviere-Q100 » et "
            "« Riviere-Q100- » donnent le même titre.\n\n"
            "Titre complet limité à 32 caractères — la borne de "
            "ras-commander, qui refuse au-delà sur « Plan Title » et "
            "« Flow Title ». Au-delà, la composition REFUSE plutôt que de "
            "tronquer : deux plans tronqués au même identifiant "
            "partageraient le dossier de résultats que RAS Mapper nomme "
            "d'après le « Short Identifier ». La ligne sous le champ compte "
            "les caractères à la frappe.")
        # « OBLIGATOIRE » DANS LE LIBELLE, PAS SEULEMENT DANS LE PLACEHOLDER
        # (0.8.5) : un placeholder disparait a la premiere frappe.
        f.addRow("&Préfixe de scénario (obligatoire) :", self._avec_temoin(
            self.edit_prefixe_scenario, "Prefixe_scenario"))
        # LE RECAPITULATIF NOMME LES PLANS AVEC CE PREFIXE : il le suit a la
        # frappe, sinon il annoncerait des titres que le calage ne creera pas.
        # LE DOSSIER PROPOSE D'ABORD : les slots partent dans l'ordre de leur
        # connexion, et _maj_resume juge les prealables de la composition.
        self.edit_prefixe_scenario.textChanged.connect(
            self._proposer_dossier_sortie)
        self.edit_prefixe_scenario.textChanged.connect(self._dire_reprise)
        self.edit_prefixe_scenario.textChanged.connect(self._maj_resume)
        self.label_titres_prefixe = texte_aide("")
        self.label_titres_prefixe.setObjectName("titresPrefixe")
        self.label_titres_prefixe.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        f.addRow(self.label_titres_prefixe)
        self._dire_titres_prefixe()
        return enveloppe

    def _noms_injections(self):
        """Noms des injections de la couche chargée, dans l'ordre de la couche."""
        couche = couche_vivante(getattr(self, "couche_injections", None))
        if couche is None or "nom" not in couche.fields().names():
            return []
        return [str(e["nom"]) for e in couche.getFeatures()
                if e["nom"] not in (None, "") and str(e["nom"]) != "NULL"]

    def _dire_titres_prefixe(self, *_):
        """
        LES TITRES QUE LE PREFIXE DONNERA, SOUS LE CHAMP, A LA FRAPPE
        (23/10/2026). La borne de 32 caracteres n'etait jugee qu'a la
        composition, apres l'ecriture dans la geometrie. Le controle du
        classeur reste l'arbitre (controle_donnees) : ici, on previent.

        Les apports viennent de la couche des injections chargee : avant
        qu'elle le soit, seuls les titres fixes se comptent, et la ligne le
        dit. Tous les titres de reprise sont comptes, comme le controle du
        classeur, a ceci pres que l'ordre de la couche n'est pas celui du
        calage : le titre de reprise du premier apport, jamais construit,
        peut faire prevenir a tort d'un caractere ou deux.
        """
        label = getattr(self, "label_titres_prefixe", None)
        if label is None:
            return
        prefixe = self.edit_prefixe_scenario.text().strip()
        if not prefixe:
            label.setText(
                "Commencez par le cours d’eau, puis la crue : « Riviere-Q100 ». "
                "Deux cours d’eau calés pour la même crue dans un modèle "
                "partageraient sinon leurs plans, leur Excel et leur dossier "
                "de sortie.")
            return
        noms = self._noms_injections()
        etapes = (["sans_apport"] + [f"Apport_{a}" for a in noms or ["A1"]]
                  + ["avec_apports"] + [f"sans {a} et aval" for a in noms])
        titres = [self._titre_etape(nom) for nom in etapes]
        long_ = max(titres, key=len)
        exemple = "« " + " », « ".join(html.escape(t) for t in titres[:2]) + " »"
        exemple += (("…" if len(noms) > 1 else "")
                    + f", « {html.escape(self._titre_etape('avec_apports'))} »")
        phrases = [f"Plans : {exemple}.",
                   f"Excel : {html.escape(noyau.nom_classeur(prefixe))}."]
        trop = len(long_) - LONGUEUR_MAX_TITRE
        if trop > 0:
            phrases.insert(0, (
                f"<b style='color:{ISL_ROUGE}'>⚠ Trop long :</b> "
                f"« {html.escape(long_)} » compte {len(long_)} caractères pour "
                f"{LONGUEUR_MAX_TITRE} (borne de ras-commander). Raccourcissez "
                f"le préfixe de {trop} caractère{'s' if trop > 1 else ''}."))
        else:
            phrases.append(f"Titre le plus long : {len(long_)} caractères sur "
                           f"{LONGUEUR_MAX_TITRE}"
                           + ("" if noms else " (sans les noms des apports : "
                              "chargez les couches du modèle pour les compter)")
                           + ".")
        if not prefixe.isascii():
            phrases.append(
                "<b>⚠ Accents :</b> HEC-RAS les "
                "remplace par « ? » dans le titre des résultats qu’il "
                "calcule. Écrivez le préfixe sans accent.")
        source, autres = self._plans_au_titre_final(self.info_projet)
        if source:
            phrases.insert(0, (
                f"<b style='color:{ISL_ROUGE}'>⚠ Nom déjà pris :</b> le plan de "
                f"référence p{source} s’appelle déjà « {html.escape(prefixe)} », "
                "le titre du plan final. Le lancement sera refusé : "
                "choisissez un autre préfixe."))
        elif autres:
            phrases.append(
                f"<b>⚠ Nom déjà pris :</b> le plan p{', p'.join(autres)} sera "
                "remplacé à la fin du calage. Le lancement le redemandera.")
        label.setText("<br>".join(phrases))

    def _plans_au_titre_final(self, info_projet):
        """
        Plans dont le titre est celui du plan final : (numero du plan de
        reference s'il en fait partie, sinon None ; numeros des autres).
        """
        final = self._titre_etape("avec_apports").strip()
        reference = (self.combo_plan.currentData() or {}).get("numero")
        numeros = [p["numero"] for p in (info_projet or {}).get("plans", [])
                   if p["titre"].strip() == final]
        return (reference if reference in numeros else None,
                [n for n in numeros if n != reference])

    def _groupe_classeur(self):
        # « EXCEL DES HYDROGRAMMES OBJECTIFS », ET NON « CLASSEUR ». Le mot
        # « classeur » est celui du CODE et de la chaine, ou il designe un
        # format ; a l'ecran il ne dit ni ce que le fichier contient, ni a
        # quoi il sert. L'utilisateur, lui, y vient pour une chose : saisir
        # les hydrogrammes qu'il vise. Le nom le dit maintenant.
        # « HYDROGRAMMES CIBLES » (21/09/2026, demande utilisateur). Le nom
        # disait le CONTENANT — « Excel des hydrogrammes objectifs » — la ou
        # l'utilisateur vient pour son CONTENU. Le fichier est nomme deux
        # lignes plus bas, par le champ qui le nomme pour de bon.
        groupe_actions = QGroupBox("Hydrogrammes cibles")
        v_classeur = QVBoxLayout(groupe_actions)
        v_classeur.setSpacing(8)
        # LE PREFIXE EN PREMIER : sans lui, il n'y a pas de classeur a
        # ouvrir, et c'est lui qui le nomme.
        v_classeur.addWidget(self._champ_prefixe_scenario())
        # LE BOUTON SOUS LE PREFIXE (22/09/2026, demande utilisateur) : UN
        # SEUL geste — ecrire la geometrie, composer le classeur, controler —
        # avec son compte rendu. La composition automatique (0.9.5) renonce
        # EN SILENCE quand un prealable manque : « Ouvrir dans Excel »
        # restait gris apres le prefixe, et rien ne disait pourquoi. Le
        # bouton, lui, nomme ce qui manque — gris tant que c'est le cas, vert
        # sinon (_maj_bouton_controle) — et son compte rendu dit ce qui a ete
        # ecrit, compose et controle.
        ligne_valider = QHBoxLayout()
        self.bouton_controle = self._bouton_controle_parametrage()
        ligne_valider.addWidget(self.bouton_controle)
        ligne_valider.addStretch(1)
        v_classeur.addLayout(ligne_valider)
        self.consigne_classeur = QLabel(
            "Dans la feuille <b>Cibles</b>, saisissez un hydrogramme par "
            "section, puis enregistrez l’Excel : ce qu’elles portent se relit "
            "plus bas au retour dans QGIS.")
        self.consigne_classeur.setWordWrap(True)
        v_classeur.addWidget(self.consigne_classeur)
        # EMPILES DE NOUVEAU (24/09/2026). La 0.8.4 les avait mis cote a cote
        # avec des libelles raccourcis ; le libelle d'import demande par
        # l'utilisateur ne tient plus sur la ligne d'« Ouvrir dans Excel » a
        # 13 pt — une rangee de boutons ne se replie pas, elle deborde.
        ligne_classeur = QVBoxLayout()
        ligne_classeur.setSpacing(6)
        self.bouton_ouvrir_classeur = QPushButton("Ouvrir dans &Excel")
        self.bouton_ouvrir_classeur.setToolTip(
            "Ouvre l'Excel des hydrogrammes objectifs. C'est dans sa feuille "
            "Cibles que se saisissent les hydrogrammes, une colonne par "
            "section.")
        self.bouton_ouvrir_classeur.clicked.connect(self._ouvrir_classeur)
        # Deux lignes : sur une, 625 px a 13 pt, l'etape defilait de cote.
        self.bouton_importer = QPushButton(
            "&Importer des hydrogrammes\nd'un calcul précédent…")
        self.bouton_importer.setAccessibleName(
            "Importer des hydrogrammes d'un calcul précédent")
        self.bouton_importer.setToolTip(
            "Recopie dans l'Excel de ce calcul, depuis l'Excel d'un calcul "
            "précédent, les hydrogrammes des sections de même nom (feuille "
            "Cibles) et les pentes des apports de même nom. Rien d'autre ne "
            "change : paramètres, modèle et dossier de sortie restent ceux "
            "de ce calcul.")
        self.bouton_importer.clicked.connect(self._importer_hydrogrammes)
        for _b in (self.bouton_ouvrir_classeur, self.bouton_importer):
            _b.setSizePolicy(QSizePolicy.Policy.Maximum,
                             QSizePolicy.Policy.Fixed)
            ligne_classeur.addWidget(_b, 0, Qt.AlignmentFlag.AlignLeft)
        v_classeur.addLayout(ligne_classeur)
        # LE COMPTE RENDU DE L'IMPORT, DANS LA PAGE, SOUS SON BOUTON : on le
        # relit en complétant l'Excel.
        self.label_import = texte_etat()
        v_classeur.addWidget(self.label_import)

        # HYPOTHESE SUR LA PENTE, dite a cote du bouton qui ouvre le fichier
        # ou elle se corrige. Elle est desormais PRE-REMPLIE a la composition,
        # d'ou « à ajuster si besoin » : ce n'est plus une case vide a
        # comprendre, c'est une valeur proposee qu'on peut refuser.
        # GROUPE REPLIABLE NATIF (0.8.2) plutot qu'un bouton a bascule : meme
        # aspect que les proprietes de couche QGIS, et l'etat replie est
        # MEMORISE par QGIS d'une session a l'autre (QgsSettings, cle formee
        # des objectName du groupe et de ses parents — d'ou le nom pose).
        self.groupe_pente = QgsCollapsibleGroupBox("Hypothèse de pente des apports")
        self.groupe_pente.setObjectName("grpPente")
        self.groupe_pente.setToolTip("Le calcul de la pente proposée et les cas où l’ajuster.")
        detail_pente = texte_aide(
            "<b>Pente des apports</b> — colonne « Pente_m_par_m », feuille "
            "Correspondance. <b>Pré-remplie</b> à la composition : pente "
            "moyenne du fond sur ±200 m autour de l'injection, majorée de "
            "20 %. À ajuster si besoin — une valeur saisie n'est jamais "
            "écrasée par une recomposition.<br><br>"
            "HEC-RAS s'en sert pour répartir le débit entre les mailles que "
            "la ligne recoupe. Une pente sous-estimée concentre l'injection "
            "au lieu de l'étaler : la majoration va dans le sens de la "
            "prudence. Elle dépend du tronçon, d'où la saisie par apport.<br><br>"
            "Laissée vide — profil trop court ou géométrie non prétraitée — "
            "le calage la déduit lui-même, comme avant.")
        QVBoxLayout(self.groupe_pente).addWidget(detail_pente)
        self.groupe_pente.setCollapsed(True)
        v_classeur.addWidget(self.groupe_pente)
        self._maj_groupe_classeur()
        return groupe_actions

    @property
    def classeur(self):
        """Chemin de l'Excel des objectifs ; None tant que rien n'est compose."""
        return self._classeur

    @classeur.setter
    def classeur(self, chemin):
        # LE GROUPE « Excel des hydrogrammes objectifs » SUIT CET ETAT, ET
        # L'APPREND ICI. Deux endroits l'affectent — construction et
        # composition — et le rafraichir a chacun, c'est en oublier
        # un tot ou tard. A la construction l'onglet 3 n'existe pas encore :
        # il se peint lui-meme en naissant (_groupe_classeur).
        self._classeur = chemin
        # CE QUE L'ECRAN TENAIT QUAND LE PAQUET EST ARRIVE, a la composition.
        # Un champ n'est perime que s'il a bouge depuis : voir
        # _ecarts_avec_le_paquet.
        try:
            self._valeurs_au_paquet = self._valeurs_de_la_fenetre()
        except (AttributeError, RuntimeError):
            self._valeurs_au_paquet = {}    # fenetre pas encore construite
        if hasattr(self, "bouton_ouvrir_classeur"):
            self._maj_groupe_classeur()

    def _maj_groupe_classeur(self):
        """
        Grise ce qui n'a pas d'objet tant qu'aucun Excel n'existe (0.8.4,
        demande utilisateur) ; la ligne d'attente, posee a la construction,
        dit pourquoi et quoi faire.

        L'IMPORT SE GRISE AUSSI (24/09/2026) : il ecrit DANS l'Excel de ce
        calcul, qui n'existe pas encore. Le groupe entier n'est pas desactive
        pour autant — le prefixe et le bouton de composition y vivent.
        """
        pret = bool(self.classeur)
        for widget in (self.bouton_ouvrir_classeur, self.bouton_importer,
                       self.consigne_classeur, self.groupe_pente):
            widget.setEnabled(pret)
        self.label_classeur_attente.setVisible(not pret)

    # --- Onglet 3 : Objectifs et precision -----------------------------------

    def _onglet_objectifs(self):
        """
        CE QU'ON VISE, ET AVEC QUOI. La precision attendue et le classeur ou
        se saisissent les hydrogrammes cibles : deux faces d'une meme
        decision, qui vivaient dans deux onglets differents — la precision au
        « 2. Profil en long », le classeur au « 4. Lancer ».
        """
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)



        # LE CONTROLE EST REDESCENDU AU BAS DE LA FENETRE (0.7.24, demande
        # utilisateur), a cote de « Fermer », ou il vivait avant la 0.7.19.
        # Voir _bouton_controle_parametrage : quatre demenagements en cinq
        # versions ont fini par montrer que ce geste n'appartient a AUCUN
        # onglet — il consomme les trois premiers et prepare le quatrieme.
        # L'ORDRE EST CELUI DU PARCOURS (20/09/2026, demande utilisateur) :
        # ce qu'on vise, le geste qui ouvre la saisie, puis la saisie et sa
        # verification. Le classeur venait en premier alors qu'il n'existe
        # pas encore : la page s'ouvrait sur un groupe grise.
        v.addWidget(self._groupe_precision())
        # LE GESTE QUI DEBLOQUE LA SAISIE, HORS DU GROUPE QU'IL DEBLOQUE.
        # Cette ligne vivait DANS « Excel des hydrogrammes objectifs » : elle
        # expliquait, depuis l'interieur d'un groupe grise, comment le
        # degriser. Posee entre les deux, elle est l'etape qu'elle decrit.
        self.label_classeur_attente = texte_aide(
            "Aucun Excel pour l’instant : il naît de "
            f"« {BOUTON_GEOMETRIE} », sous le <b>préfixe de scénario</b> "
            "ci-dessous — le bouton est gris "
            "tant qu’il manque quelque chose, et son infobulle le nomme. Le "
            "dossier de sortie se propose tout seul (« _calage\\&lt;préfixe&gt; » "
            "à côté du modèle, modifiable juste au-dessus). Les hydrogrammes "
            "d’un calcul précédent s’importent ensuite dans cet Excel.")
        # LE DOSSIER DE SORTIE JUSTE AU-DESSUS DU CLASSEUR (22/09/2026,
        # demande utilisateur) : « comme ca on sait ou mettre l'Excel ». Il
        # vivait a l'etape Lancer depuis la 0.9.0 — « une decision du
        # lancement » —, mais c'est ici que le fichier qu'il abrite se nomme
        # et se cree.
        v.addWidget(self._groupe_dossier_sortie())
        v.addWidget(self.label_classeur_attente)
        v.addWidget(self._groupe_classeur())
        v.addWidget(self._groupe_ce_que_portent_les_cibles())
        v.addStretch(1)
        return page

    # « COMPOSER LE PAQUET » N'EST PLUS UN GESTE (21/09/2026) : il se fait
    # tout seul. Ce qui manque ici n'est pas une action, c'est un fichier.
    # Un renvoi, pas la consigne : celle du dessus, visible dans le meme cas,
    # la porte deja (deux fois la meme phrase a l'ecran, 23/10/2026).
    _ATTENTE_CIBLES = (
        f"<i style='color:{ISL_ARDOISE}'>Les hydrogrammes saisis dans la "
        f"feuille Cibles de l’Excel se liront ici, chiffrés. L’Excel naît "
        f"sous le préfixe de scénario, plus haut.</i>")

    def _groupe_ce_que_portent_les_cibles(self):
        """
        CE QU'ON VIENT DE COLLER DANS L'EXCEL, RELU ET CHIFFRE (0.7.24,
        demande utilisateur).

        La feuille Cibles est une nappe de nombres : douze colonnes, plusieurs
        centaines de lignes. Rien n'y dit l'ordre de grandeur, et rien n'y
        distingue une colonne collee dans la mauvaise section d'une colonne
        juste. Un pic et un volume par apport se lisent d'un coup d'oeil, et
        trois fautes ordinaires s'y voient AVANT les heures de calcul :
          - une cible collee sous le mauvais nom — les pics ne croissent plus
            vers l'aval, alors qu'ils le font sur tout reseau qui converge ;
          - un facteur d'unite — un pic a 89 m3/s ou a 89 000 l/s ne se
            confondent pas quand ils sont ecrits ;
          - une colonne restee vide, dite ici « à saisir » et non par un
            silence.

        C'EST UNE LECTURE, JAMAIS UN VERDICT. Aucun seuil ne s'y applique et
        rien n'y bloque : le controle des cibles, lui, vit dans
        controle_donnees.py et parle au moment de composer. Ce tableau ne fait
        que MONTRER, et c'est l'oeil de l'hydraulicien qui juge.

        L'HEURE DU PIC Y EST, et ce n'est pas un ornement : c'est elle qui
        porte le decalage entre l'apport et sa section. Deux cibles voisines
        dont les pics sont dans le desordre annoncent un Dt qui n'est pas un
        temps de transfert — le defaut du 08/09/2026 (voir criteres,
        decalage_fenetre_h) est ne de la, et il a coute sept heures.
        """
        groupe = QGroupBox("Ce que portent les hydrogrammes cibles")
        groupe.setToolTip(
            "Relu dans la feuille Cibles à chaque composition, à chaque "
            "import d'hydrogrammes, et dès que le classeur a changé sur disque "
            "— au retour dans QGIS ou au changement d'étape. Le volume est "
            "intégré sur la colonne "
            "Temps_h, à la règle des trapèzes.")
        v = QVBoxLayout(groupe)
        v.setSpacing(6)
        self.label_resume_cibles = QLabel()
        self.label_resume_cibles.setTextFormat(Qt.TextFormat.RichText)
        self.label_resume_cibles.setWordWrap(True)
        self.label_resume_cibles.setText(self._ATTENTE_CIBLES)
        # UN TABLEAU HTML NE SE REPLIE PAS (0.8.2). Ses quatre colonnes
        # imposaient leur largeur au cadre, donc a TOUTE LA PAGE : a 13 pt
        # dans une fenetre de 800 px, l'onglet 3 debordait de 37 px et le
        # dernier champ sortait de la vue (mesure du banc, 11/09/2026). Le
        # defaut existait des la 0.8.0 ; il ne se voyait qu'avec des cibles
        # LUES, c'est-a-dire jamais a l'ouverture.
        #
        # Le tableau defile donc horizontalement DANS son cadre — dernier
        # recours admis pour un tableau, jamais pour un formulaire (guide
        # Qt, § 2) —, et la page ne deborde plus. QScrollArea a une largeur
        # minimale a elle, independante de son contenu : c'est ce qui coupe
        # la propagation.
        self.zone_resume_cibles = QScrollArea()
        self.zone_resume_cibles.setObjectName("zoneResumeCibles")
        self.zone_resume_cibles.setWidgetResizable(True)
        self.zone_resume_cibles.setFrameShape(QFrame.Shape.NoFrame)
        self.zone_resume_cibles.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.zone_resume_cibles.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.zone_resume_cibles.setWidget(self.label_resume_cibles)
        v.addWidget(self.zone_resume_cibles)
        return groupe

    def _maj_resume_cibles(self):
        """
        Remplit le tableau ci-dessus depuis le classeur courant.

        MUET PLUTOT QUE FAUX : si le classeur ne se lit pas, on le DIT et on
        n'efface pas le tableau precedent en silence — meme conduite que les
        deux etiquettes de l'onglet 4, ou un affichage laisse sur le classeur
        precedent avait deja menti (voir _maj_onglet_validation_depuis_classeur).
        """
        label = getattr(self, "label_resume_cibles", None)
        if label is None:
            return
        if not self.classeur:
            label.setText(self._ATTENTE_CIBLES)
            return
        self._classeur_lu = _cle_fichier(self.classeur)
        try:
            resume = noyau.resume_cibles(self.classeur)
        except Exception as e:
            journaliser("Résumé des hydrogrammes cibles", e)
            label.setText(f"<span style='color:{ISL_ROUGE}'>Illisible : "
                          f"{e}</span>")
            return
        if not resume:
            label.setText(f"<i style='color:{ISL_ARDOISE}'>Aucun apport dans "
                          f"ce classeur.</i>")
            return

        lignes = [
            f"<tr>"
            f"<th align='left'>Apport → section</th>"
            f"<th align='right'>&nbsp;&nbsp;Pointe (m³/s)</th>"
            f"<th align='right'>&nbsp;&nbsp;Heure du pic (h)</th>"
            f"<th align='right'>&nbsp;&nbsp;Volume (hm³)</th>"
            f"</tr>"]
        for e in resume:
            paire = (f"{e['apport']} → {e['section']}"
                     if e["apport"] != e["section"] else e["section"])
            if e["renseignee"]:
                lignes.append(
                    f"<tr><td>{paire}</td>"
                    f"<td align='right'>{nombre(e['pic_m3s'], 1, milliers=True)}</td>"
                    f"<td align='right'>{nombre(e['heure_pic_h'], 2, milliers=True)}</td>"
                    f"<td align='right'>{nombre(e['volume_hm3'], 3, milliers=True)}</td></tr>")
            else:
                lignes.append(
                    f"<tr><td>{paire}</td>"
                    f"<td align='right' colspan='3'>"
                    f"<i style='color:{ISL_ARDOISE}'>à saisir</i></td></tr>")
        label.setText("<table cellspacing='0' cellpadding='2'>"
                      + "".join(lignes) + "</table>")
        # SA HAUTEUR NE SE NEGOCIE PAS, POUR LA MEME RAISON QUE LE BOUTON DE
        # CONTROLE avant lui : dans une fenetre trop courte, la zone defilante
        # COMPRIME le contenu au lieu de faire apparaitre une barre, et c'est
        # le DERNIER encadre de l'onglet qui encaisse — celui-ci. Un plancher
        # calcule sur le nombre de lignes l'en soustrait.
        hauteur = (len(resume) + 1) * (label.fontMetrics().height() + 4) + 8
        label.setMinimumHeight(hauteur)
        # Le cadre defilant suit : sans cela il garderait sa hauteur par
        # defaut et le tableau s'y trouverait tronque en bas.
        zone = getattr(self, "zone_resume_cibles", None)
        if zone is not None:
            zone.setMinimumHeight(
                hauteur + zone.horizontalScrollBar().sizeHint().height())

    # --- Onglet 2 : Resultats et suivi --------------------------------------

    def _groupe_dossier_sortie(self):
        """Ou le paquet, les resultats et le suivi sont ecrits."""
        groupe = QGroupBox("Dossier de sortie")
        f = formulaire(groupe)
        ligne = QHBoxLayout()
        ligne.setSpacing(6)
        self.edit_dossier_sortie = QLineEdit()
        self.edit_dossier_sortie.setPlaceholderText(
            "Dossier du paquet : shapefiles et Excel des objectifs")
        self.edit_dossier_sortie.setToolTip(
            "Proposé tout seul dès que le modèle et le préfixe sont connus : "
            "« _calage\\<préfixe> » à côté du modèle, un dossier par "
            "scénario. Une valeur saisie ou choisie ici n'est jamais "
            "remplacée.")
        self.edit_dossier_sortie.textChanged.connect(self._maj_resume)
        bouton = QPushButton("Choisir le dossier…")
        bouton.clicked.connect(self._parcourir_dossier_sortie)
        ligne.addWidget(self.edit_dossier_sortie, 1)
        ligne.addWidget(self._temoin("Dossier_sortie"))
        ligne.addWidget(bouton)
        etiquette_dossier = QLabel("&Emplacement :")
        etiquette_dossier.setBuddy(self.edit_dossier_sortie)
        f.addRow(etiquette_dossier, ligne)

        detail_dossiers = QgsCollapsibleGroupBox("Sous-dossiers de sortie")
        detail_dossiers.setObjectName("grpSousDossiers")
        fd = formulaire(detail_dossiers)

        self.edit_sous_dossier_resultats = QLineEdit("resultats_finaux")
        self.edit_sous_dossier_resultats.textChanged.connect(self._maj_resume)
        fd.addRow("Résultats &finaux :", self._avec_temoin(
            self.edit_sous_dossier_resultats, "Sous_dossier_resultats"))

        self.edit_sous_dossier_suivi = QLineEdit("suivi")
        self.edit_sous_dossier_suivi.textChanged.connect(self._maj_resume)
        # CHANGER CE CHAMP DOIT SE VOIR TOUT DE SUITE. Sans ce reveil,
        # l'onglet 5 gardait le dossier de la derniere visite jusqu'a la
        # reouverture de QGIS : on corrigeait le sous-dossier et le suivi
        # continuait de regarder l'ancien, sans rien dire.
        for _champ in (self.edit_dossier_sortie, self.edit_sous_dossier_suivi):
            _champ.textChanged.connect(self._oublier_dossier_suivi)
        fd.addRow("&Suivi du calage :", self._avec_temoin(
            self.edit_sous_dossier_suivi, "Sous_dossier_suivi"))
        fd.addRow(texte_aide(
            "Ces sous-dossiers sont créés dans le dossier de sortie. Le suivi "
            "conserve avancement.md, avancement.png et le classeur d’itérations, "
            "consultables depuis un autre poste."))
        detail_dossiers.setCollapsed(True)
        f.addRow(detail_dossiers)
        f.addRow(texte_aide(
            "Pendant le calcul, consultez l’étape Suivi pour lire l’avancement."))
        return groupe

    def _groupe_menage(self):
        """Ce qu'il advient des plans d'etape apres le calage."""
        # « RELIRE UN HYDROGRAMME DEJA CALCULE » A QUITTE LA FENETRE (0.7.22,
        # demande utilisateur). C'etait un outil de diagnostic — exporter en
        # CSV le debit a une section — dans un onglet qui parle des sorties du
        # calage. Il n'a pas disparu du projet : « pont_hecras.py hydrogramme
        # --plan … --section … » le fait depuis une console, et c'est la sa
        # place. Un onglet n'a pas a porter ce qu'on utilise trois fois l'an.

        # LE MENAGE VIT ICI, PAS A L'ONGLET 1. L'onglet 1 prepare le modele
        # AVANT le calage ; celui-ci parle de ce que le calage a PRODUIT, et
        # l'elagage se decide une fois les livrables en main.
        groupe_menage = QGroupBox("Conservation des plans d’étape")
        fm = formulaire(groupe_menage)
        fm.addRow(texte_aide(
            "Les plans d’étape documentent le calage et permettent sa reprise : "
            "un plan « …-sans », puis un par apport. Par exemple, trente "
            "apports produisent trente et un jeux de résultats intermédiaires."))
        # UNE CASE, PAS UN BOUTON (0.7.22, demande utilisateur). Le bouton
        # elaguait APRES COUP : il fallait y penser une fois le calage fini,
        # et revenir dans la fenetre pour cela. La case se coche AVANT, avec
        # le reste du parametrage, et c'est la CHAINE qui elague en fin de
        # calage — au moment ou le plan final existe, donc ou l'operation est
        # sure.
        # Deux lignes : sur une, 609 px a 13 pt, l'etape Lancer defilait.
        self.case_elaguer = QCheckBox(
            "Supprimer les plans d’étape\naprès un calage réussi")
        self.case_elaguer.setAccessibleName(
            "Supprimer les plans d’étape après un calage réussi")
        self.case_elaguer.setToolTip(
            "Retire les plans d'étape du calage — eux seuls. Le plan de "
            "référence, le plan final au nom du préfixe et tout plan qui "
            "n'est pas de la chaîne restent.\n\n"
            "N'a lieu QUE si le calage aboutit : sans plan final, ses étapes "
            "sont tout ce qu'il en reste, et l'élagage est refusé.\n\n"
            "Oublié ? « pont_hecras.py elaguer-etapes » le fait encore après "
            "coup, depuis une console.")
        self.case_elaguer.toggled.connect(self._dire_elagage)
        fm.addRow(self.case_elaguer)
        # CE QUI VA SE PASSER, EN UNE PHRASE ET EN COULEUR. Une case a cocher
        # dit ce qu'elle FERA ; elle ne dit pas ce qu'il ADVIENDRA des plans,
        # qui est la seule chose qui compte ici — et c'est irreversible.
        self.label_elagage = QLabel()
        self.label_elagage.setWordWrap(True)
        fm.addRow(self.label_elagage)
        self._dire_elagage()
        return groupe_menage

    def _groupe_configuration(self):
        """Tout le parametrage, replie : on l'ouvre pour verifier."""
        groupe_resume = QgsCollapsibleGroupBox("Configuration complète")
        groupe_resume.setObjectName("grpConfiguration")
        v2 = QVBoxLayout(groupe_resume)
        self.texte_resume = QTextEdit()
        self.texte_resume.setObjectName("resume")
        self.texte_resume.setReadOnly(True)
        self.texte_resume.setMinimumHeight(160)
        v2.addWidget(self.texte_resume)
        groupe_resume.setCollapsed(True)
        return groupe_resume

    def _groupe_calcul(self):
        """Le nombre de cœurs que HEC-RAS recevra, propose d'apres le poste."""
        # LE POSTE DECIDE DE LA SUGGESTION, PAS UN DEFAUT FIGE — meme regle
        # que Sensi (core/materiel) : le plugin part sur des dizaines de
        # postes, et « 4 » est faux sur un portable a 2 cœurs P comme sur une
        # station a 16. UNE CASE, PAS UN NOMBRE A SAISIR : la demande est
        # « propose, et si j'accepte, ecris-le ». Decochee, rien n'est ecrit.
        self.poste = materiel.inventaire()
        groupe = QGroupBox("Calcul HEC-RAS")
        fc = formulaire(groupe)
        self.case_coeurs = QCheckBox()
        self.case_coeurs.setToolTip(
            "Cochée, la chaîne demande ce nombre de cœurs à HEC-RAS pour "
            "chaque calcul : ras-commander l'écrit dans les lignes « UNET D1 "
            "Cores », « UNET D2 Cores » et « PS Cores » du plan d'étape, "
            "juste avant de le calculer. Le plan de référence n'est pas "
            "modifié.\n\nDécochée, les plans gardent ce qu'ils demandent "
            "déjà.")
        self.case_coeurs.toggled.connect(self._dire_reprise)
        fc.addRow(self.case_coeurs)
        # UNE SUGGESTION MUETTE PASSERAIT POUR UNE LIMITATION DU PLUGIN. Dire
        # ce qui a ete detecte, ce que le plan demande et ce que cocher
        # changera en fait un renseignement, que l'utilisateur peut contredire.
        self.label_coeurs = texte_aide("")
        fc.addRow(self.label_coeurs)
        self._dire_coeurs()
        return groupe

    def _coeurs_demandes(self):
        """Ce que le lancement ecrira : la suggestion du poste, ou 0 = inchange."""
        case = getattr(self, "case_coeurs", None)
        if case is None or not case.isChecked():
            return 0
        return self.poste.suggestion

    def _dire_coeurs(self):
        """La case et son etiquette suivent le plan choisi a l'etape Modele."""
        if getattr(self, "case_coeurs", None) is None:
            return
        plan = (self.combo_plan.currentData()
                if hasattr(self, "combo_plan") else None)
        n = self.poste.suggestion
        # Deux lignes : sur une, 606 px a 13 pt, l'etape Lancer defilait.
        libelle = (f"Demander {n} cœur{'s' if n > 1 else ''} à HEC-RAS\n"
                   f"pour chaque calcul")
        self.case_coeurs.setText(libelle)
        self.case_coeurs.setAccessibleName(libelle.replace("\n", " "))
        self.label_coeurs.setText(materiel.conseil(
            self.poste, (plan or {}).get("coeurs_2d"),
            f"p{plan['numero']}" if plan else None))

    def _dire_elagage(self):
        """La conservation est un choix normal ; seule la suppression alerte."""
        supprime = self.case_elaguer.isChecked()
        if supprime:
            self.label_elagage.setText(
                f"Plans d’étape <b style='color:{ISL_ROUGE}'>supprimés</b> "
                "uniquement si le calage aboutit. Le plan de référence, le plan "
                "final au nom du préfixe et les plans hors chaîne sont conservés.")
        else:
            self.label_elagage.setText(
                "<b>Plans d’étape conservés.</b> Vous pourrez consulter les résultats "
                "intermédiaires et reprendre une séquence interrompue.")

    def _ecrire_dans_geometrie(self):
        """
        Écrit les sections et injections des couches CHARGÉES (onglet 1,
        « Charger les couches du modèle », dessinées ou complétées
        par-dessus dans QGIS) vers la géométrie HEC-RAS, et donne aux
        injections leur hydrogramme dans le fichier Unsteady Flow.

        Appelée automatiquement en tête de « Écrire, composer et contrôler », jamais
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
            raise ValueError("Choisir d'abord le fichier .prj du projet "
                             "HEC-RAS (« Choisir le projet… »).")
        numero_geom = self._geometrie_effective()
        if not numero_geom:
            raise ValueError("Choisir un plan de référence.")
        zone = self.combo_zone_2d.currentText().strip()
        if not zone:
            raise ValueError(
                "La zone d'écoulement 2D est obligatoire : HEC-RAS y "
                "rattache sections et injections. Cliquer « Charger les "
                "couches du modèle » pour la renseigner.")

        couche_s = couche_vivante(self.couche_sections)
        couche_a = couche_vivante(self.couche_injections)
        if couche_s is None or couche_a is None:
            raise ValueError(
                "Cliquer « Charger les couches du modèle » avant de "
                "composer.")

        dossier = Path(self._dossier_projet())
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
                    f"{compte(reponse['creees'], 'section')} : "
                    f"{', '.join(reponse['noms'][:6])}"
                    + (f" (dont {compte(len(reponse['remplacees']), 'remplacée')})"
                       if reponse.get("remplacees") else ""))
            else:
                reponse = noyau.creer_injections_dans_modele(
                    str(geometrie), chemin_shp, zone, remplacer=True,
                    fichier_unsteady=str(unsteady),
                    pente=PENTE_APPORT_DEFAUT)
                resume.append(
                    f"{compte(reponse['creees'], 'injection')} : "
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
        return message

    def _proposer_dossier_sortie(self, *_):
        """
        Un dossier de sortie PAR DEFAUT des que le modele et le prefixe sont
        connus : « <dossier du modele>\\_calage\\<prefixe> ».

        C'EST CE QUI MANQUAIT POUR QUE L'EXCEL EXISTE DES LA SAISIE DU
        PREFIXE (22/09/2026, demande utilisateur). Le dossier de sortie est
        un prealable de la composition, et
        son champ, vide par defaut, vivait alors a l'etape Lancer, APRES
        l'etape ou l'on saisit le prefixe : vide, il retenait toute
        composition, et l'utilisateur qui venait coller ses hydrogrammes ne
        trouvait pas de classeur. Il est depuis remonte juste au-dessus du
        classeur (etape Parametres) ; la proposition reste utile : un champ
        vide arrete toujours la composition.

        UN DOSSIER PAR SCENARIO, comme sur le calage reel Aran-Q100 : deux
        scenarios dans un meme dossier partageraient « resultats_finaux » et
        « suivi », que rien ne prefixe.

        NE REMPLACE JAMAIS UNE SAISIE : le champ n'est touche que s'il est
        vide ou s'il porte encore la valeur proposee precedente. Une valeur
        tapee ou choisie a la main est celle de l'utilisateur.
        """
        champ = getattr(self, "edit_dossier_sortie", None)
        prefixe_champ = getattr(self, "edit_prefixe_scenario", None)
        if champ is None or prefixe_champ is None:
            return
        dossier = self._dossier_projet()
        # UN NOM DE DOSSIER WINDOWS : ni « <>:"/\|?* », ni espace ou point
        # final, que Windows retire en silence (« Riviere-Q100- » laissait
        # « Riviere-Q100 »). Le reste du prefixe — espaces, apostrophe — y tient.
        prefixe = "".join("_" if c in '<>:"/\\|?*' else c
                          for c in prefixe_champ.text()).strip().rstrip("-_ .")
        if not dossier or not prefixe:
            return
        propose = str(Path(dossier) / "_calage" / prefixe)
        actuel = champ.text().strip()
        if actuel and actuel != getattr(self, "_dossier_sortie_propose", None):
            return
        self._dossier_sortie_propose = propose
        if actuel != propose:
            champ.setText(propose)

    def _parcourir_dossier_sortie(self):
        dossier = QFileDialog.getExistingDirectory(self, "Dossier de sortie")
        if dossier:
            self.edit_dossier_sortie.setText(dossier)

    # --- Onglet 4 : Validation et hydrogrammes cibles -----------------------

    def _onglet_validation(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)

        groupe = QGroupBox("Préparation du lancement")
        f = formulaire(groupe)
        self.label_validation_comptes = QLabel("À composer")
        self.label_validation_comptes.setWordWrap(True)
        f.addRow("Apports appariés :", self.label_validation_comptes)
        self.label_validation_classeur = QLabel("À composer")
        self.label_validation_classeur.setWordWrap(True)
        self.label_validation_classeur.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        # LE MEME FICHIER PORTE LE MEME NOM D'UN ONGLET A L'AUTRE. L'onglet 2
        # l'appelle « Excel des hydrogrammes objectifs » ; le laisser
        # « Classeur » ici donnerait a lire deux fichiers la ou il n'y en a
        # qu'un.
        f.addRow("Excel des objectifs :", self.label_validation_classeur)
        self.label_validation_cibles = QLabel("À renseigner dans l’Excel des objectifs")
        self.label_validation_cibles.setWordWrap(True)
        f.addRow("Hydrogrammes cibles :", self.label_validation_cibles)
        v.addWidget(groupe)

        self.label_prochaine_etape = texte_etat(ATTENTE_PAQUET)
        v.addWidget(self.label_prochaine_etape)


        # LE CHOIX DU PREMIER APPORT PRECEDE LE BOUTON QU'IL REGLE. Il figurait
        # sous lui : on decidait de reprendre a mi-parcours apres avoir lance
        # le calcul depuis le debut. Un reglage se lit avant l'action, jamais
        # apres.
        v.addWidget(self._groupe_copies_de_travail())

        # LE SORT DES PLANS D'ETAPE SE DECIDE ICI, la ou l'on lance
        # (20/09/2026). Le dossier de sortie, lui, est remonte a l'etape
        # Parametres le 22/09/2026, juste au-dessus du classeur qu'il abrite.
        v.addWidget(self._groupe_menage())
        # LES CŒURS SE DECIDENT AU LANCEMENT (22/09/2026, demande utilisateur) :
        # c'est ce clic qui les ecrit dans les plans d'etape.
        v.addWidget(self._groupe_calcul())
        v.addWidget(self._groupe_configuration())

        groupe_lancer = QGroupBox("Lancer le calage")
        vl = QVBoxLayout(groupe_lancer)
        vl.setSpacing(8)
        explication = QLabel(
            "Le calage traite les apports successivement en arrière-plan. "
            "Il peut durer plusieurs heures ; QGIS reste utilisable. "
            "L’étape <b>Suivi</b> affiche automatiquement son avancement.")
        explication.setWordWrap(True)
        vl.addWidget(explication)
        # CE QUE CE CLIC VA FAIRE, EN TOUTES LETTRES. Voir _dire_reprise.
        self.label_reprise = texte_etat()
        self.label_reprise.setObjectName("recapReprise")
        vl.addWidget(self.label_reprise)
        ligne_lancer = QHBoxLayout()
        bouton_lancer = QPushButton("Lancer le calage")
        self.bouton_lancer = bouton_lancer          # cible d'un lien du fil
        bouton_lancer.setObjectName("boutonAccent")
        bouton_lancer.setToolTip(
            "Lance la boucle séquentielle complète dans un processus "
            "détaché. QGIS reste utilisable pendant le calcul ; l'avancement "
            "se lit à l'étape 4 « Suivi », qui se rafraîchit toute seule.")
        bouton_lancer.clicked.connect(self._lancer_calage)
        ligne_lancer.addWidget(bouton_lancer)
        bouton_suivi = QPushButton("Consulter le suivi")
        bouton_suivi.clicked.connect(
            lambda: self.onglets.setCurrentIndex(ONGLET_SUIVI))
        ligne_lancer.addWidget(bouton_suivi)
        ligne_lancer.addStretch(1)
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

        # LE DOSSIER SURVEILLE, EN PERMANENCE. Il n'etait nomme que dans la
        # branche « Aucun calage suivi » : l'information disparaissait
        # precisement pendant les heures ou cet onglet sert. Le manque mord
        # apres une reprise de classeur, apres une retouche des champs de
        # l'onglet 3 en cours de calcul, ou devant deux calages menes de
        # front — soit chaque fois qu'on peut douter d'ou viennent les
        # chiffres qu'on lit.
        self.label_suivi_dossier = texte_aide("")
        self.label_suivi_dossier.setWordWrap(True)
        self.label_suivi_dossier.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.label_suivi_dossier)

        # ERREURS ET AVERTISSEMENTS, SOUS LA BANNIERE (0.8.4, demande
        # utilisateur). Ils ne vivaient que dans le journal de lancement —
        # un fichier .log dont la banniere donnait le CHEMIN. Un chemin
        # n'est pas un message : le 14/09/2026, un calage repris s'est
        # arrete sur un calcul de reference sans resultats, et les douze
        # avertissements de recadencement des cibles qui le precedaient
        # n'ont jamais paru a l'ecran.
        #   REPLIE PAR DEFAUT, ET DEPLIE TOUT SEUL QUAND QUELQUE CHOSE
        # ARRIVE : un encadre vide et ouvert en permanence apprend a ne plus
        # etre lu.
        self.groupe_alertes = QgsCollapsibleGroupBox(
            "Erreurs et avertissements")
        self.groupe_alertes.setObjectName("grpAlertesSuivi")
        self.groupe_alertes.setToolTip(
            "Les lignes du journal de lancement qui portent un arrêt, une "
            "erreur ou un avertissement. Le journal entier est dans le "
            "dossier de l'Excel des objectifs.")
        va_alertes = QVBoxLayout(self.groupe_alertes)
        self.texte_alertes = QTextEdit()
        self.texte_alertes.setReadOnly(True)
        self.texte_alertes.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.texte_alertes.setMinimumHeight(110)
        va_alertes.addWidget(self.texte_alertes)
        self.groupe_alertes.setCollapsed(True)
        self.groupe_alertes.setVisible(False)
        v.addWidget(self.groupe_alertes)

        # LE JOURNAL TEL QU'IL S'ECRIT (20/09/2026, demande utilisateur).
        # L'encadre ci-dessus ne retient que les lignes portant un mot
        # d'alerte ; celui-ci montre le fil, et c'est lui qui dit OU le
        # calage en etait. Voir _peindre_journal.
        self.groupe_journal = QgsCollapsibleGroupBox("Journal en cours")
        self.groupe_journal.setObjectName("grpJournalSuivi")
        self.groupe_journal.setToolTip(
            "Les dernières lignes du journal de lancement, rafraîchies "
            "pendant le calcul. Le fichier entier est dans le dossier de "
            "l'Excel des objectifs.")
        vj = QVBoxLayout(self.groupe_journal)
        self.texte_journal = QTextEdit()
        self.texte_journal.setReadOnly(True)
        self.texte_journal.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.texte_journal.setMinimumHeight(150)
        self.texte_journal.setAccessibleName("Journal du calage en cours")
        # POLICE A CHASSE FIXE : un journal s'aligne. On demande la famille
        # au systeme plutot que d'en nommer une — « Consolas » n'existe pas
        # partout, et QGIS suit la police du poste.
        self.texte_journal.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        vj.addWidget(self.texte_journal)
        self.groupe_journal.setCollapsed(True)
        self.groupe_journal.setVisible(False)
        v.addWidget(self.groupe_journal)

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
        # TRIABLE (27/10/2026, comme Rhoe) : l'ordre du calage, de l'amont
        # vers l'aval, revient au troisieme double-clic.
        self.table_suivi = TableauTriable(0, 6)
        self.table_suivi.setHorizontalHeaderLabels(
            ["Apport", "Section", "Statut", "Essais", "Volume",
             "Pointe"])
        self.table_suivi.horizontalHeader().setToolTip(
            "Double-cliquer sur un en-tête pour classer, une deuxième fois "
            "pour inverser, une troisième pour revenir à l'ordre du calage.")
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
        bouton_figure = QPushButton("Ouvrir la figure d’avancement")
        bouton_figure.setToolTip(
            "La figure produite par la chaîne : état de chaque apport, et "
            "volume et débit de pointe atteints face aux 100 % visés.")
        bouton_figure.clicked.connect(self._ouvrir_figure_suivi)
        ligne.addWidget(bouton_figure)
        ligne.addStretch(1)
        self.label_suivi_maj = QLabel("")
        self.label_suivi_maj.setProperty("role", ROLE_AIDE)
        # Sous la rangee, pas dedans : a 13 pt sur 720 px, a cote de la bande,
        # la rangee faisait defiler l'etape, de 9 px encore avec « Ouvrir la
        # figure d'avancement » et l'heure repliee (23/10/2026).
        self.label_suivi_maj.setWordWrap(True)
        v.addLayout(ligne)
        v.addWidget(self.label_suivi_maj)

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

        ET LA FENETRE ACCUSE CE QU'ON A DESSINE PENDANT SON ABSENCE. C'est le
        geste central de l'outil : on la laisse ouverte, on va tracer les
        sections manquantes dans QGIS, on revient. Rien ne le remarquait — le
        resume continuait d'afficher les comptes d'avant, et l'on n'apprenait
        que son dessin avait ete vu qu'au clic sur « Ecrire, composer et controler ».
        Le changement d'onglet est le seul moment ou l'on sait a coup sur que
        la fenetre reprend la main.
        """
        self._maj_resume()
        self._relire_cibles_si_modifiees()
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
        QTimer.singleShot(0, self._choisir_python_recherche)
        minuteur = getattr(self, "minuteur_suivi", None)
        if minuteur is not None and self.onglets.currentIndex() == ONGLET_SUIVI:
            self._rafraichir_suivi()
            minuteur.start()

    def _dossier_suivi(self):
        """
        Dossier ou le calage ecrit son suivi.

        LE SUIVI SUIT LE CLASSEUR, PAS L'ONGLET 3. C'est le classeur que le
        pont lit pour savoir ou ecrire (Dossier_sortie, Sous_dossier_suivi) ;
        l'onglet 3 ne dit que ou COMPOSER le prochain paquet. Les deux
        divergent des qu'on reprend le classeur d'un calcul precedent
        (onglet 4) : le calage partait dans un dossier, le suivi en
        regardait un autre, et restait muet devant un calcul qui tournait —
        « Aucun calage suivi », 0 %, pendant que le journal avancait
        (03/09/2026 : un second paquet venait d'etre compose ailleurs).

        Le classeur est relu quand il change — chemin ou date —, pas toutes
        les deux secondes : il est le plus souvent sur un partage reseau.
        Sans classeur, l'onglet 3 reste la seule indication.
        """
        classeur = str(self.classeur) if self.classeur else ""
        if classeur:
            try:
                cle = (classeur, os.path.getmtime(classeur))
            except OSError:
                cle = None
            if cle is not None:
                cache = getattr(self, "_suivi_du_classeur", None)
                if cache is None or cache[0] != cle:
                    try:
                        dossier = noyau.dossier_suivi_du_classeur(classeur)
                    except Exception as e:                  # noqa: BLE001
                        journaliser("Dossier de suivi du classeur", e)
                        dossier = None
                    cache = (cle, dossier)
                    self._suivi_du_classeur = cache
                if cache[1] is not None:
                    return cache[1]
        racine = self.edit_dossier_sortie.text().strip()
        if not racine:
            return None
        return (Path(racine)
                / (self.edit_sous_dossier_suivi.text().strip() or "suivi"))

    def _oublier_dossier_suivi(self, *_):
        """
        Le dossier surveille est a recalculer, et l'onglet 5 a redessiner.

        Appele quand les champs de l'onglet 3 changent. Defensif a dessein :
        il peut se declencher pendant la construction de la fenetre, avant que
        l'onglet 5 n'existe.
        """
        self._suivi_du_classeur = None
        if getattr(self, "label_suivi_banniere", None) is None:
            return
        if self.onglets.currentIndex() == ONGLET_SUIVI:
            self._rafraichir_suivi()

    def _origine_dossier_suivi(self):
        """
        D'ou vient le dossier surveille : « classeur » ou « onglet 3 ».

        LE CLASSEUR GAGNE, ET C'EST VOULU (0.6.2) : c'est lui que le calage
        lance a lu, et regarder ailleurs afficherait « aucun calage suivi »
        pendant qu'il tourne. Mais ce choix DEROUTE quand l'onglet 3 en
        designe un autre — on corrige un champ et rien ne bouge. La banniere
        le dit donc, au lieu de laisser deviner.
        """
        if not self.classeur:
            return "étape Paramètres"
        cache = getattr(self, "_suivi_du_classeur", None)
        return ("Excel lancé" if cache and cache[1] is not None
                else "étape Paramètres")

    def _dossier_suivi_de_l_onglet_3(self):
        """Ce que les champs de l'onglet 3 designent, ou None."""
        racine = self.edit_dossier_sortie.text().strip()
        if not racine:
            return None
        return (Path(racine)
                / (self.edit_sous_dossier_suivi.text().strip() or "suivi"))

    def _calage_en_cours(self):
        """
        L'etat du calage qui tourne, ou None. Rend l'ETAT, pas un booleen :
        l'appelant doit pouvoir le nommer.

        NE SERT PAS A GRISER UN BOUTON, et c'est delibere. Cet etat vient d'un
        fichier, souvent pose sur un partage reseau : une lecture manquee
        desarmerait l'action principale de la fenetre sans rien expliquer —
        pire que le mal qu'on repare. Il sert a POSER UNE QUESTION, dont la
        reponse par defaut est « non ».

        « Termine » compte autant que « vivant » : un calage abouti a laisse
        son avancement.json en place, et son PID a pu etre reattribue depuis.
        """
        try:
            dossier = self._dossier_suivi()
            etat = noyau.lire_avancement(dossier) if dossier else None
            if not etat or etat.get("termine"):
                return None
            return etat if noyau.processus_vivant(etat.get("pid")) else None
        except Exception as e:                              # noqa: BLE001
            # Ne jamais empecher l'action a cause du garde-fou lui-meme.
            journaliser("Detection d'un calage en cours", e)
            return None

    def _confirmer_malgre_calage(self, consequence, geste="Continuer"):
        """
        Demande confirmation si un calage tourne. Vrai si l'on peut y aller.
        « geste » nomme le bouton qui passe outre : « Recomposer », « Lancer ».

        POURQUOI UNE QUESTION ET NON UN VERROU : voir _calage_en_cours. Et
        pourquoi une question TOUT COURT : ni la composition ni le lancement
        ne consultaient l'etat du calage, alors que l'onglet 5 le lit toutes
        les deux secondes. Recomposer pendant un calcul reecrit la geometrie
        et le classeur que ce calcul partage ; relancer fait travailler deux
        calages sur les memes plans. Les deux portes se ferment ensemble —
        en fermer une seule ne fait que deplacer l'accident.
        """
        etat = self._calage_en_cours()
        if etat is None:
            return True
        titre = etat.get("titre") or "un calage"
        pid = etat.get("pid", "?")
        return confirmer(
            self, "Un calage est en cours",
            f"« {titre} » tourne encore (processus {pid}).\n\n{consequence}",
            oui=f"{geste} quand même", non="Attendre la fin du calage")

    def _ouvrir_dossier_suivi(self):
        dossier = self._dossier_suivi()
        if dossier is None or not dossier.is_dir():
            self._signaler(
                "Suivi", "Aucun dossier de suivi : renseigner le dossier de "
                f"sortie (étape Paramètres), puis cliquer « {BOUTON_GEOMETRIE} ».",
                Qgis.MessageLevel.Warning)
            return
        os.startfile(str(dossier))  # noqa: S606 (usage Windows assume)

    def _ouvrir_figure_suivi(self):
        dossier = self._dossier_suivi()
        figure = (dossier / "avancement.png") if dossier else None
        if figure is None or not figure.is_file():
            self._signaler("Suivi", "avancement.png n'existe pas encore : il "
                           "est écrit dès le premier essai.")
            return
        os.startfile(str(figure))  # noqa: S606

    def _detail_desaccord_suivi(self, dossier):
        """
        Dit que l'onglet 3 designe un AUTRE dossier, quand c'est le cas.

        C'est la seule facon de rendre comprehensible la regle « le classeur
        gagne » : sans ce mot, on corrige le champ de l'onglet 3, le suivi ne
        bouge pas, et rien n'explique pourquoi.
        """
        if dossier is None or self._origine_dossier_suivi() != "classeur":
            return ""
        autre = self._dossier_suivi_de_l_onglet_3()
        if autre is None or Path(autre) == Path(dossier):
            return ""
        return (f"<br>L'étape Paramètres en désigne un autre — <i>{autre}</i> — "
                f"qui n'est pas surveillé : c'est l'Excel lancé qui fait foi. "
                f"Cliquer « {BOUTON_GEOMETRIE} » pour que les deux s'accordent.")

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
        # LE FILET SUIT LE THEME COMME LE TITRE (0.8.5) : le titre passe par
        # Etiquette, qui remappe ses couleurs en sombre ; le filet, ecrit dans
        # une feuille de style, ne passait par rien.
        filet = couleur_theme(couleur, self.label_suivi_banniere).name()
        self.label_suivi_banniere.setStyleSheet(
            f"background-color: palette(base);"
            f"border-left: 5px solid {filet};"
            f"border-radius: 3px; padding: 12px 16px;")
        self.label_suivi_banniere.setText(
            f"<span style='font-size:13pt; font-weight:bold; color:{couleur}'>"
            f"{glyphe + '  ' if glyphe else ''}{titre}</span>"
            + (f"<br><span style='font-size:9pt; color:{ISL_ARDOISE}'>"
               f"{detail}</span>" if detail else ""))

    # Ce qui fait qu'une ligne du journal merite l'ecran. Volontairement
    # COURT : tout ce qui est ajoute ici rapproche l'encadre du journal
    # entier, que personne ne lit. « Traceback » y figure parce qu'une pile
    # d'appels annonce toujours un arret, et sa premiere ligne suffit a
    # savoir qu'il y en a une.
    MARQUEURS_ALERTE = ("AVERTISSEMENT", "ARRET", "ERREUR", "ECHEC",
                        "Traceback", "Error:")
    # Le journal d'un calage de quatorze heures pese plusieurs mega-octets :
    # ras-commander y reecrit sa banniere a chaque calcul. On n'en lit que la
    # fin, et l'on n'affiche que les dernieres lignes retenues.
    OCTETS_JOURNAL_LUS = 1_000_000
    LIGNES_ALERTE_MAX = 60
    # LE JOURNAL EN COURS EN MONTRE PLUS QUE LES ALERTES, et pour la meme
    # lecture : c'est un fil qu'on remonte pour comprendre ou le calage en
    # etait, non une liste de motifs. Borne quand meme — un QTextEdit de
    # dix mille lignes se repeint a chaque tour du minuteur.
    LIGNES_JOURNAL_MAX = 400

    def _journal_du_calage(self):
        """
        Le journal de lancement le plus recent, ou None.

        CELUI DE LA SESSION D'ABORD — self.journal_lance, pose au lancement.
        A defaut, le plus recent a cote de l'Excel des objectifs, la ou
        noyau.lancer_calage les ecrit et ou noyau.dernier_journal sait les
        retrouver : c'est ce qui permet de lire l'echec d'hier apres avoir
        rouvert QGIS.
        """
        if self.journal_lance and Path(self.journal_lance).exists():
            return Path(self.journal_lance)
        if not self.classeur:
            return None
        try:
            return noyau.dernier_journal(self.classeur)
        except OSError:
            return None

    def _lire_journal(self):
        """
        La queue du journal de lancement : (toutes les lignes, les alertes).

        UNE SEULE LECTURE POUR DEUX VUES — l'encadre des alertes et le
        journal en cours. Les separer en ferait deux, toutes les deux
        secondes, sur un fichier de partage reseau.

        NE LEVE JAMAIS : appelee par le minuteur du suivi, toutes les deux
        secondes, sur un fichier qu'un autre processus est en train d'ecrire.

        ET NE RELIT QUE CE QUI A CHANGE. Un calcul HEC-RAS dure des minutes
        sans qu'une ligne s'ecrive, et le journal est le plus souvent sur un
        partage reseau : relire un mega-octet toutes les deux secondes pour
        n'y rien trouver de neuf, c'est ce que _dossier_suivi evite deja
        pour l'avancement. Meme cle — taille et date —, un stat par tour.
        """
        chemin = self._journal_du_calage()
        if chemin is None:
            return [], []
        try:
            st = os.stat(chemin)
            cle = (str(chemin), st.st_size, st.st_mtime_ns)
            if cle == getattr(self, "_cle_journal_lu", None):
                return self._journal_lu, self._alertes_lues
            debut = max(0, st.st_size - self.OCTETS_JOURNAL_LUS)
            with open(chemin, "rb") as f:
                f.seek(debut)
                brut = f.read().decode("utf-8", "replace")
        except OSError:
            return [], []
        lignes = [ligne.rstrip() for ligne in brut.splitlines()]
        if debut:
            del lignes[:1]      # coupee au milieu par la lecture tronquee
        retenues = [ligne for ligne in lignes
                    if any(m in ligne for m in self.MARQUEURS_ALERTE)]
        self._cle_journal_lu = cle
        self._journal_lu = lignes[-self.LIGNES_JOURNAL_MAX:]
        self._alertes_lues = retenues[-self.LIGNES_ALERTE_MAX:]
        return self._journal_lu, self._alertes_lues

    def _lignes_alerte(self):
        """Les lignes du journal qui portent un arret, une erreur ou un
        avertissement. Liste vide si le journal manque ou ne dit rien."""
        return self._lire_journal()[1]

    def _peindre_journal(self):
        """
        Le journal de lancement tel qu'il s'ecrit, deroulant, dans la page.

        POURQUOI, ALORS QUE L'ENCADRE DES ALERTES EXISTE (20/09/2026, demande
        utilisateur). Celui-ci ne montre que les lignes qui portent un mot
        d'alerte : ce qui echoue SANS l'un de ces mots n'y parait pas, et
        l'on ne voit pas non plus ou le calage en etait quand il s'est
        arrete. La banniere donnait le chemin du .log — un chemin n'est pas
        un message ; c'est deja ce que la 0.8.4 reprochait au diagnostic.

        REPLIE PAR DEFAUT : on ne lit un journal que lorsqu'on le cherche.
        Il ne se deplie JAMAIS tout seul, a la difference des alertes — un
        journal qui s'ouvre a chaque ligne ecrite rendrait la page sautante
        pendant des heures.

        TOUJOURS DEROULE EN BAS, sauf si l'on a fait defiler soi-meme : la
        derniere ligne est celle qu'on vient lire, mais reprendre la main a
        quelqu'un qui remonte dans l'historique serait pire que de ne rien
        montrer.
        """
        lignes, _ = self._lire_journal()
        self.groupe_journal.setVisible(bool(lignes))
        if not lignes:
            self.texte_journal.setPlainText("")
            return
        chemin = self._journal_du_calage()
        self.groupe_journal.setTitle(
            f"Journal en cours ({len(lignes)} dernières lignes"
            + (f" — {Path(chemin).name}" if chemin else "") + ")")
        texte = "\n".join(lignes)
        if texte == self.texte_journal.toPlainText():
            return
        ascenseur = self.texte_journal.verticalScrollBar()
        colle_en_bas = ascenseur.value() >= ascenseur.maximum() - 2
        self.texte_journal.setPlainText(texte)
        if colle_en_bas:
            self.texte_journal.moveCursor(QTextCursor.MoveOperation.End)
            ascenseur.setValue(ascenseur.maximum())

    def _peindre_alertes(self):
        """Remplit l'encadre des alertes, et l'efface du regard s'il est vide."""
        groupe = self.groupe_alertes
        lignes = self._lignes_alerte()
        groupe.setVisible(bool(lignes))
        if not lignes:
            self.texte_alertes.setPlainText("")
            return
        groupe.setTitle(f"Erreurs et avertissements ({len(lignes)})")
        # SEUL UN CONTENU NOUVEAU DEPLIE, et une seule fois : deplier a
        # chaque tour du minuteur empecherait de replier l'encadre.
        texte = "\n".join(lignes)
        if texte != self.texte_alertes.toPlainText():
            self.texte_alertes.setPlainText(texte)
            self.texte_alertes.moveCursor(QTextCursor.MoveOperation.End)
            if not getattr(self, "_alertes_depliees", False):
                self._alertes_depliees = True
                groupe.setCollapsed(False)

    def _rafraichir_suivi(self):
        """
        Relit l'etat et redessine. Ne leve jamais : c'est un affichage
        periodique, et une exception dans un QTimer remonte dans la boucle
        d'evenements de QGIS.
        """
        try:
            self._peindre_suivi()
            # APRES la peinture, et hors de son chemin : un journal illisible
            # ne doit pas emporter l'avancement, qui est ce qu'on vient voir.
            self._peindre_alertes()
            self._peindre_journal()
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

        # L'ETAT LU EST-IL CELUI DU CALAGE QU'ON VIENT DE LANCER ? Apres un
        # relancement, le dossier porte encore l'avancement.json du calage
        # PRECEDENT tant que le nouveau n'a pas ecrit le sien : on peignait
        # « Calage terminé — conforme » ou « Calage interrompu » comme reponse
        # au lancement qui venait d'aboutir.
        #
        # C'EST L'HEURE QUI TRANCHE, PAS LE PID — et il a fallu un vrai calage
        # pour le decouvrir (08/09/2026, Q20 sur poste distant). Le PID rendu
        # par Popen n'est PAS celui qui ecrit l'etat des que l'interpreteur
        # HEC-RAS est un RELAIS : un venv cree depuis le Python de QGIS — ce
        # que le bouton « Installer… » propose lui-meme — a un python.exe de
        # 256 ko qui relance le vrai interpreteur dans un AUTRE processus.
        # Mesure : Popen rend 55160, le processus qui tourne est 23284.
        #   Consequence, vue a l'ecran : le suivi refusait d'afficher le calage
        # EN COURS en le prenant pour celui d'avant, pendant toute sa duree.
        #   L'etat est donc a nous s'il a commence APRES notre lancement. La
        # tolerance d'une seconde couvre l'arrondi de « debut », ecrit a la
        # seconde par suivi.py.
        perime = False
        if self.instant_lance and etat and etat.get("debut"):
            try:
                debut = datetime.fromisoformat(etat["debut"])
                perime = debut < self.instant_lance - timedelta(seconds=1)
            except ValueError:
                # Un « debut » illisible ne doit pas masquer un calage qui
                # tourne : on prefere afficher un etat douteux a ne rien
                # afficher pendant des heures.
                perime = False

        # LE DOSSIER SURVEILLE EST NOMME A CHAQUE PASSAGE, avant tout test :
        # la branche « Aucun calage suivi » sort plus bas, et c'est elle qui
        # le disait — donc jamais quand un calage tourne. Voir la construction
        # de ce label.
        # LE CHEMIN PEUT PASSER A LA LIGNE APRES CHAQUE SEPARATEUR (23/10/2026) :
        # un espace sans chasse le permet. Sans lui, Qt ne coupe pas un chemin
        # sans espace et la page Suivi defilait de 69 px a 13 pt sur 720 px.
        # Ce texte n'est pas selectionnable ; l'espace ne gene aucune copie.
        coupable = str(dossier).replace("\\", "\\\u200b").replace("/", "/\u200b")
        dire(self.label_suivi_dossier,
             (f"Dossier surveillé ({self._origine_dossier_suivi()}) : {coupable}"
              + self._detail_desaccord_suivi(dossier)) if dossier
             else "Aucun dossier de suivi désigné.")

        if etat is None or perime:
            # LE DOSSIER SURVEILLE EST NOMME : un suivi muet parce qu'il
            # regardait le mauvais dossier ne se distinguait en rien d'un
            # calage pas encore parti.
            #
            # ET « PAS ENCORE DEMARRE » SE DISTINGUE DE « MORT AU DEMARRAGE ».
            # Cette branche promettait « quelques secondes après le
            # lancement » POUR TOUJOURS, y compris devant un sous-processus
            # mort avant d'avoir rien ecrit — cas des refus precoces, qui
            # rendent la main avant que suivi.py n'ecrive son premier etat. Et
            # le seul document qui dit pourquoi, le journal de lancement, ne
            # se lisait que dans une boite d'information depuis longtemps
            # fermee.
            titre, glyphe, couleur = "Aucun calage suivi", "·", ISL_ARDOISE_CLAIR
            detail = ("Le suivi apparaît ici dès que le calage écrit son "
                      "premier état, quelques secondes après le lancement.")
            if self.pid_lance:
                journal = (f"<br>Journal de lancement : {self.journal_lance}"
                           if self.journal_lance else "")
                # « MORT AU DEMARRAGE » NE SE PRONONCE PLUS SUR LE PID DE
                # POPEN. Avec un interpreteur-relais, ce processus-la rend la
                # main aussitot apres avoir lance le vrai : le suivi annoncait
                # un calage mort alors qu'il demarrait. On ne conclut donc a la
                # mort que si l'on a laisse au calage le temps d'ecrire —
                # DELAI_PREMIER_ETAT_S — et qu'il n'a toujours rien ecrit.
                depuis = ((datetime.now() - self.instant_lance).total_seconds()
                          if self.instant_lance else 0.0)
                mort = (noyau.processus_vivant(self.pid_lance) is False
                        and depuis > DELAI_PREMIER_ETAT_S)
                if mort:
                    titre, glyphe, couleur = (
                        "Calage arrêté sans avoir rien écrit", "✕", ISL_ROUGE)
                    detail = (f"Rien n'a été écrit en "
                              f"{int(depuis)} s : le calage est mort au "
                              f"démarrage." + journal)
                else:
                    detail = (f"Calage lancé (processus {self.pid_lance}) — le "
                              f"suivi apparaît ici dès qu'il écrit son premier "
                              f"état." + journal)
            if perime:
                detail += (f"<br>Le dossier porte encore l'état d'un calage "
                           f"précédent, commencé le {date_lisible(etat.get('debut'))} : il "
                           f"n'est pas affiché, pour ne pas se lire comme "
                           f"celui du calage en cours.")
            # Le dossier surveille n'est plus recopie ici : il vit desormais
            # sous la banniere, a chaque passage.
            self._banniere(couleur, titre, glyphe=glyphe, detail=detail)
            self.barre_suivi.setValue(0)
            self.ruban_apports.actualiser([], None)
            self.courbe_suivi.actualiser(None, None)
            self.label_suivi_position.setText("—")
            self.table_suivi.setRowCount(0)
            for jauge in self.jauges.values():
                jauge.actualiser(None)
            return

        apports = etat.get("apports") or []
        en_cours = etat.get("en_cours")
        # LE CALAGE PRECEDENT RESTE A L'ECRAN, DERRIERE CELUI-CI (demande
        # utilisateur, 13/09/2026). Relancer remettait l'onglet a zero :
        # les apports deja cales disparaissaient du ruban et du tableau,
        # leurs hydrogrammes du trace, et rien ne disait qu'ils avaient
        # existe. C'est le plus visible sur une REPRISE, ou le calage en
        # cours ne porte volontairement que les apports restants.
        #   ON NE GARDE QUE CE QUE CE CALAGE NE TRAITE PAS : un apport
        # present dans les deux est celui qu'on refait, et c'est l'etat
        # COURANT qui fait foi pour lui.
        #   ILS N'ENTRENT NI DANS « en_cours », NI DANS LES JAUGES, NI
        # DANS LES COMPTES : le ruban et le tableau les montrent, tout le
        # reste de cette methode continue de ne parler que du calage qui
        # tourne. Melanger les deux ferait lire les chiffres d'hier comme
        # ceux du calcul en cours.
        repris, courbes_reprises = self._suivi_precedent(dossier)
        noms_courants = {a.get("apport") for a in apports}
        repris = [a for a in repris if a.get("apport") not in noms_courants]
        courbes_reprises = [c for c in courbes_reprises
                            if c.get("apport") not in noms_courants]
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
        self.ruban_apports.actualiser(
            repris + apports,
            en_cours if en_cours is None else en_cours + len(repris))
        self.courbe_suivi.actualiser(
            etat.get("courbes"),
            courbes_reprises + (etat.get("courbes_precedentes") or []))

        # BANNIERE : l'etat en un mot, et sa couleur avant meme la lecture.
        if etat.get("termine"):
            if etat.get("conforme"):
                self._banniere(
                    ISL_VERT, "Calage terminé — conforme", glyphe="✔",
                    detail=f"{compte(comptes.get('validé', 0), 'apport calé', 'apports calés')} en "
                    f"{duree_lisible(etat.get('ecoule_s'))}"
                    + (f", {compte(etat['nb_calculs'], 'calcul')}"
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
                    ISL_TEAL_SOMBRE, "Calage en cours", glyphe="▶",
                    detail=f"Apport {(en_cours or 0) + 1} sur {etat.get('total')} — "
                    f"{nom}. Mis à jour "
                    f"{etat.get('maj', '')[11:]}.")

        # Ligne « ou en est-on », la phrase que l'on vient chercher.
        if en_cours is not None and en_cours < len(apports):
            a = apports[en_cours]
            self.label_suivi_position.setText(
                f"<b style='color:{ISL_TEAL_SOMBRE}'>{a['apport']} → "
                f"{a['section']}</b> &nbsp;·&nbsp; essai <b>{a['essais']}</b>"
                f" &nbsp;·&nbsp; apport <b>{a['ordre']}</b> sur "
                f"<b>{etat.get('total')}</b>")
        else:
            self.label_suivi_position.setText(
                f"{compte(comptes.get('validé', 0), 'validé')}, "
                f"{compte(comptes.get('échoué', 0), 'échoué')}, "
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
            date_lisible(fin) if fin else "—")
        self.label_suivi_maj.setText(
            f"actualisé {etat.get('maj', '')[11:]}"
            + (f" · {compte(etat['incidents'], 'incident')}"
               if etat.get("incidents") else ""))
        self._remplir_table_suivi(repris + apports)

    def _suivi_precedent(self, dossier):
        """
        Ce que le calage PRECEDENT a obtenu, tel que l'ecran doit le garder.

        Rend (apports, courbes) : les apports qu'il a VALIDES, marques
        « repris », et les hydrogrammes retenus a leurs sections, marques
        « anterieur ». Deux listes vides quand il n'y a pas d'archive — le cas
        du premier calage.

        L'appelant retire ensuite ceux que le calage EN COURS traite : c'est
        lui qui sait lesquels, et les garder en double ferait un ruban ou le
        meme apport apparait deux fois.

        RELU SEULEMENT QUAND L'ARCHIVE CHANGE, c'est-a-dire au demarrage d'un
        calage et jamais ensuite. Cette methode est appelee toutes les deux
        secondes tant que l'onglet est a l'ecran, et le dossier de suivi est le
        plus souvent sur un partage reseau — meme raison que _dossier_suivi.
        """
        if not dossier:
            return [], []
        chemin = Path(dossier) / noyau.ETAT_SUIVI_PRECEDENT
        cle = _cle_fichier(chemin)
        cache = getattr(self, "_archive_suivi", None)
        if cache is None or cache[0] != cle:
            cache = (cle, noyau.lire_avancement(dossier,
                                                noyau.ETAT_SUIVI_PRECEDENT))
            self._archive_suivi = cache
        etat = cache[1]
        if not etat:
            return [], []
        apports = [dict(a, statut=STATUT_REPRIS)
                   for a in (etat.get("apports") or [])
                   if a.get("statut") == "validé"]
        noms = {a.get("apport") for a in apports}
        derniere = courbe_retenue(etat.get("courbes"))
        courbes = [dict(c, anterieur=True)
                   for c in list(etat.get("courbes_precedentes") or [])
                   + ([derniere] if derniere else [])
                   if c.get("apport") in noms]
        return apports, courbes

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
            f"<b style='color:{couleur}'>{nombre(pct, 3, signe=True)} %</b> "
            f"(seuil {format(seuil, 'g').replace('.', ',')} %)"
            + (" — au-delà du seuil : l'essai est rejeté sans être comparé "
               "à la cible. Resserrer le pas de calcul du plan."
               if depasse else
               " — qualité du calcul, pas écart à la cible."))

    def _remplir_table_suivi(self, apports):
        self.table_suivi.setRowCount(len(apports))
        for ligne, a in enumerate(apports):
            statut = a.get("statut", "")
            valeurs = [
                a.get("apport", ""), a.get("section", ""),
                f"{GLYPHE_STATUT.get(statut, '')}  {statut}",
                str(a.get("essais") or ""),
                "—" if a.get("volume_pct") is None else f"{nombre(a['volume_pct'])} %",
                "—" if a.get("pic_pct") is None else f"{nombre(a['pic_pct'])} %",
            ]
            for colonne, valeur in enumerate(valeurs):
                cellule = QTableWidgetItem(str(valeur))
                if colonne == 2:
                    # Remappee en theme sombre, comme les widgets peints :
                    # l'ardoise sur le fond Night Mapping rendait 2,3:1.
                    cellule.setForeground(couleur_theme(
                        COULEUR_STATUT.get(statut, ISL_ARDOISE), self.table_suivi))
                    police = cellule.font()
                    police.setBold(True)
                    cellule.setFont(police)
                if colonne >= 3:
                    cellule.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_suivi.setItem(ligne, colonne, cellule)
        self.table_suivi.reclasser()
        self.table_suivi.resizeColumnsToContents()

    def _onglet_aide(self):
        """
        Mode operatoire et diagnostic. Le contenu reprend la note
        methodologique : mieux vaut l'avoir sous les yeux au moment d'agir
        qu'a cote, dans un document qu'on n'ouvre pas.
        """
        page = QWidget()
        v = QVBoxLayout(page)
        v.setSpacing(10)

        texte = QTextBrowser()
        # Une ancre « #terme_… » defile jusqu'a l'entree du lexique ; une
        # source s'ouvre dans le navigateur ; le survol d'un terme montre sa
        # definition.
        texte.setOpenExternalLinks(True)
        texte.highlighted.connect(self._survol_aide)
        self.navigateur_aide = texte
        # Le style de l'aide suit la charte, mais ne fixe aucun fond : le
        # QTextBrowser herite ainsi du theme clair ou sombre de QGIS.
        texte.setHtml(
            "<style>"
            "body { line-height: 1.5; }"
            "h2 { margin-bottom: 4px; }"
            "h3 { margin-top: 16px; margin-bottom: 4px; }"
            "p { margin-top: 4px; margin-bottom: 4px; }"
            "li { margin-bottom: 6px; }"
            "</style>" + AIDE_HTML)
        texte.setAccessibleName("Mode opératoire du calage des apports")
        texte.setMinimumHeight(240)

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
        groupe = QGroupBox("Diagnostic et paramètres du poste")
        fp = formulaire(groupe)
        fp.addRow(texte_aide(
            "Les emplacements sont détectés et mémorisés automatiquement. "
            "Vérifiez l’environnement ; renseignez-les seulement s’ils sont absents."))
        bouton = QPushButton("Vérifier l’environnement")
        bouton.clicked.connect(self._diagnostic)
        ligne_diag = QHBoxLayout()
        ligne_diag.addWidget(bouton)
        ligne_diag.addStretch(1)
        fp.addRow(ligne_diag)
        self.label_diagnostic = texte_etat()
        fp.addRow(self.label_diagnostic)

        self.label_chaine = QLabel("")
        self.label_chaine.setWordWrap(True)
        self.label_chaine.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bouton_chaine = QPushButton("Choisir le dossier…")
        bouton_chaine.setToolTip(
            "Dossier contenant criteres.py, geometrie.py, controle_donnees.py, "
            "livrables.py et pont_hecras.py.")
        bouton_chaine.clicked.connect(self._choisir_chaine)
        # LE CHEMIN SUR SA LIGNE, LES BOUTONS DESSOUS (23/10/2026). Cote a
        # cote, un chemin sans espace ne passe pas a la ligne : a 13 pt sur
        # 720 px le groupe exigeait 704 px, la page defilait de 43 px et les
        # boutons etaient rognes. Le chemin reste selectionnable et copiable
        # tel quel (audit CAL-A4) : aucun espace sans chasse n'y est insere.
        ligne_chaine = QHBoxLayout()
        ligne_chaine.addWidget(bouton_chaine)
        ligne_chaine.addStretch(1)
        bloc_chaine = QVBoxLayout()
        bloc_chaine.addWidget(self.label_chaine)
        bloc_chaine.addLayout(ligne_chaine)
        fp.addRow("Chaîne de calage :", bloc_chaine)

        self.label_interpreteur = QLabel("")
        self.label_interpreteur.setWordWrap(True)
        self.label_interpreteur.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        bouton_interp = QPushButton("Choisir un Python…")
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
            "Cherche les Python présents sur ce poste, en propose un, crée "
            "l'environnement HEC-RAS et y installe tout ce qu'il faut, puis "
            "le vérifie. Il n'y a pas besoin de savoir où Python est "
            "installé — c'est ce que ce bouton résout.")
        bouton_installer.clicked.connect(self._installer_interpreteur)
        # « INSTALLER » AVANT « DESIGNER », parce que c'est le geste de celui
        # qui n'a rien : designer suppose de savoir ou chercher, installer non.
        ligne_interp = QHBoxLayout()
        ligne_interp.addWidget(bouton_installer)
        ligne_interp.addWidget(bouton_interp)
        ligne_interp.addStretch(1)
        bloc_interp = QVBoxLayout()
        bloc_interp.addWidget(self.label_interpreteur)
        bloc_interp.addLayout(ligne_interp)
        fp.addRow("Interpréteur HEC-RAS :", bloc_interp)

        self.bouton_installer = bouton_installer
        self._commandes_poste = (bouton_installer, bouton_interp, bouton_chaine, bouton)
        self.progression_installation = QProgressBar()
        self.progression_installation.setRange(0, 0)
        self.progression_installation.setAccessibleName("Installation Python en cours")
        self.progression_installation.hide()
        fp.addRow(self.progression_installation)
        QTimer.singleShot(0, self._reprendre_installation)
        v.addWidget(groupe)
        v.addWidget(texte, 1)
        self._maj_parametres_poste()
        return page

    def _survol_aide(self, lien):
        """Survol d'un terme dans l'aide : sa definition en infobulle."""
        lien = lien.toString() if hasattr(lien, "toString") else str(lien)
        t = lexique.terme(lien.partition("#" + lexique.ANCRE)[2])
        if t is None:
            QToolTip.hideText()
        else:
            QToolTip.showText(QCursor.pos(), lexique.definition(t), self.navigateur_aide)

    def _ouvrir_lexique(self, lien):
        """
        Clic sur un terme d'un texte d'aide ou d'etat : l'aide s'ouvre a son
        entree du lexique. Protege : une exception qui remonte d'un slot peut
        fermer QGIS.
        """
        try:
            if lien.startswith(lexique.PREFIXE):
                self.onglets.setCurrentIndex(ONGLET_AIDE)
                self.navigateur_aide.scrollToAnchor(
                    lexique.ANCRE + lien[len(lexique.PREFIXE):])
        except Exception as e:
            journaliser("Lexique de l'aide", e)

    def _maj_parametres_poste(self):
        """
        Reflete l'etat courant des deux emplacements.

        UN MANQUE DIT LE GESTE QUI LE COMBLE. « introuvable » en rouge est
        un constat, pas une consigne : celui qui decouvre le plugin y lit un
        defaut sans savoir lequel des trois boutons de la ligne le concerne.
        """
        chaine = noyau.trouver_chaine()
        self.label_chaine.setText(
            str(chaine) if chaine
            else f"<span style='color:{ISL_ROUGE}'>introuvable</span> — "
                 f"désignez-la ci-dessous")
        interp = noyau.interpreteur_hecras()
        self.label_interpreteur.setText(
            str(interp) if interp
            else f"<span style='color:{ISL_ROUGE}'>introuvable</span> — "
                 f"cliquez « Installer… », qui trouvera Python tout seul")

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
        if self._installation_occupe():
            return
        chemin, _ = QFileDialog.getOpenFileName(
            self, "Interpréteur Python disposant de ras-commander", "",
            "Exécutable Python (python.exe python3.exe python);;"
            "Tous les fichiers (*)")
        if not chemin:
            return
        ok, message = noyau.definir_interpreteur(chemin)
        if ok:
            QSettings().setValue(PluginCalage.CLE_INTERPRETEUR, str(chemin))
            self._signaler("Interpréteur accepté", message,
                           Qgis.MessageLevel.Success, 12)
        else:
            QMessageBox.critical(
                self, "Interpréteur inutilisable",
                f"« {chemin} » ne peut pas piloter HEC-RAS.\n\n{message}\n\n"
                f"Il lui faut ras-commander et h5py. Le python de QGIS ne "
                f"convient pas : sa bibliothèque HDF5 entre en conflit avec "
                f"celle de h5py.")
        self._maj_parametres_poste()

    def _installation_occupe(self):
        if installation_en_cours() is None:
            return False
        self._signaler(
            "Installation en cours",
            "Attendez la vérification de Python avant une opération HEC-RAS. "
            "Le suivi est dans Aide et configuration ; QGIS reste utilisable.",
            Qgis.MessageLevel.Warning, 10)
        return True

    def _reprendre_installation(self):
        tache = installation_en_cours()
        if tache is not None:
            self._suivre_installation(tache)

    def _suivre_installation(self, tache):
        if self._tache_installation is tache:
            return
        self._tache_installation = tache
        tache.phase.connect(self._phase_installation)
        fin = self._fin_recherche_python if isinstance(tache, TacheRecherchePython) else self._fin_installation
        tache.resultat.connect(fin)
        for bouton in self._commandes_poste:
            bouton.setEnabled(False)
        self.progression_installation.show()
        self._phase_installation(tache.lignes[-1] if tache.lignes else "Installation en attente…")

    def _phase_installation(self, phase):
        if isinstance(self._tache_installation, TacheRecherchePython):
            self.progression_installation.setAccessibleName("Recherche des interpréteurs Python")
            dire(self.label_diagnostic, phase + "\nQGIS reste utilisable. "
                 "La recherche continue si cette fenêtre est fermée. "
                 "Elle peut être annulée dans le gestionnaire de tâches QGIS.")
            return
        self.progression_installation.setAccessibleName("Installation Python en cours")
        dire(self.label_diagnostic, phase + "\nQGIS reste utilisable. "
             "L'installation continue si cette fenêtre est fermée. "
             "Ne quittez pas QGIS ; l'arrêt pendant pip n'est pas proposé.")

    def _detacher_installation(self):
        tache = self._tache_installation
        if tache is not None:
            try:
                tache.phase.disconnect(self._phase_installation)
                fin = self._fin_recherche_python if isinstance(tache, TacheRecherchePython) else self._fin_installation
                tache.resultat.disconnect(fin)
            except (TypeError, RuntimeError):
                pass
            self._tache_installation = None

    def _installer_interpreteur(self):
        """Confirme la cible ; recherche et installation restent hors du fil GUI."""
        if self._choix_python_ouvert:
            return
        if self._python_en_attente is not None:
            self._choisir_python_recherche()
            return
        if self._installation_occupe():
            return
        # emplacement_venv_hecras() rend TOUJOURS un chemin depuis le
        # 31/08/2026 : a cote d'une chaine externe si elle existe, dans le
        # dossier de donnees du plugin sinon. Elle rendait None dans ce
        # second cas, et le bouton refusait donc de servir sur un poste neuf
        # — le seul ou il est utile.
        cible = noyau.emplacement_venv_hecras()
        # LA LISTE VIENT DU NOYAU, jamais recopiee ici : c'est elle qui est
        # installée ET vérifiée, et l'annoncer autrement finirait par mentir.
        paquets = [p for _, p in noyau.PAQUETS_HECRAS]
        with sans_sablier(self):
            accepte = confirmer(
                self, "Installer l'environnement Python HEC-RAS",
                f"Un environnement Python va être créé dans :\n{cible}\n\n"
                f"puis {len(paquets)} paquets y seront installés depuis "
                f"PyPI :\n{', '.join(paquets)}\n\n"
                f"Téléchargement de plusieurs centaines de Mo, plusieurs "
                f"minutes. QGIS restera utilisable. Ne quittez pas QGIS : "
                f"l’arrêt pendant pip n’est pas proposé.",
                oui="Installer", non="Plus tard")
        if not accepte:
            return

        tache = TacheRecherchePython(cible)
        self._suivre_installation(tache)
        QgsApplication.taskManager().addTask(tache)

    def _fin_recherche_python(self, candidats, message, journal):
        cible = self._tache_installation.cible
        self._detacher_installation()
        self.progression_installation.hide()
        for bouton in self._commandes_poste:
            bouton.setEnabled(True)
        dire(self.label_diagnostic, message)
        if candidats is None:
            return  # annulation/erreur : aucun sélecteur ni installation implicite
        self._python_en_attente = (cible, candidats)
        # finished() doit rendre la main au gestionnaire avant une boîte de choix.
        QTimer.singleShot(0, self._choisir_python_recherche)

    def _choisir_python_recherche(self):
        if (self._python_en_attente is None or self._choix_python_ouvert
                or not self.isVisible()):
            return
        cible, candidats = self._python_en_attente
        self._python_en_attente = None
        self._choix_python_ouvert = True
        try:
            self._proposer_python(cible, candidats)
        finally:
            self._choix_python_ouvert = False

    def _proposer_python(self, cible, candidats):
        """Choix sur le fil graphique ; la cible confirmée reste inchangée."""
        base = ""
        PARCOURIR = "Parcourir moi-même…"
        if candidats:
            libelles = [
                f"{'.'.join(str(n) for n in c['version'])} — {c['chemin']}"
                + ("   (fourni par QGIS)" if c["origine"] == "QGIS" else "")
                for c in candidats] + [PARCOURIR]
            with sans_sablier(self):
                choix, valide = QInputDialog.getItem(
                    self, "Python de base",
                    f"{compte(len(candidats), 'interpréteur utilisable trouvé', 'interpréteurs utilisables trouvés')} "
                    f"sur ce poste.\nLe premier est recommandé : un "
                    f"environnement bâti sur le Python de QGIS cesse de "
                    f"fonctionner\nle jour où une montée de version de QGIS "
                    f"remplace son dossier.",
                    libelles, 0, False)
            if not valide:
                return
            if choix != PARCOURIR:
                base = str(candidats[libelles.index(choix)]["chemin"])
        else:
            # RIEN TROUVÉ : ON DIT QUOI FAIRE, au lieu d'ouvrir un sélecteur
            # devant lequel l'utilisateur n'a rien à répondre.
            with sans_sablier(self):
                QMessageBox.warning(
                    self, "Aucun Python utilisable sur ce poste",
                    "Aucun interpréteur capable de créer un environnement n'a "
                    "été trouvé.\n\n"
                    "Les « python.exe » de WindowsApps n'en sont pas : ce sont "
                    "des fichiers vides dont le seul rôle est d'afficher "
                    "« Python was not found ». Ils occupent le PATH sans rien "
                    "exécuter.\n\n"
                    "Installer Python 3.9 ou plus depuis python.org, en "
                    "cochant « Add python.exe to PATH », puis relancer QGIS. "
                    "Le Python fourni avec QGIS convient aussi : il se trouve "
                    "dans « apps\\Python3xx\\python.exe » de l'installation "
                    "QGIS, et non dans « bin ».")

        if not base:
            with sans_sablier(self):
                base, _ = QFileDialog.getOpenFileName(
                    self, "Python de base (python.exe) servant à créer "
                          "l'environnement", "",
                    "Exécutable Python (python.exe python3.exe python);;"
                    "Tous les fichiers (*)")
        if not base:
            return

        tache = TacheInstallation(base, cible, PluginCalage.CLE_INTERPRETEUR)
        self._suivre_installation(tache)
        QgsApplication.taskManager().addTask(tache)

    def _fin_installation(self, chemin, message, journal):
        self._detacher_installation()
        self.progression_installation.hide()
        for bouton in self._commandes_poste:
            bouton.setEnabled(True)
        self._maj_parametres_poste()
        if chemin is None:
            dire(self.label_diagnostic, f"Installation impossible : {message}")
            journaliser(f"Installation de l'interpréteur HEC-RAS : {message}")
            if not self.isVisible():
                return  # le journal QGIS conserve le détail ; ne pas rouvrir le dialogue
            boite = QMessageBox(self)
            boite.setIcon(QMessageBox.Icon.Critical)
            boite.setWindowTitle("Installation impossible")
            boite.setText("L'environnement Python HEC-RAS n'a pas pu être "
                          "installé.")
            boite.setDetailedText(f"{journal}\n\n{message}")
            rendre_redimensionnable(boite)
            rendre_la_main(self)
            # finished() du gestionnaire doit rendre la main sans attendre un clic.
            boite.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            boite.setModal(False)
            boite.show()
            self._erreur_installation = boite
            return

        self._maj_parametres_poste()
        rendre_la_main(self)
        dire(self.label_diagnostic,
             f"Interpréteur HEC-RAS installé et vérifié :\n{chemin}\n\n{message}")
        self._signaler(
            "Environnement installé",
            f"Interpréteur HEC-RAS installé et vérifié : {chemin}. Retenu "
            f"d'une session à l'autre ; détail sous « Vérifier l’environnement ».",
            Qgis.MessageLevel.Success, 0)

    def _diagnostic(self):
        """
        Etat de l'environnement, et proposition de designer ce qui manque.

        SEUL CHEMIN DE RECUPERATION quand le plugin est installe depuis une
        archive : son dossier parent est alors le repertoire des extensions
        du profil QGIS, qui ne contient ni la chaine ni l'interpreteur.
        """
        if self._installation_occupe():
            return
        if noyau.trouver_chaine() is None:
            # QUATRIEME QUESTION OUI/NON SANS DEFAUT, que la relecture du 17/09
            # n'avait pas comptee : meme correctif que les trois autres.
            if confirmer(
                    self, "Chaîne de calage introuvable",
                    "Le dossier de la chaîne de calage n'a pas été trouvé.\n\n"
                    "Installé depuis une archive, le plugin ne peut pas le "
                    "deviner : il doit contenir criteres.py, geometrie.py, "
                    "controle_donnees.py, livrables.py et pont_hecras.py.",
                    oui="Désigner le dossier…", non="Plus tard"):
                self._choisir_chaine()

        if noyau.interpreteur_hecras() is None:
            # LE CHEMIN DE SORTIE EST « INSTALLER », PAS « DESIGNER ».
            #
            # Ce message ne proposait QUE de designer, c'est-a-dire d'ouvrir
            # un selecteur de fichier — sur le poste ou l'interpreteur manque,
            # il n'y a precisement rien a y designer. Le bouton « Installer… »
            # existe pour ce cas exact, et le seul chemin de recuperation du
            # plugin ne le mentionnait pas.
            #
            # ET LA RECETTE MANUELLE VIENT DU NOYAU. Elle etait ecrite ici, a
            # DEUX paquets, quand la verification en exige onze : la suivre a
            # la lettre fabriquait un environnement que le plugin refusait
            # ensuite. Elle passe en detail replie — c'est l'issue de secours
            # d'un poste dont la sortie PyPI est fermee a QGIS, pas la voie
            # recommandee.
            boite = QMessageBox(self)
            boite.setIcon(QMessageBox.Icon.Question)
            boite.setWindowTitle("Interpréteur HEC-RAS introuvable")
            boite.setText(
                "Le calage a besoin d'un Python séparé de celui de QGIS, et "
                "il n'y en a pas encore sur ce poste.")
            boite.setInformativeText(
                "« Installer » s'en charge de bout en bout : il cherche les "
                "Python présents sur le poste, propose le meilleur, crée "
                "l'environnement et vérifie le résultat.\n\nVous n'avez pas "
                "besoin de savoir où Python est installé.\n\nQGIS ne peut "
                "pas piloter HEC-RAS lui-même : sa bibliothèque HDF5 entre en "
                "conflit avec celle de h5py.")
            boite.setDetailedText(
                "À la main — seulement si ce poste interdit à QGIS de sortir "
                "sur PyPI :\n\n    "
                + "\n    ".join(noyau.recette_installation_manuelle())
                + "\n\npuis désigner ici %USERPROFILE%\\venv-hecras\\"
                  "Scripts\\python.exe.")
            bouton_poser = boite.addButton(
                "Installer…", QMessageBox.ButtonRole.AcceptRole)
            bouton_designer = boite.addButton(
                "Désigner un Python existant…",
                QMessageBox.ButtonRole.ActionRole)
            boite.addButton("Plus tard", QMessageBox.ButtonRole.RejectRole)
            boite.setDefaultButton(bouton_poser)
            rendre_redimensionnable(boite, largeur=700, hauteur=160)
            boite.exec()
            if boite.clickedButton() is bouton_poser:
                self._installer_interpreteur()
            elif boite.clickedButton() is bouton_designer:
                self._choisir_interpreteur()

        disponible, messages = noyau.chaine_disponible()
        resume = ("Utilisable : " + ("oui" if disponible else "NON")
                  + "\n" + "\n".join(messages))
        dire(self.label_diagnostic, resume)
        self._maj_parametres_poste()
        self._signaler(
            "Diagnostic",
            "Environnement utilisable." if disponible
            else "Environnement incomplet : le détail est affiché sous le bouton.",
            Qgis.MessageLevel.Success if disponible else Qgis.MessageLevel.Warning)

    @avec_sablier
    def _importer_hydrogrammes(self):
        """
        Recopie dans l'Excel de CE calcul les hydrogrammes et les pentes de
        l'Excel d'un calcul precedent — et rien d'autre (24/09/2026, demande
        utilisateur). Remplace « Reprendre un Excel… », qui faisait du fichier
        choisi le classeur de la fenetre, rejouait les controles et reprenait
        ses reglages : l'utilisateur n'en voulait que les hydrogrammes. La
        regle d'appariement et les refus sont ceux de
        noyau.importer_hydrogrammes.
        """
        if not self.classeur:
            return                  # bouton grise tant qu'aucun Excel n'existe
        try:
            with sans_sablier(self):
                source, _ = QFileDialog.getOpenFileName(
                    self, "Excel des hydrogrammes d'un calcul précédent",
                    str(Path(self.classeur).parent), "Classeur Excel (*.xlsx)")
            if not source:
                return
            bilan = noyau.importer_hydrogrammes(source, self.classeur)
        except ValueError as e:
            # LES CIBLES NE CORRESPONDENT PAS, ou ce n'est pas un Excel des
            # objectifs : c'est un constat a lire, pas une panne.
            dire(self.label_import, f"<span style='color:{ISL_ROUGE}'>Rien "
                                    f"n’a été importé : {e}</span>")
            self._signaler("Hydrogrammes non importés", str(e),
                           Qgis.MessageLevel.Warning, duree=12)
            return
        except Exception as e:                              # noqa: BLE001
            journaliser("Import des hydrogrammes", e)
            QMessageBox.critical(
                self, "Import des hydrogrammes",
                f"{e}\n\nSi l'Excel de ce calcul est ouvert dans Excel, le "
                f"fermer puis recommencer : rien n'a été importé.")
            return
        lignes = [f"<b>{compte(len(bilan['importees']), 'hydrogramme importé', 'hydrogrammes importés')}</b>"
                  f" de {Path(source).name} : {', '.join(bilan['importees'])}."]
        if bilan["vides"]:
            lignes.append("Restent vides, faute de correspondance dans "
                          f"l’Excel importé : {', '.join(bilan['vides'])}.")
        if bilan["gardees"]:
            lignes.append("Sans correspondance, gardent leur saisie : "
                          f"{', '.join(bilan['gardees'])}.")
        if bilan["ignorees"]:
            lignes.append("Ignorés, leurs sections n’étant pas dans ce "
                          f"calcul : {', '.join(bilan['ignorees'])}.")
        lignes.append(f"Pentes reprises : {', '.join(bilan['pentes'])}."
                      if bilan["pentes"] else "Aucune pente reprise.")
        lignes.append("L’Excel d’avant l’import est gardé sous "
                      f"{Path(bilan['sauvegarde']).name}.")
        dire(self.label_import, "<br>".join(lignes))
        self._signaler("Hydrogrammes importés",
                       f"{compte(len(bilan['importees']), 'hydrogramme importé', 'hydrogrammes importés')} ; "
                       "le détail est sous le bouton.",
                       Qgis.MessageLevel.Success, duree=8)
        self._maj_onglet_validation_depuis_classeur()

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
                 f"référence « {self._titre_etape('sans_apport')} ».")
            # LE RECAPITULATIF SUIT AUSSI CE RETOUR-LA. Pose seulement en fin
            # de methode, il gardait a l'ecran la reprise precedente quand on
            # revenait a « tous » — un compte rendu perime, le defaut meme
            # que ce recapitulatif existe pour corriger.
            self._dire_reprise()
            return
        try:
            noms = [a for a, _ in noyau.apports_du_classeur(self.classeur)]
            amont = noms[:noms.index(premier)]
        except Exception as e:                              # noqa: BLE001
            journaliser("Apports en amont du premier apport", e)
            amont = []
        dire(self.label_premier_apport,
             f"Départ du plan « {self._titre_etape('Apport_' + amont[-1])} ». "
             f"{compte(len(amont), 'apport amont tenu pour calé et non retouché', 'apports amont tenus pour calés et non retouchés')} : "
             f"{', '.join(amont)}."
             if amont else
             "Premier apport de la liste : le calage part du calcul de "
             f"référence « {self._titre_etape('sans_apport')} », comme sans "
             "ce réglage.")
        self._dire_reprise()

    def _titre_etape(self, nom):
        """
        Titre du plan d'une etape, prefixe compris — la MEME regle que
        calage.titre_etape, redite ici pour un seul usage d'affichage : la
        chaine n'est pas importable dans le processus QGIS.
        """
        prefixe = ""
        champ = getattr(self, "edit_prefixe_scenario", None)
        if champ is not None:
            prefixe = champ.text().strip().rstrip("-_ ")
        if not prefixe:
            return nom
        if nom == "avec_apports":
            return prefixe
        if nom == "sans_apport":
            return f"{prefixe}-sans"
        return f"{prefixe}-{nom.removeprefix('Apport_').removesuffix(' et aval')}"

    def _dire_reprise(self, *_):
        """
        Ce que le lancement va faire, en toutes lettres, au-dessus du bouton.

        POURQUOI EN PERMANENCE DANS LA PAGE. La question de reprise
        (_confirmer_reprise) ne se pose que s'il y a des apports VALIDES a
        perdre. Apres un ECHEC, l'apport ou le calage s'est arrete n'est pas
        valide et rien en aval n'a tourne : plus rien ne se perd, la question
        ne se pose donc pas, et AUCUN ecran ne disait d'ou le calcul
        repartait. C'est le cas signale le 20 septembre 2026 — « la
        methodologie de reprise n'est pas claire ». Un compte rendu se lit
        dans la page, avant le clic, et se relit apres ; une boite ne se
        relit pas.

        IL NOMME LES PLANS AVEC LEUR PREFIXE. « ARA06 » ne se trouve
        pas dans le gestionnaire de plans : ce qui s'y trouve est
        « Aran-Q100-V1-ARA06 ». Un compte rendu qui nomme autrement
        que le modele oblige a traduire.
        """
        label = getattr(self, "label_reprise", None)
        if label is None:
            return
        if not self.classeur:
            dire(label, "Le récapitulatif s’affichera une fois le paquet "
                        f"composé par « {BOUTON_GEOMETRIE} ».")
            return
        try:
            tous = [a for a, _ in noyau.apports_du_classeur(self.classeur)]
        except Exception as e:                              # noqa: BLE001
            journaliser("Apports du classeur pour le récapitulatif", e)
            dire(label, f"(liste des apports illisible : {e})")
            return
        dossier = self._dossier_suivi()
        precedent = noyau.lire_avancement(dossier) if dossier else None
        valides = [a.get("apport")
                   for a in ((precedent or {}).get("apports") or [])
                   if a.get("statut") == "validé"]
        premier = self._premier_apport()
        conserves, perdus, _propose = plan_de_reprise(tous, valides, premier)
        rang = tous.index(premier) if premier in tous else 0
        a_calculer = tous[rang:]

        if not premier or rang == 0:
            phrases = [
                f"<b>Calage complet</b> — les {len(tous)} apports seront "
                f"calculés, de l’amont vers l’aval, à partir du calcul de "
                f"référence « {self._titre_etape('sans_apport')} »."]
        else:
            phrases = [
                f"<b>Reprise à « {premier} »</b> — le calage repart du plan "
                f"« {self._titre_etape('Apport_' + tous[rang - 1])} » et n’y "
                f"touche pas.",
                f"<b>Tenus pour calés</b> ({rang}) : "
                f"{', '.join(tous[:rang])}.",
                f"<b>À calculer</b> ({len(a_calculer)}) : "
                f"{', '.join(a_calculer)}."]
            phrases.append(
                "La chaîne vérifie au lancement que ce plan est bien dans le "
                "modèle. S’il manque, elle le dit et repart du plan de "
                "référence — les apports amont valent alors ce qu’ils y "
                "valent.")
        # CE QUE LE CALAGE PRECEDENT PERD, DIT ICI AUSSI. La boite ne le
        # demande que s'il y a des apports valides a perdre ; le dire dans la
        # page couvre le cas ou il n'y en a pas — un calage arrete en echec.
        if perdus:
            phrases.append(
                f"<b>Refaits</b> ({len(perdus)}) — le calage précédent les "
                f"avait validés : {', '.join(perdus)}.")
        elif valides:
            phrases.append(
                f"Le calage précédent avait validé "
                f"{compte(len(conserves), 'apport')} ; aucun n’est refait.")
        # LES CŒURS, S'ILS CHANGENT : c'est ce clic qui les ecrit.
        coeurs = self._coeurs_demandes()
        if coeurs:
            phrases.append(
                f"<b>Cœurs</b> : HEC-RAS recevra {compte(coeurs, 'cœur')} par calcul, "
                f"écrits dans chaque plan d’étape juste avant son calcul.")
        dire(label, "<br>".join(phrases))

    def _relire_cibles_si_modifiees(self, *_):
        """
        Relit les cibles si le classeur a change sur disque — Excel vient
        d'enregistrer. « Ce que portent les cibles » (onglet 3) et leur etat
        (onglet 4) ne suivaient que la composition et la reprise : un
        hydrogramme colle dans l'Excel ouvert n'y paraissait qu'apres une
        recomposition.

        Appele au changement d'onglet et quand QGIS redevient l'application
        active — le retour d'Excel. Une date de fichier lue a chaque fois ;
        le classeur, souvent sur un partage reseau, n'est rouvert que s'il
        a change.
        """
        if not self.classeur:
            return
        cle = _cle_fichier(self.classeur)
        if cle is None or cle == getattr(self, "_classeur_lu", None):
            return
        self._classeur_lu = cle
        self._maj_onglet_validation_depuis_classeur()

    def _maj_onglet_validation_depuis_classeur(self):
        """
        Relit l'etat des cibles quand l'Excel a change sur disque — Excel
        vient d'enregistrer, ou un import vient d'y ecrire.
        """
        try:
            etat = noyau.etat_cibles(self.classeur)
        except Exception as e:
            # LE CLASSEUR S'AFFICHE MEME QUAND SON ETAT EST ILLISIBLE : un
            # simple « return » laissait l'etat d'avant a l'ecran, un
            # affichage qui ment. Meme conduite que _maj_onglet_validation.
            journaliser("État des cibles après contrôle", e)
            self.label_validation_classeur.setText(str(self.classeur))
            self.label_validation_cibles.setText(f"(illisible : {e})")
            self._cibles_manquantes = None
            return
        self.label_validation_classeur.setText(str(self.classeur))
        manquantes = etat.get("manquantes") or []
        self.label_validation_cibles.setText(
            f"{etat['renseignees']}/{etat['total']} "
            f"{'renseignée' if etat['renseignees'] < 2 else 'renseignées'}"
            + (f" — manquantes : {', '.join(manquantes)}" if manquantes else ""))
        self._maj_resume_cibles()
        # Le fil et « Étape suivante » suivent le retour d'Excel.
        self._cibles_manquantes = list(manquantes)
        if hasattr(self, "label_fil"):
            self._maj_fil()

    @avec_sablier
    def _confirmer_reprise(self):
        """
        Dire ce qu'un lancement CONSERVE et ce qu'il PERD d'un calage
        precedent, et poser le depart quand on le demande. Rend False si l'on
        renonce.

        LE CAS QUI L'A DEMANDEE (13/09/2026). Un calage mene a bout, un seul
        reglage change ensuite — le nombre d'essais d'un apport —, et l'on
        relance. La fenetre repartait du calcul de reference et refaisait tous
        les apports amont, soit des heures de calcul pour rien, sans rien
        demander. Le reglage qui l'evite existe depuis longtemps — « Premier
        apport a caler », etape 4, encadre « Apports a determiner » — mais il
        faut savoir qu'il est la et y penser AVANT de cliquer : personne ne va
        chercher un reglage pour un probleme qu'il n'a pas encore.

        ON NE DEMANDE QUE S'IL Y A QUELQUE CHOSE A PERDRE. Sans calage
        precedent dans le dossier de suivi — le cas courant — le lancement
        part sans question : une question posee a chaque fois s'apprend par
        coeur et ne se lit plus.

        CE QUE L'ARCHIVE PROUVE, ET CE QU'ELLE NE PROUVE PAS. Elle dit ce que
        le calage precedent a VALIDE. Elle ne dit pas que les plans d'etape
        sont toujours dans le modele : c'est pont_hecras qui cherche le plan
        de depart et qui avertit s'il manque. La question porte donc sur le
        travail, pas sur les fichiers.
        """
        dossier = self._dossier_suivi()
        precedent = noyau.lire_avancement(dossier) if dossier else None
        valides = [a.get("apport")
                   for a in ((precedent or {}).get("apports") or [])
                   if a.get("statut") == "validé"]
        if not valides:
            return True
        try:
            tous = [a for a, _ in noyau.apports_du_classeur(self.classeur)]
        except Exception as e:                              # noqa: BLE001
            # Une lecture qui rate ne doit pas empecher de lancer : le
            # classeur est relu par la chaine, qui refusera pour de vrai.
            journaliser("Apports du classeur avant lancement", e)
            return True
        premier = self._premier_apport()
        conserves, perdus, propose = plan_de_reprise(tous, valides, premier)
        if not perdus:
            # Tout ce qui etait cale est en amont du depart : rien ne se perd.
            return True

        def lister(noms):
            return ", ".join(noms) if noms else "aucun"

        if premier:
            titre = "Reprendre le calage"
            texte = (
                f"<b>Reprendre le calage à l'apport « {premier} » ?</b>"
                f"<br><br>"
                f"<b>Conservés</b> ({len(conserves)}) — déjà calés en amont, "
                f"leurs plans d'étape ne sont pas retouchés : "
                f"{lister(conserves)}.<br><br>"
                f"<b>Perdus</b> ({len(perdus)}) — leur calage précédent sera "
                f"refait à partir de « {premier} » : {lister(perdus)}.")
        else:
            titre = "Un calage précédent existe"
            texte = (
                f"<b>Tout recaler, et perdre "
                f"{compte(len(perdus), 'apport déjà calé', 'apports déjà calés')} ?</b><br><br>"
                f"Le calage précédent avait validé : {lister(perdus)}.<br>"
                f"Lancer maintenant les refait TOUS, depuis le calcul de "
                f"référence « {self._titre_etape('sans_apport')} » — plusieurs "
                "heures par apport."
                f"<br><br>"
                + (f"Pour ne reprendre qu'à partir de « {propose} », le "
                   f"premier que le calage précédent n'a pas validé, les "
                   f"apports en amont seront conservés."
                   if propose else
                   "Pour n'en reprendre qu'une partie, renseigner « Premier "
                   "apport à caler », étape 3 « Lancer », encadré « Apports à "
                   "déterminer »."))
        with sans_sablier(self):
            boite = QMessageBox(self)
            boite.setWindowTitle(titre)
            boite.setIcon(QMessageBox.Icon.Question)
            boite.setText(texte)
            bouton_reprendre = (
                boite.addButton(f"Reprendre à {propose}",
                                QMessageBox.ButtonRole.AcceptRole)
                if propose else None)
            boite.addButton("Reprendre" if premier else "Tout recaler",
                            QMessageBox.ButtonRole.AcceptRole)
            bouton_annuler = boite.addButton(
                "Annuler", QMessageBox.ButtonRole.RejectRole)
            # LE DEFAUT EST CELUI QUI NE COUTE RIEN : reprendre si on peut,
            # annuler sinon. « Tout recaler » n'est jamais le defaut — c'est
            # l'issue qui jette des heures de calcul.
            boite.setDefaultButton(bouton_reprendre or bouton_annuler)
            boite.exec()
            clique = boite.clickedButton()
        # AUCUN BOUTON CLIQUE VAUT ANNULER. Une boite fermee par la croix, ou
        # un talon de recette qui ne repond pas, ne doit pas lancer des heures
        # de calcul par defaut.
        if clique is None or clique is bouton_annuler:
            dire(self.label_lancement, "Lancement annulé.")
            return False
        if bouton_reprendre is not None and clique is bouton_reprendre:
            rang = self.combo_premier_apport.findData(propose)
            if rang < 0:
                self._remplir_premier_apport()
                rang = self.combo_premier_apport.findData(propose)
            if rang < 0:
                # ON NE LANCE PAS PLUTOT QUE DE LANCER AUTRE CHOSE. Poser le
                # depart est TOUT ce que ce bouton fait : echouer en silence
                # repartirait de zero, c'est-a-dire exactement ce que
                # l'utilisateur vient de refuser.
                QMessageBox.critical(
                    self, "Reprise",
                    f"« {propose} » ne figure pas dans la liste « Premier "
                    f"apport à caler » : la reprise ne peut pas être posée, "
                    f"et le calage n'est pas lancé — il serait reparti du "
                    f"calcul de référence.")
                return False
            self.combo_premier_apport.setCurrentIndex(rang)
        return True

    def _accepter_plan_final(self):
        """
        Le plan final porte le prefixe seul : un plan existant peut avoir ce
        nom. Rend False si le lancement s'arrete.

        LE PLAN DE REFERENCE : refus. Il n'est jamais remplace, et deux plans
        auraient le meme titre et le meme Short Identifier.

        UN AUTRE PLAN : question, car rien ne distingue le plan final d'une
        relance d'un plan de l'ingenieur. LUE AU LANCEMENT, PAS A L'OUVERTURE :
        un calage precedent a pu ecrire ce plan depuis. Une lecture qui rate
        n'empeche pas de lancer : le pont refusera le plan de reference.
        """
        projet = self.edit_projet_hecras.text().strip()
        try:
            info = noyau.lister_projet_hecras(projet) if projet else self.info_projet
        except Exception as e:                              # noqa: BLE001
            journaliser("Plans du projet avant lancement", e)
            info = self.info_projet
        source, autres = self._plans_au_titre_final(info)
        final = self._titre_etape("avec_apports")
        if source:
            self._signaler(
                "Calage non lancé",
                f"Le plan de référence p{source} s'appelle déjà « {final} », le "
                "titre du plan final. Choisissez un autre préfixe (étape "
                "Paramètres), ou renommez ce plan dans HEC-RAS.",
                Qgis.MessageLevel.Warning, duree=15)
            return False
        if not autres:
            return True
        with sans_sablier(self):
            boite = QMessageBox(self)
            boite.setWindowTitle("Un plan porte déjà ce nom")
            boite.setIcon(QMessageBox.Icon.Question)
            boite.setText(
                f"<b>Remplacer le plan p{', p'.join(autres)} « "
                f"{html.escape(final)} » à la fin du calage ?</b><br><br>"
                "<b>Perdu</b> : ce plan et ses résultats.<br>"
                "<b>Gardé</b> : le plan de référence et tous les autres plans."
                "<br><br>Pour garder ce plan, annulez, puis changez le préfixe "
                "ou renommez le plan dans HEC-RAS.")
            boite.addButton("Remplacer à la fin du calage",
                            QMessageBox.ButtonRole.AcceptRole)
            bouton_annuler = boite.addButton(
                "Annuler", QMessageBox.ButtonRole.RejectRole)
            boite.setDefaultButton(bouton_annuler)
            boite.exec()
            clique = boite.clickedButton()
        # AUCUN BOUTON CLIQUE VAUT ANNULER, comme _confirmer_reprise.
        if clique is None or clique is bouton_annuler:
            dire(self.label_lancement, "Lancement annulé.")
            return False
        return True

    def _lancer_calage(self):
        """
        Lance la boucle de calage complete en arriere-plan. Ne bloque JAMAIS
        QGIS : le sous-processus est detache, et le suivi (§ 4.3) est le
        moyen normal de savoir ou en est le calcul pendant qu'il tourne.
        """
        if self._installation_occupe():
            return
        if not self.classeur:
            self._signaler("Calage", "Composer d'abord le paquet (bouton "
                           f"« {BOUTON_GEOMETRIE} », étape Paramètres).",
                           Qgis.MessageLevel.Warning)
            return
        # UN « ! » ALLUME REFUSE LE LANCEMENT (24/09/2026, demande
        # utilisateur). Le paquet ne se recompose plus tout seul : un reglage
        # change apres coup y resterait a son ancienne valeur, et le calage,
        # qui lit le paquet, partirait des heures sur autre chose que l'ecran.
        ecarts = self._ecarts_avec_le_paquet()
        if ecarts:
            self._signaler(
                "Calage non lancé",
                f"{compte(len(ecarts), 'réglage changé', 'réglages changés')} depuis la composition "
                "(« ! » rouge) : "
                + ", ".join(e.split(" : ", 1)[0] for e in ecarts.values())
                + f". Cliquer « {BOUTON_GEOMETRIE} » (étape Paramètres) pour "
                  "les reporter, puis relancer.",
                Qgis.MessageLevel.Warning, duree=15)
            return
        if not self._confirmer_malgre_calage(
                "Lancer maintenant ferait travailler deux calages sur les "
                "mêmes plans du même modèle, et le second écraserait les "
                "étapes du premier.", geste="Lancer"):
            return
        # CE QU'UN RELANCEMENT PERD — la question qui manquait. Elle ne se
        # pose que s'il y a quelque chose a perdre, et elle POSE le depart
        # quand on le lui demande : elle passe donc avant l'ecriture des
        # reglages, qui emporte « Premier_apport » dans le classeur.
        if not self._accepter_plan_final() or not self._confirmer_reprise():
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
            # MEME RAISON pour le prefixe : c'est le classeur que le pont lit,
            # et un prefixe modifie apres la composition y resterait perime.
            noyau.ecrire_parametre(
                self.classeur, "Prefixe_scenario",
                self.edit_prefixe_scenario.text().strip())
            # ET LES OBJECTIFS DE PRECISION, POUR LA MEME RAISON. Ils ne
            # partaient dans le classeur qu'a la COMPOSITION : les resserrer
            # ensuite n'avait aucun effet, la chaine lisant le classeur et non
            # la fenetre. On voyait « +/-2 % » a l'ecran et le calage
            # s'arretait a 5 %.
            #   La reprise d'un classeur, qui relisait ces valeurs dans l'autre
            # sens, n'existe plus depuis le 24/09/2026 : « Importer des
            # hydrogrammes d'un calcul precedent » n'apporte que les cibles et
            # les pentes, jamais les reglages.
            for cle, valeur in (
                    ("Tolerance_volume_pct", self.spin_tol_volume.value()),
                    ("Tolerance_pic_pct", self.spin_tol_pic.value()),
                    ("Bilan_masse_max_pct", self.spin_bilan_masse.value()),
                    ("Nb_max_iterations_par_apport",
                     self.spin_nb_max_essais.value()),
                    # 0 = plan inchange ; sinon la suggestion du poste, cochee.
                    ("Coeurs_par_calcul", self._coeurs_demandes()),
                    # LA CASE D'ELAGAGE VIT A L'ETAPE LANCER, et n'etait
                    # ecrite qu'a la composition : cochee ensuite, elle etait
                    # ignoree sans un mot (24/09/2026).
                    ("Elaguer_plans_etape",
                     "oui" if self.case_elaguer.isChecked() else "non")):
                noyau.ecrire_parametre(self.classeur, cle, valeur)
        except Exception as e:
            journaliser("Écriture des paramètres de lancement", e)
            QMessageBox.critical(
                self, "Réglages de lancement",
                f"Les réglages de lancement n'ont pas pu être écrits dans le "
                f"classeur : {e}\n\nLe calage n'est pas lancé — il serait "
                f"parti sur un réglage autre que celui affiché.")
            return
        # UN REFUS, PAS UNE QUESTION. « Lancer quand même (les apports
        # concernés seront ignorés) ? » etait faux : la chaine REFUSE tout le
        # classeur des qu'une seule cible manque (pont_hecras, commande_caler).
        # Repondre oui annoncait « Calage lancé (PID …) », l'onglet Suivi
        # restait a « Aucun calage suivi » pour toujours, et le refus ne vivait
        # que dans le journal de lancement — la mise en scene meme du
        # 04/09/2026.
        if etat["manquantes"]:
            # Une boite que l'on LIT, et la methode s'arrete apres : le sablier
            # se retire, il ne se suspend pas (convention rendre_la_main).
            rendre_la_main(self)
            QMessageBox.warning(
                self, "Hydrogrammes cibles incomplets",
                f"{compte(len(etat['manquantes']), 'section')} sur {etat['total']} "
                f"sans hydrogramme cible exploitable : "
                f"{', '.join(etat['manquantes'])}.\n\n"
                f"Le calage n'est pas lancé : la chaîne refuse un classeur "
                f"incomplet, elle n'ignore pas les apports concernés. "
                f"Compléter la feuille « Cibles » — une colonne « Temps_h » "
                f"et au moins deux instants en face des débits — puis "
                f"relancer.")
            return
        # HEC-RAS OUVERT : ON REFUSE (0.8.4, demande utilisateur).
        #
        # La 0.7.24 posait une QUESTION, au motif que l'interface peut etre
        # ouverte sur un AUTRE projet et que tasklist ne dit que « Ras.exe
        # tourne ». La question a ete essayee, et le texte qui la portait
        # etait trop long pour etre lu au moment ou l'on veut lancer : on
        # repondait « Oui ». Le calage partait, et s'arretait 218 s plus tard
        # sur un calcul de reference sans resultats (09/09/2026).
        #
        # UN SEUL BOUTON, « Ok ». Il n'y a rien a arbitrer : fermer HEC-RAS
        # coute quelques secondes, le laisser ouvert coute le calage et peut
        # abimer le modele. Le cas legitime — HEC-RAS ouvert sur un AUTRE
        # projet — se regle en le fermant lui aussi.
        #
        # « None » N'ARRETE RIEN : hors de Windows, ou si tasklist est
        # indisponible, on ne sait pas, et refuser sur une ignorance
        # bloquerait un lancement valide.
        if noyau.hecras_ouvert() is True:
            with sans_sablier(self):
                QMessageBox.warning(
                    self, "HEC-RAS est ouvert",
                    "HEC-RAS est ouvert sur ce poste. Ce n'est pas permis "
                    "par le plugin. Fermer HEC-RAS et relancer le calage.",
                    QMessageBox.StandardButton.Ok)
            dire(self.label_lancement,
                 "Lancement refusé — fermer HEC-RAS, puis relancer.")
            return
        try:
            info = noyau.lancer_calage(self.classeur)
        except Exception as e:
            journaliser("Lancement du calage", e)
            QMessageBox.critical(self, "Lancement du calage", str(e))
            return
        # ON RETIENT LE LANCEMENT — voir le commentaire de pid_lance. Sans
        # cela, ces deux valeurs ne vivaient que le temps d'une boite
        # d'information, et trois affichages mentaient ensuite faute d'elles.
        self.pid_lance = info.get("pid")
        self.journal_lance = info.get("journal")
        self.instant_lance = datetime.now()
        # LIBELLES : « Échec au démarrage : <chemin> » se lisait comme une
        # annonce d'échec alors que le calage venait de partir. Un chemin ne
        # doit jamais être introduit par un mot qui décrit un état.
        message = (
            f"Calage lancé en arrière-plan (processus {info['pid']}).\n"
            f"Suivre l'avancement à l'étape « 4. Suivi », qui se rafraîchit "
            f"toute seule quand elle est affichée.\n"
            f"Journal de lancement : {info['journal']}")
        dire(self.label_lancement, message)
        # PLUS DE BASCULE VERS LE SUIVI (24/09/2026, demande utilisateur) : la
        # fenetre reste ou l'on est ; « Consulter le suivi », a cote du bouton
        # de lancement, et le lien du fil conducteur y menent.
        self._signaler("Calage lancé", "Le calcul tourne en arrière-plan ; "
                       "l'étape Suivi montre son avancement.",
                       Qgis.MessageLevel.Success, 12)

    def _rendre_compte_du_controle(self, titre, anomalies, tableau,
                                   prolongation, avant="", apres=""):
        """
        La boite de compte rendu d'un controle — la meme pour ses deux
        appelants, la composition d'un paquet et le recontrole d'un classeur.

        Chacun construisait la sienne, et elles avaient deja diverge : seule
        la composition appelait rendre_redimensionnable(). Le recontrole
        presentait donc le tableau des PK par une lucarne de quelques lignes —
        exactement ce que cette fonction existe pour eviter, et le motif pour
        lequel elle a ete ecrite. L'audit du 31/08 avait laisse cette coupe de
        cote (« cinq lignes communes, le gain ne paie pas le risque ») ; la
        divergence a tranche.

        avant / apres : ce que l'appelant met autour du decompte
        « N erreur(s), M avertissement(s) », qui reste au centre.
        """
        erreurs, avertissements, _ = trier_anomalies(anomalies)
        boite = QMessageBox(self)
        boite.setWindowTitle(titre)
        boite.setIcon(QMessageBox.Icon.Critical if erreurs
                      else QMessageBox.Icon.Information)
        boite.setText(f"{avant}{compte(len(erreurs), 'erreur')}, "
                      f"{compte(len(avertissements), 'avertissement')}{apres}")
        boite.setDetailedText(texte_rapport_controle(anomalies, tableau))
        rendre_redimensionnable(boite)
        # Le travail est fini : le compte rendu se lit sans sablier.
        rendre_la_main(self)
        boite.exec()
        self._proposer_prolongation(prolongation)

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
            accepte = confirmer(
                self, "Hydrogrammes cibles trop courts",
                f"{compte(len(apports), 'hydrogramme cible s’arrête', 'hydrogrammes cibles s’arrêtent')} avant la "
                f"fin de la simulation ({nombre(duree, 2)} h) : "
                f"{', '.join(apports[:8])}"
                + ("…" if len(apports) > 8 else "")
                + f".\n\nHEC-RAS refuserait de calculer.\n\n"
                f"Prolonger ces colonnes jusqu'à {nombre(duree, 2)} h en les "
                f"complétant par des ZÉROS ?\n\n"
                f"Une crue arrêtée avant la fin de sa fenêtre est retombée : "
                f"zéro est la valeur juste, et non la dernière connue. Seule "
                f"la feuille Cibles du classeur est modifiée.",
                oui="Prolonger par des zéros", non="Laisser tel quel")
        if not accepte:
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
        self._signaler(
            "Prolongation",
            f"{bilan['ajoutees']} pas de temps ajoutés à "
            f"{compte(len(bilan['colonnes']), 'colonne')}, de "
            f"{nombre(bilan['duree_avant_h'], 2)} h à {nombre(bilan['duree_apres_h'], 2)} h, "
            f"au pas de {format(60 * bilan['pas_h'], 'g').replace('.', ',')} min. Cliquer de nouveau "
            f"« {BOUTON_GEOMETRIE} » (étape Paramètres) pour vérifier.", Qgis.MessageLevel.Success, 0)

    def _ouvrir_classeur(self):
        if not self.classeur:
            self._signaler("Excel", "Aucun Excel pour l'instant : cliquer "
                           f"« {BOUTON_GEOMETRIE} », sous le préfixe "
                           "(étape Paramètres).",
                           Qgis.MessageLevel.Warning)
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
        texte = (f"{compte(len(paires), 'apport à caler, apparié', 'apports à caler, appariés')} à leur section : "
                 + ", ".join(f"{a} → {s}" for a, s in paires[:6])
                 + ("…" if len(paires) > 6 else ""))
        if hors:
            texte += (f"\n{compte(len(hors), 'ligne d’injection non calée', 'lignes d’injection non calées')}, faute "
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
            journaliser("État des cibles (étape Lancer)", e)
            self.label_validation_cibles.setText(f"(illisible : {e})")
            self._cibles_manquantes = None
            return

        self.label_validation_cibles.setText(
            f"{etat['renseignees']} / {compte(etat['total'], 'section')} déjà "
            f"{'renseignée' if etat['renseignees'] < 2 else 'renseignées'}"
            + (f" — manquent : {', '.join(etat['manquantes'])}"
               if etat["manquantes"] else ""))

        self._maj_resume_cibles()

        self._cibles_manquantes = list(etat["manquantes"])
        if hasattr(self, "label_fil"):
            self._maj_fil()                 # le fil appelle _maj_coherence
        else:
            self._maj_coherence()
        # PLUS DE BASCULE VERS LANCER apres la composition (24/09/2026, demande
        # utilisateur) : on reste sur l'etape du bouton, ou se lit le compte
        # rendu.

    # --- resume, mis a jour a chaque changement pertinent -------------------

    def _maj_alerte_couches(self):
        """
        Dit quand les couches a l'ecran ne viennent plus de la geometrie
        retenue.

        _changer_plan ne touche ni combo_zone_2d ni crs_modele. Ce ne sont
        pourtant pas des comptes rendus dates comme label_couches : ce sont
        des valeurs COURANTES, presentees comme telles au resume et
        consommees a l'ecriture. Apres un changement de plan — ou de la
        geometrie de surcharge — elles decrivent une AUTRE geometrie, et rien
        ne le disait.

        ON COMPARE DEUX NUMEROS DEJA EN MEMOIRE, on ne controle rien : le
        plugin n'ecrit aucune regle de controle, c'est la chaine qui les
        porte. Cocher « Choisir une geometrie differente » ne suffit d'ailleurs
        pas a desynchroniser — _maj_mode_override preselectionne celle du plan.
        """
        if getattr(self, "label_geom_couches", None) is None:
            return
        if self.geom_couches is None:
            dire(self.label_geom_couches, "")
            return
        courante = self._geometrie_effective()
        if courante and courante != self.geom_couches:
            dire(self.label_geom_couches,
                 f"<span style='color:{ISL_ROUGE}'>⚠ Les couches affichées "
                 f"viennent de la géométrie g{self.geom_couches}, la "
                 f"géométrie retenue est maintenant g{courante} — zone 2D et "
                 f"système de coordonnées datent de l'ancienne. Recharger les "
                 f"couches du modèle.</span>")
        else:
            dire(self.label_geom_couches, "")

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
        self._maj_alerte_couches()
        try:
            # Les apports de la couche chargee comptent dans les titres.
            self._dire_titres_prefixe()
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
                          f"  ({self.edit_projet_hecras.text()})")
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
                          f"{compte(c_sections.featureCount(), 'entité')}")
        if c_injections is not None:
            lignes.append(f"Lignes d'injection : "
                          f"{compte(c_injections.featureCount(), 'entité')}")

        axe = couche_vivante(
            self.combo_axe.currentLayer() if hasattr(self, "combo_axe") else None)
        # MEME NOM QUE L'ENCADRE QUI LE PORTE (0.7.20) : l'onglet 1 dit
        # « Profil en long », le resume disait « Axe hydraulique » — deux noms
        # pour un seul objet, a deux ecrans d'intervalle.
        lignes.append(
            f"Profil en long (axe) : {axe.name() if axe else '(non choisi)'}")

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
        """
        Ecrire dans la geometrie, composer le paquet, controler — dans cet
        ordre. Le bouton sous le prefixe est son SEUL appelant depuis le
        retrait de la recomposition automatique (24/09/2026, demande
        utilisateur) : elle composait les prefixes a demi tapes.
        """
        # UNE SEULE COMPOSITION A LA FOIS. Elle ecrit des shapefiles et un
        # classeur, et traite des evenements Qt en chemin : un second clic
        # arrive pendant la premiere, et re-entrer, c'est deux ecritures
        # concurrentes sur les memes fichiers — constate le 21/09/2026 avec le
        # minuteur d'alors, le processus s'arretait sans trace, code 127.
        if getattr(self, "_composition_en_cours", False):
            return
        self._composition_en_cours = True
        try:
            self._composer_et_controler_interne()
        finally:
            self._composition_en_cours = False

    def _composer_et_controler_interne(self):
        # CE DRAPEAU EXISTE POUR LE MESSAGE D'ECHEC, ET RIEN D'AUTRE.
        # L'enchainement est : ecrire dans la geometrie, PUIS composer, PUIS
        # controler. Tout ce qui echoue apres l'ecriture remonte au meme
        # « except » final, qui n'affichait que le texte de l'erreur : on
        # lisait un echec et l'on concluait que rien n'avait eu lieu, alors
        # que le modele venait d'etre modifie. Le compte rendu de l'ecriture
        # OUVRE desormais la boite de composition : quand elle s'ouvre, il dit
        # ce qui a ete ecrit ; quand elle ne s'ouvre pas, ce drapeau le dit a
        # sa place.
        geometrie_reecrite = False
        # AVANT TOUT LE RESTE : recomposer pendant qu'un calage tourne
        # reecrit la geometrie et le classeur que ce calage est en train de
        # lire. Une question, pas un verrou — voir _confirmer_malgre_calage.
        if not self._confirmer_malgre_calage(
                "Composer maintenant réécrirait la géométrie HEC-RAS et le "
                "classeur que ce calage est en train de lire.",
                geste="Recomposer"):
            return
        try:
            if not self.info_projet:
                raise ValueError(
                    "Étape Modèle : choisir d'abord le fichier .prj du projet "
                    "HEC-RAS (« Choisir le projet… »).")
            plan = self.combo_plan.currentData()
            if plan is None:
                raise ValueError("Étape Modèle : choisir un plan de référence.")
            # LE PREFIXE EST OBLIGATOIRE (0.7.22, demande utilisateur). Vide,
            # il etait admis et rendait les titres d'avant — « sans_apport »,
            # « Apport_A1 ». Deux scenarios cales sur le meme modele portaient
            # alors les MEMES titres, et le second effacait les plans du
            # premier, un par un, en silence. Le prefixe est ce qui rend les
            # deux series etrangeres : le laisser facultatif, c'est laisser la
            # porte ouverte a la seule perte de donnees que cette chaine
            # sache provoquer.
            if not self.edit_prefixe_scenario.text().strip():
                raise ValueError(
                    "Étape Paramètres : renseigner le préfixe de scénario, cours "
                    "d'eau en tête. Il nomme les plans de CE calage — "
                    "« Riviere-Q100 » donne « Riviere-Q100-sans », "
                    "« Riviere-Q100-A1 » et « Riviere-Q100 » —, il nomme aussi "
                    "son Excel — « donnees_calage_Riviere-Q100.xlsx » —, et "
                    "c'est lui qui empêche un second scénario d'effacer les "
                    "plans du premier.")
            c_sections = couche_vivante(self.couche_sections)
            c_injections = couche_vivante(self.couche_injections)
            if c_sections is None or c_injections is None:
                raise ValueError(
                    "Étape Modèle : cliquer sur « Charger les couches du modèle » "
                    "avant de composer. Si elles avaient été chargées, c'est "
                    "qu'elles ont été retirées du projet depuis — les "
                    "recharger.")
            axe = self.combo_axe.currentLayer()
            if axe is None:
                raise ValueError(
                    # L'axe a rejoint l'onglet 1 en 0.7.0, avec les couches ou
                    # il se trace ; ce renvoi etait reste sur l'onglet 2.
                    "Étape Modèle : choisir la couche de l'axe hydraulique.")
            dossier_sortie = self.edit_dossier_sortie.text().strip()
            if not dossier_sortie:
                raise ValueError("Étape Paramètres : choisir le dossier de "
                                 "sortie, juste au-dessus du préfixe.")

            # Ecrit les couches QGIS dans la geometrie HEC-RAS AVANT de
            # composer le paquet : les sections doivent etre DANS le modele
            # pour que le calage ait un endroit ou lire un debit. Onglet 1,
            # ex-bouton « Ecrire dans la geometrie » — desormais automatique
            # a chaque composition, en mode remplacement systematique.
            # L'ECHEC REMONTE TEL QUEL au « except » final, qui l'affiche :
            # le doubler dans un label de l'onglet 1 n'ajoutait rien, et
            # c'est ce label qui vient d'etre retire.
            compte_rendu_ecriture = self._ecrire_dans_geometrie()
            # Pose APRES la ligne ci-dessus : un echec de l'ecriture elle-meme
            # ne doit pas heriter du message « deja reecrite ».
            geometrie_reecrite = True

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
                dossier_projet=self._dossier_projet(),
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
                prefixe_scenario=self.edit_prefixe_scenario.text().strip(),
                elaguer_etapes=self.case_elaguer.isChecked(),
                sens_axe=self.combo_sens_axe.currentData(),
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
            etiqueter_pk_sur_carte(self.paquet, parametres["Sens_axe"],
                                   {"sections": self.couche_sections,
                                    "apports": self.couche_injections})

            # LA BOITE PORTE LE NOM DU BOUTON (0.8.5) : « Composition et
            # controle » puis « Composition » pour un geste que la fenetre
            # appelle « Controle parametrage », c'etait trois noms pour une
            # chose — la regle de la 0.7.14, en sens inverse.
            self._rendre_compte_du_controle(
                f"{BOUTON_GEOMETRIE} — compte rendu", anomalies, tableau,
                prolongation,
                avant=f"{compte_rendu_ecriture}\n\n"
                      f"Paquet composé dans {dossier_sortie}\n",
                apres=(f"\nPente des apports : {len(pentes)}/"
                       f"{len(self.appariement['paires'])} "
                       f"{'pré-remplie' if len(pentes) < 2 else 'pré-remplies'}"
                       + (f" — {motif_pentes}" if motif_pentes else "")))
            self._maj_resume()
            self._maj_onglet_validation()
        except Exception as e:
            journaliser("Composition et contrôle du paquet", e)
            QMessageBox.critical(
                self, f"{BOUTON_GEOMETRIE} — échec",
                str(e) + ("\n\nLa géométrie HEC-RAS a DÉJÀ été réécrite : "
                          "les sections et injections de l'étape 1 y sont, "
                          "et l'échec ci-dessus est survenu après. Une "
                          "sauvegarde horodatée du fichier de géométrie a été "
                          "faite avant l'écriture."
                          if geometrie_reecrite else ""))


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------

class PluginCalage:
    """Extension « Calage des apports » : une entree de menu et un bouton dans
    la barre « CPN »."""

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
        # dans le modele precede la composition du paquet. Texte choisi par
        # l'ingenieur le 23/10/2026 pour le bouton de la barre \u00ab CPN \u00bb.
        action = QAction(icone, "Calage apports",
                         self.iface.mainWindow())
        action.setObjectName("calageApports_fenetre")
        infobulle = ("Fen\u00eatre unique : mod\u00e8le HEC-RAS, \u00e9criture des "
                     "sections et des apports, profil en long, paramètres, "
                     "lancement, suivi du calage et aide.")
        action.setToolTip(infobulle)
        action.setStatusTip(infobulle)
        action.triggered.connect(self.composer)
        self.iface.addPluginToVectorMenu(self.menu, action)
        self.actions.append(action)
        # Le bouton va dans la barre « CPN », commune aux extensions de la
        # maison (23/10/2026).
        cpn.ajouter(self.iface, action)

    def unload(self):
        """
        Defait ce que initGui a fait — l'essentiel, sinon tout.

        LE BOUTON : cpn.retirer() l'enleve de la barre « CPN » ; la derniere
        extension dechargee retire la barre et sa case du menu Vue > Barres
        d'outils (lecon d'ici, reportee dans cpn.py).

        LA FENETRE D'ABORD. Elle est NON MODALE et conservee d'une ouverture a
        l'autre : la fermer ne la detruit pas. Elle survivait donc au
        dechargement, cablee sur un module qui n'existe plus, et son premier
        clic executait du code decharge. C'est le scenario ordinaire du
        developpement avec Plugin Reloader.

        LE CHEMIN D'IMPORT ENFIN : noyau l'a modifie des son import, il n'y a
        pas de raison de le laisser modifie apres.
        """
        fenetre = getattr(self, "fenetre", None)
        if fenetre is not None:
            fenetre._detacher_installation()
            try:
                fenetre.close()
            except RuntimeError:
                pass                     # objet Qt deja detruit cote C++
            self.fenetre = None

        for action in self.actions:
            self.iface.removePluginVectorMenu(self.menu, action)
            cpn.retirer(self.iface, action)
        self.actions = []

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
        # TAILLE ET POSITION RETENUES D'UNE SESSION A L'AUTRE (0.8.2) : QGIS
        # les sauve a la fermeture et les restaure a l'ouverture. Pose ICI,
        # pas dans le constructeur : le banc et les captures construisent la
        # fenetre directement et ont besoin d'une geometrie deterministe.
        QgsGui.enableAutoGeometryRestore(self.fenetre, "calage_apports/fenetre")
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
