"""
Filet de PiloteHecRas._recadencer_apports() et de _messages_hecras() : ce
qu'elles font d'observable, fige avant de les decouper.

POURQUOI CES DEUX FONCTIONS. Le re-cadencage reecrit les conditions limites
que HEC-RAS va lire : une serie qui ne couvre plus la fenetre de simulation
fait refuser le calcul (« Time series data ends before the end of the
simulation » ; calage repris de Suhihandia arrete le 14/09/2026 apres douze
« pas de temps 30 min -> converti en 6 min »), et un volume deplace par
l'interpolation fausserait le calage sans rien dire. Les messages, eux, sont
le seul endroit ou l'ingenieur apprend pourquoi HEC-RAS a refuse (0.8.4 : les
quatre lignes gardees etaient le tableau des temps).

CE QUI EST FIGE, cas par cas, dans reference_pilote_recadence.json :
  - le fichier unsteady reecrit, OCTET POUR OCTET (empreinte SHA-256, et le
    texte lui-meme, decode en latin-1 — un octet, un caractere — sous 6 ko) ;
  - les lignes imprimees (le journal du calage) ;
  - la valeur rendue, la carte reconstruite, l'exception levee ;
  - pour _messages_hecras, la phrase rendue.
CE TEST NE DIT PAS CE QUE LE CODE DEVRAIT FAIRE : il enregistre ce qu'il fait.

DEUX INVARIANTS PHYSIQUES sont verifies EN PLUS, sur chaque apport converti,
independamment de la reference (test_invariants_physiques) :
  - la duree couverte n'est jamais raccourcie, et ne s'allonge que de moins
    d'un pas de travail (arrondi au pas suivant) ;
  - le volume de la serie reecrite est celui de la serie d'origine, lue
    comme HEC-RAS la lit (lineaire entre ses points, tenue au-dela), sur la
    meme duree. Tolerance CONSTATEE, et assertee comme telle : voir
    TOLERANCES_VOLUME.

DEPENDANCES. cartographier_hydrogrammes() et lire_hydrogramme_unsteady()
lisent le tableau par ras_commander.RasUnsteady : le re-cadencage n'est pas
doublable sans reecrire ce que l'on veut justement figer. Ces cas demandent
donc ras_commander (installe dans le job CI « chaine-hdf ») et sont IGNORES
sans lui. _messages_hecras ne demande que h5py. Ni HEC-RAS ni Windows.

AU BIT PRES, sur le socle qui a produit la reference seulement (numpy,
systeme, machine). Ailleurs, les tableaux de debits sont compares a 0,01
pres — le dernier chiffre ecrit — et le reste a l'identique.

    python -m pytest src/test_pilote_recadence.py
    python src/test_pilote_recadence.py --figer       (reecrit la reference)
"""
import contextlib
import hashlib
import io
import json
import os
import platform
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pilote_hecras as ph                                  # noqa: E402

REFERENCE = Path(__file__).resolve().parent / "reference_pilote_recadence.json"
TEXTE_MAX = 6000            # au-dela, le fichier n'est fige que par empreinte
ZONE = "Perimeter 1"

try:
    import ras_commander                                    # noqa: F401
    RAS_COMMANDER = True
except ImportError:                                         # pragma: no cover
    RAS_COMMANDER = False
try:
    import h5py
except ImportError:                                         # pragma: no cover
    h5py = None


# ---------------------------------------------------------------------------
# Fabrication des fichiers unsteady, au format qu'ecrit HEC-RAS
# ---------------------------------------------------------------------------

def _localisation(nom, zone):
    """« Boundary Location= », largeurs relevees sur des fichiers reels."""
    largeurs = (16, 16, 8, 8, 16, 16, 16, 32, 32)
    champs = ["", "", "", "", "", zone, "", nom, ""]
    return "Boundary Location=" + ",".join(
        c.ljust(l) for c, l in zip(champs, largeurs))


def _tableau(valeurs):
    """Dix champs de huit caracteres par ligne ; une chaine passe telle quelle."""
    champs = [v if isinstance(v, str) else f"{v:8.2f}" for v in valeurs]
    return ["".join(champs[i:i + 10]) for i in range(0, len(champs), 10)]


