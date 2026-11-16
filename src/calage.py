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
ETAPE_SANS_APPORT = "sans_apport"
PREFIXE_ETAPE_APPORT = "Apport_"
# ETAT FINAL, TOUS LES APPORTS CALES. Il existait deja : c'est le plan de la
# DERNIERE etape d'apport, qui porte tous les apports cales ET leurs
# resultats — la verification globale se borne a le relire. Rien ne le
# distinguait d'une etape intermediaire : il fallait savoir de tete quel
# apport etait le dernier pour retrouver l'etat complet. Voir Modele.conclure :
# on le RETITRE, on ne le clone pas.
# SOULIGNE, PAS ESPACE, DEPUIS LE 08/09/2026 (decision utilisateur). Les
# trois titres d'etape s'ecrivent desormais d'un seul tenant —
# « Q100_sans_apport », « Q100_Apport_A1 », « Q100_avec_apports » — et le
# separateur de prefixe suit (SEPARATEUR_PREFIXE). Ils se copient ainsi sans
# se couper, se cherchent sans espace insecable, et « Apport_<nom> » n'est
# plus le seul a etre lisible d'un bloc.
#   CE QUE CELA CASSE, ET IL FAUT LE SAVOIR : la reprise d'un calage
# ANTERIEUR au 08/09. plan_par_titre compare les « Plan Title » caractere
# pour caractere ; un projet dont les etapes s'appellent « Q100-sans apport »
# ne sera plus reconnu, et une relance y ouvrira une seconde serie a cote de
# la premiere au lieu de la remplacer. Les trois calages livres sont
# termines : le cas ne se pose que si l'on rouvre l'un d'eux.
ETAPE_AVEC_APPORTS = "avec_apports"

# LONGUEUR MAXIMALE D'UN TITRE D'ETAPE. Borne DE FICHIER, pas d'affichage :
# elle vaut pour le champ « Short Identifier » du plan, dont RAS Mapper fait
# le NOM DU DOSSIER DE RESULTATS (documentation USACE : le sous-repertoire des
# cartes stockees est « labeled the same name as the RAS Plan Short ID »).
#
# ELLE NE VIENT PAS DU FORMAT : C'EST ras-commander QUI LA POSE. Le titre
# d'etape est ecrit dans TROIS champs, et chacun a sa contrainte propre :
#
#   « Short Identifier= » du .pXX : HEC-RAS 7.0.1 en accepte AU MOINS 40.
#       Mesure du 20 septembre 2026 : une regle de 40 caracteres
#       (« ----+----1----+----2----+----3----+----4 ») tapee dans le champ
#       « Short ID » de l'interface, plan enregistre, HEC-RAS ferme, ligne du
#       .pXX relue INTACTE. Plancher demontre, pas limite : l'interface bourre
#       le champ a 64 sur 67 des 103 plans releves dans 01-cas_test/, et
#       l'essai s'est arrete a 40. ras-commander, lui, tronque ce champ a 24
#       EN SILENCE (RasPlan.set_shortid, clone_plan) — sans effet sur notre
#       chemin : _renommer_plan reecrit la ligne derriere le clonage.
#
#   « Plan Title= » du .pXX et « Flow Title= » du .uXX : ras-commander 0.99.1
#       LEVE ValueError au-dela de 32 (« Plan title must be 32 characters or
#       less »), dans clone_plan et clone_unsteady — que le pilote appelle
#       tous deux avec le titre d'etape. Ce n'est pas une troncature qu'on
#       pourrait reecrire apres coup : c'est un refus, au milieu du calage.
#
# 32 EST DONC LE PLAFOND EFFECTIF, et il est de la BIBLIOTHEQUE. Le relever
# demande de cesser de passer « new_title= » a clone_plan / clone_unsteady et
# de titrer uniquement par _renommer_plan / _renommer_unsteady, qui eux ne
# tronquent rien. Tant que l'appel existe, 32 est la borne — monter la
# constante ne ferait que deplacer le refus du controle vers le calcul.
#
# CE QUE 30 COUTAIT, ET D'OU IL VENAIT. Du meme releve de 103 plans : 14 y
# depassaient 24, jusqu'a 30 caracteres, ecrits ET calcules par l'interface.
# C'etait le plus long EXEMPLE rencontre, pas une limite eprouvee. Un prefixe
# de scenario de douze caracteres suffisait a le franchir — un calage
# « Riviere1-Q10 » repris a son sixieme apport demande
# « Riviere1-Q10_sans APP07 et aval », 31 — et la chaine refusait au
# lancement un titre que HEC-RAS comme ras-commander acceptaient.
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
LONGUEUR_MAX_TITRE_PLAN = 32

# TITRES COURTS ET HOMOGENES SOUS UN PREFIXE (02/11/2026, demande utilisateur :
# « diminuer la longueur des plans et unsteady flow et homogeneiser le rendu »).
# Un seul separateur, et l'etape ne porte plus que ce qui la distingue :
#     « Q100-sans »   « Q100-A1 »   « Q100 » (plan final)   « Q100-sans A3 » (reprise)
# Remplace le souligne du 08/09 et le « - » espace du 23/10. Les plans deja
# ecrits sous ces formes ne sont plus reconnus par la reprise : decision de
# l'utilisateur, un calage en cours se relance depuis le debut.
SEPARATEUR_PREFIXE = "-"
ETAPE_SANS_APPORT_COURTE = "sans"
SUFFIXE_ETAPE_REPRISE = " et aval"


