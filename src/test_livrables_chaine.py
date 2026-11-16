"""
Caracterisation de la chaine des livrables d'un calage : ce que l'ingenieur
livre et relit a la fin de plusieurs heures de calcul.

TROIS FONCTIONS, ET TOUT CE QU'ELLES PRODUISENT, figes AVANT de les decouper
(10/11/2026) :
  - calage.produire_livrables_finaux : fichiers ecrits (noms, ordre, contenu),
    valeur rendue, messages (avertissements de queue, figures non produites),
    exception ;
  - livrables.figure_profil_en_long : CONTENU de la figure ;
  - suivi._onglet_iterations : le classeur iterations.xlsx du suivi, cellule
    par cellule, et ses graphiques.
Un chiffre ou un libelle faux y passe tel quel dans un rapport d'etude
d'inondation : metadata.txt en garde la trace (0.7.16, un panneau « Volume »
qui tracait le biais du KGE ; 0.9.23, un profil en long hors du modele).

LES ENTREES SONT VRAIES : un calage complet sur calage.ModeleFictif, nourri a
un vrai suivi.Suivi, puis produire_livrables_finaux sur son resultat. Quelques
cas appellent directement figure_profil_en_long et _onglet_iterations, pour
les branches qu'un calage n'atteint pas.

CE QUI EST FIGE, PAR NATURE DE SORTIE.
  - FIGURES : pas de pixels (ils dependent des polices et de matplotlib). Ce
    que la figure CONTIENT, relu au moment de son enregistrement : par axe,
    titres, libelles, bornes, graduations imposees, legende ; par courbe sa
    legende, sa couleur, son style et ses donnees ; textes, annotations,
    barres et zones colorees ; et le fichier image, existant et non vide.
  - CLASSEURS : feuilles et leur ordre, chaque cellule (valeur, type, format,
    gras, taille, alignement), largeurs, volets figes, fusions, mises en
    forme conditionnelles ; les graphiques tels qu'ils sont ENREGISTRES
    (relus en memoire au moment de Workbook.save : le lecteur d'openpyxl ne
    rend pas leur taille).
  - TEXTES (note de synthese, messages, valeur rendue) : au caractere pres.
  - NOMBRES : au bit pres (float.hex). Les series longues sont condensees en
    une empreinte SHA-256 et quelques sommes, ecrites elles aussi au bit pres.

HORS DU SOCLE OU LA REFERENCE A ETE FIGEE (numpy, matplotlib, openpyxl,
pandas, systeme, machine), le test compare en REPLI, et le dit par un
avertissement : les empreintes et ce qui depend de la version d'une
bibliotheque (bornes d'axe calculees par matplotlib, mise en forme des
en-tetes ecrite par pandas — cles prefixees de « ~ ») sont ecartes, les
nombres compares a TOLERANCE_HORS_SOCLE pres en relatif, tout le reste
exactement. Le repli est EPROUVE ici meme, sur un socle simule.

NEUTRALISE A LA SOURCE : le dossier temporaire (« <DOSSIER> »), l'horloge
de calage.py (un compteur), la police par defaut du poste. DOUBLE : les trois
figures du suivi (avancement, section, convergence) — hors de cette chaine,
horodatees, et les deux tiers du temps du test. Une defaillance simulee de
figure_apports_retenus eprouve le garde-fou qui l'entoure.

SANS h5py NI ras-commander : tourne dans le job « noyau » de la CI.

CE TEST NE DIT PAS CE QUE LE CODE DEVRAIT FAIRE : il enregistre ce qu'il fait.

    python -m pytest src/test_livrables_chaine.py -q
    python src/test_livrables_chaine.py --figer      (reecrit la reference)
"""
import contextlib
import hashlib
import io
import json
import platform
import sys
import warnings
from pathlib import Path
from unittest import mock

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors     # noqa: E402
import matplotlib.pyplot as plt         # noqa: E402
import matplotlib.ticker as mticker     # noqa: E402
from matplotlib.collections import PathCollection   # noqa: E402
from matplotlib.figure import Figure    # noqa: E402
from matplotlib.text import Annotation  # noqa: E402
import numpy as np                      # noqa: E402
import openpyxl                         # noqa: E402
from openpyxl.workbook.workbook import Workbook      # noqa: E402
import pandas as pd                     # noqa: E402
import pytest                           # noqa: E402

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
import calage as cg                     # noqa: E402
import livrables as liv                 # noqa: E402
import suivi as sv                      # noqa: E402

REFERENCE = SRC / "reference_livrables_chaine.json"
TOLERANCE_HORS_SOCLE = 1e-9
# Au-dela, une serie est condensee (empreinte et sommes) plutot qu'ecrite.
COURTE = 16


# ---------------------------------------------------------------------------
# Figer une valeur
# ---------------------------------------------------------------------------

def _f(x):
    """Grandeur CALCULEE : au bit pres, comparee a la tolerance hors socle."""
    return "f:" + float(x).hex()


def _serie(valeurs):
    """
    Une serie de nombres. Courte : chaque valeur. Longue : sa longueur, ses
    trous (NaN) en plages, une empreinte au bit pres et sept grandeurs qui
    survivent au repli — premiere, derniere, min, max, somme des valeurs
    absolues, somme ponderee par le rang (un ordre change la deplace), somme
    des carres.
    """
    a = np.asarray(valeurs, dtype=float).ravel()
    if a.size <= COURTE:
        return [_f(v) for v in a]
    trous = np.isnan(a)
    v = a[~trous]
    rang = np.arange(1, a.size + 1, dtype=float)[~trous]
    fige = {"n": int(a.size), "trous": _plages(np.flatnonzero(trous)),
            "sha": hashlib.sha256(np.ascontiguousarray(a).tobytes())
            .hexdigest()[:24]}
    if v.size:
        fige["stats"] = [_f(v[0]), _f(v[-1]), _f(v.min()), _f(v.max()),
                         _f(np.abs(v).sum()), _f((rang * np.abs(v)).sum()),
                         _f((v * v).sum())]
    return fige


def _plages(indices):
    """[3, 4, 5, 9] -> [[3, 5], [9, 9]]."""
    plages = []
    for i in (int(k) for k in indices):
        if plages and plages[-1][1] == i - 1:
            plages[-1][1] = i
        else:
            plages.append([i, i])
    return plages


def _couleur(c):
    return mcolors.to_hex(c, keep_alpha=True)


def _couleurs(cs):
    return [_couleur(c) for c in mcolors.to_rgba_array(cs)]


def _scalaire(v):
    """Reglage de style passe tel quel : compare exactement, partout."""
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_scalaire(x) for x in v]
    return str(v)


# ---------------------------------------------------------------------------
# Ce qu'une figure contient
# ---------------------------------------------------------------------------

def _famille(t):
    """
    La police que le CODE impose (« monospace »), ou « defaut » : la police
    par defaut vient de la configuration du poste (matplotlibrc), pas de la
    chaine — « Inter » ici, « sans-serif » sur la CI.
    """
    famille = list(t.get_family())
    return "defaut" if famille == list(plt.rcParams["font.family"]) else famille


def _texte(t):
    fige = {"texte": t.get_text(), "position": [_f(c) for c in t.get_position()],
            "couleur": _couleur(t.get_color()), "rotation": t.get_rotation(),
            "ha": t.get_ha(), "va": t.get_va(), "taille": t.get_fontsize(),
            "style": t.get_style(), "graisse": str(t.get_weight()),
            "famille": _famille(t), "zorder": t.get_zorder()}
    if isinstance(t, Annotation):
        fige["annote"] = [_f(c) for c in t.xy]
        fige["repere"] = str(t.xycoords)
        fige["repere_texte"] = str(t.anncoords)
    return fige


