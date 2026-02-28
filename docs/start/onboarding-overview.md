# Onboarding Overview

Este documento resume os caminhos de onboarding do ClawLite e quando usar cada um.

## Escolha seu caminho

- Wizard CLI: fluxo principal para Linux e Termux.
- Configure Menu: ajustes pontuais após onboarding.

## Wizard CLI

Comando:

```bash
clawlite onboarding
```

Use quando quiser configurar modelo, auth, workspace, gateway, canais e skills em um fluxo único.

Referência completa:

- [Onboarding Wizard (CLI)](wizard.md)

## Configure Menu

Comando:

```bash
clawlite configure
```

Use para alterar seções específicas sem repetir todo o wizard.

## Modelo de confiança

Por padrão, o ClawLite é um assistente pessoal com um único operador confiável.

Em setups compartilhados ou expostos em rede:

- mantenha token obrigatório no gateway;
- use pareamento para novos remetentes;
- limite canais e ferramentas ao mínimo necessário.
