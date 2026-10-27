# CHECKPOINT — Calage des apports (ISL Ingénierie)

## 27 octobre 2026 (soir) : pente absente ajoutée, pas encore publiée

Constat (Ardanavy aval, poste lsso, plan p07) : le bloc unsteady
d'`Affl_02__KOND` n'avait pas de ligne `Flow Hydrograph Slope=` (champ
« EG Slope » laissé vide dans HEC-RAS). `definir_pente` ne savait que
remplacer la ligne : la pente du classeur (0,0044191 m/m) est restée un
avertissement. Le calcul de référence (apports à zéro) a tourné ; le premier
calcul avec débit a planté dans `RasUnsteady.exe` (SNETREAL2, code 157).

Correction dans `src/pilote_hecras.py` : `definir_pente` ajoute la ligne
après `Stage Hydrograph TW Check=` (sinon après la table), puis reconstruit
`self.carte`, car les blocs suivants sont décalés d'une ligne. Banc
`pilote_hecras.py` : 183 [OK]. Non versionnée, non publiée.

## 23 octobre 2026 (nuit) : ergonomie à fond, version 0.9.20

Branche `ergonomie-calage-1023` fusionnée dans `main` (avance rapide) à la
demande de l'utilisateur (« Oui. Push tout »), version 0.9.20, archive
`calage_apports_0.9.20.zip` conforme, poussé. **Publiée** au dépôt PIO le
24/10/2026 à 08 h 40 (`publier.bat`, STATUT=OK). La 0.9.19 a été publiée le
23/10/2026 à 19 h 40.

Demande : « optimise a fond l'ergonomie de calage des apports. Vérifie que les
liens hypertexte sont corrects. Pour le préfixe, propose plutôt "Cours-d'eau -
Q100 - ..." sinon il y aura des doublons quand plusieurs cours d'eau. Test
l'ergonomie et fais les modifications nécessaires dans une branche
spécifique. » Branche locale partie de `main` `b955a11` (0.9.19), non
poussée, non fusionnée, version inchangée.

- **Préfixe « cours d'eau - crue »** : un préfixe qui contient « - » relie
  les étapes par « - » (« Riviere - Q100 - sans_apport »), tiret final
  toléré ; sans « - », le souligné reste (« Q100_sans_apport ») : les
  calages en cours se reprennent à l'identique. Même règle dans
  `src/calage.py` (`titre_etape`) et `plugin.py` (`_titre_etape`).
  Excel : `donnees_calage_Riviere_-_Q100.xlsx` ; dossier proposé :
  `_calage\Riviere - Q100` (caractères interdits par Windows → « _ »).
- **Ligne sous le préfixe** (`label_titres_prefixe`) : titres et Excel à la
  frappe, plus long titre sur 32 caractères, « ⚠ Trop long » avec le compte
  à retirer, « ⚠ Accents » (HEC-RAS met « ? » dans ses résultats).
- **Liens** : liens externes (18 URL, HTTP 200), relatifs, ancres s1 à s11
  vérifiés. Le fil menait le dossier de sortie à l'étape Lancer : les liens
  portent maintenant « rang:champ » et donnent le focus au champ.
- **États** : une seule écriture de l'étape suivante (`_maj_coherence`),
  vraie selon les cibles manquantes ; « Paquet composé » idem.
- **Textes** : nombres à virgule, dates « 24/10/2026 à 03 h 15 », pluriels
  accordés (`compte()`), accents rendus aux messages du noyau, sens du tracé
  en mots, noms d'étape homogènes, légende « calculé », vouvoiement.
- **Disposition** : l'heure du Suivi passe sous ses boutons (débordement de
  9 px à 13 pt sur 720 px) ; le cadre vide des cibles ne répète plus la
  consigne.

Banc sans `--modele` : 413 [OK], 0 [ECHEC] (13 contrôles nouveaux ; les
deux contrôles clavier du fil se sautaient, leur regex ignorait « rang:champ ») ;
`python src/calage.py` et l'autotest du noyau passent ; aperçus clair et
sombre, 9 et 13 pt, 720 et 940 px : aucun défilement de côté.

## 23 octobre 2026 (soir) : esthétique commune (non publié)

Leçons de Rhoé et de Hyétos appliquées, sans changement fonctionnel ni de
version (0.9.18), zip non reconstruit, rien poussé. Quatre commits sur
`main` :

- `79c1ca4` : ruban, jauges et courbe du suivi sur la carte du registre
  commun (`calage_apports/registre.py`, copie identique de Rhoé), dans les
  deux thèmes ; verdict « ✔ » / « ⚠ » ; légende de la courbe au-dessus du
  tracé.
- `931aacf` : à 13 pt sur 720 px, plus de défilement de côté (chemin du
  dossier surveillé coupable, chemins de « Aide et configuration » sur leur
  ligne, barre de préparation à la largeur de son texte).
- `f1bb274` : la barre d'onglets cède la place à la bande commune
  (`calage_apports/bande.py`, copie identique) ; le « ! » d'étape passe sur
  l'entrée de la bande ; « onglet » devient « étape » dans les textes.
- `47d9521` : le banc donne au greffon `offscreen` le dossier des polices
  du système ; les 4 échecs de référence étaient des artefacts de police.

Banc `test_plugin_qgis.py` sans `--modele` : 400 [OK], 0 [ECHEC]
(référence : 4 [ECHEC]). Aperçus remplis, plate-forme windows, clair et
sombre, 9 et 13 pt, 720 et 940 px : aucune page ne défile de côté.

## 23 octobre 2026 : bouton dans la barre « CPN » (non publié)

Le bouton quitte sa barre propre « Calage des apports » pour la barre « CPN »,
commune aux extensions de la maison (`calage_apports/cpn.py`, copie identique
dans chaque extension). Version inchangée (0.9.18), zip non reconstruit.

## Reprendre ici — 11 octobre 2026 : branche `audit-1011-calage`, à fusionner

Correctifs de l'audit du 11/10/2026 et trois décisions de Cédric du même
jour. Sept commits sur la branche locale `audit-1011-calage`, partie de
`main` (`b692ca6`, 0.9.17). Rien n'est poussé ni fusionné. La version reste
0.9.17 dans `metadata.txt` ; l'entrée de changelog est écrite sous le numéro
provisoire 0.9.18.

- **A1** `e51312d` : le ménage de fin de calage ne retire plus le dossier
  de sortie `_calage\<préfixe>` ; seulement `_calage\sections.*`,
  `_calage\injections.*` et les sauvegardes (STATUT § 2.7).
- **A2** `2006a5f` : remplacer un plan homonyme n'efface plus une géométrie
  ou un flux sans plan.
- **A3** `e309bc1` : un fichier HEC-RAS réécrit garde son encodage et ses
  octets (lecture UTF-8 puis cp1252 puis latin-1).
- **A4** `2efe7c3` : le projet chargé est le `.prj` désigné.
- **ASCII = cp1252** `9baee91` : un accent écrit dans un fichier ASCII part
  en cp1252, comme HEC-RAS l'écrit ; le `.rasmap` reste en UTF-8.
- **Écritures de ras-commander** `55debba` : clones, titre du clone de
  géométrie, sorties HDF, essais et cœurs passent par
  `PiloteHecRas._par_ras_commander`, qui rend au `.prj` et aux fichiers leur
  encodage et leurs octets. Mesuré sur un projet fabriqué : avant, la BC
  line « Écluse » de la géométrie clonée devenait `EF BF BD` et l'apport
  sortait du calage sans message.
- **Documentation** : STATUT § 2.7 et § 2.11, ce paragraphe, changelog.

Bancs de la branche : `pilote_hecras.py` 181 [OK], `geometrie.py` 32,
`elaguer_projet.py` 20, `noyau.py` 55 ; pytest 5 réussis (dont les 3 neufs
de `test_projet_hecras.py`) et 11 sous `python-qgis-ltr.bat` ;
`test_plugin_qgis.py` hors écran 372 [OK] et 4 [ECHEC], les mêmes que sur
`main` (géométrie de la fenêtre sous la plateforme `offscreen`). Aucun
calcul HEC-RAS lancé, aucun modèle réel retouché.

**Reste à Cédric** :
1. Relire et fusionner `audit-1011-calage` dans `main` (commit direct, sans PR).
2. Choisir la version (0.9.18 proposé) : `version=` de `metadata.txt` et
   titre de l'entrée de changelog.
