# -*- coding: utf-8 -*-
"""
Mise en forme des classeurs de calage, aux couleurs d'ISL Ingenierie.

Deux classeurs sont concernes, et ils doivent se ressembler : le template de
reference livre avec la chaine, et celui que le plugin compose a partir du
modele. Le second est celui qu'on ouvre tous les jours ; pandas l'ecrivait
sans la moindre mise en forme.

UNE CONTRAINTE COMMANDE TOUT LE RESTE : les feuilles de donnees sont relues
par « pandas.read_excel », qui prend la PREMIERE LIGNE comme en-tete. Aucun
bandeau decoratif ne peut donc etre pose au-dessus d'un tableau — la ligne 1
est l'en-tete, et c'est elle qu'on habille. Le titre, lui, vit sur la feuille
Instructions, qui n'est jamais relue.

La mise en forme ne touche a AUCUNE valeur : couleurs, bordures, largeurs,
formats d'affichage et listes deroulantes. Un format de nombre change ce qui
s'affiche, jamais ce que pandas relit.
"""

from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# Charte ISL — memes teintes que le plugin, sans le croisillon.
VIOLET = "985898"          # domaine « prevention des inondations »
VIOLET_SOMBRE = "7A467A"
ARDOISE = "608098"         # frise institutionnelle
# Teintes de fond, tres desaturees : un classeur se lit et s'imprime.
VIOLET_VOILE = "F4EDF4"
ARDOISE_VOILE = "EDF2F5"
SAISIE = "FFFDF2"          # ce qui est a remplir
GRIS_LIGNE = "D8DEE3"

POLICE = "Calibri"

_MINCE = Side(style="thin", color=GRIS_LIGNE)
BORDURE = Border(left=_MINCE, right=_MINCE, top=_MINCE, bottom=_MINCE)

