# -*- coding: utf-8 -*-
"""
Controle de coherence des donnees d'entree, AVANT tout calcul.

Un calage represente plusieurs heures de calcul : une incoherence dans le
template doit etre detectee en quelques secondes, pas apres la premiere
simulation. Ce module valide le classeur de saisie seul (controles 1 a 4),
puis, si un modele est disponible, verifie que les noms declares y existent
reellement (controle 5).

Usage :  python controle_donnees.py [chemin_du_template.xlsx]
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

import parametres

ERREUR, AVERTISSEMENT, INFO = "ERREUR", "AVERTISSEMENT", "INFO"

# Ecart admis entre une condition limite externe et le perimetre du maillage,
# exprime en tailles de maille. Une BC line n'a pas a coincider avec le
# polygone de perimetre : HEC-RAS la rattache aux faces les plus proches, et
# un ecart de l'ordre de la maille est normal. Mesure sur un modele reel :
# ecarts de 0,6 a 2,1 mailles pour des conditions limites correctes.
TOLERANCE_EN_MAILLES = 3.0

def _controler_fenetre_simulation(valeurs, erreur):
    """
    Verifie la fenetre de simulation si elle a ete saisie.

    Les regles de format appartiennent au pilote HEC-RAS, qui seul connait les
    fichiers : les redire ici en ferait une seconde source de verite, qui
    finirait par diverger. On appelle donc sa validation et on traduit
    l'exception en anomalie de classeur.
    """
    correspondance = (("debut", "Simulation_debut"),
                      ("fin", "Simulation_fin"),
                      ("intervalle_calcul", "Intervalle_calcul"),
                      ("intervalle_sortie", "Intervalle_sortie"),
                      ("intervalle_instantane", "Intervalle_instantane"),
                      ("intervalle_mapping", "Intervalle_mapping"))
    fenetre = {}
    for cle, parametre in correspondance:
        brut = valeurs.get(parametre)
        if brut is None or (isinstance(brut, float) and pd.isna(brut)):
            continue
        if str(brut).strip():
            fenetre[cle] = str(brut).strip()
    if not fenetre:
        return
    try:
        # L'import est DANS le try pour que le rattrapage ci-dessous soit
        # atteignable.
        from pilote_hecras import valider_fenetre_simulation
        valider_fenetre_simulation(fenetre)
    except ValueError as e:
        erreur(f"fenetre de simulation : {e}")
    except ImportError:
        # Le controle du classeur doit rester utilisable sans le pilote (il
        # tourne aussi depuis QGIS, ou HEC-RAS n'est pas importable).
        pass


PARAMETRES_REQUIS = [
    "Dossier_projet_HECRAS", "Nom_projet", "Nom_zone_2D",
    "Nb_max_iterations_par_apport",
]

def _controler_prefixe_scenario(valeurs, noms_apports, erreur):
    """
    Verifie que le prefixe de scenario laisse tenir les titres de plan.

    LA REGLE APPARTIENT A LA BOUCLE DE CALAGE, qui la fait respecter : la
    redire ici en ferait une seconde source de verite, qui finirait par
    diverger. On construit, avec LES MEMES fonctions que le calage, les titres
    que le calage construira, et on rapporte ce qu'elles refusent.

    ON NE CONTROLE QUE LA LONGUEUR. Deux apports homonymes donneraient bien
    deux titres identiques, mais le doublon de nom est deja signale dix lignes
    plus haut par le controle de la feuille Correspondance : le redire ici
    refuserait un classeur deux fois pour la meme raison.

    LES TITRES DE REPRISE SONT TOUS INCLUS, un par depart possible — ce sont
    les plus longs. Ne juger que « Premier_apport » ne suffisait pas : ce
    parametre se decide AU LANCEMENT (noyau.ecrire_parametre), donc APRES ce
    controle. Vide au moment du controle, il laissait passer un prefixe que
    la reprise refusait ensuite, le lancement deja demande — constate le
    20 septembre 2026 sur le calage « Aran-Q100-V1 » repris a son sixieme
    apport. Le premier apport est exclu : partir de lui n'est pas une
    reprise, et ne construit pas ce titre.
    """
    try:
        from calage import (ETAPE_AVEC_APPORTS, ETAPE_SANS_APPORT,
                            PREFIXE_ETAPE_APPORT, titre_etape)
    except ImportError:
        # Le controle du classeur doit rester utilisable sans la chaine — il
        # tourne aussi depuis QGIS. L'import est DANS le try pour cela : le
        # placer au-dessus rendrait ce rattrapage inatteignable.
        return

    def _propre(cle):
        brut = valeurs.get(cle)
        if brut is None or (isinstance(brut, float) and pd.isna(brut)):
            return ""
        return str(brut).strip()

    prefixe = _propre("Prefixe_scenario")
    noms = [ETAPE_SANS_APPORT, ETAPE_AVEC_APPORTS]
    noms += [f"{PREFIXE_ETAPE_APPORT}{a}" for a in noms_apports]
    noms += [f"sans {a} et aval" for a in noms_apports[1:]]

    refus = []
    for nom in noms:
        try:
            titre_etape(nom, prefixe)
        except ValueError as e:
            refus.append((len(nom), str(e)))
    if refus:
        # LE PIRE DES TITRES, pas le premier venu : c'est lui qui fixe la
        # marge, et corriger sur un autre laisserait le classeur refuse.
        erreur(f"Prefixe_scenario : {max(refus)[1]}")


# L'axe hydraulique n'est pas indispensable au calage lui-meme, mais sans lui
# il n'y a ni PK, ni verification de l'ordre declare, ni profil en long.
PARAMETRE_AXE = "Fichier_SHP_Axe"


def _lire(chemin):
    """
    Les feuilles du classeur. « Parametres » N'EN EST PLUS UNE (20 septembre
    2026) : les parametres vivent dans le JSON voisin, et parametres.lire()
    sait encore lire la feuille des classeurs d'avant.
    """
    feuilles = pd.read_excel(chemin, sheet_name=None)
    manquantes = {"Correspondance", "Cibles"} - set(feuilles)
    if manquantes:
        raise ValueError(f"feuilles absentes du classeur : {sorted(manquantes)}")
    return feuilles


# ---------------------------------------------------------------------------
# Regles du classeur de saisie. Chacune rend ses anomalies (niveau, message) ;
# controler_template les enchaine dans l'ordre ou l'ingenieur les lit.
# ---------------------------------------------------------------------------

def _regle_parametres_trouves(chemin, valeurs):
    """Le JSON des parametres (ou la feuille heritee) accompagne le classeur."""
    if valeurs:
        return []
    return [(ERREUR,
             f"parametres du calage introuvables : ni "
             f"« {parametres.chemin(chemin).name} » a cote du classeur, "
             f"ni feuille « {parametres.FEUILLE_HERITEE} » dedans. Le "
             f"JSON accompagne le classeur : deplacer l'un sans l'autre "
             f"laisse un calage sans parametres.")]


def _regle_parametres_requis(valeurs):
    anomalies = []
    for cle in PARAMETRES_REQUIS:
        v = valeurs.get(cle)
        if cle not in valeurs or v is None or (
                isinstance(v, float) and pd.isna(v)):
            anomalies.append((ERREUR, f"parametre manquant ou vide : {cle}"))
    return anomalies


def _regle_nb_max_iterations(valeurs):
    nb_max = valeurs.get("Nb_max_iterations_par_apport")
    if isinstance(nb_max, (int, float)) and nb_max < 3:
        return [(ERREUR,
                 f"Nb_max_iterations_par_apport = {nb_max} : au moins 3 essais "
                 f"sont necessaires pour que la correction converge")]
    return []


def _regle_coeurs_par_calcul(valeurs):
    # Cœurs demandes a HEC-RAS : facultatif ; 0 = plan inchange ; 64 est le
    # plafond que Windows accorde a un Ras.exe (ras-commander, set_num_cores).
    coeurs = valeurs.get("Coeurs_par_calcul")
    if coeurs not in (None, "") and not (
            isinstance(coeurs, (int, float)) and not pd.isna(coeurs)
            and float(coeurs).is_integer() and 0 <= coeurs <= 64):
        return [(ERREUR,
                 f"Coeurs_par_calcul = {coeurs!r} : entier entre 0 (plan "
                 f"inchange) et 64 attendu")]
    return []


def _colonnes_correspondance(corr):
    """(Ordre, Nom_Apport, Nom_Section, Nom_Cible) de la feuille, ou None si
    l'une manque."""
    col_ordre = "Ordre"
    col_apport = next((c for c in corr.columns if c.startswith("Nom_Apport")), None)
    col_section = next((c for c in corr.columns if c.startswith("Nom_Section")), None)
    col_cible = next((c for c in corr.columns if c.startswith("Nom_Cible")), None)
    if not all([col_ordre in corr.columns, col_apport, col_section, col_cible]):
        return None
    return col_ordre, col_apport, col_section, col_cible


