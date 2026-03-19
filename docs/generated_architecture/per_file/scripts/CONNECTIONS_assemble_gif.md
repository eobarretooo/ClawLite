# CONNECTIONS scripts/assemble_gif.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `scripts/make_demo_gif.py`
- `tests/scripts/test_assemble_gif.py`

## Matching Tests

- `tests/scripts/test_assemble_gif.py`

## Mermaid

```mermaid
flowchart TD
    N0["assemble_gif.py"]
    R1["scripts/make_demo_gif.py"]
    R2["tests/scripts/test_assemble_gif.py"]
    T1["tests/scripts/test_assemble_gif.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
