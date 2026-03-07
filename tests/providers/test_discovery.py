from __future__ import annotations

from clawlite.providers.discovery import detect_local_runtime
from clawlite.providers.discovery import probe_local_provider_runtime


def test_detect_local_runtime_distinguishes_ollama_and_vllm() -> None:
    assert detect_local_runtime("http://127.0.0.1:11434") == "ollama"
    assert detect_local_runtime("http://127.0.0.1:8000/v1") == "vllm"
    assert detect_local_runtime("https://api.openai.com/v1") == ""


def test_detect_local_runtime_does_not_assume_generic_loopback_is_vllm() -> None:
    assert detect_local_runtime("http://127.0.0.1:4000/v1") == ""
    assert detect_local_runtime("http://localhost:1234/v1") == ""


def test_probe_local_provider_runtime_accepts_ollama_show_fallback(monkeypatch) -> None:
    class _Response:
        def __init__(self, status_code: int, payload):
            self.status_code = status_code
            self._payload = payload
            self.is_success = 200 <= status_code < 300

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *, timeout):
            assert timeout >= 0.5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            assert url == "http://127.0.0.1:11434/api/tags"
            return _Response(200, {"models": [{"name": "qwen2.5:latest"}]})

        def post(self, url, json):
            assert url == "http://127.0.0.1:11434/api/show"
            assert json == {"name": "llama3.2"}
            return _Response(200, {"details": {"format": "gguf"}})

    monkeypatch.setattr("clawlite.providers.discovery.httpx.Client", _Client)
    payload = probe_local_provider_runtime(model="openai/llama3.2", base_url="http://127.0.0.1:11434")

    assert payload["checked"] is True
    assert payload["ok"] is True
    assert payload["runtime"] == "ollama"


def test_probe_local_provider_runtime_rejects_missing_vllm_model(monkeypatch) -> None:
    class _Response:
        def __init__(self, status_code: int, payload):
            self.status_code = status_code
            self._payload = payload
            self.is_success = 200 <= status_code < 300

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *, timeout):
            assert timeout >= 0.5

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            if url == "http://127.0.0.1:8000/health":
                return _Response(200, {"status": "ok"})
            if url == "http://127.0.0.1:8000/v1/models":
                return _Response(200, {"data": [{"id": "qwen2.5"}]})
            raise AssertionError(url)

    monkeypatch.setattr("clawlite.providers.discovery.httpx.Client", _Client)
    payload = probe_local_provider_runtime(model="openai/llama3.2", base_url="http://127.0.0.1:8000")

    assert payload["checked"] is True
    assert payload["ok"] is False
    assert payload["runtime"] == "vllm"
    assert payload["error"] == "provider_config_error:vllm_model_missing:llama3.2"
