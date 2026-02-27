---
title: Troubleshooting
---

## Skills com erro de sintaxe (`IndentationError`)

Se houver falha ao importar skills como `aws`, `ssh` ou `supabase`, valide:

```bash
python -m compileall -q clawlite/skills
```

Corrija a indentação do bloco indicado e rode novamente.

## `agents`: worker não encontrado

Erro:
```text
❌ Falha no comando 'agents': worker <id> não encontrado
```

Solução:
```bash
clawlite agents register --channel telegram --chat-id 123 --label geral --cmd 'clawlite run "{text}"'
clawlite agents list
clawlite agents start <id>
```

## `cron`: intervalo inválido

Erro:
```text
❌ Falha no comando 'cron': interval_seconds deve ser maior que 0
```

Solução:
```bash
clawlite cron add --channel telegram --chat-id 123 --label geral --name heartbeat --text "ping" --every-seconds 60
```

## `skill`: falha de marketplace/publicação

Erros de `skill install/update/publish` costumam vir de manifesto ou URL inválida.

Checklist:
- revisar `--index-url`
- revisar `--allow-host`
- revisar `--manifest-path`
- habilitar `--allow-file-urls` apenas em ambiente local controlado

## `auth`: usuário não autenticado

Se `clawlite auth status` mostrar `não autenticado`, execute:

```bash
clawlite auth login openai
clawlite auth status
```

## `battery`: valor inesperado no throttle

Diagnóstico:
```bash
clawlite battery status
```

Ajuste:
```bash
clawlite battery set --enabled true --throttle-seconds 8
```

## Dashboard/Gateway: token inválido

Erros comuns:
- `401 Missing bearer token`
- `403 Invalid token`

Use o valor de `gateway.token` em `~/.clawlite/config.json` e envie:

```text
Authorization: Bearer <token>
```
