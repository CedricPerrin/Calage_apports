"""
Deux alertes de l'etape Suivi qui ne disaient rien, ou disaient faux.

Defauts corriges le 11/11/2026 :

  - DESACCORD DE DOSSIER. Quand l'Excel lance et l'etape Parametres designent
    deux dossiers de suivi differents, c'est l'Excel qui gagne (regle voulue),
    et la page doit le DIRE : sinon on corrige le champ de l'etape Parametres,
    le suivi ne bouge pas, et rien n'explique pourquoi. Le message existait
    mais ne s'affichait jamais : il comparait l'origine du dossier au mot
    « classeur », que _origine_dossier_suivi ne rend pas (elle rend le libelle
    « Excel lancé »).

  - ETAT ILLISIBLE. noyau.lire_avancement promet, quand le fichier d'etat
    existe mais ne peut pas etre lu (reecriture en cours, antivirus, partage
    reseau), de « garder simplement l'affichage precedent ». La page faisait
    le contraire : elle repassait a « Aucun calage suivi » et vidait le
    tableau, en plein calage.

Sous le Python de QGIS (import de calage_apports.plugin) :

    QT_QPA_PLATFORM=offscreen python3 -m pytest src/test_alertes_suivi.py -q
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC.parent))
sys.path.insert(0, str(SRC))

pytest.importorskip("qgis.core")

from calage_apports import noyau, page_suivi, plugin  # noqa: E402
from test_peinture_suivi import (  # noqa: E402,F401  (qgis_app : fixture)
    Atelier, DialogueFactice, Horloge, INSTANT, TAILLE_PAGE, qgis_app)


# --- desaccord de dossier ----------------------------------------------------

def _dialogue(dossier_excel, sortie_parametres, sous_dossier=""):
    """Ce que les trois methodes du dialogue lisent, et rien d'autre."""
    champ = lambda texte: SimpleNamespace(text=lambda: texte)   # noqa: E731
    d = SimpleNamespace(
        classeur="donnees_calage.xlsx" if dossier_excel is not None else None,
        _suivi_du_classeur=(("cle", 0.0), dossier_excel),
        edit_dossier_sortie=champ(sortie_parametres),
        edit_sous_dossier_suivi=champ(sous_dossier))
    for nom in ("_origine_dossier_suivi", "_dossier_suivi_de_l_onglet_3",
                "_detail_desaccord_suivi"):
        methode = getattr(plugin.DialogueParametrage, nom)
        setattr(d, nom, methode.__get__(d))
    return d


def test_le_desaccord_entre_l_excel_et_les_parametres_est_dit():
    surveille = Path("etude") / "Q100" / "suivi"
    d = _dialogue(surveille, str(Path("etude") / "Q10"))

    detail = d._detail_desaccord_suivi(surveille)

    assert str(Path("etude") / "Q10" / "suivi") in detail
    assert "Excel lancé" in detail


def test_pas_de_message_quand_les_deux_dossiers_s_accordent():
    surveille = Path("etude") / "Q100" / "suivi"
    d = _dialogue(surveille, str(Path("etude") / "Q100"))

    assert d._detail_desaccord_suivi(surveille) == ""


def test_pas_de_message_quand_le_dossier_vient_de_l_etape_parametres():
    d = _dialogue(None, str(Path("etude") / "Q10"))

    assert d._detail_desaccord_suivi(Path("etude") / "Q10" / "suivi") == ""


def test_pas_de_message_quand_l_etape_parametres_ne_designe_rien():
    surveille = Path("etude") / "Q100" / "suivi"
    d = _dialogue(surveille, "")

    assert d._detail_desaccord_suivi(surveille) == ""


# --- etat illisible ------------------------------------------------------------

