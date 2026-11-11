"""
Relire un refigeage : ce qui a change dans une reference, cas par cas.

Les filets de caracterisation (src/test_*.py) comparent le comportement a une
reference figee (src/reference_*.json). Quand un changement est VOULU, on
refige — et le diff d'un JSON de 1,7 Mo ne se relit pas a l'oeil. Cet outil le
relit : pour chaque reference, les cas qui ont bouge, ce qui y a ete retire,
ajoute ou modifie, et surtout SI DES NOMBRES ONT CHANGE.

    python tools/comparer_references.py                 # tout ce qui differe de HEAD
    python tools/comparer_references.py --base main     # par rapport a main
    python tools/comparer_references.py src/reference_diagnostic.json
    python tools/comparer_references.py --strict        # code 1 si un nombre a change

LA REGLE DU DEPOT : on ne refige que les cas dont le changement est voulu, et
on le PROUVE. Un correctif de message ne doit modifier aucun nombre ; si
l'outil en montre un, c'est le correctif qu'il faut relire, pas la reference.

POURQUOI LES REFERENCES NE SONT PAS « ALLEGEES » (decision du 11/11/2026).
Elles pesent 4,5 Mo de texte, mais 0,34 Mo une fois compressees, et c'est ce
que git garde. Les reduire (empreintes a la place des contenus, fichiers
compresses) ferait gagner peu et perdre l'essentiel : un filet qui dit CE QUI
a change. Ce qui coute, dans une reference, ce n'est pas son poids, c'est de
relire son diff — d'ou cet outil.
"""
import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
FLOTTANT_FIGE = re.compile(r"-?0x[0-9a-f.]+p[+-]\d+")


def feuilles(valeur, chemin=()):
    """{chemin: feuille} d'un JSON ; une liste ou un objet vide est une feuille."""
    if isinstance(valeur, dict) and valeur:
        for cle, sous in valeur.items():
            yield from feuilles(sous, chemin + (str(cle),))
    elif isinstance(valeur, list) and valeur:
        for rang, sous in enumerate(valeur):
            yield from feuilles(sous, chemin + (f"[{rang}]",))
    else:
        yield chemin, valeur


def est_un_nombre(valeur):
    """Un nombre, ou un nombre fige en texte par un filet : « f:0x1.8p+1 »,
    un flottant hexadecimal, l'empreinte d'un tableau (« nd:float64:400:… »)."""
    if isinstance(valeur, bool):
        return False
    if isinstance(valeur, (int, float)):
        return True
    return isinstance(valeur, str) and (
        valeur.startswith(("f:", "nd:"))
        or FLOTTANT_FIGE.fullmatch(valeur) is not None)


def cas_de(chemin):
    """Le cas auquel appartient une feuille : ses deux premiers niveaux
    (« cas / calage/nominal », « scenarios / pic_decale », « lot / [12] »)."""
    return " / ".join(chemin[:2]) if len(chemin) > 1 else (chemin or ("",))[0]


def comparer(avant, apres):
    """
    Ce qui separe deux references : {cas: {"retires", "ajoutes", "modifies",
    "nombres", "exemples"}}, pour les seuls cas qui different. Les cles qui
    commencent par « _ » (le socle ou la reference a ete figee) sont rangees
    sous le cas « _socle ».
    """
    f_avant, f_apres = dict(feuilles(avant)), dict(feuilles(apres))
    ecarts = collections.OrderedDict()
    for chemin in sorted(set(f_avant) | set(f_apres)):
        absent = object()
        a, b = f_avant.get(chemin, absent), f_apres.get(chemin, absent)
        if a is not absent and b is not absent and a == b and type(a) is type(b):
            continue
        nom = "_socle" if chemin and chemin[0].startswith("_") else cas_de(chemin)
        cas = ecarts.setdefault(nom, {"retires": 0, "ajoutes": 0,
                                      "modifies": 0, "nombres": 0,
                                      "exemples": []})
        if a is absent:
            cas["ajoutes"] += 1
        elif b is absent:
            cas["retires"] += 1
        else:
            cas["modifies"] += 1
        if any(v is not absent and est_un_nombre(v) for v in (a, b)):
            cas["nombres"] += 1
        if len(cas["exemples"]) < 3:
            cas["exemples"].append((
                " / ".join(chemin[2:]) or "(le cas lui-meme)",
                None if a is absent else a, None if b is absent else b))
    return ecarts


