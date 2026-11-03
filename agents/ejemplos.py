"""Agente de ejemplos: de la especificación y los perfiles generados a instancias FSH de ejemplo."""
from __future__ import annotations

import re
from pathlib import Path

from agents.base import DEFAULT_MODEL, STANDARD_ALIASES, ProfileResult, ask_fsh
from agents.catalog import CatalogIndex
from llm import LLMClient

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


def parent_ids(profiles_fsh: str, catalog: CatalogIndex) -> list[str]:
    """Perfiles de CL Core de los que heredan los perfiles propios (por nombre o por URL)."""
    out = []
    for m in re.finditer(r"^Parent:\s*(\S+)", profiles_fsh, re.MULTILINE):
        name = m.group(1).rstrip("/").rsplit("/", 1)[-1]
        if name in catalog.sd and name not in out:
            out.append(name)
    return out


def build_system(spec: str, catalog: CatalogIndex, profiles_fsh: str = "", max_chars: int = 8000) -> str:
    template = (PROMPTS / "ejemplos.md").read_text(encoding="utf-8")
    example = (PROMPTS / "ejemplo_instancias.fsh").read_text(encoding="utf-8").strip()
    # Siempre la ficha del paciente (todo ejemplo la necesita) y las de los perfiles padre de los propios.
    must = ["CorePacienteCl", *parent_ids(profiles_fsh, catalog)]
    return template.format(version=catalog.data["version"], aliases=", ".join(STANDARD_ALIASES), ejemplo=example,
                           catalogo=catalog.context(spec, max_chars=max_chars, must=must))


class ExampleAgent:
    def __init__(self, client: LLMClient, catalog: CatalogIndex, model: str = DEFAULT_MODEL, max_fixes: int = 2):
        self.client, self.catalog, self.model, self.max_fixes = client, catalog, model, max_fixes

    def generate(self, spec: str, profiles_fsh: str) -> ProfileResult:
        user = (f"Especificación de entrada:\n\n{spec}\n\nPerfiles propios ya escritos:\n```fsh\n{profiles_fsh.rstrip()}\n```\n\n"
                "Escribe las instancias de ejemplo.")
        return ask_fsh(self.client, self.catalog, self.model, "ejemplos", build_system(spec, self.catalog, profiles_fsh), user,
                       self.max_fixes)
