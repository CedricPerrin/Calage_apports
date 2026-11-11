"""
Page « 4. Suivi » de la fenêtre du plugin : construction, lecture et peinture.

Sortie de DialogueParametrage le 10/11/2026 (docs/decoupage_dialogue.md,
phase 2), code déplacé à l'identique. Reste au dialogue ce que d'autres que
cette page lisent ou réaffectent : l'état du lancement, le dossier surveillé,
le minuteur (la navigation le démarre et l'arrête) et le filet de
_rafraichir_suivi, qui journalise sous NOM_PLUGIN.
"""

import os
from datetime import datetime, timedelta
from pathlib import Path

from qgis.core import Qgis
from qgis.gui import QgsCollapsibleGroupBox
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFontDatabase, QTextCursor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QProgressBar,
    QPushButton,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import noyau
from .interface import Etiquette as QLabel
from .interface import TableauTriable
from .interface import couleur as couleur_theme
from .socle import (DELAI_PREMIER_ETAT_S, BOUTON_GEOMETRIE, COULEUR_STATUT, ISL_ARDOISE,
                    ISL_ARDOISE_CLAIR, ISL_ROUGE, ISL_TEAL_SOMBRE, ISL_VERT, ROLE_AIDE,
                    TOLERANCE_FORME_DEFAUT, TOLERANCE_PIC_DEFAUT, TOLERANCE_VOLUME_DEFAUT,
                    _cle_fichier, courbe_retenue, date_lisible, dire, duree_lisible,
                    formulaire, texte_aide)
from .widgets import (GLYPHE_STATUT, STATUT_REPRIS, CourbeComparaison, JaugeAtteinte,
                      RubanApports, compte, nombre)


