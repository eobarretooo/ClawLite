# 🦊 ClawLite

<div align="center">

**A local-first Python autonomous assistant with gateway control plane, persistent memory, scheduled autonomy, and chat-channel integrations.**

[![CI](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-gateway-009688?logo=fastapi&logoColor=white)
![WebSocket](https://img.shields.io/badge/WebSocket-live%20control-6C63FF)
![License](https://img.shields.io/badge/license-MIT-2ea44f)

</div>

ClawLite is for developers who want an assistant that runs **on their own machine first**, speaks through a **real gateway**, remembers context over time, and can grow into a **24/7 autonomous runtime**.

It already ships with:

- 🖥️ a FastAPI gateway with HTTP + WebSocket control surfaces
- 🧠 persistent memory, workspace bootstrap files, and heartbeat/bootstrap cycles
- 🔁 supervised runtime loops for autonomy, channels, cron, subagents, and self-evolution
- 🧰 built-in tools for files, exec, web, MCP, sessions, cron, memory, skills, and patching
- 💬 channel integrations for Telegram, Discord, Email, WhatsApp, and Slack-style outbound delivery

> [!IMPORTANT]
> `main` is the living branch and may be ahead of the latest tag.
> Current focus: making ClawLite **robust and operationally autonomous** using `ref/openclaw` and `ref/nanobot` as behavior references, adapted to ClawLite's Python architecture.

## ✨ What ClawLite feels like today

### 🚀 Gateway-first control plane

- local dashboard at `http://127.0.0.1:8787`
- `GET /api/status`, `GET /api/diagnostics`, `POST /api/message`, `GET /api/token`, `WS /ws`
- packaged dashboard with:
  - live chat
  - sessions view
  - automation view
  - tool catalog
  - workspace / bootstrap / memory / skills health
  - autorefresh and manual heartbeat trigger

### 🧠 Memory + workspace

- JSONL session history under `~/.clawlite/state/sessions`
- persistent memory under `~/.clawlite/memory`
- workspace runtime files like:
  - `IDENTITY.md`
  - `SOUL.md`
  - `USER.md`
  - `AGENTS.md`
  - `TOOLS.md`
  - `HEARTBEAT.md`
  - `BOOTSTRAP.md`
  - `memory/MEMORY.md`

### 🔁 Always-on runtime pieces

- heartbeat loop
- cron engine
- autonomy wake coordinator
- channel dispatcher + recovery supervisor
- subagent maintenance
- self-evolution runner
- runtime supervisor with recovery telemetry

## 🏁 Quickstart

### 1. Install

```bash
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite

python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

Windows PowerShell:

```powershell
./.venv/Scripts/Activate.ps1
```

### 2. Run the setup wizard

```bash
clawlite configure --flow quickstart
```

Quickstart currently:

- ✅ validates the provider live
- 🔒 keeps the gateway local on `127.0.0.1:8787`
- 🪪 enables token auth on the gateway
- 📦 bootstraps the workspace files
- 📲 offers Telegram setup

Want the manual path?

```bash
clawlite configure --flow advanced
```

### 3. Start the gateway

```bash
clawlite gateway
```

Then open:

```text
http://127.0.0.1:8787
```

The onboarding summary also prints a tokenized dashboard URL like:

```text
http://127.0.0.1:8787#token=...
```

The dashboard consumes that fragment once, stores the token locally for the browser session, and removes it from the address bar.

You can also print or reopen the handoff later with:

```bash
clawlite dashboard --no-open
```

That command also returns the current bootstrap state plus backup, web-search, and security guidance for the workspace.

If onboarding is still pending, the dashboard also exposes a `Hatch agent` action that sends:

```text
Wake up, my friend!
```

through the dedicated `hatch:operator` session so the first bootstrap turn can complete cleanly.

If you prefer to hatch from the terminal, you can also run:

```bash
clawlite hatch
```

Telegram operator controls are also available from the terminal:

```bash
clawlite telegram status
clawlite telegram refresh
clawlite telegram offset-commit 144
clawlite telegram offset-sync 145
```

`clawlite telegram status` now includes offset/pairing/webhook hints so operators can see the safest next action faster.

### 4. Talk to the agent

```bash
clawlite run "hello, introduce yourself and confirm the active model"
```

## 🧪 Useful examples

### CLI status + diagnostics

```bash
clawlite status
clawlite diagnostics --gateway-url http://127.0.0.1:8787
clawlite validate config
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

### HTTP chat request

```bash
python - <<'PY'
import json
import pathlib
import urllib.request

cfg = json.loads((pathlib.Path.home() / ".clawlite" / "config.json").read_text())
token = cfg["gateway"]["auth"]["token"]

req = urllib.request.Request(
    "http://127.0.0.1:8787/api/message",
    data=b'{"session_id":"readme:http","text":"summarize the runtime status"}',
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    },
)

print(urllib.request.urlopen(req).read().decode())
PY
```

### Inspect the control plane

```bash
curl -sS http://127.0.0.1:8787/api/status | python -m json.tool
curl -sS http://127.0.0.1:8787/api/dashboard/state | python -m json.tool
curl -sS http://127.0.0.1:8787/api/diagnostics | python -m json.tool
```

### Trigger a heartbeat cycle manually

```bash
curl -X POST http://127.0.0.1:8787/v1/control/heartbeat/trigger \
  -H "Authorization: Bearer YOUR_GATEWAY_TOKEN"
```

## 🧭 Current project state

| Area | Status | Notes |
| --- | --- | --- |
| Gateway | ✅ Strong | Compatibility endpoints, diagnostics, WebSocket, packaged dashboard |
| Dashboard | ✅ Active | Sessions, automation, knowledge, tools, live chat, event feed |
| Providers | ✅ Strong | Hosted providers + Ollama/vLLM + Codex OAuth |
| Heartbeat | ✅ Good | Loop, persisted state, manual trigger, parity work ongoing |
| Bootstrap | ✅ Good | Workspace bootstrap lifecycle present, more parity work ongoing |
| Telegram | ⚠️ In progress | One of the strongest channels, but durability parity still ongoing |
| Self-evolution | ⚠️ Experimental | Present and observable; still being hardened |
| 24/7 autonomy | 🚧 Active mission | Recovery, failover, memory quality, and ops polish are current focus |

For the live engineering snapshot:

- `docs/STATUS.md`
- `docs/AUTONOMY_PLAN.md`
- `CHANGELOG.md`

## 🧩 Providers available today

### OpenAI-compatible

- OpenAI
- Gemini
- Groq
- DeepSeek
- OpenRouter
- Together
- Hugging Face
- xAI
- Mistral
- Moonshot
- Qianfan
- Z.AI
- NVIDIA
- BytePlus
- Doubao
- Volcengine
- KiloCode
- `custom/<model>` backends

### Anthropic-compatible

- Anthropic
- MiniMax
- Xiaomi
- Kimi Coding

### Local runtimes

- Ollama
- vLLM

### Special case

- OpenAI Codex OAuth

Default model today:

```text
gemini/gemini-2.5-flash
```

More details: `docs/providers.md`

## 💬 Channels available today

| Channel | Inbound | Outbound | Status | Notes |
| --- | --- | --- | --- | --- |
| Telegram | Yes | Yes | Most complete | Polling + webhook, pairing, reactions, topics, media support |
| Discord | Yes | Yes | Usable | Gateway websocket inbound, REST outbound |
| Email | Yes | Yes | Usable | IMAP inbound + SMTP outbound |
| WhatsApp | Yes | Yes | Usable | Webhook inbound + outbound bridge |
| Slack | No | Yes | Send-only | Outbound supported, inbound loop not implemented |
| Signal / Google Chat / Matrix / IRC / iMessage / DingTalk / Feishu / Mochat / QQ | No | No | Placeholder | Registered surfaces, not production-ready yet |

More details: `docs/channels.md`

## 🖥️ Dashboard at a glance

The local dashboard is no longer a static landing page. It is a real operator shell.

Current tabs:

- 🧭 `Overview` — control plane, event feed, heartbeat trigger, diagnostics snapshot, and one-click hatch action when bootstrap is pending
- 🧭 `Overview` — control plane, next-step cards, event feed, heartbeat trigger, diagnostics snapshot, and one-click hatch action when bootstrap is pending
- 💬 `Chat` — live WS/HTTP chat and raw WebSocket frame preview
- 🗂️ `Sessions` — recent sessions with one-click handoff into chat
- 🤖 `Automation` — cron, inbound journal replay, dead-letter replay, operator channel recovery, Telegram transport refresh, pairing approval/rejection/revocation, offset advance, provider recovery/suppression, and operator-triggered supervisor recovery
- 🧠 `Knowledge` — workspace runtime files, bootstrap status, skills, memory monitor
- 🧰 `Tools` — tool catalog, groups, aliases

## 🧠 Workspace and memory

ClawLite uses a workspace to shape identity, behavior, and long-term context.

Default workspace root:

```text
~/.clawlite/workspace
```

State + memory roots:

```text
~/.clawlite/state
~/.clawlite/memory
```

Useful docs:

- `docs/workspace.md`
- `docs/memory.md`
- `docs/API.md`

## 🛠️ Development

### Local loop

```bash
pip install -e .
python -m pytest tests -q --tb=short
python -m ruff check --select=E,F,W .
```

### Focused validation

```bash
python -m pytest tests/gateway/test_server.py -q --tb=short
python -m pytest tests/runtime/test_autonomy_actions.py -q --tb=short
bash scripts/smoke_test.sh
```

### Release preflight

```bash
bash scripts/release_preflight.sh \
  --config ~/.clawlite/config.json \
  --gateway-url http://127.0.0.1:8787
```

## 📚 Docs map

- `docs/README.md` — docs index
- `docs/STATUS.md` — current state and active milestone
- `docs/AUTONOMY_PLAN.md` — phased robustness/autonomy plan
- `docs/QUICKSTART.md` — setup walkthrough
- `docs/API.md` — gateway HTTP + WS surfaces
- `docs/OPERATIONS.md` — operational commands and diagnostics
- `docs/RUNBOOK.md` — operator validation and incident flow
- `docs/RELEASING.md` — tag/release workflow
- `docs/providers.md` — provider catalog and auth
- `docs/channels.md` — channel behavior and caveats
- `docs/tools.md` — tool catalog and aliases
- `docs/workspace.md` — workspace runtime files and lifecycle
- `docs/memory.md` — memory backends, privacy, quality, snapshots

## 🔭 Project direction

ClawLite is actively being hardened toward a more durable, autonomous runtime.

Current reference repos used for adaptation work:

- `ref/openclaw` — dashboard, onboarding, bootstrap, heartbeat, gateway behavior
- `ref/nanobot` — reliability patterns, lightweight runtime ideas, channel/provider hardening

The goal is **behavior parity where it matters**, not codebase cloning.

## 📄 License

MIT — see `LICENSE`.
