"""Esquema de la plantilla de Excel: una sola fuente de verdad para la plantilla, el lector y el verificador.

Cada hoja es una tabla: fila 1 título, fila 2 ayuda, fila 3 estado de cada columna (Obligatorio / Recomendado /
Opcional), fila 4 encabezados y datos desde la fila 5. La hoja `Guía` es una tabla de campos (Campo | Valor).
"""
from __future__ import annotations

from dataclasses import dataclass, replace

OBLIGATORIO, RECOMENDADO, OPCIONAL = "Obligatorio", "Recomendado", "Opcional"
FILA_ESTADO, FILA_ENCABEZADO, PRIMERA_FILA = 3, 4, 5

SI_NO = ["Sí", "No"]
TIPOS_VALOR = ["texto", "código simple", "código con sistema", "número", "cantidad", "booleano", "fecha",
               "fecha y hora", "referencia", "recurso incluido"]
TIPOS_FIJO = ["texto", "código simple", "código con sistema", "número", "booleano"]
FUERZAS = ["required", "extensible", "preferred", "example"]
USOS = ["ejemplo", "definición"]
CONTENIDOS = ["complete", "fragment", "not-present", "example"]
ESTADOS_GUIA = ["draft", "active", "retired"]
# Tipos de valor que puede llevar una extensión simple (los que la hoja Valores sabe escribir).
TIPOS_EXTENSION = ["string", "code", "Coding", "CodeableConcept", "boolean", "integer", "decimal", "date", "dateTime",
                   "Quantity", "Reference", "uri", "Identifier", "Period", "Range", "Ratio", "ContactPoint",
                   "HumanName", "Address", "Annotation", "Attachment"]
DISCRIMINADORES = ["value", "pattern", "type", "exists", "profile"]
REGLAS_SLICING = ["open", "closed", "openAtEnd"]
MODOS_INCLUSION = ["incluir", "excluir"]
# CapabilityStatement: lo que un servidor ofrece o un cliente espera usar.
MODOS_CAPACIDAD = ["server", "client"]
INTERACCIONES = ["read", "vread", "update", "patch", "delete", "history-instance", "history-type", "create", "search-type"]
EXPECTATIVAS = ["SHALL", "SHOULD", "MAY", "SHOULD-NOT"]     # extensión estándar capabilitystatement-expectation
EQUIVALENCIAS = ["relatedto", "equivalent", "equal", "wider", "subsumes", "narrower", "specializes", "inexact", "unmatched", "disjoint"]
USOS_PARAMETRO = ["in", "out"]
TIPOS_OPERACION = ["operation", "query"]
POLITICAS_REFERENCIA = ["literal", "logical", "resolves", "enforced", "local"]
OPERACIONES_SERVIDOR = ["transaction", "batch", "search-system", "history-system"]
MODIFICADORES_BUSQUEDA = ["missing", "exact", "contains", "not", "text", "in", "not-in", "below", "above", "type", "identifier", "ofType"]
TIPOS_BUSQUEDA = ["number", "date", "string", "token", "reference", "composite", "quantity", "uri", "special"]
TIPOS_PREGUNTA = ["group", "display", "boolean", "decimal", "integer", "date", "dateTime", "time", "string", "text", "url", "choice",
                  "open-choice", "attachment", "reference", "quantity"]
GRAVEDADES = ["error", "warning"]
OPERADORES_CONDICION = ["exists", "=", "!=", ">", "<", ">=", "<="]
# Filtros de ValueSet sobre la propiedad «concept» (jerarquías como las de SNOMED). `regex`, `in` y `not-in` llevan texto.
FILTROS_VS = ["is-a", "descendent-of", "is-not-a", "generalizes", "regex", "in", "not-in"]
FILTROS_DE_TEXTO = ["regex", "in", "not-in"]

# Tipos de dato sobre los que se puede crear un perfil (por ejemplo una dirección chilena sobre Address).
TIPOS_DATO = ["Address", "Annotation", "Attachment", "CodeableConcept", "Coding", "ContactPoint", "HumanName", "Identifier",
              "Period", "Quantity", "Range", "Ratio", "Reference"]

# Recursos base de FHIR R4 (se ofrecen en la lista desplegable; sirven también para detectar erratas).
RECURSOS_R4 = """Account ActivityDefinition AdverseEvent AllergyIntolerance Appointment AppointmentResponse AuditEvent Basic
Binary BiologicallyDerivedProduct BodyStructure Bundle CapabilityStatement CarePlan CareTeam CatalogEntry ChargeItem
ChargeItemDefinition Claim ClaimResponse ClinicalImpression CodeSystem Communication CommunicationRequest
CompartmentDefinition Composition ConceptMap Condition Consent Contract Coverage CoverageEligibilityRequest
CoverageEligibilityResponse DetectedIssue Device DeviceDefinition DeviceMetric DeviceRequest DeviceUseStatement
DiagnosticReport DocumentManifest DocumentReference EffectEvidenceSynthesis Encounter Endpoint EnrollmentRequest
EnrollmentResponse EpisodeOfCare EventDefinition Evidence EvidenceVariable ExampleScenario ExplanationOfBenefit
FamilyMemberHistory Flag Goal GraphDefinition Group GuidanceResponse HealthcareService ImagingStudy Immunization
ImmunizationEvaluation ImmunizationRecommendation ImplementationGuide InsurancePlan Invoice Library Linkage List
Location Measure MeasureReport Media Medication MedicationAdministration MedicationDispense MedicationKnowledge
MedicationRequest MedicationStatement MedicinalProduct MedicinalProductAuthorization MedicinalProductContraindication
MedicinalProductIndication MedicinalProductIngredient MedicinalProductInteraction MedicinalProductManufactured
MedicinalProductPackaged MedicinalProductPharmaceutical MedicinalProductUndesirableEffect MessageDefinition
MessageHeader MolecularSequence NamingSystem NutritionOrder Observation ObservationDefinition OperationDefinition
OperationOutcome Organization OrganizationAffiliation Parameters Patient PaymentNotice PaymentReconciliation Person
PlanDefinition Practitioner PractitionerRole Procedure Provenance Questionnaire QuestionnaireResponse RelatedPerson
RequestGroup ResearchDefinition ResearchElementDefinition ResearchStudy ResearchSubject RiskAssessment
RiskEvidenceSynthesis Schedule SearchParameter ServiceRequest Slot Specimen SpecimenDefinition StructureDefinition
StructureMap Subscription Substance SubstancePolymer SubstanceProtein SubstanceReferenceInformation
SubstanceSourceMaterial SubstanceSpecification SubstanceNucleicAcid SupplyDelivery SupplyRequest Task
TerminologyCapabilities TestReport TestScript ValueSet VerificationResult VisionPrescription""".split()

