# Bonnes pratiques pour limiter l'utilisation du contexte
## 0.Karpathy-Inspired Claude Code Guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

Tradeoff: These guidelines bias toward caution over speed. For trivial tasks, use judgment.

1. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:

State your assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them - don't pick silently.
If a simpler approach exists, say so. Push back when warranted.
If something is unclear, stop. Name what's confusing. Ask.
2. Simplicity First
Minimum code that solves the problem. Nothing speculative.

No features beyond what was asked.
No abstractions for single-use code.
No "flexibility" or "configurability" that wasn't requested.
No error handling for impossible scenarios.
If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

3. Surgical Changes
Touch only what you must. Clean up only your own mess.

When editing existing code:

Don't "improve" adjacent code, comments, or formatting.
Don't refactor things that aren't broken.
Match existing style, even if you'd do it differently.
If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:

Remove imports/variables/functions that YOUR changes made unused.
Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

4. Goal-Driven Execution
Define success criteria. Loop until verified.

Transform tasks into verifiable goals:

"Add validation" → "Write tests for invalid inputs, then make them pass"
"Fix the bug" → "Write a test that reproduces it, then make it pass"
"Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:

1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

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