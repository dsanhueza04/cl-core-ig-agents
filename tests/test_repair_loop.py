"""Pruebas del reparador, los parches, la detección de trampa y el bucle (todo con modelo simulado)."""
import pytest

from agents.loop import Outcome, run_loop
from agents.patches import apply_patches, parse_patches
from agents.reparador import RepairAgent
from llm import BudgetExceeded, LLMClient, MockBackend
from tests.test_catalog_precheck import BASE, mini_catalog
from validator.degradation import cardinalities, degradations
from validator.parse_qa import Issue, QAReport, _fingerprint
from validator.parse_sushi import parse_sushi_text


def patch(file, old, new):
    return f"### archivo: {file}\n<<<<<<< BUSCAR\n{old}\n=======\n{new}\n>>>>>>> REEMPLAZAR\n"


# --- parches ----------------------------------------------------------------

def test_parse_and_apply_patch():
    text = "explicación\n" + patch("a.fsh", "* x 1..1", "* x 1..1 MS") + patch("a.fsh", "Id: a", "Id: b")
    ps = parse_patches(text)
    assert [p.new for p in ps] == ["* x 1..1 MS", "Id: b"]
    new, fail = apply_patches({"a.fsh": "Id: a\n* x 1..1\n"}, ps)
    assert new["a.fsh"] == "Id: b\n* x 1..1 MS\n" and fail == []


def test_apply_reports_missing_file_missing_text_and_ambiguity():
    ps = parse_patches(patch("z.fsh", "a", "b") + patch("a.fsh", "nada", "b") + patch("a.fsh", "x", "y"))
    new, fail = apply_patches({"a.fsh": "x\nx\n"}, ps)
    assert new == {"a.fsh": "x\nx\n"} and len(fail) == 3
    assert "no existe" in fail[0] and "no aparece" in fail[1] and "2 veces" in fail[2]


# --- trampa -----------------------------------------------------------------

BEFORE = "* component contains sistolica 1..1 MS and diastolica 1..1 MS\n* valueQuantity 1..1 MS\n"


def test_cardinalities_reads_plain_and_contains_rules():
    c = cardinalities(BEFORE)
    assert c["valueQuantity"] == (1, "1")
    assert c["component[sistolica]"] == (1, "1") and c["component[diastolica]"] == (1, "1")


def test_degradation_detects_lowered_min_raised_max_and_deleted_rule():
    assert degradations(BEFORE, BEFORE) == []
    assert degradations(BEFORE, BEFORE.replace("valueQuantity 1..1", "valueQuantity 0..1"))
    assert degradations(BEFORE, BEFORE.replace("valueQuantity 1..1", "valueQuantity 1..*"))
    assert degradations(BEFORE, "* valueQuantity 1..1 MS\n")
    assert degradations("* a 0..*\n", "* a 1..1\n") == []   # endurecer no es trampa


# --- SUSHI ------------------------------------------------------------------

SUSHI = """\x1b[31merror\x1b[0m Cannot resolve parent CorePacienteCL
  File: /ig/input/fsh/perfiles.fsh
  Line: 12 - 14

warn Something minor
  File: /ig/input/fsh/perfiles.fsh
  Line: 3
"""


def test_parse_sushi_errors_only_with_file_and_line():
    issues = parse_sushi_text(SUSHI)
    assert len(issues) == 1 and issues[0].kind == "content"
    assert issues[0].section == "perfiles.fsh" and issues[0].path == "perfiles.fsh:12"


# --- reparador ---------------------------------------------------------------

FILES = {"perfiles.fsh": "Profile: A\nParent: Patient\n* identifier 1..1 MS\n"}


def make_repairer(responses, tmp_path):
    backend = MockBackend(responses)
    return RepairAgent(LLMClient(backend, log_path=tmp_path / "l.jsonl"), mini_catalog()), backend


