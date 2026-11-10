"""
Caracterisation des deux fonctions de classeur de calage_apports/noyau.py :
preparer_classeur et importer_hydrogrammes.

Ce sont les deux voies par lesquelles une saisie de l'ingenieur peut etre
perdue ou abimee (README : 0.6.4, 0.6.5, 0.9.12, 0.9.16). CE TEST NE DIT PAS
CE QU'ELLES DEVRAIENT FAIRE : il enregistre ce qu'elles FONT — valeur rendue,
exception, et l'ETAT DU DOSSIER apres l'appel (fichiers presents, contenu des
classeurs cellule par cellule avec type, format et style, JSON des
parametres, fichiers restes intacts, octets et date) — dans une reference
versionnee, et refuse toute difference. Filet tendu AVANT de decouper ces
deux fonctions (10/11/2026).

    python -m pytest src/test_noyau_classeur.py -q

QUAND UN CHANGEMENT EST VOULU : « python src/test_noyau_classeur.py
--figer-reference » reecrit reference_noyau_classeur.json.

DOUBLURE : la mise en forme de preparer_classeur (style_classeur.mettre_en_
forme, module de la chaine) est remplacee par un enregistreur qui note
l'appel et L'ETAT DU DOSSIER A CET INSTANT — c'est ce qui epingle l'ordre des
ecritures. Ainsi le classeur fige est celui que noyau.py ecrit lui-meme, et
la reference ne bouge pas quand style_classeur evolue. Deux cas emploient la
vraie mise en forme, pour l'import sur un classeur habille.

NEUTRALISE : le dossier temporaire (« <TMP> »). Les dates de creation et de
modification qu'openpyxl ecrit dans docProps ne sont pas lues.
"""
import datetime as _dt
import hashlib
import json
import sys
import tempfile
import types
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest import mock

import openpyxl
import pytest

SRC = Path(__file__).resolve().parent
RACINE = SRC.parent
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(RACINE / "calage_apports"))

import noyau  # noqa: E402

REFERENCE = SRC / "reference_noyau_classeur.json"

COL_A = "Nom_Apport (BC line)"
COL_S = "Nom_Section (reference line)"

# ---------------------------------------------------------------------------
# Etat d'un dossier, sous une forme comparable
# ---------------------------------------------------------------------------


def _valeur(v):
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time, _dt.timedelta)):
        return [type(v).__name__, str(v)]
    return [type(v).__name__, v]


def _style(c):
    bord = c.border.left.style if c.border is not None else None
    remplissage = (c.fill.fgColor.rgb if c.fill is not None and c.fill.fill_type
                   else None)
    return [c.number_format, bool(c.font.b), c.font.color.rgb
            if c.font.color is not None and c.font.color.type == "rgb" else None,
            c.alignment.horizontal, bord, remplissage]


def _classeur(chemin):
    wb = openpyxl.load_workbook(chemin)
    feuilles = []
    for ws in wb.worksheets:
        cellules = []
        for ligne in ws.iter_rows():
            for c in ligne:
                st = _style(c)
                if c.value is None and st == ["General", False, None, None,
                                              None, None]:
                    continue
                cellules.append([c.coordinate, *_valeur(c.value), st])
        largeurs = {k: d.width for k, d in sorted(ws.column_dimensions.items())
                    if d.customWidth}
        feuilles.append({
            "nom": ws.title,
            "dimensions": ws.dimensions,
            "cellules": cellules,
            "largeurs": largeurs,
            "figees": ws.freeze_panes,
            "filtre": ws.auto_filter.ref,
            "fusions": sorted(str(r) for r in ws.merged_cells.ranges),
            "graphiques": len(ws._charts),
            "validations": len(ws.data_validations.dataValidation),
            "mises_en_forme_conditionnelles": len(ws.conditional_formatting),
        })
    return {"active": wb.active.title if wb.active is not None else None,
            "feuilles": feuilles}


def _contenu(chemin):
    if chemin.suffix == ".xlsx":
        try:
            return {"xlsx": _classeur(chemin)}
        except Exception as e:  # noqa: BLE001
            return {"illisible": type(e).__name__, "octets": chemin.stat().st_size}
    if chemin.suffix == ".json":
        return {"json": json.loads(chemin.read_text(encoding="utf-8"))}
    return {"octets": chemin.stat().st_size}


