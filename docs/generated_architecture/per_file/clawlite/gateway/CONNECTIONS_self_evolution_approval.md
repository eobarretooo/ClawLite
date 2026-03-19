# CONNECTIONS clawlite/gateway/self_evolution_approval.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/bus/events.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/gateway/test_self_evolution_approval.py`

## Matching Tests

- `tests/gateway/test_self_evolution_approval.py`
- `tests/runtime/test_self_evolution.py`

## Mermaid

```mermaid
flowchart TD
    N0["self_evolution_approval.py"]
    D1["clawlite/bus/events.py"]
    D2["clawlite/utils/logging.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/gateway/test_self_evolution_approval.py"]
    T1["tests/gateway/test_self_evolution_approval.py"]
    T2["tests/runtime/test_self_evolution.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
