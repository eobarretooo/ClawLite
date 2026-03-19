# CONNECTIONS clawlite/providers/transcription.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Internal Imports

- `clawlite/providers/reliability.py`

## Reverse Dependencies

- `clawlite/channels/telegram.py`
- `tests/providers/test_transcription.py`

## Matching Tests

- `tests/providers/test_transcription.py`

## Mermaid

```mermaid
flowchart TD
    N0["transcription.py"]
    D1["clawlite/providers/reliability.py"]
    R1["clawlite/channels/telegram.py"]
    R2["tests/providers/test_transcription.py"]
    T1["tests/providers/test_transcription.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