3. Construire le zip, publier dans `00-depot_QGIS`, vérifier dans QGIS.
4. Un calage réel sur un modèle à noms accentués, pour voir HEC-RAS
   apparier « Écluse » (non fait : aucun calcul lancé par la branche).

## Reprendre ici — 28 septembre 2026 : 0.9.17, deux défauts vus sur Suhi-Q100

Calage réel Suhi-Q100 (SUHI_ARAN, 12 apports, 18 calculs, 27 h 46, journal
`calage_20260925_174155.log`, poste lsso). Il est **non conforme**, et c'est
juste : SUH06 est en pointe à 104,5 % et SUH07 à 103,9 %, pour 2 % admis.
Le remous des apports aval les a fait dériver après leur calage.

- **Le plan final n'est pas visible sous son nom dans RAS Mapper.** Le
  `.rasmap` avait bien été écrit, mais RAS Mapper l'a réécrit le 28/09 à
  08:15 et a renommé la couche p23 en « Apport_SUH12 ». Il a pris ce nom
  dans les attributs de `Plan Data/Plan Information` du `.p23.hdf`, que
  `conclure()` ne retitrait pas. Correctif :
  `PiloteHecRas._retitrer_resultats_hdf`, appelé par `conclure()`. Il réécrit
  les attributs Plan Name, Plan ShortID, Plan Title et Flow Title, et ne lève
  jamais. Contrôle neuf dans `pilote_hecras.py`, banc vert.
- **L'élagage coché ne fait rien, sans le dire.** C'est voulu : il n'élague
  que sur un calage conforme, parce que la reprise a besoin des plans
  d'étape. Mais rien ne l'annonçait. Correctif : `pont_hecras.py` écrit
  désormais un AVERTISSEMENT quand la case est cochée et le calage non
  conforme.
- Constat écrit dans `0-HECRAS/.../08_constats_mesures.md`.

Bancs : QGIS **381 contrôles, aucun échec** ; `pilote_hecras.py` vert ;
`calage_apports_0.9.17.zip` conforme (le garde-fou a refusé un premier jet
qui citait « SUH12 » dans un commentaire). **Publiée** dans `00-depot_QGIS`
(STATUT=OK), vérifiée par `verifier_dans_qgis.py`, synchro L lancée.

**Non fait** : le modèle réel n'est pas retouché (p23.hdf et `.rasmap` portent encore
« Apport_SUH12 ») ; affichage dans RAS Mapper toujours pas vérifié à
l'écran.

## Reprendre ici — 24 septembre 2026 (après-midi) : 0.9.16

Trois demandes utilisateur après la publication de la 0.9.15 :

- **« Importer des hydrogrammes d'un calcul précédent »** remplace
  « Reprendre un Excel… » (`noyau.importer_hydrogrammes`) : cibles par
  en-tête `Cible_<section>` avec `Temps_h`, pentes par nom d'apport, dans
  l'Excel de ce calcul, rien d'autre. Aucune cible commune → rien d'écrit,
  les deux listes nommées ; sinon le compte rendu (dans la page) nomme
  importés, restés vides, ignorés, pentes. La reprise de classeur disparaît
  avec lui : reprendre un calcul = recomposer, puis importer.
- **Plus de couches PK** : le PK s'étiquette sur les couches de base ; celles
  de la 0.9.15 partent à la composition suivante.
- **Plus de changement d'onglet automatique** après composition et lancement.

Bancs : QGIS **381 contrôles, aucun échec** ; noyau vert (9 contrôles
d'import) ; `calage_apports_0.9.16.zip` conforme, garde-fou vert.
**Publiée** dans `00-depot_QGIS` et vérifiée par `verifier_dans_qgis.py`
(profil jetable) ; commit sur `main`. **Non fait** : fenêtre regardée à
l'écran. Juste après, `D:\1-Python` est renommé `D:\1-Dev` par la session
« 1-python-ee » : relire `D:\1-Dev\CLAUDE.md` avant de reprendre.

## Reprendre ici — 24 septembre 2026 : 0.9.15, la composition redevient un clic

Le dépôt a déménagé le même jour :
`D:\1-Python\1-Utilitaires\1.1-Plugins_QGIS\01-Calage_apports`, dépôt
d'extensions `..\00-depot_QGIS` (table ancien → nouveau dans
`D:\1-Python\CLAUDE.md`). Trois demandes utilisateur, plan validé avant
d'écrire.

