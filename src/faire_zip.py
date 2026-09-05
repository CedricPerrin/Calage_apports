# -*- coding: utf-8 -*-
"""
Construit l'archive d'installation du plugin QGIS.

Existe parce que l'empaquetage a la main s'est trompe deux fois :
une archive contenant __pycache__ — du bytecode perime qui masque les sources,
et fait croire a un defaut deja corrige — puis une archive oubliant le
sous-dossier styles/, laissant les couches sans symbologie.

LISTE BLANCHE d'extensions, jamais une liste d'exclusions : QGIS depose des
fichiers dans le repertoire courant des qu'on l'instancie, et une liste noire
ne protege que de ce qu'on a deja vu passer.

L'ARCHIVE EST AUTOPORTANTE : elle embarque la chaine de calage sous
calage_apports/chaine/. Sur un poste neuf, installer l'extension suffit, il
n'y a plus rien a deposer a cote ni de variable a definir.

LA COPIE EMBARQUEE N'EXISTE QUE DANS L'ARCHIVE, jamais sur le disque. Une
copie materialisee dans calage_apports/chaine/ serait editee un jour par
megarde, et deux versions de calage.py cohabiteraient sans que rien ne le
signale. Les modules sont donc lus a la racine du projet et ecrits
directement dans le zip.

Usage :  python faire_zip.py
"""
import ast
import builtins
import re
import time
import zipfile
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
DEPOT = DOSSIER.parent  # depot du projet : calage_apports/ est un sibling
                        # de src/, pas de ce fichier
SOURCE = DEPOT / "calage_apports"
ARCHIVE = DEPOT / "calage_apports.zip"

# Mots interdits dans ce qui est distribue : noms d'affaires, identifiants de
# cas d'essai, dossiers de synchronisation.
#
# ILS NE SONT PAS ECRITS ICI. Ce fichier est suivi par git et le depot est
# pousse : y lister les clients de la maison reviendrait a publier ce que le
# garde-fou existe precisement pour retenir. La liste vit dans « .affaires » a
# la racine du depot, NON SUIVI (.gitignore), un mot par ligne — voir
# .affaires.exemple.
#
# ABSENTE, LE CONTROLE DES NOMS NE TOURNE PAS, et le dit fort. Celui des
# chemins, lui, tourne toujours : il ne repose sur aucune liste — « ce chemin
# absolu se resout-il sur la machine qui construit l'archive ? » — et c'est le
# plus solide des deux.
FICHIER_AFFAIRES = DEPOT / ".affaires"


def mots_d_affaires():
    """Mots interdits, lus dans .affaires. Liste vide s'il n'existe pas."""
    if not FICHIER_AFFAIRES.is_file():
        return []
    return [m.strip() for m in
            FICHIER_AFFAIRES.read_text(encoding="utf-8").splitlines()
            if m.strip() and not m.startswith("#")]


# Emplacements d'INSTALLATION : identiques sur tout poste Windows, donc
# legitimes dans du code distribue. Il faut bien savoir ou HEC-RAS s'installe,
# et le repli sur C:\Windows sert quand SystemRoot manque a l'environnement.
RACINES_LOGICIELLES = ("c:\\windows", "c:\\program files")
_CHEMINS_ABSOLUS = re.compile(r"[A-Za-z]:\\[^\"'\n\r]{3,}")


def chemins_du_poste(texte):
    """
    Les chemins absolus de CETTE machine presents dans un texte.

    LE CRITERE EST « CE CHEMIN EXISTE-T-IL ICI ? ». Un chemin absolu qui se
    resout sur la machine qui controle est, par construction, un chemin de
    cette machine — c'est la signature meme du chemin d'auteur. Un chemin de
    demonstration volontairement inexistant (« D:\\projet », ou le
    « C:\\Users\\x\\Python313\\python.exe » dont l'auto-test de noyau.py
    eprouve la lecture) passe sans qu'aucune exception nominative soit posee.

    UNE SEULE DEFINITION, ET C'EST TOUT L'INTERET. Une seconde version, a
    LISTE BLANCHE, vivait dans test_plugin_qgis.py et portait « d:\\1-Python »
    — le poste de l'auteur — parmi ses exceptions : elle etait ecrite pour
    ignorer exactement ce qu'elle devait voir, et a laisse ce chemin partir
    dans noyau.py pendant des semaines. Recopier un garde-fou, c'est le vouer
    a diverger de son jumeau. Les deux appellent donc ceci.
    """
    trouves = []
    for brut in _CHEMINS_ABSOLUS.findall(texte):
        chemin = brut.strip().rstrip(".,;:)»\"'")
        if chemin.lower().startswith(RACINES_LOGICIELLES):
            continue
        if Path(chemin).exists():
            trouves.append(chemin)
    return trouves


