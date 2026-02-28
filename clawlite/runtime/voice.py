from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional, Generator, AsyncGenerator
import edge_tts
from groq import Groq
try:
    import pygame
    _PYGAME_AVAILABLE = True
except ImportError:
    _PYGAME_AVAILABLE = False

from clawlite.skills.whisper import whisper_transcribe

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "pt-BR-AntonioNeural"

class VoicePipeline:
    def __init__(self):
        self._groq_client: Optional[Groq] = None
        if _PYGAME_AVAILABLE:
            pygame.mixer.init()

    def get_groq_client(self) -> Groq:
        if not self._groq_client:
            api_key = os.environ.get("GROQ_API_KEY")
            if not api_key:
                raise VoiceError("GROQ_API_KEY não configurada para o pipeline de STT rápido.")
            self._groq_client = Groq(api_key=api_key)
        return self._groq_client

    async def speak(self, text: str, voice: str = DEFAULT_VOICE) -> None:
        if not text.strip() or not _PYGAME_AVAILABLE:
            return
            
        communicate = edge_tts.Communicate(text, voice)
        fd, temp_file = tempfile.mkstemp(prefix="claw-tts-", suffix=".mp3")
        os.close(fd)
        
        await communicate.save(temp_file)
        
        try:
            import asyncio
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Erro no playback de TTS: {e}")
        finally:
            pygame.mixer.music.unload()
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

    def transcribe(self, audio_filepath: str) -> str:
        client = self.get_groq_client()
        with open(audio_filepath, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=(audio_filepath, file.read()),
                model="whisper-large-v3-turbo",
                language="pt",
            )
            return transcription.text

_voice_pipeline = None

def get_voice_pipeline() -> VoicePipeline:
    global _voice_pipeline
    if _voice_pipeline is None:
        _voice_pipeline = VoicePipeline()
    return _voice_pipeline

AUDIO_FLAGS = ("/audio", "#audio", "--audio", "responda em áudio", "responder em áudio", "em voz")


class VoiceError(RuntimeError):
    pass


def wants_audio_reply(text: str, channel_cfg: dict[str, Any] | None = None) -> bool:
    cfg = channel_cfg or {}
    if bool(cfg.get("tts_default_reply", False)):
        return True
    raw = (text or "").strip().lower()
    if not raw:
        return False
    return any(flag in raw for flag in AUDIO_FLAGS)


def clean_audio_flags(text: str) -> str:
    out = text or ""
    for flag in AUDIO_FLAGS:
        out = out.replace(flag, "")
        out = out.replace(flag.title(), "")
    return " ".join(out.split()).strip()


def extract_telegram_audio_file_id(update: dict[str, Any]) -> str:
    msg = update.get("message") or update.get("edited_message") or {}
    if not isinstance(msg, dict):
        return ""
    voice = msg.get("voice") or {}
    audio = msg.get("audio") or {}
    return str(voice.get("file_id") or audio.get("file_id") or "")


def extract_incoming_text(channel: str, payload: dict[str, Any]) -> str:
    if channel == "telegram":
        msg = payload.get("message") or payload.get("edited_message") or {}
        text = msg.get("text") or msg.get("caption") or ""
        return str(text)
    return str(payload.get("text") or payload.get("caption") or "")


