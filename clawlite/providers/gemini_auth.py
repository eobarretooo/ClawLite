from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _read_oauth_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_gemini_auth_file(path: str | Path | None = None) -> dict[str, str]:
    raw_path = str(path or os.getenv("CLAWLITE_GEMINI_AUTH_PATH", "") or "").strip()
    candidates: list[Path] = []
    if raw_path:
        candidates.append(Path(raw_path).expanduser())
    candidates.append(Path.home() / ".gemini" / "oauth_creds.json")

    for candidate in candidates:
        payload = _read_oauth_payload(candidate)
        if not payload:
            continue
        tokens = payload.get("tokens")
        source_payload = tokens if isinstance(tokens, dict) else payload
        token = str(
            source_payload.get(
                "access_token",
                source_payload.get("accessToken", source_payload.get("token", "")),
            )
            or ""
        ).strip()
        account_id = str(
            source_payload.get(
                "account_id",
                source_payload.get("accountId", source_payload.get("organization", "")),
            )
            or ""
        ).strip()
        if token:
            return {
                "access_token": token,
                "account_id": account_id,
                "source": f"file:{candidate}",
            }
    return {"access_token": "", "account_id": "", "source": ""}
