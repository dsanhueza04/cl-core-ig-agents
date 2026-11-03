#!/usr/bin/env python3
"""Extrae de `hl7.fhir.r4.core` la lista de elementos de cada recurso base de FHIR R4.

Genera `libro/datos/elementos_r4.json`: {recursos: {Recurso: [[ruta, min, max, [tipos]], ...]}, tipos: {Tipo: [...]}} con rutas sin el nombre del recurso
(`name.family`, `value[x]`). Alimenta las listas desplegables de la plantilla de Excel y la validación de rutas del verificador.
Solo se guardan rutas y cardinalidades; el contenido de FHIR R4 es de uso libre (CC0).

Uso:
  python scripts/extract_elementos.py --package ~/.fhir/packages/hl7.fhir.r4.core#4.0.1 [--out libro/datos/elementos_r4.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OMITIR = {"id", "extension", "modifierExtension"}     # no se restringen desde la plantilla


def elementos_de(sd: dict) -> list[list]:
    prefijo = sd["type"] + "."
    out = []
    for e in sd.get("snapshot", {}).get("element", []):
        path = e["path"]
        if not path.startswith(prefijo):
            continue                                        # raíz del recurso
        ruta = path[len(prefijo):]
        if ruta.rsplit(".", 1)[-1] in OMITIR:
            continue
        tipos = sorted({t["code"] for t in e.get("type", []) if t.get("code")})
        out.append([ruta, e.get("min", 0), e.get("max", "1"), tipos])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", required=True, help="carpeta del paquete hl7.fhir.r4.core#4.0.1 (con subcarpeta package/)")
    ap.add_argument("--out", default="libro/datos/elementos_r4.json")
    args = ap.parse_args(argv)
    raiz = Path(args.package)
    if (raiz / "package").is_dir():
        raiz = raiz / "package"
    archivos = sorted(raiz.glob("StructureDefinition-*.json"))
    if not archivos:
        print(f"No encontré StructureDefinition en {raiz}", file=sys.stderr)
        return 2
    datos: dict[str, list] = {}
    tipos: dict[str, list] = {}
    for p in archivos:
        sd = json.loads(p.read_text(encoding="utf-8"))
        if sd.get("derivation") != "specialization" or sd.get("abstract") or sd.get("type") != sd.get("id"):
            continue
        if sd.get("kind") == "resource":
            datos[sd["type"]] = elementos_de(sd)
        elif sd.get("kind") == "complex-type":
            tipos[sd["type"]] = elementos_de(sd)          # HumanName, Quantity, Coding...: sus hijos no vienen en el recurso
    salida = {"fuente": "hl7.fhir.r4.core#4.0.1", "recursos": dict(sorted(datos.items())), "tipos": dict(sorted(tipos.items()))}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    total = sum(len(v) for v in datos.values())
    print(f"{len(datos)} recursos, {total} elementos, {len(tipos)} tipos complejos -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
