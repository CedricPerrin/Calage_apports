# Découpage du dialogue du plugin — matrice des attributs — 10 novembre 2026

Phase 1 du chantier « une classe par étape ». Mesuré sur `main` (58fefa1) :
`calage_apports/plugin.py` 7 823 lignes, dont `DialogueParametrage` 5 619
lignes, 136 `def` (135 noms : `classeur` est une propriété et son setter).
Les numéros de ligne de ce document sont ceux de 58fefa1.

Méthode : analyse statique (`ast`) par un script jetable, hors du dépôt. Pour
chaque `self.x` : ses écritures (affectation, `setattr(self, "x")`), ses
lectures (y compris `getattr` / `hasattr` à nom constant, lambdas et
fonctions imbriquées). Un `self.m` qui désigne une méthode compte comme un
appel, ce qui couvre les connexions de signaux. Dans le banc
`src/test_plugin_qgis.py`, on compte les références `.<nom>` (texte brut : un
homonyme d'un autre objet, `.classeur`, `.onglets`, `.poste`, `.bande`, peut
gonfler le compte).

Résultat brut : **132 attributs écrits** par la classe, plus 16 membres de
Qt lus sans jamais être écrits (`accept`, `findChildren`, `resize`…), écartés.
**94 attributs sont lus par le banc par leur nom.**

---

## 1. Règle de rattachement

1. **Constructeurs** de l'étape X : `_onglet_X`, puis, de proche en proche,
   les `_groupe_*`, `_champ_*` et `_bouton_*` qu'il appelle.
2. **Widget de X** : attribut créé (première écriture) par un constructeur de
   X. Tout autre attribut est un **état** (créé dans `__init__` ou en cours de
   vie).
3. Une méthode relève de X si **les widgets qu'elle touche** sont tous de X.
   S'ils viennent de plusieurs étapes : **commun**.
4. Une méthode qui ne touche aucun widget prend l'étape de ses appelants
   s'ils n'en ont qu'une. La navigation ne compte pas comme appelant :
   elle deviendra `page.methode()`.
5. Commun d'office : `__init__`, navigation (`_aller_etape`,
   `_changer_onglet`, `_maj_navigation`, `keyPressEvent`, `show/hideEvent`,
   `eventFilter`, `changeEvent`), fil conducteur (`_maj_fil`), bandeau et
   bande (`_bandeau`, `_bande`), style (`_actualiser_style`,
   `_nommer_champs`), `_signaler`.

Pourquoi les widgets plutôt que le graphe d'appels seul : la navigation et
les autres étapes appellent la page (`_rafraichir_suivi` est appelée par
`_changer_onglet`, `showEvent` et `_oublier_dossier_suivi`). Ces appels
entrants deviendront des appels publics de la page ; ils ne l'empêchent pas
d'exister. Ce qui l'en empêche, c'est ce qu'elle TOUCHE.

## 2. Bilan par étape

| Étape | Méthodes | Lignes | Attributs propres (lus par le banc) | Partagés (dont états) | Méthodes appelées par le banc | Méthodes du dialogue appelées | Globaux de `plugin.py` requis | Doublures du banc nommées |
|---|---:|---:|---|---|---:|---:|---:|---|
| Modèle | 27 | 929 | 17 (7) | 20 (11) | 14 | 10 | 22 | `QFileDialog`, `QMessageBox` |
| Paramètres | 22 | 973 | 14 (8) | 14 (6) | 11 | 13 | 17 | `QFileDialog`, `QMessageBox` |
| Lancer | 16 | 646 | 9 (5) | 14 (8) | 4 | 12 | 14 | `QMessageBox` |
| **Suivi** | **17** | **774** | **24 (15)** | **6 (5)** | **5** | **4** | 28 | **aucune** |
| Aide | 16 | 460 | 8 (5) | 4 (4) | 3 | 2 | 14 | `QFileDialog`, `QInputDialog`, `QMessageBox` |
| commun | 37 | 1 517 | 9 (4) | 49 (25) | 14 | — | 29 | `QMessageBox` |

« Doublures » : le banc remplace `mod_plugin.QMessageBox`, `QFileDialog` et
`QInputDialog` au niveau du MODULE `plugin` (`test_plugin_qgis.py:401-403`).
Une page logée dans un autre module qui les nommerait directement ouvrirait
les vraies boîtes, hors écran, et bloquerait le banc.

### 2.1 Méthodes par étape

