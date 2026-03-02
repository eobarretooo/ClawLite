# ClawLite

Assistente pessoal autônomo em Python, com arquitetura modular própria e foco em execução real.

## O que já está no runtime atual

- Engine único para chat/canais com prompt de workspace + memória + skills
- Gateway FastAPI (`/health`, `/v1/chat`, `/v1/cron/*`, `/v1/ws`)
- Scheduler com cron e heartbeat
- Sistema de skills por `SKILL.md` com autoload e execução por `command/script`
- Estrutura preparada para múltiplos canais e subagentes

## Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

Desenvolvimento local:

```bash
pip install -e .
```

## Quickstart

```bash
clawlite onboard
export CLAWLITE_MODEL="gemini/gemini-2.5-flash"
export CLAWLITE_LITELLM_API_KEY="<sua-chave>"
clawlite start --host 127.0.0.1 --port 8787
```

Teste rápido:

```bash
curl -sS http://127.0.0.1:8787/v1/chat \
  -H 'content-type: application/json' \
  -d '{"session_id":"cli:demo","text":"quem voce e?"}'
```

## CLI principal

```bash
clawlite start
clawlite run "resuma este projeto"
clawlite onboard
clawlite skills list
clawlite skills show cron
clawlite cron add --session-id cli:ops --expression "every 120" --prompt "status"
clawlite cron list --session-id cli:ops
clawlite cron remove --job-id <id>
```

## Documentação

- [Docs Index](docs/README.md)
- [Quickstart](docs/QUICKSTART.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/CONFIGURATION.md)
- [API](docs/API.md)
- [Skills](docs/SKILLS.md)
- [Operations](docs/OPERATIONS.md)

## Estrutura

```text
clawlite/
├── core/
├── tools/
├── bus/
├── channels/
├── gateway/
├── scheduler/
├── providers/
├── session/
├── config/
├── workspace/
├── skills/
├── cli/
└── utils/
```

## Referências

ClawLite é implementação própria. Agradecimento aos projetos open source **OpenClaw** e **nanobot**, usados como referência de arquitetura e operação para inspirar decisões de design.

## Licença

MIT
