<div align="center">
  <h1>ClawLite</h1>
  <p><strong>Assistente pessoal autônomo em Python</strong></p>
  <p>Arquitetura modular, foco em execução real e operação contínua.</p>
  <p>
    <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/license-MIT-10b981" alt="MIT">
    <img src="https://img.shields.io/badge/runtime-active-0ea5e9" alt="runtime active">
    <img src="https://img.shields.io/badge/status-in%20development-f59e0b" alt="in development">
  </p>
</div>

## Visão geral

ClawLite foi construído para ser um assistente que **age**, não só responde texto.  
O núcleo atual já unifica engine, tools, memória, cron, skills e gateway HTTP/WS.

## O que já está funcionando

- Engine único para CLI, chat e canais
- Prompt com contexto de workspace (`IDENTITY`, `SOUL`, `USER`, `AGENTS`, `TOOLS`)
- Memória persistente com busca lexical/BM25
- Gateway FastAPI (`/health`, `/v1/chat`, `/v1/cron/*`, `/v1/ws`)
- Scheduler com `cron` + `heartbeat`
- Skills por `SKILL.md` com autoload e execução via `command/script`
- Estrutura pronta para múltiplos canais e subagentes

## Instalação

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

Desenvolvimento local:

```bash
pip install -e .
```

## Quickstart (1 minuto)

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

## Arquitetura

```text
clawlite/
├── core/       # engine, prompt, memory, skills, subagent
├── tools/      # registry + ferramentas locais
├── bus/        # eventos e fila interna
├── channels/   # integrações de canal
├── gateway/    # FastAPI + websocket
├── scheduler/  # cron + heartbeat
├── providers/  # LLM providers
├── session/    # histórico por sessão
├── workspace/  # templates e bootstrap
├── skills/     # skills builtin
└── cli/        # comandos do usuário
```

## Planos futuros (roadmap de implementação)

- [ ] Fechar autonomia operacional 24/7 em Linux/proot com supervisão completa
- [ ] Expandir confiabilidade de canais com reconexão e entrega proativa robusta
- [ ] Internacionalização completa (`pt-BR` e `en`) em CLI + docs
- [ ] Evoluir sistema de skills (hub, versionamento, métricas e quality gates)
- [ ] Melhorar memória de longo prazo com consolidação mais inteligente
- [ ] Integração com ClawWork para fluxos de execução contínua
- [ ] Benchmark e tuning de provedores para custo/latência/qualidade

## Documentação

- Web docs: https://eobarretooo.github.io/ClawLite/
- [Docs Index](docs/README.md)
- [Quickstart](docs/QUICKSTART.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/CONFIGURATION.md)
- [API](docs/API.md)
- [Skills](docs/SKILLS.md)
- [Operations](docs/OPERATIONS.md)

## Agradecimentos

ClawLite é implementação própria.  
Agradecimento aos projetos open source **OpenClaw** e **nanobot**, que serviram como referência de arquitetura e operação.

## Licença

MIT
