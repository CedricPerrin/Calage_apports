# CHECKPOINT — Calage des apports (ISL Ingénierie)

Point de reprise pour ouvrir une nouvelle conversation avec un contexte
minimal. L'état courant et les règles en vigueur restent dans `STATUT.txt` ;
ce fichier ne dit que **où on en est** et **par quoi reprendre**.

## ▶ Reprendre ici — état au 8 septembre 2026

Tout est sur **`main`**. La branche `claude/project-files-overview-ld982p` a
été **supprimée** le 8 : elle pointait sur le même commit que `main`, sans
aucun commit propre.

**Plugin en 0.7.18**, archive **reconstruite et versionnée** — `calage_apports.zip`
porte la 0.7.18, construite sous Linux : les vingt fichiers embarqués sont en
fins de ligne LF, identiques à l'octet aux sources ; la prochaine construction
Windows les remettra en CRLF. **Pas encore réinstallée dans QGIS.** Bancs rejoués le 8 **depuis
le poste**, donc avec `.affaires` : `calage` contre sa référence regelée,
`criteres`, `suivi`, `livrables`, `style_classeur`, `creer_template`,
`faire_zip` « archive conforme » et `essai_garde_fou_archive` « TOUT PASSE » —
ces deux derniers **après** le retrait des quatre noms de cas. Trois bancs
n'ont pas pu tourner ici, faute de `geopandas` et de `h5py` dans le Python
ordinaire : `geometrie`, `controle_donnees`, `elaguer_projet` — il leur faut
l'interpréteur HEC-RAS, que `CALAGE_PYTHON` ne désigne plus sur ce poste. La
suite du plugin (172 contrôles au 6, sept de plus depuis) n'a pas été rejouée :
elle exige QGIS.

### Ce que la journée du 8 a donné

**Deux décisions d'hydraulicien, et un onglet 1 remanié.** Le plugin passe en
**0.7.19** — non réinstallé, non vu sous QGIS.

| | |
|---|---|
| **Il n'y a pas de boucle hydraulique** — confirmé. L'hypothèse d'ordre total tient. Elle est désormais écrite **comme une hypothèse du modèle, que la chaîne ne vérifie pas** : aide du plugin, note § 1.2 et « Trois questions bloquantes », README | `STATUT.txt` § 6, À FOURNIR |
| **Le verdict de volume reste sur la fenêtre** — « le concept de fenêtre a été fait pour ça ». Rien ne change dans le code ; l'aide et la note l'énoncent, la question d'élargir la fenêtre est close | `STATUT.txt` § 6, À TRANCHER |
| **« Écrire, composer et contrôler » ferme l'onglet 1**, dans un encadré « Mise à jour du modèle » — il était permanent en bas de la fenêtre, visible depuis six onglets dont cinq n'en font rien | |
| **L'encadré « Écriture dans la géométrie » descend dans l'aide** — il ne portait aucune commande, et se lisait pourtant comme une étape. Son compte rendu ouvre maintenant la boîte de composition, d'où il est enfin visible | |
| **« Axe hydraulique » devient « Profil en long »**, et remonte sous le plan | |
| **L'aide perd « Sur un autre poste »** — elle ne disait rien de plus que « Première utilisation » | |
| **Le garde-fou d'archive a mordu pour de vrai** — quatre noms de cas réels dormaient dans des commentaires de la chaîne embarquée, invisibles depuis le clone Linux du 7, qui n'avait pas `.affaires`. La mesure reste, le nom renvoie à `STATUT.txt` § 5. `faire_zip` rend de nouveau « archive conforme », le garde-fou « TOUT PASSE » | `STATUT.txt` § 1 |
| **L'archive porte la 0.7.19**, reconstruite sous Windows — les vingt fichiers sont donc en CRLF | |
| **La note passe en V16** — `contenu.py` § 1.2, § 1.4 et le chapitre du plugin ; `.docx` reconstruit, 8 911 mots. **Le `.pdf` reste en V15** : Word se fige dans son export sur ce poste, et pas à cause du document — la note d'avant, sortie de git, se fige pareil | `STATUT.txt` § 6 |
| **Les six captures sont refaites, et par un script** — `src/captures_plugin.py`, avec un projet de démonstration et les chemins du poste mis en scène | `STATUT.txt` § 1 |
| **Deux défauts d'affichage trouvés PAR les captures** — le libellé du bouton coupé à mi-hauteur dans une fenêtre trop courte, et une phrase à deux lignes dont la seconde sortait rognée. Le banc ne les voit pas : il n'éprouve pas l'apparence | `STATUT.txt` § 1 |
| **Le banc du plugin rejoué : 153 contrôles, 0 échec**, sur une copie réduite d'un modèle réel (113 Mo au lieu de 60 Go). Sept contrôles neufs pour la 0.7.19, plus trois pour la branche « poste neuf » du diagnostic | `STATUT.txt` § 1 |
| **Deux défauts du banc de plus**, même motif que les huit précédents — il suppose le monde de son auteur : le mannequin de `QMessageBox` ignorait quatre méthodes que seule la branche « pas d'interpréteur » appelle, et un appariement impossible était compté comme quatre échecs au lieu d'un diagnostic sur le modèle | `STATUT.txt` § 1 |
| **L'interpréteur HEC-RAS posé par le bouton « Installer… »**, depuis QGIS, sur un poste qui n'en avait pas — le point ouvert depuis le 30/08 est levé | `STATUT.txt` § 1 |

