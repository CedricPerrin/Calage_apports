# -*- coding: utf-8 -*-
"""
Verification de la disponibilite de tout ce qui est necessaire pour mettre en
oeuvre la methodologie de calage d'apports.

Ne verifie PAS : le modele hydraulique lui-meme et les hydrogrammes cibles,
qui sont fournis par l'utilisateur.

Usage :  python verification_environnement.py
"""

import importlib
import importlib.metadata as md
import os
import shutil
import sys
from pathlib import Path

DOSSIER = Path(__file__).parent
RACINE = DOSSIER.parent  # depot du projet : src/ contient la chaine, RACINE
                         # porte calage_apports/, la note methodologique, le
                         # template et STATUT.txt
# LA VERSION MINIMALE DE ras-commander VIENT DU NOYAU DU GREFFON, jamais
# recopiee ici. Elle y est justifiee (une 0.98.2 borne mal les tableaux
# d'hydrogramme : un apport ecrit y serait tronque SANS message), et le
# greffon refuse deja un interpreteur qui ne l'atteint pas. Ce script, lui,
# affichait la version sans la juger : le meme poste etait donc accepte ici
# et refuse la-bas. Deux regles qui doivent s'accorder finissent toujours par
# diverger — il n'y en a plus qu'une, et _version_ras_commander est reutilise
# pour la lire de la meme facon.
sys.path.insert(0, str(RACINE))
from calage_apports.noyau import (RAS_COMMANDER_MINIMUM,          # noqa: E402
                                  _version_ras_commander)
MINIMUM_LISIBLE = ".".join(str(x) for x in RAS_COMMANDER_MINIMUM)

OK, ABSENT, INFO = "[ OK ]", "[MANQ]", "[ -- ]"
resultats = []


def controler(libelle, condition, detail="", bloquant=True):
    """Enregistre et affiche un point de controle. Retourne la condition."""
    marque = OK if condition else (ABSENT if bloquant else INFO)
    resultats.append((marque, libelle, detail, bloquant and not condition))
    print(f"{marque} {libelle}" + (f"  ->  {detail}" if detail else ""))
    return condition


print("=" * 72)
print("VERIFICATION - MISE EN OEUVRE DU CALAGE D'APPORTS")
print("=" * 72)

