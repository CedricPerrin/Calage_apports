# -*- coding: utf-8 -*-
"""
Banc d'auto-tests de pilote_hecras.py.

Sorti du module le 10/11/2026 : c'etait son bloc « if __name__ ==
"__main__" », pres de 1 800 lignes qui partaient dans l'archive du plugin.
Le code est celui du bloc, a l'identique, desindente d'un cran. Il se lance
seul (python3 src/bancs/banc_pilote_hecras.py) ou par le module
(python3 src/pilote_hecras.py), qui l'execute puis garde sa ligne de
commande --projet.

LES DOUBLURES PASSENT PAR LE MODULE. Dans le module, le banc remplacait
fermer_processus et PERIODE_SURVEILLANCE_S en les reaffectant : la fonction
du module voyait la nouvelle valeur. Ici, un nom importe est une copie
locale ; le remplacement s'ecrit donc pilote_hecras.<nom> = ..., sans quoi
le controle resterait vert sans plus rien eprouver.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # src/

import re                                                   # noqa: E402
import time                                                 # noqa: E402

import numpy as np                                          # noqa: E402
import pandas as pd                                         # noqa: E402

import pilote_hecras                                        # noqa: E402
from pilote_hecras import (  # noqa: E402
    INTERVALLE_APPORT, PERIODE_SURVEILLANCE_S, PiloteHecRas, _champ,
    _ecrire_texte, _en_minutes, _erreur_ecriture_geometrie, _heure_du_dossier,
    _lire_texte, _messages_hecras, _retablir_octets, _sans_tableau_des_temps,
    _table_debits, ajouter_condition_limite_debit, bilan_masse_depuis_comptes,
    cartographier_hydrogrammes, conditions_trop_courtes,
    fenetre_simulation_du_plan, fermer_processus, hecras_ouvert,
    imposer_intervalle_apport, instant_hecras, intervalle_hecras,
    intervalle_hecras_depuis_heures, ligne_localisation,
    lignes_reference_sans_trace, lire_hydrogramme_unsteady,
    orphelins_du_calcul, par_controleur, pids_hecras, plan_detourne,
    plan_par_titre, plans_par_titre, retarder_hydrogrammes, symbole_decimal,
    valider_fenetre_simulation, verifier_intervalle_apports)

# SORTIE EN UTF-8, MEME LANCE A LA MAIN. Les auto-tests de ce module
# impriment des caracteres hors ASCII (« → », « Δ », les guillemets
# francais). Dans une console ou une redirection Windows, la sortie prend
# l'encodage local — cp1252 sur un poste francais — et le premier de ces
# caracteres leve UnicodeEncodeError : l'auto-test s'interrompt sur ce qui
# ressemble a un defaut du module, alors que rien n'est casse. Le pont
# impose PYTHONIOENCODING=utf-8 a la chaine lancee par le plugin ; ceci
# couvre l'appel direct, que la documentation recommande pourtant.
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import shutil
import tempfile

print("=" * 74)
print("AUTO-TEST — lecture du bilan de masse et creation d'un apport")
print("=" * 74)
_echecs_test = []

def _verifier(libelle, condition, detail=""):
    # Le DETAIL est facultatif mais precieux : « [OK] ... » ne dit pas sur
    # quelle valeur le controle a porte, et c'est ce qui manque le jour ou
    # il faut comprendre pourquoi il ne passe plus.
    print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
          + (f"  ->  {detail}" if detail else ""))
    if not condition:
        _echecs_test.append(libelle)

def _leve(exception, fonction, *args, **kwargs):
    """Vrai si l'appel leve bien l'exception attendue."""
    try:
        fonction(*args, **kwargs)
    except exception:
        return True
    except Exception:
        return False
    return False

# Colonnes REELLEMENT observees sur un calcul reel (ras-commander 0.99.1,
# 2026-07-26) : c'est ce format qui avait echappe au premier filtre et
# laissait le bilan a NaN en silence.
_comptes_reels = pd.DataFrame({
    "Error": [0.079627],
    "Error Percent": [0.0008],
    "Total Boundary Flux of Water In": [9954.874023],
    "Total Boundary Flux of Water Out": [9204.600586],
    "Vol Accounting in": ["1000 m^3"],
    "Volume Ending": [750.353149],
    "Volume Starting": [0.0],
})
_verifier("colonne reelle « Error Percent » lue correctement",
          abs(bilan_masse_depuis_comptes(_comptes_reels) - 0.0008) < 1e-9)

_comptes_avec_symbole = pd.DataFrame({"Error %": [1.23]})
_verifier("variante avec symbole « % » toujours reconnue",
          abs(bilan_masse_depuis_comptes(_comptes_avec_symbole) - 1.23) < 1e-9)

_verifier("DataFrame vide -> NaN, pas d'exception",
          pd.isna(bilan_masse_depuis_comptes(pd.DataFrame())))
_verifier("None -> NaN, pas d'exception",
          pd.isna(bilan_masse_depuis_comptes(None)))
_verifier("aucune colonne pertinente -> NaN",
          pd.isna(bilan_masse_depuis_comptes(pd.DataFrame({"Autre": [1]}))))

# --- creation d'une condition limite dans un fichier unsteady ----------
print("\n--- ajouter_condition_limite_debit ---")

# Ligne relevee TELLE QUELLE dans un fichier unsteady reel : elle fige le
# format a largeur fixe, qu'aucun test synthetique ne pourrait deviner.
_reelle = ("Boundary Location=                ,                ,        ,"
           "        ,                ,Perimeter 1     ,                ,"
           "IN_AMONT                        ,"
           "                                ")
_verifier("la ligne produite est identique au format reel de HEC-RAS",
          ligne_localisation("IN_AMONT", "Perimeter 1") == _reelle)

_verifier("un nom trop long est refuse, pas tronque en silence",
          _leve(ValueError, ligne_localisation, "N" * 33, "Perimeter 1"))

_tampon = Path(tempfile.gettempdir()) / "_essai_calage_apports.u01"
_tampon.write_text(
    "Flow Title=Essai\n"
    "Use Restart= 0 \n"
    + ligne_localisation("EXISTANT", "Perimeter 1") + "\n"
    "Interval=15MIN\n"
    "Flow Hydrograph= 4 \n"
    "    1.00    2.00    3.00    4.00\n"
    "Flow Hydrograph Slope= 0.02 \n",
    encoding="utf-8")

_debits = [10.0, 25.5, 40.0, 30.25, 12.0, 5.0, 2.5]
_n = ajouter_condition_limite_debit(_tampon, "APPORT_ESSAI", "Perimeter 1",
                                    _debits, pente=0.01)
_verifier("nombre de valeurs ecrites correct", _n == len(_debits))

_texte = _tampon.read_text(encoding="utf-8")
# Le pas de l'apport cree DOIT valoir 6 min : c'est celui auquel les cibles
# sont ramenees a la lecture du classeur. Un apport cree a 15 min obligeait
# definir_forme a reechantillonner la cible une seconde fois.
_verifier("l'apport cree porte l'intervalle de 6 min",
          f"Interval={INTERVALLE_APPORT}\n" in _texte
          and _texte.count("Interval=15MIN") == 1,
          INTERVALLE_APPORT)
_verifier("la condition limite existante est preservee",
          "EXISTANT" in _texte and "Flow Hydrograph= 4 " in _texte)
_verifier("la pente demandee est ecrite",
          "Flow Hydrograph Slope= 0.01 " in _texte)

# -----------------------------------------------------------------------
# PENTES DEPOSEES AVANT LE CALAGE, APPLIQUEES APRES LE CLONAGE.
#
# Releve en production : « pente de A1 non appliquee : condition limite
# A1 absente du fichier unsteady. Presentes : [] ». La liste etait VIDE —
# ce n'est pas l'apport qui manquait, c'est la carte des blocs, que seul
# preparer() construit. _appliquer_pentes() du pont tournant AVANT lui,
# toutes les pentes saisies au classeur etaient perdues derriere un
# avertissement. Les deux controles ci-dessous tiennent l'ordre.
# -----------------------------------------------------------------------
_pilote_pente = PiloteHecRas(_tampon.parent, "_essai_calage_apports",
                             plan_reference="01")
_pilote_pente.fichier_unsteady = _tampon
_pilote_pente.carte = cartographier_hydrogrammes(_tampon)
_pilote_pente.pentes = {"APPORT_ESSAI": 0.037}
_pilote_pente._appliquer_pentes_deposees()
_verifier("une pente deposee est bien ecrite dans le fichier unsteady",
          "Flow Hydrograph Slope= 0.037 " in _tampon.read_text(
              encoding="utf-8"))

# Bloc saisi dans HEC-RAS sans « EG Slope » : pas de ligne de pente.
# RasUnsteady.exe plantait des que le calage y mettait du debit
# (constat du 27/10/2026). La ligne doit etre AJOUTEE, et
# le bloc suivant rester lisible malgre le decalage d'une ligne.
_sans_pente = Path(tempfile.gettempdir()) / "_essai_sans_pente.u01"
_sans_pente.write_text(
    "Flow Title=Essai\n"
    + ligne_localisation("SANS_PENTE", "Perimeter 1") + "\n"
    "Interval=6MIN\n"
    "Flow Hydrograph= 2 \n"
    "    1.00    2.00\n"
    "Stage Hydrograph TW Check=0\n"
    "DSS Path=\n"
    + ligne_localisation("SUIVANT", "Perimeter 1") + "\n"
    "Interval=6MIN\n"
    "Flow Hydrograph= 2 \n"
    "    7.00    8.00\n"
    "Stage Hydrograph TW Check=0\n"
    "Flow Hydrograph Slope= 0.02 \n", encoding="utf-8")
_pilote_sp = PiloteHecRas(_sans_pente.parent, "_essai_sans_pente",
                          plan_reference="01")
_pilote_sp.fichier_unsteady = _sans_pente
_pilote_sp.carte = cartographier_hydrogrammes(_sans_pente)
_pilote_sp.definir_pente("SANS_PENTE", 0.0044)
_lignes_sp = _sans_pente.read_text(encoding="utf-8").splitlines()
_verifier("une pente absente est ajoutee apres « Stage Hydrograph TW "
          "Check= », dans le bloc de l'apport",
          _lignes_sp[5:8] == ["Stage Hydrograph TW Check=0",
                              "Flow Hydrograph Slope= 0.0044 ",
                              "DSS Path="], _lignes_sp[5:8])
_info_sp = _pilote_sp.carte["SUIVANT"]
_verifier("la carte suit le decalage : le bloc suivant reste lisible",
          list(lire_hydrogramme_unsteady(_sans_pente, _info_sp["debut"],
                                         _info_sp["fin"])) == [7.0, 8.0])
_sans_pente.unlink()

import ast as _ast
import inspect as _inspect
import textwrap as _textwrap
_src_preparer = _textwrap.dedent(_inspect.getsource(PiloteHecRas.preparer))
_verifier("preparer() applique les pentes deposees, sinon elles se perdent",
          any(isinstance(n, _ast.Call)
              and isinstance(n.func, _ast.Attribute)
              and n.func.attr == "_appliquer_pentes_deposees"
              for n in _ast.walk(_ast.parse(_src_preparer))))

_carte = cartographier_hydrogrammes(_tampon)
_verifier("l'apport cree est relu par cartographier_hydrogrammes",
          "APPORT_ESSAI" in _carte)
if "APPORT_ESSAI" in _carte:
    _info = _carte["APPORT_ESSAI"]
    _relus = lire_hydrogramme_unsteady(_tampon, _info["debut"],
                                          _info["fin"])
    _verifier("les debits relus sont EXACTEMENT ceux ecrits",
              len(_relus) == len(_debits)
              and max(abs(a - b) for a, b in zip(_relus, _debits)) < 1e-9)
    _verifier("l'intervalle est relu correctement",
              abs(_info["intervalle_h"] - 0.1) < 1e-9,
              f"{60 * _info['intervalle_h']:.0f} min")
    _verifier("la zone 2D est relue correctement",
              _info["zone"] == "Perimeter 1")

_verifier("un doublon de nom est refuse",
          _leve(ValueError, ajouter_condition_limite_debit, _tampon,
                "APPORT_ESSAI", "Perimeter 1", _debits))

# --- re-cadencage d'un apport DEJA present ------------------------------
print("\n--- imposer_intervalle_apport ---")
# « EXISTANT » porte 4 valeurs au quart d'heure, soit 0,75 h — une duree
# qui n'est PAS un multiple entier de 6 min (7,5 pas). Le cas est
# volontaire : il exerce la regle de prolongation.
_cr = imposer_intervalle_apport(_tampon, "EXISTANT")
_verifier("le pas d'un apport existant est ramene a 6 min",
          _cr and _cr["intervalle_apres"] == INTERVALLE_APPORT,
          f"{60 * _cr['intervalle_avant_h']:.0f} min -> "
          f"{_cr['intervalle_apres']}" if _cr else "aucun compte rendu")
_verifier("la DUREE commande le compte, pas le nombre de valeurs",
          _cr and _cr["nb_avant"] == 4 and _cr["nb_apres"] == 9
          and abs(_cr["duree_h"] - 0.75) < 1e-9,
          f"{_cr['nb_avant']} -> {_cr['nb_apres']} valeurs sur "
          f"{_cr['duree_h']:.2f} h" if _cr else "")
_verifier("une duree non multiple du pas PROLONGE, jamais ne raccourcit",
          _cr and _cr["prolonge_h"] > 0
          and _cr["prolonge_h"] <= 0.1 + 1e-9,
          f"+{60 * _cr['prolonge_h']:.0f} min de queue plate" if _cr else "")

_carte_r = cartographier_hydrogrammes(_tampon)
_vals_r = lire_hydrogramme_unsteady(_tampon, _carte_r["EXISTANT"]["debut"],
                                       _carte_r["EXISTANT"]["fin"])
# Aux instants de l'ANCIENNE grille, les valeurs doivent etre intactes :
# une interpolation lineaire repasse par ses points d'appui. C'est ce qui
# garantit qu'un pic n'est ni deplace ni ecrete par le re-cadencage.
_verifier("les valeurs d'origine sont retrouvees a leur instant",
          len(_vals_r) == 9
          and max(abs(_vals_r[int(2.5 * k)] - v)
                  for k, v in enumerate([1.0, 2.0, 3.0, 4.0])
                  if (2.5 * k) % 1 == 0) < 1e-6,
          f"{[round(float(v), 2) for v in _vals_r]}")
_verifier("la queue prolongee tient la derniere valeur, sans extrapoler",
          abs(_vals_r[-1] - 4.0) < 1e-6, f"{_vals_r[-1]:.2f} attendu 4.00")

_bilan_r = verifier_intervalle_apports(_tampon)
_verifier("le controle relit un fichier conforme",
          _bilan_r["EXISTANT"]["conforme"]
          and _bilan_r["EXISTANT"]["annonce"] == 9,
          _bilan_r["EXISTANT"]["motif"] or "conforme, en-tete accordee")

# Duree multiple exact du nouveau pas : aucune prolongation, et le pic
# horaire doit se retrouver a l'identique dix pas plus loin.
_tampon2 = Path(tempfile.gettempdir()) / "_essai_calage_recadence.u01"
_tampon2.write_text(
    "Flow Title=Essai\n"
    + ligne_localisation("HORAIRE", "Perimeter 1") + "\n"
    "Interval=1HOUR\n"
    "Flow Hydrograph= 4 \n"
    "   10.00   50.00  100.00   20.00\n"
    "Flow Hydrograph Slope= 0.02 \n",
    encoding="utf-8")
_cr2 = imposer_intervalle_apport(_tampon2, "HORAIRE")
_c2 = cartographier_hydrogrammes(_tampon2)
_v2 = lire_hydrogramme_unsteady(_tampon2, _c2["HORAIRE"]["debut"],
                                   _c2["HORAIRE"]["fin"])
_verifier("3 h au pas horaire font 31 valeurs au pas de 6 min",
          _cr2 and _cr2["nb_apres"] == 31 and abs(_cr2["prolonge_h"]) < 1e-9,
          f"{_cr2['nb_avant']} -> {_cr2['nb_apres']} valeurs, "
          f"prolonge de {_cr2['prolonge_h']:.3f} h" if _cr2 else "")
_verifier("le pic horaire est retrouve a la meme heure et a la meme valeur",
          abs(_v2[20] - 100.0) < 1e-6 and abs(float(np.max(_v2)) - 100.0) < 1e-6,
          f"t=2 h -> {_v2[20]:.2f}, pic {float(np.max(_v2)):.2f}")
_tampon2.unlink(missing_ok=True)
_verifier("un apport deja au bon pas n'est pas retouche",
          imposer_intervalle_apport(_tampon, "EXISTANT") is None)
_verifier("un apport inconnu leve une erreur nommant les presents",
          _leve(ValueError, imposer_intervalle_apport, _tampon, "ABSENT"))

# Une en-tete desaccordee du tableau doit etre VUE : c'est la panne
# silencieuse que le controle existe pour attraper.
_texte_faux = _tampon.read_text(encoding="utf-8").replace(
    "Flow Hydrograph= 9 ", "Flow Hydrograph= 12 ")
_tampon.write_text(_texte_faux, encoding="utf-8")
_verifier("une en-tete qui ment sur le nombre de valeurs est detectee",
          not verifier_intervalle_apports(_tampon)["EXISTANT"]["conforme"],
          verifier_intervalle_apports(_tampon)["EXISTANT"]["motif"])
_tampon.unlink(missing_ok=True)

# -----------------------------------------------------------------------
# RE-CADENCAGE AUTOMATIQUE A LA PREPARATION.
#
# Sans lui, la cible ramenee a 6 min par la lecture du classeur etait
# reprojetee sur la grille HORAIRE de l'apport par definir_forme() : neuf
# valeurs sur dix de ce que l'utilisateur avait saisi disparaissaient a
# l'ecriture, en silence. Les deux controles ci-dessous tiennent l'ordre
# ET l'effet.
# -----------------------------------------------------------------------
print("\n--- _recadencer_apports (branche dans preparer) ---")
_tampon3 = Path(tempfile.gettempdir()) / "_essai_calage_prepare.u01"
_tampon3.write_text(
    "Flow Title=Essai\n"
    + ligne_localisation("AMONT", "Perimeter 1") + "\n"
    "Interval=1HOUR\n"
    "Flow Hydrograph= 4 \n"
    "   10.00   50.00  100.00   20.00\n"
    "Flow Hydrograph Slope= 0.02 \n"
    + ligne_localisation("DEJA_FIN", "Perimeter 1") + "\n"
    "Interval=6MIN\n"
    "Flow Hydrograph= 3 \n"
    "    1.00    2.00    3.00\n"
    "Flow Hydrograph Slope= 0.02 \n",
    encoding="utf-8")
_pilote_recad = PiloteHecRas(_tampon3.parent, "_essai_calage_prepare",
                             plan_reference="01")
_pilote_recad.fichier_unsteady = _tampon3
_pilote_recad.carte = cartographier_hydrogrammes(_tampon3)
_convertis = _pilote_recad._recadencer_apports()
_verifier("seul l'apport au mauvais pas est converti",
          len(_convertis) == 1 and _convertis[0]["nom"] == "AMONT",
          f"{[c['nom'] for c in _convertis]}")
_verifier("la carte est RECONSTRUITE apres le re-cadencage",
          _pilote_recad.carte["AMONT"]["intervalle_h"] == 0.1
          and _pilote_recad.carte["AMONT"]["fin"]
          - _pilote_recad.carte["AMONT"]["debut"] == 4,
          f"pas {60 * _pilote_recad.carte['AMONT']['intervalle_h']:.0f} min, "
          f"{_pilote_recad.carte['AMONT']['fin'] - _pilote_recad.carte['AMONT']['debut']} "
          f"ligne(s) de tableau")
_verifier("le second apport, deja au bon pas, est intact",
          _pilote_recad.carte["DEJA_FIN"]["intervalle_h"] == 0.1,
          f"pas {60 * _pilote_recad.carte['DEJA_FIN']['intervalle_h']:.0f} min")
_verifier("un fichier deja entierement a 6 min ne declenche rien",
          _pilote_recad._recadencer_apports() == [])
_tampon3.unlink(missing_ok=True)

# -----------------------------------------------------------------------
# CORRECTION AUTOMATIQUE : UNE CONDITION LIMITE NON PILOTEE AU MAUVAIS PAS.
#
# Cas reel du 2026-08-05 : la cible est native a 3 min,
# pas_travail_h vaut donc 0,05 h — jamais le plancher fige 6 min. Une
# condition hors calage (ici « BC_MAUVAIS », l'equivalent de la
# « BC Line 1 » du projet reel) reste a 6 min : un libelle herite du
# modele qui a servi de base, perime pour les valeurs qu'elle porte
# (demande utilisateur : donnees_calage.xlsx fait AUTORITE sur le pas, le
# calage doit corriger lui-meme l'intervalle plutot que d'arreter et
# renvoyer l'utilisateur rouvrir HEC-RAS a la main). La correction est un
# RE-ETIQUETAGE (Interval= seul) : jamais un re-echantillonnage, qui
# fabriquerait des valeurs sur une condition dont le contenu est final.
# -----------------------------------------------------------------------
print("\n--- correction automatique d'une condition NON pilotee ---")
_verifier("intervalle_hecras_depuis_heures traduit un pas en minutes "
          "entieres",
          intervalle_hecras_depuis_heures(0.05) == "3MIN"
          and intervalle_hecras_depuis_heures(1.0) == "60MIN")
_verifier("un pas non representable en minutes entieres est refuse",
          _leve(ValueError, intervalle_hecras_depuis_heures, 0.017))

_tampon4 = Path(tempfile.gettempdir()) / "_essai_calage_garde_fou.u01"
_tampon4.write_text(
    "Flow Title=Essai\n"
    + ligne_localisation("APPORT_01", "Perimeter 1") + "\n"
    "Interval=1HOUR\n"
    "Flow Hydrograph= 4 \n"
    "   10.00   50.00  100.00   20.00\n"
    "Flow Hydrograph Slope= 0.02 \n"
    + ligne_localisation("BC_AMONT", "Perimeter 1") + "\n"
    "Interval=3MIN\n"
    "Flow Hydrograph= 3 \n"
    "    1.00    2.00    3.00\n"
    "Flow Hydrograph Slope= 0.02 \n"
    + ligne_localisation("BC_MAUVAIS", "Perimeter 1") + "\n"
    "Interval=6MIN\n"
    "Flow Hydrograph= 3 \n"
    "    5.00    6.00    7.00\n"
    "Flow Hydrograph Slope= 0.02 \n",
    encoding="utf-8")
# Seul « APPORT_01 » est pilote par CE calage : pas_travail_h vient de la
# cible (3 min), comme le ferait commande_caler().
_pilote_garde = PiloteHecRas(_tampon4.parent, "_essai_calage_garde_fou",
                             plan_reference="01", pas_travail_h=0.05,
                             apports_a_caler=["APPORT_01"])
_pilote_garde.fichier_unsteady = _tampon4
_pilote_garde.carte = cartographier_hydrogrammes(_tampon4)
_valeurs_avant = lire_hydrogramme_unsteady(
    _tampon4, _pilote_garde.carte["BC_MAUVAIS"]["debut"],
    _pilote_garde.carte["BC_MAUVAIS"]["fin"])
try:
    _pilote_garde._recadencer_apports()
    _msg_garde = None
except ValueError as e:
    _msg_garde = str(e)
_verifier("la condition non pilotee au mauvais pas ne bloque plus le "
          "calage : elle est corrigee automatiquement",
          _msg_garde is None, _msg_garde or "corrigee sans exception")

_carte_garde = cartographier_hydrogrammes(_tampon4)
_verifier("l'apport PILOTE est toujours RE-ECHANTILLONNE a 3 min",
          abs(_carte_garde["APPORT_01"]["intervalle_h"] - 0.05) < 1e-9,
          f"pas {60 * _carte_garde['APPORT_01']['intervalle_h']:.1f} min")
_verifier("la condition non pilotee mais deja conforme n'a pas ete "
          "touchee",
          abs(_carte_garde["BC_AMONT"]["intervalle_h"] - 0.05) < 1e-9)
_verifier("la condition non pilotee et fautive est RE-ECHANTILLONNEE a "
          "3 min",
          abs(_carte_garde["BC_MAUVAIS"]["intervalle_h"] - 0.05) < 1e-9,
          f"pas {60 * _carte_garde['BC_MAUVAIS']['intervalle_h']:.1f} min")
_valeurs_apres = lire_hydrogramme_unsteady(
    _tampon4, _carte_garde["BC_MAUVAIS"]["debut"],
    _carte_garde["BC_MAUVAIS"]["fin"])
# LA DUREE EST CONSERVEE, PAS LE NOMBRE DE VALEURS. 3 valeurs a 6 min
# couvrent 12 min ; les memes 12 min en demandent 5 au pas de 3 min. Le
# re-etiquetage seul, qui gardait les 3 valeurs, ramenait la duree a 6 min
# — c'est ce qui a fait echouer un calage reel (voir _recadencer_apports).
_verifier("le RE-ECHANTILLONNAGE conserve la DUREE de la condition non "
          "pilotee",
          len(_valeurs_apres) == 5,
          f"{len(_valeurs_avant)} valeurs (12 min) -> "
          f"{len(_valeurs_apres)} valeurs "
          f"({3 * (len(_valeurs_apres) - 1)} min)")
_verifier("les valeurs d'origine sont retrouvees A LEURS INSTANTS : rien "
          "n'est deplace ni ecrete",
          [_valeurs_apres[0], _valeurs_apres[2], _valeurs_apres[4]]
          == list(_valeurs_avant),
          f"{list(_valeurs_avant)} -> {list(_valeurs_apres)}")
_tampon4.unlink(missing_ok=True)

# GARDE-FOU DE DUREE : une condition qui s'arrete avant la fin de la
# simulation fait refuser le calcul par HEC-RAS (« Time series data ends
# before the end of the simulation ») sans que ras-commander le rapporte.
# Cas reel du 2026-08-07 : 20,10 h de donnees pour 33 h simulees.
_tampon6 = Path(tempfile.gettempdir()) / "_essai_duree.u01"
_tampon6.write_text(
    "Flow Title=Essai\n"
    + ligne_localisation("COURTE", "Perimeter 1") + "\n"
    "Interval=1HOUR\n"
    "Flow Hydrograph= 3 \n"
    "    1.00    2.00    3.00\n"
    "Flow Hydrograph Slope= 0.02 \n",
    encoding="utf-8")
_plan6 = Path(tempfile.gettempdir()) / "_essai_duree.p01"
_plan6.write_text("Plan Title=Essai\n"
                  "Simulation Date=01JUL2024,00:00,02JUL2024,09:00\n",
                  encoding="utf-8")
_courtes = conditions_trop_courtes(_tampon6, _plan6)
_verifier("une condition plus courte que la simulation est detectee, avec "
          "ses deux durees",
          "COURTE" in _courtes
          and abs(_courtes["COURTE"]["duree_h"] - 2.0) < 1e-9
          and abs(_courtes["COURTE"]["simulation_h"] - 33.0) < 1e-9,
          str(_courtes))
_plan6.write_text("Plan Title=Essai\n"
                  "Simulation Date=01JUL2024,00:00,01JUL2024,02:00\n",
                  encoding="utf-8")
_verifier("une condition qui couvre EXACTEMENT la simulation est acceptee",
          conditions_trop_courtes(_tampon6, _plan6) == {},
          str(conditions_trop_courtes(_tampon6, _plan6)))
_verifier("sans fenetre de simulation lisible, rien n'est bloque",
          conditions_trop_courtes(_tampon6, _plan6.with_suffix(".pZZ"))
          == {})
_tampon6.unlink(missing_ok=True)
_plan6.unlink(missing_ok=True)

# Cas RESIDUEL : une condition dont le bloc est trop abime pour etre
# corrige (pas de ligne Interval= reconnaissable). Le re-cadencage echoue
# proprement (avertissement), et c'est alors verifier_intervalle_apports()
# qui arrete le calage avant tout calcul, en la nommant.
_tampon5 = Path(tempfile.gettempdir()) / "_essai_calage_garde_fou_kox.u01"
_tampon5.write_text(
    "Flow Title=Essai\n"
    + ligne_localisation("APPORT_01", "Perimeter 1") + "\n"
    "Interval=3MIN\n"
    "Flow Hydrograph= 2 \n"
    "    1.00    2.00\n"
    "Flow Hydrograph Slope= 0.02 \n"
    # Bloc volontairement sans ligne « Interval= » exploitable.
    + ligne_localisation("BC_ABIMEE", "Perimeter 1") + "\n"
    "Flow Hydrograph= 2 \n"
    "    3.00    4.00\n"
    "Flow Hydrograph Slope= 0.02 \n",
    encoding="utf-8")
_pilote_garde5 = PiloteHecRas(_tampon5.parent, "_essai_calage_garde_fou_kox",
                              plan_reference="01", pas_travail_h=0.05,
                              apports_a_caler=["APPORT_01"])
_pilote_garde5.fichier_unsteady = _tampon5
_pilote_garde5.carte = cartographier_hydrogrammes(_tampon5)
_verifier("le cas residuel est bien construit : le bloc abime n'a pas "
          "d'intervalle lisible",
          _pilote_garde5.carte.get("BC_ABIMEE", {}).get("intervalle_h")
          is None)
try:
    _pilote_garde5._recadencer_apports()
    _msg_garde5 = None
except ValueError as e:
    _msg_garde5 = str(e)
_verifier("une condition non pilotee irreparable arrete encore le "
          "calage AVANT calcul, en la nommant",
          _msg_garde5 is not None and "BC_ABIMEE" in _msg_garde5,
          _msg_garde5 or "aucune exception levee")
_tampon5.unlink(missing_ok=True)

# L'ORDRE EST L'INVARIANT : recadencer APRES avoir fige self.originaux
# laisserait la boucle travailler sur des valeurs qui ne sont plus celles
# du fichier. Le test lit la source plutot que de simuler un clonage, qui
# exigerait HEC-RAS.
_src_prep = _textwrap.dedent(_inspect.getsource(PiloteHecRas.preparer))
_corps = _ast.parse(_src_prep).body[0].body
_rang_recad = next((i for i, n in enumerate(_corps)
                    if "_recadencer_apports" in _ast.dump(n)), None)
_rang_originaux = next((i for i, n in enumerate(_corps)
                        if "originaux" in _ast.dump(n)), None)
_verifier("preparer() recadence AVANT de figer les hydrogrammes d'origine",
          _rang_recad is not None and _rang_originaux is not None
          and _rang_recad < _rang_originaux,
          f"recadencage en position {_rang_recad}, "
          f"originaux en position {_rang_originaux}")

# --- deux pieges releves sur le fichier unsteady reel du projet -------
print("\n--- cartographier_hydrogrammes : bornage et zones ---")
_piege = Path(tempfile.gettempdir()) / "_essai_calage_pieges.u01"
_piege.write_text(
    "Flow Title=Essai\n"
    # Une SORTIE : pas d'hydrogramme, seulement une pente imposee.
    + ligne_localisation("SORTIE_AVAL", "Perimeter 1") + "\n"
    "Friction Slope=0.02,0\n"
    # Un apport, dans la zone reelle.
    + ligne_localisation("APPORT_A", "Perimeter 1") + "\n"
    "Interval=15MIN\n"
    "Flow Hydrograph= 3 \n"
    "    7.00    8.00    9.00\n"
    "Flow Hydrograph Slope= 0.01 \n"
    # Le MEME nom, dans une zone devenue orpheline.
    + ligne_localisation("APPORT_A", "Zone_orpheline") + "\n"
    "Interval=15MIN\n"
    "Flow Hydrograph= 3 \n"
    "  100.00  200.00  300.00\n"
    "Flow Hydrograph Slope= 0.02 \n"
    # DANS LA BONNE ZONE, mais SANS BC line en geometrie : le residu que
    # HEC-RAS ignore et que le calage prenait pour une condition vive.
    + ligne_localisation("APPORT_B", "Perimeter 1") + "\n"
    "Interval=15MIN\n"
    "Flow Hydrograph= 2 \n"
    "    1.00    2.00\n"
    "Flow Hydrograph Slope= 0.03 \n",
    encoding="utf-8")

_c = cartographier_hydrogrammes(_piege)
_verifier("une sortie sans hydrogramme n'est PAS prise pour un apport",
          "SORTIE_AVAL" not in _c)
_verifier("le doublon de zone est signale, pas ignore",
          _c.get("APPORT_A", {}).get("autres_zones") == ["Zone_orpheline"])

_cz = cartographier_hydrogrammes(_piege, "Perimeter 1")
_verifier("le filtrage par zone leve l'ambiguite",
          "APPORT_A" in _cz and not _cz["APPORT_A"]["autres_zones"])
if "APPORT_A" in _cz:
    _v = lire_hydrogramme_unsteady(_piege, _cz["APPORT_A"]["debut"],
                                      _cz["APPORT_A"]["fin"])
    _verifier("c'est bien le bloc de la BONNE zone qui est retenu",
              list(_v) == [7.0, 8.0, 9.0])

_co = cartographier_hydrogrammes(_piege, "Zone_orpheline")
_verifier("filtrer sur la zone orpheline retourne bien l'autre bloc",
          "APPORT_A" in _co
          and list(lire_hydrogramme_unsteady(
              _piege, _co["APPORT_A"]["debut"],
              _co["APPORT_A"]["fin"])) == [100.0, 200.0, 300.0])

# --- BLOCS SANS BC LINE EN GEOMETRIE : HEC-RAS LES IGNORE, NOUS AUSSI ---
# Cas reel du 30/08/2026 : un unsteady de 45 blocs pour 14 BC lines en
# geometrie. Deux des blocs surnumeraires, restes courts, ont fait
# REFUSER trois lancements sur des series que le solveur n'ouvre jamais.
_verifier("un bloc sans BC line en geometrie est ignore",
          set(cartographier_hydrogrammes(
              _piege, "Perimeter 1", {"APPORT_A"})) == {"APPORT_A"})
_verifier("le filtre retire bien un nom absent de la geometrie",
          "APPORT_B" not in cartographier_hydrogrammes(
              _piege, "Perimeter 1", {"APPORT_A"})
          and "APPORT_B" in cartographier_hydrogrammes(
              _piege, "Perimeter 1"))
# NONE VEUT DIRE « JE NE SAIS PAS », PAS « AUCUNE ». Une geometrie
# illisible doit desactiver le filtre, jamais vider la carte : sinon un
# incident de lecture arreterait un calage parfaitement valide.
_verifier("noms_connus=None n'ote rien (geometrie illisible)",
          cartographier_hydrogrammes(_piege, "Perimeter 1", None)
          == cartographier_hydrogrammes(_piege, "Perimeter 1"))
_verifier("une geometrie VRAIMENT vide, elle, ne laisse rien passer",
          cartographier_hydrogrammes(_piege, "Perimeter 1", set()) == {})
# LE FILTRE DOIT VALOIR PARTOUT OU LA CARTE EST ENUMEREE, pas seulement a
# l'ecriture. Pose a deux endroits sur trois le 30/08, il laissait
# verifier_intervalle_apports() se prononcer sur des orphelins que le
# re-cadencage avait volontairement laisses tranquilles : le calage
# s'arretait sur « pas 0.5 h au lieu de 0.1 » pour des conditions que
# HEC-RAS n'ouvre meme pas (releve le 31/08/2026, second poste).
_sans_filtre = verifier_intervalle_apports(_piege, "Perimeter 1",
                                           intervalle="15MIN")
_avec_filtre = verifier_intervalle_apports(_piege, "Perimeter 1",
                                           intervalle="15MIN",
                                           noms_connus={"APPORT_A"})
# --- LES MESSAGES DE HEC-RAS SONT DANS LE HDF, MEME PARTIEL ----------
# Un calcul qui n'a jamais demarre laisse quand meme
# « Results/Summary/Compute Messages (text) », ou HEC-RAS dit ce qu'il a
# refuse. La chaine ne lisait que _compute_pXX.log — qui ne porte souvent
# que les lignes du serveur de communication, ecartees par le filtre — et
# concluait « aucun message exploitable » en renvoyant l'utilisateur
# ouvrir HEC-RAS a la main. La reponse etait dans le fichier qu'elle
# venait de lire (releve le 31/08/2026 : « Geometry Writer Failed »).
print("\n--- messages de HEC-RAS dans un HDF partiel ---")
import h5py as _h5
_msg_hdf = Path(tempfile.gettempdir()) / "_essai_calage_msg.p01.hdf"
with _h5.File(_msg_hdf, "w") as _h:
    _h.create_dataset(
        "Results/Summary/Compute Messages (text)",
        data=np.bytes_((
            "Plan: 'sans apport' (ESSAI.p01)\n"
            "Simulation started at: 31Aug2026 12:22:00 PM\n"
            "Writing Geometry...\n"
            "Geometry Writer Failed\n"
            "Error Processing Geometry\n"
            "Computation Task\tTime\n").encode("utf-8")))
_lu = _messages_hecras(_msg_hdf)
_verifier("la cause est extraite du HDF, pas du journal texte",
          "Geometry Writer Failed" in _lu
          and "Error Processing Geometry" in _lu, _lu[:110])
_verifier("l'en-tete de plan et les temps ne noient pas la cause",
          "Simulation started" not in _lu and "Computation Task" not in _lu)
_msg_hdf.unlink(missing_ok=True)

# --- LE .gXX.hdf N'A PAS PU ETRE REECRIT ------------------------------
# Reproduit le 30/10/2026 sur une copie de modele reel : le .gXX.hdf tenu
# ouvert par un autre programme, HEC-RAS calcule sur l'ancien HDF et ne le
# dit qu'au milieu de son compte rendu, que la simulation prolonge ensuite
# de dizaines de lignes. compute_plan rend pourtant un succes.
print("\n--- pretraitement non reecrit, reference lines sans point ---")
_msg_hdf = Path(tempfile.gettempdir()) / "_essai_calage_ecriture.p01.hdf"
with _h5.File(_msg_hdf, "w") as _h:
    _h.create_dataset(
        "Results/Summary/Compute Messages (text)",
        data=np.bytes_((
            "Plan: 'sans apport' (ESSAI.p01)\n"
            "Writing Geometry...\n"
            "Completed Writing Geometry\n"
            "Finished Processing Geometry\n"
            "Error updating base geometry file with pre-processed tables "
            "'C:\\essai\\ESSAI.g01.hdf' \n"
            + "Performing Unsteady Flow Simulation\n" * 40
            + "Computation Task\tTime\n").encode("utf-8")))
_lu = _erreur_ecriture_geometrie(_msg_hdf)
_verifier("l'echec de reecriture du .gXX.hdf est trouve, meme noye",
          "Error updating base geometry file" in _lu and "QGIS" in _lu,
          _lu[:110])
with _h5.File(_msg_hdf, "w") as _h:
    _h.create_dataset(
        "Results/Summary/Compute Messages (text)",
        data=np.bytes_(b"Writing Geometry...\nFinished Processing Geometry\n"))
_verifier("un compte rendu sans cet echec ne dit rien",
          _erreur_ecriture_geometrie(_msg_hdf) == "")
_msg_hdf.unlink(missing_ok=True)

_geo = Path(tempfile.gettempdir()) / "_essai_calage_rl.g01"
_geo.write_bytes(b"Geom Title=Essai\r\n")

def _hdf_rl(points, info):
    with _h5.File(str(_geo) + ".hdf", "w") as _h:
        _g = _h.create_group("Geometry/Reference Lines")
        _g.create_dataset("Attributes", data=np.array(
            [(b"SC_A", b"Perimeter 1"), (b"SC_B", b""),
             (b"SC_C", b"Perimeter 1")],
            dtype=[("Name", "S32"), ("SA-2D", "S32")]))
        _g.create_dataset("Polyline Info", data=np.array(info, dtype="i4"))
        _g.create_dataset("Polyline Points", data=np.array(
            points, dtype="f8").reshape(-1, 2))

_hdf_rl([[0, 0], [1, 1], [2, 2], [3, 3]],
        [[0, 2, 0, 1], [2, 0, 1, 1], [2, 2, 2, 1]])
_verifier("une reference line sans point est nommee, les autres non",
          lignes_reference_sans_trace(_geo) == ["SC_B"],
          f"{lignes_reference_sans_trace(_geo)}")
_hdf_rl([], [[0, 0, 0, 1], [0, 0, 1, 1], [0, 0, 2, 1]])
_verifier("« Polyline Points » vide : toutes sont nommees (cas du 27/10)",
          lignes_reference_sans_trace(_geo) == ["SC_A", "SC_B", "SC_C"],
          f"{lignes_reference_sans_trace(_geo)}")
Path(str(_geo) + ".hdf").unlink()
_verifier("sans .gXX.hdf, rien a signaler",
          lignes_reference_sans_trace(_geo) == [])
_geo.unlink(missing_ok=True)

_verifier("verifier_intervalle_apports honore le meme filtre",
          "APPORT_B" in _sans_filtre and "APPORT_B" not in _avec_filtre,
          f"sans filtre {sorted(_sans_filtre)}, avec {sorted(_avec_filtre)}")

# --- PROLONGEMENT DES APPORTS PILOTES -------------------------------
# Un modele livre porte souvent des apports plus courts que la fenetre de
# simulation. HEC-RAS refuse alors de calculer, et l'utilisateur devait
# rallonger a la main des series que le calage REECRIT des le premier
# essai. Releve le 31/08/2026 : six apports sur douze, et le message
# l'envoyait corriger la feuille Cibles — sans aucun effet sur le modele.
_court = Path(tempfile.gettempdir()) / "_essai_calage_court.u01"
_court.write_text(
    "Flow Title=Essai\n"
    + ligne_localisation("BREF", "Perimeter 1") + "\n"
    "Interval=1HOUR\n"
    "Flow Hydrograph= 4 \n"
    "    1.00    5.00    3.00    1.00\n"
    "Flow Hydrograph Slope= 0.01 \n", encoding="utf-8")
_avant = cartographier_hydrogrammes(_court)["BREF"]
_v_avant = lire_hydrogramme_unsteady(_court, _avant["debut"],
                                        _avant["fin"])
imposer_intervalle_apport(_court, "BREF", intervalle="1HOUR",
                          duree_min_h=10.0)
_apres = cartographier_hydrogrammes(_court)["BREF"]
_v_apres = lire_hydrogramme_unsteady(_court, _apres["debut"],
                                        _apres["fin"])
_verifier("un apport trop court est prolonge jusqu'a la fenetre",
          abs((len(_v_apres) - 1) * _apres["intervalle_h"] - 10.0) < 1e-9,
          f"{(len(_v_avant) - 1) * _avant['intervalle_h']:.0f} h -> "
          f"{(len(_v_apres) - 1) * _apres['intervalle_h']:.0f} h")
_verifier("la serie d'origine est intacte, et la queue vaut ZERO",
          list(_v_apres[:4]) == [1.0, 5.0, 3.0, 1.0]
          and set(_v_apres[4:]) == {0.0},
          f"{list(_v_apres)}")
_verifier("sans duree_min_h, rien n'est prolonge",
          imposer_intervalle_apport(_court, "BREF",
                                    intervalle="1HOUR") is None)
_court.unlink(missing_ok=True)
_piege.unlink(missing_ok=True)

# --- fenetre de simulation du plan ------------------------------------
#
# Une fenetre mal ecrite n'est pas refusee par HEC-RAS : elle est lue
# autrement, et le calcul tourne sur une periode qui n'est pas celle des
# hydrogrammes. Rien dans les resultats ne le signale — d'ou une validation
# stricte, eprouvee ici sur les erreurs de saisie realistes.
print("\n--- fenetre de simulation ---")
_verifier("un instant bien forme est accepte",
          instant_hecras("13oct2014,00:00") == "13OCT2014,00:00")
_verifier("un mois francais est refuse",
          _leve(ValueError, instant_hecras, "13FEV2014,00:00"))
_verifier("une date au format francais est refusee",
          _leve(ValueError, instant_hecras, "13/10/2014 00:00"))
_verifier("une heure invalide est refusee",
          _leve(ValueError, instant_hecras, "13OCT2014,25:00"))
_verifier("un jour invalide est refuse",
          _leve(ValueError, instant_hecras, "32OCT2014,00:00"))
_verifier("minuit et 23:59 restent acceptes",
          instant_hecras("01JAN2020,00:00") == "01JAN2020,00:00"
          and instant_hecras("31DEC2020,23:59") == "31DEC2020,23:59")
# Les deux formes coexistent dans un projet reel :
# n'en accepter qu'une rejetterait un plan valide.
_verifier("la forme sans deux-points est acceptee et normalisee",
          instant_hecras("13OCT2014,0000") == "13OCT2014,00:00"
          and instant_hecras("13OCT2014,1200") == "13OCT2014,12:00")
_verifier("une heure invalide reste refusee sans deux-points",
          _leve(ValueError, instant_hecras, "13OCT2014,2500"))
# 24:00 = MINUIT EN FIN DE JOURNEE, convention HEC. C'est ainsi qu'un plan
# ecrit la fin d'une simulation d'une journee pleine, et le refuser
# bloquait le calage sur un plan valide (releve le 31/08/2026, second
# poste). La bascule sur le lendemain doit tenir sur les fins de mois,
# les annees bissextiles et les fins d'annee.
_verifier("24:00 bascule sur minuit du lendemain",
          instant_hecras("01Jan2000,2400") == "02JAN2000,00:00"
          and instant_hecras("01JAN2000,24:00") == "02JAN2000,00:00")
_verifier("la bascule tient sur une fin de mois et une fin d'annee",
          instant_hecras("31JAN2000,2400") == "01FEB2000,00:00"
          and instant_hecras("31DEC2000,2400") == "01JAN2001,00:00")
_verifier("la bascule connait les annees bissextiles",
          instant_hecras("28FEB2000,2400") == "29FEB2000,00:00"
          and instant_hecras("28FEB2001,2400") == "01MAR2001,00:00")
_verifier("24:30 est refuse : minuit est un instant, pas une heure",
          _leve(ValueError, instant_hecras, "01JAN2000,24:30"))

# _en_minutes SERT A MESURER UNE DUREE, pas seulement a ordonner. Il
# comptait 31 jours par mois : 28 fevrier -> 1er mars ressortait a 96 h.
# La duree ainsi calculee est celle de la fenetre de simulation, a
# laquelle conditions_trop_courtes() confronte chaque condition limite —
# un modele valide enjambant une fin de mois courte voyait donc TOUTES
# ses conditions declarees trop courtes.
def _duree_h(a, b):
    return (_en_minutes(instant_hecras(b))
            - _en_minutes(instant_hecras(a))) / 60.0

_verifier("une duree d'un jour vaut 24 h, quel que soit le mois",
          all(abs(_duree_h(a, b) - 24.0) < 1e-9 for a, b in (
              ("01JAN2000,00:00", "02JAN2000,00:00"),
              ("31JAN2000,00:00", "01FEB2000,00:00"),
              ("28FEB2001,00:00", "01MAR2001,00:00"),
              ("29FEB2000,00:00", "01MAR2000,00:00"),
              ("30APR2000,00:00", "01MAY2000,00:00"),
              ("31DEC2000,00:00", "01JAN2001,00:00"))))
_verifier("une journee pleine ecrite « 2400 » vaut bien 24 h",
          abs(_duree_h("01JAN2000,00:00", "01JAN2000,2400") - 24.0) < 1e-9)
_verifier("l'ordre chronologique est preserve",
          [_en_minutes(instant_hecras(x)) for x in (
              "01JAN2000,00:00", "01JAN2000,00:01", "02JAN2000,00:00",
              "01FEB2000,00:00", "01JAN2001,00:00")]
          == sorted(_en_minutes(instant_hecras(x)) for x in (
              "01JAN2000,00:00", "01JAN2000,00:01", "02JAN2000,00:00",
              "01FEB2000,00:00", "01JAN2001,00:00")))
_verifier("un intervalle bien forme est accepte",
          intervalle_hecras("0.2sec") == "0.2SEC")
_verifier("un intervalle sans unite est refuse",
          _leve(ValueError, intervalle_hecras, "10"))
_verifier("une fenetre inversee est refusee",
          _leve(ValueError, valider_fenetre_simulation,
                {"debut": "14OCT2014,00:00", "fin": "13OCT2014,00:00"}))
_verifier("une fenetre a moitie fournie est refusee",
          _leve(ValueError, valider_fenetre_simulation,
                {"debut": "13OCT2014,00:00"}))
_verifier("seules les cles fournies deviennent des lignes de plan",
          valider_fenetre_simulation({"intervalle_calcul": "2SEC"})
          == {"Computation Interval": "2SEC"})

# Lecture / ecriture sur un plan de la meme forme que ceux du projet.
_plan = Path(tempfile.gettempdir()) / "_essai_calage_plan.p01"
_plan.write_text(
    "Plan Title=Essai\n"
    "Simulation Date=13OCT2014,00:00,14OCT2014,04:00\n"
    "Geom File=g01\n"
    "Flow File=u01\n"
    "Computation Interval=1SEC\n"
    "Output Interval=1MIN\n"
    "Instantaneous Interval=1MIN\n"
    "Mapping Interval=1MIN\n",
    encoding="utf-8")
_lu = fenetre_simulation_du_plan(_plan)
_verifier("la fenetre se relit depuis un plan",
          _lu["debut"] == "13OCT2014,00:00"
          and _lu["fin"] == "14OCT2014,04:00"
          and _lu["intervalle_calcul"] == "1SEC")

class _PiloteMuet(PiloteHecRas):
    """Juste de quoi exercer l'ecriture, sans HEC-RAS ni ras-commander."""
    def __init__(self, dossier, **kw):
        self.dossier = Path(dossier)
        self.nom_projet = "_essai_calage_plan"
        self.fenetre_simulation = kw.get("fenetre_simulation")
        if self.fenetre_simulation:
            valider_fenetre_simulation(self.fenetre_simulation)

