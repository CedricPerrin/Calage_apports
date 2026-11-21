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


def test_a_egale_distance_du_milieu_le_pk_ne_depend_pas_du_sens_de_dessin():
    # Section en U : croise l'axe en x = 200 et x = 800, a egale distance de son milieu.
    u = LineString([(200, -10), (200, 10), (800, 10), (800, -10)])
    envers = LineString(list(u.coords)[::-1])
    lignes = pd.DataFrame({"nom": ["U", "U a l'envers"], "geometry": [u, envers]})
    r = geo.calculer_pk(lignes, AXE, pk_origine=50.0)
    assert r["pk_m"].tolist() == [250.0, 250.0]          # le plus petit des deux PK
    r = geo.calculer_pk(lignes, AXE, pk_origine=50.0, sens="aval_amont")
    assert r["pk_m"].tolist() == [250.0, 250.0]          # 1000 - 800 + 50


def test_l_ex_aequo_est_une_tolerance_pas_une_marche_d_arrondi():
    # Jambe droite allongee de e : le milieu glisse de e/2 vers x = 800, qui devient le
    # croisement le plus proche, de e/2 environ.
    def pk(e):
        u = LineString([(200, -10), (200, 10), (800, 10), (800, -10 - e)])
        lignes = pd.DataFrame({"nom": ["U"], "geometry": [u]})
        return geo.calculer_pk(lignes, AXE)["pk_m"].tolist()

    # A moins d'un millimetre du plus proche : ex aequo, le plus petit PK, quel que soit e
    # (un arrondi a 3 decimales rendait 800 pour e = 0,0004 et 200 pour e = 0,0002).
    assert pk(0.0002) == pk(0.0004) == pk(0.001) == [200.0]
    # Au-dela du millimetre, le croisement le plus proche l'emporte.
    assert pk(0.01) == [800.0]

