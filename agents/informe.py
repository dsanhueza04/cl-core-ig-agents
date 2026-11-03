"""Informe en lenguaje claro (informe.md) a partir del informe técnico (informe.json).

Responde tres preguntas a quien no es desarrollador: ¿qué hizo el sistema?, ¿pasó la validación? y
¿qué tiene que revisar una persona?
"""
from __future__ import annotations

import re

ESTADOS = {
    "ok": ("✅", "La guía pasó SUSHI y el IG Publisher sin errores.",
           "Sigue siendo un borrador: una persona debe revisarla antes de usarla."),
    "ficha_invalida": ("⚠️", "No se generó la guía: la ficha (lo que el sistema entendió de la especificación) tiene problemas.",
                       "Corrige la especificación o la ficha según los problemas listados abajo y vuelve a ejecutar."),
    "con_problemas": ("⚠️", "La guía se construyó, pero el IG Publisher encontró errores.",
                      "Abre ig/output/qa.html para verlos en contexto, corrige el libro de Excel y vuelve a ejecutar. No se llamó a ningún modelo."),
    "sin_progreso": ("⚠️", "La guía no pasó: los errores que quedan se repetían sin mejorar.",
                     "Mira los problemas pendientes; suelen requerir una decisión humana (unidad, código, valor)."),
    "max_iteraciones": ("⚠️", "La guía no pasó: se agotaron las vueltas de reparación.",
                        "Mira los problemas pendientes o aumenta el número máximo de iteraciones."),
    "presupuesto": ("⚠️", "Se detuvo porque se alcanzó el tope de costo configurado.", "Sube MAX_COST_USD_PER_RUN o usa un modelo local."),
    "modelo_no_responde": ("⚠️", "El modelo no respondió, así que no se pudo seguir reparando.",
                           "Revisa que Ollama esté encendido y que LLM_MODEL exista (python cl_ig.py diagnostico)."),
    "infraestructura": ("⚠️", "Falló la herramienta de validación (Docker o red), no necesariamente la guía.",
                        "Mira la salida de Docker en ig/consola.txt, revisa Docker (python cl_ig.py diagnostico) y vuelve a ejecutar."),
}


def _pasos(report: dict) -> list[dict]:
    return report.get("pasos") or report.get("steps") or []


def _descripcion_paso(i: int, s: dict) -> list[str]:
    etapa, n = s.get("stage"), s.get("problems", 0)
    if etapa == "ok":
        return [f"- Vuelta {i}: validación sin errores."]
    if etapa == "infra":
        return [f"- Vuelta {i}: falló la infraestructura de validación; se reintentó sin llamar al modelo."]
    nombre = {"precheck": "chequeo previo (sin Docker)", "sushi": "SUSHI (compilador de FSH)",
              "publisher": "IG Publisher"}.get(etapa, str(etapa))
    out = [f"- Vuelta {i}: {nombre} encontró {n} problema(s)."]
    if s.get("reglas"):
        out.append(f"  - Se corrigieron por regla (sin modelo): {len(s['reglas'])} cambio(s).")
    elif s.get("applied"):
        out.append(f"  - El modelo propuso y se aplicaron {s['applied']} parche(s).")
    for f in s.get("failures") or []:
        out.append(f"  - Parche rechazado: {f}")
    return out


def costo_texto(report: dict) -> str:
    """` · costo: $X` solo cuando hubo gasto real (modelo de pago); con modelo local o simulado no se muestra."""
    costo = (report.get("llm") or {}).get("total_cost_usd", 0) or 0
    return f" · costo: ${costo:.2f}" if costo > 0 else ""


