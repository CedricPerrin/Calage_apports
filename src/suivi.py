# -*- coding: utf-8 -*-
"""
Suivi de l'avancement d'un calage, reactualise a chaque apport valide.

Un calage represente plusieurs heures de calcul. Attendre la fin pour savoir
ou il en est, c'est decouvrir trop tard qu'il derive. Ce module reecrit donc,
apres CHAQUE apport valide, le rapport, le tableau de bord et les figures
correspondant a ce qui est connu a cet instant.

Trois principes de fond.

1. LE SUIVI NE DOIT JAMAIS INTERROMPRE LE CALAGE. Toute defaillance de
   production d'un livrable est capturee et consignee, jamais propagee : il
   serait absurde de perdre six heures de calcul parce qu'une figure n'a pas
   pu s'ecrire.

2. LES ECRITURES SONT ATOMIQUES. Les fichiers sont relus pendant que le
   calage tourne ; ils sont donc ecrits sous un nom temporaire puis
   renommes, de sorte qu'un lecteur ne tombe jamais sur un fichier a moitie
   ecrit.

3. LE TEMPS RESTANT EST ESTIME. C'est le seul chiffre qui permette de decider
   s'il faut attendre ou revenir plus tard.

Comme criteres.py et livrables.py, ce module est INDEPENDANT du code de
calcul hydraulique.

Usage :  python suivi.py        (simule un calage complet)
"""

import json
import os
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import livrables as liv

EN_ATTENTE, EN_COURS, VALIDE, ECHOUE = "en attente", "en cours", "validé", "échoué"

# Excel refuse ces caracteres dans un nom d'onglet, et le limite a 31 signes.
CARACTERES_INTERDITS_ONGLET = set("[]:*?/\\")


def nom_onglet(nom):
    """
    Nom d'onglet Excel acceptable pour un apport.

    Les conditions limites HEC-RAS portent des noms du type
    « Perimeter 1: BCLine 3 » : sans ce filtrage, un seul apport ainsi nomme
    ferait echouer l'ecriture du classeur ENTIER, donc le suivi de tous les
    autres.
    """
    propre = "".join("-" if c in CARACTERES_INTERDITS_ONGLET else c
                     for c in str(nom)).strip()
    return (propre or "apport")[:31]


def _sur_grille(temps_cible, temps, debits):
    """
    Projette une serie sur la base de temps de la cible, SANS extrapoler.

    Hors de la fenetre effectivement calculee, la valeur reste indefinie
    plutot que prolongee par la derniere connue : une valeur prolongee se lit
    comme une mesure et fausserait la colonne d'ecart aux extremites, la ou
    justement on cherche a voir si le calcul couvre bien la cible.
    """
    grille = np.asarray(temps_cible, dtype=float)
    t = np.asarray(temps, dtype=float)
    q = np.asarray(debits, dtype=float)
    if t.size == 0 or q.size == 0:
        return np.full(grille.shape, np.nan)
    ordre = np.argsort(t)
    return np.interp(grille, t[ordre], q[ordre],
                     left=float("nan"), right=float("nan"))


def _etat_a_tracer(etats, en_cours):
    """
    Quel apport l'ecran doit montrer : celui en cours s'il a deja produit un
    essai, sinon LE DERNIER QUI EN A PRODUIT UN.

    Un apport n'a de series qu'une fois son premier essai EVALUE, c'est-a-dire
    apres son calcul HEC-RAS — soit environ trois heures. Sans repli, le
    panneau « Atteinte de la cible » restait donc vide pendant tout le calcul,
    c'est-a-dire pendant exactement les heures ou on le regarde, et ne
    s'allumait que quelques secondes entre l'evaluation d'un essai et le debut
    de l'apport suivant. Sur un calage ou chaque apport converge du premier
    coup, personne ne voyait jamais de courbe.
    """
    if en_cours is not None and etats[en_cours].series:
        return etats[en_cours]
    return next((e for e in reversed(etats) if e.series), None)


def _courbes_precedentes(etats, etat_trace, points=90):
    """
    Les hydrogrammes RETENUS aux sections deja calees, pour les tracer
    derriere la paire courante.

    POURQUOI LES MONTRER. Le panneau ne disait qu'une chose a la fois :
    l'apport en cours, sa cible et sa section. Or un calage sequentiel se lit
    de l'amont vers l'aval, et ce qu'on veut voir pendant les heures qu'il
    dure, c'est si la FAMILLE de courbes se tient — un debit qui grandit
    section apres section, des formes qui se ressemblent. Une section calee
    dont l'hydrogramme sort du lot se voit d'un coup d'oeil ; dans trois
    jauges lues l'une apres l'autre, non.

    SEULEMENT LES VALIDEES, ET SEULEMENT LA SECTION. Un apport en echec ou
    encore en recherche n'a pas d'hydrogramme retenu — le montrer laisserait
    croire a un resultat. Et l'on ne publie que la serie CALCULEE : les
    cibles precedentes ne se comparent pas a la cible courante, elles
    encombreraient le trace sans rien dire.

    ALLEGEES DEUX FOIS. La serie est deja sous-echantillonnee a 180 points au
    moment de l'essai ; on la ramene ici a 90, parce qu'elles sont N et que
    l'etat est relu toutes les deux secondes. Le pic reste preserve — c'est
    _alleger qui s'en charge.
    """
    if etat_trace is None:
        return []
    rendu = []
    for etat in etats:
        if etat is etat_trace:
            break
        if etat.statut != VALIDE or not etat.series:
            continue
        (_, _), (t_s, q_s) = etat.series
        temps, debits = Suivi._alleger(t_s, q_s, points=points)
        if len(temps) < 2:
            continue
        rendu.append({"apport": etat.nom_apport, "section": etat.nom_section,
                      "temps": temps, "debit": debits})
    return rendu


def _courbes_publiees(etat):
    """
    Les deux courbes d'un apport, telles que l'ecran doit les tracer.

    L'apport est NOMME dans le resultat : ce ne sont pas toujours celles de
    l'apport en cours (voir _etat_a_tracer), et montrer sans dire de qui
    reviendrait a laisser croire qu'on regarde le calcul qui tourne.

    LA CIBLE EST DECALEE DE -Δt, exactement comme au classeur d'iterations et
    comme dans calage.ecart_a_la_cible : c'est cette cible-la que la section
    est censee reproduire, et c'est la seule superposition qui se lise sous
    des jauges annoncant 100 %. Le decalage accompagne les courbes pour que la
    legende puisse le nommer plutot que de le laisser deviner.

    Decaler la cible revient ici a tracer ses debits aux instants t - Δt : sur
    des series deja sous-echantillonnees, une translation de la base de temps
    est exacte, la ou une reinterpolation ajouterait une approximation a
    l'endroit meme du pic.
    """
    if etat is None or not etat.series:
        return None
    (t_c, q_c), (t_s, q_s) = etat.series
    d = float(etat.decalage_correction or 0.0)
    return {"temps_cible": [round(t + d, 3) for t in t_c],
            "debit_cible": q_c,
            "temps_calcule": t_s,
            "debit_calcule": q_s,
            "decalage_h": round(d, 2),
            "apport": etat.nom_apport,
            "section": etat.nom_section,
            "statut": etat.statut}


def _cellule(valeur):
    """Valeur ecrivable telle quelle : un NaN devient une cellule vide."""
    if valeur is None:
        return None
    v = float(valeur)
    return None if np.isnan(v) else round(v, 4)

COULEURS = {
    EN_ATTENTE: "#BDC3C7",
    EN_COURS: liv.ALERTE,
    VALIDE: liv.OK,
    ECHOUE: liv.CIBLE,
}


@dataclass
class EtatApport:
    """Ce que l'on sait d'un apport a un instant donne."""
    nom_apport: str
    nom_section: str
    statut: str = EN_ATTENTE
    essais: int = 0
    facteur: float = float("nan")
    # VOLUME ATTEINT, en fraction de la cible — « rapport_volume » du
    # diagnostic, integre sur la fenetre ou les deux series existent. Ce champ
    # s'appelait « beta » et recevait le terme de biais du KGE, calcule lui sur
    # la grille qui ENGLOBE les deux series : sur un cas reel il affichait
    # 261 % la ou le calage lisait 104 %. Un nom qui ne dit pas ce qu'il porte
    # est ce qui a permis a l'erreur de passer.
    volume: float = float("nan")
    pic: float = float("nan")
    # Forme et decalage de l'essai EN COURS. Sans eux, ces deux grandeurs
    # n'existaient qu'une fois l'apport valide — l'affichage montrait donc une
    # jauge « Forme » vide precisement pendant la recherche, qui est le seul
    # moment ou l'on regarde.
    forme: float = float("nan")
    decalage: float = float("nan")
    # Δt EFFECTIVEMENT EMPLOYE pour construire la correction, en heures. Ce
    # n'est pas « decalage » ci-dessus, qui est celui du diagnostic : les deux
    # sont mesures differemment et peuvent differer. C'est celui-ci qui doit
    # servir a decaler la cible, au classeur comme a l'ecran.
    decalage_correction: float = 0.0
    # Series du DERNIER essai : (temps, cible, temps, calcule), sous-echantil-
    # lonnees. Ce sont elles que le suivi trace — les chiffres disent de
    # combien on s'ecarte, la courbe dit OU et POURQUOI. BRUTES, sans decalage :
    # la figure de comparaison en a besoin telles quelles (elle trace un
    # panneau brut et un panneau recale). Le decalage est applique au moment de
    # PUBLIER les courbes — voir _ecrire_etat.
    series: tuple = ()
    duree_s: float = 0.0
    motif: str = ""
    diagnostic: object = None
    historique: list = field(default_factory=list)
    # Series COMPLETES de chaque essai, non sous-echantillonnees : c'est la
    # matiere du classeur d'iterations. Distinctes de « series », qui ne garde
    # que le dernier essai allege pour l'affichage. Le cout est negligeable —
    # quelques centaines de valeurs par essai — et c'est la seule trace
    # exploitable de ce qui a ete tente une fois le calage fini.
    essais_detail: list = field(default_factory=list)
    # ETAT DE DEPART — la section AVEC L'APPORT A ZERO, sur la grille de la
    # cible. C'est de cet ecart-la, et d'aucun autre, que sort le premier
    # apport injecte. Sans lui le classeur commencait a l'essai 1 et personne
    # ne pouvait refaire la premiere injection : on comparait l'ecart RESTANT
    # apres l'essai 1 a l'apport qui l'avait PRECEDE, deux colonnes decalees
    # d'un rang. Meme forme que les entrees de essais_detail, avec
    # « essai » = 0.
    residuel_detail: object = None


