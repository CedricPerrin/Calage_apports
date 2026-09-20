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

from pathlib import Path

import numpy as np
import pandas as pd

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
    from pilote_hecras import valider_fenetre_simulation

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
    feuilles = pd.read_excel(chemin, sheet_name=None)
    manquantes = {"Parametres", "Correspondance", "Cibles"} - set(feuilles)
    if manquantes:
        raise ValueError(f"feuilles absentes du classeur : {sorted(manquantes)}")
    return feuilles


def controler_template(chemin):
    """
    Valide le classeur de saisie. Retourne une liste de couples
    (niveau, message). Une liste vide signifie que rien ne s'oppose au
    lancement du calage.
    """
    anomalies = []

    def erreur(msg):
        anomalies.append((ERREUR, msg))

    def avertir(msg):
        anomalies.append((AVERTISSEMENT, msg))

    try:
        feuilles = _lire(chemin)
    except Exception as e:
        return [(ERREUR, f"classeur illisible : {e}")]

    # --- 1. Parametres -----------------------------------------------------
    par = feuilles["Parametres"]
    if {"Parametre", "Valeur"} <= set(par.columns):
        valeurs = dict(zip(par["Parametre"], par["Valeur"]))
    else:
        valeurs = {}
        erreur("feuille Parametres : colonnes 'Parametre' et 'Valeur' attendues")

    for cle in PARAMETRES_REQUIS:
        if cle not in valeurs or pd.isna(valeurs.get(cle)):
            erreur(f"parametre manquant ou vide : {cle}")

    nb_max = valeurs.get("Nb_max_iterations_par_apport")
    if isinstance(nb_max, (int, float)) and nb_max < 3:
        erreur(f"Nb_max_iterations_par_apport = {nb_max} : au moins 3 essais "
               f"sont necessaires pour que la correction converge")

    # Fenetre de simulation : facultative, mais si elle est saisie elle doit
    # etre juste. Une date mal formee n'est pas refusee par HEC-RAS — elle est
    # lue autrement, et le calcul tourne sur une periode qui n'est pas celle
    # des hydrogrammes. La verifier ici coute une seconde ; s'en apercevoir
    # apres coup coute une campagne de calculs.
    _controler_fenetre_simulation(valeurs, erreur)

    # --- 2. Correspondance -------------------------------------------------
    corr = feuilles["Correspondance"]
    col_ordre = "Ordre"
    col_apport = next((c for c in corr.columns if c.startswith("Nom_Apport")), None)
    col_section = next((c for c in corr.columns if c.startswith("Nom_Section")), None)
    col_cible = next((c for c in corr.columns if c.startswith("Nom_Cible")), None)

    if not all([col_ordre in corr.columns, col_apport, col_section, col_cible]):
        erreur("feuille Correspondance : colonnes Ordre / Nom_Apport / "
               "Nom_Section / Nom_Cible attendues")
        return anomalies

    corr = corr.dropna(subset=[col_ordre, col_apport, col_section, col_cible])
    n = len(corr)
    if n == 0:
        erreur("feuille Correspondance : aucune station renseignee")
        return anomalies

    ordres = sorted(int(o) for o in corr[col_ordre])
    if ordres != list(range(1, n + 1)):
        erreur(f"colonne Ordre : doit etre la suite 1..{n} sans trou ni doublon "
               f"(valeurs lues : {ordres})")

    for col, libelle in [(col_apport, "apport"), (col_section, "section")]:
        doublons = corr[col][corr[col].duplicated()].tolist()
        if doublons:
            erreur(f"nom de {libelle} en doublon : {doublons}. Chaque "
                   f"{libelle} doit etre unique — une inconnue par contrainte.")

    # LE PREFIXE SE JUGE SUR LES NOMS D'APPORT REELS : il est donc controle
    # ici, et non a la section 1, qui ne les connait pas encore.
    # DANS L'ORDRE DECLARE : _controler_prefixe_scenario exclut le premier
    # apport, qui seul ne donne pas de titre de reprise. L'ordre des lignes
    # de la feuille n'est pas force d'etre celui de la colonne Ordre.
    _controler_prefixe_scenario(
        valeurs,
        [str(a) for a in corr.sort_values(col_ordre)[col_apport]],
        erreur)

    # --- 3. Cibles ---------------------------------------------------------
    cib = feuilles["Cibles"]
    if "Temps_h" not in cib.columns:
        erreur("feuille Cibles : colonne 'Temps_h' absente")
        return anomalies

    temps = pd.to_numeric(cib["Temps_h"], errors="coerce").dropna().to_numpy()
    if len(temps) < 10:
        avertir(f"feuille Cibles : seulement {len(temps)} pas de temps. "
                f"Un hydrogramme trop grossier fausse le volume et le debit "
                f"de pointe compares a la cible.")
    if len(temps) > 1 and not np.all(np.diff(temps) > 0):
        erreur("feuille Cibles : la colonne Temps_h doit etre strictement "
               "croissante")

    cibles_declarees = set(corr[col_cible].astype(str))
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
    cibles_presentes = {c for c in cib.columns
                        if isinstance(c, str) and not c.startswith("Unnamed:")
                        } - reserves
    absentes = cibles_declarees - cibles_presentes
    if absentes:
        erreur(f"cibles declarees dans Correspondance mais absentes de la "
               f"feuille Cibles : {sorted(absentes)}")
    inutilisees = cibles_presentes - cibles_declarees
    if inutilisees:
        avertir(f"colonnes de la feuille Cibles jamais utilisees : "
                f"{sorted(inutilisees)}")

    for nom in sorted(cibles_declarees & cibles_presentes):
        serie = pd.to_numeric(cib[nom], errors="coerce")
        valides = serie.dropna()
        # Colonne entierement vide : le template n'est pas encore rempli, ce
        # qui est un etat normal et non une donnee fautive.
        if len(valides) == 0:
            avertir(f"cible '{nom}' : colonne vide, a renseigner avant le calage")
            continue
        if len(valides) < 2:
            erreur(f"cible '{nom}' : pas assez de valeurs numeriques "
                   f"({len(valides)} valeur exploitable)")
            continue
        if (valides < 0).any():
            erreur(f"cible '{nom}' : contient des debits negatifs")
        if float(valides.max()) <= 0:
            erreur(f"cible '{nom}' : hydrogramme identiquement nul")
        if serie.isna().sum() > 0 and serie.dropna().index.max() < len(serie) - 1:
            avertir(f"cible '{nom}' : valeurs manquantes intercalees")

    return anomalies