def bloc(nom, valeurs, intervalle="1HOUR", zone=ZONE, pente=True,
         queue=("DSS Path=", "Use DSS=False", "Use Fixed Start Time=False")):
    """Un bloc de condition limite a hydrogramme de debit."""
    lignes = [_localisation(nom, zone)]
    if intervalle is not None:
        lignes.append(f"Interval={intervalle}")
    lignes.append(f"Flow Hydrograph= {len(valeurs)} ")
    lignes += _tableau(valeurs)
    lignes.append("Stage Hydrograph TW Check=0")
    if pente:
        lignes.append("Flow Hydrograph Slope= 0.02 ")
    lignes += list(queue)
    return lignes


def sortie(nom, zone=ZONE):
    """Une condition de SORTIE : une pente, aucun hydrogramme."""
    return [_localisation(nom, zone), "Friction Slope=0.001,0"]


def unsteady(*blocs, fin="\r\n"):
    lignes = ["Flow Title=Essai recadence", "Program Version=6.60",
              "Use Restart= 0 "]
    for b in blocs:
        lignes += b
    return (fin.join(lignes) + fin).encode("cp1252")


def plan(debut="01JAN2024,0000", fin="02JAN2024,0000"):
    lignes = ["Plan Title=Essai", "Program Version=6.60", "Geom File=g01",
              "Flow File=u02"]
    if debut is not None:
        lignes.append(f"Simulation Date={debut},{fin}")
    return ("\r\n".join(lignes) + "\r\n").encode("cp1252")


def h(n, depart=0.0, pic=50.0):
    """
    Une crue DISSYMETRIQUE de n valeurs, montee rapide et longue decrue.
    Pas une sinusoide : la regle des trapezes est exacte sur un sin² pris sur
    une periode entiere, et le volume y paraissait conserve par hasard.
    """
    x = np.linspace(0.0, 1.0, n) / 0.25
    return [round(depart + pic * float(t ** 3 * np.exp(3.0 * (1.0 - t))), 2)
            for t in x]


