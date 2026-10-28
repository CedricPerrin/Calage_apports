# -*- coding: utf-8 -*-
"""
Refait les captures d'ecran du plugin, dans docs/captures/.

POURQUOI UN SCRIPT ET PAS UNE COPIE D'ECRAN. Les six images du README ont ete
prises a la main le 6 septembre 2026. Deux jours plus tard, l'onglet 1 avait
change de forme et l'aide de contenu : les images mentaient, et personne ne
l'aurait vu — une capture perimee ressemble a une capture. Refaire six copies
d'ecran a chaque version d'interface ne tiendrait pas ; un script, si.

CE QU'IL MONTRE EST UN ETAT DE DEMONSTRATION, PAS UN CALAGE. Les valeurs de
l'onglet 1 — un projet, un plan, une fenetre de simulation — sont ecrites
directement dans les widgets, comme elles l'etaient dans les captures a la
main : tous les postes n'ont pas un modele HEC-RAS sous la main, et une
capture d'onglet vide n'apprend rien. AUCUN RESULTAT DE CALAGE N'EST
FABRIQUE : les onglets qui en presentent — 4 et 5 — se capturent tels qu'ils
s'ouvrent, et disent eux-memes qu'il n'y a rien a montrer.

DEUX PIEGES, MESURES SUR CE POSTE, POUR QUI VOUDRAIT L'AMELIORER :

  - PAS DE PLATEFORME « offscreen ». Elle semble le choix evident pour un
    script, mais Qt n'y trouve aucune police systeme : tout retombe sur une
    fonte de secours dont les metriques sont pres du DOUBLE. La barre
    d'onglets reclamait 1212 px au lieu de 662, la fenetre s'ouvrait a 1236
    de large au lieu de 880, et l'image ne ressemblait a rien de ce que
    l'utilisateur voit. QT_FONT_DPI et QT_SCALE_FACTOR n'y changent rien.
    Avec la plateforme reelle et WA_DontShowOnScreen, les dispositions sont
    activees normalement mais rien n'apparait a l'ecran.

  - LA POLICE DOIT ETRE POSEE A LA MAIN. Un QgsApplication construit ici
    n'herite pas de la police d'interface de QGIS : il demarre en Helvetica
    12 pt. Il faut lui donner celle du poste, en points, avec un DPI fixe
    pour que les textes du formulaire et de la feuille de style s'accordent.

A LANCER AVEC LE PYTHON DE QGIS, comme test_plugin_qgis.py :

    "C:\\Program Files\\QGIS\\LTR\\bin\\python-qgis-ltr.bat" captures_plugin.py

    --onglets 1,6     ne refait que ces onglets (defaut : tous)
    --echelle 1.5     finesse du rendu ; 1,5 rend 1320 px de large
"""
import argparse
import os
import sys
from pathlib import Path

# LE DPI DES POLICES EST FIGE A 96, ET C'EST INDISPENSABLE. Sans cela le
# processus herite du facteur d'agrandissement de l'ecran du poste — 150 %
# ici — qui s'applique aux corps exprimes en POINTS (la feuille de style du
# plugin) mais pas a la largeur de la fenetre, exprimee en pixels : les
# textes d'aide sortaient une fois et demie trop gros dans une fenetre restee
# a sa taille. A 96, un corps de 9 pt vaut 12 px, comme sur l'ecran de
# reference des captures d'origine.
os.environ["QT_FONT_DPI"] = "96"
if sys.platform == "win32":
    os.environ["QT_QPA_PLATFORM"] = "windows"

from qgis.core import QgsApplication, QgsProject                # noqa: E402

_analyseur = argparse.ArgumentParser(add_help=True)
_analyseur.add_argument("--onglets", default="tous",
                        help="numeros separes par des virgules ; 6 = aide")
_analyseur.add_argument("--echelle", type=float, default=1.8)
_analyseur.add_argument("--sortie", default=None)
_args = _analyseur.parse_args()
if not 0 < _args.echelle <= 4:
    _analyseur.error("--echelle doit etre comprise entre 0 (exclu) et 4")


