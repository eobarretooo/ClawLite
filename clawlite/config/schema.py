from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    token: str = ""


@dataclass(slots=True)
class ProviderConfig:
    model: str = "gemini/gemini-2.5-flash"
    litellm_base_url: str = "https://api.openai.com/v1"
    litellm_api_key: str = ""


@dataclass(slots=True)
class SchedulerConfig:
    heartbeat_interval_seconds: int = 1800
    timezone: str = "UTC"


@dataclass(slots=True)
class AppConfig:
    workspace_path: str = str(Path.home() / ".clawlite" / "workspace")
    state_path: str = str(Path.home() / ".clawlite" / "state")
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    channels: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        def _pick(klass: type, payload: dict[str, Any]) -> dict[str, Any]:
            allowed = {item.name for item in fields(klass)}
            return {key: value for key, value in payload.items() if key in allowed}

        raw = dict(data or {})
        defaults = cls()
        provider = ProviderConfig(**_pick(ProviderConfig, dict(raw.get("provider") or {})))
        gateway = GatewayConfig(**_pick(GatewayConfig, dict(raw.get("gateway") or {})))
        scheduler = SchedulerConfig(**_pick(SchedulerConfig, dict(raw.get("scheduler") or {})))
        channels = raw.get("channels")
        return cls(
            workspace_path=str(raw.get("workspace_path") or defaults.workspace_path),
            state_path=str(raw.get("state_path") or defaults.state_path),
            provider=provider,
            gateway=gateway,
            scheduler=scheduler,
            channels=dict(channels) if isinstance(channels, dict) else {},
        )
