"""Banc d'auto-test de src/geometrie.py.

Ce banc etait le bloc `if __name__ == "__main__":` du module ; il en a ete
sorti le 10/11/2026 pour ne plus partir avec le code dans l'archive du plugin.
Il se lance seul (python3 src/bancs/banc_geometrie.py) ou par le relais
que garde src/geometrie.py (python3 src/geometrie.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from geometrie import (calculer_pk, controler_profil, controler_shp,
                       echantillonner_axe, ecrire_dans_geometrie, lire_axe,
                       lire_lignes, noms_objets_geometrie,
                       objets_depuis_texte, pente_locale,
                       perimetres_depuis_texte, profil_depuis_modele,
                       supprimer_lignes_reference, verifier_ordre,
                       verifier_position_apports)

import tempfile

import geopandas as gpd
from shapely.geometry import LineString

print("=" * 72)
print("AUTO-TEST DE LA COUCHE GEOMETRIQUE")
print("=" * 72)

dossier = Path(tempfile.gettempdir()) / "calage_geom_test"
dossier.mkdir(exist_ok=True)
CRS = "EPSG:2154"

# Axe sinueux de l'amont (x=0) vers l'aval (x=8000), en Lambert-93.
xs = np.linspace(0, 8000, 60)
ys = 300 * np.sin(xs / 1400)
axe_geom = LineString(zip(500000 + xs, 6200000 + ys))
gpd.GeoDataFrame({"Nom": ["Axe"]}, geometry=[axe_geom], crs=CRS).to_file(
    dossier / "axe.shp")

def transversale(x_local, demi=400.0, decal=0.0):
    y = 300 * np.sin(x_local / 1400) + decal
    return LineString([(500000 + x_local, 6200000 + y - demi),
                       (500000 + x_local, 6200000 + y + demi)])

sections = ["S1_Amont", "S2_Pont", "S3_Confluence", "S4_Aval"]
x_sections = [900, 2800, 5100, 7400]
gpd.GeoDataFrame(
    {"Nom": sections},
    geometry=[transversale(x) for x in x_sections],
    crs=CRS).to_file(dossier / "sections.shp")

apports = ["A1_Amont", "A2_Affluent", "A3_Ruisseau", "A4_Lateral"]
x_apports = [200, 2100, 4300, 6600]
gpd.GeoDataFrame(
    {"Nom": apports},
    geometry=[transversale(x, demi=250) for x in x_apports],
    crs=CRS).to_file(dossier / "apports.shp")

print(f"\nShapefiles de test ecrits dans : {dossier}")

# --- 1. Lecture -------------------------------------------------------
print("\n1. LECTURE ET NORMALISATION")
axe, crs_axe = lire_axe(dossier / "axe.shp")
g_sec = lire_lignes(dossier / "sections.shp")
g_app = lire_lignes(dossier / "apports.shp")
print(f"   axe      : {axe.length:8.0f} m, {crs_axe.to_string()}")
print(f"   sections : {len(g_sec)} -> {list(g_sec['nom'])}")
print(f"   apports  : {len(g_app)} -> {list(g_app['nom'])}")

# --- 2. Controles -----------------------------------------------------
print("\n2. CONTROLES SIG")
anomalies = (controler_shp(g_sec, "sections", crs_axe,
                           exiger_croisement=True, axe=axe)
             + controler_shp(g_app, "apports", crs_axe))
print("   aucune anomalie" if not anomalies
      else "\n".join(f"   [{n}] {m}" for n, m in anomalies))

# --- 3. PK ------------------------------------------------------------
print("\n3. CALCUL DES PK PAR PROJECTION CURVILIGNE")
g_sec = calculer_pk(g_sec, axe)
g_app = calculer_pk(g_app, axe)
print(g_sec[["nom", "pk_m", "croise_axe"]].to_string(index=False))
print()
print(g_app[["nom", "pk_m", "croise_axe"]].to_string(index=False))

pk_sec = dict(zip(g_sec["nom"], g_sec["pk_m"]))
pk_app = dict(zip(g_app["nom"], g_app["pk_m"]))

# --- 4. Coherence de l'ordre -----------------------------------------
print("\n4. VERIFICATION DE L'ORDRE DECLARE")
print("   ordre correct           :", verifier_ordre(sections, pk_sec) or "OK")
faux = ["S1_Amont", "S3_Confluence", "S2_Pont", "S4_Aval"]
for n, m in verifier_ordre(faux, pk_sec):
    print(f"   ordre S1,S3,S2,S4      : [{n}] {m}")
inverse = list(reversed(sections))
for n, m in verifier_ordre(inverse, pk_sec):
    print(f"   axe inverse            : [{n}] {m}")

# --- 5. Position des apports -----------------------------------------
print("\n5. POSITION DES APPORTS PAR RAPPORT AUX SECTIONS")
couples = list(zip(apports, sections))
print("   correspondance correcte :",
      verifier_position_apports(couples, pk_app, pk_sec) or "OK")
mauvais = [("A2_Affluent", "S1_Amont")] + couples[2:]
for n, m in verifier_position_apports(mauvais, pk_app, pk_sec):
    print(f"   apport en aval          : [{n}] {m}")

# --- 6. Echantillonnage de l'axe --------------------------------------
print("\n6. ECHANTILLONNAGE DE L'AXE POUR LE PROFIL EN LONG")
pk, x, y = echantillonner_axe(axe, pas=25.0)
print(f"   {len(pk)} points, pas de 25 m, de PK {pk[0]:.0f} a {pk[-1]:.0f} m")
print("   L'altimetrie provient du MAILLAGE du modele (cote de fond de la")
print("   maille la plus proche), donc du terrain effectivement calcule.")
print("   Indisponible ici : l'auto-test tourne sans modele hydraulique.")

# --- 7. Controles de vraisemblance du profil --------------------------
print("\n7. CONTROLES DE VRAISEMBLANCE DU PROFIL")
pk_essai = np.arange(0, 2000, 25.0)
z_fond = 100 - 0.002 * pk_essai

correct = pd.DataFrame({
    "pk_m": pk_essai, "z_fond": z_fond, "z_eau_max": z_fond + 2.0,
    "h_max": np.full_like(pk_essai, 2.0),
    "hors_maillage": np.zeros(len(pk_essai), dtype=bool),
})
print("   profil correct          :", controler_profil(correct) or "OK")

hors = correct.copy()
hors.loc[hors.index[:30], "hors_maillage"] = True
for n, m in controler_profil(hors):
    print(f"   axe sortant du maillage : [{n}] {m}")

dessous = correct.copy()
dessous.loc[dessous.index[:5], "h_max"] = -0.5
for n, m in controler_profil(dessous):
    print(f"   eau sous le fond        : [{n}] {m}")

envers = correct.copy()
envers["z_fond"] = envers["z_fond"].to_numpy()[::-1]
for n, m in controler_profil(envers):
    print(f"   axe a l'envers          : [{n}] {m}")

# --- 8. Pente locale d'un apport --------------------------------------
print("\n8. PENTE LOCALE, POUR LA « FLOW HYDROGRAPH SLOPE »")
_echecs_pente = []

def _ctrl(libelle, condition, detail=""):
    print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
          + (f"  ->  {detail}" if detail else ""))
    if not condition:
        _echecs_pente.append(libelle)

# Profil a 0,2 % : la pente rendue doit valoir 0,2 % majore de 20 %.
_p = pente_locale(correct, 1000.0)
_ctrl("la pente locale est celle du fond, majoree de 20 %",
      _p is not None and abs(_p - 0.002 * 1.20) < 1e-6,
      f"{_p:.5f} attendu {0.002 * 1.20:.5f}")
_ctrl("elle ne depend pas du sens du profil",
      abs(pente_locale(envers, 1000.0) - _p) < 1e-6)

# Pente variable : la valeur doit suivre l'endroit ou on la demande.
_var = correct.copy()
_var["z_fond"] = 100 - np.where(pk_essai < 1000, 0.001, 0.006) * pk_essai
_ctrl("elle est bien LOCALE",
      pente_locale(_var, 300.0) < pente_locale(_var, 1700.0),
      f"amont {pente_locale(_var, 300.0):.5f} / "
      f"aval {pente_locale(_var, 1700.0):.5f}")

_ctrl("un PK hors du profil ne rend pas de valeur",
      pente_locale(correct, 50000.0) is None)
_ctrl("un fond parfaitement plat ne rend pas de valeur",
      pente_locale(
          pd.DataFrame({"pk_m": pk_essai,
                        "z_fond": np.full_like(pk_essai, 100.0)}),
          1000.0) is None)
_ctrl("un profil absent ne leve pas d'erreur",
      pente_locale(None, 1000.0) is None)

# Axe qui deborde de 200 m de chaque cote d'une zone 2D carree de 1 km :
# a moins de 250 m des mailles du bord, la distance seule gardait ces
# points et prolongeait le profil hors du modele.
import h5py
_hdf_contour = dossier / "contour_test.p01.hdf"
_cx, _cy = np.meshgrid(np.arange(25.0, 1000.0, 50.0),
                       np.arange(25.0, 1000.0, 50.0))
with h5py.File(_hdf_contour, "w") as _h:
    _z = _h.create_group("Geometry/2D Flow Areas/Zone")
    _z["Cells Center Coordinate"] = np.column_stack([_cx.ravel(),
                                                     _cy.ravel()])
    _z["Cells Minimum Elevation"] = 100.0 - _cx.ravel() / 1000.0
    _z["Perimeter"] = np.array([[0.0, 0.0], [0.0, 1000.0],
                                [1000.0, 1000.0], [1000.0, 0.0]])
_pc = profil_depuis_modele(_hdf_contour, LineString([(-200, 500),
                                                     (1200, 500)]),
                           avec_ligne_eau=False)
_dans = _pc.dropna(subset=["z_fond"])["pk_m"]
_ctrl("le profil s'arrete au contour de la zone 2D",
      _dans.min() >= 200.0 and _dans.max() <= 1200.0
      and _pc["hors_maillage"].sum() == 18,
      f"PK {_dans.min():.0f} a {_dans.max():.0f} m, "
      f"{int(_pc['hors_maillage'].sum())} points hors")

# --- 9. Lecture depuis un fichier geometrie texte (avant pretraitement)
print("\n9. LECTURE DEPUIS LE FICHIER GEOMETRIE TEXTE (avant pretraitement)")
print("   Fabrique un .gXX minimal, meme format en champs fixes de 16")
print("   caracteres qu'un fichier HEC-RAS reel : c'est la seule route")
print("   disponible pour une geometrie qui n'a jamais ete calculee.")

def _champ16(v):
    return f"{v:16.6f}"

def _ligne_point(p):
    return "".join(_champ16(c) for c in p)

perimetre_brut = [(1000.0, 5000.0), (1000.0, 5100.0),
                  (1100.0, 5100.0), (1100.0, 5000.0)]
section_brute = [(1020.0, 5000.0), (1020.0, 5100.0)]
apport_brut = [(1080.0, 5000.0), (1080.0, 5100.0)]

geom_texte = "\n".join([
    "Geom Title=Test_Auto",
    "Program Version=6.6",
    "",
    "Storage Area=Zone Test     ,,",
    f"Storage Area Surface Line= {len(perimetre_brut)} ",
    # Troisieme champ de 16 espaces, comme l'ecrit HEC-RAS.
    *[_ligne_point(p) + " " * 16 for p in perimetre_brut],
    "Storage Area Type= 1 ",
    "Storage Area Is2D=-1",
    "",
    "Reference Line Name=Section_Test",
    "Reference Line Storage Area=Zone Test     ",
    f"Reference Line Arc= {len(section_brute)} ",
    *[_ligne_point(p) for p in section_brute],
    "",
    "Reference Line Name=Section_Autre",
    "Reference Line Storage Area=Zone Test     ",
    f"Reference Line Arc= {len(section_brute)} ",
    *[_ligne_point(p) for p in section_brute],
    "",
    "BC Line Name=Apport_Test",
    "BC Line Storage Area=Zone Test     ",
    f"BC Line Arc= {len(apport_brut)} ",
    *[_ligne_point(p) for p in apport_brut],
    "",
])
fichier_geom_texte = dossier / "geometrie_test.g01"
fichier_geom_texte.write_text(geom_texte, encoding="utf-8")

objets = objets_depuis_texte(fichier_geom_texte)
_ctrl("les deux sections sont lues depuis le texte",
      sorted(o["nom"] for o in objets["sections"])
      == ["Section_Autre", "Section_Test"])
_ctrl("l'injection est lue depuis le texte",
      [o["nom"] for o in objets["apports"]] == ["Apport_Test"])

perimetres = perimetres_depuis_texte(fichier_geom_texte)
_ctrl("un seul perimetre de zone 2D trouve", len(perimetres) == 1,
      f"{len(perimetres)} trouve(s)")
if perimetres:
    _ctrl("le nom de la zone est lu, espaces de bourrage retires",
          perimetres[0]["zone"] == "Zone Test",
          repr(perimetres[0]["zone"]))
    _ctrl("le contour ouvert est referme automatiquement",
          perimetres[0]["wkt"].count(",") == len(perimetre_brut),
          perimetres[0]["wkt"])

# --- 10. Retrait d'un bloc « Reference Line », prealable au remplacement
print("\n10. RETRAIT D'UN BLOC « REFERENCE LINE » (prealable au remplacement)")
retirees = supprimer_lignes_reference(
    fichier_geom_texte, ["Section_Test", "Section_Inexistante"])
_ctrl("seul le nom present est rapporte comme retire",
      retirees == ["Section_Test"], retirees)

apres = objets_depuis_texte(fichier_geom_texte)
_ctrl("la section visee a disparu, l'autre reste",
      [o["nom"] for o in apres["sections"]] == ["Section_Autre"],
      [o["nom"] for o in apres["sections"]])
_ctrl("l'injection n'est pas affectee",
      [o["nom"] for o in apres["apports"]] == ["Apport_Test"])
_ctrl("le perimetre de la zone 2D n'est pas affecte",
      len(perimetres_depuis_texte(fichier_geom_texte)) == 1)
_ctrl("aucun nom a retirer ne touche pas au fichier",
      supprimer_lignes_reference(fichier_geom_texte, []) == [])

# REGRESSION DU 03/08/2026 — la DERNIERE reference line du fichier.
# Aucune ligne « ... Line Name= » ne la suit : l'ancienne delimitation
# courait jusqu'a la fin du fichier et emportait les blocs qui la
# suivent. Reproduit ici la queue exacte d'une geometrie reelle.
queue = "\n".join([
    "Geom Title=Test_Queue",
    "",
    "Reference Line Name=SC1",
    "Reference Line Storage Area=2D Area 1       ",
    f"Reference Line Arc= {len(section_brute)} ",
    *[_ligne_point(p) for p in section_brute],
    "Reference Line Text Position= 407004.33825 , 6210543.7065 ",
    "LCMann Time=Dec/30/1899 00:00:00",
    "LCMann Region Time=Dec/30/1899 00:00:00",
    "LCMann Region Name=Prairies",
    "LCMann Region Table=0",
    "LCMann Table=0",
    "Chan Stop Cuts=-1 ",
    "",
    "Use User Specified Reach Order=0",
    "GIS Ratio Cuts To Invert=-1",
    "GIS Limit At Bridges=0",
    "Composite Channel Slope=5",
    "",
])
fichier_queue = dossier / "geometrie_queue.g01"
fichier_queue.write_text(queue, encoding="utf-8")
_avant_queue = fichier_queue.read_text(encoding="utf-8")

_retire_queue = supprimer_lignes_reference(fichier_queue, ["SC1"])
_apres_queue = fichier_queue.read_text(encoding="utf-8")
_ctrl("la derniere reference line du fichier est bien retiree",
      _retire_queue == ["SC1"], _retire_queue)
_ctrl("son trace part avec elle",
      "Reference Line Arc=" not in _apres_queue)
for _bloc in ("LCMann Region Name=Prairies", "LCMann Table=0",
              "Chan Stop Cuts=", "Use User Specified Reach Order=",
              "GIS Ratio Cuts To Invert=", "GIS Limit At Bridges=",
              "Composite Channel Slope="):
    _ctrl(f"le bloc voisin « {_bloc.rstrip('=0123456789 ')} » survit",
          _bloc in _apres_queue)
# Rien d'autre que le bloc vise ne doit bouger : le nombre de lignes
# perdues se compte, il ne s'estime pas.
_perdues = (len(_avant_queue.splitlines())
            - len(_apres_queue.splitlines()))
_ctrl("seules les lignes du bloc vise disparaissent",
      _perdues == 4 + len(section_brute), f"{_perdues} ligne(s) perdue(s)")

# ENCODAGE (audit du 11/10/2026). HEC-RAS ecrit en cp1252 et en CRLF. La
# geometrie D'ORIGINE se relisait en UTF-8 errors="replace" puis se
# reecrivait en UTF-8 : au premier remplacement de section, chaque accent
# du fichier devenait U+FFFD. Tout ce qui n'est pas le bloc retire doit
# revenir A L'OCTET PRES — le tiret (0x96) n'existe qu'en cp1252, et la
# derniere ligne est en LF : chaque ligne garde SA fin.
_tete = b"Geom Title=G\xe9om\xe9trie \xe9tat am\xe9nag\xe9 \x96 digue\r\n"
_bloc_sc1 = ("Reference Line Name=SC1\r\n"
             "Reference Line Storage Area=2D Area 1       \r\n"
             f"Reference Line Arc= {len(section_brute)} \r\n"
             + "".join(_ligne_point(p) + "\r\n" for p in section_brute)
             ).encode("cp1252")
_bloc_ecluse = _bloc_sc1.replace(b"SC1", "Écluse".encode("cp1252"))
_queue = b"LCMann Region Name=For\xeat\r\nChan Stop Cuts=-1 \n"
fichier_accents = dossier / "geometrie_accents.g01"
fichier_accents.write_bytes(_tete + _bloc_sc1 + _bloc_ecluse + _queue)

_ctrl("un nom de section accentue en cp1252 est lu juste",
      noms_objets_geometrie(fichier_accents)["sections"]
      == ["SC1", "Écluse"]
      and [o["nom"] for o in objets_depuis_texte(fichier_accents)["sections"]]
      == ["SC1", "Écluse"],
      noms_objets_geometrie(fichier_accents)["sections"])
_ctrl("retirer une section rend le reste de la geometrie a l'octet pres",
      supprimer_lignes_reference(fichier_accents, ["SC1"]) == ["SC1"]
      and fichier_accents.read_bytes() == _tete + _bloc_ecluse + _queue,
      repr(fichier_accents.read_bytes()[:48]))
_ctrl("une section au nom accentue se retire aussi",
      supprimer_lignes_reference(fichier_accents, ["Écluse"]) == ["Écluse"]
      and fichier_accents.read_bytes() == _tete + _queue,
      repr(fichier_accents.read_bytes()[-48:]))

# ET A TRAVERS ras-commander, qui ECRIT le trace. Retirer le bloc ne
# suffisait pas : add_reference_lines et add_bc_lines (0.99.2) relisent
# en UTF-8 errors="ignore" et reecrivent en UTF-8 — mesure le 11/10/2026,
# « Géométrie état aménagé – digue » ressortait « Gomtrie tat amnag  digue ».
try:
    import ras_commander  # noqa: F401
except ImportError:
    print("   ignore : ras-commander absent, son ecriture n'est pas eprouvee")
else:
    _corps_rc = "\r\n".join([
        "Storage Area=Zone Test     ,,",
        f"Storage Area Surface Line= {len(perimetre_brut)} ",
        *[_ligne_point(p) for p in perimetre_brut],
        "Storage Area Type= 1 ", "Storage Area Is2D=-1", "",
        "LCMann Region Name=Forêt", "Chan Stop Cuts=-1 ", ""]
    ).encode("cp1252")
    fichier_rc = dossier / "geometrie_ras_commander.g01"
    for _genre in ("sections", "apports"):
        fichier_rc.write_bytes(_tete + _corps_rc)
        _gdf = gpd.GeoDataFrame({"nom": ["Écluse"]}, crs=CRS,
                                geometry=[LineString(section_brute)])
        ecrire_dans_geometrie(fichier_rc, **{f"gdf_{_genre}": _gdf},
                              nom_zone_2d="Zone Test", remplacer=True)
        _octets = fichier_rc.read_bytes()
        _ctrl(f"ecrire des {_genre} par ras-commander garde l'encodage "
              f"de la geometrie (cp1252), accents et nom neuf compris",
              _octets.startswith(_tete) and b"For\xeat" in _octets
              and b"Line Name=\xc9cluse" in _octets,
              repr(_octets[:48]))
    # UNE GEOMETRIE TOUT ASCII EST DU cp1252 (decision du 11/10/2026) : le
    # nom d'apport neuf y prend un octet, comme HEC-RAS l'ecrit et comme
    # dans l'unsteady, et non deux (UTF-8).
    fichier_rc.write_bytes(_corps_rc.replace(b"For\xeat", b"Foret"))
    ecrire_dans_geometrie(fichier_rc, gdf_apports=_gdf,
                          nom_zone_2d="Zone Test")
    _octets = fichier_rc.read_bytes()
    _ctrl("dans une geometrie ASCII, un nom d'apport accentue s'ecrit en "
          "cp1252", b"Line Name=\xc9cluse" in _octets
          and b"\xc3" not in _octets,
          repr(_octets[_octets.find(b"Line Name="):][:24]))

print("\n" + "=" * 72)
if _echecs_pente:
    print(f"{len(_echecs_pente)} ECHEC(S) : {_echecs_pente}")
    raise SystemExit(1)
print("Couche geometrique operationnelle.")
print("=" * 72)
