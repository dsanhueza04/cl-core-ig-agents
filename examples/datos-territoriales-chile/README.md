# Códigos territoriales de Chile (regiones, provincias y comunas)

Tres CSV (separados por «;», se abren en dos columnas en Excel en español: A = código, B = texto; el mismo contenido está en `datos-territoriales-chile.xlsx`) listos para `python cl_ig.py importar-codigos`: 16 regiones, 56 provincias y 346 comunas, con el Código Único Territorial (CUT).

- **Origen:** tabla «Código Único Territorial, región-provincia-comuna» (PDF oficial de la administración pública chilena). Ese PDF es anterior a los cambios territoriales recientes, así que se actualizó a mano:
  - Región de Ñuble (16): provincias Diguillín, Itata y Punilla, con sus 21 comunas y códigos nuevos (antes era la provincia 084 de Biobío).
  - Provincia de Marga Marga (058): Quilpué, Limache, Olmué y Villa Alemana (antes en Valparaíso y Quillota).
  - Se corrigieron tildes (Los Álamos, Los Ángeles) y los nombres que el PDF partía en dos líneas.
- **Verificación:** los códigos coinciden uno a uno con los de CL Core 1.9.3 (16, 56 y 346), solo cotejando códigos; los nombres son los oficiales, no los de CL Core.
- Revisa los nombres contra la fuente vigente antes de publicar una guía.

Ejemplo:

```
python cl_ig.py importar-codigos mi-libro.xlsx examples/datos-territoriales-chile/comunas.csv --codesystem CSComunas --titulo "Comunas de Chile"
```
