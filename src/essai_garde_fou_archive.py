# -*- coding: utf-8 -*-
"""
Met le garde-fou d'empaquetage de faire_zip.py EN DEFAUT, volontairement.

UN CONTROLE QUI N'A JAMAIS ECHOUE NE PROUVE RIEN. Celui-ci a laisse partir le
chemin du poste de developpement pendant des semaines, et l'essai equivalent
de test_plugin_qgis.py portait meme ce chemin en liste blanche. On injecte
donc, une par une, les trois fautes qu'il doit voir, on verifie qu'il REFUSE
l'archive, puis on retablit la source et on reconstruit.

Ce script MODIFIE temporairement calage_apports/noyau.py et le retablit dans
un bloc finally. Il ne s'execute pas pendant un calage : faire_zip.py
reconstruit l'archive a chaque appel.

Usage :  python essai_garde_fou_archive.py
"""
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJET = Path(__file__).resolve().parent
CIBLE = PROJET.parent / "calage_apports" / "noyau.py"
PYTHON = sys.executable

# LES MOTS INJECTES VIENNENT DE .affaires, comme ceux que le garde-fou
# cherche : les ecrire ici les publierait dans un fichier suivi, ce qui est
# exactement la faute que cet essai verifie.
#
# .affaires N'EST PAS SUIVI PAR GIT, DONC ABSENT DE TOUT CLONE NEUF — d'un
# poste qui vient de cloner, d'une session dans un bac a sable cloud. Cet
# essai se contentait alors d'imprimer « ignore », puis concluait « TOUT
# PASSE » : le controle des noms d'affaires etait DESARME et la sortie
# verte. C'est exactement le piege que STATUT.txt nomme — « un controle qui
# s'ignore lui-meme ne controle rien », « a chaque fois la sortie disait
# ignore ou OK ». Mesure du 01/09/2026 : deux [OK] sur trois, et TOUT PASSE.
#
# ON LUI FABRIQUE DONC SON DECOR, comme au controle de l'emplacement du venv :
# a defaut de liste reelle, on ECRIT un .affaires temporaire portant un mot
# inventé, on injecte ce mot, et on verifie qu'il est refuse. Le controle
# tourne ainsi PARTOUT, et le mot invente ne peut pas se trouver ailleurs dans
# le depot — sans quoi la reconstruction finale echouerait, ce qui se verrait.
sys.path.insert(0, str(PROJET))
import faire_zip                                            # noqa: E402

MOT_FABRIQUE = "ESSAI_GARDE_FOU_ZZZ"
_affaires_fabrique = False
_mots = faire_zip.mots_d_affaires()
if not _mots:
    faire_zip.FICHIER_AFFAIRES.write_text(
        f"# Fabrique par essai_garde_fou_archive.py, retire a la fin.\n"
        f"{MOT_FABRIQUE}\n", encoding="utf-8")
    _affaires_fabrique = True
    _mots = faire_zip.mots_d_affaires()
    print(f"   {faire_zip.FICHIER_AFFAIRES.name} absent : liste TEMPORAIRE "
          f"fabriquee avec « {MOT_FABRIQUE} » — le controle des noms est "
          f"eprouve quand meme, sur un mot invente")

FAUTES = [
    ("chemin du poste de developpement",
     "\n# essai : " + str(PROJET) + "\n"),
    ("nom d'affaire ou identifiant de cas d'essai",
     f"\n# essai : mesure faite sur {_mots[0]}\n"),
]

sauvegarde = CIBLE.read_text(encoding="utf-8")
echecs = []
try:
    for intitule, faute in FAUTES:
        CIBLE.write_text(sauvegarde + faute, encoding="utf-8")
        acheve = subprocess.run([PYTHON, "faire_zip.py"], cwd=PROJET,
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        refuse = acheve.returncode != 0
        motif = [l.strip() for l in (acheve.stdout or "").splitlines()
                 if "ECHEC" in l]
        print(f"   [{'OK' if refuse else 'ECHEC'}] {intitule} : "
              f"{'refuse' if refuse else 'LAISSE PASSER'}")
        for m in motif[:2]:
            print(f"           {m}")
        if not refuse:
            echecs.append(intitule)
finally:
    CIBLE.write_text(sauvegarde, encoding="utf-8")
    # LA RECONSTRUCTION PROPRE SE FAIT AVEC LA LISTE ENCORE EN PLACE : le
    # garde-fou doit rendre une archive conforme ALORS QU'IL EST ARME, sinon
    # on ne prouve que sa capacite a refuser, jamais celle a accepter.
    acheve = subprocess.run([PYTHON, "faire_zip.py"], cwd=PROJET,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    propre = acheve.returncode == 0
    print(f"   [{'OK' if propre else 'ECHEC'}] source retablie, "
          f"archive {'conforme' if propre else 'TOUJOURS REFUSEE'}")
    if not propre:
        echecs.append("retablissement")
    # ET ON NE LAISSE PAS DE .affaires DERRIERE SOI : il porterait un mot
    # invente, et le prochain qui le lirait croirait que sa liste est en place.
    if _affaires_fabrique:
        faire_zip.FICHIER_AFFAIRES.unlink(missing_ok=True)
        print(f"   liste temporaire retiree — "
              f"{faire_zip.FICHIER_AFFAIRES.name} reste a fournir sur ce poste")

print()
print("TOUT PASSE" if not echecs else f"{len(echecs)} ECHEC(S) : {echecs}")
sys.exit(1 if echecs else 0)
