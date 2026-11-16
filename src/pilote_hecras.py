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

import difflib
import math
import re
import subprocess
import threading
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

# Au-dela de cet ecart (en fraction de la pointe) entre une condition limite
# NON CALEE et sa serie re-cadencee, le journal porte « AVERTISSEMENT », que
# l'etape Suivi montre sous sa banniere AU DEBUT DU CALAGE — elle ne lit que
# la fin du journal, et la ligne en sort quand il grossit ; elle reste dans le
# journal. En dessous du seuil, une simple ligne d'information.
# 1 % : sous ce seuil tombent les crues qui montent en plus de
# deux heures environ (mesure du 11/11/2026, 15 -> 6 min). Voir
# PiloteHecRas._dire_ecart_de_recadencage().
SEUIL_ECART_RECADENCAGE = 0.01

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

    UTF-8 STRICT, PUIS cp1252, PUIS latin-1 — DANS CET ORDRE. HEC-RAS ecrit
    en cp1252. latin-1 lit tout octet et ne peut donc pas echouer : place
    avant cp1252, comme il l'etait ici (l'ordre de ras-commander), cp1252
    n'etait jamais atteint, et le tiret long (0x97) ou « œ » (0x9C)
    revenaient en caracteres de controle. Il ne vient qu'en dernier, pour
    le fichier dont on n'a pas reconnu l'encodage : aucun octet n'est perdu.

    Meme politique que calage_apports.noyau._lire_texte_hecras et
    elaguer_projet._lire_texte : ces trois modules ne peuvent PAS partager
    de code (le plugin est livre seul dans son zip, elaguer_projet ne
    depend que de la bibliotheque standard). La duplication est assumee ;
    toute correction ici doit etre reportee aux deux autres.
    """
    chemin = Path(chemin)
    for encodage in ("utf-8", "cp1252"):
        try:
            return chemin.read_text(encoding=encodage)
        except (UnicodeDecodeError, LookupError):
            continue
    return chemin.read_text(encoding="latin-1")


def _lire_lignes(chemin):
    return _lire_texte(chemin).splitlines(keepends=True)


def _encodage(octets):
    """
    L'encodage ou des octets deja ecrits se relisent, donc celui ou l'on
    REECRIT le fichier : la cascade de _lire_texte.

    L'ASCII PUR EST DU cp1252 (regle de la maison, decision du 11/10/2026) :
    c'est un fichier HEC-RAS, que HEC-RAS relit en cp1252. Le premier accent
    qu'on y ecrit — un nom d'apport, un titre d'etape — part donc en cp1252,
    plus en UTF-8 que HEC-RAS afficherait « Ã© ». Ce que ras-commander
    reecrit ensuite en UTF-8 est rendu a cet encodage par _retablir_octets.
    Le .rasmap fait exception (UTF-8) : voir _ecrire_texte.
    """
    if octets.isascii():
        return "cp1252"
    for encodage in ("utf-8", "cp1252"):
        try:
            octets.decode(encodage)
            return encodage
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _ecrire_texte(chemin, texte):
    """
    Reecrit un fichier texte HEC-RAS dans L'ENCODAGE ET AVEC LA FIN DE LIGNE
    QU'IL AVAIT : on y a touche une ligne, on ne le convertit pas.

    TOUTE REECRITURE D'UN FICHIER DU MODELE PASSE PAR ICI. Neuf d'entre elles
    forcaient l'UTF-8 : un .pNN, un .uNN ou le .prj lu juste en cp1252
    ressortait avec ses accents sur deux octets, et HEC-RAS affichait « Ã© »
    (audit du 11/10/2026). Le texte vient de _lire_texte, fins de ligne
    ramenees a « \\n » : on rend celle du fichier, CRLF a defaut.

    REFUSER PLUTOT QUE TRONQUER : un caractere que l'encodage du fichier ne
    sait pas ecrire leve ValueError AVANT toute ecriture.

    LE .rasmap EST EN UTF-8, ASCII compris : RAS Mapper l'ecrit ainsi, et un
    accent ecrit en cp1252 dans une carte la rend invalide (0-HECRAS).
    """
    chemin = Path(chemin)
    ancien = chemin.read_bytes() if chemin.is_file() else b""
    encodage = ("utf-8" if chemin.suffix.lower() == ".rasmap"
                else _encodage(ancien))
    try:
        octets = texte.encode(encodage)
    except UnicodeEncodeError as e:
        raise ValueError(
            f"« {texte[e.start]} » ne s'ecrit pas en {encodage}, l'encodage "
            f"de {chemin.name} : rien n'y est ecrit. Retirer ce caractere du "
            f"nom ou du titre.") from e
    # ponytail: une seule fin de ligne par fichier ; un melange CRLF/LF est
    # ramene a CRLF, comme avant. La garder ligne par ligne demanderait de
    # lire en octets (voir 05-HECRAS_Organizer, core/io/textfile.py).
    fin = b"\n" if b"\n" in ancien and b"\r\n" not in ancien else b"\r\n"
    chemin.write_bytes(octets.replace(b"\n", fin))


def _retablir_octets(chemin, origine):
    """
    Rend a un fichier que ras-commander vient de reecrire l'encodage et les
    octets de « origine » : les siens avant l'appel, ou ceux du fichier dont
    il est le clone.

    ras-commander (0.99.2) relit et reecrit en UTF-8 errors="replace" : a
    chaque clone, essai ou calcul, un accent cp1252 devenait EF BF BD. Mesure
    du 11/10/2026 sur un projet fabrique : titre du projet, region LCMann
    « Forêt », et l'apport « Écluse », que la geometrie clonee et l'unsteady
    de l'etape suivante n'appariaient plus — l'apport sortait du calage.
    BcoMonitor.enable_detailed_logging relit en errors="ignore" : l'accent
    DISPARAIT (« lit mineur à 40 » -> « lit mineur  40 », 08/11/2026).

    UNE LIGNE QU'IL N'A PAS CHANGEE REPREND SES OCTETS, terminateur compris :
    on la reconnait a ce qu'il en a lu, sous l'une ou l'autre forme : sans
    ses U+FFFD, une ligne se confond avec les deux. L'appariement suit
    l'ordre des lignes (difflib) : une vraie ligne vide ne prend pas l'accent
    d'une ligne « é » seule, qui ne se lit plus qu'en ligne vide. Une ligne
    ajoutee ou changee est
    encodee dans l'encodage d'origine, avec la fin de ligne qu'il lui a
    donnee ; un caractere que cet encodage ne sait pas ecrire leve
    ValueError, le fichier restant tel que ras-commander l'a laisse. Un
    fichier d'origine en UTF-8 n'a rien perdu : il n'est pas touche.
    """
    chemin = Path(chemin)
    apres = chemin.read_bytes()
    encodage = _encodage(origine)
    if apres == origine or encodage == "utf-8":
        return

    def lu(ligne):                         # ce qu'en a lu ras-commander
        return ligne.rstrip(b"\r\n").decode("utf-8", "replace")

    def cle(ligne):                        # formes « replace » et « ignore »
        return lu(ligne).replace("�", "")

    anciennes = origine.splitlines(keepends=True)
    nouvelles = apres.splitlines(keepends=True)
    sortie = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, [cle(l) for l in anciennes], [cle(l) for l in nouvelles],
            autojunk=False).get_opcodes():
        if op == "equal":
            sortie += anciennes[i1:i2]
            continue
        for ligne in nouvelles[j1:j2]:
            # ponytail: un U+FFFD dans une ligne CHANGEE vient d'un texte que
            # ras-commander a mal lu puis recopie. Seul cas connu : la ligne
            # « Short Identifier=<ancien>_copy » de clone_plan, que
            # _renommer_plan reecrit aussitot. Il devient « ? » ; retrouver
            # l'octet demanderait d'aligner la ligne sur son originale.
            texte = lu(ligne).replace("�", "?")
            try:
                sortie.append(texte.encode(encodage)
                              + ligne[len(ligne.rstrip(b"\r\n")):])
            except UnicodeEncodeError as e:
                raise ValueError(
                    f"« {texte[e.start]} » ne s'ecrit pas en {encodage}, "
                    f"l'encodage de {chemin.name} : ras-commander l'y a ecrit "
                    f"en UTF-8. Retirer ce caractere du nom ou du titre."
                ) from e
    chemin.write_bytes(b"".join(sortie))


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
    _ecrire_texte(chemin, "".join(lignes))
    return len(valeurs)


def _refuser_zone_ambigue(chemin, carte, nom_zone_2d):
    """
    ValueError si, SANS nom de zone 2D, une condition limite de « carte »
    existe dans PLUSIEURS zones 2D du fichier.

    Decision de l'utilisateur du 11/11/2026 : un refus, pas un avertissement.
    Sans nom de zone, cartographier_hydrogrammes retient le PREMIER bloc
    rencontre et note les autres dans « autres_zones ». Ecrire dans ce
    premier bloc, c'est parier sur l'ordre du fichier : s'il appartient a une
    zone devenue orpheline, HEC-RAS lit l'autre, et ce qu'on vient d'ecrire
    n'a aucun effet. PiloteHecRas.preparer() refusait deja ce cas avant tout
    calage ; les fonctions qui ECRIVENT, appelees seules, ne le refusaient
    pas. A appeler AVANT toute ecriture.
    """
    if nom_zone_2d is not None:
        return
    ambigus = {n: [i["zone"]] + i["autres_zones"]
               for n, i in carte.items() if i["autres_zones"]}
    if ambigus:
        detail = "; ".join(f"« {n} » dans {z}" for n, z in ambigus.items())
        raise ValueError(
            f"condition(s) limite(s) de meme nom dans plusieurs zones 2D de "
            f"{Path(chemin).name} : {detail}. Sans nom de zone 2D, rien ne "
            f"dit lequel de ces blocs HEC-RAS lit : le fichier n'est pas "
            f"modifie. Donner le nom de la zone (parametre « Nom_zone_2D » "
            f"du classeur).")


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

    Les valeurs sont interpolees lineairement sur la nouvelle grille. QUAND
    LE NOUVEAU PAS DIVISE L'ANCIEN (1 h -> 6 min, 30 -> 6 min), elles sont
    INCHANGEES aux instants de l'ancienne grille : le pic d'un hydrogramme
    horaire reste a la valeur et a l'heure ou il etait. SINON (15 -> 6 min,
    ou un pas plus grossier), un point d'origine tombe entre deux points
    neufs : le volume est conserve, mais la pointe d'une crue rapide est
    rabotee. Le compte rendu porte l'ecart mesure (« ecart_max »).

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
    _refuser_zone_ambigue(chemin, {nom: info}, nom_zone_2d)
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
    # CE QUE LE RE-CADENCAGE A DEPLACE (11/11/2026) : le plus grand ecart
    # entre la serie reecrite et la serie d'origine, toutes deux lues comme
    # HEC-RAS les lit — lineairement entre leurs points —, sur la duree
    # d'origine. Nul quand la nouvelle grille contient l'ancienne ; sinon un
    # point d'origine tombe entre deux points neufs, et c'est la POINTE qui
    # est rabotee. Mesure, pas corrige : voir _dire_ecart_de_recadencage.
    instants_avant = np.arange(len(valeurs)) * pas_avant
    instants_apres = np.arange(nb_apres) * pas_apres
    instants = np.union1d(instants_avant,
                          instants_apres[instants_apres <= duree_h + 1e-9])
    ecart_max = float(np.max(np.abs(
        np.interp(instants, instants_apres, nouvelles)
        - np.interp(instants, instants_avant, valeurs))))

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
    _ecrire_texte(chemin, "".join(lignes))

    return {"nom": nom, "zone": info["zone"], "duree_h": duree_h,
            "duree_apres_h": (nb_apres - 1) * pas_apres,
            "prolonge_h": (nb_apres - 1) * pas_apres - duree_h,
            "intervalle_avant_h": pas_avant, "intervalle_apres": intervalle,
            "nb_avant": len(valeurs), "nb_apres": nb_apres,
            "pic_avant": float(np.max(valeurs)),
            "pic_apres": float(np.max(nouvelles)),
            "ecart_max": ecart_max}


def retarder_hydrogrammes(fichier_unsteady, nb_pas, apports, nom_zone_2d=None,
                          noms_connus=None):
    """
    Retarde de « nb_pas » pas les hydrogrammes de debit du fichier unsteady.

    Hors « apports » (alimentation amont, apports non cales ici) : nb_pas
    copies de la PREMIERE valeur sont posees en tete — le debit de base tenu
    pendant le retard. Les « apports » a caler gardent leurs heures et sont
    prolonges par leur derniere valeur : le calage les reecrit, ils n'ont
    qu'a couvrir la fenetre allongee. Chaque tableau gagne nb_pas valeurs.

    nb_pas EST UN MULTIPLE DE DIX, le nombre de valeurs par ligne : les
    lignes ajoutees en tete repetent le premier champ tel qu'il est ecrit,
    et les lignes d'origine restent intactes, sans arrondi.

    Les blocs sont traites DU BAS VERS LE HAUT : les indices de la carte
    restent justes pour ceux qui ne sont pas encore reecrits.

    Retourne les noms retardes, hors apports.
    """
    if nb_pas <= 0 or nb_pas % 10:
        raise ValueError(f"nb_pas = {nb_pas} : un multiple de dix est attendu")
    chemin = Path(fichier_unsteady)
    carte = cartographier_hydrogrammes(chemin, nom_zone_2d, noms_connus)
    _refuser_zone_ambigue(chemin, carte, nom_zone_2d)
    lignes = _lire_lignes(chemin)
    retardes = []
    for nom, info in sorted(carte.items(), key=lambda c: -c[1]["debut"]):
        debut, fin = info["debut"], info["fin"]
        entete = next(j for j in range(debut - 1, -1, -1)
                      if lignes[j].startswith(MOTIF_HYDROGRAMME))
        valeurs = lire_hydrogramme_unsteady(chemin, debut, fin)
        if nom in apports:
            prolonge = np.concatenate([valeurs, np.full(nb_pas, valeurs[-1])])
            lignes[debut:fin] = [l + "\n" for l in _table_debits(prolonge)]
        else:
            premier = lignes[debut].rstrip("\n")[:8].rjust(8)
            lignes[debut:debut] = [premier * 10 + "\n"] * (nb_pas // 10)
            retardes.append(nom)
        lignes[entete] = f"{MOTIF_HYDROGRAMME} {len(valeurs) + nb_pas} \n"
    _ecrire_texte(chemin, "".join(lignes))
    return sorted(retardes)


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


def _nom_hdf(valeur):
    """
    Nom lu dans un .hdf de HEC-RAS : UTF-8 STRICT, PUIS cp1252, PUIS latin-1.

    La regle de la maison (_lire_texte), appliquee a des octets ; meme cascade
    que pont_hecras._texte, que ce module ne peut pas importer (c'est le pont
    qui importe le pilote). Jusqu'au 11/11/2026 le nom etait decode en UTF-8
    AVEC REMPLACEMENT : « Pont de Béhobie », ecrit en cp1252, etait annonce
    « Pont de B?hobie » — un nom que l'utilisateur ne retrouve nulle part
    dans son modele.
    """
    if not isinstance(valeur, bytes):
        return str(valeur)
    for encodage in ("utf-8", "cp1252"):
        try:
            return valeur.decode(encodage)
        except UnicodeDecodeError:
            continue
    return valeur.decode("latin-1")


def lignes_reference_sans_trace(fichier_geometrie):
    """
    Reference lines que le .gXX.hdf nomme sans en porter AUCUN POINT : [noms].
    Vide si toutes ont un trace, ou si le .gXX.hdf n'existe pas encore.

    POURQUOI CE CONTROLE EXISTE. Le 27/10/2026, le .gXX.hdf d'un modele reel
    nommait ses trois reference lines avec un « Polyline Points » vide.
    HEC-RAS ne regenere le .gXX.hdf que si le .gXX est plus recent que lui :
    sinon il reprend ces lignes telles quelles, et RasUnsteady s'arrete des
    leur lecture (« forrtl: severe (157) ... READ_UN_HDF_REF_P »). Deux
    calculs perdus, les 27 et 28/10, sans que rien n'en ait annonce la cause.

    LU AVEC h5py ET NON PAR ras-commander : selon sa version, celui-ci rend
    ces lignes en « LINESTRING EMPTY » (0.99.2) ou n'en rend aucune (0.105).
    """
    import h5py

    g = Path(fichier_geometrie)
    hdf = g.with_suffix(g.suffix + ".hdf")
    if not hdf.is_file():
        return []
    with h5py.File(hdf, "r") as h:
        groupe = h.get("Geometry/Reference Lines")
        if groupe is None or "Attributes" not in groupe:
            return []
        noms = [_nom_hdf(n).strip() for n in groupe["Attributes"]["Name"]]
        if ("Polyline Info" not in groupe or "Polyline Points" not in groupe
                or groupe["Polyline Points"].shape[0] == 0):
            return noms
        # « Polyline Info » : une ligne par objet — premier point, NOMBRE DE
        # POINTS, premiere partie, nombre de parties.
        points = groupe["Polyline Info"][()][:, 1]
    return [nom for nom, n in zip(noms, points) if n == 0]


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
    return (_messages_du_hdf(hdf_resultats)
            or _messages_des_journaux(hdf_resultats)
            or "Aucun message de HEC-RAS exploitable : ouvrir le plan dans "
            "HEC-RAS et lancer le calcul a la main pour voir ce qu'il refuse.")


def _messages_du_hdf(hdf_resultats):
    """
    Messages lus dans le fichier de resultats, ou None — voir
    _messages_hecras(), qui l'interroge EN PREMIER.
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
    return None


