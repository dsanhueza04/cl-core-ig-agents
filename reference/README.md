# reference/

Carpeta de material de referencia **no versionado** (todo lo demás de esta carpeta está en `.gitignore`).

Coloca aquí, sin subirlo al repositorio:

```
reference/
└── clcore-1.9.3/
    └── site/
        └── package.tgz      # paquete oficial hl7.fhir.cl.clcore 1.9.3
```

`python cl_ig.py catalogo` y el contenedor de validación leen `reference/clcore-1.9.3/site/package.tgz`.
Ver `docs/LICENCIAS.md` para el motivo de no redistribuirlo.

## Dónde conseguir el paquete

En el sitio publicado de CL Core (<https://hl7chile.cl/fhir/ig/clcore/>), en la sección de descargas de la versión 1.9.3; el archivo se llama `package.tgz`. Guárdalo en la ruta de arriba y ejecuta `python cl_ig.py catalogo`.