def _regle_ordre_contigu(colonne_ordre):
    n = len(colonne_ordre)
    illisibles = []
    for ligne, o in colonne_ordre.items():
        try:
            int(o)
        except (TypeError, ValueError):
            # +2 : l'index de pandas compte depuis 0, l'en-tete est la ligne 1.
            illisibles.append((ligne + 2, o))
    if illisibles:
        lus = ", ".join(f"{o!r} (ligne {ligne})" for ligne, o in illisibles)
        return [(ERREUR,
                 f"feuille Correspondance, colonne Ordre : valeur non "
                 f"numerique {lus} ; la colonne doit etre la suite 1..{n} "
                 f"sans trou ni doublon.")]
    ordres = sorted(int(o) for o in colonne_ordre)
    if ordres != list(range(1, n + 1)):
        return [(ERREUR,
                 f"colonne Ordre : doit etre la suite 1..{n} sans trou ni doublon "
                 f"(valeurs lues : {ordres})")]
    return []


def _regle_noms_uniques(corr, col_apport, col_section):
    anomalies = []
    for col, libelle in [(col_apport, "apport"), (col_section, "section")]:
        doublons = corr[col][corr[col].duplicated()].tolist()
        if doublons:
            anomalies.append((
                ERREUR,
                f"nom de {libelle} en doublon : {doublons}. Chaque "
                f"{libelle} doit etre unique — une inconnue par contrainte."))
    return anomalies


def _regle_pas_de_temps(colonne_temps):
    anomalies = []
    temps = pd.to_numeric(colonne_temps, errors="coerce").dropna().to_numpy()
    if len(temps) < 10:
        anomalies.append((
            AVERTISSEMENT,
            f"feuille Cibles : seulement {len(temps)} pas de temps. "
            f"Un hydrogramme trop grossier fausse le volume et le debit "
            f"de pointe compares a la cible."))
    if len(temps) > 1 and not np.all(np.diff(temps) > 0):
        anomalies.append((
            ERREUR,
            "feuille Cibles : la colonne Temps_h doit etre strictement "
            "croissante"))
    return anomalies


