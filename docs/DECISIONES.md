# Registro de decisiones

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-10-01 | **Fijar CL Core 1.9.3** y no migrar a 1.9.4 por ahora | La versión nueva está aún en construcción; se migra cuando se publique estable. El IG Publisher avisa de la 1.9.4 como warning y es una advertencia asumida. |
| 2026-10-01 | **FHIR R4 (4.0.1)** como única versión soportada | CL Core 1.9.3 es R4. |
| 2026-10-01 | **Licencia Apache-2.0** para el repositorio | Permisiva, con concesión explícita de patentes; compatible con SUSHI (Apache-2.0). |
| 2026-10-01 | **Gratis por defecto; modelo intercambiable** (`mock` / `local` / `anthropic`) | Objetivo de visibilidad y desarrollo sin gasto. La herramienta es gratuita; quien la use aporta su modelo (local o con su propia clave). Un servicio de pago se puede construir después alrededor de la herramienta. |
| 2026-10-01 | **Contexto por demanda + chequeo previo sin modelo** antes de los agentes | Equipo de 16 GB sin GPU dedicada: los modelos locales son pequeños y lentos, así que los prompts deben ser cortos y los errores de referencia se detectan en segundos, no en los 6 min del publisher. |
| 2026-10-04 | **Reparación por parches BUSCAR/REEMPLAZAR** con rechazo de parches que debilitan cardinalidades | Los modelos pequeños reescriben archivos enteros y rompen lo que funcionaba; un parche exacto es verificable y la antitrampa evita "arreglar" bajando restricciones. |
| 2026-10-06 | **El código completa el andamiaje de la ficha; el modelo solo aporta lo que exige leer la especificación** (códigos, componentes, unidades, valores) | Las mediciones 1 y 2 mostraron que cada ajuste del prompt desplaza qué campo olvida el modelo de 7 B (nombres de componente, luego `codigo_loinc`, y al corregir una cosa perdía otras). El paciente de ejemplo, ids y metadatos del ejemplo no requieren leer nada: los completa `completar_ficha` y el informe lista lo completado. Lo clínico nunca se inventa por código. |
| 2026-10-06 | **El código también normaliza la FORMA de la ficha** (nombres internos de componente `presion_sistolica` → `presionSistolica`, clave `valor` → `valores` en paneles, ids de andamiaje inválidos se recalculan) y lo registra | Tras 3 mediciones (n = 3 c/u) el modelo de 7 B seguía fallando en forma, no en contenido: en la medición 3 repitió los nombres con guion bajo aun con la regla explícita y puso el ejemplo del panel bajo `valor`. Nada de esto es una decisión clínica y arreglarlo por código es verificable; el informe lista cada cambio y `medir.py` separa los aciertos con y sin ayuda del código. |
| 2026-10-06 | **Casos de desarrollo y casos reservados** (`examples/casos/`) y la firma estructural de `medir.py` ignora el texto de la unidad | Las reglas se escribieron mirando fallos; medir sobre los mismos casos sobreestima. Los reservados no inspiran cambios (si uno lo hace, pasa a desarrollo y se escribe otro). Comparar el texto de la unidad daba falsos negativos (`lpm` vs `latidos/minuto`, mismo UCUM `/min`): lo que cuenta es el código. |
| 2026-10-06 | **Un panel necesita al menos 2 componentes**; una medición única escrita como panel de 1 componente con el LOINC de la observación se convierte a `valor` | La medición 5 mostró que el modelo escribía peso y talla como paneles de un componente y el validador lo aceptaba (hueco de mis reglas, no del modelo). Si el LOINC del componente difiere del de la observación no se adivina: sigue siendo error. |
| 2026-10-05 | **Modo estructurado por defecto**: el modelo rellena una ficha (`spec.json`) y el código escribe el FSH | La corrida 3 mostró que un modelo local de 7 B no escribe FSH con slices desde cero. Con la ficha, el modelo solo elige datos y la sintaxis es determinista y probada. El modo libre queda como experimental. |
| 2026-10-05 | **Los códigos LOINC de la ficha deben aparecer en la especificación de entrada** | LOINC no se puede verificar sin su base de datos; así el modelo no puede inventar códigos. Al aplicarlo se vio que `examples/demo/spec.md` no traía el código del panel (`85354-9`): se agregó a la especificación en vez de aflojar la regla. |
| 2026-10-01 | **IG Publisher 2.3.4** (antes 2.0.17) | El publisher marcó la 2.0.17 como desactualizada y `tx.fhir.org` rechazó su identificador de caché. |
| 2026-09-29 | CL Core se **referencia, no se redistribuye** | Señal de licencia mixta (CC0 y nota de derechos de HL7 International). Ver `LICENCIAS.md`. |

## Reglas deterministas antes del modelo
- Decisión: los errores cuyo arreglo sale del mensaje y del contexto del IG se reparan por regla (`agents/reglas.py`), antes de llamar al modelo. Motivo: un modelo de 7B no repara de forma fiable (experimentos 3 y 7) y cada llamada local cuesta minutos.
- Límites: una regla cambia una sola línea, nunca toca cardinalidades ni borra restricciones, y deja un `Cambio` registrado (archivo:línea, antes, después, nota). No hay regla para lo que exige decisión clínica.
- Se puede desactivar (`--sin-reglas`) para medir al modelo solo.

## Un mismo mensaje puede pedir la corrección contraria
- SUSHI dice "Cannot assign X ...; a different code is already assigned: Y" tanto cuando el ejemplo está mal (`vitalsigns` vs `vital-signs`) como cuando el que está mal es el perfil (`mmHg` vs `mm[Hg]`).
- Decisión: la regla `codigo_del_perfil_base` solo corrige el ejemplo si el valor fijo Y no aparece en ningún archivo del IG (viene de un perfil base). Si aparece, no se adivina.
- La regla `codigo_distinto_al_perfil` (códigos de `CodeableConcept`) sí asume que el perfil manda, porque en el flujo estructurado el perfil sale de la ficha. Es una suposición: queda anotada en el cambio para revisión humana.
- Una excepción del IG Publisher es un error del IG, no "infraestructura": se lee de `qa.json`.
