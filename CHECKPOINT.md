# CHECKPOINT — Calage des apports (ISL Ingénierie)

Point de reprise pour ouvrir une nouvelle conversation avec un contexte
minimal. L'état courant et les règles en vigueur restent dans `STATUT.txt` ;
ce fichier ne dit que **où on en est** et **par quoi reprendre**.

> ## ⚠️ Ce fichier est en retard sur `STATUT.txt`
>
> Tout ce qui suit la section « Session du 30 août 2026 » ci-dessous décrit
> un algorithme **retiré le 07/08/2026** : déphasage de la réponse φ, mode
> rapide, plancher de volume irréductible, correction à deux termes. Ces
> sections sont conservées comme récit, **pas comme référence**.
> **`STATUT.txt` fait foi.**

## Reprendre depuis GitHub, sans le poste de travail

Le dépôt porte le code, `STATUT.txt`, ce fichier, la note et le template.
**L'historique des conversations ne voyage pas** — il vit dans
`~/.claude/projects\…` sur le poste. Ces deux fichiers le remplacent.

**Par quoi commencer :** la section du 1er septembre ci-dessous, puis
`STATUT.txt` § 1, § 2.2 bis, § 2.2 ter, § 5.3 ter et § 5.5. Ne pas lire le
reste de ce fichier : tout ce qui suit la session du 30 août décrit un
algorithme retiré le 07/08/2026.

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

## Session du 4 septembre 2026 — le troisième calage, et ce qu'il a révélé

**Par quoi reprendre :** `STATUT.txt` § 1 (état courant), § 2.2 ter (le
critère de cohérence se juge à la fin — corrigé), § 5.7 fin (le troisième
calage, mesuré), § 6 (le verdict de volume, chiffre reproductible).

**15 bancs verts, 152 contrôles QGIS verts, greffon en 0.6.4.**

### Ardanavy Q100, refait de zéro avec la 0.6.1 : 6/6 conforme en 16 h 49

Livrables **complets au premier passage** : profil en long, feuille
`Hydrogrammes_apports`, figures entières, plan final « Q100-avec apports »,
préfixe sur les sept plans. ARD11 rejoue le 01/09 à la décimale (cas de forme,
validé au second essai). Volume : ARD11 à 100,3 % sur la fenêtre jugée,
**111,7 % sur la crue entière** — 111,8 % le 01/09. Reproductible : c'est la
fenêtre (§ 6, à trancher par l'utilisateur).

### Le critère de cohérence tirait sur la lecture fausse — 0.6.3

`_coherence_decalage` se mesurait sur le **calcul de référence**, tous apports
à zéro : l'état que § 2.2 ter déclare faux depuis le 02/09 (sections aval
affamées). Première sortie réelle le 03/09 : « DÉRIVE de 7,2 h » sur un modèle
qui, calé, s'étend sur 1,8 h — réserve portée jusque dans `synthese.md`.
Désormais `caler()` recueille le Δt **retenu** et la fenêtre de chaque apport
et juge **à la fin** (`_coherence_points`). Banc : la ligne « cohérence » sort
après la vérification finale, son étendue est celle des Δt retenus ; échoue
sur le code d'avant. La note du run V2 est à régénérer
(`reconstruire_livrables.py`) si le dossier est livré.

### Un classeur sans colonne de temps est parti en calage — 0.6.4

Premier lancement depuis un autre poste (Ardanavy Q20 V1) : feuille Cibles
avec l'en-tête A1 remplacé par un caractère isolé et la colonne de temps
vide sous six colonnes de débit pleines. Le pont a planté en arrière-plan
(`'numpy.float64' object has no attribute 'to_numpy'`). `etat_cibles()`, que
le greffon consulte avant de lancer, refuse désormais un classeur sans
colonne « Temps_h » en nommant l'en-tête trouvé, et ne tient une cible pour
renseignée que si elle a deux instants numériques en face de deux débits —
la règle du pont, qui porte le même garde-fou.

Et le geste naturel après ce refus — recomposer — **réécrivait la feuille
Cibles vide**, sans un mot : 418 lignes sur six colonnes, mesuré sur copie.
`preparer_classeur()` ne retrouvait la saisie que sous l'en-tête
« Temps_h ». Défaut **antérieur** au 04/09. La recomposition est désormais
refusée quand la feuille porte des colonnes « Cible_ » non vides sans
colonne de temps. Quatre bancs, échec avant / succès après. Détail :
`STATUT.txt` § 5.7, fin. La suite QGIS n'a pas été rejouée : `plugin.py`
n'est pas touché.

### L'onglet Suivi regardait le mauvais dossier — 0.6.2

Voir la session du 3 septembre ci-dessous (correctif fait le 3 au soir).

## Session du 3 septembre 2026 — deux calages conformes, deux jeux de livrables incomplets

**Par quoi reprendre :** `STATUT.txt` § 1 (état courant), § 2.5 (titres des
plans — neuf), § 5.7 (les cinq défauts, mesurés), § 6 (le verdict de volume,
à trancher).

**15 bancs verts, 152 contrôles QGIS verts, greffon en 0.6.2.**

### Ce que le relevé des dossiers a montré

Les deux calages étaient conformes. Ardanavy n'avait **pas de profil en
long** ; Suhihandia n'avait **ni classeur, ni note de synthèse, ni figure des
apports, ni profil en long**. Les journaux nommaient chaque cause. Cinq
défauts, chacun reproduit avant correction, chacun avec un banc qui échoue
avant et passe après :

| défaut | cause | commit |
|---|---|---|
| Rapport de 12/12 perdu | masque du **premier** apport appliqué à tous — l'unsteady porte 256, 321, 811 et 1 001 points | `5fb1932` |
| Figure tronquée à la fenêtre jugée | les séries étaient coupées avant le tracé, alors que `figure_comparaison` cadre déjà seule | `ed21fe9` |
| « PK indisponibles » | la porte testait la gravité **générale** du contrôle SIG, pas les conditions du PK — une ligne de 94 cm suffisait | `bf3a7aa` |
| Profil en long / `xarray` | le calage avait tourné sur un **autre interpréteur** (0.99.2 au journal, 0.99.1 au venv) et rien ne le disait | `233f092` |
| Apports dans le classeur | la feuille n'avait jamais existé | `45668e7` |

### Le préfixe de scénario et le plan final

Demandés par l'utilisateur après lecture du gestionnaire de plans. Conçus par
panel de trois approches puis juge ; le plan retenu a **renversé une croyance
du code** : la troncature du *Short Identifier* à 24 caractères n'était pas
une limite de HEC-RAS mais une convention de ras-commander, sous un
commentaire faux (« à largeur fixe »). Mesuré sur **103 plans réels** :
largeur 64 sur les 67 qu'HEC-RAS écrit lui-même, 24 sur les 34 de la chaîne,
et 14 plans **dépassant 24, jusqu'à 30**, écrits et calculés.

Ce que ça donne : `titre_etape()` seul fabrique les titres, pose le tiret et
**refuse au-delà de 30** au lieu de rogner — deux plans rognés au même
identifiant partagent le dossier de résultats que RAS Mapper nomme d'après ce
champ. Le plan final `avec apports` est **le plan de la dernière étape
retitré** : il portait déjà tout, il ne lui manquait qu'un nom. Préfixe vide
= titres d'avant, octet pour octet.

