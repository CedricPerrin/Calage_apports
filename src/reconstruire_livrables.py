# -*- coding: utf-8 -*-
"""
Reconstruit les livrables d'un calage TERMINE dont le rapport s'est perdu.

POURQUOI CE MODULE EXISTE. Un calage de 46 heures, douze apports sur douze
conformes, n'a rendu ni classeur, ni note de synthese, ni figure des apports :
le rapport a leve une IndexError avant d'ecrire (corrigee depuis, voir
calage.produire_livrables_finaux). Tout ce que le rapport decrit etait pourtant
sur le disque — le plan final avec ses resultats, l'unsteady avec les apports
retenus, le classeur de saisie avec les cibles, le journal avec les fenetres
jugees. Il ne manquait que l'assemblage. C'est la seconde fois qu'un calage
perd ses livrables apres coup ; recalculer des heures pour refaire a
l'identique ce qui est deja la serait absurde.

CE QU'IL FAIT, ET CE QU'IL NE FAIT PAS. Il RELIT : la section calculee de
chaque apport dans le HDF du plan final, l'hydrogramme retenu de chaque apport
dans l'unsteady de ce plan, les cibles dans le classeur, les fenetres jugees
et les essais dans le journal et le suivi. Il rejoue diagnostiquer() avec les
MEMES entrees que le calage — meme fenetre, memes tolerances — et appelle
produire_livrables_finaux() exactement comme le fait pont_hecras a la fin d'un
calage. Il n'ECRIT RIEN dans le modele : le pilote est une doublure en lecture
seule, et le HDF est ouvert en « r ».

CE QU'IL NE PEUT PAS RETROUVER. Le « Volume retenu / 1re estimation » du
tableau des apports vient de la boucle, pas du modele : il est rendu vide.
Tout le reste — verdicts, series, hydrogrammes, journal des essais, profil en
long — est reconstruit a l'identique, et la fidelite se VERIFIE : le script
compare, apport par apport, les volumes, pointes et formes qu'il recalcule a
ceux que le suivi (avancement.json) a consignes pendant le calage.

Usage :
  python reconstruire_livrables.py --template <donnees_calage.xlsx>
      --journal <calage_....log> --plan 17
      [--dossier-shp <dossier ou vivent les .shp, s'ils ont demenage>]
      [--sortie <dossier resultats_finaux>] [--suivi <dossier suivi>]
"""
import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from calage import (Configuration, ResultatApport, ResultatCalage,  # noqa: E402
                    produire_livrables_finaux)
from criteres import diagnostiquer                              # noqa: E402
from pilote_hecras import (cartographier_hydrogrammes,          # noqa: E402
                           lire_hydrogramme_unsteady)
from pont_hecras import (_cibles_depuis_classeur,               # noqa: E402
                         _profil_pour_livrables, lire_serie_hdf)


class ModeleFige:
    """
    Doublure EN LECTURE SEULE d'un PiloteHecRas dont le calage est termine.

    produire_livrables_finaux() n'appelle le modele que pour forme_apport() ;
    _profil_pour_livrables() ne lit que hdf_resultats et nom_zone_2d. Tout le
    reste du pilote — cloner, titrer, calculer — n'a rien a faire ici, et
    l'instancier obligerait a passer par preparer(), qui ECRIT dans le projet.
    """

    def __init__(self, dossier, nom_projet, numero_plan, nom_zone_2d):
        self.dossier = Path(dossier)
        self.nom_projet = nom_projet
        self.nom_zone_2d = nom_zone_2d
        self.hdf_resultats = self.dossier / f"{nom_projet}.p{numero_plan}.hdf"
        plan = self.dossier / f"{nom_projet}.p{numero_plan}"
        flot = re.search(r"^Flow File=(u\d+)", plan.read_text(encoding="utf-8",
                                                               errors="replace"),
                         re.M)
        if not flot:
            raise ValueError(f"{plan.name} ne declare pas de « Flow File= ».")
        self.fichier_unsteady = self.dossier / f"{nom_projet}.{flot.group(1)}"
        self.carte = cartographier_hydrogrammes(self.fichier_unsteady,
                                                nom_zone_2d)

    def forme_apport(self, nom_apport):
        # MEME LECTURE QUE PiloteHecRas.forme_apport : un axe PAR apport, au
        # pas de son bloc. C'est l'heterogeneite de ces axes qui avait fait
        # perdre le rapport d'origine.
        info = self.carte[nom_apport]
        valeurs = lire_hydrogramme_unsteady(self.fichier_unsteady,
                                            info["debut"], info["fin"])
        return np.arange(len(valeurs)) * info["intervalle_h"], valeurs

    def lire_section(self, nom_section):
        serie = lire_serie_hdf(self.hdf_resultats, nom_section,
                               groupe="Reference Lines")
        return (serie["temps"].to_numpy(dtype=float),
                serie["debit_m3s"].to_numpy(dtype=float))


