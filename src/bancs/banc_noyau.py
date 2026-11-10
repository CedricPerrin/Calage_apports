# -*- coding: utf-8 -*-
"""
Banc d'auto-tests de calage_apports/noyau.py, hors QGIS.

Sorti du module le 10/11/2026 : c'etait son bloc « if __name__ ==
"__main__" », un millier de lignes que l'archive du plugin emportait (tout
.py de calage_apports/ y part, d'ou ce fichier HORS du paquet). Le code est
celui du bloc, a l'identique, desindente d'un cran. Il se lance seul
(python3 src/bancs/banc_noyau.py) ou par le module
(python calage_apports/noyau.py, la ligne de la CI), qui l'execute.

LE NOYAU S'IMPORTE COMME QUAND ON LE LANCE : module de premier niveau, son
dossier en tete de sys.path. Son import raccorde la chaine (_raccorder()),
exactement comme avant.

LES DOUBLURES PASSENT PAR LE MODULE. Dans le module, le banc reaffectait
_dossier_chaine, DOSSIER_EMBARQUE et emplacement_venv_hecras (par globals())
pour que les fonctions du noyau voient la nouvelle valeur. Ici, un nom
importe est une copie locale : chacune de ces lectures et ecritures s'ecrit
donc noyau.<nom>, sans quoi l'essai resterait vert sans plus rien eprouver.
"""
import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent
                       / "calage_apports"))

import noyau                                                # noqa: E402
from noyau import (  # noqa: E402
    FICHIERS_CHAINE, MAXIMUM_CANDIDATS, NOMS_FICHIERS, PAQUETS_HECRAS,
    PYTHON_MINIMUM, VARIABLE_INTERPRETEUR, _chemin_dans_ligne_py,
    _emplacements_python, _python_utilisable, _raccorder, _racines_recherche,
    apparier_paquet, appeler_pont, chaine_disponible, commande_pip_hecras,
    composer_paquet, controler_paquet, definir_chaine, dernier_journal,
    dossier_donnees_plugin, dossier_suivi_du_classeur,
    emplacement_venv_hecras, est_chaine, etat_cibles, fraicheur,
    hecras_ouvert, importer_hydrogrammes, installer_interpreteur,
    interpreteur_hecras, lister_projet_hecras, nom_classeur,
    pk_pour_affichage, preparer_classeur, prolonger_cibles, pythons_candidats,
    recette_installation_manuelle, resume_cibles, trouver_chaine,
    verifier_interpreteur)

import tempfile
import time

import geopandas as gpd
import numpy as np
from shapely.geometry import LineString

def site_packages(venv):
    """
    Le site-packages que CE venv porte reellement.

    « Lib/site-packages » sous Windows, « lib/python3.x/site-packages »
    ailleurs — et le « 3.x » ne se devine pas. sysconfig ne repond pas
    non plus : sur les distributions qui le corrigent, il rend
    « local/lib/python3.x/dist-packages », que venv ne cree pas, et
    get_preferred_scheme demande 3.10 quand PYTHON_MINIMUM est (3, 9).
    On lit donc la disposition sur le venv lui-meme.

    DEUX BANCS EN ONT BESOIN — les 9 et 10 — et une seule definition les
    sert : recopiee, elle se vouerait a diverger de son jumeau. Sans
    elle, tous deux s'arretaient sur un FileNotFoundError hors de
    Windows, et le banc du noyau ne passait pas depuis un clone neuf.
    """
    paquets = venv / "Lib" / "site-packages"
    if paquets.is_dir():
        return paquets
    return next(venv.glob("lib/python*/site-packages"), paquets)

print("=" * 72)
print("AUTO-TEST DU NOYAU DU PLUGIN  (hors QGIS)")
print("=" * 72)

print(f"\nChaine de calage : {trouver_chaine()}")
disponible, messages = chaine_disponible()
print(f"disponible : {disponible}")
for m in messages:
    print("   ", m)

dossier = Path(tempfile.gettempdir()) / "calage_paquet_test"
if dossier.exists():
    shutil.rmtree(dossier)

xs = np.linspace(0, 8000, 60)
axe_geom = LineString(zip(500000 + xs, 6200000 + 300 * np.sin(xs / 1400)))

def transversale(xl, demi=400.0):
    y = 300 * np.sin(xl / 1400)
    return LineString([(500000 + xl, 6200000 + y - demi),
                       (500000 + xl, 6200000 + y + demi)])

noms_s = ["S1_Amont", "S2_Pont", "S3_Confluence", "S4_Aval"]
noms_a = ["A1", "A2", "A3", "A4"]
sections = gpd.GeoDataFrame(
    {"nom": noms_s}, crs="EPSG:2154",
    geometry=[transversale(x) for x in (900, 2800, 5100, 7400)])
apports = gpd.GeoDataFrame(
    {"nom": noms_a}, crs="EPSG:2154",
    geometry=[transversale(x, 250) for x in (200, 2100, 4300, 6600)])
axe = gpd.GeoDataFrame({"nom": ["Axe"]}, geometry=[axe_geom], crs="EPSG:2154")

print("\n1. COMPOSITION DU PAQUET")
chemins = composer_paquet(dossier, sections, apports, axe)
for cle, chemin in chemins.items():
    print(f"   {cle:10s} -> {chemin.name}")

print("\n2. APPARIEMENT AMONT -> AVAL")
appariement = apparier_paquet(chemins)
print(f"   sens retenu : {appariement['sens']}")
for a, s in appariement["paires"]:
    print(f"   {a}  alimente  {s}")
for nom, pk in appariement["sans_section"]:
    print(f"   {nom} : aucune section en aval — non cale (PK {pk:.0f} m)")

print("\n3. CLASSEUR PRE-REMPLI")
# Le plugin demande l'identification du modele dans sa boite de dialogue :
# sans elle, le controle refuse de laisser lancer un calage.
classeur = preparer_classeur(dossier, appariement["paires"], chemins,
                             parametres={
    # Valeurs fictives : ce bloc n'exerce que le pre-remplissage du
    # classeur, aucun fichier n'est ouvert. Le dossier est relatif a
    # dessein — un chemin absolu ecrit dans un fichier livre finirait par
    # designer le poste de celui qui l'a ecrit.
    "Dossier_projet_HECRAS": str(dossier / "projet_fictif"),
    "Nom_projet": "Essai",
    "Nom_zone_2D": "Zone_2D_essai",
})
import pandas as pd
corr = pd.read_excel(classeur, sheet_name="Correspondance")
print(f"   {classeur.name} — feuille Correspondance deja renseignee :")
print("   " + corr.to_string(index=False).replace("\n", "\n   "))

print("\n4. CONTROLE DU PAQUET")
anomalies, tableau, _prolongation = controler_paquet(classeur)
erreurs = [m for n, m in anomalies if n == "ERREUR"]
for niveau, message in anomalies:
    print(f"   [{niveau:13s}] {message}")
etat = "conforme" if not erreurs else "A CORRIGER"
print(f"   -> {len(erreurs)} erreur(s), {len(anomalies) - len(erreurs)} "
      f"avertissement(s) : {etat}")
print("      (un classeur fraichement compose n'a pas encore de cibles :")
print("       c'est un avertissement, pas une erreur)")
if tableau is not None:
    print("\n   PK calcules :")
    print("   " + tableau.to_string(index=False).replace("\n", "\n   "))

print("\n4 bis. PROLONGATION DES CIBLES PAR DES ZEROS")
# LE GESTE QUE LE PRE-VOL RECLAME. Un hydrogramme cible qui s'arrete avant
# la fin de la simulation fait refuser le calcul par HEC-RAS ; le
# prolonger a la main, colonne par colonne dans Excel, etait la seule
# issue. Ce qui est eprouve ici : le pas est celui de la SAISIE, les
# valeurs ajoutees sont des ZEROS (une crue retombee, pas la derniere
# valeur connue — invariant 8), l'existant n'est pas touche, et rappeler
# la fonction ne fait rien.
import openpyxl
_cl = dossier / "essai_prolongation.xlsx"
_wb = openpyxl.Workbook()
_fe = _wb.active
_fe.title = "Cibles"
_fe.append(["Temps_h", "Cible_S1", "Cible_S2"])
for _i in range(5):                       # 0,00 -> 1,00 h au quart d'heure
    _fe.append([round(0.25 * _i, 2), 10.0 + _i, 20.0 + _i])
