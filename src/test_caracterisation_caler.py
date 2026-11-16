"""
Caracterisation de caler() : TOUT ce qu'il fait d'observable, fige.

POURQUOI CE FICHIER, A COTE DE reference_calage_fictif.json. La reference du
banc embarque (python calage.py) fige UN calage — quatre apports qui convergent
chacun au premier essai — et n'en retient que des nombres, compares a 1e-9
pres : ni le journal, ni l'ordre des appels au modele, ni ce que recoit le
suivi, ni aucune des branches d'arret. Decouper caler() demande davantage : un
message deplace d'une ligne, un appel au modele qui change de place, un essai
de plus ou de moins doivent se voir.

CE QUI EST FIGE, scenario par scenario, dans UNE SEULE suite ordonnee :
  - chaque ligne dite au journal ;
  - chaque appel fait au modele (methode, arguments, retour ou exception) ;
  - chaque appel fait au suivi (methode, arguments) ;
  - chaque lecture de l'horloge — time.time() est remplace par un compteur, si
    bien que les durees sont des nombres figes elles aussi ;
  - le ResultatCalage entier, champ par champ, et l'etat final du modele ;
  - l'exception, quand caler() en laisse sortir une.
L'ordre RELATIF de ces evenements fait partie de la reference : un message dit
avant le calcul au lieu d'apres est un ecart.

AU BIT PRES. Les flottants sont ecrits par float.hex(), les tableaux par leur
empreinte SHA-256. Une identite au bit pres ne vaut que sur le socle qui a
produit la reference (numpy, systeme, machine) : ailleurs, le test ne compare
que ce qui se transporte — le journal, la suite des appels, le bilan — et le
DIT par un avertissement. Avant de remanier caler() sur un autre poste,
refiger la reference SUR LE CODE D'ORIGINE.

CE TEST NE DIT PAS CE QUE LE CODE DEVRAIT FAIRE : il enregistre ce qu'il fait.

    python -m pytest src/test_caracterisation_caler.py
    python src/test_caracterisation_caler.py --figer      (reecrit la reference)
"""
import contextlib
import dataclasses
import hashlib
import io
import json
import platform
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calage as cg

REFERENCE = Path(__file__).resolve().parent / "reference_journal_caler.json"


# ---------------------------------------------------------------------------
# Figer une valeur
# ---------------------------------------------------------------------------

def _figer(v):
    """
    Forme JSON d'une valeur, sans perte : le type y est, les flottants sont en
    hexadecimal, les tableaux en empreinte. Un type inconnu LEVE — rien ne
    doit traverser sans avoir ete regarde.
    """
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, np.bool_):
        return f"np.bool:{bool(v)}"
    if isinstance(v, np.floating):          # avant float : np.float64 en herite
        return f"{type(v).__name__}:{float(v).hex()}"
    if isinstance(v, np.integer):
        return f"{type(v).__name__}:{int(v)}"
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return f"f:{v.hex()}"
    if isinstance(v, np.ndarray):
        a = np.ascontiguousarray(v)
        return (f"nd:{a.dtype}:{'x'.join(map(str, a.shape))}:"
                f"{hashlib.sha256(a.tobytes()).hexdigest()[:24]}")
    if isinstance(v, tuple):
        return {"tuple": [_figer(x) for x in v]}
    if isinstance(v, list):
        return [_figer(x) for x in v]
    if isinstance(v, dict):
        return {"dict": {str(k): _figer(x) for k, x in v.items()}}
    if isinstance(v, BaseException):
        return {"exception": type(v).__name__, "message": str(v)}
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        fige = {"classe": type(v).__name__}
        for champ in dataclasses.fields(v):
            fige[champ.name] = _figer(getattr(v, champ.name))
        if hasattr(type(v), "converge"):    # propriete de criteres.Diagnostic
            fige["converge"] = _figer(v.converge)
        return fige
    raise TypeError(f"valeur non figeable : {type(v).__name__}")


# ---------------------------------------------------------------------------
# Les trois temoins : modele, suivi, horloge
# ---------------------------------------------------------------------------

class _Espion:
    """
    Se place entre caler() et le modele : note chaque appel, avec ses
    arguments, puis son retour ou l'exception qu'il leve. Ne change rien a ce
    que le modele repond.
    """

    def __init__(self, reel, trace):
        self._reel, self._trace = reel, trace

    def __getattr__(self, nom):
        cible = getattr(self._reel, nom)
        if not callable(cible):
            return cible

        def appel(*arguments, **nommes):
            evenement = ["modele", nom, _figer(list(arguments))]
            if nommes:
                evenement.append({"nommes": _figer(nommes)})
            self._trace.append(evenement)
            try:
                rendu = cible(*arguments, **nommes)
            except Exception as e:
                evenement.append({"leve": _figer(e)})
                raise
            evenement.append({"rend": _figer(rendu)})
            return rendu
        return appel


