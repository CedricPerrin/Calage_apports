"""
Les bancs embarques, vus de pytest : UNE commande joue tout.

Decision du 11/11/2026 (vue « long terme, partage ») : les bancs de la chaine
(src/bancs/banc_*.py, celui du noyau du plugin, l'autotest du pont) NE SONT
PAS REECRITS en pytest. Ce sont 6 700 lignes de scenarios qui se suivent et
partagent leur etat ; les reecrire couterait cher, pour un risque reel et
aucun controle de plus. Ils sont EXPOSES a pytest : chaque banc devient un
test, qui le lance comme le lance la CI, compte ses [OK] et ses [ECHEC], et
nomme ceux qui echouent. Celui qui arrive sur le depot lance « pytest src »
et voit tout ; il n'a pas a savoir qu'il existe des bancs.

    python -m pytest src/test_bancs.py -v

CE QUE CHAQUE TEST EXIGE D'UN BANC :
  - aucun [ECHEC] (hors ceux, nommes ci-dessous, qui tiennent au poste) ;
  - le code de sortie 0 ;
  - AU MOINS le nombre de controles releve le 11/11/2026 : un banc qui
    s'arreterait en chemin sans rien dire ferait moins de controles, pas des
    controles faux.

UN BANC DONT LES DEPENDANCES MANQUENT EST SAUTE, et le dit : geometrie, le
pont et le pilote demandent h5py et ras-commander, absents du job « noyau »
de la CI et inutilisables sous QGIS.

LES NOUVEAUX TESTS S'ECRIVENT EN pytest, directement (src/test_*.py) : on
n'ajoute plus de controle a un banc.
"""
import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
CONTROLE = re.compile(r"^\s*\[(OK|ECHEC)\]\s*(.*)$")

# Le pilote, hors de Windows : ces controles tiennent au poste, pas au code.
# Les deux derniers interrogent les processus de Windows. Les quatre premiers
# passent avec un ras-commander recent (0.117) et echouent avec la 0.99.2
# sous Linux, qui n'y ecrit ni les fins de ligne ni l'encodage de Windows.
PILOTE_HORS_WINDOWS = {
    "ras-commander : le .prj garde chaque octet, ses lignes neuves en cp1252 "
    "et CRLF",
    "ras-commander : la geometrie clonee ne change que son titre, BC line "
    "« Écluse » et « Forêt » comprises",
    "ras-commander : le plan de l'etape garde titre et description "
    "accentues, coeurs ecrits",
    "un plan que le .prj ne declare plus n'est pas lance",
    "un calcul deja en cours au lancement n'arrete pas le notre",
    "un reste de calcul recree avec sa vieille date n'arrete pas le notre",
}

HDF = ("h5py", "ras_commander")

# nom : (commande depuis la racine, controles au minimum, modules exiges,
#        echecs toleres hors de Windows)
BANCS = {
    "criteres": (["src/criteres.py"], 87, (), ()),
    "calage": (["src/calage.py"], 141, (), ()),
    "controle_donnees": (["src/controle_donnees.py"], 6, (), ()),
    "suivi": (["src/suivi.py"], 55, (), ()),
    "livrables": (["src/livrables.py"], 16, (), ()),
    "parametres": (["src/parametres.py"], 12, (), ()),
    "style_classeur": (["src/style_classeur.py"], 13, (), ()),
    "noyau": (["calage_apports/noyau.py"], 57, (), ()),
    "geometrie": (["src/geometrie.py"], 33, HDF, ()),
    "pont": (["src/pont_hecras.py", "autotest"], 27, HDF, ()),
    "pilote_hecras": (["src/pilote_hecras.py"], 209, HDF,
                      PILOTE_HORS_WINDOWS),
}


def _absents(modules):
    """Ceux de ces modules que cet interpreteur ne sait pas importer —
    absents, ou presents mais inutilisables (h5py sous le Python de QGIS)."""
    absents = []
    for module in modules:
        try:
            importlib.import_module(module)
        except Exception:                                   # noqa: BLE001
            absents.append(module)
    return absents


def jouer(commande):
    """Lance un banc comme la CI ; rend (code, controles, sortie)."""
    execution = subprocess.run(
        [sys.executable, *commande], cwd=RACINE, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=900,
        env=dict(os.environ, MPLBACKEND="Agg", PYTHONIOENCODING="utf-8"))
    sortie = execution.stdout + execution.stderr
    controles = [(m.group(1), m.group(2).split("  ->  ")[0].strip())
                 for m in map(CONTROLE.match, sortie.splitlines()) if m]
    return execution.returncode, controles, sortie


@pytest.mark.parametrize("nom", sorted(BANCS))
def test_le_banc_passe(nom):
    commande, minimum, exiges, toleres = BANCS[nom]
    manquants = _absents(exiges)
    if manquants:
        pytest.skip(f"banc {nom} : {', '.join(manquants)} inutilisable(s) "
                    f"dans cet interpreteur")

    code, controles, sortie = jouer(commande)

    echecs = [libelle for etat, libelle in controles if etat == "ECHEC"]
    if sys.platform != "win32":
        echecs = [e for e in echecs if e not in toleres]
    fin = "\n".join(sortie.splitlines()[-15:])
    assert not echecs, (
        f"banc {nom} : {len(echecs)} controle(s) en echec :\n  - "
        + "\n  - ".join(echecs) + f"\n\nFin de sa sortie :\n{fin}")
    assert len(controles) >= minimum, (
        f"banc {nom} : {len(controles)} controle(s) joue(s), {minimum} "
        f"attendus au moins — il s'est arrete en chemin.\n\n"
        f"Fin de sa sortie :\n{fin}")
    if not (toleres and sys.platform != "win32"):
        assert code == 0, (
            f"banc {nom} : code de sortie {code} sans [ECHEC].\n\n"
            f"Fin de sa sortie :\n{fin}")


def test_un_echec_tolere_est_un_controle_qui_existe():
    """Un libelle renomme dans le banc ne doit pas rester tolere pour rien."""
    commande, _, exiges, toleres = BANCS["pilote_hecras"]
    if _absents(exiges):
        pytest.skip("h5py ou ras-commander inutilisable dans cet interpreteur")

    _, controles, _ = jouer(commande)

    inconnus = set(toleres) - {libelle for _, libelle in controles}
    assert not inconnus, f"tolere(s) mais introuvable(s) : {sorted(inconnus)}"
