# CONNECTIONS clawlite/runtime/gjallarhorn.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/runtime/test_gjallarhorn.py`

## Matching Tests

- `tests/runtime/test_gjallarhorn.py`

## Mermaid

```mermaid
flowchart TD
    N0["gjallarhorn.py"]
    D1["clawlite/utils/logging.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/runtime/test_gjallarhorn.py"]
    T1["tests/runtime/test_gjallarhorn.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
