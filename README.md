<div align="center">

# 🦊 ClawLite

*A local-first autonomous AI agent — persistent memory, 20+ LLM providers, real chat channels, and a 24/7 self-healing runtime.*

[![CI](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/eobarretooo/ClawLite?include_prereleases&label=release&color=ff6b2b)](https://github.com/eobarretooo/ClawLite/releases/tag/v0.7.0-beta.0)
[![Stars](https://img.shields.io/github/stars/eobarretooo/ClawLite?style=flat&color=f5b301)](https://github.com/eobarretooo/ClawLite/stargazers)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)

[Quickstart](#-quickstart) · [Features](#-features) · [Channels](#-channels) · [Providers](#-providers) · [Docs](#-docs) · [Contributing](#-contributing)

</div>

> **Built by AI · Maintained by one person.** Every line of code, every test, every commit was written by an AI agent — the human author supervises, reviews goals, and guides direction.

---

## ⚡ Why ClawLite?

- **Truly local-first** — runs entirely on your machine; no cloud required
- **Real channel adapters** — Telegram, Discord, Email, WhatsApp, Slack, IRC
- **Persistent memory** — hybrid BM25 + vector search, temporal decay, consolidation loop
- **Self-healing runtime** — heartbeat supervisor, dead-letter replay, automatic provider failover
- **Batteries included** — 25+ skills, streaming responses, operator dashboard

---

## 🏁 Quickstart

```bash
# Clone and install
git clone https://github.com/eobarretooo/ClawLite.git
cd ClawLite
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[browser,telegram,media,runtime]"

# Configure interactively
clawlite configure

# Start the gateway + dashboard
clawlite gateway
```

Open **http://127.0.0.1:8787** for the live dashboard.

```bash
# Or talk directly from the terminal
clawlite run "hello — what can you do?"
```

**Docker:**
```bash
bash scripts/docker_setup.sh
```

**Android / Termux:** see [`docs/TERMUX_PROOT_UBUNTU.md`](docs/TERMUX_PROOT_UBUNTU.md)

---

## ✨ Features

| Area | What you get |
|---|---|
| 🧠 **Memory** | BM25 + vector search · FTS5 · temporal decay · episodic→knowledge consolidation · SQLite or pgvector |
| 🔁 **Runtime** | Heartbeat supervisor · cron engine · dead-letter replay · background job queue · loop detection · subagent orchestration |
| 🌊 **Streaming** | `stream_run()` async generator · `ProviderChunk` delta/done · edit-in-place on Telegram and Discord |
| 🖥️ **Dashboard** | Live chat · sessions · cron controls · memory health · tools catalog — `http://127.0.0.1:8787` |
| 🧰 **Tools** | `files` `exec` `web` `browser` `memory` `sessions` `spawn` `cron` `mcp` `pdf` `tts` and more |
| 🎯 **Skills (25+)** | `web-search` `coding-agent` `github` `docker` `notion` `spotify` `obsidian` `weather` `tmux` and more |

---

## 💬 Channels

| Channel | Status |
|---|---|
| **Telegram** | ✅ Complete — polling + webhook, streaming, reactions, topics, keyboards |
| **Discord** | 🟡 Usable — gateway WS, slash commands, buttons/selects/modals, voice transcription, streaming |
| **Email** | 🟡 Usable — IMAP inbound + SMTP outbound |
| **WhatsApp** | 🟡 Usable — webhook inbound, outbound retry |
| **Slack** | 🟡 Usable — Socket Mode, working indicator |
| **IRC** | 🟡 Minimal — asyncio transport, PING/PONG |

---

## 🤖 Providers

Powered by **LiteLLM** — swap models without changing code.

**OpenAI-compatible:** OpenAI · Azure OpenAI · Gemini · Groq · DeepSeek · OpenRouter · SiliconFlow · Cerebras · Mistral · Moonshot · xAI · `custom/<model>`

**Anthropic-compatible:** Anthropic · MiniMax · Kimi

**Local:** Ollama · vLLM

**OAuth (free-tier):** `gemini-oauth` · `qwen-oauth` · `openai-codex`

```bash
clawlite provider login gemini-oauth   # authenticate
clawlite provider status gemini-oauth  # check status
```

Full auth details → [`docs/providers.md`](docs/providers.md)

---

## 🏛️ Architecture

```text
User Message
    -> Channel Adapter (Telegram / Discord / CLI / ...)
    -> FastAPI Gateway :8787
    -> Agent Engine (memory + tools + LLM stream)
    -> Response streamed back + memory updated
```

---

## 🛠️ Development

```bash
pip install -e ".[all]"
python -m pytest tests/ -q --tb=short   # full suite (2018 passed, 1 skipped)
python -m ruff check --select=E,F,W .   # lint
```

CI runs on Python 3.10 and 3.12.

---

## 🖥️ CLI Reference

```bash
clawlite configure              # interactive setup wizard; reuses local runtimes, suggests the detected provider when clear, reuses detected credentials, skips redundant env-backed key prompts, surfaces plausible backends when setup is ambiguous, and lets quickstart skip redundant local-runtime/model prompts on the resolved happy path
clawlite --profile prod configure  # save setup changes to config.prod.json
clawlite --profile prod dashboard --no-open  # reopen the control plane against config.prod.json
clawlite gateway                # start HTTP/WS gateway
clawlite run "..."              # one-shot agent call
clawlite status                 # runtime health summary
clawlite diagnostics            # full diagnostic snapshot

clawlite skills list            # list available skills
clawlite skills doctor          # diagnose broken skills
clawlite skills validate        # refresh + diagnose live skills state
clawlite skills install <slug>  # install from marketplace

clawlite tools approvals        # list pending tool approvals
clawlite tools approve <id>     # approve a tool call
clawlite tools reject <id>      # reject a tool call
```

Full CLI reference → [`docs/OPERATIONS.md`](docs/OPERATIONS.md)

---

## 📚 Docs

| Doc | Contents |
|---|---|
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | Detailed setup walkthrough |
| [`docs/DOCKER.md`](docs/DOCKER.md) | Container build + compose |
| [`docs/TERMUX_PROOT_UBUNTU.md`](docs/TERMUX_PROOT_UBUNTU.md) | Android / Termux setup |
| [`docs/API.md`](docs/API.md) | Gateway HTTP + WebSocket API |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | CLI and operational commands |
| [`docs/providers.md`](docs/providers.md) | Provider catalog and auth |
| [`docs/channels.md`](docs/channels.md) | Channel behavior and caveats |
| [`docs/STATUS.md`](docs/STATUS.md) | Engineering snapshot and changelog |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |

---

## 🤝 Contributing

1. Fork the repo and create a feature branch
2. Follow the existing code style (ruff, typed Python 3.10+)
3. Add tests for new functionality
4. Open a PR with a clear description

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for full guidelines. Join the [Discord](https://discord.gg/F4wQvdv9fR) for discussion.

---

## 📄 License

MIT — see [`LICENSE`](LICENSE).

---

<div align="center">

Built for developers who want their AI assistant to run on their own terms.

**[⭐ Star on GitHub](https://github.com/eobarretooo/ClawLite)** · **[🐛 Report a Bug](https://github.com/eobarretooo/ClawLite/issues)** · **[💡 Request a Feature](https://github.com/eobarretooo/ClawLite/issues)**

</div>
