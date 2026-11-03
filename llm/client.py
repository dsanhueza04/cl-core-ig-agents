"""Cliente único de modelos de lenguaje, independiente del proveedor, con registro de costo.

Backends:
  - ``mock``      respuestas simuladas; no usa red ni cuesta nada (por defecto, ideal para pruebas).
  - ``local``     cualquier servidor compatible con la API de OpenAI (Ollama, LM Studio, etc.).
                  Se asume gratuito: el costo se registra como 0.
  - ``anthropic`` API de Anthropic con tu propia clave. De pago: exige precio en ``pricing.json``.

Todas las llamadas pasan por ``LLMClient.complete``, que:
  1. comprueba el tope de gasto ANTES de llamar (una llamada puede excederlo levemente),
  2. registra tokens y costo en un archivo JSONL (una línea por llamada).
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol

PRICING_PATH = Path(__file__).with_name("pricing.json")


class BudgetExceeded(RuntimeError):
    """Se alcanzó el tope de gasto de la corrida."""


class LLMUnavailable(RuntimeError):
    """El servidor del modelo no respondió a tiempo o no se pudo conectar."""


class UnknownModelPricing(KeyError):
    """Un backend de pago se usó con un modelo sin precio en pricing.json."""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class LLMResponse:
    text: str
    usage: Usage
    model: str
    backend: str
    cost_usd: float = 0.0
    latency_s: float = 0.0


class Backend(Protocol):
    name: str
    paid: bool

    def complete(
        self, *, system: str, messages: list[dict], model: str, max_tokens: int, cache_system: bool
    ) -> tuple[str, Usage]: ...


# --------------------------------------------------------------------------- precios

def load_pricing(path: Path = PRICING_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def compute_cost(usage: Usage, price: Mapping[str, float]) -> float:
    """Costo en USD. `price` está en USD por millón de tokens."""
    inp = price["input"]
    cache_read = inp * price.get("cache_read_multiplier", 0.1)
    cache_write = inp * price.get("cache_write_multiplier", 1.25)
    total = (
        usage.input_tokens * inp
        + usage.output_tokens * price["output"]
        + usage.cache_read_tokens * cache_read
        + usage.cache_write_tokens * cache_write
    )
    return total / 1_000_000


# --------------------------------------------------------------------------- backends

def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockBackend:
    """Respuestas simuladas. `responses` puede ser una lista (se consume en orden) o una función."""

    name = "mock"
    paid = False

    def __init__(self, responses: list[str] | Callable[..., str] | None = None, default: str = "(respuesta simulada)"):
        self._fn = responses if callable(responses) else None
        self._queue = [] if callable(responses) else list(responses or [])
        self.default = default
        self.calls: list[dict] = []

    def complete(self, *, system, messages, model, max_tokens, cache_system, json_mode=False):
        self.calls.append({"system": system, "messages": messages, "model": model, "max_tokens": max_tokens,
                           "json_mode": json_mode})
        if self._fn:
            text = self._fn(system=system, messages=messages, model=model)
        elif self._queue:
            text = self._queue.pop(0)
        else:
            text = self.default
        prompt = system + "".join(m.get("content", "") for m in messages)
        return text, Usage(input_tokens=_estimate_tokens(prompt), output_tokens=_estimate_tokens(text))


class OpenAICompatBackend:
    """Servidor compatible con la API de OpenAI (`/chat/completions`). Por defecto, Ollama local."""

    paid = False

    def __init__(self, base_url: str = "http://localhost:11434/v1", api_key: str | None = None,
                 timeout: float = 600.0, name: str = "local"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.name = name

    def complete(self, *, system, messages, model, max_tokens, cache_system, json_mode=False):
        if str(model).startswith("claude"):   # error típico: falta LLM_MODEL con el backend local
            raise LLMUnavailable(f"El backend local no sirve el modelo '{model}' (es un modelo de pago). "
                                 "Define LLM_MODEL, por ejemplo: export LLM_MODEL=qwen2.5:7b")
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        if json_mode:   # el servidor restringe la salida a JSON válido
            body["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps(body).encode("utf-8"), headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except (TimeoutError, OSError) as exc:   # incluye URLError y errores de conexión
            raise LLMUnavailable(f"El modelo local no respondió ({type(exc).__name__}: {exc}). "
                                 f"Espera máxima: {self.timeout:.0f} s (LLM_TIMEOUT_S).") from exc
        text = data["choices"][0]["message"].get("content") or ""
        u = data.get("usage") or {}
        return text, Usage(input_tokens=u.get("prompt_tokens", 0), output_tokens=u.get("completion_tokens", 0))


class AnthropicBackend:
    """API de Anthropic. Requiere `pip install anthropic` y tu propia clave."""

    name = "anthropic"
    paid = True

    def __init__(self, api_key: str | None = None):
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Falta el paquete 'anthropic': pip install anthropic") from exc
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, *, system, messages, model, max_tokens, cache_system, json_mode=False):  # pragma: no cover (requiere red)
        block: dict = {"type": "text", "text": system}
        if cache_system:
            block["cache_control"] = {"type": "ephemeral"}
        resp = self._client.messages.create(model=model, max_tokens=max_tokens, system=[block], messages=messages)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        u = resp.usage
        return text, Usage(
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )


# --------------------------------------------------------------------------- cliente

class LLMClient:
    def __init__(self, backend: Backend, *, pricing: dict | None = None, log_path: str | Path | None = None,
                 max_cost_usd: float | None = None, run_id: str | None = None, log_text: bool = False):
        self.backend = backend
        self.log_text = log_text
        self.pricing = pricing if pricing is not None else load_pricing()
        self.max_cost_usd = max_cost_usd
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:6]
        self.log_path = Path(log_path) if log_path else Path("runs") / self.run_id / "llm_calls.jsonl"
        self.total_cost_usd = 0.0
        self._by_agent: dict[str, dict] = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})

    def _price(self, model: str) -> Mapping[str, float] | None:
        if not self.backend.paid:
            return None  # gratuito: costo 0
        try:
            return self.pricing["models"][model]
        except KeyError:
            raise UnknownModelPricing(f"Sin precio para '{model}'. Agrégalo a llm/pricing.json.") from None

    def complete(self, *, agent: str, model: str, system: str, messages: list[dict],
                 max_tokens: int = 4096, iteration: int = 0, cache_system: bool = False,
                 json_mode: bool = False) -> LLMResponse:
        if self.max_cost_usd is not None and self.total_cost_usd >= self.max_cost_usd:
            raise BudgetExceeded(f"Tope de {self.max_cost_usd:.2f} USD alcanzado (gastado: {self.total_cost_usd:.4f} USD).")
        price = self._price(model)  # falla antes de llamar si no hay precio
        start = time.monotonic()
        try:
            extra = {"json_mode": True} if json_mode else {}   # solo si se pide: los backends ajenos no cambian
            text, usage = self.backend.complete(
                system=system, messages=messages, model=model, max_tokens=max_tokens, cache_system=cache_system, **extra
            )
        except LLMUnavailable as exc:   # queda constancia de la llamada fallida en el registro
            self._log({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run_id": self.run_id,
                       "agent": agent, "iteration": iteration, "backend": self.backend.name, "model": model,
                       "error": str(exc), "latency_s": round(time.monotonic() - start, 3)})
            raise
        latency = time.monotonic() - start
        cost = compute_cost(usage, price) if price else 0.0
        self.total_cost_usd += cost

        stats = self._by_agent[agent]
        stats["calls"] += 1
        stats["input_tokens"] += usage.input_tokens
        stats["output_tokens"] += usage.output_tokens
        stats["cost_usd"] += cost

        self._log({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_id": self.run_id, "agent": agent, "iteration": iteration,
            "backend": self.backend.name, "model": model, **asdict(usage),
            "cost_usd": round(cost, 8), "total_cost_usd": round(self.total_cost_usd, 8),
            "latency_s": round(latency, 3),
        })
        if self.log_text:   # prompts y respuestas completos, para depurar (solo en local, no se versiona)
            self._log({"run_id": self.run_id, "agent": agent, "iteration": iteration, "system": system,
                       "messages": messages, "response": text}, name="llm_texts.jsonl")
        return LLMResponse(text=text, usage=usage, model=model, backend=self.backend.name,
                           cost_usd=cost, latency_s=latency)

    def _log(self, record: dict, name: str | None = None) -> None:
        path = self.log_path.with_name(name) if name else self.log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def summary(self) -> dict:
        return {
            "run_id": self.run_id,
            "backend": self.backend.name,
            "calls": sum(s["calls"] for s in self._by_agent.values()),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "by_agent": {k: dict(v) for k, v in self._by_agent.items()},
        }


def client_from_env(env: Mapping[str, str] | None = None, **kwargs) -> LLMClient:
    """Construye el cliente según variables de entorno. Sin configurar, usa `mock` (gratis)."""
    env = os.environ if env is None else env
    kind = env.get("LLM_BACKEND", "mock").strip().lower()
    if kind == "mock":
        backend: Backend = MockBackend()
    elif kind == "local":
        backend = OpenAICompatBackend(env.get("LLM_BASE_URL", "http://localhost:11434/v1"), env.get("LLM_API_KEY"),
                                      timeout=float(env.get("LLM_TIMEOUT_S", "1800")))
    elif kind == "anthropic":
        backend = AnthropicBackend(env.get("ANTHROPIC_API_KEY"))
    else:
        raise ValueError(f"LLM_BACKEND desconocido: '{kind}' (usa mock, local o anthropic)")
    cap = env.get("MAX_COST_USD_PER_RUN")
    kwargs.setdefault("max_cost_usd", float(cap) if cap else None)
    return LLMClient(backend, **kwargs)
