# CONNECTIONS clawlite/core/memory_consolidator.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 1 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `tests/core/test_memory_consolidator.py`

## Matching Tests

- `tests/core/test_memory.py`
- `tests/core/test_memory_consolidator.py`

## Mermaid

```mermaid
flowchart TD
    N0["memory_consolidator.py"]
    R1["tests/core/test_memory_consolidator.py"]
    T1["tests/core/test_memory.py"]
    T2["tests/core/test_memory_consolidator.py"]
    R1 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
