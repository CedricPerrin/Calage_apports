"""
Caracterisation des trois controles de controle_donnees.py :
controler_template, controler_geometrie et controler_contre_modele.

CE TEST NE DIT PAS CE QUE LES CONTROLES DEVRAIENT FAIRE. Il enregistre ce
qu'ils FONT — chaque message a l'octet pres, son niveau, leur ordre, la forme
de la valeur rendue, l'exception levee le cas echeant — dans une reference
versionnee, et refuse toute difference. C'est le filet tendu AVANT de
decouper ces trois fonctions en regles nommees (chantier du 10/11/2026) :
le decoupage doit le laisser vert sans qu'on y touche.

    python -m pytest src/test_controle_donnees.py -q

QUAND UN CHANGEMENT EST VOULU : « python src/test_controle_donnees.py
--figer-reference » reecrit reference_controle_donnees.json. Le refuser sans
ce geste explicite est tout l'interet — une reference qui se met a jour
toute seule ne prouve rien.

CHAQUE CAS PROVOQUE UNE BRANCHE PRECISE : un cas sain, puis un defaut a la
fois, puis quelques combinaisons. Tout est fabrique dans un dossier
temporaire, dont le chemin est remplace par « <TMP> » : la reference est la
meme d'un poste a l'autre.

SANS HEC-RAS NI h5py : ras_commander est remplace par un faux module, et les
lectures HDF de geometrie.py (zones_2d, taille_maille, objets_depuis_texte)
par des fonctions qui rendent ce que le cas a decide. controler_contre_modele
est donc juge sur SA logique — l'enchainement des controles et leurs
messages — et non sur la lecture des fichiers HEC-RAS, que pilote_hecras et
geometrie eprouvent ailleurs.
"""
import json
import shutil
import sys
import tempfile
import types
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd
import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

import controle_donnees as cd  # noqa: E402
import parametres  # noqa: E402

REFERENCE = SRC / "reference_controle_donnees.json"
RACINE = SRC.parent
CRS = "EPSG:2154"

# ---------------------------------------------------------------------------
# Mise en forme figee d'un resultat
# ---------------------------------------------------------------------------


def _py(v):
    """Scalaire numpy -> scalaire Python, pour JSON."""
    return v.item() if isinstance(v, np.generic) else v


def _anomalies(liste):
    return {
        "type": type(liste).__name__,
        "types_elements": sorted({type(a).__name__ for a in liste}),
        "anomalies": [[a[0], a[1]] for a in liste],
    }


def _tableau(t):
    if t is None:
        return None
    return {
        "type": type(t).__name__,
        "index": str(t.index),
        "colonnes": [str(c) for c in t.columns],
        "dtypes": [str(d) for d in t.dtypes],
        "lignes": [[_py(v) for v in ligne] for ligne in t.itertuples(index=False)],
    }


def _figer(appel):
    """Appelle, et rend la sortie sous une forme comparable et serialisable."""
    try:
        r = appel()
    except Exception as e:  # noqa: BLE001 - l'exception fait partie du contrat
        return {"exception": type(e).__name__, "message": str(e)}
    if isinstance(r, tuple):
        return {"type": "tuple", "longueur": len(r),
                "rendu": _anomalies(r[0]), "tableau": _tableau(r[1])}
    return {"rendu": _anomalies(r)}


def _neutraliser(objet, dossier):
    """Remplace le dossier temporaire par <TMP>, partout ou il apparait."""
    variantes = sorted({str(dossier), str(Path(dossier).resolve())},
                       key=len, reverse=True)

    def nettoyer(o):
        if isinstance(o, str):
            for v in variantes:
                o = o.replace(v, "<TMP>")
            return o
        if isinstance(o, list):
            return [nettoyer(x) for x in o]
        if isinstance(o, dict):
            return {k: nettoyer(x) for k, x in o.items()}
        return o

    return nettoyer(objet)


# ---------------------------------------------------------------------------
# Fabrication des classeurs
# ---------------------------------------------------------------------------

PARAMS = {"Dossier_projet_HECRAS": r"D:\projet", "Nom_projet": "Essai",
          "Nom_zone_2D": "Zone2D", "Nb_max_iterations_par_apport": 6}

COL_APPORT = "Nom_Apport (BC line)"
COL_SECTION = "Nom_Section (reference line)"

CORR = {"Ordre": [1, 2, 3],
        COL_APPORT: ["A1", "A2", "A3"],
        COL_SECTION: ["S1", "S2", "S3"],
        "Nom_Cible": ["C1", "C2", "C3"]}

_HYDRO = [0.0, 1.0, 3.0, 6.0, 10.0, 8.0, 5.0, 3.0, 2.0, 1.0, 0.5, 0.2]
CIBLES = {"Temps_h": list(range(12)),
          "C1": list(_HYDRO),
          "C2": [2 * q for q in _HYDRO],
          "C3": [3 * q for q in _HYDRO]}


def _avec(base, **changes):
    d = dict(base)
    for k, v in changes.items():
        if v is _SUPPRIMER:
            d.pop(k, None)
        else:
            d[k] = v
    return d


_SUPPRIMER = object()


