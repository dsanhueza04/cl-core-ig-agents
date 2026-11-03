"""Ficha estructurada (spec.json) de lo que el IG debe definir, y su validación.

Es el contrato entre el analista (modelo) y el generador (código): el modelo solo rellena datos,
el generador escribe el FSH. La validación es estricta y devuelve mensajes que se le pueden mostrar al
modelo para que corrija. Alcance v1: observaciones de signos vitales (perfil hijo de
`cl-core-signos-vitales`) con valor único o con componentes, más un paciente de ejemplo.
"""
from __future__ import annotations

import copy
import re
import unicodedata

from agents.catalog import CatalogIndex

SUPPORTED_PARENTS = {"cl-core-signos-vitales"}
SEXOS = {"female", "male", "other", "unknown"}

RE_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")                 # nombre FSH de perfil / instancia
RE_ID = re.compile(r"^[a-z0-9][a-z0-9\-.]{0,63}$")           # id FHIR
RE_COMP = re.compile(r"^[a-z][A-Za-z0-9]*$")                 # nombre de slice
RE_LOINC = re.compile(r"^\d{1,7}-\d$")
RE_UCUM = re.compile(r"^[A-Za-z0-9\[\]/.\-^%_{}()*]+$")
FECHA_HINT = "formato AAAA-MM-DDThh:mm:ss-03:00, por ejemplo 2026-03-15T09:30:00-03:00"
RE_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$")
RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_RUN = re.compile(r"^\d{1,2}\.\d{3}\.\d{3}-[\dkK]$")


PACIENTE_POR_DEFECTO = {"id": "PacienteDemo", "run": "11.111.111-1", "nombres": ["Camila"], "primer_apellido": "Pérez",
                        "segundo_apellido": "Soto", "sexo": "female", "fecha_nacimiento": "1975-06-12"}
FECHA_POR_DEFECTO = "2026-03-15T09:30:00-03:00"
SEXO_ES = {"femenino": "female", "mujer": "female", "f": "female", "masculino": "male", "hombre": "male", "m": "male"}


def _palabras(texto: str) -> list[str]:
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.findall(r"[A-Za-z0-9]+", plano)


def pascal(texto: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in _palabras(texto))


def kebab(texto: str) -> str:
    return "-".join(w.lower() for w in _palabras(texto))


def _camel(texto: str) -> str:
    palabras = _palabras(texto)
    if not palabras:
        return ""
    return palabras[0][:1].lower() + palabras[0][1:] + "".join(w[:1].upper() + w[1:] for w in palabras[1:])


def _normalizar_valor_unico(o: dict, path: str, notas: list[str]) -> None:
    """Arregla la FORMA de una medición única mal escrita, sin tocar su contenido: `unidad`/`ucum` sueltos en la
    observación se suben a `valor`, y un 'panel' de un solo componente con el mismo LOINC que la observación es en
    realidad un valor único."""
    if "componentes" in o and not o["componentes"]:
        del o["componentes"]
    comps, ej = o.get("componentes"), o.get("ejemplo")
    if not comps and not o.get("valor") and isinstance(o.get("unidad"), str) and isinstance(o.get("ucum"), str):
        o["valor"] = {"unidad": o.pop("unidad"), "ucum": o.pop("ucum")}
        o.pop("obligatorio", None)
        notas.append(f"{path}: `unidad` y `ucum` se subieron a `valor`")
        return
    if (isinstance(comps, list) and len(comps) == 1 and isinstance(comps[0], dict) and not o.get("valor")
            and comps[0].get("loinc") == o.get("codigo_loinc")
            and isinstance(comps[0].get("unidad"), str) and isinstance(comps[0].get("ucum"), str)):
        c = comps[0]
        o["valor"] = {"unidad": c["unidad"], "ucum": c["ucum"]}
        del o["componentes"]
        if isinstance(ej, dict):
            valores = ej.pop("valores", None)
            numero = valores.get(c.get("nombre")) if isinstance(valores, dict) else None
            if numero is not None and "valor" not in ej:
                ej["valor"] = numero
        notas.append(f"{path}: un panel de un solo componente con el LOINC de la observación pasó a `valor` (medición única)")