_wb.save(_cl)

_bilan = prolonger_cibles(_cl, 2.0)
_lu = pd.read_excel(_cl, sheet_name="Cibles")
_ajoutees = _lu[_lu["Temps_h"] > 1.0 + 1e-9]
_controles = [
    ("le pas de la saisie est repris", abs(_bilan["pas_h"] - 0.25) < 1e-9,
     f"{_bilan['pas_h']} h"),
    ("la duree visee est atteinte", abs(_lu["Temps_h"].max() - 2.0) < 1e-9,
     f"{_lu['Temps_h'].max()} h"),
    ("les lignes ajoutees valent ZERO, pas la derniere valeur",
     bool((_ajoutees[["Cible_S1", "Cible_S2"]] == 0).all().all()),
     f"{len(_ajoutees)} ligne(s)"),
    ("la saisie d'origine est intacte",
     list(_lu["Cible_S1"][:5]) == [10.0, 11.0, 12.0, 13.0, 14.0],
     str(list(_lu["Cible_S1"][:5]))),
    ("rappeler la fonction n'ajoute rien",
     prolonger_cibles(_cl, 2.0)["ajoutees"] == 0),
    ("une cible deja assez longue n'est pas touchee",
     prolonger_cibles(_cl, 1.5)["ajoutees"] == 0),
]
for _libelle, _ok, *_detail in _controles:
    print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}"
          + (f"  ->  {_detail[0]}" if _detail else ""))
    assert _ok, _libelle
_cl.unlink(missing_ok=True)

print("\n4 bis bis. IMPORT DES HYDROGRAMMES D'UN CALCUL PRECEDENT")
# (24/09/2026, demande utilisateur.) Les cibles vont par EN-TETE, les
# pentes par NOM D'APPORT ; une colonne sans correspondance n'est pas
# touchee ; et tout refus laisse l'Excel de ce calcul intact.

def _excel_objectifs(chemin, paires, cibles, pentes=None):
    """Correspondance et Cibles, aux en-tetes de preparer_classeur."""
    _wb = openpyxl.Workbook()
    _fe = _wb.active
    _fe.title = "Correspondance"
    _fe.append(["Ordre", "Nom_Apport (BC line)",
                "Nom_Section (reference line)", "Nom_Cible",
                "Pente_m_par_m"])
    for _rang, (_a, _s) in enumerate(paires, 1):
        _fe.append([_rang, _a, _s, f"Cible_{_s}", (pentes or {}).get(_a)])
    _fc = _wb.create_sheet("Cibles")
    _fc.append(list(cibles))
    for _ligne in zip(*cibles.values()):
        _fc.append(list(_ligne))
    _wb.save(chemin)

_ce = dossier / "essai_import_ce_calcul.xlsx"
_prec = dossier / "essai_import_precedent.xlsx"
_paires_ce = [("A1", "S1"), ("A2", "S2"), ("A3", "S3")]
_excel_objectifs(_ce, _paires_ce, {"Temps_h": [], "Cible_S1": [],
                                   "Cible_S2": [], "Cible_S3": []})
_excel_objectifs(_prec, [("A1", "S1"), ("A2", "S2"), ("A9", "S9")],
                 {"Temps_h": [0.0, 1.0, 2.0], "Cible_S1": [1.0, 2.0, 3.0],
                  "Cible_S2": [4.0, 5.0, 6.0], "Cible_S9": [7.0, 8.0, 9.0]},
                 pentes={"A1": 0.02})
_imp = importer_hydrogrammes(_prec, _ce)
_cib = pd.read_excel(_ce, sheet_name="Cibles")
_cor = pd.read_excel(_ce, sheet_name="Correspondance")
_pente = dict(zip(_cor["Nom_Apport (BC line)"], _cor["Pente_m_par_m"]))

def _intact(chemin):
    return (chemin.stat().st_size, chemin.stat().st_mtime_ns)

_controles = [
    ("les cibles de meme en-tete sont importees, et elles seules",
     _imp["importees"] == ["Cible_S1", "Cible_S2"], str(_imp["importees"])),
    ("leurs valeurs et le temps arrivent",
     list(_cib["Cible_S1"]) == [1.0, 2.0, 3.0]
     and list(_cib["Temps_h"]) == [0.0, 1.0, 2.0],
     str(list(_cib["Cible_S1"]))),
    ("une cible sans correspondance reste vide, et est nommee",
     _imp["vides"] == ["Cible_S3"] and _cib["Cible_S3"].isna().all(),
     str(_imp["vides"])),
    ("une cible absente de ce calcul est ignoree, et nommee",
     _imp["ignorees"] == ["Cible_S9"], str(_imp["ignorees"])),
    ("la pente d'un apport de meme nom est reprise, les autres non",
     _imp["pentes"] == ["A1"] and _pente["A1"] == 0.02
     and pd.isna(_pente["A3"]), str(_pente)),
    ("l'Excel d'avant est garde en .precedent",
     Path(_imp["sauvegarde"]).exists(), Path(_imp["sauvegarde"]).name),
]
# AUCUNE CIBLE EN COMMUN : refus, rien d'ecrit.
_excel_objectifs(_prec, [("A9", "S9")],
                 {"Temps_h": [0.0, 1.0], "Cible_S9": [7.0, 8.0]})
_avant = _intact(_ce)
try:
    importer_hydrogrammes(_prec, _ce)
    _dit = "aucun refus"
except ValueError as e:
    _dit = str(e)
_controles.append(("sans cible commune, l'import refuse et nomme les deux "
                   "listes, sans rien ecrire",
                   "Cible_S1" in _dit and "Cible_S9" in _dit
                   and _intact(_ce) == _avant, _dit))
# UNE COLONNE DEJA SAISIE SUR UNE AUTRE BASE DE TEMPS : refus.
_excel_objectifs(_ce, _paires_ce, {"Temps_h": [0.0, 0.5],
                                   "Cible_S1": [None, None],
                                   "Cible_S2": [None, None],
                                   "Cible_S3": [3.0, 4.0]})
_excel_objectifs(_prec, [("A1", "S1")],
                 {"Temps_h": [0.0, 1.0, 2.0], "Cible_S1": [1.0, 2.0, 3.0]})
_avant = _intact(_ce)
try:
    importer_hydrogrammes(_prec, _ce)
    _dit = "aucun refus"
except ValueError as e:
    _dit = str(e)
_controles.append(("une colonne saisie sur une autre base de temps fait "
                   "refuser l'import, sans rien ecrire",
                   "Cible_S3" in _dit and "Temps_h" in _dit
                   and _intact(_ce) == _avant, _dit))
try:
    importer_hydrogrammes(_ce, _ce)
    _dit = "aucun refus"
except ValueError as e:
    _dit = str(e)
_controles.append(("importer l'Excel de ce calcul dans lui-meme est refuse",
                   "déjà" in _dit, _dit))
for _libelle, _ok, *_detail in _controles:
    print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}"
          + (f"  ->  {_detail[0][:100]}" if _detail else ""))
    assert _ok, _libelle
for _f in (_ce, _prec, Path(_imp["sauvegarde"])):
    _f.unlink(missing_ok=True)

# ET LE LANCEMENT REFUSE UN CLASSEUR SANS COLONNE Temps_h (04/09/2026).
# etat_cibles() est ce que le plugin consulte juste avant de partir. Il
# laissait passer un en-tete A1 remplace ; le pont plantait ensuite en
# arriere-plan, hors de vue, sur un scalaire. Refuser ICI, et nommer
# l'en-tete trouve : c'est lui qu'il faut corriger.
_wb = openpyxl.Workbook()
_fe = _wb.active
_fe.title = "Correspondance"
_fe.append(["Ordre", "Nom_Apport (BC line)",
            "Nom_Section (reference line)", "Nom_Cible"])