def test_repairer_applies_patch_and_prompt_has_problem_and_file(tmp_path):
    from agents.reparador import Problem
    rep, backend = make_repairer([patch("perfiles.fsh", "Parent: Patient", "Parent: CorePacienteCl")], tmp_path)
    r = rep.repair(FILES, [Problem("sushi", "No existe Patient2", file="perfiles.fsh", line=2)])
    assert r.changed and r.applied == 1 and "CorePacienteCl" in r.files["perfiles.fsh"]
    user = backend.calls[0]["messages"][0]["content"]
    assert "No existe Patient2" in user and "Parent: Patient" in user


def test_repairer_rejects_cheating_patch_entirely(tmp_path):
    from agents.reparador import Problem
    rep, _ = make_repairer([patch("perfiles.fsh", "* identifier 1..1 MS", "* identifier 0..1 MS")], tmp_path)
    r = rep.repair(FILES, [Problem("publisher", "error")])
    assert not r.changed and r.files == FILES and "debilitar" in r.failures[0]


def test_repairer_handles_reply_without_patches(tmp_path):
    from agents.reparador import Problem
    rep, _ = make_repairer(["no sé"], tmp_path)
    r = rep.repair(FILES, [Problem("publisher", "error")])
    assert not r.changed and "formato" in r.failures[0]


# --- bucle -------------------------------------------------------------------

def content_issue(msg):
    return Issue("error", "content", msg, fingerprint=_fingerprint("error", None, None, msg))


def report_with(*issues):
    r = QAReport()
    r.issues = list(issues)
    return r


class FakeValidator:
    """Falla mientras el texto 'BUG' siga en perfiles.fsh; permite simular infraestructura."""

    def __init__(self, infra_first=0):
        self.calls, self.infra_left = 0, infra_first

    def __call__(self, files):
        self.calls += 1
        if self.infra_left:
            self.infra_left -= 1
            return Outcome(report=report_with(Issue("error", "infra", "SocketTimeoutException", fingerprint="i")))
        if "BUG" in files["perfiles.fsh"]:
            return Outcome(report=report_with(content_issue("hay un BUG")))
        return Outcome(report=report_with())


BUGGY = {"perfiles.fsh": "Profile: A\nParent: Patient\n* identifier 1..1 MS\n// BUG\n"}


def loop(responses, tmp_path, validate=None, **kw):
    rep, backend = make_repairer(responses, tmp_path)
    return run_loop(BUGGY, validate or FakeValidator(), rep, mini_catalog(), **kw), backend


def test_loop_converges_after_one_repair(tmp_path):
    res, backend = loop([patch("perfiles.fsh", "// BUG", "// listo")], tmp_path)
    assert res.ok and len(backend.calls) == 1 and res.steps[0].stage == "publisher"


def test_loop_stalls_when_repairs_do_nothing(tmp_path):
    res, backend = loop(["sin parches"] * 10, tmp_path, max_iterations=9)
    assert res.status == "sin_progreso" and len(backend.calls) <= 3 and res.problems


def test_loop_stops_at_max_iterations(tmp_path):
    changing = [patch("perfiles.fsh", "// BUG", "// BUG otra vez"), patch("perfiles.fsh", "// BUG otra vez", "// BUG de nuevo")]
    res, _ = loop(changing, tmp_path, max_iterations=2, max_stalls=99)
    assert res.status == "max_iteraciones"


def test_infra_errors_are_retried_without_calling_the_model(tmp_path):
    v = FakeValidator(infra_first=2)
    res, backend = loop([patch("perfiles.fsh", "// BUG", "// ok")], tmp_path, validate=v)
    assert res.ok and len(backend.calls) == 1 and v.calls == 4


def test_persistent_infra_failure_gives_up_without_model(tmp_path):
    res, backend = loop([], tmp_path, validate=FakeValidator(infra_first=99), max_infra_retries=1)
    assert res.status == "infraestructura" and backend.calls == []


def test_precheck_runs_before_publisher_and_spares_validation(tmp_path):
    files = {"perfiles.fsh": f"Profile: A\nParent: CorePacienteCl\n* extension contains {BASE}/StructureDefinition/ComunaCl named c 0..1\n"}
    fix = patch("perfiles.fsh", "ComunaCl", "ComunasCl")
    rep, backend = make_repairer([fix], tmp_path)
    v = FakeValidator()
    res = run_loop(files, v, rep, mini_catalog())
    assert res.ok and res.steps[0].stage == "precheck" and v.calls == 1


