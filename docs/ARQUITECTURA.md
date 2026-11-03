# Arquitectura

## Principios

1. **El validador es determinista y va primero.** SUSHI + IG Publisher producen los errores; ningún LLM decide si el IG "pasa".
2. **Contratos entre agentes.** El analista produce `spec.json`; cada agente recibe solo lo que necesita (menos costo, pruebas más simples).
3. **Parches acotados.** El reparador edita fragmentos, no reescribe archivos, y tiene tope de iteraciones (por archivo y por corrida).
4. **Sin trampas.** Comprobaciones que detectan si el reparador relajó cardinalidades, borró ejemplos o quitó restricciones para "pasar".
5. **Un humano revisa siempre** el resultado final.
6. **Costo medido.** Cada llamada al LLM se registra (agente, modelo, tokens, costo, iteración) y hay un tope de gasto por corrida.

## Flujo

```
spec (md/csv) → [1 Analista] → spec.json
   → [2 Perfiles FSH] [3 Ejemplos FSH] [4 Páginas y terminología]
   → ig/ (proyecto SUSHI)
   → [5 Validador — sin LLM]: SUSHI → IG Publisher → errores JSON
   → [6 Reparador (LLM)] → parche → vuelve a 5 (máx. N iteraciones)
   → informe + revisión humana
```

## Anti-alucinación con CL Core

`scripts/extract_catalog.py` produce dos artefactos a partir del paquete oficial:

- `catalog.md`: resumen de perfiles, extensiones, ValueSets y CodeSystems, como contexto (con caché de prompt) para los agentes.
- `catalog.json`: índice completo con todos los códigos. Un chequeo previo, sin LLM, rechaza cualquier perfil, extensión o código citado que no exista en CL Core 1.9.3 antes de gastar una ejecución del publisher.

## Modelos y costo

- Todas las llamadas pasan por `llm.LLMClient`, con tres backends: `mock` (por defecto, gratis), `local` (servidor compatible con OpenAI, por ejemplo Ollama) y `anthropic` (de pago, opcional).
- Cada llamada queda en un JSONL (agente, modelo, tokens, costo, iteración) y los backends de pago respetan un tope de gasto por corrida.
- Los precios viven en `llm/pricing.json`, con fecha y fuente; un modelo de pago sin precio falla antes de llamar.
- **Hipótesis a medir:** el bucle de validación objetivo permite que modelos pequeños y locales lleguen a un IG válido. Se medirá con iteraciones hasta converger y tasa de éxito por modelo.

## Restricción de versión: FHIR R4

CL Core 1.9.3 está construido sobre **FHIR R4 (4.0.1)**, no R5. Consecuencias:

- Los IG generados declaran `fhirVersion: 4.0.1`.
- Los prompts de los agentes deben indicar R4 de forma explícita y prohibir elementos que solo existen en R5.
- El validador es la red de seguridad: un elemento R5 en un perfil R4 falla en SUSHI o en el IG Publisher.
- El mensaje "Unable to load IG as an r5 IG - try R4" del publisher es informativo y normal: intenta R5 primero y cae a R4.

## Clasificación de errores del validador

La primera corrida real del IG de referencia (fixture en `tests/fixtures/`) dio 15 errores, pero solo **2 eran de contenido**; los otros 13 eran fallas del servidor de terminología (`SocketTimeoutException` y "The cache … was never issued by this server"). Consecuencia de diseño:

- `parse_qa.py` clasifica cada mensaje como **contenido** (el IG está mal) o **infraestructura** (red o servidor de terminología).
- Los errores de infraestructura se **reintentan**, sin invocar al LLM. Solo los de contenido van al reparador.
- Un error de contenido puede quedar enmascarado por uno de infraestructura sobre el mismo recurso; tras reintentar se vuelve a clasificar.

## Decisiones abiertas (a cerrar en semana 2)

- Modelos concretos para generación y reparación (se medirá costo real).
- Formato de `spec.json` (se define con el primer caso de demostración).
- Tope de iteraciones (por archivo / por corrida).

## Métricas de calidad

1. Errores, warnings e infos del IG Publisher (objetivo: 0 errores, warnings justificados).
2. Cobertura de la especificación: campos mapeados a elementos o decisiones documentadas.
3. Conformidad de ejemplos: al menos un ejemplo positivo válido por perfil.
4. Detección de degradación: cardinalidades y restricciones finales frente a `spec.json`.
5. Comparación con el IG de referencia hecho a mano ("gold").
6. Eficiencia: iteraciones hasta converger, tokens y costo por IG.
7. Rúbrica de revisión humana (pertinencia clínica, narrativa, uso correcto de CL Core).

## Modo estructurado (desde 2026-10-05)

```
spec.md ──► Analista (modelo, JSON) ──► spec.json ──► validate_spec ──┐
                  ▲  (retroalimentación si hay problemas, máx. 2)      │ ficha válida
                  └──────────────────────────────────────────────────┘
spec.json ──► generator/render.py (determinista) ──► aliases / perfiles / ejemplos .fsh
          ──► chequeo previo ──► SUSHI + IG Publisher ──► reparador (parches) ──► IG
```

- El modelo solo elige datos (códigos, unidades, nombres, valores de ejemplo); nunca escribe sintaxis FSH.
- La ficha se valida de forma estricta: formatos, padre existente en CL Core, nombres únicos, y **cada código LOINC debe aparecer en la especificación** (no se puede verificar LOINC sin su base de datos, así que se impide inventarlos).
- El generador es una función pura: misma ficha, mismo FSH. Una prueba automática exige que reproduzca las reglas del IG de referencia.
- El reparador queda como red de seguridad para lo que solo ven SUSHI y el IG Publisher.
- Límite actual: solo observaciones de signos vitales. Ampliar a otros recursos es agregar plantillas y reglas de validación, no cambiar el flujo.