| Étape | Méthodes |
|---|---|
| Modèle | `_onglet_modele`, `_groupe_axe`, `_groupe_couches_existantes`, `_bouton_defauts`, `_changer_plan`, `_charger_couches_modele`, `_charger_projet_hecras`, `_parcourir_projet_hecras`, `_phrase_version`, `_maj_mode_override`, `_maj_resume_fichiers`, `_remplir_fenetre_depuis_plan`, `_selectionner_par_numero`, `fenetre_saisie`, `_fenetre_modifiee`, `_resume_fenetre`, `_geometrie_effective`, `_unsteady_effective`, `_dossier_projet`, `_ecrire_dans_geometrie`, `_maj_alerte_couches`, `_plans_au_titre_final`, `_parametres_du_paquet`, `_ecarts_avec_le_paquet`, `_montrer`, `_defauts_a_l_ecran`, `_revenir_aux_defauts` |
| Paramètres | `_onglet_objectifs`, `_groupe_precision`, `_groupe_classeur`, `_groupe_ce_que_portent_les_cibles`, `_groupe_dossier_sortie`, `_champ_prefixe_scenario`, `_bouton_controle_parametrage`, `_maj_bouton_controle`, `_maj_groupe_classeur`, `_maj_resume_cibles`, `_importer_hydrogrammes`, `_ouvrir_classeur`, `_composer_et_controler`, `_classeur_neuf_annonce`, `_dire_titres_prefixe`, `_noms_injections`, `_titre_etape`, `_parcourir_dossier_sortie`, `_proposer_dossier_sortie`, `_dossier_suivi`, `_dossier_suivi_de_l_onglet_3`, `classeur` |
| Lancer | `_onglet_validation`, `_groupe_copies_de_travail`, `_groupe_menage`, `_groupe_configuration`, `_groupe_calcul`, `_dire_elagage`, `_coeurs_demandes`, `_premier_apport`, `_remplir_premier_apport`, `_dire_premier_apport`, `_dire_reprise`, `_confirmer_reprise`, `_maj_onglet_validation`, `_maj_onglet_validation_depuis_classeur`, `_maj_coherence`, `_maj_temoins` |
| Suivi | `_onglet_suivi`, `_rafraichir_suivi`, `_peindre_suivi`, `_peindre_journal`, `_peindre_alertes`, `_lignes_alerte`, `_lire_journal`, `_journal_du_calage`, `_banniere`, `_suivi_precedent`, `_afficher_bilan_masse`, `_remplir_table_suivi`, `_ouvrir_dossier_suivi`, `_ouvrir_figure_suivi`, `_detail_desaccord_suivi`, `_origine_dossier_suivi`, `_oublier_dossier_suivi` |
| Aide | `_onglet_aide`, `_survol_aide`, `_ouvrir_lexique`, `_diagnostic`, `_maj_parametres_poste`, `_choisir_chaine`, `_choisir_interpreteur`, `_choisir_python_recherche`, `_proposer_python`, `_installer_interpreteur`, `_reprendre_installation`, `_suivre_installation`, `_phase_installation`, `_detacher_installation`, `_fin_recherche_python`, `_fin_installation` |
| commun | navigation et fil (voir § 1, règle 5) ; défauts et témoins (`_temoin`, `_avec_temoin`, `_marque_defaut`, `_texte_defaut`, `_maj_defauts`, `_memes_valeurs`, `_valeurs_de_la_fenetre`, `_parametres_fenetre`) ; résumé (`_maj_resume`, `_composer_resume`, `_dire_coeurs`, `_etapes_preparation`, `_etapes_avant_controle`) ; composition (`_composer_et_controler_interne`, 211 l., `_rendre_compte_du_controle`, `_proposer_prolongation`) ; lancement (`_lancer_calage`, 168 l., `_accepter_plan_final`, `_calage_en_cours`, `_confirmer_malgre_calage`, `_installation_occupe`, `_relire_cibles_si_modifiees`) |

Trois rattachements surprennent et sont justes au sens de la règle :
`_ecrire_dans_geometrie` (Modèle : il ne lit que des widgets du Modèle, même
si c'est la composition qui l'appelle) ; `_dossier_suivi` (Paramètres : il lit
le dossier de sortie, et c'est le Suivi et le Lancer qui l'appellent) ;
`_oublier_dossier_suivi` (Suivi : bouton du groupe « dossier de sortie », mais
il ne touche que la bannière du Suivi).

## 3. Attributs partagés, par étape

Un **widget** partagé (créé par un constructeur, jamais réaffecté) se
résout par un alias posé à la construction : `dialogue.x = page.x`, même
objet. Un **état** partagé ne se résout pas ainsi : il reste au dialogue.

| Étape | Widgets partagés (lus ailleurs) | États partagés (restent au dialogue) |
|---|---|---|
| Modèle | `champ_axe`, `combo_axe`, `combo_plan`, `combo_sens_axe`, `combo_zone_2d`, `edit_projet_hecras`, `label_fenetre`, `radio_override`, `spin_pk_origine` | `couche_sections`, `couche_injections`, `couche_maillage`, `couche_perimetre`, `crs_modele`, `geom_couches`, `info_projet`, `version_hecras`, `_defauts`, `_boutons_defauts`, `_valeurs_au_paquet` |
| Paramètres | `edit_dossier_sortie`, `edit_prefixe_scenario`, `edit_sous_dossier_resultats`, `edit_sous_dossier_suivi`, `spin_bilan_masse`, `spin_nb_max_essais`, `spin_tol_pic`, `spin_tol_volume` | `_classeur_lu`, `_suivi_du_classeur`, `_valeurs_au_paquet`, `couche_injections`, `info_projet`, `pid_lance` |
| Lancer | `case_coeurs`, `case_elaguer`, `label_coeurs`, `label_lancement`, `poste`, `texte_resume` | `_cibles_manquantes`, `_temoins`, `_textes_bande`, `_textes_bande_vus`, `appariement`, `bande`, `label_fil`, `onglets` |
| Suivi | `minuteur_suivi` (lu par `_changer_onglet`, `showEvent`, `hideEvent`) | `pid_lance`, `instant_lance`, `journal_lance` (écrits par `_lancer_calage` ET par le banc), `_suivi_du_classeur` (écrit par `_dossier_suivi`), `onglets` (lu) |
| Aide | — | `_choix_python_ouvert`, `_python_en_attente`, `_tache_installation`, `onglets` |

À quoi s'ajoute, pour le Suivi, `_cle_journal_lu` : propre à l'étape au sens
de la règle, mais **réaffecté par le banc** (`dlg._cle_journal_lu = None`,
lignes 3440 et 3465) ; il resterait donc au dialogue.

## 4. Ordre de sortie — état après la phase 3 (10 novembre 2026)

