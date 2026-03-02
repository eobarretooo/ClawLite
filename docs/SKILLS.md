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