# Chaque cas : le fichier .u02 fabrique, le pilote (pas de travail, apports
# pilotes, zone, BC lines de la geometrie) et, s'il y a lieu, le plan .p02.
CAS_RECADENCE = {
    "un_apport_1h_vers_6min": dict(
        u=unsteady(bloc("AMONT", [10.0, 50.0, 100.0, 20.0])),
        pas=0.1),
    "trois_apports_30min_vers_6min_prolonges": dict(
        u=unsteady(bloc("SUH01", h(12), "30MIN"),
                   bloc("SUH02", h(12, 1.0, 20.0), "30MIN"),
                   bloc("SUH12", h(12, 0.5, 80.0), "30MIN")),
        pas=0.1, apports=["SUH01", "SUH02", "SUH12"],
        p=plan("01JAN2000,0000", "01JAN2000,1200")),
    "trois_apports_30min_vers_6min_sans_plan": dict(
        u=unsteady(bloc("SUH01", h(12), "30MIN"),
                   bloc("SUH02", h(12, 1.0, 20.0), "30MIN"),
                   bloc("SUH12", h(12, 0.5, 80.0), "30MIN")),
        pas=0.1, apports=["SUH01", "SUH02", "SUH12"]),
    "15min_vers_6min_non_commensurable": dict(
        u=unsteady(bloc("A", [0.0, 5.0, 12.0, 7.0], "15MIN")), pas=0.1),
    "deja_au_pas": dict(
        u=unsteady(bloc("A", [1.0, 2.0, 3.0], "6MIN")), pas=0.1),
    "5min_vers_6min": dict(
        u=unsteady(bloc("A", h(13), "5MIN")), pas=0.1),
    "6min_vers_30min_pas_plus_grossier": dict(
        u=unsteady(bloc("A", h(21), "6MIN")), pas=0.5),
    "1h_vers_15min_multiple": dict(
        u=unsteady(bloc("A", h(9), "1HOUR")), pas=0.25),
    "une_seule_valeur": dict(
        u=unsteady(bloc("A", [4.0], "1HOUR")), pas=0.1),
    "deux_valeurs": dict(
        u=unsteady(bloc("A", [4.0, 9.0], "1HOUR")), pas=0.1),
    "tres_long_240h": dict(
        u=unsteady(bloc("A", h(240, 2.0, 400.0), "1HOUR")), pas=0.1),
    "nulles_saturees_negatives": dict(
        u=unsteady(bloc("A", [0.0, 0.0, "99999.99", "123456.7", " 1234567",
                              "12345.67", -5.5, -0.01, 0.0, "-9999999",
                              "-9999998"], "1HOUR")),
        pas=0.25),
    "zone_nommee_meme_nom_deux_zones": dict(
        u=unsteady(bloc("AMONT", [1.0, 2.0, 3.0], "1HOUR",
                        zone="Zone Orpheline"),
                   bloc("AMONT", [10.0, 20.0, 30.0], "1HOUR")),
        pas=0.5, zone=ZONE),
    "zone_non_nommee_meme_nom_deux_zones": dict(
        u=unsteady(bloc("AMONT", [1.0, 2.0, 3.0], "1HOUR",
                        zone="Zone Orpheline"),
                   bloc("AMONT", [10.0, 20.0, 30.0], "1HOUR")),
        pas=0.5),
    "hors_liste_trop_court_bloque": dict(
        u=unsteady(bloc("A1", h(4), "1HOUR"),
                   bloc("AMONT_NON_PILOTE", h(4, 5.0), "1HOUR")),
        pas=0.25, apports=["A1"], p=plan("01JAN2024,0000", "01JAN2024,0600")),
    "hors_liste_couvrant_recadence_sans_prolongement": dict(
        u=unsteady(bloc("A1", h(4), "1HOUR"),
                   bloc("AMONT_NON_PILOTE", h(8, 5.0), "1HOUR")),
        pas=0.25, apports=["A1"], p=plan("01JAN2024,0000", "01JAN2024,0600")),
    "pilote_et_autre_trop_courts": dict(
        u=unsteady(bloc("A1", [1.0, 2.0], "1HOUR"),
                   bloc("AUTRE", [3.0, 4.0], "1HOUR")),
        pas=0.5, apports=["A1"], p=plan("01JAN2024,0000", "01JAN2024,0600"),
        sans_prolongement=True),
    "pilote_seul_trop_court": dict(
        u=unsteady(bloc("A1", [1.0, 2.0], "1HOUR")),
        pas=0.5, apports=["A1"], p=plan("01JAN2024,0000", "01JAN2024,0600"),
        sans_prolongement=True),
    "orphelin_hors_geometrie": dict(
        u=unsteady(bloc("A1", h(4), "1HOUR"),
                   bloc("VIEUX", [1.0, 1.0], "30MIN")),
        pas=0.25, apports=["A1"], bc=["A1"]),
    "noms_accentues_cp1252": dict(
        u=unsteady(bloc("Écluse", h(5), "1HOUR"),
                   bloc("Forêt aval", h(3, 1.0), "30MIN")),
        pas=0.1),
    "sans_ligne_de_pente": dict(
        u=unsteady(bloc("A", [2.0, 8.0, 4.0], "1HOUR", pente=False,
                        queue=())),
        pas=0.1),
    "ecritures_de_l_intervalle": dict(
        u=unsteady(bloc("I_1HOUR", [1.0, 3.0], "1HOUR"),
                   bloc("I_60MIN", [1.0, 3.0], "60MIN"),
                   bloc("I_2HOUR", [1.0, 3.0], "2HOUR"),
                   bloc("I_1DAY", [1.0, 3.0], "1DAY"),
                   bloc("I_30MIN", [1.0, 3.0], "30MIN"),
                   bloc("I_10MIN", [1.0, 3.0, 2.0], "10MIN"),
                   bloc("I_6MIN", [1.0, 3.0], "6MIN"),
                   bloc("I_300SEC", [1.0, 3.0], "300SEC"),
                   bloc("I_1HR", [1.0, 3.0], "1HR")),
        pas=0.1),
    "aucun_apport": dict(
        u=unsteady(sortie("AVAL")), pas=0.1),
    "apport_et_sortie": dict(
        u=unsteady(bloc("A", [1.0, 4.0], "1HOUR"), sortie("AVAL")), pas=0.5),
    "intervalle_absent": dict(
        u=unsteady(bloc("A", [1.0, 2.0], "3MIN"),
                   bloc("ABIME", [3.0, 4.0], None)),
        pas=0.05, apports=["A"]),
    "intervalle_illisible": dict(
        u=unsteady(bloc("A", [1.0, 2.0], "PARFOIS")), pas=0.1),
    "pas_de_travail_absent": dict(
        u=unsteady(bloc("A", [1.0, 5.0, 2.0], "1HOUR")), pas=None),
    "pas_de_travail_non_representable": dict(
        u=unsteady(bloc("A", [1.0, 5.0], "1HOUR")), pas=0.017),
    "plan_sans_fenetre": dict(
        u=unsteady(bloc("A", [1.0, 5.0], "1HOUR")), pas=0.5, apports=["A"],
        p=plan(None)),
    "plan_absent": dict(
        u=unsteady(bloc("A", [1.0, 5.0], "1HOUR")), pas=0.5, apports=["A"],
        plan_travail="02"),
    "plan_a_l_instant_invalide": dict(
        u=unsteady(bloc("A", [1.0, 5.0], "1HOUR")), pas=0.5, apports=["A"],
        p=plan("99XYZ2024,0000", "01JAN2024,0600")),
    "fin_de_ligne_lf": dict(
        u=unsteady(bloc("A", [1.0, 5.0, 2.0], "1HOUR"), fin="\n"), pas=0.1),
    "pilote_non_commensurable_prolonge": dict(
        u=unsteady(bloc("A", [0.0, 6.0, 9.0, 3.0], "15MIN")), pas=0.1,
        apports=["A"], p=plan("01JAN2024,0000", "01JAN2024,0200")),
    "pilote_deja_au_pas_mais_trop_court": dict(
        u=unsteady(bloc("A", [1.0, 2.0, 3.0], "6MIN")), pas=0.1,
        apports=["A"], p=plan("01JAN2024,0000", "01JAN2024,0100")),
    "pilote_couvrant_deja_la_fenetre": dict(
        u=unsteady(bloc("A", h(7), "1HOUR")), pas=0.5, apports=["A"],
        p=plan("01JAN2024,0000", "01JAN2024,0300")),
    "fenetre_24h_fin_de_journee": dict(
        u=unsteady(bloc("A", h(5), "1HOUR")), pas=0.5, apports=["A"],
        p=plan("01JAN2024,0000", "01JAN2024,2400")),
    "pas_3min_condition_non_pilotee_au_mauvais_pas": dict(
        u=unsteady(bloc("APPORT_01", [10.0, 50.0, 100.0, 20.0], "1HOUR"),
                   bloc("BC_AMONT", [1.0, 2.0, 3.0], "3MIN"),
                   bloc("BC_MAUVAIS", [5.0, 6.0, 7.0], "6MIN")),
        pas=0.05, apports=["APPORT_01"]),
}


