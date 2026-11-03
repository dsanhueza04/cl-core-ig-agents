"""Crea la carpeta liviana «cl-ig-kit» para probar la herramienta (sin pruebas, mediciones ni material de desarrollo).

    python scripts/crear_kit.py DESTINO [--forzar]

Copia solo lo necesario, agrega LEEME.md y PRIMERA-GUIA.md (de docs/kit/) y comprueba que la copia funciona
(plantilla, revisar y construir --sin-docker en una carpeta limpia).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

CARPETAS = ["libro", "agents", "generator", "validator", "llm", "prompts", "templates", "docker"]
ARCHIVOS = ["cl_ig.py", "Makefile", "LICENSE", ".gitattributes"]
DOCS = ["LIBRO.md", "LICENCIAS.md", "DECISIONES.md", "ARQUITECTURA.md"]
SCRIPTS = ["extract_catalog.py", "extract_elementos.py", "prueba_ida_y_vuelta.py"]
EJEMPLOS = ["libro-demo", "libro-con-paginas", "ejercicio-1-presion-arterial", "prueba-reconstruccion", "demo"]
IGNORAR = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "runs", "output", "temp", "fsh-generated", "input-cache")

PYPROJECT = '''[project]
name = "cl-ig-kit"
version = "0.1.0"
description = "Kit para probar cl-core-ig-agents: del Excel a una guía de implementación FHIR sobre CL Core 1.9.3."
requires-python = ">=3.11"
dependencies = ["openpyxl>=3.1", "pyyaml>=6"]
'''


def crear(destino: Path, forzar: bool = False) -> None:
    if destino.exists():
        if not forzar:
            raise SystemExit(f"{destino} ya existe. Usa --forzar para reemplazarlo.")
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    for c in CARPETAS:
        shutil.copytree(RAIZ / c, destino / c, ignore=IGNORAR)
    for a in ARCHIVOS:
        shutil.copy2(RAIZ / a, destino / a)
    (destino / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (destino / "docs").mkdir()
    for d in DOCS:
        shutil.copy2(RAIZ / "docs" / d, destino / "docs" / d)
    (destino / "scripts").mkdir()
    for s in SCRIPTS:
        shutil.copy2(RAIZ / "scripts" / s, destino / "scripts" / s)
    (destino / "examples").mkdir()
    for e in EJEMPLOS:
        shutil.copytree(RAIZ / "examples" / e, destino / "examples" / e, ignore=IGNORAR)
    (destino / "reference").mkdir()
    shutil.copy2(RAIZ / "reference" / "README.md", destino / "reference" / "README.md")
    shutil.copy2(RAIZ / "docs" / "kit" / "LEEME.md", destino / "README.md")
    shutil.copy2(RAIZ / "docs" / "kit" / "PRIMERA-GUIA.md", destino / "PRIMERA-GUIA.md")
    sys.path.insert(0, str(RAIZ))
    from libro.plantilla import guardar_plantilla
    guardar_plantilla(destino / "plantilla-vacia.xlsx")      # sin catálogo de CL Core: no se redistribuye
    (destino / ".gitignore").write_text("build/\nruns/\nreference/*\n!reference/README.md\n__pycache__/\n*.pyc\n", encoding="utf-8")


def comprobar(destino: Path) -> list[str]:
    if not (destino / "plantilla-vacia.xlsx").is_file():
        return ["falta plantilla-vacia.xlsx"]
    """Corre el flujo sin Docker en una copia limpia; devuelve los problemas (vacío = funciona)."""
    problemas = []
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "kit"
        shutil.copytree(destino, copia)
        libro = Path(tmp) / "mi-guia.xlsx"
        for args in (["plantilla", str(libro), "--ejemplo"], ["revisar", str(libro)],
                     ["construir", str(libro), "--sin-docker", "--runs", str(Path(tmp) / "runs")],
                     ["estructura", "Patient", "--ruta", "telecom"]):
            r = subprocess.run([sys.executable, "cl_ig.py", *args], cwd=copia, capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                problemas.append(f"cl_ig.py {args[0]} salió con {r.returncode}: {(r.stdout + r.stderr)[-400:]}")
        r = subprocess.run([sys.executable, "cl_ig.py", "catalogo"], cwd=copia, capture_output=True, text=True, timeout=60)
        if r.returncode != 2 or "package.tgz" not in r.stderr:
            problemas.append("catalogo sin paquete no explicó dónde ponerlo: " + (r.stdout + r.stderr)[-300:])
        # el libro en blanco debe abrirse y decir, en español, que falta contenido (no una traza)
        r = subprocess.run([sys.executable, "cl_ig.py", "revisar", str(copia / "plantilla-vacia.xlsx")], cwd=copia, capture_output=True, text=True, timeout=300)
        if "no define ningún perfil" not in r.stdout + r.stderr or "Traceback" in r.stderr:
            problemas.append("revisar sobre plantilla-vacia.xlsx no dio el mensaje esperado: " + (r.stdout + r.stderr)[-300:])
        # el ejemplo de páginas y menú debe construirse y traer las páginas generadas
        ej = copia / "examples" / "libro-con-paginas" / "libro-con-paginas.xlsx"
        r = subprocess.run([sys.executable, "cl_ig.py", "construir", str(ej), "--sin-docker", "--runs", str(copia / "runs-ej")], cwd=copia, capture_output=True, text=True, timeout=300)
        pagina = next((copia / "runs-ej").glob("*/input/pagecontent/must-support.md"), None)
        if r.returncode != 0 or pagina is None or "birthDate" not in pagina.read_text(encoding="utf-8"):
            problemas.append("el ejemplo libro-con-paginas no generó la página Must Support: " + (r.stdout + r.stderr)[-300:])
    return problemas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("destino")
    ap.add_argument("--forzar", action="store_true")
    a = ap.parse_args()
    destino = Path(a.destino)
    crear(destino, a.forzar)
    problemas = comprobar(destino)
    n = sum(1 for p in destino.rglob("*") if p.is_file())
    print(f"Kit creado en {destino} ({n} archivos).")
    if problemas:
        print("La copia NO pasó la comprobación:")
        for p in problemas:
            print(" -", p)
        return 1
    print("Comprobado en una copia limpia: plantilla, revisar, construir --sin-docker y estructura funcionan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
