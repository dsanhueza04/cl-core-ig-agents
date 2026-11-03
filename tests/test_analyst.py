"""Pruebas del analista y del pipeline estructurado (modelo simulado, sin Docker)."""
import json
from pathlib import Path

import pytest

from agents.analista import AnalystAgent, build_system, extract_json
from agents.generate import generate_ig, main
from agents.loop import Outcome
from generator.render import render_files
from generator.spec import validate_spec
from llm import LLMClient, MockBackend
from tests.test_catalog_precheck import mini_catalog
from validator.parse_qa import QAReport

DEMO = Path("examples/demo")
FICHA = json.loads((DEMO / "spec.json").read_text(encoding="utf-8"))
SPEC_TEXT = (DEMO / "spec.md").read_text(encoding="utf-8")


def reply(obj):
    return json.dumps(obj, ensure_ascii=False)


def client(responses, tmp_path):
    backend = MockBackend(responses)
    return LLMClient(backend, log_path=tmp_path / "l.jsonl"), backend


def ok_validate(files):
    return Outcome(report=QAReport())


def rules(text, skip=("Title:", "Description:", "* component ^slicing.description")):
    return [ln for ln in text.splitlines() if ln.strip() and not ln.startswith(skip)]


# --- extracción de JSON ---------------------------------------------------------

def test_extract_json_from_fenced_block_plain_text_and_noise():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Claro: {"a": 1} listo') == {"a": 1}


def test_extract_json_errors():
    with pytest.raises(ValueError, match="no contiene"):
        extract_json("sin json")
    with pytest.raises(ValueError, match="JSON inválido"):
        extract_json('{"a": }')


# --- analista -----------------------------------------------------------------------

def test_prompt_example_is_itself_a_valid_ficha_and_prompt_is_small():
    example = json.loads(Path("prompts/ejemplo_spec.json").read_text(encoding="utf-8"))
    assert validate_spec(example, mini_catalog()) == []
    assert len(build_system(mini_catalog())) < 5000


def test_analyst_valid_first_time_uses_json_mode(tmp_path):
    c, backend = client([reply(FICHA)], tmp_path)
    r = AnalystAgent(c, mini_catalog()).generate(SPEC_TEXT)
    assert r.valid and r.attempts == 1 and backend.calls[0]["json_mode"] is True
    assert "Especificación:" in backend.calls[0]["messages"][0]["content"]


def test_analyst_gets_feedback_and_fixes_invented_code(tmp_path):
    bad = json.loads(reply(FICHA))
    bad["observaciones"][0]["componentes"][0]["loinc"] = "9999-9"   # no está en la especificación
    c, backend = client([reply(bad), reply(FICHA)], tmp_path)
    r = AnalystAgent(c, mini_catalog()).generate(SPEC_TEXT)
    assert r.valid and r.attempts == 2
    assert "9999-9" in backend.calls[1]["messages"][-1]["content"] and "no inventes" in backend.calls[1]["messages"][-1]["content"]


def test_analyst_handles_broken_json_then_gives_up(tmp_path):
    c, backend = client(["{esto no es json}"] * 5, tmp_path)
    r = AnalystAgent(c, mini_catalog(), max_fixes=1).generate(SPEC_TEXT)
    assert not r.valid and r.spec is None and r.attempts == 2 and "JSON inválido" in r.errors[0]
    assert len(backend.calls) == 2


# --- pipeline estructurado --------------------------------------------------------------

def test_structured_pipeline_end_to_end_matches_gold(tmp_path):
    c, backend = client([reply(FICHA)], tmp_path)
    res = generate_ig(SPEC_TEXT, tmp_path / "run", c, mini_catalog(), ok_validate)
    assert res.status == "ok" and len(backend.calls) == 1
    fsh = tmp_path / "run" / "ig" / "input" / "fsh"
    for name in ("perfiles.fsh", "ejemplos.fsh"):
        gold = (DEMO / "gold" / "input" / "fsh" / name).read_text(encoding="utf-8")
        assert rules((fsh / name).read_text(encoding="utf-8")) == rules(gold), name
    assert json.loads((tmp_path / "run" / "spec.json").read_text(encoding="utf-8")) == FICHA
    assert (tmp_path / "run" / "ig" / "sushi-config.yaml").is_file()
    assert res.generation["analista"]["intentos"] == 1 and res.generation["modo"] == "estructurado"


