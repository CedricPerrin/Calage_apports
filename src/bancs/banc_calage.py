# -*- coding: utf-8 -*-
"""
Banc d'auto-tests de calage.py : la boucle de calage sur ModeleFictif.

Sorti du module le 10/11/2026 : c'etait son bloc « if __name__ ==
"__main__" », pres de 1 500 lignes qui partaient dans l'archive du plugin.
Le code est celui du bloc, a l'identique, desindente d'un cran. Il se lance
seul (python3 src/bancs/banc_calage.py) ou par le module
(python3 src/calage.py), qui l'execute ; « --figer-reference » se passe a
l'un comme a l'autre et reecrit le meme src/reference_calage_fictif.json.

ModeleFictif RESTE dans calage.py : test_caracterisation_caler.py et
verification_environnement.py l'y cherchent. Les sous-classes d'essai
definies ici partent avec le banc.

LA DOUBLURE PASSE PAR LE MODULE. Dans le module, _recaler() remplacait
_verifier_globalement par « global » : caler() voyait la nouvelle fonction.
Ici, un nom importe est une copie locale ; le remplacement s'ecrit donc
calage._verifier_globalement = ..., sans quoi le controle appellerait la
vraie verification sans rien dire.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # src/

import numpy as np                                          # noqa: E402

import calage                                               # noqa: E402
from calage import (  # noqa: E402
    Configuration, ETAPE_AVEC_APPORTS, ETAPE_SANS_APPORT,
    LONGUEUR_MAX_TITRE_PLAN, ModeleFictif, ResultatCalage, ResultatCalcul,
    _coherence_decalage, _coherence_points, _progression_pic,
    _sections_derivees, _verifier_globalement, _volume, admissible, caler,
    cliquet_volume, concordance, corriger_apport, decalage_minimisant_ecart,
    ecart_a_la_cible, ecart_combine, etape_apport, fenetre_injection,
    masque_fenetre, produire_livrables_finaux, qualite_acceptable, rang_essai,
    titre_etape)

# SORTIE EN UTF-8, MEME LANCE A LA MAIN. Les auto-tests de ce module
# impriment des caracteres hors ASCII (« → », « Δ », les guillemets
# francais). Dans une console ou une redirection Windows, la sortie prend
# l'encodage local — cp1252 sur un poste francais — et le premier de ces
# caracteres leve UnicodeEncodeError : l'auto-test s'interrompt sur ce qui
# ressemble a un defaut du module, alors que rien n'est casse. Le pont
# impose PYTHONIOENCODING=utf-8 a la chaine lancee par le plugin ; ceci
# couvre l'appel direct, que la documentation recommande pourtant.
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import tempfile
from pathlib import Path

from suivi import Suivi, nom_onglet

def _onglets(chemin):
    """Noms des onglets d'un classeur, ou [] s'il n'est pas lisible."""
    import openpyxl
    try:
        return openpyxl.load_workbook(chemin, read_only=True).sheetnames
    except Exception:                                   # noqa: BLE001
        return []

print("=" * 74)
print("AUTO-TEST DE LA BOUCLE DE CALAGE — modele fictif, reponse connue")
print("=" * 74)

def hydrogramme(t, pic, t_pic=6.0, forme=2.5):
    t = np.maximum(np.asarray(t, dtype=float), 1e-3)
    return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))

temps = np.linspace(0.01, 36, 400)
# Nommes comme les conditions limites d'un vrai modele — « A1 » et non
# « Apport_1 » : les etapes du calage s'appellent « Apport_<nom> », et un
# nom deja prefixe rendrait « Apport_Apport_1 » illisible dans le controle.
apports = ["A1", "A2", "A3", "A4"]
sections = ["S1_Amont", "S2_Pont", "S3_Confluence", "S4_Aval"]
formes = [hydrogramme(temps, 10.0) for _ in apports]

# Laminage faible (2 %) : le domaine de validite de la correction directe
# (§ methodologie V1.3, hypothese « troncon transparent »). Ce test n'a
# plus a demontrer la precision face a un fort laminage — c'etait le role
# du mode par defaut, retire lors de la simplification du 07/08/2026.
modele = ModeleFictif(apports, sections, temps, formes)

# Cibles obtenues EN FAISANT TOURNER le modele avec des facteurs connus :
# la bonne reponse est donc connue exactement, et un echec de la boucle
# designe le code, jamais les donnees.
facteurs_vrais = [4.5, 3.4, 3.6, 3.5]
for a, f in zip(apports, facteurs_vrais):
    modele.appliquer_facteur(a, f)
cibles = [modele.lire_section(s) for s in sections]
for i, (s, (_, q)) in enumerate(zip(sections, cibles)):
    print(f"   cible {s:16s} pic {float(np.max(q)):7.2f} m3/s "
          f"(facteur vrai {facteurs_vrais[i]})")

sortie = Path(tempfile.gettempdir()) / "calage_boucle_test"
suivi = Suivi(sortie, apports, sections, titre="Test a blanc")

modele.preparer()
resultat = caler(modele, apports, sections, cibles,
                 Configuration(nb_max_essais=8),
                 suivi=suivi)

print("\n--- BILAN ---")
print(f"   {resultat.nb_calculs} calculs, "
      f"{sum(a.essais for a in resultat.apports)} essais retenus")
# La correction etant ADDITIVE, il n'y a plus de facteur scalaire a
# comparer : c'est l'HYDROGRAMME INJECTE qui doit retrouver celui ayant
# servi a fabriquer la cible. Controle plus exigeant qu'un scalaire — il
# porte sur le volume, la pointe ET la forme, c'est-a-dire exactement ce
# que la methode promet.
vrais_hydrogrammes = {a: formes[k] * facteurs_vrais[k]
                      for k, a in enumerate(apports)}
ecarts_volume, ecarts_pic = [], []
for a in resultat.apports:
    obtenu = modele.formes[a.nom_apport] * modele.facteurs[a.nom_apport]
    attendu = vrais_hydrogrammes[a.nom_apport]
    e_v = abs(_volume(temps, obtenu) / _volume(temps, attendu) - 1)
    e_p = abs(float(np.max(obtenu)) / float(np.max(attendu)) - 1)
    ecarts_volume.append(e_v)
    ecarts_pic.append(e_p)
    print(f"   {a.nom_apport:10s} volume {100 * e_v:+5.1f} %  "
          f"pointe {100 * e_p:+5.1f} %  "
          f"volume {100 * a.diagnostic.rapport_volume:5.1f} %  "
          f"pointe {100 * a.diagnostic.rapport_pic:5.1f} %  "
          f"{a.essais} essai(s)")
print(f"   conforme : {resultat.conforme}")

# --- controles ---------------------------------------------------------
print("\n--- CONTROLES ---")
echecs = []

def controler(libelle, condition, detail=""):
    print(f"   [{'OK' if condition else 'ECHEC'}] {libelle}"
          + (f"  ->  {detail}" if detail else ""))
    if not condition:
        echecs.append(libelle)

controler("tous les apports valides",
          all(a.valide for a in resultat.apports),
          f"{sum(a.valide for a in resultat.apports)}/{len(apports)}")
controler("calage conforme a la verification finale", resultat.conforme)
controler("hydrogrammes retrouves en VOLUME a mieux que 5 %",
          max(ecarts_volume) < 0.05,
          f"ecart max {100 * max(ecarts_volume):.2f} %")
controler("hydrogrammes retrouves en POINTE a mieux que 5 %",
          max(ecarts_pic) < 0.05,
          f"ecart max {100 * max(ecarts_pic):.2f} %")
# LA CONCORDANCE PORTE SUR LE VOLUME, LA POINTE ET LA FORME — RIEN D'AUTRE.
_c = Configuration()
_faux = type("D", (), {"rapport_volume": 1.0, "rapport_pic": 1.0,
                       "r": 0.99})()
controler("volume, pointe et forme conformes : la concordance est acquise",
          concordance(_faux, _c), "volume/pointe/forme conformes")
_faux_pic = type("D", (), {"rapport_volume": 1.0, "rapport_pic": 1.5,
                           "r": 0.99})()
controler("une pointe fausse arrete la concordance",
          not concordance(_faux_pic, _c), f"pic {_faux_pic.rapport_pic}")

controler("concordance simultanee volume / pointe / forme a chaque section",
          all(d.converge for d in resultat.diagnostics_finaux),
          "  ".join(f"{d.rapport_volume:.3f}/{d.rapport_pic:.3f}/{d.r:.3f}"
                    for d in resultat.diagnostics_finaux))
controler("convergence econome (<= 6 essais par apport)",
          max(a.essais for a in resultat.apports) <= 6,
          f"max {max(a.essais for a in resultat.apports)}")
controler("suivi produit", (sortie / "avancement.md").exists()
          and (sortie / "avancement.png").exists())
controler("un onglet d'iterations par apport",
          (sortie / "iterations.xlsx").exists()
          and _onglets(sortie / "iterations.xlsx")
          == [nom_onglet(a) for a in apports],
          f"{_onglets(sortie / 'iterations.xlsx')}")

# ETAPES JALONNEES : une pour l'etat de reference, une par apport, dans
# l'ordre. C'est ce qui donne leurs noms aux plans conserves sous HEC-RAS.
# LA DERNIERE A CHANGE DE NOM, et c'est la correction du 03/09 : le plan du
# dernier apport porte tous les apports cales et leurs resultats ; il
# s'appelle desormais « avec_apports » et non « Apport_<dernier> ».
controler("etapes jalonnees dans l'ordre",
          modele.etapes[:-1] == [ETAPE_SANS_APPORT]
          + [etape_apport(a) for a in apports[:-1]],
          " | ".join(modele.etapes))
controler("l'etat final est titre « avec_apports », pas du nom du dernier "
          "apport",
          modele.etapes[-1] == ETAPE_AVEC_APPORTS, modele.etapes[-1])

# RECALAGE D'UN PLAN VALIDE QUI GARDE SON NOM (10/11/2026). Poser le titre
# final efface le plan valide : on ne le fait que sur un calage CONFORME.
# Le verdict est force a « non conforme » pour le second passage.
_vraie_verification = _verifier_globalement

def _recaler(conforme):
    m = ModeleFictif(apports, sections, temps, formes)
    if not conforme:
        def _verifier_globalement(*a, **k):
            _vraie_verification(*a, **k)
            a[4].conforme = False
        calage._verifier_globalement = _verifier_globalement
    try:
        caler(m, apports, sections, cibles,
              Configuration(nb_max_essais=8, remplacer_plan_source=True),
              journal=lambda *a, **k: None)
    finally:
        calage._verifier_globalement = _vraie_verification
    return m.etapes[-1]

controler("plan source a remplacer : calage conforme, le titre final est "
          "pose", _recaler(True) == ETAPE_AVEC_APPORTS)
controler("plan source a remplacer : calage NON conforme, le plan garde "
          "son titre d'etape", _recaler(False) == etape_apport(apports[-1]),
          _recaler(False))

# --- PREFIXE DE SCENARIO -----------------------------------------------
print("\n--- PREFIXE DE SCENARIO ---")

