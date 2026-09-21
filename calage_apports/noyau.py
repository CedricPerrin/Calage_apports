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
import time
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

import ast
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
    prefixe = str(prefixe or "").strip().strip("-_")
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
    return (f"aucun interpreteur capable de piloter HEC-RAS n'a ete trouve. "
            f"Dans l'onglet « Aide et configuration » du plugin, groupe "
            f"« Parametres du poste » : bouton « Installer… » pour en creer "
            f"un — il cherche seul les Python presents sur le poste et "
            f"propose ceux qui conviennent — ou « Designer… » si un "
            f"environnement avec ras-commander existe deja. A defaut, la "
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


def pythons_candidats():
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
            f"module(s) absent(s) de cet interpreteur : "
            f"{', '.join(absents)}.\n\nLe pont en a besoin des la premiere "
            f"composition. Les installer par :\n"
            f"    \"{chemin}\" -m pip install {pip}\n\n"
            + ("L'installeur a deja tente de les poser : voir la sortie de "
               "pip ci-dessus, et le journal du plugin."
               if depuis_installeur else
               "ou laisser le bouton « Installer… » creer un environnement "
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
            f"chaine de calage introuvable : impossible d'atteindre "
            f"pont_hecras.py. La declarer par la variable {VARIABLE_CHAINE}, "
            f"ou la designer depuis le plugin.")

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
        raise RuntimeError(f"delai depasse ({delai} s) : {' '.join(arguments[:2])}")

    sortie = (acheve.stdout or "").strip()
    if not sortie:
        raise RuntimeError(
            f"aucune reponse du pont.\nCommande : {' '.join(commande)}\n"
            f"Erreur : {(acheve.stderr or '').strip()[:800]}")
    try:
        reponse = json.loads(sortie.splitlines()[-1])
    except json.JSONDecodeError:
        raise RuntimeError(f"reponse illisible du pont :\n{sortie[:800]}")

    if not reponse.get("ok"):
        details = reponse.get("details") or []
        raise RuntimeError(reponse.get("erreur", "echec sans message")
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

# SEUIL DE QUALITE NUMERIQUE, PAS DE CONCORDANCE. Doit rester d'accord avec
# calage.Configuration.bilan_masse_max_pct : c'est la meme grandeur, ecrite
# ici pour que le classeur la porte sans que le plugin importe la chaine.
BILAN_MASSE_DEFAUT = 5.0


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
    import pandas as pd

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

    # ET L'ANCIEN CLASSEUR EST MIS DE COTE, JAMAIS ECRASE (20/09/2026,
    # demande utilisateur). Depuis la 0.8.4, deux PREFIXES donnent deux
    # fichiers ; avec le MEME prefixe, recomposer reecrivait le fichier en
    # place. Ce qui compte y survivait — les cibles et les pentes sont
    # relues juste au-dessus et reportees — mais tout le reste partait sans
    # un mot : une feuille ajoutee a la main, une mise en forme, une colonne
    # de travail, un commentaire.
    #   HORODATEE, COMME LA GEOMETRIE. Le bouton promet deja « ecrit dans la
    # geometrie HEC-RAS APRES SAUVEGARDE HORODATEE » ; le classeur suit la
    # meme regle et le meme nom (voir pont_hecras._sauvegarder). Une seule
    # phrase decrit les deux gestes.
    #   LE NOM CANONIQUE NE BOUGE PAS : c'est l'ANCIEN fichier qui change de
    # nom. Renommer le nouveau rendrait imprevisible celui que la chaine
    # lit, et le prefixe existe justement pour que ce nom soit previsible.
    sauvegarde = None
    if chemin.exists():
        sauvegarde = chemin.with_name(
            chemin.stem + time.strftime(".sauvegarde_%Y%m%d_%H%M%S")
            + chemin.suffix)
        try:
            chemin.replace(sauvegarde)
        except OSError:
            # Un classeur ouvert dans Excel refuse d'etre renomme sous
            # Windows. On ne fait pas echouer la composition pour cela : le
            # geste suivant — l'ecriture — dira lui-meme qu'il ne peut pas.
            sauvegarde = None

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
        "Simulation_debut": "",
        "Simulation_fin": "",
        "Intervalle_calcul": "",
        "Intervalle_sortie": "",
        "Intervalle_instantane": "",
        "Intervalle_mapping": "",
        # Trace de la pente donnee aux injections CREEES par le plugin. Non
        # relue par le calage : elle est ecrite dans l'Unsteady Flow au moment
        # de la creation. Elle figure ici pour que le classeur porte, seul, de
        # quoi refaire l'etude.
        "Pente_apport_creee_m_par_m": "",
        # Precision attendue, en POURCENTAGE de la cible, jugee sur la
        # fenetre du hydrogramme PRINCIPAL uniquement.
        "Tolerance_volume_pct": 5.0,
        "Tolerance_pic_pct": 2.0,
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
        "Nb_max_iterations_par_apport": 6,
        "Bilan_masse_max_pct": BILAN_MASSE_DEFAUT,
        "Source_geometrie": "SHP",
        "Fichier_SHP_Sections": str(chemins_shp.get("sections", "")),
        "Fichier_SHP_Apports": str(chemins_shp.get("apports", "")),
        "Fichier_SHP_Axe": str(chemins_shp.get("axe", "")),
        "Sens_axe": "amont_aval",
        "Champ_nom_SHP": "nom",
        "PK_origine_m": 0,
        "Pas_profil_m": 25,
        "Distance_max_axe_maillage_m": "",
    }
    valeurs.update(parametres or {})

    n = len(noms_sections)
    noms_cibles = [f"Cible_{s}" for s in noms_sections]
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
            f"la feuille Cibles n'a pas de colonne « Temps_h » (en-tete A1). "
            f"En-tetes trouves : {_entetes_dits(cibles.columns)}. Le calage "
            f"n'est pas lance.")

    # DES DATES NE SONT PAS DES HEURES. pd.to_numeric ne rend NaN que sur du
    # texte : sur une colonne de DATES il rend les microsecondes depuis 1970,
    # le compte « deux instants » etait satisfait, et le pont mourait plus
    # loin sur une allocation de 536 Gio (relecture adverse du 04/09/2026).
    if pd.api.types.is_datetime64_any_dtype(cibles["Temps_h"]):
        raise ValueError(
            "la colonne « Temps_h » de la feuille Cibles contient des DATES. "
            "Le calage attend des heures decimales comptees depuis le debut "
            "de la simulation (0 ; 0,5 ; 1 …). Le calage n'est pas lance.")

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
            "la colonne « Temps_h » de la feuille Cibles contient des DATES. "
            "Le calage attend des heures decimales comptees depuis le debut "
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
    return False


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
        raise ValueError("la feuille Cibles porte moins de deux instants : "
                         "le pas de temps n'est pas deductible.")

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
    Lit un fichier texte HEC-RAS en essayant plusieurs encodages, comme le
    fait ras-commander en interne. Aucune dependance a ras-commander : cette
    fonction tourne directement dans le processus QGIS.

    Meme politique que pilote_hecras._lire_texte et elaguer_projet._lire_texte.
    Ces trois modules ne peuvent PAS partager de code : le plugin est livre
    seul dans son zip et doit fonctionner avant meme que la chaine soit
    localisee. La duplication est assumee ; toute correction ici doit etre
    reportee aux deux autres.
    """
    chemin = Path(chemin)
    for encodage in ("utf-8", "latin1", "cp1252"):
        try:
            return chemin.read_text(encoding=encodage)
        except (UnicodeDecodeError, LookupError):
            continue
    return chemin.read_text(encoding="latin1", errors="replace")


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


def version_hecras_du_projet(dossier):
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

    Retourne (version, detail) ou detail liste ce qui a ete trouve. Retourne
    (None, ...) si aucune version n'est lisible : mieux vaut le dire que
    d'inventer une valeur par defaut qui echouerait plus loin.
    """
    dossier = Path(dossier)
    trouvees = {}
    for fichier in dossier.iterdir():
        if not fichier.is_file():
            continue
        if not re.match(r"^\.(g|p|u|f|b)\d+$", fichier.suffix, re.I):
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