def _empreintes(dossier):
    """Octets ET date de modification : un fichier reecrit a l'identique
    dans la meme seconde n'est pas « intact » pour autant."""
    return {str(p.relative_to(dossier)): (hashlib.sha256(p.read_bytes()).hexdigest(),
                                          p.stat().st_mtime_ns)
            for p in sorted(Path(dossier).rglob("*")) if p.is_file()}


def _etat(dossier):
    return {str(p.relative_to(dossier)): _contenu(p)
            for p in sorted(Path(dossier).rglob("*")) if p.is_file()}


def _liste(dossier):
    return sorted(str(p.relative_to(dossier)) for p in Path(dossier).rglob("*")
                  if p.is_file())


def _rendu(r):
    if isinstance(r, Path):
        return ["Path", str(r)]
    return [type(r).__name__, r]


def observer(dossier, appel):
    """Appelle, puis rend : resultat ou exception, et l'etat du dossier."""
    avant = _empreintes(dossier)
    try:
        sortie = {"rendu": _rendu(appel())}
    except Exception as e:  # noqa: BLE001 - l'exception fait partie du contrat
        sortie = {"exception": type(e).__name__, "message": str(e)}
    apres = _empreintes(dossier)
    sortie["intacts"] = sorted(f for f in avant
                                            if apres.get(f) == avant[f])
    sortie["dossier"] = _etat(dossier)
    return sortie


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
            return {nettoyer(k): nettoyer(x) for k, x in o.items()}
        return o

    return nettoyer(objet)


# ---------------------------------------------------------------------------
# Doublure de la mise en forme
# ---------------------------------------------------------------------------

@contextmanager
def style_double(dossier, journal, mode="enregistrer"):
    """
    mode : « enregistrer » (note l'appel et le dossier a cet instant),
    « lever » (la mise en forme echoue), « absent » (import impossible),
    « reel » (la vraie mise en forme de la chaine).
    """
    if mode == "reel":
        yield
        return
    if mode == "absent":
        with mock.patch.dict(sys.modules, {"style_classeur": None}):
            yield
        return
    faux = types.ModuleType("style_classeur")

    def mettre_en_forme(chemin):
        journal.append({"appel": "mettre_en_forme",
                        "chemin": str(chemin),
                        "dossier_a_cet_instant": _liste(dossier)})
        if mode == "lever":
            raise RuntimeError("openpyxl fache")

    faux.mettre_en_forme = mettre_en_forme
    with mock.patch.dict(sys.modules, {"style_classeur": faux}):
        yield


# ---------------------------------------------------------------------------
# Fabrication des classeurs
# ---------------------------------------------------------------------------

def excel(chemin, feuilles):
    """feuilles : {nom: [ligne, ...]} ecrites telles quelles, dans l'ordre."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nom, lignes in feuilles.items():
        ws = wb.create_sheet(nom)
        for ligne in lignes:
            ws.append(list(ligne))
    chemin.parent.mkdir(parents=True, exist_ok=True)
    wb.save(chemin)
    return chemin


def correspondance(paires, pentes=None, avec_pente=True):
    entete = ["Ordre", COL_A, COL_S, "Nom_Cible"] + (["Pente_m_par_m"]
                                                     if avec_pente else [])
    lignes = [entete]
    for rang, (a, s) in enumerate(paires, 1):
        ligne = [rang, a, s, f"Cible_{s}"]
        if avec_pente:
            ligne.append((pentes or {}).get(a))
        lignes.append(ligne)
    return lignes


def cibles(colonnes):
    """{en-tete: valeurs} -> lignes (colonnes de meme longueur)."""
    entetes = list(colonnes)
    return [entetes] + [list(l) for l in zip(*colonnes.values())]


PAIRES = [("A1", "S1"), ("A2", "S2"), ("A3", "S3")]
SHP = {"sections": "D:/calage/sections.shp", "apports": "D:/calage/apports.shp",
       "axe": "D:/calage/axe.shp"}
SAISIE = {"Temps_h": [0.0, 0.5, 1.0, 1.5],
          "Cible_S1": [1.0, 4.0, 2.5, 1.0],
          "Cible_S2": [2.0, 8.0, None, 2.0],
          "Cible_S3": [3.0, 12.0, 7.5, 3.0]}


CAS = {}


def cas(nom):
    def enregistrer(f):
        assert nom not in CAS, nom
        CAS[nom] = f
        return f
    return enregistrer


# ===========================================================================
# preparer_classeur
# ===========================================================================

def preparer(d, paires=PAIRES, chemins=SHP, parametres=None, pentes=None,
             style="enregistrer", sous_dossier="sortie", patchs=()):
    journal = []
    sortie = Path(d) / sous_dossier
    with ExitStack() as pile:
        pile.enter_context(style_double(d, journal, style))
        for p in patchs:
            pile.enter_context(p)
        r = observer(d, lambda: noyau.preparer_classeur(
            sortie, paires, chemins, parametres=parametres, pentes=pentes))
    r["journal_style"] = journal
    return r


def composer_avant(d, paires=PAIRES, parametres=None, pentes=None):
    """Un classeur deja compose (mise en forme doublee, donc non habille)."""
    with style_double(d, []):
        return noyau.preparer_classeur(Path(d) / "sortie", paires, SHP,
                                       parametres=parametres, pentes=pentes)


def saisir(chemin, colonnes, pentes=None):
    """L'ingenieur colle ses hydrogrammes et saisit des pentes."""
    wb = openpyxl.load_workbook(chemin)
    ws = wb["Cibles"]
    entetes = [c.value for c in ws[1]]
    for nom, valeurs in colonnes.items():
        col = entetes.index(nom) + 1
        for i, v in enumerate(valeurs):
            ws.cell(row=i + 2, column=col, value=v)
    if pentes:
        wc = wb["Correspondance"]
        tete = [c.value for c in wc[1]]
        ca, cp = tete.index(COL_A) + 1, tete.index("Pente_m_par_m") + 1
        for ligne in range(2, wc.max_row + 1):
            nom = wc.cell(row=ligne, column=ca).value
            if nom in pentes:
                wc.cell(row=ligne, column=cp, value=pentes[nom])
    wb.save(chemin)