class _FauxSuivi:
    """
    Un suivi qui enregistre tout ce qu'on lui dit, et rien d'autre. En panne
    (« leve »), il enregistre PUIS leve : caler() ne doit pas s'en apercevoir.
    """

    def __init__(self, trace, leve=False):
        self._trace, self._leve = trace, leve

    def __getattr__(self, nom):
        if nom.startswith("__"):
            raise AttributeError(nom)

        def appel(*arguments, **nommes):
            evenement = ["suivi", nom, _figer(list(arguments))]
            if nommes:
                evenement.append({"nommes": _figer(nommes)})
            self._trace.append(evenement)
            if self._leve:
                raise RuntimeError(f"suivi en panne ({nom})")
        return appel


class _Horloge:
    """
    Remplace le module « time » vu par calage.py. time() rend 0, 1, 2... et
    s'inscrit dans la trace : les durees deviennent des nombres figes, et
    l'endroit ou caler() regarde l'heure aussi.
    """

    def __init__(self, trace):
        self._trace, self._t = trace, 0.0

    def time(self):
        maintenant = self._t
        self._t += 1.0
        self._trace.append(["horloge", maintenant])
        return maintenant

    def sleep(self, secondes):
        return None


# ---------------------------------------------------------------------------
# Les montages
# ---------------------------------------------------------------------------

def _hydrogramme(t, pic, t_pic=6.0, forme=2.5):
    """Le meme que celui du banc embarque de calage.py."""
    t = np.maximum(np.asarray(t, dtype=float), 1e-3)
    return pic * (t / t_pic) ** forme * np.exp(forme * (1 - t / t_pic))


TEMPS = np.linspace(0.01, 36, 400)
APPORTS = ["A1", "A2", "A3", "A4"]
SECTIONS = ["S1_Amont", "S2_Pont", "S3_Confluence", "S4_Aval"]
FACTEURS_VRAIS = [4.5, 3.4, 3.6, 3.5]


def _formes(n=4):
    return [_hydrogramme(TEMPS, 10.0) for _ in range(n)]


def _cibles(n=4, **modele):
    """Cibles obtenues en faisant tourner le modele avec des facteurs connus."""
    m = cg.ModeleFictif(APPORTS[:n], SECTIONS[:n], TEMPS, _formes(n), **modele)
    for a, f in zip(APPORTS[:n], FACTEURS_VRAIS):
        m.appliquer_facteur(a, f)
    return [m.lire_section(s) for s in SECTIONS[:n]]


class _Capricieux(cg.ModeleFictif):
    """
    ModeleFictif dont on choisit les defaillances, par leur RANG d'appel
    (1 = le premier). Tout ce qui n'est pas demande se comporte comme lui.
    """
    lectures_en_echec = ()      # lire_section() qui levent
    calculs_en_echec = ()       # calculer() qui levent
    calculs_rates = ()          # calculer() qui rendent reussi=False
    jalons_en_echec = ()        # jalonner() qui levent
    bavard = False              # jalonner() et conclure() rendent un texte
    conclure_en_echec = False
    retard_en_echec = False
    retard_a_moitie = False     # retarder() ne retarde que de la moitie
    formes_en_echec = ()        # definir_forme() qui levent
    duree_en_echec = False
    garde_amont = ()            # apports que preparer() ne remet pas a zero
    remous = 0.0                # part du debit qu'une section perd des qu'un
    #                             apport est actif EN AVAL d'elle

    def __init__(self, *arguments, **nommes):
        super().__init__(*arguments, **nommes)
        self._lectures = self._jalons = self._formes = 0

    def preparer(self):
        gardes = {a: self.facteurs[a] for a in self.garde_amont}
        super().preparer()
        self.facteurs.update(gardes)

    def jalonner(self, etape):
        self._jalons += 1
        if self._jalons in self.jalons_en_echec:
            raise OSError(f"fichier verrouille ({etape})")
        super().jalonner(etape)
        return f"plan p{self._jalons:02d} ouvert" if self.bavard else None

    def conclure(self, etape):
        if self.conclure_en_echec:
            raise PermissionError("interface laissee ouverte")
        super().conclure(etape)
        return "plan retitre" if self.bavard else None

    def retarder(self, heures, apports):
        if self.retard_en_echec:
            raise ValueError("axe non modifiable")
        if self.retard_a_moitie:
            return super().retarder(heures / 2.0, apports)
        return super().retarder(heures, apports)

    def definir_forme(self, nom_apport, temps_h, debits):
        self._formes += 1
        if self._formes in self.formes_en_echec:
            raise OSError(f"unsteady en lecture seule ({nom_apport})")
        return super().definir_forme(nom_apport, temps_h, debits)

    def limiter_duree(self, heures):
        if self.duree_en_echec:
            raise OSError("plan en lecture seule")
        return super().limiter_duree(heures)

    def calculer(self):
        rang = self.nb_calculs + 1
        if rang in self.calculs_en_echec:
            self.nb_calculs += 1
            raise RuntimeError(f"le solveur s'est arrete (calcul {rang})")
        calcul = super().calculer()
        if rang in self.calculs_rates:
            return cg.ResultatCalcul(reussi=False, message="solveur instable")
        return calcul

    def lire_section(self, nom_section):
        self._lectures += 1
        if self._lectures in self.lectures_en_echec:
            raise RuntimeError(
                f"plan sans resultats (lecture {self._lectures})")
        t, q = super().lire_section(nom_section)
        rang = self.sections.index(nom_section)
        if self.remous and any(self.facteurs[a]
                               for a in self.apports[rang + 1:]):
            q = q * (1.0 - self.remous)
        return t, q


