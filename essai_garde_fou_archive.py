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
CIBLE = PROJET / "calage_apports" / "noyau.py"
PYTHON = sys.executable

FAUTES = [
    ("chemin du poste de developpement",
     "\n# essai : " + str(PROJET) + "\n"),
    ("nom d'affaire cliente",
     "\n# essai : mesure faite sur Las_Hies\n"),
    ("identifiant de cas d'essai",
     "\n# essai : apport KON_01 du modele de recette\n"),
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
