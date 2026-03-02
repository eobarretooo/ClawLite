from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from clawlite.config.schema import AppConfig

DEFAULT_CONFIG_PATH = Path.home() / ".clawlite" / "config.json"


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _read_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception as exc:
            raise RuntimeError("pyyaml is required for YAML config files") from exc
        loaded = yaml.safe_load(text) or {}
        if not isinstance(loaded, dict):
            raise RuntimeError("invalid config format: expected mapping")
        return dict(loaded)
    loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise RuntimeError("invalid config format: expected object")
    return dict(loaded)


def _env_overrides() -> dict[str, Any]:
    out: dict[str, Any] = {}
    model = os.getenv("CLAWLITE_MODEL", "").strip()
    if model:
        out["provider"] = {"model": model}
    workspace = os.getenv("CLAWLITE_WORKSPACE", "").strip()
    if workspace:
        out["workspace_path"] = workspace
    base_url = os.getenv("CLAWLITE_LITELLM_BASE_URL", "").strip()
    if base_url:
        out.setdefault("provider", {})["litellm_base_url"] = base_url
    api_key = os.getenv("CLAWLITE_LITELLM_API_KEY", "").strip()
    if api_key:
        out.setdefault("provider", {})["litellm_api_key"] = api_key
    host = os.getenv("CLAWLITE_GATEWAY_HOST", "").strip()
    if host:
        out.setdefault("gateway", {})["host"] = host
    port = os.getenv("CLAWLITE_GATEWAY_PORT", "").strip()
    if port:
        try:
            out.setdefault("gateway", {})["port"] = int(port)
        except ValueError:
            pass
    return out


def load_config(path: str | Path | None = None) -> AppConfig:
    target = Path(path) if path else DEFAULT_CONFIG_PATH
    file_cfg = _read_file(target)
    defaults = AppConfig().to_dict()
    merged = _deep_merge(defaults, file_cfg)
    merged = _deep_merge(merged, _env_overrides())
    return AppConfig.from_dict(merged)


def save_config(config: AppConfig, path: str | Path | None = None) -> Path:
    target = Path(path) if path else DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target