def _bornes(ax, axe):
    """Bornes imposees par le code : exactes. Calculees par matplotlib : « ~ »."""
    if axe == "x":
        auto, lim = ax.get_autoscalex_on(), ax.get_xlim()
    else:
        auto, lim = ax.get_autoscaley_on(), ax.get_ylim()
    return ("~" if auto else "") + f"bornes_{axe}", [_f(v) for v in lim]


def _graduations(axis):
    fige = {}
    locator, formatter = axis.get_major_locator(), axis.get_major_formatter()
    if isinstance(locator, mticker.FixedLocator):
        fige["positions"] = _serie(locator.locs)
    if isinstance(formatter, mticker.FixedFormatter):
        fige["etiquettes"] = list(formatter.seq)
        etiquettes = axis.get_ticklabels()
        if etiquettes:
            fige["rotation"] = etiquettes[0].get_rotation()
            fige["ha"] = etiquettes[0].get_ha()
    return fige


def _legende_de(artiste):
    """
    « _child7 » et ses semblables sont des noms que matplotlib donne aux
    artistes SANS legende ; leur numero suit un compteur interne. Seul compte
    qu'ils n'en ont pas.
    """
    nom = artiste.get_label()
    return "_" if nom.startswith("_") else nom


def _ligne(ln):
    return {"legende": _legende_de(ln), "couleur": _couleur(ln.get_color()),
            "style": ln.get_linestyle(), "epaisseur": ln.get_linewidth(),
            "marqueur": str(ln.get_marker()), "alpha": ln.get_alpha(),
            "zorder": ln.get_zorder(),
            "x": _serie(np.asarray(ln.get_xdata(orig=True), dtype=float)),
            "y": _serie(np.asarray(ln.get_ydata(orig=True), dtype=float))}


def _collection(c):
    fige = {"legende": _legende_de(c), "fond": _couleurs(c.get_facecolor()),
            "alpha": c.get_alpha(), "zorder": c.get_zorder()}
    if isinstance(c, PathCollection):
        xy = np.asarray(c.get_offsets(), dtype=float).reshape(-1, 2)
        fige.update(genre="nuage", x=_serie(xy[:, 0]), y=_serie(xy[:, 1]),
                    tailles=[_scalaire(s) for s in c.get_sizes()])
    else:
        # LES SOMMETS EN ENSEMBLE, PAS EN SUITE : leur ordre et le point de
        # fermeture des polygones changent d'une version de matplotlib a
        # l'autre ; les points eux-memes, non.
        sommets = [p.vertices for p in c.get_paths() if len(p.vertices)]
        xy = (np.unique(np.concatenate(sommets), axis=0) if sommets
              else np.empty((0, 2)))
        fige.update(genre="polygones", x=_serie(xy[:, 0]), y=_serie(xy[:, 1]))
    return fige


def _rectangle(p):
    """Barre ou bande (axhspan) : son emprise, quelle que soit sa classe."""
    xy = p.get_patch_transform().transform(p.get_path().vertices)
    return {"emprise": [_f(xy[:, 0].min()), _f(xy[:, 1].min()),
                        _f(xy[:, 0].max()), _f(xy[:, 1].max())],
            "fond": _couleur(p.get_facecolor()), "alpha": p.get_alpha(),
            "zorder": p.get_zorder(), "legende": _legende_de(p)}


def _legende(ax):
    leg = ax.get_legend()
    if leg is None:
        return None
    return {"textes": [t.get_text() for t in leg.get_texts()],
            "colonnes": getattr(leg, "_ncols", getattr(leg, "_ncol", None)),
            "position": _scalaire(leg._loc),
            "cadre": leg.get_frame_on(),
            "taille": (leg.get_texts()[0].get_fontsize()
                       if leg.get_texts() else None)}


def _ordre(ax):
    """
    L'ORDRE DE TRACE, toutes natures confondues : courbes, zones, barres et
    textes vivent dans des listes separees, et une permutation entre deux
    natures n'y laisserait aucune trace.
    """
    natures = ([(a, "ligne") for a in ax.lines]
               + [(a, "collection") for a in ax.collections]
               + [(a, "rectangle") for a in ax.patches]
               + [(a, "texte") for a in ax.texts])
    nature = {id(a): n for a, n in natures}
    return [nature[id(a)] for a in ax.get_children() if id(a) in nature]


def _axe(ax, fig):
    gs = ax.get_subplotspec().get_gridspec()
    fige = {
        "ordre": _ordre(ax),
        "grille": [gs.nrows, gs.ncols, _scalaire(gs.get_height_ratios()),
                   _scalaire(gs.get_width_ratios())],
        "x_partage": ax.get_shared_x_axes().joined(ax, fig.axes[0]),
        "visible": ax.axison,
        "titres": {
            loc: [t.get_text(), t.get_fontsize(), str(t.get_weight()),
                  _couleur(t.get_color())]
            for loc, t in (("left", ax._left_title), ("center", ax.title),
                           ("right", ax._right_title)) if t.get_text()},
        "x": ax.get_xlabel(), "y": ax.get_ylabel(),
        "graduations_x": _graduations(ax.xaxis),
        "graduations_y": _graduations(ax.yaxis),
        "lignes": [_ligne(ln) for ln in ax.lines],
        "collections": [_collection(c) for c in ax.collections],
        "rectangles": [_rectangle(p) for p in ax.patches],
        "barres": [_legende_de(c) for c in ax.containers],
        "textes": [_texte(t) for t in ax.texts],
        "legende": _legende(ax),
    }
    for axe in ("x", "y"):
        cle, valeur = _bornes(ax, axe)
        fige[cle] = valeur
    return fige


def _figure(fig):
    sup = getattr(fig, "_suptitle", None)
    return {"taille": _scalaire(list(fig.get_size_inches())),
            "suptitre": _texte(sup) if sup is not None else None,
            "textes": [_texte(t) for t in fig.texts],
            "axes": [_axe(ax, fig) for ax in fig.axes]}


@contextlib.contextmanager
def _capter_figures(journal, neutre, ecritures=None):
    """Chaque figure ENREGISTREE est relue juste avant d'etre ecrite."""
    original = Figure.savefig

    def savefig(fig, fname, *arguments, **nommes):
        journal.append({"fichier": neutre(str(fname)), "figure": _figure(fig)})
        if ecritures is not None:
            ecritures.append(neutre(str(fname)))
        return original(fig, fname, *arguments, **nommes)

    with mock.patch.object(Figure, "savefig", savefig):
        yield


@contextlib.contextmanager
def _capter_textes(ecritures, neutre):
    """L'ORDRE D'ECRITURE EST UN RESULTAT : la note est ecrite en dernier."""
    original = Path.write_text

    def write_text(chemin, *arguments, **nommes):
        ecritures.append(neutre(str(chemin)))
        return original(chemin, *arguments, **nommes)

    with mock.patch.object(Path, "write_text", write_text):
        yield


# ---------------------------------------------------------------------------
# Ce qu'un classeur contient
# ---------------------------------------------------------------------------

def _texte_riche(titre):
    """Texte d'un titre de graphique openpyxl, ou None."""
    if titre is None or titre.tx is None or titre.tx.rich is None:
        return None
    return "".join(r.t for p in titre.tx.rich.p for r in (p.r or []))