def fenetres_et_decalages_du_journal(chemin_journal):
    """
    Fenetres jugees et decalages retenus, dans l'ordre des apports.

    LE JOURNAL EST LA SEULE TRACE DE LA FENETRE que le calage a employee. La
    recalculer aujourd'hui donnerait une AUTRE fenetre — la chaine a change
    depuis — et le rapport reconstruit ne decrirait plus le calage qui a
    tourne, mais celui qui aurait tourne. On relit, on ne refait pas.
    """
    texte = Path(chemin_journal).read_text(encoding="utf-8", errors="replace")
    fenetres = [(float(a), float(b)) for a, b in re.findall(
        r"hydrogramme principal ([\d.]+) h -> ([\d.]+) h", texte)]
    decalages = [float(d) for d in re.findall(
        r"decalage retenu ([+-][\d.]+) h", texte)]
    return fenetres, decalages


def historiques_du_suivi(chemin_iterations, apports):
    """
    Journal des essais, relu dans iterations.xlsx : un tableau par apport,
    en-tete en ligne 4 — Essai, Volume, Pointe, Forme, decalages. Les
    classeurs anterieurs au 07/09/2026 portent aussi une colonne KGE : elle
    est ignoree, comme toute colonne que l'on ne cherche pas.

    Les cles rendues sont celles que caler() consigne (essai, volume, pic,
    r) ; « facteur » n'est pas retrouvable et n'est pas invente.
    """
    x = pd.ExcelFile(chemin_iterations)
    historiques = {}
    for nom in apports:
        if nom not in x.sheet_names:
            historiques[nom] = []
            continue
        f = x.parse(nom, header=None)
        entetes = [str(v) for v in f.iloc[3].tolist()]
        col = {e: i for i, e in enumerate(entetes)}
        lignes = []
        for i in range(4, len(f)):
            essai = f.iloc[i, col["Essai"]]
            if pd.isna(essai) or not str(essai).strip().isdigit():
                break
            lignes.append({
                "essai": int(essai),
                "volume": float(f.iloc[i, col["Volume (% cible)"]]) / 100.0,
                "pic": float(f.iloc[i, col["Pointe (% cible)"]]) / 100.0,
                "r": float(f.iloc[i, col["Forme (%)"]]) / 100.0})
        historiques[nom] = lignes
    return historiques


