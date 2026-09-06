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

## 5 bis. Ergonomie — quatre correctifs appliqués le 6 septembre

Issus de `docs/ergonomie_2026-09-06.md`. Chacun vérifié au banc **et** dans
le QGIS réel après réinstallation.

| correctif | commit |
|---|---|
| Entrée n'écrit plus dans la géométrie (`keyPressEvent`) | `3d845b7` |
| La boîte d'échec dit que la géométrie a déjà été réécrite | `fecbf79` |
| L'axe n'est plus choisi tout seul — son refus redevient atteignable, et nomme l'onglet 1 | `fecbf79` |
| « Dossier du projet » devient l'afficheur qu'il était déjà | `fecbf79` |
| Le plancher de largeur s'adapte à la barre d'onglets | `dc5ace6` |

**Deux d'entre eux ont failli être faux, et la mesure les a rattrapés :**

- Retirer `setDefault` ne suffit pas — Qt promeut alors « Parcourir… ».
  Il faut avaler Return dans un `keyPressEvent`.
- `setAllowEmptyLayer(True)` **ajoute** l'entrée vide sans la
  sélectionner : le combo rendait encore « Lignes d'injection ». Il faut
  `setLayer(None)`, qui tient quand des couches arrivent ensuite.

Le greffon installé dans QGIS est passé de **0.6.9 à 0.7.3**. L'ancienne
version est conservée sous
`…\plugins\calage_apports.sauvegarde_0.6.9`.

## 6. La barre d'onglets — mesurée deux fois, et la seconde a corrigé la première

Mesuré sur la fenêtre réellement instanciée, QGIS 3.44.14, greffon 0.6.9,
police « MS Shell Dlg 2 » 8 pt gras.

Les six onglets demandent **529 px**. La fenêtre porte un `minimumWidth`
**explicite de 720 px**, alors que le `minimumSizeHint` de son agencement
descendrait à 388 px. Au plus étroit, la barre dispose donc de 696 px pour
529 px de besoin : **+167 px de marge**. `usesScrollButtons` vaut `True` —
le défilement est *autorisé*, jamais déclenché.

**Ce qui protège la barre est le plancher `minimumWidth`, pas la brièveté
des libellés** — donc pas ce qu'affirme le commentaire de `plugin.py`.

> ### La seconde mesure, le 6 septembre, a corrigé la première
>
> Les 529 px ci-dessus valent pour le greffon **0.6.9**. La 0.7.0 avait
> renommé deux onglets — « 2. Objectifs et précision » et « Aide et
> configuration » — et le besoin est passé à **663 px**. La marge était
> donc de **+33 px**, pas +167. Elle s'était resserrée de 80 % sans que
> personne le voie.
>
> Pire : sous la police par défaut d'une session sans interface — donc
> sous un autre thème Windows, un réglage d'accessibilité ou une autre
> mise à l'échelle — la même barre demande **877 px** et **défile**.
>
> **Le plancher se déduit désormais de ce que la barre demande**
> (`dc5ace6`). L'invariante est vraie par construction, sur toute police
> et toute mise à l'échelle ; un libellé trop long élargit la fenêtre au
> lieu de disparaître. La réserve « pas mesuré à 150 % » tombe : il n'y a
> plus rien à mesurer.
>
> Un contrôle du banc compare ce que les onglets demandent à ce que la
> fenêtre peut donner au plus étroit. Écrit d'abord en dur, il échouait
> dans le banc headless faute d'y avoir la même police — c'eût été le
> septième défaut « le banc suppose le monde de son auteur » de la
> journée. Avec le plancher adaptatif, il passe partout.

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

### 7.2 Ce qui reste ouvert au 6 septembre, 14 h

**Réglé depuis** : le modèle (plan TEST de Muncie), `.affaires`, les six
correctifs du banc, le push sur `main`, la suppression des branches, la
réinstallation du greffon (0.7.3), la coquille de commit.