def _pilote(dossier, cas):
    """Un pilote dans l'etat ou preparer() le laisse avant de recadencer."""
    dossier.mkdir(parents=True, exist_ok=True)
    u = dossier / "ESSAI.u02"
    u.write_bytes(cas["u"])
    if "p" in cas:
        (dossier / "ESSAI.p02").write_bytes(cas["p"])
    p = ph.PiloteHecRas(dossier, "ESSAI", plan_reference="01",
                        nom_zone_2d=cas.get("zone"),
                        pas_travail_h=cas.get("pas"),
                        apports_a_caler=cas.get("apports"))
    if "p" in cas or "plan_travail" in cas:
        p.plan_travail = cas.get("plan_travail", "02")
    if "bc" in cas:
        p.objets_geometrie = (frozenset(), frozenset(cas["bc"]))
    p.fichier_unsteady = u
    p.carte = ph.cartographier_hydrogrammes(u, p.nom_zone_2d,
                                            p._bc_lines_connues())
    return p


def jouer_recadence(nom, dossier):
    """Joue un cas ; rend tout ce qu'on en observe."""
    cas = CAS_RECADENCE[nom]
    p = _pilote(dossier, cas)
    if cas.get("sans_prolongement"):
        # Le prolongement par des zeros ne peut echouer ici : on le neutralise
        # pour atteindre la branche « apport pilote encore trop court » du
        # message, que le pilote n'atteint qu'apres un tel echec.
        vraie = ph.imposer_intervalle_apport

        def sans_prolongement(*a, **k):
            k["duree_min_h"] = None
            return vraie(*a, **k)
        ph.imposer_intervalle_apport = sans_prolongement
    sortie_std = io.StringIO()
    retour, exception = None, None
    try:
        with contextlib.redirect_stdout(sortie_std):
            retour = p._recadencer_apports()
    except Exception as e:                                  # noqa: BLE001
        exception = f"{type(e).__name__}: {e}"
    finally:
        if cas.get("sans_prolongement"):
            ph.imposer_intervalle_apport = vraie
    octets = p.fichier_unsteady.read_bytes()
    return {
        "retour": retour,
        "exception": exception,
        "journal": sortie_std.getvalue().splitlines(),
        "carte": p.carte,
        "inchange": octets == cas["u"],
        "sha256": hashlib.sha256(octets).hexdigest(),
        "taille": len(octets),
        "texte": octets.decode("latin-1") if len(octets) <= TEXTE_MAX else None,
    }