_PiloteMuet(_plan.parent, fenetre_simulation={
    "debut": "01JAN2022,06:00", "fin": "03JAN2022,18:30",
    "intervalle_calcul": "5SEC"})._ecrire_fenetre_simulation("01")
_relu = fenetre_simulation_du_plan(_plan)
_verifier("la fenetre imposee est bien ecrite dans le plan",
          _relu["debut"] == "01JAN2022,06:00"
          and _relu["fin"] == "03JAN2022,18:30"
          and _relu["intervalle_calcul"] == "5SEC")
_verifier("ce qui n'est pas precise reste celui du plan de reference",
          _relu["intervalle_sortie"] == "1MIN"
          and _relu["intervalle_mapping"] == "1MIN")
_verifier("les autres lignes du plan sont intactes",
          "Geom File=g01" in _plan.read_text(encoding="utf-8")
          and "Flow File=u01" in _plan.read_text(encoding="utf-8"))

_plan.write_text("Plan Title=Tronque\nGeom File=g01\n", encoding="utf-8")
_verifier("un plan sans les lignes attendues leve une erreur",
          _leve(ValueError,
                _PiloteMuet(_plan.parent, fenetre_simulation={
                    "debut": "01JAN2022,06:00",
                    "fin": "03JAN2022,18:30"})._ecrire_fenetre_simulation,
                "01"))
