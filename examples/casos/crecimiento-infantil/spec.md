# Especificación de entrada (caso reservado): control de crecimiento infantil

Diccionario de datos de ejemplo, escrito para este proyecto. Caso reservado: no se usó para diseñar reglas, solo para medir.

## Observaciones

Se registran **dos observaciones independientes** de signos vitales, cada una de valor único (no forman un panel):

- **Perímetro cefálico (circunferencia occipito-frontal de la cabeza), código LOINC `9843-4`**, en centímetros (`cm`; código UCUM `cm`).
- **Índice de masa corporal, código LOINC `39156-5`**, en kilogramos por metro cuadrado (`kg/m2`; código UCUM `kg/m2`).

## Datos

| Campo | Descripción | Tipo | Obligatorio | Terminología / unidad |
|---|---|---|---|---|
| run | RUN del paciente | texto | sí | Identificador chileno |
| nombres | Nombres del paciente | texto | sí | |
| primer_apellido | Primer apellido | texto | sí | |
| segundo_apellido | Segundo apellido | texto | no | Extensión de CL Core |
| sexo | Sexo administrativo | código | sí | `female`, `male`, `other`, `unknown` |
| fecha_nacimiento | Fecha de nacimiento | fecha | sí | |
| fecha_hora_control | Momento del control | fecha y hora | sí | |
| perimetro_cefalico | Perímetro cefálico | número | sí | cm (LOINC 9843-4) |
| imc | Índice de masa corporal | número | sí | kg/m2 (LOINC 39156-5) |
