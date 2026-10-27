# -*- coding: utf-8 -*-
"""
Le lexique du calage : chaque terme technique des textes d'aide et des
lignes d'etat, defini simplement, avec sa publication quand il en faut une.

Demande du 27/10/2026 (« prendre le meilleur et les plus recentes evolutions
de Rhoe, Hyetos, Plemmyra, Sensi ») : repris de ``06-Rhoe/rhoe/gui/lexique.py``
et de ``02-Hyetos/hyetos/gui/lexique.py``, eux-memes repris de Plemmyra
(« Ne mets pas les liens bleus soulignes », 26/10/2026). Ce n'est pas une
copie commune : les termes sont ceux de Calage. Chaque occurrence d'un terme
devient un lien discret (:func:`lier`, :func:`liens_discrets`) : le survol
montre la definition, le clic ouvre l'aide a l'entree du terme ; l'entree
cite sa publication, que le clic ouvre dans le navigateur.

Regles d'ecriture (base ``ergonomie``, « Lisibilite ») : trois phrases au
plus, de 25 mots au plus chacune. Une adresse n'est ecrite qu'apres
verification : DOI relu sur Crossref, page web repondant 200 (27/10/2026).

Sans Qt : testable sans QGIS (``src/test_lexique.py``).
"""

import html
import re
from dataclasses import dataclass
from functools import lru_cache

#: Prefixe des liens vers une entree du lexique.
PREFIXE = "terme:"
#: Prefixe des ancres des entrees dans l'aide.
ANCRE = "terme_"


@dataclass(frozen=True)
class Terme:
    """
    cle : identifiant, dans le lien (``terme:<cle>``) et l'ancre de l'entree.
    nom : le terme tel que l'entree le titre.
    motif : expression reguliere de ses occurrences dans les textes.
    definition : trois phrases courtes au plus.
    source : la publication ; vide si la definition n'en a pas besoin.
    url : l'adresse verifiee de la publication ; vide sinon.
    """

    cle: str
    nom: str
    motif: str
    definition: str
    source: str = ""
    url: str = ""


# Adresses verifiees le 27/10/2026 (HTTP 200 ; DOI relu sur Crossref).
_HEC_2D = ("USACE HEC, HEC-RAS 2D User's Manual",
           "https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/latest")
_HEC = ("USACE HEC, HEC-RAS User's Manual",
        "https://www.hec.usace.army.mil/confluence/rasdocs/rasum/latest")
_NOTE = "Note méthodologique du calage, § 1.4 et 1.5"