def test_budget_exceeded_ends_loop_cleanly(tmp_path):
    class Broke:
        def repair(self, *a, **k):
            raise BudgetExceeded("tope")
    res = run_loop(BUGGY, FakeValidator(), Broke(), mini_catalog())
    assert res.status == "presupuesto"


def test_sushi_failure_is_repaired_from_console_issues(tmp_path):
    state = {"n": 0}

    def validate(files):
        state["n"] += 1
        if "BUG" in files["perfiles.fsh"]:
            return Outcome(sushi_issues=parse_sushi_text("error Algo falla\n  File: x/perfiles.fsh\n  Line: 4\n"))
        return Outcome(report=report_with())

    res, backend = loop([patch("perfiles.fsh", "// BUG", "// ok")], tmp_path, validate=validate)
    assert res.ok and res.steps[0].stage == "sushi"
    assert "perfiles.fsh:4" in backend.calls[0]["messages"][0]["content"]


def test_same_broken_spot_with_new_guesses_counts_as_stall(tmp_path):
    """Si el modelo cambia un valor por otro igual de malo en la misma línea, el bucle debe cortar."""
    base = f"Alias: $CSDNI = {BASE}/CodeSystem/CSCodigoDNI\n"
    files = {"e.fsh": base + "* t = $CSDNI#01\n"}
    guesses = [patch("e.fsh", "$CSDNI#01", "$CSDNI#11"), patch("e.fsh", "$CSDNI#11", "$CSDNI#22"),
               patch("e.fsh", "$CSDNI#22", "$CSDNI#33"), patch("e.fsh", "$CSDNI#33", "$CSDNI#44")]
    rep, backend = make_repairer(guesses, tmp_path)
    res = run_loop(files, FakeValidator(), rep, mini_catalog(), max_iterations=9)
    assert res.status == "sin_progreso" and len(backend.calls) <= 3


def test_model_timeout_in_repair_ends_loop_with_clear_status(tmp_path):
    from llm import LLMUnavailable

    class Slow:
        def repair(self, *a, **k):
            raise LLMUnavailable("tiempo agotado")

    res = run_loop(BUGGY, FakeValidator(), Slow(), mini_catalog())
    assert res.status == "modelo_no_responde" and res.problems


def test_parse_real_sushi_console_output():
    """Salida real de SUSHI (corrida 3): la primera línea es un resto sin cabecera y se ignora."""
    from pathlib import Path
    issues = parse_sushi_text(Path("tests/fixtures/sushi_corrida3.txt").read_text(encoding="utf-8"))
    assert [(i.section, i.path) for i in issues] == [
        ("ejemplos.fsh", "ejemplos.fsh:15"), ("ejemplos.fsh", "ejemplos.fsh:27"),
        ("ejemplos.fsh", "ejemplos.fsh:19"), ("ejemplos.fsh", "ejemplos.fsh:19")]
    assert "does not exist: name[NombreOficial]" in issues[0].message and all(i.kind == "content" for i in issues)
    assert len({i.fingerprint for i in issues}) == 4


def test_excepcion_del_publisher_se_convierte_en_error_de_contenido(tmp_path):
    import json
    from validator.run import excepcion_del_publisher
    out = tmp_path / "output"
    out.mkdir()
    assert excepcion_del_publisher(out) is None                       # sin qa.json
    (out / "qa.json").write_text(json.dumps({"exception": 'Invalid date/time format: "1975-06-31"'}), encoding="utf-8")
    r = excepcion_del_publisher(out)
    assert r and not r.ok and len(r.content_errors) == 1 and "1975-06-31" in r.content_errors[0].message
    (out / "qa.json").write_text(json.dumps({"exception": "java.net.UnknownHostException: tx.fhir.org"}), encoding="utf-8")
    assert excepcion_del_publisher(out).needs_retry                   # de red: infraestructura, se reintenta
    (out / "qa.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
    assert excepcion_del_publisher(out) is None                       # sin excepción