EXTENSIONS = {".py", ".txt", ".md", ".png", ".qml", ".svg"}
# Le nom du dossier racine de l'archive EST le nom du paquet pour QGIS, et le
# repertoire sous lequel l'extension s'installe. Il ne doit pas changer.
RACINE = "calage_apports"

# Sous-dossier de l'archive ou atterrit la chaine. Doit rester accorde a
# noyau.DOSSIER_EMBARQUE, que le controle final verifie.
CHAINE = "chaine"

# CE QUE LE PLUGIN APPELLE VRAIMENT, et rien de plus : pont_hecras.py est le
# script lance en sous-processus (caler, modele, controler-modele), les autres
# sont importes par noyau.py. Le reste de la chaine suit tout seul, par
# fermeture des imports — voir modules_chaine().
ENTREES_CHAINE = ("pont_hecras", "pilote_hecras", "geometrie",
                  "controle_donnees", "style_classeur", "criteres",
                  "livrables")

# Les cinq marqueurs auxquels noyau.est_chaine reconnait un dossier de chaine.
# La copie embarquee doit evidemment les contenir, sinon le plugin ne la
# verrait meme pas.
MARQUEURS = ("criteres.py", "geometrie.py", "controle_donnees.py",
             "livrables.py", "pont_hecras.py")


def fichiers_a_livrer():
    """Fichiers retenus, tries, chemins relatifs au dossier du plugin."""
    retenus = []
    for chemin in sorted(SOURCE.rglob("*")):
        if not chemin.is_file():
            continue
        if "__pycache__" in chemin.parts:
            continue
        if chemin.suffix.lower() not in EXTENSIONS:
            continue
        retenus.append(chemin)
    return retenus


def imports_locaux(module, connus):
    """Modules de la racine du projet qu'importe « module »."""
    arbre = ast.parse((DOSSIER / f"{module}.py").read_text(encoding="utf-8"))
    trouves = set()
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            trouves |= {a.name.split(".")[0] for a in noeud.names}
        elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
            trouves.add(noeud.module.split(".")[0])
    return trouves & connus


# Dunders que Python pose lui-meme dans tout module : ils sont lus sans
# jamais avoir ete ecrits.
_DUNDERS_MODULE = frozenset((
    "__file__", "__name__", "__doc__", "__package__", "__spec__",
    "__loader__", "__builtins__", "__debug__"))


def _noms_lies(arbre):
    """Tout ce qu'un fichier LIE, a n'importe quelle portee."""
    lies = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            lies |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            lies |= {a.asname or a.name for a in n.names}
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                            ast.ClassDef)):
            lies.add(n.name)
            arguments = getattr(n, "args", None)
            if arguments is not None:
                lies |= _noms_arguments(arguments)
        elif isinstance(n, ast.Lambda):
            lies |= _noms_arguments(n.args)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            lies.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            lies.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            lies.update(n.names)
    return lies


def _noms_arguments(arguments):
    """Noms de tous les parametres d'une signature, forme par forme."""
    tous = (list(arguments.posonlyargs) + list(arguments.args)
            + list(arguments.kwonlyargs)
            + ([arguments.vararg] if arguments.vararg else [])
            + ([arguments.kwarg] if arguments.kwarg else []))
    return {a.arg for a in tous}


def noms_jamais_lies(source):
    """
    Noms LUS par ce fichier sans y avoir jamais ete lies : {nom: [lignes]}.

    POURQUOI CE CONTROLE EXISTE. « re » a ete employe dans pont_hecras.py sans
    y etre importe, a l'interieur d'un « except Exception » qui rendait le
    NameError sous la forme d'un probleme d'environnement. Le repli des pentes
    y a perdu un echelon sans que rien ne le dise, pendant des semaines. Un
    module qui s'importe et se compile ne prouve rien : la faute n'apparait
    qu'a l'execution de CETTE branche-la, et elle etait attrapee.

    DELIBEREMENT AVEUGLE AUX PORTEES. On rassemble ce que le fichier lie
    N'IMPORTE OU, puis on signale ce qui n'y figure pas. Cela ne voit donc PAS
    un nom lie dans une fonction et lu dans une autre — ce n'est pas un
    verificateur de portees, et ne pretend pas l'etre. En echange, il ne rend
    aucun faux positif, ce qui est la seule facon qu'un garde-fou d'archive
    soit cru : mesure du 05/09/2026 sur les 25 800 lignes du projet, une seule
    sortie, la vraie.

    Rend None sur un fichier portant « from x import * » : on ne peut alors
    rien affirmer, et affirmer quand meme serait pire que se taire.
    """
    arbre = ast.parse(source)
    if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
           for n in ast.walk(arbre)):
        return None
    connus = _noms_lies(arbre) | set(dir(builtins)) | _DUNDERS_MODULE
    inconnus = {}
    for n in ast.walk(arbre):
        if (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                and n.id not in connus):
            inconnus.setdefault(n.id, []).append(n.lineno)
    return inconnus


