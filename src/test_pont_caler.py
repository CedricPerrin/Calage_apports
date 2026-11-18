"""
Caracterisation de commande_caler (src/pont_hecras.py), la sous-commande qui
lance un calage reel.

CE TEST NE DIT PAS CE QUE LA COMMANDE DEVRAIT FAIRE. Il enregistre ce
qu'elle FAIT — la Configuration construite, les arguments passes au pilote, a
caler(), au suivi et aux livrables, l'ordre de ces appels, le JSON rendu, le
code de retour, chaque ligne du journal, l'exception levee le cas echeant, les
fichiers presents a la fin — dans une reference versionnee, et refuse toute
difference. C'est le filet tendu AVANT de decouper commande_caler en phases
(chantier du 10/11/2026) : le decoupage doit le laisser vert sans qu'on y
touche.

    python -m pytest src/test_pont_caler.py -q

QUAND UN CHANGEMENT EST VOULU : « python src/test_pont_caler.py
--figer-reference » reecrit reference_pont_caler.json. Le refuser sans ce
geste explicite est tout l'interet.

CE QUI EST DOUBLE, ET POURQUOI. Un calage ne peut pas tourner ici (pas de
HEC-RAS sous Linux) et dure des heures. Sont donc remplaces, LA OU
commande_caler VA LES CHERCHER — ses imports sont locaux a la fonction, c'est
donc sur les modules pilote_hecras, calage et suivi qu'on les pose :
  - pilote_hecras.PiloteHecRas : enregistre ses arguments, rend ce que le cas
    choisit pour nettoyer_reliquats() et elaguer_etapes() ;
  - pilote_hecras.symbole_decimal : le registre Windows, valeur choisie ;
  - calage.caler et calage.produire_livrables_finaux : enregistrent, rendent
    un ResultatCalage fabrique a la main (rien de l'interieur de caler()) ;
  - suivi.Suivi : enregistre son titre, ses tolerances et le verdict.
Sont seulement ESPIONNES (la vraie fonction tourne) : plan_par_titre et
plans_par_titre (sur de vrais .pNN fabriques), _appliquer_pentes et
_profil_pour_livrables. Calage.Configuration, titre_etape, etape_apport,
parametres.lire et _cibles_depuis_classeur sont les vrais.

NEUTRALISE : le dossier temporaire (« <TMP> »), l'horodatage du journal
(« <HORODATE> »), l'interpreteur (« <PYTHON> »).
"""
import dataclasses
import json
import re
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pandas as pd
import pytest

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

import calage  # noqa: E402
import parametres  # noqa: E402
import pilote_hecras  # noqa: E402
import pont_hecras  # noqa: E402
import suivi  # noqa: E402

REFERENCE = SRC / "reference_pont_caler.json"

# ---------------------------------------------------------------------------
# Fabrication des entrees
# ---------------------------------------------------------------------------

COL_APPORT = "Nom_Apport (BC line)"
COL_SECTION = "Nom_Section (reference line)"
COL_CIBLE = "Nom_Cible"

CORR = {"Ordre": [1, 2, 3],
        COL_APPORT: ["A1", "A2", "A3"],
        COL_SECTION: ["S1", "S2", "S3"],
        COL_CIBLE: ["C1", "C2", "C3"]}

_HYDRO = [0.0, 1.0, 3.0, 6.0, 10.0, 8.0, 5.0, 3.0, 2.0, 1.0, 0.5, 0.2]
# Pas HORAIRE : chaque cible est ramenee a 6 min, avec une ligne au journal.
CIBLES = {"Temps_h": [float(t) for t in range(12)],
          "C1": list(_HYDRO),
          "C2": [2 * q for q in _HYDRO],
          "C3": [3 * q for q in _HYDRO]}

# Le dossier projet est remplace par le vrai chemin a l'execution.
PROJET = "<PROJET>"
PARAMS = {"Dossier_projet_HECRAS": PROJET, "Nom_projet": "Essai",
          "Nom_zone_2D": "Zone2D", "Plan_reference": "p01",
          "Version_HECRAS": "6.6"}

# Plans du projet fabrique : numero -> « Plan Title ».
PLANS = {"01": "Reference", "02": "Autre"}

_SUPPRIMER = object()


def _avec(base, **changes):
    d = dict(base)
    for k, v in changes.items():
        if v is _SUPPRIMER:
            d.pop(k, None)
        else:
            d[k] = v
    return d


