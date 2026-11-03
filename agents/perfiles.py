"""Agente de perfiles: de una especificación (diccionario de datos) a FSH de perfiles.

Flujo:
  1. arma un prompt pequeño (reglas + ejemplo + catálogo por demanda),
  2. pide el FSH al modelo,
  3. revisa las referencias a CL Core sin modelo (`validator.precheck`),
  4. si hay referencias inventadas, se las devuelve al modelo (máx. `max_fixes` veces).

No ejecuta SUSHI ni el IG Publisher; eso lo hace el validador. Los errores que solo ellos ven
los repara el agente reparador.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from agents.base import (  # noqa: F401  (se reexportan: otros módulos los importan desde aquí)
    DEFAULT_MODEL, FSH_BLOCK, STANDARD_ALIASES, ProfileResult, aliases_fsh, ask_fsh, extract_fsh,
    feedback as _feedback)
from agents.catalog import CatalogIndex
from llm import LLMClient, MockBackend, client_from_env

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"


def build_system(spec: str, catalog: CatalogIndex, max_chars: int = 7500) -> str:
    template = (PROMPTS / "perfiles.md").read_text(encoding="utf-8")
    example = (PROMPTS / "ejemplo_perfil.fsh").read_text(encoding="utf-8").strip()
    return template.format(
        version=catalog.data["version"],
        aliases=", ".join(STANDARD_ALIASES),
        ejemplo=example,
        catalogo=catalog.context(spec, max_chars=max_chars, limit=5),
    )


class ProfileAgent:
    def __init__(self, client: LLMClient, catalog: CatalogIndex, model: str = DEFAULT_MODEL, max_fixes: int = 2):
        self.client, self.catalog, self.model, self.max_fixes = client, catalog, model, max_fixes

    def generate(self, spec: str) -> ProfileResult:
        return ask_fsh(self.client, self.catalog, self.model, "perfiles", build_system(spec, self.catalog),
                       f"Especificación de entrada:\n\n{spec}\n\nEscribe los perfiles FSH.", self.max_fixes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Genera perfiles FSH a partir de una especificación.")
    ap.add_argument("--spec", required=True, help="archivo de especificación (markdown)")
    ap.add_argument("--out", required=True, help="carpeta input/fsh de salida")
    ap.add_argument("--catalog", default="build/catalog/catalog.json")
    ap.add_argument("--model", default=None, help="modelo (por defecto LLM_MODEL o el de pago por defecto)")
    args = ap.parse_args(argv)

    try:
        catalog = CatalogIndex.from_file(args.catalog)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
    client = client_from_env()
    if isinstance(client.backend, MockBackend):
        print("AVISO: modo simulado (LLM_BACKEND=mock). La salida es un ejemplo fijo, no la genera un modelo.",
              file=sys.stderr)
        client.backend = MockBackend(default=f"```fsh\n{(PROMPTS / 'ejemplo_perfil.fsh').read_text(encoding='utf-8')}```")
    model = args.model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
    result = ProfileAgent(client, catalog, model=model).generate(Path(args.spec).read_text(encoding="utf-8"))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "aliases.fsh").write_text(aliases_fsh(), encoding="utf-8")
    (out / "perfiles.fsh").write_text(result.fsh, encoding="utf-8")
    for i in result.issues:
        print(f"perfiles.fsh:{i.line}: [{i.kind}] {i.message}", file=sys.stderr)
    s = client.summary()
    print(f"perfiles.fsh escrito en {out} · intentos: {result.attempts} · llamadas: {s['calls']}" + (f" · costo: ${s['total_cost_usd']:.2f}" if s["total_cost_usd"] > 0 else ""))
    return 0 if result.clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
