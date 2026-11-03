# Plan de 4 semanas (≈14 h por semana)

Caso de demostración propuesto: registro de **control de presión arterial / tamizaje de hipertensión** (10 a 15 campos, especificación propia y datos sintéticos). Reutiliza `cl-core-signos-vitales` y `CorePacienteCl` de CL Core y añade uno o dos perfiles propios, un ValueSet y ejemplos.

## Semana 1 — Cimientos

| Bloque | Horas | Entregable | Estado |
|---|---|---|---|
| Repo y licencias | 2 | Repo con estructura, README, `.gitignore`, `docs/LICENCIAS.md` | Hecho. Apache-2.0 elegida; falta verificar la licencia del IG Publisher |
| Contenedor de validación | 4 | `make build` y `make validate` funcionando | Hecho. SUSHI 3.20.1 + IG Publisher 2.3.4; validación en ≈6 min con caché caliente |
| IG mínimo hecho a mano | 4 | `examples/demo/gold`: 1 perfil sobre CL Core, 1 ejemplo, 1 página, **0 errores** | Hecho. 0 errores, 7 warnings, 7 avisos (corrida del 2026-10-01) |
| Parser de errores | 3 | `validator/parse_qa.py` + pruebas con errores provocados a propósito | Hecho. 25 pruebas con corridas reales; separa errores de contenido e infraestructura |
| Cliente LLM con métricas | 1 | `llm/client.py` con registro de tokens y costo | Hecho. Independiente del proveedor; modo simulado y local gratuitos; 16 pruebas |
| Catálogo por demanda y chequeo previo | 2 | `agents/catalog.py` + `validator/precheck.py`: contexto pequeño por consulta y detección sin modelo de URLs, códigos y displays inventados de CL Core | Hecho. 14 pruebas (incluye CL Core real); el IG de referencia pasa limpio |

**Criterio de éxito:** clonar, `make validate` y ver pasar el IG mínimo; un error inducido aparece como JSON estructurado.

## Semana 2 — Bucle de generación y reparación

- Agente de perfiles FSH (**hecho**: `agents/perfiles.py`, prompt ≈1.500 tokens, corrige referencias inventadas con el chequeo previo; falta probarlo con un modelo local real) y agente de ejemplos.
- Reparador con parches acotados y topes de iteración (**hecho** con modelo simulado: `agents/reparador.py`, `agents/loop.py`; rechaza parches que debilitan cardinalidades; detecta falta de progreso; reintenta la infraestructura sin llamar al modelo). Probado el 2026-10-05 con Docker real y `qwen2.5:7b` local: repara 2 errores de referencia inyectados y el IG pasa con 0 errores (ver `EXPERIMENTOS.md`). **Pendiente:** errores que solo ve el IG Publisher y errores de SUSHI.
- ~~Chequeo previo de existencia de perfiles y códigos contra `catalog.json`~~ (hecho).
- **Entregable:** a partir de un `spec.json` escrito a mano, el sistema genera un IG que converge a 0 errores; informe de iteraciones y costo.

## Semana 3 — Analista y narrativa

- Agente analista: del diccionario de datos (md/csv) a `spec.json`.
- Agente de páginas narrativas y terminología básica.
- Comprobaciones de degradación (cardinalidades y restricciones).
- **Entregable:** flujo completo de punta a punta sobre el caso de presión arterial.

## Semana 4 — Medición, demo y difusión

- Métricas de calidad y comparación con el IG de referencia.
- Repositorio pulido: README con la demo, licencia, guía de contribución.
- Resumen de una página para presentar a tu jefe y borrador de post técnico.
- **Entregable:** demo reproducible con costo por IG publicado.

## Estado del pipeline (2026-10-05)
`python -m agents.generate --spec <spec.md>` une todo: perfiles → ejemplos → chequeo previo → SUSHI + IG Publisher → reparación. Esqueleto del IG desde `templates/ig-base/` (neutro, no es el IG de referencia). Falta medirlo con un modelo real (ver `EXPERIMENTOS.md`).

## Cambio de rumbo (2026-10-05): modo estructurado
Tras la corrida 3 (ver `EXPERIMENTOS.md`) el flujo por defecto es: **analista (modelo) → `spec.json` validado → generador determinista (`generator/render.py`) → chequeo previo → SUSHI + IG Publisher → reparador**. El agente de perfiles y el de ejemplos de FSH libre se conservan como modo `--modo libre` (experimental). Hecho: ficha y validador, generador (reproduce las reglas del IG de referencia), analista con salida JSON y retroalimentación, pipeline y CLI. `python -m agents.generate --spec-json examples/demo/spec.json` corre todo sin modelo. Alcance v1: observaciones de signos vitales (valor único o componentes) y un paciente de ejemplo; otros tipos de recurso quedan fuera por ahora.

## Estado (2026-10-07): fin del ciclo de mediciones
- Hecho: modo estructurado de punta a punta, reglas deterministas de reparación, banco de errores inyectados, mediciones 1–11 (`EXPERIMENTOS.md`).
- Siguiente (en este orden): (1) publicar: README al día, `git init`, revisar licencias (`LICENCIAS.md`); (2) resumen de una página para la propuesta; (3) borrador del artículo técnico; (4) lector de planillas como segunda entrada.
- Pendiente de diseño, sin medir: regla de UCUM, nombres nuevos para instancias duplicadas, `estado_capitalizado` y fecha sin zona horaria; revisión con un modelo de pago (BYO key).
- Fuera de alcance por ahora: lector HL7 v2 (los ejemplos reales no se guardan en el repo).

