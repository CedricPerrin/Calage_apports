# Plugin QGIS — Calage des apports

Préparation et contrôle du paquet de calage pour **HEC-RAS uniquement**.
Voir `methodologie_calage_amont_aval.docx`, § 2.4.

## Ce que fait le plugin

**Une seule entrée de menu**, qui ouvre une fenêtre non modale en six
onglets — l'ordre des onglets est celui des décisions.

| Onglet | Rôle |
|---|---|
| 1. Modèle | le **fichier `.prj`** du projet HEC-RAS — et non le dossier qui le contient —, plan de référence, géométrie, zone 2D, fenêtre de simulation, **axe hydraulique**. Charge les sections, injections et emprises **existantes** en couches **éditables**, et écrit dans le `.gXX` celles qu'on y dessine (sauvegarde horodatée) |
| 2. Objectifs et précision | ce qu'on vise et avec quoi : l'**écart admis** sur le volume et sur le débit de pointe — le résultat, lui, se lit en pourcentage d'atteinte de la cible —, le nombre maximal d'essais, et l'**Excel des hydrogrammes objectifs** où ils se saisissent (ouverture, reprise d'un calcul précédent, pente des apports) |
| 3. Résultats | dossiers de sortie et de suivi, relecture d'un hydrogramme calculé (export CSV), résumé de la configuration |
| 4. Lancer | appariement apport → section, état des cibles, premier apport à caler, **préfixe de scénario** (« Q100 » : sans lui, caler le Q10 après le Q100 sur le même modèle efface les plans du Q100), **lancement du calage** en arrière-plan |
| 5. Suivi | où en est le calcul : apport en cours, essai, atteinte du volume, de la pointe et de la forme, courbes cible et section, temps restant. Se rafraîchit tout seul tant qu'il est affiché. Le dossier surveillé est celui que désigne le **classeur lancé** — pas celui de l'onglet 3 — et il est nommé **en permanence** sous la bannière, y compris pendant que le calage tourne |
| Aide et configuration | mode opératoire, pièges connus, et les deux emplacements du poste — chaîne de calage et interpréteur HEC-RAS |

**Les six onglets sont en images** dans le README du dépôt, section « La
fenêtre du plugin » — une capture par onglet.

Le bouton **Écrire, composer et contrôler**, permanent en bas de la fenêtre,
fait les trois choses que son nom annonce, dans cet ordre :

1. il **écrit dans la géométrie HEC-RAS** les sections et injections dessinées
   à l'onglet 1, en remplaçant tout objet de même nom — **c'est le seul geste
   irréversible de la fenêtre**, et une sauvegarde horodatée du `.gXX` le
   précède ;
2. il **compose** les shapefiles normalisés et l'Excel **pré-rempli** ;
3. il **contrôle** — PK, ordre déclaré, position des apports — et ajoute une
   **couche des PK à la carte**.

Si la composition échoue après l'étape 1, le message le dit : le modèle a déjà
été modifié.

La fenêtre reste ouverte pendant qu'on dessine : c'est précisément le travail.

Le plugin **ne contient aucune règle de contrôle** : il appelle celles de
`controle_donnees.py` et `geometrie.py`. Une règle modifiée à un seul endroit
s'applique donc aux deux voies d'accès.

Les **calculs longs ne passent pas par QGIS** : un calage représente des heures
et figerait l'interface.

## Installation

**Depuis l'archive.** `calage_apports.zip` est **à la racine du dépôt** :
la télécharger suffit, il n'y a rien à reconstruire. Puis, dans QGIS :
*Extensions → Installer/Gérer les extensions → Installer depuis un ZIP*,
la choisir, et cocher **Calage des apports** dans *Extensions installées*.

Pour la reconstruire après une modification des sources :
`python src/faire_zip.py`.

Si l'extension n'apparaît pas dans la liste après installation, cocher
*Extensions → Paramètres → **Afficher aussi les extensions expérimentales***  :
`metadata.txt` porte `experimental=True`, et le gestionnaire masque ces
extensions par défaut.

**Par lien symbolique**, préférable pendant la mise au point : le plugin suit
alors les modifications du dossier projet sans réinstallation. Le profil QGIS
actif n'est pas nécessairement `default` — le lire dans le titre de la fenêtre,
ou sous *Préférences → Profils utilisateur*, et le substituer à `<PROFIL>`
ci-dessous.

```bat
REM invite de commandes en administrateur
REM <PROFIL> : le profil QGIS actif   <PROJET> : le dossier de ce projet
mklink /D ^
  "%APPDATA%\QGIS\QGIS3\profiles\<PROFIL>\python\plugins\calage_apports" ^
  "<PROJET>\calage_apports"
```

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

S'il reste introuvable, **Vérifier l'environnement** (onglet Aide) propose de
le désigner, et le retient d'une session à l'autre.

**L'interpréteur capable de piloter HEC-RAS** — un `python.exe` **séparé de
celui de QGIS**, disposant de `ras-commander` (≥ 0.99) et `h5py`. Cherché dans
l'ordre : dossier désigné à l'exécution, variable `CALAGE_PYTHON`, puis un
`.venv` voisin de la chaîne. Rien au-delà : un interpréteur deviné « quelque
part » serait employé sans que personne ne sache d'où il vient.

**Si vous n'en avez pas encore** — c'est le cas sur un poste neuf.
*Aide → **Installer…*** le fait de bout en bout : il cherche les Python
présents sur le poste, propose le meilleur, crée l'environnement, y pose les
paquets et vérifie le résultat. **Il n'y a rien à savoir sur l'emplacement de
Python** : c'est précisément ce que le bouton résout.

La version de `ras-commander` est **vérifiée** : les versions antérieures à
0.99 bornent mal les tableaux d'hydrogramme, et un apport y serait tronqué
sans message.

*À la main*, si le poste interdit à QGIS de sortir sur PyPI alors qu'une
invite de commandes le peut : **la commande exacte est donnée par *Aide →
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

> Ce que les calages livrés n'ont PAS rencontré : un volume plancher, un
> apport refusé, un modèle incohérent. Les garde-fous qui traitent ces cas
> n'ont donc été éprouvés qu'au banc.
