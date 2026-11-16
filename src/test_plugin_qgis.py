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
from datetime import datetime, timedelta
from pathlib import Path

# ORDRE IMPOSE : qgis.core avant tout le reste. Charger geopandas d'abord
# casserait le chargement des DLL de qgis._core.
import os  # noqa: E402

from qgis.core import QgsApplication, QgsProject, QgsVectorLayer, QgsFeature, \
    QgsGeometry, QgsField

# QgsApplication.setPrefixPath() DOIT etre appele avant initQgis(), sans quoi
# les plugins providers (dont MDAL, qui lit nativement les maillages
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

# LE GREFFON « offscreen » NE VOIT AUCUNE POLICE SOUS WINDOWS tant qu'on ne
# lui donne pas le dossier des polices du systeme (23/10/2026). Il mesurait
# alors chaque texte dans une police de repli sans nom (« police resolue : »
# vide), aux metriques gonflees — le bouton « Valider la geometrie… » y
# demandait 1088 px a 13 pt, 600 environ sous la plate-forme windows —, et
# quatre controles de disposition echouaient sans rien dire de la fenetre
# reelle : la page Objectifs et le dernier champ des etapes 1 a 3 a 13 pt.
# Avec ce dossier, Segoe UI est resolue et les memes controles passent ; un
# QT_QPA_FONTDIR deja pose est respecte.
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
qgs = QgsApplication([], False)
qgs.initQgis()
from qgis.PyQt.QtGui import QFont, QFontDatabase, QFontInfo    # noqa: E402

# Les metriques du greffon de plateforme « offscreen » peuvent utiliser une
# police de remplacement sous Windows. Nommer la police disponible et dire
# celle que Qt resout, au lieu de certifier une geometrie sur ce remplacement.
try:
    _familles = QFontDatabase.families()          # Qt 6 : methode statique
except TypeError:
    _familles = QFontDatabase().families()        # Qt 5
if "Segoe UI" in _familles:
    qgs.setFont(QFont("Segoe UI", 9))
else:
    # L'alias par défaut « DejaVu LGC Sans » peut être résolu en « DejaVu Sans ».
    # Tester une famille réellement disponible, avec les mêmes tailles demandées.
    _police_resolue = QFont(qgs.font())
    _police_resolue.setFamily(QFontInfo(qgs.font()).family())
    qgs.setFont(_police_resolue)
print(f"Plateforme Qt : {qgs.platformName()} ; police demandee : "
      f"{qgs.font().family()} ; police resolue : {QFontInfo(qgs.font()).family()}")

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

if os.name != "nt":
    # Le produit interroge tasklist sur son poste Windows. Ici seul cet adaptateur
    # OS est remplacé : les états du suivi et les widgets restent ceux du produit.
    # Une sonde POSIX réelle permet d'éprouver vivant/disparu dans le conteneur.
    # Ceci ne valide pas tasklist : la recette Windows conserve cette obligation.
    def _processus_posix_de_recette(pid):
        if not pid:
            return None
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except (OSError, ValueError):
            return None
        return True
    noyau.processus_vivant = _processus_posix_de_recette
    print("Recette Linux : sonde PID POSIX ; tasklist Windows NON éprouvé.")

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
    # « del » ; il ne suffit plus des lors que le plugin appelle
    # removeToolBar(), qui exige un QToolBar et rien d'autre. cpn.ajouter()
    # passe la barre toute faite (23/10/2026) : addToolBar(nom) de QGIS rend
    # une barre que Python detruit aussitot.
    def addToolBar(self, barre):  # noqa: N802
        from qgis.PyQt.QtWidgets import QMenu
        self.barres.append(barre.windowTitle())
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


class DialogueTexte:
    """Repond aux QInputDialog dans l'ordre programme."""

    def __init__(self):
        self.reponses_item, self.reponses_texte = [], []
        self.questions = []

    def getItem(self, parent, titre, libelle, choix, i, editable):  # noqa: N802
        # LA SIGNATURE REPRODUIT QInputDialog.getItem, ELLE NE SE CHOISIT PAS.
        # Quatre de ses six arguments ne servent a rien ici — le mannequin
        # repond sans rien afficher — mais les retirer casserait l'appel du
        # plugin, qui les passe en position. Les consommer explicitement dit
        # que l'oubli est voulu, et evite a vulture de signaler chaque annee
        # un « unused variable 'editable' » qu'il faut re-instruire (P2-11 de
        # AUDIT.md).
        del parent, titre, i, editable
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


class _RolesBouton:
    AcceptRole = 0
    ActionRole = 1
    RejectRole = 2


class _BoutonDeBoite:
    """Ce que rend addButton() : de quoi se comparer PAR IDENTITE."""

    def __init__(self, libelle, role):
        self._libelle = libelle
        self.role = role

    def text(self):
        return self._libelle


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
    #
    # ET IL A RECOMMENCE, LE 08/09/2026, AU MOT PRES. La meme branche, sur un
    # poste ou CALAGE_PYTHON n'est plus defini : setInformativeText,
    # addButton, setDefaultButton et clickedButton manquaient cette fois, et
    # le banc s'arretait sur AttributeError apres 179 controles verts. La
    # lecon ne change pas — ce talon suit une classe Qt qu'il n'implemente
    # qu'a moitie, et c'est la branche la moins parcourue qui le revele. Les
    # quatre methodes sont posees ci-dessous, et la branche a desormais son
    # controle.
    StandardButton = _BoutonsStandard
    ButtonRole = _RolesBouton
    Icon = _Icones

    def __init__(self, parent=None):
        self.detail = ""
        self.informatif = ""
        self.redimensionnable = False
        self.boutons = []
        self.bouton_defaut = None
        self.bouton_echappement = None

    def setWindowTitle(self, t): pass          # noqa: E704, N802
    def setIcon(self, i): pass                 # noqa: E704, N802
    def setText(self, t): self.texte = t       # noqa: E704, N802
    def setDetailedText(self, t): self.detail = t   # noqa: E704, N802
    def setInformativeText(self, t): self.informatif = t  # noqa: E704, N802
    def setDefaultButton(self, b): self.bouton_defaut = b  # noqa: E704, N802
    # confirmer() (0.8.5) pose aussi le bouton d'echappement : Echap et la
    # croix disent « non », comme Entree.
    def setEscapeButton(self, b): self.bouton_echappement = b  # noqa: E704, N802
    def exec(self): BoiteMessage.dernier = self     # noqa: E704

    def addButton(self, libelle, role):  # noqa: N802
        bouton = _BoutonDeBoite(libelle, role)
        self.boutons.append(bouton)
        return bouton

    # AUCUN BOUTON N'EST CLIQUE, ET C'EST LE BON DEFAUT. Repondre « Installer »
    # lancerait un pip de plusieurs centaines de mega-octets au milieu du
    # banc ; repondre « designer » ouvrirait un selecteur de fichier. None
    # vaut « Plus tard » : la boite est montree, et rien ne s'ensuit.
    def clickedButton(self): return None            # noqa: E704, N802

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
# LES DOUBLURES VALENT POUR TOUT MODULE DU PAQUET QUI NOMME UNE BOITE, et non
# plus pour plugin.py seul. La fenetre se repartit en modules de pages
# (docs/decoupage_dialogue.md) : une page qui ouvrirait une vraie boite, hors
# ecran, attendrait un clic qui ne vient jamais, et le banc resterait bloque.
# On parcourt donc les modules du paquet DEJA IMPORTES — plugin.py importe ses
# pages des son chargement — et l'on remplace chacun des trois noms que le
# module lie lui-meme. Une page future est ainsi couverte sans y repenser ;
# confirmer() aussi, ou qu'il vive, puisqu'il lit QMessageBox dans son module.
# Limite assumee : un module qui ecrirait « QtWidgets.QMessageBox » n'est pas
# vu ; aucun ne le fait.
_DOUBLURES = {"QInputDialog": dialogue, "QFileDialog": fichiers,
              "QMessageBox": BoiteMessage}
_modules_doubles = []
for _nom_module, _module in sorted(sys.modules.items()):
    if not _nom_module.startswith("calage_apports.") or _module is None:
        continue
    _lies = [_n for _n in _DOUBLURES if _n in vars(_module)]
    for _n in _lies:
        setattr(_module, _n, _DOUBLURES[_n])
    if _lies:
        _modules_doubles.append(_nom_module.split(".", 1)[1])
# Une boucle qui ne doublerait rien — paquet renomme, import deplace — ne
# se verrait qu'au premier blocage : on le dit ici, et on nomme les modules.
verifier("les boites sont doublees dans chaque module du paquet qui les nomme",
         "plugin" in _modules_doubles, ", ".join(_modules_doubles) or "aucun")

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
    # LE TYPE QUE LE PLUGIN A CHOISI, pas QMetaType ecrit en dur : QgsField ne
    # l'accepte que depuis QGIS 3.38, et ce banc s'arretait ici sous la 3.34,
    # le minimum que metadata.txt declare (11/11/2026).
    c.dataProvider().addAttributes([QgsField("nom", mod_plugin.TYPE_CHAMP_TEXTE)])
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
verifier("5 onglets crees (3 etapes + suivi + aide)",
         dlg.onglets.count() == 5,
         [dlg.onglets.tabText(i) for i in range(dlg.onglets.count())])

# LE GROUPE « EXCEL DES HYDROGRAMMES OBJECTIFS » EST GRIS TANT QU'AUCUN
# CLASSEUR N'EXISTE (0.8.4, demande utilisateur) — mais « Reprendre un
# Excel… » reste actif : c'est la SEULE porte d'entree vers un calage d'une
# autre session, et la griser avec le reste fermerait la reprise a cle. Le
# prefixe, lui, doit rester saisissable AVANT la composition, puisque c'est
# lui qui nomme le fichier a composer.
# HORS DU GATE « --modele » : la fenetre vient d'etre construite, son
# classeur vaut None, et rien ici ne demande un modele HEC-RAS.
verifier("avant composition : « Ouvrir dans Excel » est gris",
         not dlg.bouton_ouvrir_classeur.isEnabled(),
         f"classeur={dlg.classeur!r}")
verifier("avant composition : le prefixe de scenario reste saisissable",
         dlg.edit_prefixe_scenario.isEnabled())
# LE GESTE A POSER N'EST PLUS LE BOUTON : depuis le 21/09/2026 le paquet se
# compose tout seul des que le prefixe est la.
verifier("avant composition : l'attente est dite a l'ecran",
         "préfixe de scénario" in dlg.label_classeur_attente.text()
         and "tout seul" in dlg.label_classeur_attente.text(),
         dlg.label_classeur_attente.text()[:70])
if MODELE is None or not MODELE.exists():
    print("   ignore : aucun modele declare "
          "(--modele, ou variable CALAGE_MODELE_ESSAI)")
    p.classeur = None
else:
    # LE .prj, PAS LE DOSSIER — c'est ce que la fenetre demande depuis
    # qu'un selecteur de fichier a remplace le selecteur de dossier.
    _prj = next(MODELE.glob("*.prj"), MODELE / "projet.prj")
    dlg.edit_projet_hecras.setText(str(_prj))
    dlg._charger_projet_hecras(str(MODELE))
    verifier("projet HEC-RAS detecte", bool(dlg.info_projet),
             dlg.info_projet["nom_projet"] if dlg.info_projet else "")
    # ON DESIGNE LE FICHIER, ON DEDUIT LE DOSSIER. Un dossier de modele porte
    # des dizaines de fichiers et rien n'y distingue a l'oeil un projet
    # HEC-RAS ; le .prj, lui, EST le projet. Tout ce qui suit travaille
    # pourtant sur le dossier — geometrie, Unsteady Flow et .hdf en sont les
    # voisins — d'ou ce derive, que cinq lecteurs empruntent.
    verifier("le champ porte le .prj, pas le dossier",
             dlg.edit_projet_hecras.text().lower().endswith(".prj"),
             dlg.edit_projet_hecras.text())
    verifier("et le dossier s'en deduit, pour les cinq qui en ont besoin",
             Path(dlg._dossier_projet()) == MODELE,
             f"{dlg._dossier_projet()}")
    # La version n'est plus saisie : elle est lue dans les fichiers du
    # modele, la plus recente l'emportant en cas de melange.
    verifier("version HEC-RAS lue dans le modele, pas saisie",
             bool(dlg.version_hecras)
             and not hasattr(dlg, "edit_version_hecras"),
             f"{dlg.version_hecras} — {dlg.label_nom_projet.text()[:60]}")
    # ET ELLE EST DITE A PART (10/11/2026) : sous le projet, et au resume.
    verifier("la version qui calculera est dite sous le projet, et au resume",
             dlg.label_version_calage.text()
             == dlg._phrase_version(dlg.version_hecras,
                                    noyau.versions_hecras_installees())
             and not dlg.label_version_calage.isHidden()
             and f"HEC-RAS : {dlg.version_hecras}"
             in dlg.texte_resume.toPlainText().splitlines(),
             dlg.label_version_calage.text())

    numero_plan =(PLAN.with_suffix("").suffix.lstrip(".p")
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
    #   geometrie passe par lui. Le plugin ne le trouve seul que si c'est un
    #   .venv voisin de la chaine retenue ; ailleurs il faut le lui designer, et
    #   CALAGE_PYTHON dans l'environnement suffit pour cette suite.
    if dlg.couche_injections is None or dlg.couche_sections is None:
        print("\n   ARRET : sans les couches du modele, aucun des controles "
              "suivants n'a de sens.")
        print("   Le diagnostic de chargement ci-dessus dit pourquoi — un "
              "interpreteur HEC-RAS introuvable suffit a produire ceci.")
        print("   Le designer par CALAGE_PYTHON, ou par le bouton "
              "« Designer… » du plugin.")
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
    verifier("l'axe n'est pas pre-choisi par le plugin",
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
             "axe hydraulique" in _refus.lower() and "étape 1" in _refus.lower(),
             _refus[:90] or "aucun refus — la branche est morte")
    BoiteMessage.critiques.clear()

    dlg.combo_axe.setLayer(QgsProject.instance().mapLayersByName("Axe")[0])
    dlg.edit_dossier_sortie.setText(str(ESSAI))

    # LE PREFIXE DE SCENARIO EST OBLIGATOIRE (0.7.22). C'est ce qui rend
    # etrangeres les series de plans de deux scenarios : sans lui, caler le
    # Q10 apres le Q100 effacait les plans du Q100 un par un, en silence. Le
    # banc verifie donc le REFUS avant de le renseigner — et il doit le
    # renseigner, sans quoi tout ce qui suit tomberait sur ce refus.
    BoiteMessage.critiques.clear()
    dlg.edit_prefixe_scenario.setText("")
    dlg._composer_et_controler()
    _refus_prefixe = BoiteMessage.critiques[0] if BoiteMessage.critiques else ""
    verifier("sans prefixe de scenario, la composition refuse et dit pourquoi",
             "préfixe de scénario" in _refus_prefixe
             and "paramètres" in _refus_prefixe.lower(),
             _refus_prefixe[:100] or "aucun refus — la branche est morte")
    BoiteMessage.critiques.clear()
    dlg.edit_prefixe_scenario.setText("ESSAI")

    dlg._composer_et_controler()

    # LA RECOMPOSITION AUTOMATIQUE EST RETIREE (24/09/2026) : le bouton est le
    # seul appelant, et la composition ne doit pas laisser la fenetre
    # verrouillee derriere elle.
    verifier("la composition ne laisse pas la fenêtre verrouillée",
             not getattr(dlg, "_composition_en_cours", False)
             and not getattr(dlg, "_sablier_pose", False),
             f"en cours={getattr(dlg, '_composition_en_cours', None)}, "
             f"sablier={getattr(dlg, '_sablier_pose', None)}")

    # UN APPARIEMENT IMPOSSIBLE EST UN DIAGNOSTIC SUR LE MODELE, PAS UN ECHEC
    # DU PLUGIN — et c'est le banc qui le provoque.
    #
    # L'AXE DE CE BANC EST FABRIQUE : il enfile les centroides des injections
    # TRIES PAR LATITUDE (voir plus haut). Sur un modele d'essai, ou le banc
    # pose lui-meme une section par apport, cela suffit. Sur un modele REEL
    # qui porte ses PROPRES lignes de reference, cet axe n'est pas le fil de
    # l'eau : les PK n'ont plus de sens, deux sections tombent derriere la
    # meme injection, et le plugin refuse — a JUSTE TITRE, c'est meme le
    # garde-fou « la methode cale un apport contre UNE cible ».
    #   Le banc comptait ce refus comme quatre echecs. Mesure du 08/09/2026
    # sur deux modeles reels : « ARD08 » pour ARD08 et ARD07 sur l'un,
    # « SUH03 » pour SUH02 et SUH01 sur l'autre. Neuvieme defaut du meme
    # motif que les huit autres — il suppose le monde de son auteur, ici un
    # modele dont les sections s'ordonnent du sud au nord.
    #   CE QU'IL FAUT POUR EXERCER LA COMPOSITION : un modele qui porte des
    # lignes d'injection et AUCUNE ligne de reference — le banc pose alors
    # une section par apport, en aval de chacune, et l'appariement est 1:1
    # par construction. C'est le cas du plan TEST de Muncie augmente de ses
    # BC Line, avec lequel les 172 controles du 06/09 ont ete obtenus.
    _refus_compo = BoiteMessage.critiques[0] if BoiteMessage.critiques else ""
    _appariement_impossible = any(
        motif in _refus_compo
        for motif in ("alimenterait plusieurs sections",
                      "aucune ligne d'injection en amont"))
    if _appariement_impossible:
        print("   ignore : les sections que porte « "
              f"{MODELE.name} » ne s'apparient pas contre l'axe que ce banc "
              "fabrique — 4 controles de composition non joues.")
        print(f"            {_refus_compo[:150]}")
        print("            Il faut un modele SANS ligne de reference : le "
              "banc pose alors sa propre section par apport.")
        BoiteMessage.critiques.clear()
    else:
        verifier("aucune erreur remontee", not BoiteMessage.critiques,
                 BoiteMessage.critiques[0][:90] if BoiteMessage.critiques else "")
        # Le rapport porte le tableau des PK, plusieurs dizaines de lignes
        # larges : la fenetre qui le presente doit pouvoir s'agrandir.
        _rapport_compo = getattr(BoiteMessage, "dernier", None)
        verifier("« Contrôle paramétrage — compte rendu » est redimensionnable",
                 _rapport_compo is not None and _rapport_compo.redimensionnable,
                 "poignée posée" if _rapport_compo else "aucune boîte affichée")
        # « donnees_calage_ESSAI.xlsx » : depuis la 0.8.4, le prefixe de
        # scenario nomme le classeur — voir noyau.nom_classeur. Le banc
        # compose avec le prefixe « ESSAI ».
        attendus = ["sections_controle.shp", "lignes_injection.shp",
                    "axe_hydraulique.shp", "donnees_calage_ESSAI.xlsx"]
        presents = [f for f in attendus if (ESSAI / f).exists()]
        verifier("paquet ecrit", len(presents) == 4, f"{presents}")
        verifier("sous-dossiers resultats/suivi crees",
                 (ESSAI / "resultats_finaux").is_dir()
                 and (ESSAI / "suivi").is_dir())
        verifier("apres composition : « Ouvrir dans Excel » est actif",
                 dlg.bouton_ouvrir_classeur.isEnabled(),
                 f"classeur={dlg.classeur!r}")

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
            [QgsField("nom", mod_plugin.TYPE_CHAMP_TEXTE)])
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

        # --- LES COUCHES NE VIENNENT PLUS DE LA GEOMETRIE RETENUE ----------
        # Zone 2D et CRS ne sont pas des comptes rendus dates : ce sont des
        # valeurs courantes, consommees a l'ecriture. Changer de plan ne les
        # touche pas — elles datent alors d'une AUTRE geometrie.
        _geom_vraie = dlg.geom_couches
        verifier("aucune alerte tant que les couches suivent la geometrie",
                 not dlg.label_geom_couches.text(),
                 dlg.label_geom_couches.text()[:60] or "(vide)")
        dlg.geom_couches = "99"          # comme si le plan avait change depuis
        dlg._maj_alerte_couches()
        verifier("des qu'elles en viennent d'une autre, l'ecran le DIT",
                 "⚠" in dlg.label_geom_couches.text()
                 and "g99" in dlg.label_geom_couches.text(),
                 re.sub("<[^>]+>", "", dlg.label_geom_couches.text())[:80])
        dlg.geom_couches = _geom_vraie
        dlg._maj_alerte_couches()
        verifier("et l'alerte disparait quand elles se raccordent",
                 not dlg.label_geom_couches.text())

        # Reproduit exactement ce que fait PluginCalage.composer() une fois la
        # fenetre fermee : recuperer classeur/paquet sur l'objet plugin, pour
        # que les actions 2, 3 et 4 continuent d'y acceder ensuite.
        p.classeur, p.paquet = dlg.classeur, dlg.paquet

# ---------------------------------------------------------------------------
# IMPORTER DES HYDROGRAMMES D'UN CALCUL PRECEDENT (24/09/2026, demande
# utilisateur) — il remplace « Reprendre un Excel… ». Il n'ecrit que dans
# l'Excel de CE calcul, et seulement les cibles et les pentes : la fenetre
# garde son classeur. La regle d'appariement est eprouvee dans noyau.py ;
# ici, le geste de la fenetre et ce qu'elle en dit.
print("\n3. IMPORTER DES HYDROGRAMMES D'UN CALCUL PRECEDENT")
import openpyxl as _openpyxl_i                               # noqa: E402
_imp = mod_plugin.DialogueParametrage(iface)
verifier("le bouton porte le libelle demande, et reste gris sans Excel",
         _imp.bouton_importer.text().replace("\n", " ")
         == "&Importer des hydrogrammes d'un calcul précédent…"
         and not _imp.bouton_importer.isEnabled(),
         f"{_imp.bouton_importer.text()} | actif={_imp.bouton_importer.isEnabled()}")
_bac_imp = Path(tempfile.mkdtemp(prefix="import_hydrogrammes_"))
_ce_calcul = noyau.preparer_classeur(
    _bac_imp / "ce_calcul", [("A1", "S1"), ("A2", "S2"), ("A3", "S3")], {},
    parametres={"Prefixe_scenario": "Q100"})
_precedent = noyau.preparer_classeur(
    _bac_imp / "precedent", [("A1", "S1"), ("A2", "S2"), ("A9", "S9")], {},
    parametres={"Prefixe_scenario": "Q100"})
_wb_p = _openpyxl_i.load_workbook(_precedent)
_f_p = _wb_p["Cibles"]
_rang = {c.value: c.column for c in _f_p[1] if c.value}
for _ligne, _t in enumerate((0.0, 1.0, 2.0), start=2):
    _f_p.cell(row=_ligne, column=_rang["Temps_h"], value=_t)
    _f_p.cell(row=_ligne, column=_rang["Cible_S1"], value=10.0 + _t)
    _f_p.cell(row=_ligne, column=_rang["Cible_S9"], value=90.0 + _t)
_wb_p.save(_precedent)
_imp.classeur = str(_ce_calcul)
verifier("il s'active des qu'un Excel existe", _imp.bouton_importer.isEnabled())
_json_avant = (_ce_calcul.with_suffix(".json").stat().st_mtime_ns
               if _ce_calcul.with_suffix(".json").exists() else None)
_messages_imp = []
_imp._signaler = lambda titre, texte, *a, **k: _messages_imp.append((titre, texte))
fichiers.fichiers = [str(_precedent)]
_imp._importer_hydrogrammes()
_compte_rendu = _imp.label_import.text()
verifier("le compte rendu nomme les hydrogrammes importes",
         "Cible_S1" in _compte_rendu and "1 hydrogramme importé"
         in _compte_rendu, re.sub("<[^>]+>", "", _compte_rendu)[:120])
