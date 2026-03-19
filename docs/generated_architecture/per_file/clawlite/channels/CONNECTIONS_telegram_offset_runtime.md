# CONNECTIONS clawlite/channels/telegram_offset_runtime.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 1 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/channels/telegram_offset_store.py`

## Reverse Dependencies

- `clawlite/channels/telegram.py`

## Matching Tests

- `tests/channels/test_telegram.py`

## Mermaid

```mermaid
flowchart TD
    N0["telegram_offset_runtime.py"]
    D1["clawlite/channels/telegram_offset_store.py"]
    R1["clawlite/channels/telegram.py"]
    T1["tests/channels/test_telegram.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    T1 -->|tests| N0
```
