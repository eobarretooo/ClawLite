from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
        raw = dict(data or {})
        provider = ProviderConfig(**dict(raw.get("provider") or {}))
        gateway = GatewayConfig(**dict(raw.get("gateway") or {}))
        scheduler = SchedulerConfig(**dict(raw.get("scheduler") or {}))
        channels = raw.get("channels")
        return cls(
            workspace_path=str(raw.get("workspace_path") or cls.workspace_path),
            state_path=str(raw.get("state_path") or cls.state_path),
            provider=provider,
            gateway=gateway,
            scheduler=scheduler,
            channels=dict(channels) if isinstance(channels, dict) else {},
        )
