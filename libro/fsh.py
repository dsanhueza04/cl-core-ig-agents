"""Traduce el libro (ya revisado) a los archivos de una guía: FSH, sushi-config.yaml y páginas. Sin modelo: determinista."""
from __future__ import annotations

from pathlib import Path

import json
import re

from agents.catalog import CatalogIndex
from generator.render import code, q
from datetime import date

from libro import extensiones
from libro.comun import PAGINAS_GENERADAS, RE_CODIGO_SEGURO, href_menu, texto_de_pagina, es_no, es_si, kebab, lista as _lista, minuscula_inicial, pascal, url_sistema
from libro.esquema import FILTROS_DE_TEXTO, RECURSOS_R4, SISTEMAS_CONOCIDOS
from libro.lector import Libro

PLANTILLA = Path(__file__).resolve().parent.parent / "templates" / "ig-base"
CLCORE_BASE = "https://hl7chile.cl/fhir/ig/clcore/StructureDefinition"
AVISO_REVISION = "Borrador generado con cl-core-ig-agents. Requiere revisión humana antes de cualquier uso."


def id_de(f: dict) -> str:
    """Id del artefacto: el que dice el libro o, si no, el nombre en minúsculas con guiones."""
    return f.get("id") or kebab(f["nombre"])


def cod(c: str) -> str:
    """Código FSH: `#abc` o `#"con espacios"`."""
    return "#" + (c if RE_CODIGO_SEGURO.match(c) else q(c))