def _correspondance(chemin_template):
    """Lit la feuille Correspondance et retourne (noms_sections, noms_apports)
    dans l'ordre declare."""
    corr = pd.read_excel(chemin_template, sheet_name="Correspondance")
    col_ordre = "Ordre"
    col_apport = next(c for c in corr.columns if c.startswith("Nom_Apport"))
    col_section = next(c for c in corr.columns if c.startswith("Nom_Section"))
    corr = corr.dropna(subset=[col_ordre, col_apport, col_section])
    corr = corr.sort_values(col_ordre)
    return (corr[col_section].astype(str).tolist(),
            corr[col_apport].astype(str).tolist())


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

    anomalies, tableau = [], None
    try:
        par = pd.read_excel(chemin_template, sheet_name="Parametres")
        valeurs = dict(zip(par["Parametre"], par["Valeur"]))
    except Exception as e:
        return [(ERREUR, f"feuille Parametres illisible : {e}")], None

    def chemin(cle):
        v = valeurs.get(cle)
        return None if v is None or pd.isna(v) or not str(v).strip() else Path(str(v))

    p_sections, p_apports = chemin("Fichier_SHP_Sections"), chemin("Fichier_SHP_Apports")
    p_axe = chemin(PARAMETRE_AXE)

    for cle, p in [("Fichier_SHP_Sections", p_sections),
                   ("Fichier_SHP_Apports", p_apports),
                   (PARAMETRE_AXE, p_axe)]:
        if p is not None and not p.exists():
            anomalies.append((ERREUR, f"{cle} : fichier introuvable -> {p}"))

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
        return anomalies, None

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
    # Champ_nom_SHP : vide ou absent = detection automatique du champ de nom.
    champ_nom = valeurs.get("Champ_nom_SHP")
    champ_nom = (str(champ_nom).strip()
                 if champ_nom is not None and not pd.isna(champ_nom)
                 and str(champ_nom).strip() else None)
    try:
        g_sec = geo.lire_lignes(p_sections, colonne_nom=champ_nom,
                                prefixe_defaut="Section")
        g_app = geo.lire_lignes(p_apports, colonne_nom=champ_nom,
                                prefixe_defaut="Apport")
    except Exception as e:
        anomalies.append((ERREUR, f"lecture des shapefiles : {e}"))
        return anomalies, None

    axe = crs_ref = None
    if p_axe is not None:
        try:
            axe, crs_ref = geo.lire_axe(p_axe)
        except Exception as e:
            anomalies.append((ERREUR, f"lecture de l'axe hydraulique : {e}"))
    else:
        anomalies.append((
            AVERTISSEMENT,
            f"{PARAMETRE_AXE} non renseigne : pas de PK, donc ni verification "
            f"de l'ordre declare ni profil en long. Fournir l'axe hydraulique "
            f"en polyligne est vivement recommande."))
        crs_ref = g_sec.crs

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

    noms_absents = []
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
    if axe is None or noms_absents or doublons:
        raisons = ["axe hydraulique indisponible"] if axe is None else []
        if noms_absents:
            raisons.append(f"noms declares absents des shapefiles : "
                           f"{noms_absents}")
        if doublons:
            raisons.append(f"noms en doublon dans les shapefiles : {doublons}")
        anomalies.append((
            AVERTISSEMENT,
            f"PK non calculables ({' ; '.join(raisons)}) : ni ordre declare "
            f"verifie, ni profil en long, ni pente locale deduite."))
        return anomalies, None

    # --- PK et coherence geographique -------------------------------------
    sens = str(valeurs.get("Sens_axe", "amont_aval")).strip() or "amont_aval"
    if sens not in ("amont_aval", "aval_amont"):
        anomalies.append((
            ERREUR,
            f"Sens_axe = '{sens}' : valeurs admises ['amont_aval', "
            f"'aval_amont']."))
        return anomalies, None

    pk_origine = valeurs.get("PK_origine_m", 0)
    try:
        pk_origine = 0.0 if pd.isna(pk_origine) else float(pk_origine)
    except (TypeError, ValueError):
        anomalies.append((
            ERREUR, f"PK_origine_m = '{pk_origine}' : un nombre est attendu."))
        return anomalies, None

    g_sec = geo.calculer_pk(g_sec, axe, pk_origine=pk_origine, sens=sens)
    g_app = geo.calculer_pk(g_app, axe, pk_origine=pk_origine, sens=sens)
    pk_sec = dict(zip(g_sec["nom"], g_sec["pk_m"]))
    pk_app = dict(zip(g_app["nom"], g_app["pk_m"]))

    anomalies += geo.verifier_ordre(noms_sections, pk_sec)
    anomalies += geo.verifier_position_apports(
        list(zip(noms_apports, noms_sections)), pk_app, pk_sec)

    tableau = pd.DataFrame({
        "Ordre": range(1, len(noms_sections) + 1),
        "Section": noms_sections,
        "PK section (m)": [round(pk_sec[n], 1) for n in noms_sections],
        "Apport": noms_apports,
        "PK apport (m)": [round(pk_app[n], 1) for n in noms_apports],
    })
    tableau["Distance apport-section (m)"] = (
        tableau["PK section (m)"] - tableau["PK apport (m)"]).round(1)
    return anomalies, tableau


