# -*- coding: utf-8 -*-
"""
Criteres de comparaison entre un hydrogramme calcule et un hydrogramme cible,
et strategie de correction de l'apport.

Ce module est INDEPENDANT du code de calcul hydraulique : il ne manipule que
des series temporelles (temps, debit). Il est donc utilisable tel quel avec
HEC-RAS, TELEMAC-2D ou tout autre modele 2D.

Voir methodologie_calage_amont_aval.docx (partie 1 : methodologie generale).
"""

from dataclasses import dataclass, field

import numpy as np

# Pas IMPOSE a tout hydrogramme D'ENTREE (cible saisie par l'utilisateur).
# Un HSMF ou une crue relevee arrive avec le pas de sa source — horaire le
# plus souvent, parfois minute — alors que toute la chaine raisonne sur UNE
# base de temps : c'est elle qui porte le recalage temporel, l'estimation du
# decalage et la forme injectee dans le modele. C'est aussi l'intervalle des
# apports crees dans l'unsteady (pilote_hecras.INTERVALLE_APPORT), pour que
# la cible s'y projette valeur pour valeur. 6 minutes = 0,1 h.
PAS_ENTREE_H = 0.1

# Pas de la grille de reechantillonnage utilisee pour le recalage temporel.
# Expose parce que tout code qui veut TRACER les series recalees a besoin du
# meme pas et de la meme origine pour reconstruire l'axe des temps.
#
# IL VAUT LE PAS D'ENTREE, ET C'EST UNE CORRECTION. Il valait 0,25 h alors que
# toute la chaine — cible normalisee, apport ecrit dans l'unsteady, series
# lues — travaille a 6 min. Trois consequences, toutes mesurees sur un cas de
# recette :
#   - le decalage rapporte etait QUANTIFIE au quart d'heure (-0,75 h) tandis
#     que la correction, qui cherche en continu, employait -0,86 h : les deux
#     nombres differaient d'un pas de temps entier, alors que leurs
#     docstrings affirment mesurer la meme grandeur. Impossible de refaire le
#     calcul a la main a partir du decalage affiche ;
#   - le volume, integre sur cette grille grossiere, s'ecartait de 0,04 point
#     du volume calcule a 6 min — pour une tolerance de 0,5 point, c'est un
#     dixieme du budget consomme par un choix purement numerique ;
#   - r, evalue apres recalage au quart d'heure, perdait 0,2 point (99,68 %
#     au lieu de 99,90 %) : un residu de dephasage non resorbe lu comme un
#     defaut de forme.
# Reechantillonner plus FIN que la donnee n'aurait aucun sens ; au pas de la
# donnee, le recalage ne degrade plus rien.
PAS_RECALAGE_H = PAS_ENTREE_H


# ---------------------------------------------------------------------------
# Recalage temporel
# ---------------------------------------------------------------------------

def reechantillonner(temps, debit, pas_h, debut=None, fin=None):
    """
    Reechantillonne une serie (temps en heures, debit) sur un pas constant.

    debut et fin permettent d'imposer une GRILLE COMMUNE a plusieurs series.
    Hors de la plage de donnees, np.interp prolonge par la valeur de bord.
    """
    temps = np.asarray(temps, dtype=float)
    debit = np.asarray(debit, dtype=float)
    debut = temps[0] if debut is None else debut
    fin = temps[-1] if fin is None else fin
    grille = np.arange(debut, fin + pas_h / 2, pas_h)
    return grille, np.interp(grille, temps, debit)


def pas_serie_h(temps):
    """
    Pas de temps d'une serie, en heures : la MEDIANE des ecarts.

    Mediane et non moyenne : une serie saisie a la main comporte souvent une
    ligne isolee ou un trou, qui deplacerait la moyenne sans rien dire du pas
    reellement employe. Retourne nan en dessous de deux points.
    """
    temps = np.asarray(temps, dtype=float)
    if len(temps) < 2:
        return float("nan")
    return float(np.median(np.diff(temps)))


def normaliser_entree(temps, debit, pas_h=PAS_ENTREE_H):
    """
    Ramene un hydrogramme D'ENTREE au pas pas_h AU PLUS GROSSIER (6 min par
    defaut).

    Retourne (temps, debit, pas_initial_h). pas_initial_h vaut None quand la
    serie ressort inchangee : c'est ce qui permet a l'appelant de ne
    consigner une conversion que lorsqu'il y en a eu une.

    Bornes conservees, interpolation lineaire, aucune valeur extrapolee
    au-dela. Une serie plus GROSSIERE que pas_h est densifiee. Une serie DEJA
    a ce pas ou plus FINE est conservee TELLE QUELLE, a son pas natif : la
    degrader aurait perdu, sur un pic tres bref, de l'information que rien
    en aval n'exige de sacrifier — recaler()/diagnostiquer() reechantillonnent
    de toute facon sur leur propre grille de comparaison, et definir_forme()
    reprojette sur la grille du modele au moment de l'ecriture. Seule une
    serie plus grossiere que le pas commun a besoin d'etre densifiee ici.
    """
    temps = np.asarray(temps, dtype=float)
    debit = np.asarray(debit, dtype=float)
    if len(temps) < 2:
        return temps, debit, None
    pas_initial = pas_serie_h(temps)
    if pas_initial <= pas_h + 1e-9:
        return temps, debit, None
    grille, valeurs = reechantillonner(temps, debit, pas_h)
    return grille, valeurs, pas_initial


def grille_commune(temps_cible, temps_calcule):
    """Bornes de la grille ENGLOBANT les deux series, pour le recalage."""
    tc = np.asarray(temps_cible, dtype=float)
    ts = np.asarray(temps_calcule, dtype=float)
    return min(tc[0], ts[0]), max(tc[-1], ts[-1])


def fenetre_commune(temps_cible, temps_calcule):
    """
    Intervalle ou les DEUX series sont effectivement definies.

    C'est la seule fenetre sur laquelle des volumes soient comparables. Les
    integrer chacun sur sa propre etendue reviendrait a comparer un volume sur
    36 h a un volume sur 48 h : le rapport serait gonfle par la decrue
    supplementaire, sans qu'aucun defaut de calage n'en soit la cause.

    Retourne (debut, fin), ou (nan, nan) si les deux series ne se recouvrent
    pas.
    """
    tc = np.asarray(temps_cible, dtype=float)
    ts = np.asarray(temps_calcule, dtype=float)
    debut, fin = max(tc[0], ts[0]), min(tc[-1], ts[-1])
    return (debut, fin) if fin > debut else (float("nan"), float("nan"))


def volume(temps, debit, debut, fin, pas_h=PAS_RECALAGE_H):
    """Volume ecoule entre debut et fin, temps en heures."""
    if not np.isfinite(debut) or not np.isfinite(fin):
        return float("nan")
    grille, valeurs = reechantillonner(temps, debit, pas_h, debut, fin)
    return float(np.trapezoid(valeurs, grille))


def axe_recale(temps_cible, temps_calcule, nb_points, pas_h=PAS_RECALAGE_H):
    """
    Axe des temps correspondant aux series retournees par recaler().

    Le reconstruire a partir de la seule etendue de la cible serait faux : les
    series recalees vivent sur la grille COMMUNE aux deux, qui peut etre plus
    large et ne commence pas forcement a zero.
    """
    debut, _ = grille_commune(temps_cible, temps_calcule)
    return debut + np.arange(nb_points) * pas_h