def _nom_sous_prefixe(nom):
    """Partie du titre qui suit le prefixe : ce qui distingue l'etape."""
    nom = str(nom)
    if nom == ETAPE_SANS_APPORT:
        return ETAPE_SANS_APPORT_COURTE
    if nom.startswith(PREFIXE_ETAPE_APPORT):
        return nom[len(PREFIXE_ETAPE_APPORT):]
    return nom.removesuffix(SUFFIXE_ETAPE_REPRISE)


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

    LE SEPARATEUR EST POSE ICI, PAS LAISSE A LA SAISIE : « Q100 », « Q100- » et
    « Q100_ » doivent rendre le MEME titre. _remplacer_homonymes et
    plan_par_titre comparent le « Plan Title » caractere pour caractere ; deux
    ecritures du meme prefixe donneraient des plans non homonymes, que rien ne
    remplacerait ni ne retrouverait — le doublon meme que le prefixe supprime.

    LE PLAN FINAL PORTE LE PREFIXE SEUL. Il perd le suffixe qui l'empechait de
    rencontrer un plan de l'ingenieur : le plugin demande confirmation avant
    d'en remplacer un. Le plan SOURCE de ce nom est remplace des que tous
    les apports sont retenus (accord donne au lancement, « Remplacer_plan_
    source » ; regle du 16/11/2026) ; sans cet accord, le pont le refuse.

    COPIE dans calage_apports/plugin.py (_titre_etape), qui ne peut pas
    importer la chaine : changer l'une, c'est changer l'autre.

    PREFIXE VIDE = LE COMPORTEMENT D'AVANT, AU CARACTERE PRES.
    """
    prefixe = str(prefixe or "").strip().rstrip("-_ ")
    if not prefixe:
        titre = str(nom)
    elif nom == ETAPE_AVEC_APPORTS:
        titre = prefixe
    else:
        titre = f"{prefixe}{SEPARATEUR_PREFIXE}{_nom_sous_prefixe(nom)}"
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

    def retarder(self, heures, apports):
        """
        Retarde TOUT L'AXE TEMPOREL du modele d'au moins « heures ».
        Facultatif, et sans effet par defaut.

        Les entrees NON calees (alimentation amont, apports hors de la liste)
        commencent « heures » plus tard ; les « apports » a caler, eux, sont
        reecrits par le calage et n'ont qu'a couvrir la fenetre allongee.

        POURQUOI. Le decalage Δt aligne le pic du calcul sur celui de la
        cible. Quand le calcul culmine TOT et la cible TARD, Δt est tres
        negatif : la cible decalee commence AVANT le debut de la simulation,
        et sa montee ne peut pas etre injectee (cas reel du 30/10/2026 :
        entree a 2 h, cible a 4,5 h, Δt = -2,4 h ; l'apport demarrait a
        4,19 m3/s des t = 0). Retarder les entrees decale le calcul, donc Δt,
        sans rien changer a la physique.

        Retourne le retard effectivement applique, en heures, ou None.
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
    # OBJECTIF DEGRADE D'UN CRAN (16/11/2026, demande utilisateur : « si
    # l'objectif n'est pas atteint, continuer en degradant de 5 % l'objectif
    # sur le volume et / ou la forme et mettre l'apport en orange »). Quand la
    # recherche d'un apport s'arrete sans concordance, l'essai retenu est
    # rejuge avec le volume admis a tolerance_volume + ce cran et la forme a
    # r_min - ce cran. LA POINTE GARDE SA TOLERANCE : c'est elle qui fait
    # l'alea. Tenu : l'apport est retenu « degrade » et le calage continue.
    # Sinon : arret, comme avant. UN SEUL CRAN (decision utilisateur) : l'ecart
    # accepte reste borne et connu. 0 = jamais de degradation.
    degradation_objectif: float = 0.05
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
    # Vide = les titres d'avant : « sans_apport », « Apport_A1 ». « Q100 »
    # donne « Q100-sans », « Q100-A1 » et, a l'arrivee, « Q100 ».
    # Sans lui, caler le Q10 apres le Q100 sur le meme modele efface les plans
    # du Q100 : jalonner() remplace les homonymes, et les deux calages titrent
    # leurs etapes pareil.
    prefixe_etape: str = ""
    # RECALAGE D'UN PLAN VALIDE QUI GARDE SON NOM (10/11/2026). Le plan source
    # porte deja le titre final et l'ingenieur a accepte, au lancement, de le
    # voir remplace. DES QUE TOUS LES APPORTS SONT RETENUS (16/11/2026,
    # decision utilisateur ; « conforme » seulement jusque-la) : le plan final
    # prend ce titre, le plan source est supprime. Un calage arrete sur un
    # apport le laisse intact. caler() ne lit plus ce champ — il conclut tout
    # calage mene au bout ; c'est le pilote qui sait quel plan il a le droit
    # de remplacer (PiloteHecRas.plan_a_remplacer).
    remplacer_plan_source: bool = False

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
    # RETENU SUR L'OBJECTIF DEGRADE (Configuration.degradation_objectif) :
    # valide, donc le calage continue, mais hors des tolerances demandees —
    # « motif » dit alors de combien et pourquoi. L'orange du suivi.
    degrade: bool = False
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
    # LE Dt AUQUEL « fenetre_principale » SE RAPPORTE. fenetre_injection la
    # mesure sur « cible(t - Dt) - section(t) » : ses bornes sont des instants
    # de SIMULATION. diagnostiquer() en a besoin pour lire la cible au bon
    # endroit — sans lui, il juge la cible sur un intervalle decale de Dt.
    # Repasse a la verification finale et a l'etape 7, qui recalculent.
    decalage_fenetre_h: float = None


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
    # NI CONFORME NI EN ECHEC : a la verification finale, aucune section hors
    # de l'objectif degrade, et une au moins hors de l'objectif demande.
    objectif_degrade: bool = False
    motif: str = ""
    # ALERTES QUI NE VISENT AUCUN APPORT EN PARTICULIER mais le calage entier.
    # Diagnostic.alertes est par apport ; il n'y avait aucun canal pour ce qui
    # se constate sur l'ENSEMBLE des sections — la coherence du decalage le
    # long de l'axe, par exemple. Non bloquantes par construction : elles
    # n'entrent pas dans conforme, qui reste l'affaire des diagnostics.
    alertes_chaine: list = field(default_factory=list)
    # RETARD DE L'AXE TEMPOREL DU MODELE, en heures (voir Modele.retarder).
    # 0 = les entrees du modele sont restees a leurs heures d'origine.
    retard_axe_h: float = 0.0


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


def avance_hors_simulation(temps_cible, debit_cible, decalage_h, debut_h,
                           seuil_pic=0.01):
    """
    Heures dont la cible DECALEE commence avant le debut de la simulation.

    La cible decalee est cible(t - Δt) : son debut tombe a t_debut + Δt, ou
    t_debut est le premier instant ou la cible atteint « seuil_pic » de son
    pic (1 % : en deca, ce qui serait perdu ne pese ni sur le volume ni sur
    la forme). Ce qui tombe avant « debut_h » ne peut pas etre injecte :
    ecart_a_la_cible() n'y voit rien, et l'apport demarre brutalement,
    montee de crue perdue.

    Rend 0.0 quand la cible decalee tient entiere dans la simulation.
    """
    t = np.asarray(temps_cible, dtype=float)
    q = np.asarray(debit_cible, dtype=float)
    if t.size == 0 or float(np.max(q)) <= 0.0:
        return 0.0
    t_debut = float(t[int(np.argmax(q >= seuil_pic * float(np.max(q))))])
    return max(0.0, float(debut_h) - (t_debut + float(decalage_h)))


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
    sur un apport d'un modele reel (le cas est nomme dans STATUT.txt § 5) :
    25 % du volume de crue hors fenetre la ou le commentaire promettait
    2,5 %.
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


def concordance_degradee(diag, config):
    """
    L'objectif DEGRADE D'UN CRAN est-il tenu ? Volume et forme relaches de
    Configuration.degradation_objectif, POINTE INCHANGEE.

    Ne se substitue jamais a concordance() : la recherche vise toujours
    l'objectif demande, et ce test ne juge que l'essai RETENU, une fois la
    recherche arretee. Une forme non calculable (r = NaN) echoue d'elle-meme.
    """
    cran = config.degradation_objectif
    return bool(
        cran > 0
        and abs(diag.rapport_volume - 1.0) <= config.tolerance_volume + cran
        and abs(diag.rapport_pic - 1.0) <= config.tolerance_pic
        and diag.r >= config.r_min - cran)


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------