def _capricieux(n=4, modele=None, **defaillances):
    m = _Capricieux(APPORTS[:n], SECTIONS[:n], TEMPS, _formes(n),
                    **(modele or {}))
    for cle, valeur in defaillances.items():
        assert hasattr(_Capricieux, cle), cle
        setattr(m, cle, valeur)
    return m


def _fictif(n=4, **modele):
    return cg.ModeleFictif(APPORTS[:n], SECTIONS[:n], TEMPS, _formes(n),
                           **modele)


def _montage(modele, n=4, cibles=None, config=None, sections=None, **options):
    """Les arguments d'un appel a caler(), sous une forme que _jouer() lit."""
    return {"modele": modele, "apports": APPORTS[:n],
            "sections": SECTIONS[:n] if sections is None else sections,
            "cibles": _cibles(n) if cibles is None else cibles,
            "config": config, **options}


# --- deux apports dont les evenements finissent loin l'un de l'autre -------
_T6 = np.linspace(0.0, 40.0, 401)
_F6 = [np.exp(-0.5 * ((_T6 - 3.0) / 1.0) ** 2),
       np.exp(-0.5 * ((_T6 - 14.0) / 2.5) ** 2)]


def _montage_durees(config, classe=cg.ModeleFictif, **options):
    m = classe(["A1", "A2"], ["S1", "S2"], _T6, [f.copy() for f in _F6],
               retard_h=0.0)
    cibles = []
    for k in range(2):
        m.facteurs = {"A1": 30.0, "A2": 45.0}
        cibles.append((_T6, m.lire_section(f"S{k + 1}")[1].copy()))
    m.preparer()
    return {"modele": m, "apports": ["A1", "A2"], "sections": ["S1", "S2"],
            "cibles": cibles, "config": config, **options}


# --- une serie de 20 h dont l'evenement finit pres du bout : le plafond ----
_T9 = np.linspace(0.0, 20.0, 201)


def _montage_plafond(config, pics=(14.0,), classe=cg.ModeleFictif, **attributs):
    noms = [f"A{k + 1}" for k in range(len(pics))]
    secs = [f"S{k + 1}" for k in range(len(pics))]
    formes = [np.exp(-0.5 * ((_T9 - p) / 2.0) ** 2)
              + 0.004 * np.exp(-(_T9 - p) / 25.0) * (_T9 > p) for p in pics]
    m = classe(noms, secs, _T9, formes, retard_h=0.0)
    for cle, valeur in attributs.items():
        setattr(m, cle, valeur)
    m.facteurs = {a: 40.0 for a in noms}
    cibles = [(_T9, m.lire_section(s)[1].copy()) for s in secs]
    m.preparer()
    return {"modele": m, "apports": noms, "sections": secs, "cibles": cibles,
            "config": config}


# --- la cible decalee commence avant le debut de la simulation -------------
_TK = np.round(np.arange(0.0, 26.0 + 1e-9, 0.1), 6)


