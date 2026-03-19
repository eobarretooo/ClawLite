# CONNECTIONS clawlite/core/norns.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/core/test_norns.py`

## Matching Tests

- `tests/core/test_norns.py`

## Mermaid

```mermaid
flowchart TD
    N0["norns.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/core/test_norns.py"]
    T1["tests/core/test_norns.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
