# Guia de configuração

## Arquivo principal

O arquivo principal fica em `~/.clawlite/config.json`.

Exemplo completo:
- `docs/config.example.json`

## Campos centrais

```bash
workspace_path
state_path
provider.model
provider.litellm_base_url
provider.litellm_api_key
gateway.host
gateway.port
gateway.token
scheduler.heartbeat_interval_seconds
scheduler.timezone
channels.<canal>
```

## Fluxo recomendado

```bash
clawlite onboard
clawlite start --host 127.0.0.1 --port 8787
```

## Variáveis de ambiente

- `CLAWLITE_MODEL`
- `CLAWLITE_WORKSPACE`
- `CLAWLITE_LITELLM_BASE_URL`
- `CLAWLITE_LITELLM_API_KEY`
- `CLAWLITE_API_KEY` (fallback genérico)
- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY`
- `GEMINI_API_KEY` / `GOOGLE_API_KEY`
- `GROQ_API_KEY`
- `DEEPSEEK_API_KEY`
- `CLAWLITE_GATEWAY_HOST`
- `CLAWLITE_GATEWAY_PORT`

## Resolução automática de autenticação

- O runtime detecta provedor por `model`, `api_key` e `base_url`.
- Se você usar `gemini/...` com `GEMINI_API_KEY`, a base URL é ajustada automaticamente.
- Erros de autenticação/configuração retornam mensagens acionáveis no endpoint `/v1/chat`.

➡️ Próxima página: [Skills](/skills-reference)
