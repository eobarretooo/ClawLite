# Session Memory (persistência de contexto)

O ClawLite implementa memória persistente em workspace local para manter contexto entre sessões.

## Estrutura

No workspace (`~/.clawlite/workspace` por padrão):

- `AGENTS.md`
- `SOUL.md`
- `USER.md`
- `IDENTITY.md`
- `MEMORY.md`
- `memory/YYYY-MM-DD.md` (logs diários)

## Comportamento

- No início do fluxo de execução, o runtime carrega contexto-base desses arquivos.
- Antes de responder tasks, roda busca semântica local para trazer snippets relevantes.
- Durante execução, registra eventos em `memory/YYYY-MM-DD.md`.
- Ao final de sessão, pode salvar resumo em `MEMORY.md` + diário.
- Compactação automática reduz logs antigos, preservando resumo em `MEMORY.md`.

## Comandos CLI

```bash
clawlite memory init
clawlite memory context
clawlite memory semantic-search "meus projetos"
clawlite memory save-session "Resumo da sessão"
clawlite memory compact --max-daily-files 21
```

## Observações

- Busca semântica atual é local (token matching + ranking simples).
- Funciona offline e é compatível com Linux/Termux.
