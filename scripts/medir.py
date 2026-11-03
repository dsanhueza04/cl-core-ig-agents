"""Mide al analista: repite N veces la generación de la ficha y resume éxito, intentos, tiempo y fallos.

    python scripts/medir.py --spec examples/demo/spec.md --n 5
    python scripts/medir.py --spec a.md --spec b.md --n 3 --max-minutos 90 --validar

Qué mide (por corrida):
  - valida:     la ficha pasó el validador (con hasta 2 correcciones)
  - intentos:   1 = a la primera; 2 o 3 = el modelo corrigió con la retroalimentación del validador
  - segundos y tokens
  - estructura: la parte estructural de la ficha (padre, LOINC, unidades, obligatoriedad) coincide con la
                ficha de referencia (la `spec.json` junto a la especificación, o --gold). Textos y datos del
                ejemplo NO cuentan: pueden variar sin que el perfil cambie.
  - categorías: de qué tipo fueron los errores que el validador atrapó (formato, código inventado, etc.)
Con --validar, cada ficha distinta además se compila (SUSHI + IG Publisher) SIN permitir reparación con
modelo: mide si la ficha produce un IG limpio por sí sola.

Escribe en runs/medicion-<fecha>/: resultados.csv (se actualiza tras cada corrida), fichas/, resumen.json
y resumen.md. Con n pequeño, los intervalos son amplios: el resumen lo dice.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.analista import AnalystAgent  # noqa: E402
from agents.base import DEFAULT_MODEL  # noqa: E402
from agents.catalog import CatalogIndex  # noqa: E402
from llm import BudgetExceeded, LLMClient, LLMUnavailable, MockBackend, client_from_env  # noqa: E402

# (patrón, categoría): el primero que coincide gana
CATEGORIAS = [
    (r"JSON", "json_invalido"),
    (r"no aparece en la especificaci", "codigo_inventado"),
    (r"ejemplo\.valor", "valores_ejemplo"),
    (r"\.padre:", "perfil_padre"),
    (r"ucum", "unidad_ucum"),
    (r"formato LOINC", "formato_loinc"),
    (r"\.(nombre|id):", "formato_identificador"),
    (r"fecha|paciente_ejemplo", "paciente_o_fecha"),
    (r"falta", "campo_faltante"),
]
CSV_COLUMNAS = ["caso", "corrida", "valida", "intentos", "segundos", "tokens_entrada", "tokens_salida",
                "autocompletados", "estructura_igual", "ficha_hash", "errores_por_intento", "estado_ig", "nota"]


def categoria(error: str) -> str:
    for patron, nombre in CATEGORIAS:
        if re.search(patron, error):
            return nombre
    return "otro"


def firma_estructural(ficha: dict) -> list[dict]:
    """Lo que define el perfil, sin textos ni datos del ejemplo. No cuentan los nombres de componente (el LOINC los
    identifica) ni el texto de la unidad ('lpm' o 'latidos/minuto' son lo mismo); sí cuentan padre, código del
    panel, LOINC, código UCUM y obligatoriedad."""
    out = []
    for o in ficha.get("observaciones", []):
        comps = sorted((c.get("loinc"), c.get("ucum"), c.get("obligatorio", True))
                       for c in o.get("componentes", []))
        v = o.get("valor")
        out.append({"padre": o.get("padre"), "codigo_loinc": o.get("codigo_loinc"),
                    "componentes": [list(c) for c in comps],
                    "valor": v.get("ucum") if isinstance(v, dict) else None})
    return sorted(out, key=lambda d: str(d["codigo_loinc"]))


def ficha_hash(ficha: dict) -> str:
    return hashlib.sha256(json.dumps(ficha, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confianza de Wilson para una proporción (ok con n pequeño)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / d
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centro - margen), min(1.0, centro + margen))


def percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    s = sorted(valores)
    k = (len(s) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _tokens(client: LLMClient) -> tuple[int, int]:
    por_agente = client.summary()["by_agent"].values()
    return (sum(a.get("input_tokens", 0) for a in por_agente), sum(a.get("output_tokens", 0) for a in por_agente))


def ejecutar_una(agent: AnalystAgent, client: LLMClient, spec_text: str, ref_firma: list[dict] | None) -> dict:
    """Una corrida del analista. Lanza LLMUnavailable/BudgetExceeded: el llamador decide si sigue."""
    in0, out0 = _tokens(client)
    t = time.monotonic()
    res = agent.generate(spec_text)
    seg = round(time.monotonic() - t, 1)
    in1, out1 = _tokens(client)
    fila = {"valida": res.valid, "intentos": res.attempts, "segundos": seg,
            "tokens_entrada": in1 - in0, "tokens_salida": out1 - out0,
            "autocompletados": len(res.completed),
            "estructura_igual": None, "ficha_hash": "", "errores_por_intento": res.history, "ficha": res.spec}
    if res.valid:
        fila["ficha_hash"] = ficha_hash(res.spec)
        if ref_firma is not None:
            fila["estructura_igual"] = firma_estructural(res.spec) == ref_firma
    return fila


def resumir(filas: list[dict], meta: dict) -> dict:
    n = len(filas)
    validas = [f for f in filas if f["valida"]]
    lo, hi = wilson(len(validas), n)
    con_ref = [f for f in validas if f["estructura_igual"] is not None]
    cats: dict[str, int] = {}
    for f in filas:
        for errores in f["errores_por_intento"]:
            for e in errores:
                cats[categoria(e)] = cats.get(categoria(e), 0) + 1
    segs = [f["segundos"] for f in filas]
    ig = [f["estado_ig"] for f in filas if f.get("estado_ig")]
    return {
        **meta, "corridas": n,
        "validas": len(validas), "tasa_valida": round(len(validas) / n, 3) if n else 0.0,
        "tasa_valida_ic95": [round(lo, 3), round(hi, 3)],
        "a_la_primera": sum(1 for f in filas if f["valida"] and f["intentos"] == 1),
        "a_la_primera_sin_ayuda": sum(1 for f in filas if f["valida"] and f["intentos"] == 1 and not f.get("autocompletados")),
        "intentos_media": round(statistics.mean(f["intentos"] for f in filas), 2) if n else 0.0,
        "intentos_distribucion": {str(k): sum(1 for f in filas if f["intentos"] == k)
                                  for k in sorted({f["intentos"] for f in filas})},
        "segundos_mediana": round(statistics.median(segs), 1) if segs else 0.0,
        "segundos_p95": round(percentil(segs, 0.95), 1),
        "tokens_entrada_media": round(statistics.mean(f["tokens_entrada"] for f in filas)) if n else 0,
        "tokens_salida_media": round(statistics.mean(f["tokens_salida"] for f in filas)) if n else 0,
        "autocompletados_media": round(statistics.mean(f.get("autocompletados", 0) for f in filas), 1) if n else 0.0,
        "estructura_igual": f"{sum(1 for f in con_ref if f['estructura_igual'])}/{len(con_ref)}" if con_ref else "sin referencia",
        "fichas_distintas": len({f["ficha_hash"] for f in validas}),
        "errores_atrapados_por_categoria": dict(sorted(cats.items(), key=lambda kv: -kv[1])),
        "ig_resultados": {e: ig.count(e) for e in sorted(set(ig))},
    }


def resumen_md(r: dict, filas: list[dict]) -> str:
    lo, hi = r["tasa_valida_ic95"]
    lineas = [f"# Medición del analista — {r['fecha']}", "",
              f"- Modelo: `{r['modelo']}` · backend: `{r['backend']}` · correcciones permitidas: {r['max_fixes']}",
              f"- Casos: {', '.join(r['casos'])} · corridas: {r['corridas']}", "",
              "## Resultado", "",
              f"- Fichas válidas: **{r['validas']}/{r['corridas']}** ({r['tasa_valida']:.0%}; intervalo 95 %: {lo:.0%}–{hi:.0%})",
              f"- A la primera: {r['a_la_primera']} (sin que el código completara nada: {r['a_la_primera_sin_ayuda']}) · intentos medios: {r['intentos_media']} · distribución: {r['intentos_distribucion']}",
              f"- Estructura igual a la referencia: {r['estructura_igual']} · fichas distintas: {r['fichas_distintas']}",
              f"- Campos que completó el código y no el modelo (media por corrida): {r['autocompletados_media']}",
              f"- Tiempo: mediana {r['segundos_mediana']} s, p95 {r['segundos_p95']} s · "
              f"tokens medios: {r['tokens_entrada_media']} entrada / {r['tokens_salida_media']} salida"]
    if r["ig_resultados"]:
        lineas.append(f"- IG compilado sin reparación con modelo: {r['ig_resultados']}")
    lineas += ["", "## Qué errores atrapó el validador (todos los intentos)", ""]
    lineas += [f"- {k}: {v}" for k, v in r["errores_atrapados_por_categoria"].items()] or ["- ninguno"]
    lineas += ["", "## Por corrida", "", "| caso | # | válida | intentos | segundos | estructura | IG |", "|---|---|---|---|---|---|---|"]
    for f in filas:
        lineas.append(f"| {f['caso']} | {f['corrida']} | {'sí' if f['valida'] else 'no'} | {f['intentos']} | {f['segundos']} | "
                      f"{f['estructura_igual'] if f['estructura_igual'] is not None else '-'} | {f.get('estado_ig') or '-'} |")
    lineas += ["", "> Con pocas corridas los intervalos son amplios: esto es una señal, no una garantía. "
                   "Toda ficha e IG generados son borradores que requieren revisión humana."]
    return "\n".join(lineas) + "\n"


def validar_ig(ficha: dict, spec_text: str, destino: Path, catalog: CatalogIndex, clcore: str) -> str:
    """Compila la ficha SIN modelo de reparación: ok solo si el IG sale limpio por sí solo."""
    from agents.generate import generate_ig
    from validator.run import docker_validate
    cliente = LLMClient(MockBackend(default="sin reparación"), log_path=destino / "llm_calls.jsonl")
    res = generate_ig(spec_text, destino, cliente, catalog, docker_validate(destino / "ig", clcore), ficha=ficha)
    return res.status


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", action="append", required=True, help="especificación (repetible)")
    ap.add_argument("--gold", help="ficha de referencia (si no, se usa spec.json junto a la especificación)")
    ap.add_argument("--n", type=int, default=5, help="corridas por especificación")
    ap.add_argument("--max-minutos", type=float, default=None, help="no inicia corridas nuevas pasado este tiempo")
    ap.add_argument("--max-fixes", type=int, default=2)
    ap.add_argument("--validar", action="store_true", help="compila cada ficha distinta con Docker (lento)")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--catalog", default="build/catalog/catalog.json")
    ap.add_argument("--clcore", default="reference/clcore-1.9.3/site/package.tgz")
    ap.add_argument("--model", default=None)
    args = ap.parse_args(argv)

    try:
        catalog = CatalogIndex.from_file(args.catalog)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
    fecha = time.strftime("%Y%m%d-%H%M%S")
    out = Path(args.runs) / f"medicion-{fecha}"
    (out / "fichas").mkdir(parents=True, exist_ok=True)
    client = client_from_env(run_id=f"medicion-{fecha}", log_path=out / "llm_calls.jsonl", log_text=True)
    model = args.model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
    if client.backend.name == "mock":
        print("AVISO: LLM_BACKEND=mock: las respuestas son simuladas, la medición no significa nada. "
              "Usa LLM_BACKEND=local.", file=sys.stderr)
    agent = AnalystAgent(client, catalog, model=model, max_fixes=args.max_fixes)

    inicio = time.monotonic()
    filas: list[dict] = []
    vistas: dict[str, str] = {}      # ficha_hash -> estado del IG
    csv_path = out / "resultados.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, CSV_COLUMNAS)
        w.writeheader()
        try:
            for spec_path in args.spec:
                sp = Path(spec_path)
                texto = sp.read_text(encoding="utf-8")
                gold_path = Path(args.gold) if args.gold and len(args.spec) == 1 else sp.with_name("spec.json")
                ref = firma_estructural(json.loads(gold_path.read_text(encoding="utf-8"))) if gold_path.is_file() else None
                for i in range(1, args.n + 1):
                    if args.max_minutos is not None and (time.monotonic() - inicio) / 60 > args.max_minutos:
                        print(f"tiempo máximo alcanzado: no inicio la corrida {i} de {sp.name}")
                        break
                    nota = ""
                    try:
                        fila = ejecutar_una(agent, client, texto, ref)
                    except (LLMUnavailable, BudgetExceeded) as exc:
                        print(f"se detiene la medición: {exc}", file=sys.stderr)
                        raise
                    fila.update(caso=sp.stem if sp.stem != "spec" else sp.parent.name, corrida=i)
                    if fila["ficha"] is not None:
                        (out / "fichas" / f"{fila['caso']}-{i:02d}.json").write_text(
                            json.dumps(fila["ficha"], ensure_ascii=False, indent=2), encoding="utf-8")
                    if args.validar and fila["valida"]:
                        h = fila["ficha_hash"]
                        if h not in vistas:
                            print(f"  compilando ficha {h} (varios minutos)…")
                            vistas[h] = validar_ig(fila["ficha"], texto, out / f"ig-{h}", catalog, args.clcore)
                        fila["estado_ig"] = vistas[h]
                    fila["nota"] = nota
                    filas.append(fila)
                    w.writerow({**{k: fila.get(k, "") for k in CSV_COLUMNAS},
                                "errores_por_intento": json.dumps(fila["errores_por_intento"], ensure_ascii=False)})
                    fh.flush()
                    print(f"[{fila['caso']} {i}/{args.n}] {'válida' if fila['valida'] else 'INVÁLIDA'} · "
                          f"{fila['intentos']} intento(s) · {fila['segundos']} s")
        except (LLMUnavailable, BudgetExceeded):
            pass
        except KeyboardInterrupt:
            print("\ninterrumpido: resumo lo medido hasta ahora")

    if not filas:
        print("no hubo corridas", file=sys.stderr)
        return 1
    meta = {"fecha": fecha, "modelo": model, "backend": client.backend.name, "max_fixes": args.max_fixes,
            "casos": sorted({f["caso"] for f in filas})}
    resumen = resumir(filas, meta)
    (out / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "resumen.md").write_text(resumen_md(resumen, filas), encoding="utf-8")
    print(f"\nválidas {resumen['validas']}/{resumen['corridas']} · a la primera {resumen['a_la_primera']} · "
          f"intentos medios {resumen['intentos_media']} · mediana {resumen['segundos_mediana']} s")
    print(f"resultados en {out}  (resumen.md, resumen.json, resultados.csv, fichas/)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
