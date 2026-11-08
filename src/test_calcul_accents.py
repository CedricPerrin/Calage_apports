"""
Le plan que HEC-RAS lit garde ses accents (défaut trouvé le 08/11/2026 sur Sensi).

compute_plan (ras-commander 0.99.2, RasCmdr.py l. 954 ; 0.102.0, l. 3315) appelle
TOUJOURS BcoMonitor.enable_detailed_logging avant de lancer HEC-RAS : il relit le
plan en UTF-8 errors="ignore", où un accent cp1252 DISPARAÎT (« lit mineur à 40 »
devient « lit mineur  40 »), et le réécrit dès que « Write Detailed= » n'y vaut
pas 1. PiloteHecRas.calculer l'appelait hors de _par_ras_commander, et
_retablir_octets ne reconnaissait que la forme errors="replace" (EF BF BD).

La variante « bouchon » tourne partout, CI comprise. La variante « ras-commander »
prend la vraie bibliothèque et une copie d'Aberou, là où les deux sont présents ;
Ras.exe n'est jamais lancé.
"""
import importlib
import os
import re
import shutil
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pilote_hecras  # noqa: E402

CAS_TEST = Path(os.environ.get("CALAGE_CAS_TEST", r"D:\1-Dev\2-Ressources\2.2-Cas_test"))
CLES_DU_CALCUL = (b"Write Detailed=", b"UNET D1 Cores=", b"UNET D2 Cores=", b"PS Cores=")


def _cp1252(*lignes):
    return "".join(f"{ligne}\r\n" for ligne in lignes).encode("cp1252")


def _detailler(chemin):
    """BcoMonitor.enable_detailed_logging de ras-commander 0.99.2, écrit comme sous Windows."""
    chemin = Path(chemin)
    texte = chemin.read_text(encoding="utf-8", errors="ignore")
    if "Write Detailed=" in texte:
        neuf = re.sub(r"Write Detailed=\s*\d+", "Write Detailed= 1", texte)
    elif "Run HTab=" in texte:
        neuf = texte.replace("Run HTab=", "Write Detailed= 1\nRun HTab=")
    else:
        neuf = texte + "\nWrite Detailed= 1\n"
    if neuf != texte:
        chemin.write_bytes(neuf.replace("\n", "\r\n").encode("utf-8"))


@pytest.mark.parametrize("lignes", [
    # « Write Detailed= 0 » remplacé ; une vraie ligne vide voisine de « é » seul.
    ("Plan Title=Q100", "BEGIN DESCRIPTION:", "Strickler du lit mineur à 40", "", "é",
     "END DESCRIPTION:", "Write Detailed= 0 "),
    # Ni « Write Detailed= » ni « Run HTab= » : ras-commander ajoute en fin une ligne
    # vide puis la sienne. « é » seul se lit comme cette ligne vide : elle reste vide.
    ("Plan Title=Q100", "é"),
])
def test_retablir_rend_les_accents_effaces(tmp_path, lignes):
    plan = tmp_path / "Essai.p01"
    avant = _cp1252(*lignes)
    plan.write_bytes(avant)
    _detailler(plan)

    pilote_hecras._retablir_octets(plan, avant)

    attendu = (avant.replace(b"Write Detailed= 0 ", b"Write Detailed= 1 ")
               if b"Write Detailed=" in avant else avant + b"\r\nWrite Detailed= 1\r\n")
    assert plan.read_bytes() == attendu


def _calcul_bouchonne(monkeypatch, espace, lus):
    """compute_plan 0.99.2 jusqu'au lancement de HEC-RAS : son écriture du plan."""
    plan = espace / "Essai.p01"
    plan.write_bytes(_cp1252(
        "Plan Title=Q100", "Program Version=7.01", "Geom File=g01", "Flow File=u01",
        "BEGIN DESCRIPTION:", "Strickler du lit mineur à 40", "END DESCRIPTION:",
        "UNET D2 Cores= 0 ", "DSS File=Données – crues.dss", "Write Detailed= 0 "))
    (espace / "Essai.prj").write_bytes(_cp1252("Proj Title=Étude", "Plan File=p01"))

    def coeurs(_numero, nombre, ras_object=None):     # RasPlan.set_num_cores, errors="replace"
        texte = plan.read_text(encoding="utf-8", errors="replace")
        neuf = re.sub(r"(?m)^(UNET D1 Cores|UNET D2 Cores|PS Cores)=.*$", rf"\1= {nombre}", texte)
        plan.write_bytes(neuf.replace("\n", "\r\n").encode("utf-8"))

    def compute_plan(_numero, **_reglages):
        _detailler(plan)
        lus.append(plan.read_bytes())                 # ce que HEC-RAS lirait
        return False

    module = types.ModuleType("ras_commander")
    module.RasCmdr = SimpleNamespace(compute_plan=compute_plan)
    module.RasPlan = SimpleNamespace(set_num_cores=coeurs)
    module.HdfResultsPlan = SimpleNamespace()
    bco = types.ModuleType("ras_commander.RasBco")
    bco.BcoMonitor = SimpleNamespace(enable_detailed_logging=_detailler)
    monkeypatch.setitem(sys.modules, "ras_commander", module)
    monkeypatch.setitem(sys.modules, "ras_commander.RasBco", bco)
    return "Essai", "01"


