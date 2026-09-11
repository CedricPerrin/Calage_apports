# Ergonomie de Calage des apports — 11 septembre 2026

Cette révision prépare la version **0.8.0** du plugin QGIS. Elle porte sur la
préparation d’un calage, la lecture de ses états et l’accès à l’aide. La
méthode hydraulique, les valeurs par défaut et les règles de contrôle restent
les références métier existantes. Ce document décrit les choix de conception ;
le bilan de recette et de livraison est consigné dans [STATUT.txt](../STATUT.txt).

## Parcours et changements

Les rubriques suivent **Modèle → Sorties → Objectifs → Lancer → Suivi**, avec
**Aide** accessible depuis la même barre. Le bouton **Contrôle paramétrage**
reste au bas de la fenêtre : il écrit les objets dessinés dans la géométrie,
compose le paquet, puis le contrôle. Les commandes de navigation permettent
de changer de rubrique sans déclencher cette opération.

| Rubrique | Décision mise en avant | Détails conservés |
|---|---|---|
| Modèle | Choisir le `.prj`, le plan et les objets utiles au calage | Géométrie, zone 2D, couches éditables, axe, sens, PK et période |
| Sorties | Choisir le dossier et le sort des plans d’étape | Sous-dossiers personnalisables et configuration complète dépliables |
| Objectifs | Ouvrir ou reprendre l’Excel, puis vérifier les cibles | Tolérances, bilan de masse, maximum d’essais ; hypothèse de pente dépliable |
| Lancer | Comprendre la préparation et le calcul avant de le lancer | Appariement, cibles, apport de départ, préfixe, copies de travail et accès au suivi |
| Suivi | Lire l’avancement du calage effectivement lancé | Dossier surveillé, mesures et famille de courbes déjà calculées |
| Aide | Vérifier l’environnement et retrouver les réglages du poste | Mode opératoire complet avec sommaire, placé après le diagnostic |

Les consignes longues deviennent des aides secondaires accessibles par un
bouton explicite. Les champs gardent leurs valeurs et leurs unités. La
précision distingue l’**écart admis à la cible** de l’**erreur de bilan de
masse HEC-RAS** : une tolérance de 5 % et une atteinte de 100 % ne représentent
pas la même donnée. Le critère de forme reste hors des réglages de la fenêtre.

Les plans d’étape sont **conservés par défaut**. Leur présence ne reçoit plus
la couleur d’un problème. La suppression facultative indique son effet avant
activation et ne s’applique qu’après un calage réussi ; le plan de référence,
le plan final et les plans étrangers à la chaîne restent protégés.

La présentation s’appuie sur les contrôles et la palette Qt. La taille de
texte suit celle du poste ; les formulaires, les retours à la ligne et le
défilement doivent laisser les champs atteignables dans une petite fenêtre.
La navigation au clavier doit rester indépendante des actions qui écrivent
dans le modèle ou lancent un calcul.

## Sources et adaptation à Qt

Les cinq sources primaires suivantes ont été ouvertes le **11 septembre
2026**. Elles étayent les intentions ; les choix propres à Calage des apports
restent des adaptations à vérifier dans le plugin.