| Rang | Page | Lignes | Références au dialogue | État / risque |
|---:|---|---:|---|---|
| 0 | **Socle** | 145 + 140 → `socle.py` | — | **fait** (phases 2 et 3) |
| 1 | **Suivi** | ~700 → `page_suivi.py` | 9 noms (§ 5) | **fait** (phase 2) |
| 2 | **Aide** | ~430 → `page_aide.py` (`AIDE_HTML` reste dans `plugin.py`) | 10 noms, plus 4 valeurs reçues (§ 7) | **fait** (phase 3) |
| 3 | Lancer | ~650 | ~20 noms : 8 états (`bande`, `label_fil`, `_temoins`, `appariement`, `_cibles_manquantes`…) et 12 méthodes du dialogue (`_maj_fil`, `_maj_resume`, `_ecarts_avec_le_paquet`, `_titre_etape`, `_dossier_suivi`, `classeur`…) ; 4 relais pour le banc | élevé |
| 4 | Modèle | ~930 | ~21 noms : 11 états (couches, `info_projet`, `version_hecras`, `crs_modele`, défauts) et 10 méthodes ; 14 relais pour le banc ; méthodes décorées `@avec_sablier` (le sablier vit sur la fenêtre) | élevé |
| 5 | Paramètres | ~970 | ~19 noms, dont la propriété `classeur` (32 réf. du banc) et 13 méthodes ; `_composition_en_cours` réaffecté par le banc ; « ±200 m » épinglé dans le texte de `plugin.py` | le plus élevé |

## 5. La page Suivi — ce qui a été fait (phase 2)

| | Avant (main, 58fefa1) | Après la phase 2 |
|---|---:|---:|
| `plugin.py` | 7 823 l. | 6 432 l. |
| `DialogueParametrage` | 5 619 l. | 4 947 l. |
| `widgets.py` / `socle.py` / `page_suivi.py` | — | 598 / 169 / 768 l. |

Quatre commits, banc QGIS vert après chacun (468 → 470 `[OK]` : un contrôle
« aucun chemin de données » par nouveau fichier `.py`) :

1. **Socle** (`socle.py`) : seulement ce que la page nomme — `BOUTON_GEOMETRIE`,
   tolérances, palette `ISL_*` (bloc entier, sous son commentaire), rôles,
   `COULEUR_STATUT`, `date_lisible`, `duree_lisible`, `courbe_retenue`,
   `texte_aide`, `dire`, `formulaire`, `DELAI_PREMIER_ETAT_S`, `_cle_fichier`.
   **`journaliser` n'y est pas** : il nomme `NOM_PLUGIN`, dont le banc exige
   l'unique définition dans le texte de `plugin.py`.
2. **Banc** : les gardes « teal institutionnel » et « `QMessageBox.question` »
   lisent tous les `.py` du plugin ; le contrôle de la fenêtre de crue lit le
   fichier qui définit `_fenetre_crue`. Essais adverses : chaque garde rougit
   sur une faute injectée dans un nouveau module. **La garde « énumérations Qt
   qualifiées » n'est pas élargie** : elle dénonce dans `bande.py`
   `Qt.TextFlag.TextDontClip`, pourtant qualifié (`TextFlag` manque à
   `_PORTEES_CONNUES`). Elle a été rejouée à la main sur les trois nouveaux
   modules : propres.
3. **`CourbeComparaison`**, `_fenetre_crue`, `SEUIL_CRUE`, `MARGE_CRUE_H`
   rejoignent `widgets.py`.
4. **`PageSuivi`** (`page_suivi.py`) : construction, lecture du journal,
   peinture (`_peindre_suivi` tel quel), bannière, tableau, boutons.

Ce que la page lit sur le dialogue — neuf noms, et rien d'autre :

| Nom | Nature | Pourquoi il reste au dialogue |
|---|---|---|
| `pid_lance`, `instant_lance`, `journal_lance` | état | écrits par `_lancer_calage` et par le banc |
| `_cle_journal_lu` | état | remis à `None` par le banc pour forcer une relecture |
| `classeur` | propriété | état du dialogue, lu par toutes les étapes |
| `_dossier_suivi`, `_origine_dossier_suivi`, `_detail_desaccord_suivi` | méthodes | lisent l'étape Paramètres et le classeur ; `_dossier_suivi` sert aussi au Lancer |
| `_signaler` | méthode | barre de messages du dialogue ; le banc la remplace par instance |

Restent aussi au dialogue : le **minuteur** (même parent, intervalle, slot
et moment de création ; la navigation le démarre et l'arrête) et le **filet**
de `_rafraichir_suivi`, qui journalise. Quatorze widgets y sont des alias
(mêmes objets), lus par le banc ou par `_oublier_dossier_suivi` ; quatre
méthodes y sont des relais pour le banc (`_peindre_journal`,
`_peindre_alertes`, `_banniere`, `_remplir_table_suivi`).

Identité vérifiée hors banc : arbre des 65 widgets de l'onglet (classe, nom,
textes, infobulles, géométrie, police, visibilité) et capture pixel à
1 200 × 900, identiques avant et après.

## 6. Ce que cette extraction apprend pour la suite

- **Le banc épingle des textes dans `plugin.py`** : `NOM_PLUGIN` écrit une
  seule fois (retient `journaliser`), « ±200 m » (étape Paramètres), et
  `src/test_lexique.py` (chaque terme du lexique, retient `AIDE_HTML`).
  Chaque page doit d'abord recenser ce que TOUS les bancs relisent dans le
  texte, pytest compris.
- **Et ce que TOUS les tests appellent, lisent ou remplacent sur le dialogue
  et sur le module `plugin`** — pas seulement `test_plugin_qgis.py`. La
  phase 3 l'a appris à ses dépens : `src/test_installation_qgis.py`, joué par
  la CI sous QGIS et absent alors du banc de l'arbitre, appelle
  `_suivre_installation` et `_reprendre_installation`, lit les états
  `_tache_installation`, `_python_en_attente`, `_erreur_installation`, et
  REMPLACE `_proposer_python` sur l'instance et `confirmer` sur le module.
  Un relais suffit pour un appel ; un état réaffecté reste au dialogue ; et
  ce qu'un test remplace, la page doit l'appeler PAR le dialogue, sans quoi
  la doublure n'est jamais vue. Le recensement se fait par script, sur
  `src/test_*.py`, `src/bancs/`, `tools/` et le paquet lui-même.