def _normalizar_panel(o: dict, path: str, notas: list[str]) -> None:
    """Arregla solo la FORMA de un panel, sin tocar su contenido: la clave del ejemplo (`valor` → `valores`) y los
    nombres internos de componente (`presion_sistolica` → `presionSistolica`), con las claves de `valores` al día."""
    comps, ej = o.get("componentes"), o.get("ejemplo")
    if not (isinstance(comps, list) and comps and isinstance(ej, dict)):
        return
    if isinstance(ej.get("valor"), dict) and "valores" not in ej:
        ej["valores"] = ej.pop("valor")
        notas.append(f"{path}.ejemplo: la clave `valor` se movió a `valores` (es un panel)")
    renombres: dict[str, str] = {}
    usados = {c.get("nombre") for c in comps if isinstance(c, dict) and isinstance(c.get("nombre"), str)
              and RE_COMP.match(c["nombre"])}
    for j, c in enumerate(comps):
        n = c.get("nombre") if isinstance(c, dict) else None
        if not isinstance(n, str) or RE_COMP.match(n):
            continue
        nuevo = _camel(n)
        if not RE_COMP.match(nuevo) or nuevo in usados:
            nuevo = f"componente{j + 1}"
        usados.add(nuevo)
        renombres[n] = nuevo
        c["nombre"] = nuevo
        notas.append(f"{path}.componentes[{j}].nombre: '{n}' → '{nuevo}'")
    if renombres and isinstance(ej.get("valores"), dict):
        ej["valores"] = {renombres.get(k, k): v for k, v in ej["valores"].items()}


def completar_ficha(spec: object) -> tuple[object, list[str]]:
    """Completa por código lo que NO requiere leer la especificación: datos del paciente de ejemplo, nombres e
    ids derivados del título y metadatos del ejemplo. Nunca inventa lo clínico (códigos LOINC, unidades,
    valores): eso sigue siendo del modelo y del validador. Devuelve (copia completada, lista de lo completado)."""
    if not isinstance(spec, dict):
        return spec, []
    out, notas = copy.deepcopy(spec), []
    if not isinstance(out.get("paciente_ejemplo"), dict):
        out["paciente_ejemplo"] = copy.deepcopy(PACIENTE_POR_DEFECTO)
        notas.append("paciente_ejemplo")
    else:
        p = out["paciente_ejemplo"]
        for k, v in PACIENTE_POR_DEFECTO.items():
            if k == "segundo_apellido":
                continue
            if p.get(k) in (None, "", []):
                p[k] = copy.deepcopy(v)
                notas.append(f"paciente_ejemplo.{k}")
        if isinstance(p.get("sexo"), str):
            p["sexo"] = SEXO_ES.get(p["sexo"].strip().lower(), p["sexo"].strip().lower())
    obs = out.get("observaciones")
    for i, o in enumerate(obs if isinstance(obs, list) else []):
        if not isinstance(o, dict):
            continue
        _normalizar_valor_unico(o, f"observaciones[{i}]", notas)
        if not isinstance(o.get("titulo"), str) or not _palabras(o["titulo"]):
            continue
        titulo = o["titulo"]
        derivados = {"nombre": ("CL" + pascal(titulo), RE_NAME), "id": ("cl-" + kebab(titulo), RE_ID)}
        for k, (v, patron) in derivados.items():
            if o.get(k) in (None, ""):
                o[k] = v
                notas.append(f"observaciones[{i}].{k}")
            elif not (isinstance(o[k], str) and patron.match(o[k])):
                notas.append(f"observaciones[{i}].{k}: recalculado ('{o[k]}' no tenía el formato)")
                o[k] = v
        ej = o.get("ejemplo") if isinstance(o.get("ejemplo"), dict) else {}
        defecto = {"id": pascal(titulo) + "Ejemplo", "titulo": f"{titulo} (ejemplo sintético)",
                   "descripcion": f"Ejemplo sintético de {titulo.lower()}.", "fecha": FECHA_POR_DEFECTO}
        for k, v in defecto.items():
            if ej.get(k) in (None, ""):
                ej[k] = v
                notas.append(f"observaciones[{i}].ejemplo.{k}")
            elif k == "id" and not (isinstance(ej[k], str) and RE_NAME.match(ej[k])):
                notas.append(f"observaciones[{i}].ejemplo.id: recalculado ('{ej[k]}' no tenía el formato)")
                ej[k] = v
        o["ejemplo"] = ej
        _normalizar_panel(o, f"observaciones[{i}]", notas)
    return out, notas


