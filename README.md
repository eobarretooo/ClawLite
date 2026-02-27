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
