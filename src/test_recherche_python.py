"""Sondes bornées et arrêt entre interpréteurs, sans dépendance QGIS."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calage_apports import noyau


def test_recherche_progression_priorite_et_annulation(monkeypatch):
    chemins = [Path('/qgis/python'), Path('/independant/python')]
    appels, journal = [], []
    monkeypatch.setattr(noyau, '_emplacements_python', lambda: chemins)

    def verifier(chemin):
        appels.append(chemin)
        return (3, 12, 1)

    monkeypatch.setattr(noyau, '_python_utilisable', verifier)
    resultat = noyau.pythons_candidats(journal.append)
    assert [r['chemin'] for r in resultat] == chemins[::-1]
    assert len(journal) == 2 and all(str(p) in m for p, m in zip(chemins, journal))
    appels.clear()
    assert noyau.pythons_candidats(annule=lambda: bool(appels)) == []
    assert appels == chemins[:1]  # aucune seconde sonde après l'annulation