def _decalage_pas(qc, qs, masque=None, masque_cible=None):
    """
    Decalage, en pas, qui ALIGNE LE PIC de qs sur celui de qc.

    ANCRE SUR LE PIC, ET NON SUR UN MINIMUM D'ECART GLOBAL — meme critere que
    calage.decalage_minimisant_ecart, dont se sert la correction, et les deux
    doivent rester d'accord (cf. son docstring). Ni un ajustement par moindres
    carres sur la serie entiere, ni la correlation croisee, ne conviennent :
    la correlation croisee, mesuree sur une crue dont la fenetre coupe la
    decrue a 36 % du pic, rendait 0,00 h pour un retard reel de 1,6 h, et
    1,25 h pour 3,0 h — elle sous-estime des que l'evenement ne revient pas a
    sa ligne de base dans la fenetre, cas ordinaire d'un calage sur une
    fenetre courte. Un minimum d'ecart global peut, lui, se caler sur la queue
    de decrue plutot que sur l'evenement. Le pic, lui, reste identifiable
    meme quand la decrue est tronquee ou la forme diverge ailleurs : c'est ce
    qu'un operateur lit a l'oeil en comparant l'heure du pic obtenu a celle du
    pic cible.

    Rend 0 si l'une des deux series est plate — aucun pic n'y est
    identifiable — plutot que le bord du domaine de recherche : un decalage
    imaginaire ne ferait que brouiller le diagnostic.

    AUCUNE BORNE ARTIFICIELLE SUR L'AMPLITUDE (cf. calage.
    decalage_minimisant_ecart, meme choix, meme raison) : ramener le
    decalage a une fraction de la longueur de la serie fabriquait une valeur
    qui n'avait jamais ete la mesure reelle, et sur laquelle la correction
    etait pourtant construite. La mesure brute est rendue telle quelle, et
    aucun seuil ne la juge — voir Diagnostic.converge.

    masque : booleens sur la grille de qc/qs, CONTIGUS, restreignant la
    recherche du pic DANS LE CALCUL. C'est la fenetre du hydrogramme principal
    quand elle est connue.

    masque_cible : le meme, pour la CIBLE. None = le meme que « masque ».
    LES DEUX PEUVENT DIFFERER, et c'est le cas des que la fenetre est donnee
    en temps de SIMULATION : sur la base de temps de la cible, elle est
    decalee de Dt (voir recaler). Le decalage rendu est alors une difference
    d'indices ABSOLUS — l'origine de chaque masque est rajoutee a son argmax,
    ce qui exige des masques contigus (ils le sont : ce sont des intervalles).
      SANS LUI, LE PIC LE PLUS HAUT DE TOUTE LA SERIE GAGNE, ou qu'il soit.
      Mesure : un transitoire de demarrage place a 4 h, hors d'une fenetre
      jugee 18-40 h et plus haut que l'evenement, rendait -26,00 h pour un
      retard reel de +1,50 h. Le volume et la forme, eux, sont deja bornes a
      la fenetre — mais ils comparent la cible a « calcule(t + decalage) » :
      un decalage faux les emportait quand meme (109 % de volume, r = 0,962).
      Borner les trois grandeurs sans borner leur APPARIEMENT ne bornait rien.
    Ignore s'il retient moins de trois points : aucun pic n'y serait
    identifiable, et une fenetre de deux points n'est pas une fenetre.
    """
    qc = np.asarray(qc, dtype=float)
    qs = np.asarray(qs, dtype=float)
    if masque_cible is None:
        masque_cible = masque
    pris_s = masque is not None and int(np.count_nonzero(masque)) >= 3
    pris_c = (masque_cible is not None
              and int(np.count_nonzero(masque_cible)) >= 3)
    vs = qs[masque] if pris_s else qs
    vc = qc[masque_cible] if pris_c else qc
    if (float(np.ptp(vc)) <= 1e-9 * max(1.0, float(np.max(np.abs(vc))))
            or float(np.ptp(vs)) <= 1e-9 * max(1.0, float(np.max(np.abs(vs))))):
        return 0
    i_s = int(np.argmax(vs)) + (int(np.argmax(masque)) if pris_s else 0)
    i_c = int(np.argmax(vc)) + (int(np.argmax(masque_cible)) if pris_c else 0)
    return i_s - i_c


def recaler(temps_cible, debit_cible, temps_calcule, debit_calcule,
            pas_h=PAS_RECALAGE_H, fenetre=None, decalage_fenetre_h=None):
    """
    Recale temporellement l'hydrogramme calcule sur l'hydrogramme cible.

    Le decalage retenu est celui qui ALIGNE LE PIC des deux series (cf.
    _decalage_pas), et non celui qui minimise leur ecart global ou maximise
    leur correlation. Le decalage lui-meme n'est pas penalise : seule la
    forme et l'amplitude une fois recalees entrent dans le diagnostic.

    Les deux series sont rééchantillonnees sur une GRILLE COMMUNE. C'est
    indispensable : rééchantillonner chacune depuis sa propre origine
    annulerait le decalage entre les deux, et le decalage rapporte vaudrait
    toujours zero — ce qui priverait de tout effet le garde-fou temporel, dont
    c'est precisement le role de detecter un temps de propagation incoherent.
    En pratique, la serie extraite du modele demarre au debut de la simulation
    tandis que la cible demarre au debut de l'evenement : les origines
    different presque toujours.

    fenetre : (t0, tf) en heures — la fenetre du hydrogramme PRINCIPAL, quand
    elle est connue. Elle ne restreint QUE LA RECHERCHE DU PIC : le
    reechantillonnage reste sur la grille commune (sans quoi le decalage
    rapporte vaudrait toujours zero, cf. ci-dessus) et les series rendues
    couvrent toujours cette grille. Voir _decalage_pas pour ce qu'un pic
    parasite hors fenetre coutait.

    decalage_fenetre_h : le Dt auquel cette fenetre se rapporte, quand elle
    est donnee en temps de SIMULATION. La fenetre de calage.fenetre_injection
    l'est : elle est mesuree sur « cible(t - Dt) - section(t) », dont l'indice
    est un instant de simulation. Sur la base de temps de la CIBLE, la meme
    fenetre vaut donc « fenetre - Dt ». None (defaut) : 0,0 h, la fenetre est
    prise telle quelle des deux cotes.
      CE QUE SON ABSENCE COUTAIT : sur un cas reel du 08/09/2026, un Dt de
    +2,60 h sur une cible qui culmine a 0,50 h faisait tomber TOUT le pic de
    la cible hors d'une fenetre ouverte a 2,10 h. Le pic de la cible dans la
    fenetre valait alors 0,93 m3/s au lieu de 3,25, et un calage juste a 0,1 %
    pres etait annonce a 350 % de pointe et 370 % de volume.

    Retourne (cible_recalee, calcule_recale, decalage_h).
    Un decalage positif signifie que l'hydrogramme calcule est EN RETARD.
    """
    debut, fin = grille_commune(temps_cible, temps_calcule)
    _, qc = reechantillonner(temps_cible, debit_cible, pas_h, debut, fin)
    _, qs = reechantillonner(temps_calcule, debit_calcule, pas_h, debut, fin)

    n = max(len(qc), len(qs))
    qc = np.pad(qc, (0, n - len(qc)), mode="edge")
    qs = np.pad(qs, (0, n - len(qs)), mode="edge")

    masque = masque_cible = None
    if fenetre is not None:
        axe = debut + np.arange(n) * pas_h
        dec_f = float(decalage_fenetre_h or 0.0)
        masque = (axe >= float(fenetre[0])) & (axe <= float(fenetre[1]))
        masque_cible = ((axe >= float(fenetre[0]) - dec_f)
                        & (axe <= float(fenetre[1]) - dec_f))
    decalage_pas = _decalage_pas(qc, qs, masque, masque_cible)
    decalage_h = decalage_pas * pas_h

    # On aligne en tronquant la partie qui deborde, sans reboucler.
    if decalage_pas > 0:
        qs_a, qc_a = qs[decalage_pas:], qc[: n - decalage_pas]
    elif decalage_pas < 0:
        qs_a, qc_a = qs[: n + decalage_pas], qc[-decalage_pas:]
    else:
        qs_a, qc_a = qs, qc

    return qc_a, qs_a, decalage_h


