# -*- coding: utf-8 -*-
"""
Production des livrables du calage : graphiques, tableaux et note de synthese.

Comme criteres.py, ce module est INDEPENDANT du code de calcul hydraulique :
il ne consomme que des series temporelles et des objets Diagnostic. Il est
donc utilisable tel quel avec HEC-RAS, TELEMAC-2D ou tout autre modele 2D.

Les figures sont produites en francais, legendees et unitees, de facon a etre
directement inserables dans un rapport d'etude.

Voir methodologie_calage_amont_aval.docx (partie 4 : livrables).
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from criteres import axe_recale, recaler

# --- charte graphique -------------------------------------------------------

CIBLE = "#B03A2E"       # rouge brique : l'objectif a atteindre
CALCULE = "#1B5E7E"     # bleu profond : ce que produit le modele
NEUTRE = "#7F8C8D"
OK = "#1E8449"
ALERTE = "#B9770E"

TERRAIN = "#8D6E4A"     # fond du lit
TERRAIN_CLAIR = "#D8C7AE"
EAU = "#2E86AB"         # ligne d'eau maximale calculee
EAU_CLAIR = "#AED6E8"
APPORT = "#6C3483"      # injections, pour ne pas les confondre avec les sections

plt.rcParams.update({
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": ":",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 130,
})


def _finaliser(fig, chemin):
    fig.tight_layout()
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(chemin)
    plt.close(fig)
    return str(chemin)


# ---------------------------------------------------------------------------
# GRAPHIQUES
# ---------------------------------------------------------------------------

# Les deux memes valeurs que dans le plugin (calage_apports/plugin.py,
# SEUIL_CRUE et MARGE_CRUE_H). L'egalite des deux jeux est VERIFIEE par
# test_plugin_qgis.py : la regle a le droit d'exister en deux exemplaires,
# elle n'a pas le droit de diverger.
SEUIL_CRUE = 0.02      # fraction du debit de pointe sous laquelle on coupe
MARGE_CRUE_H = 0.5     # heures conservees de part et d'autre


def _fenetre_crue(paires, seuil=SEUIL_CRUE, marge_h=MARGE_CRUE_H):
    """
    Bornes temporelles ou la crue est effectivement significative.

    Meme logique (seuil et marge) que la fenetre « 5. Suivi » du plugin
    QGIS (calage_apports/plugin.py, _fenetre_crue) : un hydrogramme saisi
    sur 24 h ne doit pas etaler le trace au-dela de la crue qu'il porte
    reellement. paires : sequence de (temps, debit).
    """
    temps_concat = np.concatenate(
        [np.asarray(t, dtype=float) for t, _ in paires])
    debit_concat = np.concatenate(
        [np.asarray(q, dtype=float) for _, q in paires])
    q_max = float(np.max(debit_concat)) or 1.0
    seuil_q = seuil * q_max
    au_dessus = temps_concat[debit_concat >= seuil_q]
    if au_dessus.size == 0:
        return float(temps_concat.min()), float(temps_concat.max())
    t_debut = max(float(au_dessus.min()) - marge_h, float(temps_concat.min()))
    t_fin = min(float(au_dessus.max()) + marge_h, float(temps_concat.max()))
    return t_debut, t_fin


def donnees_comparaison(temps_cible, debit_cible, temps_calcule, debit_calcule):
    """
    Series recalees et leur axe des temps, tels qu'ils seront traces.

    Le calcul est separe du trace pour qu'il soit VERIFIABLE : une figure ne
    s'auto-teste pas, alors qu'un tableau de valeurs si. C'est par ce trou
    qu'est passee une regression de l'axe des temps, invisible tant que le
    seul controle etait « la figure se produit sans erreur ».

    Retourne (axe_h, cible_recalee, calcule_recale).
    """
    cible, calcule, _ = recaler(temps_cible, debit_cible,
                                temps_calcule, debit_calcule)
    axe = axe_recale(temps_cible, temps_calcule, len(cible))
    return axe, cible, calcule


def figure_comparaison(nom_section, temps_cible, debit_cible,
                       temps_calcule, debit_calcule, diag, chemin):
    """
    Hydrogramme calcule vs hydrogramme cible a une section de controle.
    Deux panneaux : brut (decalage visible) et recale (base du critere de forme).
    C'est le graphique de base du livrable, un par section.
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 6.0), sharey=True)

    ax1.plot(temps_cible, debit_cible, color=CIBLE, lw=2, label="Cible (HSMF)")
    ax1.plot(temps_calcule, debit_calcule, color=CALCULE, lw=2,
             label="Calculé par le modèle")
    ax1.set_title(f"{nom_section} — hydrogrammes bruts", loc="left",
                  fontweight="bold")
    ax1.set_ylabel("Débit (m³/s)")
    ax1.legend(frameon=False)
    ax1.set_xlim(*_fenetre_crue(((temps_cible, debit_cible),
                                 (temps_calcule, debit_calcule))))
    if abs(diag.decalage_h) > 1e-6:
        ax1.annotate(f"décalage détecté : {diag.decalage_h:+.2f} h",
                     xy=(0.98, 0.92), xycoords="axes fraction",
                     ha="right", color=NEUTRE, style="italic")

    axe, c_a, s_a = donnees_comparaison(temps_cible, debit_cible,
                                        temps_calcule, debit_calcule)

    ax2.plot(axe, c_a, color=CIBLE, lw=2, label="Cible (HSMF)")
    ax2.plot(axe, s_a, color=CALCULE, lw=2, label="Calculé, recalé")
    ax2.fill_between(axe, c_a, s_a, color=NEUTRE, alpha=0.18, label="Écart")
    ax2.set_title("Après recalage temporel — base du diagnostic", loc="left",
                  fontweight="bold")
    ax2.set_xlabel("Temps (h)")
    ax2.set_ylabel("Débit (m³/s)")
    ax2.legend(frameon=False)
    ax2.set_xlim(*_fenetre_crue(((axe, c_a), (axe, s_a))))

    couleur = OK if diag.converge else ALERTE
    fig.text(0.5, 0.005, diag.resume(), ha="center", family="monospace",
             fontsize=8.5, color=couleur)
    fig.subplots_adjust(bottom=0.09)
    return _finaliser(fig, chemin)