**Les trois décisions ont été prises et appliquées** (0.7.5 à 0.7.7) —
préfixe de scénario, garde-fou « un calage tourne », renommage du bouton.
Voir § 9.

**Ce qui reste ouvert :**

1. **Le correctif clavier n'est vérifié qu'au banc.** Ce qui se juge
   devant la fenêtre : qu'Entrée ne fasse plus **rien**, nulle part.
   C'est le prix assumé, et il se voit.
2. **Trois garde-fous jamais éprouvés en réel** — volume plancher, apport
   refusé, modèle incohérent. Les trois calages livrés ne les ont pas
   rencontrés ; seul le banc les couvre.
3. **Le calage simultané** (`docs/idees_V2_plugin.md` § 1) : ×18 sur un
   modèle à 30 apports, et c'est ce chantier qui réécrirait la boucle
   dont la troisième extraction a été écartée. Il repose entièrement sur
   l'hypothèse d'ordre total, que `STATUT.txt` liste toujours comme **non
   confirmée**. C'est une question d'hydraulicien, pas de code.
4. ~~Les constats du suivi (§ 2.3)~~ — **faits** (0.7.8 et 0.7.9), voir
   § 10.

## 9. Les trois décisions, appliquées le 6 septembre

| version | |
|---|---|
| **0.7.5** | Reprendre un classeur n'efface plus son préfixe de scénario. Le lancement écrivait six réglages, la reprise n'en relisait que quatre. Reprendre le classeur d'un Q100 puis lancer effaçait « Q100 » — l'accident même que le préfixe existe pour empêcher. Même trou pour « Premier apport ». |
| **0.7.6** | Un calage qui tourne ferme les deux portes. Ni la composition ni le lancement ne consultaient l'état du calage. Une **question** nommant le calage et son processus, jamais un bouton grisé : l'état vient d'un fichier souvent sur partage réseau. Un calage *terminé* ne ferme rien. |
| **0.7.7** | Le bouton nomme les trois choses qu'il fait — « Écrire, composer et contrôler ». Seize occurrences alignées, `LISEZMOI` et note méthodologique comprises ; les changelogs et entrées historiques gardent le nom d'alors. |

**Banc : 160 contrôles, aucun échec.** Six de plus qu'au matin, tous
posés sur ce qui venait d'être corrigé — dont trois qui éprouvent le
garde-fou « un calage tourne » sur un état portant le PID du processus
d'essai.

## 8. Le 6 septembre après-midi — ce qui a été fait sans décision

### 8.1 Le bouton « Installer… » est éprouvé, enfin

`verification_environnement.py` annonçait, sous *RESTE À ÉPROUVER*, que ce
bouton *« n'est allé jusqu'au bout sur aucun poste »*. C'était vrai.

Mené le 6 septembre **dans le processus QGIS**, par les deux chemins :
création d'un environnement à partir de rien, et reprise d'un
environnement déjà présent. **12 paquets posés et vérifiés en 56 s**,
`python 3.12.10, ras-commander 0.99.2, h5py 3.16.0`, et les douze
s'importent.

C'est le lancement **depuis QGIS** qui compte, et rien d'autre : c'est là
que le `PYTHONHOME` du greffon fuyait dans les sous-processus de
l'installeur — pip voyait les paquets de QGIS, les tenait pour *already
satisfied*, n'en posait aucun, et rendait 0 (corrigé en 0.6.9, jamais
vérifié en entier). Relevé ici :
`PYTHONHOME=…\QGIS34~1.14\apps\Python312`. Le même essai lancé depuis une
invite de commandes ne prouve rien — il n'a pas cet environnement à
assainir. (`1b34c84`)

### 8.2 Deux chemins QGIS de plus, codés en dur

