# Recherche d'ergonomie sur la fenêtre du greffon — 6 septembre 2026

Lecture de `calage_apports/plugin.py` (0.7.0, 4 214 lignes) par six
lentilles indépendantes — une par zone de la fenêtre — puis une passe de
**réfutation** : chaque constat a été réattaqué par un lecteur chargé de le
démolir en allant relire le code. **30 constats, 5 réfutés, 25 tenus.**

Rien n'a été modifié. Ce document propose ; il ne corrige pas.

---

## 1. « Composer et contrôler » — la réponse

**Le bouton reste permanent, en bas, hors des onglets. Sa place est juste.**
La fenêtre n'est pas un assistant en cinq écrans : c'est un établi qu'on
garde ouvert pendant qu'on dessine dans QGIS, et l'action qui referme la
boucle doit être atteignable de partout. Le déplacer dans l'onglet 1 ou
l'onglet 4 obligerait à y revenir pour un geste qu'on répète.

**Mais il est armé de trois façons qu'il ne devrait pas l'être.**

### 1.1 La touche Entrée écrit dans la géométrie HEC-RAS — *bloquant*

`plugin.py:1599-1600`

```python
bouton_composer.setDefault(True)
bouton_composer.setAutoDefault(True)
```

Le bouton est **le bouton par défaut de la fenêtre**. Une pression sur
Entrée depuis n'importe quel champ de saisie — un chemin de dossier, une
tolérance, le préfixe de scénario — déclenche `_composer_et_controler()`,
qui **commence par écrire les sections et injections dans le `.gXX`**
(`plugin.py:4063`), en remplaçant tout objet de même nom.

C'est le seul geste irréversible de la fenêtre, et c'est celui qui est
câblé sur la touche qu'on presse par réflexe en finissant de taper.

> **Correctif : retirer `setDefault` et `setAutoDefault`.** Une ligne et
> demie. Le bouton reste visuellement l'action principale — c'est
> `objectName("boutonPrincipal")` et la feuille de style qui le disent,
> pas `setDefault`.

C'est le constat le plus rentable du document : gravité maximale, coût
minimal, aucun effet de bord.

### 1.2 Il reste actif pendant qu'un calage tourne — *bloquant*

`plugin.py:4033-4067` ne vérifie rien avant d'agir. Pendant les heures
d'un calage, un clic — ou un Entrée, cf. § 1.1 — **réécrit la géométrie et
le classeur du calcul en cours**. Le greffon sait pourtant détecter un
calage vivant : il le fait déjà en `plugin.py:3096`.

Réserve honnête : sur ce point, deux réfuteurs se sont contredits. L'un a
maintenu le constat, l'autre l'a écarté au motif que le calage travaille
sur des plans clonés. **À trancher en lisant `_composer_et_controler()`
de bout en bout** — mais même si les plans sont clonés, le `.gXX` et le
classeur, eux, sont partagés.

> **Correctif : désarmer le bouton tant qu'un calage tourne**, ou exiger
> une confirmation qui nomme le calage en cours.

### 1.3 Quand la composition échoue *après* l'écriture, la boîte se tait — *trompeur*

`plugin.py:4195-4197`. L'ordre est : écrire dans la géométrie, **puis**
composer, **puis** contrôler. Si la composition échoue, l'utilisateur voit
un message d'échec et conclut que rien n'a eu lieu — alors que **son
modèle a déjà été modifié**.

> **Correctif : la boîte d'erreur dit que la géométrie a déjà été
> réécrite.** Un bloc.

### Ce qui a été proposé et **réfuté**

- *Renommer le bouton* (il nomme deux actions sur trois, et omet la seule
  irréversible). Réfuté : le libellé doit rester court, et l'infobulle
  (`plugin.py:1602`) énonce déjà les trois temps. Le vrai manque n'est pas
  le nom, c'est le silence de la boîte d'erreur — § 1.3.
- *Absence de retour d'état pendant le travail*. Réfuté : `@avec_sablier`
  (`plugin.py:4032`) pose le curseur d'attente, et l'opération dure des
  secondes, pas des minutes.

---

## 2. Les autres constats, du plus rentable au moins

### 2.1 Une ligne chacun, à faire tout de suite

| constat | lieu |
|---|---|
| **Le refus de composer renvoie à l'onglet 2 pour choisir l'axe hydraulique, qui est à l'onglet 1.** Trouvé par **trois** lentilles indépendantes. | `plugin.py:4050-4052` |
| **Le fil conducteur coche « ✔ Axe hydraulique » alors que personne n'a choisi d'axe** — le combo est pré-rempli, éventuellement par une couche que le greffon vient lui-même de fabriquer. | `plugin.py:1684-1685`, `2248-2249` |
| **Le champ « Dossier du projet » se laisse remplir à la main, mais une saisie ne charge jamais le projet** : seul le sélecteur y conduit. | `plugin.py:1716-1723` vs `1942-1948` |
| **Le pourcentage change de sens sans le dire** : le rappel parle d'atteinte de la cible, les deux champs attendent un écart admis. | `plugin.py:2282-2312` |

