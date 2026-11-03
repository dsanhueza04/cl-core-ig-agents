Instance: PacienteDemo
InstanceOf: CorePacienteCl
Title: "Paciente sintético de demostración"
Description: "Paciente con datos ficticios, conforme al perfil CorePacienteCl de CL Core. No corresponde a ninguna persona real."
Usage: #example
* identifier[0].use = #official
* identifier[0].type = $CSDNI#NNCHL
* identifier[0].system = "http://regcivil.cl/Validacion/RUN"
* identifier[0].value = "11.111.111-1"
* name[NombreOficial].use = #official
* name[NombreOficial].family = "Pérez"
* name[NombreOficial].family.extension[segundoApellido].valueString = "Soto"
* name[NombreOficial].given[0] = "Camila"
* gender = #female
* birthDate = "1975-06-12"

Instance: PresionArterialDemo
InstanceOf: CLPresionArterial
Title: "Presión arterial 128/82 mmHg (ejemplo sintético)"
Description: "Medición de presión arterial de un paciente ficticio: sistólica 128 mmHg y diastólica 82 mmHg."
Usage: #example
* status = #final
* category[VSCat] = $ObsCat#vital-signs
* code = $LNC#85354-9
* code.text = "Presión arterial"
* subject = Reference(PacienteDemo)
* effectiveDateTime = "2026-03-15T09:30:00-03:00"
* component[sistolica].code = $LNC#8480-6
* component[sistolica].valueQuantity = 128 'mm[Hg]' "mmHg"
* component[diastolica].code = $LNC#8462-4
* component[diastolica].valueQuantity = 82 'mm[Hg]' "mmHg"
