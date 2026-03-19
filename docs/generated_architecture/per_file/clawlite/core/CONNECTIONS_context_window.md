# CONNECTIONS clawlite/core/context_window.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/core/engine.py`
- `tests/core/test_context_window.py`

## Matching Tests

- `tests/core/test_context_window.py`

## Mermaid

```mermaid
flowchart TD
    N0["context_window.py"]
    R1["clawlite/core/engine.py"]
    R2["tests/core/test_context_window.py"]
    T1["tests/core/test_context_window.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
