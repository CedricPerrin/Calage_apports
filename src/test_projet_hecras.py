"""Lecture d'un projet HEC-RAS par le noyau du plugin, sans QGIS ni chaîne."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calage_apports import noyau

# HEC-RAS écrit en cp1252 : le tiret long (0x97) et « œ » (0x9C) n'existent que là.
TITRE = "Crue décennale — état aménagé, bœuf"


def _ecrire_projet(dossier, nom, titre="Essai", version="6.60"):
    """Un projet minimal, écrit comme HEC-RAS l'écrit : cp1252 et CRLF."""
    def ecrire(suffixe, *lignes):
        (dossier / f"{nom}.{suffixe}").write_bytes(
            "".join(f"{ligne}\r\n" for ligne in lignes).encode("cp1252"))

    ecrire("prj", f"Proj Title={titre}", "Geom File=g01", "Unsteady File=u01",
           "Plan File=p01")
    ecrire("g01", f"Geom Title={titre}", f"Program Version={version}")
    ecrire("u01", f"Flow Title={titre}", f"Program Version={version}")
    ecrire("p01", f"Plan Title={titre}", f"Program Version={version}",
           "Geom File=g01", "Flow File=u01")
    return dossier / f"{nom}.prj"


def test_un_titre_cp1252_se_lit_juste(tmp_path):
    # latin1 passait avant cp1252 : il lit tout octet, cp1252 n'était jamais
    # atteint, et « — » revenait en caractère de contrôle (audit du 11/10/2026).
    prj = _ecrire_projet(tmp_path, "Essai", TITRE)
    info = noyau.lister_projet_hecras(prj.parent)
    assert [info["plans"][0]["titre"], info["geometries"][0]["titre"],
            info["unsteady"][0]["titre"]] == [TITRE] * 3


def test_le_projet_lu_est_le_prj_designe(tmp_path):
    # Deux projets dans un dossier. On chargeait le premier .prj de projet du
    # dossier, « Aval_ancien » ici, et la version la plus récente de tous ses
    # fichiers, projets confondus (audit du 11/10/2026).
    _ecrire_projet(tmp_path, "Aval_ancien", version="7.01")
    choisi = _ecrire_projet(tmp_path, "Projet_choisi", version="6.60")
    assert noyau.lister_projet_hecras(choisi)["nom_projet"] == "Projet_choisi"
    assert noyau.version_hecras_du_projet(choisi) == ("6.6", {"6.60": 3})


def test_un_dossier_a_deux_projets_est_refuse(tmp_path):
    # Le dossier reste accepté, mais seulement s'il ne porte qu'un projet :
    # deviner lequel est voulu, c'est le défaut corrigé ci-dessus.
    _ecrire_projet(tmp_path, "Aval_ancien")
    _ecrire_projet(tmp_path, "Projet_choisi")
    with pytest.raises(ValueError, match="Projet_choisi"):
        noyau.lister_projet_hecras(tmp_path)