# RETROCOMPATIBILITE, LE CONTROLE QUI PROTEGE LES CALAGES DEJA FAITS :
# prefixe vide = les titres d'avant, au caractere pres.
controler("prefixe vide : les titres d'etape sont inchanges",
          titre_etape(ETAPE_SANS_APPORT) == "sans_apport"
          and titre_etape(ETAPE_SANS_APPORT, "") == "sans_apport"
          and etape_apport("A1") == "Apport_A1"
          and etape_apport("A1", "") == "Apport_A1",
          f"{titre_etape(ETAPE_SANS_APPORT)!r} / {etape_apport('A1')!r}")
controler("prefixe renseigne : etape au nom court, plan final au prefixe seul",
          titre_etape(ETAPE_SANS_APPORT, "Q100") == "Q100-sans"
          and etape_apport("APP06", "Q100") == "Q100-APP06"
          and titre_etape("sans APP06 et aval", "Q100") == "Q100-sans APP06"
          and titre_etape(ETAPE_AVEC_APPORTS, "Q100") == "Q100",
          etape_apport("APP06", "Q100"))
# « Q100 », « Q100- » et « Q100_ » DOIVENT rendre le meme titre :
# _remplacer_homonymes et plan_par_titre comparent le Plan Title caractere
# pour caractere, et deux ecritures du meme prefixe fabriqueraient les
# plans en double que ce prefixe existe pour supprimer.
controler("le separateur n'est jamais double",
          etape_apport("A1", "Q100_") == etape_apport("A1", " Q100 ")
          == etape_apport("A1", "Q100-") == "Q100-A1"
          and titre_etape(ETAPE_AVEC_APPORTS, "Q100 - ") == "Q100")
# UN SEUL SEPARATEUR, MEME SI LE PREFIXE PORTE DES TIRETS ESPACES.
controler("« Riviere - Q100 » donne « Riviere - Q100-A1 »",
          etape_apport("A1", "Riviere - Q100") == "Riviere - Q100-A1"
          and titre_etape(ETAPE_AVEC_APPORTS, "Riviere - Q100 - ")
          == "Riviere - Q100",
          etape_apport("A1", "Riviere - Q100"))
controler("le modele propose rend « Riviere-Q100-A1 » et « Riviere-Q100 »",
          etape_apport("A1", "Riviere-Q100") == "Riviere-Q100-A1"
          and titre_etape(ETAPE_AVEC_APPORTS, "Riviere-Q100")
          == "Riviere-Q100")
# AU-DELA, ON REFUSE — jamais on ne tronque : deux titres rognes au meme
# « Short Identifier » partagent le dossier de resultats que RAS Mapper
# nomme d'apres ce champ. C'est le doublon que le prefixe supprime, et il
# serait absurde qu'il le refabrique.
# UN CARACTERE DE TROP, CALCULE DEPUIS LA BORNE : le banc suit la
# constante. Fige en dur, il rouillait a chaque mesure du champ
# « Short Identifier » — c'est ce qui est arrive le 20 septembre 2026.
_prefixe_trop = "P" * (LONGUEUR_MAX_TITRE_PLAN - 5)
try:
    etape_apport("APP06", _prefixe_trop)   # len + 1 + 5 = borne + 1
    _refus = ""
except ValueError as _e:
    _refus = str(_e)
controler(f"un titre de {LONGUEUR_MAX_TITRE_PLAN + 1} caracteres est "
          f"REFUSE, pas tronque",
          bool(_refus), _refus or "aucune erreur levee")
controler("le refus dit de combien raccourcir",
          "1 caractere(s)" in _refus, _refus)
# LE TITRE DE REPRISE EST LE PLUS LONG : c'est lui qui fixe la marge du
# prefixe, et c'est lui qui a bute le 20 septembre 2026 sur la borne a 30.
controler("un prefixe de 21 laisse tenir un titre de reprise (32)",
          len(titre_etape("sans APP07 et aval", "P" * 21)) == 32)

# LE CALAGE ENTIER SOUS PREFIXE. On rejoue caler() plutot que d'eprouver la
# seule fonction : c'est caler() qui doit poser le prefixe PARTOUT, etat de
# reference et plan final compris.
modele_p = ModeleFictif(apports, sections, temps, formes)
r_p = caler(modele_p, apports, sections, cibles,
            Configuration(nb_max_essais=8, prefixe_etape="Q100"),
            journal=lambda *a, **k: None)
controler("caler() prefixe TOUTES les etapes, plan final compris",
          modele_p.etapes == ["Q100-sans"]
          + [f"Q100-{a}" for a in apports[:-1]]
          + ["Q100"],
          " | ".join(modele_p.etapes))
controler("le prefixe ne change rien au resultat du calage",
          r_p.conforme, r_p.motif)

# --- rapport final ------------------------------------------------------
print("\n--- ASSEMBLAGE DU RAPPORT FINAL ---")
dossier_rapport = sortie / "rapport_final"
rapport = produire_livrables_finaux(resultat, modele, dossier_rapport)
controler("rapport conforme", rapport["conforme"])
# 4 comparaisons + 1 atteinte + 1 apports_retenus + xlsx + synthese = 8.
# PAS de figure de convergence attendue ICI : sur un troncon transparent
# (le defaut du modele fictif depuis la simplification du 07/08/2026),
# chaque apport converge en un seul essai, et figure_convergence exige
# au moins deux essais pour avoir quelque chose a tracer.
controler("fichiers produits", len(rapport["fichiers"]) >= 8,
          f"{len(rapport['fichiers'])} fichier(s)")
controler("4 figures de comparaison",
          len(list(dossier_rapport.glob("comparaison_*.png"))) == 4)
import pandas as pd
journal = pd.read_excel(dossier_rapport / "tableaux_calage.xlsx",
                        sheet_name="Journal")
controler("le diagnostic par essai n'est plus NaN dans le journal",
          journal["pic"].notna().all() and journal["volume"].notna().all(),
          f"{journal['pic'].notna().sum()}/{len(journal)} valeurs")
tb_final = pd.read_excel(dossier_rapport / "tableaux_calage.xlsx",
                         sheet_name="Tableau_de_bord")
controler("tableau de bord final a 4 sections", len(tb_final) == 4)
controler("le tableau de bord est fidele aux diagnostics",
          all(abs(tb_final.loc[i, "Volume (% cible)"]
                  - round(100 * d.rapport_volume, 1)) < 1e-9
              and abs(tb_final.loc[i, "Débit de pointe (% cible)"]
                      - round(100 * d.rapport_pic, 1)) < 1e-9
              for i, d in enumerate(resultat.diagnostics_finaux)))
controler("aucune colonne KGE dans le livrable",
          not any(c in tb_final.columns
                  for c in ("KGE", "r", "alpha", "beta")),
          " | ".join(tb_final.columns))

# --- LA FIGURE FINALE COUVRE LA CRUE, PAS LA FENETRE JUGEE ------------
#
# Les series finales etaient coupees a la fenetre de jugement AVANT d'etre
# tracees. La figure du rapport montrait donc moins que celle du suivi,
# avec la meme legende — et cachait la decrue, la ou un modele s'ecarte
# volontiers de sa cible. figure_comparaison cadre deja seule.
print("\n--- LES SERIES DU RAPPORT NE SONT PLUS COUPEES ---")
_avec_fen = [(a, s) for a, s in zip(resultat.apports, resultat.series_finales)
             if a.fenetre_principale is not None]
controler("une fenetre de jugement est bien posee sur ce cas",
          bool(_avec_fen),
          f"{len(_avec_fen)}/{len(resultat.apports)} apport(s)")
if _avec_fen:
    # Celui dont la fenetre coupe le plus : c'est lui qui revelait le
    # defaut, et c'est sur lui que le banc doit porter.
    _a, _s = min(_avec_fen, key=lambda x: x[0].fenetre_principale[1])
    _t_modele, _ = modele.lire_section(_a.nom_section)
    _fin_serie = float(np.max(_s[2]))
    _fin_fen = float(_a.fenetre_principale[1])
    _fin_modele = float(np.max(_t_modele))
    controler("la fenetre jugee est bien plus courte que la simulation",
              _fin_fen < _fin_modele - 1e-9,
              f"fenetre {_fin_fen:.2f} h, modele {_fin_modele:.2f} h")
    controler("et la serie du rapport va jusqu'au bout du calcul",
              abs(_fin_serie - _fin_modele) < 1e-9,
              f"serie {_fin_serie:.2f} h pour un modele a {_fin_modele:.2f} h")

# --- DES APPORTS A BASES DE TEMPS DIFFERENTES -------------------------
#
# LE CAS QUI A FAIT PERDRE SES LIVRABLES A UN CALAGE DE 46 HEURES. Dans un
# fichier unsteady, chaque apport est un bloc avec son propre
# « Interval= » et son propre nombre de points. Le modele fictif, lui, rend
# le meme axe pour tous : ce banc lui met une doublure qui rend un axe PAR
# APPORT, de longueurs differentes, comme le fait un modele reel.
# Mesure en production : 256, 321, 811 et 1 001 points chez douze apports.
print("\n--- LIVRABLES : DES APPORTS A BASES DE TEMPS DIFFERENTES ---")

class _ModeleBasesHeterogenes:
    """Le modele cale, mais dont chaque apport a sa propre base de temps."""

    def __init__(self, reel, noms):
        self._reel = reel
        self._axes = {}
        for k, nom in enumerate(noms):
            t_a, q_a = reel.forme_apport(nom)
            # Longueurs volontairement toutes differentes, et la PREMIERE
            # n'est ni la plus courte ni la plus longue : un masque pris
            # sur elle est alors trop court pour les uns, trop long pour
            # les autres.
            n = len(t_a) - 7 * ((k + 3) % 5)
            self._axes[nom] = (np.asarray(t_a)[:n], np.asarray(q_a)[:n])

    def forme_apport(self, nom_apport):
        return self._axes[nom_apport]

    def __getattr__(self, nom):
        return getattr(self._reel, nom)

# ETANCHEITE : le dossier est efface AVANT, sinon les fichiers d'un run
# precedent feraient verdir ce controle sur du code casse. C'est le piege
# que STATUT.txt nomme — un controle qui s'ignore lui-meme ne controle
# rien — et il s'applique aussi aux dossiers temporaires reutilises.
import shutil
_dossier_het = sortie / "rapport_bases_heterogenes"
shutil.rmtree(_dossier_het, ignore_errors=True)
_modele_het = _ModeleBasesHeterogenes(modele, apports)
_tailles = sorted({len(_modele_het.forme_apport(a)[0]) for a in apports})
controler("la doublure rend bien des axes de longueurs differentes",
          len(_tailles) == len(apports), str(_tailles))
try:
    _rap_het = produire_livrables_finaux(resultat, _modele_het, _dossier_het)
    _leve = None
except Exception as e:                                   # noqa: BLE001
    _rap_het, _leve = None, f"{type(e).__name__}: {e}"
controler("le rapport ne leve plus sur des bases heterogenes",
          _leve is None, _leve or "aucune exception")
controler("le classeur, la note et la figure sont tous produits",
          (_dossier_het / "tableaux_calage.xlsx").is_file()
          and (_dossier_het / "synthese.md").is_file()
          and (_dossier_het / "apports_retenus.png").is_file(),
          ", ".join(sorted(f.name for f in _dossier_het.glob("*")))[:110])