def _download_bytes(url: str, headers: dict[str, str] | None = None) -> bytes:
    req = urllib.request.Request(url)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def download_telegram_audio(update: dict[str, Any], telegram_token: str) -> str:
    file_id = extract_telegram_audio_file_id(update)
    if not file_id:
        raise VoiceError("Mensagem sem áudio/voice para transcrever.")
    if not telegram_token:
        raise VoiceError("Token do Telegram ausente na configuração.")

    api = f"https://api.telegram.org/bot{telegram_token}/getFile"
    payload = urllib.parse.urlencode({"file_id": file_id}).encode()
    req = urllib.request.Request(api, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise VoiceError(f"Falha ao resolver arquivo no Telegram: {data}")

    file_path = data.get("result", {}).get("file_path", "")
    if not file_path:
        raise VoiceError("Telegram não retornou file_path.")

    raw = _download_bytes(f"https://api.telegram.org/file/bot{telegram_token}/{file_path}")
    suffix = Path(file_path).suffix or ".ogg"
    fd, tmp_path = tempfile.mkstemp(prefix="clawlite-tg-", suffix=suffix)
    os.close(fd)
    Path(tmp_path).write_bytes(raw)
    return tmp_path


def download_whatsapp_audio(payload: dict[str, Any], whatsapp_token: str = "") -> str:
    media_url = str(payload.get("audio_url") or payload.get("media_url") or "")
    if not media_url:
        raise VoiceError("Payload WhatsApp sem media_url/audio_url.")
    headers = {"Authorization": f"Bearer {whatsapp_token}"} if whatsapp_token else {}
    raw = _download_bytes(media_url, headers=headers)
    suffix = Path(urllib.parse.urlparse(media_url).path).suffix or ".ogg"
    fd, tmp_path = tempfile.mkstemp(prefix="clawlite-wa-", suffix=suffix)
    os.close(fd)
    Path(tmp_path).write_bytes(raw)
    return tmp_path


def transcribe_audio_file(audio_path: str, model: str = "base", language: str = "pt") -> str:
    # Tenta via Groq (mais rápido) se houver chave, senão fallback primário (Whisper.cpp local stub)
    if os.environ.get("GROQ_API_KEY"):
        try:
            vp = get_voice_pipeline()
            text = vp.transcribe(audio_path)
            if text:
                return text.strip()
        except Exception as e:
            logger.warning(f"Groq API falhou, caindo para whisper local: {e}")
            
    result = whisper_transcribe(audio_path, model=model, language=language)
    if result.get("error"):
        raise VoiceError(str(result["error"]))
    text = str(result.get("text") or "").strip()
    if not text:
        raise VoiceError("Transcrição vazia.")
    return text


def inbound_to_prompt(channel: str, payload: dict[str, Any], channel_cfg: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Normaliza entrada de canal em prompt textual.

    Retorna (prompt, meta). Se houver áudio e STT habilitado, transcreve.
    """
    text = extract_incoming_text(channel, payload)
    meta: dict[str, Any] = {"source": "text", "audio_path": ""}

    stt_enabled = bool(channel_cfg.get("stt_enabled", False))
    try:
        if channel == "telegram" and stt_enabled and extract_telegram_audio_file_id(payload):
            audio_path = download_telegram_audio(payload, str(channel_cfg.get("token", "")))
            transcript = transcribe_audio_file(
                audio_path,
                model=str(channel_cfg.get("stt_model", "base")),
                language=str(channel_cfg.get("stt_language", "pt")),
            )
            meta = {"source": "voice", "audio_path": audio_path}
            text = transcript if not text else f"{text}\n\n[Transcrição de áudio]\n{transcript}"
        elif channel == "whatsapp" and stt_enabled and (payload.get("audio_url") or payload.get("media_url")):
            audio_path = download_whatsapp_audio(payload, str(channel_cfg.get("token", "")))
            transcript = transcribe_audio_file(
                audio_path,
                model=str(channel_cfg.get("stt_model", "base")),
                language=str(channel_cfg.get("stt_language", "pt")),
            )
            meta = {"source": "voice", "audio_path": audio_path}
            text = transcript if not text else f"{text}\n\n[Transcrição de áudio]\n{transcript}"
    except Exception as exc:
        raise VoiceError(f"Falha no STT ({channel}): {exc}") from exc

    text = text.strip()
    if not text:
        raise VoiceError("Não foi possível extrair texto da mensagem.")
    return text, meta


def _tts_openai(text: str, voice: str = "alloy", model: str = "gpt-4o-mini-tts") -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise VoiceError("OPENAI_API_KEY não configurada para TTS remoto.")

    payload = json.dumps({"model": model, "voice": voice, "input": text}).encode("utf-8")
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read()

    fd, out_path = tempfile.mkstemp(prefix="clawlite-tts-", suffix=".mp3")
    os.close(fd)
    Path(out_path).write_bytes(raw)
    return out_path


import asyncio
def _tts_local(text: str) -> str:
    # Substituindo espeak rudimentar pelo Edge-TTS local de alta qualidade
    fd, mp3_path = tempfile.mkstemp(prefix="clawlite-tts-", suffix=".mp3")
    os.close(fd)
    
    # Processo pseudo-sync do Edge-TTS local (que nativamente é async)
    try:
        communicate = edge_tts.Communicate(text, DEFAULT_VOICE)
        asyncio.run(communicate.save(mp3_path))
        
        # Ogg fallback para telegram
        if shutil.which("ffmpeg"):
            fd2, ogg_path = tempfile.mkstemp(prefix="clawlite-tts-tg-", suffix=".ogg")
            os.close(fd2)
            conv = subprocess.run(["ffmpeg", "-y", "-i", mp3_path, ogg_path], capture_output=True, text=True)
            if conv.returncode == 0:
                try:
                    os.unlink(mp3_path)
                except OSError:
                    pass
                return ogg_path
        return mp3_path
    except Exception as e:
        raise VoiceError(f"Falha no Edge-TTS: {e}")


def synthesize_tts(text: str, channel_cfg: dict[str, Any]) -> str:
    if not bool(channel_cfg.get("tts_enabled", False)):
        raise VoiceError("TTS desabilitado para este canal.")

    provider = str(channel_cfg.get("tts_provider", "local")).lower()
    voice = str(channel_cfg.get("tts_voice", "alloy"))
    if provider == "openai":
        return _tts_openai(text, voice=voice, model=str(channel_cfg.get("tts_model", "gpt-4o-mini-tts")))
    return _tts_local(text)


def send_telegram_audio_reply(telegram_token: str, chat_id: str, audio_path: str, caption: str = "") -> dict[str, Any]:
    if not telegram_token:
        raise VoiceError("Token do Telegram ausente para envio de áudio.")
    boundary = "clawlite_tg_audio"
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(value.encode())
        parts.append(b"\r\n")

    add_field("chat_id", str(chat_id))
    if caption:
        add_field("caption", caption)

    filename = Path(audio_path).name
    mime = "audio/ogg" if filename.endswith(".ogg") else "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="voice"; filename="{filename}"\r\n'.encode())
    parts.append(f"Content-Type: {mime}\r\n\r\n".encode())
    parts.append(Path(audio_path).read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{telegram_token}/sendVoice",
        data=b"".join(parts),
        method="POST",
    )
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))
