"""
tools/comparer_references.py : l'outil qui relit un refigeage.

Il dit, pour une reference de filet, quels cas ont change et si des nombres
ont change. On s'y fie pour valider un refigeage : il doit donc lui-meme etre
eprouve — un outil de relecture qui ne voit pas un nombre modifie est pire
que pas d'outil.

    python -m pytest src/test_comparer_references.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "tools"))

import comparer_references as cr  # noqa: E402

AVANT = {
    "_produit_par": {"numpy": "2.5.3"},
    "cas": {
        "calage/nominal": {"alertes": ["a", "b"], "volume": "f:0x1.8p+1",
                           "texte": "conforme"},
        "calage/refuse": {"exception": "IndexError", "trace": []},
    },
    "lot": [{"alertes": 1, "textes": "abc"}, {"alertes": 0, "textes": "def"}],
}


def _apres(**modifs):
    apres = json.loads(json.dumps(AVANT))
    for chemin, valeur in modifs.items():
        cible = apres
        *parents, dernier = chemin.split("|")
        for cle in parents:
            cible = cible[int(cle) if cle.isdigit() else cle]
        cible[int(dernier) if dernier.isdigit() else dernier] = valeur
    return apres


def test_deux_references_identiques_n_ont_aucun_ecart():
    assert cr.comparer(AVANT, json.loads(json.dumps(AVANT))) == {}


def test_un_texte_modifie_est_range_sous_son_cas_sans_nombre():
    ecarts = cr.comparer(AVANT, _apres(**{"cas|calage/refuse|exception":
                                          "ValueError"}))

    assert list(ecarts) == ["cas / calage/refuse"]
    cas = ecarts["cas / calage/refuse"]
    assert (cas["modifies"], cas["retires"], cas["ajoutes"]) == (1, 0, 0)
    assert cas["nombres"] == 0
    assert cas["exemples"] == [("exception", "IndexError", "ValueError")]


def test_un_nombre_fige_en_texte_est_vu_comme_un_nombre():
    ecarts = cr.comparer(AVANT, _apres(**{"cas|calage/nominal|volume":
                                          "f:0x1.8p+2"}))

    assert ecarts["cas / calage/nominal"]["nombres"] == 1


def test_une_alerte_retiree_est_un_retrait_pas_un_nombre():
    ecarts = cr.comparer(AVANT, _apres(**{"cas|calage/nominal|alertes":
                                          ["a"]}))

    cas = ecarts["cas / calage/nominal"]
    assert (cas["retires"], cas["nombres"]) == (1, 0)


def test_une_entree_du_lot_est_un_cas_et_son_compte_un_nombre():
    ecarts = cr.comparer(AVANT, _apres(**{"lot|0|alertes": 0}))

    assert list(ecarts) == ["lot / [0]"]
    assert ecarts["lot / [0]"]["nombres"] == 1


def test_une_liste_videe_est_vue():
    """[] n'a pas de feuille : elle en est une, sans quoi vider une liste
    passerait pour un simple retrait... ou pour rien."""
    ecarts = cr.comparer(_apres(**{"cas|calage/refuse|trace": ["appel"]}),
                         AVANT)

    assert "cas / calage/refuse" in ecarts


def test_vrai_et_un_ne_sont_pas_la_meme_feuille():
    ecarts = cr.comparer({"cas": {"c": {"ok": True}}},
                         {"cas": {"c": {"ok": 1}}})

    assert ecarts["cas / c"]["modifies"] == 1


def test_le_socle_est_range_a_part_et_ne_compte_pas_dans_les_nombres():
    apres = _apres(**{"_produit_par|numpy": "2.5.4"})

    lignes, nombres = cr.rapport("reference_essai.json", AVANT, apres)

    assert list(cr.comparer(AVANT, apres)) == ["_socle"]
    assert nombres == 0
    assert "aucun nombre modifie" in lignes[0]


def test_le_rapport_annonce_les_nombres_modifies():
    lignes, nombres = cr.rapport(
        "reference_essai.json", AVANT,
        _apres(**{"cas|calage/nominal|volume": "f:0x1.8p+2",
                  "cas|calage/refuse|exception": "ValueError"}))

    assert nombres == 1
    assert lignes[0] == ("== reference_essai.json : 2 cas different(s) sur 4 "
                         "— 1 NOMBRE(S) MODIFIE(S)")
    assert any("dont 1 nombre(s)" in ligne for ligne in lignes)


def test_est_un_nombre():
    for valeur in (3, 2.5, "f:0x1.8p+1", "-0x1.0p-3", "nd:float64:400:ab12"):
        assert cr.est_un_nombre(valeur), valeur
    for valeur in (True, False, None, "conforme", "", "0.5 h", [1]):
        assert not cr.est_un_nombre(valeur), valeur


def test_sans_changement_l_outil_le_dit_et_sort_en_zero():
    """Sur le depot tel qu'il est : aucune reference ne differe de HEAD — et
    si l'une differe, c'est qu'un refigeage n'a pas ete committe."""
    execution = subprocess.run(
        [sys.executable, str(RACINE / "tools" / "comparer_references.py"),
         str(RACINE / "src" / "reference_calage_fictif.json"), "--strict"],
        capture_output=True, text=True, encoding="utf-8", cwd=RACINE)

    assert execution.returncode == 0, execution.stdout + execution.stderr
