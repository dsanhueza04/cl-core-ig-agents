# Especificación de entrada (caso): frecuencia cardíaca

Diccionario de datos de ejemplo, escrito para este proyecto, para medir al analista con un caso distinto del demo.

## Observación

Se registra la frecuencia cardíaca como una observación de signos vitales de **valor único**: **frecuencia cardíaca, código LOINC `8867-4`**, expresada en latidos por minuto (`lpm`; código UCUM `/min`).

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
| frecuencia_cardiaca | Latidos por minuto | número | sí | lpm (LOINC 8867-4) |
