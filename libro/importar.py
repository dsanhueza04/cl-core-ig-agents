"""Importa códigos desde un CSV a la hoja Conceptos de un libro, sin tocar el original.

El libro se lee completo y se vuelve a escribir en un archivo NUEVO (con sus listas desplegables al día).
Los códigos que ya existen en ese CodeSystem no se duplican: si el texto cambia, se informa y se conserva el del libro.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from libro.lector import leer_libro

_COD = ("codigo", "código", "code", "id")
_TXT = ("texto", "display", "nombre", "name", "glosa", "descripcion", "descripción", "term")
_DEF = ("definicion", "definición", "definition", "detalle")


@dataclass
class Resultado:
    nuevos: int = 0
    repetidos: int = 0
    distintos: list[str] = field(default_factory=list)   # códigos ya existentes con otro texto
    omitidos: list[str] = field(default_factory=list)    # filas del CSV sin código o sin texto
    creado_codesystem: bool = False


def _leer_csv(ruta: Path) -> list[dict]:
    crudo = ruta.read_bytes()
    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")          # exportaciones de Excel en Windows
    try:
        dialecto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t|")
    except csv.Error:
        dialecto = csv.excel
    return list(csv.DictReader(io.StringIO(texto), dialect=dialecto))


def _columna(encabezados: list[str], pedida: str | None, candidatas: tuple[str, ...]) -> str | None:
    if pedida:
        for h in encabezados:
            if h.strip().lower() == pedida.strip().lower():
                return h
        raise ValueError(f"El CSV no tiene la columna «{pedida}». Columnas: {', '.join(encabezados)}.")
    for c in candidatas:
        for h in encabezados:
            if h.strip().lower() == c:
                return h
    return None


def importar_codigos(libro_xlsx: str | Path, csv_ruta: str | Path, codesystem: str, destino: str | Path, *,
                     col_codigo: str | None = None, col_texto: str | None = None, col_definicion: str | None = None,
                     titulo: str = "", descripcion: str = "") -> Resultado:
    from libro.plantilla import guardar_plantilla
    libro = leer_libro(libro_xlsx)
    filas_csv = _leer_csv(Path(csv_ruta))
    if not filas_csv:
        raise ValueError("El CSV no tiene filas.")
    enc = list(filas_csv[0].keys())
    c_cod, c_txt, c_def = _columna(enc, col_codigo, _COD), _columna(enc, col_texto, _TXT), _columna(enc, col_definicion, _DEF)
    if not c_cod or not c_txt:
        raise ValueError(f"No encuentro las columnas de código y texto en el CSV (columnas: {', '.join(enc)}). "
                         "Indícalas con --col-codigo y --col-texto.")
    datos = {"Guía": dict(libro.guia)}
    for hoja, filas in libro.hojas.items():
        datos[hoja] = [{k: v for k, v in f.items() if not k.startswith("_")} for f in filas]
    res = Resultado()
    sistemas = datos.setdefault("CodeSystems", [])
    if not any(s.get("nombre") == codesystem for s in sistemas):
        sistemas.append({"nombre": codesystem, "titulo": titulo or codesystem, "descripcion": descripcion or f"Códigos importados desde {Path(csv_ruta).name}."})
        res.creado_codesystem = True
    conceptos = datos.setdefault("Conceptos", [])
    existentes = {c["codigo"]: c for c in conceptos if c.get("codesystem") == codesystem}
    for i, f in enumerate(filas_csv, start=2):
        cod, txt = (f.get(c_cod) or "").strip(), (f.get(c_txt) or "").strip()
        if not cod or not txt:
            res.omitidos.append(f"fila {i} del CSV")
            continue
        if cod in existentes:
            res.repetidos += 1
            if existentes[cod].get("texto") != txt:
                res.distintos.append(f"{cod}: el libro dice «{existentes[cod].get('texto')}», el CSV «{txt}»")
            continue
        nuevo = {"codesystem": codesystem, "codigo": cod, "texto": txt, "definicion": (f.get(c_def) or "").strip() if c_def else ""}
        conceptos.append(nuevo)
        existentes[cod] = nuevo
        res.nuevos += 1
    from cl_ig import _cargar_catalogo
    guardar_plantilla(destino, datos, _cargar_catalogo())
    return res


# ---------------------------------------------------------------------------------------------------------------------
# Importar un CapabilityStatement (JSON) a las hojas de capacidades
# ---------------------------------------------------------------------------------------------------------------------
URL_EXPECTATIVA = "http://hl7.org/fhir/StructureDefinition/capabilitystatement-expectation"


def _expectativa(obj: dict | None) -> str:
    for e in (obj or {}).get("extension", []):
        if e.get("url") == URL_EXPECTATIVA:
            return e.get("valueCode", "")
    return ""


def _valores_con_expectativa(r: dict, clave: str) -> list[str]:
    """['a','b'] + _clave con expectativas -> ['a SHALL', 'b']."""
    exps = r.get("_" + clave, [])
    out = []
    for i, v in enumerate(r.get(clave, [])):
        if v is None:                       # hueco de FHIR JSON: el valor falta y solo trae extensiones
            continue
        e = _expectativa(exps[i]) if i < len(exps) else ""
        out.append(f"{v} {e}" if e else str(v))
    return out


def _def_op(url: str, propios: set[str]) -> str:
    """Definición de una operación propia: nombre del libro si termina en uno de los artefactos importados, si no la URL."""
    return url


def capacidad_desde_json(cs: dict, nombre: str, *, con_textos: bool = False, perfiles_propios: set[str] | None = None) -> dict[str, list[dict]]:
    """Convierte un CapabilityStatement en filas de las hojas Capacidades, RecursosCapacidad, OperacionesCapacidad y BusquedasCapacidad.

    `con_textos=False` omite los textos explicativos (documentación, derechos de autor) para no copiar texto ajeno;
    `perfiles_propios` son nombres de perfiles del libro: si un perfil de la declaración termina en uno de ellos se usa el nombre, si no la URL.
    """
    propios = perfiles_propios or set()
    rest = (cs.get("rest") or [{}])[0]
    cap = {"nombre": nombre, "titulo": cs.get("title", "") if con_textos else nombre, "descripcion": cs.get("description", "") if con_textos else "Declaración de capacidades importada de un paquete.",
           "modo": rest.get("mode", "server"), "formato": ", ".join(cs.get("format", [])), "formato_parche": ", ".join(cs.get("patchFormat", [])),
           "documentacion": rest.get("documentation", "") if con_textos else "", "derechos": cs.get("copyright", "") if con_textos else ""}
    recursos, operaciones, busquedas = [], [], []
    for o in rest.get("operation", []):
        operaciones.append({"capacidad": nombre, "recurso": "", "operacion": o["name"], "expectativa": _expectativa(o), "definicion": _def_op(o.get("definition", ""), propios)})
    for i in rest.get("interaction", []):
        operaciones.append({"capacidad": nombre, "recurso": "", "operacion": i["code"], "expectativa": _expectativa(i)})
    for r in rest.get("resource", []):
        t = r["type"]
        sp = r.get("supportedProfile") or ([r["profile"]] if r.get("profile") else [])
        esperadas = [_expectativa(x) for x in (r.get("_supportedProfile") or [])] + [""] * len(sp)
        esperadas = esperadas[:len(sp)]
        comun = esperadas[0] if esperadas and len(set(esperadas)) == 1 else ""
        items = []
        for url, exp in zip(sp, esperadas):
            corto = url.rsplit("/", 1)[-1]
            nom = corto if corto in propios else url
            items.append(nom + (f" {exp}" if exp and not comun else ""))
        perfil, perfil_exp = ", ".join(items), comun
        recursos.append({"capacidad": nombre, "recurso": t, "expectativa": _expectativa(r), "perfil": perfil, "perfil_expectativa": perfil_exp,
                         "referencias": ", ".join(_valores_con_expectativa(r, "referencePolicy")), "incluir": ", ".join(_valores_con_expectativa(r, "searchInclude")),
                         "incluir_inverso": ", ".join(_valores_con_expectativa(r, "searchRevInclude")), "documentacion": r.get("documentation", "") if con_textos else ""})
        for i in r.get("interaction", []):
            operaciones.append({"capacidad": nombre, "recurso": t, "operacion": i["code"], "expectativa": _expectativa(i)})
        for o in r.get("operation", []):
            operaciones.append({"capacidad": nombre, "recurso": t, "operacion": o["name"], "expectativa": _expectativa(o), "definicion": _def_op(o.get("definition", ""), propios)})
        for b in r.get("searchParam", []):
            busquedas.append({"capacidad": nombre, "recurso": t, "parametro": b["name"], "tipo": b["type"], "expectativa": _expectativa(b),
                              "definicion": b.get("definition", ""), "documentacion": b.get("documentation", "") if con_textos else ""})
    return {"Capacidades": [cap], "RecursosCapacidad": recursos, "OperacionesCapacidad": operaciones, "BusquedasCapacidad": busquedas}


def aplanar_capacidad_json(cs: dict) -> dict[str, str]:
    """Reglas {ruta normalizada: valor} de un CapabilityStatement, sin textos explicativos (para comparar con el FSH generado)."""
    out: dict[str, str] = {}
    for k in ("format", "patchFormat"):
        for i, v in enumerate(cs.get(k, [])):
            out[f"{k}[{i}]"] = v
    rest = (cs.get("rest") or [{}])[0]
    out["rest.mode"] = rest.get("mode", "")
    for j, it in enumerate(rest.get("interaction", [])):
        out[f"rest.interaction[{j}].code"] = it["code"]
        if _expectativa(it):
            out[f"rest.interaction[{j}].expectation"] = _expectativa(it)
    for i, r in enumerate(rest.get("resource", [])):
        b = f"rest.resource[{i}]"
        out[f"{b}.type"] = r["type"]
        if _expectativa(r):
            out[f"{b}.expectation"] = _expectativa(r)
        for j, v in enumerate(r.get("supportedProfile", [])):
            out[f"{b}.supportedProfile[{j}]"] = v
            if j == 0 and r.get("_supportedProfile") and _expectativa(r["_supportedProfile"][0]):
                out[f"{b}.supportedProfile[0].expectation"] = _expectativa(r["_supportedProfile"][0])
        for k in ("searchInclude", "searchRevInclude", "referencePolicy"):
            exps = r.get("_" + k, [])
            j = 0
            for i0, v in enumerate(r.get(k, [])):
                if v is None:
                    continue
                out[f"{b}.{k}[{j}]"] = v
                if i0 < len(exps) and _expectativa(exps[i0]):
                    out[f"{b}.{k}[{j}].expectation"] = _expectativa(exps[i0])
                j += 1
        for j, it in enumerate(r.get("interaction", [])):
            out[f"{b}.interaction[{j}].code"] = it["code"]
            if _expectativa(it):
                out[f"{b}.interaction[{j}].expectation"] = _expectativa(it)
        for j, sp in enumerate(r.get("searchParam", [])):
            p = f"{b}.searchParam[{j}]"
            out[f"{p}.name"], out[f"{p}.type"] = sp["name"], sp["type"]
            if sp.get("definition"):
                out[f"{p}.definition"] = sp["definition"]
            if _expectativa(sp):
                out[f"{p}.expectation"] = _expectativa(sp)
    return out


def aplanar_capacidad_fsh(fsh: str) -> dict[str, str]:
    """Lo mismo, leído del FSH generado por la herramienta (`* ruta = valor`)."""
    import re
    out: dict[str, str] = {}
    for linea in fsh.splitlines():
        m = re.match(r"^\* (rest\[0\]\.|format|patchFormat)(.*?) = (.+)$", linea)
        if not m:
            continue
        ruta = (m.group(1) + m.group(2)).replace("rest[0]", "rest")
        ruta = ruta.replace(f"extension[{URL_EXPECTATIVA}].valueCode", "expectation")
        valor = m.group(3).strip()
        if ruta.endswith((".documentation", "copyright")) or ruta in ("description",):
            continue
        if valor.startswith("#"):
            valor = valor[1:].strip('"')
        elif valor.startswith("Canonical(") or valor.startswith('"'):
            valor = valor.strip('"')
        out[ruta] = valor
    return out
