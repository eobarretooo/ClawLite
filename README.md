# ClawLite

<p align="center">
  <img src="assets/mascot.svg" alt="Mascote ClawLite" width="180"/>
</p>

> O assistente de IA open source para Linux + Termux, com gateway nativo, skills modulares e operação portátil.

[![Docs](https://img.shields.io/badge/docs-online-7c3aed?style=for-the-badge)](https://eobarretooo.github.io/ClawLite/)
[![License](https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge)](LICENSE)
[![Stars](https://img.shields.io/github/stars/eobarretooo/ClawLite?style=for-the-badge)](https://github.com/eobarretooo/ClawLite)

## Por que ClawLite

- **Linux + Termux first** (ARM e x86)
- **Instalação em 1 comando**
- **Gateway WebSocket** com autenticação por token
- **Configure estilo OpenClaw** (`clawlite configure`) com seções, autosave e preview JSON
- **Onboarding wizard guiado** (`clawlite onboarding`) com etapas + barra de progresso
- **Diagnóstico amigável** (`clawlite doctor`) com validações de dependências e runtime
- **Status local de runtime** (`clawlite status`) para gateway/workers/cron/reddit
- **Bootstrap rápido de servidor** (`clawlite start`) para subir gateway local
- **Learning analytics** (`clawlite stats`) com taxa de sucesso, top skills e preferências aprendidas
- **Integração Reddit** (`clawlite reddit ...`) com OAuth, postagem de milestone e monitor de menções
- **Ecossistema de skills** em expansão contínua
- **Marketplace de skills** com índice remoto, checksum e allowlist de hosts

## Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

## Quickstart (estado atual)

```bash
# 1) validar ambiente
clawlite doctor

# 2) onboarding guiado (primeira execução)
clawlite onboarding

# 3) ajuste fino no estilo OpenClaw
clawlite configure

# 4) conferir runtime local
clawlite status

# 5) subir gateway HTTP/WebSocket
clawlite start --host 0.0.0.0 --port 8787
```

## Comandos essenciais

```bash
clawlite doctor
clawlite status
clawlite start --port 8787
clawlite auth status
clawlite stats --period week
clawlite reddit status
clawlite skill install find-skills
clawlite skill update
```

## Learning / Stats

A telemetria local de aprendizado pode ser consultada via CLI:

```bash
clawlite stats --period all
clawlite stats --period month --skill github
```

Saída inclui: total de tasks, taxa de sucesso, tempo médio, tokens, streak, top skills e preferências aprendidas.

## Reddit

Fluxo completo:

```bash
clawlite reddit status
clawlite reddit auth-url
clawlite reddit exchange-code "SEU_CODE"
clawlite reddit post-milestone --title "ClawLite v0.4.0" --text "..."
clawlite reddit monitor-once
```

Guia detalhado: `docs/REDDIT_INTEGRATION.md`

## Dashboard v2

- Chat em tempo real integrado ao pipeline do agente (`/ws/chat`)
- Telemetria de tokens/custo por sessao e por periodo (`/api/dashboard/telemetry`)
- Acoes de skills com feedback de loading/sucesso/erro
- Logs realtime com filtros basicos e busca (`/api/dashboard/logs`, `/ws/logs`)

Guia completo: `docs/DASHBOARD.md`

## Offline automático com Ollama

- Se `offline_mode.enabled=true`, o runtime tenta o modelo remoto e faz fallback automático para Ollama em dois casos:
  - sem conectividade
  - falha do provedor
- Fallback usa o primeiro `ollama/...` em `model_fallback`.

Status rápido de modelo/fallback:

```bash
clawlite model status
```

## Cron por conversa

```bash
clawlite cron list
clawlite cron add --channel telegram --chat-id 123 --thread-id suporte --label general --name heartbeat --text "ping" --every-seconds 300
clawlite cron remove 1
clawlite cron run
clawlite cron run --all
```

## Config de exemplo

- Arquivo de referência: `docs/config.example.json`
- Arquivo real de runtime: `~/.clawlite/config.json`

## Documentação

- PT-BR: https://eobarretooo.github.io/ClawLite/
- EN: https://eobarretooo.github.io/ClawLite/en/
- Guia de configuração UX: `docs/CONFIGURE_UX_PTBR.md`
- Troubleshooting técnico: `docs/TROUBLESHOOTING.md`

## Contribuição

1. Fork do repositório
2. Branch: `feat/minha-feature`
3. Commit + push
4. Pull Request com contexto, screenshots/logs e teste

## Community Automation (Reddit + Threads + GitHub)

- Playbook consolidado: `docs/COMMUNITY_AUTOMATION.md`
- Templates: `templates/community/`
- Gerador de pacote por milestone:

```bash
python3 scripts/community_pack.py --version v0.5.0 --date 2026-02-27 --highlights "Multiagent por thread" "Cron por conversa" "Reddit monitor"
```