- **Regrouper les décisions et séparer les actions dommageables.** Le HIG
  QGIS recommande des groupes thématiques, des commandes standard, des pages
  défilantes pour les longs contenus et une séparation des options avancées.
  Ici, cela motive les groupes courts, l’aide dépliable et la formulation
  explicite de la suppression des plans. Ses conventions de capitalisation
  anglaise et ses dimensions historiques ne sont pas appliquées littéralement
  au français et aux écrans actuels.
  [QGIS 3.44 — Human Interface Guidelines](https://docs.qgis.org/3.44/en/docs/developers_guide/hig.html).
- **Nommer chaque saisie et adapter le formulaire.** Microsoft préconise des
  libellés explicites, des contrôles adaptés au type de donnée et des
  formulaires redimensionnables. Son guide concerne XAML : les dimensions
  suggérées ne sont pas des règles Qt. Dans ce plugin, les labels persistants,
  les unités et les `QFormLayout` remplissent ce rôle.
  [Microsoft — Forms](https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/forms).
- **Laisser le moteur de disposition répartir l’espace.** Qt explique que
  les layouts réagissent au redimensionnement, à la police, au texte et aux
  éléments affichés, selon les tailles conseillées et les politiques de
  taille. Cela justifie de tester les champs et boutons effectivement rendus,
  au lieu de juger uniquement la taille minimale de la fenêtre. La page Qt 6
  a été accessible lors de cette consultation ; les liens d’archives Qt 5.15
  n’ont pas pu être relus. La compatibilité du code avec le Qt de QGIS relève
  donc de la recette, sans être déduite du seul guide Qt 6.
  [Qt — Layout Management](https://doc.qt.io/qt-6/layout.html).
- **Rendre le parcours clavier prévisible.** Microsoft recommande un focus
  visible et un ordre clavier cohérent avec l’ordre visuel. Dans le plugin,
  cela motive les labels associés aux champs, les contrôles natifs et la
  vérification de Tab, Maj+Tab et Entrée ; une saisie ne doit pas activer par
  défaut une commande d’écriture ou de calcul.
  [Microsoft — Keyboard interactions](https://learn.microsoft.com/en-us/windows/apps/develop/input/keyboard-interactions).
- **Mesurer le contraste des couleurs ajoutées.** Le W3C donne le repère de
  4,5:1 pour le texte courant, avec notamment des exceptions pour les grands
  textes et les contrôles inactifs. Il sert ici d’objectif pour les accents
  personnalisés ; une couleur de marque ne suffit pas à garantir la
  lisibilité sur les thèmes clair et sombre. Ce repère issu du Web ne
  constitue pas une certification d’accessibilité de l’application Qt.
  [W3C — Understanding Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

## Cohérence du dépôt et de l’archive

Le numéro de version provient de
[`calage_apports/metadata.txt`](../calage_apports/metadata.txt).
[`src/faire_zip.py`](../src/faire_zip.py) lit ce numéro pour nommer
`calage_apports_0.8.0.zip` et copie les modules de `src/` directement dans
`calage_apports/chaine/` à l’intérieur de l’archive. Cette chaîne embarquée ne
doit pas devenir une seconde copie éditable dans le dépôt.

La construction du ZIP comprend une vérification de la présence des fichiers
attendus, de l’identité des modules embarqués avec leurs sources, de l’absence
de bytecode et de chemins propres au poste. Le contrôle des noms d’affaires
dépend de la liste locale prévue par le constructeur. Après une modification,
la version affichée dans les documents ne prouve ni que le ZIP a été reconstruit
ni que le plugin installé a été rechargé : ces étapes se vérifient séparément.

## Recette et limites

Le contrôle visuel doit couvrir les six pages, une fenêtre de **800 × 620**,
une police ordinaire et agrandie, les aides ouvertes et fermées, les chemins
longs, le thème et le clavier. Un champ doit rester entièrement atteignable
après défilement. Les vérifications métier portent sur la conservation des
saisies, les prérequis, la lecture du classeur et l’origine du dossier suivi.

La matrice visuelle exécutée dans QGIS couvre les six pages à 940 × 760 et
800 × 620, le thème Night Mapping, l’échelle réelle de 150 % et une police
de 13 points. Dans ces scénarios observés, les six onglets et le contrôle
permanent restent visibles, sans champ comprimé ni défilement horizontal.
Le bilan final des tests automatisés est rapporté séparément dans le statut.

Les captures utilisent un projet de démonstration. Elles illustrent le rendu
observé ; elles ne prouvent pas un calage réel ni la compatibilité avec tous
les facteurs DPI ou toutes les technologies d’assistance. Les contrôles Qt,
les essais simulés et les éventuels calculs réels doivent être rapportés
séparément, avec leur périmètre.