def _montage_retard(classe=cg.ModeleFictif, config=None, **attributs):
    m = classe(["K1"], ["SK1"], _TK, [np.zeros_like(_TK)],
               debit_base=_hydrogramme(_TK, 1.7, t_pic=2.0))
    for cle, valeur in attributs.items():
        setattr(m, cle, valeur)
    return {"modele": m, "apports": ["K1"], "sections": ["SK1"],
            "cibles": [(_TK, _hydrogramme(_TK, 3.4, t_pic=4.5))],
            "config": config or cg.Configuration(nb_max_essais=6)}


class _SansRetard(cg.ModeleFictif):
    def retarder(self, heures, apports):
        return None


def _montage_reprise(prefixe=""):
    """A1 et A2 deja cales restent en place ; la liste ne porte que l'aval."""
    m = _capricieux(garde_amont=("A1", "A2"))
    m.appliquer_facteur("A1", FACTEURS_VRAIS[0])
    m.appliquer_facteur("A2", FACTEURS_VRAIS[1])
    return {"modele": m, "apports": APPORTS[2:], "sections": SECTIONS[2:],
            "cibles": _cibles()[2:],
            "config": cg.Configuration(nb_max_essais=8, prefixe_etape=prefixe),
            "etape_reference": "sans A3 et aval"}


def _montage_derive_axe():
    """
    Quatre apports dont les evenements ne tombent pas ensemble : le residuel
    de la deuxieme section culmine onze heures avant sa cible, celui des
    suivantes en meme temps qu'elle. Le decalage retenu n'est pas le meme
    d'une section a l'autre.
    """
    noms, secs = APPORTS, ["S1", "S2", "S3", "S4"]
    formes = [np.exp(-0.5 * ((_T6 - 3.0) / 1.0) ** 2),
              np.exp(-0.5 * ((_T6 - 14.0) / 2.5) ** 2),
              np.exp(-0.5 * ((_T6 - 15.0) / 2.5) ** 2),
              np.exp(-0.5 * ((_T6 - 16.0) / 2.5) ** 2)]
    m = cg.ModeleFictif(noms, secs, _T6, formes, retard_h=0.0)
    m.facteurs = dict(zip(noms, (30.0, 45.0, 10.0, 10.0)))
    cibles = [(_T6, m.lire_section(s)[1].copy()) for s in secs]
    m.preparer()
    return {"modele": m, "apports": noms, "sections": secs, "cibles": cibles,
            "config": cg.Configuration(nb_max_essais=4), "suivi": "faux"}


_BASE = _hydrogramme(TEMPS, 60.0)


def _montage_plancher(**modele):
    """
    Un debit non cale qui deborde la cible sur une partie de la fenetre et
    reste dessous ailleurs : le calage part, et bute sur ce qu'un apport ne
    sait pas retirer.
    """
    m = cg.ModeleFictif(
        ["A1"], ["S1"], TEMPS, [_hydrogramme(TEMPS, 10.0)],
        debit_base=_hydrogramme(TEMPS, 140.0, t_pic=12.0, forme=8.0),
        **modele)
    return {"modele": m, "apports": ["A1"], "sections": ["S1"],
            "cibles": [(TEMPS, _hydrogramme(TEMPS, 100.0, t_pic=12.0,
                                            forme=2.0))],
            "config": cg.Configuration(nb_max_essais=8), "suivi": "faux"}


def _montage_etale(**reglages):
    """
    Cible pointue, debit non cale large, troncon qui lamine : le volume est
    deja de trop quand la pointe manque encore, et la pointe ne monte plus
    que de quelques millioniemes par essai.
    """
    m = cg.ModeleFictif(
        ["A1"], ["S1"], TEMPS, [_hydrogramme(TEMPS, 10.0)],
        debit_base=60.0 * np.exp(-0.5 * ((TEMPS - 12.0) / 2.0) ** 2),
        laminage=0.2, retard_h=0.0)
    return {"modele": m, "apports": ["A1"], "sections": ["S1"],
            "cibles": [(TEMPS,
                        100.0 * np.exp(-0.5 * ((TEMPS - 12.0) / 1.0) ** 2))],
            "config": cg.Configuration(**{"nb_max_essais": 8, **reglages}),
            "suivi": "faux"}