Deux choix par défaut faute d'arbitrage, chacun une constante : `avec
apports` (fait la paire avec `sans apport`) et préfixe vide.

### Ce qui reste, et qui est au § 6

**Le verdict de volume porte sur la fenêtre jugée, pas sur la crue.** Mesuré
dans le plan final d'Ardanavy : deux apports sur six sont conformes sur la
fenêtre (99,9 et 100,3 %) et hors bande sur la crue entière (106,7 et
111,8 %). `fenetre_injection` ferme à 99 % du **déficit**, et son garde-fou
borne le déficit exclu, pas le volume exclu — 25 % du volume de crue hors
fenêtre là où le commentaire promet 2,5 %. La figure le montre désormais ; le
critère ne le juge pas encore. **À trancher par l'utilisateur** : élargir
changerait des verdicts déjà rendus.

> Le garde-fou d'archive a fait son travail deux fois : mes commentaires et
> mes bancs nommaient les affaires du client dans des fichiers distribués.
> L'extension de `.affaires` aux codes de section (01/09) les a refusés.

### Les livrables de Suhihandia, reconstruits sans recalculer

`src/reconstruire_livrables.py` — nouveau, **non distribué**, outil de
rattrapage. Il relit le plan final `p17`, l'unsteady `u24`, le classeur, le
journal et `iterations.xlsx`, rejoue `diagnostiquer()` avec **les fenêtres du
journal** (on relit, on ne refait pas), et appelle `produire_livrables_finaux`
comme le pont. Doublure en lecture seule du pilote : le modèle n'est pas touché.

**19 fichiers, verdict CONFORME, les douze lignes concordent au dixième avec
le suivi** — dont le `profil_en_long.png` qu'aucun des deux calages n'avait
obtenu. Les quinze fichiers d'origine sont mis de côté, pas écrasés.

### Le contrôle neuf a attrapé son premier cas sur un poste neuf

Le bouton « Installer… » a **réutilisé** un environnement existant, « installé »
onze paquets, puis la vérification a refusé : `xarray` absent — le manque
même qui avait coûté le profil en long à Ardanavy, attrapé dix secondes avant.
Mais le message conseillait le bouton qui venait d'échouer, et l'installeur
n'avait pas complété : pip `--upgrade` (*only-if-needed*) ne re-résout pas les
dépendances d'un paquet déjà présent. **0.6.1** : l'installeur pose ce que la
sonde nomme puis revérifie, et son message ne renvoie plus au bouton. Banc 10,
sans téléchargement ; il échoue sur le code d'avant (pip lancé une fois).

### Le suivi regardait le mauvais dossier

Le calage Ardanavy Q100 V2 tournait (ARD06 validé, ARD07 en cours) et
l'onglet Suivi affichait « Aucun calage suivi ». Le lancement part de
`self.classeur` — que « Reprendre un classeur… » (onglet 4) peut pointer
n'importe où ; le suivi lisait les champs de l'**onglet 3**, qui ne disent
que où composer le prochain paquet. **0.6.2** : le suivi lit le dossier dans
le classeur (`noyau.dossier_suivi_du_classeur`, la règle du pont), et la
bannière nomme le dossier surveillé. Suite QGIS : l'onglet 3 désigne exprès
un autre dossier — 16 contrôles échouent avant, 152 passent après.

## Nuit du 1er au 2 septembre 2026 — le critère reposait sur une mesure fausse

**Par quoi reprendre :** `STATUT.txt` § 1 (les deux calages), § 2.2 ter et
§ 5.5 (le décalage), § 6 (points ouverts).

> **Où sont les résultats** (déplacés le 03/09) : `<modèle>\3-Apports\<MODÈLE>_Apports_Q100`.
> Les **modèles**, eux, n'ont pas bougé.

**Ardanavy Q100 s'est terminé le 02/09 à 0 h 34, CONFORME** — six apports sur
six, un ou deux essais chacun, 14 h 29, bilan de masse 0,011 %, zéro incident.
Premier calage complet et conforme de la chaîne corrigée.

### Et il dément le tableau qui avait fait changer le critère

|  | 1 | 2 | 3 | 4 | 5 | 6 | étendue |
|---|---|---|---|---|---|---|---|
| annoncé le 01/09 | −0,70 | +0,40 | −1,10 | +2,30 | +3,40 | +5,90 | **7,0 h** |
| mesuré par la chaîne | −0,70 | +0,10 | −0,80 | −0,40 | +0,40 | +1,00 | **1,8 h** |
| écart | 0,00 | 0,30 | −0,30 | 2,70 | 3,00 | 4,90 | |

**Zéro sur le premier apport**, puis un écart qui grandit avec le rang. C'est
une signature, pas une coïncidence — et la cause est écrite dans le dossier
lui-même : pour ne pas attendre le calage, les six sections avaient été relues
sur le HDF **du calcul de référence**, celui où *tous les apports sont à
zéro*. Or la méthode est séquentielle : le Δt d'un apport se mesure sur un
résiduel où l'amont est **déjà calé**. Avec tout à zéro, chaque section aval
est affamée, son pic arrive de plus en plus tard, et la lecture *fabrique* une
dérive proportionnelle au rang.

**Et ce n'est pas une déduction — les deux lectures ont été refaites.** Les six
sections relues sur le plan de référence `p04` (tous apports à zéro) rendent
10,30 / 12,90 / 13,40 / 17,80 / 18,90 / 21,90 h : le tableau annoncé, **au
centième d'heure près, sur les six**. Relues sur le plan final `p10` (tous
apports calés), elles rendent les Δt que la chaîne a mesurés.

| progression du pic le long de l'axe | h/section |
|---|---|
| cibles | +1,00 |
| modèle, apports à **zéro** | **+2,30** |
| modèle, apports **calés** | **+1,25** |

Le « le modèle route plus de deux fois plus vite que ses cibles » décrivait un
modèle *privé de ses apports*.

Le modèle réel : étendue 1,8 h, pente +0,280, r +0,751, seuil 2,3 h →
**aucune alerte**, ni par le critère retiré ni par celui qui l'a remplacé. Le
reproche fait au premier critère — « il ne lève rien sur le pire des deux
cas » — tombe avec la mesure qui le portait.

**Et la dérive n'est plus attestée que sur un modèle.** Elle l'était sur deux,
« en sens contraire », ce qui en faisait un écart systématique entre routage
et cibles. Il reste Suhihandia, dont les Δt ont toujours été ceux de la chaîne
(+0,1 → −6,5 h sur dix sections) : une anomalie isolée, sur un modèle.

`ETENDUE_DECALAGE_MAX_PART = 0,15` **ne repose donc plus que sur un cas**. Ni
validé ni invalidé : sans appui suffisant. Rien n'a été changé dans le code —
changer un seuil sur la foi d'un seul cas serait refaire ce qui vient d'être
défait.

> **La leçon, générale :** un raccourci qui évite d'attendre le calage mesure
> autre chose que le calage. Le HDF était complet, la commande bien employée,
> les chiffres bien lus — la grandeur n'était pas la bonne. Troisième fois en
> deux jours ; celle-ci a mis vingt-quatre heures et a fait changer un critère
> entre-temps.

### Les deux calages sont terminés et conformes

**Suhihandia V3** a fini le 02/09 à 10 h 41 — 12/12, dont **dix en un seul
essai**, 46 h 07 en tout, zéro incident. `SUH12` a été le seul difficile :
cinq essais, 14 h 47 à lui seul, pointe 91,6 → 95,3 → 97,4 → 98,6 %. Il passe,
mais sa forme tombe à 97,1 % pour un minimum de 97,0 — le seul des dix-huit
apports des deux calages à frôler une limite.

### Et le critère se prononce enfin, sur deux cas réels

| modèle | étendue | médiane des fenêtres | seuil | rapport | verdict |
|---|---|---|---|---|---|
| Suhihandia | 6,6 h | 27,8 h | 4,2 h | 0,238 | **ALERTE** |
| Ardanavy | 1,8 h | 15,5 h | 2,3 h | 0,116 | aucune |

**Il discrimine** — et le critère *retiré* aurait dit exactement la même chose
(Suhihandia pente −0,494 / r −0,923 → alerte ; Ardanavy +0,280 / +0,751 →
silence). Le changement du 01/09 a été fait pour une raison qui n'existait pas
**et** ne change rien sur les données disponibles : rien à défaire dans
l'urgence.

Deux réserves : la marge du côté silencieux est mince (0,116 pour 0,150), et
les fenêtres de Suhihandia sont surdimensionnées par le bug d'unités, ce qui
rend son seuil trop généreux. La conclusion tient, le chiffre non.

L'objection « l'étendue grandit avec le rang » se nuance : 2,1 / 3,3 / 4,4 /
6,6 h, puis **elle plafonne** à 6,6 h dès le dixième apport. La croissance
n'est pas mécanique — mais un chiffre lu avant la fin d'un calage ne vaut rien.

## Session du 1er septembre 2026, soir — la liste des points ouverts mentait

**Par quoi reprendre :** `STATUT.txt` § 1 (état courant), § 2.4 (le cliquet),
§ 6 (points ouverts, désormais élagués).

**15 bancs verts hors QGIS, 149 contrôles verts dessous** — la suite QGIS est
passée de bout en bout pour la première fois.

### Trois points ouverts sur six étaient déjà faits

Repris un par un, dans le code et non de confiance :

| point ouvert | état réel |
|---|---|
| « r et le KGE travaillent sur la grille qui englobe » | faux — bornés depuis longtemps, § 7 du banc |
| « la ligne A3 annonce x 1,000 et plancher 0,00 % » | faux — elle dit la lecture en escalier |
| « porter `RAS_COMMANDER_MINIMUM` » | vrai, et fait |

La liste porte maintenant son avertissement en tête : **les vérifier dans le
code avant de les traiter**. Un point ouvert ne se périme pas tout seul.

### Ce que la vérification a trouvé de pire que ce qui était écrit

Le volume, la pointe, la couverture et la forme étaient bien bornés à la
fenêtre jugée. Le **décalage**, lui, se mesurait sur toute la grille — et
c'est lui qui **apparie** les deux séries avant toute comparaison. Mesure : un
transitoire de mise en eau hors fenêtre, plus haut que l'événement, rendait
**−26,00 h pour un retard réel de +1,50 h**, et emportait le volume à 109 % et
r à 0,95, tous deux pourtant bornés. *Borner les grandeurs sans borner leur
appariement ne bornait rien.*

### Le cliquet, énoncé depuis la V13, mesuré depuis ce soir

Un apport ne sait qu'ajouter du débit : là où la section donne déjà plus que
la cible, l'excès est irréductible. `caler()` ne refusait que le cas **total**
(cible entièrement sous le résiduel, jugé sur la pointe). Le cas ordinaire —
cible atteignable en pointe, volume condamné — passait :

    plancher annonçable AVANT le premier essai   109,8 %
    volume atteint après trois essais            109,6 %
    verdict rendu   « le modèle répond de façon trop non linéaire »

Le motif accusait le modèle. La cause était le cliquet, et il ne coûte aucune
simulation : l'excès est la part négative de l'écart, déjà calculée.

### La suite QGIS, enfin

Deux choses l'empêchaient, invisibles hors QGIS : le banc **s'effondrait** sur
un `NoneType` au lieu de dire qu'il manquait l'interpréteur (un échec au lieu
de 149) ; et quatre chemins de `noyau.py` faisaient échouer le contrôle
d'attache — deux exemples **élidés** qui effaçaient le préfixe que la liste
blanche reconnaît, deux **motifs de recherche** portant une étoile. L'étoile
étant interdite dans un nom de fichier Windows, le contrôle les écarte sur ce
critère plutôt que d'ajouter leurs racines à la liste blanche : *un motif de
recherche n'est pas un chemin* est une règle, pas une exception nominative.

**Sur ce poste, la suite QGIS exige `CALAGE_PYTHON`** — le greffon ne trouve
seul qu'un `.venv` voisin de la chaîne.

### Ce qui reste, et ce qui a changé de statut

`plugin.py` est désormais éprouvé sous QGIS : la boîte de compte rendu
dupliquée, laissée de côté le 31/08 parce qu'« aucun banc local ne la
couvre », a vu sa condition levée. La pente d'apport en dur
(`PENTE_APPORT_DEFAUT = 0,01`) devient elle aussi vérifiable.

### Le suivi des deux calages a corrigé deux chiffres du dossier

Relevé du soir, sur les fichiers de suivi. **Suhihandia V3** : 10/12 calés,
*neuf en un seul essai*, volumes 99,9–101,0 %, zéro incident. **Ardanavy
Q100** : 3/6, tous en deux essais, 100,0 / 100,7 / 100,6 %. Rien à faire sur
l'un ni sur l'autre.

**Le bilan de masse n'est pas un trait de la chaîne.** J'avais écrit une heure
plus tôt que « nos 0,5 à 1,4 % sont un à deux ordres de grandeur au-dessus de
ce que HEC appelle *very low* ». Mesure : Ardanavy **0,011 %**, Suhihandia
**0,471 %** — deux modèles de la même affaire, dans la même chaîne. Le
0,5–1,4 % appartient à un modèle, pas à la méthode.

**Et « 4,4 h » était une mesure partielle.** L'étendue de Δt du modèle A, au
dossier comme sa caractéristique, avait été prise à 8 apports sur 12 :

| lu à | 3 sections | 5 | 8 | 10 |
|---|---|---|---|---|
| étendue de Δt | 2,1 h | 3,3 h | 4,4 h | **6,6 h** |

**L'étendue grandit avec le nombre de sections calées**, et le seuil se lit sur
une durée de fenêtre qui, elle, ne grandit pas. Deux modèles également
cohérents mais de longueurs différentes ne sont donc pas jugés pareil — et le
même modèle ne l'est pas non plus selon où son calage s'est arrêté. C'est une
objection **de fond** au critère, pas un ajustement de valeur. La grandeur
comparable serait la pente en h/section (ici −0,571, r −0,950) : ce que la
pente disait déjà. Ce qui avait été retiré le matin, c'est le « ET corrélation
élevée », pas la pente.

Le critère se jouera sur ARD09–ARD11, dont la mesure de référence annonce
+2,3, +3,4 et +5,9 h.

## Session du 1er septembre 2026 — un second modèle renverse un critère

**Par quoi reprendre :** `STATUT.txt` § 1 (état courant), § 2.2 bis et 2.2 ter
(couverture et cohérence du décalage), § 5.3 ter et 5.3 quater.

**15 bancs verts.** Note de méthodologie en V15 (25 pages, 22 tableaux).

### Deux calages ont tourné en même temps, et c'est ce qui a payé

Un sur le modèle **A** (12 apports, lancé la veille avec la chaîne d'avant les
correctifs), un sur le modèle **B** (6 apports, avec le zip de 09:55). Le
second a validé cinq choses en production et **invalidé un critère posé le
matin même**.

Ce que B a validé : l'horodatage de `dire()`, `pretraitement_perime` (première
alerte réelle), l'avertissement de pente d'apport, et surtout le **correctif
d'unités** — décisif ici, pas marginal. Les cibles de B courent jusqu'à
**208,5 h** de remplissage à zéro et `tf` tombait entre 83 et 129 h : les six
durées auraient été plafonnées à 37 h, soit **zéro économie**.

### Ce que B a renversé

| | pente | r | étendue Δt | ancien critère |
|---|---|---|---|---|
| modèle A (8 apports) | −0,70 | −0,98 | 4,4 h | OUI |
| **modèle B** (6 apports) | **+0,99** | **+0,73** | **7,0 h** | **non** |

Le modèle B avait la pente la plus forte et la dérive la plus grande, et
passait sous « pente forte **ET** corrélation élevée » parce que sa dérive
n'est pas monotone. **Le `ET` sur la corrélation écartait le pire des deux
cas.** Le critère porte désormais sur l'**étendue de Δt**, rapportée à la
durée médiane des fenêtres jugées, seuil relatif 15 %.

**Les deux modèles sont au banc, B nommément** — sans lui, rien n'empêcherait
d'y revenir.

### La leçon de la journée, prise trois fois

Un gain annoncé à 34 %, mesuré à 11 %, puis à 33 % après correctif. Un seuil
de couverture aveugle par construction. Un critère de cohérence renversé par
le modèle qui devait le confirmer. **Chaque fois, la valeur était juste et la
grandeur fausse** — et chaque fois c'est une mesure sur données réelles qui l'a
montré, jamais un raisonnement.

### Ce qui attend une décision

Sur les **deux** modèles, le décalage dérive de 4 à 7 h le long de l'axe, **en
sens contraire** : A route plus vite que ses cibles, B plus lentement. Ce n'est
plus une anomalie isolée. Les sections sont calées à 99–101 % de volume, mais
les hydrogrammes d'apport livrés portent ce décalage, et pas le même d'une
section à l'autre. Sont-ce les cibles, le routage, ou une origine de temps ?

Deux détails : `.affaires` ne surveille que `SUH01`/`SUH02` — ni les autres
sections, ni `ARD06`…`ARD11` ; et le seuil de 15 % ne repose que sur deux cas.

## Session du 31 août 2026 — la durée ajustée passe en production

**Par quoi reprendre :** `STATUT.txt` § 1 (état courant), § 2.6 (durée
ajustée) et § 5.3 bis (ce que le premier passage a appris).

### Un calage tourne encore au moment où cette session se ferme

Lancé le 31/08 à 12:33 **depuis un second poste**, sorties dans
`T:\…\Suhihandia_v7\HEC_RAS_v7_Suhihandia\Sortie-V3\`. À 16:15 : référence
faite, SUH01 calé, SUH02 en calcul. Fin attendue le **01/09 après-midi** si
chaque apport tient en un essai.

**Rien n'est validé.** Le seul apport passé est SUH01, celui qui ne pèse que
1,3 % du débit de sa section. Reprendre en lisant le journal, pas en
supposant que ça s'est bien terminé.

### Ce que le premier passage a appris

| Ce qui était annoncé | Ce qui a été mesuré |
|---|---|
| 34 % de temps de calcul en moins | **11 %** (et ~33 % après le correctif du soir) |
| SUH01 simulé ~12,5 h | **21,5 h** |
| plafond de 36 h rarement atteint | **7 durées sur 12 le dépassent** |

L'écart vient de la grandeur, pas du calcul : l'estimation portait sur la
**fin de crue de la cible**, le code mesure la **fenêtre de déficit sur le
calcul de référence**, toujours plus longue. La chaîne a raison, la
prévision avait tort.

**Deux constats qui demandent une décision :**

1. **Il manque 3 h au modèle.** Le calendrier réclame jusqu'à 39,0 h pour
   juger SUH07…SUH12 ; le plan en offre 36. Rien ne bloque — le plafond
   `duree_reference_h` tronque — mais les six derniers apports seront jugés
   sur une fenêtre incomplète, et **aucun livrable ne le dit**.
2. **SUH01 calé au premier essai n'est pas une réussite.** Sa section
   recevait déjà 4,9 m³/s sur 5,0 attendus. Converger instantanément est ici
   le symptôme de la non-identifiabilité (écart possible : 373 %).

### Coût réel, sur réseau

3,5 à 4,0 min de calcul par heure simulée. Référence : 36 h en 2 h 23.
SUH01 : 21,5 h en 1 h 15. Une passe des douze apports ≈ 25 h.
**Rapatrier le modèle et le terrain de 17,7 Go en local rapporterait plus
que l'optimisation des durées.**

### Le soir : trois correctifs et trois coupes

Partis d'une question — « pourquoi ça tourne encore alors que l'hydrogramme
SUH03 est déjà passé ? » — dont la réponse était un bug. Détail en
`STATUT.txt` § 5.3 ter.

| | ce qui n'allait pas | mesure |
|---|---|---|
| **1** | `fenetre_injection()` comparait un volume en m³ à un volume en m³/s·h dans un `min()` — 3 600× d'écart. `seuil_haut=0.99` était **du code mort en production** | `tf` = 24,0 h sur SUH03 là où 99 % du volume est à **13,0 h** ; 81,5 h au lieu de 34,5 h sur SUH12 |
| **2** | le correctif 1 a rendu agissante une asymétrie : la fenêtre de jugement gardée par `fenetre_active`, la durée par `ajuster_duree` seul | `Fenetre_active=non` → volume 100,0 %, pointe 100,0 %, **conforme=False** |
| **3** | un décalage plus long que la fenêtre rendait `volume nan`, et `caler()` concluait « le modèle ne répond plus » — en accusant l'hydraulique | volume redevenu mesurable, alerte non bloquante qui nomme la cause |

Le correctif 2 est traité par un **prédicat unique** `_fenetre_demandee(config)`
servant les deux sites, plutôt qu'en rustinant un côté — même remède que
`PAQUETS_HECRAS` pour les deux listes de paquets.

**Trois coupes après audit de sur-ingénierie : −89 lignes de code, −1 dépendance.**

La plus grosse : toute la branche RASTER du profil en long. Elle **n'avait
jamais été raccordée** — le raster rendait une colonne `z_terrain` que le seul
consommateur du profil ne lit pas (`livrables.py` lit `z_fond`). Deux pièges
dans la même coupe : les deux noms figuraient dans une liste `hasattr` à
`bloquant=True`, et le paramètre dans l'ensemble confronté au template livré.
Template régénéré : 42 → 41 paramètres.

**Les quatorze suites sont vertes**, garde-fou d'archive compris.

### Ce qui reste à faire

- **Trancher la mesure de Δt** (point V2). Le contrôle recadré exige que la
  chaîne *refuse* l'apport quand Δt est aberrant ; il basculera le jour où Δt
  sera mesuré autrement, et c'est voulu.
- Les **dix coupes non vérifiées** de l'audit, ~30 lignes, à traiter une par
  une — aucune n'a été soumise à réfutation (§ 6 de `STATUT.txt`).
- Les trois points du matin : livrable disant le manque d'heures, horodatage
  de `dire()`, note à mettre à jour avec le gain — ~33 % après correctif,
  et en disant toujours la base de calcul.

## Session du 30 août 2026 — premier calage sur modèle client

**Le calage n'a pas abouti, et c'est instructif.** Premier essai sur un
modèle client réel (ARAN / Suhihandia, 12 apports SUH01…SUH12). Cinq
lancements, aucun apport calé, **aucun dégât** : chaque arrêt s'est produit
avant ou pendant le calcul de référence, jamais dans un état ambigu.

| # | Où ça s'est arrêté | Cause |
|---|---|---|
| 1–3 | `preparer()`, avant tout calcul | conditions limites plus courtes que la simulation — dont **deux blocs orphelins** que HEC-RAS ignore |
| 4 | 1ᵉʳ apport, après 2 calculs (2 h 23) | bilan de masse **+1,119 %** > 1,0 % |
| 5 | calcul de référence (2 h 11) | bilan de masse **+1,394 %** > 1,0 % |

**Le pas de calcul n'est pas en cause.** Passer de 2 s à 1 s a *dégradé* le
bilan (1,119 → 1,394 %). La piste que suggère le message d'erreur — resserrer
le pas — ne mène nulle part sur ce modèle ; chercher côté maillage,
conditions limites ou tolérance 2D du plan.

**Six correctifs en sont sortis**, tous détaillés dans `STATUT.txt` :

1. **Blocs orphelins de l'unsteady filtrés** — `cartographier_hydrogrammes()`
   ne retient que les noms déclarés en géométrie, comme fait HEC-RAS. Sur ce
   modèle : 45 blocs pour 14 BC lines.
2. **Le message « condition trop courte » dit où corriger** — apports à caler
   (→ classeur) vs autres conditions limites (→ modèle source).
3. **Seuil de bilan de masse 1 % → 5 %**, exposé au classeur et au plugin,
   et **affiché sous les jauges** de l'onglet Suivi. *Ce n'est pas un écart à
   la cible* : c'est le « volume accounting error » du solveur.
4. **Contrôle de durée remonté au pré-vol** — à « Composer et contrôler », plus
   seulement dans le sous-processus détaché.
5. **Le plugin propose de prolonger les cibles par des zéros**
   (`noyau.prolonger_cibles`).
6. **Bouton « Installer… »** qui crée l'environnement Python HEC-RAS
   (`noyau.installer_interpreteur`).

**Vérifié** : les 12 suites passent, archive reconstruite et conforme, garde-fou
adverse « TOUT PASSE ». **Rien n'a tourné sous QGIS** ni sur un calcul HEC-RAS.

**Par quoi reprendre** : réinstaller le greffon (son dossier a disparu du
profil QGIS le 30/08 vers 09:40), puis relancer le calage — le seuil à 5 %
laissera passer le calcul de référence.

---

**Ajout du 28 août 2026** — réorganisation du dépôt Git pour la visibilité
GitHub : la chaîne Python (calage.py, criteres.py, etc., 15 modules) a
déménagé dans `src/` ; `calage_apports/` (plugin QGIS), la note
méthodologique, le template et `STATUT.txt` restent à la racine.
`noyau.chaines_candidates()` a été adapté en conséquence et tout a été
vérifié en exécutant réellement les auto-tests, pas seulement relu. Détail
complet en tête de `STATUT.txt`. Sans rapport avec le sujet méthodologique
ci-dessous.

Dernière mise à jour méthodologique : **4 août 2026 (suite 3) — en Mode_rapide, Δt n'est
plus forcé à zéro au calcul de référence, et φ n'est plus mesuré par
corrélation : les deux sont remplacés par la méthode manuelle vérifiée par
l'utilisateur** (Δt mesuré une fois sur le résiduel, pic contre pic, gardé
fixe ; φ = −Δt, analytique). Corrige un défaut réel du Mode_rapide devenu
défaut la veille : correct sur la section 1 (proche de l'injection, par
chance), faux sur les suivantes. Voir la session ci-dessous. **Non encore
rejoué sur un vrai calcul HEC-RAS.**

### Session du 4 août 2026 (suite 3) — Δt mesuré au résiduel, φ = −Δt en Mode_rapide

**Demande utilisateur**, après avoir observé un calage réel : l'hydrogramme
d'apport n'est pas inséré au bon instant — correct pour la section 1, faux
pour les suivantes. Décrit lui-même, et vérifié à la main, la méthode
attendue : mesurer Δt **une seule fois**, sur le calcul de référence
(apports à zéro), entre le pic obtenu à la section et le pic de la cible ;
garder cette valeur **fixe** pour tous les essais suivants ; écrire la
correction `apport(t) = cible(t − Δt) − section(t)`, plancher à zéro. Pas de
moindres carrés, pas de remesure.

**Cause exacte.** `caler()` forçait `decalage_zero` à 0.0 en Mode_rapide
([calage.py:1421](calage.py#L1421) avant correctif), sous l'hypothèse
« section proche de l'injection » — vraie par chance pour la section 1 du
modèle de l'utilisateur, fausse pour les suivantes, dont le résiduel porte
déjà un temps de transfert réel (amont non calé + apports déjà validés).
φ, de son côté, était mesuré par corrélation croisée à chaque essai jusqu'à
verrouillage — une « stratégie lourde » que le Mode_rapide est censé éviter.

**Vérification mathématique, faite avant de coder** :
`ecart_en_temps_apport` implémente `manque(u) = ecart(u + φ)` où
`ecart(t) = cible(t) − section(t + Δt)`. En posant `φ = −Δt` :
`manque(u) = cible(u − Δt) − section(u)` — exactement la formule de
l'utilisateur. Et `dephasage_reponse` documente elle-même `φ = L − Δt` où
`L` est le temps de transfert de l'apport à la section : poser `φ = −Δt`
revient à dire **L = 0**, la même hypothèse que le gain figé à 1. La
méthode demandée n'est donc pas une approximation : c'est l'hypothèse 1 du
Mode_rapide, appliquée sans la mesurer une seconde fois.

**Modifications, `calage.py` uniquement :**
- `decalage_zero` toujours mesuré (`decalage_minimisant_ecart` sur le
  résiduel), dans les deux modes — plus de forçage à zéro.
- En Mode_rapide, `dephasage_apport` est fixé une fois à `-decalage_zero`
  avant le premier essai, et le bloc de mesure de φ par corrélation
  (`dephasage_reponse`) est entièrement sauté. Hors Mode_rapide : inchangé.
- Boucle des essais : `decalage = decalage_zero` en Mode_rapide (plus de
  variable `decalage_verrouille`, plus de remesure au premier essai).
- Nouveau `Configuration.fenetre_marge_h` (défaut 1,0 h) : marge fixe
  ajoutée de chaque côté de la fenêtre du hydrogramme principal après sa
  détection (ou ses bornes imposées), bornée à l'étendue des données —
  appliquée telle quelle, sans logique particulière pour les bornes
  imposées à la main (demande explicite de simplicité). Pas exposée au
  classeur/plugin.

**Vérifié** : `calage.py` (14 contrôles neufs — égalité exacte formule
manuelle / code à 2,84e-14 près ; Δt mesuré non nul sur un modèle minimal
dédié, `ModeleResiduelDecale`, car le modèle fictif standard ne peut pas
reproduire un résiduel décalé indépendamment de l'apport ; marge de fenêtre
bornée aux données), `criteres.py`, `suivi.py`, `pont_hecras.py autotest` :
0 échec.

**Ce qui reste ouvert** : rien de tout cela n'a tourné sur un vrai calcul
HEC-RAS dans cette session. À confirmer par l'utilisateur sur son modèle
réel, sections 2 et suivantes : que `decalage_zero` mesuré au résiduel se
rapproche de ce qu'il a mesuré à la main, et que l'apport retenu tombe au
bon instant.

### Session du 4 août 2026 (suite 2) — mode rapide et masquage de l'injection par défaut

**Demande utilisateur**, juste après la mise à jour précédente : que le
défaut soit le mode rapide ET le masquage de l'injection (§ 5). Avant
d'appliquer, l'utilisateur a été prévenu que le cas de recette du projet a
un tronçon qui lamine fortement (gain hydraulique mesuré **0,076** — la
section ne rend que 7,6 % de ce qu'on lui injecte), et que la note
méthodologique marque explicitement le mode rapide comme réservé aux
sections proches du point d'apport, pas comme un remplacement de
l'algorithme par défaut. **Confirmé malgré cela** : le défaut global change
quand même, charge à chaque étude qui a besoin de l'algorithme à deux termes
de poser `Mode_rapide=non` dans son classeur.

**Ce qui a changé** :
- `Configuration.mode_rapide` (`calage.py`) : `False` → **`True`**.
- `Mode_rapide` dans le classeur (`creer_template.py`,
  `calage_apports/noyau.py`) et dans le fallback de lecture
  (`pont_hecras.py`) : `"non"` → **`"oui"`**.
- `Fenetre_active` reste vide par défaut (suit `Mode_rapide`) : le masquage
  de l'injection (§ 5) devient donc actif par défaut lui aussi, sans réglage
  séparé — c'est la logique déjà en place depuis le 03/08 (« la fenêtre suit
  le mode rapide, dont elle fait partie ») qui produit ce résultat sans
  aucun code neuf pour la fenêtre elle-même.
- Les deux démonstrations de précision de l'auto-test (§0 « test à blanc »)
  fixent maintenant `mode_rapide=False` explicitement (en plus de
  `tolerance_beta=0.005` déjà fixé la veille) : elles continuent de prouver
  la précision de l'algorithme à deux termes sur le modèle fictif qui lamine
  (11 %), une question indépendante des deux défauts de production.

**Vérifié** : `calage.py`, `suivi.py`, `livrables.py`, `pont_hecras.py
autotest` passent tous (0 échec) sous l'interpréteur `python` disponible
dans cette session. Archive du plugin régénérée (`faire_zip.py`, « archive
conforme »), **puis testée et confirmée par l'utilisateur en conditions
réelles avant cette mise à jour de la documentation**.

**Ce qui reste ouvert** : surveiller `gain_observe()` dans le journal des
prochains calages réels — c'est désormais le premier indice pour repérer
une section où `Mode_rapide=non` doit être reposé à la main.
`methodologie_calage_apport.docx` n'a pas été mis à jour (ni pour la
tolérance à 5 %, ni pour ce nouveau défaut) — à faire à la prochaine
occasion d'ouvrir Word.

### Session du 4 août 2026 (suite) — tolérance à 5 % et fenêtre du hydrogramme principal

**Demande utilisateur** : porter la tolérance par défaut sur l'écart de
volume à 5 % (au lieu de 0,5 %), et ne plus la juger que sur la fenêtre du
hydrogramme PRINCIPAL — un excédent dans une mini-crue qui commence et finit
avant (ou après) l'événement calé ne doit pas être vu comme un problème, et
la « fenêtre de résultats » doit couvrir l'événement, pas la durée totale de
la donnée d'entrée fournie.

**Clarifié avec l'utilisateur avant d'écrire du code** — deux points
laissés ouverts par la demande initiale :
1. Comment déterminer les bornes du hydrogramme principal ? Réponse :
   depuis le premier calcul complet (résiduel, apports à zéro) — donc
   l'infrastructure déjà posée le 03/08 pour la fenêtre d'injection du § 5
   (`calage.fenetre_injection`, sur l'écart au résiduel) est réutilisée
   telle quelle, mais désormais pour le JUGEMENT et non plus seulement pour
   l'injection.
2. La restriction porte-t-elle sur le volume seul, ou aussi la pointe et la
   couverture ? Réponse : les trois ensemble.

**Ce qui a changé, dans l'ordre :**

- `criteres.diagnostiquer()` gagne un paramètre `fenetre=(t0, tf)` : volume,
  pointe (le max n'est plus cherché que dans la fenêtre) et l'alerte de
  couverture (dont la référence redevient la durée de l'ÉVÉNEMENT, pas celle
  de toute la série d'entrée) y sont tous les trois restreints. `None`
  (défaut) = comportement inchangé. Le `Diagnostic` retourné porte
  désormais `fenetre`, et `resume()` l'affiche quand elle est fournie.
- `calage.py`, boucle par apport : la fenêtre du hydrogramme principal
  (`fenetre_injection` sur l'écart au résiduel) est désormais **toujours**
  calculée — plus seulement en mode rapide / `Fenetre_active` — et elle sert
  à DEUX choses distinctes qu'il ne fallait pas confondre :
  - le **plancher de volume irréductible** et les deux refus « avant tout
    calcul » ne portent plus que sur l'écart DANS la fenêtre (hors fenêtre,
    l'écart est mis à zéro, même règle que pour le rephasage) ;
  - les trois `diagnostiquer()` de la boucle (par essai, vérification
    globale finale, sections amont dérivées) reçoivent cette fenêtre —
    `ResultatApport` porte un nouveau champ `fenetre_principale` pour la
    transmettre jusqu'à la vérification finale.
  - Le masquage de l'INJECTION elle-même (forcer l'apport à zéro hors
    fenêtre, § 5) reste, lui, optionnel et gouverné par `Mode_rapide` /
    `Fenetre_active` comme avant : la fenêtre restreint désormais le
    JUGEMENT dans tous les modes, sans changer par défaut où l'apport
    est écrit.
- `Configuration.tolerance_beta` : 0,005 → **0,05**. Même changement sur les
  defaults lus/écrits dans le classeur (`creer_template.py`,
  `calage_apports/noyau.py`, `style_classeur.py`, `pont_hecras.py`) et dans
  le plugin QGIS (`calage_apports/plugin.py`,
  `TOLERANCE_VOLUME_DEFAUT` et l'infobulle du champ).

**Un test existant du projet documentait exactement l'ancien problème, et sa
prémisse est devenue obsolète par construction.** `calage.py` avait un
scénario « PLANCHER AU-DELA DE LA BANDE » : un débit de base constant de
12 m³/s sous une cible qui se tarit, refusé avant tout calcul. C'est
précisément le cas visé par le correctif (TODO de `STATUT.txt`, « les
tolérances par défaut sont-elles tenables ? ») : avec la fenêtre, cet excès
— qui ne se manifeste qu'APRÈS que la cible soit retombée — ne bloque plus
rien. Remplacé par deux scénarios : **« PLANCHER HORS FENETRE »** (le même
débit de base constant, ne bloque plus) et **« PLANCHER DANS LA FENETRE »**
(un débit de base constant sous une vallée ENTRE deux crues bimodales — donc
à l'intérieur de la fenêtre — continue de bloquer avant tout calcul). Les
deux vérifiés : la fenêtre restreint le jugement, elle ne désactive pas le
garde-fou pour un excès qui appartient réellement à l'événement.

**Le test à blanc de précision (§0, `Configuration(nb_max_essais=8)`) a
aussi dû être ajusté** — sans rapport avec un bug : il démontrait la
précision maximale atteignable par l'algorithme sur un modèle transparent
(gain connu), à l'ancienne tolérance resserrée de 0,5 %. Il pointe
maintenant `tolerance_beta=0.005` explicitement, pour continuer à démontrer
cette précision indépendamment du nouveau défaut de production (5 %), qui
répond à une question différente (la tenue des modèles à débit de base
marqué).

**Vérifié** : les 4 suites d'auto-tests touchées (`criteres.py`, `calage.py`,
`suivi.py`, `livrables.py`) passent intégralement sous l'interpréteur
disponible dans cette session (`python`, hors du venv habituel du projet,
indisponible sur ce poste — voir « L'interpréteur » plus bas, à revérifier
sur `D:\1-Python\.venv\Scripts\python.exe` à la prochaine occasion). 8
contrôles neufs dans `criteres.py` (§7 fenêtre, §8 défauts de tolérance), 4
contrôles neufs dans `calage.py` (les deux scénarios plancher).

**Non touché, et pourquoi** : `calage.cibles_pas()` (le volume/pic utilisés
par la CORRECTION, pas par le diagnostic) garde sa propre fenêtre — celle où
les deux séries existent après rephasage — le commentaire du code le disait
déjà explicitement (« Le DIAGNOSTIC, lui, n'est pas touché : il a sa propre
restriction de fenêtre »), et c'est exactement la séparation que ce
correctif complète. Les seuils `Fenetre_seuil_bas_pct`/`Fenetre_seuil_haut_pct`
(0,5 %/99 %, § 5) sont inchangés — c'est la PORTÉE de la fenêtre qu'ils
détectent qui s'élargit, pas leur valeur. `methodologie_calage_apport.docx`
n'a pas été mis à jour : il documente encore la tolérance de volume à 0,5 %
et ne mentionne pas la fenêtre appliquée au jugement — à faire à la
prochaine occasion d'ouvrir Word.

**Ce qui reste ouvert** : aucun calage réel n'a encore tourné avec ce
correctif — seuls les modèles fictifs des auto-tests l'ont exercé. À
vérifier au prochain calage HEC-RAS : que la fenêtre détectée et le
plancher restreint apparaissent bien dans le journal (`hydrogramme
principal ... h -> ... h`), et que la tolérance à 5 % ne masque pas un écart
que l'ingénieur voudrait voir malgré tout — la bande de POINTE, elle, reste
à ±2 %.

### Session du 4 août 2026 — la figure de la note n'était jamais livrée

**Le constat.** `01-cas_test/2-Resultats/resultats_finaux/` ne contient pas
`profil_en_long.png` — le profil en long de synthèse, celle des trois panneaux
(fond + ligne d'eau, débits de pointe, écart sur le pic) que reprend la note
méthodologique. Le seul exemplaire du projet est dans `livrables_exemple/`,
produit par l'auto-test de `livrables.py`. La note renvoyait donc à une figure
que l'étude ne livrait pas.

**La cause n'était pas dans la figure.** `produire_livrables_finaux` la trace
bien, mais sous `if profil is not None and len(profil)`, et ses trois arguments
`profil` / `pk_sections` / `pk_apports` valent `None` par défaut. L'unique
appelant réel, `pont_hecras.py`, ne les passait pas. La figure était donc
**impossible à produire par un calage réel**, sur n'importe quel modèle — et
**en silence** : la branche était sautée, pas en échec, donc pas même la ligne
« profil en long non produit » du `except`. Rien dans le log du cas test.

**Le correctif.** `_profil_pour_livrables()` dans
[pont_hecras.py:566](pont_hecras.py#L566) : il lit l'axe du classeur, construit
le profil par `geo.profil_depuis_modele` sur le **HDF de résultats** (le seul à
porter la ligne d'eau maximale — la géométrie ne l'a pas, d'où l'impossibilité
de partager le profil avec `_pentes_deduites`), et prend les PK dans
`cd.controler_geometrie` — **la même source que les contrôles**, donc la même
convention `PK_origine_m` / `Sens_axe` ; un axe déclaré `aval_amont` voit le
profil retourné, sans quoi les sections tomberaient à l'envers du fond. Trois
réglages du classeur restés lettre morte sont enfin lus : `Pas_profil_m`,
`PK_origine_m`, `Distance_max_axe_maillage_m`. **Chaque échec est désormais dit
au journal** au lieu de laisser la figure disparaître sans motif.

**Vérifié**, sur les données réelles du run du 3 août (`CETTE.p04.hdf`,
classeur `donnees_calage_tol_serrees.xlsx`) : profil de **77 points, PK
0 → 1 897 m**, sections à 350 / 562 / 880 m, injections à 297 / 539 / 795 m —
chaque apport bien en amont de sa section — et la figure sort avec ses trois
panneaux (pics 350 / 400 / 450 m³/s, écarts −1,2 / −1,2 / 0,0 %).
`pont_hecras.py autotest` passe. **Ce qui reste** : le `.png` du cas test n'a
pas été régénéré par la chaîne corrigée — cela demande un calage complet
(≈ 1 h 06). Tant qu'il n'a pas tourné, `resultats_finaux/` reste sans la
figure.

### À lire avant toute reprise — 3 août 2026, nuit

**0. LE JALON QUI MANQUAIT DEPUIS TROIS SESSIONS EST FRANCHI.** Calage complet
sur `01-cas_test/1-HECRAS/CETTE_TEST`, **conforme**, en **6 calculs et
49 min** :

| | essais | volume | pointe | forme | Δt |
|---|---|---|---|---|---|
| A1 → SC1 | 1 | 100,0 % | 95,4 % | 99,9 % | −0,90 h |
| A2 → SC2 | 2 | 100,9 % | **97,8 %** | 100,0 % | −1,70 h |
| A3 → SC4 | 2 | 100,1 % | 95,5 % | 99,6 % | −2,50 h |

**0 bis. REJOUÉ AUX TOLÉRANCES RESSERRÉES — ±3 % en volume, ±2 % en pointe.
Conforme, 8 calculs, 1 h 06.** C'est le run qui dit ce que valait le
précédent.

| | essais | volume | pointe | forme | plancher | φ |
|---|---|---|---|---|---|---|
| A1 → SC1 | 2 | 101,9 % | **98,8 %** | 99,9 % | 2,12 % | +0,87 h |
| A2 → SC2 | 2 | 100,8 % | **98,8 %** | 100,0 % | 0,96 % | +1,71 h |
| A3 → SC4 | 3 | 100,2 % | **100,0 %** | 100,0 % | 0,29 % | +2,53 h |

**Réponse à la question posée : A1 et A3 n'avaient PAS convergé, ils s'étaient
arrêtés dans une bande large.** A1 gagne 3,4 points de pointe (95,4 → 98,8 %),
A3 en gagne 4,4 (95,5 → 100,0 %). A1 s'arrêtait **dès l'essai 1**, donc sans
avoir jamais utilisé φ ; à ±2 % il en fait un second, et c'est là que φ agit.
La méthode allait plus loin que la bande ne le lui demandait.

**Et les apports retenus deviennent physiquement lisibles.** Leurs pointes
tombent à **5,2 / 5,3 / 5,5 h**, soit exactement `t_cible − φ`
(6,0−0,87 ; 7,0−1,71 ; 8,0−2,53), donc **en concomitance avec la pointe amont
à t = 5 h** — ce qu'exige un tronçon transparent. Avant le correctif, elles
tombaient à 6,0 / 7,0 / 8,0 h, c'est-à-dire dans la décrue de la section.

| apport retenu | pic | à t = | volume |
|---|---|---|---|
| A1 | 56,5 m³/s | 5,2 h | 218,6 |
| A2 | 63,2 m³/s | 5,3 h | 237,6 |
| A3 | 74,9 m³/s | 5,5 h | 256,0 |

**±0,5 % EN VOLUME EST IMPOSSIBLE SUR CE MODÈLE, ET CELA SE DÉMONTRE SANS
CALCUL.** Le plancher de volume irréductible vaut **2,12 %** sur SC1 et
0,96 % sur SC2 : la section dépasse déjà la cible sur une partie de
l'événement, un apport ne sait qu'ajouter du débit, donc le volume final ne
peut pas descendre sous 102,1 % sur A1. À ±0,5 %, la boucle refuse A1 avant
tout calcul et s'arrête là. **±3 % est la valeur la plus serrée qui laisse une
marge au-dessus du plancher** ; seul A3 (plancher 0,29 %) tiendrait à ±0,5 %.
La bande de POINTE, elle, est tenue à ±2 % partout — c'est elle qui juge la
méthode, le volume étant borné par l'état du modèle et non par l'algorithme.

Quatre plans conservés — `p01` « sans apport », `p02` `Apport_A1`, `p03`
`Apport_A2`, `p04` `Apport_A3` — livrables et classeur d'itérations complets,
**aucun incident de production**. Journal :
`01-cas_test/2-Resultats/calage_20260803_210300_reussi.log`.

Le run précédent, au même endroit, s'arrêtait sur A2 à **89,3 % de pointe**.

**Où est quoi.** `CETTE_TEST` porte le calage **resserré** (celui du 0 bis),
plans `p01`–`p04`, livrables dans `2-Resultats/`. Les deux états antérieurs
sont archivés et rien n'a été écrasé :

| dossier | contenu |
|---|---|
| `1-HECRAS/CETTE_TEST_cale_tol10_20260803/` | le calage à ±10 %/±5 %, plans et résultats |
| `2-Resultats/_run_20260803_reussi_tol10/` | ses livrables, son classeur, son journal, son classeur de paramètres |
| `1-HECRAS/CETTE_TEST_avant_calage_20260804/` | l'état d'avant tout calage (run échoué du 03/08 au soir) |
| `2-Resultats/_run_20260803_echec/` | le suivi et les journaux de ce run échoué |

Les tolérances resserrées sont dans un classeur **distinct**,
`2-Resultats/donnees_calage_tol_serrees.xlsx` — `donnees_calage.xlsx` était
ouvert dans Excel (fichier de verrou `~$donnees_calage.xlsx`) et n'a pas été
modifié : il reste le témoin du run à ±10 %.

**Point de départ et ce que le calage a touché.** Le modèle est remis à
l'état de `CETTE_BASE_PAS_TOUCHE` avant chaque run. **La géométrie
n'a pas bougé** — `CETTE.g02`, 720 230 octets, horodatage inchangé : les six
objets (`A1`/`A2`/`A3` en BC lines, `SC1`/`SC2`/`SC4` en reference lines)
préexistaient dans la géométrie de base. `pont_hecras.py caler` ne compose pas
la géométrie ; `Source_geometrie=SHP` ne concerne que l'étape « Composer et
contrôler » du plugin. **Le calage n'a écrit que dans l'Unsteady Flow et les
plans**, ce qui est exactement ce qu'on attend de lui.

**HEC-RAS était ouvert sur ce modèle et a été fermé avant le run** — le
projet documente qu'un plan calculé s'est déjà retrouvé vidé par l'interface.

**1. CE QUI BLOQUAIT : LA CORRECTION ÉTAIT ÉCRITE AU MAUVAIS INSTANT.**
Le classeur d'itérations montrait l'incohérence en clair — l'apport de pointe
passait de 68 à 118 m³/s entre deux essais et la pointe de la section
**baissait** (357 → 350). Le gain de pointe ressortait négatif, et la boucle
concluait « l'hydrogramme est trop ÉTALÉ ». Conclusion juste au vu de ce
qu'elle observait, et fausse : la correction tombait à côté.

Mesuré sur les séries du classeur : **la réponse du tronçon vaut exactement
l'apport injecté** — gain 1,000, retard nul, corrélation 1,000. Le tronçon
n'écrête rien du tout.

**Deux déphasages étaient confondus, et ils n'ont rien à voir.**

- **Δt**, le déphasage du **rephasage**, aligne la section sur la cible. Il
  mesure l'écart de calendrier entre le modèle et la cible — ici les entrées
  amont non calées font culminer toutes les sections à t = 5 h quand les
  cibles culminent à 6, 7 et 8 h. **L'apport n'a aucune prise dessus.**
- **φ**, le déphasage de la **réponse**, dit de combien la section rephasée
  suit l'apport qui l'a produite. Il vaut `L − Δt`, où `L` est le temps de
  transfert de l'injection à la section.

Sur SC2 : Δt = −1,86 h (le modèle est en avance), tronçon transparent donc
L = 0, donc **φ = +1,86 h**. Écrire la correction au temps où l'écart se lit
revenait à l'injecter **1,86 h trop tard**, dans la décrue au lieu de la
pointe. C'est tout ce qu'il y avait.

**Vérifié sur le vrai modèle, aux trois sections** : φ mesuré à +0,87 /
+1,67 / +2,49 h pour des Δt de −0,87 / −1,67 / −2,48 h. **φ = −Δt à 0,01 h
près**, ce qui est la signature d'un tronçon transparent, et ce qu'aucun
chiffre du projet ne disait avant.

**2. LE CORRECTIF** — `calage.py`, deux fonctions neuves.

- `calage.dephasage_reponse` mesure φ par **corrélation croisée des
  incréments** (variation d'apport contre variation de section rephasée). La
  corrélation, et non un minimum d'écart quadratique : un tronçon qui lamine
  rend une réponse d'amplitude différente, et un critère quadratique mêlerait
  le gain au déphasage. **Gratuit et disponible dès l'essai 1**, l'état sans
  apport servant de référence — donc φ est connu pour la première correction.
- `calage.ecart_en_temps_apport` ramène l'écart sur la base de temps de
  l'apport : `manque(u) = écart(u + φ)`. Hors du domaine calculé, **zéro** —
  jamais la dernière valeur connue (invariant 8).
- `fenetre_en_temps_apport` reçoit désormais **φ et non Δt**. Sa formule était
  juste, son argument faux : la fenêtre était ramenée **dans le mauvais sens**
  dès que le modèle est en avance sur la cible.

Le premier apport, lui, reste construit sur l'écart au résiduel avec φ = 0 —
aucune réponse n'a encore été observée. C'est pourquoi l'essai 1 de A2 rend
exactement les mêmes 89,3 % qu'avant le correctif : **le correctif ne se voit
qu'à partir de l'essai 2**, et c'est vérifié.

**3. LA COHÉRENCE DES APPORTS SE REFAIT À LA MAIN.** Contrôlé sur le nouveau
classeur : la correction posée entre deux essais est bien l'écart de l'essai
précédent **décalé de −φ**, à 0,03 h près sur A2 (r = 0,98) et 0,01 h près sur
A3. Sur A2, le pic de l'apport passe de t = 7,0 h (essai 1) à **t = 5,4 h**
(essai 2), et la pointe rephasée de 357 à 390 m³/s pour une cible à 400.

**4. Les tolérances de ce cas sont larges** — ±10 % en volume, ±5 % en
pointe, telles qu'elles étaient dans le classeur. A1 et A3 passent à 95,4 % et
95,5 % de pointe, donc **à 0,4 point du bord de la bande**. Le calage est
conforme, mais il n'est pas confortable sur ces deux sections : voir « Ce qui
reste ouvert ».

**1. Le bug qui détruisait des blocs de géométrie est CORRIGÉ.** Cause exacte :
`geometrie.supprimer_lignes_reference` délimitait un bloc « Reference Line »
en cherchant la **prochaine** ligne `BC Line Name=` ou `Reference Line Name=`.
La **dernière** reference line du fichier n'en a aucune après elle : la
recherche courait alors jusqu'à la fin du fichier et emportait tout ce qui
suit — `LCMann Region` et leurs tables, `Chan Stop Cuts`, `Composite Channel
Slope`, `GIS Limit At Bridges`, `GIS Ratio Cuts To Invert`, `Use User
Specified Reach Order`. Les compteurs de sections et de BC lines, eux, ne
bougeaient pas : le fichier semblait correct avec 629 lignes en moins.

Un bloc va désormais de sa ligne `Reference Line Name=` jusqu'à la dernière
ligne qui **lui appartient** — ses attributs (`Reference Line ...`) et les
lignes de coordonnées de son tracé. Toute autre ligne ouvre autre chose et
arrête le bloc. **Vérifié sur la vraie géométrie de CETTE_TEST2** (sur copie) :
retirer chacune des trois sections ôte 8 ou 9 lignes, et les huit blocs
voisins survivent tous.

**Le test qui aurait dû l'attraper l'avait manqué**, et pour une raison qui
méritait d'être corrigée : il vérifiait que le fichier **grossissait**. Le bug
le faisait rétrécir, mais le test ne posait des sections que si la couche
était vide — sur un modèle qui porte déjà les siennes, le remplacement est
sans perte et la taille ne bouge pas d'un octet. Trois assertions ont été
réécrites pour juger le **contenu** : aucun doublon, aucun bloc voisin perdu,
et le projet client comparé à **son propre état d'avant** plutôt qu'à la copie.

**2. La suite de tests écrivait dans un modèle de production.** Son chemin
était la valeur par défaut de `--geometrie`/`--plan`. **Corrigé** : plus
aucun modèle par défaut, il faut `--modele` ou `CALAGE_MODELE_ESSAI`, et à
défaut tous les essais qui écrivent sont ignorés.

**3. Le plugin exécutait une chaîne périmée.** `CHAINE_PAR_DEFAUT` était un
chemin unique écrit en dur qui gagnait quel que soit son âge ; le projet
ayant déménagé, le plugin tournait sur des sources vieilles de deux jours et
refusait des options que lui-même envoyait (`unrecognized arguments:
--remplacer`). **Corrigé** : entre plusieurs chaînes valides, c'est la
**date** qui tranche, jamais le rang. Voir `STATUT.txt`, « QUELLE CHAINE LE
PLUGIN EXECUTE ».

**4. Plus aucun modèle nommé dans le code.** Les mentions des cas de travail
ont été retirées de tous les modules : le plugin ne vaut que pour le modèle
désigné dans QGIS.

**5. Interface** : le groupe « Copies de travail et plans conservés » a
quitté l'onglet 1 pour l'onglet 4, sous « Calage » ; l'onglet 4 s'appelle
désormais « **4. Lancer le calcul des apports** ».

### Session du 3 août 2026, soirée — ce qui a changé

**A. La méthodologie V1.3 était intégrée aux trois quarts.** Vérification
faite point par point contre `methodologie_calage_apport.docx`. Étaient déjà
en place : la correction directe `A(n+1) = A(n) + [cible − rephasé]`, le
plancher à zéro, le déphasage figé (Δt = 0 à l'itération 0, mesuré au premier
essai à apport non nul, puis verrouillé). **Manquaient** : le § 5 (fenêtre
temporelle d'injection) et l'indicateur de gain hydraulique observé. Les deux
sont ajoutés.

> **Une réserve sur le document, à trancher.** Le § « Convention de signe »
> écrit `Q_sim(t − Δt)` alors que le code lit `Q_sim(t + Δt)`. **Le code est
> physiquement juste** : un simulé en retard de Δt vérifie
> `Q_sim(t) = Q_cible(t − Δt)`, donc c'est bien `Q_sim(t + Δt)` qui se compare
> à `Q_cible(t)`. La *prose* du document dit d'ailleurs la bonne chose
> (« qu'un simulé en retard soit avancé ») — c'est sa **formule** qui est
> inversée. Comme le § exige que la convention « soit respectée
> strictement », il vaut mieux corriger le document que le code.

**B. Fenêtre d'injection (§ 5)** — `calage.fenetre_injection`,
`masque_fenetre`, `fenetre_en_temps_apport`. Hors fenêtre, l'apport est forcé
à zéro, **à chaque essai** et pas seulement au premier. Trois écarts assumés
avec la lettre du document, chacun mesuré :

1. **Le cumul porte sur la part positive de l'écart**, pas sur l'écart brut.
   Un écart brut change de signe dès que la section dépasse la cible quelque
   part ; son cumul n'est plus croissant et « 99 % du volume » n'y désigne
   plus rien d'unique.
2. **La fenêtre ne peut pas coûter plus que la bande de tolérance.** Les
   seuils 0,5 %/99 % laissent dehors du volume que l'apport ne fournira
   jamais ; au-delà de la bande, la concordance devient impossible **par
   construction**. Mesuré : sur le modèle fictif, `tf` à 99 % bloquait le
   volume à 98,8 % de la cible pour une bande de ±0,5 %, huit essais sans
   concordance. Les seuils ne peuvent donc qu'**élargir** la fenêtre.
3. **La fenêtre est ramenée en temps d'apport.** Détectée sur l'écart à la
   section, elle est en temps de *section* ; l'apport injecté à `t` ne se
   manifeste qu'à `t + Δt`. Sans ce recalage, la montée de l'apport était
   tronquée d'un temps de transfert entier.

**Par défaut, la fenêtre suit `mode_rapide`** — elle est une pièce de la V1.3,
et la V1.3 reste un mode optionnel, pas un remplacement. Activée dans le mode
par défaut, elle faisait passer le modèle fictif de 2 essais à 8 sans
concordance. `Fenetre_active` (oui/non/vide) force dans un sens ou l'autre.

**C. Gain hydraulique observé** — `calage.gain_observe`. Calculé a posteriori,
à coût nul, entre deux essais successifs, sur les seuls pas où l'apport a
varié, sections **rephasées** (sinon le temps de transfert se mêlerait au
gain). **Calculé dans les deux modes** : c'est en mode rapide qu'il est le
plus utile, puisque c'est là que le gain est *supposé* valoir 1 sans être
mesuré. Il ne pilote rien — il dit si l'hypothèse tient. Mesuré à 0,93–0,94
sur le modèle fictif, annoncé dans le journal, et signalé en clair quand il
sort de [0,8 ; 1,25].

**D ter. LA NOTE MÉTHODOLOGIQUE ET L'AIDE DU PLUGIN SONT REMISES EN
COHÉRENCE** avec la méthode réellement exécutée. Sauvegarde du document avant
reprise : `methodologie_calage_apport_avant_maj_20260804.docx`.

Dans `methodologie_calage_apport.docx` — **le numéro de version n'est pas
incrémenté**, la V1.3 désignant le mode `Mode_rapide` qui n'a pas changé ;
une ligne de révision l'annonce en tête :
- **la formule de correction était fausse sur deux points** :
  `A(n+1)(t) = A(n)(t) + [Q_cible(t) − Q_sim(t − Δt)]` devient
  `A(n+1)(t − φ) = A(n)(t − φ) + [Q_cible(t) − Q_sim(t + Δt)]` — le signe du
  rephasage **et** l'instant d'écriture ;
- le § « Convention de signe » disait la bonne chose en prose et l'inverse en
  formule. Corrigé, avec la démonstration (`Q_sim(t) = Q_cible(t − Δt)` donc
  c'est `Q_sim(t + Δt)` qui se compare à `Q_cible(t)`) ;
- **§ neuf « Déphasage de la réponse (φ) — où écrire la correction »** :
  φ = L − Δt, sa mesure par corrélation croisée des incréments, le cas réel
  qui l'a révélé, et **la limite de mesure à un quart de la durée de
  l'événement, au-delà de laquelle Δt et φ saturent en silence** ;
- **§ 5 Fenêtre** : cumul sur la **part positive** de l'écart, seuils qui ne
  peuvent qu'**élargir**, et fenêtre ramenée **par φ et non par Δt** ;
- **plancher de volume irréductible** : ajouté sous la contrainte physique,
  avec le refus avant tout calcul et les valeurs mesurées ;
- **périmètre** : la note décrit le mode rapide (`Mode_rapide = oui`) ; le
  mode par défaut et sa correction à deux termes sont désormais nommés ;
- **tableau de déroulement** : étapes 3 à 7 réécrites (Δt selon le mode,
  écart nul hors fenêtre calculée, mesure de φ, φ = 0 à l'itération 1).

Dans l'aide du plugin (`AIDE_HTML`), qui décrivait encore l'algorithme
d'avant le 1er août :
- « la cible est recalée sur la mesure » — **c'était l'inverse** ;
- « l'écart est lissé et corrigé à 90 % » — **le lissage vaut 1 (aucun) et la
  relaxation a été remplacée par un pas réglé sur la bande** ;
- ajout de Δt/φ, du plancher de volume, du fait que les tolérances se règlent
  dans le classeur, et de l'avertissement qu'une pointe qui stagne à volume
  juste **ne prouve pas** que la cible soit hors d'atteinte.

Aide passée de 6 390 à 8 666 caractères ; **99 contrôles QGIS, 0 échec**
(balises équilibrées, aucune liste vide).

**D bis. φ EST ÉCRIT EN TÊTE DE CHAQUE ONGLET D'APPORT** du classeur
d'itérations — celui qui porte les hydrogrammes et les graphes. Une phrase,
à la suite de la ligne A3, qui dit ce que φ représente, sa valeur, et qu'il
n'entre dans aucun calcul :

> *Déphasage de la réponse φ = +1,71 h — délai entre l'apport injecté et son
> effet sur la section rephasée. La correction est donc écrite 1,71 h plus tôt
> que l'écart qui la réclame. À ne pas confondre avec le décalage Δt des deux
> colonnes ci-dessous, qui aligne la section sur la cible. Informatif :
> n'entre dans aucun calcul.*

**Pourquoi il y figure** : les deux colonnes de décalage du récapitulatif
disent Δt, et **rien ne donnait à lire où la correction avait été écrite**.
C'est exactement la confusion qui a coûté deux sessions (invariant 12).

Écrit **à la suite de A3, jamais sur une ligne à lui** : la ligne 4 porte
l'en-tête du récapitulatif, et décaler le tableau déplacerait tout ce qui se
repère par son numéro de ligne — séries, graphiques, blocs par essai. Même
raison que pour la fenêtre d'injection. Transmis par un argument **facultatif**
de `suivi.enregistrer_essai` ; sans mesure de φ, rien n'est écrit. Quatre
contrôles le couvrent dans l'auto-test de `suivi.py`.

**D. Affichage** : la fenêtre et ses deux seuils sont consignés en tête de
chaque onglet du classeur d'itérations. **Reste à faire** : leur
matérialisation graphique et leur ajustement à la souris dans l'onglet 3, que
le § « Affichage » prévoit.

**E. Interface** : le groupe de l'onglet 4 s'appelle « **Apports à
déterminer** » et ne porte plus que le premier apport à caler. Le champ « Nom
du clone de géométrie » a disparu — le clonage ne se pilote pas, il n'a lieu
que si la géométrie est surchargée à l'onglet 1. Le paramètre
`Nom_clone_geometrie` continue d'être écrit dans le classeur, depuis la
constante `plugin.NOM_CLONE_GEOMETRIE_DEFAUT`.

**F. La pente des apports est PRÉ-REMPLIE** dans la feuille Correspondance à
la composition (`noyau.pentes_locales_apports`), avec la valeur que le calage
aurait déduite d'une case vide : moyenne du fond sur ±200 m autour de
l'injection, majorée de 20 %. **Aucun résultat ne change** — l'hypothèse
devient simplement visible et corrigeable. Ordre de priorité : saisie
précédente > pente déduite > case vide. Une saisie n'est jamais écrasée par
une recomposition. L'explication a quitté l'onglet 2 pour l'onglet 4, dans le
groupe « Classeur » — à côté du bouton qui ouvre le fichier où elle se corrige.

### Session du 3 août 2026, mode rapide — en bref

Demande utilisateur : prendre en compte, pour accélérer le calcul, les deux
hypothèses de `methodologie_calage_apport.docx` (v1.3) — gain hydraulique
figé à 1 (section de contrôle proche du point d'apport) et priorité à la
rapidité de convergence. Cette méthodo décrit un algorithme **plus simple**
que celui en place (correction à un seul terme, déphasage verrouillé après
la première injection, aucune stratégie lourde), à l'opposé de la correction
à deux termes construite le 1er août. Clarifié avec l'utilisateur : **mode
optionnel, pas de remplacement** — l'algorithme par défaut reste nécessaire
dès qu'un tronçon écrête ou lamine fortement (gain 0,076 mesuré sur le cas de recette).

Ajouté : `Configuration.mode_rapide` (calage.py), `False` par défaut, **zéro
changement de comportement sur l'existant**. Actif, il force le gain à 1,
verrouille le déphasage après le premier essai à apport non nul (au lieu de
le remesurer à chaque essai), et remplace la correction à deux termes par
`A(n+1) = max(A(n) + [cible − calculé rephasé], 0)` — sans relaxation, sans
recherche de pas, sans terme de pointe. Exposé dans le classeur comme
paramètre `Mode_rapide` (oui/non, défaut non) : `creer_template.py`,
`style_classeur.COMMENTAIRES`, `calage_apports/noyau.py`, `pont_hecras.py`.

Vérifié par auto-test sur le modèle fictif (laminage 11 %, gain réel proche
de 1 mais pas égal) : converge en 2 essais, écart de volume 0,45 %. Détail
complet dans `STATUT.txt`, section « MODE RAPIDE — HYPOTHESES DE LA
METHODOLOGIE V1.3 ». **Non éprouvé sur un calcul HEC-RAS réel** : seul le
modèle fictif l'a exercé.

### Session du 3 août 2026, en bref

Demande utilisateur : que la géométrie chargée/modifiée dans QGIS s'écrive
sur la géométrie HEC-RAS d'origine (jamais un clone à part), et que les
couches « Sections de contrôle » / « Lignes d'injection » se créent dans
QGIS même quand la géométrie n'a encore ni BC ni section — pour pouvoir les
dessiner. Le premier point était déjà acquis (écriture en place, vérifié en
lisant le code). Le second était bloqué par un cas non couvert :
`pont_hecras.commande_modele` refusait tout net une géométrie **jamais
prétraitée par HEC-RAS** (pas de `.gXX.hdf`), avant même de regarder le
texte — aucune couche n'apparaissait, pas même vide.

Corrigé par un repli sur le fichier texte `.gXX`, qui porte déjà le contour
de la zone 2D dès sa création dans l'éditeur de géométrie (avant tout
maillage) : `geometrie.perimetres_depuis_texte` (nouveau), `pont_hecras.
commande_modele` assoupli, `plugin.py._charger_couches_modele` message mis à
jour. Détail complet, auto-test et limites dans `STATUT.txt`, section
« GEOMETRIE VIDE — LES COUCHES QGIS SE CREENT MEME SANS PRETRAITEMENT ».
**Non vérifié sous QGIS réel** (indisponible dans cette session) : à
confronter à une vraie zone 2D neuve au prochain accès à un poste QGIS.

**Deuxième demande, même journée** : la case « Remplacer les objets de même
nom déjà présents » (onglet 1) devait disparaître, et l'écriture des couches
QGIS dans la géométrie devenir automatique au clic sur « Composer et
contrôler ». Fait, plus loin que demandé après clarification avec
l'utilisateur : remplacement désormais **systématique** (plus de case),
étendu aux **sections** en plus des injections (nouveau —
`geometrie.supprimer_lignes_reference`, car `ras-commander` n'a pas de
`replace_existing` pour les reference lines), et les deux combos séparés
« Couche des sections »/« Couche des injections » ont disparu : source
unique désormais, `self.couche_sections`/`self.couche_injections` (celles
chargées par « Charger les couches du modèle »). **Garantie vérifiée et
documentée** : ce remplacement ne touche jamais le fichier Unsteady Flow
(l'hydrogramme d'un apport déjà raccordé survit à toute recomposition) ni
une BC de sortie qui ne serait pas explicitement redessinée sous le même nom
dans QGIS. Détail dans `STATUT.txt`, section « LE REMPLACEMENT DEVIENT
SYSTEMATIQUE, ET AUTOMATIQUE A LA COMPOSITION ». **Non vérifié sous QGIS
réel** non plus.

## En une phrase

La chaîne cale des apports amont sur des hydrogrammes cibles aval dans un
modèle HEC-RAS 2D, pilotée depuis un plugin QGIS. Elle **conserve un plan par
étape**, sait **reprendre à un apport donné**, écrit un **classeur
d'itérations rephasé, complet de son état de départ et vérifiable à la main**,
et l'extension QGIS est **autoportante** (elle embarque la chaîne dans son
archive).

---

## Session du 1er août 2026 — les six correctifs d'injection

Session déclenchée par une question de l'utilisateur : *« pourquoi l'apport
injecté n'est pas l'écart à la cible, au moins pour la première itération ?
L'injection de tous les essais est systématiquement trop forte. »*

**Verdict : l'apport injecté ÉTAIT bien l'écart écrêté — mais l'écart à
l'état de départ, que le classeur ne montrait nulle part. Et la
sur-injection était réelle, structurelle, et jamais mesurée.** Six correctifs.

### Le diagnostic, en trois points

**1. Un décalage d'un rang dans la lecture du classeur.** `calage.py` construit
le premier apport par `max(écart au RÉSIDUEL, 0)` — apports à zéro. Le
classeur, lui, commençait à l'essai 1 : on y comparait l'écart *restant après*
l'essai 1 à l'apport qui l'avait *précédé*. Deux colonnes décalées d'un rang,
donc impossibles à faire coïncider. Vérifié : sur `D:\SUPP\3`, pic de l'apport
injecté = **53,8 m³/s**, exactement la marge à combler de 53,2 m³/s.

**2. L'écrêtage à zéro est un CLIQUET, et il se démontre.** Si l'on injecte
`max(cible − résiduel, 0)` et que le tronçon conserve le volume, la section
rend `∫cible + ∫max(résiduel − cible, 0)`. Le volume final **ne peut donc pas
descendre sous la cible** : il la dépasse exactement de l'aire où la section
était déjà au-dessus. Mesuré sur `D:\SUPP\3` :

| | plancher `∫max(résiduel−cible,0)` | sur-cote observée à l'essai 1 |
|---|---|---|
| A1 | **2,33 %** du volume cible | 2,2 % |
| A2 | **1,40 %** | 1,2 % |

Accord à 0,1 point : ce plancher n'est pas *une* contribution à la
sur-injection, c'est **toute** la sur-injection du premier essai. Cause
physique visible en queue de série : la section garde **9,00 m³/s constants**
jusqu'à t = 16 h quand la cible redescend à 0,51 — elle dépasse déjà la cible
sur **29 % des pas de temps**. Le garde-fou existant ne pouvait pas le voir :
il ne teste que la **pointe** (`max(manquant) <= 0`), et la pointe manquait
encore de 53 m³/s.

**3. La bande de tolérance n'était pas utilisée comme une bande.** Le pas de
correction valait `0,9 × déficit`, quelle que soit la situation. Sur A2, le
volume valait 101,5 % dès l'essai 1 — **déjà dans la bande ±5 %** — et la
boucle a continué d'ajouter du volume pendant deux essais pendant que la
pointe **baissait** :

| A2 | essai 1 | essai 2 | essai 3 |
|---|---|---|---|
| volume apport (% cible) | 16,0 | 17,1 | **19,0** |
| volume section | 102,2 % | 103,3 % | **105,2 %** |
| pic brut section | 360,9 | 357,7 | **347,0** |

Deux calculs HEC-RAS dépensés à dégrader le seul essai qui tenait.

### Les six correctifs

| # | Fichier | Correctif |
|---|---|---|
| 1 | `calage.calcul_rephase` *(nouveau)* | rephasage **+ masque de fenêtre**. `np.interp` ne refuse pas une abscisse hors domaine : il **plafonne**. Rephaser de −0,86 h une cible qui commence à t = 0 faisait lire le calcul avant son début, où np.interp rendait 0 → l'écart y valait la **cible entière**. Hors fenêtre, l'écart vaut désormais **zéro** : on ne réclame pas de débit là où l'on n'a rien mesuré. |
| 2 | `calage.volume_irreductible` *(nouveau)* | mesure le plancher. Comparé à la **bande** de volume **avant tout calcul** : au-delà, la concordance est impossible, l'apport est refusé avec sa cause, et cela ne coûte aucun calcul. |
| 3 | `calage.injection_initiale` *(nouveau)* | le premier apport garde la **forme** du déficit positif mais porte le **volume du déficit NET** : `max(e,0) × ∫e / ∫max(e,0)`. Facteur **1,000 quand il n'y a pas d'excédent** — cas nominal, aucun changement. 0,869 sur A1 de `D:\SUPP\3`. |
| 4 | `calage.pas_volume` *(nouveau)* + `corriger_apport` | le pas à un terme se règle sur la **bande** au lieu d'une relaxation aveugle. Sous la bande : il ferme l'écart exactement. Dans la bande : **plus rien à corriger**, on passe à une **sonde de pointe à volume constant** (on retire sur les flancs du manque, on ajoute au sommet, intégrale nulle) — le seul moyen de mesurer le gain de pointe sans dériver en volume. |
| 5 | `calage.caler` | `cibles_pas` mesure volume et pointe **sur la même fenêtre** (celle du rephasage). `volume_mesure` intégrait *tout* le calcul quand `volume_cible` n'intégrait que la cible : 72 h contre 18 h donnait un rapport de 4, et le domaine admissible de `pas_admissible()` était bâti sur une comparaison sans objet. **Le diagnostic n'est pas touché** — il a sa propre restriction de fenêtre. |
| 6 | `calage.caler` | l'**arrêt démontré** se déclenche au **bas** de la bande (`volume >= 1 − tol`), plus seulement au-dessus. Rejoué sur A2 : gain de pointe **−0,116** mesuré à l'essai 2 → arrêt à l'essai 2, l'essai 3 (104,5 % / 86,8 %) n'aurait pas été calculé. |

### Et une consigne de méthode, donnée en cours de session

> *« L'apport n'a pas à être physique ou lissé : on peut avoir d'énormes
> variations, seul le débit final compte. »*

`Configuration.lissage_deficit` passe de **9 à 1** (aucun lissage). L'apport
n'est pas un hydrogramme observé, c'est **la commande d'un asservissement** :
seul compte le débit obtenu **à la section**. Lisser sur 9 pas (0,9 h à 6 min)
étalait la correction de part et d'autre de chaque instant, donc **ratait la
pointe** qu'elle devait combler et **déversait du volume** là où il n'en
manquait pas — précisément les deux griefs constatés.

Le paramètre reste, pour un seul usage : `lisser()` documente une mesure — au-delà
de **1 % de bruit numérique** sur la section lue, la correction additive
**diverge** sans lissage. Sur un modèle qui rend une section bruitée, remonter
ce paramètre est le remède. Mais c'est alors le bruit qu'on traite, pas
l'apport qu'on rend présentable.

**Le plancher à zéro reste la seule contrainte de forme**, et il n'est pas
cosmétique : un apport négatif serait un prélèvement, que la méthode ne prévoit
pas. C'est lui qui crée le cliquet — les correctifs 2 et 3 en traitent la
conséquence, ils ne le suppriment pas.

### Le classeur d'itérations porte désormais l'état de départ

`suivi.enregistrer_residuel()` *(nouvelle méthode)* + `EtatApport.residuel_detail`
*(nouveau champ)*. L'onglet s'ouvre sur un **bloc « Résiduel (apports à
zéro) »**, aux mêmes quatre colonnes qu'un essai, suivi des essais. La lecture
se fait **en escalier** : l'écart d'un bloc donne l'apport du bloc suivant.
Une ligne en A3 annonce en clair le plancher de volume et le facteur du premier
apport. L'onglet s'ouvre **dès le bloc résiduel**, sans attendre le premier
calcul — soit une vingtaine de minutes gagnées sur un vrai modèle.

---

## État

- **UN CALAGE COMPLET EST ALLÉ AU BOUT SUR HEC-RAS**, 3 apports sur 3,
  conforme, 6 calculs, 49 min. Voir en tête de ce fichier. Ce n'est plus le
  jalon manquant.
- **Les 13 suites d'auto-tests passent** sous l'interpréteur du projet, et la
  suite QGIS rend **99 contrôles, 0 échec** sous `python-qgis-ltr.bat`,
  exécutée sur une **copie** de `CETTE_TEST` (supprimée après coup, l'original
  vérifié intact).
  **Attention au modèle d'essai qu'on lui donne** : sur `CETTE_TEST2` la même
  suite rend **8 échecs**, tous en cascade d'un seul fait — ce modèle n'a
  **aucun plan calculé** (`.pXX.hdf`), donc le plugin ne peut pas s'y
  pré-remplir (« choisir un plan de référence »). Ce n'est pas une régression :
  la suite a besoin d'un modèle portant des résultats.
- **Contrôles neufs de cette session** : 12 dans `calage.py` sur le déphasage
  de la réponse — mesure de φ (en phase, en retard, en avance, sous
  laminage), refus de conclure quand rien n'est mesurable, écart ramené en
  temps d'apport, bord du domaine à zéro, et **le cas qui a motivé le
  correctif rejoué en miniature** (modèle en avance : 66,8 % de pointe sans
  φ, 100,0 % avec).
- **Le modèle fictif converge toujours en 2 essais par apport**, 9 calculs
  pour 4 apports, volumes finaux 99,5 à 100,0 % — **inchangé**, le correctif
  n'y touche pas (φ y vaut zéro, la cible étant sur la base de temps de
  l'apport).
- **Revue de code avant mise en production, faite en fin de session.** Relevé
  outillé (AST) sur les 15 modules du projet : **aucun import inutilisé,
  aucune fonction de module morte**. Une seule suppression sûre appliquée —
  le littéral `0.05` était dupliqué entre `PAS_PHI_H` et le défaut `pas_h` de
  `dephasage_reponse`, alors que le commentaire de la constante annonçait
  être ce pas ; le défaut lit désormais la constante. **Valeur identique,
  signature inchangée** (`inspect.signature` rend toujours `0.05`).
  Deux éléments **délibérément conservés**, et il faut savoir pourquoi avant
  d'y toucher :
  - `classFactory` est la seule fonction du projet sans aucune référence :
    c'est QGIS qui l'appelle par son nom (invariant 1).
  - `apport_essai_precedent` et `apport_pour_phi` portent la même valeur mais
    **pas la même sémantique** — le premier démarre à `None` (donc
    `gain_observe` ne conclut rien au premier essai), le second à zéro (donc
    φ est mesurable dès le premier essai). Les fusionner changerait le
    journal du premier essai. Même remarque pour `section_rephasee_precedente`
    (déjà rephasée) et `section_brute_pour_phi` (brute, re-rephasée avec le Δt
    courant).
- **Archive du plugin régénérée** : `calage_apports.zip`, **258,5 ko**,
  20 entrées, « archive conforme », **et installée sous le profil QGIS `ISL`**
  (empreintes SHA-256 des 9 modules embarqués vérifiées identiques aux
  sources). **QGIS était ouvert pendant la mise à jour : l'extension doit
  être rechargée, ou QGIS redémarré, pour exécuter la chaîne corrigée.**
- **Pas de dépôt git.** Toute suppression est irréversible ; les écritures
  dans un modèle HEC-RAS passent par une sauvegarde horodatée.
- **`STATUT.txt` est à jour** des six correctifs, de la consigne « l'apport
  n'a pas à être physique ni lissé », et des règles qu'ils changent
  (correction, arrêt démontré, classeur d'itérations, tolérances lues comme
  des bandes, plancher de volume). Sa liste « À faire » y a été refondue en
  priorités.

## L'interpréteur

Le bon interpréteur est celui du projet :

```
D:\1-Python\.venv\Scripts\python.exe     (Python 3.13.11)
```

Il porte tout : `matplotlib`, `openpyxl`, `h5py 3.16.0`, `geopandas`,
`pyproj`, **`ras-commander 0.99.1`**. C'est aussi celui que le plugin
sélectionne tout seul (`noyau.interpreteur_hecras()` cherche
`<parent de la chaîne>/.venv/Scripts/python.exe`).

Sous les interpréteurs QGIS, deux suites échouent **pour des raisons
d'environnement, pas de code** :

| Interpréteur | Symptôme |
|---|---|
| `apps\Python312\python.exe` | `geometrie.py` : `AttributeError` sur `crs.to_string()` — **`pyproj` absent** |
| `apps\Python312\python.exe` et `bin\python-qgis-ltr.bat` | `pilote_hecras.py` : 2 échecs — **`ras-commander 0.98.2`**, voir « Bugs connus » |

`bin\python-qgis-ltr.bat` fait passer `geometrie.py` (il fournit `pyproj`),
mais pas `pilote_hecras.py`. **`bin\python.exe` ne fonctionne pour aucun
test** (« Could not find platform independent libraries »).

## Bugs connus

**1. `ras-commander 0.98.2` borne mal les tableaux d'hydrogramme.** *(cause
externe au projet, non corrigé)*

`RasUnsteady.identify_tables()` attribue à une condition limite les valeurs de
la **suivante** quand deux blocs `Boundary Location=` se suivent. Reproduit
sur un `.u01` minimal, même fichier et même module, seul l'interpréteur
change :

```
3.12.13 / ras-commander 0.98.2 -> AMONT lignes 4→7  (FAUX : avale les 3 valeurs de DEJA_FIN)
3.13.11 / ras-commander 0.99.1 -> AMONT lignes 4→5  (correct)
```

Conséquence si elle se produisait en production : `_recadencer_apports()`
réécrirait un apport avec 7 valeurs au lieu de 4 et perdrait la condition
limite voisine — **corruption silencieuse du fichier unsteady**.

**Pourquoi ce n'est pas critique aujourd'hui** : le plugin délègue ce travail
en sous-processus à `interpreteur_hecras()`, qui résout vers le venv du projet
(0.99.1). Le défaut ne se manifeste que si cet interpréteur pointe vers un
environnement à `ras-commander < 0.99`.

**À faire à la reprise** : `noyau.verifier_interpreteur()` contrôle que
`ras_commander` **s'importe**, pas sa **version**. Un minimum `>= 0.99` y
refuserait franchement un environnement dangereux. Même remarque pour
`verification_environnement.py`, qui affiche la version sans la juger.

**2. Auto-test de `suivi.py` en console cp1252.** Plante en
`UnicodeEncodeError` sur « → ». Passe avec `PYTHONIOENCODING=utf-8`.
`pont_hecras.py` force déjà sa sortie en UTF-8 ; `suivi.py` non.

**3. Essai p16 arrêté après 4 secondes** sans produire de résultats, cause non
établie (voir `STATUT.txt`).

**4. ~~A2 du cas de recette n'est calable par aucun apport additif.~~ FAUX —
c'était le bug du déphasage.** Ce diagnostic a été porté deux sessions
durant : volume atteint dès le premier essai, pointe 10 points trop bas, gain
de pointe négatif, donc « hydrogramme trop étalé, le levier est ailleurs ».
**A2 cale en 2 essais à 97,8 % de pointe** une fois la correction écrite au
bon instant. Rien n'était étalé : la correction arrivait 1,86 h trop tard.

**La leçon vaut au-delà de ce cas.** Un gain de pointe négatif ne prouve pas
que le tronçon lamine — il prouve seulement que **ce qu'on a ajouté n'est pas
arrivé où on l'attendait**. Avant de conclure qu'une cible est hors
d'atteinte, vérifier φ : si la réponse mesurée vaut l'apport (gain 1, retard
nul) et que la pointe recule quand même, le déphasage est en cause, pas
l'hydraulique. `gain_observe` et `dephasage_reponse` le disent tous les deux,
gratuitement, dans le journal.

## Vérifié sur le cas réel le cas de recette

Contrôlé sur les fichiers du calage du 1er août (plan de référence `p03`,
38 Mo, calcul réussi en ~19 min) :

| Contrôle | Résultat |
|---|---|
| Lecture des sections | `SC1`, `SC2`, `SC3` — 181 pas de temps chacune |
| Apports dans l'unsteady | `A1`, `A2`, `A3` présents |
| Résiduels (apports à zéro) | 296,8 / 295,9 / 295,3 m³/s |
| Cibles | 350 / 400 / 450 m³/s |
| Marge à combler | +53,2 (15 %) / +104,1 (26 %) / +154,7 (34 %) |

**Point de vigilance SC1** : l'amont non calé fournit déjà **85 %** de la
cible. Il ne reste que 53 m³/s à trouver avec A1, et une petite erreur sur
l'amont y pèse lourd en proportion. Si le calage bute sur SC1, regarder
l'amont avant de mettre en cause A1.

## Le cas D:\SUPP\3 — LE DOSSIER N'EXISTE PLUS

**Vérifié le 03/08/2026 au soir : `D:\SUPP\3` est absent du disque.** Tout ce
que la section ci-dessous rapporte a été mesuré sur des séries qui ne sont
plus consultables. C'est conservé comme raisonnement, pas comme référence
vérifiable — et le cas de recette `01-cas_test` le remplace désormais, avec
un calage complet à l'appui.

## Le cas D:\SUPP\3 — ce qu'il donnait

C'est le cas qui a déclenché les deux dernières sessions. Apport A1 → section
SC1, cible 350 m³/s, discrétisation 6 min (161 pas, 0 à 16 h), **tolérances de
5 %**. Dernier run (1er août, 16 h 26) : **A1 validé en 1 essai** (volume
102,3 %, pointe 96,8 %), **A2 échoué en 3 essais** pour éloignement.

Ce que les correctifs y changent, **rejoué sur les séries du classeur** :

| | plancher | ancien apport essai 1 | nouvel apport essai 1 |
|---|---|---|---|
| A1 | 2,33 % | pic 53,78 m³/s, volume 17,72 % | pic **46,72**, volume **15,39 %** (facteur 0,869) |
| A2 | 1,40 % | pic 68,50 m³/s, volume 15,99 % | pic **62,52**, volume **14,60 %** (facteur 0,913) |

Le volume de l'essai 1 devrait donc revenir de 102,3 % à ~100,0 % sur A1. **La
pointe n'est pas prévisible hors calcul** : injecter moins au pic peut la faire
baisser. C'est le compromis assumé, et la bande ±5 % le couvre sur ce cas.
Sur A2, l'arrêt démontré tombe à l'essai 2 (gain de pointe −0,116) : **un
calcul HEC-RAS économisé et le meilleur essai conservé**.

`D:\SUPP\3\suivi\` contient encore `iterations.xlsx` (run du 16 h 26, **sans**
les correctifs) et `iterations_rephase.xlsx` (démonstration du rephasage,
session précédente). **Les deux sont antérieurs aux correctifs.**

## Ce que la méthode ne fait pas — à savoir avant de lire un résultat

**Elle ne cherche pas à annuler le temps de propagation.** Le déficit est
injecté sur la base de temps de la **cible**, donc la réponse de la section
arrive en retard du temps de transfert. Un calage conforme peut présenter un
hydrogramme décalé : volume, pointe et forme concordent, la dynamique non.
C'est le choix du § 1.5. Le diagnostic rapporte ce décalage (`decalage_h`) et
alerte au-delà de `Decalage_max_h`.

Mesuré sur modèle fictif à 2,5 h de retard par bief : A1 converge avec
volume 100,0 % et pointe 100,0 %, pour un décalage de +2,50 h.

**Ce qu'elle fait en revanche, depuis le 03/08/2026 : elle écrit la
correction là où celle-ci agira.** Ne pas confondre les deux. Le décalage
final reste affiché et non corrigé (−0,90 / −1,70 / −2,50 h sur le cas de
recette) ; ce que φ corrige, c'est **l'instant d'injection**, sans lequel la
correction ne rejoint jamais la pointe qu'elle vise. Renoncer à reproduire la
dynamique n'obligeait pas à injecter à contretemps.

**Corollaire** : c'est le débit **rephasé** qu'il faut comparer à la cible. Le
débit brut porte en plus le temps de transfert, que la méthode ne prétend pas
corriger.

**Et elle ne peut qu'ajouter du débit.** Deux refus en découlent, tous deux
prononcés **avant** le moindre calcul : la cible sous la pointe résiduelle, et
le **plancher de volume au-delà de la bande** (correctif 2).

## Essais de méthode du 1er août 2026

**La correction à deux termes est démontrée meilleure sur le banc synthétique,
pas sur le modèle réel.** Voir `synthese_test.docx` pour le détail chiffré.

- **Banc** : −43 % de calculs en régime d'écrêtement fort (23 → 13), pointe
  98,4 % → 100,0 %.
- **le cas de recette, trois campagnes sur clone** : A1 convergé, **A2 en échec**, A3
  jamais traité. Non conforme dans les trois cas.
- **Réglage le plus utile mesuré** : à 5 % de tolérance, plafonner à 1 essai
  donne un état final identique à 6 essais, pour 3 calculs au lieu de 5
  (16,7 min contre 28,7).

## Méthodologie de traçabilité — un plan par étape

| Étape | Contenu |
|---|---|
| `sans apport` | état de référence, tous les apports à caler à zéro |
| `Apport_A1` | recherche puis résultat de A1 |
| `Apport_A2` | cloné du précédent, qui garde A1 calé |

La première étape ne clone rien — `preparer()` vient de créer un plan neuf,
`jalonner()` le titre. Les suivantes clonent le jeu courant, si bien que
l'étape précédente reste figée **avec ses résultats**.

**Le ménage ne supprime plus les plans.** Seules partent les traces de
préparation. La seule suppression autorisée est le remplacement d'un
**homonyme** issu d'un calage précédent. Contrepartie assumée : un modèle à
trente apports garde trente et un jeux de résultats.

**Reprise** : le paramètre `Premier_apport` (vide = tous) fait repartir le
calage du plan `Apport_<précédent>`. Si le plan d'étape est absent, le calage
part du plan de référence avec un avertissement explicite.

**Classeur d'itérations** : `<suivi>/iterations.xlsx`, un onglet par apport,
réécrit à chaque essai. **Un bloc « Résiduel (apports à zéro) »** puis un bloc
par essai, quatre colonnes chacun : section, section **rephasée**, écart
`cible − rephasée`, apport injecté. **Lecture en escalier : l'écart d'un bloc
donne l'apport du bloc suivant.**

## Extension autoportante — comment ça marche

L'archive porte une copie complète de la chaîne dans `calage_apports/chaine/`
(9 modules). Sur un poste neuf, installer l'extension suffit.

Deux règles protègent de la divergence entre les deux copies :

1. **La copie n'existe que dans le zip**, jamais sur le disque. `faire_zip.py`
   lit les modules à la racine et les écrit directement dans l'archive.
   Personne ne peut éditer la copie en croyant toucher la source.
2. **Elle sert en dernier recours.** Ordre de recherche : dossier déclaré à
   l'exécution → `CALAGE_CHAINE` → parent du plugin → `d:\1-Python\calage_des_apports`
   → copie embarquée. Sur le poste de développement, les sources vives gardent
   la priorité, et une archive ancienne ne les masque jamais.

La liste des modules embarqués est **calculée** par fermeture des imports
(`faire_zip.modules_chaine`), jamais écrite à la main. `faire_zip.py` refuse de
livrer une copie qui diffère de sa source.

`chaine_disponible()` affiche la provenance retenue : `(embarquee dans le
plugin)` ou `(externe au plugin)`. **C'est la première chose à regarder devant
un correctif qui semble sans effet.**

## Par quoi reprendre — par ordre de priorité

> **PÉRIMÉ — ne pas reprendre par ici.** Cette liste date du 1er août 2026.
> Elle raisonne sur `Decalage_max_h`, seuil **retiré le 08/08/2026**, et sur
> une tolérance de volume de 0,5 % qui vaut 5 % depuis le 30/08. Elle est
> gardée comme récit. **La liste en vigueur est la section 6 de
> `STATUT.txt`**, et le point de départ est la session la plus récente, en
> tête de ce fichier.

0. **~~Resserrer les tolérances et relancer.~~ FAIT — voir 0 bis en tête.**
   Conforme à ±3 %/±2 %, et A1 comme A3 avaient bien de la marge. Ce qu'il
   en reste à trancher : **faut-il changer les tolérances par défaut de
   `Configuration` ?** Elles valent 0,5 % en volume, et ce cas montre qu'un
   modèle au débit de base marqué peut être **hors d'atteinte par
   construction** à cette valeur (plancher 2,12 %). Deux voies : relever le
   défaut de volume, ou restreindre la fenêtre d'analyse à la crue pour faire
   tomber le plancher — c'est la piste que le motif de refus suggère déjà, et
   elle n'a jamais été essayée.
1. **Le déphasage croît vers l'aval — et DEUX seuils l'attendent, dont un
   silencieux.** Mesuré à 0,87 / 1,71 / 2,53 h, soit **+0,83 h par section**.
   Une 4ᵉ section tomberait vers 3,4 h, une 5ᵉ vers 4,2 h.

   **Ce que `Decalage_max_h` fait vraiment — vérifié dans le code, ce n'est
   pas un simple avertissement.** Il vaut 3,0 h, **n'est pas exposé dans le
   classeur** (aucun paramètre correspondant : il ne se règle que dans
   `Configuration`), et le franchir ajoute une chaîne dans `diag.alertes`
   (`criteres.py`, `diagnostiquer`). Or :
   - **la boucle de recherche ignore `alertes`** — `concordance()`,
     `admissible()` et `rang_essai()` ne testent que volume, pointe et forme.
     Chaque apport est donc validé normalement ;
   - **la vérification globale finale ne l'ignore pas** — `Diagnostic.converge`
     exige `not self.alertes` en plus des trois tolérances, et
     `resultat.conforme = all(d.converge ...)`.

   Conséquence : tous les apports seraient annoncés validés, puis le calage
   ressortirait **NON CONFORME après coup**, avec le motif *« dérive détectée
   à la vérification globale : relancer une passe séquentielle amont →
   aval »* — **qui désigne une dérive inexistante**. La vraie cause n'est que
   dans `diag.alertes` (colonne « Alertes » de `tableaux_calage.xlsx`). On
   chercherait longtemps.

   **Le second seuil est plus bas en pratique, et totalement muet.** La
   MESURE du déphasage est bornée à `0,25 × durée` de l'événement, soit
   **±4,0 h** sur la fenêtre de 16 h — pour `decalage_minimisant_ecart` (Δt)
   comme pour `dephasage_reponse` (φ). Au-delà, les deux **saturent au bord
   du domaine de recherche sans que rien ne le dise**, et la correction se
   place au mauvais endroit avec des pourcentages qui restent plausibles.
   Le diagnostic, lui, cherche plus loin (`_decalage_pas`, n/3 pas ≈ ±5,3 h).

   À trancher avant d'enchaîner plus de trois sections : relever
   `Decalage_max_h`, ou recaler l'origine des temps des cibles sur celle du
   modèle. Et, indépendamment, **faire dire au motif final quelle alerte l'a
   provoqué** — c'est un correctif de traçabilité, pas de méthode.
2. **Rendre CETTE_TEST2 calculable, si l'on veut caler CE modèle-là.** La
   fenêtre de simulation du plan `p15` couvre **18 h** (06SEP2024 01:00 →
   19:00), alors que l'événement des cibles de
   `Hydrogrammes_Apports_CETTE.xlsx` se situe entre **23 h et 32 h** sur une
   base de 0 à 256 h : le calcul s'arrêterait avant le début de la crue.
   Étendre la fenêtre du plan, ou recaler l'origine des temps des cibles.
   Puis trancher le sort de `SC3` (cible sans section dans la géométrie de
   CETTE_TEST2, qui porte `SC4`, `SC1`, `SC2`).
   **Sans objet pour le calage qui vient d'aboutir** : celui-ci tourne sur
   `CETTE_TEST` avec le classeur `2-Resultats/donnees_calage.xlsx`, dont les
   cibles sont sur une base de 0 à 16 h, cohérente avec le plan.
2. **Verrouiller la version de `ras-commander`** (voir « Bugs connus », 1).
   Petit correctif, gros risque évité : un minimum `>= 0.99` dans
   `noyau.verifier_interpreteur()` et dans `verification_environnement.py`.
3. **Recréer le script de pré-vol.** Un script jetable a servi à contrôler,
   **sans lancer de calcul**, que les sections sont lisibles, que les apports
   existent dans l'unsteady et que les cibles sont atteignables. Il n'a jamais
   été versé au projet. Il devrait désormais afficher aussi **le plancher de
   volume** de chaque section : c'est le refus le moins cher du projet.
   Entrées : un `.pXX.hdf` de référence, le `.uXX`, le classeur.
4. **Borner l'analyse à la fenêtre de la cible.** Le correctif 5 l'a fait pour
   le **domaine du pas** ; `criteres.diagnostiquer` restreint déjà le volume à
   la fenêtre commune, mais le **KGE**, `r` et le recalage travaillent encore
   sur la grille qui **englobe** les deux séries. À borner, avec une marge
   paramétrable.
5. **Réserve non tranchée sur le déphasage cumulé.** Sur un modèle fictif
   volontairement brutal (2,5 h/bief **et** laminage cumulé), seuls 2 apports
   sur 4 calent : A3 s'arrête à 90,6 % de pointe. Impossible de dire si la
   méthode plafonne quand le déphasage s'accumule vers l'aval, ou si le
   modèle-jouet est hors domaine. À surveiller sur SC2 et SC3.
6. **Suppression restée en suspens dans le projet de recette** — soit
   `01-cas_test/1-HECRAS/<modèle>/`. Les clones `<modèle>.u01`/`u02`
   (+ `.hdf`) et les vestiges du calcul p01 interrompu
   (`<modèle>.p01.tmp.hdf`, `_compute_p01.log`, `<modèle>.bco01`,
   `<modèle>.ic.o01`) sont toujours en place. Sauvegarde déjà prise dans
   `_avant_suppression_20260731_194314/`. **Après suppression, éditer
   `<modèle>.prj`** : retirer les lignes `Unsteady File=u01` et
   `Unsteady File=u02`, et remplacer `Current Unsteady=u02` par
   `Current Unsteady=u06`.
7. **Renseigner la pente dans le classeur avec la valeur par défaut mesurée
   sur le profil en long.** La colonne `Pente_m_par_m` (feuille
   *Correspondance*) l'est déjà : `noyau.pentes_locales_apports()` la
   pré-remplit depuis le PL (`geometrie.pente_locale` — moyenne du fond sur
   ±200 m, majorée de 20 %), et une saisie n'est jamais écrasée. Le paramètre
   `Pente_apport_creee_m_par_m` (feuille *Configuration*), lui, est écrit
   **vide**, et un apport **créé** par le plugin reçoit
   `PENTE_APPORT_DEFAUT = 0.01` **en dur**
   (`calage_apports/plugin.py:403`, employée à la création). Un 1 % arbitraire
   alors que la pente du tronçon est mesurable au même endroit : y porter la
   pente locale au PK de l'injection, et l'écrire dans le classeur pour que
   l'hypothèse soit visible et modifiable — même règle que pour
   `Pente_m_par_m`. Repli sur 0,01 si le PL n'est pas calculable (géométrie
   non prétraitée par HEC-RAS).
8. **~~La figure de la note méthodologique n'est jamais livrée.~~ CORRIGÉ le
   4 août — voir la session en tête.** `_profil_pour_livrables()` est en place
   dans [pont_hecras.py:566](pont_hecras.py#L566) et ses trois valeurs sont
   passées à `produire_livrables_finaux`
   ([pont_hecras.py:1241](pont_hecras.py#L1241)). **Ce qu'il en reste** : la
   vérification sur un calage réel. `01-cas_test/2-Resultats/resultats_finaux/`
   **n'a toujours pas** `profil_en_long.png` — le run du 3 août est antérieur au
   correctif, et le régénérer demande un calage complet (≈ 1 h 06). Au prochain
   run, contrôler que le `.png` y est, qu'il porte ses 3 panneaux, et qu'il
   figure dans la liste des livrables. Si la figure manque encore, la raison
   est désormais **écrite au journal** — la chercher là.
9. **Trois clones d'essai à supprimer** dans `01-cas_test/1-HECRAS/` :
   les dossiers suffixés `_ESSAI`, `_REJEU6`, `_REJEU1`, et leurs dossiers
   de résultats `2-Resultats_ESSAI`, `2-Resultats_REJEU6`,
   `2-Resultats_REJEU1`.

## Repères de code

| Besoin | Où |
|---|---|
| Règles en vigueur, pièges mesurés | `STATUT.txt` |
| Boucle de calage, indépendante du solveur | `calage.py` |
| Lecture du résiduel, ordre lecture/jalon | `calage.caler`, début de la boucle par apport |
| Étapes conservées, reprise | `pilote_hecras.jalonner`, `plan_par_titre` |
| Mesure du décalage (correction) | `calage.decalage_minimisant_ecart` — continue, sur la grille native |
| Mesure du décalage (diagnostic) | `criteres._decalage_pas`, `criteres.recaler` — au pas de `PAS_RECALAGE_H` |
| **Déphasage de la RÉPONSE (φ) — où placer la correction** | `calage.dephasage_reponse` |
| **φ consigné en tête de l'onglet d'itérations** | `suivi.enregistrer_essai(dephasage_apport=...)`, `suivi._onglet_iterations` |
| **Écart ramené en temps d'apport** | `calage.ecart_en_temps_apport` |
| **Rephasage + masque de fenêtre** | `calage.calcul_rephase` |
| **Différence rephasée réinjectée** | `calage.ecart_a_la_cible` — nulle hors fenêtre |
| **Plancher de volume irréductible** | `calage.volume_irreductible` |
| **Premier apport (déficit net)** | `calage.injection_initiale` |
| **Pas réglé sur la bande, bande morte** | `calage.pas_volume` |
| **Sonde de pointe à volume constant** | `calage.corriger_apport`, repli sans gain de pointe |
| **Mode rapide (méthodologie V1.3, gain=1)** | `Configuration.mode_rapide`, branches dans `calage.caler` |
| **Fenêtre d'injection (§ 5 V1.3)** | `calage.fenetre_injection`, `masque_fenetre`, `fenetre_en_temps_apport` |
| **Gain hydraulique observé (diagnostic)** | `calage.gain_observe`, colonne `gain_observe` de l'historique |
| **Pré-remplissage de la pente par apport** | `noyau.pentes_locales_apports`, argument `pentes` de `preparer_classeur` |
| **Profil en long de synthèse dans les livrables** | `pont_hecras._profil_pour_livrables` → arguments `profil`/`pk_*` de `produire_livrables_finaux` |
| **Délimitation d'un bloc « Reference Line »** | `geometrie.supprimer_lignes_reference` — attributs + coordonnées, RIEN d'autre |
| **Domaine du pas, sur fenêtre commune** | `calage.caler`, construction de `cibles_pas` |
| Recherche exhaustive du pas (a, b) | `calage.pas_admissible` |
| **État de départ dans le classeur** | `suivi.Suivi.enregistrer_residuel`, `EtatApport.residuel_detail` |
| **Classeur d'itérations, blocs et graphes** | `suivi._onglet_iterations` |
| Analyse pure (recalage, KGE, volume) | `criteres.py` |
| Formats de fichier HEC-RAS | `pilote_hecras.py` |
| Cartographie des hydrogrammes de l'unsteady | `pilote_hecras.cartographier_hydrogrammes` |
| Pont ligne de commande QGIS → HEC-RAS | `pont_hecras.py` |
| Logique du plugin, testable hors QGIS | `calage_apports/noyau.py` |
| Choix de l'interpréteur HEC-RAS | `calage_apports/noyau.interpreteur_hecras` |
| Recherche et embarquement de la chaîne | `calage_apports/noyau.trouver_chaine`, `faire_zip.modules_chaine` |
| Enveloppe Qt | `calage_apports/plugin.py` |
| Idées non implémentées | `idees_V2_plugin.md` |

## Commandes utiles

**Interpréteur du projet** — celui qui fait passer les 15 bancs :

```bash
cd src                       # les modules de la chaîne s'exécutent depuis là
PY="D:/1-Python/.venv/Scripts/python.exe"
export PYTHONIOENCODING=utf-8          # console cp1252 : sinon les accents cassent

