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
import re
import time
import zipfile
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
DEPOT = DOSSIER.parent  # depot du projet : calage_apports/ est un sibling
                        # de src/, pas de ce fichier
SOURCE = DEPOT / "calage_apports"
ARCHIVE = DEPOT / "calage_apports.zip"

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
        # Ce controle portait sur deux mots — « OneDrive » et « 1-AFFAIRES ».
        # Il a laisse partir « d:\1-Python » dans noyau.py pendant des
        # semaines, et l'essai equivalent de test_plugin_qgis.py portait meme
        # ce chemin en liste blanche : le garde-fou etait ecrit pour ignorer
        # exactement ce qu'il devait voir.
        #
        # LE CRITERE EST DESORMAIS « CE CHEMIN EXISTE-T-IL ICI ? ». Un chemin
        # absolu qui se resout sur la machine qui construit l'archive est,
        # par construction, un chemin de CETTE machine — c'est la signature
        # meme du chemin d'auteur. Un chemin de demonstration volontairement
        # inexistant (« D:\projet », employe par les auto-tests pour eprouver
        # le controle d'un dossier absent) passe sans exception nominative.
        # Les emplacements d'INSTALLATION restent legitimes : ils sont les
        # memes sur tout poste Windows.
        racines_logicielles = ("c:\\windows", "c:\\program files")
        chemins_absolus = re.compile(r"[A-Za-z]:\\[^\"'\n\r]{3,}")
        affaires = re.compile(
            r"Las[_ ]?Hies|Kondiztegi|Ourse|Ardanavy|CETTE_TEST|CASTEST"
            r"|KON_\d|LH[2-8]\b|OneDrive|1-AFFAIRES", re.IGNORECASE)
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
            for brut in chemins_absolus.findall(texte):
                chemin = brut.strip().rstrip(".,;:)»\"'")
                if chemin.lower().startswith(racines_logicielles):
                    continue
                if Path(chemin).exists():
                    echecs.append(f"chemin du poste dans {nom} : « {chemin} » "
                                  f"(il existe ici, il n'existera pas ailleurs)")
            for mot in sorted(set(affaires.findall(texte))):
                echecs.append(f"nom d'affaire ou de cas d'essai dans {nom} : "
                              f"« {mot} »")

    print()
    if echecs:
        for e in echecs:
            print(f"   ECHEC : {e}")
        raise SystemExit(1)
    print("   archive conforme")
