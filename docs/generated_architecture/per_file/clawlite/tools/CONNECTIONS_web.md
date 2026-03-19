# CONNECTIONS clawlite/tools/web.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/tools/base.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `clawlite/tools/browser.py`
- `tests/tools/test_web.py`

## Matching Tests

- `tests/gateway/test_websocket_handlers.py`
- `tests/tools/test_web.py`

## Mermaid

```mermaid
flowchart TD
    N0["web.py"]
    D1["clawlite/tools/base.py"]
    D2["clawlite/utils/logging.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["clawlite/tools/browser.py"]
    R3["tests/tools/test_web.py"]
    T1["tests/gateway/test_websocket_handlers.py"]
    T2["tests/tools/test_web.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