def _messages_des_journaux(hdf_resultats):
    """
    Messages lus dans les _compute_pXX.log, celui du plan d'abord, ou None.
    """
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
    return None


# Ce qu'ecrit HEC-RAS quand il n'a pas pu reecrire le .gXX.hdf : la premiere
# phrase est celle de sa boite de dialogue, la seconde celle du compte rendu.
MOTIFS_ECRITURE_GEOMETRIE = ("Error writing geometry file",
                             "Error updating base geometry file")


def _erreur_ecriture_geometrie(hdf_resultats):
    """
    Explication a donner si HEC-RAS n'a PAS pu reecrire le .gXX.hdf, "" sinon.

    UN AUTRE PROGRAMME TENAIT LE FICHIER OUVERT. Reproduit le 30/10/2026 sur
    une copie de modele reel : le .gXX.hdf ouvert en lecture — ce que fait la
    couche « Maillage 2D » de QGIS, ou RAS Mapper —, HEC-RAS affiche « Error
    writing geometry file (hdf version) », le chien de garde de ras-commander
    ferme la boite, et le calcul tourne SUR L'ANCIEN HDF : une section ou une
    injection ecrite depuis dans le .gXX n'existe pas pour lui. compute_plan
    rend pourtant un succes. Seule trace : « Error updating base geometry file
    with pre-processed tables » dans le compte rendu.

    TOUT LE COMPTE RENDU EST LU, pas ses dernieres lignes comme dans
    _messages_hecras() : la phrase suit le pretraitement, et la simulation
    ecrit ensuite des dizaines de lignes.
    """
    try:
        import h5py
        with h5py.File(hdf_resultats, "r") as h:
            cle = "Results/Summary/Compute Messages (text)"
            if cle not in h:
                return ""
            brut = h[cle][()]
    except Exception:                                        # noqa: BLE001
        return ""
    if isinstance(brut, bytes):
        texte = brut.decode("utf-8", "replace")
    else:
        texte = "\n".join(x.decode("utf-8", "replace") if isinstance(x, bytes)
                          else str(x) for x in np.ravel(brut))
    ligne = next((l.strip() for l in texte.splitlines()
                  if any(m in l for m in MOTIFS_ECRITURE_GEOMETRIE)), "")
    if not ligne:
        return ""
    return (f"HEC-RAS n'a pas pu mettre a jour le pretraitement de la "
            f"geometrie (« {ligne[:120]} ») : un autre programme tenait le "
            f".gXX.hdf ouvert — QGIS (couche « Maillage 2D »), RAS Mapper ou "
            f"l'interface HEC-RAS. Le calcul a tourne sur l'ANCIEN "
            f"pretraitement, ou peuvent manquer des sections ou des injections "
            f"ecrites depuis. Fermer ces programmes, puis relancer.")


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


