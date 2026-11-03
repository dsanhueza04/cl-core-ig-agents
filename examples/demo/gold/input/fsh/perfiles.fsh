Profile: CLPresionArterial
Parent: https://hl7chile.cl/fhir/ig/clcore/StructureDefinition/cl-core-signos-vitales
Id: cl-presion-arterial
Title: "Presión arterial (demo)"
Description: "Medición de presión arterial como panel LOINC 85354-9 con dos componentes obligatorios: presión sistólica y diastólica, ambas en mmHg. Extiende el perfil de signos vitales de CL Core."
* ^status = #draft
* code = $LNC#85354-9

* component ^slicing.discriminator.type = #pattern
* component ^slicing.discriminator.path = "code"
* component ^slicing.rules = #open
* component ^slicing.ordered = false
* component ^slicing.description = "Componentes sistólico y diastólico"
* component contains sistolica 1..1 MS and diastolica 1..1 MS

* component[sistolica].code = $LNC#8480-6
* component[sistolica].value[x] only Quantity
* component[sistolica].valueQuantity.system = $UCUM
* component[sistolica].valueQuantity.code = #"mm[Hg]"
* component[sistolica].valueQuantity.unit = "mmHg"

* component[diastolica].code = $LNC#8462-4
* component[diastolica].value[x] only Quantity
* component[diastolica].valueQuantity.system = $UCUM
* component[diastolica].valueQuantity.code = #"mm[Hg]"
* component[diastolica].valueQuantity.unit = "mmHg"
