# Especificación de entrada (demo): registro de presión arterial

Diccionario de datos de ejemplo, escrito para este proyecto. Es la entrada del analista y la referencia contra la que se mide la cobertura del IG generado. El IG de referencia está en [`gold/`](gold/).

## Observación

La medición se registra como una observación de signos vitales de tipo panel: **presión arterial, código LOINC `85354-9`**, con dos componentes (sistólica y diastólica).

## Datos

| Campo | Descripción | Tipo | Obligatorio | Terminología / unidad |
|---|---|---|---|---|
| run | RUN del paciente | texto | sí | Identificador chileno |
| nombres | Nombres del paciente | texto | sí | |
| primer_apellido | Primer apellido | texto | sí | |
| segundo_apellido | Segundo apellido | texto | no | Extensión de CL Core |
| sexo | Sexo administrativo | código | sí | `female`, `male`, `other`, `unknown` |
| fecha_nacimiento | Fecha de nacimiento | fecha | sí | |
| fecha_hora_medicion | Momento de la medición | fecha y hora | sí | |
| presion_sistolica | Presión arterial sistólica | número | sí | mmHg (LOINC 8480-6) |
| presion_diastolica | Presión arterial diastólica | número | sí | mmHg (LOINC 8462-4) |

## Alcance de la versión mínima ("gold")

Cubre los campos de paciente y los dos componentes de la medición. No incluye todavía dirección, profesional que mide ni clasificación de la presión.