def classeur(dossier, nom="donnees.xlsx", params=PARAMS, corr=CORR,
             cibles=CIBLES, autres=None, json_brut=None):
    """Classeur + JSON de parametres. None = feuille ou JSON absents."""
    chemin = Path(dossier) / nom
    with pd.ExcelWriter(chemin, engine="openpyxl") as w:
        ecrit = False
        if corr is not None:
            pd.DataFrame(corr).to_excel(w, sheet_name="Correspondance", index=False)
            ecrit = True
        if cibles is not None:
            pd.DataFrame(cibles).to_excel(w, sheet_name="Cibles", index=False)
            ecrit = True
        for feuille, contenu in (autres or {}).items():
            pd.DataFrame(contenu).to_excel(w, sheet_name=feuille, index=False)
            ecrit = True
        if not ecrit:
            pd.DataFrame({"x": [1]}).to_excel(w, sheet_name="Autre", index=False)
    if json_brut is not None:
        parametres.chemin(chemin).write_text(json_brut, encoding="utf-8")
    elif params is not None:
        parametres.ecrire(chemin, params)
    return chemin


def _json_avec_nan(valeurs):
    """JSON portant un NaN litteral : json.load le relit en float('nan')."""
    return json.dumps(valeurs, ensure_ascii=False, allow_nan=True)


def _bloquer(*modules):
    """Rend ces imports impossibles (ImportError), le temps d'un appel."""
    return mock.patch.dict(sys.modules, {m: None for m in modules})


# ---------------------------------------------------------------------------
# Registre des cas
# ---------------------------------------------------------------------------

CAS = {}


def cas(nom):
    def enregistrer(f):
        assert nom not in CAS, nom
        CAS[nom] = f
        return f
    return enregistrer


# ===========================================================================
# controler_template
# ===========================================================================

def _tpl(dossier, **kw):
    return _figer(lambda: cd.controler_template(classeur(dossier, **kw)))


@cas("template/sain")
def _(d):
    return _tpl(d)


@cas("template/livre_avec_le_projet")
def _(d):
    for f in ("template_donnees_calage.xlsx", "template_donnees_calage.json"):
        shutil.copy(RACINE / f, Path(d) / f)
    return _figer(lambda: cd.controler_template(Path(d) / "template_donnees_calage.xlsx"))


@cas("template/classeur_absent")
def _(d):
    return _figer(lambda: cd.controler_template(Path(d) / "absent.xlsx"))


@cas("template/classeur_pas_excel")
def _(d):
    p = Path(d) / "faux.xlsx"
    p.write_text("ceci n'est pas un classeur", encoding="utf-8")
    return _figer(lambda: cd.controler_template(p))


@cas("template/feuille_cibles_absente")
def _(d):
    return _tpl(d, cibles=None)


@cas("template/feuilles_absentes_toutes")
def _(d):
    return _tpl(d, corr=None, cibles=None)


@cas("template/parametres_introuvables")
def _(d):
    return _tpl(d, params=None)


@cas("template/parametres_feuille_heritee")
def _(d):
    heritee = {"Parametre": list(PARAMS) + ["Coeurs_par_calcul"],
               "Valeur": list(PARAMS.values()) + [None]}
    return _tpl(d, params=None, autres={"Parametres": heritee})


@cas("template/parametres_json_corrompu")
def _(d):
    return _tpl(d, json_brut="{ pas du json")


@cas("template/parametre_requis_absent")
def _(d):
    return _tpl(d, params=_avec(PARAMS, Nom_zone_2D=_SUPPRIMER))


@cas("template/parametre_requis_none")
def _(d):
    return _tpl(d, params=_avec(PARAMS, Nom_projet=None))


@cas("template/parametre_requis_nan")
def _(d):
    return _tpl(d, json_brut=_json_avec_nan(
        _avec(PARAMS, Dossier_projet_HECRAS=float("nan"))))


@cas("template/nb_max_2")
def _(d):
    return _tpl(d, params=_avec(PARAMS, Nb_max_iterations_par_apport=2))


@cas("template/nb_max_2_5")
def _(d):
    return _tpl(d, params=_avec(PARAMS, Nb_max_iterations_par_apport=2.5))


@cas("template/nb_max_3")
def _(d):
    return _tpl(d, params=_avec(PARAMS, Nb_max_iterations_par_apport=3))


@cas("template/nb_max_chaine")
def _(d):
    return _tpl(d, params=_avec(PARAMS, Nb_max_iterations_par_apport="2"))


for _nom, _val in (("vide", ""), ("none", None), ("zero", 0), ("8", 8),
                   ("8_0", 8.0), ("64", 64), ("65", 65), ("moins_1", -1),
                   ("4_5", 4.5), ("chaine", "4"), ("vrai", True)):
    def _f(d, _val=_val):
        return _tpl(d, params=_avec(PARAMS, Coeurs_par_calcul=_val))
    cas(f"template/coeurs_{_nom}")(_f)


@cas("template/coeurs_nan")
def _(d):
    return _tpl(d, json_brut=_json_avec_nan(
        _avec(PARAMS, Coeurs_par_calcul=float("nan"))))


