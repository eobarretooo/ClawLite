# CONNECTIONS clawlite/gateway/websocket_handlers.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_websocket_handlers.py`

## Matching Tests

- `tests/gateway/test_websocket_handlers.py`
- `tests/tools/test_web.py`

## Mermaid

```mermaid
flowchart TD
    N0["websocket_handlers.py"]
    D1["clawlite/utils/logging.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_websocket_handlers.py"]
    T1["tests/gateway/test_websocket_handlers.py"]
    T2["tests/tools/test_web.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
