"""Pruebas de la ficha estructurada y del generador determinista de FSH."""
import copy
import json
from pathlib import Path

import pytest

from generator.render import code, num, q, render_files
from generator.spec import validate_spec
from tests.test_catalog_precheck import BASE, mini_catalog

DEMO = Path("examples/demo")
SPEC = json.loads((DEMO / "spec.json").read_text(encoding="utf-8"))
SPEC_TEXT = (DEMO / "spec.md").read_text(encoding="utf-8")
REAL = Path("build/catalog/catalog.json")


def catalog():
    return mini_catalog()


def errs(spec, text=None):
    return validate_spec(spec, catalog(), text)


def rules(text, skip=("Title:", "Description:", "* component ^slicing.description")):
    return [ln for ln in text.splitlines() if ln.strip() and not ln.startswith(skip)]


# --- validación ---------------------------------------------------------------

def test_demo_spec_is_valid_against_its_source_text():
    assert errs(SPEC, SPEC_TEXT) == []


def test_loinc_code_not_in_source_text_is_rejected():
    assert any("no aparece en la especificación" in e for e in errs(SPEC, SPEC_TEXT.replace("85354-9", "XXXXX")))


def test_without_source_text_the_loinc_presence_check_is_skipped():
    assert errs(SPEC) == []


@pytest.mark.parametrize("mutate,fragment", [
    (lambda s: s["observaciones"][0].update(padre="cl-core-inexistente"), "no existe en CL Core"),
    (lambda s: s["observaciones"][0].update(padre="CorePacienteCl"), "aún no está soportado"),
    (lambda s: s["observaciones"][0].update(nombre="presion arterial"), "debe empezar con mayúscula"),
    (lambda s: s["observaciones"][0].update(nombre="CorePacienteCl"), "ya existe en CL Core"),
    (lambda s: s["observaciones"][0].update(codigo_loinc="abc"), "formato LOINC"),
    (lambda s: s["observaciones"][0]["componentes"][0].update(ucum="mm Hg"), "UCUM inválido"),
    (lambda s: s["observaciones"][0]["componentes"][1].update(nombre="sistolica"), "repetido"),
    (lambda s: s["observaciones"][0].update(valor={"unidad": "x", "ucum": "x"}), "no ambos"),
    (lambda s: s["observaciones"][0].update(componentes=None), "no ambos ni ninguno"),
    (lambda s: s["observaciones"][0]["ejemplo"]["valores"].pop("diastolica"), "un número por componente"),
    (lambda s: s["observaciones"][0]["ejemplo"].update(fecha="15/03/2026"), "formato AAAA-MM-DDThh"),
    (lambda s: s["paciente_ejemplo"].update(sexo="masculino"), "paciente_ejemplo.sexo"),
    (lambda s: s["paciente_ejemplo"].update(run="1111111-1"), "formato 11.111.111-1"),
    (lambda s: s["paciente_ejemplo"].update(nombres=[]), "al menos un nombre"),
    (lambda s: s.update(observaciones=[]), "al menos una observación"),
])
def test_invalid_specs_report_a_clear_message(mutate, fragment):
    bad = copy.deepcopy(SPEC)
    mutate(bad)
    assert any(fragment in e for e in errs(bad)), errs(bad)


def test_non_object_spec_is_rejected():
    assert errs([]) == ["la ficha debe ser un objeto JSON"]


# --- generador ----------------------------------------------------------------

def test_renderer_reproduces_the_gold_ig_rules_exactly():
    """Prueba central: del spec.json sale el mismo FSH (reglas) que el IG de referencia con 0 errores."""
    files = render_files(SPEC)
    for name in ("perfiles.fsh", "ejemplos.fsh", "aliases.fsh"):
        gold = (DEMO / "gold" / "input" / "fsh" / name).read_text(encoding="utf-8")
        assert rules(files[name]) == rules(gold), name


