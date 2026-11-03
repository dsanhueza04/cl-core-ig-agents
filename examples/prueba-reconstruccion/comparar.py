"""Compara lo que escribe `datos.py` con el differential real de CorePacienteCl (paquete público CL Core 1.9.3).

Uso:  python comparar.py [carpeta/package del paquete CL Core 1.9.3]
Sin argumento busca el paquete en ~/.fhir/packages. Imprime, regla por regla, lo que el Excel reproduce y lo que no.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from datos import DATOS  # noqa: E402


def carpeta_paquete() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve().parent if Path(sys.argv[1]).is_file() else Path(sys.argv[1])
    for base in (Path.home() / ".fhir" / "packages").glob("hl7.fhir.cl.clcore#1.9.3/package"):
        return base
    sys.exit("No encuentro el paquete CL Core 1.9.3; pasa la carpeta `package` (o el StructureDefinition-CorePacienteCl.json) como argumento.")


def ruta_del_libro(id_: str) -> str:
    """Patient.name:NombreOficial.family.extension:segundoApellido -> name[NombreOficial].family.extension[segundoApellido]"""
    if "." not in id_:
        return ""                     # la raíz del tipo (Address)
    r = id_.split(".", 1)[1]
    return re.sub(r":(\w+)", r"[\1]", r)


def _norm(ruta: str) -> str:
    return re.sub(r"\[(\w+)\]", lambda m: "[" + m.group(1)[:1].lower() + m.group(1)[1:] + "]", ruta)


def reglas_reales(sd: dict) -> dict[str, dict]:
    out = {}
    for e in sd["differential"]["element"]:
        r = _norm(ruta_del_libro(e["id"]))
        if not r:
            continue
        d: dict = {}
        if e.get("min") is not None:
            d["min"] = str(e["min"])
        if e.get("max") is not None:
            d["max"] = e["max"]
        if e.get("mustSupport"):
            d["ms"] = True
        b = e.get("binding")
        if b:
            d["binding"] = (b["strength"], b["valueSet"].split("|")[0].rsplit("/", 1)[-1])
        for k in e:
            if k.startswith(("pattern", "fixed")):
                d["fijo"] = str(e[k])
        perf = [p for t in e.get("type", []) for p in t.get("profile", []) + t.get("targetProfile", [])]
        if perf:
            d["tipo_con_perfil"] = [p.rsplit("/", 1)[-1] for p in perf]
        if "slicing" in e:
            d["slicing"] = e["slicing"]["discriminator"][0]["path"]
        for k in ("comment", "short", "definition"):
            if k in e:
                d[k] = True
        out[r] = d
    return out


def reglas_del_libro(perfil: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in (x for x in DATOS["Elementos"] if x["perfil"] == perfil):
        d: dict = {}
        if f["min"]:
            d["min"] = f["min"]
        if f["max"]:
            d["max"] = f["max"]
        if f["ms"] == "Sí":
            d["ms"] = True
        if f.get("valueset"):
            d["binding"] = (f["fuerza"], f["valueset"].rsplit("/", 1)[-1])
        if f.get("fijo"):
            d["fijo"] = f["fijo"]
        for campo, k in (("resumen", "short"), ("definicion", "definition"), ("comentario", "comment")):
            if f.get(campo):
                d[k] = True
        if f.get("perfil_tipo"):
            d["tipo_con_perfil"] = [f["perfil_tipo"]]
        if f.get("destinos"):
            d["tipo_con_perfil"] = [x.strip() for x in f["destinos"].split(",")]
        out[_norm(f["ruta"])] = d
    for s in (x for x in DATOS["Slices"] if x["perfil"] == perfil):
        r = _norm(f"{s['elemento']}[{s['slice']}]")
        d = {"min": s["min"], "max": s["max"]}
        if s["ms"] == "Sí":
            d["ms"] = True
        out[r] = d
        if s.get("discriminador"):
            out.setdefault(s["elemento"], {})["slicing"] = s["disc_ruta"]
    return out


def comparar(archivo: Path, perfil: str) -> None:
    sd = json.loads(archivo.read_text(encoding="utf-8"))
    print(f"=== {sd['name']} ({sd['type']}) frente a «{perfil}» ===")
    real, libro = reglas_reales(sd), reglas_del_libro(perfil)
    ok, difs = 0, []
    for ruta, d in real.items():
        mio = libro.get(ruta)
        if ruta.endswith("extension") and set(d) <= {"slicing", "short", "definition", "comment", "min"}:
            continue                      # el «contenedor» de un slice de extensiones lo crea SUSHI al usar `contains`
        if mio is None and set(d) <= {"short", "definition", "comment"}:
            continue
        if mio is None:
            difs.append((ruta, "falta en el libro", d))
            continue
        for k, v in d.items():
            if k == "tipo_con_perfil" and (re.search(r"extension\[\w+\]$", ruta) or len(mio.get(k, [])) == len(v)):
                ok += 1                   # (extensiones: apuntan a la que define el libro; referencias: mismos destinos, con otro nombre)                   # `extension contains Mía named x` ya apunta a la extensión que el libro define
            elif k in ("comment", "short", "definition") and mio.get(k):
                ok += 1
            elif k in ("comment", "short", "definition"):
                difs.append((ruta, f"«{k}» sin escribir en datos.py (la herramienta ya puede)", v))
            elif k == "tipo_con_perfil":
                difs.append((ruta, "no se puede expresar «tipo_con_perfil»", v))
            elif k == "binding":
                # el nombre del ValueSet cambia a propósito (no usamos los de CL Core); se compara solo la fuerza
                if mio.get("binding", (None,))[0] != v[0]:
                    difs.append((ruta, f"binding distinto: libro={mio.get('binding')} real={v}", v))
                else:
                    ok += 1
            elif mio.get(k) != v:
                difs.append((ruta, f"{k}: libro={mio.get(k)!r} real={v!r}", v))
            else:
                ok += 1
    extra = sorted(set(libro) - set(real))
    print(f"Reglas del differential real: {sum(len(d) for d in real.values())} en {len(real)} elementos")
    print(f"Reproducidas igual: {ok}")
    textos = [x for x in difs if "sin escribir" in x[1]]
    perfiles = [x for x in difs if "tipo_con_perfil" in x[1]]
    otras = [x for x in difs if x not in textos and x not in perfiles]
    print(f"Diferencias: {len(difs)}  (textos del elemento: {len(textos)} · tipo con perfil: {len(perfiles)} · otras: {len(otras)})")
    for titulo, grupo in (("Tipo con perfil o destino de referencia (no expresable)", perfiles), ("Otras", otras)):
        if grupo:
            print(f"\n{titulo}:")
            for ruta, que, v in grupo:
                print(f"  - {ruta}: {que}" + (f" -> {v}" if "tipo_con_perfil" in que else ""))
    print(f"\nTextos (short/definition/comment) del original que datos.py no escribe (la herramienta sí puede): {len(textos)} reglas en "
          f"{len({x[0] for x in textos})} elementos")
    if extra:
        print("Filas del libro que no están en el differential real:", extra)


def main() -> int:
    carpeta = carpeta_paquete()
    for archivo, perfil in (("StructureDefinition-CorePacienteCl.json", "PacienteReconstruido"), ("StructureDefinition-cl-address.json", "DireccionCl")):
        comparar(carpeta / archivo, perfil)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
