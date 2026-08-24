# Calage_apports

Ajustement séquentiel d'apports amont sur des hydrogrammes cibles aval, pour
les modèles 2D HEC-RAS — chaîne Python + plugin QGIS. Projet ISL Ingénierie.

Pour chaque apport, de l'amont vers l'aval : estimer, calculer, comparer à
la cible, corriger, répéter jusqu'à concordance, puis vérifier la cohérence
des sections amont avant de passer au suivant. La boucle de calage
([calage.py](calage.py)) est indépendante du solveur — elle ne connaît de
lui qu'une interface à quatre méthodes, ce qui la rend testable sans
HEC-RAS. La déclinaison HEC-RAS vit dans
[pilote_hecras.py](pilote_hecras.py).

## Démarrage

```bat
python verification_environnement.py
```

vérifie tout ce qui est nécessaire à la mise en œuvre (interpréteurs,
dépendances, fichiers du projet) et diagnostique les manques. Pour saisir
les données d'un calage, partir de
[template_donnees_calage.xlsx](template_donnees_calage.xlsx) (produit par
[creer_template.py](creer_template.py)), puis lancer la chaîne en ligne de
commande ou depuis le plugin QGIS.

## Structure du dépôt

| Fichier / dossier | Rôle |
|---|---|
| [calage.py](calage.py) | Boucle de calage séquentiel |
| [criteres.py](criteres.py) | Analyse pure : recalage temporel, KGE et composantes |
| [controle_donnees.py](controle_donnees.py) | Validation du classeur et de la chaîne SIG avant tout calcul |
| [geometrie.py](geometrie.py) | Shapefiles, PK par projection curviligne, écriture dans la géométrie HEC-RAS |
| [livrables.py](livrables.py) | Graphiques, tableaux, export Excel, note de synthèse |
| [suivi.py](suivi.py) | Avancement lisible pendant le calcul (markdown + png) |
| [pilote_hecras.py](pilote_hecras.py) | Déclinaison HEC-RAS de l'interface `Modele` |
| [pont_hecras.py](pont_hecras.py) | Pont en ligne de commande répondant en JSON — ras-commander est inimportable dans le processus QGIS |
| [elaguer_projet.py](elaguer_projet.py) | Élagage d'un projet déjà calé dont le ménage n'a pas tourné |
| [verification_environnement.py](verification_environnement.py) | Contrôle de tout ce qui est nécessaire à la mise en œuvre |
| [creer_template.py](creer_template.py) / [style_classeur.py](style_classeur.py) | Fabrication et mise en forme du classeur de saisie |
| [methodologie_calage_amont_aval.docx](methodologie_calage_amont_aval.docx) | Note méthodologique (mode opératoire, méthode générale, application HEC-RAS/QGIS, livrables) |
| `calage_apports/` | Plugin QGIS — voir son propre [LISEZMOI.md](calage_apports/LISEZMOI.md) (installation, tests, contraintes d'environnement) |
| `livrables_exemple/` | Sortie d'exemple produite par `python livrables.py` — régénérée à chaque exécution, pas une source |
| `charte/` | Identité graphique ISL Ingénierie |
| `docs/` | Notes de travail annexes |
| `_arquivo/` | Versions obsolètes de documents, hors du chemin de lecture normal |

## État du projet

[STATUT.txt](STATUT.txt) porte l'état courant et les règles en vigueur —
c'est la référence à jour, plus fiable que ce README pour le détail.
[CHECKPOINT.md](CHECKPOINT.md) est le point de reprise entre sessions de
travail.

## Licence

Le plugin QGIS (`calage_apports/`) est distribué sous GPL-2.0-or-later —
voir [calage_apports/LICENSE.txt](calage_apports/LICENSE.txt). Copyright ©
2026 ISL Ingénierie.
