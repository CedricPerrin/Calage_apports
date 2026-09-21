# Identité et recette UX ISL — Calage_apports

## Complément préparé, non intégré — 20 septembre 2026

La [PR #4](https://github.com/CedricPerrin/Calage_apports/pull/4) déplace aussi la
recherche initiale des interpréteurs dans une tâche QGIS : progression, annulation
entre sondes, cible figée et choix au retour du dialogue. Noyau et deux tests de
cible/recherche passent localement. Trois scénarios natifs sont ajoutés.
**Ce complément n’est pas dans main** : les nouveaux jobs [QGIS et noyau](https://github.com/CedricPerrin/Calage_apports/actions/runs/35511883676)
s’arrêtent avant attribution d’un exécuteur, sans étape exécutée. Leur cause n’est
pas exposée par le connecteur ; le navigateur disponible n’est pas connecté.
Le propriétaire GitHub doit rendre l’annotation accessible ou transmettre son texte.
Le mainteneur/Codex relance les tests, corrige si nécessaire, puis fusionne la PR.
La fusion est déjà autorisée ; aucun nouveau choix technique n’est demandé à
l’ingénieur. La recherche de main demeure synchrone tant que cette validation manque.

Référence : [ISL UX 0.1](https://github.com/CedricPerrin/ergonomie/blob/d112591b9a1bbc6ccd792c1b318821eade9982ce/DESIGN_SYSTEM_ISL.md), adoptée pour l’exécution par lots demandée le 20 septembre 2026.

| Rôle | Couleur / règle |
|---|---|
| Marque institutionnelle | Bleu-vert `#3A8D94`, ardoise `#9BAEB7`, gris `#707173` |
| Texte/action bleu-vert | Variante `#2E7176` en clair ; `#7CC4C8` sur surface sombre compatible |
| Pictogrammes métier | Dessins PIO existants autorisés, proportions conservées |
| Palette PIO | Exclue de l’habillage de l’application |
| Statuts | Texte et signe explicites ; couleurs fonctionnelles uniquement |
| Police | Police du système/hôte ; aucune redistribution de Galette |
| Données scientifiques | Unités, conventions et palettes métier préservées |

La charte du logo reste applicable : utiliser un actif existant approprié, sans
recomposer « ISL Ingénierie » avec une police. Le présent lot ne crée pas de nouvel
actif de marque et n’atteste pas un droit de redistribution des polices.

## Série 0.9.0 à 0.9.3 — 20 et 21 septembre 2026, intégrée dans `main`

Sept demandes utilisateur, traitées à la suite. Banc QGIS **rejoué sur le
poste** (QGIS 3.44.8-Solothurn, profil ISL) : **329 contrôles, aucun échec** —
c'était le premier passage depuis la 0.8.4.

| Version | Ce qui change | Preuve |
|---|---|---|
| **0.9.0** | L'onglet *Sorties* disparaît, ses groupes rejoignent *Lancer* ; le préfixe de scénario se pose au-dessus du bouton ; un récapitulatif dit d'où la reprise repart ; les paramètres quittent l'Excel pour un JSON voisin | 297 contrôles ; migration vérifiée sur le classeur d'un calage réel en cours (40 paramètres lus par la feuille héritée) |
| **0.9.1** | L'onglet *Objectifs* suit l'ordre du parcours ; une barre compte la préparation à côté de « Contrôle paramétrage » | 310 contrôles ; **fenêtre ouverte et regardée** dans le QGIS du poste |
| **0.9.2** | Le classeur n'est plus écrasé (sauvegarde horodatée) ; l'écran nomme les réglages qui ne concordent plus avec le paquet ; le journal en cours dans *Suivi* | 329 contrôles |
| **0.9.3** | Le plan final est déclaré dans le `.rasmap` : son résultat paraît dans RAS Mapper | `pilote_hecras.py` vert, 9 contrôles neufs ; essai sur copie d'un `.rasmap` réel |

**Trois défauts que seule la fenêtre réelle a montrés** (0.9.1) : QGIS ne
savait plus lire la version du plugin — une ligne de changelog à la colonne
zéro rend `metadata.txt` illisible par `configparser`, et
`pluginMetadata("version")` rendait `__error__` **depuis la 0.8.5** ; le
récapitulatif de reprise restait vide à l'ouverture ; le compte de
préparation était affiché deux fois. `faire_zip.py` refuse désormais une
archive dont QGIS ne lirait pas la version.

**Ce qui reste à faire sur le poste.** Ouvrir **RAS Mapper** sur un calage
abouti — la 0.9.3 n'a pas pu être vérifiée à l'écran. Regarder la fenêtre en
**thème clair** et à **13 pt** : seul le sombre à 940 × 780 a été vu. Refaire
les **six captures**, qui datent de la 0.8.2 et dont l'une montre un onglet
supprimé. Mesurer l'onglet *Lancer*, désormais à sept groupes, **rempli** sur
petite fenêtre.

Les retours détaillés — problème, cause, décision, preuve, limite — sont dans
[`0-Ergonomie/retours/CALAGE_APPORTS.md`](https://github.com/CedricPerrin/ergonomie),
sections 0.9.0, 0.9.1 et 0.9.2.

## Critères de recette

- [ ] Parcours principal au clavier ; noms et états annoncés par le lecteur d’écran.
- [ ] Clair, sombre et thème de contraste ; mesures sur les fonds réellement rendus.
- [ ] 125/150/200 %, texte agrandi, écran portable ; actions toujours accessibles.
- [ ] Vide, erreur, traitement, arrêt et résultats partiels explicitement distingués.
- [ ] Exports et documentation cohérents avec la version testée.

Les résultats des contrôles techniques sont consignés dans la livraison de chaque
lot. Les cases ci-dessus ne sont cochées qu’après observation native : un test
Qt hors écran sous Linux ne valide pas Windows/QGIS ni le lecteur d’écran.

[Plan propre au dépôt](https://github.com/CedricPerrin/ergonomie/blob/main/audits/Calage_apports.md) ·
[Recette commune](https://github.com/CedricPerrin/ergonomie/blob/main/guides/RECETTE_UX_PC.md).

## Lots B et C — intégrés dans main, recette sur poste requise

B : le fil conducteur annonce l'écriture dans la géométrie HEC-RAS, la sauvegarde horodatée et les fichiers produits. L'attribution historique des couleurs à PIO/Helvetica est corrigée. Les rôles existants `interface.py` conservent l'adaptation au thème ; aucune palette scientifique n'est modifiée.

C : `installation.py` confie création du venv, pip et vérification à `QgsTask`. Le dossier confirmé est passé explicitement au noyau. La progression est indéterminée, accompagnée des phases ; le journal et les erreurs sont conservés dans le journal QGIS. Le réglage du Python est enregistré seulement après succès vérifié, sur le fil graphique. Une seconde installation et les opérations HEC-RAS du dialogue sont refusées pendant le travail. Les commandes du poste sont désactivées puis restaurées.

Fermer le dialogue laisse travailler la tâche détenue par QGIS ; le déchargement déconnecte ses récepteurs. Un échec ne rouvre pas une fenêtre fermée et la boîte de détail affichée ne bloque pas `finished()`. Pas d'annulation au milieu de pip : cette limite et la nécessité de garder QGIS ouvert sont annoncées avant lancement. L'environnement existant n'est jamais supprimé ; un pip échoué peut laisser des paquets partiellement actualisés, la relance et le diagnostic restent nécessaires.

**Limite restante :** la recherche initiale des Python candidats est encore synchrone. Ce lot déplace les phases longues de création/installation/vérification, pas toutes les sondes de préparation.

Contrôles complétés le 20/09 : l’autotest complet `noyau.py` passe localement et en CI. Dans **QGIS 3.44.7 / Qt 5.15.13 réels**, les quatre tests du gestionnaire et du cycle de dialogue passent, ainsi que les quatre tests cible/worker. Le banc historique compte **299 contrôles réussis** : saisies, clavier, petite fenêtre, police 9/13 pt, rôles de thème et états. [Exécution vérifiée](https://github.com/CedricPerrin/Calage_apports/actions/runs/35504377871), code `2359e4da9206`.

La tâche tourne réellement dans `QgsTaskManager` ; un minuteur du fil graphique continue de battre pendant l’attente. Succès, erreur pip et exception sont simulés uniquement à la frontière de l’installeur. Fermeture/réouverture, déchargement, nouveau dialogue et refus du double lancement sont éprouvés. Aucun pip métier ni modèle d’affaire n’est utilisé. Dans le banc Linux, la sonde de PID Windows est remplacée par une sonde POSIX réelle : `tasklist` reste à éprouver sur Windows. La famille de police est résolue avant la mesure et le test des liens donne le focus à une fenêtre active avant Tab/Entrée, conformément au [fonctionnement Qt](https://doc.qt.io/qt-6/qt.html#TextInteractionFlag-enum).

`tools/check_isl_identity.py` contrôle **10 correspondances** avec ISL UX 0.1.0 à chaque CI. Son contrat est `docs/isl-identity-contract.json` ; les couleurs institutionnelles et leurs variantes accessibles sont vérifiées dans les affectations Python.

Les commandes sont versionnées dans `.github/workflows/ux-qgis.yml` et se relancent à chaque changement. À observer sur le poste cible : installation réelle via le réseau ISL, réactivité du canevas, lecteur d’écran, DPI et suivi d’un véritable processus HEC-RAS. L’arrêt complet de QGIS pendant pip n’est pas un scénario d’annulation garanti. La [fiche des interventions sur poste](https://github.com/CedricPerrin/ergonomie/blob/main/guides/A_FAIRE_SUR_PC.md) fournit les versions et scénarios.

API utilisées : [tâches QGIS](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/tasks.html), [QgsTask](https://api.qgis.org/api/classQgsTask.html), consultées le 20/09/2026 ; `run()` n'accède à aucun widget, `finished()` revient sur le fil graphique.

Aucune archive de diffusion remplacée : la prochaine archive aura une nouvelle version après la recette native.

## Intégration et prochaine intervention — 20 septembre 2026

La [PR #3](https://github.com/CedricPerrin/Calage_apports/pull/3)
est fusionnée dans `main`. Le [registre commun](https://github.com/CedricPerrin/ergonomie/blob/main/SUIVI_LOTS_2026-09-20.md) consigne le résultat de la fusion,
le commit et sa CI. Utiliser cette version des sources pour la recette ; les
anciennes archives et observations restent attachées à leur version d’origine.

| Suite | Responsable | Preuve attendue |
|---|---|---|
| Installation réelle sur le réseau ISL, copie de modèle, suivi et arrêt Windows ; affichage DPI/thèmes et Narrateur. | Ingénieur utilisateur, accompagné du référent UX | Configuration, scénario, résultat et capture/journal si défaut |
| Corriger un défaut reproductible et mettre à jour ses guides | Mainteneur du dépôt, assisté de Codex | Correctif et contrôle ciblé réussis |
| Préparer la diffusion après recette | Mainteneur et interlocuteur informatique ISL si nécessaire | Archive identifiée, contenu vérifié et installation contrôlée |

La [fiche commune](https://github.com/CedricPerrin/ergonomie/blob/main/guides/A_FAIRE_SUR_PC.md) précise les gestes. L’intégration des sources ne coche
aucune observation d’usage. Les couleurs institutionnelles et l’utilisation possible
des pictogrammes PIO sont déjà décidées.
