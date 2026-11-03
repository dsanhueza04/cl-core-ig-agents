# Del Excel a la guía de implementación

Para quien quiere hacer una guía FHIR **sin escribir FSH**. Se rellena un libro de Excel y la herramienta revisa la coherencia, escribe la guía y la valida con SUSHI y el IG Publisher. Una persona debe revisar siempre el resultado.

```
python cl_ig.py plantilla mi-guia.xlsx              # libro vacío (con --ejemplo, uno completo de demostración)
python cl_ig.py revisar mi-guia.xlsx                # explica los problemas en lenguaje simple
python cl_ig.py construir mi-guia.xlsx              # revisa, escribe la guía y la valida
python cl_ig.py construir mi-guia.xlsx --sin-docker # solo escribe la guía
```

Necesita `pip install openpyxl`. El libro de demostración está en `examples/libro-demo/libro-demo.xlsx` (datos 100 % sintéticos).

## Las hojas

Cada hoja marca en la fila 3 si la columna es **Obligatorio** (rojo), **Recomendado** (amarillo) u **Opcional** (gris). Pasa el cursor por un encabezado para ver su ayuda. Las hojas que no necesites pueden quedar vacías.

| Hoja | Qué defines | Se convierte en |
|---|---|---|
| Guía | Identificador, título, URL canónica, versión, publicador, dependencias | `sushi-config.yaml` |
| Perfiles | Un perfil por fila: recurso base, perfil padre, título, descripción | `Profile` |
| Elementos | Reglas por elemento: mín/máx, Must Support, tipo, ValueSet, valor fijo | reglas del perfil |
| Extensiones | Datos que el recurso no trae: una fila por extensión; si es compleja, una fila por parte (columna «Es parte de») | `Extension` |
| ValorExtensiones | Reglas sobre el valor de una extensión (qué campos son obligatorios dentro de un Identifier, qué ValueSet usa un CodeableConcept) | reglas `valueX.campo` de la extensión |
| Capacidades / RecursosCapacidad / OperacionesCapacidad / BusquedasCapacidad | Qué ofrece un servidor (o espera de un cliente): recursos, perfiles, operaciones, búsquedas y la expectativa (SHALL, SHOULD, MAY) de cada uno | un `CapabilityStatement` |
| Slices | Un elemento que se repite, dividido en variantes (teléfono y correo dentro de `telecom`) | reglas `contains` del perfil |
| Instancias | Un ejemplo por fila: nombre, perfil, descripción | `Instance` |
| Valores | Los datos de cada ejemplo (texto, código, número, cantidad, fecha, referencia...) | reglas del ejemplo |
| CodeSystems y Conceptos | Códigos propios con su significado | `CodeSystem` |
| ValueSets e Inclusiones | Listas de códigos permitidos | `ValueSet` |
| Documentación | Páginas en Markdown (si falta «inicio», se genera un borrador). El texto puede venir de un archivo (`@paginas/objetivos.md`) y una página puede ir dentro de otra («Página padre») | páginas de la guía |
| Menú | Opcional. El menú superior exacto: páginas, enlaces externos, declaraciones de capacidades y desplegables | `menu` de la guía |
| Cambios | Una fila por versión | la página «Historial de cambios» |

## Listas desplegables

- **Recurso base:** los 146 recursos de FHIR R4.
- **Perfil padre:** los perfiles de CL Core del recurso elegido. Se puede escribir cualquier otro (un perfil de esta hoja o una URL).
- **Elemento (ruta):** los elementos del perfil padre si es de CL Core (con sus slices y extensiones, por ejemplo `name[NombreOficial]`), o los del recurso base de FHIR R4 (con los hijos de sus tipos de dato: `name.family`, `valueQuantity.unit`).
  Si el padre es un perfil propio, la lista sigue hasta dos saltos hasta llegar a uno de CL Core.
