"""Pruebas del cliente LLM: costos, tope de gasto, registro y backends (sin red externa)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from llm import (
    BudgetExceeded,
    LLMClient,
    MockBackend,
    OpenAICompatBackend,
    UnknownModelPricing,
    Usage,
    client_from_env,
    compute_cost,
    load_pricing,
)


class FakePaidBackend:
    """Backend de pago falso con uso de tokens conocido."""

    name = "fake-paid"
    paid = True

    def __init__(self, usage: Usage):
        self.usage = usage
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        return "ok", self.usage


def ask(client, model="claude-sonnet-5-5", agent="perfiles", **kw):
    return client.complete(agent=agent, model=model, system="s", messages=[{"role": "user", "content": "hola"}], **kw)


# --- costos ----------------------------------------------------------------

def test_cost_sonnet_one_million_in_and_out():
    price = load_pricing()["models"]["claude-sonnet-5-5"]
    assert compute_cost(Usage(input_tokens=1_000_000, output_tokens=1_000_000), price) == pytest.approx(12.0)


def test_cost_cache_read_default_is_a_tenth_and_write_is_1_25x():
    price = {"input": 2.0, "output": 10.0}
    assert compute_cost(Usage(cache_read_tokens=1_000_000), price) == pytest.approx(0.2)
    assert compute_cost(Usage(cache_write_tokens=1_000_000), price) == pytest.approx(2.5)


def test_cost_cache_read_multiplier_override_for_opus():
    price = load_pricing()["models"]["claude-opus-5-5"]
    assert compute_cost(Usage(cache_read_tokens=1_000_000), price) == pytest.approx(0.2)  # 4 USD x 0.05


def test_paid_backend_cost_is_accumulated(tmp_path):
    backend = FakePaidBackend(Usage(input_tokens=500_000, output_tokens=100_000))
    client = LLMClient(backend, log_path=tmp_path / "log.jsonl")
    r = ask(client)
    assert r.cost_usd == pytest.approx(1.0 + 1.0)  # 0.5M x 2 + 0.1M x 10
    ask(client)
    assert client.total_cost_usd == pytest.approx(4.0)


def test_paid_backend_unknown_model_fails_before_calling(tmp_path):
    backend = FakePaidBackend(Usage())
    client = LLMClient(backend, log_path=tmp_path / "log.jsonl")
    with pytest.raises(UnknownModelPricing):
        ask(client, model="modelo-inexistente")
    assert backend.calls == 0


def test_free_backends_cost_zero_even_for_unlisted_models(tmp_path):
    client = LLMClient(MockBackend(), log_path=tmp_path / "log.jsonl")
    assert ask(client, model="llama3.1:8b").cost_usd == 0.0
    assert client.total_cost_usd == 0.0


# --- tope de gasto ---------------------------------------------------------

def test_budget_blocks_next_call_once_reached(tmp_path):
    backend = FakePaidBackend(Usage(input_tokens=500_000, output_tokens=100_000))  # 2 USD por llamada
    client = LLMClient(backend, log_path=tmp_path / "log.jsonl", max_cost_usd=3.0)
    ask(client)  # 2 USD
    ask(client)  # 4 USD (la llamada puede exceder levemente el tope)
    with pytest.raises(BudgetExceeded):
        ask(client)
    assert backend.calls == 2


def test_no_budget_means_unlimited(tmp_path):
    client = LLMClient(FakePaidBackend(Usage(input_tokens=1_000_000)), log_path=tmp_path / "log.jsonl")
    for _ in range(3):
        ask(client)


# --- registro --------------------------------------------------------------

def test_every_call_is_logged_as_jsonl(tmp_path):
    log = tmp_path / "sub" / "log.jsonl"
    client = LLMClient(MockBackend(["uno", "dos"]), log_path=log, run_id="r1")
    ask(client, agent="analista", iteration=0)
    ask(client, agent="reparador", iteration=2)
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert [r["agent"] for r in rows] == ["analista", "reparador"]
    assert rows[1]["iteration"] == 2 and rows[1]["run_id"] == "r1" and rows[1]["backend"] == "mock"
    assert {"input_tokens", "output_tokens", "cost_usd", "total_cost_usd", "latency_s", "model"} <= set(rows[0])


def test_summary_groups_by_agent(tmp_path):
    client = LLMClient(MockBackend(), log_path=tmp_path / "log.jsonl")
    ask(client, agent="a")
    ask(client, agent="a")
    ask(client, agent="b")
    s = client.summary()
    assert s["calls"] == 3 and s["by_agent"]["a"]["calls"] == 2 and s["by_agent"]["b"]["calls"] == 1


# --- mock ------------------------------------------------------------------

def test_mock_replays_queue_then_default(tmp_path):
    client = LLMClient(MockBackend(["a", "b"], default="fin"), log_path=tmp_path / "log.jsonl")
    assert [ask(client).text for _ in range(3)] == ["a", "b", "fin"]


def test_mock_accepts_function_and_records_calls(tmp_path):
    backend = MockBackend(lambda system, messages, model: f"eco:{messages[-1]['content']}")
    client = LLMClient(backend, log_path=tmp_path / "log.jsonl")
    assert ask(client).text == "eco:hola"
    assert backend.calls[0]["model"] == "claude-sonnet-5-5"


# --- backend compatible con OpenAI (servidor falso local) -------------------

class _Handler(BaseHTTPRequestHandler):
    seen: dict = {}

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen = {"path": self.path, "body": body, "auth": self.headers.get("Authorization")}
        payload = json.dumps({
            "choices": [{"message": {"content": "Profile: Demo"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def test_openai_compat_backend_roundtrip(fake_server, tmp_path):
    client = LLMClient(OpenAICompatBackend(fake_server, api_key="clave"), log_path=tmp_path / "log.jsonl")
    r = ask(client, model="llama3.1:8b")
    assert r.text == "Profile: Demo"
    assert (r.usage.input_tokens, r.usage.output_tokens) == (12, 5)
    assert r.cost_usd == 0.0
    seen = _Handler.seen
    assert seen["path"] == "/v1/chat/completions" and seen["auth"] == "Bearer clave"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "s"}
    assert seen["body"]["model"] == "llama3.1:8b"


# --- configuración por entorno ----------------------------------------------

def test_default_backend_is_free_mock(tmp_path):
    client = client_from_env({}, log_path=tmp_path / "log.jsonl")
    assert client.backend.name == "mock" and client.max_cost_usd is None


def test_env_local_backend_and_cap(tmp_path):
    env = {"LLM_BACKEND": "local", "LLM_BASE_URL": "http://localhost:1234/v1", "MAX_COST_USD_PER_RUN": "0.5"}
    client = client_from_env(env, log_path=tmp_path / "log.jsonl")
    assert client.backend.name == "local" and client.backend.base_url == "http://localhost:1234/v1"
    assert client.max_cost_usd == 0.5


def test_env_unknown_backend_is_rejected():
    with pytest.raises(ValueError):
        client_from_env({"LLM_BACKEND": "otro"})


def test_log_text_saves_prompt_and_response_next_to_the_log(tmp_path):
    client = LLMClient(MockBackend(["respuesta"]), log_path=tmp_path / "r" / "log.jsonl", log_text=True)
    ask(client)
    row = json.loads((tmp_path / "r" / "llm_texts.jsonl").read_text(encoding="utf-8"))
    assert row["response"] == "respuesta" and row["messages"][0]["content"] == "hola"


def test_text_is_not_logged_by_default(tmp_path):
    ask(LLMClient(MockBackend(), log_path=tmp_path / "log.jsonl"))
    assert not (tmp_path / "llm_texts.jsonl").exists()


def test_timeout_becomes_llm_unavailable_and_is_logged(tmp_path):
    from llm import LLMUnavailable
    # servidor que acepta la conexión y no responde: la espera máxima debe cortar
    import socket
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    client = LLMClient(OpenAICompatBackend(f"http://127.0.0.1:{srv.getsockname()[1]}/v1", timeout=0.3),
                       log_path=tmp_path / "log.jsonl")
    with pytest.raises(LLMUnavailable):
        ask(client, model="m")
    srv.close()
    row = json.loads((tmp_path / "log.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "no respondió" in row["error"]


def test_env_timeout_is_configurable():
    c = client_from_env({"LLM_BACKEND": "local", "LLM_TIMEOUT_S": "42"})
    assert c.backend.timeout == 42.0
    assert client_from_env({"LLM_BACKEND": "local"}).backend.timeout == 1800.0


def test_json_mode_is_sent_to_openai_compatible_servers_only_when_requested(fake_server, tmp_path):
    client = LLMClient(OpenAICompatBackend(fake_server), log_path=tmp_path / "log.jsonl")
    ask(client, model="m", json_mode=True)
    assert _Handler.seen["body"]["response_format"] == {"type": "json_object"}
    ask(client, model="m")
    assert "response_format" not in _Handler.seen["body"]


def test_json_mode_flag_reaches_mock_and_is_omitted_for_foreign_backends(tmp_path):
    mock = MockBackend()
    ask(LLMClient(mock, log_path=tmp_path / "a.jsonl"), json_mode=True)
    assert mock.calls[0]["json_mode"] is True
    paid = FakePaidBackend(Usage())   # su complete(**kwargs) no debe recibir json_mode si no se pidió
    ask(LLMClient(paid, log_path=tmp_path / "b.jsonl"))
    assert paid.calls == 1


def test_local_backend_rejects_a_claude_model_name_with_a_clear_message():
    from llm import LLMUnavailable
    from llm.client import OpenAICompatBackend
    with pytest.raises(LLMUnavailable, match="LLM_MODEL"):
        OpenAICompatBackend().complete(system="s", messages=[], model="claude-sonnet-5-5", max_tokens=10, cache_system=False)