verifier("et les colonnes restees vides faute de correspondance",
         "Restent vides" in _compte_rendu and "Cible_S2" in _compte_rendu
         and "Cible_S3" in _compte_rendu, re.sub("<[^>]+>", "", _compte_rendu)[:200])
verifier("rien d'autre : la fenetre garde son classeur, le JSON n'est pas touche",
         _imp.classeur == str(_ce_calcul)
         and (_json_avant is None
              or _ce_calcul.with_suffix(".json").stat().st_mtime_ns == _json_avant),
         str(_imp.classeur))
verifier("les valeurs sont dans l'Excel de ce calcul",
         [c.value for c in _openpyxl_i.load_workbook(_ce_calcul)["Cibles"]["B"][1:4]]
         == [10.0, 11.0, 12.0],
         str([c.value for c in
              _openpyxl_i.load_workbook(_ce_calcul)["Cibles"]["B"][1:4]]))
# LES CIBLES NE CORRESPONDENT PAS : on le dit, dans la page, et rien ne bouge.
_autre = noyau.preparer_classeur(_bac_imp / "autre", [("B1", "T1")], {},
                                 parametres={"Prefixe_scenario": "Q10"})
_wb_a = _openpyxl_i.load_workbook(_autre)
_wb_a["Cibles"]["A2"], _wb_a["Cibles"]["B2"] = 0.0, 5.0
_wb_a.save(_autre)
_avant_refus = _ce_calcul.stat().st_mtime_ns
fichiers.fichiers = [str(_autre)]
_imp._importer_hydrogrammes()
verifier("sans cible commune, l'import le dit et n'ecrit rien",
         "Rien n’a été importé" in _imp.label_import.text()
         and "Cible_T1" in _imp.label_import.text()
         and _ce_calcul.stat().st_mtime_ns == _avant_refus
         and _messages_imp[-1][0] == "Hydrogrammes non importés",
         re.sub("<[^>]+>", "", _imp.label_import.text())[:140])
_imp.close()
_imp.deleteLater()
shutil.rmtree(_bac_imp, ignore_errors=True)

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
    dlg2.edit_projet_hecras.setText(
        str(next(Path(faux_projet).glob("*.prj"), Path(faux_projet) / "x.prj")))
    dlg2._charger_projet_hecras(str(faux_projet))
    index = next((i for i in range(dlg2.combo_plan.count())
                  if dlg2.combo_plan.itemData(i)["numero"] == numero_plan), 0)
    dlg2.combo_plan.setCurrentIndex(index)
    dlg2._charger_couches_modele()

    verifier("zone 2D renseignee par le chargement",
             bool(dlg2.combo_zone_2d.currentText()),
             dlg2.combo_zone_2d.currentText())
    # Une seule zone 2D geree (27/10/2026) : aucun choix dans la fenetre.
    verifier("aucun choix de zone 2D dans la fenetre",
             dlg2.combo_zone_2d not in dlg2.findChildren(
                 type(dlg2.combo_zone_2d)),
             f"{dlg2.combo_zone_2d.count()} zone(s)")
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
    # pas inversee, le plugin a raison de ne rien signaler, et le test
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
    _dlg3.edit_projet_hecras.setText(
        str(next(Path(faux_projet).glob("*.prj"), Path(faux_projet) / "x.prj")))
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
    _compte_rendu = ""
    try:
        _compte_rendu = dlg2._ecrire_dans_geometrie()
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

    # LE COMPTE RENDU N'EST PLUS UN LABEL DE L'ONGLET 1 (0.7.19) : il est
    # RENDU a l'appelant, qui l'ouvre en tete de la boite de composition — la
    # seule visible depuis l'endroit ou l'on a clique.
    verifier("l'ecriture rend son compte rendu a l'appelant",
             bool(_compte_rendu) and "crit dans" in _compte_rendu,
             _compte_rendu[:80])
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
verifier("5 onglets, dont le suivi et l'aide", dlg.onglets.count() == 5,
         [dlg.onglets.tabText(i) for i in range(dlg.onglets.count())])
# LES ETAPES SONT DANS LA BANDE COMMUNE (23/10/2026), dans l'ordre des pages.
# La barre d'onglets qu'elle remplace demandait 816 px a 9 pt et 993 a 13 pt,
# d'ou un plancher de largeur et des titres elides : ce que l'on controlait
# ici. On controle desormais que la bande nomme chaque etape, dans l'ordre,
# qu'aucune ligne de ses entrees ne deborde de sa largeur, et que la barre
# d'onglets ne revient pas a cote d'elle.
dlg.ensurePolished()
_bande = dlg.bande
verifier("la bande nomme les cinq etapes, dans l'ordre des pages",
         _bande.count() == dlg.onglets.count()
         and [_bande.item(i).data(mod_plugin.Qt.ItemDataRole.AccessibleTextRole)
              for i in range(_bande.count())]
         == [dlg.onglets.tabText(i) for i in range(dlg.onglets.count())]
         and _bande.item(mod_plugin.ONGLET_AIDE).text().startswith("?"),
         str([_bande.item(i).text() for i in range(_bande.count())]))
_bande.ensurePolished()
_metrique_bande = mod_plugin.QFontMetrics(_bande.font())
_utile = _bande.width() - 2 * _bande.frameWidth()
_plus_large = max(_metrique_bande.horizontalAdvance(m) for i in range(_bande.count())
                  for m in _bande.item(i).text().split("\n"))
verifier("aucune entree de la bande ne deborde de sa largeur",
         _plus_large <= _utile, f"{_plus_large} px pour {_utile} px")
verifier("la barre d'onglets est cachee, la bande la remplace",
         dlg.onglets.tabBar().isHidden() and not _bande.isHidden())
dlg.onglets.setCurrentIndex(mod_plugin.ONGLET_SUIVI)
_suit = _bande.currentRow() == mod_plugin.ONGLET_SUIVI
_bande.setCurrentRow(mod_plugin.ONGLET_LANCER)
verifier("la bande et les pages se suivent dans les deux sens",
         _suit and dlg.onglets.currentIndex() == mod_plugin.ONGLET_LANCER,
         f"bande {_bande.currentRow()}, page {dlg.onglets.currentIndex()}")
dlg.onglets.setCurrentIndex(mod_plugin.ONGLET_MODELE)
# LES RANGS NOMMES TOMBENT SUR LEUR ONGLET. Deux methodes basculent d'onglet
# apres une action ; un indice devenu faux ferait afficher l'onglet voisin sans
# que rien ne le signale — Qt ne s'en plaint pas.
verifier("les rangs nommes designent le bon onglet",
         dlg.onglets.tabText(mod_plugin.ONGLET_MODELE).startswith("1.")
         and dlg.onglets.tabText(mod_plugin.ONGLET_LANCER).startswith("3.")
         and dlg.onglets.tabText(mod_plugin.ONGLET_SUIVI).startswith("4.")
         and dlg.onglets.tabText(mod_plugin.ONGLET_AIDE).startswith("Aide")
         and mod_plugin.DERNIER_ONGLET == dlg.onglets.count() - 1,
         f"{mod_plugin.ONGLET_MODELE}={dlg.onglets.tabText(mod_plugin.ONGLET_MODELE)} | "
         f"{mod_plugin.ONGLET_LANCER}={dlg.onglets.tabText(mod_plugin.ONGLET_LANCER)} | "
         f"{mod_plugin.ONGLET_SUIVI}={dlg.onglets.tabText(mod_plugin.ONGLET_SUIVI)} | "
         f"{mod_plugin.ONGLET_AIDE}={dlg.onglets.tabText(mod_plugin.ONGLET_AIDE)} "
         f"(dernier : {dlg.onglets.count() - 1})")

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
verifier("suivi : sans classeur, le dossier surveille revient a l'onglet Sorties",
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
            # « debut » N'EST PLUS FACULTATIF : c'est lui qui dit desormais si
            # l'etat est celui du calage qu'on vient de lancer. Par defaut on
            # le pose maintenant, cas normal d'un calage qui tourne.
            "debut": datetime.now().isoformat(timespec="seconds"),
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

# ERREURS ET AVERTISSEMENTS REMONTES DU JOURNAL (0.8.4, demande
# utilisateur). Ils ne vivaient que dans le .log dont la banniere donnait le
# chemin. Le banc ecrit un journal qui melange le bruit de ras-commander et
# les lignes qui comptent, et verifie que seules les secondes paraissent.
_journal_essai = _dossier_etat() / "calage_20260914_082326.log"
_journal_essai.write_text(
    "ras-commander v0.99.2 | An open-source project\n"
    "PROJECT DATAFRAMES (single source of truth)\n"
    "AVERTISSEMENT : cible « Cible_SUH01 » : pas de temps 30 min \u2192 "
    "converti en 6 min\n"
    "   pente de « SUH12 » : 0.00034676 m/m\n"
    "    ARRET : le calcul de reference (apports a zero) n'est pas "
    "exploitable\n",
    encoding="utf-8")
_journal_garde = dlg.journal_lance
dlg.journal_lance = str(_journal_essai)
dlg._rafraichir_suivi()
_alertes = dlg.texte_alertes.toPlainText()
verifier("suivi : l'arret du journal parait a l'ecran",
         "ARRET" in _alertes, _alertes[-80:] or "(vide)")
verifier("suivi : l'avertissement de recadencement parait aussi",
         "converti en 6 min" in _alertes, _alertes[:80] or "(vide)")
verifier("suivi : le bruit de ras-commander est ecarte",
         "PROJECT DATAFRAMES" not in _alertes
         and "open-source project" not in _alertes,
         f"{len(_alertes.splitlines())} ligne(s) retenue(s)")
# isHidden() et non isVisibleTo() : la fenetre du banc n'est jamais montree,
# et isVisibleTo remonte une chaine de parents dont aucun n'est affiche.
# isHidden() ne lit que le drapeau pose par setVisible, qui est ce qu'on
# verifie ici.
verifier("suivi : l'encadre des alertes se montre quand il a quelque chose",
         not dlg.groupe_alertes.isHidden())
_journal_essai.unlink()
dlg.journal_lance = _journal_garde
dlg._rafraichir_suivi()
verifier("suivi : sans journal, l'encadre des alertes disparait",
         dlg.groupe_alertes.isHidden()
         and not dlg.texte_alertes.toPlainText(),
         dlg.texte_alertes.toPlainText()[:60] or "(vide)")

# LE CAS QUI MANQUAIT : le processus n'existe plus et aucun verdict n'a ete
# rendu. Sans cela l'affichage restait fige sur le dernier etat connu, en
# laissant croire que le calcul avance encore.
_ecrire_etat(pid=999999)
dlg._rafraichir_suivi()
verifier("suivi : un calage mort est annonce INTERROMPU",
         "interrompu" in dlg.label_suivi_banniere.text().lower(),
         dlg.label_suivi_banniere.text()[:90])

# LE CALAGE PRECEDENT RESTE A L'ECRAN (0.8.3, demande utilisateur). Relancer
# remettait l'onglet a zero : les apports deja cales disparaissaient du ruban,
# du tableau et du trace, et rien ne disait qu'ils avaient existe. suivi.py
# archive desormais l'etat d'avant ; l'affichage garde ceux que le calage en
# cours NE traite pas — exactement ce qu'une reprise conserve — et les trace
# derriere.
(_dossier_etat() / "avancement_precedent.json").write_text(
    json.dumps({
        "apports": [
            {"ordre": 1, "apport": "A0", "section": "SC0", "statut": "validé",
             "essais": 2, "volume_pct": 100.1, "pic_pct": 99.7},
            # A1 EST AUSSI DANS LE CALAGE EN COURS : c'est celui qu'on refait,
            # et l'etat courant fait foi pour lui. Il ne doit pas apparaitre
            # deux fois dans le tableau.
            {"ordre": 2, "apport": "A1", "section": "SC1", "statut": "validé",
             "essais": 1, "volume_pct": 99.0, "pic_pct": 100.0},
            # UN ECHEC N'EST PAS UN ACQUIS : il n'a pas d'hydrogramme retenu,
            # et le reprendre laisserait croire a un resultat.
            {"ordre": 3, "apport": "AX", "section": "SCX", "statut": "échoué",
             "essais": 5, "volume_pct": 91.0, "pic_pct": 88.0}],
        "courbes_precedentes": [
            {"apport": "A0", "section": "SC0", "temps": [0.0, 1.0, 2.0],
             "debit": [0.0, 5.0, 0.0]}],
        "courbes": None}, ensure_ascii=False), encoding="utf-8")
_ecrire_etat()
dlg._rafraichir_suivi()
_lignes = [dlg.table_suivi.item(i, 0).text()
           for i in range(dlg.table_suivi.rowCount())]
verifier("suivi : les apports du calage precedent restent au tableau",
         _lignes == ["A0", "A1", "A2", "A3"], str(_lignes))
verifier("suivi : ils y sont marques « repris », et non « validé »",
         "repris" in dlg.table_suivi.item(0, 2).text()
         and "validé" in dlg.table_suivi.item(1, 2).text(),
         f"{dlg.table_suivi.item(0, 2).text()} | "
         f"{dlg.table_suivi.item(1, 2).text()}")
verifier("suivi : un apport que le calage en cours refait n'est pas double",
         _lignes.count("A1") == 1, str(_lignes))
verifier("suivi : un apport en echec au calage precedent n'est pas repris",
         "AX" not in _lignes, str(_lignes))
verifier("suivi : l'apport en cours reste designe malgre le decalage du ruban",
         dlg.ruban_apports.en_cours == 2
         and dlg.ruban_apports.apports[2].get("apport") == "A2",
         f"en_cours={dlg.ruban_apports.en_cours} "
         f"apports={[a.get('apport') for a in dlg.ruban_apports.apports]}")
_anterieures = [c for c in dlg.courbe_suivi.precedentes if c.get("anterieur")]
verifier("suivi : les hydrogrammes du calage precedent sont traces derriere",
         [c["apport"] for c in _anterieures] == ["A0"],
         str([c["apport"] for c in dlg.courbe_suivi.precedentes]))

# TRI AU DOUBLE-CLIC SUR UN EN-TETE (27/10/2026, comme Rhoe). Seul l'ordre
# AFFICHE change : item(rang, ...) lit toujours le meme apport.
from qgis.PyQt.QtCore import Qt  # noqa: E402


def _ordre_suivi():
    _v = dlg.table_suivi.verticalHeader()
    return [dlg.table_suivi.item(_v.logicalIndex(p), 0).text()
            for p in range(dlg.table_suivi.rowCount())]


def _apports_tri(volume_a2=None):
    return [
        {"apport": "A1", "section": "SC1", "statut": "validé", "essais": 2,
         "volume_pct": 99.0, "pic_pct": 100.0},
        {"apport": "A2", "section": "SC2", "statut": "en attente", "essais": None,
         "volume_pct": volume_a2, "pic_pct": None},
        {"apport": "A3", "section": "SC3", "statut": "validé", "essais": 3,
         "volume_pct": 100.5, "pic_pct": 98.2},
        {"apport": "A4", "section": "SC4", "statut": "échoué", "essais": 6,
         "volume_pct": 9.5, "pic_pct": 50.0}]


_entete_suivi = dlg.table_suivi.horizontalHeader()
dlg._remplir_table_suivi(_apports_tri())
_entete_suivi.sectionDoubleClicked.emit(4)
verifier("suivi : double-clic sur « Volume » : croissant, « 9,5 % » avant "
         "« 99,0 % », « — » en dernier, indicateur pose",
         _ordre_suivi() == ["A4", "A1", "A3", "A2"]
         and _entete_suivi.isSortIndicatorShown()
         and _entete_suivi.sortIndicatorSection() == 4
         and _entete_suivi.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder,
         str(_ordre_suivi()))
# Un double-clic commence par un clic, qui retourne la fleche de Qt sans rien classer.
_entete_suivi.setSortIndicator(4, Qt.SortOrder.DescendingOrder)
verifier("suivi : un simple clic ne retourne pas la fleche",
         _entete_suivi.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
         and _ordre_suivi() == ["A4", "A1", "A3", "A2"], str(_ordre_suivi()))
_entete_suivi.sectionDoubleClicked.emit(4)
verifier("suivi : second double-clic : decroissant, « — » toujours en dernier",
         _ordre_suivi() == ["A3", "A1", "A4", "A2"]
         and _entete_suivi.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder,
         str(_ordre_suivi()))
dlg._remplir_table_suivi(_apports_tri(volume_a2=120.0))
verifier("suivi : le rafraichissement reclasse, les rangs logiques ne bougent pas",
         _ordre_suivi() == ["A2", "A3", "A1", "A4"]
         and dlg.table_suivi.item(1, 0).text() == "A2",
         str(_ordre_suivi()))
_entete_suivi.sectionDoubleClicked.emit(4)
verifier("suivi : troisieme double-clic : retour a l'ordre du calage",
         _ordre_suivi() == ["A1", "A2", "A3", "A4"]
         and not _entete_suivi.isSortIndicatorShown(),
         str(_ordre_suivi()))
# Les cases cochees en tete ; une cellule ordinaire n'est pas une case, bien
# que Qt la dise « cochable » par defaut.
from qgis.PyQt.QtWidgets import QTableWidgetItem as _QTWI  # noqa: E402
_t_cases = mod_plugin.TableauTriable(3, 2)
for _r, (_coche, _val) in enumerate(((False, "12"), (True, "3"), (False, "—"))):
    _case = _QTWI("")
    _case.setCheckState(Qt.CheckState.Checked if _coche else Qt.CheckState.Unchecked)
    _t_cases.setItem(_r, 0, _case)
    _t_cases.setItem(_r, 1, _QTWI(_val))


def _ordre_cases():
    return [_t_cases.verticalHeader().logicalIndex(p) for p in range(3)]


_t_cases.horizontalHeader().sectionDoubleClicked.emit(0)
verifier("tri : une case cochee passe en tete", _ordre_cases()[0] == 1,
         str(_ordre_cases()))
_t_cases.horizontalHeader().sectionDoubleClicked.emit(1)
verifier("tri : une cellule ordinaire se classe comme un nombre, pas comme une case",
         _ordre_cases() == [1, 0, 2], str(_ordre_cases()))
_t_cases.deleteLater()

(_dossier_etat() / "avancement_precedent.json").unlink()
dlg._rafraichir_suivi()
verifier("suivi : sans archive, le tableau ne parle que du calage en cours",
         dlg.table_suivi.rowCount() == 3,
         f"{dlg.table_suivi.rowCount()} ligne(s)")

# CE QU'UN RELANCEMENT CONSERVE ET CE QU'IL PERD (0.8.3). Le calcul est une
# fonction pure : c'est lui qui remplit la question posee au lancement, et
# c'est lui qu'il faut eprouver — la boite ne fait que l'afficher.
_TOUS = ["A1", "A2", "A3", "A4"]
verifier("reprise : un depart choisi nomme les conserves et les perdus",
         mod_plugin.plan_de_reprise(_TOUS, ["A1", "A2"], "A2")
         == (["A1"], ["A2"], None),
         str(mod_plugin.plan_de_reprise(_TOUS, ["A1", "A2"], "A2")))
verifier("reprise : sans depart, tout ce qui etait cale est perdu",
         mod_plugin.plan_de_reprise(_TOUS, ["A1", "A2"], "")[:2]
         == ([], ["A1", "A2"]),
         str(mod_plugin.plan_de_reprise(_TOUS, ["A1", "A2"], "")))
verifier("reprise : le depart propose est le premier apport non valide",
         mod_plugin.plan_de_reprise(_TOUS, ["A1", "A2"], "")[2] == "A3",
         str(mod_plugin.plan_de_reprise(_TOUS, ["A1", "A2"], "")[2]))
verifier("reprise : un calage complet ne propose aucun depart",
         mod_plugin.plan_de_reprise(_TOUS, _TOUS, "")[2] is None,
         str(mod_plugin.plan_de_reprise(_TOUS, _TOUS, "")))

(_dossier_etat() / "avancement.json").unlink()
dlg._rafraichir_suivi()
verifier("suivi : sans etat, rien n'est invente",
         "aucun calage" in dlg.label_suivi_banniere.text().lower()
         and dlg.table_suivi.rowCount() == 0,
         dlg.label_suivi_banniere.text()[:80])
# ET SANS CALAGE PRECEDENT, LE LANCEMENT NE DEMANDE RIEN : la question de
# reprise ne se pose que s'il y a quelque chose a perdre. Posee a chaque
# lancement, elle s'apprendrait par coeur et ne se lirait plus.
verifier("reprise : sans calage precedent, le lancement ne demande rien",
         dlg._confirmer_reprise() is True)
# ET LA BANNIERE DIT OU ELLE REGARDE. Un suivi muet parce qu'il regardait le
# mauvais dossier ne se distinguait en rien d'un calage pas encore parti.
verifier("suivi : sans etat, la banniere nomme le dossier qu'elle surveille",
         # LE DOSSIER A QUITTE LA BANNIERE POUR UN LABEL PERMANENT (0.7.9) :
         # il n'y etait nomme que faute de calage a montrer, c'est-a-dire
         # jamais pendant les heures ou cet onglet sert.
         str(_dossier_etat()) in dlg.label_suivi_dossier.text().replace("\u200b", ""),
         dlg.label_suivi_banniere.text()[-100:])
# LE CHEMIN SURVEILLE PASSE A LA LIGNE (23/10/2026) : sans point de coupure,
# Qt ne coupe pas un chemin sans espace, et la page Suivi defilait de 69 px a
# 13 pt sur 720 px. La largeur minimale du label tombe sous celle du chemin.
verifier("suivi : le chemin du dossier surveille peut passer a la ligne",
         dlg.label_suivi_dossier.minimumSizeHint().width()
         < dlg.label_suivi_dossier.fontMetrics().horizontalAdvance(str(_dossier_etat())),
         f"label {dlg.label_suivi_dossier.minimumSizeHint().width()} px, chemin "
         f"{dlg.label_suivi_dossier.fontMetrics().horizontalAdvance(str(_dossier_etat()))} px")

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

# --- UN CALAGE QUI TOURNE FERME LES DEUX PORTES -----------------------------
# Ni la composition ni le lancement ne consultaient l'etat du calage, alors
# que l'onglet 5 le lit toutes les deux secondes. Recomposer pendant un calcul
# reecrit la geometrie et le classeur que ce calcul partage ; relancer fait
# travailler deux calages sur les memes plans.
# L'etat pose ci-dessus porte le PID de CE processus et « termine: false » :
# il decrit donc, pour le plugin, un calage bel et bien vivant.
# UNE QUESTION, PAS UN VERROU : le mannequin repond « non », et c'est la
# reponse par defaut voulue — l'action doit etre refusee.
verifier("un calage vivant est detecte, et nomme",
         (dlg._calage_en_cours() or {}).get("pid") == os.getpid(),
         f"pid detecte : {(dlg._calage_en_cours() or {}).get('pid')} "
         f"/ le notre : {os.getpid()}")
BoiteMessage.dernier = None
verifier("il fait refuser composer et lancer, par defaut",
         dlg._confirmer_malgre_calage("essai", geste="Recomposer") is False)
# LE DEFAUT EST POSE, ET C'EST LE REFUS (0.8.5). QMessageBox.question(Yes | No)
# sans defaultButton laissait Qt choisir — et sur Oui/Non il ne retenait
# rien : Entree allait au premier bouton autoDefault, « Oui ». La docstring
# promettait « non » ; confirmer() le pose, et le mannequin l'enregistre.
_boite_calage = BoiteMessage.dernier
verifier("la question « calage en cours » a pour defaut le refus, et des verbes",
         _boite_calage is not None and _boite_calage.bouton_defaut is not None
         and _boite_calage.bouton_defaut.role == _RolesBouton.RejectRole
         and _boite_calage.bouton_echappement is _boite_calage.bouton_defaut
         and [b.text() for b in _boite_calage.boutons]
         == ["Recomposer quand même", "Attendre la fin du calage"],
         str([b.text() for b in _boite_calage.boutons]) if _boite_calage
         else "aucune boite")
# ET UN CALAGE TERMINE NE FERME RIEN : son avancement.json reste en place, et
# son PID a pu etre reattribue depuis.
_ecrire_etat(termine=True)
dlg._rafraichir_suivi()
verifier("un calage TERMINE ne ferme aucune porte",
         dlg._calage_en_cours() is None
         and dlg._confirmer_malgre_calage("essai") is True,
         f"etat : {dlg._calage_en_cours()}")

# --- CE QU'ON RETIENT DU LANCEMENT REDRESSE TROIS AFFICHAGES ----------------
# _lancer_calage recevait le PID et le chemin du journal, les mettait dans une
# boite d'information, et les perdait. Trois choses mentaient faute d'eux.
_fichier_etat = _dossier_etat() / "avancement.json"
if _fichier_etat.exists():
    _fichier_etat.unlink()
dlg.pid_lance = dlg.journal_lance = None
dlg._rafraichir_suivi()
verifier("sans lancement retenu, le suivi attend sans rien inventer",
         "Aucun calage suivi" in dlg.label_suivi_banniere.text(),
         dlg.label_suivi_banniere.text()[:60])

# UN PID QUI N'EXISTE PAS, ET DU TEMPS ECOULE : le calage est mort avant
# d'ecrire quoi que ce soit. La branche promettait « quelques secondes apres le
# lancement » pour toujours.
#   LE DELAI EST INDISPENSABLE DEPUIS LE 08/09/2026 : quand l'interpreteur
# HEC-RAS est un relais, le processus rendu par Popen disparait aussitot apres
# avoir lance le vrai. Sans patience, le suivi annoncait « mort au demarrage »
# trois secondes apres un lancement qui se deroulait bien.
dlg.pid_lance, dlg.journal_lance = 999999, r"D:\essai\lancement.log"
dlg.instant_lance = datetime.now() - timedelta(
    seconds=mod_plugin.DELAI_PREMIER_ETAT_S + 5)
dlg._rafraichir_suivi()
verifier("« mort au demarrage » se distingue de « pas encore parti »",
         "mort" in dlg.label_suivi_banniere.text().lower(),
         dlg.label_suivi_banniere.text()[:90])
verifier("et le seul document qui dit pourquoi est NOMME",
         "lancement.log" in dlg.label_suivi_banniere.text())

# ET AVANT LE DELAI, ON ATTEND. Meme PID mort, meme absence d'etat : tant que
# le calage n'a pas eu le temps d'ecrire, on ne le declare pas mort.
dlg.instant_lance = datetime.now()
dlg._rafraichir_suivi()
verifier("avant le delai, un PID disparu ne fait pas conclure a la mort",
         "mort" not in dlg.label_suivi_banniere.text().lower()
         and "Calage lancé" in dlg.label_suivi_banniere.text(),
         dlg.label_suivi_banniere.text()[:90])

# L'ETAT D'UN AUTRE CALAGE NE SE PEINT PAS COMME LE NOTRE. Apres un
# relancement, le dossier porte encore l'avancement.json du precedent : on
# peignait « Calage termine — conforme » en reponse au lancement qui venait
# d'aboutir.
dlg.instant_lance = datetime.now()
_ecrire_etat(pid=424242, termine=True, conforme=True,
             debut=(datetime.now() - timedelta(hours=3)).isoformat(
                 timespec="seconds"))
dlg._rafraichir_suivi()
verifier("l'etat d'un calage precedent n'est pas donne pour le notre",
         "précédent" in dlg.label_suivi_banniere.text()
         and "conforme" not in dlg.label_suivi_banniere.text().lower(),
         dlg.label_suivi_banniere.text()[:100])

# --- ET C'EST L'HEURE QUI TRANCHE, PAS LE PID -------------------------------
# LE DEFAUT QUI A COUTE UN CALAGE ENTIER (08/09/2026, Q20 sur poste distant).
# Le PID rendu par Popen n'est PAS celui qui ecrit l'etat quand l'interpreteur
# HEC-RAS est un relais — python.exe de 256 ko d'un venv cree depuis le Python
# de QGIS, ce que le bouton « Installer… » propose lui-meme. Mesure : Popen
# rend 55160, le processus qui tourne est 23284.
#   La comparaison de PID declarait donc « etat d'un calage precedent » LE
# CALAGE EN COURS, pendant toute sa duree — c'est-a-dire pendant exactement
# les heures ou l'on regarde cet onglet.
dlg.instant_lance = datetime.now() - timedelta(minutes=2)
_ecrire_etat(pid=424242,        # un PID qui n'est pas celui du lancement
             debut=datetime.now().isoformat(timespec="seconds"))
dlg._rafraichir_suivi()
verifier("un etat COMMENCE APRES le lancement est le notre, PID different ou "
         "non",
         "précédent" not in dlg.label_suivi_banniere.text()
         and "A2" in dlg.label_suivi_position.text(),
         dlg.label_suivi_banniere.text()[:90])

# ET LE FIL CESSE D'ORDONNER « LANCER » PENDANT LES HEURES DU CALCUL.
dlg._maj_fil()
verifier("le fil dit que le calage tourne, il n'ordonne plus de lancer",
         "calage lancé" in dlg.label_fil.text().lower()
         and "puis lancer" not in dlg.label_fil.text(),
         dlg.label_fil.text()[-80:])
dlg.pid_lance = dlg.journal_lance = None
dlg._maj_fil()  # Le banc change l'etat directement : rafraichir aussi le bouton.

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
    # LES PARAMETRES NE SONT PLUS DANS LE CLASSEUR (20 septembre 2026) : on
    # les relit par le module qui les porte, celui-la meme que la chaine
    # utilise. Les relire a la main ici aurait refait une seconde regle.
    import parametres as _parametres

    def _parametre(cle):
        return _parametres.lire(dlg.classeur).get(cle)

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
    # du plugin la ou il manque un fichier de configuration.
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
         _repli_tient or not hasattr(QVariant, "String"),  # PyQt6 : QGIS >= 3.38, repli jamais pris
         _repli_motif)

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

