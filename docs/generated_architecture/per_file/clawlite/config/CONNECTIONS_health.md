# CONNECTIONS clawlite/config/health.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/config/schema.py`

## Reverse Dependencies

- `clawlite/gateway/status_handlers.py`
- `tests/config/test_health.py`

## Matching Tests

- `tests/config/test_health.py`
- `tests/tools/test_health_check.py`

## Mermaid

```mermaid
flowchart TD
    N0["health.py"]
    D1["clawlite/config/schema.py"]
    R1["clawlite/gateway/status_handlers.py"]
    R2["tests/config/test_health.py"]
    T1["tests/config/test_health.py"]
    T2["tests/tools/test_health_check.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