# ---------------------------------------------------------------------------
# Critere de forme
# ---------------------------------------------------------------------------

def correlation(debit_cible, debit_calcule):
    """
    Correlation entre les deux series : l'accord sur la FORME.

    C'est la seule composante du Kling-Gupta Efficiency qui ait survecu. Le
    KGE agregeait r, alpha (rapport des ecarts-types, ~ pointe) et beta
    (rapport des moyennes, ~ volume) en un seul nombre ; or la concordance
    juge la pointe et le volume sur rapport_pic et rapport_volume, et un
    agregat cache lequel de ses termes derive. Calcules et stockes, le KGE,
    alpha et beta n'etaient lus nulle part — sauf beta, par une figure qui le
    tracait sous le nom du volume. Retires le 07/09/2026.

    NaN si l'une des series est constante : la correlation n'est alors pas
    definie, et la concordance echoue d'elle-meme (NaN >= r_min est faux).
    """
    c = np.asarray(debit_cible, dtype=float)
    s = np.asarray(debit_calcule, dtype=float)
    if c.std() == 0 or s.std() == 0:
        return float("nan")
    return float(np.corrcoef(c, s)[0, 1])


# ---------------------------------------------------------------------------
# Diagnostic complet d'un essai
# ---------------------------------------------------------------------------

@dataclass
class Diagnostic:
    """Resultat complet de la comparaison d'un essai avec sa cible."""
    r: float
    decalage_h: float
    rapport_pic: float
    rapport_volume: float
    # Tolerances du VERDICT, identiques a celles de la recherche. Elles y
    # figurent pour que « converge » se prononce sur les memes grandeurs que
    # l'arret : le verdict reposait sur le KGE alors que la recherche s'arretait
    # sur le volume, la pointe et la forme — une etude pouvait donc etre
    # declaree non conforme sur un critere que la boucle n'avait jamais cherche
    # a satisfaire.
    tolerance_volume: float = 0.05
    tolerance_pic: float = 0.02
    r_min: float = 0.97
    # TOUT ce qui merite d'etre signale au lecteur, y compris ce qui n'empeche
    # pas de conclure. Affiche tel quel dans la colonne « Alertes ».
    alertes: list = field(default_factory=list)
    # LE SOUS-ENSEMBLE QUI INVALIDE LA COMPARAISON ELLE-MEME, et lui seul
    # empeche « converge ». Voir la propriete ci-dessous pour la ligne de
    # partage.
    alertes_bloquantes: list = field(default_factory=list)
    # (t0, tf) en heures, sur la base de temps de la CIBLE : la fenetre du
    # hydrogramme PRINCIPAL effectivement jugee, si une a ete fournie a
    # diagnostiquer(). None = la comparaison a porte sur toute la fenetre
    # commune aux deux series (comportement d'avant l'introduction du
    # parametre). Conservee ici pour que le resume (et tout ce qui lit un
    # Diagnostic) puisse dire QUELLE periode a ete jugee.
    fenetre: tuple = None
    # CE QUE LE VERDICT NE VOIT PAS — mesure, jamais jugement.
    #
    # « rapport_volume » porte sur la seule fenetre jugee. La ou cette fenetre
    # coupe, le modele peut DEPASSER la cible sans que rien ne le dise :
    # fenetre_injection() ferme quand 99 % du DEFICIT est couvert, et un
    # excedent ne compte pas dans un deficit — il est donc exclu PAR
    # CONSTRUCTION, pas par accident de reglage. Mesure du 03/09/2026 sur un
    # modele reel, refaite le 04/09 sur un calage independant : 100,3 % sur la
    # fenetre 4,5-19,7 h, 111,7 % sur la serie entiere, 0,5 hm3 de trop dans
    # la decrue. Le cas est nomme dans STATUT.txt § 5, qui ne quitte pas le
    # depot ; ici, la chaine part dans une archive.
    #
    # « rapport_volume_serie » est le meme rapport pris sur toute la fenetre
    # commune aux deux series, et « part_cible_jugee » la part du volume de la
    # cible que la fenetre retient. Tous deux None quand aucune fenetre n'a
    # ete fournie : il n'y a alors rien qui reste dehors.
    #
    # CES DEUX NOMBRES NE SONT PAS DES CRITERES, et la reserve qui les porte
    # ENONCE UN PERIMETRE plutot qu'elle ne denonce un defaut : elle se leve
    # aussi bien quand la fenetre coupe dans la decrue que quand elle exclut,
    # a bon droit, une mini-crue anterieure. C'est assume — dans les deux cas
    # le verdict ignore un volume, et celui qui le lit doit savoir lequel.
    rapport_volume_serie: float = None
    part_cible_jugee: float = None
    # PART DE L'APPORT DANS LE DEBIT DE POINTE A SA SECTION —
    # (pic_cible - pic_residuel) / pic_cible — mesuree par caler() sur le
    # calcul de reference, le seul a connaitre le residuel, et repassee a la
    # verification finale. Une MESURE, jamais un critere : converge ne la lit
    # pas. Sous la tolerance de volume, elle fait lever la reserve « APPORT
    # PEU IDENTIFIABLE » (reserve_identifiabilite). None = inconnue.
    part_apport: float = None

    @property
    def converge(self):
        """
        L'essai est-il acceptable ? Les trois grandeurs cherchees sous leur
        tolerance, et aucune alerte BLOQUANTE.

        LA LIGNE DE PARTAGE ENTRE LES DEUX FAMILLES D'ALERTES. Une alerte
        bloque quand elle invalide la COMPARAISON : deux series qui ne se
        recouvrent pas, ou une simulation trop courte pour porter la cible,
        donnent des pourcentages justes sur des grandeurs qui ne se
        correspondent pas. Il n'y a alors rien a conclure.

        LE DECALAGE TEMPOREL N'EST PLUS JUGE DU TOUT, depuis le 08/08/2026 :
        il est MESURE, RAPPORTE, et c'est tout. Ni critere, ni alerte, ni
        seuil.

        Il n'invalide rien — recaler() le neutralise avant toute comparaison,
        et volume, pointe et forme portent bien sur les memes instants. La
        methode enonce d'ailleurs qu'elle ne le corrige pas (§ 1.5) : le
        compter comme un critere reviendrait a exiger ce qu'on a decide de ne
        pas chercher.

        SON HISTOIRE, PARCE QU'ELLE EXPLIQUE LE CHOIX. Un seuil
        « decalage_max_h » (3,0 h) levait une alerte au-dela. Bloquante
        jusqu'au 07/08/2026, elle rendait le resultat absurde sur un modele
        dont le calendrier differe de celui des cibles : tous les apports
        valides un par un, puis le calage entier declare non conforme sur un
        motif parlant d'une derive inexistante. Rendue non bloquante, elle
        restait fausse — le calage complet du 08/08 l'a levee sur SEPT
        sections sur sept, pour des decalages de 3,60 a 5,30 h parfaitement
        structurels (les deux calendriers n'ont pas la meme origine). Une
        alerte qui se declenche partout ne signale plus rien et apprend a
        l'ignorer.

        L'AMPLITUDE NE DISTINGUAIT PAS ce qu'il fallait distinguer : un temps
        de transfert reel d'un appariement de pics sans rapport. Les deux
        peuvent valoir 5 h. Ce qui les separe est la COHERENCE du decalage le
        long de l'axe, pas sa valeur — piste laissee a une v2, et deliberement
        pas remplacee par un seuil different qui aurait le meme defaut.

        Une forme non calculable (serie constante) ne bloque pas non plus :
        r vaut alors NaN et la concordance echoue d'elle-meme.
        """
        return (not self.alertes_bloquantes
                and abs(self.rapport_volume - 1.0) <= self.tolerance_volume
                and abs(self.rapport_pic - 1.0) <= self.tolerance_pic
                and self.r >= self.r_min)

    def resume(self):
        """
        Resume LU PAR L'UTILISATEUR — dans le suivi, la note de synthese et le
        journal. Il dit donc les trois grandeurs cherchees, en pourcentage
        d'atteinte de la cible, et non les symboles du KGE : « volume 99 % »
        se juge sans decodeur, « beta 0,993 » demande d'abord d'etre explique.

        La fenetre jugee est rappelee des qu'elle restreint la cible : sans
        elle, un pourcentage juste pourrait laisser croire qu'il porte sur
        toute la serie d'entree.
        """
        base = (
            f"pointe {100 * self.rapport_pic:5.1f} % | "
            f"volume {100 * self.rapport_volume:5.1f} % | "
            f"forme {100 * self.r:5.1f} % | "
            f"decalage {self.decalage_h:+.2f} h"
        )
        if self.fenetre is not None:
            base += f" | fenetre {self.fenetre[0]:.2f}-{self.fenetre[1]:.2f} h"
        return base


