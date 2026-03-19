# CONNECTIONS clawlite/gateway/control_plane.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 1.

## Reverse Dependencies

- `clawlite/gateway/server.py`
- `tests/gateway/test_control_plane.py`

## Matching Tests

- `tests/gateway/test_control_plane.py`

## Mermaid

```mermaid
flowchart TD
    N0["control_plane.py"]
    R1["clawlite/gateway/server.py"]
    R2["tests/gateway/test_control_plane.py"]
    T1["tests/gateway/test_control_plane.py"]
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
```
