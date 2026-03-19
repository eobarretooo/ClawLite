# CONNECTIONS clawlite/gateway/lifecycle_runtime.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_lifecycle_runtime.py`

## Matching Tests

- `tests/gateway/test_lifecycle_runtime.py`

## Mermaid

```mermaid
flowchart TD
    N0["lifecycle_runtime.py"]
    D1["clawlite/utils/logging.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_lifecycle_runtime.py"]
    T1["tests/gateway/test_lifecycle_runtime.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