def _text(d: dict, key: str, path: str, errors: list[str], required: bool = True, hint: str = "") -> str | None:
    v = d.get(key)
    if v is None or v == "":
        if required:
            errors.append(f"{path}.{key}: falta{'; ' + hint if hint else ''}")
        return None
    if not isinstance(v, str):
        errors.append(f"{path}.{key}: debe ser texto")
        return None
    return v


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_spec(spec: object, catalog: CatalogIndex, source_text: str | None = None) -> list[str]:
    """Lista de problemas (vacía si la ficha es válida).

    Con `source_text` (la especificación original) exige que cada código LOINC aparezca en ella: así el
    modelo no puede inventar códigos que el chequeo previo no puede verificar sin base de datos de LOINC.
    """
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["la ficha debe ser un objeto JSON"]

    # --- paciente de ejemplo -------------------------------------------------
    p = spec.get("paciente_ejemplo")
    if not isinstance(p, dict):
        errors.append("paciente_ejemplo: falta")
    else:
        n = _text(p, "id", "paciente_ejemplo", errors)
        if n and not RE_NAME.match(n):
            errors.append("paciente_ejemplo.id: debe empezar con mayúscula y solo letras o números (ej. PacienteDemo)")
        run = _text(p, "run", "paciente_ejemplo", errors)
        if run and not RE_RUN.match(run):
            errors.append("paciente_ejemplo.run: formato 11.111.111-1")
        nombres = p.get("nombres")
        if not (isinstance(nombres, list) and nombres and all(isinstance(x, str) and x for x in nombres)):
            errors.append("paciente_ejemplo.nombres: lista con al menos un nombre")
        _text(p, "primer_apellido", "paciente_ejemplo", errors)
        _text(p, "segundo_apellido", "paciente_ejemplo", errors, required=False)
        if p.get("sexo") not in SEXOS:
            errors.append(f"paciente_ejemplo.sexo: debe ser uno de {sorted(SEXOS)}")
        f = _text(p, "fecha_nacimiento", "paciente_ejemplo", errors)
        if f and not RE_DATE.match(f):
            errors.append("paciente_ejemplo.fecha_nacimiento: formato AAAA-MM-DD")

    # --- observaciones ---------------------------------------------------------
    obs = spec.get("observaciones")
    if not (isinstance(obs, list) and obs):
        errors.append("observaciones: lista con al menos una observación")
        return errors
    seen: set[str] = set()
    for i, o in enumerate(obs):
        path = f"observaciones[{i}]"
        if not isinstance(o, dict):
            errors.append(f"{path}: debe ser un objeto")
            continue
        nombre = _text(o, "nombre", path, errors)
        if nombre:
            if not RE_NAME.match(nombre):
                errors.append(f"{path}.nombre: debe empezar con mayúscula y solo letras o números (ej. CLPresionArterial)")
            if nombre in seen or nombre in catalog.sd:
                errors.append(f"{path}.nombre: '{nombre}' repetido o ya existe en CL Core")
            seen.add(nombre)
        oid = _text(o, "id", path, errors)
        if oid and not RE_ID.match(oid):
            errors.append(f"{path}.id: minúsculas, números, guiones o puntos (ej. cl-presion-arterial)")
        _text(o, "titulo", path, errors)
        _text(o, "descripcion", path, errors)
        padre = _text(o, "padre", path, errors)
        if padre:
            if padre not in catalog.sd:
                errors.append(f"{path}.padre: '{padre}' no existe en CL Core {catalog.data['version']}")
            elif padre not in SUPPORTED_PARENTS:
                errors.append(f"{path}.padre: '{padre}' aún no está soportado (solo {sorted(SUPPORTED_PARENTS)})")
        codes = []
        loinc = _text(o, "codigo_loinc", path, errors,
                      hint="es el código LOINC de la observación completa, no el de un componente: en un panel, "
                           "el código del panel; cópialo de la especificación")
        if loinc:
            codes.append((f"{path}.codigo_loinc", loinc))
        _text(o, "texto_codigo", path, errors, required=False)

        comps, valor = o.get("componentes"), o.get("valor")
        if bool(comps) == bool(valor):
            errors.append(f"{path}: define o bien 'componentes' (panel de 2 o más partes) o bien 'valor' (medición única, por ejemplo "
                          '"valor": {"unidad": "kg", "ucum": "kg"}), no ambos ni ninguno')
        names: list[str] = []
        units = []
        if comps:
            if not isinstance(comps, list):
                errors.append(f"{path}.componentes: debe ser una lista")
                comps = []
            if len(comps) == 1:
                errors.append(f"{path}.componentes: un panel necesita al menos 2 componentes; si es una sola medición, usa "
                              '"valor": {"unidad": "kg", "ucum": "kg"} y no pongas componentes')
            for j, c in enumerate(comps):
                cp = f"{path}.componentes[{j}]"
                if not isinstance(c, dict):
                    errors.append(f"{cp}: debe ser un objeto")
                    continue
                cn = _text(c, "nombre", cp, errors)
                if cn:
                    if not RE_COMP.match(cn):
                        errors.append(f"{cp}.nombre: '{cn}' no vale: debe empezar con minúscula y tener solo letras o números, "
                                      "sin guiones bajos ni espacios (ej. sistolica, presionMedia)")
                    if cn in names:
                        errors.append(f"{cp}.nombre: '{cn}' repetido")
                    names.append(cn)
                _text(c, "etiqueta", cp, errors)
                cl = _text(c, "loinc", cp, errors)
                if cl:
                    codes.append((f"{cp}.loinc", cl))
                units.append((cp, c))
                if "obligatorio" in c and not isinstance(c["obligatorio"], bool):
                    errors.append(f"{cp}.obligatorio: debe ser true o false")
        elif valor:
            if isinstance(valor, dict):
                units.append((f"{path}.valor", valor))
            else:
                errors.append(f"{path}.valor: debe ser un objeto con unidad y ucum, por ejemplo "
                          '{"unidad": "kg", "ucum": "kg"}')
        for up, u in units:
            _text(u, "unidad", up, errors)
            uc = _text(u, "ucum", up, errors)
            if uc and not RE_UCUM.match(uc):
                errors.append(f"{up}.ucum: código UCUM inválido '{uc}'")
        for cp, code in codes:
            if not RE_LOINC.match(code):
                errors.append(f"{cp}: '{code}' no tiene formato LOINC (ej. 8480-6)")
            elif source_text is not None and code not in source_text:
                errors.append(f"{cp}: el código '{code}' no aparece en la especificación; no inventes códigos. "
                              "Si la especificación no lo trae, un humano debe decidirlo")

        ej = o.get("ejemplo")
        if not isinstance(ej, dict):
            errors.append(f"{path}.ejemplo: falta")
            continue
        en = _text(ej, "id", f"{path}.ejemplo", errors)
        if en and not RE_NAME.match(en):
            errors.append(f"{path}.ejemplo.id: debe empezar con mayúscula y solo letras o números")
        if en and (en in seen or en == (p or {}).get("id")):
            errors.append(f"{path}.ejemplo.id: '{en}' repetido")
        if en:
            seen.add(en)
        _text(ej, "titulo", f"{path}.ejemplo", errors)
        _text(ej, "descripcion", f"{path}.ejemplo", errors)
        fecha = _text(ej, "fecha", f"{path}.ejemplo", errors, hint=FECHA_HINT)
        if fecha and not RE_DATETIME.match(fecha):
            errors.append(f"{path}.ejemplo.fecha: '{fecha}' no vale; {FECHA_HINT}")
        if comps:
            vals = ej.get("valores")
            if not isinstance(vals, dict) or set(vals) != set(names) or not all(_number(v) for v in vals.values()):
                pista = " Usa la clave `valores` (en plural), no `valor`." if "valor" in ej and "valores" not in ej else ""
                errors.append(f"{path}.ejemplo.valores: objeto con un número por componente ({', '.join(names)}).{pista}")
        elif valor:
            if not _number(ej.get("valor")):
                errors.append(f"{path}.ejemplo.valor: debe ser solo un número (el valor medido, sin unidad), por ejemplo 70")
    return errors


