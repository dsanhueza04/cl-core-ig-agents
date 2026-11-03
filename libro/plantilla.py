"""Crea el libro de Excel (plantilla vacía o con datos) a partir del esquema."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

from libro import elementos
from libro.esquema import (HOJA_POR_NOMBRE, FILA_ENCABEZADO, FILA_ESTADO, GUIA_CAMPOS, HOJAS, OBLIGATORIO, OPCIONAL, PRIMERA_FILA,
                           RECOMENDADO, RECURSOS_R4, TIPOS_DATO)

COLOR_ESTADO = {OBLIGATORIO: "F8CBAD", RECOMENDADO: "FFE699", OPCIONAL: "D9D9D9"}
FILAS_MAX = 500

LEEME = """Cómo usar este libro

1. Empieza por la hoja «Guía»: completa al menos los campos marcados como Obligatorio.
2. Define tus perfiles en «Perfiles» y sus reglas en «Elementos».
   Si necesitas un dato que el recurso no tiene, créalo en «Extensiones» y úsalo en «Elementos» con la ruta que muestra su columna gris.
   Si un elemento se repite con usos distintos (teléfono y correo en telecom), sepáralo en «Slices».
   Para afinar los campos internos del valor de una extensión (un Identifier con system y value obligatorios), usa «ValorExtensiones».
   Para declarar qué ofrece un servidor (CapabilityStatement), usa «Capacidades» y «RecursosCapacidad».
3. Si necesitas códigos propios, usa «CodeSystems» + «Conceptos»; para listas de valores permitidos, «ValueSets» + «Inclusiones».
4. Escribe ejemplos en «Instancias» y sus datos en «Valores».
5. Escribe la narrativa en «Documentación» (si no la escribes, se genera un borrador). Opcional: «Menú» arma el menú superior; «Cambios» el historial.
6. Ejecuta: python cl_ig.py revisar <este libro>.xlsx   — te avisa de problemas en lenguaje simple.
7. Ejecuta: python cl_ig.py construir <este libro>.xlsx  — genera la guía y la valida.