def figure_convergence(nom_section, historique, chemin):
    """
    Convergence de la recherche : volume et debit de pointe atteints, essai par
    essai, en POURCENTAGE DE LA CIBLE. Rend visible le chemin suivi par la
    correction additive et justifie a posteriori le nombre d'essais.

    historique : liste de dicts {essai, volume, pic, ...}
    """
    df = pd.DataFrame(historique)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.6, 3.1))

    for ax, cle, titre in ((ax1, "volume", "Volume"),
                           (ax2, "pic", "Débit de pointe")):
        # Un historique enregistre avant l'ajout d'une colonne ne doit pas
        # faire perdre la figure entiere : le panneau manquant le dit.
        if cle not in df.columns:
            ax.text(0.5, 0.5, f"{titre} non enregistré", ha="center",
                    va="center", transform=ax.transAxes, color=NEUTRE)
            ax.set_axis_off()
            continue
        ax.plot(df["essai"], 100 * df[cle], "o-", color=CALCULE, lw=1.8)
        ax.axhline(100.0, color=CIBLE, lw=1.4, ls="--", label="cible = 100 %")
        ax.set_xlabel("Essai")
        ax.set_ylabel(f"{titre} atteint (% de la cible)")
        ax.set_title(titre, loc="left", fontweight="bold")
        ax.set_xticks(df["essai"])
        ax.legend(frameon=False)

    fig.suptitle(f"{nom_section} — convergence du calage", fontweight="bold",
                 x=0.01, ha="left")
    return _finaliser(fig, chemin)


def figure_atteinte(noms_sections, diagnostics, chemin):
    """
    Ce qui est atteint, section par section : debit de pointe, volume et
    concordance de forme, en pourcentage de la cible.

    Remplace la decomposition r/alpha/beta du KGE. Meme information utile —
    l'ecart ne se lit pas sur un indicateur agrege, mais sur la grandeur qui
    derive — dite dans l'unite ou l'hydraulicien la juge.
    """
    x = np.arange(len(noms_sections))
    largeur = 0.26
    fig, ax = plt.subplots(figsize=(7.6, 3.4))

    for i, (cle, libelle, couleur) in enumerate([
        ("rapport_pic", "Débit de pointe", "#2E86AB"),
        ("rapport_volume", "Volume", "#117A65"),
        ("r", "Forme", "#5D6D7E"),
    ]):
        valeurs = [100 * getattr(d, cle) for d in diagnostics]
        ax.bar(x + (i - 1) * largeur, valeurs, largeur, label=libelle,
               color=couleur)

    ax.axhline(100.0, color=CIBLE, lw=1.4, ls="--", label="cible = 100 %")
    ax.set_xticks(x)
    ax.set_xticklabels(noms_sections, rotation=20, ha="right")
    ax.set_ylabel("Atteinte de la cible (%)")
    ax.set_title("Ce qui est atteint, par section de contrôle", loc="left",
                 fontweight="bold")
    ax.legend(frameon=False, ncol=4, fontsize=8)
    return _finaliser(fig, chemin)