### La 0.7.22 — remaniement d'ergonomie

| | |
|---|---|
| **L'onglet 1 suit l'ordre des gestes** : projet, plan, couches, profil en long, fenêtre | `STATUT.txt` § 1 |
| **« Contrôle du paramétrage » passe à l'onglet 2**, après la précision attendue — troisième déménagement, et le dernier a une raison qui tient | |
| **L'élagage devient une case à cocher**, décidée avant le calage et appliquée par la chaîne à la fin. L'encadré dit « Les plans intermédiaires seront CONSERVÉS / SUPPRIMÉS », le mot en rouge dans les deux sens | |
| **Le préfixe de scénario est obligatoire** — c'est ce qui empêche la seule perte de données que la chaîne sache provoquer | |
| « Relire un hydrogramme » quitte la fenêtre ; trois passe-plats de `noyau.py` partent avec lui | |
| **La console noire a disparu pour de bon** : le calage part par `pythonw.exe`, binaire graphique auquel Windows n'alloue jamais de console. Le correctif précédent — console réduite — ne valait que pour le processus créé, pas pour celui que le relais crée | |
| Banc du plugin : **128 contrôles, 0 échec** | |

### La 0.7.21 — l'action passe à l'onglet 4

| | |
|---|---|
| **« Écrire, composer et contrôler » quitte l'onglet 1 pour l'onglet 4**, dans un encadré **« Contrôle du paramétrage »** qui précède « Calage ». Ce qu'il produit — paquet, classeur, compte rendu — se lit là ; le composer ailleurs obligeait à revenir en arrière. On ne lance plus rien sans être passé devant le compte rendu | `STATUT.txt` § 1 |
| Le nom change avec la place : « Mise à jour du modèle » annonçait l'effet de bord, pas le geste qu'on cherche avant de lancer | |
| Prix assumé : recomposer au fil de l'ajustement des couches fait l'aller-retour 1 → 4 | |

### La 0.7.20, dans la foulée

| | |
|---|---|
| **Les titres d'étape passent au souligné** — `Q100_sans_apport`, `Q100_Apport_A1`, `Q100_avec_apports`. **Casse la reprise d'un calage antérieur** : ses étapes portent l'ancienne écriture et ne seront plus reconnues | `STATUT.txt` § 1 |
| **Les plans d'étape s'élaguent, sur demande** — encadré « Ménage du modèle HEC-RAS » à l'onglet 3. Simulation d'abord, confirmation ensuite, et refus si le calage n'a pas conclu. Douze contrôles au banc | `STATUT.txt` § 1 |
| **Le suivi montre les sections déjà calées**, en vert pointillé derrière la paire courante — seules les validées | `STATUT.txt` § 1 |
| **Le thème sombre était cassé, et personne ne l'avait vu** : cinq fonds pris à `alternate-base` (quasi blanc sous Night Mapping), et la piste des jauges jamais dessinée — `QColor` lit `#AARRGGBB`, pas `#RRGGBBAA`. Trois défauts qu'aucun banc n'aurait pris : il a fallu **regarder** | `STATUT.txt` § 1 |
| **Deux défauts du banc de plus** — le mannequin de `QMessageBox`, et un appariement impossible compté comme quatre échecs | `STATUT.txt` § 1 |
| Banc du plugin : **118 contrôles sans modèle, 153 avec**, 0 échec | |