def informe_md(report: dict) -> str:
    g = report.get("generacion") or {}
    pasos = _pasos(report)
    icono, titulo, siguiente = ESTADOS.get(report.get("status"), ("❔", f"Estado: {report.get('status')}", ""))
    sin_docker = bool(g.get("sin_docker"))
    if sin_docker and report.get("status") == "ok":
        icono, titulo = "⚠️", "Solo pasó el chequeo previo: SUSHI y el IG Publisher NO se ejecutaron (modo sin Docker)."
        siguiente = "No está validada. Ejecútalo sin --sin-docker para la validación real."
    L = [f"# Informe de la corrida {report.get('run_id', '')}", "", f"{icono} **{titulo}**", "", siguiente, ""]

    meta = g.get("meta") or {}
    if meta.get("title"):
        L += [f"Guía: **{meta['title']}** (`{meta.get('id', '')}`)", ""]

    L += ["## Qué hizo el sistema", ""]
    modo = g.get("modo")
    if modo == "estructurado":
        an = g.get("analista")
        if an:
            L.append(f"1. **Leyó la especificación** con el modelo y completó una ficha ({an.get('intentos', '?')} intento(s)).")
            if an.get("autocompletado_por_codigo"):
                L.append(f"   - El código corrigió {len(an['autocompletado_por_codigo'])} detalle(s) de forma de la ficha "
                         "(nombres, ids, fechas); nunca códigos clínicos, unidades ni valores.")
        else:
            L.append("1. **Usó una ficha ya hecha** (no se llamó al modelo para leer la especificación).")
        L.append("2. **Escribió el FSH** con un generador determinista a partir de la ficha (perfiles, ejemplos y alias).")
    elif modo:
        L.append("1. **Pidió al modelo que escribiera el FSH** (modo libre, experimental).")
    else:
        L.append("1. **Partió de una guía ya escrita** (por ejemplo, el FSH generado desde un libro de Excel); no se llamó al modelo para escribirla.")
    if sin_docker:
        L.append(f"{3 if modo else 2}. **Solo hizo el chequeo previo** (nombres, alias y códigos contra el catálogo de CL Core). "
                 "No ejecutó SUSHI ni el IG Publisher.")
    else:
        L.append(f"{3 if modo else 2}. **Validó** el resultado con SUSHI y el IG Publisher, que son las herramientas oficiales y no un modelo.")
    if pasos:
        L += ["", "Vueltas de validación y reparación:", ""]
        for i, s in enumerate(pasos, 1):
            L += _descripcion_paso(i, s)

    problemas = (g.get("analista") or {}).get("problemas") or (g.get("ficha_entregada") or {}).get("problemas") or []
    if problemas:
        L += ["", "## Problemas de la ficha", ""] + [f"- {p}" for p in problemas]

    pend = report.get("pendientes") or []
    if pend:
        L += ["", "## Problemas que quedaron sin resolver", ""]
        grupos: dict[str, list[dict]] = {}
        for p in pend:
            grupos.setdefault(re.sub(r"^[A-Za-z]+/[^\s:]+: ", "", str(p.get("message", ""))), []).append(p)
        for texto, ps in grupos.items():
            if len(ps) == 1:
                donde = f"{ps[0].get('file')}:{ps[0].get('line')} " if ps[0].get("file") and ps[0].get("line") else ""
                L.append(f"- [{ps[0].get('source')}] {donde}{str(ps[0].get('message', ''))[:240]}")
            else:
                ejemplos = ", ".join(re.match(r"^([A-Za-z]+/[^\s:]+)", str(p.get("message", ""))).group(1) if re.match(r"^[A-Za-z]+/[^\s:]+", str(p.get("message", ""))) else "?" for p in ps[:4])
                L.append(f"- [{ps[0].get('source')}] **{len(ps)} veces**: {texto[:240]}  (por ejemplo: {ejemplos})")

    L += ["", "## Qué debe revisar una persona", "",
          "Todo lo generado es un **borrador**. En particular:", ""]
    revisar = False
    for s in pasos:
        for c in s.get("reglas") or []:
            L.append(f"- `{c['archivo']}`: regla `{c['regla']}` cambió `{c['antes']}` por `{c['despues']}`"
                     + (f" — {c['nota']}" if c.get("nota") else ""))
            revisar = True
    for a in g.get("advertencias") or []:
        L.append(f"- {a}")
        revisar = True
    if not revisar:
        L.append("- No hubo cambios automáticos ni advertencias que confirmar.")
    L.append("- Los pacientes y valores de los ejemplos son sintéticos; confirma que representan casos reales válidos.")
    if modo:
        L.append("- Confirma que los códigos LOINC y las unidades corresponden a lo que quería la especificación.")
    else:
        L.append("- Confirma que los códigos, bindings y cardinalidades del libro corresponden a lo que quería la guía.")

    llm = report.get("llm") or {}
    seg = (g.get("validacion_y_reparacion") or {}).get("segundos")
    costo = llm.get("total_cost_usd", 0) or 0
    L += ["", "## Modelo y tiempo", "",
          f"- Llamadas al modelo: {llm.get('calls', 0)}"
          + (f" (costo: ${costo:.2f})" if costo > 0 else "")      # el costo solo se muestra con un modelo de pago
          + (f" · Validación y reparación: {seg / 60:.1f} min ({seg:.0f} s)" if seg else "")]
    L += ["", "## Dónde están los archivos", "",
          "- `ig/input/fsh/`: el FSH generado (`perfiles.fsh`, `ejemplos.fsh` y los demás archivos `.fsh`).",
          "- `ig/output/index.html`: la guía publicada (si llegó a compilar).",
          ] + (["- `spec.json`: la ficha que se usó."] if modo else []) + [
          "- `informe.json`: el mismo informe en formato técnico.", ""]
    return "\n".join(L)