_fe.append([1, "A1", "S1", "Cible_S1"])
_fc = _wb.create_sheet("Cibles")
_fc.append(["Temps (h)", "Cible_S1"])
_fc.append([0.0, 10.0])
_wb.save(_cl)
try:
    etat_cibles(_cl)
    _dit = "aucune erreur"
except ValueError as e:
    _dit = str(e)
except Exception as e:                                  # noqa: BLE001
    _dit = f"{type(e).__name__}: {e}"
_libelle = ("sans colonne Temps_h, l'etat des cibles refuse et nomme "
            "l'en-tete trouve")
_ok = "Temps_h" in _dit and "Temps (h)" in _dit
print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  {_dit[:100]}")
assert _ok, _libelle
_cl.unlink(missing_ok=True)

# ET UNE COLONNE DE TEMPS VIDE SOUS SON EN-TETE NE RENSEIGNE RIEN. Le meme
# classeur du 04/09 avait six colonnes de debit pleines (418 lignes) et UN
# SEUL instant : six cibles « renseignees » pour le plugin, six
# « inexploitables » pour le pont, qui l'aurait dit en arriere-plan apres
# l'en-tete corrige. Meme regle des deux cotes : deux instants numeriques
# en face de deux debits numeriques (_cibles_depuis_classeur).
_wb = openpyxl.Workbook()
_fe = _wb.active
_fe.title = "Correspondance"
_fe.append(["Ordre", "Nom_Apport (BC line)",
            "Nom_Section (reference line)", "Nom_Cible"])
_fe.append([1, "A1", "S1", "Cible_S1"])
_fe.append([2, "A2", "S2", "Cible_S2"])
_fc = _wb.create_sheet("Cibles")
_fc.append(["Temps_h", "Cible_S1", "Cible_S2"])
_fc.append([0.0, 0.0, 0.0])
for _i in range(1, 6):
    _fc.append([None, 10.0 * _i, 5.0 * _i])       # temps VIDE, debits pleins
_wb.save(_cl)
_etat = etat_cibles(_cl)
_libelle = "une colonne de temps vide rend les cibles non renseignees"
_ok = _etat["manquantes"] == ["S1", "S2"] and _etat["renseignees"] == 0
print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  {_etat}")
assert _ok, _libelle
for _i in range(1, 6):                              # les instants, et tout va
    _fc.cell(row=_i + 2, column=1, value=0.25 * _i)
_wb.save(_cl)
_etat = etat_cibles(_cl)
_libelle = "avec ses instants, la meme feuille renseigne les deux cibles"
_ok = _etat["manquantes"] == [] and _etat["renseignees"] == 2
print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  {_etat}")
assert _ok, _libelle
_cl.unlink(missing_ok=True)

# LE PREFIXE DE SCENARIO NOMME LE CLASSEUR (0.8.4). Deux scenarios d'un
# meme dossier de sortie partageaient « donnees_calage.xlsx » : composer
# le Q10 ecrasait la feuille Correspondance du Q100.
for _prefixe, _attendu in (("", "donnees_calage.xlsx"),
                           ("Q100", "donnees_calage_Q100.xlsx"),
                           ("Q100_", "donnees_calage_Q100.xlsx"),
                           ("Q100 V2", "donnees_calage_Q100_V2.xlsx"),
                           ("Q100/bis", "donnees_calage_Q100_bis.xlsx"),
                           ("Riviere - Q100", "donnees_calage_Riviere_-_Q100.xlsx"),
                           ("Riviere - Q100 - ", "donnees_calage_Riviere_-_Q100.xlsx")):
    _rendu = nom_classeur(_prefixe)
    _ok = _rendu == _attendu
    print(f"   [{'OK' if _ok else 'ECHEC'}] prefixe « {_prefixe} »  ->  {_rendu}")
    assert _ok, f"nom_classeur({_prefixe!r}) rend {_rendu}, attendu {_attendu}"
_dossier_p = dossier / "deux_scenarios"
_q100 = preparer_classeur(_dossier_p, [("A1", "S1")], {},
                          parametres={"Prefixe_scenario": "Q100"})
_q10 = preparer_classeur(_dossier_p, [("A1", "S1")], {},
                         parametres={"Prefixe_scenario": "Q10"})
_libelle = "deux scenarios, deux classeurs dans le meme dossier de sortie"
_ok = (_q100 != _q10 and Path(_q100).exists() and Path(_q10).exists())
print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  "
      f"{Path(_q100).name} et {Path(_q10).name}")
assert _ok, _libelle
# ET LE DERNIER JOURNAL EST CELUI AU NOM LE PLUS GRAND : l'horodatage du
# nom suffit, aucune date de fichier n'est lue.
for _nom in ("calage_20260913_235959.log", "calage_20260914_082326.log"):
    (_dossier_p / _nom).write_text("", encoding="utf-8")
_rendu = dernier_journal(_q100)
_ok = _rendu is not None and _rendu.name == "calage_20260914_082326.log"
print(f"   [{'OK' if _ok else 'ECHEC'}] dernier_journal  ->  "
      f"{_rendu.name if _rendu else None}")
assert _ok, f"dernier_journal rend {_rendu}"
_ok = dernier_journal(dossier / "sans_journal" / "x.xlsx") is None
print(f"   [{'OK' if _ok else 'ECHEC'}] dernier_journal sans journal  ->  None")
assert _ok, "dernier_journal devrait rendre None sans journal"

# ET RECOMPOSER N'EFFACE PAS UNE SAISIE QU'ON NE SAIT PAS RELIRE.
# preparer_classeur() preserve les cibles deja collees en les cherchant
# sous l'en-tete « Temps_h » ; sans lui, la feuille etait REECRITE VIDE,
# sans un mot — six colonnes de 418 lignes, et le plugin qui promet a
# l'ecran que « recomposer plus tard preserve les hydrogrammes deja
# saisis » (04/09/2026). Le geste naturel apres le nouveau message
# d'etat_cibles est justement de recomposer.
_dossier2 = dossier / "recomposition"
_dossier2.mkdir(parents=True, exist_ok=True)
_cl2 = _dossier2 / NOMS_FICHIERS["classeur"]
_wb = openpyxl.Workbook()
_fc = _wb.active
_fc.title = "Cibles"
_fc.append(["\u00b6", "Cible_S1", "Cible_S2"])       # en-tete A1 remplace
for _i in range(6):
    _fc.append([None, 10.0 + _i, 20.0 + _i])
_wb.save(_cl2)
try:
    preparer_classeur(_dossier2, [("A1", "S1"), ("A2", "S2")], {})
    _dit = "aucune erreur"
except ValueError as e:
    _dit = str(e)
_reste = pd.read_excel(_cl2, sheet_name="Cibles")
_libelle = "recomposer sans en-tete Temps_h refuse et laisse la saisie intacte"
# LA PRESERVATION EN PREMIER : sur le code d'avant, « Temps_h in _dit »
# court-circuitait et la ligne d'ECHEC ne disait que « aucune erreur »,
# sans jamais montrer la saisie detruite qui justifie le garde-fou.
_garde = int(_reste[["Cible_S1", "Cible_S2"]].notna().sum().sum())
# ET PAS DE COPIE « .precedent » : un refus ne met rien de cote (la 0.9.2
# le faisait, et le classeur canonique disparaissait).
_precedent = _cl2.with_name(_cl2.stem + ".precedent" + _cl2.suffix)
_ok = (_garde == 12 and "Temps_h" in _dit and "¶" in _dit
       and not _precedent.exists())
print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  "
      f"{_garde} valeurs restantes sur 12 ; precedent={_precedent.exists()} ; "
      f"{_dit[:60]}")
assert _ok, _libelle
_cl2.unlink(missing_ok=True)

