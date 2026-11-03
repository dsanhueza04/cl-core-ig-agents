"""Solución de referencia del ejercicio 1 (control de presión arterial). Datos 100 % sintéticos.

Genera el libro con:  python examples/ejercicio-1-presion-arterial/datos.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

CS_DNI = "https://hl7chile.cl/fhir/ig/clcore/CodeSystem/CSCodigoDNI"
CAT_OBS = "http://terminology.hl7.org/CodeSystem/observation-category"
RUN = "http://regcivil.cl/Validacion/RUN"

DATOS = {
    "Guía": {
        "id": "control-presion-arterial", "titulo": "Control de presión arterial en atención primaria (ejercicio)",
        "descripcion": "Guía de ejercicio, con datos ficticios, para registrar mediciones de presión arterial del programa cardiovascular de un centro de salud.",
        "canonical": "https://example.org/fhir/ig/control-presion-arterial", "version": "0.1.0", "estado": "draft",
        "publicador": "Ejercicio de aprendizaje", "licencia": "CC0-1.0", "usa_clcore": "Sí",
    },
    "Perfiles": [
        {"nombre": "PacienteCesfam", "recurso": "Patient", "padre": "CorePacienteCl", "titulo": "Paciente del programa cardiovascular",
         "descripcion": "Persona chilena en control cardiovascular. Exige nombre oficial con ambos apellidos, sexo, fecha de nacimiento, RUN y al menos un medio de contacto (teléfono o correo).",
         "justificacion": "Sin identificación y contacto no se puede citar ni ubicar a la persona; sin sexo y edad no se interpreta la presión."},
        {"nombre": "PresionArterialCesfam", "recurso": "Observation", "padre": "cl-core-signos-vitales", "titulo": "Presión arterial del programa cardiovascular",
         "descripcion": "Medición de presión arterial como panel con dos componentes obligatorios (sistólica y diastólica), con la postura y el lugar de la medición.",
         "justificacion": "El valor vive en los componentes: la observación completa no lleva un valor propio."},
    ],
    "Elementos": [
        # ---- paciente
        {"perfil": "PacienteCesfam", "ruta": "name[NombreOficial]", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "name[NombreOficial].given", "min": "1", "max": "*", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "name[NombreOficial].family", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "name[NombreOficial].family.extension[segundoApellido]", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "gender", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "birthDate", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "identifier", "min": "1", "max": "*", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "identifier.system", "min": "1", "max": "1", "ms": "Sí", "fijo": RUN, "fijo_tipo": "texto"},
        {"perfil": "PacienteCesfam", "ruta": "identifier.value", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "telecom", "min": "1", "max": "*", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "telecom.system", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "telecom.value", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PacienteCesfam", "ruta": "extension[programaCardiovascular]", "min": "0", "max": "1", "ms": "Sí"},
        # ---- presión arterial
        {"perfil": "PresionArterialCesfam", "ruta": "code", "min": "1", "max": "1", "fijo": "85354-9", "fijo_tipo": "código con sistema", "fijo_sistema": "LOINC"},
        {"perfil": "PresionArterialCesfam", "ruta": "subject", "min": "1", "max": "1", "ms": "Sí", "tipo": "Reference(PacienteCesfam)"},
        {"perfil": "PresionArterialCesfam", "ruta": "effective[x]", "tipo": "dateTime"},
        {"perfil": "PresionArterialCesfam", "ruta": "effectiveDateTime", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PresionArterialCesfam", "ruta": "value[x]", "min": "0", "max": "0"},
        {"perfil": "PresionArterialCesfam", "ruta": "method", "min": "0", "max": "1", "ms": "Sí", "valueset": "VSPosturaMedicion", "fuerza": "extensible",
         "justificacion": "Las posturas habituales están listadas, pero se admite otra si ninguna calza."},
        {"perfil": "PresionArterialCesfam", "ruta": "bodySite", "min": "0", "max": "1", "ms": "Sí"},
        {"perfil": "PresionArterialCesfam", "ruta": "component", "min": "2", "max": "*", "ms": "Sí"},
        {"perfil": "PresionArterialCesfam", "ruta": "extension[medicionDomiciliaria]", "min": "0", "max": "1", "ms": "Sí"},
        {"perfil": "PresionArterialCesfam", "ruta": "component[sistolica].value[x]", "tipo": "Quantity"},
        {"perfil": "PresionArterialCesfam", "ruta": "component[sistolica].valueQuantity", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PresionArterialCesfam", "ruta": "component[sistolica].valueQuantity.system", "fijo": "http://unitsofmeasure.org", "fijo_tipo": "texto"},
        {"perfil": "PresionArterialCesfam", "ruta": "component[sistolica].valueQuantity.code", "fijo": "mm[Hg]", "fijo_tipo": "código simple"},
        {"perfil": "PresionArterialCesfam", "ruta": "component[diastolica].value[x]", "tipo": "Quantity"},
        {"perfil": "PresionArterialCesfam", "ruta": "component[diastolica].valueQuantity", "min": "1", "max": "1", "ms": "Sí"},
        {"perfil": "PresionArterialCesfam", "ruta": "component[diastolica].valueQuantity.system", "fijo": "http://unitsofmeasure.org", "fijo_tipo": "texto"},
        {"perfil": "PresionArterialCesfam", "ruta": "component[diastolica].valueQuantity.code", "fijo": "mm[Hg]", "fijo_tipo": "código simple"},
    ],
    "Extensiones": [
        {"nombre": "MedicionDomiciliaria", "titulo": "Medición domiciliaria", "descripcion": "Indica si la medición la tomó la propia persona en su domicilio.",
         "contexto": "Observation", "tipo": "boolean"},
        {"nombre": "ProgramaCardiovascular", "titulo": "Programa cardiovascular", "descripcion": "Datos del ingreso de la persona al programa cardiovascular.",
         "contexto": "Patient"},
        {"nombre": "FechaIngreso", "titulo": "Fecha de ingreso", "descripcion": "Día en que la persona ingresó al programa.",
         "tipo": "date", "parte_de": "ProgramaCardiovascular", "min": "1", "max": "1"},
        {"nombre": "NivelRiesgo", "titulo": "Nivel de riesgo", "descripcion": "Riesgo cardiovascular asignado al ingreso.",
         "tipo": "code", "valueset": "VSNivelRiesgo", "fuerza": "required", "parte_de": "ProgramaCardiovascular", "min": "1", "max": "1"},
    ],
    "Slices": [
        {"perfil": "PacienteCesfam", "elemento": "telecom", "slice": "telefono", "min": "0", "max": "1", "ms": "Sí", "discriminador": "value", "disc_ruta": "system",
         "fijo": "phone", "fijo_tipo": "código simple", "reglas": "closed", "descripcion": "Teléfono de contacto."},
        {"perfil": "PacienteCesfam", "elemento": "telecom", "slice": "correo", "min": "0", "max": "1", "ms": "Sí",
         "fijo": "email", "fijo_tipo": "código simple", "descripcion": "Correo electrónico de contacto."},
        {"perfil": "PresionArterialCesfam", "elemento": "component", "slice": "sistolica", "min": "1", "max": "1", "ms": "Sí", "discriminador": "pattern", "disc_ruta": "code",
         "fijo": "8480-6", "fijo_tipo": "código con sistema", "fijo_sistema": "LOINC", "reglas": "open", "descripcion": "Presión arterial sistólica."},
        {"perfil": "PresionArterialCesfam", "elemento": "component", "slice": "diastolica", "min": "1", "max": "1", "ms": "Sí",
         "fijo": "8462-4", "fijo_tipo": "código con sistema", "fijo_sistema": "LOINC", "descripcion": "Presión arterial diastólica."},
    ],
    "Instancias": [
        {"nombre": "PacienteEjemplo", "perfil": "PacienteCesfam", "titulo": "Paciente sintético del programa",
         "descripcion": "Persona ficticia con nombre, RUN, dos medios de contacto e ingreso al programa."},
        {"nombre": "ProfesionalEjemplo", "perfil": "CorePrestadorCl", "titulo": "Profesional sintético que toma la medición",
         "descripcion": "Profesional ficticio de enfermería, necesario porque CL Core pide quién realizó la medición (performer)."},
        {"nombre": "PresionNormalEjemplo", "perfil": "PresionArterialCesfam", "titulo": "Presión 118/76 en consulta (ejemplo sintético)",
         "descripcion": "Medición normal tomada en el centro de salud, con la persona sentada."},
        {"nombre": "PresionElevadaEjemplo", "perfil": "PresionArterialCesfam", "titulo": "Presión 152/96 en domicilio (ejemplo sintético)",
         "descripcion": "Medición elevada que la propia persona se tomó en su casa, sentada."},
    ],
    "Valores": [
        # paciente
        {"instancia": "PacienteEjemplo", "ruta": "identifier[0].use", "tipo": "código simple", "valor": "official"},
        {"instancia": "PacienteEjemplo", "ruta": "identifier[0].type", "tipo": "código con sistema", "valor": "NNCHL", "sistema": CS_DNI},
        {"instancia": "PacienteEjemplo", "ruta": "identifier[0].system", "tipo": "texto", "valor": RUN},
        {"instancia": "PacienteEjemplo", "ruta": "identifier[0].value", "tipo": "texto", "valor": "11.111.111-1"},
        {"instancia": "PacienteEjemplo", "ruta": "name[NombreOficial].use", "tipo": "código simple", "valor": "official"},
        {"instancia": "PacienteEjemplo", "ruta": "name[NombreOficial].family", "tipo": "texto", "valor": "Pérez"},
        {"instancia": "PacienteEjemplo", "ruta": "name[NombreOficial].family.extension[segundoApellido].valueString", "tipo": "texto", "valor": "Soto"},
        {"instancia": "PacienteEjemplo", "ruta": "name[NombreOficial].given[0]", "tipo": "texto", "valor": "Camila"},
        {"instancia": "PacienteEjemplo", "ruta": "gender", "tipo": "código simple", "valor": "female"},
        {"instancia": "PacienteEjemplo", "ruta": "birthDate", "tipo": "fecha", "valor": "1968-06-12"},
        {"instancia": "PacienteEjemplo", "ruta": "telecom[telefono].system", "tipo": "código simple", "valor": "phone"},
        {"instancia": "PacienteEjemplo", "ruta": "telecom[telefono].value", "tipo": "texto", "valor": "+56 9 0000 0000"},
        {"instancia": "PacienteEjemplo", "ruta": "telecom[correo].system", "tipo": "código simple", "valor": "email"},
        {"instancia": "PacienteEjemplo", "ruta": "telecom[correo].value", "tipo": "texto", "valor": "paciente.ejemplo@example.org"},
        {"instancia": "PacienteEjemplo", "ruta": "extension[programaCardiovascular].extension[fechaIngreso]", "tipo": "fecha", "valor": "2025-11-03"},
        {"instancia": "PacienteEjemplo", "ruta": "extension[programaCardiovascular].extension[nivelRiesgo]", "tipo": "código simple", "valor": "moderado"},
        # profesional
        {"instancia": "ProfesionalEjemplo", "ruta": "identifier[run].use", "tipo": "código simple", "valor": "official"},
        {"instancia": "ProfesionalEjemplo", "ruta": "identifier[run].type.coding.system", "tipo": "texto",
         "valor": "https://hl7chile.cl/fhir/ig/clcore/CodeSystem/CSTipoIdentificador"},
        {"instancia": "ProfesionalEjemplo", "ruta": "identifier[run].type.coding.code", "tipo": "código simple", "valor": "01"},
        {"instancia": "ProfesionalEjemplo", "ruta": "identifier[run].system", "tipo": "texto", "valor": RUN},
        {"instancia": "ProfesionalEjemplo", "ruta": "identifier[run].value", "tipo": "texto", "valor": "22.222.222-2"},
        {"instancia": "ProfesionalEjemplo", "ruta": "name.use", "tipo": "código simple", "valor": "official"},
        {"instancia": "ProfesionalEjemplo", "ruta": "name.family", "tipo": "texto", "valor": "Rojas"},
        {"instancia": "ProfesionalEjemplo", "ruta": "name.given[0]", "tipo": "texto", "valor": "Andrés"},
        # medición normal
        {"instancia": "PresionNormalEjemplo", "ruta": "performer[0]", "tipo": "referencia", "valor": "ProfesionalEjemplo"},
        {"instancia": "PresionNormalEjemplo", "ruta": "status", "tipo": "código simple", "valor": "final"},
        {"instancia": "PresionNormalEjemplo", "ruta": "category[VSCat]", "tipo": "código con sistema", "valor": "vital-signs", "sistema": CAT_OBS},
        {"instancia": "PresionNormalEjemplo", "ruta": "code", "tipo": "código con sistema", "valor": "85354-9", "sistema": "LOINC"},
        {"instancia": "PresionNormalEjemplo", "ruta": "code.text", "tipo": "texto", "valor": "Presión arterial"},
        {"instancia": "PresionNormalEjemplo", "ruta": "subject", "tipo": "referencia", "valor": "PacienteEjemplo"},
        {"instancia": "PresionNormalEjemplo", "ruta": "effectiveDateTime", "tipo": "fecha y hora", "valor": "2026-03-15T09:30:00-03:00"},
        {"instancia": "PresionNormalEjemplo", "ruta": "method", "tipo": "código con sistema", "valor": "sentado", "sistema": "CSPosturaMedicion", "texto": "Sentado"},
        {"instancia": "PresionNormalEjemplo", "ruta": "extension[medicionDomiciliaria]", "tipo": "booleano", "valor": "No"},
        {"instancia": "PresionNormalEjemplo", "ruta": "component[sistolica].code", "tipo": "código con sistema", "valor": "8480-6", "sistema": "LOINC"},
        {"instancia": "PresionNormalEjemplo", "ruta": "component[sistolica].valueQuantity", "tipo": "cantidad", "valor": "118", "unidad": "mm[Hg]", "texto": "mm[Hg]"},
        {"instancia": "PresionNormalEjemplo", "ruta": "component[diastolica].code", "tipo": "código con sistema", "valor": "8462-4", "sistema": "LOINC"},
        {"instancia": "PresionNormalEjemplo", "ruta": "component[diastolica].valueQuantity", "tipo": "cantidad", "valor": "76", "unidad": "mm[Hg]", "texto": "mm[Hg]"},
        # medición elevada en domicilio
        {"instancia": "PresionElevadaEjemplo", "ruta": "performer[0]", "tipo": "referencia", "valor": "ProfesionalEjemplo"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "status", "tipo": "código simple", "valor": "final"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "category[VSCat]", "tipo": "código con sistema", "valor": "vital-signs", "sistema": CAT_OBS},
        {"instancia": "PresionElevadaEjemplo", "ruta": "code", "tipo": "código con sistema", "valor": "85354-9", "sistema": "LOINC"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "code.text", "tipo": "texto", "valor": "Presión arterial"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "subject", "tipo": "referencia", "valor": "PacienteEjemplo"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "effectiveDateTime", "tipo": "fecha y hora", "valor": "2026-03-20T19:05:00-03:00"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "method", "tipo": "código con sistema", "valor": "sentado", "sistema": "CSPosturaMedicion", "texto": "Sentado"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "extension[medicionDomiciliaria]", "tipo": "booleano", "valor": "Sí"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "component[sistolica].code", "tipo": "código con sistema", "valor": "8480-6", "sistema": "LOINC"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "component[sistolica].valueQuantity", "tipo": "cantidad", "valor": "152", "unidad": "mm[Hg]", "texto": "mm[Hg]"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "component[diastolica].code", "tipo": "código con sistema", "valor": "8462-4", "sistema": "LOINC"},
        {"instancia": "PresionElevadaEjemplo", "ruta": "component[diastolica].valueQuantity", "tipo": "cantidad", "valor": "96", "unidad": "mm[Hg]", "texto": "mm[Hg]"},
    ],
    "CodeSystems": [
        {"nombre": "CSPosturaMedicion", "titulo": "Postura al medir la presión", "descripcion": "Posición de la persona mientras se toma la presión arterial."},
        {"nombre": "CSNivelRiesgo", "titulo": "Nivel de riesgo cardiovascular", "descripcion": "Clasificación del riesgo cardiovascular al ingreso al programa."},
    ],
    "Conceptos": [
        {"codesystem": "CSPosturaMedicion", "codigo": "sentado", "texto": "Sentado", "definicion": "Con la espalda apoyada y el brazo a la altura del corazón."},
        {"codesystem": "CSPosturaMedicion", "codigo": "de-pie", "texto": "De pie"},
        {"codesystem": "CSPosturaMedicion", "codigo": "acostado", "texto": "Acostado"},
        {"codesystem": "CSNivelRiesgo", "codigo": "bajo", "texto": "Riesgo bajo"},
        {"codesystem": "CSNivelRiesgo", "codigo": "moderado", "texto": "Riesgo moderado"},
        {"codesystem": "CSNivelRiesgo", "codigo": "alto", "texto": "Riesgo alto"},
    ],
    "ValueSets": [
        {"nombre": "VSPosturaMedicion", "titulo": "Posturas de medición", "descripcion": "Posturas aceptadas al registrar la presión arterial."},
        {"nombre": "VSNivelRiesgo", "titulo": "Niveles de riesgo", "descripcion": "Niveles de riesgo cardiovascular permitidos."},
    ],
    "Inclusiones": [
        {"valueset": "VSPosturaMedicion", "sistema": "CSPosturaMedicion"},
        {"valueset": "VSNivelRiesgo", "sistema": "CSNivelRiesgo"},
    ],
    "Documentación": [
        {"pagina": "inicio", "titulo": "Inicio",
         "texto": "### Control de presión arterial (ejercicio)\n\nGuía de ejercicio **con datos ficticios**, creada con cl-core-ig-agents. "
                  "Define cómo registrar la presión arterial de personas en el programa cardiovascular de un centro de salud.\n\n"
                  "Borrador: requiere revisión humana.\n\nVer los [artefactos](artifacts.html)."},
        {"pagina": "decisiones", "titulo": "Decisiones de diseño",
         "texto": "- **Los dos componentes son obligatorios** (1..1): una presión sin sistólica o sin diastólica no se puede interpretar.\n"
                  "- **El valor de la observación completa está prohibido** (`value[x]` 0..0): el valor vive en los componentes.\n"
                  "- **La postura es extensible, no obligatoria**: las posturas habituales están listadas, pero un caso clínico puede requerir otra, "
                  "y obligar a elegir de la lista llevaría a registrar datos falsos.\n"
                  "- **El contacto es teléfono o correo** (slicing cerrado en `telecom`), y al menos uno es obligatorio.\n"
                  "- **El RUN** se identifica con el sistema del Registro Civil.\n"
                  "- **Medición domiciliaria** es una extensión porque FHIR no tiene un elemento para esa distinción."},
    ],
}

if __name__ == "__main__":
    import copy

    from agents.catalog import CatalogIndex
    from libro.plantilla import guardar_plantilla
    cat = CatalogIndex.from_file(RAIZ / "build" / "catalog" / "catalog.json")
    destino = Path(__file__).with_name("solucion-ejercicio-1.xlsx")
    guardar_plantilla(destino, copy.deepcopy(DATOS), cat)
    print("Listo:", destino)
