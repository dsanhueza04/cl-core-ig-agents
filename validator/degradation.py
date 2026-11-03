"""Detecta reparaciones que "arreglan" un error debilitando el perfil (hacer trampa).

Compara las reglas de cardinalidad (`* camino 1..1`, `contains x 1..1`) antes y después de un
parche. Es degradación: bajar el mínimo, subir el máximo o borrar la regla.
"""
from __future__ import annotations

import re

CARD = re.compile(r"^\s*\*\s+(?P<path>[^\s]+)\s+(?P<min>\d+)\.\.(?P<max>\d+|\*)\b", re.MULTILINE)
CONTAINS = re.compile(r"\band\s+(?P<name>[\w\-]+)\s+(?P<min>\d+)\.\.(?P<max>\d+|\*)\b|\bcontains\s+(?P<name2>[\w\-]+)\s+(?P<min2>\d+)\.\.(?P<max2>\d+|\*)\b")


def _max(value: str) -> float:
    return float("inf") if value == "*" else int(value)


def cardinalities(fsh: str) -> dict[str, tuple[int, str]]:
    rules: dict[str, tuple[int, str]] = {}
    for m in CARD.finditer(fsh):
        rules[m.group("path")] = (int(m.group("min")), m.group("max"))
    for line in fsh.splitlines():
        if "contains" not in line:
            continue
        head = line.split("contains", 1)[0].strip().lstrip("*").strip()
        for m in CONTAINS.finditer(line):
            name = m.group("name") or m.group("name2")
            lo = m.group("min") or m.group("min2")
            hi = m.group("max") or m.group("max2")
            rules[f"{head}[{name}]"] = (int(lo), hi)
    return rules


def degradations(before: str, after: str) -> list[str]:
    """Lista de textos que describen cada debilitamiento; vacía si no hay."""
    old, new = cardinalities(before), cardinalities(after)
    out = []
    for path, (lo, hi) in old.items():
        if path not in new:
            out.append(f"se eliminó la regla de cardinalidad de '{path}' ({lo}..{hi})")
            continue
        nlo, nhi = new[path]
        if nlo < lo:
            out.append(f"'{path}': el mínimo bajó de {lo} a {nlo}")
        if _max(nhi) > _max(hi):
            out.append(f"'{path}': el máximo subió de {hi} a {nhi}")
    return out