_plan.unlink(missing_ok=True)

# RETARD DE L'AXE TEMPOREL (cas reel du 30/10/2026) : l'entree non calee
# commence plus tard, l'apport a caler couvre la fenetre allongee.
_plan.write_text("Plan Title=Retard\n"
                 "Simulation Date=01JAN2022,00:00,01JAN2022,01:06\n",
                 encoding="utf-8")
_u_retard = Path(tempfile.gettempdir()) / "_essai_calage_plan.u01"
_amont = [0.5, 0.6, 1.0, 2.0, 3.5, 4.0, 3.0, 2.0, 1.5, 1.0, 0.8, 0.7]
_u_retard.write_text(
    "Flow Title=Retard\n"
    + ligne_localisation("AMONT", "Perimeter 1") + "\n"
    "Interval=6MIN\n"
    f"Flow Hydrograph= {len(_amont)} \n"
    + "\n".join(_table_debits(_amont)) + "\n"
    "Flow Hydrograph Slope= 0.01 \n"
    + ligne_localisation("APPORT", "Perimeter 1") + "\n"
    "Interval=6MIN\n"
    "Flow Hydrograph= 12 \n"
    + "\n".join(_table_debits([0.0] * 12)) + "\n"
    "Flow Hydrograph Slope= 0.01 \n",
    encoding="utf-8")

