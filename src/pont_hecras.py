# -*- coding: utf-8 -*-
"""
Pont en ligne de commande vers HEC-RAS, appelable depuis QGIS.

POURQUOI CE FICHIER EXISTE
--------------------------
Le Python de QGIS embarque sa propre bibliotheque HDF5, utilisee par GDAL.
Des que qgis.core est charge, h5py ne peut plus s'initialiser — et
ras-commander, qui en depend, devient inimportable dans le processus QGIS :

    ImportError: DLL load failed while importing _errors

Ce n'est pas contournable par un ordre d'import : dans un plugin, QGIS est
deja charge. Toute operation touchant a HEC-RAS doit donc s'executer dans un
AUTRE interpreteur. Ce module est cet autre interpreteur : il expose en ligne
de commande les operations courtes dont le plugin a besoin, et repond en JSON
sur la sortie standard.

Les calculs longs ne passent pas par ici non plus : un calage represente des
heures et n'a pas sa place derriere une interface graphique.

Usage :
    python pont_hecras.py lister       --plan <plan.hdf>
    python pont_hecras.py hydrogramme  --plan <plan.hdf> --section <nom>
                                       [--zone <zone2D>] [--sortie <csv>]
    python pont_hecras.py sections     --geometrie <modele.g01> --shp <fic.shp>
                                       --zone <zone2D>
    python pont_hecras.py injections   --geometrie <modele.g01> --shp <fic.shp>
    python pont_hecras.py caler        --template <classeur.xlsx>
                                       (operation LONGUE : lancer via
                                        noyau.lancer_calage(), jamais via
                                        appeler_pont())
    python pont_hecras.py verifier
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent
if str(DOSSIER) not in sys.path:
    sys.path.insert(0, str(DOSSIER))

# LES PARAMETRES DU CALAGE, depuis le 20 septembre 2026, vivent dans un JSON
# a cote du classeur. Ce module n'importe que la bibliotheque standard : il
# peut etre charge ici, avant pandas et avant ras-commander.
import parametres                                           # noqa: E402

# SORTIE EN UTF-8, IMPOSEE ICI. Les messages du journal portent des accents et
# une fleche (« → »), et repondre() serialise en ensure_ascii=False. Redirigee
# vers un fichier sous Windows, la sortie standard prend l'encodage local
# (cp1252) : la fleche y leverait UnicodeEncodeError, en plein calage. Le
# plugin impose deja PYTHONIOENCODING=utf-8 ; ceci couvre l'appel direct en
# ligne de commande, ou rien ne le fait.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def repondre(**donnees):
    """Reponse JSON sur la sortie standard, seul canal lu par l'appelant."""
    print(json.dumps(donnees, ensure_ascii=False, default=str))
    return 0 if donnees.get("ok") else 1


def _sauvegarder(fichier):
    """Copie horodatee avant toute ecriture dans un fichier du modele."""
    fichier = Path(fichier)
    copie = fichier.with_suffix(
        fichier.suffix + datetime.now().strftime(".sauvegarde_%Y%m%d_%H%M%S"))
    shutil.copy2(fichier, copie)
    return copie


# ---------------------------------------------------------------------------
# COMMANDES
# ---------------------------------------------------------------------------

def commande_verifier(_):
    """Confirme que cet interpreteur peut piloter HEC-RAS."""
    import ras_commander as rc

    return repondre(
        ok=True,
        interpreteur=sys.executable,
        python=".".join(str(n) for n in sys.version_info[:3]),
        ras_commander=getattr(rc, "__version__", "?"),
        h5py=__import__("h5py").__version__)


def commande_lister(args):
    """Sections de controle et lignes d'injection presentes dans le modele."""
    import geometrie as geo

    sections, apports = geo.lignes_depuis_modele(args.plan)
    return repondre(ok=True,
                    sections=list(sections["nom"]),
                    apports=list(apports["nom"]))


# Emplacement des series temporelles dans le fichier de resultats.
#
# MEME VALEUR ET MEME NOM que pilote_hecras.CHEMIN_SERIES_HDF, volontairement
# redefini ici : importer pilote_hecras au chargement du pont y entrainerait
# calage, numpy et pandas pour toutes les commandes, y compris « verifier »
# qui doit repondre vite et sans dependance. Les deux doivent rester
# identiques — le nom commun est ce qui permet de les retrouver ensemble.
CHEMIN_SERIES_HDF = ("Results/Unsteady/Output/Output Blocks/Base Output/"
                     "Unsteady Time Series")


def _texte(valeur):
    """
    Texte d'un nom ou d'un attribut lu dans un .hdf de HEC-RAS.

    UTF-8 STRICT, PUIS cp1252, PUIS latin-1 — la regle de la maison pour ce
    que HEC-RAS ecrit (pilote_hecras._lire_texte), appliquee ici a des octets.
    Jusqu'au 11/11/2026 le decodage etait en UTF-8 strict seul : un nom de
    section accentue ecrit en cp1252 levait UnicodeDecodeError des la lecture
    du jeu « Name », et plus AUCUNE section du fichier n'etait lisible.
    latin-1 lit tout octet : en dernier, il garantit qu'un nom ne bloque
    jamais la lecture des autres.
    """
    if not isinstance(valeur, bytes):
        return str(valeur)
    for encodage in ("utf-8", "cp1252"):
        try:
            return valeur.decode(encodage)
        except UnicodeDecodeError:
            continue
    return valeur.decode("latin-1")


# Unites du jeu « Time », par leur debut, et leur duree en heures. Jusqu'au
# 11/11/2026 tout ce qui ne commencait pas par « day » etait lu comme des
# HEURES : des minutes donnaient un axe des temps soixante fois trop long,
# sans message.
_UNITES_TEMPS_EN_HEURES = (("day", 24.0), ("hour", 1.0), ("hr", 1.0),
                           ("min", 1.0 / 60.0), ("sec", 1.0 / 3600.0))


def _heures_par_unite_de_temps(unite, fichier):
    """Facteur de conversion en heures ; ValueError si l'unite est inconnue."""
    texte = _texte(unite).strip()
    for debut, heures in _UNITES_TEMPS_EN_HEURES:
        if texte.lower().startswith(debut):
            return heures
    raise ValueError(
        f"unite de temps « {texte} » inconnue dans le jeu « Time » de "
        f"{Path(fichier).name} : jours, heures, minutes ou secondes attendus. "
        f"L'axe des temps n'est pas converti au hasard.")


def _orienter(debit):
    """
    Ramene une serie de debit a une convention POSITIVE vers l'aval.

    Le signe d'une reference line depend du SENS DANS LEQUEL ELLE A ETE
    TRACEE, pas de l'hydraulique : une ligne dessinee du sud vers le nord
    alors que l'eau va vers l'est donne un debit entierement negatif. Mesure
    sur le modele reel : min -275 m3/s, max 0. Compare telle quelle a une
    cible positive, une telle serie donne un rapport de volume negatif et une
    correlation denuee de sens — le calage divergerait sans que rien
    n'explique pourquoi.

    Retourne (debit_oriente, inversee, reversible). « reversible » signale
    un ecoulement qui change reellement de sens au cours du temps : la
    methode suppose au contraire un sens STABLE (hypothese du § 1.3), et le
    signalement vaut donc avertissement, pas correction.
    """
    import numpy as np

    positif = float(np.sum(debit[debit > 0]))
    negatif = float(-np.sum(debit[debit < 0]))
    if positif == 0.0 and negatif == 0.0:
        return debit, False, False
    faible, fort = min(positif, negatif), max(positif, negatif)
    reversible = faible > 0.05 * fort
    if negatif > positif:
        return -debit, True, reversible
    return debit, False, reversible


def _debit_matriciel(h, chemin, nom, vise, groupe, objets):
    """
    Disposition MATRICIELLE (« Reference Lines ») de lire_serie_hdf : rend
    (debit, nom apparie), le debit tel que stocke, non oriente.
    """
    import numpy as np

    noms = [_texte(v) for v in np.asarray(h[f"{chemin}/Name"][:])]
    # Chaque entree vaut « <nom>|<zone 2D> » : on apparie sur la
    # partie qui precede la barre, en tolerant qu'elle soit absente.
    courts = [n.split("|")[0].strip() for n in noms]
    indice = next((i for i, n in enumerate(courts) if n == str(nom)),
                  None)
    if indice is None:
        indice = next((i for i, n in enumerate(courts)
                       if n.lower() == vise), None)
    if indice is None:
        raise KeyError(
            f"« {nom} » absent des resultats de type « {groupe} ». "
            f"Presents : {courts}")
    if "Flow" not in objets:
        raise KeyError(
            f"les resultats « {groupe} » ne comportent pas de jeu "
            f"« Flow ». Presents : {objets}")
    matrice = np.asarray(h[f"{chemin}/Flow"][:], dtype=float)
    if matrice.ndim != 2 or indice >= matrice.shape[1]:
        raise ValueError(
            f"le jeu « Flow » a la forme {matrice.shape}, "
            f"incompatible avec {len(courts)} objet(s) nommes.")
    debit = matrice[:, indice]
    correspondance = noms[indice]
    return debit, correspondance


def _debit_par_objet(h, chemin, nom, vise, objets):
    """
    Disposition PAR OBJET (« Boundary Conditions ») de lire_serie_hdf : rend
    (debit, nom apparie), le debit tel que stocke, non oriente.
    """
    import numpy as np

    correspondance = next(
        (o for o in objets if o == nom), None) or next(
        (o for o in objets if o.strip().lower() == vise), None)
    if correspondance is None:
        raise KeyError(
            f"« {nom} » absent des resultats. Presents : {objets}")

    jeu = h[f"{chemin}/{correspondance}"]
    donnees = np.asarray(jeu[:], dtype=float)
    colonnes = [_texte(c) for c in jeu.attrs.get("Columns", [])]

    if donnees.ndim == 1:
        debit = donnees
    elif colonnes and "Flow" in colonnes:
        debit = donnees[:, colonnes.index("Flow")]
    elif donnees.shape[1] == 1:
        debit = donnees[:, 0]
    else:
        raise ValueError(
            f"« {correspondance} » : {donnees.shape[1]} colonnes "
            f"{colonnes or 'sans attribut Columns'} — impossible "
            f"d'identifier le debit sans deviner.")
    return debit, correspondance


def lire_serie_hdf(plan, nom, groupe="Reference Lines"):
    """
    Lit une serie de debit DIRECTEMENT dans le fichier de resultats.

    DEUX DISPOSITIONS COEXISTENT dans un meme fichier, et c'est le piege
    principal de cette lecture :

      - PAR OBJET (« Boundary Conditions ») : un jeu de donnees par
        condition limite, portant son nom, avec un attribut « Columns »
        donnant l'ordre des grandeurs — typiquement [Stage, Flow]. La
        colonne de debit est donc identifiee, jamais devinee ;

      - MATRICIELLE (« Reference Lines ») : les jeux ne portent PAS les noms
        des objets mais ceux des GRANDEURS (Flow, Velocity, Water
        Surface...), chacune etant une matrice (temps x objets). L'ordre des
        objets est donne par un jeu « Name », ou chaque entree s'ecrit
        « <nom de la ligne>|<zone 2D> ».

    Un lecteur ecrit pour la premiere disposition echoue sur la seconde en
    annoncant que la section est absente, alors qu'elle est bien la — defaut
    reste invisible tant que le modele ne comportait aucune reference line.

    Le temps est stocke en JOURS (l'attribut du jeu « Time » le precise) et
    converti en heures, unite de travail de toute la chaine. Sans attribut,
    ce sont des jours ; une unite inconnue est refusee (ValueError).

    Retourne un DataFrame (temps, debit_m3s), avec dans .attrs le nom
    reellement apparie, l'inversion d'orientation eventuelle (voir
    _orienter) et un indicateur d'ecoulement reversible.
    """
    import h5py
    import numpy as np
    import pandas as pd

    with h5py.File(plan, "r") as h:
        chemin = f"{CHEMIN_SERIES_HDF}/{groupe}"
        if chemin not in h:
            disponibles = list(h[CHEMIN_SERIES_HDF]) if CHEMIN_SERIES_HDF in h else []
            raise KeyError(
                f"aucun resultat de type « {groupe} » dans ce fichier. "
                f"Presents : {disponibles}. Si la section vient d'etre creee, "
                f"le plan doit etre RECALCULE pour produire ses resultats.")

        objets = list(h[chemin])
        vise = str(nom).strip().lower()

        if "Name" in objets:
            debit, correspondance = _debit_matriciel(h, chemin, nom, vise,
                                                     groupe, objets)
        else:
            debit, correspondance = _debit_par_objet(h, chemin, nom, vise,
                                                     objets)

        temps_jours = np.asarray(h[f"{CHEMIN_SERIES_HDF}/Time"][:], dtype=float)
        unite = h[f"{CHEMIN_SERIES_HDF}/Time"].attrs.get("Time", b"days")
        facteur = _heures_par_unite_de_temps(unite, plan)
        temps_h = (temps_jours - temps_jours[0]) * facteur

    debit, inversee, reversible = _orienter(debit)
    cadre = pd.DataFrame({"temps": temps_h[:len(debit)], "debit_m3s": debit})
    cadre.attrs["objet"] = correspondance
    cadre.attrs["orientation_inversee"] = inversee
    cadre.attrs["ecoulement_reversible"] = reversible
    return cadre


def commande_hydrogramme(args):
    """
    Serie temporelle du debit a travers une section de controle.

    Deux voies, LA LECTURE DIRECTE D'ABORD car c'est la seule verifiee.

    La fonction de synthese de ras-commander construit son tableau en
    supposant une seule colonne par jeu de donnees ; au-dela, elle echoue et
    retourne un tableau VIDE sans rien signaler. Quant a l'autre fonction de
    ras-commander, elle passe par RASMapperLib via pythonnet, absent de cet
    environnement. La lecture directe, elle, ne depend que de h5py, gere les
    DEUX dispositions de stockage du fichier (un jeu par objet pour les
    conditions limites, des matrices indexees par un jeu « Name » pour les
    sections de controle) et normalise l'orientation du debit.

    L'essayer en second reviendrait a preferer une voie dont on a mesure
    qu'elle peut se tromper en silence : l'ordre suit donc le raisonnement.
    """
    from ras_commander import HdfResultsPlan

    def voie_ras_commander():
        brut = HdfResultsPlan.get_reference_timeseries(args.plan, reftype="lines")
        return _normaliser(brut, args.section)

    def voie_directe():
        return lire_serie_hdf(args.plan, args.section, groupe=args.groupe)

    erreurs = []
    for nom_voie, lecture in (("lecture directe du HDF", voie_directe),
                              ("ras-commander", voie_ras_commander)):
        try:
            serie = lecture()
        except Exception as e:
            erreurs.append(f"{nom_voie} : {type(e).__name__} {e}")
            continue
        if serie is None or len(serie) == 0:
            erreurs.append(f"{nom_voie} : aucune serie exploitable")
            continue

        sortie = Path(args.sortie) if args.sortie else (
            Path(args.plan).parent / f"hydrogramme_{args.section}.csv")
        # Unite dans l'en-tete, comme debit_m3s : « temps » seul ne dit pas
        # l'heure. Le renommage n'a lieu qu'a l'export ; le reste de la chaine
        # continue de lire la colonne "temps" du DataFrame interne.
        serie.rename(columns={"temps": "temps_h"}).to_csv(
            sortie, index=False, sep=";", decimal=",")
        return repondre(
            ok=True, voie=nom_voie, section=args.section,
            pas_de_temps=len(serie),
            duree_h=round(float(serie["temps"].iloc[-1]
                                - serie["temps"].iloc[0]), 2),
            pointe_m3s=round(float(serie["debit_m3s"].max()), 3),
            volume_1000m3=round(float(_volume(serie)), 1),
            # Le sens d'une section depend de la facon dont elle a ete
            # tracee : le signaler evite de faire chercher longtemps pourquoi
            # un debit « part a l'envers ».
            orientation_inversee=bool(
                serie.attrs.get("orientation_inversee", False)),
            ecoulement_reversible=bool(
                serie.attrs.get("ecoulement_reversible", False)),
            fichier=str(sortie))

    return repondre(
        ok=False,
        erreur=f"debit introuvable a la section '{args.section}'.",
        details=erreurs)


