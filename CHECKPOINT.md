# CHECKPOINT — Calage des apports (ISL Ingénierie)

Point de reprise pour ouvrir une nouvelle conversation avec un contexte
minimal. L'état courant et les règles en vigueur restent dans `STATUT.txt` ;
ce fichier ne dit que **où on en est** et **par quoi reprendre**.

## ▶ Reprendre ici — état au 7 septembre 2026

Le travail du 7 est sur la branche **`claude/project-files-overview-ld982p`**,
poussée, **à fusionner dans `main`**. Le 6 au soir, tout était sur `main`.

**Plugin en 0.7.16** — pas encore installé dans QGIS : **l'archive est à
reconstruire depuis Windows** (`python src/faire_zip.py`), `noyau.py` et la
chaîne embarquée ont changé. Bancs, depuis un clone Linux : les **quatorze
exécutables hors HEC-RAS/QGIS sont verts**, dont `calage` contre sa référence
regelée, `noyau`, `faire_zip` « archive conforme », `essai_garde_fou_archive`
« TOUT PASSE ». La suite du plugin (172 contrôles au 6) n'a pas été rejouée :
elle exige QGIS.

### Ce que la journée du 7 a donné

| | |
|---|---|
| **Le KGE, alpha et beta sont retirés du code** — la figure de convergence des livrables finaux traçait beta sous « Volume atteint (% de la cible) », celle du suivi sortait vide | `STATUT.txt` § 1 et § 2, VOLUME |
| **`tolerance_beta` s'appelle `tolerance_volume`** ; la référence de caractérisation est regelée, identique à l'ancienne privée des trois clés | |
| **Deux bancs passent désormais depuis un clone Linux** — `noyau` (disposition d'un venv) et le garde-fou d'archive (chemins POSIX, qu'il ne voyait pas) | |
| **La note se reconstruit sans qu'on lui porte ses deux figures d'origine** — elles sont lues dans le gabarit | |
| **Trois affirmations de `STATUT.txt` corrigées** : le PDF n'était pas en retard (Version 15), `reprises_max` n'est pas « inerte » mais retiré, l'ordre total est en § 1.2 de la note — c'est `idees_V2_plugin.md` qui disait § 1.3 | |
| Lecture complète du dépôt, 54 fichiers, doc et code | |

### Ce que la journée du 6 a donné

| | |
|---|---|
| **La suite du plugin passe de bout en bout** — 152 annoncés, 172 obtenus | `STATUT.txt` § 1 |
| **Sept défauts du banc**, tous « il suppose le monde de son auteur » | `STATUT.txt` § 1 |
| **Lot 5 d'`AUDIT.md`** — mené le **5 au soir** : `caler()` 699 → 622 lignes, 3ᵉ extraction écartée sur mesure | `AUDIT.md` § P1-4 |
| **`AUDIT.md` est clos** — seul P2-10 reste, et l'audit dit que ce n'est pas un lot | |
| **Les correctifs d'ergonomie**, 0.7.1 à 0.7.14 (la note s'arrête à 0.7.12 : les deux dernières viennent d'une demande directe) | `docs/ergonomie_2026-09-06.md` |
| Le bouton « Installer… » **éprouvé depuis QGIS**, ses deux chemins | `STATUT.txt` § 1 |
| La note méthodologique **reconstruite** — sa table d'onglets datait d'avant la 0.7.0 | |

### Ce qui reste, et rien d'autre

0. **Reconstruire l'archive depuis Windows et réinstaller** — `python
   src/faire_zip.py`, puis Extensions → Installer depuis un ZIP. Sans cela le
   plugin installé porte encore le KGE et la figure fausse.
1. **Regarder la fenêtre.** Quatorze versions d'interface publiées en un
   jour — 0.7.1 à 0.7.14 — toutes vérifiées au banc, aucune sous les yeux de
   l'utilisateur. En particulier :
   **Entrée ne fait plus rien**, nulle part — c'est le prix assumé du
   désarmement du geste irréversible, et il se voit.
2. **Le suivi pendant un vrai calage.** L'état du calage précédent qui ne se
   peint plus, « mort au démarrage » distingué de « pas encore parti », le
   fil qui dit « calage lancé », la question posée si l'on recompose pendant
   qu'un calcul tourne : tout cela est éprouvé sur des états **fabriqués**,
   jamais sur un calage qui tourne. Y regarder aussi la **figure de
   convergence** corrigée, dans `suivi/` et dans `resultats_finaux/`.
3. **Trois garde-fous jamais rencontrés en réel** — volume plancher, apport
   refusé, modèle incohérent. Seul le banc les couvre.
4. **L'hypothèse d'ordre total.** Le seul vrai levier qui reste : si le
   jacobien est triangulaire, le coût cesse de dépendre du nombre d'apports —
   `nb_calculs = nb_essais` au lieu de `nb_apports × nb_essais`, soit un
   facteur **18 sur un modèle à 30 apports** d'après le tableau de
   `docs/idees_V2_plugin.md` § 1 — et c'est ce
   chantier qui réécrirait la boucle dont la troisième extraction a été
   écartée. `STATUT.txt` la liste toujours comme **non confirmée**. C'est une
   question d'hydraulicien, pas de code.

### Le poste de travail, pour y revenir

`venv-hecras` monté, `CALAGE_PYTHON` figé au niveau utilisateur,
`.affaires` créé depuis l'exemple. `QGIS_PREFIX_PATH` **n'est plus à
poser** : le banc le déduit de l'interpréteur qui tourne. Le modèle
d'essai est le plan **TEST** de `Muncie` (`p02`/`g02`), auquel deux
`BC Line` et deux `Reference Line` ont été ajoutées — la seconde section
en **aval** de la première, sans quoi le plugin refuse à juste titre.

### Deux questions déjà tranchées, pour ne pas les rouvrir

- **Le repli cassé des pentes n'a jamais été emprunté** — les journaux des trois
  calages ne portent pas `pente : deduction impossible`. Aucun livrable à
  reprendre. Le défaut était **latent**, et il est corrigé.
- **La réserve de périmètre du volume énonce un périmètre, elle ne dénonce pas
  un défaut** : elle se lève aussi sur une mini-crue exclue à bon droit, et
  c'est assumé (les séparer demanderait un seuil non mesuré).

---

## Reprendre depuis GitHub, sans le poste de travail

Le dépôt porte le code, `STATUT.txt`, ce fichier, la note et le template.
**L'historique des conversations ne voyage pas** — il vit dans
`~/.claude/projects\…` sur le poste. Ces deux fichiers le remplacent.

**Par quoi commencer :** la section « Reprendre ici » ci-dessus, puis
`STATUT.txt` § 1, § 2.2 bis, § 2.2 ter, § 5.3 ter et § 5.5.

**Installer :** `python -m pip install -r requirements-dev.txt`

**Ce qui ne sera PAS disponible hors du poste**, et qu'il ne faut pas chercher
à contourner :

| | |
|---|---|
| le partage réseau des modèles | ni suivi de calage, ni lecture de journal, ni relecture de HDF |
| HEC-RAS, `ras-commander`, `h5py` | aucun calage ne peut être lancé ni relu |
| QGIS | `test_plugin_qgis.py` exige le Python de QGIS |
| Word | l'export PDF de la note passe par lui ; le `.docx`, lui, se reconstruit |
| `.affaires` | ignoré par git — ce sont des noms de clients |

Sur `.affaires` : sans lui, `essai_garde_fou_archive.py` éprouve quand même le
contrôle des noms, **sur un mot qu'il fabrique**, et dit que la liste reste à
fournir. Le garde-fou n'est donc pas muet — mais il ne surveille rien de réel.
Avant de committer depuis un clone neuf, se rappeler qu'un nom de client
passerait.

## Les sessions passées

Elles vivaient ici, section par section — trente et un récits, plus de deux
mille lignes, dont ce fichier disait lui-même qu'ils étaient « conservés comme
récit, **pas comme référence** ». Ils sont retirés : `git log` les porte, et
`STATUT.txt` porte ce qui en est resté vrai.
