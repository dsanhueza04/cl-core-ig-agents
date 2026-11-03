"""Prueba el extractor de catálogo con un paquete FHIR sintético (sin depender de CL Core)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import extract_catalog as ec  # noqa: E402


def make_package(root: Path) -> Path:
    pkg = root / "package"
    pkg.mkdir()
    (pkg / "package.json").write_text(json.dumps(
        {"name": "demo.pkg", "version": "1.0.0", "fhirVersions": ["4.0.1"], "license": "CC0-1.0"}))
    (pkg / "StructureDefinition-MiPerfil.json").write_text(json.dumps({
        "id": "MiPerfil", "url": "http://ex.org/SD/MiPerfil", "kind": "resource", "type": "Patient",
        "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Patient",
        "differential": {"element": [
            {"id": "Patient.gender", "min": 1, "max": "1", "mustSupport": True,
             "binding": {"strength": "required", "valueSet": "http://ex.org/VS/Sexo"}}]}}))
    (pkg / "CodeSystem-CSX.json").write_text(json.dumps({
        "id": "CSX", "url": "http://ex.org/CS/CSX", "concept": [{"code": "a", "display": "Alfa"}]}))
    (pkg / "ValueSet-VSX.json").write_text(json.dumps({
        "id": "VSX", "url": "http://ex.org/VS/VSX",
        "compose": {"include": [{"system": "http://ex.org/CS/CSX"}]}}))
    return root


def test_catalog_from_folder(tmp_path):
    cat = ec.build_catalog(ec.open_package(make_package(tmp_path)))
    assert cat["package"] == "demo.pkg"
    assert cat["structureDefinitions"][0]["elements"][0]["binding"] == "http://ex.org/VS/Sexo"
    assert cat["codeSystems"][0]["concepts"] == {"a": "Alfa"}
    assert cat["valueSets"][0]["systems"] == ["http://ex.org/CS/CSX"]


def test_markdown_lists_profile_and_code_system(tmp_path):
    cat = ec.build_catalog(ec.open_package(make_package(tmp_path)))
    md = ec.render_markdown(cat)
    assert "### MiPerfil — Patient" in md
    assert "**CSX**" in md
