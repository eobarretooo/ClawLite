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
- `CLAWLITE_GATEWAY_HOST`
- `CLAWLITE_GATEWAY_PORT`

## Exemplo

Veja: [config.example.json](./config.example.json)
