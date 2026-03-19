# CONNECTIONS clawlite/providers/__init__.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 4 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/providers/base.py`
- `clawlite/providers/registry.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `clawlite/gateway/server.py`
- `tests/providers/test_registry_auth_resolution.py`
- `tests/providers/test_reliability.py`

## Matching Tests

- `tests/jobs/__init__.py`
- `tests/skills/__init__.py`

## Mermaid

```mermaid
flowchart TD
    N0["__init__.py"]
    D1["clawlite/providers/base.py"]
    D2["clawlite/providers/registry.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["clawlite/gateway/server.py"]
    R3["tests/providers/test_registry_auth_resolution.py"]
    R4["tests/providers/test_reliability.py"]
    T1["tests/jobs/__init__.py"]
    T2["tests/skills/__init__.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