def _volume(serie):
    """Volume ecoule en milliers de m3, temps suppose en heures."""
    import numpy as np
    import pandas as pd

    temps = serie["temps"]
    if pd.api.types.is_datetime64_any_dtype(temps):
        heures = (pd.to_datetime(temps) - pd.to_datetime(temps).iloc[0]
                  ).dt.total_seconds().to_numpy() / 3600.0
    else:
        heures = np.asarray(temps, dtype=float)
    return np.trapezoid(serie["debit_m3s"].to_numpy(dtype=float), heures) * 3.6


def _normaliser(brut, nom_section):
    """Ramene une sortie ras-commander de forme variable a (temps, debit_m3s)."""
    import pandas as pd

    if brut is None:
        return None

    if isinstance(brut, pd.DataFrame):
        cadre = brut
        if nom_section in cadre.columns:
            return pd.DataFrame({"temps": cadre.index,
                                 "debit_m3s": cadre[nom_section].to_numpy()})
        numeriques = [c for c in cadre.columns
                      if pd.api.types.is_numeric_dtype(cadre[c])]
        if len(numeriques) == 1:
            return pd.DataFrame({"temps": cadre.index,
                                 "debit_m3s": cadre[numeriques[0]].to_numpy()})
        return None

    if hasattr(brut, "to_dataframe"):          # xarray
        try:
            cadre = brut.to_dataframe().reset_index()
        except Exception:
            return None
        if nom_section in cadre.columns:
            temps = cadre["time"] if "time" in cadre.columns else cadre.index
            return pd.DataFrame({"temps": temps,
                                 "debit_m3s": cadre[nom_section].to_numpy()})
    return None


def _objets_du_hdf(chemin):
    """
    Ce que le .gXX.hdf PRETRAITE porte deja : (crs, perimetres, sections,
    injections, vides_hdf), vides_hdf etant les noms des lignes que le HDF
    nomme sans en porter le trace.
    """
    from ras_commander import HdfBndry, HdfMesh

    # LIGNES SANS GEOMETRIE DANS LE HDF : un .gXX.hdf peut nommer ses
    # reference lines sans en porter un seul point (« Polyline Points » vide —
    # releve sur un modele reel le 30/10/2026). ras-commander 0.99 les rend
    # alors en « LINESTRING EMPTY » ; le repli texte ci-dessous les croyait
    # deja connues et ne les relisait pas : la couche des sections arrivait
    # avec des entites sans trace. On les ecarte ici pour que le texte les
    # fournisse.
    vides_hdf = set()

    def lignes(gdf, prefixe):
        if gdf is None or len(gdf) == 0:
            return []
        colonne = next((c for c in gdf.columns
                        if c in ("Name", "name", "Nom", "NOM")), None)
        retenues = []
        for i in range(len(gdf)):
            nom = (str(gdf.iloc[i][colonne]).strip() if colonne
                   else f"{prefixe}_{i + 1:02d}")
            forme = gdf.geometry.iloc[i]
            if forme is None or forme.is_empty:
                vides_hdf.add(nom)
                continue
            retenues.append({"nom": nom, "wkt": forme.wkt})
        return retenues

    crs = None
    bc = HdfBndry.get_bc_lines(chemin)
    ref = HdfBndry.get_reference_lines(chemin)
    zones = HdfMesh.get_mesh_areas(chemin)

    for gdf in (ref, bc, zones):
        if gdf is not None and len(gdf) and gdf.crs is not None:
            crs = gdf.crs.to_string()
            break

    perimetres = ([{"zone": str(r["mesh_name"]), "wkt": r.geometry.wkt}
                  for _, r in zones.iterrows()]
                 if zones is not None and len(zones) else [])
    sections, injections = lignes(ref, "Section"), lignes(bc, "Apport")
    return crs, perimetres, sections, injections, vides_hdf


def commande_modele(args):
    """
    Couches geometriques EXISTANTES dans une geometrie HEC-RAS : perimetre(s)
    de zone 2D, sections de controle (reference lines) et lignes d'injection
    (BC lines) — en WKT, pour que le plugin en fasse des couches QGIS
    editables AVANT tout calcul.

    Le maillage (HdfMesh) et les objets DEJA pretraites (HdfBndry) exigent le
    fichier .hdf de la geometrie, produit par un pretraitement HEC-RAS. Une
    geometrie qui n'a JAMAIS ete pretraitee — le cas d'une zone 2D toute
    neuve, sans la moindre section de controle ni ligne d'injection — n'a
    pas ce .hdf : on se rabat alors entierement sur le fichier texte
    (geometrie.perimetres_depuis_texte, geometrie.objets_depuis_texte), qui
    porte deja le contour de la zone des sa creation dans l'editeur de
    geometrie. Seule l'absence du fichier .gXX lui-meme reste une erreur :
    sans lui, il n'y a rien a lire, pretraite ou non.
    """
    import geometrie as geo

    chemin = Path(args.geometrie)
    texte = chemin.with_suffix("")           # <modele>.g11.hdf -> <modele>.g11
    if not texte.exists():
        return repondre(ok=False, erreur=(
            f"geometrie introuvable : {texte.name}. Verifier le numero de "
            f"geometrie choisi."))

    pretraitee = chemin.exists()
    crs, perimetres, sections, injections = None, [], [], []
    vides_hdf = set()
    if pretraitee:
        crs, perimetres, sections, injections, vides_hdf = _objets_du_hdf(
            chemin)

    # LE FICHIER TEXTE FAIT FOI POUR LES OBJETS. Le .gXX.hdf lu ci-dessus est
    # le produit d'un PRETRAITEMENT : un objet qu'on vient d'ecrire dans le
    # .gXX n'y figure pas tant que HEC-RAS n'a pas repretraite la geometrie.
    # S'en tenir au HDF donnait a croire que l'ecriture avait echoue, alors
    # qu'elle avait reussi — l'utilisateur rechargeait les couches et ne
    # voyait rien de nouveau. Sans .hdf du tout, sections et injections
    # viennent ENTIEREMENT du texte, et rien n'est « en attente » : il n'y a
    # pas de pretraitement dont elles pourraient etre absentes.
    du_texte = geo.objets_depuis_texte(texte)
    en_attente = []
    for cle, depuis_hdf in (("sections", sections), ("apports", injections)):
        connus = {o["nom"] for o in depuis_hdf}
        for objet in du_texte[cle]:
            if objet["nom"] not in connus:
                depuis_hdf.append({"nom": objet["nom"], "wkt": objet["wkt"]})
                if pretraitee and objet["nom"] not in vides_hdf:
                    en_attente.append(objet["nom"])

    # OBJETS DECLARES MAIS ILLISIBLES. Un « Reference Line Name= » present
    # dans le texte, absent du HDF, et dont le trace n'a pas ete reconnu,
    # disparaissait sans bruit : la couche restait vide et l'erreur ne
    # tombait qu'a la validation, sur « aucune entite exploitable »
    # (30/10/2026, sur un modele reel). On les nomme, pour que le compte rendu
    # du chargement le dise.
    declares = geo.noms_objets_geometrie(texte)
    illisibles = (
        [n for n in declares["sections"]
         if n not in {o["nom"] for o in sections}]
        + [n for n in declares["apports"]
           if n not in {o["nom"] for o in injections}])

    # PERIMETRE DEPUIS LE TEXTE en repli : le maillage HDF n'existe qu'apres
    # un pretraitement, mais le contour de la zone 2D est deja ecrit des sa
    # creation dans l'editeur de geometrie.
    if not perimetres:
        perimetres = geo.perimetres_depuis_texte(texte)

    return repondre(ok=True, crs=crs, sections=sections,
                    injections=injections, perimetres=perimetres,
                    en_attente_pretraitement=en_attente,
                    objets_illisibles=illisibles,
                    geometrie_pretraitee=pretraitee)


