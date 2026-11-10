"""Banc d'auto-test de src/style_classeur.py.

Ce banc etait le bloc `if __name__ == "__main__":` du module ; il en a ete
sorti le 10/11/2026 pour ne plus partir avec le code dans l'archive du plugin.
Il se lance seul (python3 src/bancs/banc_style_classeur.py) ou par le relais
que garde src/style_classeur.py (python3 src/style_classeur.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from style_classeur import (COULEURS_ONGLETS, ENTETE_PIC,
                            LIGNES_GRAPHIQUE_CIBLES, mettre_en_forme)

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tempfile
from pathlib import Path

import openpyxl

_echecs = []

def _verifier(libelle, condition, detail=""):
    print(f"      [{'OK' if condition else 'ECHEC'}] {libelle}"
          + (f"  ->  {detail}" if detail else ""))
    if not condition:
        _echecs.append(libelle)

print("=" * 72)
print("AUTO-TEST DE LA MISE EN FORME DU CLASSEUR")
print("=" * 72)

_dossier = Path(tempfile.mkdtemp(prefix="calage_style_"))

def _classeur_temoin(chemin, avec_intrus=True, cibles=True):
    """Un classeur de calage plausible, plus une feuille que la charte
        ne connait pas — c'est elle qui eprouve la promesse « ne leve
        jamais »."""
    cl = openpyxl.Workbook()
    f = cl.active
    f.title = "Parametres"
    f.append(["Parametre", "Valeur"])
    f.append(["Nom_projet", "TEMOIN"])
    f.append(["Tolerance_volume_pct", 5])

    c = cl.create_sheet("Correspondance")
    c.append(["Ordre", "Nom_Apport (BC line)", "Nom_Section (reference line)",
              "Nom_Cible", "Pente_m_par_m"])
    c.append([1, "A1", "SC1", "Cible_SC1", None])
    c.append([2, "A2", "SC2", "Cible_SC2", 0.002])

    if cibles:
        ci = cl.create_sheet("Cibles")
        ci.append(["Temps_h", "Cible_SC1", "Cible_SC2"])
        for i in range(1, 6):
            ci.append([0.5 * i, 10.0 * i, 8.0 * i])

    if avec_intrus:
        x = cl.create_sheet("Feuille_que_la_charte_ignore")
        x.append(["quoi que ce soit", 1])
    cl.save(chemin)
    return chemin

print("\n1. CE QUI EST TRAITE, ET CE QUI EST IGNORE")
_temoin = _classeur_temoin(_dossier / "temoin.xlsx")
_traitees = mettre_en_forme(_temoin)
_verifier("les trois feuilles de la charte sont traitees, et elles seules",
          sorted(_traitees) == ["Cibles", "Correspondance", "Parametres"],
          str(sorted(_traitees)))
_verifier("une feuille inconnue est IGNOREE, jamais fatale — c'est la "
          "promesse du docstring",
          "Feuille_que_la_charte_ignore" not in _traitees)

_relu = openpyxl.load_workbook(_temoin)
_verifier("le quadrillage est retire de TOUTES les feuilles, l'inconnue "
          "comprise",
          all(not _relu[n].sheet_view.showGridLines
              for n in _relu.sheetnames),
          ", ".join(f"{n}={_relu[n].sheet_view.showGridLines}"
                    for n in _relu.sheetnames))
_couleurs = {n: (_relu[n].sheet_properties.tabColor.rgb
                 if _relu[n].sheet_properties.tabColor else None)
             for n in COULEURS_ONGLETS if n in _relu.sheetnames}
_verifier("chaque onglet de la charte porte sa couleur",
          all(c and COULEURS_ONGLETS[n] in str(c)
              for n, c in _couleurs.items()),
          str(_couleurs))

print("\n2. LA FEUILLE CIBLES — CELLE QUE L'UTILISATEUR REMPLIT")
_ci = _relu["Cibles"]
_verifier("les volets sont figes en B2 : le temps reste visible quand on "
          "fait defiler les debits",
          _ci.freeze_panes == "B2", str(_ci.freeze_panes))
_verifier("une mise en forme conditionnelle marque les debits negatifs",
          len(list(_ci.conditional_formatting)) >= 1,
          f"{len(list(_ci.conditional_formatting))} regle(s)")

print("\n3. L'APERCU, DONT controle_donnees.py DEPEND")
# LE LIEN EST NOMME, PAS DEVINE : controle_donnees exclut ce tableau des
# cibles par l'en-tete EXACT que ce module pose. Deux ecritures de la
# meme chaine finiraient par diverger — le banc verifie qu'elles n'ont
# qu'une source.
_entetes = [c.value for c in _ci[1]]
_verifier(f"l'en-tete « {ENTETE_PIC} » est pose sur la feuille",
          ENTETE_PIC in _entetes, str(_entetes))
_verifier("un graphique accompagne le tableau",
          len(_ci._charts) >= 1, f"{len(_ci._charts)} graphique(s)")

# LA PLAGE COUVRE CE QUI SERA COLLE, pas ce qui est la. La feuille est
# remplie A LA MAIN apres la composition, sans que mettre_en_forme() soit
# relance : une formule bornee aux 6 lignes du temoin ne verrait jamais
# les 400 lignes d'une vraie cible.
_formules = [c.value for ligne in _ci.iter_rows() for c in ligne
             if isinstance(c.value, str) and c.value.startswith("=MAX(")]
_verifier("les formules de pointe couvrent LIGNES_GRAPHIQUE_CIBLES, pas "
          "les seules lignes presentes",
          bool(_formules)
          and all(str(LIGNES_GRAPHIQUE_CIBLES) in f for f in _formules),
          _formules[0] if _formules else "aucune formule =MAX")

print("\n4. CE QUI NE DOIT PAS FAIRE TOMBER LA MISE EN FORME")
# UNE FEUILLE « Parametres » VIDE est le cas qu'un classeur a moitie
# ecrit produit. Elle ne doit ni lever, ni etre annoncee comme traitee.
_vide = openpyxl.Workbook()
_vide.active.title = "Parametres"
_chemin_vide = _dossier / "parametres_vide.xlsx"
_vide.save(_chemin_vide)
try:
    _t = mettre_en_forme(_chemin_vide)
    _leve = False
except Exception as _e:                                  # noqa: BLE001
    _t, _leve = None, f"{type(_e).__name__}: {_e}"
_verifier("une feuille « Parametres » vide ne fait pas lever "
          "mettre_en_forme()", not _leve, _leve or "aucune exception")

# ET UN CLASSEUR SANS FEUILLE CIBLES reste traitable : la composition
# peut legitimement n'en poser aucune.
_sans = _classeur_temoin(_dossier / "sans_cibles.xlsx", cibles=False)
try:
    _t2 = mettre_en_forme(_sans)
    _leve2 = False
except Exception as _e:                                  # noqa: BLE001
    _t2, _leve2 = None, f"{type(_e).__name__}: {_e}"
_verifier("un classeur sans feuille Cibles se met en forme quand meme",
          not _leve2 and _t2 is not None and "Cibles" not in _t2,
          _leve2 or str(_t2))

print("\n5. MISE EN FORME REJOUEE — ELLE DOIT ETRE IDEMPOTENTE")
# preparer_classeur() la rappelle a chaque recomposition, sur un classeur
# deja habille.
_deux = mettre_en_forme(_temoin)
_verifier("un second passage traite les memes feuilles",
          sorted(_deux) == sorted(_traitees),
          f"{sorted(_deux)} vs {sorted(_traitees)}")
_ci2 = openpyxl.load_workbook(_temoin)["Cibles"]
_verifier("et n'empile pas les graphiques",
          len(_ci2._charts) == len(_ci._charts),
          f"{len(_ci2._charts)} apres deux passages, "
          f"{len(_ci._charts)} apres un")

import shutil as _shutil
_shutil.rmtree(_dossier, ignore_errors=True)

print("\n" + "=" * 72)
if _echecs:
    print(f"{len(_echecs)} ECHEC(S) : {_echecs}")
    sys.exit(1)
print("Tous les controles passent.")
print("=" * 72)
