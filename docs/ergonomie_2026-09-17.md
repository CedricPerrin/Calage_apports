# Relecture ergonomique de Calage des apports — 17 septembre 2026

Relecture du plugin QGIS **0.8.4** (`main` = `f4aaf6e`, 14 septembre 2026, arbre propre) à
travers la grille de la synthèse du dépôt `ergonomie` (`ERGONOMIE_SYNTHESE_2026-09-17.md`,
§ 3 principes, § 4 pièges, § 5 recette, § 7.3 accessibilité). Matière lue : `calage_apports/plugin.py`
(5 958 lignes) et `interface.py`, `src/test_plugin_qgis.py` (banc, 231 contrôles), `STATUT.txt`
§ 2, 3 et 6, `CHECKPOINT.md`, `LISEZMOI.md`, `README.md`, `metadata.txt`,
`docs/ergonomie_2026-09-06.md`, `docs/ergonomie_2026-09-11.md` et ses mesures.

**Ce document a été écrit avant les correctifs**, qu'il propose sans les faire ; ce qui en a été
fait — et ce qui ne l'a pas été — est au § 7. Chaque constat a été réattaqué
en relisant le code ; ceux qui sont tombés sont au § 3, parce qu'un constat réfuté est une
décision au même titre qu'un constat tenu.

**Limites.** Pas de QGIS ni d'écran ici : les contrastes sont **calculés** en sRGB sur les
couleurs définies (formule WCAG), sur les deux fonds de fenêtre relevés par la recette du
11 septembre (`#f0f0f0` clair, `#323232` Night Mapping) — ils ne mesurent pas les pixels
anticrénelés. Aucun utilisateur n'a été observé : les quatre questions du § 4 de la note du
6 septembre restent sans réponse, et cette relecture n'en donne aucune.

---

## 0. En dix lignes

**Seize constats tenus (C1 à C16, dont trois de méthode ou de note) ; sept pistes envisagées puis écartées au § 3.** Le plugin applique déjà l'essentiel de ce que la
synthèse a établi : Entrée n'écrit jamais, l'information passe par un bandeau, l'échec après
écriture le dit, les prérequis sont nommés, aucun `isVisible()` ne décide du contenu. Ce qui
reste se range en trois familles :

1. **Le thème sombre s'arrête aux textes HTML.** Les trois widgets dessinés au `QPainter` et le
   tableau du suivi gardent les couleurs du thème clair : sur `#323232`, l'ardoise tombe à
   **2,3:1**, le rouge à **1,8:1**, le vert à **2,2:1**. Le mécanisme de remappage existe
   (`interface.COULEURS_SOMBRES`) ; les peintres ne l'appellent pas. Les scénarios sombres de la
   recette ont été mesurés sur un projet **vide** — l'onglet Suivi n'y portait aucune donnée.
2. **Trois boîtes Oui/Non n'ont pas de bouton par défaut posé**, dont celle qui autorise à
   recomposer pendant qu'un calage tourne — sa docstring promet « non » par défaut, le code ne
   le pose pas. Une ligne chacune.
3. **La documentation livrée est en retard d'une version** : le LISEZMOI dit 0.8.2 et nomme
   `calage_apports_0.8.2.zip` ; les six captures du README datent de la 0.8.2 alors que la 0.8.4
   a déplacé le préfixe et réorganisé l'onglet 3 — « une capture périmée ressemble à une
   capture », dit `captures_plugin.py` lui-même.

Le reste est petit et cheap : le teal `#3A8D94` en couleur de **texte** sur fond clair (3,4:1),
les liens du fil conducteur inatteignables au clavier, trois messages qui parlent encore du
« dossier du projet », trois noms pour le geste de contrôle, des tailles de police figées dans
les widgets peints. Deux points relèvent d'une décision, pas d'un correctif (§ 2, C9 et C16).

---

## 1. Ce que la relecture confirme — à ne pas défaire

