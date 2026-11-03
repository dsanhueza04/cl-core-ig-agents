# Especificación de entrada (caso reservado): oxigenoterapia

Diccionario de datos de ejemplo, escrito para este proyecto. Caso reservado: no se usó para diseñar reglas, solo para medir.

## Observaciones

Se registran **tres observaciones independientes** de signos vitales, cada una de valor único (no forman un panel):

- **Saturación de oxígeno en sangre arterial, código LOINC `2708-6`**, en porcentaje (`%`; código UCUM `%`).
- **Flujo de oxígeno inhalado, código LOINC `3151-8`**, en litros por minuto (`L/min`; código UCUM `L/min`).
- **Concentración de oxígeno inhalado, código LOINC `3150-0`**, en porcentaje (`%`; código UCUM `%`).

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
| sat_arterial | Saturación arterial de oxígeno | número | sí | % (LOINC 2708-6) |
| flujo_o2 | Flujo de oxígeno inhalado | número | sí | L/min (LOINC 3151-8) |
| fio2 | Concentración de oxígeno inhalado | número | sí | % (LOINC 3150-0) |
