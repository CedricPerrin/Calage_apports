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
#   - par lien symbolique depuis le dossier projet : le parent du plugin EST
#     la chaine ;
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
    Emplacements connus portant une chaine valide, DANS L'ORDRE DE PRIORITE,
    sans doublon.

    L'ordre est celui de trouver_chaine() : la copie embarquee d'abord, parce
    qu'elle est celle livree avec CE plugin et la seule dont on reponde ; le
    parent du plugin ensuite, qui n'est la chaine que pour une installation
    par lien symbolique — et dans ce cas la copie embarquee n'existe pas sur
    le disque, faire_zip.py ne la materialisant que dans l'archive. Les deux
    ne sont donc jamais en concurrence reelle.
    """
    parent_du_plugin = Path(__file__).resolve().parent.parent
    retenues = {}
    for candidate in (DOSSIER_EMBARQUE, parent_du_plugin):
        if est_chaine(candidate):
            retenues.setdefault(Path(candidate).resolve(), Path(candidate))
    return list(retenues.values())


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


DOSSIER_CHAINE = _raccorder()

NOMS_FICHIERS = {
    "sections": "sections_controle.shp",
    "apports": "lignes_injection.shp",
    "axe": "axe_hydraulique.shp",
    "classeur": "donnees_calage.xlsx",
}


def chaine_disponible():
    """
    Verifie que la chaine de calage est accessible depuis l'interpreteur
    courant. Retourne (disponible, [messages]).

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

    for module in ("criteres", "geometrie", "controle_donnees", "livrables"):
        try:
            __import__(module)
        except Exception as e:
            messages.append(f"{module}.py illisible : {e}")

    interpreteur = interpreteur_hecras()
    if interpreteur is None:
        messages.append("interpreteur HEC-RAS introuvable : les operations sur "
                        "le modele seront indisponibles")
    else:
        messages.append(f"interpreteur HEC-RAS : {interpreteur}")

    return not manquants, messages


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


