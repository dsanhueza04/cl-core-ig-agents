"""Banco de errores inyectados sobre la guía de referencia (examples/demo/gold).

Cada caso cambia UN texto exacto de un archivo FSH para producir un error conocido. Sirve para medir
qué errores repara el modelo y cuáles debe resolver el código. `etapa` es una hipótesis (dónde debería
detectarse el error); la medición registra la etapa observada.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GOLD = Path("examples/demo/gold")

AMB = "ejemplos.fsh"
PER = "perfiles.fsh"


@dataclass(frozen=True)
class Caso:
    nombre: str
    descripcion: str
    etapa: str          # precheck | sushi | publisher (hipótesis)
    archivo: str
    buscar: str
    reemplazar: str
    reservado: bool = False   # caso reservado: NO se escribió ninguna regla mirándolo


CASOS: dict[str, Caso] = {c.nombre: c for c in [
    Caso("parent_con_typo", "El Parent apunta a un perfil de CL Core que no existe", "precheck", PER,
         "cl-core-signos-vitales", "cl-core-signo-vitales"),
    Caso("codigo_en_codesystem_equivocado", "Código de identificador que no existe en el CodeSystem", "precheck", AMB,
         "$CSDNI#NNCHL", "$CSDNI#01"),
    Caso("alias_indefinido", "Alias que no está declarado ($LOINC en vez de $LNC)", "sushi", PER,
         "* code = $LNC#85354-9", "* code = $LOINC#85354-9"),
    Caso("regla_sin_espacios", "Regla de asignación sin espacios alrededor de '='", "sushi", PER,
         "* code = $LNC#85354-9", "* code=$LNC#85354-9"),
    Caso("slice_mal_escrito", "Nombre de slice con typo en el ejemplo (diastolico)", "sushi", AMB,
         "* component[diastolica].code = $LNC#8462-4", "* component[diastolico].code = $LNC#8462-4"),
    Caso("valor_sin_unidad", "Cantidad sin unidad (solo el número)", "sushi", AMB,
         "128 'mm[Hg]' \"mmHg\"", "128"),
    Caso("unidad_distinta_al_perfil", "Unidad del ejemplo distinta a la fijada en el perfil (kPa vs mm[Hg])", "sushi", AMB,
         "128 'mm[Hg]' \"mmHg\"", "128 'kPa' \"kPa\""),
    Caso("codigo_ejemplo_distinto", "El code del ejemplo contradice el patrón fijo del perfil", "sushi", AMB,
         "* code = $LNC#85354-9", "* code = $LNC#8480-6"),
    Caso("falta_componente_obligatorio", "El ejemplo omite la diastólica (slice 1..1)", "publisher", AMB,
         "* component[diastolica].code = $LNC#8462-4\n* component[diastolica].valueQuantity = 82 'mm[Hg]' \"mmHg\"\n", ""),
    Caso("referencia_a_tipo_no_permitido", "subject apunta a una Observation en vez de un Patient", "publisher", AMB,
         "* subject = Reference(PacienteDemo)", "* subject = Reference(PresionArterialDemo)"),
    Caso("fecha_con_formato_invalido", "effectiveDateTime que no es ISO 8601", "publisher", AMB,
         "\"2026-03-15T09:30:00-03:00\"", "\"15-03-2026\""),
    Caso("estado_fuera_del_valueset", "status con un código que no existe en el ValueSet obligatorio", "publisher", AMB,
         "* status = #final", "* status = #definitivo"),
]}

# --- Segundo lote: se midieron como RESERVADOS (0/8, ver docs/EXPERIMENTOS.md, experimento 10) y después se
# usaron para escribir reglas, así que ya son casos de desarrollo. Los reservados nuevos están más abajo. ---
SEGUNDO_LOTE = [
    Caso("ucum_invalido", "Código UCUM que no existe (mmHg en vez de mm[Hg])", "publisher", PER,
         '* component[sistolica].valueQuantity.code = #"mm[Hg]"', '* component[sistolica].valueQuantity.code = #"mmHg"', False),
    Caso("genero_en_espanol", "gender con un código en español (femenino)", "publisher", AMB,
         "* gender = #female", "* gender = #femenino", False),
    Caso("categoria_sin_guion", "Categoría de signos vitales mal escrita (vitalsigns)", "publisher", AMB,
         "$ObsCat#vital-signs", "$ObsCat#vitalsigns", False),
    Caso("referencia_a_instancia_inexistente", "subject apunta a una instancia con el nombre mal escrito", "sushi", AMB,
         "* subject = Reference(PacienteDemo)", "* subject = Reference(PacienteDemos)", False),
    Caso("fecha_nacimiento_imposible", "Fecha de nacimiento que no existe (31 de junio)", "publisher", AMB,
         '* birthDate = "1975-06-12"', '* birthDate = "1975-06-31"', False),
    Caso("id_con_guion_bajo", "Id del perfil con guion bajo (no cumple el formato de id de FHIR)", "sushi", PER,
         "Id: cl-presion-arterial", "Id: cl_presion_arterial", False),
    Caso("title_sin_comillas", "Title sin comillas", "sushi", PER,
         'Title: "Presión arterial (demo)"', "Title: Presión arterial (demo)", False),
    Caso("instancia_duplicada", "Dos instancias con el mismo nombre", "sushi", AMB,
         "Instance: PresionArterialDemo", "Instance: PacienteDemo", False),
]
CASOS.update({c.nombre: c for c in SEGUNDO_LOTE})

# --- Casos RESERVADOS (tercer lote): escritos después de las reglas del segundo lote y sin ninguna regla
# pensada para ellos. Sirven para saber si las reglas generalizan. Si se escribe una regla mirándolos, hay que
# registrar antes el resultado en docs/EXPERIMENTOS.md y crear casos reservados nuevos. ---
RESERVADOS = [
    Caso("parent_en_mayusculas", "Parent con las mayúsculas cambiadas (CL-Core-Signos-Vitales)", "precheck", PER,
         "cl-core-signos-vitales", "CL-Core-Signos-Vitales", True),
    Caso("estado_capitalizado", "status con mayúscula inicial (#Final)", "publisher", AMB,
         "* status = #final", "* status = #Final", True),
    Caso("fecha_sin_zona_horaria", "effectiveDateTime con hora pero sin T ni zona horaria", "sushi", AMB,
         '"2026-03-15T09:30:00-03:00"', '"2026-03-15 09:30"', True),
    Caso("display_sin_comillas", "Texto de la unidad sin comillas", "sushi", AMB,
         "82 'mm[Hg]' \"mmHg\"", "82 'mm[Hg]' mmHg", True),
    Caso("instanceof_con_typo", "InstanceOf apunta a un perfil con el nombre mal escrito", "sushi", AMB,
         "InstanceOf: CLPresionArterial", "InstanceOf: CLPresionArteral", True),
    Caso("usage_sin_numeral", "Usage sin el # (example en vez de #example)", "sushi", AMB,
         "diastólica 82 mmHg.\"\nUsage: #example", "diastólica 82 mmHg.\"\nUsage: example", True),
    Caso("alias_en_plural", "Alias casi igual a uno declarado ($ObsCats)", "sushi", AMB,
         "$ObsCat#vital-signs", "$ObsCats#vital-signs", True),
]
CASOS.update({c.nombre: c for c in RESERVADOS})


def aplicar(caso: Caso, out: Path, src: Path = GOLD) -> Path:
    """Copia el IG de referencia a `out` y le inyecta el error. Devuelve `out`."""
    import shutil
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out, ignore=shutil.ignore_patterns("output", "temp", "fsh-generated", "input-cache"))
    f = out / "input" / "fsh" / caso.archivo
    texto = f.read_text(encoding="utf-8")
    if texto.count(caso.buscar) != 1:
        raise ValueError(f"{caso.nombre}: el texto a reemplazar aparece {texto.count(caso.buscar)} veces en {caso.archivo}")
    f.write_text(texto.replace(caso.buscar, caso.reemplazar, 1), encoding="utf-8")
    return out
