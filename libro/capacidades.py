"""Une el resumen de RecursosCapacidad con el detalle de OperacionesCapacidad y BusquedasCapacidad.

Una operación o búsqueda escrita en su hoja de detalle reemplaza a la del resumen (así puede llevar expectativa y explicación).
"""
from __future__ import annotations

from libro.comun import lista
from libro.lector import Libro


def operaciones(libro: Libro, capacidad: str, recurso: str) -> list[dict]:
    """[{codigo, expectativa, _fila}] de un recurso; con recurso="" son las operaciones de todo el servidor."""
    out: dict[str, dict] = {}
    if recurso:
        for f in libro.filas("RecursosCapacidad"):
            if f["capacidad"] == capacidad and f["recurso"] == recurso:
                for c in lista(f["interacciones"]):
                    out.setdefault(c, {"codigo": c, "expectativa": "", "_fila": None})
    for f in libro.filas("OperacionesCapacidad"):
        if f["capacidad"] == capacidad and f["recurso"] == recurso and f["operacion"] and not f["definicion"]:
            out[f["operacion"]] = {"codigo": f["operacion"], "expectativa": f["expectativa"], "_fila": f["_fila"]}
    return list(out.values())


def busquedas(libro: Libro, capacidad: str, recurso: str) -> list[dict]:
    """[{nombre, tipo, expectativa, definicion, documentacion, _fila}] de un recurso."""
    out: dict[str, dict] = {}
    for f in libro.filas("RecursosCapacidad"):
        if f["capacidad"] == capacidad and f["recurso"] == recurso:
            for b in lista(f["busquedas"]):
                n, _, t = b.partition(":")
                out[n.strip()] = {"nombre": n.strip(), "tipo": t.strip(), "expectativa": "", "definicion": "", "documentacion": "", "_fila": None}
    for f in libro.filas("BusquedasCapacidad"):
        if f["capacidad"] == capacidad and f["recurso"] == recurso and f["parametro"]:
            out[f["parametro"]] = {"nombre": f["parametro"], "tipo": f["tipo"], "expectativa": f["expectativa"], "definicion": f["definicion"],
                                   "documentacion": f["documentacion"], "_fila": f["_fila"]}
    return list(out.values())


def separar_expectativa(token: str) -> tuple[str, str]:
    """`Observation:subject SHALL` -> (`Observation:subject`, `SHALL`). Sin expectativa devuelve (token, "")."""
    from libro.esquema import EXPECTATIVAS
    partes = token.strip().rsplit(None, 1)
    if len(partes) == 2 and partes[1].upper() in EXPECTATIVAS:
        return partes[0].strip(), partes[1].upper()
    return token.strip(), ""


def operaciones_propias(libro: Libro, capacidad: str, recurso: str) -> list[dict]:
    """Operaciones definidas por la guía (con OperationDefinition) que un recurso, o todo el servidor, declara."""
    return [{"nombre": f["operacion"], "definicion": f["definicion"], "expectativa": f["expectativa"], "_fila": f["_fila"]}
            for f in libro.filas("OperacionesCapacidad")
            if f["capacidad"] == capacidad and f["recurso"] == recurso and f["operacion"] and f["definicion"]]
