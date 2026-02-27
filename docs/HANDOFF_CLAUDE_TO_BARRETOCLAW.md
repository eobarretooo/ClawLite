# HANDOFF — Claude Code → BarretoClaw

> Documento de transição entre agentes. Atualizado ao final de cada sessão de trabalho.
> **Não deletar histórico** — append conforme novas sessões.

---

## [2026-02-27] Sessão 1 — Produção v1 / Dashboard parity / CI

### Resumo executivo

Sessão focada em qualidade, observabilidade e paridade de dashboard. Três blocos entregues:

**Bloco 1 — Fix crítico + Dashboard parity (P0)**
- Corrigido `test_gateway_agents_endpoints` que falhava com UNIQUE constraint na 2ª execução (isolamento de DB no teste).
- Suite subiu de 44 para 81 testes (78 pré-existentes após correção + 3 novos).
- Adicionados 3 endpoints no gateway (`/api/cron`, `/api/channels/status`, `/api/metrics`) — paridade com painel OpenClaw.

**Bloco 2 — CI/CD + Smoke test (P0 Qualidade)**
- `.github/workflows/ci.yml`: matrix pytest Python 3.10+3.12, lint ruff, smoke de importação.
- `scripts/smoke_test.sh`: validação rápida pós-deploy (exit 1 se crítico falhar).
- Smoke local: 7 ok / 0 falha.

**Bloco 3 — Runbook (P0 Observabilidade)**
- `docs/RUNBOOK.md`: 7 cenários de incidente com diagnóstico + ação + validação.

---

### Arquivos alterados

| Arquivo | Tipo | O que mudou |
|---|---|---|
| `tests/test_multiagent_channels.py` | fix | `_patch_db` adicionado em `test_gateway_agents_endpoints` |
| `clawlite/gateway/server.py` | feat | endpoints `/api/cron` GET/POST/DELETE, `/api/channels/status`, `/api/metrics` |
| `tests/test_cron_channels_metrics.py` | novo | 3 testes para os novos endpoints |
| `docs/WORKLOG_CLAUDE.md` | novo | log técnico desta sessão |
| `.github/workflows/ci.yml` | novo | CI pipeline completo |
| `scripts/smoke_test.sh` | novo | smoke test script |
| `docs/RUNBOOK.md` | novo | runbook de incidentes |
| `docs/HANDOFF_CLAUDE_TO_BARRETOCLAW.md` | novo | este arquivo |

---

### Commits desta sessão

```
5dbf48d  fix(tests): isolar DB em test_gateway_agents_endpoints via _patch_db
         feat(gateway): endpoints /api/cron, /api/channels/status, /api/metrics
         test(gateway): suite test_cron_channels_metrics.py (3 testes novos)

d205865  ci: adicionar pipeline CI completo (pytest + lint + smoke) e smoke_test.sh
```

---

### Comandos de validação

```bash
# 1. Testes completos
python -m pytest tests/ -q
# Esperado: 81 passed

# 2. Smoke test
bash scripts/smoke_test.sh
# Esperado: 7 ok / 0 falha

# 3. Novos endpoints (gateway precisa estar rodando)
clawlite start --port 8787 &
TOKEN=$(python -c "from clawlite.gateway.server import _token; print(_token())")
curl -sf -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/cron
curl -sf -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/channels/status
curl -sf -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/metrics

# 4. Importação dos módulos críticos
python -c "from clawlite.gateway import server; print('ok')"
python -c "from clawlite.runtime.conversation_cron import list_cron_jobs; print('ok')"
```

---

### Estado atual (pós-sessão)

| Área | Status | Notas |
|---|---|---|
| Testes | ✅ 81/81 | Todos passando |
| CI pipeline | ✅ criado | `.github/workflows/ci.yml` |
| Smoke test | ✅ criado | `scripts/smoke_test.sh` |
| `/api/cron` | ✅ | GET/POST/DELETE |
| `/api/channels/status` | ✅ | |
| `/api/metrics` | ✅ | uptime, workers, tasks, logs, websockets |
| RUNBOOK | ✅ | 7 cenários cobertos |
| run_remote_provider() | ✅ | Corrigido na sessão anterior (commit `898a0e9`) |
| resilience.py | ✅ | criado na sessão anterior |
| secret_store.py | ✅ | criado na sessão anterior |
| backup/restore scripts | ✅ | criados na sessão anterior |

---

### Próximos passos (recomendados por prioridade)

**P0 — Alta prioridade**

1. **Integrar retry/reconnect por canal** — `clawlite/runtime/telegram_multiagent.py` e `whatsapp_bridge.py` não usam `resilience.retry_call`. Adicionar wrapping nas funções de envio de mensagem.

2. **Token rotation assistida** — `docs/PRODUCTION_DAY1.md` menciona rotação de tokens. Implementar `clawlite configure → Channels → [canal] → Rotate Token` com aviso quando token expira.

3. **Dashboard parity: painel Config avançado** — Falta endpoint de apply/restart no gateway (`POST /api/config/apply`) para o dashboard poder salvar e reiniciar sem CLI.

**P1 — Média prioridade**

4. **Validação E2E do multi-agente** — `tests/test_multiagent_recovery.py` existe mas é unitário. Criar teste de integração real com bot Telegram de teste.

5. **Hardening installer Termux** — `scripts/install.sh` funciona mas não valida `--only-binary` em todos os casos. Adicionar detecção de aarch64 com aviso claro.

6. **Dashboard parity: painel Debug/Update** — Endpoint `GET /api/debug/info` com versão, path, env, e `POST /api/update` para self-update via pip.

7. **`clawlite stats` command** — MEMORY.md menciona como prioritário. Integrar `learning.get_stats()` no CLI como `clawlite stats [--period week]`.

**P2 — Backlog**

8. **shell=True em multiagent.worker_loop** — Risco de segurança documentado. Escopo separado, requer redesign do worker subprocess.
9. **Busca semântica real** em `session_memory.py` — atualmente é keyword counting.
10. **MCP: remover dependência de npx** — templates filesystem/github usam npx; contradiz README "sem Node.js".

---

### Notas de risco

- `multiagent.DB_DIR`/`DB_PATH` são variáveis de módulo. Qualquer novo teste que use o gateway **deve** usar `_patch_db()` para isolar. Padrão documentado em `test_multiagent_channels.py`.
- `clawlite/configure_menu.py` tem changes não commitadas. Verificar antes de próxima sessão.
- O CI só roda pytest com dependências básicas; `questionary` e `rich` são opcionais no CI.

---

*Gerado por: Claude Code (claude-sonnet-4-6)*
*Data: 2026-02-27 21:35 UTC*
