# ClawLite

<p align="center">
  <img src="assets/mascot-animated.svg" alt="Mascote oficial ClawLite" width="180"/>
</p>

> Assistente de IA open source para Linux + Termux, com runtime real (CLI + Gateway + Dashboard + Skills).

[![Docs](https://img.shields.io/badge/docs-online-7c3aed?style=for-the-badge)](https://eobarretooo.github.io/ClawLite/)
[![Site](https://img.shields.io/badge/site-oficial-000000?style=for-the-badge&logo=vercel)](https://clawlite-site.vercel.app)
[![License](https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge)](LICENSE)
[![Stars](https://img.shields.io/github/stars/eobarretooo/ClawLite?style=for-the-badge)](https://github.com/eobarretooo/ClawLite)

## Status real do projeto (v0.4.x)

- ✅ CLI principal operacional (`doctor`, `status`, `start`, `onboarding`, `configure`, `run`)
- ✅ Gateway FastAPI + WebSocket + dashboard web
- ✅ Memória persistente entre sessões (workspace + logs diários + busca semântica)
- ✅ Learning analytics (`clawlite stats`) + tracking de tasks
- ✅ Multi-agente Telegram (MVP persistente)
- ✅ Cron por conversa + modo bateria + notificações inteligentes
- ✅ Marketplace de skills + auto-update com trust policy/rollback
- ✅ 37 skills registradas

## Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

## Quickstart (sem JSON manual)

```bash
# 1) Diagnóstico
clawlite doctor

# 2) Primeira configuração (wizard)
# aqui você já define: model, canais, skills, gateway, security e voz (STT/TTS)
clawlite onboarding

# 3) Ajuste fino por seções (opcional)
clawlite configure

# 4) Status local
clawlite status

# 5) Subir gateway + dashboard
clawlite start --host 0.0.0.0 --port 8787
```

> O fluxo padrão é todo guiado no menu interativo. Não precisa editar `config.json` manualmente.

## Comandos essenciais

```bash
clawlite doctor
clawlite status
clawlite start --port 8787
clawlite auth status
clawlite run "resuma o diretório"
clawlite stats --period week
clawlite skill auto-update --dry-run
clawlite skill auto-update --apply --strict
```

## Memória de sessão (persistente)

Estrutura automática em `~/.clawlite/workspace`:
- `AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`, `MEMORY.md`
- `memory/YYYY-MM-DD.md` (log diário)

Comandos:

```bash
clawlite memory init
clawlite memory context
clawlite memory semantic-search "preferências do usuário"
clawlite memory save-session "Resumo da sessão"
clawlite memory compact --max-daily-files 21
```

## Skills e marketplace

- Catálogo local: 37 skills (`clawlite/skills/registry.py`)
- Install/update/publish via CLI
- Auto-update com:
  - allowlist de hosts
  - checksum SHA-256
  - modo `--strict`
  - rollback automático em falha

## Documentação e sites

- Docs PT-BR: https://eobarretooo.github.io/ClawLite/
- Docs EN: https://eobarretooo.github.io/ClawLite/en/
- Site oficial: https://clawlite-site.vercel.app
- Site de skills: https://clawlite-skills-site.vercel.app

## Voz (STT/TTS) — pronto para uso

- STT Telegram/WhatsApp com Whisper (local) + fallback OpenAI quando configurado
- TTS por comando no prompt (`/audio`, `#audio`, `responda em áudio`) ou por config
- Envio de áudio no Telegram (`sendVoice`) com arquivo temporário seguro
- Config por canal (`stt_enabled`, `tts_enabled`, `tts_provider`, etc.)

Detalhes e limitações: `docs/VOICE.md` e `docs/config.example.json`.

## Roadmap ativo

1. Evolução do learning system no core (melhoria contínua)
2. Evolução do ecossistema de skills (site + experiência de publicação)
3. Hardening de conectores de canais (Telegram/WhatsApp)

## Contribuição

1. Fork do repositório
2. Branch: `feat/minha-feature`
3. Commit + push
4. PR com contexto e testes
