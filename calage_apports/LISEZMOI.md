# Plugin QGIS — Calage des apports

Préparation et contrôle du paquet de calage pour **HEC-RAS uniquement**.
Voir `methodologie_calage_amont_aval.docx`, § 2.4.
Version **0.9.19** : le bouton « Calage apports » s'affiche dans la barre
d'outils « CPN », et la fenêtre prend l'esthétique commune aux extensions de
la maison. Avant, la **0.9.18** : le ménage garde le dossier de sortie, les fichiers du
modèle gardent leur encodage et leurs accents, et le projet chargé est le
`.prj` désigné. Avant, la **0.9.17** : le plan « <préfixe>_avec_apports » apparaît sous ce nom
dans RAS Mapper (le titre est aussi réécrit dans son `.hdf`), et la
suppression des plans d'étape refusée sur un calage non conforme est
annoncée. Avant, la **0.9.16** : **« Importer des hydrogrammes d'un calcul précédent »**
remplace « Reprendre un Excel… » — il recopie dans l'Excel de ce calcul les
hydrogrammes des sections de même nom et les pentes des apports de même nom,
rien d'autre, et dit ce qui a été importé et ce qui reste vide. Les couches
« Sections — PK » et « Injections — PK » disparaissent : le PK s'étiquette
sur les couches de base. Plus de changement d'onglet automatique. Avant, la
**0.9.15** : **plus de recomposition automatique** — elle composait
les préfixes à demi tapés, dossier et classeur compris. Seul le bouton
« Valider la géométrie et générer le fichier des hydrogrammes » compose ; un
réglage changé ensuite porte un **« ! » rouge** sur son champ et sur le titre
de son étape, et le lancement est refusé tant qu'il en reste un. Avant, la **0.9.14** : le changelog
redevient lisible par QGIS — ses signes pour cent sont doublés. Avant, la **0.9.13** : la recherche des interpréteurs Python quitte le fil
graphique — une tâche QGIS annulable, dont le résultat attend la réouverture
de la fenêtre. Avant, la **0.9.12** : un refus de composer — feuille Cibles
saisie sans en-tête « Temps_h » — ne met plus le classeur de côté ; le fichier
reste en place, comme le message le promet. Avant, la **0.9.11** : l'étiquette des cœurs suit
une mesure du jour — 8 demandés, 8 employés par HEC-RAS sur une station à
32 cœurs, 48 h simulées en 1 h 48. Avant, la **0.9.10** : un seul bouton, **« Valider la géométrie et générer le
fichier des hydrogrammes »**, sous le préfixe — il écrit la géométrie,
compose l'Excel et contrôle, et dit ce qui manque ; le **dossier de sortie**
remonte juste au-dessus des hydrogrammes cibles ; l'onglet « Objectifs »
s'appelle **« Paramètres »**. Avant, la **0.9.9** : la **recomposition
automatique** ne plante plus — le
décorateur du curseur d'attente n'acceptait aucun argument, et le minuteur
l'appelait avec deux ; défaut latent depuis la 0.9.5, vu sur le poste de
calcul. Le texte d'attente de l'étape Lancer ne renvoie plus à un bouton
« en bas de la fenêtre » qui n'y est plus. Avant, la **0.9.8** : l'Excel des objectifs existe **dès la saisie du
préfixe** — le dossier de sortie se propose tout seul, « _calage\<préfixe> »
à côté du modèle, modifiable à l'étape Lancer. Avant, la **0.9.7** : le
plugin lit le poste et propose le nombre de cœurs à
demander à HEC-RAS (groupe « Calcul HEC-RAS » de l'étape Lancer, case à
cocher), et la couverture du calage ne compte plus le décalage deux fois.
Avant, la **0.9.6** : le bouton d'écriture rejoint l'étape « Modèle », et
la recomposition automatique ne se ré-entre plus. Avant, la **0.9.5** : le
paquet se recompose tout seul, et le bouton ne
garde que le seul geste irréversible — écrire dans la géométrie HEC-RAS.
Avant, la **0.9.4** : le préfixe rejoint le groupe « Hydrogrammes cibles »,
l'emprise 2D ne masque plus la carte, les étapes disent le bon ordre, et
changer de préfixe s'annonce avant le clic. Avant, la **0.9.3** : le
résultat du calage apparaît enfin dans RAS Mapper
— le plan final est déclaré dans le `.rasmap`, ce que ras-commander ne fait
jamais. Avant, la **0.9.2** : recomposer ne perd plus rien, l'écran dit quand il ne
concorde plus avec le paquet composé, et le Suivi montre le journal en
cours. Avant, la **0.9.1** : l'onglet Objectifs suit l'ordre du parcours —
précision, puis le geste qui ouvre la saisie, puis les hydrogrammes — et une
barre compte la préparation au bas de la fenêtre. Avant, la **0.9.0** :
**cinq onglets** au lieu de six — les Sorties rejoignent
Lancer, avec le préfixe de scénario juste au-dessus du bouton —, un
**récapitulatif** qui dit d'où le calage repart avant qu'on clique, et les
**paramètres hors du classeur**, dans un JSON voisin. Avant : la borne d'un
titre de plan, mesurée (0.8.8), et les lots UX B et C (0.8.7).

