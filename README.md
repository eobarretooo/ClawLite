<p align="center">
  <img src="assets/mascot-animated.svg" alt="ClawLite Mascot" width="120" />
</p>

<h1 align="center">ClawLite</h1>

<p align="center">
  Assistente de IA open source para Linux e Termux, com gateway WebSocket,
  multi-canal, memória persistente, marketplace de skills e suporte a MCP.
</p>

<p align="center">
  <a href="https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/eobarretooo/ClawLite/ci.yml?branch=main&label=CI" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License" /></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python" />
  <img src="https://img.shields.io/badge/platform-Linux%20%7C%20Termux-1f8b4c" alt="Platform" />
</p>

<p align="center">
  <a href="https://clawlite-site.vercel.app">Site</a> ·
  <a href="https://eobarretooo.github.io/ClawLite/">Documentação</a> ·
  <a href="https://github.com/eobarretooo/ClawLite/issues">Issues</a> ·
  <a href="https://github.com/eobarretooo/ClawLite/discussions">Discussões</a>
</p>

## Visão Geral

O ClawLite foi projetado para execução prática, não apenas chat. O projeto combina:

- CLI operacional para uso diário.
- Gateway FastAPI + WebSocket com dashboard web.
- Runtime com fallback online/offline (incluindo Ollama).
- Integrações de canal em Python (Telegram, Discord, Slack e WhatsApp Cloud API).
- Memória persistente e learning loop.
- Marketplace de skills com validação e rollback.
- MCP client/server para integração com ferramentas externas.

## Status Atual

- `159` testes passando (`pytest -q`).
- Streaming de resposta em WebSocket.
- Multiagente com persistência SQLite.
- Pairing por código (aprovação/rejeição) para novos remetentes.
- Operação com `install-daemon`, `backup` e `restore` via CLI.

## Requisitos

- Python `3.10+`
- Linux (Ubuntu/Debian/Arch etc.) ou Termux no Android
- `curl` e `git`

Para Termux (recomendado via F-Droid):

```bash
pkg update && pkg upgrade
pkg install python curl git
```

## Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

## Primeiros Passos

```bash
# 1) Diagnóstico do ambiente
clawlite doctor

# 2) Setup guiado (recomendado)
clawlite onboarding
```

## Onboarding Wizard (QuickStart vs Avançado)

O `clawlite onboarding` agora segue um fluxo próximo ao OpenClaw:

- **QuickStart (recomendado)**: aplica defaults seguros para rodar rápido em ambiente local.
- **Avançado**: expõe todas as etapas com revisão antes de salvar.

Etapas principais cobertas no wizard:

1. **Model/Auth** (provedor e validação de API key)
2. **Workspace** (inicialização dos arquivos de memória)
3. **Gateway** (host/porta/token)
4. **Canais** (Telegram/Discord/Slack/WhatsApp/Teams)
5. **Daemon** (planejamento de `systemd --user`)
6. **Health check** (preflight de doctor + porta + token)
7. **Skills** (perfil inicial e seleção)
8. **Review + Apply** (prévia com segredos mascarados antes de persistir)

Após o onboarding:

```bash
# Ajustes avançados
clawlite configure

# Subir gateway local
clawlite start --host 0.0.0.0 --port 8787

# Dashboard
# http://127.0.0.1:8787
```

## Operação de Produção

### Daemon (systemd user)

```bash
clawlite install-daemon --host 127.0.0.1 --port 8787
```

### Pairing de novos remetentes

```bash
# listar pendências
clawlite pairing list

# aprovar/rejeitar
clawlite pairing approve telegram ABC123
clawlite pairing reject telegram ABC123

# listar aprovados
clawlite pairing approved
```

### Backup e restore

```bash
# criar backup
clawlite backup create --label daily

# listar backups
clawlite backup list

# restaurar
clawlite backup restore ~/.clawlite/backups/clawlite_backup_YYYYMMDD_HHMMSS_daily.tar.gz
```

## Comandos Principais

```bash
clawlite run "seu prompt"
clawlite status
clawlite doctor
clawlite start
clawlite skill search github
clawlite skill install github
clawlite mcp list
clawlite agents list
clawlite cron list
```

## Arquitetura (Resumo)

```text
Canais (Telegram/Discord/Slack/WhatsApp)
                |
                v
        FastAPI + WebSocket Gateway
                |
      +---------+---------+
      |                   |
      v                   v
  Runtime Agent       Dashboard Web
 (model/tools/memory) (status/skills/logs/channels)
      |
      v
 Skills + MCP + Workspace
```

### Componentes principais

- `clawlite/gateway`: rotas HTTP/WS e dashboard.
- `clawlite/channels`: conectores de canais e manager.
- `clawlite/core`: agent runtime, ferramentas, plugins, RBAC.
- `clawlite/runtime`: memória, learning, cron, backup, pairing, daemon, voz.
- `clawlite/skills`: catálogo de skills Python.

## Segurança

- Token Bearer para acesso ao gateway.
- Pairing por código para controle de remetentes novos.
- Políticas de segurança no `configure` e `security` config.
- Execução de worker multiagente sem `shell=True`.

## Skills e MCP

- Skills instaláveis/publicáveis via CLI.
- Auto-update com validação de integridade.
- MCP com `add/list/remove/install`.

Exemplos:

```bash
clawlite skill search weather
clawlite skill install weather

clawlite mcp install filesystem
clawlite mcp list
```

## Documentação Técnica

- [Dashboard](docs/DASHBOARD.md)
- [MCP](docs/MCP.md)
- [Multiagente e Multicanal](docs/MULTIAGENTE_MULTICANAL_PTBR.md)
- [Session Memory](docs/SESSION_MEMORY.md)
- [Voice](docs/VOICE.md)
- [Runbook](docs/RUNBOOK.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)

## Desenvolvimento

```bash
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
python -m venv .venv
source .venv/bin/activate
pip install -e .
pytest -q
```

## Contribuição

1. Abra uma issue descrevendo problema/feature.
2. Crie branch com escopo claro.
3. Adicione ou ajuste testes.
4. Abra PR com contexto técnico objetivo.

## Licença

MIT. Veja [LICENSE](LICENSE).
