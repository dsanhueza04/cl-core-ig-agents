"""Pruebas del agente de ejemplos y del pipeline completo (modelo simulado, sin Docker)."""
import json

from agents.ejemplos import ExampleAgent, build_system
from agents.generate import derive_meta, generate_ig, generate_ig_libre, main, render_skeleton
from agents.loop import Outcome
from llm import LLMClient, MockBackend
from tests.test_catalog_precheck import BASE, mini_catalog
from validator.parse_qa import QAReport

SPEC = "# Especificación de entrada (demo): registro de presión arterial\n\n| Campo | ... |\n"
PROFILE = "Profile: CLX\nParent: CorePacienteCl\nId: cl-x\nTitle: \"X\"\nDescription: \"X\"\n"
EXAMPLES = "Instance: P1\nInstanceOf: CorePacienteCl\nUsage: #example\n"


def fenced(text):
    return f"```fsh\n{text}```"


def client(responses, tmp_path):
    backend = MockBackend(responses)
    return LLMClient(backend, log_path=tmp_path / "l.jsonl"), backend


def ok_validate(files):
    return Outcome(report=QAReport())


# --- metadatos y esqueleto ----------------------------------------------------

def test_derive_meta_from_spec_heading():
    m = derive_meta(SPEC)
    assert m["title"] == "Registro de presión arterial"
    assert m["name"] == "RegistroDePresionArterial"
    assert m["id"] == "ig.cl.registrodepresionarterial"
    assert m["canonical"] == "https://example.org/fhir/ig/registro-de-presion-arterial"


def test_derive_meta_explicit_values_win():
    m = derive_meta(SPEC, id="mi.ig", title="Otro", canonical="https://x.cl/ig")
    assert (m["id"], m["title"], m["canonical"]) == ("mi.ig", "Otro", "https://x.cl/ig")


def test_skeleton_fills_all_placeholders_and_points_to_clcore(tmp_path):
    render_skeleton(tmp_path, derive_meta(SPEC))
    texts = {p.name: p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file()}
    assert {"sushi-config.yaml", "ig.ini", "index.md", "ignoreWarnings.txt"} <= set(texts)
    assert not any("{{" in t for t in texts.values())
    assert "hl7.fhir.cl.clcore: 1.9.3" in texts["sushi-config.yaml"] and "fhirVersion: 4.0.1" in texts["sushi-config.yaml"]
    assert "ImplementationGuide-ig.cl.registrodepresionarterial.json" in texts["ig.ini"]


# --- agente de ejemplos -------------------------------------------------------

def test_example_prompt_has_rules_catalog_and_profiles(tmp_path):
    c, backend = client([fenced(EXAMPLES)], tmp_path)
    r = ExampleAgent(c, mini_catalog()).generate(SPEC, PROFILE)
    assert r.clean and "Instance: P1" in r.fsh
    system, user = backend.calls[0]["system"], backend.calls[0]["messages"][0]["content"]
    assert "ficticios" in system and "CorePacienteCl" in system and "TemperaturaEjemplo" in system
    assert "Profile: CLX" in user


def test_example_agent_fixes_invented_reference(tmp_path):
    bad = EXAMPLES + f"* extension contains {BASE}/StructureDefinition/ComunaCl named c 0..1\n"
    c, backend = client([fenced(bad), fenced(EXAMPLES)], tmp_path)
    r = ExampleAgent(c, mini_catalog()).generate(SPEC, PROFILE)
    assert r.clean and r.attempts == 2 and "ComunasCl" in backend.calls[1]["messages"][-1]["content"]


def test_example_system_prompt_is_small_enough_for_local_models():
    assert len(build_system(SPEC, mini_catalog())) < 8000


# --- pipeline ---------------------------------------------------------------------