# L'APPORT EXPORTE EST-IL CELUI QUI EST DANS LE MODELE ?
ap_final = pd.read_excel(dossier_rapport / "tableaux_calage.xlsx",
                         sheet_name="Apports")
pics_modele = [float(np.max(modele.forme_apport(a.nom_apport)[1]))
               for a in resultat.apports]
controler("le pic injecte exporte est celui du modele",
          all(abs(ap_final.loc[i, "Pic injecte (m3/s)"] - p) < 0.02
              for i, p in enumerate(pics_modele)),
          "  ".join(f"{ap_final.loc[i, 'Pic injecte (m3/s)']:.1f}"
                    f"/{p:.1f}" for i, p in enumerate(pics_modele)))

# --- LA SERIE RETENUE, ET PAS SEULEMENT SON PIC -----------------------
#
# Le classeur ne portait que des INDICATEURS AGREGES : une ligne par
# apport, pic et volume. L'hydrogramme lui-meme ne vivait que dans une
# figure et dans le fichier unsteady du modele — ni verifiable ligne a
# ligne, ni reutilisable hors HEC-RAS. La feuille en donne la serie, dans
# la meme forme que la feuille « Cibles » du classeur de saisie.
print("\n--- LE CLASSEUR PORTE LES HYDROGRAMMES RETENUS ---")
_hy = pd.read_excel(dossier_rapport / "tableaux_calage.xlsx",
                    sheet_name="Hydrogrammes_apports")
controler("une colonne de temps et une colonne par apport",
          list(_hy.columns) == ["Temps_h"]
          + [f"Apport_{a}" for a in apports],
          " | ".join(map(str, _hy.columns)))
controler("le temps est strictement croissant",
          bool((_hy["Temps_h"].diff().dropna() > 0).all()),
          f"{len(_hy)} pas de {_hy['Temps_h'].iloc[0]:.2f} a "
          f"{_hy['Temps_h'].iloc[-1]:.2f} h")
# LA MEME VALEUR QUE LE MODELE, pas une valeur plausible : c'est tout
# l'interet d'exporter la serie plutot que de la redessiner.
controler("chaque colonne porte le pic de son apport dans le modele",
          all(abs(float(_hy[f"Apport_{a.nom_apport}"].max()) - p) < 0.02
              for a, p in zip(resultat.apports, pics_modele)),
          "  ".join(f"{float(_hy[f'Apport_{a.nom_apport}'].max()):.1f}/{p:.1f}"
                    for a, p in zip(resultat.apports, pics_modele)))
# BASES HETEROGENES : les colonnes s'alignent sur l'union des instants, et
# la ou un apport n'a pas de valeur la cellule reste VIDE. Y interpoler
# ecrirait un debit que le calcul n'a jamais recu.
_hy_het = pd.read_excel(_dossier_het / "tableaux_calage.xlsx",
                        sheet_name="Hydrogrammes_apports")
# Chaque apport s'arretant a SA fenetre, les colonnes n'ont pas la meme
# hauteur : il DOIT rester des cellules vides. Zero trou signifierait
# qu'on a prolonge ou interpole quelque part.
controler("sur des bases heterogenes, les trous restent vides",
          bool(_hy_het.isna().any().any())
          and len(_hy_het.columns) == len(apports) + 1,
          f"{len(_hy_het)} lignes, {len(_hy_het.columns)} colonnes, "
          f"{int(_hy_het.isna().sum().sum())} cellule(s) vide(s)")

# Depart volontairement faux, comme dans un vrai test a blanc.
print("\n--- DEPART FAUSSE (x0,6), comme au test a blanc T4 ---")
modele2 = ModeleFictif(apports, sections, temps, formes)
modele2.preparer()
for a, f in zip(apports, facteurs_vrais):
    modele2.appliquer_facteur(a, 0.6 * f)
r2 = caler(modele2, apports, sections, cibles,
          Configuration(nb_max_essais=8),
          journal=lambda *a, **k: None)
ecarts2 = [
    abs(_volume(temps, modele2.formes[a.nom_apport]
                * modele2.facteurs[a.nom_apport])
        / _volume(temps, vrais_hydrogrammes[a.nom_apport]) - 1)
    for a in r2.apports]
print(f"   {r2.nb_calculs} calculs, ecart de volume max "
      f"{100 * max(ecarts2):.2f} %, conforme : {r2.conforme}")
# Le depart n'a plus d'influence : la correction additive remplace
# l'hydrogramme des le premier essai.
controler("le depart fausse n'influe pas sur le resultat",
          r2.conforme and max(ecarts2) < 0.05,
          f"ecart de volume max {100 * max(ecarts2):.2f} %")

# -----------------------------------------------------------------------
# LA FORMULE MANUELLE EST CELLE DU CODE — verification directe contre le
# classeur de reference (Example_manuel_methodo.xlsx) : decalage mesure
# UNE FOIS (pic contre pic), puis cible(t - Δt) - section(t), plancher a
# zero, sans aucun autre terme.
# -----------------------------------------------------------------------
print("\n--- LA FORMULE MANUELLE EST CELLE DU CODE ---")
_mt = np.linspace(0.0, 20.0, 201)
_mp = lambda t0: 50.0 * np.exp(-((_mt - t0) ** 2) / 2.0)  # noqa: E731
_m_cible, _m_section = _mp(9.0), _mp(6.0)   # section en avance de 3 h
_m_dt = decalage_minimisant_ecart(_mt, _m_cible, _mt, _m_section)
_m_manuel = np.maximum(
    np.interp(_mt - _m_dt, _mt, _m_cible) - _m_section, 0.0)
_m_code = corriger_apport(
    np.zeros_like(_mt),
    ecart_a_la_cible(_mt, _m_cible, _mt, _m_section, _m_dt))
controler("la formule manuelle (cible(t-Δt) - section(t)) coincide avec "
          "corriger_apport(0, ecart_a_la_cible(...))",
          float(np.max(np.abs(_m_manuel - _m_code))) < 1e-9,
          f"ecart max {float(np.max(np.abs(_m_manuel - _m_code))):.2e}")

print("\n--- FENETRE DE L'EVENEMENT PRINCIPAL (jugement et presentation) ---")
_tf_t = np.linspace(0.0, 48.0, 481)          # 48 h au pas de 6 min
_tf_ecart = 30.0 * np.exp(-((_tf_t - 12.0) ** 2) / 4.0)
_t0, _tfin = fenetre_injection(_tf_t, _tf_ecart)
controler("la fenetre enserre l'evenement, pas toute la simulation",
          0.0 < _t0 < 12.0 < _tfin < 48.0, f"{_t0:.2f} h -> {_tfin:.2f} h")
controler("t0 capte plus large que tf ne coupe (asymetrie voulue)",
          (12.0 - _t0) > (_tfin - 12.0),
          f"montee {12.0 - _t0:.2f} h contre descente {_tfin - 12.0:.2f} h")
controler("un ecart nul rend la fenetre complete",
          fenetre_injection(_tf_t, np.zeros_like(_tf_t)) == (0.0, 48.0))
controler("les bornes imposees remplacent la detection",
          fenetre_injection(_tf_t, _tf_ecart, t0_impose=5.0,
                            tf_impose=20.0) == (5.0, 20.0))
controler("le masque de fenetre est vrai bornes comprises",
          bool(masque_fenetre(np.array([0.0, 5.0, 10.0]),
                              (5.0, 10.0)).tolist() == [False, True, True]))
controler("Fenetre_active=non desactive la fenetre (jugement sur tout)",
          caler(ModeleFictif(["A"], ["S"], temps,
                             [hydrogramme(temps, 10.0)]),
                ["A"], ["S"], [cibles[0]],
                Configuration(fenetre_active=False, nb_max_essais=4),
                journal=lambda *a, **k: None
                ).apports[0].fenetre_principale is None)

print("\n--- Δt MESURE AU RESIDUEL, PAS FORCE A ZERO ---")
# Le residuel, avant tout apport, porte deja un temps de transfert propre
# depuis l'amont non cale, independant de l'apport qu'on cale. Modele
# minimal qui le reproduit : le residuel est un signal FIXE, deja decale
# de la cible, et l'apport s'y ajoute SANS retard propre.
# UNE CLASSE ModeleResiduelDecale VIVAIT ICI, ET N'A JAMAIS ETE
# INSTANCIEE (P2-9 de AUDIT.md). Elle datait d'une epoque ou ce cas
# s'eprouvait en faisant tourner un calage complet ; les deux controles
# ci-dessous ont depuis ete ramenes a ce qu'ils verifient vraiment —
# decalage_minimisant_ecart et ecart_a_la_cible, deux fonctions PURES,
# sans modele ni boucle. Elle est retiree : du code que rien n'appelle
# vieillit sans que rien ne l'eprouve, et donne a croire qu'un cas est
# couvert. Git la garde si elle devait resservir.

_t3 = np.linspace(0.0, 20.0, 201)
_pic3 = lambda t0, a: a * np.exp(-((_t3 - t0) ** 2) / 2.0)  # noqa: E731
_cible3 = _pic3(9.0, 50.0)
# Amplitude MODESTE par rapport a la cible : le residuel reste un signal
# fixe (l'apport ne peut pas le retirer), et une amplitude trop proche de
# la cible laisserait une bosse residuelle qui degraderait la FORME sans
# qu'aucune correction additive ne puisse jamais l'effacer — ce ne serait
# alors plus Δt que ce test eprouve, mais une cible mal choisie.
_residuel3 = _pic3(5.0, 5.0)   # decale de la cible, SANS aucun apport
_decalage_ref3 = decalage_minimisant_ecart(_t3, _cible3, _t3, _residuel3)
controler("le residuel, avant tout apport, porte deja un retard mesurable",
          abs(_decalage_ref3) > 1.0, f"{_decalage_ref3:+.2f} h")

# LA CONVERGENCE N'EST PAS DEMANDEE ICI, deliberement. Le residuel reste
# un signal FIXE qu'aucun apport ne peut retirer : sa bosse propre, a
# t = 5 h, degrade la FORME de la section quel que soit ce qu'on injecte
# a t = 9 h — un defaut de la CIBLE de ce fixture, pas de la correction.
# Ce test ne verifie qu'une chose : que la premiere estimation est batie
# sur CE decalage-la, jamais sur zero.
_manquant3 = ecart_a_la_cible(_t3, _cible3, _t3, _residuel3, _decalage_ref3)
_manquant3_a_zero = ecart_a_la_cible(_t3, _cible3, _t3, _residuel3, 0.0)
controler("la premiere estimation est construite sur le decalage mesure, "
          "pas sur zero",
          float(np.max(np.abs(_manquant3 - _manquant3_a_zero))) > 1.0,
          "les deux estimations different bien")

# Deux situations DISTINCTES, qu'il ne faut pas confondre.
#
# LE SEUIL EST EPINGLE, PAS HERITE DU DEFAUT. Ces deux essais eprouvent le
# MECANISME de rejet, pas la valeur de production : ecrits sur le defaut,
# ils sont passes au vert le jour ou celui-ci est monte de 1 a 5 % — le
# modele fictif rendant exactement 5 %, la comparaison stricte ne
# declenchait plus. Le defaut, lui, a son propre controle plus bas.
_QUALITE = Configuration(bilan_masse_max_pct=1.0)

