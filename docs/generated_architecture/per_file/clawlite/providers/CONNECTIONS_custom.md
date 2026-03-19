# CONNECTIONS clawlite/providers/custom.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 1 internal file(s).
- Matched test files: 0.

## Internal Imports

- `clawlite/providers/litellm.py`

## Reverse Dependencies

- `clawlite/providers/registry.py`

## Mermaid

```mermaid
flowchart TD
    N0["custom.py"]
    D1["clawlite/providers/litellm.py"]
    R1["clawlite/providers/registry.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
```
