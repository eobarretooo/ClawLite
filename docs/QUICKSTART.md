# Quickstart

## 1. Install

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

Or locally:

```bash
pip install -e .
```

## 2. Guided configure wizard

```bash
clawlite configure --flow quickstart
```

QuickStart validates the provider live, configures a local token-protected gateway, offers Telegram, and generates the base templates in the workspace (when missing):
- `IDENTITY.md`
- `SOUL.md`
- `USER.md`
- `AGENTS.md`
- `TOOLS.md`
- `HEARTBEAT.md`
- `BOOTSTRAP.md`
- `memory/MEMORY.md`

For Discord, Email, WhatsApp, Slack, and manual Telegram variants, use the channel reference in `docs/channels.md` after QuickStart finishes.

If you want to skip the wizard and configure a provider manually, use `docs/providers.md`.

Use the manual section-by-section flow when you need custom gateway or channel settings:

```bash
clawlite configure --flow advanced
```

## 3. Start gateway

```bash
clawlite start --host 127.0.0.1 --port 8787
```

Equivalent alias:

```bash
clawlite gateway --host 127.0.0.1 --port 8787
```

## 4. Send the first message

```bash
clawlite run "hello, introduce yourself and confirm the active model"
```

## 5. Optional HTTP smoke test for `/v1/chat`

```bash
python - <<'PY'
import json
import pathlib
import urllib.request

cfg = json.loads((pathlib.Path.home() / ".clawlite" / "config.json").read_text())
token = cfg["gateway"]["auth"]["token"]
req = urllib.request.Request(
    "http://127.0.0.1:8787/v1/chat",
    data=b'{"session_id":"cli:quickstart","text":"who are you?"}',
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    },
)
print(urllib.request.urlopen(req).read().decode())
PY
```

QuickStart sets `gateway.auth.mode=required`, so authenticated HTTP requests must send `Authorization: Bearer <token>` or use `?token=<token>`.
