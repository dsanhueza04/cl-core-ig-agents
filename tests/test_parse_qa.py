"""Pruebas del parser de QA con corridas reales del IG de referencia."""
import json
from pathlib import Path

import pytest

from validator.parse_qa import classify, load_report, main, parse_qa_text

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def run1():
    """Primera corrida real: publisher 2.0.17, 15 errores (13 de infraestructura, 2 de contenido)."""
    return load_report(FIXTURES / "qa_gold_corrida1.txt")


@pytest.fixture(scope="module")
def run_ok():
    """Corrida real final: publisher 2.3.4, 0 errores."""
    return load_report(FIXTURES / "qa_gold_ok.txt")


# --- corrida con errores -------------------------------------------------

def test_run1_counts_match_header(run1):
    assert (run1.declared_errors, run1.declared_warnings, run1.declared_infos) == (15, 7, 3)
    assert (len(run1.errors), len(run1.warnings), len(run1.informations)) == (15, 7, 3)
    assert run1.consistent


def test_run1_splits_infra_from_content(run1):
    assert len(run1.infra_errors) == 13
    assert len(run1.content_errors) == 2
    assert run1.needs_retry
    assert not run1.ok


def test_run1_content_errors_are_the_missing_unit(run1):
    for issue in run1.content_errors:
        assert issue.resource == "Observation/PresionArterialDemo"
        assert "unit" in issue.message
        assert issue.path.startswith("Observation.component[")


def test_run1_quantity_error_caused_by_tx_is_infra(run1):
    """El error de 'Vital Signs Units' trae dentro un fallo de tx.fhir.org: es infraestructura."""
    quantity = [i for i in run1.errors if "Vital Signs Units" in i.message]
    assert len(quantity) == 2
    assert all(i.kind == "infra" for i in quantity)


def test_run1_masked_resources(run1):
    assert run1.resources_masked == [
        "ImplementationGuide/demo.cl.presionarterial",
        "Observation/PresionArterialDemo",
        "StructureDefinition/cl-presion-arterial",
    ]


def test_run1_publisher_version_and_note(run1):
    assert run1.publisher_version == "2.0.17"
    assert "Out of date" in run1.publisher_note


# --- corrida limpia ------------------------------------------------------

def test_ok_run_passes(run_ok):
    assert run_ok.ok
    assert not run_ok.needs_retry
    assert run_ok.summary()["errors"] == 0
    assert (len(run_ok.warnings), len(run_ok.informations)) == (7, 7)
    assert run_ok.consistent
    assert run_ok.publisher_version == "2.3.4"


def test_ok_run_has_no_errors_fingerprints(run_ok):
    assert run_ok.fingerprints("content") == set()


# --- detalles del formato ------------------------------------------------

def test_numbered_build_warnings_have_no_resource(run_ok):
    build = [i for i in run_ok.warnings if i.section == "n/a"]
    assert len(build) == 4
    assert all(i.resource is None and i.path is None for i in build)
    assert build[0].message.startswith("The HTML fragment 'ip-statements.xhtml'")


def test_resource_path_and_message_are_split():
    report = parse_qa_text(
        "== x ==\n"
        "WARNING: Patient/PacienteDemo: Patient.identifier[0].system: El valor URL 'http://a.cl/b' no puede resolverse\n"
    )
    issue = report.issues[0]
    assert (issue.resource_type, issue.resource_id) == ("Patient", "PacienteDemo")
    assert issue.path == "Patient.identifier[0].system"
    assert issue.message == "El valor URL 'http://a.cl/b' no puede resolverse"


def test_resource_id_with_dots():
    report = parse_qa_text("ERROR: ImplementationGuide/demo.cl.x: ImplementationGuide.jurisdiction[0]: algo falló\n")
    assert report.issues[0].resource_id == "demo.cl.x"


@pytest.mark.parametrize(
    "severity,message,kind",
    [
        ("error", "java.net.SocketTimeoutException: timeout", "infra"),
        ("error", "Error from https://tx.fhir.org/r4: Error: The cache 'abc' was never issued by this server", "infra"),
        ("error", "Unknown code 01 in https://hl7chile.cl/fhir/ig/clcore/CodeSystem/CSCodigoDNI", "content"),
        ("error", "mínimo requerido = 1, pero sólo se han encontrado 0", "content"),
        ("warning", "java.net.SocketTimeoutException: timeout", "advisory"),
        ("information", "algo", "advisory"),
    ],
)
def test_classify(severity, message, kind):
    assert classify(severity, message) == kind


def test_fingerprint_ignores_cache_uuid():
    a = parse_qa_text("ERROR: Patient/p: Patient.x: Error: The cache 'b4738921-49f7-4d4a-94bf-3a1343bffd26' was never issued\n")
    b = parse_qa_text("ERROR: Patient/p: Patient.x: Error: The cache '11111111-2222-3333-4444-555555555555' was never issued\n")
    assert a.issues[0].fingerprint == b.issues[0].fingerprint


def test_fingerprint_differs_for_different_problems():
    a = parse_qa_text("ERROR: Patient/p: Patient.x: falta algo\n")
    b = parse_qa_text("ERROR: Patient/p: Patient.y: falta algo\n")
    assert a.issues[0].fingerprint != b.issues[0].fingerprint


def test_inconsistent_header_is_detected():
    report = parse_qa_text("err = 3, warn = 0, info = 0\nERROR: Patient/p: Patient.x: falta algo\n")
    assert not report.consistent


def test_empty_text_is_not_consistent_and_ok():
    report = parse_qa_text("")
    assert report.ok and not report.consistent


# --- carga y CLI ---------------------------------------------------------

def test_load_report_accepts_directory(tmp_path):
    (tmp_path / "qa.txt").write_text((FIXTURES / "qa_gold_ok.txt").read_text(encoding="utf-8"), encoding="utf-8")
    assert load_report(tmp_path).ok


def test_load_report_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_report(tmp_path / "no_existe")


def test_cli_exit_codes(tmp_path, capsys):
    assert main([str(FIXTURES / "qa_gold_ok.txt")]) == 0
    assert main([str(FIXTURES / "qa_gold_corrida1.txt")]) == 1  # hay errores de contenido
    infra_only = tmp_path / "qa.txt"
    infra_only.write_text("err = 1, warn = 0, info = 0\nERROR: Patient/p: Patient.x: java.net.SocketTimeoutException: timeout\n")
    assert main([str(infra_only)]) == 3  # solo infraestructura: reintentar
    assert main([str(tmp_path / "nada.txt")]) == 2
    capsys.readouterr()


def test_cli_json_output(capsys):
    assert main([str(FIXTURES / "qa_gold_corrida1.txt"), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["errors"] == 15 and data["infra_errors"] == 13 and data["content_errors"] == 2
    assert len(data["issues"]) == 25
    assert {"severity", "kind", "resource", "path", "message", "fingerprint"} <= set(data["issues"][0])
