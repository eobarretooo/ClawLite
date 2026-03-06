# ClawLite ✨

<!-- Portable runtime-first autonomous assistant for Linux. -->

ClawLite is a **portable, runtime-first autonomous assistant** designed for Linux, focused on CLI and gateway operations. It provides a robust environment for intelligent agents, featuring multi-provider inference routing, an advanced memory subsystem, and scheduling services.

---

## 🚀 Overview

ClawLite serves as the core of a Python agent system, centered around command-line interface (CLI) and efficient gateway operations. It operates without the need for a graphical dashboard, serving a minimal static HTML entry point for endpoint visibility. Its modular and extensible architecture allows for the creation of autonomous agents with advanced memory, scheduling, and multi-channel interaction capabilities.

### Key Features:

*   **FastAPI Gateway**: Provides `/v1/*` endpoints and `/api/*` compatibility aliases for flexible interaction.
*   **Chat Entrypoints**: Support for both WebSocket and HTTP chat communication.
*   **Scheduling Services**: Includes cron, heartbeat, and supervision for automation and monitoring.
*   **Multi-provider Inference Routing**: Manages routing and authentication lifecycle for various inference providers.
*   **Advanced Memory Subsystem**: Features diagnostics, versioning, branching, and quality tuning for intelligent agent memory.

---

## 🛠️ Tech Stack

*   **Python 3.10+**: Core programming language.
*   **FastAPI**: High-performance web framework for the gateway.
*   **WebSocket**: For real-time chat communication.
*   **CLI (Command Line Interface)**: For agent interaction and control.
*   **LiteLLM**: For multi-provider inference routing.

---

## 🏗️ Architecture

ClawLite's architecture is modular and well-defined, comprising the following main components:

```text
clawlite/
├── core/         # engine, prompt, memory, skills, subagent
├── tools/        # tool abc, registry, and built-in tools
├── bus/          # events and async queue
├── channels/     # manager + channels (full telegram, other adapters)
├── gateway/      # FastAPI + WebSocket
├── scheduler/    # cron + heartbeat
├── providers/    # litellm/custom/codex/transcription
├── session/      # JSONL store per session
├── config/       # schema + loader
├── workspace/    # loader + identity templates
├── skills/       # built-in markdown skills (SKILL.md)
├── cli/          # start/run/onboard/cron commands
└── utils/        # shared helpers
```

**Main Flow:**

1.  A message enters via `channels` or the `gateway`.
2.  `core.engine` builds the prompt (workspace + memory + history + skills).
3.  The provider responds; if tool calls are present, `tools.registry` executes them.
4.  The final response is delivered first; persistence (`session.store` append + `core.memory` consolidate) runs in best-effort mode and logs degraded storage failures without aborting the turn.
5.  `scheduler.cron` and `scheduler.heartbeat` trigger proactive runs.

---

## ⚡ Quickstart

**Prerequisite:** Python 3.10+

Follow these steps to get ClawLite up and running quickly:

1.  **Install locally:**

    ```bash
    pip install -e .
    ```

2.  **Generate workspace templates / onboarding baseline:**

    ```bash
    clawlite onboard
    # interactive wizard variant:
    clawlite onboard --wizard
    ```

3.  **Configure provider (example):**

    ```bash
    export CLAWLITE_MODEL="gemini/gemini-2.5-flash"
    export CLAWLITE_LITELLM_API_KEY="<your-key>"
    ```

4.  **Start the gateway:**

    ```bash
    clawlite start --host 127.0.0.1 --port 8787
    # alias:
    clawlite gateway --host 127.0.0.1 --port 8787
    ```

5.  **Send a chat request:**

    ```bash
    curl -sS http://127.0.0.1:8787/v1/chat \
      -H 'content-type: application/json' \
      -d '{"session_id":"cli:quickstart","text":"hello"}'
    ```

    *If auth mode is required, include the bearer token (header or query param, per config).* 

---

## ⚙️ Essential CLI Commands

### Provider & Validation:

