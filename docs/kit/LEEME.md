# cl-ig-kit: de un Excel a una guía de implementación FHIR (CL Core 1.9.3)

Esta carpeta es la versión liviana de [cl-core-ig-agents](https://github.com/) para **probar la herramienta**: sin pruebas internas, sin mediciones de desarrollo, solo lo necesario para crear una guía propia.

Qué hace: tú completas un libro de Excel (perfiles, extensiones, terminología, ejemplos…); la herramienta lo **revisa en español simple**, escribe el **FSH de forma determinista** (sin modelo de lenguaje: el mismo libro da siempre el mismo resultado) y construye la guía con **SUSHI** y el **IG Publisher**. Una persona revisa siempre el resultado. Es un borrador, no una guía oficial.

## Dónde escribir los comandos

Todos los comandos son `python cl_ig.py ...` y no necesitan `make`, así que sirven en el **símbolo del sistema (cmd)** o PowerShell de Windows, en la terminal de Ubuntu (WSL2), en Linux y en macOS. En Windows, usa `python` (en Ubuntu puede ser `python3`).

- Necesitas Python 3.11 o superior (en Windows, desde python.org, marcando «Add Python to PATH») y `pip install openpyxl pyyaml`.
- Para validar con Docker necesitas Docker Desktop **abierto**. En cmd, abre la terminal dentro de la carpeta del kit (`cd C:\ruta\al\kit`).
- Si algo se ve con símbolos raros en cmd, no es un error: la consola de Windows no muestra algunos caracteres y los reemplaza.
- La validación con Docker se probó en Linux y se está probando en Windows nativo. Si en cmd falla, prueba lo mismo desde Ubuntu (WSL2) y cuéntanos qué pasó.

## Dónde está la plantilla para tu propia guía

- **`plantilla-vacia.xlsx`** (en esta carpeta): el libro en blanco. Cópialo como `mi-guia.xlsx` y empieza por la hoja «Guía».
- O créalo con el comando: `python cl_ig.py plantilla mi-guia.xlsx`. Si ya instalaste CL Core (sección siguiente), este comando agrega la lista desplegable de perfiles padre de CL Core, que la copia incluida no trae.
- Para ver cómo se llena, mira `examples/libro-demo/libro-demo.xlsx` (completo) o `PRIMERA-GUIA.md` (paso a paso).

## En 10 minutos, sin Docker

Necesitas Python ≥ 3.11 y `pip install openpyxl pyyaml`.

```bash
python cl_ig.py plantilla mi-guia.xlsx --ejemplo    # un libro de demostración completo (datos sintéticos)
python cl_ig.py revisar mi-guia.xlsx                # dice qué está bien y qué no, y cómo arreglarlo
python cl_ig.py construir mi-guia.xlsx --sin-docker # escribe la guía en runs/ (FSH, configuración, páginas)
```

Abre el libro en Excel, rompe algo a propósito (por ejemplo, borra un código de un ValueSet que usa un ejemplo) y vuelve a correr `revisar`: ahí se ve el valor de la revisión.

## Con CL Core instalado (recomendado)

**Para qué sirve.** CL Core es la base sobre la que se construyen las guías chilenas. Si la herramienta tiene el paquete, la plantilla ofrece listas desplegables (perfiles padre de CL Core, elementos, códigos) y `revisar` avisa cuando algo que escribiste no existe en CL Core. Sin el paquete todo funciona, pero sin esas listas ni esas comprobaciones.

**Qué necesitas.** El archivo `package.tgz` de `hl7.fhir.cl.clcore` versión 1.9.3. No viene en el kit (ver `docs/LICENCIAS.md`: es de HL7 Chile y se referencia, no se redistribuye). Puedes conseguirlo de cualquiera de estas formas:

1. **Del sitio publicado de CL Core:** `https://hl7chile.cl/fhir/ig/clcore/1.9.3/`, en la sección de descargas (el archivo se llama `package.tgz`).
2. **Del registro de paquetes FHIR:** `https://packages.fhir.org/hl7.fhir.cl.clcore/1.9.3` descarga el paquete directamente.
3. **Si ya lo tienes** porque usaste SUSHI o el IG Publisher, suele estar descomprimido en `~/.fhir/packages/hl7.fhir.cl.clcore#1.9.3/package`. En ese caso usa esa carpeta en lugar del `.tgz`.

**Qué hacer con él**

```bash
# 1) deja el archivo en esta ruta (crea las carpetas si no existen):
#    reference/clcore-1.9.3/site/package.tgz
# 2) construye el catálogo (lee el paquete y deja build/catalog/catalog.json):
python cl_ig.py catalogo
# 3) comprueba que todo esté listo:
python cl_ig.py diagnostico
# 4) crea tu libro de nuevo: ahora trae las listas de CL Core
python cl_ig.py plantilla mi-guia.xlsx --forzar
```

(Si usas la carpeta del caso 3: `python cl_ig.py catalogo --package <esa carpeta>`.) El catálogo se queda en tu computador; no se sube ni se comparte.

## Ver una guía real como Excel

```bash
python cl_ig.py importar reference/clcore-1.9.3/site/package.tgz --salida clcore.xlsx
```

Convierte el paquete en un libro: perfiles, extensiones, slices, terminología, capacidades. Sirve para leer una guía sin abrir JSON, y es la prueba de que el libro puede expresar una guía nacional completa (CL Core 1.9.3: 29 de 29 definiciones y 45 recursos más, sin diferencias).

Los textos explicativos del original no se copian (en su lugar queda «importado de un paquete»). Si quieres conservarlos, agrega `--con-textos`. Si vas a construir la guía importada, `construir` la valida con el Publisher; CL Core completo tarda unos 25 minutos.

## Construir y validar de verdad (SUSHI + IG Publisher)

Necesita Docker Desktop abierto, y el paquete de CL Core en `reference/clcore-1.9.3/site/package.tgz` (ver arriba). Todo se escribe en la **misma terminal**, dentro de la carpeta del kit:

```bash
python cl_ig.py imagen              # una sola vez: crea la imagen con SUSHI, IG Publisher y Jekyll (descarga cosas; puede tardar varios minutos)
python cl_ig.py diagnostico         # todo debería salir en [OK], incluida la imagen de Docker
python cl_ig.py construir mi-guia.xlsx
```

`construir` primero revisa el libro (si hay errores, se detiene y los explica), luego escribe el FSH y por último valida **una sola vez** con SUSHI y el IG Publisher dentro de Docker. No llama a ningún modelo: si el Publisher encuentra problemas, se corrigen en el Excel y se vuelve a ejecutar. La primera vez tarda unos 8 a 10 minutos porque descarga terminologías; las siguientes son más rápidas, y una guía grande como CL Core completo tarda unos 25 (el límite es 60; se cambia con `--timeout-min`). Al terminar deja la guía publicada en `runs/<fecha>-<id>/output/index.html` (ábrela con el navegador), el reporte técnico del Publisher en `output/qa.html` y un `informe.md` en `runs/`, que dice en español si pasó, qué problemas quedaron (agrupados si se repiten) y qué debe revisar una persona.

## Texto, menú e imágenes de la guía

Además de los artefactos, el libro controla cómo se ve la guía:

- **Documentación**: una fila por página. Para una página larga, escribe `@paginas/nombre.md` en la celda de texto y guarda el texto en una carpeta `paginas/` junto al libro. La columna avanzada «Página padre» pone una página dentro de otra (se ve en la tabla de contenido; enlázala desde la padre si quieres que el lector llegue). No repitas el título de la página al comienzo del texto: el Publisher ya lo escribe.
- **Menú** (opcional): el menú superior exacto. Admite páginas, enlaces externos, declaraciones de capacidades y desplegables. Sin esta hoja, el menú es Inicio, Requisitos y Artefactos.
- **Páginas generadas**: con el destino `must-support` en el menú, la herramienta escribe la página Must Support con todo lo que tus perfiles marcan; con `cambios`, arma el Historial de cambios desde la hoja **Cambios**.
- **Imágenes**: los archivos de una carpeta `imagenes/` junto al libro se copian a la guía; en una página se usan como `![texto](logo.png)`.

Ejemplo completo y listo para probar: `examples/libro-con-paginas/`. Detalle en `docs/LIBRO.md`.

## Tu primera guía

Sigue `PRIMERA-GUIA.md`: unos 30 minutos para un perfil propio con un ejemplo.

## Qué esperar (y qué no)

- Cubre perfiles, extensiones, slicing, invariantes, terminología, ejemplos, CapabilityStatement, SearchParameter, ConceptMap, OperationDefinition, Questionnaire, Bundles de mensaje, y el texto de la guía (páginas, menú, Must Support e historial de cambios). Detalle en `docs/LIBRO.md`.
- No cubre modelos lógicos, StructureMap ni Bundles de documento (Composition), y al importar no trae las páginas de otras guías (los ejemplos sí). Sin logos en el encabezado ni tema propio.
- Solo FHIR R4 y CL Core 1.9.3.
- Si algo del libro no se puede expresar, o un mensaje es confuso, **eso es justo lo que queremos saber**.

Licencia: Apache-2.0. CL Core y las herramientas de terceros conservan las suyas.
