"""
Defauts mineurs releves pendant le remaniement du 10/11/2026 et corriges le
11/11/2026 : ce que le code DOIT faire dans chaque cas.

criteres.diagnostiquer
  - une alerte bloquante ne figure qu'UNE fois dans les alertes (celle du
    decalage qui excede la fenetre y figurait deux fois) ;
  - une forme non calculable parce que la serie porte des valeurs manquantes
    le DIT, au lieu d'annoncer une « serie constante » ;
  - un axe des temps qui n'est pas croissant est NOMME, au lieu de passer pour
    des fenetres qui « ne se recouvrent pas » ;
  - une serie vide, des longueurs qui ne s'accordent pas ou un pas de
    recalage nul levent une ValueError LISIBLE (c'etait IndexError, ou une
    erreur de numpy sans rapport avec la cause).
calage.caler
  - des listes d'apports, de sections et de cibles de longueurs differentes
    sont refusees AVANT tout calcul (elles etaient tronquees en silence).
pilote_hecras
  - un nom de reference line ecrit en cp1252 dans le .gNN.hdf est lu, au lieu
    de perdre son accent.
noyau.importer_hydrogrammes
  - un fichier qui n'est pas un Excel est refuse par une phrase, comme sa
    docstring le promet (c'etait zipfile.BadZipFile).

    python -m pytest src/test_defauts_mineurs.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(SRC.parent / "calage_apports"))

import calage  # noqa: E402
import criteres  # noqa: E402

T = np.arange(0.0, 24.01, 0.1)


def crue(t, pointe=100.0, montee=8.0):
    x = np.clip(t, 0.0, None) / montee
    return 5.0 + (pointe - 5.0) * x ** 3 * np.exp(3.0 * (1.0 - x))


Q = crue(T)


# --- criteres.diagnostiquer ---------------------------------------------------

def test_une_alerte_bloquante_ne_figure_qu_une_fois():
    """Un decalage de 11 h pour une fenetre jugee de 10,3 h : la crue de la
    cible culmine a 14 h, celle du calcul a 3 h."""
    t = np.linspace(0.0, 40.0, 401)

    def bosse(centre, largeur):
        return 5.0 + 95.0 / (1.0 + ((t - centre) / largeur) ** 2)

    d = criteres.diagnostiquer(t, bosse(14.0, 2.5), t, bosse(3.0, 1.0),
                               fenetre=(0.0, 10.3), decalage_fenetre_h=-11.0)

    decalage = [a for a in d.alertes if "excede la fenetre jugee" in a]
    assert len(decalage) == 1, d.alertes
    assert decalage[0] in d.alertes_bloquantes
    assert len(d.alertes) == len(set(d.alertes)), "une alerte est en double"
    # les bloquantes restent en queue des alertes
    assert d.alertes[-len(d.alertes_bloquantes):] == d.alertes_bloquantes


@pytest.mark.parametrize("trou_dans, attendu", [
    ("calcul", "valeurs manquantes dans le calcul"),
    ("cible", "valeurs manquantes dans la cible"),
])
def test_des_valeurs_manquantes_ne_passent_pas_pour_une_serie_constante(
        trou_dans, attendu):
    troue = Q.copy()
    troue[50] = np.nan
    cible, calcul = (troue, Q) if trou_dans == "cible" else (Q, troue)

    d = criteres.diagnostiquer(T, cible, T, calcul)

    forme = [a for a in d.alertes if a.startswith("forme non calculable")]
    assert forme == [f"forme non calculable ({attendu})"], d.alertes
    assert not d.converge


def test_une_serie_vraiment_constante_garde_son_message():
    d = criteres.diagnostiquer(T, Q, T, np.full_like(T, 7.0))

    assert "forme non calculable (serie constante)" in d.alertes


@pytest.mark.parametrize("serie, nom", [("cible", "de la cible"),
                                        ("calcul", "du calcul")])
def test_un_axe_des_temps_decroissant_est_nomme(serie, nom):
    a_l_envers = (T[::-1], Q[::-1])
    cible, calcul = ((a_l_envers, (T, Q)) if serie == "cible"
                     else ((T, Q), a_l_envers))

    d = criteres.diagnostiquer(*cible, *calcul)

    assert not d.converge
    dites = [a for a in d.alertes_bloquantes if "croissant" in a]
    assert len(dites) == 1 and nom in dites[0], d.alertes
    assert not any("ne se recouvrent" in a for a in d.alertes), (
        "le motif annonce n'est pas le bon : les fenetres se recouvrent")


@pytest.mark.parametrize("cas, arguments, mots", [
    ("cible vide", ([], [], T, Q), ("cible", "vide")),
    ("calcul vide", (T, Q, [], []), ("calcul", "vide")),
    ("cible : instants et debits", (T, Q[:-3], T, Q), ("cible", "241", "238")),
    ("calcul : instants et debits", (T, Q, T[:-1], Q), ("calcul", "240", "241")),
])
def test_une_entree_inexploitable_est_refusee_par_une_phrase(cas, arguments,
                                                             mots):
    with pytest.raises(ValueError) as erreur:
        criteres.diagnostiquer(*arguments)

    for mot in mots:
        assert mot in str(erreur.value), (cas, str(erreur.value))


@pytest.mark.parametrize("pas", [0, 0.0, -0.1, float("nan")])
def test_un_pas_de_recalage_nul_ou_negatif_est_refuse(pas):
    with pytest.raises(ValueError) as erreur:
        criteres.diagnostiquer(T, Q, T, Q, pas_h=pas)

    assert "pas de recalage" in str(erreur.value)


# --- calage.caler --------------------------------------------------------------

@pytest.mark.parametrize("apports, sections, nb_cibles", [
    (["A1", "A2"], ["S1"], 2),
    (["A1"], ["S1", "S2"], 2),
    (["A1", "A2"], ["S1", "S2"], 1),
])
def test_des_listes_de_longueurs_differentes_sont_refusees_avant_tout_calcul(
        apports, sections, nb_cibles):
    modele = calage.ModeleFictif(["A1", "A2"], ["S1", "S2"], T, [Q, 0.5 * Q])
    cibles = [(T, Q)] * nb_cibles

    with pytest.raises(ValueError) as erreur:
        calage.caler(modele, apports, sections, cibles,
                     journal=lambda *a, **k: None)

    texte = str(erreur.value)
    assert str(len(apports)) in texte and str(len(sections)) in texte
    assert str(nb_cibles) in texte
    assert modele.nb_calculs == 0, "un calcul a ete lance avant le refus"


# --- pilote_hecras ------------------------------------------------------------

@pytest.mark.parametrize("encodage", ["cp1252", "utf-8"])
def test_un_nom_de_reference_line_accentue_est_lu_sans_perdre_son_accent(
        tmp_path, encodage):
    h5py = pytest.importorskip("h5py")
    import pilote_hecras

    geometrie = tmp_path / "Essai.g01"
    geometrie.write_text("Geom Title=Essai\n", encoding="cp1252")
    noms = ["Pont de Béhobie", "S_Aval"]
    with h5py.File(str(geometrie) + ".hdf", "w") as h:
        groupe = h.create_group("Geometry/Reference Lines")
        attributs = np.array([(n.encode(encodage),) for n in noms],
                             dtype=[("Name", "S40")])
        groupe.create_dataset("Attributes", data=attributs)
        # Aucun point : toutes les lignes sont « sans trace », donc nommees.
        groupe.create_dataset("Polyline Info",
                              data=np.zeros((2, 4), dtype="i4"))
        groupe.create_dataset("Polyline Points",
                              data=np.zeros((0, 2), dtype="f8"))

    assert pilote_hecras.lignes_reference_sans_trace(geometrie) == noms


# --- livrables.synthese -------------------------------------------------------

def _note(monkeypatch, version):
    import livrables

    monkeypatch.setattr(livrables, "_version_ras_commander", lambda: version)
    diagnostic = criteres.diagnostiquer(T, Q, T, Q)
    return livrables.synthese("Essai", ["S1"], [diagnostic])


def test_la_note_cite_la_version_de_ras_commander_qui_a_tourne(monkeypatch):
    note = _note(monkeypatch, "0.117.0")

    assert "**ras-commander v0.117.0**" in note
    assert "0.99.1" not in note, "l'ancienne version en dur est restee"


def test_sans_version_connue_la_note_ne_l_invente_pas(monkeypatch):
    note = _note(monkeypatch, None)

    assert "**ras-commander**" in note
    assert "ras-commander v" not in note


def test_la_version_citee_est_celle_de_l_interpreteur():
    import livrables
    from importlib import metadata

    try:
        attendue = metadata.version("ras-commander")
    except metadata.PackageNotFoundError:
        attendue = None

    assert livrables._version_ras_commander() == attendue


# --- noyau.importer_hydrogrammes ----------------------------------------------

def _excel_des_objectifs(chemin):
    import openpyxl

    classeur = openpyxl.Workbook()
    feuille = classeur.active
    feuille.title = "Correspondance"
    feuille.append(["Nom_Apport (BC line)", "Nom_Section (reference line)",
                    "Pente_m_par_m"])
    feuille.append(["A1", "S1", None])
    feuille = classeur.create_sheet("Cibles")
    feuille.append(["Temps_h", "Cible_S1"])
    for t, q in ((0.0, 1.0), (1.0, 2.0)):
        feuille.append([t, q])
    classeur.save(chemin)
    return chemin


@pytest.mark.parametrize("contenu", [
    b"Temps_h;Cible_S1\n0;1\n1;2\n",                   # un .csv renomme
    b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 64,  # un .xls renomme
    b"",                                               # un fichier vide
])
def test_un_fichier_qui_n_est_pas_un_excel_est_refuse_par_une_phrase(
        tmp_path, contenu):
    pytest.importorskip("openpyxl")
    import noyau

    cible = _excel_des_objectifs(tmp_path / "donnees_calage.xlsx")
    avant = cible.read_bytes()
    source = tmp_path / "precedent.xlsx"
    source.write_bytes(contenu)

    with pytest.raises(ValueError) as erreur:
        noyau.importer_hydrogrammes(source, cible)

    assert "precedent.xlsx" in str(erreur.value)
    assert "Excel" in str(erreur.value)
    assert cible.read_bytes() == avant, "l'Excel du calcul a ete touche"
    assert not list(tmp_path.glob("*.precedent.xlsx"))
