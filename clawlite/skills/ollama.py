"""Skill Ollama — execução local de modelos de IA via Ollama.

Detecta o servidor Ollama local, lista modelos, gera completions e faz pull de modelos.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

SKILL_NAME = "ollama"
SKILL_DESCRIPTION = "Execução local de modelos com Ollama"

OLLAMA_BASE = "http://localhost:11434"


def _request(path: str, method: str = "GET", data: dict | None = None, timeout: int = 120) -> dict | list | str:
    """Faz requisição HTTP ao Ollama local."""
    url = f"{OLLAMA_BASE}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Não foi possível conectar ao Ollama em {OLLAMA_BASE}: {exc}") from exc


def ollama_status() -> dict[str, Any]:
    """Verifica se o Ollama está rodando e retorna informações básicas."""
    try:
        _request("/", timeout=5)
        models = ollama_list()
        return {
            "online": True,
            "url": OLLAMA_BASE,
            "models_count": len(models),
            "models": [m["name"] for m in models],
        }
    except ConnectionError:
        return {"online": False, "url": OLLAMA_BASE, "error": "Ollama não está acessível. Verifique se está rodando."}


def ollama_list() -> list[dict[str, Any]]:
    """Lista modelos disponíveis localmente no Ollama."""
    try:
        resp = _request("/api/tags")
        if isinstance(resp, dict):
            return resp.get("models", [])
        return []
    except ConnectionError as exc:
        return [{"error": str(exc)}]


def ollama_generate(prompt: str, model: str = "llama3", stream: bool = False, **kwargs: Any) -> dict[str, Any]:
    """Gera uma completion usando um modelo Ollama local.

    Args:
        prompt: Texto de entrada para o modelo.
        model: Nome do modelo (padrão: llama3).
        stream: Se True, retorna resposta em streaming (não suportado nesta versão simples).
        **kwargs: Parâmetros extras (temperature, top_p, etc).
    """
    if not prompt:
        return {"error": "Prompt não pode ser vazio."}

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,  # sempre não-streaming nesta implementação
    }
    if kwargs:
        payload["options"] = kwargs

    try:
        resp = _request("/api/generate", method="POST", data=payload, timeout=300)
        if isinstance(resp, dict):
            return resp
        return {"response": resp}
    except ConnectionError as exc:
        return {"error": str(exc)}


def ollama_pull(model: str) -> dict[str, Any]:
    """Faz pull (download) de um modelo do registry do Ollama.

    Args:
        model: Nome do modelo para baixar (ex: 'llama3', 'mistral').
    """
    if not model:
        return {"error": "Nome do modelo não pode ser vazio."}

    try:
        resp = _request("/api/pull", method="POST", data={"name": model, "stream": False}, timeout=600)
        if isinstance(resp, dict):
            return resp
        return {"status": resp}
    except ConnectionError as exc:
        return {"error": str(exc)}


def run(command: str = "") -> str:
    """Ponto de entrada compatível com o registry do ClawLite."""
    if not command:
        status = ollama_status()
        if status.get("online"):
            return f"✅ Ollama online em {OLLAMA_BASE} — {status['models_count']} modelo(s): {', '.join(status['models']) or 'nenhum'}"
        return f"❌ Ollama offline: {status.get('error', 'desconhecido')}"

    parts = command.strip().split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "status":
        return json.dumps(ollama_status(), ensure_ascii=False, indent=2)
    elif cmd == "list":
        models = ollama_list()
        if not models:
            return "Nenhum modelo local encontrado."
        if models and "error" in models[0]:
            return models[0]["error"]
        lines = [f"- {m['name']} ({m.get('size', '?')} bytes)" for m in models]
        return "Modelos locais:\n" + "\n".join(lines)
    elif cmd == "generate":
        if not arg:
            return "Uso: generate <prompt> [--model nome]"
        # parse --model
        model = "llama3"
        if "--model" in arg:
            idx = arg.index("--model")
            rest = arg[idx + 7:].strip().split(None, 1)
            model = rest[0] if rest else "llama3"
            arg = arg[:idx].strip() + (" " + rest[1] if len(rest) > 1 else "")
        result = ollama_generate(arg.strip(), model=model)
        return result.get("response", result.get("error", json.dumps(result)))
    elif cmd == "pull":
        if not arg:
            return "Uso: pull <nome_do_modelo>"
        result = ollama_pull(arg.strip())
        return result.get("status", result.get("error", json.dumps(result)))
    else:
        return f"Comando desconhecido: {cmd}. Use: status, list, generate, pull"