def modules_chaine():
    """
    Modules a embarquer : les entrees, plus tout ce qu'elles importent, de
    proche en proche.

    CALCULEE, JAMAIS ECRITE A LA MAIN. Une liste figee aurait tenu jusqu'au
    jour ou un module de la chaine en importe un nouveau : l'archive serait
    partie sans lui, et l'extension aurait echoue a l'installation chez
    quelqu'un d'autre, sur un ImportError que rien n'annoncait ici.
    """
    connus = {p.stem for p in DOSSIER.glob("*.py")}
    vus, a_voir = set(), list(ENTREES_CHAINE)
    while a_voir:
        module = a_voir.pop()
        if module in vus:
            continue
        vus.add(module)
        a_voir += list(imports_locaux(module, connus) - vus)
    return sorted(vus)


def construire():
    if not (SOURCE / "metadata.txt").is_file():
        raise SystemExit(f"{SOURCE} ne contient pas metadata.txt")

    fichiers = fichiers_a_livrer()
    modules = modules_chaine()
    manquants = [m for m in MARQUEURS if m[:-3] not in modules]
    if manquants:
        raise SystemExit(
            f"la chaine calculee ne contient pas {manquants} : le plugin ne "
            f"reconnaitrait pas sa propre copie embarquee.")

    if ARCHIVE.exists():
        ARCHIVE.unlink()
    # as_posix() n'est PAS cosmetique : une archive ZIP separe ses chemins par
    # « / ». Sous Windows, relative_to() rend des « \ », et l'entree produite
    # devient un fichier dont le nom contient un antislash au lieu d'un
    # sous-dossier — les styles ne seraient jamais trouves.
    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as zf:
        for chemin in fichiers:
            zf.write(chemin, f"{RACINE}/{chemin.relative_to(SOURCE).as_posix()}")
        for module in modules:
            zf.write(DOSSIER / f"{module}.py",
                     f"{RACINE}/{CHAINE}/{module}.py")
        # SE DIRE COPIE, ET DIRE DE QUAND. Ouvert dans le profil QGIS, un
        # calage.py sans cette note se prend pour la source et s'edite ; la
        # correction se perd a la reinstallation suivante.
        zf.writestr(
            f"{RACINE}/{CHAINE}/PROVENANCE.txt",
            "Copie de la chaine de calage embarquee dans l'extension QGIS.\n"
            f"Produite par faire_zip.py le "
            f"{time.strftime('%d/%m/%Y a %H:%M')}.\n\n"
            "NE PAS MODIFIER CES FICHIERS : ce sont des copies. Corriger les\n"
            "sources du projet, puis relancer faire_zip.py.\n\n"
            "Le plugin ne se sert de cette copie QUE s'il ne trouve aucune\n"
            "chaine externe (variable CALAGE_CHAINE, dossier parent, ou\n"
            "emplacement par defaut). La provenance retenue est affichee dans\n"
            "le diagnostic du plugin.\n\n"
            "Modules embarques :\n"
            + "".join(f"  - {m}.py\n" for m in modules))

    print(f"{ARCHIVE.name} — {ARCHIVE.stat().st_size / 1024:.1f} ko, "
          f"{len(fichiers) + len(modules) + 1} fichier(s)")
    for chemin in fichiers:
        print(f"   {RACINE}/{chemin.relative_to(SOURCE).as_posix()}")
    print(f"   --- chaine embarquee ({len(modules)} modules) ---")
    for module in modules:
        print(f"   {RACINE}/{CHAINE}/{module}.py")
    return fichiers, modules