def _colonnes_cibles(cib):
    """Les colonnes de la feuille Cibles qui sont des hydrogrammes."""
    # Exclut l'apercu visuel que style_classeur ajoute sur cette meme feuille
    # (graphique + tableau de debit de pointe, cf. ENTETE_PIC) : ses colonnes
    # ne sont pas des cibles, et ne doivent pas se signaler comme telles.
    # « Unnamed: » est le nom que pandas donne aux colonnes sans en-tete —
    # celles du tableau, hors la premiere.
    reserves = {"Temps_h"}
    try:
        import style_classeur
        reserves.add(style_classeur.ENTETE_PIC)
    except ImportError:
        pass
    return {c for c in cib.columns
            if isinstance(c, str) and not c.startswith("Unnamed:")
            } - reserves


def _regle_cibles_declarees_presentes(cibles_declarees, cibles_presentes):
    anomalies = []
    absentes = cibles_declarees - cibles_presentes
    if absentes:
        anomalies.append((
            ERREUR,
            f"cibles declarees dans Correspondance mais absentes de la "
            f"feuille Cibles : {sorted(absentes)}"))
    inutilisees = cibles_presentes - cibles_declarees
    if inutilisees:
        anomalies.append((
            AVERTISSEMENT,
            f"colonnes de la feuille Cibles jamais utilisees : "
            f"{sorted(inutilisees)}"))
    return anomalies


def _regle_hydrogramme_cible(nom, colonne):
    serie = pd.to_numeric(colonne, errors="coerce")
    valides = serie.dropna()
    # Colonne entierement vide : le template n'est pas encore rempli, ce
    # qui est un etat normal et non une donnee fautive.
    if len(valides) == 0:
        return [(AVERTISSEMENT,
                 f"cible '{nom}' : colonne vide, a renseigner avant le calage")]
    if len(valides) < 2:
        return [(ERREUR,
                 f"cible '{nom}' : pas assez de valeurs numeriques "
                 f"({len(valides)} valeur exploitable)")]
    anomalies = []
    if (valides < 0).any():
        anomalies.append((ERREUR, f"cible '{nom}' : contient des debits negatifs"))
    if float(valides.max()) <= 0:
        anomalies.append((ERREUR, f"cible '{nom}' : hydrogramme identiquement nul"))
    if serie.isna().sum() > 0 and serie.dropna().index.max() < len(serie) - 1:
        anomalies.append((AVERTISSEMENT,
                          f"cible '{nom}' : valeurs manquantes intercalees"))
    return anomalies


def controler_template(chemin):
    """
    Valide le classeur de saisie. Retourne une liste de couples
    (niveau, message). Une liste vide signifie que rien ne s'oppose au
    lancement du calage.
    """
    anomalies = []

    def erreur(msg):
        anomalies.append((ERREUR, msg))

    try:
        feuilles = _lire(chemin)
    except Exception as e:
        return [(ERREUR, f"classeur illisible : {e}")]

    # --- 1. Parametres -----------------------------------------------------
    try:
        valeurs = parametres.lire(chemin)
    except json.JSONDecodeError as e:
        # Comme controler_geometrie : sans parametres lisibles, le reste du
        # controle ne dirait que « tout est manquant ».
        return [(ERREUR,
                 f"parametres du calage illisibles : "
                 f"« {parametres.chemin(chemin).name} » n'est pas un JSON "
                 f"valide (ligne {e.lineno}, colonne {e.colno}). Le corriger "
                 f"avant de relancer le controle.")]
    anomalies += _regle_parametres_trouves(chemin, valeurs)
    anomalies += _regle_parametres_requis(valeurs)
    anomalies += _regle_nb_max_iterations(valeurs)
    anomalies += _regle_coeurs_par_calcul(valeurs)

    # Fenetre de simulation : facultative, mais si elle est saisie elle doit
    # etre juste. Une date mal formee n'est pas refusee par HEC-RAS — elle est
    # lue autrement, et le calcul tourne sur une periode qui n'est pas celle
    # des hydrogrammes. La verifier ici coute une seconde ; s'en apercevoir
    # apres coup coute une campagne de calculs.
    _controler_fenetre_simulation(valeurs, erreur)

    # --- 2. Correspondance -------------------------------------------------
    corr = feuilles["Correspondance"]
    colonnes = _colonnes_correspondance(corr)
    if colonnes is None:
        erreur("feuille Correspondance : colonnes Ordre / Nom_Apport / "
               "Nom_Section / Nom_Cible attendues")
        return anomalies
    col_ordre, col_apport, col_section, col_cible = colonnes

    corr = corr.dropna(subset=[col_ordre, col_apport, col_section, col_cible])
    if len(corr) == 0:
        erreur("feuille Correspondance : aucune station renseignee")
        return anomalies

    anomalies += _regle_ordre_contigu(corr[col_ordre])
    anomalies += _regle_noms_uniques(corr, col_apport, col_section)

    # LE PREFIXE SE JUGE SUR LES NOMS D'APPORT REELS : il est donc controle
    # ici, et non a la section 1, qui ne les connait pas encore.
    # DANS L'ORDRE DECLARE : _controler_prefixe_scenario exclut le premier
    # apport, qui seul ne donne pas de titre de reprise. L'ordre des lignes
    # de la feuille n'est pas force d'etre celui de la colonne Ordre.
    # Un Ordre non numerique est deja signale plus haut : il ne doit pas faire
    # echouer ce tri, il part en fin de liste.
    ordre_lu = pd.to_numeric(corr[col_ordre], errors="coerce")
    _controler_prefixe_scenario(
        valeurs,
        [str(a) for a in corr.loc[ordre_lu.sort_values().index, col_apport]],
        erreur)

    # --- 3. Cibles ---------------------------------------------------------
    cib = feuilles["Cibles"]
    if "Temps_h" not in cib.columns:
        erreur("feuille Cibles : colonne 'Temps_h' absente")
        return anomalies

    anomalies += _regle_pas_de_temps(cib["Temps_h"])

    cibles_declarees = set(corr[col_cible].astype(str))
    cibles_presentes = _colonnes_cibles(cib)
    anomalies += _regle_cibles_declarees_presentes(cibles_declarees,
                                                   cibles_presentes)
    for nom in sorted(cibles_declarees & cibles_presentes):
        anomalies += _regle_hydrogramme_cible(nom, cib[nom])

    return anomalies


