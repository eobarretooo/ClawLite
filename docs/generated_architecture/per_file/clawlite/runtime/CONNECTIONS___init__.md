# CONNECTIONS clawlite/runtime/__init__.py

## Relationship Summary

- Imports 4 internal file(s).
- Imported by 4 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/runtime/autonomy.py`
- `clawlite/runtime/autonomy_actions.py`
- `clawlite/runtime/autonomy_log.py`
- `clawlite/runtime/supervisor.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `clawlite/gateway/server.py`
- `tests/gateway/test_supervisor_recovery.py`
- `tests/gateway/test_supervisor_runtime.py`

## Matching Tests

- `tests/jobs/__init__.py`
- `tests/skills/__init__.py`

## Mermaid

```mermaid
flowchart TD
    N0["__init__.py"]
    D1["clawlite/runtime/autonomy.py"]
    D2["clawlite/runtime/autonomy_actions.py"]
    D3["clawlite/runtime/autonomy_log.py"]
    D4["clawlite/runtime/supervisor.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["clawlite/gateway/server.py"]
    R3["tests/gateway/test_supervisor_recovery.py"]
    R4["tests/gateway/test_supervisor_runtime.py"]
    T1["tests/jobs/__init__.py"]
    T2["tests/skills/__init__.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    N0 -->|imports| D4
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
