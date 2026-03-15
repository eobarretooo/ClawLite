<div align="center">

<img src="docs/demo.gif" alt="ClawLite demo" width="720" />

# 🦊 ClawLite

**A local-first Python autonomous agent — persistent memory, 20+ LLM providers,<br>real chat channels, and a 24/7 self-healing runtime. No cloud required.**

[![CI](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LiteLLM](https://img.shields.io/badge/LiteLLM-20%2B%20providers-blueviolet)](https://litellm.ai)
[![FastAPI](https://img.shields.io/badge/FastAPI-gateway-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)

[Quickstart](#-quickstart) · [Features](#-features) · [Channels](#-channels) · [Providers](#-providers) · [Docs](#-docs-map) · [Contributing](#-contributing)

⭐ **Star this repo if you find it useful** — it helps others discover the project.

</div>

---

## ⚡ Why ClawLite?

- **Truly local-first** — runs entirely on your machine; no vendor lock-in, no cloud accounts required
- **Production channels out of the box** — Telegram, Discord (slash commands, voice, polls), Email, WhatsApp, Slack
- **Persistent, searchable memory** — hybrid BM25 + vector search, temporal decay, consolidation loop
- **Self-healing runtime** — heartbeat supervisor, dead-letter replay, automatic provider failover
- **Batteries included** — 24+ skills, 21+ tools, streaming responses, operator dashboard

---

## 🏁 Quickstart

```bash
# 1. Clone and install
git clone https://github.com/eobarretooo/ClawLite.git && cd ClawLite
pip install -e .

# 2. Configure (interactive wizard — sets provider, gateway, optional Telegram)
clawlite configure --flow quickstart

# 3. Start the gateway
clawlite gateway
```

Open **http://127.0.0.1:8787** → live dashboard with chat, automation, memory, and tools.

```bash
# Or talk to the agent straight from the terminal
clawlite run "hello — what can you do?"
```

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🧠 Memory
- Hybrid BM25 + vector similarity search
- SQLite (local) or pgvector (Postgres)
- FTS5 full-text indexing
- Temporal decay + salience scoring
- Consolidation loop (episodic → knowledge)
- Snapshot / rollback controls

</td>
<td width="50%">

### 🔁 Always-On Runtime
- Heartbeat supervisor with recovery telemetry
- Cron engine (persistent, replay-safe)
- Autonomy wake coordinator
- Dead-letter queue + inbound journal replay
- Subagent maintenance loop
- Self-evolution runner

</td>
</tr>
<tr>
<td>

### 🧰 Tools (21+)
`files` · `exec` · `spawn` · `process` · `web` · `browser` (Playwright)
`pdf` · `tts` · `mcp` · `sessions` · `cron` · `memory` · `skills`
`message` · `agents` · `discord_admin` · `apply_patch` · `spawn`

</td>
<td>

### 🎯 Skills (24+)
`web-search` · `cron` · `memory` · `coding-agent` · `summarize`
`github-issues` · `notion` · `obsidian` · `spotify` · `docker`
`jira` · `linear` · `trello` · `1password` · `apple-notes`
`weather` · `tmux` · `model-usage` · `session-logs` · `skill-creator`

</td>
</tr>
<tr>
<td>

### 🌊 Streaming
- `ProviderChunk` dataclass (delta + accumulated + done)
- `engine.stream_run()` async generator
- `send_streaming()` on Discord and Telegram
- Edit-in-place draft updates as the agent types

</td>
<td>

### 🖥️ Operator Dashboard
- Live chat + WebSocket frame preview
- Sessions view with one-click handoff
- Automation: cron, channel controls, recovery
- Knowledge: workspace files, skills, memory health
- Tools catalog + group/alias browser

</td>
</tr>
</table>

---

## 💬 Channels

| Channel | Inbound | Outbound | Status | Highlights |
|---------|---------|---------|--------|------------|
| **Telegram** | ✅ | ✅ | ✅ Complete | Polling + webhook, reactions, topics, reply keyboards, streaming |
| **Discord** | ✅ | ✅ | ✅ Complete | Gateway WS, slash commands, buttons, voice messages, webhooks, polls, streaming |
| **Email** | ✅ | ✅ | 🟡 Usable | IMAP inbound + SMTP outbound |
| **WhatsApp** | ✅ | ✅ | 🟡 Usable | Webhook inbound + outbound bridge |
| **Slack** | ❌ | ✅ | 📤 Send-only | Outbound delivery |
| Signal / Matrix / IRC / iMessage / DingTalk / Feishu | ❌ | ❌ | 🚧 Planned | Registered surfaces |

---

## 🤖 Providers

ClawLite uses **LiteLLM** under the hood — swap models without changing your app code.

<details>
<summary><strong>OpenAI-compatible (15+)</strong></summary>

OpenAI · Gemini · Groq · DeepSeek · OpenRouter · Together · Hugging Face · xAI · Mistral · Moonshot · NVIDIA · BytePlus / Doubao · Volcengine · KiloCode · `custom/<model>`

</details>

<details>
<summary><strong>Anthropic-compatible (4)</strong></summary>

Anthropic · MiniMax · Xiaomi · Kimi Coding

</details>

<details>
<summary><strong>Local runtimes</strong></summary>

Ollama · vLLM

</details>

<details>
<summary><strong>Special</strong></summary>

OpenAI Codex (OAuth)

</details>

Default: `gemini/gemini-2.5-flash` — fast and free-tier friendly.

---

## 🏛️ Architecture

```
                        ┌─────────────────────────────────────┐
  Telegram │ Discord    │           ClawLite Runtime           │
  Email    │ WhatsApp ──▶  Channel Dispatcher                  │
  Slack    │ Web        │       │                              │
           │            │       ▼                              │
  CLI ─────┤            │  FastAPI Gateway  ◀── Dashboard UI  │
  HTTP ────┤            │  (127.0.0.1:8787)                   │
  WS ──────┘            │       │                              │
                        │       ▼                              │
                        │  Agent Engine  ◀── Session Store    │
                        │       │                              │
              ┌─────────┴───────┼──────────────────────┐      │
              │                 │                       │      │
              ▼                 ▼                       ▼      │
         LiteLLM           Tool Registry          Skills Loader│
         (20+ providers)   (21+ tools)            (24+ skills) │
              │                                               │
              ▼                                               │
         Memory Backend (BM25 + vector + FTS5 + SQLite/pgvector)
                        └─────────────────────────────────────┘

  Supervisor Loops: heartbeat · cron · autonomy · dead-letter · self-evolution
```

---

## ⚖️ How ClawLite Compares

| Feature | **ClawLite** | LangChain | AutoGPT | OpenAI Assistants |
|---------|:-----------:|:---------:|:-------:|:-----------------:|
| Local-first (no cloud) | ✅ | ⚠️ partial | ⚠️ partial | ❌ |
| 20+ LLM providers | ✅ | ✅ | ⚠️ limited | ❌ (OpenAI only) |
| Persistent hybrid memory | ✅ | ⚠️ plugin | ⚠️ basic | ✅ (cloud) |
| Real chat channels | ✅ 5 channels | ❌ | ⚠️ limited | ❌ |
| 24/7 self-healing runtime | ✅ | ❌ | ⚠️ experimental | ✅ (cloud) |
| Streaming responses | ✅ | ✅ | ⚠️ | ✅ |
| Operator dashboard | ✅ | ❌ | ⚠️ basic | ✅ (cloud) |
| Python SDK / CLI | ✅ | ✅ | ✅ | ❌ |
| Runs offline | ✅ (Ollama/vLLM) | ⚠️ | ❌ | ❌ |
| Privacy (your data, your machine) | ✅ | ⚠️ | ⚠️ | ❌ |

---

## 🛠️ Development

```bash
# Install dev dependencies + run tests
pip install -e .
python -m pytest tests/ -q --tb=short

# Lint
python -m ruff check --select=E,F,W .

# Focused test suites
python -m pytest tests/channels/test_discord.py -v
python -m pytest tests/channels/test_telegram.py -v
python -m pytest tests/core/test_engine.py -v

# Release preflight
bash scripts/release_preflight.sh --config ~/.clawlite/config.json --gateway-url http://127.0.0.1:8787
```

**CI runs on Python 3.10 and 3.12.**

---

## 🖥️ CLI Reference

```bash
clawlite configure --flow quickstart   # interactive setup wizard
clawlite gateway                       # start the HTTP/WS gateway
clawlite run "your message here"       # one-shot agent call
clawlite status                        # runtime health summary
clawlite diagnostics                   # full diagnostic snapshot
clawlite hatch                         # trigger first bootstrap turn

# Channel controls
clawlite telegram status / refresh / offset-commit <n>
clawlite discord status / refresh

# Operator controls
clawlite provider recover
clawlite autonomy wake --kind proactive
clawlite supervisor recover --component heartbeat
```

---

## 📚 Docs Map

| Doc | Contents |
|-----|----------|
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | Detailed setup walkthrough |
| [`docs/API.md`](docs/API.md) | Gateway HTTP + WebSocket API reference |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Operational commands and diagnostics |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Operator validation and incident flow |
| [`docs/providers.md`](docs/providers.md) | Provider catalog and auth |
| [`docs/channels.md`](docs/channels.md) | Channel behavior and caveats |
| [`docs/tools.md`](docs/tools.md) | Tool catalog and aliases |
| [`docs/memory.md`](docs/memory.md) | Memory backends, privacy, quality |
| [`docs/workspace.md`](docs/workspace.md) | Workspace runtime files and lifecycle |
| [`docs/STATUS.md`](docs/STATUS.md) | Live engineering snapshot |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |

---

## 🤝 Contributing

Contributions are welcome! To get started:

1. Fork the repo and create a feature branch
2. Follow the existing code style (ruff, typed Python 3.10+)
3. Add tests for new functionality — we use TDD
4. Open a PR with a clear description of what changed and why

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for full guidelines.

---

## 📄 License

MIT — see [`LICENSE`](LICENSE).

---

<div align="center">

Built with ❤️ for developers who want their AI assistant to run on their own terms.

**[⭐ Star on GitHub](https://github.com/eobarretooo/ClawLite)** · **[🐛 Report a Bug](https://github.com/eobarretooo/ClawLite/issues)** · **[💡 Request a Feature](https://github.com/eobarretooo/ClawLite/issues)**

</div>
