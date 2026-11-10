"""Sonde du 10/11/2026 : que calcule « Ras.exe -c projet plan » selon la version de HEC-RAS ?

POURQUOI. Le 10/11/2026, lance pour p14, Ras.exe 7.0.2 a recalcule quatre autres plans du
projet Ard_aval sans ouvrir p14 (0-HECRAS, 08_constats_mesures.md). La cause n'est pas
etablie : cette sonde est faite pour la trouver. ELLE N'A PAS ENCORE TOURNE : le poste de
developpement emploie la virgule comme symbole decimal, et HEC-RAS y attend un clic.

Reproduit le lancement de PiloteHecRas (Calage des apports) sur une COPIE d'un modele :
clone d'un plan et de son unsteady par ras-commander, puis RasCmdr.compute_plan. Rien n'est
ecrit dans le modele source. A lancer avec l'interpreteur de la chaine
(%LOCALAPPDATA%\\calage_apports\\venv-hecras), HEC-RAS ferme, en 7.0.1 puis en 7.0.2.

Usage : python sonde_ligne_commande.py <modele source> <dossier de travail> <version> <cas> [plan]
  cas : clone_fin  plan clone, declare en fin de .prj (forme de ras-commander)
        liste      idem, lignes remontees dans les listes du .prj
        courant    idem clone_fin, et « Current Plan= » pointe le clone
        courant_seul  idem courant, mais « Ras.exe -c projet » SANS nommer le plan
        origine    aucun clone : calcule le plan [plan] tel quel
        origine_seul  aucun clone : [plan] devient le plan courant, « Ras.exe -c projet »
"""

import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

IMAGES = ("Ras.exe", "RasUnsteady.exe", "RasGeomPreprocess.exe", "RasProcess.exe",
          "PipeServer.exe", "RasPlotDriver.exe")
DELAI_MAX_S = 900


def pids():
    sortie = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                            text=True, errors="replace").stdout
    trouves = {}
    for ligne in sortie.splitlines():
        champs = [c.strip('"') for c in ligne.split('","')]
        if len(champs) > 1 and champs[0] in IMAGES:
            trouves[int(champs[1])] = champs[0]
    return trouves


def photo(dossier):
    etat = {}
    for f in dossier.iterdir():
        if f.is_file():
            try:
                s = f.stat()
                etat[f.name] = (s.st_mtime_ns, s.st_size)
            except OSError:
                pass
    return etat


