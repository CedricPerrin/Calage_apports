# -*- coding: utf-8 -*-
"""
Exercice de la fenetre du plugin, de bout en bout, SANS interface graphique.

Les boites de dialogue sont remplacees par des reponses programmees (actions
2 a 4, restees a base de QInputDialog/QFileDialog), et l'objet iface par un
mannequin. Le code reellement execute est celui du plugin : c'est la seule
maniere de savoir si les actions fonctionnent avant de les cliquer.

L'action 1 (fenetre de parametrage a six onglets) est construite DIRECTEMENT,
sans passer par PluginCalage.composer(), qui appelle un vrai .exec() : en
tete headless, un .exec() reel bloque indefiniment le process (deux
executions de ce test s'y sont bloquees avant que ceci ne soit corrige — voir
le commentaire au-dessus de la section correspondante).

Ne teste pas l'apparence, mais l'enchainement — c'est la ou se logent les
fautes de frappe et les variables oubliees.

A LANCER AVEC LE PYTHON DE QGIS, jamais avec celui de la chaine :

    "C:\\Program Files\\QGIS\\LTR\\bin\\python-qgis-ltr.bat" test_plugin_qgis.py

Les etapes qui touchent a un modele sont ignorees si aucun modele n'est
fourni. Pour les activer sur un autre modele que celui par defaut :

    ... test_plugin_qgis.py --plan <plan.hdf> --geometrie <modele.gXX>
                            --objet <nom d'une condition limite>
"""

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

# ORDRE IMPOSE : qgis.core avant tout le reste. Charger geopandas d'abord
# casserait le chargement des DLL de qgis._core.
import os  # noqa: E402

from qgis.core import QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, \
    QgsGeometry, QgsField
from qgis.PyQt.QtCore import QMetaType

# QgsApplication.setPrefixPath() DOIT etre appele avant initQgis(), sans quoi
# les greffons providers (dont MDAL, qui lit nativement les maillages
# HEC-RAS) ne sont pas trouves et QgsMeshLayer(...) echoue silencieusement.
# Une vraie session QGIS le fait automatiquement au demarrage ; un
# QgsApplication construit a la main pour un test headless doit le faire lui
# meme. Omis dans une premiere version de ce test, ce qui avait fait
# conclure a tort que MDAL etait absent de cette installation.
def _prefixe_qgis():
    r"""
    Le prefixe de l'installation QGIS qui EXECUTE ce banc, pas un chemin
    espere.

    Le defaut ecrit ici etait « C:\Program Files\QGIS\LTR\apps\qgis-ltr ».
    Il ne vaut que pour une installation nommee « QGIS\LTR » : sur un poste
    ou QGIS s'installe sous son numero de version — « QGIS 3.44.14 », ce que
    fait l'installeur OSGeo par defaut — il n'existe pas, MDAL n'est pas
    trouve, et QgsMeshLayer echoue en silence. C'est le meme motif que les
    six autres defauts de ce banc : supposer le poste de son auteur.

    On part donc de l'interpreteur qui tourne. sys.prefix vaut
    « <installation>\apps\Python312 » ; le prefixe QGIS est son voisin,
    « qgis-ltr » sur une LTR, « qgis » sinon.
    """
    declare = os.environ.get("QGIS_PREFIX_PATH")
    if declare and Path(declare).is_dir():
        return declare
    apps = Path(sys.prefix).parent
    for nom in ("qgis-ltr", "qgis"):
        if (apps / nom).is_dir():
            return str(apps / nom)
    return r"C:\Program Files\QGIS\LTR\apps\qgis-ltr"


_PREFIXE_QGIS = _prefixe_qgis()
QgsApplication.setPrefixPath(_PREFIXE_QGIS, True)

CHAINE = Path(__file__).resolve().parent
RACINE = CHAINE.parent  # calage_apports/ est un sibling de src/, pas de ce fichier
SCRATCH = Path(tempfile.gettempdir()) / "calage_test_plugin"
ESSAI = SCRATCH / "essai_dialogues"

# AUCUN MODELE PAR DEFAUT.
#
# Ces essais ECRIVENT dans la geometrie qu'on leur designe. Tant qu'un modele
# reel figurait ici en valeur par defaut, lancer la suite sans argument
# modifiait ce modele : une execution a supprime les regions de Manning d'un
# projet de production. Sans declaration explicite, les essais qui ecrivent
# sont ignores.
_analyseur = argparse.ArgumentParser(add_help=True)
_analyseur.add_argument("--modele", default=os.environ.get("CALAGE_MODELE_ESSAI"),
                        help="dossier d'un projet HEC-RAS de TRAVAIL, jamais "
                             "de production : sa geometrie sera modifiee")
_analyseur.add_argument("--plan", default=None,
                        help="plan .pXX.hdf dont relire un hydrogramme")
_analyseur.add_argument("--geometrie", default=None,
                        help="geometrie .gXX ; deduite de --modele si omise")
_analyseur.add_argument("--objet", default=None,
                        help="condition limite dont relire l'hydrogramme")
_args = _analyseur.parse_args()


def _premier(dossier, motif):
    if dossier is None:
        return None
    return next(iter(sorted(Path(dossier).glob(motif))), None)


MODELE = Path(_args.modele) if _args.modele else None
PLAN = Path(_args.plan) if _args.plan else _premier(MODELE, "*.p[0-9][0-9].hdf")
SOURCE_GEOM = (Path(_args.geometrie) if _args.geometrie
               else _premier(MODELE, "*.g[0-9][0-9]"))
OBJET = _args.objet

print("=" * 74)
print("EXERCICE DES QUATRE ACTIONS DU PLUGIN, SANS INTERFACE")
print("=" * 74)

qgs = QgsApplication([], False)
qgs.initQgis()

# Le plugin utilise des imports relatifs : il doit etre charge comme un
# PAQUET, exactement comme le fait QGIS. L'importer fichier par fichier
# echouerait sur « attempted relative import with no known parent package ».
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "calage_apports", RACINE / "calage_apports" / "__init__.py",
    submodule_search_locations=[str(RACINE / "calage_apports")])
_paquet = importlib.util.module_from_spec(_spec)
sys.modules["calage_apports"] = _paquet
_spec.loader.exec_module(_paquet)

from calage_apports import noyau, plugin as mod_plugin  # noqa: E402

echecs = []


def verifier(libelle, condition, detail=""):  # noqa: D401
    print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
          + (f"  ->  {detail}" if detail else ""))
    if not condition:
        echecs.append(libelle)


# ---------------------------------------------------------------------------
# Mannequins
# ---------------------------------------------------------------------------

class Iface:
    def __init__(self):
        self.menus, self.barres = [], []
        self._fenetre_principale = None
        self._menu_barres = None

    # UNE VRAIE QMainWindow, ET UNE VRAIE QToolBar. Ce mannequin rendait None
    # a mainWindow() et un talon a addToolBar() : la branche removeToolBar()
    # de unload() — le coeur du lot 7 — etait par construction inatteignable,
    # et son unique controle se resumait a « verifier(..., True) ». Avec les
    # vrais objets Qt, le retrait s'execute et se constate.
    def mainWindow(self):  # noqa: N802
        from qgis.PyQt.QtWidgets import QMainWindow
        if self._fenetre_principale is None:
            self._fenetre_principale = QMainWindow()
        return self._fenetre_principale

    # Le plugin se range dans le menu Vecteur, comme QGIS le recommande pour
    # un outil travaillant sur des couches vectorielles.
    def addPluginToVectorMenu(self, menu, action):  # noqa: N802
        self.menus.append(action)

    def removePluginVectorMenu(self, menu, action):  # noqa: N802
        pass

    # UNE VRAIE QToolBar, PARENTEE A LA VRAIE FENETRE PRINCIPALE, comme le
    # fait QGIS. Un talon suffisait tant que unload() se contentait d'un
    # « del » ; il ne suffit plus des lors que le greffon appelle
    # removeToolBar(), qui exige un QToolBar et rien d'autre.
    def addToolBar(self, nom):  # noqa: N802
        from qgis.PyQt.QtWidgets import QMenu, QToolBar
        self.barres.append(nom)
        barre = QToolBar(nom, self.mainWindow())
        self.mainWindow().addToolBar(barre)
        # CE QUE FAIT QGIS EN PLUS, et qu'il faut imiter sous peine d'un essai
        # qui ne prouve rien : QgisApp::addToolBar place le toggleViewAction()
        # de la barre dans son menu « Vue > Barres d'outils ». Un QMainWindow
        # nu ne le fait pas ; le mannequin doit donc le faire lui-meme, sinon
        # l'essai de retrait passerait au vert sans avoir rien retire.
        if self._menu_barres is None:
            self._menu_barres = QMenu("Barres d'outils", self.mainWindow())
            self.mainWindow().menuBar().addMenu(self._menu_barres)
        self._menu_barres.addAction(barre.toggleViewAction())
        return barre


class DialogueTexte:
    """Repond aux QInputDialog dans l'ordre programme."""

    def __init__(self):
        self.reponses_item, self.reponses_texte = [], []
        self.questions = []

    def getItem(self, parent, titre, libelle, choix, i, editable):  # noqa: N802
        self.questions.append(libelle)
        attendu = self.reponses_item.pop(0)
        if attendu not in choix:
            raise AssertionError(
                f"reponse « {attendu} » absente des choix proposes : {choix}")
        return attendu, True

    def getText(self, parent, titre, libelle, text=""):  # noqa: N802
        self.questions.append(libelle)
        return (self.reponses_texte.pop(0) if self.reponses_texte else text), True


class DialogueFichier:
    def __init__(self):
        self.dossiers, self.fichiers = [], []

    def getExistingDirectory(self, parent, titre):  # noqa: N802
        return self.dossiers.pop(0)

    def getOpenFileName(self, parent, titre, depart, filtre):  # noqa: N802
        return self.fichiers.pop(0), filtre


class _BoutonsStandard:
    Yes = 1
    No = 0


class _Icones:
    Critical = Information = Question = Warning = NoIcon = 0


class BoiteMessage:
    Yes = 1
    No = 0
    Critical = Information = Question = 0

    # LE MANNEQUIN N'AVAIT PAS SUIVI LA 0.4.0. Le plugin ecrit desormais ses
    # constantes sous leur forme QUALIFIEE — QMessageBox.StandardButton.Yes —
    # et le talon n'offrait que la forme plate. _diagnostic() y levait donc
    # AttributeError, mais seulement sur un poste OU L'INTERPRETEUR MANQUE :
    # c'est la seule branche qui pose une question. Le banc ne l'atteignait
    # jamais sur le poste de developpement, et l'atteignait toujours ailleurs.
    StandardButton = _BoutonsStandard
    Icon = _Icones

    def __init__(self, parent=None):
        self.detail = ""
        self.redimensionnable = False

    def setWindowTitle(self, t): pass          # noqa: E704, N802
    def setIcon(self, i): pass                 # noqa: E704, N802
    def setText(self, t): self.texte = t       # noqa: E704, N802
    def setDetailedText(self, t): self.detail = t   # noqa: E704, N802
    def exec(self): BoiteMessage.dernier = self     # noqa: E704

    # Les trois suivantes servent rendre_redimensionnable(). La poignee est
    # RETENUE — c'est ce que le test verifie ; la disposition et la zone de
    # detail sont des objets Qt qu'un talon ne peut pas imiter, et la fonction
    # les traite comme absents sans rien casser.
    def setSizeGripEnabled(self, oui): self.redimensionnable = oui  # noqa: E704, N802
    def layout(self): return None              # noqa: E704
    def findChild(self, classe): return None   # noqa: E704, N802

    @staticmethod
    def information(parent, titre, texte):
        BoiteMessage.informations.append(texte)

    @staticmethod
    def critical(parent, titre, texte):
        import traceback
        BoiteMessage.critiques.append(texte)
        trace = traceback.format_exc()
        if "NoneType: None" not in trace:
            BoiteMessage.traces.append(trace)

    @staticmethod
    def question(parent, titre, texte, boutons=None):
        return BoiteMessage.No


BoiteMessage.informations, BoiteMessage.critiques = [], []
BoiteMessage.traces = []

dialogue = DialogueTexte()
fichiers = DialogueFichier()
mod_plugin.QInputDialog = dialogue
mod_plugin.QFileDialog = fichiers
mod_plugin.QMessageBox = BoiteMessage

# ---------------------------------------------------------------------------
# Couches de travail
# ---------------------------------------------------------------------------
import numpy as np  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

if ESSAI.exists():
    shutil.rmtree(ESSAI)
ESSAI.mkdir(parents=True)


