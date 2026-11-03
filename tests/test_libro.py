"""Libro de Excel -> guía: plantilla, lector, verificador y generador de FSH."""
from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

import cl_ig
from agents.catalog import CatalogIndex
from libro.ejemplo import DATOS
from libro.esquema import HOJA_POR_NOMBRE
from libro.fsh import construir_archivos
from libro.lector import LibroInvalido, leer_libro
from libro.plantilla import guardar_plantilla
from libro.revisar import hay_errores, revisar_libro, texto_avisos

CATALOGO = Path(__file__).resolve().parent.parent / "build" / "catalog" / "catalog.json"
necesita_catalogo = pytest.mark.skipif(not CATALOGO.is_file(), reason="falta build/catalog (make catalog)")


def libro_de(tmp_path, cambio=None):
    datos = copy.deepcopy(DATOS)
    if cambio:
        cambio(datos)
    return leer_libro(guardar_plantilla(tmp_path / "l.xlsx", datos))


def avisos_de(tmp_path, cambio=None, catalogo=None):
    return revisar_libro(libro_de(tmp_path, cambio), catalogo)


def mensajes(avisos, nivel=None):
    return " || ".join(f"{a.mensaje} {a.que_hacer}" for a in avisos if nivel in (None, a.nivel))


def fila(datos, hoja, **claves):
    return next(f for f in datos[hoja] if all(f.get(k) == v for k, v in claves.items()))


# ---------------------------------------------------------------- plantilla y lector
def test_ejemplo_sintetico_no_tiene_errores(tmp_path):
    avisos = avisos_de(tmp_path)
    assert not hay_errores(avisos), mensajes(avisos, "error")


def test_la_plantilla_vacia_pide_lo_obligatorio(tmp_path):
    ruta = guardar_plantilla(tmp_path / "vacia.xlsx")
    avisos = revisar_libro(leer_libro(ruta))
    texto = mensajes(avisos, "error")
    assert "Falta «Identificador corto»" in texto and "Falta «Título»" in texto
    assert "no define ningún perfil" in texto


def test_el_lector_devuelve_lo_escrito_y_las_filas(tmp_path):
    libro = libro_de(tmp_path)
    assert libro.guia["id"] == "control-frecuencia-demo"
    perfiles = libro.filas("Perfiles")
    assert [p["nombre"] for p in perfiles] == ["PacienteControl", "FrecuenciaCardiacaControl", "DoctorControl"]
    assert perfiles[0]["_fila"] == 5
    assert libro.filas("Elementos")[0]["min"] == "1"          # los números llegan como texto limpio


def test_fechas_de_excel_se_leen_en_formato_fhir(tmp_path):
    ruta = guardar_plantilla(tmp_path / "f.xlsx", copy.deepcopy(DATOS))
    wb = load_workbook(ruta)
    ws = wb["Valores"]
    for r in range(5, ws.max_row + 1):
        if ws.cell(r, 2).value == "birthDate":
            ws.cell(r, 4).value = datetime(1975, 6, 12)
    wb.save(ruta)
    valores = leer_libro(ruta).filas("Valores")
    assert next(v for v in valores if v["ruta"] == "birthDate")["valor"] == "1975-06-12"


def test_archivo_que_no_es_la_plantilla(tmp_path):
    wb = Workbook()
    wb.active.title = "Otra"
    wb.save(tmp_path / "x.xlsx")
    with pytest.raises(LibroInvalido, match="Falta la hoja «Guía»"):
        leer_libro(tmp_path / "x.xlsx")
    (tmp_path / "no.xlsx").write_text("no soy excel")
    with pytest.raises(LibroInvalido, match="No pude abrir"):
        leer_libro(tmp_path / "no.xlsx")


def test_encabezado_cambiado_se_explica(tmp_path):
    ruta = guardar_plantilla(tmp_path / "e.xlsx", copy.deepcopy(DATOS))
    wb = load_workbook(ruta)
    wb["Perfiles"].cell(4, 1).value = "Nombre"
    wb.save(ruta)
    with pytest.raises(LibroInvalido, match="Nombre del perfil"):
        leer_libro(ruta)


# ---------------------------------------------------------------- verificador
def esperar_error(tmp_path, cambio, fragmento, catalogo=None):
    texto = mensajes(avisos_de(tmp_path, cambio, catalogo), "error")
    assert fragmento in texto, texto


def test_nombre_de_perfil_con_espacios_sugiere_uno_valido(tmp_path):
    esperar_error(tmp_path, lambda d: d["Perfiles"][0].update(nombre="Paciente control"), "«PacienteControl»")


def test_recurso_con_errata_sugiere_el_correcto(tmp_path):
    def c(d):
        d["Perfiles"][1]["recurso"] = "Observaton"
    esperar_error(tmp_path, c, "«Observation»")


def test_perfil_repetido(tmp_path):
    def c(d):
        d["Perfiles"].append(dict(d["Perfiles"][0]))
    esperar_error(tmp_path, c, "está repetido")


def test_minimo_mayor_que_maximo(tmp_path):
    def c(d):
        fila(d, "Elementos", ruta="gender").update(min="2", max="1")
    esperar_error(tmp_path, c, "es mayor que el máximo")


def test_cardinalidad_no_puede_ser_mas_laxa_que_el_padre_del_libro(tmp_path):
    def c(d):
        d["Perfiles"].append({"nombre": "PacienteEstricto", "recurso": "Patient", "padre": "PacienteControl", "descripcion": "x"})
        d["Elementos"].append({"perfil": "PacienteEstricto", "ruta": "gender", "min": "0", "max": "1"})
    esperar_error(tmp_path, c, "no puede ser más permisivo que su padre")


def test_ruta_con_nombre_del_recurso(tmp_path):
    def c(d):
        fila(d, "Elementos", ruta="gender").update(ruta="Patient.gender")
    esperar_error(tmp_path, c, "Escríbela sin él: «gender»")


def test_valueset_inexistente_sugiere(tmp_path):
    def c(d):
        fila(d, "Elementos", ruta="method").update(valueset="VSContextoMedicon")
    esperar_error(tmp_path, c, "«VSContextoMedicion»")


def test_valor_fijo_necesita_tipo(tmp_path):
    def c(d):
        fila(d, "Elementos", ruta="valueQuantity.unit").update(fijo_tipo="")
    esperar_error(tmp_path, c, "necesita «Tipo del valor fijo»")


def test_fecha_dia_mes_anio_indica_como_escribirla(tmp_path):
    def c(d):
        fila(d, "Valores", ruta="birthDate").update(valor="12/06/1975")
    esperar_error(tmp_path, c, "1975-06-12")


def test_fecha_imposible(tmp_path):
    def c(d):
        fila(d, "Valores", ruta="birthDate").update(valor="1975-02-30")
    esperar_error(tmp_path, c, "no existe en el calendario")


def test_fecha_y_hora_sin_zona_horaria(tmp_path):
    def c(d):
        fila(d, "Valores", ruta="effectiveDateTime").update(valor="2026-03-15T09:30:00")
    esperar_error(tmp_path, c, "no es una fecha válida")


def test_numero_con_coma_decimal(tmp_path):
    def c(d):
        fila(d, "Valores", ruta="valueQuantity").update(valor="72,5")
    esperar_error(tmp_path, c, "usa punto")


def test_cantidad_sin_unidad(tmp_path):
    def c(d):
        fila(d, "Valores", ruta="valueQuantity").update(unidad="")
    esperar_error(tmp_path, c, "necesita unidad")


def test_codigo_que_no_existe_en_un_codesystem_del_libro(tmp_path):
    def c(d):
        fila(d, "Valores", ruta="method").update(valor="reposso")
    esperar_error(tmp_path, c, "«reposo»")


def test_codigo_con_sistema_sin_sistema(tmp_path):
    def c(d):
        fila(d, "Valores", ruta="method").update(sistema="")
    esperar_error(tmp_path, c, "necesita un sistema")


def test_sistema_desconocido_sugiere_codesystem_del_libro(tmp_path):
    def c(d):
        fila(d, "Valores", ruta="method").update(sistema="CSContextoMedicon")
    esperar_error(tmp_path, c, "«CSContextoMedicion»")


def test_mismo_codigo_con_dos_significados_explica_la_salida(tmp_path):
    def c(d):
        d["Conceptos"].append({"codesystem": "CSContextoMedicion", "codigo": "reposo", "texto": "Dormido"})
    texto = mensajes(avisos_de(tmp_path, c), "error")
    assert "con otro significado" in texto and "un CodeSystem por pregunta" in texto


def test_codesystem_completo_sin_conceptos(tmp_path):
    def c(d):
        d["Conceptos"].clear()
        d["Valores"][:] = [v for v in d["Valores"] if v["ruta"] != "method"]
    esperar_error(tmp_path, c, "no tiene ninguno en la hoja Conceptos")


def test_valueset_sin_contenido(tmp_path):
    def c(d):
        d["Inclusiones"].clear()
    esperar_error(tmp_path, c, "no tiene contenido")


def test_referencia_a_ejemplo_inexistente(tmp_path):
    def c(d):
        fila(d, "Valores", ruta="subject").update(valor="PacienteDemoo")
    esperar_error(tmp_path, c, "«PacienteDemo»")


def test_ejemplo_repetido(tmp_path):
    def c(d):
        d["Instancias"].append(dict(d["Instancias"][0]))
    esperar_error(tmp_path, c, "está repetido")


def test_valor_distinto_al_valor_fijo_del_perfil(tmp_path):
    def c(d):
        fila(d, "Valores", instancia="FrecuenciaReposoDemo", ruta="code").update(valor="8310-5")
    texto = mensajes(avisos_de(tmp_path, c), "error")
    assert "tiene valor fijo «8867-4»" in texto


def test_ejemplo_sin_elemento_que_fhir_exige(tmp_path):
    def c(d):
        d["Valores"][:] = [v for v in d["Valores"] if not (v["instancia"] == "FrecuenciaReposoDemo" and v["ruta"] == "status")]
    texto = mensajes(avisos_de(tmp_path, c), "aviso")
    assert "FHIR exige «status»" in texto


def test_ejemplo_sin_elemento_obligatorio_del_perfil(tmp_path):
    def c(d):
        d["Valores"][:] = [v for v in d["Valores"] if not (v["instancia"] == "PacienteDemo" and v["ruta"] == "birthDate")]
    texto = mensajes(avisos_de(tmp_path, c), "aviso")
    assert "exige «birthDate»" in texto


def test_canonical_invalida_y_estado(tmp_path):
    def c(d):
        d["Guía"]["canonical"] = "miguia.cl/"
        d["Guía"]["estado"] = "listo"
    texto = mensajes(avisos_de(tmp_path, c), "error")
    assert "no es una dirección válida" in texto and "Estado «listo»" in texto


def test_pagina_con_id_invalido(tmp_path):
    def c(d):
        d["Documentación"][1]["pagina"] = "Mi Página"
    esperar_error(tmp_path, c, "«mi-pagina»")


def test_sin_catalogo_los_nombres_de_clcore_son_aviso_no_error(tmp_path):
    avisos = avisos_de(tmp_path)
    assert not hay_errores(avisos)
    assert "No pude comprobar el perfil padre «CorePacienteCl»" in mensajes(avisos, "aviso")


@necesita_catalogo
def test_con_catalogo_el_ejemplo_sigue_sin_errores_ni_avisos(tmp_path):
    avisos = avisos_de(tmp_path, catalogo=CatalogIndex.from_file(CATALOGO))
    assert avisos == [], mensajes(avisos)


@necesita_catalogo
def test_padre_de_clcore_inexistente_y_con_recurso_distinto(tmp_path):
    cat = CatalogIndex.from_file(CATALOGO)

    def c(d):
        d["Perfiles"][0]["padre"] = "CorePacienteC"
    esperar_error(tmp_path, c, "«CorePacienteCl»", cat)

    def c2(d):
        d["Perfiles"][0]["padre"] = "CoreObservacionCL"
    esperar_error(tmp_path, c2, "es un Observation", cat)


@necesita_catalogo
def test_codigo_de_clcore_inexistente(tmp_path):
    def c(d):
        fila(d, "Valores", ruta="identifier[0].type").update(valor="XXXX")
    esperar_error(tmp_path, c, "no existe en el sistema de CL Core", CatalogIndex.from_file(CATALOGO))


# ---------------------------------------------------------------- generador
def test_fsh_del_ejemplo(tmp_path):
    a = construir_archivos(libro_de(tmp_path))
    perfiles, ejemplos, term = a["input/fsh/perfiles.fsh"], a["input/fsh/ejemplos.fsh"], a["input/fsh/terminologia.fsh"]
    assert "Profile: FrecuenciaCardiacaControl\nParent: cl-core-signos-vitales" in perfiles
    assert "* gender 1..1 MS" in perfiles
    assert '* valueQuantity.code = #"/min"' in perfiles
    assert "* method from VSContextoMedicion (extensible)" in perfiles
    assert "* value[x] only Quantity" in perfiles
    assert "InstanceOf: PacienteControl" in ejemplos
    assert "* identifier[0].type = $CSCodigoDNI#NNCHL" in ejemplos
    assert "* subject = Reference(PacienteDemo)" in ejemplos
    assert "* valueQuantity = 72 '/min' \"/min\"" in ejemplos
    assert '* method = CSContextoMedicion#reposo "En reposo"' in ejemplos
    assert "* include codes from system CSContextoMedicion" in term
    assert '* #reposo "En reposo" "Tras al menos 5 minutos sentado o acostado."' in term


def test_sushi_config_y_paginas(tmp_path):
    yaml = pytest.importorskip("yaml")
    a = construir_archivos(libro_de(tmp_path))
    cfg = yaml.safe_load(a["sushi-config.yaml"])
    assert cfg["id"] == "control-frecuencia-demo" and cfg["dependencies"] == {"hl7.fhir.cl.clcore": "1.9.3"}
    assert list(cfg["pages"]) == ["index.md", "requisitos.md", "decisiones.md"]
    assert "input/pagecontent/index.md" in a and "input/pagecontent/decisiones.md" in a
    assert a["ig.ini"].startswith("[IG]") and "ImplementationGuide-control-frecuencia-demo" in a["ig.ini"]


