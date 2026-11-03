"""Pruebas del catálogo por demanda y del chequeo previo de referencias (sin modelo, sin red)."""
from pathlib import Path

import pytest

from agents.catalog import CatalogIndex
from validator.precheck import main as precheck_main
from validator.precheck import precheck_fsh, precheck_path

BASE = "https://hl7chile.cl/fhir/ig/clcore"


def mini_catalog() -> CatalogIndex:
    el = lambda i, **k: {"id": i, "min": None, "max": None, "type": "", "mustSupport": False,
                         "binding": None, "strength": None, "fixed": "", **k}
    return CatalogIndex({
        "package": "hl7.fhir.cl.clcore", "version": "1.9.3", "canonical": BASE, "fhirVersions": ["4.0.1"],
        "structureDefinitions": [
            {"id": "CorePacienteCl", "url": f"{BASE}/StructureDefinition/CorePacienteCl", "kind": "resource",
             "type": "Patient", "base": "Patient", "title": "Paciente Chile", "description": "Paciente con RUN",
             "elements": [el("Patient.identifier", min=1, max="*", mustSupport=True)]},
            {"id": "cl-core-signos-vitales", "url": f"{BASE}/StructureDefinition/cl-core-signos-vitales",
             "kind": "resource", "type": "Observation", "base": "Observation", "title": "Signos vitales",
             "description": "Signos vitales", "elements": []},
            {"id": "ComunasCl", "url": f"{BASE}/StructureDefinition/ComunasCl", "kind": "complex-type",
             "type": "Extension", "base": "Extension", "title": "Comunas", "description": "Comuna", "elements": []},
        ],
        "codeSystems": [
            {"id": "CSCodRegionCL", "url": f"{BASE}/CodeSystem/CSCodRegionCL", "count": 1,
             "concepts": {"13": "Metropolitana de Santiago"}},
            {"id": "CSCodigoDNI", "url": f"{BASE}/CodeSystem/CSCodigoDNI", "count": 1, "concepts": {"NNCHL": "Chile"}},
            {"id": "CSTipoIdentificador", "url": f"{BASE}/CodeSystem/CSTipoIdentificador", "count": 1,
             "concepts": {"01": "RUN"}},
        ],
        "valueSets": [{"id": "VSRegion", "url": f"{BASE}/ValueSet/VSRegion", "systems": [], "valueSets": []}],
    })


def kinds(issues):
    return [i.kind for i in issues]


def test_valid_references_have_no_issues():
    fsh = f'''Alias: $CSDNI = {BASE}/CodeSystem/CSCodigoDNI
Profile: Mio
Parent: CorePacienteCl
* identifier.type = $CSDNI#NNCHL "Chile"
* extension contains {BASE}/StructureDefinition/ComunasCl named c 0..1
'''
    assert precheck_fsh(fsh, mini_catalog()) == []


def test_nonexistent_url_suggests_closest():
    issues = precheck_fsh(f"* extension contains {BASE}/StructureDefinition/ComunaCl named c 0..1", mini_catalog())
    assert kinds(issues) == ["url"] and "ComunasCl" in issues[0].suggestion


def test_code_in_wrong_system_hints_where_it_exists():
    fsh = f"Alias: $CSDNI = {BASE}/CodeSystem/CSCodigoDNI\n* identifier.type = $CSDNI#01"
    issues = precheck_fsh(fsh, mini_catalog())
    assert kinds(issues) == ["code"] and "CSTipoIdentificador" in issues[0].suggestion and issues[0].line == 2


def test_display_mismatch_is_reported_with_official_text():
    fsh = f'* region = {BASE}/CodeSystem/CSCodRegionCL#13 "Región Metropolitana"'
    issues = precheck_fsh(fsh, mini_catalog())
    assert kinds(issues) == ["display"] and "Metropolitana de Santiago" in issues[0].suggestion


def test_display_comparison_ignores_case_and_spacing():
    fsh = f'* x = {BASE}/CodeSystem/CSCodRegionCL#13 "metropolitana  de santiago"'
    assert precheck_fsh(fsh, mini_catalog()) == []


def test_foreign_code_systems_are_ignored():
    assert precheck_fsh('* code = http://loinc.org#85354-9 "lo que sea"', mini_catalog()) == []


def test_parent_typo_detected_but_local_and_external_ok():
    cat = mini_catalog()
    assert kinds(precheck_fsh("Profile: A\nParent: CorePacienteCL", cat)) == ["name"]
    assert precheck_fsh("Profile: A\nParent: Observation", cat) == []
    assert precheck_fsh("Profile: B\nParent: A\nProfile: A\nParent: Patient", cat) == []


# --- catálogo ---------------------------------------------------------------

def test_search_is_accent_and_camelcase_aware():
    assert mini_catalog().search("paciente con RUN")[0] == "CorePacienteCl"
    assert mini_catalog().search("región comuna")[0] == "ComunasCl"


def test_context_respects_budget_and_includes_overview():
    cat = mini_catalog()
    ctx = cat.context("paciente", max_chars=10_000)
    assert "CorePacienteCl" in ctx and "Patient.identifier" in ctx
    assert "Patient.identifier" not in cat.context("paciente", max_chars=1)


def test_concept_display_and_code_lookup():
    cat = mini_catalog()
    assert cat.concept_display(f"{BASE}/CodeSystem/CSTipoIdentificador", "01") == "RUN"
    assert cat.concept_display("http://otro", "01") is None
    assert cat.code_systems_with("01") == ["CSTipoIdentificador"]


def test_missing_catalog_file_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="cl_ig.py catalogo"):
        CatalogIndex.from_file(tmp_path / "no.json")


