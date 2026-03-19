# CONNECTIONS clawlite/core/memory_backend.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `clawlite/core/memory.py`
- `clawlite/gateway/runtime_builder.py`
- `tests/core/test_memory_backend.py`

## Matching Tests

- `tests/core/test_memory.py`
- `tests/core/test_memory_backend.py`

## Mermaid

```mermaid
flowchart TD
    N0["memory_backend.py"]
    R1["clawlite/core/memory.py"]
    R2["clawlite/gateway/runtime_builder.py"]
    R3["tests/core/test_memory_backend.py"]
    T1["tests/core/test_memory.py"]
    T2["tests/core/test_memory_backend.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
