# CONNECTIONS clawlite/core/memory_artifacts.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/core/memory_layers.py`

## Reverse Dependencies

- `clawlite/core/memory.py`
- `tests/core/test_memory_artifacts.py`

## Matching Tests

- `tests/core/test_memory.py`
- `tests/core/test_memory_artifacts.py`

## Mermaid

```mermaid
flowchart TD
    N0["memory_artifacts.py"]
    D1["clawlite/core/memory_layers.py"]
    R1["clawlite/core/memory.py"]
    R2["tests/core/test_memory_artifacts.py"]
    T1["tests/core/test_memory.py"]
    T2["tests/core/test_memory_artifacts.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
