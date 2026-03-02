---
title: Troubleshooting
---

## `clawlite start` falha ao subir gateway

Checklist:

```bash
python -m clawlite.cli --help
clawlite start --host 127.0.0.1 --port 8787
```

- Confirme se a porta está livre.
- Confirme variáveis de provider (modelo/chave).

## Provider retorna erro de quota/rate limit

- Verifique saldo/quota da conta.
- Troque modelo temporariamente.
- Configure fallback local apenas se fizer sentido no seu ambiente.

## Skill indisponível em `clawlite skills list --all`

A saída já mostra os requisitos faltantes (`missing`).

Exemplos comuns:
- binário ausente (`gh`, `tmux`, `python`)
- variável de ambiente obrigatória ausente

## Cron não dispara

```bash
clawlite cron list --session-id <session>
```

- Valide expressão (`every N`, `at ISO`, ou cron padrão).
- Confirme que a sessão usada no `cron add` está correta.

## Workspace sem identidade

Se `IDENTITY.md`/`SOUL.md`/`USER.md` não existirem:

```bash
clawlite onboard --overwrite
```
