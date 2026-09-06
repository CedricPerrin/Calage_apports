# Sessions des 5 et 6 septembre 2026 — le poste neuf

Note de reprise autonome, tenue au fil de deux sessions. Ce qui a été
**mesuré** ici est daté ; ce qui reste à décider est au § 7.

> **Une conclusion de la première version était fausse** : elle annonçait
> les sources 0.6.7–0.6.9 perdues ou non poussées. Le clone était
> simplement sur `main`. Tout est sur
> `claude/connaissance-des-md-qjbpro`, à 0.7.0. Corrigé au § 1.

## 1. Le poste, et où sont les sources

`C:\Users\cedri` — Windows 11, QGIS **3.44.14-Solothurn**, profil
`default`, Python **3.12.14**.

| | |
|---|---|
| `origin/main` | 0.6.6 |
| `origin/claude/connaissance-des-md-qjbpro` | **0.7.0** — la branche de travail |
| plugin installé dans le profil QGIS | **0.6.9**, copie d'archive (pas un lien symbolique) |

Le clone est désormais sur la bonne branche. **Le greffon installé dans
QGIS reste en 0.6.9** : il est en retard d'une version sur les sources.
Cela n'a pas gêné les contrôles — voir § 2, le banc teste les sources.

## 2. Les 152 contrôles — RÉPONSE COMPLÈTE

### Ce qu'il faut, et rien de plus

1. **Le Python de QGIS**, jamais celui de la chaîne :
   `"C:\Program Files\QGIS 3.44.14\bin\python-qgis-ltr.bat" test_plugin_qgis.py`
   (`python3.exe` appelé directement ne trouve pas ses bibliothèques).
2. **`QGIS_PREFIX_PATH`** — à poser sur ce poste :
   `C:\Program Files\QGIS 3.44.14\apps\qgis-ltr`. Le défaut codé dans
   `test_plugin_qgis.py:54` est `C:\Program Files\QGIS\LTR\apps\qgis-ltr`,
   qui n'existe pas ici. Sans lui, MDAL n'est pas trouvé.
3. **`CALAGE_PYTHON`** — fait : `venv-hecras` créé et **figé au niveau
   utilisateur** (§ 4). QGIS doit être **redémarré** pour le voir.
4. **Un modèle de calage** — `--modele <dossier>` (ou
   `CALAGE_MODELE_ESSAI`) et `--objet <nom d'une condition limite>`.
   **C'est le seul manque qui subsiste.**

**Le banc teste les SOURCES du dépôt**, pas la copie installée :
`test_plugin_qgis.py:106-108` charge le greffon depuis
`RACINE/calage_apports/`. Aucune réinstallation n'est nécessaire avant de
lancer la suite — réserve levée.

### Ce que ça donne, mesuré le 6 septembre

| état du poste | résultat |
|---|---|
| au départ, sans modèle | 9 OK, **16 échecs**, plantage ligne 1078 |
| après correction du banc (§ 3.1) | 92 OK, 2 échecs, aucun plantage |
| après unification du garde-fou (§ 3.3) | 93 OK, 1 échec |
| après `venv-hecras` complet | **94 OK, 0 échec**, sans modèle |
| avec Muncie sans objets de calage | 125 → 126 OK, 8 échecs |
| sur le plan **TEST**, 1 apport / 1 section | 6 OK, plantage → **132 OK**, 4 échecs |
| sur le plan **TEST**, 2 apports / 2 sections bien implantés | **151 OK, 0 ÉCHEC** ✅ |

> **La suite est passée de bout en bout le 6 septembre 2026.**
> *« La fenêtre du plugin s'exécute de bout en bout. »*
> Seul reste 1 « ignoré » : `.affaires` absent — 3 contrôles de noms non
> joués. C'est un fichier de configuration non versionné, pas un défaut.

### Le modèle qui a servi

`Documents\HECRAS\Example_Projects_7_0\2D Unsteady Flow Hydraulics\Muncie`,
plan **TEST** (`Muncie.p02`, géométrie `g02`), auquel deux `BC Line` et
deux `Reference Line` ont été ajoutées puis calculées.

```bat
set QGIS_PREFIX_PATH=C:\Program Files\QGIS 3.44.14\apps\qgis-ltr
"C:\Program Files\QGIS 3.44.14\bin\python-qgis-ltr.bat" test_plugin_qgis.py ^
    --modele    "<...>\Muncie" ^
    --plan      "<...>\Muncie\Muncie.p02.hdf" ^
    --geometrie "<...>\Muncie\Muncie.g02" ^
    --objet     "BC Line 1"
```

**L'implantation compte, et le greffon la contrôle.** Au premier essai il
a refusé : *« aucune ligne d'injection en amont de : Reference Line 2 »*.
C'était juste — projetée sur l'axe, cette section tombait à PK −264, en
amont du premier apport. Une fois déplacée en aval de `BC Line 1`,
l'ordre devient celui d'un calage : chaque apport suivi de sa section.

