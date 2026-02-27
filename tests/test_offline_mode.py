from __future__ import annotations

import unittest
from unittest.mock import patch

from clawlite.runtime.offline import ProviderExecutionError, run_with_offline_fallback


class OfflineModeTests(unittest.TestCase):
    def test_fallbacks_to_ollama_when_connectivity_is_down(self) -> None:
        cfg = {
            "model": "openai/gpt-4o-mini",
            "offline_mode": {"enabled": True, "auto_fallback_to_ollama": True},
            "model_fallback": ["openrouter/auto", "ollama/tinyllama"],
            "auth": {"providers": {"openai": {"token": "token"}}},
        }

        def fake_ollama(prompt: str, model: str) -> str:
            return f"{model}:{prompt}"

        with patch("clawlite.runtime.offline.check_connectivity", return_value=False):
            out, meta = run_with_offline_fallback(
                "olá",
                cfg,
                online_executor=lambda *_: "should-not-run",
                ollama_executor=fake_ollama,
            )

        self.assertEqual(out, "tinyllama:olá")
        self.assertEqual(meta["mode"], "offline-fallback")
        self.assertEqual(meta["reason"], "connectivity")

    def test_fallbacks_to_ollama_when_provider_fails(self) -> None:
        cfg = {
            "model": "openai/gpt-4o-mini",
            "offline_mode": {"enabled": True, "auto_fallback_to_ollama": True},
            "model_fallback": ["ollama/llama3.1:8b"],
            "auth": {"providers": {"openai": {"token": "token"}}},
        }

        def failing_online(*_args: str) -> str:
            raise ProviderExecutionError("boom")

        with patch("clawlite.runtime.offline.check_connectivity", return_value=True):
            out, meta = run_with_offline_fallback(
                "teste",
                cfg,
                online_executor=failing_online,
                ollama_executor=lambda prompt, model: f"{model}:{prompt}",
            )

        self.assertEqual(out, "llama3.1:8b:teste")
        self.assertEqual(meta["mode"], "offline-fallback")
        self.assertEqual(meta["reason"], "provider_failure")


if __name__ == "__main__":
    unittest.main()