def couche(nom, geometries, noms, crs="EPSG:2154"):
    """
    Couche memoire de lignes. LE CRS SE PASSE, il ne se suppose pas.

    Le defaut Lambert-93 convient aux geometries inventees par ce banc, dont
    les coordonnees sont ecrites pour la France. Il ne convient PAS a une
    couche batie sur les coordonnees REELLES d'un modele : declarees dans le
    mauvais systeme, elles sortent de son domaine de validite et la
    reprojection rend des valeurs non finies — « Coordinates with non-finite
    values are not allowed », sur l'exemple Muncie qui est dans l'Indiana
    (releve le 06/09/2026). L'axe hydraulique se construit donc dans le CRS
    du modele, que la fenetre connait.
    """
    c = QgsVectorLayer(f"LineString?crs={crs}", nom, "memory")
    c.dataProvider().addAttributes([QgsField("nom", QMetaType.Type.QString)])
    c.updateFields()
    entites = []
    for g, n in zip(geometries, noms):
        e = QgsFeature(c.fields())
        e.setGeometry(QgsGeometry.fromWkt(g.wkt))
        e["nom"] = n
        entites.append(e)
    c.dataProvider().addFeatures(entites)
    c.updateExtents()
    QgsProject.instance().addMapLayer(c)
    return c


xs = np.linspace(0, 8000, 60)
axe_geom = LineString(zip(500000 + xs, 6200000 + 300 * np.sin(xs / 1400)))
couche("Axe", [axe_geom], ["Axe"])

# ---------------------------------------------------------------------------
# Chargement du plugin
# ---------------------------------------------------------------------------
print("\n1. CHARGEMENT")
disponible, messages = noyau.chaine_disponible()
verifier("chaine de calage joignable", disponible, " | ".join(messages))

iface = Iface()
p = mod_plugin.PluginCalage(iface)
p.initGui()
verifier("initGui : une seule entree de menu", len(iface.menus) == 1,
         f"{len(iface.menus)} action(s)")

# ---------------------------------------------------------------------------
# ACTION 1 — fenetre de parametrage (six onglets depuis la 0.5.0 ; le
#            commentaire en annonçait quatre).
#
# PluginCalage.composer() ouvre un QDialog reel et appelle .exec() : en tete
# headless, un .exec() reel ouvre une boucle d'evenements MODALE qui attend
# un clic qui ne vient jamais, et le process reste bloque indefiniment (deux
# executions de ce test s'y sont bloquees avant que ceci ne soit corrige).
# On construit donc directement DialogueParametrage et on appelle ses
# methodes internes SANS jamais appeler .exec() — c'est le meme code que
# celui reellement execute au clic, seule l'ouverture de la fenetre est
# court-circuitee.
# ---------------------------------------------------------------------------
print("\n2. ACTION 1 — FENETRE DE PARAMETRAGE A SIX ONGLETS")
# Construite inconditionnellement : les onglets Suivi et Aide (sections 6 et
# suivantes) ne dependent d'aucun modele, et ne doivent donc pas etre sautes
# faute d'un modele HEC-RAS present sur la machine qui lance ce test.
dlg = mod_plugin.DialogueParametrage(iface)
verifier("6 onglets crees (4 etapes + suivi + aide)",
         dlg.onglets.count() == 6,
         [dlg.onglets.tabText(i) for i in range(dlg.onglets.count())])
if MODELE is None or not MODELE.exists():
    print("   ignore : aucun modele declare "
          "(--modele, ou variable CALAGE_MODELE_ESSAI)")
    p.classeur = None
else:
    dlg.edit_dossier_hecras.setText(str(MODELE))
    dlg._charger_projet_hecras(str(MODELE))
    verifier("projet HEC-RAS detecte", bool(dlg.info_projet),
             dlg.info_projet["nom_projet"] if dlg.info_projet else "")
    # La version n'est plus saisie : elle est lue dans les fichiers du
    # modele, la plus recente l'emportant en cas de melange.
    verifier("version HEC-RAS lue dans le modele, pas saisie",
             bool(dlg.version_hecras)
             and not hasattr(dlg, "edit_version_hecras"),
             f"{dlg.version_hecras} — {dlg.label_nom_projet.text()[:60]}")

    numero_plan = (PLAN.with_suffix("").suffix.lstrip(".p")
                   if PLAN is not None else None)
    index_plan = next((i for i in range(dlg.combo_plan.count())
                       if dlg.combo_plan.itemData(i)["numero"] == numero_plan), 0)
    dlg.combo_plan.setCurrentIndex(index_plan)

    dlg._charger_couches_modele()
    verifier("couches du modele chargees",
             dlg.couche_sections is not None and dlg.couche_injections is not None
             and dlg.couche_perimetre is not None,
             f"sections={dlg.couche_sections.featureCount() if dlg.couche_sections else '?'} "
             f"injections={dlg.couche_injections.featureCount() if dlg.couche_injections else '?'}")
    # SANS COUCHES, TOUT CE QUI SUIT PLANTE — et plantait : la suite s'arretait
    # vingt lignes plus bas sur « NoneType n'a pas d'attribut featureCount »,
    # au lieu de dire ce qui manque. Un banc qui s'effondre n'apprend plus rien
    # de ce qu'il n'a pas encore controle : il rend UN echec la ou il en aurait
    # rendu quatre-vingt-dix-neuf.
    #   LA CAUSE ORDINAIRE EST L'INTERPRETEUR HEC-RAS ABSENT — la lecture de la
    #   geometrie passe par lui. Le greffon ne le trouve seul que si c'est un
    #   .venv voisin de la chaine retenue ; ailleurs il faut le lui designer, et
    #   CALAGE_PYTHON dans l'environnement suffit pour cette suite.
    if dlg.couche_injections is None or dlg.couche_sections is None:
        print("\n   ARRET : sans les couches du modele, aucun des controles "
              "suivants n'a de sens.")
        print("   Le diagnostic de chargement ci-dessus dit pourquoi — un "
              "interpreteur HEC-RAS introuvable suffit a produire ceci.")
        print("   Le designer par CALAGE_PYTHON, ou par le bouton "
              "« Designer… » du greffon.")
        raise SystemExit(1)

    # L'axe et les sections doivent etre COHERENTS avec la geometrie reelle :
    # l'appariement se fait desormais par PK le long de l'axe, et non plus par
    # simple comptage. Un axe pose a plusieurs kilometres du modele, comme
    # dans une version anterieure de ce test, projetait tous les objets au
    # meme endroit et rendait l'appariement absurde.
    #
    # On construit donc l'axe en enfilant les centroides des injections
    # reelles, puis on pose UNE section un peu en aval de chacune : chaque
    # apport a ainsi sa section, ce que le calage exige.
    n_apports = dlg.couche_injections.featureCount()
    centroides = sorted(
        (e.geometry().centroid().asPoint() for e in dlg.couche_injections.getFeatures()),
        key=lambda pt: pt.y())
    if len(centroides) >= 2:
        axe_modele = LineString([(pt.x(), pt.y()) for pt in centroides])
    else:
        # UN SEUL APPORT NE DEFINIT PAS D'AXE, et shapely refuse une
        # LineString a un point : « point array must contain 0 or >1
        # elements ». Le cas est legitime — un modele d'essai minimal porte
        # une ligne d'injection et une ligne de reference — et arretait
        # pourtant toute la suite au sixieme controle (releve le 06/09/2026
        # sur le plan TEST de Muncie). On prolonge donc de part et d'autre du
        # centroide unique, dans le sens que la suite de ce bloc suppose deja
        # (l'axe monte en Y, les sections se posent 30 m au nord).
        _pt = centroides[0]
        axe_modele = LineString([(_pt.x(), _pt.y() - 500),
                                 (_pt.x(), _pt.y() + 500)])
    for c in QgsProject.instance().mapLayersByName("Axe"):
        QgsProject.instance().removeMapLayer(c.id())
    couche("Axe", [axe_modele], ["Axe"], crs=dlg.crs_modele or "EPSG:2154")

    _sections_posees_par_le_test = (dlg.couche_sections.featureCount() == 0
                                    and bool(n_apports))
    if _sections_posees_par_le_test:
        fournisseur = dlg.couche_sections.dataProvider()
        objets = []
        for i, pt in enumerate(centroides):
            # Legerement en aval : l'axe monte en Y, on decale donc vers le
            # nord, en travers (segment est-ouest).
            y = pt.y() + 30
            e = QgsFeature(dlg.couche_sections.fields())
            e.setGeometry(QgsGeometry.fromWkt(
                f"LineString({pt.x() - 250} {y}, {pt.x() + 250} {y})"))
            e["nom"] = f"S_test_{i + 1}"
            objets.append(e)
        fournisseur.addFeatures(objets)
        dlg.couche_sections.updateExtents()
    # UNE SECTION PAR INJECTION N'EST VRAI QUE SI LE TEST LES A POSEES. Un
    # modele reel porte ses propres sections, et toutes ses lignes
    # d'injection ne sont pas des apports a caler : s'y trouvent aussi le
    # debit d'entree et la condition limite aval (« IN », « OUT »). Exiger
    # autant de sections que d'injections revenait a compter ces dernieres
    # comme des apports — precisement ce que noyau.preparer_classeur refuse
    # de faire.
    if _sections_posees_par_le_test:
        verifier("une section posee en aval de chaque injection",
                 dlg.couche_sections.featureCount() == n_apports,
                 f"{dlg.couche_sections.featureCount()} / {n_apports}")
    else:
        verifier("le modele porte deja ses propres sections de controle",
                 dlg.couche_sections.featureCount() > 0,
                 f"{dlg.couche_sections.featureCount()} section(s) pour "
                 f"{n_apports} ligne(s) d'injection")
    verifier("maillage natif QGIS/MDAL charge",
             dlg.couche_maillage is not None and dlg.couche_maillage.isValid(),
             f"{dlg.couche_maillage.datasetGroupCount()} groupe(s) de donnees"
             if dlg.couche_maillage else "absent")

    # L'AXE N'EST PAS CHOISI TANT QUE PERSONNE NE L'A CHOISI. Les couches du
    # modele viennent d'etre chargees, et deux d'entre elles sont des lignes :
    # sans entree vide dans le combo, currentLayer() rendait la premiere, le
    # fil conducteur cochait « Axe hydraulique » pour un geste jamais fait, et
    # le garde-fou qui refuse de composer sans axe etait inatteignable.
    # setAllowEmptyLayer NE SUFFIT PAS — il ajoute l'entree sans la choisir :
    # ce controle tombe si le setLayer(None) qui l'accompagne disparait.
    verifier("l'axe n'est pas pre-choisi par le greffon",
             dlg.combo_axe.currentLayer() is None,
             f"{dlg.combo_axe.currentLayer().name()}"
             if dlg.combo_axe.currentLayer() else "(vide)")
    # ET LE REFUS QUI VA AVEC EST ATTEIGNABLE. Il ne l'etait pas : le combo
    # rendant toujours une couche, cette branche etait morte. Le controle
    # verifie du meme coup qu'elle nomme le BON onglet — l'axe a rejoint
    # l'onglet 1 en 0.7.0, le message etait reste sur l'onglet 2.
    # Sans danger pour le modele : le refus tombe AVANT _ecrire_dans_geometrie.
    BoiteMessage.critiques.clear()
    dlg._composer_et_controler()
    _refus = BoiteMessage.critiques[0] if BoiteMessage.critiques else ""
    verifier("sans axe, la composition refuse et nomme le bon onglet",
             "axe hydraulique" in _refus.lower() and "onglet 1" in _refus.lower(),
             _refus[:90] or "aucun refus — la branche est morte")
    BoiteMessage.critiques.clear()

    dlg.combo_axe.setLayer(QgsProject.instance().mapLayersByName("Axe")[0])
    dlg.edit_dossier_sortie.setText(str(ESSAI))

    dlg._composer_et_controler()
    verifier("aucune erreur remontee", not BoiteMessage.critiques,
             BoiteMessage.critiques[0][:90] if BoiteMessage.critiques else "")
    # Le rapport porte le tableau des PK, plusieurs dizaines de lignes larges :
    # la fenetre qui le presente doit pouvoir s'agrandir.
    _rapport_compo = getattr(BoiteMessage, "dernier", None)
    verifier("« Composition et contrôle » est redimensionnable",
             _rapport_compo is not None and _rapport_compo.redimensionnable,
             "poignée posée" if _rapport_compo else "aucune boîte affichée")
    attendus = ["sections_controle.shp", "lignes_injection.shp",
               "axe_hydraulique.shp", "donnees_calage.xlsx"]
    presents = [f for f in attendus if (ESSAI / f).exists()]
    verifier("paquet ecrit", len(presents) == 4, f"{presents}")
    verifier("sous-dossiers resultats/suivi crees",
             (ESSAI / "resultats_finaux").is_dir() and (ESSAI / "suivi").is_dir())

    if not dlg.classeur:
        # UN MODELE QUI NE SE PRETE PAS AU CALAGE EST UN DIAGNOSTIC, PAS UN
        # PLANTAGE. La composition n'aboutit pas si le modele n'a ni ligne de
        # reference ni ligne d'injection — cas de tout modele HEC-RAS
        # ordinaire, les exemples livres avec le logiciel compris. La ligne
        # suivante appelait alors pd.read_excel(None) et emportait TOUTE la fin
        # de la suite sur un « Invalid file path or buffer object type », la ou
        # il fallait dire quel modele ne convient pas et ce qui lui manque.
        # Releve le 06/09/2026 en pointant la suite sur l'exemple Muncie.
        print(f"   ignore : la composition n'a produit aucun classeur — "
              f"{dlg.couche_sections.featureCount()} section(s) de controle, "
              f"{dlg.couche_injections.featureCount()} ligne(s) d'injection "
              f"dans « {MODELE.name} ». Un modele de calage en demande au "
              f"moins une de chaque.")
        p.classeur = None
    else:
        import pandas as pd  # noqa: E402
        corr = pd.read_excel(dlg.classeur, sheet_name="Correspondance")
        noms_reels_injections = sorted(
            f["nom"] for f in dlg.couche_injections.getFeatures())
        # LES APPORTS DU CLASSEUR SONT UN SOUS-ENSEMBLE DES INJECTIONS, pas
        # leur copie : une injection sans section en aval — debit d'entree,
        # condition limite aval — n'est pas un apport a caler et n'a rien a y
        # faire. Ce qu'il faut verifier, c'est qu'aucun nom n'est invente ni
        # duplique.
        _apports_classeur = sorted(str(n) for n in corr["Nom_Apport (BC line)"])
        verifier("classeur pre-rempli avec les noms reels des injections",
                 _apports_classeur
                 and set(_apports_classeur) <= set(noms_reels_injections)
                 and len(_apports_classeur) == len(set(_apports_classeur)),
                 f"classeur {_apports_classeur} / modele {noms_reels_injections}")
        # L'onglet 4 annonce desormais ce qui est CALE et ce qui ne l'est pas,
        # au lieu de comparer deux nombres qui n'avaient pas a etre egaux.
        verifier("onglet 4 : apports apparies a leur section",
                 "apport(s) à caler" in dlg.label_validation_comptes.text()
                 and "→" in dlg.label_validation_comptes.text(),
                 dlg.label_validation_comptes.text().replace("\n", " | ")[:110])
        # Convention de nommage : les objets sans nom recoivent A1.. / SC1..,
        # sans jamais reprendre un nom deja pris dans le modele.
        _sans_nom = QgsVectorLayer("LineString?crs=EPSG:2154", "SansNom", "memory")
        _sans_nom.dataProvider().addAttributes(
            [QgsField("nom", QMetaType.Type.QString)])
        _sans_nom.updateFields()
        _objets = []
        for _i in range(3):
            _e = QgsFeature(_sans_nom.fields())
            _e.setGeometry(QgsGeometry.fromWkt(
                f"LineString(504000 {6216000 + 50 * _i}, "
                f"504400 {6216000 + 50 * _i})"))
            _e["nom"] = ""
            _objets.append(_e)
        _sans_nom.dataProvider().addFeatures(_objets)
        _g = mod_plugin.couche_vers_gdf(
            _sans_nom, prefixe_defaut=mod_plugin.PREFIXE_APPORT, noms_pris=["A1"])
        verifier("les objets sans nom suivent la convention",
                 list(_g["nom"]) == ["A2", "A3", "A4"], list(_g["nom"]))
        _gs = mod_plugin.couche_vers_gdf(
            _sans_nom, prefixe_defaut=mod_plugin.PREFIXE_SECTION)
        verifier("le prefixe des sections est distinct",
                 list(_gs["nom"]) == ["SC1", "SC2", "SC3"], list(_gs["nom"]))

        verifier("chaque apport cale a bien une section distincte",
                 len({s for _, s in dlg.appariement["paires"]})
                 == len(dlg.appariement["paires"]),
                 f"{len(dlg.appariement['paires'])} paire(s)")

        # Reproduit exactement ce que fait PluginCalage.composer() une fois la
        # fenetre fermee : recuperer classeur/paquet sur l'objet plugin, pour
        # que les actions 2, 3 et 4 continuent d'y acceder ensuite.
        p.classeur, p.paquet = dlg.classeur, dlg.paquet

