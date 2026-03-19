# CONNECTIONS clawlite/tools/sessions.py

## Relationship Summary

- Imports 3 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/core/subagent.py`
- `clawlite/session/store.py`
- `clawlite/tools/base.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `clawlite/tools/agents.py`
- `tests/tools/test_sessions_tools.py`

## Matching Tests

- `tests/tools/test_sessions_tools.py`
- `tests/tools/test_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["sessions.py"]
    D1["clawlite/core/subagent.py"]
    D2["clawlite/session/store.py"]
    D3["clawlite/tools/base.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["clawlite/tools/agents.py"]
    R3["tests/tools/test_sessions_tools.py"]
    T1["tests/tools/test_sessions_tools.py"]
    T2["tests/tools/test_tools.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
