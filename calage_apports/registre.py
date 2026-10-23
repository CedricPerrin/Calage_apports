"""Registre des graphiques, commun aux extensions de la maison (décision de l'ingénieur du
22/10/2026 pour Rhoé et Hyétos, étendue le 23/10/2026 aux autres extensions).

« Teintes ISL nuancées » : une famille autour du bleu-vert ISL, sur une carte claire dans les
deux thèmes (les couleurs se lisent partout de la même façon, comme les figures des rapports).
Chaque extension qui l'emploie en garde une copie identique, sans Qt (liste :
``D:\\1-Dev\\CLAUDE.md``, « Coordination entre plugins ») : changer l'une, c'est changer toutes.
Le sens ne repose jamais sur la couleur seule : forme, trait, hachure ou texte le portent aussi.
"""

from __future__ import annotations

import math

#: Carte du graphique : fond, bordure, rayon des coins (px).
FOND = "#ffffff"
BORDURE = "#d5dde2"
RAYON_PX = 6
#: Encre du texte, texte secondaire (axes, notes), grille.
ENCRE = "#1c2430"
TEXTE_SECONDAIRE = "#5b6670"
GRILLE = "#e3e9ec"
#: Valeur retenue (mise en avant) ; éléments neutres, clair et foncé.
ACCENT = "#3a8d94"
NEUTRE = "#b9c3c9"
NEUTRE_FONCE = "#7d8a93"
#: Événement : corail ; sa variante foncée pour un texte (contraste 5,5:1 sur blanc).
EVENEMENT = "#e2725b"
EVENEMENT_TEXTE = "#b4452f"
#: Alerte (⚠, hors domaine) : ocre foncé, contraste 4,7:1 sur blanc.
ALERTE = "#a8640f"
#: Pluies décennale et centennale.
P10 = "#d9c39a"
P100 = "#3a8d94"
#: Périodes de retour, du clair au foncé : repères (T en années, couleur), interpolés en log T.
#: T = 2 ans reste à 2,1:1 sur blanc : une courbe claire porte aussi ses points et sa légende.
PERIODES = ((2.0, "#7fbcc1"), (10.0, "#3a8d94"), (100.0, "#1f5f66"), (1000.0, "#0f3a40"))
#: Occupations du sol (``rhoe.core.occupation.OCCUPATIONS``), aux couleurs des cartes
#: d'occupation : bois vert, pâturage vert clair, culture jaune, urbain rouge brique.
OCCUPATIONS = {
    "Bois": "#4f8f3a",
    "Pâturage": "#a8cf6a",
    "Culture": "#f0d26a",
    "Urbain": "#b5525c",
    "Imperméables": "#b5525c",
    "Autres": "#a39e93",
}
#: Sources de pluie.
SOURCES = {
    "postes": "#3a8d94",
    "COMEPHORE": "#5f7fb3",
    "SHYREG": "#d39b4a",
    "saisie": "#8a8f94",
}


def _rvb(couleur: str) -> tuple[int, int, int]:
    return int(couleur[1:3], 16), int(couleur[3:5], 16), int(couleur[5:7], 16)


def couleur_periode(periode_ans: float) -> str:
    """Couleur d'une période de retour, interpolée en log T entre les repères de
    :data:`PERIODES` (bornée aux repères extrêmes)."""
    t = min(max(periode_ans, PERIODES[0][0]), PERIODES[-1][0])
    for (t0, c0), (t1, c1) in zip(PERIODES, PERIODES[1:]):
        if t <= t1:
            k = (math.log(t) - math.log(t0)) / (math.log(t1) - math.log(t0))
            a, b = _rvb(c0), _rvb(c1)
            return "#" + "".join(f"{round(x + k * (y - x)):02x}" for x, y in zip(a, b))
    return PERIODES[-1][1]


if __name__ == "__main__":
    assert couleur_periode(10) == ACCENT and couleur_periode(1) == PERIODES[0][1]
    assert couleur_periode(5000) == PERIODES[-1][1] and len(couleur_periode(30)) == 7
    print("ok")
