# -*- coding: utf-8 -*-
"""
Elague d'un projet HEC-RAS les branches mortes laissees par des calages.

OUTIL DE RATTRAPAGE POUR LES PROJETS CALES PAR L'ANCIENNE CHAINE, celle qui
clonait un plan unique titre « Calage_apports » et en accumulait un par
relance. La chaine actuelle ne travaille plus ainsi : elle cree un plan et un
unsteady PAR ETAPE — « sans_apport », puis « Apport_<nom> » — et les CONSERVE
volontairement (voir pilote_hecras.jalonner). Ce script ne les voit donc pas,
et c'est voulu : leurs titres ne figurent pas dans TITRES_DE_CALAGE.

CE QUI EST CONSIDERE COMME MORT : un plan de calage qui n'est plus le
resultat retenu, l'unsteady qu'il etait seul a utiliser, leurs fichiers de
calcul, leur dossier de resultats RASMapper, et les traces de preparation
(sauvegardes horodatees, shapefiles temporaires, journaux de calcul).

CE QUI N'EST JAMAIS TOUCHE : tout plan, geometrie ou unsteady dont le titre
n'est pas un titre de calage, le plan RETENU et ce qu'il reference, et tout
objet mis en jeu par un calcul en cours.

  python elaguer_projet.py <dossier> --retenu p21          (simulation)
  python elaguer_projet.py <dossier> --retenu p21 --executer

Rien n'est supprime sans --executer. Une sauvegarde des fichiers TEXTE du
projet est faite avant toute suppression : ce sont eux qui rendent un projet
ouvrable, et ils pesent quelques centaines de ko.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Titres que l'ANCIENNE chaine donnait a ses copies de travail. Un objet dont
# le titre n'est pas dans cette liste appartient a l'utilisateur — ou est un
# plan d'etape de la chaine actuelle — et reste.
TITRES_DE_CALAGE = ("Calage_apports", "Unsteady_calage", "Geometrie_calage")

# Suffixes que HEC-RAS depose a cote d'un plan calcule, et le journal que la
# chaine ecrit elle-meme. Enumeres, jamais devines par un glob.
DERIVES_PLAN = (".p{n}", ".p{n}.hdf", ".p{n}.tmp.hdf", ".p{n}.snapshot.hdf",
                ".p{n}.blf", ".p{n}.data_errors.txt", ".p{n}.computeMsgs.txt",
                ".b{n}", ".bco{n}", ".x{n}", ".O{n}", ".r{n}",
                ".ic{n}", ".ic.o{n}")


def processus_hecras():
    """Processus HEC-RAS en cours. Vide si aucun, None si on ne sait pas."""
    try:
        # SANS FENETRE, comme les deux appels jumeaux de pilote_hecras.py :
        # ce module tourne pendant un calage, et chaque « tasklist » ferait
        # clignoter une console noire au premier plan.
        sortie = subprocess.run(["tasklist", "/NH"], capture_output=True,
                                text=True, timeout=10,
                                creationflags=getattr(
                                    subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return sorted({ligne.split()[0] for ligne in (sortie.stdout or "").splitlines()
                   if ligne.strip()
                   and ligne.split()[0].lower().startswith(("ras", "hec"))})


def _lire_texte(chemin):
    """
    Lit un fichier texte HEC-RAS en essayant plusieurs encodages.

    PAS DE errors=\"replace\" : cet outil REECRIT les fichiers qu'il lit (le
    .prj, et le plan qu'il reconstruit). Un titre de plan accentue ecrit par
    l'interface en cp1252 se relisait avec des U+FFFD a la place des accents,
    et la reecriture les gravait dans le projet de l'utilisateur. Le repli
    final ne sert que pour un fichier reellement binaire.

    Meme politique que pilote_hecras._lire_texte et
    calage_apports.noyau._lire_texte_hecras. Ces trois modules ne peuvent PAS
    partager de code : celui-ci ne depend QUE de la bibliotheque standard, a
    dessein — c'est un outil de reparation, il doit tourner meme quand
    numpy, pandas ou ras-commander sont casses. La duplication est assumee ;
    toute correction ici doit etre reportee aux deux autres.
    """
    chemin = Path(chemin)
    for encodage in ("utf-8", "latin1", "cp1252"):
        try:
            return chemin.read_text(encoding=encodage)
        except (UnicodeDecodeError, LookupError):
            continue
    return chemin.read_text(encoding="latin1", errors="replace")


def champ(chemin, cle):
    trouve = re.search(rf"^{cle}=(.*)$", _lire_texte(chemin), re.M)
    return trouve.group(1).strip() if trouve else ""


def inventorier(dossier, projet, retenu, inclure_inacheves=False):
    """
    Repartit les plans en « retenu », « a l'utilisateur », « mort » et
    « inacheve ».

    UN PLAN DE CALAGE SANS RESULTATS N'EST PAS UNE BRANCHE MORTE : c'est un
    calcul en cours, ou qui vient d'echouer et qu'on veut relire. Il se
    reconnait a l'absence de .pNN.hdf, ou a la presence d'un .pNN.tmp.hdf que
    le solveur ecrit pendant qu'il tourne. Le retirer detruirait le calcul
    qu'on est justement en train de faire.
    """
    morts, gardes, utilisateur, inacheves = [], [], [], []
    for chemin in sorted(dossier.glob(f"{projet}.p[0-9][0-9]")):
        numero = chemin.suffix[2:]
        titre = champ(chemin, "Plan Title")
        resultats = dossier / f"{projet}.p{numero}.hdf"
        provisoire = dossier / f"{projet}.p{numero}.tmp.hdf"
        info = {"numero": numero, "titre": titre,
                "court": champ(chemin, "Short Identifier"),
                "geom": champ(chemin, "Geom File"),
                "flot": champ(chemin, "Flow File"),
                "acheve": resultats.is_file() and not provisoire.is_file()}
        if numero == retenu:
            gardes.append(info)
        elif titre not in TITRES_DE_CALAGE:
            utilisateur.append(info)
        elif info["acheve"] or inclure_inacheves:
            morts.append(info)
        else:
            inacheves.append(info)
    return morts, gardes, utilisateur, inacheves


def reparer_plan(dossier, projet, retenu, plans, executer):
    """
    Remet dans le plan retenu la geometrie et le debit qu'il a reellement
    calcules, quand son fichier a ete vide par l'interface HEC-RAS.

    La verite est dans le fichier de RESULTATS, que l'interface ne reecrit
    pas : il porte « Geometry Filename » et « Flow Filename ». La structure,
    elle, est reprise du plan DONT IL EST LE CLONE — ras-commander nomme un
    clone « <identifiant du parent>_copy », ce qui permet de le retrouver.
    """
    plan = dossier / f"{projet}.p{retenu}"
    if champ(plan, "Geom File") and champ(plan, "Flow File"):
        return None
    hdf = dossier / f"{projet}.p{retenu}.hdf"
    if not hdf.is_file():
        return ("le plan retenu n'a ni geometrie ni debit, et aucun fichier "
                "de resultats ne permet de les retrouver")
    try:
        import h5py
        with h5py.File(hdf, "r") as f:
            a = f["Plan Data/Plan Information"].attrs

            def lire(cle):
                v = a.get(cle, b"")
                return (v.decode("utf-8", "replace")
                        if isinstance(v, bytes) else str(v)).strip()

            geom = Path(lire("Geometry Filename")).suffix.lstrip(".")
            flot = Path(lire("Flow Filename")).suffix.lstrip(".")
            court = lire("Plan ShortID")
    except Exception as e:                      # noqa: BLE001
        return f"fichier de resultats illisible : {e}"

    parent = court[:-len("_copy")] if court.endswith("_copy") else None
    modele = next((p for p in plans if p["court"] == parent), None)
    if modele is None:
        return (f"plan modele introuvable pour reconstruire p{retenu} "
                f"(cherche l'identifiant court « {parent} »)")

    source = dossier / f"{projet}.p{modele['numero']}"
    titre = champ(plan, "Plan Title") or court
    lignes = _lire_texte(source).splitlines(True)
    for i, ligne in enumerate(lignes):
        fin = "\n" if ligne.endswith("\n") else ""
        if ligne.startswith("Plan Title="):
            lignes[i] = f"Plan Title={titre}{fin}"
        elif ligne.startswith("Short Identifier="):
            lignes[i] = f"Short Identifier={titre[:24].ljust(24)}{fin}"
        elif ligne.startswith("Geom File="):
            lignes[i] = f"Geom File={geom}{fin}"
        elif ligne.startswith("Flow File="):
            lignes[i] = f"Flow File={flot}{fin}"
    if executer:
        plan.write_text("".join(lignes), encoding="utf-8")
    return (f"p{retenu} « {titre} » reconstruit d'apres p{modele['numero']} : "
            f"geom={geom}, flot={flot}"
            + ("" if executer else "  (simulation)"))


def unsteady_orphelins(dossier, projet, survivants):
    """Unsteady de calage qu'aucun plan survivant n'utilise."""
    utilises = {p["flot"].lstrip("uU") for p in survivants if p["flot"]}
    orphelins = []
    for chemin in sorted(dossier.glob(f"{projet}.u[0-9][0-9]")):
        numero = chemin.suffix[2:]
        if numero in utilises:
            continue
        if champ(chemin, "Flow Title") in TITRES_DE_CALAGE:
            orphelins.append(numero)
    return orphelins


def geometries_orphelines(dossier, projet, survivants):
    """Geometries de calage qu'aucun plan survivant n'utilise."""
    utilisees = {p["geom"].lstrip("gG") for p in survivants if p["geom"]}
    orphelines = []
    for chemin in sorted(dossier.glob(f"{projet}.g[0-9][0-9]")):
        numero = chemin.suffix[2:]
        if numero in utilisees:
            continue
        if champ(chemin, "Geom Title") in TITRES_DE_CALAGE:
            orphelines.append(numero)
    return orphelines


def a_supprimer(dossier, projet, morts, orphelins_u, orphelins_g, courts_gardes):
    """Liste exhaustive des chemins a retirer, dossiers compris."""
    cibles = []
    for plan in morts:
        for gabarit in DERIVES_PLAN:
            chemin = dossier / f"{projet}{gabarit.format(n=plan['numero'])}"
            if chemin.is_file():
                cibles.append(chemin)
        journal = dossier / f"_compute_p{plan['numero']}.log"
        if journal.is_file():
            cibles.append(journal)
        # Dossier de resultats RASMapper : il porte le Short Identifier.
        if plan["court"] and plan["court"] not in courts_gardes:
            rasmapper = dossier / plan["court"]
            if rasmapper.is_dir():
                cibles.append(rasmapper)
    for numero in orphelins_u:
        for suffixe in (f".u{numero}", f".u{numero}.hdf"):
            chemin = dossier / f"{projet}{suffixe}"
            if chemin.is_file():
                cibles.append(chemin)
    for numero in orphelins_g:
        for suffixe in (f".g{numero}", f".g{numero}.hdf"):
            chemin = dossier / f"{projet}{suffixe}"
            if chemin.is_file():
                cibles.append(chemin)
    # Traces de preparation.
    cibles += sorted(dossier.glob(f"{projet}.*.sauvegarde_*"))
    shapefiles = dossier / "_calage"
    if shapefiles.is_dir():
        cibles.append(shapefiles)
    # Derives dont le plan a DEJA disparu, laisses par une suppression
    # anterieure. Ceux des plans retires ci-dessus sont deja dans la liste.
    for chemin in derives_orphelins(dossier, projet):
        if chemin not in cibles:
            cibles.append(chemin)
    return cibles


def derives_orphelins(dossier, projet):
    """
    Fichiers derives dont le PLAN n'existe plus.

    Un plan supprime a la main dans HEC-RAS, ou par une version de cet outil
    qui ignorait l'un des suffixes, laisse derriere lui des fichiers que plus
    rien ne rattache : releve sur un cas reel, un « .snapshot.hdf » de
    16 Mo survivant a son plan. On les rattrape en remontant du fichier vers
    le numero de plan.
    """
    orphelins = []
    for gabarit in DERIVES_PLAN:
        if gabarit == ".p{n}":                 # le plan lui-meme, jamais ici
            continue
        motif = re.escape(gabarit).replace(r"\{n\}", r"(\d\d)")
        for chemin in sorted(dossier.glob(f"{projet}.*")):
            trouve = re.fullmatch(re.escape(projet) + motif, chemin.name)
            if trouve and not (dossier / f"{projet}.p{trouve.group(1)}").exists():
                orphelins.append(chemin)
    # Le journal de calcul de la chaine ne porte pas le nom du projet : la
    # boucle ci-dessus ne peut pas le voir. Cinq d'entre eux ont survecu a
    # leurs plans.
    for chemin in sorted(dossier.glob("_compute_p[0-9][0-9].log")):
        numero = chemin.stem[len("_compute_p"):]
        if not (dossier / f"{projet}.p{numero}").exists():
            orphelins.append(chemin)
    return sorted(set(orphelins))


def nettoyer_prj(dossier, projet):
    """Retire du .prj les objets dont le fichier n'existe plus."""
    prj = dossier / f"{projet}.prj"
    lignes = _lire_texte(prj).splitlines(True)
    gardees = []
    for ligne in lignes:
        nu = ligne.strip()
        cible = None
        for prefixe in ("Plan File=", "Geom File=", "Unsteady File=",
                        "Flow File="):
            if nu.startswith(prefixe):
                cible = dossier / f"{projet}.{nu.split('=', 1)[1].strip()}"
                break
        if cible is not None and not cible.exists():
            continue
        gardees.append(ligne)
    retirees = len(lignes) - len(gardees)
    if retirees:
        prj.write_text("".join(gardees), encoding="utf-8")
    return retirees


