# cl-ig-builder

**Crea Guías de Implementación FHIR R4 completando un Excel, sin escribir FSH a mano.**

La herramienta revisa tu planilla y te explica en español claro qué no cuadra, escribe el código FSH y lo valida con las herramientas oficiales (SUSHI e IG Publisher). Está pensada para guías de Chile que parten de [CL Core](https://hl7chile.cl/fhir/ig/clcore/) 1.9.3.

> **In short (English):** an Excel workbook describes a FHIR R4 Implementation Guide (profiles, extensions, terminology, examples, pages, menu). The tool checks it in plain language, generates FSH deterministically (same workbook, same output, no AI in the main path) and validates it with SUSHI and the official IG Publisher. Documentation is in Spanish; it targets guides built on CL Core, the Chilean national core.

> **Estado: versión 0.1.** Proyecto independiente, hecho con recursos públicos; no usa código, datos ni documentos internos de ninguna organización. Todo lo que genera es un **borrador: una persona lo revisa siempre.** Aún falta probarlo con usuarios que no lo hayan escrito.

---

## ¿Cómo funciona?

```
Excel (tu guía)  →  revisar  →  FSH  →  SUSHI + IG Publisher  →  guía publicada + informe
                    te dice qué    siempre el mismo     herramientas oficiales,
                    corregir       para el mismo Excel  no un modelo de IA
```

1. **Completas un libro de Excel.** Cada hoja es un tema: Perfiles, Extensiones, CodeSystems, ValueSets, Ejemplos, Páginas, Menú.
2. **`revisar`** detecta incoherencias antes de generar nada y dice cómo arreglarlas.
3. **`construir`** escribe el FSH y lo valida. Al final deja un `informe.md` con lo que pasó y lo que una persona debe revisar.

El mismo Excel produce siempre el mismo FSH. En este camino **no interviene ningún modelo de lenguaje**: es gratis, reproducible y se puede guardar en git.

## ¿Para quién es?

- **Equipos de salud, informáticos clínicos y analistas** que conocen el dominio pero no escriben FSH: definen la guía en una planilla y reciben mensajes que se entienden.
- **Quien ya escribe FSH:** no lo necesita para escribir, pero el FSH generado es legible y se puede seguir editando a mano. También sirve para revisar guías existentes.
- **Quien quiere leer una guía publicada** sin abrir JSON: `importar` convierte un paquete en una planilla.

---

## Pruébalo en 5 minutos (sin Docker)

Necesitas [Python 3.11 o superior](https://www.python.org/downloads/) y dos paquetes:

```
pip install openpyxl pyyaml
```

Desde la carpeta del repositorio (igual en cmd, PowerShell, Linux o macOS):

```
python cl_ig.py revisar examples/libro-con-paginas/libro-con-paginas.xlsx
python cl_ig.py construir examples/libro-con-paginas/libro-con-paginas.xlsx --sin-docker
```

En Windows con cmd, escribe las rutas con `\` (`examples\libro-con-paginas\libro-con-paginas.xlsx`).

1. `revisar` analiza el libro de ejemplo (una guía pequeña con datos inventados) y debe decir «Sin problemas».
2. `construir --sin-docker` escribe la guía en `runs/<fecha>-<id>/`. Abre `input/fsh/perfiles.fsh` para ver el FSH que salió del Excel.
3. Abre `examples/libro-con-paginas/libro-con-paginas.xlsx` en Excel y compara hoja por hoja con el FSH.

`--sin-docker` solo genera el FSH. Para validarlo y obtener la guía publicada, sigue con la sección siguiente.

**Empezar una guía tuya:** `python cl_ig.py plantilla mi-guia.xlsx` crea el libro vacío, con ayuda en cada columna. El paso a paso está en [`docs/kit/PRIMERA-GUIA.md`](docs/kit/PRIMERA-GUIA.md).

## Validar de verdad (con Docker)

Necesitas [Docker Desktop](https://www.docker.com/products/docker-desktop/) abierto:

```
python cl_ig.py diagnostico     # revisa que todo esté listo y dice cómo arreglar lo que falte
python cl_ig.py imagen          # una sola vez: prepara SUSHI, IG Publisher y Jekyll (versiones fijadas)
python cl_ig.py construir examples/libro-con-paginas/libro-con-paginas.xlsx
```

Una validación completa tarda entre 7 y 20 minutos, según el tamaño de la guía. Al terminar, la carpeta de la corrida en `runs/` trae `informe.md` (dice si pasó y qué debe revisar una persona) y la guía publicada (`index.html`, dentro de `output/`); el informe indica dónde quedó cada cosa.

**Si tu guía parte de CL Core** (el caso normal), necesitas además su paquete `package.tgz` en `reference/clcore-1.9.3/site/`. No se incluye en este repositorio porque es de HL7 Chile; se descarga del sitio publicado de CL Core (ver [`reference/README.md`](reference/README.md)). Después, una sola vez:

```
python cl_ig.py catalogo        # extrae el catálogo de CL Core para listas y comprobaciones
```

Sin ese catálogo todo funciona, pero la herramienta no puede comprobar los nombres de CL Core y verás algunos avisos de más.

---

## ¿Qué se puede describir en el libro?

| Tema | Qué incluye |
|---|---|
| **Perfiles** | Cardinalidad, Must Support, tipos, bindings, valores fijos, textos, slicing e invariantes FHIRPath |
| **Extensiones** | Simples y complejas, con su ValueSet |
| **Terminología** | CodeSystems y ValueSets (con filtros), ConceptMaps |
| **Ejemplos** | Recursos de ejemplo, Bundles de mensaje, Questionnaire y sus respuestas |
| **Comportamiento** | CapabilityStatement, SearchParameter, OperationDefinition |
| **El texto de la guía** | Páginas en Markdown (incluso dentro de otras), menú propio con desplegables, página *Must Support* generada, historial de cambios e imágenes |

Detalle hoja por hoja en [`docs/LIBRO.md`](docs/LIBRO.md). Texto, menú e imágenes: [`docs/PAGINAS-Y-MENU.md`](docs/PAGINAS-Y-MENU.md).

**Qué revisa antes de llamar a SUSHI:** campos obligatorios, nombres y URL mal escritos, perfiles que no existen (con sugerencia), cardinalidades más laxas que las del padre, códigos fuera del ValueSet que exige CL Core, rutas que no existen en el recurso, fechas y cantidades mal escritas, ejemplos que contradicen su perfil e ids duplicados. Cada mensaje dice qué pasa y cómo arreglarlo.

### Otros comandos

```
python cl_ig.py importar paquete.tgz --salida mi-libro.xlsx     # de un paquete FHIR a un libro de Excel
python cl_ig.py estructura Patient --ruta telecom               # explora los elementos de un recurso o perfil
python cl_ig.py importar-codigos libro.xlsx lista.csv --codesystem CSMiLista --titulo "Mi lista"
```

## Ejemplos

La carpeta [`examples/`](examples/) tiene libros listos para abrir, cada uno con su propio README. Empieza por [`examples/README.md`](examples/README.md), que dice cuál mirar según lo que quieras hacer.

---

## ¿Qué se probó?

**Ida y vuelta con paquetes públicos reales.** Se importa el paquete a un libro, se genera el FSH, se compila con SUSHI y se comparan los valores efectivos de cada definición (cardinalidad, Must Support, bindings, tipos, fijos, slicing, invariantes) más las URL, contra el original:

| Paquete | Definiciones estructurales | Otros recursos | Diferencias |
|---|---|---|---|
| CL Core 1.9.3 | 29 de 29 | 45 (terminología, capacidades, búsquedas, mapas, operaciones) | 0 |
| NID de MINSAL 0.4.9 | 23 de 23 | — | 4 menores, en [`docs/LIBRO.md`](docs/LIBRO.md) |

«Sin diferencias» significa valores efectivos iguales, no JSON idéntico: los textos explicativos no se comparan ni se copian. Se reproduce con `scripts/prueba_ida_y_vuelta.py`.

**Publicación completa.** CL Core 1.9.3 importado a un libro (con sus 20 ejemplos) y construido desde él pasó SUSHI y el IG Publisher con **0 errores y sin ninguna llamada a un modelo** (octubre de 2026, 18,8 min). Es una guía **importada**, no escrita desde cero, y sus descripciones son las neutras del importador, no el texto original.

Hay 460 pruebas automáticas; cada brecha que apareció al replicar un paquete real se cerró con su prueba.

## Límites

- Solo FHIR R4 y CL Core 1.9.3.
- No cubre modelos lógicos ni StructureMap. Los Bundles de tipo documento se escriben como ejemplos, sin revisión propia.
- Al importar un paquete se traen las reglas y sus ejemplos, pero **no las páginas ni los textos explicativos**. Los recursos contenidos dentro de un ejemplo no se importan y se avisa.
- No se verifica el significado clínico de ningún código (por ejemplo LOINC): lo revisa una persona.
- Excel es cómodo para definir y revisar, pero no para todo: reglas muy particulares pueden requerir editar el FSH generado.
- La validación con Docker está probada en Windows (cmd) y en Linux/WSL2; macOS no se probó.
- Aún no se probó con usuarios ajenos al desarrollo.

---

## ¿Y la inteligencia artificial?

El camino por Excel **no usa IA**. Existe un segundo camino, opcional y experimental, que parte de una especificación en texto (por ejemplo «registrar presión arterial: sistólica y diastólica, en mmHg») y usa un modelo de lenguaje para convertirla en una ficha; el FSH lo escribe un generador determinista y las herramientas oficiales validan. Hoy cubre **solo observaciones de signos vitales**.

```
python cl_ig.py generar examples/demo/spec.json                    # desde una ficha, sin modelo
python cl_ig.py generar examples/casos/peso-talla/spec.md --local  # desde texto, con un modelo local (gratis)
python cl_ig.py reparar examples/demo/gold --local                 # reparar una guía que no valida
```

Fue el planteamiento original del proyecto. Las mediciones mostraron que un modelo local pequeño no escribe FSH de forma fiable por sí solo, y por eso el diseño pasó a un núcleo determinista donde el modelo es opcional. Cifras y detalles en [`docs/EXPERIMENTOS.md`](docs/EXPERIMENTOS.md) y [`docs/DECISIONES.md`](docs/DECISIONES.md); las muestras son pequeñas, así que son señales, no garantías.

Backends (`LLM_BACKEND`): `mock` (por defecto, respuestas simuladas), `local` (modelo en tu equipo con [Ollama](https://ollama.com)) y `anthropic` (de pago, opcional, con tu propia clave en `.env`, que nunca se sube al repositorio).

---

## Documentación

| Documento | Para qué |
|---|---|
| [`docs/kit/PRIMERA-GUIA.md`](docs/kit/PRIMERA-GUIA.md) | Tu primera guía, paso a paso |
| [`docs/LIBRO.md`](docs/LIBRO.md) | Referencia de cada hoja del libro |
| [`docs/PAGINAS-Y-MENU.md`](docs/PAGINAS-Y-MENU.md) | Texto, menú, imágenes y páginas generadas |
| [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) | Cómo está construido |
| [`docs/DECISIONES.md`](docs/DECISIONES.md) | Por qué se decidió así |
| [`docs/EXPERIMENTOS.md`](docs/EXPERIMENTOS.md) | Mediciones del camino con modelo |
| [`docs/LICENCIAS.md`](docs/LICENCIAS.md) | Licencias y procedencia |

## Estructura del repositorio

```
cl_ig.py     comando único (plantilla, revisar, construir, importar, estructura, generar, reparar, diagnostico)
libro/       camino por Excel: plantilla, lector, verificador, generador de FSH, importador de paquetes
agents/      analista, reglas deterministas, reparador, bucle de validación, informe
generator/   generador determinista de FSH para signos vitales
validator/   ejecución de SUSHI e IG Publisher en Docker y lectura de sus errores
llm/         cliente de modelos (opcional)
scripts/     prueba de ida y vuelta, mediciones, extracción del catálogo
examples/    libros de ejemplo y casos de medición
docs/        documentación
docker/      imagen de Docker con SUSHI, IG Publisher y Jekyll
prompts/     instrucciones del camino opcional con modelo de lenguaje
templates/   plantilla base de la guía (ig-base)
tests/       pruebas automáticas
```

Versiones fijadas: FHIR **R4 (4.0.1)** · CL Core **1.9.3** · SUSHI 3.20.1 · IG Publisher 2.3.4.

## Licencia y avisos de terceros

[Apache License 2.0](LICENSE). Cubre el código y la documentación de este repositorio. No cubre CL Core ni otros componentes de terceros, que se referencian y conservan sus propias licencias (ver [`docs/LICENCIAS.md`](docs/LICENCIAS.md)).

- Este repositorio **no incluye** CL Core, el IG Publisher ni SUSHI: los referencia por nombre y versión.
- Los ejemplos usan datos sintéticos propios. El ejemplo de códigos territoriales (`examples/datos-territoriales-chile`) parte de la tabla oficial del Código Único Territorial de la administración pública chilena, actualizada a mano; revisa los nombres contra la fuente vigente antes de publicar una guía.
- Este material contiene contenido de LOINC. LOINC es © Regenstrief Institute, Inc. y el LOINC Committee, está disponible sin costo bajo su licencia (<https://loinc.org/license>) y es una marca registrada de Regenstrief Institute en Estados Unidos.
- HL7® y FHIR® son marcas registradas de HL7 International. Este proyecto es independiente y no está afiliado ni respaldado por HL7 International ni por HL7 Chile.
