# -*- coding: utf-8 -*-
"""
Fabrique template_donnees_calage.xlsx, le classeur de reference livre avec la
chaine.

POURQUOI UN SCRIPT ET NON UN FICHIER TENU A LA MAIN : le template precedent
demandait encore un « Seuil_KGE » — abandonne depuis que l'arret porte sur le
volume, le debit de pointe et la forme — et ignorait la precision attendue, la
fenetre de simulation et la pente par apport. Un classeur de reference qui
reclame un parametre mort et en oublie huit fait perdre plus de temps qu'il
n'en fait gagner.

La liste des parametres est donc CALQUEE sur celle que le plugin ecrit
reellement (noyau.preparer_classeur) : les deux classeurs doivent se
correspondre, sans quoi remplir le template a la main ne prepare pas au
classeur compose.

  python creer_template.py            fabrique le fichier et le controle
"""

import sys
from pathlib import Path

import pandas as pd

import style_classeur

DOSSIER = Path(__file__).resolve().parent
CHEMIN = DOSSIER.parent / "template_donnees_calage.xlsx"

# (parametre, valeur d'exemple). Le COMMENTAIRE vient de style_classeur, qui
# le partage avec le classeur compose par le plugin : les deux classeurs
# doivent expliquer la meme chose. Une chaine commencant par « --- » devient
# une barre de section a la mise en forme.
PARAMETRES = [
    ("--- MODELE HEC-RAS ---", ""),
    ("Dossier_projet_HECRAS", r"D:\etudes\MonProjet"),
    ("Nom_projet", "MonProjet"),
    ("Version_HECRAS", "7.0.1"),
    ("Nom_zone_2D", "Perimeter 1"),
    ("Plan_reference", "p01"),
    ("Geometrie_reference", "g01"),
    ("Unsteady_reference", "u01"),
    ("Mode_selection_modele", "plan"),
    ("Premier_apport", ""),

    ("--- FENETRE DE SIMULATION ---", ""),
    ("Simulation_debut", ""),
    ("Simulation_fin", ""),
    ("Intervalle_calcul", ""),
    ("Intervalle_sortie", ""),
    ("Intervalle_instantane", ""),
    ("Intervalle_mapping", ""),

    ("--- PRECISION ATTENDUE ---", ""),
    ("Tolerance_volume_pct", 5.0),
    ("Tolerance_pic_pct", 2.0),
    ("Nb_max_iterations_par_apport", 6),

    ("--- FENETRE DE JUGEMENT ---", ""),
    ("Fenetre_active", ""),
    ("Fenetre_seuil_bas_pct", 0.5),
    ("Fenetre_seuil_haut_pct", 99.0),
    ("Fenetre_t0_h", ""),
    ("Fenetre_tf_h", ""),

    ("--- CHAINE GEOGRAPHIQUE ---", ""),
    ("Source_geometrie", "SHP"),
    ("Fichier_SHP_Sections", r"D:\etudes\MonProjet\_calage\sections.shp"),
    ("Fichier_SHP_Apports", r"D:\etudes\MonProjet\_calage\injections.shp"),
    ("Fichier_SHP_Axe", r"D:\etudes\MonProjet\_calage\axe.shp"),
    ("Champ_nom_SHP", "nom"),
    ("Sens_axe", "amont_aval"),
    ("PK_origine_m", 0),

    ("--- PROFIL EN LONG ---", ""),
    ("Source_profil_en_long", "MODELE"),
    ("Pas_profil_m", 25),
    ("Distance_max_axe_maillage_m", ""),
    ("Pente_apport_creee_m_par_m", ""),
]

CORRESPONDANCE = pd.DataFrame({
    "Ordre": [1, 2, 3],
    "Nom_Apport (BC line)": ["A1", "A2", "A3"],
    "Nom_Section (reference line)": ["SC1", "SC2", "SC3"],
    "Nom_Cible": ["Cible_SC1", "Cible_SC2", "Cible_SC3"],
    "Pente_m_par_m": ["", "", ""],
})

# Hydrogramme d'exemple sur la premiere section seulement : le classeur doit
# montrer la forme attendue sans laisser croire que les trois sont remplies.
TEMPS = [0, 1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24]
EXEMPLE = [2, 5, 12, 22, 30, 28, 22, 16, 11, 6, 3, 1]
CIBLES = pd.DataFrame({"Temps_h": TEMPS, "Cible_SC1": EXEMPLE,
                       "Cible_SC2": [None] * len(TEMPS),
                       "Cible_SC3": [None] * len(TEMPS)})