def _prefixe_qgis():
    """Le prefixe de l'installation qui EXECUTE ce script — meme regle que
    test_plugin_qgis.py, pour la meme raison : ne pas supposer le poste."""
    import os
    declare = os.environ.get("QGIS_PREFIX_PATH")
    if declare and Path(declare).is_dir():
        return declare
    apps = Path(sys.prefix).parent
    for nom in ("qgis-ltr", "qgis"):
        if (apps / nom).is_dir():
            return str(apps / nom)
    return r"C:\Program Files\QGIS\LTR\apps\qgis-ltr"


QgsApplication.setPrefixPath(_prefixe_qgis(), True)

CHAINE = Path(__file__).resolve().parent
RACINE = CHAINE.parent
SORTIE = Path(_args.sortie) if _args.sortie else RACINE / "docs" / "captures"

print("Initialisation QGIS pour les captures de demonstration…", flush=True)
# Meme initialisation sans session QGIS que le banc d'interface : les vrais
# widgets Qt restent disponibles, sans ouvrir une fenetre QGIS complete.
qgs = QgsApplication([], False)
qgs.initQgis()

from qgis.PyQt.QtCore import QCoreApplication, QEvent, Qt        # noqa: E402
from qgis.PyQt.QtGui import QFont, QFontDatabase, QFontInfo, QPixmap  # noqa: E402
from qgis.PyQt.QtWidgets import (QApplication, QMainWindow,      # noqa: E402
                                 QGroupBox, QToolBar)

# La police d'interface du poste — voir l'entete.
try:
    _familles = QFontDatabase.families()          # Qt 6 : méthode statique
except TypeError:
    _familles = QFontDatabase().families()        # Qt 5
_police = next((f for f in ("Segoe UI", "Noto Sans", "DejaVu Sans", "Arial")
                if f in _familles), QApplication.font().family())
# EN POINTS, PAS EN PIXELS : la feuille de style du plugin dimensionne ses
# textes secondaires en points. Les deux doivent parler la meme langue, sinon
# l'un suit le DPI et l'autre non.
QApplication.setFont(QFont(_police, 9))
print(f"Plateforme Qt : {qgs.platformName()} ; police demandee : {_police} ; "
      f"police resolue : {QFontInfo(qgs.font()).family()}", flush=True)

# Le plugin s'importe comme un PAQUET, exactement comme le fait QGIS.
import importlib.util                                            # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "calage_apports", RACINE / "calage_apports" / "__init__.py",
    submodule_search_locations=[str(RACINE / "calage_apports")])
_paquet = importlib.util.module_from_spec(_spec)
sys.modules["calage_apports"] = _paquet
_spec.loader.exec_module(_paquet)

from calage_apports import plugin as mod_plugin                  # noqa: E402


class Iface:
    """Le strict minimum dont la fenetre a besoin pour se construire."""

    def __init__(self):
        self._fenetre = None

    def mainWindow(self):  # noqa: N802
        if self._fenetre is None:
            self._fenetre = QMainWindow()
        return self._fenetre

    def addToolBar(self, nom):  # noqa: N802
        return QToolBar(nom, self.mainWindow())

    def addPluginToVectorMenu(self, menu, action):  # noqa: N802
        pass


