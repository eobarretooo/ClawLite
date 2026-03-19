# CONNECTIONS clawlite/bus/redis_queue.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 3.

## Internal Imports

- `clawlite/bus/events.py`
- `clawlite/bus/queue.py`

## Reverse Dependencies

- `clawlite/bus/__init__.py`
- `clawlite/gateway/runtime_builder.py`
- `tests/bus/test_redis_queue.py`

## Matching Tests

- `tests/bus/test_queue.py`
- `tests/bus/test_redis_queue.py`
- `tests/jobs/test_queue.py`

## Mermaid

```mermaid
flowchart TD
    N0["redis_queue.py"]
    D1["clawlite/bus/events.py"]
    D2["clawlite/bus/queue.py"]
    R1["clawlite/bus/__init__.py"]
    R2["clawlite/gateway/runtime_builder.py"]
    R3["tests/bus/test_redis_queue.py"]
    T1["tests/bus/test_queue.py"]
    T2["tests/bus/test_redis_queue.py"]
    T3["tests/jobs/test_queue.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
```
