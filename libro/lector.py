"""Lee el libro de Excel y devuelve su contenido como datos simples, tolerante a filas vacías y espacios."""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from libro.esquema import FILA_ENCABEZADO, GUIA_CAMPOS, HOJAS, OPCIONAL, PRIMERA_FILA


class LibroInvalido(Exception):
    """El archivo no es un libro de la plantilla (faltan hojas o encabezados)."""


@dataclass
class Libro:
    guia: dict[str, str] = field(default_factory=dict)
    guia_filas: dict[str, int] = field(default_factory=dict)
    hojas: dict[str, list[dict]] = field(default_factory=dict)   # cada fila lleva "_fila" (número en el Excel)
    base: Path | None = None                                     # carpeta del libro: ahí se buscan «paginas/» e «imagenes/»

    def filas(self, hoja: str) -> list[dict]:
        return self.hojas.get(hoja, [])


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, datetime):      # Excel convierte las fechas escritas a mano; se devuelven en formato FHIR
        return v.date().isoformat() if v.time() == datetime.min.time() else v.isoformat(timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, bool):
        return "Sí" if v else "No"
    return str(v).strip()


def leer_libro(ruta: str | Path) -> Libro:
    ruta = Path(ruta)
    try:
        with warnings.catch_warnings():
            # Excel guarda las listas desplegables entre hojas como «extensión»; openpyxl avisa pero lee bien los datos.
            warnings.simplefilter("ignore", UserWarning)
            wb = load_workbook(ruta, data_only=True, read_only=False)
    except Exception as e:   # archivo corrupto, no es xlsx, etc.
        raise LibroInvalido(f"No pude abrir «{ruta.name}» como libro de Excel (.xlsx): {e}") from e
    libro = Libro(base=ruta.resolve().parent)
    if "Guía" not in wb.sheetnames:
        raise LibroInvalido("Falta la hoja «Guía». ¿Es un libro creado con la plantilla? (python cl_ig.py plantilla)")
    por_etiqueta = {c.etiqueta: c.clave for c in GUIA_CAMPOS}
    ws = wb["Guía"]
    for r in range(PRIMERA_FILA, ws.max_row + 1):
        etiqueta = _texto(ws.cell(r, 1).value)
        if etiqueta in por_etiqueta:
            libro.guia[por_etiqueta[etiqueta]] = _texto(ws.cell(r, 2).value)
            libro.guia_filas[por_etiqueta[etiqueta]] = r
    for hoja in HOJAS:
        if hoja.nombre not in wb.sheetnames:
            continue                                   # una hoja ausente equivale a una hoja vacía
        ws = wb[hoja.nombre]
        encabezados = {_texto(ws.cell(FILA_ENCABEZADO, c).value): c for c in range(1, ws.max_column + 1)}
        # Las columnas opcionales que se agregaron en versiones nuevas pueden faltar en libros antiguos: se leen como vacías.
        faltan = [c.etiqueta for c in hoja.columnas if c.etiqueta not in encabezados and c.estado != OPCIONAL]
        if faltan:
            raise LibroInvalido(f"En la hoja «{hoja.nombre}» faltan los encabezados: {', '.join(faltan)}. "
                                f"No cambies la fila {FILA_ENCABEZADO} de la plantilla.")
        filas = []
        for r in range(PRIMERA_FILA, ws.max_row + 1):
            fila = {c.clave: (_texto(ws.cell(r, encabezados[c.etiqueta]).value) if c.etiqueta in encabezados else "") for c in hoja.columnas}
            if any(fila.values()):
                fila["_fila"] = r
                filas.append(fila)
        libro.hojas[hoja.nombre] = filas
    return libro