# UNE COLONNE DE TEMPS EN DATES NE PASSE PAS. pd.to_numeric ne rend NaN
# que sur du texte : sur une colonne de DATES Excel — la facon la plus
# courante de coller une chronique — il rend les microsecondes depuis
# 1970. Le compte « deux instants » etait donc satisfait, le calage
# partait, et le pont mourait sur une allocation de 536 Gio dans
# reechantillonner (relecture adverse du 04/09/2026).
# « as _dt » ET PAS « import datetime » : noyau.py importe la CLASSE
# datetime (ligne 22), qu'un import du MODULE recouvrirait — tout ce qui
# suit et appelle datetime.fromtimestamp() casserait alors, en silence.
import datetime as _dt
_wb = openpyxl.Workbook()
_fe = _wb.active
_fe.title = "Correspondance"
_fe.append(["Ordre", "Nom_Apport (BC line)",
            "Nom_Section (reference line)", "Nom_Cible"])
_fe.append([1, "A1", "S1", "Cible_S1"])
_fc = _wb.create_sheet("Cibles")
_fc.append(["Temps_h", "Cible_S1"])
for _i in range(3):
    _fc.append([_dt.datetime(2020, 1, 1, _i), 10.0 * _i])
_wb.save(_cl)
try:
    etat_cibles(_cl)
    _dit = "aucune erreur"
except ValueError as e:
    _dit = str(e)
except Exception as e:                                  # noqa: BLE001
    _dit = f"{type(e).__name__}: {e}"
_libelle = "une colonne de temps en DATES est refusee, pas comptee"
_ok = "date" in _dit.lower() and "heures" in _dit.lower()
print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  {_dit[:100]}")
assert _ok, _libelle
_cl.unlink(missing_ok=True)

# ET LE GARDE-FOU DE RECOMPOSITION NE CHERCHE PLUS SA PREUVE DANS LA LIGNE
# ABIMEE. Il exigeait un en-tete « Cible_ » non vide — or « Temps_h » et
# les « Cible_ » vivent dans la MEME ligne 1 : ligne supprimee, triee avec
# les donnees, ou recouverte par un bloc colle avec ses propres titres, le
# detecteur partait avec elle et la feuille etait reecrite VIDE. Ce sont
# les VALEURS sous la ligne 1 qui disent qu'il y a quelque chose a perdre.
for _cas, _entetes in (("ligne 1 recouverte", ["t (h)", "Q_S1", "Q_S2"]),
                       ("ligne 1 supprimee", [0.0, 10.0, 20.0])):
    _dossier3 = dossier / ("recomposition_" + _cas.replace(" ", "_"))
    _dossier3.mkdir(parents=True, exist_ok=True)
    _cl3 = _dossier3 / NOMS_FICHIERS["classeur"]
    _wb = openpyxl.Workbook()
    _fc = _wb.active
    _fc.title = "Cibles"
    _fc.append(_entetes)
    for _i in range(6):
        _fc.append([0.25 * _i, 10.0 + _i, 20.0 + _i])
    _wb.save(_cl3)
    try:
        preparer_classeur(_dossier3, [("A1", "S1"), ("A2", "S2")], {})
        _dit = "aucune erreur"
    except ValueError as e:
        _dit = str(e)
    _reste = pd.read_excel(_cl3, sheet_name="Cibles")
    _valeurs = int(_reste.iloc[:, :3].notna().sum().sum())
    _libelle = f"recomposer avec la {_cas} refuse et garde la saisie"
    _ok = "Temps_h" in _dit and _valeurs >= 18
    print(f"   [{'OK' if _ok else 'ECHEC'}] {_libelle}  ->  "
          f"{_valeurs} valeurs restantes ; {_dit[:60]}")
    assert _ok, _libelle

print("\n4 ter. EMPLACEMENT DE L'ENVIRONNEMENT HEC-RAS")
# CE QU'IL FAUT EPROUVER ICI : que le bouton « Installer… » ait TOUJOURS
# un endroit ou ecrire, et que cet endroit ne soit JAMAIS le dossier
# d'installation de l'extension — que le gestionnaire de QGIS efface a
# chaque mise a jour.
# Le controle inverse (« la copie embarquee est refusee », emplacement
# None) a existe jusqu'au 31/08/2026 et VALIDAIT UN DEFAUT : refuser
# l'emplacement etait juste, en conclure qu'il n'y en avait aucun rendait
# le bouton inutilisable sur un poste neuf — le seul ou il sert.
_garde = noyau._dossier_chaine
_garde_emb = noyau.DOSSIER_EMBARQUE
_donnees = dossier_donnees_plugin() / "venv-hecras"
try:
    # LA COPIE EMBARQUEE N'EXISTE QUE DANS LE ZIP, jamais sur le disque
    # d'un poste de developpement : le controle qui la concerne etait donc
    # IGNORE ici, et c'est ce qui a laisse passer le defaut du 31/08. On
    # en FABRIQUE une, pour que la branche soit toujours exercee.
    _faux_emb = dossier / "faux_plugin" / "chaine"
    _faux_emb.mkdir(parents=True, exist_ok=True)
    for _f in FICHIERS_CHAINE:
        (_faux_emb / _f).write_text("# temoin\n", encoding="utf-8")
    noyau.DOSSIER_EMBARQUE = _faux_emb
    noyau._dossier_chaine = _faux_emb
    _ou = emplacement_venv_hecras()
    print(f"   [{'OK' if _ou == _donnees else 'ECHEC'}] chaine embarquee "
          f"-> dossier de donnees, PAS le plugin  ->  {_ou}")
    assert _ou == _donnees, _ou
    assert _faux_emb not in _ou.parents and _faux_emb.parent not in _ou.parents
    noyau.DOSSIER_EMBARQUE = _garde_emb
    noyau._dossier_chaine = Path(noyau.__file__).resolve().parent.parent / "src"
    if est_chaine(noyau._dossier_chaine):
        _attendu = noyau._dossier_chaine.parent / ".venv"
        print(f"   [{'OK' if emplacement_venv_hecras() == _attendu else 'ECHEC'}]"
              f" une chaine externe -> a cote d'elle  ->  {_attendu}")
        assert emplacement_venv_hecras() == _attendu
    noyau._dossier_chaine = None
    if trouver_chaine() is None:
        _ou = emplacement_venv_hecras()
        print(f"   [{'OK' if _ou == _donnees else 'ECHEC'}] sans aucune "
              f"chaine, un emplacement est quand meme propose  ->  {_ou}")
        assert _ou == _donnees
    else:
        print("   (une chaine est trouvee automatiquement : controle ignore)")
    # L'ENVIRONNEMENT INSTALLE DOIT SE RETROUVER SEUL a la session
    # suivante, sans QSettings : sinon un profil QGIS neuf le perdrait.
    # LA CONDITION AFFICHEE EST CELLE QU'ON VERIFIE. Elle valait
    # « <Path> or True » : toujours vraie, donc « [OK] » quoi qu'il
    # arrive. Seul l'assert controlait quelque chose, et la ligne au-
    # dessus de lui mentait.
    _hors_plugin = (noyau.DOSSIER_EMBARQUE.parent
                     not in dossier_donnees_plugin().parents)
    print(f"   [{'OK' if _hors_plugin else 'ECHEC'}]"
          f" le dossier de donnees est hors du plugin  ->  "
          f"{dossier_donnees_plugin()}")
    assert _hors_plugin

    # --- 4 quater. LE PLUGIN CHERCHE LES PYTHON TOUT SEUL -------------
    print("\n4 quater. Recherche des Python utilisables")
    _cands = pythons_candidats()
    for _c in _cands:
        print(f"      {'.'.join(str(n) for n in _c['version']):9} "
              f"{_c['origine']:12} {_c['chemin']}")

    # AUCUN LEURRE NE PASSE. C'est le defaut qui a bloque un poste neuf le
    # 01/09/2026 : deux « python.exe » dans le PATH, tous deux des alias
    # WindowsApps de zero octet, et le selecteur de fichier n'avait rien a
    # proposer. On FABRIQUE le leurre plutot que de dependre du poste.
    _leurre = dossier / "WindowsApps" / "python.exe"
    _leurre.parent.mkdir(parents=True, exist_ok=True)
    _leurre.write_bytes(b"")
    print(f"   [{'OK' if _python_utilisable(_leurre) is None else 'ECHEC'}]"
          f" un alias WindowsApps de zero octet est refuse")
    assert _python_utilisable(_leurre) is None
    _vide = dossier / "python.exe"
    _vide.write_bytes(b"")
    print(f"   [{'OK' if _python_utilisable(_vide) is None else 'ECHEC'}]"
          f" un fichier vide hors WindowsApps aussi")
    assert _python_utilisable(_vide) is None
    _pasla = dossier / "jamais" / "python.exe"
    print(f"   [{'OK' if _python_utilisable(_pasla) is None else 'ECHEC'}]"
          f" un chemin inexistant aussi")
    assert _python_utilisable(_pasla) is None

    # ON VALIDE EN EXECUTANT : le python qui fait tourner ce banc doit
    # passer, puisqu'il sait demarrer et porte venv.
    _moi = _python_utilisable(sys.executable)
    print(f"   [{'OK' if _moi is not None else 'ECHEC'}] le python courant "
          f"est reconnu utilisable  ->  {_moi}")
    assert _moi is not None and _moi >= PYTHON_MINIMUM

    # L'ORDRE EST LA DECISION DU 01/09/2026 : un Python independant passe
    # AVANT celui de QGIS, parce qu'un venv bati sur apps\Python3xx casse
    # quand QGIS monte de version.
    _indep = [i for i, c in enumerate(_cands)
              if c["origine"] == "independant"]
    _qgis = [i for i, c in enumerate(_cands) if c["origine"] == "QGIS"]
    _ordre = (not _indep or not _qgis or max(_indep) < min(_qgis))
    print(f"   [{'OK' if _ordre else 'ECHEC'}] tout Python independant "
          f"passe avant ceux de QGIS  ->  "
          f"{len(_indep)} independant(s), {len(_qgis)} QGIS")
    assert _ordre
    _versions = [c["version"] for c in _cands
                 if c["origine"] == "independant"]
    print(f"   [{'OK' if _versions == sorted(_versions, reverse=True) else 'ECHEC'}]"
          f" et a origine egale, la version la plus recente d'abord  ->  "
          f"{['.'.join(str(n) for n in v) for v in _versions]}")
    assert _versions == sorted(_versions, reverse=True)
    print(f"   [{'OK' if all(c['chemin'].is_file() for c in _cands) else 'ECHEC'}]"
          f" tous les candidats rendus existent vraiment")
    assert all(c["chemin"].is_file() for c in _cands)
    # installer_interpreteur REFUSE un python de base inexistant, sans
    # rien creer : c'est le seul chemin de cette fonction qu'un banc peut
    # emprunter sans telecharger plusieurs centaines de mega-octets.
    _chemin, _motif = installer_interpreteur(dossier / "python_absent.exe")
    print(f"   [{'OK' if _chemin is None and _motif else 'ECHEC'}]"
          f" un python de base inexistant est refuse  ->  {_motif[:60]}")
    assert _chemin is None and _motif
