"""Ejecuta la validación real (SUSHI + IG Publisher) en Docker sobre una carpeta de IG.

SIN PROBAR en el entorno de desarrollo remoto (no tiene Docker): se prueba en la máquina del usuario.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from agents.loop import Outcome
from validator.parse_qa import Issue, QAReport, _fingerprint, classify, load_report
from validator.parse_sushi import parse_sushi_text

DEFAULT_IMAGE = "cl-core-ig-agents/ig-tools:dev"
DEFAULT_VOLUME = "clcore-fhir-cache"


def write_fsh(ig_dir: Path, files: dict[str, str]) -> None:
    fsh = ig_dir / "input" / "fsh"
    fsh.mkdir(parents=True, exist_ok=True)
    for old in fsh.glob("*.fsh"):
        if old.name not in files:
            old.unlink()
    for name, text in files.items():
        (fsh / name).write_text(text, encoding="utf-8", newline="\n")


def guardar_consola(ig_dir: Path, console: str, codigo: int | None = None) -> None:
    """Deja la última salida de Docker en `consola.txt` (los últimos ~30 000 caracteres) para entender fallos de infraestructura."""
    try:
        cabecera = f"[código de salida de Docker: {codigo}]\n" if codigo is not None else ""
        (Path(ig_dir) / "consola.txt").write_text(cabecera + console[-30000:], encoding="utf-8")
    except OSError:
        pass


def excepcion_del_publisher(output_dir: Path) -> QAReport | None:
    """Si el publisher se cayó con una excepción, solo deja `qa.json` con el campo `exception` (sin qa.txt).

    Se convierte en un error del reporte para que el bucle lo vea; si es de red se clasifica como infraestructura.
    """
    qa_json = Path(output_dir) / "qa.json"
    if not qa_json.is_file():
        return None
    try:
        exc = json.loads(qa_json.read_text(encoding="utf-8")).get("exception")
    except (ValueError, OSError):
        return None
    if not exc:
        return None
    mensaje = f"El IG Publisher terminó con una excepción: {exc}"
    return QAReport(issues=[Issue("error", classify("error", mensaje), mensaje,
                                  fingerprint=_fingerprint("error", None, None, mensaje))])


def docker_validate(ig_dir: str | Path, clcore_tgz: str | Path, image: str = DEFAULT_IMAGE,
                    cache_volume: str = DEFAULT_VOLUME, timeout_s: int = 3600, runner=subprocess.run):
    """Devuelve una función `validate(files) -> Outcome` ligada a una carpeta de IG."""
    ig_dir, clcore_tgz = Path(ig_dir).resolve(), Path(clcore_tgz).resolve()

    def validate(files: dict[str, str]) -> Outcome:
        write_fsh(ig_dir, files)
        qa = ig_dir / "output" / "qa.txt"
        qa.unlink(missing_ok=True)
        (ig_dir / "output" / "qa.json").unlink(missing_ok=True)
        try:
            proc = runner(
                ["docker", "run", "--rm", "-v", f"{ig_dir}:/ig", "-v", f"{clcore_tgz}:/reference/clcore.tgz:ro",
                 "-v", f"{cache_volume}:/root/.fhir", image],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            salida = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            guardar_consola(ig_dir, salida + f"\n[Docker superó el tiempo máximo de {timeout_s // 60} minutos y se detuvo]\n")
            return Outcome()                      # sin informe ni errores de SUSHI → infraestructura
        console = (proc.stdout or "") + (proc.stderr or "")
        guardar_consola(ig_dir, console, getattr(proc, "returncode", None))
        if qa.is_file():
            return Outcome(report=load_report(qa))
        sushi = parse_sushi_text(console)
        if not sushi and (caida := excepcion_del_publisher(ig_dir / "output")):
            return Outcome(report=caida)
        return Outcome(sushi_issues=sushi)

    return validate
