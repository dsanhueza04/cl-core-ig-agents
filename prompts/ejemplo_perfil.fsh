// Ejemplo de estilo (dominio distinto al de la entrada): temperatura corporal.
Profile: CLTemperaturaCorporal
Parent: https://hl7chile.cl/fhir/ig/clcore/StructureDefinition/cl-core-signos-vitales
Id: cl-temperatura-corporal
Title: "Temperatura corporal"
Description: "Medición de temperatura corporal (LOINC 8310-5) en grados Celsius. Extiende el perfil de signos vitales de CL Core."
* ^status = #draft
* code = $LNC#8310-5
* value[x] only Quantity
* valueQuantity 1..1 MS
* valueQuantity.system = $UCUM
* valueQuantity.code = #Cel
* valueQuantity.unit = "°C"
