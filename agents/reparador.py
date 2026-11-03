"""Agente reparador: corrige errores con parches acotados, sin dejar que "arregle" debilitando el perfil."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agents.catalog import CatalogIndex
from agents.patches import apply_patches, parse_patches
from agents.perfiles import DEFAULT_MODEL, STANDARD_ALIASES
from llm import LLMClient
from validator.degradation import degradations

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"


@dataclass
class Problem:
    source: str                 # precheck | sushi | publisher
    message: str
    file: str | None = None
    line: int | None = None
    suggestion: str | None = None
    fingerprint: str = ""

    def render(self) -> str:
        where = f"{self.file}:{self.line} " if self.file and self.line else (f"{self.file} " if self.file else "")
        return f"- [{self.source}] {where}{self.message}" + (f" (sugerencia: {self.suggestion})" if self.suggestion else "")


@dataclass
class RepairResult:
    files: dict[str, str]
    applied: int = 0
    failures: list[str] = field(default_factory=list)   # parches que no se pudieron aplicar o se rechazaron
    changed: bool = False


class RepairAgent:
    def __init__(self, client: LLMClient, catalog: CatalogIndex, model: str = DEFAULT_MODEL, max_file_chars: int = 12000):
        self.client, self.catalog, self.model, self.max_file_chars = client, catalog, model, max_file_chars

    def _system(self, problems: list[Problem]) -> str:
        template = (PROMPTS / "reparador.md").read_text(encoding="utf-8")
        query = " ".join(p.message for p in problems)
        return template.format(version=self.catalog.data["version"], aliases=", ".join(STANDARD_ALIASES),
                               catalogo=self.catalog.context(query, max_chars=4500, limit=2))

    def _user(self, files: dict[str, str], problems: list[Problem], notes: list[str]) -> str:
        parts = ["Problemas a corregir:", *(p.render() for p in problems), ""]
        if notes:
            parts += ["Tu intento anterior falló por esto; corrígelo:", *(f"- {n}" for n in notes), ""]
        for name, text in files.items():
            if len(text) <= self.max_file_chars:
                parts += [f"Archivo {name}:", "```fsh", text.rstrip("\n"), "```", ""]
        return "\n".join(parts)

    def repair(self, files: dict[str, str], problems: list[Problem], iteration: int = 0,
               notes: list[str] | None = None) -> RepairResult:
        reply = self.client.complete(
            agent="reparador", model=self.model, system=self._system(problems),
            messages=[{"role": "user", "content": self._user(files, problems, notes or [])}],
            max_tokens=3000, iteration=iteration, cache_system=False)
        patches = parse_patches(reply.text)
        if not patches:
            return RepairResult(files, 0, ["la respuesta no contiene bloques de parche con el formato pedido"])
        new_files, failures = apply_patches(files, patches)
        # Antiverificación de trampa: se rechaza TODO el conjunto si debilita alguna cardinalidad.
        cheats = [f"{name}: {d}" for name in new_files if name in files for d in degradations(files[name], new_files[name])]
        if cheats:
            return RepairResult(files, 0, failures + [f"parche rechazado por debilitar el perfil: {c}" for c in cheats])
        applied = len(patches) - len(failures)
        return RepairResult(new_files, applied, failures, changed=new_files != files)