def test_sin_clcore_no_hay_dependencia(tmp_path):
    def c(d):
        d["Guía"]["usa_clcore"] = "No"
        d["Perfiles"][0]["padre"] = ""
        d["Perfiles"][1]["padre"] = ""
        d["Instancias"][0]["perfil"] = "Patient"
    libro = libro_de(tmp_path, c)
    assert "dependencies" not in construir_archivos(libro)["sushi-config.yaml"]


def test_borrador_de_inicio_cuando_no_hay_pagina(tmp_path):
    def c(d):
        d["Documentación"].clear()
    a = construir_archivos(libro_de(tmp_path, c))
    md = a["input/pagecontent/index.md"]
    assert "revisión humana" in md and "`FrecuenciaCardiacaControl`" in md and "`CSContextoMedicion`" in md
    assert "decisiones.md" not in a["sushi-config.yaml"] and "index.md" in a["sushi-config.yaml"]


def test_dos_sistemas_externos_no_chocan_en_el_alias(tmp_path):
    def c(d):
        d["Valores"].append({"instancia": "FrecuenciaReposoDemo", "ruta": "interpretation", "tipo": "código con sistema",
                             "valor": "N", "sistema": "https://a.org/fhir/CodeSystem/Tipo"})
        d["Valores"].append({"instancia": "FrecuenciaReposoDemo", "ruta": "note.text", "tipo": "código con sistema",
                             "valor": "X", "sistema": "https://b.org/fhir/CodeSystem/Tipo"})
    aliases = construir_archivos(libro_de(tmp_path, c))["input/fsh/aliases.fsh"]
    assert "Alias: $Tipo = https://a.org/fhir/CodeSystem/Tipo" in aliases
    assert "Alias: $Tipo2 = https://b.org/fhir/CodeSystem/Tipo" in aliases


def test_codigo_con_espacios_va_entre_comillas(tmp_path):
    def c(d):
        d["Conceptos"].append({"codesystem": "CSContextoMedicion", "codigo": "tras comer", "texto": "Tras comer"})
    assert '* #"tras comer" "Tras comer"' in construir_archivos(libro_de(tmp_path, c))["input/fsh/terminologia.fsh"]


def test_misma_entrada_misma_salida(tmp_path):
    assert construir_archivos(libro_de(tmp_path)) == construir_archivos(libro_de(tmp_path))


# ---------------------------------------------------------------- comandos
def test_cli_plantilla_revisar_construir(tmp_path, capsys):
    xlsx = tmp_path / "demo.xlsx"
    assert cl_ig.main(["plantilla", str(xlsx), "--ejemplo"]) == 0
    assert cl_ig.main(["plantilla", str(xlsx), "--ejemplo"]) == 2            # no pisa sin --forzar
    assert cl_ig.main(["revisar", str(xlsx)]) == 0
    salida = tmp_path / "ig"
    assert cl_ig.main(["construir", str(xlsx), "--sin-docker", "--salida", str(salida)]) == 0
    assert (salida / "input" / "fsh" / "perfiles.fsh").is_file() and (salida / "sushi-config.yaml").is_file()
    assert (salida / "avisos-del-libro.txt").is_file()
    assert "Guía escrita en" in capsys.readouterr().out


def test_cli_construir_no_escribe_si_hay_errores(tmp_path, capsys):
    xlsx = guardar_plantilla(tmp_path / "malo.xlsx")
    salida = tmp_path / "ig"
    assert cl_ig.main(["construir", str(xlsx), "--sin-docker", "--salida", str(salida)]) == 1
    assert not salida.exists()
    assert "No construyo la guía mientras haya errores" in capsys.readouterr().err


def test_cli_revisar_archivo_inexistente(tmp_path):
    assert cl_ig.main(["revisar", str(tmp_path / "nada.xlsx")]) == 2


def test_ruta_que_parece_un_tipo_se_explica(tmp_path):
    def c(d):
        fila(d, "Elementos", ruta="gender").update(ruta="HumanName")
    esperar_error(tmp_path, c, "parece un tipo o un recurso")


def test_sushi_config_es_yaml_valido_sin_pyyaml_instalado(tmp_path):
    texto = construir_archivos(libro_de(tmp_path))["sushi-config.yaml"]
    assert 'jurisdiction: "urn:iso:std:iso:3166#CL \\"Chile\\""' in texto
    # sin comillas: el IG Publisher lee la dependencia como texto y las dejaría dentro de la URL
    assert "dependencies:\n  hl7.fhir.cl.clcore: 1.9.3\n" in texto
    assert "version: 0.1.0\n" in texto and "fhirVersion: 4.0.1\n" in texto
    assert "instanceOptions:\n  manualSliceOrdering: true" in texto


@necesita_catalogo
def test_slice_que_el_perfil_de_clcore_no_define(tmp_path):
    def c(d):
        d["Perfiles"].append({"nombre": "DoctorControl", "recurso": "Practitioner", "padre": "CorePrestadorCl", "descripcion": "x"})
        d["Instancias"].append({"nombre": "DoctorDemo", "perfil": "DoctorControl", "descripcion": "x"})
        d["Valores"].append({"instancia": "DoctorDemo", "ruta": "name[NombreOficial].family", "tipo": "texto", "valor": "Pérez"})
    texto = mensajes(avisos_de(tmp_path, c, CatalogIndex.from_file(CATALOGO)), "aviso")
    assert "no define el slice «NombreOficial»" in texto and "existe en: CorePacienteCl" in texto
    assert "name[0].family" in texto


@necesita_catalogo
def test_slices_validos_no_generan_aviso(tmp_path):
    avisos = avisos_de(tmp_path, catalogo=CatalogIndex.from_file(CATALOGO))
    assert "slice" not in mensajes(avisos)


@necesita_catalogo
def test_codigo_que_el_perfil_de_clcore_no_acepta_en_ese_elemento(tmp_path):
    def c(d):
        fila(d, "Valores", instancia="DoctorDemo", ruta="identifier[0].type").update(
            sistema="https://hl7chile.cl/fhir/ig/clcore/CodeSystem/CSCodigoDNI", valor="NNCHL")
    texto = mensajes(avisos_de(tmp_path, c, CatalogIndex.from_file(CATALOGO)), "error")
    assert "debe usar códigos del ValueSet «VSTipoIdentificador»" in texto
    assert "CSTipoIdentificador" in texto


@necesita_catalogo
def test_el_ejemplo_ya_usa_el_codigo_correcto_del_prestador(tmp_path):
    assert avisos_de(tmp_path, catalogo=CatalogIndex.from_file(CATALOGO)) == []


def test_texto_de_un_codigo_loinc_se_advierte(tmp_path):
    def c(d):
        fila(d, "Valores", instancia="FrecuenciaReposoDemo", ruta="code").update(texto="Frecuencia cardíaca")
    texto = mensajes(avisos_de(tmp_path, c), "aviso")
    assert "idéntico al nombre oficial" in texto and "code.text" in texto


def test_un_correo_de_contacto_no_va_al_sushi_config_sino_a_la_portada(tmp_path):
    def c(d):
        d["Guía"]["contacto"] = "alguien@example.org"
        d["Documentación"].clear()
    a = construir_archivos(libro_de(tmp_path, c))
    assert "alguien@example.org" not in a["sushi-config.yaml"] and "email" not in a["sushi-config.yaml"]
    assert "Contacto: alguien@example.org" in a["input/pagecontent/index.md"]


def test_un_sitio_web_de_contacto_va_como_url_del_publicador(tmp_path):
    def c(d):
        d["Guía"]["contacto"] = "https://example.org"
    assert "  url: https://example.org\n" in construir_archivos(libro_de(tmp_path, c))["sushi-config.yaml"]


# ---------------------------------------------------------------- listas desplegables y rutas
from libro import elementos  # noqa: E402
from libro.plantilla import crear_libro  # noqa: E402


def test_rutas_de_fhir_r4_incluyen_hijos_de_tipos_y_variantes_de_choice():
    p = elementos.rutas_de_recurso("Patient")
    assert "name.family" in p and "identifier.type.coding.system" in p and "birthDate" in p
    o = elementos.rutas_de_recurso("Observation")
    assert "value[x]" in o and "valueQuantity.unit" in o and "valueCodeableConcept.coding.code" in o and "component.valueQuantity" in o
    assert "valueQuantity.unit" not in p
    assert len(elementos.datos()["recursos"]) == 146


def test_comprobar_ruta_sugiere_y_no_opina_de_extensiones_ni_slices_propios():
    p = elementos.rutas_de_recurso("Patient")
    assert elementos.comprobar_ruta("name[0].family", p) is None
    assert "name.family" in elementos.comprobar_ruta("name.famly", p)
    assert elementos.comprobar_ruta("extension[Algo].valueString", p) is None
    assert elementos.comprobar_ruta("identifier[run].value", p) is None


def test_ruta_inexistente_en_elementos_y_en_valores(tmp_path):
    def c(d):
        fila(d, "Elementos", perfil="PacienteControl", ruta="gender").update(ruta="gendr")
        fila(d, "Valores", instancia="PacienteDemo", ruta="birthDate").update(ruta="birthdate")
    texto = mensajes(avisos_de(tmp_path, c), "error")
    assert "«gendr» no es un elemento de «PacienteControl»" in texto and "«gender»" in texto
    assert "«birthdate» no es un elemento de «PacienteDemo»" not in texto      # el perfil del ejemplo es PacienteControl
    assert "«birthdate» no es un elemento de «PacienteControl»" in texto and "«birthDate»" in texto


def test_elemento_de_otro_recurso_se_detecta(tmp_path):
    def c(d):
        fila(d, "Elementos", perfil="PacienteControl", ruta="gender").update(ruta="valueQuantity.unit")
    esperar_error(tmp_path, c, "no es un elemento de «PacienteControl»")


def test_cardinalidad_frente_al_recurso_base_de_fhir(tmp_path):
    def c(d):
        d["Perfiles"].append({"nombre": "ObsLibre", "recurso": "Observation", "descripcion": "x"})
        d["Elementos"].append({"perfil": "ObsLibre", "ruta": "status", "min": "0", "max": "1"})
    esperar_error(tmp_path, c, "exige mínimo 1 en «Observation»")


def test_plantilla_con_listas_encadenadas(tmp_path):
    cat = CatalogIndex.from_file(CATALOGO) if CATALOGO.is_file() else None
    wb = crear_libro(copy.deepcopy(DATOS), cat)
    assert wb["Listas"].sheet_state == "hidden"
    nombres = set(wb.defined_names)
    assert {"padres_Patient", "rutas_Patient", "rutas_Observation", "padres_vacio"} <= nombres
    if cat:
        assert {"rutasp_CorePacienteCl", "rutasp_cl_core_signos_vitales"} <= nombres
    elems = wb["Elementos"]
    formulas = [dv.formula1 for dv in elems.data_validations.dataValidation]
    assert any(f.startswith("=INDIRECT(") for f in formulas)
    assert wb["Perfiles"].column_dimensions["H"].hidden and wb["Perfiles"].column_dimensions["I"].hidden   # auxiliares tras la columna Id
    assert elems.column_dimensions["J"].hidden        # columnas avanzadas (Solo tipo...) agrupadas y cerradas
    assert not elems.column_dimensions["H"].hidden    # Resumen y Definición quedan a la vista


def test_el_lector_sigue_leyendo_una_plantilla_con_listas_y_columnas_ocultas(tmp_path):
    cat = CatalogIndex.from_file(CATALOGO) if CATALOGO.is_file() else None
    ruta = guardar_plantilla(tmp_path / "l.xlsx", copy.deepcopy(DATOS), cat)
    libro = leer_libro(ruta)
    assert not hay_errores(revisar_libro(libro, cat))
    assert libro.filas("Elementos")[0]["perfil"] == "PacienteControl"


