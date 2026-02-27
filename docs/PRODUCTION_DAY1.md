# Produção v1 — Dia 1 (P0)

## Entregas iniciais

### 1) Resiliência de canais (base)
- Módulo `clawlite/runtime/resilience.py`
  - `retry_call(...)` com backoff exponencial + jitter
  - `RateLimiter` token-bucket simples

### 2) Secrets management (base)
- Módulo `clawlite/runtime/secrets.py`
  - load de `.env`
  - load de vault local JSON via `CLAWLITE_VAULT_FILE`
  - bootstrap automático no `clawlite/cli.py`

### 3) Backup / Restore automático
- `scripts/backup_clawlite.sh`
- `scripts/restore_clawlite.sh`

Cobre backup de:
- `~/.clawlite/config.json`
- `~/.clawlite/multiagent.db`
- `~/.clawlite/learning.db`
- `~/.clawlite/workspace/`

## Uso rápido

```bash
scripts/backup_clawlite.sh
scripts/restore_clawlite.sh ~/.clawlite/backups/clawlite-backup-YYYYMMDD-HHMMSS.tar.gz
```

## Próximo (Dia 2)
- Aplicar retry/rate-limit/reconnect por canal no dispatcher real
- iniciar rotação assistida de tokens por canal
