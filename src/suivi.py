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

# LES DEUX ETATS MACHINE DU DOSSIER DE SUIVI : celui du calage en cours,
# et celui du calage PRECEDENT, archive par renommage au demarrage du
# suivant (voir Suivi.__init__). Le plugin porte les memes noms dans
# noyau.ETAT_SUIVI_COURANT et ETAT_SUIVI_PRECEDENT — le Python de QGIS ne
# peut pas importer ce module, et toute correction va donc aux deux.
ETAT_COURANT = "avancement.json"
ETAT_PRECEDENT = "avancement_precedent.json"

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
    # VALIDE SUR L'OBJECTIF DEGRADE (calage.Configuration.degradation_
    # objectif). Le statut reste « validé » : la reprise et les courbes
    # traitent l'apport comme cale. C'est ce drapeau qui le met en orange, et
    # « motif » dit de combien il s'ecarte.
    degrade: bool = False
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
        self.degrade = False
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
        # LE SUIVI DU CALAGE PRECEDENT EST ARCHIVE, PAS EFFACE (demande
        # utilisateur, 13/09/2026). Relancer — pour reprendre a un
        # apport, ou pour tout refaire apres avoir change un reglage —
        # ecrasait avancement.json : l'onglet Suivi repartait de zero, et
        # ce qui avait ete obtenu la veille n'existait plus nulle part.
        # Il vit desormais a cote, sous un nom fixe, et l'affichage trace
        # le calage en cours PAR-DESSUS.
        #   UN SEUL NIVEAU D'HISTORIQUE : le troisieme calage remplace
        # l'archive du deuxieme. Garder une pile obligerait a choisir
        # lequel montrer, et ce qu'on veut voir est CE QUI PRECEDE.
        #   UN RENOMMAGE, PAS UNE COPIE : le plugin relit ce fichier
        # toutes les deux secondes, et Path.replace est atomique — il ne
        # peut donc pas etre surpris a mi-chemin.
        ancien = self.dossier / ETAT_COURANT
        if ancien.exists():
            try:
                ancien.replace(self.dossier / ETAT_PRECEDENT)
            except OSError as e:                            # noqa: BLE001
                self._consigner("archivage du suivi précédent", e)
        # Un etat est ecrit DES LA CONSTRUCTION : entre le lancement et le
        # premier calcul il peut s'ecouler plusieurs minutes (clonage,
        # pretraitement), et sans lui l'affichage resterait vide en laissant
        # croire que rien n'a demarre.
        try:
            self._ecrire_etat()
        except Exception as e:                              # noqa: BLE001
            self._consigner("état machine initial", e)

    # --- evenements --------------------------------------------------------

    def noter_bilan_non_lu(self, cause, seuil_pct):
        """
        La lecture du bilan de masse a echoue : l'essai est accepte mais non
        controle, et l'etat machine le dit (cle « non_lu », cause lue).
        Decision du 21/11/2026. Le bilan precedent est remplace : il ne vaut
        pas pour ce calcul.
        """
        self.bilan_masse = {"pct": None, "seuil_pct": float(seuil_pct),
                            "non_lu": str(cause)}
        try:
            self._ecrire_etat()
        except Exception as e:                              # noqa: BLE001
            self._consigner("état machine (bilan de masse non lu)", e)

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

    def valider_apport(self, i, diagnostic, duree_s=0.0, series=None,
                       motif_degrade=""):
        """
        L'apport i est valide et fige. C'est ici que le rapport complet est
        reecrit.

        series : (temps_cible, debit_cible, temps_calcule, debit_calcule) pour
        produire la figure de comparaison de la section. Facultatif.
        motif_degrade : non vide quand l'apport n'est retenu que sur
        l'objectif degrade ; il dit de combien et pourquoi.
        """
        etat = self.etats[i]
        etat.statut = VALIDE
        etat.degrade = bool(motif_degrade)
        etat.motif = motif_degrade or ""
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

    def conclure(self, conforme, motif="", nb_calculs=None, degrade=False):
        """
        Verdict final, ecrit dans l'etat machine.

        SANS CE POINT, RIEN NE DISTINGUE UN CALAGE FINI D'UN CALAGE MORT : les
        fichiers de suivi cessent simplement d'etre reecrits, et celui qui
        regarde ne sait pas s'il doit attendre encore ou s'il s'est passe
        quelque chose. C'est ce qui manquait.
        """
        self.conforme = bool(conforme)
        # Ni conforme ni en echec : mene au bout, sur l'objectif degrade.
        self.degrade = bool(degrade) and not self.conforme
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
            "degrade": self.degrade,
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
                "degrade": e.degrade,
            } for i, e in enumerate(self.etats)],
        }

    def _ecrire_etat(self):
        """
        Ecrit avancement.json, atomiquement comme le reste : il est relu
        toutes les deux secondes pendant qu'il est reecrit.
        """
        chemin = self.dossier / ETAT_COURANT
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
        degrades = sum(1 for e in self.etats if e.degrade)

        def duree(secondes):
            return "—" if secondes is None else str(
                timedelta(seconds=int(secondes)))

        lignes = [
            f"# {self.titre} — avancement",
            "",
            f"*Actualisé le {datetime.now():%d/%m/%Y à %H:%M:%S}*",
            "",
            f"**{comptes[VALIDE]} apport(s) validé(s) sur {n}**"
            + (f", dont {degrades} sur l'objectif dégradé" if degrades else "")
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
            detail = (f"{marque} **{i + 1}. {e.nom_apport} → {e.nom_section}** — "
                      f"{e.statut}" + (", objectif dégradé" if e.degrade else ""))
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
            # ORANGE pour un apport retenu sur l'objectif degrade, et le mot
            # avec lui : la couleur ne porte jamais seule le sens.
            couleur = liv.ALERTE if e.degrade else COULEURS[e.statut]
            ax1.barh(yi, largeur, color=couleur, height=0.62)
            etiquette = e.statut if e.statut != VALIDE else (
                f"volume {100 * e.volume:.0f} %  pointe {100 * e.pic:.0f} %"
                if not np.isnan(e.volume) and not np.isnan(e.pic) else VALIDE)
            if e.degrade:
                etiquette += " — objectif dégradé"
            ax1.text(largeur + 0.15, yi, etiquette, va="center", fontsize=8,
                     color=couleur)
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
    from openpyxl.styles import Font

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

    _en_tete_onglet(feuille, etat, essais)

    _recapitulatif_essais(feuille, essais, gras)

    # --- series, une colonne de temps et quatre colonnes par bloc ---------
    entete = 7 + len(essais)
    _en_tetes_series(feuille, blocs, entete, gras)

    temps = blocs[0]["temps"]
    _series_par_bloc(feuille, blocs, entete, temps)

    derniere = entete + len(temps)
    _largeurs_iterations(feuille, blocs)

    _graphes_iterations(feuille, etat, blocs, entete, derniere)


def _en_tete_onglet(feuille, etat, essais):
    """Lignes 1 a 3 de l'onglet : l'apport, son statut, la regle de lecture."""
    from openpyxl.styles import Alignment, Font

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


def _recapitulatif_essais(feuille, essais, gras):
    """Le recapitulatif, ligne 4 et suivantes : une ligne par essai."""
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


def _en_tetes_series(feuille, blocs, entete, gras):
    """La ligne d'en-tete des series : temps, cible, quatre colonnes par bloc."""
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


def _series_par_bloc(feuille, blocs, entete, temps):
    """Les valeurs des series, une ligne par instant de la grille du bloc 0."""
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


def _largeurs_iterations(feuille, blocs):
    """Largeur de toutes les colonnes ecrites."""
    from openpyxl.utils import get_column_letter

    for j in range(1, 3 + COLONNES_PAR_ESSAI * len(blocs)):
        feuille.column_dimensions[get_column_letter(j)].width = 17


def _graphes_iterations(feuille, etat, blocs, entete, derniere):
    """Les deux graphes de l'onglet, sous les series."""
    from openpyxl.chart import LineChart, Reference

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
    # Le banc vit dans src/bancs/ depuis le 10/11/2026 : l'archive du plugin
    # ne l'embarque pas. Dans le depot, ce relais le joue a l'identique.
    import runpy
    import sys
    from pathlib import Path

    _banc = (Path(__file__).resolve().parent / "bancs"
             / "banc_suivi.py")
    if not _banc.is_file():
        print("Le banc d'auto-test n'est pas livre avec cette installation.",
              file=sys.stderr)
        raise SystemExit(2)
    runpy.run_path(str(_banc), run_name="__main__")
