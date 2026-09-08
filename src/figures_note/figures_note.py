# -*- coding: utf-8 -*-
"""
Figures neuves de la note methodologique (V13).

Chacune REMPLACE de la prose : c'est la consigne. Le style reprend celui des
deux figures conservees (profil en long, correction additive) — meme palette,
meme graisse de titre, meme fond blanc.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Polygon

SORTIE = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
SORTIE.mkdir(parents=True, exist_ok=True)

# Palette relevee sur les figures conservees.
VIOLET = "#8E3B7A"
ROUGE = "#B93A32"
BLEU = "#3E7C93"
BLEU_F = "#2C5F73"
ORANGE = "#E1902F"
VERT = "#2E7D4F"
CREME = "#F7E3CD"
GRIS = "#5A7C8A"
OCRE = "#B8860B"

plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.edgecolor": "#444", "axes.labelcolor": "#222",
    "figure.facecolor": "white", "savefig.facecolor": "white",
})


def _hydro(t, pic, t_pic, largeur, base=0.0):
    return base + pic * np.exp(-0.5 * ((t - t_pic) / largeur) ** 2)


def _titre(fig, titre, sous=None):
    fig.text(0.012, 0.975, titre, fontsize=15, fontweight="bold",
             color=VIOLET, va="top")
    if sous:
        fig.text(0.012, 0.925, sous, fontsize=10.5, color=GRIS, va="top")


def enregistrer(fig, nom):
    chemin = SORTIE / nom
    fig.savefig(chemin, dpi=150, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"   {nom}")


# --------------------------------------------------------------------------
# A — Convention du decalage. REMPLACE le paragraphe « LE SENS DU DECALAGE
# N'EST PAS INTERCHANGEABLE », qui demandait au lecteur de se representer deux
# courbes translatees sans jamais les lui montrer.
# --------------------------------------------------------------------------
def figure_decalage():
    t = np.linspace(0, 24, 400)
    dt = 3.0                                   # le calcul est en AVANCE
    cible = _hydro(t, 300, 12.0, 3.0, base=40)
    section = _hydro(t, 250, 12.0 - dt, 3.0, base=40)

    fig, (g, d) = plt.subplots(1, 2, figsize=(11.5, 4.9))
    fig.subplots_adjust(top=0.70, bottom=0.23, wspace=0.24)

    g.plot(t, cible, color=ROUGE, lw=2.4, label="Cible")
    g.plot(t, section, color=BLEU, lw=2.4, label="Section calculée")
    # LES DEUX PICS SONT RELIES AU TRAIT : sans cela la double fleche flotte
    # au-dessus des courbes sans qu'on voie ce qu'elle mesure.
    for tp, qp in ((9.0, 290), (12.0, 340)):
        g.plot([tp, tp], [qp, 372], color=OCRE, ls=":", lw=1.3)
        g.plot([tp], [qp], "o", color=OCRE, ms=5)
    g.annotate("", xy=(12.0, 372), xytext=(9.0, 372),
               arrowprops=dict(arrowstyle="<->", color=OCRE, lw=2.0))
    g.text(10.5, 386, "Δt", ha="center", color=OCRE, fontweight="bold",
           fontsize=13)
    g.text(0.6, 425, "mesuré UNE fois, pic contre pic,\n"
                     "sur le calcul de référence", color=OCRE, fontsize=8.5,
           va="top")
    g.set_title("Les deux séries n'ont pas la même origine")
    g.set_xlabel("Temps (h)"); g.set_ylabel("Débit (m³/s)")
    g.legend(loc="upper right", fontsize=9); g.grid(alpha=0.25)
    g.set_ylim(0, 440)

    cible_dec = _hydro(t, 300, 12.0 - dt, 3.0, base=40)
    d.plot(t, cible_dec, color=ROUGE, lw=2.4, label="Cible décalée de −Δt")
    d.plot(t, section, color=BLEU, lw=2.4, label="Section calculée")
    d.fill_between(t, section, cible_dec, where=(cible_dec > section),
                   color=CREME, label="Écart réinjecté dans l'apport")
    d.set_title("On décale la CIBLE, jamais le calcul")
    d.set_xlabel("Temps (h)"); d.set_ylabel("Débit (m³/s)")
    d.legend(loc="upper right", fontsize=9); d.grid(alpha=0.25)
    d.set_ylim(0, 440)

    _titre(fig, "Convention de décalage — et pourquoi elle n'est pas réversible",
           "Décaler le calcul de +Δt au lieu de la cible de −Δt donne l'autre "
           "courbe translatée : 68 % d'écart au pic dès Δt = 0,7 h.")
    fig.text(0.5, 0.055,
             "apport(n+1)(t)  =  max( 0 ,  apport(n)(t) + [ cible(t − Δt) − "
             "section(t) ] )",
             ha="center", fontsize=12.5, color=BLEU_F, fontweight="bold")
    enregistrer(fig, "fig_decalage.png")


# --------------------------------------------------------------------------
# B — Resolution sequentielle. REMPLACE « Pourquoi une resolution
# sequentielle » (91 mots) : le schema dit en un coup d'oeil ce que la prose
# expliquait en trois phrases — une inconnue pour une contrainte.
# --------------------------------------------------------------------------
def figure_sequentiel():
    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    fig.subplots_adjust(top=0.70, bottom=0.04)
    ax.set_xlim(0, 12.4); ax.set_ylim(0, 4.5); ax.axis("off")

    etapes = [
        ("Référence", ["A1", "A2", "A3"], -1, "tous les apports à ZÉRO"),
        ("Étape 1", ["A1", "A2", "A3"], 0, "A1 cherché, A2–A3 à zéro"),
        ("Étape 2", ["A1", "A2", "A3"], 1, "A1 FIGÉ, A2 cherché"),
        ("Étape 3", ["A1", "A2", "A3"], 2, "A1–A2 FIGÉS, A3 cherché"),
    ]
    for k, (titre, apports, actif, note) in enumerate(etapes):
        y = 3.55 - k * 1.02
        ax.text(0.05, y + 0.16, titre, fontsize=10.5, fontweight="bold",
                color=BLEU_F, va="center")
        ax.text(0.05, y - 0.19, note, fontsize=8.5, color=GRIS, va="center")
        for i, nom in enumerate(apports):
            x = 2.55 + i * 3.1
            if i < actif:
                fc, ec, tc, lbl = "#E8F0E9", VERT, VERT, "figé"
            elif i == actif:
                fc, ec, tc, lbl = "#FDF0DC", ORANGE, ORANGE, "cherché"
            else:
                fc, ec, tc, lbl = "#F2F2F2", "#AAA", "#999", "zéro"
            ax.add_patch(FancyBboxPatch(
                (x, y - 0.28), 1.05, 0.56, boxstyle="round,pad=0.05",
                fc=fc, ec=ec, lw=1.6))
            ax.text(x + 0.52, y + 0.06, nom, ha="center", fontsize=10,
                    fontweight="bold", color=tc)
            ax.text(x + 0.52, y - 0.16, lbl, ha="center", fontsize=8, color=tc)
            ax.add_patch(FancyBboxPatch(
                (x + 1.35, y - 0.28), 1.05, 0.56, boxstyle="round,pad=0.05",
                fc="#EAF1F5" if i <= actif else "#F7F7F7",
                ec=BLEU if i <= actif else "#CCC", lw=1.4))
            ax.text(x + 1.87, y, f"S{i + 1}", ha="center", va="center",
                    fontsize=10, color=BLEU_F if i <= actif else "#999")
            ax.add_patch(FancyArrowPatch(
                (x + 1.05, y), (x + 1.33, y), arrowstyle="->",
                color="#999", lw=1.1, mutation_scale=11))
            if i < 2:
                ax.add_patch(FancyArrowPatch(
                    (x + 2.42, y), (x + 3.08, y), arrowstyle="->",
                    color="#BBB", lw=1.1, mutation_scale=11))

    ax.add_patch(FancyArrowPatch((2.4, 4.12), (11.9, 4.12), arrowstyle="->",
                                 color=BLEU_F, lw=2.0, mutation_scale=16))
    ax.text(7.1, 4.3, "amont  →  aval", ha="center", fontsize=10.5,
            color=BLEU_F, fontweight="bold")

    _titre(fig, "Résolution séquentielle : une inconnue pour une contrainte",
           "Ajuster N apports sur N cibles à la fois est sur-contraint. Résolus "
           "un par un, les apports amont étant figés, le problème reste bien "
           "posé quel que soit N.")
    enregistrer(fig, "fig_sequentiel.png")


# --------------------------------------------------------------------------
# C — Fenetre de jugement. REMPLACE deux paragraphes du § 1.4 : ce qui est
# juge, ce qui ne l'est pas, et le fait que l'apport, lui, reste calcule
# partout — trois idees qu'un dessin separe mieux qu'une phrase.
# --------------------------------------------------------------------------
def figure_fenetre():
    t = np.linspace(0, 60, 700)
    crue = _hydro(t, 260, 26, 4.2)
    mini = _hydro(t, 28, 7, 1.6)
    base = 18 * np.exp(-t / 90)
    serie = crue + mini + base

    fig, ax = plt.subplots(figsize=(11.5, 4.4))
    fig.subplots_adjust(top=0.68, bottom=0.22)
    t0, tf = 15.0, 40.0
    ax.axvspan(t0, tf, color="#E9F2F6", zorder=0)
    ax.plot(t, serie, color=BLEU, lw=2.3)
    ax.fill_between(t, 0, serie, where=(t >= t0) & (t <= tf),
                    color=CREME, alpha=0.85, zorder=1)
    ax.axvline(t0, color=OCRE, ls="--", lw=1.6)
    ax.axvline(tf, color=OCRE, ls="--", lw=1.6)
    ax.text((t0 + tf) / 2, 388, "FENÊTRE DE JUGEMENT", ha="center",
            va="top", fontsize=11, fontweight="bold", color=OCRE)
    ax.text((t0 + tf) / 2, 360,
            "volume, pointe, forme et couverture\nne sont jugés QUE là",
            ha="center", va="top", fontsize=9, color=OCRE)
    ax.annotate("mini-crue étrangère\nà l'événement calé",
                xy=(7, 46), xytext=(1.5, 170), fontsize=9, color=GRIS,
                arrowprops=dict(arrowstyle="->", color=GRIS, lw=1.2))
    ax.annotate("traîne de débit de base",
                xy=(50, 22), xytext=(44, 140), fontsize=9, color=GRIS,
                arrowprops=dict(arrowstyle="->", color=GRIS, lw=1.2))
    ax.set_xlabel("Temps (h)"); ax.set_ylabel("Débit (m³/s)")
    ax.grid(alpha=0.22); ax.set_ylim(0, 400); ax.set_xlim(0, 60)

    _titre(fig, "La fenêtre de jugement",
           "Détectée dès l'état de référence sur le cumul de la part positive "
           "de l'écart (0,5 % / 99 %, plus 1 h de marge). Elle ne coûte aucun "
           "calcul.")
    fig.text(0.5, 0.045,
             "Elle restreint le JUGEMENT et la PRÉSENTATION — jamais l'apport "
             "injecté, qui reste calculé sur toute la série.",
             ha="center", fontsize=10, color=BLEU_F, style="italic")
    enregistrer(fig, "fig_fenetre.png")


# --------------------------------------------------------------------------
# D — Le cliquet. REMPLACE la demonstration en prose du § 1.5 : l'aire
# hachuree EST la demonstration, et elle se voit.
# --------------------------------------------------------------------------
def figure_cliquet():
    t = np.linspace(0, 24, 400)
    cible = _hydro(t, 280, 11, 3.0, base=12)
    residuel = _hydro(t, 150, 11, 3.4, base=48)

    fig, (g, d) = plt.subplots(1, 2, figsize=(11.5, 4.7))
    fig.subplots_adjust(top=0.68, bottom=0.21, wspace=0.24)

    g.plot(t, cible, color=ROUGE, lw=2.3, label="Cible")
    g.plot(t, residuel, color=BLEU, lw=2.3, ls="--",
           label="Section, apports à zéro")
    g.fill_between(t, residuel, cible, where=(cible > residuel),
                   color=CREME, label="ce qui manque")
    g.fill_between(t, cible, residuel, where=(residuel > cible),
                   color="#F3C9C6", hatch="////", edgecolor=ROUGE, lw=0.6,
                   label="EXCÉDENT déjà présent")
    g.set_title("La section dépasse déjà la cible, par endroits")
    g.set_xlabel("Temps (h)"); g.set_ylabel("Débit (m³/s)")
    g.legend(loc="upper right", fontsize=8.5); g.grid(alpha=0.25)
    g.set_ylim(0, 380)

    apport = np.maximum(cible - residuel, 0.0)
    d.plot(t, apport, color=ORANGE, lw=2.4, label="Apport = max(écart, 0)")
    d.fill_between(t, 0, apport, color="#FCEBD3")
    d.axhline(0, color="#666", lw=1.0)
    d.set_title("Un apport ne sait qu'AJOUTER du débit")
    d.set_xlabel("Temps (h)"); d.set_ylabel("Débit (m³/s)")
    d.legend(loc="upper right", fontsize=9); d.grid(alpha=0.25)
    d.set_ylim(0, 175)
    d.text(0.03, 0.60,
           "l'excédent hachuré ne peut pas\nêtre retiré : il reste dans le\n"
           "volume final",
           transform=d.transAxes, ha="left", fontsize=9.5, color=ROUGE)

    _titre(fig, "Le plancher à zéro est un cliquet",
           "Le volume restitué ne peut pas descendre sous 100 % : il dépasse "
           "la cible exactement de l'aire où la section la dépassait déjà "
           "(2,3 % mesurés sur un modèle au débit de base marqué).")
    fig.text(0.5, 0.045,
             "Un volume qui plafonne au-dessus de 100 % alors que la pointe "
             "manque encore est cette signature — pas un défaut de convergence.",
             ha="center", fontsize=10, color=BLEU_F, style="italic")
    enregistrer(fig, "fig_cliquet.png")


# --------------------------------------------------------------------------
# E — Plans par etape. REMPLACE « Ce que le calage laisse derriere lui »
# (163 mots) et une partie de « Reprendre a un apport donne » (176 mots).
# --------------------------------------------------------------------------
def figure_etapes():
    fig, ax = plt.subplots(figsize=(11.5, 4.0))
    fig.subplots_adjust(top=0.72, bottom=0.02)
    ax.set_xlim(0, 12.6); ax.set_ylim(-0.2, 3.0); ax.axis("off")

    etapes = [("« sans_apport »", "tous à zéro"),
              ("« Apport_A1 »", "A1 calé"),
              ("« Apport_A2 »", "A1–A2 calés"),
              ("« Apport_A3 »", "A1–A3 calés")]
    y = 1.72
    for i, (nom, note) in enumerate(etapes):
        x = 0.25 + i * 3.1
        ax.add_patch(FancyBboxPatch((x, y - 0.42), 2.5, 0.92,
                                    boxstyle="round,pad=0.06",
                                    fc="#EAF1F5", ec=BLEU, lw=1.7))
        ax.text(x + 1.25, y + 0.24, nom, ha="center", fontsize=10.2,
                fontweight="bold", color=BLEU_F)
        ax.text(x + 1.25, y - 0.02, note, ha="center", fontsize=8.6,
                color=GRIS)
        ax.text(x + 1.25, y - 0.26, "plan + débit + résultats",
                ha="center", fontsize=8, color=VERT)
        if i < 3:
            ax.add_patch(FancyArrowPatch(
                (x + 2.5, y), (x + 3.08, y), arrowstyle="->",
                color=BLEU_F, lw=1.7, mutation_scale=15))
            ax.text(x + 2.79, y + 0.16, "clone", ha="center", fontsize=7.6,
                    color=GRIS)

    ax.add_patch(FancyArrowPatch((7.0, 0.82), (7.0, 1.24), arrowstyle="->",
                                 color=ORANGE, lw=2.0, mutation_scale=15))
    ax.text(7.0, 0.50, "« Premier_apport = A3 » repart d'ici :\n"
                       "les apports amont y sont déjà calés, et ne sont "
                       "pas retouchés",
            ha="center", va="top", fontsize=9, color=ORANGE)

    _titre(fig, "Un plan et un fichier de débit conservés par étape",
           "Chaque étape reste figée AVEC SES RÉSULTATS : elle documente ce qui "
           "a été obtenu, et elle est le point de reprise.")
    enregistrer(fig, "fig_etapes.png")


# --------------------------------------------------------------------------
# F — Organigramme. REMPLACE celui de la V12, PERIME : il annoncait un
# recalage « par ecart minimal » (c'est pic contre pic), un ecart « lisse puis
# reinjecte a 90 % » (il est reinjecte tel quel), un controle du nombre de
# Courant (retire) et une boucle de reprise des sections amont (retiree le
# 08/08/2026 — elle ne pouvait rien reprendre, faute de calcul entre deux
# tours ; la chaine SIGNALE desormais et laisse decider).
# --------------------------------------------------------------------------
def figure_organigramme():
    fig, ax = plt.subplots(figsize=(9.8, 12.4))
    fig.subplots_adjust(top=0.955, bottom=0.01, left=0.02, right=0.98)
    ax.set_xlim(0, 10.6); ax.set_ylim(0, 26); ax.axis("off")

    def boite(x, y, w, h, texte, fc, ec, gras=False, fs=9.5):
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                    boxstyle="round,pad=0.08",
                                    fc=fc, ec=ec, lw=1.7))
        ax.text(x, y, texte, ha="center", va="center", fontsize=fs,
                fontweight="bold" if gras else "normal", color="#222")

    def losange(x, y, w, h, texte, fs=9):
        ax.add_patch(Polygon([(x, y + h / 2), (x + w / 2, y),
                              (x, y - h / 2), (x - w / 2, y)],
                             closed=True, fc="white", ec=OCRE, lw=1.7))
        ax.text(x, y, texte, ha="center", va="center", fontsize=fs)

    def fleche(x1, y1, x2, y2, txt="", couleur="#7A8B94", dx=0.14):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="->",
                                     color=couleur, lw=1.5, mutation_scale=13,
                                     connectionstyle="arc3,rad=0"))
        if txt:
            ax.text((x1 + x2) / 2 + dx, (y1 + y2) / 2, txt, fontsize=8.5,
                    color=couleur, fontweight="bold", ha="left", va="center")

    C_VERT, C_BLEU, C_ROUGE = "#E8F0E9", "#EAF1F5", "#FBECEB"

    boite(4.2, 25.2, 5.6, 0.85, "Lecture du classeur et des shapefiles",
          C_VERT, VERT, True)
    fleche(4.2, 24.78, 4.2, 24.35)
    boite(4.2, 23.95, 5.6, 0.8, "PK par projection sur l'axe hydraulique",
          C_BLEU, BLEU)
    fleche(4.2, 23.55, 4.2, 23.05)
    losange(4.2, 22.4, 5.2, 1.35,
            "Données, géométrie, ordre et noms\ncohérents ?  Durées couvertes ?")
    fleche(6.8, 22.4, 8.0, 22.4, "non", ROUGE)
    boite(9.0, 22.4, 1.9, 0.9, "ARRÊT\nanomalies", C_ROUGE, ROUGE, fs=8.5)
    fleche(4.2, 21.72, 4.2, 21.2, "oui", VERT)
    boite(4.2, 20.75, 6.4, 0.95,
          "Calcul de RÉFÉRENCE : tous les apports à ZÉRO\n"
          "(mesure ce que chaque section reçoit déjà)", C_BLEU, BLEU, True,
          fs=9)

    ax.add_patch(FancyBboxPatch((0.35, 5.55), 7.55, 14.35,
                                boxstyle="round,pad=0.1", fc="#F7FAFB",
                                ec=BLEU_F, lw=1.6, ls="--"))
    ax.text(0.6, 19.55, "Pour chaque apport N, de l'amont vers l'aval",
            fontsize=10, fontweight="bold", color=BLEU_F)

    fleche(4.2, 20.28, 4.2, 19.0)
    boite(4.2, 18.6, 5.8, 0.9,
          "Estimation initiale de l'apport N :\nl'écart mesuré lui-même, "
          "écrêté à zéro", "white", BLEU)

    ax.add_patch(FancyBboxPatch((0.85, 8.6), 7.1, 9.4,
                                boxstyle="round,pad=0.08", fc="#FEF8EF",
                                ec=ORANGE, lw=1.4, ls=":"))
    ax.text(1.1, 17.72, "Boucle d'essais sur l'apport N", fontsize=9.5,
            fontweight="bold", color=ORANGE)

    fleche(4.2, 18.15, 4.2, 17.3)
    boite(4.2, 16.9, 5.0, 0.75, "Calcul complet du modèle 2D", C_BLEU, BLEU,
          True)
    fleche(4.2, 16.52, 4.2, 15.95)
    losange(4.2, 15.4, 4.4, 1.15, "Bilan de masse\ndans le seuil ?")
    # UN CALCUL REJETE ARRETE LA RECHERCHE SUR CET APPORT : la fleche va donc
    # a l'ARRET, et non a l'essai suivant. C'est la regle depuis le 07/08/2026.
    ax.text(6.6, 15.62, "non", fontsize=8.5, color=ROUGE, fontweight="bold")
    ax.add_patch(FancyArrowPatch((6.4, 15.4), (8.55, 15.4), arrowstyle="-",
                                 color=ROUGE, lw=1.5))
    ax.add_patch(FancyArrowPatch((8.55, 15.4), (8.55, 11.0), arrowstyle="->",
                                 color=ROUGE, lw=1.5, mutation_scale=13))
    fleche(4.2, 14.82, 4.2, 14.3, "oui", VERT)
    boite(4.2, 13.85, 6.5, 0.95,
          "Diagnostic sur la fenêtre de jugement :\nΔt pic contre pic (figé), "
          "volume, pointe, forme", "white", BLEU, fs=9)
    fleche(4.2, 13.37, 4.2, 12.75)
    losange(4.2, 12.15, 5.0, 1.2,
            "Volume, pointe ET forme\nconformes en même temps ?")
    ax.text(7.05, 12.36, "oui", fontsize=8.5, color=VERT, fontweight="bold")
    ax.add_patch(FancyArrowPatch((6.7, 12.15), (7.6, 12.15), arrowstyle="-",
                                 color=VERT, lw=1.5))
    fleche(4.2, 11.55, 4.2, 10.9, "non", OCRE)
    boite(4.2, 10.45, 6.4, 0.85,
          "Correction additive : l'écart est réinjecté TEL QUEL\n"
          "apport(n+1) = max(0, apport(n) + [cible(t−Δt) − section(t)])",
          "white", BLEU, fs=8.6)
    fleche(1.0, 10.45, 1.0, 16.9, "", ORANGE)
    ax.add_patch(FancyArrowPatch((1.0, 10.45), (1.0, 16.9), arrowstyle="-",
                                 color=ORANGE, lw=1.5))
    ax.add_patch(FancyArrowPatch((1.0, 16.9), (1.68, 16.9), arrowstyle="->",
                                 color=ORANGE, lw=1.5, mutation_scale=13))
    ax.text(1.1, 13.6, "essai suivant", fontsize=8.5, color=ORANGE,
            fontweight="bold", rotation=90, va="center")
    fleche(7.42, 10.45, 8.55, 10.45, "", ROUGE)
    boite(9.55, 9.6, 1.9, 2.6,
          "ARRÊT\n\néloignement,\ncorrection sans effet,\ncible hors "
          "d'atteinte,\nqualité numérique,\nessais épuisés\n\n→ le MEILLEUR "
          "essai\nest conservé", C_ROUGE, ROUGE, fs=7.6)

    boite(4.2, 7.8, 5.4, 0.85, "Apport N validé et FIGÉ\nsuivi actualisé",
          C_VERT, VERT, True)
    ax.add_patch(FancyArrowPatch((7.6, 12.15), (7.6, 7.8), arrowstyle="-",
                                 color=VERT, lw=1.5))
    ax.add_patch(FancyArrowPatch((7.6, 7.8), (6.95, 7.8), arrowstyle="->",
                                 color=VERT, lw=1.5, mutation_scale=13))
    fleche(4.2, 7.35, 4.2, 6.85)
    boite(4.2, 6.35, 6.4, 0.8,
          "Cohérence des sections amont : RELECTURE du dernier calcul.\n"
          "Une dérive est SIGNALÉE, jamais reprise automatiquement.",
          "#FEF8EF", ORANGE, fs=8.4)

    fleche(4.2, 5.5, 4.2, 5.0)
    boite(4.2, 4.6, 5.6, 0.8,
          "Vérification globale finale\n(relecture, aucun calcul de plus)",
          C_BLEU, BLEU, True)
    fleche(4.2, 4.18, 4.2, 3.7)
    boite(4.2, 3.3, 6.4, 0.8,
          "Livrables : profil en long, 6 familles de graphiques,\n"
          "4 tableaux, export Excel, note de synthèse", C_VERT, VERT, True,
          fs=8.8)
    fleche(4.2, 2.88, 4.2, 2.4)
    losange(4.2, 1.85, 4.2, 1.05, "Toutes sections\nconformes ?")
    fleche(6.35, 1.85, 7.6, 1.85, "non", OCRE)
    boite(8.7, 1.85, 2.3, 0.85, "Rapport de\nnon-conformité", "#FEF8EF",
          ORANGE, fs=8.5)
    fleche(4.2, 1.3, 4.2, 0.85, "oui", VERT)
    boite(4.2, 0.45, 3.4, 0.7, "Calage conforme", C_VERT, VERT, True)

    fig.text(0.012, 0.985, "Organigramme général", fontsize=15,
             fontweight="bold", color=VIOLET, va="top")
    enregistrer(fig, "fig_organigramme.png")


if __name__ == "__main__":
    print("Figures :")
    figure_decalage()
    figure_sequentiel()
    figure_fenetre()
    figure_cliquet()
    figure_etapes()
    figure_organigramme()
    print("OK")
