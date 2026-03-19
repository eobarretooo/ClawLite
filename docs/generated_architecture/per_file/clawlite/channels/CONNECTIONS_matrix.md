# CONNECTIONS clawlite/channels/matrix.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 0.

## Internal Imports

- `clawlite/channels/base.py`

## Reverse Dependencies

- `clawlite/channels/manager.py`
- `tests/channels/test_outbound_adapters.py`

## Mermaid

```mermaid
flowchart TD
    N0["matrix.py"]
    D1["clawlite/channels/base.py"]
    R1["clawlite/channels/manager.py"]
    R2["tests/channels/test_outbound_adapters.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
```
