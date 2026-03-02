# Skills

ClawLite usa skills em markdown (`SKILL.md`) com discovery automático.

## Fontes carregadas

1. Builtin (repo): `clawlite/skills/*/SKILL.md`
2. Workspace do usuário: `~/.clawlite/workspace/skills/*/SKILL.md`
3. Marketplace local: `~/.clawlite/marketplace/skills/*/SKILL.md`

## Campos suportados no frontmatter

- `name`
- `description`
- `always`
- `requires`
- `command` / `script` (metadado para execução)

## Builtins atuais

- `cron`
- `memory`
- `github`
- `summarize`
- `skill-creator`
- `web-search`
- `weather`
- `tmux`
- `hub`

## CLI de inspeção

```bash
clawlite skills list
clawlite skills list --all
clawlite skills show cron
```

`skills list --all` inclui skills indisponíveis no ambiente atual e mostra os requisitos faltantes.

## Execução real de skill (tool)

O runtime expõe a tool `run_skill`.

Campos principais:
- `name` (obrigatório)
- `input` ou `args`
- `timeout`
- `query` (para `web-search`)
- `location` (para `weather`)

Fluxo:
1. resolve skill por nome
2. valida disponibilidade (`bins/env/os`)
3. executa `command` ou `script` mapeado
