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


def _decalage_pas(qc, qs):
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
    """
    qc = np.asarray(qc, dtype=float)
    qs = np.asarray(qs, dtype=float)
    if (float(np.ptp(qc)) <= 1e-9 * max(1.0, float(np.max(np.abs(qc))))
            or float(np.ptp(qs)) <= 1e-9 * max(1.0, float(np.max(np.abs(qs))))):
        return 0
    return int(np.argmax(qs)) - int(np.argmax(qc))


def recaler(temps_cible, debit_cible, temps_calcule, debit_calcule,
            pas_h=PAS_RECALAGE_H):
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

    Retourne (cible_recalee, calcule_recale, decalage_h).
    Un decalage positif signifie que l'hydrogramme calcule est EN RETARD.
    """
    debut, fin = grille_commune(temps_cible, temps_calcule)
    _, qc = reechantillonner(temps_cible, debit_cible, pas_h, debut, fin)
    _, qs = reechantillonner(temps_calcule, debit_calcule, pas_h, debut, fin)

    n = max(len(qc), len(qs))
    qc = np.pad(qc, (0, n - len(qc)), mode="edge")
    qs = np.pad(qs, (0, n - len(qs)), mode="edge")

    decalage_pas = _decalage_pas(qc, qs)
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
# Critere KGE
# ---------------------------------------------------------------------------

def kge(debit_cible, debit_calcule):
    """
    Kling-Gupta Efficiency et ses trois composantes.

        KGE = 1 - sqrt[ (r-1)^2 + (alpha-1)^2 + (beta-1)^2 ]

        r     : correlation          -> accord sur la forme
        alpha : sigma_calc/sigma_cib -> accord sur la variabilite (~ pic)
        beta  : moy_calc /moy_cib    -> biais (~ volume)

    Retourne (kge, r, alpha, beta).
    """
    c = np.asarray(debit_cible, dtype=float)
    s = np.asarray(debit_calcule, dtype=float)

    if c.std() == 0 or s.std() == 0 or c.mean() == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")

    r = float(np.corrcoef(c, s)[0, 1])
    alpha = float(s.std() / c.std())
    beta = float(s.mean() / c.mean())
    valeur = 1.0 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2)
    return float(valeur), r, alpha, beta


# ---------------------------------------------------------------------------
# Diagnostic complet d'un essai
# ---------------------------------------------------------------------------

@dataclass
class Diagnostic:
    """Resultat complet de la comparaison d'un essai avec sa cible."""
    kge: float
    r: float
    alpha: float
    beta: float
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

        Le KGE non calculable ne bloque pas non plus : il ne figure dans aucun
        critere ni dans aucune sortie.
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