def _appliquer_pentes(pilote, chemin_template, apports):
    """
    Donne a chaque apport sa pente de ligne d'energie.

    Ordre de priorite : la colonne « Pente_m_par_m » du classeur, puis la
    pente locale du fond (profil en long, +/- 200 m, majoree de 20 %), puis
    rien — la valeur deja presente dans le fichier reste alors en place.

    Elle vaut par apport, pas par lot : deux injections sur des troncons
    differents n'ont aucune raison de partager la meme pente.
    """
    import pandas as pd

    try:
        corr = pd.read_excel(chemin_template, sheet_name="Correspondance")
    except Exception:
        return
    col_apport = next((c for c in corr.columns if c.startswith("Nom_Apport")),
                      None)
    if col_apport is None or "Pente_m_par_m" not in corr.columns:
        return

    saisies = {}
    for _, ligne in corr.iterrows():
        brut = ligne.get("Pente_m_par_m")
        if brut is None or (isinstance(brut, float) and pd.isna(brut)):
            continue
        try:
            valeur = float(str(brut).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if 1e-6 < valeur <= 1.0:
            saisies[str(ligne[col_apport]).strip()] = valeur

    # Repli : la pente locale du fond, pour les apports non renseignes. Calcule
    # une seule fois — le profil en long coute une lecture du maillage.
    deduites = ({} if all(nom in saisies for nom in apports)
                else _pentes_deduites(pilote, chemin_template, apports))

    for nom in apports:
        pente, origine = saisies.get(nom), "classeur"
        if pente is None:
            pente, origine = deduites.get(nom), "profil en long, +/- 200 m +20 %"
        if pente is None:
            print(f"   pente de « {nom} » : inchangee — ni saisie, ni "
                  f"deductible du profil", flush=True)
            continue
        # DEPOSEE, PAS ECRITE. Le fichier unsteady de travail n'existe pas
        # encore : il est clone par pilote.preparer(), qui applique alors ces
        # pentes. Les ecrire ici echouait sur « condition limite absente,
        # Presentes : [] » — la carte des blocs etait vide, faute d'unsteady
        # clone — et toutes les pentes saisies au classeur etaient perdues
        # derriere un simple avertissement.
        pilote.pentes[nom] = pente
        print(f"   pente de « {nom} » : {pente:.5g} m/m ({origine})",
              flush=True)


def _pentes_deduites(pilote, chemin_template, apports):
    """
    Pente locale du fond au droit de chaque apport, depuis le profil en long.

    Repli quand le classeur ne la renseigne pas. Demande l'axe hydraulique :
    sans lui il n'y a pas de PK, donc pas de « au droit de ». Son absence
    n'est pas une erreur — la pente ecrite a la creation reste alors en place.

    Retourne {nom_apport: pente}, vide si le calcul n'a pas pu se faire.
    """
    import pandas as pd

    import controle_donnees as cd
    import geometrie as geo

    try:
        valeurs = parametres.lire(chemin_template)
        axe = valeurs.get(cd.PARAMETRE_AXE)
        if not axe or pd.isna(axe) or not Path(str(axe)).is_file():
            print("   pente : axe hydraulique absent, pente locale non "
                  "calculable", flush=True)
            return {}

        _, tableau = cd.controler_geometrie(chemin_template)
        if tableau is None or "PK apport (m)" not in tableau.columns:
            return {}

        # La GEOMETRIE, et non le plan : au moment ou les pentes s'appliquent,
        # aucun calcul n'a encore tourne et le HDF du plan n'existe pas.
        plan = pilote.dossier / f"{pilote.nom_projet}.p{pilote.plan_travail}"
        trouve = re.search(r"^Geom File=g(\w+)",
                           plan.read_text(encoding="utf-8", errors="replace"),
                           re.M)
        if not trouve:
            return {}
        hdf = pilote.dossier / f"{pilote.nom_projet}.g{trouve.group(1)}.hdf"
        if not hdf.is_file():
            print("   pente : geometrie non pretraitee, pente locale non "
                  "calculable", flush=True)
            return {}
        # profil_depuis_modele attend la GEOMETRIE de l'axe, pas son chemin.
        geometrie_axe, _ = geo.lire_axe(Path(str(axe)))
        profil = geo.profil_depuis_modele(
            str(hdf), geometrie_axe, nom_zone_2d=pilote.nom_zone_2d,
            avec_ligne_eau=False)

        pk = dict(zip(tableau["Apport"].astype(str),
                      tableau["PK apport (m)"].astype(float)))
        return {nom: p for nom in apports
                if (p := geo.pente_locale(profil, pk.get(nom))) is not None}
    except Exception as e:
        print(f"   pente : deduction impossible ({type(e).__name__}: {e}) — "
              f"les valeurs en place sont conservees", flush=True)
        return {}


def _profil_pour_livrables(pilote, chemin_template, resultat):
    """
    PROFIL EN LONG DE SYNTHESE et PK des objets, pour la figure d'ensemble des
    livrables (livrables.figure_profil_en_long).

    C'est la seule figure a montrer une derive AVEC son contexte physique.
    produire_livrables_finaux() la produit des qu'on lui passe ces trois
    valeurs, et la SAUTE EN SILENCE sinon — ce qui l'a rendue absente de tous
    les livrables jusqu'ici, alors qu'elle etait codee, testee, et reprise
    dans la note methodologique. Le defaut n'etait pas dans la figure : cet
    appelant ne lui donnait pas de quoi la tracer.

    Le profil est tire du HDF DE RESULTATS, et non de la geometrie : c'est lui
    seul qui porte la ligne d'eau maximale calculee. Il n'est donc pas
    partageable avec _pentes_deduites(), qui travaille sur la geometrie avant
    tout calcul.

    Les PK viennent de controler_geometrie() — la MEME source que les
    controles, donc la meme convention (PK_origine_m, Sens_axe). Le profil est
    retourne en consequence quand l'axe est dessine de l'aval vers l'amont :
    sans cela, les sections tomberaient a l'envers du fond.

    Retourne (profil, pk_sections, pk_apports), les deux listes alignees sur
    resultat.apports — exactement l'ordre que produire_livrables_finaux()
    reconstruit de son cote. (None, None, None) des qu'une piece manque, AVEC
    LA RAISON AU JOURNAL : la figure est un complement, son absence ne doit
    rien faire perdre du reste du rapport, mais elle ne doit pas etre muette.
    """
    import pandas as pd

    import controle_donnees as cd
    import geometrie as geo

    rien = (None, None, None)
    try:
        valeurs = parametres.lire(chemin_template)

        fichier_axe = valeurs.get(cd.PARAMETRE_AXE)
        if (not fichier_axe or pd.isna(fichier_axe)
                or not Path(str(fichier_axe)).is_file()):
            print("   profil en long de synthese : axe hydraulique absent, "
                  "figure non produite", flush=True)
            return rien

        # Le HDF du plan de travail : apres la boucle, c'est celui du dernier
        # apport cale, donc l'etat que le rapport decrit.
        hdf = pilote.hdf_resultats
        if hdf is None or not Path(hdf).is_file():
            print("   profil en long de synthese : aucun HDF de resultats, "
                  "figure non produite", flush=True)
            return rien

        _, tableau = cd.controler_geometrie(chemin_template)
        if tableau is None or "PK section (m)" not in tableau.columns:
            print("   profil en long de synthese : PK indisponibles, figure "
                  "non produite", flush=True)
            return rien
        pk_sec = dict(zip(tableau["Section"].astype(str),
                          tableau["PK section (m)"].astype(float)))
        pk_app = dict(zip(tableau["Apport"].astype(str),
                          tableau["PK apport (m)"].astype(float)))

        noms_sections = [a.nom_section for a in resultat.apports]
        noms_apports = [a.nom_apport for a in resultat.apports]
        inconnus = ([n for n in noms_sections if n not in pk_sec]
                    + [n for n in noms_apports if n not in pk_app])
        if inconnus:
            print(f"   profil en long de synthese : PK inconnu pour "
                  f"{inconnus}, figure non produite", flush=True)
            return rien

        def _nombre(cle, defaut):
            brut = valeurs.get(cle)
            try:
                return defaut if brut is None or pd.isna(brut) else float(brut)
            except (TypeError, ValueError):
                return defaut

        # Les trois reglages du classeur qui commandent le profil restaient
        # lettre morte, faute d'appel : le pas d'echantillonnage, l'origine des
        # PK, et la distance au-dela de laquelle l'axe est tenu pour sorti du
        # maillage.
        pk_origine = _nombre("PK_origine_m", 0.0)
        axe, _ = geo.lire_axe(Path(str(fichier_axe)))
        profil = geo.profil_depuis_modele(
            str(hdf), axe, nom_zone_2d=pilote.nom_zone_2d,
            pas=_nombre("Pas_profil_m", 25.0), pk_origine=pk_origine,
            distance_max_m=_nombre("Distance_max_axe_maillage_m", None))

        # MEME CONVENTION DE PK que controler_geometrie, qui applique Sens_axe
        # (calculer_pk : « longueur - s » quand l'axe est dessine de l'aval
        # vers l'amont). Le profil, lui, suit toujours le sens du trace.
        if str(valeurs.get("Sens_axe", "amont_aval")).strip() == "aval_amont":
            profil = profil.assign(
                pk_m=axe.length - (profil["pk_m"] - pk_origine) + pk_origine)

        print(f"   profil en long de synthese : {len(profil)} points, "
              f"PK {float(profil['pk_m'].min()):.0f} → "
              f"{float(profil['pk_m'].max()):.0f} m", flush=True)
        return (profil,
                [pk_sec[n] for n in noms_sections],
                [pk_app[n] for n in noms_apports])
    except Exception as e:
        print(f"   profil en long de synthese : non calculable "
              f"({type(e).__name__}: {e}) — figure non produite", flush=True)
        return rien


def _oui_non_ou_defaut(brut):
    """
    Un parametre a TROIS etats : oui, non, ou « laisse la chaine decider ».

    Une case vide n'est pas un « non ». Pour « Fenetre_active », vide vaut
    ACTIVE : la lire comme un refus ferait juger volume, pointe et forme sur
    la duree simulee entiere chez tous ceux qui n'ont pas rempli la case, et
    une mini-crue etrangere a l'evenement degraderait alors le verdict.
    (Ce commentaire renvoyait au « mode rapide », retire du code le
    07/08/2026 : la fenetre ne suit plus rien, elle est active par defaut.)
    """
    valeur = str(brut or "").strip().lower()
    if valeur in ("oui", "true", "1", "vrai"):
        return True
    if valeur in ("non", "false", "0", "faux"):
        return False
    return None


def _unsteady_effectif(dossier, nom_projet, valeurs):
    """
    Fichier Unsteady Flow que le calage utilisera REELLEMENT.

    Ce n'est pas forcement celui qu'on croit : en mode « plan », c'est celui
    que le plan de reference designe, quelle que soit la valeur du parametre
    Unsteady_reference du classeur.
    """
    surcharge = (str(valeurs.get("Mode_selection_modele", "plan")).lower()
                 == "override")
    if surcharge and str(valeurs.get("Unsteady_reference", "")).strip():
        numero = str(valeurs["Unsteady_reference"]).strip().lstrip("uU")
        return dossier / f"{nom_projet}.u{numero.zfill(2)}", "le classeur"

    plan = str(valeurs.get("Plan_reference", "p01")).strip().lstrip("pP")
    fichier_plan = dossier / f"{nom_projet}.p{plan.zfill(2)}"
    if not fichier_plan.exists():
        return None, f"plan {fichier_plan.name} introuvable"
    for ligne in fichier_plan.read_text(encoding="utf-8",
                                        errors="replace").splitlines():
        if ligne.startswith("Flow File="):
            return (dossier / f"{nom_projet}.{ligne.split('=', 1)[1].strip()}",
                    f"le plan {fichier_plan.name}")
    return None, f"aucun « Flow File= » dans {fichier_plan.name}"


def _controler_apports_dans_unsteady(chemin_template):
    """
    Chaque apport a caler a-t-il son bloc de condition limite dans le fichier
    Unsteady Flow que le PLAN DE REFERENCE utilise ?

    Piege observe sur un projet reel : deux plans partageaient la meme
    geometrie mais pas le meme Unsteady Flow. L'injection avait ete ecrite en
    visant le premier plan, le calage lance sur le second. La geometrie
    contenait bien la ligne — donc tous les controles geometriques passaient —
    mais l'hydrogramme etait dans l'autre fichier. L'echec ne survenait qu'au
    premier calcul, apres clonage, avec un message qui ne disait ni quel
    fichier avait ete inspecte ni pourquoi.
    """
    import pandas as pd
    import controle_donnees as cd
    from pilote_hecras import cartographier_hydrogrammes

    try:
        valeurs = parametres.lire(chemin_template)
        corr = pd.read_excel(chemin_template, sheet_name="Correspondance")
    except Exception as e:
        return [(cd.AVERTISSEMENT,
                 f"apports non confrontes au fichier Unsteady : {e}")]

    colonne = next((c for c in corr.columns if c.startswith("Nom_Apport")), None)
    if colonne is None:
        return []
    apports = [str(n).strip() for n in corr[colonne].dropna()
               if str(n).strip()]
    if not apports:
        return []

    dossier = Path(str(valeurs.get("Dossier_projet_HECRAS", "")).strip())
    nom_projet = str(valeurs.get("Nom_projet", "")).strip()
    if not dossier.is_dir() or not nom_projet:
        return []

    fichier, origine = _unsteady_effectif(dossier, nom_projet, valeurs)
    if fichier is None:
        return [(cd.ERREUR, f"fichier Unsteady Flow indeterminable : {origine}")]
    if not fichier.exists():
        return [(cd.ERREUR,
                 f"fichier Unsteady Flow « {fichier.name} », designe par "
                 f"{origine}, introuvable")]

    zone = str(valeurs.get("Nom_zone_2D", "")).strip() or None
    try:
        presentes = set(cartographier_hydrogrammes(fichier, zone))
    except Exception as e:
        return [(cd.AVERTISSEMENT,
                 f"lecture de {fichier.name} impossible : {e}")]

    absents = [a for a in apports if a not in presentes]
    if not absents:
        return []
    return [(cd.ERREUR,
             f"apport(s) sans hydrogramme dans « {fichier.name} » (designe "
             f"par {origine}) : {', '.join(absents)}. Presents : "
             f"{sorted(presentes) or 'aucun'}. Une ligne d'injection presente "
             f"dans la geometrie mais absente de CE fichier n'apporte aucun "
             f"debit. Verifier que l'injection a bien ete ecrite en visant ce "
             f"plan : deux plans peuvent partager la geometrie sans partager "
             f"l'Unsteady Flow.")]


def _contexte_modele(chemin_template):
    """
    Resout, depuis le classeur, ce qu'il faut pour inspecter le modele AVANT
    tout calcul : (unsteady, plan, zone, noms_connus, apports).

    EXTRAIT PARCE QUE DEUX CONTROLES EN ONT BESOIN — les durees et les
    residus de l'unsteady — et que recopier cette resolution des deux cotes
    la vouerait a diverger. C'est exactement ce qui est arrive a
    mots_d_affaires() (voir RESERVE 2, 29/08/2026).

    Retourne None des qu'un element manque : on ne controle pas ce qu'on n'a
    pas su lire. Leve RuntimeError si le CLASSEUR lui-meme est illisible —
    seul cas qui merite d'etre rapporte a l'utilisateur. La seule valeur qui
    a le droit de manquer est noms_connus : None y veut dire « geometrie
    illisible, donc aucun filtre », jamais « aucune BC line ».
    """
    import pandas as pd

    try:
        valeurs = parametres.lire(chemin_template)
        corr = pd.read_excel(chemin_template, sheet_name="Correspondance")
    except Exception as e:
        raise RuntimeError(str(e)) from e

    dossier = Path(str(valeurs.get("Dossier_projet_HECRAS", "")).strip())
    nom_projet = str(valeurs.get("Nom_projet", "")).strip()
    if not dossier.is_dir() or not nom_projet:
        return None

    fichier, _ = _unsteady_effectif(dossier, nom_projet, valeurs)
    if fichier is None or not fichier.exists():
        return None                  # deja dit par le controle precedent

    plan = str(valeurs.get("Plan_reference", "p01")).strip().lstrip("pP")
    fichier_plan = dossier / f"{nom_projet}.p{plan.zfill(2)}"

    colonne = next((c for c in corr.columns if c.startswith("Nom_Apport")), None)
    apports = ([str(n).strip() for n in corr[colonne].dropna() if str(n).strip()]
               if colonne is not None else [])

    # MEME FILTRE QUE LE CALAGE : les blocs sans BC line en geometrie sont
    # ignores par HEC-RAS, donc par nous. Sans cela ces controles refuseraient
    # a la composition ce que le calage accepte — pire qu'un controle absent.
    noms_connus = None
    try:
        import geometrie as geo
        numero = str(valeurs.get("Geometrie_reference", "")).strip().lstrip("gG")
        if str(valeurs.get("Mode_selection_modele", "plan")).lower() != "override":
            for ligne in fichier_plan.read_text(encoding="utf-8",
                                                errors="replace").splitlines():
                if ligne.startswith("Geom File="):
                    numero = ligne.split("=", 1)[1].strip().lstrip("gG")
                    break
        geometrie = dossier / f"{nom_projet}.g{numero.zfill(2)}"
        if geometrie.exists():
            noms_connus = set(geo.noms_objets_geometrie(geometrie)["apports"])
    except Exception:                                        # noqa: BLE001
        noms_connus = None            # « je ne sais pas », donc aucun filtre

    zone = str(valeurs.get("Nom_zone_2D", "")).strip() or None
    return fichier, fichier_plan, zone, noms_connus, apports


def _controler_durees_avant_calcul(chemin_template):
    """
    Les series couvrent-elles la fenetre de simulation du plan de reference ?

    LE CONTROLE EXISTAIT DEJA, MAIS TROP TARD. conditions_trop_courtes() est
    appelee dans PiloteHecRas.preparer() : soit apres le clonage, dans un
    sous-processus DETACHE que le plugin ne regarde pas. L'utilisateur
    lancait un calage, basculait sur l'onglet Suivi, et n'apprenait qu'en
    ouvrant le journal texte que rien n'avait demarre. Cela s'est produit
    TROIS FOIS de suite sur un modele reel (30/08/2026).
    Ici, la meme fonction est appelee a la COMPOSITION : la reponse arrive
    dans le compte rendu de « Ecrire, composer et controler », avant tout lancement.

    ERREUR ou AVERTISSEMENT selon le cote ou se corrige la faute : un apport
    a caler se rallonge dans le classeur — c'est a notre portee, donc
    bloquant ; une autre condition limite se corrige dans le modele source —
    on le signale sans pretendre le reparer.

    Ne bloque JAMAIS sur ce qu'il n'a pas su lire : fenetre illisible,
    geometrie absente, unsteady indeterminable rendent une liste vide. Mieux
    vaut laisser HEC-RAS trancher que refuser un calage sur une lecture
    incertaine — c'est deja la regle de conditions_trop_courtes().

    Retourne (anomalies, prolongation), ou prolongation vaut None ou
    {"duree_h", "apports"} : de quoi permettre au plugin de PROPOSER la
    correction au lieu de la decrire. Le chiffre vient de la mesure, jamais
    d'une relecture du message — un texte se reformule, un contrat non.
    """
    import controle_donnees as cd
    from pilote_hecras import conditions_trop_courtes

    try:
        contexte = _contexte_modele(chemin_template)
    except RuntimeError as e:
        return [(cd.AVERTISSEMENT,
                 f"durees non confrontees a la simulation : {e}")], None
    if contexte is None:
        return [], None
    fichier, fichier_plan, zone, noms_connus, apports = contexte

    try:
        courtes = conditions_trop_courtes(fichier, fichier_plan, zone,
                                          noms_connus, apports)
    except Exception as e:                                   # noqa: BLE001
        return [(cd.AVERTISSEMENT,
                 f"durees non confrontees a la simulation : {e}")], None
    if not courtes:
        return [], None

    def _dire(noms):
        return "; ".join(
            f"« {n} » couvre {courtes[n]['duree_h']:.2f} h pour une simulation "
            f"de {courtes[n]['simulation_h']:.2f} h" for n in sorted(noms))

    anomalies = []
    a_caler = [n for n, d in courtes.items() if d["a_caler"]]
    autres = [n for n, d in courtes.items() if not d["a_caler"]]
    if a_caler:
        anomalies.append((cd.ERREUR,
                          f"apport(s) a caler plus courts que la simulation : "
                          f"{_dire(a_caler)}. HEC-RAS refuserait de calculer "
                          f"(« Time series data ends before the end of the "
                          f"simulation »). Prolonger la colonne dans la "
                          f"feuille Cibles, ou raccourcir la fenetre de "
                          f"simulation du plan."))
    if autres:
        anomalies.append((cd.AVERTISSEMENT,
                          f"condition(s) limite(s) hors calage plus courtes "
                          f"que la simulation : {_dire(autres)}. A corriger "
                          f"dans le modele source : le calage ne les pilote "
                          f"pas, mais HEC-RAS refusera de calculer."))
    # DE QUOI PROPOSER LA CORRECTION, pas seulement la decrire : la duree
    # visee et les apports concernes, tels qu'ils ont ete MESURES.
    prolongation = (
        {"duree_h": max(courtes[n]["simulation_h"] for n in a_caler),
         "apports": sorted(a_caler)} if a_caler else None)
    return anomalies, prolongation


# Au-dela de ce multiple de la fenetre de simulation, une serie n'est plus une
# donnee : c'est un residu. 10 est large a dessein — un modele qui simule 24 h
# avec des entrees couvrant 100 h reste plausible ; 1 095 h, non.
FACTEUR_DUREE_ABERRANTE = 10


def _pretraitement_perime_du_plan(fichier_plan):
    """
    Avertissement si le pretraitement 2D de la geometrie du plan est plus
    ancien qu'elle : [] ou [(AVERTISSEMENT, message)]. Ne leve jamais.
    """
    import controle_donnees as cd
    from pilote_hecras import pretraitement_perime

    anomalies = []
    try:
        for ligne in Path(fichier_plan).read_text(
                encoding="utf-8", errors="replace").splitlines():
            if ligne.startswith("Geom File="):
                g = Path(fichier_plan).with_suffix(
                    "." + ligne.split("=", 1)[1].strip())
                perime = pretraitement_perime(g)
                if perime:
                    anomalies.append((
                        cd.AVERTISSEMENT,
                        f"le pretraitement 2D de {g.name} est PERIME : le "
                        f"fichier texte a ete modifie il y a "
                        f"{perime['geometrie_h']:.1f} h, son .hdf date de "
                        f"{perime['hdf_h']:.1f} h. C'est NORMAL apres une "
                        f"composition — ecrire les sections et les injections "
                        f"perime les tables 2D. HEC-RAS les refera au premier "
                        f"calcul ; sur un modele lourd (gros terrain, projet "
                        f"sur un partage reseau) cela peut echouer sur "
                        f"« Geometry Writer Failed », et le calage s'arretera "
                        f"avant tout resultat. Dans le doute : ouvrir le "
                        f"modele dans HEC-RAS et lancer le plan une fois a la "
                        f"main, puis lancer le calage SANS recomposer."))
                break
    except Exception:                                        # noqa: BLE001
        pass
    return anomalies


def _series_aberrantes(fichier, fichier_plan, retenus):
    """
    Avertissement pour les series bien plus longues que la simulation du
    plan, ou None : rien a dire, ou fenetre de simulation illisible.
    """
    import controle_donnees as cd
    from pilote_hecras import (fenetre_simulation_du_plan, instant_hecras,
                               lire_hydrogramme_unsteady, _en_minutes)

    try:
        fenetre = fenetre_simulation_du_plan(fichier_plan)
        simulation_h = (_en_minutes(instant_hecras(fenetre["fin"]))
                        - _en_minutes(instant_hecras(fenetre["debut"]))) / 60.0
    except Exception:                                        # noqa: BLE001
        return None
    if simulation_h <= 0:
        return None

    aberrantes = []
    for nom, info in retenus.items():
        pas = info["intervalle_h"]
        if not pas:
            continue
        try:
            valeurs = lire_hydrogramme_unsteady(fichier, info["debut"],
                                                   info["fin"])
        except Exception:                                    # noqa: BLE001
            continue
        duree_h = (len(valeurs) - 1) * pas
        if duree_h > FACTEUR_DUREE_ABERRANTE * simulation_h:
            aberrantes.append(f"« {nom} » {duree_h:.0f} h")
    if not aberrantes:
        return None
    return (cd.AVERTISSEMENT,
            f"serie(s) beaucoup plus longues que la simulation "
            f"({simulation_h:.2f} h) : {', '.join(aberrantes)}. "
            f"Verifier qu'il ne s'agit pas d'un hydrogramme "
            f"herite d'un autre evenement : seul le debut sera "
            f"lu, et rien ne le signalera.")


def _controler_residus_unsteady(chemin_template):
    """
    Signale ce qui, dans le fichier Unsteady, trahit un historique d'edition.

    NE BLOQUE RIEN, JAMAIS. Aucun de ces constats n'empeche un calage : ils
    expliquent pourquoi un modele se comporte etrangement, et c'est tout ce
    qu'on leur demande. Trois familles, relevees sur un modele reel dont
    l'unsteady portait 45 blocs pour 14 BC lines (30/08/2026) :

      - BLOCS ORPHELINS : aucun equivalent en geometrie. HEC-RAS les ignore,
        le calage aussi depuis le meme jour — mais personne ne disait qu'ils
        etaient la, et deux d'entre eux ont fait refuser trois lancements ;
      - MEME NOM DANS PLUSIEURS ZONES : le calage retient celui de
        Nom_zone_2D, donc le bon. Si HEC-RAS, lui, ouvre l'autre, le debit
        ecrit ne bougerait jamais et la boucle tournerait des heures avant de
        conclure a une stagnation ;
      - DUREE ABERRANTE : une serie de 1 095 h dans un modele qui en simule
        24 est un residu, pas une donnee. Seul son debut sera lu.
    """
    import controle_donnees as cd
    from pilote_hecras import cartographier_hydrogrammes

    try:
        contexte = _contexte_modele(chemin_template)
    except RuntimeError:
        return []                     # deja dit par le controle des durees
    if contexte is None:
        return []
    fichier, fichier_plan, zone, noms_connus, _ = contexte

    anomalies_pretraitement = _pretraitement_perime_du_plan(fichier_plan)

    try:
        dans_zone = cartographier_hydrogrammes(fichier, zone)
        retenus = cartographier_hydrogrammes(fichier, zone, noms_connus)
        partout = cartographier_hydrogrammes(fichier, None)
    except Exception:                                        # noqa: BLE001
        # Le pretraitement, lui, a pu etre constate : on ne perd pas ce
        # constat parce que la lecture de l'unsteady a echoue.
        return anomalies_pretraitement

    anomalies = list(anomalies_pretraitement)
    orphelins = sorted(set(dans_zone) - set(retenus))
    if orphelins:
        anomalies.append((cd.AVERTISSEMENT,
                          f"{len(orphelins)} bloc(s) du fichier Unsteady sans "
                          f"ligne correspondante dans la geometrie, donc "
                          f"IGNORE(S) par HEC-RAS comme par le calage : "
                          f"{', '.join(orphelins)}. Residus d'une version "
                          f"anterieure du modele — sans effet, mais ils "
                          f"rendent le fichier difficile a relire."))

    if zone is not None:
        ailleurs = sorted(n for n, i in partout.items()
                          if n in retenus and i["autres_zones"])
        if ailleurs:
            anomalies.append((cd.AVERTISSEMENT,
                              f"condition(s) limite(s) declaree(s) dans "
                              f"PLUSIEURS zones 2D : {', '.join(ailleurs)}. "
                              f"Le calage retient celle de « {zone} ». Si "
                              f"HEC-RAS ouvrait l'autre, le debit ecrit "
                              f"n'aurait aucun effet et la boucle tournerait "
                              f"sans jamais progresser."))

    aberrantes = _series_aberrantes(fichier, fichier_plan, retenus)
    if aberrantes:
        anomalies.append(aberrantes)
    return anomalies


def commande_pentes(args):
    """
    Pente du fond au droit de chaque apport, pour PRE-REMPLIR la colonne
    Pente_m_par_m du classeur (noyau.pentes_locales_apports).

    POURQUOI CETTE COMMANDE EXISTE. Le calcul lui-meme tient en trois lignes
    (geometrie.profil_depuis_modele puis pente_locale) et le plugin les
    appelait DIRECTEMENT — mais profil_depuis_modele lit le maillage de la
    geometrie, donc importe h5py, donc ne peut pas tourner dans le processus
    QGIS (voir l'en-tete de ce fichier). L'echec, avale par un except, laissait
    la colonne vide a chaque composition sans jamais rien dire.

    --pk-apports : JSON {nom_apport: PK en m}, dans la MEME convention de PK
    que celle qui a servi a apparier les objets (Sens_axe). Le pont ne les
    recalcule pas : il ne connait ni l'axe normalise du plugin ni le sens
    retenu, et deux conventions differentes placeraient les apports a l'envers
    du profil.

    Repond {"ok": true, "pentes": {...}, "motif": ""}. Une pente non
    calculable n'est PAS une erreur : la case reste vide et le calage la
    deduira lui-meme au moment d'ecrire l'apport (_pentes_deduites).
    """
    import geometrie as geo

    hdf = Path(args.geometrie)
    if not hdf.is_file():
        return repondre(ok=True, pentes={},
                        motif=(f"geometrie non pretraitee par HEC-RAS "
                               f"({hdf.name} absent) : pente locale non "
                               f"calculable, les cases resteront vides."))
    axe = Path(args.axe)
    if not axe.is_file():
        return repondre(ok=True, pentes={},
                        motif=f"axe hydraulique introuvable : {axe}")
    try:
        pk = json.loads(args.pk_apports)
    except ValueError as e:
        return repondre(ok=False, erreur=f"--pk-apports illisible : {e}")
    if not pk:
        return repondre(ok=True, pentes={}, motif="aucun apport a traiter")

    # profil_depuis_modele attend la GEOMETRIE de l'axe, pas son chemin.
    geometrie_axe, _ = geo.lire_axe(axe)
    profil = geo.profil_depuis_modele(
        str(hdf), geometrie_axe, nom_zone_2d=args.zone or None,
        avec_ligne_eau=False)

    pentes = {str(nom): p for nom, valeur in pk.items()
              if valeur is not None
              and (p := geo.pente_locale(profil, float(valeur))) is not None}
    manquants = [str(n) for n in pk if str(n) not in pentes]
    return repondre(
        ok=True, pentes=pentes,
        motif=("" if not manquants else
               f"pente non calculable pour : {', '.join(manquants)} "
               f"(hors profil, ou fond trop plat)"))


def commande_controler_modele(args):
    """
    Confronte la saisie a la geometrie reelle : existence des noms declares,
    et implantation vis-a-vis du maillage 2D. Ce controle ne peut pas
    s'executer dans QGIS, d'ou son passage par le pont.
    """
    import controle_donnees as cd

    anomalies = cd.controler_contre_modele(args.template, args.geometrie)
    anomalies += _controler_apports_dans_unsteady(args.template)
    # AVANT LE LANCEMENT, PAS APRES. Le meme controle existe dans preparer(),
    # mais il n'y parle qu'au journal d'un sous-processus detache.
    durees, prolongation = _controler_durees_avant_calcul(args.template)
    anomalies += durees
    # NE BLOQUE RIEN : dit seulement ce qui, dans l'unsteady, trahit un
    # historique d'edition — et explique un modele qui se comporte mal.
    anomalies += _controler_residus_unsteady(args.template)
    erreurs = [m for n, m in anomalies if n == cd.ERREUR]
    return repondre(ok=True,
                    erreurs=erreurs,
                    avertissements=[m for n, m in anomalies if n != cd.ERREUR],
                    # DE QUOI PROPOSER LA CORRECTION au lieu de la decrire.
                    # None quand il n'y a rien a prolonger.
                    prolongation=prolongation,
                    conforme=not erreurs)


def commande_elaguer_etapes(args):
    """
    Retire les plans d'etape d'un calage abouti — sur demande, et apres coup.

    SIMULATION PAR DEFAUT : sans --executer, rien n'est efface et l'on rend
    seulement la liste de ce qui partirait. C'est ce que la fenetre affiche
    avant de demander confirmation ; le second appel, lui, porte --executer.

    Le refus (« le calage n'a pas conclu ») remonte tel quel dans la reponse :
    c'est un diagnostic sur le projet, pas une panne du pont.
    """
    from pilote_hecras import PiloteHecRas

    pilote = PiloteHecRas(args.dossier, args.projet,
                          plan_reference=args.plan_reference)
    # Le calage est termine : il n'y a plus de plan courant a proteger, et le
    # plan final se reconnait a son titre, pas a un numero.
    pilote.plan_travail = None
    rendu = pilote.elaguer_etapes(args.prefixe or "", args.apports,
                                  simuler=not args.executer)
    return repondre(ok=True, **rendu)


def commande_sections(args):
    """
    Cree des reference lines dans la geometrie, depuis un shapefile.

    Sans --remplacer, les sections DEJA presentes sont ignorees, jamais
    recreees : une geometrie contenant deux objets de meme nom rend
    l'appariement indecidable, et l'ecriture n'en avertirait pas. Avec
    --remplacer, elles sont RETRACEES (bloc retire puis reinsere) — c'est le
    mode utilise par le plugin a chaque « Ecrire, composer et controler », depuis
    que le trace QGIS fait foi sur la geometrie HEC-RAS. Meme convention que
    commande_injections.
    """
    import geometrie as geo

    lignes = geo.lire_lignes(args.shp)
    deja = geo.noms_objets_geometrie(args.geometrie)["sections"]
    a_ecrire = [n for n in lignes["nom"] if args.remplacer or n not in deja]
    ignorees = [n for n in lignes["nom"] if n not in a_ecrire]
    if not a_ecrire:
        return repondre(
            ok=True, creees=0, noms=[], remplacees=[], ignorees=ignorees,
            avertissements=[f"rien a creer : {', '.join(ignorees)} "
                            f"deja dans {Path(args.geometrie).name}."])

    remplacees = [n for n in a_ecrire if n in deja]
    lignes = lignes[lignes["nom"].isin(a_ecrire)].copy()
    copie = _sauvegarder(args.geometrie)
    bilan = geo.ecrire_dans_geometrie(args.geometrie, gdf_sections=lignes,
                                      nom_zone_2d=args.zone,
                                      remplacer=args.remplacer)
    return repondre(ok=True, creees=len(lignes), noms=list(lignes["nom"]),
                    remplacees=remplacees, ignorees=ignorees, bilan=bilan,
                    sauvegarde=str(copie),
                    avertissements=([f"deja presentes, laissees intactes : "
                                     f"{', '.join(ignorees)}"]
                                    if ignorees else []))


def commande_injections(args):
    """
    Cree des BC lines dans la geometrie ET, si un fichier unsteady est
    fourni, le bloc de condition limite qui leur donne un hydrogramme.

    LES DEUX ECRITURES SONT NECESSAIRES. Une BC line presente dans la seule
    geometrie existe pour HEC-RAS mais n'apporte AUCUN debit : elle n'a pas
    d'hydrogramme. Le calage la mettrait a l'echelle sans effet, et
    conclurait a une stagnation apres avoir consomme tous ses essais.

    La zone 2D est obligatoire : HEC-RAS rattache chaque BC line a un bloc
    « Storage Area= » du fichier geometrie.

    La FORME de l'hydrogramme initial n'a pas besoin d'etre juste — le calage
    la met a l'echelle — mais elle doit couvrir la fenetre du modele. D'ou
    --forme-depuis, qui reprend a une condition limite existante la DUREE
    qu'elle couvre. Le pas, lui, ne se reprend pas : il vaut toujours 6 min
    (--intervalle pour en imposer un autre).
    """
    import geometrie as geo
    from pilote_hecras import (INTERVALLE_APPORT, _intervalle_en_heures,
                               ajouter_condition_limite_debit,
                               cartographier_hydrogrammes, intervalle_hecras,
                               lire_hydrogramme_unsteady,
                               noms_conditions_limites)

    lignes = geo.lire_lignes(args.shp)

    # TOUT VERIFIER AVANT D'ECRIRE QUOI QUE CE SOIT. La geometrie etait
    # ecrite d'abord, puis l'unsteady : quand ce second echouait, la
    # geometrie avait deja recu des objets en double, et il fallait la
    # restaurer a la main. Les deux fichiers ne sont desormais touches que
    # si l'operation entiere peut aboutir.
    deja_geom = geo.noms_objets_geometrie(args.geometrie)["apports"]
    a_ecrire = [n for n in lignes["nom"]
                if args.remplacer or n not in deja_geom]
    deja_presents = [n for n in lignes["nom"] if n not in a_ecrire]
    if not a_ecrire:
        return repondre(
            ok=True, creees=0, noms=[], raccordes=[],
            avertissements=[
                f"rien a creer : {', '.join(deja_presents)} "
                f"{'existe' if len(deja_presents) == 1 else 'existent'} deja "
                f"dans {Path(args.geometrie).name}. Cocher « remplacer » pour "
                f"en redefinir le trace."])

    lignes = lignes[lignes["nom"].isin(a_ecrire)].copy()
    copie = _sauvegarder(args.geometrie)
    bilan = geo.ecrire_dans_geometrie(args.geometrie, gdf_apports=lignes,
                                      nom_zone_2d=args.zone,
                                      remplacer=args.remplacer)

    raccordes, avertissements = [], []
    if deja_presents:
        avertissements.append(
            f"deja dans la geometrie, laisse intact : "
            f"{', '.join(deja_presents)}")
    if not args.unsteady:
        avertissements.append(
            "aucun fichier unsteady fourni (--unsteady) : les lignes creees "
            "n'ont PAS d'hydrogramme et n'apporteront aucun debit tant qu'une "
            "condition limite ne leur aura pas ete associee.")
    else:
        copie_u = _sauvegarder(args.unsteady)
        carte = cartographier_hydrogrammes(args.unsteady, args.zone)

        # UN APPORT CREE NAIT A ZERO. Sa forme n'est pas a deviner ici : la
        # boucle de calage commence par un calcul SANS les apports, mesure ce
        # que la section recoit deja, puis donne a l'apport la forme de la
        # CIBLE avant d'en ajuster l'amplitude (§ 1.6). Recopier la forme
        # d'une autre condition limite ne servait qu'a fournir une base de
        # temps — c'est tout ce qu'on reprend ici, sans les valeurs.
        modele_temps = carte.get(args.forme_depuis) if args.forme_depuis else None
        if modele_temps is None and carte:
            modele_temps = carte[sorted(carte)[0]]
        # INTERVALLE DE 6 MIN, quel que soit celui du modele : c'est le pas
        # au-dela duquel une cible est densifiee a la lecture du classeur
        # (criteres.PAS_ENTREE_H) — une cible deja plus fine garde son pas
        # natif, et definir_forme() la reprojette de toute facon sur la
        # grille reelle de l'apport au moment de l'ecriture. Ce qui est
        # repris d'une condition limite existante n'est donc pas son pas,
        # mais sa DUREE — sans quoi un apport cree a 6 min a partir d'un
        # modele au quart d'heure couvrirait 2 h 24 la ou le modele en
        # simule 24, et n'injecterait rien au-dela.
        intervalle = (intervalle_hecras(args.intervalle) if args.intervalle
                      else INTERVALLE_APPORT)
        pas_h = _intervalle_en_heures(intervalle)
        if not pas_h:
            raise ValueError(
                f"intervalle « {intervalle} » non convertible en heures : le "
                f"nombre de valeurs de l'hydrogramme ne peut pas en etre "
                f"deduit. Utiliser une notation entiere (6MIN, 15MIN, 1HOUR).")
        if modele_temps is not None:
            # « nb » compte les LIGNES du tableau, pas les valeurs : le format
            # en aligne dix par ligne. C'est le tableau relu qui donne le
            # nombre exact de pas de temps.
            reference = lire_hydrogramme_unsteady(
                args.unsteady, modele_temps["debut"], modele_temps["fin"])
            forme = [0.0] * _nb_valeurs_meme_duree(
                len(reference), modele_temps["intervalle_h"] or pas_h, pas_h)
        else:
            forme = [0.0] * int(args.nb_valeurs)

        # On interroge TOUTES les conditions limites, et pas seulement celles
        # qui portent un hydrogramme : une condition de SORTIE n'en a pas, et
        # se fier a la seule carte des hydrogrammes revenait a la croire
        # absente, donc a vouloir la creer alors qu'elle existe.
        existantes = noms_conditions_limites(args.unsteady, args.zone)
        avec_hydrogramme = cartographier_hydrogrammes(args.unsteady, args.zone)
        for nom in lignes["nom"]:
            if nom in avec_hydrogramme:
                avertissements.append(
                    f"« {nom} » avait deja un hydrogramme : conserve tel quel, "
                    f"il n'a pas ete remplace.")
                continue
            if nom in existantes:
                avertissements.append(
                    f"« {nom} » existe deja comme condition limite sans "
                    f"hydrogramme de debit — une sortie, typiquement. Elle est "
                    f"laissee intacte : lui en ajouter un la transformerait en "
                    f"entree.")
                continue
            ajouter_condition_limite_debit(args.unsteady, nom, args.zone,
                                           forme, intervalle=intervalle,
                                           pente=args.pente)
            raccordes.append(nom)
        avertissements.append(f"sauvegarde unsteady : {copie_u}")

    return repondre(ok=True, creees=len(lignes), noms=list(lignes["nom"]),
                    bilan=bilan, sauvegarde=str(copie),
                    raccordes=raccordes, avertissements=avertissements)


def _nb_valeurs_meme_duree(nb_reference, pas_reference_h, pas_h):
    """
    Nombre de valeurs couvrant la MEME duree qu'un hydrogramme de reference,
    mais au pas pas_h.

    Ce qu'on reprend d'une condition limite existante est sa DUREE, jamais son
    pas : l'apport cree est toujours a 6 min. Reprendre le NOMBRE de valeurs,
    comme la chaine le faisait, revenait a changer la duree avec le pas — un
    apport cree a 6 min a partir d'un modele au quart d'heure ne couvrait plus
    que 2 h 24 sur les 24 h simulees, et n'injectait plus rien au-dela sans
    qu'aucun message ne le signale.

    N valeurs decrivent N-1 intervalles : c'est sur eux que porte le calcul.
    """
    duree_h = (int(nb_reference) - 1) * float(pas_reference_h)
    return int(round(duree_h / float(pas_h))) + 1


def _texte_parametre(valeurs, cle, defaut=""):
    """Valeur textuelle d'un parametre du classeur, jamais NaN ni None."""
    import pandas as pd

    v = valeurs.get(cle)
    return defaut if v is None or pd.isna(v) else str(v).strip()


def _nombre_parametre(valeurs, cle, defaut):
    """Valeur numerique d'un parametre du classeur, defaut si vide ou illisible."""
    import pandas as pd

    v = valeurs.get(cle)
    try:
        return float(v) if v is not None and not pd.isna(v) else defaut
    except (TypeError, ValueError):
        return defaut


def _dire_horodate(*morceaux):
    """
    Ecrit une ligne du journal, PRECEDEE DE L'HEURE.

    Les lignes de ras-commander passent par logging et portent deja
    « AAAA-MM-JJ HH:MM:SS » ; celles de la chaine, non. On ne pouvait donc
    chronometrer aucune etape sans se caler sur la ligne horodatee voisine —
    ce qui a fait lire « le premier apport a cale en 8 secondes » la ou il en
    avait mis 1 h 15 (releve le 31/08/2026 sur un calage de 25 h).

    MEME FORMAT QUE ras-commander, a dessein : un calage traverse minuit,
    donc la date est necessaire, et le journal reste triable d'un bout a
    l'autre. L'indentation des lignes de la chaine est conservee derriere
    l'horodatage, qui ne remplace pas la hierarchie visuelle.

    SOURCE UNIQUE pour tous les appels « journal= » de production : deux
    lambdas separees auraient fini par diverger, comme les deux listes de
    paquets avant PAQUETS_HECRAS.
    """
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *morceaux, flush=True)