# Commentaire de chaque parametre — SOURCE UNIQUE, partagee par le template de
# reference (creer_template.py) et par le classeur que le plugin compose. Les
# deux doivent expliquer la meme chose.
COMMENTAIRES = {
    "Dossier_projet_HECRAS":
        "Dossier contenant le fichier .prj. Obligatoire.",
    "Nom_projet": "Nom du fichier .prj, sans extension. Obligatoire.",
    "Version_HECRAS":
        "Lue dans les fichiers du modele par le plugin ; a renseigner ici "
        "pour un usage en ligne de commande.",
    "Nom_zone_2D":
        "Zone d'ecoulement 2D a laquelle sections et injections sont "
        "rattachees. Obligatoire : un meme nom de condition limite peut "
        "exister dans plusieurs zones.",
    "Plan_reference": "Plan de depart. Il est CLONE, jamais modifie.",
    "Geometrie_reference":
        "Geometrie a utiliser. Celle du plan si Mode_selection_modele = plan.",
    "Unsteady_reference":
        "Unsteady Flow a utiliser. Celui du plan si Mode_selection_modele = "
        "plan. Il est toujours clone.",
    "Mode_selection_modele":
        "plan : on garde la geometrie et l'Unsteady Flow du plan de "
        "reference. override : on impose ceux declares ci-dessus.",
    "Premier_apport":
        "Apport par lequel commencer. Vide = tous. Les apports situes en amont "
        "sont tenus pour cales : le calage repart de leur plan d'etape et n'y "
        "touche plus.",
    "Prefixe_scenario":
        "Prefixe pose devant le titre de chaque plan cree par le calage : "
        "« Q100 » donne « Q100-sans apport », « Q100-Apport_<nom> » et, a "
        "l'arrivee, « Q100-avec apports ». VIDE = titres sans prefixe, comme "
        "avant. A RENSEIGNER des qu'on cale plusieurs crues sur le MEME "
        "modele : sans lui, le calage du Q10 EFFACE les plans du Q100, qu'il "
        "prend pour les homonymes d'une relance. Le tiret est ajoute tout "
        "seul. Titre complet limite a 30 caracteres.",
    "Simulation_debut":
        "Laisser VIDE pour reprendre celle du plan de reference — le cas "
        "courant. Format JJMMMAAAA,HH:MM, ex. 13OCT2014,00:00.",
    "Simulation_fin":
        "A renseigner seulement si l'Unsteady Flow retenu couvre une autre "
        "periode que le plan : sinon le calcul tournerait a cote des "
        "hydrogrammes, sans que HEC-RAS s'en plaigne.",
    "Intervalle_calcul": "Ex. 1SEC. Vide = celui du plan.",
    "Intervalle_sortie": "Ex. 1MIN. Vide = celui du plan.",
    "Intervalle_instantane": "Ex. 1MIN. Vide = celui du plan.",
    "Intervalle_mapping": "Ex. 1MIN. Vide = celui du plan.",
    "Tolerance_volume_pct":
        "Ecart admis sur le VOLUME, en % de la cible, juge sur la fenetre du "
        "hydrogramme PRINCIPAL uniquement (une mini-crue avant/apres "
        "l'evenement cale n'entre pas dans ce calcul). 5 % est la valeur du "
        "guide.",
    "Tolerance_pic_pct":
        "Ecart admis sur le DEBIT DE POINTE, en % de la cible. Il a sa propre "
        "tolerance parce qu'il dimensionne l'alea.",
    "Bilan_masse_max_pct":
        "QUALITE DU CALCUL, PAS ECART A LA CIBLE. Erreur de conservation que "
        "HEC-RAS rend lui-meme (« volume accounting error ») : ce qu'il perd "
        "ou fabrique entre entrees, sorties et stockage. Au-dela, l'essai est "
        "REJETE sans etre compare a la cible — on ne corrige pas un apport "
        "pour compenser une erreur du solveur. Desserrer en connaissance de "
        "cause ; resserrer le pas de calcul du plan est le vrai remede.",
    "Nb_max_iterations_par_apport":
        "Garde-fou de dernier recours, non le mode d'arret normal : la "
        "concordance s'obtient en trois a quatre essais. Minimum 3.",
    "Fenetre_active":
        "oui / non / vide. Restreint le JUGEMENT (volume, pointe, forme) et "
        "les figures a la fenetre de la crue calee, detectee sur l'ecart a "
        "l'etat sans apport. VIDE = active, c'est le defaut ; « non » juge "
        "sur toute la duree simulee. L'apport injecte, lui, est toujours "
        "calcule sur toute la serie.",
    "Fenetre_seuil_bas_pct":
        "Part du volume cumule du deficit laissee avant t0. Capter LARGE a la "
        "montee : une fenetre trop large ne coute rien, une fenetre trop "
        "etroite interdit la convergence. Valeur a confirmer sur les premiers "
        "cas (§ 5).",
    "Fenetre_seuil_haut_pct":
        "Part du volume cumule du deficit atteinte a tf. Couper FRANC au "
        "tarissement. La fenetre est elargie d'office si ce seuil devait "
        "couter plus de volume que la tolerance n'en admet : sinon la "
        "concordance serait impossible par construction.",
    "Fenetre_t0_h":
        "Debut de la fenetre IMPOSE, en heures depuis le debut de la cible. "
        "Vide = detection automatique, qui n'est qu'une proposition. Une "
        "borne imposee n'est pas decalee du temps de transfert.",
    "Fenetre_tf_h":
        "Fin de la fenetre IMPOSEE, meme regle que Fenetre_t0_h.",
    "Source_geometrie":
        "SHP : sections et injections sont creees dans la geometrie a partir "
        "des shapefiles. MANUEL : elles existent deja dans le modele.",
    "Fichier_SHP_Sections":
        "Polylignes transversales traversant le lit de part en part, avec un "
        "champ de nom.",
    "Fichier_SHP_Apports": "Polylignes des lignes d'injection.",
    "Fichier_SHP_Axe":
        "UNE polyligne, dessinee de l'amont vers l'aval. Sans elle : ni PK, "
        "ni verification de l'ordre, ni profil en long.",
    "Champ_nom_SHP":
        "Champ portant le nom des objets dans les trois couches.",
    "Sens_axe":
        "amont_aval si l'axe est dessine dans le sens de l'ecoulement.",
    "PK_origine_m":
        "PK attribue a l'origine de l'axe. Projection METRIQUE obligatoire "
        "(Lambert-93 / EPSG:2154 en France metropolitaine).",
    "Pas_profil_m":
        "Pas d'echantillonnage du profil le long de l'axe, en metres.",
    "Distance_max_axe_maillage_m":
        "Au-dela, un point d'axe est laisse vide plutot que rattache a une "
        "maille lointaine. Vide = deduit de la taille locale de maille.",
    "Pente_apport_creee_m_par_m":
        "Pente provisoire donnee aux injections CREEES par le plugin. La "
        "pente reellement appliquee au calage est celle de la feuille "
        "Correspondance, ou a defaut celle deduite du profil en long.",
    "Dossier_sortie": "Ou sont ecrits le paquet, les resultats et le suivi.",
    "Sous_dossier_resultats": "Sous-dossier des livrables finaux.",
    "Sous_dossier_suivi":
        "Sous-dossier des sorties de suivi, reecrites a chaque apport valide.",
    "Nom_clone_geometrie": "Titre donne a la copie de travail de la geometrie. "
                           "Le plan et l'Unsteady Flow, eux, sont titres par "
                           "etape : « sans_apport », puis « Apport_<nom> ».",
}


