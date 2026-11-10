"""
Page « Aide et configuration » de la fenêtre du plugin : le mode opératoire,
et les deux emplacements du poste — chaîne de calage, interpréteur HEC-RAS —
avec la recherche et l'installation de ce dernier.

Sortie de DialogueParametrage le 10/11/2026 (docs/decoupage_dialogue.md,
phase 3), code déplacé à l'identique. Reste au dialogue ce que d'autres que
cette page emploient : _installation_occupe (le lancement et @avec_sablier
le consultent), _ouvrir_lexique (branché sur les textes de toutes les
étapes), et le sablier, porté par la fenêtre.
"""

from qgis.core import Qgis, QgsApplication
from qgis.PyQt.QtCore import QSettings, Qt, QTimer
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from . import lexique, noyau
from .installation import TacheInstallation, TacheRecherchePython, installation_en_cours
from .interface import Etiquette as QLabel, Manuel as QTextBrowser
from .socle import (ISL_ROUGE, confirmer, dire, formulaire, rendre_la_main,
                    rendre_redimensionnable, sans_sablier, texte_aide, texte_etat)
from .widgets import compte


class PageAide(QWidget):
    """
    Mode operatoire et diagnostic. Le contenu reprend la note
    methodologique : mieux vaut l'avoir sous les yeux au moment d'agir
    qu'a cote, dans un document qu'on n'ouvre pas.

    CE QU'ELLE EMPLOIE DU DIALOGUE, ET RIEN D'AUTRE : la fenetre elle-meme —
    parent de ses boites, et porteuse du sablier que sans_sablier et
    rendre_la_main suspendent (_sablier_pose) — ; sa visibilite (isVisible :
    la fenetre, pas l'onglet) ; _signaler ; _installation_occupe.

    CE QU'ELLE RECOIT A LA CONSTRUCTION, faute de pouvoir importer plugin.py
    qui l'importe : le texte de l'aide (AIDE_HTML reste dans plugin.py, ou
    src/test_lexique.py cherche chaque terme du lexique), journaliser (il
    nomme NOM_PLUGIN, que le banc veut defini dans plugin.py seul) et les
    deux cles de reglage de PluginCalage.
    """

    def __init__(self, dialogue, aide_html, journaliser, cle_chaine, cle_interpreteur):
        super().__init__()
        self._dialogue = dialogue
        self._journaliser = journaliser
        self._cle_chaine = cle_chaine
        self._cle_interpreteur = cle_interpreteur
        self._tache_installation = None
        self._python_en_attente = None
        self._choix_python_ouvert = False
        v = QVBoxLayout(self)
        v.setSpacing(10)

        texte = QTextBrowser()
        # Une ancre « #terme_… » defile jusqu'a l'entree du lexique ; une
        # source s'ouvre dans le navigateur ; le survol d'un terme montre sa
        # definition.
        texte.setOpenExternalLinks(True)
        texte.highlighted.connect(self._survol_aide)
        self.navigateur_aide = texte
        # Le style de l'aide suit la charte, mais ne fixe aucun fond : le
        # QTextBrowser herite ainsi du theme clair ou sombre de QGIS.
        texte.setHtml(
            "<style>"
            "body { line-height: 1.5; }"
            "h2 { margin-bottom: 4px; }"
            "h3 { margin-top: 16px; margin-bottom: 4px; }"
            "p { margin-top: 4px; margin-bottom: 4px; }"
            "li { margin-bottom: 6px; }"
            "</style>" + aide_html)
        texte.setAccessibleName("Mode opératoire du calage des apports")
        texte.setMinimumHeight(240)

        # PARAMETRES DU POSTE.
        #
        # Deux emplacements, et deux seulement. QGIS n'a pas à être désigné :
        # le plugin s'exécute dedans. HEC-RAS non plus : il n'est jamais lancé
        # directement — ras-commander s'en charge, à partir du numéro de
        # version lu dans les fichiers du modèle.
        #
        # Ils sont trouvés tout seuls dans le cas courant. Ce groupe n'existe
        # que pour le cas contraire : sans lui, désigner l'interpréteur
        # supposait de quitter QGIS, modifier une variable d'environnement
        # système et relancer.
        groupe = QGroupBox("Diagnostic et paramètres du poste")
        fp = formulaire(groupe)
        fp.addRow(texte_aide(
            "Les emplacements sont détectés et mémorisés automatiquement. "
            "Vérifiez l’environnement ; renseignez-les seulement s’ils sont absents."))
        bouton = QPushButton("Vérifier l’environnement")
        bouton.clicked.connect(self._diagnostic)
        ligne_diag = QHBoxLayout()
        ligne_diag.addWidget(bouton)
        ligne_diag.addStretch(1)
        fp.addRow(ligne_diag)
        self.label_diagnostic = texte_etat()
        fp.addRow(self.label_diagnostic)

        self.label_chaine = QLabel("")
        self.label_chaine.setWordWrap(True)
        self.label_chaine.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bouton_chaine = QPushButton("Choisir le dossier…")
        bouton_chaine.setToolTip(
            "Dossier contenant criteres.py, geometrie.py, controle_donnees.py, "
            "livrables.py et pont_hecras.py.")
        bouton_chaine.clicked.connect(self._choisir_chaine)
        # LE CHEMIN SUR SA LIGNE, LES BOUTONS DESSOUS (23/10/2026). Cote a
        # cote, un chemin sans espace ne passe pas a la ligne : a 13 pt sur
        # 720 px le groupe exigeait 704 px, la page defilait de 43 px et les
        # boutons etaient rognes. Le chemin reste selectionnable et copiable
        # tel quel (audit CAL-A4) : aucun espace sans chasse n'y est insere.
        ligne_chaine = QHBoxLayout()
        ligne_chaine.addWidget(bouton_chaine)
        ligne_chaine.addStretch(1)
        bloc_chaine = QVBoxLayout()
        bloc_chaine.addWidget(self.label_chaine)
        bloc_chaine.addLayout(ligne_chaine)
        fp.addRow("Chaîne de calage :", bloc_chaine)

        self.label_interpreteur = QLabel("")
        self.label_interpreteur.setWordWrap(True)
        self.label_interpreteur.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        bouton_interp = QPushButton("Choisir un Python…")
        bouton_interp.setToolTip(
            "python.exe d'un environnement disposant de ras-commander et "
            "h5py. C'est lui qui pilote HEC-RAS : QGIS ne peut pas le faire "
            "lui-même, sa bibliothèque HDF5 entre en conflit avec celle de "
            "h5py.")
        bouton_interp.clicked.connect(self._choisir_interpreteur)
        # DÉSIGNER SUPPOSE QU'IL EXISTE DÉJÀ. Sur un poste neuf il n'existe
        # pas, et la seule issue était de taper deux commandes dans une
        # console — ce que le message d'erreur décrivait sans le faire.
        bouton_installer = QPushButton("Installer…")
        bouton_installer.setToolTip(
            "Cherche les Python présents sur ce poste, en propose un, crée "
            "l'environnement HEC-RAS et y installe tout ce qu'il faut, puis "
            "le vérifie. Il n'y a pas besoin de savoir où Python est "
            "installé — c'est ce que ce bouton résout.")
        bouton_installer.clicked.connect(self._installer_interpreteur)
        # « INSTALLER » AVANT « DESIGNER », parce que c'est le geste de celui
        # qui n'a rien : designer suppose de savoir ou chercher, installer non.
        ligne_interp = QHBoxLayout()
        ligne_interp.addWidget(bouton_installer)
        ligne_interp.addWidget(bouton_interp)
        ligne_interp.addStretch(1)
        bloc_interp = QVBoxLayout()
        bloc_interp.addWidget(self.label_interpreteur)
        bloc_interp.addLayout(ligne_interp)
        fp.addRow("Interpréteur HEC-RAS :", bloc_interp)

        self.bouton_installer = bouton_installer
        self._commandes_poste = (bouton_installer, bouton_interp, bouton_chaine, bouton)
        self.progression_installation = QProgressBar()
        self.progression_installation.setRange(0, 0)
        self.progression_installation.setAccessibleName("Installation Python en cours")
        self.progression_installation.hide()
        fp.addRow(self.progression_installation)
        QTimer.singleShot(0, self._reprendre_installation)
        v.addWidget(groupe)
        v.addWidget(texte, 1)
        self._maj_parametres_poste()

    def _survol_aide(self, lien):
        """Survol d'un terme dans l'aide : sa definition en infobulle."""
        lien = lien.toString() if hasattr(lien, "toString") else str(lien)
        t = lexique.terme(lien.partition("#" + lexique.ANCRE)[2])
        if t is None:
            QToolTip.hideText()
        else:
            QToolTip.showText(QCursor.pos(), lexique.definition(t), self.navigateur_aide)

    def _maj_parametres_poste(self):
        """
        Reflete l'etat courant des deux emplacements.

        UN MANQUE DIT LE GESTE QUI LE COMBLE. « introuvable » en rouge est
        un constat, pas une consigne : celui qui decouvre le plugin y lit un
        defaut sans savoir lequel des trois boutons de la ligne le concerne.
        """
        chaine = noyau.trouver_chaine()
        self.label_chaine.setText(
            str(chaine) if chaine
            else f"<span style='color:{ISL_ROUGE}'>introuvable</span> — "
                 f"désignez-la ci-dessous")
        interp = noyau.interpreteur_hecras()
        self.label_interpreteur.setText(
            str(interp) if interp
            else f"<span style='color:{ISL_ROUGE}'>introuvable</span> — "
                 f"cliquez « Installer… », qui trouvera Python tout seul")

    def _choisir_chaine(self):
        dossier = QFileDialog.getExistingDirectory(
            self._dialogue, "Dossier de la chaîne de calage")
        if not dossier:
            return
        if not noyau.definir_chaine(dossier):
            QMessageBox.critical(
                self._dialogue, "Dossier invalide",
                f"« {dossier} » ne contient pas la chaîne de calage.")
            return
        QSettings().setValue(self._cle_chaine, str(dossier))
        self._maj_parametres_poste()

    def _choisir_interpreteur(self):
        """
        Designe l'interpreteur, et ne l'enregistre QUE s'il pilote vraiment
        HEC-RAS. Accepter un python quelconque le ferait echouer au premier
        calcul, apres clonage — plusieurs minutes plus tard, et loin de la
        cause.
        """
        if self._dialogue._installation_occupe():
            return
        chemin, _ = QFileDialog.getOpenFileName(
            self._dialogue, "Interpréteur Python disposant de ras-commander", "",
            "Exécutable Python (python.exe python3.exe python);;"
            "Tous les fichiers (*)")
        if not chemin:
            return
        ok, message = noyau.definir_interpreteur(chemin)
        if ok:
            QSettings().setValue(self._cle_interpreteur, str(chemin))
            self._dialogue._signaler("Interpréteur accepté", message,
                           Qgis.MessageLevel.Success, 12)
        else:
            QMessageBox.critical(
                self._dialogue, "Interpréteur inutilisable",
                f"« {chemin} » ne peut pas piloter HEC-RAS.\n\n{message}\n\n"
                f"Il lui faut ras-commander et h5py. Le python de QGIS ne "
                f"convient pas : sa bibliothèque HDF5 entre en conflit avec "
                f"celle de h5py.")
        self._maj_parametres_poste()

    def _reprendre_installation(self):
        tache = installation_en_cours()
        if tache is not None:
            self._suivre_installation(tache)

    def _suivre_installation(self, tache):
        if self._tache_installation is tache:
            return
        self._tache_installation = tache
        tache.phase.connect(self._phase_installation)
        fin = self._fin_recherche_python if isinstance(tache, TacheRecherchePython) else self._fin_installation
        tache.resultat.connect(fin)
        for bouton in self._commandes_poste:
            bouton.setEnabled(False)
        self.progression_installation.show()
        self._phase_installation(tache.lignes[-1] if tache.lignes else "Installation en attente…")

    def _phase_installation(self, phase):
        if isinstance(self._tache_installation, TacheRecherchePython):
            self.progression_installation.setAccessibleName("Recherche des interpréteurs Python")
            dire(self.label_diagnostic, phase + "\nQGIS reste utilisable. "
                 "La recherche continue si cette fenêtre est fermée. "
                 "Elle peut être annulée dans le gestionnaire de tâches QGIS.")
            return
        self.progression_installation.setAccessibleName("Installation Python en cours")
        dire(self.label_diagnostic, phase + "\nQGIS reste utilisable. "
             "L'installation continue si cette fenêtre est fermée. "
             "Ne quittez pas QGIS ; l'arrêt pendant pip n'est pas proposé.")

    def _detacher_installation(self):
        tache = self._tache_installation
        if tache is not None:
            try:
                tache.phase.disconnect(self._phase_installation)
                fin = self._fin_recherche_python if isinstance(tache, TacheRecherchePython) else self._fin_installation
                tache.resultat.disconnect(fin)
            except (TypeError, RuntimeError):
                pass
            self._tache_installation = None

    def _installer_interpreteur(self):
        """Confirme la cible ; recherche et installation restent hors du fil GUI."""
        if self._choix_python_ouvert:
            return
        if self._python_en_attente is not None:
            self._choisir_python_recherche()
            return
        if self._dialogue._installation_occupe():
            return
        # emplacement_venv_hecras() rend TOUJOURS un chemin depuis le
        # 31/08/2026 : a cote d'une chaine externe si elle existe, dans le
        # dossier de donnees du plugin sinon. Elle rendait None dans ce
        # second cas, et le bouton refusait donc de servir sur un poste neuf
        # — le seul ou il est utile.
        cible = noyau.emplacement_venv_hecras()
        # LA LISTE VIENT DU NOYAU, jamais recopiee ici : c'est elle qui est
        # installée ET vérifiée, et l'annoncer autrement finirait par mentir.
        paquets = [p for _, p in noyau.PAQUETS_HECRAS]
        with sans_sablier(self._dialogue):
            accepte = confirmer(
                self._dialogue, "Installer l'environnement Python HEC-RAS",
                f"Un environnement Python va être créé dans :\n{cible}\n\n"
                f"puis {len(paquets)} paquets y seront installés depuis "
                f"PyPI :\n{', '.join(paquets)}\n\n"
                f"Téléchargement de plusieurs centaines de Mo, plusieurs "
                f"minutes. QGIS restera utilisable. Ne quittez pas QGIS : "
                f"l’arrêt pendant pip n’est pas proposé.",
                oui="Installer", non="Plus tard")
        if not accepte:
            return

        tache = TacheRecherchePython(cible)
        self._suivre_installation(tache)
        QgsApplication.taskManager().addTask(tache)

    def _fin_recherche_python(self, candidats, message, journal):
        cible = self._tache_installation.cible
        self._detacher_installation()
        self.progression_installation.hide()
        for bouton in self._commandes_poste:
            bouton.setEnabled(True)
        dire(self.label_diagnostic, message)
        if candidats is None:
            return  # annulation/erreur : aucun sélecteur ni installation implicite
        self._python_en_attente = (cible, candidats)
        # finished() doit rendre la main au gestionnaire avant une boîte de choix.
        QTimer.singleShot(0, self._choisir_python_recherche)

    def _choisir_python_recherche(self):
        if (self._python_en_attente is None or self._choix_python_ouvert
                or not self._dialogue.isVisible()):
            return
        cible, candidats = self._python_en_attente
        self._python_en_attente = None
        self._choix_python_ouvert = True
        try:
            self._proposer_python(cible, candidats)
        finally:
            self._choix_python_ouvert = False

    def _proposer_python(self, cible, candidats):
        """Choix sur le fil graphique ; la cible confirmée reste inchangée."""
        base = ""
        PARCOURIR = "Parcourir moi-même…"
        if candidats:
            libelles = [
                f"{'.'.join(str(n) for n in c['version'])} — {c['chemin']}"
                + ("   (fourni par QGIS)" if c["origine"] == "QGIS" else "")
                for c in candidats] + [PARCOURIR]
            with sans_sablier(self._dialogue):
                choix, valide = QInputDialog.getItem(
                    self._dialogue, "Python de base",
                    f"{compte(len(candidats), 'interpréteur utilisable trouvé', 'interpréteurs utilisables trouvés')} "
                    f"sur ce poste.\nLe premier est recommandé : un "
                    f"environnement bâti sur le Python de QGIS cesse de "
                    f"fonctionner\nle jour où une montée de version de QGIS "
                    f"remplace son dossier.",
                    libelles, 0, False)
            if not valide:
                return
            if choix != PARCOURIR:
                base = str(candidats[libelles.index(choix)]["chemin"])
        else:
            # RIEN TROUVÉ : ON DIT QUOI FAIRE, au lieu d'ouvrir un sélecteur
            # devant lequel l'utilisateur n'a rien à répondre.
            with sans_sablier(self._dialogue):
                QMessageBox.warning(
                    self._dialogue, "Aucun Python utilisable sur ce poste",
                    "Aucun interpréteur capable de créer un environnement n'a "
                    "été trouvé.\n\n"
                    "Les « python.exe » de WindowsApps n'en sont pas : ce sont "
                    "des fichiers vides dont le seul rôle est d'afficher "
                    "« Python was not found ». Ils occupent le PATH sans rien "
                    "exécuter.\n\n"
                    "Installer Python 3.9 ou plus depuis python.org, en "
                    "cochant « Add python.exe to PATH », puis relancer QGIS. "
                    "Le Python fourni avec QGIS convient aussi : il se trouve "
                    "dans « apps\\Python3xx\\python.exe » de l'installation "
                    "QGIS, et non dans « bin ».")

        if not base:
            with sans_sablier(self._dialogue):
                base, _ = QFileDialog.getOpenFileName(
                    self._dialogue, "Python de base (python.exe) servant à créer "
                          "l'environnement", "",
                    "Exécutable Python (python.exe python3.exe python);;"
                    "Tous les fichiers (*)")
        if not base:
            return

        tache = TacheInstallation(base, cible, self._cle_interpreteur)
        self._suivre_installation(tache)
        QgsApplication.taskManager().addTask(tache)

    def _fin_installation(self, chemin, message, journal):
        self._detacher_installation()
        self.progression_installation.hide()
        for bouton in self._commandes_poste:
            bouton.setEnabled(True)
        self._maj_parametres_poste()
        if chemin is None:
            dire(self.label_diagnostic, f"Installation impossible : {message}")
            self._journaliser(f"Installation de l'interpréteur HEC-RAS : {message}")
            if not self._dialogue.isVisible():
                return  # le journal QGIS conserve le détail ; ne pas rouvrir le dialogue
            boite = QMessageBox(self._dialogue)
            boite.setIcon(QMessageBox.Icon.Critical)
            boite.setWindowTitle("Installation impossible")
            boite.setText("L'environnement Python HEC-RAS n'a pas pu être "
                          "installé.")
            boite.setDetailedText(f"{journal}\n\n{message}")
            rendre_redimensionnable(boite)
            rendre_la_main(self._dialogue)
            # finished() du gestionnaire doit rendre la main sans attendre un clic.
            boite.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            boite.setModal(False)
            boite.show()
            self._erreur_installation = boite
            return

        self._maj_parametres_poste()
        rendre_la_main(self._dialogue)
        dire(self.label_diagnostic,
             f"Interpréteur HEC-RAS installé et vérifié :\n{chemin}\n\n{message}")
        self._dialogue._signaler(
            "Environnement installé",
            f"Interpréteur HEC-RAS installé et vérifié : {chemin}. Retenu "
            f"d'une session à l'autre ; détail sous « Vérifier l’environnement ».",
            Qgis.MessageLevel.Success, 0)

    def _diagnostic(self):
        """
        Etat de l'environnement, et proposition de designer ce qui manque.

        SEUL CHEMIN DE RECUPERATION quand le plugin est installe depuis une
        archive : son dossier parent est alors le repertoire des extensions
        du profil QGIS, qui ne contient ni la chaine ni l'interpreteur.
        """
        if self._dialogue._installation_occupe():
            return
        if noyau.trouver_chaine() is None:
            # QUATRIEME QUESTION OUI/NON SANS DEFAUT, que la relecture du 17/09
            # n'avait pas comptee : meme correctif que les trois autres.
            if confirmer(
                    self._dialogue, "Chaîne de calage introuvable",
                    "Le dossier de la chaîne de calage n'a pas été trouvé.\n\n"
                    "Installé depuis une archive, le plugin ne peut pas le "
                    "deviner : il doit contenir criteres.py, geometrie.py, "
                    "controle_donnees.py, livrables.py et pont_hecras.py.",
                    oui="Désigner le dossier…", non="Plus tard"):
                self._choisir_chaine()

        if noyau.interpreteur_hecras() is None:
            # LE CHEMIN DE SORTIE EST « INSTALLER », PAS « DESIGNER ».
            #
            # Ce message ne proposait QUE de designer, c'est-a-dire d'ouvrir
            # un selecteur de fichier — sur le poste ou l'interpreteur manque,
            # il n'y a precisement rien a y designer. Le bouton « Installer… »
            # existe pour ce cas exact, et le seul chemin de recuperation du
            # plugin ne le mentionnait pas.
            #
            # ET LA RECETTE MANUELLE VIENT DU NOYAU. Elle etait ecrite ici, a
            # DEUX paquets, quand la verification en exige onze : la suivre a
            # la lettre fabriquait un environnement que le plugin refusait
            # ensuite. Elle passe en detail replie — c'est l'issue de secours
            # d'un poste dont la sortie PyPI est fermee a QGIS, pas la voie
            # recommandee.
            boite = QMessageBox(self._dialogue)
            boite.setIcon(QMessageBox.Icon.Question)
            boite.setWindowTitle("Interpréteur HEC-RAS introuvable")
            boite.setText(
                "Le calage a besoin d'un Python séparé de celui de QGIS, et "
                "il n'y en a pas encore sur ce poste.")
            boite.setInformativeText(
                "« Installer » s'en charge de bout en bout : il cherche les "
                "Python présents sur le poste, propose le meilleur, crée "
                "l'environnement et vérifie le résultat.\n\nVous n'avez pas "
                "besoin de savoir où Python est installé.\n\nQGIS ne peut "
                "pas piloter HEC-RAS lui-même : sa bibliothèque HDF5 entre en "
                "conflit avec celle de h5py.")
            boite.setDetailedText(
                "À la main — seulement si ce poste interdit à QGIS de sortir "
                "sur PyPI :\n\n    "
                + "\n    ".join(noyau.recette_installation_manuelle())
                + "\n\npuis désigner ici %USERPROFILE%\\venv-hecras\\"
                  "Scripts\\python.exe.")
            bouton_poser = boite.addButton(
                "Installer…", QMessageBox.ButtonRole.AcceptRole)
            bouton_designer = boite.addButton(
                "Désigner un Python existant…",
                QMessageBox.ButtonRole.ActionRole)
            boite.addButton("Plus tard", QMessageBox.ButtonRole.RejectRole)
            boite.setDefaultButton(bouton_poser)
            rendre_redimensionnable(boite, largeur=700, hauteur=160)
            boite.exec()
            if boite.clickedButton() is bouton_poser:
                self._installer_interpreteur()
            elif boite.clickedButton() is bouton_designer:
                self._choisir_interpreteur()

        disponible, messages = noyau.chaine_disponible()
        resume = ("Utilisable : " + ("oui" if disponible else "NON")
                  + "\n" + "\n".join(messages))
        dire(self.label_diagnostic, resume)
        self._maj_parametres_poste()
        self._dialogue._signaler(
            "Diagnostic",
            "Environnement utilisable." if disponible
            else "Environnement incomplet : le détail est affiché sous le bouton.",
            Qgis.MessageLevel.Success if disponible else Qgis.MessageLevel.Warning)