def _graphique(ch, racine=True):
    fige = {"type": type(ch).__name__, "titre": _texte_riche(ch.title),
            "x": _texte_riche(ch.x_axis.title),
            "y": _texte_riche(ch.y_axis.title),
            "axe_y": [ch.y_axis.axId, ch.y_axis.crosses],
            "series": [[s.val.numRef.f if s.val is not None else None,
                        (s.cat.numRef.f if s.cat is not None
                         and s.cat.numRef is not None else None),
                        s.tx.strRef.f if s.tx is not None else None]
                       for s in ch.series]}
    if racine:
        fige["taille"] = [ch.width, ch.height]
        fige["ancre"] = ch.anchor if isinstance(ch.anchor, str) else None
        fige["combines"] = [_graphique(c, racine=False)
                            for c in ch._charts if c is not ch]
    return fige


@contextlib.contextmanager
def _capter_graphiques(graphiques, ecritures=None, neutre=str):
    """
    Les graphiques tels qu'ils partent a l'ecriture : le lecteur d'openpyxl
    en perd la taille. Le dernier enregistrement d'un fichier fait foi.
    """
    original = Workbook.save

    def save(wb, filename):
        nom = Path(getattr(filename, "name", filename)).name
        if ecritures is not None:
            ecritures.append(neutre(str(getattr(filename, "name", filename))))
        nom = nom.replace(".tmp.xlsx", ".xlsx")
        graphiques[nom] = {ws.title: [_graphique(c) for c in ws._charts]
                           for ws in wb.worksheets}
        return original(wb, filename)

    with mock.patch.object(Workbook, "save", save):
        yield


def _style(c):
    return [c.number_format, bool(c.font.b), _scalaire(c.font.sz),
          c.alignment.wrap_text, c.alignment.horizontal,
          c.border.left.style if c.border is not None else None,
          (c.fill.fgColor.rgb if c.fill is not None and c.fill.fill_type
           else None)]


def _colonne(cellules, dependant):
    """
    Une colonne : ses textes en clair, ses nombres en serie (dans l'ordre des
    lignes), et en plages les types et les mises en forme.
    """
    textes, rangs_nombres, nombres, types, styles = [], [], [], [], []

    def empiler(plages, rang, valeur):
        if plages and plages[-1][2] == valeur and plages[-1][1] == rang - 1:
            plages[-1][1] = rang
        else:
            plages.append([rang, rang, valeur])

    for c in cellules:
        v = c.value
        empiler(types, c.row, type(v).__name__)
        empiler(styles, c.row, _style(c))
        if isinstance(v, bool) or v is None:
            textes.append([c.row, v])
        elif isinstance(v, (int, float)):
            rangs_nombres.append(c.row)
            nombres.append(v)
        else:
            textes.append([c.row, str(v)])
    fige = {"textes": textes, "lignes_nombres": _plages(rangs_nombres),
            "nombres": _serie(nombres), "types": types}
    fige["~styles" if dependant else "styles"] = styles
    return fige


def _classeur(chemin, graphiques, dependant=False):
    """
    dependant : la mise en forme est celle qu'ecrit pandas (en-tetes), qui
    change avec sa version — elle ne se compare que sur le socle.
    """
    wb = openpyxl.load_workbook(chemin)
    feuilles = []
    for ws in wb.worksheets:
        colonnes = {}
        for ligne in ws.iter_rows():
            for c in ligne:
                if c.value is None and _style(c) == [
                        "General", False, 11.0, None, None, None, None]:
                    continue
                colonnes.setdefault(c.column_letter, []).append(c)
        feuilles.append({
            "nom": ws.title,
            "dimensions": ws.dimensions,
            "figees": ws.freeze_panes,
            "filtre": ws.auto_filter.ref,
            "fusions": sorted(str(r) for r in ws.merged_cells.ranges),
            "largeurs": {k: d.width for k, d in
                         sorted(ws.column_dimensions.items()) if d.customWidth},
            "conditionnelles": [[str(cf.sqref), [r.type for r in cf.rules]]
                                for cf in ws.conditional_formatting],
            "validations": len(ws.data_validations.dataValidation),
            "colonnes": {k: _colonne(v, dependant)
                         for k, v in sorted(colonnes.items(),
                                            key=lambda kv: (len(kv[0]), kv[0]))},
            "graphiques": (graphiques or {}).get(ws.title),
        })
    return {"feuilles": feuilles}


# ---------------------------------------------------------------------------
# Les montages
# ---------------------------------------------------------------------------

def _hydrogramme(t, pic, t_pic=6.0, forme=2.5):
    t = np.maximum(np.asarray(t, dtype=float), 1e-3)
    return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))


TEMPS = np.linspace(0.01, 36, 400)
T12 = np.linspace(0.01, 48, 241)


def _noms(n, apports=None, sections=None):
    return (apports or [f"A{k + 1}" for k in range(n)],
            sections or [f"S{k + 1}" for k in range(n)])


def _cibles(classe, apports, sections, temps, formes, facteurs, **modele):
    """Cibles obtenues en faisant tourner le modele avec des facteurs connus."""
    m = classe(apports, sections, temps, [f.copy() for f in formes], **modele)
    for a, f in zip(apports, facteurs):
        m.appliquer_facteur(a, f)
    return [m.lire_section(s) for s in sections]


def _calage(n=4, apports=None, sections=None, temps=TEMPS, formes=None,
            facteurs=None, classe=cg.ModeleFictif, config=None, modele=None,
            **options):
    apports, sections = _noms(n, apports, sections)
    formes = formes or [_hydrogramme(temps, 10.0) for _ in range(n)]
    facteurs = facteurs or [4.5, 3.4, 3.6, 3.5][:n]
    modele = modele or {}
    cibles = _cibles(classe, apports, sections, temps, formes, facteurs,
                     **modele)
    return {"modele": classe(apports, sections, temps,
                             [f.copy() for f in formes], **modele),
            "apports": apports, "sections": sections, "cibles": cibles,
            "config": config or cg.Configuration(nb_max_essais=8), **options}


def _profil(longueur, avec_eau=True, hors_modele=(0, 0), trous=()):
    """
    Profil en long synthetique : pente, seuil, ligne d'eau. hors_modele :
    nombre de points SANS fond en tete et en queue (axe qui deborde du
    maillage) ; trous : plages interieures sans fond.
    """
    pk = np.linspace(0.0, longueur, 121)
    z = 320.0 - 0.0012 * pk + 1.6 * np.exp(-((pk - 0.52 * longueur)
                                              / (0.04 * longueur)) ** 2)
    colonnes = {"pk_m": pk[::-1].copy(), "z_fond": z[::-1].copy()}
    if avec_eau:
        colonnes["z_eau_max"] = (z + 2.6 + 1.1 * np.exp(
            -((pk - 0.36 * longueur) / (0.1 * longueur)) ** 2))[::-1].copy()
    profil = pd.DataFrame(colonnes)      # dans le desordre : trie par la figure
    debut, fin = hors_modele
    masque = np.zeros(len(pk), dtype=bool)
    masque[:debut] = True
    if fin:
        masque[-fin:] = True
    for a, b in trous:
        masque[a:b] = True
    masque = masque[::-1]
    profil.loc[masque, [c for c in profil.columns if c != "pk_m"]] = np.nan
    return profil


def _pk(n, longueur, decale=0.0):
    return list(np.linspace(0.08 * longueur, 0.92 * longueur, n) - decale)


class _Remous(cg.ModeleFictif):
    """Une section perd une part de son debit des qu'un apport aval agit."""
    remous = 0.06

    def lire_section(self, nom_section):
        t, q = super().lire_section(nom_section)
        rang = self.sections.index(nom_section)
        if any(self.facteurs[a] for a in self.apports[rang + 1:]):
            q = q * (1.0 - self.remous)
        return t, q


class _BasesHeterogenes(cg.ModeleFictif):
    """
    Chaque apport porte SA base de temps dans le fichier unsteady : le cas du
    calage de 46 h qui a perdu son classeur et sa note (voir calage.py).
    """
    longueurs = (400, 330, 260, 390)

    def forme_apport(self, nom_apport):
        k = self.apports.index(nom_apport)
        n = self.longueurs[k % len(self.longueurs)]
        return self.temps[:n], self.formes[nom_apport][:n]


