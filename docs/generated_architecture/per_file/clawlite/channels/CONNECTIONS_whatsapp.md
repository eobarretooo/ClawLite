# CONNECTIONS clawlite/channels/whatsapp.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/channels/base.py`

## Reverse Dependencies

- `clawlite/channels/manager.py`
- `tests/channels/test_outbound_adapters.py`
- `tests/channels/test_whatsapp.py`

## Matching Tests

- `tests/channels/test_whatsapp.py`

## Mermaid

```mermaid
flowchart TD
    N0["whatsapp.py"]
    D1["clawlite/channels/base.py"]
    R1["clawlite/channels/manager.py"]
    R2["tests/channels/test_outbound_adapters.py"]
    R3["tests/channels/test_whatsapp.py"]
    T1["tests/channels/test_whatsapp.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
```