class _Constructor:
    def __init__(self, libro: Libro, catalogo: CatalogIndex | None):
        self.l, self.cat = libro, catalogo
        g = libro.guia
        self.id = g.get("id", "")
        self.cs_nombres = {f["nombre"] for f in libro.filas("CodeSystems")}
        self.alias: dict[str, str] = {}          # '$LOINC' -> url
        self.ext = extensiones.indice(libro)

    # ---- referencias a sistemas
    def sistema(self, valor: str) -> str:
        clase, url = url_sistema(valor, self.cs_nombres)
        if clase == "libro":
            return valor
        for nombre, existente in self.alias.items():
            if existente == url:
                return nombre
        base = "$" + (next((k for k, u in SISTEMAS_CONOCIDOS.items() if u == url), None) or _alias_de_url(url)).replace("-", "")
        nombre, n = base, 1
        while nombre in self.alias:               # dos URLs distintas con el mismo nombre corto
            n += 1
            nombre = f"{base}{n}"
        self.alias[nombre] = url
        return nombre

    def _experimental(self) -> str:
        """`true` mientras la guía sea un borrador (el Publisher exige el campo en CodeSystems y ValueSets compartibles)."""
        return "true" if (self.l.guia.get("estado") or "draft") == "draft" else "false"

    def _idioma(self) -> str:
        """Idioma declarado en CodeSystems y ValueSets: sin él, el Publisher no muestra los nombres de los códigos en la expansión."""
        return (self.l.guia.get("idioma") or "es").strip()

    # ---- terminología
    def codesystems(self) -> str:
        bloques = []
        for f in self.l.filas("CodeSystems"):
            n = f["nombre"]
            lineas = [f"CodeSystem: {n}", f"Id: {id_de(f)}", f"Title: {q(f['titulo'] or n)}"]
            if f["descripcion"]:
                lineas.append(f"Description: {q(f['descripcion'])}")
            lineas += ["* ^status = #draft", f"* ^language = #{self._idioma()}", f"* ^experimental = {self._experimental()}", f"* ^caseSensitive = {'false' if es_no(f.get('distingue_mayusculas', '')) else 'true'}",
                       f"* ^content = #{f['contenido'] or 'complete'}"]
            for c in self.l.filas("Conceptos"):
                if c["codesystem"] == n:
                    extra = f" {q(c['definicion'])}" if c["definicion"] else ""
                    lineas.append(f"* {cod(c['codigo'])} {q(c['texto'])}{extra}")
            bloques.append("\n".join(lineas) + "\n")
        return "\n".join(bloques)

    def _inclusion(self, i: dict) -> str:
        """Una fila de Inclusiones -> una regla `compose` de FSH."""
        modo = "exclude" if i["modo"] == "excluir" else "include"
        s = self.sistema(i["sistema"]) if i["sistema"] else ""
        if i["otro_valueset"]:
            otro = f"valueset {self.vs_ref(i['otro_valueset'])}"
            return f"* {modo} codes from " + (f"system {s} and {otro}" if s else otro)
        if i["filtro"]:
            valor = q(i["filtro_valor"]) if i["filtro"] in FILTROS_DE_TEXTO else cod(i["filtro_valor"])
            return f"* {modo} codes from system {s} where {i.get('filtro_propiedad') or 'concept'} {i['filtro']} {valor}"
        if i["codigo"]:
            return f"* {'exclude ' if modo == 'exclude' else ''}{s}{cod(i['codigo'])}" + (f" {q(i['texto'])}" if i.get("texto") else "")
        return f"* {modo} codes from system {s}"

    def valuesets(self) -> str:
        bloques = []
        for f in self.l.filas("ValueSets"):
            n = f["nombre"]
            lineas = [f"ValueSet: {n}", f"Id: {id_de(f)}", f"Title: {q(f['titulo'] or n)}"]
            if f["descripcion"]:
                lineas.append(f"Description: {q(f['descripcion'])}")
            lineas += ["* ^status = #draft", f"* ^language = #{self._idioma()}", f"* ^experimental = {self._experimental()}"]
            for i in self.l.filas("Inclusiones"):
                if i["valueset"] == n:
                    lineas.append(self._inclusion(i))
            bloques.append("\n".join(lineas) + "\n")
        return "\n".join(bloques)

    # ---- perfiles
    def fijo_de(self, r: dict) -> str:
        """Valor fijo de una fila (con texto del código y «exactly» si corresponde)."""
        v = self.valor_fijo(r["fijo_tipo"], r["fijo"], r["fijo_sistema"], r.get("fijo_texto", ""))
        return v + (" (exactly)" if es_si(r.get("fijo_exacto", "")) else "")

    def valor_fijo(self, tipo: str, valor: str, sistema: str, texto: str = "") -> str:
        if tipo == "texto":
            return q(valor)
        if tipo == "código simple":
            return cod(valor)
        if tipo == "código con sistema":
            return f"{self.sistema(sistema)}{cod(valor)}" + (f" {q(texto)}" if texto else "")
        if tipo == "número":
            return valor
        return "true" if es_si(valor) else "false"

    def parent(self, f: dict) -> str:
        p = f["padre"]
        if not p:
            return f["recurso"]
        if p in {x["nombre"] for x in self.l.filas("Perfiles")}:
            return p
        if self.cat and p in self.cat.sd:
            return self.cat.sd[p]["url"]
        return p if p not in RECURSOS_R4 else p

    def extensiones(self) -> str:
        bloques = []
        for f in self.l.filas("Extensiones"):
            if f["parte_de"] or f["url"]:          # las partes van dentro de su extensión; las externas no se vuelven a definir
                continue
            n = f["nombre"]
            lineas = [f"Extension: {n}", f"Id: {id_de(f)}", f"Title: {q(f['titulo'] or n)}"]
            if f["descripcion"]:
                lineas.append(f"Description: {q(f['descripcion'])}")
            if f["contexto"]:
                lineas.append("Context: " + ", ".join(c.strip() for c in f["contexto"].split(",") if c.strip()))
            lineas += ["* ^status = #draft", f"* ^experimental = {self._experimental()}"]
            partes = self.ext.partes_de(n)
            if partes:
                lineas.append("* extension contains " + " and ".join(
                    f"{extensiones.slice_de(p)} {p['min'] or '0'}..{p['max'] or '1'}" + (" MS" if es_si(p["ms"]) else "") for p in partes))
                lineas.append("* value[x] 0..0")
                lineas += self._url_ms(f, "")
                for p in partes:
                    sl = f"extension[{extensiones.slice_de(p)}]"
                    if p["titulo"]:
                        lineas.append(f"* {sl} ^short = {q(p['titulo'])}")
                    if p["descripcion"]:
                        lineas.append(f"* {sl} ^definition = {q(p['descripcion'])}")
                    lineas += self._url_ms(p, f"{sl}.")
                    lineas += self._valor_extension(p, f"{sl}.")
            else:
                lineas += self._url_ms(f, "")
                lineas += self._valor_extension(f, "")
            for inv in self.l.filas("Invariantes"):
                if inv["perfil"] == n:
                    lineas.append(f"* {inv['ruta'] + ' ' if inv['ruta'] else ''}obeys {inv['clave']}")
            bloques.append("\n".join(lineas) + "\n")
        return "\n".join(bloques)

    def _url_ms(self, f: dict, prefijo: str) -> list[str]:
        """Reglas sobre Extension.url (por ahora, Must Support), escritas en ValorExtensiones con el campo «url»."""
        return [f"* {prefijo}url MS" for r in self.l.filas("ValorExtensiones")
                if r["extension"] == f["nombre"] and r["ruta"] == "url" and es_si(r["ms"])]

    def _valor_extension(self, f: dict, prefijo: str) -> list[str]:
        if not f["tipo"]:
            return []
        out = [f"* {prefijo}value[x] only {f['tipo']}"]
        if f["valueset"]:
            out.append(f"* {prefijo}value[x] from {self.vs_ref(f['valueset'])} ({f['fuerza'] or 'required'})")
        valor = f"{prefijo}{extensiones.sufijo_valor(f['tipo'])}"
        for r in self.l.filas("ValorExtensiones"):
            if r["extension"] != f["nombre"]:
                continue
            if r["ruta"] == "url":
                continue
            ruta = f"{prefijo}value[x]" if r["ruta"] == "[x]" else f"{valor}.{r['ruta']}"
            card = f"{r['min']}..{r['max']}" if (r["min"] or r["max"]) else ""
            ms = " MS" if es_si(r["ms"]) else ""
            if card or ms:
                out.append(f"* {ruta} {(card + ms).strip()}")
            if r["valueset"]:
                out.append(f"* {ruta} from {self.vs_ref(r['valueset'])} ({r['fuerza'] or 'required'})")
            if r["fijo"]:
                out.append(f"* {ruta} = {self.fijo_de(r)}")
        return out

    def _es_uso_de_extension(self, e: dict):
        r = extensiones.resolver(e["ruta"], self.ext)
        return r if r and r[0] in ("simple", "compleja") else None

    def _slices(self, perfil: str) -> list[str]:
        grupos: dict[str, list[dict]] = {}
        for f in self.l.filas("Slices"):
            if f["perfil"] == perfil:
                grupos.setdefault(f["elemento"], []).append(f)
        lineas = []
        for el, filas in grupos.items():
            tipo = next((f["discriminador"] for f in filas if f["discriminador"]), "")
            ruta = next((f["disc_ruta"] for f in filas if f["disc_ruta"]), "")
            reglas = next((f["reglas"] for f in filas if f["reglas"]), "")
            orden = next((f["ordenado"] for f in filas if f["ordenado"]), "")
            if tipo:
                lineas.append(f"* {el} ^slicing.discriminator[0].type = #{tipo}")
                lineas.append(f"* {el} ^slicing.discriminator[0].path = {q(ruta or '$this')}")
                lineas.append(f"* {el} ^slicing.rules = #{reglas or 'open'}")
                if orden:
                    lineas.append(f"* {el} ^slicing.ordered = {'true' if es_si(orden) else 'false'}")
            lineas.append(f"* {el} contains " + " and ".join(
                f"{f['slice']} {f['min'] or '0'}..{f['max'] or '*'}" + (" MS" if es_si(f["ms"]) else "") for f in filas))
            for f in filas:
                sl = f"{el}[{f['slice']}]"
                if f["descripcion"]:
                    lineas.append(f"* {sl} ^short = {q(f['descripcion'])}")
                if f["fijo"]:
                    destino = sl if ruta in ("", "$this") else f"{sl}.{ruta}"
                    lineas.append(f"* {destino} = {self.valor_fijo(f['fijo_tipo'], f['fijo'], f['fijo_sistema'])}")
        return lineas

    def perfiles(self) -> str:
        bloques = []
        for f in self.l.filas("Perfiles"):
            n = f["nombre"]
            lineas = [f"Profile: {n}", f"Parent: {self.parent(f)}", f"Id: {id_de(f)}", f"Title: {q(f['titulo'] or n)}"]
            desc = " ".join(x for x in (f["descripcion"], f["justificacion"]) if x)
            if desc:
                lineas.append(f"Description: {q(desc)}")
            lineas += ["* ^status = #draft", f"* ^experimental = {self._experimental()}"]
            filas = [e for e in self.l.filas("Elementos") if e["perfil"] == n]
            usos = [e for e in filas if self._es_uso_de_extension(e)]
            def declarar(e):
                _, ext = self._es_uso_de_extension(e)
                ruta = e["ruta"]
                pre, slice_ = ruta[:ruta.rindex("extension[")], re.search(r"extension\[(\w+)\]$", ruta)[1]
                return (f"* {pre}extension contains {ext['url'] or ext['nombre']} named {slice_} {e['min'] or '0'}..{e['max'] or '1'}"
                        + (" MS" if es_si(e["ms"]) else ""))

            # Primero se declaran las extensiones y los slices; luego se usan. Una extensión dentro de un slice
            # (name[NombreOficial].family.extension) solo puede declararse después de crear ese slice.
            def declarar_con_textos(e):
                return [declarar(e)] + self._textos(e, f"{e['ruta']}")

            for e in usos:
                if "[" not in e["ruta"][:e["ruta"].rindex("extension[")]:
                    lineas += declarar_con_textos(e)
            lineas += self._slices(n)
            for e in usos:
                if "[" in e["ruta"][:e["ruta"].rindex("extension[")]:
                    lineas += declarar_con_textos(e)
            for e in (x for x in filas if x not in usos):
                ruta = e["ruta"]
                card = f"{e['min']}..{e['max']}" if (e["min"] or e["max"]) else ""
                ms = " MS" if es_si(e["ms"]) else ""
                if card or ms:
                    lineas.append(f"* {ruta} {(card + ms).strip()}")
                if e["tipo"]:
                    lineas.append(f"* {ruta} only {e['tipo']}")
                if e["perfil_tipo"]:
                    lineas.append(f"* {ruta} only {' or '.join(self.ref_perfil(x) for x in _lista(e['perfil_tipo']))}")
                if e["destinos"]:
                    lineas.append(f"* {ruta} only Reference({' or '.join(self.ref_perfil(d) for d in _lista(e['destinos']))})")
                if e["valueset"]:
                    lineas.append(f"* {ruta} from {self.vs_ref(e['valueset'])} ({e['fuerza'] or 'required'})")
                if e["fijo"]:
                    lineas.append(f"* {ruta} = {self.fijo_de(e)}")
                lineas += self._textos(e, ruta)
            for inv in self.l.filas("Invariantes"):
                if inv["perfil"] == n:
                    lineas.append(f"* {inv['ruta'] + ' ' if inv['ruta'] else ''}obeys {inv['clave']}")
            bloques.append("\n".join(lineas) + "\n")
        definidas = set()
        for inv in self.l.filas("Invariantes"):
            if inv["clave"] in definidas:
                continue
            definidas.add(inv["clave"])
            bloques.append("\n".join([f"Invariant: {inv['clave']}", f"Description: {q(inv['descripcion'])}", f"Severity: #{inv['gravedad']}",
                                      f"Expression: {q(inv['expresion'])}"]) + "\n")
        return "\n".join(bloques)

    def _textos(self, e: dict, ruta: str) -> list[str]:
        """Resumen, definición y comentario de un elemento (short, definition, comment)."""
        return [f"* {ruta} ^{fsh} = {q(e[campo])}" for campo, fsh in (("resumen", "short"), ("definicion", "definition"), ("comentario", "comment"))
                if e.get(campo)]

    def ref_perfil(self, nombre: str) -> str:
        """Nombre con que se escribe un perfil en `only` / `Reference(...)`: los del libro por nombre, los de CL Core por URL."""
        if nombre in {x["nombre"] for x in self.l.filas("Perfiles")} or nombre in RECURSOS_R4:
            return nombre
        if self.cat and nombre in self.cat.sd:
            return self.cat.sd[nombre]["url"]
        return nombre

    def vs_ref(self, vs: str) -> str:
        if vs in {x["nombre"] for x in self.l.filas("ValueSets")}:
            return vs
        if self.cat and vs in self.cat.vs:
            return self.cat.vs[vs]["url"]
        return vs

    # ---- instancias
    def valor(self, v: dict) -> str:
        t, x = v["tipo"], v["valor"]
        if t == "texto":
            return q(x)
        if t == "código simple":
            return cod(x)
        if t == "código con sistema":
            return f"{self.sistema(v['sistema'])}{cod(x)}" + (f" {q(v['texto'])}" if v["texto"] else "")
        if t == "número":
            return x
        if t == "cantidad":
            self.alias["$UCUM"] = SISTEMAS_CONOCIDOS["UCUM"]
            return f"{x} '{v['unidad']}'" + (f" {q(v['texto'])}" if v["texto"] else "")
        if t == "booleano":
            return "true" if es_si(x) else "false"
        if t in ("fecha", "fecha y hora"):
            return q(x)
        if t == "recurso incluido":
            return x
        return f"Reference({x})"

    def instancias(self) -> str:
        bloques = []
        for f in self.l.filas("Instancias"):
            n = f["nombre"]
            of = f["perfil"]
            lineas = [f"Instance: {n}", f"InstanceOf: {of}", f"Title: {q(f['titulo'] or n)}"]
            if f["descripcion"]:
                lineas.append(f"Description: {q(f['descripcion'])}")
            lineas.append(f"Usage: #{'definition' if f['uso'] == 'definición' else 'example'}")
            if f["id"] and f["id"] != n:
                lineas.append(f"* id = {q(f['id'])}")
            for v in self.l.filas("Valores"):
                if v["instancia"] == n:
                    lineas.append(f"* {extensiones.ruta_completa(v['ruta'], self.ext)} = {self.valor(v)}")
            bloques.append("\n".join(lineas) + "\n")
        return "\n".join(bloques)

    # ---- parámetros de búsqueda, mapas de conceptos y operaciones
    def _canon(self, valor: str, nombres: set) -> str:
        """Referencia a un artefacto: por nombre si es de este libro, si no por URL."""
        if valor in nombres:
            return f"Canonical({valor})"
        if self.cat and valor in self.cat.sd:
            return q(self.cat.sd[valor]["url"])
        if self.cat and valor in self.cat.vs:
            return q(self.cat.vs[valor]["url"])
        return q(valor)

    def _uri_sistema(self, valor: str) -> str:
        """CodeSystem como URI: los del libro por nombre, los conocidos por su alias."""
        clase, url = url_sistema(valor, self.cs_nombres)
        if clase == "libro":
            return f"Canonical({valor})"
        return self.sistema(valor) if clase in ("conocido", "url") else q(valor)

    def parametros_busqueda(self) -> str:
        bloques = []
        for f in self.l.filas("ParametrosBusqueda"):
            n = f["nombre"]
            lineas = [f"Instance: {n}", "InstanceOf: SearchParameter", f"Title: {q(f['titulo'] or n)}", "Usage: #definition",
                      *([f"* id = {q(f['id'])}"] if f["id"] else []), f"* name = {q(n)}", f"* status = #{self.l.guia.get('estado') or 'draft'}", f"* experimental = {self._experimental()}",
                      f"* description = {q(f['descripcion'] or f['titulo'] or n)}", f"* code = {cod(f['codigo'])}"]
            lineas += [f"* base[{i}] = #{b}" for i, b in enumerate(_lista(f["recursos"]))]
            lineas.append(f"* type = #{f['tipo']}")
            if f["expresion"]:
                lineas.append(f"* expression = {q(f['expresion'])}")
            if f["multiple_o"]:
                lineas.append(f"* multipleOr = {'true' if es_si(f['multiple_o']) else 'false'}")
            if f["multiple_y"]:
                lineas.append(f"* multipleAnd = {'true' if es_si(f['multiple_y']) else 'false'}")
            lineas += [f"* comparator[{i}] = #{c}" for i, c in enumerate(_lista(f["comparadores"]))]
            lineas += [f"* modifier[{i}] = #{m}" for i, m in enumerate(_lista(f["modificadores"]))]
            lineas += [f"* target[{i}] = #{t}" for i, t in enumerate(_lista(f["destinos"]))]
            bloques.append("\n".join(lineas) + "\n")
        return "\n".join(bloques)

    def mapas(self) -> str:
        bloques = []
        vss = {x["nombre"] for x in self.l.filas("ValueSets")}
        for f in self.l.filas("MapasConceptos"):
            n = f["nombre"]
            lineas = [f"Instance: {n}", "InstanceOf: ConceptMap", f"Title: {q(f['titulo'] or n)}", "Usage: #definition",
                      *([f"* id = {q(f['id'])}"] if f["id"] else []), f"* name = {q(n)}", f"* title = {q(f['titulo'] or n)}", f"* status = #{self.l.guia.get('estado') or 'draft'}", f"* experimental = {self._experimental()}"]
            if f["descripcion"]:
                lineas.append(f"* description = {q(f['descripcion'])}")
            if f["origen"]:
                lineas.append(f"* sourceCanonical = {self._canon(f['origen'], vss)}")
            if f["destino"]:
                lineas.append(f"* targetCanonical = {self._canon(f['destino'], vss)}")
            grupos: dict[tuple[str, str], dict[str, list[dict]]] = {}
            for r in self.l.filas("ReglasMapa"):
                if r["mapa"] == n:
                    grupos.setdefault((r["sistema_origen"], r["sistema_destino"]), {}).setdefault(r["codigo_origen"], []).append(r)
            for gi, ((so, sd_), elementos) in enumerate(grupos.items()):
                primera = next(iter(elementos.values()))[0]
                lineas.append(f"* group[{gi}].source = {self._uri_sistema(so)}")
                if primera["version_origen"]:
                    lineas.append(f"* group[{gi}].sourceVersion = {q(primera['version_origen'])}")
                lineas.append(f"* group[{gi}].target = {self._uri_sistema(sd_)}")
                if primera["version_destino"]:
                    lineas.append(f"* group[{gi}].targetVersion = {q(primera['version_destino'])}")
                for ei, (codigo, reglas) in enumerate(elementos.items()):
                    pre = f"* group[{gi}].element[{ei}]"
                    lineas.append(f"{pre}.code = {cod(codigo)}")
                    if reglas[0]["texto_origen"]:
                        lineas.append(f"{pre}.display = {q(reglas[0]['texto_origen'])}")
                    for ti, r in enumerate(reglas):
                        t = f"{pre}.target[{ti}]"
                        if r["codigo_destino"]:
                            lineas.append(f"{t}.code = {cod(r['codigo_destino'])}")
                        if r["texto_destino"]:
                            lineas.append(f"{t}.display = {q(r['texto_destino'])}")
                        lineas.append(f"{t}.equivalence = #{r['equivalencia'] or ('equivalent' if r['codigo_destino'] else 'unmatched')}")
                        if r["comentario"]:
                            lineas.append(f"{t}.comment = {q(r['comentario'])}")
            bloques.append("\n".join(lineas) + "\n")
        return "\n".join(bloques)

    def cuestionarios(self) -> str:
        bloques = []
        vss = {x["nombre"] for x in self.l.filas("ValueSets")}
        for f in self.l.filas("Cuestionarios"):
            n = f["nombre"]
            lineas = [f"Instance: {n}", "InstanceOf: Questionnaire", f"Title: {q(f['titulo'] or n)}", "Usage: #definition",
                      *([f"* id = {q(f['id'])}"] if f["id"] else []), f"* name = {q(n)}", f"* title = {q(f['titulo'] or n)}", f"* status = #{self.l.guia.get('estado') or 'draft'}", f"* experimental = {self._experimental()}"]
            if f["descripcion"]:
                lineas.append(f"* description = {q(f['descripcion'])}")
            lineas += [f"* subjectType[{i}] = #{r}" for i, r in enumerate(_lista(f["recursos"]))]
            if f["basado_en"]:
                lineas.append(f"* derivedFrom[0] = {q(f['basado_en'])}")
            preguntas = [x for x in self.l.filas("PreguntasCuestionario") if x["cuestionario"] == n]
            tipo_de = {x["id"]: x["tipo"] for x in preguntas}
            hijos: dict[str, list[dict]] = {}
            for x in preguntas:
                hijos.setdefault(x["dentro_de"], []).append(x)

            def escribir(padre: str, prefijo: str) -> None:
                for i, x in enumerate(hijos.get(padre, [])):
                    pre = f"{prefijo}item[{i}]"
                    lineas.append(f"* {pre}.linkId = {q(x['id'])}")
                    if x["texto"]:
                        lineas.append(f"* {pre}.text = {q(x['texto'])}")
                    lineas.append(f"* {pre}.type = #{x['tipo']}")
                    for campo, fhir in (("obligatoria", "required"), ("repite", "repeats"), ("solo_lectura", "readOnly")):
                        if x[campo]:
                            lineas.append(f"* {pre}.{fhir} = {'true' if es_si(x[campo]) else 'false'}")
                    if x["largo_maximo"]:
                        lineas.append(f"* {pre}.maxLength = {x['largo_maximo']}")
                    if x["prefijo"]:
                        lineas.append(f"* {pre}.prefix = {q(x['prefijo'])}")
                    if x["definicion"]:
                        lineas.append(f"* {pre}.definition = {q(x['definicion'])}")
                    if x["opciones"]:
                        lineas.append(f"* {pre}.answerValueSet = {self._canon(x['opciones'], vss)}")
                    if x["si_pregunta"]:
                        op = x["si_operador"] or "="
                        lineas.extend([f"* {pre}.enableWhen[0].question = {q(x['si_pregunta'])}", f"* {pre}.enableWhen[0].operator = {cod(op)}",
                                   f"* {pre}.enableWhen[0].{self._respuesta_condicion(tipo_de.get(x['si_pregunta'], ''), op, x['si_respuesta'])}"])
                        if x["si_comportamiento"]:
                            lineas.append(f"* {pre}.enableBehavior = #{x['si_comportamiento']}")
                    escribir(x["id"], f"{pre}.")

            escribir("", "")
            bloques.append("\n".join(lineas) + "\n")
        return "\n".join(bloques)

    def _respuesta_condicion(self, tipo: str, operador: str, valor: str) -> str:
        """`answer[x]` de una condición, según el tipo de la pregunta de la que depende."""
        if operador == "exists":
            return f"answerBoolean = {'true' if es_si(valor) or not valor else 'false'}"
        if tipo == "boolean":
            return f"answerBoolean = {'true' if es_si(valor) or valor.lower() == 'true' else 'false'}"
        if tipo in ("integer", "decimal"):
            return f"answer{'Integer' if tipo == 'integer' else 'Decimal'} = {valor}"
        if tipo in ("date", "dateTime", "time"):
            return f"answer{tipo[0].upper()}{tipo[1:]} = {valor}"
        if tipo in ("choice", "open-choice"):
            sistema, _, codigo = valor.rpartition("#")
            return f"answerCoding = {self.sistema(sistema)}{cod(codigo)}"
        return f"answerString = {q(valor)}"

    def operaciones(self) -> str:
        bloques = []
        perfiles = {x["nombre"] for x in self.l.filas("Perfiles")}
        for f in self.l.filas("Operaciones"):
            n = f["nombre"]
            niveles = {x.strip().lower() for x in _lista(f["nivel"])}
            lineas = [f"Instance: {n}", "InstanceOf: OperationDefinition", f"Title: {q(f['titulo'] or n)}", "Usage: #definition",
                      *([f"* id = {q(f['id'])}"] if f["id"] else []), f"* name = {q(n)}", f"* title = {q(f['titulo'] or n)}", f"* status = #{self.l.guia.get('estado') or 'draft'}", f"* experimental = {self._experimental()}",
                      f"* kind = #{f['tipo_operacion'] or 'operation'}", f"* description = {q(f['descripcion'] or f['titulo'] or n)}", f"* code = {cod(f['codigo'])}"]
            if f["base"]:
                lineas.append(f"* base = {q(f['base'])}")
            lineas += [f"* resource[{i}] = #{r}" for i, r in enumerate(_lista(f["recursos"]))]
            lineas += [f"* system = {'true' if 'sistema' in niveles else 'false'}", f"* type = {'true' if 'tipo' in niveles else 'false'}",
                       f"* instance = {'true' if 'instancia' in niveles else 'false'}"]
            if f["afecta_estado"]:
                lineas.append(f"* affectsState = {'true' if es_si(f['afecta_estado']) else 'false'}")
            if f["comentario"]:
                lineas.append(f"* comment = {q(f['comentario'])}")
            for i, p in enumerate(x for x in self.l.filas("ParametrosOperacion") if x["operacion"] == n):
                pre = f"* parameter[{i}]"
                lineas += [f"{pre}.name = {cod(p['parametro'])}", f"{pre}.use = #{p['uso']}", f"{pre}.min = {p['min'] or 0}", f"{pre}.max = {q(p['max'] or '1')}"]
                if p["documentacion"]:
                    lineas.append(f"{pre}.documentation = {q(p['documentacion'])}")
                if p["tipo"]:
                    lineas.append(f"{pre}.type = #{p['tipo']}")
                if p["tipo_busqueda"]:
                    lineas.append(f"{pre}.searchType = #{p['tipo_busqueda']}")
                lineas += [f"{pre}.targetProfile[{j}] = {self._canon(x, perfiles)}" for j, x in enumerate(_lista(p["perfil"]))]
            bloques.append("\n".join(lineas) + "\n")
        return "\n".join(bloques)

    def capacidades(self) -> str:
        from libro import capacidades as cap
        exp_url = "http://hl7.org/fhir/StructureDefinition/capabilitystatement-expectation"

        def md(texto: str) -> str:
            """Texto con varios párrafos o listas: FSH admite cadenas de varias líneas entre tres comillas."""
            return '"""' + texto.strip().replace('"""', '"') + '"""' if "\n" in texto.strip() else q(texto)

        def con_expectativa(ruta: str, valor: str) -> list[str]:
            return [f"* {ruta}.extension[{exp_url}].valueCode = #{valor}"] if valor else []

        bloques = []
        for f in self.l.filas("Capacidades"):
            n = f["nombre"]
            formatos = _lista(f["formato"]) or ["json"]
            lineas = [f"Instance: {n}", "InstanceOf: CapabilityStatement", f"Title: {q(f['titulo'] or n)}"]
            if f["descripcion"]:
                lineas.append(f"Description: {q(f['descripcion'])}")
            lineas += ["Usage: #definition", *([f"* id = {q(f['id'])}"] if f["id"] else []), f"* name = {q(n)}", f"* title = {q(f['titulo'] or n)}", f"* status = #{self.l.guia.get('estado') or 'draft'}", f"* experimental = {self._experimental()}",
                       f"* date = \"{date.today().isoformat()}\"", "* kind = #requirements", "* fhirVersion = #4.0.1"]
            if f["descripcion"]:
                lineas.append(f"* description = {q(f['descripcion'])}")
            if f["derechos"]:
                lineas.append(f"* copyright = {md(f['derechos'])}")
            lineas += [f"* format[{i}] = {code(x)}" for i, x in enumerate(formatos)]
            lineas += [f"* patchFormat[{i}] = {code(x)}" for i, x in enumerate(_lista(f["formato_parche"]))]
            lineas.append(f"* rest[0].mode = #{f['modo']}")
            if f["documentacion"]:
                lineas.append(f"* rest[0].documentation = {md(f['documentacion'])}")
            for j, op in enumerate(cap.operaciones(self.l, n, "")):
                lineas.append(f"* rest[0].interaction[{j}].code = #{op['codigo']}")
                lineas += con_expectativa(f"rest[0].interaction[{j}]", op["expectativa"])
            nombres_ops = {x["nombre"] for x in self.l.filas("Operaciones")}
            for j, op in enumerate(cap.operaciones_propias(self.l, n, "")):
                lineas.append(f"* rest[0].operation[{j}].name = {q(op['nombre'])}")
                lineas.append(f"* rest[0].operation[{j}].definition = {self._canon(op['definicion'], nombres_ops)}")
                lineas += con_expectativa(f"rest[0].operation[{j}]", op["expectativa"])
            for i, r in enumerate(x for x in self.l.filas("RecursosCapacidad") if x["capacidad"] == n):
                b = f"rest[0].resource[{i}]"
                lineas.append(f"* {b}.type = #{r['recurso']}")
                lineas += con_expectativa(b, r["expectativa"])
                for k, item in enumerate(_lista(r["perfil"])):
                    nombre_p, esperado_p = cap.separar_expectativa(item)
                    ref = self.ref_perfil(nombre_p)
                    lineas.append(f"* {b}.supportedProfile[{k}] = " + (q(ref) if ref.startswith("http") else f"Canonical({ref})"))
                    lineas += con_expectativa(f"{b}.supportedProfile[{k}]", esperado_p or r["perfil_expectativa"])
                if r["documentacion"]:
                    lineas.append(f"* {b}.documentation = {md(r['documentacion'])}")
                for j, op in enumerate(cap.operaciones(self.l, n, r["recurso"])):
                    lineas.append(f"* {b}.interaction[{j}].code = #{op['codigo']}")
                    lineas += con_expectativa(f"{b}.interaction[{j}]", op["expectativa"])
                for j, op in enumerate(cap.operaciones_propias(self.l, n, r["recurso"])):
                    lineas.append(f"* {b}.operation[{j}].name = {q(op['nombre'])}")
                    lineas.append(f"* {b}.operation[{j}].definition = {self._canon(op['definicion'], nombres_ops)}")
                    lineas += con_expectativa(f"{b}.operation[{j}]", op["expectativa"])
                for campo, fsh_campo, es_codigo in (("incluir", "searchInclude", False), ("incluir_inverso", "searchRevInclude", False), ("referencias", "referencePolicy", True)):
                    for j, it in enumerate(_lista(r[campo])):
                        valor, esperado = cap.separar_expectativa(it)
                        lineas.append(f"* {b}.{fsh_campo}[{j}] = " + (f"#{valor}" if es_codigo else q(valor)))
                        lineas += con_expectativa(f"{b}.{fsh_campo}[{j}]", esperado)
                for j, bq in enumerate(cap.busquedas(self.l, n, r["recurso"])):
                    sp = f"{b}.searchParam[{j}]"
                    lineas += [f"* {sp}.name = {q(bq['nombre'])}", f"* {sp}.type = #{bq['tipo']}"]
                    lineas += con_expectativa(sp, bq["expectativa"])
                    if bq["definicion"]:
                        lineas.append(f"* {sp}.definition = {q(bq['definicion'])}")
                    if bq["documentacion"]:
                        lineas.append(f"* {sp}.documentation = {md(bq['documentacion'])}")
            bloques.append("\n".join(lineas) + "\n")
        return "\n".join(bloques)

    # ---- guía
    def config(self) -> str:
        g = self.l.guia
        nombre = pascal(g["id"])
        canonical = g.get("canonical") or f"http://example.org/fhir/ig/{g['id']}"
        cfg: dict = {
            "id": g["id"], "canonical": canonical, "name": nombre, "title": g["titulo"],
            "description": g.get("descripcion") or g["titulo"],
            "status": g.get("estado") or "draft", "version": g.get("version") or "0.1.0", "fhirVersion": "4.0.1",
            "copyrightYear": "2026+", "releaseLabel": "ci-build", "license": g.get("licencia") or "CC0-1.0",
            "jurisdiction": 'urn:iso:std:iso:3166#CL "Chile"',
            "publisher": {"name": g.get("publicador") or "(sin publicador indicado)"},
        }
        if g.get("contacto", "").startswith("http"):
            cfg["publisher"]["url"] = g["contacto"]          # un correo no va aquí: el Publisher lo trata como enlace roto
        deps = {}
        if not es_no(g.get("usa_clcore", "")):
            deps["hl7.fhir.cl.clcore"] = "1.9.3"
        for linea in g.get("dependencias", "").replace(";", "\n").splitlines():
            if "#" in linea:
                paquete, version = linea.strip().split("#", 1)
                deps[paquete.strip()] = version.strip()
        if deps:
            cfg["dependencies"] = deps
        paginas = self.paginas()
        cfg["pages"] = self._arbol_paginas(paginas)
        cfg["menu"] = self._menu()
        cfg["instanceOptions"] = {"manualSliceOrdering": True}
        return f"# {AVISO_REVISION}\n" + _yaml(cfg)

    def _paginas_ids(self) -> dict[str, tuple[str, str]]:
        """{id: (título, markdown)} con los ids tal como los escribió el autor (`inicio`, no `index`)."""
        out = {}
        for f in self.l.filas("Documentación"):
            texto, _ = texto_de_pagina(self.l.base, f["texto"])      # el verificador ya avisó si el archivo no se puede leer
            out[f["pagina"]] = (f["titulo"], texto)
        if "inicio" not in out:
            out["inicio"] = ("Inicio", self.borrador_inicio())
        if "requisitos" not in out and self.l.filas("Perfiles"):
            out["requisitos"] = ("Requisitos de esta guía", self.requisitos())
        for pid, generador in (("must-support", self.must_support), ("cambios", self.cambios)):
            if pid not in out and any(f["destino"].strip() == pid for f in self.l.filas("Menú")):
                out[pid] = (PAGINAS_GENERADAS[pid], generador())
        orden = ["inicio"] + (["requisitos"] if "requisitos" in out else []) + [k for k in out if k not in ("inicio", "requisitos")]
        return {k: out[k] for k in orden}

    def paginas(self) -> dict[str, tuple[str, str]]:
        """{id: (título, markdown)}; `inicio` se publica como index.md."""
        return {("index" if k == "inicio" else k): v for k, v in self._paginas_ids().items()}

    def _arbol_paginas(self, paginas: dict[str, tuple[str, str]]) -> dict:
        """Páginas para sushi-config, con las páginas hijas dentro de su página padre."""
        pads = {f["pagina"]: f.get("padre", "").strip() for f in self.l.filas("Documentación")}
        ids = {("index" if k == "inicio" else k): k for k in paginas}
        hijos: dict[str, list[str]] = {}
        raiz = []
        for pid in paginas:
            padre = pads.get(pid, "")
            if padre and padre in paginas and padre != pid:
                hijos.setdefault(padre, []).append(pid)
            else:
                raiz.append(pid)

        def nodo(pid: str) -> dict:
            d = {"title": paginas[pid][0]}
            for h in hijos.get(pid, []):
                d[self._archivo(h)] = nodo(h)
            return d
        return {self._archivo(pid): nodo(pid) for pid in raiz}

    @staticmethod
    def _archivo(pid: str) -> str:
        return "index.md" if pid == "inicio" else f"{pid}.md"

    def _menu(self) -> dict:
        filas = self.l.filas("Menú")
        paginas = set(self._paginas_ids())
        if not filas:
            m = {"Inicio": "index.html"}
            if "requisitos" in paginas:
                m["Requisitos"] = "requisitos.html"
            m["Artefactos"] = "artifacts.html"
            return m
        caps = {f["nombre"]: (f["id"] or f["nombre"]) for f in self.l.filas("Capacidades")}
        menu: dict = {}
        for f in filas:
            if f["padre"].strip():
                continue
            if f["destino"].strip():
                menu[f["etiqueta"]] = href_menu(f["destino"], paginas, caps) or "artifacts.html"
            else:
                menu[f["etiqueta"]] = {h["etiqueta"]: href_menu(h["destino"], paginas, caps) or "artifacts.html"
                                       for h in filas if h["padre"].strip() == f["etiqueta"] and h["destino"].strip()}
        return menu

    def must_support(self) -> str:
        """Página generada con todo lo que los perfiles marcan como Must Support."""
        s = ["Esta página lista, perfil por perfil, los elementos que esta guía marca como **Must Support** (S). Se genera a partir de las marcas de los perfiles, así que no puede quedar desactualizada.", "",
             "- Un sistema que **produce** estos datos debe poder incluirlos cuando los tiene.",
             "- Un sistema que **recibe** estos datos debe poder guardarlos, mostrarlos o usarlos, y no debe fallar por recibirlos.",
             "- Marcar un elemento como Must Support **no lo vuelve obligatorio**: eso lo dice su cardinalidad (`1..1` o `1..*`).", "",
             "*Esta es la definición general de FHIR. Si la comunidad que publica la guía adopta una definición propia, escribe tu propia página con id `must-support` en la hoja Documentación y reemplazará a esta.*", ""]

        def celda(t: str) -> str:
            return (t or "").replace("|", "\\|").replace("\n", " ").strip()
        hay = False
        for f in self.l.filas("Perfiles"):
            n = f["nombre"]
            filas = [(e["ruta"], e["resumen"] or e["definicion"]) for e in self.l.filas("Elementos") if e["perfil"] == n and es_si(e["ms"])]
            filas += [(f"{e['elemento']}:{e['slice']}", e["descripcion"]) for e in self.l.filas("Slices") if e["perfil"] == n and es_si(e["ms"])]
            if not filas:
                continue
            hay = True
            s += [f"#### {f['titulo'] or n} (`{n}`)", "", "| Elemento | Qué es |", "|---|---|"]
            s += [f"| `{r}` | {celda(t)} |" for r, t in filas]
            s += ["", f"[Ver el perfil completo](StructureDefinition-{id_de(f)}.html)", ""]
        ext = [(e["parte_de"], e.get("codigo_parte") or minuscula_inicial(e["nombre"]), e["descripcion"]) for e in self.l.filas("Extensiones") if e["parte_de"] and es_si(e["ms"])]
        ext += [(v["extension"], v["ruta"], "") for v in self.l.filas("ValorExtensiones") if es_si(v["ms"]) and v["ruta"] != "url"]
        if ext:
            hay = True
            s += ["#### Extensiones", "", "| Extensión | Parte o campo | Qué es |", "|---|---|---|"]
            s += [f"| `{e}` | `{p}` | {celda(t)} |" for e, p, t in ext]
            s.append("")
        if not hay:
            s += ["Esta guía no marca ningún elemento como Must Support.", ""]
        return "\n".join(s) + "\n"

    def cambios(self) -> str:
        """Página generada desde la hoja Cambios (en el orden en que está escrita)."""
        def celda(t: str) -> str:
            return (t or "").replace("|", "\\|").replace("\n", "<br/>").strip()
        s = ["| Versión | Fecha | Qué cambió |", "|---|---|---|"]
        s += [f"| {celda(f['version'])} | {celda(f['fecha'])} | {celda(f['cambios'])} |" for f in self.l.filas("Cambios")]
        return "\n".join(s) + "\n"

    def _herencia(self, f: dict) -> str:
        """Frase que dice de dónde parte un perfil y qué se hereda."""
        p, rec = f["padre"], f["recurso"]
        if not p:
            return (f"Parte de `{rec}` de FHIR R4 base: **no hereda nada de CL Core**, así que todo lo que exige este perfil está en la tabla de arriba "
                    "(más los pocos elementos que FHIR marca como modificadores).")
        if p in {x["nombre"] for x in self.l.filas("Perfiles")}:
            return f"Parte de `{p}`, otro perfil de esta guía; además de lo anterior, aplica lo que ese perfil ya exige."
        if (self.cat and p in self.cat.sd) or (not es_no(self.l.guia.get("usa_clcore", "")) and p.startswith("Core")):
            return (f"Parte de `{p}` de **CL Core 1.9.3**. Además de lo anterior, aplican los elementos Must Support que ese perfil ya define: "
                    "se ven en la pestaña *Key Elements* del perfil. Que un elemento sea Must Support no obliga a informarlo en todo caso: "
                    "obliga a que el sistema sepa manejarlo.")
        return f"Parte de `{p}`; además de lo anterior, aplica lo que ese perfil ya exige."

    def requisitos(self) -> str:
        """Primera página tras el inicio: solo lo que esta guía agrega o cambia en cada perfil (la tabla Differential del Publisher)."""
        s = ["Para cada perfil, esta página muestra **solo lo que esta guía agrega o cambia** respecto de su perfil de partida. "
             "Léela primero: la pestaña *Key Elements* de cada perfil también incluye lo que se hereda.", "",
             "**Cómo leer las tablas**", "",
             "- **Card.** (cardinalidad) dice cuántas veces puede aparecer un dato: `1..1` o `1..*` es obligatorio; `0..1` o `0..*` es opcional; `0..0` está prohibido.",
             "- **S** (Must Support) dice que el sistema debe saber guardar, mostrar y usar ese dato.",
             "- Un **binding** dice de qué lista salen los códigos *cuando el dato está presente*; no lo vuelve obligatorio.", ""]
        for f in self.l.filas("Perfiles"):
            pid = id_de(f)
            s += [f"#### {f['titulo'] or f['nombre']} (`{f['nombre']}`)", ""]
            if f["descripcion"]:
                s += [f["descripcion"], ""]
            if f["justificacion"]:
                s += [f"*Por qué:* {f['justificacion']}", ""]
            s += ["{% include StructureDefinition-" + pid + "-diff.xhtml %}", "", self._herencia(f), "",
                  f"[Ver el perfil completo](StructureDefinition-{pid}.html)", ""]
        return "\n".join(s) + "\n"

    def borrador_inicio(self) -> str:
        g = self.l.guia
        s = [f"### {g['titulo']}", "", g.get("descripcion") or "(Falta la descripción de la guía.)", "",
             f"**{AVISO_REVISION}** Los datos de los ejemplos son ficticios.", ""]
        if g.get("contacto") and not g["contacto"].startswith("http"):
            s += [f"Contacto: {g['contacto']}", ""]
        for titulo, hoja in (("Perfiles", "Perfiles"), ("Extensiones", "Extensiones"), ("CodeSystems", "CodeSystems"), ("ValueSets", "ValueSets"), ("Ejemplos", "Instancias")):
            filas = [f for f in self.l.filas(hoja) if not f.get("parte_de") and not f.get("url")]
            if filas:
                s += [f"#### {titulo}", ""]
                s += [f"- **{f['titulo'] or f['nombre']}** (`{f['nombre']}`)" + (f": {f['descripcion']}" if f.get("descripcion") else "") for f in filas]
                s.append("")
        if self.l.filas("Perfiles"):
            s.append("Lo que exige esta guía, perfil por perfil, está en [Requisitos de esta guía](requisitos.html).")
        s.append("Ver todos los artefactos en la página de [artefactos](artifacts.html).")
        return "\n".join(s) + "\n"