@dataclass
class _EtatApport:
    """
    Ce que les etapes du calage d'UN apport se passent de l'une a l'autre.

    caler() en construit un par apport ; chaque etape y lit ce que les
    precedentes ont etabli et y ecrit ce qu'elle etablit a son tour. Tant que
    ces valeurs etaient des variables locales de caler(), aucune etape ne
    pouvait en sortir sans emporter une quinzaine d'arguments — c'est ce qui
    tenait la fonction a pres de 700 lignes (P1-4 de AUDIT.md).

    UN ETAT NEUF A CHAQUE APPORT : rien n'y vient du tour precedent. Une
    variable locale qu'une branche oubliait de poser, elle, gardait sans
    bruit la valeur de l'apport d'avant.
    """
    # --- l'apport, sa section, sa cible ---------------------------------
    i: int                          # rang dans la liste des apports, de 0
    apport: str
    section: str
    temps_cible: object
    debit_cible: object
    # --- etape 1 : estimation initiale, apport a zero --------------------
    temps_residuel: object = None
    residuel: object = None         # None = la section n'a pas pu etre lue
    manquant: object = None         # cible(t - Dt) - residuel(t)
    decalage_zero: float = None     # Dt : mesure une fois, puis fige
    bornes_fenetre: tuple = None    # fenetre jugee ; None = toute la serie
    cliquet: float = None           # rapport de volume minimal atteignable
    part_apport: float = None       # part de l'apport dans le debit de pointe
    # --- boucle d'essais -------------------------------------------------
    debut_apport: float = None      # horloge, a l'entree de la recherche
    # « poursuivre » tant que la recherche court, puis « converge » ou
    # « arret » ; le motif dit pourquoi elle s'est arretee.
    # « degrade » : objectif degrade tenu, voir _degrader_objectif.
    issue: str = "poursuivre"
    motif: str = ""
    # LA RECHERCHE S'EST ARRETEE SUR L'OBJECTIF, et non sur un calcul rejete,
    # une section illisible ou une cible hors d'atteinte : seul cas ou
    # l'objectif degrade peut etre essaye.
    objectif_manque: bool = False
    courant: object = None          # hydrogramme d'apport de l'essai en cours
    volume_initial: float = 0.0
    essais: int = 0
    historique_rapport: list = field(default_factory=list)
    diag: object = None             # diagnostic du dernier essai, ou du retenu
    temps_calcule: object = None
    debit_calcule: object = None
    meilleur: dict = None           # le meilleur essai rencontre
    degradations: int = 0           # essais consecutifs qui s'en eloignent
    # --- restitution -----------------------------------------------------
    essai_en_place: int = 0         # rang de l'essai laisse dans le modele


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
               « sans_apport » est exact quand la liste couvre TOUS les apports
               du modele. En reprise — les apports amont deja cales ne sont pas
               dans la liste, donc pas remis a zero — l'appelant doit fournir un
               nom qui le dise, sinon la trace conservee ment sur son contenu.
               Donne SANS le prefixe de scenario : caler() le pose lui-meme sur
               tout ce qu'il titre.

    Retourne un ResultatCalage.
    """
    # AUTANT D'APPORTS QUE DE SECTIONS ET DE CIBLES, OU RIEN (11/11/2026). La
    # boucle les parcourt par zip() : une liste plus courte TRONQUAIT les
    # autres en silence, et le calage finissait « non conforme » sans motif,
    # apres des heures de calcul sur un sous-ensemble que personne n'avait
    # demande. Le refus arrive avant modele.preparer(), donc avant tout calcul.
    if not len(apports) == len(sections) == len(cibles):
        raise ValueError(
            f"{len(apports)} apport(s), {len(sections)} section(s) et "
            f"{len(cibles)} cible(s) : il en faut autant de chaque, dans le "
            f"meme ordre — un apport, sa section de controle, sa cible.")
    config = config or Configuration()
    dire = journal if journal is not None else print
    debut = time.time()
    resultat = ResultatCalage(config=config)

    modele.preparer()

    # --- etape 0 : etat de reference --------------------------------------
    residuels_reference = _calculer_reference(
        modele, apports, sections, cibles, config, suivi, resultat, dire,
        etape_reference)
    if residuels_reference is None:
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
    duree_en_vigueur = None    # derniere duree ecrite par limiter_duree()

    for i, (apport, section) in enumerate(zip(apports, sections)):
        temps_cible, debit_cible = cibles[i]
        etat = _EtatApport(i, apport, section, temps_cible, debit_cible)
        if suivi is not None:
            _sans_interrompre(suivi.commencer_apport, i)
        dire(f"\n=== Apport {i + 1}/{len(apports)} : {apport} -> {section} ===")

        # --- etape 1 : estimation initiale --------------------------------
        _estimer_apport(modele, etat, config, points_axe, dire)

        # --- duree simulee ajustee a CET apport ---------------------------
        #
        # APRES le jalon, donc sur le plan de l'etape et jamais sur le plan de
        # reference. Le calendrier a ete etabli une fois pour toutes sur le
        # calcul de reference (voir _calendrier_durees) : le lire ici plutot
        # que le recalculer evite de le mesurer sur un calcul deja raccourci.
        duree_en_vigueur = _ajuster_duree_simulee(
            modele, durees_simulees, i, duree_en_vigueur, config, dire)

        # --- boucle d'essais, puis retour au meilleur d'entre eux ---------
        _essayer_apport(modele, etat, config, suivi, resultat, dire)
        _restituer_meilleur(modele, etat, dire)
        _degrader_objectif(modele, etat, config, suivi, resultat, dire)

        # --- verdict de l'apport : un echec arrete la sequence ------------
        valide = _retenir_apport(etat, config, suivi, resultat)
        if not valide:
            dire(f"    ARRET sur cet apport : {etat.motif}")
            resultat.motif = (f"apport {apport} non cale : {etat.motif}. "
                              f"Les apports suivants ne sont pas traites : la "
                              f"resolution sequentielle suppose l'amont fige.")
            break

        # --- etape 7 : coherence des sections amont -----------------------
        if config.controle_amont and i > 0:
            _signaler_coherence_amont(
                modele, sections[:i], cibles[:i],
                [a.fenetre_principale for a in resultat.apports[:i]],
                config, apport, dire,
                [a.decalage_fenetre_h for a in resultat.apports[:i]])

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
        # .pXX.hdf. Un plan « avec_apports » vide a cote d'un
        # « Apport_<dernier> » qui a les resultats serait pire que pas de plan
        # final du tout.
        #
        # SANS ATTENDRE LE VERDICT : « avec_apports » enonce un CONTENU, pas
        # une conformite — celle-ci se lit dans les livrables et le suivi. Un
        # calage NON conforme est justement celui qu'on rouvre, et lui refuser
        # ce nom le renverrait a la confusion qu'on corrige. En revanche rien
        # n'est retitre si la sequence s'est arretee en chemin : on n'entre
        # dans ce bloc que si tous les apports sont valides.
        #
        # LE PLAN SOURCE QUI PORTE DEJA CE TITRE EST REMPLACE ICI AUSSI
        # (16/11/2026, decision utilisateur : « des que tout est cale »,
        # apports verts ou orange). Du 10/11 au 16/11 il ne l'etait que sur un
        # calage CONFORME : un calage mene au bout mais non conforme a la
        # verification laissait le plan valide en place et le recalage sous
        # un titre d'etape, a renommer a la main. Seul un calage ARRETE sur
        # un apport — qui n'entre pas dans ce bloc — laisse le plan source
        # intact.
        _conclure(modele,
                  titre_etape(ETAPE_AVEC_APPORTS, config.prefixe_etape),
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


def _calculer_reference(modele, apports, sections, cibles, config, suivi,
                        resultat, dire, etape_reference):
    """
    Etape 0 : met a zero les apports a caler, calcule l'etat de reference, y
    lit TOUTES les sections et, s'il le faut, retarde l'axe temporel du
    modele — ce qui demande un second calcul de reference, et un seul.

    Rend les residuels de reference, un (temps, debit) par section, ou None
    quand rien ne peut etre cale sur cette base : le motif est alors ecrit
    dans resultat et dit au journal, et c'est a caler() de s'arreter.
    """
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
    # LA LIGNE NOMME CE QU'ELLE MET A ZERO. « tous les apports a caler » se
    # lisait « tous les apports » sur une REPRISE, ou la liste ne porte que
    # l'aval du point de depart : on croyait le calage en train de defaire le
    # travail des apports amont, qu'il ne touche pas (14/09/2026, retour
    # utilisateur sur un calage reel repris a son dernier apport).
    dire(f"Calcul de reference : {len(apports)} apport(s) mis a zero "
         f"({', '.join(apports)}), pour mesurer ce que les sections "
         f"recoivent sans eux. Les apports hors de cette liste gardent la "
         f"valeur du plan de depart.")
    # DEUX PASSES AU PLUS : la seconde suit un retard de l'axe temporel —
    # voir plus bas et Modele.retarder.
    retard_mesure = False
    while True:
        calcul = modele.calculer()
        resultat.nb_calculs += 1
        _noter_bilan(suivi, calcul, config)
        acceptable, motif_qualite = qualite_acceptable(calcul, config)
        if not acceptable:
            resultat.motif = (
                f"le calcul de reference (apports a zero) n'est pas exploitable : "
                f"{motif_qualite}. Rien ne peut etre cale sur cette base.")
            dire(f"    ARRET : {resultat.motif}")
            return None

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
            return None

        if retard_mesure:
            break
        retard_mesure = True
        # L'AXE TEMPOREL EST-IL ASSEZ LONG AVANT L'EVENEMENT ? Quand une
        # section culmine bien avant sa cible, Δt est tres negatif et la cible
        # decalee commence AVANT le debut de la simulation : sa montee ne peut
        # pas etre injectee (cas reel du 30/10/2026). On mesure ici, sur le
        # calcul de reference, ce qu'il manque a CHAQUE section, et on retarde
        # le modele une fois pour toutes du plus grand de ces manques. Mesure
        # a apports nuls, donc approchee : l'avance restante est redite
        # apport par apport, au journal.
        retard = max((avance_hors_simulation(
            tc, qc, decalage_minimisant_ecart(tc, qc, tr, qr), tr[0])
            for (tc, qc), (tr, qr) in zip(cibles, residuels_reference)),
            default=0.0)
        if retard <= 1e-6:
            break
        try:
            applique, cause = modele.retarder(retard, list(apports)), ""
        except Exception as e:                              # noqa: BLE001
            applique, cause = None, f" ({type(e).__name__}: {e})"
        if not applique:
            dire(f"    ATTENTION — une cible decalee commence {retard:.2f} h "
                 f"avant le debut de la simulation, et ce modele ne sait pas "
                 f"retarder ses entrees{cause} : la montee de crue "
                 f"correspondante ne sera pas injectee.")
            break
        resultat.retard_axe_h = float(applique)
        resultat.alertes_chaine.append(
            f"axe temporel du modele retarde de {applique:.2f} h : les "
            f"entrees non calees commencent {applique:.2f} h plus tard et la "
            f"simulation dure {applique:.2f} h de plus. Sans cela, une cible, "
            f"une fois decalee, commencait {retard:.2f} h avant le debut de "
            f"la simulation, et sa montee de crue etait perdue.")
        dire(f"    axe temporel retarde de {applique:.2f} h (une cible "
             f"decalee commencait {retard:.2f} h avant la simulation) — "
             f"nouveau calcul de reference")
    return residuels_reference


def _estimer_apport(modele, etat, config, points_axe, dire):
    """
    Etape 1 : lit le residuel de la section, ouvre l'etape de l'apport et
    mesure CE QUI MANQUE, apport a zero — le manque, le decalage, la fenetre
    jugee, le cliquet, la part de l'apport. Tout est ecrit dans l'etat.

    Sans residuel lisible, l'issue de la recherche est deja « arret », et le
    motif dit pourquoi.

    points_axe : recoit le point de cet apport (heure du pic cible, Dt
    retenu, largeur de la fenetre jugee), pour la coherence du decalage que
    caler() juge a la fin.
    """
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
        etat.temps_residuel, etat.residuel = modele.lire_section(etat.section)
        echec_lecture = ""
    except Exception as e:                              # noqa: BLE001
        etat.temps_residuel, etat.residuel = None, None
        echec_lecture = f"{type(e).__name__}: {e}"

    # NOUVELLE ETAPE AVANT LA PREMIERE ECRITURE de cet apport : ce qui
    # precede — etat de reference ou apport precedent valide — reste ainsi
    # fige dans ses propres fichiers, relisible tel quel.
    _jalonner(modele, etape_apport(etat.apport, config.prefixe_etape), dire)

    # --- premiere estimation : CE QUI MANQUE, apport a zero -----------
    #
    # Pas un facteur applique a une forme supposee, mais l'ecart mesure
    # lui-meme. C'est deja la bonne forme au premier ordre : le deficit
    # porte l'information de volume, de pointe ET d'allure.
    if etat.residuel is None:
        # LA CAUSE EST DITE. Le message ne portait que le symptome, et
        # une lecture qui echoue a dix raisons possibles — section absente
        # du modele, nom mal orthographie, resultats non ecrits. Sans la
        # phrase de l'exception, chaque diagnostic repartait de zero.
        etat.issue, etat.motif = "arret", (
            f"impossible de lire le debit a la section « {etat.section} » "
            f"avec l'apport a zero : sans cet etat de reference, aucune "
            f"estimation n'est possible."
            + (f" Cause : {echec_lecture}" if echec_lecture else ""))
        etat.manquant = None
        etat.decalage_zero = 0.0
        etat.bornes_fenetre = None
        # DEFINI DANS LES DEUX BRANCHES. Sans cela il garderait la valeur
        # de l'apport PRECEDENT — la boucle porte sur les apports, et une
        # variable laissee de cote y traverse les tours sans bruit.
        # (Ecrit quand c'etait une variable locale de caler(). L'etat est
        # desormais NEUF a chaque apport — voir _EtatApport : une branche
        # qui l'oublierait laisserait None, et cela se verrait.)
        etat.cliquet = 1.0
        etat.part_apport = None
    else:
        # Meme raisonnement que pour les corrections suivantes : le
        # residuel arrive decale, et le soustraire tel quel melerait un
        # dephasage au deficit reel.
        #
        # MESURE UNE SEULE FOIS, ICI, PUIS FIGEE pour tous les essais
        # suivants (voir decalage_minimisant_ecart). C'est exactement le
        # geste manuel : lire l'heure du pic dans le calcul a apport nul,
        # la comparer a celle du pic cible, une fois pour toutes.
        etat.decalage_zero = decalage_minimisant_ecart(
            etat.temps_cible, etat.debit_cible,
            etat.temps_residuel, etat.residuel)
        etat.manquant = ecart_a_la_cible(etat.temps_cible, etat.debit_cible,
                                         etat.temps_residuel, etat.residuel,
                                         etat.decalage_zero)
        dire(f"    la section recoit deja "
             f"{float(np.max(etat.residuel)):.1f} m3/s sans cet apport, "
             f"pour une cible a {float(np.max(etat.debit_cible)):.1f} "
             f"(decalage retenu {etat.decalage_zero:+.2f} h)")
        # CE QUE LE RETARD DE L'AXE N'A PAS COUVERT : il a ete mesure a
        # apports nuls, et Δt se remesure ici, l'amont cale.
        avance = avance_hors_simulation(
            etat.temps_cible, etat.debit_cible,
            etat.decalage_zero, etat.temps_residuel[0])
        if avance > 1e-6:
            dire(f"    ATTENTION — la cible decalee commence "
                 f"{avance:.2f} h avant le debut de la simulation : sa "
                 f"montee de crue ne peut pas etre injectee.")

        # L'APPORT EST-IL SEULEMENT IDENTIFIABLE A CETTE TOLERANCE ? La
        # regle, sa mesure (08/08/2026 : 2 % de part, +200 % sur l'apport,
        # section a 100,5 %) et son texte vivent dans
        # criteres.reserve_identifiabilite. Ici on mesure la PART, on
        # l'annonce au journal avant tout essai, et on la passe a chaque
        # diagnostic : c'est lui qui la porte jusqu'au classeur, a la
        # note de synthese et au suivi (07/09/2026).
        pic_cible = float(np.max(etat.debit_cible))
        pic_residuel = float(np.max(etat.residuel))
        etat.part_apport = ((pic_cible - pic_residuel) / pic_cible
                            if pic_cible else 0.0)
        _reserve = reserve_identifiabilite(etat.part_apport,
                                           config.tolerance_volume)
        if _reserve:
            dire(f"    ATTENTION — {_reserve}")

        # FENETRE DE L'EVENEMENT PRINCIPAL — voir fenetre_injection() et
        # Configuration. Restreint le jugement et la presentation des
        # resultats, pas l'apport injecte.
        if _fenetre_demandee(config):
            etat.bornes_fenetre = fenetre_injection(
                etat.temps_cible, etat.manquant,
                seuil_bas=config.fenetre_seuil_bas,
                seuil_haut=config.fenetre_seuil_haut,
                t0_impose=config.fenetre_t0_h,
                tf_impose=config.fenetre_tf_h,
                volume_reference=_volume(etat.temps_cible, etat.debit_cible),
                perte_max=config.tolerance_volume)
            if config.fenetre_marge_h:
                t_min, t_max = (float(etat.temps_cible[0]),
                                float(etat.temps_cible[-1]))
                etat.bornes_fenetre = (
                    max(etat.bornes_fenetre[0] - config.fenetre_marge_h,
                        t_min),
                    min(etat.bornes_fenetre[1] + config.fenetre_marge_h,
                        t_max))
            dire(f"    hydrogramme principal "
                 f"{etat.bornes_fenetre[0]:.2f} h -> "
                 f"{etat.bornes_fenetre[1]:.2f} h — seule cette fenetre est "
                 f"jugee et presentee ; l'apport reste calcule sur toute "
                 f"la serie")
        else:
            etat.bornes_fenetre = None

        # POUR LA COHERENCE DU DECALAGE LE LONG DE L'AXE, jugee a la fin
        # du calage : le Dt RETENU et la fenetre jugee, tels que la
        # correction les emploie — voir _coherence_points.
        if etat.bornes_fenetre is not None:
            points_axe.append((
                float(etat.temps_cible[int(np.nanargmax(etat.debit_cible))]),
                float(etat.decalage_zero),
                float(etat.bornes_fenetre[1]) - float(etat.bornes_fenetre[0])))

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
        etat.cliquet = cliquet_volume(
            etat.temps_cible, etat.debit_cible, etat.manquant,
            etat.decalage_zero, etat.bornes_fenetre)
        if etat.cliquet > 1.0 + config.tolerance_volume:
            dire(f"    ATTENTION — VOLUME PLANCHER : la section donne "
                 f"deja plus que la cible sur une partie de la fenetre, "
                 f"et un apport ne sait qu'ajouter du debit. Le rapport "
                 f"de volume ne descendra pas au-dessous d'environ "
                 f"{100 * etat.cliquet:.1f} %, pour une tolerance de "
                 f"{100 * config.tolerance_volume:.1f} %. Aucun essai n'y "
                 f"changera rien : c'est le residuel qu'il faut reprendre "
                 f"— apports amont deja cales, ou la cible elle-meme.")


def _ajuster_duree_simulee(modele, durees_simulees, i, duree_en_vigueur,
                           config, dire):
    """
    Ramene la duree simulee de l'etape a ce que l'apport de rang « i »
    demande, d'apres le calendrier, et dit ce que le plafond du plan de
    reference en rogne.

    duree_en_vigueur : derniere duree ecrite par limiter_duree(), toutes
    etapes confondues. Rend sa nouvelle valeur — la meme si rien n'a ete
    reecrit.
    """
    if durees_simulees[i] is not None:
        applique = _sans_interrompre(modele.limiter_duree,
                                     durees_simulees[i])
        if applique:
            duree_en_vigueur = applique
            dire(f"    duree simulee ramenee a {applique:.1f} h — "
                 f"au-dela, plus rien n'est juge ni presente")
        # LE PLAFOND A-T-IL ROGNE ? La duree voulue peut depasser la
        # fenetre du plan de reference (PiloteHecRas.duree_reference_h),
        # qui la borne. None de limiter_duree() = rien reecrit : le plan,
        # clone de l'etape precedente, garde la duree EN VIGUEUR, et
        # c'est elle qu'on compare — sinon un plafond atteint des la
        # deuxieme etape se tait pour toutes les suivantes (22/09/2026 :
        # neuf etapes bornees a 20,5 h pour 21,2 a 23,3 h voulues, et un
        # journal muet).
        #
        # CE QUI SE PERD D'ABORD EST LA MARGE (marge_duree_h), et une
        # marge existe pour etre rognee : journal seulement, decision du
        # 31/08/2026. AU-DELA, C'EST LA FENETRE JUGEE QUI N'EST PLUS
        # SIMULEE ; la couverture le chiffrera a la fin, mais le dire ici,
        # avant le premier calcul de l'etape, c'est le dire des heures
        # plus tot — et nommer le remede.
        en_vigueur = applique or duree_en_vigueur
        if en_vigueur and en_vigueur < durees_simulees[i] - 1e-9:
            perte = durees_simulees[i] - en_vigueur
            if perte <= config.marge_duree_h + 1e-9:
                dire(f"      ({durees_simulees[i]:.1f} h voulues : plafond "
                     f"du plan de reference — {perte:.1f} h de marge en "
                     f"moins, la fenetre jugee reste couverte)")
            else:
                dire(f"    ATTENTION — PLAFOND DU PLAN DE REFERENCE : "
                     f"{durees_simulees[i]:.1f} h voulues, "
                     f"{en_vigueur:.1f} h simulees. Au-dela de la marge "
                     f"de {config.marge_duree_h:.1f} h, "
                     f"{perte - config.marge_duree_h:.1f} h de la fenetre "
                     f"jugee ne seront pas simulees. Allonger la fin de "
                     f"« Simulation Date » du plan de reference, ou "
                     f"designer comme reference un plan a fenetre pleine.")
    return duree_en_vigueur


def _essayer_apport(modele, etat, config, suivi, resultat, dire):
    """
    La boucle d'essais d'un apport : injecter, calculer, diagnostiquer,
    corriger — jusqu'a la concordance, ou jusqu'a un arret motive.

    Part de l'estimation initiale (etat.manquant) et laisse dans l'etat
    l'issue de la recherche, « converge » ou « arret » avec son motif, le
    dernier diagnostic, l'historique des essais et le meilleur d'entre eux.
    NE RESTITUE RIEN : en sortant, le modele porte le DERNIER essai — voir
    _restituer_meilleur.
    """
    etat.debut_apport = time.time()

    # La section recoit-elle DEJA plus que la cible ? On ne peut pas
    # RETIRER du debit avec un apport : le dire tout de suite vaut mieux
    # que d'iterer vers un apport nul en degradant le diagnostic.
    if etat.manquant is not None and float(np.max(etat.manquant)) <= 0.0:
        modele.appliquer_facteur(etat.apport, 0.0)
        etat.issue, etat.motif = "arret", (
            f"la section recoit deja au moins autant que la cible sans "
            f"cet apport (pointe residuelle "
            f"{float(np.max(etat.residuel)):.1f} m3/s pour une cible a "
            f"{float(np.max(etat.debit_cible)):.1f}). Un apport ne peut "
            f"qu'ajouter du debit : la cible est hors d'atteinte par ce "
            f"levier. Verifier les apports amont deja cales, ou la cible "
            f"elle-meme.")
    elif etat.manquant is not None:
        etat.courant = np.maximum(etat.manquant, 0.0)
        etat.volume_initial = max(
            _volume(etat.temps_cible, etat.courant), 1e-9)

    while etat.courant is not None:
        # --- calcul, puis qualite numerique --------------------------
        modele.definir_forme(etat.apport, etat.temps_cible, etat.courant)
        modele.appliquer_facteur(etat.apport, 1.0)
        calcul = modele.calculer()
        resultat.nb_calculs += 1
        _noter_bilan(suivi, calcul, config)
        acceptable, motif_qualite = qualite_acceptable(calcul, config)

        if not acceptable:
            # Un essai rejete n'entre PAS dans l'historique : il n'apprend
            # rien sur la relation apport -> reponse.
            dire(f"    essai {etat.essais + 1} REJETE — {motif_qualite}")
            etat.issue, etat.motif = "arret", (
                f"calcul rejete pour qualite numerique : {motif_qualite}")
            break

        # --- diagnostic ----------------------------------------------
        etat.temps_calcule, etat.debit_calcule = modele.lire_section(
            etat.section)
        etat.diag = diagnostiquer(etat.temps_cible, etat.debit_cible,
                                  etat.temps_calcule, etat.debit_calcule,
                                  tolerance_volume=config.tolerance_volume,
                                  tolerance_pic=config.tolerance_pic,
                                  r_min=config.r_min,
                                  fenetre=etat.bornes_fenetre,
                                  part_apport=etat.part_apport,
                                  decalage_fenetre_h=etat.decalage_zero)
        etat.essais += 1

        etat.historique_rapport.append({
            "essai": etat.essais,
            "facteur": (_volume(etat.temps_cible, etat.courant)
                        / etat.volume_initial),
            "volume": etat.diag.rapport_volume,
            "pic": etat.diag.rapport_pic, "r": etat.diag.r})

        # MEMORISER LE MEILLEUR. La reponse du modele n'est pas lineaire :
        # la recherche peut passer pres de la concordance puis s'en
        # eloigner. Rendre le DERNIER essai serait alors absurde.
        #
        # LE CLASSEMENT EST (admissibilite, erreur combinee) : un essai
        # qui tient les trois seuils passe devant tous les autres, et
        # entre deux essais de meme admissibilite c'est celui qui est le
        # plus proche des trois cibles A LA FOIS qui est retenu.
        if (etat.meilleur is None
                or rang_essai(etat.diag, config) < etat.meilleur["rang"]):
            etat.meilleur = {
                "rang": rang_essai(etat.diag, config),
                "apport": etat.courant.copy(),
                "diag": etat.diag, "essai": etat.essais,
                "series": (etat.temps_cible, etat.debit_cible,
                           etat.temps_calcule, etat.debit_calcule)}
            etat.degradations = 0
        else:
            etat.degradations += 1

        atteint = concordance(etat.diag, config)
        dire(f"    essai {etat.essais} : "
             f"volume {100 * etat.diag.rapport_volume:5.1f} %  "
             f"pointe {100 * etat.diag.rapport_pic:5.1f} %  "
             f"forme {100 * etat.diag.r:5.1f} %"
             + ("  -> concordance atteinte" if atteint else ""))
        _suivre_essai(suivi, etat)

        if atteint:
            etat.issue = "converge"
            break

        # VOLUME EXCEDENTAIRE ET POINTE DEFICITAIRE : les deux exigences
        # se contredisent, car un apport ne sait qu'AJOUTER du debit — il
        # remplit un hydrogramme trop maigre, il n'affute pas un
        # hydrogramme trop plat. On le DIT, sans arreter.
        if (etat.diag.rapport_volume > 1.0 + config.tolerance_volume
                and etat.diag.rapport_pic < 1.0 - config.tolerance_pic):
            dire("      volume DEJA excedentaire alors que la pointe "
                 "manque : l'hydrogramme calcule est trop ETALE, pas "
                 "trop faible. Rehausser la pointe aggravera le volume. "
                 "Pistes : resserrer les apports amont deja cales, "
                 "rapprocher l'injection de la section, ou revoir la "
                 "cible.")

        # Deux essais consecutifs qui s'eloignent : insister ne fera
        # qu'empirer. On s'arrete et on retient le meilleur.
        if etat.degradations >= 2:
            etat.objectif_manque = True
            etat.issue, etat.motif = "arret", (
                f"la recherche s'eloigne de la concordance depuis "
                f"l'essai {etat.meilleur['essai']} : le modele repond de "
                f"facon trop non lineaire a cet apport pour aller plus "
                f"loin.")
            break

        if etat.essais >= config.nb_max_essais:
            etat.objectif_manque = True
            etat.issue = "arret"
            _motiver_essais_epuises(etat, config)
            break

        # --- correction ------------------------------------------------
        # L'ecart est calcule APRES recalage temporel, avec le decalage
        # FIGE a l'itération 0 (jamais remesure) : sans cela, la
        # correction combat le temps de propagation au lieu du defaut
        # d'apport, et le debit de pointe s'emballe.
        manque = ecart_a_la_cible(etat.temps_cible, etat.debit_cible,
                                  etat.temps_calcule, etat.debit_calcule,
                                  etat.decalage_zero)
        precedent = etat.courant
        etat.courant = corriger_apport(etat.courant, manque)
        dire(f"      correction au pic "
             f"{float(np.max(etat.courant - precedent)):+.1f} m3/s")
        if float(np.max(np.abs(etat.courant - precedent))) <= 1e-6:
            etat.objectif_manque = True
            etat.issue, etat.motif = "arret", (
                f"la correction n'a plus d'effet alors que la "
                f"concordance n'est pas atteinte (volume "
                f"{100 * etat.diag.rapport_volume:.1f} %, pointe "
                f"{100 * etat.diag.rapport_pic:.1f} %) : le modele ne repond "
                f"plus a cet apport.")
            break


def _suivre_essai(suivi, etat):
    """
    Transmet au suivi l'essai qui vient d'etre diagnostique — et, au premier
    essai, le residuel dont l'estimation est partie.
    """
    if suivi is not None:
        if etat.essais == 1:
            _sans_interrompre(suivi.enregistrer_residuel, etat.i,
                              (etat.temps_cible, etat.debit_cible),
                              (etat.temps_residuel, etat.residuel),
                              etat.decalage_zero)
        # rapport_volume : c'est la grandeur que la boucle teste et
        # que le journal affiche.
        _sans_interrompre(
            suivi.enregistrer_essai, etat.i,
            _volume(etat.temps_cible, etat.courant) / etat.volume_initial,
            etat.diag.rapport_volume,
            etat.diag.rapport_pic, etat.diag.r, etat.diag.decalage_h,
            (etat.temps_cible, etat.debit_cible,
             etat.temps_calcule, etat.debit_calcule),
            (etat.temps_cible, etat.courant),
            etat.decalage_zero)


def _motiver_essais_epuises(etat, config):
    """
    Ecrit dans l'etat le motif d'une recherche arretee faute d'essais : ou
    elle en etait, si elle avancait encore, et ce que le dernier diagnostic
    signalait.
    """
    etat.motif = (
        f"{etat.essais} essais sans concordance simultanee : volume "
        f"{100 * etat.diag.rapport_volume:.1f} %, pointe "
        f"{100 * etat.diag.rapport_pic:.1f} %, forme "
        f"{100 * etat.diag.r:.1f} % de la cible.")
    # PROGRESSAIT-ON ENCORE ? Une recherche qui plafonne ne
    # gagnera rien a plus d'essais ; une recherche qui avance
    # encore, si.
    pas = _progression_pic(etat.historique_rapport)
    if pas is not None and pas > 1e-5:
        reste = (1.0 - config.tolerance_pic) - etat.diag.rapport_pic
        if reste > 0:
            etat.motif += (
                f" La pointe PROGRESSAIT ENCORE de "
                f"{100 * pas:+.2f} point au dernier essai ; il lui "
                f"manquait {100 * reste:.1f} point(s), soit "
                f"environ {reste / pas:.0f} essai(s) de plus. "
                f"Augmenter Nb_max_iterations_par_apport avant de "
                f"mettre en cause la methode.")
    if etat.diag.alertes:
        etat.motif += " Alertes : " + " ; ".join(etat.diag.alertes)


def _restituer_meilleur(modele, etat, dire):
    """
    Remet dans le modele le MEILLEUR essai quand ce n'est pas le dernier, et
    note dans l'etat le rang de l'essai qui reste en place.
    """
    # RESTITUER LE MEILLEUR ETAT, pas le dernier. Le modele conserve
    # l'hydrogramme du dernier essai : si un essai anterieur etait plus
    # proche de la concordance, c'est lui qu'il faut remettre en place,
    # sans quoi le calage laisserait derriere lui un apport moins bon que
    # celui qu'il a su trouver.
    etat.essai_en_place = etat.essais
    if (etat.meilleur is not None and etat.issue != "converge"
            and etat.meilleur["essai"] != etat.essais):
        modele.definir_forme(etat.apport, etat.temps_cible,
                             etat.meilleur["apport"])
        modele.appliquer_facteur(etat.apport, 1.0)
        etat.essai_en_place = etat.meilleur["essai"]
        etat.diag = etat.meilleur["diag"]
        (etat.temps_cible, etat.debit_cible,
         etat.temps_calcule, etat.debit_calcule) = etat.meilleur["series"]
        dire(f"    retour a l'essai {etat.meilleur['essai']}, le plus proche "
             f"de la concordance (volume "
             f"{100 * etat.diag.rapport_volume:.1f} %, pointe "
             f"{100 * etat.diag.rapport_pic:.1f} %)")


def _degrader_objectif(modele, etat, config, suivi, resultat, dire):
    """
    Quand la recherche s'est arretee sur l'objectif, rejuge l'essai retenu
    sur l'objectif DEGRADE D'UN CRAN (concordance_degradee). Tenu : l'issue
    devient « degrade », et caler() continue. Sinon l'etat ne change pas.

    APPELE APRES _restituer_meilleur : c'est l'essai EN PLACE qui est juge.

    UN RECALCUL QUAND L'ESSAI RETENU N'EST PAS LE DERNIER CALCULE. Le modele
    porte alors l'hydrogramme du meilleur essai et les RESULTATS du dernier.
    Or l'apport suivant lit son residuel dans ces resultats, et la
    verification finale relit le dernier calcul : sans recalcul, ils
    jugeraient un apport qui n'est plus en place. Avant ce cran, un apport
    remis a un essai anterieur arretait toujours le calage, et la question
    ne se posait pas. Le recalcul est juge comme tout calcul : rejete, ou
    hors de l'objectif degrade, l'apport reste en echec.
    """
    if not (etat.objectif_manque and etat.diag is not None
            and concordance_degradee(etat.diag, config)):
        return
    if etat.essai_en_place != etat.essais:
        dire(f"    objectif degrade tenu par l'essai {etat.essai_en_place} : "
             f"recalcul de cet essai, pour que les resultats en place soient "
             f"les siens")
        calcul = modele.calculer()
        resultat.nb_calculs += 1
        _noter_bilan(suivi, calcul, config)
        acceptable, motif_qualite = qualite_acceptable(calcul, config)
        if not acceptable:
            etat.motif += (f" Le recalcul de l'essai {etat.essai_en_place}, "
                           f"qui tenait l'objectif degrade, est rejete : "
                           f"{motif_qualite}")
            return
        etat.temps_calcule, etat.debit_calcule = modele.lire_section(
            etat.section)
        etat.diag = diagnostiquer(etat.temps_cible, etat.debit_cible,
                                  etat.temps_calcule, etat.debit_calcule,
                                  tolerance_volume=config.tolerance_volume,
                                  tolerance_pic=config.tolerance_pic,
                                  r_min=config.r_min,
                                  fenetre=etat.bornes_fenetre,
                                  part_apport=etat.part_apport,
                                  decalage_fenetre_h=etat.decalage_zero)
        if not concordance_degradee(etat.diag, config):
            etat.motif += (f" Le recalcul de l'essai {etat.essai_en_place} "
                           f"ne tient plus l'objectif degrade.")
            return
    etat.issue = "degrade"
    # « AVERTISSEMENT » : le mot auquel l'etape Suivi reconnait ce qui merite
    # l'ecran (MARQUEURS_ALERTE).
    dire(f"    AVERTISSEMENT : OBJECTIF DEGRADE pour {etat.apport} — volume "
         f"{100 * etat.diag.rapport_volume:.1f} %, pointe "
         f"{100 * etat.diag.rapport_pic:.1f} %, forme "
         f"{100 * etat.diag.r:.1f} % ; admis en degrade : "
         f"{_objectif_degrade_en_mots(config)}. L'apport est retenu et le "
         f"calage continue.")


def _objectif_degrade_en_mots(config):
    """« volume a 10 % pres, forme des 92 %, pointe inchangee »."""
    cran = config.degradation_objectif
    return (f"volume a {100 * (config.tolerance_volume + cran):g} % pres, "
            f"forme des {100 * (config.r_min - cran):g} %, pointe inchangee")


def _retenir_apport(etat, config, suivi, resultat):
    """
    Clot la recherche d'un apport : prononce sa validite, complete le motif
    d'un echec ou d'un objectif degrade, inscrit le ResultatApport dans
    resultat et previent le suivi.

    Rend True si l'apport est valide — objectif tenu, ou objectif degrade
    tenu. Sinon etat.motif dit pourquoi, et c'est a caler() d'arreter la
    sequence.
    """
    duree_apport = time.time() - etat.debut_apport
    degrade = etat.issue == "degrade"
    atteint = etat.issue == "converge"
    valide = atteint or degrade
    if not atteint and not etat.motif:
        etat.motif = "concordance volume / pointe / forme non atteinte"

    # LE CLIQUET EST LA PREMIERE CAUSE A CITER QUAND IL JOUE.
    #
    # L'annonce de l'iteration 0 partait au journal, et le VERDICT, lui,
    # disait autre chose : mesure au banc, « le modele repond de facon
    # trop non lineaire a cet apport » pour un volume bloque a 109,6 %
    # quand le plancher valait 109,8 %. Le modele n'y etait pour rien.
    # Un motif qui designe la mauvaise cause envoie corriger la mauvaise
    # chose — ici le maillage ou le pas de calcul, quand ce sont les
    # apports amont ou la cible qu'il faut reprendre.
    if (not atteint and etat.cliquet > 1.0 + config.tolerance_volume
            and etat.diag is not None
            and etat.diag.rapport_volume > 1.0 + config.tolerance_volume):
        etat.motif += (
            f" LE VOLUME NE POUVAIT PAS DESCENDRE PLUS BAS : la "
            f"section donne deja plus que la cible sans cet apport, "
            f"et un apport ne sait qu'ajouter du debit — plancher "
            f"estime a {100 * etat.cliquet:.1f} %, atteint "
            f"{100 * etat.diag.rapport_volume:.1f} %. Reprendre les "
            f"apports amont deja cales, ou la cible, avant de "
            f"mettre en cause la reponse du modele.")

    if degrade:
        etat.motif = (f"objectif degrade ({_objectif_degrade_en_mots(config)})"
                      f" : {etat.motif}")

    resultat.apports.append(ResultatApport(
        nom_apport=etat.apport, nom_section=etat.section, valide=valide,
        degrade=degrade,
        # Le facteur decrit l'essai RETENU. Apres un retour au meilleur
        # essai, prendre le dernier de l'historique decrirait un apport
        # qui n'est plus en place.
        facteur=_facteur_retenu(etat.historique_rapport, etat.essai_en_place),
        diagnostic=etat.diag, essais=etat.essais,
        duree_s=duree_apport, motif="" if atteint else etat.motif,
        historique=etat.historique_rapport,
        fenetre_principale=etat.bornes_fenetre,
        part_apport=etat.part_apport,
        decalage_fenetre_h=etat.decalage_zero))

    if suivi is not None:
        series = ((etat.temps_cible, etat.debit_cible,
                   etat.temps_calcule, etat.debit_calcule)
                  if valide and etat.diag is not None else None)
        if valide:
            _sans_interrompre(suivi.valider_apport, etat.i, etat.diag,
                              duree_apport, series,
                              etat.motif if degrade else "")
        else:
            _sans_interrompre(suivi.echouer_apport, etat.i, etat.motif,
                              etat.diag, duree_apport)
    return valide
        # UN APPORT REMIS EN PLACE N'EST JAMAIS VALIDE : tout essai
        # concordant fait deja sortir la boucle sur « converge » — les
        # essais encore candidats au titre de meilleur ont donc TOUS
        # echoue au meme test, sur le meme diagnostic. Rejouer ce test
        # ici ne pourrait jamais rattraper un essai qui a deja echoue.


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
                          part_apport=a.part_apport,
                          decalage_fenetre_h=a.decalage_fenetre_h)
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
             + ("conforme" if d.converge
                else "OBJECTIF DEGRADE" if _degrade_final(d, config)
                else "NON CONFORME"))
    resultat.conforme = all(d.converge for d in resultat.diagnostics_finaux)
    degradees = [s for s, d in zip(sections, resultat.diagnostics_finaux)
                 if _degrade_final(d, config)]
    resultat.objectif_degrade = bool(degradees) and all(
        d.converge or _degrade_final(d, config)
        for d in resultat.diagnostics_finaux)
    if not resultat.conforme:
        # LE MOTIF DIT CE QUI A ECHOUE, ET OU. Il annoncait autrefois une
        # « derive » quelle que soit la cause : sur un calage dont tous les
        # apports avaient ete valides un par un, cela envoyait chercher un
        # remous inexistant alors que la cause etait ailleurs.
        bloquees = [(s, d) for s, d in zip(sections,
                                           resultat.diagnostics_finaux)
                    if d.alertes_bloquantes]
        derivees = [s for s, d in zip(sections, resultat.diagnostics_finaux)
                    if not d.converge and not d.alertes_bloquantes
                    and s not in degradees]
        causes = []
        if degradees:
            # UNE SECTION ORANGE DONT L'APPORT ETAIT VERT A SON CALAGE a
            # derive depuis : le dire, sinon on la croirait retenue telle
            # quelle, et la passe sequentielle a relancer ne serait pas dite.
            par_derive = [s for s, a in zip(sections, resultat.apports)
                          if s in degradees and not a.degrade]
            causes.append(
                f"objectif degrade sur {degradees} : hors de l'objectif "
                f"demande, dans l'objectif degrade "
                f"({_objectif_degrade_en_mots(config)})"
                + (f" ; {par_derive} par derive a la verification globale, "
                   f"l'apport ayant tenu l'objectif demande a son calage"
                   if par_derive else ""))
        if derivees:
            causes.append(
                f"derive a la verification globale sur {derivees} : "
                f"relancer une passe sequentielle amont -> aval, jamais "
                f"une optimisation globale simultanee")
        for section, d in bloquees:
            causes.append(f"« {section} » : "
                          + " ; ".join(d.alertes_bloquantes))
        resultat.motif = ". ".join(causes) + "."


def _degrade_final(diag, config):
    """
    A la verification finale, la section est-elle « orange » : hors de
    l'objectif demande, dans l'objectif degrade, comparaison valide ?
    """
    return (not diag.converge and not diag.alertes_bloquantes
            and concordance_degradee(diag, config))


def _signaler_coherence_amont(modele, sections_amont, cibles_amont,
                              fenetres_amont, config, apport, dire,
                              decalages_amont=None):
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
        modele, sections_amont, cibles_amont, config, fenetres_amont,
        decalages_amont)
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


def _sections_derivees(modele, sections, cibles, config, fenetres=None,
                       decalages=None):
    """
    Sections deja validees qui sont sorties de tolerance. Simple relecture du
    dernier calcul : aucun calcul supplementaire.

    fenetres : une (t0, tf) par section, dans le meme ordre — celle de
    l'evenement principal detectee pour cette section lors de son propre
    calage (ResultatApport.fenetre_principale). Sans elle (None), chaque
    section est jugee sur sa fenetre commune entiere.

    decalages : le Dt de chacune de ces fenetres, meme ordre
    (ResultatApport.decalage_fenetre_h). Une fenetre sans son Dt est lue sur
    la base de temps de la cible, ce qu'elle n'est pas — voir
    criteres.diagnostiquer.

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
    if decalages is None:
        decalages = [None] * len(sections)
    for section, (t_c, q_c), fenetre, dec in zip(sections, cibles, fenetres,
                                                 decalages):
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
                          fenetre=fenetre,
                          decalage_fenetre_h=dec)
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

    _verifier_resultat_final(resultat)

    sections = [a.nom_section for a in resultat.apports]
    apports = [a.nom_apport for a in resultat.apports]

    dossier = Path(dossier_sortie)
    dossier.mkdir(parents=True, exist_ok=True)
    fichiers = []

    _figures_comparaison(fichiers, resultat, sections, dossier)

    fichiers.append(liv.figure_atteinte(
        sections, resultat.diagnostics_finaux, dossier / "atteinte_cible.png"))

    _figures_convergence(fichiers, resultat, dossier)

    temps_apports, hydrogrammes, dans_fenetre = _hydrogrammes_retenus(
        resultat, modele)
    if temps_apports:
        _figure_apports_retenus(fichiers, apports, temps_apports,
                                hydrogrammes, dans_fenetre, dossier)
        _avertissements_de_queue(fichiers, apports, temps_apports,
                                 hydrogrammes, dans_fenetre)

    # --- profil en long de synthese, si l'axe hydraulique est disponible ---
    if profil is not None and len(profil):
        _profil_en_long_final(fichiers, resultat, sections, apports,
                              dossier, profil, pk_sections, pk_apports)

    xlsx = _tableaux_calage(resultat, sections, apports, temps_apports,
                            hydrogrammes, dans_fenetre, dossier)
    liv.synthese("Calage des apports — note de synthèse", sections,
                resultat.diagnostics_finaux, dossier / "synthese.md",
                alertes_chaine=resultat.alertes_chaine)

    return {"fichiers": fichiers + [xlsx, str(dossier / "synthese.md")],
            "conforme": resultat.conforme}