def test_pipeline_writes_ig_with_three_fsh_files_and_reports(tmp_path):
    c, backend = client([fenced(PROFILE), fenced(EXAMPLES)], tmp_path)
    res = generate_ig_libre(SPEC, tmp_path / "run", c, mini_catalog(), ok_validate)
    assert res.status == "ok" and len(backend.calls) == 2
    fsh = tmp_path / "run" / "ig" / "input" / "fsh"
    assert sorted(p.name for p in fsh.glob("*.fsh")) == ["aliases.fsh", "ejemplos.fsh", "perfiles.fsh"]
    assert "Alias: $LNC" in (fsh / "aliases.fsh").read_text(encoding="utf-8")
    assert (tmp_path / "run" / "ig" / "sushi-config.yaml").is_file()
    assert res.generation["perfiles"]["intentos"] == 1 and res.generation["ejemplos"]["intentos"] == 1


def test_pipeline_skip_examples(tmp_path):
    c, backend = client([fenced(PROFILE)], tmp_path)
    res = generate_ig_libre(SPEC, tmp_path / "run", c, mini_catalog(), ok_validate, skip_examples=True)
    assert res.status == "ok" and len(backend.calls) == 1 and "ejemplos.fsh" not in res.files


def test_pipeline_repairs_after_validation_failure(tmp_path):
    """El validador falla mientras el perfil diga 'MAL'; el reparador lo corrige con un parche."""
    bad_profile = PROFILE + "// MAL\n"
    fix = "### archivo: perfiles.fsh\n<<<<<<< BUSCAR\n// MAL\n=======\n// bien\n>>>>>>> REEMPLAZAR\n"
    from validator.parse_qa import Issue, _fingerprint

    def validate(files):
        if "MAL" in files["perfiles.fsh"]:
            r = QAReport()
            r.issues = [Issue("error", "content", "hay un MAL", fingerprint=_fingerprint("error", None, None, "mal"))]
            return Outcome(report=r)
        return Outcome(report=QAReport())

    c, backend = client([fenced(bad_profile), fenced(EXAMPLES), fix], tmp_path)
    res = generate_ig_libre(SPEC, tmp_path / "run", c, mini_catalog(), validate)
    assert res.status == "ok" and "// bien" in (tmp_path / "run" / "ig" / "input" / "fsh" / "perfiles.fsh").read_text(encoding="utf-8")


def test_cli_without_docker_writes_report_and_marks_draft(tmp_path, monkeypatch, capsys):
    cat = tmp_path / "c.json"
    cat.write_text(json.dumps(mini_catalog().data), encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text(SPEC, encoding="utf-8")
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    # modo simulado: respuestas "(respuesta simulada)" no tienen referencias a CL Core, el chequeo previo pasa
    code = main(["--spec", str(spec), "--modo", "libre", "--runs", str(tmp_path / "runs"), "--catalog", str(cat), "--sin-docker"])
    out = capsys.readouterr()
    assert code == 0 and "BORRADOR" in out.out and "modo simulado" in out.err
    report = json.loads(next((tmp_path / "runs").glob("*/informe.json")).read_text(encoding="utf-8"))
    assert report["status"] == "ok" and report["borrador"] == "requiere revisión humana"


def test_example_prompt_always_has_patient_and_parent_cards():
    system = build_system(SPEC, mini_catalog(), "Profile: A\nParent: cl-core-signos-vitales\n")
    assert "### CorePacienteCl" in system and "### cl-core-signos-vitales" in system


def test_pipeline_survives_model_timeout_and_keeps_partial_work(tmp_path):
    from llm import LLMUnavailable

    class Dies:
        name, paid, calls = "mock", False, 0

        def complete(self, **kw):
            self.calls += 1
            if self.calls == 1:
                from llm import Usage
                return fenced(PROFILE), Usage()
            raise LLMUnavailable("tiempo agotado")

    c = LLMClient(Dies(), log_path=tmp_path / "l.jsonl")
    res = generate_ig_libre(SPEC, tmp_path / "run", c, mini_catalog(), ok_validate)
    assert res.status == "modelo_no_responde" and "perfiles.fsh" in res.files
    assert (tmp_path / "run" / "ig" / "input" / "fsh" / "perfiles.fsh").is_file()