print("\n--- MODELE DOUTEUX DES LE CALCUL DE REFERENCE ---")
modele3 = ModeleFictif(apports[:1], sections[:1], temps, formes[:1],
                       bilan_masse_pct=5.0)
r3 = caler(modele3, apports[:1], sections[:1], cibles[:1],
           _QUALITE, journal=lambda *a, **k: None)
# Un modele deja instable APPORTS A ZERO ne peut rien caler du tout : le
# dire tout de suite vaut mieux que de consommer des essais.
controler("un modele douteux est arrete des le calcul de reference",
          not r3.apports and "bilan de masse" in r3.motif, r3.motif)
controler("l'arret de reference ne coute qu'un seul calcul",
          r3.nb_calculs == 1, f"{r3.nb_calculs} calcul(s)")

print("\n--- ESSAI REJETE EN COURS DE RECHERCHE ---")
# Modele sain a l'etat de reference, mais qui devient instable des que
# l'apport depasse un seuil : c'est le cas que le garde-fou de qualite
# doit intercepter PENDANT la recherche.
modele3b = ModeleFictif(apports[:1], sections[:1], temps, formes[:1],
                        seuil_instabilite=0.5)
r3b = caler(modele3b, apports[:1], sections[:1], cibles[:1],
            _QUALITE, journal=lambda *a, **k: None)
controler("le calcul de reference d'un modele sain passe",
          r3b.nb_calculs > 1, f"{r3b.nb_calculs} calculs")
controler("un essai devenu instable est rejete, et la recherche s'arrete",
          bool(r3b.apports) and not r3b.apports[0].valide
          and "bilan de masse" in r3b.apports[0].motif,
          r3b.apports[0].motif if r3b.apports else "aucun apport")
controler("tout apport non converge reste non valide",
          all(a.valide == (not a.motif) for a in r3b.apports),
          f"{len(r3b.apports)} apport(s) examine(s)")

# LE DEFAUT DE PRODUCTION A SON PROPRE CONTROLE, separe du mecanisme
# ci-dessus. Il vaut 5 % depuis le 30/08/2026 : a 1 %, un calcul par
# ailleurs sain (1,119 % mesure sur un modele reel) arretait le calage
# des le premier apport. Le changer est une DECISION, pas un reglage :
# ce controle oblige a la prendre sciemment.
controler("le defaut de bilan_masse_max_pct est 5 %",
          Configuration().bilan_masse_max_pct == 5.0,
          f"{Configuration().bilan_masse_max_pct} %")
# LE BILAN N'EST PAS UN ECART A LA CIBLE, et rien ne doit les rapprocher :
# un seuil de qualite numerique qui suivrait la tolerance de volume ferait
# dependre le rejet d'un calcul de la precision demandee a l'etude.
controler("le bilan de masse ne se juge pas contre la tolerance de volume",
          qualite_acceptable(
              ResultatCalcul(reussi=True, bilan_masse_pct=4.0),
              Configuration(tolerance_volume=0.001))[0],
          "un volume exigeant ne rejette pas un calcul sain")

print("\n--- UNE ETAPE OUVERTE N'A PAS ENCORE DE RESULTATS ---")
# LE MODELE FICTIF EST TROP COMPLAISANT POUR CE CAS : il repond a
# lire_section() en tout temps, alors qu'un plan HEC-RAS fraichement clone
# n'a pas de fichier de resultats tant qu'il n'a pas ete calcule. La boucle
# lisait le residuel APRES avoir ouvert l'etape de l'apport : elle le
# cherchait donc dans un plan vide, et TOUT calage s'arretait sur le
# premier apport — apres avoir depense le calcul de reference pour rien
# (cas reel, 20 min perdues). Le modele ci-dessous reproduit cette regle.
class ModeleEtapeStricte(ModeleFictif):
    """Comme HEC-RAS : pas de resultats entre un jalon et son calcul."""

    _calcule = False

    def jalonner(self, etape):
        self._calcule = False
        return super().jalonner(etape)

    def calculer(self):
        self._calcule = True
        return super().calculer()

    def lire_section(self, nom_section):
        if not self._calcule:
            raise RuntimeError(
                "plan sans resultats : le .hdf n'existe pas encore")
        return super().lire_section(nom_section)

modele3c = ModeleEtapeStricte(apports, sections, temps, formes)
r3c = caler(modele3c, apports, sections, cibles,
            Configuration(), journal=lambda *a, **k: None)
controler("le residuel est lu AVANT l'ouverture de l'etape de l'apport",
          all(a.valide for a in r3c.apports)
          and len(r3c.apports) == len(apports),
          r3c.motif or f"{sum(a.valide for a in r3c.apports)}/"
                       f"{len(apports)} apport(s) cale(s)")

print("\n--- SECTION DE CONTROLE ILLISIBLE ---")
# Une section mal nommee ne se manifestait qu'au tour de SON apport, donc
# apres le calage complet de tout l'amont. Elle est desormais detectee au
# calcul de reference, ou toutes les sections sont lisibles ensemble.
modele3d = ModeleFictif(apports[:1], sections[:1], temps, formes[:1])
r3d = caler(modele3d, apports[:1], ["Section_absente"], cibles[:1],
            Configuration(), journal=lambda *a, **k: None)
controler("une section illisible arrete le calage des la reference",
          not r3d.apports and "illisible" in r3d.motif, r3d.motif)
controler("elle est NOMMEE, et l'arret ne coute qu'un calcul",
          "Section_absente" in r3d.motif and r3d.nb_calculs == 1,
          f"{r3d.nb_calculs} calcul(s)")

print("\n--- UNE SECTION AMONT ILLISIBLE EST NOMMEE, PAS AVALEE ---")
# L'etape 7 relit les sections deja calees pour voir si le remous du
# nouvel apport les a deplacees. Celle qu'on ne savait pas lire sortait
# de la liste sur un « except Exception: continue » muet : l'appelant
# n'avait plus de quoi distinguer « aucune section n'a derive » de « je
# n'ai pas pu regarder », et il annoncait le premier. Le banc d'avant ne
# pouvait pas voir la difference — la fonction ne rendait qu'une liste.
class ModeleSectionMuette(ModeleFictif):
    """Une section amont refuse de se laisser relire ; les autres non."""

    def lire_section(self, nom_section):
        if nom_section == sections[0]:
            raise RuntimeError("fichier de resultats verrouille")
        return super().lire_section(nom_section)

modele3e = ModeleSectionMuette(apports, sections, temps, formes)
derives3e, illisibles3e = _sections_derivees(
    modele3e, sections[:3], cibles[:3], Configuration())
controler("la section illisible est RAPPORTEE, pas ignoree",
          [s for s, _ in illisibles3e] == [sections[0]],
          f"illisibles : {[s for s, _ in illisibles3e]}")
controler("elle porte la raison de son echec",
          bool(illisibles3e) and "verrouille" in illisibles3e[0][1],
          illisibles3e[0][1] if illisibles3e else "aucune raison")
controler("les sections lisibles restent examinees",
          all(s != sections[0] for s, _ in derives3e),
          f"{len(derives3e)} derive(s) parmi 2 sections lisibles")
controler("aucune illisible quand toutes se lisent",
          _sections_derivees(modele, sections[:3], cibles[:3],
                             Configuration())[1] == [],
          "liste vide")

print("\n--- DECALAGE NON IDENTIFIABLE ---")
# Aucun decalage ne se lit sur une serie qui ne bouge pas. Le balayage
# rendait pourtant le BORD de son domaine — -12,12 h sur une section
# muette — parce qu'a cout egal il gardait le premier candidat essaye. Le
# deficit n'en etait pas fausse, mais le journal envoyait chercher dans le
# modele un dephasage qui n'existe pas.
cible_temoin = hydrogramme(temps, 40.0)
for libelle, serie in (("muette", np.zeros_like(temps)),
                       ("constante", np.full_like(temps, 12.0))):
    d = decalage_minimisant_ecart(temps, cible_temoin, temps, serie)
    controler(f"une section {libelle} ne fabrique pas de dephasage",
              abs(d) < 1e-9, f"{d:+.2f} h")
# Meme exigence sur le jumeau de criteres, dont se sert diagnostiquer() :
# les deux mesurent la meme grandeur et doivent repondre pareil.
from criteres import recaler as _recaler
_, _, d_criteres = _recaler(temps, np.full_like(temps, 12.0),
                            temps, np.full_like(temps, 12.0))
controler("le recalage du diagnostic non plus",
          abs(d_criteres) < 1e-9, f"{d_criteres:+.2f} h")
# ET IL RETROUVE UN VRAI DECALAGE, sans quoi le controle precedent serait
# satisfait par une fonction qui rendrait toujours zero.
retarde = np.interp(temps - 1.5, temps, cible_temoin)
d_vrai = decalage_minimisant_ecart(temps, cible_temoin, temps, retarde)
controler("un decalage reel est toujours mesure",
          abs(d_vrai - 1.5) < 0.1, f"{d_vrai:+.2f} h pour +1,50 h injecte")

# -----------------------------------------------------------------------
# INVARIANT : UN APPORT REMIS A UN ESSAI ANTERIEUR N'EST JAMAIS VALIDE.
#
# Tout repose la-dessus. C'est ce qui autorise la verification globale a
# RELIRE le dernier calcul au lieu d'en lancer un : si un apport remis en
# place pouvait etre valide, le modele porterait l'essai retenu pendant
# que le fichier de resultats porterait le dernier, et le tableau de bord
# decrirait autre chose que ce que le modele contient.
# -----------------------------------------------------------------------
import ast
import inspect
import textwrap

# LE COMPTE SUIT caler() DANS SES ETAPES. Il se faisait sur la seule
# source de caler() : la boucle d'essais sortie dans une fonction, il
# aurait rendu zero — et, pire, une seconde chance glissee dans une etape
# serait passee sans etre vue. On compte donc dans caler() ET, de proche
# en proche, dans toute fonction de ce module qu'il nomme.
#   « CE MODULE » EST CELUI DE caler(), pas celui ou ce controle est
# ecrit : le jour ou le banc vit dans un autre fichier, ses globales ne
# sont plus celles de la boucle, et un compte fait sur elles ne suivrait
# plus rien.
_module_de_caler = vars(sys.modules[caler.__module__])

def _appels_a(nom, fonction, vues):
    if fonction in vues:
        return 0
    vues.add(fonction)
    total = 0
    for n in ast.walk(ast.parse(textwrap.dedent(
            inspect.getsource(fonction)))):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == nom):
            total += 1
        elif isinstance(n, ast.Name) and n.id != nom:
            nommee = _module_de_caler.get(n.id)
            if (inspect.isfunction(nommee)
                    and nommee.__module__ == caler.__module__):
                total += _appels_a(nom, nommee, vues)
    return total

_etapes_de_caler = set()
_appels = _appels_a("concordance", caler, _etapes_de_caler)
controler("aucune seconde chance d'acceptation apres le retour au meilleur",
          _appels == 1,
          f"{_appels} appel(s) reel(s) a concordance() dans caler() et les "
          f"{len(_etapes_de_caler) - 1} fonctions du module qu'il nomme — "
          f"un seul, dans la boucle d'essais")

