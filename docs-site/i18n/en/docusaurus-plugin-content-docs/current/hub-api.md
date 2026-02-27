# Hub / Marketplace API

Initial scaffold for the ClawLite skills hub.

## Local manifest

Default file:

```text
hub/marketplace/manifest.local.json
```

Manifest shape:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-02-27T00:00:00Z",
  "allow_hosts": ["raw.githubusercontent.com", "github.com", "objects.githubusercontent.com"],
  "skills": [
    {
      "slug": "find-skills",
      "version": "1.0.0",
      "description": "Skill discovery",
      "download_url": "https://.../packages/find-skills-1.0.0.zip",
      "checksum_sha256": "<sha256>",
      "package_file": "packages/find-skills-1.0.0.zip"
    }
  ]
}
```

## Contract (v1)

- `GET /api/hub/manifest`
- `GET /api/hub/skills/{slug}`
- `POST /api/hub/publish`

## Marketplace CLI

```bash
clawlite skill install <slug>
clawlite skill update
clawlite skill publish skills/<slug> --version 1.0.0
```

## Secure install policy

- Host allowlist
- SHA-256 checksum verification
- Safe zip extraction (path traversal protection)