| Principe (synthèse) | Où le plugin le tient | Preuve |
|---|---|---|
| Entrée n'écrit jamais (§ 3.10) | `keyPressEvent` avale Return/Enter ; `_nommer_champs` retire `autoDefault` de tous les boutons | `plugin.py:1949-1984`, `1967-1969` ; banc « Entrée ne déclenche aucune action » à 9 et 13 pt |
| L'état d'affichage ne décide pas du contenu (§ 4.3, piège Sensi 6.15) | **Aucun** `isVisible()`, `isHidden()`, `isEnabled()` lu dans `plugin.py` | grep, 17/09 |
| Informer sans interrompre (§ 3.7) | `QgsMessageBar` `_signaler` ; plus aucune `QMessageBox.information` | `plugin.py:1721-1724`, `1891-1894` |
| Dire ce qui a déjà été modifié (§ 3.3) | Le drapeau `geometrie_reecrite` complète la boîte d'échec | `plugin.py:5593`, `5777-5784` |
| Prérequis visibles, refus qui nomment l'onglet (§ 3.3) | Bouton vert/gris cliquable en gris, infobulle « Il manque encore : … » ; refus « Onglet 1 : … » | `plugin.py:2397-2437`, `5602-5640` |
| Confirmation réservée aux actions graves, verbes spécifiques, défaut sûr (§ 7.4) | `_confirmer_reprise` : « Reprendre à X » / « Tout recaler » / « Annuler », défaut = celui qui ne coûte rien, croix = Annuler | `plugin.py:5126-5150` |
| Refus à un seul bouton sûr (Microsoft, § 7.2) | « HEC-RAS est ouvert … Ok » | `plugin.py:5281-5285` |
| Divulgation progressive, état mémorisé (§ 3.4) | `QgsCollapsibleGroupBox` nommés ; alertes repliées, dépliées **une fois** quand un contenu arrive | `plugin.py:3655-3670`, `4084-4092` |
| Progression réelle, jamais inventée (§ 3.8) | `QProgressBar` sur la `fraction` publiée par `suivi.py` ; « pas encore démarré » ≠ « mort au démarrage » ; dossier surveillé nommé à chaque passage | `plugin.py:4145-4219` |
| États = mot + glyphe + couleur (§ 3.7) | `GLYPHE_STATUT`, plein/contour sur le ruban | `plugin.py:541-552`, `597-611` |
| États vides qui expliquent (§ 7.4) | `texte_etat` masqué s'il est vide ; courbe « La comparaison apparaît après le premier essai évalué » ; résumé « (rien de configuré pour le moment) » | `plugin.py:1144-1156`, `791-798`, `5577-5578` |
| Libellés persistants, unités, exemples (§ 3.5) | `setBuddy` + `accessibleName` automatiques ; placeholders-exemples des dates ; suffixes ` %`, ` m` | `plugin.py:1912-1934`, `2244-2271`, `2932-2993` |
| Thème et police du poste (§ 3.12) | Feuille régénérée sur `PaletteChange`/`ApplicationFontChange` par minuteur ; surfaces en `palette(...)` ; textes HTML remappés en sombre | `plugin.py:1871-1910`, `interface.py:23-32`, `69-109` |
| Le libellé nomme ce que le geste fait (§ 3.2) | « Ouvrir dans Excel » sans points de suspension (règle KDE) ; « Reprendre un Excel… » avec | `plugin.py:3073`, `3080` |

Ce tableau est aussi la liste de ce qu'une prochaine passe ne doit pas « améliorer » : le § 3 de
la note du 6 septembre reste valable — bouton permanent, libellés courts, ordre écrire →
composer → contrôler, sablier — et s'y ajoutent, depuis, le refus HEC-RAS à un bouton, Entrée
avalée, et le sondage `tasklist` (« essayé, mesuré, retiré »).

---

## 2. Constats tenus, du plus rentable au moins

Sévérité sur l'échelle de Nielsen (1994) : 4 catastrophe · 3 majeur · 2 mineur · 1 cosmétique.

### C1 — Le thème sombre s'arrête aux textes HTML : les widgets peints et le tableau gardent les couleurs du clair — *sévérité 3*

`interface.texte_theme` remappe les `color:#…` des étiquettes riches quand la fenêtre est
sombre (`COULEURS_SOMBRES`, `interface.py:11-16`), et `feuille()` choisit ses accents selon la
clarté. Rien de tel dans les trois classes dessinées au `QPainter`, qui emploient les constantes
ISL telles quelles :

| Où | Couleur brute | Contraste sur `#323232` (fond Night Mapping mesuré) |
|---|---|---|
| `RubanApports.paintEvent` — texte « aucun calage suivi », contour des segments en attente, texte des contours | `ISL_ARDOISE_CLAIR` = `#526B7A` (`plugin.py:583`, `596`, `621`) | **2,29:1** |
| `JaugeAtteinte.paintEvent` — libellé, axe central, valeur hors tolérance / conforme | `#526B7A` (`665`, `723`), `#A03028`, `#386F55` (`674-676`) | **2,29 · 1,80 · 2,18** |
| `CourbeComparaison.paintEvent` — graduations, axes, légende « cible », sections calées, « calage précédent » | `#526B7A` (`827`, `831`, `881-885`, `917-921`), `#386F55` (`856`, `900-903`) | **2,29 · 2,18** |
| `_remplir_table_suivi` — colonne Statut | `setForeground(QColor(COULEUR_STATUT…))` (`4441`) sur `palette(base)` ≈ `#232323` | ardoise **2,80**, rouge **≈ 1,9**, vert **≈ 2,3** |
| `_banniere` — filet gauche 5 px | `border-left: 5px solid {couleur}` brut (`4006-4009`) | rouge sur base **2,21** (décoratif : le titre, lui, est remappé) |

Seules la piste et la bande de tolérance de la jauge consultent le fond réel
(`plugin.py:700-712`) — la preuve que `sombre(self)` fonctionne dans un widget peint. Le
correctif du 8 septembre (0.7.20, « le thème sombre est réparé ») portait sur `alternate-base`
et sur l'alpha ; il n'a pas atteint les couleurs de trait et de texte.