# -----------------------------------------------------------------------
# L'ARRET PORTE SUR « rapport_volume ».
# -----------------------------------------------------------------------
_c = Configuration()
_bon = type("D", (), {"r": 0.99, "decalage_h": 0.0, "rapport_pic": 1.005,
                      "rapport_volume": 1.002})()
controler("la concordance se prononce sur le volume",
          concordance(_bon, _c), f"volume {_bon.rapport_volume} conforme")
_mauvais = type("D", (), {"r": 0.99, "decalage_h": 0.0,
                          "rapport_pic": 1.005, "rapport_volume": 1.30})()
controler("un volume faux est refuse",
          not concordance(_mauvais, _c),
          f"volume {_mauvais.rapport_volume} refuse")
controler("le meilleur essai se choisit lui aussi sur le volume",
          ecart_combine(_bon, _c) < ecart_combine(_mauvais, _c),
          f"{ecart_combine(_bon, _c):.2f} < "
          f"{ecart_combine(_mauvais, _c):.2f}")

# --- selection : admissibilite d'abord, erreur combinee ensuite --------
def _diag(volume, pic, forme):
    return type("D", (), {"decalage_h": 0.0, "rapport_volume": volume,
                          "rapport_pic": pic, "r": forme})()

_juste = _diag(1.0005, 1.0002, 0.999)      # les trois dans les clous
_limite = _diag(1.0049, 1.0199, 0.9701)    # les trois tout juste tenus
_hors = _diag(1.0000, 1.0500, 1.000)       # pointe hors seuil
controler("les trois seuils tenus : l'essai est admissible",
          admissible(_juste, _c) and admissible(_limite, _c))
controler("un seul seuil depasse suffit a rendre inadmissible",
          not admissible(_hors, _c),
          f"pointe {100 * _hors.rapport_pic:.1f} %")
controler("l'erreur combinee prefere l'essai proche des TROIS cibles",
          ecart_combine(_juste, _c) < ecart_combine(_limite, _c),
          f"{ecart_combine(_juste, _c):.2f} < "
          f"{ecart_combine(_limite, _c):.2f}")
controler("l'admissibilite prime sur une erreur combinee plus faible",
          rang_essai(_limite, _c) < rang_essai(_hors, _c),
          f"admissible {ecart_combine(_limite, _c):.2f} avant "
          f"inadmissible {ecart_combine(_hors, _c):.2f}")

# Progression du pic : distingue une recherche qui plafonne d'une
# recherche qui avancait encore quand les essais ont ete epuises.
controler("une pointe qui progresse encore est detectee",
          abs(_progression_pic([{"pic": 0.937}, {"pic": 0.941}])
              - 0.004) < 1e-9,
          f"{_progression_pic([{'pic': 0.937}, {'pic': 0.941}]):.4f}")
controler("une pointe qui plafonne ne l'est pas",
          _progression_pic([{"pic": 0.945}, {"pic": 0.945}]) == 0.0)
controler("un historique trop court ne fabrique pas de progression",
          _progression_pic([{"pic": 0.94}]) is None)

# CIBLE HORS D'ATTEINTE — la correction additive injecte simplement ce
# qui manque. Ce qui reste hors d'atteinte, c'est une cible INFERIEURE a
# ce que la section recoit deja : un apport ne peut qu'ajouter du debit.
print("\n--- CIBLE HORS D'ATTEINTE : PLUS BASSE QUE LE RESIDUEL ---")
t_c, q_c = cibles[0]
# Debit permanent important : la section est deja bien au-dessus de la
# cible demandee, apports a zero.
base = hydrogramme(temps, 60.0)
modele4 = ModeleFictif(apports[:1], sections[:1], temps, formes[:1],
                       debit_base=base)
r4 = caler(modele4, apports[:1], sections[:1], [(t_c, q_c * 0.05)],
           Configuration(nb_max_essais=5), journal=lambda *a, **k: None)
controler("une cible sous le residuel est refusee, avec la raison",
          not r4.apports[0].valide
          and "recoit deja" in r4.apports[0].motif,
          r4.apports[0].motif[:90])

# APPORT PEU IDENTIFIABLE. Meme montage, mais la cible passe JUSTE
# au-dessus du residuel : l'apport ne pese plus que quelques pour-cent du
# debit a la section, et la bande de tolerance admise vaut alors plusieurs
# fois l'apport lui-meme. La section se calera ; l'apport sorti n'aura
# aucune valeur d'estimation, et la chaine doit le DIRE avant de calculer.
print("\n--- APPORT TROP PETIT DEVANT LE DEBIT DE SA SECTION ---")
_dits = []
# 2 % : la part mesuree sur le cas reel qui a motive ce garde-fou.
modele4bis = ModeleFictif(apports[:1], sections[:1], temps, formes[:1],
                          debit_base=base)
_r4bis = caler(modele4bis, apports[:1], sections[:1],
               [(temps, base / 0.98)],
               Configuration(nb_max_essais=2), journal=_dits.append)
_alerte = [l for l in _dits if "PEU IDENTIFIABLE" in l]
controler("un apport pesant 2 % du debit est annonce peu identifiable",
          bool(_alerte), (_alerte[0][:110] if _alerte else "aucune alerte"))
controler("l'alerte chiffre la part et l'ecart possible",
          bool(_alerte) and "2.0 %" in _alerte[0] and "250 %" in _alerte[0],
          _alerte[0][60:170] if _alerte else "")
# ET LE DIAGNOSTIC LA PORTE (07/09/2026) : c'est lui, et non le journal,
# que lisent le classeur, la note de synthese et le suivi. Une seule fois
# — chaque essai la porte, donc le retour au meilleur essai n'a rien a
# rattraper — et jamais parmi les bloquantes : elle dit, elle ne juge pas.
_diag4bis = _r4bis.apports[0].diagnostic
controler("la reserve est portee par le diagnostic RETENU, une seule fois",
          sum("PEU IDENTIFIABLE" in a for a in _diag4bis.alertes) == 1,
          f"{len(_diag4bis.alertes)} alerte(s)")
controler("elle ne bloque pas",
          not any("PEU IDENTIFIABLE" in a
                  for a in _diag4bis.alertes_bloquantes))
controler("la part elle-meme est portee, comme un nombre",
          _diag4bis.part_apport is not None
          and abs(_diag4bis.part_apport - 0.02) < 1e-9,
          f"part_apport={_diag4bis.part_apport}")
if _r4bis.diagnostics_finaux:
    import livrables as liv
    _fin4bis = _r4bis.diagnostics_finaux[0]
    controler("elle atteint la verification finale, une fois",
              sum("PEU IDENTIFIABLE" in a for a in _fin4bis.alertes) == 1,
              f"{len(_fin4bis.alertes)} alerte(s)")
    controler("la colonne « Alertes » du classeur la porte",
              "PEU IDENTIFIABLE" in liv.tableau_de_bord(
                  sections[:1], [_fin4bis])["Alertes"].iloc[0])
else:
    controler("la verification finale a eu lieu (apport cale en 2 essais)",
              False, f"valide={_r4bis.apports[0].valide}, "
              f"motif={_r4bis.apports[0].motif[:70]}")

# ET LE CAS SYMETRIQUE : un apport qui pese lourd ne doit RIEN declencher,
# sans quoi l'alerte deviendrait un bruit de fond qu'on cesse de lire.
_dits_gros = []
modele4ter = ModeleFictif(apports[:1], sections[:1], temps, formes[:1])
_r4ter = caler(modele4ter, apports[:1], sections[:1], [cibles[0]],
               Configuration(nb_max_essais=3), journal=_dits_gros.append)
controler("un apport qui pese lourd ne declenche pas l'alerte",
          not [l for l in _dits_gros if "PEU IDENTIFIABLE" in l])
_d4ter = _r4ter.apports[0].diagnostic
controler("ni ne charge la colonne « Alertes » de sa section",
          _d4ter is not None
          and not any("PEU IDENTIFIABLE" in a for a in _d4ter.alertes),
          " ; ".join(_d4ter.alertes)[:80] if _d4ter else "aucun diagnostic")

# La resolution sequentielle suppose l'amont fige : un apport non cale
# rend tout ce qui suit sans objet.
modele5 = ModeleFictif(apports[:2], sections[:2], temps, formes[:2],
                       debit_base=base)
r5 = caler(modele5, apports[:2], sections[:2],
           [(t_c, q_c * 0.05), cibles[1]],
           Configuration(nb_max_essais=4), journal=lambda *a, **k: None)
controler("les apports suivants ne sont pas traites apres un echec",
          len(r5.apports) == 1 and not r5.apports[0].valide,
          f"{len(r5.apports)} apport(s) traite(s) sur 2")

# --- VOLUME PLANCHER : LE CLIQUET DU PLANCHER A ZERO ------------------
#
# Le cliquet est enonce dans la note depuis la V13 — « le plancher a zero,
# et le cliquet qui en decoule » — et n'etait mesure NULLE PART. caler()
# ne refusait que le cas TOTAL : une cible entierement sous le residuel.
# Entre les deux vit le cas ordinaire, et couteux.
print("\n--- VOLUME PLANCHER : LE CLIQUET DU PLANCHER A ZERO ---")

# D'abord la formule, sur un cas qui se calcule a la main : une cible a
# 100 sur 10 h (volume 1000), un residuel a 150 sur les 5 premieres
# heures (exces 50 x 5 h = 250). Plancher = 1 + 250/1000 = 1,25.
_tk = np.linspace(0.0, 10.0, 1001)
_ck = np.full_like(_tk, 100.0)
_rk = np.where(_tk <= 5.0, 150.0, 0.0)
_mk = ecart_a_la_cible(_tk, _ck, _tk, _rk, 0.0)
controler("le cliquet vaut 1 + volume de l'exces / volume de la cible",
          abs(cliquet_volume(_tk, _ck, _mk, 0.0) - 1.25) < 0.005,
          f"{cliquet_volume(_tk, _ck, _mk, 0.0):.4f} pour 1,2500 attendu")
controler("un residuel partout sous la cible ne cliquette pas",
          abs(cliquet_volume(_tk, _ck,
                             ecart_a_la_cible(_tk, _ck, _tk, _ck * 0.5, 0.0),
                             0.0) - 1.0) < 1e-9, "1,0000")
# LA FENETRE BORNE LA MESURE, comme elle borne le volume qu'elle predit :
# un exces hors de ce qui est juge ne pesera pas sur le verdict, et
# l'annoncer serait une fausse alerte.
controler("un exces hors de la fenetre jugee ne cliquette pas",
          abs(cliquet_volume(_tk, _ck, _mk, 0.0, fenetre=(6.0, 10.0))
              - 1.0) < 1e-9, "1,0000")
controler("le meme exces, plein cadre, cliquette a 150 %",
          abs(cliquet_volume(_tk, _ck, _mk, 0.0, fenetre=(0.0, 5.0))
              - 1.5) < 0.005, "1,5000")

