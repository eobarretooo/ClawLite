# CONNECTIONS clawlite/gateway/subagents_runtime.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_subagents_runtime.py`

## Matching Tests

- `tests/core/test_subagent.py`
- `tests/gateway/test_subagents_runtime.py`

## Mermaid

```mermaid
flowchart TD
    N0["subagents_runtime.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_subagents_runtime.py"]
    T1["tests/core/test_subagent.py"]
    T2["tests/gateway/test_subagents_runtime.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
