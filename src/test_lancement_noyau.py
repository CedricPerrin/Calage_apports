"""
Le lancement, avant le sous-processus, SANS QGIS.

Etape B2 de la frontiere fenetre / noyau (11/11/2026) : ce qui s'ecrit dans le
classeur au lancement, dans quel ordre, et ce qui fait refuser le calage
vivaient dans plugin._lancer_calage, que seul le banc sous QGIS pouvait
eprouver. C'est maintenant noyau.preparer_lancement.

Le raccord de la fenetre est eprouve sous QGIS par
src/test_lancement_fenetre.py, fige sur le code d'avant.

    python -m pytest src/test_lancement_noyau.py -q
"""
import json
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC.parent / "calage_apports"))

import noyau  # noqa: E402

REGLAGES = dict(premier_apport="A2", prefixe_scenario="R-Q100",
                tolerance_volume_pct=5.0, tolerance_pic_pct=2.0,
                bilan_masse_max_pct=5.0, nb_max_iterations=6,
                coeurs_par_calcul=0, elaguer_etapes=False,
                remplacer_plan_source=False)

ECRITS = [("Premier_apport", "A2"), ("Prefixe_scenario", "R-Q100"),
          ("Tolerance_volume_pct", 5.0), ("Tolerance_pic_pct", 2.0),
          ("Bilan_masse_max_pct", 5.0), ("Nb_max_iterations_par_apport", 6),
          ("Coeurs_par_calcul", 0), ("Elaguer_plans_etape", "non"),
          ("Remplacer_plan_source", "non")]


class _Poste:
    """Doublures des quatre portes de noyau ; « journal » : ce qui s'y joue."""

    def __init__(self, monkeypatch, manquantes=(), hecras=False, echec=None,
                 au_rang=1):
        self.journal, self.echec, self.au_rang = [], echec, au_rang
        self.etat = {"total": 3, "manquantes": list(manquantes)}
        self.hecras = hecras
        for nom in ("etat_cibles", "ecrire_parametre", "hecras_ouvert"):
            monkeypatch.setattr(noyau, nom, getattr(self, nom))

    def _jouer(self, nom, detail=None):
        self.journal.append(nom if detail is None else (nom, *detail))
        rang = sum(1 for j in self.journal
                   if (j if isinstance(j, str) else j[0]) == nom)
        if self.echec == nom and rang >= self.au_rang:
            raise OSError(f"echec de {nom}")

    def etat_cibles(self, classeur):
        self._jouer("etat_cibles")
        return self.etat

    def ecrire_parametre(self, classeur, cle, valeur):
        self._jouer("ecrire_parametre", (cle, valeur))

    def hecras_ouvert(self):
        self._jouer("hecras_ouvert")
        return self.hecras

    @property
    def ecrits(self):
        return [j[1:] for j in self.journal if not isinstance(j, str)]


# --- ce qui s'ecrit, et dans quel ordre ----------------------------------------

def test_un_lancement_possible_ecrit_les_neuf_reglages_et_ne_refuse_rien(
        monkeypatch):
    poste = _Poste(monkeypatch)

    assert noyau.preparer_lancement("donnees.xlsx", REGLAGES) is None

    assert poste.journal[0] == "etat_cibles"
    assert poste.ecrits == ECRITS
    assert poste.journal[-1] == "hecras_ouvert"


@pytest.mark.parametrize("coche, ecrit", [(True, "oui"), (False, "non")])
def test_une_case_cochee_s_ecrit_oui(monkeypatch, coche, ecrit):
    poste = _Poste(monkeypatch)

    noyau.ecrire_reglages_de_lancement("donnees.xlsx", dict(
        REGLAGES, elaguer_etapes=coche, remplacer_plan_source=coche))

    assert dict(poste.ecrits)["Elaguer_plans_etape"] == ecrit
    assert dict(poste.ecrits)["Remplacer_plan_source"] == ecrit


def test_les_reglages_peuvent_etre_lus_au_dernier_moment(monkeypatch):
    """La fenetre passe une fonction : elle n'est appelee qu'APRES la lecture
    de l'etat des cibles."""
    poste = _Poste(monkeypatch)
    lus = []

    def lire():
        lus.append(list(poste.journal))
        return REGLAGES

    noyau.preparer_lancement("donnees.xlsx", lire)

    assert lus == [["etat_cibles"]]
    assert poste.ecrits == ECRITS


def test_les_reglages_s_ecrivent_pour_de_vrai_dans_le_json_voisin(tmp_path):
    classeur = tmp_path / "donnees_calage.xlsx"
    classeur.with_suffix(".json").write_text(
        json.dumps({"Nom_projet": "Essai", "Premier_apport": ""}),
        encoding="utf-8")

    noyau.ecrire_reglages_de_lancement(classeur, dict(
        REGLAGES, elaguer_etapes=True))

    ecrit = json.loads(classeur.with_suffix(".json").read_text(
        encoding="utf-8"))
    assert ecrit["Nom_projet"] == "Essai", "un parametre a ete perdu"
    assert {c: ecrit[c] for c, _ in ECRITS} == dict(
        ECRITS, Elaguer_plans_etape="oui")


