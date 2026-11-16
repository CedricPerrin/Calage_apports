"""
L'objectif degrade d'un cran, et le plan de reference remplace des que tout
est cale (16/11/2026) : ce que le code DOIT faire.

LES DEUX DEMANDES. « Si l'objectif n'est pas atteint, continuer en degradant
de 5 % l'objectif sur le volume et / ou la forme et mettre l'apport en
orange » ; « si le plan de reference et le plan de sortie sont les memes :
travailler sur une copie et, si le calcul aboutit, supprimer le plan de
reference et le remplacer ».

LES DECISIONS, prises le meme jour : un seul cran — au-dela, arret en rouge
comme avant ; la pointe garde sa tolerance ; le plan de reference est
remplace des que tous les apports sont retenus, verts ou orange, et reste
intact si le calage s'arrete sur un apport.

LE MONTAGE. Deux apports. Un debit non cale dont la QUEUE deborde la cible
de la premiere section : un apport ne sait qu'ajouter, le volume ne peut pas
redescendre. Selon la hauteur de cette queue, l'excedent tombe dans le cran
(orange) ou au-dela (rouge). Jugement sur toute la serie, sans fenetre : la
fenetre exclurait justement cette queue.

    python -m pytest src/test_objectif_degrade.py
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calage as cg
import suivi as sv
from criteres import diagnostiquer

TEMPS = np.linspace(0.01, 36, 400)
APPORTS, SECTIONS = ["A1", "A2"], ["S1", "S2"]
# Hauteur de la queue du debit non cale : 40 laisse S1 a 105,7 % de volume
# (dans le cran, 110 %), 60 a 114,3 % (au-dela).
DANS_LE_CRAN, AU_DELA = 40.0, 60.0


def _hydro(pic, t_pic, forme):
    t = np.maximum(TEMPS, 1e-3)
    return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))


CIBLE_S1 = _hydro(100.0, 10.0, 4.0)
CIBLE_S2 = CIBLE_S1 + _hydro(40.0, 9.0, 4.0)


def _caler(queue, suivi=None, **reglages):
    modele = cg.ModeleFictif(
        APPORTS, SECTIONS, TEMPS, [_hydro(10.0, 6.0, 2.5)] * 2,
        debit_base=_hydro(queue, 22.0, 6.0), retard_h=0.0,
        **{c: reglages.pop(c) for c in ("seuil_instabilite",)
           if c in reglages})
    config = cg.Configuration(**{"nb_max_essais": 6, "fenetre_active": False,
                                 **reglages})
    journal = []
    resultat = cg.caler(modele, APPORTS, SECTIONS,
                        [(TEMPS, CIBLE_S1), (TEMPS, CIBLE_S2)], config,
                        suivi=suivi, journal=journal.append)
    return modele, resultat, journal


# ---------------------------------------------------------------------------
# La regle elle-meme
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("volume, pointe, forme, tenu", [
    (1.07, 1.00, 0.99, True),      # volume dans le cran
    (0.91, 1.00, 0.99, True),      # ... des deux cotes
    (1.00, 1.00, 0.93, True),      # forme dans le cran
    (1.09, 0.985, 0.925, True),    # volume ET forme, pointe tenue
    (1.11, 1.00, 0.99, False),     # volume au-dela du cran
    (1.00, 1.00, 0.91, False),     # forme au-dela du cran
    (1.07, 0.97, 0.99, False),     # LA POINTE NE SE DEGRADE PAS
    (1.07, 1.03, 0.99, False),
    (1.07, 1.00, float("nan"), False),   # forme non calculable
])
def test_le_cran_relache_le_volume_et_la_forme_jamais_la_pointe(
        volume, pointe, forme, tenu):
    diag = SimpleNamespace(rapport_volume=volume, rapport_pic=pointe, r=forme)
    assert cg.concordance_degradee(diag, cg.Configuration()) is tenu


def test_le_cran_s_ajoute_aux_tolerances_de_l_etude():
    diag = SimpleNamespace(rapport_volume=1.12, rapport_pic=1.0, r=0.99)
    assert not cg.concordance_degradee(diag, cg.Configuration())
    assert cg.concordance_degradee(
        diag, cg.Configuration(tolerance_volume=0.08))


def test_un_cran_nul_ne_degrade_rien():
    diag = SimpleNamespace(rapport_volume=1.0, rapport_pic=1.0, r=1.0)
    assert not cg.concordance_degradee(
        diag, cg.Configuration(degradation_objectif=0.0))


# ---------------------------------------------------------------------------
# Le calage continue, ou s'arrete
# ---------------------------------------------------------------------------

def test_un_apport_dans_le_cran_est_retenu_et_le_calage_continue():
    modele, resultat, journal = _caler(DANS_LE_CRAN)
    a1, a2 = resultat.apports
    assert a1.valide and a1.degrade
    assert 1.05 < a1.diagnostic.rapport_volume <= 1.10
    assert a1.motif.startswith("objectif degrade (volume a 10 % pres")
    assert a2.valide and not a2.degrade and a2.motif == ""
    # Ni conforme, ni en echec ; le plan final est titre.
    assert not resultat.conforme and resultat.objectif_degrade
    assert resultat.motif.startswith("objectif degrade sur ['S1']")
    assert modele.etapes[-1] == "avec_apports"
    # Le mot auquel l'etape Suivi reconnait ce qui merite l'ecran.
    assert any("AVERTISSEMENT : OBJECTIF DEGRADE pour A1" in ligne
               for ligne in journal)
    assert any("S1" in ligne and "OBJECTIF DEGRADE" in ligne
               for ligne in journal)


def test_au_dela_du_cran_le_calage_s_arrete_comme_avant():
    modele, resultat, journal = _caler(AU_DELA)
    (a1,) = resultat.apports
    assert not a1.valide and not a1.degrade
    assert a1.diagnostic.rapport_volume > 1.10
    assert not resultat.conforme and not resultat.objectif_degrade
    assert resultat.motif.startswith("apport A1 non cale")
    assert modele.etapes[-1] == "Apport_A1"
    assert any("ARRET sur cet apport" in ligne for ligne in journal)


def test_sans_cran_le_meme_apport_arrete_le_calage():
    modele, resultat, _ = _caler(DANS_LE_CRAN, degradation_objectif=0.0)
    (a1,) = resultat.apports
    assert not a1.valide and not a1.degrade
    assert modele.etapes[-1] == "Apport_A1"


def test_un_calcul_rejete_ne_se_degrade_pas():
    # Le solveur derive des que l'apport est injecte : ce n'est pas
    # l'objectif qui manque, c'est le calcul. Aucun cran ne s'applique.
    _, resultat, _ = _caler(DANS_LE_CRAN, seuil_instabilite=0.5,
                            bilan_masse_max_pct=1.0)
    (a1,) = resultat.apports
    assert not a1.valide and not a1.degrade
    assert "qualite numerique" in a1.motif


# ---------------------------------------------------------------------------
# L'essai retenu n'est pas le dernier calcule : un recalcul
# ---------------------------------------------------------------------------

class _Solveur:
    """Rend toujours la meme section ; compte les calculs demandes."""

    def __init__(self, section, bilan=0.0):
        self.section, self.bilan, self.calculs = section, bilan, 0

    def calculer(self):
        self.calculs += 1
        return cg.ResultatCalcul(reussi=True, bilan_masse_pct=self.bilan)

    def lire_section(self, nom_section):
        return TEMPS, self.section


def _etat_arrete(section, essais, essai_en_place):
    """Une recherche arretee sur l'objectif, son meilleur essai remis en place."""
    etat = cg._EtatApport(0, "A1", "S1", TEMPS, CIBLE_S1)
    etat.objectif_manque, etat.issue = True, "arret"
    etat.motif = "la recherche s'eloigne de la concordance"
    etat.essais, etat.essai_en_place = essais, essai_en_place
    etat.decalage_zero = 0.0
    etat.diag = diagnostiquer(TEMPS, CIBLE_S1, TEMPS, section)
    return etat


