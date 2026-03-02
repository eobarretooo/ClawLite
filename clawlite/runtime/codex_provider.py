from __future__ import annotations

import json
from typing import Any, Iterator

import httpx

DEFAULT_CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"
DEFAULT_ORIGINATOR = "clawlite"


class CodexExecutionError(RuntimeError):
    """Erro ao executar requisição via Codex OAuth."""


def strip_codex_model_prefix(model: str) -> str:
    value = str(model or "").strip()
    if value.startswith("openai-codex/") or value.startswith("openai_codex/"):
        return value.split("/", 1)[1]
    return value


def _build_headers(account_id: str, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "chatgpt-account-id": account_id,
        "OpenAI-Beta": "responses=experimental",
        "originator": DEFAULT_ORIGINATOR,
        "User-Agent": "clawlite (python)",
        "accept": "text/event-stream",
        "content-type": "application/json",
    }


def _request_body(prompt: str, model: str) -> dict[str, Any]:
    return {
        "model": strip_codex_model_prefix(model),
        "store": False,
        "stream": True,
        "instructions": "",
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        "text": {"verbosity": "medium"},
        "include": ["reasoning.encrypted_content"],
        "tool_choice": "none",
    }


def _is_ssl_verify_error(exc: Exception) -> bool:
    raw = str(exc).upper()
    return "CERTIFICATE_VERIFY_FAILED" in raw or "SSL" in raw


def _friendly_error(status_code: int, raw: str) -> str:
    if status_code == 429:
        return "Codex atingiu limite de uso/requisição temporariamente. Tente novamente em alguns minutos."
    if status_code == 401:
        return "Codex OAuth inválido/expirado. Rode `clawlite auth login openai-codex` novamente."
    if status_code == 403:
        return "A conta atual não tem acesso ao Codex (verifique plano ChatGPT Plus/Pro)."
    return f"HTTP {status_code}: {raw}"


def _iter_sse_events(response: httpx.Response) -> Iterator[dict[str, Any]]:
    buffer: list[str] = []
    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8", "ignore") if isinstance(raw_line, bytes) else str(raw_line)
        line = line.rstrip("\r\n")
        if line == "":
            if not buffer:
                continue
            data_lines = [entry[5:].strip() for entry in buffer if entry.startswith("data:")]
            buffer = []
            if not data_lines:
                continue
            payload = "\n".join(data_lines).strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                loaded = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                yield loaded
            continue
        buffer.append(line)


def _iter_codex_text_chunks(
    *,
    prompt: str,
    model: str,
    access_token: str,
    account_id: str,
    timeout: float,
    verify: bool,
) -> Iterator[str]:
    headers = _build_headers(account_id, access_token)
    body = _request_body(prompt, model)
    saw_delta = False
    fallback_done_text = ""

    with httpx.Client(timeout=timeout, verify=verify) as client:
        with client.stream("POST", DEFAULT_CODEX_URL, headers=headers, json=body) as response:
            if response.status_code != 200:
                raw = response.read().decode("utf-8", "ignore")
                raise CodexExecutionError(_friendly_error(response.status_code, raw))

            for event in _iter_sse_events(response):
                event_type = str(event.get("type", "")).strip()

                if event_type == "response.output_text.delta":
                    delta = str(event.get("delta") or "")
                    if delta:
                        saw_delta = True
                        yield delta
                    continue

                if event_type == "response.output_item.done":
                    item = event.get("item") if isinstance(event.get("item"), dict) else {}
                    if item.get("type") != "message":
                        continue
                    contents = item.get("content", [])
                    if not isinstance(contents, list):
                        continue
                    parts: list[str] = []
                    for part in contents:
                        if not isinstance(part, dict):
                            continue
                        if part.get("type") in {"output_text", "text"}:
                            text = str(part.get("text") or "").strip()
                            if text:
                                parts.append(text)
                    if parts:
                        fallback_done_text = "\n".join(parts)
                    continue

                if event_type in {"error", "response.failed"}:
                    raise CodexExecutionError("Codex retornou falha ao processar a resposta.")

    if (not saw_delta) and fallback_done_text:
        yield fallback_done_text


def run_codex_oauth_stream(
    *,
    prompt: str,
    model: str,
    access_token: str,
    account_id: str,
    timeout: float,
) -> Iterator[str]:
    def _runner() -> Iterator[str]:
        try:
            yield from _iter_codex_text_chunks(
                prompt=prompt,
                model=model,
                access_token=access_token,
                account_id=account_id,
                timeout=timeout,
                verify=True,
            )
        except CodexExecutionError:
            raise
        except Exception as exc:
            if not _is_ssl_verify_error(exc):
                raise CodexExecutionError(f"falha ao chamar Codex OAuth: {exc}") from exc
            yield from _iter_codex_text_chunks(
                prompt=prompt,
                model=model,
                access_token=access_token,
                account_id=account_id,
                timeout=timeout,
                verify=False,
            )

    return _runner()


def run_codex_oauth(
    *,
    prompt: str,
    model: str,
    access_token: str,
    account_id: str,
    timeout: float,
) -> str:
    chunks = list(
        run_codex_oauth_stream(
            prompt=prompt,
            model=model,
            access_token=access_token,
            account_id=account_id,
            timeout=timeout,
        )
    )
    text = "".join(chunks).strip()
    if not text:
        raise CodexExecutionError("resposta sem conteúdo textual do Codex OAuth")
    return text
