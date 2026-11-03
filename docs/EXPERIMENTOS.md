# Registro de experimentos

Cada corrida real con un modelo, con lo que se esperaba y lo que pasó. Sirve de base para las métricas del informe final y del artículo.

## Equipo y modelo
Portátil i5-1235U, 16 GB de RAM, sin GPU dedicada. Ollama en Windows, modelo `qwen2.5:7b` (7,6 B parámetros, cuantizado Q4_K_M), accedido desde WSL con red espejo. Costo: 0 USD.

## Corrida 1 — IG roto (2 errores de referencia inyectados), 2026-10-05
Caso: `scripts/make_broken.py` (typo en el `Parent` de CL Core y un código en el CodeSystem equivocado).

| Vuelta | Errores | Resultado | Latencia | Tokens (entrada/salida) |
|---|---|---|---|---|
| 0 | 2 | Arregló el typo del `Parent`; cambió el código `01` por otro número | 222 s | 2.546 / 135 |
| 1 | 1 | Probó otro número | 150 s | 2.657 / 193 |
| 2 | 1 | Probó otro número (`33`) | 104 s | 2.674 / 133 |

Estado final: `max_iteraciones`, 1 de 2 errores resuelto. 3 llamadas, ≈8 min en total, 0 USD.

**Qué se aprendió**
- El modelo local de 7 B sigue el formato de parches BUSCAR/REEMPLAZAR y corrige bien lo que tiene una sugerencia directa (el nombre del perfil).
- Con el código erróneo adivinó valores sueltos: el aviso solo decía dónde existe el código, no cuáles son los válidos del CodeSystem. Corrección: el aviso ahora lista los códigos válidos cuando el CodeSystem tiene 40 o menos (`CSCodigoDNI` tiene 33, incluido `NNCHL`).
- El bucle no detectó que repetía el mismo error en la misma línea, porque la huella incluía el valor probado. Corrección: la huella de los errores del chequeo previo usa archivo, tipo y línea.
- Prompts de ≈2.600 tokens caben sin recorte; las respuestas tardan de 1,5 a 4 min por llamada en este equipo.

## Corrida 2 — mismo IG roto, con las correcciones de la corrida 1, 2026-10-05
Cambios previos: el aviso lista los códigos válidos de los CodeSystems cortos; la huella de los errores del chequeo previo usa archivo, tipo y línea.

| Vuelta | Etapa | Errores | Resultado |
|---|---|---|---|
| 0 | chequeo previo | 2 | Una sola llamada al modelo (109 s; 2.812 tokens de entrada, 140 de salida) corrigió ambos: `cl-core-signo-vitales` → `cl-core-signos-vitales` y `$CSDNI#01` → `$CSDNI#NNCHL` |
| 1 | validación real (SUSHI + IG Publisher) | 0 | `err = 0, warn = 7, info = 7`, IG Publisher 2.3.4 (≈4 min 50 s) |

Estado final: **`ok`**. 1 llamada al modelo, 0 USD, ≈7 min en total. El FSH resultante es idéntico al IG de referencia (`examples/demo/gold`).

**Qué se aprendió**
- Con el aviso completo (nombre sugerido y lista de códigos válidos), un modelo local de 7 B resuelve este tipo de errores de referencia de una vez.
- Primera corrida real de `validator/run.py` con Docker: funcionó.

**Límites de este resultado (no sobrevenderlo)**
- Los errores fueron inyectados y de tipo "referencia inexistente", justo los que el chequeo previo describe con detalle. No demuestra todavía que el sistema repare errores que solo ve el IG Publisher.
- Es un solo caso y una sola corrida; falta repetirlo y medir la variación entre corridas.
- Aún no se ha probado el camino de errores de SUSHI (su formato de consola está escrito de memoria).
- No prueba generación desde cero: el FSH de partida era el IG de referencia con dos errores.

## Corrida 3 — pipeline completo desde la especificación, `qwen2.5:7b`, 2026-10-05
Comando: `python -m agents.generate --spec examples/demo/spec.md` (sin ejemplos de referencia; caso de presión arterial).