def _police(taille=10, gras=False, couleur="1A1A1A", italique=False):
    return Font(name=POLICE, size=taille, bold=gras, color=couleur,
                italic=italique)


def habiller_entete(feuille, colonnes=None, hauteur=26):
    """
    Habille la LIGNE 1 : c'est l'en-tete du tableau, et le seul endroit ou
    poser de la couleur sans desorienter pandas.
    """
    fond = PatternFill("solid", fgColor=VIOLET)
    nb = colonnes or feuille.max_column
    for i in range(1, nb + 1):
        cellule = feuille.cell(row=1, column=i)
        cellule.fill = fond
        cellule.font = _police(10, gras=True, couleur="FFFFFF")
        cellule.alignment = Alignment(horizontal="left", vertical="center",
                                      wrap_text=True)
        cellule.border = BORDURE
    feuille.row_dimensions[1].height = hauteur
    feuille.freeze_panes = "A2"


def largeurs(feuille, valeurs):
    """Largeurs de colonnes, en caracteres. valeurs : dict {index: largeur}."""
    for index, largeur in valeurs.items():
        feuille.column_dimensions[get_column_letter(index)].width = largeur


def zebrer(feuille, premiere_ligne=2, derniere_ligne=None, colonnes=None,
           teinte=ARDOISE_VOILE):
    """
    Une ligne sur deux legerement teintee. Sur un tableau de vingt lignes et
    quatre colonnes, c'est ce qui evite de lire la valeur d'a cote.
    """
    fond = PatternFill("solid", fgColor=teinte)
    fin = derniere_ligne or feuille.max_row
    nb = colonnes or feuille.max_column
    for ligne in range(premiere_ligne, fin + 1):
        for i in range(1, nb + 1):
            cellule = feuille.cell(row=ligne, column=i)
            cellule.border = BORDURE
            if cellule.font is None or not cellule.font.name:
                cellule.font = _police()
            if ligne % 2 == 0:
                cellule.fill = PatternFill("solid", fgColor=teinte)
    return fond


def mise_en_page(feuille, paysage=False, repeter_entete=True):
    """
    Reglages d'impression. Un classeur de calage finit imprime dans un dossier
    d'etude : sans cela il sort sur six pages avec l'en-tete sur la premiere.
    """
    feuille.page_setup.orientation = "landscape" if paysage else "portrait"
    feuille.page_setup.fitToWidth = 1
    feuille.page_setup.fitToHeight = 0
    feuille.sheet_properties.pageSetUpPr.fitToPage = True
    if repeter_entete:
        feuille.print_title_rows = "1:1"


def liste_deroulante(feuille, plage, choix):
    """
    Liste de choix sur une plage. Purement une aide a la saisie : la valeur
    ecrite reste du texte, et les controles de la chaine la relisent comme
    avant. On n'INTERDIT pas la saisie libre — un classeur rempli sur un poste
    sans Excel doit rester valide.
    """
    validation = DataValidation(type="list",
                                formula1='"' + ",".join(choix) + '"',
                                allow_blank=True, showDropDown=False)
    validation.error = None
    feuille.add_data_validation(validation)
    validation.add(plage)


