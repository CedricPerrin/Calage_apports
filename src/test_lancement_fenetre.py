"""
FILET DU LANCEMENT, AU BORD DE noyau.py. Ecrit le 11/11/2026 sur le code
INCHANGE, avant que le lancement ne passe dans noyau.py (etape B2).

Tout ce que plugin._lancer_calage demande a noyau.py, dans l'ordre et avec ses
arguments ; chaque boite, chaque message de la barre, chaque ligne du journal
QGIS ; ce que la fenetre retient a la fin (processus, journal, etiquette). Un
cas par porte : installation en cours, paquet non compose, reglages changes,
calage deja en cours, plan final refuse, reprise refusee, etat des cibles
illisible, ecriture des reglages en echec, cibles incompletes, HEC-RAS ouvert,
lancement en echec.

Sous le Python de QGIS, dans son propre processus :

    QT_QPA_PLATFORM=offscreen python3 -m pytest src/test_lancement_fenetre.py -q
    QT_QPA_PLATFORM=offscreen python3 src/test_lancement_fenetre.py --figer
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("qgis.core")

from qgis.core import QgsApplication  # noqa: E402
from qgis.PyQt.QtCore import QSettings  # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow  # noqa: E402

from calage_apports import plugin  # noqa: E402

REFERENCE = Path(__file__).with_name("reference_lancement_fenetre.json")

CIBLES_COMPLETES = {"total": 3, "manquantes": []}

CAS = {
    "nominal": {},
    "installation_en_cours": {"installation": True},
    "paquet_non_compose": {"classeur": ""},
    "un_reglage_change": {"ecarts": {"tol": "Tolérance volume : 5 → 8"}},
    "trois_reglages_changes": {"ecarts": {
        "tol": "Tolérance volume : 5 → 8", "pic": "Tolérance pointe : 2 → 3",
        "prefixe": "Préfixe : R-Q100 → R-Q10"}},
    "calage_deja_en_cours_on_attend": {"malgre_calage": False},
    "plan_final_refuse": {"plan_final": False},
    "reprise_refusee": {"reprise": False},
    "etat_des_cibles_illisible": {"echec": "etat_cibles"},
    "ecriture_des_reglages_en_echec": {"echec": "ecrire_parametre",
                                       "au_rang": 3},
    "une_cible_manquante": {"etat": {"total": 3, "manquantes": ["S2"]}},
    "deux_cibles_manquantes": {"etat": {"total": 3,
                                        "manquantes": ["S2", "S3"]}},
    "hecras_ouvert": {"hecras": True},
    "hecras_indetermine": {"hecras": None},
    "lancement_en_echec": {"echec": "lancer_calage"},
    "plan_source_remplace_et_elagage": {"remplacer": True, "elaguer": True},
}


@pytest.fixture(scope="module")
def qgis_app(tmp_path_factory):
    if os.environ.get("QGIS_PREFIX_PATH"):
        QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication.instance() or QgsApplication([], True)
    app.initQgis()
    app.setOrganizationName("ISL-UX-tests")
    app.setApplicationName("calage-lancement")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      str(tmp_path_factory.mktemp("settings")))
    yield app
    app.processEvents()
    app.exitQgis()


def _fenetre():
    principale = QMainWindow()
    return principale, plugin.DialogueParametrage(
        SimpleNamespace(mainWindow=lambda: principale))


def jouer_lancement(nom, fenetre, pose):
    """Joue le lancement d'un cas ; rend la trace de ce qui s'y passe."""
    cas = CAS[nom]
    trace = []
    rangs = {}

    def temoin(nom_appel, rendu=None):
        def appel(*arguments, **nommes):
            rangs[nom_appel] = rangs.get(nom_appel, 0) + 1
            trace.append({"appel": nom_appel,
                          "arguments": _neutre(arguments),
                          "nommes": _neutre(nommes)})
            if (cas.get("echec") == nom_appel
                    and rangs[nom_appel] >= cas.get("au_rang", 1)):
                raise RuntimeError(f"echec simule de {nom_appel}")
            return rendu
        return appel

    noyau = plugin.noyau
    for cible, nom_appel, rendu in (
            (noyau, "etat_cibles", cas.get("etat", CIBLES_COMPLETES)),
            (noyau, "ecrire_parametre", None),
            (noyau, "hecras_ouvert", cas.get("hecras", False)),
            (noyau, "lancer_calage",
             {"pid": 4242, "journal": "D:/calage/sortie/calage_1.log"}),
            (plugin, "journaliser", None), (plugin, "rendre_la_main", None)):
        pose.setattr(cible, nom_appel, temoin(nom_appel, rendu))
    for boite in ("critical", "warning"):
        pose.setattr(plugin.QMessageBox, boite,
                     staticmethod(temoin(f"QMessageBox.{boite}")))
    for methode, rendu in (
            ("_installation_occupe", cas.get("installation", False)),
            ("_ecarts_avec_le_paquet", cas.get("ecarts", {})),
            ("_confirmer_malgre_calage", cas.get("malgre_calage", True)),
            ("_accepter_plan_final", cas.get("plan_final", True)),
            ("_confirmer_reprise", cas.get("reprise", True)),
            ("_signaler", None)):
        pose.setattr(fenetre, methode, temoin(methode, rendu))

    fenetre.edit_prefixe_scenario.setText("  R-Q100 ")
    fenetre.case_elaguer.setChecked(bool(cas.get("elaguer")))
    fenetre._remplacer_plan_source = bool(cas.get("remplacer"))
    fenetre.classeur = cas.get("classeur", "D:/calage/sortie/donnees.xlsx")
    fenetre.pid_lance = fenetre.journal_lance = fenetre.instant_lance = None
    plugin.dire(fenetre.label_lancement, "")
    # Saisir un texte ou cocher une case reveille des temoins de la fenetre :
    # ce qu'ils ont demande n'est pas du lancement.
    trace.clear()
    rangs.clear()

    fenetre._lancer_calage()

    return {"trace": trace,
            "apres": {"pid_lance": fenetre.pid_lance,
                      "journal_lance": fenetre.journal_lance,
                      "instant_pose": fenetre.instant_lance is not None,
                      "etiquette": fenetre.label_lancement.text()}}


def _neutre(valeur):
    """Un objet rendu comparable d'une execution a l'autre."""
    if isinstance(valeur, dict):
        return {str(c): _neutre(v) for c, v in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [_neutre(v) for v in valeur]
    if valeur is None or isinstance(valeur, (bool, int, float, str)):
        return valeur
    if isinstance(valeur, BaseException):
        return f"{type(valeur).__name__}: {valeur}"
    return f"<{type(valeur).__name__}>"


@pytest.fixture(scope="module")
def reference():
    assert REFERENCE.is_file(), (
        f"{REFERENCE.name} absent : le figer avec « --figer ».")
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def test_la_reference_couvre_les_cas_et_eux_seuls(reference):
    assert sorted(reference) == sorted(CAS)


@pytest.mark.parametrize("nom", sorted(CAS))
def test_le_lancement_fait_ce_que_la_reference_a_enregistre(
        nom, qgis_app, monkeypatch, reference):
    principale, fenetre = _fenetre()
    try:
        obtenu = jouer_lancement(nom, fenetre, monkeypatch)
    finally:
        fenetre.deleteLater()
        principale.deleteLater()
        qgis_app.processEvents()

    assert json.loads(json.dumps(obtenu)) == reference[nom]


if __name__ == "__main__" and "--figer" in sys.argv:
    _app = QgsApplication([], True)
    _app.initQgis()
    _rendus = {}
    for _nom in sorted(CAS):
        _principale, _fenetre_ = _fenetre()
        _pose = pytest.MonkeyPatch()
        _rendus[_nom] = jouer_lancement(_nom, _fenetre_, _pose)
        _pose.undo()
    REFERENCE.write_text(json.dumps(_rendus, ensure_ascii=False, indent=1,
                                    sort_keys=True) + "\n", encoding="utf-8")
    print(f"REFERENCE REECRITE : {REFERENCE.name} ({len(_rendus)} cas). "
          f"Relire le diff avant de committer.")