def test_renderer_is_deterministic():
    assert render_files(SPEC) == render_files(copy.deepcopy(SPEC))


def test_single_value_observation_renders_value_rules_and_example():
    spec = copy.deepcopy(SPEC)
    o = spec["observaciones"][0]
    o.update(nombre="CLTemperatura", id="cl-temperatura", codigo_loinc="8310-5", componentes=None,
             valor={"unidad": "°C", "ucum": "Cel"})
    o["ejemplo"].update(valores=None, valor=36.8)
    out = render_files(spec)
    assert "* valueQuantity 1..1 MS" in out["perfiles.fsh"] and "* valueQuantity.code = #Cel" in out["perfiles.fsh"]
    assert "* component" not in out["perfiles.fsh"]
    assert "* valueQuantity = 36.8 'Cel' \"°C\"" in out["ejemplos.fsh"]
    assert errs(spec) == []


def test_optional_component_and_optional_family_name():
    spec = copy.deepcopy(SPEC)
    spec["observaciones"][0]["componentes"][1]["obligatorio"] = False
    spec["paciente_ejemplo"].pop("segundo_apellido")
    out = render_files(spec)
    assert "sistolica 1..1 MS and diastolica 0..1 MS" in out["perfiles.fsh"]
    assert "segundoApellido" not in out["ejemplos.fsh"]


def test_quoting_helpers():
    assert q('di"jo') == '"di\\"jo"' and code("mm[Hg]") == '#"mm[Hg]"' and code("Cel") == "#Cel"
    assert num(128) == "128" and num(36.8) == "36.8" and num(90.0) == "90.0"


@pytest.mark.skipif(not REAL.is_file(), reason="ejecuta `make catalog` primero")
def test_demo_spec_and_rendered_fsh_pass_against_real_clcore():
    from agents.catalog import CatalogIndex
    from agents.base import STANDARD_ALIASES
    from validator.precheck import precheck_fsh
    cat = CatalogIndex.from_file(REAL)
    assert validate_spec(SPEC, cat, SPEC_TEXT) == []
    for name, text in render_files(SPEC).items():
        assert precheck_fsh(text, cat, STANDARD_ALIASES) == [], name


# --- mensajes del validador: deben decir QUÉ está mal y CÓMO arreglarlo (lo lee un modelo pequeño) ---

def test_validator_messages_name_the_offending_value_and_give_a_fix():
    import copy
    bad = copy.deepcopy(json.loads((Path("examples/demo/spec.json")).read_text(encoding="utf-8")))
    obs = bad["observaciones"][0]
    obs["componentes"][0]["nombre"] = "presion_sistolica"
    del obs["ejemplo"]["fecha"]
    errores = validate_spec(bad, mini_catalog(), (Path("examples/demo/spec.md")).read_text(encoding="utf-8"))
    nombre = next(e for e in errores if ".nombre:" in e)
    assert "'presion_sistolica'" in nombre and "guiones bajos" in nombre and "sistolica" in nombre
    fecha = next(e for e in errores if "ejemplo.fecha" in e)
    assert "falta" in fecha and "2026-03-15T09:30:00-03:00" in fecha
    obs["ejemplo"]["fecha"] = "15/03/2026"
    fecha = next(e for e in validate_spec(bad, mini_catalog()) if "ejemplo.fecha" in e)
    assert "'15/03/2026'" in fecha and "2026-03-15T09:30:00-03:00" in fecha


def test_analyst_prompt_states_the_rules_the_model_broke_in_measurement():
    from agents.analista import build_system
    system = build_system(mini_catalog())
    assert "SIN guiones bajos" in system and "presion_sistolica" in system and "`fecha`" in system


# --- completar_ficha: el código completa el andamiaje, nunca lo clínico ------------------------------