def styler_parametres(feuille):
    """
    Feuille Parametres : Parametre | Valeur | Commentaire.

    Le classeur COMPOSE par le plugin n'ecrit que les deux premieres colonnes.
    On lui ajoute la troisieme depuis COMMENTAIRES : le classeur de reference
    et celui qu'on remplit tous les jours doivent expliquer la meme chose, et
    la tenir a deux endroits garantissait qu'un des deux mente. Une colonne
    supplementaire ne gene aucun controle : ils lisent par nom de colonne.
    """
    if feuille.max_column < 3 or not feuille.cell(row=1, column=3).value:
        feuille.cell(row=1, column=3).value = "Commentaire"
        for ligne in range(2, feuille.max_row + 1):
            nom = str(feuille.cell(row=ligne, column=1).value or "")
            if nom in COMMENTAIRES:
                feuille.cell(row=ligne, column=3).value = COMMENTAIRES[nom]

    habiller_entete(feuille)
    largeurs(feuille, {1: 34, 2: 40, 3: 62})
    fond_section = PatternFill("solid", fgColor=ARDOISE_VOILE)

    for ligne in range(2, feuille.max_row + 1):
        nom = feuille.cell(row=ligne, column=1)
        valeur = feuille.cell(row=ligne, column=2)
        commentaire = feuille.cell(row=ligne, column=3)
        texte = str(nom.value or "")

        # Les separateurs « --- GEOMETRIE --- » deviennent de vraies barres de
        # section : c'est ce qui donne au tableau sa structure d'un coup d'oeil.
        if texte.startswith("---"):
            propre = texte.strip("- ").strip()
            nom.value = propre.upper()
            for i in range(1, 4):
                c = feuille.cell(row=ligne, column=i)
                c.fill = fond_section
                c.font = _police(10, gras=True, couleur=ARDOISE)
                c.border = Border(top=Side(style="thin", color=ARDOISE),
                                  bottom=Side(style="thin", color=ARDOISE))
            feuille.row_dimensions[ligne].height = 20
            continue

        nom.font = _police(10, gras=True, couleur=VIOLET_SOMBRE)
        nom.alignment = Alignment(vertical="top")
        nom.border = BORDURE
        valeur.font = _police(10)
        # ALIGNEE A GAUCHE, y compris pour les nombres : sans cela « 0,5 » et
        # « 6 » se collent au bord droit d'une colonne large pendant que les
        # chemins commencent a gauche, et la colonne parait desordonnee.
        valeur.alignment = Alignment(vertical="top", horizontal="left")
        valeur.fill = PatternFill("solid", fgColor=SAISIE)
        valeur.border = Border(left=Side(style="medium", color=VIOLET),
                               right=_MINCE, top=_MINCE, bottom=_MINCE)
        if texte.endswith("_pct"):
            valeur.number_format = "0.0"
        commentaire.font = _police(9, couleur="6B6B6B", italique=True)
        commentaire.alignment = Alignment(vertical="top", wrap_text=True)
        commentaire.border = BORDURE
        # AUCUNE HAUTEUR IMPOSEE. Une hauteur fixe empeche Excel d'ajuster la
        # ligne au texte renvoye a la ligne : les commentaires longs etaient
        # tronques a mi-phrase.

    # Aides a la saisie sur les parametres a valeurs fermees.
    fermes = {"Source_geometrie": ["SHP", "MANUEL"],
              "Sens_axe": ["amont_aval", "aval_amont"],
              "Mode_selection_modele": ["plan", "override"],
              # Trois etats : la case VIDE n'est pas un « non », c'est le
              # defaut — fenetre active.
              "Fenetre_active": ["", "oui", "non"]}
    for ligne in range(2, feuille.max_row + 1):
        nom = str(feuille.cell(row=ligne, column=1).value or "")
        if nom in fermes:
            liste_deroulante(feuille, f"B{ligne}", fermes[nom])
    mise_en_page(feuille)


def styler_correspondance(feuille):
    """Feuille Correspondance : une ligne par apport a caler."""
    habiller_entete(feuille)
    largeurs(feuille, {1: 8, 2: 26, 3: 30, 4: 24, 5: 17})
    zebrer(feuille)
    for ligne in range(2, feuille.max_row + 1):
        feuille.cell(row=ligne, column=1).alignment = Alignment(
            horizontal="center", vertical="center")
        for i in range(1, feuille.max_column + 1):
            feuille.cell(row=ligne, column=i).font = _police()
        # La pente est facultative : signalee comme une saisie possible, pas
        # comme un trou a combler.
        if feuille.max_column >= 5:
            pente = feuille.cell(row=ligne, column=5)
            pente.number_format = "0.0000"
            pente.alignment = Alignment(horizontal="center")
    if feuille.max_row > 1:
        feuille.auto_filter.ref = (
            f"A1:{get_column_letter(feuille.max_column)}{feuille.max_row}")
    mise_en_page(feuille, paysage=True)


