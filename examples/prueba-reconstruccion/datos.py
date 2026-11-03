"""Prueba de reconstrucción: ¿se puede escribir en el Excel un perfil como CorePacienteCl partiendo de `Patient` base?

Reproduce las reglas del differential de CorePacienteCl (CL Core 1.9.3, paquete público) SIN usar CL Core:
padre vacío y «Usar CL Core» en No. Los nombres de las extensiones y de los slices son los mismos que los originales.
`comparar.py` compara el resultado con el differential real e imprime las diferencias.
"""
from __future__ import annotations

P = "PacienteReconstruido"
FP = "http://hl7.org/fhir/ValueSet/"


def _territorio(archivo: str, codesystem: str) -> list[dict]:
    """Códigos oficiales de regiones, provincias o comunas (examples/datos-territoriales-chile/*.csv; col. A = código, B = texto)."""
    import csv
    from pathlib import Path
    ruta = Path(__file__).resolve().parents[1] / "datos-territoriales-chile" / archivo
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return [{"codesystem": codesystem, "codigo": r["codigo"], "texto": r["texto"]} for r in csv.DictReader(f, delimiter=";")]


DIR = "DireccionCl"


def e(ruta, mn="", mx="", ms="", perfil=P, **kw):
    return {"perfil": perfil, "ruta": ruta, "min": mn, "max": mx, "ms": ms, **kw}


