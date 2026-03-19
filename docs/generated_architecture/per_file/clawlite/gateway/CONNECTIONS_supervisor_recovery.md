# CONNECTIONS clawlite/gateway/supervisor_recovery.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_supervisor_recovery.py`

## Matching Tests

- `tests/gateway/test_supervisor_recovery.py`
- `tests/runtime/test_supervisor.py`

## Mermaid

```mermaid
flowchart TD
    N0["supervisor_recovery.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_supervisor_recovery.py"]
    T1["tests/gateway/test_supervisor_recovery.py"]
    T2["tests/runtime/test_supervisor.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
