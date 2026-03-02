# ClawLite

Assistente pessoal autônomo em Python, com arquitetura modular própria.

## Status atual

- Runtime legado removido
- Arquitetura nova ativa (core/tools/bus/channels/gateway/scheduler/providers/session/config/workspace/skills/cli)
- Testes atuais: `31 passed` (`tests_next`)

## Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

Ou em desenvolvimento local:

```bash
pip install -e .
```

## Uso rápido

1. Onboarding do workspace:

```bash
clawlite onboard
```

2. Definir provider/modelo:

```bash
export CLAWLITE_MODEL="gemini/gemini-2.5-flash"
export CLAWLITE_LITELLM_API_KEY="<sua-chave>"
```

3. Iniciar gateway:

```bash
clawlite start --host 127.0.0.1 --port 8787
```

4. Testar chat:

```bash
curl -sS http://127.0.0.1:8787/v1/chat \
  -H 'content-type: application/json' \
  -d '{"session_id":"cli:demo","text":"quem voce e?"}'
```

## CLI disponível

```bash
clawlite start
clawlite run "resuma este projeto"
clawlite onboard
clawlite skills list
clawlite skills show cron
clawlite cron add --session-id cli:ops --expression "every 120" --prompt "check"
clawlite cron list --session-id cli:ops
```

Skills com `command/script` também podem ser executadas pelo agente via tool `run_skill`.

## Documentação

- [Docs Index](docs/README.md)
- [Quickstart](docs/QUICKSTART.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/CONFIGURATION.md)
- [API](docs/API.md)
- [Skills](docs/SKILLS.md)
- [Operations](docs/OPERATIONS.md)

## Estrutura do pacote

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

ClawLite é uma implementação própria, mas o projeto foi fortemente inspirado por ideias de arquitetura e operação observadas em projetos open source como OpenClaw e nanobot. Obrigado aos mantenedores por publicarem essas bases de referência.

## Licença

MIT
