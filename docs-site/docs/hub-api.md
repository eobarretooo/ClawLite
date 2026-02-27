# Hub / Marketplace API

Este é o scaffold inicial do hub de skills do ClawLite.

## Manifest local

Arquivo padrão:

```text
hub/marketplace/manifest.local.json
```

Formato:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-02-27T00:00:00Z",
  "allow_hosts": ["raw.githubusercontent.com", "github.com", "objects.githubusercontent.com"],
  "skills": [
    {
      "slug": "find-skills",
      "version": "1.0.0",
      "description": "Descoberta de skills",
      "category": "productivity",
      "status": "stable",
      "tags": ["discovery", "marketplace"],
      "install_hint": "clawlite skill install find-skills",
      "download_url": "https://.../packages/find-skills-1.0.0.zip",
      "checksum_sha256": "<sha256>",
      "package_file": "packages/find-skills-1.0.0.zip"
    }
  ]
}
```

## Contrato (v1)

- `GET /api/hub/manifest`
- `GET /api/hub/skills/{slug}`
- `POST /api/hub/publish`

## CLI de Marketplace

```bash
clawlite skill search [query] --category <categoria> --status <status>
clawlite skill install <slug>
clawlite skill update
clawlite skill publish skills/<slug> --version 1.0.0 --category devtools --status stable --tag automation
```

## Segurança da instalação

- Allowlist de hosts (bloqueia origem fora da lista)
- Validação de checksum SHA-256 do pacote
- Extração segura de zip (proteção contra path traversal)
