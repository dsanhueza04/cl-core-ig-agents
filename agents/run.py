"""Repara un IG existente con el bucle completo.

    python -m agents.run --ig examples/demo/gold          # copia el IG a runs/<id>/ig y lo repara allí

Usa el backend de modelo configurado en .env / entorno (por defecto `mock`, sin costo).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import asdict
from pathlib import Path

from agents.catalog import CatalogIndex
from agents.informe import costo_texto as _costo
from agents.informe import informe_md
from agents.loop import run_loop
from agents.perfiles import DEFAULT_MODEL, aliases_fsh
from agents.reparador import RepairAgent
from llm import client_from_env
from validator.run import docker_validate, write_fsh


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ig", required=True, help="carpeta del IG (con sushi-config.yaml e input/fsh/)")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--catalog", default="build/catalog/catalog.json")
    ap.add_argument("--clcore", default="reference/clcore-1.9.3/site/package.tgz")
    ap.add_argument("--max-iterations", type=int, default=5)
    ap.add_argument("--model", default=None)
    ap.add_argument("--sin-reparar", action="store_true", help="valida una sola vez y no repara (libros de Excel: se corrigen en el libro)")
    ap.add_argument("--timeout-min", type=int, default=60, help="minutos máximos de cada validación con Docker (CL Core completo tarda unos 25)")
    ap.add_argument("--sin-reglas", action="store_true", help="no aplica las reglas deterministas (mide solo al modelo)")
    args = ap.parse_args(argv)

    try:
        catalog = CatalogIndex.from_file(args.catalog)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
    run_id = time.strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.runs) / run_id
    ig = run_dir / "ig"
    shutil.copytree(args.ig, ig, ignore=shutil.ignore_patterns("output", "temp", "fsh-generated", "input-cache"))
    client = client_from_env(run_id=run_id, log_path=run_dir / "llm_calls.jsonl", log_text=True)
    model = args.model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
    repairer = RepairAgent(client, catalog, model=model)

    files = {p.name: p.read_text(encoding="utf-8") for p in sorted((ig / "input" / "fsh").glob("*.fsh"))}
    inicio = time.monotonic()
    result = run_loop(files, docker_validate(ig, args.clcore, timeout_s=args.timeout_min * 60), repairer, catalog,
                      max_iterations=args.max_iterations, usar_reglas=not args.sin_reglas, reparar=not args.sin_reparar)
    write_fsh(ig, result.files)
    segundos = round(time.monotonic() - inicio, 1)

    report = {"generacion": {"validacion_y_reparacion": {"segundos": segundos}}, "run_id": run_id, "status": result.status, "steps": [asdict(s) for s in result.steps],
              "reglas_aplicadas": [c for s in result.steps for c in s.reglas],
              "pendientes": [asdict(p) for p in result.problems], "llm": client.summary()}
    (run_dir / "informe.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "informe.md").write_text(informe_md(report), encoding="utf-8")
    print(f"estado: {result.status} · vueltas: {len(result.steps)} · llamadas al modelo: {report['llm']['calls']}"
          f"{_costo(report)} · duración: {segundos / 60:.1f} min\nresultado en {run_dir}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
