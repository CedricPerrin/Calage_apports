# CHECKPOINT — Calage des apports (ISL Ingénierie)

## Reprendre ici — 20 septembre 2026 : 0.9.0, trois demandes utilisateur

Cinq onglets, la reprise annoncée avant le clic, les paramètres hors du
classeur. **Banc QGIS rejoué sur le poste** (`C:\Program Files\QGIS\LTR`) :
**297 contrôles, aucun échec** — c'est le premier passage depuis la 0.8.4, et
il solde la dette « banc non rejoué » qui traînait depuis le 17 septembre.

- **L'onglet « Sorties » disparaît.** Ses groupes rejoignent « Lancer », après
  « Apports à déterminer » ; le préfixe de scénario quitte « Objectifs » pour
  se poser au-dessus du bouton. L'ordre de la page est celui de la décision, et
  c'est l'ordre que le banc éprouve.
- **Un récapitulatif au-dessus du bouton** dit d'où le calage repart, de quel
  plan d'étape — nommé avec son préfixe —, ce qui est tenu pour calé et ce qui
  sera calculé. La boîte de reprise ne s'ouvrait pas après un **échec** : rien
  n'étant « validé » en aval, rien ne se perdait, donc rien ne se disait.
- **Les paramètres quittent l'Excel** pour `<nom du classeur>.json`, porté par
  un module unique, `src/parametres.py` (chaîne à 10 modules). Un classeur
  d'avant est encore lu par sa feuille — vérifié sur le classeur réel
  d'Aran-Q100 : 40 paramètres, contrôle sans erreur.