| Etapa | Latencia | Tokens (entrada/salida) | Resultado |
|---|---|---|---|
| Agente de perfiles | 342 s | 3.008 / 604 | Perfil **incorrecto** (ver abajo); el chequeo previo no vio referencias inventadas |
| Agente de ejemplos | 468 s | 4.241 / 525 | Instancias coherentes con el perfil malo; una sintaxis de extensión incorrecta |
| SUSHI | ≈18 s | — | Falló; el IG Publisher no llegó a correr |
| Reparador | > 600 s | ≈2.000 (estimado) | **Se agotó la espera de 10 minutos**; el programa terminó con un error en vez de un informe |

Estado: sin IG válido. 0 USD. ≈25 min.

**Qué tenía mal el perfil generado** (comparado con `examples/demo/gold`): usa `8480-6` (sistólica) como código principal en vez del panel `85354-9`; no define las componentes como slices (`component contains sistolica ... and diastolica ...`); incluye decenas de reglas `code.extension(...)` sin sentido; deja las componentes en `0..1` en vez de obligatorias.

**Qué se aprendió**
- Un modelo local de 7 B cuantizado **no escribe FSH de perfiles con slices desde cero** con este prompt, aunque el prompt incluya un ejemplo de estilo y el catálogo. Sí repara bien errores de referencia con sugerencia (corridas 1 y 2). La hipótesis "el bucle de validación hace viable un modelo pequeño" se cumple para reparar, **no** para generar.
- Los errores de SUSHI sí llegaron al bucle (el parser leyó la consola real), pero hace falta ver ese texto para confirmar que el mensaje que recibe el modelo es útil.
- 600 s de espera máxima es poco en este equipo: se sube a 1.800 s por defecto y se puede cambiar con `LLM_TIMEOUT_S`.
- Un tiempo agotado ya no tumba el programa: termina con estado `modelo_no_responde`, conserva lo generado y escribe el informe.

**Consecuencia de diseño (propuesta)**: que el modelo no escriba FSH libre. Que rellene una ficha estructurada pequeña (`spec.json`: tipo de recurso, código LOINC, componentes, unidades, cardinalidades) y que **código determinista** produzca el FSH con plantillas ya probadas. El modelo elige datos; el programa escribe la sintaxis.

### Nota posterior a la corrida 3
- La salida real de SUSHI de ese borrador (`make validate IG=runs/.../ig`) confirmó que el formato de consola que lee `validator/parse_sushi.py` es el correcto; queda como prueba en `tests/fixtures/sushi_corrida3.txt`. Los 7 errores eran de estructura (extensión mal escrita, regla con texto basura, `subject` y `effective[x]` obligatorios sin valor), no reparables por parches sin reescribir el perfil.
- El validador de la ficha detectó que `examples/demo/spec.md` no incluía el código del panel de presión arterial; se agregó una sección "Observación" a la especificación.
- El generador determinista reproduce, a partir de `examples/demo/spec.json`, exactamente las reglas FSH del IG de referencia (prueba automática). Falta confirmarlo con SUSHI + IG Publisher en tu máquina: `python -m agents.generate --spec-json examples/demo/spec.json`.

## Cómo medir (scripts/medir.py)

Repite N veces solo la parte del analista (la lenta y la que varía) y resume: fichas válidas con intervalo
de confianza, intentos, tiempo, tokens y qué tipos de error atrapó el validador. Compara la estructura de cada
ficha (padre, LOINC, unidades, obligatoriedad) con la ficha de referencia; textos y datos del ejemplo no cuentan.

    export LLM_BACKEND=local LLM_MODEL=qwen2.5:7b
    make medir N=5                                  # ~9 min por corrida con CPU
    python scripts/medir.py --spec a.md --spec b.md --n 3 --max-minutos 90
    python scripts/medir.py --spec examples/demo/spec.md --n 3 --validar   # además compila cada ficha distinta

Con `--validar` la ficha se compila sin permitir reparación con modelo: mide si por sí sola produce un IG limpio.
Los resultados quedan en `runs/medicion-<fecha>/` (resultados.csv se actualiza tras cada corrida, así que Ctrl+C no pierde datos).
Con pocas corridas los intervalos son amplios: se reportan como señal, no como garantía.

## Medición 1 — analista con `qwen2.5:7b` local (6 oct 2026, n = 3, demo de presión arterial)

| | |
|---|---|
| Fichas válidas | 2/3 (intervalo 95 %: 21–94 %) |
| A la primera | 0/3 · intentos medios 2,33 |
| Estructura igual a la referencia | 2/2 de las válidas (padre, LOINC, unidades y obligatoriedad) |
| Tiempo por corrida | 218–466 s · ~3 900 tokens de entrada, ~1 150 de salida · $0 |