Septième et huitième occurrences du motif. `C:\Program Files\QGIS\LTR`
n'existe pas sur un poste où l'installeur OSGeo range sous le numéro de
version. Conséquences : `setPrefixPath()` faux → MDAL introuvable et
`QgsMeshLayer` qui échoue **en silence** ; et le vérificateur qui rendait
« non détecté » devant un QGIS installé, tout en **dictant** une commande
menant à un fichier inexistant.

Les deux se déduisent désormais du poste. Mesure : la suite passe à
**157 OK / 0 échec sans `QGIS_PREFIX_PATH`** — une variable de moins à
poser. (`c1f4db5`)

### 8.3 Le README dit avec quel Python

Le dépôt en côtoie trois. Lancé sous celui de QGIS,
`verification_environnement.py` rend `DLL load failed` sur
`ras-commander` — qui a toute l'apparence d'un défaut d'installation et
n'est que la séparation voulue. C'est le premier outil que le README fait
lancer à un nouvel arrivant. Un tableau dit maintenant quoi avec quoi, et
que ce message-là n'est pas une panne. (`bade80a`)

### 8.4 La fenêtre accuse ce qu'on a dessiné — 0.7.4

Une ligne, sur le geste central de l'outil : `_maj_resume()` en tête de
`_changer_onglet`. On laissait la fenêtre ouverte, on allait tracer les
sections dans QGIS, on revenait — et rien ne le remarquait. (`969ac89`)

**Greffon installé dans QGIS : 0.7.4**, vérifié après rechargement.

## 10. Les constats du suivi — 0.7.8 et 0.7.9

Le § 2.3 de `docs/ergonomie_2026-09-06.md` portait six constats. Cinq
étaient corrigeables ; **le sixième a été essayé, mesuré, et retiré**.

**Trois d'entre eux n'avaient qu'une cause** : `_lancer_calage` recevait
le PID du calage et le chemin de son journal, les mettait dans une boîte
d'information, et les perdait.

| ce qui mentait | ce que ça donnait |
|---|---|
| après un relancement, l'onglet 5 peignait l'état du calage **précédent** | « Calage terminé — conforme » en réponse au lancement qui venait d'aboutir |
| « pas encore démarré » indistinguable de « mort au démarrage » | « quelques secondes après le lancement », pour toujours, devant un processus mort |
| le fil conducteur ordonnait « lancer » | pendant les **heures** du calcul, sur le seul repère permanent de la fenêtre |

Une donnée retenue en mémoire les redresse toutes les trois. **Jamais dans
`QSettings`** : celui-ci est attaché au profil QGIS, pas au projet, et
restaurer le lancement d'une autre étude coûterait plus cher que ce qu'on
répare. Fermer QGIS pendant un calage ne perd d'ailleurs ni le calcul ni
les livrables — le processus est détaché ; on perd l'orientation, pas le
travail.

**Le dossier surveillé** n'était nommé que dans la bannière « Aucun calage
suivi », donc jamais quand l'onglet sert. Il vit désormais sous la
bannière, renseigné à chaque passage.

### Le sixième : ce qui a été essayé puis retiré

Sonder `tasklist` toutes les deux secondes coûte un sous-processus sur le
fil graphique, pendant toute la durée du calage. J'ai tenu pour vivant un
`avancement.json` touché il y a moins d'une minute. **Le banc l'a réfuté
en deux temps :**

- un calage mort juste après avoir écrit son état était annoncé **en
  cours** pendant cette minute — c'est-à-dire exactement le défaut que la
  bannière « Calage interrompu » avait été ajoutée pour réparer ;
- et l'économie est **illusoire là où elle compterait** : pendant un
  calcul HEC-RAS de plusieurs heures, le fichier ne bouge pas davantage,
  donc on sonde de toute façon à chaque battement.

La friction reste, assumée. Un commentaire du code porte les deux mesures,
pour que l'idée ne revienne pas sans elles.

**Banc : 165 contrôles au terme de cette section, aucun échec** — 172 au
soir, les correctifs suivants ayant amené leurs propres contrôles.