if __name__ == "__main__":
    fichiers, modules = construire()

    # CONTROLES DE L'ARCHIVE PRODUITE, pas des fichiers sources : c'est
    # l'archive qui part chez l'utilisateur.
    echecs = []
    with zipfile.ZipFile(ARCHIVE) as zf:
        noms = zf.namelist()
        for attendu in (f"{RACINE}/metadata.txt", f"{RACINE}/__init__.py",
                        f"{RACINE}/plugin.py", f"{RACINE}/noyau.py",
                        f"{RACINE}/icon.png", f"{RACINE}/LICENSE.txt",
                        f"{RACINE}/styles/injections.qml",
                        f"{RACINE}/styles/sections.qml",
                        f"{RACINE}/styles/maillage.qml"):
            if attendu not in noms:
                echecs.append(f"absent de l'archive : {attendu}")

        # L'ARCHIVE EST-ELLE VRAIMENT AUTOPORTANTE ? Les cinq marqueurs sont
        # ce a quoi noyau.est_chaine reconnait une chaine : sans eux, le
        # dossier embarque est invisible et l'extension retombe sur une chaine
        # externe — donc sur rien, chez quelqu'un qui n'en a pas.
        for marqueur in MARQUEURS:
            if f"{RACINE}/{CHAINE}/{marqueur}" not in noms:
                echecs.append(f"chaine embarquee incomplete : {marqueur}")
        # Le sous-dossier doit etre celui que le plugin regarde. Les deux noms
        # sont ecrits dans deux fichiers differents, ils peuvent diverger.
        source_noyau = (SOURCE / "noyau.py").read_text(encoding="utf-8")
        if f'parent / "{CHAINE}"' not in source_noyau:
            echecs.append(f"noyau.py ne cherche pas la chaine embarquee dans "
                          f"« {CHAINE}/ »")
        # Chaque module embarque doit etre l'exact jumeau de sa source : un
        # zip construit sur un arbre a moitie enregistre livrerait du code
        # ancien sans que rien ne le dise.
        for module in modules:
            if zf.read(f"{RACINE}/{CHAINE}/{module}.py") != \
                    (DOSSIER / f"{module}.py").read_bytes():
                echecs.append(f"{module}.py embarque differe de la source")
        if any("__pycache__" in n or n.endswith(".pyc") for n in noms):
            echecs.append("l'archive contient du bytecode")
        for nom in noms:
            if not nom.startswith(f"{RACINE}/"):
                echecs.append(f"hors du dossier {RACINE}/ : {nom}")
            if "\\" in nom:
                echecs.append(f"separateur Windows dans l'archive : {nom}")
        # RIEN QUI DESIGNE LE POSTE OU L'AFFAIRE.
        #
        # Ce controle portait sur deux mots seulement, tous deux des dossiers
        # de synchronisation.
        # Il a laisse partir « d:\1-Python » dans noyau.py pendant des
        # semaines, et l'essai equivalent de test_plugin_qgis.py portait meme
        # ce chemin en liste blanche : le garde-fou etait ecrit pour ignorer
        # exactement ce qu'il devait voir.
        #
        # LE CRITERE EST DESORMAIS « CE CHEMIN EXISTE-T-IL ICI ? » — voir
        # chemins_du_poste(), qui le porte pour ce controle ET pour son jumeau
        # de test_plugin_qgis.py.
        mots = mots_d_affaires()
        affaires = (re.compile("|".join(re.escape(m) for m in mots),
                               re.IGNORECASE) if mots else None)
        if affaires is None:
            print(f"   AVERTISSEMENT : {FICHIER_AFFAIRES.name} absent — les "
                  f"noms d'affaires ne sont PAS controles (les chemins, si).")
        # LES .qml EN FONT PARTIE. Ils n'y etaient pas, et c'est par la que
        # le defaut serait rentre : un fichier de style se regenere d'un clic
        # droit « Enregistrer le style » DANS UN PROJET D'AFFAIRE, et emporte
        # alors volontiers un nom de couche client ou le chemin de sa source
        # de donnees. Les trois .qml pesent 62 ko de texte — 10 ko une fois
        # compresses, sur une archive de 271 ko — et aucun n'etait regarde.
        for nom in noms:
            if not nom.endswith((".py", ".md", ".txt", ".qml")):
                continue
            texte = zf.read(nom).decode("utf-8", errors="replace")
            for chemin in chemins_du_poste(texte):
                echecs.append(f"chemin du poste dans {nom} : « {chemin} » "
                              f"(il existe ici, il n'existera pas ailleurs)")
            if affaires is not None:
                for mot in sorted(set(affaires.findall(texte))):
                    echecs.append(f"nom d'affaire ou de cas d'essai dans "
                                  f"{nom} : « {mot} »")
            # UN NOM LU SANS AVOIR ETE LIE — voir noms_jamais_lies(). Un
            # « import » oublie ne fait echouer ni l'import du module, ni sa
            # compilation : il attend la branche qui l'emploie, et un
            # « except » large le deguise en panne d'environnement.
            if nom.endswith(".py"):
                try:
                    inconnus = noms_jamais_lies(texte)
                except SyntaxError as e:
                    echecs.append(f"{nom} ne compile pas : {e}")
                    inconnus = None
                for inconnu, lignes in sorted((inconnus or {}).items()):
                    echecs.append(
                        f"nom jamais lie dans {nom} : « {inconnu} » lu ligne(s) "
                        f"{', '.join(str(l) for l in lignes)} — import oublie ?")

    print()
    if echecs:
        for e in echecs:
            print(f"   ECHEC : {e}")
        raise SystemExit(1)
    print("   archive conforme")