VS_SIGNOS_VITALES = "cl-core-vs-signos-vitales"


def advertencias_spec(spec: object, catalog: CatalogIndex) -> list[str]:
    """Avisos que NO bloquean (revisión humana): códigos LOINC fuera del ValueSet de signos vitales de CL Core.

    El binding de `code` en cl-core-signos-vitales es extensible: un código fuera del conjunto es legal,
    pero conviene que una persona confirme que es lo que se quiere. Sin lista de códigos en el catálogo
    (catálogo antiguo) no avisa nada.
    """
    vs = catalog.vs.get(VS_SIGNOS_VITALES) or {}
    permitidos = set((vs.get("codes") or {}).get("http://loinc.org", []))
    if not permitidos or not isinstance(spec, dict):
        return []
    avisos: list[str] = []
    for i, o in enumerate(spec.get("observaciones") or []):
        if not isinstance(o, dict) or o.get("padre") != "cl-core-signos-vitales":
            continue
        codigos = [(f"observaciones[{i}].codigo_loinc", o.get("codigo_loinc"))]
        codigos += [(f"observaciones[{i}].componentes[{j}].loinc", c.get("loinc"))
                    for j, c in enumerate(o.get("componentes") or []) if isinstance(c, dict)]
        for ruta, cod in codigos:
            if cod and cod not in permitidos:
                avisos.append(f"{ruta}: el código {cod} no está en el ValueSet {VS_SIGNOS_VITALES} de CL Core "
                              f"({len(permitidos)} códigos); es legal (binding extensible) pero revísalo")
    return avisos
