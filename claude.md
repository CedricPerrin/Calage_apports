# Bonnes pratiques pour limiter l'utilisation du contexte

## 1. Ne jamais analyser les gros fichiers sans demande explicite

Ne pas lire automatiquement les fichiers de résultats ou les fichiers volumineux.

Les ignorer via `.claudeignore`, par exemple :

- *.hdf
- *.tif
- *.tiff
- *.las
- *.laz
- Results/
- Output/
- Temp/
- __pycache__/
- .venv/

Ne lire ces fichiers que si je le demande explicitement.

---

## 2. Travailler uniquement sur les fichiers nécessaires

Lorsque je demande une modification, analyser uniquement les fichiers directement concernés.

Ne pas parcourir tout le projet si cela n'est pas nécessaire.

---

## 3. Garder le contexte aussi petit que possible

Après chaque tâche importante :

- résumer ce qui a été réalisé ;
- indiquer les fichiers modifiés ;
- préciser les prochaines étapes.

Ne pas recopier inutilement les anciennes explications.

---

## 4. Mettre à jour STATUT.txt

À la fin de chaque session de travail importante, mettre à jour le fichier `STATUT.txt`.

Le fichier doit contenir :

- l'état actuel du projet ;
- les décisions prises ;
- les fichiers modifiés ;
- les problèmes encore ouverts ;
- les prochaines étapes.

---

## 5. Commencer une nouvelle conversation régulièrement

Lorsque :

- une fonctionnalité est terminée ;
- un bug est résolu ;
- ou que la discussion devient très longue,

proposer de créer un nouveau chat.

Avant cela :

1. mettre à jour `CHECKPOINT.md` ;
2. résumer les éléments essentiels.

---

## 6. Ne pas relire les mêmes fichiers inutilement

Si un fichier n'a pas changé depuis son analyse précédente, éviter de le relire entièrement.

Ne relire que les parties nécessaires à la tâche en cours.

---

## 7. Réponses concises

Pour les questions simples :

- répondre brièvement ;
- éviter les longues explications ;
- éviter les répétitions.

Développer uniquement lorsque je le demande.

---

## 8. Limiter les recherches

Avant de rechercher dans tout le projet, vérifier si la réponse peut être trouvée dans le fichier actuellement ouvert ou dans les fichiers directement liés.

---

## 9. Priorité

Toujours privilégier :

1. la précision ;
2. un faible usage du contexte ;
3. un faible nombre de tokens.

La solution la plus simple est généralement la meilleure.

---

## 10. Fin de session

Avant de terminer une session importante :

- mettre à jour `CHECKPOINT.md` ;
- vérifier que le projet est cohérent ;
- proposer l'ouverture d'un nouveau chat pour repartir avec un contexte minimal.