class _PiloteRetard(_PiloteMuet):
    def _bc_lines_connues(self):
        return None

_pr = _PiloteRetard(_plan.parent)
_pr.plan_travail, _pr.nom_zone_2d = "01", None
_pr.fichier_unsteady = _u_retard
_pr.duree_reference_h = 1.1
_pr.carte = cartographier_hydrogrammes(_u_retard)
_pr.originaux = {"AMONT": np.array(_amont), "APPORT": np.ones(12)}
_retard = _pr.retarder(0.25, ["APPORT"])
_cr = cartographier_hydrogrammes(_u_retard)
_va = lire_hydrogramme_unsteady(_u_retard, _cr["AMONT"]["debut"],
                                _cr["AMONT"]["fin"])
_vp = lire_hydrogramme_unsteady(_u_retard, _cr["APPORT"]["debut"],
                                _cr["APPORT"]["fin"])
_verifier("le retard est arrondi a dix pas", abs(_retard - 1.0) < 1e-9,
          f"{_retard} h")
_verifier("l'entree non calee commence dix pas plus tard",
          len(_va) == 22 and np.allclose(_va[:10], 0.5)
          and np.allclose(_va[10:], _amont), str(_va[:12]))
_verifier("l'apport a caler garde ses heures et couvre la fenetre",
          len(_vp) == 22, f"{len(_vp)} valeurs")
_verifier("les en-tetes annoncent les nouveaux comptes",
          _u_retard.read_text(encoding="utf-8").count(
              "Flow Hydrograph= 22 ") == 2)
