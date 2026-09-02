# Idées pour une V2 du plugin

Ce fichier consigne ce qui a été **identifié et mesuré, mais délibérément pas
implémenté**. Chaque entrée dit ce que c'est, pourquoi ça vaut le coup, et ce
que ça coûterait.

Écrit le 1er août 2026.

> ## ⚠️ Relu le 2 septembre 2026 — deux idées sur quatre sont sans objet
>
> **Elles décrivent un algorithme qui n'existe plus.** La correction à deux
> termes — un étalé pour le volume, un concentré pour la pointe, chacun avec
> son gain — a été **retirée le 7 août 2026**. Ce qui la remplace n'a qu'un
> seul terme et aucun gain : l'écart lui-même EST la correction
> (`STATUT.txt` § 2.1).
>
> | idée | état |
> |---|---|
> | **1.** Calage simultané | **tient toujours** — mais son constat de départ est faux : les autres sections ne sont plus jetées, elles servent à la durée ajustée et au critère de cohérence du décalage |
> | **2.** Réutiliser le jacobien | **sans objet** — il n'y a plus de gain à réutiliser |
> | **3.** Un troisième terme | **sans objet** — il n'y en a plus qu'un, pas deux |
> | **4.** Tolérances par section | **tient toujours** |
>
> **Et les chiffres de coût sont périmés d'un ordre de grandeur.** Ils
> supposent trois essais par apport à 6,3 min le calcul. Les calages réels
> convergent en **un ou deux** essais, pour **2 h 25 à 3 h 50 par apport**
> (`STATUT.txt` § 5.6). Le gain de l'idée 1 reste réel — il porte sur le
> nombre de calculs — mais le tableau du § 1 ne le chiffre plus.
>
> Deux renvois à revoir au passage : l'**étape 7 ne fait plus de reprises** —
> la boucle a été retirée, elle se contente d'un avertissement (`calage.py`,
> « étape 7 ») ; et le renvoi « § 1.3 de la note » pour l'hypothèse d'ordre
> total désigne un autre § que celui qu'annonce `STATUT.txt` (§ 1.2) — la note
> ayant été refaite en V15, **vérifier lequel est le bon dans le document**
> avant de corriger l'un ou l'autre.
>
> Le fichier est **gardé tel quel** : le raisonnement de l'idée 1 vaut encore,
> et une idée écartée dit pourquoi elle l'a été.

---

## 1. Calage SIMULTANÉ de tous les apports — le vrai levier

**C'est de loin l'idée la plus rentable du fichier.** Elle ne change rien à la
qualité du calage : elle divise le temps de calcul par un facteur égal, en
gros, au nombre d'apports.

### Le constat

Un calcul HEC-RAS produit la réponse à **toutes** les sections de contrôle à
la fois. La boucle actuelle n'en lit **qu'une** : celle de l'apport en cours
de calage. Toute l'information sur les autres sections est jetée.

Les apports étant calés en séquence, le coût est donc :

```
nb_calculs  =  nb_apports  ×  nb_essais_par_apport
```

Mesuré sur CETTE : 3 apports × 3 essais = 10 calculs, ~50 min. Extrapolé à un
modèle de production à 30 apports : **90 calculs, soit 9 h 30** à 6,3 min le
calcul — et bien davantage sur un modèle plus lourd que CETTE.

### Pourquoi on peut faire beaucoup mieux

Le jacobien du système est **triangulaire inférieur**. C'est une conséquence
directe de l'hypothèse d'ordre total (§ 1.3 de la note méthodologique) :
l'apport *i* n'a aucun effet sur les sections situées en amont de lui. En
notant `y` le vecteur des réponses aux sections et `x` celui des apports :

```
y = J · x + y₀     avec J triangulaire inférieure
```

Un système triangulaire se résout **exactement**, par substitution avant, en
une seule passe. Il n'y a là aucune approximation : c'est la structure exacte
du problème telle que la méthode la postule déjà.

On peut donc corriger **tous les apports après chaque calcul** au lieu d'un
seul, et le coût devient :

