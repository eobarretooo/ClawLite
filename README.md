<div align="center">

# 🦊 ClawLite

**A local-first Python autonomous agent — persistent memory, 20+ LLM providers,<br>real chat channels, and a 24/7 self-healing runtime. No cloud required.**

[![CI](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LiteLLM](https://img.shields.io/badge/LiteLLM-20%2B%20providers-blueviolet)](https://litellm.ai)
[![FastAPI](https://img.shields.io/badge/FastAPI-gateway-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)

[Quickstart](#-quickstart) · [Features](#-features) · [Channels](#-channels) · [Providers](#-providers) · [Architecture](#-architecture) · [Docs](#-docs-map) · [Contributing](#-contributing)

</div>

> ### 🤖 Built by AI · Maintained by one person
>
> ClawLite is a **solo-dev project built entirely by AI (Claude)**. Every line of code, every test, every commit was written by an AI agent — the human author supervises, reviews goals, and guides direction. No team. No agency. Just one person and an AI building production software together.
>
> This is an ongoing experiment in AI-driven software development at the solo-dev scale.

---

## ⚡ Why ClawLite?

- **Truly local-first** — runs entirely on your machine; no vendor lock-in, no cloud accounts required
- **Production channels out of the box** — Telegram, Discord (slash commands, voice, polls), Email, WhatsApp, Slack
- **Persistent, searchable memory** — hybrid BM25 + vector search, temporal decay, consolidation loop
- **Self-healing runtime** — heartbeat supervisor, dead-letter replay, automatic provider failover
- **Batteries included** — 25+ skills, 21+ tools, streaming responses, operator dashboard

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

## ⚙️ Configuration

Config lives at `~/.clawlite/config.json`. Run `clawlite configure --flow quickstart` to generate it interactively, or start from one of the starters below.

<details>
<summary><strong>Minimal — any provider</strong></summary>

```json
{
  "agents": {
    "defaults": { "model": "gemini/gemini-2.5-flash" }
  },
  "providers": {
    "gemini": { "api_key": "YOUR_GEMINI_KEY" }
  },
  "gateway": { "port": 8787 }
}
```

</details>

<details>
<summary><strong>With Telegram bot</strong></summary>

```json
{
  "agents": {
    "defaults": { "model": "openai/gpt-4o" }
  },
  "providers": {
    "openai": { "api_key": "sk-..." }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allow_from": ["YOUR_TELEGRAM_USER_ID"]
    }
  }
}
```

</details>

Full field reference → [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md)

---

## 💡 Examples

**One-shot question:**
```bash
clawlite run "summarize the last 3 files I worked on"
```

**Persistent memory across sessions:**
```bash
clawlite run "remember that my project deadline is March 30"
# later...
clawlite run "what's my deadline?"
# → "Your project deadline is March 30."
```

**Trigger a Telegram message:**
```bash
clawlite run "send me a Telegram when the deploy finishes"
```

**Search the web and summarize:**
```bash
clawlite run "what's new in Python 3.13?"
```

**Read a PDF and answer questions:**
```bash
clawlite run "summarize docs/architecture.pdf"
```

**Schedule a recurring task:**
```bash
clawlite run "every morning at 9am send me a briefing on HN top stories"
```

---

## ✨ Features

**🧠 Memory**
Hybrid BM25 + vector search · FTS5 full-text · temporal decay + salience scoring · episodic→knowledge consolidation · SQLite or pgvector · snapshot/rollback

**🔁 Always-On Runtime**
Heartbeat supervisor · persistent cron engine · autonomy wake coordinator · dead-letter queue + replay · background job queue (priority, retry, SQLite) · context window budget trimming · loop detection with bus events · self-evolution runner

**🌊 Streaming**
`engine.stream_run()` async generator · `ProviderChunk` (delta/accumulated/done) · edit-in-place streaming on Telegram and Discord

**🖥️ Operator Dashboard** — `http://localhost:8787`
Live chat · sessions view · automation controls (cron, recovery, channels) · memory health · tools catalog · WebSocket frame preview

**🧰 Tools (22+)**

| Category | Tools |
|----------|-------|
| Files | `files` `exec` `apply_patch` `process` |
| Web | `web` `browser` (Playwright) |
| AI | `sessions` `agents` `spawn` `memory` `skills` `jobs` |
| Media | `pdf` `tts` |
| Integrations | `cron` `mcp` `message` `discord_admin` |

**🎯 Skills (25+)**

`web-search` · `memory` · `coding-agent` · `summarize` · `github` · `notion` · `obsidian` · `spotify` · `docker` · `jira` · `linear` · `trello` · `1password` · `apple-notes` · `weather` · `tmux` · `model-usage` · `healthcheck` · `skill-creator` · and more

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

ClawLite has four main layers:

**1. Channels** — inbound/outbound adapters for Telegram, Discord, Email, WhatsApp, Slack, and the CLI. All normalize to the same internal message format before hitting the gateway.

**2. FastAPI Gateway** (`:8787`) — HTTP + WebSocket server, operator dashboard, auth, and channel dispatch. Single entry point for all traffic.

**3. Agent Engine** — the core loop. On each turn it builds a prompt from memory + identity + workspace files, calls tools as needed, and streams tokens from LiteLLM (20+ providers). Loop detection, context window budgeting, and subagent orchestration all live here.

**4. Supporting layers** always running in the background:
- **Memory** — hybrid BM25 + vector search, FTS5, temporal decay, SQLite or pgvector
- **Supervisor** — heartbeat, cron, autonomy wake, dead-letter replay, background job queue

**Request flow:** user message → channel adapter → gateway → engine (memory retrieval + tool calls + LLM stream) → response streamed back → memory updated.

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
# Install and run tests
pip install -e .
python -m pytest tests/ -q --tb=short -k "not slow"

# Lint
python -m ruff check --select=E,F,W .

# Focused test suites
python -m pytest tests/channels/test_discord.py -v
python -m pytest tests/channels/test_telegram.py -v
python -m pytest tests/core/test_engine.py -v

# Regenerate demo GIF
python3 scripts/make_demo_gif.py

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

## 🧬 Inspired By

ClawLite draws ideas from two open-source agent runtimes:

- **[openclaw](https://github.com/eobarretooo/openclaw)** — TypeScript agent runtime with the richest feature set; primary reference for channel adapters, tool interfaces, and operator dashboard design
- **[nanobot](https://github.com/eobarretooo/nanobot)** — minimal Python agent; reference for clean core architecture and skill packaging

ClawLite is a Python-first reimplementation with a focus on local deployment, persistent memory, and production-grade channel support.

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