def _echelle_pk(pk_m):
    """
    Choisit l'unite de l'axe des PK. Au-dela de 3 km, le kilometre evite un
    axe surcharge de zeros. Retourne (valeurs_converties, libelle, facteur).
    """
    pk = np.asarray(pk_m, dtype=float)
    if np.nanmax(pk) - np.nanmin(pk) > 3000:
        return pk / 1000.0, "PK (km)", 1000.0
    return pk, "PK (m)", 1.0


def figure_profil_longitudinal(noms_sections, pics_cible, pics_calcule, chemin,
                               pk_m=None):
    """
    Profil des debits de pointe de l'amont vers l'aval : voit-on une derive
    en s'eloignant de l'amont ?

    pk_m : PK des sections, en metres. S'ils sont fournis, l'axe devient
           METRIQUE — un ecart pris sur 500 m ne s'interprete pas comme le
           meme ecart etale sur 15 km. Sans PK, les sections sont equidistantes.
    """
    metrique = pk_m is not None
    if metrique:
        x, libelle_x, _ = _echelle_pk(pk_m)
        largeur = 0.35 * float(np.min(np.diff(np.sort(x)))) if len(x) > 1 else 0.5
    else:
        x = np.arange(len(noms_sections), dtype=float)
        libelle_x, largeur = None, 0.55

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.6, 4.8), sharex=True,
                                   gridspec_kw={"height_ratios": [2, 1]})

    ax1.plot(x, pics_cible, "o-", color=CIBLE, lw=2, label="Cible (HSMF)")
    ax1.plot(x, pics_calcule, "s--", color=CALCULE, lw=2, label="Calculé")
    ax1.set_ylabel("Débit de pointe (m³/s)")
    ax1.set_title("Profil longitudinal des débits de pointe (amont → aval)",
                  loc="left", fontweight="bold")
    ax1.legend(frameon=False)

    if metrique:
        for xi, nom in zip(x, noms_sections):
            ax1.annotate(nom, xy=(xi, ax1.get_ylim()[0]), xytext=(0, 4),
                         textcoords="offset points", rotation=90, fontsize=7,
                         color=NEUTRE, ha="center", va="bottom")

    ecart = 100 * (np.asarray(pics_calcule, dtype=float)
                   / np.asarray(pics_cible, dtype=float) - 1)
    ax2.bar(x, ecart, color=[OK if abs(e) <= 5 else ALERTE for e in ecart],
            width=largeur)
    ax2.axhline(0, color=NEUTRE, lw=1)
    ax2.axhspan(-5, 5, color=OK, alpha=0.10)
    ax2.set_ylabel("Écart (%)")
    ax2.set_title("Écart sur le pic — bande verte : ±5 %", loc="left",
                  fontsize=8.5, color=NEUTRE)
    if metrique:
        ax2.set_xlabel(libelle_x)
    else:
        ax2.set_xticks(x)
        ax2.set_xticklabels(noms_sections, rotation=20, ha="right")
    return _finaliser(fig, chemin)


