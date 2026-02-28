from __future__ import annotations

import json
import os
import subprocess
from typing import Iterator

import httpx

from clawlite.runtime.offline import (
    ProviderExecutionError,
    _model_name_without_provider,
    _remote_timeout_seconds,
    provider_from_model,
)

def run_remote_provider_stream(prompt: str, model: str, token: str) -> Iterator[str]:
    """
    Executa a requisição no provedor remoto com stream=True e yield chunks.
    Suporta OpenAI, Anthropic e OpenRouter via Server-Sent Events (SSE).
    """
    if os.getenv("CLAWLITE_SIMULATE_PROVIDER_FAILURE", "").strip() == "1":
        raise ProviderExecutionError("falha simulada de provedor")

    provider = provider_from_model(model)
    model_name = _model_name_without_provider(model)
    if not provider or not model_name:
        raise ProviderExecutionError("modelo remoto inválido; use provider/model")

    env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }
    env_name = env_map.get(provider)
    resolved_token = (os.getenv(env_name, "").strip() if env_name else "") or str(token or "").strip()
    if not resolved_token:
        raise ProviderExecutionError(f"token ausente para provedor remoto '{provider}'")

    timeout = _remote_timeout_seconds()

    if provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {resolved_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
    elif provider == "anthropic":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": resolved_token,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
    elif provider == "openrouter":
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {resolved_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
    else:
        raise ProviderExecutionError(f"provedor remoto não suportado para streaming: '{provider}'")

    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    line = line.strip()
                    if not line:
                        continue

                    if provider == "anthropic":
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

    except httpx.TimeoutException as exc:
        raise ProviderExecutionError(f"timeout ao chamar provedor remoto '{provider}'") from exc
    except httpx.HTTPStatusError as exc:
        raise ProviderExecutionError(f"erro HTTP '{provider}' (status {exc.response.status_code})") from exc
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