finally:
    noyau._dossier_chaine = _garde
    noyau.DOSSIER_EMBARQUE = _garde_emb

print("\n4 quinquies. TROUVER PYTHON SUR UN POSTE QUELCONQUE")
# CE QUI SE JOUE ICI : le neophyte qui ne sait pas ou est Python. Le
# plugin le cherche pour lui, et ne doit pas le manquer sur un poste
# ordinaire — un disque systeme autre que C:, un dossier de programmes
# redirige, un chemin qui contient des espaces.
for _ligne, _attendu in [
        (r" -V:3.13 *        C:\Users\x\Python313\python.exe",
         r"C:\Users\x\Python313\python.exe"),
        # LE DEFAUT CORRIGE : la lecture cherchait « c: » et laissait
        # tomber la ligne sans un mot. Un poste dont le disque systeme
        # est petit installe volontiers Python sur D:.
        (r" -V:3.12          D:\Python312\python.exe",
         r"D:\Python312\python.exe"),
        (r" -V:3.11          C:\Program Files\Python 3.11\python.exe",
         r"C:\Program Files\Python 3.11\python.exe"),
        (r" -3.11-64        E:\Py\python.exe", r"E:\Py\python.exe"),
        (r" -V:3.13         \\serveur\part\Python313\python.exe",
         r"\\serveur\part\Python313\python.exe"),
        ("Installed Pythons found by py Launcher", None),
        # pythonw n'ecrit rien sur la sortie standard : le sonder coute
        # un sous-processus pour un rejet certain.
        (r" -V:3.13          C:\Py\pythonw.exe", None)]:
    _lu = _chemin_dans_ligne_py(_ligne)
    print(f"   [{'OK' if _lu == _attendu else 'ECHEC'}] py -0p : "
          f"{_ligne.strip()[:44]:44s} -> {_lu}")
    assert _lu == _attendu, (_ligne, _lu, _attendu)

# LES RACINES SONT WINDOWS PAR NATURE : %ProgramFiles% et les lettres de
# lecteur n'ont pas d'equivalent ailleurs. Hors Windows, ce qu'on exige
# est qu'elle rende une liste sans lever — le PATH prend le relais.
_racines = _racines_recherche()
_attendu_racines = bool(_racines) if os.name == "nt" else True
print(f"   [{'OK' if _attendu_racines else 'ECHEC'}] des racines de "
      f"recherche sont proposees  ->  {len(_racines)} sur ce poste "
      f"({'Windows' if os.name == 'nt' else 'hors Windows : le PATH suffit'})")
assert _attendu_racines
assert all(isinstance(r, Path) for r in _racines)
_emplacements = _emplacements_python()
_cles = [str(e).lower() for e in _emplacements]
print(f"   [{'OK' if len(_cles) == len(set(_cles)) else 'ECHEC'}] "
      f"aucun emplacement propose deux fois  ->  {len(_cles)} chemins")
assert len(_cles) == len(set(_cles))
print(f"   [{'OK' if len(_emplacements) <= MAXIMUM_CANDIDATS else 'ECHEC'}]"
      f" la liste est plafonnee : sonder coute un sous-processus  ->  "
      f"{len(_emplacements)} <= {MAXIMUM_CANDIDATS}")
assert len(_emplacements) <= MAXIMUM_CANDIDATS

print("\n4 sexies bis. TOUT SOUS-PROCESSUS LANCE DEPUIS QGIS EST ASSAINI")
# LE DEFAUT : l'installeur lancait « python -m venv » puis deux « pip
# install » SANS env=environnement_propre(). Il s'execute dans QGIS, dont
# le PYTHONPATH et le PYTHONHOME pointent SA bibliotheque — qui livre deja
# huit des onze paquets. pip les tenait pour « already satisfied », ne les
# posait pas dans le venv, et sortait en succes ; la sonde, elle, lisait le
# venv REEL et les declarait tous absents. « Installation terminee » suivi
# de « onze modules absents », deux fois. Releve sur un poste neuf le
# 05/09/2026, a la premiere installation reelle du bouton.
#   LE CONTROLE PORTE SUR LE CODE, faute de pouvoir installer pour de vrai
# dans un banc — ce serait plusieurs centaines de Mo a chaque passage.
# « creationflags » AUTANT QUE « env » : sans lui, chaque appel fait
# clignoter une console noire devant la fenetre du plugin — quarante fois
# de suite quand « Installer… » cherche un python de base, et pendant
# plusieurs minutes quand pip travaille. Le drapeau lui-meme differe selon
# l'appel : SANS_FENETRE pour les appels synchrones, DETACHED_PROCESS pour
# le calage detache, et les deux sont INCOMPATIBLES. Ce qu'on exige ici est
# donc que la question ait ete posee, pas qu'une valeur precise soit la.
_source_noyau = Path(noyau.__file__).resolve().read_text(encoding="utf-8")
_arbre = ast.parse(_source_noyau)
_nus = []
for _f in ast.walk(_arbre):
    if not (isinstance(_f, ast.FunctionDef)
            and _f.name in ("installer_interpreteur", "_sonder_interpreteur",
                            "appeler_pont", "lancer_calage")):
        continue
    for _n in ast.walk(_f):
        if not isinstance(_n, ast.Call):
            continue
        _cible = getattr(_n.func, "attr", None)
        if _cible != "run" or getattr(_n.func.value, "id", "") != "subprocess":
            continue
        _cles = {k.arg for k in _n.keywords}
        for _exige in ("env", "creationflags"):
            if _exige not in _cles:
                _nus.append(f"{_f.name} l. {_n.lineno} : « {_exige}= » "
                            f"manquant")