def figure_profil_en_long(profil, sections_pk, chemin,
                          noms_sections=None, apports_pk=None,
                          noms_apports=None, pics_cible=None,
                          pics_calcule=None, titre="Profil en long"):
    """
    PROFIL EN LONG DE SYNTHESE — la figure d'ensemble de l'etude.

    Elle superpose, sur un meme axe de PK, ce que la lecture section par
    section ne permet pas de voir : la geometrie du lit, la ligne d'eau
    calculee, la position reelle des sections de controle et des injections,
    et la restitution des debits de pointe. Une derive s'y lit avec son
    contexte physique — rupture de pente, zone de stockage, ouvrage.

    profil      : DataFrame de colonnes 'pk_m' et 'z_fond', plus
                  optionnellement 'z_eau_max'. Produit par
                  geometrie.profil_depuis_modele().
    sections_pk : PK des sections de controle, en metres.
    apports_pk  : PK des injections, en metres (optionnel).
    pics_*      : debits de pointe cible et calcule aux sections. S'ils sont
                  fournis, deux panneaux supplementaires sont traces.
    """
    profil = profil.sort_values("pk_m")
    pk_profil = profil["pk_m"].to_numpy(dtype=float)
    z_fond = profil["z_fond"].to_numpy(dtype=float)
    z_eau = (profil["z_eau_max"].to_numpy(dtype=float)
             if "z_eau_max" in profil.columns else None)

    _, libelle_x, facteur = _echelle_pk(pk_profil)
    x_profil = pk_profil / facteur
    x_sections = np.asarray(sections_pk, dtype=float) / facteur
    x_apports = (np.asarray(apports_pk, dtype=float) / facteur
                 if apports_pk is not None else None)

    avec_debits = pics_cible is not None and pics_calcule is not None
    if avec_debits:
        fig, axes = plt.subplots(3, 1, figsize=(8.0, 7.4), sharex=True,
                                 gridspec_kw={"height_ratios": [3, 2, 1]})
        ax, ax_q, ax_e = axes
    else:
        fig, ax = plt.subplots(figsize=(8.0, 3.6))
        ax_q = ax_e = None

    # --- panneau 1 : geometrie et ligne d'eau ------------------------------
    # Une bande libre est reservee en haut pour les etiquettes d'ouvrage, de
    # facon qu'elles ne recouvrent jamais la ligne d'eau ni la legende.
    z_haut_donnees = float(np.nanmax(z_eau if z_eau is not None else z_fond))
    z_bas_donnees = float(np.nanmin(z_fond))
    plage = max(z_haut_donnees - z_bas_donnees, 1.0)
    bas = z_bas_donnees - 0.16 * plage
    base_bande = z_haut_donnees + 0.06 * plage
    haut = z_haut_donnees + 0.62 * plage

    if z_eau is not None:
        ax.fill_between(x_profil, z_fond, z_eau, where=z_eau > z_fond,
                        color=EAU_CLAIR, alpha=0.75, zorder=1,
                        label="Lame d'eau maximale")
        ax.plot(x_profil, z_eau, color=EAU, lw=1.7, zorder=3,
                label="Ligne d'eau maximale calculée")
    ax.fill_between(x_profil, bas, z_fond, color=TERRAIN_CLAIR, zorder=2)
    ax.plot(x_profil, z_fond, color=TERRAIN, lw=1.5, zorder=4,
            label="Fond du lit")
    ax.set_ylim(bas, haut)
    ax.set_ylabel("Cote (m NGF)")
    ax.set_title(titre, loc="left", fontweight="bold")
    ax.axhline(base_bande, color=NEUTRE, lw=0.7, alpha=0.35, zorder=5)

    for i, xs in enumerate(x_sections):
        # Le trait s'arrete sous la bande d'etiquettes, qu'il barrerait sinon.
        ax.plot([xs, xs], [bas, base_bande], color=CALCULE, lw=1.0, ls="--",
                alpha=0.65, zorder=5)
        if noms_sections is not None:
            ax.text(xs, base_bande + 0.03 * plage, noms_sections[i],
                    rotation=90, fontsize=6.8, color=CALCULE, ha="center",
                    va="bottom", zorder=6)

    if x_apports is not None:
        # Le profil peut comporter des trous là où l'axe sort du maillage :
        # on n'interpole que sur les points renseignés.
        reference = z_eau if z_eau is not None else z_fond
        valides = ~np.isnan(reference)
        z_apport = np.interp(np.asarray(apports_pk, dtype=float),
                             pk_profil[valides], reference[valides])
        for xa, za in zip(x_apports, z_apport):
            ax.plot([xa, xa], [za, base_bande], color=APPORT, lw=0.8, ls=":",
                    alpha=0.6, zorder=5)
        ax.scatter(x_apports, z_apport, marker="v", s=52, color=APPORT,
                   zorder=7, label="Injection d'apport")
        if noms_apports is not None:
            for xa, nom in zip(x_apports, noms_apports):
                ax.text(xa, base_bande + 0.03 * plage, nom, rotation=90,
                        fontsize=6.8, color=APPORT, ha="center", va="bottom",
                        zorder=6)

    # Legende posee sur le remblai de terrain, zone uniforme sans information.
    ax.legend(fontsize=7.6, loc="lower left", ncol=2, framealpha=0.92,
              facecolor="white", edgecolor="none", borderpad=0.5)

    # --- panneau 2 : debits de pointe --------------------------------------
    if avec_debits:
        ax_q.plot(x_sections, pics_cible, "o-", color=CIBLE, lw=2,
                  label="Cible (HSMF)")
        ax_q.plot(x_sections, pics_calcule, "s--", color=CALCULE, lw=2,
                  label="Calculé")
        for xs in x_sections:
            ax_q.axvline(xs, color=CALCULE, lw=0.8, ls="--", alpha=0.25)
        if x_apports is not None:
            for xa in x_apports:
                ax_q.axvline(xa, color=APPORT, lw=0.8, ls=":", alpha=0.45)
        ax_q.set_ylabel("Débit de pointe (m³/s)")
        ax_q.legend(frameon=False, fontsize=8)
        ax_q.set_title("Débits de pointe aux sections de contrôle "
                       "(pointillés violets : injections)",
                       loc="left", fontsize=8.5, color=NEUTRE)

        ecart = 100 * (np.asarray(pics_calcule, dtype=float)
                       / np.asarray(pics_cible, dtype=float) - 1)
        largeur = (0.35 * float(np.min(np.diff(np.sort(x_sections))))
                   if len(x_sections) > 1 else 0.5)
        ax_e.bar(x_sections, ecart, width=largeur,
                 color=[OK if abs(e) <= 5 else ALERTE for e in ecart])
        ax_e.axhline(0, color=NEUTRE, lw=1)
        ax_e.axhspan(-5, 5, color=OK, alpha=0.10)
        ax_e.set_ylabel("Écart (%)")
        ax_e.set_xlabel(libelle_x)
        ax_e.set_title("Écart sur le pic — bande verte : ±5 %", loc="left",
                       fontsize=8.5, color=NEUTRE)
    else:
        ax.set_xlabel(libelle_x)

    return _finaliser(fig, chemin)