def _ecrire_entrees(dossier, sc):
    """Classeur, JSON de parametres et projet HEC-RAS du scenario."""
    projet = dossier / "projet"
    projet.mkdir()
    for num, titre in sc["plans"].items():
        (projet / f"Essai.p{num}").write_text(
            f"Plan Title={titre}\nShort Identifier={titre}\nGeom File=g01\n"
            f"Flow File=u01\n", encoding="utf-8")

    def remplacer(valeurs):
        return {k: (str(projet) if v == PROJET else v)
                for k, v in valeurs.items()}

    chemin = dossier / "donnees.xlsx"
    if sc["classeur"]:
        with pd.ExcelWriter(chemin, engine="openpyxl") as w:
            pd.DataFrame(sc["corr"]).to_excel(w, sheet_name="Correspondance",
                                              index=False)
            pd.DataFrame(sc["cibles"]).to_excel(w, sheet_name="Cibles",
                                                index=False)
            if sc["feuille_parametres"] is not None:
                valeurs = remplacer(sc["feuille_parametres"])
                pd.DataFrame({"Parametre": list(valeurs),
                              "Valeur": list(valeurs.values())}).to_excel(
                    w, sheet_name="Parametres", index=False)
    if sc["params"] is not None:
        parametres.chemin(chemin).write_text(
            json.dumps(remplacer(sc["params"]), ensure_ascii=False),
            encoding="utf-8")
    return chemin


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------

def _resultat(sc):
    """ResultatCalage fabrique a la main, selon le cas."""
    r = sc["resultat"]
    apports = [calage.ResultatApport(nom_apport=a, nom_section=s, valide=v,
                                     facteur=1.0)
               for a, s, v in r["apports"]]
    return calage.ResultatCalage(
        apports=apports,
        diagnostics_finaux=[object()] * r["nb_diagnostics"],
        duree_s=r["duree_s"], nb_calculs=r["nb_calculs"],
        conforme=r["conforme"], motif=r["motif"],
        alertes_chaine=list(r["alertes_chaine"]))


def _cible(c):
    t, q = (np.asarray(x, dtype=float) for x in c)
    return {"n": int(len(t)), "t0": round(float(t[0]), 6),
            "tf": round(float(t[-1]), 6), "qmax": round(float(q.max()), 6),
            "somme_q": round(float(q.sum()), 6)}


