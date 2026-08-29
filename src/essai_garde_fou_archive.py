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
# exactement la faute que cet essai verifie. Sans ce fichier, seule la faute
# de chemin — la seule qui ne repose sur aucune liste — est eprouvee.
sys.path.insert(0, str(PROJET))
import faire_zip                                            # noqa: E402

FAUTES = [
    ("chemin du poste de developpement",
     "\n# essai : " + str(PROJET) + "\n"),
]
_mots = faire_zip.mots_d_affaires()
if _mots:
    FAUTES.append(("nom d'affaire ou identifiant de cas d'essai",
                   f"\n# essai : mesure faite sur {_mots[0]}\n"))
else:
    print(f"   ignore : {faire_zip.FICHIER_AFFAIRES.name} absent — la faute "
          f"« nom d'affaire » n'est pas eprouvee")

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
    acheve = subprocess.run([PYTHON, "faire_zip.py"], cwd=PROJET,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    propre = acheve.returncode == 0
    print(f"   [{'OK' if propre else 'ECHEC'}] source retablie, "
          f"archive {'conforme' if propre else 'TOUJOURS REFUSEE'}")
    if not propre:
        echecs.append("retablissement")

print()
print("TOUT PASSE" if not echecs else f"{len(echecs)} ECHEC(S) : {echecs}")
sys.exit(1 if echecs else 0)
