"""Mide qué errores inyectados repara el bucle (SUSHI + IG Publisher + modelo).

    python scripts/medir_reparacion.py                                  # los 12 casos de desarrollo, 1 vez cada uno
    python scripts/medir_reparacion.py --conjunto reservado             # los 8 casos reservados
    python scripts/medir_reparacion.py --caso valor_sin_unidad --n 3
    LLM_BACKEND=local python scripts/medir_reparacion.py --solo-etapa sushi

Necesita Docker (imagen del proyecto). Con LLM_BACKEND=mock mide solo lo que el código arregla sin modelo.
Salida en runs/reparacion-<fecha>/: resultados.csv (se actualiza tras cada corrida), resumen.json y resumen.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.errores import CASOS, aplicar  # noqa: E402
from scripts.medir import wilson  # noqa: E402

CAMPOS = ["caso", "etapa_hipotesis", "corrida", "estado", "convergio", "etapa_observada", "vueltas",
          "reglas", "llamadas", "tokens_in", "tokens_out", "segundos"]


def ejecutar_una(caso, corrida: int, base: Path, args) -> dict:
    from agents import run as agents_run
    ig = aplicar(caso, base / "roto" / f"{caso.nombre}-{corrida}")
    runs = base / "corridas" / f"{caso.nombre}-{corrida}"
    t = time.monotonic()
    argv = ["--ig", str(ig), "--runs", str(runs), "--catalog", args.catalog, "--clcore", args.clcore,
            "--max-iterations", str(args.max_iterations)]
    if args.model:
        argv += ["--model", args.model]
    if args.sin_reglas:
        argv += ["--sin-reglas"]
    agents_run.main(argv)
    segundos = round(time.monotonic() - t, 1)
    informes = sorted(runs.glob("*/informe.json"))
    fila = {"caso": caso.nombre, "etapa_hipotesis": caso.etapa, "corrida": corrida, "segundos": segundos}
    if not informes:
        return {**fila, "estado": "sin_informe", "convergio": False, "etapa_observada": "", "vueltas": 0,
                "reglas": 0, "llamadas": 0, "tokens_in": 0, "tokens_out": 0}
    inf = json.loads(informes[-1].read_text(encoding="utf-8"))
    pasos = inf.get("steps", [])
    llm = inf.get("llm", {})
    return {**fila, "estado": inf["status"], "convergio": inf["status"] == "ok",
            "etapa_observada": pasos[0]["stage"] if pasos else "", "vueltas": len(pasos),
            "reglas": len(inf.get("reglas_aplicadas", [])), "llamadas": llm.get("calls", 0),
            "tokens_in": sum(a.get("input_tokens", 0) for a in llm.get("by_agent", {}).values()),
            "tokens_out": sum(a.get("output_tokens", 0) for a in llm.get("by_agent", {}).values())}


def resumir(filas: list[dict]) -> dict:
    por_caso: dict[str, dict] = {}
    for f in filas:
        c = por_caso.setdefault(f["caso"], {"etapa_hipotesis": f["etapa_hipotesis"], "n": 0, "ok": 0,
                                            "estados": {}, "etapas_observadas": {}, "reglas": 0, "llamadas": 0, "segundos": 0.0})
        c["n"] += 1
        c["ok"] += bool(f["convergio"])
        c["estados"][f["estado"]] = c["estados"].get(f["estado"], 0) + 1
        et = f["etapa_observada"] or "?"
        c["etapas_observadas"][et] = c["etapas_observadas"].get(et, 0) + 1
        c["reglas"] += f.get("reglas", 0)
        c["llamadas"] += f["llamadas"]
        c["segundos"] += f["segundos"]
    for c in por_caso.values():
        lo, hi = wilson(c["ok"], c["n"])
        c["wilson95"] = [round(lo, 2), round(hi, 2)]
    total_ok = sum(c["ok"] for c in por_caso.values())
    total_n = sum(c["n"] for c in por_caso.values())
    lo, hi = wilson(total_ok, total_n)
    return {"casos": por_caso, "total": {"ok": total_ok, "n": total_n, "wilson95": [round(lo, 2), round(hi, 2)]}}


def resumen_md(r: dict, modelo: str) -> str:
    L = [f"# Medición de reparación ({modelo})", "",
         f"Convergieron {r['total']['ok']}/{r['total']['n']} (IC95 Wilson {r['total']['wilson95']}). "
         "n pequeño: es una señal, no una garantía.", "",
         "| Caso | Etapa (hipótesis) | Etapa observada | OK | Estados | Reglas | Llamadas | Segundos |",
         "|---|---|---|---|---|---|---|---|"]
    for nombre, c in r["casos"].items():
        L.append(f"| {nombre} | {c['etapa_hipotesis']} | {c['etapas_observadas']} | {c['ok']}/{c['n']} | "
                 f"{c['estados']} | {c['reglas']} | {c['llamadas']} | {c['segundos']:.0f} |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--caso", action="append", choices=sorted(CASOS), help="repetible; por defecto todos")
    ap.add_argument("--conjunto", choices=["desarrollo", "reservado", "todos"], default="desarrollo",
                    help="desarrollo: los 12 con los que se escribieron las reglas; reservado: 8 nuevos, sin reglas")
    ap.add_argument("--solo-etapa", choices=["precheck", "sushi", "publisher"])
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--max-iterations", type=int, default=5)
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--catalog", default="build/catalog/catalog.json")
    ap.add_argument("--clcore", default="reference/clcore-1.9.3/site/package.tgz")
    ap.add_argument("--model", default=None)
    ap.add_argument("--sin-reglas", action="store_true", help="medir solo al modelo, sin reglas deterministas")
    args = ap.parse_args(argv)

    if args.caso:
        casos = [CASOS[n] for n in args.caso]
    else:
        casos = [c for c in CASOS.values() if args.conjunto == "todos" or c.reservado == (args.conjunto == "reservado")]
    if args.solo_etapa:
        casos = [c for c in casos if c.etapa == args.solo_etapa]
    base = Path(args.runs) / f"reparacion-{time.strftime('%Y%m%d-%H%M%S')}"
    base.mkdir(parents=True, exist_ok=True)
    filas: list[dict] = []
    for caso in casos:
        for i in range(1, args.n + 1):
            fila = ejecutar_una(caso, i, base, args)
            filas.append(fila)
            print(f"{caso.nombre} #{i}: {fila['estado']} · {fila['reglas']} reglas · {fila['llamadas']} llamadas · {fila['segundos']} s", flush=True)
            with (base / "resultados.csv").open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=CAMPOS)
                w.writeheader()
                w.writerows(filas)
    r = resumir(filas)
    (base / "resumen.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "resumen.md").write_text(resumen_md(r, args.model or "backend por defecto"), encoding="utf-8")
    print("\n" + resumen_md(r, args.model or "backend por defecto") + f"\nresultados en {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
