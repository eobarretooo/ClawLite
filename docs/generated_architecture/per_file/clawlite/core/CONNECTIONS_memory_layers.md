# CONNECTIONS clawlite/core/memory_layers.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 4 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/core/memory_yggdrasil.py`

## Reverse Dependencies

- `clawlite/core/memory.py`
- `clawlite/core/memory_artifacts.py`
- `clawlite/core/memory_prune.py`
- `tests/core/test_memory_layers.py`

## Matching Tests

- `tests/core/test_memory.py`
- `tests/core/test_memory_layers.py`

## Mermaid

```mermaid
flowchart TD
    N0["memory_layers.py"]
    D1["clawlite/core/memory_yggdrasil.py"]
    R1["clawlite/core/memory.py"]
    R2["clawlite/core/memory_artifacts.py"]
    R3["clawlite/core/memory_prune.py"]
    R4["tests/core/test_memory_layers.py"]
    T1["tests/core/test_memory.py"]
    T2["tests/core/test_memory_layers.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