# PUIS CE QUE CA VAUT EN VRAI. Un residuel pointu qui deborde la cible au
# sommet et reste dessous sur les flancs : max(manquant) > 0, donc le
# refus total ne se declenche pas, et le calage part pour de bon.
_tc2 = np.linspace(0.01, 36, 400)
_cible_k = hydrogramme(_tc2, 100.0, t_pic=12.0, forme=2.0)
_base_k = hydrogramme(_tc2, 140.0, t_pic=12.0, forme=8.0)
_dits_k = []
_mk2 = ModeleFictif(["A1"], ["S1"], _tc2, [hydrogramme(_tc2, 10.0)],
                    debit_base=_base_k)
_rk2 = caler(_mk2, ["A1"], ["S1"], [(_tc2, _cible_k)],
             Configuration(nb_max_essais=8), journal=_dits_k.append)
_annonce = [l for l in _dits_k if "VOLUME PLANCHER" in l]
controler("un residuel qui deborde en partie declenche l'alerte",
          bool(_annonce), (_annonce[0][:110] if _annonce else "aucune"))
_atteint = 100 * _rk2.apports[0].diagnostic.rapport_volume
_predit = (float(_annonce[0].split("d'environ ")[1].split(" %")[0])
          if _annonce else 0.0)
# LE CHIFFRE ANNONCE EST-IL LE BON ? C'est tout l'interet : il est connu
# AVANT le premier essai, et le calage n'a jamais pu descendre en dessous.
controler("le plancher annonce est celui que le calage atteint",
          abs(_predit - _atteint) < 1.0,
          f"annonce {_predit:.1f} %, atteint {_atteint:.1f} % "
          f"apres {len(_rk2.apports[0].historique)} essai(s)")
controler("et le calage echoue bien, faute de pouvoir descendre",
          not _rk2.apports[0].valide, _rk2.apports[0].motif[:80])
# ET LE VERDICT LE DIT. L'annonce partait au journal, que personne ne
# relit une fois le calage fini ; le motif, lui, est repris partout —
# classeur, note de synthese, jauges. Il accusait le modele.
controler("le motif nomme le plancher, et n'accuse plus le modele",
          "NE POUVAIT PAS DESCENDRE" in _rk2.apports[0].motif
          and "apports amont" in _rk2.apports[0].motif,
          _rk2.apports[0].motif[-150:])
# UN ECHEC ORDINAIRE NE DOIT PAS HERITER DE CETTE PHRASE — ni du cliquet
# de l'apport precedent, la boucle portant sur les apports.
_rk3 = caler(ModeleFictif(apports[:1], sections[:1], temps, formes[:1]),
             apports[:1], sections[:1], [(temps, hydrogramme(temps, 1e4))],
             Configuration(nb_max_essais=2), journal=lambda *a, **k: None)
controler("un echec sans plancher n'herite pas de la phrase",
          "NE POUVAIT PAS DESCENDRE" not in _rk3.apports[0].motif,
          _rk3.apports[0].motif[:80])
# LE CAS SYMETRIQUE : un calage ordinaire ne doit RIEN annoncer, sans quoi
# l'alerte devient un bruit de fond qu'on cesse de lire.
_dits_sain = []
caler(ModeleFictif(apports[:1], sections[:1], temps, formes[:1]),
      apports[:1], sections[:1], [cibles[0]],
      Configuration(nb_max_essais=3), journal=_dits_sain.append)
controler("un calage ordinaire n'annonce aucun plancher",
          not [l for l in _dits_sain if "VOLUME PLANCHER" in l])

# --- DUREE SIMULEE AJUSTEE A CHAQUE APPORT ----------------------------
# Le modele fictif TRONQUE reellement ses series a la duree demandee : un
# ajustement trop court se paierait donc en concordance, et se verrait.
print("\n--- DUREE SIMULEE AJUSTEE A CHAQUE APPORT ---")
_t6 = np.linspace(0.0, 40.0, 401)
# Deux apports dont les evenements finissent LOIN l'un de l'autre : le
# premier a 6 h, le second a 20 h. C'est la configuration qui rend
# l'ajustement payant, et celle ou une troncature fautive se voit.
_f6 = [np.exp(-0.5 * ((_t6 - 3.0) / 1.0) ** 2),
       np.exp(-0.5 * ((_t6 - 14.0) / 2.5) ** 2)]
_m6 = ModeleFictif(["A1", "A2"], ["S1", "S2"], _t6, _f6, retard_h=0.0)
_cibles6 = []
for _k in range(2):
    _m6.facteurs = {"A1": 30.0, "A2": 45.0}
    _cibles6.append((_t6, _m6.lire_section(f"S{_k + 1}")[1].copy()))
_m6.duree_max, _m6.durees_demandees = None, []
_r6 = caler(_m6, ["A1", "A2"], ["S1", "S2"], _cibles6,
            Configuration(nb_max_essais=4),
            journal=lambda *a, **k: None)
# CE MONTAGE N'EPROUVE PAS LA TRONCATURE, MAIS LA MESURE DU DECALAGE —
# et il faut le dire, parce que son nom d'origine (« le calage aboutit
# malgre la troncature ») designait la mauvaise cause pendant des
# semaines.
#
# Le residuel de S2, apport A2 a zero, est la contribution de A1 : elle
# pique a 3 h quand la cible de S2 pique a 14 h. decalage_minimisant_ecart
# aligne l'un sur l'autre et rend Dt = -11 h, ce qui place la fenetre de
# jugement hors de l'evenement de A2. C'EST EXACTEMENT LA PATHOLOGIE DE
# LA SECTION 5.3 DE STATUT.txt : un Dt qui n'est pas un temps de transfert
# mais l'ecart entre deux pics qui ne decrivent pas la meme eau.
#
# MESURE DU 31/08/2026 — le rapport d'amplitude n'y est pour rien :
# facteurs A1/A2 = 30/45, 5/45 puis 2/60 rendent TOUS Dt = -11,00 h. Le
# montage n'est donc pas un artefact a corriger, il est fidele ; c'est la
# mesure du decalage qui est en cause (point ouvert V2 : juger le decalage
# sur sa COHERENCE LE LONG DE L'AXE, section 6 de STATUT.txt).
#
# CE QU'ON EXIGE DONC ICI : que la chaine REFUSE l'apport et le DISE,
# plutot que de le caler de travers en silence.
#
# CE CONTROLE A BASCULE LE 09/09/2026, ET C'ETAIT ANNONCE. Il tenait
# jusque-la PAR ACCIDENT : diagnostiquer() lisait la fenetre sur la base
# de temps de la cible alors qu'elle est en temps de SIMULATION, ce qui
# rendait des pourcentages absurdes des que Dt etait grand — l'apport
# echouait pour la mauvaise raison. La fenetre reparee (voir
# criteres.diagnostiquer, parametre decalage_fenetre_h), l'appariement
# devient coherent et ce montage rendait « conforme » un apport cale onze
# heures trop tot. Le refus est desormais PORTE PAR SON PROPRE
# GARDE-FOU : un decalage plus long que la fenetre qu'il decale est
# bloquant, et le motif nomme la cause au lieu d'accuser l'hydraulique.
#
# LE MOTIF NOMME LA SECTION, PAS L'APPORT — c'est la section dont la
# comparaison n'a plus d'objet, et c'est elle qu'on va relire.
# Que la troncature ne casse PAS un calage sain est eprouve plus bas,
# sur le montage a traine fine.
controler("un decalage aberrant fait refuser l'apport, et le DIT",
          (not _r6.conforme)
          and "S2" in (_r6.motif or "")
          and "excede la fenetre jugee" in (_r6.motif or ""),
          (_r6.motif or "conforme")[:120])
controler("et il renvoie aux cibles, pas au modele",
          "pas un temps de transfert" in (_r6.motif or ""),
          (_r6.motif or "conforme")[-90:])
controler("la duree est bien raccourcie, apport par apport",
          len(_m6.durees_demandees) >= 1
          and _m6.durees_demandees[0] < 40.0,
          f"durees demandees : "
          f"{[round(d, 1) for d in _m6.durees_demandees]}")
controler("elle ne DECROIT jamais d'un apport au suivant",
          _m6.durees_demandees == sorted(_m6.durees_demandees),
          f"{[round(d, 1) for d in _m6.durees_demandees]}")
controler("le premier apport coute moins que le second",
          _m6.durees_demandees[0] < _m6.durees_demandees[-1]
          if len(_m6.durees_demandees) > 1 else True,
          f"{[round(d, 1) for d in _m6.durees_demandees]}")
# LE DEFAUT EST DEBRAYABLE, et le debrayer doit tout laisser intact.
_m7 = ModeleFictif(["A1", "A2"], ["S1", "S2"], _t6, _f6, retard_h=0.0)
_r7 = caler(_m7, ["A1", "A2"], ["S1", "S2"], _cibles6,
            Configuration(nb_max_essais=4, ajuster_duree=False),
            journal=lambda *a, **k: None)
controler("ajuster_duree=False ne raccourcit rien",
          _m7.durees_demandees == [] and _m7.duree_max is None,
          f"{_m7.durees_demandees}")
controler("et rend le meme verdict", _r7.conforme == _r6.conforme,
          f"{_r7.conforme} vs {_r6.conforme}")

# FENETRE DESACTIVEE : LA DUREE NE DOIT PLUS ETRE TOUCHEE NON PLUS.
# Ce controle manquait, et son absence a laisse passer un defaut qui
# rendait NON CONFORME un calage par ailleurs parfait : la duree etait
# raccourcie sur une fenetre que le jugement n'utilisait pas, et la
# couverture — mesuree alors sur TOUTE la cible — levait sa bloquante
# « allonger la simulation ». La cible porte ici une traine fine, comme
# les vraies : sans elle, la couverture passe et le defaut se cache.
_t8 = np.linspace(0.0, 40.0, 401)
_f8 = [np.exp(-0.5 * ((_t8 - 4.0) / 1.2) ** 2)
       + 0.004 * np.exp(-(_t8 - 4.0) / 25.0) * (_t8 > 4)]
_cibles8 = []
for _sans in (False, True):
    _m8 = ModeleFictif(["A1"], ["S1"], _t8, _f8, retard_h=0.0)
    _m8.facteurs = {"A1": 40.0}
    if not _cibles8:
        _cibles8 = [(_t8, _m8.lire_section("S1")[1].copy())]
    _m8.duree_max, _m8.durees_demandees = None, []
    _r8 = caler(_m8, ["A1"], ["S1"], _cibles8,
                Configuration(nb_max_essais=4,
                              fenetre_active=(False if _sans else None)),
                journal=lambda *a, **k: None)
    if _sans:
        controler("fenetre_active=non ne raccourcit rien non plus",
                  _m8.durees_demandees == [] and _m8.duree_max is None,
                  f"durees demandees : {_m8.durees_demandees}")
        controler("et le calage reste conforme, sans bloquante de "
                  "couverture", _r8.conforme,
                  _r8.motif or "conforme")
    else:
        controler("fenetre active : la duree EST bien raccourcie",
                  len(_m8.durees_demandees) == 1
                  and _m8.durees_demandees[0] < 40.0,
                  f"durees demandees : "
                  f"{[round(d, 1) for d in _m8.durees_demandees]}")

