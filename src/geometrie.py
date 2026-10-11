# -*- coding: utf-8 -*-
"""
Couche geometrique du calage : shapefiles, PK et profil en long.

Ce module fait le lien entre les objets SIG fournis par l'utilisateur
(sections de controle, lignes d'injection, axe hydraulique) et le modele 2D.
Il fournit trois services :

  1. LECTURE ET CONTROLE des shapefiles avant toute utilisation (projection,
     type de geometrie, unicite des noms, croisement effectif de l'axe) ;
  2. CALCUL DES PK par projection curviligne sur l'axe hydraulique, ce qui
     evite toute saisie manuelle et permet de VERIFIER l'ordre declare dans
     le template ;
  3. EXTRACTION DU PROFIL EN LONG (fond du lit et ligne d'eau maximale) le
     long de l'axe, a partir du maillage — c'est lui qui porte le terrain
     effectivement retenu par le calcul.

Le calcul des PK et les controles SIG ne dependent pas de HEC-RAS. Seules les
fonctions d'extraction depuis le modele et d'ecriture dans la geometrie en
dependent, et elles sont importees paresseusement.

Usage :  python geometrie.py        (auto-test sur des shapefiles fabriques)
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

ERREUR, AVERTISSEMENT, INFO = "ERREUR", "AVERTISSEMENT", "INFO"

# Colonnes acceptees pour le nom, par ordre de preference.
COLONNES_NOM = ["Nom", "NOM", "nom", "Name", "NAME", "name", "Id", "ID", "id"]


# ---------------------------------------------------------------------------
# LECTURE DES SHAPEFILES
# ---------------------------------------------------------------------------

def lire_lignes(chemin, colonne_nom=None, prefixe_defaut="Ligne"):
    """
    Lit un shapefile de polylignes et le normalise.

    Retourne un GeoDataFrame a deux colonnes : 'nom' (str) et 'geometry'
    (LineString). Les MultiLineString sont fusionnees ; une geometrie
    multi-parties non contigue leve une erreur, car un PK n'y a pas de sens.

    colonne_nom : nom du champ attributaire portant le nom a utiliser. Si
                  None, le premier champ de COLONNES_NOM present est retenu ;
                  a defaut, les entites sont numerotees.
    """
    import geopandas as gpd
    from shapely.geometry import LineString
    from shapely.ops import linemerge

    gdf = gpd.read_file(chemin)
    if len(gdf) == 0:
        raise ValueError(f"{Path(chemin).name} : aucune entite")

    if colonne_nom is None:
        colonne_nom = next((c for c in COLONNES_NOM if c in gdf.columns), None)
    elif colonne_nom not in gdf.columns:
        raise ValueError(
            f"{Path(chemin).name} : champ '{colonne_nom}' absent "
            f"(champs disponibles : {[c for c in gdf.columns if c != 'geometry']})")

    if colonne_nom is None:
        noms = [f"{prefixe_defaut}_{i + 1:02d}" for i in range(len(gdf))]
    else:
        noms = [str(v).strip() for v in gdf[colonne_nom]]

    geoms = []
    for i, g in enumerate(gdf.geometry):
        if g is None or g.is_empty:
            raise ValueError(f"{Path(chemin).name} : entite {i + 1} sans geometrie")
        if g.geom_type == "MultiLineString":
            fusion = linemerge(g)
            if fusion.geom_type != "LineString":
                raise ValueError(
                    f"{Path(chemin).name} : entite '{noms[i]}' est une "
                    f"polyligne multi-parties non contigue")
            g = fusion
        if g.geom_type != "LineString":
            raise ValueError(
                f"{Path(chemin).name} : entite '{noms[i]}' est de type "
                f"{g.geom_type}, or des polylignes sont attendues")
        geoms.append(LineString(g.coords))

    return gpd.GeoDataFrame({"nom": noms}, geometry=geoms, crs=gdf.crs)


def lire_axe(chemin):
    """
    Lit l'axe hydraulique : une polyligne unique, orientee de l'amont vers
    l'aval. Si le fichier en contient plusieurs, elles sont fusionnees si
    elles se raccordent, sinon une erreur est levee.
    """
    from shapely.ops import linemerge

    gdf = lire_lignes(chemin, prefixe_defaut="Axe")
    if len(gdf) == 1:
        return gdf.geometry.iloc[0], gdf.crs

    fusion = linemerge(list(gdf.geometry))
    if fusion.geom_type != "LineString":
        raise ValueError(
            f"{Path(chemin).name} : l'axe hydraulique comporte {len(gdf)} "
            f"troncons qui ne se raccordent pas en une polyligne unique")
    return fusion, gdf.crs


# ---------------------------------------------------------------------------
# CALCUL DES PK
# ---------------------------------------------------------------------------

def calculer_pk(gdf_lignes, axe, pk_origine=0.0, sens="amont_aval"):
    """
    Calcule le PK de chaque ligne par projection curviligne sur l'axe.

    Pour une section transversale, le PK est celui de son INTERSECTION avec
    l'axe : c'est la position hydrauliquement pertinente. Si la ligne ne
    croise pas l'axe, on projette son centroide, et la colonne 'croise_axe'
    passe a False — ce cas merite verification.

    sens : "amont_aval" si l'axe est dessine de l'amont vers l'aval (cas
           normal, PK croissants vers l'aval), "aval_amont" pour inverser.

    Retourne le GeoDataFrame enrichi des colonnes 'pk_m', 'croise_axe' et
    'distance_axe_m' (ecart entre la ligne et l'axe, nul si elles se croisent).
    """
    longueur = axe.length
    pk, croise, distance = [], [], []

    for g in gdf_lignes.geometry:
        inter = g.intersection(axe)
        if not inter.is_empty:
            point = inter if inter.geom_type == "Point" else inter.representative_point()
            croise.append(True)
            distance.append(0.0)
        else:
            point = g.centroid
            croise.append(False)
            distance.append(float(g.distance(axe)))
        s = axe.project(point)
        pk.append(longueur - s if sens == "aval_amont" else s)

    resultat = gdf_lignes.copy()
    resultat["pk_m"] = np.asarray(pk) + pk_origine
    resultat["croise_axe"] = croise
    resultat["distance_axe_m"] = np.round(distance, 2)
    return resultat


def sens_depuis_profil(profil):
    """
    Deduit le sens de l'axe des ALTITUDES du profil en long : l'eau descend,
    donc le fond decroit vers l'aval.

    Demander le sens a l'utilisateur, c'est lui demander de verifier a la
    main quelque chose que le terrain dit deja. Retourne "amont_aval" si les
    PK croissent vers l'aval, "aval_amont" sinon, et None si le profil ne
    permet pas de trancher — fond trop plat ou trop bruite pour que la pente
    soit significative.
    """
    if profil is None or len(profil) < 3:
        return None
    p = profil.dropna(subset=["pk_m", "z_fond"]).sort_values("pk_m")
    if len(p) < 3:
        return None
    pk = p["pk_m"].to_numpy(dtype=float)
    z = p["z_fond"].to_numpy(dtype=float)
    pente, _ = np.polyfit(pk, z, 1)
    denivele = abs(pente) * (pk[-1] - pk[0])
    # Un denivele inferieur au bruit du terrain ne prouve rien. Seuil
    # volontairement bas (20 cm) : au-dela, la pente d'un cours d'eau est
    # deja parfaitement lisible sur plusieurs kilometres.
    if denivele < 0.20:
        return None
    return "amont_aval" if pente < 0 else "aval_amont"


DEMI_FENETRE_PENTE_M = 200.0
MAJORATION_PENTE = 1.20


def pente_locale(profil, pk, demi_fenetre_m=DEMI_FENETRE_PENTE_M,
                 majoration=MAJORATION_PENTE):
    """
    Pente du fond au droit d'un objet, deduite du profil en long.

    Sert de valeur par defaut a la « Flow Hydrograph Slope » d'un apport quand
    elle n'est pas fournie. Elle etait fixee a 1 % en dur : une valeur
    plausible, jamais la bonne, et identique pour tous les apports d'un modele.

    Ajustee sur +/- 200 m autour du PK de l'objet — assez large pour lisser le
    bruit du maillage, assez etroit pour rester local — puis MAJOREE DE 20 %.
    Cette majoration est deliberee : HEC-RAS se sert de cette pente pour
    repartir le debit entre les mailles que la ligne recoupe, et une pente
    sous-estimee concentre l'injection au lieu de l'etaler. Majorer va donc
    dans le sens de la prudence.

    Retourne None si le profil ne couvre pas la fenetre ou si la pente n'y est
    pas lisible : mieux vaut rendre l'absence de reponse qu'un chiffre invente.
    """
    if profil is None or not len(profil) or pk is None or not np.isfinite(pk):
        return None
    p = profil.dropna(subset=["pk_m", "z_fond"]).sort_values("pk_m")
    fenetre = p[(p["pk_m"] >= pk - demi_fenetre_m)
                & (p["pk_m"] <= pk + demi_fenetre_m)]
    if len(fenetre) < 3:
        return None
    x = fenetre["pk_m"].to_numpy(dtype=float)
    z = fenetre["z_fond"].to_numpy(dtype=float)
    if x[-1] - x[0] < demi_fenetre_m / 2:
        # Fenetre tronquee par un bord du profil : la pente y serait tiree
        # d'un troncon trop court pour etre representative.
        return None
    pente = abs(float(np.polyfit(x, z, 1)[0])) * majoration
    # Une pente nulle ferait diviser par zero cote HEC-RAS ; une pente
    # aberrante trahit un profil bruite plutot qu'un vrai relief.
    if not (1e-5 <= pente <= 0.5):
        return None
    return pente


def apparier_amont_aval(noms_sections, pk_sections, noms_apports, pk_apports):
    """
    Associe a chaque section de controle la PREMIERE injection situee
    immediatement en AMONT d'elle.

    Pourquoi ce n'est PAS une correspondance un pour un imposee : les lignes
    d'injection d'un modele ne sont pas toutes des apports a caler. On y
    trouve aussi les debits d'entree permanents (un affluent amont) et les
    conditions limites aval. Exiger autant de sections que de lignes
    d'injection revenait a compter ces dernieres comme des apports, et a
    refuser de composer un paquet pourtant valide.

    Regle retenue : on parcourt l'axe de l'amont vers l'aval ; chaque section
    prend l'injection rencontree le plus recemment. Une injection sans
    section en aval n'est donc PAS calee — c'est le cas normal d'un debit
    d'entree qu'on ne cherche pas a ajuster. Une section sans injection en
    amont, elle, ne peut pas etre calee du tout : c'est une erreur.

    Les PK doivent CROITRE VERS L'AVAL (voir sens_depuis_profil).

    Retourne un dict :
      paires        [(nom_apport, nom_section), ...] de l'amont vers l'aval
      sans_section  injections non calees, avec leur PK
      sans_apport   sections sans injection en amont — bloquant
      partagees     injections revendiquees par plusieurs sections
    """
    objets = ([(float(pk), "apport", nom)
               for nom, pk in zip(noms_apports, pk_apports)]
              + [(float(pk), "section", nom)
                 for nom, pk in zip(noms_sections, pk_sections)])
    # A PK egal, l'injection precede la section : une injection posee au
    # droit d'une section l'alimente bien.
    objets.sort(key=lambda o: (o[0], 0 if o[1] == "apport" else 1))

    paires, sans_apport = [], []
    revendications = {}
    courant = None
    for pk, genre, nom in objets:
        if genre == "apport":
            courant = nom
        elif courant is None:
            sans_apport.append((nom, pk))
        else:
            paires.append((courant, nom))
            revendications.setdefault(courant, []).append(nom)

    apparies = {a for a, _ in paires}
    sans_section = [(nom, float(pk))
                    for nom, pk in zip(noms_apports, pk_apports)
                    if nom not in apparies]
    partagees = {a: s for a, s in revendications.items() if len(s) > 1}
    return {"paires": paires, "sans_section": sans_section,
            "sans_apport": sans_apport, "partagees": partagees}


def verifier_ordre(noms_ordonnes, pk_par_nom):
    """
    Confronte l'ordre declare dans le template a l'ordre geographique reel
    deduit des PK. C'est le controle que la saisie manuelle ne permettait pas.

    noms_ordonnes : noms des sections dans l'ordre declare (Ordre = 1, 2, ...).
    pk_par_nom    : dict {nom: pk_m}.

    Retourne une liste (niveau, message).
    """
    anomalies = []
    manquants = [n for n in noms_ordonnes if n not in pk_par_nom]
    if manquants:
        anomalies.append((ERREUR, f"PK indisponible pour : {sorted(manquants)}"))
        return anomalies

    pk = [pk_par_nom[n] for n in noms_ordonnes]
    ecarts = np.diff(pk)

    if len(pk) > 1 and np.all(ecarts < 0):
        anomalies.append((
            ERREUR,
            "les PK decroissent regulierement le long de l'ordre declare : "
            "l'axe hydraulique est probablement dessine de l'aval vers "
            "l'amont. Utiliser sens=\"aval_amont\", ou inverser la polyligne."))
        return anomalies

    for i, e in enumerate(ecarts):
        if e < 0:
            anomalies.append((
                ERREUR,
                f"ordre incoherent : '{noms_ordonnes[i + 1]}' (PK "
                f"{pk[i + 1]:.0f} m) est declaree en aval de "
                f"'{noms_ordonnes[i]}' (PK {pk[i]:.0f} m) alors qu'elle la "
                f"precede sur l'axe"))
        elif e == 0:
            anomalies.append((
                AVERTISSEMENT,
                f"'{noms_ordonnes[i]}' et '{noms_ordonnes[i + 1]}' sont au "
                f"meme PK ({pk[i]:.0f} m) : leur ordre ne peut pas etre verifie"))

    return anomalies


def verifier_position_apports(corr_ordonnee, pk_apports, pk_sections):
    """
    Verifie qu'un apport est bien situe EN AMONT de la section qu'il alimente,
    et en aval de la section precedente. Cette condition est structurelle : la
    methode suppose un seul apport nouveau entre deux sections consecutives.

    corr_ordonnee : liste de couples (nom_apport, nom_section) dans l'ordre.
    """
    anomalies = []
    pk_section_precedente = None

    for nom_apport, nom_section in corr_ordonnee:
        if nom_apport not in pk_apports or nom_section not in pk_sections:
            continue
        pa, ps = pk_apports[nom_apport], pk_sections[nom_section]

        if pa > ps:
            anomalies.append((
                ERREUR,
                f"l'apport '{nom_apport}' (PK {pa:.0f} m) est situe EN AVAL de "
                f"la section '{nom_section}' (PK {ps:.0f} m) qu'il doit "
                f"alimenter : il ne peut pas l'influencer"))
        if pk_section_precedente is not None and pa < pk_section_precedente:
            anomalies.append((
                AVERTISSEMENT,
                f"l'apport '{nom_apport}' (PK {pa:.0f} m) est situe en amont "
                f"de la section de controle precedente (PK "
                f"{pk_section_precedente:.0f} m) : il modifiera un troncon "
                f"deja cale, ce qui peut degrader les sections amont"))
        pk_section_precedente = ps

    return anomalies


# ---------------------------------------------------------------------------
# CONTROLE DES SHAPEFILES
# ---------------------------------------------------------------------------

def controler_shp(gdf, libelle, crs_reference=None, longueur_min=1.0,
                  exiger_croisement=False, axe=None):
    """
    Controles generiques sur un shapefile de lignes deja lu et normalise.
    Retourne une liste (niveau, message).
    """
    anomalies = []

    if gdf.crs is None:
        anomalies.append((ERREUR, f"{libelle} : aucune projection definie "
                                  f"(fichier .prj absent)"))
    elif crs_reference is not None:
        try:
            identiques = gdf.crs.equals(crs_reference)
        except Exception:
            identiques = str(gdf.crs) == str(crs_reference)
        if not identiques:
            anomalies.append((
                ERREUR,
                f"{libelle} : projection {gdf.crs.to_string()} differente de "
                f"la reference {crs_reference.to_string()}. Toutes les couches "
                f"doivent partager la projection du modele."))
    if gdf.crs is not None and gdf.crs.is_geographic:
        anomalies.append((
            ERREUR,
            f"{libelle} : projection geographique (degres). Une projection "
            f"metrique est indispensable pour calculer des PK — Lambert-93 "
            f"(EPSG:2154) en France metropolitaine."))

    vides = [n for n in gdf["nom"] if not n or n.lower() in ("nan", "none")]
    if vides:
        anomalies.append((ERREUR, f"{libelle} : {len(vides)} entite(s) sans nom"))

    doublons = gdf["nom"][gdf["nom"].duplicated()].tolist()
    if doublons:
        anomalies.append((ERREUR, f"{libelle} : noms en doublon {sorted(set(doublons))}"))

    courtes = [(n, g.length) for n, g in zip(gdf["nom"], gdf.geometry)
               if g.length < longueur_min]
    if courtes:
        anomalies.append((
            ERREUR,
            f"{libelle} : entite(s) de longueur quasi nulle "
            f"{[(n, round(l, 2)) for n, l in courtes]}"))

    if exiger_croisement and axe is not None:
        sans = [n for n, g in zip(gdf["nom"], gdf.geometry)
                if g.intersection(axe).is_empty]
        if sans:
            anomalies.append((
                AVERTISSEMENT,
                f"{libelle} : {sorted(sans)} ne croisent pas l'axe hydraulique. "
                f"Une section de controle doit traverser le lit de part en "
                f"part ; leur PK est estime par projection du centroide."))

    return anomalies


def mailles_du_modele(hdf, nom_zone_2d=None):
    """
    Centres et surfaces des mailles reelles. Retourne (x, y, surface).

    Comme pour les cotes, les entrees de remplissage sont ecartees : elles se
    reconnaissent a leur cote non renseignee.
    """
    import h5py

    hdf = Path(hdf)
    zones = zones_2d(hdf)
    if not zones:
        raise ValueError(f"{hdf.name} : aucune zone 2D exploitable")
    nom_zone_2d = nom_zone_2d or zones[0]

    with h5py.File(hdf, "r") as h:
        groupe = h[f"Geometry/2D Flow Areas/{nom_zone_2d}"]
        xy = np.asarray(groupe["Cells Center Coordinate"][:], dtype=float)
        surfaces = np.asarray(groupe["Cells Surface Area"][:], dtype=float)
        cotes = np.asarray(groupe["Cells Minimum Elevation"][:], dtype=float)

    reelles = (~np.isnan(cotes)) & (surfaces > 0)
    if not reelles.any():
        raise ValueError(f"{hdf.name} : aucune maille exploitable")
    return xy[reelles, 0], xy[reelles, 1], surfaces[reelles]


def taille_maille(hdf, nom_zone_2d=None, geometrie=None, nb_voisines=25):
    """
    Taille caracteristique de maille : racine carree de la surface mediane.

    Elle sert d'echelle de tolerance geometrique. Comparer une distance a une
    valeur absolue n'aurait pas de sens : 15 m est negligeable sur un maillage
    a 50 m et considerable sur un maillage a 2 m.

    geometrie : si elle est fournie, la taille est mesuree LOCALEMENT, sur les
        mailles les plus proches de cet objet. C'est indispensable des que le
        maillage est raffine par zones — sur un modele reel, le lit peut etre
        a 3 m et la plaine a 25 m. Une tolerance batie sur la mediane globale
        serait alors beaucoup trop severe en bordure de domaine, ou se
        trouvent precisement les conditions limites.
    """
    x, y, surfaces = mailles_du_modele(hdf, nom_zone_2d)

    if geometrie is None:
        return float(np.sqrt(np.median(surfaces)))

    from scipy.spatial import cKDTree

    # Echantillonnage de l'objet, puis mailles les plus proches de chaque point.
    if geometrie.geom_type == "Point":
        points = np.array([[geometrie.x, geometrie.y]])
    else:
        n = max(int(geometrie.length / 10.0) + 1, 5)
        echantillon = [geometrie.interpolate(s, normalized=True)
                       for s in np.linspace(0, 1, n)]
        points = np.array([[p.x, p.y] for p in echantillon])

    arbre = cKDTree(np.column_stack([x, y]))
    k = min(nb_voisines, len(surfaces))
    _, indices = arbre.query(points, k=k)
    return float(np.sqrt(np.median(surfaces[np.unique(indices)])))


def controler_contre_maillage(gdf, libelle, perimetre_2d,
                              doit_etre_interieur=True, tolerance_m=None,
                              part_min=0.95):
    """
    Confronte les lignes au perimetre du maillage 2D.

    doit_etre_interieur=True  : sections de controle, qui doivent etre dans le
                                maillage — sinon le debit integre ne porte que
                                sur une partie de l'ecoulement.
    doit_etre_interieur=False : conditions limites EXTERNES, qui doivent au
                                contraire longer le perimetre.

    tolerance_m : ecart admis au perimetre. Une ligne d'injection n'a PAS a
        coincider avec le polygone de perimetre : HEC-RAS la rattache aux
        faces de mailles les plus proches, et un ecart de l'ordre de la maille
        est normal. Comparer a une distance absolue produirait des fausses
        alertes en serie. Par defaut, aucune tolerance n'est supposee et le
        controle se contente de RAPPORTER la distance mesuree.

    part_min : fraction de longueur devant etre interieure a la zone 2D.
    """
    anomalies = []
    for nom, g in zip(gdf["nom"], gdf.geometry):
        if doit_etre_interieur:
            part = (g.intersection(perimetre_2d).length / g.length
                    if g.length else 0.0)
            if part >= part_min:
                continue
            niveau = ERREUR if part < 0.5 else AVERTISSEMENT
            anomalies.append((
                niveau,
                f"{libelle} : '{nom}' n'est interieure a la zone 2D que sur "
                f"{100 * part:.0f} % de sa longueur. Une section de controle "
                f"doit traverser tout l'ecoulement, faute de quoi le debit "
                f"integre en ignore une partie."))
        else:
            distance = g.distance(perimetre_2d.boundary)
            # tolerance_m peut etre un nombre, ou une fonction de la geometrie
            # lorsque la taille de maille varie d'un endroit a l'autre.
            admis = tolerance_m(g) if callable(tolerance_m) else tolerance_m
            if admis is None:
                if distance > 0:
                    anomalies.append((
                        INFO,
                        f"{libelle} : '{nom}' est a {distance:.1f} m du "
                        f"perimetre du maillage (ecart non evalue, taille de "
                        f"maille inconnue)"))
            elif distance > admis:
                anomalies.append((
                    AVERTISSEMENT,
                    f"{libelle} : '{nom}' est a {distance:.1f} m du perimetre "
                    f"du maillage, soit plus des {admis:.1f} m admis "
                    f"localement. HEC-RAS rattache une condition limite "
                    f"externe aux faces les plus proches : au-dela, le "
                    f"rattachement peut porter sur de mauvaises faces, ou "
                    f"echouer."))
    return anomalies


# ---------------------------------------------------------------------------
# PROFIL EN LONG
# ---------------------------------------------------------------------------

def echantillonner_axe(axe, pas=25.0):
    """Points reguliers le long de l'axe. Retourne (pk_m, x, y)."""
    n = max(int(np.ceil(axe.length / pas)) + 1, 2)
    pk = np.linspace(0.0, axe.length, n)
    points = [axe.interpolate(float(s)) for s in pk]
    return pk, np.array([p.x for p in points]), np.array([p.y for p in points])


def zones_2d(hdf):
    """Noms des zones d'ecoulement 2D presentes dans un fichier HDF."""
    import h5py

    with h5py.File(Path(hdf), "r") as h:
        groupe = h.get("Geometry/2D Flow Areas")
        if groupe is None:
            return []
        return [k for k in groupe
                if hasattr(groupe[k], "keys") and "Cells Minimum Elevation" in groupe[k]]


def maillage_du_modele(hdf, nom_zone_2d=None):
    """
    Cotes de fond et positions des mailles, LUES DANS LE MODELE.

    'Cells Minimum Elevation' est la cote de terrain que HEC-RAS a retenue
    pour chaque maille lors du pretraitement de la geometrie. C'est donc le
    terrain tel que le calcul l'utilise reellement, modifications de terrain
    comprises (merlons, canaux, remblais) — et non le terrain brut d'origine.
    C'est aussi ce qui le rend exactement coherent avec la ligne d'eau
    calculee, qui provient du meme maillage.

    Les tableaux de mailles comportent des entrees de remplissage, reperables
    a leur cote non renseignee ; elles sont ecartees.

    Retourne (x, y, z_fond, nom_zone).
    """
    import h5py

    hdf = Path(hdf)
    zones = zones_2d(hdf)
    if not zones:
        raise ValueError(f"{hdf.name} : aucune zone 2D exploitable")
    if nom_zone_2d is None:
        nom_zone_2d = zones[0]
    elif nom_zone_2d not in zones:
        raise ValueError(f"zone 2D '{nom_zone_2d}' absente de {hdf.name} "
                         f"(presentes : {zones})")

    with h5py.File(hdf, "r") as h:
        groupe = h[f"Geometry/2D Flow Areas/{nom_zone_2d}"]
        z = np.asarray(groupe["Cells Minimum Elevation"][:], dtype=float)
        xy = np.asarray(groupe["Cells Center Coordinate"][:], dtype=float)

    reelles = ~np.isnan(z)
    return xy[reelles, 0], xy[reelles, 1], z[reelles], nom_zone_2d


def profil_depuis_modele(hdf_plan, axe, nom_zone_2d=None, pas=25.0,
                         pk_origine=0.0, avec_ligne_eau=True,
                         distance_max_m=None):
    """
    PROFIL EN LONG TIRE DU MODELE — voie par defaut.

    Pour chaque point de l'axe, on retient la maille 2D la plus proche : sa
    cote de fond donne le lit, et sa cote d'eau maximale la ligne d'eau. Les
    deux proviennent du meme maillage, donc du meme terrain : le profil est
    coherent par construction, sans avoir a fournir ni retrouver de fichier
    de terrain externe.

    distance_max_m : au-dela de cette distance a la maille la plus proche, le
        point est considere hors maillage et laisse a NaN plutot que rattache
        de force a une maille lointaine — ce qui tracerait un fond fictif la
        ou l'axe sort du domaine de calcul. Par defaut, dix fois le pas
        d'echantillonnage.

    Retourne un DataFrame (pk_m, z_fond, z_eau_max, h_max, distance_maille_m).
    """
    from scipy.spatial import cKDTree

    hdf_plan = Path(hdf_plan)
    x_c, y_c, z_c, nom_zone_2d = maillage_du_modele(hdf_plan, nom_zone_2d)

    pk, x, y = echantillonner_axe(axe, pas)
    arbre = cKDTree(np.column_stack([x_c, y_c]))
    distance, indice = arbre.query(np.column_stack([x, y]))

    if distance_max_m is None:
        distance_max_m = 10.0 * pas
    hors_maillage = distance > distance_max_m

    z_fond = z_c[indice].astype(float)
    z_fond[hors_maillage] = np.nan

    resultat = pd.DataFrame({
        "pk_m": pk + pk_origine,
        "z_fond": z_fond,
        "distance_maille_m": np.round(distance, 2),
        "hors_maillage": hors_maillage,
    })

    if avec_ligne_eau:
        from ras_commander import HdfResultsMesh

        ws = HdfResultsMesh.get_mesh_max_ws(hdf_plan)
        if "mesh_name" in ws.columns:
            ws = ws[ws["mesh_name"] == nom_zone_2d]
        z_eau = _colonne_valeur(ws, ("maximum_water_surface", "max_ws",
                                     "water_surface", "value"))
        # get_mesh_max_ws restitue toutes les mailles, remplissage compris :
        # on reprend le meme filtre que maillage_du_modele.
        if len(z_eau) > len(z_c):
            with __import__("h5py").File(hdf_plan, "r") as h:
                brut = np.asarray(
                    h[f"Geometry/2D Flow Areas/{nom_zone_2d}/Cells Minimum Elevation"][:],
                    dtype=float)
            z_eau = z_eau[~np.isnan(brut)]
        eau = z_eau[indice].astype(float)
        eau[hors_maillage] = np.nan
        resultat["z_eau_max"] = eau
        resultat["h_max"] = resultat["z_eau_max"] - resultat["z_fond"]

    return resultat


def controler_profil(profil):
    """
    Controles de vraisemblance du profil en long. Retourne (niveau, message).
    """
    anomalies = []
    n = len(profil)

    hors = int(profil.get("hors_maillage", pd.Series(dtype=bool)).sum())
    if hors:
        part = 100.0 * hors / max(n, 1)
        niveau = ERREUR if part > 25 else AVERTISSEMENT
        anomalies.append((
            niveau,
            f"{hors} point(s) de l'axe sur {n} ({part:.0f} %) sont hors du "
            f"maillage 2D : l'axe hydraulique sort du domaine de calcul. "
            f"Verifier son trace, ou restreindre son emprise."))

    if "h_max" in profil.columns:
        sous_le_fond = int((profil["h_max"] < -0.01).sum())
        if sous_le_fond:
            anomalies.append((
                ERREUR,
                f"{sous_le_fond} point(s) ou la ligne d'eau passe sous le fond : "
                f"le profil et les resultats ne proviennent pas du meme maillage."))

    if "z_fond" in profil.columns:
        z = profil["z_fond"].to_numpy(dtype=float)
        valides = z[~np.isnan(z)]
        if len(valides) > 1 and valides[0] < valides[-1]:
            anomalies.append((
                AVERTISSEMENT,
                f"le fond remonte de l'amont ({valides[0]:.2f} m) vers l'aval "
                f"({valides[-1]:.2f} m) : l'axe est peut-etre oriente a "
                f"l'envers."))

    return anomalies


def _colonne_valeur(gdf, candidats):
    """Extrait une colonne de valeurs d'une sortie ras-commander."""
    for c in candidats:
        if c in gdf.columns:
            return gdf[c].to_numpy(dtype=float)
    numeriques = [c for c in gdf.columns
                  if c != "geometry" and pd.api.types.is_numeric_dtype(gdf[c])
                  and not c.lower().endswith("id")]
    if not numeriques:
        raise ValueError(f"aucune colonne de valeurs trouvee parmi {list(gdf.columns)}")
    return gdf[numeriques[0]].to_numpy(dtype=float)


# ---------------------------------------------------------------------------
# ECRITURE DANS LA GEOMETRIE HEC-RAS
# ---------------------------------------------------------------------------

def noms_objets_geometrie(fichier_geometrie):
    """
    Noms des objets DEJA presents dans le fichier geometrie, lus dans le
    texte : {"sections": [...], "apports": [...]}.

    Lecture du .gXX et non du .gXX.hdf : le HDF est le resultat d'un
    pretraitement, il peut dater d'avant les derniers ajouts. Le fichier
    texte, lui, fait foi.

    Sert a ne pas recreer un objet existant : GeomBcLines.add_bc_lines sans
    remplacement INSERE un second bloc de meme nom, et une geometrie qui
    contient deux objets homonymes rend l'appariement indecidable.

    L'ENCODAGE EST CELUI DU PILOTE (_lire_texte : UTF-8, sinon cp1252). Lu en
    UTF-8 errors="replace", un nom accentue ecrit par HEC-RAS revenait avec
    un U+FFFD : il ne s'appariait plus a celui de QGIS, et l'objet etait
    ecrit une seconde fois. Import tardif : le pilote importe ce module.
    """
    from pilote_hecras import _lire_texte

    sections, apports = [], []
    for ligne in _lire_texte(fichier_geometrie).splitlines():
        if ligne.startswith("BC Line Name="):
            apports.append(ligne.split("=", 1)[1].strip())
        elif ligne.startswith("Reference Line Name="):
            sections.append(ligne.split("=", 1)[1].strip())
    return {"sections": sections, "apports": apports}


def _points_champs_fixes(lignes, depart):
    """
    Points d'un trace HEC-RAS ecrit en champs fixes de 16 caracteres,
    a partir de la ligne DEPART (celle qui suit un « ... Arc= » ou un
    « ... Surface Line= »).

    Les coordonnees suivent, par paires, jusqu'a une ligne qui ne commence
    plus par un nombre. HEC-RAS ecrit chaque valeur dans un champ fixe de 16
    caracteres justifie a droite (le nombre de decimales varie pour
    representer le double exactement) : quand une valeur occupe les 16
    caracteres sans espace de remplissage, elle se retrouve collee a la
    precedente et un simple split() la fusionne avec elle.

    Retourne (points, index de la premiere ligne non lue).
    """
    points = []
    k = depart
    while k < len(lignes) and re.match(r"^\s*-?\d", lignes[k]):
        brut = lignes[k]
        n = len(brut) // 16
        valeurs = [float(brut[16 * m:16 * (m + 1)]) for m in range(n)]
        points += list(zip(valeurs[0::2], valeurs[1::2]))
        k += 1
    return points, k


def objets_depuis_texte(fichier_geometrie):
    """
    Sections de controle et lignes d'injection lues dans le fichier
    geometrie TEXTE, avec leur trace.

    POURQUOI PAS LE HDF : le .gXX.hdf est le produit d'un pretraitement. Un
    objet qu'on vient d'ecrire dans le texte n'y figure PAS tant que HEC-RAS
    n'a pas repretraite la geometrie. Afficher les couches depuis le HDF
    donne donc a croire que l'ecriture a echoue, alors qu'elle a reussi.
    Le fichier texte, lui, est celui qu'on vient d'ecrire : il fait foi.

    Chaque objet s'ecrit ainsi :
        <genre> Line Name=<nom>
        <genre> Line Storage Area=<zone>
        ... positions ...
        <genre> Line Arc= <n>
        <n paires de coordonnees, sur une ou plusieurs lignes>

    Retourne {"sections": [{"nom", "zone", "wkt"}...], "apports": [...]}.
    """
    from pilote_hecras import _lire_texte      # voir noms_objets_geometrie

    lignes = _lire_texte(fichier_geometrie).splitlines()

    familles = {"BC": [], "Reference": []}
    i = 0
    while i < len(lignes):
        correspondance = re.match(r"^(BC|Reference) Line Name=(.*)$", lignes[i])
        if not correspondance:
            i += 1
            continue
        genre, nom = correspondance.group(1), correspondance.group(2).strip()
        zone, points = "", []
        j = i + 1
        while j < len(lignes):
            ligne = lignes[j]
            if re.match(r"^(BC|Reference) Line Name=", ligne):
                break
            zone_trouvee = re.match(
                rf"^{genre} Line Storage Area=(.*)$", ligne)
            if zone_trouvee:
                zone = zone_trouvee.group(1).strip()
            elif re.match(rf"^{genre} Line Arc=", ligne):
                nouveaux, k = _points_champs_fixes(lignes, j + 1)
                points += nouveaux
                j = k - 1
            j += 1
        if nom and len(points) >= 2:
            wkt = "LINESTRING (" + ", ".join(f"{x} {y}" for x, y in points) + ")"
            familles[genre].append({"nom": nom, "zone": zone, "wkt": wkt})
        i = j

    return {"sections": familles["Reference"], "apports": familles["BC"]}


def perimetres_depuis_texte(fichier_geometrie):
    """
    Contour(s) de zone(s) d'ecoulement 2D lus dans le fichier geometrie
    TEXTE (bloc « Storage Area=<nom> », suivi de « Storage Area Surface
    Line= <n> » et de ses points, memes champs fixes de 16 caracteres que
    les sections de controle et lignes d'injection).

    SEULE ROUTE DISPONIBLE avant tout pretraitement HEC-RAS : le maillage
    (HdfMesh.get_mesh_areas) n'existe qu'apres un premier pretraitement de la
    geometrie, mais le contour de la zone 2D, lui, est deja ecrit des sa
    creation dans l'editeur de geometrie. Permet de proposer la zone 2D — et
    de voir son contour sur la carte — avant meme la premiere section de
    controle ou la premiere ligne d'injection.

    Retourne [{"zone", "wkt"}...], wkt en POLYGON, contour referme si besoin.
    """
    from pilote_hecras import _lire_texte      # voir noms_objets_geometrie

    lignes = _lire_texte(fichier_geometrie).splitlines()

    perimetres = []
    i = 0
    while i < len(lignes):
        correspondance = re.match(r"^Storage Area=([^,]*)", lignes[i])
        if not correspondance:
            i += 1
            continue
        zone, points = correspondance.group(1).strip(), []
        j = i + 1
        while j < len(lignes):
            if re.match(r"^Storage Area=", lignes[j]):
                break
            if re.match(r"^Storage Area Surface Line=", lignes[j]):
                points, j = _points_champs_fixes(lignes, j + 1)
                continue
            j += 1
        if zone and len(points) >= 3:
            if points[0] != points[-1]:
                points = points + [points[0]]
            wkt = "POLYGON ((" + ", ".join(f"{x} {y}" for x, y in points) + "))"
            perimetres.append({"zone": zone, "wkt": wkt})
        i = j

    return perimetres


def supprimer_lignes_reference(fichier_geometrie, noms):
    """
    Retire du fichier geometrie TEXTE les blocs « Reference Line Name=<nom> »
    dont le nom figure dans `noms`, avant qu'ils soient reecrits ailleurs.

    GeomReferenceFeatures.add_reference_lines (ras-commander) n'a pas
    d'equivalent a GeomBcLines.add_bc_lines(replace_existing=...) : lui
    passer un nom deja present cree un SECOND bloc du meme nom au lieu de le
    remplacer, ce qui rend l'appariement indecidable (le meme piege que
    noms_objets_geometrie documente pour la lecture). Cette fonction est
    donc le prealable obligatoire d'un remplacement de section.

    DELIMITATION DU BLOC — c'est TOUT le sujet de cette fonction, et c'est ce
    qui a detruit une geometrie de production le 03/08/2026. Un bloc va de sa
    ligne « Reference Line Name=... » jusqu'a la derniere ligne qui LUI
    APPARTIENT, c'est-a-dire :

      - ses attributs, qui commencent tous par « Reference Line  » (Storage
        Area, Start/Middle/End Position, Arc, Text Position...) ;
      - les lignes de coordonnees de son trace, en champs fixes numeriques
        (cf. _points_champs_fixes).

    Toute autre ligne OUVRE AUTRE CHOSE et arrete le bloc.

    NE PAS chercher a la place la prochaine ligne « BC Line Name= » ou
    « Reference Line Name= » : la DERNIERE reference line du fichier n'en a
    aucune apres elle, la recherche courait alors jusqu'a la fin du fichier
    et emportait tout ce qui suit — « LCMann Region » et leurs tables,
    « Chan Stop Cuts », « Composite Channel Slope », « GIS Limit At
    Bridges », « GIS Ratio Cuts To Invert », « Use User Specified Reach
    Order ». Les reference lines et les BC lines, elles, restaient intactes :
    d'ou un fichier qui semblait correct alors que 629 lignes avaient disparu.

    Ouverture avec newline="" : les fins de ligne d'origine (HEC-RAS ecrit en
    CRLF) sont preservees telles quelles sur les lignes conservees, comme le
    fait ras-commander dans ses propres ecritures.

    L'ENCODAGE AUSSI : le fichier est relu puis reecrit dans celui ou il
    etait (pilote_hecras._encodage). C'est la geometrie D'ORIGINE ; lue en
    UTF-8 errors="replace" puis reecrite en UTF-8, elle perdait chacun de
    ses accents au premier remplacement de section (audit du 11/10/2026).

    Retourne la liste des noms effectivement retires. N'ecrit pas le fichier
    si aucun ne l'est.
    """
    if not noms:
        return []
    from pilote_hecras import _encodage        # voir noms_objets_geometrie

    a_retirer = {str(n).strip() for n in noms}
    chemin = Path(fichier_geometrie)
    encodage = _encodage(chemin.read_bytes())
    with open(chemin, "r", encoding=encodage, newline="") as f:
        lignes = f.readlines()

    conservees, retirees = [], []
    i = 0
    while i < len(lignes):
        correspondance = re.match(
            r"^Reference Line Name=(.*)$", lignes[i].rstrip("\r\n"))
        nom = correspondance.group(1).strip() if correspondance else None
        if nom is None or nom not in a_retirer:
            conservees.append(lignes[i])
            i += 1
            continue
        j = i + 1
        while j < len(lignes):
            contenu = lignes[j].rstrip("\r\n")
            if re.match(r"^Reference Line Name=", contenu):
                break          # le bloc suivant, meme famille
            if re.match(r"^Reference Line ", contenu):
                j += 1         # un attribut de CE bloc
                continue
            if re.match(r"^\s*-?\d", contenu):
                j += 1         # une ligne de coordonnees de son trace
                continue
            break              # autre chose : le bloc s'arrete ici
        retirees.append(nom)
        i = j

    if retirees:
        with open(chemin, "w", encoding=encodage, newline="") as f:
            f.writelines(conservees)
    return retirees


def ecrire_dans_geometrie(fichier_geometrie, gdf_sections=None, gdf_apports=None,
                          nom_zone_2d=None, remplacer=False):
    """
    Cree dans la geometrie HEC-RAS (.g##, format texte) les sections de
    controle et les lignes d'injection issues des shapefiles.

    Les deux familles d'objets sont RATTACHEES A UNE ZONE 2D : nom_zone_2d est
    donc obligatoire des qu'on ecrit quelque chose, et son nom doit
    correspondre exactement a un bloc « Storage Area= » du fichier.

    Les reference lines sont ecrites dans le fichier texte, donc elles
    survivent au pre-traitement de la geometrie par HEC-RAS.

    remplacer : un objet DEJA present sous le meme nom est RETRACE plutot
    qu'ignore. Pour les BC lines (apports), GeomBcLines.add_bc_lines gere
    cela nativement (replace_existing). Pour les reference lines (sections),
    ras-commander n'a pas d'equivalent : le bloc existant est retire ICI,
    par supprimer_lignes_reference, avant d'etre reinsere.

    Retourne un dict {sections: ..., apports: ...}.
    """
    from ras_commander import GeomBcLines, GeomReferenceFeatures

    a_ecrire = ((gdf_sections is not None and len(gdf_sections))
                or (gdf_apports is not None and len(gdf_apports)))
    if a_ecrire and not nom_zone_2d:
        raise ValueError(
            "nom_zone_2d est obligatoire : sections de controle et lignes "
            "d'injection sont rattachees a une zone d'ecoulement 2D, et son "
            "nom doit correspondre a un bloc « Storage Area= » du fichier "
            "geometrie.")

    # L'ENCODAGE DE LA GEOMETRIE D'ORIGINE, A TRAVERS ras-commander. Ses deux
    # ecrivains (0.99.2) relisent en UTF-8 errors="ignore" et reecrivent en
    # UTF-8 : chaque accent qu'HEC-RAS avait ecrit en cp1252 disparaissait
    # (audit du 11/10/2026). On leur presente le fichier en UTF-8, ce qui ne
    # perd rien, puis on le rend dans son encodage. Un nom neuf que cet
    # encodage ne sait pas ecrire est refuse AVANT toute ecriture.
    from pilote_hecras import _encodage        # voir noms_objets_geometrie

    chemin = Path(fichier_geometrie)
    encodage = _encodage(chemin.read_bytes())
    for gdf in (gdf_sections, gdf_apports):
        for nom in ([] if gdf is None else gdf["nom"]):
            try:
                str(nom).encode(encodage)
            except UnicodeEncodeError:
                raise ValueError(
                    f"« {nom} » ne s'ecrit pas en {encodage}, l'encodage de "
                    f"{chemin.name} : rien n'y est ecrit.") from None
    if encodage != "utf-8":
        chemin.write_bytes(chemin.read_bytes().decode(encodage).encode("utf-8"))
    try:
        bilan = {}
        if gdf_sections is not None and len(gdf_sections):
            if remplacer:
                supprimer_lignes_reference(fichier_geometrie,
                                           list(gdf_sections["nom"]))
            lignes = [{"name": n, "coordinates": list(g.coords)}
                      for n, g in zip(gdf_sections["nom"],
                                      gdf_sections.geometry)]
            bilan["sections"] = GeomReferenceFeatures.add_reference_lines(
                fichier_geometrie, lignes, nom_zone_2d)

        if gdf_apports is not None and len(gdf_apports):
            lignes = [{"name": n, "storage_area": nom_zone_2d,
                       "coordinates": list(g.coords)}
                      for n, g in zip(gdf_apports["nom"], gdf_apports.geometry)]
            bilan["apports"] = GeomBcLines.add_bc_lines(
                fichier_geometrie, lignes, replace_existing=remplacer)
    finally:
        if encodage != "utf-8":
            chemin.write_bytes(
                chemin.read_bytes().decode("utf-8").encode(encodage))

    return bilan


def lignes_depuis_modele(hdf_geometrie):
    """
    Route alternative au shapefile : recupere sections de controle et lignes
    d'injection DEJA tracees dans le modele, au meme format normalise.
    Les PK peuvent alors etre calcules sans qu'aucun SHP ne soit fourni.
    """
    from ras_commander import HdfBndry

    def normaliser(gdf, prefixe):
        import geopandas as gpd
        if gdf is None or len(gdf) == 0:
            return gpd.GeoDataFrame({"nom": []}, geometry=[], crs=None)
        col = next((c for c in COLONNES_NOM if c in gdf.columns), None)
        noms = ([str(v) for v in gdf[col]] if col
                else [f"{prefixe}_{i + 1:02d}" for i in range(len(gdf))])
        return gpd.GeoDataFrame({"nom": noms}, geometry=list(gdf.geometry),
                                crs=gdf.crs)

    return (normaliser(HdfBndry.get_reference_lines(Path(hdf_geometrie)), "Section"),
            normaliser(HdfBndry.get_bc_lines(Path(hdf_geometrie)), "Apport"))


# ---------------------------------------------------------------------------
# Auto-test : shapefiles fabriques, sans modele hydraulique
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    import geopandas as gpd
    from shapely.geometry import LineString

    print("=" * 72)
    print("AUTO-TEST DE LA COUCHE GEOMETRIQUE")
    print("=" * 72)

    dossier = Path(tempfile.gettempdir()) / "calage_geom_test"
    dossier.mkdir(exist_ok=True)
    CRS = "EPSG:2154"

    # Axe sinueux de l'amont (x=0) vers l'aval (x=8000), en Lambert-93.
    xs = np.linspace(0, 8000, 60)
    ys = 300 * np.sin(xs / 1400)
    axe_geom = LineString(zip(500000 + xs, 6200000 + ys))
    gpd.GeoDataFrame({"Nom": ["Axe"]}, geometry=[axe_geom], crs=CRS).to_file(
        dossier / "axe.shp")

    def transversale(x_local, demi=400.0, decal=0.0):
        y = 300 * np.sin(x_local / 1400) + decal
        return LineString([(500000 + x_local, 6200000 + y - demi),
                           (500000 + x_local, 6200000 + y + demi)])

    sections = ["S1_Amont", "S2_Pont", "S3_Confluence", "S4_Aval"]
    x_sections = [900, 2800, 5100, 7400]
    gpd.GeoDataFrame(
        {"Nom": sections},
        geometry=[transversale(x) for x in x_sections],
        crs=CRS).to_file(dossier / "sections.shp")

    apports = ["A1_Amont", "A2_Affluent", "A3_Ruisseau", "A4_Lateral"]
    x_apports = [200, 2100, 4300, 6600]
    gpd.GeoDataFrame(
        {"Nom": apports},
        geometry=[transversale(x, demi=250) for x in x_apports],
        crs=CRS).to_file(dossier / "apports.shp")

    print(f"\nShapefiles de test ecrits dans : {dossier}")

    # --- 1. Lecture -------------------------------------------------------
    print("\n1. LECTURE ET NORMALISATION")
    axe, crs_axe = lire_axe(dossier / "axe.shp")
    g_sec = lire_lignes(dossier / "sections.shp")
    g_app = lire_lignes(dossier / "apports.shp")
    print(f"   axe      : {axe.length:8.0f} m, {crs_axe.to_string()}")
    print(f"   sections : {len(g_sec)} -> {list(g_sec['nom'])}")
    print(f"   apports  : {len(g_app)} -> {list(g_app['nom'])}")

    # --- 2. Controles -----------------------------------------------------
    print("\n2. CONTROLES SIG")
    anomalies = (controler_shp(g_sec, "sections", crs_axe,
                               exiger_croisement=True, axe=axe)
                 + controler_shp(g_app, "apports", crs_axe))
    print("   aucune anomalie" if not anomalies
          else "\n".join(f"   [{n}] {m}" for n, m in anomalies))

    # --- 3. PK ------------------------------------------------------------
    print("\n3. CALCUL DES PK PAR PROJECTION CURVILIGNE")
    g_sec = calculer_pk(g_sec, axe)
    g_app = calculer_pk(g_app, axe)
    print(g_sec[["nom", "pk_m", "croise_axe"]].to_string(index=False))
    print()
    print(g_app[["nom", "pk_m", "croise_axe"]].to_string(index=False))

    pk_sec = dict(zip(g_sec["nom"], g_sec["pk_m"]))
    pk_app = dict(zip(g_app["nom"], g_app["pk_m"]))

    # --- 4. Coherence de l'ordre -----------------------------------------
    print("\n4. VERIFICATION DE L'ORDRE DECLARE")
    print("   ordre correct           :", verifier_ordre(sections, pk_sec) or "OK")
    faux = ["S1_Amont", "S3_Confluence", "S2_Pont", "S4_Aval"]
    for n, m in verifier_ordre(faux, pk_sec):
        print(f"   ordre S1,S3,S2,S4      : [{n}] {m}")
    inverse = list(reversed(sections))
    for n, m in verifier_ordre(inverse, pk_sec):
        print(f"   axe inverse            : [{n}] {m}")

    # --- 5. Position des apports -----------------------------------------
    print("\n5. POSITION DES APPORTS PAR RAPPORT AUX SECTIONS")
    couples = list(zip(apports, sections))
    print("   correspondance correcte :",
          verifier_position_apports(couples, pk_app, pk_sec) or "OK")
    mauvais = [("A2_Affluent", "S1_Amont")] + couples[2:]
    for n, m in verifier_position_apports(mauvais, pk_app, pk_sec):
        print(f"   apport en aval          : [{n}] {m}")

    # --- 6. Echantillonnage de l'axe --------------------------------------
    print("\n6. ECHANTILLONNAGE DE L'AXE POUR LE PROFIL EN LONG")
    pk, x, y = echantillonner_axe(axe, pas=25.0)
    print(f"   {len(pk)} points, pas de 25 m, de PK {pk[0]:.0f} a {pk[-1]:.0f} m")
    print("   L'altimetrie provient du MAILLAGE du modele (cote de fond de la")
    print("   maille la plus proche), donc du terrain effectivement calcule.")
    print("   Indisponible ici : l'auto-test tourne sans modele hydraulique.")

    # --- 7. Controles de vraisemblance du profil --------------------------
    print("\n7. CONTROLES DE VRAISEMBLANCE DU PROFIL")
    pk_essai = np.arange(0, 2000, 25.0)
    z_fond = 100 - 0.002 * pk_essai

    correct = pd.DataFrame({
        "pk_m": pk_essai, "z_fond": z_fond, "z_eau_max": z_fond + 2.0,
        "h_max": np.full_like(pk_essai, 2.0),
        "hors_maillage": np.zeros(len(pk_essai), dtype=bool),
    })
    print("   profil correct          :", controler_profil(correct) or "OK")

    hors = correct.copy()
    hors.loc[hors.index[:30], "hors_maillage"] = True
    for n, m in controler_profil(hors):
        print(f"   axe sortant du maillage : [{n}] {m}")

    dessous = correct.copy()
    dessous.loc[dessous.index[:5], "h_max"] = -0.5
    for n, m in controler_profil(dessous):
        print(f"   eau sous le fond        : [{n}] {m}")

    envers = correct.copy()
    envers["z_fond"] = envers["z_fond"].to_numpy()[::-1]
    for n, m in controler_profil(envers):
        print(f"   axe a l'envers          : [{n}] {m}")

    # --- 8. Pente locale d'un apport --------------------------------------
    print("\n8. PENTE LOCALE, POUR LA « FLOW HYDROGRAPH SLOPE »")
    _echecs_pente = []

    def _ctrl(libelle, condition, detail=""):
        print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
              + (f"  ->  {detail}" if detail else ""))
        if not condition:
            _echecs_pente.append(libelle)

    # Profil a 0,2 % : la pente rendue doit valoir 0,2 % majore de 20 %.
    _p = pente_locale(correct, 1000.0)
    _ctrl("la pente locale est celle du fond, majoree de 20 %",
          _p is not None and abs(_p - 0.002 * 1.20) < 1e-6,
          f"{_p:.5f} attendu {0.002 * 1.20:.5f}")
    _ctrl("elle ne depend pas du sens du profil",
          abs(pente_locale(envers, 1000.0) - _p) < 1e-6)

    # Pente variable : la valeur doit suivre l'endroit ou on la demande.
    _var = correct.copy()
    _var["z_fond"] = 100 - np.where(pk_essai < 1000, 0.001, 0.006) * pk_essai
    _ctrl("elle est bien LOCALE",
          pente_locale(_var, 300.0) < pente_locale(_var, 1700.0),
          f"amont {pente_locale(_var, 300.0):.5f} / "
          f"aval {pente_locale(_var, 1700.0):.5f}")

    _ctrl("un PK hors du profil ne rend pas de valeur",
          pente_locale(correct, 50000.0) is None)
    _ctrl("un fond parfaitement plat ne rend pas de valeur",
          pente_locale(
              pd.DataFrame({"pk_m": pk_essai,
                            "z_fond": np.full_like(pk_essai, 100.0)}),
              1000.0) is None)
    _ctrl("un profil absent ne leve pas d'erreur",
          pente_locale(None, 1000.0) is None)

    # --- 9. Lecture depuis un fichier geometrie texte (avant pretraitement)
    print("\n9. LECTURE DEPUIS LE FICHIER GEOMETRIE TEXTE (avant pretraitement)")
    print("   Fabrique un .gXX minimal, meme format en champs fixes de 16")
    print("   caracteres qu'un fichier HEC-RAS reel : c'est la seule route")
    print("   disponible pour une geometrie qui n'a jamais ete calculee.")

    def _champ16(v):
        return f"{v:16.6f}"

    def _ligne_point(p):
        return "".join(_champ16(c) for c in p)

    perimetre_brut = [(1000.0, 5000.0), (1000.0, 5100.0),
                      (1100.0, 5100.0), (1100.0, 5000.0)]
    section_brute = [(1020.0, 5000.0), (1020.0, 5100.0)]
    apport_brut = [(1080.0, 5000.0), (1080.0, 5100.0)]

    geom_texte = "\n".join([
        "Geom Title=Test_Auto",
        "Program Version=6.6",
        "",
        "Storage Area=Zone Test     ,,",
        f"Storage Area Surface Line= {len(perimetre_brut)} ",
        *[_ligne_point(p) for p in perimetre_brut],
        "Storage Area Type= 1 ",
        "Storage Area Is2D=-1",
        "",
        "Reference Line Name=Section_Test",
        "Reference Line Storage Area=Zone Test     ",
        f"Reference Line Arc= {len(section_brute)} ",
        *[_ligne_point(p) for p in section_brute],
        "",
        "Reference Line Name=Section_Autre",
        "Reference Line Storage Area=Zone Test     ",
        f"Reference Line Arc= {len(section_brute)} ",
        *[_ligne_point(p) for p in section_brute],
        "",
        "BC Line Name=Apport_Test",
        "BC Line Storage Area=Zone Test     ",
        f"BC Line Arc= {len(apport_brut)} ",
        *[_ligne_point(p) for p in apport_brut],
        "",
    ])
    fichier_geom_texte = dossier / "geometrie_test.g01"
    fichier_geom_texte.write_text(geom_texte, encoding="utf-8")

    objets = objets_depuis_texte(fichier_geom_texte)
    _ctrl("les deux sections sont lues depuis le texte",
          sorted(o["nom"] for o in objets["sections"])
          == ["Section_Autre", "Section_Test"])
    _ctrl("l'injection est lue depuis le texte",
          [o["nom"] for o in objets["apports"]] == ["Apport_Test"])

    perimetres = perimetres_depuis_texte(fichier_geom_texte)
    _ctrl("un seul perimetre de zone 2D trouve", len(perimetres) == 1,
          f"{len(perimetres)} trouve(s)")
    if perimetres:
        _ctrl("le nom de la zone est lu, espaces de bourrage retires",
              perimetres[0]["zone"] == "Zone Test",
              repr(perimetres[0]["zone"]))
        _ctrl("le contour ouvert est referme automatiquement",
              perimetres[0]["wkt"].count(",") == len(perimetre_brut),
              perimetres[0]["wkt"])

    # --- 10. Retrait d'un bloc « Reference Line », prealable au remplacement
    print("\n10. RETRAIT D'UN BLOC « REFERENCE LINE » (prealable au remplacement)")
    retirees = supprimer_lignes_reference(
        fichier_geom_texte, ["Section_Test", "Section_Inexistante"])
    _ctrl("seul le nom present est rapporte comme retire",
          retirees == ["Section_Test"], retirees)

    apres = objets_depuis_texte(fichier_geom_texte)
    _ctrl("la section visee a disparu, l'autre reste",
          [o["nom"] for o in apres["sections"]] == ["Section_Autre"],
          [o["nom"] for o in apres["sections"]])
    _ctrl("l'injection n'est pas affectee",
          [o["nom"] for o in apres["apports"]] == ["Apport_Test"])
    _ctrl("le perimetre de la zone 2D n'est pas affecte",
          len(perimetres_depuis_texte(fichier_geom_texte)) == 1)
    _ctrl("aucun nom a retirer ne touche pas au fichier",
          supprimer_lignes_reference(fichier_geom_texte, []) == [])

    # REGRESSION DU 03/08/2026 — la DERNIERE reference line du fichier.
    # Aucune ligne « ... Line Name= » ne la suit : l'ancienne delimitation
    # courait jusqu'a la fin du fichier et emportait les blocs qui la
    # suivent. Reproduit ici la queue exacte d'une geometrie reelle.
    queue = "\n".join([
        "Geom Title=Test_Queue",
        "",
        "Reference Line Name=SC1",
        "Reference Line Storage Area=2D Area 1       ",
        f"Reference Line Arc= {len(section_brute)} ",
        *[_ligne_point(p) for p in section_brute],
        "Reference Line Text Position= 407004.33825 , 6210543.7065 ",
        "LCMann Time=Dec/30/1899 00:00:00",
        "LCMann Region Time=Dec/30/1899 00:00:00",
        "LCMann Region Name=Prairies",
        "LCMann Region Table=0",
        "LCMann Table=0",
        "Chan Stop Cuts=-1 ",
        "",
        "Use User Specified Reach Order=0",
        "GIS Ratio Cuts To Invert=-1",
        "GIS Limit At Bridges=0",
        "Composite Channel Slope=5",
        "",
    ])
    fichier_queue = dossier / "geometrie_queue.g01"
    fichier_queue.write_text(queue, encoding="utf-8")
    _avant_queue = fichier_queue.read_text(encoding="utf-8")

    _retire_queue = supprimer_lignes_reference(fichier_queue, ["SC1"])
    _apres_queue = fichier_queue.read_text(encoding="utf-8")
    _ctrl("la derniere reference line du fichier est bien retiree",
          _retire_queue == ["SC1"], _retire_queue)
    _ctrl("son trace part avec elle",
          "Reference Line Arc=" not in _apres_queue)
    for _bloc in ("LCMann Region Name=Prairies", "LCMann Table=0",
                  "Chan Stop Cuts=", "Use User Specified Reach Order=",
                  "GIS Ratio Cuts To Invert=", "GIS Limit At Bridges=",
                  "Composite Channel Slope="):
        _ctrl(f"le bloc voisin « {_bloc.rstrip('=0123456789 ')} » survit",
              _bloc in _apres_queue)
    # Rien d'autre que le bloc vise ne doit bouger : le nombre de lignes
    # perdues se compte, il ne s'estime pas.
    _perdues = (len(_avant_queue.splitlines())
                - len(_apres_queue.splitlines()))
    _ctrl("seules les lignes du bloc vise disparaissent",
          _perdues == 4 + len(section_brute), f"{_perdues} ligne(s) perdue(s)")

    # ENCODAGE (audit du 11/10/2026). HEC-RAS ecrit en cp1252 et en CRLF. La
    # geometrie D'ORIGINE se relisait en UTF-8 errors="replace" puis se
    # reecrivait en UTF-8 : au premier remplacement de section, chaque accent
    # du fichier devenait U+FFFD. Tout ce qui n'est pas le bloc retire doit
    # revenir A L'OCTET PRES — le tiret (0x96) n'existe qu'en cp1252, et la
    # derniere ligne est en LF : chaque ligne garde SA fin.
    _tete = b"Geom Title=G\xe9om\xe9trie \xe9tat am\xe9nag\xe9 \x96 digue\r\n"
    _bloc_sc1 = ("Reference Line Name=SC1\r\n"
                 "Reference Line Storage Area=2D Area 1       \r\n"
                 f"Reference Line Arc= {len(section_brute)} \r\n"
                 + "".join(_ligne_point(p) + "\r\n" for p in section_brute)
                 ).encode("cp1252")
    _bloc_ecluse = _bloc_sc1.replace(b"SC1", "Écluse".encode("cp1252"))
    _queue = b"LCMann Region Name=For\xeat\r\nChan Stop Cuts=-1 \n"
    fichier_accents = dossier / "geometrie_accents.g01"
    fichier_accents.write_bytes(_tete + _bloc_sc1 + _bloc_ecluse + _queue)

    _ctrl("un nom de section accentue en cp1252 est lu juste",
          noms_objets_geometrie(fichier_accents)["sections"]
          == ["SC1", "Écluse"]
          and [o["nom"] for o in objets_depuis_texte(fichier_accents)["sections"]]
          == ["SC1", "Écluse"],
          noms_objets_geometrie(fichier_accents)["sections"])
    _ctrl("retirer une section rend le reste de la geometrie a l'octet pres",
          supprimer_lignes_reference(fichier_accents, ["SC1"]) == ["SC1"]
          and fichier_accents.read_bytes() == _tete + _bloc_ecluse + _queue,
          repr(fichier_accents.read_bytes()[:48]))
    _ctrl("une section au nom accentue se retire aussi",
          supprimer_lignes_reference(fichier_accents, ["Écluse"]) == ["Écluse"]
          and fichier_accents.read_bytes() == _tete + _queue,
          repr(fichier_accents.read_bytes()[-48:]))

    # ET A TRAVERS ras-commander, qui ECRIT le trace. Retirer le bloc ne
    # suffisait pas : add_reference_lines et add_bc_lines (0.99.2) relisent
    # en UTF-8 errors="ignore" et reecrivent en UTF-8 — mesure le 11/10/2026,
    # « Géométrie état aménagé – digue » ressortait « Gomtrie tat amnag  digue ».
    try:
        import ras_commander  # noqa: F401
    except ImportError:
        print("   ignore : ras-commander absent, son ecriture n'est pas eprouvee")
    else:
        _corps_rc = "\r\n".join([
            "Storage Area=Zone Test     ,,",
            f"Storage Area Surface Line= {len(perimetre_brut)} ",
            *[_ligne_point(p) for p in perimetre_brut],
            "Storage Area Type= 1 ", "Storage Area Is2D=-1", "",
            "LCMann Region Name=Forêt", "Chan Stop Cuts=-1 ", ""]
        ).encode("cp1252")
        fichier_rc = dossier / "geometrie_ras_commander.g01"
        for _genre in ("sections", "apports"):
            fichier_rc.write_bytes(_tete + _corps_rc)
            _gdf = gpd.GeoDataFrame({"nom": ["Écluse"]}, crs=CRS,
                                    geometry=[LineString(section_brute)])
            ecrire_dans_geometrie(fichier_rc, **{f"gdf_{_genre}": _gdf},
                                  nom_zone_2d="Zone Test", remplacer=True)
            _octets = fichier_rc.read_bytes()
            _ctrl(f"ecrire des {_genre} par ras-commander garde l'encodage "
                  f"de la geometrie (cp1252), accents et nom neuf compris",
                  _octets.startswith(_tete) and b"For\xeat" in _octets
                  and b"Line Name=\xc9cluse" in _octets,
                  repr(_octets[:48]))
        # UNE GEOMETRIE TOUT ASCII EST DU cp1252 (decision du 11/10/2026) : le
        # nom d'apport neuf y prend un octet, comme HEC-RAS l'ecrit et comme
        # dans l'unsteady, et non deux (UTF-8).
        fichier_rc.write_bytes(_corps_rc.replace(b"For\xeat", b"Foret"))
        ecrire_dans_geometrie(fichier_rc, gdf_apports=_gdf,
                              nom_zone_2d="Zone Test")
        _octets = fichier_rc.read_bytes()
        _ctrl("dans une geometrie ASCII, un nom d'apport accentue s'ecrit en "
              "cp1252", b"Line Name=\xc9cluse" in _octets
              and b"\xc3" not in _octets,
              repr(_octets[_octets.find(b"Line Name="):][:24]))

    print("\n" + "=" * 72)
    if _echecs_pente:
        print(f"{len(_echecs_pente)} ECHEC(S) : {_echecs_pente}")
        raise SystemExit(1)
    print("Couche geometrique operationnelle.")
    print("=" * 72)