_verifier("la fin de simulation recule d'autant",
          fenetre_simulation_du_plan(_plan)["fin"] == "01JAN2022,02:06"
          and abs(_pr.duree_reference_h - 2.1) < 1e-9,
          fenetre_simulation_du_plan(_plan)["fin"])
_verifier("les hydrogrammes retenus suivent le fichier",
          np.allclose(_pr.originaux["AMONT"], _va)
          and len(_pr.originaux["APPORT"]) == 22
          and _pr.originaux["APPORT"][0] == 1.0)
_verifier("un nombre de pas hors multiple de dix est refuse",
          _leve(ValueError, retarder_hydrogrammes, _u_retard, 5, []))
_u_retard.unlink(missing_ok=True)
_plan.unlink(missing_ok=True)

# -----------------------------------------------------------------------
# ETAPES CONSERVEES ET MENAGE DE FIN DE CALAGE
#
# Du code qui EFFACE des fichiers dans le projet d'un client n'avait aucun
# test. On fabrique donc un projet complet dans l'etat exact d'une fin de
# calage — etape du jour, etape homonyme d'une relance precedente, plans de
# l'utilisateur dont un piegeux appele « Q100 copy » — et on verifie
# fichier par fichier ce qui part et ce qui reste.
# -----------------------------------------------------------------------
print("\n--- Etapes conservees et menage de fin de calage ---")
_bac = Path(tempfile.mkdtemp(prefix="_essai_menage_"))
_NOM = "ESSAI"

def _batir_projet():
    for chemin in _bac.glob("*"):
        if chemin.is_file():
            chemin.unlink()
    plans = {"01": ("Q100", "g01", "u01"),          # plan de reference
             "02": ("Q100 copy", "g01", "u02"),     # PIEGE : plan a la main
             "10": ("Apport_A1", "g10", "u10"),     # etape d'une relance
             "11": ("Apport_A1", "g11", "u11")}     # etape du jour
    for numero, titre in {"01": "Q100", "02": "Q100 copy",
                          "10": "Apport_A1", "11": "Apport_A1"}.items():
        (_bac / f"{_NOM}.u{numero}").write_text(f"Flow Title={titre}\n",
                                                encoding="utf-8")
    for numero, titre in {"01": "Etat actuel", "10": "Geometrie_calage",
                          "11": "Geometrie_calage"}.items():
        (_bac / f"{_NOM}.g{numero}").write_text(f"Geom Title={titre}\n",
                                                encoding="utf-8")
    for numero, (titre, geom, flot) in plans.items():
        (_bac / f"{_NOM}.p{numero}").write_text(
            f"Plan Title={titre}\nShort Identifier={titre}\n"
            f"Geom File={geom}\nFlow File={flot}\n", encoding="utf-8")
        for gabarit in (".p{n}.hdf", ".b{n}", ".bco{n}", ".x{n}",
                        ".ic.o{n}"):
            (_bac / f"{_NOM}{gabarit.format(n=numero)}").write_bytes(b"x")
        (_bac / f"_compute_p{numero}.log").write_bytes(b"x")
    lignes = ["Proj Title=Essai\n"]
    lignes += [f"Geom File=g{n}\n" for n in ("01", "10", "11")]
    lignes += [f"Unsteady File=u{n}\n" for n in ("01", "02", "10", "11")]
    lignes += [f"Plan File=p{n}\n" for n in plans]
    (_bac / f"{_NOM}.prj").write_text("".join(lignes), encoding="utf-8")
    # Reliquats : sauvegardes horodatees et shapefiles transmis au pont.
    (_bac / f"{_NOM}.g01.sauvegarde_20260727_101500").write_bytes(b"x")
    (_bac / f"{_NOM}.u01.sauvegarde_20260727_101500").write_bytes(b"x")
    shp = _bac / "_calage"
    shp.mkdir(exist_ok=True)
    for nom in ("sections.shp", "sections.dbf", "injections.shp"):
        (shp / nom).write_bytes(b"x")

def _presents():
    return {p.name for p in _bac.glob("*") if p.is_file()}

def _objets():
    """Plans, unsteady et geometries encore presents."""
    return {n for n in _presents() if re.search(r"\.[pug][0-9][0-9]$", n)}

def _pilote_menage():
    p = PiloteHecRas(_bac, _NOM, plan_reference="01",
                     nom_clone_geometrie="Geometrie_calage")
    p.plan_travail = "11"
    return p

# 1. UN PLAN D'ETAPE HOMONYME D'UNE RELANCE PRECEDENTE EST REMPLACE, et lui
#    seul. C'est la seule suppression de plan que la chaine s'autorise
#    desormais : tout le reste est conserve pour servir de trace.
_batir_projet()
_efface = _pilote_menage()._remplacer_homonymes("Apport_A1")
_reste = _presents()
_prj = (_bac / f"{_NOM}.prj").read_text(encoding="utf-8")

_verifier("etapes : le plan de l'etape du jour est conserve",
          f"{_NOM}.p11" in _reste)
_verifier("etapes : le plan de reference est intact",
          f"{_NOM}.p01" in _reste)
# LE POINT LE PLUS IMPORTANT : une version anterieure supprimait tout plan
# dont le titre finit par « copy » — soit exactement ce que HEC-RAS ecrit
# sur un « Save Plan As ». Un plan fait a la main etait detruit.
_verifier("etapes : un plan de l'utilisateur nomme « ... copy » SURVIT",
          f"{_NOM}.p02" in _reste and f"{_NOM}.u02" in _reste)
_verifier("etapes : l'homonyme de la relance precedente est parti",
          f"{_NOM}.p10" not in _reste)
_verifier("etapes : son unsteady orphelin est parti",
          f"{_NOM}.u10" not in _reste)
_verifier("etapes : sa geometrie orpheline est partie",
          f"{_NOM}.g10" not in _reste)
_verifier("etapes : la geometrie de l'etape du jour est conservee",
          f"{_NOM}.g11" in _reste)
_verifier("etapes : aucun derive d'un plan supprime ne subsiste",
          not any(n in _reste for n in
                  (f"{_NOM}.p10.hdf", f"{_NOM}.b10", f"{_NOM}.bco10",
                   f"{_NOM}.x10", f"{_NOM}.ic.o10", "_compute_p10.log")))
_verifier("etapes : le .prj suit les suppressions",
          "Plan File=p10" not in _prj and "Geom File=g10" not in _prj
          and "Unsteady File=u10" not in _prj)
_verifier("etapes : le .prj declare toujours ce qui reste",
          all(f"Plan File=p{n}" in _prj for n in ("01", "02", "11"))
          and "Geom File=g11" in _prj)
_verifier("etapes : le compte rendu enumere ce qui est parti",
          set(_efface) == {"p10", "u10", "g10"}, str(_efface))

# 1 bis. UNE GEOMETRIE ET UN FLUX SANS PLAN RESTENT. Le remplacement
#    balayait tout .uNN et tout .gNN qu'aucun plan ne designe : une
#    variante que l'ingenieur garde de cote, sans plan, disparaissait
#    sans sauvegarde (audit du 11/10/2026). Ne partent que le flux et la
#    geometrie du plan REMPLACE.
_batir_projet()
(_bac / f"{_NOM}.g05").write_text("Geom Title=Variante gardee\n",
                                  encoding="utf-8")
(_bac / f"{_NOM}.u05").write_text("Flow Title=Hydrogramme garde\n",
                                  encoding="utf-8")
with open(_bac / f"{_NOM}.prj", "a", encoding="utf-8") as _f:
    _f.write("Geom File=g05\nUnsteady File=u05\n")
_efface = _pilote_menage()._remplacer_homonymes("Apport_A1")
_prj = (_bac / f"{_NOM}.prj").read_text(encoding="utf-8")
_verifier("etapes : une geometrie et un flux SANS PLAN restent",
          {f"{_NOM}.g05", f"{_NOM}.u05"} <= _presents(), str(_efface))
_verifier("etapes : le .prj les declare toujours",
          "Geom File=g05" in _prj and "Unsteady File=u05" in _prj)
_verifier("etapes : le flux et la geometrie du plan remplace partent, eux",
          set(_efface) == {"p10", "u10", "g10"}, str(_efface))

# 1 ter. CE QUE LE PLAN REMPLACE PARTAGE AVEC UN PLAN RESTANT RESTE. Ici
#    l'homonyme tourne sur la geometrie du plan de reference ; g10, que
#    plus aucun plan ne designe, n'etait pas la sienne et reste aussi.
_batir_projet()
(_bac / f"{_NOM}.p10").write_text(
    "Plan Title=Apport_A1\nShort Identifier=Apport_A1\n"
    "Geom File=g01\nFlow File=u10\n", encoding="utf-8")
_efface = _pilote_menage()._remplacer_homonymes("Apport_A1")
_verifier("etapes : une geometrie partagee avec un plan restant reste",
          {f"{_NOM}.g01", f"{_NOM}.g10"} <= _presents()
          and set(_efface) == {"p10", "u10"}, str(_efface))

# 2. UN PLAN D'UNE AUTRE ETAPE N'EST JAMAIS TOUCHE. C'est ce qui permet de
#    reprendre un calage a l'apport A2 sans perdre l'etape A1.
_batir_projet()
_pilote_menage()._remplacer_homonymes("Apport_A2")
_verifier("etapes : une etape d'un autre nom est intacte",
          {f"{_NOM}.p10", f"{_NOM}.u10", f"{_NOM}.g10"} <= _presents())

# 3. LE MENAGE DE FIN NE TOUCHE PLUS AUX PLANS. Il ne retire que ce que
#    personne ne reclame : sauvegardes de preparation et shapefiles
#    transmis au pont.
_batir_projet()
_temoin = _objets()
_bilan = _pilote_menage().nettoyer_reliquats()
_verifier("menage : les sauvegardes horodatees sont retirees",
          not any("sauvegarde_" in n for n in _presents()))
_verifier("menage : un _calage/ qui ne portait que les shapefiles du pont "
          "est retire", not (_bac / "_calage").exists())
_verifier("menage : AUCUN plan, unsteady ou geometrie n'est supprime",
          _objets() == _temoin, f"{sorted(_temoin - _objets())} manquant(s)")
_verifier("menage : les reliquats sont enumeres dans le compte rendu",
          sorted(_bilan["reliquats"])
          == [f"{_NOM}.g01.sauvegarde_20260727_101500",
              f"{_NOM}.u01.sauvegarde_20260727_101500",
              "injections.shp", "sections.dbf", "sections.shp"],
          str(_bilan["reliquats"]))
_verifier("menage : simuler=True ne retire rien",
          _pilote_menage().nettoyer_reliquats(simuler=True)["conserve"]
          == "p11")

# 3 bis. LE DOSSIER DE SORTIE EST INTOUCHABLE. Depuis la 0.9.8 le plugin
#    le propose dans « _calage/<prefixe> ». Le menage retirait TOUT
#    _calage/ : le classeur, le JSON, le suivi et les livrables d'un
#    calage qui venait d'aboutir partaient avec les shapefiles (audit du
#    11/10/2026). Le dernier temoin est a la racine de _calage/, pour le
#    cas ou l'utilisateur y met lui-meme sa sortie : « sections.* » ne
#    doit pas devenir « sections* ».
_batir_projet()
_sortie = _bac / "_calage" / "Q100"
_gardes = [_sortie / "donnees_calage_Q100.xlsx",
           _sortie / "donnees_calage_Q100.json",
           _sortie / "sections_controle.shp",
           _sortie / "suivi" / "avancement.json",
           _sortie / "resultats_finaux" / "synthese.md",
           _bac / "_calage" / "sections_controle.shp"]
for _f in _gardes:
    _f.parent.mkdir(parents=True, exist_ok=True)
    _f.write_bytes(b"x")
_bilan = _pilote_menage().nettoyer_reliquats()
_verifier("menage : le dossier de sortie _calage/<prefixe> garde tout",
          all(f.is_file() for f in _gardes),
          f"{[f.name for f in _gardes if not f.is_file()]} perdu(s)")
_verifier("menage : les shapefiles transmis au pont partent quand meme",
          not any((_bac / "_calage" / n).exists() for n in
                  ("sections.shp", "sections.dbf", "injections.shp")),
          str(_bilan["reliquats"]))
shutil.rmtree(_bac / "_calage", ignore_errors=True)

# 4. RETROUVER UN PLAN PAR SON TITRE : c'est ce sur quoi repose la reprise
#    a un apport donne.
_batir_projet()
_verifier("plan_par_titre : trouve le plan de reference",
          plan_par_titre(_bac, _NOM, "Q100") == "01")
_verifier("plan_par_titre : rend None sur un titre inconnu",
          plan_par_titre(_bac, _NOM, "Apport_A9") is None)
_verifier("plan_par_titre : sur deux homonymes, rend le plus recent",
          plan_par_titre(_bac, _NOM, "Apport_A1") in ("10", "11"))

# 5. Titrage d'un unsteady : jalonner() s'en sert pour nommer l'etape.
_pilote_menage()._renommer_unsteady("11", "Apport_A2")
_verifier("titrage : le Flow Title est reecrit",
          "Flow Title=Apport_A2"
          in (_bac / f"{_NOM}.u11").read_text(encoding="utf-8"))

# 6. LE PLAN FINAL EST UN RETITRAGE, PAS UN CLONE. Le plan de la derniere
#    etape porte deja tous les apports cales ET ses resultats ; un clone
#    n'emporterait pas son .hdf et serait muet dans RAS Mapper.
_batir_projet()
_p = _pilote_menage()
_p.fichier_unsteady = _bac / f"{_NOM}.u11"
_p.etapes = ["Q100-Apport_A1"]
_rendu = _p.conclure("Q100_avec_apports")
_p11 = (_bac / f"{_NOM}.p11").read_text(encoding="utf-8")
_verifier("plan final : le plan de la derniere etape porte le titre final",
          "Plan Title=Q100_avec_apports" in _p11, _rendu)