def _cibles_depuis_classeur(chemin_template, journal=None):
    """
    Lit les hydrogrammes cibles de la feuille Cibles, dans l'ordre de la
    feuille Correspondance.

    Retourne (apports, sections, cibles, manquantes) : cibles est une liste
    de (temps_h, debit), alignee sur apports/sections ; manquantes est la
    liste des sections dont la cible n'est pas exploitable — le calage ne
    doit jamais demarrer avec un trou dans les cibles, mieux vaut le dire
    tout de suite qu'echouer des heures plus tard sur le premier apport
    concerne.

    CHAQUE CIBLE PLUS GROSSIERE QUE 6 MIN EST RAMENEE A CE PAS
    (criteres.PAS_ENTREE_H), celui de l'apport ecrit dans l'unsteady : un HSMF
    colle a la main arrive au pas de sa source, horaire le plus souvent, et le
    recalage temporel comme la forme injectee dans le modele en heritent telle
    quelle — calage.py les reprend directement sur la base de temps de la
    cible. Une cible DEJA a 6 min ou plus fine est conservee a son pas natif,
    sans degradation. Toute conversion (densification d'une cible grossiere)
    est consignee par « journal », qui recoit une ligne par cible convertie :
    la donnee lue n'est pas celle qui a ete saisie, cela doit se lire.
    """
    import numpy as np
    import pandas as pd

    from criteres import PAS_ENTREE_H, normaliser_entree

    # LES FEUILLES ET LES COLONNES, NOMMEES, OU RIEN : pandas dirait « Worksheet
    # named 'Cibles' not found », et next() leverait StopIteration.
    with pd.ExcelFile(chemin_template) as classeur:
        feuilles = classeur.sheet_names
    for nom in ("Correspondance", "Cibles"):
        if nom not in feuilles:
            raise ValueError(f"le classeur n'a pas de feuille « {nom} » "
                             f"(feuilles trouvees : {feuilles})")
    corr = pd.read_excel(chemin_template, sheet_name="Correspondance")
    cib = pd.read_excel(chemin_template, sheet_name="Cibles")
    col_ordre = "Ordre"

    def colonne(prefixe):
        trouvee = next((c for c in corr.columns if c.startswith(prefixe)),
                       None)
        if trouvee is None:
            raise ValueError(
                f"la feuille Correspondance n'a pas de colonne « {prefixe} » "
                f"(en-tete A1). En-tetes trouves : "
                f"{[str(c) for c in corr.columns]}")
        return trouvee

    col_apport = colonne("Nom_Apport")
    col_section = colonne("Nom_Section")
    col_cible = colonne("Nom_Cible")
    corr = corr.dropna(subset=[col_ordre, col_apport, col_section, col_cible]
                       ).sort_values(col_ordre)

    # LA COLONNE DU TEMPS, NOMMEE, OU RIEN. Sans elle cib.get() rend None et
    # to_numeric() un scalaire : « 'numpy.float64' object has no attribute
    # 'to_numpy' », en arriere-plan, au lancement (04/09/2026 — un en-tete A1
    # remplace). Dire l'en-tete attendu et ceux trouves, c'est dire ou corriger.
    if "Temps_h" not in cib.columns:
        raise ValueError(
            f"la feuille Cibles n'a pas de colonne « Temps_h » (en-tete A1). "
            f"En-tetes trouves : {[str(c) for c in cib.columns][:12]}"
            + (f" … et {len(cib.columns) - 12} autres"
               if len(cib.columns) > 12 else ""))
    # DES DATES NE SONT PAS DES HEURES : to_numeric rend les microsecondes
    # depuis 1970, et reechantillonner tentait alors d'allouer 536 Gio.
    if pd.api.types.is_datetime64_any_dtype(cib["Temps_h"]):
        raise ValueError(
            "la colonne « Temps_h » de la feuille Cibles contient des DATES. "
            "Le calage attend des heures decimales comptees depuis le debut "
            "de la simulation (0 ; 0,5 ; 1 …).")
    temps = pd.to_numeric(cib["Temps_h"], errors="coerce").to_numpy(dtype=float)

    apports, sections, cibles, manquantes = [], [], [], []
    for _, ligne in corr.iterrows():
        section = str(ligne[col_section])
        nom_cible = str(ligne[col_cible])
        if nom_cible not in cib.columns or cib[nom_cible].isna().all():
            manquantes.append(section)
            continue
        debit = pd.to_numeric(cib[nom_cible], errors="coerce").to_numpy(dtype=float)
        masque = ~(np.isnan(temps) | np.isnan(debit))
        if masque.sum() < 2:
            manquantes.append(section)
            continue
        t_cible, q_cible, pas_initial = normaliser_entree(temps[masque],
                                                          debit[masque])
        if pas_initial is not None and journal is not None:
            # « X min » et non « X h » : les pas saisis vont de la minute a
            # l'heure, la minute les couvre tous sans decimale inutile.
            # AVERTISSEMENT, ET LE MOT Y EST : c'est a lui que l'onglet Suivi
            # du plugin reconnait ce qui merite l'ecran (MARQUEURS_ALERTE),
            # pas a un bout de phrase qui changerait avec la phrase.
            journal(f"AVERTISSEMENT : cible « {nom_cible} » : pas de temps "
                    f"{60 * pas_initial:g} min → converti en "
                    f"{60 * PAS_ENTREE_H:g} min")
        apports.append(str(ligne[col_apport]))
        sections.append(section)
        cibles.append((t_cible, q_cible))
    return apports, sections, cibles, manquantes