def tableau_geometrie(noms_sections, pk_sections, noms_apports=None,
                      pk_apports=None):
    """
    Tableau de reference de l'implantation : PK de chaque section et de chaque
    apport, distances inter-sections, et troncon d'influence de chaque apport.
    Il justifie l'ordre de resolution retenu.
    """
    pk_s = np.asarray(pk_sections, dtype=float)
    lignes = []
    for i, (nom, pk) in enumerate(zip(noms_sections, pk_s)):
        ligne = {
            "Ordre": i + 1,
            "Section": nom,
            "PK section (m)": round(float(pk), 1),
            "Distance amont (m)": (round(float(pk - pk_s[i - 1]), 1)
                                   if i > 0 else None),
        }
        if noms_apports is not None and pk_apports is not None and i < len(noms_apports):
            pk_a = float(np.asarray(pk_apports, dtype=float)[i])
            ligne["Apport"] = noms_apports[i]
            ligne["PK apport (m)"] = round(pk_a, 1)
            ligne["Distance apport-section (m)"] = round(float(pk - pk_a), 1)
        lignes.append(ligne)
    return pd.DataFrame(lignes)


def figure_apports_retenus(noms_apports, temps, hydrogrammes, chemin):
    """
    Hydrogrammes d'apport finalement retenus : le resultat livrable.

    temps : UN AXE PAR APPORT, dans le meme ordre que hydrogrammes — jamais un
    axe commun. Dans un fichier unsteady, chaque hydrogramme est un bloc avec
    son propre « Interval= » et son propre nombre de points, et rien n'oblige
    deux apports du meme modele a partager la meme base de temps. Mesure sur
    un modele de production : douze apports portant 256, 321, 811 ou 1 001
    points. L'axe unique qu'attendait cette fonction levait la une IndexError
    qui a coute au calage entier son classeur et sa note de synthese.
      UN AXE UNIQUE EST ENCORE ACCEPTE, et applique a tous : c'est ce que
      rendent les modeles ou les apports partagent leur base, et l'auto-test
      de ce module en est un.
    """
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    palette = plt.cm.viridis(np.linspace(0.15, 0.85, len(noms_apports)))
    axes = (list(temps) if len(temps) == len(hydrogrammes)
            and np.ndim(temps[0]) > 0 else [temps] * len(hydrogrammes))
    for nom, t_a, q, couleur in zip(noms_apports, axes, hydrogrammes, palette):
        ax.plot(t_a, q, lw=1.9, color=couleur, label=nom)
    ax.set_xlabel("Temps (h)")
    ax.set_ylabel("Débit injecté (m³/s)")
    ax.set_title("Hydrogrammes d'apport retenus après calage", loc="left",
                 fontweight="bold")
    ax.legend(frameon=False, ncol=2, fontsize=8)
    return _finaliser(fig, chemin)