@pytest.mark.skipif(not __import__("shutil").which("soffice"), reason="falta LibreOffice")
@necesita_catalogo
def test_las_formulas_auxiliares_eligen_la_lista_correcta(tmp_path):
    import subprocess

    from openpyxl import load_workbook
    cat = CatalogIndex.from_file(CATALOGO)
    ruta = guardar_plantilla(tmp_path / "f.xlsx", copy.deepcopy(DATOS), cat)
    subprocess.run(["soffice", "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(tmp_path / "out"), str(ruta)],
                   check=True, capture_output=True, timeout=180)
    e = load_workbook(tmp_path / "out" / "f.xlsx", data_only=True)["Elementos"]
    from libro.esquema import HOJAS
    aux = len(next(h for h in HOJAS if h.nombre == "Elementos").columnas) + 1        # columna oculta con el nombre de la lista
    claves = {e.cell(r, 1).value: e.cell(r, aux).value for r in range(5, 16) if e.cell(r, 1).value}
    assert claves == {"PacienteControl": "rutasp_CorePacienteCl", "DoctorControl": "rutasp_CorePrestadorCl",
                      "FrecuenciaCardiacaControl": "rutasp_cl_core_signos_vitales"}


def test_plantilla_encadena_la_ruta_de_valores():
    wb = crear_libro(copy.deepcopy(DATOS), CatalogIndex.from_file(CATALOGO) if CATALOGO.is_file() else None)
    formulas = [dv.formula1 for dv in wb["Valores"].data_validations.dataValidation]
    assert any(f.startswith("=INDIRECT($I") for f in formulas)
    assert wb["Valores"]["H4"].value == "Tipo sugerido" and wb["Valores"].column_dimensions["I"].hidden
    assert "tipos_Patient" in set(wb.defined_names)


def test_el_tipo_de_dato_vacio_se_deduce_y_da_el_mismo_fsh():
    cat = CatalogIndex.from_file(CATALOGO) if CATALOGO.is_file() else None
    explicito = copy.deepcopy(DATOS)
    vacio = copy.deepcopy(DATOS)
    n = 0
    for f in vacio["Valores"]:
        if f["tipo"] in ("fecha", "texto", "cantidad", "código simple"):
            f["tipo"] = ""
            n += 1
    assert n
    outs = []
    for d in (explicito, vacio):
        wb = crear_libro(d)
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            libro = leer_libro(guardar_plantilla(Path(t) / "x.xlsx", d))
            av = revisar_libro(libro, cat)
            assert not hay_errores(av), texto_avisos(av)
            outs.append(construir_archivos(libro, cat)["input/fsh/ejemplos.fsh"])
    assert outs[0] == outs[1]


@pytest.mark.skipif(not __import__("shutil").which("soffice"), reason="falta LibreOffice")
@necesita_catalogo
def test_las_formulas_de_valores_dan_lista_y_tipo(tmp_path):
    import subprocess

    from openpyxl import load_workbook
    cat = CatalogIndex.from_file(CATALOGO)
    ruta = guardar_plantilla(tmp_path / "v.xlsx", copy.deepcopy(DATOS), cat)
    subprocess.run(["soffice", "--headless", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(tmp_path / "out"), str(ruta)],
                   check=True, capture_output=True, timeout=180)
    v = load_workbook(tmp_path / "out" / "v.xlsx", data_only=True)["Valores"]
    filas = [(v.cell(r, 1).value, v.cell(r, 2).value, v.cell(r, 8).value, v.cell(r, 9).value) for r in range(5, 40) if v.cell(r, 1).value]
    listas = {inst: lista for inst, _, _, lista in filas}
    assert listas["PacienteDemo"] == "rutasp_CorePacienteCl"
    assert listas["DoctorDemo"] == "rutasp_CorePrestadorCl"
    # los slices y las extensiones propias del libro no están en las listas del Excel: allí no hay tipo sugerido
    propio = ("telecom[", "extension[")
    esperado = [f["tipo"] for f in DATOS["Valores"] if not f["ruta"].startswith(propio)]
    assert [t for _, ruta, t, _ in filas if not ruta.startswith(propio)] == esperado


# ---------------------------------------------------------------- extensiones y slices
def _cat():
    return CatalogIndex.from_file(CATALOGO) if CATALOGO.is_file() else None


@pytest.mark.skipif(not CATALOGO.is_file(), reason="sin build/catalog: genera el catálogo con `python cl_ig.py catalogo`")
def test_el_demo_con_extensiones_y_slices_no_tiene_errores_ni_avisos(tmp_path):
    av = avisos_de(tmp_path, catalogo=_cat())
    assert not [a for a in av if a.nivel in ("error", "aviso")], mensajes(av)


def test_fsh_de_extensiones_slices_y_ejemplos(tmp_path):
    libro = libro_de(tmp_path)
    revisar_libro(libro, _cat())              # la revisión completa los tipos de dato vacíos
    a = construir_archivos(libro, _cat())
    ext, perf, ej = a["input/fsh/extensiones.fsh"], a["input/fsh/perfiles.fsh"], a["input/fsh/ejemplos.fsh"]
    assert "Extension: AniosEscolaridad" in ext and "Context: Patient" in ext and "* value[x] only integer" in ext
    assert "* extension contains medio 1..1 and horario 0..1" in ext and "* extension[medio].value[x] only code" in ext
    assert "* extension contains AniosEscolaridad named aniosEscolaridad 0..1 MS" in perf
    assert perf.index("extension contains AniosEscolaridad") < perf.index("telecom contains") < perf.index("* gender 1..1 MS")
    assert "* telecom ^slicing.discriminator[0].type = #value" in perf and '^slicing.discriminator[0].path = "system"' in perf
    assert "* telecom contains telefono 0..1 MS and correo 0..1" in perf and "* telecom[telefono].system = #phone" in perf
    assert "* extension[aniosEscolaridad].valueInteger = 12" in ej
    assert "* extension[contactoPreferido].extension[medio].valueCode = #phone" in ej
    assert "* telecom[telefono].value =" in ej
    borrador = construir_archivos(libro_de(tmp_path, lambda d: d.update({"Documentación": []})), _cat())["input/pagecontent/index.md"]
    assert "#### Extensiones" in borrador and "`AniosEscolaridad`" in borrador and "`Medio`" not in borrador


def test_extension_sin_tipo_ni_partes(tmp_path):
    esperar_error(tmp_path, lambda d: d["Extensiones"][0].update(tipo=""), "necesita «Tipo del valor»")


def test_extension_compleja_no_lleva_tipo(tmp_path):
    esperar_error(tmp_path, lambda d: d["Extensiones"][1].update(tipo="string"), "es una extensión compleja")


def test_parte_de_una_extension_inexistente(tmp_path):
    esperar_error(tmp_path, lambda d: d["Extensiones"][2].update(parte_de="ContactoPreferid"), "«ContactoPreferido»")


def test_extension_con_tipo_inexistente_y_contexto_con_errata(tmp_path):
    def c(d):
        d["Extensiones"][0].update(tipo="entero", contexto="Pacient")
    t = mensajes(avisos_de(tmp_path, c), "error")
    assert "«entero»" in t and "«Patient»" in t


def test_extension_sin_usar_en_ningun_perfil(tmp_path):
    def c(d):
        d["Elementos"] = [e for e in d["Elementos"] if e["ruta"] != "extension[aniosEscolaridad]"]
        d["Valores"] = [v for v in d["Valores"] if v["ruta"] != "extension[aniosEscolaridad]"]
    assert "Ningún perfil usa la extensión «AniosEscolaridad»" in mensajes(avisos_de(tmp_path, c), "aviso")


def test_ejemplo_con_extension_que_su_perfil_no_usa(tmp_path):
    def c(d):
        d["Elementos"] = [e for e in d["Elementos"] if e["ruta"] != "extension[aniosEscolaridad]"]
    esperar_error(tmp_path, c, "no usa la extensión «AniosEscolaridad»")


def test_ejemplo_con_extension_compleja_sin_parte(tmp_path):
    def c(d):
        d["Valores"].append({"instancia": "PacienteDemo", "ruta": "extension[contactoPreferido]", "valor": "x"})
    esperar_error(tmp_path, c, "es una extensión compleja")


def test_ejemplo_con_parte_desconocida(tmp_path):
    def c(d):
        d["Valores"][-1].update(ruta="extension[contactoPreferido].extension[hora]") if False else None
        d["Valores"].append({"instancia": "PacienteDemo", "ruta": "extension[contactoPreferido].extension[hora]", "valor": "x"})
    esperar_error(tmp_path, c, "no tiene la parte «hora»")


def test_tipo_incoherente_con_la_extension_da_aviso(tmp_path):
    def c(d):
        for v in d["Valores"]:
            if v["ruta"] == "extension[aniosEscolaridad]":
                v["tipo"] = "texto"
    assert "guarda un valor de tipo integer" in mensajes(avisos_de(tmp_path, c), "aviso")


def test_reglas_de_valor_en_la_fila_de_una_extension_de_elementos(tmp_path):
    def c(d):
        for e in d["Elementos"]:
            if e["ruta"] == "extension[aniosEscolaridad]":
                e["tipo"] = "integer"
    esperar_error(tmp_path, c, "se definen en la hoja Extensiones")


def test_slices_sin_discriminador(tmp_path):
    def c(d):
        d["Slices"][0].update(discriminador="", disc_ruta="")
    esperar_error(tmp_path, c, "No dijiste cómo se distinguen los slices de «telecom»")


def test_slice_con_valor_pero_sin_campo(tmp_path):
    def c(d):
        d["Slices"][0].update(disc_ruta="")
    t = mensajes(avisos_de(tmp_path, c), "error")
    assert "Falta el campo que distingue" in t and "en qué campo va" in t


def test_slice_repetido_y_discriminadores_contradictorios(tmp_path):
    def c(d):
        d["Slices"][1].update(slice="telefono", discriminador="pattern")
    t = mensajes(avisos_de(tmp_path, c), "error")
    assert "repetido" in t and "valores distintos" in t


def test_slice_que_ya_existe_en_clcore(tmp_path):
    if not _cat():
        pytest.skip("falta catálogo")
    def c(d):
        d["Slices"].append({"perfil": "DoctorControl", "elemento": "identifier", "slice": "run", "min": "0", "max": "1"})
    esperar_error(tmp_path, c, "ya existe en el padre", _cat())


def test_slice_nuevo_en_elemento_ya_dividido_no_pide_discriminador(tmp_path):
    if not _cat():
        pytest.skip("falta catálogo")
    def c(d):
        d["Slices"].append({"perfil": "DoctorControl", "elemento": "identifier", "slice": "licencia", "min": "0", "max": "1",
                            "disc_ruta": "system", "fijo": "http://example.org/licencia", "fijo_tipo": "texto"})
    av = avisos_de(tmp_path, c, _cat())
    assert not [a for a in av if a.nivel == "error"], mensajes(av)


def test_slice_sin_nada_que_lo_distinga(tmp_path):
    def c(d):
        d["Slices"][1].update(fijo="", fijo_tipo="")
    assert "no tiene qué lo distinga" in mensajes(avisos_de(tmp_path, c), "aviso")


def test_ejemplo_con_slice_que_el_perfil_no_define(tmp_path):
    def c(d):
        d["Valores"].append({"instancia": "PacienteDemo", "ruta": "telecom[fax].value", "tipo": "texto", "valor": "1"})
    assert "no define el slice «fax»" in mensajes(avisos_de(tmp_path, c), "aviso")


def test_slice_obligatorio_que_el_ejemplo_no_trae(tmp_path):
    def c(d):
        d["Slices"][0].update(min="1")
        d["Valores"] = [v for v in d["Valores"] if not v["ruta"].startswith("telecom")]
    assert "exige al menos un «telecom[telefono]»" in mensajes(avisos_de(tmp_path, c), "aviso")


def test_tipo_deducido_en_un_slice_propio(tmp_path):
    def c(d):
        for v in d["Valores"]:
            if v["ruta"] == "telecom[telefono].value":
                v["tipo"] = ""
    av = avisos_de(tmp_path, c, _cat())
    assert not [a for a in av if a.nivel == "error"], mensajes(av)


def test_plantilla_tiene_hoja_de_listas_para_slices_y_pista_de_extensiones():
    wb = crear_libro(copy.deepcopy(DATOS), _cat())
    assert any(dv.formula1.startswith("=INDIRECT(") for dv in wb["Slices"].data_validations.dataValidation)
    ws = wb["Extensiones"]
    col = len(HOJA_POR_NOMBRE["Extensiones"].columnas) + 1
    assert ws.cell(4, col).value == "Ruta para usarla" and str(ws.cell(5, col).value).startswith("=IF(")


def test_tipos_vacios_en_extensiones_dan_el_mismo_fsh(tmp_path):
    def vaciar(d):
        for v in d["Valores"]:
            if v["ruta"].startswith("extension["):
                v["tipo"] = ""
    a = libro_de(tmp_path)
    b = libro_de(tmp_path, vaciar)
    revisar_libro(a, _cat())
    av = revisar_libro(b, _cat())
    assert sum("deducido de la extensión" in x.mensaje for x in av) == 3
    assert construir_archivos(a, _cat())["input/fsh/ejemplos.fsh"] == construir_archivos(b, _cat())["input/fsh/ejemplos.fsh"]


# ---------------------------------------------------------------- tipos de valores fijos y «Solo tipo»
def test_valor_fijo_de_otro_tipo_que_el_elemento(tmp_path):
    def c(d):
        d["Elementos"].append({"perfil": "PacienteControl", "ruta": "birthDate", "fijo": "8867-4", "fijo_tipo": "código con sistema", "fijo_sistema": "LOINC"})
    esperar_error(tmp_path, c, "«birthDate» es de tipo date (fecha)", _cat())


def test_valor_fijo_en_un_elemento_que_agrupa_datos(tmp_path):
    def c(d):
        d["Elementos"].append({"perfil": "PacienteControl", "ruta": "identifier", "fijo": "http://unitsofmeasure.org", "fijo_tipo": "texto"})
    esperar_error(tmp_path, c, "agrupa varios datos (Identifier)", _cat())


def test_solo_tipo_que_el_elemento_no_admite(tmp_path):
    def c(d):
        d["Elementos"].append({"perfil": "PacienteControl", "ruta": "telecom.value", "tipo": "Quantity"})
    esperar_error(tmp_path, c, "no se puede restringir a «Quantity»", _cat())


def test_solo_tipo_valido_no_da_error(tmp_path):
    av = avisos_de(tmp_path, catalogo=_cat())      # el demo restringe value[x] a Quantity
    assert "restringir" not in mensajes(av)


@pytest.mark.skipif(not CATALOGO.is_file(), reason="sin build/catalog: genera el catálogo con `python cl_ig.py catalogo`")
def test_estructura_muestra_hijos_con_su_cardinalidad():
    from libro.estructura import estructura
    t = estructura("CorePacienteCl", _cat(), "telecom")
    assert "telecom" in t and "system" in t and "0..1" in t and "ContactPoint" in t
    assert "no es un elemento" in estructura("Patient", None, "inexistente")
    assert "No conozco" in estructura("Xyz")
    assert "birthDate" in estructura("Patient")


@pytest.mark.skipif(not CATALOGO.is_file(), reason="sin build/catalog: genera el catálogo con `python cl_ig.py catalogo`")
def test_la_solucion_del_ejercicio_1_no_tiene_errores_ni_avisos(tmp_path):
    import importlib.util
    ruta = Path(__file__).resolve().parent.parent / "examples" / "ejercicio-1-presion-arterial" / "datos.py"
    spec = importlib.util.spec_from_file_location("ejercicio1", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    libro = leer_libro(guardar_plantilla(tmp_path / "e1.xlsx", copy.deepcopy(mod.DATOS)))
    av = revisar_libro(libro, _cat())
    assert not [a for a in av if a.nivel in ("error", "aviso")], mensajes(av)
    a = construir_archivos(libro, _cat())
    assert "* component contains sistolica 1..1 MS and diastolica 1..1 MS" in a["input/fsh/perfiles.fsh"]


def _reconstruccion():
    import importlib.util
    ruta = Path(__file__).resolve().parent.parent / "examples" / "prueba-reconstruccion" / "datos.py"
    spec = importlib.util.spec_from_file_location("reconstruccion", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_perfil_sin_padre_y_sin_clcore_no_da_errores(tmp_path):
    """La reconstrucción de CorePacienteCl parte del Patient base, sin CL Core y sin catálogo."""
    libro = leer_libro(guardar_plantilla(tmp_path / "r.xlsx", copy.deepcopy(_reconstruccion().DATOS)))
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel in ("error", "aviso")], mensajes(av)
    fsh = construir_archivos(libro, None)["input/fsh/perfiles.fsh"]
    assert "Parent: Patient\n" in fsh
    assert "hl7.fhir.cl.clcore" not in construir_archivos(libro, None)["sushi-config.yaml"]


def test_extension_dentro_de_un_slice_se_declara_despues_del_slice(tmp_path):
    libro = leer_libro(guardar_plantilla(tmp_path / "r.xlsx", copy.deepcopy(_reconstruccion().DATOS)))
    fsh = construir_archivos(libro, None)["input/fsh/perfiles.fsh"]
    assert fsh.index("* name contains NombreOficial") < fsh.index("* name[NombreOficial].family.extension contains SegundoApellido")


def test_los_hijos_de_una_referencia_se_reconocen(tmp_path):
    libro = leer_libro(guardar_plantilla(tmp_path / "r.xlsx", copy.deepcopy(_reconstruccion().DATOS)))
    av = revisar_libro(libro, None)
    assert "generalPractitioner.reference" not in mensajes(av)


def test_textos_del_elemento_van_al_fsh(tmp_path):
    def c(d):
        d["Elementos"].append({"perfil": "PacienteControl", "ruta": "address", "resumen": "Dirección", "definicion": "Dónde vive.", "comentario": "Opcional."})
    fsh = construir_archivos(libro_de(tmp_path, c), _cat())["input/fsh/perfiles.fsh"]
    assert '* address ^short = "Dirección"' in fsh and '* address ^definition = "Dónde vive."' in fsh and '* address ^comment = "Opcional."' in fsh
    assert "* address  " not in fsh and "* address \n" not in fsh        # una fila de solo textos no deja una regla vacía


def test_texto_en_el_uso_de_una_extension(tmp_path):
    def c(d):
        fila(d, "Elementos", perfil="PacienteControl", ruta="extension[aniosEscolaridad]")["resumen"] = "Años de estudio"
    fsh = construir_archivos(libro_de(tmp_path, c), _cat())["input/fsh/perfiles.fsh"]
    assert '* extension[aniosEscolaridad] ^short = "Años de estudio"' in fsh


@necesita_catalogo
def test_perfil_del_tipo_y_destinos_de_referencia(tmp_path):
    def c(d):
        d["Elementos"] += [
            {"perfil": "PacienteControl", "ruta": "address", "perfil_tipo": "cl-address"},
            {"perfil": "PacienteControl", "ruta": "generalPractitioner", "destinos": "Practitioner, CorePrestadorCl"},
        ]
    libro = libro_de(tmp_path, c)
    av = revisar_libro(libro, _cat())
    assert not [a for a in av if a.nivel in ("error", "aviso")], mensajes(av)
    fsh = construir_archivos(libro, _cat())["input/fsh/perfiles.fsh"]
    assert "* address only https://hl7chile.cl/fhir/ig/clcore/StructureDefinition/cl-address" in fsh
    assert "* generalPractitioner only Reference(Practitioner or https://hl7chile.cl/fhir/ig/clcore/StructureDefinition/CorePrestadorCl)" in fsh


@necesita_catalogo
def test_destinos_y_perfil_del_tipo_mal_usados(tmp_path):
    def c1(d):
        d["Elementos"].append({"perfil": "PacienteControl", "ruta": "birthDate", "destinos": "Practitioner"})
    esperar_error(tmp_path, c1, "no es una referencia", _cat())

    def c2(d):
        d["Elementos"].append({"perfil": "PacienteControl", "ruta": "generalPractitioner", "destinos": "Practitionner"})
    esperar_error(tmp_path, c2, "¿Quisiste decir «Practitioner»?", _cat())

    def c3(d):
        d["Elementos"].append({"perfil": "PacienteControl", "ruta": "generalPractitioner", "perfil_tipo": "CorePrestadorCl"})
    esperar_error(tmp_path, c3, "usa «Puede apuntar a»", _cat())

    def c4(d):
        d["Elementos"].append({"perfil": "PacienteControl", "ruta": "address", "perfil_tipo": "CorePacienteCl"})
    esperar_error(tmp_path, c4, "es de tipo Patient", _cat())


def test_un_libro_antiguo_sin_las_columnas_nuevas_se_sigue_leyendo(tmp_path):
    ruta = guardar_plantilla(tmp_path / "viejo.xlsx", copy.deepcopy(DATOS))
    wb = load_workbook(ruta)
    ws = wb["Elementos"]
    for col in range(ws.max_column, 0, -1):          # quita las columnas agregadas después
        if ws.cell(4, col).value in ("Resumen", "Definición", "Comentario", "Debe seguir el perfil", "Puede apuntar a"):
            ws.delete_cols(col)
    wb.save(ruta)
    libro = leer_libro(ruta)
    assert libro.filas("Elementos")[0]["resumen"] == ""
    assert libro.filas("Elementos")[0]["perfil"]


def test_perfil_de_un_tipo_de_dato(tmp_path):
    libro = leer_libro(guardar_plantilla(tmp_path / "r.xlsx", copy.deepcopy(_reconstruccion().DATOS)))
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel in ("error", "aviso")], mensajes(av)
    fsh = construir_archivos(libro, None)["input/fsh/perfiles.fsh"]
    assert "Profile: DireccionCl\nParent: Address\n" in fsh
    assert "* address only DireccionCl" in fsh
    assert "* city.extension contains Comunas named comunas 1..1 MS" in fsh


def test_un_tipo_de_dato_no_puede_ser_un_ejemplo(tmp_path):
    def c(d):
        d["Perfiles"].append({"nombre": "DireccionPropia", "recurso": "Address", "descripcion": "x"})
        d["Instancias"].append({"nombre": "DirEjemplo", "perfil": "DireccionPropia", "descripcion": "x", "uso": "ejemplo"})
    esperar_error(tmp_path, c, "es un tipo de dato, no un recurso")


def test_recurso_que_no_es_ni_recurso_ni_tipo_de_dato(tmp_path):
    def c(d):
        d["Perfiles"].append({"nombre": "Mal", "recurso": "Adress", "descripcion": "x"})
    esperar_error(tmp_path, c, "ni un tipo de dato que se pueda perfilar")


def test_extension_ya_definida_en_otro_paquete(tmp_path):
    libro = leer_libro(guardar_plantilla(tmp_path / "r.xlsx", copy.deepcopy(_reconstruccion().DATOS)))
    archivos = construir_archivos(libro, None)
    assert "* extension contains http://hl7.org/fhir/StructureDefinition/geolocation named geolocalizacion 0..1 MS" in archivos["input/fsh/perfiles.fsh"]
    assert "Extension: Geolocalizacion" not in archivos["input/fsh/extensiones.fsh"]
    assert "Geolocalizacion" not in archivos["input/pagecontent/index.md"]


def test_url_de_extension_externa_mal_escrita(tmp_path):
    def c(d):
        d["Extensiones"].append({"nombre": "Externa", "url": "no-es-url"})
    esperar_error(tmp_path, c, "no es válida")


def test_estructura_de_un_tipo_de_dato():
    from libro.estructura import estructura
    assert "postalCode" in estructura("Address")


def test_pagina_de_requisitos_se_genera_y_va_despues_del_inicio(tmp_path):
    a = construir_archivos(libro_de(tmp_path), _cat())
    md = a["input/pagecontent/requisitos.md"]
    for perfil in ("pacientecontrol", "frecuenciacardiacacontrol", "doctorcontrol"):
        assert "{% include StructureDefinition-" + perfil + "-diff.xhtml %}" in md
    assert "CL Core 1.9.3" in md and "no obliga a informarlo" in md
    cfg = a["sushi-config.yaml"]
    assert cfg.index("index.md") < cfg.index("requisitos.md")
    assert "Requisitos: requisitos.html" in cfg and cfg.index("Inicio: index.html") < cfg.index("Requisitos: requisitos.html") < cfg.index("Artefactos:")


def test_el_borrador_del_inicio_enlaza_los_requisitos(tmp_path):
    libro = leer_libro(guardar_plantilla(tmp_path / "r.xlsx", copy.deepcopy(_reconstruccion().DATOS)))
    assert "requisitos.html" in construir_archivos(libro, None)["input/pagecontent/index.md"]


def test_requisitos_de_un_perfil_sin_padre_dice_que_no_hereda_de_cl_core(tmp_path):
    libro = leer_libro(guardar_plantilla(tmp_path / "r.xlsx", copy.deepcopy(_reconstruccion().DATOS)))
    md = construir_archivos(libro, None)["input/pagecontent/requisitos.md"]
    assert "no hereda nada de CL Core" in md


def test_la_pagina_de_requisitos_escrita_por_la_persona_tiene_prioridad(tmp_path):
    def c(d):
        d["Documentación"].append({"pagina": "requisitos", "titulo": "Mis requisitos", "texto": "Hola."})
    a = construir_archivos(libro_de(tmp_path, c), _cat())
    assert a["input/pagecontent/requisitos.md"].startswith("Hola.")


def test_codesystems_y_valuesets_llevan_experimental_y_case_sensitive(tmp_path):
    a = construir_archivos(libro_de(tmp_path), _cat())["input/fsh/terminologia.fsh"]
    assert "* ^experimental = true" in a and "* ^caseSensitive = true" in a

    def activa(d):
        d["Guía"]["estado"] = "active"
    b = construir_archivos(libro_de(tmp_path, activa), _cat())["input/fsh/terminologia.fsh"]
    assert "* ^experimental = false" in b and "experimental = true" not in b


@pytest.mark.skipif(not CATALOGO.is_file(), reason="sin build/catalog: genera el catálogo con `python cl_ig.py catalogo`")
def test_valueset_con_filtro_exclusion_y_otro_valueset(tmp_path):
    def c(d):
        d["ValueSets"].append({"nombre": "VSDiagnosticosDemo", "titulo": "Diagnósticos", "descripcion": "x"})
        d["Inclusiones"] += [
            {"valueset": "VSDiagnosticosDemo", "sistema": "SNOMED", "filtro": "descendent-of", "filtro_valor": "404684003"},
            {"valueset": "VSDiagnosticosDemo", "sistema": "SNOMED", "codigo": "160245001"},
            {"valueset": "VSDiagnosticosDemo", "sistema": "SNOMED", "modo": "excluir", "codigo": "22298006"},
            {"valueset": "VSDiagnosticosDemo", "sistema": "SNOMED", "modo": "excluir", "filtro": "regex", "filtro_valor": "^9"},
            {"valueset": "VSDiagnosticosDemo", "otro_valueset": "VSContextoMedicion"},
        ]
    libro = libro_de(tmp_path, c)
    av = revisar_libro(libro, _cat())
    assert not [a for a in av if a.nivel in ("error", "aviso")], mensajes(av)
    fsh = construir_archivos(libro, _cat())["input/fsh/terminologia.fsh"]
    assert "* include codes from system $SNOMED where concept descendent-of #404684003" in fsh
    assert "* $SNOMED#160245001" in fsh and "* exclude $SNOMED#22298006" in fsh
    assert '* exclude codes from system $SNOMED where concept regex "^9"' in fsh
    assert "* include codes from valueset VSContextoMedicion" in fsh


@pytest.mark.skipif(not CATALOGO.is_file(), reason="sin build/catalog: genera el catálogo con `python cl_ig.py catalogo`")
def test_filtros_de_valueset_mal_escritos(tmp_path):
    def sin_valor(d):
        d["Inclusiones"].append({"valueset": d["ValueSets"][0]["nombre"], "sistema": "SNOMED", "filtro": "is-a"})
    esperar_error(tmp_path, sin_valor, "necesita su «Valor del filtro»", _cat())

    def sin_sistema(d):
        d["Inclusiones"].append({"valueset": d["ValueSets"][0]["nombre"], "filtro": "is-a", "filtro_valor": "123"})
    esperar_error(tmp_path, sin_sistema, "necesita el sistema", _cat())

    def inexistente(d):
        d["Inclusiones"].append({"valueset": d["ValueSets"][0]["nombre"], "otro_valueset": "VSNoExiste"})
    esperar_error(tmp_path, inexistente, "no existe", _cat())

    def a_si_mismo(d):
        d["Inclusiones"].append({"valueset": d["ValueSets"][0]["nombre"], "otro_valueset": d["ValueSets"][0]["nombre"]})
    esperar_error(tmp_path, a_si_mismo, "no puede incluirse a sí mismo", _cat())

    def sin_nada(d):
        d["Inclusiones"].append({"valueset": d["ValueSets"][0]["nombre"]})
    esperar_error(tmp_path, sin_nada, "Falta el sistema", _cat())


def test_codigo_de_coding_sin_sistema_da_aviso(tmp_path):
    def c(d):
        d["Valores"].append({"instancia": "PacienteEjemplo" if any(i["nombre"] == "PacienteEjemplo" for i in d["Instancias"]) else d["Instancias"][0]["nombre"],
                             "ruta": "identifier[0].type.coding.code", "tipo": "código simple", "valor": "01"})
    av = avisos_de(tmp_path, c, _cat())
    assert "tiene código pero no sistema" in mensajes(av, "aviso")


def test_codigo_de_coding_con_sistema_no_da_aviso(tmp_path):
    def c(d):
        n = d["Instancias"][0]["nombre"]
        d["Valores"] += [{"instancia": n, "ruta": "identifier[0].type.coding.system", "tipo": "texto", "valor": "http://example.org/cs"},
                         {"instancia": n, "ruta": "identifier[0].type.coding.code", "tipo": "código simple", "valor": "01"}]
    assert "tiene código pero no sistema" not in mensajes(avisos_de(tmp_path, c, _cat()))


def test_construir_valida_una_vez_sin_modelo_ni_reparaciones(tmp_path, monkeypatch):
    from agents import run
    capturado = []
    monkeypatch.setattr(run, "main", lambda argv: capturado.append(argv) or 1)
    monkeypatch.setattr(cl_ig, "_ultimo_informe", lambda *a: None)
    monkeypatch.setattr(cl_ig, "_mostrar_resumen", lambda *a: None)
    libro = tmp_path / "demo.xlsx"
    assert cl_ig.main(["plantilla", str(libro), "--ejemplo"]) == 0
    assert cl_ig.main(["construir", str(libro), "--runs", str(tmp_path / "runs")]) == 1
    argv = capturado[0]
    assert "--sin-reparar" in argv and argv[argv.index("--timeout-min") + 1] == "60"


def test_un_libro_con_problemas_no_llama_al_modelo_ni_repite_la_validacion():
    from agents.loop import Outcome, run_loop
    from tests.test_catalog_precheck import mini_catalog
    from validator.parse_qa import Issue, QAReport

    llamadas = []

    def validar(files):
        llamadas.append(1)
        return Outcome(report=QAReport(issues=[Issue("error", "content", "falta description", "CodeSystem", "CSX", fingerprint="f1")]))

    class Reparador:
        def repair(self, *a, **k):
            raise AssertionError("un libro no debe llamar al modelo")

    r = run_loop({"a.fsh": "Profile: A\nParent: Patient\n"}, validar, Reparador(), mini_catalog(), reparar=False)
    assert r.status == "con_problemas" and len(llamadas) == 1 and len(r.problems) == 1


def test_el_informe_agrupa_los_problemas_repetidos():
    from agents.informe import informe_md
    pend = [{"source": "publisher", "message": f"CodeSystem/CS{i}: CodeSystem: falta description"} for i in range(5)] + \
           [{"source": "publisher", "message": "CapabilityStatement/x: La regla cpb-2 falló"}]
    texto = informe_md({"status": "con_problemas", "steps": [{"stage": "publisher", "problems": 6}], "pendientes": pend, "llm": {}})
    assert "**5 veces**" in texto and "CodeSystem/CS0" in texto and "cpb-2" in texto and "encontró errores" in texto


def test_la_falta_de_descripcion_se_revisa_segun_quien_publica(tmp_path):
    def datos(canonical):
        return {"Guía": {"id": "d", "titulo": "D", "canonical": canonical, "usa_clcore": "No"}, "Perfiles": [{"nombre": "PacX", "recurso": "Patient", "titulo": "P", "descripcion": "P"}],
                "CodeSystems": [{"nombre": "CSX", "titulo": "X"}], "Conceptos": [{"codigo": "a", "texto": "A", "codesystem": "CSX"}],
                "Capacidades": [{"nombre": "CapX", "titulo": "X", "modo": "server"}]}
    hl7 = revisar_libro(leer_libro(guardar_plantilla(tmp_path / "a.xlsx", datos("https://hl7chile.cl/fhir/ig/x"))))
    otra = revisar_libro(leer_libro(guardar_plantilla(tmp_path / "b.xlsx", datos("https://ejemplo.cl/ig"))))
    assert "«CSX» no tiene descripción" in mensajes(hl7, "error") and "ShareableValueSet" in mensajes(hl7, "error")
    assert "«CSX» no tiene descripción" in mensajes(otra, "aviso") and "«CSX» no tiene descripción" not in mensajes(otra, "error")
    assert "cpb-2" in mensajes(hl7, "error") and "cpb-2" in mensajes(otra, "error")


# ---------- Reglas sobre el valor de una extensión (hoja ValorExtensiones) ----------

def _rec_libro(tmp_path, cambio=None):
    datos = copy.deepcopy(_reconstruccion().DATOS)
    if cambio:
        cambio(datos)
    return leer_libro(guardar_plantilla(tmp_path / "v.xlsx", datos))


def test_valor_de_extension_genera_reglas_dentro_del_valor(tmp_path):
    libro = _rec_libro(tmp_path)
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel in ("error", "aviso")], mensajes(av)
    fsh = construir_archivos(libro, None)["input/fsh/extensiones.fsh"]
    assert "* extension[tutId].valueIdentifier.system 1.." in fsh
    assert "* extension[tutId].valueIdentifier.type.coding.code 1.." in fsh
    assert "* extension[docProc].valueCodeableConcept.coding 1..1" in fsh


