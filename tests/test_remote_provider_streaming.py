from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import httpx

from clawlite.runtime.offline import ProviderExecutionError
from clawlite.runtime.streaming import run_remote_provider_stream


class RemoteProviderStreamingTests(unittest.TestCase):
    @staticmethod
    def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
        request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
        response = httpx.Response(status_code, request=request, text='{"error":"rate_limit"}')
        return httpx.HTTPStatusError(f"status {status_code}", request=request, response=response)

    def test_gemini_stream_429_retries_then_succeeds(self) -> None:
        stream_429_a = MagicMock()
        stream_429_a.raise_for_status.side_effect = self._http_status_error(429)

        stream_429_b = MagicMock()
        stream_429_b.raise_for_status.side_effect = self._http_status_error(429)

        stream_ok = MagicMock()
        stream_ok.raise_for_status.return_value = None
        stream_ok.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"ok"}}]}',
            "data: [DONE]",
        ]

        cm_stream_429_a = MagicMock()
        cm_stream_429_a.__enter__.return_value = stream_429_a
        cm_stream_429_a.__exit__.return_value = False

        cm_stream_429_b = MagicMock()
        cm_stream_429_b.__enter__.return_value = stream_429_b
        cm_stream_429_b.__exit__.return_value = False

        cm_stream_ok = MagicMock()
        cm_stream_ok.__enter__.return_value = stream_ok
        cm_stream_ok.__exit__.return_value = False

        client = MagicMock()
        client.stream.side_effect = [cm_stream_429_a, cm_stream_429_b, cm_stream_ok]

        cm_client = MagicMock()
        cm_client.__enter__.return_value = client
        cm_client.__exit__.return_value = False

        with patch("clawlite.runtime.streaming.httpx.Client", return_value=cm_client):
            with patch("clawlite.runtime.streaming.time.sleep") as sleep_mock:
                out = "".join(run_remote_provider_stream("ping", "gemini/gemini-2.5-flash", "cfg-token"))

        self.assertEqual(out, "ok")
        self.assertEqual(client.stream.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)
        sleep_mock.assert_called_with(60.0)

    def test_codex_oauth_stream_uses_codex_runtime(self) -> None:
        with patch(
            "clawlite.runtime.streaming.resolve_codex_account_id",
            return_value="acc_123",
        ) as account_mock:
            with patch(
                "clawlite.runtime.streaming.run_codex_oauth_stream",
                return_value=iter(["co", "dex"]),
            ) as codex_mock:
                out = "".join(run_remote_provider_stream("ping", "openai-codex/gpt-5.3-codex", "oauth-token"))

        self.assertEqual(out, "codex")
        account_mock.assert_called_once()
        codex_mock.assert_called_once()
        kwargs = codex_mock.call_args.kwargs
        self.assertEqual(kwargs["prompt"], "ping")
        self.assertEqual(kwargs["model"], "gpt-5.3-codex")
        self.assertEqual(kwargs["access_token"], "oauth-token")
        self.assertEqual(kwargs["account_id"], "acc_123")

    def test_gemini_stream_429_exhausted_returns_clear_message(self) -> None:
        stream_429_a = MagicMock()
        stream_429_a.raise_for_status.side_effect = self._http_status_error(429)

        stream_429_b = MagicMock()
        stream_429_b.raise_for_status.side_effect = self._http_status_error(429)

        stream_429_c = MagicMock()
        stream_429_c.raise_for_status.side_effect = self._http_status_error(429)

        cm_stream_429_a = MagicMock()
        cm_stream_429_a.__enter__.return_value = stream_429_a
        cm_stream_429_a.__exit__.return_value = False

        cm_stream_429_b = MagicMock()
        cm_stream_429_b.__enter__.return_value = stream_429_b
        cm_stream_429_b.__exit__.return_value = False

        cm_stream_429_c = MagicMock()
        cm_stream_429_c.__enter__.return_value = stream_429_c
        cm_stream_429_c.__exit__.return_value = False

        client = MagicMock()
        client.stream.side_effect = [cm_stream_429_a, cm_stream_429_b, cm_stream_429_c]

        cm_client = MagicMock()
        cm_client.__enter__.return_value = client
        cm_client.__exit__.return_value = False

        with patch("clawlite.runtime.streaming.httpx.Client", return_value=cm_client):
            with patch("clawlite.runtime.streaming.time.sleep") as sleep_mock:
                with self.assertRaises(ProviderExecutionError) as ctx:
                    "".join(run_remote_provider_stream("ping", "gemini/gemini-2.5-flash", "cfg-token"))

        message = str(ctx.exception).lower()
        self.assertIn("limite de requisições", message)
        self.assertNotIn("erro http", message)
        self.assertEqual(client.stream.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