**Pourquoi la recette ne l'a pas vu.** Les six scénarios `sombre-*` du 11 septembre ont été
mesurés dans un « profil TEST, projet vide ; aucune simulation HEC-RAS lancée »
(`docs/ergonomie_2026-09-11-mesures.json`, `contexte`) : l'onglet Suivi n'y montrait qu'« aucun
calage suivi » (déjà à 2,29:1), trois jauges à « — » et une courbe vide. Les widgets peints n'ont
jamais été **vus** avec des données en Night Mapping.

**Correctif proposé.** Une fonction `couleur(nom_hex, widget) -> QColor` dans `interface.py`,
qui rend `COULEURS_SOMBRES.get(nom_hex.lower(), nom_hex)` quand `sombre(widget)` ; l'employer
aux quatorze `QColor(ISL_…)` des trois `paintEvent` et au `setForeground` du tableau ; le filet
de la bannière suit. Une trentaine de lignes. **Au banc** : poser une `QPalette` sombre sur la
fenêtre (`Window = #323232`), remplir le suivi avec l'état synthétique déjà employé par
« suivi : chaque statut porte un glyphe », et vérifier que la couleur choisie par le peintre
est la remappée — ce qui exige d'exposer le choix de couleur hors du `paintEvent`, comme la
jauge expose déjà `tolerance`. Sans écran.

*Réfutation tentée.* « `Etiquette.setText` remappe déjà » — vrai pour les `QLabel`, sans effet
sur `QPainter`. « Night Mapping repeint les widgets » — non, un `paintEvent` maison peint ce qu'on
lui dit. « `sombre()` ne verrait pas la palette dans un widget peint » — la piste de la jauge
prouve le contraire. Le constat tient.

### C2 — `ISL_TEAL` (`#3A8D94`) sert de couleur de **texte** sur fond clair : 3,4:1 — *sévérité 2*

La feuille de style emploie `#2E7176` comme accent (4,93:1 sur `#f0f0f0`, `interface.py:72`,
`93-100`). Le code Python, lui, écrit `ISL_TEAL = #3A8D94` dans des textes :

| Où | Texte | Contraste sur `#f0f0f0` |
|---|---|---|
| `_resume_fenetre` — « **Fenêtre modifiée** — elle sera imposée au plan de calcul » | 10 pt gras | **3,40:1** (`plugin.py:2636-2638`) |
| `_peindre_suivi` — « **A3 → SC3** · essai 2 · apport 3 sur 12 » | 10 pt gras | **3,40:1** (`4304-4305`) |
| `COULEUR_STATUT["en cours"]` — colonne Statut du tableau | 10 pt gras | **3,40:1** (`531`, `4441`) |
| `CourbeComparaison` — légende « mesuré » | 7,5 pt | **3,40:1** (`888-890`) |
| `RubanApports` — blanc sur segment « en cours » | 7,5 pt gras | **3,88:1** (`617`, `621`) |

WCAG 1.4.3 demande 4,5:1 pour tout texte qui n'est pas « grand » (18 pt, ou 14 pt gras) ; 10 pt
gras n'en est pas. Le 3:1 admis pour les objets graphiques couvre le **trait** de la courbe
(`864`) et le remplissage du ruban, pas leurs textes. Sensi avait rencontré le même écart et
refusé deux variantes à 4,07 et 4,40 (`ERGONOMIE_RECHERCHE.md` § 9).

**Correctif.** Pour les textes, `ISL_TEAL_SOMBRE` (`#2E7176`, 4,93:1) — la couleur que la feuille
de style emploie déjà ; `#3A8D94` reste pour les traits et les fonds. En sombre, la table
`COULEURS_SOMBRES` mappe déjà les deux vers `#7CC4C8` (6,46:1) : le correctif ne concerne que le
clair. Cinq lignes. **Au banc** : une fonction pure `contraste(a, b)` (vingt lignes) appliquée
aux couples texte/fond des deux thèmes, avec le seuil 4,5 — c'est le calcul que Sensi a fait à
la main le 11 septembre, versionné.

### C3 — Trois boîtes Oui/Non n'ont pas de bouton par défaut posé, et l'une promet « non » — *sévérité 3, coût trivial*

`_confirmer_malgre_calage` (`plugin.py:3951-3957`) pose la question « Continuer quand même ? »
avec `Yes | No` **sans** cinquième argument `defaultButton`. Sa docstring (`3934-3945`) et celle
de `_calage_en_cours` (`3917-3918`) disent : « la réponse par défaut est « non » ». Le code ne
le pose nulle part.

Ce que Qt fait alors, d'après sa documentation (§ 7.2 de la synthèse) : `QMessageBox.question`
« choisit un défaut automatiquement » — le premier bouton de rôle **Accept** ; or `Yes` porte le
rôle *Yes*, pas *Accept*, donc aucun n'est retenu ; et un `QDialog` sans bouton par défaut donne
Entrée au premier bouton `autoDefault` de la chaîne de focus — en disposition Windows, **Oui**.
La garde de `keyPressEvent`, qui avale Entrée dans la fenêtre, ne protège pas une boîte modale :
c'est une autre fenêtre. Trois boîtes sont dans ce cas :