class _UnsteadyPlusLong(cg.ModeleFictif):
    """
    Le fichier unsteady couvre bien plus que la fenetre simulee, et le PREMIER
    apport y porte, au-dela, une seconde crue plus forte que celle qui a ete
    calee : le maximum de l'hydrogramme retenu tombe HORS de la fenetre jugee.
    Pointe, volume et serie livres ne doivent porter que sur la fenetre.
    """

    def forme_apport(self, nom_apport):
        t, q = super().forme_apport(nom_apport)
        if nom_apport != self.apports[0]:
            return t, q
        pas = float(t[1] - t[0])
        suite = t[-1] + pas * np.arange(1, 134)
        crue = q[-1] + 1.6 * float(np.max(q)) * np.exp(
            -0.5 * ((suite - 44.0) / 1.5) ** 2)
        return np.concatenate([t, suite]), np.concatenate([q, crue])


class _Reprise(cg.ModeleFictif):
    """preparer() laisse en place les apports amont deja cales."""
    gardes = ("A1", "A2")

    def preparer(self):
        gardes = {a: self.facteurs[a] for a in self.gardes}
        super().preparer()
        self.facteurs.update(gardes)


def _reprise(prefixe=""):
    base = _calage(4, classe=_Reprise, modele={"retard_h": 0.0})
    m = base["modele"]
    m.appliquer_facteur("A1", 4.5)
    m.appliquer_facteur("A2", 3.4)
    return {**base, "apports": base["apports"][2:],
            "sections": base["sections"][2:], "cibles": base["cibles"][2:],
            "config": cg.Configuration(nb_max_essais=8, prefixe_etape=prefixe),
            "etape_reference": "sans A3 et aval",
            "livrables": {"profil": _profil(2400.0), "pk_sections": _pk(2, 2400),
                          "pk_apports": _pk(2, 2400, 90.0)}}


_TK = np.round(np.arange(0.0, 26.0 + 1e-9, 0.1), 6)


def _retard():
    """La cible decalee commence avant la simulation : l'axe est retarde."""
    m = cg.ModeleFictif(["K1"], ["SK1"], _TK, [np.zeros_like(_TK)],
                        debit_base=_hydrogramme(_TK, 1.7, t_pic=2.0))
    return {"modele": m, "apports": ["K1"], "sections": ["SK1"],
            "cibles": [(_TK, _hydrogramme(_TK, 3.4, t_pic=4.5))],
            "config": cg.Configuration(nb_max_essais=6), "suivi": True,
            "livrables": {"profil": _profil(900.0), "pk_sections": [450.0],
                          "pk_apports": [380.0]}}


_T6 = np.linspace(0.0, 40.0, 401)


def _derive_axe():
    """Decalages differents d'une section a l'autre : reserve d'ensemble."""
    noms, secs = ["A1", "A2", "A3", "A4"], ["S1", "S2", "S3", "S4"]
    formes = [np.exp(-0.5 * ((_T6 - c) / s) ** 2)
              for c, s in ((3.0, 1.0), (14.0, 2.5), (15.0, 2.5), (16.0, 2.5))]
    m = cg.ModeleFictif(noms, secs, _T6, formes, retard_h=0.0)
    m.facteurs = dict(zip(noms, (30.0, 45.0, 10.0, 10.0)))
    cibles = [(_T6, m.lire_section(s)[1].copy()) for s in secs]
    m.preparer()
    return {"modele": m, "apports": noms, "sections": secs, "cibles": cibles,
            "config": cg.Configuration(nb_max_essais=4), "suivi": True}


def _peu_identifiable():
    """L'apport ne pese presque rien devant le debit qui transite deja."""
    base = _hydrogramme(TEMPS, 400.0, t_pic=7.0)
    return _calage(2, modele={"debit_base": base, "retard_h": 0.0},
                   facteurs=[0.8, 6.0], suivi=True)


def _douze():
    apports, sections = _noms(12)
    formes = [_hydrogramme(T12, 10.0, t_pic=4 + 0.5 * k) for k in range(12)]
    return _calage(12, temps=T12, formes=formes,
                   facteurs=[2.0 + 0.3 * k for k in range(12)],
                   modele={"retard_h": 0.0}, suivi=True,
                   livrables={"profil": _profil(2500.0),
                              "pk_sections": _pk(12, 2500)})


def _accents():
    apports = ["Gave d'Ossau à Gère", "Perimeter 1: BCLine 3",
               "Néez/aval — rive gauche"]
    sections = ["Pont de l'Égalité", "S2 [amont]*?", "Confluence Lagoin é"]
    return _calage(3, apports=apports, sections=sections, suivi=True,
                   livrables={"profil": _profil(6000.0),
                              "pk_sections": _pk(3, 6000),
                              "pk_apports": _pk(3, 6000, 250.0)})


def _base_hors_evenement():
    """
    Un debit de base qui culmine APRES la crue calee, plus haut qu'elle : le
    pic de toute la serie n'est pas celui de la fenetre jugee.
    """
    base = 70.0 * np.exp(-0.5 * ((TEMPS - 31.0) / 1.5) ** 2)
    return _calage(2, modele={"debit_base": base, "retard_h": 0.0},
                   livrables={"profil": _profil(2000.0),
                              "pk_sections": _pk(2, 2000),
                              "pk_apports": _pk(2, 2000, 60.0)})


def _fenetres_au_bord(resultat):
    """
    Fenetres posees a la main au ras de la fin des series : DEUX pas au-dela
    pour le premier apport (queue trop courte pour etre signalee), TROIS pour
    le second (signalee). La limite exacte de l'avertissement.
    """
    for a, reste in zip(resultat.apports, (2, 3)):
        a.fenetre_principale = (1.0, float(TEMPS[-1 - reste]))


def _incoherent(resultat):
    resultat.series_finales.pop()


def _panne_apports_retenus():
    return mock.patch.object(liv, "figure_apports_retenus",
                             side_effect=RuntimeError("panne simulée"))


AVEC_PROFIL_KM = {"profil": _profil(8000.0), "pk_sections": _pk(4, 8000),
                  "pk_apports": _pk(4, 8000, 300.0)}