- **Valores → Elemento (ruta):** la misma lista, según el perfil del ejemplo (la hoja Instancias dice con qué perfil se hace cada ejemplo). Ofrece todos los elementos del perfil, no solo los de la hoja Elementos. Elegir `name.family` sin índice vale como `name[0].family`; si quieres otra posición, escribe el índice (`name[1].family`).
- **Valores → Tipo de dato:** si lo dejas vacío se deduce del elemento elegido (`birthDate` → fecha, `valueQuantity` → cantidad...). La columna gris **Tipo sugerido** lo muestra en pantalla. Los elementos contenedor (`name`, `value[x]` sin elegir) no tienen tipo deducible: elige un hijo o escribe el tipo.
- Las listas son una ayuda: se puede escribir otro valor. `revisar` comprueba después que la ruta exista.
- Las columnas avanzadas (Solo tipo, valor fijo, perfil del tipo, destinos, comentario, justificación) están agrupadas y cerradas; el botón **+** sobre la tabla las abre.

Las listas se generan con `python cl_ig.py plantilla` a partir de `build/catalog` (`python cl_ig.py catalogo`) y de `libro/datos/elementos_r4.json`
(`python scripts/extract_elementos.py --package <hl7.fhir.r4.core#4.0.1>`). Funcionan en Excel de escritorio y en LibreOffice; no en Google Sheets.

## Qué revisa antes de llamar a SUSHI

Obligatorios que faltan; nombres, ids y URL mal formados; recursos con errata (con sugerencia); perfil padre inexistente o de otro recurso; ciclos de herencia; cardinalidad mínima mayor que máxima o **más laxa que la del padre**; rutas con el nombre del recurso; ValueSets, CodeSystems y ejemplos referenciados que no existen; códigos que no existen en el CodeSystem (del libro o de CL Core); un mismo código con dos significados en un sistema; fechas con formato día/mes/año o imposibles; coma decimal; cantidades sin unidad; rutas que no existen en el recurso (con sugerencia); cardinalidad más laxa que la del recurso base; ejemplos que contradicen un valor fijo del perfil o que no traen elementos exigidos por el perfil o por FHIR.

Cada mensaje dice **qué pasa y cómo arreglarlo**. Un `error` impide construir; un `aviso` conviene mirarlo; una `sugerencia` es opcional.

## Alcance de esta versión

Incluye: perfiles (cardinalidad, Must Support, tipo, binding, valor fijo, slicing, extensiones, invariantes FHIRPath); ejemplos; CodeSystems y ValueSets propios con filtros; CapabilityStatement; SearchParameter, ConceptMap, OperationDefinition y Questionnaire; Bundles de mensaje; páginas.

Todavía no: modelos lógicos, StructureMap, mapeo general a Observation, Bundles de tipo documento con su Composition (se escriben como ejemplos, sin revisión propia), invariantes dentro de las partes de una extensión, ni importar las páginas de otra guía ni los recursos contenidos de un ejemplo. Un perfil no puede agregar elementos nuevos: lo nuevo se define como extensión (hoja Extensiones).

## ValueSets: filtros, exclusiones y otros ValueSets (hoja Inclusiones)

Cada fila es una regla. Sin «Código», incluye todo el sistema. Con **Filtro** incluyes una rama: `descendent-of` + `404684003` en SNOMED trae todos los descendientes de ese código (`is-a` incluye también el propio código). **Incluir o excluir** = `excluir` saca códigos o ramas. **Incluir otro ValueSet** reutiliza uno de tu libro, de CL Core o una URL. Un filtro se aplica sobre la propiedad `concept`; `regex`, `in` y `not-in` llevan texto.

## Página «Requisitos de esta guía»

`construir` agrega automáticamente, justo después del Inicio, una página con la tabla **Differential** de cada perfil: solo lo que *tu guía* agrega o cambia, más una frase que dice de dónde parte el perfil (CL Core 1.9.3, otro perfil de la guía o FHIR base) y qué se hereda. Así el lector ve primero tus requisitos, y la pestaña *Key Elements* queda como complemento. Si creas en Documentación una página con id `requisitos`, se usa la tuya.

## Textos, perfil del tipo y destinos de referencia (hoja Elementos)