def _verifier_resultat_final(resultat):
    """Leve si le resultat ne peut pas etre rapporte : rien a livrer, ou
    des listes qui ne se correspondent plus un a un."""
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


def _figures_comparaison(fichiers, resultat, sections, dossier):
    """Une figure de comparaison cible / calcule par section."""
    import livrables as liv
    from suivi import assainir_nom_fichier

    for i, (section, diag) in enumerate(zip(sections, resultat.diagnostics_finaux)):
        t_c, q_c, t_s, q_s = resultat.series_finales[i]
        fichiers.append(liv.figure_comparaison(
            section, t_c, q_c, t_s, q_s, diag,
            dossier / f"comparaison_{i + 1:02d}_{assainir_nom_fichier(section)}.png"))


def _figures_convergence(fichiers, resultat, dossier):
    """Une figure de convergence par apport cale en deux essais ou plus."""
    import livrables as liv
    from suivi import assainir_nom_fichier

    for i, a in enumerate(resultat.apports):
        if len(a.historique) >= 2:
            fichiers.append(liv.figure_convergence(
                a.nom_section, a.historique,
                dossier / f"convergence_{i + 1:02d}_{assainir_nom_fichier(a.nom_apport)}.png"))


def _hydrogrammes_retenus(resultat, modele):
    """
    Hydrogramme retenu de chaque apport, sur SA base de temps, et le masque
    de la fenetre jugee. Retourne (temps_apports, hydrogrammes, dans_fenetre).
    """
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
    return temps_apports, hydrogrammes, dans_fenetre