print(f"   [{'OK' if not _nus else 'ECHEC'}] tout sous-processus lance "
      f"depuis QGIS porte « env= » ET « creationflags= »  ->  "
      f"{'aucun manque' if not _nus else _nus}")
assert not _nus, _nus

print("\n4 sexies. CE QU'ON DIT D'INSTALLER EST CE QU'ON EXIGE")
# LE DEFAUT : l'aide et le message « interpreteur introuvable » nommaient
# DEUX paquets, la verification en exige onze. Suivre l'aide a la lettre
# fabriquait un environnement refuse. Une liste ecrite deux fois finit
# toujours par diverger — il n'y en a plus qu'une, PAQUETS_HECRAS, et ce
# banc interdit qu'une seconde reapparaisse dans un texte distribue.
_commande = commande_pip_hecras()
_oublies = [pip.split(">")[0].split("=")[0]
            for _, pip in PAQUETS_HECRAS
            if pip.split(">")[0].split("=")[0] not in _commande]
print(f"   [{'OK' if not _oublies else 'ECHEC'}] la commande pip nomme "
      f"les {len(PAQUETS_HECRAS)} paquets exiges  ->  "
      f"{'aucun oubli' if not _oublies else _oublies}")
assert not _oublies, _oublies
_venv, _pip = recette_installation_manuelle()
print(f"   [{'OK' if '-m venv' in _venv and '-m pip install' in _pip else 'ECHEC'}]"
      f" la recette manuelle cree l'environnement PUIS le peuple")
assert "-m venv" in _venv and "-m pip install" in _pip

# DEUX GARDE-FOUS, PARCE QUE LA LISTE COURTE POUVAIT SE RECOMPOSER.
# Chercher le texte litteral ne suffisait pas : plugin.py l'ecrivait en
# trois morceaux de f-string, invisibles a une recherche de sous-chaine.
# On interdit donc a plugin.py de composer QUELQUE commande pip que ce
# soit — la seule source est commande_pip_hecras() — et au LISEZMOI de
# porter l'ancienne liste.
_plugin = Path(noyau.__file__).resolve().parent
_fautifs = []
_source_plugin = (_plugin / "plugin.py").read_text(encoding="utf-8") \
    if (_plugin / "plugin.py").is_file() else ""
for _marque in ("-m pip install", "ras-commander>="):
    if _marque in _source_plugin:
        _fautifs.append(f"plugin.py compose lui-meme « {_marque} »")
_lisezmoi = _plugin / "LISEZMOI.md"
if _lisezmoi.is_file() and 'install "ras-commander>=0.99" h5py' \
        in _lisezmoi.read_text(encoding="utf-8"):
    _fautifs.append("LISEZMOI.md porte la liste courte")
print(f"   [{'OK' if not _fautifs else 'ECHEC'}] aucun texte distribue "
      f"n'annonce ni ne recompose la liste courte  ->  "
      f"{'aucun' if not _fautifs else _fautifs}")
assert not _fautifs, _fautifs

print("\n5. PK POUR AFFICHAGE DANS QGIS")
affichage = pk_pour_affichage(chemins["sections"], chemins["axe"])
print("   " + affichage[["nom", "pk_m", "croise_axe"]]
      .to_string(index=False).replace("\n", "\n   "))

print("\n6. LECTEUR DE PROJET HEC-RAS  (pur texte, sans ras-commander)")
# Le projet d'essai est DECLARE, jamais code en dur : ce fichier est livre
# avec le plugin, et y inscrire le chemin d'une affaire cliente le
# diffuserait a tous ceux qui l'installent — en plus de rendre l'auto-test
# inexecutable ailleurs que sur le poste ou il a ete ecrit.
#     set CALAGE_PROJET_ESSAI=<dossier d'un projet HEC-RAS>
declare = os.environ.get("CALAGE_PROJET_ESSAI")
projet_reel = Path(declare) if declare else None
if projet_reel is not None and projet_reel.is_dir():
    info = lister_projet_hecras(projet_reel)
    print(f"   projet : {info['nom_projet']}")
    print(f"   {len(info['geometries'])} geometrie(s), "
          f"{len(info['unsteady'])} unsteady, {len(info['plans'])} plan(s)")
    if info["plans"]:
        premier = info["plans"][0]
        print(f"   premier plan : p{premier['numero']} — "
              f"{premier['titre']}  (g{premier['geometrie']}, "
              f"u{premier['unsteady']})")
        print(f"   fenetre : {premier['fenetre']['debut']} -> "
              f"{premier['fenetre']['fin']}")
else:
    print("   (aucun projet declare dans CALAGE_PROJET_ESSAI — non "
          "bloquant : le lecteur est exerce par test_plugin_qgis.py)")

print("\n7. PONT VERS HEC-RAS")
interpreteur = interpreteur_hecras()
print(f"   interpreteur : {interpreteur}")
if interpreteur is None:
    print(f"   introuvable — bouton « Installer… » du plugin "
          f"({len(pythons_candidats())} base(s) possible(s) sur ce "
          f"poste), ou « Designer… », ou {VARIABLE_INTERPRETEUR}")
else:
    try:
        reponse = appeler_pont("verifier", delai=120)
        print(f"   python {reponse['python']}, "
              f"ras-commander {reponse['ras_commander']}, "
              f"h5py {reponse['h5py']}")
    except Exception as e:
        print(f"   ECHEC : {e}")

print("\n8. ARBITRAGE ENTRE PLUSIEURS CHAINES  (le rang, plus jamais la date)")
bac = Path(tempfile.mkdtemp(prefix="calage_chaines_"))

def temoin(nom, quand):
    dossier_temoin = bac / nom
    dossier_temoin.mkdir()
    for fichier in FICHIERS_CHAINE:
        (dossier_temoin / fichier).write_text("", encoding="utf-8")
        os.utime(dossier_temoin / fichier, (quand, quand))
    return dossier_temoin

# TEMOINS VOLONTAIREMENT ANCIENS. C'est tout l'objet de cet essai : sous
# l'ancienne regle « la plus recente gagne », ils perdaient a coup sur
# contre les vraies chaines du poste. Ils doivent maintenant l'emporter
# par leur RANG. Rendre la regle de nouveau dependante des dates fait
# echouer ce bloc.
embarquee = temoin("embarquee_ancienne", time.time() - 86400)
designee = temoin("designee_plus_ancienne_encore", time.time() - 172800)

embarque_reel = noyau.DOSSIER_EMBARQUE
choix_reel = noyau._dossier_chaine
dossier_projet = Path(noyau.__file__).resolve().parent.parent / "src"
try:
    noyau.DOSSIER_EMBARQUE = embarquee
    if est_chaine(dossier_projet):
        retenue = trouver_chaine()
        assert retenue == embarquee, (
            f"la copie embarquee doit primer sur src/ du parent du "
            f"plugin meme en etant plus ancienne — retenue : {retenue}")
        print(f"   embarquee ({embarquee.name}, veille) l'emporte sur "
              f"src/ du parent du plugin, pourtant plus recent")
    else:
        print("   src/ du parent du plugin non-chaine ici : rang non "
              "departageable")

    assert definir_chaine(designee), "le temoin doit etre accepte"
    assert trouver_chaine() == designee, "le choix explicite doit primer"
    print(f"   choix explicite de « {designee.name} » -> respecte, bien "
          f"qu'il soit le plus ancien des trois")
