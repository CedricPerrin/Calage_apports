"""
L'etape Suivi montre l'objectif degrade (16/11/2026) : ce qu'elle DOIT faire.

Demande : « si l'objectif n'est pas atteint, continuer en degradant de 5 %
l'objectif [...] et mettre l'apport en orange ». La chaine publie un apport
retenu sur l'objectif degrade comme « validé », avec la cle « degrade » (voir
src/test_objectif_degrade.py). La page doit alors :

  - le montrer en ORANGE, avec son propre glyphe et son propre mot — la
    couleur ne porte jamais seule le sens ;
  - dire pourquoi, sur la ligne du tableau ;
  - annoncer un calage mene au bout sur l'objectif degrade autrement qu'un
    calage conforme (vert) ou en echec (rouge) ;
  - laisser l'etat lu intact : la reprise y lit toujours « validé ».

Sous le Python de QGIS :

    QT_QPA_PLATFORM=offscreen python3 -m pytest src/test_suivi_degrade.py -q
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC.parent))
sys.path.insert(0, str(SRC))

pytest.importorskip("qgis.core")

from calage_apports import page_suivi, socle, widgets  # noqa: E402
from calage_apports.interface import couleur as couleur_theme  # noqa: E402
from test_alertes_suivi import atelier  # noqa: E402,F401  (fixture)
from test_peinture_suivi import qgis_app  # noqa: E402,F401  (fixture)

MOTIF = ("objectif degrade (volume a 10 % pres, forme des 92 %, pointe "
         "inchangee) : 6 essais sans concordance simultanee")


def _calage_avec_un_apport_degrade(at):
    """A1 retenu sur l'objectif degrade, A2 sur l'objectif demande."""
    s = at.suivi(["A1", "A2"])
    s.commencer_apport(0)
    at.essai(s, 0, 1.07, 0.995)
    s.valider_apport(0, SimpleNamespace(rapport_volume=1.07, rapport_pic=0.995,
                                        r=0.99, decalage_h=0.0),
                     duree_s=600.0, motif_degrade=MOTIF)
    at.caler(s, 1)
    return s


def _ligne(page, apport):
    table = page.table_suivi
    for ligne in range(table.rowCount()):
        if table.item(ligne, 0).text() == apport:
            return [table.item(ligne, c) for c in range(table.columnCount())]
    raise AssertionError(f"{apport} absent du tableau")


def test_l_apport_degrade_est_orange_avec_son_glyphe_et_son_mot(atelier):
    _calage_avec_un_apport_degrade(atelier)
    atelier.page._peindre_suivi()

    statut = _ligne(atelier.page, "A1")[2]
    assert statut.text() == "⚠  objectif dégradé"
    assert statut.foreground().color() == couleur_theme(
        socle.ISL_ORANGE, atelier.page.table_suivi)
    assert statut.toolTip() == MOTIF
    # L'apport cale sur l'objectif demande reste vert, sans infobulle.
    autre = _ligne(atelier.page, "A2")[2]
    assert autre.text() == "✔  validé" and autre.toolTip() == ""
    assert autre.foreground().color() == couleur_theme(
        socle.ISL_VERT, atelier.page.table_suivi)


def test_le_ruban_porte_le_statut_degrade(atelier):
    _calage_avec_un_apport_degrade(atelier)
    atelier.page._peindre_suivi()

    statuts = [a["statut"] for a in atelier.page.ruban_apports.apports]
    assert statuts == [widgets.STATUT_DEGRADE, "validé"]
    assert "1 objectif dégradé" in atelier.page.ruban_apports.accessibleDescription()


def test_l_etat_lu_garde_valide_pour_la_reprise(atelier):
    _calage_avec_un_apport_degrade(atelier)
    apports = atelier.etat()["apports"]

    affiches = page_suivi.statuts_affiches(apports)

    assert [a["statut"] for a in apports] == ["validé", "validé"]
    assert [a["statut"] for a in affiches] == [widgets.STATUT_DEGRADE, "validé"]


def test_un_calage_mene_au_bout_en_degrade_n_est_ni_vert_ni_rouge(atelier):
    s = _calage_avec_un_apport_degrade(atelier)
    s.conclure(False, "objectif degrade sur ['S_A1']", 5, degrade=True)
    atelier.page._peindre_suivi()

    banniere = atelier.page.label_suivi_banniere.text()
    assert "Calage terminé — objectif dégradé" in banniere
    assert "2 apports calés, dont 1 sur l'objectif dégradé" in banniere
    assert "objectif degrade sur ['S_A1']" in banniere
    assert "NON conforme" not in banniere and "— conforme" not in banniere


def test_un_calage_en_echec_reste_rouge(atelier):
    s = _calage_avec_un_apport_degrade(atelier)
    s.conclure(False, "apport A2 non cale", 5)
    atelier.page._peindre_suivi()

    assert "Calage terminé — NON conforme" in atelier.page.label_suivi_banniere.text()


def test_chaque_statut_affiche_a_son_glyphe_sa_couleur_et_sa_teinte():
    assert (set(widgets.GLYPHE_STATUT) == set(socle.COULEUR_STATUT)
            == set(widgets.TEINTE_STATUT))
    assert widgets.GLYPHE_STATUT[widgets.STATUT_DEGRADE] not in (
        widgets.GLYPHE_STATUT["validé"], widgets.GLYPHE_STATUT["échoué"])
