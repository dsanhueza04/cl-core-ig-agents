#!/usr/bin/env python3
"""cl-ig: genera y repara Guías de Implementación FHIR sobre CL Core 1.9.3 (borradores para revisión humana).

Comandos:
    python cl_ig.py diagnostico                      revisa que todo esté listo (Docker, catálogo, modelo)
    python cl_ig.py imagen                           crea la imagen de Docker (una vez; equivale a make build)
    python cl_ig.py catalogo                         extrae el catálogo de CL Core (una vez; equivale a make catalog)
    python cl_ig.py ejemplos                         lista las especificaciones de ejemplo
    python cl_ig.py generar ENTRADA [--local]        crea una guía; ENTRADA puede ser:
                                                       una especificación .md  (necesita un modelo: --local)
                                                       una ficha .json         (no necesita modelo)
    python cl_ig.py reparar CARPETA_IG [--local]     repara una guía FSH que no pasa la validación

Desde una planilla de Excel (sin escribir FSH):
    python cl_ig.py plantilla [archivo.xlsx]         crea el libro vacío (con --ejemplo, uno de demostración completo)
    python cl_ig.py revisar libro.xlsx               revisa la coherencia y explica cada problema
    python cl_ig.py construir libro.xlsx             revisa, escribe la guía y la valida (SUSHI + publisher)
    python cl_ig.py importar paquete.tgz             convierte un paquete FHIR existente en un libro de Excel

Cada ejecución deja en runs/<fecha>/ un informe.md que explica qué hizo el sistema y qué debe revisar una persona.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))

IMAGEN = "cl-core-ig-agents/ig-tools:dev"
CATALOGO = Path("build/catalog/catalog.json")
PAQUETE = Path("reference/clcore-1.9.3/site/package.tgz")
MODELO_LOCAL = "qwen2.5:7b"


def _ejecutar(cmd: list[str], runner=subprocess.run) -> tuple[bool, str]:
    try:
        r = runner(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def diagnostico(env=None, runner=subprocess.run, urlopen=urllib.request.urlopen, raiz: Path = Path(".")) -> list[tuple[str, bool, str, bool]]:
    """Lista de (qué se revisó, ¿ok?, cómo arreglarlo, ¿es obligatorio?)."""
    env = os.environ if env is None else env
    filas: list[tuple[str, bool, str, bool]] = []
    filas.append(("Python 3.11 o superior", sys.version_info >= (3, 11), "Instala Python 3.11 o superior (en Windows, desde python.org; marca «Add Python to PATH»).", True))
    ok_docker, _ = _ejecutar(["docker", "info"], runner)
    filas.append(("Docker está encendido", ok_docker, "Abre Docker Desktop y espera a que diga que está en marcha.", True))
    ok_img = ok_docker and _ejecutar(["docker", "image", "inspect", IMAGEN], runner)[0]
    filas.append(("Imagen con SUSHI e IG Publisher", ok_img, "Ejecuta: python cl_ig.py imagen", True))
    filas.append(("Paquete CL Core 1.9.3", (raiz / PAQUETE).is_file(), "Pon package.tgz en reference/clcore-1.9.3/site/ (ver reference/README.md).", True))
    filas.append(("Catálogo de CL Core", (raiz / CATALOGO).is_file(), "Ejecuta: python cl_ig.py catalogo", True))
    backend = env.get("LLM_BACKEND", "mock").strip().lower()
    if backend == "local":
        base = env.get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        base = base[:-3] if base.endswith("/v1") else base
        modelo = env.get("LLM_MODEL", MODELO_LOCAL)
        try:
            import json
            with urlopen(f"{base}/api/tags", timeout=5) as r:
                nombres = [m.get("name", "") for m in json.load(r).get("models", [])]
            ok_modelo = any(n == modelo or n.split(":")[0] == modelo for n in nombres)
            ayuda = f"Descarga el modelo: ollama pull {modelo}"
            filas.append((f"Ollama responde y tiene el modelo {modelo}", ok_modelo, ayuda, False))
        except (OSError, ValueError, urllib.error.URLError):
            filas.append(("Ollama responde", False, "Enciende Ollama (en Windows) y revisa que WSL use networkingMode=mirrored.", False))
    elif backend == "mock":
        filas.append(("Modelo: simulado (mock)", True, "Para leer especificaciones .md usa --local; con una ficha .json no hace falta modelo.", False))
    else:
        filas.append((f"Modelo: {backend}", True, "", False))
    return filas


def _simbolos() -> tuple[str, str, str, str]:
    """(ok, falta, opcional, flecha): los símbolos Unicode si la consola los puede mostrar; si no (cmd de Windows), texto simple."""
    try:
        for c in "✓✗·→":
            c.encode(getattr(sys.stdout, "encoding", None) or "utf-8")
        return "✓", "✗", "·", "→"
    except (UnicodeEncodeError, LookupError):
        return "[OK]", "[FALTA]", "[ ]", "->"


def _imprimir_diagnostico(filas) -> bool:
    todo_ok = True
    ok_, mal, opc, flecha = _simbolos()
    for nombre, ok, ayuda, obligatorio in filas:
        marca = ok_ if ok else (mal if obligatorio else opc)
        print(f" {marca} {nombre}" + ("" if ok or not ayuda else f"\n     {flecha} {ayuda}"))
        todo_ok &= ok or not obligatorio
    print("\nTodo listo." if todo_ok else f"\nFalta algo obligatorio (marcado con {mal}).")
    return todo_ok


def _usar_local(args) -> None:
    if args.local:
        os.environ["LLM_BACKEND"] = "local"
        os.environ.setdefault("LLM_MODEL", MODELO_LOCAL)


def _ultimo_informe(runs: str, desde: float) -> Path | None:
    candidatos = [p for p in Path(runs).glob("*/informe.md") if p.stat().st_mtime >= desde - 1]
    return max(candidatos, key=lambda p: p.stat().st_mtime) if candidatos else None


def _mostrar_resumen(informe: Path | None) -> None:
    if informe is None:
        return
    texto = informe.read_text(encoding="utf-8").splitlines()
    print("\n" + "\n".join(texto[2:6]).strip())
    print(f"\nInforme completo: {informe}")


def cmd_ejemplos() -> int:
    print("Especificaciones de ejemplo (para: python cl_ig.py generar RUTA --local):\n")
    for spec in sorted(Path("examples").glob("**/spec.md")):
        print(f"  {spec}   (ficha de referencia: {spec.with_name('spec.json')})")
    return 0


def cmd_generar(args) -> int:
    import time
    entrada = Path(args.entrada)
    if not entrada.is_file():
        print(f"No existe {entrada}. Mira las opciones con: python cl_ig.py ejemplos", file=sys.stderr)
        return 2
    _usar_local(args)
    es_ficha = entrada.suffix.lower() == ".json"
    if not es_ficha and os.environ.get("LLM_BACKEND", "mock").lower() == "mock":
        print("Para leer una especificación (.md) hace falta un modelo. Opciones:\n"
              "  · agrega --local (usa Ollama con qwen2.5:7b, gratis), o\n"
              "  · entrega una ficha .json ya hecha (no necesita modelo), por ejemplo\n"
              "    python cl_ig.py generar examples/casos/peso-talla/spec.json", file=sys.stderr)
        return 2
    from agents import generate
    argv = (["--spec-json", str(entrada)] if es_ficha else ["--spec", str(entrada)])
    argv += ["--runs", args.runs, "--max-iterations", str(args.max_iteraciones)]
    if args.sin_docker:
        argv.append("--sin-docker")
    if args.titulo:
        argv += ["--title", args.titulo]
    inicio = time.time()
    codigo = generate.main(argv)
    _mostrar_resumen(_ultimo_informe(args.runs, inicio))
    return codigo


def cmd_reparar(args) -> int:
    import time
    if not (Path(args.carpeta) / "sushi-config.yaml").is_file():
        print(f"{args.carpeta} no parece una guía (falta sushi-config.yaml).", file=sys.stderr)
        return 2
    _usar_local(args)
    from agents import run
    argv = ["--ig", args.carpeta, "--runs", args.runs, "--max-iterations", str(args.max_iteraciones)]
    if args.sin_reglas:
        argv.append("--sin-reglas")
    inicio = time.time()
    codigo = run.main(argv)
    _mostrar_resumen(_ultimo_informe(args.runs, inicio))
    return codigo


def _cargar_catalogo(silencioso: bool = False):
    from agents.catalog import CatalogIndex
    try:
        return CatalogIndex.from_file(CATALOGO)
    except FileNotFoundError:
        if silencioso:
            return None
        print("(Sin catálogo de CL Core: no puedo comprobar nombres de CL Core. Se crea con `python cl_ig.py catalogo`.)\n", file=sys.stderr)
        return None


def cmd_imagen(args) -> int:
    """Crea la imagen de Docker con SUSHI, el IG Publisher y Jekyll (lo que hace `make build`, sin necesitar make)."""
    if not shutil.which("docker"):
        print("No encuentro Docker. Instala Docker Desktop, ábrelo y vuelve a intentar.", file=sys.stderr)
        return 2
    print(f"Creando la imagen {IMAGEN} (la primera vez tarda varios minutos)...")
    try:
        r = subprocess.run(["docker", "build", "-t", IMAGEN, "-f", str(Path("docker") / "Dockerfile"), "docker"])
    except OSError as e:
        print(f"No pude ejecutar Docker: {e}", file=sys.stderr)
        return 2
    if r.returncode != 0:
        print("No se pudo crear la imagen. ¿Docker Desktop está abierto y con internet? Corre: python cl_ig.py diagnostico", file=sys.stderr)
        return r.returncode
    print(f"Imagen lista: {IMAGEN}")
    return 0


def cmd_catalogo(args) -> int:
    """Extrae el catálogo de CL Core (lo que hace `make catalog`, sin necesitar make)."""
    paquete = Path(args.package or PAQUETE)
    if not paquete.exists():
        print(f"No encuentro el paquete de CL Core en {paquete}.\n"
              "Descarga hl7.fhir.cl.clcore 1.9.3 (package.tgz) y déjalo en reference/clcore-1.9.3/site/package.tgz,\n"
              "o pasa otra ruta con --package (un .tgz o la carpeta del paquete). Ver README.md, sección «Con CL Core instalado».", file=sys.stderr)
        return 2
    r = subprocess.run([sys.executable, str(Path("scripts") / "extract_catalog.py"), "--package", str(paquete), "--out", str(CATALOGO.parent)])
    if r.returncode == 0:
        print(f"Catálogo listo en {CATALOGO.parent}. Ahora: python cl_ig.py diagnostico")
    return r.returncode


def cmd_plantilla(args) -> int:
    from libro.ejemplo import DATOS
    from libro.plantilla import guardar_plantilla
    destino = Path(args.archivo or ("libro-demo.xlsx" if args.ejemplo else "libro-ig.xlsx"))
    if destino.exists() and not args.forzar:
        print(f"{destino} ya existe. Usa --forzar para reemplazarlo.", file=sys.stderr)
        return 2
    try:
        from agents.catalog import CatalogIndex
        catalogo = CatalogIndex.from_file(CATALOGO)
    except FileNotFoundError:
        catalogo = None
        print("(Sin catálogo de CL Core: la lista de perfiles padre quedará vacía. Se crea con `python cl_ig.py catalogo`.)", file=sys.stderr)
    from libro import elementos
    if not elementos.hay_datos():
        print("(Sin libro/datos/elementos_r4.json: no habrá lista de elementos. Ver scripts/extract_elementos.py.)", file=sys.stderr)
    guardar_plantilla(destino, DATOS if args.ejemplo else None, catalogo)
    print(f"Listo: {destino}\nÁbrelo en Excel, empieza por la hoja «Guía» y luego ejecuta: python cl_ig.py revisar {destino}")
    return 0


def _revisar(ruta: str):
    from libro.lector import LibroInvalido, leer_libro
    from libro.revisar import revisar_libro
    if not Path(ruta).is_file():
        print(f"No existe {ruta}.", file=sys.stderr)
        return None, None, None
    try:
        libro = leer_libro(ruta)
    except LibroInvalido as e:
        print(f"No puedo leer el libro: {e}", file=sys.stderr)
        return None, None, None
    catalogo = _cargar_catalogo()
    return libro, catalogo, revisar_libro(libro, catalogo)


def cmd_revisar(args) -> int:
    from libro.revisar import hay_errores, texto_avisos
    libro, _, avisos = _revisar(args.libro)
    if avisos is None:
        return 2
    print(texto_avisos(avisos))
    return 1 if hay_errores(avisos) else 0


def cmd_importar(args) -> int:
    """Convierte un paquete FHIR (carpeta o .tgz) en un libro de Excel y comprueba que el libro resultante sea coherente."""
    import tarfile
    import tempfile
    from libro.importar_paquete import importar_paquete
    from libro.plantilla import guardar_plantilla
    from libro.revisar import hay_errores, revisar_libro
    from libro.lector import leer_libro
    origen = Path(args.paquete)
    destino = Path(args.salida or (origen.stem.replace(".tgz", "") + "-libro.xlsx"))
    if destino.exists() and not args.forzar:
        print(f"{destino} ya existe. Usa --forzar para reemplazarlo.", file=sys.stderr)
        return 2
    if not origen.exists():
        print(f"No encuentro {origen}.", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = origen
        if origen.is_file():
            try:
                with tarfile.open(origen) as tf:
                    seguros = [m for m in tf.getmembers() if m.isfile() and not Path(m.name).is_absolute() and ".." not in Path(m.name).parts]
                    tf.extractall(tmp, members=seguros)
            except (tarfile.TarError, OSError) as e:
                print(f"No pude abrir {origen} como paquete (.tgz): {e}", file=sys.stderr)
                return 2
            carpeta = Path(tmp)
        base = carpeta / "package" if (carpeta / "package").is_dir() else carpeta
        canonical = args.canonical
        titulo = args.titulo
        try:
            meta = json.loads((base / "package.json").read_text(encoding="utf-8"))
            canonical = canonical or meta.get("canonical", "")
            titulo = titulo or meta.get("title") or meta.get("name", "")
        except (OSError, ValueError):
            pass
        catalogo = _cargar_catalogo(silencioso=True)
        try:
            datos, inf = importar_paquete(base, canonical=canonical, con_textos=args.con_textos, titulo=titulo or "Guía importada", catalogo=catalogo)
        except Exception as e:     # paquete ilegible: se explica, no se muestra traza
            print(f"No pude importar: {e}", file=sys.stderr)
            return 2
    if not inf.recursos:
        print("No encontré StructureDefinition, CodeSystem ni ValueSet en ese paquete.", file=sys.stderr)
        return 2
    guardar_plantilla(destino, datos)
    print(inf.texto())
    avisos = revisar_libro(leer_libro(destino), catalogo)
    print(f"\nLibro escrito: {destino}")
    print(f"Revisión del libro: {sum(a.nivel == 'error' for a in avisos)} errores, {sum(a.nivel == 'aviso' for a in avisos)} avisos."
          + (" Hay errores: el libro se ve igual, pero conviene corregirlos antes de construir." if hay_errores(avisos) else ""))
    print("Los textos explicativos del original no se copian: las descripciones de CodeSystems, ValueSets y declaraciones quedan como «importado de un paquete».\n"
          "Usa --con-textos si el paquete es tuyo o su licencia lo permite.")
    print(f"Siguiente paso: python cl_ig.py revisar {destino}   (y python cl_ig.py construir {destino})")
    return 0


def cmd_estructura(args) -> int:
    from libro.estructura import estructura
    print(estructura(args.nombre, _cargar_catalogo(), args.ruta or "", args.profundidad))
    return 0


def cmd_construir(args) -> int:
    import time
    from libro.fsh import construir_archivos, construir_binarios
    from libro.revisar import hay_errores, texto_avisos
    libro, catalogo, avisos = _revisar(args.libro)
    if avisos is None:
        return 2
    print(texto_avisos(avisos))
    if hay_errores(avisos):
        print("No construyo la guía mientras haya errores. Corrígelos en el Excel y vuelve a ejecutar.", file=sys.stderr)
        return 1
    salida = Path(args.salida or f"{args.runs}/{time.strftime('%Y%m%d-%H%M%S')}-{libro.guia['id']}")
    for ruta, texto in construir_archivos(libro, catalogo).items():
        destino = salida / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8", newline="\n")
    for ruta, datos in construir_binarios(libro).items():
        destino = salida / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(datos)
    (salida / "avisos-del-libro.txt").write_text(texto_avisos(avisos), encoding="utf-8")
    print(f"Guía escrita en {salida}")
    if catalogo is not None and not args.sin_docker:
        # Un libro se corrige en el Excel, no en el FSH ni con un modelo: si el chequeo previo ya encuentra algo, se dice aquí y no se gastan 8 minutos de Docker.
        from validator.precheck import precheck_path
        pendientes = [(f, i) for f, iss in precheck_path(salida / "input" / "fsh", catalogo).items() for i in iss]
        if pendientes:
            print(f"\nEl chequeo previo encontró {len(pendientes)} referencia(s) a CL Core que no existen. No sigo con Docker:", file=sys.stderr)
            for f, i in pendientes[:20]:
                print(f"  - {f}:{i.line} {i.message}" + (f" ({i.suggestion})" if i.suggestion else ""), file=sys.stderr)
            print("Corrígelo en el libro de Excel y vuelve a ejecutar. Si el libro está bien, es un caso que la herramienta no cubre: guarda este mensaje.", file=sys.stderr)
            return 1
    if args.sin_docker:
        print(f"Falta validarla con SUSHI y el publisher: python cl_ig.py reparar {salida}")
        return 0
    from agents import run
    argv = ["--ig", str(salida), "--runs", args.runs, "--max-iterations", "1", "--sin-reparar", "--timeout-min", str(args.timeout_min)]
    grande = len(libro.filas("Perfiles")) + len(libro.filas("Extensiones")) + len(libro.filas("CodeSystems")) > 40
    print("Validando con SUSHI y el IG Publisher en Docker" + (": es una guía grande, puede tardar 25 minutos o más." if grande else " (unos 6 minutos)."))
    inicio = time.time()
    codigo = run.main(argv)
    _mostrar_resumen(_ultimo_informe(args.runs, inicio))
    return codigo


def cmd_importar_codigos(args) -> int:
    from libro.importar import importar_codigos
    origen = Path(args.libro)
    destino = Path(args.salida or origen.with_name(origen.stem + "-importado.xlsx"))
    if destino.resolve() == origen.resolve():
        print("La salida no puede ser el mismo libro: el original no se modifica.", file=sys.stderr)
        return 2
    if destino.exists() and not args.forzar:
        print(f"{destino} ya existe. Usa --forzar para reemplazarlo.", file=sys.stderr)
        return 2
    try:
        r = importar_codigos(origen, args.csv, args.codesystem, destino, col_codigo=args.col_codigo, col_texto=args.col_texto,
                             col_definicion=args.col_definicion, titulo=args.titulo or "")
    except Exception as e:   # libro o CSV inválidos: se explica, no se muestra traza
        print(f"No pude importar: {e}", file=sys.stderr)
        return 2
    print(f"{r.nuevos} códigos nuevos en «{args.codesystem}»" + (" (CodeSystem creado)" if r.creado_codesystem else "") + f"; {r.repetidos} ya existían.")
    for linea in r.distintos:
        print(f"  Texto distinto, se conserva el del libro: {linea}")
    if r.omitidos:
        print(f"  Omitidas por no tener código o texto: {', '.join(r.omitidos[:10])}")
    print(f"Libro nuevo: {destino} (el original no cambió). Revísalo: python cl_ig.py revisar {destino}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cl_ig.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("diagnostico", help="revisa que todo esté listo")
    sub.add_parser("ejemplos", help="lista las especificaciones de ejemplo")
    for nombre, ayuda in (("generar", "crea una guía"), ("reparar", "repara una guía existente")):
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("entrada" if nombre == "generar" else "carpeta")
        p.add_argument("--local", action="store_true", help=f"usa el modelo local (Ollama, {MODELO_LOCAL})")
        p.add_argument("--runs", default="runs")
        p.add_argument("--max-iteraciones", type=int, default=5)
        if nombre == "generar":
            p.add_argument("--sin-docker", action="store_true", help="solo chequeo previo; no corre SUSHI ni el publisher")
            p.add_argument("--titulo")
        else:
            p.add_argument("--sin-reglas", action="store_true", help="no aplica las reglas deterministas")
    sub.add_parser("imagen", help="crea la imagen de Docker con SUSHI e IG Publisher (reemplaza `make build`)")
    p = sub.add_parser("catalogo", help="extrae el catálogo de CL Core (reemplaza `make catalog`)")
    p.add_argument("--package", help="package.tgz o carpeta del paquete (por defecto reference/clcore-1.9.3/site/package.tgz)")
    p = sub.add_parser("plantilla", help="crea el libro de Excel")
    p.add_argument("archivo", nargs="?")
    p.add_argument("--ejemplo", action="store_true", help="con un ejemplo sintético completo")
    p.add_argument("--forzar", action="store_true")
    p = sub.add_parser("revisar", help="revisa un libro de Excel")
    p.add_argument("libro")
    p = sub.add_parser("importar-codigos", help="agrega a un libro los códigos de un CSV (escribe un libro nuevo)")
    p.add_argument("libro")
    p.add_argument("csv")
    p.add_argument("--codesystem", required=True, help="nombre del CodeSystem (se crea si no existe)")
    p.add_argument("--col-codigo")
    p.add_argument("--col-texto")
    p.add_argument("--col-definicion")
    p.add_argument("--titulo")
    p.add_argument("--salida")
    p.add_argument("--forzar", action="store_true")
    p = sub.add_parser("importar", help="convierte un paquete FHIR (carpeta o .tgz) en un libro de Excel")
    p.add_argument("paquete", help="carpeta con los JSON, o el package.tgz")
    p.add_argument("--salida")
    p.add_argument("--titulo")
    p.add_argument("--canonical", default="", help="URL base de la guía (si el paquete no trae package.json)")
    p.add_argument("--con-textos", action="store_true", help="copia también las descripciones del original (solo si el paquete es tuyo)")
    p.add_argument("--forzar", action="store_true")
    p = sub.add_parser("estructura", help="muestra los elementos de un recurso o perfil, con su cardinalidad y tipo")
    p.add_argument("nombre", help="un recurso (Patient) o un perfil de CL Core (CorePacienteCl)")
    p.add_argument("--ruta", help="solo este elemento y sus hijos (por ejemplo telecom)")
    p.add_argument("--profundidad", type=int, default=2)
    p = sub.add_parser("construir", help="genera y valida la guía de un libro")
    p.add_argument("libro")
    p.add_argument("--salida")
    p.add_argument("--runs", default="runs")
    p.add_argument("--timeout-min", type=int, default=60, help="minutos máximos de la validación con Docker (CL Core completo tarda unos 25)")
    p.add_argument("--sin-docker", action="store_true", help="solo escribe la guía; no corre SUSHI ni el publisher")
    args = ap.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):      # la consola de Windows (cp850/cp1252) no puede mostrar flechas ni emojis: se reemplazan en vez de fallar
        try:
            flujo.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    os.chdir(RAIZ)   # las rutas del proyecto (build/, reference/, runs/) son relativas a la raíz del repo
    if args.cmd == "diagnostico":
        return 0 if _imprimir_diagnostico(diagnostico()) else 1
    if args.cmd == "ejemplos":
        return cmd_ejemplos()
    if args.cmd == "generar":
        return cmd_generar(args)
    if args.cmd == "reparar":
        return cmd_reparar(args)
    if args.cmd == "imagen":
        return cmd_imagen(args)
    if args.cmd == "catalogo":
        return cmd_catalogo(args)
    if args.cmd == "plantilla":
        return cmd_plantilla(args)
    if args.cmd == "revisar":
        return cmd_revisar(args)
    if args.cmd == "importar-codigos":
        return cmd_importar_codigos(args)
    if args.cmd == "importar":
        return cmd_importar(args)
    if args.cmd == "estructura":
        return cmd_estructura(args)
    if args.cmd == "construir":
        return cmd_construir(args)
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