SISTEMAS_CONOCIDOS = {
    "LOINC": "http://loinc.org",
    "SNOMED": "http://snomed.info/sct",
    "UCUM": "http://unitsofmeasure.org",
    "CIE-10": "http://hl7.org/fhir/sid/icd-10",
}


@dataclass(frozen=True)
class Col:
    clave: str
    etiqueta: str
    estado: str
    ayuda: str
    opciones: tuple[str, ...] | None = None
    # lista desplegable alimentada por otra hoja: (hoja, clave de columna)
    desde: tuple[str, str] | None = None
    ancho: int = 22
    avanzada: bool = False        # columna agrupada y cerrada por defecto en la plantilla


@dataclass(frozen=True)
class Hoja:
    nombre: str
    titulo: str
    ayuda: str
    columnas: tuple[Col, ...]


GUIA_CAMPOS = (
    Col("id", "Identificador corto", OBLIGATORIO, "Solo minúsculas, números y guiones. Ej.: control-prenatal. Es el id de la guía."),
    Col("titulo", "Título", OBLIGATORIO, "Nombre legible de la guía. Ej.: Control prenatal."),
    Col("descripcion", "Descripción", RECOMENDADO, "Para qué sirve la guía y a quién va dirigida (2 o 3 frases)."),
    Col("canonical", "URL canónica", RECOMENDADO,
        "Dirección base permanente de tu guía. Ej.: https://miorganizacion.cl/fhir/ig/control-prenatal. Si la dejas vacía se usa una provisional."),
    Col("version", "Versión", RECOMENDADO, "Por defecto 0.1.0."),
    Col("estado", "Estado", RECOMENDADO, "draft, active o retired. Por defecto draft.", tuple(ESTADOS_GUIA)),
    Col("publicador", "Publicador", RECOMENDADO, "Persona u organización que publica la guía."),
    Col("contacto", "Contacto", OPCIONAL, "Correo o sitio web de contacto."),
    Col("licencia", "Licencia", OPCIONAL, "Código SPDX. Por defecto CC0-1.0."),
    Col("idioma", "Idioma de los textos", OPCIONAL, "Código del idioma en que escribes los textos y nombres de códigos. Por defecto es (español)."),
    Col("usa_clcore", "Usar CL Core 1.9.3", RECOMENDADO, "Sí si tus perfiles parten de perfiles de CL Core (Paciente, Observación, etc.).", tuple(SI_NO)),
    Col("dependencias", "Otras dependencias", OPCIONAL, "Paquetes FHIR extra, uno por línea, con formato paquete#versión."),
)

