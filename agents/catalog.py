"""Catálogo de CL Core por demanda: un índice compacto más la ficha de solo los perfiles relevantes.

Sirve para dar contexto pequeño a cualquier modelo (importante con modelos locales lentos y para
bajar costo con modelos de pago). Se alimenta de `build/catalog/catalog.json` (`python cl_ig.py catalogo`).
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

DEFAULT_CATALOG = Path("build/catalog/catalog.json")


def _fold(text: str) -> str:
    """Minúsculas y sin acentos, para comparar."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _tokens(text: str) -> set[str]:
    # separa también camelCase: "CorePacienteCl" -> core, paciente, cl
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    toks = {t for t in re.split(r"[^a-z0-9]+", _fold(spaced)) if len(t) > 1}
    # plural simple: "comunas" -> "comuna"
    return {t[:-1] if len(t) > 3 and t.endswith("s") else t for t in toks}


class CatalogIndex:
    def __init__(self, data: dict):
        self.data = data
        self.sd = {s["id"]: s for s in data["structureDefinitions"]}
        self.cs_by_id = {c["id"]: c for c in data["codeSystems"]}
        self.cs_by_url = {c["url"]: c for c in data["codeSystems"]}
        self.vs = {v["id"]: v for v in data["valueSets"]}
        self.sd_by_url = {s["url"]: s for s in data["structureDefinitions"]}
        self.vs_by_url = {v["url"]: v for v in data["valueSets"]}

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_CATALOG) -> "CatalogIndex":
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"No existe {path}. Ejecuta `python cl_ig.py catalogo`.")
        return cls(json.loads(path.read_text(encoding="utf-8")))

    # --- vistas compactas -------------------------------------------------

    def overview(self) -> str:
        """Una línea por perfil, extensión, ValueSet y CodeSystem. Pensado para ~1.000 tokens."""
        d = self.data
        lines = [f"# {d['package']} {d['version']} (FHIR {', '.join(d.get('fhirVersions') or [])})",
                 f"Canonical: {d.get('canonical')}",
                 "Usa SOLO lo listado aquí. Si no aparece, no existe en esta versión.", "", "## Perfiles de recursos"]
        for s in self.sd.values():
            if s["kind"] == "resource":
                lines.append(f"- {s['id']} ({s['type']}): {self._short(s)}")
        lines.append("\n## Extensiones y tipos complejos")
        for s in self.sd.values():
            if s["kind"] != "resource":
                lines.append(f"- {s['id']} ({s['type']}): {self._short(s)}")
        lines.append("\n## CodeSystems (id: n códigos)")
        lines.append(", ".join(f"{c['id']}: {c['count']}" for c in self.cs_by_id.values()))
        lines.append("\n## ValueSets")
        lines.append(", ".join(self.vs))
        return "\n".join(lines) + "\n"

    @staticmethod
    def _short(sd: dict, limit: int = 70) -> str:
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", sd.get("title") or sd.get("description") or "")
        return re.sub(r"\s+", " ", text).strip()[:limit]

    def profile_card(self, sd_id: str) -> str:
        """Ficha de un perfil: solo sus elementos con restricciones propias."""
        s = self.sd[sd_id]
        out = [f"### {s['id']} — {s['type']}", f"URL: {s['url']}", f"Base: {s['base']}"]
        out += ["", "| elemento | card. | tipo | MS | binding | fijo |", "|---|---|---|---|---|---|"]
        for e in s["elements"]:
            bind = f"{(e['binding'] or '').rsplit('/', 1)[-1]} ({e['strength']})" if e["binding"] else ""
            if not (e["min"] is not None or e["max"] or e["type"] or e["mustSupport"] or bind or e["fixed"]):
                continue
            card = f"{e['min'] if e['min'] is not None else ''}..{e['max'] or ''}"
            row = [e["id"], card, e["type"], "sí" if e["mustSupport"] else "", bind, e["fixed"]]
            out.append("| " + " | ".join(str(x).replace("|", "\\|") for x in row) + " |")
        return "\n".join(out) + "\n"

    # --- búsqueda ---------------------------------------------------------

    def search(self, query: str, limit: int = 5) -> list[str]:
        """Ids de perfiles ordenados por relevancia para una consulta en lenguaje natural.

        Los perfiles de recursos (Patient, Observation...) pesan más que las extensiones: casi siempre
        son lo que la consulta busca, y las extensiones llegan solas a través de sus fichas.
        """
        q = _tokens(query)
        scored = []
        for s in self.sd.values():
            score = (3 * len(q & _tokens(s["id"])) + 3 * len(q & _tokens(s["type"] or ""))
                     + 2 * len(q & _tokens(s.get("title") or "")) + len(q & _tokens(s.get("description") or "")))
            if score:
                scored.append((-(score + (2 if s["kind"] == "resource" else 0)), s["id"]))
        return [i for _, i in sorted(scored)[:limit]]

    def context(self, query: str, max_chars: int = 6000, limit: int = 3, must: tuple[str, ...] | list[str] = ()) -> str:
        """Índice compacto + fichas de los perfiles más relevantes, sin pasar de `max_chars`.

        `must` fuerza fichas concretas (van primero). Una ficha que no cabe se salta y se sigue con la
        siguiente, en vez de cortar la lista. Por búsqueda solo entran fichas de perfiles de recursos:
        las extensiones ya están en el índice y se piden con `must` cuando hacen falta.
        """
        parts = [self.overview()]
        used = len(parts[0])
        wanted = [i for i in must if i in self.sd]
        found = [i for i in self.search(query, limit=len(self.sd)) if self.sd[i]["kind"] == "resource" and i not in wanted]
        wanted += found[:limit]
        for sd_id in wanted:
            card = self.profile_card(sd_id)
            if used + len(card) > max_chars:
                continue
            parts.append(card)
            used += len(card)
        return "\n".join(parts)

    # --- terminología -----------------------------------------------------

    def concept_display(self, system_url: str, code: str) -> str | None:
        cs = self.cs_by_url.get(system_url)
        return cs["concepts"].get(code) if cs else None

    def code_systems_with(self, code: str) -> list[str]:
        """Ids de los CodeSystems de CL Core que contienen ese código."""
        return [c["id"] for c in self.cs_by_id.values() if code in c["concepts"]]