def _py(v):
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, (list, tuple)):
        return [_py(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _py(x) for k, x in v.items()}
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return repr(v)


class _Banc:
    """Les doubles d'un cas, et ce qu'ils ont vu, dans l'ordre."""

    def __init__(self, sc):
        self.sc = sc
        self.appels = []
        self.pilote = None
        self.suivi = None
        self.resultat = None

    # --- pilote ------------------------------------------------------------
    def fabrique_pilote(self):
        banc = self

        class FauxPilote:
            def __init__(self, **kwargs):
                banc.appels.append(["PiloteHecRas", _py(kwargs)])
                if banc.sc["exception_pilote"]:
                    raise RuntimeError(banc.sc["exception_pilote"])
                banc.pilote = self
                self.dossier = Path(kwargs["dossier_projet"])
                self.nom_projet = kwargs["nom_projet"]
                self.nom_zone_2d = kwargs["nom_zone_2d"]
                self.plan_travail = "09"
                self.hdf_resultats = None
                self.pentes = {}
                self.plan_a_remplacer = None

            def nettoyer_reliquats(self):
                banc.appels.append(["pilote.nettoyer_reliquats"])
                m = banc.sc["menage"]
                if isinstance(m, str):
                    raise OSError(m)
                return dict(m)

            def elaguer_etapes(self, *args, **kwargs):
                banc.appels.append(["pilote.elaguer_etapes", _py(list(args)),
                                    _py(kwargs)])
                e = banc.sc["elagage"]
                if isinstance(e, str):
                    raise OSError(e)
                return dict(e)

        return FauxPilote

    # --- suivi -------------------------------------------------------------
    def fabrique_suivi(self):
        banc = self

        class FauxSuivi:
            def __init__(self, dossier, noms_apports, noms_sections, **kwargs):
                banc.appels.append(["Suivi", str(dossier), list(noms_apports),
                                    list(noms_sections), _py(kwargs)])
                banc.suivi = self

            def conclure(self, *args, **kwargs):
                banc.appels.append(["suivi.conclure", _py(list(args)),
                                    _py(kwargs)])
                if banc.sc["exception_conclure"]:
                    raise RuntimeError(banc.sc["exception_conclure"])

        return FauxSuivi

    # --- calage --------------------------------------------------------------
    def caler(self, modele, apports, sections, cibles, config=None, suivi=None,
              journal=None, etape_reference=None, **autres):
        self.appels.append(["caler", {
            "modele_est_le_pilote": modele is self.pilote and modele is not None,
            "apports": list(apports), "sections": list(sections),
            "cibles": [_cible(c) for c in cibles],
            "config_type": type(config).__name__,
            "config": _py(dataclasses.asdict(config)),
            "suivi_est_le_suivi": suivi is self.suivi and suivi is not None,
            "journal": getattr(journal, "__name__", repr(journal)),
            "etape_reference": etape_reference,
            "autres": _py(autres),
            # Etat du pilote AU MOMENT du calage : pentes deposees, plan
            # source a remplacer.
            "pilote_pentes": _py(getattr(modele, "pentes", None)),
            "pilote_plan_a_remplacer": getattr(modele, "plan_a_remplacer",
                                               None),
        }])
        if journal is not None:
            journal("   (ligne de caler, par le journal recu)")
        if self.sc["exception_caler"]:
            raise RuntimeError(self.sc["exception_caler"])
        self.resultat = _resultat(self.sc)
        return self.resultat

    def produire_livrables_finaux(self, resultat, modele, dossier_sortie,
                                  **kwargs):
        self.appels.append(["produire_livrables_finaux", {
            "resultat_est_le_resultat": resultat is self.resultat,
            "modele_est_le_pilote": modele is self.pilote,
            "dossier_sortie": str(dossier_sortie), "kwargs": _py(kwargs)}])
        if self.sc["exception_livrables"]:
            raise RuntimeError(self.sc["exception_livrables"])
        return {"rapport": "fictif"}

    def symbole_decimal(self):
        self.appels.append(["symbole_decimal"])
        return self.sc["decimal"]

    def espion(self, nom, vraie):
        def f(*args, **kwargs):
            rendu = vraie(*args, **kwargs)
            self.appels.append([nom, _py(list(args[:3]) if nom.startswith("plan")
                                         else []), _py(rendu)
                                if nom.startswith("plan") else None])
            return rendu
        return f


# ---------------------------------------------------------------------------
# Execution d'un cas
# ---------------------------------------------------------------------------

_HORODATE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d ")


def _neutraliser(objet, dossier):
    variantes = sorted({str(dossier), str(Path(dossier).resolve())},
                       key=len, reverse=True)

    def nettoyer(o):
        if isinstance(o, str):
            # Separateur ramene a « / », y compris double dans un repr :
            # meme reference sous Windows et sous Linux.
            o = o.replace("\\\\", "/").replace("\\", "/")
            for v in variantes:
                o = o.replace(v.replace("\\", "/"), "<TMP>")
            return o.replace(sys.executable.replace("\\", "/"), "<PYTHON>")
        if isinstance(o, list):
            return [nettoyer(x) for x in o]
        if isinstance(o, dict):
            return {k: nettoyer(x) for k, x in o.items()}
        return o

    return nettoyer(objet)


def jouer(sc, dossier, capsys):
    """Joue commande_caler sur le scenario, rend tout ce qu'on en observe."""
    dossier = Path(dossier)
    chemin = _ecrire_entrees(dossier, sc)
    avant = {p for p in dossier.rglob("*")}
    banc = _Banc(sc)
    with ExitStack() as pile:
        p = pile.enter_context
        p(mock.patch.object(pilote_hecras, "PiloteHecRas", banc.fabrique_pilote()))
        p(mock.patch.object(pilote_hecras, "symbole_decimal", banc.symbole_decimal))
        p(mock.patch.object(pilote_hecras, "hecras_ouvert",
                            lambda: sc["hecras_ouvert"]))
        p(mock.patch.object(pilote_hecras, "plan_par_titre",
                            banc.espion("plan_par_titre",
                                        pilote_hecras.plan_par_titre)))
        p(mock.patch.object(pilote_hecras, "plans_par_titre",
                            banc.espion("plans_par_titre",
                                        pilote_hecras.plans_par_titre)))
        p(mock.patch.object(calage, "caler", banc.caler))
        p(mock.patch.object(calage, "produire_livrables_finaux",
                            banc.produire_livrables_finaux))
        p(mock.patch.object(suivi, "Suivi", banc.fabrique_suivi()))
        p(mock.patch.object(pont_hecras, "_appliquer_pentes",
                            banc.espion("_appliquer_pentes",
                                        pont_hecras._appliquer_pentes)))
        p(mock.patch.object(pont_hecras, "_profil_pour_livrables",
                            banc.espion("_profil_pour_livrables",
                                        pont_hecras._profil_pour_livrables)))
        capsys.readouterr()
        code, exception = None, None
        try:
            code = pont_hecras.commande_caler(
                SimpleNamespace(template=str(chemin)))
        except Exception as e:  # noqa: BLE001 - l'exception fait partie du contrat
            exception = {"type": type(e).__name__, "message": str(e)}
        sortie = capsys.readouterr()
    lignes = sortie.out.splitlines()
    reponse = None
    if code is not None and lignes:
        reponse = json.loads(lignes.pop())
    journal = [_HORODATE.sub("<HORODATE> ", ligne) for ligne in lignes]
    produits = sorted(str(f.relative_to(dossier)) for f in dossier.rglob("*")
                      if f not in avant)
    rendu = {"code": code, "exception": exception, "reponse": reponse,
             "journal": journal, "stderr": sortie.err.splitlines(),
             "appels": banc.appels, "fichiers_produits": produits,
             "pilote_final": (None if banc.pilote is None else {
                 "pentes": _py(banc.pilote.pentes),
                 "plan_a_remplacer": banc.pilote.plan_a_remplacer})}
    return _neutraliser(json.loads(json.dumps(rendu, ensure_ascii=False)),
                        dossier)


# ---------------------------------------------------------------------------
# Les cas
# ---------------------------------------------------------------------------

RESULTAT_CONFORME = {
    "apports": [("A1", "S1", True), ("A2", "S2", True), ("A3", "S3", True)],
    "nb_diagnostics": 3, "duree_s": 3600.04, "nb_calculs": 9,
    "conforme": True, "motif": "", "alertes_chaine": ["alerte d'ensemble"]}

RESULTAT_NON_CONFORME = {
    "apports": [("A1", "S1", True), ("A2", "S2", False)],
    "nb_diagnostics": 0, "duree_s": 12.06, "nb_calculs": 4,
    "conforme": False, "motif": "A2 non cale", "alertes_chaine": []}

MENAGE = {"reliquats": ["Essai.p05", "Essai.u05"], "conserve": "p09",
          "etapes": ["sans_apport", "Apport_A1", "avec_apports"]}

ELAGAGE = {"supprimes": ["p03", "p04"], "final": "avec_apports"}

BASE = {"params": PARAMS, "feuille_parametres": None, "classeur": True,
        "corr": CORR, "cibles": CIBLES, "plans": PLANS, "decimal": None,
        "hecras_ouvert": False, "resultat": RESULTAT_CONFORME,
        "menage": MENAGE, "elagage": ELAGAGE, "exception_pilote": None,
        "exception_caler": None, "exception_livrables": None,
        "exception_conclure": None}

CAS = {}


def cas(nom, **changes):
    CAS[nom] = _avec(BASE, **changes)


def params(**changes):
    return _avec(PARAMS, **changes)


cas("nominal")
cas("decimal_point", decimal=".")

# --- chaque parametre a une valeur non defaut -------------------------------
_NON_DEFAUT = {
    "Prefixe_scenario": "Q100",
    "Plan_reference": "p02",
    "Plan_reference_nombre": 2,
    "Mode_selection_modele": "override",
    "Mode_selection_modele_majuscules": "OVERRIDE",
    "Geometrie_reference": "g03",
    "Unsteady_reference": "u04",
    "Simulation_debut": "01JAN2020 0000",
    "Simulation_fin": "02JAN2020 0000",
    "Intervalle_calcul": "10SEC",
    "Intervalle_sortie": "5MIN",
    "Intervalle_instantane": "1HOUR",
    "Intervalle_mapping": "30MIN",
    "Version_HECRAS": "7.0.1",
    "Nom_clone_geometrie": "Clone geo",
    "Coeurs_par_calcul": 4,
    "Nb_max_iterations_par_apport": 3,
    "Tolerance_volume_pct": 7.5,
    "Tolerance_pic_pct": 3,
    "Bilan_masse_max_pct": 1.5,
    "Fenetre_seuil_bas_pct": 1,
    "Fenetre_seuil_haut_pct": 95,
    "Fenetre_t0_h": 2,
    "Fenetre_tf_h": 9.5,
    "Fenetre_active": "non",
    "Dossier_sortie": "<SORTIE>",
    "Sous_dossier_suivi": "mon_suivi",
    "Sous_dossier_resultats": "mes_resultats",
    "Elaguer_plans_etape": "oui",
    "Remplacer_plan_source": "oui",
    "Premier_apport": "A2",
}
for _cle, _val in _NON_DEFAUT.items():
    _p = _cle.split("_nombre")[0].split("_majuscules")[0]
    cas(f"parametre/{_cle}", params=params(**{_p: _val}))

cas("parametre/Nom_zone_2D_vide", params=params(Nom_zone_2D=""))
cas("parametre/Mode_override_avec_references",
    params=params(Mode_selection_modele="override", Geometrie_reference="g03",
                  Unsteady_reference="u04"))
cas("parametre/fenetre_complete",
    params=params(Simulation_debut="01JAN2020 0000",
                  Simulation_fin="02JAN2020 0000", Intervalle_calcul="10SEC",
                  Intervalle_sortie="5MIN", Intervalle_instantane="1HOUR",
                  Intervalle_mapping="30MIN"))
cas("parametre/Fenetre_active_oui", params=params(Fenetre_active="oui"))
cas("parametre/Fenetre_active_bizarre", params=params(Fenetre_active="peut-etre"))
# Case « Accepter un objectif degrade » decochee (18/11/2026) : aucun cran.
cas("parametre/Degrader_objectif_non", params=params(Degrader_objectif="non"))
cas("parametre/Degrader_objectif_oui", params=params(Degrader_objectif="oui"))
cas("parametre/nombres_illisibles",
    params=params(Nb_max_iterations_par_apport="six", Tolerance_volume_pct=None,
                  Tolerance_pic_pct="", Fenetre_t0_h="x",
                  Coeurs_par_calcul="beaucoup"))
cas("parametre/nombres_en_texte",
    params=params(Nb_max_iterations_par_apport="4", Tolerance_pic_pct="2.5",
                  Coeurs_par_calcul="2.7"))
cas("parametre/textes_avec_espaces",
    params=params(Nom_projet="  Essai  ", Prefixe_scenario="  Q10  ",
                  Plan_reference=" p01 "))
cas("parametre/tous_absents", params={})
cas("parametre/json_avec_nulls",
    params=params(Plan_reference=None, Version_HECRAS=None, Nom_zone_2D=None,
                  Dossier_sortie=None, Sous_dossier_suivi=None))

# --- classeur ancien : feuille « Parametres », pas de JSON --------------------
cas("classeur_ancien_feuille_parametres", params=None,
    feuille_parametres=params(Prefixe_scenario="Q50", Coeurs_par_calcul=2,
                              Tolerance_volume_pct=4))
cas("classeur_ancien_json_prioritaire",
    params=params(Prefixe_scenario="JSON"),
    feuille_parametres=params(Prefixe_scenario="FEUILLE"))

# --- reprise ---------------------------------------------------------------
cas("reprise/plan_trouve", params=params(Premier_apport="A2"),
    plans={"01": "Reference", "04": "Apport_A1"},
    resultat=_avec(RESULTAT_CONFORME,
                   apports=[("A2", "S2", True), ("A3", "S3", True)]))
cas("reprise/par_section", params=params(Premier_apport="S3"),
    plans={"01": "Reference", "05": "Apport_A2"})
cas("reprise/plan_absent", params=params(Premier_apport="A3"))
cas("reprise/avec_prefixe",
    params=params(Premier_apport="A2", Prefixe_scenario="Q100"),
    plans={"01": "Reference", "06": "Q100-A1"})
cas("reprise/premier_apport_est_le_premier", params=params(Premier_apport="A1"))
cas("reprise/premier_apport_inconnu", params=params(Premier_apport="A9"))
cas("reprise/plan_trouve_source_homonyme_accepte",
    params=params(Premier_apport="A2", Prefixe_scenario="Q100",
                  Remplacer_plan_source="oui"),
    plans={"01": "Q100", "06": "Q100-A1"})
cas("reprise/elagage_tous_apports",
    params=params(Premier_apport="A2", Elaguer_plans_etape="oui"),
    plans={"01": "Reference", "04": "Apport_A1"})

# --- plan source et plan final -----------------------------------------------
cas("plan_source/porte_titre_final_accepte",
    params=params(Prefixe_scenario="Q100", Remplacer_plan_source="oui"),
    plans={"01": "Q100"})
cas("plan_source/porte_titre_final_accepte_true",
    params=params(Prefixe_scenario="Q100", Remplacer_plan_source="TRUE"),
    plans={"01": "Q100"})
cas("plan_source/porte_titre_final_accepte_1",
    params=params(Prefixe_scenario="Q100", Remplacer_plan_source="1"),
    plans={"01": "Q100"})
cas("plan_source/porte_titre_final_refuse_non",
    params=params(Prefixe_scenario="Q100", Remplacer_plan_source="non"),
    plans={"01": "Q100"})
cas("plan_source/porte_titre_final_param_absent",
    params=params(Prefixe_scenario="Q100"), plans={"01": "Q100"})
cas("plan_source/sans_prefixe_porte_avec_apports",
    params=params(Remplacer_plan_source="oui"), plans={"01": "avec_apports"})
cas("plan_source/ne_porte_pas_titre_oui",
    params=params(Prefixe_scenario="Q100", Remplacer_plan_source="oui"))
cas("plan_source/ne_porte_pas_titre_faux",
    params=params(Prefixe_scenario="Q100", Remplacer_plan_source="non"))
cas("plan_source/autres_homonymes",
    params=params(Prefixe_scenario="Q100"),
    plans={"01": "Reference", "03": "Q100", "07": "Q100"})
cas("plan_source/accepte_et_autres_homonymes",
    params=params(Prefixe_scenario="Q100", Remplacer_plan_source="oui"),
    plans={"01": "Q100", "07": "Q100"})
cas("plan_source/accepte_non_conforme",
    params=params(Prefixe_scenario="Q100", Remplacer_plan_source="oui"),
    plans={"01": "Q100"}, resultat=RESULTAT_NON_CONFORME)

# --- refus avant tout calcul ------------------------------------------------
cas("refus/symbole_decimal_virgule", decimal=",")
cas("refus/version_vide", params=params(Version_HECRAS=""))
cas("refus/version_blanche", params=params(Version_HECRAS="   "))
cas("version_absente_defaut", params=_avec(PARAMS, Version_HECRAS=_SUPPRIMER))
cas("refus/prefixe_trop_long", params=params(Prefixe_scenario="P" * 40))
cas("refus/prefixe_trop_long_par_apport",
    params=params(Prefixe_scenario="P" * 30),
    corr=_avec(CORR, **{COL_APPORT: ["A1", "A2", "A3_long"]}))

# --- HEC-RAS ouvert : commande_caler ne le consulte pas (preparer() le fait)
cas("hecras_ouvert", hecras_ouvert=True)

# --- classeur invalide ---------------------------------------------------------
cas("classeur/cible_manquante",
    cibles=_avec(CIBLES, C2=_SUPPRIMER))
cas("classeur/cible_vide",
    cibles=_avec(CIBLES, C3=[None] * 12))
cas("classeur/correspondance_vide",
    corr={"Ordre": [], COL_APPORT: [], COL_SECTION: [], COL_CIBLE: []})
cas("classeur/absent", classeur=False)
cas("classeur/sans_temps_h",
    cibles=_avec(_avec(CIBLES, Temps_h=_SUPPRIMER), Heure=CIBLES["Temps_h"]))
cas("classeur/cible_a_3_min",
    cibles={"Temps_h": [i * 0.05 for i in range(12)], "C1": list(_HYDRO),
            "C2": list(_HYDRO), "C3": list(_HYDRO)})
cas("classeur/pentes_saisies",
    corr=_avec(CORR, Pente_m_par_m=[0.002, "0,003", 0.004]))
cas("classeur/pentes_partielles",
    corr=_avec(CORR, Pente_m_par_m=[0.002, None, 0.004]))

# --- issue du calage ---------------------------------------------------------
cas("calage/non_conforme", resultat=RESULTAT_NON_CONFORME)
cas("calage/conforme_sans_diagnostics",
    resultat=_avec(RESULTAT_CONFORME, nb_diagnostics=0))
cas("calage/livrables_en_echec", exception_livrables="disque plein")
cas("calage/conclure_en_echec", exception_conclure="suivi illisible")
cas("calage/menage_en_echec", menage="fichier verrouille")
cas("calage/menage_sans_reliquat",
    menage=_avec(MENAGE, reliquats=[]))
cas("calage/menage_avec_supprimes",
    menage=_avec(MENAGE, supprimes=["p05"]))
cas("exception/pilote", exception_pilote="fenetre de simulation invalide")
cas("exception/caler", exception_caler="compute_plan a echoue")

# --- elagage des plans d'etape ---------------------------------------------
cas("elagage/conforme", params=params(Elaguer_plans_etape="oui"))
cas("elagage/conforme_true", params=params(Elaguer_plans_etape="True"))
cas("elagage/conforme_1", params=params(Elaguer_plans_etape="1"))
cas("elagage/conforme_refus", params=params(Elaguer_plans_etape="oui"),
    elagage={"refus": "aucun plan final"})
cas("elagage/conforme_exception", params=params(Elaguer_plans_etape="oui"),
    elagage="acces refuse")
cas("elagage/non_conforme", params=params(Elaguer_plans_etape="oui"),
    resultat=RESULTAT_NON_CONFORME)
cas("elagage/non_coche_non_conforme", params=params(Elaguer_plans_etape="non"),
    resultat=RESULTAT_NON_CONFORME)
cas("elagage/menage_en_echec_puis_elagage",
    params=params(Elaguer_plans_etape="oui"), menage="fichier verrouille")

# --- coeurs ---------------------------------------------------------------
cas("coeurs/zero", params=params(Coeurs_par_calcul=0))
cas("coeurs/texte", params=params(Coeurs_par_calcul="8"))


def _preparer(sc, dossier):
    """« <SORTIE> » designe un dossier de sortie a part dans le temporaire."""
    if sc["params"] and sc["params"].get("Dossier_sortie") == "<SORTIE>":
        sc = dict(sc)
        sc["params"] = dict(sc["params"],
                            Dossier_sortie=str(Path(dossier) / "sortie"))
    return sc


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def executer(nom, dossier, capsys):
    return jouer(_preparer(CAS[nom], dossier), dossier, capsys)


def _lire_reference():
    with REFERENCE.open(encoding="utf-8") as f:
        return json.load(f)


def test_reference_couvre_tous_les_cas():
    """Un cas ajoute sans figer la reference, ou retire en la laissant : refus."""
    assert sorted(_lire_reference()["cas"]) == sorted(CAS)


@pytest.mark.parametrize("nom", sorted(CAS))
def test_sortie_identique_a_la_reference(nom, tmp_path, capsys):
    attendu = _lire_reference()["cas"][nom]
    assert executer(nom, tmp_path, capsys) == attendu


class _Capture:
    """capsys hors pytest, pour --figer-reference."""

    def __init__(self):
        import io
        self._io = io
        self._ancien = None
        self._out = self._err = None

    def readouterr(self):
        if self._ancien is None:
            self._ancien = (sys.stdout, sys.stderr)
        else:
            sys.stdout, sys.stderr = self._ancien
        rendu = SimpleNamespace(
            out=self._out.getvalue() if self._out else "",
            err=self._err.getvalue() if self._err else "")
        self._out, self._err = self._io.StringIO(), self._io.StringIO()
        sys.stdout, sys.stderr = self._out, self._err
        return rendu

    def fermer(self):
        if self._ancien is not None:
            sys.stdout, sys.stderr = self._ancien


def figer_reference():
    resultats = {}
    for nom in sorted(CAS):
        with tempfile.TemporaryDirectory() as d:
            capture = _Capture()
            try:
                resultats[nom] = executer(nom, Path(d), capture)
            finally:
                capture.fermer()
    contenu = {
        "_a_propos": (
            "Caracterisation de pont_hecras.commande_caler "
            "(src/test_pont_caler.py). NE PAS MODIFIER A LA MAIN : « python "
            "src/test_pont_caler.py --figer-reference » le reecrit quand le "
            "changement de comportement est VOULU."),
        "cas": resultats,
    }
    REFERENCE.write_text(json.dumps(contenu, ensure_ascii=False, indent=1) + "\n",
                         encoding="utf-8")
    print(f"{len(resultats)} cas figes dans {REFERENCE.name}")


if __name__ == "__main__":
    if "--figer-reference" in sys.argv:
        figer_reference()
    else:
        sys.exit(pytest.main([__file__, "-q"]))
