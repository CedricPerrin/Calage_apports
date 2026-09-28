# -*- coding: utf-8 -*-
"""
Declinaison HEC-RAS de l'interface Modele : ce qui relie la boucle de calage
au solveur.

Toute la connaissance des formats de fichier, du lancement du calcul et de la
lecture des resultats est ici, et nulle part ailleurs. La boucle (calage.py)
ne connait de ce module que quatre methodes.

Deux precautions de fond, l'une et l'autre issues de l'usage :

  - LE PLAN D'ORIGINE N'EST JAMAIS MODIFIE. Le pilote clone plan et fichier
    unsteady, et ne travaille que sur les copies. On ecrit dans un projet
    d'etude ;
  - LES HYDROGRAMMES SONT MIS A L'ECHELLE DEPUIS L'ORIGINAL, jamais depuis la
    valeur precedemment ecrite. Le format a largeur fixe quantifie les
    valeurs — mesure : 5.10^-6 en relatif — et remettre a l'echelle un
    resultat deja quantifie accumulerait l'erreur essai apres essai.

Usage :  python pilote_hecras.py --projet <dossier> --plan p01
             (diagnostic de raccordement, sans lancer de calcul)
"""

import math
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from calage import (ETAPE_AVEC_APPORTS, ETAPE_SANS_APPORT,
                    LONGUEUR_MAX_TITRE_PLAN, Modele, PREFIXE_ETAPE_APPORT,
                    ResultatCalcul, titre_etape)

# LE PLAFOND DE ras-commander, AFFIRME ICI PARCE QUE C'EST ICI QU'IL S'APPLIQUE.
# jalonner() passe le titre d'etape a clone_plan(new_title=) et
# clone_unsteady(new_title=), qui LEVENT ValueError au-dela de 32 (0.99.1 :
# « Plan title must be 32 characters or less »). Relever
# LONGUEUR_MAX_TITRE_PLAN sans cesser de passer « new_title= » deplacerait
# simplement le refus du controle du classeur vers le milieu du calage, apres
# le calcul de reference. Voir le commentaire de la constante dans calage.py.
assert LONGUEUR_MAX_TITRE_PLAN <= 32, (
    "LONGUEUR_MAX_TITRE_PLAN passe le plafond de clone_plan/clone_unsteady "
    "(32) : titrer par _renommer_plan / _renommer_unsteady seuls avant de "
    "le relever.")

# Les mois d'un plan HEC-RAS sont ecrits en anglais, sur trois lettres
# majuscules. Une date construite avec les mois de la machine — « OCT » en
# francais, mais « MAI », « FEV »... — serait refusee, ou pire, mal lue.
MOIS_HECRAS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
               "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

# Format d'un instant : 13OCT2014,00:00 — ou 13OCT2014,0000.
#
# HEC-RAS ecrit les DEUX formes, y compris dans un meme projet : les plans
# anciens portent « 00:00 » et ceux edites par l'interface 6.41 portent
# « 0000 ». N'accepter que l'une des deux ferait rejeter un plan parfaitement
# valide au moment de pre-remplir la fenetre.
_INSTANT = re.compile(r"^(0[1-9]|[12]\d|3[01])(" + "|".join(MOIS_HECRAS)
                      + r")(\d{4}),([01]\d|2[0-4]):?([0-5]\d)$")
# Format d'un intervalle : 1SEC, 0.2SEC, 1MIN, 10MIN, 1HOUR...
_INTERVALLE = re.compile(r"^\d+(\.\d+)?(SEC|MIN|HOUR|DAY|WEEK|MONTH|YEAR)$")

# Intervalle PAR DEFAUT, quand aucun pas natif n'a pu etre determine depuis
# la cible (PiloteHecRas.pas_travail_h absent). Six minutes, le plancher
# historique de criteres.PAS_ENTREE_H — mais normaliser_entree() PRESERVE une
# cible deja plus fine que ce plancher (3 min, par exemple) : imposer ce
# libelle fige dans ce cas degraderait a tort des apports deja au bon pas, et
# masquerait un intervalle errant sur une condition limite non pilotee. Voir
# PiloteHecRas._recadencer_apports(), qui prefere toujours pas_travail_h.
INTERVALLE_APPORT = "6MIN"

# Les quatre intervalles d'un plan, avec le libelle de l'interface HEC-RAS.
INTERVALLES_PLAN = {
    "intervalle_calcul": ("Computation Interval", "Computation Interval"),
    "intervalle_sortie": ("Output Interval", "Output Interval"),
    "intervalle_instantane": ("Instantaneous Interval",
                              "Detailed Output Interval"),
    "intervalle_mapping": ("Mapping Interval", "Mapping Output Interval"),
}


def instant_hecras(texte):
    """
    Valide un instant au format d'un plan HEC-RAS et le rend normalise.

    La validation est stricte a dessein : une date mal formee n'est pas
    refusee par HEC-RAS, elle est interpretee autrement — le calcul tourne
    alors sur une fenetre fausse, et rien dans les resultats ne le signale.

    TROIS ECRITURES SONT ACCEPTEES, parce que HEC-RAS les produit toutes :
      - la casse du mois est libre (« 01Jan2000 » comme « 01JAN2000 ») ;
      - l'heure s'ecrit avec ou sans deux-points (« 00:00 » ou « 0000 ») ;
      - 24:00 designe MINUIT EN FIN DE JOURNEE, convention HEC : « 01JAN2000,
        2400 » est le meme instant que « 02JAN2000,00:00 ». C'est ainsi
        qu'HEC-RAS ecrit la fin d'une simulation d'une journee pleine, et le
        refuser bloquait le calage sur un plan parfaitement valide (releve le
        31/08/2026 en eprouvant la portabilite sur un second poste).

    LA SORTIE EST TOUJOURS NORMALISEE sur la forme a deux-points et sur une
    heure de 00 a 23, la journee suivante prenant le relais s'il le faut.
    Ecrire une seule forme evite qu'un projet melange les deux au gre des
    plans clones, et garde _en_minutes() — qui compare des instants — a
    l'abri d'une heure 24 qu'il compterait comme un jour de plus.
    """
    t = str(texte).strip().upper().replace(" ", "")
    trouve = _INSTANT.match(t)
    if not trouve:
        raise ValueError(
            f"instant « {texte} » invalide : attendu JJMMMAAAA,HH:MM avec un "
            f"mois anglais sur trois lettres ({', '.join(MOIS_HECRAS[:3])}...), "
            f"par exemple 13OCT2014,00:00")
    jour, mois, annee, h, mn = trouve.groups()
    if h == "24":
        # 24:30 n'a aucun sens : minuit est un INSTANT, pas une heure ou l'on
        # peut avancer. La regex laisse passer les minutes, c'est ici qu'on
        # tranche.
        if mn != "00":
            raise ValueError(
                f"instant « {texte} » invalide : 24:00 designe minuit en fin "
                f"de journee, et n'admet donc pas de minutes ({mn} lu).")
        # LA DATE SE CONSTRUIT ICI SANS L'HEURE, et non par _en_datetime() :
        # h vaut « 24 », que datetime refuse. C'est justement ce que cette
        # branche est en train de corriger.
        veille = datetime(int(annee), MOIS_HECRAS.index(mois) + 1, int(jour))
        return _en_texte_hecras(veille + timedelta(days=1))
    return f"{jour}{mois}{annee},{h}:{mn}"


def _en_datetime(instant):
    """
    Instant HEC-RAS valide -> datetime. SOURCE UNIQUE de cette conversion.

    Elle etait recopiee a trois endroits, et l'une des trois copies comptait
    31 jours par mois : un modele traversant fin fevrier voyait toutes ses
    conditions declarees trop courtes (voir _en_minutes). Trois copies d'un
    meme calcul finissent toujours par diverger — il n'y en a plus qu'une.

    L'instant DOIT avoir ete valide par instant_hecras() : l'heure y vaut 00 a
    23, la forme 24:00 ayant deja bascule sur le lendemain.
    """
    jour, mois, annee, h, mn = _INSTANT.match(instant).groups()
    return datetime(int(annee), MOIS_HECRAS.index(mois) + 1, int(jour),
                    int(h), int(mn))


def _en_texte_hecras(quand):
    """datetime -> instant HEC-RAS « JJMMMAAAA,HH:MM ». Inverse du precedent."""
    return (f"{quand.day:02d}{MOIS_HECRAS[quand.month - 1]}"
            f"{quand.year:04d},{quand.hour:02d}:{quand.minute:02d}")


def intervalle_hecras(texte):
    """Valide un intervalle de plan (« 1SEC », « 5MIN »...)."""
    t = str(texte).strip().upper().replace(" ", "")
    if not _INTERVALLE.match(t):
        raise ValueError(
            f"intervalle « {texte} » invalide : attendu un nombre suivi de "
            f"SEC, MIN, HOUR, DAY... par exemple 1SEC ou 5MIN")
    return t


def intervalle_hecras_depuis_heures(pas_h):
    """
    Traduit un pas en heures vers le libelle HEC-RAS le plus proche, en
    minutes entieres (« 3MIN », « 60MIN »...).

    Sert a faire suivre a l'ecriture (INTERVALLE_APPORT) le pas REELLEMENT lu
    dans la cible, plutot qu'un libelle fige : voir PiloteHecRas.pas_travail_h.
    """
    minutes = float(pas_h) * 60.0
    arrondi = round(minutes)
    if arrondi < 1 or abs(minutes - arrondi) > 1e-6:
        raise ValueError(
            f"pas de {pas_h:g} h non representable en minutes entieres pour "
            f"un intervalle HEC-RAS.")
    return f"{arrondi}MIN"


def valider_fenetre_simulation(fenetre):
    """
    Traduit une fenetre de simulation en lignes de fichier de plan.

    fenetre : dict aux cles « debut », « fin » (instants) et aux cles
    d'INTERVALLES_PLAN. Toutes facultatives — ce qui manque reste celui du plan
    de reference. Retourne {ligne_du_plan: valeur}.
    """
    champs = {}
    debut, fin = fenetre.get("debut"), fenetre.get("fin")
    if bool(debut) != bool(fin):
        # Ecrire la moitie d'une fenetre laisserait l'autre borne a la valeur
        # du plan de reference : une periode composite que personne n'a voulue.
        raise ValueError(
            "fenetre de simulation incomplete : le debut et la fin doivent "
            "etre fournis ensemble.")
    if debut and fin:
        d, f = instant_hecras(debut), instant_hecras(fin)
        if _en_minutes(d) >= _en_minutes(f):
            raise ValueError(
                f"fenetre de simulation vide ou inversee : debut {d}, fin {f}.")
        champs["Simulation Date"] = f"{d},{f}"
    for cle, (ligne, _) in INTERVALLES_PLAN.items():
        if fenetre.get(cle):
            champs[ligne] = intervalle_hecras(fenetre[cle])
    return champs


