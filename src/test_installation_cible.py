"""Le dossier annoncé à l'utilisateur reste la cible du worker différé."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calage_apports import noyau


def test_la_cible_confirmee_ne_suit_pas_un_changement_de_configuration(monkeypatch, tmp_path):
    cible = tmp_path / "confirmee"
    interpreteur = cible / "bin/python"
    interpreteur.parent.mkdir(parents=True)
    interpreteur.touch()
    monkeypatch.setattr(noyau, "emplacement_venv_hecras", lambda: tmp_path / "autre")
    monkeypatch.setattr(noyau, "modules_manquants", lambda _: [])
    monkeypatch.setattr(noyau, "verifier_interpreteur", lambda *a, **k: (True, "vérifié"))
    appels = []
    def lancer(commande, **options):
        appels.append(commande)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(noyau.subprocess, "run", lancer)
    chemin, message = noyau.installer_interpreteur(sys.executable, cible=cible)
    assert chemin == interpreteur
    assert appels[0][0] == str(interpreteur)
    assert appels[0][1:4] == ["-m", "pip", "install"]
    assert not (tmp_path / "autre").exists()