def _minima():
    return {"observaciones": [{"titulo": "Presión arterial", "descripcion": "Panel de presión arterial.",
                               "padre": "cl-core-signos-vitales", "codigo_loinc": "85354-9",
                               "componentes": [
                                   {"nombre": "sistolica", "etiqueta": "sistólica", "loinc": "8480-6",
                                    "unidad": "mmHg", "ucum": "mm[Hg]"},
                                   {"nombre": "diastolica", "etiqueta": "diastólica", "loinc": "8462-4",
                                    "unidad": "mmHg", "ucum": "mm[Hg]"}],
                               "ejemplo": {"valores": {"sistolica": 120, "diastolica": 80}}}]}


def test_completar_ficha_fills_scaffolding_and_the_result_validates():
    from generator.spec import completar_ficha
    entrada = _minima()
    ficha, notas = completar_ficha(entrada)
    assert entrada == _minima()                                   # no muta lo que recibe
    o = ficha["observaciones"][0]
    assert o["nombre"] == "CLPresionArterial" and o["id"] == "cl-presion-arterial"
    assert o["ejemplo"]["id"] == "PresionArterialEjemplo" and o["ejemplo"]["fecha"].endswith("-03:00")
    assert ficha["paciente_ejemplo"]["run"] == "11.111.111-1"
    assert "paciente_ejemplo" in notas and "observaciones[0].nombre" in notas
    spec_text = Path("examples/demo/spec.md").read_text(encoding="utf-8")
    assert validate_spec(ficha, mini_catalog(), spec_text) == []


def test_completar_ficha_never_overrides_or_invents_clinical_content():
    from generator.spec import completar_ficha
    dada = _minima()
    dada["observaciones"][0]["nombre"] = "CLMiPresion"
    dada["observaciones"][0]["ejemplo"].update(fecha="2024-01-02T03:04:05-03:00", id="MiEjemplo")
    dada["paciente_ejemplo"] = {"id": "PacienteX", "nombres": ["Ana"], "sexo": "Femenino"}
    ficha, notas = completar_ficha(dada)
    o = ficha["observaciones"][0]
    assert o["nombre"] == "CLMiPresion" and o["ejemplo"]["fecha"] == "2024-01-02T03:04:05-03:00" and o["ejemplo"]["id"] == "MiEjemplo"
    assert ficha["paciente_ejemplo"]["id"] == "PacienteX" and ficha["paciente_ejemplo"]["nombres"] == ["Ana"]
    assert ficha["paciente_ejemplo"]["sexo"] == "female" and ficha["paciente_ejemplo"]["run"] == "11.111.111-1"
    # lo clínico faltante NO se inventa: sigue siendo error para el modelo
    sin_codigo, _ = completar_ficha({**_minima(), "observaciones": [{**_minima()["observaciones"][0]}]})
    del sin_codigo["observaciones"][0]["codigo_loinc"]
    del sin_codigo["observaciones"][0]["ejemplo"]["valores"]
    errores = validate_spec(sin_codigo, mini_catalog())
    assert any("codigo_loinc: falta" in e and "no el de un componente" in e for e in errores)
    assert any("ejemplo.valores" in e for e in errores)


def test_completar_ficha_tolerates_garbage():
    from generator.spec import completar_ficha
    assert completar_ficha([1, 2]) == ([1, 2], [])
    ficha, _ = completar_ficha({"observaciones": [{"titulo": 5}, "x", {"titulo": "!!!"}]})
    assert ficha["observaciones"][1] == "x"


def test_pascal_and_kebab_strip_accents():
    from generator.spec import kebab, pascal
    assert pascal("Presión arterial (demo)") == "PresionArterialDemo" and kebab("Saturación de O2") == "saturacion-de-o2"


# --- regresión con la respuesta REAL del modelo local en la medición 3 (sintética, sin datos de personas) ---

FIXTURE_M3 = Path("tests/fixtures/ficha_modelo_medicion3.json")


