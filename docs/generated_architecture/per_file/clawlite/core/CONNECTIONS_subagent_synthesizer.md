# CONNECTIONS clawlite/core/subagent_synthesizer.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/core/engine.py`
- `tests/core/test_engine.py`

## Matching Tests

- `tests/core/test_subagent.py`

## Mermaid

```mermaid
flowchart TD
    N0["subagent_synthesizer.py"]
    R1["clawlite/core/engine.py"]
    R2["tests/core/test_engine.py"]
    T1["tests/core/test_subagent.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
