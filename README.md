<p align="center">
  <img src="assets/mascot-animated.svg" alt="ClawLite Mascot" width="120" />
</p>

<h1 align="center">ClawLite</h1>

<p align="center">
  Assistente de IA pessoal, open source e local-first para Linux e Termux.
  Gateway WebSocket, multicanal, memória persistente, skills e MCP.
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

## ClawLite como assistente pessoal

O ClawLite foi desenhado para rodar como seu assistente pessoal, no seu ambiente, com controle explícito sobre canais, ferramentas e memória.

Princípios:

- Local-first: estado e operação no seu dispositivo por padrão.
- Um operador confiável: o setup padrão assume uso pessoal, não multi-tenant.
- Segurança pragmática: token no gateway, pareamento de remetentes e políticas configuráveis.
- Operação contínua: daemon, backup/restore e checks de saúde.

## Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

Requisitos mínimos:

- Python `3.10+`
- Linux ou Termux
- `git` e `curl`

## Onboarding (fluxo estilo OpenClaw, adaptado ao ClawLite)

Comando:

```bash
clawlite onboarding
```

Modos:

- QuickStart: defaults seguros para subir rápido em ambiente local.
- Avançado: fluxo completo com revisão antes de aplicar.

Etapas do wizard:

1. Model/Auth
2. Workspace
3. Gateway
4. Canais
5. Daemon
6. Health check
7. Skills
8. Review + Apply

Referências:

- [Onboarding Overview](docs/start/onboarding-overview.md)
- [Onboarding Wizard (CLI)](docs/start/wizard.md)

## Primeiros comandos

```bash
clawlite doctor
clawlite onboarding
clawlite start --host 127.0.0.1 --port 8787
```

Dashboard local:

- `http://127.0.0.1:8787`

## Segurança

O ClawLite conecta canais reais (Telegram/Discord/Slack/WhatsApp/Teams). Trate mensagens de entrada como input não confiável.

Checklist mínimo:

- Mantenha `security.require_gateway_token=true`.
- Use `clawlite pairing` para aprovar remetentes novos.
- Evite expor gateway em rede pública sem camada extra de proteção.
- Rode `clawlite doctor` após mudanças de configuração.

Política completa em [SECURITY.md](SECURITY.md).

## Operação de produção

Daemon (systemd user):

```bash
clawlite install-daemon --host 127.0.0.1 --port 8787
```

Backup e restore:

```bash
clawlite backup create --label daily
clawlite backup list
clawlite backup restore ~/.clawlite/backups/clawlite_backup_YYYYMMDD_HHMMSS_daily.tar.gz
```

## Arquitetura (resumo)

```text
Canais -> Gateway FastAPI/WebSocket -> Runtime Agent -> Skills/MCP/Workspace
```

Componentes:

- `clawlite/gateway`: HTTP/WS, dashboard e rotas operacionais.
- `clawlite/channels`: conectores e manager multicanal.
- `clawlite/core`: runtime do agente e ferramentas.
- `clawlite/runtime`: memória, cron, daemon, backup, pairing e status.
- `clawlite/skills`: catálogo de skills Python.

## Documentação principal

- [Wizard](docs/start/wizard.md)
- [Skills OpenClaw Compatibility](docs/SKILLS_OPENCLAW_COMPAT.md)
- [Dashboard](docs/DASHBOARD.md)
- [MCP](docs/MCP.md)
- [Runbook](docs/RUNBOOK.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Session Memory](docs/SESSION_MEMORY.md)

## Compatibilidade de skills (OpenClaw → ClawLite)

O catálogo `skills/` do ClawLite agora inclui skills importadas do OpenClaw com adaptação para este runtime.

- Skills com equivalente direto foram mapeadas para backends nativos do ClawLite (ex.: `gh-issues` → `github`, `openai-whisper` → `whisper`, `xurl` → `web-fetch`).
- Skills sem backend nativo no ClawLite retornam guidance operacional com alternativas.

## Agradecimentos

Obrigado ao projeto [OpenClaw](https://github.com/openclaw/openclaw), que é open source.
O ClawLite aproveitou referências técnicas e de organização do ecossistema OpenClaw para acelerar arquitetura, onboarding e portabilidade de skills.

## Desenvolvimento

```bash
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
python -m venv .venv
source .venv/bin/activate
pip install -e .
pytest -q
```

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md).

## Licença

MIT. Veja [LICENSE](LICENSE).