# --------------------------------------------------------------------------
print("\n1. INTERPRETEUR PYTHON")
controler("Python >= 3.10", sys.version_info >= (3, 10),
          f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

# --------------------------------------------------------------------------
print("\n2. COUCHE D'ANALYSE (independante du code hydraulique)")
for paquet, module in [("numpy", "numpy"), ("scipy", "scipy"),
                       ("pandas", "pandas"), ("openpyxl", "openpyxl"),
                       ("matplotlib", "matplotlib")]:
    try:
        importlib.import_module(module)
        controler(paquet, True, md.version(paquet))
    except Exception as e:
        controler(paquet, False, str(e))

try:
    from criteres import diagnostiquer, kge, recaler, volume  # noqa: F401
    controler("module criteres.py importable", True,
              "kge / recaler / diagnostiquer / volume")
except Exception as e:
    controler("module criteres.py importable", False, str(e))

print("\n2 bis. COUCHE GEOMETRIQUE (shapefiles, PK, profil en long)")
for paquet in ["geopandas", "shapely", "pyproj"]:
    try:
        importlib.import_module(paquet)
        controler(paquet, True, md.version(paquet))
    except Exception as e:
        controler(paquet, False, str(e))

# geopandas lit les shapefiles via pyogrio (defaut depuis la v1) ou fiona :
# l'un des deux suffit.
_moteurs = []
for _m in ("pyogrio", "fiona"):
    try:
        importlib.import_module(_m)
        _moteurs.append(f"{_m} {md.version(_m)}")
    except Exception:
        pass
controler("moteur de lecture des shapefiles", bool(_moteurs),
          " + ".join(_moteurs) if _moteurs
          else "ni pyogrio ni fiona : installer pyogrio")

# Aller-retour reel sur un shapefile : c'est la seule preuve qui compte.
try:
    import tempfile as _tf
    import geopandas as _gpd0
    from shapely.geometry import LineString as _LS0
    _p = Path(_tf.gettempdir()) / "calage_verif_shp" / "essai.shp"
    _p.parent.mkdir(exist_ok=True)
    _gpd0.GeoDataFrame({"Nom": ["essai"]},
                       geometry=[_LS0([(0, 0), (100, 50)])],
                       crs="EPSG:2154").to_file(_p)
    _relu = _gpd0.read_file(_p)
    controler("ecriture et relecture d'un shapefile",
              len(_relu) == 1 and _relu.crs.to_epsg() == 2154,
              "EPSG conserve, geometrie relue")
except Exception as e:
    controler("ecriture et relecture d'un shapefile", False, str(e))

try:
    import geometrie
    attendues = ["lire_lignes", "lire_axe", "calculer_pk", "verifier_ordre",
                 "verifier_position_apports", "controler_shp",
                 "controler_contre_maillage", "echantillonner_axe",
                 "zones_2d", "maillage_du_modele", "profil_depuis_modele",
                 "controler_profil", "ecrire_dans_geometrie",
                 "lignes_depuis_modele"]
    absentes = [f for f in attendues if not hasattr(geometrie, f)]
    controler("module geometrie.py importable", not absentes,
              "lecture SHP, PK par projection, controles SIG, profil en long"
              if not absentes else ", ".join(absentes))
except Exception as e:
    controler("module geometrie.py importable", False, str(e))

# Test fonctionnel reel de la chaine geometrique, sans modele hydraulique.
try:
    import numpy as _np
    import geopandas as _gpd
    from shapely.geometry import LineString as _LS
    import geometrie as _geo

    _xs = _np.linspace(0, 8000, 60)
    _axe = _LS(zip(500000 + _xs, 6200000 + 300 * _np.sin(_xs / 1400)))

    def _tr(xl):
        y = 300 * _np.sin(xl / 1400)
        return _LS([(500000 + xl, 6200000 + y - 400), (500000 + xl, 6200000 + y + 400)])

    _g = _gpd.GeoDataFrame({"nom": ["S1", "S2", "S3"]},
                           geometry=[_tr(x) for x in (900, 2800, 5100)],
                           crs="EPSG:2154")
    _g = _geo.calculer_pk(_g, _axe)
    _pk = dict(zip(_g["nom"], _g["pk_m"]))
    _croissants = list(_g["pk_m"]) == sorted(_g["pk_m"])
    _detecte = bool(_geo.verifier_ordre(["S1", "S3", "S2"], _pk))
    controler("test fonctionnel des PK et de l'ordre",
              _croissants and _detecte and all(_g["croise_axe"]),
              f"PK {[round(v) for v in _g['pk_m']]} m ; ordre incoherent detecte")
except Exception as e:
    controler("test fonctionnel des PK et de l'ordre", False, str(e))

try:
    import controle_donnees
    manquantes = [f for f in ("controler_template", "controler_geometrie",
                              "controler_contre_modele")
                  if not hasattr(controle_donnees, f)]
    controler("module controle_donnees.py importable", not manquantes,
              "validation du template, de la chaine SIG et du modele"
              if not manquantes else ", ".join(manquantes))
except Exception as e:
    controler("module controle_donnees.py importable", False, str(e))

try:
    import livrables
    attendues = ["figure_comparaison", "figure_convergence",
                 "figure_atteinte", "figure_profil_longitudinal",
                 "figure_profil_en_long", "figure_apports_retenus",
                 "tableau_de_bord", "tableau_apports", "tableau_geometrie",
                 "journal_essais", "exporter_excel", "synthese",
                 "donnees_comparaison"]
    absentes = [f for f in attendues if not hasattr(livrables, f)]
    controler("module livrables.py importable", not absentes,
              "6 figures + 4 tableaux + export Excel + synthese"
              if not absentes else ", ".join(absentes))
except Exception as e:
    controler("module livrables.py importable", False, str(e))

try:
    import calage
    attendues = ["caler", "Configuration", "Modele", "ResultatCalcul",
                 "qualite_acceptable", "corriger_apport", "concordance",
                 "admissible", "ecart_combine", "rang_essai",
                 "decalage_minimisant_ecart", "ModeleFictif"]
    absentes = [f for f in attendues if not hasattr(calage, f)]
    controler("module calage.py importable", not absentes,
              "boucle sequentielle, independante du code hydraulique"
              if not absentes else ", ".join(absentes))
except Exception as e:
    controler("module calage.py importable", False, str(e))

try:
    import suivi
    attendues = ["commencer_apport", "enregistrer_essai", "valider_apport",
                 "echouer_apport", "terminer", "rapport", "tableau",
                 "avancement", "temps"]
    absentes = [m for m in attendues if not hasattr(suivi.Suivi, m)]
    controler("module suivi.py importable", not absentes,
              "rapport, tableau et figures reecrits a chaque apport valide"
              if not absentes else ", ".join(absentes))
except Exception as e:
    controler("module suivi.py importable", False, str(e))

# Test fonctionnel reel du critere
try:
    import numpy as np
    from criteres import diagnostiquer as _diag

    t = np.linspace(0.01, 30, 400)
    q = 100 * (t / 6) ** 2.5 * np.exp(2.5 * (1 - t / 6))
    d_id = _diag(t, q, t, q)
    d_bas = _diag(t, q, t, 0.75 * q)
    coherent = (abs(d_id.rapport_volume - 1.0) < 1e-3
                and abs(d_bas.rapport_volume - 0.75) < 1e-3
                and abs(d_bas.rapport_pic - 0.75) < 1e-3)
    controler("test fonctionnel du diagnostic", coherent,
              f"identite volume={100 * d_id.rapport_volume:.1f} % ; "
              f"-25% volume={100 * d_bas.rapport_volume:.1f} % "
              f"pointe={100 * d_bas.rapport_pic:.1f} %")
except Exception as e:
    controler("test fonctionnel du diagnostic", False, str(e))

# --------------------------------------------------------------------------
print("\n3. MISE EN OEUVRE HEC-RAS")
hecras = Path(r"C:\Program Files (x86)\HEC\HEC-RAS\7.0.1\Ras.exe")
controler("HEC-RAS 7.0.1 installe", hecras.exists(), str(hecras))

try:
    import ras_commander
    installee = md.version("ras-commander")
    lue = _version_ras_commander(f"ras-commander {installee}")
    # « lue is None » vaut « je ne sais pas », et laisse passer : meme regle
    # que dans le noyau, pour la meme raison — un format de version illisible
    # ne prouve pas une version trop ancienne.
    trop_ancienne = lue is not None and lue < RAS_COMMANDER_MINIMUM
    controler(f"ras-commander >= {MINIMUM_LISIBLE}", not trop_ancienne,
              installee + (" — trop ancienne : les versions anterieures "
                           "bornent mal les tableaux d'hydrogramme, un apport "
                           "ecrit y serait tronque en silence"
                           if trop_ancienne else ""))
except Exception as e:
    controler(f"ras-commander >= {MINIMUM_LISIBLE}", False, str(e))

FONCTIONS_RAS = {
    "RasUnsteady": ["extract_boundary_and_tables", "identify_tables",
                    "parse_fixed_width_table", "write_table_to_file",
                    "set_ic_from_output_profile", "get_restart_settings",
                    "update_restart_settings"],
    "RasCmdr": ["compute_plan"],
    "RasPlan": ["clone_plan", "clone_unsteady", "update_simulation_date",
                "enable_hdf_output_variable", "set_plan_title"],
    "HdfResultsPlan": ["get_reference_timeseries", "get_volume_accounting",
                       "get_runtime_data"],
    "HdfResultsMesh": ["get_profile_line_flow_timeseries",
                       "get_mesh_cells_timeseries", "get_mesh_max_ws",
                       "get_mesh_max_depth", "get_profile_line_peak_flow"],
    "GeomReferenceFeatures": ["add_reference_lines", "get_reference_lines",
                              "generate_reference_lines_from_longitudinal_line",
                              "add_reference_lines_from_longitudinal_line"],
    "GeomBcLines": ["add_bc_lines", "delete_bc_line", "rename_bc_line"],
    "HdfBndry": ["get_bc_lines", "get_reference_lines"],
    "HdfMesh": ["get_mesh_cell_points", "get_mesh_cell_polygons",
                "get_mesh_areas"],
}
try:
    import ras_commander as rc
    manquantes = []
    for classe, methodes in FONCTIONS_RAS.items():
        obj = getattr(rc, classe, None)
        if obj is None:
            manquantes.append(classe)
            continue
        manquantes += [f"{classe}.{m}" for m in methodes if not hasattr(obj, m)]
    controler("fonctions ras-commander requises", not manquantes,
              "toutes presentes" if not manquantes else ", ".join(manquantes))
except Exception as e:
    controler("fonctions ras-commander requises", False, str(e))

# Separateur decimal : le moteur Fortran de HEC-RAS y est sensible
import locale
sep = locale.localeconv().get("decimal_point", "?")
controler("separateur decimal du systeme", sep == ".", f"'{sep}' (doit etre '.')")

# --------------------------------------------------------------------------
print("\n3 bis. INTERFACE QGIS  (preparation des donnees, HEC-RAS uniquement)")
QGIS = Path(r"C:\Program Files\QGIS\LTR")
LANCEUR = QGIS / "bin" / "python-qgis-ltr.bat"
controler("QGIS LTR installe", LANCEUR.exists(), str(QGIS), bloquant=False)

# Le plugin s'installe dans le profil ACTIF, qui n'est pas toujours 'default'.
racine_profils = Path(os.environ.get("APPDATA", "")) / "QGIS" / "QGIS3" / "profiles"
profils = ([p.name for p in racine_profils.iterdir() if p.is_dir()]
           if racine_profils.exists() else [])
controler("profil(s) QGIS detecte(s)", bool(profils),
          ", ".join(profils) if profils else "aucun", bloquant=False)

controler("pont_hecras.py", (DOSSIER / "pont_hecras.py").exists(),
          "operations HEC-RAS hors du processus QGIS")

# La lecture des hydrogrammes ne doit dependre d'aucune bibliotheque tierce :
# la voie ras-commander qui passe par RASMapperLib exige pythonnet, et la
# fonction de synthese retourne un tableau VIDE sans rien signaler des qu'un
# jeu de donnees comporte plus d'une colonne. La lecture directe du HDF est
# donc la voie sure.
try:
    import pont_hecras
    controler("lecture directe des series HDF",
              hasattr(pont_hecras, "lire_serie_hdf"),
              "independante de pythonnet et de RASMapperLib")
except Exception as e:
    controler("lecture directe des series HDF", False, str(e))

try:
    importlib.import_module("clr")
    controler("pythonnet", True, "voie RASMapperLib disponible en complement",
              bloquant=False)
except Exception:
    controler("pythonnet", False,
              "absent : get_profile_line_flow_timeseries inutilisable. "
              "Sans effet, la lecture directe du HDF prend le relais",
              bloquant=False)
controler("plugin QGIS", (RACINE / "calage_apports" / "metadata.txt").exists(),
          str(RACINE / "calage_apports"), bloquant=False)
controler("archive d'installation", (RACINE / "calage_apports.zip").exists(),
          "a installer par Extensions > Installer depuis un ZIP",
          bloquant=False)
controler("test des actions du plugin",
          (DOSSIER / "test_plugin_qgis.py").exists(),
          "A LANCER AVEC LE PYTHON DE QGIS, pas celui-ci", bloquant=False)

# plugin.py depend de qgis.core : verification textuelle plutot qu'un import,
# qui echouerait systematiquement hors de QGIS.
try:
    _source_plugin = (RACINE / "calage_apports" / "plugin.py").read_text(
        encoding="utf-8")
    _attendus = ["class DialogueParametrage", "_onglet_modele", "_onglet_profil",
                "_onglet_resultats", "_onglet_validation",
                "_charger_couches_modele", "_composer_et_controler"]
    _manquants = [a for a in _attendus if a not in _source_plugin]
    controler("fenetre a 4 onglets presente dans plugin.py", not _manquants,
              "Modele HEC-RAS / Profil en long / Resultats et suivi / "
              "Validation" if not _manquants else f"absents : {_manquants}",
              bloquant=False)
except Exception as e:
    controler("fenetre a 4 onglets presente dans plugin.py", False, str(e),
              bloquant=False)

# Le pont doit repondre : c'est la seule preuve qui compte.
try:
    import json
    import subprocess

    resultat = subprocess.run(
        [sys.executable, str(DOSSIER / "pont_hecras.py"), "verifier"],
        capture_output=True, text=True, timeout=180)
    reponse = json.loads((resultat.stdout or "{}").strip().splitlines()[-1])
    controler("pont HEC-RAS operationnel", reponse.get("ok", False),
              f"python {reponse.get('python')}, "
              f"ras-commander {reponse.get('ras_commander')}, "
              f"h5py {reponse.get('h5py')}")
except Exception as e:
    controler("pont HEC-RAS operationnel", False, str(e))

if LANCEUR.exists():
    print("       Rappel : dans QGIS, h5py et donc ras-commander sont "
          "inutilisables\n"
          "       (conflit HDF5 avec GDAL). Le plugin passe par pont_hecras.py,\n"
          "       execute dans cet interpreteur-ci. Le sous-processus ne doit\n"
          "       heriter NI du PYTHONPATH NI du PATH de QGIS : les deux sont\n"
          "       reconstruits par noyau.environnement_propre().\n"
          "       Pour exercer les quatre actions du plugin :\n"
          f'         "{LANCEUR}" test_plugin_qgis.py')

# --------------------------------------------------------------------------
print("\n4. MISE EN OEUVRE TELEMAC-2D  (portage a ecrire)")
tel_env = any(os.environ.get(v) for v in ("HOMETEL", "SYSTELCFG", "TELEMAC_HOME"))
tel_exe = shutil.which("telemac2d.py") is not None
controler("openTELEMAC installe", tel_env or tel_exe,
          "non detecte - portage non realisable en l'etat", bloquant=False)

# --------------------------------------------------------------------------
print("\n5. DONNEES ET DOCUMENTS DU PROJET")
attendus_racine = [
    ("methodologie_calage_amont_aval.docx", True),
    ("template_donnees_calage.xlsx", True),
    ("STATUT.txt", True),
]
for nom, bloquant in attendus_racine:
    controler(nom, (RACINE / nom).exists(), bloquant=bloquant)

attendus_chaine = [
    ("criteres.py", True),
    ("controle_donnees.py", True),
    ("geometrie.py", True),
    ("livrables.py", True),
    ("suivi.py", True),
    ("calage.py", True),
    ("pilote_hecras.py", True),
]
for nom, bloquant in attendus_chaine:
    controler(nom, (DOSSIER / nom).exists(), bloquant=bloquant)

# Structure du template
try:
    import openpyxl
    wb = openpyxl.load_workbook(RACINE / "template_donnees_calage.xlsx")
    attendues = {"Instructions", "Parametres", "Correspondance", "Cibles"}
    controler("feuilles du template", attendues <= set(wb.sheetnames),
              ", ".join(wb.sheetnames))

    import pandas as _pd
    _par = _pd.read_excel(RACINE / "template_donnees_calage.xlsx",
                          sheet_name="Parametres")
    _cles = set(_par["Parametre"].astype(str))
    _sig = {"Source_geometrie", "Fichier_SHP_Sections", "Fichier_SHP_Apports",
            "Fichier_SHP_Axe", "Sens_axe", "Pas_profil_m"}
    controler("parametres SIG du template", _sig <= _cles,
              "route shapefile + axe hydraulique + terrain"
              if _sig <= _cles else f"absents : {sorted(_sig - _cles)}")
except Exception as e:
    controler("feuilles du template", False, str(e))

# Le template livre doit passer son propre controle sans erreur.
try:
    from controle_donnees import controler_template, ERREUR as _ERR
    _a = controler_template(RACINE / "template_donnees_calage.xlsx")
    _erreurs = [m for n, m in _a if n == _ERR]
    controler("template livre valide par controle_donnees", not _erreurs,
              f"{len(_a)} avertissement(s), aucune erreur" if not _erreurs
              else " ; ".join(_erreurs))
except Exception as e:
    controler("template livre valide par controle_donnees", False, str(e))

# --------------------------------------------------------------------------
print("\n" + "=" * 72)
bloquants = [r for r in resultats if r[3]]
if bloquants:
    print(f"{len(bloquants)} POINT(S) BLOQUANT(S) :")
    for _, libelle, detail, _ in bloquants:
        print(f"   - {libelle} {detail}")
else:
    print("TOUT EST DISPONIBLE pour la mise en oeuvre HEC-RAS.")
print("\nRESTE A FOURNIR PAR L'UTILISATEUR :")
print("   - le modele 2D HEC-RAS (projet dont un plan tourne deja)")
print("   - les shapefiles : sections de controle, lignes d'injection et")
print("     axe hydraulique, en projection metrique commune")
print("     (ou, a defaut, des lignes deja tracees et nommees dans le modele)")
print("   (aucun fichier de terrain a fournir : le profil en long est tire")
print("    du maillage, donc du terrain effectivement calcule par HEC-RAS)")
print("   - les hydrogrammes cibles (HSMF) a renseigner dans le template")
print("\nEPROUVE SUR UN MODELE REEL :")
print("   - compute_plan, la lecture du bilan de masse, la creation d'une")
print("     reference line et d'un apport interne, la mise a l'echelle et la")
print("     relecture des deux. Les pieges rencontres et les defauts corriges")
print("     a cette occasion sont listes dans STATUT.txt, et chacun est fige")
print("     par un test.")
print("\nRESTE A EPROUVER :")
print("   - une chaine de PLUSIEURS apports d'affilee, avec de vraies cibles :")
print("     seul un apport unique a ete cale de bout en bout sur cas reel.")
print("\nRESTE A CODER :")
print("   - la couche de pilotage TELEMAC-2D si ce code doit etre utilise")
print("=" * 72)