# --- ce qui fait refuser -------------------------------------------------------

def test_un_etat_des_cibles_illisible_est_une_panne_et_rien_n_est_ecrit(
        monkeypatch):
    poste = _Poste(monkeypatch, echec="etat_cibles")

    with pytest.raises(noyau.LancementRefuse) as refus:
        noyau.preparer_lancement("donnees.xlsx", REGLAGES)

    r = refus.value
    assert (r.nature, r.titre, r.message) == (
        "etat", "Calage", "echec de etat_cibles")
    assert r.contexte == "État des cibles avant lancement"
    assert isinstance(r.__cause__, OSError)
    assert poste.journal == ["etat_cibles"]


def test_une_ecriture_en_echec_est_une_panne_qui_dit_pourquoi_on_s_arrete(
        monkeypatch):
    poste = _Poste(monkeypatch, echec="ecrire_parametre", au_rang=3)

    with pytest.raises(noyau.LancementRefuse) as refus:
        noyau.preparer_lancement("donnees.xlsx", REGLAGES)

    r = refus.value
    assert (r.nature, r.titre) == ("reglages", "Réglages de lancement")
    assert r.message == (
        "Les réglages de lancement n'ont pas pu être écrits dans le "
        "classeur : echec de ecrire_parametre\n\nLe calage n'est pas lancé "
        "— il serait parti sur un réglage autre que celui affiché.")
    assert r.contexte == "Écriture des paramètres de lancement"
    assert len(poste.ecrits) == 3 and "hecras_ouvert" not in poste.journal


def test_une_lecture_des_reglages_en_echec_est_la_meme_panne(monkeypatch):
    _Poste(monkeypatch)

    def lire():
        raise RuntimeError("widget detruit")

    with pytest.raises(noyau.LancementRefuse) as refus:
        noyau.preparer_lancement("donnees.xlsx", lire)

    assert refus.value.nature == "reglages"
    assert "widget detruit" in refus.value.message


@pytest.mark.parametrize("manquantes, debut", [
    (["S2"], "1 section sur 3 sans hydrogramme cible exploitable : S2."),
    (["S2", "S3"],
     "2 sections sur 3 sans hydrogramme cible exploitable : S2, S3."),
])
def test_une_cible_manquante_est_un_refus_apres_l_ecriture_des_reglages(
        monkeypatch, manquantes, debut):
    poste = _Poste(monkeypatch, manquantes=manquantes)

    with pytest.raises(noyau.LancementRefuse) as refus:
        noyau.preparer_lancement("donnees.xlsx", REGLAGES)

    r = refus.value
    assert (r.nature, r.titre) == ("cibles", "Hydrogrammes cibles incomplets")
    assert r.message == (
        debut + "\n\nLe calage n'est pas lancé : la chaîne refuse un "
        "classeur incomplet, elle n'ignore pas les apports concernés. "
        "Compléter la feuille « Cibles » — une colonne « Temps_h » et au "
        "moins deux instants en face des débits — puis relancer.")
    assert r.contexte is None and r.__cause__ is None
    # LE CLASSEUR PORTE LES REGLAGES DE L'ECRAN, meme refuse.
    assert poste.ecrits == ECRITS
    assert "hecras_ouvert" not in poste.journal


def test_hecras_ouvert_est_un_refus(monkeypatch):
    _Poste(monkeypatch, hecras=True)

    with pytest.raises(noyau.LancementRefuse) as refus:
        noyau.preparer_lancement("donnees.xlsx", REGLAGES)

    r = refus.value
    assert (r.nature, r.titre, r.contexte) == (
        "hecras", "HEC-RAS est ouvert", None)
    assert r.message == (
        "HEC-RAS est ouvert sur ce poste. Ce n'est pas permis par le "
        "plugin. Fermer HEC-RAS et relancer le calage.")


@pytest.mark.parametrize("reponse", [None, False])
def test_ne_pas_savoir_si_hecras_est_ouvert_n_arrete_rien(
        monkeypatch, reponse):
    """Hors de Windows, ou sans tasklist : refuser sur une ignorance
    bloquerait un lancement valide."""
    _Poste(monkeypatch, hecras=reponse)

    assert noyau.preparer_lancement("donnees.xlsx", REGLAGES) is None


# --- ce qui se dit quand le calage est parti ------------------------------------

def test_le_message_de_lancement_nomme_le_processus_et_le_journal():
    assert noyau.dire_calage_lance(
        {"pid": 4242, "journal": "D:/sortie/calage_1.log"}) == (
        "Calage lancé en arrière-plan (processus 4242).\n"
        "Suivre l'avancement à l'étape « 4. Suivi », qui se rafraîchit "
        "toute seule quand elle est affichée.\n"
        "Journal de lancement : D:/sortie/calage_1.log")
