# CONNECTIONS clawlite/gateway/webhooks.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 1 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/gateway/server.py`

## Matching Tests

- `tests/tools/test_web.py`

## Mermaid

```mermaid
flowchart TD
    N0["webhooks.py"]
    R1["clawlite/gateway/server.py"]
    T1["tests/tools/test_web.py"]
    R1 -->|uses| N0
    T1 -->|tests| N0
```