SCENARIOS = {
    # --- le chemin nominal, et ses variantes de reglage --------------------
    "conforme_un_essai_avec_suivi": lambda: _montage(
        _fictif(), config=cg.Configuration(nb_max_essais=8), suivi="faux"),
    "conforme_sans_suivi_ni_config": lambda: _montage(_fictif(n=2), n=2),
    "journal_par_defaut_print": lambda: _montage(
        _fictif(n=1), n=1, journal="print"),
    "suivi_en_panne": lambda: _montage(
        _fictif(n=2), n=2, suivi="en panne"),
    "aucun_apport": lambda: _montage(_fictif(n=1), n=0, cibles=[]),
    "moins_de_sections_que_d_apports": lambda: _montage(
        _fictif(n=2), n=2, sections=SECTIONS[:1], cibles=_cibles(1)),
    "prefixe_de_scenario": lambda: _montage(
        _fictif(), config=cg.Configuration(nb_max_essais=8,
                                           prefixe_etape="Q100"),
        suivi="faux"),
    "controle_amont_faux": lambda: _montage(
        _fictif(), config=cg.Configuration(controle_amont=False)),
    "reprise_au_troisieme_apport": lambda: _montage_reprise(),
    "reprise_sous_prefixe": lambda: _montage_reprise("Q100"),
    "etapes_dites_par_le_modele": lambda: _montage(
        _capricieux(n=2, bavard=True), n=2, suivi="faux"),
    "jalon_et_titre_final_en_echec": lambda: _montage(
        _capricieux(n=2, jalons_en_echec=(1, 3), conclure_en_echec=True),
        n=2),

    # --- plusieurs essais, et les arrets de la recherche -------------------
    "plusieurs_essais_laminage": lambda: _montage(
        _fictif(laminage=0.05), cibles=_cibles(laminage=0.05),
        config=cg.Configuration(nb_max_essais=8), suivi="faux"),
    "essais_epuises": lambda: _montage(
        _fictif(n=2, laminage=0.3), n=2, cibles=_cibles(2, laminage=0.3),
        config=cg.Configuration(nb_max_essais=2), suivi="faux"),
    "essais_epuises_tolerances_serrees": lambda: _montage(
        _fictif(n=1, laminage=0.3), n=1, cibles=_cibles(1, laminage=0.3),
        config=cg.Configuration(nb_max_essais=3, tolerance_volume=1e-4,
                                tolerance_pic=1e-4, r_min=0.99999)),
    "un_seul_essai_autorise": lambda: _montage(
        _fictif(n=1, laminage=0.3), n=1, cibles=_cibles(1, laminage=0.3),
        config=cg.Configuration(nb_max_essais=1), suivi="faux"),
    "essais_epuises_pointe_deja_haute": lambda: _montage_retard(
        _SansRetard, config=cg.Configuration(nb_max_essais=3)),
    "correction_sans_effet": lambda: _montage_plancher(retard_h=0.0),
    "volume_excedentaire_pointe_deficitaire": lambda: _montage_etale(),
    "pointe_qui_progresse_lentement": lambda: _montage_etale(
        nb_max_essais=6, tolerance_pic=1e-6),
    "cible_egale_au_residuel": lambda: _montage(
        _fictif(n=1, debit_base=_BASE), n=1,
        cibles=[_fictif(n=1, debit_base=_BASE).lire_section(SECTIONS[0])]),
    "cible_infime": lambda: _montage(
        _fictif(n=1), n=1, cibles=[(TEMPS, _hydrogramme(TEMPS, 1e-11))],
        config=cg.Configuration(nb_max_essais=3)),
    "bilan_de_masse_rejete_a_la_reference": lambda: _montage(
        _fictif(n=1, bilan_masse_pct=5.0), n=1,
        config=cg.Configuration(bilan_masse_max_pct=1.0), suivi="faux"),
    "bilan_de_masse_rejete_en_cours": lambda: _montage(
        _fictif(n=1, seuil_instabilite=0.5), n=1,
        config=cg.Configuration(bilan_masse_max_pct=1.0), suivi="faux"),
    "calcul_rate_a_la_reference": lambda: _montage(
        _capricieux(n=1, calculs_rates=(1,)), n=1),
    "calcul_rate_au_second_apport": lambda: _montage(
        _capricieux(n=3, calculs_rates=(3,)), n=3, suivi="faux"),
    "apport_peu_identifiable": lambda: _montage(
        _fictif(n=1, debit_base=_BASE), n=1, cibles=[(TEMPS, _BASE / 0.98)],
        config=cg.Configuration(nb_max_essais=2), suivi="faux"),
    "cible_sous_le_residuel": lambda: _montage(
        _fictif(n=2, debit_base=_BASE), n=2,
        cibles=[(TEMPS, _cibles(1)[0][1] * 0.05), _cibles(2)[1]],
        config=cg.Configuration(nb_max_essais=4), suivi="faux"),
    "volume_plancher_cliquet": lambda: _montage_plancher(),

    # --- fenetre de jugement ----------------------------------------------
    "fenetre_desactivee": lambda: _montage(
        _fictif(n=2), n=2,
        config=cg.Configuration(fenetre_active=False, nb_max_essais=4)),
    "fenetre_imposee": lambda: _montage(
        _fictif(n=2), n=2,
        config=cg.Configuration(fenetre_t0_h=2.0, fenetre_tf_h=18.0)),
    "fenetre_sans_marge": lambda: _montage(
        _fictif(n=2), n=2, config=cg.Configuration(fenetre_marge_h=0.0)),

    # --- duree simulee -----------------------------------------------------
    "duree_ajustee_decalage_aberrant": lambda: _montage_durees(
        cg.Configuration(nb_max_essais=4), suivi="faux"),
    "duree_non_ajustee": lambda: _montage_durees(
        cg.Configuration(nb_max_essais=4, ajuster_duree=False)),
    "plan_source_remplace_meme_non_conforme": lambda: _montage_durees(
        cg.Configuration(nb_max_essais=4, remplacer_plan_source=True)),
    "plan_source_remplace": lambda: _montage(
        _fictif(n=2), n=2,
        config=cg.Configuration(remplacer_plan_source=True,
                                prefixe_etape="Q10")),
    "plafond_rogne_la_marge": lambda: _montage_plafond(
        cg.Configuration(nb_max_essais=4)),
    "plafond_rogne_la_fenetre": lambda: _montage_plafond(
        cg.Configuration(nb_max_essais=4, marge_duree_h=0.0), pics=(15.5,)),
    "marge_rognee_tout_entiere": lambda: _montage_plafond(
        cg.Configuration(nb_max_essais=4, fenetre_tf_h=19.0)),
    "plafond_herite_de_l_etape_precedente": lambda: _montage_plafond(
        cg.Configuration(nb_max_essais=4), pics=(13.0, 14.0)),
    "limiter_duree_en_echec": lambda: _montage_plafond(
        cg.Configuration(nb_max_essais=4), classe=_Capricieux,
        duree_en_echec=True),

    # --- retard de l'axe temporel ------------------------------------------
    "axe_retarde": lambda: _montage_retard(),
    "axe_non_retardable": lambda: _montage_retard(_SansRetard),
    "retarder_leve": lambda: _montage_retard(_Capricieux,
                                             retard_en_echec=True),
    "axe_retarde_a_moitie": lambda: _montage_retard(
        _Capricieux, retard_a_moitie=True),
    "illisible_apres_le_retard": lambda: _montage_retard(
        _Capricieux, lectures_en_echec=(2,)),

    # --- coherence du decalage le long de l'axe ----------------------------
    "decalage_qui_derive": lambda: _montage_derive_axe(),

    # --- le modele defaille ------------------------------------------------
    "section_illisible_a_la_reference": lambda: _montage(
        _fictif(n=1), n=1, sections=["Section_absente"]),
    "residuel_illisible_au_tour_de_l_apport": lambda: _montage(
        _capricieux(n=2, lectures_en_echec=(3,)), n=2, suivi="faux"),
    "residuel_illisible_au_second_apport": lambda: _montage(
        _capricieux(n=2, lectures_en_echec=(5,)), n=2, suivi="faux"),
    "section_amont_illisible_a_l_etape_7": lambda: _montage(
        _capricieux(n=3, lectures_en_echec=(8,)), n=3),
    "section_amont_deplacee_par_le_remous": lambda: _montage(
        _capricieux(n=3, remous=0.2), n=3, suivi="faux"),
    "lecture_qui_leve_pendant_un_essai": lambda: _montage(
        _capricieux(n=2, lectures_en_echec=(4,)), n=2, suivi="faux"),
    "lecture_qui_leve_a_la_verification_globale": lambda: _montage(
        _capricieux(n=2, lectures_en_echec=(8,)), n=2, suivi="faux"),
    "calcul_qui_leve_a_la_reference": lambda: _montage(
        _capricieux(n=2, calculs_en_echec=(1,)), n=2, suivi="faux"),
    "calcul_qui_leve_pendant_un_essai": lambda: _montage(
        _capricieux(n=3, calculs_en_echec=(3,)), n=3, suivi="faux"),
    "ecriture_de_l_apport_qui_leve": lambda: _montage(
        _capricieux(n=2, formes_en_echec=(2,)), n=2, suivi="faux"),
}


