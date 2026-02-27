from __future__ import annotations

import io
import json

from clawlite.runtime.telegram_multiagent import dispatch_telegram_update
from clawlite.runtime.voice import clean_audio_flags, extract_telegram_audio_file_id, inbound_to_prompt, wants_audio_reply
from clawlite.skills import whisper


def test_audio_flag_parser_ptbr() -> None:
    assert wants_audio_reply("/audio responde isso", {"tts_default_reply": False}) is True
    assert clean_audio_flags("/audio responda em áudio oi") == "oi"


def test_extract_telegram_file_id_from_voice_message() -> None:
    update = {"message": {"voice": {"file_id": "abc123"}}}
    assert extract_telegram_audio_file_id(update) == "abc123"


def test_whisper_fallback_to_openai_when_local_fails(monkeypatch) -> None:
    monkeypatch.setattr(whisper, "_detect_backend", lambda: "whisper")
    monkeypatch.setattr(whisper, "_openai_api_key", lambda: "sk-test")
    monkeypatch.setattr(whisper, "_transcribe_local", lambda *a, **k: {"error": "falhou local"})
    monkeypatch.setattr(whisper, "_transcribe_openai_api", lambda *a, **k: {"text": "ok api", "backend": "openai-api"})

    result = whisper.whisper_transcribe("/tmp/audio.ogg", model="base", language="pt")
    assert result["text"] == "ok api"


def test_inbound_to_prompt_telegram_voice_mock(monkeypatch) -> None:
    update = {"message": {"voice": {"file_id": "v1"}}}
    cfg = {"stt_enabled": True, "token": "bot-token", "stt_model": "base", "stt_language": "pt"}

    monkeypatch.setattr("clawlite.runtime.voice.download_telegram_audio", lambda *a, **k: "/tmp/fake.ogg")
    monkeypatch.setattr("clawlite.runtime.voice.transcribe_audio_file", lambda *a, **k: "transcrição pronta")

    text, meta = inbound_to_prompt("telegram", update, cfg)
    assert "transcrição pronta" in text
    assert meta["source"] == "voice"


def test_smoke_dispatch_telegram_update_with_voice(monkeypatch, tmp_path) -> None:
    cfg_path = tmp_path / "tg.json"
    cfg_path.write_text(json.dumps({"telegram": {"enabled": True, "token": "bot", "defaultLabel": "general", "stt_enabled": True}}), encoding="utf-8")

    monkeypatch.setattr("clawlite.runtime.telegram_multiagent.inbound_to_prompt", lambda *a, **k: ("/audio teste de voz", {"source": "voice"}))
    monkeypatch.setattr("clawlite.runtime.telegram_multiagent.enqueue_task", lambda *a, **k: 99)

    update = {"message": {"chat": {"id": 123}, "voice": {"file_id": "abc"}}}
    task_id = dispatch_telegram_update(str(cfg_path), update)
    assert task_id == 99
