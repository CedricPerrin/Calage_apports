"""
Socle d'affichage de la fenêtre : constantes et aides que plusieurs étapes nomment.

Sortis de plugin.py le 10/11/2026 (docs/decoupage_dialogue.md, phase 2), code
déplacé à l'identique, pour que la page Suivi (page_suivi.py) les emploie sans
importer plugin.py, qui l'importe. N'y entre que ce dont une page sortie a
besoin ; plugin.py ré-exporte ce que le banc lit sur lui par son nom.

journaliser n'y est pas : il nomme NOM_PLUGIN, dont test_plugin_qgis.py exige
l'unique définition dans le texte de plugin.py.
"""

import os
from datetime import datetime

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QFormLayout

from . import noyau
from .interface import EtiquetteLexique
from .widgets import STATUT_REPRIS


# UN SEUL BOUTON, SOUS LE PREFIXE (22/09/2026, demande utilisateur) : ecrire
# la geometrie, composer le classeur des hydrogrammes, controler — et le dire.
# Il s'appelait « Ecrire dans la geometrie HEC-RAS » depuis la 0.9.5, quand la
# composition est devenue automatique ; mais l'automatique renonce EN SILENCE
# des qu'un prealable manque, et « Ouvrir dans Excel » restait gris apres le
# prefixe sans que rien ne dise pourquoi.
BOUTON_GEOMETRIE = "Valider la géométrie et générer le fichier des hydrogrammes"

# En FRACTIONS de la cible ; la table du noyau, qui fait foi, les porte en
# pourcentages (noyau.DEFAUTS_PARAMETRES).
TOLERANCE_VOLUME_DEFAUT = noyau.DEFAUTS_PARAMETRES["Tolerance_volume_pct"] / 100
TOLERANCE_PIC_DEFAUT = noyau.DEFAUTS_PARAMETRES["Tolerance_pic_pct"] / 100
TOLERANCE_FORME_DEFAUT = 0.03

ISL_TEAL = "#3A8D94"          # institutionnel (Pantone 5483 C)
ISL_TEAL_SOMBRE = "#2E7176"
ISL_ARDOISE = "#526B7A"       # variante lisible sur le fond clair de QGIS
ISL_ARDOISE_CLAIR = "#526B7A"  # les étapes en attente restent lisibles
# Hors charte, et volontairement : la charte n'a pas de couleur d'etat, et
# reserver le teal institutionnel a l'erreur le banaliserait. Ces deux tons
# ne servent QU'A dire si une saisie est fautive ou une etape franchie.
ISL_ROUGE = "#A03028"
ISL_VERT = "#386F55"
ISL_VERT_SOMBRE = "#33654E"    # survol du bouton de controle, quand il est vert

# Deux registres de texte, et deux seulement, en plus des libelles de champs :
#   AIDE — une phrase grise sous un groupe, qui explique un choix ;
#   ETAT — le compte rendu de ce qui vient d'etre fait, encadre.
# Les distinguer par un ROLE plutot que par une feuille de style ecrite a
# chaque endroit evite qu'un texte d'aide finisse en corps de texte, ce qui
# etait arrive : la propriete etait posee, mais aucune regle ne la lisait.
ROLE_AIDE = "aide"
ROLE_ETAT = "etat"


# ---------------------------------------------------------------------------
# Suivi en temps reel — couleurs d'etat
#
# Un calage dure des heures. Ce qui manquait n'est pas l'information — suivi.py
# l'ecrit depuis toujours — mais un endroit ou la voir : le calcul s'arretait
# sans donner de nouvelles. Ces quatre couleurs sont le vocabulaire de
# l'affichage, et il n'y en a pas d'autre.
# ---------------------------------------------------------------------------

