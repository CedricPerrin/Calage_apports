"""
Bilan de masse non lu (constat D3, decision de Cedric du 21/11/2026,
« Accepter, mais le dire ») : quand la LECTURE du bilan echoue (exception),
l'essai reste accepte comme avant, mais le resultat du calcul porte la cause,
et le suivi et le journal disent « bilan de masse non lu : essai non controle ».
Une colonne absente sans erreur (NaN) et un bilan lu ne changent pas.
"""
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calage as cg  # noqa: E402
import pilote_hecras  # noqa: E402
import suivi as sv  # noqa: E402


def _pilote_bouchonne(monkeypatch, tmp_path, comptes):
    """Un pilote dont le calcul « reussit » et dont les comptes de volume sont `comptes`."""
    class Comptes:
        @staticmethod
        def get_volume_accounting(_hdf):
            if isinstance(comptes, Exception):
                raise comptes
            return comptes

    rc = types.ModuleType("ras_commander")
    rc.HdfResultsPlan = Comptes
    def calculer_plan(*a, **k):
        (tmp_path / "P.p01.hdf").write_bytes(b"xx")   # reecrit : mtime change
        return True

    rc.RasCmdr = SimpleNamespace(compute_plan=calculer_plan)
    rc.RasPlan = SimpleNamespace()
    bco = types.ModuleType("ras_commander.RasBco")
    bco.BcoMonitor = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "ras_commander", rc)
    monkeypatch.setitem(sys.modules, "ras_commander.RasBco", bco)

    hdf = tmp_path / "P.p01.hdf"
    hdf.write_bytes(b"x")
    import os
    os.utime(hdf, ns=(1, 1))
    p = pilote_hecras.PiloteHecRas.__new__(pilote_hecras.PiloteHecRas)
    p.dossier, p.nom_projet, p.plan_travail = tmp_path, "P", "01"
    p.hdf_resultats, p.fermer_orphelins, p.coeurs, p.version = hdf, False, 0, "6.4.1"
    p.nb_calculs = 0
    monkeypatch.setattr(p, "_manques_avant_calcul", lambda: [], raising=False)
    monkeypatch.setattr(p, "_surveiller_geometrie", lambda m: None, raising=False)
    monkeypatch.setattr(p, "_par_ras_commander", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(p, "_fermer_orphelins", lambda a: None, raising=False)
    monkeypatch.setattr(pilote_hecras, "par_controleur", lambda v: False)
    monkeypatch.setattr(pilote_hecras, "plan_detourne", lambda *a: None)
    monkeypatch.setattr(pilote_hecras, "_series_absentes", lambda h: "")
    monkeypatch.setattr(pilote_hecras, "_erreur_ecriture_geometrie", lambda h: "")
    return p


def test_une_lecture_du_bilan_qui_echoue_dit_sa_cause(monkeypatch, tmp_path):
    p = _pilote_bouchonne(monkeypatch, tmp_path, KeyError("Error Percent"))
    r = p.calculer()
    assert r.reussi and np.isnan(r.bilan_masse_pct)   # toujours accepte
    assert "Error Percent" in r.bilan_non_lu
    assert cg.qualite_acceptable(r, SimpleNamespace(bilan_masse_max_pct=1.0))[0]


def test_un_bilan_lu_ne_porte_aucune_cause(monkeypatch, tmp_path):
    import pandas as pd
    comptes = pd.DataFrame({"Error Percent": [0.01]})
    p = _pilote_bouchonne(monkeypatch, tmp_path, comptes)
    monkeypatch.setattr(pilote_hecras, "bilan_masse_depuis_comptes", lambda c: 0.01)
    r = p.calculer()
    assert r.bilan_masse_pct == 0.01 and r.bilan_non_lu == ""


def test_le_suivi_et_le_journal_disent_bilan_non_lu(tmp_path):
    calcul = cg.ResultatCalcul(reussi=True, bilan_non_lu="KeyError: 'Error Percent'")
    dit = []
    s = sv.Suivi.__new__(sv.Suivi)
    s.bilan_masse = None
    s._ecrire_etat = lambda: None
    cg._noter_bilan(s, calcul, SimpleNamespace(bilan_masse_max_pct=1.0), dit.append)
    assert s.bilan_masse["non_lu"] == "KeyError: 'Error Percent'"
    assert any("bilan de masse non lu : essai non contrôlé" in m
               and "Error Percent" in m for m in dit)
