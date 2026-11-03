"""Piezas comunes de los agentes que generan FSH: alias, extracción del bloque y bucle con chequeo previo."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents.catalog import CatalogIndex
from llm import LLMClient
from validator.precheck import RefIssue, precheck_fsh

STANDARD_ALIASES = {
    "$LNC": "http://loinc.org",
    "$UCUM": "http://unitsofmeasure.org",
    "$ObsCat": "http://terminology.hl7.org/CodeSystem/observation-category",
    "$CSDNI": "https://hl7chile.cl/fhir/ig/clcore/CodeSystem/CSCodigoDNI",
}

FSH_BLOCK = re.compile(r"```(?:fsh|FSH)?[ \t]*\n(.*?)```", re.DOTALL)
DEFAULT_MODEL = "claude-sonnet-5-5"  # solo se usa con backend de pago; el local usa LLM_MODEL


def aliases_fsh() -> str:
    return "".join(f"Alias: {k} = {v}\n" for k, v in STANDARD_ALIASES.items())


def extract_fsh(text: str) -> str:
    """Saca el bloque FSH de la respuesta; si no hay bloque, usa el texto completo."""
    blocks = FSH_BLOCK.findall(text)
    return "\n".join(b.strip("\n") for b in blocks).strip() + "\n" if blocks else text.strip() + "\n"


def feedback(issues: list[RefIssue]) -> str:
    lines = ["Tu FSH tiene referencias a CL Core que no existen o no coinciden. Corrígelas y responde de nuevo con el bloque ```fsh completo:"]
    for i in issues:
        lines.append(f"- línea {i.line}: {i.message}" + (f" (sugerencia: {i.suggestion})" if i.suggestion else ""))
    return "\n".join(lines)


@dataclass
class ProfileResult:
    fsh: str
    issues: list[RefIssue] = field(default_factory=list)  # referencias aún sin resolver
    attempts: int = 1

    @property
    def clean(self) -> bool:
        return not self.issues


def ask_fsh(client: LLMClient, catalog: CatalogIndex, model: str, agent: str, system: str, user: str,
            max_fixes: int = 2, max_tokens: int = 4000) -> ProfileResult:
    """Pide FSH al modelo y devuelve las referencias inventadas para que las corrija (máx. `max_fixes`)."""
    messages = [{"role": "user", "content": user}]
    fsh, issues = "", []
    for attempt in range(max_fixes + 1):
        reply = client.complete(agent=agent, model=model, system=system, messages=messages,
                                max_tokens=max_tokens, iteration=attempt, cache_system=True)
        fsh = extract_fsh(reply.text)
        issues = precheck_fsh(fsh, catalog, STANDARD_ALIASES)
        if not issues:
            return ProfileResult(fsh, [], attempt + 1)
        messages += [{"role": "assistant", "content": reply.text}, {"role": "user", "content": feedback(issues)}]
    return ProfileResult(fsh, issues, max_fixes + 1)