# « EN COURS » EST LE TEAL SOMBRE, PAS LE TEAL INSTITUTIONNEL (0.8.5). Ces
# teintes servent de couleur de TEXTE — colonne Statut du tableau, ligne de
# position — et « #3A8D94 » sur le fond clair de QGIS rend 3,4:1, sous les
# 4,5:1 que WCAG 1.4.3 demande a un texte de 10 pt ; « #2E7176 » rend 4,9:1.
# Le teal institutionnel reste celui des TRAITS (courbe du suivi), ou 3:1
# suffit. En theme sombre, interface.COULEURS_SOMBRES ramene les deux au
# meme « #7CC4C8 ».
COULEUR_STATUT = {
    "validé": ISL_VERT,
    "en cours": ISL_TEAL_SOMBRE,
    "échoué": ISL_ROUGE,
    "en attente": ISL_ARDOISE_CLAIR,
    STATUT_REPRIS: ISL_ARDOISE,
}


def date_lisible(iso):
    """« 24/10/2026 à 03 h 15 » depuis l'ISO de l'avancement ; le texte tel
    quel s'il ne se lit pas."""
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d/%m/%Y à %H h %M")
    except ValueError:
        return str(iso)


def duree_lisible(secondes):
    """« 2 h 14 » plutot que « 8040 s » : c'est ce qu'on lit d'un coup d'oeil."""
    if secondes is None:
        return "—"
    secondes = int(secondes)
    if secondes < 60:
        return f"{secondes} s"
    if secondes < 3600:
        return f"{secondes // 60} min"
    return f"{secondes // 3600} h {(secondes % 3600) // 60:02d}"


def courbe_retenue(courbes):
    """
    La serie CALCULEE d'une paire publiee, au format des courbes precedentes.

    Le suivi publie deux choses de forme differente : « courbes », la paire
    cible/section que l'on regarde, et « courbes_precedentes », la famille des
    sections deja calees. Pour rejouer un calage archive, il faut les deux —
    la derniere section validee n'est que dans la premiere. None si la paire
    n'a pas ete validee : un apport en echec ou en recherche n'a pas
    d'hydrogramme retenu, et le tracer laisserait croire a un resultat.
    """
    if not courbes or courbes.get("statut") != "validé":
        return None
    return {"apport": courbes.get("apport"), "section": courbes.get("section"),
            "temps": courbes.get("temps_calcule") or [],
            "debit": courbes.get("debit_calcule") or []}


def texte_aide(contenu, infobulle=None):
    """
    Phrase d'accompagnement : grise, plus petite, jamais indispensable. Ses
    termes techniques renvoient au lexique de l'aide (EtiquetteLexique).
    """
    label = EtiquetteLexique(contenu)
    label.setWordWrap(True)
    label.setProperty("role", ROLE_AIDE)
    if infobulle:
        label.setToolTip(infobulle)
    return label


def dire(label, contenu):
    """Renseigne un compte rendu, et le fait apparaitre ou disparaitre."""
    label.setText(contenu)
    label.setVisible(bool(contenu))


def formulaire(parent=None):
    """QFormLayout au rythme commun ; les champs occupent toute la largeur."""
    f = QFormLayout(parent) if parent is not None else QFormLayout()
    f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    f.setHorizontalSpacing(12)
    f.setVerticalSpacing(9)
    return f

# COMBIEN DE TEMPS ON LAISSE AU CALAGE POUR ECRIRE SON PREMIER ETAT avant de
# le declarer mort. Il lui faut ouvrir le classeur, initialiser ras-commander
# et titrer sa premiere etape — une trentaine de secondes sur un modele leger,
# davantage sur un partage reseau. Mesure du 08/09/2026 sur un modele reel :
# 1 min 55 entre le lancement et la premiere ligne d'etape.
#   ET IL FAUT CETTE PATIENCE : le PID rendu par Popen n'est pas celui du
# calage quand l'interpreteur est un relais (voir _maj_suivi), si bien qu'il
# disparait aussitot. Sans delai, le suivi annoncait « mort au demarrage »
# trois secondes apres un lancement qui se deroulait bien.
DELAI_PREMIER_ETAT_S = 240


def _cle_fichier(chemin):
    """(chemin, date de modification) — ce qui dit qu'un fichier a change."""
    try:
        return (str(chemin), os.path.getmtime(chemin))
    except OSError:
        return None
