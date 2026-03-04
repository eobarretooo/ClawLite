from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from clawlite.config.schema import AppConfig

DEFAULT_CONFIG_PATH = Path.home() / ".clawlite" / "config.json"


def _strict_mode_enabled() -> bool:
    raw = os.getenv("CLAWLITE_CONFIG_STRICT", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


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




def _migrate_config(raw: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(raw)

    tools = cfg.get("tools")
    if isinstance(tools, dict):
        tools = dict(tools)
        if "loopDetection" in tools and "loop_detection" not in tools:
            loop_detection = tools.get("loopDetection")
            tools["loop_detection"] = dict(loop_detection) if isinstance(loop_detection, dict) else {}
        cfg["tools"] = tools

    gateway = cfg.get("gateway")
    if isinstance(gateway, dict):
        gateway = dict(gateway)
        legacy_token = str(gateway.pop("token", "") or "").strip()
        if legacy_token:
            auth = dict(gateway.get("auth") or {})
            if not str(auth.get("token", "") or "").strip():
                auth["token"] = legacy_token
            if str(auth.get("mode", "") or "").strip().lower() not in {"required", "optional"}:
                auth["mode"] = "required"
            gateway["auth"] = auth
        cfg["gateway"] = gateway

    scheduler = cfg.get("scheduler")
    if isinstance(scheduler, dict):
        scheduler = dict(scheduler)
        interval = scheduler.get("heartbeat_interval_seconds")
        gateway = dict(cfg.get("gateway") or {})
        heartbeat = dict(gateway.get("heartbeat") or {})
        if interval is not None and "interval_s" not in heartbeat and "intervalS" not in heartbeat:
            heartbeat["interval_s"] = interval
            gateway["heartbeat"] = heartbeat
            cfg["gateway"] = gateway

    provider = cfg.get("provider")
    agents = dict(cfg.get("agents") or {})
    defaults = dict(agents.get("defaults") or {})
    if isinstance(provider, dict):
        model = str(provider.get("model", "") or "").strip()
        if model and "model" not in defaults:
            defaults["model"] = model
    if defaults:
        agents["defaults"] = defaults
        cfg["agents"] = agents

    return cfg


def _validate_config_keys(config: dict[str, Any]) -> None:
    template = AppConfig().to_dict()
    errors: list[str] = []

    def _walk(node: Any, ref: Any, path: str) -> None:
        if not isinstance(node, dict) or not isinstance(ref, dict):
            return

        for key, value in node.items():
            location = f"{path}.{key}" if path else key
            if key in ref:
                _walk(value, ref[key], location)
                continue

            if path == "channels" and isinstance(value, dict):
                continue
            if path == "tools.mcp.servers" and isinstance(value, dict):
                continue
            if path.endswith("extra_headers"):
                continue
            errors.append(location)

    _walk(config, template, "")
    if errors:
        formatted = ", ".join(sorted(errors))
        raise RuntimeError(f"invalid config keys: {formatted}")


def _env_overrides(*, include_model: bool = True) -> dict[str, Any]:
    bool_tokens = {"1", "true", "yes", "on", "0", "false", "no", "off"}

    def _parse_bool(value: str) -> bool | None:
        token = str(value or "").strip().lower()
        if token not in bool_tokens:
            return None
        return token in {"1", "true", "yes", "on"}

    out: dict[str, Any] = {}
    if include_model:
        model = os.getenv("CLAWLITE_MODEL", "").strip()
        if model:
            out["provider"] = {"model": model}
            out.setdefault("agents", {}).setdefault("defaults", {})["model"] = model
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

    auth_mode = os.getenv("CLAWLITE_GATEWAY_AUTH_MODE", "").strip().lower()
    if auth_mode in {"off", "optional", "required"}:
        out.setdefault("gateway", {}).setdefault("auth", {})["mode"] = auth_mode
    auth_token = os.getenv("CLAWLITE_GATEWAY_AUTH_TOKEN", "").strip()
    if not auth_token:
        auth_token = os.getenv("CLAWLITE_GATEWAY_TOKEN", "").strip()
    if auth_token:
        out.setdefault("gateway", {}).setdefault("auth", {})["token"] = auth_token
    auth_allow_loopback = _parse_bool(os.getenv("CLAWLITE_GATEWAY_AUTH_ALLOW_LOOPBACK", ""))
    if auth_allow_loopback is not None:
        out.setdefault("gateway", {}).setdefault("auth", {})["allow_loopback_without_auth"] = auth_allow_loopback

    diag_enabled = _parse_bool(os.getenv("CLAWLITE_GATEWAY_DIAGNOSTICS_ENABLED", ""))
    if diag_enabled is not None:
        out.setdefault("gateway", {}).setdefault("diagnostics", {})["enabled"] = diag_enabled
    diag_auth = _parse_bool(os.getenv("CLAWLITE_GATEWAY_DIAGNOSTICS_REQUIRE_AUTH", ""))
    if diag_auth is not None:
        out.setdefault("gateway", {}).setdefault("diagnostics", {})["require_auth"] = diag_auth
    diag_provider_telemetry = _parse_bool(os.getenv("CLAWLITE_GATEWAY_DIAGNOSTICS_INCLUDE_PROVIDER_TELEMETRY", ""))
    if diag_provider_telemetry is not None:
        out.setdefault("gateway", {}).setdefault("diagnostics", {})["include_provider_telemetry"] = diag_provider_telemetry
    return out


def load_config(path: str | Path | None = None, *, strict: bool | None = None) -> AppConfig:
    target = Path(path) if path else DEFAULT_CONFIG_PATH
    file_cfg = _migrate_config(_read_file(target))
    merged = _deep_merge(file_cfg, _env_overrides(include_model=path is None))
    strict_mode = strict if strict is not None else _strict_mode_enabled()
    if strict_mode:
        _validate_config_keys(merged)
    return AppConfig.from_dict(merged)


def save_config(config: AppConfig, path: str | Path | None = None) -> Path:
    target = Path(path) if path else DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target