def _correspondance(chemin_template):
    """Lit la feuille Correspondance et retourne (noms_sections, noms_apports)
    dans l'ordre declare."""
    corr = pd.read_excel(chemin_template, sheet_name="Correspondance")
    col_ordre = "Ordre"
    col_apport = next(
        (c for c in corr.columns if c.startswith("Nom_Apport")), None)
    if col_apport is None:
        raise ValueError("colonne 'Nom_Apport' absente")
    col_section = next(
        (c for c in corr.columns if c.startswith("Nom_Section")), None)
    if col_section is None:
        raise ValueError("colonne 'Nom_Section' absente")
    corr = corr.dropna(subset=[col_ordre, col_apport, col_section])
    corr = corr.sort_values(col_ordre)
    return (corr[col_section].astype(str).tolist(),
            corr[col_apport].astype(str).tolist())


# ---------------------------------------------------------------------------
# Regles de la chaine SIG, enchainees par controler_geometrie.
# ---------------------------------------------------------------------------

def _chemin_declare(valeurs, cle):
    """Chemin saisi pour ce parametre, ou None s'il est vide."""
    v = valeurs.get(cle)
    return None if v is None or pd.isna(v) or not str(v).strip() else Path(str(v))


def _regle_fichiers_existent(chemins):
    return [(ERREUR, f"{cle} : fichier introuvable -> {p}")
            for cle, p in chemins if p is not None and not p.exists()]


def _regle_source_modele(p_sections, p_apports):
    anomalies = []
    if p_sections is not None or p_apports is not None:
        anomalies.append((
            AVERTISSEMENT,
            "Source_geometrie = MODELE, mais des shapefiles sont declares : "
            "ils seront ignores. Passer a SHP pour les utiliser."))
    anomalies.append((
        AVERTISSEMENT,
        "Source_geometrie = MODELE : les sections et les injections sont "
        "supposees deja tracees et nommees dans la geometrie. Leur "
        "existence reelle est verifiee par le controle contre le modele."))
    return anomalies


def _champ_nom(valeurs):
    """Champ_nom_SHP : vide ou absent = detection automatique du champ de nom."""
    champ_nom = valeurs.get("Champ_nom_SHP")
    return (str(champ_nom).strip()
            if champ_nom is not None and not pd.isna(champ_nom)
            and str(champ_nom).strip() else None)


def _lire_axe(p_axe, g_sec):
    """(axe, crs_reference, anomalies). Sans axe, la reference est la
    projection des sections."""
    import geometrie as geo

    if p_axe is None:
        return None, g_sec.crs, [(
            AVERTISSEMENT,
            f"{PARAMETRE_AXE} non renseigne : pas de PK, donc ni verification "
            f"de l'ordre declare ni profil en long. Fournir l'axe hydraulique "
            f"en polyligne est vivement recommande.")]
    try:
        axe, crs_ref = geo.lire_axe(p_axe)
    except Exception as e:
        return None, None, [(ERREUR, f"lecture de l'axe hydraulique : {e}")]
    return axe, crs_ref, []


def _regle_noms_dans_shp(noms_sections, noms_apports, g_sec, g_app):
    """(noms_absents, anomalies) : les noms declares absents des shapefiles."""
    noms_absents, anomalies = [], []
    for declares, presents, libelle in [
        (noms_sections, set(g_sec["nom"]), "section de controle"),
        (noms_apports, set(g_app["nom"]), "ligne d'injection"),
    ]:
        absents = [n for n in declares if n not in presents]
        if absents:
            noms_absents += absents
            anomalies.append((
                ERREUR,
                f"{libelle}(s) declaree(s) dans le template mais absente(s) du "
                f"shapefile : {absents} (presentes : {sorted(presents)})"))
    return noms_absents, anomalies