# LE PLAFOND ROGNE LA MARGE, ET LE DIT — SANS ALERTE NI ECHEC.
#
# Serie de 20 h, evenement centre sur 14 h : le calendrier veut 21,7 h et
# le plafond n'en donne que 20. Ce qui se perd est la MARGE ; la fenetre
# jugee (7,9 -> 19,7 h) reste couverte, et le calage doit rester conforme.
# Decision du 31/08/2026 : journal seulement. Une marge existe pour etre
# rognee, et un garde-fou qui se declenche pour une perte sans consequence
# apprend a etre ignore. Le jour ou la FENETRE ne rentrerait plus, c'est la
# couverture qui le dirait (criteres.diagnostiquer, section 4 ter).
_t9 = np.linspace(0.0, 20.0, 201)
_f9 = [np.exp(-0.5 * ((_t9 - 14.0) / 2.0) ** 2)
       + 0.004 * np.exp(-(_t9 - 14.0) / 25.0) * (_t9 > 14.0)]
_m9 = ModeleFictif(["A1"], ["S1"], _t9, _f9, retard_h=0.0)
_m9.facteurs = {"A1": 40.0}
_cibles9 = [(_t9, _m9.lire_section("S1")[1].copy())]
_m9.duree_max, _m9.durees_demandees = None, []
_dits9 = []
_r9 = caler(_m9, ["A1"], ["S1"], _cibles9,
            Configuration(nb_max_essais=4), journal=_dits9.append)
_rogne9 = [l for l in map(str, _dits9) if "voulues" in l]
controler("le plafond qui rogne la marge le DIT au journal",
          bool(_rogne9), _rogne9[0].strip()[:95] if _rogne9 else "rien")
controler("il chiffre la marge perdue et rassure sur la fenetre",
          bool(_rogne9) and "de marge en moins" in _rogne9[0]
          and "fenetre jugee reste couverte" in _rogne9[0],
          _rogne9[0].strip()[:95] if _rogne9 else "rien")
controler("et le calage reste CONFORME : rien de juge ne manque",
          _r9.conforme, _r9.motif or "conforme")
controler("aucune alerte n'est levee pour une simple perte de marge",
          bool(_r9.apports) and not _r9.apports[0].diagnostic.alertes,
          str(_r9.apports[0].diagnostic.alertes) if _r9.apports else "?")

# --- COHERENCE DU DECALAGE LE LONG DE L'AXE -------------------------
print("\n--- CIBLE DECALEE AVANT LE DEBUT DE LA SIMULATION ---")
# Le cas reel du 30/10/2026 : l'entree amont culmine a 2 h, la cible
# du premier apport a 4,5 h. Δt vaut environ -2,1 h ici : sans retard de
# l'axe, la cible decalee commence avant t = 0 et l'apport demarre haut.
_tk = np.round(np.arange(0.0, 26.0 + 1e-9, 0.1), 6)
_base_k5 = hydrogramme(_tk, 1.7, t_pic=2.0)
_cible_k5 = hydrogramme(_tk, 3.4, t_pic=4.5)

class _SansRetard(ModeleFictif):
    def retarder(self, heures, apports):
        return None

def _caler_k5(classe):
    _dits_k5 = []
    _m = classe(["K1"], ["SK1"], _tk, [np.zeros_like(_tk)],
                debit_base=_base_k5)
    _r = caler(_m, ["K1"], ["SK1"], [(_tk, _cible_k5)],
               Configuration(nb_max_essais=6), journal=_dits_k5.append)
    return _m, _r, " ".join(map(str, _dits_k5))

_m0, _r0, _j0 = _caler_k5(_SansRetard)
_q0 = float(_m0.formes["K1"][0])
controler("sans retard possible, la perte de la montee est DITE",
          "ne sait pas retarder" in _j0 and "avant le debut" in _j0)
controler("et l'apport demarre haut des t = 0 : c'est le defaut signale",
          _q0 > 0.2 * 3.4, f"{_q0:.2f} m3/s a t = 0")

_m1, _r1, _j1 = _caler_k5(ModeleFictif)
_q1 = float(_m1.formes["K1"][0])
controler("le modele est retarde, et le retard est rapporte",
          _r1.retard_axe_h > 1.0
          and any("axe temporel" in a for a in _r1.alertes_chaine),
          f"{_r1.retard_axe_h:.1f} h")
controler("un second calcul de reference suit le retard",
          "nouveau calcul de reference" in _j1)
controler("aucune cible ne commence plus avant la simulation",
          "commence" not in _j1.split("nouveau calcul de reference")[-1])
controler("l'apport part de presque rien : la montee est injectee",
          _q1 < 0.02 * 3.4, f"{_q1:.3f} m3/s a t = 0")
controler("et l'apport se cale",
          _r1.apports and _r1.apports[0].valide,
          _r1.apports[0].motif[:90] if _r1.apports else "")

print("\n--- COHERENCE DU DECALAGE LE LONG DE L'AXE ---")
# DEUX MODELES REELS, PAS DES INVENTIONS : les pics et les Dt sont ceux
# releves aux journaux des 31/08 et 01/09/2026. LE MODELE B EST LA POUR UNE
# RAISON PRECISE — il passait sous les premiers seuils (pente ET
# correlation) alors qu'il derive PLUS que le modele A. C'est lui qui a
# impose le critere d'etendue ; sans ce controle, rien n'empecherait d'y
# revenir.
_t10 = np.linspace(0.0, 40.0, 401)

def _bosse(t_pic, amplitude=50.0):
    return amplitude * np.exp(-0.5 * ((_t10 - t_pic) / 2.0) ** 2)

def _mesurer(pics_cibles, pics_modele):
    _cib = [(_t10, _bosse(p)) for p in pics_cibles]
    _res = [(_t10, _bosse(p, 20.0)) for p in pics_modele]
    _dits = []
    return _coherence_decalage(_cib, _res, Configuration(),
                               _dits.append), _dits, _cib, _res

# --- MODELE A : derive nette et monotone, -0,70 de pente, r -0,98 -------
_pics_a = [3.0, 4.5, 5.5, 6.5, 7.0, 7.0, 8.5, 9.5]
_mod_a = [3.10, 3.10, 3.50, 3.60, 3.80, 4.00, 4.20, 5.20]
_al_a, _dits_a, _cib_a, _res_a = _mesurer(_pics_a, _mod_a)
controler("modele A : la derive du decalage leve l'alerte",
          bool(_al_a), (_al_a or "aucune")[:90])
controler("l'etendue de Dt y est chiffree, avec son seuil",
          bool(_dits_a) and "s'etend sur 4.4 h" in _dits_a[0]
          and "seuil" in _dits_a[0],
          _dits_a[0].strip()[95:200] if _dits_a else "rien dit")
controler("pente et correlation restent RAPPORTEES",
          bool(_dits_a) and "-0.70" in _dits_a[0] and "-0.98" in _dits_a[0],
          _dits_a[0].strip()[-40:] if _dits_a else "")
controler("et les deux progressions le long de l'axe",
          bool(_dits_a) and "+0.26" in _dits_a[0] and "+0.84" in _dits_a[0],
          _dits_a[0].strip()[60:150] if _dits_a else "")

# --- MODELE B : LE CAS QUI PASSAIT, et qui derive le plus --------------
# Derive NON monotone (-0,70 +0,40 -1,10 +2,30 +3,40 +5,90), donc r = 0,73 :
# sous l'ancien « |r| > 0,9 » il ne levait rien, avec une etendue de 7,0 h
# contre 4,4 pour le modele A. Le sens est aussi INVERSE — ici le modele
# route plus lentement que les cibles.
_pics_b = [11.0, 12.5, 14.5, 15.5, 15.5, 16.0]
_mod_b = [10.3, 12.9, 13.4, 17.8, 18.9, 21.9]
_al_b, _dits_b, _cib_b, _res_b = _mesurer(_pics_b, _mod_b)
controler("modele B : il leve l'alerte, LUI AUSSI",
          bool(_al_b), (_al_b or "AUCUNE — regression")[:90])
controler("son etendue de 7,0 h depasse celle du modele A",
          bool(_dits_b) and "s'etend sur 7.0 h" in _dits_b[0],
          _dits_b[0].strip()[95:175] if _dits_b else "rien dit")
controler("alors que sa correlation, seule, l'aurait ecarte",
          bool(_dits_b) and "+0.73" in _dits_b[0],
          "r = +0,73 < 0,9 : c'est le defaut de l'ancien critere")

# --- LE CAS SAIN : un decalage CONSTANT, quelle que soit sa valeur -----
# Deja manque une fois : la premiere version sortait avant d'imprimer
# quand l'ecart ne variait pas, si bien que le seul cas a ne rien
# rapporter etait le bon.
_al_s, _dits_s, _, _ = _mesurer(_pics_a, [p - 1.0 for p in _pics_a])
controler("un decalage constant ne leve AUCUNE alerte",
          _al_s is None, str(_al_s)[:80])
controler("mais il est quand meme CHIFFRE au journal",
          bool(_dits_s) and "constant" in _dits_s[0],
          _dits_s[0].strip()[60:170] if _dits_s else "rien dit")

# --- CE QUE LE SEUIL RELATIF ACHETE -----------------------------------
# Une derive FAIBLE devant la duree de l'evenement ne doit rien lever :
# c'est tout l'interet d'un seuil en pourcentage plutot qu'en heures.
_al_f, _dits_f, _, _ = _mesurer(
    _pics_b, [p - 0.5 * (k % 2) for k, p in enumerate(_pics_b)])
controler("une derive faible devant l'evenement ne leve rien",
          _al_f is None, (_al_f or "aucune")[:70])
controler("le seuil est bien RELATIF a la fenetre jugee",
          bool(_dits_f) and "% d'une fenetre de" in _dits_f[0],
          _dits_f[0].strip()[95:185] if _dits_f else "rien dit")

controler("moins de quatre apports : aucune derive, aucune alerte",
          _coherence_decalage(_cib_a[:3], _res_a[:3], Configuration(),
                              lambda *a, **k: None) is None)
controler("un residuel illisible est simplement ignore",
          _coherence_decalage(_cib_a, [None] * 8, Configuration(),
                              lambda *a, **k: None) is None)
# L'ALERTE REMONTE-T-ELLE JUSQU'AU RESULTAT ? Le canal est neuf : sans ce
# controle, la mesure resterait dans le journal.
controler("ResultatCalage porte le canal des alertes de chaine",
          isinstance(ResultatCalage().alertes_chaine, list)
          and ResultatCalage().alertes_chaine == [])

# --- JUGEE A LA FIN, SUR LES Dt RETENUS (04/09/2026) --------------------
# Le critere s'evaluait sur le calcul de reference, tous apports a zero :
# sections aval affamees, derive fabriquee par le rang. Sur un modele qui
# ne derive pas (etendue 1,8 h une fois cale) il a livre une reserve pour
# 7,2 h. Ici : la ligne « coherence » doit sortir APRES la verification
# finale, et son etendue doit etre celle des Dt RETENUS au journal.
import re as _re
_m11 = ModeleFictif(apports, sections, temps, formes)
for _a, _f in zip(apports, facteurs_vrais):
    _m11.appliquer_facteur(_a, _f)
_cib11 = [_m11.lire_section(s) for s in sections]
_m11.preparer()
_dits11 = []
caler(_m11, apports, sections, _cib11, Configuration(nb_max_essais=8),
      journal=_dits11.append)
