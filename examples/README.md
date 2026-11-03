# Ejemplos

Cada carpeta tiene su propio README. Todos usan datos inventados, salvo el de códigos territoriales (ver más abajo). Los comandos se ejecutan desde la raíz del repositorio; en Windows con cmd usa `\` en las rutas.

## Empieza aquí

| Carpeta | Qué muestra | Cómo probarlo |
|---|---|---|
| [`libro-con-paginas/`](libro-con-paginas/) | Una guía pequeña con **texto en archivos `.md`, menú con desplegable, página Must Support generada e historial de cambios**. Es la mejor primera mirada a lo que produce la herramienta. | `python cl_ig.py revisar examples/libro-con-paginas/libro-con-paginas.xlsx` |
| [`libro-demo/`](libro-demo/) | Perfiles con extensiones y slices, terminología y ejemplos, sin páginas. Sirve de referencia de las hojas de datos. | `python cl_ig.py revisar examples/libro-demo/libro-demo.xlsx` |

## Aprender cómo se escribe

| Carpeta | Qué muestra |
|---|---|
| [`ejercicio-1-presion-arterial/`](ejercicio-1-presion-arterial/) | Un ejercicio resuelto (control de presión arterial): cada fila del libro explicada con el FSH que produce. Para entender cómo una hoja se convierte en FHIR. |

## Pruebas de alcance

| Carpeta | Qué muestra |
|---|---|
| [`prueba-reconstruccion/`](prueba-reconstruccion/) | Si CL Core no existiera, ¿se podría escribir en el Excel un perfil como `CorePacienteCl`? Reconstruye el perfil sin heredar de CL Core y lo compara regla por regla con el paquete público (que debes descargar aparte). |

## Datos reales para tu propia guía

| Carpeta | Qué muestra |
|---|---|
| [`datos-territoriales-chile/`](datos-territoriales-chile/) | Regiones, provincias y comunas de Chile con su código territorial, listas para cargar con `python cl_ig.py importar-codigos`. Parte de una tabla oficial de la administración pública, actualizada a mano: revisa los nombres contra la fuente vigente antes de publicar. |

## Camino con modelo de lenguaje (opcional y experimental)

Estos ejemplos son para el segundo camino del proyecto, el que parte de una especificación en texto y hoy cubre solo observaciones de signos vitales (ver el README principal).

| Carpeta | Qué muestra |
|---|---|
| [`demo/`](demo/) | Una especificación de presión arterial (`spec.md`, `spec.json`) y la guía de referencia (`gold/`) contra la que se compara lo generado. |
| [`casos/`](casos/) | Seis especificaciones (frecuencia cardíaca, saturación de oxígeno, peso y talla, y otras) con su ficha de referencia, usadas para medir el camino con modelo. |

## ¿Cuál abro primero?

- **Quiero ver qué hace la herramienta:** `libro-con-paginas`.
- **Quiero escribir mi primera guía:** `docs/kit/PRIMERA-GUIA.md` y, si te trabas, `ejercicio-1-presion-arterial`.
- **Quiero cargar una lista larga de códigos:** `datos-territoriales-chile`.
- **Me interesa la parte de IA:** `demo`, y luego `casos`.