# LE MAILLAGE NE TIENT JAMAIS OUVERT LE .gXX.hdf DU PROJET. Une couche MDAL
# sur l'original empechait HEC-RAS de le reecrire, et le calcul tournait sur
# l'ancien pretraitement (modele reel, 27/10/2026).
_bac_maillage = Path(tempfile.mkdtemp(prefix="copie_maillage_"))
_original = _bac_maillage / "ESSAI.g01.hdf"
_original.write_bytes(b"version 1")
_copie_1 = mod_plugin.copie_pour_maillage(_original)
verifier("la couche de maillage lit une copie, pas le fichier du projet",
         _copie_1 is not None and _copie_1 != _original
         and _copie_1.read_bytes() == b"version 1", f"{_copie_1}")
_avant_ns = _original.stat().st_mtime_ns
_original.write_bytes(b"version 2, plus longue")
os.utime(_original, ns=(_avant_ns, _avant_ns + 10**9))
_copie_2 = mod_plugin.copie_pour_maillage(_original)
verifier("un .gXX.hdf reecrit donne une copie neuve, l'ancienne est effacee",
         _copie_2 is not None and _copie_2 != _copie_1
         and _copie_2.read_bytes() == b"version 2, plus longue"
         and not _copie_1.exists(), f"{_copie_1.name} -> {_copie_2}")
verifier("sans .gXX.hdf (geometrie jamais pretraitee), pas de copie",
         mod_plugin.copie_pour_maillage(_bac_maillage / "ABSENT.g02.hdf") is None)
_copie_2.unlink(missing_ok=True)
shutil.rmtree(_bac_maillage, ignore_errors=True)

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
    "TransformationMode|ContextMenuPolicy|WidgetAttribute|ArrowType|ShortcutContext|ApplicationState|"
    "FocusReason|TextFlag")
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
# SUR TOUS LES .py DU PLUGIN, et non plus sur plugin.py seul : la fenetre se
# repartit en modules (widgets, socle, pages), et une constante nue ecrite
# dans l'un d'eux echappait au controle. Le detail nomme le fichier.
_FICHIERS_PLUGIN = sorted(Path(mod_plugin.__file__).parent.glob("*.py"))
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
    _nus = sorted({f"{_f.name}:{_m}" for _f in _FICHIERS_PLUGIN
                   for _m in re.findall(
                       rf"\b{_classe}\.(?!(?:{_portees})\b)([A-Z][A-Za-z_0-9]+)",
                       _f.read_text(encoding="utf-8"))})
    verifier(f"aucune constante {_classe} non qualifiee (Qt6)",
             not _nus, ", ".join(_nus[:4]) or "aucune")


# LA FENETRE DE CRUE EXISTE EN DEUX EXEMPLAIRES — plugin et livrables.py — et
# c'est un choix : fusionner ferait entrer matplotlib dans un paintEvent. Ce
# qui est interdit, c'est qu'elles divergent : la courbe du suivi et la figure
# du livrable cadreraient alors deux fenetres differentes, sans que rien ne le
# dise. Les deux constantes sont donc comparees ici, sur le TEXTE des deux
# fichiers — ce qui n'exige d'importer ni matplotlib ni la chaine.
#   LE COTE PLUGIN EST LE FICHIER QUI DEFINIT _fenetre_crue, et non plus
# plugin.py ecrit en dur : la courbe du suivi et sa fenetre de crue quittent
# plugin.py (docs/decoupage_dialogue.md). Suivre la fonction garde le
# controle sur le code qui trace reellement, ou qu'il vive.
_FICHIER_CRUE = Path(sys.modules[mod_plugin._fenetre_crue.__module__].__file__)
_CRUE = {}
for _quel, _fichier in (("plugin", _FICHIER_CRUE),
                        ("livrables", CHAINE / "livrables.py")):
    _texte = _fichier.read_text(encoding="utf-8")
    _CRUE[_quel] = {
        _c: (re.search(rf"^{_c} = ([0-9.]+)", _texte, re.M) or [None, None])[1]
        for _c in ("SEUIL_CRUE", "MARGE_CRUE_H")}
verifier("la fenetre de crue est nommee des deux cotes",
         all(v is not None for d in _CRUE.values() for v in d.values()),
         f"plugin={_CRUE['plugin']} livrables={_CRUE['livrables']}")
verifier("la fenetre de crue ne diverge pas entre plugin et livrables",
         _CRUE["plugin"] == _CRUE["livrables"],
         f"plugin={_CRUE['plugin']} | livrables={_CRUE['livrables']}")

