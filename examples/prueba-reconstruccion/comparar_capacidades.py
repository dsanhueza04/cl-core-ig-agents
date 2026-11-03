"""Prueba de reconstrucción de los CapabilityStatement de CL Core 1.9.3 (server y client).

Uso:  python comparar_capacidades.py <carpeta con CapabilityStatement-cl-core-server.json y -client.json>
Lee cada declaración, la convierte a filas del libro (sin copiar sus textos), genera el FSH con la herramienta y comprueba
regla por regla que dice lo mismo que el original: recursos, perfiles, operaciones, búsquedas y expectativas.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
from libro.fsh import construir_archivos  # noqa: E402
from libro.importar import aplanar_capacidad_fsh, aplanar_capacidad_json, capacidad_desde_json  # noqa: E402
from libro.lector import leer_libro  # noqa: E402
from libro.plantilla import guardar_plantilla  # noqa: E402
from libro.revisar import revisar_libro, texto_avisos  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    carpeta = Path(sys.argv[1])
    datos = {"Guía": {"id": "capacidades-reconstruidas", "titulo": "Capacidades reconstruidas", "usa_clcore": "No"},
             "Perfiles": [{"nombre": "Marcador", "recurso": "Patient", "titulo": "Marcador", "descripcion": "Perfil mínimo para que el libro sea válido."}]}
    originales = {}
    for nombre, archivo in (("ServidorReconstruido", "CapabilityStatement-cl-core-server.json"), ("ClienteReconstruido", "CapabilityStatement-cl-core-client.json")):
        cs = json.loads((carpeta / archivo).read_text(encoding="utf-8"))
        originales[nombre] = cs
        for hoja, filas in capacidad_desde_json(cs, nombre).items():
            datos.setdefault(hoja, []).extend(filas)
    destino = Path(__file__).with_name("capacidades-reconstruidas.xlsx")
    guardar_plantilla(destino, copy.deepcopy(datos))
    libro = leer_libro(destino)
    avisos = revisar_libro(libro, None)
    print(texto_avisos([a for a in avisos if a.nivel != "sugerencia"]))
    fsh = construir_archivos(libro, None)["input/fsh/capacidades.fsh"]
    total_ok = total_dif = 0
    for nombre, cs in originales.items():
        inicio = fsh.index(f"Instance: {nombre}")
        fin = fsh.find("\nInstance: ", inicio + 1)
        bloque = fsh[inicio: fin if fin > 0 else None]
        real, mio = aplanar_capacidad_json(cs), aplanar_capacidad_fsh(bloque)
        dif = [(k, real.get(k), mio.get(k)) for k in sorted(set(real) | set(mio)) if real.get(k) != mio.get(k)]
        print(f"=== {nombre}: {len(real)} reglas del original · iguales {len(real) - len([d for d in dif if d[1] is not None])} · diferencias {len(dif)}")
        for k, a, b in dif[:15]:
            print(f"  {k}: original={a!r} libro={b!r}")
        total_ok += len(real) - len([d for d in dif if d[1] is not None]); total_dif += len(dif)
    return 1 if total_dif else 0


if __name__ == "__main__":
    sys.exit(main())
