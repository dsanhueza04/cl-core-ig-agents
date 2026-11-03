# Especificación de entrada (caso): peso y talla

Diccionario de datos de ejemplo, escrito para este proyecto, para medir al analista con un caso distinto del demo.

## Observaciones

Se registran **dos observaciones independientes** de signos vitales, cada una de valor único (no forman un panel):

- **Peso corporal, código LOINC `29463-7`**, en kilogramos (`kg`; código UCUM `kg`).
- **Talla (estatura de pie), código LOINC `8302-2`**, en centímetros (`cm`; código UCUM `cm`).

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
| peso | Peso corporal | número | sí | kg (LOINC 29463-7) |
| talla | Talla del paciente | número | sí | cm (LOINC 8302-2) |
