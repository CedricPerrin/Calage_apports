# -*- coding: utf-8 -*-
"""
Reconstruit methodologie_calage_amont_aval.docx (V16).

LE FICHIER D'ORIGINE SERT DE GABARIT : on en vide le corps et on le
reconstruit avec SES PROPRES styles. C'est la methode deja employee pour la
V11 — elle conserve la mise en page, les styles nommes et les proprietes de
section, qu'une creation ex nihilo perdrait.
"""
import io
import sys
import zipfile
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, Cm, RGBColor

sys.path.insert(0, str(Path(__file__).parent))
from contenu import CONTENU                                  # noqa: E402

GABARIT = Path(sys.argv[1])
FIGURES = Path(sys.argv[2])
SORTIE = Path(sys.argv[3])

VIOLET = RGBColor(0x8E, 0x3B, 0x7A)
GRIS = RGBColor(0x5A, 0x7C, 0x8A)
BLEU_F = RGBColor(0x2C, 0x5F, 0x73)


def figure_du_gabarit(nom):
    """
    Rend une figure absente du dossier, lue dans word/media/ du GABARIT.

    figures_note.py en rend SIX ; le contenu en reference HUIT. Les deux
    autres — le profil en long et la correction additive — viennent du
    document d'origine, et c'est justement lui que l'on passe en gabarit :
    il les porte deja. Les extraire a la main etait un pas de plus a chaque
    reconstruction, et son oubli arretait le script sur un
    FileNotFoundError.

    Retourne None si le gabarit ne la porte pas non plus.
    """
    with zipfile.ZipFile(GABARIT) as archive:
        try:
            return io.BytesIO(archive.read(f"word/media/{nom}"))
        except KeyError:
            return None


def vider_corps(document):
    """Retire tout le contenu, en gardant la derniere balise de section."""
    corps = document.element.body
    for enfant in list(corps.iterchildren()):
        if not enfant.tag.endswith("}sectPr"):
            corps.remove(enfant)


def largeur_utile(document):
    s = document.sections[0]
    return s.page_width - s.left_margin - s.right_margin


def style_tableau(document):
    """Le style de tableau du gabarit, ou un repli qui existe partout."""
    for nom in ("Table Grid", "Grille du tableau", "TableGrid"):
        try:
            document.styles[nom]
            return nom
        except KeyError:
            continue
    return None


def main():
    doc = docx.Document(str(GABARIT))
    vider_corps(doc)
    largeur = largeur_utile(doc)
    st_tab = style_tableau(doc)
    compte = {"figures": 0, "tableaux": 0, "mots": 0}

    for genre, charge in CONTENU:
        if genre == "title":
            p = doc.add_paragraph(charge, style="Title")
        elif genre == "sous_titre":
            p = doc.add_paragraph()
            r = p.add_run(charge)
            r.bold = True
            r.font.size = Pt(12)
            r.font.color.rgb = GRIS
        elif genre in ("h1", "h2", "h3"):
            doc.add_paragraph(charge, style=f"Heading {genre[1]}")
        elif genre == "p":
            doc.add_paragraph(charge)
        elif genre == "bullet":
            doc.add_paragraph(charge, style="List Bullet")
        elif genre == "note":
            # ENCADRE : un fait qui merite d'arreter l'oeil sans meriter un
            # titre. Italique + retrait, pas de bordure — le gabarit n'en a
            # pas de style, et en fabriquer un a la main donnerait un rendu
            # different d'un Word a l'autre.
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.space_before = Pt(6)
            r = p.add_run(charge)
            r.italic = True
            r.font.color.rgb = BLEU_F
        elif genre == "code":
            for ligne in charge.split("\n"):
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(0.6)
                p.paragraph_format.space_after = Pt(0)
                r = p.add_run(ligne)
                r.font.name = "Consolas"
                r.font.size = Pt(9)
        elif genre == "table":
            entetes, lignes = charge[0], charge[1:]
            t = doc.add_table(rows=len(charge), cols=len(entetes))
            if st_tab:
                t.style = st_tab
            for j, texte in enumerate(entetes):
                cell = t.cell(0, j)
                cell.text = ""
                r = cell.paragraphs[0].add_run(texte)
                r.bold = True
                r.font.color.rgb = VIOLET
            for i, ligne in enumerate(lignes, start=1):
                for j, texte in enumerate(ligne):
                    t.cell(i, j).text = str(texte)
            # PREMIERE COLONNE ETROITE : elle porte un libelle, la seconde
            # l'explication. A largeurs egales, l'explication deborde sur
            # trois fois la hauteur necessaire.
            if len(entetes) == 2:
                for r_ in t.rows:
                    r_.cells[0].width = int(largeur * 0.30)
                    r_.cells[1].width = int(largeur * 0.70)
            compte["tableaux"] += 1
            doc.add_paragraph()
        elif genre == "figure":
            nom, legende = charge
            chemin = FIGURES / nom
            source = str(chemin) if chemin.exists() else figure_du_gabarit(nom)
            if source is None:
                raise FileNotFoundError(chemin)
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(source, width=largeur)
            if legende:
                c = doc.add_paragraph()
                c.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = c.add_run(f"Figure {compte['figures'] + 1} — {legende}")
                r.italic = True
                r.font.size = Pt(9)
                r.font.color.rgb = GRIS
            compte["figures"] += 1
        else:
            raise ValueError(f"genre inconnu : {genre}")

        if isinstance(charge, str):
            compte["mots"] += len(charge.split())
        elif genre == "table":
            compte["mots"] += sum(len(str(c).split())
                                  for ligne in charge for c in ligne)
        elif genre == "figure" and charge[1]:
            compte["mots"] += len(charge[1].split())

    doc.save(str(SORTIE))
    print(f"   {SORTIE.name}")
    print(f"   {compte['mots']} mots, {compte['tableaux']} tableaux, "
          f"{compte['figures']} figures")


if __name__ == "__main__":
    main()