Qué atrapó el validador: los nombres de componente (`presion_sistolica`, con guion bajo) fallaron en **las 3 corridas, en
el primer intento**: es un error sistemático, no azar. La corrida inválida además omitió `ejemplo.fecha` y no la agregó en
los dos reintentos: el mensaje solo decía "falta", sin formato ni ejemplo.

Lectura: el modelo local acierta la parte que importa del perfil (estructura) y falla en convenciones de formato; el
validador las atrapa, pero un mensaje pobre no basta para que un modelo pequeño corrija.

Cambios derivados (antes de la medición 2): los mensajes del validador ahora citan el valor erróneo y dan un ejemplo
correcto; el prompt dice explícitamente "sin guiones bajos (sistolica, no presion_sistolica)" y que `ejemplo` siempre
lleva `fecha`. Decisión pendiente según la medición 2: si el nombre sigue fallando, normalizarlo por código (es un
identificador interno, sin significado clínico) y no pedirle al modelo que lo acierte.

## Medición 2 — mismo modelo y caso, tras mejorar mensajes y prompt (6 oct 2026, n = 3)

| | Medición 1 | Medición 2 |
|---|---|---|
| Fichas válidas | 2/3 | 3/3 (intervalo 95 %: 44–100 %) |
| A la primera | 0/3 | 0/3 |
| Intentos medios | 2,33 | 2,33 |
| Estructura igual a la referencia | 2/2 | 3/3 |
| Tiempo por corrida | 218–466 s | 184–321 s |

El error de nombres de componente desapareció (6 → 0 apariciones), pero en las 3 corridas el modelo omitió
`codigo_loinc` (el código del panel) en el primer intento; en una corrida, al corregirlo, perdió además el sexo y la
fecha de nacimiento del paciente de ejemplo. Lectura: no mejoró la tasa a la primera; el fallo se desplazó. Con n = 3
la diferencia entre mediciones no es concluyente; el patrón (olvida campos al reescribir la ficha completa) sí es consistente.

Cambios derivados (para la medición 3): el prompt exige `codigo_loinc` de la observación completa y el mensaje de error
lo explica; el modelo ya no necesita entregar el paciente de ejemplo, `nombre`, `id` ni los metadatos del ejemplo, que
completa el código (`completar_ficha`, nunca contenido clínico). El informe y `medir.py` registran cuántos campos completó
el código, para no confundirlo con aciertos del modelo.

## Medición 3 — ficha mínima + andamiaje por código (6 oct 2026, n = 3)

| | Med. 1 | Med. 2 | Med. 3 |
|---|---|---|---|
| Fichas válidas | 2/3 | 3/3 | **0/3** |
| A la primera | 0/3 | 0/3 | 0/3 |
| Intentos medios | 2,33 | 2,33 | 3 |

Resultado peor, y útil. Con el prompt reescrito, el modelo volvió a escribir `presion_sistolica` (3/3 corridas, primer
intento) aunque el prompt lo prohíbe de forma explícita, y puso el ejemplo del panel bajo la clave `valor` en vez de
`valores`: el mensaje de error nombraba `valores` pero no decía que la clave estaba mal, y el modelo repitió el error en los
dos reintentos. En una corrida, al corregir, rompió ids que antes estaban bien.

Lectura honesta: entre mediciones el mismo modelo varía mucho (con n = 3 no se puede atribuir la mejora de la 2 ni el
empeoramiento de la 3 al prompt) y, en las tres, el contenido (LOINC, unidades, componentes) fue correcto: lo que falla es
la forma. Ajustar el prompt solo desplaza el error.

Cambios derivados (medición 4, mismo prompt para aislar el efecto): `completar_ficha` ahora normaliza la forma —nombres
de componente, `valor` → `valores`, ids de andamiaje inválidos— y lo registra; el mensaje de `valores` explica la clave.
Lo clínico (códigos, unidades, valores) no se toca. La respuesta real de esta medición quedó como prueba de regresión
(`tests/fixtures/ficha_modelo_medicion3.json`). `medir.py` separa "a la primera" de "a la primera sin ayuda del código".

## Medición 4 — misma entrada y prompt, con normalización de forma por código (6 oct 2026, n = 3)

