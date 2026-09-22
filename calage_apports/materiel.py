# -*- coding: utf-8 -*-
"""
Ce que le poste peut donner a HEC-RAS, et le nombre de cœurs qu'on suggere donc.

REPRIS DE SENSI HEC-RAS (sensi_hecras/core/materiel.py, mesure du 9 septembre
2026, REPRISE § 9.4) : sur un processeur HYBRIDE, HEC-RAS 7.0.1 ecrit « CPU
Affinity ON (Performance Cores …) » et ne calcule le maillage 2D que sur les
cœurs de PERFORMANCE, qu'on lui en demande 4 ou « tous » (Cores=0). Les cœurs
d'efficience ne servent pas au solveur. Le bon denominateur est donc le cœur de
performance, pas le cœur physique ni le processeur logique.

CE QUE LE CALAGE EN FAIT. Il ne lance qu'UN calcul a la fois : pas de
sursouscription a eviter, seulement un nombre a demander. ras-commander
(RasPlan.set_num_cores, relu sur GitHub le 22/09/2026, v0.99 a v0.102) reecrit
« UNET D1 Cores= », « UNET D2 Cores= » et « PS Cores= » du plan calcule avec ce
nombre ; 0 signifie « tous les cœurs disponibles » ; son texte recommande « 2
(le plus efficace) a 8 (le plus performant) », et compute_plan annonce des
rendements decroissants au-dela de 8. La suggestion est donc le nombre de cœurs
utiles du poste, plafonne a 8.

MESURE SUR UN CALAGE REEL (22/09/2026, SUHI_ARAN, 127 341 cellules, poste a
4 cœurs P) : le plan demandait « tous » et un maillage a 8 ; HEC-RAS a employe
4 cœurs (« Maximum number of cores = 4 », 2 h 46 pour 20 h 30 simulees). Sur un
tel poste la suggestion ne change rien a la duree — et l'etiquette le dit,
plutot que de promettre.

DEUXIEME MESURE, LE MEME JOUR, SUR UNE STATION (« Performance Cores
0,2,…,62 », 32 cœurs de meme classe) : la case cochee a demande 8 ; HEC-RAS a
employe 8 (« Maximum number of cores = 8 ») et simule 48 h en 1 h 48, 26,4 fois
le temps reel — contre 7,4 fois sur le portable (autre crue, Q20 contre Q100 :
la comparaison est indicative). Un nombre demande explicitement est donc
honore ; ce que « tous » aurait donne sur cette station n'a pas ete mesure.

POURQUOI SUGGERER PLUTOT QUE DECIDER : meme regle que Sensi. On detecte, on
suggere, on dit pourquoi, et l'utilisateur coche — une valeur qui change sans le
dire est pire qu'une valeur absente. ctypes suffit : aucune dependance.
"""
from __future__ import annotations

from dataclasses import dataclass

# Plafond de la suggestion : « 2 to 8 » (ras-commander, set_num_cores) et
# « >8 cores: diminishing returns » (compute_plan). Au-dessus, c'est a
# l'utilisateur de le demander en connaissance de cause, dans le plan.
# ponytail: plafond fixe, non mesure chez nous ; mesurer un plan seul a 8 puis
# a « tous » sur une station a plus de 8 cœurs P avant de le bouger.
PLAFOND_SUGGERE = 8
# Windows n'alloue pas plus de 64 cœurs a un Ras.exe (ras-commander).
PLAFOND_RAS = 64

RELATION_COEUR = 0          # RelationProcessorCore
_DECALAGE_CLASSE = 9        # Relationship (4) + Size (4) + Flags (1)


@dataclass(frozen=True)
class Poste:
    """L'inventaire du processeur, et ce qu'on en deduit."""

    logiques: int                  # processeurs logiques (os.cpu_count)
    coeurs: int | None             # cœurs physiques, None si non detecte
    performance: int | None        # cœurs de performance, None si non detecte
    hybride: bool                  # au moins deux classes d'efficience
    detail: str                    # ce qu'on dit a l'utilisateur

    @property
    def coeurs_utiles(self):
        """Les cœurs sur lesquels le solveur 2D calculera vraiment."""
        if self.hybride and self.performance:
            return self.performance
        return self.coeurs or self.logiques

    @property
    def suggestion(self):
        """Cœurs a demander pour le seul calcul en cours : utiles, plafonnes."""
        return max(1, min(PLAFOND_SUGGERE, self.coeurs_utiles))


def _coeurs_windows():
    """
    (nb_coeurs, nb_performance, classes) par GetLogicalProcessorInformationEx.

    Renvoie (None, None, ()) si l'appel n'est pas disponible ou echoue : le
    plugin ne doit pas tomber parce qu'un poste refuse cette information. La
    structure est de taille variable : on avance d'entree en entree avec son
    champ « Size » plutot que de la decrire a ctypes.
    """
    import ctypes

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (OSError, AttributeError):          # pas Windows
        return None, None, ()

    taille = ctypes.c_ulong(0)
    kernel32.GetLogicalProcessorInformationEx(
        RELATION_COEUR, None, ctypes.byref(taille))
    if not taille.value:
        return None, None, ()
    tampon = (ctypes.c_ubyte * taille.value)()
    if not kernel32.GetLogicalProcessorInformationEx(
            RELATION_COEUR, tampon, ctypes.byref(taille)):
        return None, None, ()

    brut = bytes(tampon)
    classes, position = [], 0
    while position + 8 <= len(brut):
        relation = int.from_bytes(brut[position:position + 4], "little")
        octets = int.from_bytes(brut[position + 4:position + 8], "little")
        if octets <= 0:
            break
        if relation == RELATION_COEUR:
            classes.append(brut[position + _DECALAGE_CLASSE])
        position += octets

    if not classes:
        return None, None, ()
    haute = max(classes)
    return len(classes), sum(1 for c in classes if c == haute), tuple(classes)


