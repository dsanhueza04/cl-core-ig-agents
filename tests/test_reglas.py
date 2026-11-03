"""Reglas deterministas: con los mensajes REALES de SUSHI/precheck/publisher, el IG roto vuelve a ser el de referencia."""
import json

import pytest

from agents.loop import Outcome, run_loop
from agents.reglas import aplicar_reglas
from agents.reparador import Problem
from scripts import errores
from tests.test_catalog_precheck import mini_catalog
from validator.parse_qa import Issue

GOLD = {p.name: p.read_text(encoding="utf-8") for p in (errores.GOLD / "input" / "fsh").glob("*.fsh")}

# (caso, fuente, mensaje real, sugerencia)
MENSAJES = {
    "parent_con_typo": ("precheck", "StructureDefinition 'cl-core-signo-vitales' no existe en CL Core 1.9.3", "¿cl-core-signos-vitales?"),
    "alias_indefinido": ("sushi", 'Value $LOINC does not resolve as alias, values beginning with "$" must resolve', None),
    "regla_sin_espacios": ("sushi", "Assignment rules must include at least one space both before and after the '=' sign", None),
    "slice_mal_escrito": ("sushi", "The element or path you referenced does not exist: component[diastolico].code", None),
    "valor_sin_unidad": ("sushi", "Cannot assign number value: 128. Value does not match element type: Quantity", None),
    "codigo_ejemplo_distinto": ("sushi", 'Cannot assign http://loinc.org#8480-6 to this element; a different CodeableConcept is already assigned: {"coding":[{"code":"85354-9","system":"http://loinc.org"}]}.', None),
    "fecha_con_formato_invalido": ("sushi", "Cannot assign string value: 15-03-2026. Value does not match element type: dateTime", None),
    "referencia_a_tipo_no_permitido": ("sushi", 'The type "Reference(Observation)" does not match any of the allowed types: Reference(https://hl7chile.cl/fhir/ig/clcore/StructureDefinition/CorePacienteCl)', None),
    "estado_fuera_del_valueset": ("publisher", "package.tgz: Error converting pacakge to R4B: Error processing example/Observation-PresionArterialDemo.json: Unknown ObservationStatus code 'definitivo'", None),
    "genero_en_espanol": ("publisher", "package.tgz: Error converting pacakge to R4B: Error processing example/Patient-PacienteDemo.json: Unknown AdministrativeGender code 'femenino'", None),
    "categoria_sin_guion": ("sushi", 'Cannot assign vitalsigns to this element; a different code is already assigned: "vital-signs".', None),
    "id_con_guion_bajo": ("sushi", 'The string "cl_presion_arterial" does not represent a valid FHIR id. FHIR ids only allow ASCII letters (A-Z, a-z), numbers (0-9), hyphens (-), and dots (.), with a length limit of 64 characters.', None),
    "title_sin_comillas": ("sushi", "mismatched input 'Presión' expecting STRING", None),
    "referencia_a_instancia_inexistente": ("publisher", "Incapaz de resolver el recurso con la referencia 'PacienteDemos'", None),
}
SIN_REGLA = {
    "instancia_duplicada": ("sushi", "Skipping Instance: an Instance named PacienteDemo already exists.", None),
    "fecha_nacimiento_imposible": ("publisher", 'El IG Publisher terminó con una excepción: Invalid date/time format: "1975-06-31"', None),
    "unidad_distinta_al_perfil": ("sushi", 'Cannot assign kPa to this element; a different string is already assigned: "mmHg".', None),
    "falta_componente_obligatorio": ("publisher", "Constraint failed: vs-3: 'If there is no a value a data absent reason must be present'", None),
    "codigo_en_codesystem_equivocado": ("precheck", "El código '01' no existe en CSCodigoDNI", "el código existe en: CSCodRegionCL, CSTipoIdentificador"),
}


def roto_y_problema(nombre, mensaje):
    caso = errores.CASOS[nombre]
    texto = GOLD[caso.archivo]
    roto = texto.replace(caso.buscar, caso.reemplazar, 1)
    files = {**GOLD, caso.archivo: roto}
    # línea del primer cambio
    linea = next(i for i, (a, b) in enumerate(zip(roto.split("\n"), texto.split("\n")), 1) if a != b)
    fuente, msg, sug = mensaje
    archivo = None if fuente == "publisher" else caso.archivo
    return files, Problem(fuente, msg, file=archivo, line=None if fuente == "publisher" else linea, suggestion=sug)


@pytest.mark.parametrize("nombre", sorted(MENSAJES))
def test_la_regla_devuelve_el_ig_al_estado_de_referencia(nombre):
    files, problema = roto_y_problema(nombre, MENSAJES[nombre])
    nuevos, cambios = aplicar_reglas(files, [problema])
    esperado = GOLD
    if nombre == "fecha_con_formato_invalido":   # el error no trae la hora: queda solo la fecha, y se avisa
        esperado = {**GOLD, "ejemplos.fsh": GOLD["ejemplos.fsh"].replace('"2026-03-15T09:30:00-03:00"', '"2026-03-15"')}
        assert "sin hora" in cambios[0].nota
    assert nuevos == esperado, nombre
    assert len(cambios) == 1 and cambios[0].regla


