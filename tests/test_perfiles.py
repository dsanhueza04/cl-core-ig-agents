"""Pruebas del agente de perfiles con modelo simulado (sin red, sin costo)."""
from pathlib import Path

import pytest

from agents.perfiles import ProfileAgent, aliases_fsh, build_system, extract_fsh, main
from llm import LLMClient, MockBackend
from tests.test_catalog_precheck import BASE, mini_catalog

GOOD = f"""Profile: CLX
Parent: CorePacienteCl
Id: cl-x
Title: "X"
Description: "X"
* extension contains {BASE}/StructureDefinition/ComunasCl named comuna 0..1
"""
BAD = GOOD.replace("ComunasCl", "ComunaCl")


def agent(responses, tmp_path, **kw):
    backend = MockBackend(responses)
    client = LLMClient(backend, log_path=tmp_path / "log.jsonl")
    return ProfileAgent(client, mini_catalog(), **kw), backend


def fenced(text):
    return f"Aquí va:\n```fsh\n{text}```\nlisto"


def test_extract_fsh_takes_fenced_block_or_whole_text():
    assert extract_fsh(fenced("Profile: A\n")) == "Profile: A\n"
    assert extract_fsh("Profile: A") == "Profile: A\n"
    assert extract_fsh("```\nProfile: A\n```") == "Profile: A\n"


def test_prompt_contains_rules_example_aliases_catalog_and_version():
    system = build_system("paciente con comuna", mini_catalog())
    assert "FHIR R4" in system and "CLTemperaturaCorporal" in system
    assert "$LNC" in system and "CorePacienteCl" in system and "1.9.3" in system


def test_clean_first_answer_needs_one_call(tmp_path):
    ag, backend = agent([fenced(GOOD)], tmp_path)
    r = ag.generate("spec")
    assert r.clean and r.attempts == 1 and len(backend.calls) == 1 and "ComunasCl" in r.fsh


def test_invented_reference_is_sent_back_and_fixed(tmp_path):
    ag, backend = agent([fenced(BAD), fenced(GOOD)], tmp_path)
    r = ag.generate("spec")
    assert r.clean and r.attempts == 2
    feedback = backend.calls[1]["messages"][-1]["content"]
    assert "ComunaCl" in feedback and "ComunasCl" in feedback  # error y sugerencia
    assert backend.calls[1]["messages"][-2]["role"] == "assistant"


def test_gives_up_after_max_fixes_and_reports_remaining_issues(tmp_path):
    ag, backend = agent([fenced(BAD)] * 5, tmp_path, max_fixes=1)
    r = ag.generate("spec")
    assert not r.clean and r.attempts == 2 and len(backend.calls) == 2 and r.issues


def test_calls_are_logged_under_agent_name(tmp_path):
    ag, _ = agent([fenced(GOOD)], tmp_path)
    ag.generate("spec")
    assert ag.client.summary()["by_agent"]["perfiles"]["calls"] == 1


def test_aliases_file_declares_standard_aliases():
    text = aliases_fsh()
    assert "Alias: $LNC = http://loinc.org" in text and text.count("Alias:") == 4


def test_cli_mock_mode_writes_files_and_warns(tmp_path, monkeypatch, capsys):
    import json
    cat = tmp_path / "c.json"
    cat.write_text(json.dumps(mini_catalog().data), encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text("# spec", encoding="utf-8")
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    code = main(["--spec", str(spec), "--out", str(tmp_path / "fsh"), "--catalog", str(cat)])
    assert code == 0
    assert (tmp_path / "fsh" / "aliases.fsh").is_file()
    assert "CLTemperaturaCorporal" in (tmp_path / "fsh" / "perfiles.fsh").read_text(encoding="utf-8")
    assert "modo simulado" in capsys.readouterr().err
