# 🖥️ Comandos CLI

Referência dos comandos suportados no runtime atual.

## Núcleo

```bash
clawlite start --host 127.0.0.1 --port 8787
clawlite run "resuma o diretório"
clawlite onboard
```

## Skills

```bash
clawlite skills list
clawlite skills list --all
clawlite skills show cron
```

## Cron

```bash
clawlite cron add --session-id cli:ops --expression "every 120" --prompt "status"
clawlite cron list --session-id cli:ops
clawlite cron remove --job-id <id>
```

## Variáveis de ambiente mais usadas

```bash
export CLAWLITE_MODEL="gemini/gemini-2.5-flash"
export CLAWLITE_LITELLM_API_KEY="<chave>"
export CLAWLITE_GATEWAY_HOST="127.0.0.1"
export CLAWLITE_GATEWAY_PORT="8787"
```

➡️ Próxima página: [Configuração](/configuration)