class Suivi:
    """
    Journal vivant d'un calage. Un objet par calage, une methode par
    evenement, et des livrables reecrits a chaque fois.
    """

    def __init__(self, dossier, noms_apports, noms_sections,
                 pk_sections=None, titre="Calage des apports",
                 tolerances=None):
        """
        tolerances : {"volume", "pic", "forme"} en FRACTION, telles que la
            configuration du calage les porte. Elles sont republiees dans
            l'etat machine parce que l'affichage doit juger « conforme ou
            non » sur LES MEMES seuils que la boucle. Sans elles, le suivi
            colorait en rouge des valeurs parfaitement admises — un ecart de
            4 % juge sur une tolerance de 2 % alors que l'etude en tolere 5.
        """
        self.dossier = Path(dossier)
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.titre = titre
        self.pk_sections = pk_sections
        self.tolerances = tolerances or {}
        self.debut = datetime.now()
        self.incidents = []
        # Verdict final, renseigne par conclure(). Tant que « fin » vaut None,
        # le calage est repute EN COURS — c'est ce qui permet de distinguer un
        # calcul qui tourne d'un calcul mort.
        self.fin = None
        self.conforme = None
        self.motif_final = ""
        self.nb_calculs = None
        # BILAN DE MASSE DU DERNIER CALCUL, et le seuil au-dela duquel il est
        # rejete. Ce n'est PAS un ecart a la cible : c'est ce que le solveur
        # perd ou fabrique entre entrees, sorties et stockage. Publie parce
        # qu'un calage arrete pour « qualite numerique » n'exposait son
        # chiffre que dans le journal texte.
        self.bilan_masse = None
        self.etats = [EtatApport(a, s)
                      for a, s in zip(noms_apports, noms_sections)]
        # Un etat est ecrit DES LA CONSTRUCTION : entre le lancement et le
        # premier calcul il peut s'ecouler plusieurs minutes (clonage,
        # pretraitement), et sans lui l'affichage resterait vide en laissant
        # croire que rien n'a demarre.
        try:
            self._ecrire_etat()
        except Exception as e:                              # noqa: BLE001
            self._consigner("état machine initial", e)

    # --- evenements --------------------------------------------------------

    def noter_bilan_masse(self, pct, seuil_pct):
        """
        Bilan de masse du calcul qui vient de tourner, et son seuil de rejet.

        ECRIT L'ETAT MACHINE, SANS REPRODUIRE LES LIVRABLES : cette methode
        est appelee apres CHAQUE calcul, y compris ceux qui vont etre rejetes
        et n'entreront jamais dans un tableau. Relancer figures et classeurs
        a chaque fois couterait des secondes pour une seule ligne de texte.

        Un bilan non mesurable (NaN — colonne absente du HDF) n'efface pas le
        precedent : on garderait sinon l'ecran vide sans savoir si c'est la
        mesure ou le calcul qui manque.
        """
        try:
            valeur = float(pct)
        except (TypeError, ValueError):
            return
        if not np.isfinite(valeur):
            return
        self.bilan_masse = {"pct": valeur, "seuil_pct": float(seuil_pct)}
        try:
            self._ecrire_etat()
        except Exception as e:                              # noqa: BLE001
            self._consigner("état machine (bilan de masse)", e)

    def commencer_apport(self, i):
        """L'apport i entre en cours de recherche."""
        self.etats[i].statut = EN_COURS
        self._produire()

    @staticmethod
    def _alleger(temps, debits, points=180):
        """
        Sous-echantillonne une serie pour l'affichage.

        L'etat machine est relu toutes les deux secondes : y verser 700 points
        par serie le ferait grossir sans rien montrer de plus qu'un trace de
        quelques centaines de pixels de large. Le PIC est preserve — c'est la
        grandeur que l'on juge, il ne doit pas disparaitre dans un pas
        d'echantillonnage.
        """
        t = np.asarray(temps, dtype=float)
        q = np.asarray(debits, dtype=float)
        if t.size == 0:
            return [], []
        if t.size <= points:
            indices = np.arange(t.size)
        else:
            indices = np.unique(np.concatenate([
                np.linspace(0, t.size - 1, points).astype(int),
                [int(np.argmax(q))]]))
        return ([round(float(v), 3) for v in t[indices]],
                [round(float(v), 3) for v in q[indices]])

    def enregistrer_residuel(self, i, cible, residuel, decalage):
        """
        L'etat de reference de l'apport i : la section AVEC L'APPORT A ZERO.

        cible, residuel : couples (temps, debit).
        decalage : le Δt en heures, celui de decalage_minimisant_ecart(). La
            cible en est decalee de -Δt avant qu'on lui soustraie la section,
            comme le fait calage.ecart_a_la_cible().

        C'est le chainon qui manquait au classeur : ecart de CE bloc -> apport
        injecte a l'essai 1. Les blocs suivants disent la meme chose d'un essai
        au suivant.
        """
        t_c, q_c = cible
        grille = np.asarray(t_c, dtype=float)
        d = float(decalage) if np.isfinite(decalage) else 0.0
        self.etats[i].decalage_correction = d
        self.etats[i].residuel_detail = {
            "essai": 0, "volume": None, "pic": None, "forme": None,
            "decalage": None, "decalage_correction": d,
            "temps": grille,
            "cible": np.asarray(q_c, dtype=float),
            "calcule": _sur_grille(grille, *residuel),
            # LA CIBLE DECALEE DE -Δt, ET NON LA SECTION DECALEE DE +Δt.
            # C'est ce que compare calage.ecart_a_la_cible : les deux
            # ecritures donnent la meme courbe TRANSLATEE de Δt, et la
            # seconde rendait le classeur invérifiable — l'ecart y culminait
            # 3,8 h apres l'apport qu'il est cense expliquer (releve sur
            # premier apport d'un calage reel, 07/08/2026).
            "cible_decalee": _sur_grille(grille - d, grille,
                                         np.asarray(q_c, dtype=float)),
            # Rien n'a ete injecte a ce stade : c'est tout le propos du bloc.
            "apport": None}
        self._produire()

    def enregistrer_essai(self, i, facteur, volume, pic=float("nan"),
                          forme=float("nan"), decalage=float("nan"),
                          series=None, apport=None,
                          decalage_correction=None):
        """
        Un essai vient d'etre evalue. Rafraichit le suivi sans attendre la
        validation : sur un apport difficile, c'est justement la que l'on veut
        voir ou en est la recherche.

        volume : rapport du volume calcule au volume cible, sur la fenetre ou
            les deux series existent. C'est « rapport_volume » du diagnostic —
            jamais le terme de biais du KGE, retire depuis ; voir
            EtatApport.volume.
        series : (temps_cible, debit_cible, temps_calcule, debit_calcule).
        apport : (temps, debit) EFFECTIVEMENT injecte pour cet essai.
        decalage_correction : decalage EN HEURES effectivement employe pour
            rephaser le calcul avant d'en soustraire la cible — celui de
            calage.decalage_minimisant_ecart(), donc celui qui a servi a
            construire la correction. A defaut, « decalage » (celui du
            diagnostic) en tient lieu. C'est ce nombre qui permet de refaire
            le calcul a la main : sans lui, la colonne d'ecart du classeur
            n'est reproductible par personne.
        """
        etat = self.etats[i]
        etat.essais += 1
        etat.historique.append({"essai": etat.essais, "facteur": facteur,
                                "volume": volume, "pic": pic})
        etat.facteur, etat.volume, etat.pic = facteur, volume, pic
        etat.forme, etat.decalage = forme, decalage
        if series:
            t_c, q_c, t_s, q_s = series
            etat.series = (self._alleger(t_c, q_c), self._alleger(t_s, q_s))
            d = (float(decalage) if decalage_correction is None
                 else float(decalage_correction))
            if not np.isfinite(d):
                d = 0.0
            etat.decalage_correction = d
            grille = np.asarray(t_c, dtype=float)
            etat.essais_detail.append({
                "essai": etat.essais, "volume": volume, "pic": pic,
                "forme": forme, "decalage": decalage,
                "decalage_correction": d,
                "temps": grille,
                "cible": np.asarray(q_c, dtype=float),
                # Le calcul est ramene SUR LA GRILLE DE LA CIBLE : sans cela,
                # la colonne « ecart » du classeur soustrairait deux series de
                # pas differents ligne a ligne, ce qui ne veut rien dire.
                "calcule": _sur_grille(grille, t_s, q_s),
                # LA CIBLE DECALEE DE -Δt — meme convention et meme formule
                # que calage.ecart_a_la_cible(), dont ce classeur est le
                # calque. Decaler la SECTION de +Δt donne la meme courbe
                # translatee de Δt : les valeurs restent justes mais tombent
                # au mauvais instant, et l'ecart d'un bloc ne se raccorde plus
                # a l'apport du bloc suivant.
                "cible_decalee": _sur_grille(grille - d, grille,
                                             np.asarray(q_c, dtype=float)),
                "apport": (_sur_grille(grille, *apport) if apport is not None
                           else None)})
        self._produire()

    def valider_apport(self, i, diagnostic, duree_s=0.0, series=None):
        """
        L'apport i est valide et fige. C'est ici que le rapport complet est
        reecrit.

        series : (temps_cible, debit_cible, temps_calcule, debit_calcule) pour
        produire la figure de comparaison de la section. Facultatif.
        """
        etat = self.etats[i]
        etat.statut = VALIDE
        etat.diagnostic = diagnostic
        etat.volume = diagnostic.rapport_volume
        etat.pic = diagnostic.rapport_pic
        etat.duree_s = duree_s
        self._produire(series=(i, series) if series else None)

    def echouer_apport(self, i, motif, diagnostic=None, duree_s=0.0):
        """La recherche sur l'apport i s'arrete sans converger."""
        etat = self.etats[i]
        etat.statut = ECHOUE
        etat.motif = motif
        etat.diagnostic = diagnostic
        if diagnostic is not None:
            etat.volume = diagnostic.rapport_volume
            etat.pic = diagnostic.rapport_pic
        etat.duree_s = duree_s
        self._produire()

    def terminer(self):
        """Fin du calage : derniere production, et retour du rapport."""
        self._produire()
        return self.rapport()

    def conclure(self, conforme, motif="", nb_calculs=None):
        """
        Verdict final, ecrit dans l'etat machine.

        SANS CE POINT, RIEN NE DISTINGUE UN CALAGE FINI D'UN CALAGE MORT : les
        fichiers de suivi cessent simplement d'etre reecrits, et celui qui
        regarde ne sait pas s'il doit attendre encore ou s'il s'est passe
        quelque chose. C'est ce qui manquait.
        """
        self.conforme = bool(conforme)
        self.motif_final = motif or ""
        self.nb_calculs = nb_calculs
        self.fin = datetime.now()
        self._produire()

    # --- etat machine ------------------------------------------------------

    def etat(self):
        """
        Tout ce qu'il faut pour afficher l'avancement, en types simples.

        C'est ce que lit le plugin. Les pourcentages sont deja calcules ici :
        l'affichage ne doit RIEN recalculer, sans quoi le suivi et le rapport
        finiraient par ne plus dire la meme chose.
        """
        comptes, fraction = self.avancement()
        ecoule, moyenne, reste = self.temps()
        en_cours = next((i for i, e in enumerate(self.etats)
                         if e.statut == EN_COURS), None)

        def pct(valeur):
            return None if valeur is None or np.isnan(valeur) else round(
                100 * float(valeur), 1)

        def _arrondi(valeur):
            return None if valeur is None or np.isnan(valeur) else round(
                float(valeur), 2)

        # UNE SEULE FOIS : les courbes courantes et les precedentes se
        # definissent l'une par rapport a l'autre — celles d'avant sont celles
        # qui precedent CELLE-CI, pas celles qui precedent l'apport en cours.
        _trace = _etat_a_tracer(self.etats, en_cours)

        return {
            "titre": self.titre,
            "pid": os.getpid(),
            "debut": self.debut.isoformat(timespec="seconds"),
            "maj": datetime.now().isoformat(timespec="seconds"),
            "fin": self.fin.isoformat(timespec="seconds") if self.fin else None,
            "termine": self.fin is not None,
            "conforme": self.conforme,
            "motif_final": self.motif_final,
            "nb_calculs": self.nb_calculs,
            "fraction": round(fraction, 4),
            "comptes": {statut: comptes[statut] for statut in comptes},
            "ecoule_s": round(ecoule, 1),
            "moyenne_s": None if moyenne is None else round(moyenne, 1),
            "reste_s": None if reste is None else round(reste, 1),
            "fin_prevue": (
                (datetime.now() + timedelta(seconds=reste)).isoformat(
                    timespec="minutes") if reste else None),
            "en_cours": en_cours,
            "total": len(self.etats),
            # Les deux courbes A TRACER, pour l'affichage. Une seule serie est
            # publiee — celle qu'on regarde — plutot que toutes : l'etat est
            # relu toutes les deux secondes. Ce n'est pas forcement l'apport
            # en cours : tant que son premier essai n'est pas evalue, il n'a
            # rien a montrer, et c'est le dernier apport qui en a produit qui
            # est publie, nomme (voir _etat_a_tracer).
            #
            # LA CIBLE EST PUBLIEE DECALEE DE -Δt, comme au classeur et comme
            # dans calage.ecart_a_la_cible : c'est le seul trace qui se lise
            # sous les jauges. Publiee brute, elle apparaissait translatee de
            # Δt par rapport a la section — 3,8 h sur un calage reel — sous
            # trois jauges affichant 99,9 % : l'oeil concluait a un calage
            # faux la ou il etait juste. Le decalage accompagne les courbes
            # pour que la legende le nomme au lieu de le taire.
            "courbes": _courbes_publiees(_trace),
            # LES SECTIONS DEJA CALEES, derriere la paire courante. Voir
            # _courbes_precedentes : c'est la famille de courbes qui se lit,
            # pas la seule qui tourne.
            "courbes_precedentes": _courbes_precedentes(self.etats, _trace),
            # En POURCENTAGE, comme tout le reste de l'etat : l'affichage ne
            # doit pas avoir a convertir, il finirait par le faire autrement
            # que la boucle.
            "tolerances_pct": {cle: round(100 * float(v), 2)
                               for cle, v in self.tolerances.items()},
            # QUALITE DU CALCUL, PAS ECART A LA CIBLE. Voir noter_bilan_masse.
            # None tant qu'aucun calcul n'a rendu la mesure.
            "bilan_masse": self.bilan_masse,
            "incidents": len(self.incidents),
            "apports": [{
                "ordre": i + 1,
                "apport": e.nom_apport,
                "section": e.nom_section,
                "statut": e.statut,
                "essais": e.essais,
                "volume_pct": pct(e.volume),
                "pic_pct": pct(e.pic),
                # Le diagnostic complet n'existe qu'une fois l'apport acheve ;
                # pendant la recherche, on rend ce que le dernier essai a
                # donne. Sinon la jauge « Forme » reste vide tout le temps ou
                # l'on regarde effectivement l'ecran.
                "forme_pct": pct(e.diagnostic.r if e.diagnostic is not None
                                 else e.forme),
                "decalage_h": _arrondi(
                    e.diagnostic.decalage_h if e.diagnostic is not None
                    else e.decalage),
                "duree_s": round(e.duree_s, 1),
                "motif": e.motif,
            } for i, e in enumerate(self.etats)],
        }

    def _ecrire_etat(self):
        """
        Ecrit avancement.json, atomiquement comme le reste : il est relu
        toutes les deux secondes pendant qu'il est reecrit.
        """
        chemin = self.dossier / "avancement.json"
        provisoire = chemin.with_suffix(".json.tmp")
        provisoire.write_text(
            json.dumps(self.etat(), ensure_ascii=False, indent=1),
            encoding="utf-8")
        os.replace(provisoire, chemin)

    # --- production --------------------------------------------------------

    def _produire(self, series=None):
        """
        Reecrit rapport, tableau et figures. Chaque sortie est protegee
        separement : l'echec de l'une ne prive pas des autres.
        """
        taches = [
            # L'ETAT MACHINE D'ABORD : c'est lui que le plugin relit toutes
            # les deux secondes, et il coute quelques millisecondes la ou une
            # figure en coute plusieurs centaines. Le produire en premier
            # garantit que l'affichage suit meme si le reste traine.
            ("état machine", self._ecrire_etat),
            ("rapport", lambda: self._ecrire_texte(
                self.dossier / "avancement.md", self.rapport())),
            ("tableau", self._ecrire_tableau),
            ("classeur d'itérations", self._ecrire_iterations),
            ("figure d'avancement", self._figure_avancement),
        ]
        if series is not None:
            taches.append(("figure de section",
                           lambda: self._figure_section(*series)))
            taches.append(("figure de convergence",
                           lambda: self._figure_convergence(series[0])))
        for libelle, tache in taches:
            try:
                tache()
            except Exception as e:
                self._consigner(libelle, e)

    def _consigner(self, libelle, exception):
        """Un incident de production est note, jamais propage."""
        self.incidents.append(
            f"{datetime.now():%H:%M:%S} — {libelle} : "
            f"{type(exception).__name__} {exception}")
        try:
            with open(self.dossier / "incidents.log", "a", encoding="utf-8") as f:
                f.write(f"\n{datetime.now():%Y-%m-%d %H:%M:%S} — {libelle}\n")
                f.write(traceback.format_exc())
        except OSError:
            pass

    @staticmethod
    def _ecrire_texte(chemin, texte):
        """Ecriture atomique : le lecteur ne voit jamais un fichier partiel."""
        provisoire = Path(chemin).with_suffix(Path(chemin).suffix + ".tmp")
        provisoire.write_text(texte, encoding="utf-8")
        os.replace(provisoire, chemin)

    @staticmethod
    def _finaliser_atomique(fig, chemin):
        provisoire = Path(chemin).with_suffix(".tmp.png")
        fig.tight_layout()
        fig.savefig(provisoire)
        plt.close(fig)
        os.replace(provisoire, chemin)

    # --- indicateurs -------------------------------------------------------

    def avancement(self):
        """Compte des apports par statut, et fraction achevee."""
        comptes = {s: sum(1 for e in self.etats if e.statut == s)
                   for s in (VALIDE, EN_COURS, ECHOUE, EN_ATTENTE)}
        acheves = comptes[VALIDE] + comptes[ECHOUE]
        return comptes, acheves / max(len(self.etats), 1)

    def temps(self):
        """
        Ecoule, moyenne par apport acheve, et reste estime.

        L'estimation vaut ce que vaut l'hypothese d'apports de cout comparable.
        Elle est neanmoins le seul chiffre qui permette de decider s'il faut
        attendre : mieux vaut un ordre de grandeur explicite qu'aucun repere.
        """
        ecoule = (datetime.now() - self.debut).total_seconds()
        acheves = [e for e in self.etats if e.statut in (VALIDE, ECHOUE)]
        if not acheves:
            return ecoule, None, None
        moyenne = sum(e.duree_s for e in acheves) / len(acheves) or ecoule / len(acheves)
        restants = sum(1 for e in self.etats if e.statut in (EN_ATTENTE, EN_COURS))
        return ecoule, moyenne, moyenne * restants

    # --- sorties -----------------------------------------------------------

    def tableau(self):
        """Tableau d'avancement, une ligne par apport."""
        return pd.DataFrame([{
            "Ordre": i + 1,
            "Apport": e.nom_apport,
            "Section": e.nom_section,
            "Statut": e.statut,
            "Essais": e.essais,
            "Facteur": None if np.isnan(e.facteur) else round(e.facteur, 4),
            "Débit de pointe (% cible)":
                None if np.isnan(e.pic) else round(100 * e.pic, 1),
            "Volume (% cible)":
                None if np.isnan(e.volume) else round(100 * e.volume, 1),
            "Durée (min)": round(e.duree_s / 60.0, 1) if e.duree_s else None,
            "Motif": e.motif,
        } for i, e in enumerate(self.etats)])

    def _ecrire_tableau(self):
        chemin = self.dossier / "avancement.xlsx"
        provisoire = chemin.with_suffix(".tmp.xlsx")
        with pd.ExcelWriter(provisoire, engine="openpyxl") as w:
            self.tableau().to_excel(w, sheet_name="Avancement", index=False)
            valides = [e for e in self.etats if e.diagnostic is not None]
            if valides:
                liv.tableau_de_bord(
                    [e.nom_section for e in valides],
                    [e.diagnostic for e in valides],
                    nb_essais=[e.essais for e in valides],
                ).to_excel(w, sheet_name="Tableau_de_bord", index=False)
        os.replace(provisoire, chemin)

    # --- classeur d'iterations ---------------------------------------------

    def _ecrire_iterations(self):
        """
        Un onglet par apport : ce qui a ete injecte, ce qui a ete mesure a la
        section, et l'ecart, essai par essai.

        C'est la trace de la RECHERCHE, la ou avancement.xlsx ne donne que son
        resultat. Sur un apport qui n'aboutit pas, c'est le seul document qui
        permette de dire pourquoi : on y voit si la pointe plafonne, si le
        volume derive, ou si les essais tournent en rond.

        Les apports pas encore abordes n'ont pas d'onglet — un onglet vide ne
        dit rien et ferait grossir un fichier reecrit a chaque essai.
        """
        import openpyxl

        # LE BLOC RESIDUEL SUFFIT A OUVRIR UN ONGLET. Il est ecrit avant le
        # premier calcul de l'apport — soit une vingtaine de minutes d'attente
        # sur un vrai modele — et il porte deja le deficit a combler et
        # l'apport qui va etre injecte. C'est precisement le moment ou on
        # aimerait le lire.
        avec_essais = [e for e in self.etats
                       if e.essais_detail or e.residuel_detail]
        if not avec_essais:
            return
        classeur = openpyxl.Workbook()
        classeur.remove(classeur.active)
        utilises = set()
        for etat in avec_essais:
            nom = nom_onglet(etat.nom_apport)
            # Deux noms longs peuvent se confondre apres troncature a 31
            # signes. Excel refuserait le doublon et l'ecriture echouerait.
            if nom in utilises:
                suffixe = 2
                while f"{nom[:29]}~{suffixe}" in utilises:
                    suffixe += 1
                nom = f"{nom[:29]}~{suffixe}"
            utilises.add(nom)
            _onglet_iterations(classeur.create_sheet(nom), etat)
        chemin = self.dossier / "iterations.xlsx"
        provisoire = chemin.with_suffix(".tmp.xlsx")
        classeur.save(provisoire)
        os.replace(provisoire, chemin)

    def rapport(self):
        """Note d'avancement, en texte, relisible pendant le calage."""
        comptes, fraction = self.avancement()
        ecoule, moyenne, reste = self.temps()
        n = len(self.etats)

        def duree(secondes):
            return "—" if secondes is None else str(
                timedelta(seconds=int(secondes)))

        lignes = [
            f"# {self.titre} — avancement",
            "",
            f"*Actualisé le {datetime.now():%d/%m/%Y à %H:%M:%S}*",
            "",
            f"**{comptes[VALIDE]} apport(s) validé(s) sur {n}**"
            + (f", {comptes[ECHOUE]} en échec" if comptes[ECHOUE] else "")
            + (", 1 en cours" if comptes[EN_COURS] else "")
            + f" — {100 * fraction:.0f} % achevé",
            "",
            f"- Temps écoulé : {duree(ecoule)}",
            f"- Moyenne par apport : {duree(moyenne)}",
            f"- Reste estimé : {duree(reste)}"
            + ("" if reste is None else
               f" (fin vers {datetime.now() + timedelta(seconds=reste):%H:%M})"),
            "",
            "## Détail",
            "",
        ]
        for i, e in enumerate(self.etats):
            marque = {VALIDE: "[x]", ECHOUE: "[!]",
                      EN_COURS: "[~]", EN_ATTENTE: "[ ]"}[e.statut]
            detail = f"{marque} **{i + 1}. {e.nom_apport} → {e.nom_section}** — {e.statut}"
            if e.essais:
                detail += f", {e.essais} essai(s)"
            if not np.isnan(e.volume):
                detail += f", volume {100 * e.volume:.1f} % de la cible"
                if not np.isnan(e.pic):
                    detail += f", pointe {100 * e.pic:.1f} %"
            if e.duree_s:
                detail += f", {e.duree_s / 60:.0f} min"
            lignes.append(detail)
            if e.motif:
                lignes.append(f"    - {e.motif}")
            if e.diagnostic is not None and e.diagnostic.alertes:
                for a in e.diagnostic.alertes:
                    lignes.append(f"    - alerte : {a}")

        if self.incidents:
            lignes += ["", "## Incidents de production des livrables", "",
                       "*Sans effet sur le calage lui-même.*", ""]
            lignes += [f"- {m}" for m in self.incidents]

        return "\n".join(lignes) + "\n"

    # --- figures -----------------------------------------------------------

    def _figure_avancement(self):
        """
        Deux panneaux : ou en est-on, et la qualite obtenue jusqu'ici.
        C'est la figure que l'on regarde en revenant voir le calcul.
        """
        comptes, fraction = self.avancement()
        ecoule, _, reste = self.temps()
        n = len(self.etats)
        y = np.arange(n)[::-1]

        fig, (ax1, ax2) = plt.subplots(
            1, 2, figsize=(9.2, 0.52 * n + 2.1),
            gridspec_kw={"width_ratios": [3, 2]})

        # Panneau 1 : etat de chaque apport
        for yi, e in zip(y, self.etats):
            largeur = max(e.essais, 0.35)
            ax1.barh(yi, largeur, color=COULEURS[e.statut], height=0.62)
            etiquette = e.statut if e.statut != VALIDE else (
                f"volume {100 * e.volume:.0f} %  pointe {100 * e.pic:.0f} %"
                if not np.isnan(e.volume) and not np.isnan(e.pic) else VALIDE)
            ax1.text(largeur + 0.15, yi, etiquette, va="center", fontsize=8,
                     color=COULEURS[e.statut])
        ax1.set_yticks(y)
        ax1.set_yticklabels([f"{i + 1}. {e.nom_apport}"
                             for i, e in enumerate(self.etats)], fontsize=8.5)
        ax1.set_xlabel("Nombre d'essais")
        ax1.set_xlim(0, max([e.essais for e in self.etats] + [1]) + 2.6)
        ax1.set_title(f"{comptes[VALIDE]} / {n} apports validés "
                      f"— {100 * fraction:.0f} %", loc="left",
                      fontweight="bold")

        # Panneau 2 : ce qui est atteint, en pourcentage de la cible. Deux
        # courbes plutot qu'un indicateur agrege : quand ca derive, on voit
        # tout de suite LAQUELLE des deux grandeurs derive.
        acheves = [(i, e) for i, e in enumerate(self.etats)
                   if not np.isnan(e.volume)]
        if acheves:
            xs = [i + 1 for i, _ in acheves]
            for cle, libelle, couleur in (("volume", "Volume", liv.CALCULE),
                                          ("pic", "Débit de pointe",
                                           liv.CIBLE)):
                valeurs = [100 * getattr(e, cle) for _, e in acheves]
                if not all(np.isnan(v) for v in valeurs):
                    ax2.plot(xs, valeurs, "o-", lw=1.8, color=couleur,
                             label=libelle)
            ax2.set_xticks(range(1, n + 1))
        ax2.axhline(100.0, color=liv.OK, lw=1.4, ls="--", label="cible 100 %")
        ax2.set_xlabel("Rang de l'apport (amont → aval)")
        ax2.set_ylabel("Atteinte de la cible (%)")
        ax2.set_title("Ce qui est atteint", loc="left", fontweight="bold")
        ax2.legend(frameon=False, fontsize=8)

        pied = f"Écoulé {timedelta(seconds=int(ecoule))}"
        if reste is not None:
            pied += (f"   •   reste estimé {timedelta(seconds=int(reste))}"
                     f"   •   fin vers "
                     f"{datetime.now() + timedelta(seconds=reste):%H:%M}")
        pied += f"   •   actualisé à {datetime.now():%H:%M:%S}"
        fig.text(0.5, 0.012, pied, ha="center", fontsize=8.5, color=liv.NEUTRE)
        fig.subplots_adjust(bottom=0.16)
        self._finaliser_atomique(fig, self.dossier / "avancement.png")

    def _figure_section(self, i, series):
        temps_cible, debit_cible, temps_calcule, debit_calcule = series
        e = self.etats[i]
        liv.figure_comparaison(
            e.nom_section, temps_cible, debit_cible, temps_calcule,
            debit_calcule, e.diagnostic,
            self.dossier / f"comparaison_{i + 1:02d}_{assainir_nom_fichier(e.nom_section)}.png")

    def _figure_convergence(self, i):
        e = self.etats[i]
        if len(e.historique) < 2:
            return
        liv.figure_convergence(
            e.nom_section, e.historique,
            self.dossier / f"convergence_{i + 1:02d}_{assainir_nom_fichier(e.nom_section)}.png")


