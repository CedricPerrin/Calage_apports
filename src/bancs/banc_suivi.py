"""Banc d'auto-test de src/suivi.py.

Ce banc etait le bloc `if __name__ == "__main__":` du module ; il en a ete
sorti le 10/11/2026 pour ne plus partir avec le code dans l'archive du plugin.
Il se lance seul (python3 src/bancs/banc_suivi.py) ou par le relais
que garde src/suivi.py (python3 src/suivi.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta
import json
import os
import numpy as np
from suivi import (COLONNES_PAR_ESSAI, ECHOUE, ETAT_COURANT, ETAT_PRECEDENT,
                   Suivi, VALIDE, _cellule, _sur_grille, nom_onglet)

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import tempfile

from criteres import diagnostiquer

sortie = Path(tempfile.gettempdir()) / "calage_suivi_test"
print("=" * 74)
print("AUTO-TEST DU SUIVI — simulation d'un calage a 4 apports")
print("=" * 74)
print(f"\nSorties : {sortie}\n")

def hydrogramme(t, pic, t_pic=6.0, forme=2.5):
    t = np.maximum(np.asarray(t, dtype=float), 1e-3)
    return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))

temps = np.linspace(0.01, 36, 400)
apports = ["Apport_1", "Apport_2", "Apport_3", "Apport_4"]
sections = ["S1_Amont", "S2_Pont", "S3_Confluence", "S4_Aval"]
pics = [45.0, 78.0, 112.0, 145.0]
# Le dernier apport ne converge pas : on veut voir le suivi en situation
# d'echec autant qu'en situation nominale.
#
# Les trois premieres valeurs tiennent dans la tolerance de VOLUME (0,5 %).
# Elles etaient plus laches quand le verdict reposait sur le KGE >= 0,95,
# qui admettait plusieurs pourcents d'ecart.
restitution = [1.002, 0.998, 0.997, 0.930]

suivi = Suivi(sortie, apports, sections,
              titre="Calage d'essai")
fichiers_vus = set()

for i, (pic, f) in enumerate(zip(pics, restitution)):
    suivi.commencer_apport(i)
    cible = hydrogramme(temps, pic)
    # ETAT DE DEPART, sur le premier apport seulement : c'est de cet
    # ecart-la que sort l'apport injecte a l'essai 1, et le classeur doit
    # le montrer. Les autres apports ne l'enregistrent pas — le classeur
    # doit rester valide dans les deux cas.
    if i == 0:
        suivi.enregistrer_residuel(
            i, (temps, cible), (temps, hydrogramme(temps - 0.4, 0.3 * pic)),
            0.4)
    for essai, facteur in enumerate([1.0, 1.4, 1.6], start=1):
        volume = min(0.62 * facteur, f)
        # Les series de CHAQUE essai : c'est ce que consigne le classeur
        # d'iterations, et le seul moyen de l'eprouver.
        suivi.enregistrer_essai(
            i, facteur, volume,
            pic=min(0.60 * facteur, f),
            series=(temps, cible, temps, hydrogramme(temps - 0.4,
                                                     pic * volume)),
            apport=(temps, hydrogramme(temps, 0.5 * pic * facteur)),
            # Le calcul est cale 0,4 h EN RETARD ci-dessus : le decalage
            # que la correction mesurerait vaut donc +0,4 h, et c'est de
            # celui-la que la cible doit etre decalee.
            decalage_correction=0.4)
    calcule = hydrogramme(temps - 0.4, pic * f)
    diag = diagnostiquer(temps, cible, temps, calcule)
    if diag.converge:
        suivi.valider_apport(i, diag, duree_s=1800 + 300 * i,
                             series=(temps, cible, temps, calcule))
    else:
        suivi.echouer_apport(i, "concordance non atteinte apres 3 essais",
                             diag, duree_s=2400)
    comptes, fraction = suivi.avancement()
    _, _, reste = suivi.temps()
    print(f"   apport {i + 1} : {suivi.etats[i].statut:10s} "
          f"volume {100 * diag.rapport_volume:5.1f} % pointe "
          f"{100 * diag.rapport_pic:5.1f} %  ->  "
          f"{100 * fraction:3.0f} % achevé, "
          f"reste estimé {timedelta(seconds=int(reste)) if reste else '—'}")
    fichiers_vus |= {p.name for p in sortie.glob("*")}

rapport = suivi.terminer()

print("\n--- FICHIERS PRODUITS ---")
for p in sorted(sortie.glob("*")):
    print(f"   {p.name:44s} {p.stat().st_size / 1024:7.1f} ko")

print("\n--- EXTRAIT DU RAPPORT ---")
print("\n".join(rapport.splitlines()[:14]))

# --- controles sur les valeurs ----------------------------------------
print("\n--- CONTROLES ---")
echecs = []

def controler(libelle, condition, detail=""):
    print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
          + (f"  ->  {detail}" if detail else ""))
    if not condition:
        echecs.append(libelle)

tableau = suivi.tableau()
comptes, fraction = suivi.avancement()
controler("3 valides et 1 echec", comptes[VALIDE] == 3 and comptes[ECHOUE] == 1,
          f"{comptes}")
controler("avancement a 100 %", abs(fraction - 1.0) < 1e-9,
          f"{100 * fraction:.0f} %")
controler("tableau complet", len(tableau) == 4 and tableau["Essais"].min() == 3,
          f"{len(tableau)} lignes")
controler("motif d'echec consigne",
          bool(tableau.loc[3, "Motif"]), tableau.loc[3, "Motif"])
controler("aucun incident de production", not suivi.incidents,
          " | ".join(suivi.incidents))

attendus = ["avancement.md", "avancement.png", "avancement.xlsx",
            "avancement.json", "iterations.xlsx"]
presents = [f for f in attendus if (sortie / f).exists()]
controler("livrables de suivi presents", len(presents) == len(attendus),
          str(presents))

# -----------------------------------------------------------------------
# CLASSEUR D'ITERATIONS. C'est la trace de la RECHERCHE, la ou le reste ne
# rapporte que son resultat. On verifie qu'il y a bien un onglet par
# apport, ses deux graphes, et surtout que la colonne d'ecart dit ce
# qu'elle annonce : CIBLE MOINS DEBIT REPHASE, sur la meme base de temps.
# C'est la grandeur que la methode corrige (calage.ecart_a_la_cible) ; la
# difference brute, qu'on ecrivait avant, en differe d'un facteur dix des
# que le troncon dephase.
# -----------------------------------------------------------------------
import openpyxl

_cl = openpyxl.load_workbook(sortie / "iterations.xlsx")
controler("un onglet par apport, dans l'ordre",
          _cl.sheetnames == [nom_onglet(a) for a in apports],
          str(_cl.sheetnames))
# L'apport 2 n'a PAS d'etat de depart enregistre : son onglet commence
# donc a l'essai 1, et c'est la forme de reference.
_f = _cl[nom_onglet(apports[1])]
controler("deux graphes par onglet : debits et apports injectes",
          len(_f._charts) == 2, f"{len(_f._charts)} graphe(s)")
_entete = next(r for r in range(1, 40)
               if _f.cell(row=r, column=1).value == "Temps (h)")
_titres = [_f.cell(row=_entete, column=j).value
           for j in range(1, 3 + COLONNES_PAR_ESSAI * 3)]
controler("quatre colonnes par essai, plus temps et cible",
          _titres[:2] == ["Temps (h)", "Cible (m³/s)"]
          and _titres[2].endswith("section")
          and "cible décalée" in _titres[3]
          and _titres[4].endswith("(cible décalée − section)")
          and _titres[5].endswith("apport injecté"), str(_titres[:6]))
# Le decalage applique est ANNONCE dans l'en-tete de la colonne de cible
# decalee et dans le recapitulatif : c'est ce qui rend le classeur
# refaisable a la main. Le calcul est en retard de 0,4 h dans ce cas
# d'essai, la cible est donc decalee de -0,40 h.
controler("l'en-tete annonce le décalage appliqué à la cible",
          "-0.40 h" in _titres[3], _titres[3])
controler("le récapitulatif porte la colonne « Décalage appliqué (h) »",
          _f.cell(row=4, column=6).value == "Décalage appliqué (h)"
          and abs(_f.cell(row=5, column=6).value - 0.4) < 1e-9,
          f"{_f.cell(row=4, column=6).value} = "
          f"{_f.cell(row=5, column=6).value}")
# (section, cible decalee, ecart) — les trois colonnes d'un bloc d'essai.
_lignes_pleines = [
    (_f.cell(row=r, column=3).value, _f.cell(row=r, column=4).value,
     _f.cell(row=r, column=5).value)
    for r in range(_entete + 1, _entete + 1 + len(temps))]
_verifiables = [(s, d, e) for s, d, e in _lignes_pleines
                if None not in (s, d, e)]
controler("l'écart consigné vaut bien cible décalée moins section",
          _verifiables
          and max(abs(e - (d - s)) for s, d, e in _verifiables) < 1e-3,
          f"{len(_verifiables)} ligne(s) comparables")
# ET LA CIBLE EST DECALEE DU BON Δt, DANS LE BON SENS. C'est le controle
# qui compte : sans lui, on verifierait seulement qu'une soustraction est
# juste, pas qu'elle porte sur les bonnes series.
#
# Le cas d'essai est fait pour trancher : le calcul du premier essai est
# EXACTEMENT la cible retardee de 0,4 h et multipliee par 0,62. La cible
# decalee de -0,4 h vaut donc la cible retardee, et le rapport
# section / cible decalee doit valoir 0,62 A CHAQUE PAS — un rapport
# constant, qu'aucun decalage absent ou de mauvais signe ne peut produire.
# Le rapport n'est examine que la ou la crue existe : sous quelques
# pour-cent du pic, la serie est ecretee a zero par le clamp de
# hydrogramme(), l'identite « retard pur » n'y tient plus, et diviser par
# un debit quasi nul ferait exploser un rapport qui ne mesure rien.
_seuil = 0.05 * max(d for _, d, _ in _verifiables)
_rapports = [s / d for s, d, _ in _verifiables if d > _seuil]
controler("le décalage de la cible annule le déphasage : reste un pur "
          "défaut d'amplitude",
          _rapports and max(abs(x - 0.62) for x in _rapports) < 0.01,
          f"section/cible décalée ∈ [{min(_rapports):.4f} ; "
          f"{max(_rapports):.4f}], attendu 0,62")
# Sans decalage, la colonne porterait la difference brute cible − section :
# sur ce cas elle est plus etalee que l'ecart d'amplitude reel.
_brut = [(_f.cell(row=r, column=2).value, s)
         for (s, _, _), r in zip(_lignes_pleines,
                                 range(_entete + 1,
                                       _entete + 1 + len(temps)))]
_ec_brut = max(abs(c - s) for c, s in _brut if None not in (c, s))
_ec_decale = max(abs(e) for _, _, e in _verifiables)
controler("l'écart sur cible décalée est plus petit que la différence "
          "brute",
          _ec_decale < _ec_brut,
          f"brut {_ec_brut:.2f} -> décalé {_ec_decale:.2f} m³/s")
# -----------------------------------------------------------------------
# LE BLOC RESIDUEL — l'etat de depart, apport a zero.
#
# Sans lui, l'onglet commencait a l'essai 1 et la premiere injection ne se
# rattachait a rien : on comparait l'ecart RESTANT apres l'essai 1 a
# l'apport qui l'avait PRECEDE, deux colonnes decalees d'un rang. C'est ce
# decalage-la qui donnait a croire que « l'apport injecte n'est pas
# l'ecart a la cible ». Il l'est — mais l'ecart du bloc PRECEDENT.
# -----------------------------------------------------------------------
_f0 = _cl[nom_onglet(apports[0])]
_e0 = next(r for r in range(1, 40)
           if _f0.cell(row=r, column=1).value == "Temps (h)")
_t0 = [_f0.cell(row=_e0, column=j).value
       for j in range(1, 3 + COLONNES_PAR_ESSAI * 4)]
controler("le bloc résiduel ouvre l'onglet, avant l'essai 1",
          _t0[2].startswith("Résiduel (apports à zéro)")
          and _t0[5].endswith("(aucun)")
          and _t0[6].startswith("Essai 1"), str(_t0[2:7]))
controler("le résiduel porte les mêmes quatre colonnes qu'un essai",
          _t0[3].startswith("Résiduel") and "cible décalée" in _t0[3]
          and _t0[4].endswith("(cible décalée − section)"), str(_t0[3:5]))
# LA CHAINE SE REFAIT A LA MAIN : ecart du bloc 0 -> apport de l'essai 1.
# Dans ce cas d'essai, le residuel vaut 0,3 fois la cible retardee de
# 0,4 h ; la cible decalee valant cette meme cible retardee, l'ecart vaut
# donc 0,7 fois elle, partout.
_paires = [(_f0.cell(row=r, column=5).value,
            _f0.cell(row=r, column=4).value)
           for r in range(_e0 + 1, _e0 + 1 + len(temps))]
_paires = [(e, d) for e, d in _paires if None not in (e, d) and d > 1.0]
controler("l'écart du bloc résiduel est bien cible décalée − résiduel",
          _paires and max(abs(e / d - 0.7) for e, d in _paires) < 0.01,
          f"écart/cible décalée ∈ [{min(e / d for e, d in _paires):.4f} ; "
          f"{max(e / d for e, d in _paires):.4f}], attendu 0,70")
controler("la règle de lecture en escalier est écrite en clair",
          "escalier" in (_f0["A3"].value or "")
          and "cible décalée" in (_f0["A3"].value or ""),
          (_f0["A3"].value or "")[:110])
controler("la note ne décale pas le tableau : l'en-tête reste en ligne 4",
          _f0.cell(row=4, column=1).value == "Essai",
          str(_f0.cell(row=4, column=1).value))
controler("un onglet sans bloc résiduel reste valide",
          _f.cell(row=_entete, column=3).value.startswith("Essai 1"),
          _f.cell(row=_entete, column=3).value)
# Un onglet SANS mesure de φ ne doit rien inventer.
controler("sans mesure de φ, rien n'est écrit à son sujet",
          "φ" not in (_f["A3"].value or ""), (_f["A3"].value or "")[:80])

# HORS DE LA FENETRE CALCULEE, RIEN N'EST INVENTE. Sous HEC-RAS, la serie
# calculee a sa propre base de temps, qui ne couvre pas toujours celle de
# la cible. Une valeur prolongee s'y lirait comme une mesure et fausserait
# la colonne d'ecart aux extremites — la ou l'on regarde justement si le
# calcul couvre bien la cible.
_hors = _sur_grille([0.0, 1.0, 2.0, 3.0], [1.0, 2.0], [10.0, 20.0])
controler("hors de la fenetre calculee, la valeur reste indefinie",
          np.isnan(_hors[0]) and np.isnan(_hors[3])
          and abs(_hors[1] - 10.0) < 1e-9, str(_hors))
controler("et une valeur indefinie donne une cellule VIDE",
          _cellule(float("nan")) is None and _cellule(2.5) == 2.5)
controler("un nom d'onglet impossible est assaini",
          nom_onglet("Perimeter 1: BCLine/3") == "Perimeter 1- BCLine-3",
          nom_onglet("Perimeter 1: BCLine/3"))
controler("un nom d'onglet trop long est tronque a 31 signes",
          len(nom_onglet("A" * 60)) == 31)

# -----------------------------------------------------------------------
# L'ETAT MACHINE — c'est lui que le plugin relit toutes les deux secondes.
# Ce qui compte : qu'il dise TOUJOURS si le calage tourne encore, et
# qu'il porte le verdict une fois fini. Sans cela, l'affichage ne peut pas
# distinguer « en cours » de « mort en chemin », et c'est precisement le
# reproche fait au suivi : le calcul s'arretait sans donner de nouvelles.
# -----------------------------------------------------------------------
# -----------------------------------------------------------------------
# LE VOLUME RAPPORTE EST « rapport_volume ».
#
# Ce champ recevait beta, le terme de biais du KGE, calcule sur la grille
# qui ENGLOBE les deux series. Les deux coincident quand les series
# partagent leur base de temps — ce que fait le cas ci-dessus, et c'est
# precisement pour cela qu'il n'a jamais vu le defaut. Sur un cas reel
# dont la simulation debordait largement la cible, le suivi affichait
# 261 % la ou le calage lisait 104 %, donnant a croire a une divergence
# sur un apport parfaitement en route. beta n'existe plus depuis le
# 07/09/2026 ; ce qui reste a prouver, c'est que le suivi rapporte bien
# rapport_volume sur une serie calculee DEUX FOIS plus longue que la
# cible — le cas ou les deux grandeurs divergeaient.
# -----------------------------------------------------------------------
_t_cible = np.linspace(0, 24, 200)
_q_cible = hydrogramme(_t_cible, 100.0)
_t_long = np.linspace(0, 48, 400)
_q_long = hydrogramme(_t_long, 100.0)
_diag_fenetres = diagnostiquer(_t_cible, _q_cible, _t_long, _q_long)

_suivi_f = Suivi(sortie / "fenetres", ["A"], ["S"])
_suivi_f.valider_apport(0, _diag_fenetres, duree_s=60)
_ligne = _suivi_f.tableau().iloc[0]
controler("le suivi rapporte le VOLUME sur une serie plus longue que la cible",
          abs(_ligne["Volume (% cible)"]
              - round(100 * _diag_fenetres.rapport_volume, 1)) < 1e-9,
          f"tableau={_ligne['Volume (% cible)']} % "
          f"volume={100 * _diag_fenetres.rapport_volume:.1f} %")
_etat_f = _suivi_f.etat()["apports"][0]
controler("l'etat machine rapporte lui aussi le VOLUME",
          abs(_etat_f["volume_pct"]
              - round(100 * _diag_fenetres.rapport_volume, 1)) < 1e-9,
          f"{_etat_f['volume_pct']} %")

etat = json.loads((sortie / "avancement.json").read_text(encoding="utf-8"))
controler("l'etat machine porte les cles attendues",
          {"fraction", "termine", "conforme", "apports", "en_cours",
           "ecoule_s", "reste_s", "pid", "total"} <= set(etat),
          f"{len(etat)} cles")
controler("un apport y porte son avancement chiffre",
          all({"apport", "statut", "essais", "volume_pct", "pic_pct"}
              <= set(a) for a in etat["apports"]),
          f"{len(etat['apports'])} apport(s)")

# RELANCER N'EFFACE PLUS LE SUIVI PRECEDENT (13/09/2026). C'est ce qui
# permet a l'onglet Suivi de garder a l'ecran les apports deja cales
# qu'une reprise ne refait pas.
_rep = sortie / "relance"
_s1 = Suivi(_rep, ["A", "B"], ["SA", "SB"])
_s1.valider_apport(0, _diag_fenetres, duree_s=60)
_avant = json.loads((_rep / ETAT_COURANT).read_text(encoding="utf-8"))
_s2 = Suivi(_rep, ["B"], ["SB"])
controler("relancer archive le suivi precedent au lieu de l'ecraser",
          json.loads((_rep / ETAT_PRECEDENT)
                     .read_text(encoding="utf-8")) == _avant)
controler("et le calage relance repart sur son propre etat",
          [a["apport"] for a in _s2.etat()["apports"]] == ["B"],
          str([a["apport"] for a in _s2.etat()["apports"]]))

# BILAN DE MASSE — QUALITE DU CALCUL, PAS ECART A LA CIBLE. Publie parce
# qu'un calage arrete pour « qualite numerique » n'exposait son chiffre
# que dans le journal texte, que l'utilisateur du plugin n'ouvre pas.
_suivi_bilan = Suivi(sortie / "bilan", ["A"], ["S"])
controler("aucun bilan tant qu'aucun calcul n'a tourne",
          _suivi_bilan.etat()["bilan_masse"] is None)
_suivi_bilan.noter_bilan_masse(1.119, 5.0)
_b = json.loads((sortie / "bilan" / "avancement.json")
                .read_text(encoding="utf-8"))["bilan_masse"]
controler("le bilan et son seuil sont publies dans l'etat machine",
          _b == {"pct": 1.119, "seuil_pct": 5.0}, str(_b))
# UN BILAN NON MESURABLE N'EFFACE PAS LE PRECEDENT : on garderait sinon
# l'ecran vide sans savoir si c'est la mesure ou le calcul qui manque.
_suivi_bilan.noter_bilan_masse(float("nan"), 5.0)
controler("un bilan non mesurable laisse le dernier connu en place",
          _suivi_bilan.etat()["bilan_masse"]["pct"] == 1.119,
          str(_suivi_bilan.etat()["bilan_masse"]))
_suivi_bilan.noter_bilan_masse(None, 5.0)
controler("un bilan absent ne leve pas d'exception",
          _suivi_bilan.etat()["bilan_masse"]["pct"] == 1.119)

# LES TROIS GRANDEURS DES L'ESSAI, pas seulement a la validation. Sinon la
# jauge « Forme » du plugin reste vide pendant toute la recherche, c'est-a
# -dire pendant les heures ou l'on regarde l'ecran.
_suivi_essai = Suivi(sortie / "en_cours", ["A"], ["S"])
_suivi_essai.commencer_apport(0)
_suivi_essai.enregistrer_essai(0, 1.2, 1.034, 0.937, 0.998, -1.9)
_a = _suivi_essai.etat()["apports"][0]
controler("un essai EN COURS rapporte volume, pointe, forme et decalage",
          (_a["volume_pct"], _a["pic_pct"], _a["forme_pct"],
           _a["decalage_h"]) == (103.4, 93.7, 99.8, -1.9),
          f"volume={_a['volume_pct']} pointe={_a['pic_pct']} "
          f"forme={_a['forme_pct']} decalage={_a['decalage_h']}")
controler("tant qu'aucun verdict n'est rendu, le calage est dit EN COURS",
          etat["termine"] is False and etat["conforme"] is None)

# -----------------------------------------------------------------------
# LES COURBES PUBLIEES A L'ECRAN PORTENT LA CIBLE DECALEE, comme le
# classeur. Publiee brute, elle apparaissait translatee de Δt sous des
# jauges annoncant 100 % — 3,8 h sur un calage reel — et l'oeil concluait a
# un calage faux la ou il etait juste.
#
# Le cas est fait pour trancher : le calcul est la cible RETARDEE de 0,4 h,
# donc Δt = +0,4 h. La cible publiee doit voir sa base de temps translatee
# de +0,4 h, et son pic tomber sur celui de la section — pas 0,4 h avant.
# -----------------------------------------------------------------------
_suivi_c = Suivi(sortie / "courbes", ["A"], ["S"])
_suivi_c.commencer_apport(0)
_suivi_c.enregistrer_essai(
    0, 1.0, 0.62, series=(temps, hydrogramme(temps, 100.0),
                                temps, hydrogramme(temps - 0.4, 62.0)),
    decalage_correction=0.4)
_c = _suivi_c.etat()["courbes"]
controler("les courbes publiees nomment le decalage employe",
          _c is not None and _c.get("decalage_h") == 0.4,
          str(None if _c is None else _c.get("decalage_h")))
controler("les courbes publiees nomment l'apport dont elles viennent",
          _c.get("apport") == "A" and _c.get("section") == "S",
          f"{_c.get('apport')} -> {_c.get('section')}")
_pic_cible = _c["temps_cible"][int(np.argmax(_c["debit_cible"]))]
_pic_section = _c["temps_calcule"][int(np.argmax(_c["debit_calcule"]))]
# Les deux series sont sous-echantillonnees independamment : leurs pics
# respectifs sont conserves, mais tombent sur des instants qui peuvent
# differer d'un pas. C'est donc au pas d'echantillonnage qu'on juge, pas a
# une constante — et l'ecart residuel doit rester tres inferieur au Δt de
# 0,4 h qu'on vient d'annuler.
_pas = min(b - a for a, b in zip(_c["temps_cible"], _c["temps_cible"][1:]))
controler("la cible publiee est decalee : son pic tombe sur celui de la "
          "section",
          abs(_pic_cible - _pic_section) <= _pas + 1e-9
          and abs(_pic_cible - _pic_section) < 0.4 / 4,
          f"pic cible {_pic_cible:.2f} h, pic section {_pic_section:.2f} h, "
          f"pas {_pas:.3f} h (Δt annule = 0,40 h)")

# -----------------------------------------------------------------------
# LES SECTIONS DEJA CALEES SONT PUBLIEES A PART, pour se tracer derriere la
# paire courante. Ce qui compte ici : n'y mettre QUE des apports valides —
# un apport en echec ou en recherche n'a pas d'hydrogramme retenu, et le
# montrer laisserait croire a un resultat.
# -----------------------------------------------------------------------
_suivi_p = Suivi(sortie / "precedentes", ["A1", "A2", "A3"],
                 ["S1", "S2", "S3"])
_series = (temps, hydrogramme(temps, 100.0),
           temps, hydrogramme(temps, 96.0))
controler("aucune section calee tant que rien n'est valide",
          _suivi_p.etat()["courbes_precedentes"] == [],
          str(_suivi_p.etat()["courbes_precedentes"]))

_suivi_p.commencer_apport(0)
_suivi_p.enregistrer_essai(0, 1.0, 0.96, series=_series)
_suivi_p.valider_apport(0, diagnostiquer(temps, hydrogramme(temps, 100.0),
                                         temps, hydrogramme(temps, 96.0)))
_suivi_p.commencer_apport(1)
_suivi_p.enregistrer_essai(1, 1.0, 0.99, series=_series)
_p = _suivi_p.etat()["courbes_precedentes"]
controler("l'apport valide precedent est publie, nomme par sa section",
          len(_p) == 1 and _p[0]["section"] == "S1"
          and _p[0]["apport"] == "A1", str([c["section"] for c in _p]))
controler("il porte une serie tracable",
          len(_p[0]["temps"]) > 1
          and len(_p[0]["temps"]) == len(_p[0]["debit"]),
          f"{len(_p[0]['temps'])} point(s)")
controler("elle est allegee plus fort que la courbe courante",
          len(_p[0]["temps"]) <= 91,
          f"{len(_p[0]['temps'])} point(s) pour 90 demandes")
controler("l'apport EN COURS n'est pas dans les precedentes",
          all(c["section"] != "S2" for c in _p),
          str([c["section"] for c in _p]))

# UN APPORT EN ECHEC N'EST PAS UN RESULTAT. Il a des series — il a bien
# calcule — mais aucun hydrogramme retenu.
_suivi_e = Suivi(sortie / "echoue", ["A1", "A2"], ["S1", "S2"])
_suivi_e.commencer_apport(0)
_suivi_e.enregistrer_essai(0, 1.0, 0.5, series=_series)
_suivi_e.echouer_apport(0, "cible hors d'atteinte")
_suivi_e.commencer_apport(1)
_suivi_e.enregistrer_essai(1, 1.0, 0.99, series=_series)
controler("un apport en ECHEC ne figure pas parmi les sections calees",
          _suivi_e.etat()["courbes_precedentes"] == [],
          str(_suivi_e.etat()["courbes_precedentes"]))
controler("seule la base de temps est decalee, jamais les debits",
          abs(max(_c["debit_cible"]) - 100.0) < 0.5,
          f"pic publie {max(_c['debit_cible']):.2f} m³/s, attendu 100")

# ET SURTOUT : QUAND L'APPORT EN COURS N'A RIEN PRODUIT, ON MONTRE LE
# PRECEDENT. Un apport n'a de series qu'apres l'evaluation de son premier
# essai, soit ~3 h de calcul HEC-RAS : sans repli, le panneau restait vide
# pendant exactement les heures ou on le regarde, et sur un calage ou
# chaque apport converge du premier coup personne ne voyait de courbe.
_suivi_r = Suivi(sortie / "repli", ["A1", "A2"], ["S1", "S2"])
_suivi_r.commencer_apport(0)
_suivi_r.enregistrer_essai(
    0, 1.0, 1.0, series=(temps, hydrogramme(temps, 100.0),
                              temps, hydrogramme(temps, 99.0)))
_suivi_r.etats[0].statut = VALIDE
_suivi_r.commencer_apport(1)            # A2 calcule, rien a montrer encore
_cr = _suivi_r.etat()["courbes"]
controler("l'apport en cours sans essai montre le dernier apport chiffre",
          _cr is not None and _cr.get("apport") == "A1",
          "aucune courbe publiee" if _cr is None else _cr.get("apport"))
_suivi_v = Suivi(sortie / "vierge", ["A1"], ["S1"])
_suivi_v.commencer_apport(0)
controler("avant le tout premier essai, rien n'est invente",
          _suivi_v.etat()["courbes"] is None,
          str(_suivi_v.etat()["courbes"]))

suivi.conclure(False, "deux apports sur quatre non cales", 11)
etat = json.loads((sortie / "avancement.json").read_text(encoding="utf-8"))
controler("apres conclure(), le verdict est lisible",
          etat["termine"] is True and etat["conforme"] is False
          and "non cales" in etat["motif_final"]
          and etat["nb_calculs"] == 11,
          f"termine={etat['termine']} conforme={etat['conforme']}")
controler("l'etat machine est ecrit atomiquement",
          not list(sortie.glob("*.json.tmp")))
controler("le PID permet de reperer un calage mort",
          etat["pid"] == os.getpid(), str(etat["pid"]))
controler("figures de section produites",
          len(list(sortie.glob("comparaison_*.png"))) == 3,
          f"{len(list(sortie.glob('comparaison_*.png')))} figure(s)")
controler("aucun fichier temporaire residuel",
          not list(sortie.glob("*.tmp*")),
          str([p.name for p in sortie.glob('*.tmp*')]))

# Le suivi ne doit jamais interrompre le calage.
suivi_casse = Suivi(sortie / "protege", ["A"], ["S"])
suivi_casse.dossier = Path("Z:/inexistant/impossible")
try:
    suivi_casse.valider_apport(0, diag, duree_s=10)
    survit = True
except Exception:
    survit = False
controler("une defaillance d'ecriture n'interrompt pas le calage",
          survit and bool(suivi_casse.incidents),
          f"{len(suivi_casse.incidents)} incident(s) consigne(s)")

print()
if echecs:
    print(f"   {len(echecs)} CONTROLE(S) EN ECHEC : {echecs}")
    raise SystemExit(1)
print("   Tous les controles passent.")
print("=" * 74)