# ---------------------------------------------------------------------------
# Fabrication des HDF de resultats et des journaux de calcul
# ---------------------------------------------------------------------------

CLE = "Results/Summary/Compute Messages (text)"
CLE_2 = "Results/Summary/Compute Messages"
TABLEAU = ["Computation Task\tTime(hh:mm:ss)",
           "Completing Geometry, Flow and Plan\t      25",
           "Unsteady Flow Computations\t<1", "Complete Process\t25",
           "Computation Speed\tSimulation/Runtime",
           "Unsteady Flow Computations\t617968x"]
EN_TETE = ["Plan: 'sans apport' (ESSAI.p01)",
           "Simulation started at: 31Aug2026 12:22:00 PM"]
SERVEUR = ["Current executing directory: C:\\x", "Server: started",
           "Starting async read", "Client connected"]


def _texte(lignes):
    return ("\r\n".join(lignes) + "\r\n").encode("utf-8")


# Chaque cas : {"hdf": {cle: donnee} | "absent" | octets bruts,
#               "nom": nom du .hdf, "journaux": {nom: (octets|"dossier", mtime)}}
CAS_MESSAGES = {
    "messages_normaux_quatre_dernieres": dict(hdf={CLE: _texte(
        EN_TETE + ["Writing Geometry...", "Ligne 1", "Ligne 2", "Ligne 3",
                   "Ligne 4", "Ligne 5"])}),
    "erreur_avant_le_tableau_des_temps": dict(hdf={CLE: _texte(
        EN_TETE + ["Computing 2D Flow Area tables: Associated terrain has "
                   "been updated", "Geometry Writer Failed",
                   "Error Processing Geometry"] + TABLEAU)}),
    "tableau_seul": dict(hdf={CLE: _texte(EN_TETE + TABLEAU)}),
    "jeu_de_donnees_absent": dict(hdf={"Results/Summary/Autre": b"x"}),
    "groupe_absent": dict(hdf={}),
    "octets_invalides": dict(hdf={CLE: b"Erreur \xe9cluse \xff\xfe\r\nFin"}),
    "messages_vides": dict(hdf={CLE: b""}),
    "lignes_blanches_seules": dict(hdf={CLE: b"  \r\n\r\n   \n"}),
    "tableau_d_octets": dict(hdf={CLE: np.array(
        [b"Plan: x", b"Erreur A", b"Erreur B", b"Computation Task\t1"])}),
    "tableau_de_chaines_variables": dict(hdf={CLE: "vlen", }),
    "tableau_de_nombres": dict(hdf={CLE: np.array([[1, 2], [3, 4]])}),
    "seconde_cle_seule": dict(hdf={CLE_2: _texte(["Erreur sur la seconde cle"])}),
    "premiere_cle_vide_seconde_parlante": dict(hdf={
        CLE: _texte(EN_TETE), CLE_2: _texte(["La seconde explique"])}),
    "fichier_absent": dict(hdf="absent"),
    "fichier_absent_journal_present": dict(hdf="absent", journaux={
        "_compute_p01.log": (_texte(SERVEUR + ["Geometry Writer Failed",
                                               "Error Processing Geometry",
                                               "Fin du compte rendu"]
                                    + TABLEAU), 1_700_000_000)}),
    "journal_quatre_lignes_garde_trois": dict(hdf="absent", journaux={
        "_compute_p01.log": (_texte(["L1", "L2", "L3", "L4"]), 1_700_000_000)}),
    "journal_serveur_seul_puis_autre_journal": dict(hdf="absent", journaux={
        "_compute_p01.log": (_texte(SERVEUR), 1_700_000_300),
        "_compute_p07.log": (_texte(["Ancien message"]), 1_700_000_100),
        "_compute_p09.log": (_texte(["Message recent"]), 1_700_000_200)}),
    "journal_du_plan_avant_un_plus_recent": dict(hdf="absent", journaux={
        "_compute_p01.log": (_texte(["Celui du plan"]), 1_700_000_100),
        "_compute_p03.log": (_texte(["Un autre, plus recent"]),
                             1_700_000_200)}),
    "journal_tableau_seul": dict(hdf="absent", journaux={
        "_compute_p01.log": (_texte(TABLEAU), 1_700_000_000)}),
    "journal_vide": dict(hdf="absent", journaux={
        "_compute_p01.log": (b"", 1_700_000_000)}),
    "journal_illisible_un_dossier": dict(hdf="absent", journaux={
        "_compute_p01.log": ("dossier", 1_700_000_300),
        "_compute_p05.log": (_texte(["Lisible"]), 1_700_000_100)}),
    "journal_cp1252": dict(hdf="absent", journaux={
        "_compute_p01.log": ("Écluse refusée\r\n".encode("cp1252"),
                             1_700_000_000)}),
    "hdf_corrompu_journal_present": dict(hdf=b"ceci n'est pas un HDF", journaux={
        "_compute_p01.log": (_texte(["Depuis le journal"]), 1_700_000_000)}),
    "hdf_muet_journal_present": dict(hdf={CLE: _texte(TABLEAU)}, journaux={
        "_compute_p01.log": (_texte(["Le journal parle"]), 1_700_000_000)}),
    "hdf_sans_numero_de_plan": dict(hdf="absent", nom="ESSAI.hdf", journaux={
        "_compute_phdf.log": (_texte(["Nom derive du suffixe"]),
                              1_700_000_000)}),
}


