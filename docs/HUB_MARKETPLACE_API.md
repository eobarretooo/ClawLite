# Hub / Marketplace API (Scaffold inicial)

Este documento define o contrato inicial do hub de skills do ClawLite.

## Manifesto local

Arquivo padrão: `hub/marketplace/manifest.local.json`

Estrutura:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-02-27T00:00:00Z",
  "allow_hosts": ["raw.githubusercontent.com", "github.com"],
  "skills": [
    {
      "slug": "nome-da-skill",
      "version": "1.0.0",
      "description": "Resumo curto",
      "download_url": "https://.../packages/nome-da-skill-1.0.0.zip",
      "checksum_sha256": "...",
      "package_file": "packages/nome-da-skill-1.0.0.zip"
    }
  ]
}
```

## Endpoints planejados

- `GET /api/hub/manifest`
  - Retorna o manifesto publicado do marketplace.

- `GET /api/hub/skills/{slug}`
  - Retorna metadados da skill por slug.

- `POST /api/hub/publish`
  - Publica pacote + metadados da skill (fluxo administrativo).

## CLI associada

- `clawlite skill publish`
  - Empacota skill local, calcula checksum SHA-256 e atualiza manifesto.

- `clawlite skill install`
  - Consome índice remoto, valida allowlist/checksum e instala skill.

- `clawlite skill update`
  - Atualiza skills instaladas comparando manifesto local com índice remoto.
