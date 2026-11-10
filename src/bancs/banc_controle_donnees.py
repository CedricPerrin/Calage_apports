"""Banc d'auto-test de src/controle_donnees.py.

Ce banc etait le bloc `if __name__ == "__main__":` du module ; il en a ete
sorti le 10/11/2026 pour ne plus partir avec le code dans l'archive du plugin.
Il se lance seul (python3 src/bancs/banc_controle_donnees.py) ou par le relais
que garde src/controle_donnees.py (python3 src/controle_donnees.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import parametres
import controle_donnees
from controle_donnees import (ERREUR, afficher, controler_geometrie,
                              controler_template)

import tempfile

dossier = Path(controle_donnees.__file__).parent
reference = dossier.parent / "template_donnees_calage.xlsx"

print("=" * 70)
print("AUTO-TEST DU CONTROLE DES DONNEES")
print("=" * 70)

print("\n1. Template de reference, vierge")
afficher(controler_template(reference), "Template livre avec le projet")

print("\n2. Template volontairement fautif")
tmp = Path(tempfile.gettempdir()) / "template_fautif.xlsx"
parametres.ecrire(tmp, {
    "Dossier_projet_HECRAS": r"D:\projet", "Nom_projet": "Essai",
    "Nb_max_iterations_par_apport": 2,
    # Date au format francais : l'erreur de saisie la plus probable, et
    # la plus silencieuse.
    "Simulation_debut": "13/10/2014 00:00",
    "Simulation_fin": "14OCT2014,04:00"})
with pd.ExcelWriter(tmp, engine="openpyxl") as w:
    pd.DataFrame({
        "Ordre": [1, 2, 4],
        "Nom_Apport (BC line)": ["A1", "A2", "A2"],
        "Nom_Section (reference line)": ["S1", "S2", "S3"],
        "Nom_Cible": ["C1", "C2", "C_absente"],
    }).to_excel(w, sheet_name="Correspondance", index=False)
    pd.DataFrame({
        "Temps_h": [0, 2, 1, 6],
        "C1": [1, 5, 3, 1],
        "C2": [1, -8, 3, 1],
        "C_inutile": [1, 2, 3, 4],
    }).to_excel(w, sheet_name="Cibles", index=False)

afficher(controler_template(tmp), "Template fautif (8 anomalies attendues)")

print("\n2 bis. Prefixe de scenario et longueur des titres de plan")
# « Riviere1-Q100 » (13) donne « Riviere1-Q100-APP06 » : 19 caracteres —
# il doit PASSER.
# Les trois premieres lignes prouvent que le controle ne crie pas a tort —
# un garde-fou qui se declenche sans raison apprend a etre ignore.
#
# LE DERNIER EST LA REGRESSION DU 20 SEPTEMBRE 2026. Vingt-deux
# caracteres : tous les titres « <prefixe>-APP07 » tiennent (28), mais le
# titre de reprise « <prefixe>-sans APP07 » fait 33 pour 32 tenables. Avant
# le correctif, ce classeur passait le controle avec « Premier_apport »
# vide — la valeur ne s'ecrit qu'au lancement — et le calage etait refuse
# ensuite, une fois lance.
tmp_prefixe = Path(tempfile.gettempdir()) / "template_prefixe.xlsx"
_echecs_prefixe = []
for prefixe, refus_attendu in (("", False), ("Q100", False),
                               ("Riviere1-Q100", False),
                               ("Riviere1_Q100_1000_ABC", True)):
    parametres.ecrire(tmp_prefixe, {
        "Dossier_projet_HECRAS": r"D:\projet", "Nom_projet": "Essai",
        "Nom_zone_2D": "Perimeter 1",
        "Nb_max_iterations_par_apport": 6, "Prefixe_scenario": prefixe})
    with pd.ExcelWriter(tmp_prefixe, engine="openpyxl") as w:
        pd.DataFrame({
            "Ordre": [1, 2],
            "Nom_Apport (BC line)": ["APP06", "APP07"],
            "Nom_Section (reference line)": ["S1", "S2"],
            "Nom_Cible": ["C1", "C2"],
        }).to_excel(w, sheet_name="Correspondance", index=False)
        pd.DataFrame({"Temps_h": list(range(11)),
                      "C1": list(range(11)),
                      "C2": list(range(11))}
                     ).to_excel(w, sheet_name="Cibles", index=False)
    vu = any(niveau == ERREUR and "Prefixe_scenario" in message
             for niveau, message in controler_template(tmp_prefixe))
    juste = vu == refus_attendu
    print(f"   [{'OK' if juste else 'ECHEC'}] "
          f"prefixe {prefixe!r:22s} -> {'refuse' if vu else 'accepte'} "
          f"(attendu : {'refuse' if refus_attendu else 'accepte'})")
    if not juste:
        _echecs_prefixe.append(prefixe)
if _echecs_prefixe:
    raise SystemExit(f"{len(_echecs_prefixe)} ECHEC(S) sur le prefixe : "
                     f"{_echecs_prefixe}")

# --- 3. Chaine SIG ----------------------------------------------------
print("\n3. CHAINE SIG : shapefiles, PK et coherence geographique")
import geopandas as gpd
from shapely.geometry import LineString

dossier_shp = Path(tempfile.gettempdir()) / "calage_shp_test"
dossier_shp.mkdir(exist_ok=True)
CRS = "EPSG:2154"

xs = np.linspace(0, 8000, 60)
axe_geom = LineString(zip(500000 + xs, 6200000 + 300 * np.sin(xs / 1400)))
gpd.GeoDataFrame({"Nom": ["Axe"]}, geometry=[axe_geom], crs=CRS).to_file(
    dossier_shp / "axe.shp")

def transversale(xl, demi=400.0):
    y = 300 * np.sin(xl / 1400)
    return LineString([(500000 + xl, 6200000 + y - demi),
                       (500000 + xl, 6200000 + y + demi)])

noms_s = ["S1", "S2", "S3", "S4"]
gpd.GeoDataFrame({"Nom": noms_s},
                 geometry=[transversale(x) for x in (900, 2800, 5100, 7400)],
                 crs=CRS).to_file(dossier_shp / "sections.shp")
noms_a = ["A1", "A2", "A3", "A4"]
gpd.GeoDataFrame({"Nom": noms_a},
                 geometry=[transversale(x, 250) for x in (200, 2100, 4300, 6600)],
                 crs=CRS).to_file(dossier_shp / "apports.shp")

def template_sig(chemin, ordre_sections, nom_apport_1="A1"):
    parametres.ecrire(chemin, {
        "Dossier_projet_HECRAS": r"D:\projet", "Nom_projet": "Essai",
        "Nom_zone_2D": "Zone2D", "Nb_max_iterations_par_apport": 6,
        "Fichier_SHP_Sections": str(dossier_shp / "sections.shp"),
        "Fichier_SHP_Apports": str(dossier_shp / "apports.shp"),
        "Fichier_SHP_Axe": str(dossier_shp / "axe.shp"),
        "Sens_axe": "amont_aval"})
    with pd.ExcelWriter(chemin, engine="openpyxl") as w:
        pd.DataFrame({
            "Ordre": [1, 2, 3, 4],
            "Nom_Apport (BC line)": [nom_apport_1] + noms_a[1:],
            "Nom_Section (reference line)": ordre_sections,
            "Nom_Cible": ["C1", "C2", "C3", "C4"],
        }).to_excel(w, sheet_name="Correspondance", index=False)
        pd.DataFrame({"Temps_h": [0, 1, 2, 3],
                      "C1": [1, 5, 3, 1], "C2": [1, 6, 3, 1],
                      "C3": [1, 7, 3, 1], "C4": [1, 8, 3, 1]}
                     ).to_excel(w, sheet_name="Cibles", index=False)

t_ok = dossier_shp / "template_sig_ok.xlsx"
template_sig(t_ok, noms_s)
anomalies, tableau = controler_geometrie(t_ok)
afficher(anomalies, "Chaine SIG coherente")
if tableau is not None:
    print("\n  PK calcules automatiquement par projection sur l'axe :")
    print("   " + tableau.to_string(index=False).replace("\n", "\n   "))

t_nom = dossier_shp / "template_sig_nom.xlsx"
template_sig(t_nom, noms_s, nom_apport_1="A_inexistant")
afficher(controler_geometrie(t_nom)[0],
         "\nApport declare absent du shapefile")

t_ordre = dossier_shp / "template_sig_ordre.xlsx"
template_sig(t_ordre, ["S1", "S3", "S2", "S4"])
afficher(controler_geometrie(t_ordre)[0],
         "\nOrdre declare S1, S3, S2, S4 alors que S2 precede S3")

# --- UNE ERREUR SANS RAPPORT AVEC LES PK NE DOIT PLUS LES EFFACER -----
#
# Mesure en production : sur un calage CONFORME de douze apports, une
# ligne d'injection de 94 cm — signalee « de longueur quasi nulle », ce
# qui est juste — a fait disparaitre le tableau des PK, et avec lui le
# profil en long et les pentes locales deduites. La porte testait la
# GRAVITE GENERALE du controle SIG, pas les conditions du PK.
dossier_court = Path(tempfile.gettempdir()) / "calage_shp_test_court"
dossier_court.mkdir(exist_ok=True)
# Le troisieme apport mesure 94 cm : assez pour lever l'ERREUR, pas assez
# pour deplacer un PK — il se projette sur l'axe comme les autres.
_geoms = [transversale(x, 250) for x in (200, 2100, 4300, 6600)]
_geoms[2] = LineString([(500000 + 4300, 6200000 + 0.0),
                        (500000 + 4300, 6200000 + 0.94)])
gpd.GeoDataFrame({"Nom": noms_a}, geometry=_geoms,
                 crs=CRS).to_file(dossier_court / "apports.shp")
t_court = dossier_court / "template_sig_court.xlsx"
template_sig(t_court, noms_s)
parametres.ecrire_un(t_court, "Fichier_SHP_Apports",
                     str(dossier_court / "apports.shp"))
_anos, _tab = controler_geometrie(t_court)

# CE MODULE N'AVAIT AUCUNE ASSERTION : son auto-test se contentait
# d'afficher, donc « il passe » ne voulait dire que « il n'a pas plante ».
# Ces deux controles-la, eux, doivent pouvoir ECHOUER.
_echecs_pk = []

def _verifier(libelle, condition, detail=""):
    print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
          + (f"  ->  {detail}" if detail else ""))
    if not condition:
        _echecs_pk.append(libelle)

print("\nUne ERREUR sans rapport avec les PK ne doit plus les effacer")
print("-----------------------------------------------------------")
# LE NIVEAU, PAS SEULEMENT LE TEXTE. Degrader cette anomalie en
# AVERTISSEMENT rouvrirait la porte d'origine et ferait verdir ce banc
# sans que rien ne soit corrige : on exige donc ERREUR.
_verifier("la ligne d'injection de 94 cm reste signalee en ERREUR",
          any(n == ERREUR and "quasi nulle" in m for n, m in _anos),
          " | ".join(m[:60] for n, m in _anos if n == ERREUR)[:140])
_verifier("et les PK sont malgre tout calcules",
          _tab is not None and len(_tab) > 0,
          "tableau rendu" if _tab is not None else "AUCUN TABLEAU")
if _echecs_pk:
    raise SystemExit(f"{len(_echecs_pk)} ECHEC(S) : {_echecs_pk}")

print("\nAnomalies que ce cas doit faire remonter :")
for att in [
    "parametre Nom_zone_2D manquant",
    "Nb_max_iterations insuffisant pour converger",
    "Simulation_debut au format francais",
    "colonne Ordre non contigue (1, 2, 4)",
    "nom d'apport en doublon (A2)",
    "Temps_h non strictement croissant",
    "cible C_absente declaree mais absente",
    "debit negatif dans C2",
]:
    print(f"   - {att}")
