# CONNECTIONS clawlite/core/skills.py

## Relationship Summary

- Imports 1 internal file(s).
- Imported by 8 internal file(s).
- Matched test files: 3.

## Internal Imports

- `clawlite/config/loader.py`

## Reverse Dependencies

- `clawlite/cli/commands.py`
- `clawlite/core/engine.py`
- `clawlite/gateway/runtime_builder.py`
- `clawlite/tools/skill.py`
- `tests/cli/test_commands.py`
- `tests/core/test_skills.py`
- `tests/skills/test_markdown_skills.py`
- `tests/tools/test_skill_tool.py`

## Matching Tests

- `tests/core/test_skills.py`
- `tests/core/test_skills_new.py`
- `tests/skills/test_markdown_skills.py`

## Mermaid

```mermaid
flowchart TD
    N0["skills.py"]
    D1["clawlite/config/loader.py"]
    R1["clawlite/cli/commands.py"]
    R2["clawlite/core/engine.py"]
    R3["clawlite/gateway/runtime_builder.py"]
    R4["clawlite/tools/skill.py"]
    R5["tests/cli/test_commands.py"]
    R6["tests/core/test_skills.py"]
    R7["tests/skills/test_markdown_skills.py"]
    R8["tests/tools/test_skill_tool.py"]
    T1["tests/core/test_skills.py"]
    T2["tests/core/test_skills_new.py"]
    T3["tests/skills/test_markdown_skills.py"]
    N0 -->|imports| D1
    R1 -->|uses| N0
    R2 -->|uses| N0
    R3 -->|uses| N0
    R4 -->|uses| N0
    R5 -->|uses| N0
    R6 -->|uses| N0
    R7 -->|uses| N0
    R8 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
    T3 -->|tests| N0
```