def _regle_pk_calculables(axe, noms_absents, g_sec, g_app):
    """Rien si les PK sont calculables ; sinon l'avertissement qui dit
    pourquoi."""
    # CE QUI EMPECHE UN PK, DIT EN CLAIR — et non plus deduit de la gravite
    # GENERALE du controle SIG. Un PK est une projection metrique sur l'axe,
    # indexee par le nom : il lui faut l'axe, une projection metrique, et tous
    # les noms declares presents UNE SEULE FOIS. Rien d'autre.
    #   LA SORTIE PRECEDENTE — « des qu'une anomalie ERREUR traine, quelle
    #   qu'elle soit » — supprimait le tableau pour des defauts qui ne
    #   deplacent aucun PK. Mesure en production : sur un calage CONFORME de
    #   douze apports, une ligne d'injection de 94 cm, signalee « de longueur
    #   quasi nulle », a fait disparaitre le profil en long ET les pentes
    #   locales deduites, derriere un « PK indisponibles » qui ne nommait
    #   rien. L'anomalie reste dite, au meme niveau ; elle n'efface plus les PK.
    #   UN NOM EN DOUBLON, LUI, BLOQUE VRAIMENT : dict(zip(...)) garderait la
    #   derniere occurrence en silence, et le profil placerait la section au
    #   mauvais PK.
    doublons = sorted({n for g in (g_sec, g_app)
                       for n in g["nom"][g["nom"].duplicated()]})
    if not (axe is None or noms_absents or doublons):
        return []
    raisons = ["axe hydraulique indisponible"] if axe is None else []
    if noms_absents:
        raisons.append(f"noms declares absents des shapefiles : "
                       f"{noms_absents}")
    if doublons:
        raisons.append(f"noms en doublon dans les shapefiles : {doublons}")
    return [(
        AVERTISSEMENT,
        f"PK non calculables ({' ; '.join(raisons)}) : ni ordre declare "
        f"verifie, ni profil en long, ni pente locale deduite.")]


def _regle_sens_axe(sens):
    if sens is None:
        return [(ERREUR,
                 "Sens_axe : valeur manquante ; valeurs admises "
                 "['amont_aval', 'aval_amont'].")]
    if sens not in ("amont_aval", "aval_amont"):
        return [(ERREUR,
                 f"Sens_axe = '{sens}' : valeurs admises ['amont_aval', "
                 f"'aval_amont'].")]
    return []


def _pk_origine(valeurs):
    """(pk_origine, anomalies) : PK_origine_m en nombre, 0 s'il est vide."""
    pk_origine = valeurs.get("PK_origine_m", 0)
    try:
        return (0.0 if pd.isna(pk_origine) else float(pk_origine)), []
    except (TypeError, ValueError):
        return None, [(
            ERREUR, f"PK_origine_m = '{pk_origine}' : un nombre est attendu.")]


def _tableau_pk(noms_sections, noms_apports, pk_sec, pk_app):
    tableau = pd.DataFrame({
        "Ordre": range(1, len(noms_sections) + 1),
        "Section": noms_sections,
        "PK section (m)": [round(pk_sec[n], 1) for n in noms_sections],
        "Apport": noms_apports,
        "PK apport (m)": [round(pk_app[n], 1) for n in noms_apports],
    })
    tableau["Distance apport-section (m)"] = (
        tableau["PK section (m)"] - tableau["PK apport (m)"]).round(1)
    return tableau


