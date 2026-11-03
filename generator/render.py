"""Escribe el FSH a partir de la ficha validada. Sin modelo: mismas entradas, misma salida."""
from __future__ import annotations

import re

from agents.base import aliases_fsh

CLCORE = "https://hl7chile.cl/fhir/ig/clcore/StructureDefinition"
SAFE_CODE = re.compile(r"^[A-Za-z0-9\-_.]+$")


def q(text: str) -> str:
    """Texto entre comillas de FSH."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def code(ucum: str) -> str:
    return "#" + (ucum if SAFE_CODE.match(ucum) else q(ucum))


def num(value) -> str:
    return str(int(value)) if float(value).is_integer() and not isinstance(value, float) else repr(float(value))


def _quantity_rules(prefix: str, unit: dict) -> list[str]:
    return [f"* {prefix}value[x] only Quantity",
            f"* {prefix}valueQuantity.system = $UCUM",
            f"* {prefix}valueQuantity.code = {code(unit['ucum'])}",
            f"* {prefix}valueQuantity.unit = {q(unit['unidad'])}"]


def render_profile(o: dict) -> str:
    lines = [f"Profile: {o['nombre']}", f"Parent: {CLCORE}/{o['padre']}", f"Id: {o['id']}", f"Title: {q(o['titulo'])}",
             f"Description: {q(o['descripcion'])}", "* ^status = #draft", f"* code = $LNC#{o['codigo_loinc']}"]
    comps = o.get("componentes")
    if comps:
        etiquetas = " y ".join(c["etiqueta"] for c in comps)
        lines += ["",
                  "* component ^slicing.discriminator.type = #pattern",
                  '* component ^slicing.discriminator.path = "code"',
                  "* component ^slicing.rules = #open",
                  "* component ^slicing.ordered = false",
                  f"* component ^slicing.description = {q('Componentes: ' + etiquetas)}",
                  "* component contains " + " and ".join(
                      f"{c['nombre']} {'1' if c.get('obligatorio', True) else '0'}..1 MS" for c in comps)]
        for c in comps:
            lines += ["", f"* component[{c['nombre']}].code = $LNC#{c['loinc']}"]
            lines += _quantity_rules(f"component[{c['nombre']}].", c)
    else:
        lines += ["", "* valueQuantity 1..1 MS"]
        lines += _quantity_rules("", o["valor"])
    return "\n".join(lines) + "\n"


def render_patient(p: dict) -> str:
    lines = [f"Instance: {p['id']}", "InstanceOf: CorePacienteCl",
             f"Title: {q('Paciente sintético de demostración')}",
             f"Description: {q('Paciente con datos ficticios, conforme al perfil CorePacienteCl de CL Core. No corresponde a ninguna persona real.')}",
             "Usage: #example",
             "* identifier[0].use = #official",
             "* identifier[0].type = $CSDNI#NNCHL",
             '* identifier[0].system = "http://regcivil.cl/Validacion/RUN"',
             f"* identifier[0].value = {q(p['run'])}",
             "* name[NombreOficial].use = #official",
             f"* name[NombreOficial].family = {q(p['primer_apellido'])}"]
    if p.get("segundo_apellido"):
        lines.append(f"* name[NombreOficial].family.extension[segundoApellido].valueString = {q(p['segundo_apellido'])}")
    lines += [f"* name[NombreOficial].given[{i}] = {q(n)}" for i, n in enumerate(p["nombres"])]
    lines += [f"* gender = #{p['sexo']}", f"* birthDate = {q(p['fecha_nacimiento'])}"]
    return "\n".join(lines) + "\n"


# Códigos "mágicos" de los perfiles base de signos vitales de FHIR R4: el publisher
# exige un coding adicional en el ejemplo. Conocimiento determinista, no del modelo.
# 59408-5 (SpO2 por oximetría) exige además 2708-6 (saturación de oxígeno en sangre arterial).
CODIGOS_OBLIGATORIOS_FHIR = {"59408-5": ["2708-6"]}


def render_observation_example(o: dict, patient_id: str) -> str:
    e = o["ejemplo"]
    lines = [f"Instance: {e['id']}", f"InstanceOf: {o['nombre']}", f"Title: {q(e['titulo'])}",
             f"Description: {q(e['descripcion'])}", "Usage: #example", "* status = #final",
             "* category[VSCat] = $ObsCat#vital-signs", f"* code = $LNC#{o['codigo_loinc']}"]
    # Índices explícitos: con [+] SUSHI parte en 0 y pisa el coding principal.
    for i, extra in enumerate(CODIGOS_OBLIGATORIOS_FHIR.get(o["codigo_loinc"], []), start=1):
        lines.append(f"* code.coding[{i}] = $LNC#{extra}")
    if o.get("texto_codigo"):
        lines.append(f"* code.text = {q(o['texto_codigo'])}")
    lines += [f"* subject = Reference({patient_id})", f"* effectiveDateTime = {q(e['fecha'])}"]
    if o.get("componentes"):
        for c in o["componentes"]:
            lines += [f"* component[{c['nombre']}].code = $LNC#{c['loinc']}",
                      f"* component[{c['nombre']}].valueQuantity = {num(e['valores'][c['nombre']])} "
                      f"'{c['ucum']}' {q(c['unidad'])}"]
    else:
        lines.append(f"* valueQuantity = {num(e['valor'])} '{o['valor']['ucum']}' {q(o['valor']['unidad'])}")
    return "\n".join(lines) + "\n"


def render_files(spec: dict) -> dict[str, str]:
    """Archivos FSH del IG: aliases.fsh, perfiles.fsh y ejemplos.fsh."""
    obs = spec["observaciones"]
    patient = spec["paciente_ejemplo"]
    return {
        "aliases.fsh": aliases_fsh(),
        "perfiles.fsh": "\n".join(render_profile(o) for o in obs),
        "ejemplos.fsh": "\n".join([render_patient(patient)] + [render_observation_example(o, patient["id"]) for o in obs]),
    }
