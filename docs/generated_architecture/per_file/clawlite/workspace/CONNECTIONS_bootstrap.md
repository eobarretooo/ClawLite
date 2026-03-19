# CONNECTIONS clawlite/workspace/bootstrap.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 0.

## Internal Imports

- `clawlite/config/loader.py`
- `clawlite/workspace/loader.py`

## Reverse Dependencies

- `clawlite/workspace/__init__.py`
- `tests/workspace/test_workspace_loader.py`

## Mermaid

```mermaid
flowchart TD
    N0["bootstrap.py"]
    D1["clawlite/config/loader.py"]
    D2["clawlite/workspace/loader.py"]
    R1["clawlite/workspace/__init__.py"]
    R2["tests/workspace/test_workspace_loader.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
```