def lister_projet_hecras(dossier):
    """
    Enumere geometries, unsteady flows et plans d'un projet HEC-RAS par
    simple lecture de fichiers texte (.prj, .gXX, .uXX, .pXX) — SANS
    ras-commander, donc directement utilisable dans le processus QGIS, sans
    passer par le pont.

    Retourne {"nom_projet", "geometries", "unsteady", "plans"}. Les entrees
    de "geometries"/"unsteady" sont {"numero", "titre"} ; celles de "plans"
    ajoutent {"geometrie", "unsteady"} (numeros references par le plan).

    Leve FileNotFoundError si aucun .prj de projet HEC-RAS n'est trouve —
    un dossier peut contenir un .prj de PROJECTION (shapefile) qui n'a rien
    a voir : on ne retient que celui qui contient « Proj Title= ».
    """
    dossier = Path(dossier)
    prj = next((f for f in dossier.glob("*.prj")
               if "Proj Title=" in _lire_texte_hecras(f)), None)
    if prj is None:
        raise FileNotFoundError(
            f"aucun projet HEC-RAS (.prj) trouve dans {dossier}")

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
            f"chaine de calage introuvable. La declarer par la variable "
            f"{VARIABLE_CHAINE}, ou la designer depuis le plugin.")
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
        raise RuntimeError(f"interpreteur HEC-RAS inutilisable : {motif}")

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
    import tempfile
    import time

    import geopandas as gpd
    import numpy as np
    from shapely.geometry import LineString

    def site_packages(venv):
        """
        Le site-packages que CE venv porte reellement.

        « Lib/site-packages » sous Windows, « lib/python3.x/site-packages »
        ailleurs — et le « 3.x » ne se devine pas. sysconfig ne repond pas
        non plus : sur les distributions qui le corrigent, il rend
        « local/lib/python3.x/dist-packages », que venv ne cree pas, et
        get_preferred_scheme demande 3.10 quand PYTHON_MINIMUM est (3, 9).
        On lit donc la disposition sur le venv lui-meme.

        DEUX BANCS EN ONT BESOIN — les 9 et 10 — et une seule definition les
        sert : recopiee, elle se vouerait a diverger de son jumeau. Sans
        elle, tous deux s'arretaient sur un FileNotFoundError hors de
        Windows, et le banc du noyau ne passait pas depuis un clone neuf.
        """
        paquets = venv / "Lib" / "site-packages"
        if paquets.is_dir():
            return paquets
        return next(venv.glob("lib/python*/site-packages"), paquets)

    print("=" * 72)
    print("AUTO-TEST DU NOYAU DU PLUGIN  (hors QGIS)")
    print("=" * 72)

    print(f"\nChaine de calage : {trouver_chaine()}")
    disponible, messages = chaine_disponible()
    print(f"disponible : {disponible}")
    for m in messages:
        print("   ", m)

    dossier = Path(tempfile.gettempdir()) / "calage_paquet_test"
    if dossier.exists():
        shutil.rmtree(dossier)

    xs = np.linspace(0, 8000, 60)
    axe_geom = LineString(zip(500000 + xs, 6200000 + 300 * np.sin(xs / 1400)))

    def transversale(xl, demi=400.0):
        y = 300 * np.sin(xl / 1400)
        return LineString([(500000 + xl, 6200000 + y - demi),
                           (500000 + xl, 6200000 + y + demi)])

    noms_s = ["S1_Amont", "S2_Pont", "S3_Confluence", "S4_Aval"]
    noms_a = ["A1", "A2", "A3", "A4"]
    sections = gpd.GeoDataFrame(
        {"nom": noms_s}, crs="EPSG:2154",
        geometry=[transversale(x) for x in (900, 2800, 5100, 7400)])
    apports = gpd.GeoDataFrame(
        {"nom": noms_a}, crs="EPSG:2154",
        geometry=[transversale(x, 250) for x in (200, 2100, 4300, 6600)])
    axe = gpd.GeoDataFrame({"nom": ["Axe"]}, geometry=[axe_geom], crs="EPSG:2154")

    print("\n1. COMPOSITION DU PAQUET")
    chemins = composer_paquet(dossier, sections, apports, axe)
    for cle, chemin in chemins.items():
        print(f"   {cle:10s} -> {chemin.name}")

    print("\n2. APPARIEMENT AMONT -> AVAL")
    appariement = apparier_paquet(chemins)
    print(f"   sens retenu : {appariement['sens']}")
    for a, s in appariement["paires"]:
        print(f"   {a}  alimente  {s}")
    for nom, pk in appariement["sans_section"]:
        print(f"   {nom} : aucune section en aval — non cale (PK {pk:.0f} m)")

    print("\n3. CLASSEUR PRE-REMPLI")
    # Le plugin demande l'identification du modele dans sa boite de dialogue :
    # sans elle, le controle refuse de laisser lancer un calage.
    classeur = preparer_classeur(dossier, appariement["paires"], chemins,
                                 parametres={
        # Valeurs fictives : ce bloc n'exerce que le pre-remplissage du
        # classeur, aucun fichier n'est ouvert. Le dossier est relatif a
        # dessein — un chemin absolu ecrit dans un fichier livre finirait par
        # designer le poste de celui qui l'a ecrit.
        "Dossier_projet_HECRAS": str(dossier / "projet_fictif"),
        "Nom_projet": "Essai",
        "Nom_zone_2D": "Zone_2D_essai",
    })
    import pandas as pd
    corr = pd.read_excel(classeur, sheet_name="Correspondance")
    print(f"   {classeur.name} — feuille Correspondance deja renseignee :")
    print("   " + corr.to_string(index=False).replace("\n", "\n   "))

    print("\n4. CONTROLE DU PAQUET")
    anomalies, tableau, _prolongation = controler_paquet(classeur)
    erreurs = [m for n, m in anomalies if n == "ERREUR"]
    for niveau, message in anomalies:
        print(f"   [{niveau:13s}] {message}")
    etat = "conforme" if not erreurs else "A CORRIGER"
    print(f"   -> {len(erreurs)} erreur(s), {len(anomalies) - len(erreurs)} "
          f"avertissement(s) : {etat}")
    print("      (un classeur fraichement compose n'a pas encore de cibles :")
    print("       c'est un avertissement, pas une erreur)")
    if tableau is not None:
        print("\n   PK calcules :")
        print("   " + tableau.to_string(index=False).replace("\n", "\n   "))

    print("\n4 bis. PROLONGATION DES CIBLES PAR DES ZEROS")
    # LE GESTE QUE LE PRE-VOL RECLAME. Un hydrogramme cible qui s'arrete avant
    # la fin de la simulation fait refuser le calcul par HEC-RAS ; le
    # prolonger a la main, colonne par colonne dans Excel, etait la seule
    # issue. Ce qui est eprouve ici : le pas est celui de la SAISIE, les
    # valeurs ajoutees sont des ZEROS (une crue retombee, pas la derniere
    # valeur connue — invariant 8), l'existant n'est pas touche, et rappeler
    # la fonction ne fait rien.
    import openpyxl
    _cl = dossier / "essai_prolongation.xlsx"
    _wb = openpyxl.Workbook()
    _fe = _wb.active
    _fe.title = "Cibles"
    _fe.append(["Temps_h", "Cible_S1", "Cible_S2"])
    for _i in range(5):                       # 0,00 -> 1,00 h au quart d'heure
        _fe.append([round(0.25 * _i, 2), 10.0 + _i, 20.0 + _i])
    _wb.save(_cl)

    _bilan = prolonger_cibles(_cl, 2.0)
    _lu = pd.read_excel(_cl, sheet_name="Cibles")
    _ajoutees = _lu[_lu["Temps_h"] > 1.0 + 1e-9]
    _controles = [
        ("le pas de la saisie est repris", abs(_bilan["pas_h"] - 0.25) < 1e-9,
         f"{_bilan['pas_h']} h"),
        ("la duree visee est atteinte", abs(_lu["Temps_h"].max() - 2.0) < 1e-9,
         f"{_lu['Temps_h'].max()} h"),
        ("les lignes ajoutees valent ZERO, pas la derniere valeur",
         bool((_ajoutees[["Cible_S1", "Cible_S2"]] == 0).all().all()),
         f"{len(_ajoutees)} ligne(s)"),
        ("la saisie d'origine est intacte",
         list(_lu["Cible_S1"][:5]) == [10.0, 11.0, 12.0, 13.0, 14.0],
         str(list(_lu["Cible_S1"][:5]))),
        ("rappeler la fonction n'ajoute rien",
         prolonger_cibles(_cl, 2.0)["ajoutees"] == 0),
        ("une cible deja assez longue n'est pas touchee",
         prolonger_cibles(_cl, 1.5)["ajoutees"] == 0),
    ]
    for _libelle, _ok, *_detail in _controles:
        print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}"
              + (f"  ->  {_detail[0]}" if _detail else ""))
        assert _ok, _libelle
    _cl.unlink(missing_ok=True)

    # ET LE LANCEMENT REFUSE UN CLASSEUR SANS COLONNE Temps_h (04/09/2026).
    # etat_cibles() est ce que le plugin consulte juste avant de partir. Il
    # laissait passer un en-tete A1 remplace ; le pont plantait ensuite en
    # arriere-plan, hors de vue, sur un scalaire. Refuser ICI, et nommer
    # l'en-tete trouve : c'est lui qu'il faut corriger.
    _wb = openpyxl.Workbook()
    _fe = _wb.active
    _fe.title = "Correspondance"
    _fe.append(["Ordre", "Nom_Apport (BC line)",
                "Nom_Section (reference line)", "Nom_Cible"])
    _fe.append([1, "A1", "S1", "Cible_S1"])
    _fc = _wb.create_sheet("Cibles")
    _fc.append(["Temps (h)", "Cible_S1"])
    _fc.append([0.0, 10.0])
    _wb.save(_cl)
    try:
        etat_cibles(_cl)
        _dit = "aucune erreur"
    except ValueError as e:
        _dit = str(e)
    except Exception as e:                                  # noqa: BLE001
        _dit = f"{type(e).__name__}: {e}"
    _libelle = ("sans colonne Temps_h, l'etat des cibles refuse et nomme "
                "l'en-tete trouve")
    _ok = "Temps_h" in _dit and "Temps (h)" in _dit
    print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  {_dit[:100]}")
    assert _ok, _libelle
    _cl.unlink(missing_ok=True)

    # ET UNE COLONNE DE TEMPS VIDE SOUS SON EN-TETE NE RENSEIGNE RIEN. Le meme
    # classeur du 04/09 avait six colonnes de debit pleines (418 lignes) et UN
    # SEUL instant : six cibles « renseignees » pour le plugin, six
    # « inexploitables » pour le pont, qui l'aurait dit en arriere-plan apres
    # l'en-tete corrige. Meme regle des deux cotes : deux instants numeriques
    # en face de deux debits numeriques (_cibles_depuis_classeur).
    _wb = openpyxl.Workbook()
    _fe = _wb.active
    _fe.title = "Correspondance"
    _fe.append(["Ordre", "Nom_Apport (BC line)",
                "Nom_Section (reference line)", "Nom_Cible"])
    _fe.append([1, "A1", "S1", "Cible_S1"])
    _fe.append([2, "A2", "S2", "Cible_S2"])
    _fc = _wb.create_sheet("Cibles")
    _fc.append(["Temps_h", "Cible_S1", "Cible_S2"])
    _fc.append([0.0, 0.0, 0.0])
    for _i in range(1, 6):
        _fc.append([None, 10.0 * _i, 5.0 * _i])       # temps VIDE, debits pleins
    _wb.save(_cl)
    _etat = etat_cibles(_cl)
    _libelle = "une colonne de temps vide rend les cibles non renseignees"
    _ok = _etat["manquantes"] == ["S1", "S2"] and _etat["renseignees"] == 0
    print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  {_etat}")
    assert _ok, _libelle
    for _i in range(1, 6):                              # les instants, et tout va
        _fc.cell(row=_i + 2, column=1, value=0.25 * _i)
    _wb.save(_cl)
    _etat = etat_cibles(_cl)
    _libelle = "avec ses instants, la meme feuille renseigne les deux cibles"
    _ok = _etat["manquantes"] == [] and _etat["renseignees"] == 2
    print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  {_etat}")
    assert _ok, _libelle
    _cl.unlink(missing_ok=True)

    # LE PREFIXE DE SCENARIO NOMME LE CLASSEUR (0.8.4). Deux scenarios d'un
    # meme dossier de sortie partageaient « donnees_calage.xlsx » : composer
    # le Q10 ecrasait la feuille Correspondance du Q100.
    for _prefixe, _attendu in (("", "donnees_calage.xlsx"),
                               ("Q100", "donnees_calage_Q100.xlsx"),
                               ("Q100_", "donnees_calage_Q100.xlsx"),
                               ("Q100 V2", "donnees_calage_Q100_V2.xlsx"),
                               ("Q100/bis", "donnees_calage_Q100_bis.xlsx")):
        _rendu = nom_classeur(_prefixe)
        _ok = _rendu == _attendu
        print(f"   [{'OK' if _ok else 'ECHEC'}] prefixe « {_prefixe} »  ->  {_rendu}")
        assert _ok, f"nom_classeur({_prefixe!r}) rend {_rendu}, attendu {_attendu}"
    _dossier_p = dossier / "deux_scenarios"
    _q100 = preparer_classeur(_dossier_p, [("A1", "S1")], {},
                              parametres={"Prefixe_scenario": "Q100"})
    _q10 = preparer_classeur(_dossier_p, [("A1", "S1")], {},
                             parametres={"Prefixe_scenario": "Q10"})
    _libelle = "deux scenarios, deux classeurs dans le meme dossier de sortie"
    _ok = (_q100 != _q10 and Path(_q100).exists() and Path(_q10).exists())
    print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  "
          f"{Path(_q100).name} et {Path(_q10).name}")
    assert _ok, _libelle
    # ET LE DERNIER JOURNAL EST CELUI AU NOM LE PLUS GRAND : l'horodatage du
    # nom suffit, aucune date de fichier n'est lue.
    for _nom in ("calage_20260913_235959.log", "calage_20260914_082326.log"):
        (_dossier_p / _nom).write_text("", encoding="utf-8")
    _rendu = dernier_journal(_q100)
    _ok = _rendu is not None and _rendu.name == "calage_20260914_082326.log"
    print(f"   [{'OK' if _ok else 'ECHEC'}] dernier_journal  ->  "
          f"{_rendu.name if _rendu else None}")
    assert _ok, f"dernier_journal rend {_rendu}"
    _ok = dernier_journal(dossier / "sans_journal" / "x.xlsx") is None
    print(f"   [{'OK' if _ok else 'ECHEC'}] dernier_journal sans journal  ->  None")
    assert _ok, "dernier_journal devrait rendre None sans journal"

    # ET RECOMPOSER N'EFFACE PAS UNE SAISIE QU'ON NE SAIT PAS RELIRE.
    # preparer_classeur() preserve les cibles deja collees en les cherchant
    # sous l'en-tete « Temps_h » ; sans lui, la feuille etait REECRITE VIDE,
    # sans un mot — six colonnes de 418 lignes, et le plugin qui promet a
    # l'ecran que « recomposer plus tard preserve les hydrogrammes deja
    # saisis » (04/09/2026). Le geste naturel apres le nouveau message
    # d'etat_cibles est justement de recomposer.
    _dossier2 = dossier / "recomposition"
    _dossier2.mkdir(parents=True, exist_ok=True)
    _cl2 = _dossier2 / NOMS_FICHIERS["classeur"]
    _wb = openpyxl.Workbook()
    _fc = _wb.active
    _fc.title = "Cibles"
    _fc.append(["\u00b6", "Cible_S1", "Cible_S2"])       # en-tete A1 remplace
    for _i in range(6):
        _fc.append([None, 10.0 + _i, 20.0 + _i])
    _wb.save(_cl2)
    try:
        preparer_classeur(_dossier2, [("A1", "S1"), ("A2", "S2")], {})
        _dit = "aucune erreur"
    except ValueError as e:
        _dit = str(e)
    _reste = pd.read_excel(_cl2, sheet_name="Cibles")
    _libelle = "recomposer sans en-tete Temps_h refuse et laisse la saisie intacte"
    # LA PRESERVATION EN PREMIER : sur le code d'avant, « Temps_h in _dit »
    # court-circuitait et la ligne d'ECHEC ne disait que « aucune erreur »,
    # sans jamais montrer la saisie detruite qui justifie le garde-fou.
    _garde = int(_reste[["Cible_S1", "Cible_S2"]].notna().sum().sum())
    _ok = (_garde == 12 and "Temps_h" in _dit and "\u00b6" in _dit)
    print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  "
          f"{_garde} valeurs restantes sur 12 ; {_dit[:60]}")
    assert _ok, _libelle
    _cl2.unlink(missing_ok=True)

    # UNE COLONNE DE TEMPS EN DATES NE PASSE PAS. pd.to_numeric ne rend NaN
    # que sur du texte : sur une colonne de DATES Excel — la facon la plus
    # courante de coller une chronique — il rend les microsecondes depuis
    # 1970. Le compte « deux instants » etait donc satisfait, le calage
    # partait, et le pont mourait sur une allocation de 536 Gio dans
    # reechantillonner (relecture adverse du 04/09/2026).
    # « as _dt » ET PAS « import datetime » : noyau.py importe la CLASSE
    # datetime (ligne 22), qu'un import du MODULE recouvrirait — tout ce qui
    # suit et appelle datetime.fromtimestamp() casserait alors, en silence.
    import datetime as _dt
    _wb = openpyxl.Workbook()
    _fe = _wb.active
    _fe.title = "Correspondance"
    _fe.append(["Ordre", "Nom_Apport (BC line)",
                "Nom_Section (reference line)", "Nom_Cible"])
    _fe.append([1, "A1", "S1", "Cible_S1"])
    _fc = _wb.create_sheet("Cibles")
    _fc.append(["Temps_h", "Cible_S1"])
    for _i in range(3):
        _fc.append([_dt.datetime(2020, 1, 1, _i), 10.0 * _i])
    _wb.save(_cl)
    try:
        etat_cibles(_cl)
        _dit = "aucune erreur"
    except ValueError as e:
        _dit = str(e)
    except Exception as e:                                  # noqa: BLE001
        _dit = f"{type(e).__name__}: {e}"
    _libelle = "une colonne de temps en DATES est refusee, pas comptee"
    _ok = "date" in _dit.lower() and "heures" in _dit.lower()
    print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  {_dit[:100]}")
    assert _ok, _libelle
    _cl.unlink(missing_ok=True)

    # ET LE GARDE-FOU DE RECOMPOSITION NE CHERCHE PLUS SA PREUVE DANS LA LIGNE
    # ABIMEE. Il exigeait un en-tete « Cible_ » non vide — or « Temps_h » et
    # les « Cible_ » vivent dans la MEME ligne 1 : ligne supprimee, triee avec
    # les donnees, ou recouverte par un bloc colle avec ses propres titres, le
    # detecteur partait avec elle et la feuille etait reecrite VIDE. Ce sont
    # les VALEURS sous la ligne 1 qui disent qu'il y a quelque chose a perdre.
    for _cas, _entetes in (("ligne 1 recouverte", ["t (h)", "Q_S1", "Q_S2"]),
                           ("ligne 1 supprimee", [0.0, 10.0, 20.0])):
        _dossier3 = dossier / ("recomposition_" + _cas.replace(" ", "_"))
        _dossier3.mkdir(parents=True, exist_ok=True)
        _cl3 = _dossier3 / NOMS_FICHIERS["classeur"]
        _wb = openpyxl.Workbook()
        _fc = _wb.active
        _fc.title = "Cibles"
        _fc.append(_entetes)
        for _i in range(6):
            _fc.append([0.25 * _i, 10.0 + _i, 20.0 + _i])
        _wb.save(_cl3)
        try:
            preparer_classeur(_dossier3, [("A1", "S1"), ("A2", "S2")], {})
            _dit = "aucune erreur"
        except ValueError as e:
            _dit = str(e)
        _reste = pd.read_excel(_cl3, sheet_name="Cibles")
        _valeurs = int(_reste.iloc[:, :3].notna().sum().sum())
        _libelle = f"recomposer avec la {_cas} refuse et garde la saisie"
        _ok = "Temps_h" in _dit and _valeurs >= 18
        print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  "
              f"{_valeurs} valeurs restantes ; {_dit[:60]}")
        assert _ok, _libelle

    print("\n4 ter. EMPLACEMENT DE L'ENVIRONNEMENT HEC-RAS")
    # CE QU'IL FAUT EPROUVER ICI : que le bouton « Installer… » ait TOUJOURS
    # un endroit ou ecrire, et que cet endroit ne soit JAMAIS le dossier
    # d'installation de l'extension — que le gestionnaire de QGIS efface a
    # chaque mise a jour.
    # Le controle inverse (« la copie embarquee est refusee », emplacement
    # None) a existe jusqu'au 31/08/2026 et VALIDAIT UN DEFAUT : refuser
    # l'emplacement etait juste, en conclure qu'il n'y en avait aucun rendait
    # le bouton inutilisable sur un poste neuf — le seul ou il sert.
    _garde = _dossier_chaine
    _garde_emb = DOSSIER_EMBARQUE
    _donnees = dossier_donnees_plugin() / "venv-hecras"
    try:
        # LA COPIE EMBARQUEE N'EXISTE QUE DANS LE ZIP, jamais sur le disque
        # d'un poste de developpement : le controle qui la concerne etait donc
        # IGNORE ici, et c'est ce qui a laisse passer le defaut du 31/08. On
        # en FABRIQUE une, pour que la branche soit toujours exercee.
        _faux_emb = dossier / "faux_plugin" / "chaine"
        _faux_emb.mkdir(parents=True, exist_ok=True)
        for _f in FICHIERS_CHAINE:
            (_faux_emb / _f).write_text("# temoin\n", encoding="utf-8")
        DOSSIER_EMBARQUE = _faux_emb
        _dossier_chaine = _faux_emb
        _ou = emplacement_venv_hecras()
        print(f"   [{'OK' if _ou == _donnees else 'ECHEC'}] chaine embarquee "
              f"-> dossier de donnees, PAS le plugin  ->  {_ou}")
        assert _ou == _donnees, _ou
        assert _faux_emb not in _ou.parents and _faux_emb.parent not in _ou.parents
        DOSSIER_EMBARQUE = _garde_emb
        _dossier_chaine = Path(__file__).resolve().parent.parent / "src"
        if est_chaine(_dossier_chaine):
            _attendu = _dossier_chaine.parent / ".venv"
            print(f"   [{'OK' if emplacement_venv_hecras() == _attendu else 'ECHEC'}]"
                  f" une chaine externe -> a cote d'elle  ->  {_attendu}")
            assert emplacement_venv_hecras() == _attendu
        _dossier_chaine = None
        if trouver_chaine() is None:
            _ou = emplacement_venv_hecras()
            print(f"   [{'OK' if _ou == _donnees else 'ECHEC'}] sans aucune "
                  f"chaine, un emplacement est quand meme propose  ->  {_ou}")
            assert _ou == _donnees
        else:
            print("   (une chaine est trouvee automatiquement : controle ignore)")
        # L'ENVIRONNEMENT INSTALLE DOIT SE RETROUVER SEUL a la session
        # suivante, sans QSettings : sinon un profil QGIS neuf le perdrait.
        # LA CONDITION AFFICHEE EST CELLE QU'ON VERIFIE. Elle valait
        # « <Path> or True » : toujours vraie, donc « [OK] » quoi qu'il
        # arrive. Seul l'assert controlait quelque chose, et la ligne au-
        # dessus de lui mentait.
        _hors_plugin = (DOSSIER_EMBARQUE.parent
                         not in dossier_donnees_plugin().parents)
        print(f"   [{'OK' if _hors_plugin else 'ECHEC'}]"
              f" le dossier de donnees est hors du plugin  ->  "
              f"{dossier_donnees_plugin()}")
        assert _hors_plugin

        # --- 4 quater. LE PLUGIN CHERCHE LES PYTHON TOUT SEUL -------------
        print("\n4 quater. Recherche des Python utilisables")
        _cands = pythons_candidats()
        for _c in _cands:
            print(f"      {'.'.join(str(n) for n in _c['version']):9} "
                  f"{_c['origine']:12} {_c['chemin']}")

        # AUCUN LEURRE NE PASSE. C'est le defaut qui a bloque un poste neuf le
        # 01/09/2026 : deux « python.exe » dans le PATH, tous deux des alias
        # WindowsApps de zero octet, et le selecteur de fichier n'avait rien a
        # proposer. On FABRIQUE le leurre plutot que de dependre du poste.
        _leurre = dossier / "WindowsApps" / "python.exe"
        _leurre.parent.mkdir(parents=True, exist_ok=True)
        _leurre.write_bytes(b"")
        print(f"   [{'OK' if _python_utilisable(_leurre) is None else 'ECHEC'}]"
              f" un alias WindowsApps de zero octet est refuse")
        assert _python_utilisable(_leurre) is None
        _vide = dossier / "python.exe"
        _vide.write_bytes(b"")
        print(f"   [{'OK' if _python_utilisable(_vide) is None else 'ECHEC'}]"
              f" un fichier vide hors WindowsApps aussi")
        assert _python_utilisable(_vide) is None
        _pasla = dossier / "jamais" / "python.exe"
        print(f"   [{'OK' if _python_utilisable(_pasla) is None else 'ECHEC'}]"
              f" un chemin inexistant aussi")
        assert _python_utilisable(_pasla) is None

        # ON VALIDE EN EXECUTANT : le python qui fait tourner ce banc doit
        # passer, puisqu'il sait demarrer et porte venv.
        _moi = _python_utilisable(sys.executable)
        print(f"   [{'OK' if _moi is not None else 'ECHEC'}] le python courant "
              f"est reconnu utilisable  ->  {_moi}")
        assert _moi is not None and _moi >= PYTHON_MINIMUM

        # L'ORDRE EST LA DECISION DU 01/09/2026 : un Python independant passe
        # AVANT celui de QGIS, parce qu'un venv bati sur apps\Python3xx casse
        # quand QGIS monte de version.
        _indep = [i for i, c in enumerate(_cands)
                  if c["origine"] == "independant"]
        _qgis = [i for i, c in enumerate(_cands) if c["origine"] == "QGIS"]
        _ordre = (not _indep or not _qgis or max(_indep) < min(_qgis))
        print(f"   [{'OK' if _ordre else 'ECHEC'}] tout Python independant "
              f"passe avant ceux de QGIS  ->  "
              f"{len(_indep)} independant(s), {len(_qgis)} QGIS")
        assert _ordre
        _versions = [c["version"] for c in _cands
                     if c["origine"] == "independant"]
        print(f"   [{'OK' if _versions == sorted(_versions, reverse=True) else 'ECHEC'}]"
              f" et a origine egale, la version la plus recente d'abord  ->  "
              f"{['.'.join(str(n) for n in v) for v in _versions]}")
        assert _versions == sorted(_versions, reverse=True)
        print(f"   [{'OK' if all(c['chemin'].is_file() for c in _cands) else 'ECHEC'}]"
              f" tous les candidats rendus existent vraiment")
        assert all(c["chemin"].is_file() for c in _cands)
        # installer_interpreteur REFUSE un python de base inexistant, sans
        # rien creer : c'est le seul chemin de cette fonction qu'un banc peut
        # emprunter sans telecharger plusieurs centaines de mega-octets.
        _chemin, _motif = installer_interpreteur(dossier / "python_absent.exe")
        print(f"   [{'OK' if _chemin is None and _motif else 'ECHEC'}]"
              f" un python de base inexistant est refuse  ->  {_motif[:60]}")
        assert _chemin is None and _motif
    finally:
        _dossier_chaine = _garde
        DOSSIER_EMBARQUE = _garde_emb

    print("\n4 quinquies. TROUVER PYTHON SUR UN POSTE QUELCONQUE")
    # CE QUI SE JOUE ICI : le neophyte qui ne sait pas ou est Python. Le
    # plugin le cherche pour lui, et ne doit pas le manquer sur un poste
    # ordinaire — un disque systeme autre que C:, un dossier de programmes
    # redirige, un chemin qui contient des espaces.
    for _ligne, _attendu in [
            (r" -V:3.13 *        C:\Users\x\Python313\python.exe",
             r"C:\Users\x\Python313\python.exe"),
            # LE DEFAUT CORRIGE : la lecture cherchait « c: » et laissait
            # tomber la ligne sans un mot. Un poste dont le disque systeme
            # est petit installe volontiers Python sur D:.
            (r" -V:3.12          D:\Python312\python.exe",
             r"D:\Python312\python.exe"),
            (r" -V:3.11          C:\Program Files\Python 3.11\python.exe",
             r"C:\Program Files\Python 3.11\python.exe"),
            (r" -3.11-64        E:\Py\python.exe", r"E:\Py\python.exe"),
            (r" -V:3.13         \\serveur\part\Python313\python.exe",
             r"\\serveur\part\Python313\python.exe"),
            ("Installed Pythons found by py Launcher", None),
            # pythonw n'ecrit rien sur la sortie standard : le sonder coute
            # un sous-processus pour un rejet certain.
            (r" -V:3.13          C:\Py\pythonw.exe", None)]:
        _lu = _chemin_dans_ligne_py(_ligne)
        print(f"   [{'OK' if _lu == _attendu else 'ECHEC'}] py -0p : "
              f"{_ligne.strip()[:44]:44s} -> {_lu}")
        assert _lu == _attendu, (_ligne, _lu, _attendu)

    # LES RACINES SONT WINDOWS PAR NATURE : %ProgramFiles% et les lettres de
    # lecteur n'ont pas d'equivalent ailleurs. Hors Windows, ce qu'on exige
    # est qu'elle rende une liste sans lever — le PATH prend le relais.
    _racines = _racines_recherche()
    _attendu_racines = bool(_racines) if os.name == "nt" else True
    print(f"   [{'OK' if _attendu_racines else 'ECHEC'}] des racines de "
          f"recherche sont proposees  ->  {len(_racines)} sur ce poste "
          f"({'Windows' if os.name == 'nt' else 'hors Windows : le PATH suffit'})")
    assert _attendu_racines
    assert all(isinstance(r, Path) for r in _racines)
    _emplacements = _emplacements_python()
    _cles = [str(e).lower() for e in _emplacements]
    print(f"   [{'OK' if len(_cles) == len(set(_cles)) else 'ECHEC'}] "
          f"aucun emplacement propose deux fois  ->  {len(_cles)} chemins")
    assert len(_cles) == len(set(_cles))
    print(f"   [{'OK' if len(_emplacements) <= MAXIMUM_CANDIDATS else 'ECHEC'}]"
          f" la liste est plafonnee : sonder coute un sous-processus  ->  "
          f"{len(_emplacements)} <= {MAXIMUM_CANDIDATS}")
    assert len(_emplacements) <= MAXIMUM_CANDIDATS

    print("\n4 sexies bis. TOUT SOUS-PROCESSUS LANCE DEPUIS QGIS EST ASSAINI")
    # LE DEFAUT : l'installeur lancait « python -m venv » puis deux « pip
    # install » SANS env=environnement_propre(). Il s'execute dans QGIS, dont
    # le PYTHONPATH et le PYTHONHOME pointent SA bibliotheque — qui livre deja
    # huit des onze paquets. pip les tenait pour « already satisfied », ne les
    # posait pas dans le venv, et sortait en succes ; la sonde, elle, lisait le
    # venv REEL et les declarait tous absents. « Installation terminee » suivi
    # de « onze modules absents », deux fois. Releve sur un poste neuf le
    # 05/09/2026, a la premiere installation reelle du bouton.
    #   LE CONTROLE PORTE SUR LE CODE, faute de pouvoir installer pour de vrai
    # dans un banc — ce serait plusieurs centaines de Mo a chaque passage.
    # « creationflags » AUTANT QUE « env » : sans lui, chaque appel fait
    # clignoter une console noire devant la fenetre du plugin — quarante fois
    # de suite quand « Installer… » cherche un python de base, et pendant
    # plusieurs minutes quand pip travaille. Le drapeau lui-meme differe selon
    # l'appel : SANS_FENETRE pour les appels synchrones, DETACHED_PROCESS pour
    # le calage detache, et les deux sont INCOMPATIBLES. Ce qu'on exige ici est
    # donc que la question ait ete posee, pas qu'une valeur precise soit la.
    _source_noyau = Path(__file__).resolve().read_text(encoding="utf-8")
    _arbre = ast.parse(_source_noyau)
    _nus = []
    for _f in ast.walk(_arbre):
        if not (isinstance(_f, ast.FunctionDef)
                and _f.name in ("installer_interpreteur", "_sonder_interpreteur",
                                "appeler_pont", "lancer_calage")):
            continue
        for _n in ast.walk(_f):
            if not isinstance(_n, ast.Call):
                continue
            _cible = getattr(_n.func, "attr", None)
            if _cible != "run" or getattr(_n.func.value, "id", "") != "subprocess":
                continue
            _cles = {k.arg for k in _n.keywords}
            for _exige in ("env", "creationflags"):
                if _exige not in _cles:
                    _nus.append(f"{_f.name} l. {_n.lineno} : « {_exige}= » "
                                f"manquant")
    print(f"   [{'OK' if not _nus else 'ECHEC'}] tout sous-processus lance "
          f"depuis QGIS porte « env= » ET « creationflags= »  ->  "
          f"{'aucun manque' if not _nus else _nus}")
    assert not _nus, _nus

    print("\n4 sexies. CE QU'ON DIT D'INSTALLER EST CE QU'ON EXIGE")
    # LE DEFAUT : l'aide et le message « interpreteur introuvable » nommaient
    # DEUX paquets, la verification en exige onze. Suivre l'aide a la lettre
    # fabriquait un environnement refuse. Une liste ecrite deux fois finit
    # toujours par diverger — il n'y en a plus qu'une, PAQUETS_HECRAS, et ce
    # banc interdit qu'une seconde reapparaisse dans un texte distribue.
    _commande = commande_pip_hecras()
    _oublies = [pip.split(">")[0].split("=")[0]
                for _, pip in PAQUETS_HECRAS
                if pip.split(">")[0].split("=")[0] not in _commande]
    print(f"   [{'OK' if not _oublies else 'ECHEC'}] la commande pip nomme "
          f"les {len(PAQUETS_HECRAS)} paquets exiges  ->  "
          f"{'aucun oubli' if not _oublies else _oublies}")
    assert not _oublies, _oublies
    _venv, _pip = recette_installation_manuelle()
    print(f"   [{'OK' if '-m venv' in _venv and '-m pip install' in _pip else 'ECHEC'}]"
          f" la recette manuelle cree l'environnement PUIS le peuple")
    assert "-m venv" in _venv and "-m pip install" in _pip

    # DEUX GARDE-FOUS, PARCE QUE LA LISTE COURTE POUVAIT SE RECOMPOSER.
    # Chercher le texte litteral ne suffisait pas : plugin.py l'ecrivait en
    # trois morceaux de f-string, invisibles a une recherche de sous-chaine.
    # On interdit donc a plugin.py de composer QUELQUE commande pip que ce
    # soit — la seule source est commande_pip_hecras() — et au LISEZMOI de
    # porter l'ancienne liste.
    _plugin = Path(__file__).resolve().parent
    _fautifs = []
    _source_plugin = (_plugin / "plugin.py").read_text(encoding="utf-8") \
        if (_plugin / "plugin.py").is_file() else ""
    for _marque in ("-m pip install", "ras-commander>="):
        if _marque in _source_plugin:
            _fautifs.append(f"plugin.py compose lui-meme « {_marque} »")
    _lisezmoi = _plugin / "LISEZMOI.md"
    if _lisezmoi.is_file() and 'install "ras-commander>=0.99" h5py' \
            in _lisezmoi.read_text(encoding="utf-8"):
        _fautifs.append("LISEZMOI.md porte la liste courte")
    print(f"   [{'OK' if not _fautifs else 'ECHEC'}] aucun texte distribue "
          f"n'annonce ni ne recompose la liste courte  ->  "
          f"{'aucun' if not _fautifs else _fautifs}")
    assert not _fautifs, _fautifs

    print("\n5. PK POUR AFFICHAGE DANS QGIS")
    affichage = pk_pour_affichage(chemins["sections"], chemins["axe"])
    print("   " + affichage[["nom", "pk_m", "croise_axe"]]
          .to_string(index=False).replace("\n", "\n   "))

    print("\n6. LECTEUR DE PROJET HEC-RAS  (pur texte, sans ras-commander)")
    # Le projet d'essai est DECLARE, jamais code en dur : ce fichier est livre
    # avec le plugin, et y inscrire le chemin d'une affaire cliente le
    # diffuserait a tous ceux qui l'installent — en plus de rendre l'auto-test
    # inexecutable ailleurs que sur le poste ou il a ete ecrit.
    #     set CALAGE_PROJET_ESSAI=<dossier d'un projet HEC-RAS>
    declare = os.environ.get("CALAGE_PROJET_ESSAI")
    projet_reel = Path(declare) if declare else None
    if projet_reel is not None and projet_reel.is_dir():
        info = lister_projet_hecras(projet_reel)
        print(f"   projet : {info['nom_projet']}")
        print(f"   {len(info['geometries'])} geometrie(s), "
              f"{len(info['unsteady'])} unsteady, {len(info['plans'])} plan(s)")
        if info["plans"]:
            premier = info["plans"][0]
            print(f"   premier plan : p{premier['numero']} — "
                  f"{premier['titre']}  (g{premier['geometrie']}, "
                  f"u{premier['unsteady']})")
            print(f"   fenetre : {premier['fenetre']['debut']} -> "
                  f"{premier['fenetre']['fin']}")
    else:
        print("   (aucun projet declare dans CALAGE_PROJET_ESSAI — non "
              "bloquant : le lecteur est exerce par test_plugin_qgis.py)")

    print("\n7. PONT VERS HEC-RAS")
    interpreteur = interpreteur_hecras()
    print(f"   interpreteur : {interpreteur}")
    if interpreteur is None:
        print(f"   introuvable — bouton « Installer… » du plugin "
              f"({len(pythons_candidats())} base(s) possible(s) sur ce "
              f"poste), ou « Designer… », ou {VARIABLE_INTERPRETEUR}")
    else:
        try:
            reponse = appeler_pont("verifier", delai=120)
            print(f"   python {reponse['python']}, "
                  f"ras-commander {reponse['ras_commander']}, "
                  f"h5py {reponse['h5py']}")
        except Exception as e:
            print(f"   ECHEC : {e}")

    print("\n8. ARBITRAGE ENTRE PLUSIEURS CHAINES  (le rang, plus jamais la date)")
    bac = Path(tempfile.mkdtemp(prefix="calage_chaines_"))

    def temoin(nom, quand):
        dossier_temoin = bac / nom
        dossier_temoin.mkdir()
        for fichier in FICHIERS_CHAINE:
            (dossier_temoin / fichier).write_text("", encoding="utf-8")
            os.utime(dossier_temoin / fichier, (quand, quand))
        return dossier_temoin

    # TEMOINS VOLONTAIREMENT ANCIENS. C'est tout l'objet de cet essai : sous
    # l'ancienne regle « la plus recente gagne », ils perdaient a coup sur
    # contre les vraies chaines du poste. Ils doivent maintenant l'emporter
    # par leur RANG. Rendre la regle de nouveau dependante des dates fait
    # echouer ce bloc.
    embarquee = temoin("embarquee_ancienne", time.time() - 86400)
    designee = temoin("designee_plus_ancienne_encore", time.time() - 172800)

    embarque_reel = DOSSIER_EMBARQUE
    choix_reel = _dossier_chaine
    dossier_projet = Path(__file__).resolve().parent.parent / "src"
    try:
        DOSSIER_EMBARQUE = embarquee
        if est_chaine(dossier_projet):
            retenue = trouver_chaine()
            assert retenue == embarquee, (
                f"la copie embarquee doit primer sur src/ du parent du "
                f"plugin meme en etant plus ancienne — retenue : {retenue}")
            print(f"   embarquee ({embarquee.name}, veille) l'emporte sur "
                  f"src/ du parent du plugin, pourtant plus recent")
        else:
            print("   src/ du parent du plugin non-chaine ici : rang non "
                  "departageable")

        assert definir_chaine(designee), "le temoin doit etre accepte"
        assert trouver_chaine() == designee, "le choix explicite doit primer"
        print(f"   choix explicite de « {designee.name} » -> respecte, bien "
              f"qu'il soit le plus ancien des trois")
    finally:
        DOSSIER_EMBARQUE = embarque_reel
        _dossier_chaine = choix_reel
        sys.path[:] = [p for p in sys.path if not p.startswith(str(bac))]
        shutil.rmtree(bac, ignore_errors=True)
        _raccorder()

    assert fraicheur(bac / "disparu") == 0.0, "un dossier absent vaut 0.0"
    assert fraicheur(None) == 0.0, "une valeur nulle vaut 0.0"
    print("   dossier absent ou nul -> fraicheur 0.0, jamais d'exception")
    print(f"   chaine retenue apres essais : {trouver_chaine()}")

    print("\n" + "=" * 72)
    print("\n9. UN MANQUE QUI N'EST PAS DANS NOTRE LISTE  (xarray)")
    # Production, 02/09/2026 : calage conforme apres 14 h, puis « profil en
    # long de synthese : non calculable (ModuleNotFoundError: No module named
    # 'xarray') ». xarray n'est a nous NI par l'import NI par la liste : c'est
    # ras-commander qui l'exige pour HdfResultsMesh. find_spec sur les dix
    # noms de PAQUETS_HECRAS ne pouvait pas le voir ; et sur une ras-commander
    # qui charge .hdf paresseusement, « import ras_commander » ne le voyait
    # pas non plus. L'interpreteur etait ACCEPTE.
    # AUCUN TELECHARGEMENT : « venv --without-pip » et des modules factices.
    bac_x = Path(tempfile.mkdtemp(prefix="calage_xarray_"))

    def interpreteur_sans_xarray(nom, paresseux):
        """
        Faux interpreteur : les modules de PAQUETS_HECRAS sont la, une
        ras_commander factice exige xarray pour HdfResultsMesh, et xarray est
        ABSENT. « paresseux » reproduit une ras-commander qui ne charge .hdf
        qu'a la demande — la seule forme ou le calage va jusqu'au bout avant
        de buter sur la figure.
        """
        cible = bac_x / nom
        subprocess.run([sys.executable, "-m", "venv", "--without-pip",
                        str(cible)], check=True, capture_output=True)
        paquets = site_packages(cible)
        for module in (i for i, _ in PAQUETS_HECRAS if i != "ras_commander"):
            (paquets / f"{module}.py").write_text("__version__ = '0.0'\n",
                                                  encoding="utf-8")
        rc = paquets / "ras_commander"
        (rc / "hdf").mkdir(parents=True)
        (rc / "hdf" / "__init__.py").write_text(
            "from .HdfResultsMesh import HdfResultsMesh\n", encoding="utf-8")
        # La classe et son corps sont deux litteraux, SEPARES : le nom de
        # classe suivi d'un saut de ligne echappe, ecrit d'un trait,
        # ressemble a un chemin pour le garde-fou d'attache. Aucune
        # lettre suivie de deux-points et d'une barre oblique inverse ici.
        (rc / "hdf" / "HdfResultsMesh.py").write_text(
            "import xarray as xr\n\n\nclass HdfResultsMesh:"
            "\n    pass\n",
            encoding="utf-8")
        (rc / "__init__.py").write_text(
            ("__version__ = '0.99.0'\n"
             "_TARDIFS = {'HdfResultsMesh'}\n"
             "def __getattr__(n):\n"
             "    if n in _TARDIFS:\n"
             "        from .hdf import HdfResultsMesh\n"
             "        return HdfResultsMesh\n"
             "    raise AttributeError(n)\n")
            if paresseux else
            ("__version__ = '0.99.1'\n"
             "from .hdf import HdfResultsMesh\n"), encoding="utf-8")
        # MEME REPLI QUE creer_venv_hecras : « Scripts\python.exe » sous
        # Windows, « bin/python » ailleurs. Sans lui, le refus tombait sur un
        # interpreteur INEXISTANT au lieu de tomber sur xarray, et le banc ne
        # prouvait plus ce qu'il annonce.
        interpreteur = cible / "Scripts" / "python.exe"
        if not interpreteur.is_file():
            interpreteur = cible / "bin" / "python"
        return interpreteur

    try:
        for nom_cas, tardif in (("chargement paresseux de .hdf", True),
                                ("chargement immediat de .hdf", False)):
            faux = interpreteur_sans_xarray(
                "paresseux" if tardif else "immediat", tardif)
            ok_x, msg_x = verifier_interpreteur(faux)
            assert not ok_x, (
                f"un interpreteur sans xarray doit etre REFUSE "
                f"({nom_cas}) — rendu : {msg_x}")
            # LE REFUS NE SUFFIT PAS : il doit NOMMER le module et donner la
            # commande. Un « ModuleNotFoundError » brut n'apprend a personne
            # quoi installer.
            assert "xarray" in msg_x and "pip install" in msg_x, (
                f"le refus doit nommer xarray et la commande pip "
                f"({nom_cas}) — rendu : {msg_x}")
            print(f"   {nom_cas} -> refuse, et la commande pip est donnee")
    finally:
        shutil.rmtree(bac_x, ignore_errors=True)

    print("\n10. L'INSTALLEUR COMPLETE CE QUE LA SONDE NOMME  (poste neuf, 03/09/2026)")
    # Environnement REUTILISE, ras-commander deja present sans xarray : pip
    # « --upgrade » ne le repare pas, et l'installeur repondait « inutilisable
    # : xarray absent... ou laisser le bouton Installer... » — le bouton qui
    # venait de tourner. AUCUN TELECHARGEMENT : pip est doublé, la sonde est
    # reelle.
    bac_i = Path(tempfile.mkdtemp(prefix="calage_installeur_"))
    _vrai_run = subprocess.run
    _vrai_emplacement = emplacement_venv_hecras
    pips = []

    def _run_double(commande, *a, **k):
        # La sonde (« -c ») tourne pour de vrai : c'est elle qu'on eprouve.
        # pip est enregistre et repond 0 sans rien poser : c'est ce que fait
        # un pip qui tient la contrainte pour satisfaite.
        if "-c" in commande:
            return _vrai_run(commande, *a, **k)
        pips.append(list(commande))
        return subprocess.CompletedProcess(commande, 0, stdout="", stderr="")

    try:
        faux_venv = bac_i / "venv-hecras"
        subprocess.run([sys.executable, "-m", "venv", "--without-pip",
                        str(faux_venv)], check=True, capture_output=True)
        paquets = site_packages(faux_venv)
        for module in (i for i, _ in PAQUETS_HECRAS if i != "ras_commander"):
            (paquets / f"{module}.py").write_text("__version__ = '0.0'\n",
                                                  encoding="utf-8")
        rc = paquets / "ras_commander"
        (rc / "hdf").mkdir(parents=True)
        (rc / "hdf" / "__init__.py").write_text(
            "from .HdfResultsMesh import HdfResultsMesh\n", encoding="utf-8")
        (rc / "hdf" / "HdfResultsMesh.py").write_text(
            "import xarray as xr\n\n\nclass HdfResultsMesh:"
            "\n    pass\n", encoding="utf-8")
        (rc / "__init__.py").write_text(
            "__version__ = '0.99.2'\nfrom .hdf import HdfResultsMesh\n",
            encoding="utf-8")

        globals()["emplacement_venv_hecras"] = lambda: faux_venv
        subprocess.run = _run_double
        chemin_i, message_i = installer_interpreteur(sys.executable)
    finally:
        subprocess.run = _vrai_run
        globals()["emplacement_venv_hecras"] = _vrai_emplacement
        shutil.rmtree(bac_i, ignore_errors=True)

    assert len(pips) == 2, (
        f"l'installeur doit lancer pip DEUX fois — le lot, puis le complement "
        f"que la sonde nomme — il l'a lance {len(pips)} fois : {pips}")
    assert pips[1][-1] == "xarray" and "--upgrade" not in pips[1], (
        f"le complement doit poser exactement ce que la sonde nomme : {pips[1]}")
    # pip etant double, xarray manque toujours : l'installeur DOIT echouer,
    # et son message ne doit plus conseiller le bouton qui vient d'echouer.
    assert chemin_i is None and "xarray" in message_i, message_i
    assert "Installer" not in message_i, (
        f"le message renvoie encore au bouton « Installer… » : {message_i}")
    print("   complement pose : pip install xarray, apres le lot")
    print("   message d'echec : nomme xarray et la commande, sans renvoyer au bouton")

    print("\n11. LE SUIVI SE LIT DANS LE CLASSEUR  (03/09/2026)")
    # Un calage lance sur le classeur d'un calcul precedent ecrivait son suivi
    # la ou CE classeur le dit ; la fenetre regardait les champs de l'onglet 3,
    # qui designaient le dossier du DERNIER paquet compose. Le suivi restait
    # muet devant un calage qui tournait. La regle est celle du pont.
    import pandas as pd
    bac_s = Path(tempfile.mkdtemp(prefix="calage_suivi_"))
    try:
        ailleurs = bac_s / "sortie_du_classeur"
        classeur_s = bac_s / "compose_ici" / "donnees_calage.xlsx"
        classeur_s.parent.mkdir()
        import parametres as _parametres
        _parametres.ecrire(classeur_s, {"Nom_projet": "Essai",
                                        "Dossier_sortie": str(ailleurs),
                                        "Sous_dossier_suivi": "suivi_q100"})
        trouve = dossier_suivi_du_classeur(classeur_s)
        assert trouve == ailleurs / "suivi_q100", (
            f"le suivi doit suivre Dossier_sortie et Sous_dossier_suivi du "
            f"classeur — rendu : {trouve}")
        print(f"   classeur compose dans {classeur_s.parent.name}, "
              f"suivi dans {trouve.parent.name}/{trouve.name} : c'est le classeur qui a parle")

        # Sans ces deux cles — classeur d'une version anterieure —, la regle
        # du pont vaut aussi : le dossier du classeur, sous-dossier « suivi ».
        _parametres.ecrire(classeur_s, {"Nom_projet": "Essai"})
        trouve = dossier_suivi_du_classeur(classeur_s)
        assert trouve == classeur_s.parent / "suivi", trouve
        print("   sans Dossier_sortie : le dossier du classeur, sous-dossier « suivi »")
    finally:
        shutil.rmtree(bac_s, ignore_errors=True)

    # -----------------------------------------------------------------
    print("\n12. CE QUE PORTENT LES CIBLES, ET SI HEC-RAS EST OUVERT")
    import numpy as _np
    import pandas as _pd

    bac_r = Path(tempfile.mkdtemp(prefix="calage_resume_"))
    try:
        _classeur_r = bac_r / "donnees.xlsx"
        # Un triangle de 0 a 10 h, pic 100 m3/s a 5 h : son volume vaut
        # 0.5 * base * hauteur = 0.5 * 10 h * 100 m3/s = 500 m3/s.h,
        # soit 500 * 3600 / 1e6 = 1.8 hm3. Un nombre qu'on peut poser a la
        # main, et c'est tout l'interet : la regle des trapezes est EXACTE
        # sur un triangle, l'ecart ne peut donc venir que du code.
        _t_r = _np.arange(0.0, 10.01, 0.5)
        _q_r = _np.where(_t_r <= 5.0, 100.0 * _t_r / 5.0,
                         100.0 * (10.0 - _t_r) / 5.0)
        with _pd.ExcelWriter(_classeur_r) as _ec:
            _pd.DataFrame({"Nom_Apport": ["A1", "A2"],
                           "Nom_Section": ["S1", "S2"],
                           "Nom_Cible": ["Cible_S1", "Cible_S2"]}
                          ).to_excel(_ec, sheet_name="Correspondance",
                                     index=False)
            # La seconde cible reste VIDE : c'est l'etat ordinaire d'un
            # classeur qu'on vient de composer.
            _pd.DataFrame({"Temps_h": _t_r, "Cible_S1": _q_r,
                           "Cible_S2": [None] * len(_t_r)}
                          ).to_excel(_ec, sheet_name="Cibles", index=False)

        _res = resume_cibles(_classeur_r)
        assert len(_res) == 2, _res
        assert _res[0]["renseignee"] and not _res[1]["renseignee"], _res
        assert abs(_res[0]["pic_m3s"] - 100.0) < 1e-9, _res[0]
        assert abs(_res[0]["heure_pic_h"] - 5.0) < 1e-9, _res[0]
        assert abs(_res[0]["volume_hm3"] - 1.8) < 1e-9, _res[0]["volume_hm3"]
        # UNE CIBLE VIDE N'EST PAS UN ZERO : rendre 0,0 hm3 la ferait passer
        # pour saisie et nulle, ce qui est un resultat, pas une absence.
        assert _res[1]["pic_m3s"] is None and _res[1]["volume_hm3"] is None
        print(f"   triangle 0-10 h, pic 100 m3/s a 5 h : "
              f"{_res[0]['volume_hm3']:.3f} hm3 (attendu 1,800), "
              f"la cible vide est dite « a saisir »")

        # LES COUPLES INCOMPLETS SORTENT DES DEUX SERIES ENSEMBLE. Integrer
        # des debits sur une base de temps trouee rendrait un nombre qui ne
        # veut rien dire — ici, la ligne a 5 h perd son instant, et le pic
        # avec.
        _t_troue = _t_r.astype(object).copy()
        _t_troue[10] = "n/c"                      # l'instant 5,0 h
        with _pd.ExcelWriter(_classeur_r) as _ec:
            _pd.DataFrame({"Nom_Apport": ["A1"], "Nom_Section": ["S1"],
                           "Nom_Cible": ["Cible_S1"]}
                          ).to_excel(_ec, sheet_name="Correspondance",
                                     index=False)
            _pd.DataFrame({"Temps_h": _t_troue, "Cible_S1": _q_r}
                          ).to_excel(_ec, sheet_name="Cibles", index=False)
        _res2 = resume_cibles(_classeur_r)
        assert _res2[0]["renseignee"], _res2
        assert abs(_res2[0]["pic_m3s"] - 90.0) < 1e-9, _res2[0]["pic_m3s"]
        print(f"   un instant illisible retire son debit : pic "
              f"{_res2[0]['pic_m3s']:.0f} m3/s au lieu de 100")

        # SANS COLONNE DE TEMPS, ON REFUSE — meme regle que etat_cibles, et
        # c'est la faute reelle du 04/09/2026.
        with _pd.ExcelWriter(_classeur_r) as _ec:
            _pd.DataFrame({"Nom_Apport": ["A1"], "Nom_Section": ["S1"],
                           "Nom_Cible": ["Cible_S1"]}
                          ).to_excel(_ec, sheet_name="Correspondance",
                                     index=False)
            _pd.DataFrame({"Heure": _t_r, "Cible_S1": _q_r}
                          ).to_excel(_ec, sheet_name="Cibles", index=False)
        try:
            resume_cibles(_classeur_r)
            raise AssertionError("une feuille Cibles sans Temps_h doit etre "
                                 "refusee")
        except ValueError as _e:
            assert "Temps_h" in str(_e), _e
            print("   feuille Cibles sans « Temps_h » : refusee, et l'en-tete "
                  "trouve est nomme")
    finally:
        shutil.rmtree(bac_r, ignore_errors=True)

    # HEC-RAS OUVERT : trois reponses possibles, et « je ne sais pas » en est
    # une. Le plugin ne pose sa question que sur True (voir _lancer_calage) :
    # demander « peut-etre ? » a chaque lancement apprendrait a repondre oui
    # sans lire.
    _ouvert = hecras_ouvert()
    assert _ouvert in (True, False, None), _ouvert
    print(f"   hecras_ouvert() rend {_ouvert!r} — jumeau de "
          f"pilote_hecras.hecras_ouvert, que le Python de QGIS ne peut pas "
          f"importer")

    print("\nNoyau operationnel. Le plugin ne fait qu'appeler ces fonctions.")
    print("=" * 72)
