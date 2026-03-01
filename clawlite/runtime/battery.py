from __future__ import annotations

from typing import Any

from clawlite.config.settings import load_config, save_config

DEFAULT_BATTERY_MODE = {
    "enabled": False,
    "throttle_seconds": 6.0,
}


def _parse_positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


def get_battery_mode(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    source = cfg if cfg is not None else load_config()
    raw = source.get("battery_mode", {})
    return {
        "enabled": bool(raw.get("enabled", DEFAULT_BATTERY_MODE["enabled"])),
        "throttle_seconds": _parse_positive_float(
            raw.get("throttle_seconds", DEFAULT_BATTERY_MODE["throttle_seconds"]),
            DEFAULT_BATTERY_MODE["throttle_seconds"],
        ),
    }


def set_battery_mode(enabled: bool | None = None, throttle_seconds: float | None = None) -> dict[str, Any]:
    cfg = load_config()
    cfg.setdefault("battery_mode", {})

    if enabled is not None:
        cfg["battery_mode"]["enabled"] = bool(enabled)
    if throttle_seconds is not None:
        cfg["battery_mode"]["throttle_seconds"] = _parse_positive_float(
            throttle_seconds,
            DEFAULT_BATTERY_MODE["throttle_seconds"],
        )

    save_config(cfg)
    return get_battery_mode(cfg)


def effective_poll_seconds(base_seconds: float, cfg: dict[str, Any] | None = None) -> float:
    base = _parse_positive_float(base_seconds, 1.0)
    mode = get_battery_mode(cfg)
    if not mode["enabled"]:
        return base
    return max(base, float(mode["throttle_seconds"]))