def _depart_du_calage(valeurs, apports, sections, prefixe_etape):
    """
    D'ou part le calage : rend (erreur, depart, etape_reference,
    plan_reference, plan_fenetre_pleine). « depart » est l'indice du premier
    apport a caler ; « erreur », si elle n'est pas None, est le refus a
    rendre tel quel.
    """
    from calage import ETAPE_SANS_APPORT, etape_apport
    from pilote_hecras import plan_par_titre

    def texte(cle, defaut=""):
        return _texte_parametre(valeurs, cle, defaut)

    # REPRISE A UN APPORT DONNE. Les apports situes en amont de celui-ci sont
    # tenus pour cales : ils ne sont ni remis a zero, ni retouches. On repart
    # du plan de l'etape precedente, qui les porte deja — repartir du plan de
    # reference les perdrait tous, en silence.
    depart, etape_reference, reprise = 0, ETAPE_SANS_APPORT, ""
    premier = texte("Premier_apport")
    if premier:
        # Le nom de la condition limite d'abord, celui de la section de
        # controle ensuite : les deux designent la meme ligne du tableau de
        # correspondance, et l'utilisateur emploie couramment l'un pour l'autre.
        for liste in (apports, sections):
            if premier in liste:
                depart = liste.index(premier)
                break
        else:
            return (f"« Premier_apport » vaut « {premier} », qui ne figure ni "
                    f"parmi les apports {apports} ni parmi les sections "
                    f"{sections} de la feuille Correspondance.",
                    None, None, None, None)

    plan_reference = texte("Plan_reference", "p01")
    # EN REPRISE SEULEMENT : « plan_reference » devient alors le plan de
    # l'etape precedente, deja raccourci par le calage d'avant, et le pilote
    # doit savoir sur quel plan lire la fenetre pleine. En calage ordinaire
    # il la lit sur son plan de travail, qui porte la fenetre imposee s'il y
    # en a une — voir PiloteHecRas._duree_borne_h().
    plan_fenetre_pleine = None
    if depart > 0:
        deja = apports[:depart]
        etape_precedente = etape_apport(apports[depart - 1], prefixe_etape)
        # « sans apport X et aval » NE TENAIT PAS : 25 caracteres pour un nom
        # de section a cinq lettres, et il etait deja rogne en silence — un
        # plan de reprise du depot porte « sans apport XXX et ava », le « l »
        # perdu. La forme courte dit la meme chose, tient, et laisse onze
        # caracteres au prefixe de scenario.
        etape_reference = f"sans {apports[depart]} et aval"
        trouve = plan_par_titre(texte("Dossier_projet_HECRAS"),
                                texte("Nom_projet"), etape_precedente)
        if trouve:
            plan_fenetre_pleine = plan_reference
            plan_reference = f"p{trouve}"
            reprise = (f"Reprise a l'apport {apports[depart]} : {len(deja)} "
                       f"apport(s) amont {deja} tenus pour cales, depart du "
                       f"plan p{trouve} « {etape_precedente} ».")
        else:
            reprise = (
                f"AVERTISSEMENT : reprise demandee a l'apport "
                f"{apports[depart]}, mais aucun plan « {etape_precedente} » "
                f"dans le projet. Le calage part du plan de reference "
                f"{plan_reference} : les apports amont {deja} y valent ce "
                f"qu'ils y valent, et ne seront pas verifies. Si ce plan ne "
                f"les porte pas deja cales, le resultat sera faux.")
        print(reprise, flush=True)
    return None, depart, etape_reference, plan_reference, plan_fenetre_pleine


