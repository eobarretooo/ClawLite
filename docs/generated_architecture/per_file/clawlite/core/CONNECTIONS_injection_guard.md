# CONNECTIONS clawlite/core/injection_guard.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 4 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/core/runestone.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/channels/base.py`
- `clawlite/core/engine.py`
- `clawlite/core/prompt.py`
- `tests/core/test_injection_guard.py`

## Matching Tests

- `tests/core/test_injection_guard.py`

## Mermaid

```mermaid
flowchart TD
    N0["injection_guard.py"]
    D1["clawlite/core/runestone.py"]
    D2["clawlite/utils/logging.py"]
    R1["clawlite/channels/base.py"]
    R2["clawlite/core/engine.py"]
    R3["clawlite/core/prompt.py"]
    R4["tests/core/test_injection_guard.py"]
    T1["tests/core/test_injection_guard.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    T1 -->|tests| N0
```