def reserve_identifiabilite(part_apport, tolerance_volume):
    """
    La reserve « APPORT PEU IDENTIFIABLE », ou None si l'apport pese assez.

    La chaine cale la SECTION sur sa cible ; l'apport retenu en est deduit.
    Quand l'apport ne pese presque rien devant le debit qui transite deja, la
    bande de tolerance admise a la section est AUSSI LARGE QUE L'APPORT
    LUI-MEME : une infinite d'apports tres differents y satisfont, et celui
    qui sort n'est plus une mesure. Ecart possible sur l'apport ~= tolerance
    de volume / part de l'apport dans le debit de pointe a la section.

    MESURE SUR UN CALAGE REEL (7 apports, 08/08/2026), face a un calcul
    manuel independant : six apports pesant 6 a 62 % du debit a leur section
    tombent a moins de 10 % du calcul manuel ; le septieme, qui n'en pese que
    2 %, s'en ecarte de 200 % sur la pointe — alors que sa section est a
    100,5 % de la cible.

    UNE RESERVE, PAS UN ARRET — decision du 07/09/2026. Caler la section
    reste legitime, c'est ce qu'on demande a la chaine ; publier l'apport
    comme une estimation hydrologique ne l'est pas. Le texte le DIT, sans
    juger : il n'entre jamais dans les alertes bloquantes et ne change aucun
    verdict. Jusque-la il n'existait qu'au journal texte, a l'iteration 0 ;
    porte par le Diagnostic, il atteint la colonne « Alertes » du classeur,
    la note de synthese et le suivi, par le chemin de la reserve de
    perimetre du volume.

    part_apport : (pic_cible - pic_residuel) / pic_cible, mesure par caler()
    sur le calcul de reference — le seul a connaitre le residuel. None quand
    elle n'est pas connue (appels anciens, reconstruction hors ligne) : pas
    de reserve, plutot qu'une reserve devinee. Le seuil est strict : a part
    egale a la tolerance, l'ecart possible vaut 100 %, et l'apport est encore
    identifiable au sens de la bande.
    """
    if part_apport is None or not (0.0 < part_apport < tolerance_volume):
        return None
    return (f"APPORT PEU IDENTIFIABLE : il ne pese que {100 * part_apport:.1f} % "
            f"du debit de pointe a la section, pour une tolerance de "
            f"{100 * tolerance_volume:.1f} % sur le volume. L'apport retenu "
            f"peut s'ecarter de l'ordre de "
            f"{100 * tolerance_volume / part_apport:.0f} % du veritable apport "
            f"sans que la section cesse d'etre conforme. Caler la section "
            f"reste legitime ; l'hydrogramme d'apport sorti n'est pas une "
            f"estimation hydrologique et ne doit pas etre exploite comme "
            f"telle. Pour l'identifier, il faudrait une section ou cet apport "
            f"pese davantage, ou une tolerance plus serree.")


@dataclass(frozen=True)
class _Comparaison:
    """
    Ce que diagnostiquer() compare : les deux series, le decalage qui les
    apparie, le pas, et la fenetre jugee dite dans les DEUX bases de temps.

    Etabli une fois, en tete de diagnostiquer(), puis LU par chacune des
    grandeurs du verdict — forme, pointes, volumes, couverture. Aucune ne le
    modifie (il est fige), et ce qu'elles calculent est rendu, pas range ici.

    POURQUOI UN OBJET PLUTOT QUE DIX ARGUMENTS. f0/f1 et f0c/f1c designent
    la MEME fenetre sur deux bases de temps, et les confondre est le defaut
    du 08/09/2026 (voir diagnostiquer, « decalage_fenetre_h ») : une section
    juste a 0,1 % pres annoncee a 350 %. Passes un a un a cinq fonctions, ces
    quatre flottants s'echangeraient a l'appel sans que rien ne le dise ; lus
    ici par leur nom, ils ne le peuvent pas.
    """
    temps_cible: object
    debit_cible: object
    temps_calcule: object
    debit_calcule: object
    tc: object                  # temps_cible, en tableau de flottants
    ts: object                  # temps_calcule, de meme
    pas_h: float
    decalage_h: float           # mesure par recaler() ; positif = calcul en retard
    fenetre: object = None      # telle que recue ; None = pas de fenetre
    f0: float = None            # la fenetre en temps de SIMULATION : la ou
    f1: float = None            # se lit le calcul
    f0c: float = None           # la meme sur la base de temps de la CIBLE
    f1c: float = None           # (f0 - Dt de fenetre, f1 - Dt de fenetre)



