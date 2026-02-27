# ClawLite

[![Docs](https://img.shields.io/badge/docs-online-7c3aed?style=for-the-badge)](https://eobarretooo.github.io/ClawLite/)
[![License](https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge)](LICENSE)
[![Stars](https://img.shields.io/github/stars/eobarretooo/ClawLite?style=for-the-badge)](https://github.com/eobarretooo/ClawLite)

Assistente de IA open source para **Linux + Termux** com:

- Gateway WebSocket com autenticação por token
- Menu de configuração interativo (`clawlite configure`)
- Onboarding guiado (`clawlite onboarding`)
- Auth para provedores de IA (`clawlite auth login ...`)
- Ecossistema de skills extensível

## Instalação (1 comando)

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

## Contribuição

1. Fork
2. Branch: `feat/minha-feature`
3. Commit + push
4. Pull Request com contexto e teste
