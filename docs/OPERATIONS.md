# Operations

## Start / stop

```bash
clawlite start --host 127.0.0.1 --port 8787
```

## Smoke test local

```bash
bash scripts/smoke_test.sh
```

## Testes

```bash
pytest -q tests
```

Preflight de config estrita (falha com rc=2 em chave invalida/erro de parse):

```bash
clawlite validate config
```

## Verificar saúde

```bash
curl -sS http://127.0.0.1:8787/health | python -m json.tool
```

## Verificar aliases de compatibilidade do gateway

```bash
curl -sS http://127.0.0.1:8787/
curl -sS http://127.0.0.1:8787/api/status | python -m json.tool
curl -sS http://127.0.0.1:8787/api/diagnostics | python -m json.tool
curl -sS -X POST http://127.0.0.1:8787/api/message \
  -H 'content-type: application/json' \
  -d '{"session_id":"cli:ops","text":"ping"}' | python -m json.tool
curl -sS http://127.0.0.1:8787/api/token | python -m json.tool
```

Notas:
- `/api/status` e `/api/message` espelham `/v1/status` e `/v1/chat`.
- `/api/diagnostics` espelha `/v1/diagnostics` (mesma auth e semântica de payload).
- `/api/token` retorna token mascarado (nunca o token bruto).
- `WS /ws` espelha `WS /v1/ws`.
- `/v1/status` e `/api/status` expõem `contract_version` e `server_time`.
- `/v1/status` e `/api/status` incluem componente `bootstrap` com visibilidade de pendência/último estado.
- `/v1/diagnostics` e `/api/diagnostics` expõem `generated_at`, `uptime_s` e `contract_version`.
- `/v1/diagnostics` e `/api/diagnostics` incluem `bootstrap` com estado persistido (`pending`, `last_status`, `completed_at`, etc.).
- `/v1/diagnostics` e `/api/diagnostics` incluem `http` com contadores de requisicoes em memoria (`total_requests`, `in_flight`, `by_method`, `by_path`, `by_status`, `latency_ms`).
- `/v1/diagnostics` e `/api/diagnostics` incluem `channels_delivery` para inspecao de contadores de entrega por total e por canal.
- `channels_delivery` inclui supressao idempotente outbound e confirmacao/falha final (`idempotency_suppressed`, `delivery_confirmed`, `delivery_failed_final`).
- `/v1/diagnostics` e `/api/diagnostics` incluem `engine.turn_metrics` com contadores por turno (`turns_total`, `turns_success`, `turns_provider_errors`, `turns_cancelled`), `tool_calls_executed`, buckets de latencia e ultimo resultado/modelo.
- Telemetria de provider/failover inclui classificacao de erro (`last_error_class`, `error_class_counts`, `last_primary_error_class`, `last_fallback_error_class`) para diagnostico operacional.
- `queue.dead_letter_recent` expoe snapshots por mensagem (sem `text`) para inspecionar outcomes de fallback/dead-letter em ordem mais recente primeiro.

## Bootstrap one-shot lifecycle

- `BOOTSTRAP.md` é processado como etapa one-shot: após o primeiro turno de usuário bem-sucedido (sessões não internas), o gateway remove o arquivo e grava `memory/bootstrap-state.json`.
- Sessões internas (`heartbeat:*`, `autonomy:*`, `bootstrap:*`) não finalizam bootstrap automaticamente.
- Visibilidade local: `clawlite status` (`bootstrap_pending`, `bootstrap_last_status`) e `clawlite diagnostics` (`local.bootstrap`).

## Retrieval observability + eval

```bash
curl -sS http://127.0.0.1:8787/api/diagnostics | python -m json.tool
clawlite memory eval --limit 5
```

Checagens rápidas:
- `engine.retrieval_metrics.route_counts` mostra rotas `NO_RETRIEVE/RETRIEVE/NEXT_QUERY`.
- `engine.retrieval_metrics.retrieval_attempts/hits/rewrites` mostram volume e rewrites do planner.
- `engine.retrieval_metrics.latency_buckets` mostra distribuição de latência do path de busca.
- `clawlite memory eval` retorna JSON determinístico (`ok`, `cases`, `passed`, `failed`, `details`).

## Cron manual

```bash
clawlite cron add --session-id cli:ops --expression "every 300" --prompt "status rapido"
clawlite cron list --session-id cli:ops
```

## Memory doctor

```bash
clawlite memory doctor
clawlite memory doctor --repair
```

Campos esperados no JSON:
- `ok`, `repair_applied`
- `paths` (`history`, `curated`, `checkpoints`)
- `files` (`exists`, `size_bytes`, `mtime` por arquivo)
- `counts` (`history`, `curated`, `total`)
- `analysis` (`recent`, `temporal_marked_count`, `top_sources`)
- `diagnostics` (contadores de reparo/dedup/recovery)
- `schema` (hints de versão/chaves para curated e checkpoints)

## Codex provider auth lifecycle

```bash
clawlite provider login openai-codex --access-token "..." --account-id "org_..." --set-model
clawlite provider status openai-codex
clawlite validate provider
clawlite provider logout openai-codex
```

Notas:
- `openai-codex/*` usa caminho dedicado Codex (sem fallback silencioso para OpenAI LiteLLM).
- Em erro de token ausente/expirado, gateway retorna orientação explícita para `clawlite provider login openai-codex`.
- `clawlite provider status` também suporta providers de API key (`openai`, `gemini`, `groq`, `deepseek`, `anthropic`, `openrouter`, `custom`) com payload seguro de origem/configuração.

Troca segura de provider/modelo ativo:

```bash
clawlite provider use openai --model openai/gpt-4.1-mini --fallback-model openai/gpt-4o-mini
clawlite provider use openai --model openai/gpt-4.1-mini --clear-fallback
```

## Incident checklist

1. Confirmar `/health`.
2. Confirmar `clawlite run "ok"`.
3. Validar provider (`CLAWLITE_MODEL`, `CLAWLITE_LITELLM_API_KEY`).
4. Rodar `pytest -q tests` antes de qualquer release/hotfix.
