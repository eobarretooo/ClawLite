# ClawLite

Assistente open source em Python, portátil para **Linux** e **Termux** (ARM), com instalação simples e arquitetura modular de tools/skills/memória.

## Objetivo

Ser um assistente universal estilo "agentic CLI":
- execução de comandos locais
- memória em arquivos
- skills modulares
- suporte a múltiplos provedores LLM
- operação confiável sem Homebrew

## Status

MVP em construção (Milestone 1: bootstrap de arquitetura + CLI).

## Instalação (Linux/Termux)

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

> Durante o desenvolvimento, use instalação local:

```bash
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
bash scripts/install.sh
clawlite --help
```

## Requisitos

- Python 3.10+
- git
- curl

## Comandos iniciais

```bash
clawlite doctor
clawlite run "Resuma o diretório atual"
clawlite memory add "preferência: respostas diretas"
clawlite memory search "preferência"
```

## Estrutura

- `clawlite/cli.py` — entrada principal
- `clawlite/core/agent.py` — loop do agente
- `clawlite/core/tools.py` — registro/execução de tools locais
- `clawlite/core/memory.py` — memória local (sqlite)
- `clawlite/providers/` — provedores de LLM
- `clawlite/skills/` — skills locais em markdown
- `scripts/install.sh` — instalador Linux/Termux

## Próximos marcos

1. Tooling local robusto (`read/write/edit/exec`)
2. Provider OpenAI-compatible + fallback
3. Skill loader + roteamento por descrição
4. Sessões/subagentes locais (processos isolados)
5. Conectores Telegram/Discord opcionais