# ET LES DEUX SIGNATURES DOIVENT LIRE CES CONSTANTES. Comparer les constantes
# ne suffit pas : ecrire « def _fenetre_crue(paires, seuil=0.05, ...) » en
# laissant SEUIL_CRUE = 0.02 juste au-dessus laisserait les deux controles
# ci-dessus au vert pendant que les deux fenetres divergent — exactement ce
# que ce garde-fou existe pour empecher.
_SIGN = {}
for _quel, _fichier in (("plugin", _FICHIER_CRUE),
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
# du plugin : il se designe, et le plugin compose et controle tres bien un
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
# LE SOMMAIRE TOMBE SUR SES ANCRES, ET DANS L'ORDRE. Les sections ont ete
# renumerotees en 0.7.19 — « Sur un autre poste » retiree, « Ecrire dans la
# geometrie » ajoutee — et un lien mort ne se voit PAS : Qt ne bouge pas, la
# page reste ou elle est, et le lecteur croit avoir mal clique.
_ancres_aide = re.findall(r'name="(s[0-9]+)"', mod_plugin.AIDE_HTML)
_liens_aide = re.findall(r'href="#(s[0-9]+)"', mod_plugin.AIDE_HTML)
# Le sommaire ouvre l'aide : ses liens sont les PREMIERS, et dans l'ordre des
# sections. Les renvois places dans le corps viennent apres, et il leur suffit
# de tomber sur une ancre existante.
verifier("chaque lien du sommaire de l'aide tombe sur son ancre, dans l'ordre",
         _liens_aide[:len(_ancres_aide)] == _ancres_aide
         and len(set(_ancres_aide)) == len(_ancres_aide),
         f"sommaire {_liens_aide[:len(_ancres_aide)]} / ancres {_ancres_aide}")
verifier("aucun renvoi de l'aide ne pointe dans le vide",
         set(_liens_aide) <= set(_ancres_aide),
         f"{sorted(set(_liens_aide) - set(_ancres_aide))} sans ancre")
verifier("l'aide a recueilli l'ecriture dans la geometrie",
         "Écrire dans la géométrie" in mod_plugin.AIDE_HTML
         and "Sur un autre poste" not in mod_plugin.AIDE_HTML)
# L'ABSENCE DE BOUCLE HYDRAULIQUE EST DITE COMME UNE HYPOTHESE, jamais
# comme un fait : la chaine ne la verifie nulle part, et c'est
# l'hydraulicien qui repond. Confirmee par l'utilisateur le 08/09/2026
# pour les modeles en cours.
verifier("l'aide pose l'absence de boucle comme une hypothese du modele",
         "hypothèse du" in mod_plugin.AIDE_HTML
         and "rien dans la chaîne ne la vérifie" in mod_plugin.AIDE_HTML)
# LE VERDICT PORTE SUR LA FENETRE, ET L'AIDE LE DIT. Decision du
# 08/09/2026 : la fenetre a ete introduite pour cela. Sans cette phrase, un
# lecteur qui compare au volume de la crue entiere croit a un defaut.
verifier("l'aide dit que le verdict porte sur la fenetre",
         "pas sur la crue" in mod_plugin.AIDE_HTML)

# L'ACTION A REJOINT L'ONGLET QUI LA PREPARE (0.7.19).
from qgis.PyQt.QtWidgets import QDialog as _QDialogA  # noqa: E402
from qgis.PyQt.QtWidgets import QGroupBox as _QGroupBoxA  # noqa: E402
from qgis.PyQt.QtWidgets import QPushButton as _QPushButtonA  # noqa: E402
_page_modele = dlg.onglets.widget(mod_plugin.ONGLET_MODELE)
_boutons_modele = [b.text() for b in _page_modele.findChildren(_QPushButtonA)]
_groupes_modele = [g.title() for g in _page_modele.findChildren(_QGroupBoxA)]
verifier("l'onglet 1 ne porte plus ni l'écriture ni la mise à jour",
         "Écriture dans la géométrie" not in _groupes_modele
         and "Mise à jour du modèle" not in _groupes_modele
         and "Écrire, composer et contrôler" not in _boutons_modele,
         f"{_groupes_modele} | {_boutons_modele}")

# L'ONGLET « SORTIES » A DISPARU (20/09/2026, demande utilisateur) : ses
# groupes ont rejoint « Lancer », ou se prennent les decisions du lancement.
verifier("l'ordre des onglets est celui des constantes",
         dlg.onglets.tabText(mod_plugin.ONGLET_OBJECTIFS).startswith("2.")
         and "Paramètres" in dlg.onglets.tabText(mod_plugin.ONGLET_OBJECTIFS)
         and dlg.onglets.tabText(mod_plugin.ONGLET_LANCER).startswith("3.")
         and "Lancer" in dlg.onglets.tabText(mod_plugin.ONGLET_LANCER),
         [dlg.onglets.tabText(i) for i in range(dlg.onglets.count())])
verifier("plus aucun onglet « Sorties »",
         not [i for i in range(dlg.onglets.count())
              if "Sorties" in dlg.onglets.tabText(i)],
         [dlg.onglets.tabText(i) for i in range(dlg.onglets.count())])

# L'ORDRE DEMANDE, GROUPE PAR GROUPE (20/09/2026, demande utilisateur) :
# les apports a determiner, puis les sorties, puis le prefixe, puis le
# lancement. C'est l'ORDRE qui est le correctif, pas la seule presence — un
# reglage lu apres le bouton qu'il regle ne sert a rien.
_ordre_lancer = [g.title() for g in dlg.onglets.widget(
    mod_plugin.ONGLET_LANCER).findChildren(_QGroupBoxA)]
# LE PREFIXE A QUITTE « Lancer » (21/09/2026) : il a rejoint le groupe du
# fichier qu'il nomme, a l'onglet Objectifs.
# LE DOSSIER DE SORTIE EST REMONTE A L'ETAPE PARAMETRES (22/09/2026, demande
# utilisateur), juste au-dessus du classeur qu'il abrite.
_attendu_lancer = ["Préparation du lancement", "Apports à déterminer",
                   "Conservation des plans d’étape",
                   "Calcul HEC-RAS", "Configuration complète",
                   "Lancer le calage"]
verifier("l'onglet Lancer enchaine apports, conservation, calcul, lancement",
         [g for g in _ordre_lancer if g in _attendu_lancer] == _attendu_lancer,
         str(_ordre_lancer))

# LES CŒURS (0.9.7, 22/09/2026, demande utilisateur) : le poste est lu, un
# nombre est propose, et RIEN n'est ecrit tant que la case n'est pas cochee.
_case_coeurs = getattr(dlg, "case_coeurs", None)
verifier("Lancer porte la case des cœurs, décochée, libellée par un verbe",
         _case_coeurs is not None and not _case_coeurs.isChecked()
         and _case_coeurs.text().startswith("Demander"),
         _case_coeurs.text() if _case_coeurs else "absente")
verifier("décochée, le lancement laisse le plan inchangé (0)",
         dlg._coeurs_demandes() == 0, str(dlg._coeurs_demandes()))
if _case_coeurs is not None:
    _case_coeurs.setChecked(True)
    verifier("cochée, il demande la suggestion du poste, entre 1 et 8",
             1 <= dlg._coeurs_demandes() <= 8
             and dlg._coeurs_demandes() == dlg.poste.suggestion,
             f"{dlg._coeurs_demandes()} ; {dlg.poste.detail}")
    verifier("le récapitulatif du lancement annonce les cœurs cochés",
             "Cœurs" in dlg.label_reprise.text()
             or not dlg.classeur,     # sans paquet, le recap dit d'en composer
             dlg.label_reprise.text()[:100])
    verifier("l'étiquette dit sur quoi la suggestion se fonde",
             "processeur" in dlg.label_coeurs.text()
             and "Suggestion pour ce poste" in dlg.label_coeurs.text(),
             dlg.label_coeurs.text()[:140])
    _case_coeurs.setChecked(False)

# LE SABLIER (avec_sablier) TRANSMET LES MOTS-CLES ET AVALE LE BOOLEEN D'UN
# CLIC (0.9.9). Avec « self » seul, le minuteur de recomposition — deux
# mots-cles — cassait ; avec « *args », le booleen de « clicked » passait a
# une methode qui le refusait, et une exception dans un slot PyQt tue le
# processus sans trace (banc mort deux fois, code 9). Eprouve sur un
# mannequin : aucun geste reel, aucune boite.
class _AuSablier:
    @mod_plugin.avec_sablier
    def sans_argument(self):
        return "ok"

    @mod_plugin.avec_sablier
    def avec_mots_cles(self, a=1, b=2):
        return (a, b)

_sab = _AuSablier()
try:
    _clic = _sab.sans_argument(False)          # ce que « clicked(bool) » envoie
    _mots = _sab.avec_mots_cles(a=5, b=6)      # ce que le minuteur envoie
    _sab_detail = f"clic -> {_clic!r}, mots-clés -> {_mots!r}"
except TypeError as e:
    _clic, _mots, _sab_detail = None, None, str(e)
verifier("le sablier avale le booléen d'un clic Qt", _clic == "ok", _sab_detail)
verifier("et transmet les mots-clés du minuteur", _mots == (5, 6), _sab_detail)
verifier("puis rend le curseur", not QgsApplication.overrideCursor(),
         str(QgsApplication.overrideCursor()))

# L'ATTENTE DU PAQUET NE RENVOIE PLUS A UN BOUTON « EN BAS DE LA FENETRE »
# (0.9.9, 22/09/2026, constate par l'utilisateur) : ce bouton vit a l'etape
# Modele depuis la 0.9.6 et n'a plus rien a voir avec la composition.
verifier("sans paquet, l'étape Lancer dit ce qui compose, et où, sans bouton fantôme",
         "en bas de la fen" not in dlg.label_prochaine_etape.text()
         and "Écrire dans la géométrie" not in dlg.label_prochaine_etape.text()
         and "Paramètres" in dlg.label_prochaine_etape.text(),
         dlg.label_prochaine_etape.text()[:120])

# LE DOSSIER DE SORTIE SE PROPOSE TOUT SEUL (0.9.8, 22/09/2026, demande
# utilisateur) : l'Excel doit exister des la saisie du prefixe, et le dossier,
# a l'etape Lancer, etait le prealable qui manquait. Une saisie manuelle n'est
# jamais remplacee.
_dossier_avant_prop = dlg.edit_dossier_sortie.text()
_prefixe_avant_prop = dlg.edit_prefixe_scenario.text()
_projet_avant_prop = dlg.edit_projet_hecras.text()
dlg.edit_projet_hecras.setText(str(ESSAI / "Modele" / "Modele.prj"))
dlg.edit_dossier_sortie.setText("")
dlg.edit_prefixe_scenario.setText("Q100")
verifier("le prefixe saisi propose « _calage\\Q100 » a cote du modele",
         dlg.edit_dossier_sortie.text()
         == str(ESSAI / "Modele" / "_calage" / "Q100"),
         dlg.edit_dossier_sortie.text())
dlg.edit_prefixe_scenario.setText("Q10_")
verifier("changer le prefixe suit, sans le souligne final, tant que le "
         "dossier n'a pas ete saisi a la main",
         dlg.edit_dossier_sortie.text()
         == str(ESSAI / "Modele" / "_calage" / "Q10"),
         dlg.edit_dossier_sortie.text())
dlg.edit_dossier_sortie.setText(str(ESSAI / "ailleurs"))
dlg.edit_prefixe_scenario.setText("Q1000")
verifier("un dossier saisi a la main n'est jamais remplace",
         dlg.edit_dossier_sortie.text() == str(ESSAI / "ailleurs"),
         dlg.edit_dossier_sortie.text())

# LE COURS D'EAU EN TETE DU PREFIXE (23/10/2026, demande utilisateur :
# « propose plutot "Cours-d'eau - Q100 - ..." sinon il y aura des doublons
# quand plusieurs cours d'eau »). Meme regle que calage.titre_etape.
dlg.edit_dossier_sortie.setText("")
dlg.edit_prefixe_scenario.setText("Riviere - Q100 - ")
verifier("un seul separateur « - », tiret final ou non",
         dlg._titre_etape("Apport_A1") == "Riviere - Q100-A1"
         and dlg.edit_prefixe_scenario.setText("Riviere - Q100") is None
         and dlg._titre_etape("sans_apport") == "Riviere - Q100-sans"
         and dlg._titre_etape("sans A3 et aval") == "Riviere - Q100-sans A3"
         and dlg._titre_etape("avec_apports") == "Riviere - Q100",
         dlg._titre_etape("Apport_A1"))
verifier("le dossier propose a un nom Windows (ni « - » ni espace final)",
         dlg.edit_dossier_sortie.text()
         == str(ESSAI / "Modele" / "_calage" / "Riviere - Q100"),
         dlg.edit_dossier_sortie.text())
dlg.edit_prefixe_scenario.setText("Q100/bis")
verifier("un caractere interdit dans un nom de dossier devient « _ »",
         dlg.edit_dossier_sortie.text().endswith("Q100_bis"),
         dlg.edit_dossier_sortie.text())
dlg.edit_prefixe_scenario.setText("Q100")
verifier("un prefixe sans tiret espace prend aussi « - »",
         dlg._titre_etape("Apport_A1") == "Q100-A1", dlg._titre_etape("Apport_A1"))
dlg.edit_prefixe_scenario.setText("")
_ligne = dlg.label_titres_prefixe.text()
verifier("prefixe vide : la ligne dit de commencer par le cours d'eau",
         "cours d’eau" in _ligne and "Q100" in _ligne, _ligne[:90])
dlg.edit_prefixe_scenario.setText("Riviere-Q100")
_ligne = dlg.label_titres_prefixe.text()
verifier("la ligne montre les titres, l'Excel et le compte des caracteres",
         "Riviere-Q100-sans" in _ligne
         and "donnees_calage_Riviere-Q100.xlsx" in _ligne
         and "sur 32" in _ligne and "Trop long" not in _ligne,
         re.sub("<[^>]+>", " ", _ligne)[:140])
dlg.edit_prefixe_scenario.setText("Riviere des Grandes Eaux - Q1000")
_ligne = dlg.label_titres_prefixe.text()
verifier("un prefixe trop long est dit a la frappe, avec le compte a retirer",
         "Trop long" in _ligne and "Raccourcissez le préfixe de" in _ligne,
         re.sub("<[^>]+>", " ", _ligne)[:140])
dlg.edit_prefixe_scenario.setText("Rivière - Q100")
verifier("un accent est signale : HEC-RAS le rabote dans les resultats",
         "Accents" in dlg.label_titres_prefixe.text(),
         re.sub("<[^>]+>", " ", dlg.label_titres_prefixe.text())[-90:])
dlg.edit_prefixe_scenario.setText("<b>Q100")
verifier("le prefixe est echappe dans la ligne (texte riche)",
         "&lt;b&gt;Q100" in dlg.label_titres_prefixe.text(),
         dlg.label_titres_prefixe.text()[:80])
verifier("« Sens du tracé » montre des mots, garde le code en donnee",
         [dlg.combo_sens_axe.itemText(i) for i in range(2)]
         == ["De l'amont vers l'aval", "De l'aval vers l'amont"]
         and [dlg.combo_sens_axe.itemData(i) for i in range(2)]
         == ["amont_aval", "aval_amont"],
         str([dlg.combo_sens_axe.itemText(i) for i in range(2)]))
verifier("les nombres affiches prennent la virgule",
         mod_plugin.nombre(99.84) == "99,8"
         and mod_plugin.nombre(-1.25, 2, signe=True) == "-1,25"
         and mod_plugin.nombre(1234.5, 1, milliers=True) == "1 234,5"
         and mod_plugin.date_lisible("2026-10-24T03:15") == "24/10/2026 à 03 h 15",
         mod_plugin.nombre(1234.5, 1, milliers=True))

# UN LIEN DU FIL MENE AU CHAMP, PAS SEULEMENT A L'ETAPE (23/10/2026) :
# « Choisir le dossier de sortie » ouvrait l'etape Lancer, ou il n'est plus.
_rang_avant_lien = dlg.onglets.currentIndex()
dlg._aller_etape("1:edit_dossier_sortie")
verifier("le lien « 1:edit_dossier_sortie » ouvre l'etape 2 et y donne le focus au champ",
         dlg.onglets.currentIndex() == 1
         and dlg.focusWidget() is dlg.edit_dossier_sortie,
         f"etape {dlg.onglets.currentIndex()}, focus "
         f"{type(dlg.focusWidget()).__name__ if dlg.focusWidget() else None}")
dlg._aller_etape("9:inconnu")
dlg._aller_etape("2:attribut_absent")
verifier("un lien inconnu ne casse rien ; une cible absente ouvre l'etape seule",
         dlg.onglets.currentIndex() == 2, str(dlg.onglets.currentIndex()))
dlg.onglets.setCurrentIndex(_rang_avant_lien)
dlg.edit_projet_hecras.setText(_projet_avant_prop)
dlg.edit_prefixe_scenario.setText(_prefixe_avant_prop)
dlg.edit_dossier_sortie.setText(_dossier_avant_prop)

# LE PROJET CHARGE EST CELUI QU'ON DESIGNE (audit du 11/10/2026). Le
# selecteur rend le .prj, mais on chargeait son DOSSIER, et le noyau y
# prenait le premier .prj de projet : dans un dossier a deux projets, un
# autre que celui choisi — « Aval_ancien » vient ici en tete — et la version
# de HEC-RAS lue dans les fichiers des deux.
_bac_prj = Path(tempfile.mkdtemp(prefix="deux_projets_"))
for _nom, _version in (("Aval_ancien", "7.01"), ("Projet_choisi", "6.60")):
    (_bac_prj / f"{_nom}.prj").write_text(
        f"Proj Title={_nom}\nPlan File=p01\n", encoding="utf-8")
    (_bac_prj / f"{_nom}.p01").write_text(
        f"Plan Title=Q100\nProgram Version={_version}\n", encoding="utf-8")
_dlg_prj = mod_plugin.DialogueParametrage(iface)
# LA VERSION QUI CALCULERA EST DITE A PART (10/11/2026) : une ligne sous le
# projet et une ligne du resume, absentes tant qu'aucun modele n'est charge.
_dlg_prj._maj_resume()
verifier("sans modele, ni la ligne de version ni celle du resume ne parlent",
         _dlg_prj.label_version_calage.isHidden()
         and _dlg_prj.label_version_calage.text() == ""
         and "HEC-RAS :" not in _dlg_prj.texte_resume.toPlainText(),
         _dlg_prj.texte_resume.toPlainText()[:80])
fichiers.fichiers.append(str(_bac_prj / "Projet_choisi.prj"))
_dlg_prj._parcourir_projet_hecras()
verifier("le projet charge est le .prj designe, pas le premier du dossier",
         (_dlg_prj.info_projet or {}).get("nom_projet") == "Projet_choisi"
         and _dlg_prj.version_hecras == "6.6",
         f"{(_dlg_prj.info_projet or {}).get('nom_projet')}, "
         f"HEC-RAS {_dlg_prj.version_hecras}")
verifier("la version lue est dite sous le projet",
         _dlg_prj.label_version_calage.text()
         == _dlg_prj._phrase_version("6.6", noyau.versions_hecras_installees())
         and not _dlg_prj.label_version_calage.isHidden(),
         _dlg_prj.label_version_calage.text())
# LA PHRASE NE PROMET PAS UN CALAGE QUE LE POSTE NE PEUT PAS FAIRE.
verifier("version installee : « Le calage sera réalisé avec HEC-RAS 7.0.2. »",
         _dlg_prj._phrase_version("7.0.2", ["7.0.1", "7.0.2"])
         == "Le calage sera réalisé avec HEC-RAS 7.0.2."
         and _dlg_prj._phrase_version("7.0.2", [])
         == "Le calage sera réalisé avec HEC-RAS 7.0.2.")
verifier("version absente du poste : la phrase dit que le calage ne calculera pas",
         "pas installé" in _dlg_prj._phrase_version("6.6", ["7.0.1"])
         and "sera réalisé" not in _dlg_prj._phrase_version("6.6", ["7.0.1"])
         and _dlg_prj._phrase_version(None, ["7.0.1"]) == "",
         _dlg_prj._phrase_version("6.6", ["7.0.1"]))
verifier("et le resume la porte sur sa ligne « HEC-RAS : 6.6 »",
         "HEC-RAS : 6.6" in _dlg_prj.texte_resume.toPlainText().splitlines(),
         _dlg_prj.texte_resume.toPlainText()[:120])
shutil.rmtree(_bac_prj, ignore_errors=True)
# ET LE PREFIXE A QUITTE « Objectifs ». Laisse aux deux endroits, il aurait
# donne deux champs a lire pour un seul reglage.
# L'ORDRE DE L'ONGLET OBJECTIFS (20/09/2026, demande utilisateur) : ce qu'on
# vise, puis le geste qui ouvre la saisie, puis la saisie. Le classeur venait
# en premier alors qu'il n'existe pas encore — la page s'ouvrait sur un groupe
# grise.
_ordre_objectifs = [g.title() for g in dlg.onglets.widget(
    mod_plugin.ONGLET_OBJECTIFS).findChildren(_QGroupBoxA)]
_attendu_objectifs = ["Précision du calage", "Dossier de sortie",
                      "Hydrogrammes cibles",
                      "Ce que portent les hydrogrammes cibles"]
verifier("l'onglet Paramètres enchaine precision, dossier, cibles, ce qu'elles portent",
         [g for g in _ordre_objectifs
          if g in _attendu_objectifs] == _attendu_objectifs,
         str(_ordre_objectifs))
# LA LIGNE QUI DEMANDE DE COMPOSER EST HORS DU GROUPE QU'ELLE DEBLOQUE :
# dedans, elle expliquait depuis l'interieur d'un groupe grise comment le
# degriser.
verifier("le geste a poser est dit hors du groupe qu'il debloque",
         dlg.label_classeur_attente.parent()
         is not dlg.findChild(_QGroupBoxA, "")
         and "préfixe de scénario" in dlg.label_classeur_attente.text()
         and not [g for g in dlg.onglets.widget(
             mod_plugin.ONGLET_OBJECTIFS).findChildren(_QGroupBoxA)
             if dlg.label_classeur_attente in g.findChildren(type(
                 dlg.label_classeur_attente))],
         dlg.label_classeur_attente.text()[:70])
# LE PREFIXE EST DANS LE GROUPE DU FICHIER QU'IL NOMME (21/09/2026, demande
# utilisateur), et la consigne y renvoie « ci-dessous ».
verifier("la consigne renvoie au prefixe, juste dessous",
         "ci-dessous" in dlg.label_classeur_attente.text()
         and "préfixe de scénario" in dlg.label_classeur_attente.text(),
         dlg.label_classeur_attente.text()[:90])
_groupe_cibles = next(g for g in dlg.onglets.widget(
    mod_plugin.ONGLET_OBJECTIFS).findChildren(_QGroupBoxA)
    if g.title() == "Hydrogrammes cibles")
verifier("le prefixe vit DANS le groupe « Hydrogrammes cibles »",
         dlg.edit_prefixe_scenario in _groupe_cibles.findChildren(
             type(dlg.edit_prefixe_scenario)),
         _groupe_cibles.title())
# LE PIEGE QUE LA 0.8.4 CRAIGNAIT : un champ obligatoire dans un bloc grise
# serait une impasse. _maj_groupe_classeur ne desactive QUE trois enfants,
# jamais le groupe — on le verifie, plutot que de s'y fier.
dlg._maj_groupe_classeur()
verifier("et il reste saisissable tant que rien n'est compose",
         dlg.edit_prefixe_scenario.isEnabled() and _groupe_cibles.isEnabled(),
         f"champ={dlg.edit_prefixe_scenario.isEnabled()} "
         f"groupe={_groupe_cibles.isEnabled()}")

# L'EMPRISE 2D : CONTOUR ROUGE, AUCUN REMPLISSAGE (21/09/2026, demande
# utilisateur). Elle arrivait avec l'aplat aleatoire de QGIS et masquait le
# maillage et les sections qu'on vient regarder dessous.
_emprise = QgsVectorLayer("Polygon?crs=EPSG:2154", "Emprise 2D (HEC-RAS)",
                            "memory")
_ok_emprise, _msg_emprise = mod_plugin.styler_emprise(_emprise)
verifier("l'emprise 2D se style sans erreur", _ok_emprise, _msg_emprise)
_symbole = _emprise.renderer().symbol()
# Comparaison a l'enumeration, pas a int() : sous PyQt6 (QGIS 4), une
# enumeration Qt n'est plus un entier (constat CI du 28/10/2026).
verifier("l'emprise 2D n'a aucun remplissage",
         _symbole.symbolLayer(0).brushStyle() == Qt.BrushStyle.NoBrush,
         str(_symbole.symbolLayer(0).brushStyle()))
_contour = _symbole.symbolLayer(0).strokeColor()
verifier("son contour est rouge et opaque",
         _contour.red() > 200 and _contour.green() < 80
         and _contour.blue() < 80 and _contour.alpha() == 255,
         f"rgba({_contour.red()},{_contour.green()},{_contour.blue()},"
         f"{_contour.alpha()})")

# PLUS DE COUCHE DE PK : LE PK S'ETIQUETTE SUR LES COUCHES DE BASE
# (24/09/2026, demande utilisateur). « Sections — PK » et « Injections — PK »
# doublaient les couches de base et se lisaient comme des doublons.
import geopandas as _gpd                                      # noqa: E402
from qgis.core import (QgsExpression as _QgsExpression,       # noqa: E402
                       QgsExpressionContext as _QgsExpressionContext,
                       QgsExpressionContextUtils as _QgsExpressionContextUtils)
_bac_pk = Path(tempfile.mkdtemp(prefix="couches_pk_"))
_chemins_pk = {cle: str(_bac_pk / f"{cle}.shp")
               for cle in ("axe", "sections", "apports")}


def _en_travers(x):
    """Une ligne qui coupe l'axe du banc a l'abscisse x."""
    return LineString([(500000 + x, 6199500), (500000 + x, 6200800)])


def _etiquettes(couche):
    """Le texte que l'etiquette de chaque entite affiche, par nom."""
    expression = _QgsExpression(couche.labeling().settings().fieldName)
    contexte = _QgsExpressionContext(
        _QgsExpressionContextUtils.globalProjectLayerScopes(couche))
    rendu = {}
    for entite in couche.getFeatures():
        contexte.setFeature(entite)
        rendu[entite["nom"]] = expression.evaluate(contexte)
    return rendu


for _cle, _noms, _xs in (("axe", ["Axe"], None),
                         ("sections", ["S1", "S2"], (2000, 6000)),
                         ("apports", ["A1", "A2"], (1500, 5500))):
    _gpd.GeoDataFrame(
        {"nom": _noms},
        geometry=[axe_geom] if _xs is None else [_en_travers(x) for x in _xs],
        crs="EPSG:2154").to_file(_chemins_pk[_cle])
# « S9 » est tracee apres la composition : elle n'a pas encore de PK.
_base_s = couche("Sections de contrôle (HEC-RAS)",
                 [_en_travers(2000), _en_travers(7000)], ["S1", "S9"])
_base_a = couche("Lignes d'injection (HEC-RAS)", [_en_travers(1500)], ["A1"])
mod_plugin.appliquer_style(_base_s, "sections")
mod_plugin.appliquer_style(_base_a, "injections")
# LE NOM DES LE CHARGEMENT, sur fond blanc arrondi a trait gris (27/10/2026).
_echecs_etiquettes = mod_plugin.appliquer_styles(_base_a, _base_s, None)


def _fond(c):
    if c.labeling() is None:
        return None
    # CHAQUE OBJET TENU PAR UN NOM : settings() rend une copie, et format()
    # une reference DANS cette copie. Enchaines, la copie meurt avant la
    # lecture, et QGIS plante par violation d'acces (une fois sur deux).
    reglages = c.labeling().settings()
    texte = reglages.format()
    f = texte.background()
    return (f.enabled(), f.fillColor().name(), f.strokeColor().name(),
            f.radii().width())


verifier("le nom est affiche des le chargement, sur fond blanc arrondi",
         _fond(_base_s) == (True, "#ffffff", "#808080", 3.0)
         and _base_s.labelsEnabled() and _etiquettes(_base_s)["S1"] == "S1"
         and _base_a.labelsEnabled() and _etiquettes(_base_a)["A1"] == "A1",
         f"{_fond(_base_s)} {_echecs_etiquettes}")
_homonyme = couche("Sections — PK", [_en_travers(100)], ["X"])
# UNE COUCHE DE PK LAISSEE PAR LA 0.9.15 dans le projet : elle doit partir.
_reliquat = couche("Injections — PK", [_en_travers(1500)], ["A1"])
_reliquat.setCustomProperty(mod_plugin.MARQUE_PK, "apports")
# L'IDENTIFIANT AVANT L'APPEL : retiree du projet, la couche est detruite, et
# l'objet Python qui la portait ne repond plus.
_id_reliquat = _reliquat.id()
_nb_avant = len(QgsProject.instance().mapLayers())
_bases_pk = {"sections": _base_s, "apports": _base_a}
mod_plugin.etiqueter_pk_sur_carte(_chemins_pk, "amont_aval", _bases_pk)
mod_plugin.etiqueter_pk_sur_carte(_chemins_pk, "amont_aval", _bases_pk)
verifier("aucune couche de PK n'est creee, et celle de la 0.9.15 est retiree",
         len(QgsProject.instance().mapLayers()) == _nb_avant - 1
         and QgsProject.instance().mapLayer(_id_reliquat) is None,
         f"{_nb_avant} -> {len(QgsProject.instance().mapLayers())} couches")
verifier("une couche de l'utilisateur au meme nom n'est pas retiree",
         QgsProject.instance().mapLayer(_homonyme.id()) is not None,
         _homonyme.name())
_rendu_s = _etiquettes(_base_s)
verifier("la couche de base des sections etiquette « nom — PK n m »",
         _base_s.labelsEnabled()
         and str(_rendu_s["S1"]).startswith("S1 — PK ")
         and str(_rendu_s["S1"]).endswith(" m"),
         str(_rendu_s))
verifier("un objet trace apres la composition n'affiche que son nom",
         _rendu_s["S9"] == "S9", str(_rendu_s["S9"]))
_rendu_a = _etiquettes(_base_a)
verifier("et celle des injections aussi",
         _base_a.labelsEnabled() and str(_rendu_a["A1"]).startswith("A1 — PK "),
         str(_rendu_a))
verifier("le PK garde le fond des etiquettes du chargement",
         _fond(_base_a) == (True, "#ffffff", "#808080", 3.0),
         str(_fond(_base_a)))
verifier("le symbole de la couche de base ne bouge pas",
         _base_s.renderer().symbol().color().name() == "#e31a1c",
         _base_s.renderer().symbol().color().name())
for _c in (_base_s, _base_a, _homonyme):
    QgsProject.instance().removeMapLayer(_c.id())
shutil.rmtree(_bac_pk, ignore_errors=True)

# L'ANCIEN CLASSEUR EST MIS DE COTE, JAMAIS ECRASE (20/09/2026, demande
# utilisateur). Deux prefixes donnaient deja deux fichiers depuis la 0.8.4 ;
# avec le MEME prefixe, recomposer reecrivait le fichier en place. Les cibles
# y survivaient — elles sont relues et reportees — mais pas ce que
# l'utilisateur avait pu y ajouter.
import openpyxl as _openpyxl                                 # noqa: E402
import pandas as _pd                                         # noqa: E402
_bac_cl = Path(tempfile.mkdtemp(prefix="classeur_sauve_"))
_paires_cl = [("A1", "S1"), ("A2", "S2")]
_par_cl = {"Prefixe_scenario": "Q100", "Nom_projet": "Essai"}
_cl1 = noyau.preparer_classeur(_bac_cl, _paires_cl, {}, parametres=_par_cl)
# REMPLACER LE PLAN DE REFERENCE EST UN ACCORD DU LANCEMENT (10/11/2026) : la
# composition ecrit « non », seule la question posee au depart ecrit « oui ».
verifier("un paquet compose n'autorise pas a remplacer le plan de reference",
         noyau.lire_parametres(_cl1).get("Remplacer_plan_source") == "non",
         repr(noyau.lire_parametres(_cl1).get("Remplacer_plan_source")))
_wb = _openpyxl.load_workbook(_cl1)
_wb["Cibles"]["A2"], _wb["Cibles"]["B2"] = 0.0, 12.5
_wb.create_sheet("Mes notes")["A1"] = "a garder"
_wb.save(_cl1)
_cl2 = noyau.preparer_classeur(_bac_cl, _paires_cl, {}, parametres=_par_cl)
_sauves = sorted(_bac_cl.glob("donnees_calage_Q100.precedent.xlsx"))
verifier("recomposer ne change pas le nom canonique du classeur",
         Path(_cl2) == Path(_cl1), Path(_cl2).name)
# UN SEUL NIVEAU : la composition est automatique depuis le 21/09/2026, et
# une copie datee par recomposition enterrerait le dossier de sortie.
verifier("l'ancien classeur est mis de cote, un seul niveau",
         len(_sauves) == 1, _sauves[0].name if _sauves else "AUCUNE")
verifier("la sauvegarde garde ce que la recomposition ne sait pas reporter",
         bool(_sauves) and "Mes notes" in _openpyxl.load_workbook(
             _sauves[0]).sheetnames)
verifier("et les cibles saisies restent dans le classeur neuf",
         12.5 in list(_pd.read_excel(_cl2, sheet_name="Cibles").iloc[:, 1]),
         str(list(_pd.read_excel(_cl2, sheet_name="Cibles").iloc[:, 1])[:3]))
# ET RECOMPOSER UNE TROISIEME FOIS N'EMPILE PAS : « precedent » est
# remplace, il n'y a jamais qu'une copie par scenario.
noyau.preparer_classeur(_bac_cl, _paires_cl, {}, parametres=_par_cl)
verifier("une troisieme composition n'empile pas les copies",
         len(list(_bac_cl.glob("donnees_calage_Q100.precedent*"))) == 1,
         str(sorted(p.name for p in _bac_cl.glob("donnees_calage_Q100*"))))
_cl3 = noyau.preparer_classeur(_bac_cl, _paires_cl, {},
                               parametres={"Prefixe_scenario": "Q10"})
verifier("un prefixe neuf donne un fichier neuf, sans sauvegarde inutile",
         Path(_cl3).name == "donnees_calage_Q10.xlsx"
         and not list(_bac_cl.glob("donnees_calage_Q10.precedent*")),
         Path(_cl3).name)
shutil.rmtree(_bac_cl, ignore_errors=True)

# LE CONTROLE DE COHERENCE (20/09/2026, demande utilisateur). Le paquet est
# un instantane : changer le prefixe, un dossier ou une precision APRES la
# composition laissait l'ecran et le paquet dire deux choses, en silence.
_coh = mod_plugin.DialogueParametrage(iface)
# LE CLASSEUR PORTE LE NOM QUE LA CHAINE LUI DONNERAIT — « donnees_calage_
# <prefixe>.xlsx » —, sans quoi l'annonce de classeur neuf se declencherait
# a juste titre : composer ne reecrit pas un fichier hors convention, il en
# cree un au nom canonique. Le dossier est a lui : deux essais voisins se
# marcheraient dessus.
_coh_bac = Path(tempfile.mkdtemp(prefix="coherence_"))
_coh_cl = _coh_bac / "donnees_calage_Q100.xlsx"
_pd.DataFrame({"Ordre": [1], "Nom_Apport (BC line)": ["A1"],
               "Nom_Section (reference line)": ["S1"]}
              ).to_excel(_coh_cl, sheet_name="Correspondance", index=False)
import parametres as _param_mod
# LE PAQUET PORTE AUSSI UN MODELE ET UN AXE QUE L'ECRAN N'A PAS : c'est la
# reprise d'un Excel sans son modele, que le refus de lancer ne doit pas
# bloquer (voir plus bas).
_param_mod.ecrire(_coh_cl, {
    "Prefixe_scenario": "Q100",
    "Dossier_sortie": str(_coh_bac),
    "Sous_dossier_resultats": "resultats_finaux",
    "Sous_dossier_suivi": "suivi",
    "Tolerance_volume_pct": 5.0, "Tolerance_pic_pct": 2.0,
    "Bilan_masse_max_pct": 5.0, "Nb_max_iterations_par_apport": 6,
    "Dossier_projet_HECRAS": "D:/modele_absent", "Nom_projet": "Riviere",
    "Plan_reference": "p03", "Sens_axe": "aval_amont", "PK_origine_m": 0.0})
_coh.classeur = str(_coh_cl)
_coh.edit_prefixe_scenario.setText("Q100")
_coh.edit_dossier_sortie.setText(str(_coh_bac))
_coh._maj_resume()
verifier("un paquet conforme a l'ecran ne signale aucun ecart",
         not _coh._ecarts_avec_le_paquet(),
         str(_coh._ecarts_avec_le_paquet()))


def _temoin_de(fenetre, cle):
    """Le « ! » du champ qui porte cette cle du paquet."""
    return next(t for cles, t in fenetre._temoins if cle in cles)


def _marque_onglet(fenetre, rang):
    """L'entree de la bande de cette etape si elle porte le « ! », ou None."""
    element = fenetre.bande.item(rang)
    return element if "!" in element.text() else None


# UN CLASSEUR REPRIS SANS SON MODELE N'ALLUME RIEN (24/09/2026). Le paquet
# nomme un modele, un plan et un sens que l'ecran n'a pas : ces champs muets
# n'ont pas bouge depuis l'arrivee du paquet, ce ne sont pas des ecarts. Sans
# cette regle, le refus de lancer aurait rendu impossible un calage repris.
verifier("un classeur repris sans son modele n'allume aucun « ! »",
         not [c for c, t in _coh._temoins if not t.isHidden()]
         and _marque_onglet(_coh, mod_plugin.ONGLET_MODELE) is None,
         str([c for c, t in _coh._temoins if not t.isHidden()]))
# LES NOMBRES SE COMPARENT EN NOMBRES : 5.0 au classeur, 5 au spin.
verifier("5,0 du classeur et 5 du spin ne sont pas un ecart",
         _coh._memes_valeurs(5, 5.0) and _coh._memes_valeurs("5", 5.0))
# ET LES CHEMINS SE COMPARENT SANS ANTISLASH FINAL NI CASSE.
verifier("deux ecritures du meme chemin ne sont pas un ecart",
         _coh._memes_valeurs("D:\\sortie\\", "D:/Sortie"))
_coh.edit_prefixe_scenario.setText("Q10")
_coh._maj_resume()
_ecarts = _coh._ecarts_avec_le_paquet()
verifier("changer le prefixe apres composition est signale",
         any("préfixe" in e for e in _ecarts.values()), str(_ecarts))
# LE PAQUET NE SE RECOMPOSE PLUS TOUT SEUL (24/09/2026) : le texte renvoie
# au bouton, et dit que le lancement attend.
verifier("et l'ecran le dit, en nommant les deux valeurs et le bouton",
         "Q10" in _coh.label_prochaine_etape.text()
         and "Q100" in _coh.label_prochaine_etape.text()
         and mod_plugin.BOUTON_GEOMETRIE in _coh.label_prochaine_etape.text()
         and "refusé" in _coh.label_prochaine_etape.text(),
         _coh.label_prochaine_etape.text()[:160])
# LE « ! » ROUGE SUR LE CHAMP PERIME, ET SUR LE TITRE DE SON ETAPE.
_t_prefixe = _temoin_de(_coh, "Prefixe_scenario")
verifier("un « ! » s'allume sur le prefixe perime, lui seul",
         not _t_prefixe.isHidden()
         and [c for c, t in _coh._temoins if not t.isHidden()]
         == [("Prefixe_scenario",)],
         str([c for c, t in _coh._temoins if not t.isHidden()]))
verifier("son infobulle dit les deux valeurs et le bouton qui actualise",
         "Q10" in _t_prefixe.toolTip() and "Q100" in _t_prefixe.toolTip()
         and mod_plugin.BOUTON_GEOMETRIE in _t_prefixe.toolTip()
         and _t_prefixe.accessibleDescription() == _t_prefixe.toolTip()
         and _t_prefixe.accessibleName() == "Réglage à actualiser",
         _t_prefixe.toolTip()[:120])
from calage_apports import interface as _mod_interface_t     # noqa: E402
verifier("il est rouge ISL, et suit le theme sombre comme les autres textes",
         isinstance(_t_prefixe, _mod_interface_t.Etiquette)
         and mod_plugin.ISL_ROUGE in _t_prefixe._texte_original,
         _t_prefixe._texte_original)
verifier("l'etape Parametres porte un « ! » sur son titre, pas les autres",
         _marque_onglet(_coh, mod_plugin.ONGLET_OBJECTIFS) is not None
         and _marque_onglet(_coh, mod_plugin.ONGLET_MODELE) is None
         and _marque_onglet(_coh, mod_plugin.ONGLET_LANCER) is None,
         str([_marque_onglet(_coh, i) is not None
              for i in range(_coh.onglets.count())]))
verifier("et le titre garde son texte",
         _coh.onglets.tabText(mod_plugin.ONGLET_OBJECTIFS) == "2. Paramètres",
         _coh.onglets.tabText(mod_plugin.ONGLET_OBJECTIFS))
# LE « ! » EST SUR L'ENTREE DE LA BANDE (23/10/2026) : le numero le porte,
# l'entree passe au rouge de la charte, l'infobulle nomme le reglage.
_entree_perimee = _coh.bande.item(mod_plugin.ONGLET_OBJECTIFS)
verifier("l'entree de la bande porte « 2 ! », en rouge, et nomme le reglage",
         _entree_perimee.text().startswith("2 !")
         and _entree_perimee.foreground().color().name().lower()
         == mod_plugin.couleur_theme(mod_plugin.ISL_ROUGE, _coh.bande).name().lower()
         and "À actualiser dans cette étape" in _entree_perimee.toolTip()
         and "À actualiser" in _entree_perimee.data(mod_plugin.Qt.ItemDataRole.AccessibleTextRole),
         f"{_entree_perimee.text()!r} {_entree_perimee.foreground().color().name()} "
         f"{_entree_perimee.toolTip()[-60:]!r}")
# ET IL SURVIT AU CHANGEMENT DE FORME DE LA BANDE : resserree aux numeros
# quand la hauteur manque, elle relit ses textes.
_coh.bande.ajuster(0)
_court = _entree_perimee.text()
_coh.bande.ajuster(_coh.bande.hauteur_complete)
verifier("le « ! » reste quand la bande ne montre que les numeros",
         _court == "2 !" and _entree_perimee.text().startswith("2 !"),
         f"{_court!r} puis {_entree_perimee.text()!r}")
verifier("un paquet perime ne compte pas comme compose",
         dict(_coh._etapes_preparation())["Paquet composé"] is False,
         str(_coh._etapes_preparation()))
# LE LANCEMENT EST REFUSE TANT QU'UN « ! » EST ALLUME, et le dit.
_messages = []
_coh._signaler = lambda titre, texte, *a, **k: _messages.append((titre, texte))
_coh._lancer_calage()
verifier("lancer avec un « ! » allume est refuse, en nommant le reglage",
         bool(_messages) and _messages[-1][0] == "Calage non lancé"
         and "préfixe de scénario" in _messages[-1][1]
         and mod_plugin.BOUTON_GEOMETRIE in _messages[-1][1],
         str(_messages[-1] if _messages else "aucun message"))
_coh.edit_prefixe_scenario.setText("Q100")
_coh._maj_resume()
verifier("revenir a la valeur du paquet eteint le « ! » et celui de l'onglet",
         _t_prefixe.isHidden()
         and _marque_onglet(_coh, mod_plugin.ONGLET_OBJECTIFS) is None,
         f"champ caché={_t_prefixe.isHidden()}")
_coh.spin_tol_volume.setValue(3.0)
_coh._maj_resume()
verifier("changer la precision apres composition est signale aussi",
         any("volume" in e for e in _coh._ecarts_avec_le_paquet().values())
         and not _temoin_de(_coh, "Tolerance_volume_pct").isHidden(),
         str(_coh._ecarts_avec_le_paquet()))
_coh.spin_tol_volume.setValue(5.0)
# UN CHAMP DE L'ETAPE MODELE, TOUCHE APRES LA REPRISE, S'ANNONCE : le PK
# d'origine part au paquet a la composition, et n'etait compare a rien.
_coh.spin_pk_origine.setValue(250.0)
verifier("changer le PK d'origine allume son « ! » et celui de l'etape Modele",
         not _temoin_de(_coh, "PK_origine_m").isHidden()
         and _marque_onglet(_coh, mod_plugin.ONGLET_MODELE) is not None,
         str(_coh._ecarts_avec_le_paquet()))
_coh.spin_pk_origine.setValue(0.0)
# ET UN CHAMP REMIS A LA VALEUR DU PAQUET N'EST PAS UN ECART, meme s'il a
# bouge depuis la reprise : c'est le paquet qui fait foi.
_coh.combo_sens_axe.setCurrentIndex(_coh.combo_sens_axe.findData("aval_amont"))
verifier("un sens remis a celui du paquet n'est pas un ecart",
         "Sens_axe" not in _coh._ecarts_avec_le_paquet()
         and _marque_onglet(_coh, mod_plugin.ONGLET_MODELE) is None,
         str(_coh._ecarts_avec_le_paquet()))
# ET UN REGLAGE HORS DEFAUT N'EST PAS UN ECART (10/11/2026). « aval_amont »
# n'est pas le sens par defaut : sa marque « ! défaut : … » est allumee, mais
# l'ecran dit ce que dit le paquet. Aucun temoin, aucun « ! » sur la bande :
# le lancement, qui ne refuse que les ecarts, n'est pas bloque.
_coh._maj_resume()
_m_sens = next(m for c, _w, m in _coh._defauts if c == "Sens_axe")
verifier("un reglage hors defaut, conforme au paquet, ne bloque pas le lancement",
         not _m_sens.isHidden()
         and not _coh._ecarts_avec_le_paquet()
         and not [c for c, t in _coh._temoins if not t.isHidden()]
         and _marque_onglet(_coh, mod_plugin.ONGLET_MODELE) is None,
         f"marque cachee={_m_sens.isHidden()}, ecarts={_coh._ecarts_avec_le_paquet()}")
# CHANGER LE PREFIXE FERA UN CLASSEUR NEUF, DONC VIDE (21/09/2026, signale
# comme « supprime les apports »). Mesure : rien n'est supprime, l'ancien
# garde ses cibles — mais le neuf nait vide et la fenetre bascule dessus.
# On l'annonce AVANT le clic, et on nomme le fichier ou le travail se
# trouve encore. On ne recopie pas les cibles : un scenario n'a pas les
# hydrogrammes d'un autre.
_openpyxl_c = _openpyxl.load_workbook(_coh_cl)
_openpyxl_c["Cibles"] if "Cibles" in _openpyxl_c.sheetnames else     _openpyxl_c.create_sheet("Cibles")
_f_cib = _openpyxl_c["Cibles"]
_f_cib["A1"], _f_cib["B1"] = "Temps_h", "Cible_S1"
_f_cib["A2"], _f_cib["B2"] = 0.0, 12.5
_openpyxl_c.save(_coh_cl)
_coh.edit_prefixe_scenario.setText("Q100")
verifier("sans changement de prefixe, aucune annonce de classeur neuf",
         not _coh._classeur_neuf_annonce(), _coh._classeur_neuf_annonce())
_coh.edit_prefixe_scenario.setText("Q10")
_annonce = _coh._classeur_neuf_annonce()
verifier("un prefixe neuf annonce un classeur vide, avant le clic",
         "cibles vides" in _annonce
         and "donnees_calage_Q10.xlsx" in _annonce
         and "donnees_calage_Q100.xlsx" in _annonce,
         _annonce[:110])
verifier("et il dit que rien n'est supprime",
         "rien n’est supprimé" in _annonce, _annonce[-90:])
_coh.edit_prefixe_scenario.setText("Q100")

_coh.edit_dossier_sortie.setText(str(Path(tempfile.gettempdir()) / "ailleurs"))
_coh._maj_resume()
verifier("changer le dossier de sortie apres composition est signale aussi",
         any("dossier de sortie" in e
             for e in _coh._ecarts_avec_le_paquet().values()),
         str(_coh._ecarts_avec_le_paquet()))
# SANS PAQUET, RIEN N'EST SIGNALE : il n'y a pas d'instantane a contredire.
_coh.classeur = None
verifier("sans paquet compose, aucun ecart n'est invente",
         not _coh._ecarts_avec_le_paquet())

_coh.close()
_coh.deleteLater()
shutil.rmtree(_coh_bac, ignore_errors=True)

# LES REGLAGES HORS VALEUR PAR DEFAUT (10/11/2026, demande utilisateur) : un
# « ! défaut : … » a droite du champ change, un bouton « Revenir aux
# paramètres par défaut » en tete de chacune des trois etapes, et le defaut
# dit a la derniere ligne de l'infobulle du champ. Ce n'est pas un temoin :
# rien n'est compare au paquet, rien n'est bloque.
_def = mod_plugin.DialogueParametrage(iface)
_def._maj_resume()
_ETAPES_DEFAUTS = (mod_plugin.ONGLET_MODELE, mod_plugin.ONGLET_OBJECTIFS,
                   mod_plugin.ONGLET_LANCER)


def _marque_de(fenetre, cle):
    """Le « ! défaut : … » du champ qui porte cette cle."""
    return next(m for c, _champ, m in fenetre._defauts if c == cle)


def _texte_marque(fenetre, cle):
    """Son texte tel qu'il se lit : sans balises, l'apostrophe rendue."""
    from html import unescape
    return unescape(re.sub("<[^>]+>", "", _marque_de(fenetre, cle).text()))


def _allumees(fenetre):
    return [c for c, _champ, m in fenetre._defauts if not m.isHidden()]


def _boutons_defauts_actifs(fenetre):
    """Par etape (Modele, Parametres, Lancer) : son bouton est-il actif ?"""
    return [next(b for b in fenetre._boutons_defauts
                 if fenetre.onglets.widget(rang).isAncestorOf(b)).isEnabled()
            for rang in _ETAPES_DEFAUTS]


def _cliquer_defauts(fenetre, rang):
    next(b for b in fenetre._boutons_defauts
         if fenetre.onglets.widget(rang).isAncestorOf(b)).click()


_table = noyau.DEFAUTS_PARAMETRES
verifier("defauts : une seule table, dont derivent les constantes et les champs",
         mod_plugin.TOLERANCE_VOLUME_DEFAUT == _table["Tolerance_volume_pct"] / 100 == 0.05
         and mod_plugin.TOLERANCE_PIC_DEFAUT == _table["Tolerance_pic_pct"] / 100 == 0.02
         and noyau.BILAN_MASSE_DEFAUT == _table["Bilan_masse_max_pct"] == 5.0
         and _def.spin_nb_max_essais.value()
         == _table["Nb_max_iterations_par_apport"] == 6
         and (_def.edit_sous_dossier_resultats.text(),
              _def.edit_sous_dossier_suivi.text())
         == (_table["Sous_dossier_resultats"], _table["Sous_dossier_suivi"])
         == ("resultats_finaux", "suivi"),
         f"{mod_plugin.TOLERANCE_VOLUME_DEFAUT} {mod_plugin.TOLERANCE_PIC_DEFAUT} "
         f"{noyau.BILAN_MASSE_DEFAUT} {_def.spin_nb_max_essais.value()}")
verifier("defauts : chaque reglage de la table a sa marque, une seule",
         sorted(c for c, _w, _m in _def._defauts) == sorted(_table),
         str(sorted(set(_table) ^ {c for c, _w, _m in _def._defauts})))
verifier("defauts : a l'ouverture, aucune marque, et les trois boutons inactifs",
         not _allumees(_def) and len(_def._boutons_defauts) == 3
         and _boutons_defauts_actifs(_def) == [False, False, False],
         f"{_allumees(_def)} {_boutons_defauts_actifs(_def)}")
verifier("defauts : le bouton ouvre chacune des trois etapes, a l'infinitif",
         all(_def.onglets.widget(rang).widget().layout().itemAt(0).widget()
             in _def._boutons_defauts for rang in _ETAPES_DEFAUTS)
         and {b.text() for b in _def._boutons_defauts}
         == {"Revenir aux paramètres par défaut"},
         str({b.text() for b in _def._boutons_defauts}))
verifier("defauts : l'infobulle de chaque champ garde son texte et finit par le defaut",
         _def.spin_tol_volume.toolTip().startswith("Écart admis sur le volume")
         and _def.spin_tol_volume.toolTip().endswith("\n\nValeur par défaut : 5 %.")
         and _def.edit_sim_debut.toolTip() == "Valeur par défaut : celui du plan."
         and all(w.toolTip().splitlines()[-1].startswith("Valeur par défaut : ")
                 for _c, w, _m in _def._defauts),
         _def.spin_tol_volume.toolTip()[-40:])
_def.spin_tol_volume.setValue(3.0)
_m_volume = _marque_de(_def, "Tolerance_volume_pct")
verifier("defauts : une valeur changee allume « ! défaut : 5 % », elle seule",
         _allumees(_def) == ["Tolerance_volume_pct"]
         and _texte_marque(_def, "Tolerance_volume_pct") == "! défaut : 5 %",
         f"{_allumees(_def)} {_texte_marque(_def, 'Tolerance_volume_pct')!r}")
verifier("defauts : la marque dit les deux valeurs et le bouton qui remet",
         "« 3 »" in _m_volume.toolTip() and "5 % par défaut" in _m_volume.toolTip()
         and mod_plugin.BOUTON_DEFAUTS in _m_volume.toolTip()
         and _m_volume.accessibleDescription() == _m_volume.toolTip()
         and _m_volume.accessibleName() == "Réglage différent de sa valeur par défaut",
         _m_volume.toolTip())
verifier("defauts : elle a le rouge du plugin, et suit le theme sombre comme les autres textes",
         isinstance(_m_volume, _mod_interface_t.Etiquette)
         and mod_plugin.ISL_ROUGE in _m_volume._texte_original,
         _m_volume._texte_original)
verifier("defauts : seul le bouton de l'etape Parametres devient actif",
         _boutons_defauts_actifs(_def) == [False, True, False],
         str(_boutons_defauts_actifs(_def)))
verifier("defauts : ce n'est pas un temoin — ni ecart avec le paquet, ni « ! » sur la bande",
         not _def._ecarts_avec_le_paquet()
         and not [c for c, t in _def._temoins if not t.isHidden()]
         and _marque_onglet(_def, mod_plugin.ONGLET_OBJECTIFS) is None,
         str(_def._ecarts_avec_le_paquet()))
# LES AUTRES ETAPES, ET LES DEFAUTS QUI SE DISENT EN MOTS.
_def.spin_pk_origine.setValue(250.0)
_def.combo_sens_axe.setCurrentIndex(_def.combo_sens_axe.findData("aval_amont"))
_def.case_elaguer.setChecked(True)
verifier("defauts : le PK, le sens et l'elagage s'annoncent, leur defaut en mots",
         (_texte_marque(_def, "PK_origine_m"), _texte_marque(_def, "Sens_axe"),
          _texte_marque(_def, "Elaguer_plans_etape"))
         == ("! défaut : 0 m", "! défaut : de l'amont vers l'aval", "! défaut : non")
         and _texte_marque(_def, "Coeurs_par_calcul") == "! défaut : ceux du plan"
         and _allumees(_def) == ["Sens_axe", "PK_origine_m", "Tolerance_volume_pct",
                                 "Elaguer_plans_etape"]
         and _boutons_defauts_actifs(_def) == [True, True, True],
         f"{_allumees(_def)} {_boutons_defauts_actifs(_def)}")
# LE BOUTON NE REMET QUE SON ETAPE, ET SANS QUESTION.
BoiteMessage.dernier = None
_cliquer_defauts(_def, mod_plugin.ONGLET_OBJECTIFS)
verifier("defauts : le bouton remet la valeur et eteint la marque, sans question",
         _def.spin_tol_volume.value() == 5.0 and _m_volume.isHidden()
         and BoiteMessage.dernier is None,
         f"{_def.spin_tol_volume.value()} cachee={_m_volume.isHidden()}")
verifier("defauts : il ne touche pas aux reglages des autres etapes",
         _def.spin_pk_origine.value() == 250.0 and _def.case_elaguer.isChecked()
         and _boutons_defauts_actifs(_def) == [True, False, True],
         f"{_allumees(_def)} {_boutons_defauts_actifs(_def)}")
_cliquer_defauts(_def, mod_plugin.ONGLET_MODELE)
_cliquer_defauts(_def, mod_plugin.ONGLET_LANCER)
verifier("defauts : les boutons des etapes Modele et Lancer remettent les leurs",
         _def.spin_pk_origine.value() == 0.0
         and _def.combo_sens_axe.currentData() == "amont_aval"
         and not _def.case_elaguer.isChecked()
         and not _allumees(_def)
         and _boutons_defauts_actifs(_def) == [False, False, False],
         f"{_allumees(_def)} {_boutons_defauts_actifs(_def)}")
# UNE FENETRE DE SIMULATION PAR DEFAUT EST CELLE DU PLAN : le champ la montre
# remplie, et seule une saisie qui s'en ecarte s'annonce.
_def.combo_plan.addItem("p01 — Q100", {
    "numero": "01", "titre": "Q100", "geometrie": "01", "unsteady": "01",
    "fenetre": {"debut": "13OCT2014,00:00", "fin": "14OCT2014,04:00",
                "intervalle_calcul": "1SEC", "intervalle_sortie": "1MIN",
                "intervalle_instantane": "1MIN", "intervalle_mapping": "1MIN"}})
verifier("defauts : la fenetre du plan, recopiee dans les champs, n'allume rien",
         _def.edit_sim_fin.text() == "14OCT2014,04:00" and not _allumees(_def),
         f"{_def.edit_sim_fin.text()!r} {_allumees(_def)}")
_def.edit_sim_fin.setText("14OCT2014,02:00")
verifier("defauts : une fin de simulation saisie s'annonce « celle du plan »",
         _allumees(_def) == ["Simulation_fin"]
         and _texte_marque(_def, "Simulation_fin") == "! défaut : celle du plan"
         and _boutons_defauts_actifs(_def) == [True, False, False],
         f"{_allumees(_def)} {_texte_marque(_def, 'Simulation_fin')!r}")
_cliquer_defauts(_def, mod_plugin.ONGLET_MODELE)
verifier("defauts : et le bouton y remet la fenetre du plan",
         _def.edit_sim_fin.text() == "14OCT2014,04:00" and not _allumees(_def),
         f"{_def.edit_sim_fin.text()!r} {_allumees(_def)}")
_def.close()
_def.deleteLater()

verifier("le prefixe de scenario a quitte l'onglet Objectifs",
         "Préfixe de scénario" not in [g.title() for g in dlg.onglets.widget(
             mod_plugin.ONGLET_OBJECTIFS).findChildren(_QGroupBoxA)],
         str([g.title() for g in dlg.onglets.widget(
             mod_plugin.ONGLET_OBJECTIFS).findChildren(_QGroupBoxA)]))

# LE RECAPITULATIF DE REPRISE (20/09/2026, demande utilisateur).
#
# SUR UNE FENETRE JETABLE, ET C'EST LA LECON. Eprouve sur « dlg », il devait
# lui poser un classeur, un prefixe et un premier apport — puis les retirer.
# Avec un modele, « dlg » portait deja un classeur REEL a cet endroit : le
# rendre a None ensuite laissait la suite du banc devant un etat que rien
# n'avait produit, et sept controles sans rapport tombaient. Un essai qui
# doit reparer l'etat qu'il abime est un essai qui le reparera mal un jour.
_recap_dlg = mod_plugin.DialogueParametrage(iface)
# SANS L'APPELER A LA MAIN : c'est la construction qui doit l'avoir rempli.
# Le banc l'appelait, et ne pouvait donc pas voir qu'a l'ouverture de la
# fenetre reelle il restait vide — constate le 20 septembre 2026 sur le QGIS
# du poste, pas au banc.
# isHidden(), NON isVisibleTo() : QTabWidget masque les pages qui ne sont
# pas a l'ecran, si bien que tout widget d'un autre onglet est « invisible »
# pour Qt. isHidden() ne dit que ce qui nous interesse — le label a-t-il ete
# masque par texte_etat("") faute d'avoir ete rempli.
verifier("le recapitulatif est rempli des l'ouverture, sans rien toucher",
         bool(_recap_dlg.label_reprise.text())
         and not _recap_dlg.label_reprise.isHidden(),
         repr(_recap_dlg.label_reprise.text()[:60]))
verifier("sans paquet compose, le recapitulatif dit quoi faire",
         "composé" in _recap_dlg.label_reprise.text()
         and mod_plugin.BOUTON_GEOMETRIE in _recap_dlg.label_reprise.text(),
         _recap_dlg.label_reprise.text()[:80])
# AVEC UN CLASSEUR, il nomme le plan de depart AVEC SON PREFIXE, les apports
# tenus pour cales et ceux qui restent a calculer. C'est le cas signale le
# 20 septembre : apres un ECHEC, _confirmer_reprise ne pose aucune question
# — rien n'est « valide » a perdre — et aucun ecran ne disait d'ou l'on
# repartait.
import pandas as _pd                                          # noqa: E402
_cl = Path(tempfile.gettempdir()) / "recap_reprise.xlsx"
_pd.DataFrame({"Ordre": [1, 2, 3, 4],
               "Nom_Apport (BC line)": ["A1", "A2", "A3", "A4"],
               "Nom_Section (reference line)": ["S1", "S2", "S3", "S4"]}
              ).to_excel(_cl, sheet_name="Correspondance", index=False)
_recap_dlg.edit_prefixe_scenario.setText("Q100")
_recap_dlg.classeur = str(_cl)
_recap_dlg._remplir_premier_apport()
_recap_dlg.combo_premier_apport.setCurrentIndex(3)   # depart a « A3 »
_recap = _recap_dlg.label_reprise.text()
verifier("le recapitulatif nomme le plan de depart avec son prefixe",
         "Q100-A2" in _recap, _recap)
verifier("le recapitulatif nomme les apports tenus pour cales",
         "A1, A2" in _recap, _recap)
verifier("le recapitulatif nomme les apports restant a calculer",
         "A3, A4" in _recap, _recap)
verifier("le recapitulatif previent si le plan de depart manque",
         "S’il manque" in _recap, _recap)
_recap_dlg.combo_premier_apport.setCurrentIndex(0)   # « tous »
verifier("sans depart choisi, le recapitulatif annonce le calage complet",
         "Calage complet" in _recap_dlg.label_reprise.text()
         and "Q100-sans" in _recap_dlg.label_reprise.text(),
         _recap_dlg.label_reprise.text())
# UN PLAN PORTE DEJA LE NOM DU PLAN FINAL (0.9.30). Le plan final porte le
# prefixe seul. Le plan source etait refuse ; depuis le 10/11/2026 (decision
# utilisateur : recaler un plan valide qui garde son nom) il demande
# confirmation, comme tout autre plan, et le talon de boite ne clique rien :
# cela vaut « Annuler ».
_recap_dlg.edit_projet_hecras.setText("")
_recap_dlg.info_projet = {"plans": [{"numero": "01", "titre": "Q100"},
                                    {"numero": "07", "titre": "Q100 "},
                                    {"numero": "08", "titre": "Autre"}]}
_recap_dlg.combo_plan.currentData = lambda: {"numero": "01"}
verifier("plan final : le plan source et les autres plans du nom sont distingues",
         _recap_dlg._plans_au_titre_final(_recap_dlg.info_projet) == ("01", ["07"]),
         str(_recap_dlg._plans_au_titre_final(_recap_dlg.info_projet)))
BoiteMessage.dernier = None
verifier("plan final : un plan source au nom du prefixe demande, et sans clic rien ne part",
         _recap_dlg._accepter_plan_final() is False
         and _recap_dlg._remplacer_plan_source is False
         and _recap_dlg.label_lancement.text() == "Lancement annulé.",
         _recap_dlg.label_lancement.text())
_boite_source = BoiteMessage.dernier
verifier("plan final : la question du plan source a « Annuler » pour defaut, et des verbes",
         _boite_source is not None and _boite_source.bouton_defaut is not None
         and _boite_source.bouton_defaut.role == _RolesBouton.RejectRole
         and _boite_source.bouton_echappement is _boite_source.bouton_defaut
         and [b.text() for b in _boite_source.boutons]
         == ["Remplacer à la fin du calage", "Annuler"],
         str([b.text() for b in _boite_source.boutons]) if _boite_source
         else "aucune boite")
verifier("plan final : elle nomme le plan de reference, et dit ce qui est supprime",
         _boite_source is not None
         and "Remplacer le plan de référence p01 « Q100 »" in _boite_source.texte
         and "travaille sur une copie" in _boite_source.texte
         # DES QUE TOUT EST CALE, objectif tenu ou degrade (16/11/2026) ; un
         # arret sur un apport laisse le plan intact.
         and "Si tous les apports sont calés" in _boite_source.texte
         and "p01 et ses résultats sont supprimés" in _boite_source.texte
         and "Si le calage s'arrête sur un apport" in _boite_source.texte
         and "reste intact" in _boite_source.texte,
         re.sub("<[^>]+>", " ", _boite_source.texte)[:140] if _boite_source else "")
_recap_dlg._dire_titres_prefixe()
verifier("plan final : la ligne sous le prefixe dit que le plan de reference sera remplace",
         "Même nom que le plan de référence p01" in _recap_dlg.label_titres_prefixe.text()
         and "qui le remplacera dès que tous les apports seront calés"
         in _recap_dlg.label_titres_prefixe.text()
         and "Le lancement demandera confirmation" in _recap_dlg.label_titres_prefixe.text()
         and "refusé" not in _recap_dlg.label_titres_prefixe.text()
         # PLUS EN ROUGE (16/11/2026) : le rouge se lisait comme un refus.
         and mod_plugin.ISL_ROUGE not in _recap_dlg.label_titres_prefixe.text()
         # ET LES AUTRES PLANS DU NOM RESTENT ANNONCES : le lancement posera
         # les deux questions.
         and "le plan p07 sera" in _recap_dlg.label_titres_prefixe.text(),
         re.sub("<[^>]+>", " ", _recap_dlg.label_titres_prefixe.text())[:140])
# L'ACCORD EST RETENU, PUIS ECRIT AU LANCEMENT avec les autres reglages. Le
# talon clique ici le premier bouton ; l'etat des cibles, pose a la main,
# arrete le lancement juste apres l'ecriture : aucune chaine n'est lancee.
_clic_talon, _ecrire_noyau, _etat_noyau = (
    BoiteMessage.clickedButton, noyau.ecrire_parametre, noyau.etat_cibles)
_ecrits, _avertis = {}, []
BoiteMessage.clickedButton = lambda self: self.boutons[0]
BoiteMessage.warning = staticmethod(lambda parent, titre, texte: _avertis.append(titre))
noyau.ecrire_parametre = lambda classeur, cle, valeur: _ecrits.update({cle: valeur})
noyau.etat_cibles = lambda classeur: {"manquantes": ["S1"], "total": 4}
try:
    verifier("plan final : accepter retient le remplacement, puis demande pour les autres plans",
             _recap_dlg._accepter_plan_final() is True
             and _recap_dlg._remplacer_plan_source is True
             and "p07" in BoiteMessage.dernier.texte,
             re.sub("<[^>]+>", " ", BoiteMessage.dernier.texte)[:80])
    _recap_dlg._lancer_calage()
    verifier("plan final : le lancement ecrit l'accord sous « Remplacer_plan_source »",
             _ecrits.get("Remplacer_plan_source") == "oui"
             and _avertis == ["Hydrogrammes cibles incomplets"],
             f"{_ecrits.get('Remplacer_plan_source')!r} {_avertis}")
    _recap_dlg.combo_plan.currentData = lambda: {"numero": "08"}
    _ecrits.clear()
    _recap_dlg._lancer_calage()
    verifier("plan final : sans plan de reference de ce nom, il ecrit « non »",
             _ecrits.get("Remplacer_plan_source") == "non"
             and _recap_dlg._remplacer_plan_source is False,
             f"{_ecrits.get('Remplacer_plan_source')!r}")
finally:
    BoiteMessage.clickedButton = _clic_talon
    noyau.ecrire_parametre, noyau.etat_cibles = _ecrire_noyau, _etat_noyau
    del BoiteMessage.warning
_recap_dlg.combo_plan.currentData = lambda: {"numero": "08"}
verifier("plan final : un autre plan du nom demande, et sans clic rien ne part",
         _recap_dlg._plans_au_titre_final(_recap_dlg.info_projet) == (None, ["01", "07"])
         and _recap_dlg._accepter_plan_final() is False)
_recap_dlg._dire_titres_prefixe()
verifier("plan final : la ligne sous le prefixe nomme le plan remplace",
         "p01, p07" in _recap_dlg.label_titres_prefixe.text(),
         re.sub("<[^>]+>", " ", _recap_dlg.label_titres_prefixe.text())[:140])
_recap_dlg.info_projet = {"plans": [{"numero": "08", "titre": "Autre"}]}
verifier("plan final : sans plan de ce nom, le lancement ne demande rien",
         _recap_dlg._accepter_plan_final() is True)
del _recap_dlg.combo_plan.currentData
_recap_dlg.close()
_recap_dlg.deleteLater()

# L'ACTION N'APPARTIENT PLUS A AUCUN ONGLET (0.7.24, demande utilisateur).
# Elle est redescendue au bas de la fenetre, a cote de « Fermer », ou elle
# vivait jusqu'a la 0.7.19 — et elle DIT desormais si c'est le moment.
_page_objectifs = dlg.onglets.widget(mod_plugin.ONGLET_OBJECTIFS)
_groupes_objectifs = [g.title() for g in _page_objectifs.findChildren(_QGroupBoxA)]
_boutons_partout = []
for _i in range(dlg.onglets.count()):
    _boutons_partout += [b.text()
                         for b in dlg.onglets.widget(_i).findChildren(
                             _QPushButtonA)]
verifier("le bouton de controle a quitte tous les onglets",
         not [b for b in _boutons_partout
              if "ontrôle paramétrage" in b or "composer" in b],
         [b for b in _boutons_partout if "ontrôle" in b or "composer" in b])
# UN SEUL BOUTON, SOUS LE PREFIXE (22/09/2026, demande utilisateur) : il
# ecrit la geometrie, compose le classeur et controle — la composition
# automatique renoncait en silence, et « Ouvrir dans Excel » restait gris
# sans que rien ne dise pourquoi.
verifier("il nomme les trois gestes et vit sous le prefixe, a l'etape Parametres",
         dlg.bouton_controle.text().replace("\n", " ")
         == "Valider la géométrie et générer le fichier des hydrogrammes"
         and dlg.bouton_controle in dlg.onglets.widget(
             mod_plugin.ONGLET_OBJECTIFS).findChildren(_QPushButtonA)
         and dlg.bouton_controle.parentWidget().title() == "Hydrogrammes cibles",
         f"{dlg.bouton_controle.text()} | {dlg.bouton_controle.parentWidget().title()}")
_pid_clic = dlg.pid_lance
dlg.pid_lance = None
BoiteMessage.critiques.clear()
dlg.bouton_controle.click()
_refus_clic = BoiteMessage.critiques[0] if BoiteMessage.critiques else ""
verifier("cliqué sans modèle, il refuse et nomme l'étape où l'on va",
         "onglet 1" in _refus_clic.lower() or "étape" in _refus_clic.lower(),
         _refus_clic[:90] or "aucun refus")
BoiteMessage.critiques.clear()
dlg.pid_lance = _pid_clic
_manquants_bouton = [nom for nom, ok in dlg._etapes_avant_controle() if not ok]
verifier("son infobulle nomme exactement ce qui manque, axe, préfixe et dossier compris",
         all(nom in dlg.bouton_controle.toolTip() for nom in _manquants_bouton)
         and {"l'axe hydraulique", "le préfixe de scénario", "le dossier de sortie"}
         <= {nom for nom, _ in dlg._etapes_avant_controle()},
         dlg.bouton_controle.toolTip()[:160])
# PLUS AUCUNE RECOMPOSITION AUTOMATIQUE (24/09/2026, demande utilisateur) :
# taper « Q100 » en marquant une pause composait « Q1 » — un dossier
# « _calage\Q1 » avec son classeur, et la fenetre basculait dessus. Rien ne
# doit partir d'une frappe, meme apres plus que les 1,5 s de l'ancien
# minuteur ; le clic, lui, compose — c'est le temoin que l'espion marche.
from qgis.PyQt.QtTest import QTest as _QTestR                  # noqa: E402
_appels_compo = []
_saisie_avant = (dlg.edit_prefixe_scenario.text(),
                 dlg.edit_dossier_sortie.text())
dlg._composer_et_controler_interne = lambda: _appels_compo.append("clic")
for _frappe in ("Q1", "Q100"):
    dlg.edit_prefixe_scenario.setText(_frappe)
    _QTestR.qWait(1800)
verifier("taper un prefixe ne compose rien, meme apres une pause",
         not _appels_compo and not hasattr(dlg, "_minuteur_recomposition"),
         f"{len(_appels_compo)} composition(s) partie(s) de la frappe")
dlg.bouton_controle.click()
verifier("le clic sur le bouton, lui, compose",
         _appels_compo == ["clic"], str(_appels_compo))
# ET JAMAIS DEUX A LA FOIS : un second clic pendant une composition, qui
# traite des evenements Qt en chemin, ferait deux ecritures concurrentes.
dlg._composition_en_cours = True
dlg.bouton_controle.click()
verifier("jamais pendant qu'une composition tourne deja",
         _appels_compo == ["clic"], str(_appels_compo))
dlg._composition_en_cours = False
del dlg._composer_et_controler_interne
dlg.edit_prefixe_scenario.setText(_saisie_avant[0])
dlg.edit_dossier_sortie.setText(_saisie_avant[1])
# LA SUITE DU BANC PART SANS PAQUET, comme avant ce bloc depuis la 0.9.5.
dlg.classeur = None
# LA BARRE DE PREPARATION (20/09/2026, demande utilisateur). Elle compte la
# SAISIE avant lancement, non le calage — celui-ci dure des heures et se lit a
# l'onglet Suivi. On eprouve donc son libelle, son compte, et le fait qu'elle
# vive au bas de la fenetre, a cote du bouton qu'elle prepare.
_barre_prep = dlg.barre_preparation
verifier("la barre de preparation reste au bas de la fenetre",
         _barre_prep.parent() is dlg, str(_barre_prep.parent()))
verifier("elle compte les quatre etapes de la saisie",
         _barre_prep.maximum() == len(dlg._etapes_preparation()) == 4,
         f"{_barre_prep.value()}/{_barre_prep.maximum()}")
# LE COMPTE EN CHIFFRES, PAS SEULEMENT UN REMPLISSAGE : une barre aux trois
# quarts ne dit pas laquelle des quatre etapes manque.
verifier("elle porte son compte en chiffres et se nomme « Préparation »",
         _barre_prep.isTextVisible() and "Préparation" in _barre_prep.format()
         and "%v" in _barre_prep.format() and "%m" in _barre_prep.format(),
         _barre_prep.format())
# ET ELLE DIT QU'ELLE NE PARLE PAS DU CALAGE. C'est la confusion que la
# demande nommait : une barre dans une fenetre de calage se lit comme
# l'avancement du calcul.
verifier("son infobulle distingue la saisie du calage",
         "SAISIE" in _barre_prep.toolTip() and "non du calage" in _barre_prep.toolTip(),
         _barre_prep.toolTip()[:70])
# LE COMPTE SUIT L'ETAT REEL, et il vient de la MEME liste que le fil.
_avant_barre = _barre_prep.value()
_dossier_avant = dlg.edit_dossier_sortie.text()
dlg.edit_dossier_sortie.setText("")
dlg._maj_fil()
_vide = _barre_prep.value()
dlg.edit_dossier_sortie.setText(str(Path(tempfile.gettempdir()) / "barre_essai"))
dlg._maj_fil()
verifier("renseigner le dossier de sortie fait avancer la barre",
         _barre_prep.value() == _vide + 1,
         f"{_vide} -> {_barre_prep.value()}")
verifier("et sa description accessible nomme ce qui manque encore",
         (str(_barre_prep.value()) in _barre_prep.accessibleDescription()
          and ("il reste" in _barre_prep.accessibleDescription()
               or _barre_prep.value() == _barre_prep.maximum())),
         _barre_prep.accessibleDescription())
verifier("le compte n'est plus dit deux fois : le fil ne le porte plus",
         "/4" not in dlg.label_fil.text(),
         dlg.label_fil.text()[:80])
verifier("la barre et le fil comptent la meme chose",
         _barre_prep.value() == sum(bool(ok) for _, ok in dlg._etapes_preparation()),
         f"barre={_barre_prep.value()}")
dlg.edit_dossier_sortie.setText(_dossier_avant)
dlg._maj_fil()
verifier("et l'etat de depart est rendu",
         _barre_prep.value() == _avant_barre,
         f"{_barre_prep.value()} attendu {_avant_barre}")

# LE JOURNAL EN COURS, DANS LE SUIVI (20/09/2026, demande utilisateur).
# L'encadre des alertes ne montre que les lignes portant un mot d'alerte ;
# celui-ci montre le fil, et c'est lui qui dit OU le calage en etait.
verifier("le suivi porte un journal en cours, replie et masque a vide",
         dlg.groupe_journal.isCollapsed() and not dlg.groupe_journal.isVisible()
         and dlg.texte_journal.isReadOnly(),
         f"replie={dlg.groupe_journal.isCollapsed()}")
_faux_journal = Path(tempfile.gettempdir()) / "journal_essai_suivi.log"
_faux_journal.write_text(
    "\n".join([f"2026-09-20 10:00:{i:02d} ligne ordinaire {i}"
               for i in range(5)]
              + ["2026-09-20 10:00:05 AVERTISSEMENT : cible recadencee"]),
    encoding="utf-8")
dlg.journal_lance = str(_faux_journal)
dlg._cle_journal_lu = None
dlg._peindre_journal()
dlg._peindre_alertes()
verifier("le journal en cours montre les lignes ORDINAIRES, pas seulement les alertes",
         "ligne ordinaire 0" in dlg.texte_journal.toPlainText()
         and "ligne ordinaire 4" in dlg.texte_journal.toPlainText(),
         dlg.texte_journal.toPlainText()[:60])
verifier("l'encadre des alertes, lui, ne retient que l'alerte",
         "ligne ordinaire" not in dlg.texte_alertes.toPlainText()
         and "AVERTISSEMENT" in dlg.texte_alertes.toPlainText(),
         dlg.texte_alertes.toPlainText()[:60])
verifier("le titre du journal nomme le fichier suivi",
         _faux_journal.name in dlg.groupe_journal.title(),
         dlg.groupe_journal.title())
# UNE SEULE LECTURE POUR LES DEUX VUES : la cle de relecture ne bouge pas
# quand on repeint sans que le fichier ait change.
_cle = dlg._cle_journal_lu
dlg._peindre_journal()
dlg._peindre_alertes()
verifier("un journal inchange n'est pas relu",
         dlg._cle_journal_lu == _cle)
verifier("le journal ne se deplie jamais tout seul",
         dlg.groupe_journal.isCollapsed(),
         "un journal qui s'ouvre a chaque ligne rendrait la page sautante")
dlg.journal_lance = None
dlg._cle_journal_lu = None

verifier("aucun onglet ne porte plus l'encadre « Contrôle du paramétrage »",
         "Contrôle du paramétrage" not in _groupes_objectifs
         and "Contrôle du paramétrage" not in
         [g.title() for g in
          dlg.onglets.widget(mod_plugin.ONGLET_LANCER).findChildren(_QGroupBoxA)],
         _groupes_objectifs)

# VERT QUAND C'EST LE MOMENT, GRIS SINON. L'etat vient des memes etapes que
# le fil conducteur : deux lectures qui divergeraient donneraient un bouton
# vert sous un fil qui reclame encore une etape.
verifier("sans modele charge, le bouton est gris",
         dlg.bouton_controle.objectName() == "boutonControleAttente",
         dlg.bouton_controle.objectName())
verifier("et son infobulle nomme ce qui manque",
         "Il manque encore" in dlg.bouton_controle.toolTip(),
         dlg.bouton_controle.toolTip()[:90])
verifier("il reste cliquable en gris — il n'est pas desactive",
         dlg.bouton_controle.isEnabled())
_etapes_faussees = [("le modèle chargé", True), ("le profil en long", True),
                    ("le dossier de sortie", True)]
_vraies_etapes = dlg._etapes_avant_controle
dlg._etapes_avant_controle = lambda: _etapes_faussees
_pid_avant = dlg.pid_lance
dlg.pid_lance = None
dlg._maj_bouton_controle()
verifier("tout etant pret, il passe au vert",
         dlg.bouton_controle.objectName() == "boutonControlePret",
         dlg.bouton_controle.objectName())
verifier("et la feuille de style connait cet habillage",
         "boutonControlePret" in mod_plugin.STYLE_ISL
         and "boutonControleAttente" in mod_plugin.STYLE_ISL)
# UN CALAGE QUI TOURNE LE REMET AU GRIS : recomposer pendant un calcul
# reecrit la geometrie et le classeur que ce calcul partage.
dlg.pid_lance = 4242
dlg._maj_bouton_controle()
verifier("un calage en cours le remet au gris, et le dit",
         dlg.bouton_controle.objectName() == "boutonControleAttente"
         and "4242" in dlg.bouton_controle.toolTip(),
         dlg.bouton_controle.toolTip()[:90])
dlg.pid_lance = _pid_avant
dlg._etapes_avant_controle = _vraies_etapes
dlg._maj_bouton_controle()

# CE QUE PORTENT LES CIBLES (0.7.24, demande utilisateur) : le pic et le
# volume de chaque hydrogramme, relus apres validation de l'Excel.
verifier("l'onglet 3 porte « Ce que portent les hydrogrammes cibles »",
         "Ce que portent les hydrogrammes cibles" in _groupes_objectifs,
         _groupes_objectifs)
# « COMPOSER LE PAQUET » N'EST PLUS UN GESTE (21/09/2026) : il se fait tout
# seul. Ce qui manque n'est pas une action, c'est un fichier.
verifier("et il attend d'avoir un classeur avant de rien dire",
         "préfixe de scénario" in dlg.label_resume_cibles.text()
         and "Composer le paquet" not in dlg.label_resume_cibles.text(),
         dlg.label_resume_cibles.text()[:90])

# LE CLASSEUR MODIFIE HORS QGIS EST RELU AU RETOUR (0.8.1) : Excel enregistre,
# la date du fichier change, la fenetre s'en apercoit au changement d'onglet
# ou quand QGIS redevient actif — sans recomposer. Sur une COPIE du gabarit :
# le mecanisme ne depend pas d'un modele, et l'on touche a la date du fichier.
_gabarit = Path(mod_plugin.__file__).parents[1] / "template_donnees_calage.xlsx"
_copie = Path(tempfile.mkdtemp(prefix="_relecture_")) / _gabarit.name
shutil.copy2(_gabarit, _copie)
dlg.classeur = str(_copie)
dlg._relire_cibles_si_modifiees()
_lu = dlg._classeur_lu
verifier("un classeur designe est lu a la premiere occasion",
         _lu is not None
         and "Composer le paquet" not in dlg.label_resume_cibles.text(),
         dlg.label_resume_cibles.text()[:80])
dlg.label_resume_cibles.setText("périmé")
dlg._relire_cibles_si_modifiees()
verifier("et n'est pas rouvert tant qu'il n'a pas change",
         dlg.label_resume_cibles.text() == "périmé")
_apres = os.path.getmtime(_copie) + 5
os.utime(_copie, (_apres, _apres))
dlg._relire_cibles_si_modifiees()
verifier("le classeur modifie sur disque est relu au retour dans QGIS",
         dlg._classeur_lu != _lu
         and "périmé" not in dlg.label_resume_cibles.text(),
         dlg.label_resume_cibles.text()[:80])
dlg.classeur = None
dlg._maj_resume_cibles()
shutil.rmtree(_copie.parent, ignore_errors=True)

# WIDGETS NATIFS QGIS (0.8.2). Le bandeau de messages remplace les boites
# d'information : cache tant qu'il n'a rien a dire, visible des le premier
# message, et c'est LUI qui parle quand on ouvre l'Excel sans paquet.
verifier("bandeau de messages present et muet a l'ouverture",
         hasattr(dlg, "barre_messages")
         and not dlg.barre_messages.isVisibleTo(dlg))
dlg.classeur = None
dlg._ouvrir_classeur()
verifier("ouvrir l'Excel sans paquet : avertissement dans le bandeau, pas de boite",
         dlg.barre_messages.isVisibleTo(dlg)
         and dlg.barre_messages.currentItem() is not None
         and "Aucun Excel pour l'instant" in dlg.barre_messages.currentItem().text(),
         dlg.barre_messages.currentItem().text()[:60]
         if dlg.barre_messages.currentItem() else "aucun message")
dlg.barre_messages.clearWidgets()
# Les trois aides depliables sont des QgsCollapsibleGroupBox nommes — le
# nom forme la cle sous laquelle QGIS memorise l'etat replie — et partent
# replies.
_repliables = {g.objectName(): g for g in
               dlg.findChildren(mod_plugin.QgsCollapsibleGroupBox)}
verifier("trois groupes repliables natifs, nommes",
         {"grpPente", "grpSousDossiers", "grpConfiguration"} <= set(_repliables),
         sorted(_repliables))
verifier("et replies au depart",
         all(_repliables[n].isCollapsed() for n in
             ("grpPente", "grpSousDossiers", "grpConfiguration")
             if n in _repliables),
         {n: g.isCollapsed() for n, g in _repliables.items()})

# LE TABLEAU DES CIBLES N'ELARGIT PLUS LA PAGE (0.8.2). C'est lui qui
# faisait deborder l'onglet 3 de 37 px a 13 pt : un tableau HTML ne se
# replie pas, et sa largeur remontait jusqu'a la page. Il defile
# desormais dans son cadre. Le controle compare la largeur minimale de la
# page AVANT et APRES remplissage — il ne depend donc d'aucune police.
_interieur = (_page_objectifs.widget()
              if hasattr(_page_objectifs, "widget") else _page_objectifs)
dlg.label_resume_cibles.setText(mod_plugin.DialogueParametrage._ATTENTE_CIBLES)
dlg.label_resume_cibles.setMinimumHeight(0)
_interieur.adjustSize()
_avant = _interieur.minimumSizeHint().width()
dlg.label_resume_cibles.setText(
    "<table cellspacing='0' cellpadding='2'><tr>"
    "<th align='left'>Apport → section</th>"
    "<th align='right'>&nbsp;&nbsp;Pointe (m³/s)</th>"
    "<th align='right'>&nbsp;&nbsp;Heure du pic (h)</th>"
    "<th align='right'>&nbsp;&nbsp;Volume (hm³)</th></tr>"
    + "".join("<tr><td>APPORT_TRES_LONG_%02d → SECTION_TRES_LONGUE_%02d</td>"
                "<td align='right'>1 234.5</td><td align='right'>12.34</td>"
                "<td align='right'>123.456</td></tr>" % (i, i)
                for i in range(8))
    + "</table>")
_interieur.adjustSize()
_apres = _interieur.minimumSizeHint().width()
verifier("la page Objectifs tient dans la vue la plus etroite",
         _interieur.minimumSizeHint().width() <= dlg.minimumWidth() - 50,
         f"{_interieur.minimumSizeHint().width()} px pour "
         f"{dlg.minimumWidth() - 50} px disponibles")
verifier("un tableau de cibles large n'elargit pas la page Objectifs",
         _apres <= _avant,
         f"avant {_avant} px, apres {_apres} px "
         f"(tableau : {dlg.label_resume_cibles.minimumSizeHint().width()} px)")
dlg.label_resume_cibles.setText(mod_plugin.DialogueParametrage._ATTENTE_CIBLES)

# LA GEOMETRIE DE LA FENETRE EST RETENUE D'UNE SESSION A L'AUTRE (0.8.2).
# L'appel vit dans PluginCalage.composer(), pas dans le constructeur : le banc
# et les captures construisent la fenetre directement et ont besoin d'une
# geometrie deterministe. On l'eprouve donc sur une fenetre JETABLE, avec une
# cle a elle — l'activer ici sur DialogueParametrage fausserait la matrice
# d'affichage, qui redimensionne a 800 x 620.
_jetable = _QDialogA()
_jetable.setObjectName("essaiGeometrieCalage")
try:
    mod_plugin.QgsGui.enableAutoGeometryRestore(_jetable, "calage_apports/essai")
    _restaure = True
except Exception as _e:                                      # noqa: BLE001
    _restaure = _e
verifier("QgsGui.enableAutoGeometryRestore est appelable sur ce QGIS",
         _restaure is True, str(_restaure))
_jetable.deleteLater()

# « RELIRE UN HYDROGRAMME » A QUITTE LA FENETRE (0.7.22). L'outil vit encore,
# en ligne de commande ; c'est l'onglet qui n'avait pas a le porter.
verifier("l'onglet du lancement ne porte plus la relecture d'hydrogramme",
         "Relire un hydrogramme déjà calculé" not in
         [g.title() for g in dlg.onglets.widget(
             mod_plugin.ONGLET_LANCER).findChildren(_QGroupBoxA)])

# L'ELAGAGE EST UNE CASE, ET ELLE DIT CE QU'ELLE FERA. La conservation est
# neutre ; la suppression reste un avertissement. Ici on eprouve la decision
# annoncee, pas un code couleur qui doit aussi s'adapter au theme de QGIS.
dlg.case_elaguer.setChecked(False)
verifier("case decochee : les plans intermediaires sont dits CONSERVES",
         "conservés" in dlg.label_elagage.text()
         and "supprimés" not in dlg.label_elagage.text(),
         dlg.label_elagage.text())
dlg.case_elaguer.setChecked(True)
verifier("case cochee : ils sont dits SUPPRIMES",
         "supprimés" in dlg.label_elagage.text(),
         dlg.label_elagage.text())
dlg.case_elaguer.setChecked(False)

# ET LE CHOIX VOYAGE JUSQU'A LA CHAINE, par le classeur — c'est elle qui
# elague, en fin de calage, quand le plan final existe.
def _parametres_essai(**extra):
    return mod_plugin.noyau.parametres_calage(
        ".", "P", "7.0.1", "Z", "01", "01", "01", "plan", "G", "",
        "amont_aval", 0.0, 8, 5.0, 2.0, ".", "r", "s",
        prefixe_scenario="Q100", **extra)


verifier("le parametre d'elagage part dans le classeur",
         _parametres_essai(elaguer_etapes=True)["Elaguer_plans_etape"] == "oui"
         and _parametres_essai()["Elaguer_plans_etape"] == "non",
         f"coche -> {_parametres_essai(elaguer_etapes=True)['Elaguer_plans_etape']} "
         f"| decoche -> {_parametres_essai()['Elaguer_plans_etape']}")
# LES SECTIONS DEJA CALEES SE TRACENT DERRIERE LA PAIRE COURANTE. Le banc
# n'eprouve pas l'apparence, mais il peut verifier que le widget ACCEPTE les
# deux jeux et les retient : sans cela, une signature changee d'un cote et pas
# de l'autre ne se verrait qu'a l'ecran, pendant un calage.
_serie_t = [round(0.5 * i, 2) for i in range(40)]
_serie_q = [round(100.0 * (1 - abs(i - 20) / 20.0), 2) for i in range(40)]
dlg.courbe_suivi.actualiser(
    {"temps_cible": _serie_t, "debit_cible": _serie_q,
     "temps_calcule": _serie_t, "debit_calcule": _serie_q,
     "decalage_h": 0.0, "apport": "A2", "section": "SC2"},
    [{"apport": "A1", "section": "SC1", "temps": _serie_t,
      "debit": [q / 2 for q in _serie_q]}])
verifier("la courbe de suivi retient les sections deja calees",
         len(dlg.courbe_suivi.precedentes) == 1
         and dlg.courbe_suivi.precedentes[0]["section"] == "SC1",
         str(dlg.courbe_suivi.precedentes)[:60])
dlg.courbe_suivi.actualiser(None, None)
verifier("et les oublie quand il n'y a plus de calage suivi",
         dlg.courbe_suivi.precedentes == []
         and dlg.courbe_suivi.courbes is None)

# LE MENAGE EST UNE CASE (0.7.22), ET IL VIT DESORMAIS DANS « Lancer »
# (20/09/2026) : il se coche avant le calage, avec le reste de ce qui decide
# du lancement ; c'est la chaine qui elague a la fin, quand le plan final
# existe.
_page_resultats = dlg.onglets.widget(mod_plugin.ONGLET_LANCER)
_groupes_resultats = [g.title() for g in _page_resultats.findChildren(_QGroupBoxA)]
verifier("l'onglet du lancement porte la conservation des plans d’etape",
         "Conservation des plans d’étape" in _groupes_resultats, _groupes_resultats)
verifier("l'elagage est une case a cocher, plus un bouton",
         "Élaguer les plans d'étape…" not in
         [b.text() for b in _page_resultats.findChildren(_QPushButtonA)]
         and dlg.case_elaguer.parent() is not None)
verifier("et elle est DECOCHEE par defaut : on ne supprime rien sans le dire",
         not dlg.case_elaguer.isChecked())

# L'ORDRE DES ENCADRES EST UN CONTENU, et il suit l'ordre des gestes
# (0.7.22) : on choisit le projet, puis le plan, on CHARGE les couches qu'il
# designe, on trace le profil en long dessus, et l'on ne touche a la fenetre
# de simulation que si l'Unsteady couvre une autre periode.
# LE GESTE IRREVERSIBLE A QUITTE CET ONGLET (22/09/2026, demande
# utilisateur) : il vit sous le prefixe, a l'etape Parametres, et compose de
# nouveau. L'onglet 1 s'arrete a la fenetre de simulation.
verifier("l'onglet 1 suit l'ordre des gestes",
         len(_groupes_modele) == 5
         and all(mot in titre.lower() for mot, titre in zip(
             ("projet", "plan", "couches", "axe", "simulation"),
             _groupes_modele)),
         _groupes_modele)
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
# du plugin etaient concernes.
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

# LE COMPTE EST DANS LA BARRE, PAS DANS LE FIL : il s'y lisait deux fois.
# Le fil garde ce que la barre ne sait pas dire — quoi faire, et le lien.
verifier("fil conducteur renseigne et coherent",
         ("Prochaine étape" in dlg.label_fil.text()
          or "Paquet composé" in dlg.label_fil.text()
          or "Calage lancé" in dlg.label_fil.text())
         and bool(re.search(r"href=['\"][0-5](:\w+)?['\"]", dlg.label_fil.text())),
         dlg.label_fil.text().replace("<b>", "").replace("</b>", "")[:90])
BoiteMessage.informations.clear()
BoiteMessage.dernier = None
dlg._diagnostic()
# LA BRANCHE « PAS D'INTERPRETEUR » NE SE PARCOURT QUE LA OU IL MANQUE, et
# c'est justement la qu'elle doit tenir : sur un poste neuf. Elle propose
# trois issues, et « Installer… » est celle qui doit etre mise en avant —
# designer suppose de savoir ou chercher, installer non.
if noyau.interpreteur_hecras() is None:
    _boite = BoiteMessage.dernier
    _libelles = [b.text() for b in _boite.boutons] if _boite else []
    verifier("sans interpreteur, le diagnostic propose ses trois issues",
             len(_libelles) == 3 and _libelles[0].startswith("Installer"),
             f"{_libelles}")
    verifier("« Installer… » est le bouton mis en avant",
             _boite is not None and _boite.bouton_defaut is not None
             and _boite.bouton_defaut.text().startswith("Installer"),
             _boite.bouton_defaut.text() if _boite and _boite.bouton_defaut
             else "aucun")
    verifier("la boite dit POURQUOI un second Python",
             _boite is not None and "h5py" in _boite.informatif,
             _boite.informatif[:70] if _boite else "")
else:
    print("   ignore : un interpreteur est designe, la branche « poste neuf »"
          " du diagnostic n'est pas parcourue")
# LE DIAGNOSTIC NE S'ANNONCE PLUS PAR UNE BOITE (0.8.2) : il ecrit dans
# l'onglet — c'est la qu'on revient le lire — et le bandeau de messages dit
# en une ligne s'il est bon. Une boite modale pour un compte rendu qu'on ne
# peut ni copier ni relire etait exactement ce que le Cookbook PyQGIS
# deconseille.
verifier("diagnostic annonce dans le bandeau, sans boite d'information",
         not BoiteMessage.informations
         and dlg.barre_messages.currentItem() is not None,
         f"boites={len(BoiteMessage.informations)} ; bandeau="
         + (dlg.barre_messages.currentItem().text()[:60]
            if dlg.barre_messages.currentItem() else "vide"))
verifier("diagnostic repris dans l'onglet", bool(dlg.label_diagnostic.text()),
         dlg.label_diagnostic.text().replace("\n", " | ")[:70])

# ---------------------------------------------------------------------------
print("\n7. PARCOURS CLAVIER ET PETITE FENETRE")
from unittest.mock import patch as _patch                   # noqa: E402
from qgis.PyQt.QtCore import QPoint, QRect                  # noqa: E402
from qgis.PyQt.QtTest import QTest                          # noqa: E402
from qgis.PyQt.QtWidgets import (                           # noqa: E402
    QAbstractSpinBox, QComboBox, QLineEdit, QScrollArea, QTextBrowser)


def _rectangle_dans(widget, parent):
    return QRect(widget.mapTo(parent, QPoint(0, 0)), widget.size())


_hauteurs_peintes = {}


def _eprouver_petite_fenetre(points):
    """Vrais clics/touches et geometrie Qt, sans modele ni effet d'ecriture.

    Les minima viennent des widgets Qt sous la police demandee, jamais de
    pixels devines pour une capture. Une page plus haute doit defiler ; les
    champs ne doivent pas etre aplatis pour tenir dans la fenetre.
    """
    police_avant = QFont(QApplication.font())
    police = QFont(police_avant)
    police.setPointSizeF(points)
    effets, clics = [], []
    fenetre = None
    # Neutraliser AVANT construction : les signaux clicked retiennent leur
    # callable d'origine. Une regression Entrée doit echouer au banc sans
    # jamais ecrire dans une geometrie ni lancer un solveur.
    with _patch.object(mod_plugin.DialogueParametrage, "_composer_et_controler",
                       lambda *_a: effets.append("composer")), \
         _patch.object(mod_plugin.DialogueParametrage, "_lancer_calage",
                       lambda *_a: effets.append("lancer")):
        try:
            QApplication.setFont(police)
            fenetre = mod_plugin.DialogueParametrage(iface)
            fenetre.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            fenetre.setFont(police)
            fenetre.resize(800, 620)
            fenetre.show()
            QApplication.processEvents()
            verifier(f"police {points} pt : la fenetre tient dans 800 x 620",
                     fenetre.width() <= 800 and fenetre.height() <= 620,
                     f"{fenetre.width()} x {fenetre.height()}")
            verifier(f"police {points} pt : les saisies suivent la police demandee",
                     fenetre.edit_projet_hecras.font().pointSizeF() >= points,
                     str(fenetre.edit_projet_hecras.font().pointSizeF()))
            # LES WIDGETS PEINTS AUSSI (0.8.5, C4). Ils ecrivaient 7,5, 8 et
            # 11 pt en dur ; ils dessinent desormais en fraction de leur
            # police, que la feuille de style pose sur tout QWidget — avec
            # son plancher de 10 pt, d'ou le min().
            _peints = (fenetre.ruban_apports, fenetre.jauges["volume_pct"],
                       fenetre.courbe_suivi)
            verifier(f"police {points} pt : les widgets peints suivent la police",
                     all(w.font().pointSizeF() >= min(points, 10.0) for w in _peints),
                     str([w.font().pointSizeF() for w in _peints]))
            _hauteurs_peintes[points] = [w.minimumHeight() for w in _peints]
            # LA BARRE DE PREPARATION LOGE SON TEXTE A TOUTE POLICE (23/10/2026) :
            # plafonnee a 170 px et dimensionnee sans son texte, elle lisait
            # « réparation 1/ » a 13 pt.
            _prep = fenetre.barre_preparation
            verifier(f"police {points} pt : la barre de preparation loge son texte",
                     _prep.width() >= _prep.fontMetrics().horizontalAdvance(_prep.text()),
                     f"{_prep.width()} px pour « {_prep.text()} » "
                     f"({_prep.fontMetrics().horizontalAdvance(_prep.text())} px)")
            verifier(f"police {points} pt : Qt utilise la famille demandee",
                     QFontInfo(fenetre.edit_projet_hecras.font()).family()
                     == police.family(),
                     f"demandee={police.family()}, "
                     f"resolue={QFontInfo(fenetre.edit_projet_hecras.font()).family()}")
            attendus = ("1. Modèle", "2. Paramètres", "3. Lancer",
                        "4. Suivi", "Aide et configuration")
            verifier(f"police {points} pt : les cinq etapes sont identifiables",
                     tuple(fenetre.onglets.tabText(i)
                           for i in range(fenetre.onglets.count())) == attendus)
            boutons = fenetre.findChildren(QPushButton)
            for bouton in boutons:
                bouton.clicked.connect(
                    lambda _c=False, b=bouton: clics.append(b.text()))

            bande = fenetre.bande
            for index, titre in enumerate(attendus):
                repere = f"{points} pt / {titre}"
                bande.scrollToItem(bande.item(index))
                rectangle = bande.visualItemRect(bande.item(index))
                verifier(f"{repere} : entree de la bande entierement accessible au clic",
                         bande.viewport().rect().contains(rectangle),
                         f"entree={rectangle.getRect()}, "
                         f"bande={bande.viewport().rect().getRect()}")
                QTest.mouseClick(bande.viewport(), Qt.MouseButton.LeftButton,
                                 pos=rectangle.center())
                QApplication.processEvents()
                verifier(f"{repere} : le clic ouvre la bonne page",
                         fenetre.onglets.currentIndex() == index)
                # LE CHEMIN SUR SA LIGNE, LES BOUTONS DESSOUS (23/10/2026). Cote
                # a cote, un chemin sans espace imposait sa largeur a la ligne :
                # a 13 pt sur 720 px, la page defilait de 43 px et rognait
                # « Choisir le dossier… ».
                if index == mod_plugin.ONGLET_AIDE:
                    def _bas(w):
                        return w.mapTo(fenetre, w.rect().bottomLeft()).y()

                    def _haut(w):
                        return w.mapTo(fenetre, w.rect().topLeft()).y()

                    _installer, _interp, _chaine = fenetre._commandes_poste[:3]
                    verifier(f"{repere} : chaque chemin du poste a sa ligne, "
                             "ses boutons dessous",
                             _bas(fenetre.label_chaine) < _haut(_chaine)
                             and _bas(fenetre.label_interpreteur)
                             < min(_haut(_installer), _haut(_interp)),
                             f"chaine {_bas(fenetre.label_chaine)} / bouton "
                             f"{_haut(_chaine)} ; interpreteur "
                             f"{_bas(fenetre.label_interpreteur)} / boutons "
                             f"{_haut(_installer)}, {_haut(_interp)}")
                # LE BOUTON N'EST PLUS PERMANENT (21/09/2026) : il vit a
                # l'onglet 1, avec les couches qu'il ecrit. Ce qui reste au
                # bas de la fenetre, et doit y etre visible depuis chaque
                # onglet, c'est la barre de preparation.
                barre_prep = fenetre.barre_preparation
                verifier(f"{repere} : la preparation se lit depuis cet onglet",
                         barre_prep.isVisibleTo(fenetre)
                         and fenetre.rect().contains(
                             _rectangle_dans(barre_prep, fenetre)))

                zone = fenetre.onglets.widget(index)
                verifier(f"{repere} : le contenu dispose d'un defilement",
                         isinstance(zone, QScrollArea))
                if not isinstance(zone, QScrollArea):
                    continue
                page = zone.widget()
                champs = [w for w in page.findChildren(QWidget)
                          if isinstance(w, (QLineEdit, QComboBox, QAbstractSpinBox))
                          and w.isVisibleTo(page)
                          and not (isinstance(w, QLineEdit)
                                   and isinstance(w.parentWidget(),
                                                  (QComboBox, QAbstractSpinBox)))]
                comprimes = [(w.objectName() or type(w).__name__, w.height(),
                              w.minimumSizeHint().height()) for w in champs
                             if w.height() < w.minimumSizeHint().height()]
                verifier(f"{repere} : les champs gardent leur hauteur minimale",
                         not comprimes, str(comprimes))
                requis = page.minimumSizeHint().height()
                verifier(f"{repere} : un contenu trop haut peut defiler",
                         requis <= zone.viewport().height()
                         or zone.verticalScrollBar().maximum() > 0,
                         f"minimum={requis}, vue={zone.viewport().height()}, "
                         f"defilement={zone.verticalScrollBar().maximum()}")
                if champs:
                    dernier = max(champs,
                                  key=lambda w: _rectangle_dans(w, page).bottom())
                    zone.ensureWidgetVisible(dernier)
                    QApplication.processEvents()
                    _atteignable = zone.viewport().rect().contains(
                        _rectangle_dans(dernier, zone.viewport()))
                    _detail = (f"{dernier.objectName() or type(dernier).__name__} : "
                               f"{_rectangle_dans(dernier, zone.viewport()).getRect()}, "
                               f"vue={zone.viewport().rect().getRect()}")
                    if not _atteignable:
                        # LE COUPABLE D'UN DEBORDEMENT HORIZONTAL N'EST PAS LE
                        # DERNIER CHAMP : c'est le widget dont la largeur
                        # minimale depasse la vue. Le nommer evite de chercher
                        # a l'oeil (11/09/2026 : 37 px de trop a 13 pt, onglet 3).
                        _larges = sorted(
                            ((w.minimumSizeHint().width(),
                              w.objectName() or type(w).__name__,
                              (w.text()[:40] if callable(getattr(w, "text", None))
                               else ""))
                             for w in page.findChildren(QWidget)
                             if w.isVisibleTo(page)), reverse=True)[:5]
                        _detail += f" ; plus larges (largeur minimale) : {_larges}"
                    verifier(f"{repere} : le dernier champ est atteignable",
                             _atteignable, _detail)

                # Saisies et boutons sensibles : ni Entrée standard ni celle
                # du pave numerique ne doit declencher le controle/lancement.
                cibles = [w for w in champs if w.isEnabled()]
                cibles += [b for b in boutons if b.isVisibleTo(fenetre)
                           and b.isEnabled()
                           and (b is bouton or "Lancer le calage" in b.text())]
                for cible in cibles:
                    cible.setFocus()
                    for touche in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                        QTest.keyClick(cible, touche)
                QApplication.processEvents()
                verifier(f"{repere} : Entree ne declenche aucune action",
                         not effets and not clics and fenetre.isVisible(),
                         f"effets={effets}, clics={clics}")
                effets.clear()
                clics.clear()

            # Les raccourcis doivent traverser les widgets qui consomment
            # eux-memes les fleches (boutons et navigateur HTML de l'aide).
            # Une fenetre hors ecran n'est pas active par defaut : poser et
            # verifier cette condition avant les vrais evenements clavier.
            QApplication.setActiveWindow(fenetre)
            QApplication.processEvents()
            verifier(f"police {points} pt : la fenetre est active pour les raccourcis",
                     QApplication.activeWindow() is fenetre)
            # LE BOUTON VIT A L'ETAPE PARAMETRES (22/09/2026) : on part de la.
            fenetre.onglets.setCurrentIndex(mod_plugin.ONGLET_OBJECTIFS)
            fenetre.bouton_controle.setFocus()
            QTest.keyClick(fenetre.bouton_controle, Qt.Key.Key_Right,
                           Qt.KeyboardModifier.AltModifier)
            QApplication.processEvents()
            verifier(f"police {points} pt : Alt-droite navigue depuis un bouton",
                     fenetre.onglets.currentIndex() == mod_plugin.ONGLET_LANCER)
            QTest.keyClick(fenetre.bouton_controle, Qt.Key.Key_Left,
                           Qt.KeyboardModifier.AltModifier)
            QApplication.processEvents()
            verifier(f"police {points} pt : Alt-gauche revient depuis un bouton",
                     fenetre.onglets.currentIndex() == mod_plugin.ONGLET_OBJECTIFS)
            # LE RANG NOMME, PAS LE NOMBRE. Ecrit « 5 », il a suivi l'aide
            # d'un onglet a l'autre jusqu'au jour ou « Sorties » est sorti.
            fenetre.onglets.setCurrentIndex(mod_plugin.ONGLET_AIDE)
            navigateur = fenetre.onglets.widget(
                mod_plugin.ONGLET_AIDE).findChild(QTextBrowser)
            navigateur.setFocus()
            QTest.keyClick(navigateur, Qt.Key.Key_Left,
                           Qt.KeyboardModifier.AltModifier)
            QApplication.processEvents()
            verifier(f"police {points} pt : Alt-gauche quitte le navigateur d'aide",
                     fenetre.onglets.currentIndex() == mod_plugin.ONGLET_SUIVI)
            fenetre.bouton_controle.setFocus()
            QTest.keyClick(fenetre.bouton_controle, Qt.Key.Key_Right,
                           Qt.KeyboardModifier.AltModifier)
            QApplication.processEvents()
            verifier(f"police {points} pt : Alt-droite revient a l'aide",
                     fenetre.onglets.currentIndex() == mod_plugin.ONGLET_AIDE)
            # LES « ! défaut : … » NE FONT DEFILER AUCUNE ETAPE DE COTE
            # (10/11/2026). Tous les reglages changes, groupes deplies : c'est
            # l'etat le plus large, que la fenetre a l'ouverture ne montre pas.
            fenetre.edit_sim_debut.setText("01JAN2000,00:00")
            fenetre.edit_sim_fin.setText("02JAN2000,00:00")
            for champ in fenetre.edits_intervalles.values():
                champ.setText("2MIN")
            fenetre.combo_sens_axe.setCurrentIndex(1)
            fenetre.spin_pk_origine.setValue(12.0)
            for spin in (fenetre.spin_tol_volume, fenetre.spin_tol_pic,
                         fenetre.spin_bilan_masse, fenetre.spin_nb_max_essais):
                spin.setValue(spin.value() + 1)
            fenetre.edit_sous_dossier_resultats.setText("r")
            fenetre.edit_sous_dossier_suivi.setText("s")
            fenetre.case_coeurs.setChecked(True)
            fenetre.case_elaguer.setChecked(True)
            # La case des cœurs ne change rien sur un poste sans suggestion :
            # sa marque n'est pas comptee.
            for index, attendues in ((mod_plugin.ONGLET_MODELE, 8),
                                     (mod_plugin.ONGLET_OBJECTIFS, 6),
                                     (mod_plugin.ONGLET_LANCER, 1)):
                fenetre.onglets.setCurrentIndex(index)
                QApplication.processEvents()
                zone = fenetre.onglets.widget(index)
                # Un groupe repliable ne se deplie qu'a l'ecran. SANS MEMOIRE :
                # QGIS retient l'etat d'un groupe nomme, et la fenetre
                # suivante — comme le banc suivant — s'ouvrirait depliee.
                for groupe in zone.findChildren(type(fenetre.groupe_fenetre)):
                    groupe.setSaveCollapsedState(False)
                    groupe.setCollapsed(False)
                QApplication.processEvents()
                marques = [m for _c, _w, m in fenetre._defauts
                           if zone.isAncestorOf(m) and m.isVisibleTo(zone)]
                verifier(f"{points} pt / {attendus[index]} : tous les « ! défaut » "
                         "allumes, la page ne defile pas de cote",
                         len(marques) >= attendues
                         and zone.horizontalScrollBar().maximum() == 0,
                         f"{len(marques)} marque(s) a l'ecran, defilement "
                         f"horizontal={zone.horizontalScrollBar().maximum()} px, "
                         f"page={zone.widget().minimumSizeHint().width()} px, "
                         f"vue={zone.viewport().width()} px")
        finally:
            if fenetre is not None:
                fenetre.close()
                fenetre.deleteLater()
            QApplication.setFont(police_avant)
            QApplication.processEvents()


for _points in (9, 13):
    _eprouver_petite_fenetre(_points)

verifier("les widgets peints grandissent avec la police (9 -> 13 pt)",
         len(_hauteurs_peintes.get(13, [])) == 3
         and all(h13 > h9 for h9, h13 in zip(_hauteurs_peintes.get(9, []),
                                             _hauteurs_peintes[13])),
         str(_hauteurs_peintes))

# ---------------------------------------------------------------------------
print("\n7 bis. CE QUE LA RELECTURE DU 17/09/2026 A CHANGE (0.8.5)")
# docs/ergonomie_2026-09-17.md. Tout ce qui suit se mesure SANS ecran : les
# couleurs se demandent aux widgets, jamais aux pixels.
from qgis.PyQt.QtCore import QEvent as _QEvent                 # noqa: E402
from qgis.PyQt.QtGui import QColor as _QColor       # noqa: E402
from qgis.PyQt.QtGui import QPalette as _QPalette              # noqa: E402
from calage_apports import interface as mod_interface          # noqa: E402


def _contraste(a, b):
    """Rapport de contraste WCAG 2 entre deux couleurs « #rrggbb »."""
    def luminance(couleur):
        canaux = [int(couleur.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lineaires = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
                     for c in canaux]
        return 0.2126 * lineaires[0] + 0.7152 * lineaires[1] + 0.0722 * lineaires[2]
    clair, fonce = sorted((luminance(a), luminance(b)), reverse=True)
    return (clair + 0.05) / (fonce + 0.05)


# --- LES COULEURS DE TEXTE TIENNENT 4,5:1 DANS LES DEUX THEMES (WCAG 1.4.3) --
# Les fonds sont ceux releves par la recette du 11/09 : « #f0f0f0 » pour le
# theme clair de QGIS, « #323232 » pour Night Mapping. C'est le calcul que
# Sensi a fait a la main le 11/09, versionne — le teal institutionnel
# « #3A8D94 » rend 3,4:1 et servait de couleur de texte a cinq endroits.
_FOND_CLAIR, _FOND_SOMBRE = "#f0f0f0", "#323232"
_sous_seuil = {statut: round(_contraste(c, _FOND_CLAIR), 2)
               for statut, c in mod_plugin.COULEUR_STATUT.items()
               if _contraste(c, _FOND_CLAIR) < 4.5}
verifier("theme clair : chaque couleur de statut tient 4,5:1 sur le fond",
         not _sous_seuil, str(_sous_seuil) or "toutes >= 4,5:1")
verifier("theme clair : « en cours » est le teal sombre, pas l'institutionnel",
         mod_plugin.COULEUR_STATUT["en cours"] == mod_plugin.ISL_TEAL_SOMBRE
         and _contraste(mod_plugin.ISL_TEAL_SOMBRE, _FOND_CLAIR) >= 4.5
         and _contraste(mod_plugin.ISL_TEAL, _FOND_CLAIR) < 4.5,
         f"sombre {_contraste(mod_plugin.ISL_TEAL_SOMBRE, _FOND_CLAIR):.2f}:1, "
         f"institutionnel {_contraste(mod_plugin.ISL_TEAL, _FOND_CLAIR):.2f}:1")
# SUR TOUS LES .py DU PLUGIN, et non plus sur plugin.py seul : la fenetre se
# repartit en modules (docs/decoupage_dialogue.md), et un texte en teal ecrit
# dans l'un d'eux echappait au controle sans le faire rougir.
_teal_ecrit = [_f.name for _f in sorted(Path(mod_plugin.__file__).parent.glob("*.py"))
               if re.search(r"color:\{ISL_TEAL\}", _f.read_text(encoding="utf-8"))]
verifier("theme clair : plus aucun texte ecrit en teal institutionnel dans le plugin",
         not _teal_ecrit, ", ".join(_teal_ecrit) or "aucun fichier")
_remappees = set(mod_interface.COULEURS_SOMBRES.values())
_sous_seuil = {c: round(_contraste(c, _FOND_SOMBRE), 2) for c in _remappees
               if _contraste(c, _FOND_SOMBRE) < 4.5}
verifier("theme sombre : chaque couleur remappee tient 4,5:1 sur le fond",
         not _sous_seuil, str(_sous_seuil) or "toutes >= 4,5:1")
verifier("theme sombre : le fond de la fenetre sert d'encre lisible sur chaque teinte remappee",
         all(_contraste(_FOND_SOMBRE, c) >= 4.5 for c in _remappees),
         str({c: round(_contraste(_FOND_SOMBRE, c), 2) for c in _remappees}))
# LE RUBAN ECRIT A L'ENCRE DU REGISTRE SUR UNE TEINTE CLAIRE (23/10/2026).
# Le blanc sur l'accent plein ne rendait que 3,9:1 ; la teinte est posee en
# transparence sur la carte blanche, on calcule donc le melange.
def _melange(teinte, alpha, fond="#ffffff"):
    return "#" + "".join(
        f"{round(int(fond[i:i + 2], 16) * (1 - alpha / 255) + int(teinte[i:i + 2], 16) * alpha / 255):02x}"
        for i in (1, 3, 5))


_segments = {statut: _melange(teinte, mod_plugin.OPACITE_SEGMENT.get(
                 statut, mod_plugin.OPACITE_SEGMENT_DEFAUT))
             for statut, teinte in mod_plugin.TEINTE_STATUT.items()
             if statut != "en attente"}
verifier("ruban : l'encre tient 4,5:1 sur chaque segment teinte",
         all(_contraste(mod_plugin.registre.ENCRE, c) >= 4.5
             for c in _segments.values())
         and _contraste(mod_plugin.registre.TEXTE_SECONDAIRE,
                        mod_plugin.registre.FOND) >= 4.5,
         str({statut: round(_contraste(mod_plugin.registre.ENCRE, c), 2)
              for statut, c in _segments.items()}))

# --- LES WIDGETS PEINTS GARDENT LEUR CARTE CLAIRE DANS LES DEUX THEMES -------
# Ils remappaient leurs teintes sous Night Mapping (0.8.5, C1) ; depuis le
# 23/10/2026 ils se dessinent sur la carte blanche du registre commun, comme
# les graphiques de Rhoe et de Hyetos. On le lit sur l'image rendue : un
# pixel de la carte, pres du bord gauche, a mi-hauteur.
_nuit = _QPalette()
_nuit.setColor(_QPalette.ColorRole.Window, _QColor(_FOND_SOMBRE))
_nuit.setColor(_QPalette.ColorRole.WindowText, _QColor("#e0e0e0"))
_nuit.setColor(_QPalette.ColorRole.Base, _QColor("#232323"))
_peints = {"ruban": dlg.ruban_apports, "jauge": dlg.jauges["volume_pct"],
           "courbe": dlg.courbe_suivi}


def _fond_carte(widget):
    widget.resize(max(widget.width(), 300), max(widget.height(),
                                                widget.minimumHeight()))
    image = widget.grab().toImage()
    return image.pixelColor(4, image.height() // 2).name().lower()


for _theme, _palette in (("sombre", _nuit), ("clair", _QPalette())):
    for _w in _peints.values():
        _w.setPalette(_palette)
    verifier(f"theme {_theme} : ruban, jauge et courbe gardent la carte blanche du registre",
             all(_fond_carte(_w) == mod_plugin.registre.FOND
                 for _w in _peints.values()),
             str({n: _fond_carte(_w) for n, _w in _peints.items()}))
for _w in _peints.values():
    _w.setPalette(_QPalette())
dlg.table_suivi.setPalette(_nuit)
_ecrire_etat(total=1, en_cours=None,
             apports=[{"ordre": 1, "apport": "A1", "section": "SC1",
                       "statut": "échoué", "essais": 3, "volume_pct": 80.0,
                       "pic_pct": 70.0, "forme_pct": 90.0, "duree_s": 900,
                       "motif": "essai"}])
dlg._rafraichir_suivi()
verifier("theme sombre : la colonne Statut du tableau est remappee",
         dlg.table_suivi.rowCount() >= 1
         and dlg.table_suivi.item(0, 2).foreground().color().name().lower()
         == "#f29d97",
         dlg.table_suivi.item(0, 2).foreground().color().name()
         if dlg.table_suivi.rowCount() else "tableau vide")
dlg.table_suivi.setPalette(_QPalette())
dlg.label_suivi_banniere.setPalette(_nuit)
dlg._banniere(mod_plugin.ISL_ROUGE, "essai de filet")
verifier("theme sombre : le filet de la banniere suit le titre",
         "#f29d97" in dlg.label_suivi_banniere.styleSheet().lower(),
         dlg.label_suivi_banniere.styleSheet()[:90])
dlg.label_suivi_banniere.setPalette(_QPalette())

# --- LES TROIS AUTRES QUESTIONS A DEUX ISSUES : DEFAUT SUR, VERBES (C3) -----
# La premiere — « calage en cours » — est eprouvee a la section du suivi, la
# ou l'etat vivant est pose. Le mannequin ne clique rien : « Installer »
# lancerait pip, « Prolonger » ecrirait dans un classeur.
BoiteMessage.dernier = None
dlg._installer_interpreteur()
_boite_pip = BoiteMessage.dernier
verifier("« Installer l'environnement » : « Plus tard » est le defaut, « Installer » le verbe",
         _boite_pip is not None and _boite_pip.bouton_defaut is not None
         and _boite_pip.bouton_defaut.text() == "Plus tard"
         and _boite_pip.bouton_defaut.role == _RolesBouton.RejectRole
         and _boite_pip.boutons[0].text() == "Installer",
         str([b.text() for b in _boite_pip.boutons]) if _boite_pip else "aucune boite")
BoiteMessage.dernier = None
dlg._proposer_prolongation({"duree_h": 48.0, "apports": ["A1", "A2"]})
_boite_zeros = BoiteMessage.dernier
verifier("« Hydrogrammes trop courts » : « Laisser tel quel » est le defaut",
         _boite_zeros is not None and _boite_zeros.bouton_defaut is not None
         and _boite_zeros.bouton_defaut.text() == "Laisser tel quel"
         and _boite_zeros.boutons[0].text() == "Prolonger par des zéros",
         str([b.text() for b in _boite_zeros.boutons]) if _boite_zeros else "aucune boite")
# La quatrieme ne se montre que sans chaine : on la lui fait croire, et l'on
# releve TOUTES les boites parcourues — sur un poste sans interpreteur, le
# diagnostic en montre une seconde apres celle-ci.
_vues = []
_exec_origine = BoiteMessage.exec
with _patch.object(BoiteMessage, "exec",
                   lambda self: (_vues.append(self), _exec_origine(self))), \
     _patch.object(mod_plugin.noyau, "trouver_chaine", lambda: None):
    dlg._diagnostic()
_boite_chaine = next((b for b in _vues
                      if b.boutons and b.boutons[0].text().startswith("Désigner")), None)
verifier("« Chaîne introuvable » : « Plus tard » est le defaut, « Désigner » le verbe",
         _boite_chaine is not None and _boite_chaine.bouton_defaut is not None
         and _boite_chaine.bouton_defaut.text() == "Plus tard",
         str([[b.text() for b in v.boutons] for v in _vues]))
dlg._diagnostic()          # le diagnostic reel reprend sa place dans l'onglet
# Sur tous les .py du plugin, pour la meme raison que le teal ci-dessus.
_questions = [_f.name for _f in sorted(Path(mod_plugin.__file__).parent.glob("*.py"))
              if re.search(r"^\s*\w[^#\n]*QMessageBox\.question\(",
                           _f.read_text(encoding="utf-8"), re.MULTILINE)]
verifier("plus aucun QMessageBox.question dans le plugin",
         not _questions, ", ".join(_questions) or "aucun fichier")

# --- LES LIENS DU FIL CONDUCTEUR REPONDENT AU CLAVIER (C5) --------------------
_flags = dlg.label_fil.textInteractionFlags()
verifier("fil conducteur : les liens sont accessibles au clavier",
         bool(_flags & Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
         and dlg.label_fil.focusPolicy() != Qt.FocusPolicy.NoFocus,
         f"flags={_flags} focus={dlg.label_fil.focusPolicy()}")
_cible = re.search(r"href=['\"](\d)(?::\w+)?['\"]", dlg.label_fil.text())
if _cible is None:
    print("   ignore : le fil ne porte aucun lien dans cet etat")
else:
    _voulu = int(_cible.group(1))
    dlg.onglets.setCurrentIndex(mod_plugin.ONGLET_AIDE if _voulu != mod_plugin.ONGLET_AIDE
                                else mod_plugin.ONGLET_MODELE)
    dlg.show()
    dlg.activateWindow()
    QApplication.setActiveWindow(dlg)
    QApplication.processEvents()
    # Qt distingue le focus du QLabel et celui de son lien interne. Le premier
    # doit exister dans une fenêtre active avant Tab puis Entrée.
    dlg.bouton_controle.setFocus()
    dlg.label_fil.setFocus()
    QApplication.processEvents()
    QTest.keyClick(dlg.label_fil, Qt.Key.Key_Tab)
    verifier("fil conducteur : Tab sélectionne le texte du lien",
             bool(dlg.label_fil.selectedText()), dlg.label_fil.selectedText())
    QTest.keyClick(dlg.label_fil, Qt.Key.Key_Return)
    QApplication.processEvents()
    verifier("fil conducteur : Tab puis Entree ouvrent l'etape du lien",
             dlg.onglets.currentIndex() == _voulu,
             f"onglet {dlg.onglets.currentIndex()}, attendu {_voulu}")

# --- LEXIQUE : LES TERMES RENVOIENT A L'AIDE (27/10/2026) ---------------------
from qgis.PyQt.QtCore import QUrl as _QUrlLx  # noqa: E402
from qgis.PyQt.QtGui import QPalette as _QPaletteLx  # noqa: E402
from qgis.PyQt.QtWidgets import QLabel as _QLabelLx, QToolTip as _QToolTipLx  # noqa: E402
dlg.show()
QApplication.processEvents()
_lx = next((e for e in dlg.findChildren(mod_plugin.EtiquetteLexique)
            if "Δt de propagation" in e.text()), None)
verifier("lexique : text() rend le texte donne, sans les liens",
         _lx is not None and "<a" not in _lx.text(), _lx.text() if _lx else "absent")
if _lx is not None:
    _affiche = _QLabelLx.text(_lx)
    _couleur_lx = _lx.palette().color(_QPaletteLx.ColorRole.WindowText).name()
    verifier("lexique : les termes d'un texte d'aide sont des liens discrets, "
             "a la couleur grise du texte d'aide",
             'href="terme:section_controle"' in _affiche and 'href="terme:dt"' in _affiche
             and f"color: {_couleur_lx}; text-decoration: none" in _affiche
             and _couleur_lx == "#526b7a",
             f"{_couleur_lx} | {_affiche[:140]}")
    verifier("lexique : le survol d'un texte d'aide montre les definitions",
             _lx.toolTip().startswith("Section de contrôle :")
             and "Δt, décalage de propagation :" in _lx.toolTip(),
             _lx.toolTip()[:80])
    dlg.onglets.setCurrentIndex(mod_plugin.ONGLET_MODELE)
    QApplication.processEvents()
    _lx.linkActivated.emit("terme:dt")
    QApplication.processEvents()
    _defile = dlg.navigateur_aide.verticalScrollBar().value()
    dlg.navigateur_aide.scrollToAnchor("terme_dt")
    QApplication.processEvents()
    verifier("lexique : un clic sur un terme ouvre l'aide a son entree",
             dlg.onglets.currentIndex() == mod_plugin.ONGLET_AIDE and _defile > 0
             and _defile == dlg.navigateur_aide.verticalScrollBar().value(),
             f"onglet {dlg.onglets.currentIndex()}, defilement {_defile} / "
             f"{dlg.navigateur_aide.verticalScrollBar().value()}")
verifier("lexique : chaque renvoi de l'aide tombe sur une entree",
         set(re.findall(r'href="#(terme_\w+)"', mod_plugin.AIDE_HTML))
         <= set(re.findall(r'name="(terme_\w+)"', mod_plugin.AIDE_HTML))
         and len(re.findall(r'name="terme_\w+"', mod_plugin.AIDE_HTML))
         == len(mod_plugin.lexique.TERMES))
verifier("lexique : les sources de l'aide s'ouvrent dans le navigateur",
         dlg.navigateur_aide.openExternalLinks())
dlg._survol_aide(_QUrlLx("#terme_pk"))
verifier("lexique : le survol d'un terme de l'aide montre sa definition",
         _QToolTipLx.text().startswith("PK : point kilométrique"), _QToolTipLx.text()[:60])
_QToolTipLx.hideText()
_etat_lx = mod_plugin.texte_etat("PK\nligne 2")
_format_lx = _etat_lx.textFormat()
_etat_lx.setText("ligne 1\nligne 2")
verifier("lexique : une ligne d'etat sans terme retrouve son format d'origine",
         _format_lx == Qt.TextFormat.RichText
         and _etat_lx.textFormat() == Qt.TextFormat.AutoText
         and _etat_lx.toolTip() == "",
         f"{_format_lx} -> {_etat_lx.textFormat()}")
_etat_lx.deleteLater()

# --- LES WIDGETS PEINTS ONT UN NOM ET UNE DESCRIPTION ACCESSIBLES (C6) --------
verifier("les widgets peints ont un nom accessible",
         all(w.accessibleName() for w in (dlg.ruban_apports, dlg.courbe_suivi,
                                          *dlg.jauges.values())),
         str([w.accessibleName() for w in (dlg.ruban_apports, dlg.courbe_suivi)]))
_ecrire_etat()          # l'etat synthetique a trois apports, A2 en cours chiffre
dlg._rafraichir_suivi()
verifier("la description accessible d'une jauge dit la valeur et le verdict",
         "%" in dlg.jauges["volume_pct"].accessibleDescription()
         and ("conforme" in dlg.jauges["volume_pct"].accessibleDescription()
              or "tolérance" in dlg.jauges["volume_pct"].accessibleDescription()),
         dlg.jauges["volume_pct"].accessibleDescription())
verifier("la description accessible du ruban compte les apports",
         "3 apport" in dlg.ruban_apports.accessibleDescription(),
         dlg.ruban_apports.accessibleDescription())
_ecrire_etat(termine=True)      # ne pas laisser un calage « vivant » derriere
dlg._rafraichir_suivi()

# ---------------------------------------------------------------------------
print("\n8. DECHARGEMENT")
# LE BOUTON EST DANS LA BARRE « CPN », commune aux extensions de la maison
# (23/10/2026) : cpn.ajouter() l'y pose des que l'interface sait creer une
# barre, ce que fait le mannequin.
from qgis.PyQt.QtWidgets import QToolBar as _QToolBar          # noqa: E402
_barre_avant = iface.mainWindow().findChild(_QToolBar, "CPN")
verifier("initGui pose le bouton dans la barre « CPN »",
         _barre_avant is not None and p.actions[0] in _barre_avant.actions(),
         f"barre={_barre_avant}")
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
verifier("unload retire la barre « CPN », dont il etait le seul bouton",
         iface.mainWindow().findChild(_QToolBar, "CPN") is None)
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

# Les widgets QGIS retiennent des couches et leurs providers. En mode Windows
# natif, solder aussi les deleteLater avant de decharger ces providers ; le
# bilan vert ne suffit pas si le processus plante ensuite pendant sa cloture.
from qgis.PyQt.QtCore import QCoreApplication, QEvent         # noqa: E402
for _fenetre_test in QApplication.topLevelWidgets():
    _fenetre_test.close()
    _fenetre_test.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
QApplication.processEvents()
QgsProject.instance().clear()
qgs.exitQgis()
sys.exit(1 if echecs else 0)
