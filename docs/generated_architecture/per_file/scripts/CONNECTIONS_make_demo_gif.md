# CONNECTIONS scripts/make_demo_gif.py

## Relationship Summary

- Imports 3 internal file(s).
- Imported by 1 internal file(s).
- Matched test files: 1.

## Internal Imports

- `scripts/assemble_gif.py`
- `scripts/capture_frames.py`
- `scripts/terminal_template.py`

## Reverse Dependencies

- `tests/scripts/test_make_demo_gif.py`

## Matching Tests

- `tests/scripts/test_make_demo_gif.py`

## Mermaid

```mermaid
flowchart TD
    N0["make_demo_gif.py"]
    D1["scripts/assemble_gif.py"]
    D2["scripts/capture_frames.py"]
    D3["scripts/terminal_template.py"]
    R1["tests/scripts/test_make_demo_gif.py"]
    T1["tests/scripts/test_make_demo_gif.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    R1 -->|uses| N0
    T1 -->|tests| N0
```