- **Plus de recomposition automatique.** Taper « Q100 » en marquant une pause
  composait « Q1 » : `_calage\Q1\`, classeur, JSON, SHP, et la fenêtre
  basculait dessus. Minuteur et ses cinq méthodes retirés ; seul le bouton
  « Valider la géométrie et générer le fichier des hydrogrammes » compose.
- **Un « ! » rouge** sur chaque champ périmé et sur le titre de son onglet
  (`_temoin`, `_avec_temoin`, `_maj_temoins`), infobulle avec les deux
  valeurs ; `_COMPARES` passe de 11 à 22 clés ; « Paquet composé » ne compte
  plus et **le lancement est refusé** tant qu'un « ! » reste allumé. Règle :
  un écart est un champ qui a **bougé depuis l'arrivée du paquet**
  (`_valeurs_au_paquet`, pris par le setter de `classeur`) — sinon un Excel
  repris sans son modèle n'aurait jamais pu se lancer.
- **Couches PK remplacées**, marquées par `MARQUE_PK`, au style des couches
  de base, étiquette « nom — PK », posées sous elles. Piège mesuré :
  `loadNamedStyle` efface les propriétés personnalisées — marque posée après
  le style.
- Au passage : la case d'élagage cochée après composition était ignorée —
  écrite au lancement, relue à la reprise. Aide, README, LISEZMOI : l'ancien
  bouton « Contrôle paramétrage / en bas de la fenêtre » remplacé.

Bancs : QGIS **376 contrôles, aucun échec** (363 avant) ; noyau vert ;
`faire_zip.py` conforme, `calage_apports_0.9.15.zip` construit ; garde-fou
d'archive vert. **Publiée** dans `00-depot_QGIS` (`publier.py` STATUT=OK) et
vérifiée par `verifier_dans_qgis.py` dans un profil jetable : installée par
la boîte de QGIS, version lue, mise à jour proposée, `plugin.py` importé.
Commit sur `main`, sans branche (demande utilisateur). **Non fait** : fenêtre
regardée à l'écran (« ! » dans les onglets, thème sombre, 13 pt) ; banc
`--modele`. Par quoi reprendre : (1) mettre à jour l'extension dans le
profil ISL depuis le gestionnaire et regarder la fenêtre ; (2) la limite de
la règle : une reprise sur une fenêtre qui décrit déjà un autre modèle ne
s'annonce pas.

## Reprendre ici — 22 septembre 2026 : la couverture comptait Dt deux fois

Calage réel **Aran-Q100** (SUHI_ARAN, 11 apports ARA07→ARA17, 13 calculs,
31 h 49 de machine, journal `calage_20260920_193228.log`) rendu **2/11
conformes** à 99,3–100,5 % de volume : neuf « la fenetre de calcul ne couvre
que 45 à 90 % », plus « le decalage (-11 h) excede la fenetre jugee (9,5 h) »
sur ARA17. **Faux positifs.** Le modèle répond 4,6 à 11 h *avant* les cibles
(Dt négatif) ; `criteres.diagnostiquer` rognait la fenêtre jugée sur
l'étendue brute des deux axes puis retirait encore |Dt| d'un côté — Dt compté
deux fois. Le calcul couvrait la fenêtre `[f0, f1]` en entier.

- **`src/criteres.py`** : avec une fenêtre, la cible est lue sur `[f0c, f1c]`
  et le calcul sur `[f0c + Dt, f1c + Dt]`, bornés par ce que chaque série
  porte ; la garde « décalage plus long que la fenêtre » devient
  `|Dt| >= fin - debut` explicitement (même valeur qu'avant sans fenêtre).
  Auto-test § 7 ter bis. Sans fenêtre : rien ne change.
- **`src/calage.py`** : le plafond du plan de référence se compare à la
  durée *en vigueur* (None de `limiter_duree` = plan inchangé), et **alerte**
  quand la perte dépasse `marge_duree_h` — le journal se taisait dès la
  deuxième étape (neuf étapes bornées à 20,5 h pour 21,2–23,3 h voulues).
- **`src/reference_calage_fictif.json`** refigé : seuls `rapport_volume`
  (≤ 0,02 %) et `part_cible_jugee` bougent — le volume est intégré sur toute
  la fenêtre au lieu de la fenêtre amputée de |Dt|.

**Preuve sur les séries du suivi** (`avancement.json` + cibles du classeur,
mêmes fenêtres et Dt que le journal) : ancien critère 9 bloquantes, nouveau
**0 bloquante, 11/11 convergent, volumes 99,9–100,1 %**. Restent deux
réserves non bloquantes vraies : 0,3 h (ARA15) et 0,5 h (ARA17) de fenêtre
non simulées — le plan de référence désigné était **p12**, plan d'étape du
calage précédent déjà raccourci à 20 h 30 (la reprise cherchait
« Ara-Q100-V1_Apport_ARA06 », le préfixe ayant perdu un « n »). Pour un
rejeu : repartir de p07 ou p14 (48 h), ou rallonger `Simulation Date` de p12.
Les CL amont (BC_SUH_01, 200 × 10 min = 33 h) le permettent sans retouche.

**Non fait** : les livrables réels ne sont pas régénérés (h5py absent de ce
poste ; `reconstruire_livrables.py --plan 26` sur le poste de calcul le fait
sans recalcul). La dérive de Dt le long de l'axe (6,4 h) reste une vraie
question de base de temps des cibles.

**0.9.7 — les cœurs se proposent (demande utilisateur, même jour).** Lu dans
le `.p26.hdf` : « CPU Affinity ON (Performance Cores 0,2,4,6) »,
`Maximum number of cores = 4` — HEC-RAS employait déjà les quatre cœurs P du
poste de calcul, quoi que le plan demande (`UNET D2 Cores = 0, 0, 8`).
Vérifié sur GitHub (v0.99.1 → v0.102.0) : `compute_plan(num_cores=)` appelle
`RasPlan.set_num_cores`, qui réécrit **toutes** les lignes `UNET D1 Cores=`,
`UNET D2 Cores=`, `PS Cores=` du plan calculé avant le calcul ; 0 = tous ;
docstring « 2 à 8 » ; limite : relecture/réécriture UTF-8 `errors="replace"`.

- **`calage_apports/materiel.py`** (neuf, repris de Sensi, ctypes seul) :
  inventaire du poste, `suggestion` = cœurs utiles (P si hybride) plafonnés
  à 8, `conseil()` qui dit ce que le plan demande et si cocher changera
  quelque chose. Auto-test `__main__`.
- **Lancer** : groupe « Calcul HEC-RAS » entre la conservation des plans
  d'étape et la configuration complète. Case décochée « Demander N cœurs à
  HEC-RAS pour chaque calcul », étiquette sous elle, suit le plan choisi.
  Le récapitulatif annonce les cœurs quand la case est cochée.
- **Paramètre `Coeurs_par_calcul`** (0 = plan inchangé) : écrit au
  lancement avec les autres réglages, relu à la reprise d'un classeur,
  contrôlé (entier 0–64), défaut dans `preparer_classeur`, template,
  commentaire `style_classeur`. `lister_projet_hecras` rend `coeurs_2d`.
- **Chaîne** : `PiloteHecRas(coeurs=)`, `calculer()` passe `num_cores` ;
  `preparer()` journalise « coeurs demandes … (plan de reference demande
  « UNET D2 Cores = tous, 8 ») ». Le plan de référence n'est jamais touché.

Banc QGIS : **354 contrôles, aucun échec, sortie 0** (cinq neufs). Ce poste
(Core Ultra 5, 2 P) propose 2. **Non fait** : aucun calage réel relancé avec
la case cochée ; fenêtre non regardée ; plafond 8 = recommandation citée.
Retour écrit dans `0-Ergonomie/retours/CALAGE_APPORTS.md`.

**0.9.8 — l'Excel dès le préfixe (demande utilisateur, même jour).** La
composition automatique exigeait le dossier de sortie, champ de l'étape
Lancer, vide par défaut : à la saisie du préfixe (étape Objectifs), rien ne
se composait. `_proposer_dossier_sortie()` remplit le champ avec
`<modèle>\_calage\<préfixe>` dès que modèle et préfixe sont connus (au
chargement du projet et à chaque frappe du préfixe, connecté avant
`_maj_resume`), et ne remplace jamais une valeur saisie à la main (mémoire
de la dernière proposition). Infobulle du champ et texte d'attente du
classeur mis à jour. Banc QGIS : **357 contrôles, aucun échec, sortie 0**
(trois neufs). Non fait : aucun modèle réel chargé au banc — la chaîne
préfixe → dossier → composition → Excel est éprouvée jusqu'au dossier.

**0.9.9 — la recomposition automatique plantait sur tout poste.** Erreur
vue chez lsso le 22/09, deux fois, après réinstallation :
`_composer_et_controler() got an unexpected keyword argument
'ecrire_geometrie'` à la ligne 1948 (le minuteur de recomposition).
**Première explication, fausse** : une classe d'avant la 0.9.5 encore
chargée dans QGIS — réfutée par la récidive après redémarrage. **Cause
réelle** : le décorateur `avec_sablier` enveloppait la méthode avec
`def enveloppe(self)`, sans `*args, **kwargs` ; la méthode a reçu deux
mots-clés en 0.9.5 et le minuteur l'appelle avec — `functools.wraps`
donnait à l'enveloppe le nom de la méthode, d'où un message qui accusait
celle-ci. Latent depuis la 0.9.5, jamais exercé : le banc n'appelait la
méthode que sans argument, et la recomposition automatique « n'a jamais
tourné contre un vrai modèle » (CHECKPOINT 0.9.6). Correctif : l'enveloppe
transmet les arguments. Le banc appelle désormais la méthode exactement
comme le minuteur, à travers le sablier, puis vérifie que ni le verrou de
composition ni le sablier ne restent posés.

**Et le premier correctif tuait le banc** — code 9, sans trace, deux fois,
`faulthandler` muet. Deux méthodes au sablier sont branchées sur
`clicked`, qui émet un booléen : avec `self` seul, PyQt retombait tout seul
sur l'appel sans argument ; avec `*args`, l'enveloppe passait le booléen à
`_charger_couches_modele` / `_recontroler_classeur`, qui le refusaient — et
une exception dans un slot PyQt ne fait pas une boîte, elle tue le
processus (qFatal). L'enveloppe **tronque désormais les positionnels au
nombre que la méthode déclare** (`inspect.signature`), le repli que PyQt
faisait pour nous. Éprouvé hors QGIS sur un mannequin (clic avalé,
mots-clés transmis, `*args` intact, curseur rendu) et au banc. Banc QGIS :
**361 contrôles, aucun échec, sortie 0** — dont « le sablier survit à un
vrai clic », le contrôle existant qui mourait avec `*args`. La sortie
tamponnée du banc masque la ligne exacte de la mort : lancer le banc avec
`python -u` quand un processus s'arrête sans trace. Le « code 127 sans
trace » du 21/09 (ré-entrance) relève sans doute du même mécanisme.
Le texte d'attente de l'étape Lancer ne renvoie plus à « Écrire dans la
géométrie HEC-RAS en bas de la fenêtre » (bouton à l'étape Modèle depuis
la 0.9.6) : une seule phrase, `ATTENTE_PAQUET`, dite aux deux endroits.

**0.9.10 — un bouton, un dossier, un nom (trois demandes du poste de
calcul, même jour).** « Ouvrir dans Excel » restait gris après le préfixe :
la composition automatique renonce en silence dès qu'un préalable manque.
Décisions de l'utilisateur, qui défont celles du 20-21/09 : **un seul
bouton** « Valider la géométrie et générer le fichier des hydrogrammes »,
**sous le préfixe** (groupe Hydrogrammes cibles), branché sur
`_composer_et_controler` — écrire, composer, contrôler, compte rendu ; gris
tant qu'un préalable manque (`_etapes_avant_controle` compte désormais
l'axe, le préfixe et le dossier), refus explicite au clic. Le bouton
« Écrire dans la géométrie HEC-RAS » de l'étape Modèle et `_ecrire_seulement`
disparaissent. Le **dossier de sortie** remonte juste au-dessus de
« Hydrogrammes cibles » (étape Paramètres) ; l'étape Lancer garde la
conservation des plans, les cœurs, la configuration, le lancement.
L'onglet **« 2. Objectifs » devient « 2. Paramètres »** ; les refus disent
« Étape Paramètres : … » au lieu d'un « Onglet 3 » périmé. Banc : ordre des
groupes des deux onglets, bouton sous le préfixe, clic sans modèle → refus,
navigation Alt depuis l'étape Paramètres. Banc QGIS : **363 contrôles, aucun
échec, sortie 0** ; la page Paramètres tient dans la vue la plus étroite
(400 px pour 675) malgré le libellé de 60 caractères. Non fait : fenêtre non
regardée, aucun vrai modèle au banc.

**Mesure du 22/09 après-midi — calage réel Aran-Q20 avec la 0.9.10.** Lancé
11:21 depuis le plugin, plan de référence **p04** (48 h, fenêtre pleine),
16 apports, case des cœurs **cochée : 8 demandés**. Le poste n'est pas le
portable du Q100 : `p27.hdf` dit « Performance Cores 0,2,…,62 » (32 cœurs
de même classe) et **« Maximum number of cores = 8 »** — un nombre demandé
est honoré ; sur le Q100, « tous » n'avait donné que 4 sur 4 P. Référence :
48 h simulées en **1 h 48** (26,4 × le temps réel ; Q100 : 7,4 ×, autre crue).
Calendrier 17,2 → 48,4 h, sans plafond. ARA02 : essai 1, 100,0/100,0/100,0 %,
60 min. ARA03 en cours (Dt −3,0 h, fenêtre 0–13,8 h, 18,2 h simulées).
Suivi estimé par la chaîne : fin vers 05:07 le 23/09. `materiel.conseil`
(0.9.11) ne prétend plus que « tous » prend tous les processeurs logiques.
Le plafond 8 reste non mesuré : sur cette station, 16 pourrait aller plus
vite — à essayer sur un plan seul, jamais pendant un calage.

**Correctif du 23/09 matin — 0.9.12, un refus de composer ne met plus le
classeur de côté.** La CI, bloquée du 20 au 23 septembre par le quota GitHub
Actions (2 000 min/mois, épuisées le 19), repart après relèvement du budget
et révèle un banc `noyau.py` rouge depuis la 0.9.2 : `preparer_classeur`
renommait l'ancien classeur en `.precedent.xlsx` **avant** le garde-fou
« Temps_h », si bien qu'un refus faisait disparaître le fichier canonique
alors que le message promettait « le classeur n'est pas touché ». Mise de
côté déplacée juste avant l'écriture ; le banc vérifie qu'aucune copie
`.precedent` n'apparaît sur un refus (46 contrôles OK en local avec
venv-hecras ; PR #6 fusionnée, CI verte). Suite en 0.9.13 : `STATUT.txt` et
le changelog de `metadata.txt` remis à niveau (0.9.7 à 0.9.13), PR #4
rebasée et fusionnée.

**Intégration du 23/09 — 0.9.13, la recherche des interpréteurs Python quitte
le fil graphique.** PR #4 (Codex, 20/09, brouillon en conflit) rebasée sur la
0.9.12 : un seul conflit, la ligne d'import de `plugin.py` (`materiel` ajouté
en 0.9.7) ; ses retouches documentaires, déjà dans main, abandonnées.
`installation.TacheRecherchePython` porte la recherche des candidats
(`noyau.pythons_candidats(journal, annule)`), le choix reste sur le fil
graphique, le résultat attend la réouverture de la fenêtre, aucune
installation implicite après annulation ou erreur. Vérifié : banc `noyau.py`
46 OK, banc QGIS local **363 contrôles, aucun échec** (python-qgis-ltr),
pytest hors QGIS 2 tests, CI verte (les trois scénarios QGIS natifs tournent
dans le conteneur). Fusion en rebase, branches distantes fusionnées
supprimées : il ne reste que `main`. `STATUT.txt` et le changelog de
`metadata.txt` rattrapent 0.9.7 à 0.9.13 ; la règle 2.5 dit 32, plus 30.
Le stash du 18/09 (« Reprendre les hydrogrammes d'un autre Excel », absent
de main) a été abandonné le 23/09 à la demande de l'utilisateur ; commit
`defe62ee`, récupérable par `git stash apply` tant que git ne l'a pas purgé.

## État précédent — 21 septembre 2026 : 0.9.6, le bouton rentre à l'étape 1

Banc QGIS : **347 contrôles, aucun échec, sortie 0**. Plugin installé et
ouvert dans le QGIS du poste ; version lue : 0.9.6.

- **Le bouton rejoint l'étape « Modèle »**, sous les couches qu'il écrit.
  Puisqu'il ne compose plus rien, ce qu'il consomme tient tout entier dans
  cet onglet — la raison de sa permanence (0.7.24) a disparu. Compte rendu
  dans la page ; échec en boîte.
- **Correctif important de la 0.9.5** : la recomposition automatique pouvait
  se **ré-entrer** — le minuteur partait pendant une composition, deux
  écritures concurrentes, et le processus s'arrêtait **sans trace**
  (code 127, reproduit au banc). Verrou posé, et aucun rendez-vous tant que
  les préalables ne sont pas tous là.

**Toujours pas prouvé** : la recomposition automatique n'a jamais tourné
contre un vrai modèle. Le banc éprouve la programmation, les refus et le
bandeau — pas un cycle complet écran → fichiers. Premier point de recette.

## État précédent — 21 septembre 2026 : 0.9.5, la composition est automatique

Banc QGIS : **345 contrôles, aucun échec**. Plugin **installé et ouvert** dans
le QGIS du poste ; version lue par QGIS : 0.9.5.

« Contrôle paramétrage » faisait trois choses. Les deux réversibles —
composer, contrôler — se font **seules**, 1,5 s après le dernier changement,
et seulement s'il y a un écart entre l'écran et le paquet. La troisième —
**écrire dans la géométrie HEC-RAS** — reste un bouton, qui porte enfin ce
nom. Le bandeau nomme ce qui a été reporté.

Conséquence assumée : la sauvegarde du classeur passe de l'horodatage à **un
seul niveau** (`.precedent.xlsx`). Automatique, un horodatage par frappe
enterrerait le dossier de sortie.

**Ce qui n'est pas prouvé** : la recomposition automatique n'a **jamais tourné
contre un vrai modèle** — le banc éprouve sa programmation, son refus pendant
un calage et son bandeau, pas un cycle complet. C'est le premier point de
recette.

Par quoi reprendre : (1) **charger un modèle et changer un réglage** — vérifier
que le paquet se recompose et que le bandeau le dit ; (2) ouvrir **RAS Mapper**
sur un calage abouti (0.9.3, jamais vu à l'écran) ; (3) thème clair et 13 pt ;
(4) refaire les six captures ; (5) le rattrapage des plans déjà calculés.

## État précédent — 21 septembre 2026 : 0.9.4, quatre demandes de plus

Banc QGIS : **337 contrôles, aucun échec**.

- **Le préfixe rejoint le groupe du fichier qu'il nomme**, renommé
  « Hydrogrammes cibles ». La raison de l'avoir tenu dehors depuis la 0.8.4
  — « le groupe voisin se grise » — a été **vérifiée** et n'en est plus une.
- **L'emprise 2D** : contour rouge, aucun remplissage. Elle masquait le
  maillage et les sections sous un aplat aléatoire.
- **Les listes d'étapes de l'aide** décrivaient encore six rubriques avec
  « Sorties » en deuxième : le dossier de sortie vient **après** les
  objectifs.
- **Changer le préfixe puis recomposer** est annoncé **avant** le clic.
  Mesuré : rien n'est supprimé, l'ancien classeur garde ses cibles — mais
  le neuf naît vide, ce qui à l'écran ne se distingue pas d'une perte.

**DEMANDE OUVERTE, non traitée** — supprimer le bouton « Contrôle
paramétrage » et faire le contrôle automatiquement, en annonçant ce qui a
changé. Non fait à dessein : ce bouton porte **le seul geste irréversible
de la fenêtre**, l'écriture dans la géométrie HEC-RAS. Le rendre
automatique réécrirait le modèle du client à chaque frappe. La découpe à
trancher est dans STATUT.txt § 1.

## État précédent — 21 septembre 2026 : 0.9.3, RAS Mapper voit le résultat

La demande laissée ouverte par la 0.9.2 est traitée. **Cause trouvée sur
deux modèles réels** : l'arbre *Results* de RAS Mapper ne parcourt pas le
dossier, il liste ce que le `.rasmap` déclare — et ras-commander ne l'écrit
jamais. Sur le modèle de l'affaire, **treize plans** calculés par la chaîne
portaient 300 à 420 Mo de résultats et le `.rasmap` n'en déclarait **aucun**.

`conclure()` inscrit maintenant le plan final dans le bloc `<Results>`.
Bancs : `pilote_hecras.py` vert (neuf contrôles neufs), banc QGIS 329,
`calage.py` vert, plus un essai sur une **copie du `.rasmap` réel**.

Par quoi reprendre : (1) **ouvrir RAS Mapper** sur un calage abouti — c'est
la seule chose que je n'ai pas pu vérifier ; (2) décider d'un **rattrapage**
pour les treize plans déjà calculés, aujourd'hui invisibles ; (3) refaire
les six captures, toujours de la 0.8.2 ; (4) regarder la fenêtre en thème
clair et à 13 pt ; (5) les six échecs du banc `--modele`, antérieurs.

## État précédent — 21 septembre 2026 : 0.9.2, et une demande ouverte

Banc QGIS : **329 contrôles, aucun échec**.

- **Recomposer ne perd plus rien** : l'ancien classeur est mis de côté,
  horodaté, comme la géométrie. Le nom canonique ne bouge pas.
- **Contrôle de cohérence permanent** : onze réglages comparés à chaque
  modification entre l'écran et le paquet composé, l'écart nommé avec les
  deux valeurs. C'est le paquet que le calage lit.
- **Le journal en cours dans le Suivi**, repliable et déroulant, à côté de
  l'encadré des alertes qui ne retient que les mots d'alerte.

**DEMANDE OUVERTE, non traitée dans cette version** — après un calage
réussi, le plan « <préfixe>_avec_apports » existe mais **RAS Mapper ne
montre pas ses résultats**. Le plan final n'est pas un clone : c'est la
dernière étape **retitrée**. RAS Mapper nomme son dossier de résultats
d'après le `Short Identifier`, et la base `0-HECRAS` note que
ras-commander **ne met jamais le `.rasmap` à jour**. À instruire sur un
modèle réel **avec résultats** — c'est par là qu'il faut reprendre.

## État précédent — 20 septembre 2026 (suite) : 0.9.1, la fenêtre regardée

Plugin **installé dans le profil ISL et ouvert** dans QGIS 3.44.8-Solothurn.
Banc QGIS : **310 contrôles, aucun échec**.

- **Onglet Objectifs dans l'ordre du parcours** : précision, la ligne qui
  demande de composer — **sortie du groupe qu'elle débloque** —, l'Excel,
  puis ce que portent les cibles.
- **Une barre « Préparation n/4 »** à côté de « Contrôle paramétrage » :
  la saisie avant lancement, pas le calage. Le fil conducteur ne dit plus
  le compte, qui se lisait deux fois.
- **Trois défauts que seule la fenêtre réelle a montrés** : QGIS ne savait
  plus lire la version du plugin (changelog non indenté → `metadata.txt`
  illisible par `configparser`, `__error__` depuis la 0.8.5) ; le
  récapitulatif de reprise restait vide à l'ouverture ; le compte était
  dit deux fois. `faire_zip.py` refuse maintenant une archive dont QGIS ne
  lirait pas la version.

Par quoi reprendre : (1) **refaire les six captures** — elles datent de la
0.8.2 ; (2) regarder la fenêtre en **thème clair**, à **13 pt**, et en
petite fenêtre — seul le sombre à 940 × 780 a été vu ; (3) **lancer un
calage** : rien de la chaîne n'a tourné aujourd'hui ; (4) instruire les six
échecs du banc `--modele`, antérieurs ; (5) `pont_hecras.py autotest`.

## État précédent — 20 septembre 2026 : 0.9.0, trois demandes utilisateur

Cinq onglets, la reprise annoncée avant le clic, les paramètres hors du
classeur. **Banc QGIS rejoué sur le poste** (`C:\Program Files\QGIS\LTR`) :
**297 contrôles, aucun échec** — c'est le premier passage depuis la 0.8.4, et
il solde la dette « banc non rejoué » qui traînait depuis le 17 septembre.

- **L'onglet « Sorties » disparaît.** Ses groupes rejoignent « Lancer », après
  « Apports à déterminer » ; le préfixe de scénario quitte « Objectifs » pour
  se poser au-dessus du bouton. L'ordre de la page est celui de la décision, et
  c'est l'ordre que le banc éprouve.
- **Un récapitulatif au-dessus du bouton** dit d'où le calage repart, de quel
  plan d'étape — nommé avec son préfixe —, ce qui est tenu pour calé et ce qui
  sera calculé. La boîte de reprise ne s'ouvrait pas après un **échec** : rien
  n'étant « validé » en aval, rien ne se perdait, donc rien ne se disait.
- **Les paramètres quittent l'Excel** pour `<nom du classeur>.json`, porté par
  un module unique, `src/parametres.py` (chaîne à 10 modules). Un classeur
  d'avant est encore lu par sa feuille — vérifié sur le classeur réel
  d'Aran-Q100 : 40 paramètres, contrôle sans erreur.

Par quoi reprendre : (1) **regarder la fenêtre** — rien n'a été vu à l'écran,
tout est mesuré au banc ; (2) **refaire les six captures**
(`captures_plugin.py`), celle dite « onglet 2 Sorties » montrant un onglet
disparu ; (3) mesurer « Lancer » **rempli** à 13 pt sur petite fenêtre — sept
groupes désormais ; (4) **instruire les six échecs du banc avec `--modele`**,
reproduits à l'identique sur le commit précédent : ils sont antérieurs à ce
chantier ; (5) installer le ZIP **0.9.0** dans le profil ISL et relancer le
calage Aran-Q100 (son classeur n'a pas de JSON : c'est le chemin de
compatibilité qui servira) ; (6) `pont_hecras.py autotest` sur le poste ;
(7) la [PR #4](https://github.com/CedricPerrin/Calage_apports/pull/4), toujours
bloquée par une CI sans exécuteur.

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

Point de reprise pour ouvrir une nouvelle conversation avec un contexte
minimal. L'état courant et les règles en vigueur restent dans `STATUT.txt` ;
ce fichier ne dit que **où on en est** et **par quoi reprendre**.

## Reprendre ici — 20 septembre 2026 : intégration des lots UX B/C

L’utilisateur demande la fusion de la PR #3 dans `main`. La recette se fait depuis ces sources, avec les preuves et responsables de `docs/UX_ISL.md`. L’exécution par lots autorise C9 et C16. Les effets du contrôle sont visibles ; création du venv, pip et vérification passent par `QgsTask`. La cible confirmée est figée et la préférence Python n’est publiée qu’après succès. Voir [implémentation, bancs et limites](docs/UX_ISL.md).

La recette automatisée est maintenant verte : noyau complet ; QGIS 3.44.7 / Qt 5.15.13, quatre tests du gestionnaire/cycle, quatre tests cible/worker et 299 contrôles du banc historique. Les phases pip sont simulées, le gestionnaire et les widgets sont réels. Dix correspondances ISL sont contrôlées en CI. Voir `docs/UX_ISL.md` pour le lien de preuve et la portée du harnais Linux (sonde PID POSIX, pas tasklist Windows).

Prochaine étape : recette sur le poste Windows ISL, installation réelle via son réseau, DPI/thèmes/lecteur d’écran et modèle représentatif. Aucun nouveau ZIP de diffusion avant cette recette ; aucun calcul métier ni archive 0.8.6 remplacé. Nouveaux fichiers : workflow `.github/workflows/ux-qgis.yml`, test `src/test_installation_qgis.py`, contrôle `tools/check_isl_identity.py` et contrat `docs/isl-identity-contract.json` ; banc historique rendu reproductible sous Linux.

## État précédent — 18 septembre 2026 (suite) : 0.8.6, la revue de qualité fusionnée

La branche `claude/ponytail-lycxeg` (revue de qualité de la 0.8.4, 17/09) est
fusionnée dans `main` — merge `e402072` — et l'archive refaite sous un nom
neuf, `calage_apports_0.8.6.zip` : la 0.8.5 était déjà sur GitHub, et une
archive dont le contenu change porte un autre nom. Aucune promesse ne change.

**Bancs :** `noyau.py` vert ici ; `pilote_hecras.py` s'arrête à l'import de
`ras-commander`, absent de ce clone ; `faire_zip.py` conforme, garde-fou vert ;
**banc QGIS toujours non rejoué**.

Par quoi reprendre : (1) **rejouer `test_plugin_qgis.py`** — 301 contrôles
attendus, dont trois de la revue et vingt-trois de la 0.8.5 jamais vus sous
QGIS ; (2) `pont_hecras.py autotest` sur le poste ; (3) installer le ZIP
**0.8.6** dans le profil ISL ; (4) le reste de la liste de la 0.8.5
ci-dessous — Night Mapping avec un Suivi rempli, captures, Accessibility
Insights, décisions C9 et C16 ; (5) les deux points que la revue laisse à
trancher (`STATUT.txt` § 6) : « HEC-RAS ouvert = refus » n'existe que dans le
plugin ; `suivi/` et les journaux sont partagés entre scénarios d'un même
dossier de sortie. La branche `claude/ponytail-lycxeg` peut être supprimée
sur GitHub : tout est dans `main`.

## État précédent — 18 septembre 2026 : 0.8.5, la relecture ergonomique livrée

La relecture du 17 septembre (`docs/ergonomie_2026-09-17.md`, grille du
dépôt `ergonomie`) validée par l'utilisateur, et ses correctifs — écrits
**sans QGIS**, depuis un clone Linux : le banc n'a pas tourné, le reste a
été mesuré autrement.

- **Thème sombre** : ruban, jauges, courbe et colonne Statut du Suivi
  passent par `interface.couleur()` — même table que les textes HTML ; le
  filet de la bannière suit. Ils gardaient les couleurs du clair sur Night
  Mapping (ardoise 2,3:1, rouge 1,8:1) : la recette du 11 avait mesuré ses
  scénarios sombres sur un projet **vide**.
- **Quatre questions Oui/Non** — pas trois : la relecture avait manqué
  « Chaîne de calage introuvable » — deviennent `confirmer()` : des verbes,
  le refus par défaut, Échap et croix compris.
- **Police** : les widgets peints dessinent en fraction de leur police et
  recalculent leur hauteur au `FontChange` ; noms et descriptions
  accessibles à chaque `actualiser()`.
- Teal sombre pour les textes, liens du fil conducteur au clavier,
  « fichier .prj » dans trois refus, boîtes du contrôle nommées comme le
  bouton, « (obligatoire) » au libellé du préfixe, `ONGLET_AIDE`, note HIG
  580 px, et `faire_zip.py` refuse un LISEZMOI qui cite une autre version.
- **Trouvé au passage** : `self.sizePolicy().Expanding` cassait sous PyQt6
  pur — forme qualifiée posée.

**Bancs : banc QGIS NON REJOUÉ** — 23 contrôles neufs, **301 attendus**.
À la place : `py_compile` des quatre `.py` touchés ; `faire_zip.py`
« archive conforme » ; garde-fou d'archive vert ; les trois widgets peints
dessinés hors écran sous PyQt6 6.11 (shim `qgis`) en clair et en sombre à
10 et 13 pt — couleurs remappées présentes, hauteurs qui suivent — et
`confirmer()` éprouvée (défaut, échappement, retour sans clic).

Par quoi reprendre : (1) **rejouer `test_plugin_qgis.py`** sous le Python
de QGIS — rien de la 0.8.5 n'a été vu tourner sous QGIS ; (2) regarder
l'onglet Suivi **rempli** en Night Mapping ; (3) refaire les six captures
(`captures_plugin.py`), qui datent de la 0.8.2 ; (4) installer le ZIP 0.8.5
dans le profil ISL ; (5) Accessibility Insights FastPass sur la fenêtre ;
(6) deux décisions laissées ouvertes — C9, dire au fil conducteur que le
bouton écrit dans la géométrie, et C16, un `QProgressDialog` sous
« Installer… » ; (7) la branche `claude/ponytail-lycxeg` — revue de
qualité de la 0.8.4, commit `0fd1b9a` du 17/09 — a été **fusionnée dans
`main` le 18 septembre** : voir la section suivante, et `STATUT.txt` § 6
pour les deux points qu'elle laisse à trancher.

## État précédent — 17 septembre 2026 : revue de qualité de la 0.8.4, fusionnée le 18

La 0.8.4 est commitée (`f4aaf6e`, `main`). Sur la branche
`claude/ponytail-lycxeg`, un passage `/simplify` : quatre relectures
(réutilisation, simplification, efficacité, profondeur du correctif), puis
les correctifs retenus. Aucune promesse de la 0.8.4 ne change ; `STATUT.txt`
§ 1 (entrée du 17/09, items 3, 5, 8 et 9) dit ce qui a bougé et ce qui a
été écarté.

- **`DialogueParametrage.classeur` est une propriété** : son setter
  rafraîchit le groupe « Excel des hydrogrammes objectifs » — trois
  affectations, un seul rafraîchissement.
- **Le Suivi ne relit le journal que s'il a changé** (un `stat` par tour) ;
  `noyau.dernier_journal` le retrouve, à côté de `lancer_calage` qui le nomme.
- **`_sans_tableau_des_temps`** coupe le compte rendu HEC-RAS à l'en-tête du
  tableau des temps ; plus de liste de mots d'échec.
- **`plan_fenetre_pleine` n'est passé qu'en reprise** ;
  `PiloteHecRas._duree_borne_h()` porte la borne et le banc l'éprouve.
- **Le recadencement des cibles dit `AVERTISSEMENT`** depuis la chaîne.

**À faire sur le poste** : rejouer `test_plugin_qgis.py` (QGIS) et
`pont_hecras.py autotest` (h5py). L'archive a été refaite en **0.8.6** à la
fusion dans `main`, le 18 septembre.
Deux points ouverts à trancher : la règle « HEC-RAS ouvert = refus » ne vit
que dans le plugin ; `suivi/`, `resultats_finaux/` et les journaux restent
partagés entre les scénarios d'un même dossier de sortie.

## État précédent — 14 septembre 2026 : 0.8.4 (commit `f4aaf6e`)

Six demandes utilisateur après un calage réel repris — Suhihandia, reprise à
SUH12 — et le constat qui les a fait naître : ce calage s'arrête au calcul de
référence, et rien de ce qui l'annonçait n'était visible à l'écran.

- **Le préfixe de scénario nomme l'Excel** : `donnees_calage_Q100.xlsx`
  (`noyau.nom_classeur`). Deux scénarios d'un même dossier de sortie ont deux
  classeurs, et composer l'un n'écrase plus l'autre. Préfixe vide = le nom
  d'avant. Aucune boîte « voulez-vous écraser ? » : un préfixe neuf est un
  fichier neuf — décision utilisateur.
- **Le préfixe passe à l'onglet 3**, seul dans son groupe et toujours actif,
  au-dessus du groupe « Excel des hydrogrammes objectifs » qui, lui, est
  **grisé** tant que rien n'est composé. « Reprendre un Excel… » reste actif :
  c'est la seule porte d'entrée vers un calage d'une autre session.
- **Les deux boutons reviennent côte à côte**, libellés raccourcis — ce qui
  rend la hauteur que l'empilement de la 0.8.2 coûtait sans ramener le
  débordement à 13 pt.
- **Les erreurs et avertissements remontent dans l'onglet Suivi**, encadré
  repliable sous la bannière, alimenté par le journal de lancement filtré.
- **HEC-RAS ouvert refuse le lancement**, un seul bouton « Ok ».
- **La ligne du calcul de référence nomme ce qu'elle met à zéro** — le
  comportement, lui, était déjà correct en reprise.
- **Les messages de HEC-RAS gardent la ligne qui explique**, non les quatre
  dernières, qui sont son tableau des temps (`_sans_tableau_des_temps` depuis
  la revue du 17/09). C'est
  ce qui empêchait de diagnostiquer l'arrêt de Suhihandia.
- **En reprise, la borne haute de la fenêtre reste celle du plan de
  référence** — mesuré sur le cas réel : 36 h au `.p01`, 32 h 06 au `.p20`
  dont la reprise repart. Défaut réel, mais pas la cause de l'arrêt.

**Bancs : banc QGIS 278 OK, aucun échec, sortie 0** (8 contrôles neufs) ;
`noyau.py`, `calage.py`, `suivi.py`, `criteres.py`, `pilote_hecras.py` et
`pont_hecras.py autotest` verts. La caractérisation de `calage.py` rend « la
trajectoire est celle de la référence » : la chaîne hydraulique est inchangée.

Par quoi reprendre : (1) **relancer le calage repris de Suhihandia avec la
0.8.4**, et lire l'encadré « Erreurs et avertissements » de l'onglet Suivi —
il dira ce que HEC-RAS refuse, ce que l'ancien diagnostic cachait derrière son
tableau des temps ; (2) voir les changements à l'écran dans QGIS ;
(3) installer le ZIP 0.8.4 dans le profil ISL ; (4) **commit** — fait,
`f4aaf6e` sur `main`.

## État précédent — 13 septembre 2026 : 0.8.3 commitée et poussée

Deux demandes utilisateur, la même scène : un calage mené à bout, le nombre
d'essais changé pour un apport, et l'on relance.

- **Le lancement demande par où reprendre.** `_confirmer_reprise()` nomme les
  apports **conservés** (déjà calés en amont, plans d'étape non retouchés) et
  les apports **perdus** (refaits à partir du départ), et propose le premier
  que le calage précédent n'a pas validé. Le calcul est une fonction pure,
  `plan_de_reprise()` — c'est elle que le banc éprouve. La question ne se pose
  que s'il y a quelque chose à perdre ; aucun bouton cliqué vaut *Annuler*.
- **L'onglet Suivi garde le calage précédent.** `Suivi.__init__` renomme
  `avancement.json` en `avancement_precedent.json` au lieu de l'écraser (un
  seul niveau d'historique). L'affichage reprend les apports validés que le
  calage en cours ne traite pas, statut **« repris »** posé par l'affichage —
  suivi.py n'en connaît que quatre —, teinte ardoise, hydrogrammes tracés
  derrière en tiret-point. Ils n'entrent ni dans `en_cours`, ni dans les
  jauges, ni dans les comptes.

**Bancs : suivi.py vert (2 contrôles neufs) ; banc QGIS 270 OK, aucun échec,
sortie 0** (12 contrôles neufs). ZIP 0.8.3 conforme et installé dans le profil
ISL, 21 fichiers — QGIS ouvert, recharger le plugin.

Commit `164bbf5` sur `main`, poussé ; l'arbre est propre.

Par quoi reprendre : (1) voir la boîte de reprise à l'écran, sur un vrai
calage relancé — le banc ne clique aucun bouton ; (2) les points restés
ouverts de la 0.8.2 (recette
Accessibility Insights / Load QSS, élision de la barre à 13 pt, diagnostic de
`_charger_couches_modele` pour rejouer `--modele`).

## État précédent — 0.8.2

Quatre changements d'ergonomie issus de la veille, tous natifs QGIS :
- trois aides dépliables deviennent des `QgsCollapsibleGroupBox` (état
  replié mémorisé par QGIS, objectName obligatoire pour la clé) ;
- toutes les boîtes d'information deviennent un `QgsMessageBar` dans la
  fenêtre (`_signaler`) ; seules décisions et erreurs interrompent encore ;
  diagnostic et installation écrivent leur détail sous le bouton ;
- `QgsGui.enableAutoGeometryRestore` dans `PluginCalage.composer()`, pas
  dans le constructeur (banc et captures exigent une géométrie fixe) ;
- **débordement de l'onglet Objectifs à 13 pt corrigé**, deux causes : la
  rangée de deux boutons (703 px, désormais empilés) et le tableau des
  cibles (désormais dans son propre `QScrollArea`). 773 px → 514 px.

**Banc : 258 contrôles, aucun échec, sortie 0.** ZIP 0.8.2 conforme et
installé dans le profil ISL ; captures refaites. Reste : commit, et la
recette Accessibility Insights / Load QSS proposée par la veille.

## État précédent — 0.8.1

Sur la branche `ergonomie`, arbre non propre. Fait et vérifié :
- onglet **« Aide et configuration »** ; plancher de largeur borné à 800 px
  (`LARGEUR_PLANCHER_MAX`), barre élidée sans défilement ;
- **relecture automatique des cibles** (onglets 3 et 4) quand l'Excel a
  changé sur disque : `_relire_cibles_si_modifiees()`, au changement
  d'onglet et au retour dans QGIS ; sans reprendre les réglages du classeur ;
- deux messages citaient l'ancien bouton « Composer et contrôler » ;
- banc QGIS **250 OK, 1 échec préexistant** (13 pt / Objectifs, débordement
  de 37 px — identique sur les sources 0.8.0, voir STATUT § 6) ;
- `calage_apports_0.8.1.zip` reconstruit et **installé dans le profil ISL**
  (QGIS ouvert : recharger le plugin) ; six captures refaites ;
- STATUT.txt, LISEZMOI, README, metadata, et `0-Ergonomie/retours/
  CALAGE_APPORTS.md` complétés.

Par quoi reprendre : (1) regarder l'élision de la barre d'onglets à 13 pt
dans une fenêtre de 800 px, à l'écran ; (2) faire remonter le diagnostic de
`_charger_couches_modele` dans le banc, puis rejouer `--modele` ;
(3) commit. Le point 2 de la 0.8.1 — widget trop large de l'onglet 3 — est
**réglé** en 0.8.2.

## Reprendre ici — 11 septembre 2026

La refonte **0.8.0** est sur la branche **`ergonomie`**, créée depuis
`bfff3fe`. Au contrôle initial, `main`, `origin/main` et les sources locales
étaient identiques, avec un arbre propre ; l'archive 0.7.24 correspondait
à ses sources. L'ancien état « quatre commits non poussés » était périmé.

La version **0.8.0** est installée et ouverte dans le profil QGIS **ISL**.
Les **21 fichiers installés** sont identiques à `calage_apports_0.8.0.zip` ;
les **20 fichiers sources** du ZIP sont identiques au dépôt, et le dernier
est le manifeste de provenance généré. Aucun bytecode n'est livré.

Le parcours conserve Modèle → Sorties → Objectifs → Lancer → Suivi, avec
Aide et le contrôle permanent en bas. Les détails secondaires se replient,
les textes suivent le thème et la police, et les étapes sont accessibles
par boutons, liens, F1 et Alt+flèches. Entrée ne déclenche plus les commandes
même si un bouton a le focus ; Espace reste disponible.

Validation : **248 contrôles Qt réussis, code de sortie 0**, sans modèle réel ;
**30 scénarios visuels** dans QGIS 3.44.8, dont 800 × 620, texte à 13 points,
Night Mapping et écran réel à 150 %. Trois défauts injectés sur une copie
isolée sont refusés par le garde-fou d'archive, puis la copie propre est
acceptée. Les six captures du README sont à jour. La chaîne hydraulique et
`noyau.py` n'ont pas été modifiés ; les 15 bancs de référence ont réussi.

Voir [les décisions et sources](docs/ergonomie_2026-09-11.md) et
[les mesures d'affichage](docs/ergonomie_2026-09-11-mesures.json).

**Suite :** relire la branche avant fusion. Un prochain calage réel permettra
de compléter la recette de la version 0.8.0 ; aucun calcul long ni écriture
dans un modèle de travail n'a été lancé pour cette refonte. Les chantiers
hydrauliques historiques ci-dessous restent hors du périmètre ergonomique.

## Historique technique du 9 septembre 2026

Les relevés et pistes qui suivent décrivent cette date. L'installation,
la recette graphique et le renouvellement des captures ont depuis été
réalisés pour la 0.8.0, comme indiqué ci-dessus.

### ✅ ARDANAVY Q20 V3 — TERMINÉ ET CONFORME

Lancé le 9 à 08 h 50 avec la **0.7.23**, conclu à **22 h 35**. **6 apports
sur 6**, 11 calculs, 13 h 44. Plan final **p12**. Livrables écrits dans
`resultats_finaux\` (15 fichiers). `alertes_chaine` vide.

| apport | essais | volume | pointe | forme | Δt appliqué |
|---|---:|---:|---:|---:|---:|
| ARD06 | 2 | 100,0 % | 100,7 % | 99,7 % | −1,6 h |
| ARD07 | 2 | 100,7 % | 98,3 % | 99,9 % | −0,8 h |
| ARD08 | 2 | 100,6 % | 100,3 % | 100,0 % | −1,7 h |
| ARD09 | 1 | 98,2 % | 101,7 % | 99,0 % | −1,6 h |
| ARD10 | 1 | 99,9 % | 99,3 % | 100,0 % | −0,5 h |
| ARD11 | 2 | 100,3 % | 99,3 % | 99,3 % | +0,1 h |

Écart maximal 1,9 % en volume, 1,7 % en pointe. Bilan de masse **0,015 %**
pour un seuil à 5 %.

**Cohérence du décalage : aucune alerte.** Étendue 1,8 h pour un seuil de
2,3 h ; pic du modèle +1,28 h par section, pic des cibles +1,00 h. Mesure
identique à celle du Q100 de ce modèle.

**Deux réserves de périmètre**, non bloquantes, dans `synthese.md` : une
fenêtre qui retient 72 % du volume cible (106,7 % sur toute la série) et une
autre 76 % (111,7 %). Règle en `STATUT.txt` § 2.2 bis — ce qui est hors
fenêtre n'est pas jugé et ne peut pas l'être, un apport ne sachant qu'ajouter
du débit.

**ARD11 a demandé deux essais pour une raison qui mérite d'être connue** :
sa section porte DEUX pics quasi égaux à l'essai 1 — 145,15 m³/s à 14,40 h et
142,87 à 16,10 h, soit 1,6 % d'écart. L'appariement par le pic a pris le
mauvais, rendu un Δt diagnostic de −1,60 h contre +0,10 appliqué, et annoncé
82,7 % de volume et 86,9 % de forme. Le Q100 avait donné 82,8 / 102,9 au même
endroit, et s'était redressé de la même façon à l'essai 2. Ce n'est donc ni
un défaut neuf ni un effet du correctif du 9.

**L'identifiabilité chute vers l'aval**, et c'est à porter au client :
l'apport pèse 56 % de la pointe à ARD06, 36 % à ARD07, 27 % à ARD08, 12 % à
ARD09, 8 % à ARD10, 8,7 % à ARD11. À 8 %, l'hydrogramme retenu peut
s'écarter de ~62 % du véritable sans que la section cesse d'être conforme
(règle en `STATUT.txt` § 2.5). La réserve automatique ne se lève qu'en
dessous de 5 %, donc aucune n'a été émise. **Sur ces trois sections,
l'hydrogramme d'apport livré est une valeur de commande, pas une estimation
hydrologique.**

**Deux lancements ont échoué avant celui-ci, le même jour :**

1. **08 h 46** — le calcul de référence est sorti en échec après 201 s. Cause :
   le **prétraitement 2D était périmé**, la composition de 08 h 40 ayant
   réécrit `Ardanavy.g03` dont le `.hdf` datait de trois jours. La chaîne
   l'avait annoncé, ligne 72 de son propre journal. Ce run raté a régénéré le
   `.hdf` — c'est ce qui a permis au suivant d'aboutir.
2. **HEC-RAS était ouvert** pendant les deux. La 0.7.24 pose désormais la
   question au lancement.

### Ce que la journée du 9 a donné

**Un défaut de verdict trouvé en production, corrigé, et quatre demandes
d'ergonomie.**

| | |
|---|---|
| **LA FENÊTRE JUGÉE EST EN TEMPS DE SIMULATION, et le diagnostic la lisait sur la base de temps de la cible.** Δt de +2,60 h sur une cible culminant à 0,50 h : le pic de la cible tombait hors fenêtre, une section calée à 0,1 % près était annoncée à **350 % de pointe et 370 % de volume**, refusée après trois essais et sept heures. Onze apports non traités | `STATUT.txt` § 2.2, commit `0302ccd` |
| **Un décalage plus long que la fenêtre qu'il décale devient BLOQUANT** — il n'était refusé que par l'effet du défaut ci-dessus | idem |
| **Décision : le calage vise le volume, la pointe et la forme. Pas l'heure du pic.** Le volume injecté n'est pas un levier (0,03 % d'écart de Δt = 0 à −3 h) et le prendre pour objectif serait dégénéré : son minimum est zéro | `STATUT.txt` § 2.1 |
| **Ce n'était pas une régression** — `decalage_minimisant_ecart` et `_temps_du_pic` sont mot pour mot ceux du 31/08, et cette chaîne rejouée rend le même −1,60 h | idem |
| **0.7.24 : les onglets 2 et 3 s'inversent**, « Contrôle paramétrage » quitte les onglets pour le bas de la fenêtre — vert quand c'est le moment, gris sinon —, l'onglet « Objectifs » chiffre pointe, heure du pic et volume de chaque cible, et HEC-RAS ouvert fait poser une question au lancement | commit `3cac4f8` |
| **L'analyse « jacobien triangulaire / calage simultané » est retirée du dépôt** — demande utilisateur. `docs/idees_V2_plugin.md` ne garde que ses deux idées sans rapport. L'historique git la porte toujours | commit `349d503` |

### Bancs — ce qui a été rejoué le 9, et ce qui ne l'a pas été

**Verts, depuis le poste :** `calage` (référence **regelée**), `criteres`
(section 7 quinquies, neuf contrôles neufs), `noyau` (section 12, quatre
contrôles neufs), `suivi`, `livrables`, `geometrie`, `controle_donnees`,
`elaguer_projet`, `pilote_hecras`, `pont_hecras`, `style_classeur`,
`creer_template`, `verification_environnement`, `faire_zip`,
`essai_garde_fou_archive`.

**`CALAGE_PYTHON` n'est plus posée sur ce poste, et ce n'est pas un obstacle :**
`D:\1-Python\.venv\Scripts\python.exe` porte les treize paquets, geopandas et
h5py compris. C'est lui qui a fait tourner les quinze bancs.

**NON REJOUÉ : `test_plugin_qgis.py`** — douze contrôles neufs pour la 0.7.24,
et il exige QGIS.

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

0. **Relire les livrables d'ARDANAVY Q20 V3** — `resultats_finaux\`, à
   l'œil : `synthese.md`, `tableaux_calage.xlsx`, le profil en long, les six
   comparaisons. Le calage est conforme ; ce sont ses SORTIES qui n'ont pas
   encore été regardées. Pas de figure de convergence pour ARD09 et ARD10 :
   un seul essai, rien à tracer.
1. **Installer la 0.7.24 et rejouer `test_plugin_qgis.py`** — Extensions →
   Installer depuis un ZIP, `calage_apports_0.7.24.zip`. **Pas pendant un
   calage.** Douze contrôles neufs, et ils exigent QGIS. Sans cela le poste
   garde la 0.7.23 : elle porte le correctif de la fenêtre, mais pas l'ordre
   des onglets, ni le bouton du bas, ni le tableau des cibles, ni la question
   sur HEC-RAS ouvert.
2. **Refaire les captures du README** — `python src/captures_plugin.py` sous
   l'interpréteur de QGIS. Elles datent de la 0.7.19 et montrent l'ancien
   ordre des onglets ; le README le dit désormais, ce qui ferme le risque de
   les croire à jour, pas celui de les laisser fausses.
3. **Le `.pdf` de la note, à réexporter à la main** — ouvrir le `.docx`
   (V17) dans Word, *Enregistrer sous > PDF*, et lui remettre une table des
   matières au passage : la reconstruction la perd. Quatre tentatives
   d'export piloté ont échoué, sans que le document y soit pour quelque
   chose. **La note ne parle encore ni du correctif de la fenêtre ni de la
   0.7.24** — `contenu.py` est à reprendre avant l'export.
4. **Regarder la fenêtre**, et cette fois il y a de quoi : la 0.7.24 déplace
   deux onglets et sort un bouton des onglets, sans qu'aucun œil ne l'ait vu
   sous QGIS.
   **À regarder en priorité : les fenêtres étroites.** La zone défilante de
   chaque onglet comprime son contenu au lieu de faire apparaître une barre,
   et c'est le dernier encadré qui encaisse — le plancher posé sur le bouton
   principal ne protège que lui, et le nouveau tableau des cibles est
   justement le dernier encadré de son onglet (il porte son propre plancher,
   calculé sur le nombre de lignes — à vérifier à l'œil).
   **Entrée ne fait toujours rien**, nulle part — prix assumé du désarmement
   du geste irréversible.
5. **Le suivi pendant un vrai calage.** L'état du calage précédent qui ne se
   peint plus, « mort au démarrage » distingué de « pas encore parti », le
   fil qui dit « calage lancé », la question posée si l'on recompose pendant
   qu'un calcul tourne : tout cela est éprouvé sur des états **fabriqués**,
   jamais sur un calage qui tourne. Y regarder aussi la **figure de
   convergence** corrigée, dans `suivi/` et dans `resultats_finaux/`.
6. **Trois garde-fous jamais rencontrés en réel** — volume plancher, apport
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