_PLANO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:+\-]*$")
_RESERVADAS = {"true", "false", "null", "yes", "no", "on", "off", "y", "n", "~"}


def _escalar(v) -> str:
    """Texto simple sin comillas cuando es seguro (el IG Publisher lee las dependencias como texto y no quita comillas)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v)
    if _PLANO.match(s) and s.lower() not in _RESERVADAS:
        try:
            float(s)
        except ValueError:
            return s
    return json.dumps(s, ensure_ascii=False)


def _yaml(valor, nivel: int = 0) -> str:
    """YAML mínimo para el sushi-config (mapas, texto, números y booleanos); sin depender de PyYAML.

    Los textos van entre comillas dobles de JSON, que también son YAML válido.
    """
    sangria, lineas = "  " * nivel, []
    for clave, v in valor.items():
        if isinstance(v, dict):
            lineas.append(f"{sangria}{json.dumps(clave, ensure_ascii=False) if not clave.replace('.', '').replace('_', '').isalnum() else clave}:")
            lineas.append(_yaml(v, nivel + 1).rstrip("\n"))
        else:
            clave_txt = clave if clave.replace(".", "").replace("_", "").isalnum() else json.dumps(clave, ensure_ascii=False)
            lineas.append(f"{sangria}{clave_txt}: {_escalar(v)}")
    return "\n".join(lineas) + "\n"


def _alias_de_url(url: str) -> str:
    """Nombre corto para un alias: el último tramo de la URL (`.../CSCodigoDNI` -> `CSCodigoDNI`)."""
    tramos = [t for t in url.replace("urn:", "").rstrip("/").replace(":", "/").split("/") if t]
    ultimo = "".join(c for c in tramos[-1] if c.isalnum()) if tramos else ""
    return ultimo or "Sistema"


def construir_archivos(libro: Libro, catalogo: CatalogIndex | None = None) -> dict[str, str]:
    """Todos los archivos de la guía, como {ruta relativa: contenido}. Supone que el libro ya fue revisado sin errores."""
    c = _Constructor(libro, catalogo)
    terminologia = "\n".join(x for x in (c.codesystems(), c.valuesets()) if x)
    perfiles, ejemplos = c.perfiles(), c.instancias()
    extensiones_fsh = c.extensiones()
    capacidades_fsh, busquedas_fsh, mapas_fsh, operaciones_fsh, cuestionarios_fsh = c.capacidades(), c.parametros_busqueda(), c.mapas(), c.operaciones(), c.cuestionarios()   # antes de los alias: pueden crear alias
    aliases = "".join(f"Alias: {k} = {v}\n" for k, v in sorted(c.alias.items()))
    archivos = {
        "sushi-config.yaml": c.config(),
        "ig.ini": (PLANTILLA / "ig.ini").read_text(encoding="utf-8").replace("{{id}}", libro.guia["id"]),
        "input/ignoreWarnings.txt": (PLANTILLA / "input" / "ignoreWarnings.txt").read_text(encoding="utf-8"),
        "input/fsh/aliases.fsh": aliases or "// (sin alias)\n",
    }
    for nombre, texto in (("terminologia.fsh", terminologia), ("extensiones.fsh", extensiones_fsh), ("perfiles.fsh", perfiles), ("ejemplos.fsh", ejemplos), ("capacidades.fsh", capacidades_fsh),
                         ("busquedas.fsh", busquedas_fsh), ("mapas.fsh", mapas_fsh), ("operaciones.fsh", operaciones_fsh), ("cuestionarios.fsh", cuestionarios_fsh)):
        if texto.strip():
            archivos[f"input/fsh/{nombre}"] = texto
    for pid, (_, md) in c.paginas().items():
        archivos[f"input/pagecontent/{pid}.md"] = md if md.endswith("\n") else md + "\n"
    return archivos


EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}


def construir_binarios(libro: Libro) -> dict[str, bytes]:
    """Imágenes de la carpeta «imagenes» junto al libro, para input/images (las páginas las usan como ![texto](nombre.png))."""
    if libro.base is None:
        return {}
    carpeta = libro.base / "imagenes"
    if not carpeta.is_dir():
        return {}
    return {f"input/images/{f.name}": f.read_bytes() for f in sorted(carpeta.iterdir()) if f.is_file() and f.suffix.lower() in EXT_IMAGEN}