# Une section dans le cran — la cible et une queue de trop : volume 107,7 %,
# pointe 101,2 %, forme 99,9 % — et une au-dela : volume 118,4 %.
_SECTION_ORANGE = CIBLE_S1 + _hydro(5.0, 22.0, 6.0)
_SECTION_ROUGE = CIBLE_S1 + _hydro(12.0, 22.0, 6.0)


def _degrader(essais, essai_en_place, bilan=0.0, section_recalculee=None):
    etat = _etat_arrete(_SECTION_ORANGE, essais, essai_en_place)
    solveur = _Solveur(_SECTION_ORANGE if section_recalculee is None
                       else section_recalculee, bilan)
    resultat = cg.ResultatCalage(config=cg.Configuration())
    journal = []
    cg._degrader_objectif(solveur, etat, resultat.config, None, resultat,
                          journal.append)
    return etat, solveur, resultat, journal


def test_l_essai_retenu_est_le_dernier_aucun_recalcul():
    etat, solveur, resultat, _ = _degrader(essais=3, essai_en_place=3)
    assert etat.issue == "degrade"
    assert solveur.calculs == 0 and resultat.nb_calculs == 0


def test_l_essai_retenu_n_est_pas_le_dernier_il_est_recalcule():
    # Sans recalcul, l'apport suivant lirait son residuel dans les resultats
    # d'un essai qui n'est plus en place, et la verification finale aussi.
    etat, solveur, resultat, journal = _degrader(essais=3, essai_en_place=1)
    assert etat.issue == "degrade"
    assert solveur.calculs == 1 and resultat.nb_calculs == 1
    assert any("recalcul" in ligne for ligne in journal)