@cas("template/fenetre_valide")
def _(d):
    return _tpl(d, params=_avec(PARAMS, Simulation_debut="13OCT2014,00:00",
                                Simulation_fin="14OCT2014,04:00",
                                Intervalle_calcul="10SEC",
                                Intervalle_sortie="15MIN"))


@cas("template/fenetre_date_francaise")
def _(d):
    return _tpl(d, params=_avec(PARAMS, Simulation_debut="13/10/2014 00:00",
                                Simulation_fin="14OCT2014,04:00"))


@cas("template/fenetre_incomplete_et_blancs")
def _(d):
    # « Simulation_fin » en blancs seuls : non retenue ; le debut reste seul.
    return _tpl(d, params=_avec(PARAMS, Simulation_debut="13OCT2014,00:00",
                                Simulation_fin="   ", Intervalle_calcul=None))


@cas("template/fenetre_nan")
def _(d):
    return _tpl(d, json_brut=_json_avec_nan(
        _avec(PARAMS, Simulation_debut=float("nan"),
              Intervalle_sortie="abc")))


@cas("template/fenetre_sans_pilote")
def _(d):
    with _bloquer("pilote_hecras"):
        return _tpl(d, params=_avec(PARAMS, Simulation_debut="13/10/2014 00:00",
                                    Simulation_fin="x"))


@cas("template/correspondance_colonnes_manquantes")
def _(d):
    return _tpl(d, corr=_avec(CORR, Nom_Cible=_SUPPRIMER))


@cas("template/correspondance_sans_ordre")
def _(d):
    return _tpl(d, corr=_avec(CORR, Ordre=_SUPPRIMER))


@cas("template/correspondance_vide")
def _(d):
    return _tpl(d, corr={"Ordre": [1, None], COL_APPORT: [None, "A2"],
                         COL_SECTION: ["S1", "S2"], "Nom_Cible": ["C1", "C2"]})


@cas("template/correspondance_lignes_incompletes_ignorees")
def _(d):
    return _tpl(d, corr={"Ordre": [1, 2, 3, None],
                         COL_APPORT: ["A1", "A2", "A3", "A4"],
                         COL_SECTION: ["S1", "S2", "S3", "S4"],
                         "Nom_Cible": ["C1", "C2", "C3", "C4"]})


@cas("template/ordre_non_contigu")
def _(d):
    return _tpl(d, corr=_avec(CORR, Ordre=[1, 2, 4]))


@cas("template/ordre_doublon")
def _(d):
    return _tpl(d, corr=_avec(CORR, Ordre=[1, 1, 2]))


@cas("template/ordre_non_numerique")
def _(d):
    return _tpl(d, corr=_avec(CORR, Ordre=[1, "deux", 3]))


@cas("template/apport_en_doublon")
def _(d):
    return _tpl(d, corr=_avec(CORR, **{COL_APPORT: ["A1", "A2", "A2"]}))


@cas("template/section_en_doublon")
def _(d):
    return _tpl(d, corr=_avec(CORR, **{COL_SECTION: ["S1", "S1", "S1"]}))


_CORR_PREFIXE = {"Ordre": [1, 2], COL_APPORT: ["APP06", "APP07"],
                 COL_SECTION: ["S1", "S2"], "Nom_Cible": ["C1", "C2"]}
_CIBLES_PREFIXE = {"Temps_h": list(range(11)), "C1": list(range(11)),
                   "C2": list(range(11))}

for _nom, _pref in (("vide", ""), ("court", "Q100"), ("limite", "Riviere1-Q100"),
                    ("trop_long", "Riviere1_Q100_1000_ABC"),
                    ("beaucoup_trop_long", "P" * 40)):
    def _f(d, _pref=_pref):
        return _tpl(d, params=_avec(PARAMS, Prefixe_scenario=_pref),
                    corr=_CORR_PREFIXE, cibles=_CIBLES_PREFIXE)
    cas(f"template/prefixe_{_nom}")(_f)


@cas("template/prefixe_ordre_des_lignes_inverse")
def _(d):
    # La colonne Ordre, pas l'ordre des lignes, designe le premier apport :
    # ici APP07 (Ordre 1) n'a pas de titre de reprise, APP06 (Ordre 2) si.
    corr = {"Ordre": [2, 1], COL_APPORT: ["APP06", "APP0000007"],
            COL_SECTION: ["S1", "S2"], "Nom_Cible": ["C1", "C2"]}
    return _tpl(d, params=_avec(PARAMS, Prefixe_scenario="Riviere1_Q100_1000_A"),
                corr=corr, cibles=_CIBLES_PREFIXE)


@cas("template/prefixe_nan")
def _(d):
    return _tpl(d, json_brut=_json_avec_nan(
        _avec(PARAMS, Prefixe_scenario=float("nan"))),
        corr=_CORR_PREFIXE, cibles=_CIBLES_PREFIXE)


@cas("template/prefixe_sans_calage")
def _(d):
    with _bloquer("calage"):
        return _tpl(d, params=_avec(PARAMS, Prefixe_scenario="P" * 40),
                    corr=_CORR_PREFIXE, cibles=_CIBLES_PREFIXE)


