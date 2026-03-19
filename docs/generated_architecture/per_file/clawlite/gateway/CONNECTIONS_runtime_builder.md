# CONNECTIONS clawlite/gateway/runtime_builder.py

## Relationship Summary

- Imports 46 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 0.

## Internal Imports

- `clawlite/bus/journal.py`
- `clawlite/bus/queue.py`
- `clawlite/bus/redis_queue.py`
- `clawlite/channels/manager.py`
- `clawlite/config/schema.py`
- `clawlite/core/engine.py`
- `clawlite/core/memory.py`
- `clawlite/core/memory_backend.py`
- `clawlite/core/memory_monitor.py`
- `clawlite/core/prompt.py`
- `clawlite/core/skills.py`
- `clawlite/gateway/autonomy_notice.py`
- `clawlite/gateway/discord_thread_binding.py`
- `clawlite/gateway/self_evolution_approval.py`
- `clawlite/gateway/tool_approval.py`
- `clawlite/jobs/journal.py`
- `clawlite/jobs/queue.py`
- `clawlite/providers/__init__.py`
- `clawlite/providers/discovery.py`
- `clawlite/runtime/__init__.py`
- `clawlite/runtime/self_evolution.py`
- `clawlite/runtime/telemetry.py`
- `clawlite/scheduler/cron.py`
- `clawlite/scheduler/heartbeat.py`
- `clawlite/session/store.py`
- `clawlite/tools/agents.py`
- `clawlite/tools/apply_patch.py`
- `clawlite/tools/browser.py`
- `clawlite/tools/cron.py`
- `clawlite/tools/discord_admin.py`
- `clawlite/tools/exec.py`
- `clawlite/tools/files.py`
- `clawlite/tools/jobs.py`
- `clawlite/tools/mcp.py`
- `clawlite/tools/memory.py`
- `clawlite/tools/message.py`
- `clawlite/tools/pdf.py`
- `clawlite/tools/process.py`
- `clawlite/tools/registry.py`
- `clawlite/tools/sessions.py`
- `clawlite/tools/skill.py`
- `clawlite/tools/spawn.py`
- `clawlite/tools/tts.py`
- `clawlite/tools/web.py`
- `clawlite/utils/logging.py`
- `clawlite/workspace/loader.py`

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_server.py`

## Mermaid

```mermaid
flowchart TD
    N0["runtime_builder.py"]
    D1["clawlite/bus/journal.py"]
    D2["clawlite/bus/queue.py"]
    D3["clawlite/bus/redis_queue.py"]
    D4["clawlite/channels/manager.py"]
    D5["clawlite/config/schema.py"]
    D6["clawlite/core/engine.py"]
    D7["clawlite/core/memory.py"]
    D8["clawlite/core/memory_backend.py"]
    D9["clawlite/core/memory_monitor.py"]
    D10["clawlite/core/prompt.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_server.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    N0 -->|imports| D4
    N0 -->|imports| D5
    N0 -->|imports| D6
    N0 -->|imports| D7
    N0 -->|imports| D8
    N0 -->|imports| D9
    N0 -->|imports| D10
    R1 -->|uses| N0
    R2 -->|uses| N0
```
