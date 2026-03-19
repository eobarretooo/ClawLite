# CONNECTIONS clawlite/core/prompt.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 4 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/core/injection_guard.py`
- `clawlite/workspace/loader.py`

## Reverse Dependencies

- `clawlite/core/engine.py`
- `clawlite/gateway/runtime_builder.py`
- `tests/core/test_engine.py`
- `tests/core/test_prompt.py`

## Matching Tests

- `tests/core/test_prompt.py`

## Mermaid

```mermaid
flowchart TD
    N0["prompt.py"]
    D1["clawlite/core/injection_guard.py"]
    D2["clawlite/workspace/loader.py"]
    R1["clawlite/core/engine.py"]
    R2["clawlite/gateway/runtime_builder.py"]
    R3["tests/core/test_engine.py"]
    R4["tests/core/test_prompt.py"]
    T1["tests/core/test_prompt.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    T1 -->|tests| N0
```