@cas("template/cibles_sans_temps")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, Temps_h=_SUPPRIMER))


@cas("template/cibles_peu_de_pas")
def _(d):
    return _tpl(d, cibles={"Temps_h": [0, 1, 2, 3], "C1": [1, 5, 3, 1],
                           "C2": [1, 6, 3, 1], "C3": [1, 7, 3, 1]})


@cas("template/cibles_dix_pas")
def _(d):
    # La borne : dix pas de temps suffisent, neuf non.
    return _tpl(d, cibles={c: v[:10] for c, v in CIBLES.items()})


@cas("template/cibles_neuf_pas")
def _(d):
    return _tpl(d, cibles={c: v[:9] for c, v in CIBLES.items()})


@cas("template/cibles_un_seul_pas")
def _(d):
    return _tpl(d, cibles={"Temps_h": [0], "C1": [1], "C2": [1], "C3": [1]})


@cas("template/cibles_temps_non_croissant")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, Temps_h=[0, 1, 2, 3, 4, 5, 5, 7, 8, 9, 10, 11]))


@cas("template/cibles_temps_texte_ignore")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, Temps_h=[0, 1, 2, "x", 4, 5, 6, 7, 8, 9, 10, 11]))


@cas("template/cible_absente_et_inutilisee")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, C3=_SUPPRIMER, C_inutile=list(_HYDRO)))


@cas("template/cibles_apercu_style_exclu")
def _(d):
    import style_classeur
    cib = _avec(CIBLES, **{style_classeur.ENTETE_PIC: ["C1"] * 12,
                          "": [None] * 12})
    return _tpl(d, cibles=cib)


@cas("template/cibles_apercu_sans_style_classeur")
def _(d):
    import style_classeur
    cib = _avec(CIBLES, **{style_classeur.ENTETE_PIC: ["C1"] * 12})
    with _bloquer("style_classeur"):
        return _tpl(d, cibles=cib)


@cas("template/cibles_entete_numerique")
def _(d):
    return _tpl(d, cibles={**CIBLES, 5: list(_HYDRO)})


@cas("template/cible_vide")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, C2=[None] * 12))


@cas("template/cible_une_valeur")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, C2=[4.0] + [None] * 11))


@cas("template/cible_texte_une_valeur")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, C2=["a"] * 11 + [3.0]))


@cas("template/cible_negative")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, C2=[1, -8] + _HYDRO[2:]))


@cas("template/cible_nulle")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, C2=[0.0] * 12))


@cas("template/cible_negative_et_nulle")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, C2=[-1.0] * 12))


@cas("template/cible_trous_intercales")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, C2=_HYDRO[:3] + [None] + _HYDRO[4:]))


@cas("template/cible_trous_en_fin")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, C2=_HYDRO[:9] + [None] * 3))


@cas("template/cible_trous_en_tete")
def _(d):
    return _tpl(d, cibles=_avec(CIBLES, C2=[None] * 3 + _HYDRO[3:]))


@cas("template/fautif_du_banc")
def _(d):
    # Le classeur fautif du banc embarque : huit anomalies d'un coup.
    return _tpl(d, params={"Dossier_projet_HECRAS": r"D:\projet",
                           "Nom_projet": "Essai",
                           "Nb_max_iterations_par_apport": 2,
                           "Simulation_debut": "13/10/2014 00:00",
                           "Simulation_fin": "14OCT2014,04:00"},
                corr={"Ordre": [1, 2, 4], COL_APPORT: ["A1", "A2", "A2"],
                      COL_SECTION: ["S1", "S2", "S3"],
                      "Nom_Cible": ["C1", "C2", "C_absente"]},
                cibles={"Temps_h": [0, 2, 1, 6], "C1": [1, 5, 3, 1],
                        "C2": [1, -8, 3, 1], "C_inutile": [1, 2, 3, 4]})


@cas("template/combinaison_parametres_et_cibles_vides")
def _(d):
    return _tpl(d, params=None, cibles={"Temps_h": [0, 1], "C1": [None, None],
                                        "C2": [1, None], "C3": [0, 0]})


# ===========================================================================
# controler_geometrie
# ===========================================================================

def _transversale(xl, demi=400.0):
    from shapely.geometry import LineString
    y = 300 * np.sin(xl / 1400)
    return LineString([(500000 + xl, 6200000 + y - demi),
                       (500000 + xl, 6200000 + y + demi)])


def _shp(dossier, nom, noms, geoms, crs=CRS, colonne="Nom"):
    import geopandas as gpd
    chemin = Path(dossier) / nom
    gpd.GeoDataFrame({colonne: noms}, geometry=geoms, crs=crs).to_file(chemin)
    return chemin


