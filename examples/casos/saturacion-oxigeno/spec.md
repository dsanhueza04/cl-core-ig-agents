# Especificación de entrada (caso): saturación de oxígeno

Diccionario de datos de ejemplo, escrito para este proyecto, para medir al analista con un caso distinto del demo.

## Observación

Se registra la saturación de oxígeno medida por oximetría de pulso como una observación de signos vitales de **valor único**: **saturación de oxígeno en sangre por oximetría de pulso, código LOINC `59408-5`**, expresada como porcentaje (`%`; código UCUM `%`).

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
| saturacion_o2 | Saturación de oxígeno por oximetría de pulso | número | sí | % (LOINC 59408-5) |
