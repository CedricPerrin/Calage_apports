"""
Ce que noyau.importer_hydrogrammes DOIT faire quand l'Excel importe est plus
court, ou troue, par rapport a ce que porte deja l'Excel de ce calcul.

Defaut corrige le 11/11/2026 : les lignes au-dela de la source n'etaient
JAMAIS videes. La fonction ecrivait « feuille.cell(row, column, value=None) »,
et openpyxl n'affecte la valeur que si elle n'est pas None : la cellule
gardait donc l'ancienne. Un hydrogramme importe plus court que le precedent
gardait la queue de l'ancien — une cible melee de deux crues, sans message.
Meme cause, meme effet pour un trou AU MILIEU de la source : l'ancienne
valeur restait dessous.

Contrairement a test_noyau_classeur.py, qui enregistre ce que la fonction
FAIT, ce fichier dit ce qu'elle DOIT faire.

    python -m pytest src/test_import_hydrogrammes.py -q
"""
import sys
from pathlib import Path

import openpyxl

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC.parent / "calage_apports"))

import noyau  # noqa: E402

COL_A = "Nom_Apport (BC line)"
COL_S = "Nom_Section (reference line)"


def _excel(chemin, cibles):
    """Un Excel des objectifs minimal : Correspondance et Cibles."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    classeur = openpyxl.Workbook()
    feuille = classeur.active
    feuille.title = "Correspondance"
    feuille.append([COL_A, COL_S, "Pente_m_par_m"])
    feuille.append(["A1", "S1", None])
    feuille.append(["A2", "S2", None])
    feuille = classeur.create_sheet("Cibles")
    entetes = list(cibles)
    feuille.append(entetes)
    for i in range(max(len(serie) for serie in cibles.values())):
        feuille.append([cibles[e][i] if i < len(cibles[e]) else None
                        for e in entetes])
    classeur.save(chemin)
    return chemin


def _colonnes(chemin):
    """{en-tete: valeurs sous l'en-tete, sur toute la hauteur de la feuille}."""
    feuille = openpyxl.load_workbook(chemin)["Cibles"]
    return {cellule.value: [feuille.cell(row=ligne, column=cellule.column).value
                            for ligne in range(2, feuille.max_row + 1)]
            for cellule in feuille[1] if cellule.value}


def _sans_vides_de_fin(serie):
    serie = list(serie)
    while serie and serie[-1] is None:
        serie.pop()
    return serie


def test_un_import_plus_court_ne_garde_pas_la_queue_de_l_ancien(tmp_path):
    ancien = {"Temps_h": [0.0, 1.0, 2.0, 3.0, 4.0],
              "Cible_S1": [10.0, 20.0, 30.0, 40.0, 50.0],
              "Cible_S2": [11.0, 21.0, 31.0, 41.0, 51.0]}
    nouveau = {"Temps_h": [0.0, 1.0, 2.0],
               "Cible_S1": [1.0, 2.0, 3.0],
               "Cible_S2": [4.0, 5.0, 6.0]}
    source = _excel(tmp_path / "precedent" / "donnees_calage.xlsx", nouveau)
    cible = _excel(tmp_path / "ce_calcul" / "donnees_calage.xlsx", ancien)

    bilan = noyau.importer_hydrogrammes(source, cible)

    assert bilan["importees"] == ["Cible_S1", "Cible_S2"]
    lu = _colonnes(cible)
    for entete, attendu in nouveau.items():
        assert _sans_vides_de_fin(lu[entete]) == attendu, (
            f"{entete} : la queue de l'ancien hydrogramme est restee sous "
            f"le nouveau ({lu[entete]}).")


def test_un_trou_de_la_source_ne_garde_pas_l_ancienne_valeur(tmp_path):
    ancien = {"Temps_h": [0.0, 1.0, 2.0],
              "Cible_S1": [10.0, 20.0, 30.0],
              "Cible_S2": [11.0, 21.0, 31.0]}
    nouveau = {"Temps_h": [0.0, 1.0, 2.0],
               "Cible_S1": [1.0, None, 3.0],
               "Cible_S2": [4.0, 5.0, 6.0]}
    source = _excel(tmp_path / "precedent" / "donnees_calage.xlsx", nouveau)
    cible = _excel(tmp_path / "ce_calcul" / "donnees_calage.xlsx", ancien)

    noyau.importer_hydrogrammes(source, cible)

    lu = _colonnes(cible)
    assert lu["Cible_S1"] == [1.0, None, 3.0], (
        "le trou de la source a ete comble par l'ancienne valeur (20.0).")
    assert lu["Cible_S2"] == [4.0, 5.0, 6.0]


def test_l_excel_d_avant_garde_l_ancien_hydrogramme_entier(tmp_path):
    """Le filet de securite de l'import : rien n'est perdu sans recours."""
    ancien = {"Temps_h": [0.0, 1.0, 2.0, 3.0, 4.0],
              "Cible_S1": [10.0, 20.0, 30.0, 40.0, 50.0],
              "Cible_S2": [11.0, 21.0, 31.0, 41.0, 51.0]}
    nouveau = {"Temps_h": [0.0, 1.0], "Cible_S1": [1.0, 2.0],
               "Cible_S2": [4.0, 5.0]}
    source = _excel(tmp_path / "precedent" / "donnees_calage.xlsx", nouveau)
    cible = _excel(tmp_path / "ce_calcul" / "donnees_calage.xlsx", ancien)

    bilan = noyau.importer_hydrogrammes(source, cible)

    assert _colonnes(Path(bilan["sauvegarde"])) == ancien


def test_une_colonne_que_l_import_ne_touche_pas_reste_entiere(tmp_path):
    """Sur la meme base de temps, une cible absente de la source est gardee."""
    ancien = {"Temps_h": [0.0, 1.0, 2.0],
              "Cible_S1": [10.0, 20.0, 30.0],
              "Cible_S2": [11.0, 21.0, 31.0]}
    nouveau = {"Temps_h": [0.0, 1.0, 2.0], "Cible_S1": [1.0, 2.0, 3.0]}
    source = _excel(tmp_path / "precedent" / "donnees_calage.xlsx", nouveau)
    cible = _excel(tmp_path / "ce_calcul" / "donnees_calage.xlsx", ancien)

    bilan = noyau.importer_hydrogrammes(source, cible)

    assert bilan["gardees"] == ["Cible_S2"]
    lu = _colonnes(cible)
    assert lu["Cible_S1"] == [1.0, 2.0, 3.0]
    assert lu["Cible_S2"] == [11.0, 21.0, 31.0]
