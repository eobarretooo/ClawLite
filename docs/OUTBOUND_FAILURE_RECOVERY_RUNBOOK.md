# Outbound Failure Recovery Runbook (Priority 5)

## Objetivo
Padronizar diagnostico e recuperacao dos canais novos (`googlechat`, `irc`, `signal`, `imessage`) quando houver falha outbound.

## Politica de thresholds (concreta)
Valores ativos em `clawlite/runtime/outbound_policy.py`:

| Check | Warning | Error |
| --- | --- | --- |
| Latencia outbound (`last_attempt_latency_s` ou `avg_attempt_latency_s`) | `> 5.0s` | `> 15.0s` |
| Falhas consecutivas (`circuit_consecutive_failures`) | `> 3` | `> 5` |
| Envios bloqueados pelo circuito (`circuit_blocked_count`) | `> 1` | `> 5` |
| Cooldown restante com circuito aberto (`circuit_cooldown_remaining_s`) | `> 5.0s` | `> 15.0s` |

Decisao global:
- `level=ok` -> operacao normal.
- `level=warning` -> monitorar e executar mitigacao leve.
- `level=error` -> incidente ativo, executar recuperacao imediata.

## Pre-requisitos
```bash
clawlite start
TOKEN=$(python -c "from clawlite.gateway.server import _token; print(_token())")
```

## Passo 1: Baseline de saude
Comando:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8787/api/channels/status | jq '.channels[] | {channel, level:.outbound_health.level, pass:.outbound_health.pass}'
```

Output esperado (ambiente saudavel):
```json
{"channel":"googlechat","level":"ok","pass":true}
{"channel":"irc","level":"ok","pass":true}
{"channel":"signal","level":"ok","pass":true}
{"channel":"imessage","level":"ok","pass":true}
```

Decisao:
- Todos `pass=true` -> PASS.
- Qualquer `pass=false` -> FAIL e seguir Passo 3.

## Passo 2: Triagem de warning
Comando:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8787/api/channels/status \
  | jq '.channels[] | {channel, checks:.outbound_health.checks}'
```

Exemplo real de warning:
```json
{
  "channel": "irc",
  "checks": [
    {"id":"latency","level":"warning","decision":"warn: send latency (s) (6.200) > 5.000"},
    {"id":"consecutive_failures","level":"ok","decision":"pass"},
    {"id":"circuit_blocked","level":"warning","decision":"warn: circuit blocked sends (2.000) > 1.000"}
  ]
}
```

Decisao:
- Apenas warning e sem crescimento em 10 min -> continuar monitorando.
- Warning recorrente em 3 coletas seguidas -> tratar como erro operacional e ir para Passo 3.

## Passo 3: Recuperacao de erro outbound
Disparo: `outbound_health.level=error` ou `outbound_health.pass=false`.

### 3.1 Identificar canal afetado
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8787/api/channels/status \
  | jq '.channels[] | select(.outbound_health.level=="error") | {channel, outbound, checks:.outbound_health.checks}'
```

Exemplo de erro:
```json
{
  "channel": "googlechat",
  "checks": [
    {"id":"latency","level":"error","decision":"fail: send latency (s) (16.100) > 15.000"},
    {"id":"consecutive_failures","level":"error","decision":"fail: consecutive failures (6.000) > 5.000"},
    {"id":"circuit_blocked","level":"error","decision":"fail: circuit blocked sends (6.000) > 5.000"}
  ]
}
```

### 3.2 Acao por tipo de falha
- `code=provider_timeout`:
  - Validar latencia de rede e endpoint provider.
  - Se persistir por 3 ciclos, aumentar timeout do canal em `sendTimeoutSec` e reiniciar canal.
- `code=provider_send_failed`:
  - Validar credenciais/CLI/relay.
  - Reexecutar envio manual pelo provider.
- `code=channel_unavailable`:
  - Corrigir dependencia faltante (`signal-cli`, `imsg`, webhook URL, relay URL).
- `code=provider_circuit_open`:
  - Aguardar cooldown e testar probe unico.

### 3.3 Reconnect controlado do canal
```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  http://127.0.0.1:8787/api/channels/reconnect \
  -d '{"channel":"irc"}' | jq
```

Output esperado:
```json
{"ok":true,"channel":"irc","started":["irc"]}
```

Decisao:
- `ok=true` e `started` contem o canal -> PASS.
- Sem `started` ou `ok=false` -> FAIL, escalar para intervencao manual.

## Passo 4: Verificacao de recuperacao
Comandos:
```bash
pytest -q tests/test_channels_outbound_resilience.py -k "circuit_breaker_cooldown_and_recovery"
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/metrics | jq '.channels_outbound.health'
```

Output esperado:
- `pytest`: todos os cenarios `... passed`.
- `health.summary.error == 0` apos recuperacao.

Decisao:
- Testes + metricas ok -> incidente encerrado.
- Qualquer falha -> manter incidente aberto.

## Decisao final (binaria)
- PASS: sem canais em `level=error`, `health.summary.error=0`, e testes E2E de recuperacao passando.
- FAIL: qualquer canal com `pass=false`, qualquer teste de recuperacao falhando, ou reconnect sem sucesso.
