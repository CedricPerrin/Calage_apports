"""
Ce que pont_hecras.lire_serie_hdf DOIT faire devant un nom accentue et devant
une unite de temps autre que le jour.

Deux defauts corriges le 11/11/2026 :

  - NOMS. Les noms du jeu « Name » etaient decodes en UTF-8 strict. Un seul
    nom ecrit en cp1252 (l'encodage de HEC-RAS : « Pont de l'Eglise » avec son
    accent) faisait lever UnicodeDecodeError AVANT tout appariement : plus
    AUCUNE section du fichier n'etait lisible, y compris celles sans accent.
    Regle de la maison, la meme que pour les fichiers texte de HEC-RAS
    (pilote_hecras._lire_texte) : UTF-8 strict, puis cp1252, puis latin-1.

  - TEMPS. Toute unite qui ne commencait pas par « day » etait lue comme des
    HEURES : des minutes ou des secondes donnaient un axe des temps faux d'un
    facteur 60 ou 3600, sans message. Les unites connues sont maintenant
    converties, et une unite inconnue est REFUSEE avec son nom, plutot que
    devinee.

Les .hdf sont FABRIQUES avec h5py, sur la structure que la fonction parcourt.
Ils ne prouvent pas que HEC-RAS ecrit ainsi : a verifier sur un vrai .pNN.hdf.

    python -m pytest src/test_lecture_hdf.py -q
"""
import sys
from pathlib import Path

import numpy as np
import pytest

h5py = pytest.importorskip("h5py")

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

import pont_hecras as pont  # noqa: E402

SERIES = pont.CHEMIN_SERIES_HDF
DEBIT = np.concatenate([np.linspace(10, 100, 7), np.linspace(90, 20, 6)])
ACCENT = "Pont de l'Église"


def _hdf(chemin, noms, temps, unite=b"days"):
    """Resultats « Reference Lines » : une colonne de debit par nom."""
    flow = np.column_stack([(i + 1) * DEBIT for i in range(len(noms))])
    with h5py.File(chemin, "w") as h:
        groupe = h.require_group(f"{SERIES}/Reference Lines")
        groupe.create_dataset("Name", data=np.array(noms))
        groupe.create_dataset("Flow", data=flow)
        jeu = h.create_dataset(f"{SERIES}/Time", data=temps)
        if unite is not None:
            jeu.attrs["Time"] = unite
    return chemin


JOURS = np.linspace(0.0, 0.5, 13)                # 12 h, pas de 1 h


# --- noms -------------------------------------------------------------------

def test_un_nom_en_cp1252_ne_rend_pas_les_autres_sections_illisibles(tmp_path):
    f = _hdf(tmp_path / "r.hdf",
             [f"{ACCENT}|Zone".encode("cp1252"), b"B|Zone"], JOURS)

    serie = pont.lire_serie_hdf(f, "B")

    assert serie.attrs["objet"] == "B|Zone"
    assert np.allclose(serie["debit_m3s"], 2 * DEBIT)


def test_une_section_au_nom_accentue_en_cp1252_est_trouvee(tmp_path):
    f = _hdf(tmp_path / "r.hdf",
             [f"{ACCENT}|Zone".encode("cp1252"), b"B|Zone"], JOURS)

    serie = pont.lire_serie_hdf(f, ACCENT)

    assert serie.attrs["objet"] == f"{ACCENT}|Zone"
    assert np.allclose(serie["debit_m3s"], DEBIT)


def test_une_section_au_nom_accentue_en_utf8_reste_trouvee(tmp_path):
    f = _hdf(tmp_path / "r.hdf",
             [f"{ACCENT}|Zone".encode("utf-8"), b"B|Zone"], JOURS)

    serie = pont.lire_serie_hdf(f, ACCENT)

    assert serie.attrs["objet"] == f"{ACCENT}|Zone"


def test_un_octet_que_cp1252_ne_definit_pas_ne_bloque_pas_la_lecture(tmp_path):
    # 0x81 n'existe ni en UTF-8 (seul) ni en cp1252 : latin-1 le lit.
    f = _hdf(tmp_path / "r.hdf", [b"A\x81|Zone", b"B|Zone"], JOURS)

    serie = pont.lire_serie_hdf(f, "B")

    assert serie.attrs["objet"] == "B|Zone"


# --- temps ------------------------------------------------------------------

@pytest.mark.parametrize("unite, pas, attendu_h", [
    (b"days", 1 / 24, 1.0),
    (b"DAYS", 1 / 24, 1.0),
    ("days", 1 / 24, 1.0),
    (b"Hours", 1.0, 1.0),
    (b"hrs", 1.0, 1.0),
    (b"minutes", 60.0, 1.0),
    (b"Minutes", 6.0, 0.1),
    (b"seconds", 3600.0, 1.0),
    (b"sec", 360.0, 0.1),
])
def test_l_unite_de_temps_est_convertie_en_heures(tmp_path, unite, pas,
                                                  attendu_h):
    f = _hdf(tmp_path / "r.hdf", [b"B|Zone"], np.arange(13.0) * pas, unite)

    serie = pont.lire_serie_hdf(f, "B")

    assert np.allclose(np.diff(serie["temps"]), attendu_h), (
        f"unite {unite!r} : pas lu {np.diff(serie['temps'])[0]} h, "
        f"attendu {attendu_h} h.")
    assert serie["temps"].iloc[0] == 0.0


def test_sans_attribut_le_temps_est_en_jours(tmp_path):
    f = _hdf(tmp_path / "r.hdf", [b"B|Zone"], JOURS, unite=None)

    serie = pont.lire_serie_hdf(f, "B")

    assert np.allclose(np.diff(serie["temps"]), 1.0)


def test_une_unite_de_temps_inconnue_est_refusee_avec_son_nom(tmp_path):
    f = _hdf(tmp_path / "r.hdf", [b"B|Zone"], JOURS, unite=b"fortnights")

    with pytest.raises(ValueError) as erreur:
        pont.lire_serie_hdf(f, "B")

    assert "fortnights" in str(erreur.value)