def symbole_decimal():
    """
    Symbole decimal de Windows pour cet utilisateur, ou None si on ne sait pas.

    HEC-RAS EXIGE LE POINT. Avec la virgule — le reglage francais d'origine —
    Ras.exe ouvre un message « HEC-RAS requires the "." symbol be used for
    decimals » et attend un clic. Releve le 10/11/2026 (7.0.1) : dix minutes
    plus tard le calcul n'avait pas commence, et le chien de garde de
    ras-commander n'avait pas ferme le message.
    """
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Control Panel\International") as cle:
            return winreg.QueryValueEx(cle, "sDecimal")[0]
    except (ImportError, OSError):
        return None


def par_controleur(version):
    """
    Faut-il lancer le calcul par le controleur COM plutot que par
    « Ras.exe -c » ? Vrai a partir de HEC-RAS 7.0.2.

    SONDE DU 10/11/2026 (Muncie, tools/sonde_ligne_commande.py). En 7.0.1,
    « Ras.exe -c projet plan » calcule le plan nomme et lui seul. En 7.0.2,
    il calcule TOUS les plans du projet, dans l'ordre du .prj — plan nomme,
    plan range dans la liste, plan courant designe, plan non nomme : quatre
    formes, meme resultat. Le controleur (RAS702.HECRASController), lui,
    calcule le plan courant et lui seul.
    """
    numeros = [int(n) for n in re.findall(r"\d+", str(version or ""))[:3]]
    return (numeros + [0, 0, 0])[:3] >= [7, 0, 2]


# Cadence, en secondes, a laquelle calculer() regarde ce que HEC-RAS ecrit.
PERIODE_SURVEILLANCE_S = 20


def _heure_du_dossier(dossier):
    """
    Heure du disque qui porte le projet — celle des dates de ses fichiers.

    Un partage reseau n'a pas l'horloge du poste : comparer une date de
    fichier a time.time() fausse plan_detourne() de tout leur ecart.
    """
    jalon = Path(dossier) / "_jalon_calcul.tmp"
    try:
        jalon.write_bytes(b"")
        return jalon.stat().st_mtime
    except OSError:
        return time.time()
    finally:
        try:
            jalon.unlink()
        except OSError:
            pass


def plan_detourne(dossier, nom_projet, plan, depuis):
    """
    HEC-RAS calcule-t-il un AUTRE plan que celui qu'on lui a demande ?
    Retourne le numero de cet autre plan, ou None.

    RELEVE LE 10/11/2026 (HEC-RAS 7.0.2, projet de 17 plans) : lance pour
    p14, Ras.exe a parcouru les plans du projet depuis p01 et en a recalcule
    quatre par-dessus leurs resultats ; p14 n'a jamais ete ouvert. La chaine
    n'en a rien su pendant 4 h 53 : compute_plan ne rend la main qu'a la fin.

    DEUX CONDITIONS, ENSEMBLE : un .pMM.tmp.hdf d'un autre plan CREE ET ECRIT
    depuis le lancement, et aucun signe de vie du notre (.bNN, .pNN.tmp.hdf
    ou .pNN.hdf ecrits depuis). La seconde epargne notre calcul quand un
    collegue calcule un autre plan du meme projet depuis son poste ; la date
    de CREATION ecarte son calcul deja en cours au lancement ; la date
    d'ECRITURE ecarte un reste de calcul que HEC-RAS 7.0.2 ou RAS Mapper
    recree en l'ouvrant, en lui rendant sa date d'ecriture d'origine.
    """
    dossier, plan = Path(dossier), str(plan).zfill(2)

    def depuis_le_lancement(chemin, creation=False):
        try:
            etat = chemin.stat()
        except OSError:
            return False
        return (getattr(etat, "st_birthtime", etat.st_ctime) if creation
                else etat.st_mtime) >= depuis

    if any(depuis_le_lancement(dossier / f"{nom_projet}.{suffixe}")
           for suffixe in (f"b{plan}", f"p{plan}.tmp.hdf", f"p{plan}.hdf")):
        return None
    for chemin in sorted(dossier.glob(f"{nom_projet}.p[0-9][0-9].tmp.hdf")):
        numero = chemin.name[len(nom_projet) + 2:len(nom_projet) + 4]
        if (numero != plan and depuis_le_lancement(chemin, creation=True)
                and depuis_le_lancement(chemin)):
            return numero
    return None


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


# Un echantillon de debit d'apport est tenu pour ABERRANT au-dela de ce
# multiple du plus fort des autres echantillons de la meme serie.
FACTEUR_ECHANTILLON_ABERRANT = 10.0