| PK | objet |
|---|---|
| 0 | BC Line 2 |
| 1 263 | Reference Line 1 |
| 1 710 | BC Line 1 |
| 2 344 | Reference Line 2 |

Réserve : cet ordre découle de l'axe que **le banc fabrique** (centroïdes
des injections triés par Y croissant). En usage réel, c'est l'axe
hydraulique dessiné par l'utilisateur qui décide de l'amont.

## 3. Six défauts trouvés en faisant tourner la suite

Aucun n'était visible sans lancer le banc sur un poste neuf, avec un
modèle qui n'est pas celui de son auteur. **Tous les six ont le même
motif : le banc suppose le monde dans lequel il a été écrit.** Chemin
figé, liste absente, modèle sans objets, date codée en dur, axe à un
point, CRS français en dur. Les six sont corrigés et commités.

Les trois premiers sont détaillés ci-dessous ; les trois suivants —
modèle sans objets de calage (`0713475`), date de fenêtre inversée
(`47cc98c`), axe dégénéré et `EPSG:2154` en dur (`3a7c571`) — le sont
dans leurs messages de commit.

Le plus parlant est le sixième : `couche()` déclarait `EPSG:2154` —
Lambert-93 — pour une couche bâtie sur les coordonnées **réelles** du
modèle. Sur Muncie, qui est dans l'Indiana, la reprojection rendait
« Coordinates with non-finite values are not allowed ». Le défaut ne
pouvait pas se voir sur un modèle français.

### 3.1 Le banc inventait 16 échecs faute de modèle (`11e7f64`)

Sa docstring promet que « les étapes qui touchent à un modèle sont
ignorées si aucun modèle n'est fourni ». La section Suivi n'y touche
pas — elle dépose un faux `avancement.json` et vérifie le rendu — mais
elle écrivait, effaçait et cherchait à un **chemin figé**, celui du
classeur. Sans modèle, aucun classeur n'est composé : la fenêtre se
replie légitimement sur l'onglet 3, et l'état déposé n'était jamais relu.
D'où 16 faux échecs, puis un plantage sur `table_suivi.item(0, 2)` valant
`None`.

`_dossier_etat()` rend désormais le dossier que la fenêtre surveille
vraiment. Avec un modèle, les deux chemins coïncident : **aucun contrôle
n'est relâché**.

### 3.2 Un garde-fou privé de sa liste plantait au lieu de se taire (`7be8d95`)

`mots_d_affaires()` lit `.affaires`, non versionné, donc absent de tout
poste neuf : `_AFFAIRES` valait `None`. Le `else None` qui le construit
montre que le cas était prévu — `findall` était pourtant appelé dessus, et
emportait toute la fin de la suite.

### 3.3 Le garde-fou des chemins existait en deux exemplaires divergents (`758ca27`)

**C'est le plus intéressant des trois.** `faire_zip.py` notait depuis le
08/08/2026 pourquoi la version à **liste blanche** ne pouvait pas
marcher : elle portait `d:\1-Python`, le poste de l'auteur, parmi ses
exceptions — *« le garde-fou était écrit pour ignorer exactement ce qu'il
devait voir »*. Il est passé au critère **« ce chemin existe-t-il ici ? »**.

Son jumeau de `test_plugin_qgis.py` était resté en arrière. Depuis la
**0.6.7**, il refusait les faux chemins que l'auto-test de `noyau.py`
emploie pour éprouver la lecture de `py -0p` —
`C:\Users\x\Python313\python.exe`, `D:\Python312`, `E:\Py` — des chemins
qui n'existent nulle part, donc inoffensifs. **La suite était rouge depuis
la 0.6.7 et personne ne l'avait vu, faute de l'avoir repassée.**

`faire_zip.chemins_du_poste()` porte désormais le critère pour les deux.
La liste blanche disparaît : plus aucune exception nominative à maintenir.

Vérifié trois fois : le banc adverse de l'archive passe en entier (il
injecte un vrai chemin de poste et le voit refusé), l'archive se
reconstruit `conforme`, et la suite du greffon est verte.

## 4. Environnement HEC-RAS — monté le 6 septembre

`%USERPROFILE%\venv-hecras`, depuis
`C:\Users\cedri\AppData\Local\Programs\Python\Python312\python.exe`.

Les onze paquets de `noyau.PAQUETS_HECRAS` : `ras-commander 0.99.2`
(≥ 0.99 exigé), `h5py 3.16.0`, `numpy`, `pandas`, `scipy`, `geopandas`,
`shapely`, `pyproj`, `matplotlib`, `openpyxl`, `pywin32` — **plus
`xarray`** (§ 6.1).