Colores de la fila 3:  rojo = Obligatorio · amarillo = Recomendado · gris = Opcional.
No cambies los nombres de las hojas ni los encabezados de la fila 4. Puedes dejar vacías las hojas que no necesites.
Los datos de ejemplo deben ser ficticios. Una persona debe revisar siempre la guía generada antes de usarla."""


def _estilo_celda_titulo(ws, titulo: str, ayuda: str, ncols: int) -> None:
    ws.cell(1, 1, titulo).font = Font(bold=True, size=14)
    ws.cell(2, 1, ayuda).alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(ncols, 2))
    ws.row_dimensions[2].height = 32


def _encabezados(ws, columnas) -> None:
    for i, c in enumerate(columnas, start=1):
        e = ws.cell(FILA_ESTADO, i, c.estado)
        e.fill = PatternFill("solid", fgColor=COLOR_ESTADO[c.estado])
        e.font = Font(size=9, italic=True)
        h = ws.cell(FILA_ENCABEZADO, i, c.etiqueta)
        h.font = Font(bold=True, color="FFFFFF")
        h.fill = PatternFill("solid", fgColor="2F5597")
        h.comment = Comment(f"{c.estado}. {c.ayuda}", "cl-core-ig-agents", width=320, height=110)
        ws.column_dimensions[get_column_letter(i)].width = c.ancho
    ws.freeze_panes = ws.cell(PRIMERA_FILA, 1)


def _lista(ws, formula: str, col: int, desde: int, hasta: int) -> None:
    dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=False)
    ws.add_data_validation(dv)
    letra = get_column_letter(col)
    dv.add(f"{letra}{desde}:{letra}{hasta}")


def _nombre(texto: str) -> str:
    """Nombre válido de rango en Excel (sin guiones)."""
    return texto.replace("-", "_")


def _hoja_listas(wb, catalogo) -> None:
    """Hoja oculta «Listas» con una columna por lista y un nombre de rango por columna.

    padres_<Recurso>      perfiles de CL Core de ese recurso
    rutas_<Recurso>       elementos del recurso base de FHIR R4 (con los hijos de sus tipos de dato)
    rutasp_<Perfil>       elementos de un perfil de CL Core, con sus slices y extensiones
    """
    ws = wb.create_sheet("Listas")
    columnas: dict[str, list[str]] = {"padres_vacio": [""]}
    sds = [s for s in (catalogo.sd.values() if catalogo else []) if s["kind"] in ("resource", "complex-type")]
    for recurso in RECURSOS_R4 + TIPOS_DATO:
        columnas[f"padres_{recurso}"] = sorted(s["id"] for s in sds if s["type"] == recurso) or [""]
        if elementos.hay_datos():
            columnas[f"rutas_{recurso}"] = elementos.lista_para(recurso) or [""]
            columnas[f"tipos_{recurso}"] = elementos.tipos_para(recurso) or [""]
    if elementos.hay_datos():
        for s in sds:
            if s.get("rutas") and (s["type"] in RECURSOS_R4 or s["type"] in TIPOS_DATO):
                columnas[f"rutasp_{_nombre(s['id'])}"] = elementos.lista_para(s["type"], s["rutas"])
                columnas[f"tiposp_{_nombre(s['id'])}"] = elementos.tipos_para(s["type"], s["rutas"])
    for i, (nombre, valores) in enumerate(columnas.items(), start=1):
        letra = get_column_letter(i)
        ws.cell(1, i, nombre)
        for j, v in enumerate(valores, start=2):
            if v:
                ws.cell(j, i, v)
        ref = f"Listas!${letra}$2:${letra}${len(valores) + 1}"
        wb.defined_names[nombre] = DefinedName(nombre, attr_text=ref)
    ws.sheet_state = "hidden"


def _col_aux_perfiles() -> tuple[int, int]:
    """Columnas ocultas de «Perfiles»: las dos que siguen a las de datos."""
    n = len(HOJA_POR_NOMBRE["Perfiles"].columnas)
    return n + 1, n + 2


def _auxiliares_perfiles(ws, fila_max: int) -> None:
    """Columnas ocultas de «Perfiles»: perfil de CL Core del que parte cada perfil (hasta dos saltos por perfiles propios)."""
    c1, c2 = _col_aux_perfiles()
    l1, l2 = get_column_letter(c1), get_column_letter(c2)
    A, C = f"$A${PRIMERA_FILA}:$A${fila_max}", f"$C${PRIMERA_FILA}:$C${fila_max}"
    G = f"${l1}${PRIMERA_FILA}:${l1}${fila_max}"
    ws.cell(FILA_ENCABEZADO, c1, "(auxiliar 1)")
    ws.cell(FILA_ENCABEZADO, c2, "(auxiliar 2)")
    for r in range(PRIMERA_FILA, fila_max + 1):
        ws.cell(r, c1, f'=IF(C{r}="","",IF(ISNUMBER(MATCH(C{r},{A},0)),INDEX({C},MATCH(C{r},{A},0)),C{r}))')
        ws.cell(r, c2, f'=IF({l1}{r}="","",IF(ISNUMBER(MATCH({l1}{r},{A},0)),INDEX({G},MATCH({l1}{r},{A},0)),{l1}{r}))')
    ws.column_dimensions[l1].hidden = True
    ws.column_dimensions[l2].hidden = True


def _auxiliar_elementos(ws, ncols: int, fila_max: int) -> int:
    """Columna oculta de «Elementos» con el nombre de la lista de rutas que corresponde al perfil de cada fila."""
    col = ncols + 1
    A, B, H = (f"Perfiles!${c}${PRIMERA_FILA}:${c}${fila_max}" for c in ("A", "B", get_column_letter(_col_aux_perfiles()[1])))
    ws.cell(FILA_ENCABEZADO, col, "(lista de rutas)")
    for r in range(PRIMERA_FILA, fila_max + 1):
        idx = f"MATCH($A{r},{A},0)"
        base = f'SUBSTITUTE(INDEX({H},{idx}),"-","_")'
        ws.cell(r, col, f'=IF($A{r}="","",IFERROR(IF(ISREF(INDIRECT("rutasp_"&{base})),"rutasp_"&{base},"rutas_"&INDEX({B},{idx})),""))')
    ws.column_dimensions[get_column_letter(col)].hidden = True
    return col


def _auxiliares_valores(ws, ncols: int, fila_max: int) -> tuple[int, int]:
    """«Valores»: columna oculta con la lista de rutas del perfil de cada ejemplo y columna visible «Tipo sugerido»."""
    col_tipo, col_lista = ncols + 1, ncols + 2
    IA, IB = (f"Instancias!${c}${PRIMERA_FILA}:${c}${fila_max}" for c in "AB")
    PA, PB, PH = (f"Perfiles!${c}${PRIMERA_FILA}:${c}${fila_max}" for c in "ABH")
    L = get_column_letter(col_lista)
    ws.cell(FILA_ENCABEZADO, col_tipo, "Tipo sugerido")
    ws.cell(FILA_ENCABEZADO, col_tipo).font = Font(bold=True, color="FFFFFF")
    ws.cell(FILA_ENCABEZADO, col_tipo).fill = PatternFill("solid", fgColor="7F7F7F")
    ws.cell(FILA_ENCABEZADO, col_lista, "(lista de rutas)")
    ws.column_dimensions[get_column_letter(col_tipo)].width = 20
    for r in range(PRIMERA_FILA, fila_max + 1):
        p = f"INDEX({IB},MATCH($A{r},{IA},0))"
        idx = f"MATCH({p},{PA},0)"
        propio = f'SUBSTITUTE(INDEX({PH},{idx}),"-","_")'
        clcore = f'SUBSTITUTE({p},"-","_")'
        formula = (
            f'=IF($A{r}="","",IFERROR(IF(ISNUMBER({idx}),'
            f'IF(ISREF(INDIRECT("rutasp_"&{propio})),"rutasp_"&{propio},"rutas_"&INDEX({PB},{idx})),'
            f'IF(ISREF(INDIRECT("rutasp_"&{clcore})),"rutasp_"&{clcore},"rutas_"&{p})),""))')
        ws.cell(r, col_lista, formula)
        ruta = f"$B{r}"
        for ind in [str(i) for i in range(10)] + ["+", "="]:
            ruta = f'SUBSTITUTE({ruta},"[{ind}]","")'
        ws.cell(r, col_tipo, f'=IF(OR(${L}{r}="",$B{r}=""),"",IFERROR(INDEX(INDIRECT("tipos"&MID(${L}{r},6,99)),MATCH({ruta},INDIRECT(${L}{r}),0))&"",""))')
    ws.column_dimensions[L].hidden = True
    return col_tipo, col_lista


def _pista_extensiones(ws, claves: dict, ncols: int, fila_max: int) -> None:
    """Columna gris de «Extensiones» con la ruta que hay que escribir en Elementos y Valores."""
    col = ncols + 1
    ws.cell(FILA_ENCABEZADO, col, "Ruta para usarla")
    ws.cell(FILA_ENCABEZADO, col).font = Font(bold=True, color="FFFFFF")
    ws.cell(FILA_ENCABEZADO, col).fill = PatternFill("solid", fgColor="7F7F7F")
    ws.column_dimensions[get_column_letter(col)].width = 44
    n = get_column_letter(claves["nombre"])
    p = get_column_letter(claves["parte_de"])
    for r in range(PRIMERA_FILA, fila_max + 1):
        propio = f'LOWER(LEFT({n}{r},1))&MID({n}{r},2,99)'
        padre = f'LOWER(LEFT({p}{r},1))&MID({p}{r},2,99)'
        ws.cell(r, col, f'=IF({n}{r}="","",IF({p}{r}="","extension["&{propio}&"]","extension["&{padre}&"].extension["&{propio}&"]"))')


def crear_libro(datos: dict | None = None, catalogo=None):
    """Devuelve un Workbook. `datos` = {hoja: [fila(dict clave->valor)]} y {"Guía": {clave: valor}}.

    Con `catalogo` (de CL Core) y los datos de FHIR R4 (`libro/datos/`), el perfil padre y el elemento se ofrecen como listas
    desplegables encadenadas al recurso y al perfil. Se puede escribir cualquier otro valor.
    """
    datos = datos or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "Léeme"
    for i, linea in enumerate(LEEME.split("\n"), start=1):
        ws.cell(i, 1, linea)
    ws["A1"].font = Font(bold=True, size=14)
    ws.column_dimensions["A"].width = 120

    # Guía: tabla de campos (Campo | Valor | Estado | Ayuda)
    g = wb.create_sheet("Guía")
    _estilo_celda_titulo(g, "Datos generales de la guía", "Una fila por campo. Completa la columna Valor.", 4)
    for i, h in enumerate(("Campo", "Valor", "Estado", "Ayuda"), start=1):
        c = g.cell(FILA_ENCABEZADO, i, h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="2F5597")
    for r, campo in enumerate(GUIA_CAMPOS, start=PRIMERA_FILA):
        g.cell(r, 1, campo.etiqueta).font = Font(bold=True)
        g.cell(r, 2, (datos.get("Guía") or {}).get(campo.clave, ""))
        e = g.cell(r, 3, campo.estado)
        e.fill = PatternFill("solid", fgColor=COLOR_ESTADO[campo.estado])
        a = g.cell(r, 4, campo.ayuda)
        a.alignment = Alignment(wrap_text=True, vertical="top")
        if campo.opciones:
            _lista(g, '"' + ",".join(campo.opciones) + '"', 2, r, r)
    for letra, ancho in zip("ABCD", (26, 50, 14, 90)):
        g.column_dimensions[letra].width = ancho
    g.freeze_panes = g.cell(PRIMERA_FILA, 1)

    claves = {h.nombre: {c.clave: i for i, c in enumerate(h.columnas, start=1)} for h in HOJAS}
    for hoja in HOJAS:
        ws = wb.create_sheet(hoja.nombre)
        _estilo_celda_titulo(ws, hoja.titulo, hoja.ayuda, len(hoja.columnas))
        _encabezados(ws, hoja.columnas)
        for r, fila in enumerate(datos.get(hoja.nombre) or [], start=PRIMERA_FILA):
            for i, c in enumerate(hoja.columnas, start=1):
                v = fila.get(c.clave, "")
                if v != "" and v is not None:
                    ws.cell(r, i, v)
        for i, c in enumerate(hoja.columnas, start=1):
            if c.opciones:
                formula = '"' + ",".join(c.opciones) + '"'
                if len(formula) <= 255:
                    _lista(ws, formula, i, PRIMERA_FILA, FILAS_MAX)
            elif c.desde:
                hoja_o, clave = c.desde
                letra = get_column_letter(claves[hoja_o][clave])
                _lista(ws, f"={hoja_o}!${letra}${PRIMERA_FILA}:${letra}${FILAS_MAX}", i, PRIMERA_FILA, FILAS_MAX)
    _hoja_listas(wb, catalogo)
    perfiles, elems = wb["Perfiles"], wb["Elementos"]
    _auxiliares_perfiles(perfiles, FILAS_MAX)
    colp = list(claves["Perfiles"]).index("padre") + 1
    colr = list(claves["Perfiles"]).index("recurso") + 1
    _lista(perfiles, f'=INDIRECT("padres_"&${get_column_letter(colr)}{PRIMERA_FILA})', colp, PRIMERA_FILA, FILAS_MAX)
    aux = _auxiliar_elementos(elems, len(HOJA_POR_NOMBRE["Elementos"].columnas), FILAS_MAX)
    colruta = list(claves["Elementos"]).index("ruta") + 1
    _lista(elems, f"=INDIRECT(${get_column_letter(aux)}{PRIMERA_FILA})", colruta, PRIMERA_FILA, FILAS_MAX)
    _pista_extensiones(wb["Extensiones"], {k: i for i, k in enumerate(claves["Extensiones"], start=1)}, len(HOJA_POR_NOMBRE["Extensiones"].columnas), FILAS_MAX)
    auxs = _auxiliar_elementos(wb["Slices"], len(HOJA_POR_NOMBRE["Slices"].columnas), FILAS_MAX)
    _lista(wb["Slices"], f"=INDIRECT(${get_column_letter(auxs)}{PRIMERA_FILA})", list(claves["Slices"]).index("elemento") + 1, PRIMERA_FILA, FILAS_MAX)
    vals = wb["Valores"]
    _, auxv = _auxiliares_valores(vals, len(HOJA_POR_NOMBRE["Valores"].columnas), FILAS_MAX)
    colrv = list(claves["Valores"]).index("ruta") + 1
    _lista(vals, f"=INDIRECT(${get_column_letter(auxv)}{PRIMERA_FILA})", colrv, PRIMERA_FILA, FILAS_MAX)
    for hoja in HOJAS:                       # columnas avanzadas: agrupadas y cerradas (botón + sobre la tabla)
        avanzadas = [i for i, c in enumerate(hoja.columnas, start=1) if c.avanzada]
        if avanzadas:
            wb[hoja.nombre].column_dimensions.group(get_column_letter(avanzadas[0]), get_column_letter(avanzadas[-1]), hidden=True)
    return wb


def guardar_plantilla(destino: str | Path, datos: dict | None = None, catalogo=None) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    crear_libro(datos, catalogo).save(destino)
    return destino
