# Configuration

Arquivo padrão: `~/.clawlite/config.json`

Schema principal (`clawlite/config/schema.py`):
- `workspace_path`
- `state_path`
- `provider`:
  - `model`
  - `litellm_base_url`
  - `litellm_api_key`
- `gateway`:
  - `host`
  - `port`
  - `token`
- `scheduler`:
  - `heartbeat_interval_seconds`
  - `timezone`
- `channels` (dict por canal)

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

## Resolução automática do provedor

- `provider.model` define o provedor preferencial (`gemini/...`, `openrouter/...`, `openai/...`, `groq/...`).
- Se a chave não estiver em `provider.litellm_api_key`, o runtime tenta variáveis de ambiente específicas por provedor.
- `provider.litellm_base_url` é opcional para provedores comuns: o runtime aplica base URL padrão por provedor.

## Exemplo

Veja: [config.example.json](./config.example.json)