# ---------------------------------------------------------------------------
# Ces trois fonctions ont quitte le menu pour rejoindre la fenetre : le
# recontrole en onglet 4, la relecture d'hydrogramme en onglet 3, l'aide et
# le diagnostic dans un onglet dedie. Le test les exerce donc la ou elles
# sont desormais, et non plus sur l'objet plugin.
print("\n3. ONGLET 4 — RECONTROLER UN CLASSEUR DEJA COMPOSE")
if dlg is None or not dlg.classeur:
    print("   ignore : aucun classeur compose")
else:
    BoiteMessage.critiques.clear()
    avant = len(QgsProject.instance().mapLayers())
    fichiers.fichiers = [str(dlg.classeur)]
    dlg._recontroler_classeur()
    verifier("aucune erreur remontee", not BoiteMessage.critiques,
             BoiteMessage.critiques[0][:70] if BoiteMessage.critiques else "")
    apres = len(QgsProject.instance().mapLayers())
    verifier("couches de PK ajoutees a la carte", apres > avant,
             f"{avant} -> {apres} couches")
    rapport = getattr(BoiteMessage, "dernier", None)
    verifier("rapport detaille produit",
             rapport is not None and "PK" in rapport.detail,
             (rapport.detail[:70] + "...") if rapport else "aucun")

# ---------------------------------------------------------------------------
print("\n4. ONGLET 3 — RELIRE UN HYDROGRAMME")
if PLAN is None or not PLAN.exists() or not OBJET:
    print("   ignore : aucun plan declare, ou aucune condition limite (--objet)")
else:
    BoiteMessage.critiques.clear()
    fichiers.fichiers = [str(PLAN)]
    dialogue.reponses_item = [f"{OBJET}  (injection)"]
    dlg._relire_hydrogramme()
    verifier("aucune erreur remontee", not BoiteMessage.critiques,
             BoiteMessage.critiques[0][:90] if BoiteMessage.critiques else "")
    verifier("resume affiche dans l'onglet", bool(dlg.label_relecture.text()),
             dlg.label_relecture.text()[:90])

# ---------------------------------------------------------------------------
print("\n5. ECRITURE DANS LA GEOMETRIE — depuis l'onglet 1 de la fenetre")
# Cette etape a rejoint la fenetre de parametrage : elle y dispose deja du
# fichier geometrie, de la zone 2D et de l'Unsteady Flow. Le chemin des
# fichiers etant DEDUIT du projet choisi et non demande, le test doit faire
# pointer la fenetre vers une COPIE du projet — le modele designe n'est
# jamais touche.
copie = None
if (SOURCE_GEOM is None or not SOURCE_GEOM.exists()
        or MODELE is None or not MODELE.exists()):
    print("   ignore : aucun modele declare")
