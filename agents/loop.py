"""Bucle generar → validar → reparar, con topes y detección de falta de progreso.

Orden de cada vuelta (de lo más barato a lo más caro):
  1. chequeo previo de referencias a CL Core (sin modelo, segundos),
  2. validación real (SUSHI + IG Publisher, ≈6 min); los errores de infraestructura se reintentan
     sin llamar al modelo,
  3. si quedan errores de contenido, el reparador propone parches.

Termina con estado: ok | con_problemas | max_iteraciones | sin_progreso | infraestructura | presupuesto | modelo_no_responde.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable

from agents.catalog import CatalogIndex
from agents.reglas import aplicar_reglas
from agents.reparador import Problem, RepairAgent
from llm import BudgetExceeded, LLMUnavailable
from validator.parse_qa import Issue, QAReport
from validator.precheck import collect_aliases, collect_local_names, precheck_fsh


@dataclass
class Outcome:
    """Resultado de una validación real."""
    report: QAReport | None = None            # None si SUSHI falló antes del publisher
    sushi_issues: list[Issue] = field(default_factory=list)


Validate = Callable[[dict[str, str]], Outcome]


@dataclass
class Step:
    iteration: int
    stage: str                   # precheck | sushi | publisher | infra | ok
    problems: int
    applied: int = 0
    failures: list[str] = field(default_factory=list)
    reglas: list[dict] = field(default_factory=list)   # cambios hechos por reglas deterministas (sin modelo)


@dataclass
class LoopResult:
    status: str
    files: dict[str, str]
    steps: list[Step]
    problems: list[Problem] = field(default_factory=list)   # pendientes al terminar

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _from_issue(issue: Issue, source: str) -> Problem:
    line = None
    if issue.path and ":" in issue.path:
        tail = issue.path.rsplit(":", 1)[1]
        line = int(tail) if tail.isdigit() else None
    file = issue.section if source == "sushi" else None
    return Problem(source, issue.message, file=file, line=line, fingerprint=issue.fingerprint)


def _precheck(files: dict[str, str], catalog: CatalogIndex, aliases: dict[str, str]) -> list[Problem]:
    # Los alias pueden estar en otro archivo (aliases.fsh): se juntan todos antes de revisar.
    shared = {**aliases, **collect_aliases(files.values())}
    locales = collect_local_names(t for n, t in files.items() if n.endswith(".fsh"))
    out = []
    for name, text in files.items():
        if name.endswith(".fsh"):
            for i in precheck_fsh(text, catalog, shared, locales):
                out.append(Problem("precheck", i.message, file=name, line=i.line, suggestion=i.suggestion,
                                   fingerprint=f"pre:{name}:{i.kind}:{i.line}"))
    return out


def run_loop(files: dict[str, str], validate: Validate, repairer: RepairAgent, catalog: CatalogIndex,
             aliases: dict[str, str] | None = None, max_iterations: int = 5, max_infra_retries: int = 2,
             max_stalls: int = 2, usar_reglas: bool = False, reparar: bool = True) -> LoopResult:
    files, steps = dict(files), []
    infra_retries = stalls = 0
    previous: set[str] | None = None
    notes: list[str] = []
    problems: list[Problem] = []

    for it in range(max_iterations):
        stage = "precheck"
        problems = _precheck(files, catalog, aliases or {})
        if not problems:
            outcome = validate(files)
            if outcome.report is None and not outcome.sushi_issues:
                return LoopResult("infraestructura", files, steps + [Step(it, "infra", 0)], [])
            if outcome.sushi_issues:
                stage, problems = "sushi", [_from_issue(i, "sushi") for i in outcome.sushi_issues]
            else:
                report = outcome.report
                if report.needs_retry and not report.content_errors:
                    infra_retries += 1
                    steps.append(Step(it, "infra", len(report.infra_errors)))
                    if infra_retries > max_infra_retries:
                        return LoopResult("infraestructura", files, steps, [])
                    continue   # reintento sin modelo; no consume reparación
                if report.ok:
                    return LoopResult("ok", files, steps + [Step(it, "ok", 0)], [])
                if not report.content_errors:   # reporte inconsistente: no hay nada que reparar
                    return LoopResult("infraestructura", files, steps + [Step(it, "infra", 0)], [])
                stage, problems = "publisher", [_from_issue(i, "publisher") for i in report.content_errors]

        if not reparar:        # un libro se corrige en el Excel: no se llama al modelo ni se repite una validación de decenas de minutos
            return LoopResult("con_problemas", files, steps + [Step(it, stage, len(problems))], problems)

        if usar_reglas:
            nuevos, cambios = aplicar_reglas(files, problems)
            if cambios:
                files = nuevos
                steps.append(Step(it, stage, len(problems), len(cambios), [], [asdict(c) for c in cambios]))
                continue   # se vuelve a validar sin gastar una llamada al modelo

        current = {p.fingerprint for p in problems}
        stalls = stalls + 1 if previous is not None and current >= previous else 0
        if stalls >= max_stalls:
            return LoopResult("sin_progreso", files, steps + [Step(it, stage, len(problems))], problems)
        previous = current

        try:
            result = repairer.repair(files, problems, iteration=it, notes=notes)
        except BudgetExceeded:
            return LoopResult("presupuesto", files, steps + [Step(it, stage, len(problems))], problems)
        except LLMUnavailable:
            return LoopResult("modelo_no_responde", files, steps + [Step(it, stage, len(problems))], problems)
        files, notes = result.files, result.failures
        steps.append(Step(it, stage, len(problems), result.applied, result.failures))

    return LoopResult("max_iteraciones", files, steps, problems)
