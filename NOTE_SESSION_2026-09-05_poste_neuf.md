# Session du 5 septembre 2026 — reconnaissance du poste neuf

Note de reprise autonome. Écrite pour qu'une session repartie de zéro
puisse continuer sans rien redécouvrir.

> **Corrigée en cours de session.** Une première version concluait que les
> sources 0.6.7–0.6.9 étaient perdues ou non poussées. **C'était faux** :
> le clone était simplement sur `main`. Voir § 1. Les mesures des § 3.4 et
> § 4 sont inchangées — elles portent sur le plugin réellement chargé.

## 1. Ce qu'est ce poste, et où sont les sources

`C:\Users\cedri` — Windows 11, QGIS **3.44.14-Solothurn**, profil
`default`, Python **3.12.14**.

Le plugin installé est en **0.6.9**, dans le profil QGIS
(`…\QGIS3\profiles\default\python\plugins\calage_apports`), **par copie
d'archive et non par lien symbolique** (`os.path.islink` → `False`).
C'est une copie de distribution : elle porte `chaine/`, mais **aucun
fichier de `src/`** — ni `test_plugin_qgis.py`, ni `faire_zip.py`, ni
`essai_garde_fou_archive.py`, ni `verification_environnement.py`.

**Les sources sont sur GitHub, sur une branche qui n'est pas `main`.**

| | |
|---|---|
| `origin/main` | 0.6.6 — HEAD `684f537` |
| `origin/claude/connaissance-des-md-qjbpro` | **0.7.0**, contient 0.6.9 (`e734173`) |

Le clone fait ici le 5 septembre est sur `main`, d'où les 0.6.6 partout.
Se placer sur la bonne branche débloque les tâches 1 et 2 :

```bat
cd C:\Users\cedri\Calage_apports
git checkout claude/connaissance-des-md-qjbpro
```

Deux points à ne pas oublier :

- **0.7.0 est en attente de push** au moment de cette note. Le dépôt
  distant porte 0.6.9 ; le travail 0.7.0 est local à l'autre poste.
- **L'archive `.zip` n'est pas sur GitHub** — `.gitignore` ligne 9 porte
  `*.zip` : c'est un artefact de construction, jamais versionné. Elle se
  régénère par `python src/faire_zip.py`.

