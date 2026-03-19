# CONNECTIONS clawlite/channels/telegram_offset_store.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `clawlite/channels/telegram.py`
- `clawlite/channels/telegram_offset_runtime.py`
- `tests/channels/test_telegram.py`

## Matching Tests

- `tests/channels/test_telegram.py`
- `tests/session/test_store.py`

## Mermaid

```mermaid
flowchart TD
    N0["telegram_offset_store.py"]
    R1["clawlite/channels/telegram.py"]
    R2["clawlite/channels/telegram_offset_runtime.py"]
    R3["tests/channels/test_telegram.py"]
    T1["tests/channels/test_telegram.py"]
    T2["tests/session/test_store.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
