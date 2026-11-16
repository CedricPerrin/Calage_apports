"""
Reference lines videes du .gXX.hdf en cours de calage (13/11/2026, HEC-RAS
7.0.2) : reparation par la date du .gXX, terrain, regroupement des messages.

    python -m pytest src/test_reparation_trace.py
"""
import os
import sys
import time
from pathlib import Path

import pytest

h5py = pytest.importorskip("h5py")
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pilote_hecras as ph  # noqa: E402

TEXTE = "".join(f"Reference Line Name={n}\nReference Line Arc= 2 \n"
                for n in ("S1", "S2"))


def _hdf(chemin, noms, points_par_ligne, terrain=None):
    with h5py.File(chemin, "w") as h:
        geo = h.create_group("Geometry")
        if terrain:
            geo.attrs["Terrain Filename"] = np.bytes_(terrain)
        g = geo.create_group("Reference Lines")
        g.create_dataset("Attributes", data=np.array(
            [(n.encode(),) for n in noms], dtype=[("Name", "S8")]))
        info, debut = [], 0
        for n in points_par_ligne:
            info.append((debut, n, 0, 1 if n else 0))
            debut += n
        g.create_dataset("Polyline Info", data=np.array(info, dtype="i4"))
        g.create_dataset("Polyline Points",
                         data=np.zeros((debut, 2)) if debut else np.zeros((0, 0)))


@pytest.fixture
def modele(tmp_path):
    g = tmp_path / "M.g01"
    g.write_text(TEXTE, encoding="cp1252")
    return g


def _hdf_plus_recent(g):
    t = time.time()
    os.utime(g, (t - 3600, t - 3600))
    os.utime(g.with_name(g.name + ".hdf"), (t, t))


def test_lignes_sans_trace_reparees(modele):
    _hdf(modele.with_name("M.g01.hdf"), ["S1", "S2"], [0, 0])
    _hdf_plus_recent(modele)
    assert ph.lignes_reference_sans_trace(modele) == ["S1", "S2"]
    assert not ph.pretraitement_perime(modele)
    assert ph.reparer_trace_reference(modele) == ["S1", "S2"]
    assert ph.pretraitement_perime(modele)
    assert modele.read_text(encoding="cp1252") == TEXTE
    assert ph.reparer_trace_reference(modele) == []


def test_lignes_tracees_intactes(modele):
    _hdf(modele.with_name("M.g01.hdf"), ["S1", "S2"], [3, 4])
    _hdf_plus_recent(modele)
    assert ph.reparer_trace_reference(modele) == []
    assert not ph.pretraitement_perime(modele)


def test_ligne_absente_du_texte_pas_masquee(modele):
    _hdf(modele.with_name("M.g01.hdf"), ["S1", "S3"], [3, 0])
    _hdf_plus_recent(modele)
    assert ph.reparer_trace_reference(modele) == []
    assert not ph.pretraitement_perime(modele)


def test_terrain_lu_depuis_le_hdf(modele):
    (modele.parent / "Terrain").mkdir()
    terrain = modele.parent / "Terrain" / "T.hdf"
    terrain.write_bytes(b"x")
    _hdf(modele.with_name("M.g01.hdf"), ["S1"], [3], terrain=r".\Terrain\T.hdf")
    lu = ph.terrain_de_geometrie(modele)
    assert lu is not None and lu[0].name == "T.hdf"
    assert abs(lu[1] - terrain.stat().st_mtime) < 1e-6


def test_messages_regroupes():
    lignes = [f"Reference line SUH0{i} is not a valid polyline."
              for i in (4, 1, 3, 6, 7, 8, 9)]
    lignes += ["Error Processing Geometry", "Computations Summary"]
    r = ph._regrouper_lignes_invalides(lignes)
    assert len(r) == 3 and r[0].startswith("7 reference line(s)")
    assert "SUH04" in r[0] and "SUH09" in r[0]
    assert ph._regrouper_lignes_invalides(["a", "b"]) == ["a", "b"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