```
nb_calculs  =  nb_essais   (indépendant du nombre d'apports)
```

### Le gain attendu

| apports | séquentiel (actuel) | simultané | facteur |
|---|---|---|---|
| 3 (CETTE) | ~10 calculs | ~4 | 2,5 |
| 10 | ~30 calculs, 3 h | ~5, 30 min | 6 |
| **30** | **~90 calculs, 9 h 30** | **~5, 30 min** | **18** |

Le gain croît avec le nombre d'apports : c'est exactement le régime visé par
l'objectif « appliquer le plugin sur des modèles importants ».

### Ce que ça demande

Une réécriture du cœur de `caler()`, et de ce qui en dépend :

- la boucle `pour chaque apport` devient une boucle `pour chaque essai`, avec
  une correction vectorielle de tous les apports par substitution avant ;
- les gains ne sont plus deux scalaires mais deux matrices triangulaires,
  estimées par différences entre essais successifs (Broyden par blocs) ;
- `suivi.py` suit aujourd'hui un apport en cours à la fois — il faut un
  avancement par essai global, pas par apport ;
- l'étape 7 (reprises quand un apport dégrade une section amont validée)
  disparaît : elle n'existe que parce que le calage est séquentiel. En
  simultané, toutes les sections sont vérifiées à chaque essai ;
- les livrables et le journal supposent une chronologie par apport.

**Estimation honnête : 2 à 3 jours de travail, et une revalidation complète
sur CETTE.** Ce n'est pas un ajustement, c'est un changement d'architecture.

### Risque principal

Le gain de la méthode simultanée repose entièrement sur la validité de
l'hypothèse d'ordre total. Or `STATUT.txt` la liste toujours parmi les points
ouverts : *« la confirmation qu'il n'y a pas de boucle hydraulique »* n'a pas
été apportée par l'utilisateur. **À confirmer avant d'engager le chantier** :
s'il existe une boucle, le jacobien n'est plus triangulaire, la substitution
avant ne s'applique plus, et il faut retomber sur une résolution générale —
plus coûteuse mais toujours très inférieure au séquentiel.

---

## 2. Réutiliser le jacobien d'un apport à l'autre

Les gains de volume et de pointe sont réestimés à zéro pour chaque apport.
Sur un tronçon homogène, deux apports voisins ont des gains proches. Partir du
gain du voisin amont plutôt que de la valeur par défaut ferait gagner l'essai
qui sert aujourd'hui uniquement à mesurer le gain — soit **un calcul par
apport**, 30 calculs sur un modèle à 30 apports.

Peu coûteux à implémenter (quelques lignes), à valider sur un modèle réel
comportant plusieurs apports sur un même bief.

---

## 3. Élargir le noyau de correction à un troisième terme

La correction actuelle a deux termes : un étalé qui ferme le volume, un
concentré qui ferme la pointe. La **forme** (critère r) n'est pas pilotée
explicitement — elle s'améliore par construction, la correction étant bâtie
sur l'écart point par point.

Un troisième terme piloté par la forme permettrait de traiter le cas
diagnostiqué mais non résolu : *volume excédentaire et pointe déficitaire*,
c'est-à-dire un hydrogramme calculé trop étalé. Aujourd'hui le message dit
seulement que rehausser la pointe aggravera le volume, et renvoie
l'utilisateur vers les apports amont.

Attention : un apport ne sait qu'**ajouter** du débit. Un terme de forme ne
peut donc pas creuser les flancs de l'hydrogramme, seulement les remplir. Le
gain est probablement limité, et ce point mérite d'être étudié avant d'être
codé.

---

## 4. Tolérances par section plutôt que globales

`Tolerance_volume_pct` et `Tolerance_pic_pct` s'appliquent à toutes les
sections. Sur une étude réelle, certaines sections sont dimensionnantes et
d'autres accessoires. Des tolérances par ligne de la feuille
`Correspondance` permettraient de ne pas dépenser des heures de calcul à
serrer une section qui n'en a pas besoin.

Coût faible : une colonne au classeur, deux champs dans `Configuration`, et le
contrôle qui va avec.