## Ce que fait le plugin

**Une seule entrée de menu**, qui ouvre une fenêtre non modale en six
onglets — l'ordre des onglets est celui des décisions.

| Onglet | Rôle |
|---|---|
| 1. Modèle | **Fichier `.prj`** du projet HEC-RAS, plan de référence, géométrie, zone 2D, **profil en long** (axe, sens, PK d’origine) et fenêtre de simulation. Charge les sections, injections et emprises existantes en couches éditables |
| 2. Paramètres | Précision du calage (écarts admis sur le volume et la pointe, bilan de masse, essais), **dossier de sortie** (proposé tout seul : `_calage\<préfixe>` à côté du modèle), puis **Hydrogrammes cibles** : le **préfixe de scénario** — **obligatoire** : sans lui, caler le Q10 après le Q100 effacerait les plans du Q100 — et, sous lui, le bouton **« Valider la géométrie et générer le fichier des hydrogrammes »**, qui écrit les dessins dans le `.gXX` après sauvegarde horodatée, compose l’Excel et contrôle ; gris tant qu’il manque quelque chose, son infobulle le nomme |
| 3. Lancer | appariement apport → section, état des cibles, premier apport à caler, sort des plans d’étape (**conservés par défaut**), cœurs demandés à HEC-RAS, configuration complète, puis **lancement du calage** en arrière-plan |
| 4. Suivi | Apport en cours, essai, atteinte du volume, de la pointe et de la forme, courbes cible et section, **sections déjà calées en vert pointillé**, temps restant. Actualisation automatique quand la rubrique est affichée. Le dossier surveillé est celui du **classeur lancé**, nommé en permanence |
| Aide et configuration | **Diagnostic et paramètres du poste** en tête de page : chaîne de calage et interpréteur HEC-RAS. Mode opératoire avec sommaire et pièges connus en dessous |

**Les six onglets sont en images** dans le README du dépôt, section « La
fenêtre du plugin » — une capture par onglet.

Le bouton **Valider la géométrie et générer le fichier des hydrogrammes**
vit sous le préfixe de scénario, à l'étape Paramètres. **Vert** dès que tout
ce qu'il consomme est prêt, **gris** tant qu'il manque quelque chose — son
infobulle nomme le manquant, et un clic en gris le dit en clair. Les
commandes **Précédent** et **Suivant** facilitent le parcours. Il fait trois
choses, dans cet ordre :

1. il **écrit dans la géométrie HEC-RAS** les sections et injections dessinées
   dans **Modèle**, en remplaçant tout objet de même nom — **c'est le seul geste
   irréversible de la fenêtre**, et une sauvegarde horodatée du `.gXX` le
   précède ;
2. il **compose** les shapefiles normalisés et l'Excel **pré-rempli** ;
3. il **contrôle** — PK, ordre déclaré, position des apports — et **étiquette
   les couches de base** de leur PK (« nom — PK n m »).

Sous lui, **Importer des hydrogrammes d'un calcul précédent** recopie dans
l'Excel de ce calcul, depuis l'Excel d'un autre, les hydrogrammes des
sections de même nom et les pentes des apports de même nom — et rien d'autre.
Le compte rendu, dans la page, nomme ce qui a été importé et ce qui reste
vide ; sans aucune cible commune, rien n'est écrit.

Si la composition échoue après l'étape 1, le message le dit : le modèle a déjà
été modifié. Sinon, le compte rendu de composition **ouvre par ce qui a été
écrit** dans la géométrie.

Le mode opératoire complet vit dans **Aide et configuration** ; ce
qu'écrit l'étape 1, et pourquoi elle n'a pas de bouton à elle, y tient une
section — *Écrire dans la géométrie*.

La fenêtre reste ouverte pendant qu'on dessine : c'est précisément le travail.

Le plugin **ne contient aucune règle de contrôle** : il appelle celles de
`controle_donnees.py` et `geometrie.py`. Une règle modifiée à un seul endroit
s'applique donc aux deux voies d'accès.

Les **calculs longs ne passent pas par QGIS** : un calage représente des heures
et figerait l'interface.

## Installation

**Depuis le dépôt d'extensions PIO**, la voie normale : déclarer une fois
`file://sudouest/users/perrin/16-Dev/1-Utilitaires/1.1-Plugins_QGIS/00-depot_QGIS/plugins.xml` dans *Extensions →
Installer/Gérer les extensions → Paramètres*, cocher **Afficher aussi les
extensions expérimentales**, puis installer **Calage des apports**. QGIS
propose ensuite les mises à jour. Le `LISEZMOI.md` du dépôt détaille la marche.

**Depuis l'archive**, pour un poste sans accès au dépôt.
`calage_apports_<version>.zip` —
`calage_apports_0.9.18.zip` pour cette version — est **à la racine du dépôt** : la télécharger
suffit, il n'y a rien à reconstruire. Le nom porte la version pour qu'on
sache, sur un poste distant, ce qu'on installe ; il n'y en a jamais qu'une
dans le dépôt, la plus récente. Puis, dans QGIS :
*Extensions → Installer/Gérer les extensions → Installer depuis un ZIP*,
la choisir, et cocher **Calage des apports** dans *Extensions installées*.

