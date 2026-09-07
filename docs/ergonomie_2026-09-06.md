# Recherche d'ergonomie sur la fenêtre du plugin — 6 septembre 2026

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

> **Correctif : retirer `setDefault` et `setAutoDefault` — mais cela ne
> suffit pas.** Qt promeut alors le premier bouton `autoDefault` visible,
> ici **« Parcourir… »** (`plugin.py:1719`). Il faut donc en plus **avaler
> Return/Enter dans un `keyPressEvent` de la classe** — trois lignes.
>
> **Effet de bord à assumer et à dire** : Entrée n'activera plus aucun
> bouton ayant le focus, nulle part dans la fenêtre.

Le bouton reste visuellement l'action principale : c'est
`objectName("boutonPrincipal")` (`plugin.py:1598`) et la feuille de style
qui le disent — le rôle d'un style, pas d'un raccourci clavier.

La fenêtre est un `QDialog` (`plugin.py:1480`) et ne définit ni
`keyPressEvent` ni `returnPressed` : rien n'intercepte aujourd'hui la
touche. Vérifié par grep, zéro occurrence.

C'est le constat le plus rentable du document : gravité maximale, coût
faible — mais **pas nul**, et pas sans effet de bord. Une première
rédaction de cette note annonçait « une ligne et demie » : c'était faux,
et un correctif qui s'y serait tenu aurait simplement déplacé la touche
Entrée de « Composer » vers « Parcourir… ».

### 1.2 Il reste actif pendant qu'un calage tourne — *bloquant*

`plugin.py:4033-4067` ne vérifie rien avant d'agir. Pendant les heures
d'un calage, un clic — ou un Entrée, cf. § 1.1 — **réécrit la géométrie et
le classeur du calcul en cours**. Le plugin sait pourtant détecter un
calage vivant : il le fait déjà en `plugin.py:3096`.

Le partage est réel en mode « plan », qui est le défaut ; en mode
surcharge (`plugin.py:1989-1990`) la géométrie est clonée et le risque
disparaît.