def _calcul_reel(monkeypatch, espace, lus):
    """Le vrai compute_plan sur une copie d'Aberou ; Ras.exe n'est jamais lancé."""
    ras_commander = pytest.importorskip("ras_commander", reason="interpréteur HEC-RAS seulement")
    source = CAS_TEST / "Aberou"
    if not (source / "Modele_Aberou.p07").is_file():
        pytest.skip(f"modèle de test Aberou absent ({source})")
    for fichier in source.glob("Modele_Aberou.*"):
        if re.fullmatch(r"\.(prj|[pgu]\d\d)", fichier.suffix):
            shutil.copy(fichier, espace / fichier.name)
    plan = espace / "Modele_Aberou.p07"
    # p07 porte « à » dans sa description ; dans la copie seulement, un chemin DSS
    # accentué de plus.
    plan.write_bytes(plan.read_bytes().replace(
        b"DSS File=dss", "DSS File=Données – crues.dss".encode("cp1252")))

    module = importlib.import_module("ras_commander.RasCmdr")
    faux = types.ModuleType("subprocess")
    faux.__dict__.update(vars(module.subprocess))

    def lancer(*_commande, **_options):            # run (0.99.2) ou Popen (0.102.0)
        lus.append(plan.read_bytes())
        raise OSError("les tests ne lancent jamais Ras.exe")

    faux.run = faux.Popen = lancer
    monkeypatch.setattr(module, "subprocess", faux)
    # Le chien de garde clique « Oui » dans les boîtes de tout Ras.exe ouvert sur le
    # poste (psutil présent) : il ne démarre pas pendant le test.
    garde = importlib.import_module("ras_commander.RasDialogWatchdog")
    monkeypatch.setattr(garde, "DialogWatchdog", lambda *_a, **_k: SimpleNamespace(
        start=lambda: None, stop=lambda: None, add_pid=lambda _pid: None))
    ras_commander.init_ras_project(str(espace), "7.0.1")
    return "Modele_Aberou", "07"


@pytest.mark.parametrize("bibliotheque", ["bouchon", "ras-commander"])
def test_hecras_lit_le_plan_avec_ses_accents(tmp_path, monkeypatch, bibliotheque):
    espace = tmp_path / "Espace"
    espace.mkdir()
    lus = []
    preparer = _calcul_bouchonne if bibliotheque == "bouchon" else _calcul_reel
    nom, numero = preparer(monkeypatch, espace, lus)
    plan = espace / f"{nom}.p{numero}"
    avant = plan.read_bytes()
    pilote = pilote_hecras.PiloteHecRas(espace, nom, numero, fermer_orphelins=False, coeurs=2)
    pilote.plan_travail = numero
    pilote.hdf_resultats = espace / f"{nom}.p{numero}.hdf"

    pilote.calculer()

    assert len(lus) == 1, "le calcul n'est pas allé jusqu'au lancement de HEC-RAS"
    lu = lus[0].splitlines(keepends=True)
    # Les lignes que le calcul ne règle pas : à l'octet, accents en cp1252.
    perdues = [ligne for ligne in avant.splitlines(keepends=True)
               if not ligne.startswith(CLES_DU_CALCUL) and ligne not in lu]
    assert perdues == []
    assert b"\xef\xbf\xbd" not in lus[0]
    assert any(ligne.startswith(b"Write Detailed= 1") for ligne in lu)
    assert any(ligne.startswith(b"UNET D2 Cores= 2") for ligne in lu)
