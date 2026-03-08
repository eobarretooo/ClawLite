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

## Release preflight

```bash
clawlite validate preflight
clawlite validate preflight --gateway-url http://127.0.0.1:8787
clawlite validate preflight --gateway-url http://127.0.0.1:8787 --provider-live --telegram-live
bash scripts/release_preflight.sh --config ~/.clawlite/config.json --gateway-url http://127.0.0.1:8787
```

## Stage 19 release closure checklist

1) Baseline preflight:

```bash
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

2) Memory tuning diagnostics snapshot:

```bash
curl -sS http://127.0.0.1:8787/v1/diagnostics | python -m json.tool
clawlite memory quality --gateway-url http://127.0.0.1:8787
```

3) Confirm additive tuning keys in diagnostics:
- `memory_quality_tuning`
- `engine.memory_quality`
- `environment` (expandido quando `gateway.diagnostics.include_config=true`)
- `actions_by_layer`, `actions_by_playbook`, `actions_by_action`, `action_status_by_layer`
- `last_action_metadata` com campos de Stage 18 (`template_id`, `backfill_limit`, `snapshot_tag`, `action_variant`)

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
- `clawlite skills check` emite diagnostico agregado e deterministico de skills para operadores (saude, requisitos ausentes, e issues de contrato).
- `run_skill` agora e safety-gated por canal e skills command-bound reutilizam os guardrails do tool `exec`.
- Telegram suporta runtime em webhook com validacao de `X-Telegram-Bot-Api-Secret-Token`; se ativacao de webhook falhar, o canal faz fallback seguro para polling.
- Telegram hardening adicional: dedupe unificado de updates (webhook + polling), persistencia atomica de offset (`schema_version=2`) e timeout de 5s na leitura de payload webhook (`telegram_webhook_payload_timeout`).
- `/v1/status` e `/api/status` expõem `contract_version` e `server_time`.
- `/v1/status` e `/api/status` incluem componente `bootstrap` com visibilidade de pendência/último estado.
- `/v1/diagnostics` e `/api/diagnostics` expõem `generated_at`, `uptime_s` e `contract_version`.
- `/v1/diagnostics` e `/api/diagnostics` incluem `bootstrap` com estado persistido (`pending`, `last_status`, `completed_at`, etc.).
- `/v1/diagnostics` e `/api/diagnostics` incluem `http` com contadores de requisicoes em memoria (`total_requests`, `in_flight`, `by_method`, `by_path`, `by_status`, `latency_ms`).
- `/v1/diagnostics` e `/api/diagnostics` incluem `memory_monitor` com telemetria operacional (`enabled`, `scans`, `generated`, `deduped`, `low_priority_skipped`, `cooldown_skipped`, `sent`, `failed`, `pending`, `cooldown_seconds`, `suggestions_path`).
- `/v1/diagnostics` e `/api/diagnostics` incluem `channels_delivery` para inspecao de contadores de entrega por total e por canal.
- `channels_delivery` inclui supressao idempotente outbound e confirmacao/falha final (`idempotency_suppressed`, `delivery_confirmed`, `delivery_failed_final`).
- `channels_delivery.recent` lista outcomes por mensagem (mais recente primeiro), incluindo `send_result` e `receipt` seguro de canais como Telegram (`message_ids`, `last_message_id`, `chunks`, `chat_id`).
- Telegram tambem ingere eventos `callback_query`; contadores operacionais podem ser inspecionados em `engine.channels.telegram_signals` (ex.: `callback_query_received_count`, `callback_query_blocked_count`, `callback_query_ack_error_count`).
- Telegram tambem ingere `message_reaction` com politica `reaction_notifications=off|own|all`; acompanhe `message_reaction_received_count`, `message_reaction_blocked_count`, `message_reaction_ignored_bot_count` e `message_reaction_emitted_count` em `engine.channels.telegram_signals`.
- Autorizacao de ingress Telegram agora e sensivel a contexto (DM, grupo, topico) para `message/channel_post`, `callback_query` e `message_reaction`, com politica por contexto e `group_overrides` por chat/topico.
- Contadores agregados de decisao de politica ficam em `engine.channels.telegram_signals`: `policy_allowed_count` e `policy_blocked_count`.
- Telegram ingere tambem updates de canal `channel_post` e `edited_channel_post` (polling e webhook) pelo mesmo pipeline inbound.
- Tool `message` suporta `metadata` e `buttons` para inline keyboard do Telegram via `_telegram_inline_keyboard`.
- Tool `message` suporta a surface de acoes Telegram via `action`/`metadata` (`send`, `reply`, `edit`, `delete`, `react`, `create_topic`) com bridge por `_telegram_action*`.
- `/v1/diagnostics` e `/api/diagnostics` incluem `engine.turn_metrics` com contadores por turno (`turns_total`, `turns_success`, `turns_provider_errors`, `turns_cancelled`), `tool_calls_executed`, buckets de latencia e ultimo resultado/modelo.
- Telemetria de provider/failover inclui classificacao de erro (`last_error_class`, `error_class_counts`, `last_primary_error_class`, `last_fallback_error_class`) para diagnostico operacional.
- `queue.dead_letter_recent` expoe snapshots por mensagem (sem `text`) para inspecionar outcomes de fallback/dead-letter em ordem mais recente primeiro.
- Heartbeat pode disparar entrega proactive de memoria quando `agents.defaults.memory.proactive=true` e houver sugestoes com prioridade suficiente.

## Bootstrap one-shot lifecycle

- `BOOTSTRAP.md` é processado como etapa one-shot com ciclo de startup: quando o arquivo ainda está pendente, o gateway executa bootstrap usando a sessão interna `bootstrap:system`, grava o estado em `memory/bootstrap-state.json` e remove `BOOTSTRAP.md` após sucesso.
- Sessões internas continuam separadas do tráfego normal de usuário; o bootstrap não depende mais do primeiro turno externo bem-sucedido para ser finalizado.
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

## Memory lifecycle runbook

Visao e estado rapido:

```bash
clawlite memory
clawlite memory profile
clawlite memory privacy
clawlite memory suggest
```

Versionamento e rollback:

```bash
clawlite memory snapshot --tag before_change
clawlite memory version
clawlite memory rollback <id>
```

Branches e merge:

```bash
clawlite memory branches
clawlite memory branch feature-x --from-version <id> --checkout
clawlite memory checkout main
clawlite memory merge --source feature-x --target main --tag merge
```

Compartilhamento e portabilidade:

```bash
clawlite memory share-optin --user alice --enabled true
clawlite memory export --out /tmp/memory-export.json
clawlite memory import /tmp/memory-export.json
```

Saude do monitor proativo:
- Rode `clawlite diagnostics --gateway-url http://127.0.0.1:8787` e confirme `memory_monitor.enabled=true` quando `agents.defaults.memory.proactive=true`.
- Verifique progresso com `memory_monitor.scans/generated/sent/failed` e backlog com `memory_monitor.pending`.
- Se houver falhas recorrentes de entrega, confira `channels_delivery` e `queue.dead_letter_recent` para correlacionar causa por canal.

## Codex provider auth lifecycle

```bash
clawlite provider login openai-codex --access-token "..." --account-id "org_..."
clawlite provider status openai-codex
clawlite validate provider
clawlite provider logout openai-codex
```

Notas:
- `provider login openai-codex` agora seleciona automaticamente `openai-codex/gpt-5.3-codex`.
- Use `--keep-model` se quiser persistir a autenticação sem trocar o modelo ativo.
- `openai-codex/*` usa caminho dedicado Codex (sem fallback silencioso para OpenAI LiteLLM).
- Em erro de token ausente/expirado, gateway retorna orientação explícita para `clawlite provider login openai-codex`.
- `clawlite provider status` também suporta providers de API key (`openai`, `gemini`, `groq`, `deepseek`, `anthropic`, `openrouter`, `custom`) com payload seguro de origem/configuração.

Provider API-key auth ops:

```bash
clawlite provider set-auth openai --api-key "sk-..."
clawlite provider clear-auth openai --clear-api-base
```

Heartbeat manual trigger:

```bash
clawlite heartbeat trigger --gateway-url http://127.0.0.1:8787
```

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
