# -*- coding: utf-8 -*-
"""
Noyau du plugin QGIS — logique pure, SANS aucune dependance a QGIS.

Ce fichier est volontairement importable en dehors de QGIS : c'est ce qui
permet de le tester en console, et surtout d'eviter que la logique de
controle existe en deux exemplaires. Le plugin (plugin.py) ne fait
qu'appeler ces fonctions et afficher leur resultat ; il ne decide de rien.

Toute la validation reste dans controle_donnees.py et geometrie.py, qui sont
partages avec la chaine de calcul. Une regle modifiee a un seul endroit
s'applique donc aux deux.

Usage hors QGIS :  python noyau.py
"""

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# --- raccordement a la chaine de calage -------------------------------------
#
# Le plugin s'installe de deux manieres, et le chemin de la chaine n'est pas
# le meme dans les deux cas :
#   - par lien symbolique depuis le dossier projet : src/, au cote du parent
#     du plugin, EST la chaine (depuis le 28/08/2026 — la chaine vivait
#     avant cela directement au parent, voir STATUT.txt) ;
#   - par archive ZIP : le plugin atterrit dans le profil QGIS, et son parent
#     est le dossier plugins/, qui ne contient rien.
# Le chemin est donc CHERCHE, et jamais suppose.
#
# CHAINE EMBARQUEE. L'archive livrée porte une copie complete de la chaine
# dans calage_apports/chaine/ : sur un poste neuf, l'extension suffit, il n'y
# a rien a installer a cote.
#
# L'ORDRE EST FIXE, ET NE COMPARE AUCUNE DATE. La regle precedente retenait
# la chaine LA PLUS RECENTE. Elle etait indeterministe des l'installation :
# zipfile.extractall — ce qu'emploie le gestionnaire d'extensions de QGIS — ne
# restitue PAS la date stockee dans l'archive, les fichiers extraits portent
# l'heure de l'installation. La copie embarquee se trouvait donc toujours plus
# recente que les sources vives d'un poste de developpement, et les masquait
# en silence : on corrigeait la chaine sans aucun effet. Mesure le 08/08/2026,
# archive du 07/08 19:56 extraite le 08/08 16:03 -> mtime 08/08 16:03.
#
# AUCUN EMPLACEMENT DE DEVELOPPEMENT N'EST ECRIT ICI. Cette archive part sur
# des dizaines de postes : un chemin d'auteur y designerait un dossier
# inexistant, ou — bien pire — un dossier homonyme portant une AUTRE version
# de la chaine, que le plugin executerait sans rien dire. Qui veut faire
# tourner une chaine externe la designe, par CALAGE_CHAINE ou depuis le
# plugin ; c'est explicite, donc verifiable.

import os

FICHIERS_CHAINE = ("criteres.py", "geometrie.py", "controle_donnees.py",
                   "livrables.py", "pont_hecras.py")
# CHAQUE SOUS-PROCESSUS OUVRIRAIT UNE CONSOLE, ET ELLE PASSE DEVANT QGIS.
#
# Le plugin en lance beaucoup : la sonde d'interpreteur, le lanceur « py »,
# JUSQU'A QUARANTE essais de python.exe quand « Installer… » cherche une base,
# pip pendant plusieurs minutes, et le pont a chaque operation sur le modele.
# Sans ce drapeau, chacun fait clignoter une fenetre noire au premier plan —
# et celle de pip reste ouverte tout du long, masquant la fenetre du plugin.
# pilote_hecras.py le posait deja sur ses deux appels ; nulle part ailleurs.
#
# IL EST INCOMPATIBLE AVEC DETACHED_PROCESS, et ce n'est pas un detail :
# Windows refuse la creation du processus (ERROR_INVALID_PARAMETER) si les
# deux sont combines. lancer_calage() emploie DETACHED_PROCESS, qui prive
# DEJA le calage de console — il ne doit donc PAS y ajouter celui-ci.
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)

VARIABLE_CHAINE = "CALAGE_CHAINE"
DOSSIER_EMBARQUE = Path(__file__).resolve().parent / "chaine"

_dossier_chaine = None
_interpreteur = None


def est_chaine(dossier):
    """Un dossier contient-il la chaine de calage ?"""
    try:
        dossier = Path(dossier)
    except TypeError:
        return False
    return dossier.is_dir() and all((dossier / f).exists() for f in FICHIERS_CHAINE)


def fraicheur(dossier):
    """
    Date du module le plus recent d'une chaine, 0.0 si elle est illisible.

    Tous les .py comptent, pas seulement FICHIERS_CHAINE : une chaine dont
    seul calage.py serait perime passerait sinon pour fraiche.
    """
    try:
        return max((f.stat().st_mtime for f in Path(dossier).glob("*.py")),
                   default=0.0)
    except (OSError, TypeError):
        return 0.0


def chaines_candidates():
    """
    Emplacements connus portant une chaine valide, DANS L'ORDRE DE PRIORITE.

    L'ordre est celui de trouver_chaine() : la copie embarquee d'abord, parce
    qu'elle est celle livree avec CE plugin et la seule dont on reponde ; le
    dossier src/ du parent du plugin ensuite, qui n'est la chaine que pour
    une installation par lien symbolique — et dans ce cas la copie embarquee
    n'existe pas sur le disque, faire_zip.py ne la materialisant que dans
    l'archive. Les deux ne sont donc jamais en concurrence reelle — et ne
    peuvent pas non plus designer le meme dossier, l'un etant SOUS le plugin
    et l'autre a cote. Le dedoublonnage qui figurait ici ne dedoublonnait
    donc rien.
    """
    dossier_projet = Path(__file__).resolve().parent.parent / "src"
    return [c for c in (DOSSIER_EMBARQUE, dossier_projet) if est_chaine(c)]


def trouver_chaine():
    """
    Localise la chaine de calage, ou None.

    ORDRE FIXE, AUCUNE COMPARAISON DE DATES : designation explicite
    (definir_chaine, puis CALAGE_CHAINE), puis la copie embarquee, puis le
    parent du plugin. Voir l'en-tete du module pour la raison — la regle « la
    plus recente gagne » se retournait contre le poste de developpement des
    l'installation de l'archive.

    Une chaine externe reste donc accessible, mais elle se DESIGNE : rien ne
    la retient plus par hasard.
    """
    for designe in (_dossier_chaine, os.environ.get(VARIABLE_CHAINE)):
        if designe and est_chaine(designe):
            return Path(designe)
    return next(iter(chaines_candidates()), None)


def chaine_embarquee(dossier=None):
    """La chaine retenue est-elle celle qu'embarque l'archive ?"""
    dossier = dossier if dossier is not None else trouver_chaine()
    try:
        return dossier is not None and Path(dossier) == DOSSIER_EMBARQUE
    except TypeError:
        return False


def definir_chaine(dossier):
    """
    Declare le dossier de la chaine a l'execution, lorsqu'il n'a pas ete
    trouve automatiquement. Retourne True si le dossier convient.
    """
    global _dossier_chaine

    if not est_chaine(dossier):
        return False
    _dossier_chaine = Path(dossier)
    _raccorder()
    return True


def _raccorder():
    """Place la chaine sur le chemin d'import, si elle a ete localisee."""
    dossier = trouver_chaine()
    if dossier is not None and str(dossier) not in sys.path:
        sys.path.insert(0, str(dossier))
    return dossier


# CE QUI COMPTE ICI EST L'EFFET DE BORD : _raccorder() place la chaine sur le
# chemin d'import des l'import du module, et c'est la seule raison de cette
# ligne. Son resultat etait garde sous le nom DOSSIER_CHAINE, trompeur a deux
# titres — rien dans le plugin ne le lisait, et la valeur devenait FAUSSE des
# le premier definir_chaine(), qui change la chaine retenue sans la mettre a
# jour. Qui veut la chaine courante appelle trouver_chaine().
_raccorder()

NOMS_FICHIERS = {
    "sections": "sections_controle.shp",
    "apports": "lignes_injection.shp",
    "axe": "axe_hydraulique.shp",
    "classeur": "donnees_calage.xlsx",
}


def nom_classeur(prefixe=""):
    """
    Nom du classeur de saisie pour un scenario : « donnees_calage_Q100.xlsx ».

    LE PREFIXE DE SCENARIO NOMME LE FICHIER (0.8.4, demande utilisateur).
    Tous les scenarios d'un meme dossier de sortie partageaient
    « donnees_calage.xlsx » : composer le Q10 ecrasait la feuille
    Correspondance du Q100, et la seule facon de garder les deux etait de
    tenir deux dossiers de sortie. Le prefixe etant deja obligatoire — il
    nomme les plans HEC-RAS —, le faire nommer aussi le fichier suffit : deux
    scenarios, deux classeurs, et composer l'un ne touche pas l'autre.

    PREFIXE VIDE = LE NOM D'AVANT, AU CARACTERE PRES. Les classeurs des
    calages anterieurs restent lisibles tels quels.

    CE QUI N'EST PAS UN CARACTERE DE NOM DE FICHIER DEVIENT « _ ». Le prefixe
    est libre a la saisie — « Q100 V2 », « Q100/bis » — et un nom de fichier
    ne l'est pas. On ne refuse pas, on remplace : le titre des plans, lui,
    garde le prefixe tel qu'il a ete tape.

    MEME REGLE QUE suivi.assainir_nom_fichier, copiee plutot qu'importee :
    suivi.py charge matplotlib a l'import, ce que le processus QGIS n'a pas a
    faire pour nommer un fichier. Si la regle change, elle change aux deux
    endroits.
    """
    # « Riviere - Q100 - » et « Riviere - Q100 » nomment les memes plans
    # (calage.titre_etape) : ils nomment le meme classeur.
    prefixe = str(prefixe or "").strip().strip("-_ ")
    if not prefixe:
        return NOMS_FICHIERS["classeur"]
    sur = "".join(c if (c.isalnum() or c in "-_") else "_" for c in prefixe)
    tige, point, extension = NOMS_FICHIERS["classeur"].rpartition(".")
    return f"{tige}_{sur}{point}{extension}"


def detacher():
    """
    Retire du chemin d'import TOUT dossier reconnu comme une chaine.

    Plus large que ce que _raccorder() y a mis, et deliberement : celui-ci
    n'insere que si le dossier n'y figure pas deja, si bien qu'on ne peut pas
    savoir apres coup lequel vient de nous. Consequence assumee : un dossier
    de chaine que l'utilisateur aurait mis dans son PYTHONPATH est retire
    aussi.

    A appeler au DECHARGEMENT du plugin. _raccorder() insere en tete de
    sys.path des l'import du module, et peut recommencer si la chaine change
    en cours de session : on retire donc TOUT dossier que est_chaine()
    reconnait, plutot que de parier sur un seul. Un dossier laisse la
    continuerait de fournir « import criteres » a tout le processus QGIS,
    plugin decharge ou non.
    """
    sys.path[:] = [p for p in sys.path if not est_chaine(p)]


def chaine_disponible():
    """
    Verifie que la chaine de calage est accessible depuis l'interpreteur
    courant. Retourne (disponible, [messages]).

    DISPONIBLE VEUT DIRE : les paquets tiers sont la ET les modules de la
    chaine s'importent. Le verdict ne portait auparavant que sur les paquets
    tiers : un criteres.py en erreur de syntaxe ajoutait bien son message a la
    liste, mais laissait le titre annoncer « Utilisable : oui » — dans le seul
    ecran dont le metier est de repondre a cette question.

    L'interpreteur HEC-RAS, lui, reste un AVERTISSEMENT et non un refus : sans
    lui on ne pilote pas le modele, mais on compose et l'on controle le paquet,
    ce qui est deja la moitie du travail.

    Le Python de QGIS embarque deja numpy, scipy, pandas, geopandas, shapely,
    openpyxl et matplotlib : la preparation des donnees et tous les controles
    geographiques s'executent donc directement dans QGIS, sans installation.

    HEC-RAS, lui, passe obligatoirement par un autre interpreteur (voir
    interpreteur_hecras).
    """
    messages, manquants = [], []
    for module in ("numpy", "scipy", "pandas", "geopandas", "shapely",
                   "openpyxl", "matplotlib"):
        try:
            __import__(module)
        except ImportError:
            manquants.append(module)
    if manquants:
        messages.append(f"paquets absents : {', '.join(manquants)}")

    chaine = _raccorder()
    if chaine is None:
        messages.append(
            f"chaine de calage INTROUVABLE. Elle doit contenir "
            f"{', '.join(FICHIERS_CHAINE)}. La declarer par la variable "
            f"{VARIABLE_CHAINE}, ou la designer depuis le plugin.")
        return False, messages
    # Plusieurs chaines coexistent souvent sur un poste et peuvent diverger :
    # savoir LAQUELLE tourne, et de quand elle date, est la premiere chose a
    # verifier devant un correctif qui semble sans effet.
    date = datetime.fromtimestamp(fraicheur(chaine)).strftime("%d/%m/%Y %H:%M")
    messages.append(
        f"chaine de calage : {chaine} — modifiee le {date}"
        + (" (embarquee dans le plugin)" if chaine_embarquee(chaine)
           else " (externe au plugin)"))

    illisibles = []
    for module in ("criteres", "geometrie", "controle_donnees", "livrables"):
        try:
            __import__(module)
        except Exception as e:
            illisibles.append(module)
            messages.append(f"{module}.py illisible : {e}")

    interpreteur = interpreteur_hecras()
    if interpreteur is None:
        messages.append("interpreteur HEC-RAS introuvable : les operations sur "
                        "le modele seront indisponibles")
    else:
        messages.append(f"interpreteur HEC-RAS : {interpreteur}")

    return not (manquants or illisibles), messages


# ---------------------------------------------------------------------------
# PONT VERS HEC-RAS
# ---------------------------------------------------------------------------
#
# Le Python de QGIS embarque sa propre bibliotheque HDF5. Des que qgis.core est
# charge, h5py ne peut plus s'initialiser, et ras-commander — qui en depend —
# devient inimportable :
#
#     ImportError: DLL load failed while importing _errors
#
# Ce n'est pas contournable par un ordre d'import, puisque dans un plugin QGIS
# est deja charge. Toute operation touchant a HEC-RAS s'execute donc dans un
# AUTRE interpreteur, appele en sous-processus via pont_hecras.py.

VARIABLE_INTERPRETEUR = "CALAGE_PYTHON"

# VERSION MINIMALE DE ras-commander, et non le seul import. Sur des dizaines
# de postes, chacun installe ce qu'il obtient le jour ou il le fait : la
# 0.98.2 borne mal les tableaux d'hydrogramme, un apport ecrit y serait
# tronque SANS message, et le calage corrigerait ensuite une forme qu'il a
# lui-meme mutilee. C'est exactement le genre de defaut qu'un controle
# portant sur l'import laisse passer.
RAS_COMMANDER_MINIMUM = (0, 99)

# CE QU'IL FAUT A L'INTERPRETEUR HEC-RAS, en (nom d'import, nom pip).
#
# UNE SEULE LISTE POUR INSTALLER ET POUR VERIFIER. Elles etaient implicitement
# deux — installer_interpreteur() posait ras-commander et h5py,
# verifier_interpreteur() n'exigeait que les memes deux — et le pont, lui,
# importe geometrie des la premiere composition, donc geopandas. Un
# environnement cree par le bouton etait donc ACCEPTE puis echouait sur
# « ModuleNotFoundError: No module named 'geopandas' » a la premiere
# operation reelle (releve le 31/08/2026, second poste). Deux listes qui
# doivent s'accorder finissent toujours par diverger : il n'y en a plus qu'une.
#
# rasterio N'Y EST PAS, et n'a plus de raison d'y etre : la lecture d'un profil
# en long sur RASTER etait son seul importateur, et elle a ete retiree le
# 31/08/2026 — jamais raccordee, elle rendait une colonne « z_terrain » que le
# seul consommateur du profil ne lit pas. Le profil vient du maillage.
PAQUETS_HECRAS = (
    ("ras_commander", f"ras-commander>={'.'.join(str(n) for n in RAS_COMMANDER_MINIMUM)}"),
    ("h5py", "h5py"),
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("scipy", "scipy"),
    ("geopandas", "geopandas"),
    ("shapely", "shapely"),
    ("pyproj", "pyproj"),
    ("matplotlib", "matplotlib"),
    ("openpyxl", "openpyxl"),
    # PYWIN32 N'EST PAS UN CONFORT. ras-commander installe pendant chaque
    # calcul un veilleur qui ferme les boites de dialogue de HEC-RAS ; sans
    # win32gui il previent qu'il ne fera rien, et une seule boite modale fige
    # alors le calcul INDEFINIMENT — un calage sans surveillance ne se
    # reveillerait jamais. Le manque ne se voit qu'en avertissement au milieu
    # du journal, la ou personne ne le lit (releve le 31/08/2026, second
    # poste). Windows seulement, voir _CODE_VERIF.
    ("win32gui", "pywin32"),
)


