"""Reparaciones deterministas: errores cuyo arreglo sale del propio mensaje y del contexto del IG.

Se aplican ANTES de llamar al modelo. Cada regla cambia una sola línea, nunca toca cardinalidades ni
borra restricciones, y deja registrado qué cambió (`Cambio`) para la revisión humana. Lo que exige una
decisión clínica (por ejemplo convertir kPa a mmHg, o inventar el valor de un componente que falta)
NO tiene regla: queda para el modelo o para una persona.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from datetime import date

from agents.reparador import Problem

SINONIMOS_ALIAS = {"$LOINC": "$LNC", "$LN": "$LNC", "$LOINCS": "$LNC", "$OBSCAT": "$ObsCat"}

ESTADOS_ES = {"definitivo": "final", "final": "final", "preliminar": "preliminary", "registrado": "registered",
              "corregido": "corrected", "enmendado": "amended", "cancelado": "cancelled",
              "ingresado-en-error": "entered-in-error"}
GENERO_ES = {"femenino": "female", "masculino": "male", "otro": "other", "desconocido": "unknown"}
# ValueSet obligatorio de FHIR -> (elemento FSH, traducciones español -> código)
CODIGOS_ES = {"ObservationStatus": ("status", ESTADOS_ES), "AdministrativeGender": ("gender", GENERO_ES)}


@dataclass(frozen=True)
class Cambio:
    regla: str
    archivo: str
    antes: str
    despues: str
    nota: str = ""


def _linea(files: dict[str, str], p: Problem) -> tuple[str, list[str], int] | None:
    if not p.file or p.file not in files or not p.line:
        return None
    lineas = files[p.file].split("\n")
    if not 1 <= p.line <= len(lineas):
        return None
    return p.file, lineas, p.line - 1


def _alias_declarados(files: dict[str, str]) -> list[str]:
    return [m for t in files.values() for m in re.findall(r"^Alias:\s*(\$\w+)", t, re.M)]


def _slices_declarados(files: dict[str, str]) -> list[str]:
    return [m for t in files.values() for m in re.findall(r"(?:contains|\band)\s+([A-Za-z_]\w*)\s+\d+\.\.", t)]


def _unico_parecido(valor: str, candidatos: list[str], corte: float) -> str | None:
    cerca = difflib.get_close_matches(valor, sorted(set(candidatos)), n=2, cutoff=corte)
    return cerca[0] if len(cerca) == 1 or (cerca and difflib.SequenceMatcher(None, valor, cerca[0]).ratio() >
                                           difflib.SequenceMatcher(None, valor, cerca[1]).ratio() + 0.1) else None


def _primer_igual_fuera_de_comillas(linea: str) -> int | None:
    en_texto = False
    for i, ch in enumerate(linea):
        if ch == '"' and (i == 0 or linea[i - 1] != "\\"):
            en_texto = not en_texto
        elif ch == "=" and not en_texto:
            return i
    return None


# --- reglas: cada una recibe (files, problem) y devuelve (archivo, linea_idx, linea_nueva, Cambio) o None ----

def _parent_con_typo(files, p):
    m = re.search(r"StructureDefinition '([^']+)' no existe", p.message)
    s = re.search(r"¿([^?]+)\?", p.suggestion or "")
    pos = _linea(files, p)
    if p.source != "precheck" or not (m and s and pos):
        return None
    f, ls, i = pos
    if m.group(1) not in ls[i]:
        return None
    return f, i, ls[i].replace(m.group(1), s.group(1), 1), "parent_con_typo", ""


def _alias_indefinido(files, p):
    m = re.search(r"Value (\$\w+) does not resolve as alias", p.message)
    pos = _linea(files, p)
    if not (m and pos):
        return None
    malo = m.group(1)
    declarados = _alias_declarados(files)
    bueno = SINONIMOS_ALIAS.get(malo.upper())
    if bueno not in declarados:
        bueno = _unico_parecido(malo, declarados, 0.6)
    f, ls, i = pos
    if not bueno or malo not in ls[i]:
        return None
    return f, i, ls[i].replace(malo, bueno, 1), "alias_indefinido", ""


def _regla_sin_espacios(files, p):
    pos = _linea(files, p)
    if not (p.message.startswith("Assignment rules must include at least one space") and pos):
        return None
    f, ls, i = pos
    k = _primer_igual_fuera_de_comillas(ls[i])
    if k is None:
        return None
    nueva = ls[i][:k].rstrip() + " = " + ls[i][k + 1:].lstrip()
    return (f, i, nueva, "regla_sin_espacios", "") if nueva != ls[i] else None


def _slice_mal_escrito(files, p):
    m = re.search(r"The element or path you referenced does not exist: (.+)", p.message)
    pos = _linea(files, p)
    if not (m and pos):
        return None
    f, ls, i = pos
    declarados = _slices_declarados(files)
    linea = ls[i]
    for nombre in re.findall(r"\[([A-Za-z_]\w*)\]", m.group(1)):
        if nombre in declarados:
            continue
        bueno = _unico_parecido(nombre, declarados, 0.8)
        if bueno and f"[{nombre}]" in linea:
            return f, i, linea.replace(f"[{nombre}]", f"[{bueno}]"), "slice_mal_escrito", ""
    return None


def _unidad_del_perfil(files, ruta: str) -> tuple[str, str] | None:
    r = re.escape(ruta)
    for t in files.values():
        c = re.search(rf'^\*\s+{r}\.code\s*=\s*#"?([^"\s]+)"?\s*$', t, re.M)
        u = re.search(rf'^\*\s+{r}\.unit\s*=\s*"([^"]*)"\s*$', t, re.M)
        if c and u:
            return c.group(1), u.group(1)
    return None


def _valor_sin_unidad(files, p):
    m = re.search(r"Cannot assign number value: ([\d.]+)\. Value does not match element type: Quantity", p.message)
    pos = _linea(files, p)
    if not (m and pos):
        return None
    f, ls, i = pos
    mm = re.match(rf"^(\*\s+)(\S+)(\s*=\s*){re.escape(m.group(1))}\s*$", ls[i])
    if not mm:
        return None
    u = _unidad_del_perfil(files, mm.group(2))
    if not u:
        return None
    nueva = f"{mm.group(1)}{mm.group(2)} = {m.group(1)} '{u[0]}' \"{u[1]}\""
    return f, i, nueva, "valor_sin_unidad", f"se asumió que {m.group(1)} está en {u[1]} (unidad del perfil): confirmar"


def _codigo_distinto_al_perfil(files, p):
    m = re.search(r"Cannot assign \S+#(\S+) to this element; a different CodeableConcept is already assigned: (\{.*\})",
                  p.message)
    pos = _linea(files, p)
    if not (m and pos):
        return None
    try:
        codings = json.loads(m.group(2).rstrip(".")).get("coding", [])
    except ValueError:
        return None
    if len(codings) != 1:
        return None
    f, ls, i = pos
    malo, bueno = m.group(1), codings[0].get("code")
    if not bueno or f"#{malo}" not in ls[i]:
        return None
    return (f, i, ls[i].replace(f"#{malo}", f"#{bueno}", 1), "codigo_distinto_al_perfil",
            f"el perfil manda: {malo} → {bueno}; confirmar que el ejemplo corresponde a ese perfil")


def _fecha_dia_mes_anio(files, p):
    m = re.search(r"Cannot assign string value: (\S+)\. Value does not match element type: dateTime", p.message)
    pos = _linea(files, p)
    d = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", m.group(1)) if m else None
    if not (d and pos):
        return None
    try:
        iso = date(int(d.group(3)), int(d.group(2)), int(d.group(1))).isoformat()
    except ValueError:
        return None
    f, ls, i = pos
    if m.group(1) not in ls[i]:
        return None
    return f, i, ls[i].replace(m.group(1), iso, 1), "fecha_dia_mes_anio", "se leyó como día-mes-año (convención chilena); queda solo la fecha, sin hora: confirmar"


def _referencia_a_paciente(files, p):
    m = re.search(r'The type "Reference\((\w+)\)" does not match any of the allowed types: Reference\((\S+?)\)', p.message)
    pos = _linea(files, p)
    if not (m and pos):
        return None
    perfil = m.group(2).rsplit("/", 1)[-1]
    instancias = [n for t in files.values()
                  for n in re.findall(rf"^Instance:\s*(\S+)\s*\nInstanceOf:\s*{re.escape(perfil)}\s*$", t, re.M)]
    f, ls, i = pos
    ref = re.search(r"Reference\(([^)]+)\)", ls[i])
    if len(instancias) != 1 or not ref or ref.group(1) == instancias[0]:
        return None
    return (f, i, ls[i].replace(ref.group(0), f"Reference({instancias[0]})", 1), "referencia_a_paciente",
            f"única instancia de {perfil}: {instancias[0]}")


def _codigo_en_espanol(files, p):
    m = re.search(r"Unknown (\w+) code '([^']+)'", p.message) or \
        re.search(r"El valor provisto \('([^']+)'\) no está en el conjunto de valores'(\w+)'", p.message)
    if not m:
        return None
    nombre, malo = (m.group(1), m.group(2)) if m.re.pattern.startswith("Unknown") else (m.group(2), m.group(1))
    if nombre not in CODIGOS_ES:
        return None
    elemento, tabla = CODIGOS_ES[nombre]
    bueno = tabla.get(malo)
    if not bueno or bueno == malo:
        return None
    for f, t in files.items():
        for i, ln in enumerate(t.split("\n")):
            if re.fullmatch(rf"\*\s+{elemento}\s*=\s*#{re.escape(malo)}\s*", ln):
                return f, i, ln.replace(f"#{malo}", f"#{bueno}"), "codigo_en_espanol", ""
    return None


def _codigo_del_perfil_base(files, p):
    """`Cannot assign X ...; a different code is already assigned: "Y"`: el ejemplo contradice un valor fijo.

    Solo se corrige si Y NO aparece en ningún archivo del IG, es decir, si el valor fijo viene de un perfil
    base (CL Core o FHIR). Si Y está en nuestros archivos, el error puede estar en el perfil y no en el ejemplo
    (p. ej. un UCUM mal escrito en el perfil): ahí no se adivina.
    """
    m = re.search(r'Cannot assign (\S+) to this element; a different code is already assigned: "([^"]+)"', p.message)
    pos = _linea(files, p)
    if not (m and pos):
        return None
    malo, bueno = m.groups()
    f, ls, i = pos
    if f"#{malo}" not in ls[i] or any(bueno in t for t in files.values()):
        return None
    return (f, i, ls[i].replace(f"#{malo}", f"#{bueno}", 1), "codigo_del_perfil_base",
            f"el valor fijo viene de un perfil base: {malo} → {bueno}")


def _id_fhir_invalido(files, p):
    m = re.search(r'The string "([^"]+)" does not represent a valid FHIR id', p.message)
    pos = _linea(files, p)
    if not (m and pos):
        return None
    f, ls, i = pos
    bueno = re.sub(r"[^A-Za-z0-9.\-]", "-", m.group(1))[:64]
    if m.group(1) not in ls[i] or bueno == m.group(1):
        return None
    return f, i, ls[i].replace(m.group(1), bueno, 1), "id_fhir_invalido", "revisar que nada más use el id anterior"


def _texto_sin_comillas(files, p):
    m = re.search(r"mismatched input '[^']*' expecting STRING", p.message)
    pos = _linea(files, p)
    if not (m and pos):
        return None
    f, ls, i = pos
    k = re.match(r'^(Title|Description):\s*([^"\s].*)$', ls[i])
    if not k:
        return None
    return f, i, f'{k.group(1)}: "{k.group(2).strip().replace(chr(34), chr(92) + chr(34))}"', "texto_sin_comillas", ""


def _referencia_inexistente(files, p):
    m = re.search(r"Incapaz de resolver el recurso con la referencia '([^']+)'", p.message)
    if not m:
        return None
    malo = m.group(1)
    instancias = [n for t in files.values() for n in re.findall(r"^Instance:\s*(\S+)", t, re.M)]
    bueno = _unico_parecido(malo, instancias, 0.8)
    if not bueno or bueno == malo:
        return None
    for f, t in files.items():
        for i, ln in enumerate(t.split("\n")):
            if f"Reference({malo})" in ln:
                return (f, i, ln.replace(f"Reference({malo})", f"Reference({bueno})", 1), "referencia_inexistente",
                        f"nombre parecido: {malo} → {bueno}")
    return None


REGLAS = [_parent_con_typo, _alias_indefinido, _regla_sin_espacios, _slice_mal_escrito, _valor_sin_unidad,
          _codigo_distinto_al_perfil, _fecha_dia_mes_anio, _referencia_a_paciente, _codigo_en_espanol, _codigo_del_perfil_base, _id_fhir_invalido,
          _texto_sin_comillas, _referencia_inexistente]


def aplicar_reglas(files: dict[str, str], problems: list[Problem]) -> tuple[dict[str, str], list[Cambio]]:
    """Aplica todas las reglas que corresponden; devuelve los archivos nuevos y los cambios hechos."""
    nuevos = dict(files)
    cambios: list[Cambio] = []
    for p in problems:
        for regla in REGLAS:
            r = regla(nuevos, p)
            if r is None:
                continue
            f, i, nueva, nombre, nota = r
            ls = nuevos[f].split("\n")
            if ls[i] == nueva:
                continue
            cambios.append(Cambio(nombre, f"{f}:{i + 1}", ls[i].strip(), nueva.strip(), nota))
            ls[i] = nueva
            nuevos[f] = "\n".join(ls)
            break
    return nuevos, cambios