### Ce que la journée du 7 a donné

| | |
|---|---|
| **Le KGE, alpha et beta sont retirés du code** — la figure de convergence des livrables finaux traçait beta sous « Volume atteint (% de la cible) », celle du suivi sortait vide | `STATUT.txt` § 1 et § 2, VOLUME |
| **`tolerance_beta` s'appelle `tolerance_volume`** ; la référence de caractérisation est regelée, identique à l'ancienne privée des trois clés | |
| **L'apport peu identifiable est une réserve non bloquante du Diagnostic** — colonne « Alertes » du classeur, note de synthèse, suivi ; aucun verdict ne bouge | `STATUT.txt` § 2, « L'APPORT EST-IL IDENTIFIABLE ? » |
| **Les deux comptes rendus de contrôle sont une seule boîte** — le recontrôle d'un classeur avait perdu sa poignée | `STATUT.txt` § 6 |
| **Deux bancs passent désormais depuis un clone Linux** — `noyau` (disposition d'un venv) et le garde-fou d'archive (chemins POSIX, qu'il ne voyait pas) | |
| **La note se reconstruit sans qu'on lui porte ses deux figures d'origine** — elles sont lues dans le gabarit | |
| **Trois affirmations de `STATUT.txt` corrigées** : le PDF n'était pas en retard (Version 15), `reprises_max` n'est pas « inerte » mais retiré, l'ordre total est en § 1.2 de la note | |
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

0. **Le `.pdf` de la note, à réexporter à la main** — ouvrir le `.docx`
   (V16) dans Word, *Enregistrer sous > PDF*, et lui remettre une table des
   matières au passage : la reconstruction la perd. Quatre tentatives
   d'export piloté ont échoué, sans que le document y soit pour quelque
   chose.
1. **Réinstaller le plugin depuis `calage_apports_<version>.zip`** —
   Extensions → Installer depuis un ZIP — puis rejouer `test_plugin_qgis.py` :
   sept contrôles neufs depuis le 6. Sans cela le plugin installé porte encore
   le KGE, la figure fausse, et l'onglet 1 d'avant.
2. **Regarder la fenêtre.** Quatorze versions d'interface publiées en un
   jour — 0.7.1 à 0.7.14 — toutes vérifiées au banc, aucune sous les yeux de
   l'utilisateur. En particulier :
   **Entrée ne fait plus rien**, nulle part — c'est le prix assumé du
   désarmement du geste irréversible, et il se voit.
   **Et depuis la 0.7.19, l'onglet 1 a changé de forme** : le bouton d'action
   y est descendu, un encadré en est parti, un autre a changé de nom et de
   place. Les captures sont à jour — mais une capture n'est pas un usage :
   c'est une fenêtre construite hors QGIS, jamais cliquée.
   **À regarder en priorité : les fenêtres étroites.** La zone défilante de
   chaque onglet comprime son contenu au lieu de faire apparaître une barre,
   et c'est le dernier encadré qui encaisse — le plancher posé sur le bouton
   principal ne protège que lui.
3. **Le suivi pendant un vrai calage.** L'état du calage précédent qui ne se
   peint plus, « mort au démarrage » distingué de « pas encore parti », le
   fil qui dit « calage lancé », la question posée si l'on recompose pendant
   qu'un calcul tourne : tout cela est éprouvé sur des états **fabriqués**,
   jamais sur un calage qui tourne. Y regarder aussi la **figure de
   convergence** corrigée, dans `suivi/` et dans `resultats_finaux/`.
4. **Trois garde-fous jamais rencontrés en réel** — volume plancher, apport
   refusé, modèle incohérent. Seul le banc les couvre.

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