def test_valor_de_extension_extension_inexistente(tmp_path):
    libro = _rec_libro(tmp_path, lambda d: d["ValorExtensiones"].append({"extension": "NoExiste", "ruta": "system", "min": "1"}))
    assert "NoExiste" in mensajes(revisar_libro(libro, None), "error")


def test_valor_de_extension_campo_inexistente(tmp_path):
    libro = _rec_libro(tmp_path, lambda d: d["ValorExtensiones"].append({"extension": "TutId", "ruta": "campoInventado", "min": "1"}))
    assert "campoInventado" in mensajes(revisar_libro(libro, None), "error")


def test_valor_de_extension_no_puede_ser_mas_laxa_que_el_tipo(tmp_path):
    libro = _rec_libro(tmp_path, lambda d: d["ValorExtensiones"].append({"extension": "TutId", "ruta": "system", "max": "5"}))
    assert "system" in mensajes(revisar_libro(libro, None), "error")


def test_valor_de_extension_compleja_pide_ir_a_las_partes(tmp_path):
    libro = _rec_libro(tmp_path, lambda d: d["ValorExtensiones"].append({"extension": "IdContacto", "ruta": "system", "min": "1"}))
    assert "compleja" in mensajes(revisar_libro(libro, None), "error")


# ---------- Importación de códigos desde CSV ----------