@cas("preparer/absent_dossier_cree")
def _(d):
    return preparer(d, sous_dossier="a/b/sortie")


@cas("preparer/absent_chemins_shp_vides")
def _(d):
    return preparer(d, chemins={})


@cas("preparer/parametres_et_prefixe")
def _(d):
    return preparer(d, parametres={"Prefixe_scenario": " Q100 V2/bis- ",
                                   "Nom_projet": "Gave", "Version_HECRAS": "6.4.1",
                                   "Simulation_debut": "01JAN2020,00:00",
                                   "Cle_inconnue": 3})


@cas("preparer/parametres_prefixe_none")
def _(d):
    return preparer(d, parametres={"Prefixe_scenario": None})


@cas("preparer/parametres_vides")
def _(d):
    return preparer(d, parametres={})


@cas("preparer/pentes_deduites")
def _(d):
    return preparer(d, pentes={"A1": 0.0123, "A3": 0, 7: 0.5, "A9": 0.1})


@cas("preparer/paires_vides")
def _(d):
    return preparer(d, paires=[])


@cas("preparer/paires_non_textuelles")
def _(d):
    return preparer(d, paires=[(1, 10), (2.5, None)], pentes={"1": 0.01})


@cas("preparer/noms_accentues")
def _(d):
    return preparer(d, paires=[("Apport_Lées", "Pont d'Orthez"),
                               ("Affluent_Œ", "Gué")],
                    pentes={"Apport_Lées": 0.002})


@cas("preparer/deja_saisi_preserve")
def _(d):
    chemin = composer_avant(d, pentes={"A2": 0.004})
    saisir(chemin, SAISIE, pentes={"A1": 0.01, "A3": "0,02"})
    return preparer(d, pentes={"A1": 0.9, "A2": 0.9, "A3": 0.9})


@cas("preparer/sections_ajoutees_retirees_renommees")
def _(d):
    chemin = composer_avant(d)
    saisir(chemin, SAISIE, pentes={"A1": 0.01, "A2": 0.02, "A3": 0.03})
    # S2 retiree, S3 renommee S3b (meme apport), S4 ajoutee, ordre change.
    return preparer(d, paires=[("A3", "S3b"), ("A4", "S4"), ("A1", "S1")])


@cas("preparer/pente_blanche_cede_a_la_deduite")
def _(d):
    chemin = composer_avant(d)
    saisir(chemin, {}, pentes={"A1": "  ", "A2": 0.0, "A3": "x"})
    return preparer(d, pentes={"A1": 0.5, "A2": 0.5})


@cas("preparer/refus_sans_temps_h")
def _(d):
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Correspondance": correspondance(PAIRES[:2]),
        "Cibles": [["\u00b6", "Cible_S1", "Cible_S2"]]
                  + [[None, 10.0 + i, 20.0 + i] for i in range(6)]})
    return preparer(d, paires=PAIRES[:2])