_verifier("plan final : le Short Identifier suit",
          "Short Identifier=Q100_avec_apports" in _p11)
_verifier("plan final : l'unsteady du plan courant suit",
          "Flow Title=Q100_avec_apports"
          in (_bac / f"{_NOM}.u11").read_text(encoding="utf-8"))
_verifier("plan final : ses resultats sont conserves (aucun clone)",
          (_bac / f"{_NOM}.p11.hdf").is_file())
_verifier("plan final : aucun plan cree ni supprime — les quatre sont la",
          len(list(_bac.glob(f"{_NOM}.p[0-9][0-9]"))) == 4,
          str(sorted(p.name
                     for p in _bac.glob(f"{_NOM}.p[0-9][0-9]"))))
_verifier("plan final : l'etape courante est rebaptisee, pas ajoutee",
          _p.etapes == ["Q100_avec_apports"], str(_p.etapes))

# RAS MAPPER NOMME LA COUCHE D'APRES LE HDF (28/09/2026) : sans ce
# retitrage, le plan final s'affichait sous le nom de la derniere etape.
import h5py as _h5
(_bac / f"{_NOM}.p11.hdf").unlink()
with _h5.File(_bac / f"{_NOM}.p11.hdf", "w") as _h:
    _info = _h.create_group("Plan Data/Plan Information").attrs
    for _cle in ("Plan Name", "Plan ShortID", "Plan Title", "Flow Title"):
        _info[_cle] = np.bytes_(b"Q100-Apport_A1")
_rendu = _p.conclure("Q100_avec_apports")
with _h5.File(_bac / f"{_NOM}.p11.hdf", "r") as _h:
    _lu = dict(_h["Plan Data/Plan Information"].attrs)
_verifier("plan final : le .hdf porte le titre final (RAS Mapper le lit)",
          all(_lu[c] == b"Q100_avec_apports" for c in
              ("Plan Name", "Plan ShortID", "Plan Title", "Flow Title")),
          f"{_rendu} | {_lu}")

# --- LE PLAN FINAL EST DECLARE A RAS MAPPER (21/09/2026) --------------
# Constate sur deux modeles reels : la chaine laissait des plans avec
# des centaines de Mo de resultats que RAS Mapper ne montrait pas. Son
# arbre « Results » liste ce que le .rasmap declare ; ras-commander ne
# l'ecrit jamais. Sur l'un des deux, treize plans calcules, zero declare.
from xml.etree import ElementTree as _ET

_rasmap = _bac / f"{_NOM}.rasmap"
_rasmap.write_text(
    '<RASMapper>\n  <Results Checked="True">\n'
    '    <Layer Name="Q100" Type="RASResults" Filename=".\\'
    + _NOM + '.p01.hdf" />\n  </Results>\n</RASMapper>\n',
    encoding="utf-8")
_avant_rasmap = _rasmap.read_text(encoding="utf-8")
_dit = _p._declarer_resultats_rasmap("11", "Q100_avec_apports")
_lu = _rasmap.read_text(encoding="utf-8")
_verifier("rasmap : le plan final y est declare", "declare" in _dit, _dit)
_verifier("rasmap : le fichier reste du XML valide",
          _ET.fromstring(_lu) is not None)
_noms = [c.get("Name") for c in _ET.fromstring(_lu).find("Results")
         if c.get("Type") == "RASResults"]
_verifier("rasmap : la couche s'ajoute sans retirer les existantes",
          _noms == ["Q100", "Q100_avec_apports"], str(_noms))
_verifier("rasmap : elle designe le .hdf du plan final",
          f'Filename=".\\{_NOM}.p11.hdf"' in _lu)
# IDEMPOTENT, ET C'EST LE FICHIER QUI IDENTIFIE : relancer un calage sur
# le meme scenario ne doit pas empiler les couches, et un retitrage doit
# renommer celle qui existe — son nom vient justement de changer.
_p._declarer_resultats_rasmap("11", "Q100_avec_apports")
_p._declarer_resultats_rasmap("11", "Q100_final")
_noms = [c.get("Name") for c in
         _ET.fromstring(_rasmap.read_text(encoding="utf-8")).find("Results")
         if c.get("Type") == "RASResults"]
_verifier("rasmap : un second passage renomme au lieu d'empiler",
          _noms == ["Q100", "Q100_final"], str(_noms))
# UN TITRE A CARACTERE XML NE CASSE PAS LE FICHIER DE L'UTILISATEUR.
_p._declarer_resultats_rasmap("11", 'Q100 & "bis"')
_verifier("rasmap : un titre a esperluette est echappe",
          _ET.fromstring(_rasmap.read_text(encoding="utf-8")) is not None
          and "&amp;" in _rasmap.read_text(encoding="utf-8"))
# SANS BLOC <Results>, ON NE DEVINE PAS : on le dit et on ne touche rien.
_rasmap.write_text("<RASMapper>\n</RASMapper>\n", encoding="utf-8")
_dit = _p._declarer_resultats_rasmap("11", "Q100_avec_apports")
_verifier("rasmap : sans bloc <Results>, on ne touche a rien et on le dit",
          "Results" in _dit
          and _rasmap.read_text(encoding="utf-8")
          == "<RASMapper>\n</RASMapper>\n", _dit)
# ET SANS .rasmap DU TOUT, un calage abouti n'echoue pas pour autant.
_rasmap.unlink()
_dit = _p._declarer_resultats_rasmap("11", "Q100_avec_apports")
_verifier("rasmap : absent, le calage ne rate pas — il le dit",
          "aucun" in _dit.lower(), _dit)
_verifier("plan final : conclure() avant preparer() est refuse",
          _leve(RuntimeError,
                PiloteHecRas(_bac, _NOM, plan_reference="01").conclure,
                "Q100_avec_apports"))

# 7. LA TRONCATURE SILENCIEUSE DU SHORT IDENTIFIER EST PARTIE. C'est elle
#    qui fabriquait le doublon : un plan de reprise du depot porte encore
#    « sans apport XXX et ava », rogne d'un « l » depuis toujours.
_batir_projet()
_p = _pilote_menage()
_p.fichier_unsteady = _bac / f"{_NOM}.u11"
_long = "Riviere1-Q100_avec_apports"                # 26 caracteres
_p.conclure(_long)
_verifier("short id : un titre de 26 caracteres est ecrit ENTIER",
          f"Short Identifier={_long}\n"
          in (_bac / f"{_NOM}.p11").read_text(encoding="utf-8"))
# RETROCOMPATIBILITE, OCTET POUR OCTET : le bourrage a 24 reste, et rend la
# ligne exacte des 34 plans deja ecrits par la chaine dans 01-cas_test.
_p.conclure("sans_apport")
_verifier("short id : un titre court reste complete a 24, octet pour octet",
          "Short Identifier=" + "sans_apport".ljust(24) + "\n"
          in (_bac / f"{_NOM}.p11").read_text(encoding="utf-8"))

# 8. UN ETAT FINAL HOMONYME D'UN CALAGE PRECEDENT EST REMPLACE, comme une
#    etape : deux « Q100_avec_apports » ne diraient plus lequel fait foi.
_batir_projet()
(_bac / f"{_NOM}.p10").write_text(
    "Plan Title=Q100_avec_apports\n"
    "Short Identifier=Q100_avec_apports\n"
    "Geom File=g10\nFlow File=u10\n", encoding="utf-8")
_p = _pilote_menage()
_p.fichier_unsteady = _bac / f"{_NOM}.u11"
_rendu = _p.conclure("Q100_avec_apports")
_verifier("plan final : l'etat final d'un calage precedent est remplace",
          not (_bac / f"{_NOM}.p10").exists()
          and (_bac / f"{_NOM}.p11").exists(), _rendu)

# 9. ELAGAGE DES ETAPES, SUR DEMANDE. La chaine les conserve ; cette
#    methode-ci les retire APRES COUP, et seulement si le calage a
#    conclu. C'est la seule suppression de plan que l'utilisateur puisse
#    demander, et elle ne doit emporter que ce qui lui appartient.
def _titrer(numero, titre, geom, flot):
    (_bac / f"{_NOM}.p{numero}").write_text(
        f"Plan Title={titre}\nShort Identifier={titre}\n"
        f"Geom File={geom}\nFlow File={flot}\n", encoding="utf-8")

_batir_projet()
_titrer("10", "Q100-sans", "g10", "u10")
_titrer("02", "Q100-A1", "g10", "u02")
_titrer("11", "Q100", "g11", "u11")
_p = _pilote_menage()
_p.plan_travail = None          # le calage est fini : plus de plan courant

_avant = _objets()
_simule = _p.elaguer_etapes("Q100", ["A1"], simuler=True)
_verifier("elagage : la simulation annonce les deux etapes",
          _simule["etapes"] == ["02", "10"], str(_simule))
_verifier("elagage : la simulation ne retire RIEN",
          _objets() == _avant,
          f"{sorted(_avant - _objets())} manquant(s)")

_fait = _p.elaguer_etapes("Q100", ["A1"], simuler=False)
_verifier("elagage : les plans d'etape sont partis",
          not (_bac / f"{_NOM}.p10").exists()
          and not (_bac / f"{_NOM}.p02").exists(), str(_fait))
_verifier("elagage : le plan final est intact, AVEC ses resultats",
          (_bac / f"{_NOM}.p11").exists()
          and (_bac / f"{_NOM}.p11.hdf").exists())
_verifier("elagage : le plan de reference n'est pas touche",
          (_bac / f"{_NOM}.p01").exists())
_verifier("elagage : les derives des plans retires partent avec eux",
          not (_bac / f"{_NOM}.p10.hdf").exists()
          and not (_bac / "_compute_p10.log").exists())
_verifier("elagage : l'unsteady que seul un plan retire designait part",
          not (_bac / f"{_NOM}.u02").exists(), str(_fait["supprimes"]))
_verifier("elagage : le .prj ne declare plus les plans retires",
          "Plan File=p10" not in (_bac / f"{_NOM}.prj").read_text(
              encoding="utf-8"))

# LE GARDE-FOU QUI COMPTE : sans plan final, les etapes sont TOUT ce qui
# reste du calage. Les retirer l'effacerait. LE PLAN DE REFERENCE, TITRE ICI
# « Q100 », NE VAUT PAS PLAN FINAL.
_batir_projet()
_titrer("10", "Q100-sans", "g10", "u10")
_titrer("11", "Q100-A1", "g11", "u11")
_p = _pilote_menage()
_p.plan_travail = None
_avant = _objets()
_refus = _p.elaguer_etapes("Q100", ["A1"], simuler=False)
_verifier("elagage : sans plan final, on REFUSE et l'on dit pourquoi",
          "refus" in _refus and "n'a pas conclu" in _refus["refus"],
          str(_refus)[:90])
_verifier("elagage : le refus ne retire rien",
          _objets() == _avant,
          f"{sorted(_avant - _objets())} manquant(s)")

# UN PLAN QUI N'EST PAS DE NOUS RESTE, quel que soit son titre.
_batir_projet()
_titrer("10", "Q100-sans", "g10", "u10")
_titrer("11", "Q100", "g11", "u11")
_p = _pilote_menage()
_p.plan_travail = None
_p.elaguer_etapes("Q100", ["A1"], simuler=False)
_verifier("elagage : le plan « Q100 copy » de l'utilisateur reste",
          (_bac / f"{_NOM}.p02").exists())
# ET LE PREFIXE ISOLE LES SERIES : elaguer le Q10 ne touche pas au Q100.
_batir_projet()
_titrer("10", "Q100-sans", "g10", "u10")
_titrer("11", "Q10", "g11", "u11")
_p = _pilote_menage()
_p.plan_travail = None
_p.elaguer_etapes("Q10", ["A1"], simuler=False)
_verifier("elagage : le prefixe isole les series — le Q100 est intact",
          (_bac / f"{_NOM}.p10").exists())
# UN SCENARIO DONT LE NOM COMMENCE PAR L'AUTRE : « Q100-V2 » et ses etapes
# ne sont pas des etapes de « Q100 ».
_batir_projet()
_titrer("10", "Q100-sans", "g10", "u10")
_titrer("11", "Q100", "g11", "u11")
_titrer("02", "Q100-V2", "g10", "u02")
_p = _pilote_menage()
_p.plan_travail = None
_simule = _p.elaguer_etapes("Q100", ["A1"], simuler=True)
_verifier("elagage : « Q100-V2 » n'est pas une etape de « Q100 »",
          _simule["etapes"] == ["10"], str(_simule))
# LE PLAN DE REFERENCE PORTANT LE TITRE FINAL N'EST JAMAIS REMPLACE.
_batir_projet()
_titrer("11", "Q100", "g11", "u11")
_verifier("plans_par_titre rend tous les plans de ce titre",
          plans_par_titre(_bac, _NOM, "Q100") == ["01", "11"],
          str(plans_par_titre(_bac, _NOM, "Q100")))
_p = _pilote_menage()
_p.plan_travail = "10"
_efface = _p._remplacer_homonymes("Q100")
_verifier("plan final : le plan de reference homonyme reste, l'autre part",
          (_bac / f"{_NOM}.p01").exists()
          and not (_bac / f"{_NOM}.p11").exists(), str(_efface))