finally:
    noyau.DOSSIER_EMBARQUE = embarque_reel
    noyau._dossier_chaine = choix_reel
    sys.path[:] = [p for p in sys.path if not p.startswith(str(bac))]
    shutil.rmtree(bac, ignore_errors=True)
    _raccorder()

assert fraicheur(bac / "disparu") == 0.0, "un dossier absent vaut 0.0"
assert fraicheur(None) == 0.0, "une valeur nulle vaut 0.0"
print("   dossier absent ou nul -> fraicheur 0.0, jamais d'exception")
print(f"   chaine retenue apres essais : {trouver_chaine()}")

print("\n" + "=" * 72)
print("\n9. UN MANQUE QUI N'EST PAS DANS NOTRE LISTE  (xarray)")
# Production, 02/09/2026 : calage conforme apres 14 h, puis « profil en
# long de synthese : non calculable (ModuleNotFoundError: No module named
# 'xarray') ». xarray n'est a nous NI par l'import NI par la liste : c'est
# ras-commander qui l'exige pour HdfResultsMesh. find_spec sur les dix
# noms de PAQUETS_HECRAS ne pouvait pas le voir ; et sur une ras-commander
# qui charge .hdf paresseusement, « import ras_commander » ne le voyait
# pas non plus. L'interpreteur etait ACCEPTE.
# AUCUN TELECHARGEMENT : « venv --without-pip » et des modules factices.
bac_x = Path(tempfile.mkdtemp(prefix="calage_xarray_"))

def interpreteur_sans_xarray(nom, paresseux):
    """
    Faux interpreteur : les modules de PAQUETS_HECRAS sont la, une
    ras_commander factice exige xarray pour HdfResultsMesh, et xarray est
    ABSENT. « paresseux » reproduit une ras-commander qui ne charge .hdf
    qu'a la demande — la seule forme ou le calage va jusqu'au bout avant
    de buter sur la figure.
    """
    cible = bac_x / nom
    subprocess.run([sys.executable, "-m", "venv", "--without-pip",
                    str(cible)], check=True, capture_output=True)
    paquets = site_packages(cible)
    for module in (i for i, _ in PAQUETS_HECRAS if i != "ras_commander"):
        (paquets / f"{module}.py").write_text("__version__ = '0.0'\n",
                                              encoding="utf-8")
    rc = paquets / "ras_commander"
    (rc / "hdf").mkdir(parents=True)
    (rc / "hdf" / "__init__.py").write_text(
        "from .HdfResultsMesh import HdfResultsMesh\n", encoding="utf-8")
    # La classe et son corps sont deux litteraux, SEPARES : le nom de
    # classe suivi d'un saut de ligne echappe, ecrit d'un trait,
    # ressemble a un chemin pour le garde-fou d'attache. Aucune
    # lettre suivie de deux-points et d'une barre oblique inverse ici.
    (rc / "hdf" / "HdfResultsMesh.py").write_text(
        "import xarray as xr\n\n\nclass HdfResultsMesh:"
        "\n    pass\n",
        encoding="utf-8")
    (rc / "__init__.py").write_text(
        ("__version__ = '0.99.0'\n"
         "_TARDIFS = {'HdfResultsMesh'}\n"
         "def __getattr__(n):\n"
         "    if n in _TARDIFS:\n"
         "        from .hdf import HdfResultsMesh\n"
         "        return HdfResultsMesh\n"
         "    raise AttributeError(n)\n")
        if paresseux else
        ("__version__ = '0.99.1'\n"
         "from .hdf import HdfResultsMesh\n"), encoding="utf-8")
    # MEME REPLI QUE creer_venv_hecras : « Scripts\python.exe » sous
    # Windows, « bin/python » ailleurs. Sans lui, le refus tombait sur un
    # interpreteur INEXISTANT au lieu de tomber sur xarray, et le banc ne
    # prouvait plus ce qu'il annonce.
    interpreteur = cible / "Scripts" / "python.exe"
    if not interpreteur.is_file():
        interpreteur = cible / "bin" / "python"
    return interpreteur

try:
    for nom_cas, tardif in (("chargement paresseux de .hdf", True),
                            ("chargement immediat de .hdf", False)):
        faux = interpreteur_sans_xarray(
            "paresseux" if tardif else "immediat", tardif)
        ok_x, msg_x = verifier_interpreteur(faux)
        assert not ok_x, (
            f"un interpreteur sans xarray doit etre REFUSE "
            f"({nom_cas}) — rendu : {msg_x}")
        # LE REFUS NE SUFFIT PAS : il doit NOMMER le module et donner la
        # commande. Un « ModuleNotFoundError » brut n'apprend a personne
        # quoi installer.
        assert "xarray" in msg_x and "pip install" in msg_x, (
            f"le refus doit nommer xarray et la commande pip "
            f"({nom_cas}) — rendu : {msg_x}")
        print(f"   {nom_cas} -> refuse, et la commande pip est donnee")
finally:
    shutil.rmtree(bac_x, ignore_errors=True)

print("\n10. L'INSTALLEUR COMPLETE CE QUE LA SONDE NOMME  (poste neuf, 03/09/2026)")
# Environnement REUTILISE, ras-commander deja present sans xarray : pip
# « --upgrade » ne le repare pas, et l'installeur repondait « inutilisable
# : xarray absent... ou laisser le bouton Installer... » — le bouton qui
# venait de tourner. AUCUN TELECHARGEMENT : pip est doublé, la sonde est
# reelle.
bac_i = Path(tempfile.mkdtemp(prefix="calage_installeur_"))
_vrai_run = subprocess.run
_vrai_emplacement = emplacement_venv_hecras
pips = []

def _run_double(commande, *a, **k):
    # La sonde (« -c ») tourne pour de vrai : c'est elle qu'on eprouve.
    # pip est enregistre et repond 0 sans rien poser : c'est ce que fait
    # un pip qui tient la contrainte pour satisfaite.
    if "-c" in commande:
        return _vrai_run(commande, *a, **k)
    pips.append(list(commande))
    return subprocess.CompletedProcess(commande, 0, stdout="", stderr="")

try:
    faux_venv = bac_i / "venv-hecras"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip",
                    str(faux_venv)], check=True, capture_output=True)
    paquets = site_packages(faux_venv)
    for module in (i for i, _ in PAQUETS_HECRAS if i != "ras_commander"):
        (paquets / f"{module}.py").write_text("__version__ = '0.0'\n",
                                              encoding="utf-8")
    rc = paquets / "ras_commander"
    (rc / "hdf").mkdir(parents=True)
    (rc / "hdf" / "__init__.py").write_text(
        "from .HdfResultsMesh import HdfResultsMesh\n", encoding="utf-8")
    (rc / "hdf" / "HdfResultsMesh.py").write_text(
        "import xarray as xr\n\n\nclass HdfResultsMesh:"
        "\n    pass\n", encoding="utf-8")
    (rc / "__init__.py").write_text(
        "__version__ = '0.99.2'\nfrom .hdf import HdfResultsMesh\n",
        encoding="utf-8")

    noyau.emplacement_venv_hecras = lambda: faux_venv
    subprocess.run = _run_double
    chemin_i, message_i = installer_interpreteur(sys.executable)
finally:
    subprocess.run = _vrai_run
    noyau.emplacement_venv_hecras = _vrai_emplacement
    shutil.rmtree(bac_i, ignore_errors=True)

assert len(pips) == 2, (
    f"l'installeur doit lancer pip DEUX fois — le lot, puis le complement "
    f"que la sonde nomme — il l'a lance {len(pips)} fois : {pips}")
assert pips[1][-1] == "xarray" and "--upgrade" not in pips[1], (
    f"le complement doit poser exactement ce que la sonde nomme : {pips[1]}")
