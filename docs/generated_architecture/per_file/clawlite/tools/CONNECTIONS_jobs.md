# CONNECTIONS clawlite/tools/jobs.py

## Relationship Summary

- Imports 2 internal file(s).
- Imported by 2 internal file(s).
- Matched test files: 2.

## Internal Imports

- `clawlite/jobs/queue.py`
- `clawlite/tools/base.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `tests/tools/test_jobs_tool.py`

## Matching Tests

- `tests/tools/test_jobs_tool.py`
- `tests/tools/test_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["jobs.py"]
    D1["clawlite/jobs/queue.py"]
    D2["clawlite/tools/base.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["tests/tools/test_jobs_tool.py"]
    T1["tests/tools/test_jobs_tool.py"]
    T2["tests/tools/test_tools.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    R1 -->|uses| N0
    R2 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