# SAUF SI L'INGENIEUR L'A ACCEPTE (10/11/2026) : recalage d'un plan valide
# qui garde son nom. Le plan source part alors avec ses resultats et sa
# couche du .rasmap ; la couche voisine reste.
_batir_projet()
_titrer("11", "Q100", "g11", "u11")
(_bac / f"{_NOM}.rasmap").write_text(
    "<RASMapper>\n  <Results>\n"
    + PiloteHecRas._GABARIT_RASRESULTS.format(
        titre="Q100", fichier=f".\\{_NOM}.p01.hdf")
    + PiloteHecRas._GABARIT_RASRESULTS.format(
        titre="Autre", fichier=f".\\{_NOM}.p02.hdf")
    + "  </Results>\n</RASMapper>\n", encoding="utf-8")
_p = PiloteHecRas(_bac, _NOM, plan_reference="01", plan_a_remplacer="p01")
_p.plan_travail = "11"
_efface = _p._remplacer_homonymes("Q100")
_rasmap = (_bac / f"{_NOM}.rasmap").read_text(encoding="utf-8")
_verifier("plan final : le plan source a remplacer part, resultats compris",
          not (_bac / f"{_NOM}.p01").exists()
          and not (_bac / f"{_NOM}.p01.hdf").exists()
          and (_bac / f"{_NOM}.p11").exists(), str(_efface))
_verifier("plan final : sa couche quitte le .rasmap, la voisine reste",
          f"{_NOM}.p01.hdf" not in _rasmap and f"{_NOM}.p02.hdf" in _rasmap
          and _rasmap.count('Type="RASResults"') == 1
          and _ET.fromstring(_rasmap) is not None,
          _rasmap[:300].replace("\n", " "))

_verifier("detection de HEC-RAS ouvert : repond sans lever",
          hecras_ouvert() in (True, False, None), str(hecras_ouvert()))

# -----------------------------------------------------------------------
# ENCODAGE ET FINS DE LIGNE (audit du 11/10/2026)
#
# HEC-RAS ecrit en cp1252 et en CRLF. La chaine relisait juste, puis
# reecrivait TOUT le fichier en UTF-8 : le titre accentue d'un plan, d'un
# unsteady ou du projet ressortait « Ã© » dans HEC-RAS. Et la lecture
# essayait latin1 avant cp1252 : latin1 lit tout octet, cp1252 n'etait
# jamais atteint, le tiret long (0x97) et « œ » (0x9C) devenaient des
# caracteres de controle.
#   LA REGLE : un fichier relu puis reecrit garde son encodage, sa fin de
# ligne, et chaque octet des lignes qu'on n'a pas voulu changer.
# -----------------------------------------------------------------------
print("\n--- Encodage : un fichier reecrit garde ses octets ---")
_ACCENTS = "Crue décennale — état aménagé, bœuf"

def _lignes_perdues(avant, apres):
    """Lignes d'« avant », octets et fin de ligne compris, absentes d'« apres »."""
    reste = apres.splitlines(keepends=True)
    return [l for l in avant.splitlines(keepends=True) if l not in reste]

_batir_projet()
_p = _pilote_menage()
_p11 = _bac / f"{_NOM}.p11"
_avant = ("Plan Title=Apport_A1\r\nShort Identifier=Apport_A1\r\n"
          "Geom File=g11\r\nFlow File=u11\r\n"
          f"BEGIN DESCRIPTION:\r\n{_ACCENTS}\r\nEND DESCRIPTION:\r\n"
          ).encode("cp1252")
_p11.write_bytes(_avant)
_verifier("encodage : un texte cp1252 se lit juste, tiret long et « œ » "
          "compris", _ACCENTS in _lire_texte(_p11),
          repr(_lire_texte(_p11).splitlines()[5]))
_p._renommer_plan("11", "Q100_Apport_A1")
_verifier("encodage : retitrer un plan cp1252 ne change que ses deux lignes",
          _lignes_perdues(_avant, _p11.read_bytes())
          == [b"Plan Title=Apport_A1\r\n", b"Short Identifier=Apport_A1\r\n"]
          and b"Plan Title=Q100_Apport_A1\r\n" in _p11.read_bytes(),
          repr(_p11.read_bytes()[:120]))
_avant = _p11.read_bytes()
_p._reassigner_unsteady("11", "10")
_verifier("encodage : rattacher un unsteady ne change que « Flow File= »",
          _lignes_perdues(_avant, _p11.read_bytes())
          == [b"Flow File=u11\r\n"]
          and b"Flow File=u10\r\n" in _p11.read_bytes())

# LE .prj DU PROJET, fichier d'origine : une ligne retiree, rien d'autre.
_prj_essai = _bac / f"{_NOM}.prj"
_avant = (f"Proj Title={_ACCENTS}\r\nPlan File=p01\r\nPlan File=p99\r\n"
          "Geom File=g01\r\n").encode("cp1252")
_prj_essai.write_bytes(_avant)
_p._nettoyer_prj()
_verifier("encodage : le .prj garde son titre accentue, a l'octet pres",
          _prj_essai.read_bytes()
          == _avant.replace(b"Plan File=p99\r\n", b""),
          repr(_prj_essai.read_bytes()[:60]))

# L'UNSTEADY D'ORIGINE, ou le plugin cree l'hydrogramme d'une injection.
_u_essai = _bac / f"{_NOM}.u01"
_avant = (f"Flow Title={_ACCENTS}\r\nProgram Version=6.60\r\n"
          + ligne_localisation("Amont", "Zone") + "\r\n"
          "Interval=1HOUR\r\nFlow Hydrograph= 2 \r\n"
          "      10      20\r\n").encode("cp1252")
_u_essai.write_bytes(_avant)
ajouter_condition_limite_debit(_u_essai, "A1", "Zone", [1.0, 2.0, 3.0])
_apres = _u_essai.read_bytes()
_verifier("encodage : creer un hydrogramme ne touche a aucune ligne de "
          "l'unsteady d'origine", _lignes_perdues(_avant, _apres) == []
          and _champ("A1", 32).encode() in _apres,
          repr(_apres[:60]))
_verifier("encodage : le bloc ajoute prend la fin de ligne du fichier",
          _apres.count(b"\n") == _apres.count(b"\r\n"))

# CE QUI ETAIT EN UTF-8 ET EN LF LE RESTE : on ne convertit rien.
_u11 = _bac / f"{_NOM}.u11"
_avant = (f"Flow Title=Apport_A1\nBEGIN DESCRIPTION:\n{_ACCENTS}\n"
          "END DESCRIPTION:\n").encode("utf-8")
_u11.write_bytes(_avant)
_p._renommer_unsteady("11", "Q100_Apport_A1")
_verifier("encodage : un fichier UTF-8 en LF reste en UTF-8 et en LF",
          _u11.read_bytes() == _avant.replace(
              b"Flow Title=Apport_A1\n", b"Flow Title=Q100_Apport_A1\n"),
          repr(_u11.read_bytes()[:60]))

# NI UTF-8 NI cp1252 (0x81 n'existe pas en cp1252) : latin-1 en dernier
# recours, qui rend chaque octet tel quel.
_u02 = _bac / f"{_NOM}.u02"
_u02.write_bytes(b"Flow Title=Q100 copy\r\nNote=\x81\xe9\r\n")
_p._renommer_unsteady("02", "Q100")
_verifier("encodage : un fichier d'encodage inconnu garde ses octets",
          _u02.read_bytes() == b"Flow Title=Q100\r\nNote=\x81\xe9\r\n",
          repr(_u02.read_bytes()))

# L'ASCII PUR EST DU cp1252 (decision du 11/10/2026, regle de la maison) :
# un accent neuf y prend UN octet, comme HEC-RAS l'ecrit. Le .rasmap,
# que RAS Mapper ecrit en UTF-8, fait exception.
_u10 = _bac / f"{_NOM}.u10"
_u10.write_bytes(b"Flow Title=Apport_A1\r\n")
_p._renommer_unsteady("10", "Été")
_verifier("encodage : un accent ecrit dans un fichier ASCII l'est en "
          "cp1252", _u10.read_bytes() == b"Flow Title=\xc9t\xe9\r\n",
          repr(_u10.read_bytes()))
_u10.write_bytes(b"Flow Title=Q100\r\n"
                 + ligne_localisation("Amont", "Zone").encode() + b"\r\n")
ajouter_condition_limite_debit(_u10, "Écluse", "Zone", [1.0, 2.0])
_verifier("encodage : un nom d'apport accentue ajoute a un unsteady ASCII "
          "l'est en cp1252, comme dans la geometrie",
          _champ("Écluse", 32).encode("cp1252") in _u10.read_bytes()
          and b"\xc3" not in _u10.read_bytes(), repr(_u10.read_bytes()[:90]))
_rasmap_ascii = _bac / "ascii.rasmap"
_rasmap_ascii.write_bytes(b"<RASMapper>\r\n</RASMapper>\r\n")
_ecrire_texte(_rasmap_ascii, '<RASMapper Name="Été">\n</RASMapper>\n')
_verifier("encodage : un .rasmap ASCII aussi, que RAS Mapper lit en UTF-8",
          _rasmap_ascii.read_bytes()
          == b'<RASMapper Name="\xc3\x89t\xc3\xa9">\r\n</RASMapper>\r\n',
          repr(_rasmap_ascii.read_bytes()))
# REFUSER PLUTOT QUE TRONQUER : « → » n'existe pas en cp1252. Avant, le
# fichier entier passait en UTF-8 sans un mot.
_avant = _u_essai.read_bytes()
_verifier("encodage : un caractere que le fichier ne sait pas ecrire est "
          "refuse, fichier intact",
          _leve(ValueError, _p._renommer_unsteady, "01", "Q100 → aval")
          and _u_essai.read_bytes() == _avant,
          repr(_u_essai.read_bytes()[:40]))
_corps = Path(pilote_hecras.__file__).read_text(encoding="utf-8").split(
    '\nif __name__ == "__main__":')[0]
_verifier("encodage : plus aucune ecriture ne force l'UTF-8 hors du banc",
          "write_text(" not in _corps,
          f"{_corps.count('write_text(')} « write_text( »")
shutil.rmtree(_bac, ignore_errors=True)

# -----------------------------------------------------------------------
# LES ECRITURES DE ras-commander (decision du 11/10/2026)
#
# ras-commander relit et reecrit en UTF-8 errors="replace" : a chaque
# clone, essai ou calcul, un accent cp1252 devenait EF BF BD. Mesure sur
# ce meme projet : le .prj perdait son titre ; la geometrie clonee,
# « Forêt » et la BC line « Écluse », que preparer() retirait alors de la
# carte sans un mot ; l'unsteady de la 2e etape, « Écluse » a son tour.
#   Le calage tourne ici pour de vrai, CALCUL EXCLU : RasCmdr.compute_plan
# est remplace par un leurre, et AUCUN HEC-RAS n'est lance. Le vrai
# compute_plan, arrete au lancement de Ras.exe : src/test_calcul_accents.py.
# -----------------------------------------------------------------------
print("\n--- Encodage a travers ras-commander : clones, essais, calcul ---")
from ras_commander import RasCmdr
_bac = Path(tempfile.mkdtemp(prefix="_essai_clones_"))

def _cp1252(*lignes):
    return "".join(f"{l}\r\n" for l in lignes).encode("cp1252")

(_bac / "ESSAI.prj").write_bytes(_cp1252(
    "Proj Title=Étude de dangers – digue", "Current Plan=p01", "SI Units",
    "Geom File=g01", "Unsteady File=u01", "Plan File=p01",
    "BEGIN DESCRIPTION:", "Modèle calé en février", "END DESCRIPTION:"))
(_bac / "ESSAI.p01").write_bytes(_cp1252(
    "Plan Title=Crue décennale", "Program Version=6.60",
    "Short Identifier=Q10 aménagé",
    "Simulation Date=01JAN2024,0000,02JAN2024,0000", "Geom File=g01",
    "Flow File=u01", "UNET D2 Cores= 0", "BEGIN DESCRIPTION:",
    "État aménagé", "END DESCRIPTION:"))
(_bac / "ESSAI.g01").write_bytes(_cp1252(
    "Geom Title=Géométrie état aménagé", "Program Version=6.60",
    "Storage Area=Zone Test       ,,", f"BC Line Name={'Amont':<40}",
    f"BC Line Name={'Écluse':<40}", "LCMann Region Name=Forêt"))
(_bac / "ESSAI.u01").write_bytes(_cp1252(
    "Flow Title=Crue décennale", "Program Version=6.60",
    ligne_localisation("Amont", "Zone Test"), "Interval=1HOUR",
    "Flow Hydrograph= 25 ", "      10" * 10, "      10" * 10,
    "      10" * 5, "Flow Hydrograph Slope= 0.01 "))
ajouter_condition_limite_debit(_bac / "ESSAI.u01", "Écluse", "Zone Test",
                               [1.0] * 25, intervalle="1HOUR")
_origine = {f.suffix: f.read_bytes() for f in _bac.iterdir()}
_vrai_calcul = RasCmdr.compute_plan
_p = PiloteHecRas(_bac, "ESSAI", plan_reference="01", version="6.6",
                  nom_zone_2d="Zone Test", geometrie_override="01",
                  nom_clone_geometrie="Géométrie calage",
                  fermer_orphelins=False, coeurs=2)
try:
    _p.preparer()
    _carte = sorted(_p.carte)
    _p.jalonner("sans apport")
    _p.jalonner("Apport_Écluse")
    _p.appliquer_facteur("Écluse", 1.5)
    RasCmdr.compute_plan = staticmethod(lambda *a, **k: False)
    if RasCmdr.compute_plan("leurre") is False:     # jamais de vrai calcul
        _p.calculer()
    _arret = ""
except Exception as e:                                   # noqa: BLE001
    _arret = f"{type(e).__name__}: {e}"
