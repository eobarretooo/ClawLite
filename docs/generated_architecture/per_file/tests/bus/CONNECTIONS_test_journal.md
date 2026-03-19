# CONNECTIONS tests/bus/test_journal.py

## Relationship Summary

- Imports 3 internal file(s).
- Imported by 0 internal file(s).
- Matched test files: 0.

## Internal Imports

- `clawlite/bus/events.py`
- `clawlite/bus/journal.py`
- `clawlite/bus/queue.py`

## Candidate Sources Exercised By This Test File

- `clawlite/bus/journal.py`
- `clawlite/jobs/journal.py`

## Mermaid

```mermaid
flowchart TD
    N0["test_journal.py"]
    D1["clawlite/bus/events.py"]
    D2["clawlite/bus/journal.py"]
    D3["clawlite/bus/queue.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
```
