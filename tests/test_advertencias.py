import copy
import json
from pathlib import Path

import pytest

from agents.catalog import CatalogIndex
from generator.spec import advertencias_spec
from tests.test_catalog_precheck import mini_catalog

REAL = Path("build/catalog/catalog.json")
CODIGOS = ["59576-9", "77606-2", "85354-9", "8480-6", "8462-4", "39156-5", "8302-2", "8310-5",
           "29463-7", "9843-4", "8867-4", "59408-5", "2708-6", "3151-8", "3150-0", "9279-1", "8289-1"]


def cat_con_codigos():
    data = copy.deepcopy(mini_catalog().data)
    data["valueSets"] = [v for v in data["valueSets"] if v["id"] != "cl-core-vs-signos-vitales"]
    data["valueSets"].append({"id": "cl-core-vs-signos-vitales", "url": "x", "systems": ["http://loinc.org"],
                              "valueSets": [], "codes": {"http://loinc.org": CODIGOS}})
    return CatalogIndex(data)


def ficha(codigo, comp=None):
    o = {"padre": "cl-core-signos-vitales", "codigo_loinc": codigo}
    if comp:
        o["componentes"] = [{"loinc": comp}]
    return {"observaciones": [o]}


def test_codigo_permitido_no_avisa():
    assert advertencias_spec(ficha("8867-4"), cat_con_codigos()) == []


def test_codigo_fuera_del_valueset_avisa_sin_bloquear():
    av = advertencias_spec(ficha("8310-5", comp="1234-5"), cat_con_codigos())
    assert len(av) == 1 and "1234-5" in av[0] and "componentes[0]" in av[0]


def test_catalogo_sin_lista_de_codigos_no_avisa():
    assert advertencias_spec(ficha("0000-0"), mini_catalog()) == []


def test_casos_de_referencia_no_generan_avisos_con_el_catalogo_real():
    if not REAL.is_file():
        pytest.skip("sin build/catalog")
    cat = CatalogIndex.from_file(REAL)
    if not (cat.vs.get("cl-core-vs-signos-vitales") or {}).get("codes"):
        pytest.skip("catálogo sin códigos: ejecuta make catalog")
    for f in sorted(Path("examples").glob("**/spec.json")):
        assert advertencias_spec(json.loads(f.read_text(encoding="utf-8")), cat) == [], f