class PageSuivi(QWidget):
    """
    Ce qui se passe pendant le calcul, rafraichi tout seul.

    Le calage tourne dans un processus DETACHE : QGIS n'en sait rien.
    Cet onglet relit le fichier d'etat que suivi.py reecrit a chaque
    essai, et signale de lui-meme la fin, l'echec — et l'interruption,
    qui ne s'annonce pas.

    CE QU'ELLE LIT SUR LE DIALOGUE, ET RIEN D'AUTRE : l'etat du lancement
    (pid_lance, instant_lance, journal_lance), que _lancer_calage et le banc
    reaffectent ; _cle_journal_lu, que le banc remet a None pour forcer une
    relecture ; le classeur ; le dossier surveille et son origine
    (_dossier_suivi, _origine_dossier_suivi, _detail_desaccord_suivi) ;
    _signaler.
    """

    # Ce qui fait qu'une ligne du journal merite l'ecran. Volontairement
    # COURT : tout ce qui est ajoute ici rapproche l'encadre du journal
    # entier, que personne ne lit. « Traceback » y figure parce qu'une pile
    # d'appels annonce toujours un arret, et sa premiere ligne suffit a
    # savoir qu'il y en a une.
    MARQUEURS_ALERTE = ("AVERTISSEMENT", "ARRET", "ERREUR", "ECHEC",
                        "Traceback", "Error:")
    # Le journal d'un calage de quatorze heures pese plusieurs mega-octets :
    # ras-commander y reecrit sa banniere a chaque calcul. On n'en lit que la
    # fin, et l'on n'affiche que les dernieres lignes retenues.
    OCTETS_JOURNAL_LUS = 1_000_000
    LIGNES_ALERTE_MAX = 60
    # LE JOURNAL EN COURS EN MONTRE PLUS QUE LES ALERTES, et pour la meme
    # lecture : c'est un fil qu'on remonte pour comprendre ou le calage en
    # etait, non une liste de motifs. Borne quand meme — un QTextEdit de
    # dix mille lignes se repeint a chaque tour du minuteur.
    LIGNES_JOURNAL_MAX = 400

    def __init__(self, dialogue):
        super().__init__()
        self._dialogue = dialogue
        v = QVBoxLayout(self)
        v.setSpacing(10)

        self.label_suivi_banniere = QLabel()
        self.label_suivi_banniere.setWordWrap(True)
        self.label_suivi_banniere.setTextFormat(Qt.TextFormat.RichText)
        self.label_suivi_banniere.setObjectName("banniereSuivi")
        v.addWidget(self.label_suivi_banniere)

        # LE DOSSIER SURVEILLE, EN PERMANENCE. Il n'etait nomme que dans la
        # branche « Aucun calage suivi » : l'information disparaissait
        # precisement pendant les heures ou cet onglet sert. Le manque mord
        # apres une reprise de classeur, apres une retouche des champs de
        # l'onglet 3 en cours de calcul, ou devant deux calages menes de
        # front — soit chaque fois qu'on peut douter d'ou viennent les
        # chiffres qu'on lit.
        self.label_suivi_dossier = texte_aide("")
        self.label_suivi_dossier.setWordWrap(True)
        self.label_suivi_dossier.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.label_suivi_dossier)

        # ERREURS ET AVERTISSEMENTS, SOUS LA BANNIERE (0.8.4, demande
        # utilisateur). Ils ne vivaient que dans le journal de lancement —
        # un fichier .log dont la banniere donnait le CHEMIN. Un chemin
        # n'est pas un message : le 14/09/2026, un calage repris s'est
        # arrete sur un calcul de reference sans resultats, et les douze
        # avertissements de recadencement des cibles qui le precedaient
        # n'ont jamais paru a l'ecran.
        #   REPLIE PAR DEFAUT, ET DEPLIE TOUT SEUL QUAND QUELQUE CHOSE
        # ARRIVE : un encadre vide et ouvert en permanence apprend a ne plus
        # etre lu.
        self.groupe_alertes = QgsCollapsibleGroupBox(
            "Erreurs et avertissements")
        self.groupe_alertes.setObjectName("grpAlertesSuivi")
        self.groupe_alertes.setToolTip(
            "Les lignes du journal de lancement qui portent un arrêt, une "
            "erreur ou un avertissement. Le journal entier est dans le "
            "dossier de l'Excel des objectifs.")
        va_alertes = QVBoxLayout(self.groupe_alertes)
        self.texte_alertes = QTextEdit()
        self.texte_alertes.setReadOnly(True)
        self.texte_alertes.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.texte_alertes.setMinimumHeight(110)
        va_alertes.addWidget(self.texte_alertes)
        self.groupe_alertes.setCollapsed(True)
        self.groupe_alertes.setVisible(False)
        v.addWidget(self.groupe_alertes)

        # LE JOURNAL TEL QU'IL S'ECRIT (20/09/2026, demande utilisateur).
        # L'encadre ci-dessus ne retient que les lignes portant un mot
        # d'alerte ; celui-ci montre le fil, et c'est lui qui dit OU le
        # calage en etait. Voir _peindre_journal.
        self.groupe_journal = QgsCollapsibleGroupBox("Journal en cours")
        self.groupe_journal.setObjectName("grpJournalSuivi")
        self.groupe_journal.setToolTip(
            "Les dernières lignes du journal de lancement, rafraîchies "
            "pendant le calcul. Le fichier entier est dans le dossier de "
            "l'Excel des objectifs.")
        vj = QVBoxLayout(self.groupe_journal)
        self.texte_journal = QTextEdit()
        self.texte_journal.setReadOnly(True)
        self.texte_journal.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.texte_journal.setMinimumHeight(150)
        self.texte_journal.setAccessibleName("Journal du calage en cours")
        # POLICE A CHASSE FIXE : un journal s'aligne. On demande la famille
        # au systeme plutot que d'en nommer une — « Consolas » n'existe pas
        # partout, et QGIS suit la police du poste.
        self.texte_journal.setFont(
            QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        vj.addWidget(self.texte_journal)
        self.groupe_journal.setCollapsed(True)
        self.groupe_journal.setVisible(False)
        v.addWidget(self.groupe_journal)

        groupe_avancement = QGroupBox("Avancement")
        va = QVBoxLayout(groupe_avancement)
        va.setSpacing(9)
        self.ruban_apports = RubanApports()
        va.addWidget(self.ruban_apports)
        self.barre_suivi = QProgressBar()
        self.barre_suivi.setRange(0, 100)
        self.barre_suivi.setTextVisible(True)
        self.barre_suivi.setFormat("%p %")
        va.addWidget(self.barre_suivi)
        self.label_suivi_position = QLabel("—")
        self.label_suivi_position.setWordWrap(True)
        self.label_suivi_position.setTextFormat(Qt.TextFormat.RichText)
        va.addWidget(self.label_suivi_position)
        v.addWidget(groupe_avancement)

        groupe_jauges = QGroupBox("Atteinte de la cible — dernier essai évalué")
        vj = QVBoxLayout(groupe_jauges)
        vj.setSpacing(10)
        ligne_jauges = QHBoxLayout()
        ligne_jauges.setSpacing(18)
        self.jauges = {}
        for cle, libelle in (("volume_pct", "Volume"),
                             ("pic_pct", "Débit de pointe"),
                             ("forme_pct", "Forme")):
            jauge = JaugeAtteinte(libelle)
            self.jauges[cle] = jauge
            ligne_jauges.addWidget(jauge, 1)
        vj.addLayout(ligne_jauges)
        # LA COURBE SOUS LES JAUGES : les chiffres disent de combien on
        # s'ecarte, le trace dit ou. Un volume excedentaire avec une pointe
        # basse peut venir d'un pic trop faible ou d'une decrue trop longue —
        # deux diagnostics opposes que seule la courbe separe.
        # DE QUEL APPORT viennent les chiffres et les courbes affiches. Ce
        # n'est pas toujours celui qui calcule : tant que son premier essai
        # n'est pas evalue, c'est le dernier apport chiffre qui est montre.
        self.label_jauges = texte_aide("")
        vj.addWidget(self.label_jauges)
        # BILAN DE MASSE DU DERNIER CALCUL — VOISIN DES JAUGES, MAIS PAS UNE
        # QUATRIEME JAUGE. Il ne dit rien de l'atteinte de la cible : c'est
        # la conservation du solveur. Il figure ici parce que c'est lui qui
        # peut faire REJETER un essai avant toute comparaison, et qu'un arrêt
        # « qualité numérique » ne se lisait alors que dans le journal texte.
        self.label_bilan_masse = texte_aide("")
        vj.addWidget(self.label_bilan_masse)
        self.courbe_suivi = CourbeComparaison()
        vj.addWidget(self.courbe_suivi)
        vj.addWidget(texte_aide(
            "Débit à la section de contrôle au dernier essai évalué, face à "
            "l'hydrogramme visé, décalé du Δt de propagation."))
        v.addWidget(groupe_jauges)

        groupe_temps = QGroupBox("Temps")
        ft = formulaire(groupe_temps)
        self.label_suivi_ecoule = QLabel("—")
        self.label_suivi_reste = QLabel("—")
        self.label_suivi_fin = QLabel("—")
        ft.addRow("Écoulé :", self.label_suivi_ecoule)
        ft.addRow("Reste estimé :", self.label_suivi_reste)
        ft.addRow("Fin prévisible :", self.label_suivi_fin)
        ft.addRow(texte_aide(
            "Estimé d'après la durée moyenne des apports déjà achevés. "
            "L'estimation vaut ce que vaut l'hypothèse d'apports de coût "
            "comparable, mais c'est le seul chiffre qui permette de décider "
            "s'il faut attendre."))
        v.addWidget(groupe_temps)

        groupe_detail = QGroupBox("Apports")
        vd = QVBoxLayout(groupe_detail)
        # TRIABLE (27/10/2026, comme Rhoe) : l'ordre du calage, de l'amont
        # vers l'aval, revient au troisieme double-clic.
        self.table_suivi = TableauTriable(0, 6)
        self.table_suivi.setHorizontalHeaderLabels(
            ["Apport", "Section", "Statut", "Essais", "Volume",
             "Pointe"])
        self.table_suivi.horizontalHeader().setToolTip(
            "Double-cliquer sur un en-tête pour classer, une deuxième fois "
            "pour inverser, une troisième pour revenir à l'ordre du calage.")
        self.table_suivi.verticalHeader().setVisible(False)
        self.table_suivi.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_suivi.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.table_suivi.setAlternatingRowColors(True)
        self.table_suivi.setMinimumHeight(150)
        self.table_suivi.horizontalHeader().setStretchLastSection(True)
        vd.addWidget(self.table_suivi)
        v.addWidget(groupe_detail, 1)

        ligne = QHBoxLayout()
        ligne.setSpacing(8)
        bouton_dossier = QPushButton("Ouvrir le dossier de suivi")
        bouton_dossier.clicked.connect(self._ouvrir_dossier_suivi)
        ligne.addWidget(bouton_dossier)
        bouton_figure = QPushButton("Ouvrir la figure d’avancement")
        bouton_figure.setToolTip(
            "La figure produite par la chaîne : état de chaque apport, et "
            "volume et débit de pointe atteints face aux 100 % visés.")
        bouton_figure.clicked.connect(self._ouvrir_figure_suivi)
        ligne.addWidget(bouton_figure)
        ligne.addStretch(1)
        self.label_suivi_maj = QLabel("")
        self.label_suivi_maj.setProperty("role", ROLE_AIDE)
        # Sous la rangee, pas dedans : a 13 pt sur 720 px, a cote de la bande,
        # la rangee faisait defiler l'etape, de 9 px encore avec « Ouvrir la
        # figure d'avancement » et l'heure repliee (23/10/2026).
        self.label_suivi_maj.setWordWrap(True)
        v.addLayout(ligne)
        v.addWidget(self.label_suivi_maj)

    def _ouvrir_dossier_suivi(self):
        dossier = self._dialogue._dossier_suivi()
        if dossier is None or not dossier.is_dir():
            self._dialogue._signaler(
                "Suivi", "Aucun dossier de suivi : renseigner le dossier de "
                f"sortie (étape Paramètres), puis cliquer « {BOUTON_GEOMETRIE} ».",
                Qgis.MessageLevel.Warning)
            return
        os.startfile(str(dossier))  # noqa: S606 (usage Windows assume)

    def _ouvrir_figure_suivi(self):
        dossier = self._dialogue._dossier_suivi()
        figure = (dossier / "avancement.png") if dossier else None
        if figure is None or not figure.is_file():
            self._dialogue._signaler("Suivi", "avancement.png n'existe pas encore : il "
                           "est écrit dès le premier essai.")
            return
        os.startfile(str(figure))  # noqa: S606

    def _banniere(self, couleur, titre, detail="", glyphe=""):
        """
        Bandeau d'etat : fond NEUTRE, filet de couleur, titre colore.

        Un aplat sature sur toute la largeur criait sans rien dire de plus, et
        forcait un texte blanc qui devenait illisible des que QGIS passe en
        theme clair. Ici le fond vient de la palette — il suit donc le theme —
        et la couleur ne sert qu'a marquer : un filet a gauche et le titre.
        C'est la regle que suit tout le reste de la fenetre, et la seule qui
        tienne en theme clair comme en theme sombre.
        """
        # LE FILET SUIT LE THEME COMME LE TITRE (0.8.5) : le titre passe par
        # Etiquette, qui remappe ses couleurs en sombre ; le filet, ecrit dans
        # une feuille de style, ne passait par rien.
        filet = couleur_theme(couleur, self.label_suivi_banniere).name()
        self.label_suivi_banniere.setStyleSheet(
            f"background-color: palette(base);"
            # border: none d'abord : sous Qt 5.15, border-left seul ne dessine
            # rien sur un QLabel (Arche, 13/10/2026 ; revu le 08/11/2026).
            f"border: none; border-left: 5px solid {filet};"
            f"border-radius: 3px; padding: 12px 16px;")
        self.label_suivi_banniere.setText(
            f"<span style='font-size:13pt; font-weight:bold; color:{couleur}'>"
            f"{glyphe + '  ' if glyphe else ''}{titre}</span>"
            + (f"<br><span style='font-size:9pt; color:{ISL_ARDOISE}'>"
               f"{detail}</span>" if detail else ""))

    def _journal_du_calage(self):
        """
        Le journal de lancement le plus recent, ou None.

        CELUI DE LA SESSION D'ABORD — self._dialogue.journal_lance, pose au lancement.
        A defaut, le plus recent a cote de l'Excel des objectifs, la ou
        noyau.lancer_calage les ecrit et ou noyau.dernier_journal sait les
        retrouver : c'est ce qui permet de lire l'echec d'hier apres avoir
        rouvert QGIS.
        """
        if self._dialogue.journal_lance and Path(self._dialogue.journal_lance).exists():
            return Path(self._dialogue.journal_lance)
        if not self._dialogue.classeur:
            return None
        try:
            return noyau.dernier_journal(self._dialogue.classeur)
        except OSError:
            return None

    def _lire_journal(self):
        """
        La queue du journal de lancement : (toutes les lignes, les alertes).

        UNE SEULE LECTURE POUR DEUX VUES — l'encadre des alertes et le
        journal en cours. Les separer en ferait deux, toutes les deux
        secondes, sur un fichier de partage reseau.

        NE LEVE JAMAIS : appelee par le minuteur du suivi, toutes les deux
        secondes, sur un fichier qu'un autre processus est en train d'ecrire.

        ET NE RELIT QUE CE QUI A CHANGE. Un calcul HEC-RAS dure des minutes
        sans qu'une ligne s'ecrive, et le journal est le plus souvent sur un
        partage reseau : relire un mega-octet toutes les deux secondes pour
        n'y rien trouver de neuf, c'est ce que _dossier_suivi evite deja
        pour l'avancement. Meme cle — taille et date —, un stat par tour.
        """
        chemin = self._journal_du_calage()
        if chemin is None:
            return [], []
        try:
            st = os.stat(chemin)
            cle = (str(chemin), st.st_size, st.st_mtime_ns)
            if cle == getattr(self._dialogue, "_cle_journal_lu", None):
                return self._journal_lu, self._alertes_lues
            debut = max(0, st.st_size - self.OCTETS_JOURNAL_LUS)
            with open(chemin, "rb") as f:
                f.seek(debut)
                brut = f.read().decode("utf-8", "replace")
        except OSError:
            return [], []
        lignes = [ligne.rstrip() for ligne in brut.splitlines()]
        if debut:
            del lignes[:1]      # coupee au milieu par la lecture tronquee
        retenues = [ligne for ligne in lignes
                    if any(m in ligne for m in self.MARQUEURS_ALERTE)]
        self._dialogue._cle_journal_lu = cle
        self._journal_lu = lignes[-self.LIGNES_JOURNAL_MAX:]
        self._alertes_lues = retenues[-self.LIGNES_ALERTE_MAX:]
        return self._journal_lu, self._alertes_lues

    def _lignes_alerte(self):
        """Les lignes du journal qui portent un arret, une erreur ou un
        avertissement. Liste vide si le journal manque ou ne dit rien."""
        return self._lire_journal()[1]

    def _peindre_journal(self):
        """
        Le journal de lancement tel qu'il s'ecrit, deroulant, dans la page.

        POURQUOI, ALORS QUE L'ENCADRE DES ALERTES EXISTE (20/09/2026, demande
        utilisateur). Celui-ci ne montre que les lignes qui portent un mot
        d'alerte : ce qui echoue SANS l'un de ces mots n'y parait pas, et
        l'on ne voit pas non plus ou le calage en etait quand il s'est
        arrete. La banniere donnait le chemin du .log — un chemin n'est pas
        un message ; c'est deja ce que la 0.8.4 reprochait au diagnostic.

        REPLIE PAR DEFAUT : on ne lit un journal que lorsqu'on le cherche.
        Il ne se deplie JAMAIS tout seul, a la difference des alertes — un
        journal qui s'ouvre a chaque ligne ecrite rendrait la page sautante
        pendant des heures.

        TOUJOURS DEROULE EN BAS, sauf si l'on a fait defiler soi-meme : la
        derniere ligne est celle qu'on vient lire, mais reprendre la main a
        quelqu'un qui remonte dans l'historique serait pire que de ne rien
        montrer.
        """
        lignes, _ = self._lire_journal()
        self.groupe_journal.setVisible(bool(lignes))
        if not lignes:
            self.texte_journal.setPlainText("")
            return
        chemin = self._journal_du_calage()
        self.groupe_journal.setTitle(
            f"Journal en cours ({len(lignes)} dernières lignes"
            + (f" — {Path(chemin).name}" if chemin else "") + ")")
        texte = "\n".join(lignes)
        if texte == self.texte_journal.toPlainText():
            return
        ascenseur = self.texte_journal.verticalScrollBar()
        colle_en_bas = ascenseur.value() >= ascenseur.maximum() - 2
        self.texte_journal.setPlainText(texte)
        if colle_en_bas:
            self.texte_journal.moveCursor(QTextCursor.MoveOperation.End)
            ascenseur.setValue(ascenseur.maximum())

    def _peindre_alertes(self):
        """Remplit l'encadre des alertes, et l'efface du regard s'il est vide."""
        groupe = self.groupe_alertes
        lignes = self._lignes_alerte()
        groupe.setVisible(bool(lignes))
        if not lignes:
            self.texte_alertes.setPlainText("")
            return
        groupe.setTitle(f"Erreurs et avertissements ({len(lignes)})")
        # SEUL UN CONTENU NOUVEAU DEPLIE, et une seule fois : deplier a
        # chaque tour du minuteur empecherait de replier l'encadre.
        texte = "\n".join(lignes)
        if texte != self.texte_alertes.toPlainText():
            self.texte_alertes.setPlainText(texte)
            self.texte_alertes.moveCursor(QTextCursor.MoveOperation.End)
            if not getattr(self, "_alertes_depliees", False):
                self._alertes_depliees = True
                groupe.setCollapsed(False)

    def _peindre_suivi(self):
        dossier = self._dialogue._dossier_suivi()
        etat = noyau.lire_avancement(dossier) if dossier else None
        # ETAT ILLISIBLE N'EST PAS ETAT ABSENT (11/11/2026). Le fichier est
        # reecrit pendant qu'on le lit ; un antivirus ou un partage reseau
        # peuvent rendre une lecture illisible. noyau.lire_avancement promet
        # alors de « garder l'affichage precedent » — et cette methode faisait
        # le contraire : « Aucun calage suivi », tableau vide, en plein calage.
        #   ON NE GARDE QUE CE QU'ON A PEINT POUR CE DOSSIER, et on LE DIT sous
        # la banniere : un affichage fige sans un mot se lirait comme un calage
        # qui n'avance plus.
        #   UN ETAT ABSENT, LUI, REMET TOUJOURS L'ECRAN A ZERO : une relance
        # archive l'etat avant d'en ecrire un neuf, et ce vide est une
        # information.
        illisible = (etat is None and bool(dossier)
                     and noyau.avancement_illisible(dossier))
        if illisible and getattr(self, "_dossier_peint", None) == dossier:
            self._nommer_dossier_suivi(dossier, illisible="garde")
            return

        perime = self._etat_perime(etat)

        self._nommer_dossier_suivi(dossier,
                                   illisible="dit" if illisible else "")

        if etat is None or perime:
            self._dossier_peint = None
            self._peindre_sans_etat(etat, perime)
            return
        self._dossier_peint = dossier

        apports = etat.get("apports") or []
        en_cours = etat.get("en_cours")
        # LE CALAGE PRECEDENT RESTE A L'ECRAN, DERRIERE CELUI-CI (demande
        # utilisateur, 13/09/2026). Relancer remettait l'onglet a zero :
        # les apports deja cales disparaissaient du ruban et du tableau,
        # leurs hydrogrammes du trace, et rien ne disait qu'ils avaient
        # existe. C'est le plus visible sur une REPRISE, ou le calage en
        # cours ne porte volontairement que les apports restants.
        #   ON NE GARDE QUE CE QUE CE CALAGE NE TRAITE PAS : un apport
        # present dans les deux est celui qu'on refait, et c'est l'etat
        # COURANT qui fait foi pour lui.
        #   ILS N'ENTRENT NI DANS « en_cours », NI DANS LES JAUGES, NI
        # DANS LES COMPTES : le ruban et le tableau les montrent, tout le
        # reste de cette methode continue de ne parler que du calage qui
        # tourne. Melanger les deux ferait lire les chiffres d'hier comme
        # ceux du calcul en cours.
        repris, courbes_reprises = self._apports_repris(dossier, apports)
        self._appliquer_tolerances(etat)
        comptes = etat.get("comptes") or {}
        self._peindre_avancement(etat, apports, en_cours, repris,
                                 courbes_reprises)
        self._peindre_banniere_etat(etat, apports, en_cours, comptes)
        self._peindre_position(etat, apports, en_cours, comptes)
        self._peindre_jauges(apports, en_cours)

        self._afficher_bilan_masse(etat.get("bilan_masse"))

        self._peindre_temps(etat)
        self._remplir_table_suivi(repris + apports)

    def _etat_perime(self, etat):
        """L'etat lu est-il celui d'un calage PRECEDENT ? (verdict « a nous / perime »)"""
        # L'ETAT LU EST-IL CELUI DU CALAGE QU'ON VIENT DE LANCER ? Apres un
        # relancement, le dossier porte encore l'avancement.json du calage
        # PRECEDENT tant que le nouveau n'a pas ecrit le sien : on peignait
        # « Calage terminé — conforme » ou « Calage interrompu » comme reponse
        # au lancement qui venait d'aboutir.
        #
        # C'EST L'HEURE QUI TRANCHE, PAS LE PID — et il a fallu un vrai calage
        # pour le decouvrir (08/09/2026, Q20 sur poste distant). Le PID rendu
        # par Popen n'est PAS celui qui ecrit l'etat des que l'interpreteur
        # HEC-RAS est un RELAIS : un venv cree depuis le Python de QGIS — ce
        # que le bouton « Installer… » propose lui-meme — a un python.exe de
        # 256 ko qui relance le vrai interpreteur dans un AUTRE processus.
        # Mesure : Popen rend 55160, le processus qui tourne est 23284.
        #   Consequence, vue a l'ecran : le suivi refusait d'afficher le calage
        # EN COURS en le prenant pour celui d'avant, pendant toute sa duree.
        #   L'etat est donc a nous s'il a commence APRES notre lancement. La
        # tolerance d'une seconde couvre l'arrondi de « debut », ecrit a la
        # seconde par suivi.py.
        perime = False
        if self._dialogue.instant_lance and etat and etat.get("debut"):
            try:
                debut = datetime.fromisoformat(etat["debut"])
                perime = debut < self._dialogue.instant_lance - timedelta(seconds=1)
            except ValueError:
                # Un « debut » illisible ne doit pas masquer un calage qui
                # tourne : on prefere afficher un etat douteux a ne rien
                # afficher pendant des heures.
                perime = False
        return perime

    def _nommer_dossier_suivi(self, dossier, illisible=""):
        """Le dossier surveille, sous la banniere, a chaque passage ; et, si
        l'etat n'a pas pu etre lu, le fait de le dire (« garde » : l'affichage
        precedent reste ; « dit » : il n'y avait rien a garder)."""
        # LE DOSSIER SURVEILLE EST NOMME A CHAQUE PASSAGE, avant tout test :
        # la branche « Aucun calage suivi » sort plus bas, et c'est elle qui
        # le disait — donc jamais quand un calage tourne. Voir la construction
        # de ce label.
        # LE CHEMIN PEUT PASSER A LA LIGNE APRES CHAQUE SEPARATEUR (23/10/2026) :
        # un espace sans chasse le permet. Sans lui, Qt ne coupe pas un chemin
        # sans espace et la page Suivi defilait de 69 px a 13 pt sur 720 px.
        # Ce texte n'est pas selectionnable ; l'espace ne gene aucune copie.
        coupable = str(dossier).replace("\\", "\\\u200b").replace("/", "/\u200b")
        dire(self.label_suivi_dossier,
             (f"Dossier surveillé ({self._dialogue._origine_dossier_suivi()}) : {coupable}"
              + self._dialogue._detail_desaccord_suivi(dossier)
              + self._mention_etat_illisible(illisible)) if dossier
             else "Aucun dossier de suivi désigné.")

    @staticmethod
    def _mention_etat_illisible(illisible):
        if not illisible:
            return ""
        return ("<br>L'état du calage existe mais n'a pas pu être lu à cette "
                "lecture (fichier en cours d'écriture, antivirus, partage "
                "réseau ou fichier abîmé)"
                + (" : l'affichage précédent est conservé."
                   if illisible == "garde" else "."))

    def _peindre_sans_etat(self, etat, perime):
        """Rien a montrer : pas encore parti, mort au demarrage, ou etat perime."""
        # LE DOSSIER SURVEILLE EST NOMME : un suivi muet parce qu'il
        # regardait le mauvais dossier ne se distinguait en rien d'un
        # calage pas encore parti.
        #
        # ET « PAS ENCORE DEMARRE » SE DISTINGUE DE « MORT AU DEMARRAGE ».
        # Cette branche promettait « quelques secondes après le
        # lancement » POUR TOUJOURS, y compris devant un sous-processus
        # mort avant d'avoir rien ecrit — cas des refus precoces, qui
        # rendent la main avant que suivi.py n'ecrive son premier etat. Et
        # le seul document qui dit pourquoi, le journal de lancement, ne
        # se lisait que dans une boite d'information depuis longtemps
        # fermee.
        titre, glyphe, couleur = "Aucun calage suivi", "·", ISL_ARDOISE_CLAIR
        detail = ("Le suivi apparaît ici dès que le calage écrit son "
                  "premier état, quelques secondes après le lancement.")
        if self._dialogue.pid_lance:
            journal = (f"<br>Journal de lancement : {self._dialogue.journal_lance}"
                       if self._dialogue.journal_lance else "")
            # « MORT AU DEMARRAGE » NE SE PRONONCE PLUS SUR LE PID DE
            # POPEN. Avec un interpreteur-relais, ce processus-la rend la
            # main aussitot apres avoir lance le vrai : le suivi annoncait
            # un calage mort alors qu'il demarrait. On ne conclut donc a la
            # mort que si l'on a laisse au calage le temps d'ecrire —
            # DELAI_PREMIER_ETAT_S — et qu'il n'a toujours rien ecrit.
            depuis = ((datetime.now() - self._dialogue.instant_lance).total_seconds()
                      if self._dialogue.instant_lance else 0.0)
            mort = (noyau.processus_vivant(self._dialogue.pid_lance) is False
                    and depuis > DELAI_PREMIER_ETAT_S)
            if mort:
                titre, glyphe, couleur = (
                    "Calage arrêté sans avoir rien écrit", "✕", ISL_ROUGE)
                detail = (f"Rien n'a été écrit en "
                          f"{int(depuis)} s : le calage est mort au "
                          f"démarrage." + journal)
            else:
                detail = (f"Calage lancé (processus {self._dialogue.pid_lance}) — le "
                          f"suivi apparaît ici dès qu'il écrit son premier "
                          f"état." + journal)
        if perime:
            detail += (f"<br>Le dossier porte encore l'état d'un calage "
                       f"précédent, commencé le {date_lisible(etat.get('debut'))} : il "
                       f"n'est pas affiché, pour ne pas se lire comme "
                       f"celui du calage en cours.")
        # Le dossier surveille n'est plus recopie ici : il vit desormais
        # sous la banniere, a chaque passage.
        self._banniere(couleur, titre, glyphe=glyphe, detail=detail)
        self.barre_suivi.setValue(0)
        self.ruban_apports.actualiser([], None)
        self.courbe_suivi.actualiser(None, None)
        self.label_suivi_position.setText("—")
        self.table_suivi.setRowCount(0)
        for jauge in self.jauges.values():
            jauge.actualiser(None)

    def _apports_repris(self, dossier, apports):
        """(apports, courbes) du calage precedent que celui-ci ne traite pas."""
        repris, courbes_reprises = self._suivi_precedent(dossier)
        noms_courants = {a.get("apport") for a in apports}
        repris = [a for a in repris if a.get("apport") not in noms_courants]
        courbes_reprises = [c for c in courbes_reprises
                            if c.get("apport") not in noms_courants]
        return repris, courbes_reprises

    def _appliquer_tolerances(self, etat):
        """Les tolerances de l'etude, posees sur les jauges."""
        # Les jauges jugent sur LES TOLERANCES DE L'ETUDE, publiees par le
        # suivi. Figees a 2 %, elles coloraient en rouge des valeurs admises
        # par une etude qui en tolere 5.
        # Les defauts sont CEUX DE LA CHAINE, repris des constantes du module :
        # ecrits en dur ici, ils divergeaient — la jauge « Volume » jugeait a
        # 0,5 % ce que la boucle admet a 5 %, et virait au rouge sur un apport
        # parfaitement conforme des que le suivi ne publiait pas ses seuils.
        tolerances = etat.get("tolerances_pct") or {}
        for cle, defaut in (("volume_pct", 100 * TOLERANCE_VOLUME_DEFAUT),
                            ("pic_pct", 100 * TOLERANCE_PIC_DEFAUT),
                            ("forme_pct", 100 * TOLERANCE_FORME_DEFAUT)):
            self.jauges[cle].tolerance = float(
                tolerances.get(cle.replace("_pct", ""), defaut))

    def _peindre_avancement(self, etat, apports, en_cours, repris,
                            courbes_reprises):
        """Barre, ruban des apports et courbe cible / calcule."""
        fraction = float(etat.get("fraction") or 0.0)
        self.barre_suivi.setValue(int(round(100 * fraction)))
        self.ruban_apports.actualiser(
            repris + apports,
            en_cours if en_cours is None else en_cours + len(repris))
        self.courbe_suivi.actualiser(
            etat.get("courbes"),
            courbes_reprises + (etat.get("courbes_precedentes") or []))

    def _peindre_banniere_etat(self, etat, apports, en_cours, comptes):
        """Banniere d'un etat lu : termine, interrompu ou en cours."""
        # BANNIERE : l'etat en un mot, et sa couleur avant meme la lecture.
        if etat.get("termine"):
            if etat.get("conforme"):
                self._banniere(
                    ISL_VERT, "Calage terminé — conforme", glyphe="✔",
                    detail=f"{compte(comptes.get('validé', 0), 'apport calé', 'apports calés')} en "
                    f"{duree_lisible(etat.get('ecoule_s'))}"
                    + (f", {compte(etat['nb_calculs'], 'calcul')}"
                       if etat.get("nb_calculs") else "")
                    + ". Les livrables sont dans le dossier de résultats.")
            else:
                self._banniere(
                    ISL_ROUGE, "Calage terminé — NON conforme", glyphe="✕",
                    detail=etat.get("motif_final")
                    or "voir avancement.md pour le détail.")
        else:
            vivant = noyau.processus_vivant(etat.get("pid"))
            if vivant is False:
                # LE CAS QUI MANQUAIT : plus personne n'ecrit, et rien ne le
                # disait. Le dernier etat connu reste affiche, mais il est
                # annonce comme tel.
                self._banniere(
                    ISL_ROUGE, "Calage interrompu", glyphe="⏹",
                    detail=f"Le processus {etat.get('pid')} n'existe plus et le "
                    f"calage n'a pas rendu de verdict. Dernier état connu "
                    f"ci-dessous ; le journal de lancement dit pourquoi.")
            else:
                nom = (apports[en_cours]["apport"]
                       if en_cours is not None and en_cours < len(apports)
                       else "—")
                self._banniere(
                    ISL_TEAL_SOMBRE, "Calage en cours", glyphe="▶",
                    detail=f"Apport {(en_cours or 0) + 1} sur {etat.get('total')} — "
                    f"{nom}. Mis à jour "
                    f"{etat.get('maj', '')[11:]}.")

    def _peindre_position(self, etat, apports, en_cours, comptes):
        """La ligne « ou en est-on », sous la barre."""
        # Ligne « ou en est-on », la phrase que l'on vient chercher.
        if en_cours is not None and en_cours < len(apports):
            a = apports[en_cours]
            self.label_suivi_position.setText(
                f"<b style='color:{ISL_TEAL_SOMBRE}'>{a['apport']} → "
                f"{a['section']}</b> &nbsp;·&nbsp; essai <b>{a['essais']}</b>"
                f" &nbsp;·&nbsp; apport <b>{a['ordre']}</b> sur "
                f"<b>{etat.get('total')}</b>")
        else:
            self.label_suivi_position.setText(
                f"{compte(comptes.get('validé', 0), 'validé')}, "
                f"{compte(comptes.get('échoué', 0), 'échoué')}, "
                f"{comptes.get('en attente', 0)} en attente")

    def _peindre_jauges(self, apports, en_cours):
        """Les trois jauges, et de quel apport viennent leurs chiffres."""
        # LES JAUGES SE REPLIENT SUR LE DERNIER APPORT CHIFFRE. Un apport dont
        # le premier essai n'est pas encore evalue — soit toute la duree de son
        # calcul HEC-RAS, environ trois heures — n'a aucun chiffre a montrer :
        # les trois jauges restaient donc vides pendant exactement les heures
        # ou on les regarde. Le repli dit de QUEL apport il s'agit, sans quoi
        # on lirait les chiffres du precedent comme ceux du calcul en cours.
        montre = (apports[en_cours]
                  if en_cours is not None and en_cours < len(apports)
                  and apports[en_cours].get("volume_pct") is not None
                  else next((a for a in reversed(apports)
                             if a.get("volume_pct") is not None), None))
        for cle, jauge in self.jauges.items():
            jauge.actualiser(montre.get(cle) if montre else None)
        self.label_jauges.setText(
            "en attente du premier essai" if montre is None
            else (f"<b>{montre['apport']} → {montre['section']}</b>, essai "
                  f"{montre['essais']}"
                  + ("" if en_cours is not None
                     and en_cours < len(apports)
                     and montre is apports[en_cours]
                     else " — dernier essai évalué ; le calcul en cours n'a "
                          "pas encore rendu le sien")))

    def _peindre_temps(self, etat):
        """Ecoule, reste estime, fin previsible et heure de mise a jour."""
        self.label_suivi_ecoule.setText(duree_lisible(etat.get("ecoule_s")))
        self.label_suivi_reste.setText(
            "—" if etat.get("termine") else duree_lisible(etat.get("reste_s")))
        fin = etat.get("fin") or etat.get("fin_prevue")
        self.label_suivi_fin.setText(
            date_lisible(fin) if fin else "—")
        self.label_suivi_maj.setText(
            f"actualisé {etat.get('maj', '')[11:]}"
            + (f" · {compte(etat['incidents'], 'incident')}"
               if etat.get("incidents") else ""))

    def _suivi_precedent(self, dossier):
        """
        Ce que le calage PRECEDENT a obtenu, tel que l'ecran doit le garder.

        Rend (apports, courbes) : les apports qu'il a VALIDES, marques
        « repris », et les hydrogrammes retenus a leurs sections, marques
        « anterieur ». Deux listes vides quand il n'y a pas d'archive — le cas
        du premier calage.

        L'appelant retire ensuite ceux que le calage EN COURS traite : c'est
        lui qui sait lesquels, et les garder en double ferait un ruban ou le
        meme apport apparait deux fois.

        RELU SEULEMENT QUAND L'ARCHIVE CHANGE, c'est-a-dire au demarrage d'un
        calage et jamais ensuite. Cette methode est appelee toutes les deux
        secondes tant que l'onglet est a l'ecran, et le dossier de suivi est le
        plus souvent sur un partage reseau — meme raison que _dossier_suivi.
        """
        if not dossier:
            return [], []
        chemin = Path(dossier) / noyau.ETAT_SUIVI_PRECEDENT
        cle = _cle_fichier(chemin)
        cache = getattr(self, "_archive_suivi", None)
        if cache is None or cache[0] != cle:
            cache = (cle, noyau.lire_avancement(dossier,
                                                noyau.ETAT_SUIVI_PRECEDENT))
            self._archive_suivi = cache
        etat = cache[1]
        if not etat:
            return [], []
        apports = [dict(a, statut=STATUT_REPRIS)
                   for a in (etat.get("apports") or [])
                   if a.get("statut") == "validé"]
        noms = {a.get("apport") for a in apports}
        derniere = courbe_retenue(etat.get("courbes"))
        courbes = [dict(c, anterieur=True)
                   for c in list(etat.get("courbes_precedentes") or [])
                   + ([derniere] if derniere else [])
                   if c.get("apport") in noms]
        return apports, courbes

    def _afficher_bilan_masse(self, bilan):
        """
        Bilan de masse du dernier calcul, sous les jauges.

        TROIS ETATS, ET LE TROISIEME COMPTE AUTANT QUE LES DEUX AUTRES :
        pas encore mesuré (aucun calcul n'a rendu la valeur), dans le seuil,
        au-delà du seuil. Le dernier explique à lui seul un calage qui
        s'arrête sans qu'aucune jauge n'ait bougé.

        Un état publié par une version ANTERIEURE du suivi n'a pas la clé :
        la ligne reste alors vide plutôt que d'annoncer une mesure absente.
        """
        if not isinstance(bilan, dict):
            self.label_bilan_masse.setText("")
            return
        try:
            pct = float(bilan["pct"])
            seuil = float(bilan["seuil_pct"])
        except (KeyError, TypeError, ValueError):
            self.label_bilan_masse.setText("")
            return
        depasse = abs(pct) > seuil
        couleur = ISL_ROUGE if depasse else ISL_VERT
        self.label_bilan_masse.setText(
            f"Bilan de masse du dernier calcul : "
            f"<b style='color:{couleur}'>{nombre(pct, 3, signe=True)} %</b> "
            f"(seuil {format(seuil, 'g').replace('.', ',')} %)"
            + (" — au-delà du seuil : l'essai est rejeté sans être comparé "
               "à la cible. Resserrer le pas de calcul du plan."
               if depasse else
               " — qualité du calcul, pas écart à la cible."))

    def _remplir_table_suivi(self, apports):
        self.table_suivi.setRowCount(len(apports))
        for ligne, a in enumerate(apports):
            statut = a.get("statut", "")
            valeurs = [
                a.get("apport", ""), a.get("section", ""),
                f"{GLYPHE_STATUT.get(statut, '')}  {statut}",
                str(a.get("essais") or ""),
                "—" if a.get("volume_pct") is None else f"{nombre(a['volume_pct'])} %",
                "—" if a.get("pic_pct") is None else f"{nombre(a['pic_pct'])} %",
            ]
            for colonne, valeur in enumerate(valeurs):
                cellule = QTableWidgetItem(str(valeur))
                if colonne == 2:
                    # Remappee en theme sombre, comme les widgets peints :
                    # l'ardoise sur le fond Night Mapping rendait 2,3:1.
                    cellule.setForeground(couleur_theme(
                        COULEUR_STATUT.get(statut, ISL_ARDOISE), self.table_suivi))
                    police = cellule.font()
                    police.setBold(True)
                    cellule.setFont(police)
                if colonne >= 3:
                    cellule.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table_suivi.setItem(ligne, colonne, cellule)
        self.table_suivi.reclasser()
        self.table_suivi.resizeColumnsToContents()
