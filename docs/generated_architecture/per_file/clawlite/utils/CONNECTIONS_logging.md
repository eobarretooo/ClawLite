# CONNECTIONS clawlite/utils/logging.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 27 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/utils/logger.py`

## Reverse Dependencies

- `clawlite/channels/base.py`
- `clawlite/channels/manager.py`
- `clawlite/core/engine.py`
- `clawlite/core/injection_guard.py`
- `clawlite/gateway/autonomy_notice.py`
- `clawlite/gateway/lifecycle_runtime.py`
- `clawlite/gateway/request_handlers.py`
- `clawlite/gateway/runtime_builder.py`
- `clawlite/gateway/self_evolution_approval.py`
- `clawlite/gateway/server.py`
- `clawlite/gateway/tool_approval.py`
- `clawlite/gateway/websocket_handlers.py`
- `clawlite/runtime/autonomy.py`
- `clawlite/runtime/gjallarhorn.py`
- `clawlite/runtime/self_evolution.py`
- `clawlite/runtime/supervisor.py`
- `clawlite/runtime/valkyrie.py`
- `clawlite/runtime/volva.py`
- `clawlite/scheduler/cron.py`
- `clawlite/scheduler/heartbeat.py`
- `clawlite/tools/exec.py`
- `clawlite/tools/files.py`
- `clawlite/tools/mcp.py`
- `clawlite/tools/skill.py`
- `clawlite/tools/web.py`
- `clawlite/utils/__init__.py`
- `tests/core/test_engine.py`

## Matching Tests

- `tests/utils/test_logging.py`

## Mermaid

```mermaid
flowchart TD
    N0["logging.py"]
    D1["clawlite/utils/logger.py"]
    R1["clawlite/channels/base.py"]
    R2["clawlite/channels/manager.py"]
    R3["clawlite/core/engine.py"]
    R4["clawlite/core/injection_guard.py"]
    R5["clawlite/gateway/autonomy_notice.py"]
    R6["clawlite/gateway/lifecycle_runtime.py"]
    R7["clawlite/gateway/request_handlers.py"]
    R8["clawlite/gateway/runtime_builder.py"]
    R9["clawlite/gateway/self_evolution_approval.py"]
    R10["clawlite/gateway/server.py"]
    T1["tests/utils/test_logging.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    R6 -->|uses| N0
    R7 -->|uses| N0
    R8 -->|uses| N0
    R9 -->|uses| N0
    R10 -->|uses| N0
    T1 -->|tests| N0
```