#: Les termes, dans l'ordre de l'aide. L'ordre compte aussi pour :func:`lier` :
#: a une meme position, le premier motif qui convient l'emporte (« hydrogramme
#: cible » avant « hydrogramme »).
TERMES = (
    Terme("hydrogramme_cible", "Hydrogramme cible",
          r"[Hh]ydrogrammes? (?:cibles?|visés?)\b",
          "Hydrogramme que le calage doit retrouver à une section de contrôle. "
          "Il se saisit dans la feuille Cibles de l'Excel, une colonne par section."),
    Terme("hydrogramme", "Hydrogramme", r"[Hh]ydrogrammes?\b",
          "Débit d'un cours d'eau en fonction du temps, en m³/s. Un apport, une "
          "cible et le débit calculé à une section sont des hydrogrammes."),
    Terme("section_controle", "Section de contrôle", r"[Ss]ections? de contrôle",
          "Ligne tracée en travers de l'écoulement, où HEC-RAS calcule le débit qui "
          "la traverse ; HEC-RAS la nomme « Reference Line ». Le calage y compare "
          "ce débit à la cible.", *_HEC_2D),
    Terme("injection", "Injection", r"\b[Ii]njections?\b",
          "Ligne de condition aux limites (« BC Line ») par où un hydrogramme entre "
          "dans la zone 2D. L'apport calé y est posé en « Flow Hydrograph ».",
          *_HEC_2D),
    Terme("debit_pointe", "Débit de pointe", r"[Dd]ébits? de pointe",
          "Débit maximal d'un hydrogramme, en m³/s. Le calage l'exige à 2 % près "
          "par défaut, réglable à l'étape Paramètres."),
    Terme("dt", "Δt, décalage de propagation", r"Δt",
          "Instant du pic calculé moins instant du pic cible, en heures. Il se "
          "mesure une fois, sur le calcul de référence, puis reste figé. La cible "
          "en est décalée avant chaque comparaison.", _NOTE),
    Terme("calcul_reference", "Calcul de référence", r"[Cc]alculs? de référence",
          "Premier calcul du calage, avec tous les apports à zéro. Il mesure le "
          "débit que chaque section reçoit déjà ; le Δt s'y mesure."),
    Terme("plan_reference", "Plan de référence", r"[Pp]lans? de référence",
          "Plan HEC-RAS choisi à l'étape Modèle. Sa géométrie, son Unsteady Flow et "
          "ses réglages servent de base à tous les plans du calage."),
    Terme("plan_etape", "Plan d'étape", r"[Pp]lans? d[’']étape",
          "Plan HEC-RAS que le calage crée à chaque étape : un sans apport, puis un "
          "par apport calé. Il garde ses résultats et permet de reprendre un "
          "calage interrompu."),
    Terme("unsteady", "Unsteady Flow", r"Unsteady(?:&nbsp;|\s)Flow",
          "Fichier HEC-RAS de l'écoulement non permanent, d'extension .u01 à .u99. "
          "Il porte les hydrogrammes injectés, les conditions aux limites et les "
          "conditions initiales.", *_HEC),
    Terme("zone_2d", "Zone 2D", r"[Zz]ones? (?:d[’']écoulement )?2D",
          "Zone maillée où HEC-RAS calcule l'écoulement en deux dimensions "
          "(« 2D Flow Area »). Le calage n'accepte qu'une zone 2D par modèle.",
          *_HEC_2D),
    Terme("maillage", "Maillage", r"\b[Mm]aillages?\b",
          "Ensemble des cellules de calcul de la zone 2D. HEC-RAS y calcule "
          "hauteurs et débits, cellule par cellule.", *_HEC_2D),
    Terme("axe", "Axe hydraulique", r"[Aa]xe hydraulique",
          "Polyligne tracée le long du cours d'eau. Les PK des sections et des "
          "injections s'y mesurent, et le profil en long la suit."),
    Terme("pk", "PK", r"\bPK\b",
          "Point kilométrique : distance mesurée le long de l'axe hydraulique, en "
          "m. Il range sections et injections de l'amont vers l'aval."),
    Terme("profil_long", "Profil en long", r"[Pp]rofils? en long",
          "Cote du fond et ligne d'eau maximale le long de l'axe hydraulique, lues "
          "dans les mailles les plus proches. Il donne la pente des apports créés."),
    Terme("appariement", "Appariement", r"[Aa]ppariements?",
          "Lien entre une section de contrôle et l'injection qu'elle sert à caler. "
          "Chaque section prend la première injection en amont d'elle, le long de "
          "l'axe."),
    Terme("fenetre_evenement", "Fenêtre de l'événement",
          r"[Ff]enêtres? de l[’']événement",
          "Période où le calage juge l'apport : volume, pointe et forme s'y "
          "comparent à la cible. L'apport est tout de même calculé sur toute la "
          "durée simulée."),
    Terme("forme", "Critère de forme", r"[Cc]ritères? de forme",
          "Corrélation r entre le débit calculé et la cible décalée du Δt. Elle "
          "juge la forme de la crue ; il faut au moins 97 %.",
          # Sans le sigle de l'indicateur agrege : l'aide ne le nomme plus
          # (banc, « l'aide ne parle plus en KGE »).
          "Gupta, Kling, Yilmaz et Martinez 2009, décomposition de l'erreur "
          "quadratique",
          "https://doi.org/10.1016/j.jhydrol.2009.08.003"),
    Terme("bilan_masse", "Bilan de masse", r"[Bb]ilans? de masse",
          "Écart entre l'eau entrée et l'eau sortie ou stockée dans le modèle, en % "
          "du volume. Il juge la qualité numérique du calcul, pas l'écart à la "
          "cible."),
    Terme("pas_calcul", "Pas de calcul", r"[Pp]as de calcul",
          "Intervalle de temps entre deux instants calculés par HEC-RAS. Plus "
          "court, il réduit l'erreur de bilan de masse, mais allonge le calcul."),
    Terme("ras_commander", "ras-commander", r"ras-commander",
          "Bibliothèque Python libre qui pilote HEC-RAS : plans, calculs, lecture "
          "des résultats. Le calage s'en sert hors du processus de QGIS.",
          "CLB Engineering, ras-commander", "https://github.com/gpt-cmdr/ras-commander"),
    Terme("hdf5", "HDF5", r"\bHDF5\b",
          "Format des fichiers de résultats de HEC-RAS (.hdf). QGIS et h5py "
          "chargent chacun leur bibliothèque HDF5, qui ne cohabitent pas dans un "
          "même processus.",
          "The HDF Group", "https://www.hdfgroup.org/solutions/hdf5/"),
    Terme("ras_mapper", "RAS Mapper", r"RAS(?:&nbsp;|\s)Mapper",
          "Module cartographique de HEC-RAS. Il affiche la géométrie, le terrain "
          "et les résultats des plans.", *_HEC),
)


