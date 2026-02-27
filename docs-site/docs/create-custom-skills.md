# Create Custom Skills

A skill consists of:

- `skills/<skill-name>/SKILL.md`
- `clawlite/skills/<skill_name>.py`

Example:

```python
from __future__ import annotations

def run(command: str = "") -> str:
    if not command:
        return "my-skill ready"
    return "done"
```

Then register it in `clawlite/skills/registry.py`.
