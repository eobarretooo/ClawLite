# CONNECTIONS clawlite/core/runestone.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 5 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/channels/base.py`
- `clawlite/core/injection_guard.py`
- `clawlite/gateway/server.py`
- `clawlite/tools/exec.py`
- `tests/core/test_runestone.py`

## Matching Tests

- `tests/core/test_runestone.py`

## Mermaid

```mermaid
flowchart TD
    N0["runestone.py"]
    R1["clawlite/channels/base.py"]
    R2["clawlite/core/injection_guard.py"]
    R3["clawlite/gateway/server.py"]
    R4["clawlite/tools/exec.py"]
    R5["tests/core/test_runestone.py"]
    T1["tests/core/test_runestone.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    T1 -->|tests| N0
```