@pytest.fixture()
def atelier(qgis_app, monkeypatch, tmp_path):
    import suivi as module_suivi
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtWidgets import QApplication
    monkeypatch.setattr(page_suivi, "datetime", Horloge)
    monkeypatch.setattr(module_suivi, "datetime", Horloge)
    monkeypatch.setattr(noyau, "processus_vivant", lambda pid: True)
    monkeypatch.chdir(tmp_path)
    Horloge.instant = INSTANT
    dialogue = DialogueFactice(None)
    page = page_suivi.PageSuivi(dialogue)
    page.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    page.resize(*TAILLE_PAGE)
    page.show()
    at = Atelier(page, dialogue)
    dialogue._atelier = at
    yield at
    page.hide()
    page.deleteLater()
    QApplication.processEvents()


def _calage_en_cours(at):
    s = at.suivi(["A1", "A2"])
    at.caler(s, 0, minutes=-30)
    s.commencer_apport(1)
    return at.dossier / "avancement.json"


def _ecran(at):
    page = at.page
    return (page.label_suivi_banniere.text(), page.table_suivi.rowCount(),
            page.barre_suivi.value(), page.label_suivi_position.text())


def test_un_etat_illisible_garde_l_affichage_precedent(atelier):
    chemin = _calage_en_cours(atelier)
    atelier.page._peindre_suivi()
    avant = _ecran(atelier)
    assert avant[1] == 2 and "Aucun calage suivi" not in avant[0]

    chemin.write_text(chemin.read_text(encoding="utf-8")[:40], encoding="utf-8")
    atelier.a(1)
    atelier.page._peindre_suivi()

    assert _ecran(atelier) == avant, (
        "l'etat illisible a remis la page a zero en plein calage.")
    assert "n'a pas pu être lu" in atelier.page.label_suivi_dossier.text()
    assert "conservé" in atelier.page.label_suivi_dossier.text()


def test_la_mention_disparait_des_que_l_etat_est_relu(atelier):
    chemin = _calage_en_cours(atelier)
    atelier.page._peindre_suivi()
    sain = chemin.read_text(encoding="utf-8")
    chemin.write_text(sain[:40], encoding="utf-8")
    atelier.page._peindre_suivi()

    chemin.write_text(sain, encoding="utf-8")
    atelier.page._peindre_suivi()

    assert "n'a pas pu être lu" not in atelier.page.label_suivi_dossier.text()
    assert atelier.page.table_suivi.rowCount() == 2


def test_un_etat_illisible_des_la_premiere_lecture_est_dit(atelier):
    """Rien a conserver : la page dit « Aucun calage suivi », ET pourquoi."""
    chemin = _calage_en_cours(atelier)
    chemin.write_text("{", encoding="utf-8")

    atelier.page._peindre_suivi()

    assert "Aucun calage suivi" in atelier.page.label_suivi_banniere.text()
    texte = atelier.page.label_suivi_dossier.text()
    assert "n'a pas pu être lu" in texte and "conservé" not in texte


def test_un_etat_absent_remet_bien_la_page_a_zero(atelier):
    """Une relance archive l'etat avant d'en ecrire un neuf : ce vide-la est
    une information, il ne doit pas etre masque par l'affichage d'avant."""
    chemin = _calage_en_cours(atelier)
    atelier.page._peindre_suivi()

    chemin.unlink()
    atelier.page._peindre_suivi()

    assert "Aucun calage suivi" in atelier.page.label_suivi_banniere.text()
    assert atelier.page.table_suivi.rowCount() == 0
    assert "n'a pas pu être lu" not in atelier.page.label_suivi_dossier.text()


def test_avancement_illisible_distingue_absent_et_illisible(tmp_path):
    assert noyau.avancement_illisible(tmp_path) is False
    (tmp_path / noyau.ETAT_SUIVI_COURANT).write_text("{", encoding="utf-8")
    assert noyau.lire_avancement(tmp_path) is None
    assert noyau.avancement_illisible(tmp_path) is True
    (tmp_path / noyau.ETAT_SUIVI_COURANT).write_text(
        json.dumps({"apports": []}), encoding="utf-8")
    assert noyau.avancement_illisible(tmp_path) is False
