# CONNECTIONS clawlite/bus/journal.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/bus/events.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/bus/test_journal.py`

## Matching Tests

- `tests/bus/test_journal.py`
- `tests/jobs/test_journal.py`

## Mermaid

```mermaid
flowchart TD
    N0["journal.py"]
    D1["clawlite/bus/events.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/bus/test_journal.py"]
    T1["tests/bus/test_journal.py"]
    T2["tests/jobs/test_journal.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
