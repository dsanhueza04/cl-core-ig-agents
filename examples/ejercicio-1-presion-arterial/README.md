# Ejercicio 1: control de presión arterial — solución de referencia

Libro resuelto del ejercicio, con datos 100 % sintéticos. Sirve para estudiar cómo cada hoja se convierte en FHIR.

```
python cl_ig.py revisar   examples/ejercicio-1-presion-arterial/solucion-ejercicio-1.xlsx
python cl_ig.py construir examples/ejercicio-1-presion-arterial/solucion-ejercicio-1.xlsx
```

Las filas del libro están en `datos.py` (el `.xlsx` se genera con `python examples/ejercicio-1-presion-arterial/datos.py`).

## Cómo leerlo (hoja → FSH → qué ves en la guía)

| En el libro | Se escribe como | Dónde se ve en la guía publicada |
|---|---|---|
| **Perfiles**: `PacienteCesfam` con padre `CorePacienteCl` | `Profile: PacienteCesfam` / `Parent: …CorePacienteCl` | Perfil, pestaña *Snapshot* (todo lo heredado) y *Differential* (solo tus cambios) |
| **Elementos**: `gender` 1..1 MS | `* gender 1..1 MS` | Tabla del perfil: el elemento aparece con «1..1» y «S» |
| **Elementos**: `identifier.system` con valor fijo | `* identifier.system = "http://regcivil.cl/Validacion/RUN"` | Fila con el valor fijo |
| **Elementos**: `method` con ValueSet y fuerza `extensible` | `* method from VSPosturaMedicion (extensible)` | Pestaña de bindings del perfil |
| **Elementos**: `code` con valor fijo LOINC | `* code = $LOINC#85354-9` | El panel de presión arterial queda identificado |
| **Elementos**: `value[x]` 0..0 | `* value[x] 0..0` | El valor propio de la observación queda prohibido |
| **Slices**: `telecom` → `telefono`, `correo` | `* telecom contains telefono 0..1 MS and correo 0..1 MS` | Sección *Slices* del perfil |
| **Slices**: `component` → `sistolica`, `diastolica` | `* component contains sistolica 1..1 MS and …` y `* component[sistolica].code = $LOINC#8480-6` | Lo que distingue cada componente es su `code` |
| **Extensiones**: `MedicionDomiciliaria` (simple) | `Extension: MedicionDomiciliaria` / `* value[x] only boolean` | Página de la extensión |
| **Extensiones**: `ProgramaCardiovascular` con partes | `* extension contains fechaIngreso 1..1 and nivelRiesgo 1..1` | Extensión compleja con dos sub-extensiones |
| **Elementos**: `extension[programaCardiovascular]` | `* extension contains ProgramaCardiovascular named programaCardiovascular 0..1 MS` | Esto es lo que hace que el perfil **admita** la extensión |
| **CodeSystems / Conceptos / ValueSets / Inclusiones** | `CodeSystem:` y `ValueSet:` | Páginas de terminología |
| **Valores**: `extension[medicionDomiciliaria]` | `* extension[medicionDomiciliaria].valueBoolean = false` | El tipo de valor (`valueBoolean`) lo agrega la herramienta |

## Decisiones que conviene entender

1. **Solo se escribe lo que cambia.** No hay filas para `category[VSCat]`, `status` ni `subject` obligatorio en la observación porque `cl-core-signos-vitales` ya los exige.
2. **Mín 1 y Must Support son cosas distintas.** Los datos que «debe presentar» el paciente llevan los dos.
3. **La regla de cantidad va en el padre y la de contenido en el hijo:** `telecom` 1..* (al menos un contacto) y `telecom.value` 1..1 (cada contacto trae su dato).
4. **Slicing cerrado vs abierto.** `telecom` es `closed` (solo teléfono o correo); `component` es `open` (se pueden agregar otros componentes además de los dos).
5. **`pattern` para distinguir componentes.** El campo `code` de cada componente es un CodeableConcept; se distingue por su patrón (el código LOINC).
6. **Extensible vs required.** La postura es `extensible` para no obligar a registrar una postura falsa; el nivel de riesgo es `required` porque la lista es cerrada.
7. **Extensión solo cuando no existe el elemento.** `bodySite` y `method` ya existen en Observation; la medición domiciliaria no, por eso es extensión.
8. **El tipo de valor de las extensiones lo pone la herramienta** (`valueBoolean`, `valueDate`, `valueCode`) a partir de la hoja Extensiones.

## Qué mirar después de construir
- La pestaña *Differential* y *Snapshot* del perfil `PresionArterialCesfam`.
- Cómo aparece `component` con sus dos slices.
- Las páginas de las extensiones.
- Que los dos ejemplos de presión pasen la validación contra el perfil (0 errores).
