# Operação e Release

Guia objetivo para operação diária do runtime atual.

## Smoke local

```bash
clawlite --help
clawlite run "ok"
curl -sS http://127.0.0.1:8787/health | python -m json.tool
```

## Testes

```bash
pytest -q
```

## Cron operacional

```bash
clawlite cron add --session-id cli:ops --expression "every 300" --prompt "status rapido"
clawlite cron list --session-id cli:ops
```

## Release checklist mínimo

- `pytest -q` passando
- CLI principal validada
- API `/health` e `/v1/chat` validada
- Documentação atualizada com os comandos reais
