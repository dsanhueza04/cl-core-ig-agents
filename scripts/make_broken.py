"""Crea una copia del IG de referencia con un error inyectado, para probar el bucle de reparación.

    python scripts/make_broken.py --listar
    python scripts/make_broken.py --caso falta_componente_obligatorio --out build/roto
    python scripts/make_broken.py --out build/roto          # sin --caso: los 2 errores clásicos del precheck

Los casos están en scripts/errores.py. Sin --caso se inyectan juntos `parent_con_typo` y
`codigo_en_codesystem_equivocado` (ambos los detecta el chequeo previo, sin Docker).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.errores import CASOS, aplicar  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="build/roto")
    ap.add_argument("--caso", choices=sorted(CASOS))
    ap.add_argument("--listar", action="store_true")
    args = ap.parse_args()
    if args.listar:
        for c in CASOS.values():
            print(f"{c.nombre:36} [{c.etapa:9}] {'(reservado) ' if c.reservado else ''}{c.descripcion}")
        return 0
    out = Path(args.out)
    if args.caso:
        aplicar(CASOS[args.caso], out)
        print(f"IG con el error '{args.caso}' en {out}")
        return 0
    aplicar(CASOS["parent_con_typo"], out)
    c2 = CASOS["codigo_en_codesystem_equivocado"]
    f = out / "input" / "fsh" / c2.archivo
    f.write_text(f.read_text(encoding="utf-8").replace(c2.buscar, c2.reemplazar, 1), encoding="utf-8")
    print(f"IG con 2 errores inyectados en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
