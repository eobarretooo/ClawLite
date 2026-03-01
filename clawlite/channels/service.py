from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from clawlite.channels.manager import manager
from clawlite.config.settings import load_config


@dataclass(frozen=True)
class ConfiguredChannel:
    name: str
    enabled: bool
    has_token: bool
    accounts: int
    running_instances: int


def list_configured_channels() -> list[ConfiguredChannel]:
    cfg = load_config()
    channels_cfg = cfg.get("channels", {}) if isinstance(cfg.get("channels"), dict) else {}
    rows: list[ConfiguredChannel] = []
    for name in sorted(channels_cfg.keys()):
        raw = channels_cfg.get(name, {})
        if not isinstance(raw, dict):
            continue
        instances = 0
        prefix = f"{name}:"
        for key in manager.active_channels.keys():
            if key == name or key.startswith(prefix):
                instances += 1
        accounts = raw.get("accounts", [])
        rows.append(
            ConfiguredChannel(
                name=name,
                enabled=bool(raw.get("enabled", False)),
                has_token=bool(str(raw.get("token", "")).strip()),
                accounts=(len(accounts) if isinstance(accounts, list) else 0),
                running_instances=instances,
            )
        )
    return rows


def describe_running_channels(channel_name: str | None = None) -> list[dict[str, Any]]:
    return manager.describe_instances(channel_name=channel_name)


async def start_channel(channel_name: str) -> list[str]:
    cfg = load_config()
    return await manager.start_channel(channel_name, cfg=cfg)


async def stop_channel(channel_name: str) -> dict[str, Any]:
    return await manager.stop_channel(channel_name)


async def reconnect_channel(channel_name: str) -> dict[str, Any]:
    return await manager.reconnect_channel(channel_name)

