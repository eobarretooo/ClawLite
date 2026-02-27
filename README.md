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

## UX nova do `clawlite configure` (PT-BR)

- Menu vibrante com ícones e descrições curtas
- Navegação por **setas** + seleção com **espaço** (checkbox)
- Barra de progresso por etapas
- Validações amigáveis (porta, campos obrigatórios)
- Prévia JSON antes de salvar + confirmação
- Resumo final claro após salvar

Exemplo (ASCII):

```text
╭──────────────────────────────────────────────╮
│ ⚙️ ClawLite Configure (PT-BR)               │
│ 🟪🟪🟪🟪🟪🟪🟪⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 2/6 etapas • 33% │
╰──────────────────────────────────────────────╯

? Use ↑↓ para navegar e Enter para abrir uma etapa:
❯ 🤖 Modelo e autenticação
    └─ Define IA padrão e login inicial de provedor
  📡 Canais
    └─ Liga/desliga Telegram e Discord
  👀 Prévia, confirmação e salvar
    └─ Revise tudo antes de gravar
```

Onboarding mantém o mesmo padrão visual em PT-BR, com progresso, validação e confirmação antes de persistir em `~/.clawlite/config.json`.

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

## Skills

Estrutura de skill:

```text
skills/<nome>/SKILL.md
clawlite/skills/<nome_modulo>.py
```

Registro central:

- `clawlite/skills/registry.py`

## Roadmap curto

1. Multi-agente nativo no Telegram
2. Auto-update de skills
3. Modo offline com Ollama
4. Cron por conversa

## Contribuição

1. Fork do repositório
2. Branch: `feat/minha-feature`
3. Commit + push
4. Pull Request com contexto, screenshots/logs e teste
