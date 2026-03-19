# CONNECTIONS clawlite/core/memory_monitor.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 7 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/core/memory.py`

## Reverse Dependencies

- `clawlite/cli/ops.py`
- `clawlite/gateway/autonomy_notice.py`
- `clawlite/gateway/control_handlers.py`
- `clawlite/gateway/runtime_builder.py`
- `clawlite/gateway/server.py`
- `tests/core/test_memory_monitor.py`
- `tests/gateway/test_server.py`

## Matching Tests

- `tests/core/test_memory.py`
- `tests/core/test_memory_monitor.py`

## Mermaid

```mermaid
flowchart TD
    N0["memory_monitor.py"]
    D1["clawlite/core/memory.py"]
    R1["clawlite/cli/ops.py"]
    R2["clawlite/gateway/autonomy_notice.py"]
    R3["clawlite/gateway/control_handlers.py"]
    R4["clawlite/gateway/runtime_builder.py"]
    R5["clawlite/gateway/server.py"]
    R6["tests/core/test_memory_monitor.py"]
    R7["tests/gateway/test_server.py"]
    T1["tests/core/test_memory.py"]
    T2["tests/core/test_memory_monitor.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    R6 -->|uses| N0
    R7 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