| Boîte | Ce qu'« Oui » fait | Ligne |
|---|---|---|
| « Un calage est en cours … Continuer quand même ? » | réécrit la géométrie et le classeur qu'un calcul lit | `3951` |
| « Installer l'environnement Python HEC-RAS … Continuer ? » | télécharge plusieurs centaines de Mo, QGIS figé | `4635` |
| « Hydrogrammes cibles trop courts … Prolonger … par des ZÉROS ? » | écrit dans la feuille Cibles | `5370` |

À l'opposé, `_confirmer_reprise` (`5142`) et la boîte de l'interpréteur (`4797`) posent leur
défaut explicitement, et le banc le vérifie pour la seconde (« « Installer… » est le bouton mis
en avant ») : le mannequin `BoiteMessage` enregistre `bouton_defaut`, l'outil existe.

**Correctif.** `QMessageBox.StandardButton.No` en cinquième argument des trois appels, et un
contrôle au banc par boîte. Tant qu'à rouvrir ces trois lignes : des **verbes** plutôt que
Oui/Non — « Recomposer quand même » / « Ne pas recomposer », « Installer » / « Plus tard »,
« Prolonger par des zéros » / « Laisser tel quel » — comme `_confirmer_reprise` le fait déjà, et
comme NN/g et Microsoft le demandent (§ 7.4, § 7.2). **À confirmer à l'écran** quel bouton reçoit
Entrée aujourd'hui ; le correctif est le même quel que soit le verdict.

### C4 — Les widgets peints ignorent la taille de police du poste — *sévérité 2*

Le formulaire suit la police (`feuille(palette, taille)`, banc « les saisies suivent la police
demandée » à 9 et 13 pt) et le bouton de contrôle calcule sa hauteur sur `fontMetrics()`
(`plugin.py:2393-2394`). Les trois widgets peints, non :

| Widget | Figé | Ligne |
|---|---|---|
| `RubanApports` | hauteur minimale 46 px ; texte **7,5 pt** | `568`, `623` |
| `JaugeAtteinte` | hauteur 56 px « mesurés à l'écran » ; libellé **8 pt**, valeur **11 pt** ; ordonnées 2/16/18/20/42/12 px | `650`, `662`, `670`, `666-705` |
| `CourbeComparaison` | hauteur 190 px ; texte **7,5 pt** ; marges 46/8/8/22 px ; largeur de légende `24 + 6 × len(libellé)` | `774`, `788`, `809`, `878`, `898`, `914` |

À 13 pt — le cas du banc — ou sous le réglage Windows « Taille du texte » (100 à 225 %, distinct
du DPI, § 7.2), tout le reste de la fenêtre grandit et ces trois-là restent à 7,5–11 pt. Le
`6 px par caractère` de la légende est vrai pour une police, pas pour une autre.

**Correctif.** Tailles dérivées de `self.font().pointSizeF()` (× 0,75 · × 0,8 · × 1,1), hauteurs
minimales de `fontMetrics().height()`, largeur de légende par
`fontMetrics().horizontalAdvance(libellé)`. Le banc a déjà la boucle des polices ; ajouter les
trois widgets à ce qu'il regarde.

### C5 — Les liens du fil conducteur ne sont pas atteignables au clavier — *sévérité 2, coût une ligne*

`label_fil` est un `QLabel` riche dont les `<a href='n'>` mènent à l'étape (`plugin.py:1814-1818`,
`linkActivated`). Aucun `setTextInteractionFlags` : un `QLabel` riche n'accepte par défaut que
`LinksAccessibleByMouse`. Le seul repère permanent de la fenêtre — celui qui dit « Choisir le
profil en long » ou « vérifier le lancement » — est donc à la souris seulement, dans une fenêtre
dont tout le reste a été rendu navigable (Alt+flèches, F1, Espace).

**Correctif.** `LinksAccessibleByKeyboard | LinksAccessibleByMouse` sur `label_fil` ; Tab atteint
alors le lien, Entrée l'active — et c'est le `QLabel` qui consomme Entrée, pas `keyPressEvent`.
Un contrôle au banc : `QTest.keyClick(label_fil, Key_Return)` après focus change l'onglet.

### C6 — Ruban, jauges et courbe n'ont ni nom ni description accessibles — *sévérité 2*

Dix-huit `setAccessibleName` dans le fichier, aucun sur `RubanApports`, `JaugeAtteinte`,
`CourbeComparaison` (`plugin.py:3675`, `3697`, `3717`). Le tableau redit le ruban et les jauges ;
la courbe n'a d'équivalent textuel que `label_jauges`. Qt expose un widget peint à UI Automation
comme un objet muet (§ 7.2, *Accessibility for QWidget applications*).

