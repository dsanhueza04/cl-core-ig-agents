"""Extensiones propias del libro: índice por nombre de slice y resolución de rutas de ejemplos.

Una extensión simple guarda un valor (`tipo`); una compleja tiene partes (filas con «Es parte de»). En las rutas se
nombran por su slice: `extension[aniosEscolaridad]`, y una parte `extension[contactoPreferido].extension[medio]`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from libro.comun import minuscula_inicial
from libro.lector import Libro

RE_EXT_FINAL = re.compile(r"^(?P<ini>.*?)extension\[(?P<s>[A-Za-z][A-Za-z0-9]*)\]$")
RE_EXT_PADRE = re.compile(r"extension\[([A-Za-z][A-Za-z0-9]*)\]\.$")


def tipo_base(tipo: str) -> str:
    """`Reference(Patient)` -> `Reference`."""
    return re.sub(r"\(.*\)$", "", tipo.strip())


def sufijo_valor(tipo: str) -> str:
    """Nombre del elemento de valor de una extensión: `string` -> `valueString`."""
    b = tipo_base(tipo)
    return "value" + b[:1].upper() + b[1:]


@dataclass
class Indice:
    superiores: dict[str, dict] = field(default_factory=dict)            # slice -> fila
    partes: dict[tuple[str, str], dict] = field(default_factory=dict)    # (nombre del padre, slice) -> fila

    def partes_de(self, nombre: str) -> list[dict]:
        return [f for (p, _), f in self.partes.items() if p == nombre]

    def es_compleja(self, fila: dict) -> bool:
        return bool(self.partes_de(fila["nombre"]))


def slice_de(f: dict) -> str:
    """Nombre del slice (y URL) de una parte de extensión: el «código de la parte» si lo hay, si no el nombre con minúscula inicial."""
    return f.get("codigo_parte") or minuscula_inicial(f["nombre"])


def indice(libro: Libro) -> Indice:
    ix = Indice()
    for f in libro.filas("Extensiones"):
        if not f["nombre"]:
            continue
        if f["parte_de"]:
            ix.partes.setdefault((f["parte_de"], slice_de(f)), f)
        else:
            ix.superiores.setdefault(minuscula_inicial(f["nombre"]), f)
    # Una misma extensión puede usarse con otro nombre de slice: `extension[nacionalidad]` con «Debe seguir el perfil» = CodigoPaises.
    por_nombre = {f["nombre"]: f for f in ix.superiores.values()}
    for e in libro.filas("Elementos"):
        m = RE_EXT_FINAL.match(e["ruta"])
        if m and e["perfil_tipo"]:
            destino = por_nombre.get(e["perfil_tipo"]) or next((f for f in ix.superiores.values() if f["url"] and f["url"] == e["perfil_tipo"]), None)
            if destino is not None:
                ix.superiores.setdefault(m["s"], destino)
    return ix


def resolver(ruta: str, ix: Indice):
    """Si `ruta` termina en una extensión del libro: ('simple', fila) | ('compleja', fila) | ('parte_desconocida', padre, slice).

    Devuelve None si no termina en `extension[...]` o si la extensión no es del libro (por ejemplo, una de CL Core).
    """
    m = RE_EXT_FINAL.match(ruta)
    if not m:
        return None
    s, ini = m["s"], m["ini"]
    mp = RE_EXT_PADRE.search(ini)
    if mp and mp[1] in ix.superiores:
        padre = ix.superiores[mp[1]]
        fila = ix.partes.get((padre["nombre"], s))
        if fila is None:
            return ("parte_desconocida", padre, s)
    elif s in ix.superiores:
        fila = ix.superiores[s]
    else:
        return None
    return ("compleja" if ix.es_compleja(fila) else "simple", fila)


def ruta_completa(ruta: str, ix: Indice) -> str:
    """Agrega el elemento de valor a una extensión simple (`extension[x]` -> `extension[x].valueString`)."""
    r = resolver(ruta, ix)
    if r and r[0] == "simple" and r[1]["tipo"]:
        return f"{ruta}.{sufijo_valor(r[1]['tipo'])}"
    return ruta
