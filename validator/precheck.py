"""Chequeo previo, sin modelo, de referencias a CL Core en código FSH.

Detecta antes de ejecutar SUSHI y el IG Publisher (≈6 min):
  - URLs de perfiles, extensiones, ValueSets o CodeSystems de CL Core que no existen,
  - códigos que no existen en el CodeSystem indicado (con pista de dónde sí existen),
  - displays que no coinciden con el oficial,
  - nombres de perfil con error tipográfico (`CorePacienteCL` en vez de `CorePacienteCl`).

Uso:
  python -m validator.precheck examples/demo/gold/input/fsh
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from agents.catalog import CatalogIndex

try:
    from libro.esquema import RECURSOS_R4, TIPOS_DATO
    BASE_FHIR = set(RECURSOS_R4) | set(TIPOS_DATO)      # recursos y tipos de dato de FHIR R4: son padres válidos aunque no estén en CL Core
except ImportError:                                      # el validador puede usarse sin el paquete `libro`
    BASE_FHIR = set()

CLCORE_URL = re.compile(r"https://hl7chile\.cl/fhir/ig/clcore/(StructureDefinition|CodeSystem|ValueSet)/([\w.\-]+)")
ALIAS = re.compile(r"^Alias:\s*(\$[\w\-]+)\s*=\s*(\S+)", re.MULTILINE)
CODE_REF = re.compile(
    r'(?P<sys>\$[A-Za-z0-9_\-]+|https?://[^\s#"]+)#(?P<code>"[^"]*"|[^\s"\)\],]+)(?:[ \t]+"(?P<disp>[^"]*)")?'
)
LOCAL_DEF = re.compile(r"^(?:Profile|Extension|Instance|Logical|Resource|ValueSet|CodeSystem|Invariant|RuleSet):\s*(\S+)", re.MULTILINE)
PARENT_REF = re.compile(r"^(Parent|InstanceOf):\s*(\S+)", re.MULTILINE)

MAX_LISTED_CODES = 40
_KIND_TO_TABLE = {"StructureDefinition": "sd", "CodeSystem": "cs_by_id", "ValueSet": "vs"}


@dataclass
class RefIssue:
    kind: str          # url | code | display | name
    line: int
    text: str
    message: str
    suggestion: str | None = None


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def collect_aliases(texts) -> dict[str, str]:
    """Alias declarados en cualquiera de los textos (suelen estar en aliases.fsh)."""
    return {name: url for t in texts for name, url in ALIAS.findall(t)}


def collect_local_names(texts) -> set[str]:
    """Nombres definidos en cualquiera de los textos (un perfil puede estar en perfiles.fsh y usarse en ejemplos.fsh)."""
    return {n for t in texts for n in LOCAL_DEF.findall(t)}


def precheck_fsh(fsh: str, catalog: CatalogIndex, aliases: dict[str, str] | None = None,
                 locales: set[str] | None = None) -> list[RefIssue]:
    issues: list[RefIssue] = []
    aliases = {**(aliases or {}), **collect_aliases([fsh])}

    # 1. URLs de CL Core inexistentes
    for m in CLCORE_URL.finditer(fsh):
        table = getattr(catalog, _KIND_TO_TABLE[m.group(1)])
        if m.group(2) not in table:
            close = catalog.search(m.group(2), limit=1) if m.group(1) == "StructureDefinition" else []
            if not close:
                close = difflib.get_close_matches(m.group(2), list(table), n=1, cutoff=0.6)
            issues.append(RefIssue(
                "url", _line_of(fsh, m.start()), m.group(0),
                f"{m.group(1)} '{m.group(2)}' no existe en CL Core {catalog.data['version']}",
                f"¿{close[0]}?" if close else None))

    # 2. Códigos y displays frente a los CodeSystems de CL Core
    for m in CODE_REF.finditer(fsh):
        system = aliases.get(m.group("sys"), m.group("sys"))
        if system not in catalog.cs_by_url:
            continue
        cs = catalog.cs_by_url[system]
        code = m.group("code").strip('"')
        line = _line_of(fsh, m.start())
        if code not in cs["concepts"]:
            elsewhere = catalog.code_systems_with(code)
            parts = []
            if elsewhere:
                parts.append(f"el código existe en: {', '.join(elsewhere)}")
            if len(cs["concepts"]) <= MAX_LISTED_CODES:   # lista corta: se muestran todos los válidos
                valid = ", ".join(f"{c}={d}" for c, d in cs["concepts"].items())
                parts.append(f"códigos válidos en {cs['id']}: {valid}")
            hint = "; ".join(parts) or None
            issues.append(RefIssue("code", line, m.group(0), f"El código '{code}' no existe en {cs['id']}", hint))
        elif m.group("disp") is not None:
            official = cs["concepts"][code]
            if _norm(m.group("disp")) != _norm(official):
                issues.append(RefIssue("display", line, m.group(0),
                                       f"Display '{m.group('disp')}' distinto del oficial en {cs['id']}", f"'{official}'"))

    # 3. Nombres de perfil con error tipográfico
    local = set(LOCAL_DEF.findall(fsh)) | (locales or set())
    known = set(catalog.sd)
    for m in PARENT_REF.finditer(fsh):
        name = m.group(2)
        if name.startswith("http") or name in local or name in known or name in BASE_FHIR:
            continue
        close = difflib.get_close_matches(name, list(known), n=1, cutoff=0.85)
        if close or name.startswith("Core"):
            issues.append(RefIssue("name", _line_of(fsh, m.start()), m.group(0),
                                   f"'{name}' no existe en CL Core ni está definido localmente",
                                   f"¿{close[0]}?" if close else None))
    return issues


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def precheck_path(path: str | Path, catalog: CatalogIndex) -> dict[str, list[RefIssue]]:
    """Revisa un archivo .fsh o todos los .fsh de una carpeta."""
    path = Path(path)
    files = [path] if path.is_file() else sorted(path.rglob("*.fsh"))
    texts = {str(f): f.read_text(encoding="utf-8") for f in files}
    shared = collect_aliases(texts.values())
    locales = collect_local_names(texts.values())
    return {name: precheck_fsh(t, catalog, shared, locales) for name, t in texts.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="archivo .fsh o carpeta con .fsh")
    ap.add_argument("--catalog", default="build/catalog/catalog.json")
    args = ap.parse_args(argv)
    try:
        catalog = CatalogIndex.from_file(args.catalog)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
    total = 0
    for file, issues in precheck_path(args.path, catalog).items():
        for i in issues:
            total += 1
            print(f"{file}:{i.line}: [{i.kind}] {i.message}" + (f" → {i.suggestion}" if i.suggestion else ""))
    print(f"{total} problema(s) de referencias")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