`CALAGE_PYTHON` est figé au **niveau utilisateur**. QGIS doit être
redémarré pour le voir.

## 5. Lot 5 de `AUDIT.md` — fait le 5 septembre

| commit | |
|---|---|
| `bc60fbb` | P1-5 — une section amont illisible est nommée, plus avalée |
| `9efddcc` | étape 7 → `_signaler_coherence_amont()` |
| `43db3f1` | vérification globale finale → `_verifier_globalement()` |
| `00cb3df` | AUDIT.md mis à jour |

`caler()` : **699 → 622 lignes**. Le test de caractérisation est resté
`identique` après chaque commit — aucune trajectoire déplacée.

**La troisième extraction est écartée sur mesure** : le bloc de
journalisation d'itération (`calage.py:1312-1333`) lit **quinze variables
locales**. Une fonction à quinze paramètres se lit plus mal que le bloc en
place. Ce qui reste du poids de `caler()` ne relève plus de l'extraction
mais de l'étendue de l'état porté par la boucle — donc du chantier
« calage simultané » de `docs/idees_V2_plugin.md`.

## 6. La barre d'onglets — vérifiée le 5 septembre, conforme

Mesuré sur la fenêtre réellement instanciée, QGIS 3.44.14, greffon 0.6.9,
police « MS Shell Dlg 2 » 8 pt gras.

Les six onglets demandent **529 px**. La fenêtre porte un `minimumWidth`
**explicite de 720 px**, alors que le `minimumSizeHint` de son agencement
descendrait à 388 px. Au plus étroit, la barre dispose donc de 696 px pour
529 px de besoin : **+167 px de marge**. `usesScrollButtons` vaut `True` —
le défilement est *autorisé*, jamais déclenché.

**Ce qui protège la barre est le plancher `minimumWidth = 720`, pas la
brièveté des libellés** — donc pas ce qu'affirme le commentaire de
`plugin.py:1512`. **Seuil de régression : 553 px** (529 + 24 de marges).
Un contrôle utile compare `tabBar().sizeHint().width()` à
`minimumWidth() - marges` ; mesurer la longueur des intitulés ne protège
rien.

Réserve : mesuré au DPI et à la police de ce poste. Les 24 % de marge
absorbent large, mais un poste à 150 % n'est pas couvert.

## 7. CE QUI DEMANDE UNE DÉCISION

### 7.1 Un défaut réel, non corrigé — `xarray` manque à `PAQUETS_HECRAS`

`commande_pip_hecras()` promet « la commande pip qui pose **TOUT** ce que
le pont exige », et sa docstring dit elle-même que la vérification exige
« onze **plus xarray** ». Or `xarray` n'est pas dans `PAQUETS_HECRAS` :
**suivre la commande du greffon à la lettre fabrique encore un
environnement qu'il refuse ensuite.** C'est exactement la divergence entre
deux listes que `PAQUETS_HECRAS` existe pour empêcher, et c'est le même
accident que la 0.6.1 (`ras-commander` sans `xarray`) et la 0.6.7 (deux
paquets au lieu de onze).

Reproduit ici : les onze posés, puis
`module(s) absent(s) de cet interpreteur : xarray.`

Je ne l'ai **pas** corrigé : ajouter `("xarray", "xarray")` à
`PAQUETS_HECRAS` est d'une ligne, mais `xarray` est une dépendance de
`ras-commander`, pas du pont. Le déclarer nous-mêmes masque le fait que
`ras-commander` la déclare mal. **À trancher.**

### 7.2 Les autres questions

Elles sont posées à l'oral au retour. En résumé :

1. **Un modèle de calage** sur ce poste — le seul manque pour les 58
   contrôles restants. Où, et quel `--objet` ?
2. **`.affaires`** — absent ; 3 contrôles ne sont pas joués. Le créer
   depuis `.affaires.exemple`, ou le garder hors du poste ?
3. **Les trois correctifs du banc** (§ 3) — approche validée ?
4. **Pousser** les commits locaux de cette branche ?
5. **Réinstaller le greffon en 0.7.0** dans QGIS ? L'archive vient d'être
   reconstruite ; le profil est encore en 0.6.9.
6. **Une coquille** dans le message du commit `11e7f64` (`n''a`) —
   réécrire l'historique pour la corriger, ou laisser ?
7. **`QGIS_PREFIX_PATH`** codé en dur dans `test_plugin_qgis.py:54` —
   faut-il le déduire de l'installation plutôt que d'écrire un chemin qui
   n'existe pas sur ce poste ?
8. **Le README** dit « `python verification_environnement.py` » sans dire
   *lequel*. Lancé sous le Python de QGIS, il rend un
   `DLL load failed` sur `ras-commander` qui ressemble à une panne alors
   que c'est l'incompatibilité h5py/QGIS documentée. Préciser ?
