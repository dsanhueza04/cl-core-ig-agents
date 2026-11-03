# Guía con páginas, menú y páginas generadas

Un libro pequeño (`libro-con-paginas.xlsx`) que usa lo que el libro de Excel permite para el texto de una guía:

- **Documentación**: `generalidades` y `objetivos` leen su texto de `paginas/*.md` (celda `@paginas/objetivos.md`); `objetivos` va dentro de `generalidades` (columna «Página padre»).
- **Menú**: Inicio, Generalidades, Must Support, un desplegable «Declaraciones» con la declaración del servidor, Artefactos e Historial de cambios. Un enlace externo (por ejemplo a `https://hl7.org/fhir/R4`) es opcional: se agrega como una fila más con ese destino.
- **Must Support** y **Historial de cambios**: las genera la herramienta (destinos `must-support` y `cambios` del menú).

Para probarlo, desde la raíz del kit:

```
python cl_ig.py revisar examples\libro-con-paginas\libro-con-paginas.xlsx
python cl_ig.py construir examples\libro-con-paginas\libro-con-paginas.xlsx --sin-docker
```

Sin `--sin-docker` también valida con SUSHI y el IG Publisher (con Docker abierto). Las imágenes van en una carpeta `imagenes\` junto al libro y se usan en una página como `![texto](logo.png)`.