**Correctif.** `setAccessibleName` au montage (« Avancement par apport », « Atteinte du
volume », « Cible et débit calculé ») et `setAccessibleDescription` mis à jour dans
`actualiser()` avec la phrase que le widget dessine (« Volume 101,2 % — conforme ») — la valeur
est déjà calculée, il ne manque que de l'écrire dans une propriété. Puis **Accessibility
Insights for Windows**, FastPass, sur la fenêtre ouverte dans le profil TEST : c'est la recette
que la veille du 11 septembre proposait et que le CHECKPOINT liste encore comme restant
(0.8.2, 0.8.3). Elle dira ce que Windows voit — noms, ordre de tabulation, pièges — que le banc
ne peut pas voir.

### C7 — Trois messages parlent encore du « dossier du projet » — *sévérité 1, trivial*

Depuis la 0.7.13, on désigne le **fichier `.prj`** (« Fichier .prj : », « Choisir le projet… »,
`plugin.py:2107-2121`). Trois refus disent encore « choisir d'abord le dossier du projet
HEC-RAS » : `_charger_couches_modele` (`2725`), `_ecrire_dans_geometrie` (`3464`),
`_composer_et_controler` (`5604`). Un utilisateur qui les lit cherche un sélecteur de dossier
qui n'existe plus. C'est la règle des 0.7.14 et 0.7.15 : un mot pour une chose.

**Correctif.** « Onglet 1 : choisir d'abord le fichier .prj du projet (« Choisir le projet… »). »

### C8 — Trois noms pour un geste : « Contrôle paramétrage », « Composition », « Composition et contrôle » — *sévérité 1*

Le bouton dit « Contrôle paramétrage » (`plugin.py:2378`) ; sa boîte de compte rendu est titrée
« Composition et contrôle » (`5766-5767`) ; sa boîte d'échec « Composition » (`5777-5778`). La
0.7.14 avait posé la règle en renommant le classeur : « deux noms pour une chose se lisent comme
deux choses ». **Correctif** : « Contrôle paramétrage — compte rendu » / « Contrôle paramétrage —
échec » ; le banc « « Composition et contrôle » est redimensionnable » suit.

### C9 — Ce que le bouton **écrit** vit dans l'infobulle et l'aide — une tension entre deux décisions — *sévérité 2, décision*

Le 7 septembre (0.7.7) : « Un survol d'infobulle n'est pas un consentement » — le bouton est
renommé pour nommer l'écriture dans la géométrie. Le 9 septembre (0.7.24, demande utilisateur) :
« Contrôle paramétrage », court, l'écriture « dite par l'infobulle et l'aide ». NN/g : une
infobulle ne porte jamais une information vitale (§ 7.4). Les deux décisions sont vôtres ; cette
relecture ne propose pas de renommer une troisième fois.

**Ce qui les réconcilierait sans rallonger le bouton** : le fil conducteur, quand les trois
prérequis sont tenus et rien n'est composé, dit « Définir les objectifs, puis contrôler le
paramétrage » (`plugin.py:2069`). Il pourrait dire « … puis « Contrôle paramétrage » — qui écrit
d'abord vos sections et injections dans la géométrie ». Une ligne, visible depuis les six
onglets, sans modale. À trancher.

### C10 — « Obligatoire » n'est dit que par le placeholder, l'infobulle et le refus — *sévérité 1*

`edit_prefixe_scenario` : placeholder « Q100 — obligatoire » (`plugin.py:3022-3023`), libellé
« Préfixe de scénario : » (`3041`), texte d'aide qui explique ce que le préfixe nomme sans dire
qu'il est requis (`3042-3045`). Un placeholder disparaît à la première frappe (NN/g, formulaires,
§ 7.4). **Correctif** : « Préfixe de scénario (obligatoire) : », ou « Obligatoire : … » en tête
du texte d'aide.

### C11 — Documentation et captures en retard sur la 0.8.4 — *sévérité 2 pour un document livré*

| Document | Ce qu'il dit | Ce qui est vrai |
|---|---|---|
| `calage_apports/LISEZMOI.md:5` | « Version **0.8.2** » | `metadata.txt` : 0.8.4 |
| `LISEZMOI.md:62` | « `calage_apports_0.8.2.zip` … à la racine du dépôt » | `calage_apports_0.8.4.zip` |
| `docs/captures/onglet_*.png` | dernier commit `f7c0244` (0.8.2) | 0.8.3 a changé le Suivi (« repris »), 0.8.4 a déplacé le préfixe à l'onglet 3, remis les deux boutons côte à côte, ajouté l'encadré d'alertes au Suivi : **onglets 3, 4 et 5 ne ressemblent plus aux images du README** |
| `CHECKPOINT.md:7` | « 0.8.4, **NON COMMITÉE** » | `f4aaf6e` du 14/09 |

`captures_plugin.py` a été écrit pour ce cas exact (« une capture périmée ressemble à une
capture »). **Correctif** : `captures_plugin.py --onglets 3,4,5`, les deux lignes du LISEZMOI, la
ligne du CHECKPOINT. **Pour que ça ne revienne pas** : `faire_zip.py` vérifie déjà que les modules
embarqués sont identiques aux sources ; lui faire aussi vérifier que la version citée par
`LISEZMOI.md` est celle de `metadata.txt`.

