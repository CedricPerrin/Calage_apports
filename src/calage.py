# -*- coding: utf-8 -*-
"""
Boucle de calage sequentiel : l'assemblage de toute la chaine.

Ce module realise la procedure du § 1.6 de la note methodologique : pour
chaque apport, de l'amont vers l'aval, estimer, calculer, comparer a la
cible, corriger, repeter jusqu'a concordance, puis verifier la coherence
des sections amont avant de passer au suivant.

Il est INDEPENDANT du code de calcul hydraulique. Il ne connait du modele
qu'une interface a quatre methodes (classe Modele ci-dessous), ce qui a deux
consequences :

  - la boucle se teste ENTIEREMENT sans HEC-RAS, sur un modele fictif dont on
    connait la reponse exacte. C'est ce que fait l'auto-test de ce fichier ;
  - un autre code hydraulique se branche en ecrivant une seule classe.

La declinaison HEC-RAS est dans pilote_hecras.py.

SIMPLIFIE LE 07/08/2026 (methode manuelle validee, hypothese « section de
controle proche du point d'apport », § 1.2 de la note) : correction
directe a UN SEUL TERME, decalage temporel Δt mesure une seule fois sur le
calcul de reference (pic contre pic) puis fige, aucun dephasage de reponse φ
mesure separement (equivaut a φ = 0), aucun plancher de volume calcule a
l'avance, aucun gain hydraulique mesure. C'est EXACTEMENT la methode manuelle
verifiee dans le classeur de reference, SUR TOUTE LA DUREE SIMULEE — l'apport
injecte n'est jamais force a zero hors d'une fenetre :

    apport(n+1)(t) = max(0, apport(n)(t) + [cible(t - Δt) - section(t)])

Les versions anterieures portaient EN PLUS un second algorithme (« mode par
defaut » : correction a deux termes volume + pointe, region de confiance
adaptative, recherche de pas exhaustive) et des raffinements (dephasage de
reponse φ mesure par correlation croisee, plancher de volume irreductible,
fenetre d'injection qui forcait en plus l'APPORT a zero hors d'elle) — chacun
documente, mesure, et utile dans le cas qui l'a motive, mais qui triplaient
la taille de ce fichier pour un usage que la methode manuelle ne couvre pas.
Ce choix est assume : sur un troncon qui lamine ou ecrete fortement (gain
hydraulique loin de 1), cette version simplifiee convergera plus lentement,
voire pas du tout, la ou l'ancien mode par defaut savait s'adapter. Ce n'est
plus dans le perimetre de ce module.

LA FENETRE DE L'EVENEMENT PRINCIPAL (fenetre_injection(), reintroduite le
07/08/2026 dans une version plus etroite) reste, elle : elle restreint le
JUGEMENT (diagnostiquer(), concordance()) et la PRESENTATION des resultats
(series comparees dans le rapport final) a la crue calee, exactement comme
avant — une mini-crue isolee ou une longue traine de debit de base, dans la
donnee d'entree, ne doit ni gonfler ni degrader le verdict ni la figure
montree a l'ingenieur. Elle ne force en revanche plus l'apport injecte a
zero en dehors d'elle : celui-ci reste calcule sur toute la serie, comme
dans le classeur de reference.

CORRECTIF DE FOND APPORTE PAR CETTE MEME SIMPLIFICATION (pas seulement une
reduction de code) : ecart_a_la_cible() decale desormais la CIBLE de -Δt
pour la comparer au calcul, la ou l'ancien calcul_rephase() decalait le
CALCUL de +Δt pour le comparer a la cible. Les deux ecritures ne sont PAS
equivalentes point a point (l'une est l'autre translatee de Δt) : verifie
contre les 4 blocs du classeur de reference, l'ancienne convention s'ecartait
de 68 % du pic cible des que Δt atteignait 0,7 h (14 pas de temps), quand la
nouvelle correspond au classeur a la precision numerique pres (< 0,1 % du pic,
sur les quatre apports). Ce n'etait pas un defaut introduit par la
simplification : l'ancien calcul_rephase() portait cette meme convention
depuis avant elle, jamais confronte au classeur avant maintenant.

Usage :  python calage.py        (calage complet sur un modele fictif)
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from criteres import diagnostiquer, reserve_identifiabilite

# NOMS DES ETAPES DU CALAGE. Ils ne servent pas qu'a l'affichage : le modele
# les reprend tels quels pour titrer ce qu'il conserve — sous HEC-RAS, un plan
# et un unsteady flow par etape. On relit donc plus tard « Apport_A2 » dans le
# gestionnaire de plans sans avoir a deviner quel numero correspond a quoi.
ETAPE_SANS_APPORT = "sans apport"
PREFIXE_ETAPE_APPORT = "Apport_"
# ETAT FINAL, TOUS LES APPORTS CALES. Il existait deja : c'est le plan de la
# DERNIERE etape d'apport, qui porte tous les apports cales ET leurs
# resultats — la verification globale se borne a le relire. Rien ne le
# distinguait d'une etape intermediaire : il fallait savoir de tete quel
# apport etait le dernier pour retrouver l'etat complet. Voir Modele.conclure :
# on le RETITRE, on ne le clone pas.
# « avec apports » et non « avec_apports » : il fait la paire avec
# « sans apport » dans le gestionnaire de plans, et celui-la ne peut pas
# changer sans rendre etrangers les plans des calages deja faits.
ETAPE_AVEC_APPORTS = "avec apports"

# LONGUEUR MAXIMALE D'UN TITRE D'ETAPE. Borne DE FICHIER, pas d'affichage :
# elle vaut pour le champ « Short Identifier » du plan, dont RAS Mapper fait
# le NOM DU DOSSIER DE RESULTATS (documentation USACE : le sous-repertoire des
# cartes stockees est « labeled the same name as the RAS Plan Short ID »).
#
# MESUREE, PAS DEVINEE. Releve sur les 103 fichiers .pXX de 01-cas_test/ :
#   - largeur du champ : 64 sur les 67 plans ecrits par l'interface HEC-RAS,
#     24 sur les 34 ecrits par cette chaine, 17 et 22 sur deux clones bruts
#     de ras-commander. Trois largeurs coexistent dans des projets qui
#     s'ouvrent : le format n'impose donc aucune largeur fixe ;
#   - contenu utile : 14 plans DEPASSENT 24, jusqu'a 30 caracteres, ecrits ET
#     calcules par l'interface (leurs .bXX sont la).
# 30 est donc un PLANCHER DEMONTRE. Le tampon reel est probablement 64
# (l'interface bourre a cette largeur sur 67 plans sur 67), mais aucun
# document USACE ne publie de limite, et l'essai n'a pas ete fait. On ne
# suppose pas. POUR RELEVER : ouvrir un plan dans HEC-RAS, taper 40
# caracteres dans « Short ID », enregistrer, relire la ligne
# « Short Identifier= » du .pXX. Une seule constante a changer.
#
# LE 24 D'AVANT N'ETAIT PAS UNE LIMITE DE HEC-RAS mais une convention de
# ras-commander (RasPlan.set_shortid, clone_plan, update_flow_title) que
# _renommer_plan avait reprise — et sur notre chemin elle n'etait meme pas
# contraignante, jalonner() reecrivant les trois lignes derriere le clonage.
# La seule troncature qui atteignait le fichier etait la notre.
#
# CE QU'ELLE COUTAIT : une troncature MUETTE, et elle frappait deja. Un plan
# de reprise du depot porte « Plan Title=sans apport XXX et aval » (25,
# intact) et « Short Identifier=sans apport XXX et ava » (24, le « l » de
# « aval » perdu). Avec un prefixe le degat change de nature : six etapes de
# 26 caracteres se reduiraient TOUTES au meme identifiant, donc au meme
# dossier de resultats — le doublon meme que le prefixe supprime.
# On REFUSE, avant le premier calcul.
LONGUEUR_MAX_TITRE_PLAN = 30

# Separateur pose entre le prefixe de scenario et le nom d'etape.
SEPARATEUR_PREFIXE = "-"


def titre_etape(nom, prefixe=""):
    """
    Titre porte par le plan et l'unsteady d'une etape.

    SEUL ENDROIT OU UN TITRE D'ETAPE EST FABRIQUE, et seul qui verifie sa
    longueur. etape_apport() passe par lui ; controle_donnees l'appelle pour
    juger le classeur, pont_hecras pour juger la reprise. Une seule regle,
    jamais deux qui divergent.

    POURQUOI UN PREFIXE. jalonner() REMPLACE le plan homonyme d'un calage
    precedent — sans quoi le gestionnaire de plans porterait deux
    « Apport_A1 » dont rien ne dirait lequel fait foi. Consequence non
    voulue : caler le Q10 apres le Q100 sur le meme modele detruisait les
    plans du Q100 un par un, en silence, puisque les deux calages titrent
    leurs etapes pareil. Le prefixe rend les deux series etrangeres.

    LE SEPARATEUR EST POSE ICI, PAS LAISSE A LA SAISIE : « Q100 » et « Q100- »
    doivent rendre le MEME titre. _remplacer_homonymes et plan_par_titre
    comparent le « Plan Title » caractere pour caractere ; deux ecritures du
    meme prefixe donneraient des plans non homonymes, que rien ne
    remplacerait ni ne retrouverait — le doublon meme que le prefixe
    supprime. Un prefixe finissant deja par « - » ou « _ » garde le sien : on
    ne reecrit pas ce que l'utilisateur a tape.

    PREFIXE VIDE = LE COMPORTEMENT D'AVANT, AU CARACTERE PRES.
    """
    prefixe = str(prefixe or "").strip()
    if not prefixe:
        titre = str(nom)
    else:
        separateur = "" if prefixe[-1] in "-_" else SEPARATEUR_PREFIXE
        titre = f"{prefixe}{separateur}{nom}"
    if len(titre) > LONGUEUR_MAX_TITRE_PLAN:
        raise ValueError(
            f"titre d'etape « {titre} » : {len(titre)} caracteres pour "
            f"{LONGUEUR_MAX_TITRE_PLAN} tenables. Raccourcir le prefixe de "
            f"scenario de {len(titre) - LONGUEUR_MAX_TITRE_PLAN} caractere(s) "
            f"au moins, ou le nom de l'apport. Tronquer donnerait le meme "
            f"« Short Identifier » a plusieurs plans, donc le meme dossier de "
            f"resultats sous RAS Mapper.")
    return titre


def etape_apport(nom_apport, prefixe=""):
    """Nom de l'etape de calage d'un apport : « Apport_A1 » pour « A1 »."""
    return titre_etape(f"{PREFIXE_ETAPE_APPORT}{nom_apport}", prefixe)


# ---------------------------------------------------------------------------
# Interface avec le modele hydraulique
# ---------------------------------------------------------------------------


@dataclass
class ResultatCalcul:
    """Ce que la boucle a besoin de savoir d'un calcul qui vient de tourner."""
    reussi: bool
    duree_s: float = 0.0
    bilan_masse_pct: float = float("nan")
    courant_max: float = float("nan")
    message: str = ""


class Modele:
    """
    Interface minimale attendue d'un modele hydraulique.

    Quatre methodes seulement. Tout ce qui touche au format des fichiers, au
    lancement du solveur ou a la lecture des resultats appartient a
    l'implementation, jamais a la boucle.
    """

    def preparer(self):
        """Etat de depart : clonage du plan de travail, activation des sorties."""
        raise NotImplementedError

    def jalonner(self, etape):
        """
        Ouvre une nouvelle etape de calage sous ce nom.

        Facultatif, et sans effet par defaut : la boucle marche sans. Un modele
        qui sait conserver une trace bascule ici sur un jeu de fichiers neuf
        portant ce nom, de sorte que l'etape precedente reste relisible telle
        qu'elle s'est terminee. C'est ce que fait PiloteHecRas, avec un plan et
        un unsteady flow par etape.
        """
        return None

    def conclure(self, etape):
        """
        Titre sous ce nom l'etat FINAL : tous les apports cales.

        Facultatif, et sans effet par defaut. Appele une seule fois, apres la
        verification globale, quand la sequence est allee jusqu'au bout.

        CE N'EST PAS UN JALON DE PLUS. jalonner() ouvre une etape NEUVE : il
        clone, et un clone n'a pas de resultats. L'etat final, lui, est deja
        calcule — c'est le dernier calcul, celui que la verification globale
        vient de relire section par section. Il n'y a rien a cloner ni a
        recalculer : il n'y a qu'a le TITRER pour ce qu'il est.

        Retourne un compte rendu affichable, ou None.
        """
        return None

    def limiter_duree(self, heures):
        """
        Raccourcit la fenetre de simulation de l'etape COURANTE a « heures »
        depuis son debut. Facultatif, et sans effet par defaut.

        POURQUOI C'EST LEGITIME. Un solveur qui marche dans le temps ne peut
        pas voir l'avenir : la serie lue a une section sur [0, T] est la meme,
        que le calcul s'arrete a T ou bien plus tard. Tronquer ne change donc
        rien a ce qu'on lit AVANT la troncature.

        POURQUOI CELA VAUT LA PEINE. Le cout d'un calcul est a peu pres
        proportionnel a la duree simulee, et les evenements s'allongent vers
        l'aval : sur un modele reel a douze apports, la premiere section a
        fini de reagir en 8 h quand la derniere en demande 34. Imposer 34 h a
        tout le monde double le cout du calage.

        RENDRE None NE FAIT RIEN, et c'est le bon defaut : un modele qui ne
        sait pas raccourcir sa fenetre calcule simplement comme avant.
        """
        return None

    def forme_apport(self, nom_apport):
        """Hydrogramme de reference de cet apport : (temps_h, debit)."""
        raise NotImplementedError

    def appliquer_facteur(self, nom_apport, facteur):
        """
        Applique un facteur multiplicatif a l'hydrogramme de reference.

        Toujours a partir de l'hydrogramme D'ORIGINE, jamais du precedent :
        les formats de fichier quantifient les valeurs, et remettre a l'echelle
        un resultat deja quantifie accumulerait l'erreur.
        """
        raise NotImplementedError

    def definir_forme(self, nom_apport, temps_h, debits):
        """
        Remplace l'hydrogramme de reference d'un apport.

        C'est le chemin normal de la correction additive : le nouvel apport
        n'est pas un multiple de l'ancien, c'est une serie neuve, calculee
        point par point.
        """
        raise NotImplementedError

    def calculer(self):
        """Lance le solveur. Retourne un ResultatCalcul."""
        raise NotImplementedError

    def lire_section(self, nom_section):
        """Hydrogramme calcule a une section : (temps_h, debit)."""
        raise NotImplementedError


@dataclass
class Configuration:
    """Reglages de la recherche."""
    nb_max_essais: int = 6
    # QUALITE NUMERIQUE DU CALCUL, ET NON ECART A LA CIBLE : c'est le
    # « volume accounting error » que HEC-RAS rend lui-meme (colonne
    # « Error Percent »), soit ce qu'il perd ou fabrique entre ce qui entre,
    # ce qui sort et ce qui est stocke. Il ne dit RIEN de la concordance avec
    # l'hydrogramme cible — celle-la se juge par tolerance_volume / _pic /
    # r_min. Un calcul dont la conservation derive est REJETE : corriger un
    # apport dessus reviendrait a compenser une erreur du solveur.
    # 1,0 % jusqu'au 30/08/2026, releve a 5,0 % : sur un modele reel, un
    # calcul par ailleurs sain rendait 1,119 % et arretait le calage des le
    # premier apport. VALEUR A FONDER SUR SOURCES (USACE, SOP) — voir
    # STATUT.txt, « SEUIL DE BILAN DE MASSE ».
    bilan_masse_max_pct: float = 5.0
    # Tolerance sur le VOLUME. La concordance exige en plus la pointe et la
    # forme : un volume juste avec une pointe fausse serait non conservatif
    # pour une etude d'alea.
    tolerance_volume: float = 0.05
    # CONCORDANCE DEMANDEE : volume, debit de pointe ET forme.
    # Le pic a sa propre tolerance : le KGE l'agrege avec le reste et peut
    # rester bon alors que la pointe est franchement fausse — mesure sur un
    # cas reel, KGE 0,97 pour un pic a 53 % de la cible.
    tolerance_pic: float = 0.02
    # Correlation minimale APRES recalage temporel : c'est la forme, sans la
    # dynamique, qu'on exige de reproduire.
    r_min: float = 0.97
    # AJUSTER LA DUREE SIMULEE A CE QUE CHAQUE APPORT DEMANDE.
    #
    # La fenetre de jugement dit jusqu'ou l'evenement de CET apport est
    # regarde ; au-dela, plus rien n'est ni juge ni presente. Simuler plus
    # loin ne sert donc qu'a payer du temps de calcul. Les evenements
    # s'allongeant vers l'aval, une fenetre unique impose a tous le besoin du
    # dernier : mesure sur un modele a douze apports, 8 h suffisent au premier
    # quand le dernier en demande 34 — 41 % du calage depense pour rien.
    #
    # TROIS GARDE-FOUS, ET AUCUN N'EST FACULTATIF :
    #   - la duree ne DECROIT jamais d'un apport au suivant. L'etape 7 relit
    #     les sections amont, et la verification globale finale relit LE
    #     DERNIER CALCUL pour TOUTES les sections : raccourcir apres coup les
    #     priverait de leur fenetre ;
    #   - elle ne DEPASSE jamais celle du plan de reference. On raccourcit, on
    #     n'allonge pas : allonger demanderait des hydrogrammes plus longs que
    #     ce que le modele porte ;
    #   - marge_duree_h est ajoutee au-dela de la fenetre de jugement, parce
    #     que celle-ci est detectee sur l'ecart au residuel et qu'un apport
    #     corrige peut deplacer un peu la reponse.
    # Le calcul de REFERENCE garde toujours la fenetre entiere : il mesure le
    # residuel de toutes les sections a la fois.
    ajuster_duree: bool = True
    marge_duree_h: float = 2.0
    controle_amont: bool = True
    # PREFIXE DE SCENARIO POSE DEVANT CHAQUE TITRE D'ETAPE (voir titre_etape).
    # Vide = les titres d'avant : « sans apport », « Apport_A1 ». « Q100 »
    # donne « Q100-sans apport », « Q100-Apport_A1 », « Q100-avec apports ».
    # Sans lui, caler le Q10 apres le Q100 sur le meme modele efface les plans
    # du Q100 : jalonner() remplace les homonymes, et les deux calages titrent
    # leurs etapes pareil.
    prefixe_etape: str = ""

    # ------------------------------------------------------------------
    # FENETRE DE L'EVENEMENT PRINCIPAL. Restreint le JUGEMENT (diagnostiquer,
    # concordance) et la PRESENTATION des resultats (series comparees dans le
    # rapport) a la crue calee — jamais l'apport injecte lui-meme, qui reste
    # calcule sur toute la serie (voir fenetre_injection() et le docstring du
    # module). Les bornes se deduisent du volume cumule de l'ecart a l'etat
    # sans apport, disponible des l'iteration 0, sans aucun calcul
    # supplementaire.
    # ------------------------------------------------------------------
    # None ou True = active (defaut). False = aucune fenetre, le jugement et
    # les series presentees portent alors sur toute la duree simulee.
    fenetre_active: bool = None
    fenetre_seuil_bas: float = 0.005     # t0 : 0,5 % du volume cumule
    fenetre_seuil_haut: float = 0.99     # tf : 99 % du volume cumule
    # Bornes imposees a la main, en heures. None = detection automatique.
    fenetre_t0_h: float = None
    fenetre_tf_h: float = None
    # Marge fixe ajoutee de chaque cote de la fenetre detectee (ou imposee),
    # pour laisser de la place a l'oeil plutot que de couper au plus juste.
    fenetre_marge_h: float = 1.0

    # Il n'y a PLUS de champ « mode_rapide » ni « lissage_deficit » : depuis
    # le 07/08/2026 caler() ne connait qu'un seul algorithme de correction, et
    # le deficit n'est plus lisse. Les cellules correspondantes ont ete
    # retirees du gabarit ; un classeur ancien qui les porte encore n'est pas
    # en erreur pour autant — pont_hecras.py ne les lit tout simplement plus.


@dataclass
class ResultatApport:
    """Ce qui est retenu pour un apport a la fin de sa recherche."""
    nom_apport: str
    nom_section: str
    valide: bool
    facteur: float
    diagnostic: object = None
    essais: int = 0
    duree_s: float = 0.0
    motif: str = ""
    historique: list = field(default_factory=list)
    # Conserve pour compatibilite (suivi.py, livrables.py) : plus jamais
    # calcule depuis la simplification du 07/08/2026, toujours None.
    fenetre_principale: tuple = None
    # PART DE L'APPORT DANS LE DEBIT DE POINTE A SA SECTION, mesuree a
    # l'iteration 0. Repassee a la verification finale : diagnostics_finaux
    # sont RECALCULES par diagnostiquer(), une reserve ajoutee ici s'y
    # perdrait — elle renait du nombre, par la meme regle
    # (criteres.reserve_identifiabilite). None = inconnue.
    part_apport: float = None


@dataclass
class ResultatCalage:
    """Resultat d'ensemble."""
    apports: list = field(default_factory=list)
    diagnostics_finaux: list = field(default_factory=list)
    # Series (temps_cible, debit_cible, temps_calcule, debit_calcule) de la
    # verification globale finale, alignees sur diagnostics_finaux. Necessaires
    # pour tracer les figures de comparaison du rapport final : un Diagnostic
    # seul ne contient que des indicateurs (r, rapports de volume et de pointe), pas
    # les courbes elles-memes.
    series_finales: list = field(default_factory=list)
    config: object = None
    duree_s: float = 0.0
    nb_calculs: int = 0
    conforme: bool = False
    motif: str = ""
    # ALERTES QUI NE VISENT AUCUN APPORT EN PARTICULIER mais le calage entier.
    # Diagnostic.alertes est par apport ; il n'y avait aucun canal pour ce qui
    # se constate sur l'ENSEMBLE des sections — la coherence du decalage le
    # long de l'axe, par exemple. Non bloquantes par construction : elles
    # n'entrent pas dans conforme, qui reste l'affaire des diagnostics.
    alertes_chaine: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Controle de qualite numerique
# ---------------------------------------------------------------------------


def qualite_acceptable(resultat, config):
    """
    Un calcul numeriquement douteux est REJETE, pas compare a la cible.

    Comparer un essai dont la conservation derive reviendrait a corriger un
    apport pour compenser une erreur du solveur.

    Retourne (acceptable, motif).
    """
    if not resultat.reussi:
        return False, f"le calcul a echoue : {resultat.message}"
    bilan = resultat.bilan_masse_pct
    if np.isfinite(bilan) and abs(bilan) > config.bilan_masse_max_pct:
        return False, (f"bilan de masse {bilan:+.3f} % au-dela de "
                       f"{config.bilan_masse_max_pct} % admis")
    return True, ""


# ---------------------------------------------------------------------------
# Correction ADDITIVE de l'hydrogramme d'apport
#
# Un coefficient multiplicatif n'agit que sur l'AMPLITUDE : il peut amener le
# volume a la cible, jamais corriger la forme ni le debit de pointe si la
# forme differe. La correction point par point n'a pas ce defaut : elle
# ajoute exactement ce qui manque, la ou cela manque.
# ---------------------------------------------------------------------------


def _volume(temps, debits):
    """Volume ecoule, en unites coherentes avec les debits fournis."""
    return float(np.trapezoid(np.asarray(debits, dtype=float),
                              np.asarray(temps, dtype=float)))


def _facteur_retenu(historique, essai_en_place):
    """
    Rapport de volume de l'essai EFFECTIVEMENT en place a la fin.

    Quand la recherche revient a un essai anterieur, le dernier enregistrement
    de l'historique decrit un apport qui n'est plus dans le modele. Rapporter
    ce chiffre ferait mentir le tableau des apports sur ce qui a ete livre.
    """
    if not historique:
        return 0.0
    for essai in historique:
        if essai["essai"] == essai_en_place:
            return essai["facteur"]
    return historique[-1]["facteur"]


def corriger_apport(apport, manque):
    """
    Nouvel hydrogramme d'apport, corrige DIRECTEMENT du manque mesure a la
    section.

        apport(n+1)(t) = max(0, apport(n)(t) + manque(t))

    C'est la methode manuelle telle que verifiee dans le classeur de
    reference : aucun coefficient de gain, aucune region de confiance,
    aucune recherche de pas — l'ecart lui-meme EST la correction. Elle
    suppose un troncon transparent (gain hydraulique proche de 1, section de
    controle proche du point d'apport) : voir le docstring du module.

    LE PLANCHER A ZERO EST LA SEULE CONTRAINTE. Un apport negatif serait un
    prelevement, que la methode ne prevoit pas et que HEC-RAS refuserait ici.
    Tout le reste est libre : l'apport n'est pas un hydrogramme observe mais
    la commande d'un asservissement, il peut varier brutalement d'un pas au
    suivant, seul le debit obtenu A LA SECTION est juge.

    Ce plancher rend la correction UNIDIRECTIONNELLE la ou l'apport vaut deja
    zero : la ou la section donne deja plus que la cible, le manque est
    negatif et n'est pas compense — un apport ne sait qu'ajouter du debit. Le
    volume final ne peut donc pas descendre sous la cible augmentee de cet
    exces residuel. C'est une consequence de la physique, pas de ce code.
    """
    return np.maximum(np.asarray(apport, dtype=float)
                      + np.asarray(manque, dtype=float), 0.0)


