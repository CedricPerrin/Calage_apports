# -*- coding: utf-8 -*-
"""
Contenu de la note methodologique V16.

COUPE FRANCHE (decision utilisateur 30/08/2026) : ~40 % de mots en moins par
RETRAIT de contenu, pas par reformulation. Ce qui est retire du corps :

  - toute justification historique (« on a essaye X, puis retire ») : elle
    part en ANNEXE B, d'un bloc. Le corps enonce la regle en vigueur, il ne
    raconte plus comment on y est venu ;
  - toute prose qu'une figure dit mieux : six figures neuves la remplacent ;
  - les redites entre le mode operatoire, la partie 1 et la partie 2.

Chaque entree est (genre, charge). Genres : h1 h2 h3 p bullet table figure
caption code note.
"""

CONTENU = [
    ("title", "Calage d'apports amont sur des hydrogrammes cibles en aval"),
    ("sous_titre", "Note méthodologique — Version 16"),
    ("p", "Détermine, pour un cours d'eau modélisé en 2D comportant plusieurs "
          "apports successifs, les débits à injecter en chaque point d'apport "
          "pour que le modèle restitue à chaque section de contrôle aval un "
          "hydrogramme cible imposé."),
    ("note", "Version 16 (8 septembre 2026) — deux réponses d'hydraulicien "
             "y entrent : l'absence de boucle hydraulique est une HYPOTHÈSE "
             "DU MODÈLE que la chaîne ne vérifie pas (§ 1.2), et le verdict "
             "de volume porte sur la fenêtre de l'événement, pas sur la crue "
             "entière (§ 1.4). Depuis la V15, les justifications historiques "
             "(essais, mesures, approches écartées) sont regroupées en "
             "annexe B ; le corps n'énonce que la règle en vigueur. Six "
             "figures remplacent les développements qu'elles disent mieux."),
    ("table", [
        ["Partie", "Contenu"],
        ["Mode opératoire", "ce qu'il faut préparer, et dans quel ordre. À "
         "lire en premier."],
        ["1 — Méthodologie", "la méthode, indépendante de tout logiciel. "
         "Partie de référence."],
        ["2 — Application HEC-RAS", "mise en œuvre vérifiée, et les pièges "
         "relevés sur modèle réel."],
        ["3 — Application TELEMAC-2D", "déclinaison identifiée, non réalisée."],
        ["4 — Livrables", "ce que la chaîne produit. Indépendant du code de "
         "calcul."],
        ["Annexes A et B", "état de validation ; historique des essais et des "
         "choix écartés."],
    ]),

    # ---------------------------------------------------------------- MODE OP
    ("h1", "Mode opératoire"),
    ("h2", "Trois questions bloquantes, avant tout"),
    ("table", [
        ["Question", "Pourquoi elle est bloquante"],
        ["Le réseau comporte-t-il une boucle hydraulique ?",
         "La méthode exige un ordre total amont → aval (§ 1.2). Sur un réseau "
         "bouclé — bras se rejoignant, casiers interconnectés — elle n'est pas "
         "applicable en l'état. C'est une HYPOTHÈSE DU MODÈLE : elle est posée "
         "par l'hydraulicien, une fois, avant de commencer, et rien dans la "
         "chaîne ne la vérifie."],
        ["Combien de temps dure un calcul complet ?",
         "Coût total ≈ N × k calculs, k ≈ 2 à 4 essais par apport, plus un "
         "calcul de référence. À 2 h le calcul, sept apports font trois à cinq "
         "jours. C'est ce chiffre qui dimensionne le projet."],
        ["Un seul apport nouveau entre deux sections consécutives ?",
         "Une inconnue pour une contrainte (§ 1.2). Sinon : regrouper les "
         "apports, ou ajouter des sections."],
    ]),
    ("h2", "Les cinq étapes"),
    ("table", [
        ["Étape", "Contenu"],
        ["A — Tracer dans QGIS",
         "Trois couches en projection métrique commune : sections de contrôle, "
         "lignes d'injection, axe hydraulique (UNE polyligne, amont → aval). "
         "Aucun fichier de terrain n'est demandé (§ 1.7)."],
        ["B — Écrire, composer et contrôler",
         "Le plugin écrit les objets dans la géométrie, produit les shapefiles "
         "normalisés et un classeur pré-rempli — noms réels, ordre, une colonne "
         "de cible par section, pente de chaque apport déduite du profil. Il "
         "ne reste qu'à coller les hydrogrammes cibles. Ne rien lancer tant "
         "qu'une erreur subsiste."],
        ["C — Calibrer",
         "Boucle séquentielle amont → aval (§ 1.6). Plusieurs heures : le "
         "suivi est réécrit à chaque essai (§ 4.3), il n'y a pas à attendre "
         "devant l'écran."],
        ["D — Vérifier",
         "Passe finale sur toutes les sections, par relecture du dernier "
         "calcul. Aucune simulation supplémentaire."],
        ["E — Livrer", "Graphiques, tableaux et note de synthèse (partie 4)."],
    ]),
    ("p", "Les mêmes contrôles sont disponibles hors QGIS :"),
    ("code", "python controle_donnees.py donnees_calage.xlsx\n"
             "python pont_hecras.py controler-modele --template "
             "donnees_calage.xlsx"),
    ("h2", "Première mise en service"),
    ("p", "Sur un modèle jamais traité, chaque brique se valide séparément, "
          "dans un ordre tel que chaque test ne dépende que des précédents : "
          "un échec désigne alors une brique, non l'ensemble."),
    ("table", [
        ["Test", "Objet", "Critère de réussite"],
        ["T0", "Environnement", "verification_environnement.py puis "
         "test_plugin_qgis.py sous le Python de QGIS : aucun point bloquant, "
         "le pont répond avec sa version de ras-commander."],
        ["T0 bis", "Confrontation au modèle", "les noms déclarés existent dans "
         "la géométrie et les lignes sont bien implantées. Quelques secondes."],
        ["T1", "LIRE une section existante", "la série extraite a un nombre de "
         "pas, une pointe et un volume plausibles."],
        ["T2 / T3", "CRÉER une section, puis une injection, depuis QGIS",
         "l'objet apparaît dans la géométrie, HEC-RAS ouvre le modèle sans "
         "erreur, un nouveau calcul produit un résultat à cette section. "
         "Travailler sur une COPIE : ces tests écrivent dans la géométrie."],
        ["T4", "Test à blanc de la boucle", "prendre pour cibles les "
         "hydrogrammes d'un calcul quelconque, repartir d'apports faussés "
         "(× 0,6), vérifier que la boucle retrouve les apports d'origine. La "
         "bonne réponse étant connue, un échec désigne le code."],
    ]),

    # --------------------------------------------------------------- PARTIE 1
    ("h1", "Partie 1 — Méthodologie"),
    ("h2", "1.1  Objectif et principe"),
    ("p", "Le critère porte sur la forme complète de l'hydrogramme, et non sur "
          "le pic et le volume pris séparément. Un décalage dans le temps est "
          "accepté et neutralisé avant comparaison : seules la forme et "
          "l'amplitude une fois recalées comptent."),
    ("p", "Ajuster N apports sur N cibles à la fois est sur-contraint. Ils sont "
          "donc résolus un par un, d'amont en aval. Sur un réseau ramifié, on "
          "procède branche par branche ; une confluence se traite comme une "
          "section ordinaire."),
    ("figure", ("fig_sequentiel.png",
                "Résolution séquentielle. Une seule inconnue — l'apport N — "
                "pour une seule contrainte nouvelle — la cible N.")),
    ("h2", "1.2  Hypothèses de validité"),
    ("table", [
        ["Hypothèse", "Ce qu'elle implique"],
        ["Ordre total amont → aval", "les sections doivent s'ordonner sans "
         "ambiguïté le long d'un chemin d'écoulement. La plus contraignante : "
         "elle INTERDIT les réseaux bouclés, où « section suivante » n'a plus "
         "de sens. HYPOTHÈSE DU MODÈLE, jamais vérifiée par la chaîne : "
         "aucun contrôle ne détecte une boucle, et le calage se déroulerait "
         "sans rien dire sur un réseau qui en porte une. C'est à "
         "l'hydraulicien de répondre — confirmé pour les modèles en cours le "
         "8 septembre 2026."],
        ["Un seul apport nouveau par section", "sinon : regrouper les apports, "
         "ou ajouter des sections intermédiaires. Une section sans apport "
         "nouveau reste utile comme point de vérification."],
        ["Section de contrôle proche de son injection", "la correction est "
         "écrite là où l'écart se lit, sans modéliser le temps de transfert. "
         "D'autant mieux vérifiée que la section est proche — quelques "
         "dizaines à quelques centaines de mètres."],
        ["Sens d'écoulement stable", "une inversion de courant rend le débit "
         "intégré non interprétable, et fausse le volume."],
        ["Réponse croissante à l'apport", "augmenter un apport doit augmenter "
         "le débit restitué. Mise en défaut possible par un ouvrage à seuil ou "
         "une mise en charge."],
        ["L'apport pèse assez lourd à sa section", "en deçà, la tolérance "
         "admise à la section vaut plusieurs fois l'apport : la section se "
         "cale, l'apport n'est plus déterminé (§ 1.5)."],
    ]),
    ("p", "S'y ajoute une limite d'influence : si la condition limite aval "
          "pilote la ligne d'eau très en amont — modèle court, influence "
          "maritime, ouvrage régulé — les sections deviennent fortement "
          "couplées et le contrôle de cohérence amont doit être resserré."),
    ("p", "Une cible n'a pas à être un HSMF : rien dans l'algorithme n'en "
          "dépend. La méthode s'applique à tout hydrogramme cible — crue "
          "historique reconstituée, hydrogramme mesuré, scénario "
          "d'aménagement."),
    ("h2", "1.3  Cadre de référence : les HSMF"),
    ("p", "Les cibles sont généralement des hydrogrammes synthétiques "
          "monofréquence, construits conformément au guide national : Lang M., "
          "Lavabre J. (coord.), 2007, Estimation de la crue centennale pour "
          "les plans de prévention des risques d'inondations, Quæ, chap. 3, "
          "p. 76-81. Deux points de ce guide commandent la méthode."),
    ("bullet", "Des apports tous de même période de retour « conduisent en "
               "aval à une dérive en fréquence du fait de la concomitance des "
               "événements » (p. 79), dont le guide recommande de vérifier "
               "l'absence (p. 81). C'est l'objet de la méthode : le caractère "
               "monofréquence est garanti sur le RÉSULTAT, non sur les seules "
               "données d'entrée."),
    ("bullet", "Le guide propose (p. 79) de construire l'apport intermédiaire "
               "par soustraction analytique entre HSMF. Établie avant toute "
               "modélisation, cette soustraction ignore le routage 2D — "
               "laminage, stockage en champ d'expansion, effet des digues. La "
               "présente méthode cale au contraire les apports sur le "
               "résultat du calcul hydraulique."),
    ("note", "Réserve reprise du guide — l'hydrogramme d'apport obtenu n'est "
             "pas lui-même homogène en fréquence : c'est un opérateur "
             "intermédiaire, auquel il ne faut pas attribuer de période de "
             "retour propre."),
    ("h2", "1.4  Ce que l'on compare"),
    ("p", "Trois grandeurs, et trois seulement, rapportées en POURCENTAGE "
          "D'ATTEINTE — « volume 99,3 % » se juge sans décodeur."),
    ("table", [
        ["Grandeur", "Définition", "Tolérance"],
        ["Volume", "rapport des volumes, intégrés sur la fenêtre commune, "
         "après neutralisation du décalage", "± 5 %"],
        ["Débit de pointe", "rapport des maxima. Sa propre tolérance, parce "
         "qu'il dimensionne l'aléa", "± 2 %"],
        ["Forme", "corrélation APRÈS recalage temporel — la forme sans la "
         "dynamique", "≥ 97 %"],
    ]),
    ("p", "Les tolérances portent sur chaque grandeur SÉPARÉMENT, jamais sur "
          "un indicateur agrégé : un nombre unique peut rester flatteur alors "
          "qu'une composante dérive. Ce sont des BANDES — « ± 5 % » veut dire "
          "[95 ; 105], et il n'y a rien à gagner une fois dedans."),
    ("p", "LE VERDICT PORTE SUR LA FENÊTRE DE L'ÉVÉNEMENT, PAS SUR LA CRUE "
          "ENTIÈRE, et c'est délibéré — décision du 8 septembre 2026 : la "
          "fenêtre a été introduite pour cela, juger l'apport là où "
          "l'événement se joue, sans laisser une queue de décrue peser sur le "
          "volume. Le rapport de volume sur TOUTE la série est tout de même "
          "porté au Diagnostic, avec la part du volume que la fenêtre "
          "retient ; quand les deux lectures divergent, une réserve NON "
          "bloquante les nomme, au classeur, à la note de synthèse et au "
          "suivi. Elle DIT, elle ne juge pas — et aucun verdict déjà rendu "
          "ne bouge."),
    ("h3", "Le décalage temporel : mesuré, jamais jugé"),
    ("p", "Δt est l'écart entre L'HEURE DU PIC calculé et celle du pic cible — "
          "le geste même de l'opérateur. Aucune borne ne lui est appliquée, et "
          "aucun seuil ne le juge : il figure au journal, au suivi, au "
          "classeur et à la note, sans jamais bloquer."),
    ("p", "L'amplitude ne distingue pas un temps de transfert d'un appariement "
          "de pics sans rapport : les deux peuvent valoir cinq heures. Un "
          "décalage important sans défaut de volume ni de forme désigne un "
          "problème de propagation, que l'apport aggraverait s'il tentait de "
          "le corriger."),
    ("p", "CE QUI EST JUGÉ, EN REVANCHE, C'EST SA COHÉRENCE LE LONG DE "
          "L'AXE. Un Δt identique à toutes les sections ne dit rien de "
          "suspect : c'est une origine de temps qui diffère. Un Δt qui DÉRIVE "
          "d'une section à l'autre dit que le modèle et les cibles ne routent "
          "pas la crue au même rythme, et que le désaccord grandit."),
    ("p", "La grandeur retenue est l'ÉTENDUE de Δt — son maximum moins son "
          "minimum — rapportée à la durée médiane des fenêtres jugées. Ni son "
          "amplitude, qui ne distingue rien, ni la pente d'une régression, qui "
          "suppose une dérive régulière : sur un cas réel la dérive n'était "
          "pas monotone, et un critère de pente l'aurait laissée passer. Le "
          "seuil est relatif — 15 % — parce qu'une dérive de 4 h sur des crues "
          "de 25 h ne dit pas la même chose que sur des crues de 100 h."),
    ("table", [
        ["Deux modèles réels", "Ce qui a été mesuré"],
        ["Modèle A, 8 apports",
         "pic du modèle +0,26 h par section, pic des cibles +0,84 ; étendue de "
         "Δt 4,4 h. Le modèle route PLUS VITE que ses cibles ne le supposent."],
        ["Modèle B, 6 apports",
         "pic du modèle +2,30 h par section, pic des cibles +1,00 ; étendue de "
         "Δt 7,0 h. Le modèle route PLUS LENTEMENT — signe inverse."],
    ]),
    ("note", "Réserve à porter au client — la mesure ne coûte aucune "
             "simulation et sort dès l'état de référence, mais elle ne tranche "
             "pas : les sections seront calées, à 99–101 % de volume. Ce que "
             "l'étendue interroge est le POSITIONNEMENT TEMPOREL des "
             "hydrogrammes d'apport livrés, qui reproduisent la forme des "
             "cibles en portant ce décalage — et pas le même d'une section à "
             "l'autre. Sont-ce les cibles, le routage du modèle, ou une "
             "origine de temps ? La question appartient à l'ingénieur ; la "
             "chaîne se contente de la poser, sans bloquer. Le seuil de 15 % "
             "ne repose que sur DEUX cas."),
    ("figure", ("fig_fenetre.png",
                "La fenêtre de jugement, détectée dès l'état de référence.")),
    ("h3", "Comparer sur la bonne fenêtre"),
    ("p", "Les deux séries n'ont en général ni la même origine ni la même "
          "durée. Deux conséquences : le recalage s'opère sur une grille "
          "COMMUNE aux deux séries — rééchantillonner chacune depuis sa propre "
          "origine annulerait le décalage entre elles ; et les volumes se "
          "comparent sur la fenêtre où les DEUX séries existent — les intégrer "
          "chacun sur son étendue reviendrait à comparer 36 h à 48 h."),
    ("note", "Réserve non levée — volume, pointe et couverture sont bien "
             "restreints à la fenêtre de jugement, mais la corrélation et le "
             "recalage travaillent encore sur la grille qui englobe les deux "
             "séries."),
    ("p", "CE QUI MANQUE À LA FENÊTRE JUGÉE EST TOUJOURS DIT, et chiffré en "
          "heures. Au-delà de 10 % non simulés, la comparaison est déclarée "
          "invalide et le calage s'arrête sur « allonger la simulation ». En "
          "deçà, une réserve non bloquante accompagne le verdict : il garde "
          "son sens, la queue manquante pesant moins que la tolérance de "
          "volume, mais il porte sur un événement incomplet."),
    ("note", "Aucun autre indicateur ne pourrait le révéler : la cible et le "
             "calcul sont intégrés sur le MÊME intervalle rogné, donc leur "
             "rapport de volume reste à 100 % alors qu'une part de "
             "l'événement n'a jamais été simulée. C'est pourquoi la réserve "
             "est émise dès le premier dixième d'heure manquant."),
    ("h3", "Garde-fous"),
    ("bullet", "COUVERTURE — si la simulation ne couvre pas toute la durée de "
               "la cible, une alerte est levée. Le volume manquant serait "
               "sinon attribué à un défaut d'apport, que le calage "
               "compenserait en surdimensionnant l'injection."),
    ("bullet", "QUALITÉ NUMÉRIQUE — le bilan de masse rendu par le solveur est "
               "contrôlé AVANT toute comparaison à la cible. Un essai dont la "
               "conservation dérive est rejeté : corriger un apport pour "
               "compenser une erreur du solveur n'aurait aucun sens. Le seuil "
               "se règle (défaut 5 %) ; il ne dit rien de l'écart à la cible."),
    ("h2", "1.5  La correction"),
    ("p", "Un seul algorithme, et il tient en une ligne. À chaque essai, "
          "l'écart entre la cible et la mesure est réinjecté TEL QUEL dans "
          "l'apport — aucun gain, aucune relaxation, aucune recherche de pas. "
          "Δt est mesuré une seule fois, sur le calcul de référence, puis figé "
          "pour tous les essais de cet apport."),
    ("figure", ("fig_decalage.png",
                "Convention de décalage et formule de correction.")),
    ("p", "Hors de la plage où les DEUX séries sont connues, l'écart vaut "
          "ZÉRO, et non « la cible » : l'interpolation ne refuse pas une "
          "abscisse hors domaine, elle plafonne, et un déficit fabriqué là où "
          "rien n'a été mesuré serait indétectable dans les chiffres finaux."),
    ("figure", ("image3.png",
                "Définition d'un apport par correction additive. ① un calcul "
                "de référence, apports à zéro, mesure ce que la section reçoit "
                "déjà ; ② la première estimation est l'écart à la cible, non "
                "une forme supposée ; ③ l'écart qui subsiste est réinjecté ; "
                "④ volume, pointe et forme sont atteints simultanément.")),
    ("h3", "Le plancher à zéro, et le cliquet qui en découle"),
    ("p", "Le plancher à zéro est la SEULE contrainte de forme : un apport "
          "négatif serait un prélèvement. Tout le reste est libre — l'apport "
          "n'est pas un hydrogramme observé mais LA COMMANDE D'UN "
          "ASSERVISSEMENT, et seul compte le débit obtenu à la section."),
    ("figure", ("fig_cliquet.png",
                "Le cliquet : conséquence physique du plancher, non un défaut "
                "de convergence.")),
    ("h3", "Quand l'apport n'est pas identifiable"),
    ("p", "La méthode cale la SECTION ; l'apport n'en est que le moyen. Les "
          "deux ne se confondent que si l'apport pèse assez lourd dans le "
          "débit qui transite déjà. Sinon, une infinité d'hydrogrammes très "
          "différents satisfont la tolérance : la section est calée, l'apport "
          "ne l'est pas."),
    ("p", "L'ordre de grandeur se calcule AVANT tout calcul : écart possible "
          "sur l'apport ≈ tolérance de volume ÷ part de l'apport dans le débit "
          "de pointe à la section. À 2 % de part pour 5 % de tolérance, "
          "l'apport retenu peut s'écarter de 250 % du véritable sans que la "
          "section cesse d'être conforme."),
    ("p", "La chaîne annonce ce cas avant de calculer, en chiffrant la part et "
          "l'amplification, puis continue : caler la section reste légitime. "
          "Ce qui ne l'est pas, c'est de publier l'apport comme une estimation "
          "hydrologique. Y remédier demande une section où cet apport pèse "
          "davantage, ou une tolérance plus serrée — jamais un calcul de plus."),
    ("h3", "Ce qui arrête la recherche sur un apport"),
    ("table", [
        ["État", "Signification et suite à donner"],
        ["Concordance", "volume, pointe et forme simultanément sous leurs "
         "tolérances. Apport validé, on passe au suivant."],
        ["Cible hors d'atteinte", "AVANT tout calcul : la section reçoit déjà "
         "au moins autant que la cible. Un apport ne peut qu'ajouter du débit "
         "— revoir les apports amont, ou la cible. Le refus le moins cher de "
         "la chaîne."],
        ["Éloignement", "deux essais consécutifs s'écartent de la concordance : "
         "le modèle répond de façon trop non linéaire."],
        ["Correction sans effet", "l'apport ne bouge plus alors que la "
         "concordance n'est pas atteinte. Vérifier l'implantation de la ligne "
         "d'injection."],
        ["Qualité numérique", "bilan de masse hors du seuil : le calcul est "
         "rejeté et n'entre pas dans l'historique."],
        ["Essais épuisés", "garde-fou de dernier recours. Le motif indique si "
         "la pointe PROGRESSAIT ENCORE, et de combien d'essais on estime être "
         "loin — relever le plafond avant de mettre en cause la méthode."],
    ]),
    ("p", "Dans tous les cas, c'est le MEILLEUR essai qui est remis en place, "
          "jamais le dernier. Il est choisi sur (admissibilité, erreur "
          "combinée) : un essai qui tient les trois seuils passe devant tout "
          "essai qui n'en tient qu'un, et à admissibilité égale c'est la norme "
          "euclidienne des trois violations qui départage."),
    ("h3", "Ce que la méthode ne fait pas"),
    ("p", "Elle ne cherche pas à annuler le temps de propagation. La section "
          "calée reproduit la cible TRANSLATÉE de Δt : volume, pointe et forme "
          "concordent, la dynamique non. C'est un choix, d'autant plus anodin "
          "que la section est proche de son injection."),
    ("h2", "1.6  Procédure"),
    ("p", "Étape générique pour l'apport N, identique quel que soit N. "
          "Prérequis : les apports 1 à N−1 sont validés et figés."),
    ("table", [
        ["Étape", "Contenu"],
        ["0. État de référence", "un calcul avec TOUS les apports à caler mis "
         "à ZÉRO. Il mesure ce que chaque section reçoit indépendamment des "
         "apports cherchés. Les apports étant ensuite activés un par un, le "
         "dernier calcul de l'apport N est exactement l'état « sans apport "
         "N+1 » : le résiduel de chaque apport est MESURÉ, pour UN SEUL calcul "
         "sur tout le calage."],
        ["0 bis. Toutes les sections sont éprouvées", "c'est le seul état où "
         "elles sont toutes lisibles ensemble, et il a lieu de toute façon. "
         "Une section mal nommée ne se manifesterait sinon qu'au tour de SON "
         "apport."],
        ["1. Estimation initiale", "l'écart mesuré lui-même, écrêté à zéro. Il "
         "porte déjà l'information de volume, de pointe et d'allure."],
        ["2. Calcul complet", "simulation entière, avec l'apport N appliqué."],
        ["3. Contrôle numérique", "bilan de masse, AVANT toute comparaison."],
        ["4. Diagnostic", "recalage, rapports de volume et de pointe, forme, "
         "décalage, garde-fous — sur la fenêtre de jugement."],
        ["5. Acceptation", "les trois grandeurs simultanément sous leurs "
         "tolérances : apport validé et figé. Sinon, on ne passe pas au "
         "suivant."],
        ["6. Correction", "§ 1.5, puis retour à l'étape 2."],
        ["7. Cohérence amont", "vérifier que les sections 1 à N−1 restent sous "
         "le seuil : en régime fluvial, un apport peut influencer par remous "
         "les sections amont. RELECTURE de résultats déjà calculés — une "
         "dérive est signalée, jamais reprise automatiquement."],
        ["8. Apport suivant", "retour à l'étape 1 jusqu'à la dernière "
         "section."],
    ]),
    ("p", "Une fois tous les apports validés, le diagnostic est établi sur "
          "toutes les sections en RELISANT LE DERNIER CALCUL — aucune "
          "simulation supplémentaire, et ce n'est pas une approximation : on "
          "n'atteint cette passe que si tous les apports sont validés, et un "
          "essai concordant fait sortir la boucle immédiatement. Le dernier "
          "calcul porte donc nécessairement le jeu d'apports en place."),
    ("p", "Si une section dérive à ce stade, la reprise se fait par une "
          "nouvelle passe séquentielle amont → aval, jamais par une "
          "optimisation globale : celle-ci réintroduirait le problème "
          "sur-contraint que la résolution séquentielle a pour objet d'éviter."),
    ("figure", ("fig_etapes.png",
                "Un plan et un fichier de débit conservés par étape — c'est "
                "aussi le point de reprise.")),
    ("note", "Si le plan d'étape attendu est absent, le calage part du plan de "
             "référence avec un AVERTISSEMENT : les apports amont y valent ce "
             "qu'ils y valent, et ne seront pas vérifiés. Un fichier de "
             "reprise HEC-RAS, lui, n'aide pas : la notion est temporelle et "
             "non spatiale."),
    ("h3", "La durée simulée suit chaque apport"),
    ("p", "Les événements s'allongent vers l'aval : le premier apport a "
          "souvent fini de s'écouler quand le dernier n'a pas commencé. Une "
          "fenêtre de simulation unique impose donc à tous le besoin du "
          "dernier. La durée de chaque étape est ramenée à ce qui lui est "
          "nécessaire, ce qui ne change AUCUN résultat — seulement le temps de "
          "calcul."),
    ("p", "Ce n'est pas la durée de la crue cible qui commande, mais la "
          "FENÊTRE DE DÉFICIT relevée sur l'état de référence : l'intervalle "
          "où la cible dépasse ce que la section reçoit sans les apports. Elle "
          "est plus longue que la crue, et elle est datée dans le calendrier "
          "DU MODÈLE, non dans celui de la cible — le décalage y est déjà "
          "incorporé."),
    ("table", [
        ["Règle", "Raison"],
        ["Chaque étape couvre aussi l'événement de la SUIVANTE",
         "le calcul de l'apport N est l'état de référence de l'apport N+1 : "
         "c'est dans ses résultats que le déficit de N+1 se lit. Le tronquer à "
         "l'événement de N priverait N+1 de sa propre mesure."],
        ["La durée ne décroît jamais d'un apport au suivant",
         "l'étape de cohérence amont relit les sections déjà calées, et la "
         "vérification finale relit le DERNIER calcul pour TOUTES les "
         "sections. Une durée qui redescendrait les priverait de leur "
         "fenêtre."],
        ["On ne dépasse jamais la fenêtre du plan de référence",
         "elle est relevée une fois au départ. Ce qui se perd quand elle borne "
         "est la MARGE, pas la fenêtre jugée ; le journal le chiffre. Si la "
         "fenêtre jugée elle-même cessait d'être couverte, c'est le contrôle "
         "de couverture qui le dirait (§ 1.4)."],
        ["L'état de référence garde toujours la fenêtre entière",
         "il mesure le déficit de TOUTES les sections d'un seul coup, donc il "
         "doit couvrir l'événement le plus tardif."],
        ["Une durée qu'on ne sait pas mesurer laisse la fenêtre entière",
         "plus lent, jamais faux."],
    ]),
    ("p", "Mesure sur un modèle réel à douze apports, pour une fenêtre de "
          "référence de 36 h — les durées retenues, apport par apport : 14, "
          "16, 17,5, 18,5, 18,5, 21,5, 23,5, 24,5, 31, 33, 36 et 36 h. Soit "
          "290 h simulées au lieu de 432, environ un tiers de temps de calcul "
          "en moins. CE CHIFFRE DÉPEND ENTIÈREMENT DU JEU DE CIBLES et ne se "
          "transpose pas : sur un modèle dont les événements sont tous "
          "synchrones, le gain est nul."),
    ("note", "L'apport injecté, lui, reste calculé sur TOUTE la série, comme "
             "la fenêtre de jugement : c'est le JUGEMENT et la PRÉSENTATION "
             "qui sont restreints, jamais la donnée écrite dans le modèle."),
    ("h2", "1.7  Implantation géométrique : PK et profil en long"),
    ("p", "Le point kilométrique vient d'une projection curviligne sur l'axe "
          "hydraulique, JAMAIS d'une saisie. L'appariement apport → section est "
          "lui aussi géométrique — chaque section prend la première injection "
          "en amont d'elle — et le sens de l'axe se déduit des altitudes. "
          "Faire porter ce lien par les NOMS créerait une seconde source de "
          "vérité, qui finirait par diverger."),
    ("table", [
        ["Contrôle", "Ce qui est détecté"],
        ["Cohérence de l'ordre", "les PK doivent croître avec la colonne "
         "Ordre. Une inversion est signalée en désignant les deux stations."],
        ["Sens de l'axe", "des PK décroissants signifient un axe dessiné de "
         "l'aval vers l'amont. Diagnostiqué comme tel, et non rapporté comme "
         "N−1 inversions."],
        ["Position des apports", "un apport en aval de la section qu'il "
         "alimente ne peut pas l'influencer : le calage ne convergerait "
         "jamais."],
        ["Empiètement", "un apport en amont de la section précédente modifiera "
         "un tronçon déjà validé. Admissible, mais appelle une vigilance à "
         "l'étape 7."],
    ]),
    ("p", "Le fond du lit est la cote INTÉGRÉE AU MAILLAGE, non le terrain "
          "d'entrée : elle décrit ce qui a réellement été calculé, et la ligne "
          "d'eau vient du même maillage — fond et ligne d'eau sont donc "
          "cohérents par construction. Conséquence pratique : aucun fichier de "
          "terrain n'est à fournir. Trois contrôles de vraisemblance "
          "accompagnent le profil — axe sortant du domaine, ligne d'eau sous "
          "le fond, fond remontant vers l'aval."),
    ("p", "La PENTE DE LIGNE D'ÉNERGIE de chaque apport, dont le code se sert "
          "pour répartir le débit entre les mailles, se renseigne PAR APPORT. "
          "Elle est pré-remplie depuis le profil : pente moyenne du fond sur "
          "±200 m autour de l'injection, MAJORÉE DE 20 % — une pente "
          "sous-estimée concentre l'injection au lieu de l'étaler. Une valeur "
          "saisie à la main n'est jamais écrasée."),
    ("h2", "1.8  Données d'entrée et contrôles"),
    ("p", "CE DOCUMENT L'APPELLE « le classeur », et le plugin "
          "« l'Excel des hydrogrammes objectifs » : c'est le même fichier. Le "
          "premier nom dit sa forme — un classeur à quatre feuilles —, le "
          "second ce qu'on y vient faire. L'écran a retenu le second, parce "
          "qu'un utilisateur n'ouvre pas un format, il saisit des "
          "hydrogrammes."),
    ("p", "Le classeur formalise les données en quatre feuilles : "
          "Instructions ; Paramètres (identification du modèle, fenêtre de "
          "simulation, précision attendue, plafond d'essais, blocs géométrie "
          "et profil) ; Correspondance (une ligne par station dans l'ordre "
          "amont → aval) ; Cibles (une colonne Temps_h puis une colonne par "
          "station). La forme de chaque apport n'est pas saisie : elle est lue "
          "dans le fichier de débit du modèle."),
    ("p", "Un calage représente plusieurs heures de calcul : une incohérence "
          "doit être détectée en quelques secondes, avant le premier calcul."),
    ("table", [
        ["Famille", "Vérifications"],
        ["Paramètres", "présence des paramètres requis, plafond d'essais "
         "suffisant, format de la fenêtre de simulation."],
        ["Correspondance", "colonne Ordre = suite 1..N sans trou ni doublon ; "
         "aucun nom répété, faute de quoi « une inconnue pour une contrainte » "
         "est rompue."],
        ["Cohérence croisée", "chaque cible déclarée existe comme colonne dans "
         "la feuille Cibles."],
        ["Hydrogrammes", "temps strictement croissant, pas de débit négatif, "
         "hydrogramme non identiquement nul, nombre de pas suffisant."],
        ["Durées couvertes", "chaque série du modèle couvre-t-elle la fenêtre "
         "de simulation ? Sinon HEC-RAS refuse de calculer. Le contrôle "
         "distingue les apports à caler — qui se rallongent dans le classeur, "
         "au besoin par des zéros — des autres conditions limites, qui se "
         "corrigent dans le modèle."],
        ["Chaîne géographique", "projection métrique commune, unicité et "
         "non-vacuité des noms, longueur non nulle, croisement de l'axe, puis "
         "les quatre contrôles du § 1.7."],
        ["Confrontation au modèle", "chaque nom déclaré existe réellement dans "
         "la géométrie — zone 2D comprise — et les lignes sont correctement "
         "implantées. Source d'erreur la plus fréquente."],
    ]),
    ("p", "Les anomalies sont classées en erreurs, qui bloquent le lancement, "
          "et avertissements. Une colonne de cible encore vide relève de "
          "l'avertissement : c'est l'état normal d'un classeur en cours de "
          "remplissage."),
    ("h2", "1.9  Organigramme général"),
    ("figure", ("fig_organigramme.png", None)),

    # --------------------------------------------------------------- PARTIE 2
    ("h1", "Partie 2 — Application HEC-RAS"),
    ("p", "Mise en œuvre vérifiée. HEC-RAS est piloté en Python, sans passer "
          "par l'interface graphique, au moyen de la bibliothèque "
          "ras-commander. Elle nécessite HEC-RAS installé localement — ici "
          "7.0.1 — dont elle pilote le moteur sans le remplacer."),
    ("h2", "2.1  Environnement"),
    ("code", "pip install ras-commander\n"
             "init_ras_project(<dossier_du_projet>, <version_hecras>)"),
    ("note", "CITATION EXIGÉE — ras-commander est un projet libre de CLB "
             "Engineering Corporation, dont les auteurs demandent que les "
             "travaux publiés la citent : « ras-commander v0.99.1, CLB "
             "Engineering Corporation — github.com/gpt-cmdr/ras-commander »."),
    ("bullet", "SÉPARATEUR DÉCIMAL — le moteur exige le point, et pas seulement "
               "dans le format régional de l'interface : c'est le paramètre de "
               "langue pour les programmes non Unicode qui est déterminant. "
               "Une virgule provoque des échecs de calcul silencieux."),
    ("bullet", "NE PAS LAISSER HEC-RAS OUVERT pendant un calage. L'interface "
               "réécrit les fichiers du projet depuis sa propre mémoire et "
               "défait ce que la chaîne y écrit. La chaîne relève donc une "
               "EMPREINTE de la géométrie au début du calage et la revérifie à "
               "chaque étape : un objet disparu arrête le calage, au lieu de "
               "le laisser produire un résultat faux (annexe B)."),
    ("h2", "2.2  Correspondance prérequis → fonctions"),
    ("table", [
        ["Prérequis de la méthode", "Fonctions ras-commander"],
        ["Injecter un hydrogramme", "RasUnsteady.extract_boundary_and_tables, "
         "identify_tables, parse_fixed_width_table, write_table_to_file — "
         "format largeur fixe des fichiers .uXX."],
        ["Extraire le débit à une section",
         "HdfResultsPlan.get_reference_timeseries, complétée par une LECTURE "
         "DIRECTE du fichier de résultats (§ 2.5)."],
        ["Piloter le calcul", "RasCmdr.compute_plan."],
        ["Contrôler la qualité numérique",
         "HdfResultsPlan.get_volume_accounting."],
        ["Ne pas altérer le projet", "RasPlan.clone_plan et clone_unsteady. "
         "Indispensable sur un projet client."],
    ]),
    ("h2", "2.3  Implantation géométrique et base de temps"),
    ("p", "Les sections et les injections sont écrites dans le fichier "
          "géométrie EN TEXTE CLAIR (.gXX) : elles survivent ainsi au "
          "prétraitement, ce qui ne serait pas le cas d'objets injectés dans "
          "le seul fichier HDF. Une sauvegarde horodatée précède chaque "
          "écriture."),
    ("bullet", "UNE LIGNE D'INJECTION CRÉÉE N'INJECTE RIEN tant que le fichier "
               "de débit ne porte pas son bloc de condition limite. La chaîne "
               "l'écrit : localisation au format à largeur fixe — le nom doit "
               "y tenir exactement —, intervalle, table de débits et pente."),
    ("bullet", "LE BON FICHIER DE DÉBIT N'EST PAS TOUJOURS CELUI QU'ON CROIT. "
               "Deux plans peuvent partager la géométrie sans partager le "
               "fichier de débit. Le contrôle confronte donc chaque apport au "
               "fichier que le PLAN DE RÉFÉRENCE désigne."),
    ("bullet", "FENÊTRE DE SIMULATION — substituer un fichier de débit couvrant "
               "une autre période ne déplace pas la fenêtre du plan : HEC-RAS "
               "calcule alors hors des hydrogrammes, sans rien signaler. Elle "
               "est donc saisissable, pré-remplie depuis le plan choisi. "
               "C'est aussi la ligne « Simulation Date= » que le calage "
               "réécrit à chaque étape pour ajuster la durée à l'apport en "
               "cours (§ 1.6), sans jamais dépasser celle du plan de "
               "référence."),
    ("bullet", "BLOCS ORPHELINS — un fichier de débit qui a de l'historique "
               "garde des conditions limites sans ligne correspondante en "
               "géométrie. HEC-RAS les ignore ; la chaîne aussi, en croisant "
               "avec les noms lus dans la géométrie. Sans ce filtre, une série "
               "que le solveur n'ouvrira jamais peut faire refuser un calage."),
    ("p", "Le pas de travail est le plus fin des pas natifs des cibles, avec "
          "un plancher à 6 minutes : une cible plus grossière est densifiée, "
          "une cible plus fine est préservée. TOUTES les conditions limites à "
          "hydrogramme du fichier cloné sont ramenées à ce pas, PAR "
          "INTERPOLATION ET À DURÉE CONSERVÉE. N valeurs au pas p couvrent "
          "(N−1)×p heures, jamais N×p."),
    ("p", "Le calage ouvre une ÉTAPE par apport et titre du même nom son plan "
          "et son fichier de débit. Ces plans sont CONSERVÉS. Ce qui est "
          "retiré à la fin d'un calage réussi se limite aux traces de "
          "préparation ; la seule suppression de plan autorisée est le "
          "remplacement d'un HOMONYME. Rien n'est supprimé si le calage "
          "échoue. Contrepartie assumée : trente apports laissent trente et un "
          "jeux de résultats — un coût de disque, pas un oubli."),
    ("h2", "2.4  Interface QGIS : le plugin de préparation"),
    ("p", "Ce plugin est propre à HEC-RAS et n'appartient pas à la "
          "méthodologie générale. Il ne fait rien que la ligne de commande ne "
          "sache faire : il rend plus sûre la part géographique du travail. "
          "MONTRER UNE ERREUR LÀ OÙ ELLE EST — un rapport affirme que l'apport "
          "A3 est en aval de la section S2, la carte le fait voir ; éviter la "
          "recopie de noms ; relire les résultats en couches symbolisables. "
          "Aucune règle de contrôle ne lui est propre."),
    ("h3", "Pourquoi deux interpréteurs"),
    ("p", "Le Python de QGIS porte tout ce qu'il faut pour la préparation des "
          "données. Mais il porte aussi sa propre bibliothèque HDF5 : dès que "
          "le cœur de QGIS est chargé, h5py ne peut plus s'initialiser, et "
          "ras-commander devient inimportable. TOUTE opération touchant au "
          "modèle s'exécute donc dans un AUTRE interpréteur, appelé en "
          "sous-processus par un pont qui répond en JSON."),
    ("note", "Second piège, lié au premier — le sous-processus hérite du "
             "PYTHONPATH, du PYTHONHOME et du PATH de QGIS. Les variables "
             "PYTHON* doivent être retirées et le PATH RECONSTRUIT à partir de "
             "rien : une liste noire ne protège que des chemins déjà connus."),
    ("h3", "Une seule fenêtre, cinq onglets et une aide"),
    ("p", "L'ORDRE DES ONGLETS EST CELUI DES DÉCISIONS, et il a changé en "
          "septembre 2026 : l'axe hydraulique a rejoint l'onglet 1, où il se "
          "trace comme les sections et les injections, au lieu de voisiner "
          "avec des objectifs chiffrés auxquels il n'a rien à voir. Il y a "
          "pris le nom de PROFIL EN LONG et la place qui lui revient, "
          "immédiatement sous le plan : le plan dit quelle géométrie on lit, "
          "le profil en long comment on la parcourt."),
    ("p", "L'ACTION EST AU BOUT DE L'ONGLET QUI LA PRÉPARE. « Écrire, "
          "composer et contrôler » était permanent en bas de la fenêtre, "
          "visible depuis les six onglets — y compris ceux où il n'a rien à "
          "faire. Il ferme désormais l'onglet 1, dans un encadré MISE À JOUR "
          "DU MODÈLE, au bout de tout ce qu'il consomme. L'encadré « Écriture "
          "dans la géométrie », qui ne portait aucune commande, est descendu "
          "dans l'aide : un cadre sans geste, au milieu d'un onglet qui n'est "
          "fait que de gestes, se lisait comme une étape à franchir."),
    ("table", [
        ["Onglet", "Contenu"],
        ["1. Modèle", "le FICHIER .prj du projet — et non le dossier qui le "
         "contient : rien ne distingue à l'œil un dossier de modèle d'un "
         "autre —, le plan de référence, la géométrie et le fichier de débit, "
         "le PROFIL EN LONG (l'axe, son sens, le PK d'origine), la zone 2D et "
         "la fenêtre de simulation ; chargement des couches, qui deviennent "
         "éditables dans QGIS ; puis MISE À JOUR DU MODÈLE, qui écrit, "
         "compose et contrôle."],
        ["2. Objectifs et précision", "ce qu'on vise et avec quoi : l'ÉCART "
         "ADMIS sur le volume et sur le débit de pointe — le résultat, lui, "
         "se lit en pourcentage d'atteinte de la cible —, le bilan de masse "
         "admis, le plafond d'essais, et l'« Excel des hydrogrammes "
         "objectifs » où ils se saisissent."],
        ["3. Résultats", "dossier de sortie et ses deux sous-dossiers, "
         "relecture d'un hydrogramme déjà calculé, résumé de la "
         "configuration, et le MÉNAGE DU MODÈLE — l'élagage des plans "
         "d'étape d'un calage livré, sur demande et après confirmation."],
        ["4. Lancer", "appariement géométrique, et surtout COMBIEN "
         "D'HYDROGRAMMES CIBLES RESTENT À SAISIR ; le premier apport à caler, "
         "le PRÉFIXE DE SCÉNARIO — sans lui, caler le Q10 après le Q100 sur "
         "le même modèle efface les plans du Q100 — et le lancement du calage "
         "en arrière-plan."],
        ["5. Suivi", "où en est le calage, rafraîchi toutes les deux "
         "secondes : en cours, terminé (avec le motif), ou INTERROMPU quand le "
         "processus n'existe plus sans qu'aucun verdict ait été rendu. Le "
         "bilan de masse du dernier calcul y figure. La courbe porte la cible "
         "et la section de l'apport en cours, et DERRIÈRE, EN POINTILLÉ, LES "
         "SECTIONS DÉJÀ CALÉES : un calage séquentiel se lit de l'amont vers "
         "l'aval, et c'est la famille de courbes qui dit si tout se tient."],
        ["Aide et configuration", "le mode opératoire — précédé d'un "
         "sommaire, car il est long —, les pièges connus, et le diagnostic de "
         "l'environnement : c'est là qu'on désigne la chaîne, ou qu'on "
         "INSTALLE l'interpréteur HEC-RAS sans avoir à savoir où Python se "
         "trouve sur le poste."],
    ]),
    ("p", "CE QUE LE CALAGE LAISSE DANS LE MODÈLE : un plan HEC-RAS par "
          "étape, et son Unsteady Flow — « <préfixe>_sans_apport », puis "
          "« <préfixe>_Apport_<nom> », et à l'arrivée "
          "« <préfixe>_avec_apports ». Ce dernier n'est pas un clone : c'est "
          "le plan de la dernière étape, RETITRÉ, qui porte donc tous les "
          "apports calés ET ses résultats de calcul. Les étapes sont "
          "CONSERVÉES — elles documentent le calage apport par apport et "
          "permettent de reprendre une séquence interrompue — au prix du "
          "disque : un modèle à trente apports garde trente et un jeux de "
          "résultats. L'onglet 3 les élague SUR DEMANDE, jamais d'office, et "
          "refuse de le faire si le calage n'a pas conclu : ses étapes sont "
          "alors tout ce qu'il en reste."),
    ("p", "La fenêtre est NON MODALE : le travail consiste précisément à "
          "dessiner des sections et des injections dans QGIS pendant qu'elle "
          "est ouverte. « Écrire, composer et contrôler » écrit d'abord les couches "
          "dans la géométrie — le remplacement des objets de même nom est "
          "SYSTÉMATIQUE, ce que QGIS montre fait foi — puis compose le paquet. "
          "Le fichier de débit n'est jamais touché : un apport raccordé garde "
          "son hydrogramme, et un calage en cours survit à une recomposition."),
    ("p", "Recomposer n'efface jamais un travail de saisie : hydrogrammes "
          "cibles et pentes déjà saisis sont PRÉSERVÉS pour les couples qui "
          "persistent, retrouvés par leur NOM et non par leur position."),
    ("p", "Toutes les lignes d'injection ne sont pas des apports à caler : on "
          "y trouve aussi les débits d'entrée permanents et les conditions "
          "limites aval. Une injection sans section en aval n'est pas calée — "
          "cas normal. Une section sans injection en amont ne peut pas l'être "
          "du tout : erreur bloquante, tout comme une injection que plusieurs "
          "sections revendiqueraient."),
    ("h3", "Installation et chemins"),
    ("p", "Depuis l'archive : Extensions → Installer depuis un ZIP. Par lien "
          "symbolique pendant la mise au point, le plugin suit alors les "
          "modifications du dossier projet sans réinstallation :"),
    ("code", 'mklink /D "%APPDATA%\\QGIS\\QGIS3\\profiles\\<profil>\\python\\'
             'plugins\\calage_apports" "<dossier du projet>\\calage_apports"'),
    ("p", "Le dossier de la chaîne est CHERCHÉ, jamais supposé, dans un ORDRE "
          "FIXE qui ne compare aucune date : désignation explicite, variable "
          "d'environnement, copie embarquée, parent du plugin."),
    ("code", "set CALAGE_CHAINE=<dossier du projet>\n"
             "set CALAGE_PYTHON=%USERPROFILE%\\venv-hecras\\Scripts\\python.exe"),
    ("h2", "2.5  Pièges rencontrés et vérifiés"),
    ("p", "Chacun a été relevé sur un modèle réel et figé par un test."),
    ("table", [
        ["Piège", "Description"],
        ["Le fichier texte fait foi", "le .gXX.hdf est un produit de "
         "prétraitement, périmé tant que le modèle n'a pas été recalculé."],
        ["Un bloc se délimite par ce qu'il CONTIENT", "jamais par ce qui le "
         "suit. Chercher la PROCHAINE ligne d'en-tête emporte tout jusqu'à la "
         "fin du fichier sur le DERNIER bloc — 629 lignes et sept régions de "
         "Manning supprimées sans que les compteurs d'objets bougent."],
        ["Colonnes mal nommées", "« Storage Area Name » contient le nom de la "
         "zone 2D et « Blank 1 » celui de la BC line. Ne pas se fier aux "
         "intitulés."],
        ["Même nom dans plusieurs zones 2D", "retenir la première occurrence "
         "revient à parier sur l'ordre du fichier : si une zone orpheline "
         "vient en tête, l'écriture se fait dans un bloc que HEC-RAS ignore, "
         "le débit ne bouge jamais, et la boucle tourne des heures. Le "
         "filtrage par zone est obligatoire."],
        ["Une condition de sortie prise pour un apport", "elle porte une pente "
         "imposée, pas un hydrogramme. Chercher « le premier tableau qui "
         "suit » sans borner au bloc courant lui attribue celui du bloc "
         "SUIVANT."],
        ["« Flow Hydrograph= N » compte les VALEURS", "et non les lignes, que "
         "le fichier aligne par dix. Une en-tête désaccordée fait lire une "
         "série tronquée ou débordante, SANS message."],
        ["Une série plus courte que la simulation", "HEC-RAS refuse de "
         "calculer et l'écrit dans <plan>.data_errors.txt, mais ras-commander "
         "rapporte le calcul RÉUSSI. Contrôlé avant calcul (§ 1.8)."],
        ["Nom de colonne du bilan de masse", "elle s'appelle « Error "
         "Percent », sans le signe %. Un filtre exigeant ce signe ne "
         "correspond à aucune colonne réelle."],
        ["Un calcul interrompu rapporté « réussi »", "le fichier de résultats "
         "existe mais ne contient aucune série. La présence des séries est "
         "vérifiée, et l'horodatage relevé avant puis après."],
        ["Deux dispositions dans un même fichier", "les conditions limites "
         "sont stockées à raison d'un jeu par objet ; les sections de contrôle "
         "EN MATRICES. Un lecteur écrit pour la première annonce que la "
         "section est absente alors qu'elle est là."],
        ["Le signe du débit dépend du sens de tracé", "une section dessinée à "
         "contresens renvoie un débit ENTIÈREMENT NÉGATIF : indicateurs dénués "
         "de sens, divergence sans message. La série est ramenée à une "
         "convention positive vers l'aval, et l'inversion rapportée."],
        ["Croiser résultats et géométrie lus séparément", "dès que la "
         "géométrie a été reprétraitée, les deux ne portent plus le même "
         "nombre de mailles. Chaque fichier de plan embarque SA copie."],
        ["Entrées de remplissage dans les tableaux de mailles", "elles se "
         "reconnaissent à leur cote non renseignée et doivent être écartées "
         "avant tout minimum, maximum ou plus proche voisin."],
        ["Taille de maille médiane trompeuse", "sur un maillage raffiné, la "
         "médiane globale décrit le lit et non la plaine — 3,4 m contre 15 m "
         "au droit des conditions limites. Toute tolérance géométrique doit "
         "être évaluée localement."],
        ["Ligne d'injection à distance du périmètre", "un écart de l'ordre de "
         "la maille est normal ; un test d'intersection stricte les "
         "rejetterait toutes."],
        ["Shapefile sans .prj", "il se lit sans erreur et ses coordonnées sont "
         "interprétées telles quelles : les objets se retrouvent "
         "silencieusement décalés. Erreur bloquante."],
    ]),

    # --------------------------------------------------------------- PARTIE 3
    ("h1", "Partie 3 — Application TELEMAC-2D"),
    ("note", "Statut — déclinaison identifiée mais NON RÉALISÉE. La "
             "correspondance ci-dessous est établie d'après les mécanismes "
             "standards du code, à valider lors d'une mise en œuvre effective."),
    ("p", "TELEMAC-2D satisfait les prérequis et présente trois avantages pour "
          "l'automatisation : fichier cas en texte clair, sorties aux sections "
          "directement exploitables, et pilotage sans bibliothèque tierce."),
    ("table", [
        ["Prérequis", "Mécanisme TELEMAC-2D"],
        ["Injecter un hydrogramme", "frontière liquide à débit imposé en "
         "limite de maillage ; source ponctuelle ou distribuée pour une "
         "injection interne. En 2D, préférer une répartition sur quelques "
         "nœuds."],
        ["Extraire le débit à une section", "sections natives, déclarées par "
         "SECTIONS INPUT FILE, écrites dans SECTIONS OUTPUT FILE."],
        ["Piloter le calcul", "fichier cas en texte clair et lancement en "
         "ligne de commande, ou API TelApy."],
        ["Contrôler la qualité numérique", "bilan de volume activable par "
         "mot-clé, écrit dans le listing."],
        ["Mécanisme de reprise", "COMPUTATION CONTINUED = YES avec PREVIOUS "
         "COMPUTATION FILE."],
    ]),
    ("p", "L'orthographe des mots-clés a évolué selon les versions. Les "
          "couches d'analyse et de livrables ne manipulant que des séries "
          "temporelles, elles s'appliquent sans modification : seuls "
          "l'extraction des séries et le lancement des calculs sont à "
          "réécrire."),

    # --------------------------------------------------------------- PARTIE 4
    ("h1", "Partie 4 — Livrables"),
    ("p", "Indépendants du code de calcul. Principe directeur : être "
          "directement insérables dans un rapport d'étude — légendes et unités "
          "en français, tableaux exportés dans un format exploitable."),
    ("h2", "4.1  Graphiques"),
    ("table", [
        ["Figure", "Ce qu'elle apporte"],
        ["Profil en long (synthèse)", "sur un même axe de PK : géométrie du "
         "lit et ligne d'eau maximale, implantation réelle des sections et des "
         "injections, débits de pointe et écart en pourcentage."],
        ["Comparaison à la cible (une par section)", "deux panneaux : "
         "hydrogrammes bruts, où le décalage reste visible, puis recalés. Ne "
         "montrer que la version recalée masquerait une information "
         "hydraulique réelle."],
        ["Atteinte de la cible", "pointe, volume et forme par section, en "
         "pourcentage. L'écart se lit sur la grandeur qui dérive, non sur un "
         "indicateur agrégé."],
        ["Profil longitudinal des pointes", "version allégée, centrée sur la "
         "restitution des débits."],
        ["Convergence du calage", "volume et pointe atteints, essai par essai. "
         "Premier support de diagnostic : oscillation et stagnation s'y lisent "
         "directement."],
        ["Hydrogrammes d'apport retenus", "le résultat livrable de l'étude, "
         "réutilisable dans les modélisations ultérieures."],
    ]),
    ("p", "RÔLE RÉGLEMENTAIRE DES FIGURES LONGITUDINALES — ce sont elles qui "
          "répondent à la vérification exigée par le guide (p. 81) sur « l'effet "
          "éventuel de concomitance de crue entre affluents et cours d'eau "
          "principal, qui pourrait induire une dérive en fréquence vers "
          "l'aval ». Une dérive progressive y est immédiatement lisible, ce "
          "qu'aucun indicateur section par section ne montre."),
    ("figure", ("image2.png",
                "Profil en long de synthèse. Cas à quatre sections, la "
                "dernière volontairement non conforme : l'écart de −4,9 % sur "
                "le pic apparaît juste en aval de la fosse. Le fond du lit est "
                "la cote de maille retenue par le code, la ligne d'eau celle "
                "du calcul final.")),
    ("h2", "4.2  Tableaux"),
    ("table", [
        ["Tableau", "Contenu et rôle"],
        ["Tableau de bord", "une ligne par section : volume, pointe et forme "
         "en pourcentage d'atteinte, décalage, nombre d'essais, bilan de "
         "masse, statut, alertes. LIVRABLE CENTRAL de vérification, à joindre "
         "au rapport."],
        ["Apports retenus", "débit de pointe et volume injectés. Le résultat "
         "exploitable de l'étude."],
        ["Implantation", "PK de chaque section et de chaque apport, distances. "
         "Tous calculés, jamais saisis."],
        ["Journal des essais", "enregistrement exhaustif des itérations. "
         "N'a pas vocation à figurer dans le corps du rapport, mais assure la "
         "traçabilité exigée dans un cadre réglementaire."],
    ]),
    ("p", "Les quatre tableaux sont exportés dans un classeur unique, un "
          "onglet par tableau."),
    ("h2", "4.3  Suivi en temps réel"),
    ("p", "Attendre la fin d'un calage pour savoir où il en est, c'est "
          "découvrir trop tard qu'il dérive. Les sorties sont réécrites après "
          "chaque apport validé, et rafraîchies à chaque essai."),
    ("table", [
        ["Sortie", "Contenu"],
        ["avancement.md", "note relisible pendant le calage : apports validés "
         "sur le total, pourcentage achevé, temps écoulé, RESTE ESTIMÉ et "
         "heure de fin prévisible, puis le détail apport par apport."],
        ["avancement.png", "l'état de chaque apport, volume et pointe atteints "
         "face aux 100 % visés."],
        ["avancement.json", "état machine complet, réécrit à chaque essai et "
         "de façon atomique, PID compris. C'est lui que le plugin relit."],
        ["iterations.xlsx", "un onglet par apport : récapitulatif des essais, "
         "puis les séries. L'onglet s'ouvre sur un bloc RÉSIDUEL (apports à "
         "zéro) : la lecture se fait EN ESCALIER, l'écart d'un bloc donnant "
         "l'apport du bloc suivant. Les écarts sont tracés sur AXE SECONDAIRE, "
         "sans quoi quelques m³/s seraient écrasés par des débits de plusieurs "
         "centaines. C'est la trace de la RECHERCHE, là où le reste ne "
         "rapporte que son résultat."],
    ]),
    ("bullet", "LE SUIVI NE DOIT JAMAIS INTERROMPRE LE CALAGE. Toute "
               "défaillance de production est capturée et consignée, jamais "
               "propagée : il serait absurde de perdre six heures de calcul "
               "parce qu'une figure n'a pas pu s'écrire."),
    ("bullet", "LES ÉCRITURES SONT ATOMIQUES. Les fichiers sont relus pendant "
               "que le calage tourne : écrits sous un nom temporaire puis "
               "renommés, un lecteur ne tombe jamais sur un fichier à moitié "
               "écrit."),
    ("bullet", "LE TEMPS RESTANT EST ESTIMÉ à partir des apports déjà achevés. "
               "L'estimation vaut ce que vaut l'hypothèse d'apports de coût "
               "comparable, mais c'est le seul chiffre qui permette de décider "
               "s'il faut attendre ou revenir plus tard."),
    ("h2", "4.4  Note de synthèse et non-convergence"),
    ("p", "Une note est rédigée automatiquement : conclusion de conformité "
          "assortie des écarts d'ensemble, diagnostic section par section, et "
          "rappel des vérifications exigées par le guide."),
    ("p", "Lorsqu'un apport n'atteint pas le seuil, la chaîne ne s'arrête pas "
          "silencieusement : elle explicite la cause identifiée, avec la "
          "figure de convergence et le journal des essais. Le tableau de bord "
          "et la note restent produits, les sections concernées étant marquées "
          "non validées — le livrable reste exploitable pour comprendre "
          "l'échec."),

    # --------------------------------------------------------------- ANNEXE A
    ("h1", "Annexe A — État de validation"),
    ("p", "Chaque module porte son propre auto-test, lancé en l'exécutant "
          "directement. Ils tournent sans HEC-RAS et sans QGIS, à l'exception "
          "de la suite du plugin. Chaque correction laisse derrière elle le "
          "contrôle qui la garde ; plusieurs ont été validés en réintroduisant "
          "volontairement le défaut d'origine — un contrôle qui n'a jamais "
          "échoué ne prouve rien."),
    ("table", [
        ["Module", "Ce qui est vérifié"],
        ["criteres.py", "identité → concordance parfaite ; translation pure → "
         "le recalage la neutralise et le décalage est néanmoins RAPPORTÉ ; "
         "apport sous-dimensionné → rapport de volume juste et "
         "non-convergence ; retards de 0,8 à 3,0 h sur une fenêtre qui coupe "
         "la décrue à 36 % du pic, retrouvés exactement."],
        ["calage.py", "la boucle est éprouvée contre un modèle fictif dont le "
         "laminage est délibérément NON LINÉAIRE, les cibles étant obtenues en "
         "le faisant tourner avec des apports connus : la bonne réponse est "
         "donc connue exactement. S'y ajoutent les cas d'arrêt et la fenêtre "
         "de jugement."],
        ["pilote_hecras.py", "vérifié sur une copie d'un projet réel, dans les "
         "deux modes de sélection. Le plan, la géométrie et le fichier de "
         "débit de RÉFÉRENCE restent inchangés — contrôlé par empreinte. Le "
         "re-cadençage conserve la durée ; une condition plus courte que la "
         "simulation est détectée avec ses deux durées ; un bloc orphelin est "
         "ignoré, mais une géométrie illisible ne fait rien ignorer."],
        ["geometrie.py", "PK par projection curviligne, ordre incohérent "
         "désigné nommément, axe inversé diagnostiqué comme tel, apport mal "
         "positionné détecté. La suppression d'un objet ne touche à aucun bloc "
         "voisin — vérifié sur une vraie géométrie, blocs comptés avant et "
         "après."],
        ["controle_donnees.py", "sur un classeur volontairement fautif, huit "
         "erreurs détectées : paramètre manquant, seuil hors intervalle, Ordre "
         "non contigu, nom en doublon, temps non croissant, cible absente, "
         "débit négatif."],
        ["suivi.py et livrables.py", "un calage complet est simulé, dont un "
         "apport qui échoue délibérément. Contrôles sur les VALEURS et non sur "
         "la seule absence d'erreur. Et surtout QU'UNE DÉFAILLANCE D'ÉCRITURE "
         "N'INTERROMPT PAS LE CALAGE, vérifié en dirigeant les sorties vers un "
         "disque inexistant."],
        ["le plugin, sans interface", "la fenêtre est exercée de bout en bout, "
         "les boîtes de dialogue étant remplacées par des réponses "
         "programmées — mais le code exécuté est bien celui du plugin."],
    ]),
    ("h2", "A.1  Ce qui reste à faire"),
    ("bullet", "Borner la corrélation et le recalage temporel à la fenêtre de "
               "jugement, comme le sont déjà le volume, la pointe et la "
               "couverture."),
    ("bullet", "Reprendre le seuil de cohérence du décalage (15 % de la "
               "fenêtre jugée) sur un TROISIÈME modèle : il ne repose que sur "
               "deux cas, et le premier critère retenu avait déjà été renversé "
               "par le deuxième modèle — celui-là même qui devait le "
               "confirmer."),
    ("bullet", "Trancher, avec le client, les dérives de décalage mesurées sur "
               "les deux modèles : 4 h sur l'un, 7 h sur l'autre, en sens "
               "contraire. Ce n'est plus une anomalie isolée mais un écart "
               "systématique entre le routage des modèles et celui que les "
               "cibles supposent."),
    ("bullet", "Recréer le script de pré-vol, en y portant deux mesures qui ne "
               "coûtent aucune simulation : le cliquet par section, et la part "
               "de chaque apport dans le débit de sa section."),
    ("bullet", "Fonder le seuil de bilan de masse sur les sources (USACE, "
               "guides SOP) plutôt que sur les seules mesures disponibles."),
    ("bullet", "Décliner la chaîne sur TELEMAC-2D (partie 3)."),

    # --------------------------------------------------------------- ANNEXE B
    ("h1", "Annexe B — Historique : essais, mesures et choix écartés"),
    ("note", "Cette annexe regroupe TOUT ce qui relève du chemin parcouru : "
             "mesures sur cas réels, approches essayées puis retirées, "
             "incidents. Le corps de la note n'énonce que la règle en vigueur ; "
             "c'est ici qu'on trouve pourquoi elle est ce qu'elle est."),
    ("h2", "B.1  Calage complet sur modèle réel"),
    ("p", "Sept apports en cascade, sept sections, huit calculs HEC-RAS, "
          "26 h 22 min. CHAQUE APPORT A ATTEINT SA CIBLE AU PREMIER ESSAI, "
          "sans incident. Environ 3 h 10 par apport : c'est le coût de "
          "référence en configuration de production."),
    ("table", [
        ["Apport", "Volume", "Pointe", "Forme", "Décalage", "Part du débit"],
        ["1", "101,1 %", "99,9 %", "99,9 %", "−3,80 h", "62 %"],
        ["2", "100,2 %", "100,1 %", "100,0 %", "−4,30 h", "24 %"],
        ["3", "100,5 %", "99,9 %", "100,0 %", "−4,20 h", "6 %"],
        ["4", "100,0 %", "100,0 %", "100,0 %", "−4,80 h", "28 %"],
        ["5", "102,0 %", "100,5 %", "99,8 %", "−3,60 h", "2 %"],
        ["6", "100,0 %", "100,1 %", "100,0 %", "−5,00 h", "27 %"],
        ["7", "100,2 %", "99,1 %", "99,9 %", "−5,30 h", "33 %"],
    ]),
    ("p", "CE QUE CE RÉSULTAT ÉTABLIT — la méthode tient sur un enchaînement "
          "long : les trois tolérances sont tenues sur sept sections "
          "d'affilée, chacune au premier essai."),
    ("p", "CE QU'IL N'ÉTABLIT PAS — que l'APPORT retenu soit juste. Face à un "
          "calcul manuel indépendant, six apports sur sept tombent à moins de "
          "10 % en pointe ; le septième s'en écarte de 200 %, et c'est "
          "précisément celui qui ne pèse que 2 % du débit de sa section "
          "(§ 1.5). Caler la section et déterminer l'apport sont deux "
          "questions distinctes."),
    ("note", "Le verdict final de ce calage a été prononcé NON CONFORME, à "
             "tort : le processus tournait avec une version où le dépassement "
             "d'un seuil de décalage, depuis supprimé, empêchait de conclure. "
             "Les chiffres ci-dessus sont ceux du calcul et n'ont pas bougé ; "
             "seul le passage du chiffre au verdict était fautif. C'est ce "
             "défaut qui a conduit à retirer le seuil."),
    ("h2", "B.2  Approches essayées, puis retirées"),
    ("table", [
        ["Approche", "Ce qui l'a fait retirer"],
        ["Décalage par moindres carrés, plutôt que pic contre pic",
         "à l'état de référence, le résiduel n'a pas la forme de la cible — il "
         "lui manque ce que l'apport doit fournir. L'ajustement global se cale "
         "alors sur la décrue ou le débit de base. La corrélation croisée "
         "sous-estime le retard dès que l'événement ne revient pas à sa ligne "
         "de base : 0,00 h annoncé pour 1,6 h réels."],
        ["Borner le décalage à une fraction de la durée de la série",
         "fabriquait une valeur qui n'est ni la mesure ni un temps de "
         "transfert plausible, et sur laquelle toute la correction était "
         "pourtant bâtie. Mesuré : −2,49 h au lieu de −3,3 h, et le premier "
         "essai partait à 3 469 738 % du volume cible."],
        ["Un seuil d'alerte sur le décalage",
         "il s'est déclenché sur sept sections sur sept d'un calage réel, pour "
         "un décalage structurel — les deux calendriers n'ayant pas la même "
         "origine. Une alerte qui se déclenche partout n'apprend qu'à être "
         "ignorée."],
        ["Correction à deux termes (volume + pointe), région de confiance, "
         "recherche de pas exhaustive, déphasage de la réponse",
         "triplait la taille du code pour un usage que la méthode manuelle ne "
         "couvre pas. Contrepartie assumée : sur un tronçon qui lamine "
         "fortement, la version actuelle convergera plus lentement, voire pas "
         "du tout."],
        ["Lisser l'écart avant de le réinjecter",
         "étalait la correction de part et d'autre de chaque instant : elle "
         "ratait la pointe qu'elle devait combler et déversait du volume hors "
         "du manque."],
        ["Re-étiqueter « Interval= » sans toucher aux valeurs",
         "supposait le tableau déjà juste et l'étiquette seule périmée — vrai "
         "sur un modèle, faux sur un autre, et rien dans le fichier ne les "
         "distingue. Sur un projet nativement au quart d'heure, ramener ainsi "
         "la condition amont à 6 minutes a divisé par 2,5 la durée couverte."],
        ["Choisir la chaîne de calage sur sa DATE",
         "l'extraction d'une archive ne restitue pas les dates qu'elle "
         "stocke : les fichiers extraits portent l'heure de l'installation, et "
         "la copie embarquée masquait donc en silence les sources vives d'un "
         "poste de développement."],
        ["Reprendre automatiquement les sections amont en dérive",
         "la vérification est une relecture pure du dernier calcul : la "
         "rejouer sans calcul intermédiaire rend le même verdict. La boucle ne "
         "pouvait rien reprendre, par construction. La chaîne SIGNALE "
         "désormais, et laisse décider."],
    ]),
    ("h2", "B.3  Incidents relevés en production"),
    ("bullet", "L'INTERFACE HEC-RAS A ÉCRIT PAR-DESSUS LA GÉOMÉTRIE, en plein "
               "calage. Le veilleur de dialogues de la bibliothèque de "
               "pilotage — actif par défaut, pour qu'un calcul sans "
               "surveillance ne se fige pas sur une boîte modale — répond OUI "
               "à toutes, y compris « Voulez-vous enregistrer les "
               "modifications ? ». Les dégâts se sont limités à des positions "
               "d'étiquettes ; avec un état antérieur à la création des "
               "sections de contrôle, celles-ci disparaissaient au milieu de "
               "vingt-six heures de calcul. Le désactiver exposerait au mal "
               "qu'il soigne : d'où l'empreinte de géométrie (§ 2.1)."),
    ("bullet", "UN FICHIER DE DÉBIT PORTANT 45 BLOCS POUR 14 LIGNES EN "
               "GÉOMÉTRIE. Séquelle d'un historique d'édition — plusieurs "
               "découpages de zones, plusieurs passes de calage. Deux blocs "
               "orphelins, restés courts, ont fait refuser trois lancements "
               "sur des séries que le solveur n'aurait jamais ouvertes. D'où "
               "le filtrage par les noms lus en géométrie (§ 2.3)."),
    ("bullet", "UN BILAN DE MASSE À 1,1 PUIS 1,4 % sur un modèle par ailleurs "
               "sain, contre un seuil alors fixé à 1 %. Resserrer le pas de "
               "calcul de 2 s à 1 s a DÉGRADÉ le bilan, non amélioré : la "
               "cause est ailleurs (maillage, conditions limites, tolérances "
               "2D). Le seuil a été porté à 5 % et exposé au classeur ; sa "
               "valeur reste à fonder sur les sources."),
]
