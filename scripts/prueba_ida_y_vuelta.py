#!/usr/bin/env python3
"""Prueba de ida y vuelta: paquete FHIR -> libro de Excel -> FSH -> SUSHI -> comparar con el paquete original.

Uso:  python scripts/prueba_ida_y_vuelta.py CARPETA_CON_LOS_JSON [--sushi RUTA_A_SUSHI] [--salida CARPETA] [--con-textos]

1. Importa el paquete a un libro (sin copiar textos explicativos, salvo --con-textos) y lo revisa.
2. Genera el FSH con la herramienta y corre SUSHI (hace falta `sushi` y el paquete hl7.fhir.r4.core en ~/.fhir/packages).
3. Compara, elemento por elemento, el snapshot generado con el original: cardinalidad, Must Support, bindings, tipos, perfiles,
   valores fijos y slicing. Los textos y las URL propias no se comparan. Imprime las diferencias.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from libro.fsh import construir_archivos  # noqa: E402
from libro.importar_paquete import importar_paquete  # noqa: E402
from libro.lector import leer_libro  # noqa: E402
from libro.plantilla import guardar_plantilla  # noqa: E402
from libro.revisar import hay_errores, revisar_libro, texto_avisos  # noqa: E402


def _json_por_tipo(carpeta: Path, tipo: str) -> list[dict]:
    out = []
    for f in sorted(carpeta.glob(f"{tipo}-*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(d, dict) and d.get("resourceType") == tipo:
            out.append(d)
    return out


def _normal(e: dict, nombre_de) -> dict:
    """Propiedades de un elemento que importan para el contrato (sin textos)."""
    p: dict = {}
    for k in ("min", "max"):                      # sliceName ya va en el id del elemento
        if k in e:
            p[k] = e[k]
    if e.get("mustSupport"):
        p["mustSupport"] = True
    if e.get("constraint"):
        p["constraint"] = sorted((c.get("key"), c.get("severity"), c.get("expression")) for c in e["constraint"])
    if e.get("binding", {}).get("valueSet"):
        p["binding"] = (e["binding"].get("strength"), nombre_de(e["binding"]["valueSet"]))
    if e.get("type"):
        p["type"] = sorted((t["code"], tuple(sorted(nombre_de(x) for x in t.get("profile", []))),
                            tuple(sorted(nombre_de(x) for x in t.get("targetProfile", [])))) for t in e["type"])
    for k, v in e.items():
        if k.startswith(("fixed", "pattern")):
            p[k] = v
    if "slicing" in e:
        s = e["slicing"]
        p["slicing"] = (tuple((d.get("type"), d.get("path")) for d in s.get("discriminator", [])), s.get("rules", "open"))
    return p


NUCLEO = Path.home() / ".fhir" / "packages" / "hl7.fhir.r4.core#4.0.1" / "package"
_CACHE_NUCLEO: dict = {}


def _nucleo(tipo: str) -> dict:
    """Elementos del snapshot de un tipo base de FHIR R4 {id: elemento}."""
    if tipo not in _CACHE_NUCLEO:
        f = NUCLEO / f"StructureDefinition-{tipo}.json"
        _CACHE_NUCLEO[tipo] = {e["id"]: e for e in json.loads(f.read_text(encoding="utf-8"))["snapshot"]["element"]} if f.is_file() else {}
    return _CACHE_NUCLEO[tipo]


class Conjunto:
    """StructureDefinition de un lado de la comparación; calcula el valor efectivo de un elemento recorriendo los padres.

    SUSHI no escribe el snapshot (lo hace el Publisher), así que se compara lo que cada perfil dice más lo que hereda.
    """

    def __init__(self, sds: list[dict], nombre_de, externos: dict | None = None) -> None:
        self.por_url = {**(externos or {}), **{d["url"]: d for d in sds}}
        self.nombre_de = nombre_de

    def _efectivo(self, sd: dict, id_: str) -> dict:
        base = sd.get("baseDefinition", "")
        if base in self.por_url:
            heredado = self._efectivo(self.por_url[base], id_)
        else:
            tipo = base.rsplit("/", 1)[-1]
            raiz = id_.split(".", 1)
            nuc = _nucleo(tipo)
            sin_slice = re.sub(r":[\w-]+", "", id_)
            sin_slice = tipo + ("." + sin_slice.split(".", 1)[1] if "." in sin_slice else "")
            heredado = _normal(nuc.get(id_) or nuc.get(sin_slice) or {}, self.nombre_de)
        propio = next((e for e in sd["differential"]["element"] if e["id"] == id_), None)
        return {**heredado, **(_normal(propio, self.nombre_de) if propio else {})}

    def efectivo(self, sd: dict, id_: str) -> dict:
        return self._efectivo(sd, id_)


def canonical_igual(d: dict) -> str:
    return d.get("url", "")


def comparar(originales: list[dict], generados: list[dict], url_a_nombre_orig: dict, nombre_de_gen, externos: dict | None = None) -> list[str]:
    """Lista de diferencias legibles entre los dos conjuntos de StructureDefinition (valores efectivos, sin textos)."""
    difs = []
    nombre_orig = lambda u: url_a_nombre_orig.get(u.split("|")[0], u.split("|")[0].rsplit("/", 1)[-1])  # noqa: E731
    co, cg = Conjunto(originales, nombre_orig, externos), Conjunto(generados, nombre_de_gen, externos)
    gen_por_nombre = {d["name"]: d for d in generados}
    for o in originales:
        g = gen_por_nombre.get(url_a_nombre_orig.get(o["url"]))
        if g is None:
            difs.append(f"{o['name']}: no se generó en SUSHI")
            continue
        if canonical_igual(o) != canonical_igual(g):
            difs.append(f"{o['name']} · url: original={o['url']} generado={g['url']}")
        ids = {e["id"] for e in o["differential"]["element"]} | {e["id"] for e in g["differential"]["element"]}
        if o.get("type") == "Extension" and sorted((c["type"], c["expression"]) for c in o.get("context", [])) != sorted(
                (c["type"], c["expression"]) for c in g.get("context", [])):
            difs.append(f"{o['name']} · contexto: original={[(c['type'], c['expression']) for c in o.get('context', [])]} "
                        f"generado={[(c['type'], c['expression']) for c in g.get('context', [])]}")
        if o.get("baseDefinition") != g.get("baseDefinition") and nombre_orig(o.get("baseDefinition", "")) != nombre_de_gen(g.get("baseDefinition", "")):
            difs.append(f"{o['name']} · baseDefinition: original={o.get('baseDefinition')} generado={g.get('baseDefinition')}")
        for i in sorted(ids):
            if i.endswith(".url") and o.get("type") == "Extension":
                continue                                   # la URL propia de la extensión cambia con la guía
            pa, pb = co.efectivo(o, i), cg.efectivo(g, i)
            for k in sorted(set(pa) | set(pb)):
                if pa.get(k) != pb.get(k):
                    difs.append(f"{o['name']} · {i} · {k}: original={pa.get(k)!r} generado={pb.get(k)!r}")
    return difs


CAMPOS_POR_TIPO = {
    "SearchParameter": ("code", "base", "type", "expression", "multipleOr", "multipleAnd", "modifier", "comparator", "target"),
    "ConceptMap": ("sourceCanonical", "targetCanonical", "group"),
    "OperationDefinition": ("code", "kind", "base", "resource", "system", "type", "instance", "affectsState", "parameter"),
    "CodeSystem": ("caseSensitive", "content", "concept"),
    "ValueSet": ("compose",),
    "Questionnaire": ("subjectType", "derivedFrom", "item"),
    "CapabilityStatement": ("format", "patchFormat", "rest"),
}
TEXTOS_IGNORADOS = {"documentation", "definition", "comment", "description", "short", "designation", "property"}


def _plano(valor, nombre_de, ruta="") -> dict:
    """Aplana un JSON a {ruta: valor}; las URL conocidas se reemplazan por su nombre y se ignoran los textos explicativos."""
    out: dict = {}
    if isinstance(valor, dict):
        for k, v in valor.items():
            if k in TEXTOS_IGNORADOS:
                continue
            out.update(_plano(v, nombre_de, f"{ruta}.{k}" if ruta else k))
    elif isinstance(valor, list):
        escalares = all(not isinstance(x, (dict, list)) for x in valor)
        if escalares:
            out[ruta] = tuple(sorted((str(nombre_de(x)) if isinstance(x, str) and x.startswith("http") else x for x in valor), key=str))
        else:
            for i, x in enumerate(valor):
                out.update(_plano(x, nombre_de, f"{ruta}[{i}]"))
    else:
        out[ruta] = nombre_de(valor) if isinstance(valor, str) and valor.startswith("http") else valor
    return out


def _sin_huecos(cs: dict) -> dict:
    """Quita los valores nulos de searchInclude/searchRevInclude (y su expectativa): son un descuido de algunos paquetes."""
    cs = json.loads(json.dumps(cs))
    for rest in cs.get("rest", []):
        for r in rest.get("resource", []):
            for campo in ("searchInclude", "searchRevInclude"):
                valores = r.get(campo)
                if valores and None in valores:
                    ext = r.get("_" + campo) or [None] * len(valores)
                    pares = [(v, e) for v, e in zip(valores, ext + [None] * len(valores)) if v is not None]
                    r[campo] = [v for v, _ in pares]
                    if "_" + campo in r:
                        r["_" + campo] = [e for _, e in pares]
    return cs


def comparar_otros(originales: dict, generados: dict, url_a_nombre: dict, nombre_de_gen, nombre_de_orig) -> list[str]:
    """SearchParameter, ConceptMap, OperationDefinition, CodeSystem, ValueSet y CapabilityStatement: campos de contrato, sin textos."""
    difs = []
    for tipo, campos in CAMPOS_POR_TIPO.items():
        gen_por_nombre = {d.get("name"): d for d in generados.get(tipo, [])}
        for o in originales.get(tipo, []):
            nombre = url_a_nombre.get(o.get("url"), o.get("name"))
            g = gen_por_nombre.get(nombre)
            if g is None:
                difs.append(f"{tipo} {o.get('name')}: no se generó en SUSHI")
                continue
            if o.get("url") != g.get("url"):
                difs.append(f"{tipo} {o.get('name')} · url: original={o.get('url')} generado={g.get('url')}")
            o = _sin_huecos(o) if tipo == "CapabilityStatement" else o
            po = _plano({k: o[k] for k in campos if k in o}, nombre_de_orig)
            pg = _plano({k: g[k] for k in campos if k in g}, nombre_de_gen)
            for k in sorted(set(po) | set(pg)):
                if k == "caseSensitive" and po.get(k) is None and pg.get(k) is True:
                    continue                                   # el original no lo dice; el libro lo escribe explícito
                if po.get(k) != pg.get(k):
                    difs.append(f"{tipo} {o.get('name')} · {k}: original={po.get(k)!r} generado={pg.get(k)!r}")
    return difs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paquete")
    ap.add_argument("--sushi", default=shutil.which("sushi") or "sushi")
    ap.add_argument("--salida", default="")
    ap.add_argument("--con-textos", action="store_true")
    ap.add_argument("--dependencia", action="append", default=[], help="carpeta con los JSON de un paquete del que dependen los perfiles (se repite)")
    ap.add_argument("--canonical", default="", help="URL base de la guía (si el paquete no trae package.json)")
    ap.add_argument("--max", type=int, default=60, help="máximo de diferencias a imprimir")
    a = ap.parse_args()

    carpeta = Path(a.paquete)
    base = carpeta / "package" if (carpeta / "package").is_dir() else carpeta
    salida = Path(a.salida or (RAIZ / "runs" / "ida-y-vuelta"))
    if salida.exists():
        shutil.rmtree(salida)
    salida.mkdir(parents=True)
    catalogo = None
    try:
        from agents.catalog import CatalogIndex
        catalogo = CatalogIndex.from_file(RAIZ / "build" / "catalog" / "catalog.json")
    except (FileNotFoundError, ImportError):
        pass
    canonical = a.canonical
    try:
        canonical = canonical or json.loads((base / "package.json").read_text(encoding="utf-8")).get("canonical", "")
    except (OSError, json.JSONDecodeError):
        pass
    datos, inf = importar_paquete(base, canonical=canonical, con_textos=a.con_textos, catalogo=catalogo)
    print(inf.texto())
    xlsx = guardar_plantilla(salida / "libro-importado.xlsx", datos)
    libro = leer_libro(xlsx)
    avisos = revisar_libro(libro, catalogo)
    print("\n" + texto_avisos([x for x in avisos if x.nivel != "sugerencia"]))
    if hay_errores(avisos):
        print("El libro importado tiene errores: no sigo con SUSHI.")
        return 2
    ig = salida / "ig"
    for ruta, texto in construir_archivos(libro, catalogo).items():
        destino = ig / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    r = subprocess.run([a.sushi, str(ig)], capture_output=True, text=True, timeout=1500)
    (salida / "sushi.log").write_text(r.stdout + r.stderr, encoding="utf-8")
    resumen = [x for x in (r.stdout + r.stderr).splitlines() if "Errors" in x or x.startswith(("error", "warn"))]
    print("\nSUSHI:", *resumen[:25], sep="\n  ")
    gen = ig / "fsh-generated" / "resources"
    if not gen.is_dir():
        print("SUSHI no generó recursos; ver", salida / "sushi.log")
        return 2
    url_a_nombre = {v["url"]: k for k, v in inf.nombres.items()}
    generados = _json_por_tipo(gen, "StructureDefinition")
    todos_gen = {d["url"]: d["name"] for d in generados + _json_por_tipo(gen, "ValueSet") + _json_por_tipo(gen, "CodeSystem")}
    externos = {}
    carpetas = [Path(x) for x in a.dependencia] + sorted((Path.home() / ".fhir" / "packages").glob("hl7.fhir.cl.clcore#*/package"))
    for c in carpetas:
        for d in _json_por_tipo(c, "StructureDefinition"):
            externos.setdefault(d["url"], d)
    difs = comparar(_json_por_tipo(base, "StructureDefinition"), generados, url_a_nombre,
                    lambda u: todos_gen.get(u.split("|")[0], u.split("|")[0].rsplit("/", 1)[-1]), externos)
    tipos = [t for t in CAMPOS_POR_TIPO]
    orig_otros = {t: _json_por_tipo(base, t) for t in tipos}
    gen_otros = {t: _json_por_tipo(gen, t) for t in tipos}
    nombre_orig = lambda u: url_a_nombre.get(u.split("|")[0], u.split("|")[0].rsplit("/", 1)[-1])  # noqa: E731
    nombre_gen = lambda u: todos_gen.get(u.split("|")[0]) or url_a_nombre.get(u.split("|")[0], u.split("|")[0].rsplit("/", 1)[-1])  # noqa: E731
    todos_gen.update({d["url"]: d["name"] for t in tipos for d in gen_otros[t]})
    difs_otros = comparar_otros(orig_otros, gen_otros, url_a_nombre, nombre_gen, nombre_orig)
    print(f"\nOtros recursos comparados (terminología, capacidades, búsquedas, mapas, operaciones): "
          f"{sum(len(v) for v in orig_otros.values())} · diferencias: {len(difs_otros)}")
    for x in difs_otros[: a.max]:
        print("  -", x)
    print(f"\nStructureDefinition originales: {len(_json_por_tipo(base, 'StructureDefinition'))} · generadas: {len(generados)} · diferencias: {len(difs)}")
    for x in difs[: a.max]:
        print("  -", x)
    if len(difs) > a.max:
        print(f"  ... y {len(difs) - a.max} más (usa --max)")
    return 1 if (difs or difs_otros) else 0


if __name__ == "__main__":
    sys.exit(main())