SCENARIOS = {
    "conforme_quatre_apports_suivi_profil_km": lambda: _calage(
        4, suivi=True, livrables=AVEC_PROFIL_KM),
    "conforme_un_apport_sans_profil": lambda: _calage(1, suivi=True),
    "douze_apports_profil_en_metres_sans_pk_apports": _douze,
    "plusieurs_essais_laminage": lambda: _calage(
        3, modele={"laminage": 0.05}, suivi=True,
        livrables={"profil": _profil(8000.0), "pk_sections": _pk(3, 8000),
                   "pk_apports": _pk(3, 8000, 300.0)}),
    "non_conforme_remous": lambda: _calage(
        3, classe=_Remous, modele={"retard_h": 0.0}, suivi=True,
        livrables={"profil": _profil(8000.0), "pk_sections": _pk(3, 8000),
                   "pk_apports": _pk(3, 8000, 300.0)}),
    "apport_echoue": lambda: _calage(
        2, modele={"laminage": 0.3}, config=cg.Configuration(nb_max_essais=2),
        suivi=True),
    "apport_peu_identifiable": _peu_identifiable,
    "reprise_au_troisieme_apport": _reprise,
    "reprise_sous_prefixe": lambda: _reprise("Q100"),
    "prefixe_de_scenario": lambda: _calage(
        2, config=cg.Configuration(nb_max_essais=8, prefixe_etape="Q100")),
    "retard_de_l_axe": _retard,
    "reserve_d_ensemble_derive_de_l_axe": _derive_axe,
    "sans_fenetre_jugee": lambda: _calage(
        2, config=cg.Configuration(nb_max_essais=8, fenetre_active=False)),
    "fenetre_imposee": lambda: _calage(
        2, config=cg.Configuration(nb_max_essais=8, fenetre_t0_h=2.0,
                                   fenetre_tf_h=18.0)),
    "noms_accentues_et_illisibles": _accents,
    "bases_de_temps_heterogenes": lambda: _calage(
        4, classe=_BasesHeterogenes, livrables=AVEC_PROFIL_KM),
    "bilan_de_masse_absent": lambda: _calage(
        2, modele={"bilan_masse_pct": float("nan")}, suivi=True),
    "profil_sans_ligne_d_eau_debordant_le_modele": lambda: _calage(
        2, livrables={"profil": _profil(2000.0, avec_eau=False,
                                        hors_modele=(9, 14), trous=((50, 58),)),
                      "pk_sections": _pk(2, 2000),
                      "pk_apports": _pk(2, 2000, 60.0)}),
    "profil_entierement_hors_modele": lambda: _calage(
        2, livrables={"profil": _profil(2000.0, hors_modele=(121, 0)),
                      "pk_sections": _pk(2, 2000),
                      "pk_apports": _pk(2, 2000, 60.0)}),
    "profil_sans_pk_des_sections": lambda: _calage(
        2, livrables={"profil": _profil(2000.0), "pk_sections": None}),
    "profil_vide": lambda: _calage(
        2, livrables={"profil": _profil(2000.0).iloc[:0],
                      "pk_sections": _pk(2, 2000)}),
    "figure_des_apports_en_panne": lambda: _calage(
        2, pannes=_panne_apports_retenus),
    "resultat_incoherent": lambda: _calage(2, alterer=_incoherent),
    "debit_de_base_hors_evenement": _base_hors_evenement,
    "queue_de_deux_et_trois_pas": lambda: _calage(
        2, formes=[_hydrogramme(TEMPS, 10.0, t_pic=20.0) for _ in range(2)],
        modele={"retard_h": 0.0}, alterer=_fenetres_au_bord),
    "crue_de_l_unsteady_hors_fenetre": lambda: _calage(
        2, classe=_UnsteadyPlusLong, modele={"retard_h": 0.0}),
}


# --- appels directs de figure_profil_en_long --------------------------------

_P = _profil(5000.0)
PROFILS = {
    "complet_avec_debits": lambda: dict(
        profil=_P, sections_pk=_pk(4, 5000), noms_sections=list("ABCD"),
        apports_pk=_pk(4, 5000, 200.0), noms_apports=["a1", "a2", "a3", "a4"],
        pics_cible=[10.0, 25.0, 31.0, 40.0],
        pics_calcule=[10.2, 23.0, 31.1, 44.0], titre="Profil — Q100"),
    "sans_debits_ni_noms": lambda: dict(
        profil=_P, sections_pk=_pk(3, 5000), apports_pk=_pk(3, 5000, 100.0)),
    "sans_apports": lambda: dict(
        profil=_P, sections_pk=_pk(3, 5000), noms_sections=["x", "y", "z"],
        pics_cible=[1.0, 2.0, 3.0], pics_calcule=[1.0, 2.2, 2.7]),
    "une_seule_section_en_metres": lambda: dict(
        profil=_profil(1200.0), sections_pk=[600.0], noms_sections=["S"],
        apports_pk=[520.0], noms_apports=["A"], pics_cible=[5.0],
        pics_calcule=[5.6]),
    "un_seul_pic_fourni": lambda: dict(
        profil=_P, sections_pk=_pk(2, 5000), pics_cible=[1.0, 2.0]),
    "sans_eau_troue_hors_modele": lambda: dict(
        profil=_profil(5000.0, avec_eau=False, hors_modele=(5, 7),
                       trous=((40, 52),)),
        sections_pk=_pk(3, 5000), noms_sections=["u", "v", "w"],
        apports_pk=_pk(3, 5000, 150.0), noms_apports=["p", "q", "r"],
        pics_cible=[3.0, 4.0, 5.0], pics_calcule=[3.0, 3.0, 6.0]),
    "eau_trouee_apport_dans_le_trou": lambda: dict(
        profil=_profil(5000.0, trous=((40, 52),)), sections_pk=_pk(2, 5000),
        apports_pk=[1900.0, 2000.0], noms_apports=["t1", "t2"]),
    "noms_de_sections_sans_pk_d_apports": lambda: dict(
        profil=_P, sections_pk=_pk(2, 5000), noms_sections=["m", "n"],
        noms_apports=["ignore"]),
}


# --- appels directs de _onglet_iterations ----------------------------------

_G = np.linspace(0.0, 30.0, 61)


def _bloc(essai, d=0.0, calcule=None, decalee=None, apport=None, **mesures):
    q = _hydrogramme(_G, 12.0)
    return {"essai": essai, "volume": mesures.get("volume"),
            "pic": mesures.get("pic"), "forme": mesures.get("forme"),
            "decalage": mesures.get("decalage"), "decalage_correction": d,
            "temps": _G, "cible": q,
            "calcule": q * (0.8 + 0.05 * essai) if calcule is None else calcule,
            "cible_decalee": (sv._sur_grille(_G - d, _G, q) if decalee is None
                              else decalee),
            "apport": apport}


def _etat(**champs):
    e = sv.EtatApport("Gave d'Aspe", "Pont « neuf »", statut=sv.VALIDE)
    for cle, valeur in champs.items():
        setattr(e, cle, valeur)
    return e


ONGLETS = {
    "aucun_bloc": lambda: _etat(),
    "residuel_seul": lambda: _etat(
        statut=sv.EN_COURS, residuel_detail=_bloc(0, d=0.75)),
    "essais_sans_residuel_avec_motif": lambda: _etat(
        statut=sv.ECHOUE, motif="concordance non atteinte",
        essais_detail=[
            _bloc(1, d=-0.5, apport=_hydrogramme(_G, 3.0), volume=0.91,
                  pic=0.88, forme=0.97, decalage=-0.4),
            _bloc(2, d=-0.5, apport=_hydrogramme(_G, 3.5), volume=0.97,
                  pic=0.95, forme=0.99, decalage=-0.3)]),
    "residuel_et_essais_grilles_inegales": lambda: _etat(
        residuel_detail=_bloc(0, d=1.25),
        essais_detail=[
            _bloc(1, d=1.25, apport=_hydrogramme(_G, 2.0)[:40], volume=0.95,
                  pic=float("nan"), forme=None, decalage=1.2),
            _bloc(2, d=1.5, calcule=_hydrogramme(_G, 11.0)[:50],
                  decalee=_hydrogramme(_G, 12.0)[:30],
                  apport=_hydrogramme(_G, 2.4), volume=1.001, pic=0.999,
                  forme=0.995, decalage=1.4)]),
    "trous_dans_les_series": lambda: _etat(
        residuel_detail=_bloc(0, d=2.0, calcule=np.where(
            _G > 26.0, np.nan, _hydrogramme(_G, 9.0))),
        essais_detail=[_bloc(1, d=2.0, apport=np.where(
            _G < 1.0, np.nan, _hydrogramme(_G, 3.0)), volume=float("nan"),
            pic=1.02, forme=0.98, decalage=float("nan"))]),
}


# ---------------------------------------------------------------------------
# Jouer un cas
# ---------------------------------------------------------------------------

class _Horloge:
    """time vu par calage.py : 0, 1, 2... Les durees deviennent fixes."""

    def __init__(self):
        self._t = 0.0

    def time(self):
        self._t += 1.0
        return self._t

    def sleep(self, secondes):
        return None