def diagnostiquer(temps_cible, debit_cible, temps_calcule, debit_calcule,
                  pas_h=PAS_RECALAGE_H,
                  couverture_min=0.9, tolerance_volume=0.05,
                  tolerance_pic=0.02, r_min=0.97, fenetre=None,
                  part_apport=None, decalage_fenetre_h=None):
    """
    Compare un hydrogramme calcule a sa cible et retourne un Diagnostic complet.

    tolerance_volume / tolerance_pic / r_min : ce que « converge » exigera.
    Ce sont les MEMES grandeurs et les memes seuils que ceux sur lesquels la
    recherche s'arrete — les separer avait laisse le verdict de l'etude
    dependre du KGE, que la recherche ne cherchait plus a satisfaire.

    Du KGE ne reste que r, le critere de forme. Le KGE agrege, alpha et beta
    ont ete retires le 07/09/2026 : calcules et stockes, ils n'etaient lus
    nulle part — sauf beta, par une figure qui le tracait sous le nom du
    volume (voir criteres.correlation).

    LE DECALAGE EST RAPPORTE, JAMAIS JUGE. Diagnostic.decalage_h porte la
    mesure, resume() l'affiche, le classeur et la note de synthese la
    reprennent — et rien n'en tire de verdict. Un seuil « decalage_max_h »
    a existe jusqu'au 08/08/2026 : voir Diagnostic.converge pour ce qu'il
    coutait et pourquoi il a ete retire.

    couverture_min : fraction de la duree de la cible que la fenetre de calcul
    doit couvrir. En dessous, une alerte est levee : un hydrogramme tronque
    prive le calage d'une partie du volume, qu'il chercherait alors a
    compenser en surdimensionnant l'apport.

    fenetre : (t0, tf) en heures — le hydrogramme PRINCIPAL a juger
    (typiquement calage.fenetre_injection, detectee sur l'ecart au residuel).
    None (par defaut) : comportement d'avant ce parametre, la comparaison
    porte sur toute la fenetre commune aux deux series.

    decalage_fenetre_h : LA BASE DE TEMPS DANS LAQUELLE « fenetre » EST DITE.
    calage.fenetre_injection mesure la fenetre sur « cible(t - Dt) -
    section(t) » : ses bornes sont des instants de SIMULATION. Sur la base de
    temps de la cible, la meme fenetre vaut « fenetre - Dt ». Ce parametre
    porte ce Dt — celui que la CORRECTION emploie, fige une fois par apport.
    None (defaut) : 0,0 h, les deux bases sont confondues, comportement
    d'avant ce parametre.
      LE PIC, LE VOLUME, LA FORME, LA COUVERTURE ET LA RECHERCHE DU PIC
    lisent donc la cible sur « fenetre - Dt » et le calcul sur « fenetre ».
    Les confondre coutait, sur un cas reel du 08/09/2026 (Dt = +2,60 h, cible
    culminant a 0,50 h, fenetre ouverte a 2,10 h), un verdict de 350 % de
    pointe et 370 % de volume sur un calage juste a 0,1 % pres — et un arret
    sur « le modele repond de facon trop non lineaire » apres trois essais.

    LE PIC, LE VOLUME, LA COUVERTURE, LA FORME ET LA MESURE DU DECALAGE SONT
    TOUS RESTREINTS A CETTE FENETRE quand elle est fournie. Le decalage en
    fait partie parce qu'il APPARIE les deux series avant toute comparaison :
    borner les grandeurs sans borner l'appariement ne bornait rien (voir
    _decalage_pas). Une mini-crue isolee dans la serie
    d'entree, avant ou apres l'evenement cale, ne doit peser ni sur le pic
    (un maximum pris hors de l'evenement jugerait un debit qui n'est pas
    celui qu'on cale), ni sur le volume, ni sur l'alerte de couverture (dont
    la reference — la duree de « la cible » — redevient la duree de
    l'evenement, et non celle de toute la donnee d'entree fournie).

    ET CE QUI RESTE DEHORS EST MESURE, SANS ETRE JUGE. Le Diagnostic porte
    alors « rapport_volume_serie » (le meme rapport de volume, pris sur toute
    la fenetre commune) et « part_cible_jugee » (la part du volume de la cible
    que la fenetre retient). Une reserve NON bloquante se leve quand ces deux
    lectures ne disent pas la meme chose : verdict dans la bande, serie
    dehors. Voir les champs eux-memes pour ce qui rend ce cas structurel, et
    pourquoi la boucle ne peut pas s'en saisir.

    part_apport : part de l'apport dans le debit de pointe a sa section,
    mesuree par caler() a l'iteration 0. Sous tolerance_volume, la reserve
    NON bloquante « APPORT PEU IDENTIFIABLE » est ajoutee aux alertes (voir
    reserve_identifiabilite) — a chaque essai, donc aussi sur celui que le
    retour au meilleur essai remet en place, et a la verification finale, ou
    diagnostics_finaux sont recalcules et l'auraient perdue sinon. Elle se
    leve aussi sur un apport NON VALIDE : l'enonce reste vrai, et c'est ce
    que caler() annoncait deja avant tout essai. None : pas de reserve.
    """
    _refuser_series_inexploitables(temps_cible, debit_cible, temps_calcule,
                                   debit_calcule, pas_h)
    dec_f = float(decalage_fenetre_h or 0.0)
    c_a, s_a, decalage_h = recaler(
        temps_cible, debit_cible, temps_calcule, debit_calcule, pas_h,
        fenetre=fenetre, decalage_fenetre_h=dec_f
    )

    tc = np.asarray(temps_cible, dtype=float)
    ts = np.asarray(temps_calcule, dtype=float)
    f0 = f1 = f0c = f1c = None
    if fenetre is not None:
        f0, f1 = float(fenetre[0]), float(fenetre[1])
        # LA MEME FENETRE, SUR LA BASE DE TEMPS DE LA CIBLE. Tout ce qui lit
        # la cible passe par f0c/f1c ; tout ce qui lit le calcul, par f0/f1.
        f0c, f1c = f0 - dec_f, f1 - dec_f
    comparaison = _Comparaison(
        temps_cible, debit_cible, temps_calcule, debit_calcule, tc, ts,
        pas_h, decalage_h, fenetre, f0, f1, f0c, f1c)

    r, pic_cible, pic_calcule = _forme_et_pointes(comparaison, c_a, s_a)

    debut, fin, vol_cible, rapport_vol, decalage_hors_fenetre = _volume_juge(
        comparaison)

    rapport_volume_serie, part_cible_jugee = _volume_de_la_serie(
        comparaison, vol_cible)

    # DEUX FAMILLES — voir Diagnostic.converge pour la ligne de partage.
    # « alertes » porte tout ce qui est signale ; « bloquantes » le seul
    # sous-ensemble qui invalide la comparaison.
    alertes, bloquantes = [], []
    if decalage_hors_fenetre:
        # DANS « bloquantes » SEULEMENT : elles rejoignent « alertes » en fin
        # de fonction. L'ajouter aussi a « alertes » la faisait figurer DEUX
        # fois dans tout ce qui les affiche (corrige le 11/11/2026).
        bloquantes.append(decalage_hors_fenetre)
    if not np.isfinite(r):
        alertes.append(_motif_forme_non_calculable(debit_cible, debit_calcule))

    _juger_couverture(comparaison, debut, fin, couverture_min,
                      alertes, bloquantes)

    _dire_perimetre(comparaison, rapport_vol, rapport_volume_serie,
                    part_cible_jugee, tolerance_volume, alertes)
    # L'APPORT EST-IL IDENTIFIABLE ? NON BLOQUANTE, meme famille que PERIMETRE
    # DU VERDICT : elle dit le perimetre de ce qui est publie, elle ne denonce
    # rien. Avant les bloquantes, pour que celles-ci restent en queue.
    _reserve = reserve_identifiabilite(part_apport, tolerance_volume)
    if _reserve:
        alertes.append(_reserve)
    alertes.extend(bloquantes)

    return Diagnostic(
        r=r, decalage_h=decalage_h,
        rapport_pic=pic_calcule / pic_cible if pic_cible else float("nan"),
        rapport_volume=rapport_vol,
        alertes=alertes, alertes_bloquantes=bloquantes,
        tolerance_volume=tolerance_volume, tolerance_pic=tolerance_pic,
        r_min=r_min, fenetre=fenetre,
        rapport_volume_serie=rapport_volume_serie,
        part_cible_jugee=part_cible_jugee,
        part_apport=part_apport,
    )


def _refuser_series_inexploitables(temps_cible, debit_cible, temps_calcule,
                                   debit_calcule, pas_h):
    """
    Leve ValueError, par une phrase, sur ce qui ne peut pas etre compare : une
    serie vide, des instants et des debits en nombres differents, un pas de
    recalage qui n'est pas strictement positif.

    Ces entrees levaient deja (11/11/2026) — mais IndexError, ou une erreur
    de numpy sans rapport avec la cause (« Maximum allowed size exceeded »
    pour un pas nul). Rien n'est juge ici : une serie mal formee n'est pas un
    calage qui ne converge pas, c'est une donnee a corriger.
    """
    for nom, temps, debits in (("la cible", temps_cible, debit_cible),
                               ("le calcul", temps_calcule, debit_calcule)):
        nb_temps, nb_debits = np.size(temps), np.size(debits)
        if nb_temps == 0 or nb_debits == 0:
            raise ValueError(f"serie vide pour {nom} : rien a comparer.")
        if nb_temps != nb_debits:
            raise ValueError(
                f"{nb_temps} instant(s) pour {nb_debits} debit(s) dans "
                f"{nom} : les deux colonnes doivent avoir la meme longueur.")
    if not (np.isfinite(pas_h) and pas_h > 0):
        raise ValueError(
            f"pas de recalage {pas_h!r} : un pas strictement positif, en "
            f"heures, est attendu.")


