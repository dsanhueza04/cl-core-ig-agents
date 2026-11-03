"""Parches por bloques BUSCAR/REEMPLAZAR: el modelo cambia solo lo necesario, no reescribe el archivo.

Formato que debe producir el modelo:

    ### archivo: perfiles.fsh
    <<<<<<< BUSCAR
    texto exacto actual
    =======
    texto nuevo
    >>>>>>> REEMPLAZAR
"""
from __future__ import annotations

import re
from dataclasses import dataclass

BLOCK = re.compile(
    r"###\s*archivo:\s*(?P<file>[^\n]+?)\s*\n\s*<{5,}\s*BUSCAR\s*\n(?P<old>.*?)\n={5,}\s*\n(?P<new>.*?)\n?>{5,}\s*REEMPLAZAR",
    re.DOTALL,
)


@dataclass
class Patch:
    file: str
    old: str
    new: str


def parse_patches(text: str) -> list[Patch]:
    return [Patch(m.group("file").strip(), m.group("old"), m.group("new")) for m in BLOCK.finditer(text)]


def apply_patches(files: dict[str, str], patches: list[Patch]) -> tuple[dict[str, str], list[str]]:
    """Aplica los parches sobre una copia. Devuelve (archivos nuevos, fallos en texto)."""
    out, failures = dict(files), []
    for p in patches:
        if p.file not in out:
            failures.append(f"{p.file}: el archivo no existe (existen: {', '.join(sorted(out))})")
            continue
        count = out[p.file].count(p.old)
        if count == 0:
            failures.append(f"{p.file}: el texto a buscar no aparece tal cual: {p.old.strip()[:80]!r}")
        elif count > 1:
            failures.append(f"{p.file}: el texto a buscar aparece {count} veces; agrega líneas vecinas para que sea único")
        else:
            out[p.file] = out[p.file].replace(p.old, p.new, 1)
    return out, failures