INSTRUCTIONS = [
    ("titre", "Calage d'apports amont sur hydrogrammes cibles aval"),
    ("soustitre", "Classeur de saisie — ISL Ingénierie"),
    ("vide", ""),
    ("intro",
     "Ce classeur rassemble tout ce que le calage doit savoir. Rempli à la "
     "main, il se lance en ligne de commande ; composé par le plugin QGIS, "
     "il arrive déjà pré-rempli et seule la feuille Cibles reste à compléter."),
    ("vide", ""),
    ("section", "Les trois feuilles"),
    ("puce", "Paramètres — le modèle, la précision attendue, les shapefiles. "
             "Les cases crème sont celles à remplir."),
    ("puce", "Correspondance — une ligne par apport à caler, de l'amont vers "
             "l'aval. L'ordre fixe à lui seul la séquence."),
    ("puce", "Cibles — une colonne Temps_h, puis un hydrogramme par section. "
             "Les échelles de temps n'ont pas à être synchronisées entre "
             "sections : le recalage temporel s'en charge."),
    ("vide", ""),
    ("section", "Avant de lancer"),
    ("puce", "Le réseau doit avoir un ordre amont → aval strict : la méthode "
             "ne s'applique pas à un réseau bouclé."),
    ("puce", "Un seul apport nouveau entre deux sections consécutives — une "
             "inconnue pour une contrainte."),
    ("puce", "Toutes les couches dans la même projection métrique. Un "
             "shapefile sans son fichier .prj est refusé : il se lirait sans "
             "erreur en décalant les objets."),
    ("vide", ""),
    ("section", "Ce qui arrête le calage"),
    ("puce", "La concordance simultanée du volume, du débit de pointe et de "
             "la forme, chacun sous sa tolérance. Tout est rapporté en "
             "pourcentage d'atteinte de la cible."),
    ("puce", "Le décalage temporel n'est pas un critère : il est mesuré et "
             "signalé comme garde-fou, jamais corrigé."),
    ("vide", ""),
    ("section", "Contrôler avant de calculer"),
    ("code", "python controle_donnees.py donnees_calage.xlsx"),
    ("code", "python pont_hecras.py controler-modele --template donnees_calage.xlsx"),
    ("vide", ""),
    ("note", "Un calage représente des heures de calcul : une incohérence "
             "doit être détectée en quelques secondes, avant le premier "
             "calcul. Ne rien lancer tant qu'une erreur subsiste."),
    ("note", "Détail complet : methodologie_calage_amont_aval.docx."),
]


def ecrire_instructions(feuille):
    """Feuille de garde. Jamais relue par la chaine : elle peut respirer."""
    from openpyxl.styles import Alignment, Font, PatternFill

    feuille.sheet_view.showGridLines = False
    feuille.column_dimensions["A"].width = 3
    feuille.column_dimensions["B"].width = 108

    styles = {
        "titre": (Font(name=style_classeur.POLICE, size=18, bold=True,
                       color=style_classeur.VIOLET), 30),
        "soustitre": (Font(name=style_classeur.POLICE, size=11,
                           color=style_classeur.ARDOISE), 20),
        "section": (Font(name=style_classeur.POLICE, size=12, bold=True,
                         color=style_classeur.ARDOISE), 26),
        "intro": (Font(name=style_classeur.POLICE, size=10.5), 46),
        "puce": (Font(name=style_classeur.POLICE, size=10), 32),
        "code": (Font(name="Consolas", size=9.5,
                      color=style_classeur.VIOLET_SOMBRE), 18),
        "note": (Font(name=style_classeur.POLICE, size=9.5, italic=True,
                      color="6B6B6B"), 30),
        "vide": (Font(name=style_classeur.POLICE), 8),
    }
    ligne = 2
    for genre, texte in INSTRUCTIONS:
        cellule = feuille.cell(row=ligne, column=2)
        cellule.value = ("•   " + texte) if genre == "puce" else texte
        police, hauteur = styles[genre]
        cellule.font = police
        cellule.alignment = Alignment(vertical="top", wrap_text=True,
                                      indent=1 if genre == "puce" else 0)
        if genre == "code":
            cellule.fill = PatternFill("solid",
                                       fgColor=style_classeur.VIOLET_VOILE)
        feuille.row_dimensions[ligne].height = hauteur
        ligne += 1

    # Filet violet sous le titre, a la maniere du bandeau du plugin.
    for colonne in ("A", "B"):
        c = feuille[f"{colonne}4"]
        c.fill = PatternFill("solid", fgColor=style_classeur.VIOLET)
    feuille.row_dimensions[4].height = 4
    feuille.sheet_properties.tabColor = style_classeur.VIOLET
    style_classeur.mise_en_page(feuille, repeter_entete=False)


def construire():
    inconnus = [p for p, _ in PARAMETRES
                if not p.startswith("---")
                and p not in style_classeur.COMMENTAIRES]
    if inconnus:
        raise SystemExit(f"parametre(s) sans commentaire dans "
                         f"style_classeur.COMMENTAIRES : {inconnus}")
    parametres = pd.DataFrame({
        "Parametre": [p for p, _ in PARAMETRES],
        "Valeur": [v for _, v in PARAMETRES],
        "Commentaire": [style_classeur.COMMENTAIRES.get(p, "")
                        for p, _ in PARAMETRES],
    })
    with pd.ExcelWriter(CHEMIN, engine="openpyxl") as w:
        # Feuille de garde d'abord : c'est elle qui s'ouvre.
        pd.DataFrame().to_excel(w, sheet_name="Instructions", index=False)
        parametres.to_excel(w, sheet_name="Parametres", index=False)
        CORRESPONDANCE.to_excel(w, sheet_name="Correspondance", index=False)
        CIBLES.to_excel(w, sheet_name="Cibles", index=False)

    import openpyxl
    classeur = openpyxl.load_workbook(CHEMIN)
    ecrire_instructions(classeur["Instructions"])
    classeur.active = 0
    classeur.save(CHEMIN)

    style_classeur.mettre_en_forme(CHEMIN)
    return CHEMIN


if __name__ == "__main__":
    chemin = construire()
    print(f"{chemin.name} — {chemin.stat().st_size / 1024:.1f} ko")

    # LE TEMPLATE LIVRE DOIT PASSER SON PROPRE CONTROLE. Un classeur de
    # reference que la chaine refuse enverrait chercher l'erreur dans le
    # modele de l'utilisateur.
    import controle_donnees
    anomalies = controle_donnees.controler_template(chemin)
    erreurs = [m for n, m in anomalies if n == controle_donnees.ERREUR]
    for niveau, message in anomalies:
        print(f"   [{niveau}] {message[:110]}")
    if erreurs:
        print(f"\n{len(erreurs)} ERREUR(S) : le template ne passe pas son "
              f"propre controle.")
        sys.exit(1)
    print("\nLe template passe son propre controle (avertissements admis : "
          "les chemins d'exemple n'existent pas).")