def _motif_forme_non_calculable(debit_cible, debit_calcule):
    """
    Pourquoi r n'est pas calculable. Une serie CONSTANTE n'a pas de forme ;
    une serie qui porte des VALEURS MANQUANTES non plus, mais ce n'est pas la
    meme panne — un calcul HEC-RAS qui diverge rend des NaN, et l'annoncer
    « serie constante » envoyait chercher ailleurs (11/11/2026).
    """
    trouees = [nom for nom, debits in (("la cible", debit_cible),
                                       ("le calcul", debit_calcule))
               if np.isnan(np.asarray(debits, dtype=float)).any()]
    if trouees:
        return ("forme non calculable (valeurs manquantes dans "
                + " et dans ".join(trouees) + ")")
    return "forme non calculable (serie constante)"


def _axe_non_croissant(comparaison):
    """« de la cible », « du calcul », ou None : la serie dont l'axe des
    temps n'est pas strictement croissant, s'il y en a une."""
    for nom, temps in (("de la cible", comparaison.tc),
                       ("du calcul", comparaison.ts)):
        if temps.size > 1 and not np.all(np.diff(temps) > 0):
            return nom
    return None


def _forme_et_pointes(comparaison, c_a, s_a):
    """
    La FORME (r) et les deux POINTES — sur la fenetre jugee quand il y en a
    une, sur les series entieres sinon.

    c_a, s_a : les series recalees sur toute la grille commune, telles que
    recaler() les rend. Elles ne servent que sans fenetre.

    Rend (r, pic_cible, pic_calcule).
    """
    fenetre, pas_h, decalage_h = (comparaison.fenetre, comparaison.pas_h,
                                  comparaison.decalage_h)
    tc, ts = comparaison.tc, comparaison.ts
    debit_cible, debit_calcule = (comparaison.debit_cible,
                                  comparaison.debit_calcule)
    f0, f1, f0c, f1c = (comparaison.f0, comparaison.f1,
                        comparaison.f0c, comparaison.f1c)
    if fenetre is not None:
        # LA FORME EST JUGEE SUR LA MEME FENETRE QUE LA POINTE ET LE VOLUME,
        # PAS SUR c_a/s_a — qui portent toute la grille commune aux deux
        # series. Sans cette restriction, une mini-crue isolee hors de
        # l'evenement cale (avant ou apres) degradait r sans le
        # moindre rapport avec l'apport qu'on cherche a caler : le § 7 de
        # l'auto-test verifiait deja que le pic et le volume l'ignoraient,
        # jamais que la forme le faisait.
        #
        # Meme decalage que pour le pic et le volume : cible(t) pour
        # t dans [f0, f1] comparee a calcule(t + decalage_h), soit
        # exactement l'appariement que recaler() etablit ailleurs.
        grille_f = np.arange(f0c, f1c + pas_h / 2, pas_h)
        cible_f = np.interp(grille_f, tc,
                            np.asarray(debit_cible, dtype=float))
        calc_f = np.interp(grille_f + decalage_h, ts,
                           np.asarray(debit_calcule, dtype=float))
        # np.interp PROLONGE par la valeur de bord hors du domaine calcule :
        # comme pour calcul_rephase() ailleurs, on exclut ces points plutot
        # que de les laisser fausser la correlation avec un plateau fictif.
        dedans_f = ((grille_f + decalage_h >= ts[0])
                   & (grille_f + decalage_h <= ts[-1])
                   & (grille_f >= tc[0]) & (grille_f <= tc[-1]))
        if dedans_f.sum() >= 2:
            cible_f, calc_f = cible_f[dedans_f], calc_f[dedans_f]
        r = correlation(cible_f, calc_f)

        dans_c = (tc >= f0c) & (tc <= f1c)
        dans_s = (ts >= f0) & (ts <= f1)
        pic_cible = (float(np.max(np.asarray(debit_cible, dtype=float)[dans_c]))
                    if dans_c.any() else float(np.max(debit_cible)))
        pic_calcule = (float(np.max(np.asarray(debit_calcule, dtype=float)[dans_s]))
                      if dans_s.any() else float(np.max(debit_calcule)))
    else:
        r = correlation(c_a, s_a)
        pic_cible = float(np.max(debit_cible))
        pic_calcule = float(np.max(debit_calcule))
    return r, pic_cible, pic_calcule


