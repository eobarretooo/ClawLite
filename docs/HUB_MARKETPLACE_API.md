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
      "category": "devtools",
      "status": "stable",
      "tags": ["github", "automation"],
      "install_hint": "clawlite skill install nome-da-skill",
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

- `clawlite skill search [query] [--category ...] [--status ...]`
  - Busca catálogo remoto por termo, categoria e status, incluindo estado de instalação local.

- `clawlite skill update`
  - Atualiza skills instaladas comparando manifesto local com índice remoto.

- `clawlite skill auto-update --dry-run`
  - Simula atualizações com saída por skill (`updated`/`skipped`/`blocked`) sem alterar arquivos.

- `clawlite skill auto-update --apply [--strict]`
  - Aplica atualizações com política de confiança (allowlist + checksum).
  - `--strict` bloqueia updates sem checksum válido no índice remoto.
  - Em falha, rollback automático mantém a versão anterior ativa.

- `clawlite skill auto-update --apply --schedule-seconds 3600`
  - Agenda execução periódica no runtime reutilizando `conversation_cron` (job `system/skills/auto-update`).
