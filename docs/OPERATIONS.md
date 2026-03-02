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
pytest -q tests_next
```

## Verificar saúde

```bash
curl -sS http://127.0.0.1:8787/health | python -m json.tool
```

## Cron manual

```bash
clawlite cron add --session-id cli:ops --expression "every 300" --prompt "status rapido"
clawlite cron list --session-id cli:ops
```

## Incident checklist

1. Confirmar `/health`.
2. Confirmar `clawlite run "ok"`.
3. Validar provider (`CLAWLITE_MODEL`, `CLAWLITE_LITELLM_API_KEY`).
4. Rodar `pytest -q tests_next` antes de qualquer release/hotfix.