def _volume_juge(comparaison):
    """
    Le rapport de VOLUME du verdict, et l'intervalle sur lequel il est pris.

    Rend (debut, fin, vol_cible, rapport_vol, decalage_hors_fenetre) :
      - [debut, fin] : l'intervalle juge, sur la base de temps de la cible —
        la fenetre, retrecie a ce que les deux series couvrent une fois
        appariees ; (nan, nan) quand il n'en reste rien. C'est aussi sur lui
        que se juge la COUVERTURE ;
      - vol_cible : le volume de la cible qui y a ete integre ;
      - rapport_vol : calcule / cible, nan si rien n'est comparable ;
      - decalage_hors_fenetre : le texte de la bloquante, quand le decalage
        excede l'intervalle juge et que les volumes ont du etre repris sur
        toute la fenetre commune ; None sinon.
    """
    temps_cible, debit_cible = comparaison.temps_cible, comparaison.debit_cible
    temps_calcule, debit_calcule = (comparaison.temps_calcule,
                                    comparaison.debit_calcule)
    tc, ts = comparaison.tc, comparaison.ts
    fenetre, pas_h, decalage_h = (comparaison.fenetre, comparaison.pas_h,
                                  comparaison.decalage_h)
    f0c, f1c = comparaison.f0c, comparaison.f1c
    # Volumes compares sur la fenetre ou les deux series existent, jamais
    # chacun sur sa propre etendue — ET APRES NEUTRALISATION DU DECALAGE.
    #
    # Sans cette neutralisation, un temps de propagation coute du volume au
    # seul calcul des lors que la fenetre se ferme sur un debit encore fort :
    # mesure, 1,6 h de retard sur une crue dont la fenetre coupe la decrue a
    # 36 % du pic amputent le volume de 3,7 %. Or la correction, elle, est
    # calculee APRES recalage et ne voit alors rien a injecter. Le calage se
    # trouvait ainsi somme de combler un deficit que sa propre methode lui
    # interdit de corriger : il stagnait, sans levier.
    #
    # On compare donc les deux series sur la meme DUREE, chacune decalee de sa
    # part : c'est la meme regle que pour la forme, ou r est evalue apres
    # recalage. La dynamique est exclue partout, ou nulle part.
    debut, fin = fenetre_commune(temps_cible, temps_calcule)
    avance, retard = max(decalage_h, 0.0), min(decalage_h, 0.0)
    # OU CHAQUE SERIE EST LUE, par rapport a [debut, fin] : le calcul sur
    # [debut + ds0, fin + ds1], la cible sur [debut + dc0, fin + dc1]. Sans
    # fenetre, [debut, fin] est l'etendue brute commune aux deux axes, et
    # chaque serie cede |Dt| d'un cote pour que cible(t) et calcule(t + Dt)
    # y tiennent toutes deux, sur la meme duree.
    ds0, ds1, dc0, dc1 = avance, retard, -retard, -avance
    if fenetre is not None and np.isfinite(debut):
        # La fenetre du hydrogramme principal ne peut que RETRECIR la
        # comparaison, jamais l'elargir au-dela de ce que les deux series
        # couvrent reellement.
        #
        # SUR LA BASE DE TEMPS DE LA CIBLE, ET DECALEE DE Dt POUR LE CALCUL.
        # La cible doit exister sur [f0c, f1c], le calcul sur
        # [f0c + Dt, f1c + Dt] = [f0, f1] : c'est cela qui borne la fenetre
        # jugee, pas l'etendue brute des deux axes.
        #   RETRECIR SUR L'ETENDUE BRUTE PUIS RETIRER ENCORE |Dt| D'UN COTE
        # (le schema sans fenetre) comptait Dt DEUX FOIS. Mesure du
        # 22/09/2026 sur onze apports reels : calcul en avance de 4,6 a 11 h
        # sur des cibles de 80 h, simulation de 20,5 h qui couvrait toute la
        # fenetre jugee — « ne couvre que 45 a 90 % », onze sections NON
        # CONFORMES a 100 % de volume, et un « decalage qui excede la fenetre
        # jugee » de 9,5 h pour une fenetre de 21 h.
        debut = max(f0c, float(tc[0]), float(ts[0]) - decalage_h)
        fin = min(f1c, float(tc[-1]), float(ts[-1]) - decalage_h)
        if not fin > debut:
            debut = fin = float("nan")
        ds0, ds1, dc0, dc1 = decalage_h, decalage_h, 0.0, 0.0

    # BORNES PROPRES AU VOLUME. « debut/fin » servent aussi a juger la
    # COUVERTURE plus bas, ou ils doivent rester ceux de la fenetre : les
    # elargir la-bas ferait passer pour couverte une simulation qui ne l'est
    # pas. Le repli ci-dessous ne touche donc que la mesure des volumes.
    debut_v, fin_v = debut, fin
    decalage_hors_fenetre = None
    if np.isfinite(debut) and abs(decalage_h) >= fin - debut:
        # LE DECALAGE EXCEDE LA FENETRE JUGEE — il ne reste, apres recalage,
        # aucun intervalle commun aux deux series. Rendre « nan » ici etait
        # exact mais muet : caler() n'y lisait qu'un volume non calculable et
        # concluait « le modele ne repond plus a cet apport », ce qui designe
        # l'hydraulique alors que la cause est la MESURE DU DECALAGE.
        #
        # On rend donc la comparaison des volumes a la fenetre commune
        # ENTIERE — meme regle que fenetre_injection() sur un ecart nul :
        # mieux vaut ne rien restreindre que restreindre au hasard — et on le
        # DIT.
        #
        # ET C'EST BLOQUANT DEPUIS LE 09/09/2026. L'alerte etait signalee sans
        # l'etre : le calage acceptait un apport apparie sur un decalage plus
        # long que l'evenement lui-meme. Ce n'est pas juger le decalage — la
        # regle « mesure, rapporte, jamais juge » tient — c'est constater que
        # LA COMPARAISON N'A PLUS D'OBJET, ce qui est la definition meme
        # d'alertes_bloquantes : les pourcentages seraient justes sur des
        # grandeurs qui ne se correspondent pas.
        #   CE QUI AVAIT FAIT CHOISIR « NON BLOQUANT » RESTE SATISFAIT :
        # l'objection portait sur un « nan » MUET, ou caler() lisait un volume
        # non calculable et concluait « le modele ne repond plus a cet
        # apport » — l'hydraulique accusee a la place de la mesure du
        # decalage. Le motif nomme desormais la cause, et le volume reste
        # calcule : on refuse EN DISANT POURQUOI.
        #   POURQUOI MAINTENANT : jusqu'au correctif de la fenetre
        # (09/09/2026), ce cas etait refuse PAR ACCIDENT — diagnostiquer()
        # lisait la cible sur un intervalle decale de Dt, donc hors de son
        # evenement, et rendait des pourcentages absurdes qui faisaient
        # echouer l'apport. La fenetre reparee, l'appariement devient
        # coherent et le verdict passait a « conforme » sur un apport cale
        # onze heures trop tot. Le garde-fou est donc pose la ou il aurait
        # toujours du etre.
        #
        # UN DECALAGE PLUS LONG QUE L'EVENEMENT QU'IL DECALE N'EST PAS UN
        # TEMPS DE TRANSFERT. Revele le 31/08/2026 en resserrant la borne
        # haute de fenetre_injection() : le defaut preexistait, une fenetre
        # qui courait jusqu'au bout de la serie le masquait.
        decalage_hors_fenetre = (
            f"le decalage mesure ({decalage_h:+.2f} h) excede la fenetre "
            f"jugee ({fin - debut:.2f} h) : les volumes sont compares sur "
            f"toute la fenetre commune, pas sur l'evenement. Un decalage "
            f"plus long que l'evenement qu'il decale n'est pas un temps de "
            f"transfert - relire les cibles et leur base de temps")
        debut_v, fin_v = fenetre_commune(temps_cible, temps_calcule)
        # Etendue brute : chaque serie cede de nouveau |Dt| d'un cote.
        ds0, ds1, dc0, dc1 = avance, retard, -retard, -avance

    if np.isfinite(debut_v) and (fin_v + ds1) - (debut_v + ds0) <= 0:
        # Meme apres elargissement, rien de comparable : la, c'est franc.
        vol_cible = vol_calcule = float("nan")
    else:
        vol_calcule = volume(temps_calcule, debit_calcule,
                             debut_v + ds0, fin_v + ds1, pas_h)
        vol_cible = volume(temps_cible, debit_cible,
                           debut_v + dc0, fin_v + dc1, pas_h)
    rapport_vol = (vol_calcule / vol_cible if vol_cible else float("nan"))
    return debut, fin, vol_cible, rapport_vol, decalage_hors_fenetre


def _volume_de_la_serie(comparaison, vol_cible):
    """
    Ce que la fenetre jugee laisse dehors : le rapport de volume pris sur
    TOUTE la fenetre commune aux deux series, et la part du volume de la
    cible que la fenetre retient. Mesures, jamais verdict.

    vol_cible : le volume de la cible sur la fenetre jugee, tel que
    _volume_juge() l'a integre.

    Rend (rapport_volume_serie, part_cible_jugee) — (None, None) sans
    fenetre, ou quand rien n'est mesurable.
    """
    temps_cible, debit_cible = comparaison.temps_cible, comparaison.debit_cible
    temps_calcule, debit_calcule = (comparaison.temps_calcule,
                                    comparaison.debit_calcule)
    fenetre, pas_h, decalage_h = (comparaison.fenetre, comparaison.pas_h,
                                  comparaison.decalage_h)
    # La part que chaque serie cede, comme dans _volume_juge().
    avance, retard = max(decalage_h, 0.0), min(decalage_h, 0.0)
    # CE QUE LA FENETRE LAISSE DEHORS — MESURE, PAS VERDICT.
    #
    # Le meme rapport de volume, pris sur toute la fenetre commune aux deux
    # series : c'est la grandeur que le verdict n'a PAS regardee. Elle se
    # calcule exactement comme celle du verdict — memes bornes decalees de la
    # meme part — pour que les deux soient comparables ligne a ligne.
    #
    # ON NE JUGE PAS SUR ELLE, et ce n'est pas une prudence de facade : un
    # apport ne sait qu'AJOUTER du debit. La ou le modele depasse deja la
    # cible, aucune valeur d'apport ne le corrige — juger sur ce nombre
    # poserait une cible impossible par construction, que la boucle epuiserait
    # en essais sans que rien ne dise pourquoi (invariant 11).
    rapport_volume_serie = part_cible_jugee = None
    if fenetre is not None and np.isfinite(vol_cible):
        debut_s, fin_s = fenetre_commune(temps_cible, temps_calcule)
        if (np.isfinite(debut_s)
                and (fin_s + retard) - (debut_s + avance) > 0):
            vol_calcule_s = volume(temps_calcule, debit_calcule,
                                   debut_s + avance, fin_s + retard, pas_h)
            vol_cible_s = volume(temps_cible, debit_cible,
                                 debut_s - retard, fin_s - avance, pas_h)
            if vol_cible_s:
                rapport_volume_serie = vol_calcule_s / vol_cible_s
                part_cible_jugee = vol_cible / vol_cible_s
    return rapport_volume_serie, part_cible_jugee


