"""Utilidades compartidas por el verificador y el generador."""
from __future__ import annotations

import re

from generator.spec import kebab, pascal  # noqa: F401  (se reexportan)
from libro.esquema import SISTEMAS_CONOCIDOS

RE_NOMBRE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
RE_ID = re.compile(r"^[a-z0-9][a-z0-9\-.]{0,63}$")
RE_URL = re.compile(r"^(https?://|urn:)\S+$")
_SEG = r"[a-z][A-Za-z0-9]*(?:\[[^\]\s]+\])*"
RE_RUTA = re.compile(rf"^{_SEG}(?:\.{_SEG})*$")
RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_FECHA_HORA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$")
RE_FECHA_LATINA = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")
RE_UCUM = re.compile(r"^[A-Za-z0-9\[\]/.\-^%_{}()*]+$")
RE_CODIGO_SEGURO = re.compile(r"^[A-Za-z0-9\-_.]+$")
SI = {"sí", "si", "s", "true", "verdadero", "yes", "1"}
NO = {"no", "n", "false", "falso", "0"}


def es_si(valor: str) -> bool:
    return valor.strip().lower() in SI


def es_no(valor: str) -> bool:
    return valor.strip().lower() in NO


def sin_indices(ruta: str) -> str:
    """`name[0].given[1]` -> `name.given`."""
    return re.sub(r"\[[^\]]*\]", "", ruta).replace("[x]", "")


def primer_segmento(ruta: str) -> str:
    return sin_indices(ruta).split(".")[0]


def maximo(texto: str) -> float | None:
    if texto == "*":
        return float("inf")
    return float(int(texto)) if texto.isdigit() else None


def entero(texto: str) -> int | None:
    return int(texto) if texto.isdigit() else None


def url_sistema(valor: str, nombres_cs: set[str]) -> tuple[str, str | None]:
    """Clasifica un «sistema» escrito por la persona.

    Devuelve (clase, url): clase = 'libro' (CodeSystem del libro), 'conocido', 'url' o 'desconocido'.
    """
    v = valor.strip()
    if v in nombres_cs:
        return "libro", None
    for nombre, url in SISTEMAS_CONOCIDOS.items():
        if v.lower() == nombre.lower():
            return "conocido", url
    if RE_URL.match(v):
        return "url", v
    return "desconocido", None


def minuscula_inicial(nombre: str) -> str:
    """`AniosEscolaridad` -> `aniosEscolaridad` (nombre de slice de una extensión)."""
    return nombre[:1].lower() + nombre[1:]


def lista(texto: str) -> list[str]:
    """«A, B or C» / «A; B» -> ['A', 'B', 'C']."""
    return [x.strip() for x in re.split(r",|;|\s+or\s+|\n", texto) if x.strip()]


# ---- páginas y menú de la guía
PAGINAS_GENERADAS = {"must-support": "Must Support", "cambios": "Historial de cambios"}


def texto_de_pagina(base, texto: str) -> tuple[str, str]:
    """Texto de una página. Si empieza con «@», es la ruta de un .md dentro de «paginas/» junto al libro. Devuelve (texto, error)."""
    t = (texto or "").strip()
    if not t.startswith("@"):
        return texto, ""
    rel = t[1:].strip()
    if base is None:
        return "", "No sé dónde está la carpeta del libro, así que no puedo leer el archivo."
    carpeta = (base / "paginas").resolve()
    ruta = (base / rel).resolve()
    if carpeta not in ruta.parents:
        return "", f"El archivo «{rel}» debe estar dentro de la carpeta «paginas», junto al libro (ej.: @paginas/objetivos.md)."
    if ruta.suffix.lower() != ".md":
        return "", f"El archivo «{rel}» debe terminar en .md."
    if not ruta.is_file():
        return "", f"No encuentro el archivo «{rel}» junto al libro ({base})."
    contenido = ruta.read_text(encoding="utf-8-sig")
    if not contenido.strip():
        return "", f"El archivo «{rel}» está vacío."
    return contenido, ""


def href_menu(destino: str, paginas: set[str], capacidades: dict[str, str]) -> str | None:
    """Enlace del menú para un destino; None si el destino no existe. `capacidades` = {nombre: id}."""
    d = (destino or "").strip()
    if d.startswith(("http://", "https://")):
        return d
    if d.lower() == "artefactos":
        return "artifacts.html"
    if d in paginas:
        return "index.html" if d == "inicio" else f"{d}.html"
    if d in capacidades:
        return f"CapabilityStatement-{capacidades[d]}.html"
    return None
