# Gateway API

## Subir gateway

```bash
clawlite gateway --host 0.0.0.0 --port 8787
```

## Endpoints

- `GET /health`
- `GET /dashboard`
- `GET /api/status` (Bearer token)
- `GET /api/dashboard/bootstrap` (Bearer token)
- `GET /api/dashboard/skills` (Bearer token)
- `POST /api/dashboard/skills/install|enable|disable|remove` (Bearer token)
- `GET /api/dashboard/telemetry` (Bearer token)
- `GET /api/dashboard/logs` (Bearer token)
- `GET /api/hub/manifest`
- `GET /api/hub/skills/{slug}`
- `POST /api/hub/publish` (Bearer token)
- `WS /ws?token=<token>`
- `WS /ws/chat?token=<token>`
- `WS /ws/logs?token=<token>&level=&event=&q=`

## Auth

Use token do gateway no header:

```text
Authorization: Bearer <token>
```