def styler_cibles(feuille):
    """
    Feuille Cibles : Temps_h puis une colonne par section.

    C'est la seule feuille ou l'utilisateur colle beaucoup de chiffres. Le
    temps est fige a gauche, les debits sont marques comme saisie, et une
    valeur negative — impossible pour un debit de crue, et refusee par les
    controles — se colore d'elle-meme.
    """
    habiller_entete(feuille)
    largeurs(feuille, {1: 11})
    for i in range(2, max(feuille.max_column, 2) + 1):
        feuille.column_dimensions[get_column_letter(i)].width = 15
    feuille.freeze_panes = "B2"

    derniere = max(feuille.max_row, 2)
    for ligne in range(2, derniere + 1):
        temps = feuille.cell(row=ligne, column=1)
        # « General » et non « 0.### » : ce dernier affiche « 0. », « 1. »,
        # avec un separateur decimal orphelin sur les valeurs entieres.
        temps.number_format = "General"
        temps.font = _police(10, gras=True, couleur=ARDOISE)
        temps.alignment = Alignment(horizontal="center", vertical="center")
        temps.fill = PatternFill("solid", fgColor=ARDOISE_VOILE)
        temps.border = BORDURE
        for i in range(2, feuille.max_column + 1):
            c = feuille.cell(row=ligne, column=i)
            c.number_format = "0.00"
            c.font = _police()
            c.alignment = Alignment(horizontal="right", vertical="center")
            c.fill = PatternFill("solid", fgColor=SAISIE)
            c.border = BORDURE

    if feuille.max_column >= 2:
        plage = (f"B2:{get_column_letter(feuille.max_column)}"
                 f"{max(derniere, 2)}")
        feuille.conditional_formatting.add(plage, CellIsRule(
            operator="lessThan", formula=["0"],
            fill=PatternFill("solid", fgColor="F6D6D2"),
            font=Font(name=POLICE, size=10, color="A03028", bold=True)))

    # TOUJOURS present, meme un template vide : c'est ce qui permet de
    # verifier une cible collee — bonne unite, bonne colonne, bon pas de
    # temps — d'un coup d'oeil, sans rouvrir un autre outil.
    _ajouter_apercu_cibles(feuille)
    mise_en_page(feuille, paysage=True)


# En-tete du petit tableau de debit de pointe ajoute sur la feuille Cibles
# (cf. _ajouter_apercu_cibles). RESERVE : controle_donnees.py l'exclut par ce
# nom exact pour ne pas le prendre pour une cible mal orthographiee — source
# unique, comme COMMENTAIRES.
ENTETE_PIC = "Q pic (m³/s)"

# Marge au-dela de la donnee actuelle pour les plages du graphique et des
# formules MAX. La feuille Cibles est completee A LA MAIN apres la
# composition du classeur, SANS que mettre_en_forme() soit relance : la
# plage doit donc deja couvrir ce que l'utilisateur y collera, pas seulement
# ce qui s'y trouve au moment de la generation.
LIGNES_GRAPHIQUE_CIBLES = 500

_MARQUEURS_SERIES = ("diamond", "square", "triangle", "circle", "x", "star")
_COULEURS_SERIES = (VIOLET, ARDOISE, "C87137", "4C8C5C", "B85C5C", "5C7AB8")