HOJAS: tuple[Hoja, ...] = (
    Hoja("Perfiles", "Perfiles", "Un perfil es un recurso FHIR (Patient, Observation...) con reglas más estrictas para tu caso. Una fila por perfil.", (
        Col("nombre", "Nombre del perfil", OBLIGATORIO, "Sin espacios, empieza con mayúscula. Ej.: ControlPrenatal."),
        Col("recurso", "Recurso base", OBLIGATORIO,
            "El recurso FHIR sobre el que se construye (Patient...). También puede ser un tipo de dato (Address, HumanName...) para crear, por ejemplo, una dirección propia.",
            tuple(RECURSOS_R4) + tuple(TIPOS_DATO)),
        Col("padre", "Perfil padre", OPCIONAL, "Si parte de otro perfil (de esta hoja o de CL Core, ej.: CorePacienteCl). Vacío = parte del recurso base."),
        Col("titulo", "Título", RECOMENDADO, "Nombre legible."),
        Col("descripcion", "Descripción", RECOMENDADO, "Qué representa y cuándo se usa.", ancho=45),
        Col("justificacion", "Justificación", OPCIONAL, "Por qué se tomaron estas decisiones. Va a la documentación.", ancho=45, avanzada=True),
    )),
    Hoja("Elementos", "Restricciones de cada perfil",
         "Una fila por elemento que quieras restringir: cardinalidad (mín/máx), obligatorio de implementar, tipo, valores permitidos o valor fijo.", (
        Col("perfil", "Perfil", OBLIGATORIO, "Elige uno de la hoja Perfiles.", desde=("Perfiles", "nombre")),
        Col("ruta", "Elemento (ruta)", OBLIGATORIO, "Ruta sin el nombre del recurso. Ej.: identifier, name.family, value[x]."),
        Col("min", "Mín", RECOMENDADO, "Mínimo de repeticiones: 0, 1, 2... 1 significa obligatorio.", ancho=8),
        Col("max", "Máx", RECOMENDADO, "Máximo de repeticiones: un número o * (sin límite). 0 prohíbe el elemento.", ancho=8),
        Col("ms", "Must Support", OPCIONAL, "Sí si quien implemente debe soportar este elemento.", tuple(SI_NO), ancho=12),
        Col("valueset", "ValueSet permitido", OPCIONAL, "Un ValueSet de la hoja ValueSets, de CL Core, o una URL.", desde=("ValueSets", "nombre")),
        Col("fuerza", "Fuerza", OPCIONAL, "required = solo esos valores; extensible = esos, salvo que no calce; preferred y example = sugerencia.", tuple(FUERZAS), ancho=14),
        Col("resumen", "Resumen", OPCIONAL, "Una línea que explica el elemento. Aparece en las tablas de la guía.", ancho=30),
        Col("definicion", "Definición", OPCIONAL, "Qué es este elemento en tu guía, con más detalle.", ancho=40),
        Col("tipo", "Solo tipo", OPCIONAL, "Limita el tipo de dato. Ej.: Quantity, string, Reference(Patient).", ancho=24, avanzada=True),
        Col("fijo", "Valor fijo", OPCIONAL, "El elemento siempre debe tener este valor.", avanzada=True),
        Col("fijo_tipo", "Tipo del valor fijo", OPCIONAL, "Cómo interpretar el valor fijo.", tuple(TIPOS_FIJO), avanzada=True),
        Col("fijo_sistema", "Sistema del valor fijo", OPCIONAL, "Solo para 'código con sistema': LOINC, SNOMED, un CodeSystem de tu libro o una URL.", avanzada=True),
        Col("fijo_texto", "Texto del código fijo", OPCIONAL, "Solo para 'código con sistema': el texto (display) que acompaña al código.", avanzada=True),
        Col("fijo_exacto", "Valor exacto", OPCIONAL, "Sí = el valor debe ser exactamente ese (fixed); vacío = debe contenerlo (pattern).", ("Sí", "No"), avanzada=True),
        Col("perfil_tipo", "Debe seguir el perfil", OPCIONAL,
            "El dato debe cumplir este perfil (de la hoja Perfiles, de CL Core o una URL). Ej.: cl-address para address.", ancho=24, avanzada=True),
        Col("destinos", "Puede apuntar a", OPCIONAL,
            "Solo para referencias: perfiles o recursos permitidos, separados por coma. Ej.: Practitioner, CorePrestadorCl.", ancho=30, avanzada=True),
        Col("comentario", "Comentario", OPCIONAL, "Aclaraciones para quien implemente: cuándo omitirlo, cómo llenarlo.", ancho=40, avanzada=True),
        Col("justificacion", "Justificación", OPCIONAL, "Por qué esta regla.", ancho=40, avanzada=True),
    )),
    Hoja("Extensiones", "Extensiones propias",
         "Una extensión agrega un dato que el recurso base no tiene. Una fila por extensión; para una extensión compleja, agrega una fila por cada parte "
         "indicando en «Es parte de» el nombre de la extensión. Luego úsala en «Elementos» con la ruta que muestra la columna gris.", (
        Col("nombre", "Nombre de la extensión", OBLIGATORIO, "Sin espacios, empieza con mayúscula. Ej.: AniosEscolaridad."),
        Col("titulo", "Título", RECOMENDADO, "Nombre legible."),
        Col("descripcion", "Descripción", RECOMENDADO, "Qué dato agrega y cuándo se usa.", ancho=45),
        Col("contexto", "Se usa en", RECOMENDADO, "Recurso(s) donde se puede usar, separados por coma. Ej.: Patient, Observation. También un elemento: Patient.address.",
            ancho=24),
        Col("tipo", "Tipo del valor", RECOMENDADO, "Qué tipo de dato guarda. Vacío si la extensión tiene partes (es compleja). Ej.: string, CodeableConcept, Reference(Patient).",
            tuple(TIPOS_EXTENSION), ancho=20),
        Col("valueset", "ValueSet permitido", OPCIONAL, "Solo para code, Coding o CodeableConcept.", desde=("ValueSets", "nombre")),
        Col("fuerza", "Fuerza", OPCIONAL, "required = solo esos valores; extensible; preferred; example.", tuple(FUERZAS), ancho=14),
        Col("parte_de", "Es parte de", OPCIONAL, "Si esta fila es una parte de una extensión compleja, el nombre de esa extensión.", desde=("Extensiones", "nombre")),
        Col("codigo_parte", "Nombre exacto de la parte", OPCIONAL, "Solo para partes: cómo se escribe el nombre de la parte dentro de la extensión, si no es el nombre con minúscula inicial (ej.: Contactado).", ancho=22),
        Col("min", "Mín", OPCIONAL, "Solo para partes. Por defecto 0.", ancho=8),
        Col("max", "Máx", OPCIONAL, "Solo para partes: un número o *. Por defecto 1.", ancho=8),
        Col("ms", "Must Support", OPCIONAL, "Solo para partes: Sí si los sistemas deben soportar esta parte.", ("Sí", "No"), ancho=10),
        Col("url", "Ya existe en (URL)", OPCIONAL,
            "Si la extensión ya está definida en otro paquete (por ejemplo http://hl7.org/fhir/StructureDefinition/geolocation), pon aquí su URL y deja el resto vacío. No se vuelve a definir.",
            ancho=40),
    )),
    Hoja("ValorExtensiones", "Reglas sobre el valor de una extensión",
         "Para afinar el interior del valor de una extensión (o de una de sus partes) cuando guarda un dato con campos, como un Identifier o un CodeableConcept: "
         "qué campos son obligatorios, qué lista de códigos usan, qué valor fijo llevan. Una fila por campo.", (
        Col("extension", "Extensión o parte", OBLIGATORIO, "Una extensión simple o una parte de una extensión compleja (hoja Extensiones).", desde=("Extensiones", "nombre")),
        Col("ruta", "Campo dentro del valor", OBLIGATORIO, "Ruta dentro del valor. Ej.: system, value, coding.code (para un Identifier o un CodeableConcept). Usa [x] para el valor mismo (su cardinalidad o Must Support)."),
        Col("min", "Mín", RECOMENDADO, "Mínimo de repeticiones: 1 significa obligatorio.", ancho=8),
        Col("max", "Máx", RECOMENDADO, "Máximo de repeticiones: un número o *. 0 prohíbe el campo.", ancho=8),
        Col("ms", "Must Support", OPCIONAL, "Sí si quien implemente debe soportar este campo.", tuple(SI_NO), ancho=12),
        Col("valueset", "ValueSet permitido", OPCIONAL, "Un ValueSet de la hoja ValueSets, de CL Core, o una URL.", desde=("ValueSets", "nombre")),
        Col("fuerza", "Fuerza", OPCIONAL, "required = solo esos valores; extensible; preferred; example.", tuple(FUERZAS), ancho=14),
        Col("fijo", "Valor fijo", OPCIONAL, "El campo siempre debe tener este valor.", avanzada=True),
        Col("fijo_tipo", "Tipo del valor fijo", OPCIONAL, "Cómo interpretar el valor fijo.", tuple(TIPOS_FIJO), avanzada=True),
        Col("fijo_sistema", "Sistema del valor fijo", OPCIONAL, "Solo para 'código con sistema'.", avanzada=True),
        Col("fijo_texto", "Texto del código fijo", OPCIONAL, "Solo para 'código con sistema'.", avanzada=True),
        Col("fijo_exacto", "Valor exacto", OPCIONAL, "Sí = exactamente ese valor (fixed).", ("Sí", "No"), avanzada=True),
    )),
    Hoja("Slices", "Slices (variantes de un elemento)",
         "Un slice separa los distintos usos de un elemento que se repite (por ejemplo, teléfono y correo dentro de telecom). Una fila por slice. "
         "La primera fila de cada elemento dice cómo se distinguen los slices.", (
        Col("perfil", "Perfil", OBLIGATORIO, "Elige uno de la hoja Perfiles.", desde=("Perfiles", "nombre")),
        Col("elemento", "Elemento que se divide", OBLIGATORIO, "Un elemento que se repite. Ej.: telecom, identifier, component."),
        Col("slice", "Nombre del slice", OBLIGATORIO, "Una palabra, sin espacios. Ej.: telefono. Úsala en las rutas: telecom[telefono].value."),
        Col("min", "Mín", RECOMENDADO, "Mínimo de repeticiones de este slice. Por defecto 0.", ancho=8),
        Col("max", "Máx", RECOMENDADO, "Máximo: un número o *. Por defecto *.", ancho=8),
        Col("ms", "Must Support", OPCIONAL, "Sí si quien implemente debe soportar este slice.", tuple(SI_NO), ancho=12),
        Col("discriminador", "Se distingue por", RECOMENDADO,
            "Solo en la primera fila del elemento. value/pattern = por un valor; type = por el tipo; exists = por si el campo existe.", tuple(DISCRIMINADORES), ancho=14),
        Col("disc_ruta", "Campo que lo distingue", RECOMENDADO, "Campo dentro del elemento. Ej.: system. Usa $this si es el elemento mismo.", ancho=18),
        Col("ordenado", "Slices en orden", OPCIONAL, "Solo en la primera fila del elemento. Sí = los slices deben aparecer en el orden de la lista; No = sin orden (unordered).", ("Sí", "No"), ancho=12, avanzada=True),
        Col("fijo", "Valor que lo distingue", OPCIONAL, "El valor de ese campo en este slice. Ej.: phone."),
        Col("fijo_tipo", "Tipo del valor", OPCIONAL, "Cómo interpretar el valor.", tuple(TIPOS_FIJO), ancho=18),
        Col("fijo_sistema", "Sistema del valor", OPCIONAL, "Solo para 'código con sistema': LOINC, SNOMED, un CodeSystem de tu libro o una URL."),
        Col("reglas", "Reglas de slicing", OPCIONAL, "open (por defecto) admite otros además de los definidos; closed no; openAtEnd solo al final.", tuple(REGLAS_SLICING), ancho=14,
            avanzada=True),
        Col("descripcion", "Descripción", OPCIONAL, "Para qué sirve este slice.", ancho=40, avanzada=True),
    )),
    Hoja("Instancias", "Ejemplos (instancias)", "Un ejemplo es un recurso concreto con datos ficticios que cumple un perfil. Una fila por ejemplo.", (
        Col("nombre", "Nombre del ejemplo", OBLIGATORIO, "Sin espacios, empieza con mayúscula. Ej.: EjemploControl1."),
        Col("perfil", "Perfil o recurso", OBLIGATORIO, "Perfil de la hoja Perfiles, perfil de CL Core, o un recurso base.", desde=("Perfiles", "nombre")),
        Col("titulo", "Título", RECOMENDADO, "Nombre legible."),
        Col("descripcion", "Descripción", RECOMENDADO, "Qué muestra este ejemplo.", ancho=45),
        Col("uso", "Uso", OPCIONAL, "ejemplo (por defecto) o definición.", tuple(USOS), ancho=14),
        Col("id", "Id del recurso", OPCIONAL, "Cómo se identifica el recurso (Patient/<id>). Si lo dejas vacío se usa el nombre. Complétalo cuando otros recursos lo referencian por ese id.",
            ancho=24, avanzada=True),
    )),
    Hoja("Valores", "Datos de cada ejemplo", "Una fila por dato. Para listas, usa índices en la ruta: name[0].given[0].", (
        Col("instancia", "Ejemplo", OBLIGATORIO, "Elige uno de la hoja Instancias.", desde=("Instancias", "nombre")),
        Col("ruta", "Elemento (ruta)", OBLIGATORIO, "Elige de la lista (según el perfil del ejemplo) o escribe. Ej.: status, subject, name[0].family."),
        Col("tipo", "Tipo de dato", RECOMENDADO, "Cómo escribir el valor. Si lo dejas vacío se deduce del elemento (ver «Tipo sugerido»). 'cantidad' usa Unidad; 'referencia' y 'recurso incluido' usan el nombre de otro ejemplo (el segundo mete el recurso dentro, como en las entradas de un Bundle).", tuple(TIPOS_VALOR), ancho=20),
        Col("valor", "Valor", OBLIGATORIO, "El dato. Fechas: AAAA-MM-DD; fecha y hora: AAAA-MM-DDThh:mm:ss-03:00."),
        Col("sistema", "Sistema", OPCIONAL, "Para 'código con sistema': LOINC, SNOMED, un CodeSystem de tu libro o una URL."),
        Col("unidad", "Unidad (UCUM)", OPCIONAL, "Solo para 'cantidad'. Código UCUM: mm[Hg], kg, %, /min...", ancho=16),
        Col("texto", "Texto visible", OPCIONAL, "Etiqueta legible del código o de la unidad."),
    )),
    Hoja("CodeSystems", "Sistemas de códigos", "Un CodeSystem define códigos propios con su significado. Una fila por sistema.", (
        Col("nombre", "Nombre", OBLIGATORIO, "Sin espacios, empieza con mayúscula. Ej.: CSEstadoControl."),
        Col("titulo", "Título", RECOMENDADO, "Nombre legible."),
        Col("descripcion", "Descripción", RECOMENDADO, "Qué conceptos reúne.", ancho=45),
        Col("contenido", "Contenido", OPCIONAL, "complete = listas todos los códigos (por defecto); not-present = los códigos están definidos en otro lugar.", tuple(CONTENIDOS), ancho=16),
        Col("distingue_mayusculas", "Distingue mayúsculas", OPCIONAL, "Sí (por defecto): «A» y «a» son códigos distintos. No: se tratan como el mismo código.", ("Sí", "No"), ancho=14, avanzada=True),
    )),
    Hoja("Conceptos", "Códigos de cada sistema", "Una fila por código. Un mismo código no puede significar dos cosas en el mismo sistema.", (
        Col("codesystem", "CodeSystem", OBLIGATORIO, "Elige uno de la hoja CodeSystems.", desde=("CodeSystems", "nombre")),
        Col("codigo", "Código", OBLIGATORIO, "Ej.: 1, activo, P12-3."),
        Col("texto", "Texto", OBLIGATORIO, "Cómo se muestra el código."),
        Col("definicion", "Definición", OPCIONAL, "Explicación más larga.", ancho=45),
    )),
    Hoja("ValueSets", "Conjuntos de valores", "Un ValueSet es la lista de códigos permitidos en un elemento. Una fila por ValueSet; su contenido va en la hoja Inclusiones.", (
        Col("nombre", "Nombre", OBLIGATORIO, "Sin espacios, empieza con mayúscula. Ej.: VSEstadoControl."),
        Col("titulo", "Título", RECOMENDADO, "Nombre legible."),
        Col("descripcion", "Descripción", RECOMENDADO, "Qué valores permite.", ancho=45),
    )),
    Hoja("Inclusiones", "Contenido de cada ValueSet",
         "Una fila por regla. Deja Código vacío para incluir todo el sistema; con «Filtro» incluyes una rama (por ejemplo todos los descendientes de un código SNOMED); "
         "con «Excluir» sacas códigos; con «Incluir otro ValueSet» reutilizas uno existente.", (
        Col("valueset", "ValueSet", OBLIGATORIO, "Elige uno de la hoja ValueSets.", desde=("ValueSets", "nombre")),
        Col("sistema", "Sistema", RECOMENDADO, "Un CodeSystem de tu libro, LOINC, SNOMED, o una URL. Puede quedar vacío solo si usas «Incluir otro ValueSet».",
            desde=("CodeSystems", "nombre")),
        Col("codigo", "Código", OPCIONAL, "Vacío = todo el sistema."),
        Col("texto", "Texto del código", OPCIONAL, "Cómo se muestra el código en el ValueSet (opcional; si lo dejas vacío se toma del CodeSystem).", ancho=30, avanzada=True),
        Col("modo", "Incluir o excluir", OPCIONAL, "Por defecto incluir.", tuple(MODOS_INCLUSION), ancho=16),
        Col("filtro", "Filtro", OPCIONAL, "Selecciona códigos por su relación: is-a (el código y sus descendientes), descendent-of (solo descendientes), "
            "is-not-a, generalizes, regex, in, not-in.", tuple(FILTROS_VS), ancho=16),
        Col("filtro_valor", "Valor del filtro", OPCIONAL, "El código de partida (is-a, descendent-of...) o el texto (regex; in y not-in con códigos separados por coma)."),
        Col("filtro_propiedad", "Propiedad del filtro", OPCIONAL, "Por defecto concept (el código mismo en la jerarquía). Otras: code (el texto del código, útil con regex) o una propiedad propia del sistema.", ancho=16, avanzada=True),
        Col("otro_valueset", "Incluir otro ValueSet", OPCIONAL, "Reutiliza los códigos de un ValueSet de tu libro, de CL Core o una URL.", desde=("ValueSets", "nombre")),
    )),
    Hoja("Capacidades", "Declaración de capacidades (CapabilityStatement)",
         "Qué ofrece un servidor (o qué espera de un cliente) que use esta guía. Una fila por declaración; sus recursos van en la hoja «RecursosCapacidad».", (
        Col("nombre", "Nombre", OBLIGATORIO, "Sin espacios, empieza con mayúscula. Ej.: ServidorClinica."),
        Col("titulo", "Título", RECOMENDADO, "Nombre legible."),
        Col("descripcion", "Descripción", RECOMENDADO, "Para quién es y qué cubre.", ancho=45),
        Col("modo", "Rol", OBLIGATORIO, "server = lo que ofrece el sistema que guarda los datos; client = lo que espera la aplicación que los consulta.", tuple(MODOS_CAPACIDAD), ancho=12),
        Col("formato", "Formatos", OPCIONAL, "json (por defecto), xml, o tipos MIME como application/fhir+json; varios separados por coma.", ancho=24),
        Col("documentacion", "Documentación general", OPCIONAL, "Texto (Markdown) que acompaña a toda la declaración: qué debe cumplir el servidor o el cliente.", ancho=60),
        Col("formato_parche", "Formatos de parche", OPCIONAL, "Si ofrece la operación patch: application/json-patch+json, application/xml-patch+xml… separados por coma.", ancho=30, avanzada=True),
        Col("derechos", "Derechos de autor", OPCIONAL, "Texto de copyright, si corresponde.", ancho=40, avanzada=True),
    )),
    Hoja("RecursosCapacidad", "Recursos de cada declaración",
         "Una fila por recurso que la declaración soporta. Las operaciones y búsquedas se pueden escribir resumidas aquí o una por fila (con expectativa y detalle) en las dos hojas siguientes.", (
        Col("capacidad", "Declaración", OBLIGATORIO, "Elige una de la hoja Capacidades.", desde=("Capacidades", "nombre")),
        Col("recurso", "Recurso", OBLIGATORIO, "Tipo de recurso FHIR. Ej.: Patient.", tuple(RECURSOS_R4), ancho=22),
        Col("expectativa", "Expectativa", OPCIONAL, "SHALL (debe), SHOULD (debería), MAY (puede) o SHOULD-NOT. Se marca en el recurso.", tuple(EXPECTATIVAS), ancho=14),
        Col("perfil", "Perfil que se espera", RECOMENDADO, "Perfil de la hoja Perfiles o de CL Core que deben cumplir estos recursos. Varios separados por coma; cada uno puede llevar su expectativa al final (PerfilA SHALL).", desde=("Perfiles", "nombre")),
        Col("interacciones", "Operaciones", RECOMENDADO, f"Resumen, separadas por coma. Opciones: {', '.join(INTERACCIONES)}. Ej.: read, search-type. Para marcar la expectativa de cada una usa la hoja OperacionesCapacidad.", ancho=30),
        Col("busquedas", "Búsquedas", OPCIONAL, f"Resumen: parámetro:tipo, separados por coma. Ej.: identifier:token, birthdate:date. Tipos: {', '.join(TIPOS_BUSQUEDA)}. Para el detalle usa la hoja BusquedasCapacidad.", ancho=40),
        Col("perfil_expectativa", "Expectativa del perfil", OPCIONAL, "SHALL, SHOULD o MAY, aplicada al perfil.", tuple(EXPECTATIVAS), ancho=14, avanzada=True),
        Col("referencias", "Referencias admitidas", OPCIONAL, f"Cómo se pueden escribir las referencias a este recurso, separadas por coma: {', '.join(POLITICAS_REFERENCIA)}.", ancho=24, avanzada=True),
        Col("incluir", "Incluir en búsquedas", OPCIONAL, "searchInclude: recursos que se pueden traer junto al resultado. Ej.: Observation:subject.", ancho=30, avanzada=True),
        Col("incluir_inverso", "Incluir inversos", OPCIONAL, "searchRevInclude: recursos que apuntan a este. Ej.: Provenance:target.", ancho=30, avanzada=True),
        Col("documentacion", "Documentación", OPCIONAL, "Texto del recurso en la declaración.", ancho=50, avanzada=True),
    )),
    Hoja("OperacionesCapacidad", "Operaciones de cada declaración",
         "Una fila por operación, con su expectativa. Deja «Recurso» vacío para las operaciones de todo el servidor (transaction, batch, search-system, history-system).", (
        Col("capacidad", "Declaración", OBLIGATORIO, "Elige una de la hoja Capacidades.", desde=("Capacidades", "nombre")),
        Col("recurso", "Recurso", OPCIONAL, "Vacío = todo el servidor.", tuple(RECURSOS_R4), ancho=22),
        Col("operacion", "Operación", OBLIGATORIO, f"Una de: {', '.join(INTERACCIONES + OPERACIONES_SERVIDOR)}.", tuple(INTERACCIONES + OPERACIONES_SERVIDOR), ancho=18),
        Col("expectativa", "Expectativa", RECOMENDADO, "SHALL, SHOULD, MAY o SHOULD-NOT.", tuple(EXPECTATIVAS), ancho=14),
        Col("definicion", "Operación propia", OPCIONAL, "Solo para operaciones definidas por la guía: la hoja Operaciones (o la URL de su OperationDefinition). "
            "Entonces «Operación» es el nombre, sin $ (por ejemplo match).", desde=("Operaciones", "nombre"), ancho=24),
    )),
    Hoja("BusquedasCapacidad", "Búsquedas de cada declaración",
         "Una fila por parámetro de búsqueda, con su expectativa y la explicación de cómo usarlo.", (
        Col("capacidad", "Declaración", OBLIGATORIO, "Elige una de la hoja Capacidades.", desde=("Capacidades", "nombre")),
        Col("recurso", "Recurso", OBLIGATORIO, "Recurso en que se busca.", tuple(RECURSOS_R4), ancho=22),
        Col("parametro", "Parámetro", OBLIGATORIO, "Nombre del parámetro. Ej.: identifier, birthdate."),
        Col("tipo", "Tipo", OBLIGATORIO, "Tipo del parámetro.", tuple(TIPOS_BUSQUEDA), ancho=14),
        Col("expectativa", "Expectativa", RECOMENDADO, "SHALL, SHOULD, MAY o SHOULD-NOT.", tuple(EXPECTATIVAS), ancho=14),
        Col("documentacion", "Cómo se usa", OPCIONAL, "Explica qué debe hacer el cliente y el servidor con este parámetro.", ancho=60),
        Col("definicion", "Definición (URL)", OPCIONAL, "URL del SearchParameter que lo define. Ej.: http://hl7.org/fhir/SearchParameter/Patient-identifier.", ancho=45, avanzada=True),
    )),
    Hoja("ParametrosBusqueda", "Parámetros de búsqueda propios (SearchParameter)",
         "Un parámetro de búsqueda permite consultar un recurso por un dato que FHIR no trae. Una fila por parámetro; se declara en «BusquedasCapacidad».", (
        Col("nombre", "Nombre", OBLIGATORIO, "Sin espacios, empieza con mayúscula. Ej.: PacienteSegundoApellido."),
        Col("codigo", "Código de búsqueda", OBLIGATORIO, "Lo que se escribe en la consulta. Ej.: segundo-apellido (GET Patient?segundo-apellido=...)."),
        Col("recursos", "Recursos", OBLIGATORIO, "Recursos en que se busca, separados por coma. Ej.: Patient."),
        Col("tipo", "Tipo", OBLIGATORIO, "Tipo del parámetro.", tuple(TIPOS_BUSQUEDA), ancho=14),
        Col("expresion", "Expresión (FHIRPath)", RECOMENDADO, "Dónde está el dato. Ej.: Patient.name.family.extension('URL-de-la-extension').value.", ancho=50),
        Col("titulo", "Título", RECOMENDADO, "Nombre legible."),
        Col("descripcion", "Descripción", RECOMENDADO, "Qué devuelve esta búsqueda.", ancho=45),
        Col("modificadores", "Modificadores", OPCIONAL, f"Separados por coma. Opciones: {', '.join(MODIFICADORES_BUSQUEDA)}.", ancho=24, avanzada=True),
        Col("multiple_o", "Admite varios valores (o)", OPCIONAL, "Sí = se pueden dar varios valores separados por coma.", ("Sí", "No"), ancho=14, avanzada=True),
        Col("multiple_y", "Admite repetirlo (y)", OPCIONAL, "Sí = se puede repetir el parámetro en la misma consulta.", ("Sí", "No"), ancho=14, avanzada=True),
        Col("comparadores", "Comparadores", OPCIONAL, "eq, ne, gt, lt, ge, le, sa, eb, ap, separados por coma (fechas, números, cantidades).", ancho=24, avanzada=True),
        Col("destinos", "Apunta a", OPCIONAL, "Para tipo reference: recursos a que puede apuntar, separados por coma.", ancho=24, avanzada=True),
    )),
    Hoja("MapasConceptos", "Mapas de conceptos (ConceptMap)",
         "Un mapa dice a qué código de otro sistema equivale cada código del tuyo. Una fila por mapa; sus equivalencias van en «ReglasMapa».", (
        Col("nombre", "Nombre", OBLIGATORIO, "Sin espacios, empieza con mayúscula. Ej.: MapaEstadoCivil."),
        Col("titulo", "Título", RECOMENDADO, "Nombre legible."),
        Col("descripcion", "Descripción", RECOMENDADO, "Qué se está traduciendo y para qué.", ancho=45),
        Col("origen", "ValueSet de origen", OPCIONAL, "ValueSet del que se parte (de tu libro, de CL Core o una URL).", desde=("ValueSets", "nombre")),
        Col("destino", "ValueSet de destino", OPCIONAL, "ValueSet al que se traduce (de tu libro, de CL Core o una URL).", desde=("ValueSets", "nombre")),
    )),
    Hoja("ReglasMapa", "Equivalencias de cada mapa",
         "Una fila por código de origen y destino. Un código de origen puede aparecer en varias filas si se traduce a varios.", (
        Col("mapa", "Mapa", OBLIGATORIO, "Elige uno de la hoja MapasConceptos.", desde=("MapasConceptos", "nombre")),
        Col("sistema_origen", "Sistema de origen", OBLIGATORIO, "CodeSystem de tu libro, LOINC, SNOMED o una URL.", desde=("CodeSystems", "nombre")),
        Col("sistema_destino", "Sistema de destino", OBLIGATORIO, "CodeSystem de tu libro, LOINC, SNOMED o una URL.", desde=("CodeSystems", "nombre")),
        Col("codigo_origen", "Código de origen", OBLIGATORIO, "Ej.: 01."),
        Col("codigo_destino", "Código de destino", RECOMENDADO, "Ej.: S. Vacío si no hay equivalente (equivalencia unmatched)."),
        Col("equivalencia", "Equivalencia", RECOMENDADO, "equivalent (por defecto), equal, wider, narrower, inexact, unmatched…", tuple(EQUIVALENCIAS), ancho=14),
        Col("version_origen", "Versión del sistema de origen", OPCIONAL, "Versión del CodeSystem de origen, si importa.", ancho=14, avanzada=True),
        Col("version_destino", "Versión del sistema de destino", OPCIONAL, "Versión del CodeSystem de destino, si importa.", ancho=14, avanzada=True),
        Col("texto_origen", "Texto de origen", OPCIONAL, "Cómo se muestra el código de origen.", ancho=30, avanzada=True),
        Col("texto_destino", "Texto de destino", OPCIONAL, "Cómo se muestra el código de destino.", ancho=30, avanzada=True),
        Col("comentario", "Comentario", OPCIONAL, "Aclaración de esta equivalencia.", ancho=40, avanzada=True),
    )),
    Hoja("Operaciones", "Operaciones propias (OperationDefinition)",
         "Una operación es una consulta o acción con nombre (por ejemplo $match). Una fila por operación; sus parámetros van en «ParametrosOperacion».", (
        Col("nombre", "Nombre", OBLIGATORIO, "Sin espacios, empieza con mayúscula. Ej.: BuscarCoincidencias."),
        Col("codigo", "Código", OBLIGATORIO, "Lo que se escribe tras el signo $. Ej.: match."),
        Col("recursos", "Recursos", OPCIONAL, "Recursos sobre los que se invoca, separados por coma. Vacío = ninguno en particular."),
        Col("nivel", "Se invoca sobre", RECOMENDADO, "Dónde se puede invocar, separados por coma: sistema (todo el servidor), tipo (Patient/$op), instancia (Patient/123/$op).", ancho=24),
        Col("titulo", "Título", RECOMENDADO, "Nombre legible."),
        Col("descripcion", "Descripción", RECOMENDADO, "Qué hace la operación.", ancho=50),
        Col("base", "Operación en que se basa", OPCIONAL, "URL de la operación que restringe, si corresponde. Ej.: http://hl7.org/fhir/OperationDefinition/Patient-match.", ancho=40, avanzada=True),
        Col("tipo_operacion", "Tipo", OPCIONAL, "operation (por defecto) o query.", tuple(TIPOS_OPERACION), ancho=14, avanzada=True),
        Col("afecta_estado", "Modifica datos", OPCIONAL, "Sí si la operación cambia datos del servidor.", ("Sí", "No"), ancho=14, avanzada=True),
        Col("comentario", "Comentario", OPCIONAL, "Notas de uso.", ancho=40, avanzada=True),
    )),
    Hoja("ParametrosOperacion", "Parámetros de cada operación",
         "Una fila por parámetro de entrada (in) o de salida (out).", (
        Col("operacion", "Operación", OBLIGATORIO, "Elige una de la hoja Operaciones.", desde=("Operaciones", "nombre")),
        Col("parametro", "Parámetro", OBLIGATORIO, "Nombre del parámetro. Ej.: resource, count."),
        Col("uso", "Entrada o salida", OBLIGATORIO, "in = entrada; out = salida.", tuple(USOS_PARAMETRO), ancho=12),
        Col("min", "Mín", RECOMENDADO, "0 si es opcional. Por defecto 0.", ancho=8),
        Col("max", "Máx", RECOMENDADO, "1, un número o * (por defecto 1).", ancho=8),
        Col("tipo", "Tipo de dato", RECOMENDADO, "Ej.: Patient, boolean, integer, Bundle, string. Vacío si es un parámetro de búsqueda.", ancho=22),
        Col("perfil", "Perfil exigido", OPCIONAL, "Perfiles que debe cumplir el valor (de tu libro, de CL Core o una URL), separados por coma.", ancho=30),
        Col("tipo_busqueda", "Tipo de búsqueda", OPCIONAL, "Si el parámetro funciona como un parámetro de búsqueda: token, uri, string…", tuple(TIPOS_BUSQUEDA), ancho=14, avanzada=True),
        Col("documentacion", "Documentación", OPCIONAL, "Qué significa este parámetro.", ancho=50),
    )),
    Hoja("Cuestionarios", "Cuestionarios (Questionnaire)",
         "Un cuestionario es un formulario con preguntas. Una fila por cuestionario; sus preguntas van en «PreguntasCuestionario».", (
        Col("nombre", "Nombre", OBLIGATORIO, "Sin espacios, empieza con mayúscula. Ej.: MotivoDerivacion."),
        Col("titulo", "Título", RECOMENDADO, "Nombre legible."),
        Col("descripcion", "Descripción", RECOMENDADO, "Para qué sirve el formulario.", ancho=45),
        Col("recursos", "Se responde sobre", OPCIONAL, "Recursos a los que se refieren las respuestas (por ejemplo Patient), separados por coma.", ancho=24, avanzada=True),
        Col("basado_en", "Basado en", OPCIONAL, "URL de otro cuestionario del que deriva.", ancho=40, avanzada=True),
    )),
    Hoja("PreguntasCuestionario", "Preguntas de cada cuestionario",
         "Una fila por pregunta, grupo o texto informativo. Para anidar, indica el grupo en «Dentro de».", (
        Col("cuestionario", "Cuestionario", OBLIGATORIO, "Elige uno de la hoja Cuestionarios.", desde=("Cuestionarios", "nombre")),
        Col("id", "Id de la pregunta", OBLIGATORIO, "Identificador único dentro del cuestionario. Ej.: motivo, 1.1."),
        Col("dentro_de", "Dentro de", OPCIONAL, "Id del grupo que la contiene. Vacío = primer nivel.", ancho=14),
        Col("tipo", "Tipo", OBLIGATORIO, "group (grupo), display (texto informativo) o el tipo de respuesta.", tuple(TIPOS_PREGUNTA), ancho=14),
        Col("texto", "Texto", RECOMENDADO, "Lo que ve quien responde.", ancho=45),
        Col("obligatoria", "Obligatoria", OPCIONAL, "Sí si debe responderse.", ("Sí", "No"), ancho=12),
        Col("repite", "Se puede repetir", OPCIONAL, "Sí si admite varias respuestas o repeticiones.", ("Sí", "No"), ancho=12),
        Col("solo_lectura", "Solo lectura", OPCIONAL, "Sí si no se puede editar.", ("Sí", "No"), ancho=12, avanzada=True),
        Col("opciones", "Opciones (ValueSet)", OPCIONAL, "Para preguntas choice u open-choice: ValueSet de tu libro, de CL Core o una URL.", desde=("ValueSets", "nombre"), ancho=30),
        Col("largo_maximo", "Largo máximo", OPCIONAL, "Máximo de caracteres de una respuesta de texto.", ancho=10, avanzada=True),
        Col("prefijo", "Número o prefijo", OPCIONAL, "Cómo se numera. Ej.: 1., a).", ancho=10, avanzada=True),
        Col("definicion", "Definición", OPCIONAL, "URL del elemento que esta pregunta representa (item.definition).", ancho=40, avanzada=True),
        Col("si_pregunta", "Mostrar solo si… (pregunta)", OPCIONAL, "Id de otra pregunta cuya respuesta decide si esta se muestra.", ancho=16, avanzada=True),
        Col("si_operador", "Operador", OPCIONAL, "exists, =, !=, >, <, >=, <=. Por defecto «=».", tuple(OPERADORES_CONDICION), ancho=10, avanzada=True),
        Col("si_respuesta", "Respuesta esperada", OPCIONAL, "Valor que debe tener la otra pregunta. Para códigos: SISTEMA#codigo (sistema de tu libro, conocido o URL). Con «exists»: Sí o No.", ancho=30, avanzada=True),
        Col("si_comportamiento", "Si hay varias condiciones", OPCIONAL, "any (basta una, por defecto) o all (todas).", ("any", "all"), ancho=12, avanzada=True),
    )),
    Hoja("Invariantes", "Reglas de validación (FHIRPath)",
         "Una regla que los datos deben cumplir y que no se puede expresar con cardinalidad ni valores fijos. Una fila por cada lugar donde se aplica.", (
        Col("clave", "Clave", OBLIGATORIO, "Identificador corto de la regla. Ej.: cl-1. Se puede repetir en varias filas para aplicarla a varios perfiles o elementos."),
        Col("perfil", "Perfil o extensión", OBLIGATORIO, "Perfil (hoja Perfiles) o extensión propia (hoja Extensiones) al que se aplica.", desde=("Perfiles", "nombre")),
        Col("ruta", "Elemento", OPCIONAL, "Elemento al que se aplica. Vacío = el recurso completo. Ej.: name, identifier.", ancho=24),
        Col("gravedad", "Gravedad", OBLIGATORIO, "error: el dato es inválido; warning: es solo una advertencia.", tuple(GRAVEDADES), ancho=12),
        Col("descripcion", "Qué exige la regla", OBLIGATORIO, "Frase que verá quien incumpla la regla. Ej.: Debe haber RUN o pasaporte.", ancho=50),
        Col("expresion", "Expresión (FHIRPath)", OBLIGATORIO, "La condición, evaluada desde el elemento. Ej.: identifier.where(system='...').exists().", ancho=60),
    )),
    Hoja("Documentación", "Páginas de la guía", "Texto narrativo en Markdown. Si no escribes la página 'inicio', se genera un borrador.", (
        Col("pagina", "Página (id)", OBLIGATORIO, "Minúsculas y guiones. 'inicio' es la portada."),
        Col("titulo", "Título", OBLIGATORIO, "Título de la página."),
        Col("texto", "Texto (Markdown)", OBLIGATORIO,
            "Contenido de la página. Para una página larga, escribe @paginas/nombre.md y guarda el texto en esa carpeta, junto a este libro.", ancho=80),
        Col("padre", "Página padre", OPCIONAL, "Si esta página va dentro de otra, el id de la otra página. Vacío = página de primer nivel.", ancho=18, avanzada=True),
    )),
    Hoja("Menú", "Menú superior de la guía",
         "Opcional. Si la dejas vacía, el menú es Inicio, Requisitos y Artefactos. Si escribes filas, el menú es exactamente lo que pongas aquí, en ese orden.", (
        Col("etiqueta", "Texto del menú", OBLIGATORIO, "Lo que verá el lector. Ej.: Objetivos."),
        Col("destino", "A dónde lleva", OPCIONAL,
            "El id de una página (hoja Documentación), «artefactos», «must-support» (página generada con los elementos Must Support), «cambios» (página generada desde la hoja Cambios), "
            "el nombre de una declaración de capacidades (hoja Capacidades) o una dirección https://. Vacío = es un desplegable que agrupa otras filas.", ancho=40),
        Col("padre", "Dentro del desplegable", OPCIONAL, "Si va dentro de un desplegable, el «Texto del menú» de esa fila.", ancho=24),
    )),
    Hoja("Cambios", "Historial de cambios", "Una fila por versión. Se publica como la página «cambios» (úsala en el menú con destino «cambios»).", (
        Col("version", "Versión", OBLIGATORIO, "Ej.: 0.2.0."),
        Col("fecha", "Fecha", RECOMENDADO, "Ej.: 2026-10-21."),
        Col("cambios", "Qué cambió", OBLIGATORIO, "Resumen de los cambios de esa versión.", ancho=80),
    )),
)

# Hojas de artefactos que se publican con URL propia: el «id» es el final de esa URL (…/StructureDefinition/<id>).
HOJAS_CON_ID = ("Perfiles", "Extensiones", "CodeSystems", "ValueSets", "Capacidades", "ParametrosBusqueda", "MapasConceptos", "Operaciones", "Cuestionarios")
_COL_ID = Col("id", "Id (final de la URL)", OPCIONAL, "Cómo termina la URL del artefacto. Si lo dejas vacío se usa el nombre en minúsculas con guiones "
              "(MiPerfil -> miperfil). Complétalo cuando la URL ya está publicada o la usan otras guías.", ancho=28, avanzada=True)
HOJAS = tuple(replace(h, columnas=h.columnas + (_COL_ID,)) if h.nombre in HOJAS_CON_ID else h for h in HOJAS)

HOJA_POR_NOMBRE = {h.nombre: h for h in HOJAS}