@cas("preparer/refus_ligne_1_supprimee")
def _(d):
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Cibles": [[0.0, 10.0, 20.0]]
                  + [[0.25 * i, 10.0 + i, 20.0 + i] for i in range(1, 6)]})
    return preparer(d, paires=PAIRES[:2])


@cas("preparer/refus_beaucoup_d_entetes")
def _(d):
    entetes = ["t"] + [f"Q{i}" for i in range(15)]
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Cibles": [entetes, [1.0] * 16]})
    return preparer(d, paires=PAIRES)


@cas("preparer/sans_temps_h_zone_vide_ecrase")
def _(d):
    # Seul l'apercu, au-dela de la zone de saisie, porte des valeurs.
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Cibles": [["x", "a", "b", "Q pic"], [None, None, None, 5.0],
                   [None, None, None, 6.0]]})
    return preparer(d, paires=PAIRES[:2])


@cas("preparer/ancien_classeur_feuille_parametres")
def _(d):
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Parametres": [["Parametre", "Valeur"], ["Nom_projet", "Ancien"],
                       ["Tolerance_pic_pct", 2.0]],
        "Correspondance": correspondance(PAIRES, pentes={"A2": 0.03}),
        "Cibles": cibles(SAISIE)})
    return preparer(d)


@cas("preparer/feuille_ajoutee_a_la_main")
def _(d):
    chemin = composer_avant(d)
    saisir(chemin, SAISIE)
    wb = openpyxl.load_workbook(chemin)
    wb.create_sheet("Mes notes").append(["a verifier", 42])
    wb.save(chemin)
    return preparer(d)


@cas("preparer/precedent_deja_present_remplace")
def _(d):
    chemin = composer_avant(d)
    excel(chemin.with_name("donnees_calage.precedent.xlsx"),
          {"Vieux": [["tres ancien"]]})
    return preparer(d)


@cas("preparer/changement_de_prefixe")
def _(d):
    chemin = composer_avant(d, parametres={"Prefixe_scenario": "Q100"})
    saisir(chemin, SAISIE)
    return preparer(d, parametres={"Prefixe_scenario": "Q10"})


@cas("preparer/meme_prefixe_ecrit_autrement")
def _(d):
    chemin = composer_avant(d, parametres={"Prefixe_scenario": "Q100"})
    saisir(chemin, SAISIE)
    return preparer(d, parametres={"Prefixe_scenario": "Q100-"})


@cas("preparer/existant_sans_feuille_cibles")
def _(d):
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Correspondance": correspondance(PAIRES, pentes={"A1": 0.07})})
    return preparer(d)


@cas("preparer/existant_sans_correspondance")
def _(d):
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {"Cibles": cibles(SAISIE)})
    return preparer(d, pentes={"A1": 0.5})


@cas("preparer/existant_pente_sans_colonne_apport")
def _(d):
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Correspondance": [["Ordre", COL_S, "Pente_m_par_m"], [1, "S1", 0.01]],
        "Cibles": cibles(SAISIE)})
    return preparer(d)


@cas("preparer/existant_sans_colonne_pente")
def _(d):
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Correspondance": correspondance(PAIRES, avec_pente=False),
        "Cibles": cibles(SAISIE)})
    return preparer(d, pentes={"A2": 0.2})


@cas("preparer/existant_illisible")
def _(d):
    p = Path(d) / "sortie" / "donnees_calage.xlsx"
    p.parent.mkdir(parents=True)
    p.write_text("pas un classeur", encoding="utf-8")
    return preparer(d)


@cas("preparer/cibles_dates_et_apercu")
def _(d):
    t0 = _dt.datetime(2020, 1, 1)
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Correspondance": correspondance(PAIRES),
        "Cibles": [["Temps_h", "Cible_S1", "Cible_S2", None, "Q pic (m³/s)"],
                   [t0, 1.0, 2.0, None, "Cible_S1"],
                   [t0 + _dt.timedelta(hours=1), 3.0, "texte", None, 3.0]]})
    return preparer(d)


@cas("preparer/verrouille_renommage_refuse")
def _(d):
    chemin = composer_avant(d)
    saisir(chemin, SAISIE)

    def refuser(self, cible):
        raise PermissionError("[WinError 32] fichier ouvert dans Excel")
    return preparer(d, patchs=[mock.patch.object(Path, "replace", refuser)])


