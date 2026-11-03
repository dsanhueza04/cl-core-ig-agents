### Demo: registro de presión arterial sobre CL Core

Este IG es una **demostración mínima**. Reutiliza dos perfiles de [CL Core 1.9.3](https://hl7chile.cl/fhir/ig/clcore/): `CorePacienteCl` para el paciente y `cl-core-signos-vitales` como base de la medición.

#### Qué define

- [Presión arterial (demo)](StructureDefinition-cl-presion-arterial.html): panel LOINC `85354-9` con presión sistólica (`8480-6`) y diastólica (`8462-4`) obligatorias, en mmHg.
- Ejemplos con datos sintéticos: [paciente](Patient-PacienteDemo.html) y [medición](Observation-PresionArterialDemo.html).

#### Alcance

Los datos de los ejemplos son ficticios y no corresponden a ninguna persona real. El contenido no es una guía clínica.

Ver todos los artefactos en la página de [artefactos](artifacts.html).
