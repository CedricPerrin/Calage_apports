"""
Ce que noyau.preparer_classeur DOIT laisser derriere lui quand l'ecriture du
nouveau classeur echoue.

Defaut corrige le 11/11/2026. Recomposer met l'ancien classeur de cote
(« <nom>.precedent.xlsx ») PUIS ecrit le nouveau. Si cette ecriture echouait
(disque plein, droit refuse, partage reseau coupe), le classeur canonique
n'existait plus : la chaine ne trouvait plus de classeur, et la saisie de
l'ingenieur ne vivait plus que dans le fichier mis de cote. Or la composition
est AUTOMATIQUE : la suivante repartait d'un classeur absent, en ecrivait un
VIDE, et celle d'apres mettait ce vide de cote PAR-DESSUS la saisie. Deux
compositions apres l'echec, les hydrogrammes colles a la main etaient perdus.

Desormais un echec d'ecriture REMET EN PLACE le classeur mis de cote, puis
laisse remonter l'erreur.

    python -m pytest src/test_classeur_perdu.py -q
"""
import sys
from pathlib import Path
from unittest import mock

import openpyxl
import pandas as pd  # AVANT tout appel : les aides du filet posent un
#                      mock.patch.dict sur sys.modules, qui RETIRE a sa sortie
#                      ce qui a ete importe dedans ; numpy ne se recharge pas.
import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

import parametres  # noqa: E402  (meme raison que pandas)
import test_noyau_classeur as filet  # noqa: E402  (aides : composer, saisir)

noyau = filet.noyau

SAISIE = {"Temps_h": [0.0, 1.0, 2.0], "Cible_S1": [10.0, 20.0, 30.0]}


def _cibles(chemin):
    """{en-tete: valeurs non vides} de la feuille Cibles."""
    feuille = openpyxl.load_workbook(chemin)["Cibles"]
    return {c.value: [v for v in (feuille.cell(row=r, column=c.column).value
                                  for r in range(2, feuille.max_row + 1))
                      if v is not None]
            for c in feuille[1] if c.value}


def _saisie_presente(chemin):
    lues = _cibles(chemin)
    return all(lues.get(nom) == valeurs for nom, valeurs in SAISIE.items())


@pytest.fixture()
def classeur(tmp_path):
    """Un classeur compose, ou l'ingenieur a colle un hydrogramme."""
    chemin = filet.composer_avant(tmp_path)
    filet.saisir(chemin, SAISIE)
    assert _saisie_presente(chemin)
    return tmp_path, Path(chemin)


def _disque_plein(*a, **k):
    raise PermissionError("disque plein")


def test_un_echec_d_ecriture_laisse_le_classeur_en_place(classeur):
    dossier, chemin = classeur
    avant = chemin.read_bytes()

    rendu = filet.preparer(
        dossier, patchs=[mock.patch.object(pd, "ExcelWriter", _disque_plein)])

    assert rendu["exception"] == "PermissionError", "l'erreur doit remonter"
    assert chemin.exists(), (
        "le classeur canonique a disparu apres un echec d'ecriture.")
    assert chemin.read_bytes() == avant, "ce n'est plus le classeur d'avant."


def test_un_echec_apres_l_ecriture_du_classeur_rend_l_ancien(classeur):
    """Le .xlsx neuf est ecrit, puis le JSON des parametres echoue : un
    classeur neuf SANS ses parametres ne doit pas remplacer l'ancien."""
    dossier, chemin = classeur
    avant = chemin.read_bytes()

    rendu = filet.preparer(
        dossier, patchs=[mock.patch.object(parametres, "ecrire",
                                           _disque_plein)])

    assert rendu["exception"] == "PermissionError"
    assert chemin.read_bytes() == avant, "ce n'est plus le classeur d'avant."


def test_la_saisie_survit_a_deux_compositions_apres_un_echec(classeur):
    """Le scenario de la perte : echec, puis deux compositions automatiques."""
    dossier, chemin = classeur
    filet.preparer(
        dossier, patchs=[mock.patch.object(pd, "ExcelWriter", _disque_plein)])

    for _ in range(2):
        rendu = filet.preparer(dossier)
        assert "exception" not in rendu, rendu

    assert _saisie_presente(chemin), (
        "les hydrogrammes saisis ont ete perdus deux compositions apres "
        "l'echec d'ecriture.")


def test_une_composition_reussie_met_toujours_l_ancien_de_cote(classeur):
    dossier, chemin = classeur

    rendu = filet.preparer(dossier)

    assert "exception" not in rendu, rendu
    precedent = chemin.with_name(chemin.stem + ".precedent" + chemin.suffix)
    assert _saisie_presente(precedent) and _saisie_presente(chemin)


def test_sans_mise_de_cote_un_echec_ne_touche_a_rien(classeur):
    """Classeur ouvert dans Excel : le renommage est refuse, rien n'a bouge,
    il n'y a donc rien a remettre en place."""
    dossier, chemin = classeur

    def refuser(self, cible):
        raise PermissionError("[WinError 32] fichier ouvert dans Excel")

    rendu = filet.preparer(dossier, patchs=[
        mock.patch.object(Path, "replace", refuser),
        mock.patch.object(pd, "ExcelWriter", _disque_plein)])

    assert rendu["exception"] == "PermissionError"
    assert _saisie_presente(chemin)
