"""Muestra la estructura de un recurso o perfil de CL Core: qué elementos trae, con qué cardinalidad y de qué tipo.

Sirve para decidir en qué elemento escribir una regla del libro: lo que aparece aquí sin que lo toques ya viene heredado.
"""
from __future__ import annotations

from libro import elementos
from libro.esquema import RECURSOS_R4, TIPOS_DATO


def _resolver(nombre: str, catalogo):
    if catalogo and nombre in catalogo.sd:
        sd = catalogo.sd[nombre]
        return sd["type"], sd.get("rutas"), sd["id"]
    if nombre in RECURSOS_R4 or nombre in TIPOS_DATO:
        return nombre, None, nombre
    return None, None, nombre


def estructura(nombre: str, catalogo=None, ruta: str = "", profundidad: int = 2) -> str:
    """Texto con el árbol de elementos. `ruta` limita a un elemento y sus hijos; `profundidad` = niveles bajo ese elemento."""
    if not elementos.hay_datos():
        return "No tengo los datos de FHIR R4 (libro/datos/elementos_r4.json).\n"
    recurso, rutas_clcore, titulo = _resolver(nombre, catalogo)
    if recurso is None:
        return f"No conozco «{nombre}». Usa un recurso de FHIR (Patient, Observation...) o un perfil de CL Core (CorePacienteCl).\n"
    rutas = elementos.rutas_con_perfil(recurso, rutas_clcore)
    base = ruta.strip(".")
    nivel_base = base.count(".") + 1 if base else 0
    filas = []
    for r, info in rutas.items():
        sin_x = r.replace("[x]", "")
        if base and not (sin_x == base or sin_x.startswith(base + ".") or r == base or r.startswith(base + ".")):
            continue
        nivel = sin_x.count(".") + 1
        if nivel - (nivel_base or 1) > profundidad - (0 if base else 1):
            continue
        if "[" in sin_x and not base and "." in sin_x:
            continue                                  # los hijos de cada slice se ven pidiendo ese slice
        mn, mx, tipos = info[0], info[1], info[2] if len(info) > 2 else ()
        filas.append((nivel, r, f"{mn}..{mx}", "/".join(tipos[:3]) + ("…" if len(tipos) > 3 else "")))
    if not filas:
        return f"«{base}» no es un elemento de {titulo}.\n"
    ancho = max(len("  " * (n - 1) + r.split('.')[-1]) for n, r, *_ in filas)
    out = [f"{titulo} ({recurso}) — cardinalidad y tipo de cada elemento" + (f", desde «{base}»" if base else ""), ""]
    for n, r, card, tipo in filas:
        etiqueta = "  " * (n - 1) + r.split(".")[-1]
        out.append(f"{etiqueta:<{ancho}}  {card:<6} {tipo}")
    out += ["", "Cada hijo tiene su propia cardinalidad: una regla sobre el padre no la cambia.",
            "Para ver más hijos: python cl_ig.py estructura " + nombre + " --ruta <elemento> --profundidad 3"]
    return "\n".join(out) + "\n"
