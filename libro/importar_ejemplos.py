"""Ejemplos de un paquete FHIR (recursos JSON) -> filas de las hojas Instancias y Valores.

Cada dato del ejemplo pasa a una fila de «Valores» con su ruta completa. Las extensiones se escriben con su URL
(`extension[https://.../SegundoApellido].valueString`), que no depende de cómo cada perfil nombre el slice.
Lo que no tiene hoja en el libro (recursos contenidos, narrativa `text`, metadatos) queda fuera y se informa.
"""
from __future__ import annotations

import re
from decimal import Decimal

RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_FECHA_HORA = re.compile(r"^\d{4}-\d{2}-\d{2}T")
RE_UCUM_SEGURO = re.compile(r"^[A-Za-z0-9\[\]/.\-^%_{}()*]+$")
_NUM = (int, float, Decimal)


def _es_coding(o) -> bool:
    return isinstance(o, dict) and set(o) <= {"system", "version", "code", "display", "userSelected"} and ("code" in o or "system" in o) \
        and all(isinstance(v, str) for v in o.values()) and "version" not in o and "userSelected" not in o


def _es_cantidad(o) -> bool:
    return (isinstance(o, dict) and isinstance(o.get("value"), _NUM) and not isinstance(o.get("value"), bool)
            and set(o) <= {"value", "unit", "system", "code"} and bool(o.get("code") or o.get("unit"))
            and RE_UCUM_SEGURO.match(str(o.get("code") or o.get("unit"))) is not None)


def _es_referencia(o) -> bool:
    return isinstance(o, dict) and isinstance(o.get("reference"), str) and set(o) <= {"reference", "display"}


class _Conversor:
    def __init__(self, nombre: str, conserva_texto=lambda sistema: True):
        self.n = nombre
        self.conserva_texto = conserva_texto
        self.vscat = False                              # perfil de signos vitales: su categoría va en el slice VSCat
        self.filas: list[dict] = []

    def fila(self, ruta, tipo="", valor="", sistema="", unidad="", texto=""):
        self.filas.append({"instancia": self.n, "ruta": ruta, "tipo": tipo, "valor": str(valor), "sistema": sistema, "unidad": unidad, "texto": texto})

    def primitivo(self, ruta: str, v) -> None:
        if isinstance(v, bool):
            self.fila(ruta, "booleano", "Sí" if v else "No")
        elif isinstance(v, _NUM):
            self.fila(ruta, "número", v)
        elif ruta.endswith(".div"):
            self.fila(ruta, "texto", v)
        elif RE_FECHA_HORA.match(v):
            self.fila(ruta, "fecha y hora", v)
        elif RE_FECHA.match(v):
            self.fila(ruta, "fecha", v)
        elif re.search(r"\.valueCode$", ruta):
            self.fila(ruta, "código simple", v)
        elif re.search(r"\.value[A-Z]\w*(\.|$)", ruta):          # dentro de una extensión: el tipo lo dice su nombre, no la estructura
            self.fila(ruta, "texto", v)
        else:
            self.fila(ruta, "", v)                               # el verificador lo deduce del elemento (texto, código, uri...)

    def extension(self, base: str, e: dict) -> None:
        clave = next((k for k in e if k.startswith("value")), None)
        if clave is None:
            for sub in e.get("extension", []):
                self.extension(f"{base}.extension[{sub['url']}]", sub)
            return
        self.recorrer(f"{base}.{clave}", e[clave])

    def recorrer(self, ruta: str, o) -> None:
        if isinstance(o, list):
            for i, v in enumerate(o):
                self.recorrer(f"{ruta}[{i}]", v)
        elif _es_coding(o):
            if self.vscat and re.fullmatch(r"category\[\d+\]\.coding\[0\]", ruta) is not None \
                    and o.get("code") == "vital-signs" and o.get("system", "").endswith("/observation-category"):
                ruta = "category[VSCat].coding[0]"
            texto = o.get("display", "") if self.conserva_texto(o.get("system", "")) else ""
            self.fila(ruta, "código con sistema", o.get("code", ""), o.get("system", ""), texto=texto)
        elif _es_cantidad(o):
            self.fila(ruta, "cantidad", o["value"], unidad=o.get("code") or o.get("unit", ""), texto=o.get("unit", ""))
        elif _es_referencia(o):
            self.fila(ruta, "referencia", o["reference"])
            if o.get("display"):
                self.fila(f"{ruta}.display", "", o["display"])
        elif isinstance(o, dict):
            for k, v in o.items():
                if k in ("extension", "modifierExtension") and isinstance(v, list):
                    for e in v:
                        self.extension(f"{ruta}.extension[{e['url']}]" if ruta else f"extension[{e['url']}]", e)
                else:
                    clave = k.lstrip("_")                        # extensiones de un valor simple: en FSH van sin guion bajo
                    self.recorrer(f"{ruta}.{clave}" if ruta else clave, v)
        else:
            self.primitivo(ruta, o)


def ejemplos_desde_json(recursos: list[dict], ref, nombre_valido, usados: set, inf, signos_vitales: set | None = None) -> tuple[list[dict], list[dict]]:
    """(filas de Instancias, filas de Valores). `ref(url)` da el nombre del perfil en el libro; `nombre_valido` crea nombres únicos."""
    instancias, valores = [], []

    def conserva_texto(sistema: str) -> bool:
        """El texto de un código solo se conserva si el publicador puede darlo por bueno: sistemas del propio paquete o de HL7.
        LOINC, SNOMED o los idiomas lo traen en otro idioma o con otra redacción y el publicador lo marca como error."""
        return sistema.startswith(("http://terminology.hl7.org/", "http://hl7.org/fhir")) or ref(sistema) != sistema

    for r in recursos:
        tipo, id_ = r["resourceType"], r.get("id", "")
        nombre = nombre_valido("", id_ or tipo, usados)
        perfil = ""
        for url in r.get("meta", {}).get("profile", [])[:1]:
            perfil = ref(url)
            if "/" in perfil or ":" in perfil:                    # el perfil no está en el paquete ni en CL Core
                inf.falta("ejemplo cuyo perfil no está en el libro (se usa el recurso base)", id_ or tipo)
                perfil = ""
        if "contained" in r:
            inf.falta("recurso contenido dentro de un ejemplo", id_ or tipo)
        c = _Conversor(nombre, conserva_texto)
        c.vscat = any(u in (signos_vitales or ()) for u in r.get("meta", {}).get("profile", []))
        c.recorrer("", {k: v for k, v in r.items() if k not in ("resourceType", "id", "meta", "text", "contained")})
        instancias.append({"nombre": nombre, "perfil": perfil or tipo, "titulo": id_ or nombre, "descripcion": "Ejemplo importado del paquete.",
                           "id": id_ if id_ and id_ != nombre else ""})
        valores += c.filas
        inf.recursos["Ejemplo"] += 1
    return instancias, valores
