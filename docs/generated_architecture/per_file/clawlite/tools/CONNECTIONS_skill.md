# CONNECTIONS clawlite/tools/skill.py

## Relationship Summary

- Imports 7 internal file(s).
- Imported by 3 internal file(s).
- Matched test files: 6.

## Internal Imports

- `clawlite/cli/ops.py`
- `clawlite/config/loader.py`
- `clawlite/core/skills.py`
- `clawlite/session/store.py`
- `clawlite/tools/base.py`
- `clawlite/tools/registry.py`
- `clawlite/utils/logging.py`

## Reverse Dependencies

- `clawlite/gateway/runtime_builder.py`
- `clawlite/tools/__init__.py`
- `tests/tools/test_skill_tool.py`

## Matching Tests

- `tests/core/test_skills.py`
- `tests/core/test_skills_new.py`
- `tests/skills/test_markdown_skills.py`
- `tests/skills/test_skill_creator.py`
- `tests/tools/test_skill_tool.py`
- `tests/tools/test_tools.py`

## Mermaid

```mermaid
flowchart TD
    N0["skill.py"]
    D1["clawlite/cli/ops.py"]
    D2["clawlite/config/loader.py"]
    D3["clawlite/core/skills.py"]
    D4["clawlite/session/store.py"]
    D5["clawlite/tools/base.py"]
    D6["clawlite/tools/registry.py"]
    D7["clawlite/utils/logging.py"]
    R1["clawlite/gateway/runtime_builder.py"]
    R2["clawlite/tools/__init__.py"]
    R3["tests/tools/test_skill_tool.py"]
    T1["tests/core/test_skills.py"]
    T2["tests/core/test_skills_new.py"]
    T3["tests/skills/test_markdown_skills.py"]
    T4["tests/skills/test_skill_creator.py"]
    T5["tests/tools/test_skill_tool.py"]
    T6["tests/tools/test_tools.py"]
    N0 -->|imports| D1
    N0 -->|imports| D2
    N0 -->|imports| D3
    N0 -->|imports| D4
    N0 -->|imports| D5
    N0 -->|imports| D6
    N0 -->|imports| D7
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
    T4 -->|tests| N0
    T5 -->|tests| N0
    T6 -->|tests| N0
```