def controler_geometrie(chemin_template):
    """
    Controle de la chaine SIG : shapefiles, PK, et coherence entre la
    geometrie reelle et l'ordre declare dans le template.

    C'est ici que se verifie ce qu'aucune relecture du classeur ne peut
    attraper : une section declaree en amont d'une autre alors qu'elle est
    physiquement en aval, un apport place apres la section qu'il doit
    alimenter, un axe dessine a l'envers, ou des couches en projections
    differentes.

    Retourne (anomalies, tableau_pk). tableau_pk vaut None si les PK n'ont pas
    pu etre calcules.
    """
    import geometrie as geo

    try:
        valeurs = parametres.lire(chemin_template)
    except Exception as e:
        return [(ERREUR, f"parametres du calage illisibles : {e}")], None

    p_sections = _chemin_declare(valeurs, "Fichier_SHP_Sections")
    p_apports = _chemin_declare(valeurs, "Fichier_SHP_Apports")
    p_axe = _chemin_declare(valeurs, PARAMETRE_AXE)

    anomalies = _regle_fichiers_existent([("Fichier_SHP_Sections", p_sections),
                                          ("Fichier_SHP_Apports", p_apports),
                                          (PARAMETRE_AXE, p_axe)])

    # Source_geometrie declare l'intention ; les chemins declarent le fait.
    # Une contradiction entre les deux doit etre dite, pas devinee.
    source_geometrie = str(valeurs.get("Source_geometrie", "SHP") or "SHP"
                           ).strip().upper()
    if source_geometrie not in ("SHP", "MODELE"):
        anomalies.append((
            ERREUR,
            f"Source_geometrie = '{source_geometrie}' : valeurs admises "
            f"['SHP', 'MODELE']."))
        return anomalies, None

    if source_geometrie == "MODELE":
        return anomalies + _regle_source_modele(p_sections, p_apports), None

    if p_sections is None or p_apports is None:
        anomalies.append((
            ERREUR,
            "Source_geometrie = SHP mais les chemins des shapefiles ne sont "
            "pas renseignes. Les renseigner, ou passer Source_geometrie a "
            "MODELE si les lignes sont deja tracees dans la geometrie."))
        return anomalies, None

    if any(n == ERREUR for n, _ in anomalies):
        return anomalies, None

    # --- lecture ----------------------------------------------------------
    champ_nom = _champ_nom(valeurs)
    try:
        g_sec = geo.lire_lignes(p_sections, colonne_nom=champ_nom,
                                prefixe_defaut="Section")
        g_app = geo.lire_lignes(p_apports, colonne_nom=champ_nom,
                                prefixe_defaut="Apport")
    except Exception as e:
        anomalies.append((ERREUR, f"lecture des shapefiles : {e}"))
        return anomalies, None

    axe, crs_ref, lues = _lire_axe(p_axe, g_sec)
    anomalies += lues

    # --- controles SIG ----------------------------------------------------
    anomalies += geo.controler_shp(g_sec, "sections de controle", crs_ref,
                                   exiger_croisement=axe is not None, axe=axe)
    anomalies += geo.controler_shp(g_app, "lignes d'injection", crs_ref)

    # --- confrontation des noms au template -------------------------------
    try:
        noms_sections, noms_apports = _correspondance(chemin_template)
    except Exception as e:
        anomalies.append((ERREUR, f"feuille Correspondance illisible : {e}"))
        return anomalies, None

    noms_absents, absences = _regle_noms_dans_shp(noms_sections, noms_apports,
                                                  g_sec, g_app)
    anomalies += absences

    empechements = _regle_pk_calculables(axe, noms_absents, g_sec, g_app)
    if empechements:
        return anomalies + empechements, None

    # --- PK et coherence geographique -------------------------------------
    # Cle absente ou texte vide : le defaut. Valeur NULLE : elle manque, et
    # str(None) ferait lire « 'None' » a l'ingenieur.
    sens = valeurs.get("Sens_axe", "amont_aval")
    if sens is None or (isinstance(sens, float) and pd.isna(sens)):
        sens = None
    else:
        sens = str(sens).strip() or "amont_aval"
    refus = _regle_sens_axe(sens)
    if refus:
        return anomalies + refus, None

    pk_origine, refus = _pk_origine(valeurs)
    if refus:
        return anomalies + refus, None

    g_sec = geo.calculer_pk(g_sec, axe, pk_origine=pk_origine, sens=sens)
    g_app = geo.calculer_pk(g_app, axe, pk_origine=pk_origine, sens=sens)
    pk_sec = dict(zip(g_sec["nom"], g_sec["pk_m"]))
    pk_app = dict(zip(g_app["nom"], g_app["pk_m"]))

    anomalies += geo.verifier_ordre(noms_sections, pk_sec)
    anomalies += geo.verifier_position_apports(
        list(zip(noms_apports, noms_sections)), pk_app, pk_sec)

    return anomalies, _tableau_pk(noms_sections, noms_apports, pk_sec, pk_app)


def geometrie_hdf(chemin_template):
    """
    Chemin du fichier HDF de geometrie, deduit des parametres du template :
    <Dossier_projet_HECRAS>/<Nom_projet>.<Geometrie_reference>.hdf

    Retourne (chemin, anomalies). chemin vaut None si les parametres ne
    permettent pas de le construire ou si le fichier n'existe pas.
    """
    anomalies = []
    valeurs = parametres.lire(chemin_template)

    def lire(cle):
        v = valeurs.get(cle)
        return None if v is None or pd.isna(v) or not str(v).strip() else str(v).strip()

    dossier, projet = lire("Dossier_projet_HECRAS"), lire("Nom_projet")
    geometrie = lire("Geometrie_reference")
    manquants = [c for c, v in [("Dossier_projet_HECRAS", dossier),
                                ("Nom_projet", projet),
                                ("Geometrie_reference", geometrie)] if v is None]
    if manquants:
        return None, [(AVERTISSEMENT,
                       f"controle contre le modele non effectue : parametre(s) "
                       f"{manquants} non renseigne(s)")]

    # "g01", "01" ou ".g01" designent le meme fichier.
    suffixe = geometrie.lstrip(".")
    if not suffixe.startswith("g"):
        suffixe = "g" + suffixe.zfill(2)
    chemin = Path(dossier) / f"{projet}.{suffixe}.hdf"
    if not chemin.exists():
        return None, [(ERREUR, f"geometrie introuvable : {chemin}")]
    return chemin, anomalies


# ---------------------------------------------------------------------------
# Regles du controle contre le modele, enchainees par controler_contre_modele.
# ---------------------------------------------------------------------------

def _regle_zone_2d(chemin_template, chemin_geometrie_hdf):
    """
    (zone_declaree, anomalies) : la zone 2D declaree existe-t-elle ? Une zone
    absente est rendue None, pour que le perimetre ne soit pas filtre sur
    elle.
    """
    import geometrie as geo

    valeurs = parametres.lire(chemin_template)
    zone_declaree = valeurs.get("Nom_zone_2D")
    zone_declaree = (str(zone_declaree).strip()
                     if zone_declaree is not None and not pd.isna(zone_declaree)
                     else None)

    zones_presentes = geo.zones_2d(chemin_geometrie_hdf)
    if zone_declaree and zone_declaree not in zones_presentes:
        return None, [(
            ERREUR,
            f"zone d'ecoulement 2D '{zone_declaree}' absente de la geometrie "
            f"(presentes : {zones_presentes})")]
    if not zone_declaree and len(zones_presentes) > 1:
        return zone_declaree, [(
            AVERTISSEMENT,
            f"Nom_zone_2D non renseigne et le modele en comporte plusieurs "
            f"{zones_presentes} : la premiere est retenue par defaut.")]
    return zone_declaree, []


