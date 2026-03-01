# Operação e Release

Guia objetivo para operação diária, incidentes outbound e critérios de release.

## Runbooks oficiais

- `docs/RUNBOOK.md` — incidentes gerais do gateway/canais/runtime.
- `docs/OUTBOUND_FAILURE_RECOVERY_RUNBOOK.md` — falha/recuperação outbound dos canais novos.

## Checklist de beta (passa/falha)

Use sempre o checklist binário antes de criar tag beta:

- `docs/BETA_RELEASE_CHECKLIST.md`

Critério: qualquer item em FAIL bloqueia a release.

## Verificações mínimas

```bash
pytest -q tests/test_channels_outbound_resilience.py tests/test_cron_channels_metrics.py tests/test_outbound_policy.py
pytest -q tests/test_webhooks_hardening.py
```

Runtime:

```bash
TOKEN=$(python -c "from clawlite.gateway.server import _token; print(_token())")
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/channels/status
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/metrics
```

## Canais cobertos no hardening/outbound resiliente

- `googlechat`
- `irc`
- `signal`
- `imessage`
