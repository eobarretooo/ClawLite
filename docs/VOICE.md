# Voz (STT/TTS) — Telegram e WhatsApp

## O que está implementado

- STT no fluxo de entrada:
  - Telegram: aceita `voice`/`audio`, resolve `file_id` -> `file_path` via Bot API e baixa o arquivo.
  - WhatsApp: usa `audio_url`/`media_url` do payload atual da integração.
  - Transcrição via Whisper local (`faster-whisper` ou `whisper`) com fallback para API OpenAI quando disponível.
- TTS no fluxo de saída:
  - Ativado por flag no prompt (`/audio`, `#audio`, `--audio`, `responda em áudio`, etc.) ou por `tts_default_reply`.
  - Geração de áudio por provedor local (`espeak`, com conversão para `.ogg` se houver `ffmpeg`) ou OpenAI (`tts_provider: openai`).
  - Envio de áudio no Telegram via `sendVoice`.

## Configuração por canal

```json
{
  "channels": {
    "telegram": {
      "stt_enabled": true,
      "stt_model": "base",
      "stt_language": "pt",
      "tts_enabled": true,
      "tts_provider": "local",
      "tts_model": "gpt-4o-mini-tts",
      "tts_voice": "alloy",
      "tts_default_reply": false
    }
  }
}
```

## Limitações atuais

- TTS com envio automático está pronto para Telegram.
- WhatsApp depende do conector HTTP já usado no ambiente (payload com `audio_url`/`media_url`).
- Para TTS local, é recomendado instalar `espeak` (e opcionalmente `ffmpeg` para `.ogg`).
- Para TTS/STT via OpenAI, exporte `OPENAI_API_KEY`.

## Dicas Linux/Termux

- Linux: `sudo apt install espeak ffmpeg`.
- Termux: `pkg install espeak ffmpeg`.