finally:
    RasCmdr.compute_plan = _vrai_calcul
_octets = {f.suffix: f.read_bytes() for f in _bac.iterdir()}
_verifier("ras-commander : le calage va jusqu'au calcul exclu",
          not _arret, _arret[:150])
_verifier("ras-commander : le .prj garde chaque octet, ses lignes neuves "
          "en cp1252 et CRLF", _octets.get(".prj") == _origine[".prj"]
          + b"Geom File=g02\r\nPlan File=p02\r\nUnsteady File=u02\r\n"
          b"Unsteady File=u03\r\nPlan File=p03\r\n",
          repr(_octets.get(".prj", b"")[:48]))
_verifier("ras-commander : la geometrie clonee ne change que son titre, "
          "BC line « Écluse » et « Forêt » comprises",
          _octets.get(".g02") == _origine[".g01"].replace(
              "Géométrie état aménagé".encode("cp1252"),
              "Géométrie calage".encode("cp1252")),
          repr(_octets.get(".g02", b"")[:48]))
_verifier("ras-commander : preparer() garde l'apport « Écluse » dans la "
          "carte", _arret == "" and _carte == ["Amont", "Écluse"], _carte)
_verifier("ras-commander : l'unsteady de la 2e etape, essai ecrit, garde "
          "« Écluse » en cp1252",
          _champ("Écluse", 32).encode("cp1252") in _octets.get(".u03", b"")
          and b"\xef\xbf\xbd" not in _octets.get(".u03", b"X\xef\xbf\xbd"))
_verifier("ras-commander : le plan de l'etape garde titre et description "
          "accentues, coeurs ecrits",
          all(l in _octets.get(".p03", b"").splitlines(keepends=True)
              for l in _cp1252("Plan Title=Apport_Écluse", "État aménagé",
                               "UNET D2 Cores= 2").splitlines(keepends=True))
          and b"\xef\xbf\xbd" not in _octets.get(".p03", b"X\xef\xbf\xbd"),
          repr(_octets.get(".p03", b"")[:60]))
_verifier("ras-commander : plan, geometrie et unsteady de reference "
          "intacts", all(_octets.get(s) == _origine[s]
                         for s in (".p01", ".g01", ".u01")))
# HEC-RAS PARTI SUR UN AUTRE PLAN, PUIS PLAN RETIRE DU .prj (10/11/2026).
# Le leurre ecrit le .tmp.hdf d'un AUTRE plan, comme l'a fait HEC-RAS
# 7.0.2. fermer_processus est remplace : aucun processus n'est ferme.
_fermes, _lances = [], []
_vraie_fermeture, _vraie_periode = fermer_processus, PERIODE_SURVEILLANCE_S

def _leurre_detour(*a, **k):
    (_bac / "ESSAI.p01.tmp.hdf").write_bytes(b"x")
    time.sleep(1.0)
    return True

try:
    pilote_hecras.fermer_processus = lambda pids: _fermes.append(pids) or []  # noqa: E731
    pilote_hecras.PERIODE_SURVEILLANCE_S = 0.2
    RasCmdr.compute_plan = staticmethod(_leurre_detour)
    _detour = _p.calculer()
    (_bac / "ESSAI.p01.tmp.hdf").unlink()
    RasCmdr.compute_plan = staticmethod(lambda *a, **k: _lances.append(a))
    (_bac / "ESSAI.prj").write_bytes((_bac / "ESSAI.prj").read_bytes()
                                     .replace(b"Plan File=p03\r\n", b""))
    _retire = _p.calculer()
finally:
    pilote_hecras.fermer_processus, pilote_hecras.PERIODE_SURVEILLANCE_S = (
        _vraie_fermeture, _vraie_periode)
    RasCmdr.compute_plan = _vrai_calcul
_verifier("un HEC-RAS parti sur un autre plan arrete le calcul et le nomme",
          not _detour.reussi and "p01" in _detour.message
          and len(_fermes) == 1, _detour.message[:150])
_verifier("un plan que le .prj ne declare plus n'est pas lance",
          not _retire.reussi and "Plan File=p03" in _retire.message
          and not _lances, _retire.message[:150])
# Ce que ras-commander n'a pas change garde AUSSI sa fin de ligne, LF
# comme CRLF ; une ligne qu'il a changee prend la sienne.
_f = _bac / "melange.p09"
_f.write_bytes(b"Plan Title=Apport_\xc3\x89cluse\r\n"
               b"DSS File=Donn\xef\xbf\xbdes\r\nLigne=neuve\r\n")
_retablir_octets(_f, b"Plan Title=Q100\r\nDSS File=Donn\xe9es\n")
_verifier("ras-commander : ligne inchangee a l'octet (LF garde), ligne "
          "changee en cp1252", _f.read_bytes()
          == b"Plan Title=Apport_\xc9cluse\r\nDSS File=Donn\xe9es\n"
          b"Ligne=neuve\r\n", repr(_f.read_bytes()))
shutil.rmtree(_bac, ignore_errors=True)

# -----------------------------------------------------------------------
# FERMETURE DES HEC-RAS ORPHELINS
#
# C'est la REGLE DE CHOIX qui est eprouvee, pas l'appel systeme : fermer
# le mauvais processus ferait perdre a l'utilisateur une session ouverte
# sur un autre projet. Le cas qui compte est celui du milieu — un
# processus deja la avant le calcul ne doit JAMAIS etre retenu, meme s'il
# est encore la apres.
# -----------------------------------------------------------------------
print("\n--- Fermeture des HEC-RAS orphelins ---")
_avant = {100: "Ras.exe", 101: "RasUnsteady.exe"}
_apres = {100: "Ras.exe", 102: "Ras.exe", 103: "RasUnsteady.exe"}
_orph = orphelins_du_calcul(_avant, _apres)
_verifier("seuls les processus APPARUS pendant le calcul sont retenus",
          set(_orph) == {102, 103}, str(sorted(_orph)))
_verifier("une session ouverte AVANT le calcul est epargnee",
          100 not in _orph)
_verifier("un processus disparu de lui-meme n'est pas poursuivi",
          101 not in _orph)
_verifier("aucun orphelin quand rien n'a bouge",
          not orphelins_du_calcul(_avant, dict(_avant)))
_verifier("un releve impossible ne ferme rien",
          not orphelins_du_calcul(None, _apres)
          and not orphelins_du_calcul(_avant, None))
_verifier("le releve des processus repond sans lever",
          pids_hecras() is None or isinstance(pids_hecras(), dict),
          str(pids_hecras()))
_verifier("fermer_processus ne leve pas sur un PID inexistant",
          fermer_processus({999999: "Fantome.exe"}) == [])

# -----------------------------------------------------------------------
# HEC-RAS PARTI SUR UN AUTRE PLAN : la regle de plan_detourne()
#
# Comme ci-dessus, c'est la REGLE qui est eprouvee. Le cas qui compte est
# le premier : le calcul qu'un collegue a lance avant le notre, sur un
# autre plan du meme projet, ne doit JAMAIS faire arreter le notre.
# -----------------------------------------------------------------------
print("\n--- HEC-RAS parti sur un autre plan ---")
_bac = Path(tempfile.mkdtemp(prefix="_essai_detour_"))
(_bac / "ESSAI.p05.tmp.hdf").write_bytes(b"x")
time.sleep(0.05)
_t0 = _heure_du_dossier(_bac)
time.sleep(0.05)
(_bac / "ESSAI.p05.tmp.hdf").write_bytes(b"xx")          # il ecrit toujours
_verifier("un calcul deja en cours au lancement n'arrete pas le notre",
          plan_detourne(_bac, "ESSAI", "03", _t0) is None)
# Un reste de calcul recree a l'ouverture du projet garde sa vieille date
# d'ecriture : HEC-RAS 7.0.2 et RAS Mapper le font (releve du 10/11/2026).
import os as _os
(_bac / "ESSAI.p07.tmp.hdf").write_bytes(b"x")
_os.utime(_bac / "ESSAI.p07.tmp.hdf", (_t0 - 3600, _t0 - 3600))
_verifier("un reste de calcul recree avec sa vieille date n'arrete pas le "
          "notre", plan_detourne(_bac, "ESSAI", "03", _t0) is None)
(_bac / "ESSAI.p02.tmp.hdf").write_bytes(b"x")
_verifier("un autre plan commence depuis le lancement, sans signe du "
          "notre : detournement",
          plan_detourne(_bac, "ESSAI", "03", _t0) == "02",
          str(plan_detourne(_bac, "ESSAI", "03", _t0)))
(_bac / "ESSAI.p03.tmp.hdf").write_bytes(b"x")
_verifier("notre plan donne signe de vie : plus de detournement",
          plan_detourne(_bac, "ESSAI", 3, _t0) is None)
_verifier("le jalon d'horloge ne reste pas dans le projet",
          not (_bac / "_jalon_calcul.tmp").exists())
_verifier("controleur COM a partir de HEC-RAS 7.0.2, « Ras.exe -c » avant",
          par_controleur("7.0.2") and par_controleur("7.1")
          and par_controleur("8.0") and not par_controleur("7.0.1")
          and not par_controleur("7.0") and not par_controleur("6.6")
          and not par_controleur(""))
_verifier("le symbole decimal de Windows se lit sans lever",
          symbole_decimal() is None or len(symbole_decimal()) == 1,
          repr(symbole_decimal()))
shutil.rmtree(_bac, ignore_errors=True)

# EN REPRISE, LA BORNE HAUTE RESTE CELLE DU PLAN DE REFERENCE. Le plan
# d'etape dont une reprise repart a pu etre raccourci par le calage
# precedent ; lire la borne SUR LUI la bornait a son tour, et l'apport
# repris ne pouvait plus rallonger jusqu'a son propre evenement. Mesure
# sur un cas reel (14/09/2026) : 36 h au plan de reference, 32 h 06 au
# plan d'etape. limiter_duree() ne fait que RACCOURCIR : une borne trop
# basse est donc un plafond, jamais un plancher.
_bac_f = Path(tempfile.mkdtemp(prefix="calage_borne_"))
try:
    (_bac_f / "Essai.p01").write_text(
        "Plan Title=reference\n"
        "Simulation Date=01JAN2000,00:00,02JAN2000,12:00\n",
        encoding="utf-8")                                     # 36 h
    (_bac_f / "Essai.p20").write_text(
        "Plan Title=etape\n"
        "Simulation Date=01JAN2000,00:00,02JAN2000,08:06\n",
        encoding="utf-8")                                     # 32 h 06

    # Le plan de travail est pose a la main — ce que preparer() aurait
    # clone — : rien a cloner ni a calculer, seule la borne est eprouvee.
    _ordinaire = PiloteHecRas(_bac_f, "Essai", "p20")
    _ordinaire.plan_travail = "20"
    _repris = PiloteHecRas(_bac_f, "Essai", "p20",
                           plan_fenetre_pleine="p01")
    _repris.plan_travail = "20"
    _verifier("calage ordinaire : la borne est celle du plan de travail",
              abs(_ordinaire._duree_borne_h() - 32.1) < 1e-9,
              f"{_ordinaire._duree_borne_h():.2f} h")
    _verifier("reprise : la borne reste les 36 h du plan de reference",
              abs(_repris._duree_borne_h() - 36.0) < 1e-9,
              f"{_repris._duree_borne_h():.2f} h au lieu de "
              f"{_ordinaire._duree_borne_h():.2f} h")
    _verifier("le pilote retient le plan de la borne, normalise",
              _repris.plan_fenetre_pleine == "01")
    _verifier("sans reprise, aucun plan de borne n'est retenu",
              _ordinaire.plan_fenetre_pleine is None)
    _ordinaire.plan_travail = "99"                    # fichier absent
    _verifier("un plan illisible ne borne rien, et ne leve pas",
              _ordinaire._duree_borne_h() is None)
finally:
    shutil.rmtree(_bac_f, ignore_errors=True)

# LA LIGNE QUI EXPLIQUE N'EST PAS LA DERNIERE. Compte rendu reel d'un
# calcul avorte (14/09/2026) : l'erreur est suivie du tableau des temps,
# plus de lignes que le filtre n'en garde. Coupe a son en-tete, le tableau
# ne pousse plus l'erreur dehors.
_compte_rendu = [
    "Plan: Q100_sans_apport",
    "Geometry Writer Failed",
    "Error Processing Geometry",
    "Computation Task\tTime(hh:mm:ss)",
    "Completing Geometry, Flow and Plan\t      25",
    "Unsteady Flow Computations\t<1",
    "Complete Process\t25",
    "Computation Speed\tSimulation/Runtime",
    "Unsteady Flow Computations\t617968x",
]
_retenues = _sans_tableau_des_temps(_compte_rendu)[-4:]
_verifier("les messages HEC-RAS gardent l'erreur, pas le tableau des temps",
          "Error Processing Geometry" in _retenues
          and "Geometry Writer Failed" in _retenues
          and not any("617968x" in l or "Complete Process" in l
                      for l in _retenues),
          " | ".join(_retenues))
# SANS TABLEAU, RIEN N'EST COUPE : un compte rendu interrompu avant lui se
# lit comme avant, par la fin.
_banal = ["ligne un", "ligne deux", "ligne trois", "ligne quatre",
          "ligne cinq"]
_verifier("sans tableau des temps, le compte rendu est rendu tel quel",
          _sans_tableau_des_temps(_banal) == _banal,
          str(_sans_tableau_des_temps(_banal)))

print()
if _echecs_test:
    print(f"{len(_echecs_test)} ECHEC(S)")
else:
    print("Tous les controles passent.")
print("=" * 74 + "\n")

raise SystemExit(1 if _echecs_test else 0)