else:
    BoiteMessage.critiques.clear()
    BoiteMessage.informations.clear()

    faux_projet = ESSAI / "copie_projet"
    faux_projet.mkdir(parents=True, exist_ok=True)
    nom_projet = dlg.info_projet["nom_projet"]
    numero_geom = dlg._geometrie_effective()
    numero_unst = dlg._unsteady_effective()
    a_copier = [f"{nom_projet}.prj",
                f"{nom_projet}.g{numero_geom}",
                f"{nom_projet}.g{numero_geom}.hdf",
                f"{nom_projet}.u{numero_unst}"]
    if PLAN is not None:
        a_copier.append(PLAN.with_suffix("").name
                        + PLAN.suffix.replace(".hdf", ""))
    for nom in a_copier:
        src = MODELE / nom
        if src.exists():
            shutil.copy2(src, faux_projet / nom)
    copie = faux_projet / f"{nom_projet}.g{numero_geom}"
    verifier("copie de travail du projet constituee", copie.exists(),
             f"{len(list(faux_projet.iterdir()))} fichier(s)")

    taille = copie.stat().st_size
    # L'ETAT DE LA SOURCE AVANT TOUTE ECRITURE. C'est le seul point de
    # comparaison qui prouve que le projet client n'a pas ete touche :
    # comparer la source a la COPIE ne prouve rien — une ecriture fidele
    # rend justement les deux identiques.
    source_avant = SOURCE_GEOM.read_bytes()
    # Blocs voisins des reference lines. Leur disparition est l'incident du
    # 03/08/2026 : l'ecriture d'une section emportait les blocs suivants
    # quand elle visait la DERNIERE reference line du fichier.
    BLOCS_VOISINS = ("LCMann Region Name=", "LCMann Table=",
                     "Chan Stop Cuts=", "Use User Specified Reach Order=",
                     "GIS Ratio Cuts To Invert=", "GIS Limit At Bridges=",
                     "Composite Channel Slope=")

    def _compter_blocs(chemin):
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        lignes = texte.splitlines()
        compte = {p: sum(l.startswith(p) for l in lignes)
                  for p in BLOCS_VOISINS}
        compte["BC Line Name="] = sum(l.startswith("BC Line Name=")
                                      for l in lignes)
        return compte

    blocs_avant = _compter_blocs(copie)
    import geometrie                                          # noqa: E402
    noms_sections_avant = geometrie.noms_objets_geometrie(copie)["sections"]
    dlg2 = mod_plugin.DialogueParametrage(iface)
    dlg2.edit_dossier_hecras.setText(str(faux_projet))
    dlg2._charger_projet_hecras(str(faux_projet))
    index = next((i for i in range(dlg2.combo_plan.count())
                  if dlg2.combo_plan.itemData(i)["numero"] == numero_plan), 0)
    dlg2.combo_plan.setCurrentIndex(index)
    dlg2._charger_couches_modele()

    verifier("zone 2D renseignee par le chargement",
             bool(dlg2.combo_zone_2d.currentText()),
             dlg2.combo_zone_2d.currentText())
    # Une seule zone dans ce modele : le champ ne doit pas se presenter comme
    # un choix a faire.
    verifier("zone 2D verrouillee quand il n'y en a qu'une",
             not dlg2.combo_zone_2d.isEnabled()
             if dlg2.combo_zone_2d.count() == 1
             else dlg2.combo_zone_2d.isEnabled(),
             f"{dlg2.combo_zone_2d.count()} zone(s), "
             f"active={dlg2.combo_zone_2d.isEnabled()}")
    # Plus aucun champ de forme d'hydrogramme : un apport cree nait a zero,
    # et recoit la forme de la cible au premier essai du calage.
    verifier("aucun champ de forme d'hydrogramme dans l'interface",
             not hasattr(dlg2, "combo_forme_hydro"))

    # LA PENTE EST PAR APPORT, dans le classeur — pas un reglage unique dans
    # le plugin : deux injections sur des troncons differents n'ont aucune
    # raison de partager la meme pente.
    verifier("plus de champ de pente unique dans l'interface",
             not hasattr(dlg2, "spin_pente"))
    verifier("l'hypothese de pente est dite a l'utilisateur",
             "±200 m" in mod_plugin.inspect_source_pente()
             if hasattr(mod_plugin, "inspect_source_pente")
             else "±200 m" in Path(mod_plugin.__file__).read_text(
                 encoding="utf-8"),
             "moyenne sur ±200 m, majorée de 20 %")
    verifier("la precision attendue est saisissable",
             abs(dlg2.spin_tol_volume.value()
                 - 100 * mod_plugin.TOLERANCE_VOLUME_DEFAUT) < 1e-9
             and abs(dlg2.spin_tol_pic.value()
                     - 100 * mod_plugin.TOLERANCE_PIC_DEFAUT) < 1e-9,
             f"volume {dlg2.spin_tol_volume.value()} % / "
             f"pointe {dlg2.spin_tol_pic.value()} %")
    # PREMIER APPORT A CALER : vide par defaut, c'est-a-dire « tous ». Le
    # combo n'est rempli qu'une fois un classeur connu ; a la construction, il
    # ne porte que la ligne « tous », et le reglage doit valoir la chaine vide.
    verifier("le premier apport vaut « tous » par defaut",
             dlg2._premier_apport() == ""
             and dlg2.combo_premier_apport.count() == 1,
             f"{dlg2.combo_premier_apport.count()} entree(s)")
    # ET IL EST LU DANS LA DONNEE DE L'ENTREE, pas decoupe dans son libelle.
    # Le libelle porte « apport → section » : un apport dont le nom contient
    # lui-meme cette fleche rendait faux le nom transmis au classeur, donc le
    # point de reprise du calage.
    dlg2.combo_premier_apport.addItem("A → B → SC1", "A → B")
    dlg2.combo_premier_apport.setCurrentIndex(1)
    verifier("le premier apport est lu dans la donnee, pas dans le libelle",
             dlg2._premier_apport() == "A → B",
             f"{dlg2._premier_apport()!r} pour "
             f"« {dlg2.combo_premier_apport.currentText()} »")
    dlg2.combo_premier_apport.setCurrentIndex(0)

    # --- fenetre de simulation -------------------------------------------
    #
    # Substituer un Unsteady Flow d'une autre periode ne deplace pas la fenetre
    # du plan : le calcul tournerait alors a cote des hydrogrammes, sans que
    # HEC-RAS s'en plaigne. D'ou une saisie, pre-remplie depuis le plan.
    _saisie = dlg2.fenetre_saisie()
    verifier("la fenetre est pre-remplie depuis le plan choisi",
             bool(_saisie["debut"]) and bool(_saisie["fin"]),
             f"{_saisie['debut']} -> {_saisie['fin']}")
    verifier("les intervalles du plan sont repris",
             bool(_saisie["intervalle_calcul"]),
             f"calcul={_saisie['intervalle_calcul']} "
             f"sortie={_saisie['intervalle_sortie']}")
    verifier("une fenetre non touchee n'est pas signalee comme modifiee",
             not dlg2._fenetre_modifiee())

    # Le format sans deux-points est celui qu'ecrit l'interface HEC-RAS 6.41 :
    # le plugin doit le relire sans le prendre pour une faute de saisie.
    dlg2._maj_resume()
    verifier("une fenetre du plan ne declenche aucune alerte",
             "⚠" not in dlg2.label_fenetre.text(),
             dlg2.label_fenetre.text()[:70])

    # LA FIN MODIFIEE SE DERIVE DU PLAN, elle ne se code pas en dur. Une date
    # fixe (« 15OCT2014 ») n'est posterieure au debut que pour le modele
    # d'essai qui a servi a ecrire ce test : sur tout modele dont la
    # simulation est plus recente, elle produit une fenetre INVERSEE, et le
    # test echouait sur une alerte parfaitement justifiee.
    _date_fin = dlg2.edit_sim_fin.text().split(",")[0]
    _heure_autre = ("22:00" if dlg2.edit_sim_fin.text().endswith("23:00")
                    else "23:00")
    dlg2.edit_sim_fin.setText(f"{_date_fin},{_heure_autre}")
    verifier("une fenetre modifiee est detectee", dlg2._fenetre_modifiee())
    dlg2._maj_resume()
    verifier("la modification est annoncee, sans alerte",
             "⚠" not in dlg2.label_fenetre.text()
             and "modifiée" in dlg2.label_fenetre.text(),
             dlg2.label_fenetre.text()[:70])

    dlg2.edit_sim_fin.setText("15/10/2014 06:00")
    dlg2._maj_resume()
    verifier("une date au format francais est signalee tout de suite",
             "⚠" in dlg2.label_fenetre.text(),
             dlg2.label_fenetre.text()[:90])

    # LA FENETRE INVERSEE SE DERIVE AUSSI DU PLAN. Ce test portait
    # « 12OCT2014 », c'est-a-dire la meme faute que le paragraphe ci-dessus
    # denonce, deux lignes plus bas : la date n'est ANTERIEURE au debut que
    # pour le modele qui a servi a ecrire le test. Sur l'exemple Muncie, qui
    # simule le 02JAN1900, elle lui est posterieure — la fenetre n'est donc
    # pas inversee, le greffon a raison de ne rien signaler, et le test
    # echouait sur son silence parfaitement justifie (releve le 06/09/2026).
    # On recule d'un an sur la date de DEBUT : anterieure sur tout modele.
    _jour_debut, _, _heure_debut = dlg2.edit_sim_debut.text().partition(",")
    _avant = f"{_jour_debut[:5]}{int(_jour_debut[5:]) - 1:04d}"
    dlg2.edit_sim_fin.setText(f"{_avant},{_heure_debut or '00:00'}")
    dlg2._maj_resume()
    verifier("une fenetre inversee est signalee",
             "⚠" in dlg2.label_fenetre.text(),
             f"fin={dlg2.edit_sim_fin.text()} < debut="
             f"{dlg2.edit_sim_debut.text()} | "
             f"{dlg2.label_fenetre.text()[:60]}")

    dlg2._remplir_fenetre_depuis_plan()
    verifier("changer de plan reprend la fenetre de ce plan",
             not dlg2._fenetre_modifiee())

    # Une couche retiree du projet pendant que la fenetre est ouverte ne doit
    # plus faire planter : c'est devenu possible depuis qu'elle n'est plus
    # modale.
    _morte = QgsVectorLayer("LineString?crs=EPSG:2154", "AJeter", "memory")
    QgsProject.instance().addMapLayer(_morte)
    QgsProject.instance().removeMapLayer(_morte.id())
    verifier("une couche supprimee est detectee, pas touchee",
             mod_plugin.couche_vivante(_morte) is None)
    verifier("une couche vivante est bien reconnue",
             mod_plugin.couche_vivante(dlg2.couche_injections) is not None)

    # Reproduit la situation reelle : les couches du modele sont retirees du
    # projet alors que la fenetre est ouverte, puis un signal declenche le
    # rafraichissement. Aucune trace ne doit remonter dans le journal QGIS.
    _dlg3 = mod_plugin.DialogueParametrage(iface)
    _dlg3.edit_dossier_hecras.setText(str(faux_projet))
    _dlg3._charger_projet_hecras(str(faux_projet))
    _dlg3.combo_plan.setCurrentIndex(index)
    _dlg3._charger_couches_modele()
    for _c in (_dlg3.couche_sections, _dlg3.couche_injections,
               _dlg3.couche_perimetre):
        if _c is not None:
            QgsProject.instance().removeMapLayer(_c.id())
    _plante = False
    try:
        _dlg3._maj_resume()
        _dlg3._maj_fil()
    except RuntimeError as _e:
        _plante = True
    verifier("couches detruites pendant que la fenetre est ouverte : "
             "aucun plantage", not _plante)
    verifier("le resume reste renseigne malgre les couches perdues",
             bool(_dlg3.texte_resume.toPlainText()),
             _dlg3.texte_resume.toPlainText().replace("\n", " | ")[:70])
    _dlg3.close()

    # Couches non chargees : l'ecriture doit etre refusee, pas silencieuse.
    # _ecrire_dans_geometrie() LEVE desormais une exception plutot que
    # d'afficher elle-meme une boite de message — cet affichage est a la
    # charge de l'appelant, _composer_et_controler — donc le test la capture
    # lui-meme. Il n'y a plus de combo separe a vider : la seule source
    # possible est self.couche_sections/injections, celles chargees par
    # « Charger les couches du modele ».
    _sections_avant, dlg2.couche_sections = dlg2.couche_sections, None
    _refus = None
    try:
        dlg2._ecrire_dans_geometrie()
    except ValueError as e:
        _refus = str(e)
    dlg2.couche_sections = _sections_avant
    verifier("couches non chargees -> refus explicite", bool(_refus),
             (_refus or "")[:70])

    # Ecriture reelle des sections dessinees dans QGIS — meme couche que
    # celle chargee par « Charger les couches du modele » : plus de combo
    # separe, c'est desormais la seule source possible pour l'ecriture.
    if (dlg2.couche_sections is not None
            and dlg2.couche_sections.featureCount() == 0):
        fournisseur = dlg2.couche_sections.dataProvider()
        objets = []
        for i in range(2):
            x = 503600 + 120 * i
            e = QgsFeature(dlg2.couche_sections.fields())
            e.setGeometry(QgsGeometry.fromWkt(
                f"LineString({x} 6216000, {x} 6216200)"))
            e["nom"] = f"S_onglet_{i + 1}"
            objets.append(e)
        fournisseur.addFeatures(objets)
        dlg2.couche_sections.updateExtents()

    _echec = None
    try:
        dlg2._ecrire_dans_geometrie()
    except Exception as e:
        _echec = str(e)
    verifier("aucune erreur remontee", _echec is None, _echec or "")
    # LA TAILLE N'EST PAS UN CRITERE. Elle ne grandit que si l'ecriture AJOUTE
    # des objets ; sur une geometrie qui porte deja les sections chargees,
    # l'ecriture les REMPLACE a l'identique et le fichier ne bouge pas d'un
    # octet. C'est le cas nominal depuis que le remplacement est systematique,
    # et c'est meme le signe que la reecriture est fidele. Ce qu'il faut
    # verifier, c'est que le fichier reste COMPLET.
    _noms_apres = geometrie.noms_objets_geometrie(copie)
    verifier("les sections chargees sont bien dans la geometrie ecrite",
             set(_noms_apres["sections"]) >= set(noms_sections_avant),
             f"{_noms_apres['sections']}")
    verifier("aucune section en double apres ecriture",
             len(_noms_apres["sections"]) == len(set(_noms_apres["sections"])),
             f"{_noms_apres['sections']}")

    # REGRESSION DU 03/08/2026 : ecrire une section ne doit emporter AUCUN
    # bloc voisin. Sept regions de Manning, « Chan Stop Cuts », « Composite
    # Channel Slope », « GIS Limit At Bridges », « GIS Ratio Cuts To
    # Invert » et « Use User Specified Reach Order » avaient disparu — 629
    # lignes — sans que les compteurs de sections et de BC lines bougent.
    _blocs_apres = _compter_blocs(copie)
    _perdus = {p: (n, _blocs_apres[p]) for p, n in blocs_avant.items()
               if _blocs_apres[p] != n}
    verifier("l'ecriture n'emporte aucun bloc voisin de la geometrie",
             not _perdus, f"{_perdus}" if _perdus else "tous conserves")

    verifier("compte rendu affiche dans l'onglet",
             bool(dlg2.label_ecriture.text()),
             dlg2.label_ecriture.text()[:80])
    # LE PROJET CLIENT : compare a SON PROPRE etat d'avant, pas a la copie.
    # Comparer source et copie ne prouvait rien — une ecriture fidele les
    # rend identiques, et l'assertion se retournait contre le correctif.
    verifier("le projet client n'a pas ete touche",
             SOURCE_GEOM.read_bytes() == source_avant,
             f"{len(source_avant)} -> {SOURCE_GEOM.stat().st_size} octets")

    # REMPLACEMENT SYSTEMATIQUE : reecrire tout de suite les memes sections
    # ne doit ni lever, ni les dupliquer dans la geometrie — c'est tout
    # l'enjeu d'un remplacement automatique a chaque « Composer et
    # controler » plutot qu'un ajout ignore/refuse au second passage.
    _echec2 = None
    try:
        dlg2._ecrire_dans_geometrie()
    except Exception as e:
        _echec2 = str(e)
    verifier("un second appel ne leve pas (remplacement, pas doublon)",
             _echec2 is None, _echec2 or "")
    import geometrie as _geo
    _sections_apres = _geo.objets_depuis_texte(copie)["sections"]
    _noms_apres = [o["nom"] for o in _sections_apres]
    verifier("pas de doublon apres reecriture",
             len(_noms_apres) == len(set(_noms_apres)), _noms_apres)

# ---------------------------------------------------------------------------
print("\n6. ONGLET AIDE — CONTENU ET DIAGNOSTIC")
verifier("6 onglets, dont le suivi et l'aide", dlg.onglets.count() == 6,
         [dlg.onglets.tabText(i) for i in range(dlg.onglets.count())])