- **Relais réels sur le dialogue** : 5 pour le Suivi (`_rafraichir_suivi`,
  méthode véritable, et 4 relais) ; 9 pour l'Aide (`_survol_aide`,
  `_diagnostic`, `_installer_interpreteur`, `_choisir_python_recherche`,
  `_detacher_installation`, `_suivre_installation`, `_reprendre_installation`,
  `_proposer_python`, et `_confirmer`, qui mène à `plugin.confirmer`).
- **Les doublures du banc** (`QMessageBox`, `QFileDialog`, `QInputDialog`)
  ne valent que pour les noms du module `plugin`. Toute page qui ouvre une
  boîte — Aide, Lancer, Modèle, Paramètres, et `confirmer` s'il quittait
  `plugin.py` — les contournerait. À trancher avant la prochaine page :
  étendre les doublures aux modules de pages (renforcement du banc), ou faire
  passer les boîtes par le dialogue.
- **La règle de rattachement a tenu** : la matrice annonçait 5 états et 4
  méthodes pour le Suivi ; il en a fallu 4 et 5 (`_suivi_du_classeur` reste
  derrière `_dossier_suivi` ; `_origine_dossier_suivi` et
  `_detail_desaccord_suivi` remplacent `_dossier_suivi_de_l_onglet_3`).

- **Les doublures du banc couvrent désormais tout module du paquet** qui
  nomme `QMessageBox`, `QFileDialog` ou `QInputDialog` (phase 3) ; la garde
  « énumérations Qt qualifiées » lit tous les `.py` et connaît `TextFlag`.

## 7. La page Aide — ce qui a été fait (phase 3)

| | Après la phase 2 | Après la phase 3 |
|---|---:|---:|
| `plugin.py` | 6 432 l. | 5 862 l. |
| `DialogueParametrage` | 4 947 l. | 4 519 l. |
| `socle.py` / `page_aide.py` | 169 / — l. | 309 / 516 l. |

Banc QGIS vert après chaque commit (470 → 472 `[OK]` : le contrôle des
doublures, puis « aucun chemin de données dans page_aide.py »).

Ce que la page emploie du dialogue — dix noms, dont six imposés par
`src/test_installation_qgis.py` (voir § 6) :

| Nom | Pourquoi il reste au dialogue |
|---|---|
| la fenêtre elle-même | parent des boîtes (le centrage et la modalité suivent la fenêtre) ; porteuse de `_sablier_pose`, que `sans_sablier` et `rendre_la_main` suspendent et rétablissent |
| `isVisible()` | c'est la visibilité de la FENÊTRE qui décide d'ouvrir une boîte, pas celle de l'onglet |
| `_signaler` | barre de messages du dialogue |
| `_installation_occupe` | le lancement et `@avec_sablier` la consultent aussi |
| `_tache_installation`, `_python_en_attente`, `_choix_python_ouvert`, `_erreur_installation` | états lus par le test d'installation ; réaffectés, ils ne peuvent pas être des alias |
| `_proposer_python` | le test le remplace sur l'instance : la page l'appelle par le dialogue |
| `_confirmer` | le test remplace `plugin.confirmer` : la page passe par le dialogue, qui le lit dans le module à l'appel |

Ce qu'elle reçoit à la construction, faute de pouvoir importer `plugin.py`
qui l'importe : `AIDE_HTML`, `journaliser` (il nomme `NOM_PLUGIN`, épinglé
dans le texte de `plugin.py` par le banc) et les deux clés de réglage de
`PluginCalage`.

**`AIDE_HTML` reste dans `plugin.py`**, et c'est une épingle de plus :
`src/test_lexique.py` (joué par le pytest du banc) cherche chaque terme du
lexique dans le TEXTE de `plugin.py`, et « Δt », « fenêtre de l'événement »,
« HDF5 » n'y figurent que par lui. Le sortir faisait échouer trois cas. Lire
tous les `.py` du paquet dans ce test, comme les gardes élargies, le
libérerait ; c'est hors du périmètre de ce chantier.

**Le nœud attendu — l'installation — ne s'est dénoué qu'en partie** : les
tâches de `installation.py`, leurs signaux et l'ordre de connexion sont
inchangés, et `PluginCalage.unload` détache par un relais du dialogue ; mais
les états d'installation restent au dialogue et deux appels y repassent, parce
que `src/test_installation_qgis.py` les y lit ou les y remplace (§ 6). La
première livraison les avait emportés dans la page : deux tests sur onze
échouaient, corrigé au commit suivant. Identité vérifiée hors banc, depuis le
même dossier : arbre des 19 widgets de l'onglet, capture pixel, et parcours
d'installation simulé (phases, détachement, échec fenêtre cachée, réussite,
journal QGIS, sablier suspendu pendant la question), identiques.

## 8. Avis : le découpage a atteint son bon niveau

Le Suivi et l'Aide étaient des pages PÉRIPHÉRIQUES : chacune a sa source de
données (l'avancement du calage ; le poste) et ne partage presque rien avec
les étapes. Les trois restantes sont le cœur du flux : elles écrivent et
lisent le même état (couches, projet, classeur, témoins, défauts), que la
composition et le lancement relisent ensemble. Les sortir en `QWidget`
donnerait des pages d'une vingtaine de références chacune vers le dialogue,
plus des relais et des alias — de la plomberie, pas de l'indépendance.

Ce qui vaudrait encore son coût, si l'on continue : non plus des pages, mais
**l'état partagé du modèle** (couches, `info_projet`, `version_hecras`,
`crs_modele`, défauts) dans un objet à lui, puis, en fonctions pures et
testables hors QGIS, les deux gros traitements du commun —
`_composer_et_controler_interne` (211 l.) et `_lancer_calage` (168 l.). C'est
un autre chantier, à instruire par sa propre matrice.

## 9. Décision du 11 novembre 2026 : pas d'objet d'état, une frontière fenêtre / noyau

Tranché par Cédric, avec une vue « long terme, partagé à beaucoup de monde ».

