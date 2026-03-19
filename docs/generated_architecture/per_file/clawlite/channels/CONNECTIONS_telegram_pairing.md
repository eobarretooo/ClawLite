# CONNECTIONS clawlite/channels/telegram_pairing.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/channels/telegram.py`
- `clawlite/cli/ops.py`
- `tests/cli/test_commands.py`

## Matching Tests

- `tests/channels/test_telegram.py`

## Mermaid

```mermaid
flowchart TD
    N0["telegram_pairing.py"]
    R1["clawlite/channels/telegram.py"]
    R2["clawlite/cli/ops.py"]
    R3["tests/cli/test_commands.py"]
    T1["tests/channels/test_telegram.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
```
