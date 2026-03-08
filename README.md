# ClawLite

ClawLite is a Python autonomous assistant with a local gateway, pluggable LLM providers, persistent memory, workspace bootstrap files, scheduled jobs, and messaging channels.

It is built for developers who want to get a bot running locally first, then wire it into Telegram, Discord, Email, WhatsApp, or Slack.

## Why ClawLite

- Local-first runtime with CLI, HTTP, and WebSocket entry points.
- Provider routing across hosted APIs, local Ollama/vLLM, OpenAI Codex OAuth, and custom OpenAI-compatible backends.
- Persistent memory with JSONL history, SQLite or pgvector indexing, snapshots, branches, privacy rules, and working-memory state.
- Built-in tools for exec, files, web, MCP, cron, messaging, sessions, skills, and memory operations.
- Channel adapters for Telegram, Discord, Email, WhatsApp, and Slack.
- Workspace bootstrap files that shape identity, user context, operating style, heartbeat behavior, and long-term notes.

## 5-minute Quickstart

### 1) Install

```bash
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

On Windows PowerShell, activate the virtualenv with `./.venv/Scripts/Activate.ps1`.

### 2) Run the guided setup

```bash
clawlite configure --flow quickstart
```

Quickstart does four things for you:

- Validates the selected provider live.
- Keeps the gateway local on `127.0.0.1:8787`.
- Enables token auth on the gateway.
- Offers Telegram setup and bootstraps the workspace files.

### 3) Start the gateway

```bash
clawlite gateway
```

### 4) Send the first message

```bash
clawlite run "hello, introduce yourself and confirm the active model"
```

Optional HTTP smoke test against the running gateway:

```bash
python - <<'PY'
import json
import pathlib
import urllib.request

cfg = json.loads((pathlib.Path.home() / ".clawlite" / "config.json").read_text())
token = cfg["gateway"]["auth"]["token"]
req = urllib.request.Request(
    "http://127.0.0.1:8787/v1/chat",
    data=b'{"session_id":"readme:quickstart","text":"who are you?"}',
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    },
)
print(urllib.request.urlopen(req).read().decode())
PY
```

## Channels Available Today

| Channel | Inbound | Outbound | Status | Notes |
| --- | --- | --- | --- | --- |
| Telegram | Yes | Yes | Most complete | Polling and webhook, pairing flows, reactions, topics, typing keepalive, voice/audio transcription |
| Discord | Yes | Yes | Usable | Gateway websocket inbound, REST outbound, attachments arrive as text placeholders |
| Email | Yes | Yes | Usable | IMAP receive plus SMTP reply/send |
| WhatsApp | Yes | Yes | Usable | Inbound webhook plus outbound bridge `/send` |
| Slack | No | Yes | Send-only | Outbound `chat.postMessage`; no inbound event loop yet |
| Signal, Google Chat, Matrix, IRC, iMessage, DingTalk, Feishu, Mochat, QQ | No | No | Placeholders | Registered channel names, but passive stubs only |

See `docs/channels.md` for real config examples and channel-specific caveats.

## Providers Available Today

ClawLite currently supports:

- Hosted OpenAI-compatible providers: OpenAI, Gemini, Groq, DeepSeek, OpenRouter, Together, Hugging Face, xAI, Mistral, Moonshot, Qianfan, Z.AI, NVIDIA, BytePlus, Doubao, Volcengine, KiloCode.
- Hosted Anthropic-compatible providers: Anthropic, MiniMax, Xiaomi, Kimi Coding.
- Local runtimes: Ollama and vLLM.
- Special cases: OpenAI Codex OAuth and `custom/<model>` providers.

The default model is `gemini/gemini-2.5-flash`.

See `docs/providers.md` for auth resolution, aliases, base URLs, and failover notes.

## Workspace and Memory

Quickstart bootstraps these workspace files under `~/.clawlite/workspace` by default:

- `IDENTITY.md`
- `SOUL.md`
- `USER.md`
- `AGENTS.md`
- `TOOLS.md`
- `HEARTBEAT.md`
- `BOOTSTRAP.md`
- `memory/MEMORY.md`

ClawLite also keeps session state under `~/.clawlite/state` and structured memory data under `~/.clawlite/memory`.

See `docs/workspace.md` and `docs/memory.md` for the current file layout and lifecycle.

## Useful CLI Commands

```bash
clawlite status
clawlite validate config
clawlite validate preflight --gateway-url http://127.0.0.1:8787
clawlite diagnostics --gateway-url http://127.0.0.1:8787
clawlite provider use openai --model openai/gpt-4o-mini
clawlite skills list
clawlite memory doctor --repair
```

The full command reference lives in `docs/cli.md`.

## Documentation

- `docs/cli.md` - every CLI command with examples
- `docs/channels.md` - Telegram, Discord, Email, WhatsApp, Slack, and channel runtime behavior
- `docs/providers.md` - supported providers, auth, aliases, local runtimes, and failover notes
- `docs/tools.md` - built-in tool catalog, aliases, and config
- `docs/workspace.md` - workspace bootstrap, runtime-critical files, and bootstrap lifecycle
- `docs/memory.md` - memory config, backends, files, privacy, quality, and snapshots
- `docs/QUICKSTART.md` - quickstart walkthrough
- `docs/API.md` - gateway HTTP and WebSocket surfaces
- `docs/SKILLS.md` - skill discovery and lifecycle
- `docs/ARCHITECTURE.md` - runtime architecture
- `docs/OPERATIONS.md` - diagnostics and operational runbooks

## Development

```bash
pip install -e .
python -m pytest tests -q --tb=short
python -m ruff check --select=E,F,W .
```

## License

MIT. See `LICENSE`.
