# CONNECTIONS clawlite/workspace/__init__.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 0 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/workspace/bootstrap.py`
- `clawlite/workspace/loader.py`

## Matching Tests

- `tests/jobs/__init__.py`
- `tests/skills/__init__.py`

## Mermaid

```mermaid
flowchart TD
    N0["__init__.py"]
    D1["clawlite/workspace/bootstrap.py"]
    D2["clawlite/workspace/loader.py"]
    T1["tests/jobs/__init__.py"]
    T2["tests/skills/__init__.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    T1 -->|tests| N0
    T2 -->|tests| N0
```