_lignes11 = [str(l) for l in _dits11]
_i_coh = next((k for k, l in enumerate(_lignes11)
               if "coherence du decalage" in l), None)
_i_verif = next((k for k, l in enumerate(_lignes11)
                 if "Verification globale finale" in l), None)
_i_premier = next((k for k, l in enumerate(_lignes11)
                   if "decalage retenu" in l), None)
controler("la coherence du decalage est jugee APRES la verification finale",
          _i_coh is not None and _i_verif is not None and _i_coh > _i_verif,
          f"coherence a la ligne {_i_coh}, verification a {_i_verif}, "
          f"premier « decalage retenu » a {_i_premier}")
_retenus = [float(m.group(1)) for l in _lignes11
            for m in [_re.search(r"decalage retenu ([+-]\d+\.\d+) h", l)]
            if m]
_etendue_dite = next(
    (float(m.group(1)) for l in _lignes11
     for m in [_re.search(r"s'etend sur (\d+\.\d+) h", l)] if m), None)
controler("et son etendue est celle des Dt RETENUS, pas d'une relecture",
          len(_retenus) == len(apports) and _etendue_dite is not None
          and abs(_etendue_dite - (max(_retenus) - min(_retenus))) < 0.051,
          f"retenus {_retenus} ; dit : {_etendue_dite} h")

# --- LE TROISIEME CALAGE REEL, SUR SES Dt RETENUS (04/09/2026) -----------
# Six apports d'un modele de production : pics cibles du classeur, Dt
# retenus et fenetres jugees releves au journal. Etendue 1,8 h pour des
# fenetres de 15,5 h en mediane : AUCUNE alerte — la ou la lecture a
# apports nuls annoncait 7,2 h.
_pics_r = [11.0, 12.5, 14.5, 15.5, 15.5, 16.0]
_dt_r = [-1.7, -0.9, -1.8, -1.4, -0.6, 0.0]
_larg_r = [22.6, 13.8, 27.2, 15.8, 14.9, 15.2]
_dits_r = []
_al_r = _coherence_points(list(zip(_pics_r, _dt_r, _larg_r)),
                          _dits_r.append)
controler("le troisieme calage reel, sur ses Dt retenus : aucune alerte",
          _al_r is None and bool(_dits_r)
          and "s'etend sur 1.8 h" in _dits_r[0]
          and "fenetre de 15.5 h" in _dits_r[0],
          (_al_r or (_dits_r[0].strip()[95:185] if _dits_r
                     else "rien dit"))[:90])
controler("mais la meme etendue sur des crues courtes alerterait",
          _coherence_points([(p, d, 8.0) for p, d in zip(_pics_r, _dt_r)],
                            lambda *a, **k: None) is not None)

# -----------------------------------------------------------------------
# TEST DE CARACTERISATION — la TRAJECTOIRE, et non plus des proprietes.
#
# POURQUOI IL EXISTE. Tous les controles ci-dessus verifient des BANDES :
# « volume a mieux que 5 % », « conforme », « tous les apports valides ».
# Une bande ne voit pas un decalage. Un remaniement de caler() peut
# deplacer tous les apports de 3 %, ou faire converger en trois essais au
# lieu de deux, sans qu'aucun d'eux ne bronche — 97 %, c'est toujours
# « mieux que 5 % ». Or caler() pese 699 lignes pour une complexite
# cyclomatique de 81, et le depot ne porte AUCUN modele HEC-RAS : le seul
# test qui touche un vrai modele exige le poste et une copie de 166 Mo.
#
# CE TEST NE DIT PAS CE QUE LE CODE DEVRAIT FAIRE. Il enregistre ce qu'il
# FAIT, dans un fichier de reference versionne, et refuse toute
# difference. C'est le filet a tendre AVANT de decouper caler().
#
# QUAND LE CHANGEMENT EST VOULU : « python calage.py --figer-reference »
# reecrit le fichier. Le refuser sans ce geste explicite est tout
# l'interet — une reference qui se met a jour toute seule ne prouve rien.
#
# CE QU'IL NE FIGE PAS, ET POURQUOI : ni les durees (horloge), ni
# l'historique par essai (il porte des mesures de temps). « nb_calculs »
# et le nombre d'essais par apport suffisent a epingler le chemin de
# recherche ; les hydrogrammes et les diagnostics epinglent les nombres.
# -----------------------------------------------------------------------
print("\n--- CARACTERISATION : la trajectoire, pas la bande ---")
import json
import platform

REFERENCE = (Path(calage.__file__).resolve().parent
             / "reference_calage_fictif.json")
RTOL_DEBIT = 1e-9      # debits, volumes, rapports : relatif
ATOL_HEURE = 1e-6      # decalages et bornes de fenetre : absolu, en heures

def _diag_fige(d):
    """Ce qu'on retient d'un Diagnostic : des nombres, et rien d'autre."""
    if d is None:
        return None
    return {
        "rapport_volume": float(d.rapport_volume),
        "rapport_pic": float(d.rapport_pic),
        "r": float(d.r),
        "decalage_h": float(d.decalage_h),
        "fenetre": (None if d.fenetre is None
                    else [float(d.fenetre[0]), float(d.fenetre[1])]),
        "rapport_volume_serie": (None if d.rapport_volume_serie is None
                                 else float(d.rapport_volume_serie)),
        "part_cible_jugee": (None if d.part_cible_jugee is None
                             else float(d.part_cible_jugee)),
        "converge": bool(d.converge),
        "alertes": list(d.alertes),
    }

trajectoire = {
    "_a_propos": (
        "Test de caracterisation de caler() sur ModeleFictif. NE PAS "
        "MODIFIER A LA MAIN : « python calage.py --figer-reference » le "
        "reecrit quand le changement de comportement est VOULU."),
    "_produit_par": {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "systeme": platform.system(),
    },
    "nb_calculs": int(resultat.nb_calculs),
    "conforme": bool(resultat.conforme),
    "motif": resultat.motif,
    "alertes_chaine": list(getattr(resultat, "alertes_chaine", []) or []),
    "apports": [{
        "nom_apport": a.nom_apport,
        "nom_section": a.nom_section,
        "valide": bool(a.valide),
        "essais": int(a.essais),
        "motif": a.motif,
        "facteur": float(a.facteur),
        # L'HYDROGRAMME INJECTE EST LE LIVRABLE du calage : c'est lui qui
        # part dans l'unsteady, et c'est donc lui qu'un remaniement ne
        # doit pas deplacer.
        "hydrogramme": [float(v) for v in
                        modele.formes[a.nom_apport]
                        * modele.facteurs[a.nom_apport]],
        "diagnostic": _diag_fige(a.diagnostic),
    } for a in resultat.apports],
    "diagnostics_finaux": [_diag_fige(d)
                           for d in resultat.diagnostics_finaux],
}

if "--figer-reference" in sys.argv:
    REFERENCE.write_text(
        json.dumps(trajectoire, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"   REFERENCE REECRITE : {REFERENCE.name} "
          f"({REFERENCE.stat().st_size / 1024:.1f} ko)")
    print("   Relire le diff avant de committer : il dit exactement ce "
          "que le changement a deplace.")
elif not REFERENCE.is_file():
    controler("fichier de reference present", False,
              f"{REFERENCE.name} absent — le creer par "
              f"« python calage.py --figer-reference »")
else:
    _attendu = json.loads(REFERENCE.read_text(encoding="utf-8"))
    _ecarts = []

    def _comparer(chemin, obtenu, attendu):
        """Compare deux valeurs de meme forme et accumule les ecarts."""
        if isinstance(attendu, dict):
            for cle in sorted(set(attendu) | set(obtenu or {})):
                if cle.startswith("_"):
                    continue
                if cle not in (obtenu or {}) or cle not in attendu:
                    _ecarts.append(f"{chemin}.{cle} : present d'un seul cote")
                    continue
                _comparer(f"{chemin}.{cle}", obtenu[cle], attendu[cle])
        elif isinstance(attendu, list) and not isinstance(obtenu, str):
            if len(obtenu) != len(attendu):
                _ecarts.append(f"{chemin} : {len(obtenu)} valeur(s) au "
                               f"lieu de {len(attendu)}")
                return
            for i, (o, a_) in enumerate(zip(obtenu, attendu)):
                _comparer(f"{chemin}[{i}]", o, a_)
        elif isinstance(attendu, bool) or isinstance(obtenu, bool):
            if bool(obtenu) != bool(attendu):
                _ecarts.append(f"{chemin} : {obtenu} au lieu de {attendu}")
        elif isinstance(attendu, (int, float)) and attendu is not None:
            # LES HEURES SE COMPARENT EN ABSOLU, LE RESTE EN RELATIF. Un
            # decalage nul ne peut pas se juger en relatif, et 1e-6 h
            # vaut 4 millisecondes : bien en deca du pas de recalage.
            if chemin.endswith("decalage_h") or ".fenetre[" in chemin:
                if abs(float(obtenu) - float(attendu)) > ATOL_HEURE:
                    _ecarts.append(f"{chemin} : {obtenu:+.9f} h au lieu de "
                                   f"{attendu:+.9f} h")
            elif not np.isclose(float(obtenu), float(attendu),
                                rtol=RTOL_DEBIT, atol=0.0,
                                equal_nan=True):
                _ecarts.append(f"{chemin} : {obtenu!r} au lieu de "
                               f"{attendu!r}")
        elif obtenu != attendu:
            _ecarts.append(f"{chemin} : {obtenu!r} au lieu de {attendu!r}")

    _comparer("", trajectoire, _attendu)
    _meme_socle = (_attendu.get("_produit_par", {}).get("numpy")
                   == np.__version__
                   and _attendu.get("_produit_par", {}).get("systeme")
                   == platform.system())
    controler(
        f"la trajectoire est celle de la reference "
        f"(rtol={RTOL_DEBIT:g} sur les debits, atol={ATOL_HEURE:g} h "
        f"sur les decalages)",
        not _ecarts,
        "identique" if not _ecarts else
        f"{len(_ecarts)} ecart(s), dont : " + " | ".join(_ecarts[:3]))
    if _ecarts and not _meme_socle:
        # UN ECART N'EST PAS FORCEMENT UNE REGRESSION. La reference porte
        # le socle qui l'a produite : le dire evite de chercher dans le
        # code une derive qui vient de la bibliotheque.
        print(f"   NOTE : reference produite sous numpy "
              f"{_attendu.get('_produit_par', {}).get('numpy')} / "
              f"{_attendu.get('_produit_par', {}).get('systeme')}, ici "
              f"numpy {np.__version__} / {platform.system()}. Un ecart au "
              f"dernier chiffre significatif peut venir de la, pas du "
              f"code — relire les ecarts avant de conclure.")
    if _ecarts:
        print(f"   Les {len(_ecarts)} ecart(s), en entier :")
        for _e in _ecarts[:40]:
            print(f"      {_e}")
        if len(_ecarts) > 40:
            print(f"      … et {len(_ecarts) - 40} autre(s)")
        print("   Si le changement est VOULU : "
              "« python calage.py --figer-reference », puis relire le diff.")

print()
if echecs:
    print(f"   {len(echecs)} CONTROLE(S) EN ECHEC : {echecs}")
    raise SystemExit(1)
print("   Tous les controles passent.")
print("=" * 74)