```bash
clawlite provider status
clawlite provider use openai --model openai/gpt-4.1-mini
clawlite provider set-auth openai --api-key "<key>"
clawlite validate provider
clawlite validate config
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

### Diagnostics, Memory, Scheduler & Skills:

```bash
clawlite diagnostics --gateway-url http://127.0.0.1:8787
clawlite memory
clawlite memory doctor
clawlite memory quality --gateway-url http://127.0.0.1:8787
clawlite cron add --session-id cli:ops --expression "every 300" --prompt "status"
clawlite heartbeat trigger --gateway-url http://127.0.0.1:8787
clawlite skills list
clawlite skills check
```

---

## 🌐 Gateway Endpoints (v1 + Compatibility Aliases)

| Method | Endpoint | Notes |
|---|---|---|
| `GET` | `/` | Minimal static gateway entrypoint (no dashboard dependency) |
| `GET` | `/health` | Health/readiness snapshot |
| `GET` | `/v1/status` | Control-plane status |
| `GET` | `/api/status` | Alias of `/v1/status` |
| `GET` | `/v1/diagnostics` | Runtime diagnostics snapshot |
| `GET` | `/api/diagnostics` | Alias of `/v1/diagnostics` |
| `POST` | `/v1/chat` | Main HTTP chat endpoint |
| `POST` | `/api/message` | Alias of `/v1/chat` |
| `GET` | `/api/token` | Masked token diagnostics |
| `POST` | `/v1/control/heartbeat/trigger` | Trigger heartbeat cycle |
| `POST` | `/v1/cron/add` | Create cron job |
| `GET` | `/v1/cron/list` | List cron jobs by session |
| `DELETE` | `/v1/cron/{job_id}` | Remove cron job |
| `WS` | `/v1/ws` | Main WebSocket chat |
| `WS` | `/ws` | Alias of `/v1/ws` |

---

## 🧠 Memory & Autonomy Highlights

*   Hybrid memory retrieval and quality tracking are integrated into runtime diagnostics and CLI operations.
*   Memory quality state persists scoring, drift assessment, recommendations, and tuning history.
*   The tuning loop runs as an autonomous runtime component when enabled, with fail-soft behavior, cooldown, and rate limiting.
*   Layer-aware playbooks select actions based on drift severity and the weakest reasoning layer.
*   Layer-specific execution details are persisted for auditability (`template_id`, `backfill_limit`, `snapshot_tag`, `action_variant`) along with playbook fields.
*   Diagnostics expose tuning telemetry maps and the latest action context (`actions_by_layer`, `actions_by_playbook`, `actions_by_action`, `action_status_by_layer`, `last_action_metadata`).

---

## 💡 Skills

ClawLite uses **Markdown skills (`SKILL.md`)** with automatic discovery. Skills are loaded from sources including `builtin` (repository), `user workspace`, and `local marketplace`, with a deterministic resolution policy for duplicates.

### Current Built-in Skills:

*   `cron`
*   `memory`
*   `github`
*   `summarize`
*   `skill-creator`
*   `web-search`
*   `weather`
*   `tmux`
*   `hub`
*   `clawhub`

---

## 🧪 Testing & CI

### Local Checks:

```bash
pytest -q tests
ruff check clawlite/ --select E9,F --ignore F401,F811
bash scripts/smoke_test.sh
clawlite validate preflight --gateway-url http://127.0.0.1:8787
```

### CI Workflows (`.github/workflows/`):

*   `ci.yml` (pytest matrix, lint, smoke, autonomy contract)
*   `coverage.yml` (pytest + coverage XML)
*   `secret-scan.yml` (gitleaks)

---

## 🤝 Contributing

Contributions are **highly welcome**! To contribute to ClawLite, please follow the guidelines in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 📝 License

This project is distributed under the [MIT License](LICENSE). See the `LICENSE` file for more details.

---

## 👤 Authors

*   **eobarretooo** - *Initial Development* - [GitHub](https://github.com/eobarretooo)

---

## 🌟 Acknowledgments

ClawLite is built upon and inspired by several amazing open-source projects:

*   **[Nanobot](https://github.com/HKUDS/nanobot)** - For its innovative approach to autonomous agents.
*   **[OpenClaw](https://github.com/openclaw/openclaw)** - For providing a solid foundation and inspiration for the runtime.
*   **[memU](https://github.com/NevaMind-AI/memU)** - For its advanced memory management concepts.
*   **[awesome-readme](https://github.com/matiassingers/awesome-readme)** - For the design patterns and best practices for creating professional READMEs.
*   To the entire open-source community for the incredible tools and libraries that make this project possible.