# CE QUI N'EST PAS DES NOTRES, ET QUE LA COMMANDE DOIT POSER QUAND MEME.
#
# xarray arrive par ras-commander, qui l'exige pour HdfResultsMesh sans que
# pip le pose : la contrainte « >=0.99 » etant satisfaite par une version deja
# installee, il ne re-resout pas ses dependances. Releve en production le
# 02/09/2026 — calage conforme apres 14 h, puis « profil en long : non
# calculable (No module named 'xarray') » — et de nouveau le 06/09 en montant
# l'environnement d'un poste neuf : les onze poses, puis « module(s)
# absent(s) : xarray ».
#
# IL RESTE HORS DE PAQUETS_HECRAS, ET C'EST VOULU. Cette liste-la sert a
# SONDER : le mecanisme qui compte est « la sonde nomme ce qui manque, quel
# que soit le nom, et l'installeur le pose ensuite » — c'est lui qui rattrape
# la dependance suivante, celle qu'on n'a pas encore rencontree. Deux bancs
# l'eprouvent en fabriquant un environnement ou xarray manque ; l'inscrire
# dans PAQUETS_HECRAS les rendait verts et vides, puisqu'ils peuplent
# l'environnement d'essai depuis cette meme liste.
# Ici, on ne sonde pas : on ECRIT une commande. Elle doit etre complete.
PAQUETS_INDIRECTS = (("xarray", "xarray"),)


def commande_pip_hecras(interpreteur=None):
    r"""
    La commande pip qui pose TOUT ce que le pont exige, en un seul texte.

    ELLE SE DEDUIT DE PAQUETS_HECRAS, ET NE SE RECOPIE NULLE PART. L'aide du
    plugin et son message « interpreteur introuvable » annonçaient
    « pip install "ras-commander>=0.99" h5py » — deux paquets, quand la
    verification en exige onze, plus xarray par ras-commander
    (PAQUETS_INDIRECTS). Qui suivait l'aide a la lettre
    fabriquait donc un environnement que le plugin REFUSAIT ensuite, et
    devait recommencer sur la foi du message d'echec. C'est exactement la
    divergence entre deux listes que PAQUETS_HECRAS existe pour empecher : la
    liste avait ete unifiee dans le code le 31/08/2026, pas dans les textes.

    interpreteur : le python.exe a employer. Sans lui, « python » — pour une
    invite ou l'environnement est deja actif.
    """
    paquets = " ".join(f'"{pip}"' if any(c in pip for c in "<>=") else pip
                       for _, pip in PAQUETS_HECRAS + PAQUETS_INDIRECTS)
    tete = f'"{interpreteur}"' if interpreteur else "python"
    return f"{tete} -m pip install {paquets}"


def recette_installation_manuelle():
    r"""
    Les deux commandes a taper pour se passer du bouton « Installer… ».

    Elle reste offerte parce qu'un poste d'entreprise interdit parfois a QGIS
    de sortir sur PyPI alors qu'une invite de commandes le peut. Elle n'est
    PAS le chemin recommande : le bouton fait la meme chose, verifie le
    resultat, et retient l'emplacement.
    """
    venv = r"%USERPROFILE%\venv-hecras"
    return (f"python -m venv {venv}",
            commande_pip_hecras(rf"{venv}\Scripts\python.exe"))


def message_interpreteur_introuvable():
    """
    Le message d'interpreteur manquant, EN UN SEUL EXEMPLAIRE.

    LE GESTE LE PLUS SIMPLE D'ABORD. Ce texte ne proposait que la variable
    d'environnement — c'est-a-dire quitter QGIS, ouvrir les parametres
    systeme et revenir — alors qu'un bouton fait le travail. C'est la
    premiere erreur qu'a vue l'utilisateur sur un poste neuf, et elle
    l'envoyait vers la seule issue penible (releve le 29/08/2026).

    IL EN EXISTAIT DEUX, ET UN SEUL AVAIT ETE CORRIGE. Le jumeau de
    lancer_calage — le seul appel qui n'emprunte pas appeler_pont — etait
    reste sur « Definir la variable d'environnement ». Le cas ou on le lit
    n'est pas le poste neuf, dont la premiere composition passe par
    appeler_pont : c'est l'environnement casse ENTRE DEUX SESSIONS, et
    l'utilisateur y recevait le mauvais conseil. Deux exemplaires d'un
    message se corrigent une fois sur deux.

    « Parametres du poste » EST UN GROUPE, PAS UN ONGLET : il vit dans
    l'onglet « Aide et configuration ». L'annoncer comme un onglet envoie
    chercher ce qui n'existe pas.
    """
    return (f"aucun interpréteur capable de piloter HEC-RAS n'a été trouvé. "
            f"Dans « Aide et configuration » du plugin, groupe "
            f"« Diagnostic et paramètres du poste » : bouton « Installer… » "
            f"pour en créer un — il cherche seul les Python présents sur le "
            f"poste et propose ceux qui conviennent — ou « Choisir un "
            f"Python… » si un environnement avec ras-commander existe déjà. "
            f"À défaut, la "
            f"variable d'environnement {VARIABLE_INTERPRETEUR} accepte le "
            f"chemin d'un python.exe.")


def interpreteur_hecras():
    """
    Interpreteur capable d'importer ras-commander, ou None. Recherche, dans
    l'ordre : la valeur declaree a l'execution, la variable d'environnement
    CALAGE_PYTHON, puis les .venv voisins de la chaine retenue.

    AUCUN EMPLACEMENT N'EST DEVINE AU-DELA DE CA, et c'est voulu. Un
    interpreteur trouve « quelque part » serait accepte sans que personne ne
    sache d'ou il vient ; sur un poste ou il manque, la reponse honnete est de
    le DEMANDER — le diagnostic du plugin propose de le designer et le retient.

    LE DOSSIER DE DONNEES DU PLUGIN FAIT EXCEPTION, et ce n'est pas une
    entorse a la regle : ce n'est pas un emplacement DEVINE, c'est le seul que
    le plugin INSTALLE lui-meme (installer_interpreteur). Le chercher revient
    a se souvenir de ce qu'on a fait, pas a parier sur ce qu'un autre aurait
    pu poser la. Sans lui, un environnement installe par le bouton serait
    perdu des que QSettings ne le rendrait plus — profil QGIS neuf, reglages
    reinitialises.
    """
    candidats = []
    if _interpreteur is not None:
        candidats.append(Path(_interpreteur))
    declare = os.environ.get(VARIABLE_INTERPRETEUR)
    if declare:
        candidats.append(Path(declare))

    chaine = trouver_chaine()
    for racine in ([chaine] if chaine is not None else []):
        candidats += [
            racine.parent / ".venv" / "Scripts" / "python.exe",
            racine / ".venv" / "Scripts" / "python.exe",
            racine.parent / ".venv" / "bin" / "python",
        ]
    installe = dossier_donnees_plugin() / "venv-hecras"
    candidats += [installe / "Scripts" / "python.exe",
                  installe / "bin" / "python"]
    return next((c for c in candidats if c.exists()), None)


def definir_interpreteur(chemin):
    """
    Declare l'interpreteur a l'execution. Symetrique de definir_chaine().

    Sans cela, le seul moyen de le designer etait la variable d'environnement
    CALAGE_PYTHON : il fallait quitter QGIS, modifier les variables systeme et
    relancer. La chaine, elle, avait deja un selecteur — l'asymetrie ne se
    justifiait par rien.

    Retourne (accepte, message). N'accepte QUE ce qui sait reellement piloter
    HEC-RAS : un interpreteur qui n'importe pas ras-commander serait accepte
    ici pour echouer au premier calcul, apres clonage.
    """
    global _interpreteur

    chemin = Path(chemin)
    if not chemin.is_file():
        return False, f"« {chemin} » n'est pas un fichier."
    ok, message = verifier_interpreteur(chemin)
    if ok:
        _interpreteur = chemin
    return ok, message


def dossier_donnees_plugin():
    """
    Dossier PROPRE AU PLUGIN, hors de son dossier d'installation.

    %LOCALAPPDATA%\\calage_apports sous Windows, ~/.calage_apports ailleurs.
    Il survit aux mises a jour de l'extension, ne demande aucun droit
    d'administration, et reste propre a l'utilisateur.
    """
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) / "calage_apports" if base
            else Path.home() / ".calage_apports")


def emplacement_venv_hecras():
    """
    Ou installer l'environnement Python HEC-RAS. Ne rend JAMAIS None.

    DEUX CAS, ET LE SECOND EST LE PLUS COURANT :

      - une chaine EXTERNE est retenue (poste de developpement, installation
        par lien symbolique) : a cote d'elle, « <parent>/.venv ». C'est
        l'emplacement que interpreteur_hecras() retrouve tout seul, sans
        meme avoir a le memoriser ;
      - sinon — chaine embarquee, ou aucune chaine — dans le dossier de
        donnees du plugin (dossier_donnees_plugin()).

    JAMAIS SOUS LA COPIE EMBARQUEE : elle vit dans le dossier d'installation
    de l'extension, que le gestionnaire de QGIS efface et reecrit a chaque
    mise a jour ; l'environnement y disparaitrait sans prevenir, et le projet
    s'interdit par ailleurs d'ecrire dans ce dossier.

    CETTE FONCTION RENDAIT None DANS CE DEUXIEME CAS, ce qui rendait le bouton
    « Installer… » inutilisable DANS LE SEUL CAS POUR LEQUEL IL EXISTE : un
    poste neuf, ou le plugin vient d'une archive et n'a donc que sa copie
    embarquee. Releve le 31/08/2026 en eprouvant la portabilite sur un second
    poste. Le refus etait juste sur l'emplacement, faux sur la conclusion :
    il fallait proposer un autre endroit, pas renoncer.
    """
    chaine = trouver_chaine()
    if chaine is not None and chaine != DOSSIER_EMBARQUE:
        return chaine.parent / ".venv"
    return dossier_donnees_plugin() / "venv-hecras"


PYTHON_MINIMUM = (3, 9)

# CE QUI DISQUALIFIE UN CANDIDAT SANS MEME L'ESSAYER. Les alias d'execution
# Windows sont des fichiers de zero octet dont le seul role est d'afficher
# « Python was not found; run without arguments to install from the Microsoft
# Store ». Ils occupent le PATH, repondent a « where python », et ne sont pas
# des interpreteurs. Releve le 01/09/2026 sur un poste neuf : l'utilisateur
# voyait deux python.exe et aucun ne demarrait.
_LEURRES = ("windowsapps",)


def _python_utilisable(chemin):
    r"""
    Version d'un python.exe s'il sait DEMARRER et fabriquer un venv, None sinon.

    ON VALIDE EN EXECUTANT, JAMAIS SUR LE CHEMIN, et c'est tout l'interet de
    cette fonction. Mesure du 01/09/2026 sur une installation QGIS reelle :
        C:\Program Files\QGIS\LTR\bin\python.exe
            echoue au demarrage
        C:\Program Files\QGIS\LTR\apps\Python312\python.exe
            venv utilisable, pip 25.0.1
    ILS SONT ECRITS EN ENTIER, et non elides comme ils l'etaient. Un
    emplacement de LOGICIEL est legitime dans un fichier distribue, mais le
    garde-fou qui l'autorise le reconnait A SON PREFIXE — celui du dossier
    des programmes. Abrege par des points de suspension, il ressemblait a
    un chemin de donnees, et c'est ce qu'il devenait pour le controle.
    Releve par la suite QGIS le 01/09/2026, a son premier passage complet.
    Le premier n'est qu'un lanceur : hors de l'environnement pose par
    qgis-bin.exe il rend « Could not find platform independent libraries ».
    Une recherche par emplacement l'aurait propose, et l'installation aurait
    echoue apres la validation de l'utilisateur.

    « import venv » est teste explicitement : certaines distributions
    reduites l'omettent, et l'absence ne se verrait qu'au moment de creer.
    """
    chemin = Path(chemin)
    if not chemin.is_file():
        return None
    if any(l in str(chemin).lower() for l in _LEURRES):
        return None
    try:
        if chemin.stat().st_size == 0:
            return None
    except OSError:
        return None
    try:
        sortie = subprocess.run(
            [str(chemin), "-c",
             "import venv, sys; print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20, creationflags=SANS_FENETRE)
    except Exception:                                        # noqa: BLE001
        return None
    if sortie.returncode != 0:
        return None
    brut = (sortie.stdout or "").strip().splitlines()
    if not brut:
        return None
    try:
        version = tuple(int(n) for n in brut[-1].split("."))
    except ValueError:
        return None
    return version if version >= PYTHON_MINIMUM else None


# UNE LIGNE DE « py -0p », ET N'IMPORTE QUEL DISQUE. Le lecteur precedent
# cherchait la sous-chaine « c: » et laissait tomber la ligne quand il ne la
# trouvait pas : un Python installe sur D: — cas ordinaire d'un poste
# d'entreprise dont le disque systeme est petit — etait donc INVISIBLE, sans
# un mot. Le motif accepte desormais toute lettre de lecteur, et un chemin
# UNC (\\serveur\partage\...), qu'un profil itinerant peut porter.
# « pythonw.exe » est ECARTE : il n'a pas de sortie standard, si bien que la
# sonde de _python_utilisable ne lit rien et le rejette de toute facon — un
# sous-processus de 20 s depense pour rien.
_CHEMIN_PY = re.compile(r"([A-Za-z]:\\[^\r\n]*?python(?!w)\w*\.exe"
                        r"|\\\\[^\r\n]*?python(?!w)\w*\.exe)", re.IGNORECASE)

# COMBIEN DE CANDIDATS ON ACCEPTE DE SONDER. Chaque candidat coute un
# sous-processus, borne a 20 s : une liste sans plafond ferait attendre des
# minutes devant une boite de dialogue. L'ordre etant deja « le plus probable
# d'abord » (l'interpreteur qui nous execute, puis le lanceur py, puis les
# emplacements connus, puis le PATH), ce qui tombe est la queue.
MAXIMUM_CANDIDATS = 40


def _chemin_dans_ligne_py(ligne):
    r"""
    Chemin d'interpreteur contenu dans une ligne de « py -0p », ou None.

    Le lanceur ecrit « -V:3.13 * <chemin> », et « -3.11-64 <chemin> » dans
    ses versions plus anciennes. Le chemin est la seule partie qu'on lise, et
    il peut contenir des espaces : on le reconnait a sa forme, pas a sa
    position dans la ligne.
    """
    trouve = _CHEMIN_PY.search(ligne or "")
    return trouve.group(1).strip('" ') if trouve else None


def _racines_recherche():
    r"""
    Racines sous lesquelles chercher Python, sur CE poste.

    TROIS FAMILLES, ET AUCUNE N'EST ECRITE EN DUR :
      - les dossiers de programmes que Windows declare lui-meme
        (%ProgramFiles%, %ProgramW6432%, %ProgramFiles(x86)%), qui ne sont pas
        toujours « C:\Program Files » — ni sur un poste dont le systeme est
        sur un autre disque, ni sur une installation redirigee ;
      - %LOCALAPPDATA%, ou l'installeur de python.org pose par defaut ;
      - la racine de chaque disque fixe, pour QGIS et OSGeo4W qu'on installe
        volontiers hors des dossiers de programmes.

    A: ET B: SONT ECARTES : ce sont les lettres historiques des lecteurs de
    disquettes, et les interroger reveille un materiel absent.
    """
    racines, vus = [], set()

    def ajouter(brut):
        if not brut:
            return
        chemin = Path(str(brut))
        cle = str(chemin).lower()
        if cle not in vus:
            vus.add(cle)
            racines.append(chemin)

    for variable in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)",
                     "LOCALAPPDATA"):
        ajouter(os.environ.get(variable))

    if os.name == "nt":
        for lettre in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            racine = Path(f"{lettre}:\\")
            try:
                if racine.is_dir():
                    ajouter(racine)
            except OSError:
                # Un lecteur reseau deconnecte leve plutot que de rendre
                # False : il n'est pas candidat, il ne doit pas etre fatal.
                continue
    return racines