# ---------------------------------------------------------------------------
# TABLEAUX
# ---------------------------------------------------------------------------

def tableau_de_bord(noms_sections, diagnostics, nb_essais=None,
                    qualite_numerique=None):
    """
    Tableau de bord de synthese : une ligne par section de controle.
    C'est le livrable de verification exige par le guide (Lang & Lavabre, p. 81).
    """
    if len(noms_sections) != len(diagnostics):
        raise ValueError(
            f"{len(noms_sections)} section(s) pour {len(diagnostics)} "
            f"diagnostic(s) : le tableau de bord serait tronque en silence.")

    def _valeur(serie, i, arrondi=None):
        """Lit une colonne facultative sans supposer qu'elle est complete."""
        if serie is None or i >= len(serie) or serie[i] is None:
            return None
        return round(serie[i], arrondi) if arrondi is not None else serie[i]

    # Le tableau dit ce qu'on cherche, dans l'unite ou on le lit : un
    # POURCENTAGE D'ATTEINTE de la cible. « 0,993 » et « volume atteint a
    # 99,3 % » sont le meme nombre, mais le second se lit sans decodeur et se
    # reprend tel quel dans un rapport d'etude.
    lignes = []
    for i, (nom, d) in enumerate(zip(noms_sections, diagnostics)):
        lignes.append({
            "Section": nom,
            "Débit de pointe (% cible)": round(100 * d.rapport_pic, 1),
            "Volume (% cible)": round(100 * d.rapport_volume, 1),
            "Forme (concordance %)": round(100 * d.r, 1),
            "Décalage (h)": round(d.decalage_h, 2),
            "Essais": _valeur(nb_essais, i),
            "Bilan masse (%)": _valeur(qualite_numerique, i, 4),
            "Statut": "Validé" if d.converge else "NON VALIDÉ",
            "Alertes": " ; ".join(d.alertes) if d.alertes else "",
        })
    return pd.DataFrame(lignes)


def tableau_apports(noms_apports, facteurs, pics, volumes):
    """
    Apports retenus : le resultat exploitable de l'etude.

    « facteurs » n'est plus un coefficient d'echelle depuis que la correction
    est additive : c'est le rapport entre le volume finalement injecte et celui
    de la premiere estimation. L'intituler « facteur » laisserait croire que
    l'apport livre se deduit d'une forme de reference multipliee par ce
    nombre — ce qui n'est plus vrai, et conduirait a reconstruire un
    hydrogramme faux.
    """
    return pd.DataFrame({
        "Apport": noms_apports,
        "Volume retenu / 1re estimation": [round(f, 4) for f in facteurs],
        "Pic injecte (m3/s)": [round(p, 2) for p in pics],
        "Volume injecte (1000 m3)": [round(v, 1) for v in volumes],
    })


