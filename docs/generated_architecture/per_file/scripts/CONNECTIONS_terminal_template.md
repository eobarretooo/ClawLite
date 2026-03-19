# CONNECTIONS scripts/terminal_template.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 4 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `scripts/capture_frames.py`
- `scripts/make_demo_gif.py`
- `tests/scripts/test_capture_frames.py`
- `tests/scripts/test_terminal_template.py`

## Matching Tests

- `tests/scripts/test_terminal_template.py`

## Mermaid

```mermaid
flowchart TD
    N0["terminal_template.py"]
    R1["scripts/capture_frames.py"]
    R2["scripts/make_demo_gif.py"]
    R3["tests/scripts/test_capture_frames.py"]
    R4["tests/scripts/test_terminal_template.py"]
    T1["tests/scripts/test_terminal_template.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    T1 -->|tests| N0
```