- **Resumen / Definición / Comentario**: explican el elemento en la guía publicada (`short`, `definition`, `comment` en FSH). Una fila puede tener solo textos, sin ninguna regla. También sirven en las filas que admiten una extensión.
- **Debe seguir el perfil**: el dato debe cumplir un perfil del tipo de dato, por ejemplo `address` → `cl-address`. Acepta un perfil de CL Core o una URL. Para definir tu propio perfil de un tipo de dato, crea en Perfiles una fila con «Recurso base» = `Address` (o `HumanName`, `Identifier`...) y úsalo aquí por su nombre. Un tipo de dato no puede tener ejemplos propios.
- **Puede apuntar a**: para referencias, los recursos o perfiles permitidos, separados por coma (`Practitioner, CorePrestadorCl`). Se escribe `only Reference(A or B)` en FSH. No se combina con «Solo tipo».

## Extensiones

Si la extensión ya existe en otro paquete (por ejemplo `http://hl7.org/fhir/StructureDefinition/geolocation`), crea una fila solo con el nombre y la URL en «Ya existe en (URL)»: se usa pero no se vuelve a definir.

1. En **Extensiones** crea una fila: nombre (`AniosEscolaridad`), «Se usa en» (`Patient`) y «Tipo del valor» (`integer`). Para un código con lista cerrada usa `code`, `Coding` o `CodeableConcept` más un ValueSet.
2. La columna gris **Ruta para usarla** te dice cómo escribirla: `extension[aniosEscolaridad]`.
3. En **Elementos** agrega una fila del perfil con esa ruta y su cardinalidad (`0..1`, Must Support). Eso hace que el perfil admita la extensión.
4. En **Valores** escribe el dato con la misma ruta: la herramienta agrega el `valueInteger` y deduce el tipo de dato.

**Extensión compleja** (varios datos juntos): una fila para la extensión sin tipo, y una fila por parte con «Es parte de» = la extensión, su tipo y Mín/Máx. Las rutas son `extension[contactoPreferido].extension[medio]`. Si el nombre de la parte debe llevar mayúscula inicial (p. ej. `Contactado`), escríbelo exacto en «Nombre exacto de la parte». Solo se admite un nivel de partes.

Las extensiones ya definidas por CL Core aparecen en la lista de rutas del perfil (por ejemplo `extension[nacionalidad]`) y se usan igual, pero su valor se escribe completo (`extension[nacionalidad].valueCodeableConcept`).

## Reglas sobre el valor de una extensión (hoja ValorExtensiones)

Una extensión cuyo valor es un tipo con campos internos (Identifier, CodeableConcept, Coding, Quantity, Period, Address…) puede exigir cosas *dentro* de ese valor. Una fila por campo:

- **Extensión**: nombre de una extensión propia (o de una parte de extensión compleja).
- **Campo dentro del valor**: ruta relativa, por ejemplo `system`, `type.coding.code`.
- Cardinalidad, Must Support, ValueSet con fuerza y valor fijo, igual que en Elementos.

Una extensión compleja no guarda valor propio: pon las reglas en cada una de sus partes. Un campo no puede ser más permisivo que su tipo (no se puede poner máximo 5 donde el tipo admite 1). Genera, por ejemplo, `* extension[tutId].valueIdentifier.system 1..`. Con `[x]` en el campo se regla el valor mismo (su cardinalidad o Must Support). En la hoja Extensiones, la columna **Must Support** marca una parte como obligatoria de soportar.

## Importar códigos desde un CSV

Para listas largas (comunas, países, un catálogo local) no hace falta escribir fila por fila:

```
python cl_ig.py importar-codigos mi-libro.xlsx comunas.csv --codesystem CSComunas
```

Reconoce columnas llamadas `codigo`/`code` y `texto`/`display`/`glosa` (separador `,` `;` o tabulador); si se llaman distinto usa `--col-codigo`, `--col-texto`, `--col-definicion`. Crea el CodeSystem si no existe, no duplica códigos que ya están y, si el texto del CSV difiere del del libro, lo avisa y conserva el del libro. **El libro original no se modifica**: escribe `mi-libro-importado.xlsx` (usa `--salida` para elegir el nombre). Usa solo listas que puedas publicar.

## Declaración de capacidades (CapabilityStatement)

Cuatro hojas, de lo general a lo particular:

