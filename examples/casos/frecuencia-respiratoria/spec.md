# Especificación de entrada (caso reservado): frecuencia respiratoria

Diccionario de datos de ejemplo, escrito para este proyecto. Caso reservado: no se usó para diseñar reglas, solo para medir.

## Observación

Se registra la frecuencia respiratoria como una observación de signos vitales de **valor único**: **frecuencia respiratoria, código LOINC `9279-1`**, en respiraciones por minuto (`rpm`; código UCUM `/min`).

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
| frecuencia_respiratoria | Respiraciones por minuto | número | sí | rpm (LOINC 9279-1) |