Pour la reconstruire après une modification des sources :
`python src/faire_zip.py` ; pour la publier ensuite dans le dépôt PIO,
double-cliquer `D:\1-Dev\1-Utilitaires\1.1-Plugins_QGIS\00-depot_QGIS\outils\publier.bat`.

Si l'extension n'apparaît pas dans la liste après installation, cocher
*Extensions → Paramètres → **Afficher aussi les extensions expérimentales***  :
`metadata.txt` porte `experimental=True`, et le gestionnaire masque ces
extensions par défaut.

⛔ **Jamais de lien symbolique ni de jonction vers les sources** dans un profil
QGIS. Sous Windows, QGIS ne sait pas retirer une jonction : une mise à jour ou
une désinstallation depuis le gestionnaire vide le dossier **au travers**,
c'est-à-dire dans les sources — constaté le 23 septembre 2026 sur une jonction
d'essai, QGIS 3.44.14 ; le lien symbolique de dossier n'a pas été essayé, le
traiter pareil. L'installation par lien, conseillée ici pour la mise au point
jusqu'au 24 septembre 2026, est abandonnée avec le passage en phase
opérationnelle. Si un lien existe encore, le retirer par `rmdir`, sans `/s`,
avant toute autre opération.

## Les deux chemins que le plugin doit connaître

**Le dossier de la chaîne de calage**, qui contient `criteres.py`,
`geometrie.py`, `controle_donnees.py`, `livrables.py` et `pont_hecras.py`.

**L'archive l'embarque** : elle porte une copie complète de la chaîne dans
`calage_apports/chaine/`. Sur un poste neuf, installer l'extension suffit — il
n'y a rien à déposer à côté, aucune variable à définir.

Il est malgré tout *cherché*, jamais supposé, parce qu'il diffère selon le mode
d'installation : par lien symbolique, `src/` — au côté du parent du plugin —
**est** la chaîne ; depuis une archive, le plugin atterrit dans le profil QGIS
et son parent est le dossier `plugins/`, qui ne contient rien.

L'ordre est **fixe**, et ne compare aucune date :

1. le dossier désigné à l'exécution (bouton de *Vérifier l'environnement*) ;
2. la variable d'environnement `CALAGE_CHAINE` ;
3. la **copie embarquée** dans l'archive ;
4. `src/` du parent du plugin — ce qui ne vaut que pour l'installation par
   lien symbolique, où la copie embarquée n'existe pas sur le disque.

Les rangs 3 et 4 ne sont donc jamais en concurrence réelle. Une chaîne externe
reste utilisable, mais elle se **désigne** : plus rien ne la retient par hasard.

*La règle précédente retenait la chaîne la plus récente. Elle était
indéterministe dès l'installation : l'extraction d'un ZIP ne restitue pas la
date stockée dans l'archive, les fichiers extraits portent l'heure de
l'installation — la copie embarquée se trouvait donc systématiquement plus
récente que les sources vives d'un poste de développement, et les masquait en
silence. C'était exactement l'accident que cette section prétendait éviter.*

La chaîne réellement utilisée — et sa provenance, embarquée ou externe — est
affichée par **Vérifier l'environnement**.

Les fichiers de `calage_apports/chaine/` sont des **copies**. Les modifier ne
sert à rien : corriger les sources du projet, puis relancer `faire_zip.py`, qui
reconstruit l'archive et vérifie que chaque copie est l'exact jumeau de sa
source.

S'il reste introuvable, **Vérifier l'environnement** (onglet Aide et configuration) propose de
le désigner, et le retient d'une session à l'autre.

**L'interpréteur capable de piloter HEC-RAS** — un `python.exe` **séparé de
celui de QGIS**, disposant de `ras-commander` (≥ 0.99) et `h5py`. Cherché dans
l'ordre : dossier désigné à l'exécution, variable `CALAGE_PYTHON`, puis un
`.venv` voisin de la chaîne. Rien au-delà : un interpréteur deviné « quelque
part » serait employé sans que personne ne sache d'où il vient.

**Si vous n'en avez pas encore** — c'est le cas sur un poste neuf.
*Aide et configuration → **Installer…*** le fait de bout en bout : il cherche les Python
présents sur le poste, propose le meilleur, crée l'environnement, y pose les
paquets et vérifie le résultat. **Il n'y a rien à savoir sur l'emplacement de
Python** : c'est précisément ce que le bouton résout.

La version de `ras-commander` est **vérifiée** : les versions antérieures à
0.99 bornent mal les tableaux d'hydrogramme, et un apport y serait tronqué
sans message.

*À la main*, si le poste interdit à QGIS de sortir sur PyPI alors qu'une
invite de commandes le peut : **la commande exacte est donnée par *Aide et configuration →
Vérifier l'environnement***, qui la construit à partir de la liste que le
plugin exige réellement. Ne pas la recopier ici — elle compte une dizaine de
paquets et a déjà divergé une fois, un environnement bâti sur une liste courte
étant ensuite refusé.