def _neutraliseur(dossier):
    variantes = sorted({str(dossier), str(Path(dossier).resolve())},
                       key=len, reverse=True)

    def neutre(texte):
        # Separateur ramene a « / », y compris double dans un repr :
        # meme reference sous Windows et sous Linux.
        texte = texte.replace("\\\\", "/").replace("\\", "/")
        for v in variantes:
            texte = texte.replace(v.replace("\\", "/"), "<DOSSIER>")
        return texte
    return neutre


def _contenu_dossier(dossier, neutre, graphiques):
    contenu = {}
    for p in sorted(Path(dossier).rglob("*")):
        if not p.is_file():
            continue
        nom = neutre(str(p))
        if p.suffix == ".xlsx":
            contenu[nom] = {"classeur": _classeur(
                p, graphiques.get(p.name),
                dependant=(p.name == "tableaux_calage.xlsx"))}
        elif p.suffix == ".md":
            contenu[nom] = {"texte": p.read_text(encoding="utf-8")}
        else:
            contenu[nom] = {"non_vide": p.stat().st_size > 0}
    return contenu


def _exception(e, neutre):
    return {"exception": type(e).__name__, "message": neutre(str(e))}


def _jouer(nom, dossier):
    """Un calage, puis ses livrables : la trace de tout ce qui en sort."""
    montage = dict(SCENARIOS[nom]())
    dossier = Path(dossier)
    neutre = _neutraliseur(dossier)
    trace = {}
    suivi = (sv.Suivi(dossier / "suivi", montage["apports"],
                      montage["sections"]) if montage.get("suivi") else None)
    graphiques = {}
    arguments = {"config": montage["config"], "journal": lambda ligne: None}
    # LES FIGURES DU SUIVI NE SONT PAS TRACEES : elles ne sont pas de cette
    # chaine, portent l'heure, et coutaient les deux tiers du temps du test.
    # Le classeur d'iterations, lui, est ecrit par le vrai Suivi.
    sans_figures = [mock.patch.object(sv.Suivi, f, lambda *a, **k: None)
                    for f in ("_figure_avancement", "_figure_section",
                              "_figure_convergence")]
    if "etape_reference" in montage:
        arguments["etape_reference"] = montage["etape_reference"]
    with mock.patch.object(cg, "time", _Horloge()), \
            _capter_graphiques(graphiques), contextlib.ExitStack() as pile:
        for doublure in sans_figures:
            pile.enter_context(doublure)
        resultat = cg.caler(montage["modele"], montage["apports"],
                            montage["sections"], montage["cibles"],
                            suivi=suivi, **arguments)
    trace["calage"] = {"conforme": resultat.conforme, "motif": resultat.motif,
                       "essais": [a.essais for a in resultat.apports],
                       "retard_axe_h": _f(resultat.retard_axe_h)}
    if suivi is not None:
        trace["iterations"] = _classeur(dossier / "suivi" / "iterations.xlsx",
                                        graphiques.get("iterations.xlsx"))
    if "alterer" in montage:
        montage["alterer"](resultat)

    figures, graphiques, ecritures, sortie = [], {}, [], io.StringIO()
    pannes = montage.get("pannes", contextlib.nullcontext)()
    # LA NOTE CITE LA VERSION DE ras-commander INSTALLEE : elle differe d'un
    # poste a l'autre (et le job « noyau » n'en a pas). Fixee ici, pour que la
    # reference ne depende pas du poste ; test_defauts_mineurs.py verifie que
    # la note porte bien la version reelle.
    version_fixe = mock.patch.object(liv, "_version_ras_commander",
                                     lambda: "0.0.filet")
    with _capter_figures(figures, neutre, ecritures), \
            _capter_graphiques(graphiques, ecritures, neutre), \
            _capter_textes(ecritures, neutre), version_fixe, \
            pannes, contextlib.redirect_stdout(sortie):
        try:
            rendu = cg.produire_livrables_finaux(
                resultat, montage["modele"], dossier / "livrables",
                **montage.get("livrables", {}))
        except Exception as e:                              # noqa: BLE001
            trace["exception"] = _exception(e, neutre)
        else:
            trace["rendu"] = {"fichiers": [neutre(str(f))
                                           for f in rendu["fichiers"]],
                              "conforme": rendu["conforme"]}
    plt.close("all")
    trace["sortie"] = sortie.getvalue()
    trace["ecritures"] = ecritures
    trace["figures"] = figures
    trace["dossier"] = _contenu_dossier(dossier / "livrables", neutre,
                                        graphiques)
    return trace


def _jouer_profil(nom, dossier):
    neutre = _neutraliseur(dossier)
    figures, trace = [], {}
    with _capter_figures(figures, neutre):
        try:
            rendu = liv.figure_profil_en_long(chemin=Path(dossier) / "p.png",
                                              **PROFILS[nom]())
        except Exception as e:                              # noqa: BLE001
            trace["exception"] = _exception(e, neutre)
        else:
            trace["rendu"] = neutre(rendu)
    plt.close("all")
    trace["figures"] = figures
    trace["dossier"] = _contenu_dossier(dossier, neutre, {})
    return trace


def _jouer_onglet(nom, dossier):
    graphiques = {}
    chemin = Path(dossier) / "iterations.xlsx"
    with _capter_graphiques(graphiques):
        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        sv._onglet_iterations(wb.create_sheet("Onglet"), ONGLETS[nom]())
        wb.save(chemin)
    return {"classeur": _classeur(chemin, graphiques.get("iterations.xlsx"))}


def _tous_les_cas():
    return ([("calage", n) for n in SCENARIOS]
            + [("profil", n) for n in PROFILS]
            + [("onglet", n) for n in ONGLETS])


JOUEURS = {"calage": _jouer, "profil": _jouer_profil, "onglet": _jouer_onglet}


def _cle(famille, nom):
    return f"{famille}/{nom}"


def _rejouer(famille, nom, dossier):
    """La trace sous sa forme JSON : celle que la reference conserve."""
    with warnings.catch_warnings():
        # Les avertissements de numpy et matplotlib (series toutes NaN,
        # mise en page) dependent de leur version : ils ne sont pas figes.
        warnings.simplefilter("ignore")
        trace = JOUEURS[famille](nom, dossier)
    return json.loads(json.dumps(trace, ensure_ascii=False))


# ---------------------------------------------------------------------------
# La reference, et le repli hors socle
# ---------------------------------------------------------------------------

def _simd():
    """
    Les jeux d'instructions vectorielles que numpy EMPLOIE sur ce processeur.

    Ils font partie du socle (11/11/2026) : numpy choisit ses noyaux de calcul
    selon le processeur, et une somme faite avec ou sans AVX-512 differe d'un
    dernier bit. A versions egales, deux machines ne rendent donc PAS les
    memes octets ; sans cette ligne, le filet « au bit pres » echouait a tort
    sur un processeur different de celui qui a fige la reference.
    """
    try:
        from numpy._core._multiarray_umath import (__cpu_dispatch__ as cibles,
                                                   __cpu_features__ as vus)
    except ImportError:
        return "inconnu"
    return "+".join(c for c in cibles if vus.get(c)) or "base"


def _socle():
    return {"python": platform.python_version(), "numpy": np.__version__,
            "matplotlib": matplotlib.__version__,
            "openpyxl": openpyxl.__version__, "pandas": pd.__version__,
            "systeme": platform.system(), "machine": platform.machine(),
            "simd": _simd()}


def _meme_socle(produit_par):
    ici = _socle()
    return all(produit_par.get(c) == ici[c]
               for c in ("numpy", "matplotlib", "openpyxl", "pandas",
                         "systeme", "machine", "simd"))


