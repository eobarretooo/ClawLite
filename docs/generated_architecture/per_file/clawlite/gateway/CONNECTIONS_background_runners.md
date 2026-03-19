# CONNECTIONS clawlite/gateway/background_runners.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_background_runners.py`

## Matching Tests

- `tests/gateway/test_background_runners.py`

## Mermaid

```mermaid
flowchart TD
    N0["background_runners.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_background_runners.py"]
    T1["tests/gateway/test_background_runners.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