def _ajouter_apercu_cibles(feuille):
    """
    Controle visuel sur la feuille Cibles elle-meme : un graphique superposant
    tous les hydrogrammes cibles, et un petit tableau du debit de pointe de
    chacun (formule MAX, pas une valeur figee — il suit la saisie).

    BUT : reperer une cible mal collee (mauvaise unite, colonne decalee,
    pas de temps foireux) en un coup d'oeil, sans ouvrir un autre outil.

    Le tableau et le graphique vivent a distance des colonnes de saisie
    (au moins deux colonnes vides apres la derniere cible) : ils ne doivent
    jamais se confondre visuellement avec les donnees collees. Cote lecture,
    controle_donnees.py les reconnait a l'en-tete ENTETE_PIC et aux colonnes
    sans nom que produit pandas pour les colonnes d'ecart — il les ignore,
    plutot que de les signaler comme des cibles inutilisees.
    """
    from openpyxl.chart import Reference, ScatterChart, Series
    from openpyxl.chart.marker import Marker
    from openpyxl.chart.shapes import GraphicalProperties
    from openpyxl.drawing.line import LineProperties

    # CAPTUREE UNE FOIS : ecrire le tableau plus bas deplace feuille.max_column
    # vers la droite. Le relire ensuite aurait fait entrer le tableau
    # lui-meme dans la liste des cibles a tracer.
    derniere_col_cible = feuille.max_column
    if derniere_col_cible < 2:
        return  # pas une seule colonne de cible : rien a montrer

    noms = [feuille.cell(row=1, column=i).value
           for i in range(2, derniere_col_cible + 1)]
    if not any(noms):
        return

    derniere = max(feuille.max_row, 2, LIGNES_GRAPHIQUE_CIBLES)

    # --- petit tableau des debits de pointe -------------------------------
    col_debut = derniere_col_cible + 3
    entete = feuille.cell(row=1, column=col_debut)
    entete.value = ENTETE_PIC
    entete.font = _police(10, gras=True, couleur=VIOLET_SOMBRE)
    for j, nom in enumerate(noms):
        col = col_debut + j
        c_nom = feuille.cell(row=2, column=col)
        c_nom.value = nom
        c_nom.font = _police(9, couleur=ARDOISE)
        c_pic = feuille.cell(row=3, column=col)
        lettre_source = get_column_letter(2 + j)
        c_pic.value = f"=MAX({lettre_source}2:{lettre_source}{derniere})"
        c_pic.number_format = "0.00"
        c_pic.font = _police(10, gras=True, couleur=VIOLET)
        c_pic.fill = PatternFill("solid", fgColor=VIOLET_VOILE)
        c_pic.border = BORDURE

    # --- graphique des hydrogrammes cibles superposes ----------------------
    graphique = ScatterChart()
    graphique.title = "Hydrogrammes cibles"
    graphique.scatterStyle = "lineMarker"
    graphique.x_axis.title = "Temps (h)"
    graphique.y_axis.title = "Debit (m3/s)"
    graphique.x_axis.delete = False
    graphique.y_axis.delete = False
    graphique.legend.position = "t"
    graphique.width, graphique.height = 18, 9

    x_valeurs = Reference(feuille, min_col=1, min_row=2, max_row=derniere)
    for j, i in enumerate(range(2, derniere_col_cible + 1)):
        # min_row=1 pour que title_from_data reprenne l'en-tete comme nom de
        # serie : c'est le meme nom que la colonne, jamais a resaisir.
        y_valeurs = Reference(feuille, min_col=i, min_row=1, max_row=derniere)
        serie = Series(y_valeurs, x_valeurs, title_from_data=True)
        couleur = _COULEURS_SERIES[j % len(_COULEURS_SERIES)]
        serie.marker = Marker(
            symbol=_MARQUEURS_SERIES[j % len(_MARQUEURS_SERIES)], size=6,
            spPr=GraphicalProperties(solidFill=couleur,
                                     ln=LineProperties(solidFill=couleur)))
        serie.graphicalProperties = GraphicalProperties(
            ln=LineProperties(solidFill=couleur, w=20000))
        serie.smooth = False
        graphique.series.append(serie)

    # Idempotence : si la feuille portait deja un graphique (rare — ce chemin
    # part toujours d'une ecriture pandas fraiche, cf. noyau.preparer_classeur
    # et creer_template.construire), on ne l'empile pas dessus.
    feuille._charts = []
    feuille.add_chart(graphique, f"{get_column_letter(col_debut)}5")


COULEURS_ONGLETS = {"Instructions": VIOLET, "Parametres": ARDOISE,
                    "Correspondance": ARDOISE, "Cibles": VIOLET_SOMBRE}


def mettre_en_forme(chemin):
    """
    Applique la charte a un classeur de calage, quelles que soient les
    feuilles qu'il contient. Retourne la liste des feuilles traitees.

    Ne leve JAMAIS sur une feuille inattendue : un classeur mal forme doit
    rester lisible, et c'est aux controles de la chaine de le refuser — pas a
    la mise en forme.
    """
    import openpyxl

    classeur = openpyxl.load_workbook(chemin)
    traitees = []
    for nom in classeur.sheetnames:
        feuille = classeur[nom]
        feuille.sheet_view.showGridLines = False
        if nom in COULEURS_ONGLETS:
            feuille.sheet_properties.tabColor = COULEURS_ONGLETS[nom]
        try:
            if nom == "Parametres":
                styler_parametres(feuille)
            elif nom == "Correspondance":
                styler_correspondance(feuille)
            elif nom == "Cibles":
                styler_cibles(feuille)
            else:
                continue
            traitees.append(nom)
        except Exception:                                   # noqa: BLE001
            continue
    classeur.save(chemin)
    return traitees