def tableau_hydrogrammes_apports(noms_apports, temps_par_apport,
                                 hydrogrammes):
    """
    Hydrogrammes d'apport RETENUS : une colonne de temps, une colonne par
    apport — la forme exacte de la feuille « Cibles » du classeur de saisie,
    pour que les deux se superposent d'un coup d'oeil.

    tableau_apports() ne livre que le pic et le volume ; la SERIE elle-meme ne
    figurait dans aucun tableau, seulement dans la figure apports_retenus.png
    et dans le fichier unsteady du modele. Elle n'etait donc ni verifiable
    ligne a ligne, ni reutilisable hors HEC-RAS.

    CHAQUE APPORT PORTE SA PROPRE BASE DE TEMPS, et c'est la raison d'etre du
    parametre « temps_par_apport ». Releve en production : douze apports au
    meme pas de 6 min, comptant 256, 321, 811 ou 1 001 valeurs, parce que
    chaque bloc conserve SA duree. Les colonnes sont donc alignees sur
    l'UNION des instants, et la ou un apport n'a pas de valeur la cellule
    reste VIDE : interpoler ou prolonger y ecrirait un debit que le calcul
    n'a jamais recu.

    Debits arrondis au millieme de m3/s : le fichier unsteady stocke ses
    hydrogrammes sur un champ de huit caracteres, et l'arrondi divise par
    trois le poids de la feuille sans rien perdre de ce que le modele a
    reellement recu.
    """
    if not (len(noms_apports) == len(temps_par_apport) == len(hydrogrammes)):
        raise ValueError(
            f"{len(noms_apports)} apport(s) pour {len(temps_par_apport)} "
            f"base(s) de temps et {len(hydrogrammes)} hydrogramme(s) : les "
            f"colonnes porteraient le nom d'un apport et les debits d'un "
            f"autre.")

    colonnes = []
    for nom, t, q in zip(noms_apports, temps_par_apport, hydrogrammes):
        # Index arrondi au millieme d'heure (3,6 s) : deux bases construites
        # separement different au 1e-16 et fabriqueraient deux lignes la ou il
        # n'y a qu'un instant.
        colonnes.append(pd.Series(
            np.round(np.asarray(q, dtype=float), 3),
            index=np.round(np.asarray(t, dtype=float), 3),
            name=f"Apport_{nom}"))
    table = pd.concat(colonnes, axis=1).sort_index()
    table.insert(0, "Temps_h", table.index)
    return table.reset_index(drop=True)


def journal_essais(enregistrements):
    """
    Journal complet de tous les essais, toutes sections confondues.
    Assure la tracabilite : indispensable pour une etude reglementaire.
    """
    return pd.DataFrame(enregistrements)


def exporter_excel(chemin, **tableaux):
    """
    Ecrit tous les tableaux dans un classeur Excel, un onglet par tableau.

    Excel limite les noms d'onglet a 31 caracteres. Deux noms qui ne different
    qu'au-dela seraient tronques a l'identique et openpyxl refuserait le
    doublon : les collisions sont donc levees en numerotant.
    """
    Path(chemin).parent.mkdir(parents=True, exist_ok=True)
    utilises = set()

    def onglet(nom):
        court = nom[:31]
        if court not in utilises:
            utilises.add(court)
            return court
        for i in range(2, 100):
            suffixe = f"_{i}"
            candidat = nom[:31 - len(suffixe)] + suffixe
            if candidat not in utilises:
                utilises.add(candidat)
                return candidat
        raise ValueError(f"trop de noms d'onglet en collision sur « {court} »")

    with pd.ExcelWriter(chemin, engine="openpyxl") as writer:
        for nom, df in tableaux.items():
            df.to_excel(writer, sheet_name=onglet(nom), index=False)
    return str(chemin)


# ---------------------------------------------------------------------------
# SYNTHESE
# ---------------------------------------------------------------------------

