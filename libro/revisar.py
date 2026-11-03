"""Verificador de coherencia del libro, con mensajes en lenguaje simple.

No ejecuta SUSHI: detecta antes lo que se puede saber leyendo el libro (obligatorios, nombres, referencias entre hojas,
cardinalidades más laxas que el padre, códigos que no existen, fechas mal escritas...). Un `error` impide construir la
guía; un `aviso` no, pero conviene mirarlo; una `sugerencia` es una mejora opcional.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import date

from agents.catalog import CatalogIndex
from libro.comun import (PAGINAS_GENERADAS, href_menu, texto_de_pagina, NO, RE_CODIGO_SEGURO, RE_FECHA, RE_FECHA_HORA, RE_FECHA_LATINA, RE_ID, RE_NOMBRE, RE_RUTA,
                         RE_UCUM, RE_URL, SI, entero, es_no, es_si, kebab, maximo, pascal, primer_segmento,
                         sin_indices, url_sistema)
from libro.esquema import (GRAVEDADES, OPERADORES_CONDICION, TIPOS_PREGUNTA, EQUIVALENCIAS, MODIFICADORES_BUSQUEDA, TIPOS_OPERACION, USOS_PARAMETRO, EXPECTATIVAS, OPERACIONES_SERVIDOR, POLITICAS_REFERENCIA, INTERACCIONES, MODOS_CAPACIDAD, TIPOS_BUSQUEDA, DISCRIMINADORES, FILTROS_DE_TEXTO, FILTROS_VS, MODOS_INCLUSION, REGLAS_SLICING, TIPOS_DATO, TIPOS_EXTENSION, SISTEMAS_CONOCIDOS, CONTENIDOS, ESTADOS_GUIA, FUERZAS, GUIA_CAMPOS, HOJAS, OBLIGATORIO, RECURSOS_R4, TIPOS_FIJO,
                           TIPOS_VALOR, USOS)
from libro import elementos, extensiones

RE_MIME = re.compile(r"^[a-z]+/[A-Za-z0-9.+-]+$")
from libro.comun import lista as _lista
from libro.lector import Libro

ERROR, AVISO, SUGERENCIA = "error", "aviso", "sugerencia"

# Elementos que FHIR R4 exige en cada recurso (mínimo 1). Se usa para avisar si un ejemplo no los trae.
MINIMOS_R4 = {
    "Observation": ["status", "code"], "Condition": ["subject"], "Encounter": ["status", "class"],
    "MedicationRequest": ["status", "intent", "medication", "subject"], "Procedure": ["status", "subject"],
    "Questionnaire": ["status"], "QuestionnaireResponse": ["status"],
    "Immunization": ["status", "vaccineCode", "patient", "occurrence"], "AllergyIntolerance": ["patient"],
    "DiagnosticReport": ["status", "code"], "ServiceRequest": ["status", "intent", "subject"],
    "CarePlan": ["status", "intent", "subject"], "Goal": ["lifecycleStatus", "description", "subject"],
    "Coverage": ["status", "beneficiary", "payor"], "Appointment": ["status", "participant"],
    "Composition": ["status", "type", "date", "author", "title"], "DocumentReference": ["status", "content"],
    "Task": ["status", "intent"], "List": ["status", "mode"],
}


# Slices que vienen de FHIR R4 (no de CL Core) y se usan en ejemplos de signos vitales.
SLICES_DE_FHIR = {"VSCat"}


# Tipos que se pueden usar en lugar de otro al restringir un elemento («Solo tipo»).
SUBTIPOS = {"Quantity": {"SimpleQuantity", "Age", "Count", "Distance", "Duration", "Money", "MoneyQuantity"},
            "Element": {"*"}, "BackboneElement": {"*"}}
# Qué «Tipo del valor fijo» admite cada tipo de dato del elemento.
FIJO_ADMITIDO = {"texto": {"texto"}, "código simple": {"código simple"}, "código con sistema": {"código con sistema"},
                 "número": {"número"}, "booleano": {"booleano"}, "fecha": {"texto"}, "fecha y hora": {"texto"}}


@dataclass(frozen=True)
class Aviso:
    nivel: str
    hoja: str
    fila: int | None
    mensaje: str
    que_hacer: str = ""

    def __str__(self) -> str:
        donde = f"{self.hoja}, fila {self.fila}" if self.fila else self.hoja
        extra = f" → {self.que_hacer}" if self.que_hacer else ""
        return f"[{self.nivel}] {donde}: {self.mensaje}{extra}"


class _Revisor:
    def __init__(self, libro: Libro, catalogo: CatalogIndex | None):
        self.l, self.cat = libro, catalogo
        self.avisos: list[Aviso] = []
        self.perfiles = {f["nombre"]: f for f in libro.filas("Perfiles") if f["nombre"]}
        self.cs = {f["nombre"]: f for f in libro.filas("CodeSystems") if f["nombre"]}
        self.vs = {f["nombre"]: f for f in libro.filas("ValueSets") if f["nombre"]}
        self.inst = {f["nombre"]: f for f in libro.filas("Instancias") if f["nombre"]}
        self.conceptos: dict[str, dict[str, str]] = {}
        for f in libro.filas("Conceptos"):
            self.conceptos.setdefault(f["codesystem"], {}).setdefault(f["codigo"], f["texto"])
        self.ext = extensiones.indice(libro)
        self.reglas_por_perfil: dict[str, list[dict]] = {}
        for f in libro.filas("Elementos"):
            self.reglas_por_perfil.setdefault(f["perfil"], []).append(f)

    def add(self, nivel, hoja, fila, mensaje, que_hacer=""):
        self.avisos.append(Aviso(nivel, hoja, fila, mensaje, que_hacer))

    # ---------------------------------------------------------------- Guía
    def guia(self):
        g, filas = self.l.guia, self.l.guia_filas
        for campo in GUIA_CAMPOS:
            if campo.estado == OBLIGATORIO and not g.get(campo.clave):
                self.add(ERROR, "Guía", filas.get(campo.clave), f"Falta «{campo.etiqueta}».", campo.ayuda)
        if g.get("id") and not RE_ID.match(g["id"]):
            self.add(ERROR, "Guía", filas.get("id"), f"El identificador «{g['id']}» no es válido.",
                     f"Usa solo minúsculas, números y guiones. Por ejemplo: «{kebab(g['id']) or 'mi-guia'}».")
        if not g.get("canonical"):
            self.add(AVISO, "Guía", filas.get("canonical"), "No indicaste la URL canónica; se usará una provisional.",
                     "Cámbiala por la dirección donde publicarás la guía antes de compartirla.")
        elif not RE_URL.match(g["canonical"]):
            self.add(ERROR, "Guía", filas.get("canonical"), f"La URL canónica «{g['canonical']}» no es una dirección válida.",
                     "Debe empezar con https:// (por ejemplo https://miorganizacion.cl/fhir/ig/mi-guia).")
        elif g["canonical"].endswith("/"):
            self.add(ERROR, "Guía", filas.get("canonical"), "La URL canónica no debe terminar en «/».", "Quita la barra final.")
        if g.get("idioma") and not re.fullmatch(r"[a-z]{2,3}(-[A-Za-z0-9]{2,8})*", g["idioma"].strip()):
            self.add(ERROR, "Guía", filas.get("idioma"), f"El idioma «{g['idioma']}» no es un código válido.", "Usa el código de idioma, por ejemplo: es, en o es-CL.")
        if g.get("estado") and g["estado"] not in ESTADOS_GUIA:
            self.add(ERROR, "Guía", filas.get("estado"), f"Estado «{g['estado']}» no válido.", f"Elige uno de: {', '.join(ESTADOS_GUIA)}.")
        for cmp in ("descripcion", "publicador"):
            if not g.get(cmp):
                self.add(SUGERENCIA, "Guía", filas.get(cmp), f"Conviene completar «{next(c.etiqueta for c in GUIA_CAMPOS if c.clave == cmp)}».")
        if g.get("usa_clcore") and not (es_si(g["usa_clcore"]) or es_no(g["usa_clcore"])):
            self.add(ERROR, "Guía", filas.get("usa_clcore"), "«Usar CL Core» debe ser Sí o No.")
        if not self.usa_clcore() and any(p["padre"].startswith("Core") for p in self.perfiles.values()):
            self.add(ERROR, "Guía", filas.get("usa_clcore"), "Un perfil parte de un perfil de CL Core pero «Usar CL Core» está en No.",
                     "Cámbialo a Sí o cambia el perfil padre.")

    def usa_clcore(self) -> bool:
        v = self.l.guia.get("usa_clcore", "")
        return not es_no(v)          # por defecto, sí

    # ------------------------------------------------------------- Perfiles
    def _padre(self, nombre: str):
        if nombre in self.perfiles:
            return "libro", self.perfiles[nombre]
        if self.cat and nombre in self.cat.sd:
            return "clcore", self.cat.sd[nombre]
        if RE_URL.match(nombre):
            return "url", None
        if not self.cat and self.usa_clcore():
            return "sin_catalogo", None          # podría ser de CL Core; SUSHI lo confirmará
        return None, None

    def perfiles_hoja(self):
        vistos: dict[str, int] = {}
        for f in self.l.filas("Perfiles"):
            n, r = f["nombre"], f["_fila"]
            if not n:
                self.add(ERROR, "Perfiles", r, "Falta el nombre del perfil.")
                continue
            if not RE_NOMBRE.match(n):
                self.add(ERROR, "Perfiles", r, f"El nombre «{n}» no es válido para un perfil.",
                         f"Sin espacios ni símbolos y empezando con mayúscula. Por ejemplo: «{pascal(n) or 'MiPerfil'}».")
            if n in vistos:
                self.add(ERROR, "Perfiles", r, f"El perfil «{n}» está repetido (también en la fila {vistos[n]}).", "Cada perfil debe tener un nombre único.")
            vistos[n] = r
            self._recurso(f)
            if not f["titulo"]:
                self.add(SUGERENCIA, "Perfiles", r, f"«{n}» no tiene título; se usará el nombre.")
            if not f["descripcion"]:
                self.add(AVISO, "Perfiles", r, f"«{n}» no tiene descripción.", "Explica qué representa; aparece en la guía publicada.")
        for n in self.perfiles:
            self._ciclo(n)

    def _falta_descripcion(self, hoja: str, fila: int, nombre: str) -> None:
        """El IG Publisher exige descripción a los CodeSystem y ValueSet de guías de HL7 (perfil ShareableValueSet); en otras guías es solo una buena práctica."""
        if "hl7" in self.l.guia.get("canonical", "").lower():
            self.add(ERROR, hoja, fila, f"«{nombre}» no tiene descripción.", "El IG Publisher la exige en las guías de HL7 (perfil ShareableValueSet).")
        else:
            self.add(AVISO, hoja, fila, f"«{nombre}» no tiene descripción.", "Explica para qué sirve; aparece en la guía publicada.")

    def _recurso(self, f):
        n, r, rec, padre = f["nombre"], f["_fila"], f["recurso"], f["padre"]
        if not rec:
            self.add(ERROR, "Perfiles", r, f"«{n}» no tiene recurso base.", "Elige uno de la lista (Patient, Observation...).")
        elif rec not in RECURSOS_R4 and rec not in TIPOS_DATO:
            cerca = difflib.get_close_matches(rec, RECURSOS_R4 + TIPOS_DATO, n=1, cutoff=0.7)
            self.add(ERROR, "Perfiles", r, f"«{rec}» no es un recurso de FHIR R4 ni un tipo de dato que se pueda perfilar.",
                     f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Elige uno de la lista desplegable.")
        if not padre:
            return
        clase, info = self._padre(padre)
        if clase is None:
            sugerencias = difflib.get_close_matches(padre, list(self.perfiles) + (list(self.cat.sd) if self.cat else []), n=1, cutoff=0.7)
            self.add(ERROR, "Perfiles", r, f"El perfil padre «{padre}» de «{n}» no existe.",
                     f"¿Quisiste decir «{sugerencias[0]}»?" if sugerencias else "Debe ser un perfil de esta hoja, uno de CL Core o una URL.")
        elif clase == "libro" and rec and info["recurso"] and info["recurso"] != rec:
            self.add(ERROR, "Perfiles", r, f"«{n}» es un {rec} pero su padre «{padre}» es un {info['recurso']}.", "Un perfil debe partir de un perfil del mismo recurso.")
        elif clase == "clcore" and rec and info.get("type") != rec:
            self.add(ERROR, "Perfiles", r, f"«{n}» es un {rec} pero el perfil de CL Core «{padre}» es un {info.get('type')}.",
                     "Un perfil debe partir de un perfil del mismo recurso.")
        elif clase == "sin_catalogo":
            self.add(AVISO, "Perfiles", r, f"No pude comprobar el perfil padre «{padre}» (no tengo el catálogo de CL Core).",
                     "Genera el catálogo con `python cl_ig.py catalogo` para una revisión completa; SUSHI también lo confirmará.")
        if clase in ("clcore",) and not self.usa_clcore():
            self.add(ERROR, "Perfiles", r, f"«{padre}» es de CL Core pero «Usar CL Core» está en No.")

    def _ciclo(self, nombre: str):
        visto, actual = set(), nombre
        while actual in self.perfiles and self.perfiles[actual]["padre"]:
            if actual in visto:
                self.add(ERROR, "Perfiles", self.perfiles[nombre]["_fila"], f"El perfil «{nombre}» depende de sí mismo a través de sus padres.", "Corta el ciclo.")
                return
            visto.add(actual)
            actual = self.perfiles[actual]["padre"]

    # ------------------------------------------------------------- Elementos
    def _cadena_libro(self, nombre: str) -> list[str]:
        """Perfil y sus padres que estén en el libro (el más cercano primero)."""
        cadena, visto = [], set()
        while nombre in self.perfiles and nombre not in visto:
            cadena.append(nombre)
            visto.add(nombre)
            nombre = self.perfiles[nombre]["padre"]
        return cadena

    def _cadena_con_tipos(self, nombre: str) -> list[str]:
        """Como `_cadena_libro`, más los perfiles que sus elementos exigen por «Debe seguir el perfil» (un ejemplo puede usar lo que esos perfiles declaran)."""
        cadena: list[str] = []
        pendientes = [nombre]
        while pendientes:
            for p in self._cadena_libro(pendientes.pop()):
                if p not in cadena:
                    cadena.append(p)
                    pendientes += [e["perfil_tipo"] for e in self.reglas_por_perfil.get(p, []) if e.get("perfil_tipo") in self.perfiles]
        return cadena

    def _cardinalidad_del_padre(self, perfil: str, ruta: str):
        """(min, max, de_donde) que impone el padre para esa ruta, o None si no se conoce."""
        cadena = self._cadena_libro(perfil)[1:]
        for p in cadena:
            for f in self.reglas_por_perfil.get(p, []):
                if f["ruta"] == ruta and (f["min"] or f["max"]):
                    return entero(f["min"]), maximo(f["max"]), p
        raiz = self._raiz_clcore(perfil)
        if raiz:
            for rr, mn, mx, *_ in raiz.get("rutas") or []:
                if rr == ruta:
                    return int(mn), maximo(str(mx)), raiz["id"]
        base = self.perfiles[perfil]["recurso"] if perfil in self.perfiles else ""
        if (base in RECURSOS_R4 or base in TIPOS_DATO) and elementos.hay_datos():
            lim = elementos.rutas_de_recurso(base).get(_normalizar_indices(ruta))
            if lim:
                return int(lim[0]), maximo(str(lim[1])), base
        return None

    def elementos(self):
        vistos: dict[tuple[str, str], int] = {}
        for f in self.l.filas("Elementos"):
            r, perfil, ruta = f["_fila"], f["perfil"], f["ruta"]
            if not perfil or perfil not in self.perfiles:
                cerca = difflib.get_close_matches(perfil, list(self.perfiles), n=1, cutoff=0.6) if perfil else []
                self.add(ERROR, "Elementos", r, f"El perfil «{perfil}» no está en la hoja Perfiles." if perfil else "Falta el perfil.",
                         f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Elige uno de la lista desplegable.")
                continue
            if not ruta:
                self.add(ERROR, "Elementos", r, "Falta el elemento (ruta).")
                continue
            self._ruta(f, "Elementos", perfil)
            self._ruta_existe(f, "Elementos", perfil)
            uso = self._uso_extension(f)
            if (perfil, ruta) in vistos:
                self.add(AVISO, "Elementos", r, f"«{ruta}» de «{perfil}» ya tiene reglas en la fila {vistos[(perfil, ruta)]}.", "Junta las reglas en una sola fila.")
            vistos[(perfil, ruta)] = r
            self._cardinalidad(f)
            self._binding(f)
            self._fijo(f)
            if f["tipo"] and not _tipo_valido(f["tipo"]):
                self.add(ERROR, "Elementos", r, f"El tipo «{f['tipo']}» no parece válido.", "Ejemplos: Quantity, string, Reference(Patient), Quantity or CodeableConcept.")
            if f["tipo"] and _tipo_valido(f["tipo"]):
                self._tipo_compatible(f)
            if not (uso and uso[0] in ("simple", "compleja") and f["perfil_tipo"] in (uso[1]["nombre"], uso[1]["url"])):
                self._perfil_y_destinos(f)
            if not uso and not any(f[k] for k in ("min", "max", "ms", "tipo", "valueset", "fijo", "perfil_tipo", "destinos", "resumen", "definicion", "comentario")):
                self.add(AVISO, "Elementos", r, f"La fila de «{ruta}» no define ninguna restricción.",
                         "Indica al menos una: cardinalidad, Must Support, tipo, ValueSet, valor fijo o un texto explicativo.")

    def _perfil_y_destinos(self, f):
        """«Debe seguir el perfil» (tipos de dato) y «Puede apuntar a» (referencias)."""
        r, ruta = f["_fila"], f["ruta"]
        tipos = self._tipos_del_elemento(f["perfil"], ruta)
        sabe = bool(tipos) and not ({"BackboneElement", "Element"} & set(tipos))
        if f["perfil_tipo"]:
            for nombre in _lista(f["perfil_tipo"]):
                clase, info = self._padre(nombre)
                if clase is None:
                    cerca = difflib.get_close_matches(nombre, list(self.perfiles) + (list(self.cat.sd) if self.cat else []), n=1, cutoff=0.7)
                    self.add(ERROR, "Elementos", r, f"El perfil «{nombre}» de «{ruta}» no existe.",
                             f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Debe ser un perfil de la hoja Perfiles, uno de CL Core o una URL.")
                elif sabe and "Reference" in tipos:
                    self.add(ERROR, "Elementos", r, f"«{ruta}» es una referencia: para limitar a qué apunta usa «Puede apuntar a».",
                             "«Debe seguir el perfil» es para datos como address o identifier.")
                elif info and sabe:
                    de = info.get("type") or info.get("recurso") or ""
                    if de and de not in tipos and not (_ES_GENERICO & set(tipos) and de in RECURSOS_R4):
                        self.add(ERROR, "Elementos", r, f"«{ruta}» es de tipo {', '.join(tipos)} pero el perfil «{nombre}» es de tipo {de}.",
                                 "El perfil debe ser del mismo tipo de dato que el elemento.")
            if f["tipo"]:
                self.add(ERROR, "Elementos", r, f"«{ruta}» tiene «Solo tipo» y «Debe seguir el perfil» a la vez.", "Deja solo uno.")
        if f["destinos"]:
            if sabe and "Reference" not in tipos:
                self.add(ERROR, "Elementos", r, f"«{ruta}» no es una referencia (es {', '.join(tipos)}); «Puede apuntar a» no corresponde.",
                         "Borra los destinos de esta fila.")
            if f["tipo"]:
                self.add(ERROR, "Elementos", r, f"«{ruta}» tiene «Solo tipo» y «Puede apuntar a» a la vez.",
                         "Usa solo «Puede apuntar a» (por ejemplo: Practitioner, CorePrestadorCl).")
            vistos = set()
            for d in _lista(f["destinos"]):
                if d in vistos:
                    self.add(AVISO, "Elementos", r, f"El destino «{d}» de «{ruta}» está repetido.")
                vistos.add(d)
                if d in RECURSOS_R4:
                    continue
                clase, _ = self._padre(d)
                if clase is None:
                    cerca = difflib.get_close_matches(d, RECURSOS_R4 + list(self.perfiles) + (list(self.cat.sd) if self.cat else []), n=1, cutoff=0.7)
                    self.add(ERROR, "Elementos", r, f"El destino «{d}» de «{ruta}» no existe.",
                             f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Debe ser un recurso de FHIR (Practitioner), un perfil de la hoja Perfiles, uno de CL Core o una URL.")

    def _tipos_del_elemento(self, perfil: str, ruta: str) -> tuple:
        """Tipos de FHIR del elemento en ese perfil, o () si no se sabe."""
        if not elementos.hay_datos():
            return ()
        rutas = self._rutas_de(perfil)
        info = rutas.get(_normalizar_indices(ruta)) or rutas.get(re.sub(r"\[(?!x\])[^\]]+\]", "", ruta))
        return tuple(info[2]) if info and len(info) > 2 else ()

    def _tipo_compatible(self, f):
        """«Solo tipo» debe ser uno de los tipos que el elemento ya admite (o un subtipo)."""
        tipos = self._tipos_del_elemento(f["perfil"], f["ruta"])
        if not tipos or {"BackboneElement", "Element"} & set(tipos):
            return
        for t in (extensiones.tipo_base(x) for x in re.split(r"\s+or\s+|\|", f["tipo"])):
            if not any(t == p or t in SUBTIPOS.get(p, ()) or (p in _ES_GENERICO and t in RECURSOS_R4) for p in tipos):
                self.add(ERROR, "Elementos", f["_fila"], f"«{f['ruta']}» es de tipo {', '.join(tipos)}; no se puede restringir a «{t}».",
                         "«Solo tipo» solo sirve para elegir entre los tipos que el elemento ya admite. Borra el tipo de esta fila.")

    def _fijo_compatible(self, f, hoja):
        """El valor fijo debe ser del mismo tipo que el elemento."""
        tipos = self._tipos_del_elemento(f["perfil"], f["ruta"])
        if not tipos:
            return
        esperado = elementos.tipo_de_dato(f["ruta"], self._rutas_de(f["perfil"]))
        r = f["_fila"]
        if not esperado:
            if tipos and not set(tipos) & {"BackboneElement", "Element"} and all(t not in elementos.TIPO_DE_DATO for t in tipos) and len(tipos) == 1:
                self.add(ERROR, hoja, r, f"«{f['ruta']}» agrupa varios datos ({tipos[0]}); no puede tener un valor fijo simple.",
                         "Borra el valor fijo de esta fila." if tipos[0] == "Extension" else
                         "Fija el campo de adentro (por ejemplo «" + f["ruta"] + ".system») o borra el valor fijo.")
            return
        if f["fijo_tipo"] in FIJO_ADMITIDO.get(esperado, set()):
            return
        if {esperado, f["fijo_tipo"]} == {"texto", "código simple"}:
            self.add(AVISO, hoja, r, f"«{f['ruta']}» es de tipo {tipos[0]} y el valor fijo está como «{f['fijo_tipo']}».",
                     f"Usa «{esperado}» (SUSHI puede rechazarlo).")
            return
        self.add(ERROR, hoja, r, f"«{f['ruta']}» es de tipo {', '.join(tipos)} ({esperado}) pero el valor fijo «{f['fijo']}» está como «{f['fijo_tipo']}».",
                 "Un valor fijo debe ser del mismo tipo que el elemento. Si lo pegaste de otra fila, bórralo.")

    def _uso_extension(self, f):
        """Comprueba una fila de Elementos que usa una extensión del libro (`extension[aniosEscolaridad]`)."""
        uso = extensiones.resolver(f["ruta"], self.ext)
        if not uso:
            return None
        r, ruta, perfil = f["_fila"], f["ruta"], f["perfil"]
        if uso[0] == "parte_desconocida":
            self.add(ERROR, "Elementos", r, f"La extensión «{uso[1]['nombre']}» no tiene la parte «{uso[2]}».", "Revisa los nombres en la hoja Extensiones.")
            return None
        ext = uso[1]
        alias = f["perfil_tipo"] in (ext["nombre"], ext["url"]) if f["perfil_tipo"] else False     # `extension[nacionalidad]` + perfil = CodigoPaises
        if any(f[k] for k in ("valueset", "fijo", "tipo", "destinos")) or (f["perfil_tipo"] and not alias):
            self.add(ERROR, "Elementos", r, f"«{ruta}» es una extensión: su tipo, ValueSet y valores se definen en la hoja Extensiones, no aquí.",
                     "Deja aquí solo cardinalidad y Must Support.")
        rec = self.perfiles[perfil]["recurso"] if perfil in self.perfiles else ""
        contextos = [c.split(".")[0].strip() for c in ext["contexto"].split(",") if c.strip()] if not ext["url"] else []
        if rec and contextos and "." not in ruta.split("extension[")[0] + "x" and rec not in contextos \
                and not {"Resource", "DomainResource", "Element"} & set(contextos):
            self.add(AVISO, "Elementos", r, f"La extensión «{ext['nombre']}» está pensada para {', '.join(contextos)}, y «{perfil}» es un {rec}.",
                     "Agrega el recurso en «Se usa en» de la hoja Extensiones, o usa otra extensión.")
        return uso

    def extensiones(self):
        nombres_sup = {f["nombre"]: f for f in self.ext.superiores.values()}
        vistos: dict[str, int] = {}
        usadas = set()
        for f in self.l.filas("Elementos"):
            uso = extensiones.resolver(f["ruta"], self.ext)
            if uso and uso[0] in ("simple", "compleja"):
                usadas.add(uso[1]["nombre"])
        for f in self.l.filas("Extensiones"):
            n, r, padre = f["nombre"], f["_fila"], f["parte_de"]
            if not n:
                self.add(ERROR, "Extensiones", r, "Falta el nombre de la extensión.")
                continue
            if not RE_NOMBRE.match(n):
                self.add(ERROR, "Extensiones", r, f"El nombre «{n}» no es válido para una extensión.",
                         f"Sin espacios ni símbolos y empezando con mayúscula. Por ejemplo: «{pascal(n) or 'MiExtension'}».")
            clave = f"{padre}/{n}" if padre else n
            if clave in vistos:
                self.add(ERROR, "Extensiones", r, f"«{n}» está repetida (también en la fila {vistos[clave]}).", "Cada extensión (o parte) debe tener un nombre único.")
            vistos[clave] = r
            if f["url"]:
                if padre:
                    self.add(ERROR, "Extensiones", r, f"«{n}» es una parte y tiene URL: una extensión ya definida en otro paquete no puede ser parte de otra.",
                             "Borra la URL o quita «Es parte de».")
                elif not RE_URL.match(f["url"]):
                    self.add(ERROR, "Extensiones", r, f"La URL «{f['url']}» de «{n}» no es válida.", "Empieza con http:// o https:// (o urn:).")
                elif any(f[k] for k in ("tipo", "valueset", "contexto", "descripcion")):
                    self.add(AVISO, "Extensiones", r, f"«{n}» ya existe en otro paquete: su tipo, ValueSet, contexto y descripción se ignoran.",
                             "Esos datos vienen de la extensión original.")
                if not padre and n not in usadas:
                    self.add(AVISO, "Extensiones", r, f"Ningún perfil usa la extensión «{n}».",
                             f"En la hoja Elementos agrega una fila con la ruta «extension[{extensiones.minuscula_inicial(n)}]».")
                continue
            if padre:
                if padre not in nombres_sup:
                    if padre in {x["nombre"] for x in self.l.filas("Extensiones")}:
                        self.add(ERROR, "Extensiones", r, f"«{padre}» es a su vez una parte; solo se admite un nivel de partes.", "Haz que «Es parte de» apunte a una extensión principal.")
                    else:
                        cerca = difflib.get_close_matches(padre, list(nombres_sup), n=1, cutoff=0.6)
                        self.add(ERROR, "Extensiones", r, f"La extensión «{padre}» (de la que «{n}» sería parte) no existe.",
                                 f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Crea primero la fila de la extensión principal.")
                if not f["tipo"]:
                    self.add(ERROR, "Extensiones", r, f"La parte «{n}» necesita «Tipo del valor».", f"Elige uno de: {', '.join(TIPOS_EXTENSION)}.")
                if f["contexto"]:
                    self.add(AVISO, "Extensiones", r, f"«Se usa en» no se usa en una parte («{n}»); se ignora.", "El contexto va en la fila de la extensión principal.")
                for campo, etiqueta in (("min", "mínimo"), ("max", "máximo")):
                    v = f[campo]
                    if v and not (v == "*" and campo == "max") and entero(v) is None:
                        self.add(ERROR, "Extensiones", r, f"El {etiqueta} «{v}» debe ser un número{' o *' if campo == 'max' else ''}.")
                if f["min"] and f["max"] and entero(f["min"]) is not None and maximo(f["max"]) is not None and maximo(f["max"]) < entero(f["min"]):
                    self.add(ERROR, "Extensiones", r, f"El mínimo ({f['min']}) es mayor que el máximo ({f['max']}).")
            else:
                partes = self.ext.partes_de(n)
                if partes and f["tipo"]:
                    self.add(ERROR, "Extensiones", r, f"«{n}» tiene partes, así que es una extensión compleja y no lleva «Tipo del valor».",
                             "Borra el tipo (cada parte lleva el suyo) o quita las partes.")
                if not partes and not f["tipo"]:
                    self.add(ERROR, "Extensiones", r, f"«{n}» necesita «Tipo del valor» (o partes, si es compleja).", f"Elige uno de: {', '.join(TIPOS_EXTENSION)}.")
                if not f["contexto"]:
                    self.add(AVISO, "Extensiones", r, f"«{n}» no dice dónde se puede usar.", "Indica en «Se usa en» el recurso (por ejemplo Patient).")
                if f["min"] or f["max"]:
                    self.add(AVISO, "Extensiones", r, f"Mín y Máx solo valen para partes; en «{n}» se ignoran.", "La cardinalidad se define al usar la extensión en la hoja Elementos.")
                if not f["descripcion"]:
                    self.add(SUGERENCIA, "Extensiones", r, f"«{n}» no tiene descripción.")
                if n not in usadas:
                    self.add(AVISO, "Extensiones", r, f"Ningún perfil usa la extensión «{n}».",
                             f"En la hoja Elementos agrega una fila con la ruta «extension[{extensiones.minuscula_inicial(n)}]».")
            for c in (x.strip() for x in f["contexto"].split(",") if x.strip()) if not padre else []:
                base = c.split(".")[0]
                if RE_URL.match(c):
                    continue                                    # contexto «extension»: la URL de otra extensión
                if base not in RECURSOS_R4 and base not in TIPOS_DATO and base not in ("Resource", "DomainResource", "Element", "Extension"):
                    cerca = difflib.get_close_matches(base, RECURSOS_R4 + TIPOS_DATO, n=1, cutoff=0.6)
                    self.add(ERROR, "Extensiones", r, f"«{c}» no es un recurso ni un tipo de dato de FHIR R4.",
                             f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Usa un recurso (Patient), un elemento (Patient.address) o un tipo de dato (Address.city).")
            if f["tipo"]:
                if not _tipo_valido(f["tipo"]) or extensiones.tipo_base(f["tipo"]) not in TIPOS_EXTENSION:
                    self.add(ERROR, "Extensiones", r, f"El tipo «{f['tipo']}» no está disponible para extensiones.",
                             f"Elige uno de: {', '.join(TIPOS_EXTENSION)} (Reference puede llevar el recurso: Reference(Patient)).")
                elif f["valueset"] and extensiones.tipo_base(f["tipo"]) not in ("code", "Coding", "CodeableConcept"):
                    self.add(AVISO, "Extensiones", r, f"Un ValueSet solo se puede usar con code, Coding o CodeableConcept; «{n}» es {f['tipo']}.")
            if f["valueset"] or f["fuerza"]:
                self._binding(f, "Extensiones")
        # los ids deben ser únicos entre perfiles y extensiones (ambos son StructureDefinition)
        ids: dict[str, str] = {}
        for hoja, nombres in (("Perfiles", [f for f in self.l.filas("Perfiles")]), ("Extensiones", [f for f in self.l.filas("Extensiones") if not f["parte_de"] and not f["url"]])):
            for f in nombres:
                if not f["nombre"]:
                    continue
                k = kebab(f["nombre"])
                if k in ids and ids[k] != hoja:
                    self.add(ERROR, hoja, f["_fila"], f"«{f['nombre']}» produce el mismo identificador («{k}») que un perfil o extensión.", "Usa un nombre distinto.")
                ids.setdefault(k, hoja)

    def valor_extensiones(self):
        """Hoja ValorExtensiones: reglas sobre los campos internos del valor de una extensión o de una parte."""
        por_nombre: dict[str, list[dict]] = {}
        for f in self.l.filas("Extensiones"):
            if f["nombre"]:
                por_nombre.setdefault(f["nombre"], []).append(f)
        vistos: dict[tuple[str, str], int] = {}
        for f in self.l.filas("ValorExtensiones"):
            r, n, ruta = f["_fila"], f["extension"], f["ruta"]
            if n not in por_nombre:
                cerca = difflib.get_close_matches(n, list(por_nombre), n=1, cutoff=0.6) if n else []
                self.add(ERROR, "ValorExtensiones", r, f"La extensión «{n}» no está en la hoja Extensiones." if n else "Falta la extensión.",
                         f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Elige una de la lista desplegable.")
                continue
            if not ruta:
                self.add(ERROR, "ValorExtensiones", r, "Falta el campo dentro del valor.", "Por ejemplo: system, value o coding.code.")
                continue
            fila_ext = por_nombre[n][0]
            tipo = extensiones.tipo_base(fila_ext["tipo"]) if fila_ext["tipo"] else ""
            if fila_ext["url"]:
                self.add(ERROR, "ValorExtensiones", r, f"«{n}» ya existe en otro paquete: no se puede cambiar su valor.", "Borra esta fila.")
                continue
            if ruta == "url":
                if (n, ruta) in vistos:
                    self.add(AVISO, "ValorExtensiones", r, f"«url» de «{n}» ya tiene reglas en la fila {vistos[(n, ruta)]}.", "Junta las reglas en una sola fila.")
                vistos[(n, ruta)] = r
                if f["min"] or f["max"] or f["valueset"] or f["fijo"]:
                    self.add(ERROR, "ValorExtensiones", r, "En «url» solo se puede marcar Must Support.", "Deja vacíos Mín, Máx, ValueSet y Valor fijo.")
                continue
            if not tipo:
                self.add(ERROR, "ValorExtensiones", r, f"«{n}» es una extensión compleja y no guarda un valor propio.",
                         "Pon la regla en una de sus partes: " + ", ".join(p["nombre"] for p in self.ext.partes_de(n)) + ".")
                continue
            if (n, ruta) in vistos:
                self.add(AVISO, "ValorExtensiones", r, f"«{ruta}» de «{n}» ya tiene reglas en la fila {vistos[(n, ruta)]}.", "Junta las reglas en una sola fila.")
            vistos[(n, ruta)] = r
            if ruta == "[x]":
                self._binding(f, "ValorExtensiones")
                if not any(f[k] for k in ("min", "max", "ms")):
                    self.add(AVISO, "ValorExtensiones", r, "La fila de «[x]» no define ninguna regla.", "Indica cardinalidad o Must Support.")
                continue
            rutas = elementos.rutas_de_recurso(tipo) if elementos.hay_datos() else {}
            if elementos.hay_datos() and not rutas:
                self.add(ERROR, "ValorExtensiones", r, f"El valor de «{n}» es de tipo {fila_ext['tipo']}, que no tiene campos internos.",
                         "Estas reglas sirven para tipos con campos: Identifier, CodeableConcept, Coding, Quantity, Reference, Period...")
                continue
            msg = elementos.comprobar_ruta(ruta, rutas)
            if msg:
                self.add(ERROR, "ValorExtensiones", r, f"«{ruta}» no es un campo de {tipo}.", msg)
            mn, mx = f["min"], f["max"]
            if mn and entero(mn) is None:
                self.add(ERROR, "ValorExtensiones", r, f"El mínimo «{mn}» debe ser un número entero.")
            elif mx and mx != "*" and entero(mx) is None:
                self.add(ERROR, "ValorExtensiones", r, f"El máximo «{mx}» debe ser un número o *.")
            elif mn and mx and maximo(mx) < entero(mn):
                self.add(ERROR, "ValorExtensiones", r, f"El mínimo ({mn}) es mayor que el máximo ({mx}).")
            else:
                lim = rutas.get(_normalizar_indices(ruta))
                if lim and mn and entero(mn) is not None and entero(mn) < int(lim[0]):
                    self.add(ERROR, "ValorExtensiones", r, f"«{ruta}» exige mínimo {lim[0]} en {tipo}, pero aquí pusiste {mn}.", "Un campo no puede ser más permisivo que su tipo.")
                if lim and mx and mx != "*" and entero(mx) is not None and maximo(str(lim[1])) is not None and maximo(str(lim[1])) < entero(mx):
                    self.add(ERROR, "ValorExtensiones", r, f"«{ruta}» permite como máximo {lim[1]} en {tipo}, pero aquí pusiste {mx}.", "Un campo no puede ser más permisivo que su tipo.")
            self._binding(f, "ValorExtensiones")
            self._fijo(f, "ValorExtensiones")
            if not any(f[k] for k in ("min", "max", "ms", "valueset", "fijo")):
                self.add(AVISO, "ValorExtensiones", r, f"La fila de «{ruta}» no define ninguna regla.", "Indica cardinalidad, Must Support, ValueSet o valor fijo.")

    def slices(self):
        grupos: dict[tuple[str, str], list[dict]] = {}
        vistos: dict[tuple[str, str, str], int] = {}
        for f in self.l.filas("Slices"):
            r, perfil, el, sl = f["_fila"], f["perfil"], f["elemento"], f["slice"]
            if not perfil or perfil not in self.perfiles:
                cerca = difflib.get_close_matches(perfil, list(self.perfiles), n=1, cutoff=0.6) if perfil else []
                self.add(ERROR, "Slices", r, f"El perfil «{perfil}» no está en la hoja Perfiles." if perfil else "Falta el perfil.",
                         f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Elige uno de la lista desplegable.")
                continue
            if not el:
                self.add(ERROR, "Slices", r, "Falta el elemento que se divide.")
                continue
            falso = {"ruta": el, "_fila": r}
            self._ruta(falso, "Slices", perfil)
            self._ruta_existe(falso, "Slices", perfil)
            if el.endswith("extension"):
                self.add(ERROR, "Slices", r, "Las extensiones no se dividen aquí.", "Defínelas en la hoja Extensiones y úsalas con «extension[nombre]» en Elementos.")
                continue
            if not sl:
                self.add(ERROR, "Slices", r, f"Falta el nombre del slice de «{el}».", "Una palabra sin espacios, por ejemplo telefono.")
                continue
            if not re.match(r"^[A-Za-z][A-Za-z0-9]*$", sl):
                self.add(ERROR, "Slices", r, f"El nombre de slice «{sl}» no es válido.", "Usa solo letras y números, sin espacios (por ejemplo telefono).")
            if (perfil, el, sl) in vistos:
                self.add(ERROR, "Slices", r, f"El slice «{sl}» de «{el}» está repetido (fila {vistos[(perfil, el, sl)]}).")
            vistos[(perfil, el, sl)] = r
            if f"{el}[{sl}]" in self._rutas_de(perfil):
                self.add(ERROR, "Slices", r, f"El slice «{sl}» ya existe en el padre de «{perfil}».",
                         f"No lo vuelvas a crear: restríngelo en la hoja Elementos con la ruta «{el}[{sl}]».")
            mn, mx = f["min"], f["max"]
            if mn and entero(mn) is None:
                self.add(ERROR, "Slices", r, f"El mínimo «{mn}» debe ser un número entero.")
            if mx and mx != "*" and entero(mx) is None:
                self.add(ERROR, "Slices", r, f"El máximo «{mx}» debe ser un número o *.")
            if mn and mx and entero(mn) is not None and maximo(mx) is not None and maximo(mx) < entero(mn):
                self.add(ERROR, "Slices", r, f"El mínimo ({mn}) es mayor que el máximo ({mx}).")
            if f["discriminador"] and f["discriminador"] not in DISCRIMINADORES:
                self.add(ERROR, "Slices", r, f"«{f['discriminador']}» no es una forma de distinguir válida.", f"Elige una de: {', '.join(DISCRIMINADORES)}.")
            if f["reglas"] and f["reglas"] not in REGLAS_SLICING:
                self.add(ERROR, "Slices", r, f"Regla de slicing «{f['reglas']}» no válida.", f"Elige una de: {', '.join(REGLAS_SLICING)}.")
            self._fijo(f, "Slices")
            grupos.setdefault((perfil, el), []).append(f)
        for (perfil, el), filas in grupos.items():
            rutas = self._rutas_de(perfil)
            for campo, etiqueta in (("discriminador", "Se distingue por"), ("disc_ruta", "Campo que lo distingue"), ("reglas", "Reglas de slicing")):
                distintos = {f[campo] for f in filas if f[campo]}
                if len(distintos) > 1:
                    self.add(ERROR, "Slices", filas[0]["_fila"], f"«{etiqueta}» de «{el}» tiene valores distintos en sus filas: {', '.join(sorted(distintos))}.",
                             "Se define una sola vez por elemento: déjalo solo en la primera fila.")
            tipo = next((f["discriminador"] for f in filas if f["discriminador"]), "")
            ruta = next((f["disc_ruta"] for f in filas if f["disc_ruta"]), "")
            heredado = any(k.startswith(f"{el}[") for k in rutas) or any(
                any(g["elemento"] == el and g["discriminador"] for g in self.l.filas("Slices") if g["perfil"] == p)
                for p in self._cadena_libro(perfil)[1:])
            if not tipo and not heredado:
                self.add(ERROR, "Slices", filas[0]["_fila"], f"No dijiste cómo se distinguen los slices de «{el}».",
                         "En la primera fila completa «Se distingue por» (por ejemplo value) y «Campo que lo distingue» (por ejemplo system).")
            elif tipo and heredado:
                self.add(AVISO, "Slices", filas[0]["_fila"], f"«{el}» ya está dividido en el padre de «{perfil}»; aquí lo vuelves a definir.",
                         "Normalmente basta con agregar slices y dejar «Se distingue por» vacío.")
            if tipo and not ruta:
                self.add(ERROR, "Slices", filas[0]["_fila"], f"Falta el campo que distingue los slices de «{el}».", "Por ejemplo system, o $this si es el elemento mismo.")
            if ruta and ruta != "$this" and re.match(r"^[A-Za-z][A-Za-z0-9.\[\]]*$", ruta) and elementos.hay_datos() and rutas:
                pista = elementos.comprobar_ruta(f"{el}.{ruta}", rutas)
                if pista:
                    self.add(AVISO, "Slices", filas[0]["_fila"], f"«{ruta}» no parece un campo de «{el}».", pista)
            for f in filas:
                if f["fijo"] and not ruta:
                    self.add(ERROR, "Slices", f["_fila"], f"El valor «{f['fijo']}» necesita saber en qué campo va.",
                             "Completa «Campo que lo distingue» (o $this si es el elemento mismo).")
                tiene_regla = any(e["ruta"].startswith(f"{el}[{f['slice']}]") for p in self._cadena_libro(perfil) for e in self.reglas_por_perfil.get(p, []))
                if (tipo in ("value", "pattern")) and not f["fijo"] and not tiene_regla:
                    self.add(AVISO, "Slices", f["_fila"], f"El slice «{f['slice']}» no tiene qué lo distinga de los demás.",
                             f"Completa «Valor que lo distingue» o agrega reglas en Elementos para «{el}[{f['slice']}]».")

    def _es_perfil_de_tipo(self, nombre: str) -> bool:
        if nombre in TIPOS_DATO:
            return True
        if nombre in self.perfiles:
            return self.perfiles[nombre]["recurso"] in TIPOS_DATO
        return bool(self.cat and nombre in self.cat.sd and self.cat.sd[nombre].get("kind") != "resource")

    def _rutas_de(self, perfil: str) -> dict:
        """Rutas válidas para un perfil o recurso (vacío si no se puede saber)."""
        if perfil in self.perfiles:
            recurso, raiz = self.perfiles[perfil]["recurso"], self._raiz_clcore(perfil)
        elif self.cat and perfil in self.cat.sd:
            recurso, raiz = self.cat.sd[perfil]["type"], self.cat.sd[perfil]
        else:
            recurso, raiz = perfil, None
        return elementos.rutas_con_perfil(recurso, (raiz or {}).get("rutas")) if recurso in RECURSOS_R4 or recurso in TIPOS_DATO else {}

    def _ruta_existe(self, f, hoja, perfil):
        if not elementos.hay_datos() or not RE_RUTA.match(f["ruta"]) or f["ruta"][:1].isupper():
            return
        pista = elementos.comprobar_ruta(f["ruta"], self._rutas_de(perfil))
        if pista:
            self.add(ERROR, hoja, f["_fila"], f"«{f['ruta']}» no es un elemento de «{perfil}».", pista)

    def _ruta(self, f, hoja, perfil_o_inst=""):
        ruta, r = f["ruta"], f["_fila"]
        if ruta[:1].isupper():
            if "." in ruta:
                self.add(ERROR, hoja, r, f"La ruta «{ruta}» empieza con el nombre del recurso.", f"Escríbela sin él: «{ruta.split('.', 1)[1]}».")
            else:
                self.add(ERROR, hoja, r, f"«{ruta}» parece un tipo o un recurso, no un elemento.",
                         "Las rutas son nombres de elemento en minúscula inicial (name, name.family, value[x]). Los tipos van en la columna «Solo tipo».")
        elif not RE_RUTA.match(ruta):
            self.add(ERROR, hoja, r, f"La ruta «{ruta}» no es válida.", "Usa nombres de elemento separados por puntos, por ejemplo name.family o value[x]. Sin espacios.")

    def _cardinalidad(self, f):
        r, mn, mx = f["_fila"], f["min"], f["max"]
        if mn and entero(mn) is None:
            self.add(ERROR, "Elementos", r, f"El mínimo «{mn}» debe ser un número entero (0, 1, 2...).")
            mn = ""
        if mx and mx != "*" and entero(mx) is None:
            self.add(ERROR, "Elementos", r, f"El máximo «{mx}» debe ser un número o *.")
            mx = ""
        if mn and mx and maximo(mx) < entero(mn):
            self.add(ERROR, "Elementos", r, f"El mínimo ({mn}) es mayor que el máximo ({mx}).", "Revisa los dos números.")
            return
        if mx == "0" and f["ms"] and es_si(f["ms"]):
            self.add(AVISO, "Elementos", r, "Marcaste Must Support en un elemento prohibido (máximo 0).", "Quita una de las dos cosas.")
        if (mn or mx) and f["perfil"] in self.perfiles:
            p = self._cardinalidad_del_padre(f["perfil"], f["ruta"])
            if p:
                pmin, pmax, de = p
                if mn and pmin is not None and entero(mn) < pmin:
                    self.add(ERROR, "Elementos", r, f"«{f['ruta']}» exige mínimo {pmin} en «{de}», pero aquí pusiste {mn}. Un perfil no puede ser más permisivo que su padre.",
                             f"Usa {pmin} o más.")
                if mx and pmax is not None and maximo(mx) > pmax:
                    self.add(ERROR, "Elementos", r, f"«{f['ruta']}» permite como máximo {int(pmax) if pmax != float('inf') else '*'} en «{de}», pero aquí pusiste {mx}. Un perfil no puede ser más permisivo que su padre.",
                             "Usa un máximo igual o menor.")

    def _binding(self, f, hoja="Elementos"):
        r, vs = f["_fila"], f["valueset"]
        if f["fuerza"] and f["fuerza"] not in FUERZAS:
            self.add(ERROR, hoja, r, f"La fuerza «{f['fuerza']}» no es válida.", f"Elige una de: {', '.join(FUERZAS)}.")
        if f["fuerza"] and not vs:
            self.add(AVISO, hoja, r, "Indicaste una fuerza pero ningún ValueSet.", "Completa «ValueSet permitido» o borra la fuerza.")
        if vs:
            if not f["fuerza"]:
                self.add(SUGERENCIA, hoja, r, f"No indicaste la fuerza para «{vs}»; se usará «required» (solo se aceptan esos valores).")
            if vs in self.vs or RE_URL.match(vs):
                return
            if self.cat and (vs in self.cat.vs):
                return
            cerca = difflib.get_close_matches(vs, list(self.vs) + (list(self.cat.vs) if self.cat else []), n=1, cutoff=0.6)
            if not self.cat and not cerca:
                self.add(AVISO, hoja, r, f"No pude comprobar el ValueSet «{vs}» (no está en tu hoja ValueSets y no tengo el catálogo de CL Core).",
                         "Si es de CL Core, genera el catálogo con `python cl_ig.py catalogo`.")
            else:
                self.add(ERROR, hoja, r, f"El ValueSet «{vs}» no existe.", f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Defínelo en la hoja ValueSets o usa uno de CL Core.")

    def _fijo(self, f, hoja="Elementos"):
        r = f["_fila"]
        if not f["fijo"]:
            if f["fijo_tipo"] or f["fijo_sistema"]:
                self.add(AVISO, hoja, r, "Indicaste tipo o sistema del valor fijo pero no el valor.")
            return
        if not f["fijo_tipo"]:
            self.add(ERROR, hoja, r, f"El valor fijo «{f['fijo']}» necesita «Tipo del valor fijo».", f"Elige uno de: {', '.join(TIPOS_FIJO)}.")
            return
        if f["fijo_tipo"] not in TIPOS_FIJO:
            self.add(ERROR, hoja, r, f"Tipo de valor fijo «{f['fijo_tipo']}» no válido.", f"Elige uno de: {', '.join(TIPOS_FIJO)}.")
            return
        self._valor_por_tipo(hoja, r, f["fijo_tipo"], f["fijo"], f["fijo_sistema"], "", "")
        if hoja == "Elementos":
            self._fijo_compatible(f, hoja)

    # ------------------------------------------------------------ Valor genérico
    def _valor_por_tipo(self, hoja, r, tipo, valor, sistema, unidad, texto):
        if tipo == "número":
            if "," in valor and "." not in valor:
                self.add(ERROR, hoja, r, f"«{valor}» usa coma decimal.", f"Escribe «{valor.replace(',', '.')}» (FHIR usa punto).")
            else:
                try:
                    float(valor)
                except ValueError:
                    self.add(ERROR, hoja, r, f"«{valor}» no es un número.")
        elif tipo == "booleano":
            if valor.lower() not in SI | NO:
                self.add(ERROR, hoja, r, f"«{valor}» no es un valor Sí/No.", "Escribe Sí o No.")
        elif tipo == "fecha":
            self._fecha(hoja, r, valor)
        elif tipo == "fecha y hora":
            if RE_FECHA_HORA.match(valor):
                self._fecha(hoja, r, valor[:10])
            elif RE_FECHA.match(valor):
                self.add(ERROR, hoja, r, f"«{valor}» no tiene hora.", "Usa «fecha» si no hay hora, o escribe AAAA-MM-DDThh:mm:ss-03:00.")
            else:
                self._fecha_mala(hoja, r, valor, con_hora=True)
        elif tipo == "código simple":
            if " " in valor.strip():
                self.add(AVISO, hoja, r, f"El código «{valor}» tiene espacios.", "Los códigos suelen ser una sola palabra (se usarán comillas).")
        elif tipo == "código con sistema":
            self._codigo_con_sistema(hoja, r, valor, sistema, texto)
        elif tipo == "cantidad":
            try:
                float(valor)
            except ValueError:
                self.add(ERROR, hoja, r, f"«{valor}» no es un número" + (" (usa punto, no coma)." if "," in valor else "."))
            if not unidad:
                self.add(ERROR, hoja, r, "Una cantidad necesita unidad (UCUM).", "Ej.: mm[Hg], kg, %, /min, mg/dL.")
            elif not RE_UCUM.match(unidad):
                self.add(ERROR, hoja, r, f"La unidad «{unidad}» no es un código UCUM válido.", "Sin espacios. Ej.: mm[Hg], kg, /min.")
            if unidad and not texto:
                self.add(SUGERENCIA, hoja, r, "Agrega «Texto visible» para la unidad (ej. «mmHg»).")

    def _fecha(self, hoja, r, valor):
        if not RE_FECHA.match(valor):
            return self._fecha_mala(hoja, r, valor)
        try:
            date.fromisoformat(valor)
        except ValueError:
            self.add(ERROR, hoja, r, f"La fecha «{valor}» no existe en el calendario.", "Revisa el día y el mes.")

    def _fecha_mala(self, hoja, r, valor, con_hora=False):
        m = RE_FECHA_LATINA.match(valor)
        if m:
            d, mes, a = m.groups()
            self.add(ERROR, hoja, r, f"La fecha «{valor}» está en formato día/mes/año.", f"Escríbela como {a}-{int(mes):02d}-{int(d):02d} (año-mes-día).")
        else:
            self.add(ERROR, hoja, r, f"«{valor}» no es una fecha válida.",
                     "Usa AAAA-MM-DDThh:mm:ss-03:00 (con zona horaria)." if con_hora else "Usa AAAA-MM-DD, por ejemplo 2026-03-15.")

    def _codigo_con_sistema(self, hoja, r, codigo, sistema, texto=""):
        if not sistema:
            self.add(ERROR, hoja, r, f"El código «{codigo}» necesita un sistema.", "Indica LOINC, SNOMED, un CodeSystem de tu libro o una URL.")
            return
        clase, url = url_sistema(sistema, set(self.cs))
        if texto and url in (SISTEMAS_CONOCIDOS["LOINC"], SISTEMAS_CONOCIDOS["SNOMED"]):
            self.add(AVISO, hoja, r, f"El texto «{texto}» de un código {sistema} debe ser idéntico al nombre oficial del código.",
                     "El IG Publisher lo compara con el nombre oficial y lo marca como error si difiere. Déjalo vacío (y pon la etiqueta legible "
                     "en el elemento «.text», por ejemplo code.text) o cópialo exactamente del sitio oficial.")
        if clase == "desconocido":
            cerca = difflib.get_close_matches(sistema, list(self.cs) + ["LOINC", "SNOMED"], n=1, cutoff=0.6)
            self.add(ERROR, hoja, r, f"No reconozco el sistema «{sistema}».",
                     f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Usa LOINC, SNOMED, un CodeSystem de tu hoja CodeSystems o una URL.")
        elif clase == "libro":
            if codigo not in self.conceptos.get(sistema, {}):
                cerca = difflib.get_close_matches(codigo, list(self.conceptos.get(sistema, {})), n=1, cutoff=0.6)
                self.add(ERROR, hoja, r, f"El código «{codigo}» no existe en «{sistema}».",
                         f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Agrégalo en la hoja Conceptos o usa otro código.")
        elif self.cat and url in self.cat.cs_by_url:
            if self.cat.concept_display(url, codigo) is None:
                self.add(ERROR, hoja, r, f"El código «{codigo}» no existe en el sistema de CL Core «{sistema}».")

    # --------------------------------------------------------------- Instancias
    def instancias(self):
        vistos: dict[str, int] = {}
        for f in self.l.filas("Instancias"):
            n, r = f["nombre"], f["_fila"]
            if not n:
                self.add(ERROR, "Instancias", r, "Falta el nombre del ejemplo.")
                continue
            if not RE_NOMBRE.match(n):
                self.add(ERROR, "Instancias", r, f"El nombre «{n}» no es válido.", f"Sin espacios ni símbolos y empezando con mayúscula. Por ejemplo: «{pascal(n) or 'Ejemplo1'}».")
            if n in vistos:
                self.add(ERROR, "Instancias", r, f"El ejemplo «{n}» está repetido (también en la fila {vistos[n]}).", "Cada ejemplo debe tener un nombre único.")
            vistos[n] = r
            p = f["perfil"]
            if not p:
                self.add(ERROR, "Instancias", r, f"«{n}» no tiene perfil o recurso.")
            elif self._es_perfil_de_tipo(p):
                self.add(ERROR, "Instancias", r, f"«{n}» no puede ser un ejemplo de «{p}»: es un tipo de dato, no un recurso.",
                         "Los ejemplos son recursos completos. Úsalo dentro de un ejemplo de un recurso (por ejemplo, en la dirección de un Patient).")
            elif p not in self.perfiles and p not in RECURSOS_R4 and not (self.cat and p in self.cat.sd) and not RE_URL.match(p) \
                    and (self.cat or not self.usa_clcore()):
                cerca = difflib.get_close_matches(p, list(self.perfiles) + RECURSOS_R4, n=1, cutoff=0.6)
                self.add(ERROR, "Instancias", r, f"El perfil «{p}» de «{n}» no existe.", f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Elige uno de la lista.")
            if f["uso"] and f["uso"] not in USOS:
                self.add(ERROR, "Instancias", r, f"Uso «{f['uso']}» no válido.", f"Elige uno de: {', '.join(USOS)}.")
            if not f["descripcion"]:
                self.add(SUGERENCIA, "Instancias", r, f"«{n}» no tiene descripción.")

    def _codigo_sin_sistema(self):
        """Un `...coding.code` sin su `...coding.system` no puede estar en ningún ValueSet: el Publisher lo rechaza (codes = null#01)."""
        rutas: dict[str, set[str]] = {}
        for f in self.l.filas("Valores"):
            rutas.setdefault(f["instancia"], set()).add(_normalizar_indices(f["ruta"]))
        for f in self.l.filas("Valores"):
            m = re.match(r"^(.*\.coding)\.code$", _normalizar_indices(f["ruta"]))
            if m and f["tipo"] in ("código simple", "texto", "") and m[1] + ".system" not in rutas[f["instancia"]]:
                self.add(AVISO, "Valores", f["_fila"], f"«{f['ruta']}» tiene código pero no sistema: un código sin sistema no calza con ningún ValueSet.",
                         f"Agrega una fila «{f['ruta'].rsplit('.', 1)[0]}.system» con la URL del CodeSystem (o usa «código con sistema» en «{f['ruta'].rsplit('.', 1)[0]}»).")

    def valores(self):
        self._codigo_sin_sistema()
        por_inst: dict[str, list[dict]] = {}
        for f in self.l.filas("Valores"):
            r, inst = f["_fila"], f["instancia"]
            if inst not in self.inst:
                cerca = difflib.get_close_matches(inst, list(self.inst), n=1, cutoff=0.6) if inst else []
                self.add(ERROR, "Valores", r, f"El ejemplo «{inst}» no está en la hoja Instancias." if inst else "Falta el ejemplo.",
                         f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Elige uno de la lista desplegable.")
                continue
            por_inst.setdefault(inst, []).append(f)
            if not f["ruta"]:
                self.add(ERROR, "Valores", r, "Falta el elemento (ruta).")
                continue
            self._ruta(f, "Valores")
            self._ruta_existe(f, "Valores", self.inst[inst]["perfil"])
            uso = extensiones.resolver(f["ruta"], self.ext)
            esperado = ""
            if uso and uso[0] == "compleja":
                self.add(ERROR, "Valores", r, f"«{f['ruta']}» es una extensión compleja: no lleva un valor directo.",
                         "Escribe una fila por parte: " + ", ".join(f"{f['ruta']}.extension[{extensiones.slice_de(p)}]" for p in self.ext.partes_de(uso[1]["nombre"])) + ".")
                continue
            if uso and uso[0] == "parte_desconocida":
                self.add(ERROR, "Valores", r, f"La extensión «{uso[1]['nombre']}» no tiene la parte «{uso[2]}».",
                         "Partes: " + ", ".join(extensiones.slice_de(p) for p in self.ext.partes_de(uso[1]["nombre"])) + ".")
                continue
            if uso:
                esperado = elementos.TIPO_DE_DATO.get(extensiones.tipo_base(uso[1]["tipo"]), "")
                if not f["tipo"] and esperado:
                    f["tipo"] = esperado
                    self.add(SUGERENCIA, "Valores", r, f"Tipo de dato «{esperado}» deducido de la extensión «{uso[1]['nombre']}».")
                elif f["tipo"] and esperado and f["tipo"] != esperado:
                    self.add(AVISO, "Valores", r, f"La extensión «{uso[1]['nombre']}» guarda un valor de tipo {uso[1]['tipo']} ({esperado}) y aquí indicaste «{f['tipo']}».")
            if not f["tipo"] and elementos.hay_datos():
                deducido = elementos.tipo_de_dato(f["ruta"], self._rutas_de(self.inst[inst]["perfil"]))
                if deducido:
                    f["tipo"] = deducido
                    self.add(SUGERENCIA, "Valores", r, f"Tipo de dato «{deducido}» deducido de «{f['ruta']}».", "Puedes escribirlo tú si prefieres otro.")
            tipo, valor = f["tipo"], f["valor"]
            if tipo not in TIPOS_VALOR:
                self.add(ERROR, "Valores", r, f"Tipo de dato «{tipo}» no válido." if tipo else f"No se puede deducir el tipo de dato de «{f['ruta']}».", f"Elige uno de: {', '.join(TIPOS_VALOR)}.")
                continue
            if not valor:
                self.add(ERROR, "Valores", r, f"Falta el valor de «{f['ruta']}».")
                continue
            if tipo in ("referencia", "recurso incluido"):
                if valor not in self.inst and (tipo == "recurso incluido" or "/" not in valor):
                    cerca = difflib.get_close_matches(valor, list(self.inst), n=1, cutoff=0.6)
                    self.add(ERROR, "Valores", r, f"{'La referencia' if tipo == 'referencia' else 'El recurso incluido'} «{valor}» no corresponde a ningún ejemplo.",
                             f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Crea ese ejemplo en la hoja Instancias.")
            else:
                self._valor_por_tipo("Valores", r, tipo, valor, f["sistema"], f["unidad"], f["texto"])
        for nombre, filas in por_inst.items():
            self._contra_perfil(nombre, filas)
            self._slices(nombre, filas)
            self._bindings_clcore(nombre, filas)
        for nombre, f in self.inst.items():
            if nombre not in por_inst:
                self.add(AVISO, "Instancias", f["_fila"], f"«{nombre}» no tiene ningún dato en la hoja Valores.", "Agrega al menos los elementos obligatorios.")

    def _raiz_clcore(self, perfil: str):
        """Perfil de CL Core del que parte (directa o indirectamente) un perfil, o None."""
        cadena = self._cadena_libro(perfil)
        ultimo = self.perfiles[cadena[-1]]["padre"] if cadena else perfil
        return self.cat.sd.get(ultimo) if self.cat and ultimo else None

    def _slices(self, nombre: str, filas: list[dict]):
        """Avisa si el ejemplo usa un slice o una extensión (`name[NombreOficial]`, `extension[x]`) que su perfil no define."""
        perfil = self.inst[nombre]["perfil"]
        raiz, cadena = self._raiz_clcore(perfil), self._cadena_con_tipos(perfil)
        if raiz is None and not cadena:
            return
        propios = {s for e in raiz["elements"] for s in re.findall(r":([A-Za-z0-9]+)", e["id"])} if raiz else set()
        declaradas = set()
        for p in cadena:
            propios |= {g["slice"] for g in self.l.filas("Slices") if g["perfil"] == p}
            for e in self.reglas_por_perfil.get(p, []):
                uso = extensiones.resolver(e["ruta"], self.ext)
                if uso and uso[0] in ("simple", "compleja"):
                    declaradas.add(uso[1]["nombre"])
                    propios.add(extensiones.minuscula_inicial(uso[1]["nombre"]))
        for d in declaradas:
            propios |= {extensiones.slice_de(x) for x in self.ext.partes_de(d)}
        for f in filas:
            for s in re.findall(r"\[([A-Za-z][A-Za-z0-9]*)\]", f["ruta"].replace("[x]", "")):
                if s in propios or s in SLICES_DE_FHIR:
                    continue
                if s in self.ext.superiores:
                    self.add(ERROR, "Valores", f["_fila"], f"El perfil «{perfil}» no usa la extensión «{self.ext.superiores[s]['nombre']}» que pide «{f['ruta']}».",
                             f"En la hoja Elementos agrega una fila del perfil «{perfil}» con la ruta «extension[{s}]».")
                    continue
                sugerencia = ""
                if raiz:
                    donde = sorted(sd["id"] for sd in self.cat.sd.values() if any(f":{s}" in e["id"] for e in sd["elements"]))
                    sugerencia = (f"«{s}» existe en: {', '.join(donde)}." if donde else "") + \
                                 (f" En «{raiz['id']}» usa índices numéricos (por ejemplo {f['ruta'].replace('[' + s + ']', '[0]')}).")
                de = f"«{raiz['id']}»" if raiz else f"«{perfil}»"
                self.add(AVISO, "Valores", f["_fila"], f"El perfil {de} no define el slice «{s}» que usa «{f['ruta']}».",
                         sugerencia.strip() or "Defínelo en la hoja Slices o usa un índice numérico.")

    def _bindings_clcore(self, nombre: str, filas: list[dict]):
        """Compara los códigos del ejemplo con el ValueSet que el perfil de CL Core exige en ese elemento."""
        raiz = self._raiz_clcore(self.inst[nombre]["perfil"])
        if raiz is None:
            return
        reglas = {e["id"]: e for e in raiz["elements"] if e.get("binding")}
        for f in filas:
            if f["tipo"] != "código con sistema" or not f["sistema"] or not f["valor"]:
                continue
            e = reglas.get(f"{raiz['type']}.{sin_indices(f['ruta'])}")
            vs = self.cat.vs_by_url.get(e["binding"].split("|")[0]) if e else None
            clase, url = url_sistema(f["sistema"], set(self.cs))
            if not vs or clase not in ("url", "conocido") or vs.get("valueSets") or not vs.get("systems"):
                continue                                   # no puedo decidirlo con el catálogo
            if url in vs["systems"] and (url not in (vs.get("codes") or {}) or f["valor"] in vs["codes"][url]):
                continue
            nivel = ERROR if e["strength"] == "required" else AVISO
            validos = []
            for s in vs["systems"]:
                conceptos = (self.cat.cs_by_url.get(s) or {}).get("concepts") or {}
                validos.append(f"{s} (" + ", ".join(f"{c}: {t}" for c, t in list(conceptos.items())[:8]) + ")" if conceptos else s)
            self.add(nivel, "Valores", f["_fila"],
                     f"«{f['ruta']}» debe usar códigos del ValueSet «{vs['id']}» ({'obligatorio' if nivel == ERROR else 'recomendado'}) "
                     f"según «{raiz['id']}», y «{f['sistema']}#{f['valor']}» no está en él.",
                     "Usa: " + "; ".join(validos) + ".")

    def _contra_perfil(self, nombre: str, filas: list[dict]):
        """Compara el ejemplo con los valores fijos y los elementos obligatorios de su perfil."""
        perfil = self.inst[nombre]["perfil"]
        rutas = {sin_indices(f["ruta"]) for f in filas}
        primeros = {primer_segmento(f["ruta"]) for f in filas}
        crudas = {_normalizar_indices(f["ruta"]) for f in filas}

        def esta(ruta_regla: str) -> bool:
            return any(c == ruta_regla or c.startswith(ruta_regla + ".") for c in crudas)
        cadena = self._cadena_libro(perfil)
        for p in cadena:
            for e in self.reglas_por_perfil.get(p, []):
                if e["fijo"]:
                    for f in filas:
                        if f["ruta"] == e["ruta"] and f["valor"] != e["fijo"]:
                            self.add(ERROR, "Valores", f["_fila"], f"«{e['ruta']}» tiene valor fijo «{e['fijo']}» en el perfil «{p}», pero el ejemplo «{nombre}» usa «{f['valor']}».",
                                     "Usa el valor del perfil o cambia el perfil.")
                if e["min"] and (entero(e["min"]) or 0) >= 1 and "." not in sin_indices(e["ruta"]) and e["ruta"] not in rutas | primeros \
                        and not (("[" in e["ruta"]) and esta(e["ruta"])) and not e["fijo"]:
                    self.add(AVISO, "Instancias", self.inst[nombre]["_fila"], f"El perfil «{p}» exige «{e['ruta']}» pero el ejemplo «{nombre}» no lo tiene.",
                             "Agrégalo en la hoja Valores.")
        for p in cadena:
            for g in self.l.filas("Slices"):
                if g["perfil"] == p and g["min"] and (entero(g["min"]) or 0) >= 1 and not esta(f"{g['elemento']}[{g['slice']}]"):
                    self.add(AVISO, "Instancias", self.inst[nombre]["_fila"],
                             f"El perfil «{p}» exige al menos un «{g['elemento']}[{g['slice']}]» y el ejemplo «{nombre}» no lo tiene.", "Agrégalo en la hoja Valores.")
        base = self.perfiles[perfil]["recurso"] if perfil in self.perfiles else perfil
        for el in MINIMOS_R4.get(base, []):
            if el not in primeros and not any(sin_indices(r).startswith(el) for r in rutas):
                self.add(AVISO, "Instancias", self.inst[nombre]["_fila"], f"FHIR exige «{el}» en un {base}, y el ejemplo «{nombre}» no lo tiene.", "Agrégalo en la hoja Valores.")

    # ---------------------------------------------------------- Terminología
    def terminologia(self):
        for f in self.l.filas("CodeSystems"):
            n, r = f["nombre"], f["_fila"]
            if not RE_NOMBRE.match(n):
                self.add(ERROR, "CodeSystems", r, f"El nombre «{n}» no es válido.", f"Sin espacios ni símbolos y empezando con mayúscula. Por ejemplo: «{pascal(n) or 'CSMio'}».")
            if f["contenido"] and f["contenido"] not in CONTENIDOS:
                self.add(ERROR, "CodeSystems", r, f"Contenido «{f['contenido']}» no válido.", f"Elige uno de: {', '.join(CONTENIDOS)}.")
            if (f["contenido"] or "complete") == "complete" and not self.conceptos.get(n):
                self.add(ERROR, "CodeSystems", r, f"«{n}» dice tener todos sus códigos (complete) pero no tiene ninguno en la hoja Conceptos.",
                         "Agrega sus códigos o cambia «Contenido» a not-present.")
            if not f["descripcion"]:
                self._falta_descripcion("CodeSystems", r, n)
        nombres = [f["nombre"] for f in self.l.filas("CodeSystems")]
        for n in {x for x in nombres if nombres.count(x) > 1}:
            self.add(ERROR, "CodeSystems", None, f"El CodeSystem «{n}» está repetido.")
        vistos: dict[tuple[str, str], int] = {}
        for f in self.l.filas("Conceptos"):
            cs, cod, r = f["codesystem"], f["codigo"], f["_fila"]
            if cs not in self.cs:
                cerca = difflib.get_close_matches(cs, list(self.cs), n=1, cutoff=0.6) if cs else []
                self.add(ERROR, "Conceptos", r, f"El CodeSystem «{cs}» no está en la hoja CodeSystems." if cs else "Falta el CodeSystem.",
                         f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Elige uno de la lista desplegable.")
                continue
            if not cod:
                self.add(ERROR, "Conceptos", r, "Falta el código.")
                continue
            if not f["texto"]:
                self.add(ERROR, "Conceptos", r, f"El código «{cod}» no tiene texto.", "Escribe cómo se muestra.")
            if (cs, cod) in vistos:
                otro = next((x for x in self.l.filas("Conceptos") if x["_fila"] == vistos[(cs, cod)]), None)
                distinto = otro and otro["texto"] != f["texto"]
                self.add(ERROR, "Conceptos", r, f"El código «{cod}» ya existe en «{cs}» (fila {vistos[(cs, cod)]})" +
                         (f" con otro significado («{otro['texto']}» y «{f['texto']}»)." if distinto else "."),
                         "Un código no puede significar dos cosas en un mismo sistema. Crea un CodeSystem por pregunta o usa códigos compuestos (por ejemplo P12-3).")
            vistos[(cs, cod)] = r
            if not RE_CODIGO_SEGURO.match(cod):
                self.add(AVISO, "Conceptos", r, f"El código «{cod}» tiene espacios o símbolos.", "Se escribirá entre comillas; conviene usar letras, números y guiones.")
        self._valuesets()

    def _regla_inclusion(self, f, vs):
        """Comprueba modo, filtro y «Incluir otro ValueSet» de una fila de Inclusiones."""
        r = f["_fila"]
        if f["modo"] and f["modo"] not in MODOS_INCLUSION:
            self.add(ERROR, "Inclusiones", r, f"«{f['modo']}» no es un modo válido.", f"Elige uno de: {', '.join(MODOS_INCLUSION)}.")
        if f["filtro"]:
            if f["filtro"] not in FILTROS_VS:
                self.add(ERROR, "Inclusiones", r, f"El filtro «{f['filtro']}» no es válido.", f"Elige uno de: {', '.join(FILTROS_VS)}.")
            if not f["filtro_valor"]:
                self.add(ERROR, "Inclusiones", r, f"El filtro «{f['filtro']}» necesita su «Valor del filtro».",
                         "Escribe el código de partida (o el texto, si es regex).")
            if not f["sistema"]:
                self.add(ERROR, "Inclusiones", r, "Un filtro necesita el sistema sobre el que se aplica.")
            if f["codigo"] or f["otro_valueset"]:
                self.add(ERROR, "Inclusiones", r, "Una fila con filtro no lleva también «Código» ni «Incluir otro ValueSet».", "Usa una fila por regla.")
            if f["filtro"] in FILTROS_VS and f["filtro"] not in FILTROS_DE_TEXTO and f["filtro_valor"] and f["sistema"] in self.cs and not f["filtro_propiedad"] \
                    and f["filtro_valor"] not in self.conceptos.get(f["sistema"], {}):
                self.add(ERROR, "Inclusiones", r, f"El código «{f['filtro_valor']}» del filtro no existe en «{f['sistema']}».", "Corrige el código o agrégalo en Conceptos.")
        elif f["filtro_propiedad"]:
            self.add(AVISO, "Inclusiones", r, "Escribiste «Propiedad del filtro» pero no elegiste «Filtro»; se ignora.")
        elif f["filtro_valor"]:
            self.add(AVISO, "Inclusiones", r, "Escribiste «Valor del filtro» pero no elegiste «Filtro»; se ignora.")
        otro = f["otro_valueset"]
        if otro:
            if otro == vs:
                self.add(ERROR, "Inclusiones", r, f"El ValueSet «{vs}» no puede incluirse a sí mismo.")
            elif otro not in self.vs and not RE_URL.match(otro) and not (self.cat and (otro in self.cat.vs)) and (self.cat or not self.usa_clcore()):
                cerca = difflib.get_close_matches(otro, list(self.vs) + (list(self.cat.vs) if self.cat else []), n=1, cutoff=0.6)
                self.add(ERROR, "Inclusiones", r, f"El ValueSet «{otro}» no existe.",
                         f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Debe ser un ValueSet de tu libro, de CL Core o una URL.")
            if f["codigo"]:
                self.add(ERROR, "Inclusiones", r, "Una fila con «Incluir otro ValueSet» no lleva «Código».", "Usa una fila por regla.")

    def _valuesets(self):
        incl: dict[str, list[dict]] = {}
        for f in self.l.filas("Inclusiones"):
            incl.setdefault(f["valueset"], []).append(f)
            r, vs, sis, cod = f["_fila"], f["valueset"], f["sistema"], f["codigo"]
            if vs not in self.vs:
                cerca = difflib.get_close_matches(vs, list(self.vs), n=1, cutoff=0.6) if vs else []
                self.add(ERROR, "Inclusiones", r, f"El ValueSet «{vs}» no está en la hoja ValueSets." if vs else "Falta el ValueSet.",
                         f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Elige uno de la lista desplegable.")
                continue
            self._regla_inclusion(f, vs)
            if not sis:
                if not f["otro_valueset"]:
                    self.add(ERROR, "Inclusiones", r, "Falta el sistema.", "Indica el sistema, o un ValueSet en «Incluir otro ValueSet».")
                continue
            clase, url = url_sistema(sis, set(self.cs))
            if clase == "desconocido":
                cerca = difflib.get_close_matches(sis, list(self.cs) + ["LOINC", "SNOMED"], n=1, cutoff=0.6)
                self.add(ERROR, "Inclusiones", r, f"No reconozco el sistema «{sis}».", f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Usa un CodeSystem de tu libro, LOINC, SNOMED o una URL.")
            elif clase == "libro" and cod and cod not in self.conceptos.get(sis, {}):
                self.add(ERROR, "Inclusiones", r, f"El código «{cod}» no existe en «{sis}».", "Agrégalo en Conceptos o corrige el código.")
        for n, f in self.vs.items():
            if not RE_NOMBRE.match(n):
                self.add(ERROR, "ValueSets", f["_fila"], f"El nombre «{n}» no es válido.", f"Por ejemplo: «{pascal(n) or 'VSMio'}».")
            if n not in incl:
                self.add(ERROR, "ValueSets", f["_fila"], f"El ValueSet «{n}» no tiene contenido.", "Agrega sus códigos en la hoja Inclusiones.")
            if not f["descripcion"]:
                self._falta_descripcion("ValueSets", f["_fila"], n)
        usados = {f["sistema"] for fs in incl.values() for f in fs} | {f["fijo_sistema"] for f in self.l.filas("Elementos")} \
            | {f["sistema"] for f in self.l.filas("Valores")}
        for n, f in self.cs.items():
            if n not in usados:
                self.add(SUGERENCIA, "CodeSystems", f["_fila"], f"El CodeSystem «{n}» no se usa en ningún ValueSet, regla ni ejemplo.")

    # ------------------------------------------------------------ Documentación
    def documentacion(self):
        vistos: dict[str, int] = {}
        for f in self.l.filas("Documentación"):
            p, r = f["pagina"], f["_fila"]
            if not RE_ID.match(p or ""):
                self.add(ERROR, "Documentación", r, f"El identificador de página «{p}» no es válido.", f"Minúsculas, números y guiones. Por ejemplo: «{kebab(p) or 'inicio'}».")
            if p in vistos:
                self.add(ERROR, "Documentación", r, f"La página «{p}» está repetida (fila {vistos[p]}).")
            vistos[p] = r
            if not f["titulo"] or not f["texto"]:
                self.add(ERROR, "Documentación", r, f"La página «{p}» necesita título y texto.")
            elif f["texto"].strip().startswith("@"):
                _, error = texto_de_pagina(self.l.base, f["texto"])
                if error:
                    self.add(ERROR, "Documentación", r, f"Página «{p}»: {error}")
        if "inicio" not in vistos:
            self.add(SUGERENCIA, "Documentación", None, "No escribiste la página «inicio»; se generará un borrador con tus perfiles y ejemplos.", "Revísalo antes de publicar.")
        automaticas = {"requisitos"} if self.l.filas("Perfiles") else set()
        for f in self.l.filas("Documentación"):
            padre, r = f.get("padre", "").strip(), f["_fila"]
            if not padre:
                continue
            if padre == f["pagina"]:
                self.add(ERROR, "Documentación", r, f"La página «{padre}» no puede ser su propia página padre.")
            elif padre not in vistos and padre not in automaticas | {"inicio"}:
                self.add(ERROR, "Documentación", r, f"La página padre «{padre}» no existe en esta hoja.", "Escribe el id de otra página de la hoja Documentación.")
            else:
                visto, actual = {f["pagina"]}, padre
                pads = {g["pagina"]: g.get("padre", "").strip() for g in self.l.filas("Documentación")}
                while actual in pads and pads[actual]:
                    if actual in visto:
                        self.add(ERROR, "Documentación", r, f"Las páginas padre de «{f['pagina']}» forman un círculo.")
                        break
                    visto.add(actual)
                    actual = pads[actual]
        self.menu(set(vistos))
        self.cambios()

    def menu(self, ids_documentacion: set[str]):
        filas = self.l.filas("Menú")
        if not filas:
            return
        paginas = ids_documentacion | {"inicio"} | set(PAGINAS_GENERADAS) | ({"requisitos"} if self.l.filas("Perfiles") else set())
        caps = {f["nombre"]: (f["id"] or f["nombre"]) for f in self.l.filas("Capacidades")}
        etiquetas: dict[str, int] = {}
        for f in filas:
            e, r = f["etiqueta"], f["_fila"]
            if e in etiquetas:
                self.add(ERROR, "Menú", r, f"El texto «{e}» está repetido (fila {etiquetas[e]}).")
            etiquetas[e] = r
        desplegables = {f["etiqueta"] for f in filas if not f["destino"].strip()}
        for f in filas:
            e, d, pad, r = f["etiqueta"], f["destino"].strip(), f["padre"].strip(), f["_fila"]
            if d:
                if href_menu(d, paginas, caps) is None:
                    self.add(ERROR, "Menú", r, f"«{e}»: el destino «{d}» no existe.",
                             "Usa el id de una página de Documentación, «artefactos», «must-support», «cambios», el nombre de una declaración de capacidades o una dirección https://.")
                if d == "must-support" and "must-support" not in ids_documentacion and not any(
                        es_si(x["ms"]) for h in ("Elementos", "Slices", "Extensiones", "ValorExtensiones") for x in self.l.filas(h)):
                    self.add(AVISO, "Menú", r, "Ningún elemento está marcado como Must Support: la página saldrá vacía.")
                if d == "cambios" and "cambios" not in ids_documentacion and not self.l.filas("Cambios"):
                    self.add(ERROR, "Menú", r, "«cambios» necesita filas en la hoja Cambios.")
            elif not any(h["padre"].strip() == e for h in filas):
                self.add(ERROR, "Menú", r, f"«{e}» no lleva a ninguna parte y no tiene opciones dentro.", "Escribe un destino o agrega filas que lo usen como «Dentro del desplegable».")
            if pad:
                if pad not in desplegables:
                    self.add(ERROR, "Menú", r, f"«{e}»: «{pad}» no es un desplegable.", "Un desplegable es una fila de esta hoja sin destino.")
                elif not d:
                    self.add(ERROR, "Menú", r, f"«{e}» es un desplegable dentro de otro desplegable; solo se admite un nivel.")

    def cambios(self):
        vistos: dict[str, int] = {}
        for f in self.l.filas("Cambios"):
            v, r = f["version"], f["_fila"]
            if v in vistos:
                self.add(AVISO, "Cambios", r, f"La versión «{v}» está repetida (fila {vistos[v]}).")
            vistos[v] = r
            if not f["version"] or not f["cambios"]:
                self.add(ERROR, "Cambios", r, "Cada fila necesita versión y qué cambió.")

    # ---- parámetros de búsqueda, mapas de conceptos y operaciones
    def _nombres_unicos(self, hoja: str, clave: str = "nombre") -> dict[str, int]:
        vistos: dict[str, int] = {}
        for f in self.l.filas(hoja):
            n, r = f[clave], f["_fila"]
            if not n:
                self.add(ERROR, hoja, r, "Falta el nombre.")
                continue
            if not RE_NOMBRE.match(n):
                self.add(ERROR, hoja, r, f"El nombre «{n}» no es válido.", f"Sin espacios ni símbolos y empezando con mayúscula. Por ejemplo: «{pascal(n) or 'Nombre'}».")
            if n in vistos:
                self.add(ERROR, hoja, r, f"«{n}» está repetido (también en la fila {vistos[n]}).")
            vistos[n] = r
        return vistos

    def parametros_busqueda(self):
        self._nombres_unicos("ParametrosBusqueda")
        codigos: dict[tuple[str, str], int] = {}
        for f in self.l.filas("ParametrosBusqueda"):
            r, n = f["_fila"], f["nombre"] or "el parámetro"
            if not f["codigo"]:
                self.add(ERROR, "ParametrosBusqueda", r, f"Falta el código de búsqueda de «{n}».", "Por ejemplo: segundo-apellido.")
            elif not re.match(r"^[A-Za-z0-9_-]+$", f["codigo"]):
                self.add(ERROR, "ParametrosBusqueda", r, f"El código «{f['codigo']}» de «{n}» no es válido.", "Usa letras, números, guiones y guion bajo, sin espacios.")
            recursos = _lista(f["recursos"])
            if not recursos:
                self.add(ERROR, "ParametrosBusqueda", r, f"«{n}» no dice en qué recursos se busca.", "Por ejemplo: Patient.")
            for rec in recursos:
                if rec not in RECURSOS_R4:
                    self.add(ERROR, "ParametrosBusqueda", r, f"«{rec}» no es un recurso de FHIR.", "Escríbelo como en FHIR, por ejemplo Patient.")
                if f["codigo"] and (rec, f["codigo"]) in codigos:
                    self.add(AVISO, "ParametrosBusqueda", r, f"Ya hay un parámetro «{f['codigo']}» para {rec} (fila {codigos[(rec, f['codigo'])]}).")
                codigos[(rec, f["codigo"])] = r
            if f["tipo"] not in TIPOS_BUSQUEDA:
                self.add(ERROR, "ParametrosBusqueda", r, f"El tipo «{f['tipo']}» de «{n}» no es válido.", f"Opciones: {', '.join(TIPOS_BUSQUEDA)}.")
            if not f["expresion"]:
                self.add(SUGERENCIA, "ParametrosBusqueda", r, f"«{n}» no indica la expresión (FHIRPath): sin ella el servidor no sabe dónde buscar.")
            for m in _lista(f["modificadores"]):
                if m not in MODIFICADORES_BUSQUEDA:
                    self.add(ERROR, "ParametrosBusqueda", r, f"El modificador «{m}» no es válido.", f"Opciones: {', '.join(MODIFICADORES_BUSQUEDA)}.")
            for c in _lista(f["comparadores"]):
                if c not in ("eq", "ne", "gt", "lt", "ge", "le", "sa", "eb", "ap"):
                    self.add(ERROR, "ParametrosBusqueda", r, f"El comparador «{c}» no es válido.", "Opciones: eq, ne, gt, lt, ge, le, sa, eb, ap.")
            for d in _lista(f["destinos"]):
                if d not in RECURSOS_R4:
                    self.add(ERROR, "ParametrosBusqueda", r, f"«{d}» no es un recurso de FHIR.")
            for campo in ("multiple_o", "multiple_y"):
                if f[campo] and not (es_si(f[campo]) or es_no(f[campo])):
                    self.add(ERROR, "ParametrosBusqueda", r, f"«{f[campo]}» no es Sí ni No.")
            if not f["descripcion"]:
                self.add(SUGERENCIA, "ParametrosBusqueda", r, f"«{n}» no tiene descripción.")

    def _artefacto_existe(self, hoja: str, r: int, valor: str, que: str, tablas) -> None:
        if not valor or RE_URL.match(valor) or valor in tablas[0] or (self.cat and any(valor in t for t in tablas[1])):
            return
        self.add(ERROR, hoja, r, f"El {que} «{valor}» no existe.", "Debe ser de la hoja correspondiente, de CL Core o una URL.")

    def mapas(self):
        self._nombres_unicos("MapasConceptos")
        mapas = {f["nombre"] for f in self.l.filas("MapasConceptos")}
        for f in self.l.filas("MapasConceptos"):
            for campo, que in (("origen", "ValueSet de origen"), ("destino", "ValueSet de destino")):
                self._artefacto_existe("MapasConceptos", f["_fila"], f[campo], que, (set(self.vs), (self.cat.vs,) if self.cat else ()))
            if not f["origen"] and not f["destino"]:
                self.add(SUGERENCIA, "MapasConceptos", f["_fila"], f"«{f['nombre']}» no indica ValueSet de origen ni de destino.")
        vistos: dict[tuple, int] = {}
        con_reglas = set()
        for f in self.l.filas("ReglasMapa"):
            r, m = f["_fila"], f["mapa"]
            if m not in mapas:
                self.add(ERROR, "ReglasMapa", r, f"El mapa «{m}» no está en la hoja MapasConceptos." if m else "Falta el mapa.", "Elige uno de la lista desplegable.")
                continue
            con_reglas.add(m)
            for campo in ("sistema_origen", "sistema_destino"):
                clase, _ = url_sistema(f[campo], set(self.cs)) if f[campo] else ("desconocido", None)
                if clase == "desconocido":
                    self.add(ERROR, "ReglasMapa", r, f"El sistema «{f[campo]}» no es conocido." if f[campo] else "Falta el sistema.",
                             "Usa un CodeSystem de tu libro, LOINC, SNOMED o una URL.")
            if not f["codigo_origen"]:
                self.add(ERROR, "ReglasMapa", r, "Falta el código de origen.")
            elif f["sistema_origen"] in self.cs and f["codigo_origen"] not in self.conceptos.get(f["sistema_origen"], {}):
                self.add(ERROR, "ReglasMapa", r, f"El código «{f['codigo_origen']}» no existe en «{f['sistema_origen']}».", "Corrige el código o agrégalo en Conceptos.")
            if f["codigo_destino"] and f["sistema_destino"] in self.cs and f["codigo_destino"] not in self.conceptos.get(f["sistema_destino"], {}):
                self.add(ERROR, "ReglasMapa", r, f"El código «{f['codigo_destino']}» no existe en «{f['sistema_destino']}».", "Corrige el código o agrégalo en Conceptos.")
            if f["equivalencia"] and f["equivalencia"] not in EQUIVALENCIAS:
                self.add(ERROR, "ReglasMapa", r, f"La equivalencia «{f['equivalencia']}» no es válida.", f"Opciones: {', '.join(EQUIVALENCIAS)}.")
            if not f["codigo_destino"] and f["equivalencia"] not in ("", "unmatched", "disjoint"):
                self.add(ERROR, "ReglasMapa", r, f"«{f['codigo_origen']}» tiene equivalencia «{f['equivalencia']}» pero no código de destino.", "Escribe el código de destino o usa unmatched.")
            clave = (m, f["sistema_origen"], f["sistema_destino"], f["codigo_origen"], f["codigo_destino"])
            if clave in vistos:
                self.add(AVISO, "ReglasMapa", r, f"Esta equivalencia ya está en la fila {vistos[clave]}.")
            vistos[clave] = r
        for f in self.l.filas("MapasConceptos"):
            if f["nombre"] and f["nombre"] not in con_reglas:
                self.add(AVISO, "MapasConceptos", f["_fila"], f"El mapa «{f['nombre']}» no tiene equivalencias.", "Agrégalas en la hoja ReglasMapa.")

    def operaciones(self):
        self._nombres_unicos("Operaciones")
        ops = {f["nombre"] for f in self.l.filas("Operaciones")}
        con_params = set()
        for f in self.l.filas("Operaciones"):
            r, n = f["_fila"], f["nombre"] or "la operación"
            if not f["codigo"]:
                self.add(ERROR, "Operaciones", r, f"Falta el código de «{n}».", "Lo que va tras el $. Por ejemplo: match.")
            elif not re.match(r"^[A-Za-z0-9_.-]+$", f["codigo"]):
                self.add(ERROR, "Operaciones", r, f"El código «{f['codigo']}» de «{n}» no es válido.", "Escríbelo sin el signo $ ni espacios.")
            for rec in _lista(f["recursos"]):
                if rec not in RECURSOS_R4:
                    self.add(ERROR, "Operaciones", r, f"«{rec}» no es un recurso de FHIR.")
            niveles = [x.strip().lower() for x in _lista(f["nivel"])]
            for x in niveles:
                if x not in ("sistema", "tipo", "instancia"):
                    self.add(ERROR, "Operaciones", r, f"«{x}» no es un nivel válido.", "Usa sistema, tipo o instancia, separados por coma.")
            if not niveles:
                self.add(AVISO, "Operaciones", r, f"«{n}» no dice dónde se invoca.", "Indica sistema, tipo o instancia.")
            if niveles and ("tipo" in niveles or "instancia" in niveles) and not _lista(f["recursos"]):
                self.add(AVISO, "Operaciones", r, f"«{n}» se invoca sobre un tipo o instancia pero no indica recursos.")
            if f["tipo_operacion"] and f["tipo_operacion"] not in TIPOS_OPERACION:
                self.add(ERROR, "Operaciones", r, f"El tipo «{f['tipo_operacion']}» no es válido.", "Usa operation o query.")
            if f["base"] and not RE_URL.match(f["base"]):
                self.add(ERROR, "Operaciones", r, f"La operación base de «{n}» debe ser una URL.")
            if not f["descripcion"]:
                self.add(SUGERENCIA, "Operaciones", r, f"«{n}» no tiene descripción.")
        vistos: dict[tuple[str, str, str], int] = {}
        for f in self.l.filas("ParametrosOperacion"):
            r, o = f["_fila"], f["operacion"]
            if o not in ops:
                self.add(ERROR, "ParametrosOperacion", r, f"La operación «{o}» no está en la hoja Operaciones." if o else "Falta la operación.", "Elige una de la lista desplegable.")
                continue
            con_params.add(o)
            if not f["parametro"]:
                self.add(ERROR, "ParametrosOperacion", r, "Falta el nombre del parámetro.")
            if f["uso"] not in USOS_PARAMETRO:
                self.add(ERROR, "ParametrosOperacion", r, f"«{f['uso']}» no es un uso válido." if f["uso"] else "Falta si es de entrada o de salida.", "Usa in (entrada) u out (salida).")
            mn, mx = f["min"], f["max"]
            if mn and entero(mn) is None:
                self.add(ERROR, "ParametrosOperacion", r, f"El mínimo «{mn}» debe ser un número entero.")
            elif mx and mx != "*" and entero(mx) is None:
                self.add(ERROR, "ParametrosOperacion", r, f"El máximo «{mx}» debe ser un número o *.")
            elif mn and mx and maximo(mx) < entero(mn):
                self.add(ERROR, "ParametrosOperacion", r, f"El mínimo ({mn}) es mayor que el máximo ({mx}).")
            if f["tipo"] and not _tipo_valido(f["tipo"]):
                self.add(ERROR, "ParametrosOperacion", r, f"El tipo «{f['tipo']}» no es válido.", "Por ejemplo: Patient, boolean, integer, string.")
            if not f["tipo"] and not f["tipo_busqueda"]:
                self.add(ERROR, "ParametrosOperacion", r, f"«{f['parametro']}» necesita un tipo de dato (o un tipo de búsqueda).")
            if f["tipo_busqueda"] and f["tipo_busqueda"] not in TIPOS_BUSQUEDA:
                self.add(ERROR, "ParametrosOperacion", r, f"El tipo de búsqueda «{f['tipo_busqueda']}» no es válido.", f"Opciones: {', '.join(TIPOS_BUSQUEDA)}.")
            for p in _lista(f["perfil"]):
                self._artefacto_existe("ParametrosOperacion", r, p, "perfil", (set(self.perfiles), (self.cat.sd,) if self.cat else ()))
            clave = (o, f["parametro"], f["uso"])
            if clave in vistos:
                self.add(AVISO, "ParametrosOperacion", r, f"El parámetro «{f['parametro']}» ({f['uso']}) ya está en la fila {vistos[clave]}.")
            vistos[clave] = r
        for f in self.l.filas("Operaciones"):
            if f["nombre"] and f["nombre"] not in con_params:
                self.add(AVISO, "Operaciones", f["_fila"], f"«{f['nombre']}» no tiene parámetros.", "Agrégalos en la hoja ParametrosOperacion.")

    def ids_artefactos(self):
        """El «id» (final de la URL) debe ser válido y no repetirse entre artefactos del mismo tipo."""
        from libro.esquema import HOJAS_CON_ID
        from libro.fsh import id_de
        tipos = {"Perfiles": "StructureDefinition", "Extensiones": "StructureDefinition", "CodeSystems": "CodeSystem", "ValueSets": "ValueSet",
                 "Capacidades": "CapabilityStatement", "ParametrosBusqueda": "SearchParameter", "MapasConceptos": "ConceptMap",
                 "Operaciones": "OperationDefinition", "Cuestionarios": "Questionnaire"}
        vistos: dict[tuple[str, str], tuple[str, int]] = {}
        for hoja in HOJAS_CON_ID:
            for f in self.l.filas(hoja):
                if not f["nombre"] or f.get("parte_de") or f.get("url"):
                    continue
                if f["id"] and not re.match(r"^[A-Za-z0-9.\-]{1,64}$", f["id"]):
                    self.add(ERROR, hoja, f["_fila"], f"El id «{f['id']}» no es válido.", "Hasta 64 letras, números, puntos o guiones; sin espacios.")
                clave = (tipos[hoja], id_de(f))
                if clave in vistos:
                    self.add(ERROR, hoja, f["_fila"], f"El id «{clave[1]}» ya lo usa «{vistos[clave][0]}» (fila {vistos[clave][1]}).",
                             "Dos artefactos del mismo tipo no pueden terminar igual su URL. Cambia uno en la columna «Id».")
                vistos.setdefault(clave, (f["nombre"], f["_fila"]))

    def invariantes(self):
        extensiones_propias = {f["nombre"] for f in self.l.filas("Extensiones") if f["nombre"] and not f["parte_de"] and not f["url"]}
        definidas: dict[str, dict] = {}
        vistos: set[tuple] = set()
        for f in self.l.filas("Invariantes"):
            r, k = f["_fila"], f["clave"]
            if not k:
                self.add(ERROR, "Invariantes", r, "Falta la clave de la regla.")
                continue
            if not re.match(r"^[A-Za-z][A-Za-z0-9_.-]*$", k):
                self.add(ERROR, "Invariantes", r, f"La clave «{k}» no es válida.", "Letras, números y guiones, empezando con letra. Ej.: cl-1.")
            if f["perfil"] not in self.perfiles and f["perfil"] not in extensiones_propias:
                self.add(ERROR, "Invariantes", r, f"«{f['perfil']}» no está en la hoja Perfiles ni en Extensiones." if f["perfil"] else "Falta el perfil.", "Elige uno de la lista desplegable.")
            if f["gravedad"] not in GRAVEDADES:
                self.add(ERROR, "Invariantes", r, f"La gravedad «{f['gravedad']}» no es válida." if f["gravedad"] else f"Falta la gravedad de «{k}».", "Usa error o warning.")
            if not f["descripcion"]:
                self.add(ERROR, "Invariantes", r, f"Falta qué exige la regla «{k}».")
            if not f["expresion"]:
                self.add(ERROR, "Invariantes", r, f"Falta la expresión de la regla «{k}».")
            else:
                e = f["expresion"]
                if e.count("(") != e.count(")") or e.count("'") % 2 or e.count("[") != e.count("]"):
                    self.add(ERROR, "Invariantes", r, f"La expresión de «{k}» tiene paréntesis, corchetes o comillas sin cerrar.")
            if f["ruta"]:
                self._ruta(f, "Invariantes")
            previa = definidas.get(k)
            if previa and (previa["gravedad"], previa["descripcion"], previa["expresion"]) != (f["gravedad"], f["descripcion"], f["expresion"]):
                self.add(ERROR, "Invariantes", r, f"La regla «{k}» ya está definida distinto en la fila {previa['_fila']}.", "Una misma clave debe tener la misma gravedad, texto y expresión; usa otra clave si es otra regla.")
            definidas.setdefault(k, f)
            clave = (k, f["perfil"], f["ruta"])
            if clave in vistos:
                self.add(AVISO, "Invariantes", r, f"La regla «{k}» ya se aplica a ese perfil y elemento.")
            vistos.add(clave)

    def mensajes(self):
        """Un Bundle de tipo message debe llevar un MessageHeader; en el mensaje real va como primera entrada (bdl-12 de FHIR)."""
        for n, pf in self.perfiles.items():
            if pf["recurso"] != "Bundle":
                continue
            filas = [e for e in self.l.filas("Elementos") if e["perfil"] == n]
            if not any(e["ruta"] == "type" and e["fijo"] == "message" for e in filas):
                continue
            slices = [x for x in self.l.filas("Slices") if x["perfil"] == n and x["elemento"] == "entry"]

            def es_cabecera(sl: dict) -> bool:
                for e in filas:
                    if e["ruta"] == f"entry[{sl['slice']}].resource":
                        if e["tipo"] == "MessageHeader":
                            return True
                        for p in _lista(e["perfil_tipo"]):
                            if (self.perfiles.get(p) or {}).get("recurso") == "MessageHeader":
                                return True
                            if self.cat and p in self.cat.sd and self.cat.sd[p].get("type") == "MessageHeader":
                                return True
                return False
            cab = [i for i, sl in enumerate(slices) if es_cabecera(sl)]
            fila = pf["_fila"]
            if not cab:
                self.add(AVISO, "Perfiles", fila, f"«{n}» es un mensaje (type = message) pero ninguna entrada es un MessageHeader.",
                         "Agrega una entrada (hoja Slices) cuyo recurso sea MessageHeader o un perfil suyo. FHIR exige que sea la primera.")
                continue
            if cab[0] != 0:
                ordenado = any(x["ordenado"] and x["ordenado"].lower().startswith("s") for x in slices)
                self.add(AVISO if ordenado else SUGERENCIA, "Slices", slices[cab[0]]["_fila"],
                         f"En «{n}» la entrada del MessageHeader no está primera en la lista de slices.",
                         "Muévela al comienzo." if ordenado else "No es un error: sin orden, el perfil lo permite. Al armar un mensaje real, el MessageHeader debe ir como primera entrada (bdl-12).")
            if entero(slices[cab[0]]["min"] or "0") in (None, 0):
                self.add(AVISO, "Slices", slices[cab[0]]["_fila"], f"En «{n}» el MessageHeader debe ser obligatorio (mínimo 1).")
            if entero(slices[cab[0]]["max"] or "1") not in (1,):
                self.add(AVISO, "Slices", slices[cab[0]]["_fila"], f"En «{n}» solo puede haber un MessageHeader (máximo 1).")

    def cuestionarios(self):
        self._nombres_unicos("Cuestionarios")
        cuestionarios = {f["nombre"] for f in self.l.filas("Cuestionarios")}
        for f in self.l.filas("Cuestionarios"):
            for rec in _lista(f["recursos"]):
                if rec not in RECURSOS_R4:
                    self.add(ERROR, "Cuestionarios", f["_fila"], f"«{rec}» no es un recurso de FHIR.")
            if f["basado_en"] and not RE_URL.match(f["basado_en"]):
                self.add(ERROR, "Cuestionarios", f["_fila"], f"«Basado en» de «{f['nombre']}» debe ser una URL.")
            if not f["descripcion"]:
                self.add(SUGERENCIA, "Cuestionarios", f["_fila"], f"«{f['nombre']}» no tiene descripción.")
        por_cuestionario: dict[str, dict[str, dict]] = {}
        for f in self.l.filas("PreguntasCuestionario"):
            r, c = f["_fila"], f["cuestionario"]
            if c not in cuestionarios:
                self.add(ERROR, "PreguntasCuestionario", r, f"El cuestionario «{c}» no está en la hoja Cuestionarios." if c else "Falta el cuestionario.", "Elige uno de la lista desplegable.")
                continue
            ids = por_cuestionario.setdefault(c, {})
            if not f["id"]:
                self.add(ERROR, "PreguntasCuestionario", r, "Falta el id de la pregunta.")
            elif f["id"] in ids:
                self.add(ERROR, "PreguntasCuestionario", r, f"El id «{f['id']}» ya se usó en la fila {ids[f['id']]['_fila']} de «{c}».", "Cada pregunta necesita un id único dentro de su cuestionario.")
            else:
                ids[f["id"]] = f
        for c, ids in por_cuestionario.items():
            con_hijos = {f["dentro_de"] for f in ids.values() if f["dentro_de"]}
            for f in ids.values():
                r, i, t = f["_fila"], f["id"], f["tipo"]
                if t not in TIPOS_PREGUNTA:
                    self.add(ERROR, "PreguntasCuestionario", r, f"El tipo «{t}» de «{i}» no es válido." if t else f"Falta el tipo de «{i}».", f"Opciones: {', '.join(TIPOS_PREGUNTA)}.")
                if f["dentro_de"]:
                    padre = ids.get(f["dentro_de"])
                    if padre is None:
                        self.add(ERROR, "PreguntasCuestionario", r, f"El grupo «{f['dentro_de']}» de «{i}» no existe en «{c}».", "Indica el id de otra pregunta de tipo group.")
                    elif padre["tipo"] != "group":
                        self.add(ERROR, "PreguntasCuestionario", r, f"«{f['dentro_de']}» no es de tipo group, no puede contener a «{i}».")
                    else:                                 # ciclos: subir por los grupos hasta salir o repetir
                        visto, actual = {i}, f["dentro_de"]
                        while actual and actual in ids:
                            if actual in visto:
                                self.add(ERROR, "PreguntasCuestionario", r, f"«{i}» queda dentro de sí misma por una cadena de grupos.")
                                break
                            visto.add(actual)
                            actual = ids[actual]["dentro_de"]
                if t in ("group", "display") and (f["obligatoria"] or f["opciones"]) and t == "display":
                    self.add(AVISO, "PreguntasCuestionario", r, f"«{i}» es solo un texto: «Obligatoria» y «Opciones» no se usan.")
                if i in con_hijos and t != "group":
                    self.add(ERROR, "PreguntasCuestionario", r, f"«{i}» contiene otras preguntas pero no es de tipo group.")
                if t == "group" and i not in con_hijos:
                    self.add(AVISO, "PreguntasCuestionario", r, f"El grupo «{i}» no tiene preguntas dentro.")
                if not f["texto"] and t != "group":
                    self.add(AVISO, "PreguntasCuestionario", r, f"«{i}» no tiene texto.")
                if f["opciones"]:
                    if t not in ("choice", "open-choice"):
                        self.add(ERROR, "PreguntasCuestionario", r, f"«{i}» tiene opciones pero es de tipo «{t}».", "Solo choice y open-choice llevan un ValueSet.")
                    self._artefacto_existe("PreguntasCuestionario", r, f["opciones"], "ValueSet", (set(self.vs), (self.cat.vs,) if self.cat else ()))
                elif t in ("choice", "open-choice"):
                    self.add(AVISO, "PreguntasCuestionario", r, f"«{i}» es de tipo {t} pero no indica las opciones.", "Elige un ValueSet.")
                for campo, que in (("obligatoria", "Obligatoria"), ("repite", "Se puede repetir"), ("solo_lectura", "Solo lectura")):
                    if f[campo] and not (es_si(f[campo]) or es_no(f[campo])):
                        self.add(ERROR, "PreguntasCuestionario", r, f"«{f[campo]}» no es Sí ni No en «{que}».")
                if f["largo_maximo"]:
                    if entero(f["largo_maximo"]) is None or t not in ("string", "text", "url"):
                        self.add(ERROR, "PreguntasCuestionario", r, f"«Largo máximo» de «{i}» debe ser un número y solo vale para texto." )
                if f["si_pregunta"]:
                    origen = ids.get(f["si_pregunta"])
                    op = f["si_operador"] or "="
                    if origen is None:
                        self.add(ERROR, "PreguntasCuestionario", r, f"La pregunta «{f['si_pregunta']}» de la condición de «{i}» no existe en «{c}».")
                    elif f["si_pregunta"] == i:
                        self.add(ERROR, "PreguntasCuestionario", r, f"«{i}» depende de sí misma.")
                    if op not in OPERADORES_CONDICION:
                        self.add(ERROR, "PreguntasCuestionario", r, f"El operador «{op}» no es válido.", f"Opciones: {', '.join(OPERADORES_CONDICION)}.")
                    elif not f["si_respuesta"] and op != "exists":
                        self.add(ERROR, "PreguntasCuestionario", r, f"Falta la respuesta esperada en la condición de «{i}».")
                    elif origen is not None and op != "exists" and origen["tipo"] in ("choice", "open-choice") and "#" not in f["si_respuesta"]:
                        self.add(ERROR, "PreguntasCuestionario", r, f"La respuesta esperada de «{i}» debe ser SISTEMA#codigo.", "Por ejemplo: MiCodeSystem#01.")
                    elif origen is not None and op != "exists" and origen["tipo"] in ("integer", "decimal") and entero(f["si_respuesta"]) is None and not re.match(r"^-?\d+(\.\d+)?$", f["si_respuesta"]):
                        self.add(ERROR, "PreguntasCuestionario", r, f"La respuesta esperada «{f['si_respuesta']}» de «{i}» debe ser un número.")
                    elif origen is not None and op != "exists" and origen["tipo"] in ("group", "display", "attachment", "reference", "quantity"):
                        self.add(ERROR, "PreguntasCuestionario", r, f"Una condición sobre una pregunta de tipo «{origen['tipo']}» solo admite el operador exists.")
                elif f["si_operador"] or f["si_respuesta"] or f["si_comportamiento"]:
                    self.add(AVISO, "PreguntasCuestionario", r, f"«{i}» tiene datos de condición pero no dice de qué pregunta depende.")
                if f["si_comportamiento"] and f["si_comportamiento"] not in ("any", "all"):
                    self.add(ERROR, "PreguntasCuestionario", r, f"«{f['si_comportamiento']}» no es válido.", "Usa any o all.")
        for f in self.l.filas("Cuestionarios"):
            if f["nombre"] and f["nombre"] not in por_cuestionario:
                self.add(AVISO, "Cuestionarios", f["_fila"], f"El cuestionario «{f['nombre']}» no tiene preguntas.", "Agrégalas en la hoja PreguntasCuestionario.")

    def capacidades(self):
        from libro import capacidades as cap
        nombres: dict[str, int] = {}
        for f in self.l.filas("Capacidades"):
            n, r = f["nombre"], f["_fila"]
            if not n:
                self.add(ERROR, "Capacidades", r, "Falta el nombre de la declaración.")
                continue
            if not RE_NOMBRE.match(n):
                self.add(ERROR, "Capacidades", r, f"El nombre «{n}» no es válido.", f"Sin espacios ni símbolos y empezando con mayúscula. Por ejemplo: «{pascal(n) or 'Servidor'}».")
            if n in nombres:
                self.add(ERROR, "Capacidades", r, f"La declaración «{n}» está repetida (también en la fila {nombres[n]}).")
            nombres[n] = r
            if f["modo"] not in MODOS_CAPACIDAD:
                self.add(ERROR, "Capacidades", r, f"El rol de «{n}» debe ser uno de: {', '.join(MODOS_CAPACIDAD)}.")
            for fmt in _lista(f["formato"]):
                if fmt not in ("json", "xml") and not RE_MIME.match(fmt):
                    self.add(ERROR, "Capacidades", r, f"Formato «{fmt}» no válido en «{n}».", "Usa json, xml o un tipo MIME como application/fhir+json, separados por coma.")
            for fmt in _lista(f["formato_parche"]):
                if not RE_MIME.match(fmt):
                    self.add(ERROR, "Capacidades", r, f"Formato de parche «{fmt}» no válido en «{n}».", "Escribe un tipo MIME, por ejemplo application/json-patch+json.")
            if not f["descripcion"]:
                self.add(ERROR, "Capacidades", r, f"«{n}» no tiene descripción.",
                         "Una declaración de capacidades necesita descripción (regla cpb-2 de FHIR): el IG Publisher la rechaza sin ella.")

        def expectativa(hoja, r, valor, que):
            if valor and valor not in EXPECTATIVAS:
                self.add(ERROR, hoja, r, f"La expectativa «{valor}» de {que} no es válida.", f"Elige una de: {', '.join(EXPECTATIVAS)}.")

        usados: dict[tuple[str, str], int] = {}
        con_recursos = set()
        for f in self.l.filas("RecursosCapacidad"):
            c, rec, r = f["capacidad"], f["recurso"], f["_fila"]
            if c not in nombres:
                self.add(ERROR, "RecursosCapacidad", r, f"La declaración «{c}» no está en la hoja Capacidades." if c else "Falta la declaración.", "Elige una de la lista.")
                continue
            con_recursos.add(c)
            if rec not in RECURSOS_R4:
                cerca = difflib.get_close_matches(rec, RECURSOS_R4, n=1, cutoff=0.6)
                self.add(ERROR, "RecursosCapacidad", r, f"«{rec}» no es un recurso FHIR R4." if rec else "Falta el recurso.", f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Elige uno de la lista.")
                continue
            if (c, rec) in usados:
                self.add(ERROR, "RecursosCapacidad", r, f"«{rec}» ya está en «{c}» (fila {usados[(c, rec)]}).", "Junta las operaciones y búsquedas en una sola fila.")
            usados[(c, rec)] = r
            expectativa("RecursosCapacidad", r, f["expectativa"], f"«{rec}»")
            expectativa("RecursosCapacidad", r, f["perfil_expectativa"], "su perfil")
            for item in _lista(f["perfil"]):
                p, exp_p = cap.separar_expectativa(item)
                expectativa("RecursosCapacidad", r, exp_p, "su perfil")
                if p not in self.perfiles and not (self.cat and p in self.cat.sd) and not RE_URL.match(p) and (self.cat or not self.usa_clcore()):
                    cerca = difflib.get_close_matches(p, list(self.perfiles), n=1, cutoff=0.6)
                    self.add(ERROR, "RecursosCapacidad", r, f"El perfil «{p}» no existe.", f"¿Quisiste decir «{cerca[0]}»?" if cerca else "Elige uno de la lista.")
                elif p in self.perfiles and self.perfiles[p].get("recurso") not in ("", rec):
                    self.add(ERROR, "RecursosCapacidad", r, f"El perfil «{p}» es de {self.perfiles[p].get('recurso')}, no de {rec}.")
            for pol in _lista(f["referencias"]):
                pol = cap.separar_expectativa(pol)[0]
                if pol not in POLITICAS_REFERENCIA:
                    self.add(ERROR, "RecursosCapacidad", r, f"La política de referencias «{pol}» no existe.", f"Opciones: {', '.join(POLITICAS_REFERENCIA)}.")
            for campo in ("incluir", "incluir_inverso"):
                for x in _lista(f[campo]):
                    x = cap.separar_expectativa(x)[0]
                    if ":" not in x and x != "*":
                        self.add(AVISO, "RecursosCapacidad", r, f"«{x}» no tiene la forma Recurso:parámetro (ni es *).", "FHIR espera, por ejemplo, Observation:subject. Puedes agregar SHALL, SHOULD o MAY al final.")
            inter = cap.operaciones(self.l, c, rec)
            for i in _lista(f["interacciones"]):
                if i not in INTERACCIONES:
                    self.add(ERROR, "RecursosCapacidad", r, f"La operación «{i}» no existe.", f"Opciones: {', '.join(INTERACCIONES)}.")
            if not inter:
                self.add(AVISO, "RecursosCapacidad", r, f"«{rec}» en «{c}» no indica operaciones.", "Sin operaciones la declaración no dice qué se puede hacer con el recurso.")
            for b in _lista(f["busquedas"]):
                nombre, _, tipo = b.partition(":")
                if not nombre.strip() or tipo.strip() not in TIPOS_BUSQUEDA:
                    self.add(ERROR, "RecursosCapacidad", r, f"La búsqueda «{b}» debe escribirse parámetro:tipo.", f"Tipos: {', '.join(TIPOS_BUSQUEDA)}. Ej.: identifier:token.")
            if cap.busquedas(self.l, c, rec) and inter and "search-type" not in {i["codigo"] for i in inter}:
                self.add(AVISO, "RecursosCapacidad", r, f"«{rec}» declara búsquedas pero no la operación search-type.", "Agrega search-type a las operaciones.")

        vistos: set = set()
        for f in self.l.filas("OperacionesCapacidad"):
            c, rec, op, r = f["capacidad"], f["recurso"], f["operacion"], f["_fila"]
            if c not in nombres:
                self.add(ERROR, "OperacionesCapacidad", r, f"La declaración «{c}» no está en la hoja Capacidades." if c else "Falta la declaración.", "Elige una de la lista.")
                continue
            if rec and (c, rec) not in usados:
                self.add(ERROR, "OperacionesCapacidad", r, f"«{rec}» no está en los recursos de «{c}».", "Agrégalo primero en la hoja RecursosCapacidad.")
            permitidas = INTERACCIONES if rec else OPERACIONES_SERVIDOR
            if f["definicion"]:
                if not re.match(r"^[A-Za-z0-9_.-]+$", op or ""):
                    self.add(ERROR, "OperacionesCapacidad", r, f"El nombre de operación «{op}» no es válido.", "Escríbelo sin el signo $ ni espacios. Ej.: match.")
                self._artefacto_existe("OperacionesCapacidad", r, f["definicion"], "OperacionDefinition", (set(x["nombre"] for x in self.l.filas("Operaciones")), ()))
            elif op not in permitidas:
                self.add(ERROR, "OperacionesCapacidad", r, f"«{op}» no es una operación válida {'de un recurso' if rec else 'de todo el servidor'}.",
                         f"Opciones: {', '.join(permitidas)}." + ("" if rec else " Para las de un recurso, indica el recurso."))
            expectativa("OperacionesCapacidad", r, f["expectativa"], f"«{op}»")
            if (c, rec, op) in vistos:
                self.add(AVISO, "OperacionesCapacidad", r, f"«{op}» está repetida en «{c}».", "Deja una sola fila.")
            vistos.add((c, rec, op))
        vistos = set()
        for f in self.l.filas("BusquedasCapacidad"):
            c, rec, n, r = f["capacidad"], f["recurso"], f["parametro"], f["_fila"]
            if c not in nombres:
                self.add(ERROR, "BusquedasCapacidad", r, f"La declaración «{c}» no está en la hoja Capacidades." if c else "Falta la declaración.", "Elige una de la lista.")
                continue
            if (c, rec) not in usados:
                self.add(ERROR, "BusquedasCapacidad", r, f"«{rec}» no está en los recursos de «{c}».", "Agrégalo primero en la hoja RecursosCapacidad.")
            if f["tipo"] not in TIPOS_BUSQUEDA:
                self.add(ERROR, "BusquedasCapacidad", r, f"El tipo «{f['tipo']}» de «{n}» no es válido.", f"Opciones: {', '.join(TIPOS_BUSQUEDA)}.")
            expectativa("BusquedasCapacidad", r, f["expectativa"], f"«{n}»")
            if f["definicion"] and not RE_URL.match(f["definicion"]):
                self.add(ERROR, "BusquedasCapacidad", r, f"La definición de «{n}» debe ser una URL.")
            if (c, rec, n) in vistos:
                self.add(AVISO, "BusquedasCapacidad", r, f"«{n}» está repetida en «{rec}» de «{c}».", "Deja una sola fila.")
            vistos.add((c, rec, n))
        for n, r in nombres.items():
            if n not in con_recursos:
                self.add(AVISO, "Capacidades", r, f"La declaración «{n}» no tiene recursos.", "Agrega filas en la hoja RecursosCapacidad.")

    def todo(self) -> list[Aviso]:
        self.guia()
        self.perfiles_hoja()
        self.extensiones()
        self.valor_extensiones()
        self.slices()
        self.elementos()
        self.instancias()
        self.valores()
        self.capacidades()
        self.terminologia()
        self.parametros_busqueda()
        self.mapas()
        self.operaciones()
        self.cuestionarios()
        self.mensajes()
        self.invariantes()
        self.ids_artefactos()
        self.documentacion()
        if not self.perfiles and not self.cs and not self.vs and not any(self.l.filas(h) for h in ("Capacidades", "ParametrosBusqueda", "MapasConceptos", "Operaciones", "Cuestionarios")):
            self.add(ERROR, "Perfiles", None, "El libro no define ningún perfil, CodeSystem ni ValueSet.", "Completa al menos una hoja de contenido.")
        orden = {ERROR: 0, AVISO: 1, SUGERENCIA: 2}
        return sorted(self.avisos, key=lambda a: (orden[a.nivel], [h.nombre for h in HOJAS].index(a.hoja) if a.hoja in [h.nombre for h in HOJAS] else -1, a.fila or 0))


_ES_GENERICO = {"Resource", "DomainResource"}      # elementos que admiten cualquier recurso (Bundle.entry.resource, contained)


def _normalizar_indices(ruta: str) -> str:
    return re.sub(r"\[(\d+|\+|=)\]", "", ruta)


def _tipo_valido(texto: str) -> bool:
    import re
    return all(re.match(r"^[A-Za-z][A-Za-z0-9]*(\([A-Za-z0-9,|\s]+\))?$", t.strip()) for t in re.split(r"\s+or\s+|\|", texto))


def revisar_libro(libro: Libro, catalogo: CatalogIndex | None = None) -> list[Aviso]:
    return _Revisor(libro, catalogo).todo()


def hay_errores(avisos: list[Aviso]) -> bool:
    return any(a.nivel == ERROR for a in avisos)


def texto_avisos(avisos: list[Aviso]) -> str:
    if not avisos:
        return "Sin problemas: el libro está coherente.\n"
    n = {k: sum(a.nivel == k for a in avisos) for k in (ERROR, AVISO, SUGERENCIA)}
    out = [f"{n[ERROR]} errores · {n[AVISO]} avisos · {n[SUGERENCIA]} sugerencias", ""]
    out += [str(a) for a in avisos]
    return "\n".join(out) + "\n"
