"""Normalización de la FORMA de mediciones únicas (descubierta en la medición 5) y mensajes con ejemplo."""
import copy
import json
from pathlib import Path

from generator.spec import completar_ficha, validate_spec
from tests.test_catalog_precheck import mini_catalog

CASO = Path("examples/casos/peso-talla")
REF = json.loads((CASO / "spec.json").read_text(encoding="utf-8"))
TEXTO = (CASO / "spec.md").read_text(encoding="utf-8")


def como_panel_de_un_componente(ficha):
    """Lo que hizo el modelo local en la medición 5: cada medición única escrita como panel de 1 componente."""
    f = copy.deepcopy(ficha)
    for o in f["observaciones"]:
        nombre = o["nombre"][2:].lower()
        o["componentes"] = [{"nombre": nombre, "etiqueta": nombre, "loinc": o["codigo_loinc"],
                             "unidad": o["valor"]["unidad"], "ucum": o["valor"]["ucum"], "obligatorio": True}]
        del o["valor"]
        o["ejemplo"]["valores"] = {nombre: o["ejemplo"].pop("valor")}
    return f


def test_single_component_panel_with_the_observation_loinc_becomes_a_single_value():
    cruda = como_panel_de_un_componente(REF)
    assert any("al menos 2 componentes" in e for e in validate_spec(cruda, mini_catalog(), TEXTO))
    ficha, notas = completar_ficha(cruda)
    assert validate_spec(ficha, mini_catalog(), TEXTO) == []
    for o, ref in zip(ficha["observaciones"], REF["observaciones"]):
        assert o["valor"] == ref["valor"] and o["ejemplo"]["valor"] == ref["ejemplo"]["valor"]
        assert "componentes" not in o and "valores" not in o["ejemplo"]
    assert sum("un solo componente" in n for n in notas) == 2


def test_single_component_with_a_different_loinc_is_not_guessed():
    cruda = como_panel_de_un_componente(REF)
    cruda["observaciones"][0]["componentes"][0]["loinc"] = "8302-2"     # distinto del código de la observación
    ficha, _ = completar_ficha(cruda)
    assert "componentes" in ficha["observaciones"][0]                    # no se adivina: sigue siendo error
    assert any("al menos 2 componentes" in e for e in validate_spec(ficha, mini_catalog(), TEXTO))


def test_loose_unit_fields_and_null_components_are_lifted_into_valor():
    cruda = copy.deepcopy(REF)
    for o in cruda["observaciones"]:
        o["unidad"], o["ucum"], o["obligatorio"], o["componentes"] = o["valor"]["unidad"], o["valor"]["ucum"], True, None
        del o["valor"]
    ficha, notas = completar_ficha(cruda)
    assert validate_spec(ficha, mini_catalog(), TEXTO) == []
    assert ficha["observaciones"][0]["valor"] == REF["observaciones"][0]["valor"]
    assert all(k not in ficha["observaciones"][0] for k in ("unidad", "ucum", "obligatorio", "componentes"))
    assert sum("se subieron a `valor`" in n for n in notas) == 2


def test_unit_object_inside_the_example_is_not_invented_away():
    """Confusión real de la medición 5: el ejemplo lleva el objeto de unidad en vez de un número. Falta contenido
    clínico (el valor medido): el código no lo inventa y el mensaje le muestra al modelo cómo corregirlo."""
    mala = copy.deepcopy(REF)
    mala["observaciones"][0]["ejemplo"]["valor"] = {"unidad": "kg", "ucum": "kg"}
    ficha, _ = completar_ficha(mala)
    error = next(e for e in validate_spec(ficha, mini_catalog(), TEXTO) if "ejemplo.valor" in e)
    assert "solo un número" in error and "por ejemplo 70" in error


def test_messages_show_a_correct_example_for_single_values():
    mala = copy.deepcopy(REF)
    mala["observaciones"][0]["valor"] = 70
    del mala["observaciones"][1]["valor"]
    errores = validate_spec(mala, mini_catalog(), TEXTO)
    assert any(".valor:" in e and '{"unidad": "kg", "ucum": "kg"}' in e for e in errores)
    assert any("define o bien" in e and '"valor": {"unidad"' in e for e in errores)


def test_reference_fichas_of_every_case_are_untouched_by_completion():
    for ruta in sorted(Path("examples/casos").glob("*/spec.json")):
        ficha = json.loads(ruta.read_text(encoding="utf-8"))
        assert completar_ficha(ficha) == (ficha, []), ruta