def _emplacements_python():
    r"""
    Chemins a essayer, sans garantie : c'est _python_utilisable qui tranche.

    LE PLUS PROBABLE D'ABORD, parce que la liste est plafonnee
    (MAXIMUM_CANDIDATS) et que chaque candidat coute un sous-processus.
    """
    vus, candidats = set(), []

    def ajouter(p):
        if p is None:
            return
        p = Path(p)
        cle = str(p).lower()
        if cle not in vus:
            vus.add(cle)
            candidats.append(p)

    # LE PYTHON QUI NOUS EXECUTE, par sys.base_prefix et NON sys.executable :
    # sous QGIS, sys.executable vaut qgis-bin.exe, qui n'est pas un
    # interpreteur. base_prefix, lui, pointe la racine de l'installation
    # Python — apps\Python312 sur une installation QGIS Windows.
    ajouter(Path(sys.base_prefix) / "python.exe")
    ajouter(Path(sys.base_prefix) / "bin" / "python")

    # Le lanceur « py » sait enumerer ce qui est installe.
    try:
        sortie = subprocess.run(["py", "-0p"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=20,
                                creationflags=SANS_FENETRE)
        for ligne in (sortie.stdout or "").splitlines():
            ajouter(_chemin_dans_ligne_py(ligne))
    except Exception:                                        # noqa: BLE001
        pass

    # QGIS et OSGeo4W : DEUX niveaux, « QGIS\LTR\apps » comme
    # « QGIS 3.34\apps ». Motifs bornes plutot qu'un parcours recursif, qui
    # prendrait des secondes sur un dossier de programmes.
    import glob as _glob
    for racine in _racines_recherche():
        for motif in (r"Programs\Python\Python3*\python.exe",
                      r"Python3*\python.exe",
                      r"QGIS*\apps\Python3*\python.exe",
                      r"QGIS*\*\apps\Python3*\python.exe",
                      r"OSGeo4W*\apps\Python3*\python.exe"):
            try:
                for trouve in _glob.glob(str(racine / motif)):
                    ajouter(trouve)
            except OSError:
                continue

    # LE PATH EN ENTIER, PAS SEULEMENT SON PREMIER NOM. shutil.which s'arrete
    # au premier trouve, et sur un poste ou un leurre WindowsApps precede la
    # vraie installation, ce premier est justement celui qui ne demarre pas
    # (_LEURRES l'ecarte ensuite, et il ne restait alors plus rien).
    for dossier in os.environ.get("PATH", "").split(os.pathsep):
        if not dossier.strip():
            continue
        for nom in ("python.exe", "python3.exe", "python", "python3"):
            chemin = Path(dossier.strip('" ')) / nom
            try:
                if chemin.is_file():
                    ajouter(chemin)
            except OSError:
                continue
    for nom in ("python", "python3", "py"):
        ajouter(shutil.which(nom))
    return candidats[:MAXIMUM_CANDIDATS]


def _origine_python(chemin):
    """« QGIS » si l'interpreteur appartient a une installation QGIS."""
    bas = str(chemin).lower()
    return "QGIS" if ("qgis" in bas or "osgeo4w" in bas) else "independant"


def pythons_candidats(journal=None, annule=None):
    r"""
    Interpreteurs capables de servir de BASE au venv HEC-RAS, valides un par
    un en les executant. Rend une liste de dicts {chemin, version, origine},
    LE MEILLEUR D'ABORD.

    UN PYTHON INDEPENDANT PASSE AVANT CELUI DE QGIS (decision du 01/09/2026).
    Les deux fonctionnent, mais un venv construit sur apps\Python312 casse le
    jour ou une montee de version de QGIS remplace ce dossier — et QGIS se met
    a jour seul. Celui de QGIS reste propose, et devient le premier choix
    quand il est le seul present : c'est le cas ordinaire d'un poste neuf, ou
    il evite toute installation.

    A egalite d'origine, la version la plus recente d'abord.
    """
    trouves = []
    for chemin in _emplacements_python():
        if annule is not None and annule():
            return []
        if journal is not None:
            journal(f"Vérification de Python : {chemin}")
        version = _python_utilisable(chemin)
        if version is not None:
            trouves.append({"chemin": Path(chemin), "version": version,
                            "origine": _origine_python(chemin)})
    trouves.sort(key=lambda c: (c["origine"] == "QGIS",
                                tuple(-n for n in c["version"])))
    return trouves


def installer_interpreteur(python_base, journal=None, *, cible=None):
    """
    Cree un environnement Python HEC-RAS et y installe ras-commander et h5py.

    python_base : l'interpreteur qui sert de BASE au venv. Il n'est pas
        devine : « python » n'existe pas forcement dans le PATH d'un poste
        Windows, et celui de QGIS ne sait pas toujours creer un venv
        utilisable. C'est l'appelant qui le designe.
    journal : appelable recevant les lignes de sortie, pour que l'attente ne
        soit pas muette. pip peut prendre plusieurs minutes.

    cible : dossier annoncé à la confirmation, figé avant le démarrage différé.

    Retourne (chemin_interpreteur, message). En cas d'echec, (None, motif).

    NE REMPLACE JAMAIS UN ENVIRONNEMENT EXISTANT : si le dossier est deja la,
    on tente de l'utiliser tel quel. Effacer un .venv que l'utilisateur a
    peuple lui-meme serait irreversible et hors sujet.
    """
    import subprocess

    dire = journal or (lambda _: None)
    cible = Path(cible) if cible is not None else emplacement_venv_hecras()
    python_base = Path(python_base)
    if not python_base.is_file():
        return None, f"« {python_base} » n'est pas un fichier."

    interpreteur = cible / "Scripts" / "python.exe"
    if not interpreteur.exists():
        interpreteur = cible / "bin" / "python"

    if not interpreteur.exists():
        dire(f"Création de l'environnement dans {cible}…")
        try:
            # ENVIRONNEMENT ASSAINI, COMME PARTOUT AILLEURS. Cette fonction
            # s'execute DANS QGIS : sans cela, python.exe herite du
            # PYTHONHOME et du PYTHONPATH de QGIS et fabrique un
            # environnement qui n'est pas le sien. Voir environnement_propre.
            subprocess.run([str(python_base), "-m", "venv", str(cible)],
                           check=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600,
                           env=environnement_propre(python_base),
                           creationflags=SANS_FENETRE)
        except Exception as e:                               # noqa: BLE001
            sortie = getattr(e, "stderr", "") or ""
            return None, f"création de l'environnement impossible : {e}\n{sortie}"
        interpreteur = cible / "Scripts" / "python.exe"
        if not interpreteur.exists():
            interpreteur = cible / "bin" / "python"
    else:
        dire(f"Environnement déjà présent dans {cible}, réutilisé.")

    if not interpreteur.exists():
        return None, (f"environnement cree dans {cible}, mais aucun "
                      f"interpreteur n'y a ete trouve.")

    # LA VERSION MINIMALE EST IMPOSEE ICI AUSSI, pas seulement verifiee apres
    # coup : une 0.98 borne mal les tableaux d'hydrogramme et tronquerait un
    # apport en silence (voir RAS_COMMANDER_MINIMUM).
    # MEME EXCEPTION QU'A LA VERIFICATION : pywin32 n'existe que sous Windows,
    # et pip echouerait ailleurs sur tout le lot.
    paquets = [p for i, p in PAQUETS_HECRAS
               if sys.platform == "win32" or not i.startswith("win32")]
    dire(f"Installation de {len(paquets)} paquets ({', '.join(paquets[:3])}…) "
         f"— plusieurs minutes")
    try:
        resultat = subprocess.run(
            [str(interpreteur), "-m", "pip", "install", "--upgrade", *paquets],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=1800,
            # SANS CET ASSAINISSEMENT, PIP N'INSTALLE RIEN ET REND 0.
            # L'installeur tourne dans QGIS, dont le PYTHONPATH et le
            # PYTHONHOME pointent SA bibliotheque — qui livre deja numpy,
            # pandas, scipy, matplotlib, openpyxl, geopandas, shapely et
            # pyproj, soit huit des onze paquets. pip les voit sur sys.path,
            # les tient pour « already satisfied », ne les pose pas dans le
            # venv, et sort en succes. La sonde, elle, regarde le venv REEL
            # avec un environnement propre : elle les declare tous absents.
            # D'ou « installation terminee » suivi de « onze modules
            # absents », deux fois de suite. Releve sur un poste neuf le
            # 05/09/2026, a la premiere installation reelle du bouton.
            env=environnement_propre(interpreteur),
            creationflags=SANS_FENETRE)
    except Exception as e:                                   # noqa: BLE001
        return None, f"installation impossible : {e}"
    if resultat.returncode != 0:
        return None, (f"pip a echoue (code {resultat.returncode}) :\n"
                      f"{(resultat.stderr or resultat.stdout or '')[-2000:]}")
    dire("Installation terminée, vérification…")

    # PIP NE REPARE PAS UN PAQUET DEJA PRESENT. « --upgrade » suit la strategie
    # only-if-needed : sur un environnement REUTILISE ou ras-commander est
    # deja la dans une version qui satisfait « >=0.99 », pip tient la
    # contrainte pour remplie et ne re-resout PAS ses dependances. Ce qui
    # manquait dans cet environnement y manque toujours. Releve le
    # 03/09/2026 sur un poste neuf : onze paquets « installes », puis
    # « module(s) absent(s) : xarray » — la dependance declaree par
    # ras-commander que pip n'a jamais regardee.
    #   ON POSE DONC CE QUE LA SONDE NOMME, avant de juger. La liste vient de
    #   la meme sonde que le verdict ; un manquant qui n'est pas des notres
    #   recoit son nom d'import comme nom pip, comme dans le message.
    manquants = modules_manquants(interpreteur)
    if manquants:
        connus = dict(PAQUETS_HECRAS)
        complement = [connus.get(m, m) for m in manquants]
        dire(f"Il manque encore {', '.join(complement)} — dependance(s) d'un "
             f"paquet deja present, que pip n'a pas re-resolues. Installation "
             f"du complement…")
        try:
            resultat = subprocess.run(
                [str(interpreteur), "-m", "pip", "install", *complement],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=1800,
                env=environnement_propre(interpreteur),
                creationflags=SANS_FENETRE)
        except Exception as e:                               # noqa: BLE001
            return None, f"installation du complement impossible : {e}"
        if resultat.returncode != 0:
            return None, (f"pip a echoue sur le complement (code "
                          f"{resultat.returncode}) :\n"
                          f"{(resultat.stderr or resultat.stdout or '')[-2000:]}")
        dire("Complément installé, vérification…")

    # LE MEME CONTROLE QUE POUR UN INTERPRETEUR DESIGNE A LA MAIN : ce qui
    # compte n'est pas que pip ait rendu 0, c'est que la chaine puisse s'en
    # servir.
    ok, message = verifier_interpreteur(interpreteur, depuis_installeur=True)
    if not ok:
        return None, f"environnement cree, mais inutilisable : {message}"
    return interpreteur, message


def restaurer_interpreteur(chemin):
    """
    Retablit un interpreteur DEJA verifie lors d'une session precedente.

    Distincte de definir_interpreteur() a dessein : celle-ci lance un
    sous-processus, et le faire a chaque ouverture de QGIS retarderait le
    demarrage pour un cas — un environnement devenu invalide entre deux
    sessions — que le diagnostic signale de toute facon. On verifie donc
    seulement que le fichier existe encore.

    Retourne True si l'interpreteur a ete retabli.
    """
    global _interpreteur

    if not chemin or not Path(chemin).is_file():
        return False
    _interpreteur = Path(chemin)
    return True


def _sonder_interpreteur(chemin):
    """
    Lance la sonde d'import dans l'interpreteur et rend son resultat brut.

    Retourne (acheve, None) ou (None, message d'erreur). Deux appelants :
    verifier_interpreteur(), qui en tire un verdict, et modules_manquants(),
    qui en tire la liste de ce que pip doit encore poser. Une seule sonde,
    pour que les deux voient la meme chose.
    """
    import subprocess

    noms = [i for i, _ in PAQUETS_HECRAS]
    code = (
        # « import importlib » NE SUFFIT PAS : importlib.util est un
        # sous-module, qui n'est pas charge par l'import du paquet.
        "import importlib.util, sys\n"
        f"manquants = [m for m in {noms!r} "
        "if importlib.util.find_spec(m) is None]\n"
        # pywin32 n'existe QUE sous Windows. L'exiger ailleurs refuserait un
        # interpreteur par ailleurs valide — la chaine tourne sous Windows en
        # pratique, mais un refus fonde sur une impossibilite serait faux.
        "if sys.platform != 'win32':\n"
        "    manquants = [m for m in manquants if not m.startswith('win32')]\n"
        "if manquants:\n"
        "    print('MANQUANTS ' + ' '.join(manquants)); sys.exit(3)\n"
        # IMPORTER CE QU'ON APPELLE, PAS SEULEMENT CE QU'ON NOMME.
        # PAQUETS_HECRAS enumere ce que LA CHAINE importe ; ras-commander a
        # ses propres dependances, qu'on ne peut pas suivre a la main sans
        # diverger a la premiere version. find_spec sur nos dix noms rendait
        # donc une liste VIDE sur un interpreteur prive de xarray — que
        # ras-commander exige pour HdfResultsMesh, seule voie du profil en
        # long. Et sur une ras-commander qui charge .hdf paresseusement,
        # « import ras_commander » passait AUSSI : le calage tournait 14 h,
        # et seule la figure mourait — « profil en long de synthese : non
        # calculable (ModuleNotFoundError: No module named 'xarray') »,
        # releve en production le 02/09/2026.
        # UN ModuleNotFoundError REPART PAR LE CANAL DES MANQUANTS : c'est le
        # seul message qui donne la commande pip, donc le seul utilisable.
        "try:\n"
        "    import h5py, ras_commander\n"
        "    from ras_commander import HdfResultsMesh\n"
        "except ModuleNotFoundError as manque:\n"
        "    print('MANQUANTS ' + (manque.name or '?')); sys.exit(3)\n"
        "print(f'python {sys.version_info.major}.{sys.version_info.minor}"
        ".{sys.version_info.micro}, ras-commander "
        "{ras_commander.__version__}, h5py {h5py.__version__}')")
    try:
        # errors="replace" : un octet non UTF-8 dans la sortie (accent d'un
        # chemin, message Windows en cp1252) faisait mourir CE controle-ci
        # sur une UnicodeDecodeError, et la raison de l'echec se perdait au
        # moment precis ou elle sert. Meme regle qu'a l'appel du pont.
        return subprocess.run(
            [str(chemin), "-c", code], capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=90, env=environnement_propre(chemin),
            creationflags=SANS_FENETRE), None
    except Exception as e:                                   # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def modules_manquants(chemin):
    """
    Noms d'import que la sonde declare absents de cet interpreteur.

    [] si rien ne manque, None si la sonde n'a pas pu tourner. C'est ce que
    l'installeur pose ensuite par pip : la liste vient de la MEME sonde que le
    verdict, pas d'une seconde regle.
    """
    acheve, erreur = _sonder_interpreteur(chemin)
    if acheve is None:
        return None
    if acheve.returncode == 3 and "MANQUANTS" in (acheve.stdout or ""):
        return acheve.stdout.split("MANQUANTS", 1)[1].split()
    return []


def verifier_interpreteur(chemin, depuis_installeur=False):
    """
    Cet interpreteur sait-il piloter HEC-RAS ? Retourne (ok, message).

    depuis_installeur : le message d'echec ne renvoie alors PAS au bouton
    « Installer… » — c'est lui qui appelle, et il vient d'echouer. Releve le
    03/09/2026 sur un poste neuf : « ou laisser le bouton Installer… creer un
    environnement complet », affiche par ce bouton meme. Un message qui
    conseille ce qui vient d'echouer apprend a etre ignore.

    Le test est celui qui compte : importer TOUT ce dont le pont a besoin
    (PAQUETS_HECRAS) dans un sous-processus, avec le meme assainissement
    d'environnement que les appels reels. Verifier la seule existence du
    fichier ne prouverait rien.

    IL N'EXIGEAIT QUE ras-commander ET h5py, si bien qu'un environnement
    depourvu de geopandas etait accepte ici pour echouer a la premiere
    composition — loin de la cause, et apres que l'utilisateur ait cru
    l'installation reussie.
    """
    if chemin is None:
        return False, "aucun interpreteur n'a ete designe."
    chemin = Path(chemin)
    if not chemin.is_file():
        return False, f"« {chemin} » n'est pas un fichier."

    acheve, erreur = _sonder_interpreteur(chemin)
    if acheve is None:
        return False, erreur
    if acheve.returncode == 3 and "MANQUANTS" in (acheve.stdout or ""):
        absents = acheve.stdout.split("MANQUANTS", 1)[1].split()
        # UN MANQUANT PEUT NE PAS ETRE DES NOTRES — xarray arrive par
        # ras-commander. A defaut de nom pip connu, le nom d'import fait une
        # commande juste ; le taire rendrait « pip install » sans rien
        # derriere.
        connus = dict(PAQUETS_HECRAS)
        pip = " ".join(connus.get(a, a) for a in absents)
        return False, (
            f"{'module absent' if len(absents) < 2 else 'modules absents'} "
            f"de cet interpréteur : "
            f"{', '.join(absents)}.\n\nLe pont en a besoin dès la première "
            f"composition. Les installer par :\n"
            f"    \"{chemin}\" -m pip install {pip}\n\n"
            + ("L'installeur a déjà tenté de les poser : voir la sortie de "
               "pip ci-dessus, et le journal du plugin."
               if depuis_installeur else
               "ou laisser le bouton « Installer… » créer un environnement "
               "complet."))
    if acheve.returncode != 0:
        return False, _cause_echec(acheve)

    resume = acheve.stdout.strip()
    version = _version_ras_commander(resume)
    if version is not None and version < RAS_COMMANDER_MINIMUM:
        return False, (
            f"ras-commander {'.'.join(str(n) for n in version)} est trop "
            f"ancienne : il en faut au moins "
            f"{'.'.join(str(n) for n in RAS_COMMANDER_MINIMUM)}. Les versions "
            f"anterieures bornent mal les tableaux d'hydrogramme — un apport "
            f"ecrit y serait tronque en silence. Mettre a jour par "
            f"« python -m pip install --upgrade ras-commander ».")
    return True, resume


def _version_ras_commander(resume):
    """
    (majeur, mineur, correctif) lus dans la ligne rendue par l'interpreteur,
    ou None si elle ne s'y trouve pas.

    None vaut « je ne sais pas », et laisse passer : refuser sur une version
    illisible bloquerait un environnement parfaitement valide au premier
    changement de format de cette chaine.
    """
    trouve = re.search(r"ras-commander\s+v?(\d+(?:\.\d+)*)", resume or "")
    if not trouve:
        return None
    return tuple(int(n) for n in trouve.group(1).split("."))


def _cause_echec(acheve):
    """
    Ligne la plus PARLANTE d'un echec d'interpreteur.

    Prendre la derniere ligne de stderr donnait « <no Python frame> » sur le
    python de QGIS : vrai, mais sans valeur pour qui doit corriger sa
    configuration. On cherche donc d'abord la ligne qui nomme la cause.
    """
    sortie = ((acheve.stderr or "") + "\n" + (acheve.stdout or "")).strip()
    lignes = [l.strip() for l in sortie.splitlines() if l.strip()]
    parlantes = ("ModuleNotFoundError", "ImportError", "DLL load failed",
                 "SRE module mismatch", "Fatal Python error",
                 "Could not find platform")
    for ligne in lignes:
        if any(p in ligne for p in parlantes):
            return ligne[:200]
    return lignes[-1][:200] if lignes else f"code de retour {acheve.returncode}"


def environnement_propre(interpreteur):
    """
    Environnement assaini pour le sous-processus.

    Deux assainissements, tous deux indispensables et decouverts a l'usage.

    1. QGIS exporte PYTHONPATH et PYTHONHOME vers sa propre bibliotheque
       standard. Un interpreteur d'une autre version qui en herite s'arrete
       aussitot sur « AssertionError: SRE module mismatch ». Toutes les
       variables PYTHON* sont donc retirees.

    2. Le PATH de QGIS place ses propres binaires en tete, et il y figure une
       bibliotheque HDF5. Meme en prefixant le repertoire de l'interpreteur,
       les repertoires de QGIS restent PRESENTS et h5py y trouve la mauvaise
       DLL : « DLL load failed while importing _errors ». Le PATH est donc
       RECONSTRUIT a partir de rien plutot que filtre — une liste noire ne
       protege que des chemins deja connus.
    """
    import os

    env = {c: v for c, v in os.environ.items() if not c.startswith("PYTHON")}

    racine = Path(interpreteur).parent
    systeme = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    env["PATH"] = os.pathsep.join(str(d) for d in [
        racine,                      # python.exe et ses DLL
        racine.parent,               # racine de l'environnement virtuel
        racine.parent / "Library" / "bin",   # DLL scientifiques (conda)
        systeme / "System32",
        systeme,
        systeme / "System32" / "Wbem",
    ])

    # Retire par le filtre PYTHON* ci-dessus, et pourtant indispensable :
    # sans lui, le sous-processus ecrit sur sa sortie avec l'encodage de la
    # console Windows (cp1252) alors que l'appelant la relit en UTF-8. Les
    # accents et les guillemets des messages arrivaient donc en « ? ». Un
    # message d'erreur illisible est presque aussi genant que pas de message.
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def appeler_pont(*arguments, delai=300):
    """
    Execute une commande de pont_hecras.py dans l'interpreteur HEC-RAS et
    retourne sa reponse JSON decodee.

    Leve RuntimeError avec un message exploitable si l'appel echoue : c'est ce
    message que le plugin affiche, il doit donc rester lisible.
    """
    import json
    import subprocess

    chaine = trouver_chaine()
    if chaine is None:
        raise RuntimeError(
            f"Chaîne de calage introuvable : impossible d'atteindre "
            f"pont_hecras.py. La déclarer par la variable {VARIABLE_CHAINE}, "
            f"ou la désigner depuis le plugin.")

    interpreteur = interpreteur_hecras()
    if interpreteur is None:
        raise RuntimeError(message_interpreteur_introuvable())

    commande = [str(interpreteur), str(chaine / "pont_hecras.py"),
                *[str(a) for a in arguments]]
    try:
        acheve = subprocess.run(commande, capture_output=True, text=True,
                                timeout=delai, encoding="utf-8", errors="replace",
                                env=environnement_propre(interpreteur),
                                creationflags=SANS_FENETRE)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Délai dépassé ({delai} s) : {' '.join(arguments[:2])}")

    sortie = (acheve.stdout or "").strip()
    if not sortie:
        raise RuntimeError(
            f"Aucune réponse du pont.\nCommande : {' '.join(commande)}\n"
            f"Erreur : {(acheve.stderr or '').strip()[:800]}")
    try:
        reponse = json.loads(sortie.splitlines()[-1])
    except json.JSONDecodeError:
        raise RuntimeError(f"Réponse illisible du pont :\n{sortie[:800]}")

    if not reponse.get("ok"):
        details = reponse.get("details") or []
        raise RuntimeError(reponse.get("erreur", "échec sans message")
                           + ("\n" + "\n".join(details) if details else ""))
    return reponse


# ---------------------------------------------------------------------------
# PREPARATION DU PAQUET DE CALAGE
# ---------------------------------------------------------------------------

def composer_paquet(dossier_sortie, sections, apports, axe, crs_cible=None):
    """
    Ecrit les trois shapefiles normalises dans un dossier unique.

    sections / apports / axe : GeoDataFrames deja normalises (colonnes 'nom'
    et 'geometry'), tels que produits par couche_vers_gdf().

    Reprojette si crs_cible est fourni. Retourne les chemins ecrits.
    """
    import geopandas as gpd  # noqa: F401  (verifie la disponibilite)

    dossier = Path(dossier_sortie)
    dossier.mkdir(parents=True, exist_ok=True)

    chemins = {}
    for cle, gdf in (("sections", sections), ("apports", apports), ("axe", axe)):
        if gdf is None or len(gdf) == 0:
            continue
        if crs_cible is not None and gdf.crs is not None and str(gdf.crs) != str(crs_cible):
            gdf = gdf.to_crs(crs_cible)
        chemin = dossier / NOMS_FICHIERS[cle]
        gdf[["nom", "geometry"]].to_file(chemin)
        chemins[cle] = chemin
    return chemins


def apparier_paquet(chemins_shp, sens=None, pk_origine=0.0, profil=None):
    """
    Determine quelle injection alimente quelle section, a partir des
    shapefiles composes.

    Enchaine ce que le plugin ne doit pas avoir a orchestrer lui-meme :
    lecture des couches, calcul des PK par projection sur l'axe, deduction du
    SENS de l'axe d'apres les altitudes du profil en long, puis appariement
    de chaque section avec la premiere injection en amont d'elle.

    sens : impose le sens ; None le fait deduire du profil, et a defaut de
        profil exploitable retombe sur « amont_aval ».

    Retourne le dict de geometrie.apparier_amont_aval(), enrichi de « sens »,
    « sens_deduit » et des PK, pour que l'appelant puisse expliquer.
    """
    _raccorder()
    import geometrie as geo

    sens_deduit = geo.sens_depuis_profil(profil) if sens is None else None
    sens_retenu = sens or sens_deduit or "amont_aval"

    axe, _ = geo.lire_axe(chemins_shp["axe"])
    g_sections = geo.calculer_pk(geo.lire_lignes(chemins_shp["sections"]), axe,
                                 pk_origine=pk_origine, sens=sens_retenu)
    g_apports = geo.calculer_pk(geo.lire_lignes(chemins_shp["apports"]), axe,
                                pk_origine=pk_origine, sens=sens_retenu)

    resultat = geo.apparier_amont_aval(
        list(g_sections["nom"]), list(g_sections["pk_m"]),
        list(g_apports["nom"]), list(g_apports["pk_m"]))
    resultat["sens"] = sens_retenu
    resultat["sens_deduit"] = sens_deduit
    resultat["pk_sections"] = dict(zip(g_sections["nom"], g_sections["pk_m"]))
    resultat["pk_apports"] = dict(zip(g_apports["nom"], g_apports["pk_m"]))
    return resultat


def pentes_locales_apports(dossier_projet, nom_projet, geometrie, chemin_axe,
                           nom_zone_2d, pk_apports):
    """
    Pente du fond au droit de chaque apport, pour PRE-REMPLIR la colonne
    Pente_m_par_m du classeur.

    C'est exactement la valeur que le calage aurait deduite tout seul d'une
    case laissee vide (moyenne du fond sur +/- 200 m autour de l'injection,
    majoree de 20 %, cf. geometrie.pente_locale). L'ecrire dans le classeur ne
    change donc AUCUN resultat : cela rend visible, et modifiable, une
    hypothese qui restait jusqu'ici implicite — on ne discute pas une valeur
    qu'on ne voit pas.

    PASSE PAR LE PONT, ET C'EST OBLIGATOIRE. Le calcul lui-meme est court
    (geometrie.profil_depuis_modele puis pente_locale) et cette fonction
    l'appelait directement — mais profil_depuis_modele lit le MAILLAGE de la
    geometrie, donc importe h5py, qui ne s'initialise plus des que QGIS est
    charge (voir « PONT VERS HEC-RAS » plus haut). L'ImportError etait avale
    par un except muet : la colonne restait vide A CHAQUE COMPOSITION, sur
    tous les modeles, y compris parfaitement pretraites — sans qu'aucun
    message ne le dise. Constat utilisateur du 07/08/2026, « la pente des
    apports n'est jamais remplie ».

    geometrie : numero ou nom du fichier de geometrie (« 03 » ou « g03 »).
    pk_apports : {nom_apport: PK en m}, tel que apparier_paquet le rend — donc
        deja dans la convention de PK du sens retenu. Le pont ne les recalcule
        pas.

    Retourne (pentes, motif) : {nom_apport: pente}, VIDE si la pente n'est pas
    calculable — geometrie non pretraitee par HEC-RAS (pas de .gXX.hdf),
    interpreteur HEC-RAS introuvable, profil trop court ou trop plat — et le
    MOTIF en clair, a afficher. Ne leve jamais : une pente absente laisse
    simplement la case vide, et le calage la deduira comme avant
    (pont_hecras._pentes_deduites), au moment d'ecrire l'apport.
    """
    if not pk_apports:
        return {}, "aucun PK d'apport disponible"
    numero = str(geometrie).lstrip("gG")
    hdf = Path(dossier_projet) / f"{nom_projet}.g{numero}.hdf"
    if not hdf.is_file():
        return {}, (f"geometrie non pretraitee par HEC-RAS ({hdf.name} "
                    f"absent) : pente locale non calculable.")
    try:
        reponse = appeler_pont(
            "pentes", "--geometrie", str(hdf),
            "--axe", str(chemin_axe),
            *(("--zone", str(nom_zone_2d)) if nom_zone_2d else ()),
            "--pk-apports", json.dumps(
                {str(n): float(pk) for n, pk in pk_apports.items()
                 if pk is not None}))
    except Exception as e:                                   # noqa: BLE001
        return {}, f"{type(e).__name__}: {e}"
    return (reponse.get("pentes") or {}), (reponse.get("motif") or "")


# ---------------------------------------------------------------------------
# LE CONTRAT AVEC LA CHAINE
#
# Ces dix-huit cles sont tout ce que la fenetre transmet a la chaine de
# calage, par la feuille Parametres du classeur. Elles etaient construites
# DANS le QDialog : un renommage cote chaine cassait donc a un endroit
# qu'aucun essai hors QGIS ne pouvait atteindre, et le defaut ne se voyait
# qu'a la composition suivante — sur un classeur silencieusement incomplet,
# ou la valeur manquante retombait sur le defaut de preparer_classeur.
#
# Ici, le contrat s'eprouve en console : la fenetre passe des valeurs simples,
# et c'est cette fonction qui NOMME les cles et pose les prefixes p/g/u.
#
# LE DEPLACEMENT EST PARTIEL, ET IL FAUT LE DIRE. _composer_et_controler relit
# ensuite six cles du dict pour son propre usage — Sens_axe, PK_origine_m,
# Dossier_projet_HECRAS, Nom_projet, Geometrie_reference, Nom_zone_2D. Ce qui
# a change est l'ECRITURE du contrat, plus sa lecture : renommer une cle ici
# casse toujours la-bas, mais la liste des cles, elle, s'eprouve desormais
# sans QGIS.
# ---------------------------------------------------------------------------

# LES VALEURS PAR DEFAUT DES REGLAGES DE LA FENETRE, EN UN SEUL EXEMPLAIRE
# (10/11/2026, demande utilisateur : signaler un reglage qui n'est pas a sa
# valeur par defaut, et pouvoir y revenir). Cle du classeur -> valeur. La
# fenetre y lit ses valeurs d'ouverture, ses « ! défaut : … » et son bouton
# « Revenir aux paramètres par défaut » ; preparer_classeur y lit les siennes.
DEFAUTS_PARAMETRES = {
    # Fenetre de simulation : vide = celle du plan de reference.
    "Simulation_debut": "",
    "Simulation_fin": "",
    "Intervalle_calcul": "",
    "Intervalle_sortie": "",
    "Intervalle_instantane": "",
    "Intervalle_mapping": "",
    "Sens_axe": "amont_aval",
    "PK_origine_m": 0,
    # Precision attendue, en POURCENTAGE de la cible.
    "Tolerance_volume_pct": 5.0,
    "Tolerance_pic_pct": 2.0,
    "Bilan_masse_max_pct": 5.0,
    "Nb_max_iterations_par_apport": 6,
    "Sous_dossier_resultats": "resultats_finaux",
    "Sous_dossier_suivi": "suivi",
    # 0 = les plans gardent les cœurs qu'ils demandent.
    "Coeurs_par_calcul": 0,
    "Elaguer_plans_etape": "non",
}

# SEUIL DE QUALITE NUMERIQUE, PAS DE CONCORDANCE. Doit rester d'accord avec
# calage.Configuration.bilan_masse_max_pct : c'est la meme grandeur, ecrite
# ici pour que le classeur la porte sans que le plugin importe la chaine.
BILAN_MASSE_DEFAUT = DEFAUTS_PARAMETRES["Bilan_masse_max_pct"]


def parametres_calage(dossier_projet, nom_projet, version_hecras, nom_zone_2d,
                      numero_plan, numero_geometrie, numero_unsteady,
                      mode_selection, nom_clone_geometrie, premier_apport,
                      sens_axe, pk_origine_m, nb_max_iterations,
                      tolerance_volume_pct, tolerance_pic_pct, dossier_sortie,
                      sous_dossier_resultats, sous_dossier_suivi,
                      fenetre=None, bilan_masse_max_pct=BILAN_MASSE_DEFAUT,
                      prefixe_scenario="", elaguer_etapes=False):
    """
    Feuille Parametres du classeur, a partir de valeurs simples.

    Aucun widget, aucun objet Qt : cette fonction s'appelle et se compare en
    console. C'est tout son interet.

    numero_plan, numero_geometrie, numero_unsteady : les NUMEROS seuls (« 03 »),
        tels que lister_projet_hecras les rend. Les prefixes p/g/u sont poses
        ici, une fois, et ne sont plus ecrits ailleurs.
    fenetre : les cles de fenetre de simulation, ou un dict vide. Elle n'est
        transmise QUE si elle differe de celle du plan de reference — la
        recopier a l'identique reviendrait a reecrire dans le plan clone ce
        qu'il contient deja.
    """
    parametres = {
        "Dossier_projet_HECRAS": dossier_projet,
        "Nom_projet": nom_projet,
        # Lue dans les fichiers du modele, jamais saisie.
        "Version_HECRAS": version_hecras or "",
        "Nom_zone_2D": nom_zone_2d,
        "Plan_reference": f"p{numero_plan}",
        "Geometrie_reference": f"g{numero_geometrie}",
        "Unsteady_reference": f"u{numero_unsteady}",
        "Mode_selection_modele": mode_selection,
        "Nom_clone_geometrie": nom_clone_geometrie,
        "Premier_apport": premier_apport,
        # Prefixe des titres de plan. Vide = comportement d'avant. Il separe
        # les plans d'un scenario de ceux d'un autre : sans lui, caler le Q10
        # apres le Q100 efface les plans du Q100.
        "Prefixe_scenario": prefixe_scenario,
        # ELAGAGE DES PLANS D'ETAPE, DECIDE ICI ET APPLIQUE PAR LA CHAINE a la
        # fin d'un calage abouti. « oui » / « non » et non True/False : ce
        # parametre traverse un classeur Excel, ou un booleen se relit
        # « TRUE », « VRAI » ou 1 selon la langue d'Excel.
        "Elaguer_plans_etape": "oui" if elaguer_etapes else "non",
        "Sens_axe": sens_axe,
        "PK_origine_m": pk_origine_m,
        "Nb_max_iterations_par_apport": nb_max_iterations,
        # EN POURCENTAGES, comme le disent les noms de cle : c'est la chaine
        # qui les ramene en fractions a la lecture (pont_hecras, « / 100.0 »).
        "Tolerance_volume_pct": tolerance_volume_pct,
        "Tolerance_pic_pct": tolerance_pic_pct,
        # CELUI-CI RESTE EN POURCENTAGE DES DEUX COTES : ce n'est pas un
        # rapport a la cible mais l'erreur de conservation du solveur.
        "Bilan_masse_max_pct": bilan_masse_max_pct,
        "Dossier_sortie": dossier_sortie,
        "Sous_dossier_resultats": sous_dossier_resultats,
        "Sous_dossier_suivi": sous_dossier_suivi,
    }
    parametres.update(fenetre or {})
    return parametres


def _saisie_a_preserver(chemin):
    """
    Ce qui a deja ete saisi dans le classeur a recomposer : (cibles, pentes).
    cibles : la feuille Cibles telle que pandas la lit, None si le classeur
    n'existe pas ou si elle est illisible. pentes : {(apport, section):
    pente}, vide si rien n'est relisible.
    """
    import pandas as pd

    cibles_existantes = None
    pentes_existantes = {}
    if chemin.exists():
        try:
            cibles_existantes = pd.read_excel(chemin, sheet_name="Cibles")
        except Exception:
            cibles_existantes = None
        try:
            corr_existante = pd.read_excel(chemin, sheet_name="Correspondance")
            if "Pente_m_par_m" in corr_existante.columns:
                for _, ligne in corr_existante.iterrows():
                    valeur = ligne["Pente_m_par_m"]
                    if pd.notna(valeur) and str(valeur).strip() != "":
                        cle = (str(ligne["Nom_Apport (BC line)"]),
                               str(ligne["Nom_Section (reference line)"]))
                        pentes_existantes[cle] = valeur
        except Exception:
            pentes_existantes = {}
    return cibles_existantes, pentes_existantes


def _parametres_du_classeur(chemins_shp, parametres):
    """Les parametres ecrits dans le JSON voisin : defauts, puis ceux transmis."""
    valeurs = {
        "Dossier_projet_HECRAS": "",
        "Nom_projet": "",
        "Version_HECRAS": "7.0.1",
        "Nom_zone_2D": "",
        "Geometrie_reference": "g01",
        "Unsteady_reference": "u01",
        "Plan_reference": "p01",
        # Fenetre de simulation du plan de calcul. Laissees vides, celle du
        # plan de reference s'applique telle quelle — le bon defaut tant qu'on
        # ne substitue pas un unsteady flow couvrant une autre periode.
        **{cle: DEFAUTS_PARAMETRES[cle] for cle in (
            "Simulation_debut", "Simulation_fin", "Intervalle_calcul",
            "Intervalle_sortie", "Intervalle_instantane", "Intervalle_mapping")},
        # Trace de la pente donnee aux injections CREEES par le plugin. Non
        # relue par le calage : elle est ecrite dans l'Unsteady Flow au moment
        # de la creation. Elle figure ici pour que le classeur porte, seul, de
        # quoi refaire l'etude.
        "Pente_apport_creee_m_par_m": "",
        # Precision attendue, en POURCENTAGE de la cible, jugee sur la
        # fenetre du hydrogramme PRINCIPAL uniquement.
        "Tolerance_volume_pct": DEFAUTS_PARAMETRES["Tolerance_volume_pct"],
        "Tolerance_pic_pct": DEFAUTS_PARAMETRES["Tolerance_pic_pct"],
        # FENETRE DE JUGEMENT. Restreint le verdict et les figures a la crue
        # calee ; l'apport, lui, reste calcule sur toute la serie. Vide =
        # active, le defaut. Les deux seuils portent sur le volume cumule du
        # deficit ; la methodologie les donne comme valeurs A CONFIRMER, d'ou
        # leur presence ici plutot qu'en dur dans le code. t0/tf vides =
        # detection automatique, qui n'est qu'une proposition.
        "Fenetre_active": "",
        "Fenetre_seuil_bas_pct": 0.5,
        "Fenetre_seuil_haut_pct": 99.0,
        "Fenetre_t0_h": "",
        "Fenetre_tf_h": "",
        # Apport par lequel demarrer. Vide = tous. Renseigne, le calage repart
        # du plan d'etape de l'apport precedent et tient l'amont pour cale.
        "Premier_apport": "",
        "Prefixe_scenario": "",
        # Le plan de reference porte deja le titre du plan final : « oui »
        # autorise la chaine a le remplacer si le calage est conforme. Reglage
        # DU LANCEMENT : la question posee au depart l'ecrit, jamais la
        # composition.
        "Remplacer_plan_source": "non",
        # Cœurs demandes a HEC-RAS pour chaque calcul, ecrits par
        # ras-commander dans le plan d'etape avant son calcul. 0 = le plan
        # garde ce qu'il demande. Reglage DU LANCEMENT : la case de l'etape
        # Lancer l'ecrit au depart, avec la suggestion faite d'apres le poste.
        "Coeurs_par_calcul": DEFAUTS_PARAMETRES["Coeurs_par_calcul"],
        "Nb_max_iterations_par_apport":
            DEFAUTS_PARAMETRES["Nb_max_iterations_par_apport"],
        "Bilan_masse_max_pct": BILAN_MASSE_DEFAUT,
        "Source_geometrie": "SHP",
        "Fichier_SHP_Sections": str(chemins_shp.get("sections", "")),
        "Fichier_SHP_Apports": str(chemins_shp.get("apports", "")),
        "Fichier_SHP_Axe": str(chemins_shp.get("axe", "")),
        "Sens_axe": DEFAUTS_PARAMETRES["Sens_axe"],
        "Champ_nom_SHP": "nom",
        "PK_origine_m": DEFAUTS_PARAMETRES["PK_origine_m"],
        "Pas_profil_m": 25,
        "Distance_max_axe_maillage_m": "",
    }
    valeurs.update(parametres or {})
    return valeurs


def _feuille_correspondance(noms_apports, noms_sections, noms_cibles,
                            pentes_existantes, pentes):
    """La feuille Correspondance, pentes reportees ou pre-remplies."""
    import pandas as pd

    n = len(noms_sections)
    # Priorite : saisie precedente, puis pente deduite du profil en long,
    # puis vide. Le pre-remplissage ne doit jamais ecraser une saisie.
    deduites = {str(k): v for k, v in (pentes or {}).items()}
    colonne_pente = [pentes_existantes.get((a, s), deduites.get(a, ""))
                     for a, s in zip(noms_apports, noms_sections)]
    correspondance = pd.DataFrame({
        "Ordre": range(1, n + 1),
        "Nom_Apport (BC line)": list(noms_apports),
        "Nom_Section (reference line)": list(noms_sections),
        "Nom_Cible": noms_cibles,
        # Pente de la ligne d'energie, PAR APPORT : elle depend du troncon, pas
        # du lot. PRE-REMPLIE depuis le profil en long — moyenne sur +/- 200 m
        # autour de l'injection, majoree de 20 % — pour que l'hypothese soit
        # visible et modifiable au lieu d'etre deduite en silence. Deja saisie
        # dans un classeur precedent (couple apport/section identique),
        # PRESERVEE au lieu d'etre effacee par une recomposition.
        "Pente_m_par_m": colonne_pente,
    })
    return correspondance


def _refuser_cibles_illisibles(chemin, cibles_existantes, noms_cibles):
    """Leve ValueError si la feuille Cibles porte une saisie qu'on ne sait
    pas relire : la recomposer l'effacerait."""
    # UNE SAISIE QU'ON NE SAIT PAS RELIRE NE S'EFFACE PAS. Les cibles deja
    # collees sont retrouvees sous l'en-tete « Temps_h » ; sans lui, la
    # branche suivante reecrivait la feuille VIDE, sans un mot — le geste
    # naturel apres le refus d'etat_cibles etant justement de recomposer
    # (04/09/2026, six colonnes de 418 lignes).
    # LA PREUVE SE CHERCHE SOUS LA LIGNE 1, PAS DEDANS. Un premier correctif
    # exigeait un en-tete « Cible_ » non vide — or « Temps_h » et les
    # « Cible_ » vivent dans la MEME ligne : ligne supprimee, triee avec les
    # donnees, ou recouverte par un bloc colle avec ses propres titres, le
    # detecteur partait avec elle. Ce sont les VALEURS de la zone de saisie
    # (le temps puis une colonne par cible, par POSITION) qui disent qu'il y
    # a quelque chose a perdre ; l'apercu des pics est au-dela, intact.
    if cibles_existantes is not None and "Temps_h" not in cibles_existantes.columns:
        zone = cibles_existantes.iloc[:, :1 + len(noms_cibles)]
        if int(zone.notna().sum().sum()) > 0:
            entetes = [str(c) for c in cibles_existantes.columns]
            raise ValueError(
                f"la feuille Cibles de {chemin.name} porte des valeurs "
                f"saisies, mais pas de colonne « Temps_h » (en-tete A1) : "
                f"{_entetes_dits(entetes)}. Recomposer les effacerait. "
                f"Retablir la ligne d'en-tete — « Temps_h », puis une colonne "
                f"par section — puis RELANCER LA COMPOSITION : le classeur "
                f"n'est pas touche, mais la geometrie et les couches viennent "
                f"d'etre reecrites, et la composition s'arrete ici.")


def _feuille_cibles(cibles_existantes, noms_cibles):
    """La feuille Cibles : la saisie precedente reconciliee avec les sections
    courantes, ou une feuille vide."""
    import pandas as pd

    if cibles_existantes is not None and "Temps_h" in cibles_existantes.columns:
        # Meme grille de temps qu'auparavant ; seules les colonnes de section
        # sont reconciliees avec la liste courante.
        cibles = pd.DataFrame({"Temps_h": cibles_existantes["Temps_h"]})
        for nom_cible in noms_cibles:
            cibles[nom_cible] = (cibles_existantes[nom_cible]
                                 if nom_cible in cibles_existantes.columns
                                 else pd.NA)
    else:
        cibles = pd.DataFrame({"Temps_h": []})
        for nom_cible in noms_cibles:
            cibles[nom_cible] = []
    return cibles


def _mettre_de_cote(chemin):
    """Renomme l'ancien classeur en « .precedent.xlsx » ; rend ce nom, ou
    None s'il n'y avait rien a mettre de cote ou si le renommage est refuse."""
    # APRES LE GARDE-FOU Temps_h, PAS AVANT (23/09/2026) : la 0.9.2 mettait
    # l'ancien classeur de cote en tete de fonction ; sur un refus, le
    # fichier canonique avait donc disparu alors que le message promettait
    # « le classeur n'est pas touche ». Le banc ci-dessous le verifie.
    # ET L'ANCIEN CLASSEUR EST MIS DE COTE, JAMAIS ECRASE (20/09/2026,
    # demande utilisateur). Depuis la 0.8.4, deux PREFIXES donnent deux
    # fichiers ; avec le MEME prefixe, recomposer reecrivait le fichier en
    # place. Ce qui compte y survivait — les cibles et les pentes sont
    # relues juste au-dessus et reportees — mais tout le reste partait sans
    # un mot : une feuille ajoutee a la main, une mise en forme, une colonne
    # de travail, un commentaire.
    #   UN SEUL NIVEAU, PAS UN HORODATAGE. La 0.9.2 datait chaque
    # sauvegarde, comme la geometrie : c'etait juste pour un geste RARE, sur
    # un bouton. Depuis le 21/09/2026 la composition est AUTOMATIQUE — une
    # copie datee par frappe enterrerait le dossier de sortie, souvent un
    # partage reseau. On garde donc « ce qui precede », et un seul :
    # c'est la regle deja prise pour le suivi en 0.8.3 —
    # « avancement_precedent.json », un seul niveau d'historique, parce que
    # garder une pile obligerait a choisir laquelle montrer.
    #   LE NOM CANONIQUE NE BOUGE PAS : c'est l'ANCIEN fichier qui change de
    # nom. Renommer le nouveau rendrait imprevisible celui que la chaine
    # lit, et le prefixe existe justement pour que ce nom soit previsible.
    sauvegarde = None
    if chemin.exists():
        sauvegarde = chemin.with_name(chemin.stem + ".precedent"
                                      + chemin.suffix)
        try:
            chemin.replace(sauvegarde)
        except OSError:
            # Un classeur ouvert dans Excel refuse d'etre renomme sous
            # Windows. On ne fait pas echouer la composition pour cela : le
            # geste suivant — l'ecriture — dira lui-meme qu'il ne peut pas.
            sauvegarde = None
    return sauvegarde


def _ecrire_classeur(chemin, correspondance, cibles, valeurs):
    """Ecrit le classeur, puis le JSON des parametres, puis l'habille."""
    import pandas as pd

    # LE CLASSEUR NE PORTE PLUS QUE CE QU'ON Y ECRIT (20 septembre 2026,
    # demande utilisateur) : la correspondance et les cibles. Les parametres
    # partent dans le JSON voisin — voir chaine/parametres.py.
    with pd.ExcelWriter(chemin, engine="openpyxl") as w:
        correspondance.to_excel(w, sheet_name="Correspondance", index=False)
        cibles.to_excel(w, sheet_name="Cibles", index=False)
    import parametres as _parametres
    _parametres.ecrire(chemin, valeurs)

    # MISE EN FORME, jamais bloquante. C'est le classeur qu'on ouvre tous les
    # jours pour y coller des hydrogrammes ; pandas le rendait nu. Mais un
    # classeur mal habille reste exploitable, alors qu'une composition perdue
    # fait recommencer tout le parametrage : si la chaine est introuvable ou
    # openpyxl fache, on garde le classeur tel quel.
    try:
        import style_classeur
        style_classeur.mettre_en_forme(chemin)
    except Exception:                                       # noqa: BLE001
        pass


def preparer_classeur(dossier_sortie, paires, chemins_shp, parametres=None,
                      pentes=None):
    """
    Ecrit le classeur de saisie, PRE-REMPLI a partir de ce qui a ete designe
    dans QGIS : la feuille Correspondance contient deja les noms reels et
    l'ordre, la feuille Cibles deja une colonne par section.

    C'est le point ou le plugin fait gagner le plus de temps : recopier vingt
    noms a la main est long et fautif, alors qu'ils sont deja connus.

    paires : [(nom_apport, nom_section), ...] de l'amont vers l'aval, tel que
        le produit geometrie.apparier_amont_aval(). Ce n'est PLUS deux listes
        de meme longueur : les lignes d'injection d'un modele ne sont pas
        toutes des apports a caler — s'y trouvent aussi les debits d'entree
        permanents et les conditions limites aval. Exiger autant de sections
        que d'injections revenait a compter ces dernieres comme des apports,
        et refusait de composer un paquet pourtant valide.

    Si le classeur EXISTE DEJA, les hydrogrammes cibles deja saisis a la main
    dans la feuille Cibles sont PRESERVES pour les sections qui persistent
    d'une composition a l'autre : recomposer ne doit jamais effacer un
    travail de saisie deja fait. Seules les colonnes des sections retirees
    disparaissent, et les sections nouvelles arrivent vides. La meme regle
    vaut pour la pente saisie par apport (Pente_m_par_m, feuille
    Correspondance) : preservee pour les couples apport/section qui
    persistent, retrouvee par leur NOM (l'ordre peut changer d'une
    composition a l'autre).

    pentes : {nom_apport: pente} deduit du profil en long
        (pentes_locales_apports). Sert a PRE-REMPLIR la colonne
        Pente_m_par_m des apports qui n'en ont pas deja une. Ordre de
        priorite, du plus fort au plus faible : valeur deja saisie dans le
        classeur precedent > pente deduite du profil > case vide. Une saisie
        de l'utilisateur n'est donc JAMAIS ecrasee par une recomposition, et
        une case vide reste possible — c'est le cas ou le profil ne couvre
        pas l'apport, et le calage deduira la pente comme avant.

    Le nom du fichier porte le PREFIXE DE SCENARIO — « donnees_calage_Q100
    .xlsx » : deux scenarios d'un meme dossier de sortie ont deux classeurs,
    et composer l'un n'ecrase pas l'autre. Voir nom_classeur.

    Retourne le chemin du classeur.
    """
    paires = [(str(a), str(s)) for a, s in paires]
    if not paires:
        raise ValueError(
            "aucun apport à caler : aucune section de contrôle n'a de ligne "
            "d'injection en amont d'elle. Vérifier le tracé de l'axe "
            "hydraulique et la position des objets.")
    noms_apports = [a for a, _ in paires]
    noms_sections = [s for _, s in paires]

    dossier = Path(dossier_sortie)
    dossier.mkdir(parents=True, exist_ok=True)
    # LE NOM PORTE LE PREFIXE DE SCENARIO (0.8.4) — voir nom_classeur. Le
    # prefixe est lu dans les parametres, la ou le lancement le relira : un
    # second argument le laisserait diverger de ce que le classeur declare.
    chemin = dossier / nom_classeur((parametres or {}).get("Prefixe_scenario"))

    # Cibles et pentes deja saisies dans un classeur precedent, a preserver.
    cibles_existantes, pentes_existantes = _saisie_a_preserver(chemin)
    valeurs = _parametres_du_classeur(chemins_shp, parametres)

    noms_cibles = [f"Cible_{s}" for s in noms_sections]
    correspondance = _feuille_correspondance(
        noms_apports, noms_sections, noms_cibles, pentes_existantes, pentes)

    # LE GARDE-FOU D'ABORD, LA MISE DE COTE ENSUITE, L'ECRITURE ENFIN : un
    # refus ne doit rien avoir deplace (defaut de la 0.9.2, corrige en
    # 0.9.12 — voir _mettre_de_cote).
    _refuser_cibles_illisibles(chemin, cibles_existantes, noms_cibles)
    cibles = _feuille_cibles(cibles_existantes, noms_cibles)
    _mettre_de_cote(chemin)
    _ecrire_classeur(chemin, correspondance, cibles, valeurs)
    return chemin


# LES DEUX ETATS MACHINE QUE suivi.py ECRIT dans le dossier de suivi :
# celui du calage en cours, et celui du calage PRECEDENT, archive par
# renommage au demarrage du suivant. Jumeaux de suivi.ETAT_COURANT et
# suivi.ETAT_PRECEDENT — le Python de QGIS ne peut pas importer la chaine
# (h5py, ras-commander), et toute correction va donc aux deux, comme pour
# hecras_ouvert.
ETAT_SUIVI_COURANT = "avancement.json"
ETAT_SUIVI_PRECEDENT = "avancement_precedent.json"


def lire_avancement(dossier_suivi, nom=ETAT_SUIVI_COURANT):
    """
    Etat courant du calage, tel que suivi.py le reecrit a chaque essai.

    « nom » vaut ETAT_SUIVI_PRECEDENT pour relire le calage d'avant, que
    suivi.py archive au lieu de l'ecraser : c'est ce qui permet a
    l'onglet Suivi de garder a l'ecran les apports qu'une reprise
    conserve.

    Retourne None si aucun calage n'a encore ecrit dans ce dossier — ce n'est
    pas une erreur, c'est l'etat normal avant le lancement.

    La lecture ne leve JAMAIS : le fichier est reecrit pendant qu'on le lit.
    L'ecriture est atomique du cote de suivi.py, mais un antivirus ou un
    partage reseau peuvent malgre tout rendre un instantane illisible ; dans
    ce cas on garde simplement l'affichage precedent.
    """
    chemin = Path(dossier_suivi) / nom
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def avancement_illisible(dossier_suivi, nom=ETAT_SUIVI_COURANT):
    """
    L'etat du calage EXISTE-T-IL sans pouvoir etre lu ? lire_avancement()
    rend None aussi bien pour « aucun calage n'a encore ecrit » que pour « le
    fichier est la, illisible a cet instant », et l'onglet Suivi ne doit pas
    traiter les deux de la meme facon : le premier remet l'ecran a zero, le
    second garde l'affichage precedent (11/11/2026).

    Ne leve jamais.
    """
    try:
        present = (Path(dossier_suivi) / nom).exists()
    except OSError:
        return False
    return present and lire_avancement(dossier_suivi, nom) is None


def processus_vivant(pid):
    """
    Le processus existe-t-il encore ? None si on ne sait pas dire.

    C'EST CE QUI DISTINGUE UN CALAGE QUI TOURNE D'UN CALAGE MORT. Un calage
    interrompu — plantage, session fermee, machine arretee — cesse simplement
    de reecrire ses fichiers : sans cette verification, l'affichage resterait
    fige sur le dernier etat connu en laissant croire que le calcul avance.
    """
    if not pid:
        return None
    try:
        # tasklist ecrit dans la page de codes OEM de la console, pas en UTF-8 :
        # un nom de processus accentue suffit a faire echouer le decodage, et
        # avec lui la seule chose qui distingue un calage vivant d'un calage
        # mort. Le PID recherche, lui, est en ASCII — remplacer les octets
        # indecodables ne peut donc pas fausser la reponse.
        sortie = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
            capture_output=True, text=True, errors="replace", timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return str(pid) in (sortie.stdout or "")


def _entetes_dits(entetes, maximum=12):
    """
    Les en-tetes trouves, pour un message d'erreur — BORNES. Une feuille dont
    la ligne 1 a recu un hydrogramme colle en travers en porte des centaines,
    et le message part tel quel dans une boite de dialogue (mesure : 3 431
    caracteres sur une ligne).
    """
    entetes = [str(e) for e in entetes]
    if len(entetes) <= maximum:
        return str(entetes)
    return f"{entetes[:maximum]} … et {len(entetes) - maximum} autres"


def etat_cibles(chemin_classeur):
    """
    Combien d'hydrogrammes cibles restent a saisir dans le classeur : c'est
    l'information qui guide l'etape suivante — completer la feuille Cibles —
    avant de lancer le calage.

    Une cible est RENSEIGNEE quand elle est exploitable au sens du pont
    (_cibles_depuis_classeur) : au moins deux instants numeriques de Temps_h
    en face de deux debits numeriques. « Au moins une valeur non vide »
    laissait partir un classeur aux six colonnes de debit pleines et a la
    colonne de temps vide (04/09/2026) — refuse ensuite en arriere-plan.
    controle_donnees.py verifie separement qu'un hydrogramme partiel ou
    incoherent est signale.

    Retourne {"total", "renseignees", "manquantes": [noms de section]}.
    """
    import pandas as pd

    corr = pd.read_excel(chemin_classeur, sheet_name="Correspondance")
    cibles = pd.read_excel(chemin_classeur, sheet_name="Cibles")
    col_section = next(c for c in corr.columns if c.startswith("Nom_Section"))
    col_cible = next(c for c in corr.columns if c.startswith("Nom_Cible"))

    # LA COLONNE DU TEMPS D'ABORD : le plugin appelle cette fonction juste
    # avant de lancer le calage. Sans « Temps_h » en A1 le pont plantait en
    # arriere-plan, hors de vue (04/09/2026). Refuser ici, en nommant l'en-tete
    # trouve a la place — c'est lui qu'il faut corriger.
    if "Temps_h" not in cibles.columns:
        raise ValueError(
            f"La feuille Cibles n'a pas de colonne « Temps_h » (en-tête A1). "
            f"En-têtes trouvés : {_entetes_dits(cibles.columns)}. Le calage "
            f"n'est pas lancé.")

    # DES DATES NE SONT PAS DES HEURES. pd.to_numeric ne rend NaN que sur du
    # texte : sur une colonne de DATES il rend les microsecondes depuis 1970,
    # le compte « deux instants » etait satisfait, et le pont mourait plus
    # loin sur une allocation de 536 Gio (relecture adverse du 04/09/2026).
    if pd.api.types.is_datetime64_any_dtype(cibles["Temps_h"]):
        raise ValueError(
            "La colonne « Temps_h » de la feuille Cibles contient des DATES. "
            "Le calage attend des heures décimales comptées depuis le début "
            "de la simulation (0 ; 0,5 ; 1 …). Le calage n'est pas lancé.")

    temps_ok = pd.to_numeric(cibles["Temps_h"], errors="coerce").notna()
    manquantes = []
    for _, ligne in corr.dropna(subset=[col_section, col_cible]).iterrows():
        nom_cible = str(ligne[col_cible])
        renseignee = (
            nom_cible in cibles.columns
            and int((temps_ok & pd.to_numeric(cibles[nom_cible], errors="coerce"
                                              ).notna()).sum()) >= 2)
        if not renseignee:
            manquantes.append(str(ligne[col_section]))

    total = len(corr.dropna(subset=[col_section, col_cible]))
    return {"total": total, "renseignees": total - len(manquantes),
            "manquantes": manquantes}


def resume_cibles(chemin_classeur):
    """
    Debit de pointe et volume de chaque hydrogramme cible, dans l'ordre du
    classeur : [{"apport", "section", "cible", "pic_m3s", "volume_hm3",
    "heure_pic_h", "renseignee"}, ...].

    POURQUOI A L'ECRAN, ET DES LA VALIDATION DE L'EXCEL. La feuille Cibles ne
    dit rien de ce qu'on y a colle : douze colonnes de nombres, dont on ne
    sait ni l'ordre de grandeur ni si l'une porte une unite etrangere aux
    autres. Un pic et un volume par section se lisent d'un coup d'oeil, et
    une cible collee dans la mauvaise colonne, un facteur 1000, ou une serie
    restee vide s'y voient AVANT les heures de calcul — pas au verdict.

    LE VOLUME EST INTEGRE A LA REGLE DES TRAPEZES sur la colonne Temps_h, en
    hm3 (m3/s x h x 3600 / 1e6). Les couples (temps, debit) non numeriques
    sont ecartes des deux series ensemble : integrer une serie de debits sur
    une base de temps trouee rendrait un nombre qui ne veut rien dire.

    Une cible non exploitable — moins de deux couples numeriques, meme regle
    que etat_cibles — est rendue avec "renseignee": False et des valeurs
    None. Elle n'est pas une erreur ici : c'est l'etat normal d'un classeur
    qu'on vient de composer et qu'il reste a remplir.
    """
    import pandas as pd

    corr = pd.read_excel(chemin_classeur, sheet_name="Correspondance")
    cibles = pd.read_excel(chemin_classeur, sheet_name="Cibles")
    col_apport = next(c for c in corr.columns if c.startswith("Nom_Apport"))
    col_section = next(c for c in corr.columns if c.startswith("Nom_Section"))
    col_cible = next(c for c in corr.columns if c.startswith("Nom_Cible"))

    # MEMES REFUS QUE etat_cibles, ET POUR LES MEMES RAISONS : sans colonne
    # Temps_h il n'y a pas de base de temps, et une colonne de DATES rend des
    # microsecondes depuis 1970 la ou on attend des heures.
    if "Temps_h" not in cibles.columns:
        raise ValueError(
            f"la feuille Cibles n'a pas de colonne « Temps_h » (en-tete A1). "
            f"En-tetes trouves : {_entetes_dits(cibles.columns)}.")
    if pd.api.types.is_datetime64_any_dtype(cibles["Temps_h"]):
        raise ValueError(
            "La colonne « Temps_h » de la feuille Cibles contient des DATES. "
            "Le calage attend des heures décimales comptées depuis le début "
            "de la simulation (0 ; 0,5 ; 1 …).")

    temps = pd.to_numeric(cibles["Temps_h"], errors="coerce")
    resume = []
    for _, ligne in corr.dropna(subset=[col_section, col_cible]).iterrows():
        nom_cible = str(ligne[col_cible])
        entree = {"apport": str(ligne[col_apport]),
                  "section": str(ligne[col_section]),
                  "cible": nom_cible,
                  "pic_m3s": None, "volume_hm3": None, "heure_pic_h": None,
                  "renseignee": False}
        if nom_cible in cibles.columns:
            debit = pd.to_numeric(cibles[nom_cible], errors="coerce")
            garde = temps.notna() & debit.notna()
            if int(garde.sum()) >= 2:
                t_ok = temps[garde].to_numpy(dtype=float)
                q_ok = debit[garde].to_numpy(dtype=float)
                ordre = t_ok.argsort()
                t_ok, q_ok = t_ok[ordre], q_ok[ordre]
                # Trapezes a la main : numpy est deja la (pandas en depend),
                # mais son nom de fonction a change de version en version
                # (trapz, puis trapezoid) — et ce module tourne sous le Python
                # de QGIS comme sous celui de HEC-RAS.
                aires = (q_ok[1:] + q_ok[:-1]) / 2.0 * (t_ok[1:] - t_ok[:-1])
                entree.update(
                    pic_m3s=float(q_ok.max()),
                    heure_pic_h=float(t_ok[int(q_ok.argmax())]),
                    volume_hm3=float(aires.sum()) * 3600.0 / 1e6,
                    renseignee=True)
        resume.append(entree)
    return resume


def hecras_ouvert():
    """
    HEC-RAS tourne-t-il ? Retourne True, False, ou None si on ne sait pas.

    JUMEAU DE pilote_hecras.hecras_ouvert, ET IL FAUT LES DEUX. Celui-la est
    lu par la CHAINE, qui tourne sous l'interpreteur HEC-RAS ; celui-ci par le
    PLUGIN, sous le Python de QGIS, qui ne peut pas importer pilote_hecras —
    il exige h5py et ras-commander. C'est la meme raison qui a triplique la
    politique d'encodage (STATUT.txt § 2.11) : deux modules qui ne peuvent
    pas partager de code. Toute correction va aux deux.

    POURQUOI LE PLUGIN LE DEMANDE AUSSI. La chaine l'ecrit dans son journal
    de lancement — que personne ne lit pendant qu'un calcul demarre. Le
    09/09/2026, un calage est parti avec l'interface ouverte et s'est arrete
    218 s plus tard sur un calcul de reference sans resultats. L'avertissement
    etait dans le journal, a la ligne 15.

    CE QUE L'INTERFACE OUVERTE FAIT : elle reecrit les fichiers du projet
    depuis sa memoire, par-dessus ce que la chaine vient d'y ecrire — et le
    chien de garde de ras-commander repond « Oui » a sa boite « Save Edits ».
    """
    import subprocess

    try:
        sortie = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Ras.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None          # pas Windows, ou tasklist indisponible
    return "Ras.exe" in (sortie.stdout or "")


def apports_du_classeur(chemin_classeur):
    """
    Apports a caler, dans l'ordre : [(nom_apport, nom_section), ...].

    Lu du classeur et non de l'appariement en memoire : c'est le classeur qui
    fait foi au lancement, y compris quand il a ete rouvert d'un calcul
    precedent sans passer par une composition.
    """
    import pandas as pd

    corr = pd.read_excel(chemin_classeur, sheet_name="Correspondance")
    col_apport = next(c for c in corr.columns if c.startswith("Nom_Apport"))
    col_section = next(c for c in corr.columns if c.startswith("Nom_Section"))
    return [(str(l[col_apport]), str(l[col_section]))
            for _, l in corr.dropna(subset=[col_apport, col_section]).iterrows()]


def lire_parametres(chemin_classeur):
    """
    Feuille Parametres d'un classeur, en dictionnaire {cle: valeur}.

    Les valeurs vides d'Excel arrivent en NaN chez pandas : elles sont
    rendues None, pour qu'un appelant puisse ecrire « if valeur is None »
    sans importer pandas.

    SERT A REMPLIR LA FENETRE DEPUIS UN CLASSEUR REPRIS. Sans elle, « Reprendre
    un classeur d'un calcul precedent… » laissait les objectifs de precision
    sur les valeurs par defaut de la fenetre : reprendre un classeur cale a
    +/-2 % puis lancer l'aurait DESSERRE a 5 % sans un mot, des lors que le
    lancement reecrit ces parametres (voir plugin, _lancer_calage).

    DEPUIS LE 20 SEPTEMBRE 2026, LES PARAMETRES NE SONT PLUS UNE FEUILLE du
    classeur mais un JSON a cote (chaine, parametres.py) : personne ne les
    saisissait a la main, et la feuille etait la premiere chose vue en
    ouvrant un classeur ou l'on ne vient que coller des hydrogrammes. Les
    classeurs d'avant sont encore lus par leur feuille — c'est parametres.py
    qui porte cette compatibilite, et lui seul.
    """
    import parametres

    return parametres.lire(chemin_classeur)


def ecrire_parametre(chemin_classeur, cle, valeur):
    """
    Ecrit une valeur dans la feuille Parametres d'un classeur existant.

    Sert aux reglages qui se decident AU LANCEMENT et non a la composition —
    « Premier_apport » en premier lieu : choisir par ou reprendre ne doit pas
    obliger a recomposer tout le paquet.

    LE CLASSEUR N'EST PLUS TOUCHE (20 septembre 2026) : les parametres vivent
    dans le JSON voisin. On y gagne ce que la reecriture openpyxl coutait —
    ouvrir, modifier et resauvegarder un classeur de plusieurs milliers de
    lignes de cibles pour changer un seul mot, sur un partage reseau.
    """
    import parametres

    return parametres.ecrire_un(chemin_classeur, cle, valeur)


def prolonger_cibles(chemin_classeur, duree_h):
    """
    Prolonge les hydrogrammes cibles jusqu'a duree_h, EN COMPLETANT PAR DES
    ZEROS. Retourne {"ajoutees", "duree_avant_h", "duree_apres_h", "colonnes"}.

    POURQUOI ZERO ET NON LA DERNIERE VALEUR. Une cible qui s'arrete avant la
    fin de la simulation decrit une crue DEJA RETOMBEE : zero est la mesure,
    pas une commodite. Prolonger a la derniere valeur connue — ce que fait
    np.interp quand on le laisse faire (invariant 8) — fabriquerait un debit
    que personne n'a mesure, et le calage passerait ses essais a le combler.

    POURQUOI CETTE FONCTION EXISTE. HEC-RAS refuse de calculer si une serie
    s'arrete avant la fin de la simulation (« Time series data ends before
    the end of the simulation »). Le pre-vol le dit desormais avant tout
    lancement ; il fallait encore le corriger a la main, colonne par colonne,
    dans Excel.

    LE PAS EST CELUI DE LA SAISIE, repris des deux dernieres lignes. Il n'est
    pas impose : une cible au quart d'heure reste au quart d'heure, et c'est
    la chaine qui la densifiera si besoin (criteres.normaliser_entree).

    N'ECRIT RIEN SI LA CIBLE COUVRE DEJA LA DUREE. openpyxl modifie les
    cellules sur place : styles, graphique et tableau des pics de la feuille
    Cibles sont conserves.
    """
    import openpyxl

    classeur = openpyxl.load_workbook(chemin_classeur)
    feuille = classeur["Cibles"]

    entetes = [c.value for c in feuille[1]]
    try:
        col_temps = entetes.index("Temps_h") + 1
    except ValueError:
        raise ValueError("la feuille Cibles n'a pas de colonne « Temps_h ».")
    # LES COLONNES DE SAISIE SEULEMENT. La feuille porte aussi, a distance, un
    # graphique et un tableau des debits de pointe (style_classeur.
    # _ajouter_apercu_cibles) : y ecrire des zeros abimerait l'apercu.
    colonnes = [i + 1 for i, e in enumerate(entetes)
                if isinstance(e, str) and e.startswith("Cible_")]

    temps = []
    for ligne in range(2, feuille.max_row + 1):
        valeur = feuille.cell(row=ligne, column=col_temps).value
        if isinstance(valeur, (int, float)):
            temps.append((ligne, float(valeur)))
    if len(temps) < 2:
        raise ValueError("La feuille Cibles porte moins de deux instants : "
                         "le pas de temps n'est pas déductible.")

    derniere_ligne, derniere_h = temps[-1]
    pas_h = temps[-1][1] - temps[-2][1]
    if pas_h <= 0:
        raise ValueError(f"pas de temps non croissant en fin de saisie "
                         f"({pas_h:g} h) : corriger la colonne Temps_h.")

    ajoutees = 0
    instant, ligne = derniere_h, derniere_ligne
    # TOLERANCE D'UN CENTIEME DE PAS : une cible qui finit pile a la fin de la
    # simulation ne doit pas gagner une ligne pour une erreur d'arrondi.
    while instant < duree_h - pas_h * 1e-2:
        instant += pas_h
        ligne += 1
        ajoutees += 1
        feuille.cell(row=ligne, column=col_temps, value=round(instant, 6))
        for colonne in colonnes:
            feuille.cell(row=ligne, column=colonne, value=0.0)

    if ajoutees:
        classeur.save(chemin_classeur)
    return {"ajoutees": ajoutees, "duree_avant_h": derniere_h,
            "duree_apres_h": instant, "pas_h": pas_h,
            "colonnes": [entetes[c - 1] for c in colonnes]}


def _colonnes_entete(feuille):
    """{en-tete: numero de colonne} de la ligne 1 d'une feuille."""
    # JUSQU'AU PREMIER EN-TETE VIDE : au-dela vivent le tableau des pics
    # et le graphique (style_classeur._ajouter_apercu_cibles).
    rangs = {}
    for cellule in feuille[1]:
        if cellule.value is None or str(cellule.value).strip() == "":
            break
        rangs[str(cellule.value).strip()] = cellule.column
    return rangs


def _valeurs_colonne(feuille, colonne):
    """Les valeurs d'une colonne sous l'en-tete, sans les vides de fin."""
    serie = [feuille.cell(row=ligne, column=colonne).value
             for ligne in range(2, feuille.max_row + 1)]
    while serie and serie[-1] in (None, ""):
        serie.pop()
    return serie


def _verifier_excels_objectifs(source, lu, cible, ecrit):
    """Leve ValueError si l'un des deux classeurs n'a pas les feuilles d'un
    Excel des objectifs."""
    for fichier, classeur in ((source, lu), (cible, ecrit)):
        absentes = [f for f in ("Correspondance", "Cibles")
                    if f not in classeur.sheetnames]
        if absentes:
            raise ValueError(
                f"{fichier.name} n’a pas de feuille « "
                f"{' » ni « '.join(absentes)} » : ce n’est pas un Excel des "
                f"hydrogrammes objectifs.")


def _verifier_temps_h(source, cols_src, cible, cols_dst):
    """Leve ValueError si une feuille Cibles n'a pas de colonne Temps_h."""
    for fichier, cols in ((source, cols_src), (cible, cols_dst)):
        if "Temps_h" not in cols:
            raise ValueError(f"la feuille Cibles de {fichier.name} n’a pas de "
                             f"colonne « Temps_h ».")


def _cibles_communes(source, src, cols_src, cols_dst):
    """(attendues, portees, importees) ; leve ValueError si aucune cible de
    ce calcul n'est renseignee dans la source."""
    attendues = [e for e in cols_dst if e.startswith("Cible_")]
    portees = [e for e in cols_src
               if e.startswith("Cible_") and _valeurs_colonne(src, cols_src[e])]
    importees = [e for e in attendues if e in portees]
    if not importees:
        raise ValueError(
            f"aucun hydrogramme de {source.name} ne correspond aux cibles de "
            f"ce calcul. Attendues : {_entetes_dits(attendues)}. Dans l’Excel "
            f"importé : " + (_entetes_dits(portees) if portees else
                             "aucune colonne « Cible_… » renseignée") + ".")
    return attendues, portees, importees


def _refuser_autre_base_de_temps(source, gardees, temps, dst, cols_dst):
    """Leve ValueError si des colonnes deja saisies dans ce calcul le sont
    sur une autre base de temps : l'import changerait Temps_h sous elles."""
    if gardees and _valeurs_colonne(dst, cols_dst["Temps_h"]) != temps:
        raise ValueError(
            f"{', '.join(gardees)} {'porte' if len(gardees) < 2 else 'portent'} déjà des valeurs, sur une autre "
            f"base de temps que {source.name} : l’import changerait la colonne "
            f"Temps_h sous elles. Les vider dans l’Excel de ce calcul, ou les "
            f"ajouter à l’Excel importé, puis recommencer.")


def _recopier_cibles(src, dst, cols_src, cols_dst, temps, importees):
    """Ecrit Temps_h et les cibles importees, SUR PLACE ; les lignes de la
    cible au-dela de la source sont videes."""
    hauteur = max(len(temps), dst.max_row - 1)
    for entete in ["Temps_h"] + importees:
        serie = (temps if entete == "Temps_h"
                 else _valeurs_colonne(src, cols_src[entete]))
        for i in range(hauteur):
            dst.cell(row=i + 2, column=cols_dst[entete],
                     value=serie[i] if i < len(serie) else None)


def _recopier_pentes(f_src, f_dst):
    """Reporte, par nom d'apport, les pentes de la source ; rend les apports
    servis."""
    pentes = []
    apport, pente = "Nom_Apport (BC line)", "Pente_m_par_m"
    c_src, c_dst = _colonnes_entete(f_src), _colonnes_entete(f_dst)
    if {apport, pente} <= set(c_src) and {apport, pente} <= set(c_dst):
        lues = {}
        for ligne in range(2, f_src.max_row + 1):
            nom = f_src.cell(row=ligne, column=c_src[apport]).value
            valeur = f_src.cell(row=ligne, column=c_src[pente]).value
            if nom not in (None, "") and valeur not in (None, ""):
                lues[str(nom).strip()] = valeur
        for ligne in range(2, f_dst.max_row + 1):
            nom = str(f_dst.cell(row=ligne, column=c_dst[apport]).value
                      or "").strip()
            if nom in lues:
                f_dst.cell(row=ligne, column=c_dst[pente], value=lues[nom])
                pentes.append(nom)
    return pentes


def importer_hydrogrammes(source, cible):
    """
    Recopie dans l'Excel de CE calcul (`cible`) les hydrogrammes cibles et les
    pentes des apports d'un Excel d'un calcul precedent (`source`). Rien
    d'autre : ni les parametres (le JSON voisin), ni la correspondance, ni le
    classeur que la fenetre suit (24/09/2026, demande utilisateur — ce geste
    remplace « Reprendre un Excel… », qui faisait de la source le classeur de
    la fenetre, rejouait les controles et reprenait ses reglages).

    PAR EN-TETE : chaque colonne « Cible_<section> » de la cible prend celle
    de meme en-tete dans la source, avec la colonne Temps_h. PAR NOM
    D'APPORT : la pente « Pente_m_par_m » d'un apport de la source rejoint
    l'apport de meme nom. Une colonne sans correspondance n'est pas touchee.

    SUR PLACE, comme prolonger_cibles : styles, graphique et tableau des pics
    de la feuille Cibles sont conserves. L'Excel d'avant est garde sous
    « <nom>.precedent.xlsx », le niveau unique de la composition.

    REFUSE SANS RIEN ECRIRE (ValueError) : un fichier qui n'est pas un Excel
    des objectifs, l'Excel de ce calcul lui-meme, aucune cible en commun, ou
    des colonnes deja saisies sur une AUTRE base de temps — l'import
    changerait Temps_h sous elles.

    Rend {"importees", "vides", "gardees", "ignorees", "pentes",
    "sauvegarde"}.
    """
    import openpyxl

    source, cible = Path(source), Path(cible)
    if source.resolve() == cible.resolve():
        raise ValueError(f"{source.name} est déjà l’Excel de ce calcul.")
    lu = openpyxl.load_workbook(source, data_only=True)
    ecrit = openpyxl.load_workbook(cible)
    _verifier_excels_objectifs(source, lu, cible, ecrit)

    src, dst = lu["Cibles"], ecrit["Cibles"]
    cols_src, cols_dst = _colonnes_entete(src), _colonnes_entete(dst)
    _verifier_temps_h(source, cols_src, cible, cols_dst)
    attendues, portees, importees = _cibles_communes(source, src, cols_src,
                                                     cols_dst)
    restantes = [e for e in attendues if e not in importees]
    gardees = [e for e in restantes if _valeurs_colonne(dst, cols_dst[e])]
    temps = _valeurs_colonne(src, cols_src["Temps_h"])
    _refuser_autre_base_de_temps(source, gardees, temps, dst, cols_dst)

    # L'EXCEL D'AVANT EST MIS DE COTE AVANT TOUTE ECRITURE, apres le dernier
    # refus : un refus ne laisse aucune copie.
    sauvegarde = cible.with_name(cible.stem + ".precedent" + cible.suffix)
    shutil.copy2(cible, sauvegarde)
    _recopier_cibles(src, dst, cols_src, cols_dst, temps, importees)
    pentes = _recopier_pentes(lu["Correspondance"], ecrit["Correspondance"])
    ecrit.save(cible)
    return {"importees": importees,
            "vides": [e for e in restantes if e not in gardees],
            "gardees": gardees,
            "ignorees": [e for e in portees if e not in attendues],
            "pentes": pentes, "sauvegarde": str(sauvegarde)}


def controler_paquet(chemin_classeur):
    """
    Controle complet du paquet : saisie, chaine geographique, PK et ordre,
    puis — si un modele est joignable — confrontation a la geometrie reelle.

    Delegue integralement a controle_donnees.py : aucune regle n'est
    reimplementee ici. Le controle contre le modele passe par le pont, car il
    exige ras-commander, inutilisable dans le processus QGIS.

    Retourne (anomalies, tableau_pk, prolongation), ou prolongation vaut None
    ou {"duree_h", "apports"} : de quoi PROPOSER a l'utilisateur de prolonger
    ses hydrogrammes cibles (prolonger_cibles) au lieu de lui decrire le
    geste. Le chiffre est celui qu'a MESURE le pont, jamais une relecture du
    message d'anomalie — un texte se reformule, un contrat non.
    """
    import controle_donnees as cd

    anomalies = cd.controler_template(chemin_classeur)
    geo_anomalies, tableau = cd.controler_geometrie(chemin_classeur)
    anomalies += geo_anomalies

    prolongation = None
    try:
        reponse = appeler_pont("controler-modele", "--template",
                               chemin_classeur)
        anomalies += [(cd.ERREUR, m) for m in reponse.get("erreurs", [])]
        anomalies += [(cd.AVERTISSEMENT, m)
                      for m in reponse.get("avertissements", [])]
        prolongation = reponse.get("prolongation")
    except Exception as e:
        anomalies.append((
            cd.AVERTISSEMENT,
            f"controle contre le modele non effectue : {e}"))

    return anomalies, tableau, prolongation


def chemins_du_classeur(chemin_classeur):
    """
    Chemins des shapefiles et sens de l'axe, relus DANS le classeur.

    Le plugin doit pouvoir controler un paquet compose lors d'une session
    precedente : se fier a ce qui est en memoire priverait l'utilisateur de la
    couche des PK des qu'il rouvre QGIS.
    """
    valeurs = lire_parametres(chemin_classeur)

    def chemin(cle):
        v = valeurs.get(cle)
        if v is None or not str(v).strip():
            return None
        p = Path(str(v))
        return p if p.exists() else None

    return {
        "sections": chemin("Fichier_SHP_Sections"),
        "apports": chemin("Fichier_SHP_Apports"),
        "axe": chemin("Fichier_SHP_Axe"),
        "sens": str(valeurs.get("Sens_axe", "amont_aval") or "amont_aval").strip(),
    }


def dossier_suivi_du_classeur(chemin_classeur):
    """
    Dossier ou le calage lance sur ce classeur ecrit son suivi.

    LA MEME REGLE QUE LE PONT, et aucune autre : « Dossier_sortie » des
    parametres du calage, sinon le dossier du classeur ; puis
    « Sous_dossier_suivi », sinon « suivi » (pont_hecras, commande caler).

    C'est ce que l'onglet de suivi doit regarder. Le classeur dit ou le
    calage ecrit ; l'onglet 3 de la fenetre ne dit que ou COMPOSER le
    prochain paquet — et les deux divergent des qu'on reprend le classeur
    d'un calcul precedent.
    """
    chemin_classeur = Path(chemin_classeur)
    valeurs = lire_parametres(chemin_classeur)

    def texte(cle, defaut=""):
        v = valeurs.get(cle)
        return defaut if v is None else str(v).strip()

    racine = Path(texte("Dossier_sortie") or chemin_classeur.parent)
    return racine / texte("Sous_dossier_suivi", "suivi")


def pk_pour_affichage(chemin_shp_lignes, chemin_shp_axe, sens="amont_aval"):
    """
    Calcule les PK d'une couche pour les afficher dans QGIS. C'est ce que le
    plugin apporte de specifique : le PK devient un attribut visible sur la
    carte, et une incoherence d'ordre se voit a l'endroit ou elle est.

    Retourne un GeoDataFrame avec 'nom', 'pk_m', 'croise_axe'.
    """
    import geometrie as geo

    axe, _ = geo.lire_axe(chemin_shp_axe)
    lignes = geo.lire_lignes(chemin_shp_lignes)
    return geo.calculer_pk(lignes, axe, sens=sens)


# ---------------------------------------------------------------------------
# OPERATIONS HEC-RAS COURTES  (pilotables depuis QGIS sans figer l'interface)
# ---------------------------------------------------------------------------
#
# Les calculs longs ne passent PAS par ici : un calage represente des heures
# et bloquerait l'interface. Seules les operations de quelques secondes sont
# exposees — lire un hydrogramme, creer une ligne.

def creer_sections_dans_modele(fichier_geometrie, chemin_shp, nom_zone_2d,
                               remplacer=False):
    """
    Cree des reference lines dans la geometrie HEC-RAS depuis un shapefile.
    Une sauvegarde horodatee du fichier geometrie est faite au prealable : on
    ecrit dans un projet d'etude, l'operation doit rester reversible.

    remplacer : une section DEJA presente sous ce nom est RETRACEE (bloc
    retire puis reinsere) plutot qu'ignoree. Meme convention que
    creer_injections_dans_modele.
    """
    arguments = ["sections", "--geometrie", fichier_geometrie,
                "--shp", chemin_shp, "--zone", nom_zone_2d]
    if remplacer:
        arguments.append("--remplacer")
    return appeler_pont(*arguments)


def creer_injections_dans_modele(fichier_geometrie, chemin_shp, nom_zone_2d,
                                 remplacer=False, fichier_unsteady=None,
                                 forme_depuis=None, pente=0.01):
    """
    Cree des BC lines dans la geometrie HEC-RAS ET, si fichier_unsteady est
    fourni, la condition limite qui leur donne un hydrogramme.

    LES DEUX ECRITURES SONT NECESSAIRES : une BC line presente dans la seule
    geometrie n'apporte AUCUN debit, faute d'hydrogramme. Le calage la
    mettrait a l'echelle sans le moindre effet et conclurait a une stagnation
    apres avoir epuise ses essais. Le pont le signale explicitement lorsque
    l'unsteady n'est pas fourni.

    forme_depuis : nom d'une condition limite existante dont on recopie la
        forme. Intervalle et nombre de valeurs sont alors coherents avec le
        modele par construction — le calage n'a qu'a mettre a l'echelle.

    Meme precaution de sauvegarde horodatee, sur les deux fichiers.
    """
    arguments = ["injections", "--geometrie", fichier_geometrie,
                 "--shp", chemin_shp, "--zone", nom_zone_2d]
    if remplacer:
        arguments.append("--remplacer")
    if fichier_unsteady:
        arguments += ["--unsteady", fichier_unsteady, "--pente", str(pente)]
        if forme_depuis:
            arguments += ["--forme-depuis", forme_depuis]
    return appeler_pont(*arguments)


def _lire_texte_hecras(chemin):
    """
    Lit un fichier texte HEC-RAS en essayant plusieurs encodages. Aucune
    dependance a ras-commander : cette fonction tourne directement dans le
    processus QGIS.

    UTF-8 STRICT, PUIS cp1252, PUIS latin-1 — DANS CET ORDRE. HEC-RAS ecrit
    en cp1252. latin-1 lit tout octet et ne peut pas echouer : place avant
    cp1252, comme il l'etait ici (l'ordre de ras-commander), cp1252 n'etait
    jamais atteint, et un titre portant un tiret long (0x97) ou « œ » (0x9C)
    s'affichait avec des caracteres de controle.

    Meme politique que pilote_hecras._lire_texte et elaguer_projet._lire_texte.
    Ces trois modules ne peuvent PAS partager de code : le plugin est livre
    seul dans son zip et doit fonctionner avant meme que la chaine soit
    localisee. La duplication est assumee ; toute correction ici doit etre
    reportee aux deux autres.
    """
    chemin = Path(chemin)
    for encodage in ("utf-8", "cp1252"):
        try:
            return chemin.read_text(encoding=encodage)
        except (UnicodeDecodeError, LookupError):
            continue
    return chemin.read_text(encoding="latin-1")


def _normaliser_version(brute):
    """
    Convertit une version telle qu'ecrite dans les fichiers HEC-RAS vers la
    forme utilisee par les dossiers d'installation.

    Les fichiers ecrivent « 7.01 », « 6.41 », « 6.50 » : la partie apres le
    point porte DEUX niveaux, mineur et correctif. « 7.01 » vaut donc 7.0.1,
    et non 7.1. Un correctif nul est omis, comme le fait l'installateur :
    « 6.50 » -> « 6.5 ».
    """
    correspondance = re.match(r"\s*(\d+)\.(\d)(\d)?\s*$", str(brute))
    if not correspondance:
        return str(brute).strip()
    majeur, mineur, correctif = correspondance.groups()
    if correctif in (None, "0"):
        return f"{majeur}.{mineur}"
    return f"{majeur}.{mineur}.{correctif}"


def version_hecras_du_projet(projet):
    """
    Lit la version de HEC-RAS dans les fichiers du projet, plutot que de la
    faire saisir : elle y est deja, et une saisie manuelle ne peut
    qu'introduire une erreur.

    La ligne « Program Version= » figure dans les fichiers de geometrie, de
    plan et d'unsteady — chacun portant la version qui l'a ECRIT EN DERNIER.
    Un projet ancien repris avec une version recente en contient donc
    plusieurs : sur le modele d'essai, 6.41 dans 57 fichiers, 6.50 dans 5 et
    7.01 dans 2. On retient LA PLUS RECENTE, seule capable de relire toutes
    les autres.

    projet : le .prj designe — seuls SES fichiers sont lus. Le plugin
    passait le dossier, et tous ses fichiers etaient lus : dans un dossier a
    deux projets, la version de l'autre pouvait l'emporter (audit du
    11/10/2026). Un dossier reste accepte, avec ce comportement.

    Retourne (version, detail) ou detail liste ce qui a ete trouve. Retourne
    (None, ...) si aucune version n'est lisible : mieux vaut le dire que
    d'inventer une valeur par defaut qui echouerait plus loin.
    """
    projet = Path(projet)
    dossier, nom = ((projet.parent, projet.stem.lower())
                    if projet.suffix.lower() == ".prj" else (projet, None))
    trouvees = {}
    for fichier in dossier.iterdir():
        if not fichier.is_file():
            continue
        if not re.match(r"^\.(g|p|u|f|b)\d+$", fichier.suffix, re.I):
            continue
        if nom is not None and fichier.stem.lower() != nom:
            continue
        try:
            for ligne in fichier.read_text(encoding="utf-8",
                                           errors="replace").splitlines():
                if ligne.startswith("Program Version="):
                    brute = ligne.split("=", 1)[1].strip()
                    trouvees[brute] = trouvees.get(brute, 0) + 1
                    break
        except OSError:
            continue

    if not trouvees:
        return None, {}

    def cle(v):
        return [int(x) for x in re.findall(r"\d+", _normaliser_version(v))]

    plus_recente = max(trouvees, key=cle)
    return _normaliser_version(plus_recente), dict(sorted(trouvees.items()))


def versions_hecras_installees():
    """Versions de HEC-RAS reellement installees sur ce poste."""
    versions = []
    for base in (r"C:\Program Files (x86)\HEC\HEC-RAS",
                 r"C:\Program Files\HEC\HEC-RAS"):
        racine = Path(base)
        if racine.is_dir():
            versions += [d.name for d in racine.iterdir() if d.is_dir()]
    return sorted(set(versions))


def lister_projet_hecras(projet):
    """
    Enumere geometries, unsteady flows et plans d'un projet HEC-RAS par
    simple lecture de fichiers texte (.prj, .gXX, .uXX, .pXX) — SANS
    ras-commander, donc directement utilisable dans le processus QGIS, sans
    passer par le pont.

    projet : LE .prj DESIGNE. On recevait le dossier et l'on y prenait le
    premier .prj de projet : dans un dossier a deux projets, un autre que
    celui choisi pouvait etre charge (audit du 11/10/2026). Un dossier reste
    accepte, mais seulement s'il ne porte qu'un projet ; sinon ValueError.

    Retourne {"nom_projet", "geometries", "unsteady", "plans"}. Les entrees
    de "geometries"/"unsteady" sont {"numero", "titre"} ; celles de "plans"
    ajoutent {"geometrie", "unsteady"} (numeros references par le plan).

    Leve FileNotFoundError si aucun .prj de projet HEC-RAS n'est trouve —
    un dossier peut contenir un .prj de PROJECTION (shapefile) qui n'a rien
    a voir : on ne retient que celui qui contient « Proj Title= ».
    """
    projet = Path(projet)
    candidats = (sorted(projet.glob("*.prj")) if projet.is_dir()
                 else [projet] if projet.is_file() else [])
    projets = [f for f in candidats if "Proj Title=" in _lire_texte_hecras(f)]
    if not projets:
        raise FileNotFoundError(f"Aucun projet HEC-RAS (.prj) trouvé : {projet}")
    if len(projets) > 1:
        raise ValueError(
            f"{len(projets)} projets HEC-RAS dans {projet} "
            f"({', '.join(f.name for f in projets)}) : désigner le .prj.")
    prj = projets[0]
    dossier = prj.parent

    texte_prj = _lire_texte_hecras(prj)
    nom_projet = prj.stem

    def numeros(motif):
        trouves = set(re.findall(motif, texte_prj, re.M))
        return sorted(trouves, key=lambda n: (len(n), n))

    def titre(chemin, motif):
        if not chemin.exists():
            return "(fichier introuvable)"
        trouve = re.search(motif, _lire_texte_hecras(chemin))
        return trouve.group(1).strip() if trouve else "(sans titre)"

    geometries = [{"numero": n,
                   "titre": titre(dossier / f"{nom_projet}.g{n}", r"Geom Title=(.*)")}
                  for n in numeros(r"^Geom File=g(\w+)")]
    unsteady = [{"numero": n,
                "titre": titre(dossier / f"{nom_projet}.u{n}", r"Flow Title=(.*)")}
               for n in numeros(r"^Unsteady File=u(\w+)")]

    plans = []
    for n in numeros(r"^Plan File=p(\w+)"):
        chemin_plan = dossier / f"{nom_projet}.p{n}"
        texte_plan = _lire_texte_hecras(chemin_plan) if chemin_plan.exists() else ""
        geom = re.search(r"^Geom File=g(\w+)", texte_plan, re.M)
        flot = re.search(r"^Flow File=u(\w+)", texte_plan, re.M)
        # La fenetre de simulation est relue ICI plutot que par
        # pilote_hecras.fenetre_simulation_du_plan, qui fait la meme chose.
        # LA RAISON N'EST PAS QUE LE PILOTE SERAIT INIMPORTABLE SOUS QGIS —
        # valider_fenetre() l'importe quelques lignes plus bas — mais que
        # cette fonction-ci ne doit dependre de RIEN : ouvrir un projet est
        # le tout premier geste de l'utilisateur, et il doit reussir avant
        # meme que la chaine de calage ait ete localisee. D'ou une lecture
        # qui n'utilise que la bibliotheque standard. Les motifs restent
        # triviaux, et le format est verifie avant ecriture, du cote du
        # pilote, qui reste seul detenteur des regles.
        dates = re.search(r"^Simulation Date=([^,]+),([^,]+),([^,]+),(.+)$",
                          texte_plan, re.M)
        fenetre = {"debut": "", "fin": ""}
        if dates:
            fenetre["debut"] = f"{dates.group(1).strip()},{dates.group(2).strip()}"
            fenetre["fin"] = f"{dates.group(3).strip()},{dates.group(4).strip()}"
        for cle, ligne in (("intervalle_calcul", "Computation Interval"),
                           ("intervalle_sortie", "Output Interval"),
                           ("intervalle_instantane", "Instantaneous Interval"),
                           ("intervalle_mapping", "Mapping Interval")):
            trouve = re.search(rf"^{ligne}=(.*)$", texte_plan, re.M)
            fenetre[cle] = trouve.group(1).strip() if trouve else ""

        plans.append({
            "numero": n,
            "titre": titre(chemin_plan, r"Plan Title=(.*)"),
            "geometrie": geom.group(1) if geom else None,
            "unsteady": flot.group(1) if flot else None,
            "fenetre": fenetre,
            # Cœurs demandes au solveur 2D, une ligne par bloc (plan a trois
            # sur SUHI_ARAN : 0, 0, 8). 0 = « tous ». Lus ici pour que l'etape
            # Lancer dise ce que le plan demande avant de proposer autre chose.
            "coeurs_2d": [int(v) for v in re.findall(
                r"^UNET D2 Cores=\s*(\d+)", texte_plan, re.M)],
        })

    return {"nom_projet": nom_projet, "geometries": geometries,
            "unsteady": unsteady, "plans": plans}


def valider_fenetre(fenetre):
    """
    Verifie une fenetre de simulation saisie dans le plugin.

    Delegue au pilote HEC-RAS, seul detenteur des regles de format. Les redire
    ici en ferait une seconde source de verite : le jour ou HEC-RAS accepterait
    une forme de plus, le plugin refuserait une saisie que le calcul accepte.

    Leve ValueError si la saisie est fautive ; ne retourne rien sinon.
    """
    _raccorder()
    from pilote_hecras import valider_fenetre_simulation

    valider_fenetre_simulation({c: v for c, v in fenetre.items()
                                if str(v).strip()})


def charger_couches_modele(fichier_geometrie_hdf):
    """
    Perimetre(s) de la ou des zones 2D, sections de controle et lignes
    d'injection EXISTANTES dans la geometrie HEC-RAS — lues via le pont,
    puisque cela exige ras-commander.

    C'est ce qui rend visible sur la carte, AVANT tout calcul, ce que la
    geometrie contient deja, et qui permet d'y ajouter de nouvelles lignes en
    les dessinant directement dans QGIS. Fonctionne aussi sur une geometrie
    JAMAIS pretraitee (pas de fichier .hdf) : sections, injections et
    contour de zone 2D sont alors lus dans le fichier texte, qui les porte
    des la creation de la zone dans l'editeur de geometrie. Seul le fichier
    .gXX lui-meme doit exister.

    Retourne {"crs", "sections": [...], "injections": [...], "perimetres": [...],
    "geometrie_pretraitee": bool}, chaque entree etant {"nom", "wkt"} (ou
    {"zone", "wkt"} pour les perimetres).
    """
    return appeler_pont("modele", "--geometrie", str(fichier_geometrie_hdf))


def dernier_journal(chemin_classeur):
    """
    Le journal de lancement le plus recent ecrit a cote du classeur, ou None.

    ICI, A COTE DE lancer_calage QUI LES NOMME : « calage_<horodatage>.log »
    n'est ecrit qu'a un endroit, et qui cherche un journal — l'onglet Suivi
    du plugin, pour lire l'echec d'hier apres avoir rouvert QGIS — passe par
    la meme fonction. L'horodatage du nom ordonne les fichiers comme leurs
    dates, sans lire une seule date de modification.
    """
    return max(Path(chemin_classeur).parent.glob("calage_*.log"),
               default=None)


def lancer_calage(chemin_classeur):
    """
    Lance le calage complet en ARRIERE-PLAN : cette operation dure des heures
    et ne doit JAMAIS bloquer QGIS.

    Contrairement a appeler_pont(), qui ATTEND la reponse avec un delai
    court, cette fonction lance un sous-processus DETACHE (CREATE_NEW_
    PROCESS_GROUP + DETACHED_PROCESS sous Windows) et ne l'attend pas : elle
    retourne immediatement, avec le PID et le chemin d'un journal texte ou
    suivre le deroulement. Les sorties de suivi elles-memes (§ 4.3, reecrites
    a chaque apport valide) restent le moyen normal de savoir ou en est le
    calcul ; le journal ne sert qu'a diagnostiquer un echec au demarrage.

    Meme assainissement d'environnement que pour les appels courts
    (environnement_propre) : PYTHONPATH et PATH de QGIS ne doivent etre
    herites ni par un appel synchrone ni par celui-ci.
    """
    import subprocess
    import time

    chaine = trouver_chaine()
    if chaine is None:
        raise RuntimeError(
            f"Chaîne de calage introuvable. La déclarer par la variable "
            f"{VARIABLE_CHAINE}, ou la désigner depuis le plugin.")
    interpreteur = interpreteur_hecras()
    if interpreteur is None:
        raise RuntimeError(message_interpreteur_introuvable())

    chemin_classeur = Path(chemin_classeur)
    horodatage = time.strftime("%Y%m%d_%H%M%S")
    # Le nom que dernier_journal retrouve : les deux vont ensemble.
    journal = chemin_classeur.parent / f"calage_{horodatage}.log"

    # DIX SECONDES CONTRE QUATORZE HEURES. restaurer_interpreteur() ne
    # verifie au demarrage de QGIS que l'EXISTENCE du fichier — a dessein,
    # pour ne pas retarder l'ouverture. Un interpreteur declare bon un jour
    # etait donc cru sur parole indefiniment, et un module disparu depuis ne
    # se decouvrait qu'a la fin du calage, dans la figure qui en a besoin.
    # Ici, et ici seulement, le sous-processus est negligeable devant ce
    # qu'il protege.
    ok, motif = verifier_interpreteur(interpreteur)
    if not ok:
        raise RuntimeError(f"Interpréteur HEC-RAS inutilisable : {motif}")

    commande = [str(chaine / "pont_hecras.py"),
                "caler", "--template", str(chemin_classeur)]
    drapeaux = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        drapeaux = (subprocess.DETACHED_PROCESS
                    | subprocess.CREATE_NEW_PROCESS_GROUP)

    # LA CONSOLE NE DOIT PAS COUVRIR LA FENETRE, ET ELLE LE FAISAIT.
    #
    # DETACHED_PROCESS prive NOTRE processus de console — mais quand
    # l'interpreteur HEC-RAS est un RELAIS (python.exe de 256 ko d'un venv
    # cree depuis le Python de QGIS), il relance le vrai interpreteur, et
    # celui-la, n'ayant aucune console a heriter, s'en fait allouer une NEUVE.
    # Elle s'ouvrait au premier plan, par-dessus la fenetre du plugin, pendant
    # les heures que dure le calage. Constate le 08/09/2026 sur un poste
    # distant, capture a l'appui.
    #
    # PYTHONW, ET C'EST LA VRAIE REPONSE. Un premier correctif demandait la
    # console REDUITE (SW_SHOWMINNOACTIVE) ; elle revenait quand meme au
    # premier plan, parce que ce reglage ne vaut que pour le processus qu'on
    # cree — le relais, lui, en cree un autre a sa facon. pythonw.exe, a cote
    # de python.exe dans tout venv, est un binaire du sous-systeme GRAPHIQUE :
    # Windows ne lui alloue JAMAIS de console, ni a lui ni au relais qui le
    # lance. Le probleme ne se contourne plus, il n'existe plus.
    #   CE QU'ON NE PERD PAS : la sortie. stdout et stderr sont rediriges vers
    # le journal, comme avant — c'est meme la seule facon de lire un
    # pythonw. Une trace de demarrage rate y figure toujours.
    #   ET SI PYTHONW MANQUE (interpreteur qui n'est pas un venv, poste
    # exotique), on retombe sur python.exe avec la console reduite : mieux
    # vaut une console rangee que pas de calage.
    lancement = interpreteur
    graphique = Path(interpreteur).with_name("pythonw.exe")
    if graphique.is_file():
        lancement = graphique

    demarrage = None
    if lancement is interpreteur and hasattr(subprocess, "STARTUPINFO"):
        demarrage = subprocess.STARTUPINFO()
        demarrage.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        demarrage.wShowWindow = 7        # SW_SHOWMINNOACTIVE

    fichier_journal = open(journal, "w", encoding="utf-8")
    processus = subprocess.Popen(
        [str(lancement)] + commande,
        stdout=fichier_journal, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, env=environnement_propre(interpreteur),
        creationflags=drapeaux, startupinfo=demarrage, close_fds=True)
    # LE PID RENDU N'EST PAS FORCEMENT CELUI DU CALAGE — voir ci-dessus : avec
    # un interpreteur-relais, c'est celui du relais, qui rend la main aussitot.
    # Le suivi ne s'en sert donc que pour l'afficher ; ce qui fait foi, c'est
    # l'heure de debut ecrite dans avancement.json (plugin, _maj_suivi).
    return {"pid": processus.pid, "journal": str(journal)}


def ecrire_shp_temporaire(gdf, dossier, nom):
    """
    Ecrit un GeoDataFrame en shapefile, pour le transmettre au pont.
    Le pont travaille sur des fichiers : c'est la seule maniere de faire
    passer une geometrie d'un interpreteur a l'autre sans serialisation
    maison.
    """
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{nom}.shp"
    gdf[["nom", "geometry"]].to_file(chemin)
    return chemin


# ---------------------------------------------------------------------------
# Auto-test hors QGIS
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # LE BANC VIT HORS DU PAQUET (10/11/2026) : <depot>/src/bancs/banc_noyau.py.
    # Tout .py de calage_apports/ part dans l'archive ; lui n'y part plus.
    import runpy
    _banc = (Path(__file__).resolve().parent.parent / "src" / "bancs"
             / "banc_noyau.py")
    if not _banc.is_file():
        print("Le banc d'auto-tests de noyau.py n'est pas livre avec cette "
              "installation.")
        raise SystemExit(2)
    runpy.run_path(str(_banc), run_name="__main__")