# 13 suites : les 11 modules auto-testables, le pont, le noyau du plugin
for m in calage criteres suivi livrables controle_donnees geometrie \
         style_classeur elaguer_projet creer_template \
         verification_environnement pilote_hecras; do "$PY" $m.py; done
"$PY" pont_hecras.py autotest
"$PY" ../calage_apports/noyau.py       # le noyau est HORS de src/

# + 2 bancs d'archive, qui ferment la liste des 15
"$PY" faire_zip.py                     # doit finir sur « archive conforme »
"$PY" essai_garde_fou_archive.py       # doit finir sur « TOUT PASSE »
```

**Plugin, sous l'interpréteur QGIS — 152 contrôles.** Trois conditions, et
aucune n'est facultative :

- `--modele` doit désigner une **COPIE** : la suite MODIFIE la géométrie du
  modèle qu'on lui donne. Copier `01-cas_test/1-CETTE/1-HECRAS/CETTE_TEST1`
  (166 Mo) hors du dépôt.
- le modèle doit porter au moins un plan **CALCULÉ**, sinon 8 contrôles
  échouent en cascade — ce n'est pas une régression.
- `CALAGE_PYTHON` doit désigner l'interpréteur HEC-RAS. Le greffon ne le
  trouve seul que si c'est un `.venv` **voisin de la chaîne**, ce que
  `D:\1-Python\.venv` n'est pas. Sans lui la lecture de la géométrie échoue,
  et la suite s'arrête en le disant.

```bash
export CALAGE_PYTHON="D:\1-Python\.venv\Scripts\python.exe"
M="<une copie de CETTE_TEST1, hors du dépôt>"
"C:\Program Files\QGIS\LTR\bin\python-qgis-ltr.bat" test_plugin_qgis.py \
    --modele "$M" --plan "$M\CETTE.p03.hdf"
