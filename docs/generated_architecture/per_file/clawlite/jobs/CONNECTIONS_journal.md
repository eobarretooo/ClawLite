# CONNECTIONS clawlite/jobs/journal.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/jobs/queue.py`

## Reverse Dependencies

- `clawlite/cli/commands.py`
- `clawlite/gateway/runtime_builder.py`
- `tests/jobs/test_journal.py`

## Matching Tests

- `tests/bus/test_journal.py`
- `tests/jobs/test_journal.py`

## Mermaid

```mermaid
flowchart TD
    N0["journal.py"]
    D1["clawlite/jobs/queue.py"]
    R1["clawlite/cli/commands.py"]
    R2["clawlite/gateway/runtime_builder.py"]
    R3["tests/jobs/test_journal.py"]
    T1["tests/bus/test_journal.py"]
    T2["tests/jobs/test_journal.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
