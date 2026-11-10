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
    # Rien hors du modele : l'axe qui en deborde n'allonge pas la figure. Les
    # trous interieurs restent des trous.
    dedans = profil["z_fond"].notna().to_numpy()
    if dedans.any():
        rangs = np.flatnonzero(dedans)
        profil = profil.iloc[rangs[0]:rangs[-1] + 1]
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
    # Le banc vit dans src/bancs/ depuis le 10/11/2026 : l'archive du plugin
    # ne l'embarque pas. Dans le depot, ce relais le joue a l'identique.
    import runpy
    import sys
    from pathlib import Path

    _banc = Path(__file__).resolve().parent / "bancs" / "banc_livrables.py"
    if not _banc.is_file():
        print("Le banc de livrables n'est pas livre avec cette installation.",
              file=sys.stderr)
        raise SystemExit(2)
    runpy.run_path(str(_banc), run_name="__main__")
