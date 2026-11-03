# Casos de medición

Cada carpeta tiene una especificación (`spec.md`, la entrada del analista) y su ficha de referencia (`spec.json`,
escrita a mano, contra la que `scripts/medir.py` compara la estructura).

| Grupo | Casos | Uso |
|---|---|---|
| Desarrollo | `frecuencia-cardiaca`, `saturacion-oxigeno`, `peso-talla` | Sus fallos sirvieron para diseñar validaciones y normalizaciones (`docs/EXPERIMENTOS.md`). |
| Reservados | `frecuencia-respiratoria`, `crecimiento-infantil`, `oxigenoterapia` | No se usaron para diseñar nada: sirven para medir si lo hecho generaliza. |

Regla: si un caso reservado llega a inspirar un cambio, pasa a "desarrollo" y se escribe uno nuevo. Todos son sintéticos y
escritos para este proyecto (sin datos de personas ni material de terceros). Los códigos LOINC son los del ValueSet de
signos vitales de CL Core 1.9.3.
