# CONNECTIONS clawlite/scheduler/heartbeat.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 5 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `clawlite/gateway/server.py`
- `clawlite/scheduler/__init__.py`
- `tests/gateway/test_server.py`
- `tests/scheduler/test_heartbeat.py`

## Matching Tests

- `tests/scheduler/test_heartbeat.py`

## Mermaid

```mermaid
flowchart TD
    N0["heartbeat.py"]
    D1["clawlite/utils/logging.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["clawlite/gateway/server.py"]
    R3["clawlite/scheduler/__init__.py"]
    R4["tests/gateway/test_server.py"]
    R5["tests/scheduler/test_heartbeat.py"]
    T1["tests/scheduler/test_heartbeat.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    T1 -->|tests| N0
```
