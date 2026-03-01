# Beta Release Checklist (Pass/Fail)

Uso: execute cada item e marque somente `PASS` ou `FAIL`.
Regra: se qualquer item falhar, release beta bloqueada.

## Gate 1 - Testes obrigatorios

1. Testes E2E de falha + recuperacao outbound  
Comando:
```bash
pytest -q tests/test_channels_outbound_resilience.py
```
Criterio PASS: saida final contem `passed` e `failed=0`.

2. Testes de API de metricas e thresholds  
Comando:
```bash
pytest -q tests/test_cron_channels_metrics.py -k "outbound or metrics"
```
Criterio PASS: saida final contem `passed` e `failed=0`.

3. Testes de hardening de webhooks (Prioridade 1)  
Comando:
```bash
pytest -q tests/test_webhooks_hardening.py
```
Criterio PASS: saida final contem `passed` e `failed=0`.

## Gate 2 - Saude runtime (ambiente real)

4. Nenhum canal em erro de outbound  
Comando:
```bash
TOKEN=$(python -c "from clawlite.gateway.server import _token; print(_token())")
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8787/api/channels/status \
  | jq '[.channels[] | .outbound_health.pass] | all'
```
Criterio PASS: output exatamente `true`.

5. Threshold de latencia respeitado no agregado  
Comando:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8787/api/metrics \
  | jq '.channels_outbound.health.summary.error == 0'
```
Criterio PASS: output exatamente `true`.

6. Circuit breaker sem bloqueio critico  
Comando:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8787/api/channels/status \
  | jq '[.channels[] | .outbound.circuit_blocked_count <= 5] | all'
```
Criterio PASS: output exatamente `true`.

## Gate 3 - Recuperacao operacional

7. Reconnect do canal afetado funciona  
Comando:
```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  http://127.0.0.1:8787/api/channels/reconnect \
  -d '{"channel":"irc"}' | jq '.ok == true and (.started | length) >= 1'
```
Criterio PASS: output exatamente `true`.

8. Fallback padronizado registrado em falha real (quando houver incidente)  
Comando:
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8787/api/dashboard/logs?level=error&limit=50" \
  | jq '.logs[] | select((.event=="channels.outbound.failed") and (.data.code != null) and (.data.fallback != null)) | .data' | head -n 1
```
Criterio PASS: existe ao menos uma linha retornada com `code` e `fallback`.

## Resultado da release

- PASS FINAL: itens 1..8 em PASS.
- FAIL FINAL: qualquer item em FAIL.

Registro recomendado no PR:
```text
Beta Release Checklist:
1 PASS
2 PASS
3 PASS
4 PASS
5 PASS
6 PASS
7 PASS
8 PASS
```
