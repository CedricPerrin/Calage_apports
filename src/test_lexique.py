"""
Le lexique de l'aide (calage_apports/lexique.py), sans QGIS : chaque terme
est employe par les textes du plugin, defini simplement, sa source est une
adresse https, et ses occurrences deviennent des liens vers l'aide (demande
du 27/10/2026, comme Plemmyra, Hyetos et Rhoe).

    python -m pytest src/test_lexique.py
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calage_apports import lexique as lx

PLUGIN = (Path(__file__).resolve().parents[1] / "calage_apports" / "plugin.py").read_text(
    encoding="utf-8")


def test_cles_uniques_et_motifs_valides():
    cles = [t.cle for t in lx.TERMES]
    assert len(cles) == len(set(cles))
    for t in lx.TERMES:
        assert re.fullmatch(r"[a-z0-9_]+", t.cle), t.cle
        re.compile(t.motif)


@pytest.mark.parametrize("terme", lx.TERMES, ids=lambda t: t.cle)
def test_terme_employe_par_le_plugin(terme):
    """Un terme du lexique est un terme que les textes du plugin emploient."""
    assert re.search(terme.motif, PLUGIN), terme.cle


@pytest.mark.parametrize("terme", lx.TERMES, ids=lambda t: t.cle)
def test_definition_courte_et_lisible(terme):
    """Trois phrases au plus, de 25 mots au plus chacune (ASD-STE100)."""
    phrases = [x for x in re.split(r"(?<=[.!?])\s+", terme.definition) if x]
    assert 1 <= len(phrases) <= 3, terme.cle
    for phrase in phrases:
        assert len(phrase.split()) <= 25, (terme.cle, phrase)
    assert terme.definition.endswith("."), terme.cle


@pytest.mark.parametrize("terme", [t for t in lx.TERMES if t.url], ids=lambda t: t.cle)
def test_une_adresse_est_https_et_a_sa_source(terme):
    assert terme.url.startswith("https://"), terme.cle
    assert terme.source, f"{terme.cle} : une adresse sans citation"


@pytest.mark.parametrize(("texte", "cles"), [
    ("Les hydrogrammes cibles et l'hydrogramme injecté.",
     ["hydrogramme_cible", "hydrogramme"]),
    ("Débit à la section de contrôle, décalé du Δt de propagation.",
     ["section_controle", "dt"]),
    ("Le plan de référence et le calcul de référence.",
     ["plan_reference", "calcul_reference"]),
    ("Unsteady&nbsp;Flow, zone d'écoulement 2D, maillage 2D.",
     ["unsteady", "zone_2d", "maillage"]),
])
def test_lier_trouve_les_termes(texte, cles):
    assert re.findall(r'href="terme:([a-z0-9_]+)"', lx.lier(texte)) == cles


def test_lier_respecte_balises_code_titres_et_liens_et_garde_les_lignes():
    texte = ('<h3><a name="s1"></a>Le maillage</h3><tt>Q100 maillage</tt> ; '
             '<i>Valider les hydrogrammes</i> ; <a href="#s2">maillage</a> ; <b>PK</b>.')
    lie = lx.lier(texte)
    assert lie.startswith('<h3><a name="s1"></a>Le maillage</h3><tt>Q100 maillage</tt>'), lie
    assert "<i>Valider les hydrogrammes</i>" in lie, "un nom de bouton reste tel quel"
    assert '<a href="#s2">maillage</a>' in lie, "un lien existant reste tel quel"
    assert '<b><a href="terme:pk">PK</a></b>' in lie
    assert lx.lier("PK\n1 < 2 & 3") == '<a href="terme:pk">PK</a><br>1 &lt; 2 &amp; 3', \
        "un texte brut garde ses retours a la ligne et ses chevrons"
    assert lx.lier(lie) == lie, "appliquee deux fois, elle ne change plus rien"


def test_liens_discrets_epargne_le_sommaire():
    texte = '<a href="#s1">Sommaire</a> <a href="terme:pk">PK</a> <a href="https://x">x</a>'
    rendu = lx.liens_discrets(texte, "#123456")
    assert '<a href="#s1">' in rendu, "le sommaire garde son apparence de lien"
    assert rendu.count('style="color: #123456; text-decoration: none"') == 2


def test_entree_et_infobulle():
    entree = lx.entree(lx.terme("forme"))
    assert '<a name="terme_forme"></a>' in entree
    assert 'href="#terme_dt"' in entree, "un autre terme renvoie a son entree"
    assert 'href="https://doi.org/10.1016/j.jhydrol.2009.08.003"' in entree
    assert lx.resume("Le PK et le Δt.").splitlines() == [
        lx.definition(lx.terme("pk")), lx.definition(lx.terme("dt"))]