def test_cli_exit_codes(tmp_path, capsys):
    import json
    cat_path = tmp_path / "c.json"
    cat_path.write_text(json.dumps(mini_catalog().data), encoding="utf-8")
    good, bad = tmp_path / "ok.fsh", tmp_path / "bad.fsh"
    good.write_text("Profile: A\nParent: Patient\n", encoding="utf-8")
    bad.write_text(f"* x = {BASE}/CodeSystem/CSCodRegionCL#99\n", encoding="utf-8")
    assert precheck_main([str(good), "--catalog", str(cat_path)]) == 0
    assert precheck_main([str(bad), "--catalog", str(cat_path)]) == 1
    assert precheck_main([str(good), "--catalog", str(tmp_path / "x.json")]) == 2


# --- integración con el CL Core real (se omite si no se generó el catálogo) --

REAL = Path("build/catalog/catalog.json")


@pytest.mark.skipif(not REAL.is_file(), reason="ejecuta `make catalog` primero")
def test_real_catalog_catches_the_errors_seen_in_first_runs():
    cat = CatalogIndex.from_file(REAL)
    fsh = f'''Alias: $CSDNI = {BASE}/CodeSystem/CSCodigoDNI
* extension contains {BASE}/StructureDefinition/CodigoComuna named c 0..1
* identifier.type = $CSDNI#01
* region = {BASE}/CodeSystem/CSCodRegionCL#13 "Región Metropolitana"
* extension contains {BASE}/StructureDefinition/ComunasCl named ok 0..1
'''
    issues = precheck_fsh(fsh, cat)
    assert sorted(kinds(issues)) == ["code", "display", "url"]
    assert any("ComunasCl" in (i.suggestion or "") for i in issues if i.kind == "url")
    assert 0 < len(cat.overview()) < 8000
    assert "CorePacienteCl" in cat.search("paciente")


@pytest.mark.skipif(not REAL.is_file(), reason="ejecuta `make catalog` primero")
def test_gold_demo_passes_precheck():
    cat = CatalogIndex.from_file(REAL)
    results = precheck_path(
        "examples/demo/gold/input/fsh", cat)
    assert all(not v for v in results.values()), results


def test_aliases_declared_in_another_file_are_used(tmp_path):
    (tmp_path / "aliases.fsh").write_text(f"Alias: $CSDNI = {BASE}/CodeSystem/CSCodigoDNI\n", encoding="utf-8")
    (tmp_path / "ej.fsh").write_text("* identifier.type = $CSDNI#01\n", encoding="utf-8")
    from validator.precheck import precheck_path
    res = precheck_path(tmp_path, mini_catalog())
    assert [i.kind for i in res[str(tmp_path / "ej.fsh")]] == ["code"]


def test_code_issue_lists_valid_codes_of_short_code_systems():
    fsh = f"Alias: $CSDNI = {BASE}/CodeSystem/CSCodigoDNI\n* identifier.type = $CSDNI#01"
    hint = precheck_fsh(fsh, mini_catalog())[0].suggestion
    assert "códigos válidos en CSCodigoDNI: NNCHL=Chile" in hint and "CSTipoIdentificador" in hint


def test_context_skips_cards_that_do_not_fit_and_keeps_going():
    cat = mini_catalog()
    small, big = sorted(["CorePacienteCl", "cl-core-signos-vitales"], key=lambda i: len(cat.profile_card(i)))
    assert len(cat.profile_card(big)) > len(cat.profile_card(small)) + 5
    room = len(cat.overview()) + len(cat.profile_card(small)) + 5
    ctx = cat.context("paciente signos vitales", max_chars=room, limit=3, must=[big])
    # la ficha grande se exige pero no cabe: se salta y la pequeña sí entra
    assert f"### {small}" in ctx and f"### {big}" not in ctx


def test_search_cards_are_resource_profiles_only_but_must_can_add_extensions():
    cat = mini_catalog()
    assert "### ComunasCl" not in cat.context("comuna paciente", max_chars=20000)
    ctx = cat.context("comuna", max_chars=20000, must=["ComunasCl", "CorePacienteCl", "no-existe"])
    assert ctx.index("### ComunasCl") < ctx.index("### CorePacienteCl")
    assert cat.search("paciente comuna")[0] == "CorePacienteCl"


def test_un_recurso_base_de_fhir_es_un_padre_valido_aunque_se_parezca_a_un_perfil_de_cl_core():
    """Caso real: un perfil de CL Core se llama casi igual que el recurso base (p. ej. EncounterCl), y el padre «Encounter» no es una errata."""
    cat = mini_catalog()
    cat.sd["EncounterCl"] = dict(cat.sd["CorePacienteCl"], id="EncounterCl")
    assert precheck_fsh("Profile: A\nParent: Encounter\nProfile: B\nParent: AuditEvent", cat) == []
    assert kinds(precheck_fsh("Profile: A\nParent: EncounterC", cat)) == ["name"]      # una errata de verdad se sigue detectando


def test_un_perfil_definido_en_otro_archivo_no_es_un_nombre_desconocido(tmp_path):
    (tmp_path / "perfiles.fsh").write_text("Profile: DiagnosticoCl\nParent: Condition\nId: CoreDiagnosticoCl\n", encoding="utf-8")
    (tmp_path / "ejemplos.fsh").write_text("Instance: Ej\nInstanceOf: DiagnosticoCl\nUsage: #example\n", encoding="utf-8")
    from validator.precheck import precheck_path
    cat = mini_catalog()
    cat.sd["CoreDiagnosticoCl"] = {}
    res = precheck_path(tmp_path, cat)
    assert all(not v for v in res.values())