| | Med. 1 | Med. 2 | Med. 3 | Med. 4 |
|---|---|---|---|---|
| Fichas válidas | 2/3 | 3/3 | 0/3 | **3/3** |
| A la primera | 0/3 | 0/3 | 0/3 | **3/3** |
| A la primera sin ayuda del código | – | – | – | **0/3** |
| Estructura igual a la referencia | 2/2 | 3/3 | – | 3/3 |
| Tiempo por corrida (mediana) | 241 s | 310 s | 336 s | 99 s |

Qué hizo el código en cada corrida (reconstruido con la respuesta cruda del modelo): normalizó nombres de componente
(`presion_sistolica` → `presionSistolica`, 2/3), movió `valor` a `valores` en el panel (2/3) y recalculó `nombre`, donde el
modelo había puesto el perfil padre (2/3). Es decir: la respuesta cruda del modelo habría fallado el validador las 3
veces; el pipeline absorbe esos errores de forma y el contenido (LOINC, unidades, componentes) coincidió 3/3 con la
referencia. La mejora de tiempo es solo la ausencia de reintentos.

Cautelas: n = 3 (intervalo 95 %: 44–100 %); las normalizaciones se escribieron mirando fallos de este mismo caso y se
midieron sobre él, así que **no prueban generalización**. Siguiente paso: tres casos distintos del demo
(`examples/casos/`: frecuencia cardíaca, saturación de oxígeno, peso y talla con dos observaciones), para medir sobre
entradas que el código no vio, y compilar con SUSHI + IG Publisher sus fichas de referencia (el renderizador solo se ha
compilado de punta a punta con el panel de presión arterial; valor único y varias observaciones aún no).

## Medición 5 — tres casos nuevos con `qwen2.5:7b` local (6 oct 2026, n = 3 por caso)

Casos: `frecuencia-cardiaca`, `saturacion-oxigeno`, `peso-talla` (`examples/casos/`). Con el código de la medición 4.

| | Resultado |
|---|---|
| Fichas válidas | 8/9 (intervalo 95 %: 56–98 %) |
| A la primera | 6/9 (sin ninguna ayuda del código: 1/9) |
| Estructura igual a la referencia | 6/8 |
| Tiempo (mediana / p95) | 96 s / 299 s |

Por caso: frecuencia cardíaca 3/3 y saturación de oxígeno 3/3 válidas (una de ellas con 3 intentos); peso y talla
(dos observaciones) 2/3, con la inválida tras 3 intentos.

Los 3 hallazgos del detalle:
1. **Falso negativo de mi comparación**: `lpm` vs `latidos/minuto` (mismo UCUM `/min`). La firma estructural ya no cuenta
   el texto de la unidad.
2. **Hueco de mi validador**: el modelo escribió peso y talla como paneles de un solo componente y el validador lo
   aceptó. Ahora un panel exige 2 o más componentes; el caso inequívoco (LOINC del componente igual al de la observación)
   se convierte a `valor`.
3. **Confusión de forma con varias observaciones**: el modelo puso el objeto de unidad en `ejemplo.valor` (debe ser un
   número) y alternó formas entre intentos; los mensajes decían qué estaba mal pero no mostraban un ejemplo correcto. Ahora
   lo muestran. El código no inventa el valor medido: es contenido clínico.

Estos tres casos pasan a ser de **desarrollo** (sus fallos inspiraron cambios). Para la medición 6 se agregaron tres
**reservados** que el código no ha visto: `frecuencia-respiratoria`, `crecimiento-infantil` (2 observaciones) y
`oxigenoterapia` (3 observaciones).

## Medición 6 — tres casos reservados con `qwen2.5:7b` local (6 oct 2026, n = 3 por caso)

Casos que no se usaron para diseñar reglas: `frecuencia-respiratoria`, `crecimiento-infantil` (2 observaciones) y
`oxigenoterapia` (3 observaciones).

| | Resultado |
|---|---|
| Fichas válidas | 9/9 (intervalo 95 %: 70–100 %) |
| A la primera | 9/9 (sin ninguna ayuda del código: 1/9; el código completó o normalizó 5,9 campos por corrida) |
| Estructura igual a la referencia | 9/9 |
| Tiempo (mediana / p95) | 95 s / 164 s · ~1 400 tokens de entrada, ~460 de salida · $0 |

Lectura: con el código de las mediciones 4 y 5, el modelo local generaliza a entradas nuevas, incluso con 3
observaciones. Cautelas: n = 9 en total; el "a la primera" cuenta la ayuda del código (la respuesta cruda casi nunca valida
sola); las normalizaciones corrigen hábitos de este modelo y no se ha probado con otro.