def geometrie_hdf(chemin_template):
    """
    Chemin du fichier HDF de geometrie, deduit des parametres du template :
    <Dossier_projet_HECRAS>/<Nom_projet>.<Geometrie_reference>.hdf

    Retourne (chemin, anomalies). chemin vaut None si les parametres ne
    permettent pas de le construire ou si le fichier n'existe pas.
    """
    anomalies = []
    par = pd.read_excel(chemin_template, sheet_name="Parametres")
    valeurs = dict(zip(par["Parametre"], par["Valeur"]))

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
    par = pd.read_excel(chemin_template, sheet_name="Parametres")
    valeurs = dict(zip(par["Parametre"], par["Valeur"]))
    zone_declaree = valeurs.get("Nom_zone_2D")
    zone_declaree = (str(zone_declaree).strip()
                     if zone_declaree is not None and not pd.isna(zone_declaree)
                     else None)

    zones_presentes = geo.zones_2d(chemin_geometrie_hdf)
    if zone_declaree and zone_declaree not in zones_presentes:
        anomalies.append((
            ERREUR,
            f"zone d'ecoulement 2D '{zone_declaree}' absente de la geometrie "
            f"(presentes : {zones_presentes})"))
        zone_declaree = None
    elif not zone_declaree and len(zones_presentes) > 1:
        anomalies.append((
            AVERTISSEMENT,
            f"Nom_zone_2D non renseigne et le modele en comporte plusieurs "
            f"{zones_presentes} : la premiere est retenue par defaut."))

    # --- 1. existence des noms declares -----------------------------------
    def noms_de(gdf):
        if gdf is None or len(gdf) == 0:
            return set()
        colonne = next((c for c in gdf.columns if c in geo.COLONNES_NOM), None)
        return set(gdf[colonne].astype(str)) if colonne else set()

    presents = {
        "ligne d'injection": noms_de(HdfBndry.get_bc_lines(chemin_geometrie_hdf)),
        "section de controle": noms_de(
            HdfBndry.get_reference_lines(chemin_geometrie_hdf)),
    }

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

    noms_sections, noms_apports = _correspondance(chemin_template)
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

    # Signale, sans bloquer, ce qui est ecrit mais pas encore pretraite : le
    # premier calcul s'en chargera, mais il vaut mieux que l'utilisateur le
    # sache que de le laisser s'interroger.
    declares_tous = set(noms_sections) | set(noms_apports)
    concernes = sorted(en_attente & declares_tous)
    if concernes:
        anomalies.append((
            INFO,
            f"ecrits dans la geometrie mais pas encore pretraites par "
            f"HEC-RAS : {concernes}. Ils seront pris en compte au prochain "
            f"calcul ; rien a faire."))

    # --- 2. implantation vis-a-vis du maillage ----------------------------
    try:
        zones = HdfMesh.get_mesh_areas(chemin_geometrie_hdf)
    except Exception as e:
        anomalies.append((AVERTISSEMENT,
                          f"perimetre de la zone 2D illisible : {e}"))
        return anomalies
    if zones is None or len(zones) == 0:
        anomalies.append((AVERTISSEMENT, "aucune zone 2D dans la geometrie"))
        return anomalies

    # Sur un modele multi-zones, ne retenir que celle qui est declaree :
    # unir tous les perimetres donnerait une emprise qui n'existe pas.
    if zone_declaree and "mesh_name" in zones.columns:
        zones = zones[zones["mesh_name"].astype(str) == zone_declaree]
        if len(zones) == 0:
            anomalies.append((AVERTISSEMENT,
                              f"perimetre de la zone '{zone_declaree}' introuvable"))
            return anomalies

    perimetre = zones.geometry.union_all() if hasattr(zones.geometry, "union_all") \
        else zones.geometry.unary_union

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

    g_sec, _ = geo.lignes_depuis_modele(chemin_geometrie_hdf)
    if len(g_sec):
        anomalies += geo.controler_contre_maillage(
            g_sec, "sections de controle", perimetre, doit_etre_interieur=True)

    # Seules les conditions limites EXTERNES doivent longer le perimetre ;
    # une condition interne est par definition ailleurs.
    bc = HdfBndry.get_bc_lines(chemin_geometrie_hdf)
    if bc is not None and len(bc) and "Type" in bc.columns:
        externes = bc[bc["Type"].astype(str).str.strip().str.lower() == "external"]
        if len(externes):
            import geopandas as gpd

            colonne = next((c for c in externes.columns if c in geo.COLONNES_NOM),
                           None)
            g_ext = gpd.GeoDataFrame(
                {"nom": externes[colonne].astype(str) if colonne
                        else [f"BC_{i}" for i in range(len(externes))]},
                geometry=list(externes.geometry), crs=externes.crs)
            anomalies += geo.controler_contre_maillage(
                g_ext, "lignes d'injection externes", perimetre,
                doit_etre_interieur=False, tolerance_m=tolerance)

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
    import tempfile

    if len(sys.argv) > 1:
        chemin = Path(sys.argv[1])
        ok = afficher(controler_template(chemin), f"Controle de {chemin.name}")
        sys.exit(0 if ok else 1)

    dossier = Path(__file__).parent
    reference = dossier.parent / "template_donnees_calage.xlsx"

    print("=" * 70)
    print("AUTO-TEST DU CONTROLE DES DONNEES")
    print("=" * 70)

    print("\n1. Template de reference, vierge")
    afficher(controler_template(reference), "Template livre avec le projet")

    print("\n2. Template volontairement fautif")
    tmp = Path(tempfile.gettempdir()) / "template_fautif.xlsx"
    with pd.ExcelWriter(tmp, engine="openpyxl") as w:
        pd.DataFrame({
            "Parametre": ["Dossier_projet_HECRAS", "Nom_projet",
                          "Nb_max_iterations_par_apport",
                          # Date au format francais : l'erreur de saisie la
                          # plus probable, et la plus silencieuse.
                          "Simulation_debut", "Simulation_fin"],
            "Valeur": [r"D:\projet", "Essai", 2,
                       "13/10/2014 00:00", "14OCT2014,04:00"],
        }).to_excel(w, sheet_name="Parametres", index=False)
        pd.DataFrame({
            "Ordre": [1, 2, 4],
            "Nom_Apport (BC line)": ["A1", "A2", "A2"],
            "Nom_Section (reference line)": ["S1", "S2", "S3"],
            "Nom_Cible": ["C1", "C2", "C_absente"],
        }).to_excel(w, sheet_name="Correspondance", index=False)
        pd.DataFrame({
            "Temps_h": [0, 2, 1, 6],
            "C1": [1, 5, 3, 1],
            "C2": [1, -8, 3, 1],
            "C_inutile": [1, 2, 3, 4],
        }).to_excel(w, sheet_name="Cibles", index=False)

    afficher(controler_template(tmp), "Template fautif (8 anomalies attendues)")

    print("\n2 bis. Prefixe de scenario et longueur des titres de plan")
    # « Riviere1-Q100 » (13) donne « Riviere1-Q100_Apport_APP06 » : 26
    # caracteres, l'exemple exact de la demande — il doit PASSER.
    # Les trois premieres lignes prouvent que le controle ne crie pas a tort —
    # un garde-fou qui se declenche sans raison apprend a etre ignore.
    #
    # LE DERNIER EST LA REGRESSION DU 20 SEPTEMBRE 2026. Vingt-deux
    # caracteres : tous les titres « <prefixe>_Apport_APP07 » tiennent (35),
    # mais le titre de reprise « <prefixe>_sans APP07 et aval » fait 41 pour
    # 40 tenables. Avant le correctif, ce classeur passait le controle avec
    # « Premier_apport » vide — la valeur ne s'ecrit qu'au lancement — et le
    # calage etait refuse ensuite, une fois lance.
    tmp_prefixe = Path(tempfile.gettempdir()) / "template_prefixe.xlsx"
    _echecs_prefixe = []
    for prefixe, refus_attendu in (("", False), ("Q100", False),
                                   ("Riviere1-Q100", False),
                                   ("Riviere1_Q100_1000_ABC", True)):
        with pd.ExcelWriter(tmp_prefixe, engine="openpyxl") as w:
            pd.DataFrame({
                "Parametre": ["Dossier_projet_HECRAS", "Nom_projet",
                              "Nom_zone_2D", "Nb_max_iterations_par_apport",
                              "Prefixe_scenario"],
                "Valeur": [r"D:\projet", "Essai", "Perimeter 1", 6, prefixe],
            }).to_excel(w, sheet_name="Parametres", index=False)
            pd.DataFrame({
                "Ordre": [1, 2],
                "Nom_Apport (BC line)": ["APP06", "APP07"],
                "Nom_Section (reference line)": ["S1", "S2"],
                "Nom_Cible": ["C1", "C2"],
            }).to_excel(w, sheet_name="Correspondance", index=False)
            pd.DataFrame({"Temps_h": list(range(11)),
                          "C1": list(range(11)),
                          "C2": list(range(11))}
                         ).to_excel(w, sheet_name="Cibles", index=False)
        vu = any(niveau == ERREUR and "Prefixe_scenario" in message
                 for niveau, message in controler_template(tmp_prefixe))
        juste = vu == refus_attendu
        print(f"   [{'OK' if juste else 'ECHEC'}] "
              f"prefixe {prefixe!r:22s} -> {'refuse' if vu else 'accepte'} "
              f"(attendu : {'refuse' if refus_attendu else 'accepte'})")
        if not juste:
            _echecs_prefixe.append(prefixe)
    if _echecs_prefixe:
        raise SystemExit(f"{len(_echecs_prefixe)} ECHEC(S) sur le prefixe : "
                         f"{_echecs_prefixe}")

    # --- 3. Chaine SIG ----------------------------------------------------
    print("\n3. CHAINE SIG : shapefiles, PK et coherence geographique")
    import geopandas as gpd
    from shapely.geometry import LineString

    dossier_shp = Path(tempfile.gettempdir()) / "calage_shp_test"
    dossier_shp.mkdir(exist_ok=True)
    CRS = "EPSG:2154"

    xs = np.linspace(0, 8000, 60)
    axe_geom = LineString(zip(500000 + xs, 6200000 + 300 * np.sin(xs / 1400)))
    gpd.GeoDataFrame({"Nom": ["Axe"]}, geometry=[axe_geom], crs=CRS).to_file(
        dossier_shp / "axe.shp")

    def transversale(xl, demi=400.0):
        y = 300 * np.sin(xl / 1400)
        return LineString([(500000 + xl, 6200000 + y - demi),
                           (500000 + xl, 6200000 + y + demi)])

    noms_s = ["S1", "S2", "S3", "S4"]
    gpd.GeoDataFrame({"Nom": noms_s},
                     geometry=[transversale(x) for x in (900, 2800, 5100, 7400)],
                     crs=CRS).to_file(dossier_shp / "sections.shp")
    noms_a = ["A1", "A2", "A3", "A4"]
    gpd.GeoDataFrame({"Nom": noms_a},
                     geometry=[transversale(x, 250) for x in (200, 2100, 4300, 6600)],
                     crs=CRS).to_file(dossier_shp / "apports.shp")

    def template_sig(chemin, ordre_sections, nom_apport_1="A1"):
        with pd.ExcelWriter(chemin, engine="openpyxl") as w:
            pd.DataFrame({
                "Parametre": ["Dossier_projet_HECRAS", "Nom_projet", "Nom_zone_2D",
                              "Nb_max_iterations_par_apport",
                              "Fichier_SHP_Sections", "Fichier_SHP_Apports",
                              "Fichier_SHP_Axe", "Sens_axe"],
                "Valeur": [r"D:\projet", "Essai", "Zone2D", 6,
                           str(dossier_shp / "sections.shp"),
                           str(dossier_shp / "apports.shp"),
                           str(dossier_shp / "axe.shp"), "amont_aval"],
            }).to_excel(w, sheet_name="Parametres", index=False)
            pd.DataFrame({
                "Ordre": [1, 2, 3, 4],
                "Nom_Apport (BC line)": [nom_apport_1] + noms_a[1:],
                "Nom_Section (reference line)": ordre_sections,
                "Nom_Cible": ["C1", "C2", "C3", "C4"],
            }).to_excel(w, sheet_name="Correspondance", index=False)
            pd.DataFrame({"Temps_h": [0, 1, 2, 3],
                          "C1": [1, 5, 3, 1], "C2": [1, 6, 3, 1],
                          "C3": [1, 7, 3, 1], "C4": [1, 8, 3, 1]}
                         ).to_excel(w, sheet_name="Cibles", index=False)

    t_ok = dossier_shp / "template_sig_ok.xlsx"
    template_sig(t_ok, noms_s)
    anomalies, tableau = controler_geometrie(t_ok)
    afficher(anomalies, "Chaine SIG coherente")
    if tableau is not None:
        print("\n  PK calcules automatiquement par projection sur l'axe :")
        print("   " + tableau.to_string(index=False).replace("\n", "\n   "))

    t_nom = dossier_shp / "template_sig_nom.xlsx"
    template_sig(t_nom, noms_s, nom_apport_1="A_inexistant")
    afficher(controler_geometrie(t_nom)[0],
             "\nApport declare absent du shapefile")

    t_ordre = dossier_shp / "template_sig_ordre.xlsx"
    template_sig(t_ordre, ["S1", "S3", "S2", "S4"])
    afficher(controler_geometrie(t_ordre)[0],
             "\nOrdre declare S1, S3, S2, S4 alors que S2 precede S3")

    # --- UNE ERREUR SANS RAPPORT AVEC LES PK NE DOIT PLUS LES EFFACER -----
    #
    # Mesure en production : sur un calage CONFORME de douze apports, une
    # ligne d'injection de 94 cm — signalee « de longueur quasi nulle », ce
    # qui est juste — a fait disparaitre le tableau des PK, et avec lui le
    # profil en long et les pentes locales deduites. La porte testait la
    # GRAVITE GENERALE du controle SIG, pas les conditions du PK.
    dossier_court = Path(tempfile.gettempdir()) / "calage_shp_test_court"
    dossier_court.mkdir(exist_ok=True)
    # Le troisieme apport mesure 94 cm : assez pour lever l'ERREUR, pas assez
    # pour deplacer un PK — il se projette sur l'axe comme les autres.
    _geoms = [transversale(x, 250) for x in (200, 2100, 4300, 6600)]
    _geoms[2] = LineString([(500000 + 4300, 6200000 + 0.0),
                            (500000 + 4300, 6200000 + 0.94)])
    gpd.GeoDataFrame({"Nom": noms_a}, geometry=_geoms,
                     crs=CRS).to_file(dossier_court / "apports.shp")
    t_court = dossier_court / "template_sig_court.xlsx"
    template_sig(t_court, noms_s)
    _p = pd.read_excel(t_court, sheet_name="Parametres")
    _p.loc[_p["Parametre"] == "Fichier_SHP_Apports", "Valeur"] = str(
        dossier_court / "apports.shp")
    with pd.ExcelWriter(t_court, engine="openpyxl", mode="a",
                        if_sheet_exists="replace") as w:
        _p.to_excel(w, sheet_name="Parametres", index=False)
    _anos, _tab = controler_geometrie(t_court)

    # CE MODULE N'AVAIT AUCUNE ASSERTION : son auto-test se contentait
    # d'afficher, donc « il passe » ne voulait dire que « il n'a pas plante ».
    # Ces deux controles-la, eux, doivent pouvoir ECHOUER.
    _echecs_pk = []

    def _verifier(libelle, condition, detail=""):
        print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
              + (f"  ->  {detail}" if detail else ""))
        if not condition:
            _echecs_pk.append(libelle)

    print("\nUne ERREUR sans rapport avec les PK ne doit plus les effacer")
    print("-----------------------------------------------------------")
    # LE NIVEAU, PAS SEULEMENT LE TEXTE. Degrader cette anomalie en
    # AVERTISSEMENT rouvrirait la porte d'origine et ferait verdir ce banc
    # sans que rien ne soit corrige : on exige donc ERREUR.
    _verifier("la ligne d'injection de 94 cm reste signalee en ERREUR",
              any(n == ERREUR and "quasi nulle" in m for n, m in _anos),
              " | ".join(m[:60] for n, m in _anos if n == ERREUR)[:140])
    _verifier("et les PK sont malgre tout calcules",
              _tab is not None and len(_tab) > 0,
              "tableau rendu" if _tab is not None else "AUCUN TABLEAU")
    if _echecs_pk:
        raise SystemExit(f"{len(_echecs_pk)} ECHEC(S) : {_echecs_pk}")

    print("\nAnomalies que ce cas doit faire remonter :")
    for att in [
        "parametre Nom_zone_2D manquant",
        "Nb_max_iterations insuffisant pour converger",
        "Simulation_debut au format francais",
        "colonne Ordre non contigue (1, 2, 4)",
        "nom d'apport en doublon (A2)",
        "Temps_h non strictement croissant",
        "cible C_absente declaree mais absente",
        "debit negatif dans C2",
    ]:
        print(f"   - {att}")
