# CONNECTIONS clawlite/channels/__init__.py

## Relationship Summary

- Imports 3 internal file(s).
- Imported by 0 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/channels/base.py`
- `clawlite/channels/manager.py`
- `clawlite/channels/telegram.py`

## Matching Tests

- `tests/jobs/__init__.py`
- `tests/skills/__init__.py`

## Mermaid

```mermaid
flowchart TD
    N0["__init__.py"]
    D1["clawlite/channels/base.py"]
    D2["clawlite/channels/manager.py"]
    D3["clawlite/channels/telegram.py"]
    T1["tests/jobs/__init__.py"]
    T2["tests/skills/__init__.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    T1 -->|tests| N0
    T2 -->|tests| N0
```