Le bouton **Installer…** réutilise un environnement déjà présent plutôt que de
l'effacer — et le **complète** : pip ne re-résout pas les dépendances d'un
paquet qu'il trouve déjà installé, si bien qu'un environnement où
`ras-commander` était là sans `xarray` restait inutilisable après
« installation ». Depuis la 0.6.1, ce qui manque est nommé par la vérification
puis posé, et revérifié.

Pour figer les deux emplacements sans passer par l'interface :

```bat
set CALAGE_CHAINE=<PROJET>
set CALAGE_PYTHON=%USERPROFILE%\venv-hecras\Scripts\python.exe
```

## Deux contraintes d'environnement, mesurées et non contournables

**h5py est inutilisable dans QGIS.** QGIS embarque sa propre bibliothèque
HDF5 pour GDAL ; dès que `qgis.core` est chargé, `import h5py` échoue sur
`DLL load failed while importing _errors`. Comme `ras-commander` en dépend, il
est inimportable dans le processus QGIS. Aucun ordre d'import ne contourne le
problème : dans un plugin, QGIS est déjà chargé. D'où le pont en
sous-processus (`pont_hecras.py`).

**Le PYTHONPATH de QGIS ne doit pas être transmis.** Un sous-processus lancé
depuis QGIS hérite de `PYTHONPATH` et `PYTHONHOME`, qui pointent vers sa
bibliothèque standard 3.12 ; un interpréteur d'une autre version s'arrête
alors sur `AssertionError: SRE module mismatch`. `noyau.environnement_propre()`
retire les variables `PYTHON*` et place le répertoire de l'interpréteur en tête
du `PATH`.

## Tests

