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
- **Menu de configuração interativo** (`clawlite configure`)
- **Onboarding guiado** (`clawlite onboarding`)
- **Auth para provedores de IA** (`clawlite auth login ...`)
- **Ecossistema de skills** em expansão contínua
- **Marketplace de skills** com índice remoto, checksum e allowlist de hosts

## Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

## Comandos principais

```bash
clawlite doctor
clawlite onboarding
clawlite configure
clawlite auth status
clawlite gateway --port 8787
clawlite skill install find-skills
clawlite skill update
```

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
# listar
clawlite cron list

# criar job por conversa/chat/thread/label
clawlite cron add --channel telegram --chat-id 123 --thread-id suporte --label general --name heartbeat --text "ping" --every-seconds 300

# remover
clawlite cron remove 1

# rodar jobs vencidos (ou todos com --all)
clawlite cron run
clawlite cron run --all
```

## Notificações inteligentes (prioridade + dedupe)

- Eventos críticos (falha de provedor/cron) geram prioridade `high`.
- Eventos de fallback offline usam prioridade `normal`.
- Execuções de cron com sucesso usam prioridade `low`.
- Deduplicação evita spam de alertas repetidos na janela configurada.

## Modo bateria com throttling

```bash
clawlite battery status
clawlite battery set --enabled true --throttle-seconds 8
```

Com `battery_mode.enabled=true`, workers aumentam o intervalo de polling para economizar bateria.

## Config de exemplo

- Arquivo de referência: `docs/config.example.json`
- Arquivo real de runtime: `~/.clawlite/config.json`

## MVP Multi-Agente Telegram (P0)

```bash
# 1) Registrar worker persistente por chat/thread/label
clawlite agents register --channel telegram --chat-id 123 --thread-id suporte --label general --cmd 'clawlite run "{text}"'

# 2) Subir/parar/listar workers
clawlite agents start 1
clawlite agents stop 1
clawlite agents list

# 3) Dispatch local (simulando update Telegram)
clawlite agents telegram-dispatch --config telegram.multiagent.json --chat-id 123 --label general "responda este pedido"

# 4) Acompanhar fila
clawlite agents tasks --limit 20
```

Template de configuração:

```bash
clawlite channels template telegram-multiagent
```

## Documentação

- PT-BR: https://eobarretooo.github.io/ClawLite/
- EN: https://eobarretooo.github.io/ClawLite/en/
- Troubleshooting técnico: `docs/TROUBLESHOOTING.md`

## Skills

Estrutura de skill:

```text
skills/<nome>/SKILL.md
clawlite/skills/<nome_modulo>.py
```

Registro central:

- `clawlite/skills/registry.py`

## Contribuição

1. Fork do repositório
2. Branch: `feat/minha-feature`
3. Commit + push
4. Pull Request com contexto, screenshots/logs e teste


## Reddit

- OAuth + postagem de milestone + monitor de menções com aprovação via Telegram.
- Guia: `docs/REDDIT_INTEGRATION.md`