def _juger_couverture(comparaison, debut, fin, couverture_min,
                      alertes, bloquantes):
    """
    La simulation couvre-t-elle l'evenement juge ? Ajoute ce qu'il y a a en
    dire : a « bloquantes » quand les series ne se recouvrent pas ou que la
    couverture tombe sous couverture_min, a « alertes » quand il en manque
    un peu — ce que le rapport de volume ne peut pas reveler.

    [debut, fin] : l'intervalle juge, tel que _volume_juge() le rend.
    """
    fenetre, tc = comparaison.fenetre, comparaison.tc
    f0c, f1c = comparaison.f0c, comparaison.f1c
    # Une fenetre de simulation qui ne couvre pas tout l'hydrogramme cible est
    # une erreur de configuration courante et couteuse : le volume manquant
    # est attribue a tort a un defaut d'apport, et le calage cherche a le
    # compenser en surdimensionnant l'injection.
    #
    # LA REFERENCE EST LA DUREE DE L'EVENEMENT, PAS CELLE DE LA DONNEE
    # D'ENTREE : une cible peut porter, avant ou apres l'evenement cale, une
    # periode qui ne le concerne pas (mini-crue anterieure, bruit de fin de
    # serie). La juger sur la duree totale de l'entree ferait passer pour une
    # simulation tronquee ce qui n'est que la fenetre voulue.
    # LA PART DE LA FENETRE QUE LA CIBLE PORTE REELLEMENT, et non sa
    # longueur nominale. Des que la fenetre est decalee sur la base de temps
    # de la cible (dec_f non nul), ses bords peuvent tomber hors de la donnee
    # d'entree — c'est alors la MARGE de fenetre_injection qui deborde, pas
    # l'evenement. Une marge existe pour etre rognee : la compter comme non
    # simulee levait une alerte sur une perte sans consequence, et un
    # garde-fou qui se declenche pour rien apprend a etre ignore.
    duree_cible = ((min(f1c, float(tc[-1])) - max(f0c, float(tc[0])))
                   if fenetre is not None else float(tc[-1] - tc[0]))
    desordre = _axe_non_croissant(comparaison)
    if desordre:
        # UN AXE DES TEMPS QUI RECULE, pas des fenetres disjointes : la meme
        # impossibilite de comparer, mais pas la meme chose a corriger. Il
        # passait pour « ne se recouvrent pas — verifier la date de debut »
        # (11/11/2026).
        bloquantes.append(
            f"l'axe des temps {desordre} n'est pas strictement croissant : "
            f"les series ne peuvent pas etre comparees - relire la colonne "
            f"des temps, ses lignes sont dans le desordre ou en double")
    elif not np.isfinite(debut):
        bloquantes.append(
            "les fenetres de temps de la cible et du calcul ne se recouvrent "
            "pas - verifier la date de debut de la simulation")
    elif duree_cible > 0 and (fin - debut) < couverture_min * duree_cible:
        bloquantes.append(
            f"la fenetre de calcul ne couvre que "
            f"{100 * (fin - debut) / duree_cible:.0f} % de la duree de "
            f"l'hydrogramme cible - allonger la simulation, sinon le volume "
            f"manquant sera attribue a tort a un defaut d'apport")
    elif duree_cible > 0 and (fin - debut) < duree_cible - 1e-9:
        # L'ANGLE MORT DE couverture_min, ET IL EST AVEUGLE PAR CONSTRUCTION.
        #
        # Entre 90 et 100 % de couverture, la bloquante ci-dessus se taisait
        # et RIEN D'AUTRE NE POUVAIT LE DIRE : les volumes sont integres sur
        # le MEME intervalle rogne pour la cible et pour le calcul (voir
        # debut_v / fin_v plus haut), donc leur rapport reste a 100 % alors
        # qu'une part de l'evenement juge n'a jamais ete simulee. Mesure du
        # 31/08/2026 : fenetre jugee 2-35 h, calcul arrete a 34 h — 97 % de
        # couverture, volume 100,0 %, aucune alerte.
        #
        # NON BLOQUANTE, A DESSEIN : ce qui manque est la queue de
        # l'evenement, dont le poids en volume est justement inferieur a la
        # tolerance — le verdict garde son sens. Mais il porte sur un
        # evenement incomplet, et celui qui lit le rapport doit le savoir.
        # Le seuil bloquant reste a couverture_min.
        alertes.append(
            f"{duree_cible - (fin - debut):.1f} h de la fenetre jugee ne sont "
            f"pas simulees ({100 * (fin - debut) / duree_cible:.0f} % de "
            f"couverture) : le verdict porte sur un evenement incomplet. Le "
            f"rapport de volume ne peut PAS le reveler, cible et calcul etant "
            f"integres sur le meme intervalle rogne")


def _dire_perimetre(comparaison, rapport_vol, rapport_volume_serie,
                    part_cible_jugee, tolerance_volume, alertes):
    """
    Ajoute a « alertes » la reserve PERIMETRE DU VERDICT, quand le volume
    juge tient dans la bande et que la serie entiere en sort. Jamais
    bloquante.
    """
    f0, f1 = comparaison.f0, comparaison.f1
    # LE VERDICT DE VOLUME TIENT, ET LA SERIE ENTIERE LE DEMENT.
    #
    # ELLE ENONCE UN PERIMETRE, ELLE NE DENONCE PAS UN DEFAUT — et c'est ce
    # qui regle le seul cas ou l'on pourrait la croire abusive : celui d'une
    # mini-crue anterieure que la fenetre exclut A BON DROIT (§ 7 du banc).
    # La distinguer d'une fenetre qui coupe dans la decrue (§ 7 ter) demande
    # un seuil d'amplitude que personne n'a mesure — le signe de l'ecart n'y
    # suffit pas, verifie : dans les deux cas l'excedent touche le bord de la
    # fenetre. Or l'enonce reste VRAI et utile dans les deux : au § 7 le
    # modele double la mini-crue, et le verdict ne le voit pas davantage.
    #
    # ELLE NE SE LEVE PAS QUAND LE VERDICT EST DEJA HORS BANDE : il le dit
    # alors lui-meme et la boucle travaille dessus ; ajouter un second
    # pourcentage a chaque essai n'apprendrait rien et apprendrait a ignorer
    # la colonne « Alertes ». Le NOMBRE, lui, est porte par le Diagnostic dans
    # tous les cas.
    #
    # NON BLOQUANTE, comme celle de la couverture : ce qu'elle signale n'est
    # pas une comparaison invalide, c'est une comparaison dont il faut
    # connaitre le perimetre.
    if (rapport_volume_serie is not None and part_cible_jugee is not None
            and np.isfinite(rapport_vol) and np.isfinite(rapport_volume_serie)
            and abs(rapport_vol - 1.0) <= tolerance_volume
            and abs(rapport_volume_serie - 1.0) > tolerance_volume):
        alertes.append(
            f"PERIMETRE DU VERDICT : le volume est juge sur la fenetre "
            f"{f0:.1f}-{f1:.1f} h, qui retient "
            f"{100 * part_cible_jugee:.0f} % du volume de la cible. Sur "
            f"toute la serie le rapport vaut "
            f"{100 * rapport_volume_serie:.1f} %, hors de la bande "
            f"+/-{100 * tolerance_volume:.0f} %. Ce qui est dehors n'est pas "
            f"juge, et ne peut pas l'etre ici : un apport ne sait qu'ajouter "
            f"du debit, un excedent hors fenetre se corrige en amont")


# ---------------------------------------------------------------------------
# Auto-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Le banc vit dans src/bancs/ depuis le 10/11/2026 : l'archive du plugin
    # ne l'embarque pas. Dans le depot, ce relais le joue a l'identique.
    import runpy
    import sys
    from pathlib import Path

    _banc = (Path(__file__).resolve().parent / "bancs"
             / "banc_criteres.py")
    if not _banc.is_file():
        print("Le banc d'auto-test n'est pas livre avec cette installation.",
              file=sys.stderr)
        raise SystemExit(2)
    runpy.run_path(str(_banc), run_name="__main__")