def test_importar_codigos_no_toca_el_original_y_no_duplica(tmp_path):
    from libro.importar import importar_codigos
    origen = guardar_plantilla(tmp_path / "o.xlsx", copy.deepcopy(_reconstruccion().DATOS))
    antes = origen.read_bytes()
    csv_ = tmp_path / "c.csv"
    csv_.write_text("codigo;glosa\nCL;Chile\nPE;Perú\n;sin código\nBR;Brasil\n", encoding="utf-8")
    destino = tmp_path / "n.xlsx"
    r = importar_codigos(origen, csv_, "CSPaises", destino)
    assert (r.nuevos, r.repetidos, len(r.omitidos)) == (2, 1, 1)
    assert origen.read_bytes() == antes
    codigos = {f["codigo"] for f in leer_libro(destino).hojas["Conceptos"] if f["codesystem"] == "CSPaises"}
    assert {"CL", "AR", "PE", "BR"} <= codigos


def test_importar_codigos_crea_el_codesystem_y_el_libro_sigue_valido(tmp_path):
    from libro.importar import importar_codigos
    origen = guardar_plantilla(tmp_path / "o.xlsx", copy.deepcopy(_reconstruccion().DATOS))
    csv_ = tmp_path / "c.csv"
    csv_.write_text("code,display\n1,Uno\n2,Dos\n", encoding="utf-8-sig")
    r = importar_codigos(origen, csv_, "CSNuevo", tmp_path / "n.xlsx")
    assert r.creado_codesystem and r.nuevos == 2
    assert not [a for a in revisar_libro(leer_libro(tmp_path / "n.xlsx"), None) if a.nivel == "error"]


def test_importar_codigos_sin_columnas_reconocibles_explica(tmp_path):
    import pytest
    from libro.importar import importar_codigos
    origen = guardar_plantilla(tmp_path / "o.xlsx", copy.deepcopy(_reconstruccion().DATOS))
    csv_ = tmp_path / "c.csv"
    csv_.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="col-codigo"):
        importar_codigos(origen, csv_, "CSX", tmp_path / "n.xlsx")


# ---------- CapabilityStatement (hojas Capacidades y RecursosCapacidad) ----------

def _con_capacidad(tmp_path, cambio=None):
    def c(d):
        d["Capacidades"] = [{"nombre": "ServidorX", "titulo": "Servidor X", "descripcion": "Qué ofrece.", "modo": "server", "formato": "json"}]
        d["RecursosCapacidad"] = [{"capacidad": "ServidorX", "recurso": "Patient", "perfil": "PacienteReconstruido",
                                   "interacciones": "read, search-type", "busquedas": "identifier:token"}]
        if cambio:
            cambio(d)
    return _rec_libro(tmp_path, c)


def test_capability_statement_se_genera_con_perfil_operaciones_y_busquedas(tmp_path):
    libro = _con_capacidad(tmp_path)
    assert not [a for a in revisar_libro(libro, None) if a.nivel in ("error", "aviso")]
    fsh = construir_archivos(libro, None)["input/fsh/capacidades.fsh"]
    assert "InstanceOf: CapabilityStatement" in fsh
    assert "* rest[0].mode = #server" in fsh
    assert "* rest[0].resource[0].supportedProfile[0] = Canonical(PacienteReconstruido)" in fsh
    assert "* rest[0].resource[0].interaction[1].code = #search-type" in fsh
    assert '* rest[0].resource[0].searchParam[0].name = "identifier"' in fsh
    assert "* date = " in fsh


def test_capability_statement_errores(tmp_path):
    casos = {
        "operación": ({"interacciones": "read, volar"}, "volar"),
        "búsqueda": ({"busquedas": "identifier"}, "parámetro:tipo"),
        "recurso": ({"recurso": "Pacient"}, "Patient"),
        "perfil": ({"perfil": "NoExiste"}, "NoExiste"),
    }
    for _, (cambio, esperado) in casos.items():
        libro = _con_capacidad(tmp_path, lambda d, c=cambio: d["RecursosCapacidad"][0].update(c))
        assert esperado in mensajes(revisar_libro(libro, None), "error")


def test_capability_statement_avisos_y_duplicados(tmp_path):
    libro = _con_capacidad(tmp_path, lambda d: d["RecursosCapacidad"][0].update({"interacciones": "read"}))
    assert "search-type" in mensajes(revisar_libro(libro, None), "aviso")
    libro = _con_capacidad(tmp_path, lambda d: d["RecursosCapacidad"].append(dict(d["RecursosCapacidad"][0])))
    assert "ya está" in mensajes(revisar_libro(libro, None), "error")
    libro = _con_capacidad(tmp_path, lambda d: d["Capacidades"].append({"nombre": "Vacia", "modo": "client"}))
    assert "no tiene recursos" in mensajes(revisar_libro(libro, None), "aviso")


def test_reconstruccion_trae_los_codigos_territoriales_y_los_enlaza(tmp_path):
    libro = leer_libro(guardar_plantilla(tmp_path / "r.xlsx", copy.deepcopy(_reconstruccion().DATOS)))
    por_sistema = {}
    for c in libro.hojas["Conceptos"]:
        por_sistema.setdefault(c["codesystem"], []).append(c["codigo"])
    assert (len(por_sistema["CSRegiones"]), len(por_sistema["CSProvincias"]), len(por_sistema["CSComunas"])) == (16, 56, 346)
    assert "16101" in por_sistema["CSComunas"] and "058" in por_sistema["CSProvincias"] and "01" in por_sistema["CSRegiones"]
    assert not [a for a in revisar_libro(libro, None) if a.nivel in ("error", "aviso")]
    ext = construir_archivos(libro, None)["input/fsh/extensiones.fsh"]
    assert "* value[x] from VSComunas (required)" in ext


def test_codesystems_y_valuesets_declaran_idioma(tmp_path):
    libro = _rec_libro(tmp_path)
    t = construir_archivos(libro, None)["input/fsh/terminologia.fsh"]
    assert "CodeSystem: CSComunas" in t and "* ^language = #es" in t
    assert t.count("* ^language = #es") == t.count("CodeSystem: ") + t.count("ValueSet: ")
    libro = _rec_libro(tmp_path, lambda d: d["Guía"].update({"idioma": "en"}))
    assert "* ^language = #en" in construir_archivos(libro, None)["input/fsh/terminologia.fsh"]
    libro = _rec_libro(tmp_path, lambda d: d["Guía"].update({"idioma": "español!"}))
    assert "idioma" in mensajes(revisar_libro(libro, None), "error")


# ---------- CapabilityStatement completo: expectativas, operaciones del servidor, importación desde JSON ----------

_EXP = "http://hl7.org/fhir/StructureDefinition/capabilitystatement-expectation"


def _e(valor):
    return {"extension": [{"url": _EXP, "valueCode": valor}]}


def _cs_json():
    return {"resourceType": "CapabilityStatement", "title": "T", "format": ["json", "application/fhir+json"], "patchFormat": ["application/json-patch+json"],
            "rest": [{"mode": "server", "documentation": "Texto ajeno", "interaction": [{**_e("MAY"), "code": "transaction"}],
                      "resource": [{**_e("SHALL"), "type": "Patient", "supportedProfile": ["https://x.cl/StructureDefinition/PacienteX"],
                                    "_supportedProfile": [_e("SHALL")], "referencePolicy": ["literal", "logical"], "_referencePolicy": [_e("SHOULD"), _e("MAY")],
                                    "searchInclude": ["*", None, "Patient:link"], "_searchInclude": [_e("SHALL"), _e("MAY"), _e("SHOULD")],
                                    "interaction": [{**_e("SHALL"), "code": "read"}, {**_e("MAY"), "code": "search-type"}],
                                    "searchParam": [{**_e("SHALL"), "name": "identifier", "definition": "http://hl7.org/fhir/SearchParameter/Patient-identifier",
                                                     "type": "token", "documentation": "Texto ajeno"}]}]}]}


def test_capability_statement_se_importa_desde_json_y_se_reproduce_sin_diferencias(tmp_path):
    from libro.importar import aplanar_capacidad_fsh, aplanar_capacidad_json, capacidad_desde_json
    cs = _cs_json()
    filas = capacidad_desde_json(cs, "ServidorX", perfiles_propios={"PacienteX"})
    assert all("ajeno" not in str(v) for hoja in filas.values() for f in hoja for v in f.values())      # no copia textos
    datos = {"Guía": {"id": "cap-x", "titulo": "Cap X", "canonical": "https://x.cl/ig", "usa_clcore": "No"},
             "Perfiles": [{"nombre": "PacienteX", "recurso": "Patient", "titulo": "P", "descripcion": "P"}], **filas}
    libro = leer_libro(guardar_plantilla(tmp_path / "c.xlsx", datos))
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel == "error"], mensajes(av)
    fsh = construir_archivos(libro, None)["input/fsh/capacidades.fsh"]
    real, mio = aplanar_capacidad_json(cs), aplanar_capacidad_fsh(fsh)
    assert real.pop("rest.resource[0].supportedProfile[0]").endswith("/PacienteX") and mio.pop("rest.resource[0].supportedProfile[0]") == "Canonical(PacienteX)"
    assert real == mio                       # el perfil propio se escribe por nombre; el resto es idéntico
    assert "* patchFormat[0] = #\"application/json-patch+json\"" in fsh
    assert "* rest[0].interaction[0].code = #transaction" in fsh