def interpreteur_hecras():
    """
    Interpreteur capable d'importer ras-commander, ou None. Recherche, dans
    l'ordre : la valeur declaree a l'execution, la variable d'environnement
    CALAGE_PYTHON, puis les .venv voisins de la chaine retenue.

    AUCUN EMPLACEMENT N'EST DEVINE AU-DELA DE CA, et c'est voulu. Un
    interpreteur trouve « quelque part » serait accepte sans que personne ne
    sache d'ou il vient ; sur un poste ou il manque, la reponse honnete est de
    le DEMANDER — le diagnostic du plugin propose de le designer et le retient.
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


def verifier_interpreteur(chemin):
    """
    Cet interpreteur sait-il piloter HEC-RAS ? Retourne (ok, message).

    Le test est celui qui compte : importer ras-commander ET h5py dans un
    sous-processus, avec le meme assainissement d'environnement que les appels
    reels. Verifier la seule existence du fichier ne prouverait rien.
    """
    import subprocess

    chemin = Path(chemin)
    if not chemin.is_file():
        return False, f"« {chemin} » n'est pas un fichier."
    code = ("import ras_commander, h5py, sys; "
            "print(f'python {sys.version_info.major}.{sys.version_info.minor}"
            ".{sys.version_info.micro}, ras-commander "
            "{ras_commander.__version__}, h5py {h5py.__version__}')")
    try:
        # DECODAGE IMPOSE, ET TOLERANT. Sans lui, Python decode la sortie dans
        # l'encodage ambiant : un interpreteur qui echoue en ecrivant des
        # octets qui n'y sont pas valides — le python de QGIS, justement, celui
        # que ce controle doit refuser — tuait le fil de lecture de subprocess
        # sur une UnicodeDecodeError, et la raison de l'echec se perdait au
        # moment precis ou elle sert. Meme regle qu'a l'appel du pont.
        acheve = subprocess.run(
            [str(chemin), "-c", code], capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=90, env=environnement_propre(chemin))
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
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
        raise RuntimeError(
            f"aucun interpreteur capable de piloter HEC-RAS n'a ete trouve. "
            f"Definir la variable d'environnement {VARIABLE_INTERPRETEUR} sur "
            f"le python.exe d'un environnement disposant de ras-commander.")

    commande = [str(interpreteur), str(chaine / "pont_hecras.py"),
                *[str(a) for a in arguments]]
    try:
        acheve = subprocess.run(commande, capture_output=True, text=True,
                                timeout=delai, encoding="utf-8", errors="replace",
                                env=environnement_propre(interpreteur))
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
    chemin = dossier / NOMS_FICHIERS["classeur"]

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
        "Nb_max_iterations_par_apport": 6,
        "Source_geometrie": "SHP",
        "Fichier_SHP_Sections": str(chemins_shp.get("sections", "")),
        "Fichier_SHP_Apports": str(chemins_shp.get("apports", "")),
        "Fichier_SHP_Axe": str(chemins_shp.get("axe", "")),
        "Sens_axe": "amont_aval",
        "Champ_nom_SHP": "nom",
        "PK_origine_m": 0,
        "Source_profil_en_long": "MODELE",
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

    with pd.ExcelWriter(chemin, engine="openpyxl") as w:
        pd.DataFrame({"Parametre": list(valeurs), "Valeur": list(valeurs.values())}
                     ).to_excel(w, sheet_name="Parametres", index=False)
        correspondance.to_excel(w, sheet_name="Correspondance", index=False)
        cibles.to_excel(w, sheet_name="Cibles", index=False)

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


def lire_avancement(dossier_suivi):
    """
    Etat courant du calage, tel que suivi.py le reecrit a chaque essai.

    Retourne None si aucun calage n'a encore ecrit dans ce dossier — ce n'est
    pas une erreur, c'est l'etat normal avant le lancement.

    La lecture ne leve JAMAIS : le fichier est reecrit pendant qu'on le lit.
    L'ecriture est atomique du cote de suivi.py, mais un antivirus ou un
    partage reseau peuvent malgre tout rendre un instantane illisible ; dans
    ce cas on garde simplement l'affichage precedent.
    """
    chemin = Path(dossier_suivi) / "avancement.json"
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


def etat_cibles(chemin_classeur):
    """
    Combien d'hydrogrammes cibles restent a saisir dans le classeur : c'est
    l'information qui guide l'etape suivante — completer la feuille Cibles —
    avant de lancer le calage.

    Une cible est consideree renseignee des qu'elle comporte au moins une
    valeur non vide ; controle_donnees.py verifie deja separement qu'un
    hydrogramme partiel ou incoherent est signale.

    Retourne {"total", "renseignees", "manquantes": [noms de section]}.
    """
    import pandas as pd

    corr = pd.read_excel(chemin_classeur, sheet_name="Correspondance")
    cibles = pd.read_excel(chemin_classeur, sheet_name="Cibles")
    col_section = next(c for c in corr.columns if c.startswith("Nom_Section"))
    col_cible = next(c for c in corr.columns if c.startswith("Nom_Cible"))

    manquantes = []
    for _, ligne in corr.dropna(subset=[col_section, col_cible]).iterrows():
        nom_cible = str(ligne[col_cible])
        renseignee = (nom_cible in cibles.columns
                      and cibles[nom_cible].notna().any())
        if not renseignee:
            manquantes.append(str(ligne[col_section]))

    total = len(corr.dropna(subset=[col_section, col_cible]))
    return {"total": total, "renseignees": total - len(manquantes),
            "manquantes": manquantes}


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


def ecrire_parametre(chemin_classeur, cle, valeur):
    """
    Ecrit une valeur dans la feuille Parametres d'un classeur existant.

    Sert aux reglages qui se decident AU LANCEMENT et non a la composition —
    « Premier_apport » en premier lieu : choisir par ou reprendre ne doit pas
    obliger a recomposer tout le paquet.

    La feuille est reecrite en conservant la mise en forme du classeur :
    openpyxl modifie la cellule sur place, la ou pandas reconstruirait le
    fichier et perdrait styles, commentaires et listes deroulantes.
    """
    import openpyxl

    classeur = openpyxl.load_workbook(chemin_classeur)
    feuille = classeur["Parametres"]
    for ligne in feuille.iter_rows(min_row=1, max_col=2):
        if str(ligne[0].value).strip() == cle:
            ligne[1].value = valeur
            classeur.save(chemin_classeur)
            return True
    # La cle peut manquer d'un classeur compose par une version anterieure :
    # on l'ajoute plutot que d'echouer, sinon le reglage serait perdu sans que
    # rien ne le dise.
    feuille.cell(row=feuille.max_row + 1, column=1, value=cle)
    feuille.cell(row=feuille.max_row, column=2, value=valeur)
    classeur.save(chemin_classeur)
    return False


def controler_paquet(chemin_classeur, contre_modele=True):
    """
    Controle complet du paquet : saisie, chaine geographique, PK et ordre,
    puis — si un modele est joignable — confrontation a la geometrie reelle.

    Delegue integralement a controle_donnees.py : aucune regle n'est
    reimplementee ici. Le controle contre le modele passe par le pont, car il
    exige ras-commander, inutilisable dans le processus QGIS.

    Retourne (anomalies, tableau_pk).
    """
    import controle_donnees as cd

    anomalies = cd.controler_template(chemin_classeur)
    geo_anomalies, tableau = cd.controler_geometrie(chemin_classeur)
    anomalies += geo_anomalies

    if contre_modele:
        try:
            reponse = appeler_pont("controler-modele", "--template",
                                   chemin_classeur)
            anomalies += [(cd.ERREUR, m) for m in reponse.get("erreurs", [])]
            anomalies += [(cd.AVERTISSEMENT, m)
                          for m in reponse.get("avertissements", [])]
        except Exception as e:
            anomalies.append((
                cd.AVERTISSEMENT,
                f"controle contre le modele non effectue : {e}"))

    return anomalies, tableau


def chemins_du_classeur(chemin_classeur):
    """
    Chemins des shapefiles et sens de l'axe, relus DANS le classeur.

    Le plugin doit pouvoir controler un paquet compose lors d'une session
    precedente : se fier a ce qui est en memoire priverait l'utilisateur de la
    couche des PK des qu'il rouvre QGIS.
    """
    import pandas as pd

    par = pd.read_excel(chemin_classeur, sheet_name="Parametres")
    valeurs = dict(zip(par["Parametre"], par["Valeur"]))

    def chemin(cle):
        v = valeurs.get(cle)
        if v is None or pd.isna(v) or not str(v).strip():
            return None
        p = Path(str(v))
        return p if p.exists() else None

    return {
        "sections": chemin("Fichier_SHP_Sections"),
        "apports": chemin("Fichier_SHP_Apports"),
        "axe": chemin("Fichier_SHP_Axe"),
        "sens": str(valeurs.get("Sens_axe", "amont_aval") or "amont_aval").strip(),
    }


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

def lister_objets_modele(hdf_plan):
    """Sections de controle et lignes d'injection presentes dans le modele."""
    reponse = appeler_pont("lister", "--plan", hdf_plan)
    return {"sections": reponse["sections"], "apports": reponse["apports"]}