def _figure_apports_retenus(fichiers, apports, temps_apports, hydrogrammes,
                            dans_fenetre, dossier):
    """La figure des apports retenus, coupes a leur fenetre."""
    import livrables as liv

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


def _avertissements_de_queue(fichiers, apports, temps_apports, hydrogrammes,
                             dans_fenetre):
    """Un avertissement par apport prolonge au-dela de la fenetre simulee."""
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


def _profil_en_long_final(fichiers, resultat, sections, apports, dossier,
                          profil, pk_sections, pk_apports):
    """Le profil en long de synthese, ou la raison pour laquelle il manque."""
    import livrables as liv

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


def _tableaux_calage(resultat, sections, apports, temps_apports,
                     hydrogrammes, dans_fenetre, dossier):
    """Les quatre tableaux du rapport, ecrits dans tableaux_calage.xlsx."""
    import livrables as liv

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
    return xlsx


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

    def retarder(self, heures, apports):
        """
        Retarde d'un nombre entier de pas le debit de base et les apports
        hors de la liste. La grille ne s'allonge pas : la queue de la serie
        sort de la fenetre, ce qui suffit a l'auto-test.
        """
        pas = float(self.temps[1] - self.temps[0])
        n = int(np.ceil(float(heures) / pas - 1e-9))
        if n <= 0:
            return None

        def _retardee(serie):
            return np.concatenate([np.full(n, serie[0]), serie[:-n]])

        self.debit_base = _retardee(self.debit_base)
        for a in self.apports:
            if a not in apports:
                self.formes[a] = _retardee(self.formes[a])
        return n * pas

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
    # LE BANC VIT A COTE, PAS ICI (10/11/2026) : src/bancs/banc_calage.py,
    # absent de l'archive du plugin. Dans le depot, ce relais le joue a
    # l'identique, « --figer-reference » compris (le banc lit sys.argv).
    import runpy
    _banc = Path(__file__).resolve().parent / "bancs" / "banc_calage.py"
    if not _banc.is_file():
        print("Le banc d'auto-tests de calage.py n'est pas livre avec cette "
              "installation.")
        raise SystemExit(2)
    runpy.run_path(str(_banc), run_name="__main__")