Par quoi reprendre : (1) **regarder la fenêtre** — rien n'a été vu à l'écran,
tout est mesuré au banc ; (2) **refaire les six captures**
(`captures_plugin.py`), celle dite « onglet 2 Sorties » montrant un onglet
disparu ; (3) mesurer « Lancer » **rempli** à 13 pt sur petite fenêtre — sept
groupes désormais ; (4) **instruire les six échecs du banc avec `--modele`**,
reproduits à l'identique sur le commit précédent : ils sont antérieurs à ce
chantier ; (5) installer le ZIP **0.9.0** dans le profil ISL et relancer le
calage Aran-Q100 (son classeur n'a pas de JSON : c'est le chemin de
compatibilité qui servira) ; (6) `pont_hecras.py autotest` sur le poste ;
(7) la [PR #4](https://github.com/CedricPerrin/Calage_apports/pull/4), toujours
bloquée par une CI sans exécuteur.

## Complément préparé, non intégré — 20 septembre 2026

La [PR #4](https://github.com/CedricPerrin/Calage_apports/pull/4) déplace aussi la
recherche initiale des interpréteurs dans une tâche QGIS : progression, annulation
entre sondes, cible figée et choix au retour du dialogue. Noyau et deux tests de
cible/recherche passent localement. Trois scénarios natifs sont ajoutés.
**Ce complément n’est pas dans main** : les nouveaux jobs [QGIS et noyau](https://github.com/CedricPerrin/Calage_apports/actions/runs/35511883676)
s’arrêtent avant attribution d’un exécuteur, sans étape exécutée. Leur cause n’est
pas exposée par le connecteur ; le navigateur disponible n’est pas connecté.
Le propriétaire GitHub doit rendre l’annotation accessible ou transmettre son texte.
Le mainteneur/Codex relance les tests, corrige si nécessaire, puis fusionne la PR.
La fusion est déjà autorisée ; aucun nouveau choix technique n’est demandé à
l’ingénieur. La recherche de main demeure synchrone tant que cette validation manque.

Point de reprise pour ouvrir une nouvelle conversation avec un contexte
minimal. L'état courant et les règles en vigueur restent dans `STATUT.txt` ;
ce fichier ne dit que **où on en est** et **par quoi reprendre**.

## Reprendre ici — 20 septembre 2026 : intégration des lots UX B/C

L’utilisateur demande la fusion de la PR #3 dans `main`. La recette se fait depuis ces sources, avec les preuves et responsables de `docs/UX_ISL.md`. L’exécution par lots autorise C9 et C16. Les effets du contrôle sont visibles ; création du venv, pip et vérification passent par `QgsTask`. La cible confirmée est figée et la préférence Python n’est publiée qu’après succès. Voir [implémentation, bancs et limites](docs/UX_ISL.md).

La recette automatisée est maintenant verte : noyau complet ; QGIS 3.44.7 / Qt 5.15.13, quatre tests du gestionnaire/cycle, quatre tests cible/worker et 299 contrôles du banc historique. Les phases pip sont simulées, le gestionnaire et les widgets sont réels. Dix correspondances ISL sont contrôlées en CI. Voir `docs/UX_ISL.md` pour le lien de preuve et la portée du harnais Linux (sonde PID POSIX, pas tasklist Windows).

Prochaine étape : recette sur le poste Windows ISL, installation réelle via son réseau, DPI/thèmes/lecteur d’écran et modèle représentatif. Aucun nouveau ZIP de diffusion avant cette recette ; aucun calcul métier ni archive 0.8.6 remplacé. Nouveaux fichiers : workflow `.github/workflows/ux-qgis.yml`, test `src/test_installation_qgis.py`, contrôle `tools/check_isl_identity.py` et contrat `docs/isl-identity-contract.json` ; banc historique rendu reproductible sous Linux.

## État précédent — 18 septembre 2026 (suite) : 0.8.6, la revue de qualité fusionnée

La branche `claude/ponytail-lycxeg` (revue de qualité de la 0.8.4, 17/09) est
fusionnée dans `main` — merge `e402072` — et l'archive refaite sous un nom
neuf, `calage_apports_0.8.6.zip` : la 0.8.5 était déjà sur GitHub, et une
archive dont le contenu change porte un autre nom. Aucune promesse ne change.

**Bancs :** `noyau.py` vert ici ; `pilote_hecras.py` s'arrête à l'import de
`ras-commander`, absent de ce clone ; `faire_zip.py` conforme, garde-fou vert ;
**banc QGIS toujours non rejoué**.

Par quoi reprendre : (1) **rejouer `test_plugin_qgis.py`** — 301 contrôles
attendus, dont trois de la revue et vingt-trois de la 0.8.5 jamais vus sous
QGIS ; (2) `pont_hecras.py autotest` sur le poste ; (3) installer le ZIP
**0.8.6** dans le profil ISL ; (4) le reste de la liste de la 0.8.5
ci-dessous — Night Mapping avec un Suivi rempli, captures, Accessibility
Insights, décisions C9 et C16 ; (5) les deux points que la revue laisse à
trancher (`STATUT.txt` § 6) : « HEC-RAS ouvert = refus » n'existe que dans le
plugin ; `suivi/` et les journaux sont partagés entre scénarios d'un même
dossier de sortie. La branche `claude/ponytail-lycxeg` peut être supprimée
sur GitHub : tout est dans `main`.

## État précédent — 18 septembre 2026 : 0.8.5, la relecture ergonomique livrée

La relecture du 17 septembre (`docs/ergonomie_2026-09-17.md`, grille du
dépôt `ergonomie`) validée par l'utilisateur, et ses correctifs — écrits
**sans QGIS**, depuis un clone Linux : le banc n'a pas tourné, le reste a
été mesuré autrement.

- **Thème sombre** : ruban, jauges, courbe et colonne Statut du Suivi
  passent par `interface.couleur()` — même table que les textes HTML ; le
  filet de la bannière suit. Ils gardaient les couleurs du clair sur Night
  Mapping (ardoise 2,3:1, rouge 1,8:1) : la recette du 11 avait mesuré ses
  scénarios sombres sur un projet **vide**.
- **Quatre questions Oui/Non** — pas trois : la relecture avait manqué
  « Chaîne de calage introuvable » — deviennent `confirmer()` : des verbes,
  le refus par défaut, Échap et croix compris.
- **Police** : les widgets peints dessinent en fraction de leur police et
  recalculent leur hauteur au `FontChange` ; noms et descriptions
  accessibles à chaque `actualiser()`.
- Teal sombre pour les textes, liens du fil conducteur au clavier,
  « fichier .prj » dans trois refus, boîtes du contrôle nommées comme le
  bouton, « (obligatoire) » au libellé du préfixe, `ONGLET_AIDE`, note HIG
  580 px, et `faire_zip.py` refuse un LISEZMOI qui cite une autre version.
- **Trouvé au passage** : `self.sizePolicy().Expanding` cassait sous PyQt6
  pur — forme qualifiée posée.

**Bancs : banc QGIS NON REJOUÉ** — 23 contrôles neufs, **301 attendus**.
À la place : `py_compile` des quatre `.py` touchés ; `faire_zip.py`
« archive conforme » ; garde-fou d'archive vert ; les trois widgets peints
dessinés hors écran sous PyQt6 6.11 (shim `qgis`) en clair et en sombre à
10 et 13 pt — couleurs remappées présentes, hauteurs qui suivent — et
`confirmer()` éprouvée (défaut, échappement, retour sans clic).

Par quoi reprendre : (1) **rejouer `test_plugin_qgis.py`** sous le Python
de QGIS — rien de la 0.8.5 n'a été vu tourner sous QGIS ; (2) regarder
l'onglet Suivi **rempli** en Night Mapping ; (3) refaire les six captures
(`captures_plugin.py`), qui datent de la 0.8.2 ; (4) installer le ZIP 0.8.5
dans le profil ISL ; (5) Accessibility Insights FastPass sur la fenêtre ;
(6) deux décisions laissées ouvertes — C9, dire au fil conducteur que le
bouton écrit dans la géométrie, et C16, un `QProgressDialog` sous
« Installer… » ; (7) la branche `claude/ponytail-lycxeg` — revue de
qualité de la 0.8.4, commit `0fd1b9a` du 17/09 — a été **fusionnée dans
`main` le 18 septembre** : voir la section suivante, et `STATUT.txt` § 6
pour les deux points qu'elle laisse à trancher.

## État précédent — 17 septembre 2026 : revue de qualité de la 0.8.4, fusionnée le 18

La 0.8.4 est commitée (`f4aaf6e`, `main`). Sur la branche
`claude/ponytail-lycxeg`, un passage `/simplify` : quatre relectures
(réutilisation, simplification, efficacité, profondeur du correctif), puis
les correctifs retenus. Aucune promesse de la 0.8.4 ne change ; `STATUT.txt`
§ 1 (entrée du 17/09, items 3, 5, 8 et 9) dit ce qui a bougé et ce qui a
été écarté.

- **`DialogueParametrage.classeur` est une propriété** : son setter
  rafraîchit le groupe « Excel des hydrogrammes objectifs » — trois
  affectations, un seul rafraîchissement.
- **Le Suivi ne relit le journal que s'il a changé** (un `stat` par tour) ;
  `noyau.dernier_journal` le retrouve, à côté de `lancer_calage` qui le nomme.
- **`_sans_tableau_des_temps`** coupe le compte rendu HEC-RAS à l'en-tête du
  tableau des temps ; plus de liste de mots d'échec.
- **`plan_fenetre_pleine` n'est passé qu'en reprise** ;
  `PiloteHecRas._duree_borne_h()` porte la borne et le banc l'éprouve.
- **Le recadencement des cibles dit `AVERTISSEMENT`** depuis la chaîne.

**À faire sur le poste** : rejouer `test_plugin_qgis.py` (QGIS) et
`pont_hecras.py autotest` (h5py). L'archive a été refaite en **0.8.6** à la
fusion dans `main`, le 18 septembre.
Deux points ouverts à trancher : la règle « HEC-RAS ouvert = refus » ne vit
que dans le plugin ; `suivi/`, `resultats_finaux/` et les journaux restent
partagés entre les scénarios d'un même dossier de sortie.

## État précédent — 14 septembre 2026 : 0.8.4 (commit `f4aaf6e`)

Six demandes utilisateur après un calage réel repris — Suhihandia, reprise à
SUH12 — et le constat qui les a fait naître : ce calage s'arrête au calcul de
référence, et rien de ce qui l'annonçait n'était visible à l'écran.

- **Le préfixe de scénario nomme l'Excel** : `donnees_calage_Q100.xlsx`
  (`noyau.nom_classeur`). Deux scénarios d'un même dossier de sortie ont deux
  classeurs, et composer l'un n'écrase plus l'autre. Préfixe vide = le nom
  d'avant. Aucune boîte « voulez-vous écraser ? » : un préfixe neuf est un
  fichier neuf — décision utilisateur.
- **Le préfixe passe à l'onglet 3**, seul dans son groupe et toujours actif,
  au-dessus du groupe « Excel des hydrogrammes objectifs » qui, lui, est
  **grisé** tant que rien n'est composé. « Reprendre un Excel… » reste actif :
  c'est la seule porte d'entrée vers un calage d'une autre session.
- **Les deux boutons reviennent côte à côte**, libellés raccourcis — ce qui
  rend la hauteur que l'empilement de la 0.8.2 coûtait sans ramener le
  débordement à 13 pt.
- **Les erreurs et avertissements remontent dans l'onglet Suivi**, encadré
  repliable sous la bannière, alimenté par le journal de lancement filtré.
- **HEC-RAS ouvert refuse le lancement**, un seul bouton « Ok ».
- **La ligne du calcul de référence nomme ce qu'elle met à zéro** — le
  comportement, lui, était déjà correct en reprise.
- **Les messages de HEC-RAS gardent la ligne qui explique**, non les quatre
  dernières, qui sont son tableau des temps (`_sans_tableau_des_temps` depuis
  la revue du 17/09). C'est
  ce qui empêchait de diagnostiquer l'arrêt de Suhihandia.
- **En reprise, la borne haute de la fenêtre reste celle du plan de
  référence** — mesuré sur le cas réel : 36 h au `.p01`, 32 h 06 au `.p20`
  dont la reprise repart. Défaut réel, mais pas la cause de l'arrêt.

**Bancs : banc QGIS 278 OK, aucun échec, sortie 0** (8 contrôles neufs) ;
`noyau.py`, `calage.py`, `suivi.py`, `criteres.py`, `pilote_hecras.py` et
`pont_hecras.py autotest` verts. La caractérisation de `calage.py` rend « la
trajectoire est celle de la référence » : la chaîne hydraulique est inchangée.

Par quoi reprendre : (1) **relancer le calage repris de Suhihandia avec la
0.8.4**, et lire l'encadré « Erreurs et avertissements » de l'onglet Suivi —
il dira ce que HEC-RAS refuse, ce que l'ancien diagnostic cachait derrière son
tableau des temps ; (2) voir les changements à l'écran dans QGIS ;
(3) installer le ZIP 0.8.4 dans le profil ISL ; (4) **commit** — fait,
`f4aaf6e` sur `main`.

## État précédent — 13 septembre 2026 : 0.8.3 commitée et poussée

Deux demandes utilisateur, la même scène : un calage mené à bout, le nombre
d'essais changé pour un apport, et l'on relance.

- **Le lancement demande par où reprendre.** `_confirmer_reprise()` nomme les
  apports **conservés** (déjà calés en amont, plans d'étape non retouchés) et
  les apports **perdus** (refaits à partir du départ), et propose le premier
  que le calage précédent n'a pas validé. Le calcul est une fonction pure,
  `plan_de_reprise()` — c'est elle que le banc éprouve. La question ne se pose
  que s'il y a quelque chose à perdre ; aucun bouton cliqué vaut *Annuler*.
- **L'onglet Suivi garde le calage précédent.** `Suivi.__init__` renomme
  `avancement.json` en `avancement_precedent.json` au lieu de l'écraser (un
  seul niveau d'historique). L'affichage reprend les apports validés que le
  calage en cours ne traite pas, statut **« repris »** posé par l'affichage —
  suivi.py n'en connaît que quatre —, teinte ardoise, hydrogrammes tracés
  derrière en tiret-point. Ils n'entrent ni dans `en_cours`, ni dans les
  jauges, ni dans les comptes.

**Bancs : suivi.py vert (2 contrôles neufs) ; banc QGIS 270 OK, aucun échec,
sortie 0** (12 contrôles neufs). ZIP 0.8.3 conforme et installé dans le profil
ISL, 21 fichiers — QGIS ouvert, recharger le plugin.

Commit `164bbf5` sur `main`, poussé ; l'arbre est propre.

Par quoi reprendre : (1) voir la boîte de reprise à l'écran, sur un vrai
calage relancé — le banc ne clique aucun bouton ; (2) les points restés
ouverts de la 0.8.2 (recette
Accessibility Insights / Load QSS, élision de la barre à 13 pt, diagnostic de
`_charger_couches_modele` pour rejouer `--modele`).

## État précédent — 0.8.2

Quatre changements d'ergonomie issus de la veille, tous natifs QGIS :
- trois aides dépliables deviennent des `QgsCollapsibleGroupBox` (état
  replié mémorisé par QGIS, objectName obligatoire pour la clé) ;
- toutes les boîtes d'information deviennent un `QgsMessageBar` dans la
  fenêtre (`_signaler`) ; seules décisions et erreurs interrompent encore ;
  diagnostic et installation écrivent leur détail sous le bouton ;
- `QgsGui.enableAutoGeometryRestore` dans `PluginCalage.composer()`, pas
  dans le constructeur (banc et captures exigent une géométrie fixe) ;
- **débordement de l'onglet Objectifs à 13 pt corrigé**, deux causes : la
  rangée de deux boutons (703 px, désormais empilés) et le tableau des
  cibles (désormais dans son propre `QScrollArea`). 773 px → 514 px.

**Banc : 258 contrôles, aucun échec, sortie 0.** ZIP 0.8.2 conforme et
installé dans le profil ISL ; captures refaites. Reste : commit, et la
recette Accessibility Insights / Load QSS proposée par la veille.

## État précédent — 0.8.1

Sur la branche `ergonomie`, arbre non propre. Fait et vérifié :
- onglet **« Aide et configuration »** ; plancher de largeur borné à 800 px
  (`LARGEUR_PLANCHER_MAX`), barre élidée sans défilement ;
- **relecture automatique des cibles** (onglets 3 et 4) quand l'Excel a
  changé sur disque : `_relire_cibles_si_modifiees()`, au changement
  d'onglet et au retour dans QGIS ; sans reprendre les réglages du classeur ;
- deux messages citaient l'ancien bouton « Composer et contrôler » ;
- banc QGIS **250 OK, 1 échec préexistant** (13 pt / Objectifs, débordement
  de 37 px — identique sur les sources 0.8.0, voir STATUT § 6) ;
- `calage_apports_0.8.1.zip` reconstruit et **installé dans le profil ISL**
  (QGIS ouvert : recharger le plugin) ; six captures refaites ;
- STATUT.txt, LISEZMOI, README, metadata, et `0-Ergonomie/retours/
  CALAGE_APPORTS.md` complétés.

Par quoi reprendre : (1) regarder l'élision de la barre d'onglets à 13 pt
dans une fenêtre de 800 px, à l'écran ; (2) faire remonter le diagnostic de
`_charger_couches_modele` dans le banc, puis rejouer `--modele` ;
(3) commit. Le point 2 de la 0.8.1 — widget trop large de l'onglet 3 — est
**réglé** en 0.8.2.

## Reprendre ici — 11 septembre 2026

La refonte **0.8.0** est sur la branche **`ergonomie`**, créée depuis
`bfff3fe`. Au contrôle initial, `main`, `origin/main` et les sources locales
étaient identiques, avec un arbre propre ; l'archive 0.7.24 correspondait
à ses sources. L'ancien état « quatre commits non poussés » était périmé.

La version **0.8.0** est installée et ouverte dans le profil QGIS **ISL**.
Les **21 fichiers installés** sont identiques à `calage_apports_0.8.0.zip` ;
les **20 fichiers sources** du ZIP sont identiques au dépôt, et le dernier
est le manifeste de provenance généré. Aucun bytecode n'est livré.

Le parcours conserve Modèle → Sorties → Objectifs → Lancer → Suivi, avec
Aide et le contrôle permanent en bas. Les détails secondaires se replient,
les textes suivent le thème et la police, et les étapes sont accessibles
par boutons, liens, F1 et Alt+flèches. Entrée ne déclenche plus les commandes
même si un bouton a le focus ; Espace reste disponible.

Validation : **248 contrôles Qt réussis, code de sortie 0**, sans modèle réel ;
**30 scénarios visuels** dans QGIS 3.44.8, dont 800 × 620, texte à 13 points,
Night Mapping et écran réel à 150 %. Trois défauts injectés sur une copie
isolée sont refusés par le garde-fou d'archive, puis la copie propre est
acceptée. Les six captures du README sont à jour. La chaîne hydraulique et
`noyau.py` n'ont pas été modifiés ; les 15 bancs de référence ont réussi.

Voir [les décisions et sources](docs/ergonomie_2026-09-11.md) et
[les mesures d'affichage](docs/ergonomie_2026-09-11-mesures.json).

**Suite :** relire la branche avant fusion. Un prochain calage réel permettra
de compléter la recette de la version 0.8.0 ; aucun calcul long ni écriture
dans un modèle de travail n'a été lancé pour cette refonte. Les chantiers
hydrauliques historiques ci-dessous restent hors du périmètre ergonomique.

## Historique technique du 9 septembre 2026

Les relevés et pistes qui suivent décrivent cette date. L'installation,
la recette graphique et le renouvellement des captures ont depuis été
réalisés pour la 0.8.0, comme indiqué ci-dessus.

### ✅ ARDANAVY Q20 V3 — TERMINÉ ET CONFORME

Lancé le 9 à 08 h 50 avec la **0.7.23**, conclu à **22 h 35**. **6 apports
sur 6**, 11 calculs, 13 h 44. Plan final **p12**. Livrables écrits dans
`resultats_finaux\` (15 fichiers). `alertes_chaine` vide.

| apport | essais | volume | pointe | forme | Δt appliqué |
|---|---:|---:|---:|---:|---:|
| ARD06 | 2 | 100,0 % | 100,7 % | 99,7 % | −1,6 h |
| ARD07 | 2 | 100,7 % | 98,3 % | 99,9 % | −0,8 h |
| ARD08 | 2 | 100,6 % | 100,3 % | 100,0 % | −1,7 h |
| ARD09 | 1 | 98,2 % | 101,7 % | 99,0 % | −1,6 h |
| ARD10 | 1 | 99,9 % | 99,3 % | 100,0 % | −0,5 h |
| ARD11 | 2 | 100,3 % | 99,3 % | 99,3 % | +0,1 h |

Écart maximal 1,9 % en volume, 1,7 % en pointe. Bilan de masse **0,015 %**
pour un seuil à 5 %.

**Cohérence du décalage : aucune alerte.** Étendue 1,8 h pour un seuil de
2,3 h ; pic du modèle +1,28 h par section, pic des cibles +1,00 h. Mesure
identique à celle du Q100 de ce modèle.

**Deux réserves de périmètre**, non bloquantes, dans `synthese.md` : une
fenêtre qui retient 72 % du volume cible (106,7 % sur toute la série) et une
autre 76 % (111,7 %). Règle en `STATUT.txt` § 2.2 bis — ce qui est hors
fenêtre n'est pas jugé et ne peut pas l'être, un apport ne sachant qu'ajouter
du débit.

**ARD11 a demandé deux essais pour une raison qui mérite d'être connue** :
sa section porte DEUX pics quasi égaux à l'essai 1 — 145,15 m³/s à 14,40 h et
142,87 à 16,10 h, soit 1,6 % d'écart. L'appariement par le pic a pris le
mauvais, rendu un Δt diagnostic de −1,60 h contre +0,10 appliqué, et annoncé
82,7 % de volume et 86,9 % de forme. Le Q100 avait donné 82,8 / 102,9 au même
endroit, et s'était redressé de la même façon à l'essai 2. Ce n'est donc ni
un défaut neuf ni un effet du correctif du 9.

**L'identifiabilité chute vers l'aval**, et c'est à porter au client :
l'apport pèse 56 % de la pointe à ARD06, 36 % à ARD07, 27 % à ARD08, 12 % à
ARD09, 8 % à ARD10, 8,7 % à ARD11. À 8 %, l'hydrogramme retenu peut
s'écarter de ~62 % du véritable sans que la section cesse d'être conforme
(règle en `STATUT.txt` § 2.5). La réserve automatique ne se lève qu'en
dessous de 5 %, donc aucune n'a été émise. **Sur ces trois sections,
l'hydrogramme d'apport livré est une valeur de commande, pas une estimation
hydrologique.**

**Deux lancements ont échoué avant celui-ci, le même jour :**

1. **08 h 46** — le calcul de référence est sorti en échec après 201 s. Cause :
   le **prétraitement 2D était périmé**, la composition de 08 h 40 ayant
   réécrit `Ardanavy.g03` dont le `.hdf` datait de trois jours. La chaîne
   l'avait annoncé, ligne 72 de son propre journal. Ce run raté a régénéré le
   `.hdf` — c'est ce qui a permis au suivant d'aboutir.
2. **HEC-RAS était ouvert** pendant les deux. La 0.7.24 pose désormais la
   question au lancement.

### Ce que la journée du 9 a donné

**Un défaut de verdict trouvé en production, corrigé, et quatre demandes
d'ergonomie.**

| | |
|---|---|
| **LA FENÊTRE JUGÉE EST EN TEMPS DE SIMULATION, et le diagnostic la lisait sur la base de temps de la cible.** Δt de +2,60 h sur une cible culminant à 0,50 h : le pic de la cible tombait hors fenêtre, une section calée à 0,1 % près était annoncée à **350 % de pointe et 370 % de volume**, refusée après trois essais et sept heures. Onze apports non traités | `STATUT.txt` § 2.2, commit `0302ccd` |
| **Un décalage plus long que la fenêtre qu'il décale devient BLOQUANT** — il n'était refusé que par l'effet du défaut ci-dessus | idem |
| **Décision : le calage vise le volume, la pointe et la forme. Pas l'heure du pic.** Le volume injecté n'est pas un levier (0,03 % d'écart de Δt = 0 à −3 h) et le prendre pour objectif serait dégénéré : son minimum est zéro | `STATUT.txt` § 2.1 |
| **Ce n'était pas une régression** — `decalage_minimisant_ecart` et `_temps_du_pic` sont mot pour mot ceux du 31/08, et cette chaîne rejouée rend le même −1,60 h | idem |
| **0.7.24 : les onglets 2 et 3 s'inversent**, « Contrôle paramétrage » quitte les onglets pour le bas de la fenêtre — vert quand c'est le moment, gris sinon —, l'onglet « Objectifs » chiffre pointe, heure du pic et volume de chaque cible, et HEC-RAS ouvert fait poser une question au lancement | commit `3cac4f8` |
| **L'analyse « jacobien triangulaire / calage simultané » est retirée du dépôt** — demande utilisateur. `docs/idees_V2_plugin.md` ne garde que ses deux idées sans rapport. L'historique git la porte toujours | commit `349d503` |

### Bancs — ce qui a été rejoué le 9, et ce qui ne l'a pas été

**Verts, depuis le poste :** `calage` (référence **regelée**), `criteres`
(section 7 quinquies, neuf contrôles neufs), `noyau` (section 12, quatre
contrôles neufs), `suivi`, `livrables`, `geometrie`, `controle_donnees`,
`elaguer_projet`, `pilote_hecras`, `pont_hecras`, `style_classeur`,
`creer_template`, `verification_environnement`, `faire_zip`,
`essai_garde_fou_archive`.

**`CALAGE_PYTHON` n'est plus posée sur ce poste, et ce n'est pas un obstacle :**
`D:\1-Python\.venv\Scripts\python.exe` porte les treize paquets, geopandas et
h5py compris. C'est lui qui a fait tourner les quinze bancs.

**NON REJOUÉ : `test_plugin_qgis.py`** — douze contrôles neufs pour la 0.7.24,
et il exige QGIS.

### Ce que la journée du 8 a donné

**Deux décisions d'hydraulicien, et un onglet 1 remanié.** Le plugin passe en
**0.7.19** — non réinstallé, non vu sous QGIS.

| | |
|---|---|
| **Il n'y a pas de boucle hydraulique** — confirmé. L'hypothèse d'ordre total tient. Elle est désormais écrite **comme une hypothèse du modèle, que la chaîne ne vérifie pas** : aide du plugin, note § 1.2 et « Trois questions bloquantes », README | `STATUT.txt` § 6, À FOURNIR |
| **Le verdict de volume reste sur la fenêtre** — « le concept de fenêtre a été fait pour ça ». Rien ne change dans le code ; l'aide et la note l'énoncent, la question d'élargir la fenêtre est close | `STATUT.txt` § 6, À TRANCHER |
| **« Écrire, composer et contrôler » ferme l'onglet 1**, dans un encadré « Mise à jour du modèle » — il était permanent en bas de la fenêtre, visible depuis six onglets dont cinq n'en font rien | |
| **L'encadré « Écriture dans la géométrie » descend dans l'aide** — il ne portait aucune commande, et se lisait pourtant comme une étape. Son compte rendu ouvre maintenant la boîte de composition, d'où il est enfin visible | |
| **« Axe hydraulique » devient « Profil en long »**, et remonte sous le plan | |
| **L'aide perd « Sur un autre poste »** — elle ne disait rien de plus que « Première utilisation » | |
| **Le garde-fou d'archive a mordu pour de vrai** — quatre noms de cas réels dormaient dans des commentaires de la chaîne embarquée, invisibles depuis le clone Linux du 7, qui n'avait pas `.affaires`. La mesure reste, le nom renvoie à `STATUT.txt` § 5. `faire_zip` rend de nouveau « archive conforme », le garde-fou « TOUT PASSE » | `STATUT.txt` § 1 |
| **L'archive porte la 0.7.19**, reconstruite sous Windows — les vingt fichiers sont donc en CRLF | |
| **La note passe en V16** — `contenu.py` § 1.2, § 1.4 et le chapitre du plugin ; `.docx` reconstruit, 8 911 mots. **Le `.pdf` reste en V15** : Word se fige dans son export sur ce poste, et pas à cause du document — la note d'avant, sortie de git, se fige pareil | `STATUT.txt` § 6 |
| **Les six captures sont refaites, et par un script** — `src/captures_plugin.py`, avec un projet de démonstration et les chemins du poste mis en scène | `STATUT.txt` § 1 |
| **Deux défauts d'affichage trouvés PAR les captures** — le libellé du bouton coupé à mi-hauteur dans une fenêtre trop courte, et une phrase à deux lignes dont la seconde sortait rognée. Le banc ne les voit pas : il n'éprouve pas l'apparence | `STATUT.txt` § 1 |
| **Le banc du plugin rejoué : 153 contrôles, 0 échec**, sur une copie réduite d'un modèle réel (113 Mo au lieu de 60 Go). Sept contrôles neufs pour la 0.7.19, plus trois pour la branche « poste neuf » du diagnostic | `STATUT.txt` § 1 |
| **Deux défauts du banc de plus**, même motif que les huit précédents — il suppose le monde de son auteur : le mannequin de `QMessageBox` ignorait quatre méthodes que seule la branche « pas d'interpréteur » appelle, et un appariement impossible était compté comme quatre échecs au lieu d'un diagnostic sur le modèle | `STATUT.txt` § 1 |
| **L'interpréteur HEC-RAS posé par le bouton « Installer… »**, depuis QGIS, sur un poste qui n'en avait pas — le point ouvert depuis le 30/08 est levé | `STATUT.txt` § 1 |

### La 0.7.22 — remaniement d'ergonomie

| | |
|---|---|
| **L'onglet 1 suit l'ordre des gestes** : projet, plan, couches, profil en long, fenêtre | `STATUT.txt` § 1 |
| **« Contrôle du paramétrage » passe à l'onglet 2**, après la précision attendue — troisième déménagement, et le dernier a une raison qui tient | |
| **L'élagage devient une case à cocher**, décidée avant le calage et appliquée par la chaîne à la fin. L'encadré dit « Les plans intermédiaires seront CONSERVÉS / SUPPRIMÉS », le mot en rouge dans les deux sens | |
| **Le préfixe de scénario est obligatoire** — c'est ce qui empêche la seule perte de données que la chaîne sache provoquer | |
| « Relire un hydrogramme » quitte la fenêtre ; trois passe-plats de `noyau.py` partent avec lui | |
| **La console noire a disparu pour de bon** : le calage part par `pythonw.exe`, binaire graphique auquel Windows n'alloue jamais de console. Le correctif précédent — console réduite — ne valait que pour le processus créé, pas pour celui que le relais crée | |
| Banc du plugin : **128 contrôles, 0 échec** | |

### La 0.7.21 — l'action passe à l'onglet 4

| | |
|---|---|
| **« Écrire, composer et contrôler » quitte l'onglet 1 pour l'onglet 4**, dans un encadré **« Contrôle du paramétrage »** qui précède « Calage ». Ce qu'il produit — paquet, classeur, compte rendu — se lit là ; le composer ailleurs obligeait à revenir en arrière. On ne lance plus rien sans être passé devant le compte rendu | `STATUT.txt` § 1 |
| Le nom change avec la place : « Mise à jour du modèle » annonçait l'effet de bord, pas le geste qu'on cherche avant de lancer | |
| Prix assumé : recomposer au fil de l'ajustement des couches fait l'aller-retour 1 → 4 | |

### La 0.7.20, dans la foulée

| | |
|---|---|
| **Les titres d'étape passent au souligné** — `Q100_sans_apport`, `Q100_Apport_A1`, `Q100_avec_apports`. **Casse la reprise d'un calage antérieur** : ses étapes portent l'ancienne écriture et ne seront plus reconnues | `STATUT.txt` § 1 |
| **Les plans d'étape s'élaguent, sur demande** — encadré « Ménage du modèle HEC-RAS » à l'onglet 3. Simulation d'abord, confirmation ensuite, et refus si le calage n'a pas conclu. Douze contrôles au banc | `STATUT.txt` § 1 |
| **Le suivi montre les sections déjà calées**, en vert pointillé derrière la paire courante — seules les validées | `STATUT.txt` § 1 |
| **Le thème sombre était cassé, et personne ne l'avait vu** : cinq fonds pris à `alternate-base` (quasi blanc sous Night Mapping), et la piste des jauges jamais dessinée — `QColor` lit `#AARRGGBB`, pas `#RRGGBBAA`. Trois défauts qu'aucun banc n'aurait pris : il a fallu **regarder** | `STATUT.txt` § 1 |
| **Deux défauts du banc de plus** — le mannequin de `QMessageBox`, et un appariement impossible compté comme quatre échecs | `STATUT.txt` § 1 |
| Banc du plugin : **118 contrôles sans modèle, 153 avec**, 0 échec | |

### Ce que la journée du 7 a donné

| | |
|---|---|
| **Le KGE, alpha et beta sont retirés du code** — la figure de convergence des livrables finaux traçait beta sous « Volume atteint (% de la cible) », celle du suivi sortait vide | `STATUT.txt` § 1 et § 2, VOLUME |
| **`tolerance_beta` s'appelle `tolerance_volume`** ; la référence de caractérisation est regelée, identique à l'ancienne privée des trois clés | |
| **L'apport peu identifiable est une réserve non bloquante du Diagnostic** — colonne « Alertes » du classeur, note de synthèse, suivi ; aucun verdict ne bouge | `STATUT.txt` § 2, « L'APPORT EST-IL IDENTIFIABLE ? » |
| **Les deux comptes rendus de contrôle sont une seule boîte** — le recontrôle d'un classeur avait perdu sa poignée | `STATUT.txt` § 6 |
| **Deux bancs passent désormais depuis un clone Linux** — `noyau` (disposition d'un venv) et le garde-fou d'archive (chemins POSIX, qu'il ne voyait pas) | |
| **La note se reconstruit sans qu'on lui porte ses deux figures d'origine** — elles sont lues dans le gabarit | |
| **Trois affirmations de `STATUT.txt` corrigées** : le PDF n'était pas en retard (Version 15), `reprises_max` n'est pas « inerte » mais retiré, l'ordre total est en § 1.2 de la note | |
| Lecture complète du dépôt, 54 fichiers, doc et code | |

### Ce que la journée du 6 a donné

| | |
|---|---|
| **La suite du plugin passe de bout en bout** — 152 annoncés, 172 obtenus | `STATUT.txt` § 1 |
| **Sept défauts du banc**, tous « il suppose le monde de son auteur » | `STATUT.txt` § 1 |
| **Lot 5 d'`AUDIT.md`** — mené le **5 au soir** : `caler()` 699 → 622 lignes, 3ᵉ extraction écartée sur mesure | `AUDIT.md` § P1-4 |
| **`AUDIT.md` est clos** — seul P2-10 reste, et l'audit dit que ce n'est pas un lot | |
| **Les correctifs d'ergonomie**, 0.7.1 à 0.7.14 (la note s'arrête à 0.7.12 : les deux dernières viennent d'une demande directe) | `docs/ergonomie_2026-09-06.md` |
| Le bouton « Installer… » **éprouvé depuis QGIS**, ses deux chemins | `STATUT.txt` § 1 |
| La note méthodologique **reconstruite** — sa table d'onglets datait d'avant la 0.7.0 | |

### Ce qui reste, et rien d'autre

0. **Relire les livrables d'ARDANAVY Q20 V3** — `resultats_finaux\`, à
   l'œil : `synthese.md`, `tableaux_calage.xlsx`, le profil en long, les six
   comparaisons. Le calage est conforme ; ce sont ses SORTIES qui n'ont pas
   encore été regardées. Pas de figure de convergence pour ARD09 et ARD10 :
   un seul essai, rien à tracer.
1. **Installer la 0.7.24 et rejouer `test_plugin_qgis.py`** — Extensions →
   Installer depuis un ZIP, `calage_apports_0.7.24.zip`. **Pas pendant un
   calage.** Douze contrôles neufs, et ils exigent QGIS. Sans cela le poste
   garde la 0.7.23 : elle porte le correctif de la fenêtre, mais pas l'ordre
   des onglets, ni le bouton du bas, ni le tableau des cibles, ni la question
   sur HEC-RAS ouvert.
2. **Refaire les captures du README** — `python src/captures_plugin.py` sous
   l'interpréteur de QGIS. Elles datent de la 0.7.19 et montrent l'ancien
   ordre des onglets ; le README le dit désormais, ce qui ferme le risque de
   les croire à jour, pas celui de les laisser fausses.
3. **Le `.pdf` de la note, à réexporter à la main** — ouvrir le `.docx`
   (V17) dans Word, *Enregistrer sous > PDF*, et lui remettre une table des
   matières au passage : la reconstruction la perd. Quatre tentatives
   d'export piloté ont échoué, sans que le document y soit pour quelque
   chose. **La note ne parle encore ni du correctif de la fenêtre ni de la
   0.7.24** — `contenu.py` est à reprendre avant l'export.
4. **Regarder la fenêtre**, et cette fois il y a de quoi : la 0.7.24 déplace
   deux onglets et sort un bouton des onglets, sans qu'aucun œil ne l'ait vu
   sous QGIS.
   **À regarder en priorité : les fenêtres étroites.** La zone défilante de
   chaque onglet comprime son contenu au lieu de faire apparaître une barre,
   et c'est le dernier encadré qui encaisse — le plancher posé sur le bouton
   principal ne protège que lui, et le nouveau tableau des cibles est
   justement le dernier encadré de son onglet (il porte son propre plancher,
   calculé sur le nombre de lignes — à vérifier à l'œil).
   **Entrée ne fait toujours rien**, nulle part — prix assumé du désarmement
   du geste irréversible.
5. **Le suivi pendant un vrai calage.** L'état du calage précédent qui ne se
   peint plus, « mort au démarrage » distingué de « pas encore parti », le
   fil qui dit « calage lancé », la question posée si l'on recompose pendant
   qu'un calcul tourne : tout cela est éprouvé sur des états **fabriqués**,
   jamais sur un calage qui tourne. Y regarder aussi la **figure de
   convergence** corrigée, dans `suivi/` et dans `resultats_finaux/`.
6. **Trois garde-fous jamais rencontrés en réel** — volume plancher, apport
   refusé, modèle incohérent. Seul le banc les couvre.

### Le poste de travail, pour y revenir

`venv-hecras` monté, `CALAGE_PYTHON` figé au niveau utilisateur,
`.affaires` créé depuis l'exemple. `QGIS_PREFIX_PATH` **n'est plus à
poser** : le banc le déduit de l'interpréteur qui tourne. Le modèle
d'essai est le plan **TEST** de `Muncie` (`p02`/`g02`), auquel deux
`BC Line` et deux `Reference Line` ont été ajoutées — la seconde section
en **aval** de la première, sans quoi le plugin refuse à juste titre.

### Deux questions déjà tranchées, pour ne pas les rouvrir

- **Le repli cassé des pentes n'a jamais été emprunté** — les journaux des trois
  calages ne portent pas `pente : deduction impossible`. Aucun livrable à
  reprendre. Le défaut était **latent**, et il est corrigé.
- **La réserve de périmètre du volume énonce un périmètre, elle ne dénonce pas
  un défaut** : elle se lève aussi sur une mini-crue exclue à bon droit, et
  c'est assumé (les séparer demanderait un seuil non mesuré).

---

## Reprendre depuis GitHub, sans le poste de travail

Le dépôt porte le code, `STATUT.txt`, ce fichier, la note et le template.
**L'historique des conversations ne voyage pas** — il vit dans
`~/.claude/projects\…` sur le poste. Ces deux fichiers le remplacent.

**Par quoi commencer :** la section « Reprendre ici » ci-dessus, puis
`STATUT.txt` § 1, § 2.2 bis, § 2.2 ter, § 5.3 ter et § 5.5.

**Installer :** `python -m pip install -r requirements-dev.txt`

**Ce qui ne sera PAS disponible hors du poste**, et qu'il ne faut pas chercher
à contourner :

| | |
|---|---|
| le partage réseau des modèles | ni suivi de calage, ni lecture de journal, ni relecture de HDF |
| HEC-RAS, `ras-commander`, `h5py` | aucun calage ne peut être lancé ni relu |
| QGIS | `test_plugin_qgis.py` exige le Python de QGIS |
| Word | l'export PDF de la note passe par lui ; le `.docx`, lui, se reconstruit |
| `.affaires` | ignoré par git — ce sont des noms de clients |

Sur `.affaires` : sans lui, `essai_garde_fou_archive.py` éprouve quand même le
contrôle des noms, **sur un mot qu'il fabrique**, et dit que la liste reste à
fournir. Le garde-fou n'est donc pas muet — mais il ne surveille rien de réel.
Avant de committer depuis un clone neuf, se rappeler qu'un nom de client
passerait.

## Les sessions passées

Elles vivaient ici, section par section — trente et un récits, plus de deux
mille lignes, dont ce fichier disait lui-même qu'ils étaient « conservés comme
récit, **pas comme référence** ». Ils sont retirés : `git log` les porte, et
`STATUT.txt` porte ce qui en est resté vrai.