def test_operaciones_y_busquedas_validan_recurso_y_expectativa(tmp_path):
    def mal(d):
        d["OperacionesCapacidad"] = [{"capacidad": "ServidorX", "recurso": "Patient", "operacion": "transaction", "expectativa": "SHALL"},
                                     {"capacidad": "ServidorX", "recurso": "Observation", "operacion": "read", "expectativa": "SHALL"},
                                     {"capacidad": "ServidorX", "recurso": "Patient", "operacion": "read", "expectativa": "QUIZAS"}]
        d["BusquedasCapacidad"] = [{"capacidad": "ServidorX", "recurso": "Patient", "parametro": "x", "tipo": "numero"}]
    m = mensajes(revisar_libro(_con_capacidad(tmp_path, mal), None), "error")
    assert "transaction" in m and "Observation" in m and "QUIZAS" in m and "numero" in m


# ---------- Importador de paquetes ----------

def _paquete_sintetico(carpeta):
    import json
    base = "https://x.cl/ig"
    sds = {
        "StructureDefinition-MedX.json": {
            "resourceType": "StructureDefinition", "id": "medx", "url": f"{base}/StructureDefinition/medx", "name": "MedX", "title": "Med X",
            "kind": "resource", "type": "Medication", "derivation": "constraint", "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Medication",
            "differential": {"element": [
                {"id": "Medication", "path": "Medication"},
                {"id": "Medication.ingredient.item[x]", "path": "Medication.ingredient.item[x]",
                 "slicing": {"discriminator": [{"type": "type", "path": "$this"}], "rules": "open"}},
                {"id": "Medication.ingredient.item[x]:itemCodeableConcept", "path": "Medication.ingredient.item[x]", "sliceName": "itemCodeableConcept",
                 "min": 0, "max": "1", "type": [{"code": "CodeableConcept"}]},
            ]}},
        "StructureDefinition-ExtX.json": {
            "resourceType": "StructureDefinition", "id": "extx", "url": f"{base}/StructureDefinition/extx", "name": "ExtX", "title": "Ext X",
            "kind": "complex-type", "type": "Extension", "derivation": "constraint", "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Extension",
            "context": [{"type": "element", "expression": "Patient"}],
            "differential": {"element": [
                {"id": "Extension", "path": "Extension"},
                {"id": "Extension.value[x]", "path": "Extension.value[x]", "min": 1, "mustSupport": True, "type": [{"code": "string"}]},
            ]}},
    }
    for n, d in sds.items():
        (carpeta / n).write_text(json.dumps(d), encoding="utf-8")


def test_importar_paquete_slices_de_tipo_variable_y_valor_de_extension(tmp_path):
    from libro.importar_paquete import importar_paquete
    carpeta = tmp_path / "pq"
    carpeta.mkdir()
    _paquete_sintetico(carpeta)
    datos, inf = importar_paquete(carpeta, canonical="https://x.cl/ig", id_guia="x", titulo="X")
    assert not inf.no_soportado
    libro = leer_libro(guardar_plantilla(tmp_path / "i.xlsx", datos))
    assert not [a for a in revisar_libro(libro, None) if a.nivel == "error"]
    archivos = construir_archivos(libro, None)
    fsh = "\n".join(archivos.values())
    assert "ingredient.item[x] contains itemCodeableConcept 0..1" in fsh
    assert "* value[x] 1..1 MS" in fsh or "* value[x] 1.. MS" in fsh


def test_importar_paquete_bundle_con_perfiles_y_valores_fijos_de_concepto(tmp_path):
    import json
    from libro.importar_paquete import importar_paquete
    base = "https://x.cl/ig"
    carpeta = tmp_path / "pq2"
    carpeta.mkdir()

    def sd(nombre, tipo, elementos):
        d = {"resourceType": "StructureDefinition", "id": nombre.lower(), "url": f"{base}/StructureDefinition/{nombre}", "name": nombre,
             "kind": "resource", "type": tipo, "derivation": "constraint", "baseDefinition": f"http://hl7.org/fhir/StructureDefinition/{tipo}",
             "differential": {"element": [{"id": tipo, "path": tipo}] + elementos}}
        (carpeta / f"StructureDefinition-{nombre}.json").write_text(json.dumps(d), encoding="utf-8")
    sd("PacA", "Patient", [])
    sd("PacB", "Patient", [])
    sd("Obs", "Observation", [
        {"id": "Observation.code", "path": "Observation.code", "patternCodeableConcept": {"coding": [{"system": "http://x.cl/cs", "code": "01", "display": "Uno"}]}}])
    sd("Mensaje", "Bundle", [
        {"id": "Bundle.type", "path": "Bundle.type", "fixedCode": "searchset"},
        {"id": "Bundle.entry", "path": "Bundle.entry", "slicing": {"discriminator": [{"type": "profile", "path": "resource"}], "rules": "open"}},
        {"id": "Bundle.entry:pac", "path": "Bundle.entry", "sliceName": "pac", "min": 0, "max": "*"},
        {"id": "Bundle.entry:pac.resource", "path": "Bundle.entry.resource",
         "type": [{"code": "Patient", "profile": [f"{base}/StructureDefinition/PacA", f"{base}/StructureDefinition/PacB"]}]}])
    datos, inf = importar_paquete(carpeta, canonical=base, id_guia="x", titulo="X")
    libro = leer_libro(guardar_plantilla(tmp_path / "i2.xlsx", datos))
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel == "error"], mensajes(av)
    fsh = "\n".join(construir_archivos(libro, None).values())
    assert "entry[pac].resource only PacA or PacB" in fsh
    assert '* type = #searchset (exactly)' in fsh
    assert any(l.startswith('* code = ') and '#01 "Uno"' in l for l in fsh.splitlines())
    assert "^slicing.discriminator[0].type = #profile" in fsh


# ---------- SearchParameter, ConceptMap, OperationDefinition y terminología fina ----------

def _libro_nuevos(tmp_path, **hojas):
    datos = {"Guía": {"id": "nuevos", "titulo": "Nuevos", "canonical": "https://x.cl/ig", "usa_clcore": "No"},
             "Perfiles": [{"nombre": "PacX", "recurso": "Patient", "titulo": "P", "descripcion": "P"}],
             "CodeSystems": [{"nombre": "CSOrigen", "titulo": "O", "descripcion": "O", "distingue_mayusculas": "No"},
                             {"nombre": "CSDestino", "titulo": "D", "descripcion": "D"}],
             "Conceptos": [{"codigo": "01", "texto": "Uno", "codesystem": "CSOrigen"}, {"codigo": "S", "texto": "Soltero", "codesystem": "CSDestino"}],
             "ValueSets": [{"nombre": "VSOrigen", "titulo": "VO", "descripcion": "VO"}],
             "Inclusiones": [{"valueset": "VSOrigen", "sistema": "CSOrigen", "codigo": "01", "texto": "Uno visible"},
                             {"valueset": "VSOrigen", "sistema": "urn:iso:std:iso:3166", "filtro": "regex", "filtro_valor": "[0-9]{3}", "filtro_propiedad": "code"}]}
    datos.update(hojas)
    return leer_libro(guardar_plantilla(tmp_path / "n.xlsx", datos))


def test_busqueda_mapa_y_operacion_generan_fsh_y_pasan_la_revision(tmp_path):
    libro = _libro_nuevos(
        tmp_path,
        ParametrosBusqueda=[{"nombre": "PacSegundoApellido", "codigo": "segundo-apellido", "recursos": "Patient", "tipo": "string",
                             "expresion": "Patient.name.family", "titulo": "Segundo apellido", "descripcion": "Busca por segundo apellido", "modificadores": "exact", "multiple_o": "Sí"}],
        MapasConceptos=[{"nombre": "MapaX", "titulo": "Mapa", "descripcion": "Mapa", "origen": "VSOrigen", "destino": "http://hl7.org/fhir/ValueSet/marital-status"}],
        ReglasMapa=[{"mapa": "MapaX", "sistema_origen": "CSOrigen", "sistema_destino": "CSDestino", "codigo_origen": "01", "codigo_destino": "S",
                     "equivalencia": "equivalent", "version_destino": "3.0.0"}],
        Operaciones=[{"nombre": "BuscarX", "codigo": "match", "recursos": "Patient", "nivel": "tipo", "titulo": "Buscar", "descripcion": "Busca coincidencias"}],
        ParametrosOperacion=[{"operacion": "BuscarX", "parametro": "resource", "uso": "in", "min": "1", "max": "1", "tipo": "Patient", "perfil": "PacX"},
                             {"operacion": "BuscarX", "parametro": "return", "uso": "out", "min": "1", "max": "1", "tipo": "Bundle"}],
        Capacidades=[{"nombre": "ServX", "titulo": "S", "descripcion": "S", "modo": "server"}],
        RecursosCapacidad=[{"capacidad": "ServX", "recurso": "Patient", "perfil": "PacX SHALL, http://x.cl/otro", "interacciones": "read"}],
        OperacionesCapacidad=[{"capacidad": "ServX", "recurso": "Patient", "operacion": "match", "expectativa": "SHALL", "definicion": "BuscarX"}])
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel == "error"], mensajes(av)
    arch = construir_archivos(libro, None)
    assert "InstanceOf: SearchParameter" in arch["input/fsh/busquedas.fsh"] and "* code = #segundo-apellido" in arch["input/fsh/busquedas.fsh"]
    mapas = arch["input/fsh/mapas.fsh"]
    assert "* group[0].element[0].target[0].code = #S" in mapas and '* group[0].targetVersion = "3.0.0"' in mapas
    assert "* sourceCanonical = Canonical(VSOrigen)" in mapas
    ops = arch["input/fsh/operaciones.fsh"]
    assert "InstanceOf: OperationDefinition" in ops and "* parameter[0].targetProfile[0] = Canonical(PacX)" in ops and "* type = true" in ops
    cap = arch["input/fsh/capacidades.fsh"]
    assert "supportedProfile[1]" in cap and "operation[0].definition = Canonical(BuscarX)" in cap
    term = arch["input/fsh/terminologia.fsh"]
    assert "* ^caseSensitive = false" in term and 'where code regex' in term and '#01 "Uno visible"' in term


def test_busqueda_mapa_y_operacion_errores(tmp_path):
    libro = _libro_nuevos(
        tmp_path,
        ParametrosBusqueda=[{"nombre": "Mal", "codigo": "con espacio", "recursos": "Paciente", "tipo": "otro", "modificadores": "raro"}],
        MapasConceptos=[{"nombre": "MapaX", "origen": "NoExiste"}],
        ReglasMapa=[{"mapa": "MapaX", "sistema_origen": "CSOrigen", "sistema_destino": "CSDestino", "codigo_origen": "99", "codigo_destino": "", "equivalencia": "equivalent"}],
        Operaciones=[{"nombre": "OpX", "codigo": "$match", "nivel": "global"}],
        ParametrosOperacion=[{"operacion": "OpX", "parametro": "p", "uso": "entrada", "min": "2", "max": "1"}])
    texto = mensajes(revisar_libro(libro, None))
    for esperado in ("con espacio", "Paciente", "«otro»", "raro", "NoExiste", "«99»", "no código de destino", "$match", "global", "entrada", "mayor que el máximo"):
        assert esperado in texto, (esperado, texto)


def test_cuestionario_genera_fsh_anidado_y_pasa_la_revision(tmp_path):
    libro = _libro_nuevos(
        tmp_path,
        Cuestionarios=[{"nombre": "MotivoX", "titulo": "Motivo", "descripcion": "Motivo de derivación", "recursos": "Patient"}],
        PreguntasCuestionario=[
            {"cuestionario": "MotivoX", "id": "g1", "tipo": "group", "texto": "Datos"},
            {"cuestionario": "MotivoX", "id": "tipo", "dentro_de": "g1", "tipo": "choice", "texto": "Tipo", "obligatoria": "Sí", "opciones": "VSOrigen"},
            {"cuestionario": "MotivoX", "id": "otro", "dentro_de": "g1", "tipo": "string", "texto": "Detalle", "largo_maximo": "50",
             "si_pregunta": "tipo", "si_operador": "=", "si_respuesta": "CSOrigen#01"},
            {"cuestionario": "MotivoX", "id": "ges", "tipo": "boolean", "texto": "¿GES?", "repite": "No"},
            {"cuestionario": "MotivoX", "id": "det", "tipo": "string", "texto": "Detalle GES", "si_pregunta": "ges", "si_operador": "=", "si_respuesta": "Sí"}])
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel == "error"], mensajes(av)
    f = construir_archivos(libro, None)["input/fsh/cuestionarios.fsh"]
    assert "InstanceOf: Questionnaire" in f and "* subjectType[0] = #Patient" in f
    assert '* item[0].item[1].linkId = "otro"' in f
    assert "* item[0].item[0].answerValueSet = Canonical(VSOrigen)" in f
    assert "* item[0].item[1].enableWhen[0].answerCoding = CSOrigen#01" in f
    assert "* item[2].enableWhen[0].answerBoolean = true" in f and "* item[0].item[0].required = true" in f


def test_cuestionario_errores(tmp_path):
    libro = _libro_nuevos(
        tmp_path,
        Cuestionarios=[{"nombre": "Q", "titulo": "Q", "descripcion": "Q"}],
        PreguntasCuestionario=[
            {"cuestionario": "Q", "id": "a", "tipo": "string", "texto": "A", "opciones": "VSOrigen"},
            {"cuestionario": "Q", "id": "b", "tipo": "raro", "texto": "B"},
            {"cuestionario": "Q", "id": "a", "tipo": "string", "texto": "repetida"},
            {"cuestionario": "Q", "id": "c", "dentro_de": "a", "tipo": "string", "texto": "C", "si_pregunta": "zz", "si_operador": "=", "si_respuesta": "x"},
            {"cuestionario": "Q", "id": "d", "dentro_de": "nada", "tipo": "integer", "texto": "D", "largo_maximo": "5"},
            {"cuestionario": "Otro", "id": "e", "tipo": "string"}])
    texto = mensajes(revisar_libro(libro, None))
    for esperado in ("tiene opciones pero es de tipo", "ya se usó", "«raro»", "no es de tipo group", "zz", "nada", "Largo máximo", "«Otro»"):
        assert esperado in texto, (esperado, texto)


