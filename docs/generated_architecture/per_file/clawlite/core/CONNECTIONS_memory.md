# CONNECTIONS clawlite/core/memory.py

## Relationship Summary

- Imports 22 internal file(s).
- Imported by 14 internal file(s).
- Matched test files: 30.

## Internal Imports

- `clawlite/core/memory_add.py`
- `clawlite/core/memory_api.py`
- `clawlite/core/memory_artifacts.py`
- `clawlite/core/memory_backend.py`
- `clawlite/core/memory_classification.py`
- `clawlite/core/memory_curation.py`
- `clawlite/core/memory_history.py`
- `clawlite/core/memory_ingest.py`
- `clawlite/core/memory_layers.py`
- `clawlite/core/memory_maintenance.py`
- `clawlite/core/memory_policy.py`
- `clawlite/core/memory_privacy.py`
- `clawlite/core/memory_profile.py`
- `clawlite/core/memory_prune.py`
- `clawlite/core/memory_quality.py`
- `clawlite/core/memory_reporting.py`
- `clawlite/core/memory_resources.py`
- `clawlite/core/memory_retrieval.py`
- `clawlite/core/memory_search.py`
- `clawlite/core/memory_versions.py`
- `clawlite/core/memory_workflows.py`
- `clawlite/core/memory_working_set.py`

## Reverse Dependencies

- `clawlite/cli/ops.py`
- `clawlite/core/engine.py`
- `clawlite/core/memory_monitor.py`
- `clawlite/gateway/runtime_builder.py`
- `clawlite/tools/memory.py`
- `tests/core/test_engine.py`
- `tests/core/test_memory.py`
- `tests/core/test_memory_curation.py`
- `tests/core/test_memory_ingest.py`
- `tests/core/test_memory_monitor.py`
- `tests/core/test_memory_resources.py`
- `tests/core/test_memory_ttl.py`
- `tests/gateway/test_server.py`
- `tests/tools/test_memory_tools.py`

## Matching Tests

- `tests/core/test_memory.py`
- `tests/core/test_memory_api.py`
- `tests/core/test_memory_artifacts.py`
- `tests/core/test_memory_backend.py`
- `tests/core/test_memory_classification.py`
- `tests/core/test_memory_consolidator.py`
- `tests/core/test_memory_curation.py`
- `tests/core/test_memory_history.py`
- `tests/core/test_memory_ingest.py`
- `tests/core/test_memory_ingest_helpers.py`
- `tests/core/test_memory_layers.py`
- `tests/core/test_memory_maintenance.py`
- `tests/core/test_memory_monitor.py`
- `tests/core/test_memory_policy.py`
- `tests/core/test_memory_privacy.py`
- `tests/core/test_memory_proactive.py`
- `tests/core/test_memory_profile.py`
- `tests/core/test_memory_prune.py`
- `tests/core/test_memory_quality.py`
- `tests/core/test_memory_reporting.py`
- `tests/core/test_memory_resources.py`
- `tests/core/test_memory_resources_helpers.py`
- `tests/core/test_memory_retrieval.py`
- `tests/core/test_memory_search.py`
- `tests/core/test_memory_ttl.py`
- `tests/core/test_memory_versions.py`
- `tests/core/test_memory_workflows.py`
- `tests/core/test_memory_working_set.py`
- `tests/gateway/test_memory_dashboard.py`
- `tests/tools/test_memory_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["memory.py"]
    D1["clawlite/core/memory_add.py"]
    D2["clawlite/core/memory_api.py"]
    D3["clawlite/core/memory_artifacts.py"]
    D4["clawlite/core/memory_backend.py"]
    D5["clawlite/core/memory_classification.py"]
    D6["clawlite/core/memory_curation.py"]
    D7["clawlite/core/memory_history.py"]
    D8["clawlite/core/memory_ingest.py"]
    D9["clawlite/core/memory_layers.py"]
    D10["clawlite/core/memory_maintenance.py"]
    R1["clawlite/cli/ops.py"]
    R2["clawlite/core/engine.py"]
    R3["clawlite/core/memory_monitor.py"]
    R4["clawlite/gateway/runtime_builder.py"]
    R5["clawlite/tools/memory.py"]
    R6["tests/core/test_engine.py"]
    R7["tests/core/test_memory.py"]
    R8["tests/core/test_memory_curation.py"]
    R9["tests/core/test_memory_ingest.py"]
    R10["tests/core/test_memory_monitor.py"]
    T1["tests/core/test_memory.py"]
    T2["tests/core/test_memory_api.py"]
    T3["tests/core/test_memory_artifacts.py"]
    T4["tests/core/test_memory_backend.py"]
    T5["tests/core/test_memory_classification.py"]
    T6["tests/core/test_memory_consolidator.py"]
    T7["tests/core/test_memory_curation.py"]
    T8["tests/core/test_memory_history.py"]
    T9["tests/core/test_memory_ingest.py"]
    T10["tests/core/test_memory_ingest_helpers.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    N0 -->|imports| D4
    N0 -->|imports| D5
    N0 -->|imports| D6
    N0 -->|imports| D7
    N0 -->|imports| D8
    N0 -->|imports| D9
    N0 -->|imports| D10
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    R6 -->|uses| N0
    R7 -->|uses| N0
    R8 -->|uses| N0
    R9 -->|uses| N0
    R10 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
    T4 -->|tests| N0
    T5 -->|tests| N0
    T6 -->|tests| N0
    T7 -->|tests| N0
    T8 -->|tests| N0
    T9 -->|tests| N0
    T10 -->|tests| N0
```
