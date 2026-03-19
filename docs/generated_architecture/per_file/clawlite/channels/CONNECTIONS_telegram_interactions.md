# CONNECTIONS clawlite/channels/telegram_interactions.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `clawlite/channels/telegram.py`
- `tests/channels/test_telegram_interactions.py`

## Matching Tests

- `tests/channels/test_telegram.py`
- `tests/channels/test_telegram_interactions.py`

## Mermaid

```mermaid
flowchart TD
    N0["telegram_interactions.py"]
    R1["clawlite/channels/telegram.py"]
    R2["tests/channels/test_telegram_interactions.py"]
    T1["tests/channels/test_telegram.py"]
    T2["tests/channels/test_telegram_interactions.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
