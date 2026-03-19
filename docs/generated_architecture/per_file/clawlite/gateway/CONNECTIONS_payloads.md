# CONNECTIONS clawlite/gateway/payloads.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/providers/hints.py`

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_payloads.py`

## Matching Tests

- `tests/gateway/test_payloads.py`

## Mermaid

```mermaid
flowchart TD
    N0["payloads.py"]
    D1["clawlite/providers/hints.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_payloads.py"]
    T1["tests/gateway/test_payloads.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