**Mesuré avant de décider** (`plugin.py`, classe `DialogueParametrage`) :

| Mesure | Valeur |
|---|---|
| Dialogue | 4 544 lignes, 123 méthodes |
| États réellement partagés (lus ou écrits par 4 méthodes ou plus) | 7 sur 45 |
| `_composer_et_controler_interne` | 211 lignes, 16 widgets lus |
| `_lancer_calage` | 168 lignes, 7 widgets lus |

**Pas d'objet d'état.** Sept attributs partagés ne le justifient pas, même à plusieurs
mainteneurs : ce serait de la plomberie, pas de l'indépendance (§ 8).

**Une frontière, en revanche : la fenêtre lit ses widgets et affiche, `noyau.py` décide.** Ce
qui paie sur la durée, c'est de pouvoir vérifier un changement de la composition ou du
lancement sans QGIS — c'est là que viendront les nouveaux paramètres et les nouveaux contrôles,
et là qu'un contributeur casserait quelque chose sans le voir.

| Étape | Contenu | État |
|---|---|---|
| A | Les refus de la composition dans `noyau.py` (`refus_avant_composition`, `refus_appariement`, `dire_pentes_pre_remplies`), éprouvés sans QGIS (`src/test_refus_composition.py`) ; le raccord de la fenêtre éprouvé sous QGIS (`src/test_composition_fenetre.py`) | fait le 11/11/2026 |
| B | La saisie lue dans les widgets rassemblée en une structure simple ; la composition, puis le lancement, confiés à des fonctions de `noyau.py` testées sans QGIS. Une PR par traitement, sous filet | à faire |

**Ce que l'étape A n'a pas déplacé** : le refus d'une projection géographique. Il interroge
`QgsCoordinateReferenceSystem`, que `noyau.py` n'importe pas ; le rejouer avec une autre
bibliothèque changerait la lecture des systèmes mal formés. Il reste dans la fenêtre.

## Annexe — matrice complète

Lignes de 58fefa1. « Étapes » : étapes des méthodes qui touchent l'attribut
(Mod, Par, Lan, Sui, Aid, com). « Banc » : références `.<nom>` dans
`src/test_plugin_qgis.py`. Partagés d'abord, puis propres.