def _temps_du_pic(t, q):
    """
    Heure du pic de q(t) : l'instant de la grille ou q est maximal.

    TOUJOURS UN POINT DE LA GRILLE, jamais une position sous-pas. Un
    raffinement parabolique y a ete essaye puis retire : deux series dont
    les maxima discrets tombent au MEME pas (decalage nul, au sens de
    criteres._decalage_pas) pouvaient quand meme rendre un decalage
    sous-pas des que leurs points voisins etaient asymetriques — un
    decalage que rien, cote HEC-RAS ou lecture manuelle, ne peut produire
    ni verifier.

    None si la serie est plate (aucun pic n'y est identifiable) : c'est a
    l'appelant de le dire, jamais d'en fabriquer un.
    """
    t = np.asarray(t, dtype=float)
    q = np.asarray(q, dtype=float)
    if q.size < 3 or float(np.ptp(q)) <= 1e-9 * max(1.0, float(np.max(np.abs(q)))):
        return None
    return float(t[int(np.argmax(q))])


def decalage_minimisant_ecart(temps_cible, debit_cible,
                              temps_calcule, debit_calcule):
    """
    Decalage temporel qui ALIGNE LE PIC du calcul sur celui de la cible.

    MEME CRITERE QUE criteres._decalage_pas, dont se sert diagnostiquer().
    Les deux doivent rester d'accord : c'est la meme grandeur, mesuree pour
    deux usages.

    ANCRE SUR LE PIC, ET NON SUR UN MINIMUM D'ECART GLOBAL. Le residuel
    compare ici (apports amont deja cales, apport courant a zero) n'a
    generalement pas la meme forme que la cible — il lui manque justement ce
    que l'apport courant doit fournir. Un ajustement par moindres carres sur
    la serie entiere peut alors se caler sur la queue de decrue ou le debit
    de base plutot que sur l'evenement, et rendre un decalage sans rapport
    avec le temps de transfert reel. Le pic, lui, reste identifiable meme
    quand tout le reste diverge : c'est le reperage qu'un operateur fait a
    l'oeil, en lisant l'heure du pic obtenu dans le logiciel de calcul et en
    la comparant a celle du pic cible (§ 1.4 de la note methodologique).

    MESURE UNE SEULE FOIS PAR APPORT, sur le calcul de reference (apports a
    zero), puis figee pour tous les essais suivants — voir caler(). C'est
    exactement le geste manuel : lire l'heure du pic une fois, ne plus y
    revenir.

    AUCUNE BORNE ARTIFICIELLE SUR L'AMPLITUDE : le decalage retenu est
    exactement t_pic_calcule - t_pic_cible, quelle que soit sa valeur. Un
    ecrasement vers une fraction de la duree de la serie fabriquait un
    decalage qui n'etait ni la mesure brute ni un temps de transfert
    plausible — et le calage batissait TOUS ses essais dessus, puisque le
    decalage est mesure une fois puis fige. Mesure sur un cas reel : -2,49 h
    rendus au lieu de -3,3 h, et l'essai 1 partait a 3 469 738 % du volume
    cible.

    CE DECALAGE N'EST PLUS JUGE NULLE PART (08/08/2026). Il est mesure,
    rapporte, et sert a la soustraction ; aucun seuil ne s'y applique. Voir
    criteres.Diagnostic.converge pour ce qui a ete retire et pourquoi.

    Retourne le decalage en heures. Positif = le calcul est EN RETARD.
    Rend 0.0 si l'une des deux series est plate — meme garde-fou qu'avant
    (section muette, debit constant) : decaler une serie plate ne change
    rien, et un decalage imaginaire ne ferait que brouiller le journal.
    """
    t_c = np.asarray(temps_cible, dtype=float)
    q_c = np.asarray(debit_cible, dtype=float)
    t_s = np.asarray(temps_calcule, dtype=float)
    q_s = np.asarray(debit_calcule, dtype=float)

    t_pic_c = _temps_du_pic(t_c, q_c)
    t_pic_s = _temps_du_pic(t_s, q_s)
    if t_pic_c is None or t_pic_s is None:
        return 0.0
    return t_pic_s - t_pic_c


def ecart_a_la_cible(temps_cible, debit_cible, temps_calcule, debit_calcule,
                     decalage_h):
    """
    Ce qui MANQUE a la section : cible(t - Δt) - section(t).

    C'est la formule verifiee dans le classeur de reference
    (Example_manuel_methodo.xlsx), au sens pres : on decale la CIBLE de
    -Δt, PAS le calcul. Les deux ne sont pas interchangeables des que Δt
    n'est plus negligeable devant la vitesse de variation de l'hydrogramme.
    Verifie sur le classeur : decaler le calcul plutot que la cible reste
    proche de rien quand Δt vaut un seul pas de temps (0,05 h), mais s'ecarte
    de 68 % du pic cible des que Δt atteint 0,7 h (14 pas) — ce n'est pas
    une seconde ecriture equivalente d'un meme decalage, ce sont deux courbes
    differentes, l'une etant l'autre translatee de Δt.

    Le point decisif, commun aux deux ecritures : on ne soustrait pas les
    deux hydrogrammes tels quels. Entre l'apport et la section il y a un
    temps de propagation ; la difference brute contient alors un lobe
    positif ET un lobe negatif qui ne traduisent qu'un DEPHASAGE, pas un
    defaut de volume ni de forme. Reinjecter cela dans l'apport revient a
    lutter contre le temps de propagation.

    C'est la MEME fonction qui sert a l'estimation initiale (apport a zero)
    et a la correction de chaque essai suivant : c'est la meme grandeur,
    mesuree au meme endroit, et il n'y a aucune raison d'avoir deux chemins
    de calcul pour elle.

    HORS DE LA PLAGE OU LES DEUX SERIES SONT CONNUES, L'ECART EST NUL — pas
    « egal a la cible ». np.interp() ne refuse pas une abscisse hors domaine :
    il PLAFONNE a la premiere (ou derniere) valeur de la serie, ce qui
    fabriquerait un ecart la ou rien n'a ete mesure.
    """
    t_cible = np.asarray(temps_cible, dtype=float)
    q_cible = np.asarray(debit_cible, dtype=float)
    t_calc = np.asarray(temps_calcule, dtype=float)
    q_calc = np.asarray(debit_calcule, dtype=float)

    lu_cible = t_cible - float(decalage_h)
    cible_decalee = np.interp(lu_cible, t_cible, q_cible)
    dans_cible = (lu_cible >= t_cible[0]) & (lu_cible <= t_cible[-1])

    calc_aligne = np.interp(t_cible, t_calc, q_calc)
    dans_calc = ((t_cible >= t_calc[0]) & (t_cible <= t_calc[-1])
                if t_calc.size else np.zeros(t_cible.shape, dtype=bool))

    return np.where(dans_cible & dans_calc, cible_decalee - calc_aligne, 0.0)


def cliquet_volume(temps_cible, debit_cible, manquant, decalage_h,
                   fenetre=None):
    """
    Rapport de volume MINIMAL que la section peut atteindre — le cliquet.

    UN APPORT NE SAIT QU'AJOUTER DU DEBIT (plancher a zero, cf.
    corriger_apport). La ou la section donne DEJA plus que la cible sans cet
    apport, l'exces est irreductible : aucun essai ne le retirera. Le rapport
    de volume ne peut donc pas redescendre sous

        1 + (volume de l'exces residuel) / (volume de la cible)

    Ce n'est pas un reglage, c'est une consequence de la physique — la meme
    que le § « Le plancher a zero, et le cliquet qui en decoule » de la note.

    MESURE SUR CE QUE LA CHAINE CALCULE DEJA, ET NE COUTE AUCUN CALCUL :
    « manquant » est l'ecart rendu par ecart_a_la_cible() au calcul de
    reference, et l'exces en est simplement la part negative. Aucune seconde
    interpolation, aucune seconde regle de decalage — cible_decalee est
    obtenu par le MEME appel, avec un calcul nul, pour que le denominateur
    soit exactement la cible que le numerateur suppose.

    CE QUE LE CAS TOTAL NE COUVRAIT PAS. caler() refuse deja une cible
    ENTIEREMENT sous le residuel (max(manquant) <= 0). Entre les deux, il y a
    le cas ordinaire : la cible est atteignable a la pointe, mais le residuel
    la depasse sur une partie de la fenetre — assez pour bloquer le volume
    au-dessus de sa bande. Le calage depensait alors tous ses essais a
    poursuivre un rapport de volume que sa propre methode lui interdit
    d'atteindre, et finissait « non conforme » sans jamais dire pourquoi.

    fenetre : (t0, tf) — la fenetre jugee. Le cliquet se mesure la ou le
    volume se juge, sinon il annonce un plancher sur une duree que personne
    ne regarde.

    UNE ESTIMATION, PAS UNE BORNE DEMONTREE. Elle suppose le residuel
    INCHANGE par l'ajout de l'apport — l'hypothese de troncon transparent, la
    meme sur laquelle la correction elle-meme repose (§ 1.2 de la note). Un
    modele qui repond non lineairement s'en ecarte un peu : mesure au banc,
    un cliquet annonce a 109,8 % pour un calage qui s'arrete a 109,6 %. Deux
    dixiemes de point, quand l'enjeu est de savoir si l'on est a 100 ou a 110.
    D'ou « environ » dans le message, et une alerte qui ne bloque rien.

    Rend 1,0 quand rien ne depasse : le calage peut atteindre 100 %.
    """
    t_cible = np.asarray(temps_cible, dtype=float)
    exces = np.maximum(-np.asarray(manquant, dtype=float), 0.0)
    # LE MEME CHEMIN DE CALCUL QUE L'ECART, avec un calcul nul : ce qui reste
    # est la cible decalee, exactement celle a laquelle « manquant » se
    # rapporte.
    cible_decalee = ecart_a_la_cible(t_cible, debit_cible,
                                     t_cible, np.zeros_like(t_cible),
                                     decalage_h)
    if fenetre is not None:
        dedans = (t_cible >= float(fenetre[0])) & (t_cible <= float(fenetre[1]))
        if dedans.sum() >= 2:
            t_cible, exces, cible_decalee = (t_cible[dedans], exces[dedans],
                                             cible_decalee[dedans])
    volume_cible = _volume(t_cible, cible_decalee)
    if volume_cible <= 0.0:
        return 1.0
    return 1.0 + _volume(t_cible, exces) / volume_cible


def fenetre_injection(temps, ecart, seuil_bas=0.005, seuil_haut=0.99,
                      t0_impose=None, tf_impose=None,
                      volume_reference=None, perte_max=None):
    """
    Bornes (t0, tf) de l'evenement PRINCIPAL, en heures.

    REINTRODUITE LE 07/08/2026, pour un usage plus etroit qu'avant la
    simplification : elle restreint desormais le JUGEMENT (diagnostiquer(),
    et la PRESENTATION des resultats — series comparees dans le rapport) a
    la crue calee, mais ne force plus l'apport a zero en dehors (voir le
    docstring du module). Une mini-crue anterieure ou un residu de fin de
    serie, dans la donnee d'entree, ne doit ni gonfler ni degrader le
    verdict de volume / pointe / forme qui juge chaque essai, ni la figure
    de comparaison montree a l'ingenieur — mais l'apport, lui, reste
    calcule sur toute la serie, exactement comme la methode manuelle.

    `ecart` est le manque a la section pour l'etat SANS APPORT
    (cible - residuel), disponible des l'iteration 0 : la fenetre ne coute
    donc aucun calcul.

    LE CUMUL PORTE SUR LA PART POSITIVE de l'ecart, pas sur l'ecart brut. Un
    ecart brut change de signe des que la section depasse la cible quelque
    part ; son cumul n'est alors plus croissant, et « le pas de temps ou l'on
    atteint 99 % du volume » n'y designe plus rien d'unique. La part positive,
    elle, est exactement ce qu'un apport peut combler — et c'est la grandeur
    dont on cherche les bornes.

    ASYMETRIE ASSUMEE : t0 capte large, tf coupe franc. Trop large ne coute
    rien — hors evenement, l'ecart y est quasi nul ; trop etroit exclurait a
    tort une partie du jugement sur la crue elle-meme.

    t0_impose / tf_impose : bornes fixees a la main, en heures. Elles
    REMPLACENT la detection, qui n'est qu'une proposition.

    `volume_reference` (le volume de la cible) et `perte_max` bordent les deux
    seuils : ils ne peuvent qu'ELARGIR la fenetre, jamais la retrecir.

    CE QU'ILS BORNENT EST LE DEFICIT LAISSE DEHORS, PAS LE VOLUME — et ce
    docstring a annonce le second pendant un mois. Les deux termes du min()
    plus bas se comparent en m3, mais l'un est une part du DEFICIT cumule et
    l'autre une part du VOLUME DE LA CIBLE ; le premier est presque toujours
    le plus petit, si bien que le second ne mord jamais. Mesure du 03/09/2026
    sur ARD10 : 25 % du volume de crue hors fenetre la ou le commentaire
    promettait 2,5 %.
      LE CORRIGER ICI REVIENDRAIT A ELARGIR LA FENETRE JUGEE, donc a rendre
    non conformes des apports qu'aucune valeur d'apport ne pourrait sauver —
    un apport ne sait qu'ajouter du debit, et ce qui deborde hors fenetre est
    un EXCEDENT (invariant 11). Ce qui reste dehors est donc MESURE ET DIT,
    jamais juge : voir Diagnostic.rapport_volume_serie et part_cible_jugee,
    et la reserve non bloquante que criteres.diagnostiquer leve quand les
    deux lectures divergent.

    Retourne (t0, tf) en heures. Sur un ecart vide, nul ou entierement
    negatif, rend la fenetre COMPLETE : mieux vaut ne rien restreindre que
    restreindre au hasard.
    """
    t = np.asarray(temps, dtype=float)
    if t.size == 0:
        return (0.0, 0.0)
    t0_defaut, tf_defaut = float(t[0]), float(t[-1])

    positif = np.clip(np.asarray(ecart, dtype=float), 0.0, None)
    pas = np.diff(t) * 3600.0
    increments = 0.5 * (positif[:-1] + positif[1:]) * pas
    cumul = np.concatenate(([0.0], np.cumsum(increments)))
    total = float(cumul[-1])
    if total <= 1e-9:
        t0, tf = t0_defaut, tf_defaut
    else:
        if volume_reference and perte_max:
            # LES DEUX VOLUMES DOIVENT ETRE DANS LA MEME UNITE, et ils ne
            # l'etaient pas. « cumul » ci-dessus integre avec « pas » en
            # SECONDES, donc en m3 ; _volume(), lui, integre un temps en
            # HEURES, donc en m3/s.h — 3 600 fois plus petit. Le min() ci-
            # dessous retenait donc TOUJOURS perte_bout, exclu_haut valait
            # ~0, et tf tombait sur le dernier instant ou l'ecart est encore
            # positif : seuil_haut n'a jamais coupe quoi que ce soit en
            # production. Mesure du 31/08/2026 sur douze cibles reelles :
            # tf = 24,0 h sur la 3e section la ou 99 % du volume est atteint
            # a 13,0 h, et 81,5 h sur la 12e pour 34,5 h. Le calage simulait
            # la queue
            # numerique des cibles, pas leur crue.
            perte_bout = (0.5 * float(perte_max) * float(volume_reference)
                          * 3600.0)
            exclu_bas = min(seuil_bas * total, perte_bout)
            exclu_haut = min((1.0 - seuil_haut) * total, perte_bout)
        else:
            exclu_bas = seuil_bas * total
            exclu_haut = (1.0 - seuil_haut) * total

        t0 = (float(t[int(np.searchsorted(cumul, exclu_bas, side="left"))])
              if exclu_bas > 0 else t0_defaut)
        indice_haut = int(np.searchsorted(cumul, total - exclu_haut,
                                          side="left"))
        tf = float(t[min(indice_haut, t.size - 1)])

    if t0_impose is not None:
        t0 = float(t0_impose)
    if tf_impose is not None:
        tf = float(tf_impose)
    if not (tf > t0):
        return (t0_defaut, tf_defaut)
    return (t0, tf)


def masque_fenetre(temps, bornes):
    """Masque des instants DANS la fenetre (t0, tf), bornes comprises."""
    if bornes is None:
        return np.ones(np.asarray(temps).shape, dtype=bool)
    t = np.asarray(temps, dtype=float)
    return (t >= bornes[0] - 1e-9) & (t <= bornes[1] + 1e-9)


def ecarts_normalises(diag, config):
    """
    Les TROIS violations, chacune ramenee a sa propre tolerance.

    Retourne (volume, pointe, forme). Une composante <= 1 signifie « dans les
    clous » pour cette exigence-la ; les trois <= 1, c'est la concordance.
    Normaliser est ce qui rend comparables un demi-pour-cent de volume, deux
    pour-cent de pointe et trois centiemes de correlation.
    """
    return (
        abs(diag.rapport_volume - 1.0) / max(config.tolerance_volume, 1e-9),
        abs(diag.rapport_pic - 1.0) / max(config.tolerance_pic, 1e-9),
        max(0.0, config.r_min - diag.r) / max(1.0 - config.r_min, 1e-9),
    )


def admissible(diag, config):
    """Un essai respecte-t-il les TROIS seuils a la fois ?"""
    return max(ecarts_normalises(diag, config)) <= 1.0


def ecart_combine(diag, config):
    """
    Erreur combinee volume + pointe + forme, pour departager deux essais.

    NORME EUCLIDIENNE des trois violations normalisees, la ou le critere
    d'arret, lui, reste le MAXIMUM (concordance() : les trois seuils doivent
    etre tenus simultanement, un seul depassement suffit a refuser).

    Les deux ne jouent pas le meme role et ne peuvent pas etre le meme
    calcul. Le maximum dit « es-tu recevable ? » — il ne voit que la pire
    exigence, et se moque de ce que valent les deux autres. Il classait donc
    a egalite un essai a (1,0 ; 0,1 ; 0,1) et un essai a (1,0 ; 0,99 ; 0,99),
    qui ne se valent pourtant pas du tout. La norme euclidienne dit « et de
    combien, au total ? » : elle recompense l'essai qui rapproche des trois
    cibles a la fois, ce qui est exactement l'objectif de l'etude.
    """
    v, q, f = ecarts_normalises(diag, config)
    return float(np.sqrt(v * v + q * q + f * f))


def rang_essai(diag, config):
    """
    Cle de tri d'un essai : (non admissible, erreur combinee).

    L'ADMISSIBILITE PRIME, TOUJOURS. Un essai qui tient les trois seuils
    passe devant tout essai qui n'en tient qu'un, meme si ce dernier affiche
    une erreur combinee plus faible — un volume parfait avec une pointe hors
    seuil n'est pas un resultat d'etude d'alea. A admissibilite egale, c'est
    l'erreur combinee qui departage.
    """
    return (not admissible(diag, config), ecart_combine(diag, config))


def _progression_pic(historique):
    """
    De combien le debit de pointe a gagne au DERNIER essai, en fraction.

    Sert a distinguer, quand les essais sont epuises, une recherche qui
    plafonne d'une recherche qui avancait encore. Le second cas se regle en
    autorisant plus d'essais ; le premier, non.
    """
    if not historique or len(historique) < 2:
        return None
    dernier, precedent = historique[-1].get("pic"), historique[-2].get("pic")
    if dernier is None or precedent is None:
        return None
    if np.isnan(dernier) or np.isnan(precedent):
        return None
    return float(dernier) - float(precedent)


def concordance(diag, config):
    """
    L'OBJECTIF : que l'hydrogramme mesure a la section soit le plus proche
    possible de celui vise. Concretement, concordance simultanee du VOLUME,
    du DEBIT DE POINTE et de la FORME.

    La DYNAMIQUE est volontairement exclue — un decalage temporel n'a pas a
    etre reproduit, il est seulement surveille comme garde-fou. D'ou un
    critere sur r, qui mesure la forme APRES recalage temporel, et non sur
    le KGE brut.

    LE KGE N'EST PAS UNE CONDITION D'ARRET — et depuis le 07/09/2026 il n'est
    plus calcule. Il agregeait r, alpha et beta en un seul nombre : des trois,
    seul alpha — le rapport des ecarts-types — n'etait pas deja contraint
    ici, et le maintenir revenait a ajouter une contrainte sur la
    VARIABILITE, qui ne fait pas partie de l'objectif. « Calcule et rapporte
    comme critere d'acceptation a posteriori », il n'etait en realite lu
    nulle part.

    LE VOLUME SE LIT SUR « rapport_volume » — et « beta » n'existe plus. Les
    deux etaient proches quand les series partageaient leur base de temps, et
    seulement dans ce cas : beta, terme de biais du KGE, se calculait sur la
    grille qui ENGLOBE les deux series, tandis que rapport_volume integre sur
    la seule fenetre ou elles existent TOUTES DEUX, apres neutralisation du
    decalage. Sur un cas reel dont la simulation depassait largement la
    cible : beta = 2,613 quand le volume valait 1,040 — et c'est beta qu'une
    figure livree tracait sous le nom du volume.
    """
    return (abs(diag.rapport_volume - 1.0) <= config.tolerance_volume
            and abs(diag.rapport_pic - 1.0) <= config.tolerance_pic
            and diag.r >= config.r_min)


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------