# ---------------------------------------------------------------------------
# Jouer un scenario
# ---------------------------------------------------------------------------

def _resultat_fige(resultat, config_passee):
    """Le ResultatCalage, champ par champ ; un evenement par element de liste."""
    evenements = [["bilan", {
        "nb_calculs": int(resultat.nb_calculs),
        "conforme": bool(resultat.conforme),
        "motif": resultat.motif,
        "apports": [[a.nom_apport, bool(a.valide), int(a.essais), a.motif]
                    for a in resultat.apports],
        "alertes_chaine": list(resultat.alertes_chaine)}]]
    for champ in dataclasses.fields(resultat):
        valeur = getattr(resultat, champ.name)
        if isinstance(valeur, list) and champ.name != "alertes_chaine":
            evenements.append(["resultat", f"len({champ.name})", len(valeur)])
            for k, element in enumerate(valeur):
                evenements.append(["resultat", f"{champ.name}[{k}]",
                                   _figer(element)])
        else:
            evenements.append(["resultat", champ.name, _figer(valeur)])
    evenements.append(["resultat", "config est celle passee",
                       config_passee is None or resultat.config is config_passee])
    return evenements


def _modele_fige(modele):
    return ["modele_final", {
        "facteurs": _figer(modele.facteurs),
        "formes": _figer(modele.formes),
        # L'HYDROGRAMME INJECTE EST LE LIVRABLE : forme x facteur.
        "hydrogrammes": _figer({a: modele.formes[a] * modele.facteurs[a]
                                for a in modele.apports}),
        "debit_base": _figer(modele.debit_base),
        "etapes": list(modele.etapes),
        "duree_max": _figer(modele.duree_max),
        "durees_demandees": _figer(modele.durees_demandees),
        "nb_calculs": modele.nb_calculs}]