def test_importar_cuestionario_desde_json(tmp_path):
    import json
    from libro.importar_paquete import importar_paquete
    carpeta = tmp_path / "pkg"
    carpeta.mkdir()
    q = {"resourceType": "Questionnaire", "id": "q1", "url": "https://x.cl/Questionnaire/q1", "name": "QUno", "title": "Uno", "status": "draft",
         "subjectType": ["Patient"],
         "item": [{"linkId": "g", "type": "group", "text": "G", "item": [
             {"linkId": "a", "type": "boolean", "text": "A", "required": True},
             {"linkId": "b", "type": "string", "text": "B", "maxLength": 20,
              "enableWhen": [{"question": "a", "operator": "=", "answerBoolean": True}]}]}]}
    (carpeta / "Questionnaire-q1.json").write_text(json.dumps(q), encoding="utf-8")
    datos, inf = importar_paquete(carpeta)
    assert datos["Cuestionarios"][0]["nombre"] == "QUno"
    pregs = {p["id"]: p for p in datos["PreguntasCuestionario"]}
    assert pregs["a"]["dentro_de"] == "g" and pregs["a"]["obligatoria"] == "Sí"
    assert pregs["b"]["si_pregunta"] == "a" and pregs["b"]["si_respuesta"] == "Sí" and pregs["b"]["largo_maximo"] == "20"
    assert "Questionnaire" not in str(inf.no_soportado)


def _libro_mensaje(tmp_path, entradas, slices, valores=()):
    datos = {"Guía": {"id": "msg", "titulo": "Msg", "canonical": "https://x.cl/ig", "usa_clcore": "No"},
             "Perfiles": [{"nombre": "PacLE", "recurso": "Patient", "titulo": "P", "descripcion": "P"},
                          {"nombre": "CabLE", "recurso": "MessageHeader", "titulo": "C", "descripcion": "C"},
                          {"nombre": "BunLE", "recurso": "Bundle", "titulo": "B", "descripcion": "B"}],
             "Elementos": [{"perfil": "BunLE", "ruta": "type", "min": "1", "max": "1", "fijo_tipo": "código simple", "fijo": "message"}] + entradas,
             "Slices": slices,
             "Instancias": [{"nombre": "EjPac", "perfil": "PacLE", "uso": "ejemplo"}, {"nombre": "EjMsg", "perfil": "BunLE", "uso": "ejemplo"}],
             "Valores": list(valores)}
    return leer_libro(guardar_plantilla(tmp_path / "m.xlsx", datos))


def _entrada(slice_, perfil, min_="1", max_="1"):
    return ({"perfil": "BunLE", "ruta": f"entry[{slice_}].resource", "min": "1", "max": "1", "perfil_tipo": perfil},
            {"perfil": "BunLE", "elemento": "entry", "slice": slice_, "min": min_, "max": max_, "discriminador": "profile", "disc_ruta": "resource"})


def test_mensaje_correcto_con_recurso_incluido(tmp_path):
    (e1, s1), (e2, s2) = _entrada("cabecera", "CabLE"), _entrada("paciente", "PacLE")
    libro = _libro_mensaje(tmp_path, [e1, e2], [s1, s2],
                           [{"instancia": "EjMsg", "ruta": "entry[cabecera].resource", "tipo": "recurso incluido", "valor": "EjPac"}])
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel == "error"], mensajes(av)
    assert "MessageHeader" not in mensajes([a for a in av if "primera" in a.mensaje or "ninguna entrada" in a.mensaje])
    assert "* entry[cabecera].resource = EjPac" in construir_archivos(libro, None)["input/fsh/ejemplos.fsh"]


def test_mensaje_sin_cabecera_o_cabecera_no_primera(tmp_path):
    e2, s2 = _entrada("paciente", "PacLE")
    texto = mensajes(revisar_libro(_libro_mensaje(tmp_path, [e2], [s2]), None))
    assert "ninguna entrada es un MessageHeader" in texto
    (e1, s1), (e2, s2) = _entrada("cabecera", "CabLE", "0", "2"), _entrada("paciente", "PacLE")
    texto = mensajes(revisar_libro(_libro_mensaje(tmp_path, [e2, e1], [s2, s1]), None))
    assert "no está primera" in texto and "obligatorio" in texto and "máximo 1" in texto
    # sin orden en el perfil es solo una sugerencia; con orden obligatorio es un aviso
    av = revisar_libro(_libro_mensaje(tmp_path, [e2, e1], [s2, s1]), None)
    assert [a.nivel for a in av if "no está primera" in a.mensaje] == ["sugerencia"]
    s2["ordenado"] = "Sí"
    av = revisar_libro(_libro_mensaje(tmp_path, [e2, e1], [s2, s1]), None)
    assert [a.nivel for a in av if "no está primera" in a.mensaje] == ["aviso"]


def test_recurso_incluido_inexistente(tmp_path):
    (e1, s1) = _entrada("cabecera", "CabLE")
    libro = _libro_mensaje(tmp_path, [e1], [s1], [{"instancia": "EjMsg", "ruta": "entry[cabecera].resource", "tipo": "recurso incluido", "valor": "NoExiste"}])
    assert "El recurso incluido «NoExiste»" in mensajes(revisar_libro(libro, None))


def test_invariantes_fsh_y_revision(tmp_path):
    libro = _libro_nuevos(
        tmp_path,
        Invariantes=[{"clave": "x-1", "perfil": "PacX", "ruta": "", "gravedad": "error", "descripcion": "Debe tener nombre", "expresion": "name.exists()"},
                     {"clave": "x-2", "perfil": "PacX", "ruta": "name", "gravedad": "warning", "descripcion": "Con apellido", "expresion": "family.exists()"},
                     {"clave": "x-2", "perfil": "PacX", "ruta": "contact.name", "gravedad": "warning", "descripcion": "Con apellido", "expresion": "family.exists()"}])
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel == "error"], mensajes(av)
    f = construir_archivos(libro, None)["input/fsh/perfiles.fsh"]
    assert "* obeys x-1" in f and "* name obeys x-2" in f and "* contact.name obeys x-2" in f
    assert f.count("Invariant: x-2") == 1 and 'Expression: "family.exists()"' in f and "Severity: #warning" in f


def test_invariantes_errores(tmp_path):
    libro = _libro_nuevos(
        tmp_path,
        Invariantes=[{"clave": "x 1", "perfil": "Nada", "gravedad": "grave", "descripcion": "", "expresion": "name.exists("},
                     {"clave": "ok-1", "perfil": "PacX", "gravedad": "error", "descripcion": "A", "expresion": "a"},
                     {"clave": "ok-1", "perfil": "PacX", "ruta": "name", "gravedad": "error", "descripcion": "B", "expresion": "a"}])
    texto = mensajes(revisar_libro(libro, None))
    for esperado in ("«x 1» no es válida", "«Nada»", "«grave»", "Falta qué exige", "sin cerrar", "ya está definida distinto"):
        assert esperado in texto, (esperado, texto)


def test_importar_invariantes(tmp_path):
    import json
    from libro.importar_paquete import importar_paquete
    carpeta = tmp_path / "pkg"
    carpeta.mkdir()
    sd = {"resourceType": "StructureDefinition", "id": "pac", "url": "https://x.cl/StructureDefinition/pac", "name": "PacI", "status": "draft", "kind": "resource",
          "abstract": False, "type": "Patient", "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Patient", "derivation": "constraint",
          "differential": {"element": [
              {"id": "Patient", "path": "Patient", "constraint": [{"key": "p-1", "severity": "error", "human": "Nombre", "expression": "name.exists()", "source": "https://x.cl/StructureDefinition/pac"}]},
              {"id": "Patient.name", "path": "Patient.name", "constraint": [{"key": "p-2", "severity": "warning", "human": "Ap", "expression": "family.exists()"},
                                                                         {"key": "ele-1", "severity": "error", "human": "h", "expression": "x", "source": "http://hl7.org/fhir/StructureDefinition/Element"}]}]}}
    (carpeta / "StructureDefinition-pac.json").write_text(json.dumps(sd), encoding="utf-8")
    datos, _ = importar_paquete(carpeta)
    inv = {i["clave"]: i for i in datos["Invariantes"]}
    assert set(inv) == {"p-1", "p-2"} and inv["p-1"]["ruta"] == "" and inv["p-2"]["ruta"] == "name" and inv["p-2"]["gravedad"] == "warning"


def test_invariante_en_extension(tmp_path):
    import json
    from libro.importar_paquete import importar_paquete
    libro = _libro_nuevos(
        tmp_path,
        Extensiones=[{"nombre": "ExtX", "titulo": "X", "descripcion": "X", "contexto": "Patient", "tipo": "string"}],
        Invariantes=[{"clave": "ex-1", "perfil": "ExtX", "ruta": "", "gravedad": "error", "descripcion": "Con valor", "expresion": "value.exists()"}])
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel == "error"], mensajes(av)
    assert "* obeys ex-1" in construir_archivos(libro, None)["input/fsh/extensiones.fsh"]
    carpeta = tmp_path / "pkg"
    carpeta.mkdir()
    sd = {"resourceType": "StructureDefinition", "id": "ex", "url": "https://x.cl/StructureDefinition/ex", "name": "ExI", "status": "draft", "kind": "complex-type",
          "abstract": False, "type": "Extension", "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Extension", "derivation": "constraint",
          "context": [{"type": "element", "expression": "Patient"}],
          "differential": {"element": [{"id": "Extension", "path": "Extension", "constraint": [{"key": "ex-9", "severity": "error", "human": "h", "expression": "value.exists()"}]},
                                       {"id": "Extension.value[x]", "path": "Extension.value[x]", "type": [{"code": "string"}]}]}}
    (carpeta / "StructureDefinition-ex.json").write_text(json.dumps(sd), encoding="utf-8")
    datos, _ = importar_paquete(carpeta)
    assert [(i["clave"], i["perfil"], i["ruta"]) for i in datos["Invariantes"]] == [("ex-9", "ExI", "")]


def test_id_explicito_en_perfiles_terminologia_y_definiciones(tmp_path):
    libro = _libro_nuevos(
        tmp_path,
        MapasConceptos=[{"nombre": "MapaX", "titulo": "M", "descripcion": "M", "id": "MapaId"}],
        ParametrosBusqueda=[{"nombre": "BusX", "codigo": "x", "recursos": "Patient", "tipo": "string", "descripcion": "d", "id": "bus-id"}])
    # el id explícito en los artefactos del libro base
    libro.hojas["Perfiles"][0]["id"] = "PacienteX"
    libro.hojas["CodeSystems"][0]["id"] = "CSOrigenId"
    libro.hojas["ValueSets"][0]["id"] = "VSOrigenId"
    av = revisar_libro(libro, None)
    assert not [a for a in av if a.nivel == "error"], mensajes(av)
    arch = construir_archivos(libro, None)
    assert "Id: PacienteX" in arch["input/fsh/perfiles.fsh"]
    term = arch["input/fsh/terminologia.fsh"]
    assert "Id: CSOrigenId" in term and "Id: VSOrigenId" in term and "Id: csdestino" in term
    assert '* id = "MapaId"' in arch["input/fsh/mapas.fsh"] and '* id = "bus-id"' in arch["input/fsh/busquedas.fsh"]


def test_id_repetido_o_invalido(tmp_path):
    libro = _libro_nuevos(tmp_path)
    libro.hojas["CodeSystems"][0]["id"] = "igual"
    libro.hojas["CodeSystems"][1]["id"] = "igual"
    libro.hojas["Perfiles"][0]["id"] = "con espacio"
    texto = mensajes(revisar_libro(libro, None))
    assert "ya lo usa" in texto and "«con espacio» no es válido" in texto


def test_importar_conserva_el_id_original(tmp_path):
    import json
    from libro.importar_paquete import importar_paquete
    carpeta = tmp_path / "pkg"
    carpeta.mkdir()
    cs = {"resourceType": "CodeSystem", "id": "CSMiSistema", "url": "https://x.cl/CodeSystem/CSMiSistema", "name": "CSMiSistema", "status": "draft", "content": "complete",
          "concept": [{"code": "a", "display": "A"}]}
    (carpeta / "CodeSystem-CSMiSistema.json").write_text(json.dumps(cs), encoding="utf-8")
    datos, _ = importar_paquete(carpeta)
    assert datos["CodeSystems"][0]["id"] == "CSMiSistema"


def test_codigo_de_parte_con_mayuscula_va_al_fsh(tmp_path):
    def c(d):
        for f in d["Extensiones"]:
            if f.get("parte_de") == "ContactoPreferido" and f["nombre"] == "Medio":
                f["codigo_parte"] = "Medio"
    libro = libro_de(tmp_path, c)
    revisar_libro(libro, _cat())
    ext = construir_archivos(libro, _cat())["input/fsh/extensiones.fsh"]
    assert "Medio 1..1" in ext and "* extension[Medio].value[x] only code" in ext


def test_orden_de_slices_y_slice_por_tipo_en_event_x(tmp_path):
    (e1, s1), (e2, s2) = _entrada("cabecera", "CabLE"), _entrada("paciente", "PacLE")
    s1["ordenado"] = "No"
    e3 = {"perfil": "CabLE", "ruta": "event[x][eventCoding]", "min": "1", "max": "1", "ms": "Sí"}
    s3 = {"perfil": "CabLE", "elemento": "event[x]", "slice": "eventCoding", "min": "1", "max": "1", "ms": "Sí",
          "discriminador": "type", "disc_ruta": "$this", "reglas": "closed", "ordenado": "Sí"}
    libro = _libro_mensaje(tmp_path, [e1, e2, e3], [s1, s2, s3])
    assert not [a for a in revisar_libro(libro, None) if a.nivel == "error"]
    fsh = construir_archivos(libro, None)["input/fsh/perfiles.fsh"]
    assert "* entry ^slicing.ordered = false" in fsh and "* event[x] ^slicing.ordered = true" in fsh
    assert "* event[x] contains eventCoding 1..1 MS" in fsh and "* event[x] ^slicing.discriminator[0].type = #type" in fsh