def caler(modele, apports, sections, cibles, config=None, suivi=None,
          journal=None, etape_reference=ETAPE_SANS_APPORT):
    """
    Cale sequentiellement les apports de l'amont vers l'aval.

    apports  : noms des conditions limites d'injection, dans l'ordre.
    sections : noms des sections de controle associees, meme ordre.
    cibles   : liste de (temps_h, debit) — l'hydrogramme vise a chaque section.
    suivi    : objet Suivi facultatif. Le rapport et les figures sont alors
               reecrits a chaque apport valide, sans jamais interrompre le
               calage en cas de defaillance.
    journal  : fonction d'affichage, print par defaut.
    etape_reference : nom donne a l'etape du calcul de reference. Le defaut
               « sans apport » est exact quand la liste couvre TOUS les apports
               du modele. En reprise — les apports amont deja cales ne sont pas
               dans la liste, donc pas remis a zero — l'appelant doit fournir un
               nom qui le dise, sinon la trace conservee ment sur son contenu.
               Donne SANS le prefixe de scenario : caler() le pose lui-meme sur
               tout ce qu'il titre.

    Retourne un ResultatCalage.
    """
    config = config or Configuration()
    dire = journal if journal is not None else print
    debut = time.time()
    resultat = ResultatCalage(config=config)

    modele.preparer()

    # --- etape 0 : etat de reference, TOUS LES APPORTS A CALER MIS A ZERO --
    #
    # Sans cette passe, l'estimation initiale etait fausse deux fois :
    #   - pour le PREMIER apport, aucun residuel n'etait connu, et le facteur
    #     valait cible / forme. Or la section recoit deja le debit de tout ce
    #     qui n'est pas cale — conditions limites permanentes, affluents
    #     amont. Mesure sur un cas reel : 275 m3/s deja presents pour une
    #     cible a 551, soit plus de la moitie ignoree ;
    #   - pour les SUIVANTS, le residuel etait lu sur le dernier calcul, ou
    #     l'apport en cours valait encore 1. On retranchait donc a la cible
    #     un debit qui contenait deja une part de l'apport cherche.
    #
    # Mettre TOUS les apports a zero des le depart resout les deux : chaque
    # apport est active a son tour, si bien que le dernier calcul de l'apport
    # N est exactement l'etat « sans apport N+1 ». Le surcout est donc d'UN
    # SEUL calcul pour tout le calage, et non d'un par apport.
    # Un debit injecte nul est parfaitement admis par HEC-RAS.
    for nom in apports:
        modele.appliquer_facteur(nom, 0.0)
    _jalonner(modele, titre_etape(etape_reference, config.prefixe_etape),
              dire)
    dire("Calcul de reference : tous les apports a caler sont mis a zero, "
         "pour mesurer ce que les sections recoivent sans eux.")
    calcul = modele.calculer()
    resultat.nb_calculs += 1
    _noter_bilan(suivi, calcul, config)
    acceptable, motif_qualite = qualite_acceptable(calcul, config)
    if not acceptable:
        resultat.motif = (
            f"le calcul de reference (apports a zero) n'est pas exploitable : "
            f"{motif_qualite}. Rien ne peut etre cale sur cette base.")
        dire(f"    ARRET : {resultat.motif}")
        resultat.duree_s = time.time() - debut
        return resultat

    # TOUTES LES SECTIONS SONT LUES MAINTENANT, pas quand leur tour vient.
    #
    # Le calcul de reference est le SEUL etat ou les sections sont toutes
    # lisibles ensemble, et il vient d'avoir lieu : les eprouver ici ne coute
    # rien. Une section illisible — nom absent du modele, faute de frappe —
    # ne se manifestait qu'au moment ou son apport arrivait, c'est-a-dire
    # apres le calage complet des apports amont.
    illisibles = []
    residuels_reference = []
    for section in sections:
        try:
            t_zero, residuel_zero = modele.lire_section(section)
        except Exception as e:                              # noqa: BLE001
            illisibles.append(f"{section} ({type(e).__name__}: {e})")
        else:
            dire(f"    {section:24s} recoit {float(np.max(residuel_zero)):7.1f} "
                 f"m3/s sans les apports a caler")
            residuels_reference.append((t_zero, residuel_zero))
    if illisibles:
        resultat.motif = (
            f"section(s) de controle illisible(s) dans le calcul de "
            f"reference : {' ; '.join(illisibles)}. Verifier que ces noms "
            f"sont bien ceux des lignes de reference du modele.")
        dire(f"    ARRET : {resultat.motif}")
        resultat.duree_s = time.time() - debut
        return resultat

    # --- calendrier des durees simulees, etabli ICI et pas ailleurs -------
    #
    # TOUTES LES DUREES SE CALCULENT SUR LE CALCUL DE REFERENCE, jamais au fil
    # de la boucle. La raison est un piege que l'auto-test a attrape : dans la
    # boucle, le residuel de l'apport N se lit dans les RESULTATS de l'apport
    # N-1 — donc dans un calcul deja raccourci. Un premier apport dont
    # l'evenement finit tot tronquait le calcul a 10 h, et le suivant, dont
    # l'evenement culmine a 14 h, ne pouvait plus mesurer son propre deficit :
    # sa fenetre etait bornee par la troncature du precedent, la duree ne
    # croissait jamais, et le calage echouait sur « volume nan ».
    # Le calcul de reference, lui, porte la fenetre ENTIERE et rend toutes les
    # sections lisibles ensemble : c'est le seul etat ou le calendrier complet
    # est mesurable.
    #
    # LA DUREE AINSI OBTENUE EST CONSERVATRICE. A l'etat de reference, la
    # section N ne recoit que le debit non cale : son deficit est donc PLUS
    # GRAND qu'il ne le sera quand son tour viendra, les apports amont etant
    # alors actifs. La fenetre mesurée ici est donc plus large que necessaire —
    # on simule un peu trop, jamais trop peu.
    #
    # Δt EST DEDANS : la fenetre est mesuree sur cible(t - Δt) - section(t),
    # dont l'indice est un instant de SIMULATION. Un evenement cible qui
    # culmine a 16 h avec Δt = -13 h se lit a la section vers 3 h, et la duree
    # retenue suit le calendrier DU MODELE, pas celui de la cible.
    durees_simulees = _calendrier_durees(
        cibles, residuels_reference, config,
        dire if config.ajuster_duree else (lambda *a, **k: None))

    # A LA FIN, PAS ICI. La coherence du decalage se mesurait sur le calcul de
    # reference — « disponible 2 h 23 apres le lancement au lieu de 25 h ».
    # Mais a l'etat de reference les sections aval sont AFFAMEES : tout ce
    # qui devrait venir de l'amont manque, leur pic arrive de plus en plus
    # tard, et la mesure fabrique une derive qui grandit avec le rang (etabli
    # le 02/09/2026 ; le 04/09, sur un modele qui ne derive pas — etendue
    # 1,8 h une fois cale —, ce critere a livre au client une reserve pour
    # 7,2 h). Le seul Dt qui vaille est celui que la correction emploie :
    # mesure apport par apport, l'amont deja cale, puis fige. On le recueille
    # ici, on juge a la fin — voir _coherence_points.
    points_axe = []

    for i, (apport, section) in enumerate(zip(apports, sections)):
        temps_cible, debit_cible = cibles[i]
        if suivi is not None:
            _sans_interrompre(suivi.commencer_apport, i)
        dire(f"\n=== Apport {i + 1}/{len(apports)} : {apport} -> {section} ===")

        # --- etape 1 : estimation initiale --------------------------------
        # L'hydrogramme de depart de l'apport n'a AUCUNE importance : la
        # correction additive le remplace entierement des le premier essai
        # par ce qui manque a la section.
        #
        # LIRE LE RESIDUEL AVANT D'OUVRIR L'ETAPE. Il se lit dans les
        # RESULTATS du dernier calcul — l'etat de reference pour le premier
        # apport, l'apport precedent valide pour les suivants. Or jalonner()
        # CLONE le plan et fait pointer le modele sur un plan NEUF, qui n'a
        # pas encore de fichier de resultats. Lire apres le jalon revenait
        # donc a chercher l'etat de reference dans un .hdf qui n'existe pas.
        try:
            temps_residuel, residuel = modele.lire_section(section)
            echec_lecture = ""
        except Exception as e:                              # noqa: BLE001
            temps_residuel, residuel = None, None
            echec_lecture = f"{type(e).__name__}: {e}"

        # NOUVELLE ETAPE AVANT LA PREMIERE ECRITURE de cet apport : ce qui
        # precede — etat de reference ou apport precedent valide — reste ainsi
        # fige dans ses propres fichiers, relisible tel quel.
        _jalonner(modele, etape_apport(apport, config.prefixe_etape), dire)

        # --- premiere estimation : CE QUI MANQUE, apport a zero -----------
        #
        # Pas un facteur applique a une forme supposee, mais l'ecart mesure
        # lui-meme. C'est deja la bonne forme au premier ordre : le deficit
        # porte l'information de volume, de pointe ET d'allure.
        if residuel is None:
            # LA CAUSE EST DITE. Le message ne portait que le symptome, et
            # une lecture qui echoue a dix raisons possibles — section absente
            # du modele, nom mal orthographie, resultats non ecrits. Sans la
            # phrase de l'exception, chaque diagnostic repartait de zero.
            etat_apport, motif = "arret", (
                f"impossible de lire le debit a la section « {section} » avec "
                f"l'apport a zero : sans cet etat de reference, aucune "
                f"estimation n'est possible."
                + (f" Cause : {echec_lecture}" if echec_lecture else ""))
            manquant = None
            decalage_zero = 0.0
            bornes_fenetre = None
            # DEFINI DANS LES DEUX BRANCHES. Sans cela il garderait la valeur
            # de l'apport PRECEDENT — la boucle porte sur les apports, et une
            # variable laissee de cote y traverse les tours sans bruit.
            cliquet = 1.0
            part_apport = None
        else:
            # Meme raisonnement que pour les corrections suivantes : le
            # residuel arrive decale, et le soustraire tel quel melerait un
            # dephasage au deficit reel.
            #
            # MESURE UNE SEULE FOIS, ICI, PUIS FIGEE pour tous les essais
            # suivants (voir decalage_minimisant_ecart). C'est exactement le
            # geste manuel : lire l'heure du pic dans le calcul a apport nul,
            # la comparer a celle du pic cible, une fois pour toutes.
            decalage_zero = decalage_minimisant_ecart(
                temps_cible, debit_cible, temps_residuel, residuel)
            manquant = ecart_a_la_cible(temps_cible, debit_cible,
                                        temps_residuel, residuel,
                                        decalage_zero)
            dire(f"    la section recoit deja "
                 f"{float(np.max(residuel)):.1f} m3/s sans cet apport, "
                 f"pour une cible a {float(np.max(debit_cible)):.1f} "
                 f"(decalage retenu {decalage_zero:+.2f} h)")

            # L'APPORT EST-IL SEULEMENT IDENTIFIABLE A CETTE TOLERANCE ? La
            # regle, sa mesure (08/08/2026 : 2 % de part, +200 % sur l'apport,
            # section a 100,5 %) et son texte vivent dans
            # criteres.reserve_identifiabilite. Ici on mesure la PART, on
            # l'annonce au journal avant tout essai, et on la passe a chaque
            # diagnostic : c'est lui qui la porte jusqu'au classeur, a la
            # note de synthese et au suivi (07/09/2026).
            pic_cible = float(np.max(debit_cible))
            pic_residuel = float(np.max(residuel))
            part_apport = ((pic_cible - pic_residuel) / pic_cible
                           if pic_cible else 0.0)
            _reserve = reserve_identifiabilite(part_apport,
                                               config.tolerance_volume)
            if _reserve:
                dire(f"    ATTENTION — {_reserve}")

            # FENETRE DE L'EVENEMENT PRINCIPAL — voir fenetre_injection() et
            # Configuration. Restreint le jugement et la presentation des
            # resultats, pas l'apport injecte.
            if _fenetre_demandee(config):
                bornes_fenetre = fenetre_injection(
                    temps_cible, manquant,
                    seuil_bas=config.fenetre_seuil_bas,
                    seuil_haut=config.fenetre_seuil_haut,
                    t0_impose=config.fenetre_t0_h,
                    tf_impose=config.fenetre_tf_h,
                    volume_reference=_volume(temps_cible, debit_cible),
                    perte_max=config.tolerance_volume)
                if config.fenetre_marge_h:
                    t_min, t_max = float(temps_cible[0]), float(temps_cible[-1])
                    bornes_fenetre = (
                        max(bornes_fenetre[0] - config.fenetre_marge_h, t_min),
                        min(bornes_fenetre[1] + config.fenetre_marge_h, t_max))
                dire(f"    hydrogramme principal {bornes_fenetre[0]:.2f} h -> "
                     f"{bornes_fenetre[1]:.2f} h — seule cette fenetre est "
                     f"jugee et presentee ; l'apport reste calcule sur toute "
                     f"la serie")
            else:
                bornes_fenetre = None

            # POUR LA COHERENCE DU DECALAGE LE LONG DE L'AXE, jugee a la fin
            # du calage : le Dt RETENU et la fenetre jugee, tels que la
            # correction les emploie — voir _coherence_points.
            if bornes_fenetre is not None:
                points_axe.append((
                    float(temps_cible[int(np.nanargmax(debit_cible))]),
                    float(decalage_zero),
                    float(bornes_fenetre[1]) - float(bornes_fenetre[0])))

            # LE CLIQUET : JUSQU'OU CE CALAGE PEUT-IL DESCENDRE ?
            #
            # Apres la fenetre, parce qu'il se mesure la ou le volume se juge.
            # Ne coute aucun calcul : tout est deja en main a l'iteration 0.
            #
            # ALERTE, PUIS CONTINUE — meme regle que pour un apport peu
            # identifiable. La section restera peut-etre conforme en pointe et
            # en forme, et c'est a l'operateur de decider si un volume plancher
            # a 107 % lui convient. Ce qui n'etait pas admissible, c'est de le
            # lui apprendre apres six essais et autant de simulations.
            cliquet = cliquet_volume(temps_cible, debit_cible, manquant,
                                     decalage_zero, bornes_fenetre)
            if cliquet > 1.0 + config.tolerance_volume:
                dire(f"    ATTENTION — VOLUME PLANCHER : la section donne "
                     f"deja plus que la cible sur une partie de la fenetre, "
                     f"et un apport ne sait qu'ajouter du debit. Le rapport "
                     f"de volume ne descendra pas au-dessous d'environ "
                     f"{100 * cliquet:.1f} %, pour une tolerance de "
                     f"{100 * config.tolerance_volume:.1f} %. Aucun essai n'y "
                     f"changera rien : c'est le residuel qu'il faut reprendre "
                     f"— apports amont deja cales, ou la cible elle-meme.")

        # --- duree simulee ajustee a CET apport ---------------------------
        #
        # APRES le jalon, donc sur le plan de l'etape et jamais sur le plan de
        # reference. Le calendrier a ete etabli une fois pour toutes sur le
        # calcul de reference (voir _calendrier_durees) : le lire ici plutot
        # que le recalculer evite de le mesurer sur un calcul deja raccourci.
        if durees_simulees[i] is not None:
            applique = _sans_interrompre(modele.limiter_duree,
                                         durees_simulees[i])
            if applique:
                dire(f"    duree simulee ramenee a {applique:.1f} h — "
                     f"au-dela, plus rien n'est juge ni presente")
                # LE PLAFOND A-T-IL ROGNE ? La duree voulue peut depasser la
                # fenetre du plan de reference (PiloteHecRas.duree_reference_h),
                # qui la borne. Ce qui se perd alors est la MARGE, pas la
                # fenetre jugee : sur les douze cibles reelles du 31/08/2026,
                # la plus haute borne jugee tombe a 35,5 h sous un plafond de
                # 36 h, et seul le dernier apport perd 1,5 h de marge_duree_h.
                #
                # JOURNAL SEULEMENT, PAS D'ALERTE, decision du 31/08/2026 : une
                # marge existe pour etre rognee, et rien de ce qui est juge ne
                # manque. Si la FENETRE elle-meme finissait par ne plus rentrer,
                # ce n'est pas ici que ca se verrait mais dans la couverture,
                # que criteres.diagnostiquer chiffre desormais des le premier
                # dixieme d'heure manquant.
                if applique < durees_simulees[i] - 1e-9:
                    dire(f"      ({durees_simulees[i]:.1f} h voulues : plafond "
                         f"du plan de reference — "
                         f"{durees_simulees[i] - applique:.1f} h de marge en "
                         f"moins, la fenetre jugee reste couverte)")

        historique_rapport, essais = [], 0
        debut_apport = time.time()
        etat_apport = locals().get("etat_apport", "poursuivre")
        motif = locals().get("motif", "")
        diag = None
        courant = None
        volume_initial = 0.0
        meilleur, degradations = None, 0

        # La section recoit-elle DEJA plus que la cible ? On ne peut pas
        # RETIRER du debit avec un apport : le dire tout de suite vaut mieux
        # que d'iterer vers un apport nul en degradant le diagnostic.
        if manquant is not None and float(np.max(manquant)) <= 0.0:
            modele.appliquer_facteur(apport, 0.0)
            etat_apport, motif = "arret", (
                f"la section recoit deja au moins autant que la cible sans "
                f"cet apport (pointe residuelle "
                f"{float(np.max(residuel)):.1f} m3/s pour une cible a "
                f"{float(np.max(debit_cible)):.1f}). Un apport ne peut "
                f"qu'ajouter du debit : la cible est hors d'atteinte par ce "
                f"levier. Verifier les apports amont deja cales, ou la cible "
                f"elle-meme.")
        elif manquant is not None:
            courant = np.maximum(manquant, 0.0)
            volume_initial = max(_volume(temps_cible, courant), 1e-9)

        while courant is not None:
            # --- calcul, puis qualite numerique --------------------------
            modele.definir_forme(apport, temps_cible, courant)
            modele.appliquer_facteur(apport, 1.0)
            calcul = modele.calculer()
            resultat.nb_calculs += 1
            _noter_bilan(suivi, calcul, config)
            acceptable, motif_qualite = qualite_acceptable(calcul, config)

            if not acceptable:
                # Un essai rejete n'entre PAS dans l'historique : il n'apprend
                # rien sur la relation apport -> reponse.
                dire(f"    essai {essais + 1} REJETE — {motif_qualite}")
                etat_apport, motif = "arret", (
                    f"calcul rejete pour qualite numerique : {motif_qualite}")
                break

            # --- diagnostic ----------------------------------------------
            temps_calcule, debit_calcule = modele.lire_section(section)
            diag = diagnostiquer(temps_cible, debit_cible,
                                 temps_calcule, debit_calcule,
                                 tolerance_volume=config.tolerance_volume,
                                 tolerance_pic=config.tolerance_pic,
                                 r_min=config.r_min,
                                 fenetre=bornes_fenetre,
                                 part_apport=part_apport)
            essais += 1

            historique_rapport.append({
                "essai": essais,
                "facteur": _volume(temps_cible, courant) / volume_initial,
                "volume": diag.rapport_volume,
                "pic": diag.rapport_pic, "r": diag.r})

            # MEMORISER LE MEILLEUR. La reponse du modele n'est pas lineaire :
            # la recherche peut passer pres de la concordance puis s'en
            # eloigner. Rendre le DERNIER essai serait alors absurde.
            #
            # LE CLASSEMENT EST (admissibilite, erreur combinee) : un essai
            # qui tient les trois seuils passe devant tous les autres, et
            # entre deux essais de meme admissibilite c'est celui qui est le
            # plus proche des trois cibles A LA FOIS qui est retenu.
            if meilleur is None or rang_essai(diag, config) < meilleur["rang"]:
                meilleur = {"rang": rang_essai(diag, config),
                            "apport": courant.copy(),
                            "diag": diag, "essai": essais,
                            "series": (temps_cible, debit_cible,
                                       temps_calcule, debit_calcule)}
                degradations = 0
            else:
                degradations += 1

            atteint = concordance(diag, config)
            dire(f"    essai {essais} : "
                 f"volume {100 * diag.rapport_volume:5.1f} %  "
                 f"pointe {100 * diag.rapport_pic:5.1f} %  "
                 f"forme {100 * diag.r:5.1f} %"
                 + ("  -> concordance atteinte" if atteint else ""))
            if suivi is not None:
                if essais == 1:
                    _sans_interrompre(suivi.enregistrer_residuel, i,
                                      (temps_cible, debit_cible),
                                      (temps_residuel, residuel),
                                      decalage_zero)
                # rapport_volume : c'est la grandeur que la boucle teste et
                # que le journal affiche.
                _sans_interrompre(suivi.enregistrer_essai, i,
                                  _volume(temps_cible, courant) / volume_initial,
                                  diag.rapport_volume,
                                  diag.rapport_pic, diag.r, diag.decalage_h,
                                  (temps_cible, debit_cible,
                                   temps_calcule, debit_calcule),
                                  (temps_cible, courant),
                                  decalage_zero)

            if atteint:
                etat_apport = "converge"
                break

            # VOLUME EXCEDENTAIRE ET POINTE DEFICITAIRE : les deux exigences
            # se contredisent, car un apport ne sait qu'AJOUTER du debit — il
            # remplit un hydrogramme trop maigre, il n'affute pas un
            # hydrogramme trop plat. On le DIT, sans arreter.
            if (diag.rapport_volume > 1.0 + config.tolerance_volume
                    and diag.rapport_pic < 1.0 - config.tolerance_pic):
                dire(f"      volume DEJA excedentaire alors que la pointe "
                     f"manque : l'hydrogramme calcule est trop ETALE, pas "
                     f"trop faible. Rehausser la pointe aggravera le volume. "
                     f"Pistes : resserrer les apports amont deja cales, "
                     f"rapprocher l'injection de la section, ou revoir la "
                     f"cible.")

            # Deux essais consecutifs qui s'eloignent : insister ne fera
            # qu'empirer. On s'arrete et on retient le meilleur.
            if degradations >= 2:
                etat_apport, motif = "arret", (
                    f"la recherche s'eloigne de la concordance depuis "
                    f"l'essai {meilleur['essai']} : le modele repond de "
                    f"facon trop non lineaire a cet apport pour aller plus "
                    f"loin.")
                break

            if essais >= config.nb_max_essais:
                etat_apport = "arret"
                motif = (
                    f"{essais} essais sans concordance simultanee : volume "
                    f"{100 * diag.rapport_volume:.1f} %, pointe "
                    f"{100 * diag.rapport_pic:.1f} %, forme "
                    f"{100 * diag.r:.1f} % de la cible.")
                # PROGRESSAIT-ON ENCORE ? Une recherche qui plafonne ne
                # gagnera rien a plus d'essais ; une recherche qui avance
                # encore, si.
                pas = _progression_pic(historique_rapport)
                if pas is not None and pas > 1e-5:
                    reste = (1.0 - config.tolerance_pic) - diag.rapport_pic
                    if reste > 0:
                        motif += (
                            f" La pointe PROGRESSAIT ENCORE de "
                            f"{100 * pas:+.2f} point au dernier essai ; il lui "
                            f"manquait {100 * reste:.1f} point(s), soit "
                            f"environ {reste / pas:.0f} essai(s) de plus. "
                            f"Augmenter Nb_max_iterations_par_apport avant de "
                            f"mettre en cause la methode.")
                if diag.alertes:
                    motif += " Alertes : " + " ; ".join(diag.alertes)
                break

            # --- correction ------------------------------------------------
            # L'ecart est calcule APRES recalage temporel, avec le decalage
            # FIGE a l'itération 0 (jamais remesure) : sans cela, la
            # correction combat le temps de propagation au lieu du defaut
            # d'apport, et le debit de pointe s'emballe.
            manque = ecart_a_la_cible(temps_cible, debit_cible,
                                      temps_calcule, debit_calcule,
                                      decalage_zero)
            precedent = courant
            courant = corriger_apport(courant, manque)
            dire(f"      correction au pic "
                 f"{float(np.max(courant - precedent)):+.1f} m3/s")
            if float(np.max(np.abs(courant - precedent))) <= 1e-6:
                etat_apport, motif = "arret", (
                    f"la correction n'a plus d'effet alors que la "
                    f"concordance n'est pas atteinte (volume "
                    f"{100 * diag.rapport_volume:.1f} %, pointe "
                    f"{100 * diag.rapport_pic:.1f} %) : le modele ne repond "
                    f"plus a cet apport.")
                break

        # RESTITUER LE MEILLEUR ETAT, pas le dernier. Le modele conserve
        # l'hydrogramme du dernier essai : si un essai anterieur etait plus
        # proche de la concordance, c'est lui qu'il faut remettre en place,
        # sans quoi le calage laisserait derriere lui un apport moins bon que
        # celui qu'il a su trouver.
        essai_en_place = essais
        if (meilleur is not None and etat_apport != "converge"
                and meilleur["essai"] != essais):
            modele.definir_forme(apport, temps_cible, meilleur["apport"])
            modele.appliquer_facteur(apport, 1.0)
            essai_en_place = meilleur["essai"]
            diag = meilleur["diag"]
            temps_cible, debit_cible, temps_calcule, debit_calcule = \
                meilleur["series"]
            dire(f"    retour a l'essai {meilleur['essai']}, le plus proche "
                 f"de la concordance (volume "
                 f"{100 * diag.rapport_volume:.1f} %, pointe "
                 f"{100 * diag.rapport_pic:.1f} %)")
            # UN APPORT REMIS EN PLACE N'EST JAMAIS VALIDE : tout essai
            # concordant fait deja sortir la boucle sur « converge » — les
            # essais encore candidats au titre de meilleur ont donc TOUS
            # echoue au meme test, sur le meme diagnostic. Rejouer ce test
            # ici ne pourrait jamais rattraper un essai qui a deja echoue.

        duree_apport = time.time() - debut_apport
        valide = etat_apport == "converge"
        if not valide and not motif:
            motif = "concordance volume / pointe / forme non atteinte"

        # LE CLIQUET EST LA PREMIERE CAUSE A CITER QUAND IL JOUE.
        #
        # L'annonce de l'iteration 0 partait au journal, et le VERDICT, lui,
        # disait autre chose : mesure au banc, « le modele repond de facon
        # trop non lineaire a cet apport » pour un volume bloque a 109,6 %
        # quand le plancher valait 109,8 %. Le modele n'y etait pour rien.
        # Un motif qui designe la mauvaise cause envoie corriger la mauvaise
        # chose — ici le maillage ou le pas de calcul, quand ce sont les
        # apports amont ou la cible qu'il faut reprendre.
        if (not valide and cliquet > 1.0 + config.tolerance_volume
                and diag is not None
                and diag.rapport_volume > 1.0 + config.tolerance_volume):
            motif += (f" LE VOLUME NE POUVAIT PAS DESCENDRE PLUS BAS : la "
                      f"section donne deja plus que la cible sans cet apport, "
                      f"et un apport ne sait qu'ajouter du debit — plancher "
                      f"estime a {100 * cliquet:.1f} %, atteint "
                      f"{100 * diag.rapport_volume:.1f} %. Reprendre les "
                      f"apports amont deja cales, ou la cible, avant de "
                      f"mettre en cause la reponse du modele.")

        resultat.apports.append(ResultatApport(
            nom_apport=apport, nom_section=section, valide=valide,
            # Le facteur decrit l'essai RETENU. Apres un retour au meilleur
            # essai, prendre le dernier de l'historique decrirait un apport
            # qui n'est plus en place.
            facteur=_facteur_retenu(historique_rapport, essai_en_place),
            diagnostic=diag, essais=essais,
            duree_s=duree_apport, motif="" if valide else motif,
            historique=historique_rapport,
            fenetre_principale=bornes_fenetre,
            part_apport=part_apport))

        if suivi is not None:
            series = ((temps_cible, debit_cible, temps_calcule, debit_calcule)
                      if valide and diag is not None else None)
            if valide:
                _sans_interrompre(suivi.valider_apport, i, diag,
                                  duree_apport, series)
            else:
                _sans_interrompre(suivi.echouer_apport, i, motif, diag,
                                  duree_apport)

        if not valide:
            dire(f"    ARRET sur cet apport : {motif}")
            resultat.motif = (f"apport {apport} non cale : {motif}. "
                              f"Les apports suivants ne sont pas traites : la "
                              f"resolution sequentielle suppose l'amont fige.")
            break

        # --- etape 7 : coherence des sections amont -----------------------
        if config.controle_amont and i > 0:
            _signaler_coherence_amont(
                modele, sections[:i], cibles[:i],
                [a.fenetre_principale for a in resultat.apports[:i]],
                config, apport, dire)

    # --- etape finale : verification globale -------------------------------
    if all(a.valide for a in resultat.apports) and \
            len(resultat.apports) == len(apports):
        _verifier_globalement(modele, sections, cibles, config, resultat, dire)

        # --- L'ETAT FINAL PORTE ENFIN UN NOM QUI LE DIT ----------------------
        #
        # Le plan de la DERNIERE etape porte deja tous les apports cales ET
        # leurs resultats : la verification ci-dessus vient de le relire sans
        # lancer un seul calcul. Rien ne le disait pourtant — il s'appelait
        # « Apport_<dernier apport> », un titre qui designe une ETAPE, et il
        # fallait connaitre l'ordre des apports pour savoir lequel des dix
        # plans du projet etait celui qu'on cherchait.
        #
        # ON RETITRE, ON NE CLONE PAS : clone_plan copie le .pXX, pas le
        # .pXX.hdf. Un plan « avec apports » vide a cote d'un
        # « Apport_<dernier> » qui a les resultats serait pire que pas de plan
        # final du tout.
        #
        # SANS ATTENDRE LE VERDICT : « avec apports » enonce un CONTENU, pas
        # une conformite — celle-ci se lit dans les livrables et le suivi. Un
        # calage NON conforme est justement celui qu'on rouvre, et lui refuser
        # ce nom le renverrait a la confusion qu'on corrige. En revanche rien
        # n'est retitre si la sequence s'est arretee en chemin : on n'entre
        # dans ce bloc que si tous les apports sont valides.
        _conclure(modele, titre_etape(ETAPE_AVEC_APPORTS, config.prefixe_etape),
                  dire)

    # --- coherence du decalage le long de l'axe : A LA FIN, SUR LES Dt RETENUS
    # Quel que soit le verdict : un calage arrete en chemin a quand meme ses
    # Dt, et quatre suffisent. Non bloquante, comme toute alerte de chaine.
    _alerte_axe = _sans_interrompre(_coherence_points, points_axe, dire)
    if _alerte_axe:
        resultat.alertes_chaine.append(_alerte_axe)
        dire(f"    ATTENTION — {_alerte_axe}")

    resultat.duree_s = time.time() - debut
    if suivi is not None:
        _sans_interrompre(suivi.terminer)
    return resultat


