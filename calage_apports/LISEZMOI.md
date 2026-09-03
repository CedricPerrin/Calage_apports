# Plugin QGIS — Calage des apports

Préparation et contrôle du paquet de calage pour **HEC-RAS uniquement**.
Voir `methodologie_calage_amont_aval.docx`, § 2.4.

## Ce que fait le plugin

**Une seule entrée de menu**, qui ouvre une fenêtre non modale en six
onglets — l'ordre des onglets est celui des décisions.

| Onglet | Rôle |
|---|---|
| 1. Modèle | projet HEC-RAS, plan de référence, zone 2D, fenêtre de simulation. Charge les sections, injections et emprises **existantes** en couches **éditables**, et écrit dans le `.gXX` celles qu'on y dessine (sauvegarde horodatée) |
| 2. Profil en long | axe hydraulique — PK et profil — et précision attendue sur le volume et sur le débit de pointe |
| 3. Résultats | dossiers de sortie et de suivi, relecture d'un hydrogramme calculé (export CSV), résumé de la configuration |
| 4. Lancer | appariement apport → section, cibles restant à saisir, reprise d'un classeur d'un calcul précédent, premier apport à caler, **préfixe de scénario** (« Q100 » : sans lui, caler le Q10 après le Q100 sur le même modèle efface les plans du Q100), **lancement du calage** en arrière-plan |
| 5. Suivi | où en est le calcul : apport en cours, essai, atteinte du volume, de la pointe et de la forme, courbes cible et section, temps restant. Se rafraîchit tout seul tant qu'il est affiché |
| Aide | mode opératoire, pièges connus, et diagnostic de l'environnement |

Le bouton **Composer et contrôler**, permanent en bas de la fenêtre, écrit les
shapefiles normalisés et un classeur **pré-rempli**, puis lance tous les
contrôles — PK, ordre déclaré, position des apports — et ajoute une **couche
des PK à la carte**.

La fenêtre reste ouverte pendant qu'on dessine : c'est précisément le travail.

Le plugin **ne contient aucune règle de contrôle** : il appelle celles de
`controle_donnees.py` et `geometrie.py`. Une règle modifiée à un seul endroit
s'applique donc aux deux voies d'accès.

Les **calculs longs ne passent pas par QGIS** : un calage représente des heures
et figerait l'interface.

## Installation

**Depuis l'archive** — *Extensions → Installer/Gérer les extensions →
Installer depuis un ZIP*, choisir `calage_apports.zip`, puis cocher
**Calage des apports** dans *Extensions installées*.

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

**Si vous n'en avez pas encore** — c'est le cas sur un poste neuf :

```bat
python -m venv %USERPROFILE%\venv-hecras
%USERPROFILE%\venv-hecras\Scripts\python.exe -m pip install "ras-commander>=0.99" h5py
```

puis le désigner dans *Aide → Vérifier l'environnement*, qui le retient d'une
session à l'autre. La version de `ras-commander` est **vérifiée** : les
versions antérieures à 0.99 bornent mal les tableaux d'hydrogramme, et un
apport y serait tronqué sans message.

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

> Ce que ces deux calages n'ont PAS rencontré : un volume plancher, un apport
> refusé, un modèle incohérent. Les garde-fous qui traitent ces cas n'ont donc
> été éprouvés qu'au banc.