- **Capacidades**: una fila por declaración (nombre, rol `server` o `client`, formatos, documentación general; en columnas avanzadas, formatos de parche y derechos de autor).
- **RecursosCapacidad**: una fila por recurso. Perfil que se espera, expectativa del recurso y del perfil, y en columnas avanzadas: referencias admitidas (`literal`, `logical`…), `searchInclude`, `searchRevInclude` y documentación. En los campos de lista se puede agregar la expectativa de cada elemento al final: `Observation:subject SHALL, Provenance:target MAY`. Las columnas «Operaciones» y «Búsquedas» sirven de resumen rápido (`read, search-type` / `identifier:token`).
- **OperacionesCapacidad**: una fila por operación con su expectativa. Con «Recurso» vacío son las operaciones de todo el servidor (`transaction`, `batch`, `search-system`, `history-system`).
- **BusquedasCapacidad**: una fila por parámetro de búsqueda, con tipo, expectativa, URL de su definición y la explicación de cómo usarlo.

Lo que escribes en las hojas de detalle reemplaza al resumen. Genera `input/fsh/capacidades.fsh` con un `CapabilityStatement` (`kind = #requirements`, FHIR 4.0.1); la expectativa se escribe con la extensión estándar `capabilitystatement-expectation`. Los textos de varias líneas conservan sus párrafos. El verificador avisa si declaras búsquedas sin `search-type`, si repites un recurso o una operación, si una operación de servidor se asigna a un recurso o al revés, o si el perfil es de otro recurso. Es lo que *esperas* del sistema; no prueba que un servidor real lo cumpla.

### Importar una declaración existente

`libro.importar.capacidad_desde_json(cs, "NombreNuevo")` convierte un `CapabilityStatement` en JSON en filas de estas cuatro hojas, sin copiar sus textos explicativos. La prueba `examples/prueba-reconstruccion/comparar_capacidades.py` lo usa con las dos declaraciones de CL Core 1.9.3 y comprueba regla por regla que el FSH generado dice lo mismo que el original.

## Slices

Un slice separa usos distintos de un elemento que se repite. En **Slices**, una fila por slice:

- **Elemento que se divide**: `telecom`; **Nombre del slice**: `telefono`; Mín/Máx/Must Support del slice.
- En la **primera fila del elemento**: «Se distingue por» (`value`, `pattern`, `type` o `exists`) y «Campo que lo distingue» (`system`; `$this` si es el elemento mismo).
- **Valor que lo distingue** (`phone`) fija ese campo en el slice.
- Si el padre ya divide ese elemento (por ejemplo `identifier` en `CorePrestadorCl`), solo agrega slices y deja «Se distingue por» vacío. Para restringir un slice que ya existe, usa Elementos con la ruta `identifier[run]`.
- Las reglas finas de un slice se escriben en **Elementos** con su ruta: `telecom[telefono].value` 1..1.
- En **Valores** usa `telecom[telefono].value`.

El verificador avisa si falta el discriminador, si el slice ya existe en el padre, si el ejemplo usa un slice o una extensión que su perfil no define, o si un slice obligatorio no aparece en un ejemplo. Las rutas de slices y extensiones propias del libro no están en las listas desplegables de Excel (se escriben a mano); el tipo de dato sí se deduce al revisar.

## Parámetros de búsqueda, mapas de conceptos y operaciones propias

Tres hojas para recursos que una guía define aparte de los perfiles:

