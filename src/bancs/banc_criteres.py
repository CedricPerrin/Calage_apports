"""Banc d'auto-test de src/criteres.py.

Ce banc etait le bloc `if __name__ == "__main__":` du module ; il en a ete
sorti le 10/11/2026 pour ne plus partir avec le code dans l'archive du plugin.
Il se lance seul (python3 src/bancs/banc_criteres.py) ou par le relais
que garde src/criteres.py (python3 src/criteres.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from criteres import (Diagnostic, PAS_ENTREE_H, PAS_RECALAGE_H, diagnostiquer,
                      fenetre_commune, grille_commune, normaliser_entree,
                      recaler, reechantillonner, reserve_identifiabilite,
                      volume)

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import sys

# Jusqu'ici cet auto-test ne faisait qu'AFFICHER des nombres : il ne
# pouvait pas echouer, donc il ne prouvait rien. Or c'est le module qui
# porte le KGE, la strategie de recherche et les criteres d'arret — et
# c'est deja ici qu'un garde-fou (le decalage temporel) etait reste mort
# en silence. Chaque demonstration est desormais assortie d'un controle.
_echecs = []

def _verifier(libelle, condition, detail=""):
    print(f"      [{'OK' if condition else 'ECHEC'}] {libelle}"
          + (f"  ->  {detail}" if detail else ""))
    if not condition:
        _echecs.append(libelle)

def hydrogramme(t, pic, t_pic=6.0, forme=2.5):
    t = np.maximum(np.asarray(t, dtype=float), 1e-3)
    return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))

temps = np.linspace(0.01, 30, 400)
cible = hydrogramme(temps, pic=100.0)

print("--- 1. Identite (calcule = cible) ---")
d = diagnostiquer(temps, cible, temps, cible)
print(d.resume(), "-> converge :", d.converge)
_verifier("r = 1 quand le calcul EST la cible", abs(d.r - 1.0) < 1e-6,
          f"r={d.r:.6f}")
_verifier("le cas identite converge", d.converge)

print("\n--- 2. Decalage temporel PUR de +3 h (translation, forme inchangee) ---")
print("    la methode doit le neutraliser : r doit rester ~1")
decale = hydrogramme(temps - 3.0, pic=100.0)
decale[temps < 3.0] = hydrogramme(np.array([0.01]), 100.0)[0]
d = diagnostiquer(temps, cible, temps, decale)
print(d.resume(), "-> converge :", d.converge)
_verifier("un decalage PUR est neutralise par le recalage", d.r > 0.99,
          f"r={d.r:.4f}")
_verifier("le decalage est neanmoins RAPPORTE, pas efface",
          abs(d.decalage_h) > 2.0, f"{d.decalage_h:+.2f} h")

print("\n--- 2 bis. Fenetres de temps d'origines differentes ---")
print("    La serie extraite du modele demarre au debut de la simulation,")
print("    la cible au debut de l'evenement : les origines different.")
print("    Le decalage rapporte doit rester le decalage PHYSIQUE.")
for retard in (0.0, 3.0):
    _, _, mesure = recaler(temps, cible, temps + retard, cible)
    etat = "ok" if abs(mesure - retard) <= 1.5 * 0.25 else "INCORRECT"
    print(f"    fenetre calculee decalee de {retard:+.1f} h "
          f"-> decalage mesure {mesure:+.2f} h  [{etat}]")
    _verifier(f"decalage de fenetre {retard:+.1f} h correctement mesure",
              abs(mesure - retard) <= 1.5 * 0.25, f"{mesure:+.2f} h")
print("    (rechantillonner chaque serie depuis sa propre origine")
print("     annulerait ce decalage et neutraliserait le garde-fou)")

print("\n--- 2 ter. Fenetre de calcul plus longue ou tronquee ---")
print("    Les volumes se comparent sur la fenetre COMMUNE, jamais chacun")
print("    sur sa propre etendue.")
for libelle, t_calc in [
    ("simulation plus longue (48 h)", np.linspace(0.01, 48, 700)),
    ("simulation tronquee (20 h)", np.linspace(0.01, 20, 300)),
    ("fenetres disjointes (50-80 h)", np.linspace(50, 80, 300)),
]:
    depart = 50.0 if t_calc[0] > 40 else 0.0
    d = diagnostiquer(temps, cible, t_calc, hydrogramme(t_calc - depart, 100.0))
    print(f"    {libelle:32s} vol={d.rapport_volume:.3f}")
    for a in d.alertes:
        print(f"        ALERTE : {a}")
    if "disjointes" in libelle:
        _verifier("des fenetres disjointes levent une alerte",
                  bool(d.alertes))
    else:
        # Le defaut corrige a la 4e passe : integrer chaque serie sur SA
        # propre etendue gonflait le rapport de volume d'une simulation
        # plus longue, sans le moindre defaut de calage.
        _verifier(f"volume compare sur la fenetre commune — {libelle}",
                  abs(d.rapport_volume - 1.0) < 0.02,
                  f"vol={d.rapport_volume:.3f}")
    if "tronquee" in libelle:
        _verifier("une simulation trop courte est signalee",
                  bool(d.alertes))

print("\n--- 3. Apport sous-dimensionne (-25 %) ---")
d = diagnostiquer(temps, cible, temps, 0.75 * cible)
print(d.resume(), "-> converge :", d.converge)
_verifier("un apport a -25 % donne un volume ~ 0,75",
          abs(d.rapport_volume - 0.75) < 0.01,
          f"volume={d.rapport_volume:.4f}")
_verifier("un apport sous-dimensionne ne converge PAS", not d.converge)

print("\n--- 4. Le decalage est MESURE et RAPPORTE, jamais juge ---")
# Un seuil « decalage_max_h » levait ici une alerte. Retire le 08/08/2026
# sur decision utilisateur : il s'est declenche sur SEPT sections sur sept
# d'un calage reel, pour des decalages structurels de 3,60 a 5,30 h, et
# une alerte qui se declenche partout apprend a l'ignorer. L'amplitude ne
# distinguait pas un temps de transfert reel d'un appariement de pics sans
# rapport — les deux peuvent valoir 5 h. Voir Diagnostic.converge.
tres_decale = hydrogramme(temps - 6.0, pic=100.0)
tres_decale[temps < 6.0] = hydrogramme(np.array([0.01]), 100.0)[0]
d = diagnostiquer(temps, cible, temps, tres_decale)
print(d.resume())
_verifier("un decalage de 6 h est MESURE et rapporte",
          abs(d.decalage_h - 6.0) < 0.15, f"{d.decalage_h:+.2f} h")
_verifier("il figure dans le resume lu par l'utilisateur",
          "decalage" in d.resume(), d.resume())
_verifier("il ne leve AUCUNE alerte, quelle que soit son amplitude",
          not any("decalage" in a.lower() for a in d.alertes),
          str(d.alertes) or "aucune")
_verifier("il ne bloque donc rien non plus",
          not any("decalage" in a.lower() for a in d.alertes_bloquantes),
          str(d.alertes_bloquantes) or "aucune")
# Meme forme, meme amplitude, meme fenetre couverte — seul l'instant du
# pic differe de 6 h. Le recalage l'annule, les trois grandeurs sont donc
# parfaites, et le verdict doit suivre, SANS reserve d'aucune sorte.
_long = np.linspace(0.01, 72, 900)
_cible_l = hydrogramme(_long, pic=100.0, t_pic=12.0)
_decale = diagnostiquer(_long, _cible_l, _long,
                        hydrogramme(_long - 6.0, pic=100.0, t_pic=12.0))
_verifier("un calage juste mais decale est conforme, sans aucune alerte",
          _decale.converge and not _decale.alertes,
          f"converge={_decale.converge} vol={_decale.rapport_volume:.3f} "
          f"pic={_decale.rapport_pic:.3f} r={_decale.r:.3f} "
          f"alertes={_decale.alertes}")
_verifier("et son decalage reste lisible dans le resume",
          abs(_decale.decalage_h - 6.0) < 0.15,
          f"{_decale.decalage_h:+.2f} h")

print("\n--- 4 ter. Une couverture insuffisante, elle, BLOQUE ---")
_court = temps[temps <= 0.3 * temps[-1]]
d = diagnostiquer(temps, cible, _court, hydrogramme(_court, 100.0))
for a in d.alertes:
    print("   ALERTE :", a)
_verifier("une simulation trop courte est BLOQUANTE",
          bool(d.alertes_bloquantes) and not d.converge,
          str(d.alertes_bloquantes))

# ENTRE 90 ET 100 % DE COUVERTURE, PLUS RIEN NE SE TAIT.
#
# Ce controle manquait, et son absence laissait un angle mort AVEUGLE PAR
# CONSTRUCTION : les volumes etant integres sur le meme intervalle rogne
# pour la cible et pour le calcul, leur rapport reste a 100 % alors qu'une
# part de l'evenement juge n'a jamais ete simulee. Aucun autre indicateur
# ne pouvait le reveler — d'ou l'assertion sur rapport_volume ci-dessous,
# qui fige la raison meme d'exister de cette alerte.
_tc = np.linspace(0.0, 40.0, 401)
_qc = 50.0 * np.exp(-0.5 * ((_tc - 20.0) / 6.0) ** 2)
_n34 = int(34.0 / 0.1) + 1
_rogne = diagnostiquer(_tc, _qc, _tc[:_n34], _qc[:_n34],
                       fenetre=(2.0, 35.0))
_non_bloq = [a for a in _rogne.alertes
             if a not in _rogne.alertes_bloquantes]
_verifier("une fenetre jugee rognee de 3 % est DITE, sans bloquer",
          bool(_non_bloq) and not _rogne.alertes_bloquantes,
          f"{len(_non_bloq)} alerte(s) non bloquante(s), "
          f"{len(_rogne.alertes_bloquantes)} bloquante(s)")
_verifier("elle chiffre les heures manquantes",
          any("1.0 h" in a and "97 %" in a for a in _non_bloq),
          _non_bloq[0][:100] if _non_bloq else "aucune")
_verifier("et le rapport de volume, lui, ne pouvait RIEN en dire",
          abs(_rogne.rapport_volume - 1.0) < 1e-6,
          f"volume {100 * _rogne.rapport_volume:.1f} % malgre 1,0 h "
          f"non simulee")
# ET LE CAS SYMETRIQUE : une fenetre entierement couverte ne dit rien,
# sans quoi l'alerte se declencherait partout et on cesserait de la lire.
_entier = diagnostiquer(_tc, _qc, _tc, _qc, fenetre=(2.0, 35.0))
_verifier("une fenetre entierement couverte ne leve aucune alerte",
          not _entier.alertes, str(_entier.alertes))

print("\n--- 4bis. Le retard ne doit pas couter du volume ---")
#
# Un apport JUSTE mais retarde ne doit pas etre juge deficitaire. Deux
# defauts se combinaient pour cela, et ce controle les fige tous deux :
#   - la correlation croisee sous-estimait le retard (0,00 h pour 1,6 h
#     reel) des que l'evenement ne revient pas a sa ligne de base ;
#   - le volume etait compare sur la fenetre brute, ou un retard ampute
#     la serie en retard de tout ce qui manque a la fermeture.
# Resultat : le critere reclamait 3,7 % de volume que la correction, elle,
# ne voyait pas manquer. La boucle stagnait sans levier.
t_ev = np.linspace(0, 26, 261)
crue = 460.0 * np.exp(-0.5 * ((t_ev - 16.0) / 7.0) ** 2)
_verifier("la fenetre coupe bien la decrue (cas eprouvant)",
          crue[-1] / crue.max() > 0.3,
          f"{100 * crue[-1] / crue.max():.0f} % du pic a la fermeture")
for _retard in (0.8, 1.6, 3.0):
    _tardif = 460.0 * np.exp(-0.5 * ((t_ev - _retard - 16.0) / 7.0) ** 2)
    _d = diagnostiquer(t_ev, crue, t_ev, _tardif)
    _verifier(f"retard de {_retard} h : le decalage est vu",
              abs(_d.decalage_h - _retard) <= PAS_RECALAGE_H,
              f"detecte {_d.decalage_h:+.2f} h")
    _verifier(f"retard de {_retard} h : le volume reste juste",
              abs(_d.rapport_volume - 1.0) <= 0.005,
              f"{100 * _d.rapport_volume:.2f} % de la cible")

print("\n--- 5. Volume et fenetre commune ---")
# La strategie de recherche a quitte ce module : la correction de
# l'apport est desormais ADDITIVE et vit dans calage.py, avec ses propres
# criteres d'arret. criteres.py ne garde que l'ANALYSE — recalage,
# volumes, forme, diagnostic — ce qui etait sa vocation.
t_a = np.linspace(0, 24, 200)
t_b = np.linspace(6, 36, 200)
# Les deux bornes ne servent pas a la meme chose et ne doivent pas etre
# confondues : grille_commune ENGLOBE les deux series, pour le recalage
# temporel ; fenetre_commune les INTERSECTE, seule etendue ou des volumes
# soient comparables.
_verifier("grille_commune englobe les deux series",
          grille_commune(t_a, t_b) == (0.0, 36.0),
          str(grille_commune(t_a, t_b)))
_verifier("fenetre_commune intersecte les deux series",
          fenetre_commune(t_a, t_b) == (6.0, 24.0),
          str(fenetre_commune(t_a, t_b)))
plat = np.ones_like(t_a) * 10.0
_verifier("le volume d'un debit constant vaut debit x duree",
          abs(volume(t_a, plat, 0.0, 24.0) - 240.0) < 1e-6,
          f"{volume(t_a, plat, 0.0, 24.0):.3f}")
_verifier("des series disjointes n'ont pas de fenetre commune",
          not np.isfinite(fenetre_commune(t_a, np.linspace(50, 80, 50))[0]))

print("\n--- 6. Normalisation des hydrogrammes d'entree (pas <= 6 min) ---")
# Une cible HSMF collee a la main arrive typiquement au pas horaire : trop
# grossier pour le recalage temporel et pour la forme injectee dans le
# modele, qui en heritent tous deux telle quelle. Une serie DEJA a 6 min
# ou plus fine, elle, est conservee a son pas natif, sans degradation.
t_grossier = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
q_grossier = np.array([0.0, 50.0, 100.0, 40.0, 0.0])
t_fin, q_fin, pas_initial = normaliser_entree(t_grossier, q_grossier)
_verifier("un pas horaire est ramene a 6 minutes",
          abs(np.max(np.diff(t_fin)) - PAS_ENTREE_H) < 1e-9,
          f"pas max {3600 * np.max(np.diff(t_fin)):.0f} s")
_verifier("le pas d'origine est rapporte, pour le journal",
          abs(pas_initial - 1.0) < 1e-9, f"{pas_initial} h")
_verifier("les bornes de temps sont conservees",
          t_fin[0] == t_grossier[0] and abs(t_fin[-1] - t_grossier[-1]) < 1e-9,
          f"{t_fin[0]:.3f} -> {t_fin[-1]:.3f} h")
_verifier("le pic reste 100 (interpolation lineaire, pas de lissage)",
          abs(np.max(q_fin) - 100.0) < 1e-6, f"{np.max(q_fin):.3f}")
t_source_menue, q_source_menue = reechantillonner(t_grossier, q_grossier, 0.05)
t_menu, q_menu, pas_menu = normaliser_entree(t_source_menue, q_source_menue)
_verifier("un hydrogramme plus fin que 6 min est conserve a son pas natif",
          pas_menu is None
          and len(t_menu) == len(t_source_menue)
          and abs(np.max(np.diff(t_menu)) - 0.05) < 1e-9,
          f"{len(t_menu)} pas, pas max "
          f"{3600 * np.max(np.diff(t_menu)):.0f} s, pas_initial={pas_menu}")
t_deja, q_deja, pas_deja = normaliser_entree(
    *reechantillonner(t_grossier, q_grossier, PAS_ENTREE_H))
_verifier("une serie deja au pas de 6 min ressort intacte, sans conversion",
          pas_deja is None and len(t_deja) == len(q_deja) == 41,
          f"pas_initial={pas_deja}, {len(t_deja)} valeurs")
_verifier("une serie de moins de deux points ne fait rien echouer",
          normaliser_entree([0.0], [1.0])[2] is None)

print("\n--- 7. Fenetre du hydrogramme PRINCIPAL (parametre `fenetre`) ---")
# Demande : une mini-crue ISOLEE, avant l'evenement cale, ne doit pas
# peser sur le volume, la pointe ou l'alerte de couverture — seule
# l'evenement effectivement calé (le second pic) doit etre juge.
_tf = np.linspace(0.0, 48.0, 481)
_cible7 = (hydrogramme(_tf, pic=20.0, t_pic=4.0, forme=3.0)
          + hydrogramme(_tf - 24.0, pic=100.0, t_pic=6.0, forme=3.0))
# Le calcul REPRODUIT le pic principal a la perfection, mais s'ecarte
# fortement sur la mini-crue anterieure (deux fois trop de debit) — une
# excursion de debit de base marque, sans rapport avec l'apport cale.
_calc7 = (hydrogramme(_tf, pic=40.0, t_pic=4.0, forme=3.0)
         + hydrogramme(_tf - 24.0, pic=100.0, t_pic=6.0, forme=3.0))
_fen7 = (18.0, 40.0)   # encadre largement le seul evenement principal
_sans_fen = diagnostiquer(_tf, _cible7, _tf, _calc7, tolerance_volume=0.05)
_avec_fen = diagnostiquer(_tf, _cible7, _tf, _calc7, tolerance_volume=0.05,
                          fenetre=_fen7)
_verifier("sans fenetre, la mini-crue anterieure casse le volume",
          abs(_sans_fen.rapport_volume - 1.0) > 0.05,
          f"{100 * _sans_fen.rapport_volume:.1f} %")
_verifier("avec la fenetre du hydrogramme principal, le volume est juste",
          abs(_avec_fen.rapport_volume - 1.0) < 0.01,
          f"{100 * _avec_fen.rapport_volume:.1f} %")
_verifier("avec la fenetre, la pointe ignore aussi la mini-crue",
          abs(_avec_fen.rapport_pic - 1.0) < 0.01,
          f"{100 * _avec_fen.rapport_pic:.1f} %")
_verifier("sans fenetre, la mini-crue anterieure degrade aussi la forme",
          _sans_fen.r < 0.999, f"r={_sans_fen.r:.4f}")
_verifier("avec la fenetre, la forme ignore aussi la mini-crue (r ~ 1)",
          abs(_avec_fen.r - 1.0) < 1e-3, f"r={_avec_fen.r:.6f}")
_verifier("avec la fenetre, la couverture se juge sur sa duree, pas sur "
          "celle de toute la serie d'entree",
          not any("couvre que" in a for a in _avec_fen.alertes),
          str(_avec_fen.alertes))
_verifier("la fenetre jugee est rapportee dans le resume",
          f"{_fen7[0]:.2f}-{_fen7[1]:.2f} h" in _avec_fen.resume(),
          _avec_fen.resume())
_verifier("sans fenetre fournie, le resume ne mentionne aucune fenetre",
          "fenetre" not in _sans_fen.resume(), _sans_fen.resume())

print("\n--- 7 bis. La fenetre borne aussi la MESURE DU DECALAGE ---")
# Le § 7 place la mini-crue SOUS l'evenement : le pic le plus haut de la
# serie reste le bon, et le decalage tombe juste par chance. On place ici
# un transitoire de demarrage PLUS HAUT que l'evenement, hors fenetre —
# ce qu'un modele 2D produit a la mise en eau. Le pic global change alors
# de cote, et avec lui l'appariement des deux series.
_t7b = np.linspace(0.0, 48.0, 481)
_evt_c = hydrogramme(_t7b - 24.0, pic=100.0, t_pic=6.0, forme=3.0)
_evt_s = hydrogramme(_t7b - 25.5, pic=100.0, t_pic=6.0, forme=3.0)
_cible7b = _evt_c + hydrogramme(_t7b, pic=20.0, t_pic=4.0, forme=3.0)
_calc7b = _evt_s + hydrogramme(_t7b, pic=160.0, t_pic=4.0, forme=3.0)
_fen7b = (18.0, 40.0)
_sans7b = diagnostiquer(_t7b, _cible7b, _t7b, _calc7b)
_avec7b = diagnostiquer(_t7b, _cible7b, _t7b, _calc7b, fenetre=_fen7b)
_verifier("sans fenetre, le pic parasite emporte le decalage",
          abs(_sans7b.decalage_h - 1.5) > 1.0,
          f"{_sans7b.decalage_h:+.2f} h au lieu de +1.50")
_verifier("avec la fenetre, le decalage est le retard REEL de l'evenement",
          abs(_avec7b.decalage_h - 1.5) < 0.05,
          f"{_avec7b.decalage_h:+.2f} h")
_verifier("un decalage juste rend au volume sa mesure",
          abs(_avec7b.rapport_volume - 1.0) < 0.01,
          f"{100 * _avec7b.rapport_volume:.1f} % "
          f"(sans fenetre : {100 * _sans7b.rapport_volume:.1f} %)")
_verifier("un decalage juste rend a la forme la sienne",
          _avec7b.r > 0.999,
          f"r={_avec7b.r:.4f} (sans fenetre : r={_sans7b.r:.4f})")
# SANS FENETRE, RIEN NE CHANGE : la restriction est un choix de
# l'appelant, jamais un comportement nouveau impose aux anciens appels.
_verifier("une fenetre trop courte pour porter un pic est ignoree",
          abs(recaler(_t7b, _cible7b, _t7b, _calc7b,
                      fenetre=(30.0, 30.05))[2] - _sans7b.decalage_h) < 1e-9,
          "repli sur la serie entiere")

print("\n--- 7 ter. Ce que la fenetre laisse dehors est MESURE, pas juge ---")
# LE CAS REEL DE STATUT.txt § 5, EN MINIATURE. La fenetre jugee ferme
# dans la DECRUE,
# parce que fenetre_injection() la clot quand 99 % du DEFICIT est couvert
# et qu'un excedent ne compte pas dans un deficit. Le modele deverse
# ensuite plus que la cible : le verdict reste a 100 %, la serie entiere
# dement. Mesure reelle du 03 et du 04/09/2026 : un apport rend 100,3 %
# sur 4,5-19,7 h et 111,7 % sur la crue entiere, deux calages
# independants.
_t7t = np.linspace(0.0, 48.0, 481)
_cible7t = hydrogramme(_t7t, pic=100.0, t_pic=6.0, forme=3.0)
# Meme crue, meme pointe, mais une decrue qui ne redescend pas : le modele
# garde du debit la ou la cible est retombee. Rien qu'un apport puisse
# corriger — il ne sait qu'ajouter.
_calc7t = _cible7t + 12.0 * np.exp(-((_t7t - 22.0) / 7.0) ** 2)
_fen7t = (0.5, 14.0)     # la ou 99 % du deficit est couvert : avant l'excedent
_d7t = diagnostiquer(_t7t, _cible7t, _t7t, _calc7t,
                     tolerance_volume=0.05, fenetre=_fen7t)
_verifier("le verdict de volume, lui, tient dans la bande",
          abs(_d7t.rapport_volume - 1.0) <= 0.05,
          f"{100 * _d7t.rapport_volume:.1f} % sur la fenetre jugee")
_verifier("la serie entiere est MESUREE, et elle sort de la bande",
          _d7t.rapport_volume_serie is not None
          and _d7t.rapport_volume_serie > 1.05,
          f"{100 * _d7t.rapport_volume_serie:.1f} % sur toute la serie")
_verifier("la part du volume cible que la fenetre retient est chiffree",
          _d7t.part_cible_jugee is not None
          and 0.0 < _d7t.part_cible_jugee < 1.0,
          f"{100 * _d7t.part_cible_jugee:.0f} % du volume de la cible")
_verifier("une reserve le DIT, en nommant les deux lectures",
          any("toute la serie" in a for a in _d7t.alertes),
          " ; ".join(_d7t.alertes) or "aucune alerte")
_verifier("elle ne BLOQUE pas : un excedent hors fenetre se corrige en "
          "amont, pas par cet apport",
          _d7t.converge and not _d7t.alertes_bloquantes,
          f"converge={_d7t.converge}")
# ET ELLE SE TAIT QUAND LES DEUX LECTURES CONCORDENT : une reserve qui se
# leve sur un calage sain apprend a etre ignoree.
_d7t_sain = diagnostiquer(_t7t, _cible7t, _t7t, _cible7t,
                          tolerance_volume=0.05, fenetre=_fen7t)
_verifier("sur un calage exact, aucune reserve et les deux lectures "
          "concordent",
          not _d7t_sain.alertes
          and abs(_d7t_sain.rapport_volume_serie - 1.0) < 1e-6,
          f"{100 * _d7t_sain.rapport_volume_serie:.1f} % sur la serie")
_verifier("sans fenetre, il n'y a rien dehors : les deux nombres sont None",
          diagnostiquer(_t7t, _cible7t, _t7t, _calc7t
                        ).rapport_volume_serie is None)
# ET ELLE SE LEVE AUSSI SUR LE § 7, DELIBEREMENT. La mini-crue anterieure
# y est exclue A BON DROIT, et la serie entiere sort neanmoins de la
# bande : l'enonce reste vrai — le modele double cette mini-crue, et le
# verdict ne le voit pas. Les separer demanderait un seuil d'amplitude
# non mesure ; le signe de l'ecart n'y suffit pas, l'excedent touchant le
# bord de la fenetre DANS LES DEUX CAS. Decision du 05/09/2026 : la
# reserve enonce un PERIMETRE, elle ne denonce pas un defaut.
_verifier("le meme enonce se leve sur une mini-crue exclue a bon droit "
          "(§ 7) — perimetre, pas defaut",
          _avec_fen.rapport_volume_serie is not None
          and any("PERIMETRE" in a for a in _avec_fen.alertes),
          f"fenetre {100 * _avec_fen.rapport_volume:.1f} %, "
          f"serie {100 * _avec_fen.rapport_volume_serie:.1f} %")
_verifier("un verdict DEJA hors bande n'y ajoute pas un second "
          "pourcentage",
          not any("PERIMETRE" in a for a in diagnostiquer(
              _t7t, _cible7t, _t7t, 1.30 * _calc7t,
              tolerance_volume=0.05, fenetre=_fen7t).alertes))

print("\n--- 7 ter bis. Calcul EN AVANCE sur la cible : la couverture se "
      "juge sur le calcul decale, pas sur l'etendue brute des axes ---")
# Le cas du 22/09/2026 : cible de 80 h culminant a 9,5 h ; le modele
# repond 4,6 h plus tot et n'est simule que 20,5 h. La fenetre jugee
# (0-18 h, base de SIMULATION) est calculee en entier : rien ne manque,
# et l'ancien schema annoncait pourtant « ne couvre que 88 % ».
_tc7q = np.linspace(0.0, 80.0, 1601)
_ts7q = np.linspace(0.0, 20.5, 411)
_cible7q = hydrogramme(_tc7q, pic=120.0, t_pic=9.5, forme=2.0)
_calc7q = hydrogramme(_ts7q + 4.6, pic=120.0, t_pic=9.5, forme=2.0)
_d7q = diagnostiquer(_tc7q, _cible7q, _ts7q, _calc7q,
                     fenetre=(0.0, 18.0), decalage_fenetre_h=-4.6)
_verifier("le decalage mesure est bien -4,6 h",
          abs(_d7q.decalage_h + 4.6) < 0.1, f"{_d7q.decalage_h:+.2f} h")
_verifier("aucune bloquante : la fenetre jugee est simulee en entier",
          not _d7q.alertes_bloquantes
          and not any("excede la fenetre" in a for a in _d7q.alertes),
          str(_d7q.alertes))
_verifier("le volume est juge sur toute la fenetre, a 100 %, et converge",
          abs(_d7q.rapport_volume - 1.0) < 0.01 and _d7q.converge,
          f"{100 * _d7q.rapport_volume:.1f} % ; {_d7q.alertes_bloquantes}")
# ET LA BLOQUANTE RESTE VIVE quand le calcul manque vraiment : simule
# 15 h seulement, il ne porte que 15/18 de la fenetre.
_court7q = _ts7q[_ts7q <= 15.0]
_dcourt = diagnostiquer(_tc7q, _cible7q, _court7q,
                        _calc7q[: _court7q.size],
                        fenetre=(0.0, 18.0), decalage_fenetre_h=-4.6)
_verifier("simule 15 h sur une fenetre de 18 h, la couverture bloque",
          any("couvre que 83 %" in a for a in _dcourt.alertes_bloquantes),
          str(_dcourt.alertes_bloquantes))

print("\n--- 7 quater. L'apport peu identifiable est DIT par le Diagnostic, "
      "sans etre juge ---")
# LA REGLE VIT ICI, PAS DANS caler() : le seuil, le texte, et ce qu'il
# chiffre. caler() ne fournit que la part ; le Diagnostic la porte jusqu'au
# classeur et a la note de synthese (07/09/2026).
_res = reserve_identifiabilite(0.02, 0.05)
_verifier("a 2 % de part pour 5 % de tolerance, la reserve se leve",
          _res is not None and "PEU IDENTIFIABLE" in _res,
          (_res or "None")[:60])
_verifier("elle chiffre la part et l'ecart possible",
          _res is not None and "2.0 %" in _res and "250 %" in _res,
          (_res or "")[30:120])
_verifier("un apport qui pese 30 % ne la leve pas",
          reserve_identifiabilite(0.30, 0.05) is None)
_verifier("une part inconnue ne la leve pas — pas de reserve devinee",
          reserve_identifiabilite(None, 0.05) is None)
_verifier("le seuil est strict : part egale a la tolerance, rien",
          reserve_identifiabilite(0.05, 0.05) is None)
_d7q = diagnostiquer(_t7t, _cible7t, _t7t, _cible7t, part_apport=0.02)
_verifier("le Diagnostic la porte, une seule fois",
          sum("PEU IDENTIFIABLE" in a for a in _d7q.alertes) == 1,
          f"{len(_d7q.alertes)} alerte(s)")
_verifier("elle ne bloque pas, et le verdict ne bouge pas",
          not _d7q.alertes_bloquantes and _d7q.converge)
_verifier("la part est portee comme un nombre",
          _d7q.part_apport == 0.02, f"{_d7q.part_apport}")
_verifier("sans part fournie, rien ne change pour les anciens appels",
          not diagnostiquer(_t7t, _cible7t, _t7t, _cible7t).alertes)

# ------------------------------------------------------------------
print("\n--- 7 quinquies. La fenetre est en temps de SIMULATION ---")
# LE DEFAUT DU 08/09/2026, EN MINIATURE, AVEC SES CHIFFRES REELS.
#
# Sur un modele reel (section 5 de STATUT.txt, calage Q20 du 08/09), la
# cible culmine a 0,50 h, le decalage retenu vaut +2,60 h, et
# fenetre_injection ouvre sa fenetre a 2,10 h — en temps de SIMULATION,
# puisqu'elle la mesure sur « cible(t - Dt) - section(t) ».
# diagnostiquer() la lisait sur la base de temps de la CIBLE : tout le pic
# de la cible tombait hors fenetre, son maximum retenu valait 0,93 m3/s au
# lieu de 3,25, et un calage juste a 0,1 % pres etait annonce a 350 % de
# pointe et 370 % de volume. Le calage s'est arrete sur « le modele repond
# de facon trop non lineaire » apres 7 h de calcul, et les onze apports
# suivants n'ont pas ete traites.
_tq = np.arange(0.0, 40.0 + 1e-9, 0.1)
# UNE CIBLE QUI CULMINE TOT : c'est la condition du defaut — le pic de la
# cible doit tomber AVANT le debut de la fenetre.
_cq = 3.25 * np.exp(-0.5 * ((_tq - 0.5) / 1.2) ** 2) + 0.05
_DEC = 2.6
# La section reproduit la cible a Dt pres : le calage est PARFAIT.
_sq = np.interp(_tq - _DEC, _tq, _cq)
_FEN = (2.10, 32.70)          # en temps de simulation, comme la vraie

_sans = diagnostiquer(_tq, _cq, _tq, _sq, fenetre=_FEN)
_avec = diagnostiquer(_tq, _cq, _tq, _sq, fenetre=_FEN,
                      decalage_fenetre_h=_DEC)
_verifier("sans son Dt, la fenetre coupe le pic de la cible et le verdict "
          "s'envole",
          _sans.rapport_pic > 2.0 and _sans.rapport_volume > 2.0,
          f"pointe {100 * _sans.rapport_pic:.0f} %, "
          f"volume {100 * _sans.rapport_volume:.0f} %")
_verifier("avec son Dt, le meme calage est rendu pour ce qu'il est",
          abs(_avec.rapport_pic - 1.0) < 0.02
          and abs(_avec.rapport_volume - 1.0) < 0.02,
          f"pointe {100 * _avec.rapport_pic:.1f} %, "
          f"volume {100 * _avec.rapport_volume:.1f} %")
_verifier("et il converge", _avec.converge, str(_avec.alertes))
# LE DECALAGE MESURE EST LE TROISIEME SYMPTOME DU MEME DEFAUT : le masque
# tronquait le pic de la cible, argmax retombait sur le bord gauche de la
# fenetre, et la difference d'indices rendait +1,00 h au lieu de +2,60.
_verifier("le decalage mesure retrouve celui de la correction",
          abs(_avec.decalage_h - _DEC) < 0.11,
          f"{_avec.decalage_h:+.2f} h (avant : {_sans.decalage_h:+.2f} h)")
# LA FORME ETAIT LA SEULE GRANDEUR JUSTE — elle applique le decalage des
# deux cotes. Elle ne doit pas se degrader au passage.
_verifier("la forme reste juste, elle l'etait deja",
          _avec.r > 0.99, f"r = {_avec.r:.4f}")
# SANS FENETRE, LE PARAMETRE EST SANS OBJET : il n'y a pas de fenetre a
# placer, donc rien a decaler.
_verifier("sans fenetre, le Dt fourni ne change rien",
          abs(diagnostiquer(_tq, _cq, _tq, _sq,
                            decalage_fenetre_h=_DEC).rapport_pic
              - diagnostiquer(_tq, _cq, _tq, _sq).rapport_pic) < 1e-12)
# DEFAUT ABSENT = COMPORTEMENT D'AVANT. Une cible qui culmine DANS la
# fenetre ne bouge pas d'un iota, avec ou sans le parametre : c'est ce qui
# borne le correctif aux seuls cas qu'il repare.
_ct = 3.25 * np.exp(-0.5 * ((_tq - 12.0) / 2.5) ** 2) + 0.05
_st = np.interp(_tq - 0.4, _tq, _ct)
_verifier("une cible qui culmine dans la fenetre est jugee comme avant",
          abs(diagnostiquer(_tq, _ct, _tq, _st, fenetre=(2.0, 30.0),
                            decalage_fenetre_h=0.4).rapport_pic
              - diagnostiquer(_tq, _ct, _tq, _st,
                              fenetre=(2.0, 30.0)).rapport_pic) < 1e-3)

# UN DECALAGE PLUS LONG QUE L'EVENEMENT EST BLOQUANT (09/09/2026).
# Il l'etait PAR ACCIDENT avant le correctif ci-dessus — la fenetre mal
# placee rendait des pourcentages absurdes, qui faisaient echouer
# l'apport. Reparee, elle rendait « conforme » un apport apparie sur un
# decalage qui n'est pas un temps de transfert. Le garde-fou est desormais
# explicite, et il nomme sa cause.
_cb = 45.0 * np.exp(-0.5 * ((_tq - 14.0) / 2.5) ** 2) + 0.05
_sb = np.interp(_tq + 11.0, _tq, _cb)
_db = diagnostiquer(_tq, _cb, _tq, _sb, fenetre=(0.0, 10.3),
                    decalage_fenetre_h=-11.0)
_verifier("un decalage plus long que la fenetre jugee BLOQUE",
          (not _db.converge)
          and any("excede la fenetre jugee" in _a
                  for _a in _db.alertes_bloquantes),
          f"converge={_db.converge}, "
          f"{len(_db.alertes_bloquantes)} bloquante(s)")
_verifier("et il nomme la cause plutot que l'hydraulique",
          any("pas un temps de transfert" in _a
              for _a in _db.alertes_bloquantes))

print("\n--- 8. Tolerance de volume par defaut ---")
# Le defaut precedent (0,5 %) rendait certains modeles hors d'atteinte par
# construction des que le debit de base est marque — voir calage.py,
# Configuration.tolerance_volume.
_verifier("le defaut de Diagnostic.tolerance_volume est 5 %",
          abs(Diagnostic(0, 0, 0, 0).tolerance_volume - 0.05)
          < 1e-9)
import inspect as _inspect
_defaut_diag = _inspect.signature(diagnostiquer).parameters[
    "tolerance_volume"].default
_verifier("le defaut de diagnostiquer(tolerance_volume=...) est 5 %",
          abs(_defaut_diag - 0.05) < 1e-9, f"{_defaut_diag}")

print("\n" + "=" * 74)
if _echecs:
    print(f"{len(_echecs)} ECHEC(S) : {_echecs}")
else:
    print("Tous les controles passent.")
print("=" * 74)
sys.exit(1 if _echecs else 0)