def _jouer(nom):
    """Joue un scenario et rend sa trace : la suite ordonnee des evenements."""
    montage = dict(SCENARIOS[nom]())
    trace = []
    modele = montage.pop("modele")
    config = montage.pop("config")
    suivi = montage.pop("suivi", None)
    journal = montage.pop("journal", None)
    arguments = [_Espion(modele, trace), montage.pop("apports"),
                 montage.pop("sections"), montage.pop("cibles")]
    if config is not None:
        montage["config"] = config
    if suivi is not None:
        montage["suivi"] = _FauxSuivi(trace, leve=(suivi == "en panne"))
    if journal != "print":
        montage["journal"] = lambda ligne: trace.append(["journal", ligne])

    vraie_horloge, sortie = cg.time, io.StringIO()
    cg.time = _Horloge(trace)
    try:
        with contextlib.redirect_stdout(sortie):
            try:
                resultat = cg.caler(*arguments, **montage)
            except Exception as e:                          # noqa: BLE001
                trace.append(["exception", _figer(e)])
            else:
                trace.extend(_resultat_fige(resultat, config))
    finally:
        cg.time = vraie_horloge
    if sortie.getvalue():
        trace.append(["stdout", sortie.getvalue().splitlines()])
    trace.append(_modele_fige(modele))
    return trace


# ---------------------------------------------------------------------------
# La reference
# ---------------------------------------------------------------------------

def _simd():
    """
    Les jeux d'instructions vectorielles que numpy EMPLOIE sur ce processeur.

    Ils font partie du socle (11/11/2026) : numpy choisit ses noyaux de calcul
    selon le processeur, et une somme faite avec ou sans AVX-512 differe d'un
    dernier bit. A versions egales, deux machines ne rendent donc PAS les
    memes octets ; sans cette ligne, le filet « au bit pres » echouait a tort
    sur un processeur different de celui qui a fige la reference.
    """
    try:
        from numpy._core._multiarray_umath import (__cpu_dispatch__ as cibles,
                                                   __cpu_features__ as vus)
    except ImportError:
        return "inconnu"
    return "+".join(c for c in cibles if vus.get(c)) or "base"


def _socle():
    return {"python": platform.python_version(), "numpy": np.__version__,
            "systeme": platform.system(), "machine": platform.machine(),
            "simd": _simd()}


def _meme_socle(produit_par):
    ici = _socle()
    return all(produit_par.get(c) == ici[c]
               for c in ("numpy", "systeme", "machine", "simd"))