# LA BARRE D'ONGLETS NE DOIT PAS DEFILER, ET CE N'EST PAS LA BRIEVETE DES
# LIBELLES QUI L'ASSURE — c'est le plancher minimumWidth de la fenetre.
#
# Un commentaire de plugin.py attribue la garantie aux « libelles COURTS ».
# La mesure dit autre chose : le minimumSizeHint de l'agencement descendrait
# bien plus bas, et c'est le minimumWidth explicite qui retient la barre. Le
# controle porte donc sur l'invariante reelle — ce que les onglets DEMANDENT
# contre ce que la fenetre peut leur donner au plus etroit — et non sur une
# longueur de texte, qui ne protege rien.
#
# La marge s'est deja resserree sans que personne le voie : 529 px de besoin
# en 0.6.9, 663 px en 0.7.0 apres le renommage de deux onglets, pour 696 px
# disponibles. De +167 px a +33 px. Ce controle existe pour que le prochain
# renommage se voie ici, et pas sur l'ecran d'un utilisateur.
dlg.ensurePolished()
_barre = dlg.onglets.tabBar(); _barre.ensurePolished()
_marges = dlg.layout().contentsMargins()
_besoin = _barre.sizeHint().width()
_dispo = (max(dlg.minimumSizeHint().width(), dlg.minimumWidth())
          - _marges.left() - _marges.right())
verifier("la barre d'onglets ne defile pas, meme au plus etroit",
         _besoin <= _dispo,
         f"besoin {_besoin} px / disponible {_dispo} px "
         f"(marge {_dispo - _besoin:+} px ; plancher "
         f"minimumWidth={dlg.minimumWidth()} px)")
# LES RANGS NOMMES TOMBENT SUR LEUR ONGLET. Deux methodes basculent d'onglet
# apres une action ; un indice devenu faux ferait afficher l'onglet voisin sans
# que rien ne le signale — Qt ne s'en plaint pas.
verifier("les rangs nommes designent le bon onglet",
         dlg.onglets.tabText(mod_plugin.ONGLET_MODELE).startswith("1.")
         and dlg.onglets.tabText(mod_plugin.ONGLET_LANCER).startswith("4.")
         and dlg.onglets.tabText(mod_plugin.ONGLET_SUIVI).startswith("5."),
         f"{mod_plugin.ONGLET_MODELE}={dlg.onglets.tabText(mod_plugin.ONGLET_MODELE)} | "
         f"{mod_plugin.ONGLET_LANCER}={dlg.onglets.tabText(mod_plugin.ONGLET_LANCER)} | "
         f"{mod_plugin.ONGLET_SUIVI}={dlg.onglets.tabText(mod_plugin.ONGLET_SUIVI)}")

# ---------------------------------------------------------------------------
# ONGLET SUIVI. Ce qui compte n'est pas qu'il s'affiche, mais qu'il SACHE
# DIRE ce qui se passe : en cours, terminé, ou interrompu. Le reproche fait au
# suivi etait justement qu'un calcul s'arretait sans donner de nouvelles.
#
# LE SUIVI SUIT LE CLASSEUR, PAS L'ONGLET 3 (03/09/2026). Le pont ecrit le
# suivi la ou le classeur le dit (Dossier_sortie, Sous_dossier_suivi) ; la
# fenetre lisait les champs de l'onglet 3, qui ne disent que ou composer le
# PROCHAIN paquet. Un classeur repris d'un calcul precedent (onglet 4) et
# lance pendant que l'onglet 3 designait un autre dossier laissait le suivi
# muet devant un calage qui tournait. Ici l'onglet 3 designe donc EXPRES un
# autre dossier que celui du classeur compose : le suivi doit l'ignorer.
_suivi = Path(ESSAI) / "suivi"                   # ce que le classeur dit
dlg.edit_dossier_sortie.setText(str(ESSAI / "un_autre_dossier"))
dlg.edit_sous_dossier_suivi.setText("suivi_essai")
if dlg.classeur:
    verifier("suivi : le dossier surveille est celui du classeur, pas celui "
             "de l'onglet 3",
             dlg._dossier_suivi() == _suivi, f"{dlg._dossier_suivi()}")
else:
    # Ce controle-ci demande vraiment un classeur : sans modele, il n'y a pas
    # deux dossiers concurrents, donc rien a departager. L'annoncer plutot que
    # de le rendre rouge.
    print("   ignore : aucun classeur compose (aucun modele declare)")
# Sans classeur — rien n'a encore ete compose ni repris —, l'onglet 3 reste
# la seule indication, et le suivi y revient.
_classeur_garde, dlg.classeur = dlg.classeur, None
verifier("suivi : sans classeur, le dossier surveille revient a l'onglet 3",
         dlg._dossier_suivi() == ESSAI / "un_autre_dossier" / "suivi_essai",
         f"{dlg._dossier_suivi()}")
dlg.classeur = _classeur_garde


def _dossier_etat():
    """
    Le dossier que la FENETRE surveille — jamais un chemin fige.

    Avec un modele, c'est celui du classeur, donc _suivi. SANS modele, aucun
    classeur n'est compose et la fenetre se replie legitimement sur l'onglet 3
    (voir le controle ci-dessus). Deposer et effacer l'etat ailleurs qu'ou elle
    regarde rendait alors rouges QUINZE controles de rendu qui ne demandent
    pourtant aucun modele, puis faisait planter la suite entiere sur un
    table_suivi vide. Les deux chemins coincident des qu'un modele est fourni :
    passer par ici ne relache aucun controle.
    """
    return Path(dlg._dossier_suivi() or _suivi)


_dossier_etat().mkdir(parents=True, exist_ok=True)


def _ecrire_etat(**surcharges):
    etat = {"titre": "Essai", "pid": os.getpid(), "total": 3,
            "fraction": 0.3333, "ecoule_s": 900, "reste_s": 1800,
            "maj": "2026-07-27T23:45:10", "termine": False, "conforme": None,
            "motif_final": "", "nb_calculs": 4, "incidents": 0,
            "en_cours": 1, "fin": None, "fin_prevue": "2026-07-28T00:15",
            "comptes": {"validé": 1, "en cours": 1, "échoué": 0,
                        "en attente": 1},
            "apports": [
                {"ordre": 1, "apport": "A1", "section": "SC1",
                 "statut": "validé", "essais": 3, "volume_pct": 99.8,
                 "pic_pct": 100.4, "forme_pct": 99.1, "duree_s": 900,
                 "motif": ""},
                {"ordre": 2, "apport": "A2", "section": "SC2",
                 "statut": "en cours", "essais": 2, "volume_pct": 94.2,
                 "pic_pct": 91.0, "forme_pct": 98.0, "duree_s": 0,
                 "motif": ""},
                {"ordre": 3, "apport": "A3", "section": "SC3",
                 "statut": "en attente", "essais": 0, "volume_pct": None,
                 "pic_pct": None, "forme_pct": None, "duree_s": 0,
                 "motif": ""}]}
    etat.update(surcharges)
    dossier = _dossier_etat()          # la ou la fenetre regarde, cf. sa docstring
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "avancement.json").write_text(
        json.dumps(etat, ensure_ascii=False), encoding="utf-8")


_ecrire_etat()
dlg._rafraichir_suivi()
verifier("suivi : l'apport en cours et son essai sont affiches",
         "A2" in dlg.label_suivi_position.text()
         and "SC2" in dlg.label_suivi_position.text(),
         dlg.label_suivi_position.text()[:90])
verifier("suivi : l'avancement est chiffre", dlg.barre_suivi.value() == 33,
         f"{dlg.barre_suivi.value()} %")
verifier("suivi : un apport par ligne dans le tableau",
         dlg.table_suivi.rowCount() == 3, f"{dlg.table_suivi.rowCount()} ligne(s)")
verifier("suivi : le temps restant est lisible",
         "min" in dlg.label_suivi_reste.text() or "h" in dlg.label_suivi_reste.text(),
         dlg.label_suivi_reste.text())
verifier("suivi : un calage vivant est annonce EN COURS",
         "en cours" in dlg.label_suivi_banniere.text().lower(),
         dlg.label_suivi_banniere.text()[:80])

_ecrire_etat(termine=True, conforme=True, en_cours=None, fraction=1.0,
             comptes={"validé": 3, "en cours": 0, "échoué": 0, "en attente": 0})
dlg._rafraichir_suivi()
verifier("suivi : un calage abouti est annonce CONFORME",
         "conforme" in dlg.label_suivi_banniere.text().lower()
         and dlg.barre_suivi.value() == 100,
         dlg.label_suivi_banniere.text()[:80])

_ecrire_etat(termine=True, conforme=False, motif_final="apport A2 non cale")
dlg._rafraichir_suivi()
verifier("suivi : un echec dit son motif",
         "A2 non cale" in dlg.label_suivi_banniere.text(),
         dlg.label_suivi_banniere.text()[:90])

# LE CAS QUI MANQUAIT : le processus n'existe plus et aucun verdict n'a ete
# rendu. Sans cela l'affichage restait fige sur le dernier etat connu, en
# laissant croire que le calcul avance encore.
_ecrire_etat(pid=999999)
dlg._rafraichir_suivi()
verifier("suivi : un calage mort est annonce INTERROMPU",
         "interrompu" in dlg.label_suivi_banniere.text().lower(),
         dlg.label_suivi_banniere.text()[:90])

(_dossier_etat() / "avancement.json").unlink()
dlg._rafraichir_suivi()
verifier("suivi : sans etat, rien n'est invente",
         "aucun calage" in dlg.label_suivi_banniere.text().lower()
         and dlg.table_suivi.rowCount() == 0,
         dlg.label_suivi_banniere.text()[:80])
# ET LA BANNIERE DIT OU ELLE REGARDE. Un suivi muet parce qu'il regardait le
# mauvais dossier ne se distinguait en rien d'un calage pas encore parti.
verifier("suivi : sans etat, la banniere nomme le dossier qu'elle surveille",
         str(_dossier_etat()) in dlg.label_suivi_banniere.text(),
         dlg.label_suivi_banniere.text()[-100:])

# LES JAUGES JUGENT SUR LES TOLERANCES DE L'ETUDE, pas sur des defauts. Figees
# a 2 %, elles coloraient en rouge des valeurs qu'une etude a 5 % admet.
_ecrire_etat(tolerances_pct={"volume": 5.0, "pic": 5.0, "forme": 3.0})
dlg._rafraichir_suivi()
verifier("suivi : les jauges prennent les tolerances de l'etude",
         dlg.jauges["volume_pct"].tolerance == 5.0
         and dlg.jauges["pic_pct"].tolerance == 5.0,
         f"volume={dlg.jauges['volume_pct'].tolerance} "
         f"pointe={dlg.jauges['pic_pct'].tolerance}")

# ET LEURS DEFAUTS SONT CEUX DE LA CHAINE. Ecrits en dur dans l'affichage, ils
# divergeaient : la jauge « Volume » jugeait a 0,5 % ce que la boucle admet a
# 5 %, et virait au rouge sur un apport parfaitement conforme des que l'etat
# publie ne portait pas ses seuils — ce qui est le cas d'un calage lance avant
# que le suivi ne les publie.
_ecrire_etat(tolerances_pct=None)
dlg._rafraichir_suivi()
verifier("suivi : sans seuils publies, les jauges prennent ceux de la chaine",
         dlg.jauges["volume_pct"].tolerance
         == 100 * mod_plugin.TOLERANCE_VOLUME_DEFAUT
         and dlg.jauges["pic_pct"].tolerance
         == 100 * mod_plugin.TOLERANCE_PIC_DEFAUT,
         f"volume={dlg.jauges['volume_pct'].tolerance} % "
         f"pointe={dlg.jauges['pic_pct'].tolerance} %")

# LE MINUTEUR NE TOURNE QUE SUR L'ONGLET DE SUIVI. Il tournait pour la duree de
# vie de la fenetre : relire et redessiner toutes les deux secondes un onglet
# que personne ne regarde, y compris quand aucun calage n'existe et longtemps
# apres qu'il est termine.
_au_repos = not dlg.minuteur_suivi.isActive()   # a l'ouverture, onglet 1
dlg.onglets.setCurrentIndex(mod_plugin.ONGLET_SUIVI)
_demarre = dlg.minuteur_suivi.isActive()
dlg.onglets.setCurrentIndex(mod_plugin.ONGLET_MODELE)
_arrete = not dlg.minuteur_suivi.isActive()
dlg.onglets.setCurrentIndex(mod_plugin.ONGLET_SUIVI)
verifier("suivi : le minuteur ne tourne que lorsque l'onglet est affiche",
         _au_repos and _demarre and _arrete
         and dlg.minuteur_suivi.isActive(),
         f"a l'ouverture {'arrete' if _au_repos else 'TOURNE'} ; "
         f"sur l'onglet {'tourne' if _demarre else 'ARRETE'} ; "
         f"apres en etre sorti {'arrete' if _arrete else 'TOURNE'}")

