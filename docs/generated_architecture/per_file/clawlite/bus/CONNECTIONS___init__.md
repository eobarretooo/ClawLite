# CONNECTIONS clawlite/bus/__init__.py

## Relationship Summary

- Imports 3 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/bus/events.py`
- `clawlite/bus/queue.py`
- `clawlite/bus/redis_queue.py`

## Reverse Dependencies

- `clawlite/config/watcher.py`
- `clawlite/core/engine.py`

## Matching Tests

- `tests/jobs/__init__.py`
- `tests/skills/__init__.py`

## Mermaid

```mermaid
flowchart TD
    N0["__init__.py"]
    D1["clawlite/bus/events.py"]
    D2["clawlite/bus/queue.py"]
    D3["clawlite/bus/redis_queue.py"]
    R1["clawlite/config/watcher.py"]
    R2["clawlite/core/engine.py"]
    T1["tests/jobs/__init__.py"]
    T2["tests/skills/__init__.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