def _types_sans_int_ni_float(plages):
    """Les plages de types d'une colonne, « int » et « float » confondus."""
    fusion = []
    for debut, fin, nom in plages:
        nom = "nombre" if nom in ("int", "float") else nom
        if fusion and fusion[-1][2] == nom and fusion[-1][1] == debut - 1:
            fusion[-1][1] = fin
        else:
            fusion.append([debut, fin, nom])
    return fusion


def _transportable(fige):
    """
    Sans les empreintes, ni ce qui depend de la version d'une bibliotheque,
    NI CE QU'UN DERNIER BIT FAIT BASCULER (11/11/2026).

    numpy choisit ses noyaux de calcul selon le PROCESSEUR : avec ou sans
    AVX-512, une somme differe d'un dernier bit. La tolerance de 1e-9 absorbe
    l'ecart sur les nombres, pas ses deux effets DISCRETS, constates sur les
    machines de la CI (trois cas rouges sur un processeur sans AVX-512, verts
    sur un autre, a code identique) :
      - le TYPE d'une cellule : openpyxl relit « 3 » en entier et
        « 2.9999999999999996 » en flottant. Hors socle, int et float sont
        donc un seul type, « nombre » ;
      - le NOMBRE DE SOMMETS d'une zone coloree (fill_between sous un
        seuil) : un point de plus ou de moins quand la comparaison bascule.
        Hors socle, les sommets des polygones ne sont pas compares — leur
        legende, leur couleur et leur ordre de trace le restent.
    Se rejoue ici en retirant AVX-512 a numpy :
        NPY_DISABLE_CPU_FEATURES="X86_V4 AVX512_ICL AVX512_SPR"
    """
    if isinstance(fige, dict):
        polygones = fige.get("genre") == "polygones"
        sortie = {}
        for c, v in fige.items():
            if c.startswith("~") or c == "sha":
                continue
            if polygones and c in ("x", "y"):
                continue
            if c == "types" and isinstance(v, list):
                v = _types_sans_int_ni_float(v)
            sortie[c] = _transportable(v)
        return sortie
    if isinstance(fige, list):
        return [_transportable(v) for v in fige]
    return fige


def _nombre(texte):
    if isinstance(texte, str) and texte.startswith("f:"):
        return float.fromhex(texte[2:])
    return None


def _proches(obtenu, attendu):
    """
    L'egalite du repli : les grandeurs calculees a TOLERANCE_HORS_SOCLE pres
    en relatif (1e-12 en absolu pour ce qui vaut zero), tout le reste —
    textes, structure, styles, types — exactement.
    """
    if isinstance(attendu, dict):
        return (isinstance(obtenu, dict) and list(obtenu) == list(attendu)
                and all(_proches(obtenu[c], attendu[c]) for c in attendu))
    if isinstance(attendu, list):
        return (isinstance(obtenu, list) and len(obtenu) == len(attendu)
                and all(_proches(o, a) for o, a in zip(obtenu, attendu)))
    a, o = _nombre(attendu), _nombre(obtenu)
    if a is None or o is None:
        return obtenu == attendu
    if a == o or (a != a and o != o):
        return True
    return abs(a - o) <= TOLERANCE_HORS_SOCLE * max(abs(a), abs(o)) + 1e-12


def _conforme(obtenu, attendu, produit_par):
    if _meme_socle(produit_par):
        return obtenu == attendu
    warnings.warn(
        f"reference produite sous {produit_par}, ici {_socle()} : les "
        f"grandeurs calculees sont comparees a {TOLERANCE_HORS_SOCLE:g} pres "
        f"en relatif, sans les empreintes ni ce qui depend de la version "
        f"d'une bibliotheque. L'identite AU BIT PRES n'est PAS verifiee — "
        f"refiger la reference sur le code d'origine avant de remanier la "
        f"chaine des livrables sur ce poste.")
    return _proches(_transportable(obtenu), _transportable(attendu))


def _premier_ecart(obtenu, attendu, chemin="trace"):
    """Le chemin de la premiere difference, pour un message lisible."""
    if isinstance(attendu, dict) and isinstance(obtenu, dict):
        for c in list(attendu) + [c for c in obtenu if c not in attendu]:
            if c not in obtenu or c not in attendu:
                return f"{chemin}.{c} : present d'un seul cote"
            if obtenu[c] != attendu[c]:
                return _premier_ecart(obtenu[c], attendu[c], f"{chemin}.{c}")
    if isinstance(attendu, list) and isinstance(obtenu, list):
        for k, (o, a) in enumerate(zip(obtenu, attendu)):
            if o != a:
                return _premier_ecart(o, a, f"{chemin}[{k}]")
        if len(obtenu) != len(attendu):
            return f"{chemin} : {len(obtenu)} element(s) au lieu de {len(attendu)}"
    return (f"{chemin} :\n   attendu : {json.dumps(attendu, ensure_ascii=False)[:600]}"
            f"\n   obtenu  : {json.dumps(obtenu, ensure_ascii=False)[:600]}")


def _dumps(objet, retrait=" "):
    """JSON indente, mais ce qui tient sur une ligne y reste : le diff se lit."""
    compact = json.dumps(objet, ensure_ascii=False)
    if len(compact) <= 100 or not isinstance(objet, (dict, list)) or not objet:
        return compact
    suivant = retrait + " "
    if isinstance(objet, dict):
        corps = [f"{suivant}{json.dumps(c, ensure_ascii=False)}: "
                 f"{_dumps(v, suivant)}" for c, v in objet.items()]
        return "{\n" + ",\n".join(corps) + f"\n{retrait}}}"
    corps = [f"{suivant}{_dumps(v, suivant)}" for v in objet]
    return "[\n" + ",\n".join(corps) + f"\n{retrait}]"


def _ecrire_reference(dossier):
    """UN CAS PAR BLOC, indente : le diff d'une reference refigee se relit."""
    blocs = []
    for famille, nom in _tous_les_cas():
        sous = Path(dossier) / famille / nom
        sous.mkdir(parents=True)
        corps = _dumps(_rejouer(famille, nom, sous), "  ")
        blocs.append(f"  {json.dumps(_cle(famille, nom))}: {corps}")
    a_propos = (
        "Caracterisation de la chaine des livrables (produire_livrables_"
        "finaux, figure_profil_en_long, _onglet_iterations). NE PAS MODIFIER "
        "A LA MAIN : « python src/test_livrables_chaine.py --figer » la "
        "reecrit, quand le changement de comportement est VOULU.")
    REFERENCE.write_text(
        "{\n"
        f' "_a_propos": {json.dumps(a_propos, ensure_ascii=False)},\n'
        f' "_produit_par": {json.dumps(_socle())},\n'
        ' "cas": {\n' + ",\n".join(blocs) + "\n }\n}\n",
        encoding="utf-8")


_LUE = {}


def _reference():
    if not _LUE:
        _LUE.update(json.loads(REFERENCE.read_text(encoding="utf-8")))
    return _LUE


# ---------------------------------------------------------------------------
# Les tests
# ---------------------------------------------------------------------------

def test_la_reference_couvre_les_cas_et_eux_seuls():
    assert REFERENCE.is_file(), (
        f"{REFERENCE.name} absent — le creer par "
        f"« python src/test_livrables_chaine.py --figer »")
    assert list(_reference()["cas"]) == [_cle(f, n) for f, n in _tous_les_cas()]


@pytest.mark.parametrize("famille,nom", _tous_les_cas(),
                         ids=[_cle(f, n) for f, n in _tous_les_cas()])
