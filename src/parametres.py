"""
Parametres d'un calage : un fichier JSON a cote du classeur.

POURQUOI PLUS UNE FEUILLE DU CLASSEUR (20 septembre 2026, demande
utilisateur). Les parametres vivaient dans une feuille « Parametres » de
l'Excel des objectifs. AUCUN n'y est saisi a la main quand on passe par le
plugin : la fenetre les ecrit tous a la composition du paquet, et le seul
qui change ensuite — « Premier_apport » — est ecrit au lancement. La feuille
etait donc la premiere chose vue en ouvrant un classeur ou l'on ne vient que
coller des hydrogrammes, et la seule qu'on n'y touche jamais.

CE QUE LE CLASSEUR GARDE : « Correspondance » et « Cibles ». Ce sont les deux
feuilles ou l'on ECRIT.

LE FICHIER PORTE LE NOM DU CLASSEUR, extension .json :
« donnees_calage_Q100.xlsx » -> « donnees_calage_Q100.json ». Deux scenarios
d'un meme dossier de sortie gardent donc deux jeux de parametres, exactement
comme ils gardent deux classeurs depuis la 0.8.4. Le couple se deplace d'un
poste a l'autre a condition de deplacer LES DEUX fichiers : lire() le dit
quand le JSON manque.

UN JSON, PAS UN .ini NI UN .csv. Les valeurs sont des nombres, des chaines et
des vides ; JSON rend un vide comme « null » et un nombre comme un nombre,
la ou un .ini rendrait tout en chaine et obligerait chaque appelant a
reconvertir — c'est-a-dire a se tromper un jour sur deux.

COMPATIBILITE : un classeur compose AVANT le 20 septembre 2026 n'a pas de
JSON et porte encore sa feuille. lire() la lit alors, sans rien dire de plus
qu'une mention dans « origine » : un calage en cours ne doit pas s'arreter
parce que l'outil a change d'avis sur le rangement de ses parametres.
"""

import json
from pathlib import Path

# Nom de la feuille des classeurs d'avant. Elle n'est plus ECRITE nulle part ;
# elle est encore LUE, pour les classeurs qui l'ont.
FEUILLE_HERITEE = "Parametres"


def chemin(chemin_classeur):
    """Le JSON qui accompagne ce classeur, qu'il existe ou non."""
    return Path(chemin_classeur).with_suffix(".json")


def lire(chemin_classeur):
    """
    Parametres du calage, en dictionnaire {cle: valeur}.

    Les vides sont rendus None — un appelant ecrit « if valeur is None » sans
    importer pandas.

    Rend un dictionnaire VIDE si ni le JSON ni la feuille heritee n'existent :
    c'est aux controles de dire ce qui manque, avec leurs mots. Lever ici
    remplacerait « Nom_zone_2D absent » par une trace de pile.
    """
    fichier = chemin(chemin_classeur)
    if fichier.is_file():
        with fichier.open(encoding="utf-8") as f:
            valeurs = json.load(f)
        return {str(c).strip(): v for c, v in valeurs.items()}
    return _lire_feuille_heritee(chemin_classeur)


def _lire_feuille_heritee(chemin_classeur):
    """La feuille « Parametres » d'un classeur d'avant, ou rien."""
    import pandas as pd

    try:
        par = pd.read_excel(chemin_classeur, sheet_name=FEUILLE_HERITEE)
    except Exception:                                       # noqa: BLE001
        # Classeur absent, illisible, ou sans cette feuille — les trois cas
        # veulent la meme reponse : « pas de parametres ici ».
        return {}
    if "Parametre" not in par.columns or "Valeur" not in par.columns:
        return {}
    return {str(c).strip(): (None if v is None or pd.isna(v) else v)
            for c, v in zip(par["Parametre"], par["Valeur"])}


def origine(chemin_classeur):
    """« json », « feuille » ou « aucune » — pour le dire a l'ecran."""
    if chemin(chemin_classeur).is_file():
        return "json"
    return "feuille" if _lire_feuille_heritee(chemin_classeur) else "aucune"


def ecrire(chemin_classeur, valeurs):
    """
    Ecrit TOUS les parametres, et rend le chemin du fichier.

    Les valeurs que JSON ne sait pas porter — un Timestamp pandas, un NaN —
    sont rendues en chaine ou en None : le fichier doit toujours se relire,
    et une composition perdue fait recommencer tout le parametrage.
    """
    fichier = chemin(chemin_classeur)
    fichier.write_text(
        json.dumps({str(c).strip(): _portable(v) for c, v in valeurs.items()},
                   ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8")
    return fichier


def ecrire_un(chemin_classeur, cle, valeur):
    """
    Change UN parametre sans toucher aux autres.

    Sert aux reglages qui se decident AU LANCEMENT et non a la composition —
    « Premier_apport » en premier lieu : choisir par ou reprendre ne doit pas
    obliger a recomposer tout le paquet.

    Une cle inconnue est AJOUTEE plutot que refusee : un classeur compose par
    une version anterieure peut ne pas la porter, et perdre le reglage en
    silence serait pire que l'ecrire.
    """
    valeurs = lire(chemin_classeur)
    valeurs[str(cle).strip()] = valeur
    ecrire(chemin_classeur, valeurs)
    return True


def _portable(valeur):
    """Ce que json.dumps sait ecrire, sans rien perdre d'utile."""
    if valeur is None or isinstance(valeur, (str, int, float, bool)):
        # NaN et les infinis passent le test isinstance : json les ecrirait
        # « NaN », que json.load relit mais qu'aucun autre lecteur n'accepte.
        if isinstance(valeur, float) and valeur != valeur:
            return None
        return valeur
    return str(valeur)


if __name__ == "__main__":
    # Le banc vit dans src/bancs/ depuis le 10/11/2026 : l'archive du plugin
    # ne l'embarque pas. Dans le depot, ce relais le joue a l'identique.
    import runpy
    import sys
    from pathlib import Path

    _banc = Path(__file__).resolve().parent / "bancs" / "banc_parametres.py"
    if not _banc.is_file():
        print("Le banc de parametres n'est pas livre avec cette installation.",
              file=sys.stderr)
        raise SystemExit(2)
    runpy.run_path(str(_banc), run_name="__main__")