Il n'y a **aucun arbre de développement sur ce poste** en dehors du clone
(cherché sur `C:` en entier et `G:` jusqu'à 6–8 niveaux). C'est cohérent
avec l'idée que ce poste est « le poste neuf » du changelog 0.6.9 :
`git` n'y était pas configuré avant cette session, `gh` n'était pas
installé, il n'y a pas de `venv-hecras`.

## 2. Divergence mesurée, `main` (0.6.6) vs installé (0.6.9)

Comparaison après normalisation des fins de ligne — la divergence est
réelle, ce n'est pas un artefact de `git checkout`. Mesurée avant de
découvrir la branche 0.7.0 ; elle garde son intérêt : elle dit ce que
`main` a de retard sur ce qui tourne.

| fichier | verdict | lignes 0.6.6 → 0.6.9 |
|---|---|---|
| `plugin.py` | diffère | 4149 → 4214 |
| `noyau.py` | diffère | 2784 → 3059 |
| `chaine/calage.py` | **diffère** | 3473 → **3660** |
| `chaine/criteres.py` | diffère | 980 → 1138 |
| `chaine/style_classeur.py` | diffère | 525 → 702 |
| `chaine/controle_donnees.py` | diffère | 918 → 928 |
| `chaine/pont_hecras.py` | diffère | 2099 → 2099 |
| `chaine/geometrie.py` | identique | 1328 |
| `chaine/livrables.py` | identique | 977 |
| `chaine/pilote_hecras.py` | identique | 3248 |
| `chaine/suivi.py` | identique | 1530 |

`calage.py` a pris 187 lignes entre 0.6.6 et 0.6.9 : d'où l'interdiction
d'engager le Lot 5 depuis `main` (§ 3.2).

## 3. Les quatre tâches

### 3.1 Les 152 contrôles QGIS, au poste — un blocage sur deux levé

`test_plugin_qgis.py` sera disponible dès qu'on se place sur la branche
0.7.0 ; il n'est pas dans l'archive installée, et sa version `main` est
en 0.6.6 — la lancer contre un plugin 0.6.9 produirait des échecs faux
partout où le comportement a légitimement changé (bouton « Installer… »
en 0.6.7, repli des pentes en 0.6.8, environnement assaini en 0.6.9).

**Attention à ce que l'on teste.** Le plugin installé est en 0.6.9, la
branche est en 0.7.0 : sur ce poste, la suite 0.7.0 s'exécuterait contre
un greffon 0.6.9. Réinstaller l'archive reconstruite avant de conclure,
ou passer par un lien symbolique.

Blocage restant : la suite demande **une copie d'un modèle**. Ce poste
n'a que les exemples livrés avec HEC-RAS
(`C:\Users\cedri\Documents\HECRAS\Example_Projects_7_0\`, déposés le
05/09/2026 à 17 h 45) — pas un modèle de calage.

### 3.2 Lot 5 — `_sections_derivees`, puis `caler()`

Ni « Lot 5 » ni « ergonomie » n'apparaissent dans le dépôt sur `main` :
ce sont des notes personnelles, pas un état consigné. Les seuls « lots »
écrits sont dans `_arquivo/STATUT_avant_refonte_20260830.txt` (lots 3
et 7), d'une numérotation antérieure à la refonte. **À rechercher dans le
`STATUT.txt` de la branche 0.7.0**, qui n'a pas été lu.

Sur `main`, `_sections_derivees` est en `src/calage.py:1599`, appelée une
seule fois, à l'étape 7 de `caler()` (`src/calage.py:1492`). Le
commentaire de l'étape 7 dit déjà que la boucle de « reprises » a été
retirée : la fonction est une **relecture pure** du dernier calcul, aucun
calcul HEC-RAS entre deux tours, donc la boucle ne pouvait rien changer.

**Ne pas engager le Lot 5 depuis `main`.** Le test de caractérisation qui
protège la refonte n'a pas été localisé — vérifier s'il s'agit de
l'auto-test de `calage.py` lui-même (les neuf modules de `chaine/` en
portent un, lançables par `%CALAGE_PYTHON% calage.py`) ou d'un fichier de
`src/` propre à la branche 0.7.0. **Le lancer vert AVANT toute
modification** : c'est tout son intérêt.

### 3.3 Ergonomie, dont le placement de « Composer et contrôler » — non engagée

Faisable en lecture sur le `plugin.py` de 0.6.9 du profil QGIS, ou mieux
sur celui de la branche 0.7.0. La copie installée ne doit **jamais** être
éditée (LISEZMOI : « Les fichiers de `calage_apports/chaine/` sont des
copies. Les modifier ne sert à rien »).

### 3.4 La barre d'onglets ne défile pas — VÉRIFIÉ, CONFORME

Mesuré le 5 septembre 2026 sur la fenêtre réellement instanciée
(`plugins['calage_apports'].fenetre`, un `DialogueParametrage`), sous
QGIS 3.44.14, plugin 0.6.9, police de barre « MS Shell Dlg 2 » 8 pt en
gras.

| onglet | `tabSizeHint` |
|---|---|
| 1. Modèle | 88 px |
| 2. Profil en long | 122 px |
| 3. Résultats | 100 px |
| 4. Lancer | 85 px |
| 5. Suivi | 75 px |
| Aide | 59 px |
| **total** | **529 px** |

La fenêtre porte un `minimumWidth` **explicite de 720 px**, alors que le
`minimumSizeHint` de son agencement descendrait à 388 px. Au plus étroit
qu'elle puisse être, la barre dispose donc de 720 − 12 − 12 = **696 px**
pour 529 px de besoin : **+167 px de marge**. `usesScrollButtons` vaut
`True` — le défilement est *autorisé*, il n'est simplement jamais
déclenché.

**Ce qui protège réellement la barre est le plancher `minimumWidth = 720`,
pas la brièveté des libellés** — c'est-à-dire pas ce qu'affirme le
commentaire de `plugin.py:1512`. Le seuil de régression est **553 px**
(529 + 24 de marges) : abaisser `minimumWidth` sous cette valeur fait
réapparaître le défilement et la troncature du premier onglet. C'est
cette invariante-là qu'un contrôle devrait tenir — comparer
`tabBar().sizeHint().width()` à `minimumWidth() - marges`, et non mesurer
la longueur des intitulés.

Réserve : mesuré à la mise à l'échelle et à la police de ce poste. Les
24 % de marge absorbent large, mais un poste à 150 % n'est pas couvert
par cette mesure.

À revérifier sur 0.7.0 si la fenêtre y a changé.

## 4. État de l'environnement sur ce poste

| | |
|---|---|
| QGIS | 3.44.14-Solothurn, profil `default`, Python 3.12.14 |
| plugin | 0.6.9, chargé, copie d'archive, `chaine/` embarquée présente |
| `venv-hecras` | **absent** |
| `CALAGE_PYTHON` | **non défini** |
| `CALAGE_CHAINE` | **non défini** |
| `ras_commander` | présent dans le `site-packages` **utilisateur** de Python 3.12 (posé le 05/09/2026 à 19 h 38) |
| modèles HEC-RAS | seulement les exemples `Example_Projects_7_0` |

Vérifié explicitement : le `site-packages` utilisateur **n'est pas** sur
le `sys.path` de QGIS ; ni `ras_commander` ni `h5py` n'y sont trouvables
(`importlib.util.find_spec` → `None`). La séparation exigée par le projet
tient — aucune contamination du processus QGIS.

Il n'y a donc **aucun interpréteur HEC-RAS utilisable désigné** : tout ce
qui passe par le pont (`pont_hecras.py`) est hors de portée tant que
`CALAGE_PYTHON` n'est pas fourni.

## 5. Ordre de reprise proposé

1. `git checkout claude/connaissance-des-md-qjbpro` — préalable à tout.
   Puis pousser 0.7.0 depuis l'autre poste et `git pull`.
2. Lire le `STATUT.txt` de cette branche : il porte probablement la
   définition du Lot 5 et l'état de la recherche d'ergonomie.
3. Créer `venv-hecras` et désigner `CALAGE_PYTHON` (commandes dans
   `calage_apports/LISEZMOI.md`).
4. Reconstruire l'archive (`python src/faire_zip.py`) et la réinstaller,
   pour que le greffon testé soit celui des sources (§ 3.1).
5. Obtenir un modèle de calage, puis passer les 152 contrôles.
6. Lot 5, une fois son test de caractérisation retrouvé et lancé vert.