# LA CIBLE TRACEE EST LA CIBLE DECALEE, ET LA LEGENDE LE DIT. Tracee brute,
# elle apparaissait translatee de Δt sous des jauges annoncant 100 % — 3,8 h
# sur un modele reel — et l'oeil concluait a un calage faux la ou il etait
# juste.
_ecrire_etat(courbes={"temps_cible": [0.0, 1.0, 2.0, 3.0],
                      "debit_cible": [0.0, 5.0, 10.0, 2.0],
                      "temps_calcule": [0.0, 1.0, 2.0, 3.0],
                      "debit_calcule": [0.0, 4.0, 9.0, 2.0],
                      "decalage_h": -3.8})
dlg._rafraichir_suivi()
verifier("suivi : la courbe recoit le decalage a annoncer",
         (dlg.courbe_suivi.courbes or {}).get("decalage_h") == -3.8,
         str((dlg.courbe_suivi.courbes or {}).get("decalage_h")))
# Un etat ancien, ecrit avant que le decalage ne soit publie, ne doit pas
# faire disparaitre le trace : la legende dit alors « cible », sans plus.
_ecrire_etat(courbes={"temps_cible": [0.0, 1.0], "debit_cible": [0.0, 5.0],
                      "temps_calcule": [0.0, 1.0], "debit_calcule": [0.0, 4.0]})
dlg._rafraichir_suivi()
dlg.courbe_suivi.repaint()
verifier("suivi : un etat sans decalage publie se trace quand meme",
         dlg.courbe_suivi.courbes is not None,
         str(dlg.courbe_suivi.courbes))

# LES JAUGES SE REPLIENT SUR LE DERNIER APPORT CHIFFRE. L'apport en cours n'a
# aucun chiffre tant que son premier essai n'est pas evalue — ~3 h de calcul
# HEC-RAS — et les trois jauges restaient vides pendant exactement ces
# heures-la. Ici A2 est en cours sans chiffre : on doit voir ceux de A1, et
# lire que ce n'est pas le calcul qui tourne.
_ecrire_etat(en_cours=1, apports=[
    {"ordre": 1, "apport": "A1", "section": "SC1", "statut": "validé",
     "essais": 2, "volume_pct": 99.8, "pic_pct": 100.4, "forme_pct": 99.1,
     "duree_s": 900, "motif": ""},
    {"ordre": 2, "apport": "A2", "section": "SC2", "statut": "en cours",
     "essais": 0, "volume_pct": None, "pic_pct": None, "forme_pct": None,
     "duree_s": 0, "motif": ""}])
dlg._rafraichir_suivi()
verifier("suivi : les jauges se replient sur le dernier apport chiffre",
         dlg.jauges["volume_pct"].valeur == 99.8
         and "A1" in dlg.label_jauges.text()
         and "dernier essai" in dlg.label_jauges.text(),
         f"jauge={dlg.jauges['volume_pct'].valeur} | "
         f"{dlg.label_jauges.text()[:80]}")
# Et quand l'apport en cours a ses chiffres, ce sont les siens, sans reserve.
_ecrire_etat(en_cours=1, apports=[
    {"ordre": 1, "apport": "A1", "section": "SC1", "statut": "validé",
     "essais": 2, "volume_pct": 99.8, "pic_pct": 100.4, "forme_pct": 99.1,
     "duree_s": 900, "motif": ""},
    {"ordre": 2, "apport": "A2", "section": "SC2", "statut": "en cours",
     "essais": 1, "volume_pct": 94.2, "pic_pct": 91.0, "forme_pct": 98.0,
     "duree_s": 0, "motif": ""}])
dlg._rafraichir_suivi()
verifier("suivi : des que l'apport en cours est chiffre, ce sont ses chiffres",
         dlg.jauges["volume_pct"].valeur == 94.2
         and "A2" in dlg.label_jauges.text()
         and "dernier essai" not in dlg.label_jauges.text(),
         f"jauge={dlg.jauges['volume_pct'].valeur} | "
         f"{dlg.label_jauges.text()[:80]}")

# LA COULEUR NE PORTE PAS SEULE LE SENS : chaque statut a aussi un glyphe.
verifier("suivi : chaque statut porte un glyphe, pas qu'une couleur",
         set(mod_plugin.GLYPHE_STATUT) == set(mod_plugin.COULEUR_STATUT)
         and all(mod_plugin.GLYPHE_STATUT.values()),
         str(mod_plugin.GLYPHE_STATUT))
verifier("suivi : le tableau affiche le glyphe avec le statut",
         "✔" in dlg.table_suivi.item(0, 2).text(),
         dlg.table_suivi.item(0, 2).text())

# Qt REFUSE UN Path la ou il attend une chaine : « argument 3 has unexpected
# type 'WindowsPath' ». Le classeur compose doit donc etre memorise en str,
# sinon « Reprendre un classeur d'un calcul precedent… » casse des qu'un
# paquet vient d'etre compose.
verifier("le classeur memorise est une chaine, pas un Path",
         dlg.classeur is None or isinstance(dlg.classeur, str),
         f"{type(dlg.classeur).__name__} : {str(dlg.classeur)[:50]}")

# LE NOM DU CLONE DE GEOMETRIE doit arriver jusqu'au classeur : c'est par lui
# que le pont le transmet au pilote. Le plan et l'Unsteady Flow, eux, ne
# passent plus par un nom de clone — ils sont titres par etape.
# Ce n'est plus un CHAMP de l'interface (retire de l'onglet 4, devenu
# « Apports a determiner ») mais une constante : on verifie donc qu'il arrive
# toujours au classeur, valeur par defaut comprise.
#
# LE PREMIER APPORT A CALER se choisit APRES la composition, et se relit du
# classeur : on verifie donc le chemin complet — remplissage du combo depuis le
# classeur, choix, ecriture, relecture. C'est ce chemin, et non la composition,
# qui decide par ou repart un calage.
if dlg.classeur:
    import pandas as _pd

    def _parametre(cle):
        _par = _pd.read_excel(dlg.classeur, sheet_name="Parametres")
        return dict(zip(_par["Parametre"], _par["Valeur"])).get(cle)

    verifier("le nom du clone de geometrie est ecrit dans le classeur",
             _parametre("Nom_clone_geometrie")
             == mod_plugin.NOM_CLONE_GEOMETRIE_DEFAUT,
             f"{_parametre('Nom_clone_geometrie')!r}")

    verifier("le champ « nom du clone » a bien disparu de l'interface",
             not hasattr(dlg, "edit_nom_clone_geometrie"))

    _paires = noyau.apports_du_classeur(dlg.classeur)
    dlg._remplir_premier_apport()
    verifier("le combo liste les apports du classeur, precede de « tous »",
             dlg.combo_premier_apport.count() == len(_paires) + 1,
             f"{dlg.combo_premier_apport.count()} entree(s) pour "
             f"{len(_paires)} apport(s)")
    if len(_paires) >= 2:
        dlg.combo_premier_apport.setCurrentIndex(2)
        verifier("le choix rend le nom de l'apport, pas le libelle affiche",
                 dlg._premier_apport() == _paires[1][0],
                 f"{dlg._premier_apport()!r} pour "
                 f"« {dlg.combo_premier_apport.currentText()} »")
        noyau.ecrire_parametre(dlg.classeur, "Premier_apport",
                               dlg._premier_apport())
        verifier("il est ecrit dans le classeur, et relu tel quel",
                 _parametre("Premier_apport") == _paires[1][0],
                 f"{_parametre('Premier_apport')!r}")
        # LE CHOIX SURVIT A UNE RECOMPOSITION : sans cela, recomposer
        # remettrait le calage au premier apport sans rien dire.
        dlg._remplir_premier_apport()
        verifier("le choix survit a un rechargement de la liste",
                 dlg._premier_apport() == _paires[1][0],
                 f"{dlg._premier_apport()!r}")
        noyau.ecrire_parametre(dlg.classeur, "Premier_apport", "")
# Le nom et l'editeur ne doivent exister qu'a un seul endroit : le jour ou
# metadata.txt et l'interface divergent, c'est l'utilisateur qui arbitre entre
# deux noms differents pour le meme outil.
_meta = (Path(mod_plugin.__file__).parent / "metadata.txt").read_text(
    encoding="utf-8")
verifier("le nom du plugin est celui des metadonnees",
         f"name={mod_plugin.NOM_PLUGIN}" in _meta,
         f"« {mod_plugin.NOM_PLUGIN} »")
verifier("l'editeur est celui des metadonnees",
         f"author={mod_plugin.EDITEUR}" in _meta,
         f"« {mod_plugin.EDITEUR} »")
verifier("le titre de la fenetre nomme l'outil et son editeur",
         mod_plugin.NOM_PLUGIN in dlg.windowTitle()
         and mod_plugin.EDITEUR in dlg.windowTitle(),
         dlg.windowTitle())
# AUCUNE ATTACHE A UN PROJET CLIENT.
#
# Les fichiers du plugin sont distribues : un chemin d'affaire qui s'y trouve
# part chez tous ceux qui l'installent, et rend le code inexecutable ailleurs
# que sur le poste ou il a ete ecrit.
#
# Ce qui est interdit, ce sont les chemins de DONNEES. Les emplacements de
# LOGICIEL restent legitimes : il faut bien savoir ou HEC-RAS s'installe, et
# le repli sur C:\Windows sert quand SystemRoot est absent de l'environnement.
#
# LA LISTE BLANCHE PORTAIT AUSSI « RACINE_OUTILS », c'est-a-dire d:\1-Python,
# le poste de l'auteur. Ce controle etait donc ecrit pour laisser passer
# exactement ce qu'il devait attraper, et l'archive est partie avec ce chemin
# jusqu'au 08/08/2026. Une exception nominative dans un garde-fou finit
# toujours par etre la seule chose qu'il ne voit plus : ne rien remettre ici
# sans que ce soit un emplacement d'INSTALLATION, identique sur tout poste.
# LE MEME CRITERE QUE faire_zip.py, ET UNE SEULE FOIS — comme la liste
# d'affaires plus bas, et pour la meme raison.
#
# CE CONTROLE VIVAIT SUR UNE LISTE BLANCHE, et faire_zip.py a note pourquoi
# elle ne pouvait pas marcher : elle portait « d:\1-Python », le poste de
# l'auteur, si bien que le garde-fou etait ecrit pour ignorer exactement ce
# qu'il devait voir. faire_zip.py est passe a « ce chemin existe-t-il ici ? » ;
# ce jumeau-ci etait reste en arriere, et refusait depuis la 0.6.7 les faux
# chemins que l'auto-test de noyau.py emploie pour eprouver la lecture de
# « py -0p » — des chemins qui n'existent nulle part, donc inoffensifs.
import faire_zip as _fz                                        # noqa: E402
for _fichier in sorted(Path(mod_plugin.__file__).parent.glob("*.py")):
    _chemins = _fz.chemins_du_poste(_fichier.read_text(encoding="utf-8"))
    verifier(f"aucun chemin de donnees dans {_fichier.name}",
             not _chemins, "; ".join(_chemins[:2]) or "aucun")

# AUCUNE MENTION D'UNE AFFAIRE NI D'UN CAS D'ESSAI.
#
# L'archive part sur des dizaines de postes, y compris hors de la maison. Un
# nom d'affaire cliente dans un commentaire l'accompagne, et un mainteneur
# d'ailleurs lit une justification adossee a un cas qu'il ne peut pas
# consulter. La mesure garde toute sa valeur sans le nom : « sept apports d'un
# modele reel » dit la meme chose que le nom du client.
# LA MEME LISTE QUE faire_zip.py, ET UNE SEULE FOIS. Elle etait recopiee ici,
# donc vouee a diverger — et elle nommait les clients dans un fichier suivi.
import faire_zip                                              # noqa: E402
_MOTS = faire_zip.mots_d_affaires()
_AFFAIRES = (re.compile("|".join(re.escape(_m) for _m in _MOTS), re.IGNORECASE)
             if _MOTS else None)
_a_scruter = sorted(Path(mod_plugin.__file__).parent.glob("*.py"))
if _AFFAIRES is None:
    # AUCUNE LISTE, DONC AUCUN CONTROLE — mais on le DIT. mots_d_affaires()
    # lit un fichier .affaires qui n'est pas versionne (seul .affaires.exemple
    # l'est) : il est absent de tout poste neuf. Le « else None » ci-dessus
    # montre que ce cas etait prevu ; findall etait pourtant appele dessus, et
    # emportait la suite entiere sur un AttributeError. Un garde-fou qui
    # PLANTE faute de sa liste est pire que muet : il fait croire a une panne
    # du greffon la ou il manque un fichier de configuration.
    print(f"   ignore : aucun mot d'affaire declare (fichier .affaires "
          f"absent) — {len(_a_scruter)} controles non joues")