def _verifier_globalement(modele, sections, cibles, config, resultat, dire):
    """
    Etape finale : relit TOUTES les sections sur le dernier calcul, prononce
    la conformite, et dit ce qui a echoue et ou. Ecrit dans resultat.

    AUCUN CALCUL SUPPLEMENTAIRE ICI, et c'est licite : on n'arrive dans cette
    passe que si TOUS les apports sont valides, ce qui exclut qu'un seul ait
    ete remis a un essai anterieur. Le dernier calcul porte donc le jeu
    d'apports definitif, et le relire suffit.
    """
    dire("\n=== Verification globale finale ===")
    for section, (t_c, q_c), a in zip(sections, cibles, resultat.apports):
        t_s, q_s = modele.lire_section(section)
        d = diagnostiquer(t_c, q_c, t_s, q_s,
                          tolerance_volume=config.tolerance_volume,
                          tolerance_pic=config.tolerance_pic,
                          r_min=config.r_min,
                          fenetre=a.fenetre_principale,
                          part_apport=a.part_apport)
        resultat.diagnostics_finaux.append(d)
        # SERIES PRESENTEES DANS LE RAPPORT : ENTIERES, telles que le modele
        # les rend.
        #
        # ELLES ETAIENT COUPEES A LA FENETRE JUGEE, et c'etait un doublon
        # nuisible. livrables.figure_comparaison cadre DEJA toute seule, sur
        # la crue significative (_fenetre_crue : 2 % du pic, plus une
        # demi-heure) — c'est ce qui donne a la figure de SUIVI son cadrage
        # juste, puisqu'elle, recoit les series entieres. Deux mecanismes
        # pour la meme intention, et le plus grossier gagnait dans ce qui
        # part au client.
        #   MESURE sur un apport reel : coupees, les series ne permettent
        #   qu'un cadrage 6,50-20,70 h, alors que la crue court jusqu'a 37 h
        #   et que le calcul y redescend a 1,9 % de son pic. La figure finale
        #   montrait donc MOINS que la figure de suivi, avec la meme legende
        #   — et cachait toute la decrue.
        #   CE QUI EST JUGE N'A PAS CHANGE : diagnostiquer() recoit toujours
        #   la fenetre, et c'est lui qui prononce. Seule la PRESENTATION
        #   cesse d'etre amputee.
        resultat.series_finales.append((t_c, q_c, t_s, q_s))
        dire(f"    {section:24s} volume {100 * d.rapport_volume:5.1f} %  "
             f"pointe {100 * d.rapport_pic:5.1f} %  "
             f"{'conforme' if d.converge else 'NON CONFORME'}")
    resultat.conforme = all(d.converge for d in resultat.diagnostics_finaux)
    if not resultat.conforme:
        # LE MOTIF DIT CE QUI A ECHOUE, ET OU. Il annoncait autrefois une
        # « derive » quelle que soit la cause : sur un calage dont tous les
        # apports avaient ete valides un par un, cela envoyait chercher un
        # remous inexistant alors que la cause etait ailleurs.
        bloquees = [(s, d) for s, d in zip(sections,
                                           resultat.diagnostics_finaux)
                    if d.alertes_bloquantes]
        derivees = [s for s, d in zip(sections, resultat.diagnostics_finaux)
                    if not d.converge and not d.alertes_bloquantes]
        causes = []
        if derivees:
            causes.append(
                f"derive a la verification globale sur {derivees} : "
                f"relancer une passe sequentielle amont -> aval, jamais "
                f"une optimisation globale simultanee")
        for section, d in bloquees:
            causes.append(f"« {section} » : "
                          + " ; ".join(d.alertes_bloquantes))
        resultat.motif = ". ".join(causes) + "."


def _signaler_coherence_amont(modele, sections_amont, cibles_amont,
                              fenetres_amont, config, apport, dire):
    """
    Etape 7 : le remous du nouvel apport a-t-il deplace les sections deja
    calees ? Relit, SIGNALE, et ne reprend rien.

    UNE SEULE EVALUATION, ET C'EST TOUT CE QU'ON PEUT EN TIRER.

    Ce controle etait ecrit comme une boucle de « reprises », qui rappelait
    _sections_derivees jusqu'a reprises_max. Or cette fonction est une
    RELECTURE PURE du dernier calcul : aucun calcul HEC-RAS n'intervient entre
    deux tours, les entrees sont identiques, le verdict aussi. La boucle ne
    pouvait donc rien changer — elle imprimait « reprise 1/2 » puis
    « reprise 2/2 » avant le meme resultat, ce qui donnait a lire une chaine
    en train de corriger quelque chose alors qu'elle relisait deux fois la
    meme chose. Constate sur le calage du 07-08/08/2026, ou les deux lignes
    sont apparues a chacun des sept apports.

    Rattraper reellement une derive amont demanderait de reprendre l'apport
    concerne, donc un calcul de plusieurs heures, et de relancer toute la
    sequence aval derriere lui. C'est une decision d'ingenieur, pas un
    automatisme : la chaine SIGNALE, et laisse decider.
    """
    derives, illisibles = _sections_derivees(
        modele, sections_amont, cibles_amont, config, fenetres_amont)
    # DIRE QU'ON N'A PAS PU REGARDER. Sans cette ligne, une section que le
    # modele refuse de rendre disparaissait de l'examen, et le silence qui
    # suivait se lisait comme « rien n'a derive ».
    if illisibles:
        dire(f"    AVERTISSEMENT : en aval de « {apport} », les "
             f"sections deja calees {[s for s, _ in illisibles]} "
             f"n'ont PAS pu etre relues — leur derive n'a donc pas "
             f"ete verifiee ici. "
             + " ; ".join(f"{s} — {m}" for s, m in illisibles))
    if derives:
        dire(f"    AVERTISSEMENT : en aval de « {apport} », les "
             f"sections deja calees {[s for s, _ in derives]} sont "
             f"sorties de tolerance. Le remous du nouvel apport les a "
             f"deplacees. Les reprendre suppose de relancer la "
             f"sequence a partir de la premiere d'entre elles ; rien "
             f"n'est repris automatiquement.")


def _sections_derivees(modele, sections, cibles, config, fenetres=None):
    """
    Sections deja validees qui sont sorties de tolerance. Simple relecture du
    dernier calcul : aucun calcul supplementaire.

    fenetres : une (t0, tf) par section, dans le meme ordre — celle de
    l'evenement principal detectee pour cette section lors de son propre
    calage (ResultatApport.fenetre_principale). Sans elle (None), chaque
    section est jugee sur sa fenetre commune entiere.

    Rend (derives, illisibles).

    UNE SECTION QU'ON NE SAIT PAS LIRE N'EST PAS UNE SECTION QUI VA BIEN.
    Elle sortait de la liste sans un mot : l'appelant n'avait plus aucun
    moyen de distinguer « aucune section amont n'a derive » de « je n'ai pas
    pu regarder », et il annoncait le premier. Elle est desormais RAPPORTEE,
    et jamais bloquante — le verdict, lui, ne se joue pas ici : la
    verification globale finale relit toutes les sections SANS try, et une
    lecture impossible y remonte.
    """
    if fenetres is None:
        fenetres = [None] * len(sections)
    derives = []
    illisibles = []
    for section, (t_c, q_c), fenetre in zip(sections, cibles, fenetres):
        try:
            t_s, q_s = modele.lire_section(section)
        except Exception as erreur:
            illisibles.append((section, f"{type(erreur).__name__}: {erreur}"))
            continue
        # SANS part_apport, a dessein : ce controle ne lit que converge et ne
        # produit aucun livrable ; la reserve d'identifiabilite n'y a rien a
        # dire.
        d = diagnostiquer(t_c, q_c, t_s, q_s,
                          tolerance_volume=config.tolerance_volume,
                          tolerance_pic=config.tolerance_pic,
                          r_min=config.r_min,
                          fenetre=fenetre)
        if not d.converge:
            derives.append((section, d))
    return derives, illisibles


def _sans_interrompre(fonction, *arguments):
    """
    Le suivi ne doit jamais interrompre le calage. Meme regle que dans
    suivi.py, appliquee ici aussi : un calage de six heures ne se perd pas
    parce qu'une figure n'a pas pu s'ecrire.
    """
    try:
        return fonction(*arguments)
    except Exception:
        return None


# COHERENCE DU DECALAGE LE LONG DE L'AXE — voir _coherence_decalage().
#
# LE CRITERE PORTE SUR L'ETENDUE DE Dt, ET C'EST LE SECOND MODELE QUI L'A
# IMPOSE. La premiere version alertait sur « pente forte ET correlation
# elevee », seuils poses sur un seul cas. Mesure du 01/09/2026 sur un DEUXIEME
# modele :
#     modele A, 8 apports : etendue 4,4 h   pente -0,70   r -0,98   -> alertait
#     modele B, 6 apports : etendue 7,0 h   pente +0,99   r +0,73   -> NON
#     (lecture a apports NULS — fausse comme mesure du modele, voir la
#     docstring de _coherence_decalage ; cale, ce modele s'etend sur 1,8 h)
# Le modele B a la pente LA PLUS FORTE et la derive LA PLUS GRANDE, et passait
# quand meme, parce que sa derive n'est pas monotone (-0,70, +0,40, -1,10,
# +2,30, +3,40, +5,90) et que le r restait sous 0,9. LE « ET » SUR LA
# CORRELATION ECARTAIT LE PIRE DES DEUX CAS.
#
# L'etendue, elle, ne depend pas de la FORME de la derive : un Dt constant —
# la signature saine — vaut 0,0 h quelle que soit sa valeur moyenne. La pente
# et le r restent RAPPORTES, parce qu'ils disent le sens et la nettete, mais
# ne commandent plus rien.
#
# SEUIL RELATIF A LA DUREE DE L'EVENEMENT, et non en heures : un Dt qui derive
# de 4 h sur des crues de 25 h ne dit pas la meme chose que sur des crues de
# 100 h. Un seuil en heures aurait demande un recalibrage a chaque modele.
# 15 % DE LA DUREE MEDIANE DES FENETRES JUGEES — franchement au-dessus du
# bruit, en deca des deux cas mesures. FONDE SUR DEUX CAS : a revoir au
# troisieme, meme reserve que le bilan de masse a 5 %.
ETENDUE_DECALAGE_MAX_PART = 0.15


def _fenetre_demandee(config):
    """
    Le JUGEMENT est-il restreint a l'evenement principal ?

    SOURCE UNIQUE POUR LES DEUX DECISIONS QUI EN DEPENDENT : la fenetre de
    jugement (caler(), etape « premiere estimation ») et le raccourcissement
    de la duree simulee (_calendrier_durees). Elles etaient prises sur des
    criteres disjoints — la premiere sur fenetre_active, la seconde sur
    ajuster_duree seul — et cette asymetrie a coute un calage entier : voir
    le commentaire de _calendrier_durees.

    Une case vide du classeur n'est pas un « non » (voir
    pont_hecras._oui_non_ou_defaut) : elle vaut le defaut, qui est oui.
    """
    return True if config.fenetre_active is None else bool(config.fenetre_active)


def _coherence_decalage(cibles, residuels, config, dire):
    r"""
    Le decalage est-il COHERENT LE LONG DE L'AXE ? Rend une alerte ou None.

    ON NE JUGE PAS L'AMPLITUDE DE Dt, ON JUGE SA VARIATION, et c'est ce qui
    rend ce controle compatible avec la regle « le decalage est rapporte,
    jamais juge » (decalage_minimisant_ecart). Un Dt de 5 h identique a toutes
    les sections ne dit rien de suspect : c'est une origine de temps qui
    differe. Un Dt qui DERIVE le long de l'axe dit que le modele et les cibles
    ne routent pas la crue au meme rythme, et le desaccord grandit.

    LA GRANDEUR EST L'ETENDUE DE Dt — max moins min — rapportee a la duree
    MEDIANE des fenetres jugees. Voir ETENDUE_DECALAGE_MAX_PART pour pourquoi
    ce n'est ni la pente, ni un seuil en heures.

    DEUX MODELES REELS, DEUX SIGNATURES OPPOSEES (01/09/2026) :
      modele A, 8 apports  pic modele +0,26 h/section, cibles +0,84
                           etendue 4,4 h, pente -0,70, r -0,98
                           le modele route PLUS LENTEMENT que les cibles
      modele B, 6 apports  pic modele +2,30 h/section, cibles +1,00
                           etendue 7,0 h, pente +0,99, r +0,73
                           le modele route PLUS VITE que les cibles
    Les deux divergent, en sens contraire. C'est bien la VARIATION qui est le
    signal, pas le signe ni la valeur moyenne.

    SUR QUEL ETAT DU MODELE — c'est la lecon du 04/09/2026. Cette fonction
    mesurait Dt sur le calcul de REFERENCE, tous apports a zero, pour rendre
    l'alerte 1 h 22 apres le lancement. Mais a cet etat les sections aval
    sont affamees, leur pic arrive de plus en plus tard, et la derive mesuree
    grandit avec le rang : les 7,0 h du « modele B » ci-dessus sont cette
    lecture-la — le meme modele, une fois cale, s'etend sur 1,8 h et ne
    derive pas. caler() juge donc A LA FIN, sur les Dt RETENUS apport par
    apport (_coherence_points) ; cette fonction ne sert plus qu'au banc.

    CE QU'ELLE NE REMET PAS EN CAUSE : les sections restent calees, a 99-101 %
    de volume. Ce que l'etendue interroge est le POSITIONNEMENT TEMPOREL des
    hydrogrammes d'apport livres — un apport cale sur une cible decalee de
    4,3 h reproduit sa forme, a 4,3 h pres, et le decalage n'est pas le meme
    d'une section a l'autre.
    """
    points = []
    for i, (temps_cible, debit_cible) in enumerate(cibles):
        if i >= len(residuels) or residuels[i] is None:
            continue
        t_res, q_res = residuels[i]
        t_c = np.asarray(temps_cible, dtype=float)
        q_c = np.asarray(debit_cible, dtype=float)
        if t_c.size == 0 or not np.any(np.isfinite(q_c)):
            continue
        try:
            dt = float(decalage_minimisant_ecart(temps_cible, debit_cible,
                                                 t_res, q_res))
            # LA MEME FENETRE QUE CELLE QUI SERA JUGEE, mesuree sur le meme
            # ecart : c'est elle qui donne l'echelle a laquelle un decalage
            # compte. La recalculer ici ne coute rien — aucun calcul HEC-RAS.
            manque = ecart_a_la_cible(temps_cible, debit_cible,
                                      t_res, q_res, dt)
            f0, f1 = fenetre_injection(
                temps_cible, manque,
                seuil_bas=config.fenetre_seuil_bas,
                seuil_haut=config.fenetre_seuil_haut,
                t0_impose=config.fenetre_t0_h,
                tf_impose=config.fenetre_tf_h,
                volume_reference=_volume(temps_cible, debit_cible),
                perte_max=config.tolerance_volume)
        except Exception:                                    # noqa: BLE001
            continue
        points.append((float(t_c[int(np.nanargmax(q_c))]), dt,
                       float(f1) - float(f0)))
    return _coherence_points(points, dire)


def _coherence_points(points, dire):
    """
    Le critere lui-meme, sur des points deja mesures : (heure du pic cible,
    Dt retenu, largeur de la fenetre jugee), un par apport, en heures.

    C'EST LUI QUE caler() APPELLE, A LA FIN, avec les Dt que la correction a
    employes — mesures apport par apport, l'amont deja cale, puis figes.
    _coherence_decalage() les recalcule depuis des series ; il ne sert plus
    qu'au banc, sur les deux signatures qu'il conserve.
    """
    # QUATRE APPORTS AU MOINS. Une derive sur deux ou trois sections n'a pas
    # de sens, et une alerte fondee sur elle serait du bruit.
    if len(points) < 4:
        return None
    pics = np.array([p[0] for p in points])
    ecarts = np.array([p[1] for p in points])
    largeurs = np.array([p[2] for p in points])

    etendue = float(np.ptp(ecarts))
    duree = float(np.median(largeurs[largeurs > 0])) if np.any(largeurs > 0) else 0.0
    seuil = ETENDUE_DECALAGE_MAX_PART * duree

    rangs = np.arange(len(points), dtype=float)
    prog_cible = float(np.polyfit(rangs, pics, 1)[0])
    prog_modele = float(np.polyfit(rangs, pics + ecarts, 1)[0])
    # PENTE ET CORRELATION SONT RAPPORTEES, PLUS JAMAIS DECISIVES : elles
    # disent le sens de la divergence et sa nettete, ce qu'une etendue seule
    # ne montre pas. C'est le « ET » entre elles qui ecartait le modele B.
    if np.ptp(pics) >= 1e-6 and etendue >= 1e-6:
        pente = float(np.polyfit(pics, ecarts, 1)[0])
        correlation = float(np.corrcoef(pics, ecarts)[0, 1])
        lecture = f"pente {pente:+.2f}, r = {correlation:+.2f}"
    else:
        lecture = (f"decalage constant a {float(np.mean(ecarts)):+.2f} h — les "
                   f"deux calendriers avancent du meme pas")

    dire(f"    coherence du decalage le long de l'axe, sur {len(points)} "
         f"apport(s) : pic du modele {prog_modele:+.2f} h par section, pic des "
         f"cibles {prog_cible:+.2f} h par section ; Dt s'etend sur "
         f"{etendue:.1f} h (seuil {seuil:.1f} h = "
         f"{100 * ETENDUE_DECALAGE_MAX_PART:.0f} % d'une fenetre de "
         f"{duree:.1f} h) ; {lecture}")

    if duree <= 0.0 or etendue <= seuil:
        return None
    return (
        f"le decalage DERIVE de {etendue:.1f} h le long de l'axe, pour des "
        f"fenetres jugees de {duree:.1f} h en mediane — au-dela des "
        f"{100 * ETENDUE_DECALAGE_MAX_PART:.0f} % admis ({seuil:.1f} h). Le "
        f"pic du modele avance de {prog_modele:+.2f} h par section quand celui "
        f"des cibles avance de {prog_cible:+.2f} h ({lecture}). Un decalage "
        f"qui n'est pas le meme d'une section a l'autre n'est pas un temps de "
        f"transfert. LES SECTIONS SERONT CALEES, mais les hydrogrammes "
        f"d'apport livres reproduiront la forme des cibles EN ETANT DECALES, "
        f"et pas du meme temps partout. Relire la base de temps des cibles "
        f"avant d'exploiter ces hydrogrammes.")


def _calendrier_durees(cibles, residuels, config, dire):
    """
    Duree simulee utile a chaque apport, en heures depuis le debut, d'apres le
    CALCUL DE REFERENCE. Retourne une liste aussi longue que « cibles », ou
    None a un rang dont la duree n'est pas mesurable.

    La liste est CROISSANTE : l'etape 7 relit les sections amont depuis le
    calcul courant, et la verification globale finale relit le DERNIER calcul
    pour TOUTES les sections. Une duree qui redescendrait les priverait de
    leur fenetre.

    CHAQUE ETAPE COUVRE AUSSI L'EVENEMENT DE LA SUIVANTE, et c'est la
    subtilite du calendrier. Le calcul de l'etape N n'est pas seulement le
    resultat de l'apport N : c'est l'ETAT DE REFERENCE de l'apport N+1, celui
    ou son residuel se lit. Le tronquer a l'evenement de N prive N+1 de la
    mesure de son propre deficit — son estimation initiale est nulle la ou son
    evenement se produit, et sa fenetre de jugement est bornee par la
    troncature du precedent. Attrape par l'auto-test le 31/08/2026 : un
    premier apport finissant a 10 h rendait le second incalculable.
    La duree du rang i vaut donc le cumul du rang i+1, le dernier rang gardant
    le maximum — c'est lui que relit la verification globale.

    Voir Configuration.ajuster_duree pour le reste du raisonnement.
    """
    if not config.ajuster_duree:
        return [None] * len(cibles)

    # ET PAS NON PLUS SI LE JUGEMENT N'EST PAS FENETRE. Toute la
    # justification du raccourcissement est « au-dela, plus rien n'est ni juge
    # ni presente » (voir Configuration.ajuster_duree). Fenetre_active=non
    # rend cette premisse FAUSSE : la cible est jugee en entier, et la
    # couverture est alors mesuree sur TOUTE sa duree
    # (criteres.diagnostiquer, duree_cible = tc[-1] - tc[0]). Tronquer quand
    # meme faisait echouer un calage par ailleurs parfait sur la bloquante
    # « la fenetre de calcul ne couvre que N % — allonger la simulation »,
    # alors que c'est la chaine qui venait de la raccourcir, et que
    # ajuster_duree n'est pas reglable depuis le classeur.
    # Mesure du 31/08/2026 : volume 100,0 %, pointe 100,0 %, conforme=False.
    # Le defaut etait LATENT — tf tombait jusque-la sur la fin de serie, donc
    # limiter_duree() ne retirait rien ; le correctif d'unites de
    # fenetre_injection() l'a rendu agissant.
    if not _fenetre_demandee(config):
        return [None] * len(cibles)

    durees, courante = [], 0.0
    for i, (temps_cible, debit_cible) in enumerate(cibles):
        if i >= len(residuels) or residuels[i] is None:
            durees.append(None)
            continue
        t_res, q_res = residuels[i]
        try:
            dt = decalage_minimisant_ecart(temps_cible, debit_cible,
                                           t_res, q_res)
            manque = ecart_a_la_cible(temps_cible, debit_cible,
                                      t_res, q_res, dt)
            _, tf = fenetre_injection(
                temps_cible, manque,
                seuil_bas=config.fenetre_seuil_bas,
                seuil_haut=config.fenetre_seuil_haut,
                t0_impose=config.fenetre_t0_h,
                tf_impose=config.fenetre_tf_h,
                volume_reference=_volume(temps_cible, debit_cible),
                perte_max=config.tolerance_volume)
        except Exception:                                    # noqa: BLE001
            # UNE DUREE QU'ON NE SAIT PAS MESURER N'EN EST PAS UNE : on laisse
            # la fenetre entiere plutot que de deviner. Le calcul sera plus
            # long, jamais faux.
            durees.append(None)
            continue
        courante = max(courante, float(tf) + config.fenetre_marge_h
                       + config.marge_duree_h)
        durees.append(courante)

    # DECALAGE D'UN RANG : l'etape i doit couvrir l'evenement de i+1, dont
    # elle est l'etat de reference. Un None quelque part contamine son rang
    # ET le precedent — on ne raccourcit que ce dont on est sur.
    calendrier = []
    for i in range(len(durees)):
        suivant = durees[i + 1] if i + 1 < len(durees) else durees[i]
        calendrier.append(None if (durees[i] is None or suivant is None)
                          else max(durees[i], suivant))

    connues = [d for d in calendrier if d is not None]
    if connues:
        dire(f"    durees simulees prevues, apport par apport : "
             f"{', '.join(f'{d:.1f}' for d in connues)} h "
             f"(chacune couvre aussi l'evenement du suivant, dont elle est "
             f"l'etat de reference)")
    return calendrier


def _noter_bilan(suivi, calcul, config):
    """
    Transmet au suivi le bilan de masse du calcul qui vient de tourner.

    APRES CHAQUE CALCUL, ACCEPTE OU NON. C'est justement le calcul REJETE
    qu'il faut pouvoir lire a l'ecran : sans cela, l'arret « qualite
    numerique » n'expose son chiffre que dans le journal texte, que
    l'utilisateur du plugin n'ouvre pas.
    """
    if suivi is None:
        return
    _sans_interrompre(suivi.noter_bilan_masse, calcul.bilan_masse_pct,
                      config.bilan_masse_max_pct)


