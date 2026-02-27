"""Skill Whisper — transcrição de áudio com Whisper local ou API OpenAI.

Detecta whisper/faster-whisper local e faz fallback para a API da OpenAI se configurado.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

SKILL_NAME = "whisper"
SKILL_DESCRIPTION = "Transcrição de áudio com OpenAI Whisper"

# Modelos suportados pelo whisper CLI
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"]


def _detect_backend() -> str | None:
    """Detecta qual backend Whisper está disponível.

    Retorna: 'faster-whisper', 'whisper', ou None.
    """
    if shutil.which("faster-whisper"):
        return "faster-whisper"
    if shutil.which("whisper"):
        return "whisper"
    return None


def _openai_api_key() -> str | None:
    """Busca API key da OpenAI para fallback."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    # Tenta ler do config do ClawLite
    config_path = Path(os.environ.get("CLAWLITE_CONFIG_DIR", Path.home() / ".config" / "clawlite")) / "config.json"
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
            return data.get("openai_api_key") or data.get("providers", {}).get("openai", {}).get("api_key", "")
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def whisper_status() -> dict[str, Any]:
    """Verifica disponibilidade dos backends de transcrição."""
    backend = _detect_backend()
    api_key = _openai_api_key()

    return {
        "local_backend": backend,
        "local_available": backend is not None,
        "openai_api_available": bool(api_key),
        "supported_models": WHISPER_MODELS,
        "ready": backend is not None or bool(api_key),
    }


def _transcribe_local(audio_path: str, model: str, language: str, backend: str) -> dict[str, Any]:
    """Transcreve usando whisper ou faster-whisper local."""
    if not Path(audio_path).exists():
        return {"error": f"Arquivo não encontrado: {audio_path}"}

    if backend == "faster-whisper":
        cmd = ["faster-whisper", audio_path, "--model", model]
        if language:
            cmd.extend(["--language", language])
    else:
        cmd = ["whisper", audio_path, "--model", model, "--output_format", "txt"]
        if language:
            cmd.extend(["--language", language])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            return {"error": f"Erro no {backend}: {proc.stderr.strip()}"}

        text = proc.stdout.strip()
        if not text and backend == "whisper":
            # whisper salva em arquivo .txt
            txt_path = Path(audio_path).with_suffix(".txt")
            if txt_path.exists():
                text = txt_path.read_text().strip()

        return {"text": text, "backend": backend, "model": model, "language": language or "auto"}
    except subprocess.TimeoutExpired:
        return {"error": f"Timeout ao transcrever com {backend} (limite: 600s)"}
    except Exception as exc:
        return {"error": str(exc)}


def _transcribe_openai_api(audio_path: str, model: str, language: str) -> dict[str, Any]:
    """Transcreve usando a API Whisper da OpenAI."""
    import urllib.request

    api_key = _openai_api_key()
    if not api_key:
        return {"error": "API key da OpenAI não configurada para fallback."}

    filepath = Path(audio_path)
    if not filepath.exists():
        return {"error": f"Arquivo não encontrado: {audio_path}"}

    # Multipart form upload
    boundary = "clawlite_whisper_boundary"
    body_parts = []

    # Campo model
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(b'Content-Disposition: form-data; name="model"\r\n\r\n')
    body_parts.append(b"whisper-1\r\n")

    # Campo language (opcional)
    if language:
        body_parts.append(f"--{boundary}\r\n".encode())
        body_parts.append(b'Content-Disposition: form-data; name="language"\r\n\r\n')
        body_parts.append(f"{language}\r\n".encode())

    # Campo file
    body_parts.append(f"--{boundary}\r\n".encode())
    body_parts.append(f'Content-Disposition: form-data; name="file"; filename="{filepath.name}"\r\n'.encode())
    body_parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    body_parts.append(filepath.read_bytes())
    body_parts.append(b"\r\n")
    body_parts.append(f"--{boundary}--\r\n".encode())

    full_body = b"".join(body_parts)

    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=full_body,
        method="POST",
    )
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return {"text": result.get("text", ""), "backend": "openai-api", "model": "whisper-1", "language": language or "auto"}
    except Exception as exc:
        return {"error": f"Erro na API OpenAI: {exc}"}


def whisper_transcribe(audio_path: str, model: str = "base", language: str = "") -> dict[str, Any]:
    """Transcreve um arquivo de áudio.

    Tenta backend local primeiro, depois fallback para API OpenAI.

    Args:
        audio_path: Caminho do arquivo de áudio.
        model: Modelo whisper (tiny, base, small, medium, large).
        language: Código do idioma (ex: 'pt', 'en'). Vazio = detecção automática.
    """
    if not audio_path:
        return {"error": "Caminho do áudio não pode ser vazio."}

    backend = _detect_backend()
    if backend:
        local_result = _transcribe_local(audio_path, model, language, backend)
        # Fallback para API caso backend local falhe e haja chave configurada
        if local_result.get("error") and _openai_api_key():
            api_result = _transcribe_openai_api(audio_path, model, language)
            if not api_result.get("error"):
                return api_result
        return local_result

    # Fallback para API
    return _transcribe_openai_api(audio_path, model, language)


def run(command: str = "") -> str:
    """Ponto de entrada compatível com o registry do ClawLite."""
    if not command:
        status = whisper_status()
        if status["ready"]:
            parts = []
            if status["local_backend"]:
                parts.append(f"local: {status['local_backend']}")
            if status["openai_api_available"]:
                parts.append("API OpenAI disponível")
            return f"✅ Whisper pronto ({', '.join(parts)}). Use: transcribe <audio> [--model base] [--lang pt]"
        return "❌ Nenhum backend Whisper disponível. Instale whisper/faster-whisper ou configure OPENAI_API_KEY."

    parts = command.strip().split()
    cmd = parts[0].lower()

    if cmd == "status":
        return json.dumps(whisper_status(), ensure_ascii=False, indent=2)

    elif cmd == "transcribe":
        if len(parts) < 2:
            return "Uso: transcribe <caminho_audio> [--model base] [--lang pt]"
        audio = parts[1]
        model = "base"
        language = ""
        for i, p in enumerate(parts):
            if p == "--model" and i + 1 < len(parts):
                model = parts[i + 1]
            elif p == "--lang" and i + 1 < len(parts):
                language = parts[i + 1]
        result = whisper_transcribe(audio, model=model, language=language)
        if "error" in result:
            return f"❌ {result['error']}"
        return f"[{result['backend']}/{result['model']}] {result['text']}"

    else:
        return f"Comando desconhecido: {cmd}. Use: status, transcribe"