@cas("preparer/ecriture_impossible")
def _(d):
    chemin = composer_avant(d)
    saisir(chemin, SAISIE)
    import pandas as pd

    def refuser(*a, **k):
        raise PermissionError("disque plein")
    return preparer(d, patchs=[mock.patch.object(pd, "ExcelWriter", refuser)])


@cas("preparer/mise_en_forme_en_echec")
def _(d):
    return preparer(d, style="lever")


@cas("preparer/mise_en_forme_absente")
def _(d):
    return preparer(d, style="absent")


# ===========================================================================
# importer_hydrogrammes
# ===========================================================================

def importer(d, source, cible, patchs=()):
    with ExitStack() as pile:
        for p in patchs:
            pile.enter_context(p)
        return observer(d, lambda: noyau.importer_hydrogrammes(source, cible))


def deux_excels(d, src_paires, src_cibles, dst_paires=PAIRES, dst_cibles=None,
                src_pentes=None, dst_pentes=None):
    d = Path(d)
    if dst_cibles is None:
        dst_cibles = {"Temps_h": [], **{f"Cible_{s}": [] for _, s in dst_paires}}
    src = excel(d / "precedent" / "donnees_calage_Q100.xlsx", {
        "Correspondance": correspondance(src_paires, src_pentes),
        "Cibles": cibles(src_cibles)})
    dst = excel(d / "ce_calcul" / "donnees_calage.xlsx", {
        "Correspondance": correspondance(dst_paires, dst_pentes),
        "Cibles": cibles(dst_cibles)})
    return src, dst


SRC_CIBLES = {"Temps_h": [0.0, 1.0, 2.0], "Cible_S1": [1.0, 2.0, 3.0],
              "Cible_S2": [4.0, 5.0, 6.0], "Cible_S9": [7.0, 8.0, 9.0]}
SRC_PAIRES = [("A1", "S1"), ("A2", "S2"), ("A9", "S9")]


@cas("importer/nominal")
def _(d):
    src, dst = deux_excels(d, SRC_PAIRES, SRC_CIBLES, src_pentes={"A1": 0.02})
    return importer(d, src, dst)


@cas("importer/meme_fichier")
def _(d):
    _, dst = deux_excels(d, SRC_PAIRES, SRC_CIBLES)
    return importer(d, Path(d) / "ce_calcul" / "." / "donnees_calage.xlsx", dst)


@cas("importer/source_absente")
def _(d):
    _, dst = deux_excels(d, SRC_PAIRES, SRC_CIBLES)
    return importer(d, Path(d) / "absent.xlsx", dst)


@cas("importer/source_pas_excel")
def _(d):
    _, dst = deux_excels(d, SRC_PAIRES, SRC_CIBLES)
    p = Path(d) / "faux.xlsx"
    p.write_text("rien", encoding="utf-8")
    return importer(d, p, dst)


@cas("importer/source_sans_cibles")
def _(d):
    _, dst = deux_excels(d, SRC_PAIRES, SRC_CIBLES)
    src = excel(Path(d) / "s.xlsx", {"Correspondance": correspondance(SRC_PAIRES)})
    return importer(d, src, dst)


@cas("importer/cible_sans_aucune_feuille_attendue")
def _(d):
    src, _ = deux_excels(d, SRC_PAIRES, SRC_CIBLES)
    dst = excel(Path(d) / "c.xlsx", {"Autre": [["x"]]})
    return importer(d, src, dst)


@cas("importer/source_sans_temps_h")
def _(d):
    src, dst = deux_excels(d, SRC_PAIRES,
                           {"t": [0.0, 1.0], "Cible_S1": [1.0, 2.0]})
    return importer(d, src, dst)


@cas("importer/cible_sans_temps_h")
def _(d):
    src, dst = deux_excels(d, SRC_PAIRES, SRC_CIBLES,
                           dst_cibles={"Cible_S1": [], "t": []})
    return importer(d, src, dst)


@cas("importer/aucune_commune")
def _(d):
    src, dst = deux_excels(d, [("A9", "S9")],
                           {"Temps_h": [0.0, 1.0], "Cible_S9": [7.0, 8.0]})
    return importer(d, src, dst)


@cas("importer/aucune_renseignee")
def _(d):
    src, dst = deux_excels(d, [("A1", "S1")],
                           {"Temps_h": [0.0, 1.0], "Cible_S1": [None, ""]})
    return importer(d, src, dst)


