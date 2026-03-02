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
- `requires` (legado, lista CSV de binários)
- `requirements` (novo formato JSON com `bins`, `env`, `os`)
- `command` / `script` (metadado para execução)

Também é aceito `metadata` JSON com namespace `clawlite`/`nanobot`/`openclaw`, por exemplo:

```yaml
metadata: {"clawlite":{"requires":{"bins":["gh"],"env":["GITHUB_TOKEN"]},"os":["linux","darwin"]}}
```

## Política de duplicidade

Quando duas skills possuem o mesmo `name`, a resolução é determinística:

1. `workspace` vence `marketplace`
2. `marketplace` vence `builtin`
3. empate na mesma origem: menor caminho lexicográfico (`path`) vence

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
- `clawhub`

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

## Formato de resumo em runtime

`render_for_prompt()` usa contrato XML compatível com a tool de skills:

```xml
<available_skills>
<skill>
<name>github</name>
<description>Interact with GitHub using gh CLI for PRs, issues, runs and API queries.</description>
<location>/path/to/SKILL.md</location>
</skill>
</available_skills>
```