def _jalonner(modele, etape, dire):
    """
    Ouvre une etape, et le DIT — qu'elle s'ouvre ou non.

    L'echec n'arrete pas le calage : la trace est un confort, le calage est le
    travail. Il est en revanche annonce, parce qu'un plan attendu qui n'existe
    pas se cherche longtemps si personne n'a dit qu'il n'avait pas ete cree.
    Le modele garantit de son cote qu'un echec le laisse coherent sur l'etape
    precedente — voir PiloteHecRas.jalonner.
    """
    try:
        rendu = modele.jalonner(etape)
    except Exception as e:                                  # noqa: BLE001
        dire(f"    AVERTISSEMENT : étape « {etape} » non ouverte "
             f"({type(e).__name__}: {e}). Le calage continue sur les fichiers "
             f"en place, sans trace séparée de cette étape.")
        return None
    if rendu:
        dire(f"    étape « {etape} » : {rendu}")
    return rendu


def _conclure(modele, titre, dire):
    """
    Titre l'etat final, et le DIT — qu'il soit titre ou non.

    Meme discipline que _jalonner : un echec de titrage (fichier verrouille,
    interface HEC-RAS laissee ouverte) n'annule pas un calage abouti. Il est
    en revanche annonce, ET il nomme le plan qui porte le resultat :
    quarante-six heures de calcul ne doivent pas se terminer par « on ne sait
    plus quel plan regarder ».
    """
    try:
        rendu = modele.conclure(titre)
    except Exception as e:                                  # noqa: BLE001
        dire(f"    AVERTISSEMENT : état final « {titre} » non titré "
             f"({type(e).__name__}: {e}). Le calage est terminé et ses "
             f"résultats sont bons : c'est le plan de la dernière étape "
             f"d'apport qui les porte.")
        return None
    if rendu:
        dire(f"    état final « {titre} » : {rendu}")
    return rendu


# ---------------------------------------------------------------------------
# Assemblage du rapport final
# ---------------------------------------------------------------------------

def _pic_dans_fenetre(temps, debits, fenetre):
    """
    Pic d'une serie, RESTREINT a la fenetre jugee quand il y en a une.

    Le profil en long confronte les pics section par section : ce doit etre
    les memes pics que ceux du tableau de bord, donc ceux de la fenetre. Les
    series finales, elles, sont desormais rendues ENTIERES pour la figure de
    comparaison — sans cette restriction, une mini-crue ou un debit de base
    hors evenement deviendrait le pic affiche au profil.

    Fenetre vide ou absente : le pic de toute la serie, faute de mieux.
    """
    q = np.asarray(debits, dtype=float)
    if fenetre is not None:
        t = np.asarray(temps, dtype=float)
        dedans = (t >= float(fenetre[0])) & (t <= float(fenetre[1]))
        if dedans.any():
            q = q[dedans]
    return float(np.max(q)) if q.size else float("nan")


def produire_livrables_finaux(resultat, modele, dossier_sortie,
                              profil=None, pk_sections=None, pk_apports=None):
    """
    Assemble le rapport final — graphiques, tableaux, export Excel, note de
    synthese — a partir d'un ResultatCalage produit par caler().

    Ne reimplemente AUCUNE regle : livrables.py est appele tel quel, exactement
    comme le fait son propre auto-test. Seule la donnee de resultat.py est mise
    en forme pour ses fonctions. C'est la meme discipline que caler() lui-meme :
    l'assemblage est une couche fine, la logique reste dans les modules qui la
    possedent deja.

    modele : necessaire pour relire l'hydrogramme RETENU de chaque apport. La
    correction etant additive, il n'est pas reconstructible depuis
    resultat.apports — le modele en est la seule source.

    profil, pk_sections, pk_apports : facultatifs. Fournis, ils ajoutent le
    PROFIL EN LONG DE SYNTHESE, seule figure a montrer une derive avec son
    contexte physique. Ils demandent l'axe hydraulique, que la boucle
    n'exige pas — le rapport reste donc complet sans eux.

    Retourne {"fichiers": [...], "conforme": bool}. Peut etre appele meme si
    resultat.conforme est faux, pour produire un rapport de non-conformite
    exploitable plutot que rien — mais exige que la verification globale ait
    bien tourne (resultat.diagnostics_finaux non vide) : sans elle, il n'y a
    rien a rapporter.
    """
    import livrables as liv
    from suivi import assainir_nom_fichier

    if not resultat.diagnostics_finaux:
        raise ValueError(
            "aucun diagnostic final disponible : la verification globale ne "
            "s'est pas executee (calage interrompu avant son terme sur un "
            "apport non valide).")

    # La verification globale ne tourne que si TOUS les apports sont valides :
    # les trois listes ont donc la meme longueur des qu'elle a eu lieu. On le
    # verifie plutot que de s'y fier — un decalage d'indice ferait porter a un
    # apport les series d'un autre, sans rien lever.
    if not (len(resultat.apports) == len(resultat.diagnostics_finaux)
            == len(resultat.series_finales)):
        raise ValueError(
            f"resultat incoherent : {len(resultat.apports)} apport(s), "
            f"{len(resultat.diagnostics_finaux)} diagnostic(s), "
            f"{len(resultat.series_finales)} serie(s) — les trois doivent "
            f"correspondre un a un.")

    sections = [a.nom_section for a in resultat.apports]
    apports = [a.nom_apport for a in resultat.apports]

    dossier = Path(dossier_sortie)
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers = []

    for i, (section, diag) in enumerate(zip(sections, resultat.diagnostics_finaux)):
        t_c, q_c, t_s, q_s = resultat.series_finales[i]
        fichiers.append(liv.figure_comparaison(
            section, t_c, q_c, t_s, q_s, diag,
            dossier / f"comparaison_{i + 1:02d}_{assainir_nom_fichier(section)}.png"))

    fichiers.append(liv.figure_atteinte(
        sections, resultat.diagnostics_finaux, dossier / "atteinte_cible.png"))

    for i, a in enumerate(resultat.apports):
        if len(a.historique) >= 2:
            fichiers.append(liv.figure_convergence(
                a.nom_section, a.historique,
                dossier / f"convergence_{i + 1:02d}_{assainir_nom_fichier(a.nom_apport)}.png"))

    # L'hydrogramme retenu se lit TEL QUEL dans le modele : la correction etant
    # additive, definir_forme() y a deja ecrit la serie finale et le facteur
    # applique vaut 1. La remultiplier par le rapport de volumes — ce que
    # faisait la version multiplicative — l'echelonnerait une seconde fois.
    # L'hydrogramme d'apport vit sur la base de temps du FICHIER UNSTEADY, qui
    # couvre souvent bien plus que la fenetre reellement simulee : au-dela,
    # definir_forme() prolonge par la derniere valeur connue. Rapporter le
    # volume sur toute cette etendue annoncerait un apport que le calcul n'a
    # jamais recu.
    #
    # Les livrables se limitent donc a la FENETRE DE CALAGE, celle de la cible.
    # CHAQUE APPORT PORTE SA PROPRE BASE DE TEMPS. Dans le fichier unsteady,
    # chaque hydrogramme est un bloc avec SON « Interval= » et SON nombre de
    # points ; forme_apport() rend donc un axe par apport, et deux apports du
    # meme modele n'ont aucune raison d'avoir la meme longueur.
    #   LE CODE PRECEDENT GARDAIT UN SEUL AXE, ecrase a chaque tour, et
    #   appliquait le masque du PREMIER apport a l'axe du DERNIER. Mesure sur
    #   un modele de production a douze apports, tous au pas de 6 min : QUATRE
    #   longueurs differentes dans le meme fichier unsteady — 256, 321, 811 et
    #   1 001 points. D'ou « boolean index did not match indexed array : 1001
    #   contre 811 », et un calage de 46 h, douze apports sur douze conformes,
    #   qui a perdu son classeur ET sa note de synthese.
    #   UN AUTRE MODELE DE LA MEME AFFAIRE N'A RIEN VU : ses six apports
    #   portent 500 points chacun. Le defaut ne se voit que sur un modele dont
    #   les apports ont ete saisis a des moments differents.
    temps_apports, hydrogrammes, dans_fenetre = [], [], []
    for i, a in enumerate(resultat.apports):
        t_forme, forme = modele.forme_apport(a.nom_apport)
        t_forme = np.asarray(t_forme, dtype=float)
        forme = np.asarray(forme, dtype=float)
        temps_apports.append(t_forme)
        hydrogrammes.append(forme)
        # LA BORNE EST CELLE DE LA FENETRE JUGEE, prise a sa source. Elle
        # etait lue sur la fin des series finales, qui n'etaient coupees que
        # parce qu'elles l'etaient pour la figure : le jour ou l'on a cesse de
        # les couper, cette borne serait devenue la fin de la CIBLE — jusqu'a
        # 208 h de remplissage a zero sur un cas reel — et l'avertissement de
        # queue n'aurait plus rien signale.
        fin = (float(a.fenetre_principale[1]) if a.fenetre_principale is not None
               else float(np.max(resultat.series_finales[i][0])))
        dans_fenetre.append(t_forme <= fin + 1e-9)
    if temps_apports:
        # MEME GARDE-FOU QUE LE PROFIL EN LONG PLUS BAS : une figure qui
        # echoue ne doit plus emporter le classeur et la note de synthese,
        # qui sont produits APRES elle. C'est exactement ce que la panne
        # ci-dessus a coute.
        try:
            fichiers.append(liv.figure_apports_retenus(
                apports, [t[g] for t, g in zip(temps_apports, dans_fenetre)],
                [h[g] for h, g in zip(hydrogrammes, dans_fenetre)],
                dossier / "apports_retenus.png"))
        except Exception as e:
            fichiers.append(f"apports retenus non produits : "
                            f"{type(e).__name__}: {e}")

        # Une queue constante au-dela de la fenetre n'a aucun effet ICI, mais
        # l'apport injecterait ce debit des que la simulation serait allongee.
        # Le dire vaut mieux que le laisser decouvrir.
        for nom, t_a, h, g in zip(apports, temps_apports, hydrogrammes,
                                  dans_fenetre):
            queue = h[~g]
            if len(queue) > 2 and float(np.max(queue)) > 0.01 * float(np.max(h)):
                fichiers.append(
                    f"AVERTISSEMENT — l'apport « {nom} » est prolonge a "
                    f"{float(queue[0]):.1f} m3/s sur "
                    f"{len(queue) * float(t_a[1] - t_a[0]):.0f} h "
                    f"au-dela de la fenetre simulee. Sans effet sur ce calcul, "
                    f"mais ce debit serait injecte si la fenetre etait "
                    f"allongee.")

    # --- profil en long de synthese, si l'axe hydraulique est disponible ---
    if profil is not None and len(profil):
        try:
            fichiers.append(liv.figure_profil_en_long(
                profil, pk_sections, dossier / "profil_en_long.png",
                noms_sections=sections, apports_pk=pk_apports,
                noms_apports=apports,
                pics_cible=[_pic_dans_fenetre(s[0], s[1], a.fenetre_principale)
                            for s, a in zip(resultat.series_finales,
                                            resultat.apports)],
                pics_calcule=[_pic_dans_fenetre(s[2], s[3], a.fenetre_principale)
                              for s, a in zip(resultat.series_finales,
                                              resultat.apports)]))
        except Exception as e:
            fichiers.append(f"profil en long non produit : "
                            f"{type(e).__name__}: {e}")

    tb = liv.tableau_de_bord(sections, resultat.diagnostics_finaux,
                             nb_essais=[a.essais for a in resultat.apports])
    # Pic et volume sur la FENETRE DE CALAGE seulement (cf. plus haut).
    ta = liv.tableau_apports(
        apports, [a.facteur for a in resultat.apports],
        [float(np.max(h[g])) for h, g in zip(hydrogrammes, dans_fenetre)],
        [float(np.trapezoid(h[g], t_a[g])) * 3.6
         for h, t_a, g in zip(hydrogrammes, temps_apports, dans_fenetre)])
    # LA SERIE, et pas seulement son pic et son volume : c'est elle qu'on
    # rejoue dans un autre modele et qu'on superpose a la cible. Chaque apport
    # est coupe a SA fenetre, la meme que celle du pic et du volume ci-dessus
    # — une feuille qui irait plus loin ne donnerait pas le volume annonce.
    th = liv.tableau_hydrogrammes_apports(
        apports, [t_a[g] for t_a, g in zip(temps_apports, dans_fenetre)],
        [h[g] for h, g in zip(hydrogrammes, dans_fenetre)])
    je = liv.journal_essais([
        dict(apport=a.nom_apport, **essai)
        for a in resultat.apports for essai in a.historique])

    xlsx = liv.exporter_excel(dossier / "tableaux_calage.xlsx",
                             Tableau_de_bord=tb, Apports=ta,
                             Hydrogrammes_apports=th, Journal=je)
    liv.synthese("Calage des apports — note de synthèse", sections,
                resultat.diagnostics_finaux, dossier / "synthese.md",
                alertes_chaine=resultat.alertes_chaine)

    return {"fichiers": fichiers + [xlsx, str(dossier / "synthese.md")],
            "conforme": resultat.conforme}


# ---------------------------------------------------------------------------
# Modele fictif, pour eprouver la boucle sans HEC-RAS
# ---------------------------------------------------------------------------


class ModeleFictif(Modele):
    """
    Modele-jouet : chaque section recoit la somme des apports amont, laminee
    d'autant plus fortement que le debit est eleve, et retardee.

    Le laminage NON LINEAIRE reste un parametre du constructeur, mais son
    defaut est desormais NUL (voir laminage) : la correction directe a un
    seul terme suppose un troncon transparent (gain hydraulique EXACTEMENT
    1) et n'est plus, depuis la simplification du 07/08/2026, censee
    converger sur un troncon qui lamine, meme faiblement — a fortiori sur
    plusieurs sections en chaine, ou une legere non-linearite a chaque
    section se cumule d'un apport au suivant. C'est desormais hors du
    perimetre de cette version (voir le docstring du module) : mesurer la
    tenue face au laminage etait le role du mode par defaut, retire.
    """

    def __init__(self, apports, sections, temps, formes, laminage=0.0,
                 retard_h=0.4, bilan_masse_pct=0.002, duree_calcul_s=0.0,
                 seuil_instabilite=None, bilan_masse_instable=5.0,
                 debit_base=None):
        """
        seuil_instabilite : au-dela de cette somme de facteurs, le modele
            rend un bilan de masse degrade. Permet d'eprouver le rejet d'un
            essai EN COURS de recherche, distinct d'un modele douteux des le
            depart — que caler() arrete maintenant au calcul de reference.

        debit_base : debit arrivant aux sections independamment des apports a
            caler — entrees amont non calees, affluents. TOUS LES MODELES
            N'EN ONT PAS : un modele dont toutes les entrees sont calees
            presente un debit nul une fois les apports mis a zero, et c'est
            un cas parfaitement normal que la boucle traite (l'ecart a
            combler vaut alors la cible entiere).
            Le parametre sert a eprouver le cas INVERSE, celui ou la section
            recoit deja plus que la cible : il ne peut se produire que s'il
            existe un debit non cale, puisqu'un apport ne sait qu'ajouter.
        """
        self.apports, self.sections = list(apports), list(sections)
        self.temps = np.asarray(temps, dtype=float)
        self.formes = {a: np.asarray(f, dtype=float)
                       for a, f in zip(apports, formes)}
        self.facteurs = {a: 0.0 for a in apports}
        self.laminage = laminage
        self.retard_h = retard_h
        self.bilan_masse_pct = bilan_masse_pct
        self.duree_calcul_s = duree_calcul_s
        self.seuil_instabilite = seuil_instabilite
        self.bilan_masse_instable = bilan_masse_instable
        self.debit_base = (np.zeros_like(self.temps) if debit_base is None
                           else np.asarray(debit_base, dtype=float))
        self.nb_calculs = 0
        # Etapes traversees, dans l'ordre. Le modele fictif ne conserve rien —
        # il n'a pas de fichiers — mais il note ce qu'on lui demande de jalonner
        # pour que l'auto-test verifie les noms sans HEC-RAS.
        self.etapes = []
        # Duree simulee imposee par limiter_duree(). None = fenetre entiere,
        # c'est-a-dire l'etat de tout calcul de reference.
        self.duree_max = None
        self.durees_demandees = []

    def preparer(self):
        self.facteurs = {a: 0.0 for a in self.apports}

    def jalonner(self, etape):
        self.etapes.append(etape)
        return None

    def conclure(self, etape):
        # Le retitrage REMPLACE l'etape courante, il n'en ajoute pas une : le
        # plan est le meme. C'est ce que l'auto-test verifie, sans HEC-RAS.
        if self.etapes:
            self.etapes[-1] = etape
        return None

    def limiter_duree(self, heures):
        """
        Note la duree demandee, et la RESPECTE en tronquant les series lues.

        TRONQUER POUR DE VRAI, ET NON SEULEMENT ENREGISTRER LE CHIFFRE : c'est
        ce qui fait de ce modele une epreuve. Un mannequin qui se contente de
        retenir la valeur laisserait passer une troncature qui ampute la
        fenetre de jugement — le calage continuerait de voir des series
        completes et rien ne signalerait la faute.

        MEME REGLE QUE LE PILOTE REEL : on ne depasse pas la fenetre de
        reference — ici, la duree de la serie — mais on peut RALLONGER en deca.
        Interdire d'allonger bornerait tout le calage a l'evenement du premier
        apport, chaque etape heritant de la fenetre raccourcie de la
        precedente. C'est le defaut que cet auto-test a attrape.
        """
        if heures is None or heures <= 0:
            return None
        plafond = float(self.temps[-1])
        voulue = min(float(heures), plafond)
        if self.duree_max is not None and abs(voulue - self.duree_max) < 1e-9:
            return None
        self.duree_max = voulue
        self.durees_demandees.append(voulue)
        return voulue

    def forme_apport(self, nom_apport):
        return self.temps, self.formes[nom_apport]

    def appliquer_facteur(self, nom_apport, facteur):
        self.facteurs[nom_apport] = float(facteur)

    def definir_forme(self, nom_apport, temps_h, debits):
        self.formes[nom_apport] = np.interp(
            self.temps, np.asarray(temps_h, dtype=float),
            np.asarray(debits, dtype=float))

    def calculer(self):
        self.nb_calculs += 1
        if self.duree_calcul_s:
            time.sleep(self.duree_calcul_s)
        bilan = self.bilan_masse_pct
        # Un modele qui ne devient instable qu'AU-DELA d'un certain apport :
        # indispensable pour eprouver le rejet d'un essai EN COURS de
        # recherche. Un modele mauvais des le depart, lui, est desormais
        # arrete au calcul de reference, donc n'atteint jamais cette branche.
        if self.seuil_instabilite is not None:
            total = sum(self.facteurs.values())
            if total > self.seuil_instabilite:
                bilan = self.bilan_masse_instable
        return ResultatCalcul(reussi=True, duree_s=self.duree_calcul_s,
                              bilan_masse_pct=bilan)

    def lire_section(self, nom_section):
        rang = self.sections.index(nom_section)
        total = self.debit_base.copy()
        for a in self.apports[:rang + 1]:
            total = total + self.facteurs[a] * self.formes[a]
        # Laminage non lineaire, puis retard.
        lamine = total / (1.0 + self.laminage * total / max(total.max(), 1e-9))
        pas = self.temps[1] - self.temps[0]
        decalage = int(round((rang + 1) * self.retard_h / pas))
        if decalage:
            lamine = np.concatenate([np.full(decalage, lamine[0]),
                                     lamine[:-decalage]])
        # LA TRONCATURE EST REELLE : la serie s'arrete ou le calcul se serait
        # arrete. C'est ce que fait un solveur dont on raccourcit la fenetre,
        # et c'est la seule facon d'eprouver que le raccourcissement ne coute
        # pas la fenetre de jugement.
        if self.duree_max is not None:
            garde = self.temps <= self.duree_max + 1e-9
            return self.temps[garde], lamine[garde]
        return self.temps, lamine