@cas("importer/partiel_gardee_meme_base")
def _(d):
    src, dst = deux_excels(
        d, [("A1", "S1")], {"Temps_h": [0.0, 1.0, 2.0], "Cible_S1": [1.0, 2.0, 3.0]},
        dst_cibles={"Temps_h": [0.0, 1.0, 2.0], "Cible_S1": [9.0, 9.0, 9.0],
                    "Cible_S2": [None, None, None], "Cible_S3": [5.0, None, 6.0]})
    return importer(d, src, dst)


@cas("importer/refus_une_gardee_autre_base")
def _(d):
    src, dst = deux_excels(
        d, [("A1", "S1")], {"Temps_h": [0.0, 1.0, 2.0], "Cible_S1": [1.0, 2.0, 3.0]},
        dst_cibles={"Temps_h": [0.0, 0.5], "Cible_S1": [None, None],
                    "Cible_S2": [None, None], "Cible_S3": [3.0, 4.0]})
    return importer(d, src, dst)


@cas("importer/refus_deux_gardees_autre_base")
def _(d):
    src, dst = deux_excels(
        d, [("A1", "S1")], {"Temps_h": [0.0, 1.0, 2.0], "Cible_S1": [1.0, 2.0, 3.0]},
        dst_cibles={"Temps_h": [0.0, 1.0, 3.0], "Cible_S1": [None] * 3,
                    "Cible_S2": [1.0, None, None], "Cible_S3": [3.0, 4.0, 5.0]})
    return importer(d, src, dst)


@cas("importer/cible_plus_longue_videe_dessous")
def _(d):
    src, dst = deux_excels(
        d, SRC_PAIRES, SRC_CIBLES,
        dst_cibles={"Temps_h": [0.0, 1.0, 2.0, 3.0, 4.0],
                    "Cible_S1": [5.0] * 5, "Cible_S2": [None] * 5,
                    "Cible_S3": [None] * 5})
    return importer(d, src, dst)


@cas("importer/source_plus_longue")
def _(d):
    src, dst = deux_excels(
        d, [("A1", "S1")], {"Temps_h": [float(i) for i in range(8)],
                            "Cible_S1": [float(i * i) for i in range(8)]},
        dst_cibles={"Temps_h": [0.0], "Cible_S1": [None], "Cible_S2": [None],
                    "Cible_S3": [None]})
    return importer(d, src, dst)


@cas("importer/fin_vide_et_trous")
def _(d):
    src, dst = deux_excels(
        d, [("A1", "S1")], {"Temps_h": [0.0, 1.0, 2.0, None, ""],
                            "Cible_S1": [1.0, None, 3.0, "", None]})
    return importer(d, src, dst)


@cas("importer/colonnes_apres_entete_vide_ignorees")
def _(d):
    src = excel(Path(d) / "s.xlsx", {
        "Correspondance": correspondance(SRC_PAIRES),
        "Cibles": [["Temps_h", " Cible_S1 ", None, "Cible_S2"],
                   [0.0, 1.0, None, 4.0], [1.0, 2.0, None, 5.0]]})
    dst = excel(Path(d) / "c.xlsx", {
        "Correspondance": correspondance(PAIRES),
        "Cibles": [["Temps_h", "Cible_S1", "Cible_S2", "", "Cible_S3", "Q pic"],
                   [None, None, None, None, 1.0, 2.0]]})
    return importer(d, src, dst)


@cas("importer/formules_de_la_source")
def _(d):
    src, dst = deux_excels(d, [("A1", "S1")],
                           {"Temps_h": [0.0, 1.0], "Cible_S1": [1.0, "=A2*2"]})
    return importer(d, src, dst)


@cas("importer/pentes_noms_et_valeurs")
def _(d):
    src = excel(Path(d) / "s.xlsx", {
        "Correspondance": [["Ordre", COL_A, COL_S, "Nom_Cible", "Pente_m_par_m"],
                           [1, " A1 ", "S1", "Cible_S1", 0.01],
                           [2, "A2", "S2", "Cible_S2", None],
                           [3, None, "S3", "Cible_S3", 0.5],
                           [4, 7, "S7", "Cible_S7", 0.07],
                           [5, "A3", "S3", "Cible_S3", ""],
                           [6, "A1", "S1", "Cible_S1", 0.02]],
        "Cibles": cibles(SRC_CIBLES)})
    dst = excel(Path(d) / "c.xlsx", {
        "Correspondance": [["Ordre", COL_A, COL_S, "Nom_Cible", "Pente_m_par_m"],
                           [1, "A1", "S1", "Cible_S1", 0.9],
                           [2, "A2 ", "S2", "Cible_S2", 0.8],
                           [3, None, "S3", "Cible_S3", None],
                           [4, "7", "S7", "Cible_S7", None]],
        "Cibles": cibles({"Temps_h": [], "Cible_S1": []})})
    return importer(d, src, dst)


