<div align="center">

# 🦊 ClawLite

**A local-first Python autonomous agent — persistent memory, 20+ LLM providers,<br>real chat channels, and a 24/7 self-healing runtime. No cloud required.**

[![CI](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml)
[![Discord](https://img.shields.io/badge/Discord-Join%20Server-5865F2?logo=discord&logoColor=white)](https://discord.gg/F4wQvdv9fR)
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
- **Real channel adapters out of the box** — Telegram, Discord, Email, WhatsApp, Slack, and IRC
- **Persistent, searchable memory** — hybrid BM25 + vector search, temporal decay, consolidation loop
- **Self-healing runtime** — heartbeat supervisor, dead-letter replay, automatic provider failover
- **Batteries included** — 25+ skills, built-in tools, streaming responses, operator dashboard

---

## 🏁 Quickstart

```bash
# 1. Clone and install
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .

# Or install optional integrations up front
python3 -m pip install -e ".[browser,telegram,media]"

# Optional browser runtime download
python3 -m playwright install chromium

# 2. Configure (interactive wizard — sets provider, gateway, optional Telegram)
clawlite configure

# 3. Start the gateway
clawlite gateway
```

Open **http://127.0.0.1:8787** → live dashboard with chat, automation, memory, and tools.

If you pass `--config path.yaml`, YAML configs work out of the box. Optional runtimes now install via extras: `.[browser]` for Playwright, `.[telegram]` for the Telegram channel, and `.[media]` for TTS/PDF helpers.
Config profiles are also supported: `clawlite --config ./config.yaml --profile prod status` loads `config.yaml`, overlays `config.prod.yaml` if present, and then applies env vars.

**Android / Termux path:** use `proot-distro` with Ubuntu instead of trying to run the full stack directly on native Termux. The one-shot wrapper is:

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install_termux_proot.sh | bash
```

After that:

```bash
proot-distro login ubuntu --shared-tmp
clawlite configure --flow quickstart
clawlite gateway
```

Full walkthrough: [`docs/TERMUX_PROOT_UBUNTU.md`](docs/TERMUX_PROOT_UBUNTU.md)

```bash
# Or talk to the agent straight from the terminal
clawlite run "hello — what can you do?"
```

---

## 📈 Current Status

- `main` now has robustness phases 1-7 plus the main maintainability plan landed; the next work is release polish and new roadmap items.
- Local-provider startup, cron/jobs boundaries, browser lifecycle, skill networking policy, and Telegram runtime internals are hardened on `main`.
- The biggest runtime monoliths were split by responsibility: `clawlite/gateway/server.py` is down to about `3.3k` lines and `clawlite/core/memory.py` to about `4.4k`.
- Packaging is now split into extras: base install stays leaner, while `.[browser]`, `.[telegram]`, and `.[media]` enable optional runtimes.
- Phase 7 is complete on `main`: `self_evolution` now uses provider-direct proposal, pre-apply patch policy, isolated git worktree branches, configurable branch prefixes, and Telegram/Discord approval callbacks that record human review state while staying disabled by default.
- Gateway startup now uses per-subsystem timeouts, so a slow channel transport no longer blocks the whole control plane from coming up.
- OAuth-backed free-tier cloud setup now includes `gemini-oauth` and `qwen-oauth` alongside `openai-codex`.
- Latest validation on `main`: `python -m pytest tests -q --tb=short` → `1561 passed, 1 skipped`; `python -m pytest -q tests/runtime/test_autonomy_actions.py tests/gateway/test_server.py tests/runtime/test_self_evolution.py` → `190 passed`; `bash scripts/smoke_test.sh` → `7 ok / 0 failure(s)`.
- Tracking docs: [`docs/STATUS.md`](docs/STATUS.md) and [`docs/ROBUSTNESS_SCORECARD.md`](docs/ROBUSTNESS_SCORECARD.md).

---

## ⚙️ Configuration

Config lives at `~/.clawlite/config.json`. Run `clawlite configure --flow quickstart` to generate it interactively, or use plain `clawlite configure` for the two-level Basic/Advanced configuration menu.

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
Heartbeat supervisor · persistent cron engine · autonomy wake coordinator · dead-letter queue + replay · background job queue (priority, retry, SQLite) · context window budget trimming · loop detection with bus events · bounded subagent orchestration (depth guard, retry budgets, zombie cleanup)

**🌊 Streaming**
`engine.stream_run()` async generator · `ProviderChunk` (delta/accumulated/done) · edit-in-place streaming on Telegram and Discord

**🖥️ Operator Dashboard** — `http://localhost:8787`
Live chat · sessions view · automation controls (cron, recovery, channels) · memory health · tools catalog · WebSocket frame preview

**🧰 Built-In Tools**

| Category | Tools |
|----------|-------|
| Files | `files` `exec` `apply_patch` `process` |
| Web | `web` `browser` (Playwright) |
| AI | `sessions` `agents` `spawn` `memory` `skills` `jobs` |
| Media | `pdf` `tts` |
| Integrations | `cron` `mcp` `message` `discord_admin` |

**🎯 Skills (25+)**

`web-search` · `memory` · `coding-agent` · `summarize` · `github` · `notion` · `obsidian` · `spotify` · `docker` · `jira` · `linear` · `trello` · `1password` · `apple-notes` · `weather` · `tmux` · `model-usage` · `healthcheck` · `skill-creator` · and more

Skill lifecycle: `enable` / `disable` · `pin` / `unpin` · `pin-version` / `clear-version` · `fallback_hint` for unavailable skills

---

## 💬 Channels

| Channel | Inbound | Outbound | Status | Highlights |
|---------|---------|---------|--------|------------|
| **Telegram** | ✅ | ✅ | ✅ Complete | Polling + webhook, reactions, topics, reply keyboards, streaming |
| **Discord** | ✅ | ✅ | 🟡 Usable | Gateway WS, slash commands, buttons, voice messages, webhooks, polls, streaming |
| **Email** | ✅ | ✅ | 🟡 Usable | IMAP inbound + SMTP outbound |
| **WhatsApp** | ✅ | ✅ | 🟡 Usable | Webhook inbound, outbound retry, bridge typing keepalive |
| **Slack** | ✅ | ✅ | 🟡 Usable | Socket Mode inbound, outbound delivery, reversible working indicator |
| **IRC** | ✅ | ✅ | 🟡 Minimal | Asyncio transport, PING/PONG, JOIN, PRIVMSG |
| Signal / Matrix / iMessage / DingTalk / Feishu | ❌ | ❌ | 🚧 Planned | Registered surfaces |

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

Use a `/v1` base URL for local providers. Reverse-proxied prefixes such as `https://llm.internal/ollama/v1` also work.

</details>

<details>
<summary><strong>Special</strong></summary>

OpenAI Codex · Gemini OAuth · Qwen OAuth

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
# Install package + contributor tools
pip install -e ".[all]"
python -m pip install pytest ruff

# Run the main test suite
python -m pytest tests/ -q --tb=short

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

# Skills lifecycle
clawlite skills list [--all]           # list skills
clawlite skills show <name>            # show skill detail
clawlite skills check                  # diagnostics (missing deps, fallback hints)
clawlite skills enable/disable <name>  # toggle skill
clawlite skills pin/unpin <name>       # always-include / unpin
clawlite skills pin-version <name> <version>  # lock to specific version
clawlite skills clear-version <name>   # remove version pin

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
| [`docs/TERMUX_PROOT_UBUNTU.md`](docs/TERMUX_PROOT_UBUNTU.md) | Android setup with Termux + `proot-distro` Ubuntu |
| [`docs/API.md`](docs/API.md) | Gateway HTTP + WebSocket API reference |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | Operational commands and diagnostics |
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | Operator validation and incident flow |
| [`docs/ROBUSTNESS_SCORECARD.md`](docs/ROBUSTNESS_SCORECARD.md) | Current score by area plus `P0/P1/P2` backlog |
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