def synthese(titre, noms_sections, diagnostics, chemin=None,
             alertes_chaine=()):
    """
    Note de synthese textuelle : conclusion de conformite et points d'attention.
    Redigee pour etre reprise telle quelle dans un rapport d'etude.

    alertes_chaine : reserves qui portent sur L'ENSEMBLE du calage et non sur
        une section — la coherence du decalage le long de l'axe, par exemple.
        Diagnostic.alertes est par section ; ce qui se constate sur les douze
        n'avait aucun endroit pour etre dit, et restait dans le journal texte
        que le lecteur d'un rapport n'ouvre jamais. Non bloquantes : elles
        n'entrent pas dans la conclusion de conformite.
    """
    valides = [d.converge for d in diagnostics]
    n, n_ok = len(diagnostics), sum(valides)
    # Les ecarts sont dits en POURCENTAGE D'ATTEINTE de la cible : c'est ce
    # qu'un lecteur de rapport d'etude sait juger, la ou un indicateur agrege
    # demande d'abord d'etre explique.
    pics = [100 * d.rapport_pic for d in diagnostics]
    volumes = [100 * d.rapport_volume for d in diagnostics]

    def _pire(valeurs):
        """Valeur la plus eloignee de 100 %."""
        return max(valeurs, key=lambda v: abs(v - 100.0))

    lignes = [
        f"# {titre}",
        "",
        "## Conclusion",
        "",
    ]
    if n_ok == n:
        # La note est un livrable remis au client : l'accord doit suivre le
        # nombre reel de sections, y compris quand il n'y en a qu'une.
        sujet = ("la section de contrôle restitue" if n == 1
                 else f"les {n} sections de contrôle restituent")
        lignes.append(
            f"Le calage est **conforme** : {sujet} l'hydrogramme cible en "
            f"volume, en débit de pointe et en forme. Écart maximal constaté : "
            f"{abs(_pire(volumes) - 100):.1f} % sur le volume et "
            f"{abs(_pire(pics) - 100):.1f} % sur le débit de pointe."
        )
    else:
        lignes.append(
            f"Le calage est **partiellement conforme** : {n_ok} section(s) sur "
            f"{n} atteignent la cible en volume, en débit de pointe et en "
            f"forme. Les sections non validées sont listées ci-dessous et "
            f"doivent être reprises avant exploitation des résultats."
        )
    lignes += [
        "",
        f"- Débit de pointe : de {min(pics):.1f} % à {max(pics):.1f} % "
        f"de la cible",
        f"- Volume : de {min(volumes):.1f} % à {max(volumes):.1f} % "
        f"de la cible",
        f"- Décalage temporel maximal : "
        f"{max(abs(d.decalage_h) for d in diagnostics):.2f} h "
        f"(surveillé, non corrigé)",
        "",
    ]
    # AVANT LE DETAIL PAR SECTION, ET APRES LA CONCLUSION : une reserve qui
    # porte sur tout le calage se lit avant qu'on entre dans les sections, sans
    # quoi elle passe pour un commentaire sur la derniere.
    if alertes_chaine:
        lignes += ["## Réserves sur l'ensemble du calage", ""]
        lignes += [f"- {a}" for a in alertes_chaine]
        lignes.append("")
    lignes += [
        "## Détail par section",
        "",
    ]
    for nom, d in zip(noms_sections, diagnostics):
        etat = "OK" if d.converge else "NON VALIDÉ"
        lignes.append(f"- **{nom}** — {etat} — {d.resume()}")
        for a in d.alertes:
            lignes.append(f"    - alerte : {a}")

    lignes += [
        "",
        "## Vérifications exigées par le guide méthodologique",
        "",
        "Conformément à Lang & Lavabre (2007), p. 81, les points suivants ont "
        "été contrôlés :",
        "",
        "1. Cohérence de forme entre l'hydrogramme de référence et le calcul, "
        "évaluée après recalage temporel.",
        "2. Cohérence fréquentielle, par comparaison du volume et du débit de "
        "pointe à la cible HSMF.",
        "3. Absence de dérive en fréquence vers l'aval, contrôlée par le profil "
        "longitudinal des débits de pointe.",
        "",
        "## Outils",
        "",
        # Les auteurs de ras-commander demandent que les travaux publies
        # s'appuyant sur elle la citent. La note de synthese etant destinee a
        # etre reprise dans un rapport, la mention doit y figurer d'office :
        # une citation qu'il faut penser a ajouter ne l'est jamais.
        "Le pilotage de HEC-RAS s'appuie sur **ras-commander v0.99.1** "
        "(CLB Engineering Corporation), bibliothèque libre — "
        "github.com/gpt-cmdr/ras-commander. Merci de conserver cette mention "
        "dans toute publication reprenant ces résultats "
        "(rascommander.info/ras/cite/).",
    ]

    texte = "\n".join(lignes)
    if chemin:
        Path(chemin).parent.mkdir(parents=True, exist_ok=True)
        Path(chemin).write_text(texte, encoding="utf-8")
    return texte


# ---------------------------------------------------------------------------
# Auto-test : produit un jeu complet de livrables sur donnees synthetiques
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from criteres import diagnostiquer

    sortie = Path(__file__).parent.parent / "livrables_exemple"
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
    _source = Path(__file__).read_text(encoding="utf-8")
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
