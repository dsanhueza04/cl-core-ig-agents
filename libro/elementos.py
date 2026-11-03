"""Rutas de elementos de FHIR R4 (y de perfiles de CL Core) para las listas desplegables y para validar rutas.

Los datos salen de `libro/datos/elementos_r4.json` (se genera con `scripts/extract_elementos.py`) y de `rutas` en el
catálogo de CL Core (`scripts/extract_catalog.py`).
"""
from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path

DATOS = Path(__file__).resolve().parent / "datos" / "elementos_r4.json"
# Tipos de dato cuyos hijos se ofrecen en las listas (name.family, code.coding.system, valueQuantity.unit...).
EXPANDIBLES = {"HumanName", "Address", "ContactPoint", "Identifier", "CodeableConcept", "Coding", "Quantity", "Period",
               "Range", "Ratio", "Annotation", "Attachment", "Age", "Count", "Distance", "Duration", "SimpleQuantity", "Reference",
               "Signature", "Dosage", "Timing", "Money", "Meta", "SampledData", "ContactDetail", "Contributor", "DataRequirement",
               "Expression", "MarketingStatus", "ParameterDefinition", "Population", "ProdCharacteristic", "ProductShelfLife",
               "RelatedArtifact", "SubstanceAmount", "TriggerDefinition", "UsageContext", "Narrative"}
PROFUNDIDAD_MAX = 3
SIN_COMPROBAR = ("extension", "modifierExtension", "id")


@lru_cache(maxsize=1)
def datos() -> dict:
    if not DATOS.is_file():
        return {"recursos": {}, "tipos": {}}
    return json.loads(DATOS.read_text(encoding="utf-8"))


def hay_datos() -> bool:
    return bool(datos()["recursos"])


def _mayuscula(tipo: str) -> str:
    return tipo[:1].upper() + tipo[1:]


def _hijos(tipo: str, prefijo: str, profundidad: int, out: dict) -> None:
    if profundidad > PROFUNDIDAD_MAX or tipo not in EXPANDIBLES:
        return
    for ruta, mn, mx, tipos in datos()["tipos"].get(tipo, []):
        if ruta.endswith("[x]"):
            continue
        out.setdefault(f"{prefijo}.{ruta}", (mn, mx, tuple(tipos)))
        if "." not in ruta and len(tipos) == 1:
            _hijos(tipos[0], f"{prefijo}.{ruta}", profundidad + 1, out)


@lru_cache(maxsize=None)
def rutas_de_recurso(recurso: str) -> dict[str, tuple[int, str, tuple]]:
    """{ruta: (mín, máx, tipos)} de un recurso base, con los hijos de los tipos de dato y las variantes de los `x[x]`."""
    out: dict[str, tuple[int, str, tuple]] = {}
    fuente = datos()["recursos"].get(recurso) or datos()["tipos"].get(recurso, [])        # un recurso o un tipo de dato (Address...)
    for ruta, mn, mx, tipos in fuente:
        out.setdefault(ruta, (mn, mx, tuple(tipos)))
        if ruta.endswith("[x]"):
            base = ruta[:-3]
            for t in tipos:
                concreta = base + _mayuscula(t)
                out.setdefault(concreta, (mn, mx, (t,)))
                _hijos(t, concreta, 1, out)
        elif len(tipos) == 1:
            _hijos(tipos[0], ruta, 1, out)
    return out


def rutas_con_perfil(recurso: str, rutas_clcore: list[list] | None) -> dict[str, tuple[int, str]]:
    """Rutas del recurso más las propias del perfil de CL Core (slices y extensiones con nombre)."""
    out = dict(rutas_de_recurso(recurso))
    for ruta, mn, mx, *resto in rutas_clcore or []:
        out[ruta] = (mn, mx, tuple(resto[0]) if resto else ()) if ruta not in out or "[" in ruta else \
            (mn, mx, out[ruta][2])          # el perfil de CL Core puede estrechar cardinalidades; los tipos del recurso se conservan
    return out


def _normalizar(ruta: str) -> str:
    return re.sub(r"\[(\d+|\+|=)\]", "", ruta)


def comprobar_ruta(ruta: str, rutas: dict) -> str | None:
    """None si la ruta es válida o no se puede decidir; si no existe, un mensaje corto con la sugerencia."""
    if not rutas:
        return None
    r = _normalizar(ruta)
    if r in rutas:
        return None
    segmentos = r.split(".")
    if any(re.sub(r"\[.*", "", s) in SIN_COMPROBAR for s in segmentos) or "[" in r.replace("[x]", ""):
        return None                      # extensiones y slices propios: lo decide SUSHI
    cerca = difflib.get_close_matches(r, list(rutas), n=1, cutoff=0.6)
    return f"¿Quisiste decir «{cerca[0]}»?" if cerca else "No coincide con ningún elemento del recurso."


def lista_para(recurso: str, rutas_clcore: list[list] | None = None) -> list[str]:
    """Rutas ofrecidas en el desplegable: las del recurso y, aparte, los slices/extensiones del perfil de CL Core."""
    base = list(rutas_de_recurso(recurso))
    extra = sorted(r[0] for r in (rutas_clcore or []) if "[" in r[0].replace("[x]", "") and r[0] not in base)
    return base + extra


# Tipo de FHIR -> «Tipo de dato» de la hoja Valores. Los tipos contenedor (HumanName, Period...) no tienen: hay que elegir un hijo.
TIPO_DE_DATO = {
    "code": "código simple", "Coding": "código con sistema", "CodeableConcept": "código con sistema",
    "string": "texto", "markdown": "texto", "uri": "texto", "url": "texto", "canonical": "texto", "oid": "texto",
    "uuid": "texto", "id": "texto", "time": "texto", "base64Binary": "texto",
    "integer": "número", "positiveInt": "número", "unsignedInt": "número", "decimal": "número",
    "boolean": "booleano", "date": "fecha", "dateTime": "fecha y hora", "instant": "fecha y hora",
    "Quantity": "cantidad", "SimpleQuantity": "cantidad", "Age": "cantidad", "Count": "cantidad",
    "Distance": "cantidad", "Duration": "cantidad", "Reference": "referencia",
}


def tipo_de_dato(ruta: str, rutas: dict) -> str:
    """«Tipo de dato» que corresponde a un elemento, o '' si no se puede deducir (contenedores y `x[x]` sin elegir)."""
    info = rutas.get(_normalizar(ruta)) or rutas.get(re.sub(r"\[(?!x\])[^\]]+\]", "", ruta))   # sin índices ni nombres de slice
    tipos = info[2] if info and len(info) > 2 else ()
    etiquetas = {TIPO_DE_DATO.get(t, "") for t in tipos}
    return next(iter(etiquetas)) if len(etiquetas) == 1 and "" not in etiquetas else ""


def tipos_para(recurso: str, rutas_clcore: list[list] | None = None) -> list[str]:
    """Tipo de dato de cada ruta de `lista_para`, en el mismo orden (vacío si no se puede deducir)."""
    rutas = rutas_con_perfil(recurso, rutas_clcore)
    return [tipo_de_dato(r, rutas) for r in lista_para(recurso, rutas_clcore)]