DATOS = {
    "Guía": {"id": "reconstruccion-paciente", "titulo": "Reconstrucción de Paciente (prueba)",
             "descripcion": "Prueba: reproduce un perfil de paciente sin heredar de CL Core.",
             "canonical": "https://example.org/fhir/ig/reconstruccion", "version": "0.1.0", "estado": "draft",
             "publicador": "Prueba", "licencia": "CC0-1.0", "usa_clcore": "No"},
    "Perfiles": [{"nombre": P, "recurso": "Patient", "padre": "", "titulo": "Paciente reconstruido",
                  "descripcion": "Reproduce las reglas de CorePacienteCl partiendo del Patient base."},
                 {"nombre": DIR, "recurso": "Address", "padre": "", "titulo": "Dirección reconstruida",
                  "descripcion": "Perfil de un tipo de dato (Address): reproduce las reglas de cl-address sin heredar de CL Core."}],
    "Extensiones": [
        {"nombre": "IdentidadDeGenero", "titulo": "Identidad de género", "descripcion": "Identidad de género declarada.", "contexto": "Patient", "tipo": "CodeableConcept"},
        {"nombre": "SexoBiologico", "titulo": "Sexo biológico", "descripcion": "Sexo biológico al nacer.", "contexto": "Patient", "tipo": "CodeableConcept"},
        {"nombre": "Nacionalidad", "titulo": "Nacionalidad", "descripcion": "País de nacionalidad.", "contexto": "Patient", "tipo": "CodeableConcept"},
        {"nombre": "PaisEmisionDocumento", "titulo": "País de emisión del documento", "descripcion": "País que emitió el documento.", "contexto": "Patient.identifier.type", "tipo": "CodeableConcept"},
        {"nombre": "SegundoApellido", "titulo": "Segundo apellido", "descripcion": "Segundo apellido.", "contexto": "Patient.name.family", "tipo": "string"},
        {"nombre": "Comunas", "titulo": "Comuna", "descripcion": "Comuna de la dirección.", "contexto": "Address.city", "tipo": "CodeableConcept", "valueset": "VSComunas", "fuerza": "required"},
        {"nombre": "Provincias", "titulo": "Provincia", "descripcion": "Provincia de la dirección.", "contexto": "Address.district", "tipo": "CodeableConcept", "valueset": "VSProvincias", "fuerza": "required"},
        {"nombre": "Regiones", "titulo": "Región", "descripcion": "Región de la dirección.", "contexto": "Address.state", "tipo": "CodeableConcept", "valueset": "VSRegiones", "fuerza": "required"},
        {"nombre": "Paises", "titulo": "País", "descripcion": "País de la dirección.", "contexto": "Address.country", "tipo": "CodeableConcept"},
        {"nombre": "Geolocalizacion", "url": "http://hl7.org/fhir/StructureDefinition/geolocation"},
        {"nombre": "IdContacto", "titulo": "Identificador del contacto", "descripcion": "Documento del contacto y país que lo emitió.", "contexto": "Patient.contact"},
        {"nombre": "TutId", "titulo": "Documento del contacto", "parte_de": "IdContacto", "tipo": "Identifier", "min": "1", "max": "1"},
        {"nombre": "DocProc", "titulo": "País del documento", "parte_de": "IdContacto", "tipo": "CodeableConcept", "min": "0", "max": "1",
         "valueset": "VSPaises", "fuerza": "required"},
    ],
    "Slices": [
        {"perfil": P, "elemento": "name", "slice": "NombreOficial", "min": "0", "max": "1", "ms": "Sí", "discriminador": "value", "disc_ruta": "use"},
        {"perfil": P, "elemento": "name", "slice": "NombreSocial", "min": "0", "max": "1", "ms": "Sí"},
    ],
    "ValorExtensiones": [
        {"extension": "TutId", "ruta": "type", "min": "1"}, {"extension": "TutId", "ruta": "type.coding.system", "min": "1"},
        {"extension": "TutId", "ruta": "type.coding.code", "min": "1"}, {"extension": "TutId", "ruta": "system", "min": "1"},
        {"extension": "TutId", "ruta": "value", "min": "1"},
        {"extension": "DocProc", "ruta": "coding", "min": "1", "max": "1"}, {"extension": "DocProc", "ruta": "coding.system", "min": "1"},
        {"extension": "DocProc", "ruta": "coding.code", "min": "1"},
    ],
    "CodeSystems": [{"nombre": "CSPaises", "titulo": "Países", "descripcion": "Países (muestra)."},{"nombre": "CSTiposDocumentos", "titulo": "Tipos de documento", "descripcion": "Tipos de documento de identidad."},
                    {"nombre": "CSContactoRelacion", "titulo": "Relación del contacto", "descripcion": "Relación del contacto con el paciente."},
                    {"nombre": "CSRegiones", "titulo": "Regiones de Chile", "descripcion": "Regiones de Chile con su código único territorial."},
                    {"nombre": "CSProvincias", "titulo": "Provincias de Chile", "descripcion": "Provincias de Chile con su código único territorial."},
                    {"nombre": "CSComunas", "titulo": "Comunas de Chile", "descripcion": "Comunas de Chile con su código único territorial."}],
    "Conceptos": [
        {"codesystem": "CSPaises", "codigo": "CL", "texto": "Chile"}, {"codesystem": "CSPaises", "codigo": "AR", "texto": "Argentina"},
        {"codesystem": "CSTiposDocumentos", "codigo": "RUN", "texto": "RUN"},
        {"codesystem": "CSTiposDocumentos", "codigo": "PAS", "texto": "Pasaporte"},
        {"codesystem": "CSContactoRelacion", "codigo": "C", "texto": "Contacto de emergencia"},
        {"codesystem": "CSContactoRelacion", "codigo": "N", "texto": "Persona de contacto"},
        *_territorio("regiones.csv", "CSRegiones"), *_territorio("provincias.csv", "CSProvincias"), *_territorio("comunas.csv", "CSComunas"),
    ],
    "ValueSets": [{"nombre": "VSPaises", "titulo": "Países", "descripcion": "Países permitidos (muestra)."},
                  {"nombre": "VSDiagnosticosSCT", "titulo": "Diagnósticos (SNOMED CT)", "descripcion": "Hallazgos clínicos de SNOMED CT más «sin problemas actuales»."},
                  {"nombre": "VSTiposDocumentos", "titulo": "Tipos de documento", "descripcion": "Tipos de documento permitidos."},
                  {"nombre": "VSContactoRelacion", "titulo": "Relación del contacto", "descripcion": "Relaciones permitidas."},
                  {"nombre": "VSRegiones", "titulo": "Regiones de Chile", "descripcion": "Regiones de Chile."},
                  {"nombre": "VSProvincias", "titulo": "Provincias de Chile", "descripcion": "Provincias de Chile."},
                  {"nombre": "VSComunas", "titulo": "Comunas de Chile", "descripcion": "Comunas de Chile."}],
    "Inclusiones": [{"valueset": "VSPaises", "sistema": "CSPaises"},
                    {"valueset": "VSRegiones", "sistema": "CSRegiones"}, {"valueset": "VSProvincias", "sistema": "CSProvincias"},
                    {"valueset": "VSComunas", "sistema": "CSComunas"},
                    {"valueset": "VSDiagnosticosSCT", "sistema": "SNOMED", "filtro": "descendent-of", "filtro_valor": "404684003"},
                    {"valueset": "VSDiagnosticosSCT", "sistema": "SNOMED", "codigo": "160245001"},
                    {"valueset": "VSTiposDocumentos", "sistema": "CSTiposDocumentos"},
                    {"valueset": "VSContactoRelacion", "sistema": "CSContactoRelacion"}],
    "Elementos": [
        e("extension[identidadDeGenero]", "0", "1", "Sí"), e("extension[sexoBiologico]", "0", "1", "Sí"),
        e("extension[nacionalidad]", "0", "*", "Sí"),
        e("identifier", ms="Sí"), e("identifier.use", ms="Sí"),
        e("identifier.type", ms="Sí", valueset="VSTiposDocumentos", fuerza="extensible"),
        e("identifier.type.extension[paisEmisionDocumento]", "0", "1", "Sí"),
        e("identifier.type.coding", ms="Sí"), e("identifier.type.coding.system", ms="Sí"),
        e("identifier.type.coding.code", ms="Sí"), e("identifier.type.coding.display", ms="Sí"),
        e("name[NombreOficial].use", "1", ms="Sí", fijo="official", fijo_tipo="código simple"),
        e("name[NombreOficial].family", ms="Sí"),
        e("name[NombreOficial].family.extension[segundoApellido]", "0", "1", "Sí"),
        e("name[NombreOficial].given", ms="Sí"),
        e("name[NombreSocial].use", "1", ms="Sí", fijo="usual", fijo_tipo="código simple"),
        e("name[NombreSocial].text", mx="0"), e("name[NombreSocial].family", mx="0"),
        e("name[NombreSocial].given", "1", ms="Sí"),
        e("name[NombreSocial].prefix", mx="0"), e("name[NombreSocial].suffix", mx="0"), e("name[NombreSocial].period", mx="0"),
        e("telecom", ms="Sí"),
        e("telecom.system", ms="Sí", valueset=FP + "contact-point-system", fuerza="required"),
        e("telecom.value", ms="Sí"),
        e("telecom.use", ms="Sí", valueset=FP + "contact-point-use", fuerza="required"),
        e("gender", ms="Sí", resumen="Sexo administrativo", definicion="Sexo que consta en el registro administrativo de la persona."),
        e("birthDate", ms="Sí", resumen="Fecha de nacimiento", definicion="Fecha de nacimiento de la persona.",
          comentario="Si solo se conoce el año, se informa solo el año."),
        e("address", ms="Sí", resumen="Dirección", perfil_tipo=DIR), e("contact", ms="Sí", resumen="Persona de contacto"),
        e("contact.extension[idContacto]", "0", "*", "Sí"),
        e("contact.relationship", ms="Sí", valueset="VSContactoRelacion", fuerza="required"),
        e("contact.relationship.coding", ms="Sí"),
        e("contact.name", ms="Sí"),
        e("contact.name.use", ms="Sí", fijo="official", fijo_tipo="código simple"),
        e("contact.name.family", ms="Sí"),
        e("contact.name.family.extension[segundoApellido]", "0", "1", "Sí"),
        e("contact.name.given", ms="Sí"),
        e("communication", ms="Sí"),
        e("communication.language", ms="Sí", valueset=FP + "all-languages", fuerza="required"),
        e("extension[geolocalizacion]", "0", "1", "Sí", perfil=DIR), e("use", ms="Sí", perfil=DIR), e("line", mx="1", ms="Sí", perfil=DIR),
        e("city", ms="Sí", perfil=DIR), e("city.extension[comunas]", "1", "1", "Sí", perfil=DIR),
        e("district", ms="Sí", perfil=DIR), e("district.extension[provincias]", "1", "1", "Sí", perfil=DIR),
        e("state", ms="Sí", perfil=DIR), e("state.extension[regiones]", "1", "1", "Sí", perfil=DIR),
        e("country", ms="Sí", perfil=DIR), e("country.extension[paises]", "1", "1", "Sí", perfil=DIR),
        e("generalPractitioner", ms="Sí", destinos="Organization, Practitioner, PractitionerRole",
          resumen="Prestador de atención primaria"), e("generalPractitioner.reference", ms="Sí"), e("generalPractitioner.display", ms="Sí"),
    ],
    "Instancias": [], "Valores": [], "Documentación": [],
}


if __name__ == "__main__":      # genera prueba-reconstruccion.xlsx junto a este archivo
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from libro.plantilla import guardar_plantilla
    print(guardar_plantilla(Path(__file__).with_name("prueba-reconstruccion.xlsx"), DATOS))