def _transportable(trace):
    """
    Ce qui ne depend pas du dernier bit : le journal et le bilan en entier,
    et des autres evenements leur seule nature (qui, quelle methode).
    """
    # L'etat final du modele n'a pas de « methode » en seconde position : son
    # second element EST son contenu, au bit pres. Le garder faisait echouer
    # les 57 scenarios hors du socle (CI du 10/11/2026 : numpy 2.5.4 au lieu
    # de 2.5.3, memes journaux, tableaux differents au dernier bit).
    return [e if e[0] in ("journal", "bilan", "stdout", "exception")
            else e[:1] if e[0] == "modele_final"
            else e[:2] for e in trace]


def _ecrire_reference():
    """UN EVENEMENT PAR LIGNE : le diff d'une reference refigee se relit."""
    def ligne(objet):
        return json.dumps(objet, ensure_ascii=False)

    blocs = []
    for nom in SCENARIOS:
        corps = ",\n".join("   " + ligne(e) for e in _jouer(nom))
        blocs.append(f"  {ligne(nom)}: [\n{corps}\n  ]")
    a_propos = (
        "Caracterisation de caler() : journal, appels au modele et au suivi, "
        "resultat, scenario par scenario. NE PAS MODIFIER A LA MAIN : "
        "« python src/test_caracterisation_caler.py --figer » le reecrit, "
        "quand le changement de comportement est VOULU.")
    REFERENCE.write_text(
        "{\n"
        f' "_a_propos": {ligne(a_propos)},\n'
        f' "_produit_par": {ligne(_socle())},\n'
        ' "scenarios": {\n' + ",\n".join(blocs) + "\n }\n}\n",
        encoding="utf-8")


def _lire_reference():
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def _premier_ecart(obtenu, attendu):
    """Rang et texte du premier evenement qui differe, avec ce qui le precede."""
    for k, (o, a) in enumerate(zip(obtenu, attendu)):
        if o != a:
            avant = "\n".join(f"      {json.dumps(e, ensure_ascii=False)[:160]}"
                              for e in attendu[max(0, k - 3):k])
            return (f"evenement {k} :\n   precede de :\n{avant}\n"
                    f"   attendu : {json.dumps(a, ensure_ascii=False)}\n"
                    f"   obtenu  : {json.dumps(o, ensure_ascii=False)}")
    return (f"{len(obtenu)} evenement(s) au lieu de {len(attendu)} ; le "
            f"premier en trop ou manquant : "
            f"{json.dumps((obtenu + attendu)[min(len(obtenu), len(attendu))], ensure_ascii=False)}")


def test_la_reference_couvre_les_scenarios_et_eux_seuls():
    assert REFERENCE.is_file(), (
        f"{REFERENCE.name} absent — le creer par "
        f"« python src/test_caracterisation_caler.py --figer »")
    assert list(_lire_reference()["scenarios"]) == list(SCENARIOS)


@pytest.mark.parametrize("nom", list(SCENARIOS))
def test_caler_fait_exactement_ce_que_la_reference_a_enregistre(nom):
    reference = _lire_reference()
    # json.loads(json.dumps()) : la trace obtenue passe par la meme forme que
    # la reference (les tuples y deviennent des listes), sans quoi rien ne
    # serait jamais egal.
    obtenu = json.loads(json.dumps(_jouer(nom), ensure_ascii=False))
    attendu = reference["scenarios"][nom]
    if not _meme_socle(reference["_produit_par"]):
        warnings.warn(
            f"reference produite sous {reference['_produit_par']}, ici "
            f"{_socle()} : seuls le journal, la suite des appels et le bilan "
            f"sont compares. L'identite AU BIT PRES n'est PAS verifiee — "
            f"refiger la reference sur le code d'origine avant de remanier "
            f"caler() sur ce poste.")
        obtenu, attendu = _transportable(obtenu), _transportable(attendu)
    assert obtenu == attendu, _premier_ecart(obtenu, attendu)


def test_rejouer_un_scenario_rend_la_meme_trace():
    """Sans quoi la reference figerait du hasard, ou un etat qui fuit."""
    assert _jouer("plusieurs_essais_laminage") == _jouer(
        "plusieurs_essais_laminage")


if __name__ == "__main__":
    if "--figer" in sys.argv:
        _ecrire_reference()
        print(f"REFERENCE REECRITE : {REFERENCE.name} "
              f"({REFERENCE.stat().st_size / 1024:.0f} ko, "
              f"{len(SCENARIOS)} scenarios). Relire le diff avant de "
              f"committer : il dit ce que le changement a deplace.")
    else:
        raise SystemExit(pytest.main([__file__, "-q"]))
