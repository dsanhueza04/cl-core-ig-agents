#!/usr/bin/env python3
"""Convierte el reporte `output/qa.txt` del IG Publisher en datos estructurados.

Cada mensaje se clasifica así:
  - ``infra``:   falla de red o del servidor de terminología (reintentar, NO llamar al LLM).
  - ``content``: error del propio IG (candidato a reparación).
  - ``advisory``: warning o información (no bloquea).

Uso:
  python -m validator.parse_qa examples/demo/gold/output            # resumen
  python -m validator.parse_qa examples/demo/gold/output --json     # JSON completo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

SEVERITIES = {"ERROR": "error", "WARNING": "warning", "INFORMATION": "information"}

# Mensajes que indican un problema de infraestructura, no del IG.
INFRA_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"SocketTimeoutException",
        r"java\.net\.\w+",
        r"Error from https?://tx\.",
        r"was never issued by this server",
        r"Connection (refused|reset)",
        r"UnknownHostException",
        r"Unable to connect",
        r"terminology server .{0,40}(unavailable|not (reachable|available))",
    )
]

_HEADER_COUNTS = re.compile(r"err\s*=\s*(\d+),\s*warn\s*=\s*(\d+),\s*info\s*=\s*(\d+)")
_VERSION = re.compile(r"IG Publisher Version:\s*(\S+)(?:\s+(.*))?")
_GENERATED = re.compile(r"Generated\s+(.+?)\.\s+FHIR version")
_SECTION = re.compile(r"^==\s*(.+?)\s*==\s*$")
_MESSAGE = re.compile(r"^(ERROR|WARNING|INFORMATION):\s*(.*)$")
_RESOURCE = re.compile(r"^([A-Z][A-Za-z]+)/([\w.\-]+):\s+(.*)$")
_PATH = re.compile(r"^(\S+):\s+(.*)$")
_NUMBERED = re.compile(r"^\d+:\s+")


@dataclass
class Issue:
    severity: str                    # error | warning | information
    kind: str                        # infra | content | advisory
    message: str
    resource_type: str | None = None
    resource_id: str | None = None
    path: str | None = None
    section: str | None = None       # archivo indicado por el publisher
    fingerprint: str = ""

    @property
    def resource(self) -> str | None:
        return f"{self.resource_type}/{self.resource_id}" if self.resource_type else None


@dataclass
class QAReport:
    publisher_version: str | None = None
    publisher_note: str | None = None
    generated: str | None = None
    declared_errors: int | None = None
    declared_warnings: int | None = None
    declared_infos: int | None = None
    issues: list[Issue] = field(default_factory=list)

    # --- vistas ---
    def _of(self, severity: str, kind: str | None = None) -> list[Issue]:
        return [i for i in self.issues if i.severity == severity and (kind is None or i.kind == kind)]

    @property
    def errors(self) -> list[Issue]:
        return self._of("error")

    @property
    def warnings(self) -> list[Issue]:
        return self._of("warning")

    @property
    def informations(self) -> list[Issue]:
        return self._of("information")

    @property
    def content_errors(self) -> list[Issue]:
        return self._of("error", "content")

    @property
    def infra_errors(self) -> list[Issue]:
        return self._of("error", "infra")

    @property
    def ok(self) -> bool:
        """El IG pasó: ningún error, de ningún tipo."""
        return not self.errors

    @property
    def needs_retry(self) -> bool:
        """Hay errores de infraestructura: repetir la validación antes de reparar."""
        return bool(self.infra_errors)

    @property
    def resources_masked(self) -> list[str]:
        """Recursos con error de infraestructura: podrían ocultar errores de contenido."""
        return sorted({i.resource for i in self.infra_errors if i.resource})

    @property
    def consistent(self) -> bool:
        """Los conteos de la cabecera coinciden con los mensajes leídos."""
        declared = (self.declared_errors, self.declared_warnings, self.declared_infos)
        if None in declared:
            return False
        return declared == (len(self.errors), len(self.warnings), len(self.informations))

    def fingerprints(self, kind: str = "content") -> set[str]:
        """Huellas de los errores de un tipo; sirven para detectar si el reparador progresa."""
        return {i.fingerprint for i in self.issues if i.severity == "error" and i.kind == kind}

    def summary(self) -> dict:
        return {
            "publisher_version": self.publisher_version,
            "ok": self.ok,
            "errors": len(self.errors),
            "content_errors": len(self.content_errors),
            "infra_errors": len(self.infra_errors),
            "warnings": len(self.warnings),
            "informations": len(self.informations),
            "needs_retry": self.needs_retry,
            "consistent": self.consistent,
        }

    def to_dict(self) -> dict:
        return {
            **self.summary(),
            "publisher_note": self.publisher_note,
            "generated": self.generated,
            "resources_masked": self.resources_masked,
            "issues": [{**asdict(i), "resource": i.resource} for i in self.issues],
        }


def classify(severity: str, message: str) -> str:
    if severity != "error":
        return "advisory"
    return "infra" if any(p.search(message) for p in INFRA_PATTERNS) else "content"


def _normalize(text: str) -> str:
    """Quita lo que cambia entre corridas sin cambiar el problema (UUID, índices de caché)."""
    text = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", text)
    return re.sub(r"\s+", " ", text).strip()


def _fingerprint(severity: str, resource: str | None, path: str | None, message: str) -> str:
    raw = "|".join([severity, resource or "", path or "", _normalize(message)])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _parse_message(severity: str, body: str, section: str | None) -> Issue:
    resource_type = resource_id = path = None
    message = body
    m = _RESOURCE.match(body)
    if m:
        resource_type, resource_id, rest = m.groups()
        pm = _PATH.match(rest)
        if pm:
            path, message = pm.groups()
        else:
            message = rest
    else:
        message = _NUMBERED.sub("", body)
    kind = classify(severity, message)
    resource = f"{resource_type}/{resource_id}" if resource_type else None
    return Issue(
        severity=severity,
        kind=kind,
        message=message,
        resource_type=resource_type,
        resource_id=resource_id,
        path=path,
        section=section,
        fingerprint=_fingerprint(severity, resource, path, message),
    )


def parse_qa_text(text: str) -> QAReport:
    report = QAReport()
    section: str | None = None
    for line in text.splitlines():
        if (m := _HEADER_COUNTS.search(line)) and report.declared_errors is None:
            report.declared_errors, report.declared_warnings, report.declared_infos = map(int, m.groups())
        elif (m := _VERSION.match(line)):
            report.publisher_version, report.publisher_note = m.group(1), (m.group(2) or None)
        elif (m := _GENERATED.search(line)):
            report.generated = m.group(1)
        elif (m := _SECTION.match(line)):
            section = m.group(1)
        elif (m := _MESSAGE.match(line)):
            report.issues.append(_parse_message(SEVERITIES[m.group(1)], m.group(2), section))
    return report


def load_report(source: str | Path) -> QAReport:
    """Acepta un `qa.txt` o la carpeta `output/` que lo contiene."""
    path = Path(source)
    if path.is_dir():
        path = path / "qa.txt"
    if not path.is_file():
        raise FileNotFoundError(f"No existe {path}")
    return parse_qa_text(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="qa.txt o carpeta output/")
    ap.add_argument("--json", action="store_true", help="imprime el reporte completo en JSON")
    args = ap.parse_args(argv)
    try:
        report = load_report(args.source)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        for key, value in report.summary().items():
            print(f"{key}: {value}")
        for issue in report.content_errors:
            print(f"- [contenido] {issue.resource} {issue.path}: {issue.message[:140]}")
    # 0 = pasó; 1 = hay errores de contenido; 3 = solo errores de infraestructura (reintentar)
    if report.ok:
        return 0
    return 1 if report.content_errors else 3


if __name__ == "__main__":
    raise SystemExit(main())
