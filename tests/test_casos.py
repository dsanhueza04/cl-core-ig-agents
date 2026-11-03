"""Casos de medición (examples/casos/*): la ficha de referencia de cada uno debe ser válida y renderizable."""
import json
from pathlib import Path

import pytest

from agents.base import STANDARD_ALIASES
from generator.render import render_files
from generator.spec import completar_ficha, validate_spec
from tests.test_catalog_precheck import mini_catalog

REAL = Path("build/catalog/catalog.json")
CASOS = sorted(p.parent for p in Path("examples/casos").glob("*/spec.json"))
IDS = [p.name for p in CASOS]


def cargar(caso: Path):
    return (json.loads((caso / "spec.json").read_text(encoding="utf-8")),
            (caso / "spec.md").read_text(encoding="utf-8"))


def test_there_are_cases():
    assert IDS == ["crecimiento-infantil", "frecuencia-cardiaca", "frecuencia-respiratoria", "oxigenoterapia",
                   "peso-talla", "saturacion-oxigeno"]


@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_reference_ficha_is_valid_complete_and_every_loinc_is_in_the_spec(caso):
    ficha, texto = cargar(caso)
    assert validate_spec(ficha, mini_catalog(), texto) == []
    assert completar_ficha(ficha) == (ficha, [])          # la referencia ya está completa y normalizada
    for o in ficha["observaciones"]:
        assert o["codigo_loinc"] in texto


@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_reference_ficha_renders_one_profile_and_one_example_per_observation(caso):
    ficha, _ = cargar(caso)
    out = render_files(ficha)
    n = len(ficha["observaciones"])
    assert out["perfiles.fsh"].count("Profile:") == n
    assert out["ejemplos.fsh"].count("InstanceOf: CL") == n and out["ejemplos.fsh"].count("InstanceOf: CorePacienteCl") == 1
    assert "* component" not in out["perfiles.fsh"]           # son de valor único
    for o in ficha["observaciones"]:
        assert f"* valueQuantity.code = #{o['valor']['ucum']}" in out["perfiles.fsh"] \
            or f"* valueQuantity.code = #\"{o['valor']['ucum']}\"" in out["perfiles.fsh"]


def test_case_names_do_not_overlap_between_cases():
    nombres = [o[k] for c in CASOS for o in cargar(c)[0]["observaciones"] for k in ("nombre", "id")]
    assert len(nombres) == len(set(nombres))


def test_special_ucum_codes_are_quoted_in_the_rendered_profile():
    out = {c.name: render_files(cargar(c)[0]) for c in CASOS}
    assert '#"/min"' in out["frecuencia-cardiaca"]["perfiles.fsh"] and "'/min'" in out["frecuencia-cardiaca"]["ejemplos.fsh"]
    assert '#"%"' in out["saturacion-oxigeno"]["perfiles.fsh"]


@pytest.mark.skipif(not REAL.is_file(), reason="ejecuta `make catalog` primero")
@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_reference_ficha_and_rendered_fsh_pass_against_real_clcore(caso):
    from agents.catalog import CatalogIndex
    from validator.precheck import precheck_fsh
    cat = CatalogIndex.from_file(REAL)
    ficha, texto = cargar(caso)
    assert validate_spec(ficha, cat, texto) == []
    for name, text in render_files(ficha).items():
        assert precheck_fsh(text, cat, STANDARD_ALIASES) == [], name