def test_real_model_output_of_measurement_3_was_invalid_before_and_is_valid_after_completion():
    from generator.spec import completar_ficha
    spec_text = Path("examples/demo/spec.md").read_text(encoding="utf-8")
    cruda = json.loads(FIXTURE_M3.read_text(encoding="utf-8"))
    antes = validate_spec(cruda, mini_catalog(), spec_text)
    assert any("presion_sistolica" in e for e in antes) and any("ejemplo.valores" in e and "plural" in e for e in antes)
    ficha, notas = completar_ficha(cruda)
    assert validate_spec(ficha, mini_catalog(), spec_text) == []
    o = ficha["observaciones"][0]
    assert [c["nombre"] for c in o["componentes"]] == ["presionSistolica", "presionDiastolica"]
    assert o["ejemplo"]["valores"] == {"presionSistolica": 120, "presionDiastolica": 80} and "valor" not in o["ejemplo"]
    assert any("presion_sistolica" in n and "presionSistolica" in n for n in notas)
    assert render_files(ficha)          # y se puede renderizar a FSH


def test_completar_ficha_is_idempotent_and_leaves_valid_names_alone():
    from generator.spec import completar_ficha
    una, _ = completar_ficha(json.loads(FIXTURE_M3.read_text(encoding="utf-8")))
    dos, notas = completar_ficha(una)
    assert dos == una and notas == []
    ok = json.loads(Path("examples/demo/spec.json").read_text(encoding="utf-8"))
    ficha, notas = completar_ficha(ok)
    assert ficha == ok and notas == []                     # la ficha de referencia no se toca


def test_completar_ficha_recomputes_invalid_scaffolding_but_not_clinical_content():
    from generator.spec import completar_ficha
    f = json.loads(FIXTURE_M3.read_text(encoding="utf-8"))
    o = f["observaciones"][0]
    o["nombre"], o["id"], o["ejemplo"]["id"] = "clpresion arterial", "CL Presion", "presion-ejemplo"
    o["componentes"][0]["loinc"] = "9999-9"
    ficha, notas = completar_ficha(f)
    o2 = ficha["observaciones"][0]
    assert (o2["nombre"], o2["id"], o2["ejemplo"]["id"]) == ("CLPresionArterial", "cl-presion-arterial", "PresionArterialEjemplo")
    assert sum("recalculado" in n for n in notas) == 3
    assert o2["componentes"][0]["loinc"] == "9999-9"      # lo clínico se deja tal cual: el validador lo rechaza
    assert any("9999-9" in e for e in validate_spec(ficha, mini_catalog(), Path("examples/demo/spec.md").read_text(encoding="utf-8")))


def test_name_normalization_avoids_collisions():
    from generator.spec import completar_ficha
    f = json.loads(FIXTURE_M3.read_text(encoding="utf-8"))
    comps = f["observaciones"][0]["componentes"]
    comps[0]["nombre"], comps[1]["nombre"] = "presion_media", "presion-media"
    ficha, _ = completar_ficha(f)
    nombres = [c["nombre"] for c in ficha["observaciones"][0]["componentes"]]
    assert len(set(nombres)) == 2 and nombres[0] == "presionMedia"


def test_spo2_example_gets_the_fhir_mandatory_second_coding():
    """FHIR exige 2708-6 junto a 59408-5; lo agrega el renderizador, no el modelo."""
    from generator.render import render_files
    ficha = json.loads(Path("examples/casos/saturacion-oxigeno/spec.json").read_text(encoding="utf-8"))
    files = render_files(ficha)
    assert "* code = $LNC#59408-5" in files["perfiles.fsh"]
    assert "* code = $LNC#59408-5\n* code.coding[1] = $LNC#2708-6" in files["ejemplos.fsh"]
    assert "2708-6" not in files["perfiles.fsh"]
    otra = json.loads(Path("examples/casos/frecuencia-cardiaca/spec.json").read_text(encoding="utf-8"))
    assert "code.coding[1]" not in render_files(otra)["ejemplos.fsh"]
