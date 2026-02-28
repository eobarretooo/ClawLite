# Runbook de Incidentes — ClawLite

> Procedimentos rápidos para diagnóstico e recuperação em produção.
> Atualizar conforme novos incidentes forem documentados.

---

## Índice
- [1. Gateway down](#1-gateway-down)
- [2. Channel auth failure (Telegram/Discord/Slack)](#2-channel-auth-failure)
- [3. DB lock / SQLite busy](#3-db-lock--sqlite-busy)
- [4. Worker não responde](#4-worker-não-responde)
- [5. Sem resposta do LLM (provider timeout)](#5-sem-resposta-do-llm)
- [6. Rollback de versão](#6-rollback-de-versão)
- [7. Restaurar backup](#7-restaurar-backup)

---

## 1. Gateway down

**Sintomas:** `clawlite status` mostra `gateway: stopped ❌`. Requisições a `/health` falham.

**Diagnóstico:**
```bash
clawlite status
curl -sf http://127.0.0.1:8787/health || echo "gateway offline"
# Verificar se porta está ocupada por outro processo
ss -tlnp | grep 8787
```

**Ação:**
```bash
# Reiniciar gateway
clawlite start --host 0.0.0.0 --port 8787

# Se porta ocupada
fuser -k 8787/tcp  # Linux
# ou
kill $(lsof -ti:8787)  # macOS/Termux

# Em Termux: usar nohup para manter em background
nohup clawlite start --port 8787 > ~/.clawlite/logs/gateway.log 2>&1 &
```

**Validação:**
```bash
curl -sf http://127.0.0.1:8787/health
bash scripts/smoke_test.sh
```

---

## 2. Channel auth failure

**Sintomas:** Bot Telegram/Discord/Slack não responde. Logs mostram `401 Unauthorized` ou `403 Forbidden`.

**Diagnóstico:**
```bash
# Ver status de canais via API
TOKEN=$(python -c "from clawlite.gateway.server import _token; print(_token())")
curl -sf -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/channels/status

# Verificar config
cat ~/.clawlite/config.json | python -m json.tool | grep -A5 '"channels"'
```

**Ação (Telegram):**
```bash
# 1. Verificar token via BotFather
# 2. Atualizar config interativamente
clawlite configure
# Seção: Channels → Telegram → Token

# 3. Testar token diretamente
TOKEN="SEU_TOKEN"
curl -sf "https://api.telegram.org/bot${TOKEN}/getMe"
```

**Ação (geral):**
```bash
# Recarregar config sem restart (SIGHUP)
kill -HUP $(pgrep -f "clawlite start")
```

**Ação (Slack Socket Mode):**
```bash
# Slack exige os dois tokens:
# - Bot token: xoxb-...
# - App token: xapp-...
cat ~/.clawlite/config.json | python -m json.tool | grep -A10 '"slack"'
```
Se `channels.slack.app_token` estiver vazio, o canal não inicia.

---

## 3. DB lock / SQLite busy

**Sintomas:** Erros `database is locked` ou `SQLITE_BUSY` nos logs.

**Diagnóstico:**
```bash
ls -la ~/.clawlite/*.db
# Verificar se há WAL/SHM travados
ls ~/.clawlite/*.db-wal ~/.clawlite/*.db-shm 2>/dev/null
```

**Ação:**
```bash
# 1. Parar gateway e workers
pkill -f "clawlite start" || true

# 2. Forçar checkpoint do WAL (pode ser feito com o DB aberto)
python -c "
import sqlite3
for db in ['~/.clawlite/multiagent.db', '~/.clawlite/learning.db']:
    import os; path = os.path.expanduser(db)
    if os.path.exists(path):
        with sqlite3.connect(path) as c:
            c.execute('PRAGMA wal_checkpoint(FULL)')
        print(f'checkpoint ok: {path}')
"

# 3. Reiniciar
clawlite start
```

**Preventivo:** O gateway já usa `PRAGMA busy_timeout=3000` (3s). Se recorrente, verificar processos zumbis:
```bash
ps aux | grep clawlite
```

---

## 4. Worker não responde

**Sintomas:** `clawlite status` mostra worker com PID mas sem atividade. Mensagens não processadas.

**Diagnóstico:**
```bash
clawlite agents list
TOKEN=$(python -c "from clawlite.gateway.server import _token; print(_token())")
curl -sf -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/metrics
```

**Ação:**
```bash
# Ver PID do worker problemático
clawlite agents list

# Matar e aguardar auto-restart do gateway
kill <PID>
# O gateway detecta worker morto e reinicia automaticamente (recovery loop)

# Se não reiniciar, forçar
clawlite start --restart
```

---

## 5. Sem resposta do LLM

**Sintomas:** `run_task_with_meta` retorna timeout ou erro do provider. Fallback Ollama ativado inesperadamente.

**Diagnóstico:**
```bash
# Verificar conectividade
python -c "from clawlite.runtime.offline import check_connectivity; print(check_connectivity())"

# Ver métricas de erro
TOKEN=$(python -c "from clawlite.gateway.server import _token; print(_token())")
curl -sf -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8787/api/metrics | python -m json.tool

# Ver últimos erros nos logs
curl -sf -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8787/api/dashboard/logs?level=error&limit=20"
```

**Ação:**
```bash
# 1. Testar provider diretamente
clawlite run "responda apenas: ok"

# 2. Se Anthropic/OpenAI fora: usar fallback Ollama
clawlite configure
# Runtime → Offline → Ativar fallback automático

# 3. Verificar token/quota via config
clawlite configure
# Model → Verificar token configurado
```

---

## 6. Rollback de versão

**Sintomas:** Nova versão introduz regressão crítica.

**Ação:**
```bash
# 1. Identificar commit estável anterior
git log --oneline -10

# 2. Criar branch de hotfix no commit estável
git checkout -b hotfix/<descricao> <hash-estavel>

# 3. Reinstalar localmente
pip install -e .
bash scripts/smoke_test.sh

# 4. Nunca usar git reset --hard no main sem aprovação explícita do Renan
```

---

## 7. Restaurar backup

**Ação:**
```bash
# Listar backups disponíveis
ls -lh ~/.clawlite/backups/

# Restaurar
bash scripts/restore_clawlite.sh ~/.clawlite/backups/clawlite-backup-YYYYMMDD-HHMMSS.tar.gz

# Validar após restore
clawlite doctor
bash scripts/smoke_test.sh
```

---

## Alertas automáticos

> Configurar em `~/.clawlite/config.json` → `notifications.telegram_chat_id` para receber alertas de erro crítico via Telegram.

```bash
clawlite configure
# Seção: Notifications → Telegram Chat ID
```

---

*Última atualização: 2026-02-27 — Claude Code (co-engineer)*
