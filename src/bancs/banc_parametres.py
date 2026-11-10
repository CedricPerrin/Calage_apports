"""Banc d'auto-test de src/parametres.py.

Ce banc etait le bloc `if __name__ == "__main__":` du module ; il en a ete
sorti le 10/11/2026 pour ne plus partir avec le code dans l'archive du plugin.
Il se lance seul (python3 src/bancs/banc_parametres.py) ou par le relais
que garde src/parametres.py (python3 src/parametres.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parametres import (FEUILLE_HERITEE, chemin, ecrire, ecrire_un, lire,
                        origine)

import tempfile

_echecs = []

def _verifier(nom, ok, detail=""):
    print(f"   [{'OK' if ok else 'ECHEC'}] {nom}"
          + (f"  ->  {detail}" if detail else ""))
    if not ok:
        _echecs.append(nom)

print("PARAMETRES — auto-test\n")
_dossier = Path(tempfile.mkdtemp(prefix="parametres_"))
_classeur = _dossier / "donnees_calage_Q100.xlsx"

_verifier("le JSON porte le nom du classeur",
          chemin(_classeur).name == "donnees_calage_Q100.json",
          chemin(_classeur).name)
_verifier("sans fichier ni feuille, la lecture rend un dictionnaire vide",
          lire(_classeur) == {})
_verifier("et l'origine le dit", origine(_classeur) == "aucune")

_jeu = {"Nom_projet": "Essai", "Nb_max_iterations_par_apport": 6,
        "Tolerance_volume_pct": 5.0, "Simulation_debut": None,
        "Prefixe_scenario": "Q100"}
ecrire(_classeur, _jeu)
_relu = lire(_classeur)
_verifier("ce qui est ecrit est relu a l'identique", _relu == _jeu,
          str(_relu))
_verifier("les types survivent au passage",
          isinstance(_relu["Nb_max_iterations_par_apport"], int)
          and isinstance(_relu["Tolerance_volume_pct"], float)
          and _relu["Simulation_debut"] is None)
_verifier("l'origine est le JSON", origine(_classeur) == "json")

ecrire_un(_classeur, "Premier_apport", "ARA07")
_verifier("ecrire_un change une cle et garde les autres",
          lire(_classeur)["Premier_apport"] == "ARA07"
          and lire(_classeur)["Nom_projet"] == "Essai")
ecrire_un(_classeur, "Cle_inconnue", 1)
_verifier("une cle inconnue est ajoutee, pas refusee",
          lire(_classeur)["Cle_inconnue"] == 1)

# UN NaN NE DOIT PAS ARRIVER DANS LE FICHIER. pandas en rend pour chaque
# cellule vide, et « NaN » n'est pas du JSON : un fichier qui ne se relit
# que par nous serait un fichier qu'on ne peut pas donner.
ecrire(_classeur, {"Vide": float("nan"), "Texte": "x"})
_verifier("un NaN est ecrit comme un vide",
          lire(_classeur)["Vide"] is None
          and "NaN" not in chemin(_classeur).read_text(encoding="utf-8"),
          chemin(_classeur).read_text(encoding="utf-8").strip())

# LA FEUILLE HERITEE RESTE LUE. Un calage en cours au 20 septembre 2026
# porte un classeur sans JSON : il doit continuer de tourner.
import pandas as pd

_ancien = _dossier / "ancien.xlsx"
with pd.ExcelWriter(_ancien, engine="openpyxl") as _w:
    pd.DataFrame({"Parametre": ["Nom_projet", "Simulation_debut"],
                  "Valeur": ["Ancien", None]}
                 ).to_excel(_w, sheet_name=FEUILLE_HERITEE, index=False)
    pd.DataFrame({"Temps_h": []}).to_excel(_w, sheet_name="Cibles",
                                           index=False)
_verifier("un classeur d'avant est encore lu par sa feuille",
          lire(_ancien) == {"Nom_projet": "Ancien",
                            "Simulation_debut": None},
          str(lire(_ancien)))
_verifier("et l'origine le dit", origine(_ancien) == "feuille",
          origine(_ancien))
# ET LE JSON PRIME DES QU'IL EXISTE : sans cette regle, recomposer un
# paquet sur un ancien classeur laisserait la feuille repondre a la place
# des parametres neufs.
ecrire(_ancien, {"Nom_projet": "Neuf"})
_verifier("le JSON prime sur la feuille heritee",
          lire(_ancien) == {"Nom_projet": "Neuf"}, str(lire(_ancien)))

print("\n" + "=" * 74)
print("Tous les controles passent." if not _echecs
      else f"{len(_echecs)} ECHEC(S) : {_echecs}")
print("=" * 74)
raise SystemExit(1 if _echecs else 0)