def taille(chemins):
    total = 0
    for chemin in chemins:
        if chemin.is_dir():
            total += sum(f.stat().st_size for f in chemin.rglob("*")
                         if f.is_file())
        elif chemin.is_file():
            total += chemin.stat().st_size
    return total


def autotest():
    """
    Eprouve le chemin --executer sur un projet synthetique reproduisant le cas
    reel : plan retenu vide de sa geometrie par l'interface HEC-RAS, plan de
    calage mort avec ses derives et son dossier RASMapper, plan de calage SANS
    resultats (calcul en cours), et un plan de l'utilisateur nomme « Q100 copy »
    qu'aucune regle ne doit emporter.
    """
    import h5py

    bac = Path(tempfile.mkdtemp(prefix="_essai_elagage_"))
    nom = "ESSAI"
    echecs = []

    def verifier(libelle, condition, detail=""):
        print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
              + (f"  ->  {detail}" if detail else ""))
        if not condition:
            echecs.append(libelle)

    def ecrire_plan(numero, titre, court, geom, flot):
        lignes = [f"Plan Title={titre}\n", f"Short Identifier={court}\n"]
        if geom:
            lignes += [f"Geom File={geom}\n", f"Flow File={flot}\n"]
        lignes.append("Computation Interval=20SEC\n")
        (bac / f"{nom}.p{numero}").write_text("".join(lignes), encoding="utf-8")

    def ecrire_resultats(numero, geom, flot, court):
        with h5py.File(bac / f"{nom}.p{numero}.hdf", "w") as f:
            g = f.create_group("Plan Data/Plan Information")
            g.attrs["Geometry Filename"] = f"{nom}.{geom}"
            g.attrs["Flow Filename"] = f"{nom}.{flot}"
            g.attrs["Plan ShortID"] = court

    ecrire_plan("01", "Q100", "Q100", "g01", "u01")
    ecrire_plan("02", "Q100 copy", "Q100_copy", "g01", "u02")     # PIEGE
    ecrire_plan("15", "Calage_apports", "Q100_copy_copy", "g01", "u06")
    ecrire_plan("16", "Calage_apports", "Q100_c2", "g01", "u07")  # en cours
    ecrire_plan("21", "Calage_A1_retenu", "Plan p21", None, None)  # vide
    ecrire_resultats("15", "g01", "u06", "Q100_copy_copy")
    ecrire_resultats("21", "g01", "u12", "Q100_copy_copy_copy")
    (bac / f"{nom}.p16.tmp.hdf").write_bytes(b"\x89HDF")
    # Derives d'un plan DEJA disparu : personne ne les rattache plus a rien.
    (bac / f"{nom}.p30.snapshot.hdf").write_bytes(b"x")
    (bac / f"{nom}.b30").write_bytes(b"x")
    (bac / "_compute_p30.log").write_bytes(b"x")
    for numero, titre in (("01", "Q100"), ("02", "Q50"),
                          ("06", "Unsteady_calage"), ("07", "Unsteady_calage"),
                          ("12", "Calage_A1")):
        (bac / f"{nom}.u{numero}").write_text(f"Flow Title={titre}\n",
                                              encoding="utf-8")
    (bac / f"{nom}.g01").write_text("Geom Title=Etat actuel\n",
                                    encoding="utf-8")
    for numero in ("01", "15", "16", "21"):
        for gabarit in (".b{n}", ".bco{n}", ".x{n}", ".ic.o{n}",
                        ".p{n}.snapshot.hdf"):
            (bac / f"{nom}{gabarit.format(n=numero)}").write_bytes(b"x")
        (bac / f"_compute_p{numero}.log").write_bytes(b"x")
    for court in ("Q100_copy_copy", "Q100_copy_copy_copy"):
        (bac / court).mkdir()
        (bac / court / "resultats.tif").write_bytes(b"x")
    (bac / f"{nom}.g01.sauvegarde_20260727_101500").write_bytes(b"x")
    (bac / "_calage").mkdir()
    (bac / "_calage" / "sections.shp").write_bytes(b"x")
    lignes = ["Proj Title=Essai\n", "Geom File=g01\n"]
    lignes += [f"Unsteady File=u{n}\n" for n in ("01", "02", "06", "07", "12")]
    lignes += [f"Plan File=p{n}\n" for n in ("01", "02", "15", "16", "21")]
    (bac / f"{nom}.prj").write_text("".join(lignes), encoding="utf-8")

    code = subprocess.call(
        [sys.executable, str(Path(__file__).resolve()), str(bac),
         "--retenu", "p21", "--executer", "--ignorer-hecras"],
        stdout=subprocess.DEVNULL)
    verifier("l'elagage se termine sans erreur", code == 0, f"code {code}")

    # Le coffre contient une COPIE des fichiers retires : l'inclure ferait
    # conclure que rien n'a ete supprime.
    reste = {p.name for p in bac.rglob("*") if p.is_file()
             and not any(x.startswith("_avant_elagage_") for x in p.parts)}
    p21 = (bac / f"{nom}.p21").read_text(encoding="utf-8")
    prj = (bac / f"{nom}.prj").read_text(encoding="utf-8")

    verifier("le plan retenu, vide, est reconstruit d'apres son .hdf",
             "Geom File=g01" in p21 and "Flow File=u12" in p21)
    verifier("il garde les reglages du plan modele et son nom",
             "Computation Interval=20SEC" in p21
             and "Plan Title=Calage_A1_retenu" in p21)
    verifier("son unsteady, ses resultats et son dossier RASMapper restent",
             f"{nom}.u12" in reste and f"{nom}.p21.hdf" in reste
             and (bac / "Q100_copy_copy_copy").is_dir())
    verifier("UN PLAN DE L'UTILISATEUR « Q100 copy » SURVIT",
             f"{nom}.p02" in reste and f"{nom}.u02" in reste)
    verifier("un calcul EN COURS n'est pas touche",
             f"{nom}.p16" in reste and f"{nom}.u07" in reste)
    verifier("le plan mort part avec tous ses derives",
             not any(n in reste for n in
                     (f"{nom}.p15", f"{nom}.p15.hdf", f"{nom}.b15",
                      f"{nom}.bco15", f"{nom}.x15", f"{nom}.ic.o15",
                      "_compute_p15.log")))
    verifier("son unsteady orphelin et son dossier RASMapper partent",
             f"{nom}.u06" not in reste
             and not (bac / "Q100_copy_copy").is_dir())
    verifier("sauvegardes horodatees et shapefiles temporaires partent",
             not any("sauvegarde_" in n for n in reste)
             and not (bac / "_calage").is_dir())
    verifier("les derives d'un plan DEJA disparu sont rattrapes",
             f"{nom}.p30.snapshot.hdf" not in reste
             and f"{nom}.b30" not in reste
             and "_compute_p30.log" not in reste)
    verifier("le journal du plan retenu est conserve",
             "_compute_p21.log" in reste)
    verifier("le .snapshot.hdf du plan mort part avec lui",
             f"{nom}.p15.snapshot.hdf" not in reste)
    verifier("les derives d'un plan CONSERVE sont intacts",
             f"{nom}.b01" in reste and f"{nom}.x01" in reste)
    verifier("le .prj suit les suppressions et garde le reste",
             "Plan File=p15" not in prj and "Unsteady File=u06" not in prj
             and all(f"Plan File=p{n}" in prj for n in ("01", "02", "16", "21")))
    verifier("les fichiers texte ont ete sauvegardes avant l'elagage",
             any(d.name.startswith("_avant_elagage_")
                 for d in bac.iterdir() if d.is_dir()))

    shutil.rmtree(bac, ignore_errors=True)
    print()
    print(f"{len(echecs)} ECHEC(S)" if echecs else "Tous les controles passent.")
    return 1 if echecs else 0


