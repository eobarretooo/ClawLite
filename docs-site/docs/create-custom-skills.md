# Como criar skills customizadas

## Estrutura

```text
skills/<nome>/SKILL.md
clawlite/skills/<nome_modulo>.py
```

## Exemplo

```python
from __future__ import annotations

def run(command: str = "") -> str:
    if not command:
        return "skill pronta"
    return f"executado: {command}"
```

Registre em `clawlite/skills/registry.py`.
