# Licencias y procedencia

Estado: **verificado el 2026-09-29 y actualizado el 2026-11-03** (IG Publisher y LOINC). Reverificar si cambian las versiones.

| Componente | Licencia | Cómo lo usamos | Fuente de la verificación |
|---|---|---|---|
| CL Core 1.9.3 (`hl7.fhir.cl.clcore`) | `CC0-1.0` declarada en `package.json` y en el recurso `ImplementationGuide`. El campo `copyright` del IG añade: "Usado con el permiso de HL7 International, todos los derechos reservados…" | Solo **referencia** por nombre y versión. El paquete no se incluye en el repo (`reference/` está en `.gitignore`). | Paquete `package.tgz` de la versión 1.9.3 |
| SUSHI (`fsh-sushi`) | Apache-2.0 | Se instala en la imagen Docker (versión fijada) | Registro npm, versión 3.20.1 |
| IG Publisher | Apache-2.0 | Se descarga en la imagen Docker (versión fijada); no se incluye el `.jar` en el repo | Repositorio oficial `HL7/fhir-ig-publisher` (2026-11-03) |
| Jekyll | MIT (licencia conocida de su proyecto) | Se instala en la imagen Docker; no se redistribuye | No se pudo consultar su repositorio desde el entorno de desarrollo; confirmar si se publica una imagen |
| LOINC | Licencia propia de Regenstrief: uso sin pago de licencia ni regalías, con la condición de incluir un aviso de copyright | Los códigos LOINC aparecen en ejemplos y en el FSH generado; el repo no incluye la base de LOINC | Página de licencia de LOINC (2026-11-03). El aviso está en el README, sección «Avisos de terceros». Las guías generadas con códigos LOINC deben llevar el suyo |

## Decisiones

1. **No redistribuir CL Core.** La señal de licencia es mixta (CC0 y una nota de derechos de HL7 International). Al referenciar el paquete en lugar de copiarlo no hay redistribución. Si en el futuro se quiere incluir extractos (por ejemplo el catálogo generado), confirmarlo por escrito con HL7 Chile.
2. **El catálogo generado (`build/catalog/`) tampoco se versiona**: se genera localmente con `make catalog`.
3. **Ejemplos de demostración: datos sintéticos propios.** No se usan datos de pacientes reales ni guías, ejemplos o documentos internos de ninguna organización.
4. **Licencia del repositorio: Apache-2.0** (decidido el 2026-10-01). Es la misma licencia de SUSHI. Aplica solo al código y la documentación propios; CL Core y demás componentes de terceros conservan las suyas.
