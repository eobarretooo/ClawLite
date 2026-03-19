# CONNECTIONS clawlite/cli/__init__.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/cli/commands.py`

## Reverse Dependencies

- `clawlite/cli/__main__.py`
- `tests/cli/test_onboarding.py`

## Matching Tests

- `tests/jobs/__init__.py`
- `tests/skills/__init__.py`

## Mermaid

```mermaid
flowchart TD
    N0["__init__.py"]
    D1["clawlite/cli/commands.py"]
    R1["clawlite/cli/__main__.py"]
    R2["tests/cli/test_onboarding.py"]
    T1["tests/jobs/__init__.py"]
    T2["tests/skills/__init__.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
