# Skills

O ClawLite carrega skills em Markdown (`SKILL.md`) de três origens:

1. Builtin do repositório: `clawlite/skills/*/SKILL.md`
2. Workspace do usuário: `~/.clawlite/workspace/skills/*/SKILL.md`
3. Marketplace local: `~/.clawlite/marketplace/skills/*/SKILL.md`

## Frontmatter suportado

- `name`
- `description`
- `always`
- `requires`
- `command`
- `script`

## CLI de inspeção

```bash
clawlite skills list
clawlite skills list --all
clawlite skills show cron
```

`--all` inclui skills indisponíveis e mostra requisitos ausentes.

## Execução real no agente

Skills com `command` ou `script` são executáveis via tool `run_skill` no runtime.

Fluxo:
1. Resolve skill por nome
2. Valida `requires`
3. Executa `command` ou `script`
4. Retorna saída padronizada para o agente

➡️ Próxima página: [Gateway API](/gateway-api)
