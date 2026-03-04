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
- `/v1/diagnostics` e `/api/diagnostics` expõem `generated_at`, `uptime_s` e `contract_version`.

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

## Incident checklist

1. Confirmar `/health`.
2. Confirmar `clawlite run "ok"`.
3. Validar provider (`CLAWLITE_MODEL`, `CLAWLITE_LITELLM_API_KEY`).
4. Rodar `pytest -q tests` antes de qualquer release/hotfix.
