"""Pruebas del script de medición (modelo simulado, sin Docker)."""
import copy
import json
from pathlib import Path

import pytest

from agents.analista import AnalystAgent
from llm import LLMClient, LLMUnavailable, MockBackend
from scripts import medir
from tests.test_catalog_precheck import mini_catalog

DEMO = Path("examples/demo")
FICHA = json.loads((DEMO / "spec.json").read_text(encoding="utf-8"))
SPEC_TEXT = (DEMO / "spec.md").read_text(encoding="utf-8")


def reply(obj):
    return json.dumps(obj, ensure_ascii=False)


def con_codigo_inventado():
    """Un error que el código NO puede arreglar (es clínico): el modelo debe corregirlo con la retroalimentación."""
    bad = copy.deepcopy(FICHA)
    bad["observaciones"][0]["componentes"][0]["loinc"] = "9999-9"
    return bad


# --- categorías de error: con los mensajes reales del validador -------------------------------

@pytest.mark.parametrize("mensaje, esperada", [
    ("observaciones[0].componentes[0].nombre: 'presion_sistolica' no vale: debe empezar con minúscula y tener solo letras o números", "formato_identificador"),
    ("observaciones[0].ejemplo.valores: objeto con un número por componente (sistolica, diastolica)", "valores_ejemplo"),
    ("observaciones[0].componentes[0]: el código '9999-9' no aparece en la especificación; no inventes códigos.", "codigo_inventado"),
    ("JSON inválido: Expecting value", "json_invalido"),
    ("observaciones[0].padre: 'x' no existe en CL Core 1.9.3", "perfil_padre"),
    ("observaciones[0].componentes[0].ucum: código UCUM inválido 'mmhg'", "unidad_ucum"),
    ("algo que nadie previó", "otro"),
])
def test_categoria(mensaje, esperada):
    assert medir.categoria(mensaje) == esperada


# --- firma estructural ------------------------------------------------------------------------

def test_signature_ignores_texts_example_and_patient_but_not_structure():
    otra = copy.deepcopy(FICHA)
    otra["paciente_ejemplo"]["nombres"] = ["Laura"]
    otra["observaciones"][0]["titulo"] = "Otro título"
    otra["observaciones"][0]["ejemplo"]["valores"] = {"sistolica": 120, "diastolica": 80}
    otra["observaciones"][0]["componentes"][0]["nombre"] = "sys"
    otra["observaciones"][0]["componentes"][0]["unidad"] = "milímetros de mercurio"   # texto de la unidad: cosmético
    assert medir.firma_estructural(otra) == medir.firma_estructural(FICHA)
    for cambio in (lambda f: f["observaciones"][0]["componentes"][0].update(ucum="kPa"),
                   lambda f: f["observaciones"][0]["componentes"][1].update(obligatorio=False),
                   lambda f: f["observaciones"][0]["componentes"][1].update(loinc="9999-9")):
        rota = copy.deepcopy(FICHA)
        cambio(rota)
        assert medir.firma_estructural(rota) != medir.firma_estructural(FICHA)


# --- estadística -----------------------------------------------------------------------------

def test_wilson_interval_known_values():
    assert medir.wilson(0, 0) == (0.0, 0.0)
    lo, hi = medir.wilson(5, 5)
    assert hi == 1.0 and lo == pytest.approx(0.5655, abs=1e-3)
    lo, hi = medir.wilson(0, 5)
    assert lo == 0.0 and hi == pytest.approx(0.4345, abs=1e-3)


def test_percentil():
    assert medir.percentil([], 0.95) == 0.0
    assert medir.percentil([10], 0.95) == 10
    assert medir.percentil([1, 2, 3, 4, 5], 0.5) == 3
    assert medir.percentil([1, 2, 3, 4, 5], 0.95) == pytest.approx(4.8)


# --- una corrida -----------------------------------------------------------------------------