## Compilación (SUSHI + IG Publisher) de las fichas de referencia, sin modelo (6 oct 2026)

| Caso | Estado |
|---|---|
| frecuencia-cardiaca, peso-talla (2 obs.), frecuencia-respiratoria, crecimiento-infantil (2 obs.), oxigenoterapia (3 obs.) | ok |
| saturacion-oxigeno | **sin_progreso** |

El renderizador funciona de punta a punta para valor único y para varias observaciones. El fallo de `saturacion-oxigeno` es
un error real que solo ve el IG Publisher:

    OxygenSatCode: magic LOINC code 2708-6 required, but not found
    (from http://hl7.org/fhir/StructureDefinition/oxygensat|4.0.1)

FHIR R4 exige que la saturación de oxígeno lleve el código `2708-6` aunque se use `59408-5` (oximetría de pulso); ambos
están en el ValueSet de signos vitales de CL Core. El caso se diseñó con `59408-5` como único código: error del autor del
caso, no del modelo. El pipeline se comportó como debía: clasificó el error como del publisher, intentó repararlo (con el
modelo simulado), detectó que no avanzaba y lo dejó como pendiente.

Es un buen ejemplo de la clase de conocimiento que ninguna comprobación previa tenía: reglas de los perfiles base de FHIR
("magic codes") que solo aparecen al compilar.

## Experimento 7: reparación con modelo real de un error solo del publisher

Caso `saturacion-oxigeno` (LOINC 59408-5): el publisher exige además el código 2708-6 (regla de los perfiles base de signos vitales de FHIR R4). Reparación con `qwen2.5:7b`, mismo flujo `run_loop`.

- Resultado: `max_iteraciones`, 5 llamadas al reparador, ~1090 s, $0. No convergió.
- El modelo reemplazó el código del ejemplo por 2708-6 en vez de agregar un segundo coding. Eso chocó con el patrón fijo del perfil (`Cannot assign ...#59408-5 ... a different CodeableConcept is already assigned`).
- Parches mal formados: a menudo envolvía el texto SEARCH con comillas invertidas o no lo copiaba exacto.
- Conclusión: un modelo 7B no repara errores que solo ve el publisher y requieren conocimiento del dominio. Ese conocimiento va al código: `CODIGOS_OBLIGATORIOS_FHIR` en `generator/render.py` agrega 2708-6 al ejemplo por regla.
- Primer intento de la regla: `code.coding[+]` pisó el índice 0 del ejemplo (SUSHI parte en 0), dejando solo 2708-6; el publisher reclamó que el patrón 59408-5 no se encontraba. Corregido con índices explícitos (`coding[1]`).
- Pendiente: re-compilar el caso con Docker para confirmar `estado: ok`.

## Experimento 8: banco de 12 errores inyectados, línea base sin modelo

`scripts/medir_reparacion.py` sobre `examples/demo/gold` con 12 errores de `scripts/errores.py`, `LLM_BACKEND=mock`, sin reglas deterministas, n=1 por caso.

- Resultado: 0/12 convergen (IC95 Wilson 0–0,24). Es la línea base: sin modelo ni reglas no se repara nada.
- Etapa observada vs hipótesis: 2 de los 4 casos que supuse "solo publisher" (`referencia_a_tipo_no_permitido`, `fecha_con_formato_invalido`) los detecta SUSHI antes. Solo `falta_componente_obligatorio` y `estado_fuera_del_valueset` llegan al publisher.
- Costo en tiempo: los casos que llegan al publisher tardan 10–11 min por corrida (2 pasadas); los de SUSHI, 15–40 s.
- El mensaje del publisher para `falta_componente_obligatorio` no nombra el componente que falta (reporta la restricción `vs-3`): ni una regla ni un modelo pequeño pueden deducir de ahí qué agregar.

## Experimento 9: reglas deterministas antes del modelo (casos de desarrollo)

`agents/reglas.py` + `LLM_BACKEND=mock`, 12 casos de desarrollo, n=1, Docker real (SUSHI + IG Publisher).

- Resultado: **9/12 convergen con 0 llamadas al modelo** (IC95 Wilson 0,47–0,91). Línea base sin reglas: 0/12.
- Convergen: parent con typo, alias indefinido, regla sin espacios, slice mal escrito, valor sin unidad, código del ejemplo distinto al del perfil, referencia a tipo no permitido, fecha dd-mm-aaaa, estado en español.
- No convergen, como se esperaba: `codigo_en_codesystem_equivocado`, `unidad_distinta_al_perfil`, `falta_componente_obligatorio`. Son los que exigen una decisión (cuál código, qué unidad, qué valor).
- Tiempo: ~3,5–4,5 min por caso que pasa por SUSHI y publisher (el IG completo vuelve a validarse tras la regla); 9 min el caso de estado en español.
- Límite importante: las reglas se escribieron mirando estos mismos 12 mensajes. Es una medición dentro de la muestra; no demuestra que generalicen.

## Experimento 10: casos reservados (segundo lote), mock + reglas

8 errores nuevos escritos después de las reglas y sin regla para ellos. Predicción registrada antes de medir: 0 o 1 de 8.

- Resultado: **0/8** (IC95 Wilson 0–0,32). La predicción se cumplió: las reglas del lote 1 no generalizan a otras familias de error.
- Lo que mostraron los mensajes reales:
  - `categoria_sin_guion`, `id_con_guion_bajo`, `title_sin_comillas`, `genero_en_espanol` y `referencia_a_instancia_inexistente` se pueden arreglar por regla (el mensaje dice qué está mal y el contexto dice cómo corregirlo).
  - `ucum_invalido`: SUSHI culpa al ejemplo ("Cannot assign mm[Hg] ... already assigned: mmHg") pero el error está en el **perfil**. El mismo mensaje que en `categoria_sin_guion` pide la corrección contraria. Sin una lista de unidades UCUM no hay forma segura de decidir; se deja sin regla.
  - `instancia_duplicada`: no se sabe qué nombre nuevo poner. Sin regla.
  - `fecha_nacimiento_imposible`: terminó como `infraestructura` sin ningún error. **Hueco en el validador**: el publisher se cayó con una excepción (`Invalid date/time format: "1975-06-31"`) y solo dejó `qa.json` con el campo `exception`; nadie lo leía. Corregido: ahora la excepción es un error de contenido del reporte (o de infraestructura si es de red).
- Estos 8 casos ya no son reservados: se usaron para escribir reglas (`codigo_en_espanol`, `codigo_del_perfil_base`, `id_fhir_invalido`, `texto_sin_comillas`, `referencia_inexistente`) y pasaron al conjunto de desarrollo (20 casos).

## Experimento 11: casos reservados (tercer lote), mock + reglas

7 errores nuevos, sin ninguna regla pensada para ellos. Predicción registrada antes de medir: 1 o 2 de 7.

- Resultado: **2/7** (IC95 Wilson 0,08–0,64), 0 llamadas al modelo en los que convergen. La predicción se cumplió, incluidos los casos concretos.
- Convergen: `parent_en_mayusculas` y `alias_en_plural` (variantes cercanas de reglas existentes: el chequeo previo sugiere el nombre correcto, y el alias se resuelve por parecido).
- No convergen: `estado_capitalizado` (la tabla solo conoce minúsculas), `fecha_sin_zona_horaria` (la regla de fecha solo lee día-mes-año), `display_sin_comillas`, `instanceof_con_typo`, `usage_sin_numeral`.
- Lectura: las reglas cubren su familia y variantes cercanas, no errores nuevos. Hay que presentar así el sistema: las reglas son un acelerador para errores frecuentes y conocidos, no una garantía; el resto queda para el modelo o una persona, siempre con revisión humana.

## Resumen de la reparación de errores (experimentos 8–11)

| Conjunto | Casos | Sin reglas | Con reglas (mock, 0 llamadas) |
|---|---|---|---|
| Desarrollo, lote 1 (reglas escritas mirándolo) | 12 | 0/12 | 9/12 |
| Reservado, lote 2 (antes de escribir sus reglas) | 8 | — | 0/8 |
| Reservado, lote 3 (variantes y errores nuevos) | 7 | — | 2/7 |

Cada lote reservado tiene n pequeño (un solo intento por caso): son señales, no garantías. Con el modelo local (`qwen2.5:7b`) no se logró reparar errores que solo ve el publisher (experimento 7). No se midió con un modelo de pago.

Decisión (7 oct 2026): se cierra el ciclo de mediciones de reparación. Los hallazgos de diseño que quedan por hacer están en `PLAN.md`.