`%CALAGE_PYTHON%` désigne ci-dessous l'interpréteur HEC-RAS ; `chaine\` est le
sous-dossier de la copie embarquée (`calage_apports\chaine\`), ou `..\src\`
(le dossier `src\` du projet, sibling de `calage_apports\`) en installation
par lien symbolique.

```bat
REM noyau du plugin, hors QGIS
%CALAGE_PYTHON% noyau.py

REM pont vers HEC-RAS
%CALAGE_PYTHON% chaine\pont_hecras.py verifier
%CALAGE_PYTHON% chaine\pont_hecras.py autotest
```

Les auto-tests des autres modules embarqués (`calage.py`, `controle_donnees.py`,
`criteres.py`, `geometrie.py`, `livrables.py`, `pilote_hecras.py`,
`style_classeur.py`, `suivi.py`) se lancent de la même manière — les neuf
modules de `chaine\` en portent un, `pont_hecras.py` compris.

`verification_environnement.py` **n'est pas dans l'archive** :
il fait partie des sources du projet, pas de ce qui est distribué.

Pour tester le chargement sous QGIS, **importer `qgis.core` en premier** : le
charger après geopandas casse le chargement des DLL. QGIS le fait lui-même
avant les plugins, mais un test en console doit reproduire cet ordre.

## Ce qui est exigé du poste

**QGIS ≥ 3.34.** Le plugin s'adapte à la façon dont la version installée
déclare ses types de champ (`QMetaType` depuis la 3.38, `QVariant` avant) :
l'essai porte sur la construction réelle d'un champ, jamais sur un numéro de
version.

**Qt 5 ou Qt 6.** Toutes les constantes Qt sont écrites sous leur forme
qualifiée, valable dans les deux.

**Aucune installation Python côté QGIS.** Le Python de QGIS livre déjà
`pandas`, `numpy`, `matplotlib`, `scipy`, `openpyxl`, `geopandas`, `shapely`,
`pyproj` et `pyogrio` ; le plugin n'importe rien d'autre au
chargement. Seul l'interpréteur HEC-RAS, décrit plus haut, est à fournir.

**Windows.** Le lancement du calage en arrière-plan et la détection d'un
HEC-RAS ouvert emploient des mécanismes propres à Windows.

## Vérifié

Le 26 juillet 2026 sur QGIS 3.44.8-Solothurn LTR, Python 3.12.13, GDAL 3.12.2 :
le pont appelé depuis QGIS a listé les objets d'un modèle réel.

Le 8 août 2026, un calage complet mené de bout en bout sur un modèle réel —
7 apports, 8 calculs HEC-RAS, 26 h — et l'ensemble des livrables produit,
profil en long compris.

**Le 2 septembre 2026, deux calages multi-apports sont allés à leur terme,
conformes, à quelques heures d'intervalle** : six apports sur six en 14 h 29,
et douze sur douze en 46 h 07. Dix-huit apports, zéro incident, zéro échec —
et seize d'entre eux calés en un ou deux essais. Volumes de 97,7 à 102,1 % de
la cible, pointes de 98,1 à 101,7 %, formes de 97,1 à 100,0 %.

Le même jour, la suite du plugin (`test_plugin_qgis.py`) est passée pour la
première fois de bout en bout sous QGIS : **149 contrôles, aucun échec**.
Le 3 septembre, **152** : trois de plus sur le dossier que l'onglet Suivi
surveille — celui du classeur lancé, et non celui de l'onglet 3 (0.6.2).

**Le 4 septembre, un troisième calage est allé à son terme**, conforme, six
apports en 16 h 49 — et, pour la première fois, avec des livrables complets
au premier passage. Il a aussi montré que l'alerte de cohérence du décalage
se mesurait sur le mauvais état du modèle ; elle se juge désormais à la fin,
sur les décalages retenus (0.6.3).

Le même jour, le premier lancement depuis un autre poste a montré qu'un
classeur dont la feuille Cibles n'avait plus de colonne « Temps_h » — et
aucun instant sous elle — partait en calage et plantait en arrière-plan. Le
plugin le refuse désormais avant de lancer, en nommant l'en-tête trouvé à la
place ; une cible ne compte comme renseignée que si elle a deux instants en
face de deux débits. Et recomposer par-dessus une feuille Cibles qu'on ne
sait pas relire est refusé : la composition la réécrivait vide, sans un mot,
alors que le plugin promet à l'écran qu'elle préserve les hydrogrammes déjà
saisis (0.6.4).

Une relecture adverse a réfuté ce premier correctif trois fois (0.6.5) : une
colonne de temps remplie de **dates** le passait — et le calcul mourait plus
loin en réclamant 536 Gio de mémoire ; le refus de recomposer cherchait sa
preuve dans la ligne d'en-tête, c'est-à-dire dans ce que l'accident détruit ;
et « Lancer quand même » proposait un calage que la chaîne refuse de toute
façon.

**Le 6 septembre 2026, la suite est passée de bout en bout sur un poste
neuf : 172 contrôles, aucun échec**, avec un modèle et un interpréteur
HEC-RAS. Elle n'y arrivait pas, et ce n'était pas le plugin : **sept
défauts du banc** l'en empêchaient, tous du même motif — *il supposait le
modèle et le poste de son auteur*. Un chemin de suivi figé au lieu de celui
que la fenêtre surveille (seize faux échecs, puis un plantage), un
garde-fou qui plantait faute de son fichier de configuration, un modèle
sans objets de calage qui emportait la suite, une date de fenêtre codée en
dur, un axe impossible à bâtir sur un apport unique, `EPSG:2154` déclaré en
dur pour des coordonnées réelles — sur un modèle de l'Indiana, la
reprojection rendait « Coordinates with non-finite values are not
allowed » —, et le chemin de QGIS supposé sous `QGIS\LTR`.

Le même jour, le bouton **« Installer l'environnement Python HEC-RAS »** a
été mené à bout pour la première fois, **depuis QGIS** et par ses deux
chemins — création à partir de rien, et reprise d'un environnement
présent. Douze paquets posés et vérifiés en 56 s. C'est le lancement depuis
QGIS qui comptait : c'est là, et nulle part ailleurs, que son environnement
fuyait dans les sous-processus de pip.

Et **l'ergonomie de la fenêtre a été relue** — six lectures indépendantes,
puis une passe de réfutation. Seize constats sur dix-huit corrigés ; le
détail est dans `docs/ergonomie_2026-09-06.md`, y compris ce
qu'il ne faut **pas** toucher.

**Le 11 septembre 2026, la 0.8.2** : **258 contrôles, aucun échec**. Le
débordement de l'onglet Objectifs à 13 pt, présent depuis la 0.8.0, est
corrigé : la page demandait 773 px pour 750 disponibles, elle en demande
514. La relecture automatique des cibles et la mémoire de la géométrie
sont éprouvées au banc, pas encore par un usage réel.

**La 0.8.4, le 14 septembre : 278 contrôles, aucun échec.**

**La 0.8.5, le 18 septembre 2026, vient d'une relecture ergonomique**
(`docs/ergonomie_2026-09-17.md`) : seize constats tenus, sept pistes
écartées. Le banc gagne **23 contrôles** — contrastes des deux thèmes,
couleurs remappées des widgets peints et du tableau, défaut des quatre
questions, liens du fil au clavier, noms accessibles, police des widgets
peints — mais **n'a pas été rejoué** : il exige QGIS, et cette version a
été écrite depuis un clone sans lui. Ce qui a été mesuré à sa place : les
trois widgets peints dessinés hors écran sous PyQt6 en clair et en sombre,
à 10 et 13 pt — couleurs remappées présentes, hauteurs qui suivent la
police —, et `confirmer()` éprouvée pour son défaut, son échappement et son
retour sans clic. Le passage du banc sous QGIS est la première chose à
faire avec cette version.

**La 0.8.6, le même jour, fusionne la revue de qualité de la 0.8.4** menée
le 17 sur une branche : `classeur` devient une propriété qui rafraîchit le
groupe des objectifs, le Suivi ne relit le journal que s'il a changé,
`noyau.dernier_journal` retrouve les journaux là où `lancer_calage` les
nomme, et la chaîne coupe le compte rendu HEC-RAS à l'en-tête du tableau des
temps. L'autotest de `noyau.py` est vert ici ; celui de `pilote_hecras.py`
s'arrête à l'import de `ras-commander`, absent de ce clone, après ses six
premiers contrôles ; le banc QGIS et `pont_hecras.py autotest` restent à
rejouer sur le poste.

**La 0.8.7, le 20 septembre 2026, porte les lots UX B et C.** Le fil
conducteur dit ce que le bouton de contrôle écrit — géométrie HEC-RAS,
sauvegarde horodatée, fichiers produits. `installation.py` confie la
création du venv, `pip` et la vérification à un `QgsTask` : phases
affichées, journal et erreurs dans le journal QGIS, réglage du Python
enregistré seulement après succès vérifié, second lancement refusé
pendant le travail. Il n'y a **pas d'annulation au milieu de pip**, et la
recherche initiale des interpréteurs reste **synchrone**. Banc sous QGIS
3.44.7 / Qt 5.15.13 : **299 contrôles réussis** ; la recette visuelle et
métier sur le poste ISL reste à faire.

**La 0.8.8, le 20 septembre 2026, remplace une déduction par deux faits.** Le
champ `Short Identifier`, dont RAS Mapper fait le nom du dossier de résultats,
accepte **au moins 40 caractères** : une règle de 40 tapée dans le champ sous
HEC-RAS 7.0.1, le plan enregistré, la ligne du `.pNN` relue intacte. La borne
de 30 venait du plus long **exemple** d'un relevé de 103 plans, pas d'un essai.
Mais le plafond utile n'est ni 30 ni 40 : **ras-commander 0.99.1 lève
`ValueError` au-delà de 32** sur `Plan Title` et `Flow Title`, dans
`clone_plan` et `clone_unsteady` — que le pilote appelle tous deux avec le
titre d'étape. Monter plus haut ne ferait que déplacer le refus du contrôle
vers le milieu du calage ; un `assert` le rappelle dans `pilote_hecras.py`.
La borne est donc **32**, et elle appartient à la bibliothèque, pas au
format. Second correctif : le
contrôle du classeur éprouve le titre de reprise pour **chaque** départ
possible. Il ne jugeait que « Premier_apport », paramètre qui s'écrit **au
lancement**, donc après le contrôle — un préfixe trop long passait le
contrôle et faisait refuser le calage une fois lancé.

**La 0.9.0, le 20 septembre 2026, repond a trois demandes.**

**Cinq onglets.** « Sorties » n'existe plus : le dossier de sortie, ses
sous-dossiers, le sort des plans d'étape et la configuration complète sont
dans « Lancer », après « Apports à déterminer ». Depuis la 0.9.7, « Lancer »
porte aussi le groupe **Calcul HEC-RAS** : le plugin lit le poste (cœurs de
performance sur un processeur hybride), propose un nombre de cœurs et, si la
case « Demander N cœurs à HEC-RAS pour chaque calcul » est cochée, la chaîne
l'écrit dans chaque plan d'étape juste avant son calcul — le plan de référence
n'est pas modifié. L'étiquette dit ce que le plan demande déjà et si cocher
changera quelque chose. Le **préfixe de scénario**
quitte « Objectifs » et se pose juste au-dessus du bouton — il nomme les
plans que ce bouton crée, et c'est cette portée-là qui décide de sa place.
L'ordre de la page est celui de la décision : apports, sorties, préfixe,
lancement.

**Le lancement dit ce qu'il va faire.** Au-dessus du bouton, en permanence :
d'où le calage repart, de quel plan d'étape — **nommé avec son préfixe**,
tel qu'il figure dans le gestionnaire de plans —, quels apports sont tenus
pour calés, lesquels seront calculés. La boîte de reprise, elle, ne se pose
que s'il y a des apports **validés** à perdre : après un **échec**, l'apport
d'arrêt n'est pas validé et rien en aval n'a tourné, donc rien ne se perd,
donc elle ne s'ouvrait pas — et aucun écran ne disait d'où l'on repartait.
Seul le journal le disait, après le lancement.

**Les paramètres quittent le classeur.** Ils vivent dans un JSON qui porte
le nom du classeur, à côté de lui : `donnees_calage_Q100.xlsx` va avec
`donnees_calage_Q100.json`. **Les deux se déplacent ensemble** — le contrôle
le dit si l'un manque. Le classeur ne garde que ce qu'on y écrit,
« Correspondance » et « Cibles » ; les commentaires des paramètres
descendent dans la feuille de garde, celle qui s'ouvre. Un classeur composé
**avant** cette version est encore lu par sa feuille, sans rien demander :
un calage en cours ne s'arrête pas parce que l'outil a changé d'avis sur le
rangement de ses paramètres.

**La 0.9.1 applique a « Objectifs » la regle que la 0.9.0 a posee pour
« Lancer » :** l'ordre de la page est celui du parcours. La **precision du
calage** vient d'abord — c'est ce qu'on vise ; puis la ligne qui demande de
cliquer **Controle parametrage** pour composer l'Excel et pouvoir y saisir
les hydrogrammes ; puis l'**Excel des hydrogrammes objectifs** ; puis **ce
que ces hydrogrammes portent**. La page s'ouvrait jusque-la sur le groupe de
l'Excel, grise tant qu'aucun n'est compose — et la ligne qui disait comment
le degriser vivait **dedans**. Elle ne renvoie plus non plus a un prefixe
« ci-dessus » : il a change d'onglet en 0.9.0, et la consigne le suivait
sans le dire.

**Une barre de progression accompagne « Controle parametrage »**, au bas de
la fenetre. Elle compte les **quatre etapes de la saisie avant lancement** —
modele charge, profil en long, dossier de sortie, paquet compose — et porte
son compte **en chiffres** : une barre aux trois quarts ne dirait pas qu'il
manque le dossier de sortie. **Elle ne parle pas du calage**, qui dure des
heures et se lit a l'onglet Suivi. Elle lit la meme liste que le fil
conducteur : deux comptes qui divergeraient donneraient une barre pleine
sous un fil qui reclame encore une etape. Le fil, lui, ne dit plus le
compte — les deux se lisaient a trois centimetres l'un de l'autre.

**Trois defauts que seule la fenetre REELLE a montres**, le 20 septembre
2026, sur le QGIS du poste :

- **QGIS ne savait plus lire la version du plugin.** Une ligne de changelog
  a la colonne zero rend `metadata.txt` illisible par `configparser` : le
  format veut une valeur poursuivie sur des lignes INDENTEES.
  `pluginMetadata("calage_apports", "version")` rendait `__error__` depuis
  la 0.8.5, et le gestionnaire d'extensions affichait une version vide.
  `faire_zip.py` refuse maintenant une archive dont QGIS ne lirait pas la
  version : le meme fichier, lu par les deux chemins, doit dire la meme
  chose.
- **Le recapitulatif de reprise restait vide a l'ouverture.** Rien ne
  l'appelait avant qu'on touche le premier apport ou le prefixe. Le banc
  l'appelait a la main, et ne pouvait donc pas le voir.
- **Le compte de preparation etait dit deux fois**, dans le fil et dans la
  barre.

**La 0.9.2 repond a trois demandes du 20 septembre.**

**Recomposer ne perd plus rien.** Depuis la 0.8.4, deux prefixes donnent
deux classeurs. Avec le MEME prefixe, recomposer reecrivait le fichier en
place : les cibles et les pentes y survivaient — elles sont relues et
reportees —, mais pas une feuille ajoutee a la main, une mise en forme, une
colonne de travail. L'ancien classeur est desormais **mis de cote,
horodate**, exactement comme la geometrie l'est deja avant d'etre ecrite.
**Le nom canonique ne bouge pas** : c'est celui que la chaine lit, et le
prefixe existe pour qu'il soit previsible.

**L'ecran dit quand il ne concorde plus avec le paquet.** Le paquet compose
est un instantane : il fige le prefixe, les dossiers, les tolerances et le
modele au moment du clic. Rien n'empechait de changer ensuite le prefixe ou
la precision et de lancer — **le calage lit le paquet, pas l'ecran**. Onze
reglages sont compares a chaque modification, et l'ecart est nomme sous
« Preparation du lancement », avec les deux valeurs. Le controle **ne
corrige rien** : recomposer est un geste de l'utilisateur, et il ecrit dans
la geometrie.

**Le Suivi montre le journal en cours**, repliable et deroulant. L'encadre
des alertes ne retient que les lignes portant un mot d'alerte : ce qui
echoue **sans** l'un de ces mots n'y paraissait pas, et l'on ne voyait pas
non plus ou le calage en etait quand il s'est arrete. Une seule lecture du
fichier alimente les deux vues, et le journal **ne se deplie jamais tout
seul** — un journal qui s'ouvre a chaque ligne rendrait la page sautante
pendant des heures.

**La 0.9.3 fait apparaitre le resultat du calage dans RAS Mapper.**

Un calage abouti laissait un plan « <prefixe>_avec_apports » avec son
`.pNN.hdf` complet — 300 a 420 Mo de resultats — et **RAS Mapper ne
montrait rien**. L'arbre *Results* de RAS Mapper ne parcourt pas le
dossier : il liste ce que le **`.rasmap`** declare, et ras-commander ne
l'ecrit **jamais** — c'est l'interface HEC-RAS qui inscrit cette ligne
quand elle calcule elle-meme. Mesure du 21 septembre 2026 sur deux
modeles : sur le premier, **treize** plans calcules par la chaine,
**zero** declare ; sur le seconde, seuls les plans faits a la main y
figuraient.

`conclure()` inscrit desormais le plan final dans le bloc `<Results>`. La
couche existante se retrouve par son **fichier**, non par son nom — lors
d'un retitrage, c'est le nom qui change : relancer un calage **renomme** au
lieu d'empiler. Les titres sont echappes, le fichier est relu et reparse
apres ecriture, et **rien n'echoue** si le `.rasmap` manque ou n'a pas de
bloc `<Results>` : le calage est fini, ses resultats sont bons, et la
phrase du journal le dit.

**Non verifie : l'affichage dans RAS Mapper lui-meme**, qui demande de
l'ouvrir. Et les plans d'ETAPE, eux, ne sont pas declares — seul le plan
final l'est, comme demande.

**La 0.9.4 repond a quatre demandes du 21 septembre.**

**Le prefixe rejoint le fichier qu'il nomme.** Il entre DANS le groupe du
classeur, renomme **« Hydrogrammes cibles »** : c'est la premiere chose a
renseigner pour qu'il y ait un classeur, et le nom du fichier se lit deux
lignes plus bas. La raison de l'avoir tenu dehors depuis la 0.8.4 — « le
groupe voisin se grise » — a ete **verifiee** et n'en est plus une :
`_maj_groupe_classeur` ne desactive que trois enfants, jamais le groupe.
Le banc l'eprouve maintenant, au lieu de s'y fier.

**L'emprise 2D arrive en contour rouge, sans remplissage.** Elle prenait
l'aplat de couleur aleatoire de QGIS et masquait le maillage, les sections
de controle et les lignes d'injection — tout ce qu'on vient regarder
dessous. C'est un contour qu'on veut voir : l'emprise sert a savoir ou
finit la zone de calcul.

**Les etapes disent le bon ordre.** Les listes de l'aide decrivaient encore
six rubriques avec « Sorties » en deuxieme position. Le dossier de sortie
se specifie **apres** les objectifs : c'est un reglage du lancement, et il
vit dans « Lancer » depuis la 0.9.0.

**Changer le prefixe puis recomposer est annonce AVANT le clic.** Le geste
etait signale comme « supprime les apports ». Mesure faite : **rien n'est
supprime** — l'ancien classeur garde ses cibles, et la correspondance du
neuf est correctement reconstruite. Mais le nouveau nait **vide** et la
fenetre bascule dessus : a l'ecran, c'est indiscernable d'une perte. La
fenetre le dit desormais, et nomme le fichier ou le travail se trouve
encore. **Les cibles ne sont pas recopiees** : un Q10 n'a pas les
hydrogrammes d'un Q100, et les reporter fabriquerait un calage faux qui
aurait l'air juste.

**La 0.9.5 rend la composition automatique.**

« Controle parametrage » faisait **trois** choses : ecrire les couches dans
la geometrie HEC-RAS, composer le paquet, lancer les controles. Les deux
dernieres sont bon marche et reversibles — le classeur garde sa version
precedente — et se font desormais **seules**, une seconde et demie apres le
dernier changement. La premiere ne l'est pas : elle **remplace des objets
dans le modele du client**. Elle reste un bouton, renomme **« Ecrire dans
la geometrie HEC-RAS »**, qui dit enfin ce qu'il fait.

**On ne recompose que s'il y a un ecart** entre l'ecran et le paquet — le
controle de coherence de la 0.9.2 le sait deja, et « composer a chaque
signal » aurait compose pour rien neuf fois sur dix. Jamais pendant qu'un
calage tourne : il lit le classeur qu'on reecrirait. Jamais avant la
premiere composition, qui reste le geste du bouton puisque c'est elle qui
ecrit dans le modele. Le **bandeau nomme ce qui a ete reporte** — « ecart
de pointe admis. Controle sans erreur. » — et les erreurs du controle y
passent en avertissement, sans boite.

**Une consequence assumee** : la sauvegarde du classeur passe de
l'horodatage a **un seul niveau**, `…​.precedent.xlsx`. Datee, elle
convenait a un geste rare ; automatique, une copie par frappe enterrerait
le dossier de sortie — souvent un partage reseau. C'est la regle deja
prise en 0.8.3 pour le suivi : un seul niveau, parce qu'une pile obligerait
a choisir laquelle montrer.

**La 0.9.6 remet le bouton la ou il agit, et corrige un defaut de la 0.9.5.**

**Il rejoint l'etape « Modele ».** Il avait demenage quatre fois en cinq
versions avant de descendre au bas de la fenetre en 0.7.24, avec une raison
juste : « ce geste consomme les trois premiers onglets et prepare le
quatrieme ». Cette raison a disparu avec la 0.9.5 — il ne compose plus rien.
Ce qu'il consomme tient desormais **tout entier dans cet onglet** : le
projet, le plan, la zone 2D, les deux couches. Et ce qu'il ecrit s'y
dessine. Ses prealables retrecissent avec lui : ni axe, ni dossier de
sortie, qui servaient a composer. Son compte rendu va **dans la page**,
sous le bouton qui l'a produit ; l'echec reste une boite, parce que c'est
une erreur qu'il faut lire.

**Et un defaut de la 0.9.5, corrige.** La recomposition automatique pouvait
se **re-entrer** : le minuteur partait pendant qu'une composition tournait —
elle ecrit des fichiers et traite des evenements Qt en chemin —, deux
ecritures concurrentes sur les memes fichiers, et le processus s'arretait
**sans trace**, code 127. Reproduit au banc. Un verrou empeche maintenant
deux compositions a la fois, et aucun rendez-vous n'est pose tant que tous
les prealables ne sont pas la : un minuteur qui part sans cesse finit par
partir au mauvais moment.

> Ce que les calages livrés n'ont PAS rencontré : un volume plancher, un
> apport refusé, un modèle incohérent. Les garde-fous qui traitent ces cas
> n'ont donc été éprouvés qu'au banc.