def _sig(dossier, sections=None, apports=None, axe=True, crs_apports=CRS,
         colonne="Nom"):
    """Axe, sections et apports de reference (ceux du banc embarque)."""
    from shapely.geometry import LineString
    xs = np.linspace(0, 8000, 60)
    p_axe = None
    if axe:
        p_axe = _shp(dossier, "axe.shp", ["Axe"],
                     [LineString(zip(500000 + xs, 6200000 + 300 * np.sin(xs / 1400)))])
    sections = sections or (["S1", "S2", "S3"],
                            [_transversale(x) for x in (900, 2800, 5100)])
    apports = apports or (["A1", "A2", "A3"],
                          [_transversale(x, 250) for x in (200, 2100, 4300)])
    p_sec = _shp(dossier, "sections.shp", *sections, colonne=colonne)
    p_app = _shp(dossier, "apports.shp", *apports, crs=crs_apports, colonne=colonne)
    return p_sec, p_app, p_axe


def _params_sig(dossier, p_sec, p_app, p_axe, **changes):
    v = _avec(PARAMS, Fichier_SHP_Sections=str(p_sec),
              Fichier_SHP_Apports=str(p_app),
              Fichier_SHP_Axe=str(p_axe) if p_axe else "",
              Sens_axe="amont_aval")
    return _avec(v, **changes)


def _geo(dossier, corr=CORR, sig=None, json_nan=False, **changes):
    gpd = pytest.importorskip("geopandas")  # noqa: F841
    p_sec, p_app, p_axe = sig if sig is not None else _sig(dossier)
    params = _params_sig(dossier, p_sec, p_app, p_axe, **changes)
    if json_nan:
        chemin = classeur(dossier, corr=corr, json_brut=_json_avec_nan(params))
    else:
        chemin = classeur(dossier, params=params, corr=corr)
    return _figer(lambda: cd.controler_geometrie(chemin))


@cas("geometrie/sain")
def _(d):
    return _geo(d)


@cas("geometrie/parametres_illisibles")
def _(d):
    return _figer(lambda: cd.controler_geometrie(
        classeur(d, json_brut="{ pas du json")))


@cas("geometrie/parametres_introuvables")
def _(d):
    return _figer(lambda: cd.controler_geometrie(classeur(d, params=None)))


@cas("geometrie/fichiers_introuvables")
def _(d):
    return _geo(d, Fichier_SHP_Sections=str(Path(d) / "nulle_part.shp"),
                Fichier_SHP_Axe=str(Path(d) / "axe_absent.shp"))


@cas("geometrie/source_invalide")
def _(d):
    return _geo(d, Source_geometrie=" raster ")


@cas("geometrie/source_none_vaut_shp")
def _(d):
    return _geo(d, Source_geometrie=None)


@cas("geometrie/source_modele_avec_shp")
def _(d):
    return _geo(d, Source_geometrie=" modele ")


@cas("geometrie/source_modele_sans_shp")
def _(d):
    return _geo(d, Source_geometrie="MODELE", Fichier_SHP_Sections="",
                Fichier_SHP_Apports=None)


@cas("geometrie/source_modele_apports_seuls")
def _(d):
    return _geo(d, Source_geometrie="MODELE", Fichier_SHP_Sections="  ")


@cas("geometrie/source_modele_fichier_introuvable")
def _(d):
    return _geo(d, Source_geometrie="MODELE",
                Fichier_SHP_Apports=str(Path(d) / "absent.shp"))


@cas("geometrie/shp_non_renseignes")
def _(d):
    return _geo(d, Fichier_SHP_Apports=_SUPPRIMER)


@cas("geometrie/shp_non_renseignes_nan")
def _(d):
    return _geo(d, json_nan=True, Fichier_SHP_Sections=float("nan"))


@cas("geometrie/champ_nom_explicite")
def _(d):
    return _geo(d, Champ_nom_SHP=" Nom ")


@cas("geometrie/champ_nom_nan")
def _(d):
    return _geo(d, json_nan=True, Champ_nom_SHP=float("nan"))


@cas("geometrie/champ_nom_vide")
def _(d):
    return _geo(d, Champ_nom_SHP="  ")


@cas("geometrie/champ_nom_inconnu")
def _(d):
    return _geo(d, Champ_nom_SHP="Code")


@cas("geometrie/lecture_shp_en_echec")
def _(d):
    import geometrie as geo

    def casser(*a, **k):
        raise OSError("shapefile corrompu")
    with mock.patch.object(geo, "lire_lignes", casser):
        return _geo(d)


@cas("geometrie/sans_axe")
def _(d):
    return _geo(d, sig=_sig(d, axe=False))


@cas("geometrie/lecture_axe_en_echec")
def _(d):
    import geometrie as geo

    def casser(*a, **k):
        raise ValueError("axe multiligne")
    with mock.patch.object(geo, "lire_axe", casser):
        return _geo(d)


@cas("geometrie/projection_differente")
def _(d):
    return _geo(d, sig=_sig(d, crs_apports="EPSG:3857"))


@cas("geometrie/apport_absent_du_shp")
def _(d):
    return _geo(d, corr=_avec(CORR, **{COL_APPORT: ["A_inexistant", "A2", "A3"]}))


@cas("geometrie/section_et_apport_absents")
def _(d):
    return _geo(d, corr=_avec(CORR, **{COL_APPORT: ["A1", "A2", "A9"],
                                      COL_SECTION: ["S0", "S2", "S3"]}))