def bilan_masse_recalcule(chemin_hdf, facteur=FACTEUR_ECHANTILLON_ABERRANT):
    """
    Bilan de masse REFAIT a partir des series de debit aux conditions
    limites, et echantillons aberrants qu'il a fallu ecarter pour le faire.

    POURQUOI. Le 13/11/2026 (Ard_aval, apport ARD07, essai 2), HEC-RAS 7.0.2
    a rendu « Error Percent » = +27,52 % sur un calcul SAIN. A la toute
    derniere sortie (30,6 h), la serie de la condition limite ARD07 valait
    386 032 m3/s — le volume entier de l'apport (772 000 m3) rapporte a un
    pas de 2 s — quand l'hydrogramme injecte plafonne a 44,8 m3/s. HEC-RAS a
    compte ce volume une seconde fois en SORTIE : « Cum Outflow » 2 424 milliers
    de m3 pour 1 653 a la seule sortie aval. Le volume final, lui, tombait
    juste : refait sur les series aux conditions limites, le bilan vaut
    +0,5 millier de m3, soit 0,02 %. Le calage s'arretait sur une erreur de comptabilite du solveur,
    pas sur une perte d'eau.

    LA REGLE. Debit par condition limite, integre aux trapezes sur les
    sorties : positif = entree pour un hydrogramme de debit (« Flow
    Hydrographs » des conditions du plan), positif = sortie pour toute autre
    condition. Un echantillon d'hydrogramme de debit qui depasse « facteur »
    fois le plus fort des autres est remplace par son voisin, et signale.
    Pourcentage au sens de HEC-RAS : erreur / (volume initial + entrees).

    Rend {"pct", "pct_hecras", "erreur_milliers_m3", "aberrants"} — ou
    « aberrants » liste (condition, temps_h, debit, plus_fort_des_autres) —
    ou None si le fichier ne porte pas de quoi refaire le bilan (calcul 1D,
    sorties absentes). Ne leve pas : c'est un controle, pas une lecture
    dont le calage depend.
    """
    import h5py

    try:
        with h5py.File(chemin_hdf, "r") as h:
            resume = h["Results/Unsteady/Summary/Volume Accounting"].attrs
            v_debut = float(resume["Volume Starting"])
            v_fin = float(resume["Volume Ending"])
            pct_hecras = float(resume["Error Percent"])
            unite = resume.get("Vol Accounting in", b"1000 m^3")
            unite = unite.decode() if isinstance(unite, bytes) else str(unite)
            if "1000" not in unite:
                return None   # unites US ou autre : on ne refait pas
            hydros = h.get("Event Conditions/Unsteady/Boundary Conditions/"
                           "Flow Hydrographs")
            entrees = {n.split("BCLine:")[-1].strip()
                       for n in (hydros.keys() if hydros is not None else [])}
            temps_s = h[CHEMIN_SERIES_HDF + "/Time"][()] * 86400.0
            zones = h.get(CHEMIN_SERIES_HDF + "/2D Flow Areas")
            if zones is None or len(temps_s) < 3:
                return None
            v_in = v_out = 0.0
            aberrants = []
            for zone in zones.values():
                cl = zone.get("Boundary Conditions")
                if cl is None:
                    continue
                for nom, serie in cl.items():
                    if " - " in nom or serie.ndim != 2 or serie.shape[1] < 2:
                        continue
                    q = np.asarray(serie[:, 1], dtype=float)
                    if nom in entrees and len(q) > 2:
                        for i in range(len(q)):
                            autres = np.abs(np.delete(q, i))
                            plafond = np.nanmax(autres) if len(autres) else 0.0
                            if abs(q[i]) > facteur * max(plafond, 1.0):
                                aberrants.append((nom, temps_s[i] / 3600.0,
                                                  float(q[i]), float(plafond)))
                                q[i] = q[i - 1] if i else q[i + 1]
                    trapeze = getattr(np, "trapezoid", None) or np.trapz
                    volume = float(trapeze(np.nan_to_num(q), temps_s)) / 1000.0
                    if nom in entrees:
                        v_in += volume
                    else:
                        v_out += volume
    except (OSError, KeyError, ValueError, TypeError):
        return None
    # SIGNE DE HEC-RAS : positif quand le volume final depasse ce que les
    # flux expliquent (eau fabriquee).
    erreur = v_fin + v_out - v_debut - v_in
    base = v_debut + v_in
    if base <= 0:
        return None
    return {"pct": 100.0 * erreur / base, "pct_hecras": pct_hecras,
            "erreur_milliers_m3": erreur, "aberrants": aberrants}


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
    candidats = _chemins_plans_par_titre(dossier_projet, nom_projet, titre)
    if not candidats:
        return None
    return max(candidats, key=lambda c: c.stat().st_mtime).suffix[2:]


def _chemins_plans_par_titre(dossier_projet, nom_projet, titre):
    """Tous les .pNN du projet dont le « Plan Title » vaut ce titre."""
    cherche = str(titre).strip()
    candidats = []
    for chemin in sorted(Path(dossier_projet).glob(f"{nom_projet}.p[0-9][0-9]")):
        trouve = re.search(r"^Plan Title=(.*)$", _lire_texte(chemin), re.M)
        if trouve and trouve.group(1).strip() == cherche:
            candidats.append(chemin)
    return candidats