def test_un_recalcul_rejete_laisse_l_apport_en_echec():
    etat, solveur, _, _ = _degrader(essais=3, essai_en_place=1, bilan=27.5)
    assert etat.issue == "arret" and solveur.calculs == 1
    assert "est rejete" in etat.motif


def test_un_recalcul_hors_du_cran_laisse_l_apport_en_echec():
    etat, _, _, _ = _degrader(essais=3, essai_en_place=1,
                              section_recalculee=_SECTION_ROUGE)
    assert etat.issue == "arret"
    assert "ne tient plus l'objectif degrade" in etat.motif


def test_un_arret_qui_ne_vient_pas_de_l_objectif_ne_se_degrade_pas():
    etat = _etat_arrete(_SECTION_ORANGE, essais=1, essai_en_place=1)
    etat.objectif_manque = False
    resultat = cg.ResultatCalage(config=cg.Configuration())
    cg._degrader_objectif(_Solveur(_SECTION_ORANGE), etat, resultat.config,
                          None, resultat, lambda ligne: None)
    assert etat.issue == "arret"


# ---------------------------------------------------------------------------
# La verification finale dit d'ou vient l'orange
# ---------------------------------------------------------------------------

def _verifier(apport_degrade):
    """Une section orange a la verification finale ; son apport l'etait, ou non."""
    config = cg.Configuration(fenetre_active=False)
    resultat = cg.ResultatCalage(config=config)
    resultat.apports.append(cg.ResultatApport(
        nom_apport="A1", nom_section="S1", valide=True, facteur=1.0,
        degrade=apport_degrade))
    cg._verifier_globalement(_Solveur(_SECTION_ORANGE), ["S1"],
                             [(TEMPS, CIBLE_S1)], config, resultat,
                             lambda ligne: None)
    return resultat


def test_la_verification_finale_range_la_section_en_orange():
    resultat = _verifier(apport_degrade=True)
    assert not resultat.conforme and resultat.objectif_degrade
    assert resultat.motif.startswith("objectif degrade sur ['S1']")
    assert "derive" not in resultat.motif


def test_une_section_verte_a_son_calage_puis_orange_est_dite_derivee():
    resultat = _verifier(apport_degrade=False)
    assert resultat.objectif_degrade
    assert "['S1'] par derive a la verification globale" in resultat.motif


# ---------------------------------------------------------------------------
# Le plan de reference qui garde son nom
# ---------------------------------------------------------------------------

def test_le_plan_final_prend_son_nom_des_que_tout_est_cale():
    # Calage mene au bout mais NON conforme (un apport en orange) : avant le
    # 16/11/2026 le plan de reference restait, et le recalage gardait son
    # titre d'etape, a renommer a la main.
    modele, resultat, journal = _caler(
        DANS_LE_CRAN, prefixe_etape="Q100", remplacer_plan_source=True)
    assert not resultat.conforme
    assert modele.etapes[-1] == "Q100"
    assert not any("n'est pas remplace" in ligne for ligne in journal)


def test_un_calage_arrete_ne_titre_pas_le_plan_final():
    modele, _, _ = _caler(AU_DELA, prefixe_etape="Q100",
                          remplacer_plan_source=True)
    assert modele.etapes[-1] == "Q100-A1"


# ---------------------------------------------------------------------------
# Le suivi publie l'orange
# ---------------------------------------------------------------------------

def test_le_suivi_publie_l_apport_degrade_et_le_verdict(tmp_path):
    suivi = sv.Suivi(tmp_path, APPORTS, SECTIONS)
    _, resultat, _ = _caler(DANS_LE_CRAN, suivi=suivi)
    suivi.conclure(resultat.conforme, resultat.motif, resultat.nb_calculs,
                   degrade=resultat.objectif_degrade)
    etat = json.loads((tmp_path / sv.ETAT_COURANT).read_text(encoding="utf-8"))
    a1, a2 = etat["apports"]
    # « validé » pour la reprise, « degrade » pour l'orange.
    assert a1["statut"] == "validé" and a1["degrade"] is True
    assert a1["motif"].startswith("objectif degrade")
    assert a2["statut"] == "validé" and a2["degrade"] is False
    assert etat["conforme"] is False and etat["degrade"] is True
    assert "objectif dégradé" in (tmp_path / "avancement.md").read_text(
        encoding="utf-8")