```

**Fermer HEC-RAS avant tout calage.** L'interface réécrit les fichiers du
projet depuis sa mémoire et peut effacer ce que le calage y écrit.

Sous console cp1252, préfixer par `PYTHONIOENCODING=utf-8`.

## Douze invariants à ne pas casser

1. **`classFactory` dans `calage_apports/__init__.py`** n'a aucun appelant
   dans le code : c'est **QGIS** qui l'appelle par son nom.
2. **`_raccorder()` appelé seul au niveau module dans `noyau.py`** : un appel
   nu, dont on serait tenté de croire qu'il ne sert à rien. C'est lui qui
   insère la chaîne dans `sys.path` à l'import du module. Il portait
   auparavant le nom `DOSSIER_CHAINE`, retiré le 29/08/2026 : personne ne
   lisait cette valeur, et elle devenait fausse dès le premier
   `definir_chaine()`. Ne pas la réintroduire.
3. **La politique d'encodage est dupliquée dans trois modules**
   (`pilote_hecras._lire_texte`, `elaguer_projet._lire_texte`,
   `noyau._lire_texte_hecras`) parce qu'ils ne peuvent pas partager de code.
   Toute correction doit être reportée aux trois.
4. **`PiloteHecRas.jalonner()` ne modifie l'objet qu'une fois tout vérifié.**
   Un échec à mi-course laisserait le calage à cheval entre un plan et
   l'unsteady d'un autre.
5. **Rien ne doit être lu dans le plan courant entre un jalon et son calcul.**
   `jalonner()` ouvre un plan **vide de résultats** ; toute lecture de section
   doit précéder le jalon, ou suivre un `calculer()`. C'est le bug qui a
   bloqué le calage du 1er août. Deux auto-tests le gardent.
6. **`PAS_RECALAGE_H` doit SUIVRE `PAS_ENTREE_H`**, jamais être fixé
   indépendamment. Rééchantillonner plus **grossier** que la donnée quantifie
   le décalage, dégrade `r` et grignote la tolérance de volume.
7. **L'écart consigné dans `iterations.xlsx` doit rester celui que la méthode
   corrige** — `cible − rephasé`, positif quand il faut ajouter du débit —
   sous peine d'afficher dix fois la bonne valeur, avec le mauvais signe. Et
   le **bloc résiduel doit rester en tête** : sans lui, la première injection
   ne se rattache à rien de visible, et c'est exactement ce qui a fait croire
   que la méthode était fausse.
8. **Ne jamais lire hors de la fenêtre calculée sans le dire.** `np.interp`
   plafonne au lieu de refuser : tout rephasage doit passer par
   `calage.calcul_rephase` et honorer son masque. Un déficit fabriqué là où
   rien n'a été mesuré est indétectable dans les chiffres finaux.
9. **Les objectifs de volume et de pointe sont des BANDES, ±X %, pas des
   points.** Une correction qui vise le centre d'une bande déjà tenue ne
   corrige rien : elle dérive. Tout nouveau pas doit avoir sa **bande morte**,
   et tout garde-fou doit se juger au **bord** de la bande, pas au centre.
   Corollaire mesuré : le volume ne peut jamais descendre sous
   `cible + volume_irreductible`, et si cette somme sort de la bande, il faut
   **refuser avant de calculer**.
10. **Un bloc de géométrie HEC-RAS se délimite par ce qu'il CONTIENT, jamais
    par ce qui le suit.** Chercher « le prochain bloc de même famille »
    marche pour tous les blocs sauf le dernier, et le dernier emporte alors
    la fin du fichier. Un bloc « Reference Line » = sa ligne `Name=`, ses
    attributs `Reference Line ...`, ses lignes de coordonnées. Rien d'autre.
    C'est l'incident du 03/08/2026, et il n'était visible dans aucun
    compteur d'objets.
11. **Une restriction de fenêtre ne doit jamais coûter plus que la bande de
    tolérance.** Tout ce qu'on laisse hors de la fenêtre d'injection est du
    volume que l'apport ne fournira jamais : au-delà de la bande, la
    concordance est impossible **par construction**, et la boucle épuise ses
    essais sur un volume bloqué sans que rien ne dise pourquoi. Un seuil de
    fenêtre ne peut donc qu'**élargir**. Même famille de piège que
    l'invariant 8 : ne jamais réclamer, ni interdire, du débit en silence.
12. **Δt ET φ SONT DEUX GRANDEURS DIFFÉRENTES. Ne jamais passer l'une là où
    l'autre est attendue.** `Δt` (`decalage_minimisant_ecart`) aligne la
    section **sur la cible** : il mesure l'écart de calendrier entre le
    modèle et la cible, sur lequel l'apport n'a aucune prise. `φ`
    (`dephasage_reponse`) mesure de combien la section **rephasée** suit
    l'apport qui l'a produite, et vaut `L − Δt`. Tout ce qui s'écrit dans
    l'APPORT — la correction, la fenêtre d'injection — se ramène par **φ**.
    Tout ce qui se lit sur la SECTION se rephase par **Δt**. Les confondre ne
    déclenche aucune erreur, ne casse aucun compteur, et se manifeste
    uniquement par une pointe qui refuse de monter pendant que le volume est
    juste — que la boucle interprète alors, très raisonnablement, comme un
    tronçon qui lamine. C'est l'incident du 03/08/2026, et il a coûté deux
    sessions de mauvais diagnostic.