| Attribut | Nature | Créé dans (ligne) | Écrit par | Lu par | Étapes | Banc |
|---|---|---|---|---|---|---:|
| `_cibles_manquantes` | état | `_maj_onglet_validation_depuis_classeur` (6795) | `_maj_onglet_validation`, `_maj_onglet_validation_depuis_classeur` | `_maj_coherence`, `_maj_fil` | Lan com |  |
| `case_coeurs` | widget | `_groupe_calcul` (4811) | `_groupe_calcul` | `_coeurs_demandes`, `_dire_coeurs` | Lan com | 1 |
| `case_elaguer` | widget | `_groupe_menage` (4762) | `_groupe_menage` | `_composer_et_controler_interne`, `_dire_elagage`, `_lancer_calage`, `_valeurs_de_la_fenetre` | Lan com | 9 |
| `label_coeurs` | widget | `_groupe_calcul` (4827) | `_groupe_calcul` | `_dire_coeurs` | Lan com | 3 |
| `label_lancement` | widget | `_onglet_validation` (5092) | `_onglet_validation` | `_accepter_plan_final`, `_confirmer_reprise`, `_lancer_calage` | Lan com | 2 |
| `poste` | widget | `_groupe_calcul` (4808) | `_groupe_calcul` | `_coeurs_demandes`, `_dire_coeurs` | Lan com | 2 |
| `texte_resume` | widget | `_groupe_configuration` (4793) | `_groupe_configuration` | `_composer_resume` | Lan com | 7 |
| `champ_axe` | widget | `_groupe_axe` (4056) | `_groupe_axe` | `_composer_et_controler_interne` | Mod com |  |
| `combo_axe` | widget | `_groupe_axe` (4034) | `_groupe_axe` | `_composer_et_controler_interne`, `_composer_resume`, `_etapes_avant_controle`, `_etapes_preparation` | Mod com | 4 |
| `combo_plan` | widget | `_onglet_modele` (2735) | `_onglet_modele` | 14 méthodes | Mod com | 12 |
| `combo_sens_axe` | widget | `_groupe_axe` (4064) | `_groupe_axe` | `_composer_et_controler_interne`, `_montrer`, `_valeurs_de_la_fenetre` | Mod com | 9 |
| `combo_zone_2d` | widget | `_onglet_modele` (2798) | `_onglet_modele` | 6 méthodes | Mod com | 5 |
| `edit_projet_hecras` | widget | `_onglet_modele` (2692) | `_onglet_modele` | `_accepter_plan_final`, `_composer_resume`, `_dossier_projet`, `_parcourir_projet_hecras` | Mod com | 13 |
| `label_fenetre` | widget | `_onglet_modele` (2886) | `_onglet_modele` | `_composer_resume`, `_resume_fenetre` | Mod com | 9 |
| `radio_override` | widget | `_onglet_modele` (2747) | `_onglet_modele` | 6 méthodes | Mod com |  |
| `spin_pk_origine` | widget | `_groupe_axe` (4077) | `_groupe_axe` | `_composer_et_controler_interne`, `_valeurs_de_la_fenetre` | Mod com | 6 |
| `_classeur_lu` | état | `_maj_resume_cibles` (4630) | `_maj_resume_cibles`, `_relire_cibles_si_modifiees` | — | Par com | 2 |
| `_suivi_du_classeur` | état | `_dossier_suivi` (5386) | `_dossier_suivi`, `_oublier_dossier_suivi` | `_origine_dossier_suivi` | Par Sui |  |
| `_valeurs_au_paquet` | état | `classeur` (4471) | `classeur` | `_ecarts_avec_le_paquet` | Mod Par |  |
| `edit_dossier_sortie` | widget | `_groupe_dossier_sortie` (4688) | `_groupe_dossier_sortie` | 9 méthodes | Par com | 26 |
| `edit_prefixe_scenario` | widget | `_champ_prefixe_scenario` (4221) | `_champ_prefixe_scenario` | 9 méthodes | Par com | 31 |
| `edit_sous_dossier_resultats` | widget | `_groupe_dossier_sortie` (4710) | `_groupe_dossier_sortie` | `_composer_et_controler_interne`, `_composer_resume`, `_valeurs_de_la_fenetre` | Par com | 2 |
| `edit_sous_dossier_suivi` | widget | `_groupe_dossier_sortie` (4716) | `_groupe_dossier_sortie` | 5 méthodes | Par com | 3 |
| `spin_bilan_masse` | widget | `_groupe_precision` (4149) | `_groupe_precision` | `_composer_et_controler_interne`, `_lancer_calage`, `_valeurs_de_la_fenetre` | Par com | 1 |
| `spin_nb_max_essais` | widget | `_groupe_precision` (4171) | `_groupe_precision` | `_composer_et_controler_interne`, `_lancer_calage`, `_valeurs_de_la_fenetre` | Par com | 3 |
| `spin_tol_pic` | widget | `_groupe_precision` (4127) | `_groupe_precision` | `_composer_et_controler_interne`, `_lancer_calage`, `_valeurs_de_la_fenetre` | Par com | 3 |
| `spin_tol_volume` | widget | `_groupe_precision` (4113) | `_groupe_precision` | `_composer_et_controler_interne`, `_lancer_calage`, `_valeurs_de_la_fenetre` | Par com | 11 |
| `minuteur_suivi` | widget | `_onglet_suivi` (5305) | `_onglet_suivi` | `_changer_onglet`, `hideEvent`, `showEvent` | Sui com | 4 |
| `_boutons_defauts` | état | `__init__` (2163) | `__init__` | `_bouton_defauts`, `_maj_defauts` | Mod com | 6 |
| `_choix_python_ouvert` | état | `__init__` (2093) | `__init__`, `_choisir_python_recherche` | `_installer_interpreteur` | Aid com |  |
| `_defauts` | état | `__init__` (2162) | `__init__` | `_maj_defauts`, `_marque_defaut`, `_revenir_aux_defauts` | Mod com | 7 |
| `_python_en_attente` | état | `__init__` (2092) | `__init__`, `_choisir_python_recherche`, `_fin_recherche_python` | `_installer_interpreteur` | Aid com |  |
| `_tache_installation` | état | `__init__` (2091) | `__init__`, `_detacher_installation`, `_suivre_installation` | `_fin_recherche_python`, `_phase_installation` | Aid com |  |
| `_temoins` | état | `__init__` (2160) | `__init__` | `_maj_temoins`, `_temoin` | Lan com | 7 |
| `_textes_bande` | état | `_bande` (2376) | `_bande` | `_maj_temoins` | Lan com |  |
| `_textes_bande_vus` | état | `_bande` (2377) | `_bande` | `_maj_temoins` | Lan com |  |
| `appariement` | état | `__init__` (2129) | `__init__`, `_composer_et_controler_interne` | `_maj_onglet_validation` | Lan com | 3 |
| `bande` | état | `__init__` (2241) | `__init__` | `_maj_temoins` | Lan com | 8 |
| `couche_injections` | état | `__init__` (2143) | `__init__`, `_charger_couches_modele` | 5 méthodes | Mod Par com | 10 |
| `couche_maillage` | état | `__init__` (2145) | `__init__`, `_charger_couches_modele` | — | Mod com | 4 |
| `couche_perimetre` | état | `__init__` (2144) | `__init__`, `_charger_couches_modele` | — | Mod com | 2 |
| `couche_sections` | état | `__init__` (2142) | `__init__`, `_charger_couches_modele` | 5 méthodes | Mod com | 23 |
| `crs_modele` | état | `__init__` (2141) | `__init__`, `_charger_couches_modele` | `_composer_et_controler_interne` | Mod com | 1 |
| `geom_couches` | état | `__init__` (2140) | `__init__`, `_charger_couches_modele` | `_maj_alerte_couches` | Mod com | 3 |
| `info_projet` | état | `__init__` (2124) | `__init__`, `_charger_projet_hecras` | 11 méthodes | Mod Par com | 11 |
| `instant_lance` | état | `__init__` (2123) | `__init__`, `_lancer_calage` | `_peindre_suivi` | Sui com | 4 |
| `journal_lance` | état | `__init__` (2119) | `__init__`, `_lancer_calage` | `_journal_du_calage`, `_peindre_suivi` | Sui com | 8 |
| `label_fil` | état | `__init__` (2258) | `__init__` | `_composer_resume`, `_maj_fil`, `_maj_onglet_validation`, `_maj_onglet_validation_depuis_classeur` | Lan com | 19 |
| `onglets` | état | `__init__` (2198) | `__init__` | 9 méthodes | Aid Lan Sui com | 82 |
| `pid_lance` | état | `__init__` (2118) | `__init__`, `_lancer_calage` | `_maj_bouton_controle`, `_maj_fil`, `_peindre_suivi` | Par Sui com | 10 |
| `version_hecras` | état | `__init__` (2125) | `__init__`, `_charger_projet_hecras` | `_composer_et_controler_interne`, `_composer_resume` | Mod com | 6 |
| `_commandes_poste` | widget | `_onglet_aide` (6159) | `_onglet_aide` | `_fin_installation`, `_fin_recherche_python`, `_suivre_installation` | Aid | 1 |
| `_erreur_installation` | état | `_fin_installation` (6442) | `_fin_installation` | — | Aid |  |
| `bouton_installer` | widget | `_onglet_aide` (6158) | `_onglet_aide` | — | Aid |  |
| `label_chaine` | widget | `_onglet_aide` (6105) | `_onglet_aide` | `_maj_parametres_poste` | Aid | 4 |
| `label_diagnostic` | widget | `_onglet_aide` (6102) | `_onglet_aide` | `_diagnostic`, `_fin_installation`, `_fin_recherche_python`, `_phase_installation` | Aid | 2 |
| `label_interpreteur` | widget | `_onglet_aide` (6126) | `_onglet_aide` | `_maj_parametres_poste` | Aid | 6 |
| `navigateur_aide` | widget | `_onglet_aide` (6066) | `_onglet_aide` | `_ouvrir_lexique`, `_survol_aide` | Aid | 5 |
| `progression_installation` | widget | `_onglet_aide` (6160) | `_onglet_aide` | `_fin_installation`, `_fin_recherche_python`, `_phase_installation`, `_suivre_installation` | Aid |  |
| `bouton_lancer` | widget | `_onglet_validation` (5078) | `_onglet_validation` | — | Lan |  |
| `combo_premier_apport` | widget | `_groupe_copies_de_travail` (3620) | `_groupe_copies_de_travail` | `_confirmer_reprise`, `_premier_apport`, `_remplir_premier_apport` | Lan | 12 |
| `label_elagage` | widget | `_groupe_menage` (4782) | `_groupe_menage` | `_dire_elagage` | Lan | 5 |
| `label_premier_apport` | widget | `_groupe_copies_de_travail` (3636) | `_groupe_copies_de_travail` | `_dire_premier_apport`, `_remplir_premier_apport` | Lan |  |
| `label_prochaine_etape` | widget | `_onglet_validation` (5044) | `_onglet_validation` | `_maj_coherence` | Lan | 9 |
| `label_reprise` | widget | `_onglet_validation` (5073) | `_onglet_validation` | `_dire_reprise` | Lan | 12 |
| `label_validation_cibles` | widget | `_onglet_validation` (5039) | `_onglet_validation` | `_maj_onglet_validation`, `_maj_onglet_validation_depuis_classeur` | Lan |  |
| `label_validation_classeur` | widget | `_onglet_validation` (5030) | `_onglet_validation` | `_maj_onglet_validation`, `_maj_onglet_validation_depuis_classeur` | Lan |  |
| `label_validation_comptes` | widget | `_onglet_validation` (5027) | `_onglet_validation` | `_maj_onglet_validation` | Lan | 3 |
| `_cle_paquet_lu` | état | `_parametres_du_paquet` (3086) | `_parametres_du_paquet` | — | Mod |  |
| `_paquet_lu` | état | `_parametres_du_paquet` (3085) | `_parametres_du_paquet` | — | Mod |  |
| `bouton_charger_couches` | widget | `_groupe_couches_existantes` (2917) | `_groupe_couches_existantes` | — | Mod |  |
| `combo_geometrie` | widget | `_onglet_modele` (2768) | `_onglet_modele` | `_charger_projet_hecras`, `_geometrie_effective`, `_maj_mode_override`, `_maj_resume_fichiers` | Mod |  |
| `combo_unsteady` | widget | `_onglet_modele` (2769) | `_onglet_modele` | `_charger_projet_hecras`, `_maj_mode_override`, `_maj_resume_fichiers`, `_unsteady_effective` | Mod |  |
| `edit_sim_debut` | widget | `_onglet_modele` (2854) | `_onglet_modele` | `_remplir_fenetre_depuis_plan`, `fenetre_saisie` | Mod | 4 |
| `edit_sim_fin` | widget | `_onglet_modele` (2855) | `_onglet_modele` | `_remplir_fenetre_depuis_plan`, `fenetre_saisie` | Mod | 12 |
| `edits_intervalles` | widget | `_onglet_modele` (2868) | `_onglet_modele` | `_remplir_fenetre_depuis_plan`, `fenetre_saisie` | Mod | 1 |
| `groupe_fenetre` | widget | `_onglet_modele` (2838) | `_onglet_modele` | — | Mod | 1 |
| `label_couches` | widget | `_groupe_couches_existantes` (2919) | `_groupe_couches_existantes` | `_charger_couches_modele` | Mod |  |
| `label_fichiers_plan` | widget | `_onglet_modele` (2758) | `_onglet_modele` | `_maj_resume_fichiers` | Mod |  |
| `label_geom_couches` | widget | `_onglet_modele` (2807) | `_onglet_modele` | `_maj_alerte_couches` | Mod | 6 |
| `label_geometrie_override` | widget | `_onglet_modele` (2784) | `_onglet_modele` | `_maj_resume_fichiers` | Mod |  |
| `label_nom_projet` | widget | `_onglet_modele` (2722) | `_onglet_modele` | `_charger_projet_hecras` | Mod | 1 |
| `label_unsteady_override` | widget | `_onglet_modele` (2786) | `_onglet_modele` | `_maj_resume_fichiers` | Mod |  |
| `label_version_calage` | widget | `_onglet_modele` (2729) | `_onglet_modele` | `_charger_projet_hecras` | Mod | 8 |
| `radio_du_plan` | widget | `_onglet_modele` (2743) | `_onglet_modele` | — | Mod |  |
| `_classeur` | état | `classeur` (4466) | `classeur` | — | Par |  |
| `_composition_en_cours` | état | `_composer_et_controler` (7458) | `_composer_et_controler` | — | Par | 2 |
| `_dossier_sortie_propose` | état | `_proposer_dossier_sortie` (5008) | `_proposer_dossier_sortie` | — | Par |  |
| `bouton_composer` | widget | `_bouton_controle_parametrage` (3007) | `_bouton_controle_parametrage` | — | Par |  |
| `bouton_controle` | widget | `_groupe_classeur` (4381) | `_groupe_classeur` | `_maj_bouton_controle` | Par | 26 |
| `bouton_importer` | widget | `_groupe_classeur` (4404) | `_groupe_classeur` | `_maj_groupe_classeur` | Par | 5 |
| `bouton_ouvrir_classeur` | widget | `_groupe_classeur` (4397) | `_groupe_classeur` | `_maj_groupe_classeur`, `classeur` | Par | 2 |
| `consigne_classeur` | widget | `_groupe_classeur` (4385) | `_groupe_classeur` | `_maj_groupe_classeur` | Par |  |
| `groupe_pente` | widget | `_groupe_classeur` (4433) | `_groupe_classeur` | `_maj_groupe_classeur` | Par |  |
| `label_classeur_attente` | widget | `_onglet_objectifs` (4521) | `_onglet_objectifs` | `_maj_groupe_classeur` | Par | 11 |
| `label_import` | widget | `_groupe_classeur` (4422) | `_groupe_classeur` | `_importer_hydrogrammes` | Par | 4 |
| `label_resume_cibles` | widget | `_groupe_ce_que_portent_les_cibles` (4587) | `_groupe_ce_que_portent_les_cibles` | `_maj_resume_cibles` | Par | 14 |
| `label_titres_prefixe` | widget | `_champ_prefixe_scenario` (4262) | `_champ_prefixe_scenario` | `_dire_titres_prefixe` | Par | 15 |
| `zone_resume_cibles` | widget | `_groupe_ce_que_portent_les_cibles` (4603) | `_groupe_ce_que_portent_les_cibles` | `_maj_resume_cibles` | Par |  |
| `_alertes_depliees` | état | `_peindre_alertes` (5683) | `_peindre_alertes` | — | Sui |  |
| `_alertes_lues` | état | `_lire_journal` (5619) | `_lire_journal` | — | Sui |  |
| `_archive_suivi` | état | `_suivi_precedent` (5976) | `_suivi_precedent` | — | Sui |  |
| `_cle_journal_lu` | état | `_lire_journal` (5617) | `_lire_journal` | — | Sui | 4 |
| `_derniere_panne_suivi` | état | `_rafraichir_suivi` (5712) | `_rafraichir_suivi` | — | Sui |  |
| `_journal_lu` | état | `_lire_journal` (5618) | `_lire_journal` | — | Sui |  |
| `barre_suivi` | widget | `_onglet_suivi` (5190) | `_onglet_suivi` | `_peindre_suivi` | Sui | 3 |
| `courbe_suivi` | widget | `_onglet_suivi` (5230) | `_onglet_suivi` | `_peindre_suivi` | Sui | 18 |
| `groupe_alertes` | widget | `_onglet_suivi` (5142) | `_onglet_suivi` | `_peindre_alertes` | Sui | 2 |
| `groupe_journal` | widget | `_onglet_suivi` (5163) | `_onglet_suivi` | `_peindre_journal` | Sui | 6 |
| `jauges` | widget | `_onglet_suivi` (5206) | `_onglet_suivi` | `_peindre_suivi` | Sui | 19 |
| `label_bilan_masse` | widget | `_onglet_suivi` (5228) | `_onglet_suivi` | `_afficher_bilan_masse` | Sui |  |
| `label_jauges` | widget | `_onglet_suivi` (5221) | `_onglet_suivi` | `_peindre_suivi` | Sui | 6 |
| `label_suivi_banniere` | widget | `_onglet_suivi` (5114) | `_onglet_suivi` | `_banniere`, `_oublier_dossier_suivi` | Sui | 28 |
| `label_suivi_dossier` | widget | `_onglet_suivi` (5127) | `_onglet_suivi` | `_peindre_suivi` | Sui | 5 |
| `label_suivi_ecoule` | widget | `_onglet_suivi` (5239) | `_onglet_suivi` | `_peindre_suivi` | Sui |  |
| `label_suivi_fin` | widget | `_onglet_suivi` (5241) | `_onglet_suivi` | `_peindre_suivi` | Sui |  |
| `label_suivi_maj` | widget | `_onglet_suivi` (5286) | `_onglet_suivi` | `_peindre_suivi` | Sui |  |
| `label_suivi_position` | widget | `_onglet_suivi` (5195) | `_onglet_suivi` | `_peindre_suivi` | Sui | 4 |
| `label_suivi_reste` | widget | `_onglet_suivi` (5240) | `_onglet_suivi` | `_peindre_suivi` | Sui | 3 |
| `ruban_apports` | widget | `_onglet_suivi` (5188) | `_onglet_suivi` | `_peindre_suivi` | Sui | 10 |
| `table_suivi` | widget | `_onglet_suivi` (5256) | `_onglet_suivi` | `_peindre_suivi`, `_remplir_table_suivi` | Sui | 24 |
| `texte_alertes` | widget | `_onglet_suivi` (5150) | `_onglet_suivi` | `_peindre_alertes` | Sui | 6 |
| `texte_journal` | widget | `_onglet_suivi` (5170) | `_onglet_suivi` | `_peindre_journal` | Sui | 4 |
| `_minuteur_style` | état | `__init__` (2150) | `__init__` | `changeEvent`, `eventFilter` | com |  |
| `_remplacer_plan_source` | état | `__init__` (2128) | `__init__`, `_accepter_plan_final` | `_lancer_calage` | com | 3 |
| `_style_en_attente` | état | `__init__` (2149) | `__init__`, `_actualiser_style`, `changeEvent`, `eventFilter` | — | com |  |
| `barre_messages` | état | `__init__` (2177) | `__init__` | `_signaler` | com | 10 |
| `barre_preparation` | état | `__init__` (2293) | `__init__` | `_maj_fil` | com | 3 |
| `bouton_precedent` | état | `__init__` (2304) | `__init__` | `_maj_navigation` | com |  |
| `bouton_suivant` | état | `__init__` (2309) | `__init__` | `_maj_navigation` | com |  |
| `iface` | état | `__init__` (2090) | `__init__` | — | com |  |
| `paquet` | état | `__init__` (2147) | `__init__`, `_composer_et_controler_interne` | — | com | 2 |
