from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Iterator

import httpx

from clawlite.core.codex_auth import is_codex_api_key, resolve_codex_account_id
from clawlite.core.providers import get_provider_spec, resolve_provider_token
from clawlite.runtime.codex_provider import CodexExecutionError, run_codex_oauth_stream
from clawlite.runtime.offline import (
    ProviderExecutionError,
    _codex_account_id_from_config,
    _is_codex_rate_limit_error,
    _model_name_without_provider,
    _remote_timeout_seconds,
    codex_rate_limit_max_attempts,
    codex_rate_limit_user_message,
    codex_rate_limit_wait_seconds,
    gemini_rate_limit_max_attempts,
    gemini_rate_limit_user_message,
    gemini_rate_limit_wait_seconds,
    provider_from_model,
)

def run_remote_provider_stream(prompt: str, model: str, token: str) -> Iterator[str]:
    """
    Executa a requisição no provedor remoto com stream=True e yield chunks.
    Suporta provedores OpenAI-compatible e Anthropic-compatible via SSE.
    """
    if os.getenv("CLAWLITE_SIMULATE_PROVIDER_FAILURE", "").strip() == "1":
        raise ProviderExecutionError("falha simulada de provedor")

    provider = provider_from_model(model)
    model_name = _model_name_without_provider(model)
    if not provider or not model_name:
        raise ProviderExecutionError("modelo remoto inválido; use provider/model")
    spec = get_provider_spec(provider)
    if not spec or spec.api_style == "local":
        raise ProviderExecutionError(f"provedor remoto não suportado para streaming: '{provider}'")

    resolved_token = resolve_provider_token(provider, str(token or "").strip())
    if not resolved_token and not spec.token_optional:
        raise ProviderExecutionError(f"token ausente para provedor remoto '{provider}'")

    timeout = _remote_timeout_seconds()

    if provider == "openai-codex" and resolved_token and not is_codex_api_key(resolved_token):
        account_id = resolve_codex_account_id(_codex_account_id_from_config())
        if not account_id:
            raise ProviderExecutionError(
                "token OAuth do Codex detectado, mas account_id não foi encontrado. "
                "Rode `clawlite auth login openai-codex` novamente."
            )
        max_attempts = codex_rate_limit_max_attempts()
        wait_seconds = codex_rate_limit_wait_seconds()
        for attempt in range(1, max_attempts + 1):
            try:
                yield from run_codex_oauth_stream(
                    prompt=prompt,
                    model=model_name,
                    access_token=resolved_token,
                    account_id=account_id,
                    timeout=timeout,
                )
                return
            except CodexExecutionError as exc:
                if _is_codex_rate_limit_error(exc):
                    if attempt < max_attempts:
                        time.sleep(wait_seconds)
                        continue
                    raise ProviderExecutionError(codex_rate_limit_user_message(max_attempts, wait_seconds)) from exc
                raise ProviderExecutionError(str(exc)) from exc

    url = spec.request_url
    headers = {"Content-Type": "application/json"}
    if resolved_token:
        if spec.api_style == "anthropic":
            headers["x-api-key"] = resolved_token
        else:
            headers["Authorization"] = f"Bearer {resolved_token}"

    if spec.api_style == "anthropic":
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": model_name,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
    else:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }

    if provider == "gemini":
        max_attempts = gemini_rate_limit_max_attempts()
        wait_seconds = gemini_rate_limit_wait_seconds()
        rate_limit_message = gemini_rate_limit_user_message(max_attempts, wait_seconds)
    elif provider == "openai-codex":
        max_attempts = codex_rate_limit_max_attempts()
        wait_seconds = codex_rate_limit_wait_seconds()
        rate_limit_message = codex_rate_limit_user_message(max_attempts, wait_seconds)
    else:
        max_attempts = 1
        wait_seconds = 0.0
        rate_limit_message = ""

    for attempt in range(1, max_attempts + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream("POST", url, headers=headers, json=payload) as response:
                    response.raise_for_status()

                    for line in response.iter_lines():
                        line = line.strip()
                        if not line:
                            continue

                        if spec.api_style == "anthropic":
                            if line.startswith("data: "):
                                data_str = line[6:]
                                try:
                                    data = json.loads(data_str)
                                    if data.get("type") == "content_block_delta":
                                        delta = data.get("delta", {})
                                        if delta.get("type") == "text_delta":
                                            yield delta.get("text", "")
                                except json.JSONDecodeError:
                                    pass
                        else:
                            # OpenAI / OpenRouter style
                            if line == "data: [DONE]":
                                break
                            if line.startswith("data: "):
                                data_str = line[6:]
                                try:
                                    data = json.loads(data_str)
                                    choices = data.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content", "")
                                        if content:
                                            yield content
                                except json.JSONDecodeError:
                                    pass
            return
        except httpx.TimeoutException as exc:
            raise ProviderExecutionError(f"timeout ao chamar provedor remoto '{provider}'") from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code == 429 and provider in {"gemini", "openai-codex"}:
                if attempt < max_attempts:
                    time.sleep(wait_seconds)
                    continue
                raise ProviderExecutionError(rate_limit_message) from exc
            status_display = status_code if status_code is not None else "desconhecido"
            raise ProviderExecutionError(f"erro HTTP '{provider}' (status {status_display})") from exc
        except httpx.RequestError as exc:
            raise ProviderExecutionError(f"erro de rede ao chamar provedor remoto '{provider}': {exc}") from exc


def run_ollama_stream(prompt: str, model: str) -> Iterator[str]:
    """
    Executa ollama localmente usando subprocess, capturando stdout em tempo real
    para simular streaming do modelo local.
    """
    cmd = ["ollama", "run", model, prompt]
    try:
        # bufsize=1 e encoding garantem saída baseada em linha sem buffer extenso
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        
        if proc.stdout:
            for line in proc.stdout:
                # O ollama no CLI joga tokens de forma meio interativa, cada token ou palavra separada
                # Como precisamos de chunks nativos, yield a linha inteira ou char by char.
                # A saída padrão do `ollama run` solta palavras separadas por espaço.
                yield line

        proc.wait(timeout=90)
        if proc.returncode != 0:
            err = proc.stderr.read() if proc.stderr else "erro ao executar ollama"
            from clawlite.runtime.offline import OllamaExecutionError
            raise OllamaExecutionError(err.strip())
            
    except FileNotFoundError as exc:
        from clawlite.runtime.offline import OllamaExecutionError
        raise OllamaExecutionError("binário 'ollama' não encontrado") from exc