def _noms_des_lignes(gdf):
    """Noms portes par une couche de lignes lue dans le HDF."""
    import geometrie as geo

    if gdf is None or len(gdf) == 0:
        return set()
    colonne = next((c for c in gdf.columns if c in geo.COLONNES_NOM), None)
    return set(gdf[colonne].astype(str)) if colonne else set()


def _ajouter_noms_du_texte(chemin_geometrie_hdf, presents):
    """
    Complete « presents » par les objets du fichier texte .gXX, et rend ceux
    qui n'y figuraient pas encore (ecrits, pas encore pretraites).
    """
    import geometrie as geo

    # LE FICHIER TEXTE FAIT FOI. Le .gXX.hdf lu ci-dessus est le produit d'un
    # PRETRAITEMENT : un objet qu'on vient d'ecrire dans le .gXX n'y figure
    # pas tant que HEC-RAS n'a pas repretraite la geometrie. S'en tenir au
    # HDF revenait a declarer absents des objets qui viennent d'etre crees,
    # et a bloquer un paquet parfaitement valide.
    texte = Path(chemin_geometrie_hdf).with_suffix("")   # .gXX.hdf -> .gXX
    en_attente = set()
    if texte.exists():
        du_texte = geo.objets_depuis_texte(texte)
        for libelle, cle in (("ligne d'injection", "apports"),
                             ("section de controle", "sections")):
            noms_texte = {o["nom"] for o in du_texte[cle]}
            en_attente |= noms_texte - presents[libelle]
            presents[libelle] |= noms_texte
    return en_attente


def _regle_noms_dans_modele(presents, noms_sections, noms_apports):
    anomalies = []
    for libelle, declares in [("ligne d'injection", noms_apports),
                              ("section de controle", noms_sections)]:
        disponibles = presents[libelle]
        for nom in declares:
            if nom not in disponibles:
                anomalies.append((
                    ERREUR,
                    f"{libelle} '{nom}' absente de la geometrie. "
                    + (f"Presentes : {sorted(disponibles)}." if disponibles
                       else "La geometrie n'en contient aucune — les creer "
                            "avant de lancer le calage.")))
    return anomalies


def _regle_en_attente_de_pretraitement(en_attente, noms_sections, noms_apports):
    # Signale, sans bloquer, ce qui est ecrit mais pas encore pretraite : le
    # premier calcul s'en chargera, mais il vaut mieux que l'utilisateur le
    # sache que de le laisser s'interroger.
    declares_tous = set(noms_sections) | set(noms_apports)
    concernes = sorted(en_attente & declares_tous)
    if concernes:
        return [(
            INFO,
            f"ecrits dans la geometrie mais pas encore pretraites par "
            f"HEC-RAS : {concernes}. Ils seront pris en compte au prochain "
            f"calcul ; rien a faire.")]
    return []


def _perimetre_zone(zones, zone_declaree):
    """
    (perimetre, anomalies) du maillage lu dans le HDF. Une anomalie rendue
    signifie que le perimetre manque : l'implantation n'est pas controlee.
    """
    if zones is None or len(zones) == 0:
        return None, [(AVERTISSEMENT, "aucune zone 2D dans la geometrie")]

    # Sur un modele multi-zones, ne retenir que celle qui est declaree :
    # unir tous les perimetres donnerait une emprise qui n'existe pas.
    if zone_declaree and "mesh_name" in zones.columns:
        zones = zones[zones["mesh_name"].astype(str) == zone_declaree]
        if len(zones) == 0:
            return None, [(AVERTISSEMENT,
                           f"perimetre de la zone '{zone_declaree}' introuvable")]

    perimetre = zones.geometry.union_all() if hasattr(zones.geometry, "union_all") \
        else zones.geometry.unary_union
    return perimetre, []


def _tolerance_locale(chemin_geometrie_hdf, zone_declaree):
    """Ecart admis au perimetre, fonction de la geometrie ; None si la taille
    de maille est illisible."""
    import geometrie as geo

    # La tolerance geometrique se mesure en tailles de maille, jamais en
    # metres absolus, et LOCALEMENT : sur un maillage raffine par zones, le lit
    # peut etre a 3 m et la plaine a 25 m. Une tolerance batie sur la mediane
    # globale serait beaucoup trop severe en bordure de domaine, ou se
    # trouvent precisement les conditions limites.
    try:
        # SONDE, ET NON UNE VALEUR : son resultat ne sert a rien, son ECHEC
        # si. Elle etablit que la taille de maille est lisible pour cette zone
        # AVANT qu'on ne confie « tolerance » a
        # geo.controler_contre_maillage, qui l'appelle par geometrie et SANS
        # protection (« admis = tolerance_m(g) »). Sans elle, un
        # maillage illisible ne donnerait plus tolerance=None — le repli
        # prevu, ou le controle se contente de RAPPORTER la distance — mais
        # une exception remontee au milieu du controle.
        #   Elle portait un nom, « maille_globale », que personne ne lisait :
        # ruff le signalait en F841 et l'effacer aurait emporte la sonde avec.
        geo.taille_maille(chemin_geometrie_hdf, zone_declaree)

        def tolerance(g):
            return TOLERANCE_EN_MAILLES * geo.taille_maille(
                chemin_geometrie_hdf, zone_declaree, geometrie=g)
    except Exception:
        tolerance = None
    return tolerance