def classeur_remappe(chemin_template, dossier_shp, dossier_sortie, destination):
    """
    Copie du classeur dont les chemins de shapefiles et de sortie pointent la
    ou les fichiers vivent AUJOURD'HUI. L'original n'est jamais touche.
    """
    feuilles = pd.read_excel(chemin_template, sheet_name=None)
    par = feuilles["Parametres"]
    for cle, nom in (("Fichier_SHP_Sections", "sections_controle.shp"),
                     ("Fichier_SHP_Apports", "lignes_injection.shp"),
                     ("Fichier_SHP_Axe", "axe_hydraulique.shp")):
        if dossier_shp is not None:
            par.loc[par["Parametre"] == cle, "Valeur"] = str(Path(dossier_shp) / nom)
    par.loc[par["Parametre"] == "Dossier_sortie", "Valeur"] = str(dossier_sortie.parent)
    par.loc[par["Parametre"] == "Sous_dossier_resultats", "Valeur"] = dossier_sortie.name
    with pd.ExcelWriter(destination, engine="openpyxl") as w:
        for nom, df in feuilles.items():
            df.to_excel(w, sheet_name=nom, index=False)
    return destination


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--template", required=True)
    ap.add_argument("--journal", required=True)
    ap.add_argument("--plan", required=True, help="numero du plan final, ex. 17")
    ap.add_argument("--dossier-shp", default=None)
    ap.add_argument("--sortie", default=None)
    ap.add_argument("--suivi", default=None)
    args = ap.parse_args()

    template = Path(args.template)
    par = pd.read_excel(template, sheet_name="Parametres")
    valeurs = dict(zip(par["Parametre"], par["Valeur"]))
    dossier_modele = Path(str(valeurs["Dossier_projet_HECRAS"]))
    nom_projet = str(valeurs["Nom_projet"])
    zone = str(valeurs.get("Nom_zone_2D") or "") or None
    sortie = Path(args.sortie) if args.sortie else template.parent / "resultats_finaux"
    suivi = Path(args.suivi) if args.suivi else template.parent / "suivi"

    def nombre(cle, defaut):
        v = valeurs.get(cle)
        try:
            return float(v) if v is not None and not pd.isna(v) else defaut
        except (TypeError, ValueError):
            return defaut

    config = Configuration(
        nb_max_essais=int(nombre("Nb_max_iterations_par_apport", 6)),
        tolerance_volume=nombre("Tolerance_volume_pct", 5.0) / 100.0,
        tolerance_pic=nombre("Tolerance_pic_pct", 2.0) / 100.0)

    apports, sections, cibles, manquantes = _cibles_depuis_classeur(template)
    if manquantes:
        raise SystemExit(f"cibles inexploitables pour {manquantes}")
    fenetres, decalages = fenetres_et_decalages_du_journal(args.journal)
    if len(fenetres) != len(apports):
        raise SystemExit(
            f"{len(fenetres)} fenetre(s) au journal pour {len(apports)} "
            f"apport(s) : le journal ne decrit pas ce classeur.")
    historiques = historiques_du_suivi(suivi / "iterations.xlsx", apports)
    avancement = json.loads((suivi / "avancement.json").read_text(encoding="utf-8"))
    consigne = {a["apport"]: a for a in avancement["apports"]}

    modele = ModeleFige(dossier_modele, nom_projet, str(args.plan).zfill(2), zone)
    print(f"Modele    : {modele.hdf_resultats.name} ({modele.hdf_resultats.stat().st_size // 1_000_000} Mo), "
          f"{modele.fichier_unsteady.name}, zone « {zone} »")
    print(f"Livrables : {sortie}")

    resultat = ResultatCalage(config=config,
                              duree_s=float(avancement.get("ecoule_s") or 0.0))
    print(f"\n{'apport':8s}{'volume':>9s}{'pointe':>9s}{'forme':>9s}{'dt':>7s}"
          f"   {'suivi (vol/pic/forme)':>24s}")
    for i, (apport, section, (t_c, q_c)) in enumerate(zip(apports, sections, cibles)):
        t_s, q_s = modele.lire_section(section)
        d = diagnostiquer(t_c, q_c, t_s, q_s,
                          tolerance_volume=config.tolerance_volume,
                          tolerance_pic=config.tolerance_pic,
                          r_min=config.r_min, fenetre=fenetres[i])
        hist = historiques.get(apport, [])
        resultat.apports.append(ResultatApport(
            nom_apport=apport, nom_section=section, valide=bool(d.converge),
            facteur=float("nan"), diagnostic=d, essais=len(hist),
            duree_s=float(consigne.get(apport, {}).get("duree_s") or 0.0),
            motif="" if d.converge else "concordance non atteinte a la relecture",
            historique=hist, fenetre_principale=fenetres[i]))
        resultat.diagnostics_finaux.append(d)
        resultat.series_finales.append((t_c, q_c, t_s, q_s))
        resultat.nb_calculs += len(hist)
        c = consigne.get(apport, {})
        print(f"{apport:8s}{100 * d.rapport_volume:8.1f} %{100 * d.rapport_pic:8.1f} %"
              f"{100 * d.r:8.1f} %{d.decalage_h:+6.1f}h   "
              f"{c.get('volume_pct', float('nan')):6.1f} / {c.get('pic_pct', float('nan')):5.1f} "
              f"/ {c.get('forme_pct', float('nan')):5.1f}")
    resultat.nb_calculs += 1                                  # le calcul de reference
    resultat.conforme = all(d.converge for d in resultat.diagnostics_finaux)
    print(f"\nVerdict a la relecture : {'CONFORME' if resultat.conforme else 'NON conforme'} "
          f"— suivi : {'conforme' if avancement.get('conforme') else 'non conforme'}")

    # LES FICHIERS DEJA LA SONT MIS DE COTE, pas ecrases : ce sont les seuls
    # temoins de ce que le rapport d'origine avait eu le temps d'ecrire.
    sortie.mkdir(parents=True, exist_ok=True)
    existants = [f for f in sortie.iterdir() if f.is_file()]
    if existants:
        abri = sortie / f"_avant_reconstruction_{datetime.now():%Y%m%d_%H%M}"
        abri.mkdir(exist_ok=True)
        for f in existants:
            shutil.move(str(f), str(abri / f.name))
        print(f"{len(existants)} fichier(s) existant(s) mis de cote dans {abri.name}/")

    copie = sortie / "_donnees_calage_remappe.xlsx"
    classeur_remappe(template, args.dossier_shp, sortie, copie)
    profil, pk_sections, pk_apports = _profil_pour_livrables(modele, copie, resultat)
    rapport = produire_livrables_finaux(resultat, modele, sortie, profil=profil,
                                        pk_sections=pk_sections,
                                        pk_apports=pk_apports)
    copie.unlink(missing_ok=True)
    print(f"\n{len([f for f in rapport['fichiers'] if not str(f).startswith('AVERTISSEMENT')])} "
          f"fichier(s) produit(s) ; conforme={rapport['conforme']}")
    for f in rapport["fichiers"]:
        if str(f).startswith(("AVERTISSEMENT", "apports retenus non", "profil en long non")):
            print("   ", f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