def jouer_messages(nom, dossier):
    cas = CAS_MESSAGES[nom]
    dossier.mkdir(parents=True, exist_ok=True)
    hdf = dossier / cas.get("nom", "ESSAI.p01.hdf")
    donnees = cas["hdf"]
    if isinstance(donnees, bytes):
        hdf.write_bytes(donnees)
    elif donnees != "absent":
        with h5py.File(hdf, "w") as f:
            for cle, valeur in donnees.items():
                if isinstance(valeur, bytes):
                    f.create_dataset(cle, data=np.bytes_(valeur))
                elif isinstance(valeur, str):            # « vlen »
                    f.create_dataset(cle, data=["Plan: y", "Erreur variable",
                                                "Simulation started at: z"],
                                     dtype=h5py.string_dtype())
                else:
                    f.create_dataset(cle, data=valeur)
            if not donnees:
                f.create_group("Results")
    for nom_journal, (contenu, mtime) in cas.get("journaux", {}).items():
        chemin = dossier / nom_journal
        if contenu == "dossier":
            chemin.mkdir()
        else:
            chemin.write_bytes(contenu)
        os.utime(chemin, (mtime, mtime))
    return ph._messages_hecras(hdf)


# ---------------------------------------------------------------------------
# La reference
# ---------------------------------------------------------------------------

def _socle():
    return {"python": platform.python_version(), "numpy": np.__version__,
            "systeme": platform.system(), "machine": platform.machine(),
            "ras_commander": getattr(sys.modules.get("ras_commander"),
                                     "__version__", None)}


def _meme_socle(produit_par):
    ici = _socle()
    return all(produit_par.get(c) == ici[c]
               for c in ("numpy", "systeme", "machine"))


def _ecrire_reference(dossier):
    def ligne(objet):
        return json.dumps(objet, ensure_ascii=False)

    recadence = ",\n".join(
        f"  {ligne(nom)}: {ligne(jouer_recadence(nom, dossier / 'r' / nom))}"
        for nom in CAS_RECADENCE)
    messages = ",\n".join(
        f"  {ligne(nom)}: {ligne(jouer_messages(nom, dossier / 'm' / nom))}"
        for nom in CAS_MESSAGES)
    a_propos = (
        "Filet de PiloteHecRas._recadencer_apports et de _messages_hecras. NE "
        "PAS MODIFIER A LA MAIN : « python src/test_pilote_recadence.py "
        "--figer » le reecrit, quand le changement de comportement est VOULU.")
    REFERENCE.write_text(
        "{\n"
        f' "_a_propos": {ligne(a_propos)},\n'
        f' "_produit_par": {ligne(_socle())},\n'
        f' "recadence": {{\n{recadence}\n }},\n'
        f' "messages": {{\n{messages}\n }}\n}}\n', encoding="utf-8")