@cas("geometrie/doublon_dans_shp")
def _(d):
    sig = _sig(d, sections=(["S1", "S2", "S2"],
                            [_transversale(x) for x in (900, 2800, 5100)]))
    return _geo(d, sig=sig, corr=_avec(CORR, **{COL_SECTION: ["S1", "S2", "S2"]}))


@cas("geometrie/sans_axe_absent_et_doublon")
def _(d):
    sig = _sig(d, axe=False,
               apports=(["A1", "A1", "A3"],
                        [_transversale(x, 250) for x in (200, 2100, 4300)]))
    return _geo(d, sig=sig)


@cas("geometrie/correspondance_illisible")
def _(d):
    sig = _sig(d)
    chemin = classeur(d, params=_params_sig(d, *sig),
                      corr=_avec(CORR, **{COL_SECTION: _SUPPRIMER}))
    return _figer(lambda: cd.controler_geometrie(chemin))


@cas("geometrie/correspondance_absente")
def _(d):
    sig = _sig(d)
    chemin = classeur(d, params=_params_sig(d, *sig), corr=None)
    return _figer(lambda: cd.controler_geometrie(chemin))


@cas("geometrie/sens_invalide")
def _(d):
    return _geo(d, Sens_axe="descendant")


@cas("geometrie/sens_none")
def _(d):
    return _geo(d, Sens_axe=None)


@cas("geometrie/sens_vide")
def _(d):
    return _geo(d, Sens_axe="  ")


@cas("geometrie/sens_absent")
def _(d):
    return _geo(d, Sens_axe=_SUPPRIMER)


@cas("geometrie/sens_aval_amont")
def _(d):
    return _geo(d, Sens_axe="aval_amont")


@cas("geometrie/pk_origine_texte")
def _(d):
    return _geo(d, PK_origine_m="douze")


@cas("geometrie/pk_origine_liste")
def _(d):
    return _geo(d, PK_origine_m=[1, 2])


@cas("geometrie/pk_origine_none")
def _(d):
    return _geo(d, PK_origine_m=None)


@cas("geometrie/pk_origine_1000")
def _(d):
    return _geo(d, PK_origine_m="1000.5")


@cas("geometrie/ordre_incoherent")
def _(d):
    return _geo(d, corr=_avec(CORR, **{COL_SECTION: ["S1", "S3", "S2"]}))


@cas("geometrie/injection_courte_garde_les_pk")
def _(d):
    from shapely.geometry import LineString
    geoms = [_transversale(x, 250) for x in (200, 2100, 4300)]
    geoms[2] = LineString([(504300, 6200000.0), (504300, 6200000.94)])
    return _geo(d, sig=_sig(d, apports=(["A1", "A2", "A3"], geoms)))


@cas("geometrie/section_ne_croise_pas_axe")
def _(d):
    geoms = [_transversale(x) for x in (900, 2800, 5100)]
    from shapely.affinity import translate
    geoms[1] = translate(_transversale(2800, 40), yoff=1000)
    return _geo(d, sig=_sig(d, sections=(["S1", "S2", "S3"], geoms)))


# ===========================================================================
# controler_contre_modele
# ===========================================================================

def _perimetre():
    from shapely.geometry import box
    return box(0, 0, 1000, 1000)


def _lignes(noms, geoms, types_=None, colonne="Name"):
    import geopandas as gpd
    donnees = {colonne: noms} if colonne else {}
    if types_ is not None:
        donnees["Type"] = types_
    return gpd.GeoDataFrame(donnees, geometry=geoms, crs=CRS)


def _sections_ok(noms=("S1", "S2", "S3")):
    from shapely.geometry import LineString
    return _lignes(list(noms), [LineString([(100, 200 + 200 * i), (900, 200 + 200 * i)])
                                for i in range(len(noms))])


def _bc_ok(noms=("A1", "A2", "A3"), types_=None, ecart=1.0, colonne="Name"):
    """Conditions limites EXTERNES le long du bord gauche, a « ecart » m."""
    from shapely.geometry import LineString
    geoms = [LineString([(-ecart, 100 + 250 * i), (-ecart, 200 + 250 * i)])
             for i in range(len(noms))]
    return _lignes(list(noms), geoms,
                   types_=types_ if types_ is not None else ["External"] * len(noms),
                   colonne=colonne)


def _zones(noms=("Zone2D",), colonne=True):
    import geopandas as gpd
    from shapely.geometry import box
    geoms = [box(0, 0, 1000, 1000)] + [box(2000 + 1000 * i, 0, 2500 + 1000 * i, 500)
                                       for i in range(len(noms) - 1)]
    d = {"mesh_name": list(noms)} if colonne else {}
    return gpd.GeoDataFrame(d, geometry=geoms, crs=CRS)


_DEFAUT = object()