def _refus_titres_etape(etape_reference, prefixe_etape, apports):
    """Le refus a rendre si un titre d'etape est trop long, sinon None."""
    from calage import ETAPE_AVEC_APPORTS, etape_apport, titre_etape

    # LES TITRES D'ETAPE SONT VERIFIES AVANT LE PREMIER CLONAGE. Au-dela de la
    # longueur admise, HEC-RAS ne refuse pas : la chaine rognait en silence,
    # et deux etapes rognees au meme « Short Identifier » partagent le dossier
    # de resultats que RAS Mapper nomme d'apres ce champ. Le dire ici coute
    # une seconde ; s'en apercevoir apres coup coute une campagne de calculs.
    try:
        titre_etape(etape_reference, prefixe_etape)
        titre_etape(ETAPE_AVEC_APPORTS, prefixe_etape)
        for _a in apports:
            etape_apport(_a, prefixe_etape)
    except ValueError as e:
        return f"Prefixe_scenario : {e}"
    return None


def _accord_plan_final(pilote, valeurs, prefixe_etape, plan_reference,
                      plan_fenetre_pleine):
    """
    Le plan final peut-il prendre son titre ? Rend (erreur, remplacer_source) :
    « erreur », si elle n'est pas None, est le refus a rendre tel quel. Pose
    sur le pilote le plan source a remplacer, et dit au journal ce qui le
    sera.
    """
    from calage import ETAPE_AVEC_APPORTS, titre_etape
    from pilote_hecras import plans_par_titre

    def texte(cle, defaut=""):
        return _texte_parametre(valeurs, cle, defaut)

    # LE PLAN FINAL PORTE LE PREFIXE SEUL : il peut rencontrer un plan existant.
    # Deux plans ne gardent jamais ce titre : ils auraient le meme Short
    # Identifier, donc le meme dossier sous RAS Mapper.
    #   LE PLAN SOURCE n'est remplace que si l'ingenieur l'a accepte au
    # lancement (« Remplacer_plan_source = oui », recalage d'un plan valide
    # qui garde son nom, 10/11/2026), et seulement sur un calage conforme.
    # Sans ce oui, on refuse avant le premier calcul.
    #   TOUT AUTRE PLAN de ce nom est remplace a la fin du calage : le plugin
    # a demande confirmation, la ligne de commande ne le peut pas et le dit
    # au journal.
    titre_final = titre_etape(ETAPE_AVEC_APPORTS, prefixe_etape)
    homonymes = plans_par_titre(texte("Dossier_projet_HECRAS"),
                                texte("Nom_projet"), titre_final)
    plan_source = str(plan_fenetre_pleine or plan_reference).lstrip("pP").zfill(2)
    remplacer_source = (
        plan_source in homonymes
        and texte("Remplacer_plan_source", "non").lower() in ("oui", "true", "1"))
    if plan_source in homonymes and not remplacer_source:
        return (f"Prefixe_scenario : le plan source p{plan_source} s'appelle "
                f"deja « {titre_final} », le titre du plan final. Choisir un "
                f"autre prefixe, renommer ce plan dans HEC-RAS, ou accepter son "
                f"remplacement (Remplacer_plan_source = oui).", False)
    if remplacer_source:
        pilote.plan_a_remplacer = plan_source
        print(f"AVERTISSEMENT : le plan source p{plan_source} « {titre_final} » "
              f"sera remplace par le plan final si le calage est conforme. "
              f"Sinon il reste intact.", flush=True)
    autres = [n for n in homonymes if n != plan_source]
    if autres:
        print(f"AVERTISSEMENT : le plan final remplacera a la fin du calage "
              f"{', '.join(f'p{n}' for n in autres)} « {titre_final} », avec "
              f"ses resultats.", flush=True)
    return None, remplacer_source


def _configuration(valeurs, prefixe_etape, remplacer_source):
    """La Configuration de caler(), lue dans les parametres du calage."""
    from calage import Configuration

    def texte(cle, defaut=""):
        return _texte_parametre(valeurs, cle, defaut)

    def nombre(cle, defaut):
        return _nombre_parametre(valeurs, cle, defaut)

    # La precision est saisie en POURCENTAGE, la chaine raisonne en rapports.
    return Configuration(
        nb_max_essais=int(nombre("Nb_max_iterations_par_apport", 6)),
        tolerance_volume=nombre("Tolerance_volume_pct", 5.0) / 100.0,
        tolerance_pic=nombre("Tolerance_pic_pct", 2.0) / 100.0,
        # DEJA EN POURCENTAGE des deux cotes — pas de « / 100 » ici : c'est
        # une erreur de conservation du solveur, pas un rapport a la cible.
        bilan_masse_max_pct=nombre("Bilan_masse_max_pct", 5.0),
        # FENETRE DE JUGEMENT. Les deux seuils sont donnes en POURCENTAGE du
        # volume cumule du deficit. La methodologie les declare explicitement
        # « a confirmer sur les premiers cas d'application » : ils doivent
        # donc rester saisissables, et non figes dans le code.
        fenetre_seuil_bas=nombre("Fenetre_seuil_bas_pct", 0.5) / 100.0,
        fenetre_seuil_haut=nombre("Fenetre_seuil_haut_pct", 99.0) / 100.0,
        # Bornes imposees a la main, en heures depuis le debut de la cible.
        # Vides = detection automatique, qui n'est qu'une proposition.
        fenetre_t0_h=nombre("Fenetre_t0_h", None),
        fenetre_tf_h=nombre("Fenetre_tf_h", None),
        # Vide = active, le defaut. « non » juge sur toute la duree simulee.
        fenetre_active=_oui_non_ou_defaut(texte("Fenetre_active", "")),
        # Prefixe pose devant chaque titre d'etape. Vide = comportement
        # d'avant. C'est ce qui separe les plans du Q10 de ceux du Q100.
        prefixe_etape=prefixe_etape,
        remplacer_plan_source=remplacer_source)


def _construire_pilote(valeurs, plan_reference, version, pas_travail_h,
                       apports_a_caler, plan_fenetre_pleine):
    """Le PiloteHecRas du calage, regle par les parametres du classeur."""
    from pilote_hecras import PiloteHecRas

    def texte(cle, defaut=""):
        return _texte_parametre(valeurs, cle, defaut)

    def nombre(cle, defaut):
        return _nombre_parametre(valeurs, cle, defaut)

    surcharge = texte("Mode_selection_modele", "plan").lower() == "override"

    # La fenetre de simulation n'est imposee que si elle a ete saisie. Sans
    # cela, celle du plan de reference s'applique — ce qui est le bon defaut
    # tant qu'on ne substitue pas un unsteady flow d'une autre periode.
    fenetre = {cle: texte(param)
               for cle, param in (("debut", "Simulation_debut"),
                                  ("fin", "Simulation_fin"),
                                  ("intervalle_calcul", "Intervalle_calcul"),
                                  ("intervalle_sortie", "Intervalle_sortie"),
                                  ("intervalle_instantane",
                                   "Intervalle_instantane"),
                                  ("intervalle_mapping", "Intervalle_mapping"))
               if texte(param)}

    return PiloteHecRas(
        dossier_projet=texte("Dossier_projet_HECRAS"),
        nom_projet=texte("Nom_projet"),
        plan_reference=plan_reference,
        version=version,
        nom_zone_2d=texte("Nom_zone_2D") or None,
        geometrie_override=texte("Geometrie_reference") if surcharge else None,
        unsteady_override=texte("Unsteady_reference") if surcharge else None,
        nom_clone_geometrie=texte("Nom_clone_geometrie") or None,
        fenetre_simulation=fenetre or None,
        pas_travail_h=pas_travail_h,
        apports_a_caler=apports_a_caler,
        plan_fenetre_pleine=plan_fenetre_pleine,
        # 0 ou vide = le plan garde ce qu'il demande (voir PiloteHecRas).
        coeurs=int(nombre("Coeurs_par_calcul", 0)) or None,
    )


def _consigner_verdict(suivi, resultat):
    """
    Ecrit le verdict du calage au suivi ; un echec n'est qu'un avertissement.
    """
    # VERDICT DANS LE SUIVI, avant meme les livrables. Sans lui, celui qui
    # regarde l'avancement voit les fichiers cesser d'etre reecrits sans
    # savoir si le calage a abouti, echoue, ou s'il est mort en chemin.
    # Consigne aussi si l'assemblage du rapport echoue ensuite : le calage,
    # lui, est bien termine.
    try:
        suivi.conclure(resultat.conforme, resultat.motif, resultat.nb_calculs)
    except Exception as e:                                  # noqa: BLE001
        print(f"AVERTISSEMENT : verdict non consigne au suivi : {e}",
              flush=True)


def _produire_rapport(pilote, chemin_template, resultat, dossier_resultats):
    """
    Livrables finaux du calage, dans dossier_resultats. Rend ce que
    produire_livrables_finaux() rend, ou None : rien a livrer, ou echec dit
    au journal.
    """
    from calage import produire_livrables_finaux

    rapport = None
    if resultat.diagnostics_finaux:
        # PROFIL EN LONG DE SYNTHESE. Ces trois valeurs sont FACULTATIVES pour
        # produire_livrables_finaux(), qui saute la figure d'ensemble sans rien
        # dire quand elles manquent. Ne pas les passer suffisait donc a rendre
        # la figure introuvable dans les livrables de n'importe quel calage —
        # celle-la meme que reprend la note methodologique.
        profil, pk_sections, pk_apports = _profil_pour_livrables(
            pilote, chemin_template, resultat)
        try:
            rapport = produire_livrables_finaux(
                resultat, pilote, dossier_resultats,
                profil=profil, pk_sections=pk_sections,
                pk_apports=pk_apports)
        except Exception as e:
            print(f"AVERTISSEMENT : rapport final non produit : {e}", flush=True)
    return rapport


def _ranger_plans(pilote, resultat, prefixe_etape, tous_apports, elaguer):
    """
    Menage des traces de preparation puis, si « elaguer », elagage des plans
    d'etape — sur un calage conforme seulement. Rend le bilan du menage, ou
    None s'il n'a pas eu lieu.
    """
    # MENAGE. LES PLANS D'ETAPE SONT CONSERVES — « sans_apport », puis un par
    # apport : ils documentent le calage et permettent de le reprendre sans
    # repartir du premier apport. Ne partent que les traces de preparation, et
    # seulement si le calage a abouti : tant qu'il n'a pas abouti, les
    # sauvegardes horodatees sont le seul retour en arriere sur le modele.
    menage = None
    if resultat.conforme:
        try:
            menage = pilote.nettoyer_reliquats()
            if menage["reliquats"]:
                print(f"Menage : {len(menage['reliquats'])} reliquat(s) de "
                      f"preparation retire(s) — "
                      f"{', '.join(menage['reliquats'])}", flush=True)
            print(f"Plans conserves : {', '.join(menage['etapes'])}",
                  flush=True)
        except Exception as e:
            # Le menage est un confort : son echec ne doit pas faire perdre un
            # calage qui a abouti.
            print(f"AVERTISSEMENT : menage non effectue : {e}", flush=True)

        # ELAGAGE DES PLANS D'ETAPE, SI LA CASE ETAIT COCHEE. Ici et pas
        # ailleurs : le plan final vient d'etre titre, c'est le seul moment ou
        # l'operation a un sens ET ou elle est sure — elaguer_etapes refuse de
        # toute facon s'il n'existe pas.
        #   APRES LES LIVRABLES, JAMAIS AVANT : ils relisent les plans
        # d'etape. Les retirer d'abord rendrait un rapport ampute sur un
        # calage reussi, ce qui est pire que garder des plans.
        if elaguer:
            _elaguer_plans_etape(pilote, prefixe_etape, tous_apports)
    elif elaguer:
        # La case etait cochee : dire pourquoi rien n'est retire, sinon
        # l'utilisateur croit l'option cassee (modele reel, 28/09/2026).
        print("AVERTISSEMENT : elagage non fait — le calage n'est pas "
              "conforme, et ses plans d'etape sont ce qui permet de le "
              "reprendre.", flush=True)
    return menage