def main():
    a = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    a.add_argument("dossier", nargs="?",
                   help="dossier du projet HEC-RAS ; omis : auto-test seul")
    a.add_argument("--retenu", help="plan a conserver, ex. p21")
    a.add_argument("--executer", action="store_true",
                   help="sans lui, rien n'est supprime")
    a.add_argument("--inclure-inacheves", action="store_true",
                   help="retirer AUSSI les plans de calage sans resultats. "
                        "Par defaut ils sont conserves : ce sont des calculs "
                        "en cours, ou qu'on veut relire apres un echec.")
    a.add_argument("--ignorer-hecras", action="store_true",
                   help="elaguer meme si HEC-RAS tourne. A n'utiliser QUE "
                        "s'il est ouvert sur un AUTRE projet : on ne peut pas "
                        "savoir lequel il tient.")
    args = a.parse_args()

    if args.dossier is None:
        print("=" * 78)
        print("AUTO-TEST — elagage sur un projet synthetique")
        print("=" * 78)
        return autotest()
    if not args.retenu:
        raise SystemExit("--retenu est obligatoire : quel plan conserver ?")

    dossier = Path(args.dossier)
    projets = [p.stem for p in sorted(dossier.glob("*.prj"))
               if (dossier / f"{p.stem}.p01").exists()
               or list(dossier.glob(f"{p.stem}.p[0-9][0-9]"))]
    if not projets:
        raise SystemExit(f"aucun projet HEC-RAS dans {dossier}")
    projet = projets[0]
    retenu = args.retenu.lstrip("pP").zfill(2)

    print("=" * 78)
    print(f"ELAGAGE — projet {projet} dans {dossier}")
    print("=" * 78)

    # 1. HEC-RAS OUVERT : on refuse d'AGIR, jamais de REGARDER. L'interface
    #    reecrit les fichiers du projet depuis sa memoire — ce qu'on supprime
    #    reapparait — et un calcul en cours ecrit dans des fichiers qu'on
    #    serait en train de retirer. Etablir la liste, en revanche, ne lit
    #    que des fichiers : autant pouvoir le faire pendant que ca tourne.
    en_cours = processus_hecras()
    if en_cours and args.ignorer_hecras:
        print(f"\nHEC-RAS tourne ({', '.join(en_cours)}) et le garde-fou est "
              f"LEVE (--ignorer-hecras). A vos risques : s'il tient CE "
              f"projet, l'elagage sera defait.")
        en_cours = []
    if en_cours and args.executer:
        print(f"\nREFUS D'AGIR : HEC-RAS tourne ({', '.join(en_cours)}).")
        print("L'interface reecrit les fichiers du projet depuis sa propre")
        print("memoire — un elagage fait maintenant serait defait — et un")
        print("calcul en cours ecrit dans des fichiers qu'on retirerait.")
        print("Fermer HEC-RAS, puis relancer la meme commande.")
        print("S'il est ouvert sur un AUTRE projet : --ignorer-hecras.")
        return 2
    if en_cours:
        print(f"\nHEC-RAS tourne ({', '.join(en_cours)}) : simulation "
              f"possible, elagage refuse tant qu'il n'est pas ferme.")
    elif en_cours is None:
        print("\nAvertissement : impossible de verifier que HEC-RAS est ferme.")

    morts, gardes, utilisateur, inacheves = inventorier(
        dossier, projet, retenu, args.inclure_inacheves)
    if not gardes:
        raise SystemExit(f"le plan retenu p{retenu} n'existe pas dans {projet}")
    survivants = gardes + utilisateur + inacheves
    orphelins_u = unsteady_orphelins(dossier, projet, survivants)
    orphelins_g = geometries_orphelines(dossier, projet, survivants)
    courts_gardes = {p["court"] for p in survivants if p["court"]}
    cibles = a_supprimer(dossier, projet, morts, orphelins_u, orphelins_g,
                         courts_gardes)

    # REPARATION AVANT SUPPRESSION : le plan modele dont on reprend la
    # structure est souvent l'un de ceux qu'on s'apprete a retirer.
    tous_plans = gardes + utilisateur + morts + inacheves
    repare = reparer_plan(dossier, projet, retenu, tous_plans,
                          args.executer and not en_cours)
    if repare:
        print(f"\nREPARATION DU PLAN RETENU\n   {repare}")
        if args.executer and not en_cours:
            morts, gardes, utilisateur, inacheves = inventorier(
                dossier, projet, retenu, args.inclure_inacheves)

    print(f"\nCONSERVE — plan retenu")
    for p in gardes:
        print(f"   p{p['numero']}  « {p['titre']} »  geom={p['geom'] or '?'}  "
              f"flot={p['flot'] or '?'}")
    print(f"\nCONSERVE — {len(utilisateur)} plan(s) de l'utilisateur")
    for p in utilisateur:
        print(f"   p{p['numero']}  « {p['titre']} »")
    if inacheves:
        print(f"\nCONSERVE — {len(inacheves)} plan(s) de calage SANS "
              f"RESULTATS (calcul en cours, ou echec a relire)")
        for p in inacheves:
            print(f"   p{p['numero']}  « {p['titre']} »  — "
                  f"--inclure-inacheves pour les retirer aussi")

    print(f"\nA RETIRER — {len(morts)} plan(s) de calage")
    for p in morts:
        print(f"   p{p['numero']}  « {p['titre']} »  (court « {p['court']} »)")
    print(f"A RETIRER — unsteady orphelins : "
          f"{', '.join('u' + n for n in orphelins_u) or '(aucun)'}")
    print(f"A RETIRER — geometries orphelines : "
          f"{', '.join('g' + n for n in orphelins_g) or '(aucune)'}")

    print(f"\n{len(cibles)} element(s), {taille(cibles) / 1e6:.0f} Mo :")
    for chemin in cibles:
        marque = "/" if chemin.is_dir() else " "
        print(f"   {marque} {chemin.name}")

    if not args.executer:
        print("\nSIMULATION — rien n'a ete supprime. "
              "Ajouter --executer pour agir.")
        return 0

    # 2. SAUVEGARDE DES FICHIERS TEXTE. Ce sont eux qui rendent un projet
    #    ouvrable ; ils pesent quelques centaines de ko, contre des dizaines
    #    de Mo pour chaque fichier de resultats.
    horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
    coffre = dossier / f"_avant_elagage_{horodatage}"
    coffre.mkdir()
    for motif in (f"{projet}.prj", f"{projet}.p[0-9][0-9]",
                  f"{projet}.u[0-9][0-9]", f"{projet}.g[0-9][0-9]"):
        for chemin in sorted(dossier.glob(motif)):
            shutil.copy2(chemin, coffre / chemin.name)
    print(f"\nSauvegarde des fichiers texte : {coffre.name} "
          f"({len(list(coffre.glob('*')))} fichier(s))")

    retires = 0
    for chemin in cibles:
        try:
            if chemin.is_dir():
                shutil.rmtree(chemin)
            else:
                chemin.unlink()
            retires += 1
        except OSError as e:
            print(f"   NON RETIRE : {chemin.name} — {e}")
    lignes = nettoyer_prj(dossier, projet)
    print(f"{retires} element(s) retire(s), {lignes} ligne(s) du .prj nettoyee(s)")
    print("\nLe dossier de sauvegarde peut etre supprime une fois le projet "
          "rouvert sans erreur dans HEC-RAS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
