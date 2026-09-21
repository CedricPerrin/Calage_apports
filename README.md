# Calage_apports

**20 septembre 2026 — lot UX B/C, intégration dans `main` demandée ([PR #3](https://github.com/CedricPerrin/Calage_apports/pull/3)).**
Effets du contrôle explicités ; installation Python dans une tâche QGIS avec journal et protection contre les doubles lancements.
Voir [les changements, contrôles et limites](docs/UX_ISL.md) et le
[suivi d’intégration](https://github.com/CedricPerrin/ergonomie/blob/main/SUIVI_LOTS_2026-09-20.md). Les preuves antérieures ci-dessous restent datées ;
la nouvelle recette visuelle et métier sur le poste ISL reste à réaliser.
Les ZIP déjà publiés précèdent ce lot : utiliser les sources de `main` pour la recette.

Ajustement séquentiel d'apports amont sur des hydrogrammes cibles aval, pour
les modèles 2D HEC-RAS — chaîne Python + plugin QGIS. Projet ISL Ingénierie.

Version des sources du plugin : **0.9.2**. La
[note d’ergonomie du 11 septembre 2026](docs/ergonomie_2026-09-11.md)
décrit le parcours, les choix d’interface et les points de recette.

La version 0.8.0 a passé **248 contrôles Qt** et **30 scénarios d'affichage**
dans QGIS 3.44.8, dont petites fenêtres, thème sombre et écran à 150 %.
La chaîne hydraulique reste inchangée ; aucun nouveau calage réel n'a été
lancé pour cette révision. [Mesures de la recette](docs/ergonomie_2026-09-11-mesures.json).
La **0.8.2** en passe **258, sans échec** : le débordement horizontal de
l'onglet Objectifs à 13 points, présent depuis la 0.8.0, est corrigé.
Elle remplace trois aides dépliables maison par des groupes repliables
QGIS, les boîtes d'information par un bandeau de messages, et retient la
taille de la fenêtre d'une session à l'autre.
La **0.8.3** en passe **270, sans échec** : relancer un calage demande par où
reprendre — les apports déjà calés en amont du départ sont conservés — et
l'onglet Suivi garde le calage précédent au lieu de l'écraser.
La **0.8.4** en passe **278, sans échec** : le préfixe de scénario nomme
l'Excel des objectifs — `donnees_calage_Q100.xlsx` —, si bien que deux
scénarios d'un même dossier de sortie ont deux classeurs ; les erreurs et
avertissements du journal de lancement remontent dans l'onglet Suivi ; et
HEC-RAS ouvert refuse le lancement au lieu de poser une question.
La **0.8.5** vient d'une [relecture ergonomique du 17 septembre](docs/ergonomie_2026-09-17.md)
menée avec la grille du dépôt `ergonomie` : l'onglet Suivi suit le thème
sombre — ses widgets peints et son tableau gardaient les couleurs du clair,
ardoise à 2,3:1 et rouge à 1,8:1 sur Night Mapping — et la police du
poste ; les quatre questions Oui/Non ont un défaut sûr et des verbes ; le
teal institutionnel ne sert plus de couleur de texte ; les liens du fil
conducteur se prennent au clavier. Le banc gagne 23 contrôles, **non
rejoués** : cette version a été écrite sans QGIS, et son premier passage au
banc reste à faire.
La **0.8.6** fusionne la revue de qualité de la 0.8.4 menée le 17 sur une
branche : `classeur` en propriété, journal du Suivi relu seulement s'il a
changé, `noyau.dernier_journal`, compte rendu HEC-RAS coupé au tableau des
temps, `plan_fenetre_pleine` en reprise seulement. Rien de visible ne
change ; le banc QGIS reste à rejouer.

La **0.8.7** porte les lots UX B et C du 20 septembre : le fil conducteur
annonce ce que le bouton de contrôle écrit dans la géométrie, et
`installation.py` confie la création du venv, `pip` et la vérification à un
`QgsTask` — phases affichées, journal dans celui de QGIS, réglage retenu
seulement après succès vérifié, double lancement refusé. Ni annulation au
milieu de `pip`, ni recherche d'interpréteurs asynchrone. Banc sous QGIS
3.44.7 / Qt 5.15.13 : **299 contrôles réussis** ;
[détail et limites](docs/UX_ISL.md).

La **0.8.8** remplace une déduction par deux faits. Le champ
`Short Identifier` d'un plan — dont RAS Mapper fait le nom du dossier de
résultats — accepte **au moins 40 caractères** sous HEC-RAS 7.0.1, là où la
chaîne s'arrêtait à 30, le plus long exemple d'un relevé de 103 plans. Mais
le plafond utile est **32**, et il vient de `ras-commander` 0.99.1, qui lève
`ValueError` au-delà sur `Plan Title` et `Flow Title` : la borne est celle de
la bibliothèque, pas du format. Et le
contrôle du classeur éprouve le titre de **reprise** pour chaque départ
possible : il ne jugeait que « Premier_apport », qui s'écrit au lancement,
donc après lui.

La **0.9.0** repond a trois demandes du 20 septembre. L'onglet **Sorties**
disparait : ses groupes rejoignent **Lancer**, apres les apports a determiner,
et le **prefixe de scenario** vient se poser juste au-dessus du bouton — cinq
rubriques au lieu de six. Le lancement **dit ce qu'il va faire** avant le clic :
d'ou le calage repart, de quel plan d'etape, quels apports sont tenus pour
cales et lesquels seront calcules. Et la feuille **« Parametres » quitte
l'Excel** : les valeurs vivent dans un JSON qui porte le nom du classeur, a
cote de lui ; leurs commentaires descendent dans la feuille de garde. Les
classeurs composes avant cette version sont **encore lus par leur feuille**.

La **0.9.2** : recomposer **met l'ancien classeur de cote, horodate**, au
lieu de le reecrire en place — le nom canonique ne bouge pas ; l'ecran
**nomme les reglages qui ne concordent plus** avec le paquet compose, car
c'est le paquet que le calage lit ; et le Suivi porte le **journal en
cours**, deroulant, a cote de l'encadre des alertes qui, lui, ne retient
que les lignes portant un mot d'alerte.

Pour chaque apport, de l'amont vers l'aval : estimer, calculer, comparer à la
cible, corriger, répéter jusqu'à concordance, puis vérifier la cohérence des
sections amont avant de passer au suivant.

**Le réseau ne comporte pas de boucle hydraulique : c'est une hypothèse du
modèle, posée par l'hydraulicien, et rien dans la chaîne ne la vérifie.**
L'ordre total amont → aval est ce qui donne un sens à « section suivante » ;
sur un réseau bouclé — bras qui se rejoignent, casiers interconnectés — un
apport alimenterait plusieurs sections par des chemins distincts, et la
méthode ne s'applique pas. Confirmée par l'hydraulicien le 8 septembre 2026
pour les modèles en cours. Les hypothèses de validité sont au § 1.2 de la
note méthodologique.

Le calage laisse dans le modèle **un plan HEC-RAS par étape** —
`Q100_sans_apport`, `Q100_Apport_A1`… puis `Q100_avec_apports`, qui n'est pas un
clone mais la dernière étape retitrée, avec ses résultats. Ils sont conservés :
ils documentent le calage et permettent de reprendre une séquence interrompue.
Dans **Lancer**, une case permet leur suppression **sur demande**,
uniquement après un calage réussi.

La boucle ([src/calage.py](src/calage.py)) est **indépendante du solveur** : elle
n'en connaît qu'une interface de neuf méthodes, dont six à écrire. Elle est donc
testable sans HEC-RAS, dont la déclinaison vit dans
[src/pilote_hecras.py](src/pilote_hecras.py).

## Démarrage

```bat
REM Un Python ORDINAIRE — surtout pas celui de QGIS : voir ci-dessous.
pip install -r requirements-dev.txt
cd src
python verification_environnement.py
```

`verification_environnement.py` contrôle tout ce qu'exige la mise en œuvre —
interpréteurs, dépendances, fichiers — et nomme ce qui manque.

[requirements-dev.txt](requirements-dev.txt) dit ce qu'il faut pour travailler
sur le code, et surtout ce qui n'y est **pas** : `ras-commander` et `h5py` vivent
dans un interpréteur séparé (conflit HDF5 avec QGIS), `qgis` et `PyQt` viennent
de l'installation QGIS.

Pour saisir les données d'un calage, partir de
[template_donnees_calage.xlsx](template_donnees_calage.xlsx) **et de son
[template_donnees_calage.json](template_donnees_calage.json)** — le classeur
porte la correspondance et les cibles, le JSON porte les paramètres, et les
deux se déplacent ensemble. La feuille de garde du classeur explique chaque
paramètre. Puis lancer la chaîne en ligne de commande ou depuis le plugin.

### Avec quel Python ?

Le dépôt en côtoie trois, et les confondre donne des diagnostics qui ressemblent
à des pannes.

| à lancer | avec quoi |
|---|---|
| `verification_environnement.py` | un Python **ordinaire**, ou celui du `venv-hecras` |
| `test_plugin_qgis.py` | le **Python de QGIS** (`python-qgis-ltr.bat`) — il construit la fenêtre |
| les auto-tests de `src/*.py` | l'un ou l'autre, selon leurs imports |

Sous le Python de QGIS, `verification_environnement.py` rend `DLL load failed
while importing _errors` sur `ras-commander`. **Ce n'est pas une panne** : QGIS
embarque sa propre bibliothèque HDF5, et `h5py` y est inutilisable — c'est
précisément la séparation que le projet impose.

## Structure du dépôt

`src/` porte la chaîne Python. C'est un dossier de développement, pas un paquet
distribué : le plugin en embarque une copie autonome à l'installation.

| Fichier / dossier | Rôle |
|---|---|
| [src/calage.py](src/calage.py) | Boucle de calage séquentiel |
| [src/criteres.py](src/criteres.py) | Analyse pure : recalage temporel, corrélation de forme, diagnostic |
| [src/parametres.py](src/parametres.py) | Les paramètres d'un calage : le JSON voisin du classeur, et la lecture des classeurs d'avant |
| [src/controle_donnees.py](src/controle_donnees.py) | Validation du classeur et de la chaîne SIG avant tout calcul |
| [src/geometrie.py](src/geometrie.py) | Shapefiles, PK par projection curviligne, écriture dans la géométrie HEC-RAS |
| [src/livrables.py](src/livrables.py) | Graphiques, tableaux, export Excel, note de synthèse |
| [src/suivi.py](src/suivi.py) | Avancement lisible pendant le calcul |
| [src/pilote_hecras.py](src/pilote_hecras.py) | Déclinaison HEC-RAS de l'interface `Modele` |
| [src/pont_hecras.py](src/pont_hecras.py) | Pont en ligne de commande répondant en JSON — `ras-commander` est inimportable dans le processus QGIS |
| [src/creer_template.py](src/creer_template.py) / [src/style_classeur.py](src/style_classeur.py) | Fabrication et mise en forme du classeur de saisie |
| [src/verification_environnement.py](src/verification_environnement.py) | Contrôle de l'environnement |
| [src/faire_zip.py](src/faire_zip.py) | Construit `calage_apports_<version>.zip`, l'archive d'installation — le numéro vient de `metadata.txt`, et l'archive précédente est retirée |
| [src/essai_garde_fou_archive.py](src/essai_garde_fou_archive.py) | Essai **adverse** : injecte trois fautes dans l'archive et vérifie qu'elles sont refusées |
| [src/test_plugin_qgis.py](src/test_plugin_qgis.py) | Suite du plugin, sous le Python de QGIS et sur une **copie** d'un modèle — elle **modifie** la géométrie de celui qu'on lui donne (voir ci-dessous) |
| [src/reference_calage_fictif.json](src/reference_calage_fictif.json) | Sortie figée d'un calage sur `ModeleFictif`, comparée à chaque passage du banc. **Ne pas modifier à la main** : `python calage.py --figer-reference` la réécrit |
| [src/elaguer_projet.py](src/elaguer_projet.py) | Rattrapage : élague les plans laissés par l'**ancienne** chaîne |
| [src/reconstruire_livrables.py](src/reconstruire_livrables.py) | Rattrapage : reconstruit les livrables d'un calage **terminé**, en lecture seule sur le modèle |
| [src/captures_plugin.py](src/captures_plugin.py) | Refait les six captures de ce README, sous le Python de QGIS — une capture périmée ressemble à une capture |
| `src/figures_note/` | Reconstruction de la note méthodologique |
| [methodologie_calage_amont_aval.docx](methodologie_calage_amont_aval.docx) | Note méthodologique : mode opératoire, méthode, application HEC-RAS/QGIS, livrables |
| `calage_apports_<version>.zip` | **L'archive à installer dans QGIS** — son nom porte la version, prête à l'emploi |
| `calage_apports/` | Sources du plugin QGIS — voir son [LISEZMOI.md](calage_apports/LISEZMOI.md) |
| [STATUT.txt](STATUT.txt) | État courant et règles en vigueur — la référence pour le détail |
| `charte/` | Identité graphique ISL Ingénierie |

### Lancer la suite du plugin

```bat
"…\bin\python-qgis-ltr.bat" test_plugin_qgis.py --modele "<dossier du modèle>"
```

Sans `--modele`, elle tourne quand même et annonce ce qu'elle saute. `--plan` et
`--geometrie` se déduisent du dossier — mais la déduction prend le **premier**
fichier par ordre alphabétique : les passer explicitement dès qu'un projet porte
plusieurs plans. `--objet <nom d'une condition limite>` ouvre une section de
plus. Le modèle doit porter au moins une ligne d'injection et une ligne de
référence, la seconde en **aval** de la première.

## La fenêtre du plugin

Cinq rubriques : **Modèle → Objectifs → Lancer → Suivi**, puis
**Aide et configuration**. Les commandes de navigation et **Contrôle paramétrage** restent
accessibles en bas de la fenêtre. Les pages longues défilent ; les détails
secondaires se déplient à la demande. Au bas de la fenêtre, **une barre
compte les quatre étapes de la saisie avant lancement** — modèle, profil en
long, dossier de sortie, paquet composé — à côté du bouton qu'elle prépare ;
elle ne dit rien du calage lui-même, qui se lit à l'étape Suivi. Le fil
conducteur, juste au-dessus, ne porte plus que la prochaine étape et son
lien : le compte s'y lisait une seconde fois. Les images sont produites avec un
projet de démonstration par [src/captures_plugin.py](src/captures_plugin.py).

> **Les captures datent de la 0.8.2 et ne montrent plus la fenêtre.** La
> 0.9.0 supprime l'onglet Sorties, déplace le préfixe de scénario et ajoute
> le récapitulatif de reprise ; avant elle, la 0.8.3 avait ajouté le statut
> « repris » au Suivi et la 0.8.5 changé le libellé du préfixe. **Seul
> l'onglet 1 ressemble encore à son image, et la capture « onglet 2 » montre
> un onglet qui n'existe plus.** À refaire par `captures_plugin.py`, sous le
> Python de QGIS — une capture périmée ressemble à une capture.

**1. Modèle** — le projet HEC-RAS (**on désigne le fichier `.prj`, pas le
dossier**), le plan de référence, la géométrie, la zone 2D, le **profil en
long** — l'axe, son sens, le PK d'origine — et la fenêtre de simulation. C'est
d'ici que les couches du modèle arrivent sur la carte, éditables. Ce qu'on
y dessine est écrit dans la géométrie par le bouton du bas.

![Onglet 1 — Modèle](docs/captures/onglet_1_modele.png)

**2. Objectifs** — dans l'ordre du parcours. D'abord la **précision du
calage** : elle distingue l’**écart admis à la cible** de l’erreur de bilan de
masse HEC-RAS, et le nombre maximal d’essais y reste réglable. Ensuite le
geste qui ouvre la saisie — **Contrôle paramétrage**, en bas de la fenêtre,
compose l'Excel — dit **hors** du groupe qu'il débloque. Puis l’**Excel des
hydrogrammes objectifs**, à ouvrir ou à reprendre. Enfin **ce que ces
hydrogrammes portent** une fois l’Excel validé : débit de pointe, heure du pic
et volume de chaque apport. Une cible collée dans la mauvaise colonne, un
facteur d'unité ou une colonne restée vide s'y voient avant les heures de
calcul ; le résultat se lit en pourcentage d’atteinte de la cible.

![Onglet Objectifs](docs/captures/onglet_3_objectifs.png)

**3. Lancer** — tout ce qui décide du lancement, dans l'ordre où il se
décide : l'appariement apport → section et l'état des cibles ; le **premier
apport à caler** ; le **dossier de sortie**, ses sous-dossiers et le sort des
**plans d'étape** — conservés par défaut, la case de suppression ne
s'appliquant qu'après un calage réussi ; la configuration complète, repliée ;
le **préfixe de scénario** — **obligatoire** : sans lui, caler le Q10 après le
Q100 sur le même modèle effacerait les plans du Q100 ; puis le lancement.
**Au-dessus du bouton, un récapitulatif dit ce que ce clic va faire** : d'où le
calage repart, de quel plan d'étape — nommé avec son préfixe, tel qu'il figure
dans le gestionnaire de plans —, quels apports sont tenus pour calés et
lesquels seront calculés. Il se lit avant, et se relit après. Un accès direct
permet de consulter le suivi.

![Onglet 4 — Lancer](docs/captures/onglet_4_lancer.png)

**4. Suivi** — où en est le calcul, apport par apport, rafraîchi tout seul. Le
dossier surveillé est nommé en permanence : c'est celui que désigne l'Excel
lancé. Les champs de **Lancer** préparent la prochaine composition. La
courbe porte la cible et la section de l’apport en cours, et **derrière,
en vert pointillé, les sections déjà
calées** : c'est la famille de courbes qui dit si tout se tient.

![Onglet 5 — Suivi](docs/captures/onglet_5_suivi.png)

**Aide et configuration** — diagnostic et paramètres du poste immédiatement accessibles,
puis mode opératoire avec sommaire et pièges connus. Les emplacements de la
chaîne de calage et de l’interpréteur HEC-RAS y restent configurables.

![Onglet Aide et configuration](docs/captures/onglet_6_aide.png)

Le bouton **« Contrôle paramétrage »** est permanent, au bas de la fenêtre à
côté de *Fermer* : il consomme les trois premiers onglets et prépare le
quatrième, il n'appartient donc à aucun. Il écrit dans la géométrie HEC-RAS,
compose le paquet et lance les contrôles, dans cet ordre — et la première de
ces trois choses est le seul geste irréversible de la fenêtre. **Vert** dès
que tout ce qu'il consomme est prêt, **gris** tant qu'il manque quelque
chose. L’état de préparation indique ce qu’il reste à renseigner ; le
contrôle conserve ses garde-fous métier.

La recette et la construction du ZIP sont distinctes de cette description
de l’interface. Le bilan courant est consigné dans [STATUT.txt](STATUT.txt).

## Licence

Le plugin (`calage_apports/`) est distribué sous GPL-2.0-or-later — voir
[calage_apports/LICENSE.txt](calage_apports/LICENSE.txt). Copyright © 2026
ISL Ingénierie.