def main():
    source, travail, version, cas = (Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3],
                                     sys.argv[4])
    plan_ref = sys.argv[5] if len(sys.argv) > 5 else "03"
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from pilote_hecras import symbole_decimal
    if symbole_decimal() not in (None, "."):
        raise SystemExit("le symbole decimal de Windows n'est pas le point : HEC-RAS "
                         "attendrait un clic au lieu de calculer")
    if travail.exists():
        raise SystemExit(f"{travail} existe deja : dossier neuf exige")
    shutil.copytree(source, travail)
    prj = next(p for p in travail.glob("*.prj") if b"Proj Title=" in p.read_bytes())
    nom = prj.stem

    from ras_commander import RasCmdr, RasPlan, init_ras_project

    init_ras_project(str(travail), version)
    plan = plan_ref
    if cas == "origine_seul":
        prj.write_bytes(re.sub(rb"(?m)^Current Plan=.*?(\r?)$",
                               b"Current Plan=p" + plan.encode() + rb"\1", prj.read_bytes()))
    elif cas != "origine":
        plan = str(RasPlan.clone_plan(plan_ref)).zfill(2)
        fichier_plan = travail / f"{nom}.p{plan}"
        texte = fichier_plan.read_bytes()
        flot_ref = re.search(rb"^Flow File=u(\d+)", texte, re.M).group(1).decode()
        flot = str(RasPlan.clone_unsteady(flot_ref)).zfill(2)
        fichier_plan.write_bytes(re.sub(rb"^Flow File=u\d+", f"Flow File=u{flot}".encode(),
                                        texte, count=1, flags=re.M))
        if cas in ("liste", "courant", "courant_seul"):
            lignes = prj.read_bytes().splitlines(keepends=True)
            if cas == "liste":
                for cle in (b"Unsteady File=u" + flot.encode(), b"Plan File=p" + plan.encode()):
                    mienne = next(l for l in lignes if l.startswith(cle))
                    lignes.remove(mienne)
                    prefixe = cle.split(b"=")[0] + b"="
                    rang = max(i for i, l in enumerate(lignes) if l.startswith(prefixe))
                    lignes.insert(rang + 1, mienne)
            else:
                lignes = [b"Current Plan=p" + plan.encode() + b"\r\n"
                          if l.startswith(b"Current Plan=") else l for l in lignes]
            prj.write_bytes(b"".join(lignes))
        init_ras_project(str(travail), version)

    print(f"=== version {version} | cas {cas} | plan demande p{plan} | dossier {travail}")
    print("--- .prj avant :", " ; ".join(
        l.strip() for l in prj.read_text(errors="replace").splitlines()
        if l.startswith(("Current Plan", "Plan File", "Unsteady File"))))

    avant, pids_avant, debut = photo(travail), pids(), time.time()
    releve, fini = {}, threading.Event()

    def observer():
        precedent = dict(avant)
        while not fini.wait(1.0):
            actuel = photo(travail)
            t = time.time() - debut
            for n, v in actuel.items():
                if precedent.get(n) != v:
                    releve.setdefault(n, [t, t])[1] = t
            for n in set(precedent) - set(actuel):
                releve.setdefault(n + " (supprime)", [t, t])[1] = t
            precedent = actuel
            if t > DELAI_MAX_S:
                print(f"!!! delai de {DELAI_MAX_S} s depasse : arret des HEC-RAS de la sonde")
                for pid in set(pids()) - set(pids_avant):
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                   capture_output=True)
                return

    fil = threading.Thread(target=observer, daemon=True)
    fil.start()
    try:
        if cas in ("courant_seul", "origine_seul"):
            # La forme de HEC-RAS 5.x : le plan courant, sans le nommer.
            ras = rf"C:\Program Files (x86)\HEC\HEC-RAS\{version}\Ras.exe"
            with open(travail / f"_compute_p{plan}.log", "w") as journal_ras:
                reussi = subprocess.run(f'"{ras}" -c "{prj}"', stdout=journal_ras,
                                        stderr=subprocess.STDOUT).returncode
        else:
            reussi = RasCmdr.compute_plan(plan, overwrite_dest=True)
    except Exception as e:                                   # noqa: BLE001
        reussi = f"{type(e).__name__}: {e}"
    duree = time.time() - debut
    # HEC-RAS 7 peut rendre la main avant la fin du solveur : on attend que plus
    # rien ne bouge pendant 20 s.
    while time.time() - debut < DELAI_MAX_S + 30:
        dernier = max((v[1] for v in releve.values()), default=0)
        if time.time() - debut - dernier > 20 and not (set(pids()) - set(pids_avant)):
            break
        time.sleep(2)
    fini.set()
    fil.join(5)

    print(f"--- compute_plan a rendu {reussi!r} apres {duree:.0f} s")
    print("--- fichiers ecrits (premiere et derniere ecriture, en s apres le lancement) :")
    for n, (t0, t1) in sorted(releve.items(), key=lambda kv: kv[1][0]):
        print(f"   {t0:6.0f} {t1:6.0f}  {n}")
    print("--- .prj apres :", " ; ".join(
        l.strip() for l in prj.read_text(errors="replace").splitlines()
        if l.startswith(("Current Plan", "Plan File", "Unsteady File"))))
    import h5py
    for hdf in sorted(travail.glob(f"{nom}.p[0-9][0-9].hdf")):
        try:
            with h5py.File(hdf, "r") as f:
                def s(v):
                    return v.decode("utf-8", "replace") if isinstance(v, bytes) else v
                u = f.get("Results/Unsteady/Summary")
                print(f"   {hdf.name} : {s(f.attrs.get('File Version'))} | "
                      f"{s(u.attrs.get('Run Time Window')) if u is not None else None} | "
                      f"{s(u.attrs.get('Solution')) if u is not None else None} | "
                      f"{'CALCULE PAR LA SONDE' if hdf.name in releve else 'non touche'}")
        except Exception as e:                               # noqa: BLE001
            print(f"   {hdf.name} : illisible ({type(e).__name__})")
    journal = travail / f"_compute_p{plan}.log"
    if journal.exists():
        print(f"--- {journal.name} : {journal.read_text(errors='replace').count('Client connected')}"
              " connexion(s) au serveur de calcul")


if __name__ == "__main__":
    main()
