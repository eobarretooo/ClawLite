# 🖥️ Comandos CLI

Referência objetiva dos comandos principais do ClawLite.

## Operação

```bash
clawlite doctor
clawlite status
clawlite start --port 8787
clawlite run "resuma o diretório"
clawlite agent
clawlite agent -m "quem você é?"
```

## Configuração

```bash
clawlite onboarding
clawlite configure
clawlite auth status
clawlite providers list
clawlite providers use gemini --model gemini-2.5-flash
clawlite providers current
```

## Skills

```bash
clawlite skills list --all
clawlite skill search github
clawlite skill install github
clawlite skill publish ./skills/minha-skill --version 0.1.0 --category Desenvolvimento --status stable
```

## Runtime

```bash
clawlite channels list
clawlite channels status
clawlite channels reconnect telegram
clawlite cron list
clawlite stats --period week
clawlite memory semantic-search "preferências"
```

➡️ Próxima página: [Skills](/skills-reference)
