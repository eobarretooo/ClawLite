# Automação de Sync Semanal (OpenClaw → ClawLite)

Este documento descreve como gerar e manter o `SYNC_REPORT.md` automaticamente toda semana.

## 1) Script de geração

Arquivo: `scripts/openclaw_sync.py`

Função: gerar snapshot semanal com:
- HEAD local do ClawLite
- HEAD remoto do upstream OpenClaw
- commits locais recentes (janela configurável)
- estado do working tree

### Execução manual

```bash
python3 scripts/openclaw_sync.py
```

### Preview sem gravar

```bash
python3 scripts/openclaw_sync.py --dry-run
```

### Parâmetros úteis

```bash
python3 scripts/openclaw_sync.py \
  --upstream-url https://github.com/openclaw/openclaw.git \
  --days 7 \
  --output SYNC_REPORT.md
```

## 2) Automação via GitHub Actions (semanal)

Workflow: `.github/workflows/sync-report-weekly.yml`

- dispara automaticamente toda segunda-feira (`cron`)
- também pode ser executado manualmente (`workflow_dispatch`)
- gera/atualiza `SYNC_REPORT.md`
- se houver mudança, faz commit automático na `main`

## 3) Opcional: cron local (máquina própria)

Se quiser rodar localmente além do GitHub Actions:

```cron
0 8 * * 1 cd /root/projetos/ClawLite && /usr/bin/python3 scripts/openclaw_sync.py && /usr/bin/git add SYNC_REPORT.md && /usr/bin/git commit -m "chore(sync): atualizar SYNC_REPORT semanal" || true
```

> Ajuste caminhos de `python3`/`git` conforme seu ambiente.

## 4) Checklist rápido

- [ ] `scripts/openclaw_sync.py` executa sem erro
- [ ] `SYNC_REPORT.md` atualizado corretamente
- [ ] workflow semanal ativo no GitHub
- [ ] permissões de commit do workflow habilitadas

## 5) Nota de execução manual

- 2026-02-28 (UTC): ciclo de sync executado com sucesso via:
  - `python3 scripts/openclaw_sync.py --dry-run`
  - `python3 scripts/openclaw_sync.py`
- Resultado: `SYNC_REPORT.md` regenerado no estado atual da branch `main`.