def plans_par_titre(dossier_projet, nom_projet, titre):
    """Numeros (« 07 ») de tous les plans du projet qui portent ce titre."""
    return [c.suffix[2:]
            for c in _chemins_plans_par_titre(dossier_projet, nom_projet, titre)]


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
                 plan_fenetre_pleine=None, coeurs=None,
                 plan_a_remplacer=None):
        """
        plan_a_remplacer : numero du plan SOURCE que l'ingenieur a accepte de
            voir remplace par le plan final (recalage d'un plan valide qui
            garde son nom, 10/11/2026). None = le plan de reference n'est
            jamais efface. Voir _remplacer_homonymes().
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
        self.plan_a_remplacer = (str(plan_a_remplacer).lstrip("pP").zfill(2)
                                 if plan_a_remplacer else None)
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

        # CHAQUE APPEL A ras-commander QUI ECRIT passe par _par_ras_commander,
        # qui rend aux fichiers leur encodage et leurs octets : voir
        # _retablir_octets.
        geometrie = None
        if self.geometrie_override:
            geometrie = self._par_ras_commander(
                lambda: RasPlan.clone_geom(self.geometrie_override),
                clone=("g", self.geometrie_override))
            if self.nom_clone_geometrie:
                # clone_geom ne prend pas de titre : on le pose apres coup.
                chemin = self.dossier / f"{self.nom_projet}.g{geometrie}"
                self._par_ras_commander(
                    lambda: GeomParser.set_geom_title(
                        chemin, self.nom_clone_geometrie), chemin)

        # SANS TITRE ICI, volontairement : jalonner() titre le plan et
        # l'unsteady des l'ouverture de la premiere etape, quelques lignes plus
        # loin dans caler(). Leur donner un nom de clone ne servirait qu'a le
        # voir remplace aussitot.
        unsteady = None
        if self.unsteady_override:
            unsteady = self._par_ras_commander(
                lambda: RasPlan.clone_unsteady(self.unsteady_override),
                clone=("u", self.unsteady_override))

        self.plan_travail = self._par_ras_commander(
            lambda: RasPlan.clone_plan(self.plan_reference, geometry=geometrie,
                                       unsteady_flow=unsteady),
            clone=("p", self.plan_reference))

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
            unsteady = self._par_ras_commander(
                lambda: RasPlan.clone_unsteady(numero_actuel),
                clone=("u", numero_actuel))
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
                self._par_ras_commander(
                    lambda: RasPlan.enable_hdf_output_variable(
                        self.plan_travail, "Cell Courant"),
                    self.dossier / f"{self.nom_projet}.p{self.plan_travail}")
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

        # REFERENCE LINES SANS POINT DANS LE .gXX.hdf — ICI ON REFUSE. Voir
        # lignes_reference_sans_trace() : tant que le .gXX n'est pas plus
        # recent que lui, HEC-RAS reprend ce HDF tel quel et RasUnsteady
        # s'arrete des le premier pas. Un pretraitement PERIME, lui, sera
        # refait depuis le .gXX au premier calcul : on laisse faire HEC-RAS.
        try:
            sans_trace = lignes_reference_sans_trace(
                self._geometrie_du_plan(self.plan_travail))
        except Exception:                                    # noqa: BLE001
            sans_trace = []
        if sans_trace and not perime:
            raise ValueError(
                f"le pretraitement de la geometrie "
                f"({self._geometrie_du_plan(self.plan_travail).name}.hdf) "
                f"nomme {len(sans_trace)} reference line(s) SANS AUCUN POINT "
                f": {', '.join(sans_trace)}. HEC-RAS s'arreterait au premier "
                f"calcul (« READ_UN_HDF_REF_P »). Fermer QGIS, RAS Mapper et "
                f"HEC-RAS, ouvrir la geometrie dans HEC-RAS et l'enregistrer, "
                f"puis relancer le calage.")

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
        valeurs d'origine A LEURS INSTANTS quand le pas de travail divise le
        pas d'origine : elle ne contredit alors jamais la donnee, la ou
        changer l'etiquette la contredit toujours.

        QUAND LE PAS DE TRAVAIL NE DIVISE PAS LE PAS D'ORIGINE (11/11/2026),
        la pointe d'une condition NON CALEE est rabotee — mesure : jusqu'a
        2,5 % pour une crue qui monte en 45 min a 15 -> 6 min, rien de
        sensible pour une crue lente. Le calcul n'est pas change (decision
        utilisateur) : l'ecart est AFFICHE, voir _dire_ecart_de_recadencage.

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

        # AVANT D'ECRIRE (11/11/2026) : _controler_couverture(), en fin de
        # passe, leve sur un instant de plan invalide — apres que toutes les
        # conditions ont ete reecrites. Le meme refus, tout de suite.
        self._refuser_fenetre_de_plan_invalide()
        duree_simulation = self._duree_a_couvrir()
        convertis = self._recadencer_chaque_condition(intervalle_cible,
                                                      duree_simulation)

        if convertis:
            self.carte = cartographier_hydrogrammes(self.fichier_unsteady,
                                                    self.nom_zone_2d,
                                                    self._bc_lines_connues())

        self._controler_pas_apres_recadencage(intervalle_cible)
        self._controler_couverture()
        return convertis

    def _refuser_fenetre_de_plan_invalide(self):
        """
        Leve ValueError si la fenetre de simulation du plan de travail porte
        un instant mal forme. Etape de _recadencer_apports(), AVANT toute
        ecriture. Memes conditions que conditions_trop_courtes() : pas de
        plan, ou une fenetre absente, ne bloquent rien.
        """
        if not self.plan_travail:
            return
        plan = self.dossier / f"{self.nom_projet}.p{self.plan_travail}"
        if not plan.is_file():
            return
        fenetre = fenetre_simulation_du_plan(plan)
        if fenetre.get("debut") and fenetre.get("fin"):
            instant_hecras(fenetre["debut"])
            instant_hecras(fenetre["fin"])

    def _duree_a_couvrir(self):
        """
        Duree de la simulation du plan de travail, en heures, que les apports
        pilotes doivent couvrir ; None si rien n'est pilote ou si la fenetre
        n'est pas lisible. Etape de _recadencer_apports().
        """
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
        return duree_simulation

    def _recadencer_chaque_condition(self, intervalle_cible, duree_simulation):
        """
        Re-cadence chaque condition limite de la carte, dans l'ordre des noms ;
        rend les comptes rendus des conditions converties. Etape de
        _recadencer_apports().
        """
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
            self._dire_ecart_de_recadencage(nom, pilote, compte_rendu)
        return convertis

    @staticmethod
    def _dire_ecart_de_recadencage(nom, pilote, compte_rendu):
        """
        Dit ce que le re-cadencage a change a la POINTE d'une condition non
        calee, quand le pas de travail ne divise pas son pas d'origine. Etape
        de _recadencer_chaque_condition().

        SEULES LES CONDITIONS NON CALEES : un apport pilote est mis a zero au
        calcul de reference puis reecrit en entier a chaque essai, sa serie
        re-cadencee n'entre dans aucun calcul.
        AU-DESSUS DE SEUIL_ECART_RECADENCAGE, « AVERTISSEMENT » : l'etape
        Suivi montre alors la ligne sous sa banniere, au debut du calage
        (elle ne lit que la fin du journal). En dessous, la ligne reste une
        information du journal.
        """
        if pilote:
            return
        pas_avant = compte_rendu["intervalle_avant_h"]
        pas_apres = _intervalle_en_heures(compte_rendu["intervalle_apres"])
        if not pas_avant or not pas_apres:
            return
        rapport = pas_avant / pas_apres
        if pas_apres <= pas_avant and abs(rapport - round(rapport)) < 1e-9:
            return
        pointe = compte_rendu["pic_avant"]
        if not pointe > 0:
            return
        perte = 100.0 * (compte_rendu["pic_apres"] / pointe - 1.0)
        ecart = compte_rendu["ecart_max"] / pointe
        marque = ("AVERTISSEMENT : " if ecart >= SEUIL_ECART_RECADENCAGE
                  else "")
        print(f"   {marque}« {nom} » n'est pas cale ici, et le pas de travail "
              f"({60 * pas_apres:g} min) ne divise pas son pas d'origine "
              f"({60 * pas_avant:g} min) : sa pointe passe de {pointe:.2f} a "
              f"{compte_rendu['pic_apres']:.2f} m3/s ({perte:+.2f} %), ecart "
              f"maximal a la serie d'origine {100.0 * ecart:.2f} % de la "
              f"pointe. C'est la serie re-cadencee que HEC-RAS lit.",
              flush=True)

    def _controler_pas_apres_recadencage(self, intervalle_cible):
        """
        Relit le pas et l'accord en-tete/tableau de chaque condition ; leve
        ValueError en nommant celles en desaccord. Etape de
        _recadencer_apports().
        """
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

    def _controler_couverture(self):
        """
        Leve ValueError si une condition limite s'arrete avant la fin de la
        simulation. Etape de _recadencer_apports().
        """
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
            source = self.fichier_unsteady.suffix[2:]
            flot = self._par_ras_commander(
                lambda: RasPlan.clone_unsteady(source, new_title=titre),
                clone=("u", source))
            plan = self._par_ras_commander(
                lambda: RasPlan.clone_plan(self.plan_travail, new_title=titre,
                                           unsteady_flow=flot),
                clone=("p", self.plan_travail))
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

    def _retirer_resultats_rasmap(self, numero):
        """
        Retire du .rasmap la couche de resultats d'un plan qu'on vient
        d'effacer : RAS Mapper la montrerait encore, sans fichier derriere
        elle, a cote de celle du plan qui le remplace.

        NE LEVE JAMAIS, comme _declarer_resultats_rasmap. Le .rasmap n'est
        reecrit que s'il se reparse.
        """
        chemin = self.dossier / f"{self.nom_projet}.rasmap"
        try:
            texte = _lire_texte(chemin)
            ouverture = re.search(
                r'[ \t]*<Layer\s[^>]*?Type="RASResults"[^>]*?'
                + re.escape(f'Filename=".\\{self.nom_projet}.p{numero}.hdf"')
                + r'[^>]*>', texte)
            if not ouverture:
                return
            fin = ouverture.end()
            if not ouverture.group().endswith("/>"):
                # Une couche de resultats porte des couches filles : on compte
                # les ouvertures jusqu'a SA balise fermante.
                niveau = 1
                for balise in re.finditer(r"<Layer\b[^>]*?(/?)>|</Layer>",
                                          texte[fin:]):
                    if balise.group().startswith("</"):
                        niveau -= 1
                    elif not balise.group(1):
                        niveau += 1
                    if niveau == 0:
                        fin += balise.end()
                        break
                else:
                    return
            fin += len(re.match(r"[ \t]*\r?\n?", texte[fin:]).group())
            neuf = texte[:ouverture.start()] + texte[fin:]
            from xml.etree import ElementTree
            ElementTree.fromstring(neuf)
            _ecrire_texte(chemin, neuf)
        except Exception:                                    # noqa: BLE001
            return

    def _remplacer_homonymes(self, titre):
        """
        Efface les plans d'un calage PRECEDENT portant le titre de l'etape.

        Le plan de reference et le plan de travail sont intouchables — sauf le
        plan source que l'ingenieur a accepte de remplacer (plan_a_remplacer),
        qui part ici avec ses resultats et sa couche du .rasmap. L'unsteady
        et la geometrie QUE CES PLANS DESIGNAIENT partent avec eux, si plus
        aucun plan survivant ne les designe : sans cela, chaque relance
        laisserait derriere elle un jeu complet de fichiers que personne ne
        saurait plus rattacher a rien.

        EUX SEULS, comme elaguer_etapes. Balayer tout .uNN et tout .gNN sans
        plan emportait aussi la variante que l'ingenieur garde de cote, sans
        sauvegarde (audit du 11/10/2026).
        """
        efface, designes = [], set()
        for chemin in sorted(self.dossier.glob(f"{self.nom_projet}.p[0-9][0-9]")):
            numero = chemin.suffix[2:]
            if numero == str(self.plan_travail).zfill(2) or (
                    numero == self.plan_reference
                    and numero != self.plan_a_remplacer):
                continue
            if self._titre(chemin, "Plan Title") != titre:
                continue
            # Ce que le plan designe, RELEVE AVANT de l'effacer : apres, le
            # fichier n'est plus la pour le dire.
            texte = _lire_texte(chemin)
            for cle, lettre in (("Flow File", "u"), ("Geom File", "g")):
                trouve = re.search(rf"^{cle}={lettre}(\w+)", texte, re.M)
                if trouve:
                    designes.add(f"{lettre}{trouve.group(1)}")
            self._effacer_objet(f"p{numero}")
            self._retirer_resultats_rasmap(numero)
            efface.append(f"p{numero}")
        if not efface:
            return []
        for objet in sorted(designes, reverse=True):          # u avant g
            lettre, numero = objet[0], objet[1:]
            cle = "Flow File" if lettre == "u" else "Geom File"
            if not self._utilise_par_un_plan(cle, lettre, numero):
                self._effacer_objet(objet)
                efface.append(objet)
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
        _ecrire_texte(chemin, "".join(lignes))

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
        _ecrire_texte(fichier_plan, "".join(lignes))

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
                _ecrire_texte(fichier_plan, "".join(lignes))
                return voulue_min / 60.0
        return None

    def retarder(self, heures, apports):
        """
        Retarde tout l'axe temporel du plan de travail — voir
        calage.Modele.retarder et retarder_hydrogrammes().

        LE RETARD EST ARRONDI AU-DESSUS a dix pas de travail (1 h au pas de
        6 min) : les lignes des hydrogrammes non cales restent intactes. La
        fin de simulation recule d'autant, et la borne de limiter_duree()
        avec elle : la queue de l'evenement n'est pas perdue.

        Retourne le retard applique, en heures.
        """
        pas = {round(i["intervalle_h"], 9) for i in self.carte.values()
               if i["intervalle_h"]}
        if len(pas) != 1:
            raise ValueError(
                f"pas de temps des hydrogrammes heterogenes ({sorted(pas)} h) "
                f"dans {self.fichier_unsteady.name} : un retard commun ne "
                f"s'y ecrit pas en un nombre entier de pas.")
        pas = pas.pop()
        nb_pas = 10 * int(math.ceil(float(heures) / (10 * pas) - 1e-9))
        retard_h = nb_pas * pas
        fenetre = fenetre_simulation_du_plan(
            self.dossier / f"{self.nom_projet}.p{self.plan_travail}")
        duree_h = (_en_minutes(instant_hecras(fenetre["fin"]))
                   - _en_minutes(instant_hecras(fenetre["debut"]))) / 60.0

        retardes = retarder_hydrogrammes(
            self.fichier_unsteady, nb_pas, apports, self.nom_zone_2d,
            self._bc_lines_connues())
        for nom, valeurs in self.originaux.items():
            self.originaux[nom] = (
                np.concatenate([valeurs, np.full(nb_pas, valeurs[-1])])
                if nom in apports
                else np.concatenate([np.full(nb_pas, valeurs[0]), valeurs]))
        self.carte = cartographier_hydrogrammes(self.fichier_unsteady,
                                                self.nom_zone_2d,
                                                self._bc_lines_connues())
        if getattr(self, "duree_reference_h", None) is not None:
            self.duree_reference_h += retard_h
        self.limiter_duree(duree_h + retard_h)
        autres = sorted({m.group(1) for m in (
            re.match(r"(?!Flow )([A-Za-z ]+Hydrograph)= *\d", l)
            for l in _lire_lignes(self.fichier_unsteady)) if m})
        if autres:
            print(f"   AVERTISSEMENT : {', '.join(autres)} NON retarde(s) — "
                  f"seuls les hydrogrammes de debit le sont.", flush=True)
        print(f"   entrees retardees de {retard_h:g} h : "
              f"{', '.join(retardes) or 'aucune'} ; fin de simulation "
              f"repoussee a {duree_h + retard_h:g} h", flush=True)
        return retard_h

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
        Remplace la « Flow Hydrograph Slope » d'un apport deja en place, ou
        l'ajoute si le bloc n'en a pas.

        La pente est ecrite a la creation de l'injection, avant que le classeur
        existe : sans cette methode, une valeur saisie dans le classeur serait
        restee lettre morte.

        BLOC SANS LIGNE DE PENTE : HEC-RAS n'ecrit pas la ligne quand le champ
        « EG Slope » est reste vide dans l'editeur. L'apport tourne a debit
        nul, puis RasUnsteady.exe plante (SNETREAL2, code 157) des que le
        calage y met du debit (constat du 27/10/2026). La ligne
        est donc ajoutee, a la place ou HEC-RAS l'ecrit.
        """
        self._verifier_connu(nom_apport)
        if not 1e-6 < float(pente) <= 1.0:
            raise ValueError(f"pente {pente} hors de ]0 ; 1]")
        info = self.carte[nom_apport]
        lignes = _lire_lignes(self.fichier_unsteady)
        # On ne touche QUE le bloc de cet apport : le fichier en contient
        # d'autres, et « Flow Hydrograph Slope= » y apparait plusieurs fois.
        ecrit = False
        fenetre = range(info["debut"], min(info["fin"] + 3, len(lignes)))
        for i in fenetre:
            if lignes[i].startswith("Flow Hydrograph Slope="):
                fin = "\n" if lignes[i].endswith("\n") else ""
                lignes[i] = f"Flow Hydrograph Slope= {pente} {fin}"
                ecrit = True
        if not ecrit:
            # Juste apres « Stage Hydrograph TW Check= », sinon juste apres
            # la table : l'ordre qu'ecrit HEC-RAS.
            place = next((i + 1 for i in fenetre if i >= info["fin"] and
                          lignes[i].startswith("Stage Hydrograph TW Check=")),
                         info["fin"])
            lignes.insert(place, f"Flow Hydrograph Slope= {pente} \n")
        _ecrire_texte(self.fichier_unsteady, "".join(lignes))
        if not ecrit:
            # Une ligne de plus decale les blocs suivants : la carte doit
            # suivre, sans quoi la prochaine ecriture tombe a cote.
            self.carte = cartographier_hydrogrammes(self.fichier_unsteady,
                                                    self.nom_zone_2d,
                                                    self._bc_lines_connues())

    # --- menage de fin de calage -------------------------------------------

    def _titre(self, chemin, cle):
        """Titre declare dans un fichier de plan, de geometrie ou d'unsteady."""
        trouve = re.search(rf"^{cle}=(.*)$", _lire_texte(chemin), re.M)
        return trouve.group(1).strip() if trouve else ""

    def _reliquats(self):
        """
        Traces laissees dans le dossier du modele par la preparation, hors
        plans et fichiers de calcul : les sauvegardes horodatees faites avant
        toute ecriture dans la geometrie ou l'unsteady, et les shapefiles que
        le plugin depose dans « _calage/ » pour les transmettre au pont.

        LES FICHIERS, JAMAIS LE DOSSIER « _calage/ ». Depuis la 0.9.8 le
        plugin propose la sortie dans « _calage/<prefixe> » : retirer le
        dossier emportait le classeur, le JSON, le suivi et les livrables du
        calage qui venait d'aboutir (audit du 11/10/2026). Ne partent que
        « sections.* » et « injections.* », les deux noms qu'ecrit
        noyau.ecrire_shp_temporaire.

        Elles ne sont retirees qu'a la FIN D'UN CALAGE REUSSI. Tant qu'il
        n'a pas abouti, les sauvegardes sont le seul retour en arriere
        possible sur le modele.
        """
        traces = sorted(
            self.dossier.glob(f"{self.nom_projet}.*.sauvegarde_*"))
        for nom in ("sections", "injections"):
            traces += sorted(f for f in (self.dossier / "_calage").glob(
                f"{nom}.*") if f.is_file())
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
        la preparation, et shapefiles transmis au pont. Le dossier
        « _calage/ » ne part que s'il en reste VIDE : il peut porter la
        sortie du calage (voir _reliquats).

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
                trace.unlink()
            except OSError:
                # Un reliquat verrouille — fichier ouvert ailleurs — ne doit
                # pas faire echouer un calage abouti.
                pass
        try:
            # rmdir, jamais rmtree : il refuse un dossier qui n'est pas vide.
            (self.dossier / "_calage").rmdir()
        except OSError:
            pass
        return rendu

    def elaguer_etapes(self, prefixe="", apports=(), simuler=True):
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

          - RIEN SANS PLAN FINAL. Si aucun plan, hors plan de reference, ne
            porte le titre final (le prefixe seul), le calage n'a pas conclu :
            ses etapes sont alors tout ce qui existe, et les retirer
            effacerait le calage lui-meme. On refuse, et on le dit.
          - LE PLAN DE REFERENCE ET LE PLAN COURANT SONT INTOUCHABLES, comme
            partout ailleurs dans cette classe.
          - ON NE RECONNAIT QUE NOS PROPRES TITRES, EXACTS. Un plan dont le
            titre n'est ni « <prefixe>-sans » ni « <prefixe>-<apport> » pour
            un apport de la liste reste, quel qu'il soit. PAS DE TEST SUR LE
            DEBUT DU TITRE : « Q100-… » emporterait les plans du scenario
            « Q100-V2 ».

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
        etapes = {depart} | {titre_etape(f"{PREFIXE_ETAPE_APPORT}{a}", prefixe)
                             for a in apports}

        titres = {}
        for chemin in sorted(
                self.dossier.glob(f"{self.nom_projet}.p[0-9][0-9]")):
            titres[chemin.suffix[2:]] = self._titre(chemin, "Plan Title") or ""

        if not any(titre == final and numero != self.plan_reference
                   for numero, titre in titres.items()):
            return {"refus": (f"aucun plan « {final} » dans ce projet : le "
                              f"calage n'a pas conclu, et ses etapes sont "
                              f"tout ce qu'il en reste. Rien n'est retire."),
                    "etapes": [], "supprimes": []}

        courant = (str(self.plan_travail).zfill(2)
                   if self.plan_travail is not None else None)
        a_retirer = sorted(
            numero for numero, titre in titres.items()
            if titre in etapes
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
            _ecrire_texte(prj, "".join(gardees))

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
            _ecrire_texte(chemin, "".join(lignes))

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
        _ecrire_texte(fichier_plan, "".join(lignes))

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
        self._par_ras_commander(
            lambda: RasUnsteady.write_table_to_file(
                str(self.fichier_unsteady), MOTIF_HYDROGRAMME, table,
                info["debut"]),
            self.fichier_unsteady)

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

    def _manques_avant_calcul(self):
        """
        Ce que HEC-RAS ne trouverait pas en ouvrant le projet pour calculer
        le plan de travail : liste de textes, vide si tout y est.

        Le .prj est relu AU MOMENT DE LANCER : une interface HEC-RAS ouverte
        sur le projet le reecrit depuis sa memoire, sans les plans que la
        chaine vient d'y declarer (voir hecras_ouvert).
        """
        prj = self.dossier / f"{self.nom_projet}.prj"
        declares = set(re.findall(r"^(?:Plan|Geom|Unsteady|Flow) File=(\w+)",
                                  _lire_texte(prj), re.M))
        plan = str(self.plan_travail).zfill(2)
        manques = []
        if f"p{plan}" not in declares:
            manques.append(f"« Plan File=p{plan} » absent de {prj.name}")
        for lire in (self._geometrie_du_plan, self._unsteady_du_plan):
            try:
                chemin = lire(plan)
            except ValueError as e:
                manques.append(str(e))
                continue
            if not chemin.is_file():
                manques.append(f"{chemin.name} absent")
            elif chemin.suffix[1:] not in declares:
                manques.append(f"« {chemin.suffix[1:]} » absent de {prj.name}")
        return manques

    def _calculer_par_controleur(self):
        """
        Calcule le plan de travail par le controleur COM de HEC-RAS, qui
        calcule le plan COURANT et lui seul (voir par_controleur). Rend True
        si HEC-RAS annonce un calcul abouti ; calculer() relit ensuite le
        .hdf, comme apres compute_plan.

        LE PLAN SE DESIGNE PAR SON TITRE : c'est la seule prise du
        controleur. jalonner() le pose, et remplace tout homonyme ; on relit
        quand meme quel fichier HEC-RAS a retenu, et l'on refuse s'il s'est
        trompe de plan. Le .prj n'est pas reecrit : le plan courant du
        projet reste celui de l'ingenieur.
        """
        import win32com.client

        numero = str(self.plan_travail).zfill(2)
        titre = self._titre(self.dossier / f"{self.nom_projet}.p{numero}",
                            "Plan Title")
        controleur = win32com.client.Dispatch(
            "RAS" + "".join(re.findall(r"\d", self.version))
            + ".HECRASController")
        # Meme veilleur de boites de dialogue que compute_plan : sans lui,
        # un message de HEC-RAS suspendrait le calage jusqu'a un clic.
        veilleur = None
        try:
            from ras_commander.RasDialogWatchdog import DialogWatchdog
            veilleur = DialogWatchdog()
            veilleur.start()
        except Exception:                                    # noqa: BLE001
            veilleur = None
        try:
            controleur.Project_Open(str(self.dossier / f"{self.nom_projet}.prj"))
            controleur.Plan_SetCurrent(titre)
            retenu = Path(str(controleur.CurrentPlanFile())).suffix[2:]
            if retenu != numero:
                raise RuntimeError(
                    f"HEC-RAS a retenu le plan p{retenu} pour le titre "
                    f"« {titre} », et non p{numero} : deux plans portent "
                    f"sans doute ce titre.")
            return bool(controleur.Compute_CurrentPlan(None, None, True)[0])
        finally:
            for fermer in (controleur.Project_Close, controleur.QuitRas):
                try:
                    fermer()
                except Exception:                            # noqa: BLE001
                    pass
            if veilleur is not None:
                veilleur.stop()

    def calculer(self):
        """Lance le calcul et rapporte sa qualite numerique."""
        from ras_commander import HdfResultsPlan, RasCmdr, RasPlan
        from ras_commander.RasBco import BcoMonitor

        debut = time.time()
        # AVANT DE LANCER : HEC-RAS a-t-il de quoi calculer CE plan ? Un plan
        # que le .prj ne declare plus ne se calcule pas, et HEC-RAS ne le dit
        # pas.
        manques = self._manques_avant_calcul()
        if manques:
            return ResultatCalcul(
                reussi=False, duree_s=time.time() - debut,
                message=f"le projet n'est plus en etat de calculer le plan "
                        f"p{self.plan_travail} : {' ; '.join(manques)}. "
                        f"Quelque chose a reecrit le projet depuis que la "
                        f"chaine a cree ce plan — le cas connu est "
                        f"l'interface HEC-RAS restee ouverte. La fermer, "
                        f"puis relancer le calage.")
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
        plan = self.dossier / f"{self.nom_projet}.p{self.plan_travail}"
        # PENDANT LE CALCUL : voir plan_detourne(). compute_plan ne rend la
        # main qu'a la fin ; ce fil arrete un HEC-RAS parti sur d'autres plans
        # avant qu'il ne les recalcule tous. Il ne ferme que les HEC-RAS nes
        # depuis le lancement, jamais une session de l'utilisateur.
        depart = _heure_du_dossier(self.dossier)
        pids_au_depart = (processus_avant if processus_avant is not None
                          else pids_hecras())
        detourne, fin = [], threading.Event()

        def surveiller():
            while not fin.wait(PERIODE_SURVEILLANCE_S):
                autre = plan_detourne(self.dossier, self.nom_projet,
                                      self.plan_travail, depart)
                if autre:
                    detourne.append((autre, fermer_processus(
                        orphelins_du_calcul(pids_au_depart, pids_hecras()))))
                    return

        fil = threading.Thread(target=surveiller, daemon=True)
        fil.start()
        try:
            # « Write Detailed= 1 » : compute_plan le pose TOUJOURS avant de
            # lancer HEC-RAS (0.99.2, RasCmdr.py l. 954), en relisant le plan
            # en UTF-8 errors="ignore" : un accent cp1252 y disparaissait du
            # plan que HEC-RAS lit (mesure du 08/11/2026, copie d'Aberou). Pose
            # ici, accents rendus ; compute_plan n'a plus rien a ecrire.
            self._par_ras_commander(
                lambda: BcoMonitor.enable_detailed_logging(plan), plan)
            # num_cores : ras-commander (RasPlan.set_num_cores, relu sur
            # GitHub le 22/09/2026, v0.99 a v0.102) reecrit AVANT le calcul
            # chaque ligne « UNET D1 Cores= », « UNET D2 Cores= » et
            # « PS Cores= » du plan calcule — ici le plan d'etape, jamais le
            # plan de reference. 0 vaudrait « tous » ; None laisse le plan tel
            # quel. APPELE ICI ET NON PAR compute_plan(num_cores=) : il relit
            # et reecrit le plan en UTF-8 errors="replace", et un titre
            # d'etape accentue (« Apport_Écluse ») y perdait son accent avant
            # le calcul. _par_ras_commander le lui rend.
            if self.coeurs:
                self._par_ras_commander(
                    lambda: RasPlan.set_num_cores(self.plan_travail,
                                                  self.coeurs), plan)
            # HEC-RAS 7.0.2 : « Ras.exe -c » calcule tous les plans du projet.
            # On passe alors par le controleur — voir par_controleur().
            if par_controleur(self.version):
                reussi = self._calculer_par_controleur()
            else:
                reussi = RasCmdr.compute_plan(self.plan_travail,
                                              overwrite_dest=True)
            erreur = ""
        except Exception as e:
            reussi, erreur = False, f"{type(e).__name__}: {e}"
        finally:
            fin.set()
            fil.join(60)
        self._fermer_orphelins(processus_avant)

        duree = time.time() - debut
        if detourne:
            autre, fermes = detourne[0]
            titre = self._titre(self.dossier / f"{self.nom_projet}.p{autre}",
                                "Plan Title")
            return ResultatCalcul(
                reussi=False, duree_s=duree,
                message=f"HEC-RAS {self.version} a calcule le plan p{autre} "
                        f"« {titre} » au lieu du plan p{self.plan_travail} "
                        f"demande. "
                        + (f"Calcul arrete ({', '.join(fermes)}) : p{autre} "
                           f"garde ses resultats d'avant. " if fermes else
                           "HEC-RAS n'a pas pu etre arrete : verifier les "
                           "resultats des autres plans du projet. ")
                        + "« Ras.exe -c » de HEC-RAS 7.0.2 calcule tous les "
                          "plans du projet (sonde du 10/11/2026) ; a partir "
                          "de cette version la chaine passe par le "
                          "controleur de HEC-RAS. Fermer HEC-RAS, puis "
                          "relancer le calage.")
        if erreur:
            return ResultatCalcul(reussi=False, duree_s=duree, message=erreur)
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
        ecriture = _erreur_ecriture_geometrie(self.hdf_resultats)
        absents = _series_absentes(self.hdf_resultats)
        if absents:
            return ResultatCalcul(
                reussi=False, duree_s=duree,
                message=f"calcul annonce reussi mais SANS RESULTATS : "
                        f"{absents}. " + (f"{ecriture} " if ecriture else "")
                        + _messages_hecras(self.hdf_resultats))
        # LE CALCUL A TOURNE — MAIS SUR QUELLE GEOMETRIE ? Voir
        # _erreur_ecriture_geometrie() : HEC-RAS a pu calculer sur l'ancien
        # pretraitement sans que rien d'autre ne le signale.
        if ecriture:
            return ResultatCalcul(reussi=False, duree_s=duree,
                                  message=ecriture)

        bilan = float("nan")
        try:
            comptes = HdfResultsPlan.get_volume_accounting(self.hdf_resultats)
            bilan = bilan_masse_depuis_comptes(comptes)
        except Exception:
            pass

        # UN ECHANTILLON ABERRANT A UNE CONDITION LIMITE FAUSSE LE BILAN DE
        # HEC-RAS SANS QU'UNE GOUTTE NE SOIT PERDUE — voir
        # bilan_masse_recalcule(). On ne remplace le chiffre du solveur que
        # si un tel echantillon est TROUVE : le bilan refait est alors juge
        # contre le meme seuil, et un calcul qui perd vraiment de l'eau reste
        # rejete. Les deux chiffres vont au journal.
        refait = bilan_masse_recalcule(self.hdf_resultats)
        if refait and refait["aberrants"]:
            for nom, t_h, q, plafond in refait["aberrants"]:
                print(f"   ALERTE : condition limite « {nom} » : {q:,.0f} m3/s "
                      f"a {t_h:.2f} h, pour {plafond:,.1f} m3/s au plus "
                      f"ailleurs — echantillon aberrant ecarte du bilan",
                      flush=True)
            print(f"   bilan de masse HEC-RAS {refait['pct_hecras']:+.3f} % ; "
                  f"refait sur les series aux conditions limites : "
                  f"{refait['pct']:+.3f} % "
                  f"({refait['erreur_milliers_m3']:+.1f} milliers de m3) — "
                  f"c'est lui qui est juge", flush=True)
            bilan = refait["pct"]

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

    def _par_ras_commander(self, appel, *fichiers, clone=None):
        """
        Lance un ecrivain de ras-commander, puis rend au .prj, aux
        « fichiers » qu'il reecrit en place et a la copie qu'il cree
        l'encodage et les octets d'avant l'appel (_retablir_octets).
        Decision du 11/10/2026.

        clone : (prefixe, numero) du fichier que l'appel clone. L'appel rend
            le numero de la copie, qui reprend les octets de sa source.
        """
        def fichier(prefixe, numero):
            return self.dossier / f"{self.nom_projet}.{prefixe}{numero}"

        gardes = {Path(f): Path(f).read_bytes()
                  for f in (fichier("prj", ""), *fichiers)}
        source = fichier(*clone).read_bytes() if clone else None
        try:
            resultat = appel()
        finally:
            for chemin, octets in gardes.items():
                _retablir_octets(chemin, octets)
        if clone:
            _retablir_octets(fichier(clone[0], resultat), source)
        return resultat

    def _verifier_connu(self, nom_apport):
        if nom_apport not in self.carte:
            raise KeyError(
                f"condition limite « {nom_apport} » absente du fichier "
                f"unsteady. Presentes : {sorted(self.carte)}")


# ---------------------------------------------------------------------------
# Diagnostic de raccordement, sans lancer de calcul
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # LE BANC VIT A COTE, PAS ICI (10/11/2026) : src/bancs/banc_pilote_hecras.py,
    # absent de l'archive du plugin. Il est joue d'abord, comme quand il
    # occupait ce bloc ; la ligne de commande --projet suit, inchangee.
    import argparse
    import runpy
    _banc = Path(__file__).resolve().parent / "bancs" / "banc_pilote_hecras.py"
    if not _banc.is_file():
        # SANS LE BANC, --projet RESTE UTILISABLE : c'est un diagnostic en
        # lecture seule, et c'est sur un poste installe, la ou le banc n'est
        # pas livre, qu'on en a besoin. Sans --projet, on sort en code 2.
        print("Le banc d'auto-tests de pilote_hecras.py n'est pas livre avec "
              "cette installation.")
        _code_banc = 2
    else:
        try:
            runpy.run_path(str(_banc), run_name="__main__")
            _code_banc = 0
        except SystemExit as _fin:             # le banc rend 1 sur un ECHEC
            _code_banc = _fin.code

    analyseur = argparse.ArgumentParser(
        description="Diagnostic du raccordement a un projet HEC-RAS. "
                    "Ne lance aucun calcul et ne modifie rien.")
    analyseur.add_argument("--projet", default=None,
                           help="omis : n'execute que l'auto-test ci-dessus")
    analyseur.add_argument("--unsteady", default=None,
                           help="fichier .uXX a examiner ; sinon le premier trouve")
    args = analyseur.parse_args()

    if args.projet is None:
        raise SystemExit(_code_banc)

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