def diagnostiquer(temps_cible, debit_cible, temps_calcule, debit_calcule,
                  pas_h=PAS_RECALAGE_H,
                  couverture_min=0.9, tolerance_volume=0.05,
                  tolerance_pic=0.02, r_min=0.97, fenetre=None):
    """
    Compare un hydrogramme calcule a sa cible et retourne un Diagnostic complet.

    tolerance_volume / tolerance_pic / r_min : ce que « converge » exigera.
    Ce sont les MEMES grandeurs et les memes seuils que ceux sur lesquels la
    recherche s'arrete — les separer avait laisse le verdict de l'etude
    dependre du KGE, que la recherche ne cherchait plus a satisfaire.

    Les trois composantes du KGE sont conservees systematiquement : elles
    servent au diagnostic, r etant de surcroit le critere de forme.

    LE DECALAGE EST RAPPORTE, JAMAIS JUGE. Diagnostic.decalage_h porte la
    mesure, resume() l'affiche, le classeur et la note de synthese la
    reprennent — et rien n'en tire de verdict. Un seuil « decalage_max_h »
    a existe jusqu'au 08/08/2026 : voir Diagnostic.converge pour ce qu'il
    coutait et pourquoi il a ete retire.

    couverture_min : fraction de la duree de la cible que la fenetre de calcul
    doit couvrir. En dessous, une alerte est levee : un hydrogramme tronque
    prive le calage d'une partie du volume, qu'il chercherait alors a
    compenser en surdimensionnant l'apport.

    fenetre : (t0, tf) en heures, sur la base de temps de la CIBLE — le
    hydrogramme PRINCIPAL a juger (typiquement calage.fenetre_injection,
    detectee sur l'ecart au residuel). None (par defaut) : comportement
    d'avant ce parametre, la comparaison porte sur toute la fenetre commune
    aux deux series.

    LE PIC, LE VOLUME ET LA COUVERTURE SONT TOUS TROIS RESTREINTS A CETTE
    FENETRE quand elle est fournie. Une mini-crue isolee dans la serie
    d'entree, avant ou apres l'evenement cale, ne doit peser ni sur le pic
    (un maximum pris hors de l'evenement jugerait un debit qui n'est pas
    celui qu'on cale), ni sur le volume, ni sur l'alerte de couverture (dont
    la reference — la duree de « la cible » — redevient la duree de
    l'evenement, et non celle de toute la donnee d'entree fournie).
    """
    c_a, s_a, decalage_h = recaler(
        temps_cible, debit_cible, temps_calcule, debit_calcule, pas_h
    )

    tc = np.asarray(temps_cible, dtype=float)
    ts = np.asarray(temps_calcule, dtype=float)
    if fenetre is not None:
        f0, f1 = float(fenetre[0]), float(fenetre[1])

        # LA FORME EST JUGEE SUR LA MEME FENETRE QUE LA POINTE ET LE VOLUME,
        # PAS SUR c_a/s_a — qui portent toute la grille commune aux deux
        # series. Sans cette restriction, une mini-crue isolee hors de
        # l'evenement cale (avant ou apres) degradait r (et le KGE) sans le
        # moindre rapport avec l'apport qu'on cherche a caler : le § 7 de
        # l'auto-test verifiait deja que le pic et le volume l'ignoraient,
        # jamais que la forme le faisait.
        #
        # Meme decalage que pour le pic et le volume : cible(t) pour
        # t dans [f0, f1] comparee a calcule(t + decalage_h), soit
        # exactement l'appariement que recaler() etablit ailleurs.
        grille_f = np.arange(f0, f1 + pas_h / 2, pas_h)
        cible_f = np.interp(grille_f, tc,
                            np.asarray(debit_cible, dtype=float))
        calc_f = np.interp(grille_f + decalage_h, ts,
                           np.asarray(debit_calcule, dtype=float))
        # np.interp PROLONGE par la valeur de bord hors du domaine calcule :
        # comme pour calcul_rephase() ailleurs, on exclut ces points plutot
        # que de les laisser fausser la correlation avec un plateau fictif.
        dedans_f = ((grille_f + decalage_h >= ts[0])
                   & (grille_f + decalage_h <= ts[-1]))
        if dedans_f.sum() >= 2:
            cible_f, calc_f = cible_f[dedans_f], calc_f[dedans_f]
        valeur, r, alpha, beta = kge(cible_f, calc_f)

        dans_c = (tc >= f0) & (tc <= f1)
        dans_s = (ts >= f0) & (ts <= f1)
        pic_cible = (float(np.max(np.asarray(debit_cible, dtype=float)[dans_c]))
                    if dans_c.any() else float(np.max(debit_cible)))
        pic_calcule = (float(np.max(np.asarray(debit_calcule, dtype=float)[dans_s]))
                      if dans_s.any() else float(np.max(debit_calcule)))
    else:
        valeur, r, alpha, beta = kge(c_a, s_a)
        pic_cible = float(np.max(debit_cible))
        pic_calcule = float(np.max(debit_calcule))

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
    if fenetre is not None and np.isfinite(debut):
        # La fenetre du hydrogramme principal ne peut que RETRECIR la
        # comparaison, jamais l'elargir au-dela de ce que les deux series
        # couvrent reellement.
        debut, fin = max(debut, f0), min(fin, f1)
    avance, retard = max(decalage_h, 0.0), min(decalage_h, 0.0)

    # BORNES PROPRES AU VOLUME. « debut/fin » servent aussi a juger la
    # COUVERTURE plus bas, ou ils doivent rester ceux de la fenetre : les
    # elargir la-bas ferait passer pour couverte une simulation qui ne l'est
    # pas. Le repli ci-dessous ne touche donc que la mesure des volumes.
    debut_v, fin_v = debut, fin
    decalage_hors_fenetre = None
    if np.isfinite(debut) and (fin_v + retard) - (debut_v + avance) <= 0:
        # LE DECALAGE EXCEDE LA FENETRE JUGEE — il ne reste, apres recalage,
        # aucun intervalle commun aux deux series. Rendre « nan » ici etait
        # exact mais muet : caler() n'y lisait qu'un volume non calculable et
        # concluait « le modele ne repond plus a cet apport », ce qui designe
        # l'hydraulique alors que la cause est la MESURE DU DECALAGE.
        #
        # On rend donc la comparaison des volumes a la fenetre commune
        # ENTIERE — meme regle que fenetre_injection() sur un ecart nul :
        # mieux vaut ne rien restreindre que restreindre au hasard — et on le
        # DIT. Le decalage reste RAPPORTE, JAMAIS JUGE (voir plus haut) :
        # l'alerte n'est pas bloquante, la comparaison redevient possible, et
        # c'est a l'operateur de relire ses cibles.
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

    if np.isfinite(debut_v) and (fin_v + retard) - (debut_v + avance) <= 0:
        # Meme apres elargissement, rien de comparable : la, c'est franc.
        vol_cible = vol_calcule = float("nan")
    else:
        vol_calcule = volume(temps_calcule, debit_calcule,
                             debut_v + avance, fin_v + retard, pas_h)
        vol_cible = volume(temps_cible, debit_cible,
                           debut_v - retard, fin_v - avance, pas_h)

    # DEUX FAMILLES — voir Diagnostic.converge pour la ligne de partage.
    # « alertes » porte tout ce qui est signale ; « bloquantes » le seul
    # sous-ensemble qui invalide la comparaison.
    alertes, bloquantes = [], []
    if decalage_hors_fenetre:
        alertes.append(decalage_hors_fenetre)
    if not np.isfinite(valeur):
        alertes.append("KGE non calculable (serie constante ou moyenne nulle)")

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
    duree_cible = ((f1 - f0) if fenetre is not None
                   else float(tc[-1] - tc[0]))
    if not np.isfinite(debut):
        bloquantes.append(
            "les fenetres de temps de la cible et du calcul ne se recouvrent "
            "pas - verifier la date de debut de la simulation")
    elif duree_cible > 0 and (fin - debut) < couverture_min * duree_cible:
        bloquantes.append(
            f"la fenetre de calcul ne couvre que "
            f"{100 * (fin - debut) / duree_cible:.0f} % de la duree de "
            f"l'hydrogramme cible - allonger la simulation, sinon le volume "
            f"manquant sera attribue a tort a un defaut d'apport")
    alertes.extend(bloquantes)

    return Diagnostic(
        kge=valeur, r=r, alpha=alpha, beta=beta, decalage_h=decalage_h,
        rapport_pic=pic_calcule / pic_cible if pic_cible else float("nan"),
        rapport_volume=vol_calcule / vol_cible if vol_cible else float("nan"),
        alertes=alertes, alertes_bloquantes=bloquantes,
        tolerance_volume=tolerance_volume, tolerance_pic=tolerance_pic,
        r_min=r_min, fenetre=fenetre,
    )


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
    import sys

    # Jusqu'ici cet auto-test ne faisait qu'AFFICHER des nombres : il ne
    # pouvait pas echouer, donc il ne prouvait rien. Or c'est le module qui
    # porte le KGE, la strategie de recherche et les criteres d'arret — et
    # c'est deja ici qu'un garde-fou (le decalage temporel) etait reste mort
    # en silence. Chaque demonstration est desormais assortie d'un controle.
    _echecs = []

    def _verifier(libelle, condition, detail=""):
        print(f"      [{'OK' if condition else 'ECHEC'}] {libelle}"
              + (f"  ->  {detail}" if detail else ""))
        if not condition:
            _echecs.append(libelle)

    def hydrogramme(t, pic, t_pic=6.0, forme=2.5):
        t = np.maximum(np.asarray(t, dtype=float), 1e-3)
        return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))

    temps = np.linspace(0.01, 30, 400)
    cible = hydrogramme(temps, pic=100.0)

    print("--- 1. Identite (calcule = cible) ---")
    d = diagnostiquer(temps, cible, temps, cible)
    print(d.resume(), "-> converge :", d.converge)
    _verifier("KGE = 1 quand le calcul EST la cible", abs(d.kge - 1.0) < 1e-6,
              f"KGE={d.kge:.6f}")
    _verifier("r, alpha et beta valent 1",
              max(abs(d.r - 1), abs(d.alpha - 1), abs(d.beta - 1)) < 1e-6)
    _verifier("le cas identite converge", d.converge)

    print("\n--- 2. Decalage temporel PUR de +3 h (translation, forme inchangee) ---")
    print("    la methode doit le neutraliser : KGE doit rester ~1")
    decale = hydrogramme(temps - 3.0, pic=100.0)
    decale[temps < 3.0] = hydrogramme(np.array([0.01]), 100.0)[0]
    d = diagnostiquer(temps, cible, temps, decale)
    print(d.resume(), "-> converge :", d.converge)
    _verifier("un decalage PUR est neutralise par le recalage", d.kge > 0.99,
              f"KGE={d.kge:.4f}")
    _verifier("le decalage est neanmoins RAPPORTE, pas efface",
              abs(d.decalage_h) > 2.0, f"{d.decalage_h:+.2f} h")

    print("\n--- 2 bis. Fenetres de temps d'origines differentes ---")
    print("    La serie extraite du modele demarre au debut de la simulation,")
    print("    la cible au debut de l'evenement : les origines different.")
    print("    Le decalage rapporte doit rester le decalage PHYSIQUE.")
    for retard in (0.0, 3.0):
        _, _, mesure = recaler(temps, cible, temps + retard, cible)
        etat = "ok" if abs(mesure - retard) <= 1.5 * 0.25 else "INCORRECT"
        print(f"    fenetre calculee decalee de {retard:+.1f} h "
              f"-> decalage mesure {mesure:+.2f} h  [{etat}]")
        _verifier(f"decalage de fenetre {retard:+.1f} h correctement mesure",
                  abs(mesure - retard) <= 1.5 * 0.25, f"{mesure:+.2f} h")
    print("    (rechantillonner chaque serie depuis sa propre origine")
    print("     annulerait ce decalage et neutraliserait le garde-fou)")

    print("\n--- 2 ter. Fenetre de calcul plus longue ou tronquee ---")
    print("    Les volumes se comparent sur la fenetre COMMUNE, jamais chacun")
    print("    sur sa propre etendue.")
    for libelle, t_calc in [
        ("simulation plus longue (48 h)", np.linspace(0.01, 48, 700)),
        ("simulation tronquee (20 h)", np.linspace(0.01, 20, 300)),
        ("fenetres disjointes (50-80 h)", np.linspace(50, 80, 300)),
    ]:
        depart = 50.0 if t_calc[0] > 40 else 0.0
        d = diagnostiquer(temps, cible, t_calc, hydrogramme(t_calc - depart, 100.0))
        print(f"    {libelle:32s} vol={d.rapport_volume:.3f}")
        for a in d.alertes:
            print(f"        ALERTE : {a}")
        if "disjointes" in libelle:
            _verifier("des fenetres disjointes levent une alerte",
                      bool(d.alertes))
        else:
            # Le defaut corrige a la 4e passe : integrer chaque serie sur SA
            # propre etendue gonflait le rapport de volume d'une simulation
            # plus longue, sans le moindre defaut de calage.
            _verifier(f"volume compare sur la fenetre commune — {libelle}",
                      abs(d.rapport_volume - 1.0) < 0.02,
                      f"vol={d.rapport_volume:.3f}")
        if "tronquee" in libelle:
            _verifier("une simulation trop courte est signalee",
                      bool(d.alertes))

    print("\n--- 3. Apport sous-dimensionne (-25 %) ---")
    d = diagnostiquer(temps, cible, temps, 0.75 * cible)
    print(d.resume(), "-> converge :", d.converge)
    _verifier("un apport a -25 % donne beta ~ 0,75", abs(d.beta - 0.75) < 0.01,
              f"beta={d.beta:.4f}")
    _verifier("un apport sous-dimensionne ne converge PAS", not d.converge)

    print("\n--- 4. Le decalage est MESURE et RAPPORTE, jamais juge ---")
    # Un seuil « decalage_max_h » levait ici une alerte. Retire le 08/08/2026
    # sur decision utilisateur : il s'est declenche sur SEPT sections sur sept
    # d'un calage reel, pour des decalages structurels de 3,60 a 5,30 h, et
    # une alerte qui se declenche partout apprend a l'ignorer. L'amplitude ne
    # distinguait pas un temps de transfert reel d'un appariement de pics sans
    # rapport — les deux peuvent valoir 5 h. Voir Diagnostic.converge.
    tres_decale = hydrogramme(temps - 6.0, pic=100.0)
    tres_decale[temps < 6.0] = hydrogramme(np.array([0.01]), 100.0)[0]
    d = diagnostiquer(temps, cible, temps, tres_decale)
    print(d.resume())
    _verifier("un decalage de 6 h est MESURE et rapporte",
              abs(d.decalage_h - 6.0) < 0.15, f"{d.decalage_h:+.2f} h")
    _verifier("il figure dans le resume lu par l'utilisateur",
              "decalage" in d.resume(), d.resume())
    _verifier("il ne leve AUCUNE alerte, quelle que soit son amplitude",
              not any("decalage" in a.lower() for a in d.alertes),
              str(d.alertes) or "aucune")
    _verifier("il ne bloque donc rien non plus",
              not any("decalage" in a.lower() for a in d.alertes_bloquantes),
              str(d.alertes_bloquantes) or "aucune")
    # Meme forme, meme amplitude, meme fenetre couverte — seul l'instant du
    # pic differe de 6 h. Le recalage l'annule, les trois grandeurs sont donc
    # parfaites, et le verdict doit suivre, SANS reserve d'aucune sorte.
    _long = np.linspace(0.01, 72, 900)
    _cible_l = hydrogramme(_long, pic=100.0, t_pic=12.0)
    _decale = diagnostiquer(_long, _cible_l, _long,
                            hydrogramme(_long - 6.0, pic=100.0, t_pic=12.0))
    _verifier("un calage juste mais decale est conforme, sans aucune alerte",
              _decale.converge and not _decale.alertes,
              f"converge={_decale.converge} vol={_decale.rapport_volume:.3f} "
              f"pic={_decale.rapport_pic:.3f} r={_decale.r:.3f} "
              f"alertes={_decale.alertes}")
    _verifier("et son decalage reste lisible dans le resume",
              abs(_decale.decalage_h - 6.0) < 0.15,
              f"{_decale.decalage_h:+.2f} h")

    print("\n--- 4 ter. Une couverture insuffisante, elle, BLOQUE ---")
    _court = temps[temps <= 0.3 * temps[-1]]
    d = diagnostiquer(temps, cible, _court, hydrogramme(_court, 100.0))
    for a in d.alertes:
        print("   ALERTE :", a)
    _verifier("une simulation trop courte est BLOQUANTE",
              bool(d.alertes_bloquantes) and not d.converge,
              str(d.alertes_bloquantes))

    print("\n--- 4bis. Le retard ne doit pas couter du volume ---")
    #
    # Un apport JUSTE mais retarde ne doit pas etre juge deficitaire. Deux
    # defauts se combinaient pour cela, et ce controle les fige tous deux :
    #   - la correlation croisee sous-estimait le retard (0,00 h pour 1,6 h
    #     reel) des que l'evenement ne revient pas a sa ligne de base ;
    #   - le volume etait compare sur la fenetre brute, ou un retard ampute
    #     la serie en retard de tout ce qui manque a la fermeture.
    # Resultat : le critere reclamait 3,7 % de volume que la correction, elle,
    # ne voyait pas manquer. La boucle stagnait sans levier.
    t_ev = np.linspace(0, 26, 261)
    crue = 460.0 * np.exp(-0.5 * ((t_ev - 16.0) / 7.0) ** 2)
    _verifier("la fenetre coupe bien la decrue (cas eprouvant)",
              crue[-1] / crue.max() > 0.3,
              f"{100 * crue[-1] / crue.max():.0f} % du pic a la fermeture")
    for _retard in (0.8, 1.6, 3.0):
        _tardif = 460.0 * np.exp(-0.5 * ((t_ev - _retard - 16.0) / 7.0) ** 2)
        _d = diagnostiquer(t_ev, crue, t_ev, _tardif)
        _verifier(f"retard de {_retard} h : le decalage est vu",
                  abs(_d.decalage_h - _retard) <= PAS_RECALAGE_H,
                  f"detecte {_d.decalage_h:+.2f} h")
        _verifier(f"retard de {_retard} h : le volume reste juste",
                  abs(_d.rapport_volume - 1.0) <= 0.005,
                  f"{100 * _d.rapport_volume:.2f} % de la cible")

    print("\n--- 5. Volume et fenetre commune ---")
    # La strategie de recherche a quitte ce module : la correction de
    # l'apport est desormais ADDITIVE et vit dans calage.py, avec ses propres
    # criteres d'arret. criteres.py ne garde que l'ANALYSE — recalage,
    # volumes, KGE, diagnostic — ce qui etait sa vocation.
    t_a = np.linspace(0, 24, 200)
    t_b = np.linspace(6, 36, 200)
    # Les deux bornes ne servent pas a la meme chose et ne doivent pas etre
    # confondues : grille_commune ENGLOBE les deux series, pour le recalage
    # temporel ; fenetre_commune les INTERSECTE, seule etendue ou des volumes
    # soient comparables.
    _verifier("grille_commune englobe les deux series",
              grille_commune(t_a, t_b) == (0.0, 36.0),
              str(grille_commune(t_a, t_b)))
    _verifier("fenetre_commune intersecte les deux series",
              fenetre_commune(t_a, t_b) == (6.0, 24.0),
              str(fenetre_commune(t_a, t_b)))
    plat = np.ones_like(t_a) * 10.0
    _verifier("le volume d'un debit constant vaut debit x duree",
              abs(volume(t_a, plat, 0.0, 24.0) - 240.0) < 1e-6,
              f"{volume(t_a, plat, 0.0, 24.0):.3f}")
    _verifier("des series disjointes n'ont pas de fenetre commune",
              not np.isfinite(fenetre_commune(t_a, np.linspace(50, 80, 50))[0]))

    print("\n--- 6. Normalisation des hydrogrammes d'entree (pas <= 6 min) ---")
    # Une cible HSMF collee a la main arrive typiquement au pas horaire : trop
    # grossier pour le recalage temporel et pour la forme injectee dans le
    # modele, qui en heritent tous deux telle quelle. Une serie DEJA a 6 min
    # ou plus fine, elle, est conservee a son pas natif, sans degradation.
    t_grossier = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    q_grossier = np.array([0.0, 50.0, 100.0, 40.0, 0.0])
    t_fin, q_fin, pas_initial = normaliser_entree(t_grossier, q_grossier)
    _verifier("un pas horaire est ramene a 6 minutes",
              abs(np.max(np.diff(t_fin)) - PAS_ENTREE_H) < 1e-9,
              f"pas max {3600 * np.max(np.diff(t_fin)):.0f} s")
    _verifier("le pas d'origine est rapporte, pour le journal",
              abs(pas_initial - 1.0) < 1e-9, f"{pas_initial} h")
    _verifier("les bornes de temps sont conservees",
              t_fin[0] == t_grossier[0] and abs(t_fin[-1] - t_grossier[-1]) < 1e-9,
              f"{t_fin[0]:.3f} -> {t_fin[-1]:.3f} h")
    _verifier("le pic reste 100 (interpolation lineaire, pas de lissage)",
              abs(np.max(q_fin) - 100.0) < 1e-6, f"{np.max(q_fin):.3f}")
    t_source_menue, q_source_menue = reechantillonner(t_grossier, q_grossier, 0.05)
    t_menu, q_menu, pas_menu = normaliser_entree(t_source_menue, q_source_menue)
    _verifier("un hydrogramme plus fin que 6 min est conserve a son pas natif",
              pas_menu is None
              and len(t_menu) == len(t_source_menue)
              and abs(np.max(np.diff(t_menu)) - 0.05) < 1e-9,
              f"{len(t_menu)} pas, pas max "
              f"{3600 * np.max(np.diff(t_menu)):.0f} s, pas_initial={pas_menu}")
    t_deja, q_deja, pas_deja = normaliser_entree(
        *reechantillonner(t_grossier, q_grossier, PAS_ENTREE_H))
    _verifier("une serie deja au pas de 6 min ressort intacte, sans conversion",
              pas_deja is None and len(t_deja) == len(q_deja) == 41,
              f"pas_initial={pas_deja}, {len(t_deja)} valeurs")
    _verifier("une serie de moins de deux points ne fait rien echouer",
              normaliser_entree([0.0], [1.0])[2] is None)

    print("\n--- 7. Fenetre du hydrogramme PRINCIPAL (parametre `fenetre`) ---")
    # Demande : une mini-crue ISOLEE, avant l'evenement cale, ne doit pas
    # peser sur le volume, la pointe ou l'alerte de couverture — seule
    # l'evenement effectivement calé (le second pic) doit etre juge.
    _tf = np.linspace(0.0, 48.0, 481)
    _cible7 = (hydrogramme(_tf, pic=20.0, t_pic=4.0, forme=3.0)
              + hydrogramme(_tf - 24.0, pic=100.0, t_pic=6.0, forme=3.0))
    # Le calcul REPRODUIT le pic principal a la perfection, mais s'ecarte
    # fortement sur la mini-crue anterieure (deux fois trop de debit) — une
    # excursion de debit de base marque, sans rapport avec l'apport cale.
    _calc7 = (hydrogramme(_tf, pic=40.0, t_pic=4.0, forme=3.0)
             + hydrogramme(_tf - 24.0, pic=100.0, t_pic=6.0, forme=3.0))
    _fen7 = (18.0, 40.0)   # encadre largement le seul evenement principal
    _sans_fen = diagnostiquer(_tf, _cible7, _tf, _calc7, tolerance_volume=0.05)
    _avec_fen = diagnostiquer(_tf, _cible7, _tf, _calc7, tolerance_volume=0.05,
                              fenetre=_fen7)
    _verifier("sans fenetre, la mini-crue anterieure casse le volume",
              abs(_sans_fen.rapport_volume - 1.0) > 0.05,
              f"{100 * _sans_fen.rapport_volume:.1f} %")
    _verifier("avec la fenetre du hydrogramme principal, le volume est juste",
              abs(_avec_fen.rapport_volume - 1.0) < 0.01,
              f"{100 * _avec_fen.rapport_volume:.1f} %")
    _verifier("avec la fenetre, la pointe ignore aussi la mini-crue",
              abs(_avec_fen.rapport_pic - 1.0) < 0.01,
              f"{100 * _avec_fen.rapport_pic:.1f} %")
    _verifier("sans fenetre, la mini-crue anterieure degrade aussi la forme",
              _sans_fen.r < 0.999, f"r={_sans_fen.r:.4f}")
    _verifier("avec la fenetre, la forme ignore aussi la mini-crue (r ~ 1)",
              abs(_avec_fen.r - 1.0) < 1e-3, f"r={_avec_fen.r:.6f}")
    _verifier("avec la fenetre, la couverture se juge sur sa duree, pas sur "
              "celle de toute la serie d'entree",
              not any("couvre que" in a for a in _avec_fen.alertes),
              str(_avec_fen.alertes))
    _verifier("la fenetre jugee est rapportee dans le resume",
              f"{_fen7[0]:.2f}-{_fen7[1]:.2f} h" in _avec_fen.resume(),
              _avec_fen.resume())
    _verifier("sans fenetre fournie, le resume ne mentionne aucune fenetre",
              "fenetre" not in _sans_fen.resume(), _sans_fen.resume())

    print("\n--- 8. Tolerance de volume par defaut ---")
    # Le defaut precedent (0,5 %) rendait certains modeles hors d'atteinte par
    # construction des que le debit de base est marque — voir calage.py,
    # Configuration.tolerance_beta.
    _verifier("le defaut de Diagnostic.tolerance_volume est 5 %",
              abs(Diagnostic(0, 0, 0, 0, 0, 0, 0).tolerance_volume - 0.05)
              < 1e-9)
    import inspect as _inspect
    _defaut_diag = _inspect.signature(diagnostiquer).parameters[
        "tolerance_volume"].default
    _verifier("le defaut de diagnostiquer(tolerance_volume=...) est 5 %",
              abs(_defaut_diag - 0.05) < 1e-9, f"{_defaut_diag}")

    print("\n" + "=" * 74)
    if _echecs:
        print(f"{len(_echecs)} ECHEC(S) : {_echecs}")
    else:
        print("Tous les controles passent.")
    print("=" * 74)
    sys.exit(1 if _echecs else 0)
