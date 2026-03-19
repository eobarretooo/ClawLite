# CONNECTIONS clawlite/tools/browser.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/tools/base.py`
- `clawlite/tools/web.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/tools/test_browser_tool.py`
- `tests/tools/test_tools.py`

## Matching Tests

- `tests/tools/test_browser_tool.py`
- `tests/tools/test_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["browser.py"]
    D1["clawlite/tools/base.py"]
    D2["clawlite/tools/web.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/tools/test_browser_tool.py"]
    R3["tests/tools/test_tools.py"]
    T1["tests/tools/test_browser_tool.py"]
    T2["tests/tools/test_tools.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