### 2.2 Un état qui ment après une reprise de classeur — *le groupe le plus grave après le § 1*

**Le préfixe de scénario n'est jamais relu du classeur repris, et le
lancement écrase le préfixe stocké par le champ vide de la fenêtre**
(`plugin.py:3766-3768` écrit ; `3697-3713` est la seule relecture, et il
n'y figure pas).

C'est exactement le piège que le LISEZMOI signale comme grave — *« sans
lui, caler le Q10 après le Q100 sur le même modèle efface les plans du
Q100 »* — rouvert par le chemin « Reprendre un classeur d'un calcul
précédent ». Le même trou existe pour **« Premier apport »**
(`plugin.py:3762-3763` vs `3649-3657`), et le haut de l'onglet 4 continue
d'afficher l'appariement du classeur **précédent** (`3715-3736`).

> Ces quatre-là se tiennent : la reprise de classeur ne relit qu'une
> partie de ce que le lancement réécrit. Le correctif est un seul endroit —
> `_appliquer_objectifs_du_classeur` — pas quatre.

### 2.3 Le suivi, pendant les heures où il sert

| constat | lieu |
|---|---|
| **Après un relancement, l'onglet 5 peint l'état du calage PRÉCÉDENT** comme s'il était celui qui vient de partir. | `plugin.py:3036`, `3081-3114`, `3825-3835` |
| **Rien ne distingue « pas encore démarré » de « mort au démarrage »**, et le document qui dirait pourquoi n'est pas atteignable depuis l'onglet 5. | `plugin.py:3043`, `3105` |
| **Le fil conducteur dit encore « lancer » pendant les heures où le calage tourne** — seul repère permanent de la fenêtre. | `plugin.py:1696-1703`, `3830-3835` |
| **Le dossier réellement surveillé n'est nommé que lorsqu'AUCUN calage n'est suivi** : pendant l'usage réel, rien ne dit d'où viennent les chiffres. | `plugin.py:3049` |
| **Fermer QGIS pendant un calage : rien, à la réouverture, ne ramène au calcul en cours.** | `plugin.py:4343-4366` |
| **Un `tasklist` en sous-processus sur le fil graphique toutes les deux secondes**, pendant toute la durée du calage. | `plugin.py:3096` → `noyau.py:1600` |

### 2.4 Le reste

- **Changer de plan ou surcharger la géométrie après avoir chargé les
  couches n'invalide rien** : l'écran continue d'affirmer un modèle chargé
  qui n'est plus celui-là. `plugin.py:2033-2035`, `1987-1998`.
- **On revient de QGIS après avoir dessiné les sections : la fenêtre
  n'accuse rien.** C'est pourtant le geste central du mode opératoire.
  `plugin.py:2840-2849`.
- **Au lancement, l'interpréteur manquant renvoie vers une variable
  d'environnement** — le message que le greffon a lui-même déclaré mauvais
  en 0.6.7, et qui ignore le bouton « Installer… ». `noyau.py:2261`,
  affiché par `plugin.py:3820`.
- **L'aide est un rouleau de 11 000 caractères sans repère, et aucun
  endroit de la fenêtre n'y conduit.** `plugin.py:1178`, `3238-3249`.

---

## 3. Ce qu'il ne faut PAS toucher

- **La permanence du bouton** (§ 1). C'est l'établi, pas un assistant.
- **Les libellés courts des onglets.** Mesuré le 5 septembre : 529 px pour
  696 px disponibles au plus étroit. Les rallonger ferait défiler la barre
  à partir de 553 px de besoin.
- **L'ordre écrire → composer → contrôler.** Il est voulu et documenté :
  les sections doivent être dans le modèle avant que le paquet soit
  composé. Ce qui manque n'est pas un autre ordre, c'est de le **dire**
  quand ça échoue en cours de route (§ 1.3).
- **Le curseur sablier** comme seul retour pendant la composition :
  proportionné à une opération de quelques secondes.

## 4. Ce qu'aucune lecture de code ne tranchera

- La **place** du bouton, à droite après un `addStretch(1)`, contre
  l'ordre de lecture des onglets. Rien dans le code ne dit si l'œil le
  trouve. À regarder par-dessus l'épaule de quelqu'un.
- Si le **fil conducteur** est lu, ou s'il fait partie du décor.
- Si l'**aide** est un jour ouverte spontanément, ou seulement après un
  échec.
- Combien de temps un nouvel arrivant met à comprendre qu'il doit
  **sortir dessiner dans QGIS** puis revenir.