# ---------------------------------------------------------------------------
# Auto-test
#
# CE MODULE N'EN AVAIT AUCUN, et il etait pourtant compte parmi les bancs
# verts du projet — dans STATUT.txt section 1, dans le LISEZMOI du plugin et
# dans la boucle de commandes du CHECKPOINT. « python style_classeur.py »
# sortait 0 sans un mot : il passait parce qu'il ne faisait rien. Un banc qui
# ne controle rien est pire qu'un banc absent, parce qu'on le compte.
#
# CE QU'IL PROTEGE, ET QUI N'EST PAS COSMETIQUE : mettre_en_forme() met la
# main sur le classeur que l'utilisateur remplit ensuite. Elle promet de ne
# JAMAIS lever sur une feuille inattendue, de rendre la liste de ce qu'elle a
# traite, et de poser un apercu dont controle_donnees.py depend par son
# en-tete. Ces trois promesses n'etaient verifiees nulle part.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    import tempfile
    from pathlib import Path

    import openpyxl

    _echecs = []

    def _verifier(libelle, condition, detail=""):
        print(f"      [{'OK' if condition else 'ECHEC'}] {libelle}"
              + (f"  ->  {detail}" if detail else ""))
        if not condition:
            _echecs.append(libelle)

    print("=" * 72)
    print("AUTO-TEST DE LA MISE EN FORME DU CLASSEUR")
    print("=" * 72)

    _dossier = Path(tempfile.mkdtemp(prefix="calage_style_"))

    def _classeur_temoin(chemin, avec_intrus=True, cibles=True):
        """Un classeur de calage plausible, plus une feuille que la charte
        ne connait pas — c'est elle qui eprouve la promesse « ne leve
        jamais »."""
        cl = openpyxl.Workbook()
        f = cl.active
        f.title = "Parametres"
        f.append(["Parametre", "Valeur"])
        f.append(["Nom_projet", "TEMOIN"])
        f.append(["Tolerance_volume_pct", 5])

        c = cl.create_sheet("Correspondance")
        c.append(["Ordre", "Nom_Apport (BC line)", "Nom_Section (reference line)",
                  "Nom_Cible", "Pente_m_par_m"])
        c.append([1, "A1", "SC1", "Cible_SC1", None])
        c.append([2, "A2", "SC2", "Cible_SC2", 0.002])

        if cibles:
            ci = cl.create_sheet("Cibles")
            ci.append(["Temps_h", "Cible_SC1", "Cible_SC2"])
            for i in range(1, 6):
                ci.append([0.5 * i, 10.0 * i, 8.0 * i])

        if avec_intrus:
            x = cl.create_sheet("Feuille_que_la_charte_ignore")
            x.append(["quoi que ce soit", 1])
        cl.save(chemin)
        return chemin

    print("\n1. CE QUI EST TRAITE, ET CE QUI EST IGNORE")
    _temoin = _classeur_temoin(_dossier / "temoin.xlsx")
    _traitees = mettre_en_forme(_temoin)
    _verifier("les trois feuilles de la charte sont traitees, et elles seules",
              sorted(_traitees) == ["Cibles", "Correspondance", "Parametres"],
              str(sorted(_traitees)))
    _verifier("une feuille inconnue est IGNOREE, jamais fatale — c'est la "
              "promesse du docstring",
              "Feuille_que_la_charte_ignore" not in _traitees)

    _relu = openpyxl.load_workbook(_temoin)
    _verifier("le quadrillage est retire de TOUTES les feuilles, l'inconnue "
              "comprise",
              all(not _relu[n].sheet_view.showGridLines
                  for n in _relu.sheetnames),
              ", ".join(f"{n}={_relu[n].sheet_view.showGridLines}"
                        for n in _relu.sheetnames))
    _couleurs = {n: (_relu[n].sheet_properties.tabColor.rgb
                     if _relu[n].sheet_properties.tabColor else None)
                 for n in COULEURS_ONGLETS if n in _relu.sheetnames}
    _verifier("chaque onglet de la charte porte sa couleur",
              all(c and COULEURS_ONGLETS[n] in str(c)
                  for n, c in _couleurs.items()),
              str(_couleurs))

    print("\n2. LA FEUILLE CIBLES — CELLE QUE L'UTILISATEUR REMPLIT")
    _ci = _relu["Cibles"]
    _verifier("les volets sont figes en B2 : le temps reste visible quand on "
              "fait defiler les debits",
              _ci.freeze_panes == "B2", str(_ci.freeze_panes))
    _verifier("une mise en forme conditionnelle marque les debits negatifs",
              len(list(_ci.conditional_formatting)) >= 1,
              f"{len(list(_ci.conditional_formatting))} regle(s)")

    print("\n3. L'APERCU, DONT controle_donnees.py DEPEND")
    # LE LIEN EST NOMME, PAS DEVINE : controle_donnees exclut ce tableau des
    # cibles par l'en-tete EXACT que ce module pose. Deux ecritures de la
    # meme chaine finiraient par diverger — le banc verifie qu'elles n'ont
    # qu'une source.
    _entetes = [c.value for c in _ci[1]]
    _verifier(f"l'en-tete « {ENTETE_PIC} » est pose sur la feuille",
              ENTETE_PIC in _entetes, str(_entetes))
    _verifier("un graphique accompagne le tableau",
              len(_ci._charts) >= 1, f"{len(_ci._charts)} graphique(s)")

    # LA PLAGE COUVRE CE QUI SERA COLLE, pas ce qui est la. La feuille est
    # remplie A LA MAIN apres la composition, sans que mettre_en_forme() soit
    # relance : une formule bornee aux 6 lignes du temoin ne verrait jamais
    # les 400 lignes d'une vraie cible.
    _formules = [c.value for ligne in _ci.iter_rows() for c in ligne
                 if isinstance(c.value, str) and c.value.startswith("=MAX(")]
    _verifier("les formules de pointe couvrent LIGNES_GRAPHIQUE_CIBLES, pas "
              "les seules lignes presentes",
              bool(_formules)
              and all(str(LIGNES_GRAPHIQUE_CIBLES) in f for f in _formules),
              _formules[0] if _formules else "aucune formule =MAX")

    print("\n4. CE QUI NE DOIT PAS FAIRE TOMBER LA MISE EN FORME")
    # UNE FEUILLE « Parametres » VIDE est le cas qu'un classeur a moitie
    # ecrit produit. Elle ne doit ni lever, ni etre annoncee comme traitee.
    _vide = openpyxl.Workbook()
    _vide.active.title = "Parametres"
    _chemin_vide = _dossier / "parametres_vide.xlsx"
    _vide.save(_chemin_vide)
    try:
        _t = mettre_en_forme(_chemin_vide)
        _leve = False
    except Exception as _e:                                  # noqa: BLE001
        _t, _leve = None, f"{type(_e).__name__}: {_e}"
    _verifier("une feuille « Parametres » vide ne fait pas lever "
              "mettre_en_forme()", not _leve, _leve or "aucune exception")

    # ET UN CLASSEUR SANS FEUILLE CIBLES reste traitable : la composition
    # peut legitimement n'en poser aucune.
    _sans = _classeur_temoin(_dossier / "sans_cibles.xlsx", cibles=False)
    try:
        _t2 = mettre_en_forme(_sans)
        _leve2 = False
    except Exception as _e:                                  # noqa: BLE001
        _t2, _leve2 = None, f"{type(_e).__name__}: {_e}"
    _verifier("un classeur sans feuille Cibles se met en forme quand meme",
              not _leve2 and _t2 is not None and "Cibles" not in _t2,
              _leve2 or str(_t2))

    print("\n5. MISE EN FORME REJOUEE — ELLE DOIT ETRE IDEMPOTENTE")
    # preparer_classeur() la rappelle a chaque recomposition, sur un classeur
    # deja habille.
    _deux = mettre_en_forme(_temoin)
    _verifier("un second passage traite les memes feuilles",
              sorted(_deux) == sorted(_traitees),
              f"{sorted(_deux)} vs {sorted(_traitees)}")
    _ci2 = openpyxl.load_workbook(_temoin)["Cibles"]
    _verifier("et n'empile pas les graphiques",
              len(_ci2._charts) == len(_ci._charts),
              f"{len(_ci2._charts)} apres deux passages, "
              f"{len(_ci._charts)} apres un")

    import shutil as _shutil
    _shutil.rmtree(_dossier, ignore_errors=True)

    print("\n" + "=" * 72)
    if _echecs:
        print(f"{len(_echecs)} ECHEC(S) : {_echecs}")
        sys.exit(1)
    print("Tous les controles passent.")
    print("=" * 72)
