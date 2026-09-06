# AUDIT — Calage des apports

Audit de complexité réelle, en **lecture seule**. Aucun fichier source n'a été
modifié. Écrit le 5 septembre 2026, sur `claude/connaissance-des-md-qjbpro`
au commit `c747c32`.

Outillage : `ruff 0.15.8`, `vulture 2.16`, `radon 6.0.1`, `pylint 4.0.8`,
`deptry 0.25.1`. Toutes les sorties citées sont brutes.

> **Environnement de l'audit.** Linux, sans `h5py`, `ras-commander`, `xarray`,
> `pywin32`, `PyQt` ni QGIS. Trois bancs s'interrompent pour cette seule
> raison, et c'est dit à chaque fois. Rien de ce qui suit ne repose sur une
> exécution sous HEC-RAS.

---

## 1. Synthèse en dix lignes

1. **Un défaut de correction (P0) : `re` n'est importé nulle part dans
   `pont_hecras.py`**, et son usage est enfermé dans un `except Exception`.
   *(Corrigé au lot 3, avec le garde-fou qui l'aurait attrapé.)*
2. Conséquence : **le deuxième échelon du repli des pentes n'a jamais
   fonctionné**. Tout apport dont la case `Pente_m_par_m` est vide garde la
   pente déjà en place — 1 % pour une injection créée par le plugin.
3. Le code et la documentation promettent tous deux ce repli, verbatim.
   `STATUT.txt` § 6 a même **clos un point ouvert** sur cette lecture.
4. La dette structurelle est **concentrée** : `caler()` pèse 699 lignes pour
   une complexité cyclomatique de **81**. Le reste du dépôt est en moyenne à B.
5. **Le code mort est quasi inexistant** : 4 constats `ruff`, 2 `vulture` à
   100 %. Un dépôt de 25 800 lignes déjà relu.
6. **Aucune duplication qui vaille d'être factorisée.** Les deux seuls clusters
   sont des choix documentés (invariant 3) ou du gréement de banc.
7. **Aucun cycle d'import réel** : les deux cycles apparents passent tous par
   des imports locaux, imposés par la contrainte HDF5/QGIS.
8. **Aucun secret, aucun chemin absolu** dans le code distribué. Le garde-fou
   d'archive fait son travail.
9. La surface de tests est solide (**≈ 370 contrôles**) mais **inégale** :
   `style_classeur.py` est compté parmi les quinze bancs verts et **ne
   contrôle rien du tout**.
10. Trois dérives documentaires portent sur le **premier outil qu'un nouvel
    arrivant lance**, `verification_environnement.py`.

---

## 2. PHASE A — Carte

### A.1 Points d'entrée réels

| Entrée | Appelée par | Confiance |
|---|---|---|
| `calage_apports/__init__.py:classFactory` | **QGIS, par son nom** | 5 |
| `plugin.py:PluginCalage.initGui / unload` | QGIS | 5 |
| `pont_hecras.py:main` (sous-commandes `argparse`) | `noyau.appeler_pont`, en sous-processus | 5 |
| `if __name__ == "__main__"` × 13 | l'opérateur, à la main | 5 |
| `verification_environnement.py` | **script sans garde `__main__`** : tout s'exécute à l'import | 5 |
| `faire_zip.py` / `essai_garde_fou_archive.py` | l'opérateur | 5 |

Aucun `.ui`, aucun `.qrc`, aucun `resources_rc.py`, aucun `ui_*.py` :
l'interface est **construite en code**. Le piège « grep les .ui avant de
supprimer une méthode » est donc sans objet ici — vérifié :

```
$ find . -name "*.ui" -o -name "*.qrc" -o -name "resources_rc.py" -o -name "ui_*.py"
(aucun résultat)
```

Aucun algorithme Processing (`initAlgorithm`, `processAlgorithm`,
`createInstance`) : le plugin est une fenêtre, pas un fournisseur.

### A.2 Graphe d'imports — 2 cycles apparents, 0 cycle réel

```
calage            -> criteres, livrables, suivi
controle_donnees  -> calage, geometrie, pilote_hecras, style_classeur
livrables         -> criteres
noyau             -> controle_donnees, geometrie, pilote_hecras, style_classeur
pilote_hecras     -> calage, geometrie, pont_hecras
pont_hecras       -> calage, controle_donnees, criteres, geometrie, pilote_hecras, suivi
suivi             -> criteres, livrables
```

Deux cycles : `pilote_hecras ↔ pont_hecras` et
`controle_donnees → pilote_hecras → pont_hecras → controle_donnees`.

**Aucun n'est réel.** Mesure du niveau de chaque import :

```
pilote_hecras -> pont_hecras        fonction@2189
pont_hecras   -> pilote_hecras      fonction@735, 879, 955, 1202, 1462
pont_hecras   -> controle_donnees   fonction@521, 596, 734, 878, 954, 1123, 2048
controle_donnees -> pilote_hecras   fonction@37
```

Un seul import interne est au niveau module (`pilote_hecras -> calage @35`).
Tous les autres sont **locaux à une fonction**, ce qu'impose la contrainte
HDF5/QGIS. **Confiance 5. Ne pas « corriger ».**

### A.3 God files

| Fichier | Lignes | Symboles publics |
|---|---|---|
| `calage_apports/plugin.py` | 4 214 | 26 |
| `src/pilote_hecras.py` | 3 248 | 21 |
| `src/calage.py` | 3 487 | 22 |
| `calage_apports/noyau.py` | 3 002 | **47** |
| `src/pont_hecras.py` | 2 099 | 14 |

`noyau.py` porte 47 symboles publics : c'est la façade complète que `plugin.py`
appelle. Découper, si un jour c'est fait, se fait **en dernier** (phase C).

### A.4 Surface de tests — ce qu'elle protège réellement

Contrôles effectivement rendus, mesurés sur ce clone :

| Banc | Contrôles | Remarque |
|---|---|---|
| `calage.py` | **120** | le cœur, bien couvert |
| `criteres.py` | **66** | + les 9 du § 7 ter ajoutés aujourd'hui |
| `suivi.py` | 48 | |
| `verification_environnement.py` | 39 OK / 4 MANQ | les MANQ sont l'absence de HEC-RAS ici |
| `noyau.py` | 37 | s'arrête en section 9 (arborescence Windows) |
| `geometrie.py` | 26 | |
| `livrables.py` | 16 | |
| `pilote_hecras.py` | 11 | s'interrompt (`h5py`) |
| `controle_donnees.py` | 6 | |
| `creer_template.py` | 0 affiché | **contrôle réel** : `sys.exit(1)` si le template échoue |
| `elaguer_projet.py` | 0 | s'interrompt (`h5py`) |
| **`style_classeur.py`** | **0** | **aucun contrôle — voir P1-2** |

**Jeux de référence : aucun modèle HEC-RAS dans le dépôt.**
`test_plugin_qgis.py` exige `--modele`, une **copie** d'un modèle réel gardée
hors du dépôt. Il n'existe donc **aucun test de non-régression numérique
rejouable sans le poste**. Confiance 5.

### A.5 Dérive documentaire — ✅ **traitée au lot 2**

Confiance 5 sur les trois constats — chacun est une citation.

1. `verification_environnement.py` (lancé en premier par le README) affiche :
   `RESTE A EPROUVER : seul un apport unique a ete cale de bout en bout sur
   cas reel.` **Trois calages complets ont abouti** (6, 12 et 6 apports).
2. Le même outil contrôle `fenetre a 4 onglets presente dans plugin.py` et
   annonce `Modele HEC-RAS / Profil en long / Resultats et suivi / Validation`.
   **La fenêtre en compte six** (Modèle, Profil en long, Résultats, Lancer,
   Suivi, Aide). Le contrôle passe — il vérifie sept symboles, pas des onglets.
3. `STATUT.txt` § 6 porte comme ouvert « L'ONGLET 4 SE TAIT QUAND L'ETAT DES
   CIBLES EST ILLISIBLE ». **C'est fait** (0.6.6) : le `except` de
   `_maj_onglet_validation_depuis_classeur` journalise et affiche
   `(illisible : …)`. `STATUT.txt` s'en prévient lui-même : *« Trois des points
   de cette liste étaient déjà faits quand on les a repris. »*

---

## 3. PHASE B — Constats

> **Les numéros de ligne sont ceux du commit audité, `c747c32`.** Le lot 1 a
> depuis retiré une ligne de `src/pont_hecras.py` (l'import mort de P2-8) : tout
> ce qui suit la ligne 269 dans ce fichier a glissé d'un cran. **P0-1 est le
> seul constat encore vivant** qui en dépend — il est aujourd'hui aux lignes
> **539-541**, dans `_pentes_deduites` (508-562), avec son `except` en 555-558.
> Vérifiable à tout moment par
> `ruff check --select F821 --no-cache src/pont_hecras.py`.

### P0 — comportement / résultat numérique

#### P0-1 · `re` n'est pas importé dans `pont_hecras.py` : la pente déduite du fond n'a jamais fonctionné — ✅ **corrigé au lot 3**

| | |
|---|---|
| **Sévérité** | **P0** — résultat numérique |
| **Fichier** | `src/pont_hecras.py:540-542`, fonction `_pentes_deduites` (509-563) |
| **Certitude** | **CERTAIN** |

**Preuve — 1. l'outil.**

```
$ ruff check --select F821 --no-cache --output-format concise src calage_apports
src/pont_hecras.py:540:18: F821 Undefined name `re`
src/pont_hecras.py:542:28: F821 Undefined name `re`
```

**Preuve — 2. l'AST.** Aucun `import re` dans le module :

```
re importe dans pont_hecras.py ? False
```

**Preuve — 3. le code, verbatim** (`src/pont_hecras.py:540-542`) :

```python
        trouve = re.search(r"^Geom File=g(\w+)",
                           plan.read_text(encoding="utf-8", errors="replace"),
                           re.M)
```

**Preuve — 4. l'erreur est avalée** (`src/pont_hecras.py:556-559`) :

```python
    except Exception as e:
        print(f"   pente : deduction impossible ({type(e).__name__}: {e}) — "
              f"les valeurs en place sont conservees", flush=True)
        return {}
```

Le `NameError` est capturé et rendu sous une forme qui **ressemble à un
problème d'environnement**, pas à un défaut de code.

**Preuve — 5. les deux promesses rompues.**

`src/pont_hecras.py:455-457`, docstring de `_appliquer_pentes` :

> *Ordre de priorité : la colonne « Pente_m_par_m » du classeur, **puis la
> pente locale du fond** (profil en long, +/- 200 m, majorée de 20 %), puis
> rien — la valeur déjà présente dans le fichier reste alors en place.*

`calage_apports/noyau.py:1351-1353`, docstring de `preparer_classeur` :

> *une case vide reste possible — c'est le cas où le profil ne couvre pas
> l'apport, **et le calage déduira la pente comme avant**.*

**Coût actuel.** Le repli à trois échelons en compte **deux**. Un apport dont
la case est vide reçoit la pente déjà écrite dans l'unsteady — `0,01` (1 %)
pour une injection créée par le plugin (`PENTE_APPORT_DEFAUT`, `plugin.py`).
La pente commande la condition limite de profondeur normale de l'injection :
elle a un effet sur le débit calculé. Le journal dit
`pente de « A1 » : inchangee — ni saisie, ni deductible du profil`, ce qui est
exact et n'accuse rien.

**Correctif minimal.** `import re` en tête de `src/pont_hecras.py`.
**Un fichier, une ligne.**

**Risque du correctif.** *Il change un résultat numérique* — c'est l'inverse
d'un nettoyage. Un chemin mort depuis `fbe1dde` devient vivant, et les pentes
appliquées changeront sur tout apport à case vide. **À ne pas passer en lot 1
sans arbitrage** : il faut décider si les trois calages livrés doivent être
rejoués, ou si le correctif ne vaut que pour les suivants.

**Test prouvant l'équivalence.** Il n'y a pas d'équivalence à prouver, mais un
comportement à figer :
1. un banc qui appelle `_pentes_deduites` sur un projet factice et vérifie
   qu'aucun `NameError` ne remonte — il échoue sur le code d'avant ;
2. un garde-fou statique dans `faire_zip.py` : `compile()` chaque module de la
   chaîne et refuser tout `F821`. C'est ce qui aurait attrapé ce défaut au
   moment où il est entré.

**Question ouverte, à trancher par l'utilisateur** — je ne l'ai pas tranchée :
> Le journal d'un des trois calages porte-t-il la ligne
> `pente : deduction impossible (NameError: ...)` ? Si oui, la case était vide
> et les apports concernés ont tourné à 1 %. Si non, la colonne du classeur a
> toujours été remplie, et l'impact est **nul en production** — le défaut reste
> un P0 latent. **Non déterminable ici : les journaux sont sur le partage
> réseau.**

---

### P1 — dette bloquante

#### P1-2 · `style_classeur.py` est compté parmi les quinze bancs verts et ne contrôle rien — ✅ **corrigé au lot 3**

| | |
|---|---|
| **Sévérité** | P1 |
| **Fichier** | `src/style_classeur.py` (525 lignes), aucun bloc `__main__` |
| **Certitude** | **CERTAIN** |

**Preuve.**

```
$ grep -n "__main__" src/*.py calage_apports/*.py
src/calage.py:2349          src/controle_donnees.py:699    src/creer_template.py:221
src/criteres.py:717         src/elaguer_projet.py:589      src/faire_zip.py:185
src/geometrie.py:1032       src/livrables.py:730           src/pilote_hecras.py:2214
src/pont_hecras.py:2097     src/reconstruire_livrables.py:273
src/suivi.py:1065           calage_apports/noyau.py:2248
```

`style_classeur.py` n'y figure pas.

```
$ python style_classeur.py
[code retour 0]        ← aucune sortie
```

**Ce que la documentation en dit.** `STATUT.txt` § 1 : *« Treize suites
d'auto-tests, 0 echec : … style_classeur … »*. `LISEZMOI.md` : *« Les
auto-tests des autres modules embarqués (… **style_classeur.py** …) se lancent
de la même manière — les neuf modules de `chaine\` en portent un »*.
`CHECKPOINT.md` le lance dans la boucle des commandes utiles.

**Coût actuel.** 525 lignes qui mettent en forme **le classeur que
l'utilisateur remplit** — validations, listes déroulantes, aperçu des cibles —
sans un seul contrôle. Et un compte de bancs verts qui surestime la protection
réelle. Un banc qui passe parce qu'il ne fait rien est pire qu'un banc absent :
il est compté.

**Correctif minimal.** Un bloc `__main__` qui construit un classeur, applique
`mettre_en_forme()`, rouvre et vérifie ce qui compte : les trois feuilles
traitées sont rendues, la validation de `Cibles` existe, l'aperçu est écrit.
**Un fichier.**

**Risque.** Nul — ajout pur.

**Test.** Le banc lui-même. Il ne peut pas « échouer avant » : il n'existe pas.

---

#### P1-3 · Le premier outil qu'on lance décrit un projet d'il y a un mois — ✅ **corrigé le 6 septembre 2026**

**Corrigé, en deux fois.** Le contrôle annonce « fenêtre à 6 onglets » avec
leurs vrais noms, déduits des appels `addTab` de `plugin.py` et plus jamais
écrits à la main. Et la section « RESTE À ÉPROUVER » a perdu le bouton
« Installer… », mené à bout depuis QGIS le même jour.

| | |
|---|---|
| **Sévérité** | P1 (confiance dans l'outil) |
| **Fichier** | `src/verification_environnement.py:343`, `:448` env. |
| **Certitude** | **CERTAIN** |

**Preuve** — sortie brute de `python verification_environnement.py` :

```
[ OK ] fenetre a 4 onglets presente dans plugin.py
       ->  Modele HEC-RAS / Profil en long / Resultats et suivi / Validation
...
RESTE A EPROUVER :
   - une chaine de PLUSIEURS apports d'affilee, avec de vraies cibles :
     seul un apport unique a ete cale de bout en bout sur cas reel.
```

`plugin.py:1531` monte **six** onglets ; `STATUT.txt` § 1 recense **trois
calages complets, 24 apports**.

**Coût actuel.** Le README dit d'exécuter cet outil en premier. Un nouvel
arrivant y lit que la chaîne n'a jamais enchaîné deux apports.

**Correctif minimal.** Deux textes dans `verification_environnement.py` :
renommer le contrôle en ce qu'il vérifie réellement (sept symboles de
`plugin.py`), et remplacer la section « RESTE A EPROUVER ». **Un fichier.**

**Risque.** Nul — chaînes de caractères.

**Test.** Contrôle statique : la liste d'onglets citée est déduite des appels
`self.tabs.addTab` de `plugin.py`, plus jamais écrite à la main. C'est la même
règle que `commande_pip_hecras()` applique depuis aujourd'hui aux paquets.

---

#### P1-4 · `caler()` : 699 lignes, complexité cyclomatique **81** — 🟡 **engagé le 5 septembre 2026, et clos par une décision**

> **622 lignes aujourd'hui.** Les deux extractions que l'audit désignait sont
> faites ; la troisième est écartée sur mesure — quinze variables locales à
> passer. Le titre garde les 699 lignes du constat d'origine : c'est ce qui a été
> mesuré ce jour-là. Voir l'encadré en fin de section.

| | |
|---|---|
| **Sévérité** | P1 |
| **Fichier** | `src/calage.py:912-1610` |
| **Certitude** | **CERTAIN** (mesure) |

**Preuve.**

```
$ radon cc -s -n D src calage_apports
src/calage.py
    F 912:0 caler - F (81)
    F 2005:0 produire_livrables_finaux - D (30)
...
551 blocks analyzed. Average complexity: B (5.42)
```

**Le reste du dépôt est sain** : moyenne B, et le second pire bloc est à 39.
La dette est **concentrée en un point**.

**Coût actuel.** Toute correction dans la boucle demande de tenir 699 lignes en
tête. C'est là que sont nés les incidents des 03/08 et 07/08 (Δt confondu avec
φ, invariant 12), et c'est la fonction que l'idée V2 « calage simultané »
devrait réécrire.

**Correctif minimal — et je ne le recommande pas maintenant.** Extraire les
**étapes déjà nommées dans les commentaires** (« étape 7 », vérification
globale finale, journalisation d'itération) en fonctions privées, sans changer
une seule opération flottante ni leur ordre. Cela réduit `caler()` sans rien
déplacer d'autre.

**Risque.** **Élevé.** 120 contrôles couvrent `calage.py`, mais aucun ne rejoue
un calage réel : il n'y a pas de jeu de référence dans le dépôt (§ A.4). Un
refactor ici sans test de caractérisation numérique est un pari.

**Test à écrire d'abord** — voir § 6.

> #### ✅ Engagé le 5 septembre 2026 — deux extractions sur trois
>
> Le test de caractérisation existant, l'objection ci-dessus est levée. Deux
> des trois étapes nommées sont sorties, en **déplacement pur** — aucune
> opération flottante touchée, aucun ordre changé — avec le banc relancé et
> la caractérisation `identique` après chacune :
>
> | étape | fonction | commit |
> |---|---|---|
> | étape 7 | `_signaler_coherence_amont()` | `9efddcc` |
> | vérification globale finale | `_verifier_globalement()` | `43db3f1` |
>
> **`caler()` : 699 → 622 lignes.**
>
> **La troisième — « journalisation d'itération » — n'est PAS extraite, et
> c'est une décision mesurée, pas un reste.** Le bloc (`calage.py:1312-1333`)
> lit **quinze variables locales** — `essais`, `diag`, `config`, `dire`,
> `suivi`, `i`, `temps_cible`, `debit_cible`, `temps_residuel`, `residuel`,
> `decalage_zero`, `temps_calcule`, `debit_calcule`, `courant`,
> `volume_initial` — et doit rendre `atteint`. Une fonction à quinze
> paramètres se lit plus mal que le bloc en place : l'extraction irait contre
> le but qu'elle poursuit.
>
> Ce que ce constat déplace : le poids de `caler()` ne tient pas à des étapes
> mal rangées — les deux qui l'étaient sont sorties sans peine — mais à
> **l'étendue de l'état que porte le corps de la boucle par apport**. Le
> réduire demande de regrouper cet état, donc un changement de conception, et
> non plus un déplacement. C'est le même chantier que l'idée V2 « calage
> simultané » (`docs/idees_V2_plugin.md` § 1), qui réécrit cette boucle de
> toute façon. **À traiter là, ou pas du tout** — pas en troisième extraction.

---

#### P1-5 · `_sections_derivees` fait disparaître une section de l'alerte d'étape 7 — ✅ **corrigé au lot 5, le 5 septembre 2026**

| | |
|---|---|
| **Sévérité** | P1 |
| **Fichier** | `src/calage.py:1626-1630` |
| **Certitude** | **CERTAIN** |

**Corrigé.** `_sections_derivees` rend désormais `(derives, illisibles)` : la
section qu'on ne sait pas lire est collectée avec la raison de son échec, et
l'étape 7 la **nomme** au journal — « n'ont PAS pu être relues, leur dérive
n'a donc pas été vérifiée ici ». Aucun blocage, comme prévu. Quatre contrôles
au banc de `calage.py` ; le test de caractérisation reste `identique`, le
correctif ne déplace aucune trajectoire.

**Preuve, verbatim :**

```python
    for section, (t_c, q_c), fenetre in zip(sections, cibles, fenetres):
        try:
            t_s, q_s = modele.lire_section(section)
        except Exception:
            continue
```

**Coût actuel.** Une section qu'on ne sait pas lire est **retirée de la liste
des dérives** sans un mot. L'appelant (`calage.py:1506-1510`) conclut alors
« aucune section amont n'a dérivé », alors qu'il n'a pas pu regarder.

**Ce que ce constat n'est PAS.** Le **verdict final** n'est pas touché : la
vérification globale (`calage.py:1524-1554`) appelle `modele.lire_section`
**sans `try`**, et une lecture impossible y remonte. Vérifié.

**Correctif minimal.** Collecter les sections illisibles et les rapporter dans
le journal — une alerte, jamais un blocage. **Un fichier.**

**Risque.** Faible. Le comportement de la boucle ne change pas ; seul le
journal s'allonge.

**Test.** Un `Modele` factice dont `lire_section` lève sur une section :
vérifier que la section est nommée dans la sortie. Échoue sur le code d'avant.

---

#### P1-6 · Un contrôle de banc dont la condition est toujours vraie — ✅ **corrigé au lot 1**

| | |
|---|---|
| **Sévérité** | P1 (qualité de banc) |
| **Fichier** | `calage_apports/noyau.py:2583` |
| **Certitude** | **CERTAIN** |

**Preuve.**

```
$ vulture src calage_apports --min-confidence 100
calage_apports/noyau.py:2583: unreachable 'else' expression (100% confidence)
```

Verbatim :

```python
        print(f"   [{'OK' if _donnees / 'Scripts' / 'python.exe' or True else ''}]"
              f" le dossier de donnees est hors du plugin  ->  "
              f"{dossier_donnees_plugin()}")
        assert DOSSIER_EMBARQUE.parent not in dossier_donnees_plugin().parents
```

`<Path> or True` est **toujours vrai**. La ligne affiche `[OK]` quoi qu'il
arrive. Le contrôle réel est l'`assert` en dessous.

**Coût actuel.** Un `[OK]` décoratif dans la sortie d'un banc. Il ne masque
rien ici — l'`assert` fait le travail — mais il compte pour un contrôle dans
un décompte qui sert de référence.

**Correctif minimal.** Faire porter la condition du `print` sur le prédicat de
l'`assert`. **Un fichier, deux lignes.**

**Risque.** Nul.

**Test.** Le banc lui-même, dont un contrôle de plus devient sincère.

---

#### P1-7 · Lancer le banc de `creer_template.py` salit un fichier suivi par git — ✅ **corrigé au lot 3**

| | |
|---|---|
| **Sévérité** | P1 (hygiène) |
| **Fichier** | `src/creer_template.py:221-222` |
| **Certitude** | **CERTAIN** — constaté trois fois pendant cette session |

**Preuve.** `if __name__ == "__main__": chemin = construire()` réécrit
`template_donnees_calage.xlsx`, qui est **suivi par git**. Après chaque passage
de la boucle de bancs :

```
$ git status --short
 M template_donnees_calage.xlsx
```

**Coût actuel.** Il faut un `git checkout --` après chaque exécution complète
des bancs, sinon un octet de mise en forme part dans un commit sans rapport.

**Correctif minimal.** Écrire dans un dossier temporaire, et n'écraser le
fichier livré que sur une option explicite (`--publier`). **Un fichier.**

**Risque.** Faible. Il faut vérifier que `faire_zip.py` et le README ne
comptent pas sur l'effet de bord.

**Test.** Lancer le banc, puis `git diff --exit-code template_donnees_calage.xlsx`.

---

### P2 — nettoyage sûr

#### P2-8 · Quatre constats `ruff` — ✅ **traités au lot 1**

Sortie de l'audit, avant le lot :

```
$ ruff check --select F401,F841 --no-cache --output-format concise src calage_apports
src/controle_donnees.py:649:9  F841 Local variable `maille_globale` is assigned to but never used
src/elaguer_projet.py:467:5    F841 Local variable `prj` is assigned to but never used
src/pont_hecras.py:269:22      F401 `pandas` imported but unused
src/verification_environnement.py:232:12  F401 `ras_commander` imported but unused
```

| item | certitude | attention |
|---|---|---|
| `maille_globale` (×2, lignes 643 **et** 649) | **variable morte, ligne VIVANTE** | voir l'encadré ci-dessous — **cet audit s'était trompé** |
| `prj` | CERTAIN | — |
| `pandas` dans `pont_hecras.py:269` | CERTAIN | import local, sans effet de bord |
| `ras_commander` dans `verification_environnement.py:232` | **USAGE INDIRECT** | l'import **est le test** : il prouve que le module se charge avant que `md.version()` ne soit lu. **Ne pas supprimer** — ajouter `# noqa: F401` avec la raison |

> ### Correction apportée au lot 1 — `maille_globale` n'était pas une suppression sûre
>
> L'affectation est morte ; **l'appel ne l'est pas**. `geo.taille_maille(chemin,
> zone)` est une **sonde** : son échec fait tomber dans le `except`, qui pose
> `tolerance = None`. Or `tolerance` est ensuite confiée à
> `geo.controler_contre_maillage`, qui l'appelle **par géométrie et sans
> protection** — `admis = tolerance_m(g) if callable(tolerance_m) else
> tolerance_m` (`geometrie.py:525`). Supprimer la ligne aurait donc remplacé le
> repli prévu (`None` → le contrôle *rapporte* la distance) par une exception
> remontée au milieu du contrôle.
>
> **Ce que le lot a fait** : garder l'appel, retirer le nom. `ruff` est
> satisfait, le comportement est identique.
>
> **Ce que ça dit de cet audit** : `ruff` avait raison sur la *variable* et cet
> audit a eu tort d'en conclure une suppression à risque nul. C'est exactement
> ce que la question obligatoire — *« cette complexité répond-elle à une
> contrainte réelle ? »* — sert à attraper, et elle ne l'a été qu'en relisant
> le site avant d'éditer.

**Correctif** : 2 suppressions, 1 sonde débaptisée, 1 `noqa`. Les bancs des
quatre modules le prouvent.

#### P2-9 · `ModeleResiduelDecale` — classe définie, jamais instanciée — ✅ **retirée le 6 septembre 2026**

**Tranché : retirée.** Du code que rien n'appelle vieillit sans que rien ne
l'éprouve, et donne à croire qu'un cas est couvert. Elle datait d'une époque
où ce cas s'éprouvait en faisant tourner un calage complet ; les deux
contrôles qui la suivaient ont depuis été ramenés à ce qu'ils vérifient
vraiment — `decalage_minimisant_ecart` et `ecart_a_la_cible`, deux fonctions
**pures**, sans modèle ni boucle. Un commentaire garde la trace ; git garde
le code. Test de caractérisation resté `identique`.

```
$ grep -rn "ModeleResiduelDecale" --include=*.py .
./src/calage.py:2800:    class ModeleResiduelDecale(Modele):
```

Une seule occurrence : la définition. **CERTAIN** au sens du cahier des
charges. Mais elle vit **dans le bloc `__main__`**, où elle documente un modèle
d'essai alternatif. **Je ne la classe pas en lot 1** et je pose la question
plutôt que de trancher (§ 7).

#### P2-10 · Vingt-et-un `except` larges strictement muets

Mesure (corps réduit à `pass` / `continue` / `return` d'un littéral, sans
message ni relance) :

```
except larges (bare / Exception / BaseException) : 122
dont strictement muets                           :  21
```

Répartition : `pont_hecras` 4, `pilote_hecras` 5, `calage` 4, `plugin` 3,
`noyau` 3, `style_classeur` 1, `verification_environnement` 1.

**Ce n'est pas un lot.** La plupart sont des garde-fous délibérés
(`_sans_interrompre`, lecture d'onglets d'un classeur illisible). Le seul qui
compte est **P1-5**, déjà isolé. Les vingt autres sont à revoir **un par un, à
l'occasion**, jamais en balayage.

#### P2-11 · `test_plugin_qgis.py:182` — faux positif de `vulture` — ✅ **clos le 6 septembre 2026**

La signature de `getItem` reproduit `QInputDialog.getItem` et ne se choisit
pas : quatre de ses six arguments ne servent à rien au mannequin, mais les
retirer casserait l'appel du plugin, qui les passe en position. Ils sont
consommés explicitement — l'oubli est dit volontaire, et l'avertissement ne
se re-instruit plus chaque année.

```
vulture: src/test_plugin_qgis.py:182: unused variable 'editable' (100% confidence)
```

```python
    def getItem(self, parent, titre, libelle, choix, i, editable):  # noqa: N802
```

C'est la **signature de `QInputDialog.getItem`**, rejouée par une doublure.
Le paramètre est positionnel : le retirer casse l'appel réel.
**NE PAS SUPPRIMER.** Vulture se trompe malgré ses 100 %.

### P3 — cosmétique

```
$ ruff check --select E,F,W,B,SIM,C4,ARG,RET,PIE,PERF ... | comptage par règle
  86 B905   zip() sans strict=          -> NE PAS CORRIGER (voir § 4)
  34 ARG005 argument de lambda inutilisé
  27 E741   nom ambigu (`l`)
  24 ARG002 argument de méthode inutilisé  -> souvent l'API Qt
  17 E702   deux instructions sur une ligne
  16 PERF203 try/except dans une boucle
   9 F541   f-string sans champ
```

`ARG002`/`ARG005` recouvrent largement des signatures imposées (Qt, doublures
de test). `E741`, `E702`, `F541` sont sûrs mais **sans gain** : 53 lignes
touchées pour zéro concept en moins. **Non recommandés.**

---

## 4. Ce qu'il ne faut PAS simplifier, et pourquoi

| Cible apparente | Verdict | Preuve |
|---|---|---|
| **`zip(...)` sans `strict=`, 86 fois** | **Interdit** | `noyau.PYTHON_MINIMUM = (3, 9)`. `strict=` est apparu en **3.10**. L'ajouter casse le plugin sur un poste au Python minimal annoncé. |
| **Les 3 copies de la politique d'encodage** (`pilote_hecras._lire_texte`, `elaguer_projet._lire_texte`, `noyau._lire_texte_hecras`) | **Interdit** | Seul cluster que `pylint` trouve à 6 lignes. C'est l'**invariant 3**, écrit : *« ils ne peuvent pas partager de code. Toute correction doit être reportée aux trois. »* |
| **Les 2 cycles d'imports** | **Interdit** | Tous les arcs sont des imports **locaux à une fonction** (§ A.2). C'est la parade à `import h5py` sous QGIS. Les « résoudre » réintroduirait le défaut que `pont_hecras.py` existe pour éviter. |
| **Les 7 copies du helper `_verifier(libelle, condition, detail)`** | **À laisser** | Un module partagé devrait entrer dans `FICHIERS_CHAINE` et dans l'archive, pour ~8 lignes × 7. Chaque module doit rester lançable seul. Trois lignes semblables valent mieux qu'une abstraction prématurée. |
| **`classFactory`, `initGui`, `unload`, `paintEvent` ×3** | **Interdit** | Appelés par QGIS/Qt par leur nom. `vulture` les signale à 60 %. **Invariant 1.** |
| **`_raccorder()` appelé nu dans `noyau.py`** | **Interdit** | **Invariant 2** : c'est lui qui insère la chaîne dans `sys.path`. |
| **`editable` dans `test_plugin_qgis.py:182`** | **Interdit** | Signature `QInputDialog.getItem` (P2-11). |
| **`import ras_commander` dans `verification_environnement.py:232`** | **Interdit** | L'import **est** le contrôle (P2-8). |
| **Les parseurs HEC-RAS** (`pilote_hecras.py`, 3 248 lignes) | **Non regardé, exprès** | Largeurs fixes et duplications entre versions de format : le cahier des charges l'interdit sans preuve d'identité des formats. Je n'ai pas cette preuve. |
| **Toute formule hydraulique / tout ordre d'opérations flottantes** | **Interdit** | Consigne. Aucun constat de cet audit n'y touche. |
| **`Configuration` (15 champs)** | **Rien à retirer** | Vérifié : les 15 sont lus. `nb_max_essais`, `marge_duree_h`, `controle_amont` ne le sont qu'une fois — une fois, c'est utilisé. |

**Dépendances.** `deptry` ne trouve **aucune dépendance morte** et **rien à
ajouter** (le seul `DEP002`, `python-docx`, est un artefact : le module
s'importe sous le nom `docx`, listé en `DEP001`). Le correctif P0-1 est
`import re` — bibliothèque standard, **aucune dépendance nouvelle**.

---

## 5. Top 10 par gain ÷ risque

| # | Constat | Gain | Risque | Ratio |
|---|---|---|---|---|
| 1 | **P0-1** `import re` (le correctif) | **Très fort** — restaure un échelon de repli | Faible *techniquement* | ★★★★★ |
| 2 | P2-8 `ruff` : 3 suppressions + 1 `noqa` | Faible | Nul | ★★★★★ |
| 3 | P1-6 le contrôle toujours vrai | Moyen — un banc sincère | Nul | ★★★★★ |
| 4 | P1-3 les deux textes périmés | Moyen — confiance dans l'outil d'accueil | Nul | ★★★★☆ |
| 5 | P1-7 le banc qui salit git | Moyen | Faible | ★★★★☆ |
| 6 | P1-2 le banc de `style_classeur` | Fort — 525 lignes découvertes | Nul (ajout) | ★★★★☆ |
| 7 | P1-5 les sections illisibles nommées | Moyen | Faible | ★★★☆☆ |
| 8 | Garde-fou `F821` dans `faire_zip.py` | **Fort** — ferme la classe P0-1 | Faible | ★★★☆☆ |
| 9 | P2-9 `ModeleResiduelDecale` | Faible | Faible — **question posée** | ★★☆☆☆ |
| 10 | P1-4 découpe de `caler()` | Fort à long terme | **Élevé** — pas de jeu de référence | ★☆☆☆☆ |

> **Le n° 1 est premier par le gain, pas par la sécurité.** C'est le seul de la
> liste qui change un résultat numérique, et il ne doit pas partir sans votre
> arbitrage (§ 7).

---

## 6. Tests manquants à écrire avant les lots risqués

1. ✅ **ÉCRIT le 5 septembre 2026** — Test de caractérisation numérique de
   `caler()`, dans le banc de `calage.py`, contre
   `src/reference_calage_fictif.json` (36 ko, versionné). Il réutilise le
   calage que le banc mène déjà : **aucun calcul de plus**.
   Ce qu'il fige : `nb_calculs`, `conforme`, le motif, et par apport le nombre
   d'essais, le **hydrogramme injecté en entier** (400 points) et tous les
   nombres du `Diagnostic`. Tolérances **`rtol=1e-9`** sur les débits,
   **`atol=1e-6 h`** sur les décalages et les bornes de fenêtre.
   Ce qu'il ne fige pas, et pourquoi : ni les durées (horloge), ni
   l'historique par essai (il porte des mesures de temps).
   **Mesuré dans les deux sens** : un apport déplacé de **0,1 %** — que les
   120 contrôles de bande laissent tous passer — produit **1 215 écarts** et
   fait échouer le banc ; un Δt décalé de `1e-7 h` passe, de `1e-3 h` échoue.
   La référence porte le socle qui l'a produite (Python, numpy, système) : un
   écart au dernier chiffre y est rapporté comme tel, et non comme une
   régression. Quand le changement est **voulu** :
   `python calage.py --figer-reference`, puis relire le diff.
2. **Test de non-régression des pentes** (avant P0-1) : `_pentes_deduites` sur
   un projet factice, sans `NameError`, avec la pente attendue.
3. **Garde-fou statique dans `faire_zip.py`** : refuser l'archive si un module
   de la chaîne porte un `F821`. C'est le test qui aurait empêché P0-1.
4. **Banc de `style_classeur.py`** (P1-2) — préalable à toute retouche de la
   mise en forme du classeur.
5. **Contrôle de cohérence documentaire** : la liste d'onglets citée par
   `verification_environnement.py` déduite de `plugin.py`, sur le modèle de
   `commande_pip_hecras()`.

---

## 7. PHASE C — Plan par lots

> **Aucun lot n'est engagé.** J'attends `GO LOT n`.

### Lot 1 — code mort CERTAIN et bancs sincères — ✅ **FAIT**

**Invariant de comportement** : aucune sortie du calage ne change. Aucun
fichier livrable, aucun nombre.

| Fichier | Action |
|---|---|
| `src/controle_donnees.py` | **retirer le NOM, garder l'APPEL** — c'est une sonde, voir P2-8 |
| `src/elaguer_projet.py` | retirer `prj` (467) |
| `src/pont_hecras.py` | retirer `import pandas` (269) |
| `src/verification_environnement.py` | `# noqa: F401` motivé sur `ras_commander` (232) |
| `calage_apports/noyau.py` | faire porter le `print` de 2583 sur le prédicat de l'`assert` |

**Vérification** : `ruff check --select F401,F841 src calage_apports` rend 0 ;
les bancs de `controle_donnees`, `elaguer_projet`, `noyau`,
`verification_environnement` repassent.
**Terminé quand** : `ruff` est vert et les compteurs de bancs sont inchangés
(sauf `noyau`, dont un contrôle devient sincère).

> **Résultat, 5 septembre 2026.** `ruff --select F401,F841` : *All checks
> passed*. `vulture --min-confidence 100` ne rend plus que
> `test_plugin_qgis.py:182`, qu'on garde exprès (P2-11). Compteurs **identiques
> à ceux du § A.4** : `calage` 120, `criteres` 66, `suivi` 48,
> `verification_environnement` 39, `noyau` 37, `geometrie` 26, `livrables` 16,
> `controle_donnees` 6. `faire_zip` : « archive conforme ».
>
> `elaguer_projet` et `pont_hecras` **ne s'exécutent pas ici** (`h5py`). Vérifiés
> statiquement, par portée : plus aucune fonction n'écrit `prj` sans le lire, et
> toute fonction de `pont_hecras` qui utilise `pd` l'importe chez elle. `F821`
> rend **les deux mêmes** constats qu'avant le lot — le P0 du § 3, intact : aucun
> nom indéfini n'a été introduit.

### Lot 2 — dérive documentaire — ✅ **FAIT**

`src/verification_environnement.py` (deux textes), `STATUT.txt` § 6 (retirer le
point clos), `CHECKPOINT.md`. **4 fichiers.**
**Vérification** : `python verification_environnement.py`, lecture à l'œil.
**Terminé quand** : plus aucun texte n'affirme « un seul apport calé », ni
« 4 onglets ».

> **Résultat, 5 septembre 2026.** `grep` sur tout le dépôt : plus aucune
> occurrence, hors ce document. Le contrôle rend désormais
> `[ OK ] fenetre a 6 onglets presente dans plugin.py -> 1. Modèle / 2. Profil
> en long / 3. Résultats / 4. Lancer / 5. Suivi / Aide`, **titres lus dans
> `plugin.py`** et non recopiés.

### Lot 3 — les bancs qui manquent — ✅ **FAIT**

`src/style_classeur.py` (banc neuf), `src/creer_template.py` (sortie
temporaire), `src/faire_zip.py` (garde-fou `F821`). **3 fichiers.**
**Vérification** : les trois bancs, puis `git status --short` **vide** après
une boucle complète.
**Terminé quand** : `style_classeur.py` rend des `[OK]`, et le garde-fou
`F821` **échoue** si l'on retire `import re` de `pont_hecras.py`.

> **Résultat, 5 septembre 2026.** `style_classeur.py` rend **13 contrôles**.
> `git status` est **vide** après une boucle complète de bancs. Le garde-fou
> (`faire_zip.noms_jamais_lies`) rend **code retour 1** quand on retire la
> ligne, **0** quand on la remet — mesuré dans les deux sens. Il est de plus
> **éprouvé par le banc adverse**, qui injecte désormais la faute en troisième
> position et vérifie qu'elle est refusée.
>
> **Sa conception, et pourquoi elle est sûre** : il rassemble ce qu'un fichier
> lie *n'importe où*, puis signale ce qui est lu sans y figurer. Il est donc
> **délibérément aveugle aux portées** — il ne voit pas un nom lié dans une
> fonction et lu dans une autre. En échange il ne rend **aucun faux positif**,
> mesuré sur les 25 800 lignes du projet : c'est la seule façon qu'un garde-fou
> d'archive soit cru. Un fichier portant `from x import *` le fait se taire
> plutôt qu'affirmer.
>
> **Le lot 3 a emporté le lot 4 avec lui** : le garde-fou refusait l'archive
> tant que `import re` manquait, et arbitrer ce refus aurait été le désarmer.
> La ligne est posée. Ce qui reste est la question des livrables (§ 8).

### Lot 4 — P0-1 — ✅ **fait avec le lot 3**

`import re` dans `src/pont_hecras.py`, plus le test n° 2 du § 6.
**1 fichier + 1 banc.**
**Préalable, non négociable** : la réponse à la question du § 8. Le lot 3 passe
avant, pour que le garde-fou existe d'abord.
**Terminé quand** : le banc échoue sur le code d'avant, passe après, et la
décision sur les trois calages livrés est écrite dans `STATUT.txt`.

### Lot 5 — P1-5 puis, seulement ensuite, P1-4

`_sections_derivees` d'abord (petit, local). **`caler()` ne se touche pas avant
le test de caractérisation du § 6 n° 1** — qui **existe depuis le 5 septembre
2026**. Le préalable est donc levé : le filet est tendu.

**Lot 5 mené le 5 septembre 2026.** P1-5 corrigé ; P1-4 engagé et **clos par
une décision, pas par un abandon** :

- `_sections_derivees` rend `(derives, illisibles)`, l'étape 7 nomme ce
  qu'elle n'a pas pu relire (`bc60fbb`) ;
- `_signaler_coherence_amont()` et `_verifier_globalement()` sortent de
  `caler()`, en déplacement pur (`9efddcc`, `43db3f1`) — **699 → 622 lignes** ;
- la troisième extraction que l'audit envisageait est **écartée sur mesure** :
  quinze variables locales à passer. Voir le constat P1-4.

**Ce qui reste de `caler()` ne relève plus de l'extraction** mais de l'étendue
de l'état porté par la boucle par apport — c'est-à-dire du chantier « calage
simultané » (`docs/idees_V2_plugin.md` § 1), qui réécrit cette boucle.

---

## 8. La question qui commandait le lot 4 — ✅ **tranchée le 5 septembre 2026**

> **Les journaux des trois calages livrés portent-ils la ligne
> `pente : deduction impossible (NameError: name 're' is not defined)` ?**
>
> **Non.** Relevé par l'utilisateur sur les journaux des trois calages.

**Ce que cela règle.** La colonne `Pente_m_par_m` a toujours été pré-remplie
par la composition : le **premier** échelon du repli a suffi à chaque fois, et
le second — celui qui était cassé — n'a jamais été emprunté. **Aucun livrable
n'est à reprendre** ; les pentes appliquées aux 24 apports sont bien les pentes
locales.

**Ce que cela ne règle pas.** Le défaut était **latent**, pas inoffensif : il
aurait mordu au premier apport dont la case reste vide — cas que
`noyau.preparer_classeur` prévoit explicitement (*« c'est le cas où le profil
ne couvre pas l'apport »*). Il est corrigé.

**Et c'est l'argument du garde-fou.** Un import oublié sous un `except` large
peut dormir des semaines sans qu'aucun calage ne le révèle : ni l'import du
module, ni sa compilation, ni trois calages complets de 77 heures cumulées ne
l'ont fait sortir. Seul un contrôle qui lit le code le voyait.

> ### Ce que le lot 3 a tranché, et ce qu'il n'a pas tranché
>
> **Deux questions étaient confondues sous « lot 4 ».** Ajouter `import re` ne
> dépend pas des journaux : la ligne ne change rien à ce qui est déjà produit,
> elle rend au code ce que deux docstrings promettent. **Elle est posée** — et
> le garde-fou qui l'aurait attrapée aussi.
>
> **Ce qui reste ouvert est la seule vraie question** : les trois calages
> livrés ont-ils emprunté ce repli ? Elle décide du sort de leurs livrables,
> pas de la correction du code.

---

## 9. Ce que je n'ai PAS regardé

- **`src/pilote_hecras.py` (3 248 lignes)** et les parseurs HEC-RAS
  (`.prj .pXX .gXX .uXX .hdf`), au-delà de l'outillage. Consigne du cahier des
  charges : largeurs fixes et duplications de format sont volontaires, et je
  n'ai aucun modèle réel pour prouver le contraire.
- **Toute formule hydraulique ou numérique.** Aucun constat n'y touche.
- **`src/test_plugin_qgis.py` (1 638 lignes)** — ce qu'il couvre réellement.
  Il ne s'exécute que sous le Python de QGIS, avec une copie de modèle.
- **`src/figures_note/`** (`contenu.py` 1 015 lignes, `construire_docx.py`) —
  reconstruction de la note. Hors chaîne de calage, non distribué.
- **Le comportement d'exécution du plugin** : ni PyQt, ni QGIS ici. Tout ce
  qui concerne `plugin.py` est statique.
- **Les performances** (temps de calcul, mémoire) : hors périmètre demandé.
- **La note méthodologique** (`.docx`, `.pdf`) et sa cohérence avec le code.
- **`_arquivo/`**, hors du chemin de lecture normal.

---

*Aucun fichier source n'a été modifié par cet audit.*