@pytest.fixture(scope="module")
def reference():
    assert REFERENCE.is_file(), (
        f"{REFERENCE.name} absent — le creer par "
        f"« python src/test_pilote_recadence.py --figer »")
    return json.loads(REFERENCE.read_text(encoding="utf-8"))


def _tableau_proche(obtenu, attendu):
    """Hors socle : memes lignes, debits a 0,01 pres dans les tableaux."""
    lo, la = obtenu.splitlines(), attendu.splitlines()
    if len(lo) != len(la):
        return False
    for o, a in zip(lo, la):
        if o == a:
            continue
        try:
            vo = [float(o[i:i + 8]) for i in range(0, len(o), 8)]
            va = [float(a[i:i + 8]) for i in range(0, len(a), 8)]
        except ValueError:
            return False
        if len(vo) != len(va) or any(abs(x - y) > 0.0101
                                     for x, y in zip(vo, va)):
            return False
    return True


def test_la_reference_couvre_les_cas_et_eux_seuls(reference):
    assert list(reference["recadence"]) == list(CAS_RECADENCE)
    assert list(reference["messages"]) == list(CAS_MESSAGES)


@pytest.mark.skipif(not RAS_COMMANDER, reason="ras_commander absent")
@pytest.mark.parametrize("nom", list(CAS_RECADENCE))
def test_recadencer_fait_exactement_ce_que_la_reference_a_enregistre(
        nom, reference, tmp_path):
    obtenu = jouer_recadence(nom, tmp_path)
    attendu = reference["recadence"][nom]
    if _meme_socle(reference["_produit_par"]):
        assert json.loads(json.dumps(obtenu, ensure_ascii=False)) == attendu
        return
    warnings.warn(f"reference produite sous {reference['_produit_par']}, ici "
                  f"{_socle()} : debits compares a 0,01 pres")
    for cle in ("exception", "journal", "carte", "inchange", "taille"):
        assert json.loads(json.dumps(obtenu[cle])) == attendu[cle], cle
    if attendu["texte"] is not None:
        assert _tableau_proche(obtenu["texte"], attendu["texte"])


@pytest.mark.skipif(h5py is None, reason="h5py absent")
@pytest.mark.parametrize("nom", list(CAS_MESSAGES))
def test_messages_hecras_rend_ce_que_la_reference_a_enregistre(
        nom, reference, tmp_path):
    assert jouer_messages(nom, tmp_path) == reference["messages"][nom]


# ---------------------------------------------------------------------------
# Les invariants physiques, verifies hors reference
# ---------------------------------------------------------------------------

def _valeurs_et_pas(fichier, nom, zone):
    carte = ph.cartographier_hydrogrammes(fichier, zone)
    info = carte[nom]
    return (ph.lire_hydrogramme_unsteady(fichier, info["debut"], info["fin"]),
            info["intervalle_h"])


def _volume_exact(valeurs, pas, jusqu_a):
    """
    Integrale de la serie LUE COMME HEC-RAS LA LIT : lineaire entre ses
    points, tenue a sa derniere valeur au-dela, de 0 a « jusqu_a » heures.
    Exacte : la grille d'integration contient tous les points de la serie.
    """
    t = np.arange(len(valeurs)) * pas
    grille = np.union1d(t[t < jusqu_a], [jusqu_a])
    y = np.interp(grille, t, valeurs)
    return float(np.sum((y[1:] + y[:-1]) / 2 * np.diff(grille)))


def _commensurable(pas_avant, pas_apres):
    rapport = pas_avant / pas_apres
    return pas_apres <= pas_avant and abs(rapport - round(rapport)) < 1e-9