@cas("importer/pentes_colonne_absente_source")
def _(d):
    src = excel(Path(d) / "s.xlsx", {
        "Correspondance": correspondance(SRC_PAIRES, avec_pente=False),
        "Cibles": cibles(SRC_CIBLES)})
    _, dst = deux_excels(d, SRC_PAIRES, SRC_CIBLES)
    return importer(d, src, dst)


@cas("importer/pentes_colonne_absente_cible")
def _(d):
    src, _ = deux_excels(d, SRC_PAIRES, SRC_CIBLES, src_pentes={"A1": 0.02})
    dst = excel(Path(d) / "c.xlsx", {
        "Correspondance": correspondance(PAIRES, avec_pente=False),
        "Cibles": cibles({"Temps_h": [], "Cible_S1": []})})
    return importer(d, src, dst)


@cas("importer/noms_accentues")
def _(d):
    src, dst = deux_excels(
        d, [("Lées", "Gué")], {"Temps_h": [0.0, 1.0], "Cible_Gué": [1.5, 2.5]},
        dst_paires=[("Lées", "Gué"), ("Œ", "Pont d'Orthez")],
        src_pentes={"Lées": 0.003})
    return importer(d, src, dst)


@cas("importer/precedent_deja_present_remplace")
def _(d):
    src, dst = deux_excels(d, SRC_PAIRES, SRC_CIBLES)
    excel(dst.with_name("donnees_calage.precedent.xlsx"), {"Vieux": [["v"]]})
    return importer(d, src, dst)


@cas("importer/verrouille_enregistrement_refuse")
def _(d):
    src, dst = deux_excels(d, SRC_PAIRES, SRC_CIBLES)

    def refuser(self, chemin):
        raise PermissionError("[Errno 13] fichier ouvert dans Excel")
    return importer(d, src, dst,
                    patchs=[mock.patch.object(openpyxl.Workbook, "save", refuser)])


@cas("importer/sur_classeur_habille")
def _(d):
    # La vraie mise en forme : styles, graphique et tableau des pics doivent
    # survivre a l'import, qui ecrit SUR PLACE.
    d = Path(d)
    with style_double(d, [], "reel"):
        dst = noyau.preparer_classeur(d / "ce_calcul", PAIRES, SHP,
                                      pentes={"A3": 0.001})
    src = excel(d / "s.xlsx", {"Correspondance": correspondance(SRC_PAIRES,
                                                                {"A2": 0.02}),
                               "Cibles": cibles(SRC_CIBLES)})
    return importer(d, src, dst)


@cas("preparer/recomposer_un_classeur_habille")
def _(d):
    d = Path(d)
    with style_double(d, [], "reel"):
        chemin = noyau.preparer_classeur(d / "sortie", PAIRES, SHP)
    saisir(chemin, SAISIE, pentes={"A1": 0.01})
    return preparer(d)


# ===========================================================================
# Cas ajoutes le 11/11/2026 : chacun ferme une faute injectee que les 57
# premiers laissaient passer (methode : une faute a la fois sur chaque
# condition, borne, strip, indice ou valeur par defaut des deux fonctions et
# de leurs etapes). La faute fermee est nommee en tete de chaque cas.
# ===========================================================================

@cas("importer/pente_nom_avec_espaces_sans_homonyme")
def _(d):
    # Ferme : « .strip() » retire sur le nom d'apport LU DANS LA SOURCE, et
    # celui retire sur le nom d'apport DE CE CALCUL. Aucun homonyme propre
    # plus bas ne masque l'effet (ce que faisait pentes_noms_et_valeurs).
    src = excel(Path(d) / "s.xlsx", {
        "Correspondance": [["Ordre", COL_A, COL_S, "Nom_Cible", "Pente_m_par_m"],
                           [1, " A5 ", "S5", "Cible_S5", 0.05],
                           [2, "A3", "S3", "Cible_S3", 0.03]],
        "Cibles": cibles({"Temps_h": [0.0, 1.0], "Cible_S1": [1.0, 2.0]})})
    dst = excel(Path(d) / "c.xlsx", {
        "Correspondance": [["Ordre", COL_A, COL_S, "Nom_Cible", "Pente_m_par_m"],
                           [1, "A5", "S5", "Cible_S5", None],
                           [2, " A3 ", "S3", "Cible_S3", None]],
        "Cibles": cibles({"Temps_h": [], "Cible_S1": []})})
    return importer(d, src, dst)