def _elaguer_plans_etape(pilote, prefixe_etape, tous_apports):
    """
    Retire les plans d'etape d'un calage conforme ; un echec n'est qu'un
    avertissement.
    """
    try:
        elagage = pilote.elaguer_etapes(prefixe_etape, tous_apports,
                                        simuler=False)
        if elagage.get("refus"):
            print(f"Elagage refuse : {elagage['refus']}", flush=True)
        else:
            print(f"Elagage : {len(elagage['supprimes'])} objet(s) "
                  f"retire(s) — "
                  f"{', '.join(elagage['supprimes'])}. Le plan "
                  f"« {elagage['final']} » est conserve.", flush=True)
    except Exception as e:
        # Comme le menage : un calage abouti ne se perd pas sur un
        # confort de rangement.
        print(f"AVERTISSEMENT : elagage non effectue : {e}",
              flush=True)


def commande_caler(args):
    """
    Lance la boucle de calage sequentielle COMPLETE, a partir d'un classeur
    deja compose et controle.

    C'est une operation LONGUE (potentiellement plusieurs heures) : cette
    commande n'est JAMAIS appelee via appeler_pont() (qui attend la reponse
    avec un delai court), mais via noyau.lancer_calage(), en sous-processus
    DETACHE. Le plugin repart aussitot ; le suivi (§ 4.3, dossier
    Sous_dossier_suivi) est le seul moyen de savoir ou en est le calcul
    pendant qu'il tourne.
    """
    from calage import caler
    from criteres import pas_serie_h
    from pilote_hecras import symbole_decimal
    from suivi import Suivi

    # AVANT TOUT : HEC-RAS peut-il seulement demarrer ? Voir symbole_decimal().
    decimal = symbole_decimal()
    if decimal not in (None, "."):
        return repondre(ok=False, erreur=(
            f"Windows emploie « {decimal} » comme symbole decimal : HEC-RAS "
            f"exige le point, et attendrait un clic sur un message au lieu "
            f"de calculer. Mettre « . » dans les options regionales de "
            f"Windows (Format, Parametres supplementaires, Symbole decimal), "
            f"puis relancer le calage."))

    chemin_template = Path(args.template)
    valeurs = parametres.lire(chemin_template)

    def texte(cle, defaut=""):
        return _texte_parametre(valeurs, cle, defaut)

    try:
        apports, sections, cibles, manquantes = _cibles_depuis_classeur(
            chemin_template, journal=_dire_horodate)
    except FileNotFoundError:
        return repondre(ok=False, erreur=(
            f"classeur de saisie introuvable : {chemin_template}. Verifier "
            f"son chemin avant de lancer le calage."))
    except ValueError as e:
        # Les refus que _cibles_depuis_classeur formule lui-meme (colonne
        # Temps_h absente, temps en dates) disent deja quoi corriger.
        return repondre(
            ok=False, erreur=f"classeur de saisie inexploitable : {e}")
    if manquantes:
        return repondre(ok=False, erreur=(
            f"hydrogrammes cibles manquants ou inexploitables pour : "
            f"{manquantes}. Completer la feuille Cibles avant de lancer le "
            f"calage."))
    if not apports:
        return repondre(ok=False,
                        erreur="aucun apport a caler (feuille Correspondance vide "
                               "ou toutes les cibles manquantes).")

    apports_a_caler = list(apports)
    # PAS DE TRAVAIL DE CE CALAGE : le plus fin des pas natifs des cibles
    # (criteres.pas_serie_h), jamais le plancher fige criteres.PAS_ENTREE_H —
    # normaliser_entree() (appelee par _cibles_depuis_classeur) preserve deja
    # une cible plus fine que ce plancher, mais rien en aval n'exploitait
    # cette finesse : les apports du modele, deja au bon pas, se faisaient
    # degrader vers 6 min par PiloteHecRas._recadencer_apports(), qui
    # imposait jusqu'ici un libelle fige au lieu de suivre la cible. Voir le
    # calage reel du 2026-08-05 : cible et apports natifs a
    # 3 min, plancher fige a 6 min, une condition limite hors calage restee a
    # 6 min passait alors pour conforme.
    pas_travail_h = min(
        (pas_serie_h(t) for t, _ in cibles if len(t) > 1), default=None)

    # PREFIXE DE SCENARIO. Vide = les titres d'avant. Renseigne, il rend les
    # plans du Q10 etrangers a ceux du Q100 : jalonner() remplace les
    # homonymes, et sans lui le second calage efface le premier.
    prefixe_etape = texte("Prefixe_scenario")

    erreur, depart, etape_reference, plan_reference, plan_fenetre_pleine = (
        _depart_du_calage(valeurs, apports, sections, prefixe_etape))
    if erreur:
        return repondre(ok=False, erreur=erreur)
    # Toute la serie : l'elagage retire aussi les etapes amont d'une reprise.
    tous_apports = list(apports)
    if depart > 0:
        apports, sections, cibles = (apports[depart:], sections[depart:],
                                     cibles[depart:])

    # VERSION DE HEC-RAS : le plugin la lit dans les fichiers du modele. Une
    # cellule VIDE (version illisible) partait telle quelle a ras-commander.
    version = texte("Version_HECRAS", "7.0.1")
    if not version:
        return repondre(ok=False, erreur=(
            "Version_HECRAS est vide : la version de HEC-RAS n'a pas pu etre "
            "lue dans les fichiers du modele. La renseigner dans le classeur, "
            "par exemple 7.0.1."))

    pilote = _construire_pilote(valeurs, plan_reference, version,
                                pas_travail_h, apports_a_caler,
                                plan_fenetre_pleine)

    erreur = _refus_titres_etape(etape_reference, prefixe_etape, apports)
    if erreur:
        return repondre(ok=False, erreur=erreur)

    erreur, remplacer_source = _accord_plan_final(
        pilote, valeurs, prefixe_etape, plan_reference, plan_fenetre_pleine)
    if erreur:
        return repondre(ok=False, erreur=erreur)

    config = _configuration(valeurs, prefixe_etape, remplacer_source)

    dossier_sortie = Path(texte("Dossier_sortie") or chemin_template.parent)
    sous_suivi = texte("Sous_dossier_suivi", "suivi")
    sous_resultats = texte("Sous_dossier_resultats", "resultats_finaux")
    suivi = Suivi(dossier_sortie / sous_suivi, apports, sections,
                  titre=(f"Calage des apports — {texte('Nom_projet')}"
                         + (f" (reprise à {apports[0]})" if depart else "")),
                  # Les MEMES tolerances que la boucle : l'affichage doit
                  # juger « conforme » sur les seuils de l'etude, pas sur des
                  # seuils par defaut.
                  tolerances={"volume": config.tolerance_volume,
                              "pic": config.tolerance_pic,
                              "forme": 1.0 - config.r_min})

    # PENTE DE CHAQUE APPORT. Saisie par apport dans le classeur, ou deduite
    # du profil en long — moyenne du fond sur +/- 200 m autour de l'injection,
    # majoree de 20 %. Elle est appliquee ICI et non a la creation de
    # l'injection : le classeur n'existait pas encore a ce moment-la.
    _appliquer_pentes(pilote, chemin_template, apports)

    print(f"Calage : {len(apports)} apport(s), plan de reference "
         f"{plan_reference}", flush=True)
    # QUEL PYTHON A TOURNE. Un calage de 14 h s'est termine sur « No module
    # named 'xarray' » alors que l'interpreteur verifie par le projet le porte
    # depuis juillet : il avait tourne sur un AUTRE python — ras-commander
    # 0.99.2 au journal, 0.99.1 dans le venv du projet — et rien dans le
    # journal ne disait lequel. Une ligne, et l'on sait quoi corriger.
    print(f"Interpreteur : {sys.executable}", flush=True)
    # AVEC QUEL HEC-RAS. La version suit le modele : l'ingenieur la choisit en
    # enregistrant son modele dans cette version. Le journal ne la disait
    # qu'en anglais, plus haut, dans les lignes de ras-commander.
    print(f"HEC-RAS : {version}", flush=True)
    resultat = caler(pilote, apports, sections, cibles, config, suivi=suivi,
                     journal=_dire_horodate,
                     etape_reference=etape_reference)

    _consigner_verdict(suivi, resultat)
    rapport = _produire_rapport(pilote, chemin_template, resultat,
                                dossier_sortie / sous_resultats)
    elaguer = texte("Elaguer_plans_etape", "non").lower() in ("oui", "true", "1")
    menage = _ranger_plans(pilote, resultat, prefixe_etape, tous_apports,
                           elaguer)

    return repondre(
        ok=True, conforme=resultat.conforme, motif=resultat.motif,
        duree_s=round(resultat.duree_s, 1), nb_calculs=resultat.nb_calculs,
        apports_valides=sum(a.valide for a in resultat.apports),
        apports_total=len(apports),
        dossier_suivi=str(dossier_sortie / sous_suivi),
        plan_conserve=(menage or {}).get("conserve"),
        objets_retires=(menage or {}).get("supprimes") or [],
        dossier_resultats=(str(dossier_sortie / sous_resultats)
                          if rapport else None),
        # ALERTES QUI VISENT LE CALAGE ENTIER, pas un apport. Non bloquantes :
        # elles ne touchent pas « conforme ». Sans ce relais, la coherence du
        # decalage le long de l'axe n'existait que dans le journal texte, que
        # l'utilisateur du plugin n'ouvre pas.
        alertes_chaine=list(resultat.alertes_chaine))


# ---------------------------------------------------------------------------

def construire_analyseur():
    analyseur = argparse.ArgumentParser(
        description="Pont vers HEC-RAS, appelable depuis QGIS. Repond en JSON.")
    sous = analyseur.add_subparsers(dest="commande", required=True)

    sous.add_parser("verifier", help="confirme que ras-commander est utilisable"
                    ).set_defaults(fonction=commande_verifier)

    a = sous.add_parser("lister", help="objets presents dans le modele")
    a.add_argument("--plan", required=True)
    a.set_defaults(fonction=commande_lister)

    a = sous.add_parser("hydrogramme", help="debit a une section de controle")
    a.add_argument("--plan", required=True)
    a.add_argument("--section", required=True)
    a.add_argument("--zone", default=None)
    a.add_argument("--sortie", default=None)
    a.add_argument("--groupe", default="Reference Lines",
                   choices=["Reference Lines", "Boundary Conditions"],
                   help="famille d'objets : sections de controle (defaut) ou "
                        "conditions limites, pour relire un apport injecte")
    a.set_defaults(fonction=commande_hydrogramme)

    a = sous.add_parser("modele",
                        help="couches geometriques existantes (perimetre, "
                             "sections, injections), en WKT")
    a.add_argument("--geometrie", required=True, help="fichier .gXX.hdf")
    a.set_defaults(fonction=commande_modele)

    a = sous.add_parser("pentes",
                        help="pente du fond au droit de chaque apport, pour "
                             "pre-remplir Pente_m_par_m")
    a.add_argument("--geometrie", required=True, help="fichier .gXX.hdf")
    a.add_argument("--axe", required=True, help="shapefile de l'axe")
    a.add_argument("--zone", default=None, help="zone d'ecoulement 2D")
    a.add_argument("--pk-apports", dest="pk_apports", required=True,
                   help="JSON {nom_apport: PK en m}, dans la convention de PK "
                        "de l'appelant (Sens_axe)")
    a.set_defaults(fonction=commande_pentes)

    a = sous.add_parser("controler-modele",
                        help="confronte la saisie a la geometrie reelle")
    a.add_argument("--template", required=True)
    a.add_argument("--geometrie", default=None,
                   help="geometrie HDF ; deduite du template si omise")
    a.set_defaults(fonction=commande_controler_modele)

    a = sous.add_parser("elaguer-etapes",
                        help="retire les plans d'etape d'un calage abouti")
    a.add_argument("--dossier", required=True)
    a.add_argument("--projet", required=True)
    a.add_argument("--plan-reference", required=True, dest="plan_reference")
    a.add_argument("--prefixe", default="",
                   help="prefixe de scenario du calage a elaguer")
    a.add_argument("--apports", nargs="+", required=True,
                   help="noms de tous les apports du calage")
    a.add_argument("--executer", action="store_true",
                   help="sans lui, rien n'est efface : on ne rend que la "
                        "liste de ce qui partirait")
    a.set_defaults(fonction=commande_elaguer_etapes)

    a = sous.add_parser("sections", help="cree des reference lines")
    a.add_argument("--geometrie", required=True)
    a.add_argument("--shp", required=True)
    a.add_argument("--zone", required=True)
    a.add_argument("--remplacer", action="store_true")
    a.set_defaults(fonction=commande_sections)

    a = sous.add_parser("injections",
                        help="cree des BC lines ET leur condition limite")
    a.add_argument("--geometrie", required=True)
    a.add_argument("--shp", required=True)
    a.add_argument("--zone", required=True,
                   help="zone d'ecoulement 2D de rattachement")
    a.add_argument("--remplacer", action="store_true")
    a.add_argument("--unsteady", default=None,
                   help="fichier .uXX ou creer l'hydrogramme. SANS LUI, les "
                        "lignes creees n'apportent aucun debit.")
    a.add_argument("--forme-depuis", dest="forme_depuis", default=None,
                   help="reprendre la DUREE d'une condition limite existante "
                        "(le pas, lui, reste celui de --intervalle)")
    a.add_argument("--nb-valeurs", dest="nb_valeurs", type=int, default=241,
                   help="a defaut de --forme-depuis : nombre de pas "
                        "(241 = 24 h au pas de 6 min)")
    a.add_argument("--intervalle", default=None,
                   help="pas de l'apport cree. Defaut : 6MIN, celui auquel les "
                        "cibles sont ramenees.")
    a.add_argument("--pente", type=float, default=0.01,
                   help="pente de la ligne d'energie (0,01 = 1 %%)")
    a.set_defaults(fonction=commande_injections)

    a = sous.add_parser("caler", help="lance la boucle de calage complete "
                                      "(operation LONGUE — a lancer en arriere-plan)")
    a.add_argument("--template", required=True)
    a.set_defaults(fonction=commande_caler)

    a = sous.add_parser("autotest",
                        help="verifie le lecteur de resultats sur un fichier "
                             "fabrique (aucun modele HEC-RAS necessaire)")
    a.set_defaults(fonction=commande_autotest)

    return analyseur