def test_pipeline_with_given_ficha_needs_no_model(tmp_path):
    c, backend = client([], tmp_path)
    res = generate_ig(SPEC_TEXT, tmp_path / "run", c, mini_catalog(), ok_validate, ficha=FICHA)
    assert res.status == "ok" and backend.calls == []


def test_pipeline_rejects_invalid_ficha_with_clear_status(tmp_path):
    bad = json.loads(reply(FICHA))
    bad["observaciones"][0]["padre"] = "cl-core-inexistente"
    c, backend = client([], tmp_path)
    res = generate_ig(SPEC_TEXT, tmp_path / "run", c, mini_catalog(), ok_validate, ficha=bad)
    assert res.status == "ficha_invalida" and not (tmp_path / "run" / "ig" / "input" / "fsh").exists()
    assert any("no existe en CL Core" in e for e in res.generation["ficha_entregada"]["problemas"])


def test_pipeline_reports_invalid_analyst_output_and_keeps_draft(tmp_path):
    bad = json.loads(reply(FICHA))
    bad["paciente_ejemplo"]["sexo"] = "robot"
    c, _ = client([reply(bad)] * 5, tmp_path)
    res = generate_ig(SPEC_TEXT, tmp_path / "run", c, mini_catalog(), ok_validate)
    assert res.status == "ficha_invalida"
    assert (tmp_path / "run" / "spec.json").is_file()   # el borrador queda para depurar
    assert res.generation["analista"]["problemas"]


def test_pipeline_survives_model_timeout_in_analyst(tmp_path):
    from llm import LLMUnavailable

    class Dead:
        name, paid = "mock", False

        def complete(self, **kw):
            raise LLMUnavailable("tiempo agotado")

    res = generate_ig(SPEC_TEXT, tmp_path / "run", LLMClient(Dead(), log_path=tmp_path / "l.jsonl"),
                      mini_catalog(), ok_validate)
    assert res.status == "modelo_no_responde"


def test_cli_spec_json_without_model_or_docker(tmp_path, monkeypatch, capsys):
    cat = tmp_path / "c.json"
    cat.write_text(json.dumps(mini_catalog().data), encoding="utf-8")
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    code = main(["--spec-json", str(DEMO / "spec.json"), "--runs", str(tmp_path / "runs"), "--catalog", str(cat),
                 "--sin-docker"])
    assert code == 0
    out = capsys.readouterr()
    assert "estado: ok" in out.out and "llamadas al modelo: 0" in out.out and "modo simulado" not in out.err
    report = json.loads(next((tmp_path / "runs").glob("*/informe.json")).read_text(encoding="utf-8"))
    assert report["status"] == "ok" and report["llm"]["calls"] == 0


def test_cli_requires_spec_or_spec_json(tmp_path):
    with pytest.raises(SystemExit):
        main(["--runs", str(tmp_path)])


def test_analyst_accepts_minimal_ficha_and_reports_what_code_completed(tmp_path):
    minima = json.loads(reply(FICHA))
    del minima["paciente_ejemplo"]
    obs = minima["observaciones"][0]
    for k in ("nombre", "id"):
        del obs[k]
    for k in ("id", "titulo", "descripcion", "fecha"):
        del obs["ejemplo"][k]
    c, backend = client([reply(minima)], tmp_path)
    r = AnalystAgent(c, mini_catalog()).generate(SPEC_TEXT)
    assert r.valid and r.attempts == 1 and len(backend.calls) == 1
    assert "paciente_ejemplo" in r.completed and "observaciones[0].ejemplo.fecha" in r.completed
    assert r.spec["observaciones"][0]["nombre"] == "CLPresionArterialDemo"


def test_pipeline_report_lists_code_completed_fields(tmp_path):
    minima = json.loads(reply(FICHA))
    del minima["paciente_ejemplo"]
    c, _ = client([reply(minima)], tmp_path)
    res = generate_ig(SPEC_TEXT, tmp_path / "run", c, mini_catalog(), ok_validate)
    assert res.status == "ok" and res.generation["analista"]["autocompletado_por_codigo"] == ["paciente_ejemplo"]


def test_prompt_demands_panel_code_and_allows_omitting_scaffolding():
    system = build_system(mini_catalog())
    assert "código de la observación COMPLETA" in system and "Puedes omitir `paciente_ejemplo`" in system