def test_must_support_en_la_url_de_extensiones(tmp_path):
    def c(d):
        d["ValorExtensiones"] = d.get("ValorExtensiones", []) + [
            {"extension": "AniosEscolaridad", "ruta": "url", "ms": "Sí"},
            {"extension": "ContactoPreferido", "ruta": "url", "ms": "Sí"},
            {"extension": "Medio", "ruta": "url", "ms": "Sí"}]
    libro = libro_de(tmp_path, c)
    av = revisar_libro(libro, _cat())
    assert not [a for a in av if a.nivel == "error"], mensajes(av)
    ext = construir_archivos(libro, _cat())["input/fsh/extensiones.fsh"]
    assert ext.count("url MS") == 3 and "* extension[medio].url MS" in ext
    assert "En «url» solo se puede marcar Must Support" in mensajes(avisos_de(tmp_path, lambda d: d.update(
        {"ValorExtensiones": [{"extension": "AniosEscolaridad", "ruta": "url", "min": "1"}]}), _cat()))


def test_importar_url_ms_y_orden_de_slices(tmp_path):
    import json
    from libro.importar_paquete import importar_paquete
    carpeta = tmp_path / "pkg"
    carpeta.mkdir()
    base = {"resourceType": "StructureDefinition", "status": "draft", "abstract": False, "derivation": "constraint"}
    ext = {**base, "id": "ex", "url": "https://x.cl/StructureDefinition/ex", "name": "ExI", "kind": "complex-type", "type": "Extension",
           "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Extension", "context": [{"type": "element", "expression": "Patient"}],
           "differential": {"element": [{"id": "Extension", "path": "Extension"}, {"id": "Extension.url", "path": "Extension.url", "mustSupport": True},
                                        {"id": "Extension.value[x]", "path": "Extension.value[x]", "type": [{"code": "string"}]}]}}
    bun = {**base, "id": "bun", "url": "https://x.cl/StructureDefinition/bun", "name": "BunI", "kind": "resource", "type": "Bundle",
           "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Bundle",
           "differential": {"element": [
               {"id": "Bundle.entry", "path": "Bundle.entry", "slicing": {"discriminator": [{"type": "profile", "path": "resource"}], "ordered": False, "rules": "closed"}},
               {"id": "Bundle.entry:a", "path": "Bundle.entry", "sliceName": "a", "min": 1, "max": "1"},
               {"id": "Bundle.entry:b", "path": "Bundle.entry", "sliceName": "b", "min": 0, "max": "1"}]}}
    (carpeta / "StructureDefinition-ex.json").write_text(json.dumps(ext), encoding="utf-8")
    (carpeta / "StructureDefinition-bun.json").write_text(json.dumps(bun), encoding="utf-8")
    datos, _ = importar_paquete(carpeta)
    assert {"extension": "ExI", "ruta": "url", "ms": "Sí"} in datos["ValorExtensiones"]
    assert [x["ordenado"] for x in datos["Slices"]] == ["No", ""]


def test_comando_importar_convierte_un_paquete_tgz_en_libro(tmp_path, capsys):
    import json
    import tarfile
    import cl_ig
    sd = {"resourceType": "StructureDefinition", "id": "pac", "url": "https://x.cl/StructureDefinition/pac", "name": "PacI", "status": "draft", "kind": "resource",
          "abstract": False, "type": "Patient", "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Patient", "derivation": "constraint",
          "differential": {"element": [{"id": "Patient.gender", "path": "Patient.gender", "min": 1, "mustSupport": True}]}}
    pkg = tmp_path / "package"
    pkg.mkdir()
    (pkg / "StructureDefinition-pac.json").write_text(json.dumps(sd), encoding="utf-8")
    (pkg / "package.json").write_text(json.dumps({"name": "x.cl", "canonical": "https://x.cl", "title": "Guía X"}), encoding="utf-8")
    tgz = tmp_path / "x.tgz"
    with tarfile.open(tgz, "w:gz") as tf:
        tf.add(pkg, arcname="package")
    salida = tmp_path / "libro.xlsx"
    assert cl_ig.main(["importar", str(tgz), "--salida", str(salida)]) == 0
    assert salida.exists() and "1 perfiles" in capsys.readouterr().out
    libro = leer_libro(salida)
    assert [f["nombre"] for f in libro.filas("Perfiles")] == ["PacI"]
    assert cl_ig.main(["importar", str(tgz), "--salida", str(salida)]) == 2          # no pisa sin --forzar
    assert cl_ig.main(["importar", str(tmp_path / "no-existe")]) == 2


# ---------------------------------------------------------------- páginas, menú, Must Support, cambios, imágenes
def _libro_paginas(tmp_path, **hojas):
    datos = {"Guía": {"id": "pag", "titulo": "Páginas", "canonical": "https://x.cl/ig", "usa_clcore": "No"},
             "Perfiles": [{"nombre": "PacX", "recurso": "Patient", "titulo": "Paciente X", "descripcion": "P"}],
             "Elementos": [{"perfil": "PacX", "ruta": "gender", "min": "1", "max": "1", "ms": "Sí", "resumen": "Sexo administrativo"},
                           {"perfil": "PacX", "ruta": "birthDate", "min": "0", "max": "1"}],
             "Capacidades": [{"nombre": "CapServidor", "titulo": "Servidor", "descripcion": "S", "modo": "server", "id": "cap-servidor"}]}
    datos.update(hojas)
    return leer_libro(guardar_plantilla(tmp_path / "p.xlsx", datos))


def _sushi(libro):
    return construir_archivos(libro, None)["sushi-config.yaml"]


def test_sin_hoja_menu_el_menu_es_el_de_siempre(tmp_path):
    libro = _libro_paginas(tmp_path)
    cfg = _sushi(libro)
    assert "Inicio: index.html" in cfg and "Requisitos: requisitos.html" in cfg and "Artefactos: artifacts.html" in cfg


def test_el_menu_con_desplegable_enlaces_y_paginas_generadas(tmp_path):
    libro = _libro_paginas(
        tmp_path,
        Documentación=[{"pagina": "inicio", "titulo": "Inicio", "texto": "Hola"}, {"pagina": "objetivos", "titulo": "Objetivos", "texto": "Para qué sirve"}],
        Menú=[{"etiqueta": "FHIR", "destino": "https://hl7.org/fhir/R4"}, {"etiqueta": "Inicio", "destino": "inicio"},
              {"etiqueta": "Objetivos", "destino": "objetivos"}, {"etiqueta": "Must Support", "destino": "must-support"},
              {"etiqueta": "Declaraciones", "destino": ""}, {"etiqueta": "Servidor", "destino": "CapServidor", "padre": "Declaraciones"},
              {"etiqueta": "Artefactos", "destino": "artefactos"}, {"etiqueta": "Historial de cambios", "destino": "cambios"}],
        Cambios=[{"version": "0.2.0", "fecha": "2026-10-21", "cambios": "Se agregó | algo\nen dos líneas"}])
    avisos = revisar_libro(libro)
    assert not hay_errores(avisos), mensajes(avisos, "error")
    archivos = construir_archivos(libro, None)
    cfg = archivos["sushi-config.yaml"]
    assert cfg.index("FHIR: https://hl7.org/fhir/R4") < cfg.index("Inicio: index.html") < cfg.index("Objetivos: objetivos.html")
    assert '"Must Support": must-support.html' in cfg and "Declaraciones:" in cfg and "Servidor: CapabilityStatement-cap-servidor.html" in cfg
    assert '"Historial de cambios": cambios.html' in cfg
    ms = archivos["input/pagecontent/must-support.md"]
    assert "| `gender` | Sexo administrativo |" in ms and "birthDate" not in ms and "StructureDefinition-pacx.html" in ms
    cambios = archivos["input/pagecontent/cambios.md"]
    assert "| 0.2.0 | 2026-10-21 | Se agregó \\| algo<br/>en dos líneas |" in cambios


def test_paginas_anidadas_y_texto_desde_archivo(tmp_path):
    (tmp_path / "paginas").mkdir()
    (tmp_path / "paginas" / "objetivos.md").write_text("# Objetivos\n\nTexto largo.\n", encoding="utf-8")
    libro = _libro_paginas(
        tmp_path,
        Documentación=[{"pagina": "inicio", "titulo": "Inicio", "texto": "Hola"},
                       {"pagina": "generalidades", "titulo": "Generalidades", "texto": "G"},
                       {"pagina": "objetivos", "titulo": "Objetivos", "texto": "@paginas/objetivos.md", "padre": "generalidades"}])
    assert not hay_errores(revisar_libro(libro))
    archivos = construir_archivos(libro, None)
    assert archivos["input/pagecontent/objetivos.md"].startswith("# Objetivos")
    cfg = archivos["sushi-config.yaml"]
    assert cfg.index("generalidades.md:") < cfg.index("objetivos.md:") and "      title: Objetivos" in cfg


@pytest.mark.parametrize("texto,esperado", [("@paginas/falta.md", "No encuentro el archivo"), ("@../secreto.md", "dentro de la carpeta «paginas»"),
                                            ("@paginas/x.txt", "terminar en .md")])
def test_el_texto_desde_archivo_se_revisa(tmp_path, texto, esperado):
    (tmp_path / "paginas").mkdir()
    (tmp_path / "paginas" / "x.txt").write_text("x", encoding="utf-8")
    (tmp_path.parent / "secreto.md").write_text("no debe leerse", encoding="utf-8")
    libro = _libro_paginas(tmp_path, Documentación=[{"pagina": "inicio", "titulo": "Inicio", "texto": texto}])
    assert esperado in mensajes(revisar_libro(libro), "error")


def test_el_menu_y_las_paginas_padre_se_revisan(tmp_path):
    libro = _libro_paginas(
        tmp_path,
        Documentación=[{"pagina": "a", "titulo": "A", "texto": "x", "padre": "b"}, {"pagina": "b", "titulo": "B", "texto": "x", "padre": "a"},
                       {"pagina": "c", "titulo": "C", "texto": "x", "padre": "no-existe"}],
        Menú=[{"etiqueta": "Uno", "destino": "no-existe"}, {"etiqueta": "Uno", "destino": "a"}, {"etiqueta": "Vacío", "destino": ""},
              {"etiqueta": "Dentro", "destino": "a", "padre": "Uno"}, {"etiqueta": "Cambios", "destino": "cambios"}])
    texto = mensajes(revisar_libro(libro), "error")
    for frase in ("forman un círculo", "no existe en esta hoja", "el destino «no-existe» no existe", "está repetido", "no lleva a ninguna parte",
                  "no es un desplegable", "necesita filas en la hoja Cambios"):
        assert frase in texto, frase


def test_las_imagenes_de_la_carpeta_imagenes_se_copian(tmp_path, capsys):
    from libro.fsh import construir_binarios
    (tmp_path / "imagenes").mkdir()
    (tmp_path / "imagenes" / "logo.png").write_bytes(b"\x89PNG")
    (tmp_path / "imagenes" / "notas.txt").write_text("no", encoding="utf-8")
    libro = _libro_paginas(tmp_path)
    assert construir_binarios(libro) == {"input/images/logo.png": b"\x89PNG"}
    assert cl_ig.main(["construir", str(tmp_path / "p.xlsx"), "--sin-docker", "--runs", str(tmp_path / "runs")]) == 0
    assert list((tmp_path / "runs").glob("*/input/images/logo.png"))


def test_importar_paquete_trae_los_ejemplos_con_id_y_extension(tmp_path):
    import json
    from decimal import Decimal
    from libro.importar_paquete import importar_paquete
    carpeta = tmp_path / "pq"
    (carpeta / "example").mkdir(parents=True)
    _paquete_sintetico(carpeta)
    base = "https://x.cl/ig"
    ejemplo = {"resourceType": "Medication", "id": "med-uno", "meta": {"profile": [f"{base}/StructureDefinition/medx"]},
               "text": {"status": "generated", "div": "<div/>"},
               "code": {"coding": [{"system": "http://loinc.org", "code": "1234-5", "display": "Algo"}]},
               "amount": {"numerator": {"value": 5.50, "unit": "mg", "system": "http://unitsofmeasure.org", "code": "mg"}},
               "extension": [{"url": f"{base}/StructureDefinition/extx", "valueString": "hola"}]}
    (carpeta / "example" / "Medication-med-uno.json").write_text(json.dumps(ejemplo), encoding="utf-8")
    datos, inf = importar_paquete(carpeta, canonical=base, id_guia="x", titulo="X")
    assert len(datos["Instancias"]) == 1 and datos["Instancias"][0]["id"] == "med-uno"
    rutas = {v["ruta"]: v for v in datos["Valores"]}
    assert rutas["code.coding[0]"]["tipo"] == "código con sistema"
    assert any(r.endswith(".valueString") and "extx" in r.lower() or "ExtX" in r for r in rutas)
    libro = leer_libro(guardar_plantilla(tmp_path / "i.xlsx", datos))
    assert not [a for a in revisar_libro(libro, None) if a.nivel == "error"]
    assert rutas["code.coding[0]"]["texto"] == ""      # LOINC: el publicador compara el texto con el oficial, así que no se arrastra
    fsh = "\n".join(construir_archivos(libro, None).values())
    assert '* id = "med-uno"' in fsh and "5.5 'mg'" in fsh


def test_ejemplo_de_signos_vitales_usa_el_slice_vscat_y_no_arrastra_textos_de_loinc():
    from libro.importar_ejemplos import ejemplos_desde_json
    from libro.importar_paquete import Informe
    url = "https://x.cl/ig/StructureDefinition/sv"
    r = {"resourceType": "Observation", "id": "sv1", "meta": {"profile": [url]},
         "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs"}]}],
         "code": {"coding": [{"system": "http://loinc.org", "code": "2708-6", "display": "texto largo"}]},
         "language": "es-CL"}
    _, vals = ejemplos_desde_json([r], lambda u: "SV" if u == url else u, lambda c, i, u: "Sv1", set(), Informe(), signos_vitales={url})
    rutas = {v["ruta"]: v for v in vals}
    assert "category[VSCat].coding[0]" in rutas and "category[0].coding[0]" not in rutas
    assert rutas["code.coding[0]"]["texto"] == ""