# LE VOLUME, CE QUI EST CONSTATE (10/11/2026). Reference : la serie
# d'origine lue comme HEC-RAS la lit, integree sur la duree couverte APRES
# re-cadencage (queue tenue comprise).
#   - PAS DE TRAVAIL DIVISEUR ENTIER DU PAS D'ORIGINE (1 h -> 6 min, 30 min
#     -> 6 min, 1 h -> 15 min, 1 jour -> 6 min) : la serie reecrite passe
#     par TOUS les points d'origine, c'est la meme courbe. Seul reste
#     l'arrondi d'ecriture au centieme : |dV| <= 0,005 x duree. Ecart
#     constate : 0 a 4e-5 en relatif.
#   - PAS NON COMMENSURABLE (15 -> 6 min, 10 -> 6 min, 5 -> 6 min) OU PLUS
#     GROSSIER (6 -> 30 min) : un point d'origine qui tombe entre deux
#     points neufs est « coupe ». Borne assertee, et non une marge choisie :
#     sur chaque pas neuf, la serie reecrite et l'origine restent dans
#     l'amplitude de l'origine sur ce pas, d'ou |dV| <= pas neuf x variation
#     totale de la serie (+ l'arrondi). Ecarts constates : voir le rapport
#     du filet ; le pire est une serie de DEUX valeurs a 5 min, dont la rampe
#     est etiree jusqu'au pas de 6 min suivant (7,7 %).
#   - PROLONGEMENT PAR DES ZEROS (apports pilotes plus courts que la
#     simulation) : la reference est alors la serie prolongee, qui descend
#     en un pas d'origine de sa derniere valeur a zero. Par rapport a la
#     serie d'origine sur SA duree, le volume gagne ce triangle (constate :
#     jusqu'a 37 % sur une serie de trois valeurs). Sans consequence : le
#     calage remet ces apports a zero puis les reecrit entierement.


@pytest.mark.skipif(not RAS_COMMANDER, reason="ras_commander absent")
@pytest.mark.parametrize("nom", list(CAS_RECADENCE))
def test_invariants_physiques(nom, tmp_path):
    cas = CAS_RECADENCE[nom]
    origine = tmp_path / "origine.u02"
    origine.write_bytes(cas["u"])
    obtenu = jouer_recadence(nom, tmp_path / "jeu")
    fichier = tmp_path / "jeu" / "ESSAI.u02"
    for cr in obtenu["retour"] or []:
        avant, pas_avant = _valeurs_et_pas(origine, cr["nom"], cr["zone"])
        apres, pas_apres = _valeurs_et_pas(fichier, cr["nom"], cr["zone"])
        assert pas_avant == cr["intervalle_avant_h"]
        assert len(apres) == cr["nb_apres"]
        duree_origine = (len(avant) - 1) * pas_avant
        duree_apres = (len(apres) - 1) * pas_apres
        # LA DUREE : jamais raccourcie, allongee de moins d'un pas.
        assert cr["duree_h"] >= duree_origine - 1e-9
        assert cr["duree_h"] - 1e-9 <= duree_apres < cr["duree_h"] + pas_apres
        prolonge = cr["duree_h"] > duree_origine + 1e-9
        serie = (np.concatenate([avant, np.zeros(cr["nb_avant"] - len(avant))])
                 if prolonge else avant)
        # LE VOLUME, sur la duree couverte apres re-cadencage.
        v_avant = _volume_exact(serie, pas_avant, duree_apres)
        v_apres = _volume_exact(apres, pas_apres, duree_apres)
        arrondi = 0.005 * duree_apres + 1e-9
        if _commensurable(pas_avant, pas_apres):
            assert abs(v_apres - v_avant) <= arrondi, (cr["nom"], v_avant,
                                                       v_apres)
            # et les valeurs d'origine, A LEURS INSTANTS, au centieme
            k = int(round(pas_avant / pas_apres))
            assert np.allclose(apres[::k][:len(serie)], serie, atol=0.0051)
        else:
            variation = float(np.sum(np.abs(np.diff(serie))))
            assert abs(v_apres - v_avant) <= pas_apres * variation + arrondi, (
                cr["nom"], v_avant, v_apres)


if __name__ == "__main__":
    if "--figer" in sys.argv:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            _ecrire_reference(Path(d))
        print(f"REFERENCE REECRITE : {REFERENCE.name} "
              f"({REFERENCE.stat().st_size / 1024:.0f} ko, "
              f"{len(CAS_RECADENCE)} + {len(CAS_MESSAGES)} cas). Relire le "
              f"diff avant de committer.")
    else:
        raise SystemExit(pytest.main([__file__, "-q"]))
