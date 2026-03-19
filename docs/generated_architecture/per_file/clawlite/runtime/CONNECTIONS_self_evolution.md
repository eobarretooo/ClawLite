# CONNECTIONS clawlite/runtime/self_evolution.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/runtime/test_self_evolution.py`

## Matching Tests

- `tests/gateway/test_self_evolution_approval.py`
- `tests/runtime/test_self_evolution.py`

## Mermaid

```mermaid
flowchart TD
    N0["self_evolution.py"]
    D1["clawlite/utils/logging.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/runtime/test_self_evolution.py"]
    T1["tests/gateway/test_self_evolution_approval.py"]
    T2["tests/runtime/test_self_evolution.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
