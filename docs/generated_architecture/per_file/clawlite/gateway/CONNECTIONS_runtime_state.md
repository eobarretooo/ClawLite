# CONNECTIONS clawlite/gateway/runtime_state.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_runtime_state.py`

## Matching Tests

- `tests/gateway/test_runtime_state.py`

## Mermaid

```mermaid
flowchart TD
    N0["runtime_state.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_runtime_state.py"]
    T1["tests/gateway/test_runtime_state.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