# ---------------------------------------------------------------------------
# Onglet d'iterations
# ---------------------------------------------------------------------------

# Quatre colonnes par essai : ce qu'on a obtenu a la section, LA CIBLE
# DECALEE de -Δt, l'ecart des deux, et ce qu'on avait injecte pour l'obtenir.
COLONNES_PAR_ESSAI = 4


def _onglet_iterations(feuille, etat):
    """
    Ecrit l'onglet d'un apport : recapitulatif, series, et deux graphes.

    LA COLONNE D'ECART EST CELLE DE LA METHODE, ET C'EST UN CORRECTIF. Elle
    portait la difference BRUTE, calcule moins cible ligne a ligne, alors que
    la correction reellement appliquee travaille sur la difference APRES
    neutralisation du decalage (calage.ecart_a_la_cible, § 1.4). Les deux
    n'ont pas le meme ordre de grandeur : mesure sur un cas de recette, ou le
    calcul arrive 0,86 h en avance, la difference brute oscillait entre -105
    et +113 m3/s — un pur dipole de dephasage — quand le deficit reel que la
    boucle cherche a combler tenait entre -18 et +8.

    LE SIGNE SUIT LA METHODE : ecart = cible decalee - section, soit CE QUI
    MANQUE a la section, positif quand il faut ajouter du debit. La colonne
    disait l'inverse (calcule - cible), ce qui ajoutait une inversion de signe
    a l'incoherence de definition.

    C'EST LA CIBLE QUI EST DECALEE DE -Δt, JAMAIS LA SECTION DE +Δt. Les deux
    ecritures donnent la meme courbe translatee de Δt : les valeurs restent
    justes mais tombent au mauvais instant, et l'ecart d'un bloc ne se
    raccorde plus a l'apport du bloc suivant. Releve sur un calage reel le
    07/08/2026 : l'ecart culminait a 13,30 m3/s a t = 12,00 h quand l'apport
    qu'il explique culminait a 13,29 a t = 8,20 h — meme valeur, 3,8 h plus
    loin, ce qui rendait la lecture en escalier impossible.

    Le premier graphe repond a « suis-je a la cible ? » : la cible decalee, la
    section de chaque essai, et l'ecart des deux sur un AXE SECONDAIRE — sans
    quoi un ecart de quelques m3/s serait ecrase par des debits de plusieurs
    centaines et invisible, precisement quand il devient interessant. Le
    second repond a « qu'ai-je injecte pour cela ? ».
    """
    from openpyxl.chart import LineChart, Reference
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter

    essais = etat.essais_detail
    # LE BLOC 0 EST L'ETAT DE DEPART : la section avec l'apport a zero. C'est
    # de SON ecart que sort l'apport injecte a l'essai 1 — le classeur
    # commencait a l'essai 1, et la premiere injection ne se rattachait donc a
    # rien de visible. La lecture se fait desormais en escalier : l'ecart d'un
    # bloc donne l'apport du bloc suivant.
    blocs = ([etat.residuel_detail] if etat.residuel_detail else []) + essais
    if not blocs:
        return
    gras = Font(bold=True)

    feuille["A1"] = f"Apport « {etat.nom_apport} » → section « {etat.nom_section} »"
    feuille["A1"].font = Font(bold=True, size=13)
    feuille["A2"] = (f"{etat.statut} — {len(essais)} essai(s)"
                     + (f" — {etat.motif}" if etat.motif else ""))
    feuille["A2"].alignment = Alignment(wrap_text=False)
    if etat.residuel_detail:
        # LA REGLE DE LECTURE, ECRITE EN CLAIR. Elle se refait a la main ligne
        # a ligne : c'est tout l'objet de ce classeur. Ecrite en A3 et non sur
        # une ligne a elle — la ligne 4 porte l'en-tete du recapitulatif, et
        # decaler le tableau deplacerait tout ce qui se repere par son numero
        # de ligne : series, graphiques, blocs par essai.
        feuille["A3"] = (
            "Lecture en escalier : apport du bloc suivant = max(apport du bloc "
            "+ écart du bloc, 0), ligne à ligne. L'écart vaut « cible décalée "
            "− section », la cible étant décalée du Δt annoncé en tête de sa "
            "colonne — même formule que la correction elle-même.")
        feuille["A3"].alignment = Alignment(wrap_text=False)

    # --- recapitulatif des essais -----------------------------------------
    # « Décalage appliqué » est LE nombre qui rend le classeur verifiable :
    # c'est de celui-la, et pas du decalage du diagnostic, que le calcul est
    # avance avant la soustraction. Les deux sont affiches cote a cote parce
    # qu'ils sont mesures differemment — le diagnostic sur la grille de
    # reechantillonnage, la correction en continu — et qu'un ecart entre eux
    # est en soi une information.
    entetes = ["Essai", "Volume (% cible)", "Pointe (% cible)", "Forme (%)",
               "Décalage diagnostic (h)", "Décalage appliqué (h)"]
    for j, titre in enumerate(entetes, start=1):
        cellule = feuille.cell(row=4, column=j, value=titre)
        cellule.font = gras
    for k, essai in enumerate(essais):
        ligne = 5 + k
        feuille.cell(row=ligne, column=1, value=essai["essai"])
        for j, (cle, facteur) in enumerate(
                (("volume", 100.0), ("pic", 100.0), ("forme", 100.0),
                 ("decalage", 1.0), ("decalage_correction", 1.0)),
                start=2):
            valeur = essai.get(cle)
            feuille.cell(row=ligne, column=j,
                         value=_cellule(None if valeur is None
                                        else float(valeur) * facteur))

    # --- series, une colonne de temps et quatre colonnes par bloc ---------
    entete = 7 + len(essais)
    feuille.cell(row=entete, column=1, value="Temps (h)").font = gras
    feuille.cell(row=entete, column=2, value="Cible (m³/s)").font = gras
    for k, essai in enumerate(blocs):
        base = 3 + COLONNES_PAR_ESSAI * k
        d = float(essai.get("decalage_correction") or 0.0)
        prefixe = ("Résiduel (apports à zéro)" if essai["essai"] == 0
                   else f"Essai {essai['essai']}")
        for rang, libelle in enumerate(
                (f"{prefixe} — section",
                 f"{prefixe} — cible décalée de {-d:+.2f} h",
                 f"{prefixe} — écart (cible décalée − section)",
                 (f"{prefixe} — apport injecté (aucun)" if essai["essai"] == 0
                  else f"Essai {essai['essai']} — apport injecté"))):
            feuille.cell(row=entete, column=base + rang,
                         value=libelle).font = gras

    temps = blocs[0]["temps"]
    for r, instant in enumerate(temps):
        ligne = entete + 1 + r
        feuille.cell(row=ligne, column=1, value=_cellule(instant))
        feuille.cell(row=ligne, column=2, value=_cellule(blocs[0]["cible"][r]))
        for k, essai in enumerate(blocs):
            base = 3 + COLONNES_PAR_ESSAI * k
            # Un essai peut porter une grille differente — un apport n'est pas
            # force d'etre cale sur la meme cible que le premier essai. On ne
            # tronque ni ne devine : hors de sa longueur, la cellule reste vide.
            if r >= len(essai["calcule"]):
                continue
            feuille.cell(row=ligne, column=base,
                         value=_cellule(essai["calcule"][r]))
            # La cible decalee peut sortir de la fenetre de la cible
            # (_sur_grille rend alors NaN, donc une cellule vide), et l'ecart
            # n'existe pas plus qu'elle — on ne le remplace pas par la
            # difference brute, qui serait une autre grandeur sous le meme
            # intitule. Meme regle pour la section hors fenetre calculee.
            decalee = (essai["cible_decalee"][r]
                       if r < len(essai["cible_decalee"]) else None)
            section = essai["calcule"][r]
            feuille.cell(row=ligne, column=base + 1, value=_cellule(decalee))
            manquant = (None if decalee is None or section is None
                        or np.isnan(decalee) or np.isnan(section)
                        else decalee - section)
            feuille.cell(row=ligne, column=base + 2, value=_cellule(manquant))
            if essai["apport"] is not None and r < len(essai["apport"]):
                feuille.cell(row=ligne, column=base + 3,
                             value=_cellule(essai["apport"][r]))

    derniere = entete + len(temps)
    for j in range(1, 3 + COLONNES_PAR_ESSAI * len(blocs)):
        feuille.column_dimensions[get_column_letter(j)].width = 17

    # --- graphes -----------------------------------------------------------
    abscisses = Reference(feuille, min_col=1, min_row=entete + 1,
                          max_row=derniere)

    def serie(chart, colonne):
        chart.add_data(Reference(feuille, min_col=colonne, min_row=entete,
                                 max_row=derniere), titles_from_data=True)

    debits = LineChart()
    debits.title = (f"Section {etat.nom_section} — cible décalée, sections "
                    f"calculées et écarts")
    debits.y_axis.title = "Débit (m³/s)"
    debits.x_axis.title = "Temps (h)"
    debits.height, debits.width = 11, 26
    # LA CIBLE DECALEE, ET LES SECTIONS BRUTES. C'est le couple que la methode
    # compare : elles se superposent quand le calage aboutit. Tracer la cible
    # NON decalee a cote de sections rephasees revenait au meme graphique,
    # translate — mais l'ecart trace au-dessous ne tombait alors pas au meme
    # instant que l'apport qu'il commande.
    serie(debits, 4)
    for k in range(len(blocs)):
        serie(debits, 3 + COLONNES_PAR_ESSAI * k)
    debits.set_categories(abscisses)

    ecarts = LineChart()
    ecarts.y_axis.title = "Écart cible décalée − section (m³/s)"
    # axId distinct et « crosses=max » : la recette openpyxl pour un second axe
    # a droite. Sans le crosses, les deux axes se superposent a gauche.
    ecarts.y_axis.axId = 200
    for k in range(len(blocs)):
        serie(ecarts, 5 + COLONNES_PAR_ESSAI * k)
    ecarts.set_categories(abscisses)
    debits.y_axis.crosses = "max"
    debits += ecarts
    feuille.add_chart(debits, f"A{derniere + 3}")

    injectes = LineChart()
    injectes.title = f"Apport « {etat.nom_apport} » injecté à chaque essai"
    injectes.y_axis.title = "Débit injecté (m³/s)"
    injectes.x_axis.title = "Temps (h)"
    injectes.height, injectes.width = 11, 26
    # Le bloc residuel n'a rien a montrer ici — rien n'y a ete injecte — et une
    # serie vide ferait une legende sans courbe.
    for k in range(len(blocs)):
        if blocs[k]["essai"] != 0:
            serie(injectes, 6 + COLONNES_PAR_ESSAI * k)
    injectes.set_categories(abscisses)
    feuille.add_chart(injectes, f"A{derniere + 26}")