else:
    for _fichier in _a_scruter:
        _trouves = sorted(set(_AFFAIRES.findall(
            _fichier.read_text(encoding="utf-8"))))
        verifier(f"aucun nom d'affaire ni de cas d'essai dans {_fichier.name}",
                 not _trouves, ", ".join(_trouves[:4]) or "aucun")

# TYPES DE CHAMP, ET LES DEUX VERSIONS DE QGIS QUI LES ECRIVENT AUTREMENT.
#
# QgsField n'accepte QMetaType.Type que depuis QGIS 3.38 ; metadata.txt
# annonce 3.34. Sans repli, « Charger les couches du modele » levait un
# TypeError sur toute 3.34 ou 3.36 — l'extension s'installait et s'ouvrait,
# la panne ne se voyait qu'au premier usage reel.
verifier("un type de champ texte et un type reel ont ete choisis",
         mod_plugin.TYPE_CHAMP_TEXTE is not None
         and mod_plugin.TYPE_CHAMP_REEL is not None,
         f"texte={mod_plugin.TYPE_CHAMP_TEXTE} reel={mod_plugin.TYPE_CHAMP_REEL}")

# CE QUE LE REPLI EMPLOIE DOIT MARCHER, meme quand ce n'est pas lui qui sert.
# La branche QVariant ne se declenche que sous QGIS < 3.38, introuvable ici :
# on ne peut pas la prendre, on peut prouver qu'elle tiendrait.
from qgis.PyQt.QtCore import QVariant                        # noqa: E402
from qgis.core import QgsField as _QgsField, QgsFields as _QgsFields  # noqa: E402
try:
    _champs_essai = _QgsFields()
    _champs_essai.append(_QgsField("essai", QVariant.String))
    _champs_essai.append(_QgsField("essai2", QVariant.Double))
    _repli_tient = _champs_essai.count() == 2
    _repli_motif = f"{_champs_essai.count()} champ(s) construits"
except Exception as _e:                                      # noqa: BLE001
    _repli_tient = False
    _repli_motif = f"{type(_e).__name__}: {_e}"
verifier("le repli QVariant, pris sous QGIS < 3.38, construit bien un champ",
         _repli_tient, _repli_motif)

_couche_essai = mod_plugin.construire_couche_lignes_depuis_wkt(
    "essai_types", [{"nom": "A1", "wkt": "LINESTRING(0 0, 10 10)"}],
    "EPSG:2154")
verifier("une couche de lignes se construit et porte son champ",
         _couche_essai.isValid()
         and _couche_essai.fields().indexOf("nom") >= 0
         and _couche_essai.featureCount() == 1,
         f"valide={_couche_essai.isValid()} "
         f"champs={[f.name() for f in _couche_essai.fields()]}")

_emprise_essai = mod_plugin.construire_couche_polygones_depuis_wkt(
    "essai_emprise", [{"zone": "Perimeter 1",
                       "wkt": "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"}],
    "EPSG:2154")
verifier("une couche d'emprise se construit et porte son champ",
         _emprise_essai.isValid()
         and _emprise_essai.fields().indexOf("zone") >= 0,
         f"valide={_emprise_essai.isValid()} "
         f"champs={[f.name() for f in _emprise_essai.fields()]}")

# CONSTANTES Qt TOUTES QUALIFIEES.
#
# metadata.txt annonce supportsQt6=True. Sous PyQt6, une constante non
# qualifiee — Qt.AlignLeft au lieu de Qt.AlignmentFlag.AlignLeft — leve
# AttributeError : l'annonce etait fausse, et 61 constantes etaient dans ce
# cas. La forme qualifiee vaut sous PyQt5 comme sous PyQt6 ; c'est donc elle
# partout, et cet essai empeche une nouvelle de rentrer.
_PORTEES_CONNUES = (
    "AlignmentFlag|TextInteractionFlag|TextFormat|PenStyle|ScrollBarPolicy|"
    "WindowModality|BrushStyle|ItemDataRole|Orientation|CheckState|"
    "KeyboardModifier|Key|CursorShape|WindowType|ItemFlag|SortOrder|"
    "GlobalColor|LayoutDirection|FocusPolicy|ConnectionType|MatchFlag|"
    "ToolButtonStyle|TimeSpec|DateFormat|TextElideMode|AspectRatioMode|"
    "TransformationMode|ContextMenuPolicy|WidgetAttribute|ArrowType")
#
# CE GARDE-FOU AVAIT UN ANGLE MORT, et il a coute exactement ce qu'il devait
# eviter : il ne portait que sur six classes. QFormLayout, QTextEdit et
# QTableWidget n'y etaient pas, et quatre constantes non qualifiees y sont
# restees — dont QFormLayout.AllNonFixedFieldsGrow, lue a la construction du
# PREMIER formulaire, donc a l'ouverture de la fenetre. La liste couvre
# desormais vingt classes.
#
# QMetaType Y FIGURE, et pas seulement parce qu'il est bien ecrit aujourd'hui :
# constater un usage n'est pas poser une regle. QMetaType.QString leverait
# AttributeError sous PyQt6 a la construction de tout QgsField, donc des
# « Charger les couches du modele ».
#
# UNE SEULE CLASSE EN EST VOLONTAIREMENT ABSENTE : QVariant, employe sous sa
# forme PLATE (QVariant.String), et c'est voulu — cette branche ne s'execute
# que sur QGIS < 3.38, donc sous PyQt5, ou la forme plate est la seule qui
# existe. L'y interdire casserait le repli qui fait tenir la promesse
# qgisMinimumVersion=3.34.
for _classe, _portees in (("Qt", _PORTEES_CONNUES),
                          ("QMessageBox", "StandardButton|Icon|ButtonRole"),
                          ("QSizePolicy", "Policy|ControlType"),
                          ("QPainter", "RenderHint|CompositionMode"),
                          ("QLayout", "SizeConstraint"),
                          ("QFrame", "Shape|Shadow|StyleMask"),
                          ("QFormLayout",
                           "FieldGrowthPolicy|ItemRole|RowWrapPolicy"),
                          ("QTextEdit",
                           "LineWrapMode|AutoFormattingFlag"),
                          ("QAbstractItemView",
                           "EditTrigger|SelectionMode|SelectionBehavior|"
                           "ScrollMode|ScrollHint|DragDropMode"),
                          # MEMES PORTEES QUE QAbstractItemView, dont il
                          # herite : une portee presente chez le parent et
                          # absente ici ferait denoncer une ecriture pourtant
                          # parfaitement qualifiee (QTableWidget.DragDropMode.
                          # InternalMove) comme une constante nue.
                          ("QTableWidget",
                           "EditTrigger|SelectionMode|SelectionBehavior|"
                           "ScrollMode|ScrollHint|DragDropMode"),
                          ("QHeaderView", "ResizeMode"),
                          ("QDialog", "DialogCode"),
                          ("QLineEdit", "EchoMode|ActionPosition"),
                          ("QComboBox", "InsertPolicy|SizeAdjustPolicy"),
                          ("QTabWidget", "TabPosition|TabShape"),
                          ("QFileDialog",
                           "Option|AcceptMode|FileMode|ViewMode"),
                          ("QIcon", "Mode|State"),
                          ("QPalette", "ColorRole|ColorGroup"),
                          ("QFont",
                           "Weight|Style|Capitalization|StyleHint"),
                          ("QMetaType", "Type")):
    # LE LOOKAHEAD EST ANCRE PAR \b, ET CE N'EST PAS UN DETAIL. Sans lui, il
    # suffisait qu'une portee connue soit le PREFIXE du membre pour que celui-ci
    # echappe au controle : « Key » figurant dans _PORTEES_CONNUES, toute la
    # famille Qt.Key_Return / Qt.Key_Escape — la plus nombreuse des constantes
    # Qt, et cassante sous PyQt6 — n'etait pas vue. Mesure : sur « Qt.Key_Return »
    # l'ancienne expression ne rendait rien, la nouvelle rend « Key_Return ».
    # Le [A-Za-z_0-9] capture en outre les membres a underscore ou a chiffre,
    # que [A-Za-z] tronquait.
    _nus = sorted(set(re.findall(
        rf"\b{_classe}\.(?!(?:{_portees})\b)([A-Z][A-Za-z_0-9]+)",
        Path(mod_plugin.__file__).read_text(encoding="utf-8"))))
    verifier(f"aucune constante {_classe} non qualifiee (Qt6)",
             not _nus, ", ".join(_nus[:4]) or "aucune")


# LA FENETRE DE CRUE EXISTE EN DEUX EXEMPLAIRES — greffon et livrables.py — et
# c'est un choix : fusionner ferait entrer matplotlib dans un paintEvent. Ce
# qui est interdit, c'est qu'elles divergent : la courbe du suivi et la figure
# du livrable cadreraient alors deux fenetres differentes, sans que rien ne le
# dise. Les deux constantes sont donc comparees ici, sur le TEXTE des deux
# fichiers — ce qui n'exige d'importer ni matplotlib ni la chaine.
_CRUE = {}
for _quel, _fichier in (("greffon", Path(mod_plugin.__file__)),
                        ("livrables", CHAINE / "livrables.py")):
    _texte = _fichier.read_text(encoding="utf-8")
    _CRUE[_quel] = {
        _c: (re.search(rf"^{_c} = ([0-9.]+)", _texte, re.M) or [None, None])[1]
        for _c in ("SEUIL_CRUE", "MARGE_CRUE_H")}
verifier("la fenetre de crue est nommee des deux cotes",
         all(v is not None for d in _CRUE.values() for v in d.values()),
         f"greffon={_CRUE['greffon']} livrables={_CRUE['livrables']}")
verifier("la fenetre de crue ne diverge pas entre greffon et livrables",
         _CRUE["greffon"] == _CRUE["livrables"],
         f"greffon={_CRUE['greffon']} | livrables={_CRUE['livrables']}")

# ET LES DEUX SIGNATURES DOIVENT LIRE CES CONSTANTES. Comparer les constantes
# ne suffit pas : ecrire « def _fenetre_crue(paires, seuil=0.05, ...) » en
# laissant SEUIL_CRUE = 0.02 juste au-dessus laisserait les deux controles
# ci-dessus au vert pendant que les deux fenetres divergent — exactement ce
# que ce garde-fou existe pour empecher.
_SIGN = {}
for _quel, _fichier in (("greffon", Path(mod_plugin.__file__)),
                        ("livrables", CHAINE / "livrables.py")):
    _m = re.search(r"def _fenetre_crue\((.*?)\):",
                   _fichier.read_text(encoding="utf-8"), re.S)
    _SIGN[_quel] = _m.group(1) if _m else ""
verifier("les deux signatures de crue lisent les constantes, pas des litteraux",
         all("SEUIL_CRUE" in s and "MARGE_CRUE_H" in s for s in _SIGN.values()),
         " | ".join(f"{q}: {' '.join(s.split())[:60]}" for q, s in _SIGN.items()))

# Le nom du DOSSIER est le nom du paquet pour QGIS, et le repertoire sous
# lequel l'extension s'installe. « qgis_plugin » l'installait sous un nom
# generique, indiscernable parmi les autres extensions et sujet aux collisions.
verifier("le dossier du plugin porte le nom du paquet",
         Path(mod_plugin.__file__).parent.name == "calage_apports",
         Path(mod_plugin.__file__).parent.name)

verifier("aucun nom du plugin ecrit en dur ailleurs",
         Path(mod_plugin.__file__).read_text(encoding="utf-8").count(
             f'"{mod_plugin.NOM_PLUGIN}"') == 1,
         "seule la definition de NOM_PLUGIN")

# PARAMETRES DU POSTE.
#
# Deux emplacements a designer, et deux seulement : QGIS n'a pas a l'etre — le
# plugin s'y execute — et HEC-RAS non plus, puisqu'il n'est jamais lance
# directement. Avant ce groupe, l'interpreteur ne pouvait etre designe que par
# une variable d'environnement systeme : il fallait quitter QGIS, la definir,
# et relancer.
verifier("les deux emplacements du poste sont affiches",
         bool(dlg.label_chaine.text())
         and bool(dlg.label_interpreteur.text()),
         f"chaine={dlg.label_chaine.text()[:40]} | "
         f"interp={dlg.label_interpreteur.text()[:40]}")