## Estado 2026-10-07 (tarde): guía desde Excel
Nuevo camino sin modelo: `libro/` (plantilla, lector, verificador de coherencia, generador de FSH) y los comandos `plantilla`, `revisar` y `construir` de `cl_ig.py`. Libro de demostración sintético en `examples/libro-demo/`. 46 pruebas nuevas (`tests/test_libro.py`). Pendiente: correr `construir` con Docker real sobre el libro de demostración (0 errores en SUSHI y el publisher es el criterio de éxito de la fase 1). Siguientes fases: slicing/extensiones/invariantes, Questionnaire, Observation general, comprobar rutas contra `hl7.fhir.r4.core`.

### Resultado de la fase 1 (2026-10-07, noche)
El libro de demostración (`examples/libro-demo`) pasa **SUSHI y el IG Publisher sin errores, con 1 vuelta y 0 llamadas al modelo** (corrida real en Docker, 2026-10-07). Para llegar ahí hubo cuatro correcciones al generador/verificador, todas por fallos reales: dependencia con comillas en el YAML, correo de contacto en la configuración, texto de un código LOINC distinto al nombre oficial, y un código fuera del ValueSet obligatorio de `CorePrestadorCl`. Los dos últimos ya los detecta `revisar` antes de correr el Publisher. Pendiente: medir el tiempo de la corrida limpia (ahora el informe lo registra) y probar con un libro que no haya escrito yo.

## Estado 2026-10-07 (noche): extensiones y slicing
Hojas nuevas `Extensiones` (simples y complejas con partes) y `Slices`. FSH: `input/fsh/extensiones.fsh`, `contains` de extensiones y slices antes de las reglas del perfil, rutas de ejemplo `extension[x]` completadas con `valueX`. Verificador: tipos, contexto, partes, discriminadores, slices duplicados o ya existentes en CL Core, extensión no declarada en el perfil del ejemplo. Demo ampliado (AniosEscolaridad, ContactoPreferido, telecom[telefono|correo]). Pendiente: correr `construir` con Docker sobre el demo ampliado. Siguiente: invariantes, Questionnaire, Observation general.

## Estado 2026-10-20: camino por Excel como entrada principal
- Hecho: extensiones (simples y complejas), slicing (incluido por tipo y con orden), invariantes FHIRPath, Questionnaire, Bundles de mensaje, ids explícitos, ConceptMap, SearchParameter, OperationDefinition, CapabilityStatement. Importador de paquetes expuesto como `cl_ig.py importar`.
- Ida y vuelta con paquetes públicos: CL Core 1.9.3 29 de 29 (+45 recursos, 0 diferencias) y NID de MINSAL 0.4.9 23 de 23 (4 diferencias menores documentadas). 460 pruebas.
- `scripts/crear_kit.py` genera una carpeta liviana para que otra persona pruebe una guía propia (`docs/kit/`).
- Hecho el 2026-10-21: `construir` con Docker sobre el libro de demostración actual pasa SUSHI y el IG Publisher sin errores (0 llamadas al modelo, 460 s).
- Pendiente: probar con una persona ajena al desarrollo; Bundles de documento (Composition), modelos lógicos y StructureMap.

## 2026-10-21 (tarde): CL Core importado y construido de punta a punta
- El IG Publisher construyó el libro de CL Core 1.9.3 (1.608 páginas, 0 enlaces rotos) en 23 minutos. Quedaron 45 errores, todos por lo mismo: sin `--con-textos` el libro no tenía descripción en 43 CodeSystems/ValueSets (perfil ShareableValueSet de guías HL7) ni en las 2 declaraciones de capacidades (regla FHIR cpb-2).
- Arreglos: el importador deja una descripción neutra cuando no copia textos; `revisar` marca como error la falta de descripción en declaraciones de capacidades (siempre) y en CodeSystems/ValueSets de guías HL7; `construir` valida una sola vez, sin modelo ni reparaciones (un libro se corrige en el Excel); el tiempo máximo de Docker sube de 25 a 60 minutos; el informe tiene el estado «con_problemas» y agrupa los problemas repetidos.
- Causa de los 48 minutos: la primera pasada duró 23 min; el bucle llamó al modelo simulado y repitió la validación, que superó el tope de 25 min y se informó como «falló la infraestructura».
- Resultado: tras los arreglos, `construir clcore.xlsx` pasó SUSHI y el IG Publisher con 0 errores y 0 llamadas a un modelo (corrida 20261021-184354, 17,6 min).
- Avisos de la corrida de CL Core (0 errores, 150 avisos): 34 eran de la herramienta (ValueSets marcados experimentales mientras los perfiles y extensiones no); corregido, ahora los perfiles y extensiones llevan el mismo `experimental`. El resto viene del original o de no copiar textos: 20 conceptos sin definición, 28 perfiles/extensiones sin ejemplo (el import no trae ejemplos), la URL de `geolocation` con varias coincidencias y 4 slices de CoreMedicamentoCl sin Must Support.