# ---------------------------------------------------------------------------
# Auto-test
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
    import tempfile
    from pathlib import Path

    from suivi import Suivi, nom_onglet

    def _onglets(chemin):
        """Noms des onglets d'un classeur, ou [] s'il n'est pas lisible."""
        import openpyxl
        try:
            return openpyxl.load_workbook(chemin, read_only=True).sheetnames
        except Exception:                                   # noqa: BLE001
            return []

    print("=" * 74)
    print("AUTO-TEST DE LA BOUCLE DE CALAGE — modele fictif, reponse connue")
    print("=" * 74)

    def hydrogramme(t, pic, t_pic=6.0, forme=2.5):
        t = np.maximum(np.asarray(t, dtype=float), 1e-3)
        return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))

    temps = np.linspace(0.01, 36, 400)
    # Nommes comme les conditions limites d'un vrai modele — « A1 » et non
    # « Apport_1 » : les etapes du calage s'appellent « Apport_<nom> », et un
    # nom deja prefixe rendrait « Apport_Apport_1 » illisible dans le controle.
    apports = ["A1", "A2", "A3", "A4"]
    sections = ["S1_Amont", "S2_Pont", "S3_Confluence", "S4_Aval"]
    formes = [hydrogramme(temps, 10.0) for _ in apports]

    # Laminage faible (2 %) : le domaine de validite de la correction directe
    # (§ methodologie V1.3, hypothese « troncon transparent »). Ce test n'a
    # plus a demontrer la precision face a un fort laminage — c'etait le role
    # du mode par defaut, retire lors de la simplification du 07/08/2026.
    modele = ModeleFictif(apports, sections, temps, formes)

    # Cibles obtenues EN FAISANT TOURNER le modele avec des facteurs connus :
    # la bonne reponse est donc connue exactement, et un echec de la boucle
    # designe le code, jamais les donnees.
    facteurs_vrais = [4.5, 3.4, 3.6, 3.5]
    for a, f in zip(apports, facteurs_vrais):
        modele.appliquer_facteur(a, f)
    cibles = [modele.lire_section(s) for s in sections]
    for i, (s, (_, q)) in enumerate(zip(sections, cibles)):
        print(f"   cible {s:16s} pic {float(np.max(q)):7.2f} m3/s "
              f"(facteur vrai {facteurs_vrais[i]})")

    sortie = Path(tempfile.gettempdir()) / "calage_boucle_test"
    suivi = Suivi(sortie, apports, sections, titre="Test a blanc")

    modele.preparer()
    resultat = caler(modele, apports, sections, cibles,
                     Configuration(nb_max_essais=8),
                     suivi=suivi)

    print(f"\n--- BILAN ---")
    print(f"   {resultat.nb_calculs} calculs, "
          f"{sum(a.essais for a in resultat.apports)} essais retenus")
    # La correction etant ADDITIVE, il n'y a plus de facteur scalaire a
    # comparer : c'est l'HYDROGRAMME INJECTE qui doit retrouver celui ayant
    # servi a fabriquer la cible. Controle plus exigeant qu'un scalaire — il
    # porte sur le volume, la pointe ET la forme, c'est-a-dire exactement ce
    # que la methode promet.
    vrais_hydrogrammes = {a: formes[k] * facteurs_vrais[k]
                          for k, a in enumerate(apports)}
    ecarts_volume, ecarts_pic = [], []
    for a in resultat.apports:
        obtenu = modele.formes[a.nom_apport] * modele.facteurs[a.nom_apport]
        attendu = vrais_hydrogrammes[a.nom_apport]
        e_v = abs(_volume(temps, obtenu) / _volume(temps, attendu) - 1)
        e_p = abs(float(np.max(obtenu)) / float(np.max(attendu)) - 1)
        ecarts_volume.append(e_v)
        ecarts_pic.append(e_p)
        print(f"   {a.nom_apport:10s} volume {100 * e_v:+5.1f} %  "
              f"pointe {100 * e_p:+5.1f} %  "
              f"volume {100 * a.diagnostic.rapport_volume:5.1f} %  "
              f"pointe {100 * a.diagnostic.rapport_pic:5.1f} %  "
              f"{a.essais} essai(s)")
    print(f"   conforme : {resultat.conforme}")

    # --- controles ---------------------------------------------------------
    print("\n--- CONTROLES ---")
    echecs = []

    def controler(libelle, condition, detail=""):
        print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
              + (f"  ->  {detail}" if detail else ""))
        if not condition:
            echecs.append(libelle)

    controler("tous les apports valides",
              all(a.valide for a in resultat.apports),
              f"{sum(a.valide for a in resultat.apports)}/{len(apports)}")
    controler("calage conforme a la verification finale", resultat.conforme)
    controler("hydrogrammes retrouves en VOLUME a mieux que 5 %",
              max(ecarts_volume) < 0.05,
              f"ecart max {100 * max(ecarts_volume):.2f} %")
    controler("hydrogrammes retrouves en POINTE a mieux que 5 %",
              max(ecarts_pic) < 0.05,
              f"ecart max {100 * max(ecarts_pic):.2f} %")
    # LA CONCORDANCE PORTE SUR LE VOLUME, LA POINTE ET LA FORME — RIEN D'AUTRE.
    _c = Configuration()
    _faux = type("D", (), {"rapport_volume": 1.0, "rapport_pic": 1.0,
                           "r": 0.99})()
    controler("volume, pointe et forme conformes : la concordance est acquise",
              concordance(_faux, _c), "volume/pointe/forme conformes")
    _faux_pic = type("D", (), {"rapport_volume": 1.0, "rapport_pic": 1.5,
                               "r": 0.99})()
    controler("une pointe fausse arrete la concordance",
              not concordance(_faux_pic, _c), f"pic {_faux_pic.rapport_pic}")

    controler("concordance simultanee volume / pointe / forme a chaque section",
              all(d.converge for d in resultat.diagnostics_finaux),
              "  ".join(f"{d.rapport_volume:.3f}/{d.rapport_pic:.3f}/{d.r:.3f}"
                        for d in resultat.diagnostics_finaux))
    controler("convergence econome (<= 6 essais par apport)",
              max(a.essais for a in resultat.apports) <= 6,
              f"max {max(a.essais for a in resultat.apports)}")
    controler("suivi produit", (sortie / "avancement.md").exists()
              and (sortie / "avancement.png").exists())
    controler("un onglet d'iterations par apport",
              (sortie / "iterations.xlsx").exists()
              and _onglets(sortie / "iterations.xlsx")
              == [nom_onglet(a) for a in apports],
              f"{_onglets(sortie / 'iterations.xlsx')}")

    # ETAPES JALONNEES : une pour l'etat de reference, une par apport, dans
    # l'ordre. C'est ce qui donne leurs noms aux plans conserves sous HEC-RAS.
    # LA DERNIERE A CHANGE DE NOM, et c'est la correction du 03/09 : le plan du
    # dernier apport porte tous les apports cales et leurs resultats ; il
    # s'appelle desormais « avec apports » et non « Apport_<dernier> ».
    controler("etapes jalonnees dans l'ordre",
              modele.etapes[:-1] == [ETAPE_SANS_APPORT]
              + [etape_apport(a) for a in apports[:-1]],
              " | ".join(modele.etapes))
    controler("l'etat final est titre « avec apports », pas du nom du dernier "
              "apport",
              modele.etapes[-1] == ETAPE_AVEC_APPORTS, modele.etapes[-1])

    # --- PREFIXE DE SCENARIO -----------------------------------------------
    print("\n--- PREFIXE DE SCENARIO ---")

    # RETROCOMPATIBILITE, LE CONTROLE QUI PROTEGE LES CALAGES DEJA FAITS :
    # prefixe vide = les titres d'avant, au caractere pres.
    controler("prefixe vide : les titres d'etape sont inchanges",
              titre_etape(ETAPE_SANS_APPORT) == "sans apport"
              and titre_etape(ETAPE_SANS_APPORT, "") == "sans apport"
              and etape_apport("A1") == "Apport_A1"
              and etape_apport("A1", "") == "Apport_A1",
              f"{titre_etape(ETAPE_SANS_APPORT)!r} / {etape_apport('A1')!r}")
    controler("prefixe renseigne : il precede le titre",
              titre_etape(ETAPE_SANS_APPORT, "Q100") == "Q100-sans apport"
              and etape_apport("APP06", "Q100") == "Q100-Apport_APP06"
              and titre_etape(ETAPE_AVEC_APPORTS, "Q100")
              == "Q100-avec apports",
              etape_apport("APP06", "Q100"))
    # « Q100 » et « Q100- » DOIVENT rendre le meme titre : _remplacer_homonymes
    # et plan_par_titre comparent le Plan Title caractere pour caractere, et
    # deux ecritures du meme prefixe fabriqueraient les plans en double que ce
    # prefixe existe pour supprimer.
    controler("le separateur n'est jamais double",
              titre_etape("sans apport", "Q100-")
              == titre_etape("sans apport", " Q100 ") == "Q100-sans apport")
    controler("un prefixe finissant par « _ » garde le sien",
              etape_apport("A1", "Q100_") == "Q100_Apport_A1")
    # LE CAS DE LA DEMANDE, MOT POUR MOT : 26 caracteres, refuses par une borne
    # a 24 qui n'etait pas celle de HEC-RAS.
    controler("« Riviere1-Q100 » donne « Riviere1-Q100-avec apports »",
              titre_etape(ETAPE_AVEC_APPORTS, "Riviere1-Q100")
              == "Riviere1-Q100-avec apports")
    # AU-DELA, ON REFUSE — jamais on ne tronque : deux titres rognes au meme
    # « Short Identifier » partagent le dossier de resultats que RAS Mapper
    # nomme d'apres ce champ. C'est le doublon que le prefixe supprime, et il
    # serait absurde qu'il le refabrique.
    try:
        etape_apport("APP06", "Riviere1_Q100_1000")     # 18 + 1 + 12 = 31
        _refus = ""
    except ValueError as _e:
        _refus = str(_e)
    controler("un titre de 31 caracteres est REFUSE, pas tronque",
              bool(_refus), _refus or "aucune erreur levee")
    controler("le refus dit de combien raccourcir",
              "1 caractere(s)" in _refus, _refus)

    # LE CALAGE ENTIER SOUS PREFIXE. On rejoue caler() plutot que d'eprouver la
    # seule fonction : c'est caler() qui doit poser le prefixe PARTOUT, etat de
    # reference et plan final compris.
    modele_p = ModeleFictif(apports, sections, temps, formes)
    r_p = caler(modele_p, apports, sections, cibles,
                Configuration(nb_max_essais=8, prefixe_etape="Q100"),
                journal=lambda *a, **k: None)
    controler("caler() prefixe TOUTES les etapes, plan final compris",
              modele_p.etapes == ["Q100-sans apport"]
              + [f"Q100-Apport_{a}" for a in apports[:-1]]
              + ["Q100-avec apports"],
              " | ".join(modele_p.etapes))
    controler("le prefixe ne change rien au resultat du calage",
              r_p.conforme, r_p.motif)

    # --- rapport final ------------------------------------------------------
    print("\n--- ASSEMBLAGE DU RAPPORT FINAL ---")
    dossier_rapport = sortie / "rapport_final"
    rapport = produire_livrables_finaux(resultat, modele, dossier_rapport)
    controler("rapport conforme", rapport["conforme"])
    # 4 comparaisons + 1 atteinte + 1 apports_retenus + xlsx + synthese = 8.
    # PAS de figure de convergence attendue ICI : sur un troncon transparent
    # (le defaut du modele fictif depuis la simplification du 07/08/2026),
    # chaque apport converge en un seul essai, et figure_convergence exige
    # au moins deux essais pour avoir quelque chose a tracer.
    controler("fichiers produits", len(rapport["fichiers"]) >= 8,
              f"{len(rapport['fichiers'])} fichier(s)")
    controler("4 figures de comparaison",
              len(list(dossier_rapport.glob("comparaison_*.png"))) == 4)
    import pandas as pd
    journal = pd.read_excel(dossier_rapport / "tableaux_calage.xlsx",
                            sheet_name="Journal")
    controler("le diagnostic par essai n'est plus NaN dans le journal",
              journal["pic"].notna().all() and journal["volume"].notna().all(),
              f"{journal['pic'].notna().sum()}/{len(journal)} valeurs")
    tb_final = pd.read_excel(dossier_rapport / "tableaux_calage.xlsx",
                             sheet_name="Tableau_de_bord")
    controler("tableau de bord final a 4 sections", len(tb_final) == 4)
    controler("le tableau de bord est fidele aux diagnostics",
              all(abs(tb_final.loc[i, "Volume (% cible)"]
                      - round(100 * d.rapport_volume, 1)) < 1e-9
                  and abs(tb_final.loc[i, "Débit de pointe (% cible)"]
                          - round(100 * d.rapport_pic, 1)) < 1e-9
                  for i, d in enumerate(resultat.diagnostics_finaux)))
    controler("aucune colonne KGE dans le livrable",
              not any(c in tb_final.columns
                      for c in ("KGE", "r", "alpha", "beta")),
              " | ".join(tb_final.columns))

    # --- LA FIGURE FINALE COUVRE LA CRUE, PAS LA FENETRE JUGEE ------------
    #
    # Les series finales etaient coupees a la fenetre de jugement AVANT d'etre
    # tracees. La figure du rapport montrait donc moins que celle du suivi,
    # avec la meme legende — et cachait la decrue, la ou un modele s'ecarte
    # volontiers de sa cible. figure_comparaison cadre deja seule.
    print("\n--- LES SERIES DU RAPPORT NE SONT PLUS COUPEES ---")
    _avec_fen = [(a, s) for a, s in zip(resultat.apports, resultat.series_finales)
                 if a.fenetre_principale is not None]
    controler("une fenetre de jugement est bien posee sur ce cas",
              bool(_avec_fen),
              f"{len(_avec_fen)}/{len(resultat.apports)} apport(s)")
    if _avec_fen:
        # Celui dont la fenetre coupe le plus : c'est lui qui revelait le
        # defaut, et c'est sur lui que le banc doit porter.
        _a, _s = min(_avec_fen, key=lambda x: x[0].fenetre_principale[1])
        _t_modele, _ = modele.lire_section(_a.nom_section)
        _fin_serie = float(np.max(_s[2]))
        _fin_fen = float(_a.fenetre_principale[1])
        _fin_modele = float(np.max(_t_modele))
        controler("la fenetre jugee est bien plus courte que la simulation",
                  _fin_fen < _fin_modele - 1e-9,
                  f"fenetre {_fin_fen:.2f} h, modele {_fin_modele:.2f} h")
        controler("et la serie du rapport va jusqu'au bout du calcul",
                  abs(_fin_serie - _fin_modele) < 1e-9,
                  f"serie {_fin_serie:.2f} h pour un modele a {_fin_modele:.2f} h")

    # --- DES APPORTS A BASES DE TEMPS DIFFERENTES -------------------------
    #
    # LE CAS QUI A FAIT PERDRE SES LIVRABLES A UN CALAGE DE 46 HEURES. Dans un
    # fichier unsteady, chaque apport est un bloc avec son propre
    # « Interval= » et son propre nombre de points. Le modele fictif, lui, rend
    # le meme axe pour tous : ce banc lui met une doublure qui rend un axe PAR
    # APPORT, de longueurs differentes, comme le fait un modele reel.
    # Mesure en production : 256, 321, 811 et 1 001 points chez douze apports.
    print("\n--- LIVRABLES : DES APPORTS A BASES DE TEMPS DIFFERENTES ---")

    class _ModeleBasesHeterogenes:
        """Le modele cale, mais dont chaque apport a sa propre base de temps."""

        def __init__(self, reel, noms):
            self._reel = reel
            self._axes = {}
            for k, nom in enumerate(noms):
                t_a, q_a = reel.forme_apport(nom)
                # Longueurs volontairement toutes differentes, et la PREMIERE
                # n'est ni la plus courte ni la plus longue : un masque pris
                # sur elle est alors trop court pour les uns, trop long pour
                # les autres.
                n = len(t_a) - 7 * ((k + 3) % 5)
                self._axes[nom] = (np.asarray(t_a)[:n], np.asarray(q_a)[:n])

        def forme_apport(self, nom_apport):
            return self._axes[nom_apport]

        def __getattr__(self, nom):
            return getattr(self._reel, nom)

    # ETANCHEITE : le dossier est efface AVANT, sinon les fichiers d'un run
    # precedent feraient verdir ce controle sur du code casse. C'est le piege
    # que STATUT.txt nomme — un controle qui s'ignore lui-meme ne controle
    # rien — et il s'applique aussi aux dossiers temporaires reutilises.
    import shutil
    _dossier_het = sortie / "rapport_bases_heterogenes"
    shutil.rmtree(_dossier_het, ignore_errors=True)
    _modele_het = _ModeleBasesHeterogenes(modele, apports)
    _tailles = sorted({len(_modele_het.forme_apport(a)[0]) for a in apports})
    controler("la doublure rend bien des axes de longueurs differentes",
              len(_tailles) == len(apports), str(_tailles))
    try:
        _rap_het = produire_livrables_finaux(resultat, _modele_het, _dossier_het)
        _leve = None
    except Exception as e:                                   # noqa: BLE001
        _rap_het, _leve = None, f"{type(e).__name__}: {e}"
    controler("le rapport ne leve plus sur des bases heterogenes",
              _leve is None, _leve or "aucune exception")
    controler("le classeur, la note et la figure sont tous produits",
              (_dossier_het / "tableaux_calage.xlsx").is_file()
              and (_dossier_het / "synthese.md").is_file()
              and (_dossier_het / "apports_retenus.png").is_file(),
              ", ".join(sorted(f.name for f in _dossier_het.glob("*")))[:110])

    # L'APPORT EXPORTE EST-IL CELUI QUI EST DANS LE MODELE ?
    ap_final = pd.read_excel(dossier_rapport / "tableaux_calage.xlsx",
                             sheet_name="Apports")
    pics_modele = [float(np.max(modele.forme_apport(a.nom_apport)[1]))
                   for a in resultat.apports]
    controler("le pic injecte exporte est celui du modele",
              all(abs(ap_final.loc[i, "Pic injecte (m3/s)"] - p) < 0.02
                  for i, p in enumerate(pics_modele)),
              "  ".join(f"{ap_final.loc[i, 'Pic injecte (m3/s)']:.1f}"
                        f"/{p:.1f}" for i, p in enumerate(pics_modele)))

    # --- LA SERIE RETENUE, ET PAS SEULEMENT SON PIC -----------------------
    #
    # Le classeur ne portait que des INDICATEURS AGREGES : une ligne par
    # apport, pic et volume. L'hydrogramme lui-meme ne vivait que dans une
    # figure et dans le fichier unsteady du modele — ni verifiable ligne a
    # ligne, ni reutilisable hors HEC-RAS. La feuille en donne la serie, dans
    # la meme forme que la feuille « Cibles » du classeur de saisie.
    print("\n--- LE CLASSEUR PORTE LES HYDROGRAMMES RETENUS ---")
    _hy = pd.read_excel(dossier_rapport / "tableaux_calage.xlsx",
                        sheet_name="Hydrogrammes_apports")
    controler("une colonne de temps et une colonne par apport",
              list(_hy.columns) == ["Temps_h"]
              + [f"Apport_{a}" for a in apports],
              " | ".join(map(str, _hy.columns)))
    controler("le temps est strictement croissant",
              bool((_hy["Temps_h"].diff().dropna() > 0).all()),
              f"{len(_hy)} pas de {_hy['Temps_h'].iloc[0]:.2f} a "
              f"{_hy['Temps_h'].iloc[-1]:.2f} h")
    # LA MEME VALEUR QUE LE MODELE, pas une valeur plausible : c'est tout
    # l'interet d'exporter la serie plutot que de la redessiner.
    controler("chaque colonne porte le pic de son apport dans le modele",
              all(abs(float(_hy[f"Apport_{a.nom_apport}"].max()) - p) < 0.02
                  for a, p in zip(resultat.apports, pics_modele)),
              "  ".join(f"{float(_hy[f'Apport_{a.nom_apport}'].max()):.1f}/{p:.1f}"
                        for a, p in zip(resultat.apports, pics_modele)))
    # BASES HETEROGENES : les colonnes s'alignent sur l'union des instants, et
    # la ou un apport n'a pas de valeur la cellule reste VIDE. Y interpoler
    # ecrirait un debit que le calcul n'a jamais recu.
    _hy_het = pd.read_excel(_dossier_het / "tableaux_calage.xlsx",
                            sheet_name="Hydrogrammes_apports")
    # Chaque apport s'arretant a SA fenetre, les colonnes n'ont pas la meme
    # hauteur : il DOIT rester des cellules vides. Zero trou signifierait
    # qu'on a prolonge ou interpole quelque part.
    controler("sur des bases heterogenes, les trous restent vides",
              bool(_hy_het.isna().any().any())
              and len(_hy_het.columns) == len(apports) + 1,
              f"{len(_hy_het)} lignes, {len(_hy_het.columns)} colonnes, "
              f"{int(_hy_het.isna().sum().sum())} cellule(s) vide(s)")

    # Depart volontairement faux, comme dans un vrai test a blanc.
    print("\n--- DEPART FAUSSE (x0,6), comme au test a blanc T4 ---")
    modele2 = ModeleFictif(apports, sections, temps, formes)
    modele2.preparer()
    for a, f in zip(apports, facteurs_vrais):
        modele2.appliquer_facteur(a, 0.6 * f)
    r2 = caler(modele2, apports, sections, cibles,
              Configuration(nb_max_essais=8),
              journal=lambda *a, **k: None)
    ecarts2 = [
        abs(_volume(temps, modele2.formes[a.nom_apport]
                    * modele2.facteurs[a.nom_apport])
            / _volume(temps, vrais_hydrogrammes[a.nom_apport]) - 1)
        for a in r2.apports]
    print(f"   {r2.nb_calculs} calculs, ecart de volume max "
          f"{100 * max(ecarts2):.2f} %, conforme : {r2.conforme}")
    # Le depart n'a plus d'influence : la correction additive remplace
    # l'hydrogramme des le premier essai.
    controler("le depart fausse n'influe pas sur le resultat",
              r2.conforme and max(ecarts2) < 0.05,
              f"ecart de volume max {100 * max(ecarts2):.2f} %")

    # -----------------------------------------------------------------------
    # LA FORMULE MANUELLE EST CELLE DU CODE — verification directe contre le
    # classeur de reference (Example_manuel_methodo.xlsx) : decalage mesure
    # UNE FOIS (pic contre pic), puis cible(t - Δt) - section(t), plancher a
    # zero, sans aucun autre terme.
    # -----------------------------------------------------------------------
    print("\n--- LA FORMULE MANUELLE EST CELLE DU CODE ---")
    _mt = np.linspace(0.0, 20.0, 201)
    _mp = lambda t0: 50.0 * np.exp(-((_mt - t0) ** 2) / 2.0)  # noqa: E731
    _m_cible, _m_section = _mp(9.0), _mp(6.0)   # section en avance de 3 h
    _m_dt = decalage_minimisant_ecart(_mt, _m_cible, _mt, _m_section)
    _m_manuel = np.maximum(
        np.interp(_mt - _m_dt, _mt, _m_cible) - _m_section, 0.0)
    _m_code = corriger_apport(
        np.zeros_like(_mt),
        ecart_a_la_cible(_mt, _m_cible, _mt, _m_section, _m_dt))
    controler("la formule manuelle (cible(t-Δt) - section(t)) coincide avec "
              "corriger_apport(0, ecart_a_la_cible(...))",
              float(np.max(np.abs(_m_manuel - _m_code))) < 1e-9,
              f"ecart max {float(np.max(np.abs(_m_manuel - _m_code))):.2e}")

    print("\n--- FENETRE DE L'EVENEMENT PRINCIPAL (jugement et presentation) ---")
    _tf_t = np.linspace(0.0, 48.0, 481)          # 48 h au pas de 6 min
    _tf_ecart = 30.0 * np.exp(-((_tf_t - 12.0) ** 2) / 4.0)
    _t0, _tfin = fenetre_injection(_tf_t, _tf_ecart)
    controler("la fenetre enserre l'evenement, pas toute la simulation",
              0.0 < _t0 < 12.0 < _tfin < 48.0, f"{_t0:.2f} h -> {_tfin:.2f} h")
    controler("t0 capte plus large que tf ne coupe (asymetrie voulue)",
              (12.0 - _t0) > (_tfin - 12.0),
              f"montee {12.0 - _t0:.2f} h contre descente {_tfin - 12.0:.2f} h")
    controler("un ecart nul rend la fenetre complete",
              fenetre_injection(_tf_t, np.zeros_like(_tf_t)) == (0.0, 48.0))
    controler("les bornes imposees remplacent la detection",
              fenetre_injection(_tf_t, _tf_ecart, t0_impose=5.0,
                                tf_impose=20.0) == (5.0, 20.0))
    controler("le masque de fenetre est vrai bornes comprises",
              bool(masque_fenetre(np.array([0.0, 5.0, 10.0]),
                                  (5.0, 10.0)).tolist() == [False, True, True]))
    controler("Fenetre_active=non desactive la fenetre (jugement sur tout)",
              caler(ModeleFictif(["A"], ["S"], temps,
                                 [hydrogramme(temps, 10.0)]),
                    ["A"], ["S"], [cibles[0]],
                    Configuration(fenetre_active=False, nb_max_essais=4),
                    journal=lambda *a, **k: None
                    ).apports[0].fenetre_principale is None)

    print("\n--- Δt MESURE AU RESIDUEL, PAS FORCE A ZERO ---")
    # Le residuel, avant tout apport, porte deja un temps de transfert propre
    # depuis l'amont non cale, independant de l'apport qu'on cale. Modele
    # minimal qui le reproduit : le residuel est un signal FIXE, deja decale
    # de la cible, et l'apport s'y ajoute SANS retard propre.
    # UNE CLASSE ModeleResiduelDecale VIVAIT ICI, ET N'A JAMAIS ETE
    # INSTANCIEE (P2-9 de AUDIT.md). Elle datait d'une epoque ou ce cas
    # s'eprouvait en faisant tourner un calage complet ; les deux controles
    # ci-dessous ont depuis ete ramenes a ce qu'ils verifient vraiment —
    # decalage_minimisant_ecart et ecart_a_la_cible, deux fonctions PURES,
    # sans modele ni boucle. Elle est retiree : du code que rien n'appelle
    # vieillit sans que rien ne l'eprouve, et donne a croire qu'un cas est
    # couvert. Git la garde si elle devait resservir.

    _t3 = np.linspace(0.0, 20.0, 201)
    _pic3 = lambda t0, a: a * np.exp(-((_t3 - t0) ** 2) / 2.0)  # noqa: E731
    _cible3 = _pic3(9.0, 50.0)
    # Amplitude MODESTE par rapport a la cible : le residuel reste un signal
    # fixe (l'apport ne peut pas le retirer), et une amplitude trop proche de
    # la cible laisserait une bosse residuelle qui degraderait la FORME sans
    # qu'aucune correction additive ne puisse jamais l'effacer — ce ne serait
    # alors plus Δt que ce test eprouve, mais une cible mal choisie.
    _residuel3 = _pic3(5.0, 5.0)   # decale de la cible, SANS aucun apport
    _decalage_ref3 = decalage_minimisant_ecart(_t3, _cible3, _t3, _residuel3)
    controler("le residuel, avant tout apport, porte deja un retard mesurable",
              abs(_decalage_ref3) > 1.0, f"{_decalage_ref3:+.2f} h")

    # LA CONVERGENCE N'EST PAS DEMANDEE ICI, deliberement. Le residuel reste
    # un signal FIXE qu'aucun apport ne peut retirer : sa bosse propre, a
    # t = 5 h, degrade la FORME de la section quel que soit ce qu'on injecte
    # a t = 9 h — un defaut de la CIBLE de ce fixture, pas de la correction.
    # Ce test ne verifie qu'une chose : que la premiere estimation est batie
    # sur CE decalage-la, jamais sur zero.
    _manquant3 = ecart_a_la_cible(_t3, _cible3, _t3, _residuel3, _decalage_ref3)
    _manquant3_a_zero = ecart_a_la_cible(_t3, _cible3, _t3, _residuel3, 0.0)
    controler("la premiere estimation est construite sur le decalage mesure, "
              "pas sur zero",
              float(np.max(np.abs(_manquant3 - _manquant3_a_zero))) > 1.0,
              "les deux estimations different bien")

    # Deux situations DISTINCTES, qu'il ne faut pas confondre.
    #
    # LE SEUIL EST EPINGLE, PAS HERITE DU DEFAUT. Ces deux essais eprouvent le
    # MECANISME de rejet, pas la valeur de production : ecrits sur le defaut,
    # ils sont passes au vert le jour ou celui-ci est monte de 1 a 5 % — le
    # modele fictif rendant exactement 5 %, la comparaison stricte ne
    # declenchait plus. Le defaut, lui, a son propre controle plus bas.
    _QUALITE = Configuration(bilan_masse_max_pct=1.0)

    print("\n--- MODELE DOUTEUX DES LE CALCUL DE REFERENCE ---")
    modele3 = ModeleFictif(apports[:1], sections[:1], temps, formes[:1],
                           bilan_masse_pct=5.0)
    r3 = caler(modele3, apports[:1], sections[:1], cibles[:1],
               _QUALITE, journal=lambda *a, **k: None)
    # Un modele deja instable APPORTS A ZERO ne peut rien caler du tout : le
    # dire tout de suite vaut mieux que de consommer des essais.
    controler("un modele douteux est arrete des le calcul de reference",
              not r3.apports and "bilan de masse" in r3.motif, r3.motif)
    controler("l'arret de reference ne coute qu'un seul calcul",
              r3.nb_calculs == 1, f"{r3.nb_calculs} calcul(s)")

    print("\n--- ESSAI REJETE EN COURS DE RECHERCHE ---")
    # Modele sain a l'etat de reference, mais qui devient instable des que
    # l'apport depasse un seuil : c'est le cas que le garde-fou de qualite
    # doit intercepter PENDANT la recherche.
    modele3b = ModeleFictif(apports[:1], sections[:1], temps, formes[:1],
                            seuil_instabilite=0.5)
    r3b = caler(modele3b, apports[:1], sections[:1], cibles[:1],
                _QUALITE, journal=lambda *a, **k: None)
    controler("le calcul de reference d'un modele sain passe",
              r3b.nb_calculs > 1, f"{r3b.nb_calculs} calculs")
    controler("un essai devenu instable est rejete, et la recherche s'arrete",
              bool(r3b.apports) and not r3b.apports[0].valide
              and "bilan de masse" in r3b.apports[0].motif,
              r3b.apports[0].motif if r3b.apports else "aucun apport")
    controler("tout apport non converge reste non valide",
              all(a.valide == (not a.motif) for a in r3b.apports),
              f"{len(r3b.apports)} apport(s) examine(s)")

    # LE DEFAUT DE PRODUCTION A SON PROPRE CONTROLE, separe du mecanisme
    # ci-dessus. Il vaut 5 % depuis le 30/08/2026 : a 1 %, un calcul par
    # ailleurs sain (1,119 % mesure sur un modele reel) arretait le calage
    # des le premier apport. Le changer est une DECISION, pas un reglage :
    # ce controle oblige a la prendre sciemment.
    controler("le defaut de bilan_masse_max_pct est 5 %",
              Configuration().bilan_masse_max_pct == 5.0,
              f"{Configuration().bilan_masse_max_pct} %")
    # LE BILAN N'EST PAS UN ECART A LA CIBLE, et rien ne doit les rapprocher :
    # un seuil de qualite numerique qui suivrait la tolerance de volume ferait
    # dependre le rejet d'un calcul de la precision demandee a l'etude.
    controler("le bilan de masse ne se juge pas contre la tolerance de volume",
              qualite_acceptable(
                  ResultatCalcul(reussi=True, bilan_masse_pct=4.0),
                  Configuration(tolerance_volume=0.001))[0],
              "un volume exigeant ne rejette pas un calcul sain")

    print("\n--- UNE ETAPE OUVERTE N'A PAS ENCORE DE RESULTATS ---")
    # LE MODELE FICTIF EST TROP COMPLAISANT POUR CE CAS : il repond a
    # lire_section() en tout temps, alors qu'un plan HEC-RAS fraichement clone
    # n'a pas de fichier de resultats tant qu'il n'a pas ete calcule. La boucle
    # lisait le residuel APRES avoir ouvert l'etape de l'apport : elle le
    # cherchait donc dans un plan vide, et TOUT calage s'arretait sur le
    # premier apport — apres avoir depense le calcul de reference pour rien
    # (cas reel, 20 min perdues). Le modele ci-dessous reproduit cette regle.
    class ModeleEtapeStricte(ModeleFictif):
        """Comme HEC-RAS : pas de resultats entre un jalon et son calcul."""

        _calcule = False

        def jalonner(self, etape):
            self._calcule = False
            return super().jalonner(etape)

        def calculer(self):
            self._calcule = True
            return super().calculer()

        def lire_section(self, nom_section):
            if not self._calcule:
                raise RuntimeError(
                    "plan sans resultats : le .hdf n'existe pas encore")
            return super().lire_section(nom_section)

    modele3c = ModeleEtapeStricte(apports, sections, temps, formes)
    r3c = caler(modele3c, apports, sections, cibles,
                Configuration(), journal=lambda *a, **k: None)
    controler("le residuel est lu AVANT l'ouverture de l'etape de l'apport",
              all(a.valide for a in r3c.apports)
              and len(r3c.apports) == len(apports),
              r3c.motif or f"{sum(a.valide for a in r3c.apports)}/"
                           f"{len(apports)} apport(s) cale(s)")

    print("\n--- SECTION DE CONTROLE ILLISIBLE ---")
    # Une section mal nommee ne se manifestait qu'au tour de SON apport, donc
    # apres le calage complet de tout l'amont. Elle est desormais detectee au
    # calcul de reference, ou toutes les sections sont lisibles ensemble.
    modele3d = ModeleFictif(apports[:1], sections[:1], temps, formes[:1])
    r3d = caler(modele3d, apports[:1], ["Section_absente"], cibles[:1],
                Configuration(), journal=lambda *a, **k: None)
    controler("une section illisible arrete le calage des la reference",
              not r3d.apports and "illisible" in r3d.motif, r3d.motif)
    controler("elle est NOMMEE, et l'arret ne coute qu'un calcul",
              "Section_absente" in r3d.motif and r3d.nb_calculs == 1,
              f"{r3d.nb_calculs} calcul(s)")

    print("\n--- UNE SECTION AMONT ILLISIBLE EST NOMMEE, PAS AVALEE ---")
    # L'etape 7 relit les sections deja calees pour voir si le remous du
    # nouvel apport les a deplacees. Celle qu'on ne savait pas lire sortait
    # de la liste sur un « except Exception: continue » muet : l'appelant
    # n'avait plus de quoi distinguer « aucune section n'a derive » de « je
    # n'ai pas pu regarder », et il annoncait le premier. Le banc d'avant ne
    # pouvait pas voir la difference — la fonction ne rendait qu'une liste.
    class ModeleSectionMuette(ModeleFictif):
        """Une section amont refuse de se laisser relire ; les autres non."""

        def lire_section(self, nom_section):
            if nom_section == sections[0]:
                raise RuntimeError("fichier de resultats verrouille")
            return super().lire_section(nom_section)

    modele3e = ModeleSectionMuette(apports, sections, temps, formes)
    derives3e, illisibles3e = _sections_derivees(
        modele3e, sections[:3], cibles[:3], Configuration())
    controler("la section illisible est RAPPORTEE, pas ignoree",
              [s for s, _ in illisibles3e] == [sections[0]],
              f"illisibles : {[s for s, _ in illisibles3e]}")
    controler("elle porte la raison de son echec",
              bool(illisibles3e) and "verrouille" in illisibles3e[0][1],
              illisibles3e[0][1] if illisibles3e else "aucune raison")
    controler("les sections lisibles restent examinees",
              all(s != sections[0] for s, _ in derives3e),
              f"{len(derives3e)} derive(s) parmi 2 sections lisibles")
    controler("aucune illisible quand toutes se lisent",
              _sections_derivees(modele, sections[:3], cibles[:3],
                                 Configuration())[1] == [],
              "liste vide")

    print("\n--- DECALAGE NON IDENTIFIABLE ---")
    # Aucun decalage ne se lit sur une serie qui ne bouge pas. Le balayage
    # rendait pourtant le BORD de son domaine — -12,12 h sur une section
    # muette — parce qu'a cout egal il gardait le premier candidat essaye. Le
    # deficit n'en etait pas fausse, mais le journal envoyait chercher dans le
    # modele un dephasage qui n'existe pas.
    cible_temoin = hydrogramme(temps, 40.0)
    for libelle, serie in (("muette", np.zeros_like(temps)),
                           ("constante", np.full_like(temps, 12.0))):
        d = decalage_minimisant_ecart(temps, cible_temoin, temps, serie)
        controler(f"une section {libelle} ne fabrique pas de dephasage",
                  abs(d) < 1e-9, f"{d:+.2f} h")
    # Meme exigence sur le jumeau de criteres, dont se sert diagnostiquer() :
    # les deux mesurent la meme grandeur et doivent repondre pareil.
    from criteres import recaler as _recaler
    _, _, d_criteres = _recaler(temps, np.full_like(temps, 12.0),
                                temps, np.full_like(temps, 12.0))
    controler("le recalage du diagnostic non plus",
              abs(d_criteres) < 1e-9, f"{d_criteres:+.2f} h")
    # ET IL RETROUVE UN VRAI DECALAGE, sans quoi le controle precedent serait
    # satisfait par une fonction qui rendrait toujours zero.
    retarde = np.interp(temps - 1.5, temps, cible_temoin)
    d_vrai = decalage_minimisant_ecart(temps, cible_temoin, temps, retarde)
    controler("un decalage reel est toujours mesure",
              abs(d_vrai - 1.5) < 0.1, f"{d_vrai:+.2f} h pour +1,50 h injecte")

    # -----------------------------------------------------------------------
    # INVARIANT : UN APPORT REMIS A UN ESSAI ANTERIEUR N'EST JAMAIS VALIDE.
    #
    # Tout repose la-dessus. C'est ce qui autorise la verification globale a
    # RELIRE le dernier calcul au lieu d'en lancer un : si un apport remis en
    # place pouvait etre valide, le modele porterait l'essai retenu pendant
    # que le fichier de resultats porterait le dernier, et le tableau de bord
    # decrirait autre chose que ce que le modele contient.
    # -----------------------------------------------------------------------
    import ast
    import inspect
    import textwrap
    _arbre = ast.parse(textwrap.dedent(inspect.getsource(caler)))
    _appels = sum(1 for n in ast.walk(_arbre)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name)
                  and n.func.id == "concordance")
    controler("aucune seconde chance d'acceptation apres le retour au meilleur",
              _appels == 1,
              f"{_appels} appel(s) reel(s) a concordance() dans caler() — "
              f"un seul, dans la boucle d'essais")

    # -----------------------------------------------------------------------
    # L'ARRET PORTE SUR « rapport_volume ».
    # -----------------------------------------------------------------------
    _c = Configuration()
    _bon = type("D", (), {"r": 0.99, "decalage_h": 0.0, "rapport_pic": 1.005,
                          "rapport_volume": 1.002})()
    controler("la concordance se prononce sur le volume",
              concordance(_bon, _c), f"volume {_bon.rapport_volume} conforme")
    _mauvais = type("D", (), {"r": 0.99, "decalage_h": 0.0,
                              "rapport_pic": 1.005, "rapport_volume": 1.30})()
    controler("un volume faux est refuse",
              not concordance(_mauvais, _c),
              f"volume {_mauvais.rapport_volume} refuse")
    controler("le meilleur essai se choisit lui aussi sur le volume",
              ecart_combine(_bon, _c) < ecart_combine(_mauvais, _c),
              f"{ecart_combine(_bon, _c):.2f} < "
              f"{ecart_combine(_mauvais, _c):.2f}")

    # --- selection : admissibilite d'abord, erreur combinee ensuite --------
    def _diag(volume, pic, forme):
        return type("D", (), {"decalage_h": 0.0, "rapport_volume": volume,
                              "rapport_pic": pic, "r": forme})()

    _juste = _diag(1.0005, 1.0002, 0.999)      # les trois dans les clous
    _limite = _diag(1.0049, 1.0199, 0.9701)    # les trois tout juste tenus
    _hors = _diag(1.0000, 1.0500, 1.000)       # pointe hors seuil
    controler("les trois seuils tenus : l'essai est admissible",
              admissible(_juste, _c) and admissible(_limite, _c))
    controler("un seul seuil depasse suffit a rendre inadmissible",
              not admissible(_hors, _c),
              f"pointe {100 * _hors.rapport_pic:.1f} %")
    controler("l'erreur combinee prefere l'essai proche des TROIS cibles",
              ecart_combine(_juste, _c) < ecart_combine(_limite, _c),
              f"{ecart_combine(_juste, _c):.2f} < "
              f"{ecart_combine(_limite, _c):.2f}")
    controler("l'admissibilite prime sur une erreur combinee plus faible",
              rang_essai(_limite, _c) < rang_essai(_hors, _c),
              f"admissible {ecart_combine(_limite, _c):.2f} avant "
              f"inadmissible {ecart_combine(_hors, _c):.2f}")

    # Progression du pic : distingue une recherche qui plafonne d'une
    # recherche qui avancait encore quand les essais ont ete epuises.
    controler("une pointe qui progresse encore est detectee",
              abs(_progression_pic([{"pic": 0.937}, {"pic": 0.941}])
                  - 0.004) < 1e-9,
              f"{_progression_pic([{'pic': 0.937}, {'pic': 0.941}]):.4f}")
    controler("une pointe qui plafonne ne l'est pas",
              _progression_pic([{"pic": 0.945}, {"pic": 0.945}]) == 0.0)
    controler("un historique trop court ne fabrique pas de progression",
              _progression_pic([{"pic": 0.94}]) is None)

    # CIBLE HORS D'ATTEINTE — la correction additive injecte simplement ce
    # qui manque. Ce qui reste hors d'atteinte, c'est une cible INFERIEURE a
    # ce que la section recoit deja : un apport ne peut qu'ajouter du debit.
    print("\n--- CIBLE HORS D'ATTEINTE : PLUS BASSE QUE LE RESIDUEL ---")
    t_c, q_c = cibles[0]
    # Debit permanent important : la section est deja bien au-dessus de la
    # cible demandee, apports a zero.
    base = hydrogramme(temps, 60.0)
    modele4 = ModeleFictif(apports[:1], sections[:1], temps, formes[:1],
                           debit_base=base)
    r4 = caler(modele4, apports[:1], sections[:1], [(t_c, q_c * 0.05)],
               Configuration(nb_max_essais=5), journal=lambda *a, **k: None)
    controler("une cible sous le residuel est refusee, avec la raison",
              not r4.apports[0].valide
              and "recoit deja" in r4.apports[0].motif,
              r4.apports[0].motif[:90])

    # APPORT PEU IDENTIFIABLE. Meme montage, mais la cible passe JUSTE
    # au-dessus du residuel : l'apport ne pese plus que quelques pour-cent du
    # debit a la section, et la bande de tolerance admise vaut alors plusieurs
    # fois l'apport lui-meme. La section se calera ; l'apport sorti n'aura
    # aucune valeur d'estimation, et la chaine doit le DIRE avant de calculer.
    print("\n--- APPORT TROP PETIT DEVANT LE DEBIT DE SA SECTION ---")
    _dits = []
    # 2 % : la part mesuree sur le cas reel qui a motive ce garde-fou.
    modele4bis = ModeleFictif(apports[:1], sections[:1], temps, formes[:1],
                              debit_base=base)
    _r4bis = caler(modele4bis, apports[:1], sections[:1],
                   [(temps, base / 0.98)],
                   Configuration(nb_max_essais=2), journal=_dits.append)
    _alerte = [l for l in _dits if "PEU IDENTIFIABLE" in l]
    controler("un apport pesant 2 % du debit est annonce peu identifiable",
              bool(_alerte), (_alerte[0][:110] if _alerte else "aucune alerte"))
    controler("l'alerte chiffre la part et l'ecart possible",
              bool(_alerte) and "2.0 %" in _alerte[0] and "250 %" in _alerte[0],
              _alerte[0][60:170] if _alerte else "")
    # ET LE DIAGNOSTIC LA PORTE (07/09/2026) : c'est lui, et non le journal,
    # que lisent le classeur, la note de synthese et le suivi. Une seule fois
    # — chaque essai la porte, donc le retour au meilleur essai n'a rien a
    # rattraper — et jamais parmi les bloquantes : elle dit, elle ne juge pas.
    _diag4bis = _r4bis.apports[0].diagnostic
    controler("la reserve est portee par le diagnostic RETENU, une seule fois",
              sum("PEU IDENTIFIABLE" in a for a in _diag4bis.alertes) == 1,
              f"{len(_diag4bis.alertes)} alerte(s)")
    controler("elle ne bloque pas",
              not any("PEU IDENTIFIABLE" in a
                      for a in _diag4bis.alertes_bloquantes))
    controler("la part elle-meme est portee, comme un nombre",
              _diag4bis.part_apport is not None
              and abs(_diag4bis.part_apport - 0.02) < 1e-9,
              f"part_apport={_diag4bis.part_apport}")
    if _r4bis.diagnostics_finaux:
        import livrables as liv
        _fin4bis = _r4bis.diagnostics_finaux[0]
        controler("elle atteint la verification finale, une fois",
                  sum("PEU IDENTIFIABLE" in a for a in _fin4bis.alertes) == 1,
                  f"{len(_fin4bis.alertes)} alerte(s)")
        controler("la colonne « Alertes » du classeur la porte",
                  "PEU IDENTIFIABLE" in liv.tableau_de_bord(
                      sections[:1], [_fin4bis])["Alertes"].iloc[0])
    else:
        controler("la verification finale a eu lieu (apport cale en 2 essais)",
                  False, f"valide={_r4bis.apports[0].valide}, "
                  f"motif={_r4bis.apports[0].motif[:70]}")

    # ET LE CAS SYMETRIQUE : un apport qui pese lourd ne doit RIEN declencher,
    # sans quoi l'alerte deviendrait un bruit de fond qu'on cesse de lire.
    _dits_gros = []
    modele4ter = ModeleFictif(apports[:1], sections[:1], temps, formes[:1])
    _r4ter = caler(modele4ter, apports[:1], sections[:1], [cibles[0]],
                   Configuration(nb_max_essais=3), journal=_dits_gros.append)
    controler("un apport qui pese lourd ne declenche pas l'alerte",
              not [l for l in _dits_gros if "PEU IDENTIFIABLE" in l])
    _d4ter = _r4ter.apports[0].diagnostic
    controler("ni ne charge la colonne « Alertes » de sa section",
              _d4ter is not None
              and not any("PEU IDENTIFIABLE" in a for a in _d4ter.alertes),
              " ; ".join(_d4ter.alertes)[:80] if _d4ter else "aucun diagnostic")

    # La resolution sequentielle suppose l'amont fige : un apport non cale
    # rend tout ce qui suit sans objet.
    modele5 = ModeleFictif(apports[:2], sections[:2], temps, formes[:2],
                           debit_base=base)
    r5 = caler(modele5, apports[:2], sections[:2],
               [(t_c, q_c * 0.05), cibles[1]],
               Configuration(nb_max_essais=4), journal=lambda *a, **k: None)
    controler("les apports suivants ne sont pas traites apres un echec",
              len(r5.apports) == 1 and not r5.apports[0].valide,
              f"{len(r5.apports)} apport(s) traite(s) sur 2")

    # --- VOLUME PLANCHER : LE CLIQUET DU PLANCHER A ZERO ------------------
    #
    # Le cliquet est enonce dans la note depuis la V13 — « le plancher a zero,
    # et le cliquet qui en decoule » — et n'etait mesure NULLE PART. caler()
    # ne refusait que le cas TOTAL : une cible entierement sous le residuel.
    # Entre les deux vit le cas ordinaire, et couteux.
    print("\n--- VOLUME PLANCHER : LE CLIQUET DU PLANCHER A ZERO ---")

    # D'abord la formule, sur un cas qui se calcule a la main : une cible a
    # 100 sur 10 h (volume 1000), un residuel a 150 sur les 5 premieres
    # heures (exces 50 x 5 h = 250). Plancher = 1 + 250/1000 = 1,25.
    _tk = np.linspace(0.0, 10.0, 1001)
    _ck = np.full_like(_tk, 100.0)
    _rk = np.where(_tk <= 5.0, 150.0, 0.0)
    _mk = ecart_a_la_cible(_tk, _ck, _tk, _rk, 0.0)
    controler("le cliquet vaut 1 + volume de l'exces / volume de la cible",
              abs(cliquet_volume(_tk, _ck, _mk, 0.0) - 1.25) < 0.005,
              f"{cliquet_volume(_tk, _ck, _mk, 0.0):.4f} pour 1,2500 attendu")
    controler("un residuel partout sous la cible ne cliquette pas",
              abs(cliquet_volume(_tk, _ck,
                                 ecart_a_la_cible(_tk, _ck, _tk, _ck * 0.5, 0.0),
                                 0.0) - 1.0) < 1e-9, "1,0000")
    # LA FENETRE BORNE LA MESURE, comme elle borne le volume qu'elle predit :
    # un exces hors de ce qui est juge ne pesera pas sur le verdict, et
    # l'annoncer serait une fausse alerte.
    controler("un exces hors de la fenetre jugee ne cliquette pas",
              abs(cliquet_volume(_tk, _ck, _mk, 0.0, fenetre=(6.0, 10.0))
                  - 1.0) < 1e-9, "1,0000")
    controler("le meme exces, plein cadre, cliquette a 150 %",
              abs(cliquet_volume(_tk, _ck, _mk, 0.0, fenetre=(0.0, 5.0))
                  - 1.5) < 0.005, "1,5000")

    # PUIS CE QUE CA VAUT EN VRAI. Un residuel pointu qui deborde la cible au
    # sommet et reste dessous sur les flancs : max(manquant) > 0, donc le
    # refus total ne se declenche pas, et le calage part pour de bon.
    _tc2 = np.linspace(0.01, 36, 400)
    _cible_k = hydrogramme(_tc2, 100.0, t_pic=12.0, forme=2.0)
    _base_k = hydrogramme(_tc2, 140.0, t_pic=12.0, forme=8.0)
    _dits_k = []
    _mk2 = ModeleFictif(["A1"], ["S1"], _tc2, [hydrogramme(_tc2, 10.0)],
                        debit_base=_base_k)
    _rk2 = caler(_mk2, ["A1"], ["S1"], [(_tc2, _cible_k)],
                 Configuration(nb_max_essais=8), journal=_dits_k.append)
    _annonce = [l for l in _dits_k if "VOLUME PLANCHER" in l]
    controler("un residuel qui deborde en partie declenche l'alerte",
              bool(_annonce), (_annonce[0][:110] if _annonce else "aucune"))
    _atteint = 100 * _rk2.apports[0].diagnostic.rapport_volume
    _predit = (float(_annonce[0].split("d'environ ")[1].split(" %")[0])
              if _annonce else 0.0)
    # LE CHIFFRE ANNONCE EST-IL LE BON ? C'est tout l'interet : il est connu
    # AVANT le premier essai, et le calage n'a jamais pu descendre en dessous.
    controler("le plancher annonce est celui que le calage atteint",
              abs(_predit - _atteint) < 1.0,
              f"annonce {_predit:.1f} %, atteint {_atteint:.1f} % "
              f"apres {len(_rk2.apports[0].historique)} essai(s)")
    controler("et le calage echoue bien, faute de pouvoir descendre",
              not _rk2.apports[0].valide, _rk2.apports[0].motif[:80])
    # ET LE VERDICT LE DIT. L'annonce partait au journal, que personne ne
    # relit une fois le calage fini ; le motif, lui, est repris partout —
    # classeur, note de synthese, jauges. Il accusait le modele.
    controler("le motif nomme le plancher, et n'accuse plus le modele",
              "NE POUVAIT PAS DESCENDRE" in _rk2.apports[0].motif
              and "apports amont" in _rk2.apports[0].motif,
              _rk2.apports[0].motif[-150:])
    # UN ECHEC ORDINAIRE NE DOIT PAS HERITER DE CETTE PHRASE — ni du cliquet
    # de l'apport precedent, la boucle portant sur les apports.
    _rk3 = caler(ModeleFictif(apports[:1], sections[:1], temps, formes[:1]),
                 apports[:1], sections[:1], [(temps, hydrogramme(temps, 1e4))],
                 Configuration(nb_max_essais=2), journal=lambda *a, **k: None)
    controler("un echec sans plancher n'herite pas de la phrase",
              "NE POUVAIT PAS DESCENDRE" not in _rk3.apports[0].motif,
              _rk3.apports[0].motif[:80])
    # LE CAS SYMETRIQUE : un calage ordinaire ne doit RIEN annoncer, sans quoi
    # l'alerte devient un bruit de fond qu'on cesse de lire.
    _dits_sain = []
    caler(ModeleFictif(apports[:1], sections[:1], temps, formes[:1]),
          apports[:1], sections[:1], [cibles[0]],
          Configuration(nb_max_essais=3), journal=_dits_sain.append)
    controler("un calage ordinaire n'annonce aucun plancher",
              not [l for l in _dits_sain if "VOLUME PLANCHER" in l])

    # --- DUREE SIMULEE AJUSTEE A CHAQUE APPORT ----------------------------
    # Le modele fictif TRONQUE reellement ses series a la duree demandee : un
    # ajustement trop court se paierait donc en concordance, et se verrait.
    print("\n--- DUREE SIMULEE AJUSTEE A CHAQUE APPORT ---")
    _t6 = np.linspace(0.0, 40.0, 401)
    # Deux apports dont les evenements finissent LOIN l'un de l'autre : le
    # premier a 6 h, le second a 20 h. C'est la configuration qui rend
    # l'ajustement payant, et celle ou une troncature fautive se voit.
    _f6 = [np.exp(-0.5 * ((_t6 - 3.0) / 1.0) ** 2),
           np.exp(-0.5 * ((_t6 - 14.0) / 2.5) ** 2)]
    _m6 = ModeleFictif(["A1", "A2"], ["S1", "S2"], _t6, _f6, retard_h=0.0)
    _cibles6 = []
    for _k in range(2):
        _m6.facteurs = {"A1": 30.0, "A2": 45.0}
        _cibles6.append((_t6, _m6.lire_section(f"S{_k + 1}")[1].copy()))
    _m6.duree_max, _m6.durees_demandees = None, []
    _r6 = caler(_m6, ["A1", "A2"], ["S1", "S2"], _cibles6,
                Configuration(nb_max_essais=4),
                journal=lambda *a, **k: None)
    # CE MONTAGE N'EPROUVE PAS LA TRONCATURE, MAIS LA MESURE DU DECALAGE —
    # et il faut le dire, parce que son nom d'origine (« le calage aboutit
    # malgre la troncature ») designait la mauvaise cause pendant des
    # semaines.
    #
    # Le residuel de S2, apport A2 a zero, est la contribution de A1 : elle
    # pique a 3 h quand la cible de S2 pique a 14 h. decalage_minimisant_ecart
    # aligne l'un sur l'autre et rend Dt = -11 h, ce qui place la fenetre de
    # jugement hors de l'evenement de A2. C'EST EXACTEMENT LA PATHOLOGIE DE
    # LA SECTION 5.3 DE STATUT.txt : un Dt qui n'est pas un temps de transfert
    # mais l'ecart entre deux pics qui ne decrivent pas la meme eau.
    #
    # MESURE DU 31/08/2026 — le rapport d'amplitude n'y est pour rien :
    # facteurs A1/A2 = 30/45, 5/45 puis 2/60 rendent TOUS Dt = -11,00 h. Le
    # montage n'est donc pas un artefact a corriger, il est fidele ; c'est la
    # mesure du decalage qui est en cause (point ouvert V2 : juger le decalage
    # sur sa COHERENCE LE LONG DE L'AXE, section 6 de STATUT.txt).
    #
    # CE QU'ON EXIGE DONC ICI : que la chaine REFUSE l'apport et le DISE,
    # plutot que de le caler de travers en silence. Le jour ou le decalage
    # sera mesure autrement, ce controle basculera — et c'est voulu : il
    # signalera qu'il faut le relire, pas qu'une regression est apparue.
    # Que la troncature ne casse PAS un calage sain est eprouve plus bas,
    # sur le montage a traine fine.
    controler("un decalage aberrant fait refuser l'apport, et le DIT",
              (not _r6.conforme) and "A2" in (_r6.motif or ""),
              (_r6.motif or "conforme")[:120])
    controler("la duree est bien raccourcie, apport par apport",
              len(_m6.durees_demandees) >= 1
              and _m6.durees_demandees[0] < 40.0,
              f"durees demandees : "
              f"{[round(d, 1) for d in _m6.durees_demandees]}")
    controler("elle ne DECROIT jamais d'un apport au suivant",
              _m6.durees_demandees == sorted(_m6.durees_demandees),
              f"{[round(d, 1) for d in _m6.durees_demandees]}")
    controler("le premier apport coute moins que le second",
              _m6.durees_demandees[0] < _m6.durees_demandees[-1]
              if len(_m6.durees_demandees) > 1 else True,
              f"{[round(d, 1) for d in _m6.durees_demandees]}")
    # LE DEFAUT EST DEBRAYABLE, et le debrayer doit tout laisser intact.
    _m7 = ModeleFictif(["A1", "A2"], ["S1", "S2"], _t6, _f6, retard_h=0.0)
    _r7 = caler(_m7, ["A1", "A2"], ["S1", "S2"], _cibles6,
                Configuration(nb_max_essais=4, ajuster_duree=False),
                journal=lambda *a, **k: None)
    controler("ajuster_duree=False ne raccourcit rien",
              _m7.durees_demandees == [] and _m7.duree_max is None,
              f"{_m7.durees_demandees}")
    controler("et rend le meme verdict", _r7.conforme == _r6.conforme,
              f"{_r7.conforme} vs {_r6.conforme}")

    # FENETRE DESACTIVEE : LA DUREE NE DOIT PLUS ETRE TOUCHEE NON PLUS.
    # Ce controle manquait, et son absence a laisse passer un defaut qui
    # rendait NON CONFORME un calage par ailleurs parfait : la duree etait
    # raccourcie sur une fenetre que le jugement n'utilisait pas, et la
    # couverture — mesuree alors sur TOUTE la cible — levait sa bloquante
    # « allonger la simulation ». La cible porte ici une traine fine, comme
    # les vraies : sans elle, la couverture passe et le defaut se cache.
    _t8 = np.linspace(0.0, 40.0, 401)
    _f8 = [np.exp(-0.5 * ((_t8 - 4.0) / 1.2) ** 2)
           + 0.004 * np.exp(-(_t8 - 4.0) / 25.0) * (_t8 > 4)]
    _cibles8 = []
    for _sans in (False, True):
        _m8 = ModeleFictif(["A1"], ["S1"], _t8, _f8, retard_h=0.0)
        _m8.facteurs = {"A1": 40.0}
        if not _cibles8:
            _cibles8 = [(_t8, _m8.lire_section("S1")[1].copy())]
        _m8.duree_max, _m8.durees_demandees = None, []
        _r8 = caler(_m8, ["A1"], ["S1"], _cibles8,
                    Configuration(nb_max_essais=4,
                                  fenetre_active=(False if _sans else None)),
                    journal=lambda *a, **k: None)
        if _sans:
            controler("fenetre_active=non ne raccourcit rien non plus",
                      _m8.durees_demandees == [] and _m8.duree_max is None,
                      f"durees demandees : {_m8.durees_demandees}")
            controler("et le calage reste conforme, sans bloquante de "
                      "couverture", _r8.conforme,
                      _r8.motif or "conforme")
        else:
            controler("fenetre active : la duree EST bien raccourcie",
                      len(_m8.durees_demandees) == 1
                      and _m8.durees_demandees[0] < 40.0,
                      f"durees demandees : "
                      f"{[round(d, 1) for d in _m8.durees_demandees]}")

    # LE PLAFOND ROGNE LA MARGE, ET LE DIT — SANS ALERTE NI ECHEC.
    #
    # Serie de 20 h, evenement centre sur 14 h : le calendrier veut 21,7 h et
    # le plafond n'en donne que 20. Ce qui se perd est la MARGE ; la fenetre
    # jugee (7,9 -> 19,7 h) reste couverte, et le calage doit rester conforme.
    # Decision du 31/08/2026 : journal seulement. Une marge existe pour etre
    # rognee, et un garde-fou qui se declenche pour une perte sans consequence
    # apprend a etre ignore. Le jour ou la FENETRE ne rentrerait plus, c'est la
    # couverture qui le dirait (criteres.diagnostiquer, section 4 ter).
    _t9 = np.linspace(0.0, 20.0, 201)
    _f9 = [np.exp(-0.5 * ((_t9 - 14.0) / 2.0) ** 2)
           + 0.004 * np.exp(-(_t9 - 14.0) / 25.0) * (_t9 > 14.0)]
    _m9 = ModeleFictif(["A1"], ["S1"], _t9, _f9, retard_h=0.0)
    _m9.facteurs = {"A1": 40.0}
    _cibles9 = [(_t9, _m9.lire_section("S1")[1].copy())]
    _m9.duree_max, _m9.durees_demandees = None, []
    _dits9 = []
    _r9 = caler(_m9, ["A1"], ["S1"], _cibles9,
                Configuration(nb_max_essais=4), journal=_dits9.append)
    _rogne9 = [l for l in map(str, _dits9) if "voulues" in l]
    controler("le plafond qui rogne la marge le DIT au journal",
              bool(_rogne9), _rogne9[0].strip()[:95] if _rogne9 else "rien")
    controler("il chiffre la marge perdue et rassure sur la fenetre",
              bool(_rogne9) and "de marge en moins" in _rogne9[0]
              and "fenetre jugee reste couverte" in _rogne9[0],
              _rogne9[0].strip()[:95] if _rogne9 else "rien")
    controler("et le calage reste CONFORME : rien de juge ne manque",
              _r9.conforme, _r9.motif or "conforme")
    controler("aucune alerte n'est levee pour une simple perte de marge",
              bool(_r9.apports) and not _r9.apports[0].diagnostic.alertes,
              str(_r9.apports[0].diagnostic.alertes) if _r9.apports else "?")

    # --- COHERENCE DU DECALAGE LE LONG DE L'AXE -------------------------
    print("\n--- COHERENCE DU DECALAGE LE LONG DE L'AXE ---")
    # DEUX MODELES REELS, PAS DES INVENTIONS : les pics et les Dt sont ceux
    # releves aux journaux des 31/08 et 01/09/2026. LE MODELE B EST LA POUR UNE
    # RAISON PRECISE — il passait sous les premiers seuils (pente ET
    # correlation) alors qu'il derive PLUS que le modele A. C'est lui qui a
    # impose le critere d'etendue ; sans ce controle, rien n'empecherait d'y
    # revenir.
    _t10 = np.linspace(0.0, 40.0, 401)

    def _bosse(t_pic, amplitude=50.0):
        return amplitude * np.exp(-0.5 * ((_t10 - t_pic) / 2.0) ** 2)

    def _mesurer(pics_cibles, pics_modele):
        _cib = [(_t10, _bosse(p)) for p in pics_cibles]
        _res = [(_t10, _bosse(p, 20.0)) for p in pics_modele]
        _dits = []
        return _coherence_decalage(_cib, _res, Configuration(),
                                   _dits.append), _dits, _cib, _res

    # --- MODELE A : derive nette et monotone, -0,70 de pente, r -0,98 -------
    _pics_a = [3.0, 4.5, 5.5, 6.5, 7.0, 7.0, 8.5, 9.5]
    _mod_a = [3.10, 3.10, 3.50, 3.60, 3.80, 4.00, 4.20, 5.20]
    _al_a, _dits_a, _cib_a, _res_a = _mesurer(_pics_a, _mod_a)
    controler("modele A : la derive du decalage leve l'alerte",
              bool(_al_a), (_al_a or "aucune")[:90])
    controler("l'etendue de Dt y est chiffree, avec son seuil",
              bool(_dits_a) and "s'etend sur 4.4 h" in _dits_a[0]
              and "seuil" in _dits_a[0],
              _dits_a[0].strip()[95:200] if _dits_a else "rien dit")
    controler("pente et correlation restent RAPPORTEES",
              bool(_dits_a) and "-0.70" in _dits_a[0] and "-0.98" in _dits_a[0],
              _dits_a[0].strip()[-40:] if _dits_a else "")
    controler("et les deux progressions le long de l'axe",
              bool(_dits_a) and "+0.26" in _dits_a[0] and "+0.84" in _dits_a[0],
              _dits_a[0].strip()[60:150] if _dits_a else "")

    # --- MODELE B : LE CAS QUI PASSAIT, et qui derive le plus --------------
    # Derive NON monotone (-0,70 +0,40 -1,10 +2,30 +3,40 +5,90), donc r = 0,73 :
    # sous l'ancien « |r| > 0,9 » il ne levait rien, avec une etendue de 7,0 h
    # contre 4,4 pour le modele A. Le sens est aussi INVERSE — ici le modele
    # route plus lentement que les cibles.
    _pics_b = [11.0, 12.5, 14.5, 15.5, 15.5, 16.0]
    _mod_b = [10.3, 12.9, 13.4, 17.8, 18.9, 21.9]
    _al_b, _dits_b, _cib_b, _res_b = _mesurer(_pics_b, _mod_b)
    controler("modele B : il leve l'alerte, LUI AUSSI",
              bool(_al_b), (_al_b or "AUCUNE — regression")[:90])
    controler("son etendue de 7,0 h depasse celle du modele A",
              bool(_dits_b) and "s'etend sur 7.0 h" in _dits_b[0],
              _dits_b[0].strip()[95:175] if _dits_b else "rien dit")
    controler("alors que sa correlation, seule, l'aurait ecarte",
              bool(_dits_b) and "+0.73" in _dits_b[0],
              "r = +0,73 < 0,9 : c'est le defaut de l'ancien critere")

    # --- LE CAS SAIN : un decalage CONSTANT, quelle que soit sa valeur -----
    # Deja manque une fois : la premiere version sortait avant d'imprimer
    # quand l'ecart ne variait pas, si bien que le seul cas a ne rien
    # rapporter etait le bon.
    _al_s, _dits_s, _, _ = _mesurer(_pics_a, [p - 1.0 for p in _pics_a])
    controler("un decalage constant ne leve AUCUNE alerte",
              _al_s is None, str(_al_s)[:80])
    controler("mais il est quand meme CHIFFRE au journal",
              bool(_dits_s) and "constant" in _dits_s[0],
              _dits_s[0].strip()[60:170] if _dits_s else "rien dit")

    # --- CE QUE LE SEUIL RELATIF ACHETE -----------------------------------
    # Une derive FAIBLE devant la duree de l'evenement ne doit rien lever :
    # c'est tout l'interet d'un seuil en pourcentage plutot qu'en heures.
    _al_f, _dits_f, _, _ = _mesurer(
        _pics_b, [p - 0.5 * (k % 2) for k, p in enumerate(_pics_b)])
    controler("une derive faible devant l'evenement ne leve rien",
              _al_f is None, (_al_f or "aucune")[:70])
    controler("le seuil est bien RELATIF a la fenetre jugee",
              bool(_dits_f) and "% d'une fenetre de" in _dits_f[0],
              _dits_f[0].strip()[95:185] if _dits_f else "rien dit")

    controler("moins de quatre apports : aucune derive, aucune alerte",
              _coherence_decalage(_cib_a[:3], _res_a[:3], Configuration(),
                                  lambda *a, **k: None) is None)
    controler("un residuel illisible est simplement ignore",
              _coherence_decalage(_cib_a, [None] * 8, Configuration(),
                                  lambda *a, **k: None) is None)
    # L'ALERTE REMONTE-T-ELLE JUSQU'AU RESULTAT ? Le canal est neuf : sans ce
    # controle, la mesure resterait dans le journal.
    controler("ResultatCalage porte le canal des alertes de chaine",
              isinstance(ResultatCalage().alertes_chaine, list)
              and ResultatCalage().alertes_chaine == [])

    # --- JUGEE A LA FIN, SUR LES Dt RETENUS (04/09/2026) --------------------
    # Le critere s'evaluait sur le calcul de reference, tous apports a zero :
    # sections aval affamees, derive fabriquee par le rang. Sur un modele qui
    # ne derive pas (etendue 1,8 h une fois cale) il a livre une reserve pour
    # 7,2 h. Ici : la ligne « coherence » doit sortir APRES la verification
    # finale, et son etendue doit etre celle des Dt RETENUS au journal.
    import re as _re
    _m11 = ModeleFictif(apports, sections, temps, formes)
    for _a, _f in zip(apports, facteurs_vrais):
        _m11.appliquer_facteur(_a, _f)
    _cib11 = [_m11.lire_section(s) for s in sections]
    _m11.preparer()
    _dits11 = []
    caler(_m11, apports, sections, _cib11, Configuration(nb_max_essais=8),
          journal=_dits11.append)
    _lignes11 = [str(l) for l in _dits11]
    _i_coh = next((k for k, l in enumerate(_lignes11)
                   if "coherence du decalage" in l), None)
    _i_verif = next((k for k, l in enumerate(_lignes11)
                     if "Verification globale finale" in l), None)
    _i_premier = next((k for k, l in enumerate(_lignes11)
                       if "decalage retenu" in l), None)
    controler("la coherence du decalage est jugee APRES la verification finale",
              _i_coh is not None and _i_verif is not None and _i_coh > _i_verif,
              f"coherence a la ligne {_i_coh}, verification a {_i_verif}, "
              f"premier « decalage retenu » a {_i_premier}")
    _retenus = [float(m.group(1)) for l in _lignes11
                for m in [_re.search(r"decalage retenu ([+-]\d+\.\d+) h", l)]
                if m]
    _etendue_dite = next(
        (float(m.group(1)) for l in _lignes11
         for m in [_re.search(r"s'etend sur (\d+\.\d+) h", l)] if m), None)
    controler("et son etendue est celle des Dt RETENUS, pas d'une relecture",
              len(_retenus) == len(apports) and _etendue_dite is not None
              and abs(_etendue_dite - (max(_retenus) - min(_retenus))) < 0.051,
              f"retenus {_retenus} ; dit : {_etendue_dite} h")

    # --- LE TROISIEME CALAGE REEL, SUR SES Dt RETENUS (04/09/2026) -----------
    # Six apports d'un modele de production : pics cibles du classeur, Dt
    # retenus et fenetres jugees releves au journal. Etendue 1,8 h pour des
    # fenetres de 15,5 h en mediane : AUCUNE alerte — la ou la lecture a
    # apports nuls annoncait 7,2 h.
    _pics_r = [11.0, 12.5, 14.5, 15.5, 15.5, 16.0]
    _dt_r = [-1.7, -0.9, -1.8, -1.4, -0.6, 0.0]
    _larg_r = [22.6, 13.8, 27.2, 15.8, 14.9, 15.2]
    _dits_r = []
    _al_r = _coherence_points(list(zip(_pics_r, _dt_r, _larg_r)),
                              _dits_r.append)
    controler("le troisieme calage reel, sur ses Dt retenus : aucune alerte",
              _al_r is None and bool(_dits_r)
              and "s'etend sur 1.8 h" in _dits_r[0]
              and "fenetre de 15.5 h" in _dits_r[0],
              (_al_r or (_dits_r[0].strip()[95:185] if _dits_r
                         else "rien dit"))[:90])
    controler("mais la meme etendue sur des crues courtes alerterait",
              _coherence_points([(p, d, 8.0) for p, d in zip(_pics_r, _dt_r)],
                                lambda *a, **k: None) is not None)

    # -----------------------------------------------------------------------
    # TEST DE CARACTERISATION — la TRAJECTOIRE, et non plus des proprietes.
    #
    # POURQUOI IL EXISTE. Tous les controles ci-dessus verifient des BANDES :
    # « volume a mieux que 5 % », « conforme », « tous les apports valides ».
    # Une bande ne voit pas un decalage. Un remaniement de caler() peut
    # deplacer tous les apports de 3 %, ou faire converger en trois essais au
    # lieu de deux, sans qu'aucun d'eux ne bronche — 97 %, c'est toujours
    # « mieux que 5 % ». Or caler() pese 699 lignes pour une complexite
    # cyclomatique de 81, et le depot ne porte AUCUN modele HEC-RAS : le seul
    # test qui touche un vrai modele exige le poste et une copie de 166 Mo.
    #
    # CE TEST NE DIT PAS CE QUE LE CODE DEVRAIT FAIRE. Il enregistre ce qu'il
    # FAIT, dans un fichier de reference versionne, et refuse toute
    # difference. C'est le filet a tendre AVANT de decouper caler(), et a
    # fortiori avant le calage simultane de docs/idees_V2_plugin.md, qui
    # reecrit ce coeur entierement.
    #
    # QUAND LE CHANGEMENT EST VOULU : « python calage.py --figer-reference »
    # reecrit le fichier. Le refuser sans ce geste explicite est tout
    # l'interet — une reference qui se met a jour toute seule ne prouve rien.
    #
    # CE QU'IL NE FIGE PAS, ET POURQUOI : ni les durees (horloge), ni
    # l'historique par essai (il porte des mesures de temps). « nb_calculs »
    # et le nombre d'essais par apport suffisent a epingler le chemin de
    # recherche ; les hydrogrammes et les diagnostics epinglent les nombres.
    # -----------------------------------------------------------------------
    print("\n--- CARACTERISATION : la trajectoire, pas la bande ---")
    import json
    import platform

    REFERENCE = Path(__file__).resolve().parent / "reference_calage_fictif.json"
    RTOL_DEBIT = 1e-9      # debits, volumes, rapports : relatif
    ATOL_HEURE = 1e-6      # decalages et bornes de fenetre : absolu, en heures

    def _diag_fige(d):
        """Ce qu'on retient d'un Diagnostic : des nombres, et rien d'autre."""
        if d is None:
            return None
        return {
            "rapport_volume": float(d.rapport_volume),
            "rapport_pic": float(d.rapport_pic),
            "r": float(d.r),
            "decalage_h": float(d.decalage_h),
            "fenetre": (None if d.fenetre is None
                        else [float(d.fenetre[0]), float(d.fenetre[1])]),
            "rapport_volume_serie": (None if d.rapport_volume_serie is None
                                     else float(d.rapport_volume_serie)),
            "part_cible_jugee": (None if d.part_cible_jugee is None
                                 else float(d.part_cible_jugee)),
            "converge": bool(d.converge),
            "alertes": list(d.alertes),
        }

    trajectoire = {
        "_a_propos": (
            "Test de caracterisation de caler() sur ModeleFictif. NE PAS "
            "MODIFIER A LA MAIN : « python calage.py --figer-reference » le "
            "reecrit quand le changement de comportement est VOULU."),
        "_produit_par": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "systeme": platform.system(),
        },
        "nb_calculs": int(resultat.nb_calculs),
        "conforme": bool(resultat.conforme),
        "motif": resultat.motif,
        "alertes_chaine": list(getattr(resultat, "alertes_chaine", []) or []),
        "apports": [{
            "nom_apport": a.nom_apport,
            "nom_section": a.nom_section,
            "valide": bool(a.valide),
            "essais": int(a.essais),
            "motif": a.motif,
            "facteur": float(a.facteur),
            # L'HYDROGRAMME INJECTE EST LE LIVRABLE du calage : c'est lui qui
            # part dans l'unsteady, et c'est donc lui qu'un remaniement ne
            # doit pas deplacer.
            "hydrogramme": [float(v) for v in
                            modele.formes[a.nom_apport]
                            * modele.facteurs[a.nom_apport]],
            "diagnostic": _diag_fige(a.diagnostic),
        } for a in resultat.apports],
        "diagnostics_finaux": [_diag_fige(d)
                               for d in resultat.diagnostics_finaux],
    }

    if "--figer-reference" in sys.argv:
        REFERENCE.write_text(
            json.dumps(trajectoire, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")
        print(f"   REFERENCE REECRITE : {REFERENCE.name} "
              f"({REFERENCE.stat().st_size / 1024:.1f} ko)")
        print("   Relire le diff avant de committer : il dit exactement ce "
              "que le changement a deplace.")
    elif not REFERENCE.is_file():
        controler("fichier de reference present", False,
                  f"{REFERENCE.name} absent — le creer par "
                  f"« python calage.py --figer-reference »")
    else:
        _attendu = json.loads(REFERENCE.read_text(encoding="utf-8"))
        _ecarts = []

        def _comparer(chemin, obtenu, attendu):
            """Compare deux valeurs de meme forme et accumule les ecarts."""
            if isinstance(attendu, dict):
                for cle in sorted(set(attendu) | set(obtenu or {})):
                    if cle.startswith("_"):
                        continue
                    if cle not in (obtenu or {}) or cle not in attendu:
                        _ecarts.append(f"{chemin}.{cle} : present d'un seul cote")
                        continue
                    _comparer(f"{chemin}.{cle}", obtenu[cle], attendu[cle])
            elif isinstance(attendu, list) and not isinstance(obtenu, str):
                if len(obtenu) != len(attendu):
                    _ecarts.append(f"{chemin} : {len(obtenu)} valeur(s) au "
                                   f"lieu de {len(attendu)}")
                    return
                for i, (o, a_) in enumerate(zip(obtenu, attendu)):
                    _comparer(f"{chemin}[{i}]", o, a_)
            elif isinstance(attendu, bool) or isinstance(obtenu, bool):
                if bool(obtenu) != bool(attendu):
                    _ecarts.append(f"{chemin} : {obtenu} au lieu de {attendu}")
            elif isinstance(attendu, (int, float)) and attendu is not None:
                # LES HEURES SE COMPARENT EN ABSOLU, LE RESTE EN RELATIF. Un
                # decalage nul ne peut pas se juger en relatif, et 1e-6 h
                # vaut 4 millisecondes : bien en deca du pas de recalage.
                if chemin.endswith("decalage_h") or ".fenetre[" in chemin:
                    if abs(float(obtenu) - float(attendu)) > ATOL_HEURE:
                        _ecarts.append(f"{chemin} : {obtenu:+.9f} h au lieu de "
                                       f"{attendu:+.9f} h")
                elif not np.isclose(float(obtenu), float(attendu),
                                    rtol=RTOL_DEBIT, atol=0.0,
                                    equal_nan=True):
                    _ecarts.append(f"{chemin} : {obtenu!r} au lieu de "
                                   f"{attendu!r}")
            elif obtenu != attendu:
                _ecarts.append(f"{chemin} : {obtenu!r} au lieu de {attendu!r}")

        _comparer("", trajectoire, _attendu)
        _meme_socle = (_attendu.get("_produit_par", {}).get("numpy")
                       == np.__version__
                       and _attendu.get("_produit_par", {}).get("systeme")
                       == platform.system())
        controler(
            f"la trajectoire est celle de la reference "
            f"(rtol={RTOL_DEBIT:g} sur les debits, atol={ATOL_HEURE:g} h "
            f"sur les decalages)",
            not _ecarts,
            "identique" if not _ecarts else
            f"{len(_ecarts)} ecart(s), dont : " + " | ".join(_ecarts[:3]))
        if _ecarts and not _meme_socle:
            # UN ECART N'EST PAS FORCEMENT UNE REGRESSION. La reference porte
            # le socle qui l'a produite : le dire evite de chercher dans le
            # code une derive qui vient de la bibliotheque.
            print(f"   NOTE : reference produite sous numpy "
                  f"{_attendu.get('_produit_par', {}).get('numpy')} / "
                  f"{_attendu.get('_produit_par', {}).get('systeme')}, ici "
                  f"numpy {np.__version__} / {platform.system()}. Un ecart au "
                  f"dernier chiffre significatif peut venir de la, pas du "
                  f"code — relire les ecarts avant de conclure.")
        if _ecarts:
            print(f"   Les {len(_ecarts)} ecart(s), en entier :")
            for _e in _ecarts[:40]:
                print(f"      {_e}")
            if len(_ecarts) > 40:
                print(f"      … et {len(_ecarts) - 40} autre(s)")
            print("   Si le changement est VOULU : "
                  "« python calage.py --figer-reference », puis relire le diff.")

    print()
    if echecs:
        print(f"   {len(echecs)} CONTROLE(S) EN ECHEC : {echecs}")
        raise SystemExit(1)
    print("   Tous les controles passent.")
    print("=" * 74)