# L'INTERPRETEUR HEC-RAS EST UN EQUIPEMENT OPTIONNEL DU POSTE, pas une piece
# du greffon : il se designe, et le greffon compose et controle tres bien un
# paquet sans lui. Les trois controles qui l'EXIGENT sont donc IGNORES quand il
# n'y en a pas, au lieu d'etre comptes en echec.
#
# Ils l'etaient, et c'etait nuisible : le banc sortait « 3 ECHEC(S) » sur tout
# poste depourvu de CALAGE_PYTHON — c'est-a-dire sur tout poste neuf — ce qui
# apprend a passer sur ses echecs, et masquerait le jour venu un vrai defaut.
# Pour les exercer :  set CALAGE_PYTHON=<...>\\python.exe
_interpreteur = mod_plugin.noyau.interpreteur_hecras()
if _interpreteur is None:
    print("   ignore : aucun interpreteur HEC-RAS designe sur ce poste "
          "(CALAGE_PYTHON) — 3 controles non joues")
else:
    verifier("l'interpreteur trouve est celui qui pilote HEC-RAS",
             "python" in dlg.label_interpreteur.text().lower(),
             dlg.label_interpreteur.text()[:60])

    _ok_i, _msg_i = mod_plugin.noyau.verifier_interpreteur(_interpreteur)
    verifier("la verification confirme ras-commander et h5py",
             _ok_i and "ras-commander" in _msg_i, _msg_i[:70])

# Un python qui EXISTE mais ne sait pas piloter HEC-RAS doit etre refuse : le
# python de QGIS en est l'exemple meme, et l'accepter le ferait echouer au
# premier calcul, apres clonage — loin de la cause.
_python_qgis = Path(sys.executable)
_ok_q, _msg_q = mod_plugin.noyau.verifier_interpreteur(_python_qgis)
verifier("le python de QGIS est refuse, avec une raison lisible",
         not _ok_q and len(_msg_q) > 10 and "<no Python frame>" not in _msg_q,
         _msg_q[:80])

_avant = mod_plugin.noyau.interpreteur_hecras()
_ok_r, _ = mod_plugin.noyau.definir_interpreteur(str(_python_qgis))
verifier("un interpreteur refuse ne remplace pas celui en place",
         not _ok_r and mod_plugin.noyau.interpreteur_hecras() == _avant,
         str(mod_plugin.noyau.interpreteur_hecras())[:60])

if _avant is None:
    print("   ignore : aucun interpreteur a memoriser")
else:
    verifier("un interpreteur memorise se retablit sans sous-processus",
             mod_plugin.noyau.restaurer_interpreteur(str(_avant))
             and mod_plugin.noyau.interpreteur_hecras() == Path(_avant))
verifier("un interpreteur memorise puis disparu n'est pas retabli",
         not mod_plugin.noyau.restaurer_interpreteur(r"C:\parti\python.exe"))

# Une balise mal refermee dans l'aide ne leve aucune erreur : Qt rend ce
# qu'il peut, et le reste de la page disparait silencieusement.
for _balise in ("ul", "ol", "li", "p", "h3"):
    _o = len(re.findall(rf"<{_balise}[ >]", mod_plugin.AIDE_HTML))
    _f = mod_plugin.AIDE_HTML.count(f"</{_balise}>")
    verifier(f"balises <{_balise}> equilibrees dans l'aide", _o == _f,
             f"{_o} ouvert(s) / {_f} ferme(s)")
verifier("aucune liste vide dans l'aide",
         not re.findall(r"<ul>\s*</ul>", mod_plugin.AIDE_HTML))

verifier("l'aide couvre le mode operatoire",
         all(m in mod_plugin.AIDE_HTML
             for m in ("mode opératoire", "amont", "Unsteady",
                       "Volume", "Débit de pointe", "Forme")),
         f"{len(mod_plugin.AIDE_HTML)} caracteres")
# L'aide dit les trois grandeurs cherchees, jamais un indicateur agrege : le
# vocabulaire de l'interface et celui des livrables doivent rester le meme.
verifier("l'aide ne parle plus en KGE",
         "KGE" not in mod_plugin.AIDE_HTML)
# La fenetre doit pouvoir rester ouverte pendant qu'on dessine dans QGIS :
# modale, elle bloquerait la carte et obligerait a fermer/rouvrir.
p.composer()
verifier("la fenetre s'ouvre NON MODALE",
         p.fenetre is not None and not p.fenetre.isModal(),
         f"modale={p.fenetre.isModal() if p.fenetre else '?'}")
verifier("une seconde ouverture reutilise la meme fenetre",
         (lambda f: (p.composer(), p.fenetre is f)[1])(p.fenetre))
p.fenetre.close()


# LE SABLIER DOIT SURVIVRE A UN VRAI SIGNAL.
#
# @avec_sablier a fait TOMBER QGIS. Ecrite « enveloppe(self, *args) », elle
# passait aupres de PyQt pour accepter n'importe quoi, et clicked(bool) lui
# transmettait son « checked » : methode(self, False) levait TypeError DANS un
# slot Qt, ce que PyQt >= 5.5 traite par abort(). Les cinq boutons principaux
# du greffon etaient concernes.
#
# CE BANC NE POUVAIT PAS LE VOIR : il appelle les methodes directement, jamais
# par le signal. C'est exactement l'angle mort qu'avait le controle Qt6 avant
# d'etre elargi. On eprouve donc le decorateur PAR LE SIGNAL, sur une methode
# jetable — les vraies ecrivent sur le disque et ne peuvent pas etre cliquees
# ici.
from qgis.PyQt.QtCore import Qt                              # noqa: E402
from qgis.PyQt.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402

_temoin_sablier = []


class _CobayeSablier(QWidget):
    @mod_plugin.avec_sablier
    def action(self):
        _temoin_sablier.append(QApplication.overrideCursor() is not None)


_cobaye = _CobayeSablier()
_bouton_essai = QPushButton("essai", _cobaye)
_bouton_essai.clicked.connect(_cobaye.action)
_incident_sablier = None
try:
    _bouton_essai.click()
except Exception as _e:                                      # noqa: BLE001
    _incident_sablier = f"{type(_e).__name__}: {_e}"
verifier("le sablier survit a un vrai clic (aucun argument parasite)",
         _temoin_sablier == [True] and _incident_sablier is None,
         f"execute={_temoin_sablier} incident={_incident_sablier or 'aucun'}")
verifier("le sablier est rendu apres le clic",
         QApplication.overrideCursor() is None,
         "aucun curseur residuel" if QApplication.overrideCursor() is None
         else f"IL EN RESTE UN : {QApplication.overrideCursor().shape()}")

# Et il ne doit pas depiler le curseur de quelqu'un d'autre : rendre_la_main()
# est appele AVANT une boite, puis le finally du decorateur restaure une
# seconde fois. Un restore de trop depile le curseur courant des que la pile
# n'est pas vide — celui de QGIS, par exemple.
QApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)
_avant_tiers = QApplication.overrideCursor().shape()


class _CobayeRendu(QWidget):
    @mod_plugin.avec_sablier
    def action(self):
        mod_plugin.rendre_la_main(self)


_c2 = _CobayeRendu()
_b2 = QPushButton("essai", _c2)
_b2.clicked.connect(_c2.action)
_b2.click()
_apres_tiers = QApplication.overrideCursor()
verifier("le sablier ne depile pas le curseur d'un tiers",
         _apres_tiers is not None and _apres_tiers.shape() == _avant_tiers,
         f"avant={_avant_tiers} apres="
         f"{None if _apres_tiers is None else _apres_tiers.shape()}")
QApplication.restoreOverrideCursor()


# LE SABLIER SE SUSPEND DEVANT UNE BOITE QUI ATTEND L'UTILISATEUR. Un
# selecteur de fichier peut rester ouvert des minutes : le sablier y
# designerait un calcul qui n'a pas lieu.


class _CobayeSuspension(QWidget):
    @mod_plugin.avec_sablier
    def action(self):
        _suspension.append(("avant", QApplication.overrideCursor() is not None))
        with mod_plugin.sans_sablier(self):
            _suspension.append(("pendant", QApplication.overrideCursor() is not None))
        _suspension.append(("apres", QApplication.overrideCursor() is not None))


_suspension = []
_c3 = _CobayeSuspension()
_b3 = QPushButton("essai", _c3)
_b3.clicked.connect(_c3.action)
_b3.click()
verifier("le sablier se retire devant une boite, puis revient",
         _suspension == [("avant", True), ("pendant", False), ("apres", True)],
         str(_suspension))
verifier("aucun sablier ne subsiste apres la suspension",
         QApplication.overrideCursor() is None,
         "aucun" if QApplication.overrideCursor() is None else "IL EN RESTE UN")

verifier("fil conducteur renseigne et coherent",
         "Modèle chargé" in dlg.label_fil.text()
         and "Paquet composé" in dlg.label_fil.text(),
         dlg.label_fil.text().replace("<b>", "").replace("</b>", "")[:90])
BoiteMessage.informations.clear()
dlg._diagnostic()
verifier("diagnostic affiche", bool(BoiteMessage.informations),
         BoiteMessage.informations[-1].replace("\n", " | ")[:90]
         if BoiteMessage.informations else "")
verifier("diagnostic repris dans l'onglet", bool(dlg.label_diagnostic.text()),
         dlg.label_diagnostic.text().replace("\n", " | ")[:70])

# ---------------------------------------------------------------------------
print("\n7. DECHARGEMENT")
_barre_avant = p.barre
_fenetre_avant = p.fenetre
# CE QUE unload() DOIT TROUVER A DEFAIRE. Sans ce constat prealable, les essais
# qui suivent passeraient au vert meme si rien n'avait jamais ete accroche —
# un controle qui ne peut pas echouer ne controle rien.
from qgis.PyQt.QtWidgets import QMenu as _QMenuA               # noqa: E402
verifier("avant unload : l'entree de Vue > Barres d'outils est bien la",
         any(_barre_avant.toggleViewAction() in m.actions()
             for m in iface.mainWindow().findChildren(_QMenuA)),
         "l'essai de retrait a donc quelque chose a retirer")
verifier("avant unload : la barre est dans la disposition",
         iface.mainWindow().toolBarArea(_barre_avant)
         != Qt.ToolBarArea.NoToolBarArea,
         f"zone={iface.mainWindow().toolBarArea(_barre_avant)}")
p.unload()
verifier("unload sans erreur", True)
# CE QUE unload() DOIT AVOIR DEFAIT, et qui ne se constatait pas : la barre
# d'outils retiree de la fenetre principale, la fenetre non modale fermee, la
# liste d'actions videe, et la chaine sortie de sys.path.
# CE QUE removeToolBar() GARANTIT, ET RIEN DE PLUS : la barre quitte la
# disposition et est MASQUEE ; elle n'est pas detruite et reste enfant de la
# fenetre principale. C'est suffisant — une barre masquee et delistee ne se
# duplique pas au rechargement — et c'est ce qu'il faut eprouver, pas sa
# destruction.
from qgis.PyQt.QtCore import Qt as _Qt                        # noqa: E402
# L'ENTREE DE « VUE > BARRES D'OUTILS » DOIT PARTIR AUSSI. C'est la reserve
# que unload() portait encore : une case a cocher survivante s'y serait
# dupliquee a chaque rechargement.
from qgis.PyQt.QtWidgets import QMenu as _QMenu                # noqa: E402
_bascule = _barre_avant.toggleViewAction()
verifier("unload retire l'entree de Vue > Barres d'outils",
         not any(_bascule in m.actions()
                 for m in iface.mainWindow().findChildren(_QMenu)),
         f"action « {_bascule.text()} » absente des menus")
verifier("unload masque la barre d'outils et la sort de la disposition",
         not _barre_avant.isVisible()
         and iface.mainWindow().toolBarArea(_barre_avant)
         == _Qt.ToolBarArea.NoToolBarArea,
         f"visible={_barre_avant.isVisible()} "
         f"zone={iface.mainWindow().toolBarArea(_barre_avant)}")
verifier("unload ferme la fenetre non modale",
         p.fenetre is None and (_fenetre_avant is None
                                or not _fenetre_avant.isVisible()),
         f"fenetre={p.fenetre}")
verifier("unload vide la liste des actions", p.actions == [],
         f"{len(p.actions)} action(s) restantes")
verifier("unload retire la chaine de sys.path",
         not any(mod_plugin.noyau.est_chaine(c) for c in sys.path),
         "aucune chaine sur sys.path")

print("\n" + "=" * 74)
if echecs:
    print(f"{len(echecs)} ECHEC(S) : {echecs}")
else:
    print("La fenetre du plugin s'execute de bout en bout.")
print("=" * 74)

qgs.exitQgis()
sys.exit(1 if echecs else 0)
