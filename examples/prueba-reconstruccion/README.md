# Prueba de reconstrucción: Paciente sin heredar de CL Core

Pregunta: *si CL Core no existiera, ¿se podría haber escrito en este Excel un perfil como `CorePacienteCl`?*

- `datos.py` escribe el perfil `PacienteReconstruido` partiendo de `Patient` base (**Perfil padre vacío**, **Usar CL Core = No**),
  con las mismas extensiones, slices (`NombreOficial`, `NombreSocial`), bindings y valores fijos del original.
  `python datos.py` genera `prueba-reconstruccion.xlsx`.
- `comparar.py` lee el `StructureDefinition-CorePacienteCl.json` del paquete público CL Core 1.9.3 y compara regla por regla.

```
python comparar.py ruta/a/StructureDefinition-CorePacienteCl.json
```

## Resultado

Con las columnas **Resumen / Definición / Comentario**, **Debe seguir el perfil**, **Puede apuntar a**, los perfiles de tipos de dato
(`Recurso base = Address`) y las extensiones ya definidas en otro paquete (**Ya existe en (URL)**), el Excel reproduce todas las reglas
estructurales de dos perfiles reales de CL Core 1.9.3: `CorePacienteCl` (Patient) y `cl-address` (Address).

| Brecha | Estado |
|---|---|
| Textos por elemento (`short`, `definition`, `comment`) | Cerrada: columnas nuevas. `datos.py` escribe textos propios solo en algunos elementos, a propósito (no se copian los de CL Core). |
| Destino de referencia (`generalPractitioner`) | Cerrada: «Puede apuntar a». |
| Perfil de un tipo de dato (`address` → `cl-address`) | Cerrada: se pueden definir (`DireccionCl`, sobre `Address`) y usar. |
| Extensión de otro paquete (`geolocation`) | Cerrada: «Ya existe en (URL)». |

La comparación es a nivel de reglas del libro; el differential compilado lo confirma SUSHI (`python cl_ig.py construir`).
