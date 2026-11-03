# Tu primera guía en 30 minutos

Meta: un perfil propio sobre CL Core, con una extensión, una lista de códigos y un ejemplo, y que `revisar` diga que todo está en orden. Empieza copiando `plantilla-vacia.xlsx` (en la raíz del kit) como `mi-guia.xlsx`, o créalo con `python cl_ig.py plantilla mi-guia.xlsx` (con CL Core instalado trae además la lista de perfiles padre). Pasa el cursor sobre cualquier encabezado para ver su ayuda; el color de la fila 3 indica si la columna es obligatoria (rojo), recomendada (amarillo) u opcional (gris).

1. **Guía.** Id (`mi-guia`), título, URL canónica (`https://ejemplo.cl/fhir/ig/mi-guia`), versión, publicador. Marca «Usa CL Core» = Sí.
2. **Perfiles.** Una fila: nombre `PacienteMiServicio`, recurso `Patient`, perfil padre `CorePacienteCl`, título y descripción.
3. **Elementos.** Solo lo que *cambia* respecto del padre, una fila por regla. Por ejemplo `birthDate` mín 1, Must Support = Sí. Para explorar los elementos disponibles: `python cl_ig.py estructura CorePacienteCl --profundidad 2`.
4. **Terminología.** En *CodeSystems* y *Conceptos* define una lista corta (por ejemplo `CSNivelRiesgo`: bajo, medio, alto). En *ValueSets* e *Inclusiones* crea `VSNivelRiesgo` que incluya ese sistema.
5. **Extensión.** En *Extensiones*: `NivelRiesgo`, contexto `Patient`, tipo `CodeableConcept`, ValueSet `VSNivelRiesgo`, fuerza `required`. Luego, en *Elementos*, agrega la fila de `PacienteMiServicio` con la ruta que muestra la columna gris (`extension[nivelRiesgo]`) y cardinalidad 0..1: eso hace que el perfil **admita** la extensión.
6. **Ejemplo.** En *Instancias*: `EjemploPaciente1`, perfil `PacienteMiServicio`. En *Valores*, sus datos (todo sintético).
7. **Revisar.** `python cl_ig.py revisar mi-guia.xlsx`. Cada mensaje dice qué pasa y cómo arreglarlo; un `error` impide construir.
8. **Construir.** `python cl_ig.py construir mi-guia.xlsx` (con Docker abierto, unos 6 a 10 minutos) o `--sin-docker` para solo ver el FSH en `runs/`. Al terminar abre `runs/<fecha>-mi-guia/output/index.html` en el navegador; `informe.md` dice si pasó y qué revisar.
9. **Texto y menú (opcional).** En *Documentación* agrega una página `objetivos` con su título y texto (o `@paginas/objetivos.md`). Crea la hoja *Menú* con filas `Inicio → inicio`, `Objetivos → objetivos`, `Must Support → must-support`, `Artefactos → artefactos`. Vuelve a construir: aparece el menú y la página Must Support se escribe sola con lo que marcaste en el paso 3. Un ejemplo completo está en `examples/libro-con-paginas/`.

## Si te trabas

- Un mensaje que no se entiende, una regla que no sabes cómo escribir o algo de tu guía que el libro no puede expresar: anótalo tal cual. Es lo más útil que puedes devolver.
- Para ver cómo se hace algo ya resuelto: `examples/ejercicio-1-presion-arterial/README.md` explica, hoja por hoja, qué FSH produce cada fila.