def test_la_chaine_produit_ce_que_la_reference_a_enregistre(famille, nom,
                                                            tmp_path):
    reference = _reference()
    obtenu = _rejouer(famille, nom, tmp_path)
    attendu = reference["cas"][_cle(famille, nom)]
    assert _conforme(obtenu, attendu, reference["_produit_par"]), \
        _premier_ecart(obtenu, attendu)


@pytest.mark.parametrize("famille,nom", [
    ("calage", "plusieurs_essais_laminage"),
    ("calage", "noms_accentues_et_illisibles"),
    ("profil", "complet_avec_debits"),
    ("onglet", "residuel_et_essais_grilles_inegales")])
def test_rejouer_un_cas_rend_la_meme_trace(famille, nom, tmp_path):
    """Sans quoi la reference figerait du hasard, ou un etat qui fuit."""
    (tmp_path / "1").mkdir()
    (tmp_path / "2").mkdir()
    assert (_rejouer(famille, nom, tmp_path / "1")
            == _rejouer(famille, nom, tmp_path / "2"))


def test_les_cas_couvrent_ce_qu_ils_annoncent():
    """Un montage qui ne fait plus ce que son nom dit ne garde plus rien."""
    cas = _reference()["cas"]
    calage = {n: cas[_cle("calage", n)] for n in SCENARIOS}
    assert calage["non_conforme_remous"]["rendu"]["conforme"] is False
    assert calage["conforme_quatre_apports_suivi_profil_km"]["rendu"][
        "conforme"] is True
    assert "aucun diagnostic" in calage["apport_echoue"]["exception"]["message"]
    assert "incoherent" in calage["resultat_incoherent"]["exception"]["message"]
    assert max(calage["plusieurs_essais_laminage"]["calage"]["essais"]) >= 2
    assert calage["retard_de_l_axe"]["calage"]["retard_axe_h"] != _f(0.0)
    assert any("PEU IDENTIFIABLE" in f["texte"].upper()
               for f in calage["apport_peu_identifiable"]["dossier"].values()
               if "texte" in f)
    assert any("Réserves" in f["texte"] for f in calage[
        "reserve_d_ensemble_derive_de_l_axe"]["dossier"].values()
        if "texte" in f)
    messages = [m for c in calage.values()
                for m in c.get("rendu", {}).get("fichiers", [])]
    for attendu in ("AVERTISSEMENT", "profil en long non produit",
                    "apports retenus non produits"):
        assert any(m.startswith(attendu) for m in messages), attendu
    assert not any(m.startswith("AVERTISSEMENT") for m in calage[
        "sans_fenetre_jugee"]["rendu"]["fichiers"])
    assert len(calage["douze_apports_profil_en_metres_sans_pk_apports"][
        "calage"]["essais"]) == 12


# --- le repli hors socle, eprouve ici --------------------------------------

def _un_cran_plus_loin(fige):
    """Chaque grandeur calculee poussee au flottant voisin, comme un autre numpy."""
    if isinstance(fige, dict):
        return {c: _un_cran_plus_loin(v) for c, v in fige.items()}
    if isinstance(fige, list):
        return [_un_cran_plus_loin(v) for v in fige]
    a = _nombre(fige)
    if a is None:
        return fige
    return _f(np.nextafter(a, np.inf))


def _ailleurs(obtenu, attendu, reference):
    """_conforme, comme si la reference venait d'un autre numpy."""
    with mock.patch.object(np, "__version__", "0.0.autre"):
        with pytest.warns(UserWarning, match="AU BIT PRES n'est PAS"):
            return _conforme(obtenu, attendu, reference["_produit_par"])


def _chercher(fige, predicat, chemin=()):
    """Le premier chemin d'une valeur qui satisfait predicat."""
    if predicat(fige):
        return chemin
    if isinstance(fige, dict):
        enfants = fige.items()
    elif isinstance(fige, list):
        enfants = enumerate(fige)
    else:
        return None
    for c, v in enfants:
        trouve = _chercher(v, predicat, chemin + (c,))
        if trouve is not None:
            return trouve
    return None


def _modifier(fige, chemin, fonction):
    copie = json.loads(json.dumps(fige))
    parent = copie
    for c in chemin[:-1]:
        parent = parent[c]
    parent[chemin[-1]] = fonction(parent[chemin[-1]])
    return copie


def test_le_repli_hors_socle_tolere_le_dernier_bit_et_rien_de_plus(tmp_path):
    """
    Joue sur un socle SIMULE (np.__version__ force) : un repli qu'on ne joue
    que la ou personne ne regarde peut tout accepter sans que rien le dise.
    """
    reference = _reference()
    for famille, nom in (("calage", "plusieurs_essais_laminage"),
                         ("profil", "complet_avec_debits"),
                         ("onglet", "residuel_et_essais_grilles_inegales")):
        attendu = reference["cas"][_cle(famille, nom)]
        sous = tmp_path / nom
        sous.mkdir()
        obtenu = _rejouer(famille, nom, sous)

        # Le code sain passe, meme pousse d'un flottant partout, et meme avec
        # des empreintes et des bornes calculees qui ne sont plus les memes.
        assert _ailleurs(obtenu, attendu, reference)
        assert _ailleurs(_un_cran_plus_loin(obtenu), attendu, reference)
        bouge = _chercher(obtenu, lambda v: isinstance(v, dict) and "sha" in v)
        assert _ailleurs(_modifier(obtenu, bouge + ("sha",), lambda s: "0" * 24),
                         attendu, reference)

        # Sur le socle qui a fige, un seul bit suffit a echouer. (Le socle
        # d'ICI fait office de socle de reference : ce test doit tenir aussi
        # sur un poste ou la reference n'a pas ete figee.)
        assert not _conforme(_un_cran_plus_loin(obtenu), obtenu, _socle())

        # Hors socle, tout ecart qui compte est refuse : un millionieme sur
        # une grandeur calculee...
        nombre = _chercher(obtenu, lambda v: _nombre(v) not in (None, 0.0))
        fausse = _modifier(obtenu, nombre,
                           lambda v: _f(_nombre(v) * (1 + 1e-6)))
        assert not _ailleurs(fausse, attendu, reference), nombre
        # ... un caractere dans un texte...
        texte = _chercher(obtenu, lambda v: isinstance(v, str) and len(v) > 3
                          and _nombre(v) is None and "<DOSSIER>" not in v)
        fausse = _modifier(obtenu, texte, lambda v: v + ".")
        assert not _ailleurs(fausse, attendu, reference), texte
        # ... une valeur de reglage exacte (couleur, taille, type)...
        reglage = _chercher(obtenu, lambda v: isinstance(v, str)
                            and v.startswith("#") and len(v) == 9)
        if reglage is None:
            reglage = _chercher(obtenu, lambda v: v in ("int", "float"))
        fausse = _modifier(obtenu, reglage, lambda v: "#123456ff"
                           if v.startswith("#") else "str")
        assert not _ailleurs(fausse, attendu, reference), reglage
        # ... une valeur de plus dans une serie condensee.
        serie = _chercher(obtenu, lambda v: isinstance(v, dict) and "n" in v
                          and "sha" in v)
        fausse = _modifier(obtenu, serie + ("n",), lambda v: v + 1)
        assert not _ailleurs(fausse, attendu, reference), serie


if __name__ == "__main__":
    if "--figer" in sys.argv:
        import tempfile
        with tempfile.TemporaryDirectory() as provisoire:
            _ecrire_reference(provisoire)
        print(f"REFERENCE REECRITE : {REFERENCE.name} "
              f"({REFERENCE.stat().st_size / 1024:.0f} ko, "
              f"{len(_tous_les_cas())} cas). Relire le diff avant de "
              f"committer : il dit ce que le changement a deplace.")
    else:
        raise SystemExit(pytest.main([__file__, "-q"]))
