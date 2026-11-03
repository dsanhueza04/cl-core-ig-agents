# Páginas, menú y orden: qué controla el libro

Actualizado 2026-10-21. Detalle de uso en `docs/LIBRO.md` (sección «Páginas, menú, imágenes y páginas generadas»).

## Lo que el libro controla
- Páginas de texto (hoja Documentación), con el texto en la celda o en un archivo `paginas/*.md`; orden: `inicio`, `requisitos`, luego el orden de las filas.
- Páginas dentro de páginas (columna «Página padre»).
- Menú superior completo (hoja Menú): páginas, enlaces externos, declaraciones de capacidades, un nivel de desplegables.
- Página Must Support generada desde las marcas del libro; página Historial de cambios generada desde la hoja Cambios.
- Imágenes de la carpeta `imagenes/`.
- Versión de CL Core: columna «dependencias» de la hoja Guía (`hl7.fhir.cl.clcore#1.9.4`) reemplaza la versión por defecto 1.9.3.

## Lo que sigue fijo
- FHIR R4 (4.0.1), `releaseLabel` ci-build, jurisdicción Chile.
- La página Artefactos la genera el IG Publisher.
- Sin logos en el encabezado, tema ni CSS propios.

## Comprobado y pendiente
- Comprobado: SUSHI 3.20.1 acepta las páginas anidadas y el menú con desplegable; las pruebas automáticas cubren la generación.
- Pendiente: una construcción completa con el IG Publisher que muestre el desplegable, las imágenes y la dependencia 1.9.4.
