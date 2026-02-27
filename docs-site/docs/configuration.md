# Configuration (Onboarding)

O onboarding interativo configura o ambiente base em poucos passos.

## Executar onboarding

```bash
clawlite onboarding
```

## O que é configurado

- modelo padrão
- canais habilitados (Telegram/Discord)
- token do gateway

## Arquivo de configuração

```text
~/.clawlite/config.json
```

Exemplo:

```json
{
  "model": "openai/gpt-4o-mini",
  "gateway": {
    "host": "0.0.0.0",
    "port": 8787,
    "token": "***"
  },
  "channels": {
    "telegram": {"enabled": true},
    "discord": {"enabled": false}
  },
  "skills": ["core-tools", "memory", "gateway"]
}
```