def assainir_nom_fichier(nom):
    """Nom de fichier sur, quel que soit le nom de la section. Public : reutilise
    par calage.py pour nommer les livrables finaux avec les memes regles."""
    return "".join(c if c.isalnum() or c in "-_" else "_"
                   for c in str(nom))[:40]


# ---------------------------------------------------------------------------
# Auto-test : simulation d'un calage complet
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

    from criteres import diagnostiquer

    sortie = Path(tempfile.gettempdir()) / "calage_suivi_test"
    print("=" * 74)
    print("AUTO-TEST DU SUIVI — simulation d'un calage a 4 apports")
    print("=" * 74)
    print(f"\nSorties : {sortie}\n")

    def hydrogramme(t, pic, t_pic=6.0, forme=2.5):
        t = np.maximum(np.asarray(t, dtype=float), 1e-3)
        return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))

    temps = np.linspace(0.01, 36, 400)
    apports = ["Apport_1", "Apport_2", "Apport_3", "Apport_4"]
    sections = ["S1_Amont", "S2_Pont", "S3_Confluence", "S4_Aval"]
    pics = [45.0, 78.0, 112.0, 145.0]
    # Le dernier apport ne converge pas : on veut voir le suivi en situation
    # d'echec autant qu'en situation nominale.
    #
    # Les trois premieres valeurs tiennent dans la tolerance de VOLUME (0,5 %).
    # Elles etaient plus laches quand le verdict reposait sur le KGE >= 0,95,
    # qui admettait plusieurs pourcents d'ecart.
    restitution = [1.002, 0.998, 0.997, 0.930]

    suivi = Suivi(sortie, apports, sections,
                  titre="Calage d'essai")
    fichiers_vus = set()

    for i, (pic, f) in enumerate(zip(pics, restitution)):
        suivi.commencer_apport(i)
        cible = hydrogramme(temps, pic)
        # ETAT DE DEPART, sur le premier apport seulement : c'est de cet
        # ecart-la que sort l'apport injecte a l'essai 1, et le classeur doit
        # le montrer. Les autres apports ne l'enregistrent pas — le classeur
        # doit rester valide dans les deux cas.
        if i == 0:
            suivi.enregistrer_residuel(
                i, (temps, cible), (temps, hydrogramme(temps - 0.4, 0.3 * pic)),
                0.4)
        for essai, facteur in enumerate([1.0, 1.4, 1.6], start=1):
            volume = min(0.62 * facteur, f)
            # Les series de CHAQUE essai : c'est ce que consigne le classeur
            # d'iterations, et le seul moyen de l'eprouver.
            suivi.enregistrer_essai(
                i, facteur, volume,
                pic=min(0.60 * facteur, f),
                series=(temps, cible, temps, hydrogramme(temps - 0.4,
                                                         pic * volume)),
                apport=(temps, hydrogramme(temps, 0.5 * pic * facteur)),
                # Le calcul est cale 0,4 h EN RETARD ci-dessus : le decalage
                # que la correction mesurerait vaut donc +0,4 h, et c'est de
                # celui-la que la cible doit etre decalee.
                decalage_correction=0.4)
        calcule = hydrogramme(temps - 0.4, pic * f)
        diag = diagnostiquer(temps, cible, temps, calcule)
        if diag.converge:
            suivi.valider_apport(i, diag, duree_s=1800 + 300 * i,
                                 series=(temps, cible, temps, calcule))
        else:
            suivi.echouer_apport(i, "concordance non atteinte apres 3 essais",
                                 diag, duree_s=2400)
        comptes, fraction = suivi.avancement()
        _, _, reste = suivi.temps()
        print(f"   apport {i + 1} : {suivi.etats[i].statut:10s} "
              f"volume {100 * diag.rapport_volume:5.1f} % pointe "
              f"{100 * diag.rapport_pic:5.1f} %  ->  "
              f"{100 * fraction:3.0f} % achevé, "
              f"reste estimé {timedelta(seconds=int(reste)) if reste else '—'}")
        fichiers_vus |= {p.name for p in sortie.glob("*")}

    rapport = suivi.terminer()

    print("\n--- FICHIERS PRODUITS ---")
    for p in sorted(sortie.glob("*")):
        print(f"   {p.name:44s} {p.stat().st_size / 1024:7.1f} ko")

    print("\n--- EXTRAIT DU RAPPORT ---")
    print("\n".join(rapport.splitlines()[:14]))

    # --- controles sur les valeurs ----------------------------------------
    print("\n--- CONTROLES ---")
    echecs = []

    def controler(libelle, condition, detail=""):
        print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
              + (f"  ->  {detail}" if detail else ""))
        if not condition:
            echecs.append(libelle)

    tableau = suivi.tableau()
    comptes, fraction = suivi.avancement()
    controler("3 valides et 1 echec", comptes[VALIDE] == 3 and comptes[ECHOUE] == 1,
              f"{comptes}")
    controler("avancement a 100 %", abs(fraction - 1.0) < 1e-9,
              f"{100 * fraction:.0f} %")
    controler("tableau complet", len(tableau) == 4 and tableau["Essais"].min() == 3,
              f"{len(tableau)} lignes")
    controler("motif d'echec consigne",
              bool(tableau.loc[3, "Motif"]), tableau.loc[3, "Motif"])
    controler("aucun incident de production", not suivi.incidents,
              " | ".join(suivi.incidents))

    attendus = ["avancement.md", "avancement.png", "avancement.xlsx",
                "avancement.json", "iterations.xlsx"]
    presents = [f for f in attendus if (sortie / f).exists()]
    controler("livrables de suivi presents", len(presents) == len(attendus),
              str(presents))

    # -----------------------------------------------------------------------
    # CLASSEUR D'ITERATIONS. C'est la trace de la RECHERCHE, la ou le reste ne
    # rapporte que son resultat. On verifie qu'il y a bien un onglet par
    # apport, ses deux graphes, et surtout que la colonne d'ecart dit ce
    # qu'elle annonce : CIBLE MOINS DEBIT REPHASE, sur la meme base de temps.
    # C'est la grandeur que la methode corrige (calage.ecart_a_la_cible) ; la
    # difference brute, qu'on ecrivait avant, en differe d'un facteur dix des
    # que le troncon dephase.
    # -----------------------------------------------------------------------
    import openpyxl

    _cl = openpyxl.load_workbook(sortie / "iterations.xlsx")
    controler("un onglet par apport, dans l'ordre",
              _cl.sheetnames == [nom_onglet(a) for a in apports],
              str(_cl.sheetnames))
    # L'apport 2 n'a PAS d'etat de depart enregistre : son onglet commence
    # donc a l'essai 1, et c'est la forme de reference.
    _f = _cl[nom_onglet(apports[1])]
    controler("deux graphes par onglet : debits et apports injectes",
              len(_f._charts) == 2, f"{len(_f._charts)} graphe(s)")
    _entete = next(r for r in range(1, 40)
                   if _f.cell(row=r, column=1).value == "Temps (h)")
    _titres = [_f.cell(row=_entete, column=j).value
               for j in range(1, 3 + COLONNES_PAR_ESSAI * 3)]
    controler("quatre colonnes par essai, plus temps et cible",
              _titres[:2] == ["Temps (h)", "Cible (m³/s)"]
              and _titres[2].endswith("section")
              and "cible décalée" in _titres[3]
              and _titres[4].endswith("(cible décalée − section)")
              and _titres[5].endswith("apport injecté"), str(_titres[:6]))
    # Le decalage applique est ANNONCE dans l'en-tete de la colonne de cible
    # decalee et dans le recapitulatif : c'est ce qui rend le classeur
    # refaisable a la main. Le calcul est en retard de 0,4 h dans ce cas
    # d'essai, la cible est donc decalee de -0,40 h.
    controler("l'en-tete annonce le décalage appliqué à la cible",
              "-0.40 h" in _titres[3], _titres[3])
    controler("le récapitulatif porte la colonne « Décalage appliqué (h) »",
              _f.cell(row=4, column=6).value == "Décalage appliqué (h)"
              and abs(_f.cell(row=5, column=6).value - 0.4) < 1e-9,
              f"{_f.cell(row=4, column=6).value} = "
              f"{_f.cell(row=5, column=6).value}")
    # (section, cible decalee, ecart) — les trois colonnes d'un bloc d'essai.
    _lignes_pleines = [
        (_f.cell(row=r, column=3).value, _f.cell(row=r, column=4).value,
         _f.cell(row=r, column=5).value)
        for r in range(_entete + 1, _entete + 1 + len(temps))]
    _verifiables = [(s, d, e) for s, d, e in _lignes_pleines
                    if None not in (s, d, e)]
    controler("l'écart consigné vaut bien cible décalée moins section",
              _verifiables
              and max(abs(e - (d - s)) for s, d, e in _verifiables) < 1e-3,
              f"{len(_verifiables)} ligne(s) comparables")
    # ET LA CIBLE EST DECALEE DU BON Δt, DANS LE BON SENS. C'est le controle
    # qui compte : sans lui, on verifierait seulement qu'une soustraction est
    # juste, pas qu'elle porte sur les bonnes series.
    #
    # Le cas d'essai est fait pour trancher : le calcul du premier essai est
    # EXACTEMENT la cible retardee de 0,4 h et multipliee par 0,62. La cible
    # decalee de -0,4 h vaut donc la cible retardee, et le rapport
    # section / cible decalee doit valoir 0,62 A CHAQUE PAS — un rapport
    # constant, qu'aucun decalage absent ou de mauvais signe ne peut produire.
    # Le rapport n'est examine que la ou la crue existe : sous quelques
    # pour-cent du pic, la serie est ecretee a zero par le clamp de
    # hydrogramme(), l'identite « retard pur » n'y tient plus, et diviser par
    # un debit quasi nul ferait exploser un rapport qui ne mesure rien.
    _seuil = 0.05 * max(d for _, d, _ in _verifiables)
    _rapports = [s / d for s, d, _ in _verifiables if d > _seuil]
    controler("le décalage de la cible annule le déphasage : reste un pur "
              "défaut d'amplitude",
              _rapports and max(abs(x - 0.62) for x in _rapports) < 0.01,
              f"section/cible décalée ∈ [{min(_rapports):.4f} ; "
              f"{max(_rapports):.4f}], attendu 0,62")
    # Sans decalage, la colonne porterait la difference brute cible − section :
    # sur ce cas elle est plus etalee que l'ecart d'amplitude reel.
    _brut = [(_f.cell(row=r, column=2).value, s)
             for (s, _, _), r in zip(_lignes_pleines,
                                     range(_entete + 1,
                                           _entete + 1 + len(temps)))]
    _ec_brut = max(abs(c - s) for c, s in _brut if None not in (c, s))
    _ec_decale = max(abs(e) for _, _, e in _verifiables)
    controler("l'écart sur cible décalée est plus petit que la différence "
              "brute",
              _ec_decale < _ec_brut,
              f"brut {_ec_brut:.2f} -> décalé {_ec_decale:.2f} m³/s")
    # -----------------------------------------------------------------------
    # LE BLOC RESIDUEL — l'etat de depart, apport a zero.
    #
    # Sans lui, l'onglet commencait a l'essai 1 et la premiere injection ne se
    # rattachait a rien : on comparait l'ecart RESTANT apres l'essai 1 a
    # l'apport qui l'avait PRECEDE, deux colonnes decalees d'un rang. C'est ce
    # decalage-la qui donnait a croire que « l'apport injecte n'est pas
    # l'ecart a la cible ». Il l'est — mais l'ecart du bloc PRECEDENT.
    # -----------------------------------------------------------------------
    _f0 = _cl[nom_onglet(apports[0])]
    _e0 = next(r for r in range(1, 40)
               if _f0.cell(row=r, column=1).value == "Temps (h)")
    _t0 = [_f0.cell(row=_e0, column=j).value
           for j in range(1, 3 + COLONNES_PAR_ESSAI * 4)]
    controler("le bloc résiduel ouvre l'onglet, avant l'essai 1",
              _t0[2].startswith("Résiduel (apports à zéro)")
              and _t0[5].endswith("(aucun)")
              and _t0[6].startswith("Essai 1"), str(_t0[2:7]))
    controler("le résiduel porte les mêmes quatre colonnes qu'un essai",
              _t0[3].startswith("Résiduel") and "cible décalée" in _t0[3]
              and _t0[4].endswith("(cible décalée − section)"), str(_t0[3:5]))
    # LA CHAINE SE REFAIT A LA MAIN : ecart du bloc 0 -> apport de l'essai 1.
    # Dans ce cas d'essai, le residuel vaut 0,3 fois la cible retardee de
    # 0,4 h ; la cible decalee valant cette meme cible retardee, l'ecart vaut
    # donc 0,7 fois elle, partout.
    _paires = [(_f0.cell(row=r, column=5).value,
                _f0.cell(row=r, column=4).value)
               for r in range(_e0 + 1, _e0 + 1 + len(temps))]
    _paires = [(e, d) for e, d in _paires if None not in (e, d) and d > 1.0]
    controler("l'écart du bloc résiduel est bien cible décalée − résiduel",
              _paires and max(abs(e / d - 0.7) for e, d in _paires) < 0.01,
              f"écart/cible décalée ∈ [{min(e / d for e, d in _paires):.4f} ; "
              f"{max(e / d for e, d in _paires):.4f}], attendu 0,70")
    controler("la règle de lecture en escalier est écrite en clair",
              "escalier" in (_f0["A3"].value or "")
              and "cible décalée" in (_f0["A3"].value or ""),
              (_f0["A3"].value or "")[:110])
    controler("la note ne décale pas le tableau : l'en-tête reste en ligne 4",
              _f0.cell(row=4, column=1).value == "Essai",
              str(_f0.cell(row=4, column=1).value))
    controler("un onglet sans bloc résiduel reste valide",
              _f.cell(row=_entete, column=3).value.startswith("Essai 1"),
              _f.cell(row=_entete, column=3).value)
    # Un onglet SANS mesure de φ ne doit rien inventer.
    controler("sans mesure de φ, rien n'est écrit à son sujet",
              "φ" not in (_f["A3"].value or ""), (_f["A3"].value or "")[:80])

    # HORS DE LA FENETRE CALCULEE, RIEN N'EST INVENTE. Sous HEC-RAS, la serie
    # calculee a sa propre base de temps, qui ne couvre pas toujours celle de
    # la cible. Une valeur prolongee s'y lirait comme une mesure et fausserait
    # la colonne d'ecart aux extremites — la ou l'on regarde justement si le
    # calcul couvre bien la cible.
    _hors = _sur_grille([0.0, 1.0, 2.0, 3.0], [1.0, 2.0], [10.0, 20.0])
    controler("hors de la fenetre calculee, la valeur reste indefinie",
              np.isnan(_hors[0]) and np.isnan(_hors[3])
              and abs(_hors[1] - 10.0) < 1e-9, str(_hors))
    controler("et une valeur indefinie donne une cellule VIDE",
              _cellule(float("nan")) is None and _cellule(2.5) == 2.5)
    controler("un nom d'onglet impossible est assaini",
              nom_onglet("Perimeter 1: BCLine/3") == "Perimeter 1- BCLine-3",
              nom_onglet("Perimeter 1: BCLine/3"))
    controler("un nom d'onglet trop long est tronque a 31 signes",
              len(nom_onglet("A" * 60)) == 31)

    # -----------------------------------------------------------------------
    # L'ETAT MACHINE — c'est lui que le plugin relit toutes les deux secondes.
    # Ce qui compte : qu'il dise TOUJOURS si le calage tourne encore, et
    # qu'il porte le verdict une fois fini. Sans cela, l'affichage ne peut pas
    # distinguer « en cours » de « mort en chemin », et c'est precisement le
    # reproche fait au suivi : le calcul s'arretait sans donner de nouvelles.
    # -----------------------------------------------------------------------
    # -----------------------------------------------------------------------
    # LE VOLUME RAPPORTE EST « rapport_volume ».
    #
    # Ce champ recevait beta, le terme de biais du KGE, calcule sur la grille
    # qui ENGLOBE les deux series. Les deux coincident quand les series
    # partagent leur base de temps — ce que fait le cas ci-dessus, et c'est
    # precisement pour cela qu'il n'a jamais vu le defaut. Sur un cas reel
    # dont la simulation debordait largement la cible, le suivi affichait
    # 261 % la ou le calage lisait 104 %, donnant a croire a une divergence
    # sur un apport parfaitement en route. beta n'existe plus depuis le
    # 07/09/2026 ; ce qui reste a prouver, c'est que le suivi rapporte bien
    # rapport_volume sur une serie calculee DEUX FOIS plus longue que la
    # cible — le cas ou les deux grandeurs divergeaient.
    # -----------------------------------------------------------------------
    _t_cible = np.linspace(0, 24, 200)
    _q_cible = hydrogramme(_t_cible, 100.0)
    _t_long = np.linspace(0, 48, 400)
    _q_long = hydrogramme(_t_long, 100.0)
    _diag_fenetres = diagnostiquer(_t_cible, _q_cible, _t_long, _q_long)

    _suivi_f = Suivi(sortie / "fenetres", ["A"], ["S"])
    _suivi_f.valider_apport(0, _diag_fenetres, duree_s=60)
    _ligne = _suivi_f.tableau().iloc[0]
    controler("le suivi rapporte le VOLUME sur une serie plus longue que la cible",
              abs(_ligne["Volume (% cible)"]
                  - round(100 * _diag_fenetres.rapport_volume, 1)) < 1e-9,
              f"tableau={_ligne['Volume (% cible)']} % "
              f"volume={100 * _diag_fenetres.rapport_volume:.1f} %")
    _etat_f = _suivi_f.etat()["apports"][0]
    controler("l'etat machine rapporte lui aussi le VOLUME",
              abs(_etat_f["volume_pct"]
                  - round(100 * _diag_fenetres.rapport_volume, 1)) < 1e-9,
              f"{_etat_f['volume_pct']} %")

    etat = json.loads((sortie / "avancement.json").read_text(encoding="utf-8"))
    controler("l'etat machine porte les cles attendues",
              {"fraction", "termine", "conforme", "apports", "en_cours",
               "ecoule_s", "reste_s", "pid", "total"} <= set(etat),
              f"{len(etat)} cles")
    controler("un apport y porte son avancement chiffre",
              all({"apport", "statut", "essais", "volume_pct", "pic_pct"}
                  <= set(a) for a in etat["apports"]),
              f"{len(etat['apports'])} apport(s)")

    # BILAN DE MASSE — QUALITE DU CALCUL, PAS ECART A LA CIBLE. Publie parce
    # qu'un calage arrete pour « qualite numerique » n'exposait son chiffre
    # que dans le journal texte, que l'utilisateur du plugin n'ouvre pas.
    _suivi_bilan = Suivi(sortie / "bilan", ["A"], ["S"])
    controler("aucun bilan tant qu'aucun calcul n'a tourne",
              _suivi_bilan.etat()["bilan_masse"] is None)
    _suivi_bilan.noter_bilan_masse(1.119, 5.0)
    _b = json.loads((sortie / "bilan" / "avancement.json")
                    .read_text(encoding="utf-8"))["bilan_masse"]
    controler("le bilan et son seuil sont publies dans l'etat machine",
              _b == {"pct": 1.119, "seuil_pct": 5.0}, str(_b))
    # UN BILAN NON MESURABLE N'EFFACE PAS LE PRECEDENT : on garderait sinon
    # l'ecran vide sans savoir si c'est la mesure ou le calcul qui manque.
    _suivi_bilan.noter_bilan_masse(float("nan"), 5.0)
    controler("un bilan non mesurable laisse le dernier connu en place",
              _suivi_bilan.etat()["bilan_masse"]["pct"] == 1.119,
              str(_suivi_bilan.etat()["bilan_masse"]))
    _suivi_bilan.noter_bilan_masse(None, 5.0)
    controler("un bilan absent ne leve pas d'exception",
              _suivi_bilan.etat()["bilan_masse"]["pct"] == 1.119)

    # LES TROIS GRANDEURS DES L'ESSAI, pas seulement a la validation. Sinon la
    # jauge « Forme » du plugin reste vide pendant toute la recherche, c'est-a
    # -dire pendant les heures ou l'on regarde l'ecran.
    _suivi_essai = Suivi(sortie / "en_cours", ["A"], ["S"])
    _suivi_essai.commencer_apport(0)
    _suivi_essai.enregistrer_essai(0, 1.2, 1.034, 0.937, 0.998, -1.9)
    _a = _suivi_essai.etat()["apports"][0]
    controler("un essai EN COURS rapporte volume, pointe, forme et decalage",
              (_a["volume_pct"], _a["pic_pct"], _a["forme_pct"],
               _a["decalage_h"]) == (103.4, 93.7, 99.8, -1.9),
              f"volume={_a['volume_pct']} pointe={_a['pic_pct']} "
              f"forme={_a['forme_pct']} decalage={_a['decalage_h']}")
    controler("tant qu'aucun verdict n'est rendu, le calage est dit EN COURS",
              etat["termine"] is False and etat["conforme"] is None)

    # -----------------------------------------------------------------------
    # LES COURBES PUBLIEES A L'ECRAN PORTENT LA CIBLE DECALEE, comme le
    # classeur. Publiee brute, elle apparaissait translatee de Δt sous des
    # jauges annoncant 100 % — 3,8 h sur un calage reel — et l'oeil concluait a
    # un calage faux la ou il etait juste.
    #
    # Le cas est fait pour trancher : le calcul est la cible RETARDEE de 0,4 h,
    # donc Δt = +0,4 h. La cible publiee doit voir sa base de temps translatee
    # de +0,4 h, et son pic tomber sur celui de la section — pas 0,4 h avant.
    # -----------------------------------------------------------------------
    _suivi_c = Suivi(sortie / "courbes", ["A"], ["S"])
    _suivi_c.commencer_apport(0)
    _suivi_c.enregistrer_essai(
        0, 1.0, 0.62, series=(temps, hydrogramme(temps, 100.0),
                                    temps, hydrogramme(temps - 0.4, 62.0)),
        decalage_correction=0.4)
    _c = _suivi_c.etat()["courbes"]
    controler("les courbes publiees nomment le decalage employe",
              _c is not None and _c.get("decalage_h") == 0.4,
              str(None if _c is None else _c.get("decalage_h")))
    controler("les courbes publiees nomment l'apport dont elles viennent",
              _c.get("apport") == "A" and _c.get("section") == "S",
              f"{_c.get('apport')} -> {_c.get('section')}")
    _pic_cible = _c["temps_cible"][int(np.argmax(_c["debit_cible"]))]
    _pic_section = _c["temps_calcule"][int(np.argmax(_c["debit_calcule"]))]
    # Les deux series sont sous-echantillonnees independamment : leurs pics
    # respectifs sont conserves, mais tombent sur des instants qui peuvent
    # differer d'un pas. C'est donc au pas d'echantillonnage qu'on juge, pas a
    # une constante — et l'ecart residuel doit rester tres inferieur au Δt de
    # 0,4 h qu'on vient d'annuler.
    _pas = min(b - a for a, b in zip(_c["temps_cible"], _c["temps_cible"][1:]))
    controler("la cible publiee est decalee : son pic tombe sur celui de la "
              "section",
              abs(_pic_cible - _pic_section) <= _pas + 1e-9
              and abs(_pic_cible - _pic_section) < 0.4 / 4,
              f"pic cible {_pic_cible:.2f} h, pic section {_pic_section:.2f} h, "
              f"pas {_pas:.3f} h (Δt annule = 0,40 h)")

    # -----------------------------------------------------------------------
    # LES SECTIONS DEJA CALEES SONT PUBLIEES A PART, pour se tracer derriere la
    # paire courante. Ce qui compte ici : n'y mettre QUE des apports valides —
    # un apport en echec ou en recherche n'a pas d'hydrogramme retenu, et le
    # montrer laisserait croire a un resultat.
    # -----------------------------------------------------------------------
    _suivi_p = Suivi(sortie / "precedentes", ["A1", "A2", "A3"],
                     ["S1", "S2", "S3"])
    _series = (temps, hydrogramme(temps, 100.0),
               temps, hydrogramme(temps, 96.0))
    controler("aucune section calee tant que rien n'est valide",
              _suivi_p.etat()["courbes_precedentes"] == [],
              str(_suivi_p.etat()["courbes_precedentes"]))

    _suivi_p.commencer_apport(0)
    _suivi_p.enregistrer_essai(0, 1.0, 0.96, series=_series)
    _suivi_p.valider_apport(0, diagnostiquer(temps, hydrogramme(temps, 100.0),
                                             temps, hydrogramme(temps, 96.0)))
    _suivi_p.commencer_apport(1)
    _suivi_p.enregistrer_essai(1, 1.0, 0.99, series=_series)
    _p = _suivi_p.etat()["courbes_precedentes"]
    controler("l'apport valide precedent est publie, nomme par sa section",
              len(_p) == 1 and _p[0]["section"] == "S1"
              and _p[0]["apport"] == "A1", str([c["section"] for c in _p]))
    controler("il porte une serie tracable",
              len(_p[0]["temps"]) > 1
              and len(_p[0]["temps"]) == len(_p[0]["debit"]),
              f"{len(_p[0]['temps'])} point(s)")
    controler("elle est allegee plus fort que la courbe courante",
              len(_p[0]["temps"]) <= 91,
              f"{len(_p[0]['temps'])} point(s) pour 90 demandes")
    controler("l'apport EN COURS n'est pas dans les precedentes",
              all(c["section"] != "S2" for c in _p),
              str([c["section"] for c in _p]))

    # UN APPORT EN ECHEC N'EST PAS UN RESULTAT. Il a des series — il a bien
    # calcule — mais aucun hydrogramme retenu.
    _suivi_e = Suivi(sortie / "echoue", ["A1", "A2"], ["S1", "S2"])
    _suivi_e.commencer_apport(0)
    _suivi_e.enregistrer_essai(0, 1.0, 0.5, series=_series)
    _suivi_e.echouer_apport(0, "cible hors d'atteinte")
    _suivi_e.commencer_apport(1)
    _suivi_e.enregistrer_essai(1, 1.0, 0.99, series=_series)
    controler("un apport en ECHEC ne figure pas parmi les sections calees",
              _suivi_e.etat()["courbes_precedentes"] == [],
              str(_suivi_e.etat()["courbes_precedentes"]))
    controler("seule la base de temps est decalee, jamais les debits",
              abs(max(_c["debit_cible"]) - 100.0) < 0.5,
              f"pic publie {max(_c['debit_cible']):.2f} m³/s, attendu 100")

    # ET SURTOUT : QUAND L'APPORT EN COURS N'A RIEN PRODUIT, ON MONTRE LE
    # PRECEDENT. Un apport n'a de series qu'apres l'evaluation de son premier
    # essai, soit ~3 h de calcul HEC-RAS : sans repli, le panneau restait vide
    # pendant exactement les heures ou on le regarde, et sur un calage ou
    # chaque apport converge du premier coup personne ne voyait de courbe.
    _suivi_r = Suivi(sortie / "repli", ["A1", "A2"], ["S1", "S2"])
    _suivi_r.commencer_apport(0)
    _suivi_r.enregistrer_essai(
        0, 1.0, 1.0, series=(temps, hydrogramme(temps, 100.0),
                                  temps, hydrogramme(temps, 99.0)))
    _suivi_r.etats[0].statut = VALIDE
    _suivi_r.commencer_apport(1)            # A2 calcule, rien a montrer encore
    _cr = _suivi_r.etat()["courbes"]
    controler("l'apport en cours sans essai montre le dernier apport chiffre",
              _cr is not None and _cr.get("apport") == "A1",
              "aucune courbe publiee" if _cr is None else _cr.get("apport"))
    _suivi_v = Suivi(sortie / "vierge", ["A1"], ["S1"])
    _suivi_v.commencer_apport(0)
    controler("avant le tout premier essai, rien n'est invente",
              _suivi_v.etat()["courbes"] is None,
              str(_suivi_v.etat()["courbes"]))

    suivi.conclure(False, "deux apports sur quatre non cales", 11)
    etat = json.loads((sortie / "avancement.json").read_text(encoding="utf-8"))
    controler("apres conclure(), le verdict est lisible",
              etat["termine"] is True and etat["conforme"] is False
              and "non cales" in etat["motif_final"]
              and etat["nb_calculs"] == 11,
              f"termine={etat['termine']} conforme={etat['conforme']}")
    controler("l'etat machine est ecrit atomiquement",
              not list(sortie.glob("*.json.tmp")))
    controler("le PID permet de reperer un calage mort",
              etat["pid"] == os.getpid(), str(etat["pid"]))
    controler("figures de section produites",
              len(list(sortie.glob("comparaison_*.png"))) == 3,
              f"{len(list(sortie.glob('comparaison_*.png')))} figure(s)")
    controler("aucun fichier temporaire residuel",
              not list(sortie.glob("*.tmp*")),
              str([p.name for p in sortie.glob('*.tmp*')]))

    # Le suivi ne doit jamais interrompre le calage.
    suivi_casse = Suivi(sortie / "protege", ["A"], ["S"])
    suivi_casse.dossier = Path("Z:/inexistant/impossible")
    try:
        suivi_casse.valider_apport(0, diag, duree_s=10)
        survit = True
    except Exception:
        survit = False
    controler("une defaillance d'ecriture n'interrompt pas le calage",
              survit and bool(suivi_casse.incidents),
              f"{len(suivi_casse.incidents)} incident(s) consigne(s)")

    print()
    if echecs:
        print(f"   {len(echecs)} CONTROLE(S) EN ECHEC : {echecs}")
        raise SystemExit(1)
    print("   Tous les controles passent.")
    print("=" * 74)