# --------------------------------------------------------------------------
# L'etat de demonstration de l'onglet 1
# --------------------------------------------------------------------------
# Les memes valeurs que les captures a la main : le modele d'essai PUBLIC de
# HEC-RAS (Muncie), et un chemin de projet qui ne designe le poste ni
# l'affaire de personne.
DEMONSTRATION = {
    "projet": r"D:\Etudes\Riviere\Modele2D\Riviere.prj",
    "detecte": "Muncie — HEC-RAS 7.0.1 (fichiers écrits avec 5.00, 5.10, 7.01)",
    "plan": "p01 — Unsteady Multi  9-SA run",
    "geometrie": "g01 — Muncie Base Geometry - 9 SAs",
    "unsteady": "u01 — Flow Boundary Conditions",
    "debut": "02JAN1900,0000",
    "fin": "02JAN1900,2400",
    "intervalles": {"intervalle_calcul": "15SEC",
                    "intervalle_sortie": "5MIN",
                    "intervalle_instantane": "1HOUR",
                    "intervalle_mapping": "5MIN"},
    "dossier_sortie": r"D:\Etudes\Riviere\Calage",
    # LES DEUX EMPLACEMENTS DU POSTE SONT EUX AUSSI MIS EN SCENE. Tels
    # quels, ils affichent le chemin REEL de la machine qui fabrique la
    # capture — et le README part sur GitHub. On montre donc l'etat
    # NOMINAL : les deux trouves, ce que voit un poste bien installe.
    "chaine": "C:\\Users\\…\\QGIS3\\profiles\\default\\python"
              "\\plugins\\calage_apports\\chaine",
    "interpreteur": "C:\\Users\\…\\venv-hecras\\Scripts\\python.exe",
}


def peupler(dlg):
    """
    Ecrit l'etat de demonstration DANS LES WIDGETS, sans charger de projet :
    la capture doit pouvoir se refaire sur un poste qui n'a pas de modele.

    Rien ici ne conclut : _maj_resume() et _maj_fil() tirent ensuite leurs
    conclusions de ces valeurs, exactement comme en usage reel — c'est ainsi
    que le fil conducteur du bas coche ce qui est fait.
    """
    d = DEMONSTRATION
    dlg.edit_projet_hecras.setText(d["projet"])
    dlg.label_nom_projet.setText(d["detecte"])
    dlg.combo_plan.blockSignals(True)
    dlg.combo_plan.addItem(d["plan"], {"numero": "01", "titre": "Unsteady Multi  9-SA run",
                                      "geometrie": "01", "unsteady": "01",
                                      "fenetre": {"debut": d["debut"], "fin": d["fin"],
                                                  **d["intervalles"]}})
    dlg.combo_plan.blockSignals(False)
    dlg.combo_geometrie.addItem(d["geometrie"], {"numero": "01"})
    dlg.combo_unsteady.addItem(d["unsteady"], {"numero": "01"})
    dlg._maj_resume_fichiers()
    dlg.edit_sim_debut.setText(d["debut"])
    dlg.edit_sim_fin.setText(d["fin"])
    for cle, valeur in d["intervalles"].items():
        dlg.edits_intervalles[cle].setText(valeur)
    dlg.label_fenetre.setText("Identique au plan de référence.")
    dlg.edit_dossier_sortie.setText(d["dossier_sortie"])
    dlg.label_chaine.setText(d["chaine"])
    dlg.label_interpreteur.setText(d["interpreteur"])
    dlg._maj_resume()
    dlg._maj_fil()