> **Correctif : une confirmation qui nomme le PID du calage en cours, pas
> un `setEnabled`.** L'état vient d'un fichier souvent posé sur un partage
> réseau (`plugin.py:2885-2887`) : une lecture manquée qui griserait le
> bouton principal serait pire que le mal.
>
> **Et le même test va dans la même passe en tête de `_lancer_calage`**
> (`plugin.py:3745`, qui ne teste aujourd'hui que `self.classeur`) —
> sinon on ferme une porte en laissant l'autre ouverte.

Note d'implémentation : le bouton est une **variable locale**
(`bouton_composer`, jamais `self.bouton_composer` — grep le confirme).
Aucun code ne peut donc le désactiver aujourd'hui ; le griser demanderait
d'en faire un attribut, ce qui est déjà plus qu'un `setEnabled`.

**Pas de désarmement par onglet, en revanche.** Les garde-fous de
`plugin.py:4035-4055` refusent déjà, avec un message qui nomme l'onglet où
corriger. Un bouton grisé remplacerait cinq phrases explicites par un
silence, et ne dirait pas *pourquoi*.

### 1.3 Quand la composition échoue *après* l'écriture, la boîte se tait — *trompeur*

`plugin.py:4195-4197`. L'ordre est : écrire dans la géométrie, **puis**
composer, **puis** contrôler. Si la composition échoue, l'utilisateur voit
un message d'échec et conclut que rien n'a eu lieu — alors que **son
modèle a déjà été modifié**.

> **Correctif : la boîte d'erreur dit que la géométrie a déjà été
> réécrite.** Un bloc.

### 1.4 Le renommage — un désaccord non tranché, et il faut le dire

> **Tranché le jour même, en 0.7.7** : le bouton s'appelle « Écrire, composer
> et contrôler », les douze occurrences ont suivi — sept dans `plugin.py`, une
> dans `LISEZMOI.md`, les autres n'existent plus. Le raisonnement ci-dessous
> est gardé tel qu'il a été écrit.

Le libellé (`plugin.py:1597`) nomme **deux actions sur trois** et omet la
seule qui modifie le modèle de l'utilisateur.

**Contre le renommage** : le libellé doit rester court, et l'infobulle
(`plugin.py:1602-1606`) énonce déjà les trois temps.

**Pour** : l'information n'existe QUE dans cette infobulle et dans un
paragraphe de l'onglet 1 (`plugin.py:1862`) — deux endroits invisibles à
qui clique depuis l'onglet 3 ou 4. *Un survol d'infobulle n'est pas un
consentement.* Nom proposé : **« Écrire, composer et contrôler »**.

**Condition non négociable si l'on renomme** : aligner dans la même passe
les onze occurrences du nom dans `plugin.py` — 1024, 1231, 1502, 1597,
1845, 1862, 2216, 2546, 3748, 3891, 3897 — **et `LISEZMOI.md:20`**, qui
est la documentation utilisateur. Un renommage qui l'oublie fabrique
exactement le mensonge qu'il prétend supprimer.

**Mon avis** : le § 1.3 (la boîte d'erreur qui se tait) règle le vrai
danger pour un dixième du coût. Renommer est défendable, mais c'est un
confort ; à faire seulement si l'on accepte les douze retouches.

### Ce qui a été proposé et **réfuté**

- *Absence de retour d'état pendant le travail*. Réfuté : `@avec_sablier`
  (`plugin.py:4032`) pose le curseur d'attente, et l'opération dure des
  secondes, pas des minutes.

---

## 2. Les autres constats, du plus rentable au moins

### 2.1 Une ligne chacun, à faire tout de suite

| constat | lieu |
|---|---|
| **Le refus de composer renvoie à l'onglet 2 pour choisir l'axe hydraulique, qui est à l'onglet 1.** Trouvé par **trois** lentilles indépendantes. | `plugin.py:4050-4052` |
| **Le fil conducteur coche « ✔ Axe hydraulique » alors que personne n'a choisi d'axe** — le combo est pré-rempli, éventuellement par une couche que le plugin vient lui-même de fabriquer. | `plugin.py:1684-1685`, `2248-2249` |
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
  d'environnement** — le message que le plugin a lui-même déclaré mauvais
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

---

## 5. Ce que cette note a donné, au 6 septembre au soir

**Seize constats sur dix-huit sont traités**, des versions 0.7.1 à 0.7.12.
Chacun a été vérifié au banc **et** dans le QGIS réel après réinstallation.

**Après la note — 0.7.13 à 0.7.16.** Trois versions d'interface de plus le 6
au soir, venues de demandes directes et non de ces constats : **0.7.13**
désigne le projet par son fichier `.prj` au lieu du dossier qui le contient ;
**0.7.14** nomme le fichier de saisie par ce qu'il contient — « Excel des
hydrogrammes objectifs », onglets 2 et 4 ; **0.7.15** supprime « greffon » au
profit de « plugin », 181 occurrences. Toutes vérifiées au banc sous QGIS,
aucune encore sous les yeux de l'utilisateur (`CHECKPOINT.md`, « Ce qui
reste »). **0.7.16** (7 septembre) ne touche pas à la fenêtre : elle retire
le KGE de la chaîne et corrige une figure des livrables.

Deux ne le sont pas, et c'est délibéré :

- **La permanence du bouton, les libellés courts, l'ordre écrire → composer
  → contrôler, le curseur sablier** — le § 3 dit pourquoi il ne faut pas y
  toucher, et rien depuis ne l'a démenti.
- **Le coût de `tasklist`** — essayé, mesuré, retiré. Le raccourci annonçait
  « en cours » un calage mort depuis moins d'une minute, et n'économisait
  rien pendant les longs calculs, où le fichier ne bouge pas davantage. La
  friction achète un affichage qui ne ment pas.

### Trois fois, la mesure a rattrapé le correctif

C'est le principal enseignement de la journée, et il vaut d'être noté.

1. **Retirer `setDefault` ne suffisait pas** : Qt promeut alors le premier
   bouton `autoDefault` visible — « Parcourir… ». Le correctif annoncé « une
   ligne et demie » n'aurait fait que déplacer la touche Entrée d'une action
   irréversible vers une autre.
2. **`setAllowEmptyLayer(True)` ajoute l'entrée vide sans la sélectionner** :
   le combo rendait encore une couche. Il fallait `setLayer(None)`.
3. **Le sommaire de l'aide aurait pu être un décor** : chaque onglet vit dans
   une zone défilante, et si c'est elle qui défile, `scrollToAnchor` ne fait
   rien. Mesuré sur la fenêtre affichée — document de 1923 px pour une vue de
   302, trois ancres à trois places distinctes.

Dans les trois cas, le banc ou la mesure a démenti une correction qui
paraissait juste. Le quatrième cas est plus dur : **un banc a réfuté un
correctif qui, lui, était bel et bien faux** — l'entrée de `xarray` dans
`PAQUETS_HECRAS` désactivait silencieusement les deux contrôles qui
éprouvent le mécanisme « la sonde nomme ce qui manque ». Voir 0.7.10.
