<div align="center">

# 🦊 ClawLite

**A local-first Python autonomous agent — persistent memory, 20+ LLM providers,<br>real chat channels, and a 24/7 self-healing runtime. No cloud required.**

[![CI](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/eobarretooo/ClawLite/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/eobarretooo/ClawLite?include_prereleases&label=release&color=ff6b2b)](https://github.com/eobarretooo/ClawLite/releases/tag/v0.7.0-beta.0)
[![Discord](https://img.shields.io/badge/Discord-Join%20Server-5865F2?logo=discord&logoColor=white)](https://discord.gg/F4wQvdv9fR)
[![Stars](https://img.shields.io/github/stars/eobarretooo/ClawLite?style=flat&color=f5b301)](https://github.com/eobarretooo/ClawLite/stargazers)
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
python3 -m pip install -e ".[browser,telegram,media,runtime]"

# Optional browser runtime download
python3 -m playwright install chromium

# 2. Configure (interactive wizard — sets provider, gateway, optional Telegram)
clawlite configure

# 3. Start the gateway
clawlite gateway
```

Open **http://127.0.0.1:8787** → live dashboard with chat, automation, memory, and tools.

If you pass `--config path.yaml`, YAML configs work out of the box. Optional runtimes now install via extras: `.[browser]` for Playwright, `.[telegram]` for the Telegram channel, `.[media]` for TTS/PDF helpers, `.[runtime]` for Redis-backed bus support, and `.[observability]` for OTLP/OpenTelemetry exports.
Config profiles are also supported: `clawlite --config ./config.yaml --profile prod status` loads `config.yaml`, overlays `config.prod.yaml` if present, and then applies env vars.

**Android / Termux path:** use `proot-distro` with Ubuntu instead of trying to run the full stack directly on native Termux. The one-shot wrapper is:

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install_termux_proot.sh | bash
```

If an older `/root/ClawLite` checkout inside Ubuntu has diverged from `origin/main`, the wrapper now preserves it as a timestamped backup and reclones cleanly instead of failing on `git pull --ff-only`.
The Termux wrapper also fetches the latest checkout-sync helper directly from GitHub, so rerunning the one-shot `curl ... | bash` path is the safest update path even when an older local wrapper script is stale.

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

### Docker quickstart

ClawLite now ships an official Docker path:

```bash
bash scripts/docker_setup.sh
```

This persists state in `~/.clawlite`, exposes the dashboard on `http://127.0.0.1:8787`, and includes a CLI sidecar for one-shot commands like:

```bash
docker compose run --rm clawlite-cli status
docker compose run --rm clawlite-cli run "summarize the latest session"
```

If you want the Redis bus backend from Docker, enable the `redis` profile and the matching env overrides:

```bash
CLAWLITE_BUS_BACKEND=redis docker compose --profile redis up -d
```

The Docker image now runs as a non-root `clawlite` user by default. If your host UID/GID is not `1000`, export `CLAWLITE_UID` and `CLAWLITE_GID` before building or use the setup helper, which does that automatically.

Full guide: [`docs/DOCKER.md`](docs/DOCKER.md)

---

## 📈 Current Status

- `v0.7.0-beta.0` is out, and it closes robustness phases 1-7 plus the full `plano.md` milestone on the beta track.
- `main` is now focused on soak-testing, documentation polish, and the next roadmap items rather than another large hardening pass.
- Local-provider startup, cron/jobs boundaries, browser lifecycle, skill networking policy, and Telegram runtime internals are hardened on `main`.
- The current Discord parity slice now includes DM/guild policy controls, guild/channel/role allowlists, bot gating, explicit session routing, configurable `reply_to_mode`, isolated native slash-command sessions, deferred interaction replies, static presence plus `auto_presence`, persistent `/focus` / `/unfocus` bindings, native `/discord-presence` controls, and automatic idle/max-age expiry for stale Discord focus bindings.
- The biggest runtime monoliths were split by responsibility: `clawlite/gateway/server.py` is down to about `3.3k` lines and `clawlite/core/memory.py` to about `4.4k`.
- Packaging is now split into extras: base install stays leaner, while `.[browser]`, `.[telegram]`, and `.[media]` enable optional runtimes.
- Skills now honor OpenClaw-style `skills.entries.<skill>` overrides for `enabled`, `env`, and `apiKey`, including profile overlays such as `config.prod.yaml`.
- Builtin skills can now be gated with `skills.allowBundled` without blocking workspace or marketplace overrides.
- Tool safety now supports granular specifiers such as `browser:evaluate`, `run_skill:github`, `exec:git`, `exec:shell`, and `exec:env-key:git-ssh-command`, plus approval mode via `approval_specifiers` / `approval_channels`, with `tool:*` wildcards for channel-specific policy.
- Tool safety now also derives host-aware rules for `web_fetch` and `browser:navigate`, so operator policy can target specific destinations such as `web_fetch:host:example-com` instead of only whole-tool approvals.
- Explicit shell wrappers like `sh -lc`, `bash -lc`, and `cmd /c` now classify as `exec:shell` and are recursively guarded under workspace restriction, so they no longer bypass `restrict_to_workspace` by hiding path access behind `$HOME`, `~`, or similar expansions.
- `exec` and `process` now also block obvious `curl` / `wget` / PowerShell web fetches to localhost, private ranges, and metadata-style `http(s)` targets, closing a network-policy bypass that previously sat outside `web_fetch`.
- `exec` and `process` now also block the same internal `http(s)` targets when they appear inside obvious runtime fetch payloads such as `python -c`, `python -m urllib.request`, `node -e`, or `node -p`, including common transparent launch wrappers like `/usr/bin/env`, `env -i`, `env -S`, `nohup`, `nice`, `timeout`, or `stdbuf`, so generic interpreters cannot trivially sidestep `web_fetch` policy.
- `web_fetch` and `web_search` now label their payloads as untrusted external content and include a safety notice in the structured result, reducing prompt-injection risk without changing the main `text` contract that existing skills already consume.
- `browser.navigate` keeps an explicit “external page content” prefix, and prompt guidance now treats browser page reads plus browser evaluations as untrusted external data without breaking the raw `browser.evaluate` return contract for callers that need exact values.
- Inbound channel turns now pass a compact allowlisted subset of runtime metadata into the prompt as untrusted context, including safe structural hints like message/thread ids, DM/forum state, Slack thread timestamps, signed callback/button ids, and media markers without ingesting raw webhook payloads.
- Inbound channel text now also normalizes real newlines and neutralizes obvious spoof markers like `[System Message]`, bracketed `[Developer]`, or leading `System:` before that text reaches the agent loop.
- Direct gateway chat requests over HTTP/WebSocket can now forward optional `channel`, `chat_id`, and `runtime_metadata`, so manual operator/API traffic preserves the same untrusted runtime hints that native channel adapters already provide.
- Scheduled cron turns and queued `agent_run` / `skill_exec` jobs now preserve explicit routing context (`channel`, `target` / `chat_id`, `runtime_metadata`) when that data is already present in the payload.
- `stream_run()` now falls back to the full agent loop for live lookup turns and explicit GitHub/Docker skill-routed turns, so streaming no longer takes a text-only shortcut when the runtime already knows the answer should go through operational tools or verified lookup.
- The prompt runtime-context block is now merged into the current user turn before provider calls, reducing provider-compatibility risk from adjacent `user` messages while preserving the same untrusted metadata semantics and raw session persistence.
- Approval-gated tool calls now surface interactive approve/reject controls in Telegram and Discord, backed by temporary request-bound grants so the operator can approve and then retry only that reviewed call safely.
- Operators can now review those pending tool approvals from the gateway or CLI with `clawlite tools approvals|approve|reject`, and revoke active temporary grants explicitly with `clawlite tools revoke-grant`. Approval snapshots now include structured context such as exec binary/env keys/cwd and browser or web host targets.
- Skills now include a dedicated `clawlite skills doctor` view that turns deterministic diagnostics into actionable remediation hints for missing env vars, binaries, config keys, and bundled-skill policy blocks, with optional `--status` / `--source` / `--query` filters for operator triage.
- Managed skills now expose richer local lifecycle state in the CLI, including aggregate `status_counts` plus resolved marketplace state after `install`, `update`, `sync`, and `remove`. `skills search` also includes matching locally managed skills for quick operator triage.
- `clawlite skills config <name>` now gives the operator a direct path to inspect or update `skills.entries.<skillKey>` in the active config/profile, including `apiKey`, per-skill `env`, and `enabled` overrides without editing JSON/YAML manually.
- Workspace defaults no longer inject fake user profile values like `Owner`, and explicit “search on the internet / latest” requests now add a web-research requirement so the engine is pushed toward `web_search` / `web_fetch` before answering.
- Telegram outbound rendering now cleans up inline numbered lists, markdown headings, and pipe tables into more readable channel-safe HTML.
- Phase 7 is complete on `main`: `self_evolution` now uses provider-direct proposal, pre-apply patch policy, isolated git worktree branches, configurable branch prefixes, and Telegram/Discord approval callbacks that record human review state while staying disabled by default.
- Gateway startup now uses per-subsystem timeouts, so a slow channel transport no longer blocks the whole control plane from coming up.
- OAuth-backed free-tier cloud setup now includes `gemini-oauth` and `qwen-oauth` alongside `openai-codex`.
- File-backed `gemini-oauth` and `qwen-oauth` providers now refresh expired access tokens once on `401`, persist the renewed token back into the local CLI auth file, and retry the request automatically.
- The onboarding wizard now suggests provider-specific model ids, expected base URLs, and OAuth re-login hints before it probes the selected provider.
- Wizard coverage now also includes `azure-openai`, `aihubmix`, `siliconflow`, and `cerebras`, matching the current OpenClaw/nanobot parity slice for OpenAI-compatible providers.
- Prompt/context hardening on `main` now includes larger history budget allocation, optional semantic compression for trimmed history, optional oversized tool-result compaction, workspace prompt file byte ceilings, and explicit per-tool timeout overrides through `tools.timeouts.<tool>`.
- The cron control plane now exposes richer operational state: `/v1/cron/status`, expanded `/v1/cron/list`, per-job inspection, and native enable/disable controls on top of the existing scheduler.
- Runtime scale-out and observability are now in place as opt-in surfaces: Redis bus backend, OTLP telemetry hooks, session TTL, history compaction, `sqlite-vec`, and `memory_compact`.
- Latest validation on `main`: `python -m pytest tests -q --tb=short` → `1699 passed, 1 skipped`; `python -m pytest -q tests/runtime/test_autonomy_actions.py tests/gateway/test_server.py tests/runtime/test_self_evolution.py` → `194 passed`; `bash scripts/smoke_test.sh` → `7 ok / 0 failure(s)`.
- Tracking docs: [`docs/STATUS.md`](docs/STATUS.md) and [`docs/ROBUSTNESS_SCORECARD.md`](docs/ROBUSTNESS_SCORECARD.md).
- The next major execution track is the OpenClaw parity push for Docker, Discord, tools, and skills.

---

## ⭐ Star History

<div align="center">
  <a href="https://star-history.com/#eobarretooo/ClawLite&Date">
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=eobarretooo/ClawLite&type=Date" width="100%" />
  </a>
</div>

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
`engine.stream_run()` async generator · `ProviderChunk` (delta/accumulated/done) · same base prompt shaping as `run()` for memory/history/runtime context · falls back to the full `run()` loop on live-lookup turns instead of staying text-only · edit-in-place streaming on Telegram and Discord

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

`exec` now accepts per-call `cwd` / `workdir` and `env` overrides while preserving workspace guards.
`browser.navigate` now follows the same host policy model as `web_fetch` for allowlist, denylist, and private-address blocking.
The default tool safety baseline now treats `browser` as risky alongside `exec`, `run_skill`, and `web_fetch`.

**🎯 Skills (25+)**

`web-search` · `memory` · `coding-agent` · `summarize` · `github` · `notion` · `obsidian` · `spotify` · `docker` · `jira` · `linear` · `trello` · `1password` · `apple-notes` · `weather` · `tmux` · `model-usage` · `healthcheck` · `skill-creator` · and more

Skill lifecycle: `enable` / `disable` · `pin` / `unpin` · `pin-version` / `clear-version` · `install` / `update` / `sync` / `remove` for managed marketplace skills · `fallback_hint` for unavailable skills

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
<summary><strong>OpenAI-compatible (19+)</strong></summary>

OpenAI · Azure OpenAI · Gemini · Groq · DeepSeek · OpenRouter · AiHubMix · SiliconFlow · Cerebras · Together · Hugging Face · xAI · Mistral · Moonshot · NVIDIA · BytePlus / Doubao · Volcengine · KiloCode · `custom/<model>`

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

**OpenAI Codex**

```json
{
  "auth": {
    "providers": {
      "openai_codex": {
        "access_token": "oauth-token",
        "account_id": "org-123"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": "openai-codex/gpt-5.3-codex"
    }
  }
}
```

```bash
clawlite provider login openai-codex
clawlite provider status codex
```

If the wizard or `provider status` reports an expired local Codex token, refresh it with `clawlite provider login openai-codex` and rerun the probe. File-backed Codex auth now follows the current `~/.codex/auth.json` session instead of a stale snapshot previously saved in `~/.clawlite/config.json`.

**Azure OpenAI**

```json
{
  "providers": {
    "azure_openai": {
      "api_key": "azure-key",
      "api_base": "https://example-resource.openai.azure.com/openai/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "azure-openai/gpt-4.1-mini"
    }
  }
}
```

```bash
clawlite provider set-auth azure-openai --api-key "$AZURE_OPENAI_API_KEY" \
  --api-base "https://example-resource.openai.azure.com/openai/v1"
clawlite provider status azure-openai
```

**Gemini OAuth**

```json
{
  "auth": {
    "providers": {
      "gemini_oauth": {
        "access_token": "oauth-token"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": "gemini_oauth/gemini-2.0-flash"
    }
  }
}
```

```bash
clawlite provider login gemini-oauth
clawlite provider status gemini-oauth
```

**Qwen OAuth**

```json
{
  "auth": {
    "providers": {
      "qwen_oauth": {
        "access_token": "oauth-token"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": "qwen_oauth/qwen-plus"
    }
  }
}
```

```bash
clawlite provider login qwen-oauth
clawlite provider status qwen-oauth
```

Full provider auth details: [`docs/providers.md`](docs/providers.md)

</details>

Default: `gemini/gemini-2.5-flash` — fast and free-tier friendly.

---

## 🏛️ Architecture

ClawLite has four main layers:

**1. Channels** — inbound/outbound adapters for Telegram, Discord, Email, WhatsApp, Slack, and the CLI. All normalize to the same internal message format before hitting the gateway.

**2. FastAPI Gateway** (`:8787`) — HTTP + WebSocket server, operator dashboard, auth, and channel dispatch. Single entry point for all traffic.

**3. Agent Engine** — the core loop. On each turn it builds a prompt from memory + identity + workspace files, calls tools as needed, and streams tokens from LiteLLM (20+ providers). `run()` and `stream_run()` now share the same base prompt shaping for memory, history, and runtime context, and `stream_run()` falls back to the full `run()` loop on live-lookup turns so current-data answers do not stay on a text-only path. Loop detection, context window budgeting, and subagent orchestration all live here.

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
| Real chat channels | ✅ 6 channels | ❌ | ⚠️ limited | ❌ |
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
clawlite skills doctor                 # actionable remediation hints for broken skills
clawlite skills doctor --status missing_requirements --source builtin
clawlite skills doctor --query github
clawlite skills config github --api-key ghp_example --env GH_HOST=github.example.com --enable
clawlite skills enable/disable <name>  # toggle skill
clawlite skills pin/unpin <name>       # always-include / unpin
clawlite skills pin-version <name> <version>  # lock to specific version
clawlite skills clear-version <name>   # remove version pin
clawlite skills install <slug>         # install managed skill into ~/.clawlite/marketplace
clawlite skills update <name>          # update one managed marketplace skill
clawlite skills search <query>         # search ClawHub for managed skills
clawlite skills managed [--status ready|missing_requirements|policy_blocked] [--query discord]
clawlite skills sync                   # update managed marketplace skills via ClawHub
clawlite skills remove <name>          # remove managed marketplace skill
clawlite tools safety browser --session-id telegram:1 --channel telegram --args-json '{"action":"evaluate"}'
clawlite tools approvals --include-grants --tool browser --rule browser:evaluate
clawlite tools approve <request_id> --actor ops --note "approved after review"
clawlite tools reject <request_id> --actor ops --note "needs a safer path"
clawlite tools revoke-grant --session-id telegram:1 --channel telegram --rule browser:evaluate
clawlite tools catalog --include-schema
clawlite tools show bash

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
| [`docs/DOCKER.md`](docs/DOCKER.md) | Official container build + compose flow |
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