def _regle_bc_externes_au_perimetre(bc, perimetre, tolerance):
    # Seules les conditions limites EXTERNES doivent longer le perimetre ;
    # une condition interne est par definition ailleurs.
    if bc is None or not len(bc) or "Type" not in bc.columns:
        return []
    externes = bc[bc["Type"].astype(str).str.strip().str.lower() == "external"]
    if not len(externes):
        return []

    import geopandas as gpd

    import geometrie as geo

    colonne = next((c for c in externes.columns if c in geo.COLONNES_NOM),
                   None)
    g_ext = gpd.GeoDataFrame(
        {"nom": externes[colonne].astype(str) if colonne
                else [f"BC_{i}" for i in range(len(externes))]},
        geometry=list(externes.geometry), crs=externes.crs)
    return geo.controler_contre_maillage(
        g_ext, "lignes d'injection externes", perimetre,
        doit_etre_interieur=False, tolerance_m=tolerance)


def controler_contre_modele(chemin_template, chemin_geometrie_hdf=None):
    """
    Confronte la saisie a la geometrie REELLE du modele. Deux controles que
    rien d'autre ne peut faire, et qui sont la source d'erreur la plus
    frequente s'ils ne sont pas faits avant le premier calcul :

      1. chaque nom declare existe-t-il vraiment dans la geometrie ?
      2. les lignes sont-elles correctement implantees vis-a-vis du maillage —
         sections interieures a la zone 2D, injections externes touchant son
         perimetre ?

    NECESSITE ras-commander, donc INUTILISABLE dans le processus QGIS : passer
    par pont_hecras.py. Voir la note methodologique, § 2.4.

    Retourne une liste (niveau, message).
    """
    from ras_commander import HdfBndry, HdfMesh

    import geometrie as geo

    anomalies = []
    if chemin_geometrie_hdf is None:
        chemin_geometrie_hdf, anomalies = geometrie_hdf(chemin_template)
        if chemin_geometrie_hdf is None:
            return anomalies

    # --- 0. la zone 2D declaree existe-t-elle ? ---------------------------
    zone_declaree, constats = _regle_zone_2d(chemin_template,
                                             chemin_geometrie_hdf)
    anomalies += constats

    # --- 1. existence des noms declares -----------------------------------
    presents = {
        "ligne d'injection": _noms_des_lignes(
            HdfBndry.get_bc_lines(chemin_geometrie_hdf)),
        "section de controle": _noms_des_lignes(
            HdfBndry.get_reference_lines(chemin_geometrie_hdf)),
    }
    en_attente = _ajouter_noms_du_texte(chemin_geometrie_hdf, presents)

    try:
        noms_sections, noms_apports = _correspondance(chemin_template)
    except ValueError as e:
        # Comme controler_geometrie, qui rend la meme anomalie.
        return anomalies + [(ERREUR,
                             f"feuille Correspondance illisible : {e}")]
    anomalies += _regle_noms_dans_modele(presents, noms_sections, noms_apports)
    anomalies += _regle_en_attente_de_pretraitement(en_attente, noms_sections,
                                                    noms_apports)

    # --- 2. implantation vis-a-vis du maillage ----------------------------
    try:
        zones = HdfMesh.get_mesh_areas(chemin_geometrie_hdf)
    except Exception as e:
        anomalies.append((AVERTISSEMENT,
                          f"perimetre de la zone 2D illisible : {e}"))
        return anomalies
    perimetre, manques = _perimetre_zone(zones, zone_declaree)
    if manques:
        return anomalies + manques

    tolerance = _tolerance_locale(chemin_geometrie_hdf, zone_declaree)

    g_sec, _ = geo.lignes_depuis_modele(chemin_geometrie_hdf)
    if len(g_sec):
        anomalies += geo.controler_contre_maillage(
            g_sec, "sections de controle", perimetre, doit_etre_interieur=True)

    anomalies += _regle_bc_externes_au_perimetre(
        HdfBndry.get_bc_lines(chemin_geometrie_hdf), perimetre, tolerance)

    return anomalies


def afficher(anomalies, titre="Controle des donnees d'entree"):
    """Imprime les anomalies et retourne True si aucune n'est bloquante."""
    print(f"\n{titre}")
    print("-" * len(titre))
    if not anomalies:
        print("  Aucune anomalie : les donnees peuvent etre exploitees.")
        return True
    erreurs = [a for a in anomalies if a[0] == ERREUR]
    informations = [a for a in anomalies if a[0] == INFO]
    for niveau, message in anomalies:
        print(f"  [{niveau:13s}] {message}")
    print(f"\n  -> {len(erreurs)} erreur(s), "
          f"{len(anomalies) - len(erreurs) - len(informations)} "
          f"avertissement(s)")
    return not erreurs


# ---------------------------------------------------------------------------
# Auto-test : on fabrique un template volontairement fautif et on verifie que
# chaque anomalie est bien detectee.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        chemin = Path(sys.argv[1])
        ok = afficher(controler_template(chemin), f"Controle de {chemin.name}")
        sys.exit(0 if ok else 1)

    # Le banc vit dans src/bancs/ depuis le 10/11/2026 : l'archive du plugin
    # ne l'embarque pas. Dans le depot, ce relais le joue a l'identique.
    import runpy
    from pathlib import Path

    _banc = (Path(__file__).resolve().parent / "bancs"
             / "banc_controle_donnees.py")
    if not _banc.is_file():
        print("Le banc d'auto-test n'est pas livre avec cette installation.",
              file=sys.stderr)
        raise SystemExit(2)
    runpy.run_path(str(_banc), run_name="__main__")