def test_ejecutar_una_records_retries_and_structure(tmp_path):
    client = LLMClient(MockBackend([reply(con_codigo_inventado()), reply(FICHA)]), log_path=tmp_path / "l.jsonl")
    agente = AnalystAgent(client, mini_catalog())
    fila = medir.ejecutar_una(agente, client, SPEC_TEXT, medir.firma_estructural(FICHA))
    assert fila["valida"] and fila["intentos"] == 2 and fila["estructura_igual"] is True
    assert len(fila["errores_por_intento"]) == 2 and fila["errores_por_intento"][1] == []
    assert any(medir.categoria(e) == "codigo_inventado" for e in fila["errores_por_intento"][0])
    assert fila["autocompletados"] == 0
    assert fila["tokens_entrada"] > 0 and fila["tokens_salida"] > 0 and fila["ficha_hash"]


def test_ejecutar_una_invalid_has_no_hash_or_structure(tmp_path):
    client = LLMClient(MockBackend(["{esto no es json}"] * 3), log_path=tmp_path / "l.jsonl")
    fila = medir.ejecutar_una(AnalystAgent(client, mini_catalog()), client, SPEC_TEXT, medir.firma_estructural(FICHA))
    assert not fila["valida"] and fila["intentos"] == 3 and fila["ficha_hash"] == "" and fila["estructura_igual"] is None


# --- programa completo -----------------------------------------------------------------------

@pytest.fixture
def entorno(tmp_path, monkeypatch):
    cat = tmp_path / "catalog.json"
    cat.write_text(json.dumps(mini_catalog().data), encoding="utf-8")

    def usar(respuestas):
        backend = MockBackend(respuestas)
        monkeypatch.setattr(medir, "client_from_env", lambda **kw: LLMClient(backend, **kw))
        return backend
    return cat, usar


def test_main_writes_csv_summary_and_fichas(tmp_path, entorno):
    cat, usar = entorno
    usar([reply(FICHA), reply(con_codigo_inventado()), reply(FICHA), reply(FICHA)])
    code = medir.main(["--spec", str(DEMO / "spec.md"), "--n", "3", "--catalog", str(cat), "--runs", str(tmp_path / "runs")])
    assert code == 0
    carpeta = next((tmp_path / "runs").glob("medicion-*"))
    filas = (carpeta / "resultados.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(filas) == 1 + 3
    r = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    assert r["corridas"] == 3 and r["validas"] == 3 and r["a_la_primera"] == 2 and r["a_la_primera_sin_ayuda"] == 2
    assert r["estructura_igual"] == "3/3" and r["intentos_distribucion"] == {"1": 2, "2": 1}
    assert r["errores_atrapados_por_categoria"].get("codigo_inventado", 0) >= 1
    assert r["casos"] == ["demo"] and r["tasa_valida_ic95"][0] < 1.0
    md = (carpeta / "resumen.md").read_text(encoding="utf-8")
    assert "revisión humana" in md and "3/3" in md
    assert len(list((carpeta / "fichas").glob("*.json"))) == 3


def test_main_counts_failures_and_still_summarizes(tmp_path, entorno):
    cat, usar = entorno
    usar(["{esto no es json}"] * 9)
    assert medir.main(["--spec", str(DEMO / "spec.md"), "--n", "2", "--catalog", str(cat), "--runs", str(tmp_path / "r")]) == 0
    r = json.loads(next((tmp_path / "r").glob("medicion-*/resumen.json")).read_text(encoding="utf-8"))
    assert r["validas"] == 0 and r["fichas_distintas"] == 0 and r["errores_atrapados_por_categoria"]["json_invalido"] == 6


def test_main_stops_cleanly_when_model_is_down(tmp_path, entorno, capsys):
    cat, usar = entorno

    def caido(**_):
        raise LLMUnavailable("sin respuesta")
    usar(caido)
    assert medir.main(["--spec", str(DEMO / "spec.md"), "--n", "3", "--catalog", str(cat), "--runs", str(tmp_path / "r")]) == 1
    err = capsys.readouterr().err
    assert "sin respuesta" in err and "Traceback" not in err


def test_main_respects_time_limit_and_missing_catalog(tmp_path, entorno):
    cat, usar = entorno
    backend = usar([reply(FICHA)] * 3)
    assert medir.main(["--spec", str(DEMO / "spec.md"), "--n", "3", "--max-minutos", "0", "--catalog", str(cat),
                       "--runs", str(tmp_path / "r")]) == 1 and backend.calls == []
    assert medir.main(["--spec", str(DEMO / "spec.md"), "--catalog", str(tmp_path / "no.json")]) == 2
