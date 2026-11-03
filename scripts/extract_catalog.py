#!/usr/bin/env python3
"""Extrae de un paquete FHIR (por ejemplo CL Core) un catálogo para los agentes.

Genera dos archivos en --out:
  catalog.md    resumen compacto de perfiles, extensiones, ValueSets y CodeSystems
                (se usa como contexto de los agentes; caché de prompt).
  catalog.json  índice completo, con todos los códigos de cada CodeSystem
                (se usa para comprobar de forma determinista que un código existe).

Uso:
  python scripts/extract_catalog.py --package reference/clcore-1.9.3/site/package.tgz --out build/catalog
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
import tempfile
from pathlib import Path


def open_package(src: Path) -> Path:
    """Devuelve la carpeta `package/` a partir de un .tgz o de una carpeta."""
    if src.is_file():
        tmp = Path(tempfile.mkdtemp(prefix="fhirpkg_"))
        with tarfile.open(src) as tar:
            try:
                tar.extractall(tmp, filter="data")
            except TypeError:                       # Python anterior a 3.11.4: no existe `filter`
                tar.extractall(tmp, members=[m for m in tar.getmembers() if m.isfile() and ".." not in Path(m.name).parts and not Path(m.name).is_absolute()])
        return tmp / "package"
    if (src / "package").is_dir():
        return src / "package"
    return src


def load(pkg: Path, prefix: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(pkg.glob(f"{prefix}-*.json"))]


def type_text(el: dict) -> str:
    out = []
    for t in el.get("type", []):
        code = t.get("code", "")
        refs = t.get("profile", []) + t.get("targetProfile", [])
        short = [r.rsplit("/", 1)[-1] for r in refs]
        out.append(f"{code}({', '.join(short)})" if short else code)
    return " | ".join(out)


def fixed_text(el: dict) -> str:
    for k, v in el.items():
        if k.startswith(("fixed", "pattern")):
            return f"{k}={json.dumps(v, ensure_ascii=False)}"
    return ""


def rutas_snapshot(sd: dict) -> list[list]:
    """Rutas del perfil completo (heredadas incluidas) en la notación de FSH: `name[NombreOficial].family`.

    Alimenta las listas desplegables del libro de Excel. Se omiten id/extension/modifierExtension y todo lo que cuelga de
    una extensión, salvo la propia extensión con nombre (`extension[SexoBiologico]`).
    """
    prefijo = (sd.get("type") or "") + "."
    out = []
    for el in sd.get("snapshot", {}).get("element", []):
        eid = el.get("id", el.get("path", ""))
        if not eid.startswith(prefijo):
            continue
        resto = eid[len(prefijo):]
        if re.search(r"(^|\.)extension(:[^.]+)?\.", resto) or resto.rsplit(".", 1)[-1] in ("id", "extension", "modifierExtension"):
            continue
        ruta = re.sub(r":([^.]+)", r"[\1]", resto)
        tipos = sorted({t["code"] for t in el.get("type", []) if t.get("code")})
        out.append([ruta, el.get("min", 0), el.get("max", "1"), tipos])
    return out


def sd_entry(sd: dict) -> dict:
    elements = []
    for el in sd.get("differential", {}).get("element", []):
        b = el.get("binding") or {}
        elements.append(
            {
                "id": el.get("id", el.get("path")),
                "min": el.get("min"),
                "max": el.get("max"),
                "type": type_text(el),
                "mustSupport": bool(el.get("mustSupport")),
                "binding": b.get("valueSet"),
                "strength": b.get("strength"),
                "fixed": fixed_text(el),
            }
        )
    return {
        "id": sd["id"],
        "url": sd["url"],
        "kind": sd.get("kind"),
        "type": sd.get("type"),
        "base": sd.get("baseDefinition"),
        "title": sd.get("title") or sd.get("name"),
        "description": (sd.get("description") or "").strip(),
        "elements": elements,
        "rutas": rutas_snapshot(sd),
    }


def cs_entry(cs: dict) -> dict:
    return {
        "id": cs["id"],
        "url": cs["url"],
        "count": len(cs.get("concept", [])),
        "concepts": {c["code"]: c.get("display", "") for c in cs.get("concept", [])},
    }


def vs_entry(vs: dict) -> dict:
    systems = [i.get("system") for i in vs.get("compose", {}).get("include", []) if i.get("system")]
    valuesets = [v for i in vs.get("compose", {}).get("include", []) for v in i.get("valueSet", [])]
    codes = {i["system"]: [c["code"] for c in i["concept"]]
             for i in vs.get("compose", {}).get("include", []) if i.get("system") and i.get("concept")}
    entry = {"id": vs["id"], "url": vs["url"], "systems": systems, "valueSets": valuesets}
    if codes:
        entry["codes"] = codes  # solo si el ValueSet enumera sus conceptos
    return entry


def build_catalog(pkg: Path) -> dict:
    meta = json.loads((pkg / "package.json").read_text(encoding="utf-8"))
    return {
        "package": meta["name"],
        "version": meta["version"],
        "canonical": meta.get("canonical"),
        "fhirVersions": meta.get("fhirVersions"),
        "dependencies": meta.get("dependencies", {}),
        "license": meta.get("license"),
        "structureDefinitions": [sd_entry(s) for s in load(pkg, "StructureDefinition")],
        "codeSystems": [cs_entry(c) for c in load(pkg, "CodeSystem")],
        "valueSets": [vs_entry(v) for v in load(pkg, "ValueSet")],
    }


def cell(x) -> str:
    return str(x if x not in (None, "") else "").replace("|", "\\|")


def render_markdown(cat: dict) -> str:
    L: list[str] = []
    L.append(f"# Catálogo {cat['package']} {cat['version']}")
    L.append(f"Canonical: {cat['canonical']} · FHIR {', '.join(cat['fhirVersions'] or [])} · licencia declarada: {cat['license']}")
    L.append("Dependencias: " + ", ".join(f"{k}#{v}" for k, v in cat["dependencies"].items()))
    L.append("\nUsa SOLO los perfiles, extensiones, ValueSets y códigos listados aquí. Si algo no aparece, no existe en esta versión.\n")

    sds = cat["structureDefinitions"]
    resources = [s for s in sds if s["kind"] == "resource"]
    complex_types = [s for s in sds if s["kind"] != "resource"]

    L.append("## Perfiles de recursos")
    for s in resources:
        L.append(f"\n### {s['id']} — {s['type']}")
        L.append(f"URL: {s['url']}  \nBase: {s['base']}")
        if s["description"]:
            L.append(s["description"][:300])
        L.append("\n| elemento | card. | tipo | MS | binding | fijo |\n|---|---|---|---|---|---|")
        for e in s["elements"]:
            bind = f"{(e['binding'] or '').rsplit('/', 1)[-1]} ({e['strength']})" if e["binding"] else ""
            L.append(
                f"| {cell(e['id'])} | {cell(e['min'])}..{cell(e['max'])} | {cell(e['type'])} "
                f"| {'sí' if e['mustSupport'] else ''} | {cell(bind)} | {cell(e['fixed'])} |"
            )

    L.append("\n## Extensiones y tipos complejos")
    for s in complex_types:
        binds = sorted({(e["binding"] or "").rsplit("/", 1)[-1] for e in s["elements"] if e["binding"]})
        L.append(f"- **{s['id']}** ({s['type']}) `{s['url']}`" + (f" — binding: {', '.join(binds)}" if binds else ""))

    L.append("\n## ValueSets")
    for v in cat["valueSets"]:
        src = ", ".join(v["systems"] + v["valueSets"])
        L.append(f"- **{v['id']}** `{v['url']}` ← {src}")

    L.append("\n## CodeSystems")
    for c in cat["codeSystems"]:
        sample = ", ".join(f"{k}={d}" for k, d in list(c["concepts"].items())[:4])
        L.append(f"- **{c['id']}** `{c['url']}` — {c['count']} códigos. Ej.: {sample}")

    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", required=True, type=Path, help="package.tgz o carpeta del paquete")
    ap.add_argument("--out", required=True, type=Path, help="carpeta de salida")
    args = ap.parse_args()

    if not args.package.exists():
        print(f"No existe {args.package}. Ver reference/README.md", file=sys.stderr)
        return 1

    cat = build_catalog(open_package(args.package))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "catalog.json").write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "catalog.md").write_text(render_markdown(cat), encoding="utf-8")
    print(
        f"{cat['package']}#{cat['version']}: {len(cat['structureDefinitions'])} SD, "
        f"{len(cat['valueSets'])} VS, {len(cat['codeSystems'])} CS → {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
