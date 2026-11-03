"""Lee los errores que SUSHI imprime en consola (cuando falla, el IG Publisher ni siquiera corre).

Formato esperado (puede variar entre versiones de SUSHI):

    error Cannot resolve ... 
      File: /ig/input/fsh/perfiles.fsh
      Line: 12 - 14
"""
from __future__ import annotations

import re

from validator.parse_qa import Issue, _fingerprint

ANSI = re.compile(r"\x1b\[[0-9;]*m")
HEAD = re.compile(r"^(error|warn)\s+(.*)$")
FILE = re.compile(r"^\s+File:\s*(.+?)\s*$")
LINE = re.compile(r"^\s+Line:\s*(\d+)")


def parse_sushi_text(text: str) -> list[Issue]:
    """Devuelve los errores de SUSHI como `Issue` de contenido. Los warnings se ignoran."""
    issues: list[Issue] = []
    cur: dict | None = None

    def flush():
        if cur and cur["severity"] == "error":
            where = f"{cur['file']}:{cur['line']}" if cur["file"] and cur["line"] else cur["file"]
            issues.append(Issue("error", "content", cur["message"].strip(), section=cur["file"],
                                path=where, fingerprint=_fingerprint("error", None, where, cur["message"])))

    for raw in ANSI.sub("", text).splitlines():
        head = HEAD.match(raw)
        if head:
            flush()
            cur = {"severity": "error" if head.group(1) == "error" else "warning",
                   "message": head.group(2), "file": None, "line": None}
        elif cur is not None:
            f, ln = FILE.match(raw), LINE.match(raw)
            if f:
                cur["file"] = f.group(1).replace("\\", "/").rsplit("/", 1)[-1]
            elif ln:
                cur["line"] = int(ln.group(1))
            elif raw.startswith("  ") and raw.strip():
                cur["message"] += " " + raw.strip()
            else:
                flush()
                cur = None
    flush()
    return issues