def hauteur_utile(dlg, indice):
    """
    La hauteur qui montre l'onglet ENTIER, sans barre de defilement, sans vide
    en bas, et SANS RIEN DE COMPRIME.

    Trois mesures ont ete essayees, et les deux premieres mentaient :

      - le sizeHint() de la page rend pres du double du necessaire — un
        onglet suivi de 400 px de gris ;
      - le maximum de la barre de defilement rend TROP PEU. Il se calcule sur
        ce meme sizeHint d'une page dont les textes a la ligne sous-comptent
        leur hauteur : a cette taille, la zone defilante ne fait pas
        apparaitre de barre, elle COMPRIME le dernier encadre sous sa taille
        utile — le bouton « Ecrire, composer et controler » y sortait rogne
        de deux pixels, et c'est la fenetre elle-meme qui fait cela des
        qu'elle est trop courte.

    On deplie donc large (sizeHint), on lit ou finit REELLEMENT le dernier
    encadre, on resserre — puis ON VERIFIE qu'aucun encadre n'est passe sous
    sa taille utile. Si l'un l'est, on garde la version ample : du gris en bas
    vaut mieux qu'un bouton coupe.
    """
    zone = dlg.onglets.widget(indice)
    if not hasattr(zone, "verticalScrollBar"):
        return HAUTEUR_NORMALE
    contenu = zone.widget()
    dlg.resize(880, HAUTEUR_NORMALE)
    dlg.ensurePolished()
    qgs.processEvents()
    chrome = dlg.height() - zone.viewport().height()
    ample = max(HAUTEUR_NORMALE, contenu.sizeHint().height() + chrome)
    dlg.resize(880, ample)
    dlg.ensurePolished()
    qgs.processEvents()

    encadres = [e for e in contenu.findChildren(QGroupBox)
                if e.parent() is contenu]
    if not encadres:
        return ample
    resserre = max(HAUTEUR_NORMALE,
                  max(e.geometry().bottom() for e in encadres) + chrome + 12)
    if resserre >= ample:
        return ample
    dlg.resize(880, resserre)
    dlg.ensurePolished()
    qgs.processEvents()
    if any(e.height() < e.sizeHint().height() for e in encadres):
        return ample
    return resserre


# La hauteur d'ouverture de la fenetre, celle que fixe le plugin lui-meme.
HAUTEUR_NORMALE = 720

NOMS = {0: "onglet_1_modele", 1: "onglet_2_sorties", 2: "onglet_3_objectifs",
        3: "onglet_4_lancer", 4: "onglet_5_suivi", 5: "onglet_6_aide"}

demandes = (sorted(NOMS) if _args.onglets == "tous"
            else [int(n) - 1 for n in _args.onglets.split(",")])
if any(indice not in NOMS for indice in demandes):
    _analyseur.error("--onglets accepte uniquement les numeros 1 a 6")

iface = Iface()
print("Construction de la fenetre…", flush=True)
dlg = mod_plugin.DialogueParametrage(iface)
print("Preparation de l'etat de demonstration…", flush=True)
peupler(dlg)
# Activer les layouts comme dans QGIS, tout en gardant la fenetre hors de
# l'ecran. Un simple render() d'une fenetre jamais montree peut conserver
# les hauteurs de labels calculees avant le renvoi automatique a la ligne.
dlg.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
dlg.show()
qgs.processEvents()
SORTIE.mkdir(parents=True, exist_ok=True)

for indice in demandes:
    print(f"Rendu de l'onglet {indice + 1}…", flush=True)
    dlg.onglets.setCurrentIndex(indice)
    dlg.resize(880, hauteur_utile(dlg, indice))
    dlg.ensurePolished()
    qgs.processEvents()
    # RENDU A L'ECHELLE, PAS AGRANDISSEMENT D'UNE IMAGE : la fenetre est
    # PEINTE dans un pixmap qui se declare a 1,8 point par pixel. Le texte
    # est donc trace a sa taille finale, net ; un grab() suivi d'un scaled()
    # rendrait la meme image floue.
    pixmap = QPixmap(dlg.size() * _args.echelle)
    pixmap.setDevicePixelRatio(_args.echelle)
    pixmap.fill()
    dlg.render(pixmap)
    chemin = SORTIE / f"{NOMS[indice]}.png"
    if not pixmap.toImage().save(str(chemin), "PNG"):
        raise OSError(f"Impossible d'ecrire la capture : {chemin}")
    print(f"   {chemin.name:26} {pixmap.width()}x{pixmap.height()}", flush=True)

print(f"\n{len(demandes)} capture(s) dans {SORTIE}")
# Detruire les widgets avant leurs providers QGIS : un simple deleteLater()
# sans traiter DeferredDelete laissait des objets Qt vivants apres exitQgis.
for widget in QApplication.topLevelWidgets():
    widget.close()
    widget.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
QApplication.processEvents()
QgsProject.instance().clear()
qgs.exitQgis()
