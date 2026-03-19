# CONNECTIONS clawlite/config/watcher.py

## Relationship Summary

- Imports 4 internal file(s).
- Imported by 1 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/bus/__init__.py`
- `clawlite/bus/events.py`
- `clawlite/config/loader.py`
- `clawlite/config/schema.py`

## Reverse Dependencies

- `tests/config/test_watcher.py`

## Matching Tests

- `tests/config/test_watcher.py`

## Mermaid

```mermaid
flowchart TD
    N0["watcher.py"]
    D1["clawlite/bus/__init__.py"]
    D2["clawlite/bus/events.py"]
    D3["clawlite/config/loader.py"]
    D4["clawlite/config/schema.py"]
    R1["tests/config/test_watcher.py"]
    T1["tests/config/test_watcher.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    N0 -->|imports| D4
    R1 -->|uses| N0
    T1 -->|tests| N0
```
