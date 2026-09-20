# Identité et recette UX ISL — Calage_apports

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

## Lots B et C — réalisés dans la branche, recette native requise

B : le fil conducteur annonce l'écriture dans la géométrie HEC-RAS, la sauvegarde horodatée et les fichiers produits. L'attribution historique des couleurs à PIO/Helvetica est corrigée. Les rôles existants `interface.py` conservent l'adaptation au thème ; aucune palette scientifique n'est modifiée.

C : `installation.py` confie création du venv, pip et vérification à `QgsTask`. Le dossier confirmé est passé explicitement au noyau. La progression est indéterminée, accompagnée des phases ; le journal et les erreurs sont conservés dans le journal QGIS. Le réglage du Python est enregistré seulement après succès vérifié, sur le fil graphique. Une seconde installation et les opérations HEC-RAS du dialogue sont refusées pendant le travail. Les commandes du poste sont désactivées puis restaurées.

Fermer le dialogue laisse travailler la tâche détenue par QGIS ; le déchargement déconnecte ses récepteurs. Un échec ne rouvre pas une fenêtre fermée et la boîte de détail affichée ne bloque pas `finished()`. Pas d'annulation au milieu de pip : cette limite et la nécessité de garder QGIS ouvert sont annoncées avant lancement. L'environnement existant n'est jamais supprimé ; un pip échoué peut laisser des paquets partiellement actualisés, la relance et le diagnostic restent nécessaires.

**Limite restante :** la recherche initiale des Python candidats est encore synchrone. Ce lot déplace les phases longues de création/installation/vérification, pas toutes les sondes de préparation.

Contrôles du 20/09 : compilation Python ; un test du noyau sur la cible confirmée passe ; succès, échec pip et exception passent dans trois tests du worker avec vrais signaux Qt et thread Python, enveloppe QgsTask simulée. Aucune installation de paquets métier n'a été lancée. L'autotest complet `noyau.py` est bloqué dans cette copie par l'absence de geopandas ; aucune réussite de ce banc n'est revendiquée.

À exécuter sous Python QGIS : `python -m pytest src/test_installation_cible.py src/test_installation_tache.py -q`, puis le banc `src/test_plugin_qgis.py`. Tester sur un environnement jetable : succès, PyPI inaccessible, erreur pip, fermeture/réouverture, déchargement/rechargement pendant pip, prévention du second lancement, fin de tâche sans dialogue. Vérifier que le canevas QGIS répond pendant le téléchargement. L'arrêt complet de QGIS pendant pip n'est pas un scénario d'annulation garanti.

API utilisées : [tâches QGIS](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/tasks.html), [QgsTask](https://api.qgis.org/api/classQgsTask.html), consultées le 20/09/2026 ; `run()` n'accède à aucun widget, `finished()` revient sur le fil graphique.

Aucune archive de diffusion remplacée : la prochaine archive aura une nouvelle version après la recette native.