# pip etant double, xarray manque toujours : l'installeur DOIT echouer,
# et son message ne doit plus conseiller le bouton qui vient d'echouer.
assert chemin_i is None and "xarray" in message_i, message_i
assert "Installer" not in message_i, (
    f"le message renvoie encore au bouton « Installer… » : {message_i}")
print("   complement pose : pip install xarray, apres le lot")
print("   message d'echec : nomme xarray et la commande, sans renvoyer au bouton")

print("\n11. LE SUIVI SE LIT DANS LE CLASSEUR  (03/09/2026)")
# Un calage lance sur le classeur d'un calcul precedent ecrivait son suivi
# la ou CE classeur le dit ; la fenetre regardait les champs de l'onglet 3,
# qui designaient le dossier du DERNIER paquet compose. Le suivi restait
# muet devant un calage qui tournait. La regle est celle du pont.
import pandas as pd
bac_s = Path(tempfile.mkdtemp(prefix="calage_suivi_"))
try:
    ailleurs = bac_s / "sortie_du_classeur"
    classeur_s = bac_s / "compose_ici" / "donnees_calage.xlsx"
    classeur_s.parent.mkdir()
    import parametres as _parametres
    _parametres.ecrire(classeur_s, {"Nom_projet": "Essai",
                                    "Dossier_sortie": str(ailleurs),
                                    "Sous_dossier_suivi": "suivi_q100"})
    trouve = dossier_suivi_du_classeur(classeur_s)
    assert trouve == ailleurs / "suivi_q100", (
        f"le suivi doit suivre Dossier_sortie et Sous_dossier_suivi du "
        f"classeur — rendu : {trouve}")
    print(f"   classeur compose dans {classeur_s.parent.name}, "
          f"suivi dans {trouve.parent.name}/{trouve.name} : c'est le classeur qui a parle")

    # Sans ces deux cles — classeur d'une version anterieure —, la regle
    # du pont vaut aussi : le dossier du classeur, sous-dossier « suivi ».
    _parametres.ecrire(classeur_s, {"Nom_projet": "Essai"})
    trouve = dossier_suivi_du_classeur(classeur_s)
    assert trouve == classeur_s.parent / "suivi", trouve
    print("   sans Dossier_sortie : le dossier du classeur, sous-dossier « suivi »")
finally:
    shutil.rmtree(bac_s, ignore_errors=True)

# -----------------------------------------------------------------
print("\n12. CE QUE PORTENT LES CIBLES, ET SI HEC-RAS EST OUVERT")
import numpy as _np
import pandas as _pd

bac_r = Path(tempfile.mkdtemp(prefix="calage_resume_"))
try:
    _classeur_r = bac_r / "donnees.xlsx"
    # Un triangle de 0 a 10 h, pic 100 m3/s a 5 h : son volume vaut
    # 0.5 * base * hauteur = 0.5 * 10 h * 100 m3/s = 500 m3/s.h,
    # soit 500 * 3600 / 1e6 = 1.8 hm3. Un nombre qu'on peut poser a la
    # main, et c'est tout l'interet : la regle des trapezes est EXACTE
    # sur un triangle, l'ecart ne peut donc venir que du code.
    _t_r = _np.arange(0.0, 10.01, 0.5)
    _q_r = _np.where(_t_r <= 5.0, 100.0 * _t_r / 5.0,
                     100.0 * (10.0 - _t_r) / 5.0)
    with _pd.ExcelWriter(_classeur_r) as _ec:
        _pd.DataFrame({"Nom_Apport": ["A1", "A2"],
                       "Nom_Section": ["S1", "S2"],
                       "Nom_Cible": ["Cible_S1", "Cible_S2"]}
                      ).to_excel(_ec, sheet_name="Correspondance",
                                 index=False)
        # La seconde cible reste VIDE : c'est l'etat ordinaire d'un
        # classeur qu'on vient de composer.
        _pd.DataFrame({"Temps_h": _t_r, "Cible_S1": _q_r,
                       "Cible_S2": [None] * len(_t_r)}
                      ).to_excel(_ec, sheet_name="Cibles", index=False)

    _res = resume_cibles(_classeur_r)
    assert len(_res) == 2, _res
    assert _res[0]["renseignee"] and not _res[1]["renseignee"], _res
    assert abs(_res[0]["pic_m3s"] - 100.0) < 1e-9, _res[0]
    assert abs(_res[0]["heure_pic_h"] - 5.0) < 1e-9, _res[0]
    assert abs(_res[0]["volume_hm3"] - 1.8) < 1e-9, _res[0]["volume_hm3"]
    # UNE CIBLE VIDE N'EST PAS UN ZERO : rendre 0,0 hm3 la ferait passer
    # pour saisie et nulle, ce qui est un resultat, pas une absence.
    assert _res[1]["pic_m3s"] is None and _res[1]["volume_hm3"] is None
    print(f"   triangle 0-10 h, pic 100 m3/s a 5 h : "
          f"{_res[0]['volume_hm3']:.3f} hm3 (attendu 1,800), "
          f"la cible vide est dite « a saisir »")

    # LES COUPLES INCOMPLETS SORTENT DES DEUX SERIES ENSEMBLE. Integrer
    # des debits sur une base de temps trouee rendrait un nombre qui ne
    # veut rien dire — ici, la ligne a 5 h perd son instant, et le pic
    # avec.
    _t_troue = _t_r.astype(object).copy()
    _t_troue[10] = "n/c"                      # l'instant 5,0 h
    with _pd.ExcelWriter(_classeur_r) as _ec:
        _pd.DataFrame({"Nom_Apport": ["A1"], "Nom_Section": ["S1"],
                       "Nom_Cible": ["Cible_S1"]}
                      ).to_excel(_ec, sheet_name="Correspondance",
                                 index=False)
        _pd.DataFrame({"Temps_h": _t_troue, "Cible_S1": _q_r}
                      ).to_excel(_ec, sheet_name="Cibles", index=False)
    _res2 = resume_cibles(_classeur_r)
    assert _res2[0]["renseignee"], _res2
    assert abs(_res2[0]["pic_m3s"] - 90.0) < 1e-9, _res2[0]["pic_m3s"]
    print(f"   un instant illisible retire son debit : pic "
          f"{_res2[0]['pic_m3s']:.0f} m3/s au lieu de 100")

    # SANS COLONNE DE TEMPS, ON REFUSE — meme regle que etat_cibles, et
    # c'est la faute reelle du 04/09/2026.
    with _pd.ExcelWriter(_classeur_r) as _ec:
        _pd.DataFrame({"Nom_Apport": ["A1"], "Nom_Section": ["S1"],
                       "Nom_Cible": ["Cible_S1"]}
                      ).to_excel(_ec, sheet_name="Correspondance",
                                 index=False)
        _pd.DataFrame({"Heure": _t_r, "Cible_S1": _q_r}
                      ).to_excel(_ec, sheet_name="Cibles", index=False)
    try:
        resume_cibles(_classeur_r)
        raise AssertionError("une feuille Cibles sans Temps_h doit etre "
                             "refusee")
    except ValueError as _e:
        assert "Temps_h" in str(_e), _e
        print("   feuille Cibles sans « Temps_h » : refusee, et l'en-tete "
              "trouve est nomme")
finally:
    shutil.rmtree(bac_r, ignore_errors=True)

# HEC-RAS OUVERT : trois reponses possibles, et « je ne sais pas » en est
# une. Le plugin ne pose sa question que sur True (voir _lancer_calage) :
# demander « peut-etre ? » a chaque lancement apprendrait a repondre oui
# sans lire.
_ouvert = hecras_ouvert()
assert _ouvert in (True, False, None), _ouvert
print(f"   hecras_ouvert() rend {_ouvert!r} — jumeau de "
      f"pilote_hecras.hecras_ouvert, que le Python de QGIS ne peut pas "
      f"importer")

print("\nNoyau operationnel. Le plugin ne fait qu'appeler ces fonctions.")
print("=" * 72)
