// Ejemplo de estilo (dominio distinto al de la entrada): temperatura corporal. Datos 100 % ficticios.
Instance: PacienteEjemploUno
InstanceOf: CorePacienteCl
Title: "Paciente sintético de ejemplo"
Description: "Paciente con datos ficticios, conforme al perfil CorePacienteCl de CL Core. No corresponde a ninguna persona real."
Usage: #example
* identifier[0].use = #official
* identifier[0].type = $CSDNI#NNCHL
* identifier[0].system = "http://regcivil.cl/Validacion/RUN"
* identifier[0].value = "22.222.222-2"
* name[NombreOficial].use = #official
* name[NombreOficial].family = "González"
* name[NombreOficial].family.extension[segundoApellido].valueString = "Rojas"
* name[NombreOficial].given[0] = "Matías"
* gender = #male
* birthDate = "1988-11-03"

Instance: TemperaturaEjemplo
InstanceOf: CLTemperaturaCorporal
Title: "Temperatura corporal 36,8 °C (ejemplo sintético)"
Description: "Medición de temperatura corporal de un paciente ficticio: 36,8 °C."
Usage: #example
* status = #final
* category[VSCat] = $ObsCat#vital-signs
* code = $LNC#8310-5
* subject = Reference(PacienteEjemploUno)
* effectiveDateTime = "2026-04-02T08:15:00-04:00"
* valueQuantity = 36.8 'Cel' "°C"
