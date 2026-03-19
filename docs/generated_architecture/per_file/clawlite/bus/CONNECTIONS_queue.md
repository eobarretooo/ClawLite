# CONNECTIONS clawlite/bus/queue.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 8 internal file(s).
- Matched test files: 3.

## Internal Imports

- `clawlite/bus/events.py`

## Reverse Dependencies

- `clawlite/bus/__init__.py`
- `clawlite/bus/redis_queue.py`
- `clawlite/channels/manager.py`
- `clawlite/gateway/runtime_builder.py`
- `clawlite/gateway/server.py`
- `tests/bus/test_journal.py`
- `tests/bus/test_queue.py`
- `tests/channels/test_manager.py`

## Matching Tests

- `tests/bus/test_queue.py`
- `tests/bus/test_redis_queue.py`
- `tests/jobs/test_queue.py`

## Mermaid

```mermaid
flowchart TD
    N0["queue.py"]
    D1["clawlite/bus/events.py"]
    R1["clawlite/bus/__init__.py"]
    R2["clawlite/bus/redis_queue.py"]
    R3["clawlite/channels/manager.py"]
    R4["clawlite/gateway/runtime_builder.py"]
    R5["clawlite/gateway/server.py"]
    R6["tests/bus/test_journal.py"]
    R7["tests/bus/test_queue.py"]
    R8["tests/channels/test_manager.py"]
    T1["tests/bus/test_queue.py"]
    T2["tests/bus/test_redis_queue.py"]
    T3["tests/jobs/test_queue.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    R6 -->|uses| N0
    R7 -->|uses| N0
    R8 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
```