- **ParametrosBusqueda** (SearchParameter): una fila por parámetro. Nombre, código de búsqueda (`segundo-apellido`), recursos, tipo, expresión FHIRPath, modificadores y comparadores. Se declara en el servidor con la hoja BusquedasCapacidad (campo «Definición»).
- **MapasConceptos** y **ReglasMapa** (ConceptMap): el mapa dice el ValueSet de origen y destino; cada fila de ReglasMapa une un código de origen con uno de destino y su equivalencia (`equivalent`, `wider`, `unmatched`…). Se agrupan solos por par de sistemas; la versión del sistema es opcional.
- **Operaciones** y **ParametrosOperacion** (OperationDefinition): el código de la operación (sin `$`), los recursos, dónde se invoca (sistema, tipo, instancia) y una fila por parámetro de entrada o salida, con tipo y perfil exigido. Una operación se declara en una CapabilityStatement con una fila en OperacionesCapacidad, rellenando «Operación propia».
- **Cuestionarios** y **PreguntasCuestionario** (Questionnaire): una fila por cuestionario y una por pregunta. Los grupos se anidan con «Dentro de» (el id del grupo). Las preguntas de tipo `choice` toman su lista de un ValueSet. Una condición simple («mostrar solo si…») apunta a otra pregunta; si esa es de tipo `choice`, la respuesta esperada se escribe `SISTEMA#codigo`. Las respuestas a un cuestionario (QuestionnaireResponse) se escriben como cualquier otro ejemplo, en Instancias y Valores.
- **Invariantes**: reglas que no se expresan con cardinalidad ni valores fijos (por ejemplo «si hay A, debe haber B»). Cada fila aplica una regla (clave, gravedad, texto, expresión FHIRPath) a un perfil o a una extensión propia, y a un elemento o al recurso completo. La misma clave en varias filas define la regla una vez y la aplica en varios lugares.
- **Id (final de la URL)**: columna avanzada de Perfiles, Extensiones, CodeSystems, ValueSets, Capacidades, ParametrosBusqueda, MapasConceptos, Operaciones y Cuestionarios. Si la dejas vacía, la URL termina en el nombre en minúsculas con guiones (`MiPerfil` → `miperfil`). Complétala cuando la URL ya existe o la usan otras guías: las guías chilenas suelen terminar la URL igual que el nombre (`CSTipoIdentificador`). El importador de paquetes la rellena solo.
- **Mensajes**: un perfil de Bundle con `type` fijo en `message` se escribe con las hojas de siempre (Elementos y Slices): una entrada para el MessageHeader (obligatoria y máximo 1) y una por cada recurso. El verificador avisa si falta la cabecera; si no va primera en la lista es solo una sugerencia, salvo que marques «Slices en orden» = Sí (en el mensaje real el MessageHeader siempre va primero). En un ejemplo, el tipo de dato «recurso incluido» pone otro ejemplo dentro de la entrada (`entry[cabecera].resource`).

La hoja RecursosCapacidad admite varios perfiles por recurso (`PerfilA SHALL, PerfilB SHALL`).

## Terminología fina

- **Distingue mayúsculas** (CodeSystems): `No` genera `caseSensitive = false`.
- **Propiedad del filtro** (Inclusiones): `code` para filtrar por el texto del código con `regex` (por ejemplo códigos de país de 3 dígitos).
- **Texto del código** (Inclusiones): el display que acompaña a un código incluido.

## Slices de elementos de tipo variable

Un elemento como `Medication.ingredient.item[x]` se divide por tipo: en **Slices**, elemento `ingredient.item[x]`, slice `itemCodeableConcept`, «Se distingue por» `type` y campo `$this`. El tipo del slice se pone en Elementos con la ruta `ingredient.item[x][itemCodeableConcept]`.

El orden de los slices se fija en la primera fila del elemento con «Slices en orden» (Sí/No). Las rutas de sus reglas se escriben en Elementos, p. ej. `event[x][eventCoding]`.

**Must Support en la URL de una extensión**: en ValorExtensiones, fila con el campo `url` y Must Support = Sí (sirve para la extensión o para una de sus partes).

## Valores fijos de conceptos, valor exacto y perfiles en un tipo

- **Texto del código fijo**: con tipo «código con sistema», el texto (display) que acompaña al código; sirve para Coding y CodeableConcept (`* code = LOINC#8867-4 "Heart rate"`).
- **Valor exacto**: `Sí` genera `(exactly)` y el perfil fija el valor (fixed) en vez de solo exigir que lo contenga (pattern).
- **Debe seguir el perfil** admite varios perfiles separados por coma (`PerfilA, PerfilB`): el elemento debe cumplir alguno. En un Bundle, `entry[paciente].resource` con «Debe seguir el perfil» fija el perfil del recurso de esa entrada.
- «Se distingue por» admite también `profile` (por ejemplo, entradas de un Bundle separadas por el perfil de su recurso).

## Importar un paquete de otra guía

```
python cl_ig.py importar package.tgz --salida mi-libro.xlsx      # o una carpeta con los JSON
```

