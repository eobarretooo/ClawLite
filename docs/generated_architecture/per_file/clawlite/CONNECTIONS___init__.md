# CONNECTIONS clawlite/__init__.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 1 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `clawlite/cli/commands.py`

## Matching Tests

- `tests/jobs/__init__.py`
- `tests/skills/__init__.py`

## Mermaid

```mermaid
flowchart TD
    N0["__init__.py"]
    R1["clawlite/cli/commands.py"]
    T1["tests/jobs/__init__.py"]
    T2["tests/skills/__init__.py"]
    R1 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
