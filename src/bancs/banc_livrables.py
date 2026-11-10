"""Banc d'auto-test de src/livrables.py.

Ce banc etait le bloc `if __name__ == "__main__":` du module ; il en a ete
sorti le 10/11/2026 pour ne plus partir avec le code dans l'archive du plugin.
Il se lance seul (python3 src/bancs/banc_livrables.py) ou par le relais
que garde src/livrables.py (python3 src/livrables.py).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import livrables
from livrables import (donnees_comparaison, exporter_excel,
                       figure_apports_retenus, figure_atteinte,
                       figure_comparaison, figure_convergence,
                       figure_profil_en_long, figure_profil_longitudinal,
                       journal_essais, synthese, tableau_apports,
                       tableau_de_bord, tableau_geometrie)

from criteres import diagnostiquer

sortie = Path(livrables.__file__).parent.parent / "livrables_exemple"
print(f"Production d'un jeu de livrables de demonstration dans :\n  {sortie}\n")

def hydrogramme(t, pic, t_pic=6.0, forme=2.5):
    t = np.maximum(np.asarray(t, dtype=float), 1e-3)
    return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))

temps = np.linspace(0.01, 36, 500)
sections = ["Section 1 (amont)", "Section 2", "Section 3", "Section 4 (aval)"]
pics_cibles = [45.0, 78.0, 112.0, 145.0]
# PK issus de la projection sur l'axe hydraulique (cf. geometrie.py).
pk_sections = [918.0, 2826.0, 5165.0, 7477.0]
pk_apports = [204.0, 2125.0, 4348.0, 6675.0]
apports_noms = ["Apport 1", "Apport 2", "Apport 3", "Apport 4"]
# Le modele restitue bien l'amont, un peu moins bien l'aval.
facteurs_restitution = [1.002, 0.995, 0.982, 0.951]

diagnostics, pics_calc = [], []
fichiers = []
for nom, pic, f in zip(sections, pics_cibles, facteurs_restitution):
    cible = hydrogramme(temps, pic)
    calcule = hydrogramme(temps - 0.4, pic * f)
    d = diagnostiquer(temps, cible, temps, calcule)
    diagnostics.append(d)
    pics_calc.append(float(np.max(calcule)))
    fichiers.append(figure_comparaison(
        nom, temps, cible, temps, calcule, d,
        sortie / f"comparaison_{nom.split()[1].strip('()')}.png"))

fichiers.append(figure_atteinte(
    sections, diagnostics, sortie / "atteinte_cible.png"))
fichiers.append(figure_profil_longitudinal(
    sections, pics_cibles, pics_calc, sortie / "profil_longitudinal.png",
    pk_m=pk_sections))

# --- profil en long de synthese ---------------------------------------
# Lit a pente 1,2 %o avec un seuil vers PK 4200 et un elargissement aval ;
# en situation reelle ce profil vient du terrain raster ou du maillage.
pk_profil = np.arange(0, 8100, 25.0)
z_fond = 320.0 - 0.0012 * pk_profil
z_fond += 1.6 * np.exp(-((pk_profil - 4200) / 320) ** 2)      # seuil rocheux
z_fond -= 0.9 * np.exp(-((pk_profil - 6400) / 700) ** 2)      # fosse
tirant = 2.6 + 1.1 * np.exp(-((pk_profil - 2900) / 900) ** 2)
profil = pd.DataFrame({
    "pk_m": pk_profil,
    "z_fond": z_fond,
    "z_eau_max": z_fond + tirant,
})
fichiers.append(figure_profil_en_long(
    profil, pk_sections, sortie / "profil_en_long.png",
    noms_sections=[s.split(" (")[0] for s in sections],
    apports_pk=pk_apports, noms_apports=apports_noms,
    pics_cible=pics_cibles, pics_calcule=pics_calc,
    titre="Profil en long — crue Q100 calée (amont → aval)"))

historique = [
    {"essai": 1, "facteur": 1.000, "volume": 0.559, "pic": 0.601},
    {"essai": 2, "facteur": 1.790, "volume": 0.927, "pic": 0.938},
    {"essai": 3, "facteur": 1.946, "volume": 0.994, "pic": 0.991},
    {"essai": 4, "facteur": 1.961, "volume": 1.000, "pic": 0.998},
]
fichiers.append(figure_convergence(
    sections[2], historique, sortie / "convergence_section3.png"))

apports = apports_noms
hydros = [hydrogramme(temps, p) for p in [45.0, 34.0, 36.0, 35.0]]
fichiers.append(figure_apports_retenus(
    apports, temps, hydros, sortie / "apports_retenus.png"))

tb = tableau_de_bord(sections, diagnostics, nb_essais=[2, 3, 4, 5],
                     qualite_numerique=[0.0009, 0.0012, 0.0031, 0.0044])
ta = tableau_apports(apports, [1.000, 1.212, 1.408, 1.961],
                     [float(np.max(h)) for h in hydros],
                     [float(np.trapezoid(h, temps)) * 3.6 for h in hydros])
je = journal_essais(historique)
tg = tableau_geometrie(sections, pk_sections, apports, pk_apports)

xlsx = exporter_excel(sortie / "tableaux_calage.xlsx",
                      Tableau_de_bord=tb, Apports=ta, Journal=je,
                      Implantation=tg)
md = synthese("Calage des apports — note de synthèse", sections,
              diagnostics, sortie / "synthese.md")
# UNE RESERVE D'ENSEMBLE DOIT APPARAITRE, ET AVANT LE DETAIL PAR SECTION.
_res = synthese("essai", sections, diagnostics,
                alertes_chaine=["les deux calendriers ne progressent pas "
                                "au meme rythme"])
_ok = ("## Réserves sur l'ensemble du calage" in _res
       and _res.index("## Réserves sur l'ensemble du calage")
       < _res.index("## Détail par section"))
print(f"   [{'OK' if _ok else 'ECHEC'}] la reserve d'ensemble figure dans "
      f"la synthese, avant le detail par section")
assert _ok
_sans = synthese("essai", sections, diagnostics)
print(f"   [{'OK' if 'Réserves' not in _sans else 'ECHEC'}] et rien ne "
      f"s'ajoute quand il n'y a pas de reserve")
assert "Réserves" not in _sans

print("--- TABLEAU DE BORD ---")
print(tb.drop(columns=["Alertes"]).to_string(index=False))
print("\n--- APPORTS RETENUS ---")
print(ta.to_string(index=False))
print("\n--- IMPLANTATION (PK issus de l'axe hydraulique) ---")
print(tg.to_string(index=False))
print("\n--- FICHIERS PRODUITS ---")
for f in fichiers + [xlsx, str(sortie / "synthese.md")]:
    print("  ", Path(f).name)
print("\n--- EXTRAIT DE LA SYNTHESE ---")
print("\n".join(md.splitlines()[:9]))

# -----------------------------------------------------------------------
# CONTROLES SUR LES VALEURS
#
# Verifier qu'une figure "se produit sans erreur" ne prouve rien : c'est
# par ce trou qu'est passee une regression de l'axe des temps. Les
# controles ci-dessous portent sur des NOMBRES.
# -----------------------------------------------------------------------
from criteres import PAS_RECALAGE_H

print("\n--- CONTROLES SUR LES VALEURS ---")
echecs = []

def controler(libelle, condition, detail=""):
    print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
          + (f"  ->  {detail}" if detail else ""))
    if not condition:
        echecs.append(libelle)

# 1. Axe des temps du panneau recale : pas et origine.
#    Fenetres volontairement differentes, cas ou la regression apparait.
t_cib = np.linspace(0.01, 36, 500)
t_cal = np.linspace(2.0, 48, 700)
axe, c_r, s_r = donnees_comparaison(t_cib, hydrogramme(t_cib, 100.0),
                                    t_cal, hydrogramme(t_cal - 2.0, 100.0))
controler("axe recale : pas conforme",
          abs((axe[1] - axe[0]) - PAS_RECALAGE_H) < 1e-9,
          f"{axe[1] - axe[0]:.4f} h (attendu {PAS_RECALAGE_H})")
controler("axe recale : origine sur la grille commune",
          abs(axe[0] - min(t_cib[0], t_cal[0])) < 1e-9,
          f"{axe[0]:.3f} h (attendu {min(t_cib[0], t_cal[0]):.3f})")
controler("axe recale : longueurs coherentes",
          len(axe) == len(c_r) == len(s_r),
          f"axe {len(axe)}, cible {len(c_r)}, calcule {len(s_r)}")

# 2. Le recalage doit superposer les pics, a un pas de grille pres.
ecart_pics = abs(float(axe[int(np.argmax(c_r))])
                 - float(axe[int(np.argmax(s_r))]))
controler("recalage : pics superposes", ecart_pics <= PAS_RECALAGE_H,
          f"ecart {ecart_pics:.3f} h")

# 3. Tableau de bord : les valeurs doivent etre celles des diagnostics.
#
# Le tableau est exprime en POURCENTAGE d'atteinte de la cible ; le
# controle refait la conversion depuis le diagnostic plutot que de la
# recopier, sans quoi il validerait sa propre erreur.
fidele = all(
    abs(tb.loc[i, "Débit de pointe (% cible)"]
        - round(100 * d.rapport_pic, 1)) < 1e-9
    and abs(tb.loc[i, "Volume (% cible)"]
            - round(100 * d.rapport_volume, 1)) < 1e-9
    and abs(tb.loc[i, "Forme (concordance %)"]
            - round(100 * d.r, 1)) < 1e-9
    and (tb.loc[i, "Statut"] == "Validé") == d.converge
    for i, d in enumerate(diagnostics))
controler("tableau de bord fidele aux diagnostics", fidele,
          f"{len(tb)} ligne(s)")
controler("le tableau de bord ne parle plus en KGE",
          not any(c in tb.columns for c in ("KGE", "r", "alpha", "beta")),
          " | ".join(tb.columns))

# AUCUN JARGON DANS CE QUI EST LIVRE. Les figures, les tableaux et la note
# disent volume, debit de pointe et forme, en pourcentage de la cible. Un
# « KGE » ou un « beta » qui reapparait dans un titre ou une colonne oblige
# le lecteur du rapport a se faire expliquer l'indicateur avant de juger
# le calage.
_jargon = []
_source = Path(livrables.__file__).read_text(encoding="utf-8")
for _motif in ('set_title("', 'set_ylabel("', 'set_xlabel("', 'label="'):
    for _bout in _source.split(_motif)[1:]:
        _texte = _bout.split('"')[0]
        if "KGE" in _texte or "β" in _texte or "α" in _texte:
            _jargon.append(_texte[:50])
controler("aucun jargon dans les libelles de figures", not _jargon,
          " ; ".join(_jargon) or "volume / pointe / forme partout")
controler("la note de synthese parle en pourcentages",
          "KGE" not in md and "% de la cible" in md,
          f"{len(md)} caracteres")

# 4. Tableau d'implantation : les distances doivent se recalculer.
distances = (tg["PK section (m)"] - tg["PK apport (m)"]).round(1)
controler("tableau d'implantation : distances exactes",
          bool((distances == tg["Distance apport-section (m)"]).all()),
          f"{list(distances)[:2]}...")

# 5. Longueurs incoherentes : doit lever une erreur, pas tronquer.
try:
    tableau_de_bord(sections[:2], diagnostics)
    leve = False
except ValueError:
    leve = True
controler("tableau de bord : incoherence de longueur detectee", leve)

# 6. Colonnes facultatives incompletes : ne doit pas planter.
try:
    partiel = tableau_de_bord(sections, diagnostics, nb_essais=[2, 3])
    robuste = partiel["Essais"].tolist()[:2] == [2, 3]
except Exception:
    robuste = False
controler("tableau de bord : colonne facultative incomplete toleree",
          robuste)

# 7. Onglets Excel en collision.
long1 = "Tableau_de_bord_des_sections_de_controle_A"
long2 = "Tableau_de_bord_des_sections_de_controle_B"
try:
    exporter_excel(sortie / "collision.xlsx", **{long1: tb, long2: ta})
    collision = True
except Exception as e:
    collision, detail = False, str(e)[:60]
controler("export Excel : noms d'onglet en collision geres", collision)

# 8. Profil en long troue : les trous ne doivent pas se propager.
profil_troue = profil.copy()
profil_troue.loc[40:60, ["z_fond", "z_eau_max"]] = np.nan
try:
    chemin_troue = figure_profil_en_long(
        profil_troue, pk_sections, sortie / "profil_troue.png",
        apports_pk=pk_apports, pics_cible=pics_cibles,
        pics_calcule=pics_calc)
    troue = Path(chemin_troue).stat().st_size > 10_000
except Exception:
    troue = False
controler("profil en long : axe sortant du maillage supporte", troue)

# 9. Toutes les figures produites sont non triviales.
petites = [Path(f).name for f in fichiers
           if Path(f).suffix == ".png" and Path(f).stat().st_size < 10_000]
controler("figures de taille plausible", not petites,
          f"{len(fichiers)} fichier(s)" if not petites else str(petites))

print()
if echecs:
    print(f"   {len(echecs)} CONTROLE(S) EN ECHEC : {echecs}")
    raise SystemExit(1)
print("   Tous les controles de valeurs passent.")
