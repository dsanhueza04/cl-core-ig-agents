"""Pipeline completo: especificación → perfiles → ejemplos → validación y reparación → IG en carpeta.

    python -m agents.generate --spec examples/demo/spec.md

Usa el modelo configurado por entorno (LLM_BACKEND, LLM_MODEL). Con `--sin-docker` solo hace el chequeo
previo de referencias (rápido, sin SUSHI ni IG Publisher).
Todo lo generado es un BORRADOR: un humano debe revisarlo antes de usarlo.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from agents.analista import AnalystAgent
from agents.base import DEFAULT_MODEL, aliases_fsh
from agents.catalog import CatalogIndex
from agents.ejemplos import ExampleAgent
from agents.loop import LoopResult, Outcome, run_loop
from agents.perfiles import ProfileAgent
from agents.reparador import RepairAgent
from llm import BudgetExceeded, LLMClient, LLMUnavailable, client_from_env
from validator.parse_qa import QAReport
from generator.render import render_files
from agents.informe import costo_texto as _costo
from agents.informe import informe_md
from generator.spec import advertencias_spec, validate_spec
from validator.run import docker_validate, write_fsh

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "ig-base"


def _ascii(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def derive_meta(spec: str, id: str | None = None, title: str | None = None, canonical: str | None = None) -> dict:
    """Título, nombre, id y canonical del IG, a partir del primer encabezado de la especificación."""
    if not title:
        head = next((ln.lstrip("# ").strip() for ln in spec.splitlines() if ln.startswith("#")), "IG generado")
        title = head.rsplit(":", 1)[-1].strip() or head
        title = title[:1].upper() + title[1:]
    words = re.findall(r"[A-Za-z0-9]+", _ascii(title))
    slug = "-".join(w.lower() for w in words) or "ig"
    return {"title": title.replace('"', "'"),
            "name": "".join(w[:1].upper() + w[1:] for w in words) or "IgGenerado",
            "id": id or "ig.cl." + slug.replace("-", ""),
            "canonical": canonical or f"https://example.org/fhir/ig/{slug}"}


def render_skeleton(dest: Path, meta: dict) -> None:
    """Copia la plantilla neutra del IG reemplazando {{id}}, {{name}}, {{title}} y {{canonical}}."""
    for src in TEMPLATE.rglob("*"):
        if src.is_file():
            out = dest / src.relative_to(TEMPLATE)
            out.parent.mkdir(parents=True, exist_ok=True)
            text = src.read_text(encoding="utf-8")
            for key, value in meta.items():
                text = text.replace("{{" + key + "}}", value)
            out.write_text(text, encoding="utf-8")


@dataclass
class GenerateResult:
    status: str                       # ok | max_iteraciones | sin_progreso | infraestructura | presupuesto | referencias
    files: dict[str, str]
    loop: LoopResult | None
    generation: dict = field(default_factory=dict)
    ig_dir: Path | None = None


def generate_ig_libre(spec: str, out_dir: Path, client: LLMClient, catalog: CatalogIndex, validate: Callable,
                meta: dict | None = None, model: str = DEFAULT_MODEL, skip_examples: bool = False,
                max_iterations: int = 5) -> GenerateResult:
    out_dir = Path(out_dir)
    ig = out_dir / "ig"
    meta = meta or derive_meta(spec)
    gen: dict = {"meta": meta}

    files: dict[str, str] = {}
    try:
        t = time.monotonic()
        profiles = ProfileAgent(client, catalog, model=model).generate(spec)
        gen["perfiles"] = {"intentos": profiles.attempts, "sin_resolver": len(profiles.issues),
                           "segundos": round(time.monotonic() - t, 1)}
        files = {"aliases.fsh": aliases_fsh(), "perfiles.fsh": profiles.fsh}

        if not skip_examples:
            t = time.monotonic()
            examples = ExampleAgent(client, catalog, model=model).generate(spec, profiles.fsh)
            gen["ejemplos"] = {"intentos": examples.attempts, "sin_resolver": len(examples.issues),
                               "segundos": round(time.monotonic() - t, 1)}
            files["ejemplos.fsh"] = examples.fsh
    except (LLMUnavailable, BudgetExceeded) as exc:   # se conserva lo generado hasta ahí
        render_skeleton(ig, meta)
        write_fsh(ig, files)
        gen["error"] = str(exc)
        return GenerateResult("modelo_no_responde" if isinstance(exc, LLMUnavailable) else "presupuesto",
                              files, None, gen, ig)

    render_skeleton(ig, meta)
    write_fsh(ig, files)
    t = time.monotonic()
    result = run_loop(files, validate, RepairAgent(client, catalog, model=model), catalog,
                      max_iterations=max_iterations, usar_reglas=True)
    gen["validacion_y_reparacion"] = {"segundos": round(time.monotonic() - t, 1)}
    write_fsh(ig, result.files)
    return GenerateResult(result.status, result.files, result, gen, ig)


def generate_ig(spec_text: str | None, out_dir: Path, client: LLMClient, catalog: CatalogIndex, validate: Callable,
                overrides: dict | None = None, model: str = DEFAULT_MODEL, ficha: dict | None = None,
                max_iterations: int = 5) -> GenerateResult:
    """Modo estructurado: analista (modelo) → ficha validada → FSH escrito por código → validación y reparación.

    Con `ficha` ya hecha (por ejemplo a mano) se omite el analista y el pipeline no necesita modelo salvo
    para reparar.
    """
    out_dir = Path(out_dir)
    ig = out_dir / "ig"
    gen: dict = {"modo": "estructurado"}
    if ficha is None:
        try:
            t = time.monotonic()
            analysis = AnalystAgent(client, catalog, model=model).generate(spec_text or "")
        except (LLMUnavailable, BudgetExceeded) as exc:
            gen["error"] = str(exc)
            return GenerateResult("modelo_no_responde" if isinstance(exc, LLMUnavailable) else "presupuesto",
                                  {}, None, gen, ig)
        gen["analista"] = {"intentos": analysis.attempts, "problemas": analysis.errors,
                           "autocompletado_por_codigo": analysis.completed,
                           "segundos": round(time.monotonic() - t, 1)}
        out_dir.mkdir(parents=True, exist_ok=True)
        if analysis.spec is not None:
            (out_dir / "spec.json").write_text(json.dumps(analysis.spec, ensure_ascii=False, indent=2), encoding="utf-8")
        if not analysis.valid:
            return GenerateResult("ficha_invalida", {}, None, gen, ig)
        ficha = analysis.spec
    else:
        problems = validate_spec(ficha, catalog, spec_text)
        gen["ficha_entregada"] = {"problemas": problems}
        if problems:
            return GenerateResult("ficha_invalida", {}, None, gen, ig)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "spec.json").write_text(json.dumps(ficha, ensure_ascii=False, indent=2), encoding="utf-8")

    gen["advertencias"] = advertencias_spec(ficha, catalog)

    meta = derive_meta(f"# {ficha['observaciones'][0]['titulo']}", **(overrides or {}))
    gen["meta"] = meta
    files = render_files(ficha)
    render_skeleton(ig, meta)
    write_fsh(ig, files)
    t = time.monotonic()
    result = run_loop(files, validate, RepairAgent(client, catalog, model=model), catalog,
                      max_iterations=max_iterations, usar_reglas=True)
    gen["validacion_y_reparacion"] = {"segundos": round(time.monotonic() - t, 1)}
    write_fsh(ig, result.files)
    return GenerateResult(result.status, result.files, result, gen, ig)


def _report(res: GenerateResult, client: LLMClient, run_id: str) -> dict:
    return {"run_id": run_id, "status": res.status, "generacion": res.generation,
            "pasos": [asdict(s) for s in (res.loop.steps if res.loop else [])],
            "pendientes": [asdict(p) for p in (res.loop.problems if res.loop else [])],
            "llm": client.summary(), "borrador": "requiere revisión humana"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", help="especificación en texto/markdown (entrada del analista)")
    ap.add_argument("--spec-json", help="ficha ya hecha (omite al analista; el pipeline no necesita modelo salvo para reparar)")
    ap.add_argument("--modo", choices=["estructurado", "libre"], default="estructurado",
                    help="estructurado: el modelo rellena una ficha y el código escribe el FSH (recomendado). "
                         "libre: el modelo escribe el FSH (experimental, poco fiable con modelos pequeños)")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--catalog", default="build/catalog/catalog.json")
    ap.add_argument("--clcore", default="reference/clcore-1.9.3/site/package.tgz")
    ap.add_argument("--id")
    ap.add_argument("--title")
    ap.add_argument("--canonical")
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-iterations", type=int, default=5)
    ap.add_argument("--skip-examples", action="store_true", help="solo modo libre")
    ap.add_argument("--sin-docker", action="store_true", help="solo chequeo previo; no corre SUSHI ni el IG Publisher")
    args = ap.parse_args(argv)
    if not args.spec and not args.spec_json:
        ap.error("indica --spec o --spec-json")

    try:
        catalog = CatalogIndex.from_file(args.catalog)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
    spec_text = Path(args.spec).read_text(encoding="utf-8") if args.spec else None
    ficha = json.loads(Path(args.spec_json).read_text(encoding="utf-8")) if args.spec_json else None
    run_id = time.strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.runs) / run_id
    client = client_from_env(run_id=run_id, log_path=run_dir / "llm_calls.jsonl", log_text=True)
    model = args.model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
    if client.backend.name == "mock" and ficha is None:
        print("AVISO: modo simulado (LLM_BACKEND=mock): no se genera nada real. Usa LLM_BACKEND=local.", file=sys.stderr)

    ig_dir = run_dir / "ig"
    validate = (lambda files: Outcome(report=QAReport())) if args.sin_docker else docker_validate(ig_dir, args.clcore)
    overrides = {k: v for k, v in (("id", args.id), ("title", args.title), ("canonical", args.canonical)) if v}
    if args.modo == "libre" and ficha is None:
        res = generate_ig_libre(spec_text, run_dir, client, catalog, validate, derive_meta(spec_text, **overrides),
                                model, args.skip_examples, args.max_iterations)
    else:
        res = generate_ig(spec_text, run_dir, client, catalog, validate, overrides, model, ficha, args.max_iterations)
    res.generation["sin_docker"] = bool(args.sin_docker)
    report = _report(res, client, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "informe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "informe.md").write_text(informe_md(report), encoding="utf-8")
    g = res.generation
    if g.get("analista", {}).get("problemas") or g.get("ficha_entregada", {}).get("problemas"):
        for e in g.get("analista", g.get("ficha_entregada", {})).get("problemas", []):
            print(f"ficha: {e}", file=sys.stderr)
    print(f"estado: {res.status} · llamadas al modelo: {report['llm']['calls']}{_costo(report)}"
          f"\nmodo: {g.get('modo', 'libre')} · resultado en {run_dir}  (BORRADOR: revísalo antes de usarlo)")
    return 0 if res.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
