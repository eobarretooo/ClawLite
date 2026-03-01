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

Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/refs/heads/main/scripts/install.sh | bash
```

Requisitos mínimos:

- Python `3.10+`
- Linux
- `git` e `curl`
- Dependências Python em `requirements.txt` (instaladas automaticamente pelo `install.sh`)

## Termux (somente via proot Ubuntu)

No GitHub do ClawLite, o fluxo suportado para Termux é apenas via proot Ubuntu.
Não use instalação nativa no Termux para o caminho oficial.

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/refs/heads/main/scripts/setup_termux_proot.sh | bash
```

Ou localmente no repositório:

```bash
bash scripts/setup_termux_proot.sh
```

Depois:

```bash
clawlitex status
clawlitex onboarding
clawlitex start
```

`clawlitex` funciona como proxy no Termux e repassa qualquer comando para o `clawlite` dentro do proot:

```bash
clawlitex doctor
clawlitex update --check
clawlitex configure
```

## Providers de IA (atualizado)

O ClawLite suporta providers no padrão `provider/model`, incluindo:

- `openai`, `openai-codex`, `anthropic`, `gemini`, `openrouter`, `groq`
- `moonshot`, `mistral`, `xai`, `together`, `huggingface`
- `nvidia`, `qianfan`, `venice`, `minimax`, `xiaomi`, `zai`
- `litellm`, `vercel-ai-gateway`, `kilocode`, `vllm`, `ollama`

Configuração de auth:

```bash
clawlite auth login <provider>
clawlite auth status
```

No `clawlite configure`, ao selecionar o provider o link oficial de login/chave também é exibido.

Codex:
- `openai-codex/*` pode usar `OPENAI_CODEX_API_KEY` / `OPENAI_API_KEY`.
- No `clawlite auth login openai-codex`, o ClawLite tenta reutilizar `~/.codex/auth.json` automaticamente quando disponível.
- Se não houver token salvo, o ClawLite tenta iniciar o OAuth via `codex login` (gera/abre o link de autenticação) e importa o token no final.
- Em Termux Android nativo, o binário do Codex CLI pode ser incompatível; nesse caso use API key ou importe `~/.codex/auth.json` de um ambiente Linux/macOS compatível.

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
2. Teste de API key
3. Workspace
4. Gateway
5. Canais
6. Daemon
7. Health check
8. Skills
9. Review + Apply

Referências:

- [Onboarding Overview](docs/start/onboarding-overview.md)
- [Onboarding Wizard (CLI)](docs/start/wizard.md)

## Primeiros comandos

```bash
clawlite doctor
clawlite onboarding
clawlite start --host 127.0.0.1 --port 8787
```

## Atualização sem reinstalar instalador

```bash
clawlite update
```

Somente checar:

```bash
clawlite update --check
```

Selecionar canal de atualização:

```bash
clawlite update --channel stable
clawlite update --channel beta --check
clawlite update --channel dev
```

Regras de canal:

- `stable`: segue a release estável mais recente no GitHub (tag `vX.Y.Z`).
- `beta`: segue a prerelease beta mais recente (tag `vX.Y.Z-beta.N`), com fallback para stable quando beta estiver atrás.
- `dev`: segue `main` (snapshot contínuo).
- Ao informar `--channel`, o canal fica salvo em `~/.clawlite/config.json` (`update.channel`).

Comportamento no `start`:

- Ao rodar `clawlite start`, o ClawLite faz checagem rápida de versão e avisa se houver update.
- Para desativar a checagem no boot do gateway: `export CLAWLITE_SKIP_UPDATE_CHECK=1` ou `update.check_on_start=false` no config.

Dashboard local:

- `http://127.0.0.1:8787`

## Dashboard web (status atual)

O dashboard web do ClawLite está em modo completo (estilo Control UI), com abas funcionais:

- `Overview`: status do gateway, uptime, conexões, métricas de runtime e heartbeat.
- `Chat`: chat em tempo real via WebSocket (`/ws/chat`) com metadados de execução.
- `Sessions`: busca/inspeção de sessões e reuso da sessão no chat.
- `Sessions` (paridade): preview, rename (`patch`), reset, delete e compact de histórico.
- `Telemetry`: eventos, tokens, custo estimado, timeline e ranking por sessão.
- `Channels`: status de canais, instâncias, reconnect e fluxo de pairing (approve/reject).
- `Cron`: criação/listagem/remoção de jobs recorrentes.
- `Config`: edição de model/hooks/channels com validação (`dry_run`) e apply.
- `Workspace`: editor de `SOUL.md`, `USER.md`, `HEARTBEAT.md`, `BOOTSTRAP.md`.
- `Skills`: install/enable/disable/remove + update (dry-run/apply) e leitura do hub.
- `Agents`: criação de agentes, bindings e inspeção do estado atual.
- `Logs`: stream em tempo real com filtros (`level`, `event`, `q`).
- `Security`: RBAC, políticas de tool (`allow/review/deny`) e trilha de auditoria.

## Segurança

O ClawLite conecta canais reais (Telegram/Discord/Slack/WhatsApp/Google Chat/IRC/Signal/iMessage/Teams). Trate mensagens de entrada como input não confiável.

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