Lee un paquete FHIR (`.tgz` o la carpeta con los JSON) y lo convierte en un libro: perfiles, extensiones (con ValorExtensiones y partes), slices, invariantes, CodeSystems, ValueSets, CapabilityStatements, búsquedas, mapas y operaciones, incluidos los ids (final de la URL). Omite los textos explicativos salvo `--con-textos` (úsalo solo con paquetes tuyos). Lo que no sabe expresar se informa («No se pudo expresar en el libro»). Los ejemplos del paquete (`example/`) se importan a Instancias y Valores, con su id original (columna «Id del recurso»); las páginas no. Si los perfiles parten de CL Core, haz antes `python cl_ig.py catalogo` para que distinga «restringir un slice que ya existe» de «crear uno nuevo».

Para comprobar que el libro dice lo mismo que el original hay una prueba de ida y vuelta:

`python scripts/prueba_ida_y_vuelta.py CARPETA_JSON --sushi RUTA_A_SUSHI [--salida CARPETA]`

Importa, genera FSH, corre SUSHI y compara, perfil por perfil, los valores efectivos (cardinalidad, Must Support, binding, tipos, fijos, slicing, invariantes) y las URL. Compara además terminología, capacidades, búsquedas, mapas y operaciones. Resultados con paquetes públicos: **CL Core 1.9.3** 29 de 29 definiciones estructurales y 45 recursos más, sin diferencias; **NID de MINSAL 0.4.9** 23 de 23, con 4 diferencias menores documentadas (dos máximos de cardinalidad en un Bundle de búsqueda y el máximo de `address.line` en dos perfiles). «Sin diferencias» significa valores efectivos iguales, no JSON idéntico: los textos explicativos no se comparan. Para comparar contra perfiles padre externos, deja su paquete en `~/.fhir/packages` o usa `--dependencia CARPETA`.

## Cómo se prueba

`tests/test_libro.py` cubre plantilla, lector, cada regla del verificador y el FSH generado. La validación completa (SUSHI + Publisher) se hace en la máquina con Docker: `python cl_ig.py construir examples/libro-demo/libro-demo.xlsx`.


## Páginas, menú, imágenes y páginas generadas

- **Texto desde archivo.** En «Documentación», si el texto empieza con `@`, se lee un archivo `.md` de la carpeta `paginas/` que está junto al libro (`@paginas/objetivos.md`). Sirve para páginas largas: una celda de Excel admite como máximo 32.767 caracteres.
- **Páginas dentro de páginas.** La columna avanzada «Página padre» anida una página dentro de otra. El IG Publisher las muestra en la tabla de contenido, no dentro de la página padre: si quieres que el lector llegue desde la padre, enlázala en el texto (`[Objetivos](objetivos.html)`).
- **Títulos.** El IG Publisher ya escribe el título de cada página; no lo repitas con `#` al comienzo del texto.
- **Menú.** Sin hoja «Menú», el menú es Inicio, Requisitos y Artefactos. Con filas, es exactamente lo que escribas. «A dónde lleva» acepta: el id de una página, `artefactos`, `must-support`, `cambios`, el nombre de una declaración de capacidades (hoja Capacidades) o una dirección `https://`. Una fila sin destino es un desplegable; las demás filas la nombran en «Dentro del desplegable». Solo un nivel de desplegable.
- **Página Must Support generada.** Con `must-support` como destino de una fila del menú, `construir` escribe una página con todos los elementos, slices y partes de extensiones que el libro marca como Must Support, perfil por perfil. Usa la definición general de FHIR; si la comunidad quiere otra, escribe una página `must-support` propia en Documentación y reemplaza a la generada.
- **Historial de cambios.** Con `cambios` como destino, `construir` arma la página desde la hoja «Cambios».
- **Imágenes.** Los archivos `.png .jpg .gif .svg .webp` de la carpeta `imagenes/` junto al libro se copian a `input/images`; en una página se usan como `![texto](logo.png)`. Pendiente de comprobar con una construcción completa del IG Publisher.
- No incluido: logos en el encabezado de la guía, tema o CSS propios, páginas con plantilla propia.
