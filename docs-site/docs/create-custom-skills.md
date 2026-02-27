# Create Custom Skills

Uma skill no ClawLite é simples e explícita.

## Estrutura

```text
skills/<nome-da-skill>/SKILL.md
clawlite/skills/<nome_da_skill>.py
```

## Exemplo de implementação

```python
from __future__ import annotations

SKILL_NAME = "my-skill"
SKILL_DESCRIPTION = "Executa uma automação personalizada"

def run(command: str = "") -> str:
    if not command:
        return f"{SKILL_NAME} pronta"
    return f"executado: {command}"
```

## Registrar a skill

No arquivo `clawlite/skills/registry.py`:

```python
SKILLS = {
  "my-skill": "clawlite.skills.my_skill:run"
}
```

## Boas práticas

- valide dependências externas antes de executar
- retorne erros curtos e acionáveis
- mantenha compatibilidade Linux + Termux