def inventaire(coeurs_windows=None):
    """L'inventaire du poste. NE LEVE JAMAIS : incomplet, il le dit."""
    import os

    logiques = os.cpu_count() or 1
    try:
        coeurs, performance, classes = (coeurs_windows or _coeurs_windows)()
    except Exception:                          # noqa: BLE001
        coeurs, performance, classes = None, None, ()

    hybride = len(set(classes)) > 1
    if coeurs is None:
        detail = (f"Ce poste : {logiques} processeur(s) logique(s) ; la "
                  "composition du processeur n'a pas pu être lue, la "
                  "suggestion se fonde sur ce seul nombre.")
    elif hybride:
        detail = (f"Ce poste : {logiques} processeur(s) logique(s), {coeurs} "
                  f"cœur(s), dont {performance} de performance. HEC-RAS 7.0.1 "
                  f"ne calcule le maillage 2D que sur ceux-là : les "
                  f"{coeurs - performance} cœur(s) d'efficience ne participent "
                  "pas (mesure Sensi, 9 sept. 2026).")
    else:
        detail = (f"Ce poste : {logiques} processeur(s) logique(s), {coeurs} "
                  "cœur(s) de même classe : tous comptent.")
    return Poste(logiques=logiques, coeurs=coeurs, performance=performance,
                 hybride=hybride, detail=detail)


def libelle_plan(coeurs_2d):
    """« tous » pour 0, sinon les nombres distincts du plan, dans l'ordre."""
    vus = []
    for v in coeurs_2d or ():
        texte = "tous" if int(v) == 0 else str(int(v))
        if texte not in vus:
            vus.append(texte)
    return ", ".join(vus) if vus else "non renseigné"


def conseil(poste, coeurs_2d=None, plan=None):
    """
    Le texte sous la case : le poste, ce que le plan demande, et ce que cocher
    changera — ou ne changera pas. DIT LE CHIFFRE ET SA RAISON : « 4 » sans
    explication passerait pour une limitation du plugin.
    """
    n = poste.suggestion
    phrases = [poste.detail]
    valeurs = [int(v) for v in coeurs_2d or ()]
    if valeurs:
        phrases.append(f"Le plan {plan or 'de référence'} demande "
                       f"« UNET D2 Cores = {libelle_plan(valeurs)} ».")
        demande_tout, maxi = 0 in valeurs, max(valeurs)
        if poste.hybride and (demande_tout or maxi >= n):
            phrases.append(
                f"HEC-RAS n'emploiera de toute façon que les {n} cœurs de "
                "performance de ce poste : cocher n'accélère rien ici, mais "
                "fixe le nombre dans chaque plan d'étape.")
        elif demande_tout:
            phrases.append(
                f"« Tous » laisse HEC-RAS choisir sans dire combien ; un "
                f"nombre demandé est honoré (22 sept. 2026 : 8 demandés, "
                f"8 employés sur une station à 32 cœurs, 48 h simulées en "
                f"1 h 48). {n} est le nombre de cœurs utiles de ce poste"
                + (f", plafonné à {PLAFOND_SUGGERE} (ras-commander : rendements "
                   "décroissants au-delà)." if poste.coeurs_utiles > n else "."))
        elif maxi < n:
            phrases.append(f"Le plan en demande moins que le poste n'en offre : "
                           f"{n} devrait raccourcir chaque calcul.")
        else:
            phrases.append(f"Le plan en demande déjà {maxi} ; cocher ramène à "
                           f"{n}, ce que ce poste peut vraiment donner.")
    elif plan:
        phrases.append(f"Le plan {plan} ne porte aucune ligne « UNET D2 Cores » "
                       "lisible.")
    else:
        phrases.append("Choisir le plan de référence (étape Modèle) pour lire "
                       "ce qu'il demande.")
    phrases.append(f"Suggestion pour ce poste : {n} cœur{'s' if n > 1 else ''} "
                   "par calcul.")
    return " ".join(phrases)


if __name__ == "__main__":
    # Auto-test minimal : l'inventaire ne leve pas, la suggestion tient dans
    # [1, PLAFOND_SUGGERE], et le conseil couvre les trois cas de plan.
    p = inventaire()
    assert 1 <= p.suggestion <= PLAFOND_SUGGERE, p
    assert "processeur" in conseil(p) and "cœur" in conseil(p)
    hybride = Poste(14, 12, 4, True, "d")
    assert hybride.suggestion == 4
    assert "n'accélère rien" in conseil(hybride, [0, 0, 8], "p12")
    plein = Poste(32, 16, 16, False, "d")
    assert plein.suggestion == PLAFOND_SUGGERE
    assert "plafonné" in conseil(plein, [0], "p01")
    assert "raccourcir" in conseil(Poste(8, 8, 8, False, "d"), [2], "p01")
    assert libelle_plan([0, 0, 8]) == "tous, 8" and libelle_plan([]) == "non renseigné"
    print("materiel : OK —", p.detail, "| suggestion", p.suggestion)
