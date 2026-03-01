from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import httpx

from clawlite.runtime.offline import ProviderExecutionError, run_remote_provider, run_with_offline_fallback


class RemoteProviderTests(unittest.TestCase):
    @staticmethod
    def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
        request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
        response = httpx.Response(status_code, request=request, text='{"error":"rate_limit"}')
        return httpx.HTTPStatusError(f"status {status_code}", request=request, response=response)

    def test_provider_selection_openrouter_uses_chat_completions(self) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "ok-openrouter"}}],
        }

        client = MagicMock()
        client.post.return_value = response

        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False

        with patch("clawlite.runtime.offline.httpx.Client", return_value=cm):
            out = run_remote_provider("ping", "openrouter/openai/gpt-4o-mini", "cfg-token")

        self.assertEqual(out, "ok-openrouter")
        args, kwargs = client.post.call_args
        self.assertEqual(args[0], "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(kwargs["json"]["model"], "openai/gpt-4o-mini")

    def test_missing_token_raises_error_ptbr(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            with self.assertRaises(ProviderExecutionError) as ctx:
                run_remote_provider("oi", "openai/gpt-4o-mini", "")

        self.assertIn("token ausente", str(ctx.exception))
        self.assertIn("openai", str(ctx.exception))

    def test_openai_response_parsing(self) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "resposta-openai"}}],
        }

        client = MagicMock()
        client.post.return_value = response

        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False

        with patch("clawlite.runtime.offline.httpx.Client", return_value=cm):
            out = run_remote_provider("ping", "openai/gpt-4o-mini", "cfg-token")

        self.assertEqual(out, "resposta-openai")

    def test_provider_selection_openai_codex_uses_openai_chat_completions(self) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "ok-codex"}}],
        }

        client = MagicMock()
        client.post.return_value = response

        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False

        with patch("clawlite.runtime.offline.httpx.Client", return_value=cm):
            out = run_remote_provider("ping", "openai-codex/gpt-5.3-codex", "cfg-token")

        self.assertEqual(out, "ok-codex")
        args, kwargs = client.post.call_args
        self.assertEqual(args[0], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(kwargs["json"]["model"], "gpt-5.3-codex")

    def test_provider_selection_gemini_uses_openai_compat_url(self) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "ok-gemini"}}],
        }

        client = MagicMock()
        client.post.return_value = response

        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False

        with patch("clawlite.runtime.offline.httpx.Client", return_value=cm):
            out = run_remote_provider("ping", "gemini/gemini-2.5-flash", "cfg-token")

        self.assertEqual(out, "ok-gemini")
        args, kwargs = client.post.call_args
        self.assertEqual(args[0], "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
        self.assertEqual(kwargs["json"]["model"], "gemini-2.5-flash")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer cfg-token")

    def test_gemini_429_retries_then_succeeds(self) -> None:
        response_429_a = MagicMock()
        response_429_a.raise_for_status.side_effect = self._http_status_error(429)

        response_429_b = MagicMock()
        response_429_b.raise_for_status.side_effect = self._http_status_error(429)

        response_ok = MagicMock()
        response_ok.raise_for_status.return_value = None
        response_ok.json.return_value = {
            "choices": [{"message": {"content": "ok-after-retry"}}],
        }

        client = MagicMock()
        client.post.side_effect = [response_429_a, response_429_b, response_ok]

        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False

        with patch("clawlite.runtime.offline.httpx.Client", return_value=cm):
            with patch("clawlite.runtime.offline.time.sleep") as sleep_mock:
                out = run_remote_provider("ping", "gemini/gemini-2.5-flash", "cfg-token")

        self.assertEqual(out, "ok-after-retry")
        self.assertEqual(client.post.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)
        sleep_mock.assert_called_with(60.0)

    def test_gemini_429_exhausted_returns_clear_message(self) -> None:
        response_429_a = MagicMock()
        response_429_a.raise_for_status.side_effect = self._http_status_error(429)

        response_429_b = MagicMock()
        response_429_b.raise_for_status.side_effect = self._http_status_error(429)

        response_429_c = MagicMock()
        response_429_c.raise_for_status.side_effect = self._http_status_error(429)

        client = MagicMock()
        client.post.side_effect = [response_429_a, response_429_b, response_429_c]

        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False

        with patch("clawlite.runtime.offline.httpx.Client", return_value=cm):
            with patch("clawlite.runtime.offline.time.sleep") as sleep_mock:
                with self.assertRaises(ProviderExecutionError) as ctx:
                    run_remote_provider("ping", "gemini/gemini-2.5-flash", "cfg-token")

        message = str(ctx.exception).lower()
        self.assertIn("limite de requisições", message)
        self.assertNotIn("erro http", message)
        self.assertEqual(client.post.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_anthropic_response_parsing(self) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "content": [
                {"type": "text", "text": "linha 1"},
                {"type": "text", "text": "linha 2"},
            ]
        }

        client = MagicMock()
        client.post.return_value = response

        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False

        with patch("clawlite.runtime.offline.httpx.Client", return_value=cm):
            out = run_remote_provider("ping", "anthropic/claude-sonnet-4-5", "cfg-token")

        self.assertEqual(out, "linha 1\nlinha 2")

    def test_provider_selection_minimax_uses_anthropic_messages(self) -> None:
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "content": [{"type": "text", "text": "ok-minimax"}],
        }

        client = MagicMock()
        client.post.return_value = response

        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False

        with patch("clawlite.runtime.offline.httpx.Client", return_value=cm):
            out = run_remote_provider("ping", "minimax/MiniMax-M2.1", "cfg-token")

        self.assertEqual(out, "ok-minimax")
        args, kwargs = client.post.call_args
        self.assertEqual(args[0], "https://api.minimax.io/anthropic/messages")
        self.assertEqual(kwargs["json"]["model"], "MiniMax-M2.1")
        self.assertEqual(kwargs["headers"]["x-api-key"], "cfg-token")

    def test_timeout_error_triggers_offline_fallback(self) -> None:
        cfg = {
            "model": "openai/gpt-4o-mini",
            "offline_mode": {"enabled": True, "auto_fallback_to_ollama": True},
            "model_fallback": ["ollama/tinyllama"],
            "auth": {"providers": {"openai": {"token": "token"}}},
        }

        with patch("clawlite.runtime.offline.httpx.Client", side_effect=httpx.TimeoutException("timeout")):
            with patch("clawlite.runtime.offline.check_connectivity", return_value=True):
                out, meta = run_with_offline_fallback(
                    "teste",
                    cfg,
                    ollama_executor=lambda prompt, model: f"{model}:{prompt}",
                )

        self.assertEqual(out, "tinyllama:teste")
        self.assertEqual(meta["mode"], "offline-fallback")
        self.assertEqual(meta["reason"], "provider_failure")
        self.assertIn("timeout", meta.get("error", "").lower())

    def test_http_status_error_triggers_offline_fallback(self) -> None:
        cfg = {
            "model": "openai/gpt-4o-mini",
            "offline_mode": {"enabled": True, "auto_fallback_to_ollama": True},
            "model_fallback": ["ollama/tinyllama"],
            "auth": {"providers": {"openai": {"token": "token"}}},
        }

        response = httpx.Response(401, text='{"error":"unauthorized"}', request=httpx.Request("POST", "https://api.openai.com"))

        client = MagicMock()
        client.post.return_value = response

        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False

        with patch("clawlite.runtime.offline.httpx.Client", return_value=cm):
            with patch("clawlite.runtime.offline.check_connectivity", return_value=True):
                out, meta = run_with_offline_fallback(
                    "teste",
                    cfg,
                    ollama_executor=lambda prompt, model: f"{model}:{prompt}",
                )

        self.assertEqual(out, "tinyllama:teste")
        self.assertEqual(meta["mode"], "offline-fallback")
        self.assertEqual(meta["reason"], "provider_failure")
        self.assertIn("erro http", meta.get("error", "").lower())


if __name__ == "__main__":
    unittest.main()