def _modele(d, params=None, corr=CORR, json_nan=False, hdf_fourni=False,
            zones_presentes=("Zone2D",), bc=_DEFAUT, refs=_DEFAUT,
            mesh=_DEFAUT, mesh_exc=None, maille=1.0, texte=None,
            creer_hdf=True, nom_hdf="Essai.g01.hdf"):
    """
    controler_contre_modele sur un faux modele.

    bc / refs / mesh : ce que rendent HdfBndry.get_bc_lines,
    get_reference_lines et HdfMesh.get_mesh_areas ; maille : taille de maille
    (None = illisible) ; texte : objets du fichier .gXX ({"apports": [...],
    "sections": [...]}, None = pas de fichier texte).
    """
    pytest.importorskip("geopandas")
    import geometrie as geo

    bc = _bc_ok() if bc is _DEFAUT else bc
    refs = _sections_ok() if refs is _DEFAUT else refs
    mesh = _zones() if mesh is _DEFAUT else mesh

    hdf = Path(d) / nom_hdf
    if creer_hdf:
        hdf.write_bytes(b"")
    if texte is not None:
        hdf.with_suffix("").write_text("", encoding="utf-8")
    valeurs = params if params is not None else _avec(
        PARAMS, Dossier_projet_HECRAS=str(d), Geometrie_reference="g01")
    if json_nan:
        chemin = classeur(d, corr=corr, json_brut=_json_avec_nan(valeurs))
    else:
        chemin = classeur(d, params=valeurs, corr=corr)

    class HdfBndry:
        @staticmethod
        def get_bc_lines(h):
            return bc

        @staticmethod
        def get_reference_lines(h):
            return refs

    class HdfMesh:
        @staticmethod
        def get_mesh_areas(h):
            if mesh_exc is not None:
                raise mesh_exc
            return mesh

    faux = types.ModuleType("ras_commander")
    faux.HdfBndry, faux.HdfMesh = HdfBndry, HdfMesh

    def taille_maille(h, zone=None, geometrie=None, nb_voisines=25):
        if maille is None:
            raise KeyError("Cells Center Coordinate")
        return maille

    def objets_depuis_texte(f):
        return {"apports": [{"nom": n} for n in texte.get("apports", [])],
                "sections": [{"nom": n} for n in texte.get("sections", [])]}

    with ExitStack() as pile:
        pile.enter_context(mock.patch.dict(sys.modules, {"ras_commander": faux}))
        pile.enter_context(mock.patch.object(
            geo, "zones_2d", lambda h: list(zones_presentes)))
        pile.enter_context(mock.patch.object(geo, "taille_maille", taille_maille))
        pile.enter_context(mock.patch.object(
            geo, "objets_depuis_texte", objets_depuis_texte))
        if hdf_fourni:
            return _figer(lambda: cd.controler_contre_modele(chemin, hdf))
        return _figer(lambda: cd.controler_contre_modele(chemin))


@cas("modele/sain")
def _(d):
    return _modele(d)


@cas("modele/hdf_fourni_parametres_vides")
def _(d):
    return _modele(d, params={}, hdf_fourni=True)


@cas("modele/parametres_manquants")
def _(d):
    return _modele(d, params=_avec(PARAMS, Dossier_projet_HECRAS="  ",
                                   Geometrie_reference=_SUPPRIMER))


@cas("modele/parametres_manquants_nan")
def _(d):
    return _modele(d, json_nan=True,
                   params=_avec(PARAMS, Dossier_projet_HECRAS=str(d),
                                Geometrie_reference=float("nan")))


@cas("modele/hdf_introuvable")
def _(d):
    return _modele(d, params=_avec(PARAMS, Dossier_projet_HECRAS=str(d),
                                   Geometrie_reference="g02"))


@cas("modele/geometrie_sans_g")
def _(d):
    return _modele(d, params=_avec(PARAMS, Dossier_projet_HECRAS=str(d),
                                   Geometrie_reference="1"))


@cas("modele/geometrie_avec_point")
def _(d):
    return _modele(d, params=_avec(PARAMS, Dossier_projet_HECRAS=str(d),
                                   Geometrie_reference=".g01"))


@cas("modele/zone_absente")
def _(d):
    return _modele(d, zones_presentes=("Perimeter 1", "Perimeter 2"),
                   mesh=_zones(("Perimeter 1", "Perimeter 2")))


@cas("modele/zone_non_renseignee_plusieurs")
def _(d):
    return _modele(d, params=_avec(PARAMS, Dossier_projet_HECRAS=str(d),
                                   Geometrie_reference="g01", Nom_zone_2D=None),
                   zones_presentes=("Z1", "Z2"), mesh=_zones(("Z1", "Z2")))


@cas("modele/zone_non_renseignee_une")
def _(d):
    return _modele(d, params=_avec(PARAMS, Dossier_projet_HECRAS=str(d),
                                   Geometrie_reference="g01", Nom_zone_2D=" "))


@cas("modele/zone_nan_plusieurs")
def _(d):
    return _modele(d, json_nan=True,
                   params=_avec(PARAMS, Dossier_projet_HECRAS=str(d),
                                Geometrie_reference="g01",
                                Nom_zone_2D=float("nan")),
                   zones_presentes=("Z1", "Z2"), mesh=_zones(("Z1", "Z2")))


@cas("modele/multi_zones_filtre")
def _(d):
    return _modele(d, zones_presentes=("Zone2D", "Autre"),
                   mesh=_zones(("Zone2D", "Autre")))


@cas("modele/noms_absents")
def _(d):
    return _modele(d, bc=_bc_ok(("A1", "A3", "X9")), refs=None)


