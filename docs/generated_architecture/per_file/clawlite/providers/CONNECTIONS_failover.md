# CONNECTIONS clawlite/providers/failover.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/providers/base.py`
- `clawlite/providers/reliability.py`

## Reverse Dependencies

- `clawlite/providers/registry.py`
- `tests/providers/test_failover.py`
- `tests/providers/test_registry_auth_resolution.py`

## Matching Tests

- `tests/providers/test_failover.py`

## Mermaid

```mermaid
flowchart TD
    N0["failover.py"]
    D1["clawlite/providers/base.py"]
    D2["clawlite/providers/reliability.py"]
    R1["clawlite/providers/registry.py"]
    R2["tests/providers/test_failover.py"]
    R3["tests/providers/test_registry_auth_resolution.py"]
    T1["tests/providers/test_failover.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
```
