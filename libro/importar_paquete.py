"""Convierte un paquete FHIR publicado (carpeta con los JSON de una guía) en un libro de Excel.

Sirve para dos cosas: migrar una guía que ya existe al Excel, y probar la herramienta («prueba de reconstrucción»):
paquete -> libro -> FSH -> SUSHI -> comparar con el paquete original.

Por defecto NO copia los textos explicativos (short, definition, comment, description): `con_textos=True` los incluye.
Lo que el libro no puede expresar todavía no se pierde en silencio: queda en el informe (`Informe.no_soportado`).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from decimal import Decimal

from libro import importar as imp_caps
from libro.importar_ejemplos import ejemplos_desde_json
from libro.comun import RE_NOMBRE, kebab, pascal
from libro.esquema import HOJAS_CON_ID, RECURSOS_R4, TIPOS_DATO

BASE_FHIR = "http://hl7.org/fhir/StructureDefinition/"
TIPOS_CON_VALOR_EN_EXTENSION = None   # (cualquier tipo simple o de TIPOS_EXTENSION; se valida al revisar el libro)


@dataclass
class Informe:
    recursos: Counter = field(default_factory=Counter)
    no_soportado: Counter = field(default_factory=Counter)
    ejemplos: dict = field(default_factory=dict)
    nombres: dict = field(default_factory=dict)        # nombre en el libro -> {"tipo", "name", "id", "url"} del original

    def falta(self, que: str, donde: str = "") -> None:
        self.no_soportado[que] += 1
        self.ejemplos.setdefault(que, donde)

    def texto(self) -> str:
        lineas = ["Importado: " + ", ".join(f"{n} {k}" for k, n in sorted(self.recursos.items()))]
        if self.no_soportado:
            lineas.append("No se pudo expresar en el libro (queda fuera):")
            lineas += [f"  - {n} × {k}" + (f"  (por ejemplo {self.ejemplos[k]})" if self.ejemplos.get(k) else "") for k, n in self.no_soportado.most_common()]
        return "\n".join(lineas)


def _cola(url: str) -> str:
    return url.split("|")[0].rstrip("/").rsplit("/", 1)[-1]


def _leer(carpeta: Path) -> dict[str, list[dict]]:
    base = carpeta / "package" if (carpeta / "package").is_dir() else carpeta
    out: dict[str, list[dict]] = {}
    for f in sorted(base.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(d, dict) and d.get("resourceType") and f.name.startswith(d["resourceType"] + "-"):
            out.setdefault(d["resourceType"], []).append(d)
    return out


def _nombre_valido(candidato: str, id_: str, usados: set[str]) -> str:
    n = candidato if RE_NOMBRE.match(candidato or "") else pascal(id_ or candidato or "X")
    base, i = n, 2
    while n in usados:
        n, i = f"{base}{i}", i + 1
    usados.add(n)
    return n


def _ruta(id_: str) -> str | None:
    """`Patient.name:NombreOficial.family` -> `name[NombreOficial].family`. None si no se puede expresar (slices de elementos [x])."""
    if "." not in id_:
        return ""
    r = id_.split(".", 1)[1]
    return re.sub(r":([A-Za-z][\w-]*)", r"[\1]", r)


SIGNOS_VITALES_FHIR = {"vitalsigns", "oxygensat", "bp", "bodyheight", "bodyweight", "bodytemp", "heartrate", "resprate", "headcircum", "bmi"}


def _perfiles_de_signos_vitales(sds: list[dict]) -> set[str]:
    """URL de los perfiles del paquete que descienden de los signos vitales de FHIR (traen el slice obligatorio `category:VSCat`)."""
    por_url = {d["url"]: d for d in sds}
    out = set()
    for d in sds:
        actual, vistos = d, set()
        while actual and actual["url"] not in vistos:
            vistos.add(actual["url"])
            base = actual.get("baseDefinition", "")
            if base.startswith(BASE_FHIR) and base.rsplit("/", 1)[-1] in SIGNOS_VITALES_FHIR:
                out.add(d["url"])
                break
            actual = por_url.get(base)
    return out


def _leer_ejemplos(carpeta: Path) -> list[dict]:
    """Recursos de la carpeta `example/` del paquete. Los decimales se leen sin perder ceros (5.50 sigue siendo 5.50)."""
    base = carpeta / "package" if (carpeta / "package").is_dir() else carpeta
    out = []
    for f in sorted((base / "example").glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"), parse_float=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(d, dict) and d.get("resourceType"):
            out.append(d)
    return out


def importar_paquete(carpeta: str | Path, *, con_textos: bool = False, con_ejemplos: bool = True, titulo: str = "Guía importada", id_guia: str = "guia-importada",
                     canonical: str = "", usa_clcore: bool = False, catalogo=None) -> tuple[dict, Informe]:
    """Devuelve (datos para `guardar_plantilla`, informe)."""
    r = _leer(Path(carpeta))
    inf = Informe()
    sds = r.get("StructureDefinition", [])
    css = r.get("CodeSystem", [])
    vss = r.get("ValueSet", [])
    usados: set[str] = set()
    nombre_de_url: dict[str, str] = {}              # url -> nombre en el libro (perfiles, extensiones, CodeSystems y ValueSets)

    for d in sds + css + vss:
        n = _nombre_valido(d.get("name", ""), d.get("id", ""), usados)
        nombre_de_url[d["url"]] = n
        inf.nombres[n] = {"tipo": d["resourceType"], "name": d.get("name", ""), "id": d.get("id", ""), "url": d["url"]}

    usa_cl = [usa_clcore]

    def ref(url: str) -> str:
        """Nombre del libro si el artefacto está en el paquete; si no, el recurso base (Patient) o la URL."""
        url = url.split("|")[0]
        if url in nombre_de_url:
            return nombre_de_url[url]
        if url.startswith(BASE_FHIR) and _cola(url) in RECURSOS_R4 + TIPOS_DATO:
            return _cola(url)
        if catalogo is not None:                        # artefacto de CL Core: se usa su nombre
            for tabla in (catalogo.sd_by_url, catalogo.vs_by_url):
                if url in tabla:
                    usa_cl[0] = True
                    return tabla[url]["id"]
        return url

    datos: dict[str, list[dict]] = {k: [] for k in ("Perfiles", "Elementos", "Extensiones", "ValorExtensiones", "Slices", "CodeSystems", "Conceptos",
                                                    "ValueSets", "Inclusiones", "ParametrosBusqueda", "MapasConceptos", "ReglasMapa", "Operaciones",
                                                    "ParametrosOperacion", "Cuestionarios", "PreguntasCuestionario", "Invariantes")}
    for d in sds:
        if d.get("type") == "Extension":
            _extension(d, datos, nombre_de_url, ref, inf, con_textos)
        elif d.get("derivation") == "constraint" and d.get("kind") in ("resource", "complex-type"):
            _perfil(d, datos, nombre_de_url, ref, inf, con_textos, _Herencia({x["url"]: x for x in sds}, catalogo))
        else:
            inf.falta(f"StructureDefinition de tipo {d.get('kind')}/{d.get('derivation')}", d.get("name", ""))
    for d in css:
        _codesystem(d, datos, nombre_de_url, inf, con_textos)
    for d in vss:
        _valueset(d, datos, nombre_de_url, ref, inf, con_textos)
    for cs in r.get("CapabilityStatement", []):
        nombre_cap = _nombre_valido(cs.get("name", ""), cs.get("id", ""), usados)
        inf.nombres[nombre_cap] = {"tipo": "CapabilityStatement", "name": cs.get("name", ""), "id": cs.get("id", ""), "url": cs.get("url", "")}
        filas = imp_caps.capacidad_desde_json(cs, nombre_cap, con_textos=con_textos, perfiles_propios=set(nombre_de_url.values()))
        for k, v in filas.items():
            datos.setdefault(k, []).extend(v)
        inf.recursos["CapabilityStatement"] += 1
    for tipo, funcion in (("SearchParameter", _parametro_busqueda), ("ConceptMap", _mapa), ("OperationDefinition", _operacion), ("Questionnaire", _cuestionario)):
        for d in r.get(tipo, []):
            funcion(d, datos, nombre_de_url, ref, inf, con_textos, usados)
    for f in datos.get("OperacionesCapacidad", []):
        if f.get("definicion") in nombre_de_url:
            f["definicion"] = nombre_de_url[f["definicion"]]
    for tipo in ("StructureMap", "Bundle"):
        for d in r.get(tipo, []):
            inf.falta(f"{tipo} (el libro aún no tiene hoja para este tipo)", d.get("name") or d.get("id", ""))
    for hoja in HOJAS_CON_ID:                      # el id original, cuando no es el que el libro calcularía solo
        for fila in datos.get(hoja, []):
            info = inf.nombres.get(fila.get("nombre", ""))
            if info and not fila.get("parte_de") and not fila.get("url") and info.get("id") and info["id"] != kebab(fila["nombre"]):
                fila["id"] = info["id"]
    datos["Guía"] = {"id": id_guia, "titulo": titulo, "canonical": canonical or "https://example.org/fhir/ig/importada", "usa_clcore": "Sí" if usa_cl[0] else "No"}
    datos["Documentación"] = []
    datos["Instancias"], datos["Valores"] = ejemplos_desde_json(_leer_ejemplos(Path(carpeta)) if con_ejemplos else [], ref, _nombre_valido, usados, inf,
                                                         signos_vitales=_perfiles_de_signos_vitales(sds))
    return datos, inf


# ---------------------------------------------------------------------------------------------------------------------
def _nombre_nuevo(d: dict, usados: set) -> str:
    return _nombre_valido(d.get("name", ""), d.get("id", ""), usados)


def _parametro_busqueda(d: dict, datos: dict, nombre_de_url: dict, ref, inf: Informe, con_textos: bool, usados: set) -> None:
    n = _nombre_nuevo(d, usados)
    nombre_de_url[d["url"]] = n
    inf.nombres[n] = {"tipo": "SearchParameter", "name": d.get("name", ""), "id": d.get("id", ""), "url": d["url"]}
    fila = {"nombre": n, "codigo": d.get("code", ""), "recursos": ", ".join(d.get("base", [])), "tipo": d.get("type", ""),
            "expresion": d.get("expression", ""), "titulo": d.get("title") or d.get("name", ""),
            "descripcion": d.get("description", "") if con_textos else "",
            "modificadores": ", ".join(d.get("modifier", [])), "comparadores": ", ".join(d.get("comparator", [])),
            "destinos": ", ".join(d.get("target", []))}
    for clave, campo in (("multipleOr", "multiple_o"), ("multipleAnd", "multiple_y")):
        if clave in d:
            fila[campo] = "Sí" if d[clave] else "No"
    if d.get("component"):
        inf.falta("parámetro de búsqueda compuesto (component)", n)
    datos["ParametrosBusqueda"].append(fila)
    inf.recursos["parametros de busqueda"] += 1


def _mapa(d: dict, datos: dict, nombre_de_url: dict, ref, inf: Informe, con_textos: bool, usados: set) -> None:
    n = _nombre_nuevo(d, usados)
    nombre_de_url[d["url"]] = n
    inf.nombres[n] = {"tipo": "ConceptMap", "name": d.get("name", ""), "id": d.get("id", ""), "url": d["url"]}
    datos["MapasConceptos"].append({"nombre": n, "titulo": d.get("title") or d.get("name", ""), "descripcion": d.get("description", "") if con_textos else "",
                                    "origen": ref(d["sourceCanonical"]) if d.get("sourceCanonical") else "",
                                    "destino": ref(d["targetCanonical"]) if d.get("targetCanonical") else ""})
    for g in d.get("group", []):
        so, sd_ = _sistema(g.get("source", ""), nombre_de_url), _sistema(g.get("target", ""), nombre_de_url)
        if g.get("unmapped"):
            inf.falta("regla «unmapped» de un grupo de ConceptMap", n)
        for e in g.get("element", []):
            for t in e.get("target") or [{}]:
                if t.get("dependsOn") or t.get("product"):
                    inf.falta("dependencias (dependsOn/product) en un ConceptMap", n)
                datos["ReglasMapa"].append({
                    "version_origen": g.get("sourceVersion", ""), "version_destino": g.get("targetVersion", ""),
                    "mapa": n, "sistema_origen": so, "sistema_destino": sd_, "codigo_origen": e.get("code", ""),
                    "codigo_destino": t.get("code", ""), "equivalencia": t.get("equivalence", "") if t.get("code") or t.get("equivalence") not in ("", "unmatched") else "",
                    "texto_origen": e.get("display", ""), "texto_destino": t.get("display", ""),
                    "comentario": t.get("comment", "") if con_textos else ""})
    inf.recursos["mapas de conceptos"] += 1


def _operacion(d: dict, datos: dict, nombre_de_url: dict, ref, inf: Informe, con_textos: bool, usados: set) -> None:
    n = _nombre_nuevo(d, usados)
    nombre_de_url[d["url"]] = n
    inf.nombres[n] = {"tipo": "OperationDefinition", "name": d.get("name", ""), "id": d.get("id", ""), "url": d["url"]}
    niveles = [x for x, k in (("sistema", "system"), ("tipo", "type"), ("instancia", "instance")) if d.get(k)]
    fila = {"nombre": n, "codigo": d.get("code", ""), "recursos": ", ".join(d.get("resource", [])), "nivel": ", ".join(niveles),
            "titulo": d.get("title") or d.get("name", ""), "descripcion": d.get("description", "") if con_textos else "",
            "base": d.get("base", ""), "comentario": d.get("comment", "") if con_textos else ""}
    if d.get("kind") == "query":
        fila["tipo_operacion"] = "query"
    if "affectsState" in d:
        fila["afecta_estado"] = "Sí" if d["affectsState"] else "No"
    if d.get("inputProfile") or d.get("outputProfile") or d.get("overload"):
        inf.falta("perfiles de entrada/salida u overload en OperationDefinition", n)
    datos["Operaciones"].append(fila)
    for p in d.get("parameter", []):
        if p.get("part"):
            inf.falta("parámetros anidados (part) en OperationDefinition", f"{n}: {p.get('name')}")
        if p.get("binding"):
            inf.falta("binding de un parámetro de OperationDefinition", f"{n}: {p.get('name')}")
        datos["ParametrosOperacion"].append({
            "operacion": n, "parametro": p.get("name", ""), "uso": p.get("use", ""), "min": str(p.get("min", 0)), "max": p.get("max", "1"),
            "tipo": p.get("type", ""), "perfil": ", ".join(ref(x) for x in p.get("targetProfile", [])), "tipo_busqueda": p.get("searchType", ""),
            "documentacion": p.get("documentation", "") if con_textos else ""})
    inf.recursos["operaciones"] += 1


def _cuestionario(d: dict, datos: dict, nombre_de_url: dict, ref, inf: Informe, con_textos: bool, usados: set) -> None:
    n = _nombre_nuevo(d, usados)
    nombre_de_url[d["url"]] = n
    inf.nombres[n] = {"tipo": "Questionnaire", "name": d.get("name", ""), "id": d.get("id", ""), "url": d["url"]}
    datos["Cuestionarios"].append({"nombre": n, "titulo": d.get("title") or d.get("name", ""), "descripcion": d.get("description", "") if con_textos else "",
                                   "recursos": ", ".join(d.get("subjectType", [])), "basado_en": ", ".join(d.get("derivedFrom", []))})
    if len(d.get("derivedFrom", [])) > 1:
        inf.falta("varios derivedFrom en un Questionnaire", n)
    tipos = {}

    def recoger(items: list) -> None:
        for it in items:
            tipos[it.get("linkId", "")] = it.get("type", "")
            recoger(it.get("item", []))
    recoger(d.get("item", []))

    def recorrer(items: list, padre: str) -> None:
        for it in items:
            fila = {"cuestionario": n, "id": it.get("linkId", ""), "dentro_de": padre, "tipo": it.get("type", ""),
                    "texto": it.get("text", "") if con_textos else "", "prefijo": it.get("prefix", ""), "definicion": it.get("definition", "")}
            for clave, k in (("obligatoria", "required"), ("repite", "repeats"), ("solo_lectura", "readOnly")):
                if k in it:
                    fila[clave] = "Sí" if it[k] else "No"
            if it.get("maxLength"):
                fila["largo_maximo"] = str(it["maxLength"])
            if it.get("answerValueSet"):
                fila["opciones"] = ref(it["answerValueSet"])
            for k in ("answerOption", "initial", "code"):
                if it.get(k):
                    inf.falta(f"«{k}» en una pregunta de Questionnaire", f"{n}: {fila['id']}")
            if it.get("enableWhen"):
                ew = it["enableWhen"]
                if len(ew) > 1:
                    inf.falta("varias condiciones (enableWhen) en una pregunta", f"{n}: {fila['id']}")
                e = ew[0]
                fila["si_pregunta"], fila["si_operador"] = e.get("question", ""), e.get("operator", "")
                if it.get("enableBehavior"):
                    fila["si_comportamiento"] = it["enableBehavior"]
                resp = next((k for k in e if k.startswith("answer")), None)
                v = e.get(resp) if resp else None
                if resp == "answerCoding":
                    sis = _sistema(v["system"], nombre_de_url) if v.get("system") else ""
                    fila["si_respuesta"] = f"{sis}#{v.get('code', '')}"
                elif isinstance(v, bool):
                    fila["si_respuesta"] = "Sí" if v else "No"
                elif v is not None and not isinstance(v, dict):
                    fila["si_respuesta"] = str(v)
                elif v is not None:
                    inf.falta(f"condición con {resp} en un Questionnaire", f"{n}: {fila['id']}")
            datos["PreguntasCuestionario"].append(fila)
            recorrer(it.get("item", []), it.get("linkId", ""))
    recorrer(d.get("item", []), "")
    inf.recursos["cuestionarios"] += 1


def _tipo_texto(tipos: list[dict], ref) -> dict:
    """type[] de un elemento -> columnas del libro (tipo, perfil_tipo, destinos)."""
    out: dict = {}
    if not tipos:
        return out
    if len(tipos) == 1:
        t = tipos[0]
        if t.get("targetProfile"):
            out["destinos"] = ", ".join(ref(p) for p in t["targetProfile"])
        elif t.get("profile"):
            out["perfil_tipo"] = ", ".join(ref(x) for x in t["profile"])
        else:
            out["tipo"] = t["code"]
    else:
        out["tipo"] = " or ".join(t["code"] for t in tipos)
    return out


def _fijo(e: dict) -> dict:
    for k, v in e.items():
        if not k.startswith(("fixed", "pattern")):
            continue
        exacto = {"fijo_exacto": "Sí"} if k.startswith("fixed") else {}
        tipo = k[5:] if k.startswith("fixed") else k[7:]
        if tipo == "Code":
            return {"fijo": v, "fijo_tipo": "código simple", **exacto}
        if tipo in ("String", "Uri", "Url", "Canonical", "Id"):
            return {"fijo": v, "fijo_tipo": "texto", **exacto}
        if tipo in ("Integer", "Decimal"):
            return {"fijo": str(v), "fijo_tipo": "número", **exacto}
        if tipo == "Boolean":
            return {"fijo": "Sí" if v else "No", "fijo_tipo": "booleano", **exacto}
        coding = v if tipo == "Coding" else (v["coding"][0] if tipo == "CodeableConcept" and len(v.get("coding", [])) == 1 and set(v) == {"coding"} else None)
        if coding and coding.get("code") and set(coding) <= {"system", "code", "display"}:
            return {"fijo": coding["code"], "fijo_tipo": "código con sistema", "fijo_sistema": coding.get("system", ""),
                    "fijo_texto": coding.get("display", ""), **exacto}
        return {"_no": k}
    return {}


def _binding(e: dict, ref) -> dict:
    b = e.get("binding")
    if not b or not b.get("valueSet"):
        return {}
    return {"valueset": ref(b["valueSet"]), "fuerza": b.get("strength", "required")}


def _texto_elemento(e: dict, con_textos: bool) -> dict:
    if not con_textos:
        return {}
    return {k: e[o] for k, o in (("resumen", "short"), ("definicion", "definition"), ("comentario", "comment")) if o in e}


class _Herencia:
    """Qué elementos y slices ya definen los perfiles padre (los del paquete y, si se entrega, el catálogo de CL Core)."""

    def __init__(self, por_url: dict, catalogo=None):
        self.por_url, self.catalogo = por_url, catalogo
        self._cache: dict[str, tuple[set, bool]] = {}

    def de(self, url: str) -> tuple[set, bool]:
        """(ids de elementos definidos por los ancestros, si toda la cadena se pudo recorrer)."""
        if url in self._cache:
            return self._cache[url]
        self._cache[url] = (set(), False)                   # corta ciclos
        ids: set = set()
        completo = False
        if url in self.por_url:
            sd = self.por_url[url]
            ids = {e["id"] for e in sd["differential"]["element"]}
            base = sd.get("baseDefinition", "")
            if base.startswith(BASE_FHIR):
                completo = True                             # llegó a un recurso base de FHIR
            else:
                mas, completo = self.de(base)
                ids |= mas
        elif self.catalogo is not None and url in self.catalogo.sd_by_url:
            sd = self.catalogo.sd_by_url[url]
            ids = {e["id"] for e in sd.get("elements", [])}
            completo = True
        self._cache[url] = (ids, completo)
        return ids, completo


def _perfil(d: dict, datos: dict, nombre_de_url: dict, ref, inf: Informe, con_textos: bool, herencia: _Herencia | None = None) -> None:
    nombre = nombre_de_url[d["url"]]
    tipo = d["type"]
    if tipo not in RECURSOS_R4 + TIPOS_DATO:
        inf.falta(f"perfil de {tipo} (tipo sin soporte)", nombre)
        return
    base = d.get("baseDefinition", "")
    padre = "" if base == BASE_FHIR + tipo else ref(base)
    datos["Perfiles"].append({"nombre": nombre, "recurso": tipo, "padre": padre, "titulo": d.get("title") or nombre,
                              "descripcion": d.get("description", "") if con_textos else "Perfil importado de un paquete."})
    inf.recursos["perfiles"] += 1
    slicing: dict[str, dict] = {}
    ordenado_dicho: set[str] = set()
    heredado, conocido = herencia.de(base) if herencia and base else (set(), False)
    for e in d["differential"]["element"]:
        ruta = _ruta(e["id"])
        if ruta is None:
            inf.falta("slice de un elemento de tipo variable (value[x]:valueX)", f"{nombre}: {e['id']}")
            continue
        for c in e.get("constraint", []):
            if c.get("source") not in (None, "", d["url"]):
                continue                               # restricción heredada de otro perfil, solo repetida
            if not c.get("expression"):
                inf.falta("invariante sin expresión FHIRPath", f"{nombre}: {c.get('key', '')}")
                continue
            datos["Invariantes"].append({"clave": c.get("key", ""), "perfil": nombre, "ruta": ruta, "gravedad": c.get("severity", "error"),
                                         "descripcion": c.get("human", "") if con_textos else f"Regla {c.get('key', '')} importada",
                                         "expresion": c["expression"]})
            inf.recursos["invariantes"] += 1
        if ruta == "":
            continue                                   # raíz del perfil (solo textos)
        if "slicing" in e:
            disc = e["slicing"].get("discriminator", [])
            slicing[ruta] = {"disc": disc[0] if disc else {}, "reglas": e["slicing"].get("rules", "open"),
                             "ordenado": "" if "ordered" not in e["slicing"] else ("Sí" if e["slicing"]["ordered"] else "No")}
            if len(disc) > 1:
                inf.falta("slicing con más de un discriminador", f"{nombre}: {ruta}")
        tipos = e.get("type", [])
        es_uso_ext = ruta.endswith("]") and re.search(r"(?:^|\.)(?:modifierE|e)xtension\[[^\]]+\]$", ruta) and tipos and tipos[0]["code"] == "Extension"
        extra = _tipo_texto(tipos, ref) if tipos else {}
        if es_uso_ext:
            if ruta.split(".")[-1].startswith("modifierExtension"):
                inf.falta("modifierExtension", f"{nombre}: {ruta}")
                continue
            perfil_ext = (tipos[0].get("profile") or [""])[0]
            if not perfil_ext:
                inf.falta("uso de extensión sin perfil", f"{nombre}: {ruta}")
                continue
            if perfil_ext not in nombre_de_url:
                _extension_externa(perfil_ext, datos, nombre_de_url)
            datos["Elementos"].append({"perfil": nombre, "ruta": ruta, "min": str(e["min"]) if "min" in e else "", "max": e.get("max", ""),
                                       "ms": "Sí" if e.get("mustSupport") else "", "perfil_tipo": nombre_de_url[perfil_ext] if perfil_ext in nombre_de_url else perfil_ext,
                                       **_texto_elemento(e, con_textos)})
            continue
        fila = {"perfil": nombre, "ruta": ruta, "min": str(e["min"]) if "min" in e else "", "max": e.get("max", ""),
                "ms": "Sí" if e.get("mustSupport") else "", **_binding(e, ref), **extra, **_texto_elemento(e, con_textos)}
        fx = _fijo(e)
        if fx.get("_no"):
            inf.falta(f"valor fijo de tipo {fx['_no']}", f"{nombre}: {ruta}")
        else:
            fila.update(fx)
        sin_tipo_ext = "sliceName" in e and e["path"].endswith(".extension") and "type" not in e   # solo puede ser un slice heredado
        if "sliceName" in e and ((conocido and e["id"] in heredado) or sin_tipo_ext):
            # el padre ya define este slice: aquí solo se restringe -> fila de Elementos con su ruta
            if any(k not in ("perfil", "ruta") and v for k, v in fila.items()):
                datos["Elementos"].append(fila)
            continue
        if "sliceName" in e:
            m = re.match(r"^(.*)\[([^\]]+)\]$", ruta)
            elemento, slice_ = m[1], m[2]
            info = slicing.get(elemento, {})
            disc = info.get("disc", {})
            datos["Slices"].append({"perfil": nombre, "elemento": elemento, "slice": slice_, "min": fila["min"], "max": fila["max"], "ms": fila["ms"],
                                    "discriminador": disc.get("type", ""), "disc_ruta": disc.get("path", ""), "reglas": info.get("reglas", "") if disc else "",
                                    "ordenado": info.get("ordenado", "") if disc and elemento not in ordenado_dicho else ""})
            ordenado_dicho.add(elemento)
            resto = {k: v for k, v in fila.items() if k not in ("min", "max", "ms")}
            if any(k not in ("perfil", "ruta") for k in resto):
                datos["Elementos"].append({**resto})
            continue
        if any(k not in ("perfil", "ruta") and v for k, v in fila.items()):
            datos["Elementos"].append(fila)


def _extension_externa(url: str, datos: dict, nombre_de_url: dict) -> None:
    n = pascal(_cola(url)) or "ExtensionExterna"
    usados = set(nombre_de_url.values())
    base, i = n, 2
    while n in usados:
        n, i = f"{base}{i}", i + 1
    nombre_de_url[url] = n
    datos["Extensiones"].append({"nombre": n, "url": url})


def _valor_de(e: dict | None, ref) -> dict:
    """value[x] de una extensión -> {tipo, valueset, fuerza}."""
    if not e or not e.get("type"):
        return {}
    t = e["type"]
    if len(t) > 1:
        return {"_varios": " or ".join(x["code"] for x in t)}
    t = t[0]
    tipo = t["code"]
    if t.get("targetProfile"):
        tipo = f"Reference({' or '.join(ref(p) for p in t['targetProfile'])})"
    return {"tipo": tipo, **_binding(e, ref)}


def _extension(d: dict, datos: dict, nombre_de_url: dict, ref, inf: Informe, con_textos: bool) -> None:
    nombre = nombre_de_url[d["url"]]
    ctx = [c["expression"] for c in d.get("context", []) if c.get("type") in ("element", "extension")]     # extension: URL de otra extensión
    if any(c.get("type") == "fhirpath" for c in d.get("context", [])):
        inf.falta("contexto de extensión escrito como expresión FHIRPath", nombre)
    for e in d["differential"]["element"]:
        for c in e.get("constraint", []):
            if c.get("source") not in (None, "", d["url"]):
                continue
            ruta_c = e["id"].split(".", 1)[1] if "." in e["id"] else ""
            if not c.get("expression") or ":" in ruta_c:
                inf.falta("invariante en una extensión (sin expresión o dentro de una parte)", f"{nombre}: {c.get('key', '')}")
                continue
            datos["Invariantes"].append({"clave": c.get("key", ""), "perfil": nombre, "ruta": ruta_c, "gravedad": c.get("severity", "error"),
                                         "descripcion": c.get("human", "") if con_textos else f"Regla {c.get('key', '')} importada", "expresion": c["expression"]})
            inf.recursos["invariantes"] += 1
    els = {e["id"]: e for e in d["differential"]["element"]}
    if els.get("Extension.url", {}).get("mustSupport"):
        datos["ValorExtensiones"].append({"extension": nombre, "ruta": "url", "ms": "Sí"})
    fila = {"nombre": nombre, "titulo": d.get("title") or nombre, "descripcion": d.get("description", "") if con_textos else "",
            "contexto": ", ".join(ctx)}
    inf.recursos["extensiones"] += 1
    partes = [e for e in d["differential"]["element"] if re.fullmatch(r"Extension\.extension:[\w-]+", e["id"]) and "sliceName" in e]
    if partes:
        datos["Extensiones"].append(fila)
        for pe in partes:
            slice_ = pe["sliceName"]
            pid = pe["id"]
            nombre_parte = slice_[:1].upper() + slice_[1:]
            codigo_parte = "" if nombre_parte[:1].lower() + nombre_parte[1:] == slice_ else slice_     # p. ej. «Contactado»: el libro lo bajaría a «contactado»
            ve = els.get(f"{pid}.value[x]")
            if els.get(f"{pid}.url", {}).get("mustSupport"):
                datos["ValorExtensiones"].append({"extension": nombre_parte if nombre_parte not in nombre_de_url.values() else f"{nombre}{nombre_parte}", "ruta": "url", "ms": "Sí"})
            v = _valor_de(ve, ref)
            if v.get("_varios"):
                inf.falta("parte de extensión con varios tipos de valor", f"{nombre}: {slice_}")
                v = {}
            datos["Extensiones"].append({"nombre": nombre_parte if nombre_parte not in nombre_de_url.values() else f"{nombre}{nombre_parte}", "titulo": slice_,
                                         "parte_de": nombre, "min": str(pe.get("min", "")), "max": pe.get("max", ""),
                                         "ms": "Sí" if pe.get("mustSupport") else "", "codigo_parte": codigo_parte, **v})
            _reglas_de_valor(els, f"{pid}.value[x].", datos, nombre_parte if nombre_parte not in nombre_de_url.values() else f"{nombre}{nombre_parte}", ref, inf, nombre)
        for e in d["differential"]["element"]:
            if re.match(r"Extension\.extension:[\w-]+\.extension:", e["id"]):
                inf.falta("extensión anidada de más de un nivel", f"{nombre}: {e['id']}")
        return
    ve = els.get("Extension.value[x]")
    v = _valor_de(ve, ref)
    if v.get("_varios"):
        inf.falta("extensión con varios tipos de valor", f"{nombre}: {v['_varios']}")
        v = {}
    datos["Extensiones"].append({**fila, **v})
    _reglas_de_valor(els, "Extension.value[x].", datos, nombre, ref, inf, nombre)


def _reglas_de_valor(els: dict, prefijo: str, datos: dict, destino: str, ref, inf: Informe, ext: str) -> None:
    """Reglas dentro del valor de una extensión (`value[x].coding.code`) -> hoja ValorExtensiones."""
    for id_, e in els.items():
        if id_ == prefijo[:-1]:
            ruta = "[x]"
        elif id_.startswith(prefijo):
            ruta = id_[len(prefijo):]
        else:
            continue
        if ruta == "[x]":
            fila = {"extension": destino, "ruta": ruta, "min": str(e["min"]) if "min" in e else "", "max": e.get("max", ""),
                    "ms": "Sí" if e.get("mustSupport") else ""}
            if any(fila[k] for k in ("min", "max", "ms")):
                datos["ValorExtensiones"].append(fila)
            continue
        if ":" in ruta:
            inf.falta("regla dentro del valor de una extensión con slices", f"{ext}: {ruta}")
            continue
        fila = {"extension": destino, "ruta": ruta, "min": str(e["min"]) if "min" in e else "", "max": e.get("max", ""),
                "ms": "Sí" if e.get("mustSupport") else "", **_binding(e, ref)}
        fx = _fijo(e)
        if fx.get("_no"):
            inf.falta(f"valor fijo de tipo {fx['_no']}", f"{ext}: {ruta}")
        else:
            fila.update(fx)
        if "type" in e:
            inf.falta("cambio de tipo dentro del valor de una extensión", f"{ext}: {ruta}")
        if any(fila.get(k) for k in ("min", "max", "ms", "valueset", "fijo")):
            datos["ValorExtensiones"].append(fila)


def _conceptos(lista: list[dict], salida: list[dict]) -> None:
    for c in lista:
        salida.append(c)
        _conceptos(c.get("concept", []), salida)


def _codesystem(d: dict, datos: dict, nombre_de_url: dict, inf: Informe, con_textos: bool) -> None:
    n = nombre_de_url[d["url"]]
    fila = {"nombre": n, "titulo": d.get("title") or n, "descripcion": d.get("description", "") if con_textos else "CodeSystem importado de un paquete."}
    if d.get("content") and d["content"] != "complete":
        fila["contenido"] = d["content"]
    datos["CodeSystems"].append(fila)
    inf.recursos["codesystems"] += 1
    planos: list[dict] = []
    _conceptos(d.get("concept", []), planos)
    if any(c.get("concept") for c in d.get("concept", [])):
        inf.falta("jerarquía de códigos en un CodeSystem (se aplana)", n)
    if d.get("caseSensitive") is False:
        fila["distingue_mayusculas"] = "No"
    for c in planos:
        datos["Conceptos"].append({"codesystem": n, "codigo": c["code"], "texto": c.get("display") or c["code"],
                                   "definicion": c.get("definition", "") if con_textos else ""})


def _sistema(url: str, nombre_de_url: dict) -> str:
    return nombre_de_url.get(url, url)


def _valueset(d: dict, datos: dict, nombre_de_url: dict, ref, inf: Informe, con_textos: bool) -> None:
    n = nombre_de_url[d["url"]]
    datos["ValueSets"].append({"nombre": n, "titulo": d.get("title") or n, "descripcion": d.get("description", "") if con_textos else "ValueSet importado de un paquete."})
    inf.recursos["valuesets"] += 1
    comp = d.get("compose", {})
    for modo, clave in (("incluir", "include"), ("excluir", "exclude")):
        for inc in comp.get(clave, []):
            sistema = _sistema(inc.get("system", ""), nombre_de_url) if inc.get("system") else ""
            otros = [ref(v) for v in inc.get("valueSet", [])]
            base = {"valueset": n, "sistema": sistema, "modo": modo if modo == "excluir" else ""}
            if len(otros) > 1:
                inf.falta("include con más de un ValueSet (intersección)", n)
            if inc.get("concept"):
                for c in inc["concept"]:
                    datos["Inclusiones"].append({**base, "codigo": c["code"], "texto": c.get("display", "")})
            elif inc.get("filter"):
                for f in inc["filter"]:
                    propiedad = f.get("property", "concept")
                    datos["Inclusiones"].append({**base, "filtro": f["op"], "filtro_valor": f["value"],
                                                 "filtro_propiedad": "" if propiedad == "concept" else propiedad})
                if len(inc["filter"]) > 1:
                    inf.falta("include con varios filtros", n)
            else:
                datos["Inclusiones"].append({**base, "otro_valueset": otros[0] if otros else ""})
    if d.get("expansion") and not comp:
        inf.falta("ValueSet solo con expansión", n)
