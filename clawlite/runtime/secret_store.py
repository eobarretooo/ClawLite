from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_dotenv(path: str | None = None) -> dict[str, str]:
    env_path = Path(path or ".env")
    if not env_path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), out[k.strip()])
    return out


def load_vault_json(path: str | None = None) -> dict[str, Any]:
    """Suporte simples a vault local via arquivo JSON (MVP).

    Pode ser apontado por CLAWLITE_VAULT_FILE.
    """
    raw = path if path is not None else os.getenv("CLAWLITE_VAULT_FILE", "")
    if not raw:
        return {}
    p = Path(raw).expanduser()
    if not p.exists() or p.is_dir():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    for k, v in data.items():
        if isinstance(v, (str, int, float)):
            os.environ.setdefault(str(k), str(v))
    return data


def rotate_token_hint(name: str) -> str:
    return f"Rotacione o segredo '{name}' no provider e atualize .env/vault imediatamente."
