# CONNECTIONS clawlite/skills/skill_creator.py

## Relationship Summary

- Imports 0 internal file(s).
- Imported by 1 internal file(s).
- Matched test files: 2.

## Reverse Dependencies

- `tests/skills/test_skill_creator.py`

## Matching Tests

- `tests/core/test_skills.py`
- `tests/skills/test_skill_creator.py`

## Mermaid

```mermaid
flowchart TD
    N0["skill_creator.py"]
    R1["tests/skills/test_skill_creator.py"]
    T1["tests/core/test_skills.py"]
    T2["tests/skills/test_skill_creator.py"]
    R1 -->|uses| N0
    T1 -->|tests| N0
    T2 -->|tests| N0
```