@cas("modele/references_vides")
def _(d):
    return _modele(d, refs=_sections_ok(()))


@cas("modele/bc_sans_colonne_nom")
def _(d):
    return _modele(d, bc=_bc_ok(colonne=None))


@cas("modele/bc_none")
def _(d):
    return _modele(d, bc=None)


@cas("modele/bc_sans_type")
def _(d):
    from shapely.geometry import LineString
    return _modele(d, bc=_lignes(["A1", "A2", "A3"],
                                 [LineString([(-500, 0), (-500, 10)])] * 3))


@cas("modele/bc_internes_seulement")
def _(d):
    return _modele(d, bc=_bc_ok(types_=["Internal", " internal ", "SA/2D"], ecart=300))


@cas("modele/bc_externes_casse_et_blancs")
def _(d):
    return _modele(d, bc=_bc_ok(types_=[" EXTERNAL", "external ", "Internal"], ecart=50))


@cas("modele/bc_externes_sans_nom")
def _(d):
    return _modele(d, bc=_bc_ok(colonne=None, ecart=50))


@cas("modele/texte_en_attente")
def _(d):
    return _modele(d, bc=_bc_ok(("A1", "A2")), refs=_sections_ok(("S1",)),
                   texte={"apports": ["A3", "A_libre"], "sections": ["S2", "S3", "S1"]})


@cas("modele/texte_rien_de_nouveau")
def _(d):
    return _modele(d, texte={"apports": ["A1"], "sections": []})


@cas("modele/mesh_illisible")
def _(d):
    return _modele(d, mesh_exc=RuntimeError("groupe HDF absent"))


@cas("modele/mesh_none")
def _(d):
    return _modele(d, mesh=None)


@cas("modele/mesh_vide")
def _(d):
    return _modele(d, mesh=_zones(("Zone2D",)).iloc[0:0])


@cas("modele/mesh_zone_introuvable")
def _(d):
    return _modele(d, zones_presentes=("Zone2D",), mesh=_zones(("Autre",)))


@cas("modele/mesh_sans_colonne_nom")
def _(d):
    return _modele(d, mesh=_zones(("Zone2D",), colonne=False))


@cas("modele/maille_illisible")
def _(d):
    return _modele(d, maille=None, bc=_bc_ok(ecart=12.5))


@cas("modele/maille_illisible_bc_sur_perimetre")
def _(d):
    return _modele(d, maille=None, bc=_bc_ok(ecart=0.0))


@cas("modele/bc_trop_loin")
def _(d):
    return _modele(d, maille=2.0, bc=_bc_ok(ecart=7.0))


@cas("modele/sections_hors_maillage")
def _(d):
    from shapely.geometry import LineString
    refs = _lignes(["S1", "S2", "S3"],
                   [LineString([(100, 200), (900, 200)]),
                    LineString([(700, 400), (1100, 400)]),     # 75 % dedans
                    LineString([(800, 600), (1800, 600)])])    # 20 % dedans
    return _modele(d, refs=refs)


@cas("modele/correspondance_sans_section")
def _(d):
    return _modele(d, corr=_avec(CORR, **{COL_SECTION: _SUPPRIMER}))


@cas("modele/combinaison")
def _(d):
    return _modele(d, zones_presentes=("Z1", "Z2"), mesh=_zones(("Z1", "Z2")),
                   bc=_bc_ok(("A1", "A2"), ecart=40), refs=None,
                   texte={"apports": ["A3"], "sections": ["S1"]}, maille=None)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def executer(nom, dossier):
    return _neutraliser(CAS[nom](dossier), dossier)


def _lire_reference():
    with REFERENCE.open(encoding="utf-8") as f:
        return json.load(f)


def test_reference_couvre_tous_les_cas():
    """Un cas ajoute sans figer la reference, ou retire en la laissant : refus."""
    assert sorted(_lire_reference()["cas"]) == sorted(CAS)


@pytest.mark.parametrize("nom", sorted(CAS))
def test_sortie_identique_a_la_reference(nom, tmp_path):
    attendu = _lire_reference()["cas"][nom]
    obtenu = json.loads(json.dumps(executer(nom, tmp_path), ensure_ascii=False))
    assert obtenu == attendu


def figer_reference():
    resultats = {}
    for nom in sorted(CAS):
        with tempfile.TemporaryDirectory() as d:
            resultats[nom] = executer(nom, Path(d))
    contenu = {
        "_a_propos": (
            "Caracterisation de controler_template, controler_geometrie et "
            "controler_contre_modele (src/test_controle_donnees.py). NE PAS "
            "MODIFIER A LA MAIN : « python src/test_controle_donnees.py "
            "--figer-reference » le reecrit quand le changement de "
            "comportement est VOULU."),
        "cas": resultats,
    }
    REFERENCE.write_text(json.dumps(contenu, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    print(f"{len(resultats)} cas figes dans {REFERENCE.name}")


if __name__ == "__main__":
    if "--figer-reference" in sys.argv:
        figer_reference()
    else:
        sys.exit(pytest.main([__file__, "-q"]))
