"""
PK d'une section qui coupe l'axe plusieurs fois (constat C2, decision de Cedric
du 21/11/2026, « PK du croisement central, avec alerte ») : le PK retenu est
celui du croisement le plus proche du MILIEU de la section ; la section est
signalee « coupe l'axe N fois », avec les PK possibles ; le calage n'est pas
bloque (un AVERTISSEMENT, jamais une ERREUR). Sans geopandas : un DataFrame
pandas a colonne « geometry » suffit a calculer_pk.
"""
import sys
from pathlib import Path

import pandas as pd
from shapely.geometry import LineString

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controle_donnees as cd  # noqa: E402
import geometrie as geo  # noqa: E402

AXE = LineString([(0, 0), (1000, 0)])
# Meandre : croise l'axe en x = 200, 500 et 800 ; milieu de la section en x = 500.
MEANDRE = LineString([(200, -10), (200, 10), (500, 10), (500, -10), (800, -10), (800, 10)])
DROITE = LineString([(300, -10), (300, 10)])


def _lignes():
    return pd.DataFrame({"nom": ["S1", "S2"], "geometry": [MEANDRE, DROITE]})


def test_le_pk_retenu_est_celui_du_croisement_central():
    r = geo.calculer_pk(_lignes(), AXE)
    assert r["pk_m"].tolist() == [500.0, 300.0]
    assert r["nb_croisements"].tolist() == [3, 1]


def test_les_pk_possibles_suivent_le_sens_et_l_origine():
    r = geo.calculer_pk(_lignes(), AXE, pk_origine=100.0, sens="aval_amont")
    assert r["pk_m"].tolist() == [600.0, 800.0]         # 1000 - s + 100
    assert r["pk_croisements"].iloc[0] == "300 ; 600 ; 900"


def test_le_controle_signale_la_section_sans_bloquer(monkeypatch):
    anomalies = cd._signaler_croisements(geo.calculer_pk(_lignes(), AXE))
    assert len(anomalies) == 1
    niveau, message = anomalies[0]
    assert niveau == cd.AVERTISSEMENT
    assert "S1" in message and "3 fois" in message and "200" in message