@cas("importer/entete_blanc_arrete_les_colonnes")
def _(d):
    # Ferme : un en-tete fait de BLANCS n'arretait plus la lecture des
    # colonnes, et la cible situee au-dela (dans l'apercu) etait importee.
    src = excel(Path(d) / "s.xlsx", {
        "Correspondance": correspondance(PAIRES),
        "Cibles": cibles({"Temps_h": [0.0, 1.0], "Cible_S1": [1.0, 2.0],
                          "Cible_S2": [3.0, 4.0]})})
    dst = excel(Path(d) / "c.xlsx", {
        "Correspondance": correspondance(PAIRES),
        "Cibles": [["Temps_h", "Cible_S1", "   ", "Cible_S2"]]})
    return importer(d, src, dst)


@cas("importer/colonne_de_travail_non_cible")
def _(d):
    # Ferme : « attendues » sans le filtre « Cible_ » — une colonne de
    # travail de ce calcul serait comptee comme une cible restee vide.
    src, dst = deux_excels(
        d, [("A1", "S1")], {"Temps_h": [0.0, 1.0], "Cible_S1": [1.0, 2.0]},
        dst_cibles={"Temps_h": [], "Cible_S1": [], "Notes": []})
    return importer(d, src, dst)


@cas("preparer/pente_vide_cede_a_la_deduite")
def _(d):
    # Ferme : « pd.notna » retire — une case de pente VIDE du classeur
    # precedent (NaN) passait pour une saisie et masquait la pente deduite.
    composer_avant(d)
    return preparer(d, pentes={"A2": 0.5})


@cas("preparer/cle_de_pente_deduite_numerique")
def _(d):
    # Ferme : les cles de « pentes » plus converties en texte — un apport
    # au nom numerique perdait sa pente deduite.
    return preparer(d, paires=[(7, "S7"), ("A8", "S8")],
                    pentes={7: 0.3, "A8": 0.4})


@cas("preparer/refus_saisie_dans_la_derniere_cible_seule")
def _(d):
    # Ferme : zone de saisie retrecie d'une colonne — une saisie portee par
    # la DERNIERE colonne de cible seule n'empechait plus l'ecrasement.
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Cibles": [["x", "Cible_S1", "Cible_S2"], [None, None, 4.0],
                   [None, None, 5.0]]})
    return preparer(d, paires=PAIRES[:2])


@cas("preparer/refus_une_seule_valeur")
def _(d):
    # Ferme : seuil du garde-fou porte de « > 0 » a « > 1 » — une seule
    # valeur saisie est deja une saisie a ne pas perdre.
    excel(Path(d) / "sortie" / "donnees_calage.xlsx", {
        "Cibles": [["x", "Cible_S1", "Cible_S2"], [None, 4.0, None]]})
    return preparer(d, paires=PAIRES[:2])


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def executer(nom, dossier):
    sortie = CAS[nom](dossier)
    return json.loads(json.dumps(_neutraliser(sortie, dossier), ensure_ascii=False))


def _lire_reference():
    with REFERENCE.open(encoding="utf-8") as f:
        return json.load(f)


def test_reference_couvre_tous_les_cas():
    assert sorted(_lire_reference()["cas"]) == sorted(CAS)


@pytest.mark.parametrize("nom", sorted(CAS))
def test_sortie_identique_a_la_reference(nom, tmp_path):
    assert executer(nom, tmp_path) == _lire_reference()["cas"][nom]


def figer_reference():
    resultats = {}
    for nom in sorted(CAS):
        with tempfile.TemporaryDirectory() as d:
            resultats[nom] = executer(nom, Path(d))
    REFERENCE.write_text(json.dumps({
        "_a_propos": (
            "Caracterisation de preparer_classeur et importer_hydrogrammes "
            "(src/test_noyau_classeur.py). NE PAS MODIFIER A LA MAIN : "
            "« python src/test_noyau_classeur.py --figer-reference » le "
            "reecrit quand le changement de comportement est VOULU."),
        "cas": resultats}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(resultats)} cas figes dans {REFERENCE.name}")


if __name__ == "__main__":
    if "--figer-reference" in sys.argv:
        figer_reference()
    else:
        sys.exit(pytest.main([__file__, "-q"]))