### C12 — La matrice visuelle des trente scénarios n'est pas rejouable depuis le dépôt — *sévérité 2, méthode*

`docs/ergonomie_2026-09-11-mesures.json` porte trente scénarios (six pages × normal, petit,
sombre, DPI 150, texte 13) avec leurs mesures, mais **aucun script de `src/` ne les produit** :
seuls `captures_plugin.py` et le § 7 du banc (deux polices × six onglets, à 800 × 620) sont
versionnés. La prochaine version ne pourra pas reproduire la matrice, et la mesure sombre d'un
Suivi **rempli** (C1) n'a pas d'outil. **Correctif** : versionner le script des mesures (ou le
fondre au § 7 du banc derrière une option `--matrice`), écrire le JSON dans `docs/`, et donner
au scénario sombre un suivi synthétique.

### C13 — Ce que le banc ne mesure pas — *méthode*

Le § 7 du banc (`test_plugin_qgis.py:2526-2699`) vérifie : fenêtre dans 800 × 620, police et
famille suivies, six onglets identifiables et cliquables, bouton permanent visible, zone
défilante, **champs** non comprimés, défilement possible, dernier champ atteignable, Entrée
inerte, Alt+flèches. Il ne vérifie pas :

- **la compression des étiquettes, boutons et groupes** : le filtre `comprimes` ne retient que
  `QLineEdit`, `QComboBox`, `QAbstractSpinBox` (`2600-2609`) — c'est exactement l'angle mort du
  point ouvert de `STATUT.txt` § 6 « regarder les fenêtres étroites : les widgets maigrissent,
  et c'est le dernier encadré qui encaisse ». Étendre le filtre à `QLabel`, `QPushButton`,
  `QGroupBox` rendrait le défaut mesurable avant de le corriger « à l'aveugle » ;
- **les couleurs** : aucun contraste, aucune palette sombre (voir C1, C2) ;
- **le focus** : visible par `:focus` dans la feuille pour boutons et onglets
  (`interface.py:86`, `92`, `101`), non vérifié pour les champs ; ordre de tabulation non
  parcouru ; les noms accessibles ne sont pas relus (C6) ;
- **les boîtes** : le mannequin enregistre `bouton_defaut`, une seule boîte le vérifie (C3).

### C14 — Le 580 px du HIG QGIS — *note*

Le HIG QGIS 3.44 dit « No dialog should exceed 580 pixels in height and 1000 pixels in width »
(§ 7.2). La fenêtre s'ouvre à 940 × 760, minimum 720 × 520, recette à 800 × 620 ; elle défile
onglet par onglet et se borne à l'écran − 64 px (`plugin.py:1864-1869`). L'écart est raisonné ;
il n'est écrit nulle part. Une phrase à côté de `LARGEUR_PLANCHER_MAX` suffit.

### C15 — Le rang de l'aide est écrit cinq fois — *sévérité 1, maintenance*

`min(5, …)` et `setCurrentIndex(5)` : `plugin.py:1842`, `1862`, `1942`, `1972`, `1978`. Le
commentaire des constantes dit pourtant « Les trois autres rangs n'ont pas de nom : aucun code
n'y renvoie » (`1609-1611`). Le jour où un onglet s'insère, F1 ouvre autre chose et « Suivant »
s'arrête un cran trop tôt, sans un mot — c'est le scénario que les constantes `ONGLET_*` ont été
créées pour éviter. **Correctif** : `ONGLET_AIDE = 5`, `DERNIER_ONGLET = ONGLET_AIDE`, et le
contrôle « les rangs nommés désignent le bon onglet » l'inclut.

### C16 — « Installer… » fige QGIS plusieurs minutes — *assumé, note*

