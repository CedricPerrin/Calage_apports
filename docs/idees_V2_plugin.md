# Idées pour une V2 du plugin

Ce fichier consigne ce qui a été **identifié et mesuré, mais délibérément pas
implémenté**. Chaque entrée dit ce que c'est, pourquoi ça vaut le coup, et ce
que ça coûterait.

Écrit le 1er août 2026.

> ## ⚠️ Relu le 2 septembre 2026 — une idée sur deux est sans objet
>
> **Elle décrit un algorithme qui n'existe plus.** La correction à deux
> termes — un étalé pour le volume, un concentré pour la pointe, chacun avec
> son gain — a été **retirée le 7 août 2026**. Ce qui la remplace n'a qu'un
> seul terme et aucun gain : l'écart lui-même EST la correction
> (`STATUT.txt` § 2.1).
>
> | idée | état |
> |---|---|
> | **1.** Un troisième terme | **sans objet** — il n'y en a plus qu'un, pas deux |
> | **2.** Tolérances par section | **tient toujours** |
>
> **Et les chiffres de coût sont périmés d'un ordre de grandeur.** Ils
> supposent trois essais par apport à 6,3 min le calcul. Les calages réels
> convergent en **un ou deux** essais, pour **2 h 25 à 3 h 50 par apport**
> (`STATUT.txt` § 5.6).
>
> Un renvoi à revoir au passage : l'**étape 7 ne fait plus de reprises** — la
> boucle a été retirée, elle se contente d'un avertissement (`calage.py`,
> « étape 7 »).
>
> Le fichier est **gardé tel quel** : une idée écartée dit pourquoi elle l'a
> été.

---

## 1. Élargir le noyau de correction à un troisième terme

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

## 2. Tolérances par section plutôt que globales

`Tolerance_volume_pct` et `Tolerance_pic_pct` s'appliquent à toutes les
sections. Sur une étude réelle, certaines sections sont dimensionnantes et
d'autres accessoires. Des tolérances par ligne de la feuille
`Correspondance` permettraient de ne pas dépenser des heures de calcul à
serrer une section qui n'en a pas besoin.

Coût faible : une colonne au classeur, deux champs dans `Configuration`, et le
contrôle qui va avec.
