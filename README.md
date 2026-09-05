# Calage_apports

Ajustement séquentiel d'apports amont sur des hydrogrammes cibles aval, pour
les modèles 2D HEC-RAS — chaîne Python + plugin QGIS. Projet ISL Ingénierie.

Pour chaque apport, de l'amont vers l'aval : estimer, calculer, comparer à
la cible, corriger, répéter jusqu'à concordance, puis vérifier la cohérence
des sections amont avant de passer au suivant. La boucle de calage
([src/calage.py](src/calage.py)) est indépendante du solveur — elle ne
connaît de lui qu'une interface de huit méthodes — six obligatoires, deux qui
ont un comportement par défaut — ce qui la rend testable sans HEC-RAS. La
déclinaison HEC-RAS vit dans [src/pilote_hecras.py](src/pilote_hecras.py).

## Démarrage

```bat
pip install -r requirements-dev.txt
cd src
python verification_environnement.py
```

[requirements-dev.txt](requirements-dev.txt) dit ce qu'il faut pour travailler
sur le code — et surtout ce qui n'y est **pas** : `ras-commander` et `h5py`
vivent dans un interpréteur séparé (conflit HDF5 avec QGIS), `qgis` et `PyQt`
viennent de l'installation QGIS.

`verification_environnement.py` vérifie ensuite tout ce qui est nécessaire à
la mise en œuvre (interpréteurs, dépendances, fichiers du projet) et
diagnostique les manques.

Pour saisir les données d'un calage, partir de
[template_donnees_calage.xlsx](template_donnees_calage.xlsx) (produit par
[src/creer_template.py](src/creer_template.py)), puis lancer la chaîne en
ligne de commande ou depuis le plugin QGIS.

## Structure du dépôt

`src/` porte toute la chaîne Python. C'est un dossier de développement, pas
un paquet distribué : le plugin QGIS en embarque une copie autonome à
l'installation (voir plus bas).

| Fichier / dossier | Rôle |
|---|---|
| [src/calage.py](src/calage.py) | Boucle de calage séquentiel |
| [src/criteres.py](src/criteres.py) | Analyse pure : recalage temporel, KGE et composantes |
| [src/controle_donnees.py](src/controle_donnees.py) | Validation du classeur et de la chaîne SIG avant tout calcul |
| [src/geometrie.py](src/geometrie.py) | Shapefiles, PK par projection curviligne, écriture dans la géométrie HEC-RAS |
| [src/livrables.py](src/livrables.py) | Graphiques, tableaux, export Excel, note de synthèse |
| [src/suivi.py](src/suivi.py) | Avancement lisible pendant le calcul (markdown + png) |
| [src/pilote_hecras.py](src/pilote_hecras.py) | Déclinaison HEC-RAS de l'interface `Modele` |
| [src/pont_hecras.py](src/pont_hecras.py) | Pont en ligne de commande répondant en JSON — ras-commander est inimportable dans le processus QGIS |
| [src/elaguer_projet.py](src/elaguer_projet.py) | Rattrapage : élague les plans laissés par l'**ancienne** chaîne. Les plans d'étape de la chaîne actuelle sont conservés exprès, et il ne les voit pas |
| [src/reconstruire_livrables.py](src/reconstruire_livrables.py) | Rattrapage : reconstruit les livrables d'un calage **terminé** dont le rapport s'est perdu, depuis son plan final — en lecture seule sur le modèle |
| [src/verification_environnement.py](src/verification_environnement.py) | Contrôle de tout ce qui est nécessaire à la mise en œuvre |
| [src/creer_template.py](src/creer_template.py) / [src/style_classeur.py](src/style_classeur.py) | Fabrication et mise en forme du classeur de saisie |
| [src/faire_zip.py](src/faire_zip.py) | Construit `calage_apports.zip`, l'archive d'installation du plugin |
| [src/essai_garde_fou_archive.py](src/essai_garde_fou_archive.py) | Essai **adverse** : injecte trois fautes dans l'archive et vérifie qu'elles sont refusées |
| [src/test_plugin_qgis.py](src/test_plugin_qgis.py) | Suite du plugin (152 contrôles au 03/09), à lancer sous l'interpréteur de QGIS et sur une **copie** d'un modèle — la suite **modifie** la géométrie de celui qu'on lui donne |
| `src/figures_note/` | Reconstruction de la note méthodologique : contenu, figures, assemblage du `.docx` |
| [methodologie_calage_amont_aval.docx](methodologie_calage_amont_aval.docx) | Note méthodologique (mode opératoire, méthode générale, application HEC-RAS/QGIS, livrables) |
| `calage_apports/` | Plugin QGIS — voir son propre [LISEZMOI.md](calage_apports/LISEZMOI.md) (installation, tests, contraintes d'environnement) |
| `livrables_exemple/` | Sortie d'exemple produite par `python livrables.py` — régénérée à chaque exécution, **absente d'un dépôt fraîchement cloné** (hors suivi git depuis le 31/08/2026) |
| [src/reference_calage_fictif.json](src/reference_calage_fictif.json) | Sortie figée d'un calage complet sur `ModeleFictif` — le test de caractérisation de `caler()` la compare à chaque passage du banc. **Ne pas modifier à la main** : `python calage.py --figer-reference` la réécrit quand le changement est voulu |
| [AUDIT.md](AUDIT.md) | Audit de complexité du 5 septembre 2026 — constats mesurés, ce qu'il ne faut **pas** simplifier, et le plan par lots |
| `charte/` | Identité graphique ISL Ingénierie |
| `docs/` | Notes de travail annexes |
| `_arquivo/` | Versions obsolètes de documents, hors du chemin de lecture normal |

## État du projet

**Trois calages multi-apports sont allés à leur terme, conformes** — six, douze
et six apports, **vingt-quatre en tout**, zéro incident. La plupart ont convergé
en un ou deux essais. Ce qu'ils ont appris est aux sections 5.6 et 5.7 de
`STATUT.txt`.

**Plugin QGIS en 0.7.0.** Ses six onglets suivent l'ordre des décisions :
Modèle, Objectifs et précision, Résultats, Lancer, Suivi, Aide et
configuration.

**Ce qui reste à faire est dans `AUDIT.md` § 7** — le lot 5, et lui seul :
`_sections_derivees` (petit, local), puis `caler()`, 699 lignes pour une
complexité cyclomatique de 81. Ce second point ne se touche qu'à l'abri du test
de caractérisation, qui existe depuis le 5 septembre.

**Ce qui reste à vérifier au poste** : les **152 contrôles** de
`test_plugin_qgis.py`. Ils datent du 3 septembre, et `plugin.py` a changé
plusieurs fois depuis.

[STATUT.txt](STATUT.txt) porte l'état courant et les règles en vigueur —
c'est la référence à jour, plus fiable que ce README pour le détail.
[CHECKPOINT.md](CHECKPOINT.md) est le point de reprise entre sessions de
travail.

## Licence

Le plugin QGIS (`calage_apports/`) est distribué sous GPL-2.0-or-later —
voir [calage_apports/LICENSE.txt](calage_apports/LICENSE.txt). Copyright ©
2026 ISL Ingénierie.