`_installer_interpreteur` tourne sur le fil graphique, sablier posé, et la boîte le dit
(« QGIS restera figé pendant l'opération », `plugin.py:4640-4641`) — c'est assumé dans la
docstring (`4620-4623`). NN/g fixe à 10 s le seuil au-delà duquel un indicateur de progression
et une sortie sont dus (§ 7.4). Les lignes de pip sont déjà collectées (`lignes.append`,
`4711`) : un `QProgressDialog` qui les affiche au fil de l'eau coûterait peu et donnerait au moins
le signe de vie que le sablier ne donne pas au bout de trois minutes. Une amélioration de
confort, pas un défaut — et une décision.

---

## 3. Constats envisagés puis réfutés

Écrits pour qu'on ne les recherche pas.

- **« L'état d'affichage décide du contenu » (piège Sensi § 6.15).** Aucun `isVisible()`,
  `isHidden()` ni `isEnabled()` n'est lu dans `plugin.py` ; `_maj_groupe_classeur` et
  `_maj_resume_fichiers` **posent** la visibilité, ils ne la lisent pas. Réfuté.
- **« Cibles cliquables sous 24 px » (WCAG 2.5.8).** Boutons `padding: 6px 12px` +
  `min-height: 20px` → une trentaine de pixels ; champs `min-height: 24px` ; onglets
  `padding: 8px 12px` (`interface.py:84`, `89`, `91`). Les liens du fil sont « en ligne dans une
  phrase », exemptés. Réfuté par lecture ; à mesurer seulement si une capture le contredit.
- **« Un champ focalisé se pose sous le bord d'une page défilante » (WCAG 2.4.11).**
  `QScrollArea` appelle lui-même `ensureWidgetVisible` sur le widget qui reçoit le focus par
  Tab, et le banc vérifie « le dernier champ est atteignable ». Réfuté pour le clavier ; le clic
  sur un lien du fil conducteur mène à un onglet, pas à un champ.
- **« Une modale en fin de chaîne asynchrone » (piège Sensi § 6.26).** Toutes les boîtes sont
  synchrones dans un slot ; le calage tourne hors de QGIS et n'appelle rien en retour. Sans
  objet.
- **« Informer par une boîte ».** Plus aucune `QMessageBox.information` depuis la 0.8.2 ;
  vérifié par grep et par le banc. Réfuté.
- **« Plancher de 10 pt trop haut pour qui règle QGIS à 8 pt ».** `max(10.0, …)`
  (`plugin.py:1876`) est une décision écrite (« les feuilles QGIS peuvent imposer 8,25 pt »),
  reprise de Sensi. Pas un constat.
- **« Sonder `tasklist` toutes les deux secondes coûte un sous-processus ».** Essayé, mesuré,
  retiré le 6 septembre ; « la friction achète un affichage qui ne ment pas ». Ne pas rouvrir.

---

## 4. Ce qu'aucune lecture de code ne tranchera

- **Les trois widgets peints en Night Mapping, avec un suivi réel** (C1) : l'onglet Suivi d'un
  calage en cours, dans le profil TEST — c'est la seule façon de voir si la courbe se lit.
- **Quel bouton reçoit Entrée** dans les trois boîtes Oui/Non (C3) : appuyer, une fois.
- **Ce que Windows voit** de la fenêtre : Accessibility Insights, FastPass et parcours des
  tab stops (C6) — la veille du 11 septembre l'avait mis au programme.
- **La « Taille du texte » de Windows à 150 %** (pas `QT_SCALE_FACTOR`, pas 13 pt) : ce que
  deviennent le ruban, les jauges et la légende (C4).
- **Les quatre questions du 6 septembre § 4**, toujours ouvertes : la place du bouton contre
  l'ordre de lecture, si le fil conducteur est lu, si l'aide est ouverte spontanément, combien de
  temps un nouvel arrivant met à comprendre qu'il doit sortir dessiner dans QGIS. Un
  *think-aloud* avec trois à cinq ingénieurs sur ces quatre tâches (synthèse § 7.5) coûte une
  demi-journée et n'a jamais été fait.

---

## 5. Ordre proposé

| Ordre | Constats | Coût | Ce que ça règle |
|---|---|---|---|
| 1 | **C3** | trois arguments + trois contrôles au banc | un « Oui » par réflexe pendant un calage |
| 2 | **C1** | ~30 lignes + un scénario sombre au banc | un onglet Suivi illisible en Night Mapping |
| 3 | **C2** | 5 lignes + une fonction de contraste versionnée | textes teal sous 4,5:1 en clair |
| 4 | **C11** | captures ×3, trois lignes de documentation, un contrôle dans `faire_zip.py` | un README et un LISEZMOI qui décrivent la 0.8.2 |
| 5 | **C5, C7, C8, C10, C15** | une ligne chacun | clavier, vocabulaire, noms, rang de l'aide |
| 6 | **C4, C6** | une demi-journée | police du poste et noms accessibles des widgets peints |
| 7 | **C12, C13** | méthode : versionner la matrice, élargir le banc | rejouer la recette, mesurer la compression et les couleurs |
| — | **C9, C14, C16** | décisions | à trancher, pas à coder |

Si ces points sont retenus, la version suivante vaut une passe `captures_plugin.py` et un
`faire_zip.py`, comme les précédentes.

---

## 6. Sources

Synthèse du dépôt `ergonomie` — `ERGONOMIE_SYNTHESE_2026-09-17.md` : § 3.7 (états et
erreurs), § 3.10 (Entrée), § 3.12 (thème et police), § 4.2–4.3 (pièges QSS et signaux),
§ 5.3 (contrôles d'interaction), § 7.2 (Qt `QPushButton`/`QDialogButtonBox`, HIG QGIS, Microsoft
dialogues et text scaling), § 7.3 (WCAG 1.4.3, 1.4.11, 2.4.11, 2.5.8), § 7.4 (NN/g infobulles,
confirmations, temps de réponse), § 7.5 (sévérité 0–4, think-aloud).

Sources primaires citées, consultées le 17 septembre 2026 :
W3C, Understanding 1.4.3 Contrast (Minimum) — https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html ;
W3C, Understanding 1.4.11 Non-text Contrast — https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html ;
Qt 6, QPushButton (`default`, `autoDefault`) — https://doc.qt.io/qt-6/qpushbutton.html ;
Qt 6, QMessageBox::question (`defaultButton`) — https://doc.qt.io/qt-6/qmessagebox.html ;
Qt 6, Accessibility for QWidget applications — https://doc.qt.io/qt-6/accessible-qwidget.html ;
Microsoft, Dialog controls — https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/dialogs-and-flyouts/dialogs ;
Microsoft, Text scaling — https://learn.microsoft.com/en-us/windows/apps/develop/input/text-scaling ;
Accessibility Insights for Windows — https://accessibilityinsights.io/docs/windows/overview/ ;
QGIS 3.44, Human Interface Guidelines — https://docs.qgis.org/3.44/en/docs/developers_guide/hig.html ;
NN/g, Tooltip Guidelines — https://www.nngroup.com/articles/tooltip-guidelines/ ;
NN/g, Confirmation Dialogs — https://www.nngroup.com/articles/confirmation-dialog/ ;
NN/g, Severity Ratings for Usability Problems — https://www.nngroup.com/articles/how-to-rate-the-severity-of-usability-problems/.

---

## 7. Ce que cette relecture a donné, au 18 septembre

Validée par le propriétaire le 17 au soir ; correctifs livrés en **0.8.5** le 18, **sans QGIS** :
écrits depuis un clone Linux, mesurés autrement (plus bas).

| Constat | Suite donnée |
|---|---|
| C1 | `interface.couleur(nom_hex, widget)` — même table que `texte_theme` — et une méthode `couleur()` sur les trois widgets peints ; la colonne Statut et le filet de la bannière suivent. En sombre, l'encre des segments pleins du ruban est le fond de la fenêtre : les teintes remappées sont claires, le blanc n'y tenait plus |
| C2 | `ISL_TEAL_SOMBRE` pour les cinq textes, `COULEUR_STATUT["en cours"]` compris ; le trait de la courbe garde le teal institutionnel |
| C3 | `confirmer(parent, titre, texte, oui, non)` : verbes, refus par défaut **et** en échappement, aucun clic vaut non. **Quatre** boîtes, pas trois : « Chaîne de calage introuvable » (`_diagnostic`) avait échappé au comptage du § 2 |
| C4 | `_taille_police(widget, facteur)`, hauteurs recalculées au `FontChange`, largeurs de légende par `horizontalAdvance` |
| C5 | `LinksAccessibleByKeyboard` sur `label_fil` |
| C6 | noms accessibles au montage, descriptions remises dans `actualiser()` |
| C7, C8, C10, C14, C15 | faits tels que proposés |
| C11 | LISEZMOI et README à jour ; `faire_zip.py` refuse un LISEZMOI ou un README en retard sur `metadata.txt` — vu rouge sur l'ancien LISEZMOI, vert sur le nouveau ; **captures non refaites** (elles exigent QGIS), le README le dit |
| C12, C13 | **non faits** : un script de mesures qu'on ne peut pas lancer serait écrit à l'aveugle ; étendre le filtre « comprimés » touche les fenêtres étroites, que `STATUT.txt` § 6 interdit de traiter sans l'œil sur QGIS |
| C9, C16 | **décisions**, laissées au propriétaire — `STATUT.txt` § 6 |

**Trouvé en mesurant.** `RubanApports.__init__` écrivait `self.sizePolicy().Expanding`, forme non
qualifiée que PyQt6 pur refuse (`AttributeError`) ; le contrôle des « constantes qualifiées » du banc
ne regarde que `QSizePolicy.` et ne pouvait pas le voir. Forme qualifiée posée.

**Ce qui a été mesuré, et comment.** Sans QGIS ni écran : un shim `qgis` renvoyant `qgis.PyQt` vers
PyQt6 6.11 et rendant `qgis.core` et `qgis.gui` inertes a permis d'importer `plugin.py` et de dessiner
les trois widgets peints hors écran, en palette claire (`#f0f0f0`) et sombre (`#323232`), à 10 et
13 pt, avec des données synthétiques. Relevé des couleurs présentes dans les pixels : en sombre,
`#f29d97`, `#91cdaa`, `#bbcad2`, `#7cc4c8` présentes et **aucune teinte brute** ; en clair, les
teintes de charte telles quelles. Hauteurs minimales : 44 / 55 / 190 px à 10 pt, 54 / 62 / 238 px à
13 pt. `confirmer()` : défaut et échappement sur le refus, `False` sans clic, `True` après clic sur le
verbe. Un `QLabel` riche à `LinksAccessibleByKeyboard` : Tab sélectionne le lien, Entrée l'active,
`focusPolicy` passe à `StrongFocus` tout seul. Les contrastes que le banc exige tiennent tous : 4,92
à 6,25:1 en clair, 6,13 à 7,63:1 en sombre. Ce que le shim ne peut pas dire : la fenêtre entière, les
widgets QGIS, le rendu réel sous Windows.

**Le banc** gagne 23 contrôles — § 7 bis, plus un dans la section du suivi, deux dans la boucle des
polices, un après elle — et **n'a pas été rejoué** : il exige QGIS. 301 attendus. C'est la première
chose à faire avec cette version.
