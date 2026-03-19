# CONNECTIONS clawlite/gateway/tool_catalog.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 1 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/gateway/server.py`

## Matching Tests

- `tests/providers/test_catalog.py`

## Mermaid

```mermaid
flowchart TD
    N0["tool_catalog.py"]
    R1["clawlite/gateway/server.py"]
    T1["tests/providers/test_catalog.py"]
    R1 -->|uses| N0
    T1 -->|tests| N0
```
