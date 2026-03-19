# CONNECTIONS clawlite/channels/inbound_text.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/channels/base.py`
- `tests/channels/test_inbound_text.py`

## Matching Tests

- `tests/channels/test_inbound_text.py`

## Mermaid

```mermaid
flowchart TD
    N0["inbound_text.py"]
    R1["clawlite/channels/base.py"]
    R2["tests/channels/test_inbound_text.py"]
    T1["tests/channels/test_inbound_text.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
