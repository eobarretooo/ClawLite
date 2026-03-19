# CONNECTIONS clawlite/gateway/status_handlers.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/config/health.py`
- `clawlite/providers/telemetry.py`

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_status_handlers.py`

## Matching Tests

- `tests/gateway/test_status_handlers.py`

## Mermaid

```mermaid
flowchart TD
    N0["status_handlers.py"]
    D1["clawlite/config/health.py"]
    D2["clawlite/providers/telemetry.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_status_handlers.py"]
    T1["tests/gateway/test_status_handlers.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
