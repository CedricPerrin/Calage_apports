"""
Caracterisation de trois lecteurs de src/pont_hecras.py : lire_serie_hdf,
commande_modele et _controler_residus_unsteady.

CE TEST NE DIT PAS CE QUE CES FONCTIONS DEVRAIENT FAIRE. Il enregistre ce
qu'elles FONT — la serie lue AU BIT PRES (chaque flottant en hexadecimal), ses
attributs et leurs types, le JSON rendu, les anomalies, l'exception levee le
cas echeant — dans une reference versionnee, et refuse toute difference.
C'est le filet tendu AVANT de les decouper (chantier du 10/11/2026).

    python -m pytest src/test_pont_lecture.py -q

QUAND UN CHANGEMENT EST VOULU : « python src/test_pont_lecture.py
--figer-reference » reecrit reference_pont_lecture.json.

lire_serie_hdf EST L'ENJEU : c'est par elle que chaque essai d'un calage lit
ce que HEC-RAS a calcule. Une erreur d'orientation, d'unite ou de colonne y
fausse tous les verdicts sans un mot. Les .hdf sont FABRIQUES avec h5py, sur
la structure que la fonction parcourt (CHEMIN_SERIES_HDF, « Reference
Lines » matricielles indexees par « Name », « Boundary Conditions » par objet
avec « Columns », « Time » en jours). Ce qu'un fichier fabrique ne peut pas
prouver — que HEC-RAS ecrit bien ainsi — est dit dans le rapport du chantier,
pas ici.

commande_modele : ras_commander (HdfBndry, HdfMesh) est DOUBLE — les GeoDataFrame
rendus sont choisis par le cas ; geometrie.py lit le vrai fichier texte.
_controler_residus_unsteady : rien n'est double sauf l'horloge de
pilote_hecras (l'age du pretraitement s'ecrit dans le message) ; les .pNN,
.gNN et .uNN sont ecrits comme HEC-RAS les ecrit, en cp1252 et CRLF.

NEUTRALISE : le dossier temporaire (« <TMP> »).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import h5py
import numpy as np
import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

import parametres  # noqa: E402
import pilote_hecras  # noqa: E402
import pont_hecras  # noqa: E402

REFERENCE = SRC / "reference_pont_lecture.json"
SERIES = pont_hecras.CHEMIN_SERIES_HDF


# ---------------------------------------------------------------------------
# Mise en forme figee
# ---------------------------------------------------------------------------

def _hex(v):
    v = float(v)
    return "nan" if np.isnan(v) else v.hex()


def _neutraliser(objet, dossier):
    variantes = sorted({str(dossier), str(Path(dossier).resolve())},
                       key=len, reverse=True)

    def nettoyer(o):
        if isinstance(o, str):
            for v in variantes:
                o = o.replace(v, "<TMP>")
            return o
        if isinstance(o, (list, tuple)):
            return [nettoyer(x) for x in o]
        if isinstance(o, dict):
            return {k: nettoyer(x) for k, x in o.items()}
        return o

    return nettoyer(objet)


def _exception(e):
    """
    Exception levee, figee selon SON ORIGINE.

    Levee par pont_hecras : type et message, au caractere pres — ce message
    est celui que l'utilisateur lit. Levee plus bas (h5py, numpy, pandas) :
    le type seul. Le texte d'une bibliotheque change d'une version a l'autre
    (« Unable to synchronously open file » est propre a h5py 3) ; le figer
    rendrait le filet rouge sur un autre socle sans que pont_hecras ait bouge.
    """
    tb = e.__traceback__
    while tb.tb_next is not None:
        tb = tb.tb_next
    if Path(tb.tb_frame.f_code.co_filename).name == "pont_hecras.py":
        return {"exception": type(e).__name__, "message": str(e)}
    return {"exception": type(e).__name__, "leve_par": "bibliotheque"}


def _serie(cadre):
    """Un DataFrame rendu par lire_serie_hdf, au bit pres."""
    return {
        "colonnes": [str(c) for c in cadre.columns],
        "dtypes": [str(d) for d in cadre.dtypes],
        "index": str(cadre.index),
        "temps": [_hex(v) for v in cadre["temps"]],
        "debit_m3s": [_hex(v) for v in cadre["debit_m3s"]],
        "attrs": {k: [type(v).__name__, v if isinstance(v, (bool, str))
                      else repr(v)] for k, v in cadre.attrs.items()},
    }


# ---------------------------------------------------------------------------
# lire_serie_hdf : fichiers de resultats fabriques
# ---------------------------------------------------------------------------

DEBIT = np.concatenate([np.linspace(10, 100, 7), np.linspace(90, 20, 6)])
T13 = np.linspace(0.0, 0.5, 13)              # 12 h en JOURS, pas de 1 h


def _ecrire_hdf(chemin, groupes=None, temps=T13, unite=b"days",
                autres=None, sans_series=False):
    """
    groupes : {nom_groupe: {nom_jeu: (donnees, {attribut: valeur})}}.
    unite : valeur de l'attribut « Time » du jeu Time ; None = pas d'attribut.
    autres : chemins de groupes a creer en plus (fichier sans resultats).
    """
    with h5py.File(chemin, "w") as h:
        for g in autres or []:
            h.require_group(g)
        if sans_series:
            return chemin
        h.require_group(SERIES)
        for nom_groupe, jeux in (groupes or {}).items():
            g = h.require_group(f"{SERIES}/{nom_groupe}")
            for nom_jeu, (donnees, attrs) in jeux.items():
                d = g.create_dataset(nom_jeu, data=donnees)
                for k, v in attrs.items():
                    d.attrs[k] = v
        if temps is not None:
            t = h.create_dataset(f"{SERIES}/Time", data=temps)
            if unite is not None:
                t.attrs["Time"] = unite
    return chemin


def _rl(noms, flow, autres=None):
    """Groupe « Reference Lines » matriciel."""
    jeux = {"Name": (noms, {})}
    if flow is not None:
        jeux["Flow"] = (flow, {})
    jeux.update(autres or {})
    return {"Reference Lines": jeux}


NOMS_AB = np.array([b"SECTION_A|Perimeter 1", b"SECTION_B|Perimeter 1"])
FLOW_AB = np.column_stack([-DEBIT, 3.0 * DEBIT])


def _bc(jeux):
    return {"Boundary Conditions": jeux}


STAGE_FLOW = np.array([b"Stage", b"Flow"], dtype="|S16")
BC_SF = np.column_stack([DEBIT * 0 + 440.0, DEBIT])

# Chaque cas : (kwargs de _ecrire_hdf, nom demande, groupe ou None = defaut)
CAS_HDF = {}


def cas_hdf(nom, fichier, demande, groupe="Reference Lines", **options):
    CAS_HDF[nom] = (fichier, demande, groupe, options)


# --- disposition matricielle
cas_hdf("rl/negatif_inverse", dict(groupes=_rl(NOMS_AB, FLOW_AB)), "SECTION_A")
cas_hdf("rl/positif_seconde_colonne", dict(groupes=_rl(NOMS_AB, FLOW_AB)),
        "SECTION_B")
cas_hdf("rl/groupe_par_defaut", dict(groupes=_rl(NOMS_AB, FLOW_AB)),
        "SECTION_B", groupe=None)
cas_hdf("rl/trois_lignes_celle_du_milieu",
        dict(groupes=_rl(np.array([b"S1|Z", b"S2|Z", b"S3|Z"]),
                         np.column_stack([DEBIT, 2 * DEBIT, 5 * DEBIT]))), "S2")
_variable = np.array([10, 40, -30, -60, 20, 50, -10, 5, 0, -5, 30, 10, 0.0])
cas_hdf("rl/signe_variable_reversible",
        dict(groupes=_rl(np.array([b"V|Z"]), _variable[:, None])), "V")
cas_hdf("rl/signe_variable_negatif_dominant_reversible",
        dict(groupes=_rl(np.array([b"V|Z"]), -1.5 * _variable[:, None])), "V")
_faible = -DEBIT.copy()
_faible[0] = 2.0                          # 2 contre ~700 : sous les 5 %
cas_hdf("rl/negatif_avec_pointe_positive_faible",
        dict(groupes=_rl(np.array([b"F|Z"]), _faible[:, None])), "F")
_seuil = DEBIT.copy()
_seuil[:3] = 0.0
_neg = float(np.sum(_seuil)) * 0.05       # exactement 5 % : non reversible
_seuil[-1] = -_neg
cas_hdf("rl/negatif_a_cinq_pour_cent_exactement",
        dict(groupes=_rl(np.array([b"F|Z"]), _seuil[:, None])), "F")
cas_hdf("rl/nul_partout",
        dict(groupes=_rl(np.array([b"N|Z"]), np.zeros((13, 1))),), "N")
cas_hdf("rl/egalite_positif_negatif",
        dict(groupes=_rl(np.array([b"E|Z"]),
                         np.array([5, -5, 5, -5, 0, 0, 0, 0, 0, 0, 0, 0, 0.0]
                                  )[:, None])), "E")
cas_hdf("rl/casse_differente", dict(groupes=_rl(NOMS_AB, FLOW_AB)), "section_b")
cas_hdf("rl/exact_prioritaire_sur_casse",
        dict(groupes=_rl(np.array([b"sec|Z", b"SEC|Z"]),
                         np.column_stack([DEBIT, 2 * DEBIT]))), "SEC")
cas_hdf("rl/doublon_premier_retenu",
        dict(groupes=_rl(np.array([b"D|Z1", b"D|Z2"]),
                         np.column_stack([DEBIT, 2 * DEBIT]))), "D")
cas_hdf("rl/nom_bourre_d_espaces",
        dict(groupes=_rl(np.array([b"SECTION_A       |Perimeter 1     ",
                                   b"SECTION_B       |Perimeter 1     "]),
                         FLOW_AB)), "SECTION_B")
cas_hdf("rl/nom_demande_avec_espaces", dict(groupes=_rl(NOMS_AB, FLOW_AB)),
        "  SECTION_B  ")
cas_hdf("rl/nom_sans_barre",
        dict(groupes=_rl(np.array([b"SECTION_A", b"SECTION_B"]), FLOW_AB)),
        "SECTION_B")
cas_hdf("rl/nom_absent", dict(groupes=_rl(NOMS_AB, FLOW_AB)), "INCONNUE")
cas_hdf("rl/nom_vide_demande", dict(groupes=_rl(NOMS_AB, FLOW_AB)), "")
cas_hdf("rl/nom_numerique", dict(groupes=_rl(np.array([b"12|Z"]),
                                            DEBIT[:, None])), 12)
cas_hdf("rl/sans_jeu_flow",
        dict(groupes=_rl(NOMS_AB, None,
                         {"Velocity": (FLOW_AB, {})})), "SECTION_A")
cas_hdf("rl/flow_une_dimension",
        dict(groupes=_rl(np.array([b"A|Z"]), DEBIT)), "A")
cas_hdf("rl/flow_moins_de_colonnes_que_de_noms",
        dict(groupes=_rl(NOMS_AB, DEBIT[:, None])), "SECTION_B")
cas_hdf("rl/name_en_chaines_variables",
        dict(groupes=_rl(np.array(["SECTION_A|Perimeter 1",
                                   "SECTION_B|Perimeter 1"],
                                  dtype=h5py.string_dtype()), FLOW_AB)),
        "SECTION_A")
cas_hdf("rl/nom_accentue_utf8",
        dict(groupes=_rl(np.array(["Pont de l'Église|Zone".encode("utf-8"),
                                   b"B|Zone"]), FLOW_AB)), "Pont de l'Église")
cas_hdf("rl/nom_accentue_cp1252",
        dict(groupes=_rl(np.array(["Pont de l'Église|Zone".encode("cp1252"),
                                   b"B|Zone"]), FLOW_AB)), "B")
cas_hdf("rl/valeurs_nan",
        dict(groupes=_rl(np.array([b"N|Z"]),
                         np.where(np.arange(13) % 4 == 1, np.nan,
                                  -DEBIT)[:, None])), "N")
cas_hdf("rl/flow_entier", dict(groupes=_rl(np.array([b"I|Z"]),
                                           np.arange(13, dtype=np.int32
                                                     )[:, None] - 20)), "I")
cas_hdf("rl/groupe_vide", dict(groupes={"Reference Lines": {}}), "SECTION_A")
cas_hdf("rl/sans_name_lu_comme_par_objet",
        dict(groupes={"Reference Lines": {"Flow": (FLOW_AB, {})}}), "Flow")

# --- temps
cas_hdf("temps/attribut_absent", dict(groupes=_rl(NOMS_AB, FLOW_AB),
                                      unite=None), "SECTION_B")
cas_hdf("temps/en_heures", dict(groupes=_rl(NOMS_AB, FLOW_AB),
                                temps=np.arange(13.0) * 2, unite=b"Hours"),
        "SECTION_B")
cas_hdf("temps/attribut_texte", dict(groupes=_rl(NOMS_AB, FLOW_AB),
                                     unite="days"), "SECTION_B")
cas_hdf("temps/attribut_majuscules", dict(groupes=_rl(NOMS_AB, FLOW_AB),
                                          unite=b"DAYS"), "SECTION_B")
cas_hdf("temps/attribut_inconnu", dict(groupes=_rl(NOMS_AB, FLOW_AB),
                                       unite=b"minutes"), "SECTION_B")
cas_hdf("temps/pas_irreguliers",
        dict(groupes=_rl(NOMS_AB, FLOW_AB),
             temps=np.array([0, 0.01, 0.02, 0.05, 0.1, 0.11, 0.2, 0.25, 0.3,
                             0.31, 0.4, 0.45, 0.5])), "SECTION_B")
cas_hdf("temps/origine_non_nulle",
        dict(groupes=_rl(NOMS_AB, FLOW_AB), temps=T13 + 43831.25),
        "SECTION_B")
cas_hdf("temps/plus_long_que_le_debit",
        dict(groupes=_rl(NOMS_AB, FLOW_AB), temps=np.linspace(0, 1, 25)),
        "SECTION_B")
cas_hdf("temps/plus_court_que_le_debit",
        dict(groupes=_rl(NOMS_AB, FLOW_AB), temps=T13[:5]), "SECTION_B")
cas_hdf("temps/jeu_absent", dict(groupes=_rl(NOMS_AB, FLOW_AB), temps=None),
        "SECTION_B")
cas_hdf("temps/jeu_vide",
        dict(groupes=_rl(NOMS_AB, np.zeros((0, 2))), temps=np.zeros(0)),
        "SECTION_B")
cas_hdf("temps/debit_vide_temps_present",
        dict(groupes=_rl(NOMS_AB, np.zeros((0, 2)))), "SECTION_B")

# --- disposition par objet
cas_hdf("bc/stage_flow", dict(groupes=_bc({"APPORT_X": (BC_SF, {"Columns":
                                                                STAGE_FLOW})})),
        "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/flow_stage",
        dict(groupes=_bc({"APPORT_X": (BC_SF[:, ::-1], {"Columns":
                                                        STAGE_FLOW[::-1]})})),
        "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/une_dimension", dict(groupes=_bc({"APPORT_X": (-DEBIT, {})})),
        "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/une_colonne_sans_attribut",
        dict(groupes=_bc({"APPORT_X": (DEBIT[:, None], {})})),
        "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/deux_colonnes_sans_attribut",
        dict(groupes=_bc({"APPORT_X": (BC_SF, {})})),
        "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/deux_colonnes_sans_flow",
        dict(groupes=_bc({"APPORT_X": (BC_SF, {"Columns": np.array(
            [b"Stage", b"Velocity"])})})), "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/une_colonne_columns_sans_flow",
        dict(groupes=_bc({"APPORT_X": (DEBIT[:, None], {"Columns": np.array(
            [b"Stage"])})})), "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/columns_en_chaines_variables",
        dict(groupes=_bc({"APPORT_X": (BC_SF, {"Columns": ["Stage", "Flow"]})})),
        "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/nom_bourre_d_espaces",
        dict(groupes=_bc({"APPORT_X        ": (BC_SF, {"Columns": STAGE_FLOW})})),
        "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/casse_differente",
        dict(groupes=_bc({"Apport_X": (BC_SF, {"Columns": STAGE_FLOW})})),
        "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/exact_prioritaire",
        dict(groupes=_bc({"apport_x": (BC_SF * 2, {"Columns": STAGE_FLOW}),
                          "APPORT_X": (BC_SF, {"Columns": STAGE_FLOW})})),
        "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/nom_absent",
        dict(groupes=_bc({"APPORT_X": (BC_SF, {"Columns": STAGE_FLOW})})),
        "APPORT_Y", groupe="Boundary Conditions")
cas_hdf("bc/negatif_inverse",
        dict(groupes=_bc({"APPORT_X": (-BC_SF, {"Columns": STAGE_FLOW})})),
        "APPORT_X", groupe="Boundary Conditions")
cas_hdf("bc/nom_accentue",
        dict(groupes=_bc({"Apport_Écluse": (BC_SF, {"Columns": STAGE_FLOW})})),
        "Apport_Écluse", groupe="Boundary Conditions")
cas_hdf("bc/valeurs_nan",
        dict(groupes=_bc({"APPORT_X": (np.where(BC_SF > 60, np.nan, BC_SF),
                                       {"Columns": STAGE_FLOW})})),
        "APPORT_X", groupe="Boundary Conditions")

# --- groupe et fichier
cas_hdf("fichier/groupe_absent", dict(groupes=_rl(NOMS_AB, FLOW_AB)), "X",
        groupe="Groupe Inexistant")
cas_hdf("fichier/sans_resultats_summary_unsteady",
        dict(sans_series=True, autres=["Results/Summary", "Results/Unsteady"]),
        "SECTION_A")
cas_hdf("fichier/vide", dict(sans_series=True), "SECTION_A")
cas_hdf("fichier/series_sans_le_groupe_demande",
        dict(groupes=_bc({"APPORT_X": (BC_SF, {"Columns": STAGE_FLOW})})),
        "SECTION_A")
cas_hdf("fichier/chemin_en_texte", dict(groupes=_rl(NOMS_AB, FLOW_AB)),
        "SECTION_A", texte=True)
cas_hdf("fichier/absent", None, "SECTION_A")
cas_hdf("fichier/pas_un_hdf", "texte", "SECTION_A")
cas_hdf("fichier/verrouille", dict(groupes=_rl(NOMS_AB, FLOW_AB)), "SECTION_A",
        verrou=True)


_VERROU = ("import h5py, sys, time\n"
           "f = h5py.File(sys.argv[1], 'a')\n"
           "print('pret', flush=True)\n"
           "time.sleep(60)\n")


def jouer_hdf(nom, dossier):
    fichier, demande, groupe, options = CAS_HDF[nom]
    chemin = Path(dossier) / "Essai.p01.hdf"
    if isinstance(fichier, dict):
        _ecrire_hdf(chemin, **fichier)
    elif fichier == "texte":
        chemin.write_text("pas un HDF", encoding="utf-8")
    argument = str(chemin) if options.get("texte") else chemin
    verrou = None
    if options.get("verrou"):
        # Un AUTRE processus tient le fichier : dans le meme processus, HDF5
        # ne verrouille pas. C'est le cas reel — HEC-RAS ou RAS Mapper ouvert.
        verrou = subprocess.Popen([sys.executable, "-I", "-c", _VERROU,
                                   str(chemin)], stdout=subprocess.PIPE,
                                  text=True)
        verrou.stdout.readline()
    try:
        kwargs = {} if groupe is None else {"groupe": groupe}
        rendu = _serie(pont_hecras.lire_serie_hdf(argument, demande, **kwargs))
    except Exception as e:  # noqa: BLE001 - l'exception fait partie du contrat
        rendu = _exception(e)
    finally:
        if verrou is not None:
            verrou.kill()
            verrou.wait()
    return _neutraliser(rendu, dossier)


# ---------------------------------------------------------------------------
# Fichiers texte HEC-RAS : cp1252 et CRLF
# ---------------------------------------------------------------------------

def _ecrire(chemin, lignes):
    Path(chemin).write_bytes(
        "".join(f"{ligne}\r\n" for ligne in lignes).encode("cp1252"))


def _champs16(points):
    """Coordonnees en champs fixes de 16 caracteres, deux points par ligne."""
    valeurs = [f"{v:16.4f}" for x, y in points for v in (x, y)]
    return ["".join(valeurs[k:k + 4]) for k in range(0, len(valeurs), 4)]


def _objet(genre, nom, zone, points):
    return ([f"{genre} Line Name={nom}", f"{genre} Line Storage Area={zone}",
             f"{genre} Line Arc= {len(points)} "] + _champs16(points))


def _perimetre(zone, points):
    return ([f"Storage Area={zone},1000,2000", "Storage Area Is2D=-1",
             f"Storage Area Surface Line= {len(points)} "] + _champs16(points))


# ---------------------------------------------------------------------------
# commande_modele
# ---------------------------------------------------------------------------

def _gdf(lignes, crs="EPSG:2154", colonne="Name", zones=False):
    import geopandas as gpd
    from shapely import wkt as shp_wkt

    if lignes is None:
        return None
    noms = [n for n, _ in lignes]
    formes = [None if f is None else shp_wkt.loads(f) for _, f in lignes]
    donnees = {} if colonne is None else {colonne: noms}
    if zones:
        donnees = {"mesh_name": noms}
    return gpd.GeoDataFrame(donnees, geometry=formes, crs=crs)


GEOM_TEXTE = (
    ["Geom Title=Modèle d'essai — état aménagé", "Program Version=6.60"]
    + _perimetre("Perimeter 1", [(0, 0), (1000, 0), (1000, 800), (0, 800)])
    + _objet("Reference", "S1", "Perimeter 1", [(100, 0), (100, 800)])
    + _objet("Reference", "S_Église", "Perimeter 1", [(500, 0), (500, 800)])
    + _objet("BC", "A1", "Perimeter 1", [(50, 100), (60, 200)])
    + _objet("BC", "A2", "Perimeter 1", [(400, 100), (410, 200)]))

HDF_REF = [("S1", "LINESTRING (100 0, 100 800)")]
HDF_BC = [("A1", "LINESTRING (50 100, 60 200)"),
          ("A2", "LINESTRING (400 100, 410 200)")]
HDF_ZONES = [("Perimeter 1", "POLYGON ((0 0, 1000 0, 1000 800, 0 800, 0 0))")]

CAS_MODELE = {}


def cas_modele(nom, texte=GEOM_TEXTE, hdf=True, ref=HDF_REF, bc=HDF_BC,
               zones=HDF_ZONES, crs=("EPSG:2154", "EPSG:2154", "EPSG:2154"),
               colonnes=("Name", "Name"), leve=None):
    CAS_MODELE[nom] = dict(texte=texte, hdf=hdf, ref=ref, bc=bc, zones=zones,
                           crs=crs, colonnes=colonnes, leve=leve)


cas_modele("nominal_pretraitee")
cas_modele("texte_absent", texte=None)
cas_modele("non_pretraitee", hdf=False)
cas_modele("non_pretraitee_texte_sans_objets", hdf=False,
           texte=GEOM_TEXTE[:2] + _perimetre("Z", [(0, 0), (5, 0), (5, 5)]))
cas_modele("objet_ecrit_pas_encore_pretraite", ref=[], bc=HDF_BC[:1])
cas_modele("ligne_hdf_sans_trace",
           ref=[("S1", "LINESTRING EMPTY"), ("S_Église", "LINESTRING EMPTY")])
cas_modele("ligne_hdf_geometrie_nulle", ref=[("S1", None)])
cas_modele("ligne_hdf_sans_trace_ni_texte",
           ref=HDF_REF + [("FANTOME", "LINESTRING EMPTY")])
cas_modele("objet_declare_illisible",
           texte=GEOM_TEXTE + ["Reference Line Name=ILLISIBLE",
                               "Reference Line Storage Area=Perimeter 1",
                               "Reference Line Arc= 1 ",
                               f"{100:16.4f}{5:16.4f}",
                               "BC Line Name=SANS_TRACE",
                               "BC Line Storage Area=Perimeter 1"])
cas_modele("sans_colonne_nom", colonnes=(None, None))
for _col in ("name", "Nom", "NOM"):
    cas_modele(f"colonne_nom_{_col}", colonnes=(_col, _col))
cas_modele("colonne_nom_inconnue", colonnes=("Label", "Label"))
cas_modele("hdf_vide_partout", ref=None, bc=[], zones=None)
cas_modele("zones_absentes_perimetre_du_texte", zones=None)
cas_modele("zones_vides_perimetre_du_texte", zones=[])
cas_modele("crs_seulement_sur_bc", crs=(None, "EPSG:3943", None))
cas_modele("crs_seulement_sur_zones", crs=(None, None, "EPSG:27572"))
cas_modele("crs_nulle_part", crs=(None, None, None))
# Trois CRS DIFFERENTS : seul cas ou l'ordre ref, bc, zones se voit.
cas_modele("crs_differents_ref_prioritaire",
           crs=("EPSG:2154", "EPSG:3943", "EPSG:27572"))
cas_modele("crs_ref_vide_ignore", ref=[], crs=("EPSG:3943", "EPSG:2154", None))
cas_modele("noms_hdf_avec_espaces",
           ref=[("  S1  ", "LINESTRING (100 0, 100 800)")])
cas_modele("hdf_illisible", leve="Unable to open file")


def jouer_modele(nom, dossier, capsys):
    import ras_commander

    c = CAS_MODELE[nom]
    dossier = Path(dossier)
    texte = dossier / "Essai.g01"
    hdf = dossier / "Essai.g01.hdf"
    if c["texte"] is not None:
        _ecrire(texte, c["texte"])
    if c["hdf"]:
        hdf.write_bytes(b"")
    appels = []

    def double(nom_appel, lignes, i_crs, colonne=None, zones=False):
        def f(chemin):
            appels.append([nom_appel, str(chemin)])
            if c["leve"]:
                raise OSError(c["leve"])
            return _gdf(lignes, crs=c["crs"][i_crs], colonne=colonne,
                        zones=zones)
        return f

    bndry = SimpleNamespace(
        get_bc_lines=double("HdfBndry.get_bc_lines", c["bc"], 1,
                            colonne=c["colonnes"][1]),
        get_reference_lines=double("HdfBndry.get_reference_lines", c["ref"], 0,
                                   colonne=c["colonnes"][0]))
    mesh = SimpleNamespace(get_mesh_areas=double("HdfMesh.get_mesh_areas",
                                                 c["zones"], 2, zones=True))
    capsys.readouterr()
    code, exception = None, None
    with mock.patch.object(ras_commander, "HdfBndry", bndry), \
            mock.patch.object(ras_commander, "HdfMesh", mesh):
        try:
            code = pont_hecras.commande_modele(SimpleNamespace(geometrie=str(hdf)))
        except Exception as e:  # noqa: BLE001
            exception = _exception(e)
    sortie = capsys.readouterr().out.splitlines()
    reponse = json.loads(sortie.pop()) if code is not None else None
    return _neutraliser({"code": code, "exception": exception,
                         "reponse": reponse, "autres_lignes": sortie,
                         "appels": appels}, dossier)


# ---------------------------------------------------------------------------
# _controler_residus_unsteady
# ---------------------------------------------------------------------------

def _localisation(nom, zone):
    """« Boundary Location= » au format a largeur fixe releve sur un modele reel."""
    return (f"Boundary Location={'':16},{'':16},{'':8},{'':8},{'':16},"
            f"{zone:16},{'':16},{nom:32},{'':32}")


def _bloc(nom, zone, valeurs, intervalle="1HOUR", hydrogramme=True):
    lignes = [_localisation(nom, zone)]
    if intervalle:
        lignes.append(f"Interval={intervalle}")
    if hydrogramme:
        lignes.append(f"Flow Hydrograph= {len(valeurs)} ")
        lignes += ["".join(f"{v:8.2f}" for v in valeurs[k:k + 10])
                   for k in range(0, len(valeurs), 10)]
        lignes += ["Stage Hydrograph TW Check=0", "Flow Hydrograph Slope= 0.01 "]
    else:
        lignes.append("Friction Slope=0.001,0")
    return lignes


V25 = [float(v) for v in range(25)]            # 24 h au pas horaire

UNSTEADY = (["Flow Title=Crue de référence — état aménagé", "Program Version=6.60",
             "Use Restart= 0 "]
            + _bloc("A1", "Perimeter 1", V25)
            + _bloc("A2", "Perimeter 1", V25)
            + _bloc("AVAL", "Perimeter 1", [], hydrogramme=False))

GEOM_RESIDUS = ["Geom Title=Essai", "BC Line Name=A1", "BC Line Name=A2",
                "BC Line Name=AVAL"]

PLAN = ["Plan Title=Référence", "Program Version=6.60", "Geom File=g01",
        "Flow File=u01", "Simulation Date=01JAN2020,0000,02JAN2020,0000",
        "Computation Interval=10SEC", "Output Interval=1HOUR"]

PARAMS = {"Dossier_projet_HECRAS": "<PROJET>", "Nom_projet": "Essai",
          "Plan_reference": "p01", "Nom_zone_2D": "Perimeter 1"}

MAINTENANT = 1_800_000_000.0

CAS_RESIDUS = {}


def cas_residus(nom, **changes):
    c = dict(params=PARAMS, classeur=True, plan=PLAN, geometrie=GEOM_RESIDUS,
             unsteady=UNSTEADY, ages=None, projet=True, unsteady_brut=None,
             unsteady_dossier=False, lecture_leve=False)
    c.update(changes)
    CAS_RESIDUS[nom] = c


def _p(**changes):
    d = dict(PARAMS)
    for k, v in changes.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    return d


cas_residus("nominal_rien_a_dire")
cas_residus("classeur_illisible", classeur=False)
cas_residus("dossier_projet_absent", projet=False)
cas_residus("unsteady_absent", unsteady=None)
cas_residus("pretraitement_perime", ages=(2.0, 5.5))
cas_residus("pretraitement_a_jour", ages=(5.5, 2.0))
cas_residus("pretraitement_jamais_fait", ages=(2.0, None))
cas_residus("plan_sans_geom_file",
            plan=[l for l in PLAN if not l.startswith("Geom File=")],
            ages=(2.0, 5.5))
cas_residus("geom_file_designe_absent",
            plan=[l.replace("Geom File=g01", "Geom File=g07") for l in PLAN],
            ages=(2.0, 5.5))
cas_residus("orphelins",
            unsteady=UNSTEADY + _bloc("ANCIEN_2", "Perimeter 1", V25)
            + _bloc("ANCIEN_1", "Perimeter 1", V25))
cas_residus("orphelin_hors_zone_ignore",
            unsteady=UNSTEADY + _bloc("ANCIEN", "Zone morte", V25))
cas_residus("geometrie_absente_aucun_filtre", geometrie=None,
            unsteady=UNSTEADY + _bloc("ANCIEN", "Perimeter 1", V25))
cas_residus("meme_nom_plusieurs_zones",
            unsteady=UNSTEADY + _bloc("A2", "Zone morte", V25)
            + _bloc("A1", "Autre zone", V25))
cas_residus("meme_nom_plusieurs_zones_orphelin_ignore",
            unsteady=UNSTEADY + _bloc("ANCIEN", "Perimeter 1", V25)
            + _bloc("ANCIEN", "Zone morte", V25))
cas_residus("sans_zone_aucun_controle_de_zones",
            params=_p(Nom_zone_2D=None),
            unsteady=UNSTEADY + _bloc("A2", "Zone morte", V25)
            + _bloc("ANCIEN", "Zone morte", V25))
cas_residus("serie_aberrante",
            unsteady=UNSTEADY + _bloc("LONG", "Perimeter 1",
                                      [1.0] * 400, intervalle="1HOUR"),
            geometrie=GEOM_RESIDUS + ["BC Line Name=LONG"])
cas_residus("serie_au_seuil_exact",
            unsteady=UNSTEADY + _bloc("SEUIL", "Perimeter 1",
                                      [1.0] * 241, intervalle="1HOUR"),
            geometrie=GEOM_RESIDUS + ["BC Line Name=SEUIL"])
cas_residus("deux_series_aberrantes_au_pas_6min",
            unsteady=UNSTEADY + _bloc("L1", "Perimeter 1", [1.0] * 2500,
                                      intervalle="6MIN")
            + _bloc("L2", "Perimeter 1", [1.0] * 3000, intervalle="6MIN"),
            geometrie=GEOM_RESIDUS + ["BC Line Name=L1", "BC Line Name=L2"])
cas_residus("serie_sans_intervalle_ignoree",
            unsteady=UNSTEADY + _bloc("LONG", "Perimeter 1", [1.0] * 400,
                                      intervalle=None),
            geometrie=GEOM_RESIDUS + ["BC Line Name=LONG"])
cas_residus("fenetre_absente",
            plan=[l for l in PLAN if not l.startswith("Simulation Date=")],
            unsteady=UNSTEADY + _bloc("LONG", "Perimeter 1", [1.0] * 400),
            geometrie=GEOM_RESIDUS + ["BC Line Name=LONG"])
cas_residus("fenetre_nulle",
            plan=[l.replace("02JAN2020,0000", "01JAN2020,0000") for l in PLAN],
            unsteady=UNSTEADY + _bloc("LONG", "Perimeter 1", [1.0] * 400),
            geometrie=GEOM_RESIDUS + ["BC Line Name=LONG"])
cas_residus("fenetre_inversee",
            plan=[l.replace("01JAN2020,0000,02JAN2020", "03JAN2020,0000,02JAN2020")
                  for l in PLAN],
            unsteady=UNSTEADY + _bloc("LONG", "Perimeter 1", [1.0] * 400),
            geometrie=GEOM_RESIDUS + ["BC Line Name=LONG"])
cas_residus("fenetre_2400_fin_de_journee",
            plan=[l.replace("01JAN2020,0000,02JAN2020,0000",
                            "01JAN2020,0000,01JAN2020,2400") for l in PLAN],
            unsteady=UNSTEADY + _bloc("LONG", "Perimeter 1", [1.0] * 400),
            geometrie=GEOM_RESIDUS + ["BC Line Name=LONG"])
cas_residus("unsteady_illisible_garde_le_pretraitement", ages=(2.0, 5.5),
            unsteady_brut=b"\x00\x01 pas un unsteady")
# Le .u01 est un DOSSIER : cartographier_hydrogrammes leve pour de vrai.
cas_residus("unsteady_dossier_illisible_garde_le_pretraitement", ages=(2.0, 5.5),
            unsteady=None, unsteady_dossier=True)
# Le SEUL double de cette famille : l'analyseur de tableaux de ras_commander
# n'echoue sur aucun contenu (il saute ce qu'il ne lit pas). On simule un
# fichier qui disparait entre la carte et la lecture des valeurs.
cas_residus("lecture_d_une_serie_en_echec_ignoree", lecture_leve=True,
            unsteady=UNSTEADY + _bloc("LONG", "Perimeter 1", [1.0] * 400)
            + _bloc("LONG2", "Perimeter 1", [1.0] * 500),
            geometrie=GEOM_RESIDUS + ["BC Line Name=LONG", "BC Line Name=LONG2"])
cas_residus("override_plan_absent",
            params=_p(Mode_selection_modele="override", Unsteady_reference="u01",
                      Plan_reference="p09"),
            unsteady=UNSTEADY + _bloc("ANCIEN", "Perimeter 1", V25))
cas_residus("tout_a_la_fois", ages=(1.0, 30.25),
            unsteady=UNSTEADY + _bloc("ANCIEN", "Perimeter 1", V25)
            + _bloc("A1", "Zone morte", V25)
            + _bloc("LONG", "Perimeter 1", [1.0] * 400),
            geometrie=GEOM_RESIDUS + ["BC Line Name=LONG"])


def jouer_residus(nom, dossier):
    c = CAS_RESIDUS[nom]
    dossier = Path(dossier)
    projet = dossier / "projet"
    classeur = dossier / "donnees.xlsx"
    if c["projet"]:
        projet.mkdir()
        if c["plan"] is not None:
            _ecrire(projet / "Essai.p01", c["plan"])
        if c["geometrie"] is not None:
            _ecrire(projet / "Essai.g01", c["geometrie"])
        if c["unsteady_brut"] is not None:
            (projet / "Essai.u01").write_bytes(c["unsteady_brut"])
        elif c["unsteady_dossier"]:
            (projet / "Essai.u01").mkdir()
        elif c["unsteady"] is not None:
            _ecrire(projet / "Essai.u01", c["unsteady"])
        if c["ages"] is not None:
            age_g, age_h = c["ages"]
            g = projet / "Essai.g01"
            if age_h is not None:
                (projet / "Essai.g01.hdf").write_bytes(b"\0" * 2048)
                os.utime(projet / "Essai.g01.hdf",
                         (MAINTENANT - age_h * 3600,) * 2)
            if g.exists():
                os.utime(g, (MAINTENANT - age_g * 3600,) * 2)
    if c["classeur"]:
        import pandas as pd
        with pd.ExcelWriter(classeur, engine="openpyxl") as w:
            pd.DataFrame({"Ordre": [1, 2],
                          "Nom_Apport (BC line)": ["A1", "A2"],
                          "Nom_Section (reference line)": ["S1", "S2"],
                          "Nom_Cible": ["C1", "C2"]}).to_excel(
                w, sheet_name="Correspondance", index=False)
        parametres.chemin(classeur).write_text(json.dumps(
            {k: (str(projet) if v == "<PROJET>" else v)
             for k, v in c["params"].items()}), encoding="utf-8")
    horloge = SimpleNamespace(time=lambda: MAINTENANT)
    vraie_lecture = pilote_hecras.lire_hydrogramme_unsteady

    def lecture(fichier, debut, fin):
        # Echoue sur la premiere serie seulement : la suivante doit etre lue.
        if c["lecture_leve"] and debut == min(
                i["debut"] for i in pilote_hecras.cartographier_hydrogrammes(
                    fichier, "Perimeter 1").values()
                if i["nb"] > 30):          # « nb » compte des LIGNES
            raise OSError("fichier disparu")
        return vraie_lecture(fichier, debut, fin)

    try:
        with mock.patch.object(pilote_hecras, "time", horloge), \
                mock.patch.object(pilote_hecras, "lire_hydrogramme_unsteady",
                                  lecture):
            rendu = {"anomalies": [list(a) for a in
                                   pont_hecras._controler_residus_unsteady(
                                       classeur)]}
    except Exception as e:  # noqa: BLE001
        rendu = _exception(e)
    return _neutraliser(rendu, dossier)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _lire_reference():
    with REFERENCE.open(encoding="utf-8") as f:
        return json.load(f)


def test_reference_couvre_tous_les_cas():
    ref = _lire_reference()
    assert sorted(ref["lire_serie_hdf"]) == sorted(CAS_HDF)
    assert sorted(ref["commande_modele"]) == sorted(CAS_MODELE)
    assert sorted(ref["controler_residus_unsteady"]) == sorted(CAS_RESIDUS)


@pytest.mark.parametrize("nom", sorted(CAS_HDF))
def test_lire_serie_hdf(nom, tmp_path):
    assert jouer_hdf(nom, tmp_path) == _lire_reference()["lire_serie_hdf"][nom]


@pytest.mark.parametrize("nom", sorted(CAS_MODELE))
def test_commande_modele(nom, tmp_path, capsys):
    assert (jouer_modele(nom, tmp_path, capsys)
            == _lire_reference()["commande_modele"][nom])


@pytest.mark.parametrize("nom", sorted(CAS_RESIDUS))
def test_controler_residus_unsteady(nom, tmp_path):
    assert (jouer_residus(nom, tmp_path)
            == _lire_reference()["controler_residus_unsteady"][nom])


def test_un_autre_texte_de_bibliotheque_ne_change_rien(tmp_path):
    """Autre socle simule : h5py leve la meme exception avec un autre texte."""
    def ouvrir(*_a, **_k):
        raise FileNotFoundError("texte d'une autre version de h5py")

    with mock.patch.object(h5py, "File", ouvrir):
        obtenu = jouer_hdf("fichier/absent", tmp_path)
    assert obtenu == _lire_reference()["lire_serie_hdf"]["fichier/absent"]


class _Capture:
    """capsys hors pytest, pour --figer-reference."""

    def __init__(self):
        import io
        self._io, self._ancien, self._out = io, None, None

    def readouterr(self):
        if self._ancien is None:
            self._ancien = sys.stdout
        rendu = SimpleNamespace(out=self._out.getvalue() if self._out else "")
        self._out = self._io.StringIO()
        sys.stdout = self._out
        return rendu

    def fermer(self):
        if self._ancien is not None:
            sys.stdout = self._ancien


def figer_reference():
    def tous(cas, jouer):
        rendus = {}
        for nom in sorted(cas):
            with tempfile.TemporaryDirectory() as d:
                rendus[nom] = jouer(nom, Path(d))
        return rendus

    def modele(nom, d):
        capture = _Capture()
        try:
            return jouer_modele(nom, d, capture)
        finally:
            capture.fermer()

    contenu = {
        "_a_propos": (
            "Caracterisation de lire_serie_hdf, commande_modele et "
            "_controler_residus_unsteady (src/test_pont_lecture.py). NE PAS "
            "MODIFIER A LA MAIN : « python src/test_pont_lecture.py "
            "--figer-reference » le reecrit quand le changement de "
            "comportement est VOULU."),
        "lire_serie_hdf": tous(CAS_HDF, jouer_hdf),
        "commande_modele": tous(CAS_MODELE, modele),
        "controler_residus_unsteady": tous(CAS_RESIDUS, jouer_residus),
    }
    REFERENCE.write_text(json.dumps(contenu, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    print(f"{sum(len(v) for k, v in contenu.items() if k[0] != '_')} cas "
          f"figes dans {REFERENCE.name}")


if __name__ == "__main__":
    if "--figer-reference" in sys.argv:
        figer_reference()
    else:
        sys.exit(pytest.main([__file__, "-q"]))
