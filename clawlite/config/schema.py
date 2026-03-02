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
class ProviderOverrideConfig:
    api_key: str = ""
    api_base: str = ""
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ProviderOverrideConfig:
        data = dict(raw or {})
        api_key = str(data.get("api_key", data.get("apiKey", "")) or "")
        api_base = str(data.get("api_base", data.get("apiBase", "")) or "")
        extra_headers_raw = data.get("extra_headers", data.get("extraHeaders", {}))
        extra_headers = dict(extra_headers_raw) if isinstance(extra_headers_raw, dict) else {}
        return cls(api_key=api_key, api_base=api_base, extra_headers=extra_headers)


@dataclass(slots=True)
class ProvidersConfig:
    openrouter: ProviderOverrideConfig = field(default_factory=ProviderOverrideConfig)
    gemini: ProviderOverrideConfig = field(default_factory=ProviderOverrideConfig)
    openai: ProviderOverrideConfig = field(default_factory=ProviderOverrideConfig)
    anthropic: ProviderOverrideConfig = field(default_factory=ProviderOverrideConfig)
    deepseek: ProviderOverrideConfig = field(default_factory=ProviderOverrideConfig)
    groq: ProviderOverrideConfig = field(default_factory=ProviderOverrideConfig)
    custom: ProviderOverrideConfig = field(default_factory=ProviderOverrideConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ProvidersConfig:
        data = dict(raw or {})
        return cls(
            openrouter=ProviderOverrideConfig.from_dict(dict(data.get("openrouter") or {})),
            gemini=ProviderOverrideConfig.from_dict(dict(data.get("gemini") or {})),
            openai=ProviderOverrideConfig.from_dict(dict(data.get("openai") or {})),
            anthropic=ProviderOverrideConfig.from_dict(dict(data.get("anthropic") or {})),
            deepseek=ProviderOverrideConfig.from_dict(dict(data.get("deepseek") or {})),
            groq=ProviderOverrideConfig.from_dict(dict(data.get("groq") or {})),
            custom=ProviderOverrideConfig.from_dict(dict(data.get("custom") or {})),
        )


@dataclass(slots=True)
class SchedulerConfig:
    heartbeat_interval_seconds: int = 1800
    timezone: str = "UTC"


@dataclass(slots=True)
class ChannelConfig:
    enabled: bool = False
    allow_from: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ChannelConfig:
        data = dict(raw or {})
        allow_raw = data.get("allow_from", data.get("allowFrom", []))
        allow_from = []
        if isinstance(allow_raw, list):
            allow_from = [str(item).strip() for item in allow_raw if str(item).strip()]
        return cls(
            enabled=bool(data.get("enabled", False)),
            allow_from=allow_from,
        )


@dataclass(slots=True)
class ExecToolConfig:
    path_append: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ExecToolConfig:
        data = dict(raw or {})
        if "pathAppend" in data:
            path_append = str(data.get("pathAppend", "") or "")
        else:
            path_append = str(data.get("path_append", "") or "")
        return cls(path_append=path_append)


@dataclass(slots=True)
class ToolsConfig:
    restrict_to_workspace: bool = False
    exec: ExecToolConfig = field(default_factory=ExecToolConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ToolsConfig:
        data = dict(raw or {})
        if "restrictToWorkspace" in data:
            restrict = bool(data.get("restrictToWorkspace", False))
        else:
            restrict = bool(data.get("restrict_to_workspace", False))
        exec_cfg = ExecToolConfig.from_dict(dict(data.get("exec") or {}))
        return cls(restrict_to_workspace=restrict, exec=exec_cfg)


@dataclass(slots=True)
class AppConfig:
    workspace_path: str = str(Path.home() / ".clawlite" / "workspace")
    state_path: str = str(Path.home() / ".clawlite" / "state")
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    providers: ProvidersConfig = field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    channels: dict[str, dict[str, Any]] = field(default_factory=dict)
    tools: ToolsConfig = field(default_factory=ToolsConfig)

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
        providers = ProvidersConfig.from_dict(dict(raw.get("providers") or {}))
        gateway = GatewayConfig(**_pick(GatewayConfig, dict(raw.get("gateway") or {})))
        scheduler = SchedulerConfig(**_pick(SchedulerConfig, dict(raw.get("scheduler") or {})))
        channels = raw.get("channels")
        tools = ToolsConfig.from_dict(dict(raw.get("tools") or {}))
        return cls(
            workspace_path=str(raw.get("workspace_path") or defaults.workspace_path),
            state_path=str(raw.get("state_path") or defaults.state_path),
            provider=provider,
            providers=providers,
            gateway=gateway,
            scheduler=scheduler,
            channels=dict(channels) if isinstance(channels, dict) else {},
            tools=tools,
        )