def lire_hydrogramme(hdf_plan, nom_section, nom_zone_2d=None, sortie=None,
                     groupe="Reference Lines"):
    """
    Debit calcule a travers une section de controle, ecrit en CSV.

    groupe : « Reference Lines » pour une section de controle, « Boundary
    Conditions » pour relire un apport tel qu'il a ete injecte — utile pour
    verifier qu'un hydrogramme d'apport a bien ete pris en compte.

    Retourne le dict de reponse : voie utilisee, nombre de pas de temps,
    duree, debit de pointe, volume et chemin du fichier.
    """
    arguments = ["hydrogramme", "--plan", hdf_plan, "--section", nom_section,
                 "--groupe", groupe]
    if nom_zone_2d:
        arguments += ["--zone", nom_zone_2d]
    if sortie:
        arguments += ["--sortie", sortie]
    return appeler_pont(*arguments)


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
        raise RuntimeError(
            f"aucun interpreteur capable de piloter HEC-RAS n'a ete trouve. "
            f"Definir la variable d'environnement {VARIABLE_INTERPRETEUR}.")

    chemin_classeur = Path(chemin_classeur)
    horodatage = time.strftime("%Y%m%d_%H%M%S")
    journal = chemin_classeur.parent / f"calage_{horodatage}.log"

    commande = [str(interpreteur), str(chaine / "pont_hecras.py"),
                "caler", "--template", str(chemin_classeur)]
    drapeaux = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        drapeaux = (subprocess.DETACHED_PROCESS
                    | subprocess.CREATE_NEW_PROCESS_GROUP)

    fichier_journal = open(journal, "w", encoding="utf-8")
    processus = subprocess.Popen(
        commande, stdout=fichier_journal, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, env=environnement_propre(interpreteur),
        creationflags=drapeaux, close_fds=True)
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

    print("=" * 72)
    print("AUTO-TEST DU NOYAU DU PLUGIN  (hors QGIS)")
    print("=" * 72)

    print(f"\nChaine de calage : {DOSSIER_CHAINE}")
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
    anomalies, tableau = controler_paquet(classeur)
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
        print("   introuvable — definir CALAGE_PYTHON")
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
    parent_du_plugin = Path(__file__).resolve().parent.parent
    try:
        DOSSIER_EMBARQUE = embarquee
        if est_chaine(parent_du_plugin):
            retenue = trouver_chaine()
            assert retenue == embarquee, (
                f"la copie embarquee doit primer sur le parent du plugin meme "
                f"en etant plus ancienne — retenue : {retenue}")
            print(f"   embarquee ({embarquee.name}, veille) l'emporte sur le "
                  f"parent du plugin, pourtant plus recent")
        else:
            print("   parent du plugin non-chaine ici : rang non departageable")

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
    print("Noyau operationnel. Le plugin ne fait qu'appeler ces fonctions.")
    print("=" * 72)
