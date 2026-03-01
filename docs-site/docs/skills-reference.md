# Skills marketplace (install / publish / search)

## Estado atual do catálogo

- Snapshot de 28/02/2026: **79 skills registradas no runtime**
- Composição: **37 nativas** + **42 aliases de compatibilidade OpenClaw**
- Documentação de compatibilidade: [`docs/SKILLS_OPENCLAW_COMPAT.md`](https://github.com/eobarretooo/ClawLite/blob/main/docs/SKILLS_OPENCLAW_COMPAT.md)

## Buscar skills com filtros

```bash
# listar tudo
clawlite skill search

# buscar por termo
clawlite skill search github

# filtrar por categoria e status
clawlite skill search --category devtools --status stable
```

### Filtros suportados

- `query` (termo livre em slug/descrição/tags)
- `--category <categoria>`
- `--status <stable|beta|experimental|deprecated>`

## Instalar skills

```bash
clawlite skill install <slug>
```

Após instalar, o CLI já mostra:

- versão instalada
- caminho local
- próximo passo (`clawlite run "use <slug> para ..."`)

## Publicar skills com metadados completos

```bash
clawlite skill publish skills/<slug> \
  --version 1.0.0 \
  --description "Resumo curto" \
  --category devtools \
  --status stable \
  --tag github \
  --tag automation \
  --install-hint "clawlite skill install <slug>"
```

Metadados publicados no manifesto:

- `slug`
- `version`
- `description`
- `category`
- `status`
- `tags`
- `install_hint`
- `download_url`
- `checksum_sha256`

## Categorias sugeridas

- `devtools`
- `communication`
- `productivity`
- `infra`
- `data`
- `media`
- `general`

## Exemplo de busca orientada por status

```bash
# skills prontas para produção
clawlite skill search --status stable

# skills em testes
clawlite skill search --status beta
```