def _court(valeur, largeur=70):
    if valeur is None:
        return "—"
    texte = json.dumps(valeur, ensure_ascii=False)
    return texte if len(texte) <= largeur else texte[:largeur - 1] + "…"


def rapport(nom, avant, apres):
    """Les lignes a afficher pour une reference ; (lignes, nombres modifies)."""
    ecarts = comparer(avant, apres)
    def cas(reference):
        return {cas_de(c) for c, _ in feuilles(reference)
                if not (c and c[0].startswith("_"))}

    cas_avant, cas_apres = cas(avant), cas(apres)
    nombres = sum(e["nombres"] for n, e in ecarts.items() if n != "_socle")
    lignes = [f"== {nom} : {len(ecarts)} cas different(s) sur "
              f"{len(cas_avant | cas_apres)}"
              + (f" — {nombres} NOMBRE(S) MODIFIE(S)" if nombres else
                 " — aucun nombre modifie" if ecarts else "")]
    for cas, e in ecarts.items():
        lignes.append(
            f"   {cas} : -{e['retires']} +{e['ajoutes']} ~{e['modifies']}"
            + (f", dont {e['nombres']} nombre(s)" if e["nombres"] else ""))
        for chemin, a, b in e["exemples"]:
            lignes.append(f"      {chemin}")
            lignes.append(f"         avant : {_court(a)}")
            lignes.append(f"         apres : {_court(b)}")
    return lignes, nombres


def _version_de_git(base, fichier):
    """Le contenu du fichier a la revision « base », ou None s'il n'y est pas."""
    relatif = Path(fichier).resolve().relative_to(RACINE).as_posix()
    lu = subprocess.run(["git", "show", f"{base}:{relatif}"], cwd=RACINE,
                        capture_output=True)
    return json.loads(lu.stdout.decode("utf-8")) if lu.returncode == 0 else None


def main(arguments=None):
    lecteur = argparse.ArgumentParser(
        description="Relit un refigeage : les cas qui ont change dans les "
                    "references des filets, et si des nombres ont change.")
    lecteur.add_argument("fichiers", nargs="*",
                         help="references a relire (defaut : src/reference_*.json)")
    lecteur.add_argument("--base", default="HEAD",
                         help="revision de comparaison (defaut : HEAD)")
    lecteur.add_argument("--strict", action="store_true",
                         help="code de sortie 1 si un nombre a change")
    choix = lecteur.parse_args(arguments)
    fichiers = ([Path(f) for f in choix.fichiers]
                or sorted((RACINE / "src").glob("reference_*.json")))
    total, differents = 0, 0
    for fichier in fichiers:
        apres = json.loads(Path(fichier).read_text(encoding="utf-8"))
        avant = _version_de_git(choix.base, fichier)
        if avant is None:
            print(f"== {Path(fichier).name} : absente de {choix.base} (nouvelle)")
            differents += 1
            continue
        lignes, nombres = rapport(Path(fichier).name, avant, apres)
        if len(lignes) > 1:
            print("\n".join(lignes))
            differents += 1
        total += nombres
    if not differents:
        print(f"Aucune reference ne differe de {choix.base}.")
    elif total:
        print(f"\n{total} NOMBRE(S) MODIFIE(S), A RELIRE UN PAR UN. Un compte "
              f"(d'alertes, de lignes, d'octets) peut suivre un changement "
              f"voulu ; un RESULTAT — debit, volume, rapport, facteur — ne "
              f"doit pas bouger sans que ce soit le but du changement.")
    return 1 if (choix.strict and total) else 0


if __name__ == "__main__":
    sys.exit(main())