def commande_autotest(args):
    """
    Eprouve lire_serie_hdf sur un fichier de resultats FABRIQUE reproduisant
    les deux dispositions reellement rencontrees, et l'inversion de signe.

    Ces cas ne pouvaient pas etre couverts avant le premier calage reel : le
    modele d'essai ne comportait aucune reference line, si bien que la
    disposition matricielle n'avait jamais ete lue une seule fois.
    """
    import tempfile
    import h5py
    import numpy as np

    echecs = []

    def verifier(libelle, condition, detail=""):
        print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
              + (f"  ->  {detail}" if detail else ""))
        if not condition:
            echecs.append(libelle)

    chemin = Path(tempfile.gettempdir()) / "_essai_calage_resultats.hdf"
    temps_jours = np.linspace(0, 0.5, 25)          # 12 h, en JOURS
    debit = np.concatenate([np.linspace(10, 100, 13),
                            np.linspace(100, 20, 12)])

    with h5py.File(chemin, "w") as h:
        g = h.create_group(f"{CHEMIN_SERIES_HDF}/Reference Lines")
        # Deux lignes, pour verifier que c'est bien LA BONNE colonne qui est
        # retenue — une erreur d'indice passerait inapercue avec une seule.
        g.create_dataset("Name", data=np.array(
            [b"SECTION_A|Perimeter 1", b"SECTION_B|Perimeter 1"]))
        g.create_dataset("Flow", data=np.column_stack([-debit, 3.0 * debit]))
        g.create_dataset("Velocity", data=np.column_stack([debit, debit]))

        b = h.create_group(f"{CHEMIN_SERIES_HDF}/Boundary Conditions")
        jeu = b.create_dataset("APPORT_X",
                               data=np.column_stack([debit * 0 + 440.0, debit]))
        jeu.attrs["Columns"] = np.array([b"Stage", b"Flow"], dtype="|S16")

        t = h.create_dataset(f"{CHEMIN_SERIES_HDF}/Time", data=temps_jours)
        t.attrs["Time"] = b"days"

    print("=" * 74)
    print("AUTO-TEST DU LECTEUR DE RESULTATS  (fichier fabrique)")
    print("=" * 74)

    print("\n1. DISPOSITION MATRICIELLE (« Reference Lines »)")
    s = lire_serie_hdf(chemin, "SECTION_A", groupe="Reference Lines")
    verifier("la section est trouvee malgre le suffixe « |zone »",
             s.attrs["objet"] == "SECTION_A|Perimeter 1")
    verifier("orientation inversee detectee et corrigee",
             s.attrs["orientation_inversee"]
             and abs(s["debit_m3s"].max() - 100.0) < 1e-6,
             f"pointe {s['debit_m3s'].max():.2f}")
    verifier("ecoulement non reversible", not s.attrs["ecoulement_reversible"])
    verifier("temps converti de jours en heures",
             abs(s["temps"].max() - 12.0) < 1e-6,
             f"{s['temps'].max():.2f} h")

    s2 = lire_serie_hdf(chemin, "SECTION_B", groupe="Reference Lines")
    verifier("c'est bien la COLONNE de la section demandee qui est lue",
             abs(s2["debit_m3s"].max() - 300.0) < 1e-6,
             f"pointe {s2['debit_m3s'].max():.2f}")
    verifier("une section deja orientee dans le bon sens n'est pas retournee",
             not s2.attrs["orientation_inversee"])

    print("\n2. DISPOSITION PAR OBJET (« Boundary Conditions »)")
    a = lire_serie_hdf(chemin, "APPORT_X", groupe="Boundary Conditions")
    verifier("la colonne Flow est identifiee par l'attribut « Columns »",
             abs(a["debit_m3s"].max() - 100.0) < 1e-6,
             f"pointe {a['debit_m3s'].max():.2f}")
    verifier("la colonne Stage n'est pas confondue avec le debit",
             abs(a["debit_m3s"].min() - 10.0) < 1e-6)

    print("\n3. ERREURS EXPLICITES")
    try:
        lire_serie_hdf(chemin, "INCONNUE", groupe="Reference Lines")
        verifier("une section absente leve une erreur nommant les presentes",
                 False)
    except KeyError as e:
        verifier("une section absente leve une erreur nommant les presentes",
                 "SECTION_A" in str(e), str(e)[:60])
    try:
        lire_serie_hdf(chemin, "X", groupe="Groupe Inexistant")
        verifier("un groupe absent leve une erreur", False)
    except KeyError:
        verifier("un groupe absent leve une erreur", True)

    chemin.unlink(missing_ok=True)

    print("\n4. CIBLES : LECTURE DU CLASSEUR AU PAS DE 6 MINUTES")
    import pandas as pd

    def _lire_cibles(temps_h, debits):
        """Ecrit un classeur minimal et le relit ; retourne (cible, journal)."""
        classeur = Path(tempfile.gettempdir()) / "_essai_cibles_classeur.xlsx"
        with pd.ExcelWriter(classeur) as w:
            pd.DataFrame({
                "Ordre": [1], "Nom_Apport (BC line)": ["A1"],
                "Nom_Section (reference line)": ["SC1"], "Nom_Cible": ["C1"],
            }).to_excel(w, sheet_name="Correspondance", index=False)
            pd.DataFrame({"Temps_h": temps_h, "C1": debits}
                        ).to_excel(w, sheet_name="Cibles", index=False)
        lignes = []
        _, _, lues, _ = _cibles_depuis_classeur(classeur, journal=lignes.append)
        classeur.unlink(missing_ok=True)
        return lues[0], lignes

    # SANS COLONNE Temps_h, LE DIRE (04/09/2026). Un classeur dont l'en-tete A1
    # avait ete remplace faisait planter le pont au lancement, en arriere-plan,
    # sur « 'numpy.float64' object has no attribute 'to_numpy' » : cib.get()
    # rend None, to_numeric() un scalaire. La cause doit se lire, et l'en-tete
    # trouve a la place aussi — c'est lui qu'il faut corriger.
    _sans_temps = Path(tempfile.gettempdir()) / "_essai_cibles_sans_temps.xlsx"
    with pd.ExcelWriter(_sans_temps) as w:
        pd.DataFrame({
            "Ordre": [1], "Nom_Apport (BC line)": ["A1"],
            "Nom_Section (reference line)": ["SC1"], "Nom_Cible": ["C1"],
        }).to_excel(w, sheet_name="Correspondance", index=False)
        pd.DataFrame({"Temps (h)": [0, 1, 2], "C1": [0, 10, 0]}
                    ).to_excel(w, sheet_name="Cibles", index=False)
    try:
        _cibles_depuis_classeur(_sans_temps)
        _dit = "aucune erreur"
    except ValueError as e:
        _dit = str(e)
    except Exception as e:
        _dit = f"{type(e).__name__}: {e}"
    _sans_temps.unlink(missing_ok=True)
    verifier("sans colonne Temps_h, le lecteur nomme l'en-tete attendu et "
             "celui trouve",
             "Temps_h" in _dit and "Temps (h)" in _dit, _dit[:100])

    # UNE COLONNE DE TEMPS EN DATES NON PLUS. to_numeric rend les
    # microsecondes depuis 1970 sur une colonne de dates : le calage partait
    # et mourait plus loin, dans reechantillonner, sur une allocation de
    # 536 Gio (relecture adverse du 04/09/2026).
    import datetime as _dt
    _dates = Path(tempfile.gettempdir()) / "_essai_cibles_dates.xlsx"
    with pd.ExcelWriter(_dates) as w:
        pd.DataFrame({
            "Ordre": [1], "Nom_Apport (BC line)": ["A1"],
            "Nom_Section (reference line)": ["SC1"], "Nom_Cible": ["C1"],
        }).to_excel(w, sheet_name="Correspondance", index=False)
        pd.DataFrame({"Temps_h": [_dt.datetime(2020, 1, 1, _h)
                                  for _h in range(3)],
                      "C1": [0, 10, 0]}).to_excel(w, sheet_name="Cibles",
                                                  index=False)
    try:
        _cibles_depuis_classeur(_dates)
        _dit = "aucune erreur"
    except ValueError as e:
        _dit = str(e)
    except Exception as e:
        _dit = f"{type(e).__name__}: {e}"
    _dates.unlink(missing_ok=True)
    verifier("une colonne de temps en dates est refusee, pas convertie",
             "date" in _dit.lower() and "heures" in _dit.lower(), _dit[:100])

    # Pas horaire, comme un HSMF colle tel quel : c'est le cas courant que la
    # normalisation doit corriger avant tout calage.
    (t_c, q_c), journal_lu = _lire_cibles([0, 1, 2, 3, 4], [0, 50, 100, 40, 0])
    verifier("une cible horaire est ramenee au pas de 6 minutes",
             abs(np.max(np.diff(t_c)) - 0.1) < 1e-9,
             f"pas max {3600 * np.max(np.diff(t_c)):.0f} s sur {len(t_c)} pas")
    verifier("les bornes de temps et le pic sont conserves",
             t_c[0] == 0.0 and abs(t_c[-1] - 4.0) < 1e-9
             and abs(np.max(q_c) - 100.0) < 1e-6,
             f"{t_c[0]:.2f} -> {t_c[-1]:.2f} h, pic {np.max(q_c):.1f}")
    # La conversion DOIT se lire dans le journal : la serie calee n'est plus
    # celle qui a ete saisie, et rien d'autre ne le dirait.
    verifier("la conversion est consignee, avec le pas d'origine",
             len(journal_lu) == 1
             and "60 min → converti en 6 min" in journal_lu[0],
             journal_lu[0] if journal_lu else "aucune ligne de journal")

    # Une cible DEJA au pas de 6 min ne doit etre ni touchee ni annoncee.
    _, journal_muet = _lire_cibles([round(0.1 * i, 1) for i in range(11)],
                                   list(range(11)))
    verifier("une cible deja au bon pas ne declenche aucune conversion",
             journal_muet == [], str(journal_muet))

    # UN PAS PLUS FIN EST PRESERVE (regle du 05/08/2026) : seule une cible plus
    # GROSSIERE est densifiee. Ce controle exigeait l'inverse — la degradation
    # au pas commun de 6 min — et echouait depuis, sans que rien d'autre ne
    # l'exerce : c'est le pas de travail qui suit desormais la cible, pas la
    # cible qui suit un plancher fige (PiloteHecRas.pas_travail_h).
    (t_f, _), journal_fin = _lire_cibles([0.02 * i for i in range(51)],
                                         [0.0] * 51)
    verifier("une cible plus fine que 6 min n'est PAS degradee",
             abs(np.max(np.diff(t_f)) - 0.02) < 1e-9 and journal_fin == [],
             f"pas {np.max(np.diff(t_f)):.3f} h, journal {journal_fin}")

    print("\n5. APPORT CREE : LE PAS CHANGE, LA DUREE NON")
    # 97 valeurs au quart d'heure = 24 h. Au pas de 6 min, la meme duree en
    # demande 241 — et non 97, qui ne couvriraient que 9 h 36.
    verifier("24 h au quart d'heure font 24 h au pas de 6 min",
             _nb_valeurs_meme_duree(97, 0.25, 0.1) == 241,
             f"{_nb_valeurs_meme_duree(97, 0.25, 0.1)} valeurs")
    verifier("un modele deja au pas de 6 min garde son compte",
             _nb_valeurs_meme_duree(241, 0.1, 0.1) == 241,
             f"{_nb_valeurs_meme_duree(241, 0.1, 0.1)} valeurs")
    verifier("un modele au pas horaire est densifie sans changer de duree",
             _nb_valeurs_meme_duree(25, 1.0, 0.1) == 241,
             f"{_nb_valeurs_meme_duree(25, 1.0, 0.1)} valeurs")

    # --- PRE-VOL : LES DUREES, AVANT LE LANCEMENT ---------------------------
    # Le controle existe aussi dans preparer(), mais il n'y parle qu'au
    # journal d'un sous-processus detache. Ce qui est eprouve ici, c'est
    # qu'il NE BLOQUE PAS sur ce qu'il n'a pas su lire : un classeur
    # incomplet, un dossier absent ou un plan introuvable doivent rendre une
    # liste vide, pas une exception ni un refus. Un pre-vol qui refuse ce
    # qu'il ne comprend pas est pire qu'un pre-vol absent.
    print("\n6. PRE-VOL DES DUREES")
    import pandas as pd

    _tmp_prevol = Path(tempfile.gettempdir()) / "_essai_calage_prevol.xlsx"

    def _durees(valeurs):
        # « valeurs », non « parametres » : le module du meme nom porte
        # desormais la lecture et l'ecriture, et un parametre homonyme le
        # masquerait ici.
        parametres.ecrire(_tmp_prevol, valeurs)
        with pd.ExcelWriter(_tmp_prevol, engine="openpyxl") as w:
            pd.DataFrame({"Nom_Apport": ["A1"], "Nom_Section": ["S1"]}
                         ).to_excel(w, sheet_name="Correspondance", index=False)
        return _controler_durees_avant_calcul(_tmp_prevol)

    verifier("un dossier de projet absent ne bloque rien",
             _durees({"Dossier_projet_HECRAS": r"D:\dossier_qui_n_existe_pas",
                      "Nom_projet": "ESSAI"}) == ([], None))
    verifier("un classeur sans dossier ni projet ne bloque rien",
             _durees({"Nom_projet": ""}) == ([], None))
    _sans_feuilles = Path(tempfile.gettempdir()) / "_essai_calage_vide.xlsx"
    pd.DataFrame({"x": [1]}).to_excel(_sans_feuilles, index=False)
    import controle_donnees as _cd
    _r, _p = _controler_durees_avant_calcul(_sans_feuilles)
    verifier("un classeur illisible AVERTIT, il ne refuse pas",
             len(_r) == 1 and _r[0][0] == _cd.AVERTISSEMENT, str(_r))
    verifier("et ne propose aucune prolongation", _p is None, str(_p))

    # LES RESIDUS NE BLOQUENT RIEN, JAMAIS — et surtout ne levent pas. Ce
    # controle est purement informatif : s'il emportait son appelant, il
    # ferait echouer une composition parfaitement valide pour un constat qui
    # n'empeche aucun calage.
    def _residus(valeurs):
        # « valeurs », non « parametres » : le module du meme nom porte
        # desormais la lecture et l'ecriture, et un parametre homonyme le
        # masquerait ici.
        parametres.ecrire(_tmp_prevol, valeurs)
        with pd.ExcelWriter(_tmp_prevol, engine="openpyxl") as w:
            pd.DataFrame({"Nom_Apport": ["A1"], "Nom_Section": ["S1"]}
                         ).to_excel(w, sheet_name="Correspondance", index=False)
        return _controler_residus_unsteady(_tmp_prevol)

    verifier("les residus ne disent rien d'un modele introuvable",
             _residus({"Dossier_projet_HECRAS": r"D:\dossier_qui_n_existe_pas",
                       "Nom_projet": "ESSAI"}) == [])
    verifier("un classeur illisible ne fait pas lever les residus",
             _controler_residus_unsteady(_sans_feuilles) == [])
    verifier("le seuil de duree aberrante est un multiple, pas une constante",
             FACTEUR_DUREE_ABERRANTE >= 2, f"x{FACTEUR_DUREE_ABERRANTE}")

    _tmp_prevol.unlink(missing_ok=True)
    _sans_feuilles.unlink(missing_ok=True)

    print("\n" + "=" * 74)
    if echecs:
        print(f"{len(echecs)} ECHEC(S) : {echecs}")
    else:
        print("Le lecteur gere les deux dispositions et l'orientation.")
    print("=" * 74)
    return 1 if echecs else 0


def main(argv=None):
    args = construire_analyseur().parse_args(argv)
    try:
        return args.fonction(args)
    except Exception as e:
        import traceback
        return repondre(ok=False, erreur=f"{type(e).__name__}: {e}",
                        trace=traceback.format_exc())


if __name__ == "__main__":
    sys.exit(main())