@pytest.mark.parametrize("nombre", sorted(SIN_REGLA))
def test_lo_que_exige_decision_clinica_no_tiene_regla(nombre):
    files, problema = roto_y_problema(nombre, SIN_REGLA[nombre])
    nuevos, cambios = aplicar_reglas(files, [problema])
    assert nuevos == files and cambios == []


def test_las_reglas_no_tocan_cardinalidades_ni_borran_lineas():
    for nombre in MENSAJES:
        files, problema = roto_y_problema(nombre, MENSAJES[nombre])
        nuevos, _ = aplicar_reglas(files, [problema])
        for archivo in files:
            assert len(nuevos[archivo].split("\n")) == len(files[archivo].split("\n"))


def test_no_hace_nada_si_la_linea_ya_cambio():
    files, problema = roto_y_problema("alias_indefinido", MENSAJES["alias_indefinido"])
    una_vez, _ = aplicar_reglas(files, [problema])
    dos_veces, cambios = aplicar_reglas(una_vez, [problema])
    assert dos_veces == una_vez and cambios == []


def test_fecha_imposible_no_se_inventa():
    files, p = roto_y_problema("fecha_con_formato_invalido", MENSAJES["fecha_con_formato_invalido"])
    files["ejemplos.fsh"] = files["ejemplos.fsh"].replace("15-03-2026", "45-13-2026")
    p = Problem("sushi", "Cannot assign string value: 45-13-2026. Value does not match element type: dateTime", file=p.file, line=p.line)
    assert aplicar_reglas(files, [p])[1] == []


def test_estado_desconocido_sin_traduccion_no_se_toca():
    files = {"ejemplos.fsh": "* status = #raro\n"}
    p = Problem("publisher", "Unknown ObservationStatus code 'raro'")
    assert aplicar_reglas(files, [p])[1] == []


def test_dos_instancias_de_paciente_es_ambiguo():
    files, p = roto_y_problema("referencia_a_tipo_no_permitido", MENSAJES["referencia_a_tipo_no_permitido"])
    files["ejemplos.fsh"] += "\nInstance: OtroPaciente\nInstanceOf: CorePacienteCl\n"
    assert aplicar_reglas(files, [p])[1] == []


# --- integración con el bucle: se repara sin una sola llamada al modelo ---------------------------------

class SinModelo:
    def repair(self, *a, **k):
        raise AssertionError("no debería llamarse al modelo")


def test_bucle_repara_solo_con_reglas_y_registra_los_cambios():
    caso = errores.CASOS["regla_sin_espacios"]
    roto = {**GOLD, caso.archivo: GOLD[caso.archivo].replace(caso.buscar, caso.reemplazar, 1)}
    linea = next(i for i, (a, b) in enumerate(zip(roto[caso.archivo].split("\n"), GOLD[caso.archivo].split("\n")), 1) if a != b)

    def validate(files):
        if files == GOLD:
            return Outcome(report=_ok_report())
        return Outcome(sushi_issues=[Issue("error", "content", MENSAJES["regla_sin_espacios"][1],
                                           path=f"{caso.archivo}:{linea}", section=caso.archivo, fingerprint="f1")])

    res = run_loop(roto, validate, SinModelo(), mini_catalog(), usar_reglas=True)
    assert res.ok and res.files == GOLD
    assert res.steps[0].reglas and res.steps[0].reglas[0]["regla"] == "regla_sin_espacios"


def _ok_report():
    from tests.test_repair_loop import report_with
    return report_with()


def test_ucum_mal_escrito_en_el_perfil_no_se_corrige_en_el_ejemplo():
    """El mensaje de SUSHI culpa al ejemplo, pero el error está en el perfil (mmHg no es UCUM): no se adivina."""
    caso = errores.CASOS["ucum_invalido"]
    files = {**GOLD, caso.archivo: GOLD[caso.archivo].replace(caso.buscar, caso.reemplazar, 1)}
    linea = next(i for i, ln in enumerate(files["ejemplos.fsh"].split("\n"), 1) if "component[sistolica].valueQuantity" in ln)
    p = Problem("sushi", 'Cannot assign mm[Hg] to this element; a different code is already assigned: "mmHg".',
                file="ejemplos.fsh", line=linea)
    assert aplicar_reglas(files, [p])[1] == []


def test_codigo_fijo_que_esta_en_nuestros_archivos_no_se_toca():
    files = {"perfiles.fsh": '* code = #"vital-signs"\n', "ejemplos.fsh": "* category[VSCat] = $ObsCat#vitalsigns\n"}
    p = Problem("sushi", 'Cannot assign vitalsigns to this element; a different code is already assigned: "vital-signs".',
                file="ejemplos.fsh", line=1)
    assert aplicar_reglas(files, [p])[1] == []


def test_genero_y_estado_en_espanol_usan_la_misma_tabla():
    files = {"e.fsh": "* gender = #masculino\n* status = #preliminar\n"}
    nuevos, cambios = aplicar_reglas(files, [Problem("publisher", "Unknown AdministrativeGender code 'masculino'"),
                                              Problem("publisher", "Unknown ObservationStatus code 'preliminar'")])
    assert nuevos["e.fsh"] == "* gender = #male\n* status = #preliminary\n" and len(cambios) == 2