def _en_minutes(instant):
    """
    Instant valide -> minutes depuis une origine fixe, pour comparer et pour
    MESURER UNE DUREE.

    LE CALENDRIER EST REEL. Cette fonction comptait auparavant 31 jours par
    mois, ce qui suffit a ORDONNER deux instants mais fausse toute
    SOUSTRACTION des qu'ils encadrent la fin d'un mois plus court : 28 fevrier
    -> 1er mars ressortait a 96 h au lieu de 24. Or la duree ainsi calculee est
    celle de la fenetre de simulation, a laquelle conditions_trop_courtes()
    confronte chaque condition limite — un modele parfaitement valide dont la
    simulation enjambe une fin de fevrier, d'avril, de juin, de septembre ou
    de novembre voyait donc TOUTES ses conditions declarees trop courtes, et
    le calage refuse avant tout calcul. Releve le 31/08/2026.

    L'instant DOIT avoir ete valide par instant_hecras() : l'heure y vaut 00 a
    23, la forme 24:00 ayant deja bascule sur le lendemain.
    """
    return int((_en_datetime(instant)
                - datetime(1900, 1, 1)).total_seconds() // 60)


def fenetre_simulation_du_plan(fichier_plan):
    """
    Fenetre de simulation lue dans un fichier de plan, pour pre-remplir une
    saisie. Retourne un dict aux memes cles que valider_fenetre_simulation,
    les valeurs absentes etant des chaines vides.
    """
    fenetre = {c: "" for c in ("debut", "fin", *INTERVALLES_PLAN)}
    for ligne in _lire_lignes(Path(fichier_plan)):
        if ligne.startswith("Simulation Date="):
            morceaux = ligne.split("=", 1)[1].strip().split(",")
            if len(morceaux) == 4:
                fenetre["debut"] = f"{morceaux[0]},{morceaux[1]}"
                fenetre["fin"] = f"{morceaux[2]},{morceaux[3]}"
        for cle, (nom_ligne, _) in INTERVALLES_PLAN.items():
            if ligne.startswith(nom_ligne + "="):
                fenetre[cle] = ligne.split("=", 1)[1].strip()
    return fenetre

MOTIF_HYDROGRAMME = "Flow Hydrograph="
MOTIF_LOCALISATION = "Boundary Location="


# ---------------------------------------------------------------------------
# Lecture de la structure d'un fichier unsteady
# ---------------------------------------------------------------------------

def _lire_texte(chemin):
    """
    Lit un fichier texte HEC-RAS en essayant plusieurs encodages.

    PAS DE errors=\"replace\" SUR UN FICHIER QU'ON REECRIT. C'etait le cas
    ici : un .prj ou un .pXX ecrit par l'interface en cp1252 — un titre de
    plan accentue suffit — se relisait avec des U+FFFD a la place des
    accents, et la reecriture les gravait dans le fichier de l'utilisateur.
    L'ordre des tentatives est celui de ras-commander : utf-8 d'abord, puis
    les deux encodages que Windows utilise en pratique. Le repli final ne
    sert que pour un fichier reellement binaire, cas ou l'on a de toute
    facon perdu.

    Meme politique que calage_apports.noyau._lire_texte_hecras et
    elaguer_projet._lire_texte : ces trois modules ne peuvent PAS partager
    de code (le plugin est livre seul dans son zip, elaguer_projet ne
    depend que de la bibliotheque standard). La duplication est assumee ;
    toute correction ici doit etre reportee aux deux autres.
    """
    chemin = Path(chemin)
    for encodage in ("utf-8", "latin1", "cp1252"):
        try:
            return chemin.read_text(encoding=encodage)
        except (UnicodeDecodeError, LookupError):
            continue
    return chemin.read_text(encoding="latin1", errors="replace")


def _lire_lignes(chemin):
    return _lire_texte(chemin).splitlines(keepends=True)


def _ecrire_texte(chemin, texte):
    """
    Reecrit un fichier texte HEC-RAS, dans l'encodage ou il se relit.

    L'UTF-8 D'ABORD, COMME A LA LECTURE. Un .rasmap sans declaration
    d'encodage — c'est le cas, il commence par « <RASMapper> » sans prologue
    XML — est lu en UTF-8 par RAS Mapper. Mais un fichier qui ne s'encode
    PAS en UTF-8 sans perte n'existe pas ; le repli cp1252 ne sert qu'aux
    fichiers que HEC-RAS a lui-meme ecrits en cp1252 et qu'on ne veut pas
    convertir sous pretexte qu'on y a touche une ligne.
    """
    chemin = Path(chemin)
    ancien = chemin.read_bytes() if chemin.is_file() else b""
    encodage = "utf-8"
    if ancien:
        try:
            ancien.decode("utf-8")
        except UnicodeDecodeError:
            encodage = "cp1252"
    chemin.write_text(texte, encoding=encodage)


def _echapper_xml(valeur):
    """Les cinq caracteres que XML ne laisse pas passer dans un attribut."""
    return (str(valeur).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;")
            .replace("'", "&apos;"))


def _intervalle_en_heures(texte):
    """Convertit un intervalle HEC-RAS (« 15MIN », « 1HOUR ») en heures."""
    correspondance = re.match(r"\s*(\d+)\s*([A-Za-z]+)", str(texte))
    if not correspondance:
        return None
    valeur, unite = int(correspondance.group(1)), correspondance.group(2).upper()
    facteurs = {"SEC": 1 / 3600, "MIN": 1 / 60, "HOUR": 1.0, "HR": 1.0,
                "DAY": 24.0}
    for cle, facteur in facteurs.items():
        if unite.startswith(cle):
            return valeur * facteur
    return None


def _champ(texte, largeur):
    """Champ a largeur fixe du format HEC-RAS : cale a gauche, complete."""
    texte = str(texte)
    if len(texte) > largeur:
        raise ValueError(
            f"« {texte} » depasse la largeur {largeur} imposee par le format "
            f"HEC-RAS. Un nom tronque ne serait plus apparie a la BC line de "
            f"la geometrie, et l'apport serait silencieusement ignore.")
    return texte.ljust(largeur)


def ligne_localisation(nom, nom_zone_2d):
    """
    Ligne « Boundary Location= » au format a largeur fixe de HEC-RAS.

    Largeurs relevees sur des fichiers reels : 16, 16, 8, 8, 16, 16 (zone 2D),
    16, 32 (nom de la BC line), 32. Le nom et la zone doivent correspondre
    EXACTEMENT a ceux de la geometrie, sans quoi HEC-RAS ne rattache pas la
    condition limite et l'apport reste sans effet.
    """
    return (MOTIF_LOCALISATION
            + ",".join([_champ("", 16), _champ("", 16), _champ("", 8),
                        _champ("", 8), _champ("", 16),
                        _champ(nom_zone_2d, 16), _champ("", 16),
                        _champ(nom, 32), _champ("", 32)]))


def _table_debits(valeurs, par_ligne=10, largeur=8):
    """Table de debits au format a largeur fixe, 10 valeurs par ligne."""
    lignes, tampon = [], []
    for v in valeurs:
        texte = f"{float(v):{largeur}.2f}"
        if len(texte) > largeur:                     # tres grands debits
            texte = f"{float(v):{largeur}.1f}"
        if len(texte) > largeur:
            texte = f"{float(v):{largeur}.0f}"
        if len(texte) > largeur:
            raise ValueError(f"debit {v} intracable sur {largeur} caracteres")
        tampon.append(texte)
        if len(tampon) == par_ligne:
            lignes.append("".join(tampon))
            tampon = []
    if tampon:
        lignes.append("".join(tampon))
    return lignes


def ajouter_condition_limite_debit(fichier_unsteady, nom, nom_zone_2d, debits,
                                   intervalle=INTERVALLE_APPORT, pente=0.01):
    """
    Ajoute au fichier unsteady le bloc de condition limite « Flow Hydrograph »
    correspondant a une BC line qui vient d'etre creee dans la geometrie.

    PIECE MANQUANTE DE LA CHAINE, comblee ici : ecrire_dans_geometrie() cree
    bien la BC line dans le fichier .gXX, mais une BC line sans bloc dans le
    fichier unsteady n'a AUCUN hydrogramme — l'apport existe geometriquement
    et n'injecte rien. ras-commander ne sait pas davantage creer ce bloc :
    RasUnsteady.set_boundary_inline_hydrograph() ne fait que remplacer la
    table d'une condition limite DEJA presente (elle retourne False si elle
    ne la trouve pas).

    pente : « Flow Hydrograph Slope », pente de la ligne d'energie utilisee
        par HEC-RAS pour repartir le debit sur la ligne (0,01 = 1 %).

    Le bloc est insere AVANT la premiere condition limite existante : l'ordre
    n'a pas de sens pour HEC-RAS, qui apparie par nom et par zone, et cela
    evite d'avoir a detecter la fin d'un bloc precedent.

    Retourne le nombre de valeurs ecrites.
    """
    chemin = Path(fichier_unsteady)
    lignes = _lire_lignes(chemin)

    deja = [i for i, l in enumerate(lignes)
            if l.startswith(MOTIF_LOCALISATION) and f",{_champ(nom, 32)}," in l]
    if deja:
        raise ValueError(
            f"une condition limite « {nom} » existe deja dans "
            f"{chemin.name} (ligne {deja[0] + 1}). Ajouter un doublon "
            f"produirait deux blocs de meme nom, dont un seul serait pris en "
            f"compte, et le calage piloterait peut-etre le mauvais.")

    valeurs = [float(v) for v in debits]
    if len(valeurs) < 2:
        raise ValueError("un hydrogramme demande au moins deux valeurs")

    bloc = [ligne_localisation(nom, nom_zone_2d),
            f"Interval={intervalle}",
            f"{MOTIF_HYDROGRAMME} {len(valeurs)} "]
    bloc += _table_debits(valeurs)
    bloc += ["Stage Hydrograph TW Check=0",
             f"Flow Hydrograph Slope= {pente} ",
             "DSS Path=",
             "Use DSS=False",
             "Use Fixed Start Time=False",
             "Fixed Start Date/Time=,",
             "Is Critical Boundary=False",
             "Critical Boundary Flow="]
    bloc = [l + "\n" for l in bloc]

    insertion = next((i for i, l in enumerate(lignes)
                      if l.startswith(MOTIF_LOCALISATION)), None)
    if insertion is None:
        raise ValueError(
            f"{chemin.name} ne contient aucune condition limite : ce n'est "
            f"probablement pas un fichier unsteady exploitable.")

    lignes[insertion:insertion] = bloc
    chemin.write_text("".join(lignes), encoding="utf-8")
    return len(valeurs)


def imposer_intervalle_apport(fichier_unsteady, nom, nom_zone_2d=None,
                              intervalle=INTERVALLE_APPORT, duree_min_h=None):
    """
    Re-cadence l'hydrogramme d'un apport DEJA present, au pas demande.

    Complement de ajouter_condition_limite_debit(), qui ne sait que CREER un
    bloc. Un modele livre par l'utilisateur porte ses apports au pas de sa
    source — le pas horaire est le cas courant — alors que la chaine ramene
    les cibles a 6 minutes : definir_forme() projetait alors la cible sur une
    grille horaire, et les 9/10 de l'information saisie etaient perdus a
    l'ecriture, sans qu'aucun message ne le dise.

    CE QUI EST CONSERVE, C'EST LA DUREE, jamais le nombre de valeurs. N
    valeurs decrivent N-1 intervalles : 240 valeurs au pas horaire couvrent
    239 h, et il en faut 2391 pour couvrir les memes 239 h au pas de 6 min.
    Garder le compte aurait raccourci la fenetre d'un facteur dix, et
    l'apport aurait cesse d'injecter au bout de 23 h 54 sans que HEC-RAS s'en
    plaigne.

    Les valeurs sont interpolees lineairement sur la nouvelle grille. Aux
    instants de l'ancienne grille, elles sont donc INCHANGEES : le pic d'un
    hydrogramme horaire reste a la valeur et a l'heure ou il etait.

    L'EN-TETE DU BLOC EST REECRITE — « Interval= » et « Flow Hydrograph= N ».
    C'est ce que la chaine s'interdisait jusqu'ici, et la raison en tient :
    une en-tete fausse fait lire a HEC-RAS un tableau tronque, sans erreur.
    Les deux lignes sont donc reecrites ENSEMBLE avec le tableau, et le
    resultat est immediatement relu (verifier_intervalle_apports) avant tout
    calcul.

    Retourne un compte rendu, ou None si l'apport est deja au pas demande —
    auquel cas le fichier n'est pas touche.
    """
    intervalle = intervalle_hecras(intervalle)
    pas_apres = _intervalle_en_heures(intervalle)
    if not pas_apres:
        raise ValueError(
            f"intervalle « {intervalle} » non convertible en heures : le "
            f"nombre de valeurs ne peut pas en etre deduit.")

    chemin = Path(fichier_unsteady)
    carte = cartographier_hydrogrammes(chemin, nom_zone_2d)
    if nom not in carte:
        raise ValueError(
            f"« {nom} » n'a pas d'hydrogramme de debit dans {chemin.name}. "
            f"Presents : {sorted(carte) or 'aucun'}.")
    info = carte[nom]
    pas_avant = info["intervalle_h"]
    if not pas_avant:
        raise ValueError(
            f"intervalle de temps illisible pour « {nom} » dans "
            f"{chemin.name} : la ligne « Interval= » de son bloc est absente "
            f"ou non reconnue. Le re-cadencer supposerait de deviner la base "
            f"de temps actuelle.")

    valeurs = lire_hydrogramme_unsteady(chemin, info["debut"], info["fin"])
    if len(valeurs) < 2:
        raise ValueError(
            f"l'hydrogramme de « {nom} » ne compte que {len(valeurs)} "
            f"valeur(s) : rien a re-cadencer.")
    duree_h = (len(valeurs) - 1) * pas_avant
    # PROLONGEMENT PAR DES ZEROS, POUR LES SEULS APPORTS QUE LE CALAGE PILOTE.
    #
    # Un modele livre porte souvent des apports plus courts que la fenetre de
    # simulation : ils viennent d'un evenement plus bref, ou d'une version
    # anterieure. HEC-RAS refuse alors de calculer, et l'utilisateur se
    # retrouve a devoir rallonger a la main douze hydrogrammes... que le
    # calage va de toute facon REECRIRE des le premier essai. C'est un travail
    # sans objet, et le message qui le demandait etait faux.
    #
    # POURQUOI ZERO ET NON LA DERNIERE VALEUR : np.interp tient la derniere
    # valeur au-dela du domaine, ce qui injecterait un debit constant sur des
    # heures. Un apport dont la serie s'arrete est un apport qui ne donne plus
    # rien.
    # POURQUOI C'EST SANS CONSEQUENCE : au calcul de reference l'apport est
    # mis a zero partout, et des le premier essai definir_forme() reecrit la
    # serie entiere sur la base de temps de la cible. La valeur de remplissage
    # n'entre donc dans aucun calcul — elle ne sert qu'a ce que le bloc ait la
    # bonne longueur quand HEC-RAS le lit.
    if duree_min_h and duree_min_h > duree_h + 1e-9:
        manque = int(math.ceil((duree_min_h - duree_h) / pas_avant - 1e-9))
        valeurs = np.concatenate([np.asarray(valeurs, dtype=float),
                                  np.zeros(manque)])
        duree_h = (len(valeurs) - 1) * pas_avant
    elif abs(pas_avant - pas_apres) <= 1e-12:
        return None

    # La duree n'est pas toujours un multiple entier du nouveau pas : 0,75 h
    # ne fait pas un compte rond de 6 min. On PROLONGE alors jusqu'au pas
    # suivant, jamais on ne raccourcit — np.interp tient la derniere valeur,
    # ce qui ajoute au plus un pas de queue plate. Raccourcir aurait ampute la
    # fin de l'hydrogramme, et une decrue tronquee se lit comme un defaut de
    # volume que le calage passerait ses essais a compenser. L'ecart est
    # rapporte dans le compte rendu.
    nb_apres = int(math.ceil(duree_h / pas_apres - 1e-9)) + 1
    nouvelles = np.interp(np.arange(nb_apres) * pas_apres,
                          np.arange(len(valeurs)) * pas_avant, valeurs)

    lignes = _lire_lignes(chemin)
    # L'en-tete du tableau precede immediatement ses donnees ; la ligne
    # « Interval= » precede l'en-tete, dans le meme bloc. On remonte plutot
    # que de supposer un ecart fixe : les blocs reels portent un nombre
    # variable de lignes selon le type de condition limite.
    entete = next((j for j in range(info["debut"] - 1, -1, -1)
                   if lignes[j].startswith(MOTIF_HYDROGRAMME)), None)
    ligne_intervalle = next((j for j in range(entete or 0, -1, -1)
                             if lignes[j].startswith("Interval=")), None)
    if entete is None or ligne_intervalle is None:
        raise ValueError(
            f"bloc de « {nom} » incomplet dans {chemin.name} : en-tete "
            f"« {MOTIF_HYDROGRAMME} » ou ligne « Interval= » introuvable.")

    # Les deux lignes d'en-tete AVANT le tableau : elles le precedent, leurs
    # indices ne bougent donc pas quand le tableau change de longueur.
    lignes[ligne_intervalle] = f"Interval={intervalle}\n"
    lignes[entete] = f"{MOTIF_HYDROGRAMME} {nb_apres} \n"
    lignes[info["debut"]:info["fin"]] = [l + "\n" for l
                                         in _table_debits(nouvelles)]
    chemin.write_text("".join(lignes), encoding="utf-8")

    return {"nom": nom, "zone": info["zone"], "duree_h": duree_h,
            "duree_apres_h": (nb_apres - 1) * pas_apres,
            "prolonge_h": (nb_apres - 1) * pas_apres - duree_h,
            "intervalle_avant_h": pas_avant, "intervalle_apres": intervalle,
            "nb_avant": len(valeurs), "nb_apres": nb_apres,
            "pic_avant": float(np.max(valeurs)),
            "pic_apres": float(np.max(nouvelles))}


def conditions_trop_courtes(fichier_unsteady, fichier_plan, nom_zone_2d=None,
                            noms_connus=None, apports_a_caler=None):
    """
    Conditions limites dont la serie s'arrete AVANT la fin de la simulation.

    HEC-RAS refuse alors de calculer, et le dit dans <plan>.data_errors.txt :

        Boundary at 2D: Perimeter 1 BCLine: in
              Time series data ends before the end of the simulation.

    Mais ras-commander rapporte le calcul REUSSI, et le calage ne s'en apercoit
    qu'a la lecture du .hdf absent — apres avoir depense un calcul, sans jamais
    nommer la condition en cause. Ce controle-ci se fait AVANT tout calcul, et
    la nomme.

    POURQUOI CE N'EST PAS COUVERT PAR verifier_intervalle_apports() : celui-ci
    compare le N annonce par « Flow Hydrograph= » au nombre de valeurs
    reellement presentes. Les deux peuvent s'accorder parfaitement sur une
    serie qui ne couvre que la moitie de la simulation — c'est exactement ce
    qui est arrive sur un modele reel (202 = 202, et 20,10 h pour 33 h simulees).

    N valeurs au pas p couvrent (N-1) x p heures, jamais N x p.

    noms_connus : voir cartographier_hydrogrammes. Un bloc ORPHELIN — sans BC
        line en geometrie — ne doit pas faire refuser un calage : HEC-RAS ne
        l'ouvrira pas.
    apports_a_caler : noms des apports pilotes par CE calage. Sert uniquement
        a RANGER le resultat, pas a filtrer : un apport trop court se rallonge
        cote classeur, une alimentation amont trop courte dans le modele
        source, et le message doit dire de quel cote regarder.

    Retourne {nom: {"duree_h", "simulation_h", "nb", "intervalle_h",
    "a_caler"}}, VIDE si tout couvre la fenetre — ou si celle-ci n'est pas
    lisible dans le plan, auquel cas on ne bloque rien : mieux vaut laisser
    HEC-RAS trancher que refuser un calage sur une fenetre qu'on n'a pas su
    lire.
    """
    if fichier_plan is None or not Path(fichier_plan).is_file():
        return {}
    fenetre = fenetre_simulation_du_plan(fichier_plan)
    if not (fenetre.get("debut") and fenetre.get("fin")):
        return {}
    simulation_h = (_en_minutes(instant_hecras(fenetre["fin"]))
                    - _en_minutes(instant_hecras(fenetre["debut"]))) / 60.0

    a_caler = set(apports_a_caler or ())
    courtes = {}
    for nom, info in cartographier_hydrogrammes(fichier_unsteady, nom_zone_2d,
                                                noms_connus).items():
        pas = info["intervalle_h"]
        if not pas:
            continue
        valeurs = lire_hydrogramme_unsteady(fichier_unsteady,
                                               info["debut"], info["fin"])
        duree_h = (len(valeurs) - 1) * pas if len(valeurs) > 1 else 0.0
        # TOLERANCE D'UN PAS : une serie qui s'arrete pile a la fin de la
        # simulation est acceptee par HEC-RAS, et l'arrondi de la minute ne
        # doit pas faire refuser un modele qui tourne.
        if duree_h < simulation_h - 1e-9:
            courtes[nom] = {"duree_h": duree_h, "simulation_h": simulation_h,
                            "nb": len(valeurs), "intervalle_h": pas,
                            "a_caler": nom in a_caler}
    return courtes


def pretraitement_perime(fichier_geometrie):
    """
    Le prétraitement 2D d'une geometrie est-il plus ancien qu'elle ?

    Retourne {"geometrie_h", "hdf_h", "taille_hdf_mo"} — l'age en heures de
    chacun — ou None si la question n'a pas de sens ici : .gXX absent, ou
    .gXX.hdf jamais produit (geometrie neuve, jamais pretraitee).

    POURQUOI CE CONTROLE EXISTE. Ecrire dans le .gXX — ce que fait « Composer
    et controler » a chaque passage — PERIME le .gXX.hdf, et HEC-RAS refait
    alors ses tables 2D au calcul suivant. Sur un modele leger c'est une
    affaire de secondes. Sur un modele lourd, c'est long et cela peut ECHOUER :
    releve le 31/08/2026, « Computing 2D Flow Area tables: Associated terrain
    has been updated. Geometry Writer Failed » — un terrain de 17,7 Go traverse
    par le reseau, et 98 secondes perdues avant que le calage ne s'arrete sur
    un calcul de reference sans resultats.

    ON NE BLOQUE PAS, ON PREVIENT. Le pretraitement perime est l'etat NORMAL
    juste apres une composition, et HEC-RAS le refait tres bien la plupart du
    temps. En faire une erreur bloquerait le cas courant pour un risque qui ne
    se realise que sur les gros modeles.
    """
    g = Path(fichier_geometrie)
    hdf = g.with_suffix(g.suffix + ".hdf")
    if not g.is_file() or not hdf.is_file():
        return None
    t_g, t_h = g.stat().st_mtime, hdf.stat().st_mtime
    if t_h >= t_g:
        return None
    maintenant = time.time()
    return {"geometrie_h": (maintenant - t_g) / 3600.0,
            "hdf_h": (maintenant - t_h) / 3600.0,
            "taille_hdf_mo": hdf.stat().st_size / (1024 * 1024)}


def verifier_intervalle_apports(fichier_unsteady, nom_zone_2d=None,
                                intervalle=INTERVALLE_APPORT,
                                noms_connus=None):
    """
    Relit le fichier et rapporte, par apport, son pas et son compte de valeurs.

    Se prononce sur ce qui est ECRIT, jamais sur ce qu'on croit avoir ecrit :
    une en-tete « Flow Hydrograph= N » qui ne s'accorde pas avec le tableau
    fait lire a HEC-RAS une serie tronquee, en silence. Le controle compare
    donc le N annonce au nombre de valeurs REELLEMENT relues.

    noms_connus : voir cartographier_hydrogrammes. IL DOIT ETRE LE MEME QUE
    CELUI DU RE-CADENCAGE. Filtrer les blocs orphelins a l'ECRITURE sans les
    filtrer a la RELECTURE fait echouer le controle sur des blocs qu'on a
    volontairement laisses tranquilles : le calage s'arretait alors sur
    « pas 0.5 h au lieu de 0.1 » pour deux conditions que HEC-RAS n'ouvre
    meme pas (releve le 31/08/2026, second poste — le filtre du 30/08 avait
    ete pose a deux endroits sur trois).

    Retourne {nom: {"intervalle_h", "nb", "conforme", "motif"}}.
    """
    attendu = _intervalle_en_heures(intervalle_hecras(intervalle))
    texte = _lire_lignes(fichier_unsteady)
    bilan = {}
    for nom, info in cartographier_hydrogrammes(fichier_unsteady, nom_zone_2d,
                                                noms_connus).items():
        valeurs = lire_hydrogramme_unsteady(fichier_unsteady,
                                               info["debut"], info["fin"])
        entete = next((texte[j] for j in range(info["debut"] - 1, -1, -1)
                       if texte[j].startswith(MOTIF_HYDROGRAMME)), "")
        try:
            annonce = int(entete.split("=", 1)[1].strip())
        except (IndexError, ValueError):
            annonce = None
        motifs = []
        if info["intervalle_h"] is None or abs(
                info["intervalle_h"] - attendu) > 1e-12:
            motifs.append(f"pas {info['intervalle_h']} h au lieu de {attendu}")
        if annonce != len(valeurs):
            motifs.append(f"en-tete annonce {annonce}, tableau en porte "
                          f"{len(valeurs)}")
        bilan[nom] = {"intervalle_h": info["intervalle_h"],
                      "nb": len(valeurs), "annonce": annonce,
                      "conforme": not motifs, "motif": " ; ".join(motifs)}
    return bilan


def noms_conditions_limites(fichier_unsteady, nom_zone_2d=None):
    """
    TOUS les noms de conditions limites du fichier, quel que soit leur type.

    A distinguer de cartographier_hydrogrammes(), qui ne retient que celles
    portant un hydrogramme de debit. Une condition de SORTIE n'en a pas — elle
    porte une pente imposee — et serait donc absente de la carte tout en
    existant bel et bien dans le fichier. Se fier a la carte pour savoir si un
    nom est libre conduit a vouloir creer un bloc deja present.

    Retourne {nom: zone}.
    """
    noms = {}
    for ligne in _lire_lignes(fichier_unsteady):
        if not ligne.startswith(MOTIF_LOCALISATION):
            continue
        champs = ligne.split("=", 1)[1].split(",")
        zone = champs[5].strip() if len(champs) > 5 else ""
        nom = champs[7].strip() if len(champs) > 7 else ""
        if nom and (nom_zone_2d is None or zone == nom_zone_2d):
            noms.setdefault(nom, zone)
    return noms


def cartographier_hydrogrammes(fichier_unsteady, nom_zone_2d=None,
                               noms_connus=None):
    """
    Associe chaque condition limite a SON tableau d'hydrogramme.

    On ne se fie pas a l'ordre : le fichier est parcouru, et pour chaque bloc
    « Boundary Location= » on retient le tableau de debit qui lui appartient.
    Un modele ou certaines conditions sont en cote et d'autres en debit
    decalerait tout raisonnement fonde sur un simple index.

    DEUX PIEGES, mesures sur un fichier unsteady reel :

      - LA RECHERCHE DU TABLEAU EST BORNEE AU BLOC COURANT. Une condition
        limite de SORTIE n'a pas d'hydrogramme (elle porte « Friction
        Slope= »). Chercher « le premier tableau qui suit » sans borne lui
        attribuait celui de la condition SUIVANTE : les conditions de sortie
        se retrouvaient dans la carte, avec le tableau d'un apport. Mettre a
        l'echelle un tel faux apport aurait ecrit dans le tableau d'un autre ;

      - UN MEME NOM PEUT APPARAITRE DANS PLUSIEURS ZONES 2D. Un fichier
        observe declare chaque condition limite deux fois : une fois pour la
        zone reelle de la geometrie, une fois pour une zone devenue
        orpheline. Retenir aveuglement la premiere
        occurrence revient a parier sur l'ordre du fichier : si l'orpheline
        venait en tete, le calage ecrirait dans un bloc ignore par HEC-RAS,
        le debit ne bougerait jamais, et la boucle tournerait des heures
        avant de conclure a une stagnation. D'ou nom_zone_2d, et a defaut le
        signalement des doublons dans « autres_zones ».

    TROISIEME PIEGE, ET C'EST LE PLUS COUTEUX (30/08/2026) : UN BLOC PEUT
    N'AVOIR AUCUNE BC LINE DANS LA GEOMETRIE. Un unsteady qui a de
    l'historique garde des blocs laisses par une version anterieure du modele
    — autre decoupage de zones, autre jeu d'apports. HEC-RAS les IGNORE : il
    n'ouvre que les conditions declarees dans la geometrie du plan.
    Releve sur un modele reel : 45 blocs dans l'unsteady pour 14 BC lines en
    geometrie, soit CINQ NOMS que l'utilisateur ne voyait nulle part dans son
    projet. Deux d'entre eux, restes courts, ont fait REFUSER trois lancements
    de calage sur des series que le solveur n'aurait jamais ouvertes. D'ou
    noms_connus.

    nom_zone_2d : ne retenir que les conditions limites de cette zone 2D.
        Fortement recommande des qu'un fichier a de l'historique.
    noms_connus : noms de BC lines lus dans la GEOMETRIE. Fournis, seuls ces
        noms sont retenus — comme fait HEC-RAS. None (defaut) = aucun filtre,
        et c'est VOULU : la geometrie n'est pas toujours lisible, et un
        controle qui ne peut pas se faire ne doit rien retirer. Le laisser a
        None rend exactement le comportement d'avant.

    Retourne {nom_bc: {"zone", "debut", "fin", "nb", "intervalle_h",
                       "autres_zones"}}.
    """
    from ras_commander import RasUnsteady

    lignes = _lire_lignes(fichier_unsteady)
    tables = RasUnsteady.identify_tables(lignes)

    debuts = [i for i, l in enumerate(lignes)
              if l.startswith(MOTIF_LOCALISATION)]
    fins = debuts[1:] + [len(lignes)]

    carte = {}
    for i, fin_bloc in zip(debuts, fins):
        champs = lignes[i].split("=", 1)[1].split(",")
        zone = champs[5].strip() if len(champs) > 5 else ""
        nom = champs[7].strip() if len(champs) > 7 else ""
        if not nom:
            continue
        if nom_zone_2d is not None and zone != nom_zone_2d:
            continue
        # ORPHELIN : aucun equivalent en geometrie, donc invisible pour
        # HEC-RAS. On l'ignore comme lui, sans quoi le calage se prononce sur
        # une serie que le solveur n'ouvrira jamais.
        if noms_connus is not None and nom not in noms_connus:
            continue

        suivant = next(((n, d, f) for n, d, f in tables
                        if n.startswith(MOTIF_HYDROGRAMME)
                        and i < d < fin_bloc), None)
        if suivant is None:
            continue                     # sortie a pente imposee, pas un apport
        _, debut, fin = suivant

        intervalle = None
        for j in range(i, min(debut, len(lignes))):
            if lignes[j].startswith("Interval="):
                intervalle = _intervalle_en_heures(lignes[j].split("=", 1)[1])
                break

        if nom in carte:
            carte[nom]["autres_zones"].append(zone)
            continue
        carte[nom] = {
            "zone": zone,
            "debut": debut,
            "fin": fin,
            "nb": fin - debut,
            "intervalle_h": intervalle,
            "autres_zones": [],
        }
    return carte


def lire_hydrogramme_unsteady(fichier_unsteady, debut, fin):
    """
    Valeurs d'un tableau d'hydrogramme, dans l'ordre du fichier.

    NE REND QUE LES VALEURS. Cette fonction rendait aussi le DataFrame de
    ras_commander, et les dix-huit appelants le jetaient tous — « valeurs, _ =
    » ou « [0] ». Le vrai grief n'etait pas les lignes gagnees : c'etait qu'un
    objet du solveur fuyait hors de ce module, seul endroit qui doive connaitre
    les types de ras_commander (voir le docstring du module).
    """
    from ras_commander import RasUnsteady

    lignes = _lire_lignes(fichier_unsteady)
    table = RasUnsteady.parse_fixed_width_table(lignes, debut, fin)
    return table["Value"].to_numpy(dtype=float)


# ---------------------------------------------------------------------------
# Pilote
# ---------------------------------------------------------------------------

CHEMIN_SERIES_HDF = ("Results/Unsteady/Output/Output Blocks/Base Output/"
                     "Unsteady Time Series")


def _series_absentes(hdf_resultats):
    """
    Decrit ce qui manque dans un fichier de resultats, ou "" s'il est complet.

    Un calcul avorte laisse un fichier qui EXISTE, qui est FRAIS, et qui ne
    contient rien d'exploitable. Verifier sa seule presence ne prouve donc
    rien : c'est la presence des SERIES TEMPORELLES qui atteste qu'une
    simulation a reellement tourne.
    """
    import h5py

    try:
        with h5py.File(hdf_resultats, "r") as h:
            if "Results" not in h:
                return "le fichier ne contient aucun groupe « Results »"
            if CHEMIN_SERIES_HDF not in h:
                return (f"aucune serie temporelle : la simulation n'a pas "
                        f"tourne (groupes presents : {list(h['Results'])})")
            if not list(h[CHEMIN_SERIES_HDF]):
                return "les series temporelles sont vides"
    except OSError as e:
        return f"fichier de resultats illisible ({e})"
    return ""


def _sans_tableau_des_temps(lignes):
    """
    Le compte rendu HEC-RAS sans le TABLEAU DES TEMPS qui le termine.

    LES DERNIERES LIGNES N'EXPLIQUENT RIEN, et c'est ce qui manquait. Un
    calcul avorte finit par ce tableau — « Computation Task | Completing
    Geometry, Flow and Plan | Unsteady Flow Computations | Complete Process |
    Computation Speed | ... 617968x » — plus de lignes que le filtre n'en
    garde : l'erreur, ecrite JUSTE AU-DESSUS, etait poussee dehors, et
    l'utilisateur lisait une vitesse de calcul en guise de diagnostic. Releve
    le 14/09/2026 sur un calage repris, arrete au calcul de reference.

    UN BLOC FIXE SE COUPE A SON EN-TETE ; on ne cherche pas des mots d'echec.
    Une liste de mots rate l'explication qui n'en porte aucun — « Computing
    2D Flow Area tables: Associated terrain has been updated », premiere
    ligne du cas du 31/08 — et l'en-tete, lui, ne change pas d'un calcul a
    l'autre. Sans en-tete, rien n'est coupe : la fin se lit comme avant.
    """
    for i, ligne in enumerate(lignes):
        if ligne.startswith("Computation Task"):
            return lignes[:i]
    return lignes


def _messages_hecras(hdf_resultats):
    """
    Derniers messages de HEC-RAS, pour que l'echec s'explique de lui-meme.

    Sans eux, l'utilisateur n'a qu'un constat d'echec et doit aller fouiller
    dans le dossier du projet.

    LE FICHIER DE RESULTATS EST INTERROGE EN PREMIER, et c'est le point qui
    compte. Meme un HDF « partiel » — celui d'un calcul qui n'a jamais demarre
    — porte « Results/Summary/Compute Messages (text) », ou HEC-RAS ecrit
    exactement ce qu'il a refuse de faire. Le _compute_pXX.log, lui, ne
    contient souvent que les lignes du serveur de communication, que ce
    filtre ecarte : la chaine concluait alors « aucun message exploitable »
    et renvoyait l'utilisateur ouvrir HEC-RAS a la main, alors que la reponse
    etait dans le fichier qu'elle venait de lire.
    Constate le 31/08/2026 : un calage arrete sur un calcul sans resultats,
    quand le HDF portait « Computing 2D Flow Area tables: Associated terrain
    has been updated / Geometry Writer Failed / Error Processing Geometry ».
    """
    try:
        import h5py
        with h5py.File(hdf_resultats, "r") as h:
            for cle in ("Results/Summary/Compute Messages (text)",
                        "Results/Summary/Compute Messages"):
                if cle not in h:
                    continue
                brut = h[cle][()]
                if isinstance(brut, bytes):
                    texte = brut.decode("utf-8", "replace")
                else:
                    texte = "\n".join(
                        x.decode("utf-8", "replace") if isinstance(x, bytes)
                        else str(x) for x in np.ravel(brut))
                lignes = [l.strip() for l in texte.splitlines() if l.strip()]
                # LES LIGNES QUI COMPTENT SONT LES DERNIERES AVANT LE TABLEAU
                # DES TEMPS — voir _sans_tableau_des_temps. Le debut ne fait
                # que decrire ce que HEC-RAS a commence a ecrire.
                retenues = [l for l in _sans_tableau_des_temps(lignes)
                            if not l.startswith(("Plan:",
                                                 "Simulation started"))]
                if retenues:
                    return ("Messages de HEC-RAS : "
                            + " | ".join(retenues[-4:]))
    except Exception:                                        # noqa: BLE001
        pass

    journal = Path(hdf_resultats).with_name(
        f"_compute_p{Path(hdf_resultats).suffixes[0].lstrip('.p')}.log")
    candidats = [journal] + sorted(
        Path(hdf_resultats).parent.glob("_compute_p*.log"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    for chemin in candidats:
        try:
            if not chemin.exists():
                continue
            lignes = [l.strip() for l in _lire_texte(chemin).splitlines()
                      if l.strip()]
            interessantes = [l for l in _sans_tableau_des_temps(lignes)
                             if not l.startswith(("Current executing",
                                                  "Server:", "Starting async",
                                                  "Client connected"))]
            if interessantes:
                return ("Messages de HEC-RAS : "
                        + " | ".join(interessantes[-3:]))
        except OSError:
            continue
    return ("Aucun message de HEC-RAS exploitable : ouvrir le plan dans "
            "HEC-RAS et lancer le calcul a la main pour voir ce qu'il refuse.")


def pids_hecras():
    """
    Processus HEC-RAS en cours : {pid: nom}. None si on ne sait pas dire.

    Sert a identifier PAR DIFFERENCE ceux qu'un calcul a laisses derriere
    lui : RasCmdr.compute_plan ne rend qu'un ComputeResult, sans le PID du
    processus qu'il a lance (verifie sur ras-commander 0.99.1). Comparer
    l'avant et l'apres est donc le seul moyen de distinguer un orphelin de
    NOTRE calcul d'une session que l'utilisateur a ouverte par ailleurs.
    """
    try:
        sortie = subprocess.run(
            ["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True,
            timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    processus = {}
    for ligne in (sortie.stdout or "").splitlines():
        champs = [c.strip().strip('"') for c in ligne.split('","')]
        if len(champs) < 2 or not champs[0].lower().startswith("ras"):
            continue
        try:
            processus[int(champs[1])] = champs[0]
        except ValueError:
            continue
    return processus


def orphelins_du_calcul(avant, apres):
    """
    Processus apparus PENDANT le calcul et encore vivants apres lui.

    Isole pour etre testable sans lancer HEC-RAS : c'est la regle de choix
    qui doit etre juste, pas l'appel systeme. Un processus deja present avant
    le calcul n'est JAMAIS retenu — ce serait une session de l'utilisateur.
    """
    if avant is None or apres is None:
        return {}
    return {pid: nom for pid, nom in apres.items() if pid not in avant}


def fermer_processus(pids):
    """Ferme des processus par PID. Retourne ceux qui ont bien ete fermes."""
    fermes = []
    for pid, nom in sorted(pids.items()):
        try:
            code = subprocess.call(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            continue
        if code == 0:
            fermes.append(f"{nom} (PID {pid})")
    return fermes


def hecras_ouvert():
    """
    HEC-RAS tourne-t-il ? Retourne True, False, ou None si on ne sait pas.

    RELEVE SUR UN CAS REEL : un plan cree et calcule correctement par la
    chaine — son fichier de resultats portait sa geometrie, son unsteady et
    un jeu complet de resultats — a vu son
    fichier de plan REECRIT une heure apres le calcul en un plan HEC-RAS
    vierge, sans « Geom File= » ni « Flow File= », avec un Short Identifier
    que seule l'interface produit. Le RASMapper du projet a ete enregistre deux
    minutes plus tard. La chaine, elle, ne compose jamais un fichier de plan :
    elle ne fait que modifier des lignes existantes.

    Autrement dit, l'interface HEC-RAS ouverte sur le projet ecrase depuis sa
    memoire ce que la chaine ecrit sur le disque — et defait le menage. D'ou
    cet avertissement au moment de preparer.
    """
    try:
        sortie = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Ras.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None          # pas Windows, ou tasklist indisponible
    return "Ras.exe" in (sortie.stdout or "")


def bilan_masse_depuis_comptes(comptes):
    """
    Extrait le pourcentage d'erreur de bilan de masse d'un DataFrame produit
    par HdfResultsPlan.get_volume_accounting(). Colonne reelle observee sur
    un calcul reel (ras-commander 0.99.1) : "Error Percent", SANS signe "%".
    Un premier filtre qui exigeait le caractere "%" litteral (ou le nom
    "vol_error_percent", jamais rencontre en pratique) ne correspondait a
    AUCUNE colonne reelle : le garde-fou de bilan de masse etait
    silencieusement mort, jamais signale comme erreur puisque l'appelant
    protege cette lecture par un try/except qui laisse la valeur a NaN.
    Retourne NaN si aucune colonne pertinente n'est trouvee.
    """
    if comptes is None or not len(comptes):
        return float("nan")
    colonne = next((c for c in comptes.columns
                    if "error" in c.lower()
                    and ("percent" in c.lower() or "%" in c)), None)
    if colonne is None:
        return float("nan")
    return float(pd.to_numeric(comptes[colonne], errors="coerce").abs().max())


def plan_par_titre(dossier_projet, nom_projet, titre):
    """
    Numero du plan portant ce titre, ou None.

    Sert a la REPRISE : demarrer le calage a l'apport A3 n'a de sens que si on
    repart du plan « Apport_A2 », qui porte les apports amont deja cales.
    Repartir du plan de reference les perdrait tous en silence.

    Si plusieurs plans portent le titre — projet remanie a la main — le plus
    RECEMMENT modifie est rendu : c'est le seul depart defendable, et le seul
    qui corresponde a ce que l'utilisateur vient de faire.
    """
    cherche = str(titre).strip()
    candidats = []
    for chemin in sorted(Path(dossier_projet).glob(f"{nom_projet}.p[0-9][0-9]")):
        trouve = re.search(r"^Plan Title=(.*)$", _lire_texte(chemin), re.M)
        if trouve and trouve.group(1).strip() == cherche:
            candidats.append(chemin)
    if not candidats:
        return None
    return max(candidats, key=lambda c: c.stat().st_mtime).suffix[2:]


class PiloteHecRas(Modele):
    """
    Implementation HEC-RAS de l'interface Modele.

    dossier_projet : dossier contenant le .prj.
    plan_reference : plan a cloner, par exemple « p01 ». Il n'est pas modifie.
    """

    def __init__(self, dossier_projet, nom_projet, plan_reference,
                 version="7.0.1", nom_zone_2d=None,
                 geometrie_override=None, unsteady_override=None,
                 nom_clone_geometrie=None, activer_courant=True,
                 fenetre_simulation=None, fermer_orphelins=True,
                 pas_travail_h=None, apports_a_caler=None,
                 plan_fenetre_pleine=None, coeurs=None):
        """
        geometrie_override / unsteady_override : numero ("01", "g01"... les
            deux formes sont acceptees) d'une geometrie ou d'un unsteady
            DIFFERENT de ceux du plan de reference. None = on garde ceux du
            plan tels quels.
        nom_clone_geometrie : titre attribue a la copie de travail de la
            geometrie. Une seule pour tout le calage — la geometrie ne change
            pas d'un apport a l'autre. Le plan et l'unsteady, eux, sont titres
            par ETAPE et n'ont donc pas de nom de clone : voir jalonner().
        fenetre_simulation : dict facultatif imposant au plan clone sa periode
            de simulation et ses intervalles (cf. valider_fenetre_simulation).
            Indispensable des lors qu'on substitue un unsteady flow dont la
            periode differe de celle du plan de reference.
        pas_travail_h : pas de temps (en heures) auquel toute la chaine
            travaille pour CE calage — normalement celui, natif, de la cible
            lue (voir criteres.pas_serie_h). None = pas d'ecrasement, on
            retombe sur le plancher historique INTERVALLE_APPORT (6 min).
            Determine l'intervalle cible utilise par _recadencer_apports().
        apports_a_caler : noms (BC line) des apports que CE calage pilote —
            typiquement la colonne Nom_Apport de la feuille Correspondance.
            Seuls ceux-la sont re-cadences PAR INTERPOLATION au pas de
            travail : une condition limite hors de cette liste (alimentation
            amont, autre apport non calé ici...) n'est jamais reecrite en
            silence, seulement verifiee — voir _recadencer_apports(). None =
            comportement historique, toutes les conditions a hydrogramme sont
            re-cadencees.
        plan_fenetre_pleine : numero du plan dont la fenetre de simulation
            fait office de BORNE HAUTE pour limiter_duree(). None = celle du
            plan de travail, ce qui est exact en calage ordinaire. EN REPRISE
            il faut le dire, car on part du plan de l'etape precedente, deja
            raccourci : voir preparer().
        coeurs : nombre de cœurs a demander a HEC-RAS pour chaque calcul.
            None ou 0 = le plan garde ce qu'il demande. Sinon, ras-commander
            l'ecrit dans le plan d'etape juste avant son calcul — voir
            calculer(). Le plan de reference n'est jamais touche.
        """
        self.pas_travail_h = float(pas_travail_h) if pas_travail_h else None
        self.apports_a_caler = (set(apports_a_caler)
                                if apports_a_caler is not None else None)
        self.dossier = Path(dossier_projet)
        self.nom_projet = nom_projet
        self.plan_reference = str(plan_reference).lstrip("pP").zfill(2)
        self.plan_fenetre_pleine = (
            str(plan_fenetre_pleine).lstrip("pP").zfill(2)
            if plan_fenetre_pleine else None)
        self.coeurs = int(coeurs) if coeurs else None
        self.version = version
        self.nom_zone_2d = nom_zone_2d
        self.geometrie_override = (str(geometrie_override).lstrip("gG").zfill(2)
                                   if geometrie_override else None)
        self.unsteady_override = (str(unsteady_override).lstrip("uU").zfill(2)
                                  if unsteady_override else None)
        self.nom_clone_geometrie = nom_clone_geometrie
        self.activer_courant = activer_courant
        # Fermer les HEC-RAS survivants apres chaque calcul. A ne mettre a
        # False que pour observer un calcul a la main pendant un calage.
        self.fermer_orphelins = fermer_orphelins
        # Valide DES LA CONSTRUCTION, pas au moment d'ecrire : une date fausse
        # doit etre signalee avant que le moindre fichier ait ete clone.
        self.fenetre_simulation = fenetre_simulation or None
        if self.fenetre_simulation:
            valider_fenetre_simulation(self.fenetre_simulation)

        self.plan_travail = None       # numero du plan clone
        self.fichier_unsteady = None
        # ETAPE COURANTE. None tant que jalonner() n'a pas tourne : c'est ce
        # qui distingue la premiere etape — le plan neuf de preparer(), qu'il
        # suffit de titrer — des suivantes, qui exigent un clone.
        self.etape = None
        self.etapes = []               # etapes traversees, dans l'ordre
        # PENTES A IMPOSER, par apport. Elles sont DEPOSEES ici avant le
        # calage et appliquees a la fin de preparer(), jamais avant : ecrire
        # une pente suppose de savoir dans quel bloc du fichier unsteady
        # ecrire, et cette carte n'existe qu'une fois le clone fait. Les
        # appliquer trop tot les perdait toutes en silence.
        self.pentes = {}
        self.carte = {}
        # Releve par preparer(), verifie a chaque jalonner(). None = pas
        # encore releve, ou geometrie illisible : le controle s'abstient.
        self.objets_geometrie = None
        self.originaux = {}            # hydrogrammes de reference, non quantifies
        self.hdf_resultats = None
        self.nb_calculs = 0

    # --- preparation -------------------------------------------------------

    def preparer(self):
        """
        Clone le plan, et si demande une geometrie et/ou un unsteady
        differents de ceux du plan de reference, puis active les sorties
        necessaires et retient les hydrogrammes d'origine.

        NE MODIFIE JAMAIS le plan/la geometrie/l'unsteady de reference : tout
        passe par clone_geom / clone_unsteady / clone_plan, qui creent des
        fichiers numerotes a part. clone_plan(geometry=, unsteady_flow=)
        rattache directement les clones au plan clone, en un seul appel — pas
        besoin de reecrire "Flow File=" a la main dans le fichier de plan.
        """
        from ras_commander import GeomParser, RasPlan, init_ras_project

        if hecras_ouvert():
            print("AVERTISSEMENT : HEC-RAS est OUVERT. L'interface reecrit les "
                  "fichiers du projet depuis sa memoire et peut effacer ce que "
                  "le calage y ecrit — un plan calcule s'est deja retrouve "
                  "vide de sa geometrie et de son debit. Fermer HEC-RAS avant "
                  "de laisser tourner le calage.\n"
                  "  Ce n'est pas une precaution theorique : le chien de garde "
                  "de ras-commander (dialog_watchdog, actif par defaut dans "
                  "compute_plan) repond « Oui » a toute boite modale, y "
                  "compris « Save Edits ». Le 08/08/2026, il a ainsi fait "
                  "ecrire a l'interface sa geometrie en memoire par-dessus "
                  "celle du projet, DEUX FOIS, pendant un calcul.\n"
                  "  L'empreinte de la geometrie est relevee et verifiee a "
                  "chaque etape : une section de controle qui disparaitrait "
                  "arrete le calage au lieu de le laisser produire un "
                  "resultat faux.", flush=True)

        init_ras_project(str(self.dossier), self.version)

        geometrie = None
        if self.geometrie_override:
            geometrie = RasPlan.clone_geom(self.geometrie_override)
            if self.nom_clone_geometrie:
                # clone_geom ne prend pas de titre : on le pose apres coup.
                GeomParser.set_geom_title(
                    self.dossier / f"{self.nom_projet}.g{geometrie}",
                    self.nom_clone_geometrie)

        # SANS TITRE ICI, volontairement : jalonner() titre le plan et
        # l'unsteady des l'ouverture de la premiere etape, quelques lignes plus
        # loin dans caler(). Leur donner un nom de clone ne servirait qu'a le
        # voir remplace aussitot.
        unsteady = None
        if self.unsteady_override:
            unsteady = RasPlan.clone_unsteady(self.unsteady_override)

        self.plan_travail = RasPlan.clone_plan(
            self.plan_reference, geometry=geometrie, unsteady_flow=unsteady)

        self.fichier_unsteady = self._unsteady_du_plan(self.plan_travail)
        # Le fichier unsteady effectivement utilise n'est clone ICI que s'il
        # n'a pas deja ete substitue ci-dessus (branche "unsteady is None") :
        # sans cela, le plan clone pointerait encore vers l'unsteady PARTAGE
        # du plan de reference, et appliquer_facteur() ecrirait dedans — donc
        # dans un fichier potentiellement utilise par d'autres plans du
        # projet. suffix vaut ".uXX" ; les deux premiers caracteres (".u")
        # sont retires par decoupage explicite, PAS par lstrip (qui retire un
        # ENSEMBLE de caracteres, pas un prefixe, et se serait trompe si le
        # numero avait commence par une lettre du prefixe).
        if unsteady is None:
            numero_actuel = self.fichier_unsteady.suffix[2:]
            unsteady = RasPlan.clone_unsteady(numero_actuel)
            self._reassigner_unsteady(self.plan_travail, unsteady)
            self.fichier_unsteady = self._unsteady_du_plan(self.plan_travail)

        # Apres le rattachement de l'unsteady : la fenetre imposee doit primer
        # sur celle heritee du plan de reference.
        self._ecrire_fenetre_simulation(self.plan_travail)

        # FENETRE DE REFERENCE, relevee UNE FOIS ET ICI. C'est la borne haute
        # de limiter_duree() : chaque etape clone le plan de la precedente,
        # donc une etape raccourcie transmet sa fenetre reduite a la suivante.
        # Sans cette memoire, un premier apport a l'evenement bref bornait
        # tout le calage — le deuxieme ne pouvait plus rallonger jusqu'a son
        # propre evenement, et se calait sur une serie tronquee.
        # LA BORNE HAUTE EST CELLE DU PLAN DE REFERENCE, PAS CELLE DU PLAN
        # DONT ON PART (correctif du 14/09/2026). En calage ordinaire les deux
        # sont le meme plan. EN REPRISE, on part du plan de l'etape
        # precedente, que le calage d'avant a pu RACCOURCIR : la memoire
        # censee empecher qu'une etape breve borne tout le calage etait alors
        # elle-meme bornee, et l'apport repris ne pouvait plus rallonger
        # jusqu'a son propre evenement. Mesure sur un cas reel : 36 h au plan
        # de reference, 32 h 06 au plan d'etape dont la reprise repart.
        #   PLUS LENT, JAMAIS FAUX : rendre la fenetre pleine ne fait que
        # retirer un plafond ; limiter_duree() la raccourcit ensuite au besoin
        # de l'apport.
        self.duree_reference_h = self._duree_borne_h()

        # CŒURS DEMANDES A HEC-RAS — voir calculer(). Dit ici, une fois, avec
        # ce que le plan de reference demandait : la reecriture par
        # ras-commander se fait ensuite plan d'etape par plan d'etape, sans
        # un mot dans le journal.
        if self.coeurs:
            print(f"   coeurs demandes a HEC-RAS : {self.coeurs} par calcul "
                  f"(le plan de reference p{self.plan_reference} demande "
                  f"« UNET D2 Cores = "
                  f"{self._coeurs_du_plan(self.plan_reference)} »)",
                  flush=True)

        if self.activer_courant:
            try:
                RasPlan.enable_hdf_output_variable(self.plan_travail,
                                                   "Cell Courant")
            except Exception:
                # Sans effet sur le calage : le bilan de masse suffit au
                # controle de qualite, le Courant n'est qu'un complement.
                pass

        # EMPREINTE DE LA GEOMETRIE, relevee une fois pour tout le calage.
        #
        # La geometrie de travail ne change plus jusqu'a la fin : une seule
        # copie sert a toutes les etapes. Tout ecart releve ensuite vient donc
        # de l'EXTERIEUR du calage — et cela s'est produit. Le 08/08/2026, en
        # pleine campagne, le chien de garde de ras-commander (dialog_watchdog,
        # actif par defaut dans compute_plan) a clique « Oui » sur une boite
        # « Save Edits » de l'interface HEC-RAS restee ouverte : l'interface a
        # ecrit sa geometrie EN MEMOIRE par-dessus le fichier du projet. Ce
        # jour-la, seules des positions d'etiquettes ont bouge. Si elle avait
        # tenu un etat anterieur a la creation des sections de controle, les
        # sept lignes de reference disparaissaient au milieu d'un calage de
        # 26 heures, et l'on ne l'aurait su qu'a la lecture suivante.
        self.objets_geometrie = self._objets_geometrie()

        # PRETRAITEMENT 2D PERIME — on previent, on ne bloque pas. Voir
        # pretraitement_perime() : c'est l'etat normal apres une composition,
        # mais c'est aussi ce qui fait echouer un calage sur un modele lourd,
        # avant le moindre calcul et sans que rien ne l'ait annonce.
        try:
            perime = pretraitement_perime(
                self._geometrie_du_plan(self.plan_travail))
        except Exception:                                    # noqa: BLE001
            perime = None
        if perime:
            print(f"   ATTENTION : le pretraitement 2D de la geometrie est "
                  f"PERIME — le .gXX a ete modifie il y a "
                  f"{perime['geometrie_h']:.1f} h, son .hdf date de "
                  f"{perime['hdf_h']:.1f} h ({perime['taille_hdf_mo']:.0f} Mo).\n"
                  f"              HEC-RAS va refaire ses tables 2D au premier "
                  f"calcul. Sur un modele lourd — gros terrain, projet sur un "
                  f"partage reseau — cela peut ECHOUER sur « Geometry Writer "
                  f"Failed », et le calage s'arretera sur un calcul sans "
                  f"resultats.\n"
                  f"              Si c'est le cas : ouvrir le modele dans "
                  f"HEC-RAS, lancer le plan une fois a la main pour faire le "
                  f"pretraitement, puis relancer le calage SANS recomposer.",
                  flush=True)

        self.carte = cartographier_hydrogrammes(self.fichier_unsteady,
                                                self.nom_zone_2d,
                                                self._bc_lines_connues())
        ambigus = {n: i["autres_zones"] for n, i in self.carte.items()
                   if i["autres_zones"]}
        if ambigus:
            detail = "; ".join(
                f"« {n} » dans {[self.carte[n]['zone']] + z}"
                for n, z in ambigus.items())
            raise ValueError(
                f"conditions limites de meme nom dans plusieurs zones 2D de "
                f"{self.fichier_unsteady.name} : {detail}. Renseigner le "
                f"parametre « Nom_zone_2D » du classeur pour lever "
                f"l'ambiguite : sans cela le calage ecrirait dans le premier "
                f"bloc rencontre, qui peut etre une zone devenue orpheline — "
                f"le debit ne bougerait alors jamais et la boucle tournerait "
                f"pour rien.")

        # AVANT de retenir les hydrogrammes d'origine : le re-cadencage
        # deplace les tableaux dans le fichier et change leurs valeurs.
        self._recadencer_apports()

        for nom, info in self.carte.items():
            valeurs = lire_hydrogramme_unsteady(
                self.fichier_unsteady, info["debut"], info["fin"])
            self.originaux[nom] = valeurs
        self.hdf_resultats = self.dossier / (
            f"{self.nom_projet}.p{self.plan_travail}.hdf")
        self._appliquer_pentes_deposees()
        return self.carte

    def _recadencer_apports(self):
        """
        Ramene au pas de travail TOUTES les conditions limites a hydrogramme,
        par interpolation et A DUREE CONSERVEE.

        SUR LE CLONE, JAMAIS SUR LA REFERENCE : preparer() a deja substitue un
        unsteady clone au plan de travail, et c'est lui seul qui est reecrit.
        Le fichier de l'utilisateur n'est pas touche.

        LE PAS CIBLE EST self.pas_travail_h — celui, natif, de la cible lue
        pour CE calage — et non plus un libelle fige. La chaine a longtemps
        force TOUT le fichier vers INTERVALLE_APPORT (« 6MIN ») : un modele
        dont la cible est deja plus fine (3 min, par exemple) se faisait alors
        degrader ses apports par le calage lui-meme, silencieusement.

        AUCUNE CONDITION N'EST TRAITEE A PART (07/08/2026, decision
        utilisateur). Les apports pilotes parce que leur contenu vient de la
        cible ; les AUTRES (alimentation amont, apport non cale ici...) parce
        que la DUREE qu'elles couvrent est une donnee physique du modele,
        qu'aucun changement de pas ne doit deplacer.

        UN RE-ETIQUETAGE SEUL A ETE ESSAYE, PUIS RETIRE. Il ne reecrivait que
        la ligne « Interval= », sur l'hypothese que le tableau portait deja
        les bonnes valeurs au bon pas et que seule l'etiquette etait perimee —
        vrai sur un modele reel (2026-08-05), le cas qui l'avait
        motive. Sur un AUTRE modele (2026-08-07) l'hypothese s'est revelee FAUSSE :
        la condition amont « in » etait legitimement a 15 min, comme tout le
        projet, et la ramener a 6 min A NOMBRE DE VALEURS CONSTANT a divise
        par 2,5 la duree couverte — 50,25 h → 20,10 h, pour une simulation de
        33 h. HEC-RAS a refuse de calculer (« Time series data ends before the
        end of the simulation ») et le calage s'est arrete sur un calcul de
        reference sans resultats. L'interpolation lineaire, elle, retrouve les
        valeurs d'origine A LEURS INSTANTS : elle ne contredit jamais la
        donnee, la ou changer l'etiquette la contredit toujours.

        La carte est RECONSTRUITE apres la passe — les positions dans le
        fichier bougent des qu'un tableau change de longueur — et le
        resultat est TOUJOURS relu (verifier_intervalle_apports), meme si
        rien n'a change : sans cela, une condition deja au MAUVAIS pas mais
        dont la correction a echoue passerait inapercue.

        Un echec de re-cadencage n'interrompt pas la boucle : la condition
        concernee reste a son pas d'origine et l'incident est rapporte plutot
        que tu. Ce sont les DEUX controles finaux qui arretent le calage avant
        tout calcul — verifier_intervalle_apports() pour le pas et l'accord
        en-tete/tableau, conditions_trop_courtes() pour la duree couverte.
        """
        intervalle_cible = (intervalle_hecras_depuis_heures(self.pas_travail_h)
                            if self.pas_travail_h else INTERVALLE_APPORT)

        # DUREE A COUVRIR, pour les seuls apports que CE calage pilote. Ce
        # sont les seuls dont la serie nous appartient : elle est mise a zero
        # au calcul de reference, puis entierement reecrite a chaque essai.
        # Les autres conditions limites sont la donnee du modele — on les
        # signale trop courtes, on ne les rallonge jamais.
        duree_simulation = None
        if self.apports_a_caler and self.plan_travail:
            try:
                f = fenetre_simulation_du_plan(
                    self.dossier / f"{self.nom_projet}.p{self.plan_travail}")
                if f.get("debut") and f.get("fin"):
                    duree_simulation = (
                        _en_minutes(instant_hecras(f["fin"]))
                        - _en_minutes(instant_hecras(f["debut"]))) / 60.0
            except Exception:                                # noqa: BLE001
                duree_simulation = None

        convertis = []
        for nom in sorted(self.carte):
            pilote = bool(self.apports_a_caler and nom in self.apports_a_caler)
            try:
                compte_rendu = imposer_intervalle_apport(
                    self.fichier_unsteady, nom, self.nom_zone_2d,
                    intervalle=intervalle_cible,
                    duree_min_h=duree_simulation if pilote else None)
            except Exception as e:                          # noqa: BLE001
                print(f"   AVERTISSEMENT : « {nom} » non recadence : {e}",
                      flush=True)
                continue
            if compte_rendu is None:
                continue
            convertis.append(compte_rendu)
            print(f"   « {nom} » : pas de temps "
                  f"{60 * compte_rendu['intervalle_avant_h']:g} min → converti "
                  f"en {compte_rendu['intervalle_apres']} "
                  f"({compte_rendu['nb_avant']} → {compte_rendu['nb_apres']} "
                  f"valeurs, {compte_rendu['duree_h']:.1f} h conservees)",
                  flush=True)

        if convertis:
            self.carte = cartographier_hydrogrammes(self.fichier_unsteady,
                                                    self.nom_zone_2d,
                                                    self._bc_lines_connues())

        # LE MEME FILTRE QU'A L'ECRITURE, sans quoi ce controle se prononce
        # sur des blocs que _recadencer_apports() a volontairement laisses
        # tranquilles — et arrete le calage sur des orphelins.
        discordants = {n: b["motif"] for n, b in verifier_intervalle_apports(
            self.fichier_unsteady, self.nom_zone_2d,
            intervalle=intervalle_cible,
            noms_connus=self._bc_lines_connues()).items()
            if not b["conforme"]}
        if discordants:
            raise ValueError(
                f"intervalle incoherent avec le pas de travail "
                f"({intervalle_cible}) dans {self.fichier_unsteady.name} : "
                f"{discordants}. Le calage est interrompu AVANT tout calcul : "
                f"HEC-RAS lirait une serie tronquee ou etiree dans le temps "
                f"sans s'en plaindre, et le calage compenserait un debit "
                f"faux sans jamais pouvoir y remedier. Le re-cadencage "
                f"automatique a echoue sur cette condition — voir "
                f"l'avertissement ci-dessus ; corriger son bloc a la main "
                f"dans le modele source avant de relancer.")

        courtes = conditions_trop_courtes(
            self.fichier_unsteady,
            (self.dossier / f"{self.nom_projet}.p{self.plan_travail}"
             if self.plan_travail else None),
            self.nom_zone_2d, self._bc_lines_connues(), self.apports_a_caler)
        if courtes:
            # DEUX GROUPES, PARCE QU'ILS NE SE CORRIGENT PAS AU MEME ENDROIT.
            # Le message ne les distinguait pas : sur un modele reel, il a
            # nomme deux conditions d'alimentation amont a un utilisateur qui
            # venait de rallonger ses douze apports et concluait, a juste
            # titre de son point de vue, que le controle se trompait.
            def _lister(noms):
                return "; ".join(
                    f"« {n} » couvre {courtes[n]['duree_h']:.2f} h pour une "
                    f"simulation de {courtes[n]['simulation_h']:.2f} h"
                    for n in sorted(noms))

            apports = [n for n, d in courtes.items() if d["a_caler"]]
            autres = [n for n, d in courtes.items() if not d["a_caler"]]
            detail = ""
            if apports:
                # CE CAS NE DEVRAIT PLUS SE PRODUIRE : _recadencer_apports()
                # prolonge par des zeros les apports que le calage pilote. S'il
                # subsiste, c'est que le prolongement a echoue — pas que
                # l'utilisateur a mal rempli son classeur. L'ancien message
                # l'envoyait rallonger la feuille Cibles, ce qui n'a aucun
                # effet sur la serie du MODELE : conseil faux, releve le
                # 31/08/2026 sur un modele dont six apports etaient trop
                # courts.
                detail += (f" APPORT(S) PILOTE(S) PAR LE CALAGE, dont le "
                           f"prolongement automatique a echoue — voir les "
                           f"avertissements ci-dessus : {_lister(apports)}.")
            if autres:
                detail += (f" AUTRES CONDITIONS LIMITES (alimentation amont, "
                           f"apports non cales ici) — a corriger dans le "
                           f"modele source : {_lister(autres)}.")
            raise ValueError(
                f"condition(s) limite(s) plus courte(s) que la fenetre de "
                f"simulation dans {self.fichier_unsteady.name}.{detail} "
                f"HEC-RAS refuse de calculer dans ce cas (« Time series data "
                f"ends before the end of the simulation ») et le calage "
                f"s'arreterait sur un calcul de reference sans resultats. "
                f"Prolonger la serie, ou raccourcir la fenetre de simulation "
                f"du plan.")
        return convertis

    # --- etapes conservees ---------------------------------------------------

    def jalonner(self, etape):
        """
        Ouvre une etape de calage : un plan ET un unsteady flow a ce nom.

        POURQUOI UN JEU DE FICHIERS PAR ETAPE. La chaine calait tout dans un
        plan unique, reecrit a chaque essai, et le menage final n'en gardait
        qu'un. Il ne restait donc aucune trace de l'etat « sans_apport », ni de
        ce qu'avait donne chaque apport une fois cale : un calage interrompu
        sur le troisieme apport obligeait a tout reprendre depuis le premier.
        Avec une etape par apport, le projet garde « sans_apport », puis
        « Apport_A1 », « Apport_A2 »... et l'on peut repartir de n'importe
        lequel — c'est ce que fait le parametre « Premier_apport ».

        La premiere etape ne clone rien : preparer() vient de creer un plan et
        un unsteady neufs, il suffit de les titrer. Les suivantes clonent le
        jeu courant, de sorte que l'etape precedente reste figee AVEC SES
        RESULTATS.

        UN PLAN DE MEME NOM ISSU D'UN CALAGE PRECEDENT EST REMPLACE. En garder
        deux laisserait dans le gestionnaire de plans HEC-RAS deux entrees
        homonymes dont rien ne dirait laquelle fait foi.

        L'etat de l'objet n'est modifie qu'une fois TOUT verifie : un echec en
        cours de route laisse le calage utilisable sur l'etape precedente,
        jamais a cheval entre un plan et l'unsteady d'un autre.
        """
        from ras_commander import RasPlan, init_ras_project

        if self.plan_travail is None:
            raise RuntimeError(
                "jalonner() appelee avant preparer() : il n'existe pas encore "
                "de plan de travail a decliner.")
        titre = str(etape).strip()
        if not titre:
            raise ValueError("nom d'etape vide : un plan sans titre serait "
                             "introuvable dans le projet.")

        init_ras_project(str(self.dossier), self.version)
        if self.etape is None:
            plan = self.plan_travail
            flot = self.fichier_unsteady.suffix[2:]
        else:
            flot = RasPlan.clone_unsteady(self.fichier_unsteady.suffix[2:],
                                          new_title=titre)
            plan = RasPlan.clone_plan(self.plan_travail, new_title=titre,
                                      unsteady_flow=flot)
        # Titres poses explicitement dans les deux cas : clone_plan ne renseigne
        # pas « Short Identifier », qui est ce que RASMapper affiche.
        self._renommer_plan(str(plan).zfill(2), titre)
        self._renommer_unsteady(str(flot).zfill(2), titre)

        fichier = self._unsteady_du_plan(plan)
        # MEME FILTRE QUE self.carte, sans quoi la comparaison ci-dessous
        # opposerait une carte filtree a une carte qui ne l'est pas : tout
        # bloc orphelin y passerait pour « present d'un cote, absent de
        # l'autre » selon le sens de la difference.
        carte = cartographier_hydrogrammes(fichier, self.nom_zone_2d,
                                           self._bc_lines_connues())
        absents = sorted(set(self.carte) - set(carte))
        if absents:
            raise RuntimeError(
                f"l'unsteady de l'etape « {titre} » ({fichier.name}) ne "
                f"contient plus les conditions limites {absents}. L'etape "
                f"n'est pas ouverte : le calage continue sur la precedente.")

        # MEME CONTROLE, COTE GEOMETRIE. Il manquait, et c'est la que vivent
        # les sections de controle : sans lui, une geometrie amputee de
        # l'exterieur ne se serait signalee qu'a la lecture des resultats,
        # plusieurs heures de calcul plus tard, sous la forme d'une section
        # « absente » qu'on aurait cherchee du cote du calage.
        if self.objets_geometrie is not None:
            actuels = self._objets_geometrie()
            if actuels is not None:
                perdus = sorted((self.objets_geometrie[0] - actuels[0])
                                | (self.objets_geometrie[1] - actuels[1]))
                if perdus:
                    raise RuntimeError(
                        f"la geometrie du projet ne contient plus {perdus}. "
                        f"Ces objets y etaient au debut du calage : quelque "
                        f"chose les a retires DEPUIS, hors de la chaine — le "
                        f"cas connu est l'interface HEC-RAS laissee ouverte, "
                        f"dont une boite « Save Edits » ecrit la geometrie en "
                        f"memoire par-dessus celle du projet. L'etape "
                        f"« {titre} » n'est pas ouverte : le calage continue "
                        f"sur la precedente.")

        self.plan_travail = plan
        self.fichier_unsteady = fichier
        self.carte = carte
        self.hdf_resultats = self.dossier / f"{self.nom_projet}.p{plan}.hdf"
        self.etape = titre
        self.etapes.append(titre)

        remplaces = self._remplacer_homonymes(titre)
        return (f"plan p{plan} / unsteady u{str(flot).zfill(2)}"
                + (f" — {', '.join(remplaces)} de même nom remplacé(s)"
                   if remplaces else ""))

    def conclure(self, titre):
        """
        Donne son titre d'etat final au plan COURANT — celui qui porte tous
        les apports cales, et leurs resultats.

        AUCUN CLONE, AUCUN CALCUL. Le plan de la derniere etape EST l'etat
        final : la verification globale vient de le relire section par
        section sans lancer un seul calcul (voir calage.caler). Un clone
        n'emporterait pas le .pXX.hdf — RasPlan.clone_plan copie le .pXX
        seul — et le plan « avec_apports » serait muet dans RAS Mapper a cote
        d'un « Apport_<dernier> » qui, lui, a les resultats. Recopier le .hdf
        doublerait des centaines de Mo pour deux plans decrivant LE MEME
        calcul ; recalculer couterait des heures pour refaire a l'identique
        ce qu'on vient de lire.

        L'ETAPE « Apport_<dernier> » DISPARAIT du gestionnaire de plans :
        c'est le meme jeu de fichiers, sous le nom qui le decrit. Aucune
        reprise ne le cherche — « Premier_apport = X » repart du plan de
        l'apport PRECEDENT X, et le dernier apport n'est le precedent de
        personne.

        Un etat final homonyme laisse par un calage precedent du meme
        scenario est remplace, exactement comme une etape : deux
        « Q100_avec_apports » ne diraient plus lequel fait foi.
        """
        if self.plan_travail is None or self.fichier_unsteady is None:
            raise RuntimeError(
                "conclure() appelee avant preparer() : il n'y a pas encore "
                "de plan a titrer.")
        numero = str(self.plan_travail).zfill(2)
        flot = self.fichier_unsteady.suffix[2:]
        self._renommer_plan(numero, titre)
        self._renommer_unsteady(flot, titre)
        self.etape = titre
        if self.etapes:
            # Le plan est le meme : l'etape change de nom, elle ne s'ajoute
            # pas. Ni plan_travail, ni fichier_unsteady, ni carte, ni
            # hdf_resultats ne bougent — les livrables restent intacts.
            self.etapes[-1] = titre
        remplaces = self._remplacer_homonymes(titre)
        dit_hdf = self._retitrer_resultats_hdf(numero, titre)
        dit_rasmap = self._declarer_resultats_rasmap(numero, titre)
        return (f"plan p{numero} / unsteady u{flot} retitré"
                + (f" — {', '.join(remplaces)} de même nom remplacé(s)"
                   if remplaces else "")
                + (f" ; {dit_hdf}" if dit_hdf else "")
                + (f" ; {dit_rasmap}" if dit_rasmap else ""))

    def _retitrer_resultats_hdf(self, numero, titre):
        """
        Reporte le titre final dans les attributs du .pNN.hdf.

        RAS MAPPER NOMME LA COUCHE D'APRES LE HDF, ni d'apres le .pNN ni
        d'apres le .rasmap (constate le 28/09/2026 sur un modele reel, HEC-RAS
        7.0.1). Le .rasmap ecrit par conclure() declarait
        « <prefixe>_avec_apports » ; RAS Mapper l'a reecrit a l'ouverture
        en « <prefixe>_Apport_<dernier> », le nom que HEC-RAS avait grave dans
        « Plan Data/Plan Information » au calcul de la derniere etape. Le
        plan final n'apparaissait plus sous son nom.

        NE LEVE JAMAIS, comme _declarer_resultats_rasmap : les resultats
        sont bons, seul leur nom affiche est en jeu.
        """
        chemin = self.dossier / f"{self.nom_projet}.p{numero}.hdf"
        if not chemin.is_file():
            return None
        try:
            import h5py
            import numpy as np
            with h5py.File(chemin, "r+") as h:
                info = h["Plan Data/Plan Information"].attrs
                for cle in ("Plan Name", "Plan ShortID", "Plan Title",
                            "Flow Title"):
                    if cle in info:
                        info[cle] = np.bytes_(titre.encode("utf-8"))
            return "resultats retitres dans le .hdf"
        except Exception as e:                              # noqa: BLE001
            return (f"{chemin.name} non retitre ({type(e).__name__}: {e}) "
                    f"— RAS Mapper nommera la couche d'apres l'ancienne "
                    f"etape")

    # Le bloc qu'ecrit HEC-RAS pour un plan calcule, reduit a ce qui compte :
    # la couche de resultats, sa geometrie, son plan et les trois cartes
    # usuelles. La symbologie, les couches virtuelles et les rasterizers que
    # l'interface ajoute sont REGENERES par RAS Mapper a l'ouverture — les
    # recopier ici ferait deviner cent lignes de valeurs par defaut.
    _GABARIT_RASRESULTS = """    <Layer Name="{titre}" Type="RASResults" Filename="{fichier}">
      <Layer Name="Event Conditions" Type="RASEventConditions" Filename="{fichier}" />
      <Layer Type="RASGeometry" Checked="True" Filename="{fichier}" />
      <Layer Name="Plan" Type="RASPlan" Filename="{fichier}" GeometryHDF="{fichier}" />
      <Layer Name="Depth" Type="RASResultsMap" Checked="True">
        <MapParameters MapType="depth" ProfileIndex="2147483647" ProfileName="Max" />
      </Layer>
      <Layer Name="WSE" Type="RASResultsMap">
        <MapParameters MapType="elevation" ProfileIndex="2147483647" ProfileName="Max" />
      </Layer>
      <Layer Name="Velocity" Type="RASResultsMap">
        <MapParameters MapType="velocity" ProfileIndex="2147483647" ProfileName="Max" />
      </Layer>
    </Layer>
"""

    def _declarer_resultats_rasmap(self, numero, titre):
        """
        Inscrit le plan final dans le .rasmap, pour que RAS MAPPER LE VOIE.

        LE DEFAUT QUE CECI CORRIGE (constate le 21 septembre 2026 sur deux
        modeles reels). Un calage abouti laissait un plan « <prefixe>_avec_
        apports » avec un .pNN.hdf complet — plusieurs centaines de Mo de
        resultats — et RAS Mapper ne montrait RIEN. Son arbre « Results » ne
        se construit pas en parcourant le dossier : il liste ce que le
        .rasmap declare. Sur le premier modele, treize plans ecrits par la
        chaine portaient leurs resultats et le .rasmap n'en declarait AUCUN ;
        sur le second, seuls les plans calcules depuis l'interface HEC-RAS y
        figuraient. C'est le trou connu de ras-commander — il ne met JAMAIS
        le .rasmap a jour (voir 0-HECRAS,
        references/11_bibliotheques_tierces.md, et le constat date du
        21/09/2026 dans 08_constats_mesures.md).

        IDEMPOTENT : relancer un calage sur le meme scenario retrouve la
        couche par son FICHIER, et n'en met pas une seconde. C'est le
        fichier qui identifie, non le nom : le nom, lui, vient de changer.

        NE LEVE JAMAIS. Le calage est fini et ses resultats sont bons ; un
        .rasmap absent, verrouille ou d'une forme inattendue ne doit pas
        transformer un succes en echec. On rend une phrase, l'appelant la
        journalise.
        """
        chemin = self.dossier / f"{self.nom_projet}.rasmap"
        if not chemin.is_file():
            return (f"aucun {chemin.name} : le plan n'a pas pu etre declare "
                    f"a RAS Mapper")
        fichier = f".\\{self.nom_projet}.p{numero}.hdf"
        try:
            texte = _lire_texte(chemin)
            if "</Results>" not in texte:
                return (f"{chemin.name} ne porte pas de bloc <Results> : le "
                        f"plan n'y a pas ete declare")
            # LA COUCHE EXISTANTE SE RETROUVE PAR SON FICHIER. On ne
            # reecrit alors que son attribut Name, sans toucher a la
            # symbologie que l'utilisateur a pu regler.
            motif = re.compile(
                r'(<Layer\s+Name=")([^"]*)("[^>]*?Type="RASResults"[^>]*?'
                + re.escape(f'Filename="{fichier}"') + r')')
            neuf, remplacements = motif.subn(
                lambda m: m.group(1) + _echapper_xml(titre) + m.group(3),
                texte)
            if remplacements:
                action = "couche de resultats renommee"
            else:
                bloc = self._GABARIT_RASRESULTS.format(
                    titre=_echapper_xml(titre), fichier=_echapper_xml(fichier))
                i = texte.rindex("</Results>")
                # On se raccroche a l'indentation de la balise fermante :
                # le .rasmap est relu par des humains autant que par RAS.
                debut = texte.rfind("\n", 0, i) + 1
                neuf = texte[:debut] + bloc + texte[debut:]
                action = "plan declare a RAS Mapper"
            _ecrire_texte(chemin, neuf)
            # RELU, PAS SUPPOSE (regle de la maison). Un .rasmap casse
            # empeche RAS Mapper d'ouvrir le projet : on verifie que le
            # fichier se reparse et que la couche y est.
            from xml.etree import ElementTree
            relu = _lire_texte(chemin)
            ElementTree.fromstring(relu)
            if f'Filename="{fichier}"' not in relu:
                return f"{chemin.name} reecrit mais la couche n'y est pas"
            return action
        except Exception as e:                              # noqa: BLE001
            return (f"{chemin.name} non mis a jour ({type(e).__name__}: {e}) "
                    f"— les resultats sont bons, RAS Mapper ne les listera "
                    f"pas tant que le plan n'y est pas declare")

    def _remplacer_homonymes(self, titre):
        """
        Efface les plans d'un calage PRECEDENT portant le titre de l'etape.

        Le plan de reference et le plan de travail sont intouchables. Un
        unsteady ou une geometrie que plus aucun plan survivant ne designe part
        avec eux : sans cela, chaque relance laisserait derriere elle un jeu
        complet de fichiers que personne ne saurait plus rattacher a rien.
        """
        efface = []
        for chemin in sorted(self.dossier.glob(f"{self.nom_projet}.p[0-9][0-9]")):
            numero = chemin.suffix[2:]
            if numero in (str(self.plan_travail).zfill(2), self.plan_reference):
                continue
            if self._titre(chemin, "Plan Title") != titre:
                continue
            self._effacer_objet(f"p{numero}")
            efface.append(f"p{numero}")
        if not efface:
            return []
        for prefixe, cle in (("u", "Flow File"), ("g", "Geom File")):
            for chemin in sorted(
                    self.dossier.glob(f"{self.nom_projet}.{prefixe}[0-9][0-9]")):
                numero = chemin.suffix[2:]
                if not self._utilise_par_un_plan(cle, prefixe, numero):
                    self._effacer_objet(f"{prefixe}{numero}")
                    efface.append(f"{prefixe}{numero}")
        self._nettoyer_prj()
        return efface

    def _utilise_par_un_plan(self, cle, prefixe, numero):
        """Un plan encore present designe-t-il ce fichier ?"""
        for chemin in self.dossier.glob(f"{self.nom_projet}.p[0-9][0-9]"):
            trouve = re.search(rf"^{cle}={prefixe}(\w+)", _lire_texte(chemin),
                               re.M)
            if trouve and trouve.group(1) == numero:
                return True
        return False

    def _renommer_unsteady(self, numero, titre):
        """Donne son titre a un fichier unsteady."""
        chemin = self.dossier / f"{self.nom_projet}.u{numero}"
        if not chemin.is_file():
            return
        lignes = _lire_lignes(chemin)
        for i, ligne in enumerate(lignes):
            if ligne.startswith("Flow Title="):
                fin = "\n" if ligne.endswith("\n") else ""
                lignes[i] = f"Flow Title={titre}{fin}"
        chemin.write_text("".join(lignes), encoding="utf-8")

    def _appliquer_pentes_deposees(self):
        """
        Ecrit les pentes de ligne d'energie deposees dans self.pentes.

        ICI ET NULLE PART AILLEURS : c'est le premier instant ou l'on connait
        a la fois le fichier unsteady CLONE et la carte de ses blocs. Appelee
        avant, definir_pente() ne trouvait aucune condition limite et
        rapportait « Presentes : [] » pour chaque apport — les pentes saisies
        au classeur etaient perdues sans que rien n'echoue.

        Un echec sur une pente n'interrompt pas le calage : la valeur en place
        dans le fichier reste, et l'incident est rapporte.
        """
        for nom, pente in (self.pentes or {}).items():
            try:
                self.definir_pente(nom, pente)
                print(f"   pente de « {nom} » : {pente:.5g} m/m", flush=True)
            except Exception as e:                          # noqa: BLE001
                print(f"   AVERTISSEMENT : pente de « {nom} » non appliquee : "
                      f"{e}", flush=True)

    def _ecrire_fenetre_simulation(self, numero_plan):
        """
        Impose au plan clone la fenetre de simulation et les intervalles fournis.

        Utile quand on ne repart PAS du plan de reference tel quel : substituer
        un autre unsteady flow n'ajuste pas la fenetre du plan, qui reste celle
        du plan d'origine. Le calcul tournerait alors sur une periode sans
        rapport avec les hydrogrammes du nouveau fichier — HEC-RAS ne s'en
        plaint pas, il calcule une fenetre vide.

        Seules les cles fournies sont ecrites : ce qui n'est pas precise reste
        celui du plan de reference, avec toutes ses tolerances numeriques.
        """
        if not self.fenetre_simulation:
            return
        champs = valider_fenetre_simulation(self.fenetre_simulation)
        fichier_plan = self.dossier / f"{self.nom_projet}.p{numero_plan}"
        lignes = _lire_lignes(fichier_plan)
        restants = dict(champs)
        for i, ligne in enumerate(lignes):
            for cle, valeur in champs.items():
                if ligne.startswith(cle + "="):
                    fin = "\n" if ligne.endswith("\n") else ""
                    lignes[i] = f"{cle}={valeur}{fin}"
                    restants.pop(cle, None)
        if restants:
            # Un plan qui n'a pas la ligne attendue est un plan qu'on ne
            # comprend pas : l'ajouter a l'aveugle au mauvais endroit ferait un
            # fichier que HEC-RAS lit de travers, sans le dire.
            raise ValueError(
                f"lignes absentes de {fichier_plan.name} : "
                f"{', '.join(sorted(restants))}. Le plan de reference n'a pas "
                f"la structure attendue ; la fenetre de simulation ne peut pas "
                f"y etre imposee sans risque.")
        fichier_plan.write_text("".join(lignes), encoding="utf-8")

    def _coeurs_du_plan(self, numero):
        """Valeurs « UNET D2 Cores= » d'un plan, « tous » pour 0 ; « ? » si illisible."""
        try:
            lignes = _lire_lignes(self.dossier / f"{self.nom_projet}.p{numero}")
        except OSError:
            return "?"
        vus = []
        for ligne in lignes:
            if ligne.startswith("UNET D2 Cores="):
                valeur = ligne.split("=", 1)[1].strip()
                texte = "tous" if valeur == "0" else valeur
                if texte not in vus:
                    vus.append(texte)
        return ", ".join(vus) or "?"

    def _duree_borne_h(self):
        """
        Duree, en heures, de la fenetre qui borne limiter_duree() — None si le
        plan ne la dit pas ou ne se lit pas : la borne est un gain de temps,
        pas une etape du calage, et sans elle la fenetre entiere s'applique.

        LUE SUR LE PLAN DE TRAVAIL, qui vient d'etre clone et porte deja la
        fenetre imposee s'il y en a une. EN REPRISE, sur le plan designe par
        plan_fenetre_pleine : le plan de travail est alors le clone d'un plan
        d'etape que le calage d'avant a pu raccourcir — voir preparer().
        """
        plan = self.plan_fenetre_pleine or self.plan_travail
        try:
            f = fenetre_simulation_du_plan(
                self.dossier / f"{self.nom_projet}.p{plan}")
            if f.get("debut") and f.get("fin"):
                return (_en_minutes(instant_hecras(f["fin"]))
                        - _en_minutes(instant_hecras(f["debut"]))) / 60.0
        except Exception:                                    # noqa: BLE001
            pass
        return None

    def limiter_duree(self, heures):
        """
        Ramene la fin de simulation du plan de travail a « heures » depuis son
        debut. Retourne la duree effectivement ecrite, ou None si rien n'a ete
        change.

        ON NE DEPASSE JAMAIS LA FENETRE DE REFERENCE, relevee par preparer().
        Au-dela, on calculerait apres la fin des hydrogrammes que le modele
        porte — c'est le piege deja documente : HEC-RAS ne s'en plaint pas, il
        calcule dans le vide.

        MAIS ON PEUT RALLONGER EN DECA DE CETTE BORNE, et il le faut. Chaque
        etape CLONE le plan de la precedente : une etape raccourcie transmet sa
        fenetre reduite a la suivante. Refuser d'allonger bornait alors tout le
        calage a l'evenement du PREMIER apport — le deuxieme se calait sur une
        serie tronquee, avec un volume incalculable. Attrape par l'auto-test le
        31/08/2026, avant toute mise en production.

        LA FIN EST ARRONDIE A LA MINUTE SUPERIEURE, jamais tronquee : un
        arrondi vers le bas retirerait jusqu'a une minute a la fenetre de
        jugement, et le raccourcissement se paierait en couverture.

        AUCUN EFFET SANS PLAN DE TRAVAIL, et aucune exception : cette methode
        est un gain de temps, pas une etape du calage. Si elle echoue, le
        calcul tourne sur la fenetre entiere — plus lent, jamais faux.
        """
        if not self.plan_travail or heures is None or heures <= 0:
            return None
        fichier_plan = self.dossier / f"{self.nom_projet}.p{self.plan_travail}"
        fenetre = fenetre_simulation_du_plan(fichier_plan)
        if not (fenetre.get("debut") and fenetre.get("fin")):
            return None
        debut, fin = instant_hecras(fenetre["debut"]), instant_hecras(fenetre["fin"])
        actuelle_min = _en_minutes(fin) - _en_minutes(debut)
        voulue_min = int(math.ceil(float(heures) * 60.0))
        plafond = getattr(self, "duree_reference_h", None)
        if plafond is not None:
            voulue_min = min(voulue_min, int(round(plafond * 60.0)))
        if voulue_min == actuelle_min or voulue_min <= 0:
            return None

        nouvelle_fin = _en_texte_hecras(
            _en_datetime(debut) + timedelta(minutes=voulue_min))
        lignes = _lire_lignes(fichier_plan)
        for i, ligne in enumerate(lignes):
            if ligne.startswith("Simulation Date="):
                saut = "\n" if ligne.endswith("\n") else ""
                lignes[i] = f"Simulation Date={debut},{nouvelle_fin}{saut}"
                fichier_plan.write_text("".join(lignes), encoding="utf-8")
                return voulue_min / 60.0
        return None

    def _unsteady_du_plan(self, numero_plan):
        """Fichier unsteady associe a un plan, lu dans le fichier de plan."""
        fichier_plan = self.dossier / f"{self.nom_projet}.p{numero_plan}"
        for ligne in _lire_lignes(fichier_plan):
            if ligne.startswith("Flow File="):
                return self.dossier / (f"{self.nom_projet}."
                                       + ligne.split("=", 1)[1].strip())
        raise ValueError(f"aucun « Flow File= » dans {fichier_plan.name}")

    def _geometrie_du_plan(self, numero_plan):
        """Fichier geometrie associe a un plan. Symetrique du precedent."""
        fichier_plan = self.dossier / f"{self.nom_projet}.p{numero_plan}"
        for ligne in _lire_lignes(fichier_plan):
            if ligne.startswith("Geom File="):
                return self.dossier / (f"{self.nom_projet}."
                                       + ligne.split("=", 1)[1].strip())
        raise ValueError(f"aucun « Geom File= » dans {fichier_plan.name}")

    def _bc_lines_connues(self):
        """
        Noms des BC lines declarees dans la geometrie de travail, ou None si
        elle n'est pas lisible.

        None VEUT DIRE « JE NE SAIS PAS », PAS « AUCUNE ». C'est ce qui
        distingue une geometrie illisible d'une geometrie vide : dans le
        premier cas le filtre est desactive et l'on retombe sur le
        comportement d'avant, dans le second il ne resterait aucune condition
        et le calage s'arreterait — verdict que seule une vraie lecture peut
        justifier.
        """
        objets = self.objets_geometrie
        return None if objets is None else objets[1]

    def _objets_geometrie(self):
        """
        Noms des sections de controle et des apports presents dans la
        geometrie de travail, ou None si elle n'est pas lisible.

        Lecture du .gXX TEXTE, jamais du .hdf : c'est le texte qui fait foi,
        le pretraitement peut dater d'avant.
        """
        try:
            from geometrie import noms_objets_geometrie
            fichier = self._geometrie_du_plan(self.plan_travail)
            objets = noms_objets_geometrie(fichier)
            return (frozenset(objets.get("sections", ())),
                    frozenset(objets.get("apports", ())))
        except Exception:                                    # noqa: BLE001
            # Ne JAMAIS interrompre un calage parce que ce controle n'a pas pu
            # se faire : il ajoute une securite, il n'en retire aucune.
            return None

    def definir_pente(self, nom_apport, pente):
        """
        Remplace la « Flow Hydrograph Slope » d'un apport deja en place.

        La pente est ecrite a la creation de l'injection, avant que le classeur
        existe : sans cette methode, une valeur saisie dans le classeur serait
        restee lettre morte.
        """
        self._verifier_connu(nom_apport)
        if not 1e-6 < float(pente) <= 1.0:
            raise ValueError(f"pente {pente} hors de ]0 ; 1]")
        info = self.carte[nom_apport]
        lignes = _lire_lignes(self.fichier_unsteady)
        # On ne touche QUE le bloc de cet apport : le fichier en contient
        # d'autres, et « Flow Hydrograph Slope= » y apparait plusieurs fois.
        ecrit = False
        for i in range(info["debut"], min(info["fin"] + 3, len(lignes))):
            if lignes[i].startswith("Flow Hydrograph Slope="):
                fin = "\n" if lignes[i].endswith("\n") else ""
                lignes[i] = f"Flow Hydrograph Slope= {pente} {fin}"
                ecrit = True
        if not ecrit:
            raise ValueError(
                f"aucune ligne « Flow Hydrograph Slope= » dans le bloc de "
                f"« {nom_apport} » : la pente ne peut pas y etre imposee.")
        self.fichier_unsteady.write_text("".join(lignes), encoding="utf-8")

    # --- menage de fin de calage -------------------------------------------

    def _titre(self, chemin, cle):
        """Titre declare dans un fichier de plan, de geometrie ou d'unsteady."""
        trouve = re.search(rf"^{cle}=(.*)$", _lire_texte(chemin), re.M)
        return trouve.group(1).strip() if trouve else ""

    def _reliquats(self):
        """
        Traces laissees dans le dossier du modele par la preparation, hors
        plans et fichiers de calcul : les sauvegardes horodatees faites avant
        toute ecriture dans la geometrie ou l'unsteady, et le sous-dossier ou
        le plugin depose les shapefiles transmis au pont.

        Elles ne sont retirees qu'a la FIN D'UN CALAGE REUSSI. Tant qu'il
        n'a pas abouti, les sauvegardes sont le seul retour en arriere
        possible sur le modele.
        """
        traces = sorted(
            self.dossier.glob(f"{self.nom_projet}.*.sauvegarde_*"))
        shapefiles = self.dossier / "_calage"
        if shapefiles.is_dir():
            traces.append(shapefiles)
        return traces

    def nettoyer_reliquats(self, simuler=False):
        """
        Retire les traces de PREPARATION laissees dans le dossier du modele.

        LES PLANS DE CALAGE NE SONT PLUS SUPPRIMES. Chaque etape — « sans
        apport », puis un plan par apport — est justement ce qu'on veut garder :
        elle documente ce qui a ete obtenu, et permet de reprendre un calage
        interrompu sans repartir du premier apport. Leur nombre est borne par
        le nombre d'apports, et jalonner() remplace deja un homonyme d'une
        relance precedente ; le projet ne se remplit donc pas indefiniment.
        En contrepartie, un modele a trente apports garde trente et un jeux de
        resultats : c'est un cout de disque assume, pas un oubli.

        Ce qui part ici n'est reclame par personne : sauvegardes horodatees de
        la preparation, et sous-dossier des shapefiles transmis au pont.

        simuler : ne rien supprimer, rendre seulement la liste.

        Retourne {"reliquats": [...], "conserve": "pXX", "etapes": [...]}.
        """
        traces = self._reliquats()
        rendu = {"reliquats": [t.name for t in traces],
                 "conserve": (f"p{str(self.plan_travail).zfill(2)}"
                              if self.plan_travail is not None else None),
                 "etapes": list(self.etapes)}
        if simuler:
            return rendu
        for trace in traces:
            try:
                if trace.is_dir():
                    shutil.rmtree(trace)
                else:
                    trace.unlink()
            except OSError:
                # Un reliquat verrouille — dossier ouvert dans l'explorateur —
                # ne doit pas faire echouer un calage abouti.
                pass
        return rendu

    def elaguer_etapes(self, prefixe="", simuler=True):
        """
        Retire les plans d'ETAPE d'un calage abouti — et rien d'autre.

        SUR DEMANDE, JAMAIS D'OFFICE (decision utilisateur du 08/09/2026). La
        chaine CONSERVE ses etapes : c'est ce qui documente le calage apport
        par apport et permet de reprendre une sequence interrompue sans
        repartir du premier (voir jalonner et nettoyer_reliquats). Mais une
        fois le calage fini et livre, ces plans ne servent plus qu'a occuper
        le disque — un modele a trente apports en garde trente et un jeux de
        resultats, et cela se compte en dizaines de gigaoctets. On offre donc
        de les retirer APRES COUP, a celui qui sait que le calage est clos.

        TROIS GARDE-FOUS, ET LE PREMIER EST LE PLUS IMPORTANT :

          - RIEN SANS PLAN FINAL. Si aucun plan ne porte
            « <prefixe>_avec_apports », le calage n'a pas conclu : ses etapes
            sont alors tout ce qui existe, et les retirer effacerait le
            calage lui-meme. On refuse, et on le dit.
          - LE PLAN DE REFERENCE ET LE PLAN COURANT SONT INTOUCHABLES, comme
            partout ailleurs dans cette classe.
          - ON NE RECONNAIT QUE NOS PROPRES TITRES. Un plan dont le titre
            n'est ni « <prefixe>_sans_apport » ni « <prefixe>_Apport_… »
            appartient a l'utilisateur et reste, quel qu'il soit.

        LE MENAGE DES DERIVES EST PLUS ETROIT QUE CELUI DE
        _remplacer_homonymes : on ne balaie pas tous les unsteady orphelins du
        projet, mais SEULEMENT ceux que les plans retires designaient. Un
        unsteady que l'utilisateur garde de cote sans plan qui l'emploie n'a
        rien a voir avec ce calage, et un outil de menage n'a pas a en
        decider.

        simuler : ne rien supprimer, rendre seulement ce qui partirait. C'est
            le DEFAUT : cette methode efface des resultats de calcul, et
            l'appelant doit avoir vu la liste avant de la confirmer.

        Rend {"final", "etapes", "supprimes", "simule"} ou, en cas de refus,
        {"refus", "etapes", "supprimes"}.
        """
        final = titre_etape(ETAPE_AVEC_APPORTS, prefixe)
        depart = titre_etape(ETAPE_SANS_APPORT, prefixe)
        marque = titre_etape(PREFIXE_ETAPE_APPORT, prefixe)

        titres = {}
        for chemin in sorted(
                self.dossier.glob(f"{self.nom_projet}.p[0-9][0-9]")):
            titres[chemin.suffix[2:]] = self._titre(chemin, "Plan Title") or ""

        if final not in titres.values():
            return {"refus": (f"aucun plan « {final} » dans ce projet : le "
                              f"calage n'a pas conclu, et ses etapes sont "
                              f"tout ce qu'il en reste. Rien n'est retire."),
                    "etapes": [], "supprimes": []}

        courant = (str(self.plan_travail).zfill(2)
                   if self.plan_travail is not None else None)
        a_retirer = sorted(
            numero for numero, titre in titres.items()
            if (titre == depart or titre.startswith(marque))
            and numero != self.plan_reference and numero != courant)

        # Ce que ces plans designent, RELEVE AVANT de les effacer : apres, le
        # fichier n'est plus la pour le dire.
        designes = set()
        for numero in a_retirer:
            texte = _lire_texte(self.dossier / f"{self.nom_projet}.p{numero}")
            for cle, lettre in (("Flow File", "u"), ("Geom File", "g")):
                trouve = re.search(rf"^{cle}={lettre}(\w+)", texte, re.M)
                if trouve:
                    designes.add(f"{lettre}{trouve.group(1)}")

        if simuler:
            return {"final": final, "etapes": a_retirer, "supprimes": [],
                    "simule": True}

        supprimes = []
        for numero in a_retirer:
            self._effacer_objet(f"p{numero}")
            supprimes.append(f"p{numero}")
        for objet in sorted(designes):
            lettre, numero = objet[0], objet[1:]
            cle = "Flow File" if lettre == "u" else "Geom File"
            if not self._utilise_par_un_plan(cle, lettre, numero):
                self._effacer_objet(objet)
                supprimes.append(objet)
        self._nettoyer_prj()
        return {"final": final, "etapes": a_retirer, "supprimes": supprimes,
                "simule": False}

    def _effacer_objet(self, objet):
        """
        Efface un plan, un unsteady ou une geometrie, et TOUS ses derives.

        Les suffixes sont enumeres, jamais devines par un glob : un
        « {projet}.p16* » emporterait aussi « {projet}.p16x » d'un autre plan
        des que la numerotation passe a trois chiffres. La liste couvre ce que
        HEC-RAS depose par plan calcule — resultats, run file, journal de
        calcul, conditions initiales — et le journal que la chaine ecrit
        elle-meme a cote.
        """
        numero = objet[1:]
        if objet.startswith("p"):
            motifs = [f".p{numero}", f".p{numero}.hdf", f".p{numero}.tmp.hdf",
                      # .snapshot.hdf : cliche de reprise, ecrit en cours de
                      # calcul. Oublie de cette liste, il laissait 16 Mo par
                      # essai derriere lui.
                      f".p{numero}.snapshot.hdf",
                      f".p{numero}.blf", f".p{numero}.data_errors.txt",
                      f".p{numero}.computeMsgs.txt",
                      f".b{numero}", f".bco{numero}", f".x{numero}",
                      f".O{numero}", f".r{numero}",
                      f".ic{numero}", f".ic.o{numero}"]
        elif objet.startswith("g"):
            motifs = [f".g{numero}", f".g{numero}.hdf"]
        else:
            motifs = [f".u{numero}", f".u{numero}.hdf"]
        for suffixe in motifs:
            chemin = self.dossier / f"{self.nom_projet}{suffixe}"
            if chemin.is_file():
                chemin.unlink()
        if objet.startswith("p"):
            # Journal de calcul ecrit par la chaine : il ne porte pas le nom du
            # projet, un glob sur les motifs ci-dessus ne l'aurait pas vu.
            journal = self.dossier / f"_compute_p{numero}.log"
            if journal.is_file():
                journal.unlink()

    def _nettoyer_prj(self):
        """
        Retire du .prj les objets dont le fichier n'existe plus.

        HEC-RAS refuse d'ouvrir un projet declarant un fichier absent : le .prj
        doit suivre la suppression, sinon le projet devient inouvrable. On ne
        retire QUE les lignes dont le fichier a disparu — jamais une liste
        etablie d'avance, qui pourrait deconnecter un fichier encore present.
        """
        prj = self.dossier / f"{self.nom_projet}.prj"
        lignes, gardees = _lire_lignes(prj), []
        for ligne in lignes:
            nu = ligne.strip()
            cible = None
            for prefixe in ("Plan File=", "Geom File=", "Unsteady File=",
                            "Flow File="):
                if nu.startswith(prefixe):
                    cible = self.dossier / (f"{self.nom_projet}."
                                            + nu.split("=", 1)[1].strip())
                    break
            if cible is not None and not cible.exists():
                continue
            gardees.append(ligne)
        if len(gardees) != len(lignes):
            prj.write_text("".join(gardees), encoding="utf-8")

    def _renommer_plan(self, numero, nom):
        """Donne son titre definitif au plan conserve."""
        for suffixe, cle in ((f".p{numero}", "Plan Title="),
                             (f".p{numero}", "Short Identifier=")):
            chemin = self.dossier / f"{self.nom_projet}{suffixe}"
            if not chemin.is_file():
                continue
            lignes = _lire_lignes(chemin)
            for i, ligne in enumerate(lignes):
                if ligne.startswith(cle):
                    fin = "\n" if ligne.endswith("\n") else ""
                    # PLUS DE TRONCATURE ICI. « nom[:24] » rognait en silence,
                    # et c'est lui qui fabriquait le doublon : un plan de
                    # reprise du depot porte « Plan Title=sans apport XXX et
                    # aval » (25 caracteres, intact) et « Short Identifier=
                    # sans apport XXX et ava » (24, rogne). Deux etapes rognees
                    # au meme identifiant partagent le dossier de resultats
                    # que RAS Mapper nomme d'apres ce champ. La longueur est
                    # desormais REFUSEE en amont (calage.titre_etape), avant le
                    # premier calcul.
                    # LE CHAMP N'EST PAS A LARGEUR FIXE, contrairement a ce que
                    # disait ce commentaire : sur les 103 .pXX de 01-cas_test,
                    # l'interface HEC-RAS l'ecrit sur 64, cette chaine sur 24,
                    # ras-commander sans bourrage (17, 22) — et les trois
                    # s'ouvrent. LE BOURRAGE A 24 RESTE QUAND MEME :
                    # « sans_apport ».ljust(24) rend octet pour octet la ligne
                    # des 34 plans que la chaine a deja ecrits.
                    valeur = nom.ljust(24) if "Short" in cle else nom
                    lignes[i] = f"{cle}{valeur}{fin}"
            chemin.write_text("".join(lignes), encoding="utf-8")

    def _reassigner_unsteady(self, numero_plan, numero_unsteady):
        """
        Rattache le plan clone a un fichier unsteady clone, lorsque ce dernier
        n'a pas pu etre passe directement a clone_plan (cas ou le plan de
        reference n'avait pas d'override declare a l'avance).
        """
        fichier_plan = self.dossier / f"{self.nom_projet}.p{numero_plan}"
        lignes = _lire_lignes(fichier_plan)
        for i, ligne in enumerate(lignes):
            if ligne.startswith("Flow File="):
                fin = "\n" if ligne.endswith("\n") else ""
                lignes[i] = f"Flow File=u{str(numero_unsteady).zfill(2)}{fin}"
        fichier_plan.write_text("".join(lignes), encoding="utf-8")

    # --- interface Modele --------------------------------------------------

    def forme_apport(self, nom_apport):
        """Hydrogramme de reference : (temps_h, debit)."""
        self._verifier_connu(nom_apport)
        valeurs = self.originaux[nom_apport]
        pas = self.carte[nom_apport]["intervalle_h"]
        if not pas:
            # Un defaut a 1 h fabriquerait un axe des temps faux sans rien
            # signaler : le recalage temporel et le volume seraient alors
            # calcules sur une duree erronee, et le calage compenserait un
            # ecart qui n'existe pas.
            raise ValueError(
                f"intervalle de temps illisible pour l'apport "
                f"« {nom_apport} » dans {self.fichier_unsteady.name} : la "
                f"ligne « Interval= » de son bloc est absente ou non "
                f"reconnue.")
        return np.arange(len(valeurs)) * pas, valeurs

    def definir_forme(self, nom_apport, temps_h, debits):
        """
        Remplace l'hydrogramme de reference d'un apport, en le reechantillonnant
        sur LA BASE DE TEMPS DU MODELE.

        Le nombre de valeurs et l'intervalle du fichier unsteady ne sont pas
        touches : les rendre variables reviendrait a reecrire l'en-tete du
        bloc, toute une famille d'erreurs que la chaine s'interdit. La forme
        fournie — celle de la cible, typiquement — est donc projetee sur la
        grille existante. Ce qui deborde de la fenetre du modele est
        prolonge par la derniere valeur connue, jamais extrapole.
        """
        self._verifier_connu(nom_apport)
        info = self.carte[nom_apport]
        pas = info["intervalle_h"]
        if not pas:
            raise ValueError(
                f"intervalle de temps illisible pour « {nom_apport} » : "
                f"impossible d'y projeter une forme.")
        nb = len(self.originaux[nom_apport])
        grille = np.arange(nb) * pas
        t = np.asarray(temps_h, dtype=float)
        q = np.asarray(debits, dtype=float)
        ordre = np.argsort(t)
        self.originaux[nom_apport] = np.interp(grille, t[ordre], q[ordre],
                                               left=q[ordre][0],
                                               right=q[ordre][-1])

    def appliquer_facteur(self, nom_apport, facteur):
        """
        Ecrit l'hydrogramme mis a l'echelle. Le nombre de valeurs et
        l'intervalle sont inchanges : l'en-tete du fichier n'a donc pas a etre
        touchee, ce qui elimine toute une famille d'erreurs.
        """
        from ras_commander import RasUnsteady

        self._verifier_connu(nom_apport)
        info = self.carte[nom_apport]
        table = pd.DataFrame({"Value": self.originaux[nom_apport] * float(facteur)})
        RasUnsteady.write_table_to_file(str(self.fichier_unsteady),
                                        MOTIF_HYDROGRAMME, table, info["debut"])

    def _fermer_orphelins(self, processus_avant):
        """
        Ferme les HEC-RAS que NOTRE calcul a laisses derriere lui.

        Un calage lance un HEC-RAS par essai — releve sur un cas reel :
        une instance a 16:49, une a 17:50, une a 18:11. Quand l'une d'elles
        survit a son calcul, elle continue d'ecrire dans les fichiers du
        projet pendant l'essai suivant : c'est ce qui a vide un plan de sa
        geometrie et de son debit. La chaine ne fermait rien.

        Ne ferme QUE ce qui est apparu pendant le calcul : une session
        ouverte par l'utilisateur sur un autre projet est epargnee. L'echec
        de la fermeture n'interrompt jamais le calage.
        """
        restants = orphelins_du_calcul(processus_avant, pids_hecras())
        if not restants:
            return []
        fermes = fermer_processus(restants)
        if fermes:
            print(f"HEC-RAS resté ouvert après le calcul, fermé : "
                  f"{', '.join(fermes)}", flush=True)
        return fermes

    def calculer(self):
        """Lance le calcul et rapporte sa qualite numerique."""
        from ras_commander import RasCmdr, HdfResultsPlan

        debut = time.time()
        self.nb_calculs += 1
        # Empreinte du resultat AVANT calcul : un calcul qui echouerait en
        # laissant en place le HDF de l'essai precedent serait indetectable
        # autrement. La boucle relirait alors les debits de l'essai d'avant,
        # conclurait que le facteur ne change rien, et s'arreterait sur une
        # fausse stagnation apres avoir consomme tous ses essais.
        avant = (self.hdf_resultats.stat().st_mtime_ns
                 if self.hdf_resultats.exists() else None)
        # Photographie des processus HEC-RAS AVANT le calcul : ce qui aura
        # surgi entre-temps et sera encore vivant apres est un orphelin de
        # NOTRE calcul, et de personne d'autre.
        processus_avant = pids_hecras() if self.fermer_orphelins else None
        try:
            # num_cores : ras-commander (RasPlan.set_num_cores, relu sur
            # GitHub le 22/09/2026, v0.99 a v0.102) reecrit AVANT le calcul
            # chaque ligne « UNET D1 Cores= », « UNET D2 Cores= » et
            # « PS Cores= » du plan calcule — ici le plan d'etape, jamais le
            # plan de reference. 0 vaudrait « tous » ; None laisse le plan tel
            # quel. LIMITE CONNUE : il relit et reecrit le plan en utf-8 avec
            # errors="replace" ; un titre accentue ecrit en cp1252 y perdrait
            # ses accents. Les titres d'etape sont en ASCII.
            options = {"num_cores": self.coeurs} if self.coeurs else {}
            reussi = RasCmdr.compute_plan(self.plan_travail,
                                          overwrite_dest=True, **options)
        except Exception as e:
            self._fermer_orphelins(processus_avant)
            return ResultatCalcul(reussi=False, duree_s=time.time() - debut,
                                  message=f"{type(e).__name__}: {e}")
        self._fermer_orphelins(processus_avant)

        duree = time.time() - debut
        if not reussi:
            return ResultatCalcul(reussi=False, duree_s=duree,
                                  message="compute_plan a retourne un echec")

        if not self.hdf_resultats.exists():
            return ResultatCalcul(
                reussi=False, duree_s=duree,
                message=f"calcul annonce reussi mais {self.hdf_resultats.name} "
                        f"est absent")
        if avant is not None and self.hdf_resultats.stat().st_mtime_ns == avant:
            return ResultatCalcul(
                reussi=False, duree_s=duree,
                message=f"calcul annonce reussi mais {self.hdf_resultats.name} "
                        f"n'a pas ete reecrit : les resultats seraient ceux de "
                        f"l'essai precedent")

        # LE FICHIER EXISTE ET EST FRAIS — CELA NE PROUVE PAS QU'IL CONTIENT
        # DES RESULTATS. Mesure sur un cas reel : HEC-RAS a pretraite la
        # geometrie, ecrit les donnees de plan dans un .tmp.hdf de 17 Mo, puis
        # s'est arrete sans lancer la simulation. Il restait un .hdf de 12 ko
        # ne contenant que « Results/Summary », et ras-commander a pourtant
        # rendu un succes. La boucle poursuivait alors jusqu'a echouer bien
        # plus loin, sur une erreur de lecture qui n'expliquait rien.
        absents = _series_absentes(self.hdf_resultats)
        if absents:
            return ResultatCalcul(
                reussi=False, duree_s=duree,
                message=f"calcul annonce reussi mais SANS RESULTATS : "
                        f"{absents}. {_messages_hecras(self.hdf_resultats)}")

        bilan = float("nan")
        try:
            comptes = HdfResultsPlan.get_volume_accounting(self.hdf_resultats)
            bilan = bilan_masse_depuis_comptes(comptes)
        except Exception:
            pass

        return ResultatCalcul(reussi=True, duree_s=duree,
                              bilan_masse_pct=bilan)

    def lire_section(self, nom_section):
        """
        Hydrogramme calcule a une section de controle : (temps_h, debit).

        LE PLAN COURANT N'A PAS TOUJOURS DE RESULTATS. jalonner() fait pointer
        le modele sur un plan neuf, dont le .hdf n'existe qu'apres calculer().
        Sans ce controle, la lecture echouait sur une erreur de fichier
        introuvable qui ne disait pas laquelle des deux choses manquait — le
        calcul ou la section.
        """
        from pont_hecras import lire_serie_hdf

        if not self.hdf_resultats.exists():
            raise RuntimeError(
                f"le plan « {self.etape or self.plan_travail} » n'a pas encore "
                f"de resultats ({self.hdf_resultats.name} absent) : il faut "
                f"calculer avant de lire la section « {nom_section} ».")
        serie = lire_serie_hdf(self.hdf_resultats, nom_section,
                               groupe="Reference Lines")
        return (serie["temps"].to_numpy(dtype=float),
                serie["debit_m3s"].to_numpy(dtype=float))

    # --- utilitaires -------------------------------------------------------

    def _verifier_connu(self, nom_apport):
        if nom_apport not in self.carte:
            raise KeyError(
                f"condition limite « {nom_apport} » absente du fichier "
                f"unsteady. Presentes : {sorted(self.carte)}")


# ---------------------------------------------------------------------------
# Diagnostic de raccordement, sans lancer de calcul
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # SORTIE EN UTF-8, MEME LANCE A LA MAIN. Les auto-tests de ce module
    # impriment des caracteres hors ASCII (« → », « Δ », les guillemets
    # francais). Dans une console ou une redirection Windows, la sortie prend
    # l'encodage local — cp1252 sur un poste francais — et le premier de ces
    # caracteres leve UnicodeEncodeError : l'auto-test s'interrompt sur ce qui
    # ressemble a un defaut du module, alors que rien n'est casse. Le pont
    # impose PYTHONIOENCODING=utf-8 a la chaine lancee par le plugin ; ceci
    # couvre l'appel direct, que la documentation recommande pourtant.
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import argparse
    import shutil
    import tempfile

    print("=" * 74)
    print("AUTO-TEST — lecture du bilan de masse et creation d'un apport")
    print("=" * 74)
    _echecs_test = []

    def _verifier(libelle, condition, detail=""):
        # Le DETAIL est facultatif mais precieux : « [OK] ... » ne dit pas sur
        # quelle valeur le controle a porte, et c'est ce qui manque le jour ou
        # il faut comprendre pourquoi il ne passe plus.
        print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
              + (f"  ->  {detail}" if detail else ""))
        if not condition:
            _echecs_test.append(libelle)

    def _leve(exception, fonction, *args, **kwargs):
        """Vrai si l'appel leve bien l'exception attendue."""
        try:
            fonction(*args, **kwargs)
        except exception:
            return True
        except Exception:
            return False
        return False

    # Colonnes REELLEMENT observees sur un calcul reel (ras-commander 0.99.1,
    # 2026-07-26) : c'est ce format qui avait echappe au premier filtre et
    # laissait le bilan a NaN en silence.
    _comptes_reels = pd.DataFrame({
        "Error": [0.079627],
        "Error Percent": [0.0008],
        "Total Boundary Flux of Water In": [9954.874023],
        "Total Boundary Flux of Water Out": [9204.600586],
        "Vol Accounting in": ["1000 m^3"],
        "Volume Ending": [750.353149],
        "Volume Starting": [0.0],
    })
    _verifier("colonne reelle « Error Percent » lue correctement",
              abs(bilan_masse_depuis_comptes(_comptes_reels) - 0.0008) < 1e-9)

    _comptes_avec_symbole = pd.DataFrame({"Error %": [1.23]})
    _verifier("variante avec symbole « % » toujours reconnue",
              abs(bilan_masse_depuis_comptes(_comptes_avec_symbole) - 1.23) < 1e-9)

    _verifier("DataFrame vide -> NaN, pas d'exception",
              pd.isna(bilan_masse_depuis_comptes(pd.DataFrame())))
    _verifier("None -> NaN, pas d'exception",
              pd.isna(bilan_masse_depuis_comptes(None)))
    _verifier("aucune colonne pertinente -> NaN",
              pd.isna(bilan_masse_depuis_comptes(pd.DataFrame({"Autre": [1]}))))

    # --- creation d'une condition limite dans un fichier unsteady ----------
    print("\n--- ajouter_condition_limite_debit ---")

    # Ligne relevee TELLE QUELLE dans un fichier unsteady reel : elle fige le
    # format a largeur fixe, qu'aucun test synthetique ne pourrait deviner.
    _reelle = ("Boundary Location=                ,                ,        ,"
               "        ,                ,Perimeter 1     ,                ,"
               "IN_AMONT                        ,"
               "                                ")
    _verifier("la ligne produite est identique au format reel de HEC-RAS",
              ligne_localisation("IN_AMONT", "Perimeter 1") == _reelle)

    _verifier("un nom trop long est refuse, pas tronque en silence",
              _leve(ValueError, ligne_localisation, "N" * 33, "Perimeter 1"))

    _tampon = Path(tempfile.gettempdir()) / "_essai_calage_apports.u01"
    _tampon.write_text(
        "Flow Title=Essai\n"
        "Use Restart= 0 \n"
        + ligne_localisation("EXISTANT", "Perimeter 1") + "\n"
        "Interval=15MIN\n"
        "Flow Hydrograph= 4 \n"
        "    1.00    2.00    3.00    4.00\n"
        "Flow Hydrograph Slope= 0.02 \n",
        encoding="utf-8")

    _debits = [10.0, 25.5, 40.0, 30.25, 12.0, 5.0, 2.5]
    _n = ajouter_condition_limite_debit(_tampon, "APPORT_ESSAI", "Perimeter 1",
                                        _debits, pente=0.01)
    _verifier("nombre de valeurs ecrites correct", _n == len(_debits))

    _texte = _tampon.read_text(encoding="utf-8")
    # Le pas de l'apport cree DOIT valoir 6 min : c'est celui auquel les cibles
    # sont ramenees a la lecture du classeur. Un apport cree a 15 min obligeait
    # definir_forme a reechantillonner la cible une seconde fois.
    _verifier("l'apport cree porte l'intervalle de 6 min",
              f"Interval={INTERVALLE_APPORT}\n" in _texte
              and _texte.count("Interval=15MIN") == 1,
              INTERVALLE_APPORT)
    _verifier("la condition limite existante est preservee",
              "EXISTANT" in _texte and "Flow Hydrograph= 4 " in _texte)
    _verifier("la pente demandee est ecrite",
              "Flow Hydrograph Slope= 0.01 " in _texte)

    # -----------------------------------------------------------------------
    # PENTES DEPOSEES AVANT LE CALAGE, APPLIQUEES APRES LE CLONAGE.
    #
    # Releve en production : « pente de A1 non appliquee : condition limite
    # A1 absente du fichier unsteady. Presentes : [] ». La liste etait VIDE —
    # ce n'est pas l'apport qui manquait, c'est la carte des blocs, que seul
    # preparer() construit. _appliquer_pentes() du pont tournant AVANT lui,
    # toutes les pentes saisies au classeur etaient perdues derriere un
    # avertissement. Les deux controles ci-dessous tiennent l'ordre.
    # -----------------------------------------------------------------------
    _pilote_pente = PiloteHecRas(_tampon.parent, "_essai_calage_apports",
                                 plan_reference="01")
    _pilote_pente.fichier_unsteady = _tampon
    _pilote_pente.carte = cartographier_hydrogrammes(_tampon)
    _pilote_pente.pentes = {"APPORT_ESSAI": 0.037}
    _pilote_pente._appliquer_pentes_deposees()
    _verifier("une pente deposee est bien ecrite dans le fichier unsteady",
              "Flow Hydrograph Slope= 0.037 " in _tampon.read_text(
                  encoding="utf-8"))

    import ast as _ast
    import inspect as _inspect
    import textwrap as _textwrap
    _src_preparer = _textwrap.dedent(_inspect.getsource(PiloteHecRas.preparer))
    _verifier("preparer() applique les pentes deposees, sinon elles se perdent",
              any(isinstance(n, _ast.Call)
                  and isinstance(n.func, _ast.Attribute)
                  and n.func.attr == "_appliquer_pentes_deposees"
                  for n in _ast.walk(_ast.parse(_src_preparer))))

    _carte = cartographier_hydrogrammes(_tampon)
    _verifier("l'apport cree est relu par cartographier_hydrogrammes",
              "APPORT_ESSAI" in _carte)
    if "APPORT_ESSAI" in _carte:
        _info = _carte["APPORT_ESSAI"]
        _relus = lire_hydrogramme_unsteady(_tampon, _info["debut"],
                                              _info["fin"])
        _verifier("les debits relus sont EXACTEMENT ceux ecrits",
                  len(_relus) == len(_debits)
                  and max(abs(a - b) for a, b in zip(_relus, _debits)) < 1e-9)
        _verifier("l'intervalle est relu correctement",
                  abs(_info["intervalle_h"] - 0.1) < 1e-9,
                  f"{60 * _info['intervalle_h']:.0f} min")
        _verifier("la zone 2D est relue correctement",
                  _info["zone"] == "Perimeter 1")

    _verifier("un doublon de nom est refuse",
              _leve(ValueError, ajouter_condition_limite_debit, _tampon,
                    "APPORT_ESSAI", "Perimeter 1", _debits))

    # --- re-cadencage d'un apport DEJA present ------------------------------
    print("\n--- imposer_intervalle_apport ---")
    # « EXISTANT » porte 4 valeurs au quart d'heure, soit 0,75 h — une duree
    # qui n'est PAS un multiple entier de 6 min (7,5 pas). Le cas est
    # volontaire : il exerce la regle de prolongation.
    _cr = imposer_intervalle_apport(_tampon, "EXISTANT")
    _verifier("le pas d'un apport existant est ramene a 6 min",
              _cr and _cr["intervalle_apres"] == INTERVALLE_APPORT,
              f"{60 * _cr['intervalle_avant_h']:.0f} min -> "
              f"{_cr['intervalle_apres']}" if _cr else "aucun compte rendu")
    _verifier("la DUREE commande le compte, pas le nombre de valeurs",
              _cr and _cr["nb_avant"] == 4 and _cr["nb_apres"] == 9
              and abs(_cr["duree_h"] - 0.75) < 1e-9,
              f"{_cr['nb_avant']} -> {_cr['nb_apres']} valeurs sur "
              f"{_cr['duree_h']:.2f} h" if _cr else "")
    _verifier("une duree non multiple du pas PROLONGE, jamais ne raccourcit",
              _cr and _cr["prolonge_h"] > 0
              and _cr["prolonge_h"] <= 0.1 + 1e-9,
              f"+{60 * _cr['prolonge_h']:.0f} min de queue plate" if _cr else "")

    _carte_r = cartographier_hydrogrammes(_tampon)
    _vals_r = lire_hydrogramme_unsteady(_tampon, _carte_r["EXISTANT"]["debut"],
                                           _carte_r["EXISTANT"]["fin"])
    # Aux instants de l'ANCIENNE grille, les valeurs doivent etre intactes :
    # une interpolation lineaire repasse par ses points d'appui. C'est ce qui
    # garantit qu'un pic n'est ni deplace ni ecrete par le re-cadencage.
    _verifier("les valeurs d'origine sont retrouvees a leur instant",
              len(_vals_r) == 9
              and max(abs(_vals_r[int(2.5 * k)] - v)
                      for k, v in enumerate([1.0, 2.0, 3.0, 4.0])
                      if (2.5 * k) % 1 == 0) < 1e-6,
              f"{[round(float(v), 2) for v in _vals_r]}")
    _verifier("la queue prolongee tient la derniere valeur, sans extrapoler",
              abs(_vals_r[-1] - 4.0) < 1e-6, f"{_vals_r[-1]:.2f} attendu 4.00")

    _bilan_r = verifier_intervalle_apports(_tampon)
    _verifier("le controle relit un fichier conforme",
              _bilan_r["EXISTANT"]["conforme"]
              and _bilan_r["EXISTANT"]["annonce"] == 9,
              _bilan_r["EXISTANT"]["motif"] or "conforme, en-tete accordee")

    # Duree multiple exact du nouveau pas : aucune prolongation, et le pic
    # horaire doit se retrouver a l'identique dix pas plus loin.
    _tampon2 = Path(tempfile.gettempdir()) / "_essai_calage_recadence.u01"
    _tampon2.write_text(
        "Flow Title=Essai\n"
        + ligne_localisation("HORAIRE", "Perimeter 1") + "\n"
        "Interval=1HOUR\n"
        "Flow Hydrograph= 4 \n"
        "   10.00   50.00  100.00   20.00\n"
        "Flow Hydrograph Slope= 0.02 \n",
        encoding="utf-8")
    _cr2 = imposer_intervalle_apport(_tampon2, "HORAIRE")
    _c2 = cartographier_hydrogrammes(_tampon2)
    _v2 = lire_hydrogramme_unsteady(_tampon2, _c2["HORAIRE"]["debut"],
                                       _c2["HORAIRE"]["fin"])
    _verifier("3 h au pas horaire font 31 valeurs au pas de 6 min",
              _cr2 and _cr2["nb_apres"] == 31 and abs(_cr2["prolonge_h"]) < 1e-9,
              f"{_cr2['nb_avant']} -> {_cr2['nb_apres']} valeurs, "
              f"prolonge de {_cr2['prolonge_h']:.3f} h" if _cr2 else "")
    _verifier("le pic horaire est retrouve a la meme heure et a la meme valeur",
              abs(_v2[20] - 100.0) < 1e-6 and abs(float(np.max(_v2)) - 100.0) < 1e-6,
              f"t=2 h -> {_v2[20]:.2f}, pic {float(np.max(_v2)):.2f}")
    _tampon2.unlink(missing_ok=True)
    _verifier("un apport deja au bon pas n'est pas retouche",
              imposer_intervalle_apport(_tampon, "EXISTANT") is None)
    _verifier("un apport inconnu leve une erreur nommant les presents",
              _leve(ValueError, imposer_intervalle_apport, _tampon, "ABSENT"))

    # Une en-tete desaccordee du tableau doit etre VUE : c'est la panne
    # silencieuse que le controle existe pour attraper.
    _texte_faux = _tampon.read_text(encoding="utf-8").replace(
        "Flow Hydrograph= 9 ", "Flow Hydrograph= 12 ")
    _tampon.write_text(_texte_faux, encoding="utf-8")
    _verifier("une en-tete qui ment sur le nombre de valeurs est detectee",
              not verifier_intervalle_apports(_tampon)["EXISTANT"]["conforme"],
              verifier_intervalle_apports(_tampon)["EXISTANT"]["motif"])
    _tampon.unlink(missing_ok=True)

    # -----------------------------------------------------------------------
    # RE-CADENCAGE AUTOMATIQUE A LA PREPARATION.
    #
    # Sans lui, la cible ramenee a 6 min par la lecture du classeur etait
    # reprojetee sur la grille HORAIRE de l'apport par definir_forme() : neuf
    # valeurs sur dix de ce que l'utilisateur avait saisi disparaissaient a
    # l'ecriture, en silence. Les deux controles ci-dessous tiennent l'ordre
    # ET l'effet.
    # -----------------------------------------------------------------------
    print("\n--- _recadencer_apports (branche dans preparer) ---")
    _tampon3 = Path(tempfile.gettempdir()) / "_essai_calage_prepare.u01"
    _tampon3.write_text(
        "Flow Title=Essai\n"
        + ligne_localisation("AMONT", "Perimeter 1") + "\n"
        "Interval=1HOUR\n"
        "Flow Hydrograph= 4 \n"
        "   10.00   50.00  100.00   20.00\n"
        "Flow Hydrograph Slope= 0.02 \n"
        + ligne_localisation("DEJA_FIN", "Perimeter 1") + "\n"
        "Interval=6MIN\n"
        "Flow Hydrograph= 3 \n"
        "    1.00    2.00    3.00\n"
        "Flow Hydrograph Slope= 0.02 \n",
        encoding="utf-8")
    _pilote_recad = PiloteHecRas(_tampon3.parent, "_essai_calage_prepare",
                                 plan_reference="01")
    _pilote_recad.fichier_unsteady = _tampon3
    _pilote_recad.carte = cartographier_hydrogrammes(_tampon3)
    _convertis = _pilote_recad._recadencer_apports()
    _verifier("seul l'apport au mauvais pas est converti",
              len(_convertis) == 1 and _convertis[0]["nom"] == "AMONT",
              f"{[c['nom'] for c in _convertis]}")
    _verifier("la carte est RECONSTRUITE apres le re-cadencage",
              _pilote_recad.carte["AMONT"]["intervalle_h"] == 0.1
              and _pilote_recad.carte["AMONT"]["fin"]
              - _pilote_recad.carte["AMONT"]["debut"] == 4,
              f"pas {60 * _pilote_recad.carte['AMONT']['intervalle_h']:.0f} min, "
              f"{_pilote_recad.carte['AMONT']['fin'] - _pilote_recad.carte['AMONT']['debut']} "
              f"ligne(s) de tableau")
    _verifier("le second apport, deja au bon pas, est intact",
              _pilote_recad.carte["DEJA_FIN"]["intervalle_h"] == 0.1,
              f"pas {60 * _pilote_recad.carte['DEJA_FIN']['intervalle_h']:.0f} min")
    _verifier("un fichier deja entierement a 6 min ne declenche rien",
              _pilote_recad._recadencer_apports() == [])
    _tampon3.unlink(missing_ok=True)

    # -----------------------------------------------------------------------
    # CORRECTION AUTOMATIQUE : UNE CONDITION LIMITE NON PILOTEE AU MAUVAIS PAS.
    #
    # Cas reel du 2026-08-05 : la cible est native a 3 min,
    # pas_travail_h vaut donc 0,05 h — jamais le plancher fige 6 min. Une
    # condition hors calage (ici « BC_MAUVAIS », l'equivalent de la
    # « BC Line 1 » du projet reel) reste a 6 min : un libelle herite du
    # modele qui a servi de base, perime pour les valeurs qu'elle porte
    # (demande utilisateur : donnees_calage.xlsx fait AUTORITE sur le pas, le
    # calage doit corriger lui-meme l'intervalle plutot que d'arreter et
    # renvoyer l'utilisateur rouvrir HEC-RAS a la main). La correction est un
    # RE-ETIQUETAGE (Interval= seul) : jamais un re-echantillonnage, qui
    # fabriquerait des valeurs sur une condition dont le contenu est final.
    # -----------------------------------------------------------------------
    print("\n--- correction automatique d'une condition NON pilotee ---")
    _verifier("intervalle_hecras_depuis_heures traduit un pas en minutes "
              "entieres",
              intervalle_hecras_depuis_heures(0.05) == "3MIN"
              and intervalle_hecras_depuis_heures(1.0) == "60MIN")
    _verifier("un pas non representable en minutes entieres est refuse",
              _leve(ValueError, intervalle_hecras_depuis_heures, 0.017))

    _tampon4 = Path(tempfile.gettempdir()) / "_essai_calage_garde_fou.u01"
    _tampon4.write_text(
        "Flow Title=Essai\n"
        + ligne_localisation("APPORT_01", "Perimeter 1") + "\n"
        "Interval=1HOUR\n"
        "Flow Hydrograph= 4 \n"
        "   10.00   50.00  100.00   20.00\n"
        "Flow Hydrograph Slope= 0.02 \n"
        + ligne_localisation("BC_AMONT", "Perimeter 1") + "\n"
        "Interval=3MIN\n"
        "Flow Hydrograph= 3 \n"
        "    1.00    2.00    3.00\n"
        "Flow Hydrograph Slope= 0.02 \n"
        + ligne_localisation("BC_MAUVAIS", "Perimeter 1") + "\n"
        "Interval=6MIN\n"
        "Flow Hydrograph= 3 \n"
        "    5.00    6.00    7.00\n"
        "Flow Hydrograph Slope= 0.02 \n",
        encoding="utf-8")
    # Seul « APPORT_01 » est pilote par CE calage : pas_travail_h vient de la
    # cible (3 min), comme le ferait commande_caler().
    _pilote_garde = PiloteHecRas(_tampon4.parent, "_essai_calage_garde_fou",
                                 plan_reference="01", pas_travail_h=0.05,
                                 apports_a_caler=["APPORT_01"])
    _pilote_garde.fichier_unsteady = _tampon4
    _pilote_garde.carte = cartographier_hydrogrammes(_tampon4)
    _valeurs_avant = lire_hydrogramme_unsteady(
        _tampon4, _pilote_garde.carte["BC_MAUVAIS"]["debut"],
        _pilote_garde.carte["BC_MAUVAIS"]["fin"])
    try:
        _pilote_garde._recadencer_apports()
        _msg_garde = None
    except ValueError as e:
        _msg_garde = str(e)
    _verifier("la condition non pilotee au mauvais pas ne bloque plus le "
              "calage : elle est corrigee automatiquement",
              _msg_garde is None, _msg_garde or "corrigee sans exception")

    _carte_garde = cartographier_hydrogrammes(_tampon4)
    _verifier("l'apport PILOTE est toujours RE-ECHANTILLONNE a 3 min",
              abs(_carte_garde["APPORT_01"]["intervalle_h"] - 0.05) < 1e-9,
              f"pas {60 * _carte_garde['APPORT_01']['intervalle_h']:.1f} min")
    _verifier("la condition non pilotee mais deja conforme n'a pas ete "
              "touchee",
              abs(_carte_garde["BC_AMONT"]["intervalle_h"] - 0.05) < 1e-9)
    _verifier("la condition non pilotee et fautive est RE-ECHANTILLONNEE a "
              "3 min",
              abs(_carte_garde["BC_MAUVAIS"]["intervalle_h"] - 0.05) < 1e-9,
              f"pas {60 * _carte_garde['BC_MAUVAIS']['intervalle_h']:.1f} min")
    _valeurs_apres = lire_hydrogramme_unsteady(
        _tampon4, _carte_garde["BC_MAUVAIS"]["debut"],
        _carte_garde["BC_MAUVAIS"]["fin"])
    # LA DUREE EST CONSERVEE, PAS LE NOMBRE DE VALEURS. 3 valeurs a 6 min
    # couvrent 12 min ; les memes 12 min en demandent 5 au pas de 3 min. Le
    # re-etiquetage seul, qui gardait les 3 valeurs, ramenait la duree a 6 min
    # — c'est ce qui a fait echouer un calage reel (voir _recadencer_apports).
    _verifier("le RE-ECHANTILLONNAGE conserve la DUREE de la condition non "
              "pilotee",
              len(_valeurs_apres) == 5,
              f"{len(_valeurs_avant)} valeurs (12 min) -> "
              f"{len(_valeurs_apres)} valeurs "
              f"({3 * (len(_valeurs_apres) - 1)} min)")
    _verifier("les valeurs d'origine sont retrouvees A LEURS INSTANTS : rien "
              "n'est deplace ni ecrete",
              [_valeurs_apres[0], _valeurs_apres[2], _valeurs_apres[4]]
              == list(_valeurs_avant),
              f"{list(_valeurs_avant)} -> {list(_valeurs_apres)}")
    _tampon4.unlink(missing_ok=True)

    # GARDE-FOU DE DUREE : une condition qui s'arrete avant la fin de la
    # simulation fait refuser le calcul par HEC-RAS (« Time series data ends
    # before the end of the simulation ») sans que ras-commander le rapporte.
    # Cas reel du 2026-08-07 : 20,10 h de donnees pour 33 h simulees.
    _tampon6 = Path(tempfile.gettempdir()) / "_essai_duree.u01"
    _tampon6.write_text(
        "Flow Title=Essai\n"
        + ligne_localisation("COURTE", "Perimeter 1") + "\n"
        "Interval=1HOUR\n"
        "Flow Hydrograph= 3 \n"
        "    1.00    2.00    3.00\n"
        "Flow Hydrograph Slope= 0.02 \n",
        encoding="utf-8")
    _plan6 = Path(tempfile.gettempdir()) / "_essai_duree.p01"
    _plan6.write_text("Plan Title=Essai\n"
                      "Simulation Date=01JUL2024,00:00,02JUL2024,09:00\n",
                      encoding="utf-8")
    _courtes = conditions_trop_courtes(_tampon6, _plan6)
    _verifier("une condition plus courte que la simulation est detectee, avec "
              "ses deux durees",
              "COURTE" in _courtes
              and abs(_courtes["COURTE"]["duree_h"] - 2.0) < 1e-9
              and abs(_courtes["COURTE"]["simulation_h"] - 33.0) < 1e-9,
              str(_courtes))
    _plan6.write_text("Plan Title=Essai\n"
                      "Simulation Date=01JUL2024,00:00,01JUL2024,02:00\n",
                      encoding="utf-8")
    _verifier("une condition qui couvre EXACTEMENT la simulation est acceptee",
              conditions_trop_courtes(_tampon6, _plan6) == {},
              str(conditions_trop_courtes(_tampon6, _plan6)))
    _verifier("sans fenetre de simulation lisible, rien n'est bloque",
              conditions_trop_courtes(_tampon6, _plan6.with_suffix(".pZZ"))
              == {})
    _tampon6.unlink(missing_ok=True)
    _plan6.unlink(missing_ok=True)

    # Cas RESIDUEL : une condition dont le bloc est trop abime pour etre
    # corrige (pas de ligne Interval= reconnaissable). Le re-cadencage echoue
    # proprement (avertissement), et c'est alors verifier_intervalle_apports()
    # qui arrete le calage avant tout calcul, en la nommant.
    _tampon5 = Path(tempfile.gettempdir()) / "_essai_calage_garde_fou_kox.u01"
    _tampon5.write_text(
        "Flow Title=Essai\n"
        + ligne_localisation("APPORT_01", "Perimeter 1") + "\n"
        "Interval=3MIN\n"
        "Flow Hydrograph= 2 \n"
        "    1.00    2.00\n"
        "Flow Hydrograph Slope= 0.02 \n"
        # Bloc volontairement sans ligne « Interval= » exploitable.
        + ligne_localisation("BC_ABIMEE", "Perimeter 1") + "\n"
        "Flow Hydrograph= 2 \n"
        "    3.00    4.00\n"
        "Flow Hydrograph Slope= 0.02 \n",
        encoding="utf-8")
    _pilote_garde5 = PiloteHecRas(_tampon5.parent, "_essai_calage_garde_fou_kox",
                                  plan_reference="01", pas_travail_h=0.05,
                                  apports_a_caler=["APPORT_01"])
    _pilote_garde5.fichier_unsteady = _tampon5
    _pilote_garde5.carte = cartographier_hydrogrammes(_tampon5)
    _verifier("le cas residuel est bien construit : le bloc abime n'a pas "
              "d'intervalle lisible",
              _pilote_garde5.carte.get("BC_ABIMEE", {}).get("intervalle_h")
              is None)
    try:
        _pilote_garde5._recadencer_apports()
        _msg_garde5 = None
    except ValueError as e:
        _msg_garde5 = str(e)
    _verifier("une condition non pilotee irreparable arrete encore le "
              "calage AVANT calcul, en la nommant",
              _msg_garde5 is not None and "BC_ABIMEE" in _msg_garde5,
              _msg_garde5 or "aucune exception levee")
    _tampon5.unlink(missing_ok=True)

    # L'ORDRE EST L'INVARIANT : recadencer APRES avoir fige self.originaux
    # laisserait la boucle travailler sur des valeurs qui ne sont plus celles
    # du fichier. Le test lit la source plutot que de simuler un clonage, qui
    # exigerait HEC-RAS.
    _src_prep = _textwrap.dedent(_inspect.getsource(PiloteHecRas.preparer))
    _corps = _ast.parse(_src_prep).body[0].body
    _rang_recad = next((i for i, n in enumerate(_corps)
                        if "_recadencer_apports" in _ast.dump(n)), None)
    _rang_originaux = next((i for i, n in enumerate(_corps)
                            if "originaux" in _ast.dump(n)), None)
    _verifier("preparer() recadence AVANT de figer les hydrogrammes d'origine",
              _rang_recad is not None and _rang_originaux is not None
              and _rang_recad < _rang_originaux,
              f"recadencage en position {_rang_recad}, "
              f"originaux en position {_rang_originaux}")

    # --- deux pieges releves sur le fichier unsteady reel du projet -------
    print("\n--- cartographier_hydrogrammes : bornage et zones ---")
    _piege = Path(tempfile.gettempdir()) / "_essai_calage_pieges.u01"
    _piege.write_text(
        "Flow Title=Essai\n"
        # Une SORTIE : pas d'hydrogramme, seulement une pente imposee.
        + ligne_localisation("SORTIE_AVAL", "Perimeter 1") + "\n"
        "Friction Slope=0.02,0\n"
        # Un apport, dans la zone reelle.
        + ligne_localisation("APPORT_A", "Perimeter 1") + "\n"
        "Interval=15MIN\n"
        "Flow Hydrograph= 3 \n"
        "    7.00    8.00    9.00\n"
        "Flow Hydrograph Slope= 0.01 \n"
        # Le MEME nom, dans une zone devenue orpheline.
        + ligne_localisation("APPORT_A", "Zone_orpheline") + "\n"
        "Interval=15MIN\n"
        "Flow Hydrograph= 3 \n"
        "  100.00  200.00  300.00\n"
        "Flow Hydrograph Slope= 0.02 \n"
        # DANS LA BONNE ZONE, mais SANS BC line en geometrie : le residu que
        # HEC-RAS ignore et que le calage prenait pour une condition vive.
        + ligne_localisation("APPORT_B", "Perimeter 1") + "\n"
        "Interval=15MIN\n"
        "Flow Hydrograph= 2 \n"
        "    1.00    2.00\n"
        "Flow Hydrograph Slope= 0.03 \n",
        encoding="utf-8")

    _c = cartographier_hydrogrammes(_piege)
    _verifier("une sortie sans hydrogramme n'est PAS prise pour un apport",
              "SORTIE_AVAL" not in _c)
    _verifier("le doublon de zone est signale, pas ignore",
              _c.get("APPORT_A", {}).get("autres_zones") == ["Zone_orpheline"])

    _cz = cartographier_hydrogrammes(_piege, "Perimeter 1")
    _verifier("le filtrage par zone leve l'ambiguite",
              "APPORT_A" in _cz and not _cz["APPORT_A"]["autres_zones"])
    if "APPORT_A" in _cz:
        _v = lire_hydrogramme_unsteady(_piege, _cz["APPORT_A"]["debut"],
                                          _cz["APPORT_A"]["fin"])
        _verifier("c'est bien le bloc de la BONNE zone qui est retenu",
                  list(_v) == [7.0, 8.0, 9.0])

    _co = cartographier_hydrogrammes(_piege, "Zone_orpheline")
    _verifier("filtrer sur la zone orpheline retourne bien l'autre bloc",
              "APPORT_A" in _co
              and list(lire_hydrogramme_unsteady(
                  _piege, _co["APPORT_A"]["debut"],
                  _co["APPORT_A"]["fin"])) == [100.0, 200.0, 300.0])

    # --- BLOCS SANS BC LINE EN GEOMETRIE : HEC-RAS LES IGNORE, NOUS AUSSI ---
    # Cas reel du 30/08/2026 : un unsteady de 45 blocs pour 14 BC lines en
    # geometrie. Deux des blocs surnumeraires, restes courts, ont fait
    # REFUSER trois lancements sur des series que le solveur n'ouvre jamais.
    _verifier("un bloc sans BC line en geometrie est ignore",
              set(cartographier_hydrogrammes(
                  _piege, "Perimeter 1", {"APPORT_A"})) == {"APPORT_A"})
    _verifier("le filtre retire bien un nom absent de la geometrie",
              "APPORT_B" not in cartographier_hydrogrammes(
                  _piege, "Perimeter 1", {"APPORT_A"})
              and "APPORT_B" in cartographier_hydrogrammes(
                  _piege, "Perimeter 1"))
    # NONE VEUT DIRE « JE NE SAIS PAS », PAS « AUCUNE ». Une geometrie
    # illisible doit desactiver le filtre, jamais vider la carte : sinon un
    # incident de lecture arreterait un calage parfaitement valide.
    _verifier("noms_connus=None n'ote rien (geometrie illisible)",
              cartographier_hydrogrammes(_piege, "Perimeter 1", None)
              == cartographier_hydrogrammes(_piege, "Perimeter 1"))
    _verifier("une geometrie VRAIMENT vide, elle, ne laisse rien passer",
              cartographier_hydrogrammes(_piege, "Perimeter 1", set()) == {})
    # LE FILTRE DOIT VALOIR PARTOUT OU LA CARTE EST ENUMEREE, pas seulement a
    # l'ecriture. Pose a deux endroits sur trois le 30/08, il laissait
    # verifier_intervalle_apports() se prononcer sur des orphelins que le
    # re-cadencage avait volontairement laisses tranquilles : le calage
    # s'arretait sur « pas 0.5 h au lieu de 0.1 » pour des conditions que
    # HEC-RAS n'ouvre meme pas (releve le 31/08/2026, second poste).
    _sans_filtre = verifier_intervalle_apports(_piege, "Perimeter 1",
                                               intervalle="15MIN")
    _avec_filtre = verifier_intervalle_apports(_piege, "Perimeter 1",
                                               intervalle="15MIN",
                                               noms_connus={"APPORT_A"})
    # --- LES MESSAGES DE HEC-RAS SONT DANS LE HDF, MEME PARTIEL ----------
    # Un calcul qui n'a jamais demarre laisse quand meme
    # « Results/Summary/Compute Messages (text) », ou HEC-RAS dit ce qu'il a
    # refuse. La chaine ne lisait que _compute_pXX.log — qui ne porte souvent
    # que les lignes du serveur de communication, ecartees par le filtre — et
    # concluait « aucun message exploitable » en renvoyant l'utilisateur
    # ouvrir HEC-RAS a la main. La reponse etait dans le fichier qu'elle
    # venait de lire (releve le 31/08/2026 : « Geometry Writer Failed »).
    print("\n--- messages de HEC-RAS dans un HDF partiel ---")
    import h5py as _h5
    _msg_hdf = Path(tempfile.gettempdir()) / "_essai_calage_msg.p01.hdf"
    with _h5.File(_msg_hdf, "w") as _h:
        _h.create_dataset(
            "Results/Summary/Compute Messages (text)",
            data=np.bytes_((
                "Plan: 'sans apport' (ESSAI.p01)\n"
                "Simulation started at: 31Aug2026 12:22:00 PM\n"
                "Writing Geometry...\n"
                "Geometry Writer Failed\n"
                "Error Processing Geometry\n"
                "Computation Task\tTime\n").encode("utf-8")))
    _lu = _messages_hecras(_msg_hdf)
    _verifier("la cause est extraite du HDF, pas du journal texte",
              "Geometry Writer Failed" in _lu
              and "Error Processing Geometry" in _lu, _lu[:110])
    _verifier("l'en-tete de plan et les temps ne noient pas la cause",
              "Simulation started" not in _lu and "Computation Task" not in _lu)
    _msg_hdf.unlink(missing_ok=True)

    _verifier("verifier_intervalle_apports honore le meme filtre",
              "APPORT_B" in _sans_filtre and "APPORT_B" not in _avec_filtre,
              f"sans filtre {sorted(_sans_filtre)}, avec {sorted(_avec_filtre)}")

    # --- PROLONGEMENT DES APPORTS PILOTES -------------------------------
    # Un modele livre porte souvent des apports plus courts que la fenetre de
    # simulation. HEC-RAS refuse alors de calculer, et l'utilisateur devait
    # rallonger a la main des series que le calage REECRIT des le premier
    # essai. Releve le 31/08/2026 : six apports sur douze, et le message
    # l'envoyait corriger la feuille Cibles — sans aucun effet sur le modele.
    _court = Path(tempfile.gettempdir()) / "_essai_calage_court.u01"
    _court.write_text(
        "Flow Title=Essai\n"
        + ligne_localisation("BREF", "Perimeter 1") + "\n"
        "Interval=1HOUR\n"
        "Flow Hydrograph= 4 \n"
        "    1.00    5.00    3.00    1.00\n"
        "Flow Hydrograph Slope= 0.01 \n", encoding="utf-8")
    _avant = cartographier_hydrogrammes(_court)["BREF"]
    _v_avant = lire_hydrogramme_unsteady(_court, _avant["debut"],
                                            _avant["fin"])
    imposer_intervalle_apport(_court, "BREF", intervalle="1HOUR",
                              duree_min_h=10.0)
    _apres = cartographier_hydrogrammes(_court)["BREF"]
    _v_apres = lire_hydrogramme_unsteady(_court, _apres["debut"],
                                            _apres["fin"])
    _verifier("un apport trop court est prolonge jusqu'a la fenetre",
              abs((len(_v_apres) - 1) * _apres["intervalle_h"] - 10.0) < 1e-9,
              f"{(len(_v_avant) - 1) * _avant['intervalle_h']:.0f} h -> "
              f"{(len(_v_apres) - 1) * _apres['intervalle_h']:.0f} h")
    _verifier("la serie d'origine est intacte, et la queue vaut ZERO",
              list(_v_apres[:4]) == [1.0, 5.0, 3.0, 1.0]
              and set(_v_apres[4:]) == {0.0},
              f"{list(_v_apres)}")
    _verifier("sans duree_min_h, rien n'est prolonge",
              imposer_intervalle_apport(_court, "BREF",
                                        intervalle="1HOUR") is None)
    _court.unlink(missing_ok=True)
    _piege.unlink(missing_ok=True)

    # --- fenetre de simulation du plan ------------------------------------
    #
    # Une fenetre mal ecrite n'est pas refusee par HEC-RAS : elle est lue
    # autrement, et le calcul tourne sur une periode qui n'est pas celle des
    # hydrogrammes. Rien dans les resultats ne le signale — d'ou une validation
    # stricte, eprouvee ici sur les erreurs de saisie realistes.
    print("\n--- fenetre de simulation ---")
    _verifier("un instant bien forme est accepte",
              instant_hecras("13oct2014,00:00") == "13OCT2014,00:00")
    _verifier("un mois francais est refuse",
              _leve(ValueError, instant_hecras, "13FEV2014,00:00"))
    _verifier("une date au format francais est refusee",
              _leve(ValueError, instant_hecras, "13/10/2014 00:00"))
    _verifier("une heure invalide est refusee",
              _leve(ValueError, instant_hecras, "13OCT2014,25:00"))
    _verifier("un jour invalide est refuse",
              _leve(ValueError, instant_hecras, "32OCT2014,00:00"))
    _verifier("minuit et 23:59 restent acceptes",
              instant_hecras("01JAN2020,00:00") == "01JAN2020,00:00"
              and instant_hecras("31DEC2020,23:59") == "31DEC2020,23:59")
    # Les deux formes coexistent dans un projet reel :
    # n'en accepter qu'une rejetterait un plan valide.
    _verifier("la forme sans deux-points est acceptee et normalisee",
              instant_hecras("13OCT2014,0000") == "13OCT2014,00:00"
              and instant_hecras("13OCT2014,1200") == "13OCT2014,12:00")
    _verifier("une heure invalide reste refusee sans deux-points",
              _leve(ValueError, instant_hecras, "13OCT2014,2500"))
    # 24:00 = MINUIT EN FIN DE JOURNEE, convention HEC. C'est ainsi qu'un plan
    # ecrit la fin d'une simulation d'une journee pleine, et le refuser
    # bloquait le calage sur un plan valide (releve le 31/08/2026, second
    # poste). La bascule sur le lendemain doit tenir sur les fins de mois,
    # les annees bissextiles et les fins d'annee.
    _verifier("24:00 bascule sur minuit du lendemain",
              instant_hecras("01Jan2000,2400") == "02JAN2000,00:00"
              and instant_hecras("01JAN2000,24:00") == "02JAN2000,00:00")
    _verifier("la bascule tient sur une fin de mois et une fin d'annee",
              instant_hecras("31JAN2000,2400") == "01FEB2000,00:00"
              and instant_hecras("31DEC2000,2400") == "01JAN2001,00:00")
    _verifier("la bascule connait les annees bissextiles",
              instant_hecras("28FEB2000,2400") == "29FEB2000,00:00"
              and instant_hecras("28FEB2001,2400") == "01MAR2001,00:00")
    _verifier("24:30 est refuse : minuit est un instant, pas une heure",
              _leve(ValueError, instant_hecras, "01JAN2000,24:30"))

    # _en_minutes SERT A MESURER UNE DUREE, pas seulement a ordonner. Il
    # comptait 31 jours par mois : 28 fevrier -> 1er mars ressortait a 96 h.
    # La duree ainsi calculee est celle de la fenetre de simulation, a
    # laquelle conditions_trop_courtes() confronte chaque condition limite —
    # un modele valide enjambant une fin de mois courte voyait donc TOUTES
    # ses conditions declarees trop courtes.
    def _duree_h(a, b):
        return (_en_minutes(instant_hecras(b))
                - _en_minutes(instant_hecras(a))) / 60.0

    _verifier("une duree d'un jour vaut 24 h, quel que soit le mois",
              all(abs(_duree_h(a, b) - 24.0) < 1e-9 for a, b in (
                  ("01JAN2000,00:00", "02JAN2000,00:00"),
                  ("31JAN2000,00:00", "01FEB2000,00:00"),
                  ("28FEB2001,00:00", "01MAR2001,00:00"),
                  ("29FEB2000,00:00", "01MAR2000,00:00"),
                  ("30APR2000,00:00", "01MAY2000,00:00"),
                  ("31DEC2000,00:00", "01JAN2001,00:00"))))
    _verifier("une journee pleine ecrite « 2400 » vaut bien 24 h",
              abs(_duree_h("01JAN2000,00:00", "01JAN2000,2400") - 24.0) < 1e-9)
    _verifier("l'ordre chronologique est preserve",
              [_en_minutes(instant_hecras(x)) for x in (
                  "01JAN2000,00:00", "01JAN2000,00:01", "02JAN2000,00:00",
                  "01FEB2000,00:00", "01JAN2001,00:00")]
              == sorted(_en_minutes(instant_hecras(x)) for x in (
                  "01JAN2000,00:00", "01JAN2000,00:01", "02JAN2000,00:00",
                  "01FEB2000,00:00", "01JAN2001,00:00")))
    _verifier("un intervalle bien forme est accepte",
              intervalle_hecras("0.2sec") == "0.2SEC")
    _verifier("un intervalle sans unite est refuse",
              _leve(ValueError, intervalle_hecras, "10"))
    _verifier("une fenetre inversee est refusee",
              _leve(ValueError, valider_fenetre_simulation,
                    {"debut": "14OCT2014,00:00", "fin": "13OCT2014,00:00"}))
    _verifier("une fenetre a moitie fournie est refusee",
              _leve(ValueError, valider_fenetre_simulation,
                    {"debut": "13OCT2014,00:00"}))
    _verifier("seules les cles fournies deviennent des lignes de plan",
              valider_fenetre_simulation({"intervalle_calcul": "2SEC"})
              == {"Computation Interval": "2SEC"})

    # Lecture / ecriture sur un plan de la meme forme que ceux du projet.
    _plan = Path(tempfile.gettempdir()) / "_essai_calage_plan.p01"
    _plan.write_text(
        "Plan Title=Essai\n"
        "Simulation Date=13OCT2014,00:00,14OCT2014,04:00\n"
        "Geom File=g01\n"
        "Flow File=u01\n"
        "Computation Interval=1SEC\n"
        "Output Interval=1MIN\n"
        "Instantaneous Interval=1MIN\n"
        "Mapping Interval=1MIN\n",
        encoding="utf-8")
    _lu = fenetre_simulation_du_plan(_plan)
    _verifier("la fenetre se relit depuis un plan",
              _lu["debut"] == "13OCT2014,00:00"
              and _lu["fin"] == "14OCT2014,04:00"
              and _lu["intervalle_calcul"] == "1SEC")

    class _PiloteMuet(PiloteHecRas):
        """Juste de quoi exercer l'ecriture, sans HEC-RAS ni ras-commander."""
        def __init__(self, dossier, **kw):
            self.dossier = Path(dossier)
            self.nom_projet = "_essai_calage_plan"
            self.fenetre_simulation = kw.get("fenetre_simulation")
            if self.fenetre_simulation:
                valider_fenetre_simulation(self.fenetre_simulation)

    _PiloteMuet(_plan.parent, fenetre_simulation={
        "debut": "01JAN2022,06:00", "fin": "03JAN2022,18:30",
        "intervalle_calcul": "5SEC"})._ecrire_fenetre_simulation("01")
    _relu = fenetre_simulation_du_plan(_plan)
    _verifier("la fenetre imposee est bien ecrite dans le plan",
              _relu["debut"] == "01JAN2022,06:00"
              and _relu["fin"] == "03JAN2022,18:30"
              and _relu["intervalle_calcul"] == "5SEC")
    _verifier("ce qui n'est pas precise reste celui du plan de reference",
              _relu["intervalle_sortie"] == "1MIN"
              and _relu["intervalle_mapping"] == "1MIN")
    _verifier("les autres lignes du plan sont intactes",
              "Geom File=g01" in _plan.read_text(encoding="utf-8")
              and "Flow File=u01" in _plan.read_text(encoding="utf-8"))

    _plan.write_text("Plan Title=Tronque\nGeom File=g01\n", encoding="utf-8")
    _verifier("un plan sans les lignes attendues leve une erreur",
              _leve(ValueError,
                    _PiloteMuet(_plan.parent, fenetre_simulation={
                        "debut": "01JAN2022,06:00",
                        "fin": "03JAN2022,18:30"})._ecrire_fenetre_simulation,
                    "01"))
    _plan.unlink(missing_ok=True)

    # -----------------------------------------------------------------------
    # ETAPES CONSERVEES ET MENAGE DE FIN DE CALAGE
    #
    # Du code qui EFFACE des fichiers dans le projet d'un client n'avait aucun
    # test. On fabrique donc un projet complet dans l'etat exact d'une fin de
    # calage — etape du jour, etape homonyme d'une relance precedente, plans de
    # l'utilisateur dont un piegeux appele « Q100 copy » — et on verifie
    # fichier par fichier ce qui part et ce qui reste.
    # -----------------------------------------------------------------------
    print("\n--- Etapes conservees et menage de fin de calage ---")
    _bac = Path(tempfile.mkdtemp(prefix="_essai_menage_"))
    _NOM = "ESSAI"

    def _batir_projet():
        for chemin in _bac.glob("*"):
            if chemin.is_file():
                chemin.unlink()
        plans = {"01": ("Q100", "g01", "u01"),          # plan de reference
                 "02": ("Q100 copy", "g01", "u02"),     # PIEGE : plan a la main
                 "10": ("Apport_A1", "g10", "u10"),     # etape d'une relance
                 "11": ("Apport_A1", "g11", "u11")}     # etape du jour
        for numero, titre in {"01": "Q100", "02": "Q100 copy",
                              "10": "Apport_A1", "11": "Apport_A1"}.items():
            (_bac / f"{_NOM}.u{numero}").write_text(f"Flow Title={titre}\n",
                                                    encoding="utf-8")
        for numero, titre in {"01": "Etat actuel", "10": "Geometrie_calage",
                              "11": "Geometrie_calage"}.items():
            (_bac / f"{_NOM}.g{numero}").write_text(f"Geom Title={titre}\n",
                                                    encoding="utf-8")
        for numero, (titre, geom, flot) in plans.items():
            (_bac / f"{_NOM}.p{numero}").write_text(
                f"Plan Title={titre}\nShort Identifier={titre}\n"
                f"Geom File={geom}\nFlow File={flot}\n", encoding="utf-8")
            for gabarit in (".p{n}.hdf", ".b{n}", ".bco{n}", ".x{n}",
                            ".ic.o{n}"):
                (_bac / f"{_NOM}{gabarit.format(n=numero)}").write_bytes(b"x")
            (_bac / f"_compute_p{numero}.log").write_bytes(b"x")
        lignes = ["Proj Title=Essai\n"]
        lignes += [f"Geom File=g{n}\n" for n in ("01", "10", "11")]
        lignes += [f"Unsteady File=u{n}\n" for n in ("01", "02", "10", "11")]
        lignes += [f"Plan File=p{n}\n" for n in plans]
        (_bac / f"{_NOM}.prj").write_text("".join(lignes), encoding="utf-8")
        # Reliquats : sauvegardes horodatees et shapefiles du plugin.
        (_bac / f"{_NOM}.g01.sauvegarde_20260727_101500").write_bytes(b"x")
        (_bac / f"{_NOM}.u01.sauvegarde_20260727_101500").write_bytes(b"x")
        shp = _bac / "_calage"
        shp.mkdir(exist_ok=True)
        (shp / "sections.shp").write_bytes(b"x")

    def _presents():
        return {p.name for p in _bac.glob("*") if p.is_file()}

    def _objets():
        """Plans, unsteady et geometries encore presents."""
        return {n for n in _presents() if re.search(r"\.[pug][0-9][0-9]$", n)}

    def _pilote_menage():
        p = PiloteHecRas(_bac, _NOM, plan_reference="01",
                         nom_clone_geometrie="Geometrie_calage")
        p.plan_travail = "11"
        return p

    # 1. UN PLAN D'ETAPE HOMONYME D'UNE RELANCE PRECEDENTE EST REMPLACE, et lui
    #    seul. C'est la seule suppression de plan que la chaine s'autorise
    #    desormais : tout le reste est conserve pour servir de trace.
    _batir_projet()
    _efface = _pilote_menage()._remplacer_homonymes("Apport_A1")
    _reste = _presents()
    _prj = (_bac / f"{_NOM}.prj").read_text(encoding="utf-8")

    _verifier("etapes : le plan de l'etape du jour est conserve",
              f"{_NOM}.p11" in _reste)
    _verifier("etapes : le plan de reference est intact",
              f"{_NOM}.p01" in _reste)
    # LE POINT LE PLUS IMPORTANT : une version anterieure supprimait tout plan
    # dont le titre finit par « copy » — soit exactement ce que HEC-RAS ecrit
    # sur un « Save Plan As ». Un plan fait a la main etait detruit.
    _verifier("etapes : un plan de l'utilisateur nomme « ... copy » SURVIT",
              f"{_NOM}.p02" in _reste and f"{_NOM}.u02" in _reste)
    _verifier("etapes : l'homonyme de la relance precedente est parti",
              f"{_NOM}.p10" not in _reste)
    _verifier("etapes : son unsteady orphelin est parti",
              f"{_NOM}.u10" not in _reste)
    _verifier("etapes : sa geometrie orpheline est partie",
              f"{_NOM}.g10" not in _reste)
    _verifier("etapes : la geometrie de l'etape du jour est conservee",
              f"{_NOM}.g11" in _reste)
    _verifier("etapes : aucun derive d'un plan supprime ne subsiste",
              not any(n in _reste for n in
                      (f"{_NOM}.p10.hdf", f"{_NOM}.b10", f"{_NOM}.bco10",
                       f"{_NOM}.x10", f"{_NOM}.ic.o10", "_compute_p10.log")))
    _verifier("etapes : le .prj suit les suppressions",
              "Plan File=p10" not in _prj and "Geom File=g10" not in _prj
              and "Unsteady File=u10" not in _prj)
    _verifier("etapes : le .prj declare toujours ce qui reste",
              all(f"Plan File=p{n}" in _prj for n in ("01", "02", "11"))
              and "Geom File=g11" in _prj)
    _verifier("etapes : le compte rendu enumere ce qui est parti",
              set(_efface) == {"p10", "u10", "g10"}, str(_efface))

    # 2. UN PLAN D'UNE AUTRE ETAPE N'EST JAMAIS TOUCHE. C'est ce qui permet de
    #    reprendre un calage a l'apport A2 sans perdre l'etape A1.
    _batir_projet()
    _pilote_menage()._remplacer_homonymes("Apport_A2")
    _verifier("etapes : une etape d'un autre nom est intacte",
              {f"{_NOM}.p10", f"{_NOM}.u10", f"{_NOM}.g10"} <= _presents())

    # 3. LE MENAGE DE FIN NE TOUCHE PLUS AUX PLANS. Il ne retire que ce que
    #    personne ne reclame : sauvegardes de preparation et shapefiles.
    _batir_projet()
    _temoin = _objets()
    _bilan = _pilote_menage().nettoyer_reliquats()
    _verifier("menage : les sauvegardes horodatees sont retirees",
              not any("sauvegarde_" in n for n in _presents()))
    _verifier("menage : le dossier _calage/ est retire",
              not (_bac / "_calage").exists())
    _verifier("menage : AUCUN plan, unsteady ou geometrie n'est supprime",
              _objets() == _temoin, f"{sorted(_temoin - _objets())} manquant(s)")
    _verifier("menage : les reliquats sont enumeres dans le compte rendu",
              len(_bilan["reliquats"]) == 3, str(_bilan["reliquats"]))
    _verifier("menage : simuler=True ne retire rien",
              _pilote_menage().nettoyer_reliquats(simuler=True)["conserve"]
              == "p11")

    # 4. RETROUVER UN PLAN PAR SON TITRE : c'est ce sur quoi repose la reprise
    #    a un apport donne.
    _batir_projet()
    _verifier("plan_par_titre : trouve le plan de reference",
              plan_par_titre(_bac, _NOM, "Q100") == "01")
    _verifier("plan_par_titre : rend None sur un titre inconnu",
              plan_par_titre(_bac, _NOM, "Apport_A9") is None)
    _verifier("plan_par_titre : sur deux homonymes, rend le plus recent",
              plan_par_titre(_bac, _NOM, "Apport_A1") in ("10", "11"))

    # 5. Titrage d'un unsteady : jalonner() s'en sert pour nommer l'etape.
    _pilote_menage()._renommer_unsteady("11", "Apport_A2")
    _verifier("titrage : le Flow Title est reecrit",
              "Flow Title=Apport_A2"
              in (_bac / f"{_NOM}.u11").read_text(encoding="utf-8"))

    # 6. LE PLAN FINAL EST UN RETITRAGE, PAS UN CLONE. Le plan de la derniere
    #    etape porte deja tous les apports cales ET ses resultats ; un clone
    #    n'emporterait pas son .hdf et serait muet dans RAS Mapper.
    _batir_projet()
    _p = _pilote_menage()
    _p.fichier_unsteady = _bac / f"{_NOM}.u11"
    _p.etapes = ["Q100-Apport_A1"]
    _rendu = _p.conclure("Q100_avec_apports")
    _p11 = (_bac / f"{_NOM}.p11").read_text(encoding="utf-8")
    _verifier("plan final : le plan de la derniere etape porte le titre final",
              "Plan Title=Q100_avec_apports" in _p11, _rendu)
    _verifier("plan final : le Short Identifier suit",
              "Short Identifier=Q100_avec_apports" in _p11)
    _verifier("plan final : l'unsteady du plan courant suit",
              "Flow Title=Q100_avec_apports"
              in (_bac / f"{_NOM}.u11").read_text(encoding="utf-8"))
    _verifier("plan final : ses resultats sont conserves (aucun clone)",
              (_bac / f"{_NOM}.p11.hdf").is_file())
    _verifier("plan final : aucun plan cree ni supprime — les quatre sont la",
              len(list(_bac.glob(f"{_NOM}.p[0-9][0-9]"))) == 4,
              str(sorted(p.name
                         for p in _bac.glob(f"{_NOM}.p[0-9][0-9]"))))
    _verifier("plan final : l'etape courante est rebaptisee, pas ajoutee",
              _p.etapes == ["Q100_avec_apports"], str(_p.etapes))

    # RAS MAPPER NOMME LA COUCHE D'APRES LE HDF (28/09/2026) : sans ce
    # retitrage, le plan final s'affichait sous le nom de la derniere etape.
    import h5py as _h5
    (_bac / f"{_NOM}.p11.hdf").unlink()
    with _h5.File(_bac / f"{_NOM}.p11.hdf", "w") as _h:
        _info = _h.create_group("Plan Data/Plan Information").attrs
        for _cle in ("Plan Name", "Plan ShortID", "Plan Title", "Flow Title"):
            _info[_cle] = np.bytes_(b"Q100-Apport_A1")
    _rendu = _p.conclure("Q100_avec_apports")
    with _h5.File(_bac / f"{_NOM}.p11.hdf", "r") as _h:
        _lu = dict(_h["Plan Data/Plan Information"].attrs)
    _verifier("plan final : le .hdf porte le titre final (RAS Mapper le lit)",
              all(_lu[c] == b"Q100_avec_apports" for c in
                  ("Plan Name", "Plan ShortID", "Plan Title", "Flow Title")),
              f"{_rendu} | {_lu}")

    # --- LE PLAN FINAL EST DECLARE A RAS MAPPER (21/09/2026) --------------
    # Constate sur deux modeles reels : la chaine laissait des plans avec
    # des centaines de Mo de resultats que RAS Mapper ne montrait pas. Son
    # arbre « Results » liste ce que le .rasmap declare ; ras-commander ne
    # l'ecrit jamais. Sur l'un des deux, treize plans calcules, zero declare.
    from xml.etree import ElementTree as _ET

    _rasmap = _bac / f"{_NOM}.rasmap"
    _rasmap.write_text(
        '<RASMapper>\n  <Results Checked="True">\n'
        '    <Layer Name="Q100" Type="RASResults" Filename=".\\'
        + _NOM + '.p01.hdf" />\n  </Results>\n</RASMapper>\n',
        encoding="utf-8")
    _avant_rasmap = _rasmap.read_text(encoding="utf-8")
    _dit = _p._declarer_resultats_rasmap("11", "Q100_avec_apports")
    _lu = _rasmap.read_text(encoding="utf-8")
    _verifier("rasmap : le plan final y est declare", "declare" in _dit, _dit)
    _verifier("rasmap : le fichier reste du XML valide",
              _ET.fromstring(_lu) is not None)
    _noms = [c.get("Name") for c in _ET.fromstring(_lu).find("Results")
             if c.get("Type") == "RASResults"]
    _verifier("rasmap : la couche s'ajoute sans retirer les existantes",
              _noms == ["Q100", "Q100_avec_apports"], str(_noms))
    _verifier("rasmap : elle designe le .hdf du plan final",
              f'Filename=".\\{_NOM}.p11.hdf"' in _lu)
    # IDEMPOTENT, ET C'EST LE FICHIER QUI IDENTIFIE : relancer un calage sur
    # le meme scenario ne doit pas empiler les couches, et un retitrage doit
    # renommer celle qui existe — son nom vient justement de changer.
    _p._declarer_resultats_rasmap("11", "Q100_avec_apports")
    _p._declarer_resultats_rasmap("11", "Q100_final")
    _noms = [c.get("Name") for c in
             _ET.fromstring(_rasmap.read_text(encoding="utf-8")).find("Results")
             if c.get("Type") == "RASResults"]
    _verifier("rasmap : un second passage renomme au lieu d'empiler",
              _noms == ["Q100", "Q100_final"], str(_noms))
    # UN TITRE A CARACTERE XML NE CASSE PAS LE FICHIER DE L'UTILISATEUR.
    _p._declarer_resultats_rasmap("11", 'Q100 & "bis"')
    _verifier("rasmap : un titre a esperluette est echappe",
              _ET.fromstring(_rasmap.read_text(encoding="utf-8")) is not None
              and "&amp;" in _rasmap.read_text(encoding="utf-8"))
    # SANS BLOC <Results>, ON NE DEVINE PAS : on le dit et on ne touche rien.
    _rasmap.write_text("<RASMapper>\n</RASMapper>\n", encoding="utf-8")
    _dit = _p._declarer_resultats_rasmap("11", "Q100_avec_apports")
    _verifier("rasmap : sans bloc <Results>, on ne touche a rien et on le dit",
              "Results" in _dit
              and _rasmap.read_text(encoding="utf-8")
              == "<RASMapper>\n</RASMapper>\n", _dit)
    # ET SANS .rasmap DU TOUT, un calage abouti n'echoue pas pour autant.
    _rasmap.unlink()
    _dit = _p._declarer_resultats_rasmap("11", "Q100_avec_apports")
    _verifier("rasmap : absent, le calage ne rate pas — il le dit",
              "aucun" in _dit.lower(), _dit)
    _verifier("plan final : conclure() avant preparer() est refuse",
              _leve(RuntimeError,
                    PiloteHecRas(_bac, _NOM, plan_reference="01").conclure,
                    "Q100_avec_apports"))

    # 7. LA TRONCATURE SILENCIEUSE DU SHORT IDENTIFIER EST PARTIE. C'est elle
    #    qui fabriquait le doublon : un plan de reprise du depot porte encore
    #    « sans apport XXX et ava », rogne d'un « l » depuis toujours.
    _batir_projet()
    _p = _pilote_menage()
    _p.fichier_unsteady = _bac / f"{_NOM}.u11"
    _long = "Riviere1-Q100_avec_apports"                # 26 caracteres
    _p.conclure(_long)
    _verifier("short id : un titre de 26 caracteres est ecrit ENTIER",
              f"Short Identifier={_long}\n"
              in (_bac / f"{_NOM}.p11").read_text(encoding="utf-8"))
    # RETROCOMPATIBILITE, OCTET POUR OCTET : le bourrage a 24 reste, et rend la
    # ligne exacte des 34 plans deja ecrits par la chaine dans 01-cas_test.
    _p.conclure("sans_apport")
    _verifier("short id : un titre court reste complete a 24, octet pour octet",
              "Short Identifier=" + "sans_apport".ljust(24) + "\n"
              in (_bac / f"{_NOM}.p11").read_text(encoding="utf-8"))

    # 8. UN ETAT FINAL HOMONYME D'UN CALAGE PRECEDENT EST REMPLACE, comme une
    #    etape : deux « Q100_avec_apports » ne diraient plus lequel fait foi.
    _batir_projet()
    (_bac / f"{_NOM}.p10").write_text(
        "Plan Title=Q100_avec_apports\n"
        "Short Identifier=Q100_avec_apports\n"
        "Geom File=g10\nFlow File=u10\n", encoding="utf-8")
    _p = _pilote_menage()
    _p.fichier_unsteady = _bac / f"{_NOM}.u11"
    _rendu = _p.conclure("Q100_avec_apports")
    _verifier("plan final : l'etat final d'un calage precedent est remplace",
              not (_bac / f"{_NOM}.p10").exists()
              and (_bac / f"{_NOM}.p11").exists(), _rendu)

    # 9. ELAGAGE DES ETAPES, SUR DEMANDE. La chaine les conserve ; cette
    #    methode-ci les retire APRES COUP, et seulement si le calage a
    #    conclu. C'est la seule suppression de plan que l'utilisateur puisse
    #    demander, et elle ne doit emporter que ce qui lui appartient.
    def _titrer(numero, titre, geom, flot):
        (_bac / f"{_NOM}.p{numero}").write_text(
            f"Plan Title={titre}\nShort Identifier={titre}\n"
            f"Geom File={geom}\nFlow File={flot}\n", encoding="utf-8")

    _batir_projet()
    _titrer("10", "Q100_sans_apport", "g10", "u10")
    _titrer("02", "Q100_Apport_A1", "g10", "u02")
    _titrer("11", "Q100_avec_apports", "g11", "u11")
    _p = _pilote_menage()
    _p.plan_travail = None          # le calage est fini : plus de plan courant

    _avant = _objets()
    _simule = _p.elaguer_etapes("Q100", simuler=True)
    _verifier("elagage : la simulation annonce les deux etapes",
              _simule["etapes"] == ["02", "10"], str(_simule))
    _verifier("elagage : la simulation ne retire RIEN",
              _objets() == _avant,
              f"{sorted(_avant - _objets())} manquant(s)")

    _fait = _p.elaguer_etapes("Q100", simuler=False)
    _verifier("elagage : les plans d'etape sont partis",
              not (_bac / f"{_NOM}.p10").exists()
              and not (_bac / f"{_NOM}.p02").exists(), str(_fait))
    _verifier("elagage : le plan final est intact, AVEC ses resultats",
              (_bac / f"{_NOM}.p11").exists()
              and (_bac / f"{_NOM}.p11.hdf").exists())
    _verifier("elagage : le plan de reference n'est pas touche",
              (_bac / f"{_NOM}.p01").exists())
    _verifier("elagage : les derives des plans retires partent avec eux",
              not (_bac / f"{_NOM}.p10.hdf").exists()
              and not (_bac / "_compute_p10.log").exists())
    _verifier("elagage : l'unsteady que seul un plan retire designait part",
              not (_bac / f"{_NOM}.u02").exists(), str(_fait["supprimes"]))
    _verifier("elagage : le .prj ne declare plus les plans retires",
              "Plan File=p10" not in (_bac / f"{_NOM}.prj").read_text(
                  encoding="utf-8"))

    # LE GARDE-FOU QUI COMPTE : sans plan final, les etapes sont TOUT ce qui
    # reste du calage. Les retirer l'effacerait.
    _batir_projet()
    _titrer("10", "Q100_sans_apport", "g10", "u10")
    _titrer("11", "Q100_Apport_A1", "g11", "u11")
    _p = _pilote_menage()
    _p.plan_travail = None
    _avant = _objets()
    _refus = _p.elaguer_etapes("Q100", simuler=False)
    _verifier("elagage : sans plan final, on REFUSE et l'on dit pourquoi",
              "refus" in _refus and "n'a pas conclu" in _refus["refus"],
              str(_refus)[:90])
    _verifier("elagage : le refus ne retire rien",
              _objets() == _avant,
              f"{sorted(_avant - _objets())} manquant(s)")

    # UN PLAN QUI N'EST PAS DE NOUS RESTE, quel que soit son titre.
    _batir_projet()
    _titrer("10", "Q100_sans_apport", "g10", "u10")
    _titrer("11", "Q100_avec_apports", "g11", "u11")
    _p = _pilote_menage()
    _p.plan_travail = None
    _p.elaguer_etapes("Q100", simuler=False)
    _verifier("elagage : le plan « Q100 copy » de l'utilisateur reste",
              (_bac / f"{_NOM}.p02").exists())
    # ET LE PREFIXE ISOLE LES SERIES : elaguer le Q10 ne touche pas au Q100.
    _batir_projet()
    _titrer("10", "Q100_sans_apport", "g10", "u10")
    _titrer("11", "Q10_avec_apports", "g11", "u11")
    _p = _pilote_menage()
    _p.plan_travail = None
    _p.elaguer_etapes("Q10", simuler=False)
    _verifier("elagage : le prefixe isole les series — le Q100 est intact",
              (_bac / f"{_NOM}.p10").exists())

    _verifier("detection de HEC-RAS ouvert : repond sans lever",
              hecras_ouvert() in (True, False, None), str(hecras_ouvert()))
    shutil.rmtree(_bac, ignore_errors=True)

    # -----------------------------------------------------------------------
    # FERMETURE DES HEC-RAS ORPHELINS
    #
    # C'est la REGLE DE CHOIX qui est eprouvee, pas l'appel systeme : fermer
    # le mauvais processus ferait perdre a l'utilisateur une session ouverte
    # sur un autre projet. Le cas qui compte est celui du milieu — un
    # processus deja la avant le calcul ne doit JAMAIS etre retenu, meme s'il
    # est encore la apres.
    # -----------------------------------------------------------------------
    print("\n--- Fermeture des HEC-RAS orphelins ---")
    _avant = {100: "Ras.exe", 101: "RasUnsteady.exe"}
    _apres = {100: "Ras.exe", 102: "Ras.exe", 103: "RasUnsteady.exe"}
    _orph = orphelins_du_calcul(_avant, _apres)
    _verifier("seuls les processus APPARUS pendant le calcul sont retenus",
              set(_orph) == {102, 103}, str(sorted(_orph)))
    _verifier("une session ouverte AVANT le calcul est epargnee",
              100 not in _orph)
    _verifier("un processus disparu de lui-meme n'est pas poursuivi",
              101 not in _orph)
    _verifier("aucun orphelin quand rien n'a bouge",
              not orphelins_du_calcul(_avant, dict(_avant)))
    _verifier("un releve impossible ne ferme rien",
              not orphelins_du_calcul(None, _apres)
              and not orphelins_du_calcul(_avant, None))
    _verifier("le releve des processus repond sans lever",
              pids_hecras() is None or isinstance(pids_hecras(), dict),
              str(pids_hecras()))
    _verifier("fermer_processus ne leve pas sur un PID inexistant",
              fermer_processus({999999: "Fantome.exe"}) == [])

    # EN REPRISE, LA BORNE HAUTE RESTE CELLE DU PLAN DE REFERENCE. Le plan
    # d'etape dont une reprise repart a pu etre raccourci par le calage
    # precedent ; lire la borne SUR LUI la bornait a son tour, et l'apport
    # repris ne pouvait plus rallonger jusqu'a son propre evenement. Mesure
    # sur un cas reel (14/09/2026) : 36 h au plan de reference, 32 h 06 au
    # plan d'etape. limiter_duree() ne fait que RACCOURCIR : une borne trop
    # basse est donc un plafond, jamais un plancher.
    _bac_f = Path(tempfile.mkdtemp(prefix="calage_borne_"))
    try:
        (_bac_f / "Essai.p01").write_text(
            "Plan Title=reference\n"
            "Simulation Date=01JAN2000,00:00,02JAN2000,12:00\n",
            encoding="utf-8")                                     # 36 h
        (_bac_f / "Essai.p20").write_text(
            "Plan Title=etape\n"
            "Simulation Date=01JAN2000,00:00,02JAN2000,08:06\n",
            encoding="utf-8")                                     # 32 h 06

        # Le plan de travail est pose a la main — ce que preparer() aurait
        # clone — : rien a cloner ni a calculer, seule la borne est eprouvee.
        _ordinaire = PiloteHecRas(_bac_f, "Essai", "p20")
        _ordinaire.plan_travail = "20"
        _repris = PiloteHecRas(_bac_f, "Essai", "p20",
                               plan_fenetre_pleine="p01")
        _repris.plan_travail = "20"
        _verifier("calage ordinaire : la borne est celle du plan de travail",
                  abs(_ordinaire._duree_borne_h() - 32.1) < 1e-9,
                  f"{_ordinaire._duree_borne_h():.2f} h")
        _verifier("reprise : la borne reste les 36 h du plan de reference",
                  abs(_repris._duree_borne_h() - 36.0) < 1e-9,
                  f"{_repris._duree_borne_h():.2f} h au lieu de "
                  f"{_ordinaire._duree_borne_h():.2f} h")
        _verifier("le pilote retient le plan de la borne, normalise",
                  _repris.plan_fenetre_pleine == "01")
        _verifier("sans reprise, aucun plan de borne n'est retenu",
                  _ordinaire.plan_fenetre_pleine is None)
        _ordinaire.plan_travail = "99"                    # fichier absent
        _verifier("un plan illisible ne borne rien, et ne leve pas",
                  _ordinaire._duree_borne_h() is None)
    finally:
        shutil.rmtree(_bac_f, ignore_errors=True)

    # LA LIGNE QUI EXPLIQUE N'EST PAS LA DERNIERE. Compte rendu reel d'un
    # calcul avorte (14/09/2026) : l'erreur est suivie du tableau des temps,
    # plus de lignes que le filtre n'en garde. Coupe a son en-tete, le tableau
    # ne pousse plus l'erreur dehors.
    _compte_rendu = [
        "Plan: Q100_sans_apport",
        "Geometry Writer Failed",
        "Error Processing Geometry",
        "Computation Task\tTime(hh:mm:ss)",
        "Completing Geometry, Flow and Plan\t      25",
        "Unsteady Flow Computations\t<1",
        "Complete Process\t25",
        "Computation Speed\tSimulation/Runtime",
        "Unsteady Flow Computations\t617968x",
    ]
    _retenues = _sans_tableau_des_temps(_compte_rendu)[-4:]
    _verifier("les messages HEC-RAS gardent l'erreur, pas le tableau des temps",
              "Error Processing Geometry" in _retenues
              and "Geometry Writer Failed" in _retenues
              and not any("617968x" in l or "Complete Process" in l
                          for l in _retenues),
              " | ".join(_retenues))
    # SANS TABLEAU, RIEN N'EST COUPE : un compte rendu interrompu avant lui se
    # lit comme avant, par la fin.
    _banal = ["ligne un", "ligne deux", "ligne trois", "ligne quatre",
              "ligne cinq"]
    _verifier("sans tableau des temps, le compte rendu est rendu tel quel",
              _sans_tableau_des_temps(_banal) == _banal,
              str(_sans_tableau_des_temps(_banal)))

    print()
    if _echecs_test:
        print(f"{len(_echecs_test)} ECHEC(S)")
    else:
        print("Tous les controles passent.")
    print("=" * 74 + "\n")

    analyseur = argparse.ArgumentParser(
        description="Diagnostic du raccordement a un projet HEC-RAS. "
                    "Ne lance aucun calcul et ne modifie rien.")
    analyseur.add_argument("--projet", default=None,
                           help="omis : n'execute que l'auto-test ci-dessus")
    analyseur.add_argument("--unsteady", default=None,
                           help="fichier .uXX a examiner ; sinon le premier trouve")
    args = analyseur.parse_args()

    if args.projet is None:
        raise SystemExit(1 if _echecs_test else 0)

    dossier = Path(args.projet)
    print("=" * 74)
    print("RACCORDEMENT A UN PROJET HEC-RAS — lecture seule")
    print("=" * 74)
    print(f"\nProjet : {dossier}")

    fichiers = ([Path(args.unsteady)] if args.unsteady
                else sorted(p for p in dossier.glob("*.u[0-9][0-9]")
                            if p.suffix != ".hdf"))
    if not fichiers:
        raise SystemExit("aucun fichier unsteady trouve")

    for fichier in fichiers[:3]:
        print(f"\n--- {fichier.name} ---")
        carte = cartographier_hydrogrammes(fichier)
        if not carte:
            print("   aucune condition limite a hydrogramme de debit")
            continue
        for nom, info in carte.items():
            valeurs = lire_hydrogramme_unsteady(fichier, info["debut"],
                                                   info["fin"])
            duree = (len(valeurs) - 1) * (info["intervalle_h"] or 0)
            print(f"   {nom:16s} zone={info['zone']:14s} "
                  f"{len(valeurs):5d} valeurs, pas "
                  f"{60 * (info['intervalle_h'] or 0):.0f} min, "
                  f"duree {duree:6.1f} h, pic {valeurs.max():8.2f} m3/s")
    print("\n" + "=" * 74)
