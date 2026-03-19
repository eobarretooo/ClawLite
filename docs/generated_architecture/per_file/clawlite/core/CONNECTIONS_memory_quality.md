# CONNECTIONS clawlite/core/memory_quality.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `clawlite/core/memory.py`
- `tests/core/test_memory_quality.py`

## Matching Tests

- `tests/core/test_memory.py`
- `tests/core/test_memory_quality.py`

## Mermaid

```mermaid
flowchart TD
    N0["memory_quality.py"]
    R1["clawlite/core/memory.py"]
    R2["tests/core/test_memory_quality.py"]
    T1["tests/core/test_memory.py"]
    T2["tests/core/test_memory_quality.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
