"""Agente analista: de la especificación (texto) a la ficha estructurada (spec.json).

El modelo solo rellena datos; el FSH lo escribe `generator.render`. La ficha se valida con
`generator.spec.validate_spec` y, si tiene problemas, se le devuelven al modelo para que corrija
(máx. `max_fixes` veces).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from agents.base import DEFAULT_MODEL
from agents.catalog import CatalogIndex
from generator.spec import completar_ficha, validate_spec
from llm import LLMClient

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
JSON_BLOCK = re.compile(r"```(?:json|JSON)?[ \t]*\n(.*?)```", re.DOTALL)


def extract_json(text: str) -> object:
    """Primer objeto JSON de la respuesta (en bloque ```json o suelto). Lanza ValueError si no hay."""
    m = JSON_BLOCK.search(text)
    candidate = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    if not candidate.strip():
        raise ValueError("la respuesta no contiene un objeto JSON")
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido: {exc}") from exc


def build_system(catalog: CatalogIndex) -> str:
    template = (PROMPTS / "analista.md").read_text(encoding="utf-8")
    example = (PROMPTS / "ejemplo_spec.json").read_text(encoding="utf-8").strip()
    # replace y no format: el prompt contiene llaves JSON literales
    return template.replace("{version}", catalog.data["version"]).replace("{ejemplo}", example)


@dataclass
class AnalystResult:
    spec: dict | None
    errors: list[str] = field(default_factory=list)   # problemas que siguen sin resolver
    attempts: int = 1
    history: list[list[str]] = field(default_factory=list)   # problemas de cada intento (el último, vacío si valió)
    completed: list[str] = field(default_factory=list)       # campos que completó el código (no el modelo)

    @property
    def valid(self) -> bool:
        return self.spec is not None and not self.errors


def _feedback(errors: list[str]) -> str:
    return ("Tu ficha tiene problemas. Corrígelos y responde de nuevo con el objeto JSON completo:\n"
            + "\n".join(f"- {e}" for e in errors))


class AnalystAgent:
    def __init__(self, client: LLMClient, catalog: CatalogIndex, model: str = DEFAULT_MODEL, max_fixes: int = 2):
        self.client, self.catalog, self.model, self.max_fixes = client, catalog, model, max_fixes

    def generate(self, spec_text: str) -> AnalystResult:
        system = build_system(self.catalog)
        messages = [{"role": "user", "content": f"Especificación:\n\n{spec_text}\n\nRellena la ficha JSON."}]
        spec, errors, history, completed = None, [], [], []
        for attempt in range(self.max_fixes + 1):
            reply = self.client.complete(agent="analista", model=self.model, system=system, messages=messages,
                                         max_tokens=3000, iteration=attempt, cache_system=True, json_mode=True)
            try:
                spec, completed = completar_ficha(extract_json(reply.text))
                errors = validate_spec(spec, self.catalog, spec_text)
            except ValueError as exc:
                spec, errors, completed = None, [str(exc)], []
            history.append(list(errors))
            if not errors:
                return AnalystResult(spec, [], attempt + 1, history, completed)
            messages += [{"role": "assistant", "content": reply.text}, {"role": "user", "content": _feedback(errors)}]
        return AnalystResult(spec if isinstance(spec, dict) else None, errors, self.max_fixes + 1, history, completed)