@lru_cache(maxsize=1)
def _par_cle():
    return {t.cle: t for t in TERMES}


def terme(cle):
    """Le terme de cle ``cle`` ; None s'il n'existe pas."""
    return _par_cle().get(cle)


@lru_cache(maxsize=1)
def _motif():
    return re.compile("|".join(f"(?P<t{i}>{t.motif})" for i, t in enumerate(TERMES)))


# Ce que lier() laisse tel quel : un lien existant, un texte en italique, en
# code ou en titre (un nom de fichier, un bouton, un titre de section), puis
# toute balise.
_INTACT = re.compile(r"(<a\b[^>]*>.*?</a>|<i>.*?</i>|<tt>.*?</tt>|<code>.*?</code>"
                     r"|<h[1-6]\b[^>]*>.*?</h[1-6]>|<[A-Za-z/!][^>]*>)", re.DOTALL)
# Un « & » qui n'ouvre pas une entite HTML.
_ESPERLUETTE = re.compile(r"&(?![A-Za-z]+;|#\d+;|#x[0-9A-Fa-f]+;)")


def est_html(texte):
    """Vrai si le texte porte au moins une balise."""
    return re.search(r"<[A-Za-z/][^>]*>", texte) is not None


def _echapper(morceau):
    return _ESPERLUETTE.sub("&amp;", morceau).replace("<", "&lt;").replace(">", "&gt;")


def lier(texte, sauf=""):
    """
    Fait de chaque occurrence d'un terme un lien ``terme:<cle>`` (HTML), hors
    des balises, des liens existants et des textes en italique, en code ou en
    titre ; ``sauf`` : un terme a laisser tel quel. Un texte brut devient du
    HTML : « < » et « & » y sont echappes, les retours a la ligne y deviennent
    des <br>. Appliquee deux fois, la fonction ne change plus rien.
    """
    if not texte:
        return texte
    brut = not est_html(texte)

    def remplacer(m):
        cle = TERMES[int(m.lastgroup[1:])].cle
        if cle == sauf:
            return m.group(0)
        return f'<a href="{PREFIXE}{cle}">{m.group(0)}</a>'

    morceaux = _INTACT.split(texte)
    rendu = "".join(morceau if i % 2 else _motif().sub(remplacer, _echapper(morceau))
                    for i, morceau in enumerate(morceaux))
    return rendu.replace("\n", "<br>") if brut else rendu


def presents(texte):
    """Les termes nommes dans ``texte`` (sans balises), chacun une fois, dans l'ordre."""
    vus = {}
    for m in _motif().finditer(re.sub(r"<[^>]+>", "", texte)):
        t = TERMES[int(m.lastgroup[1:])]
        vus.setdefault(t.cle, t)
    return list(vus.values())


def apres_deux_points(texte):
    """Une definition apres « Terme : » : minuscule initiale, sauf pour un sigle."""
    if len(texte) > 1 and texte[1].islower():
        return texte[0].lower() + texte[1:]
    return texte


def definition(t):
    """« Terme : definition », en texte brut : l'infobulle d'un terme."""
    return f"{t.nom} : {apres_deux_points(t.definition)}"


def resume(texte):
    """Les definitions des termes de ``texte``, une par ligne : l'infobulle d'un libelle."""
    return "\n".join(definition(t) for t in presents(texte))


# Les liens que liens_discrets() habille : ceux du lexique, et les sources.
_LIEN = re.compile(rf'<a href="({PREFIXE}|#{ANCRE}|https://)')


def liens_discrets(texte, couleur):
    """
    Les liens du lexique et des sources dans la couleur du texte qui les
    porte, sans soulignement : Qt les peindrait en bleu souligne, ce que
    l'utilisateur ne veut pas (Plemmyra, 26/10/2026). Le sommaire de l'aide
    et le fil conducteur gardent leur apparence de lien.
    """
    return _LIEN.sub(rf'<a style="color: {couleur}; text-decoration: none" href="\1', texte)


def entree(t):
    """
    L'entree d'un terme dans l'aide (HTML) : ancre, nom, definition dont les
    autres termes renvoient a leur entree, et publication (lien ↗ quand son
    adresse est connue).
    """
    texte = lier(apres_deux_points(t.definition), sauf=t.cle).replace(
        f'href="{PREFIXE}', f'href="#{ANCRE}')
    source = ""
    if t.source:
        cite = html.escape(t.source, quote=False)
        if t.url:
            cite = f'<a href="{html.escape(t.url)}">{cite}</a>&nbsp;↗'
        source = f" <i>Source : {cite}.</i>"
    return f'<a name="{ANCRE}{t.cle}"></a><b>{html.escape(t.nom)}</b> : {texte}{source}'
