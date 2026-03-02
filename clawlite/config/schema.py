from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class GatewayHeartbeatConfig:
    enabled: bool = True
    interval_s: int = 1800

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> GatewayHeartbeatConfig:
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", True)),
            interval_s=max(5, int(data.get("interval_s", data.get("intervalS", 1800)) or 1800)),
        )


@dataclass(slots=True)
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    heartbeat: GatewayHeartbeatConfig = field(default_factory=GatewayHeartbeatConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> GatewayConfig:
        data = dict(raw or {})
        return cls(
            host=str(data.get("host", "127.0.0.1") or "127.0.0.1"),
            port=int(data.get("port", 8787) or 8787),
            heartbeat=GatewayHeartbeatConfig.from_dict(dict(data.get("heartbeat") or {})),
        )


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
class AgentDefaultsConfig:
    model: str = "gemini/gemini-2.5-flash"
    provider: str = "auto"
    max_tokens: int = 8192
    temperature: float = 0.1
    max_tool_iterations: int = 40
    memory_window: int = 100
    reasoning_effort: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> AgentDefaultsConfig:
        data = dict(raw or {})
        return cls(
            model=str(data.get("model", "gemini/gemini-2.5-flash") or "gemini/gemini-2.5-flash"),
            provider=str(data.get("provider", "auto") or "auto"),
            max_tokens=max(1, int(data.get("max_tokens", data.get("maxTokens", 8192)) or 8192)),
            temperature=float(data.get("temperature", 0.1) or 0.1),
            max_tool_iterations=max(1, int(data.get("max_tool_iterations", data.get("maxToolIterations", 40)) or 40)),
            memory_window=max(1, int(data.get("memory_window", data.get("memoryWindow", 100)) or 100)),
            reasoning_effort=(str(data.get("reasoning_effort", data.get("reasoningEffort", "")) or "").strip() or None),
        )


@dataclass(slots=True)
class AgentsConfig:
    defaults: AgentDefaultsConfig = field(default_factory=AgentDefaultsConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> AgentsConfig:
        data = dict(raw or {})
        return cls(defaults=AgentDefaultsConfig.from_dict(dict(data.get("defaults") or {})))


@dataclass(slots=True)
class SchedulerConfig:
    heartbeat_interval_seconds: int = 1800
    timezone: str = "UTC"


@dataclass(slots=True)
class BaseChannelConfig:
    enabled: bool = False
    allow_from: list[str] = field(default_factory=list)

    @classmethod
    def _allow_from(cls, data: dict[str, Any]) -> list[str]:
        allow_raw = data.get("allow_from")
        if (not allow_raw) and ("allowFrom" in data):
            allow_raw = data.get("allowFrom")
        if allow_raw is None:
            allow_raw = []
        if not isinstance(allow_raw, list):
            return []
        return [str(item).strip() for item in allow_raw if str(item).strip()]


@dataclass(slots=True)
class ChannelConfig(BaseChannelConfig):
    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ChannelConfig:
        data = dict(raw or {})
        return cls(enabled=bool(data.get("enabled", False)), allow_from=cls._allow_from(data))


@dataclass(slots=True)
class TelegramChannelConfig(BaseChannelConfig):
    token: str = ""
    poll_interval_s: float = 1.0
    poll_timeout_s: int = 20

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> TelegramChannelConfig:
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            allow_from=cls._allow_from(data),
            token=str(data.get("token", "") or ""),
            poll_interval_s=float(data.get("poll_interval_s", data.get("pollIntervalS", 1.0)) or 1.0),
            poll_timeout_s=int(data.get("poll_timeout_s", data.get("pollTimeoutS", 20)) or 20),
        )


@dataclass(slots=True)
class DiscordChannelConfig(BaseChannelConfig):
    token: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> DiscordChannelConfig:
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            allow_from=cls._allow_from(data),
            token=str(data.get("token", "") or ""),
        )


@dataclass(slots=True)
class SlackChannelConfig(BaseChannelConfig):
    bot_token: str = ""
    app_token: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SlackChannelConfig:
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            allow_from=cls._allow_from(data),
            bot_token=str(data.get("bot_token", data.get("botToken", "")) or ""),
            app_token=str(data.get("app_token", data.get("appToken", "")) or ""),
        )


@dataclass(slots=True)
class WhatsAppChannelConfig(BaseChannelConfig):
    bridge_url: str = "ws://localhost:3001"
    bridge_token: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> WhatsAppChannelConfig:
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            allow_from=cls._allow_from(data),
            bridge_url=str(data.get("bridge_url", data.get("bridgeUrl", "ws://localhost:3001")) or "ws://localhost:3001"),
            bridge_token=str(data.get("bridge_token", data.get("bridgeToken", "")) or ""),
        )


@dataclass(slots=True)
class ChannelsConfig:
    send_progress: bool = True
    send_tool_hints: bool = False
    telegram: TelegramChannelConfig = field(default_factory=TelegramChannelConfig)
    discord: DiscordChannelConfig = field(default_factory=DiscordChannelConfig)
    slack: SlackChannelConfig = field(default_factory=SlackChannelConfig)
    whatsapp: WhatsAppChannelConfig = field(default_factory=WhatsAppChannelConfig)
    extra: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ChannelsConfig:
        data = dict(raw or {})
        known = {"send_progress", "sendProgress", "send_tool_hints", "sendToolHints", "telegram", "discord", "slack", "whatsapp"}
        extra: dict[str, dict[str, Any]] = {}
        for key, value in data.items():
            if key in known:
                continue
            if isinstance(value, dict):
                extra[str(key)] = dict(value)
        return cls(
            send_progress=bool(data.get("send_progress", data.get("sendProgress", True))),
            send_tool_hints=bool(data.get("send_tool_hints", data.get("sendToolHints", False))),
            telegram=TelegramChannelConfig.from_dict(dict(data.get("telegram") or {})),
            discord=DiscordChannelConfig.from_dict(dict(data.get("discord") or {})),
            slack=SlackChannelConfig.from_dict(dict(data.get("slack") or {})),
            whatsapp=WhatsAppChannelConfig.from_dict(dict(data.get("whatsapp") or {})),
            extra=extra,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "send_progress": self.send_progress,
            "send_tool_hints": self.send_tool_hints,
            "telegram": asdict(self.telegram),
            "discord": asdict(self.discord),
            "slack": asdict(self.slack),
            "whatsapp": asdict(self.whatsapp),
        }
        for key, value in self.extra.items():
            out[key] = dict(value)
        return out

    def enabled_names(self) -> list[str]:
        rows: list[str] = []
        for name in ("telegram", "discord", "slack", "whatsapp"):
            payload = getattr(self, name)
            if bool(payload.enabled):
                rows.append(name)
        for name, payload in self.extra.items():
            if isinstance(payload, dict) and bool(payload.get("enabled", False)):
                rows.append(name)
        return sorted(rows)


@dataclass(slots=True)
class ExecToolConfig:
    timeout: int = 60
    path_append: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ExecToolConfig:
        data = dict(raw or {})
        timeout = int(data.get("timeout", 60) or 60)
        if "pathAppend" in data:
            path_append = str(data.get("pathAppend", "") or "")
        else:
            path_append = str(data.get("path_append", "") or "")
        return cls(timeout=max(1, timeout), path_append=path_append)


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
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    channels: ChannelsConfig = field(default_factory=ChannelsConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)

    def __post_init__(self) -> None:
        if isinstance(self.provider, dict):
            payload = dict(self.provider)
            self.provider = ProviderConfig(
                model=str(payload.get("model", "gemini/gemini-2.5-flash") or "gemini/gemini-2.5-flash"),
                litellm_base_url=str(payload.get("litellm_base_url", "https://api.openai.com/v1") or "https://api.openai.com/v1"),
                litellm_api_key=str(payload.get("litellm_api_key", "") or ""),
            )
        if isinstance(self.providers, dict):
            self.providers = ProvidersConfig.from_dict(self.providers)
        if isinstance(self.agents, dict):
            self.agents = AgentsConfig.from_dict(self.agents)
        if isinstance(self.gateway, dict):
            self.gateway = GatewayConfig.from_dict(self.gateway)
        if isinstance(self.scheduler, dict):
            scheduler_payload = dict(self.scheduler)
            self.scheduler = SchedulerConfig(
                heartbeat_interval_seconds=int(scheduler_payload.get("heartbeat_interval_seconds", 1800) or 1800),
                timezone=str(scheduler_payload.get("timezone", "UTC") or "UTC"),
            )
        if isinstance(self.channels, dict):
            self.channels = ChannelsConfig.from_dict(self.channels)
        if isinstance(self.tools, dict):
            self.tools = ToolsConfig.from_dict(self.tools)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_path": self.workspace_path,
            "state_path": self.state_path,
            "provider": asdict(self.provider),
            "providers": asdict(self.providers),
            "agents": asdict(self.agents),
            "gateway": asdict(self.gateway),
            "scheduler": asdict(self.scheduler),
            "channels": self.channels.to_dict(),
            "tools": asdict(self.tools),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        raw = dict(data or {})
        defaults = cls()

        provider_raw = dict(raw.get("provider") or {})
        provider = ProviderConfig(
            model=str(provider_raw.get("model", defaults.provider.model) or defaults.provider.model),
            litellm_base_url=str(provider_raw.get("litellm_base_url", defaults.provider.litellm_base_url) or defaults.provider.litellm_base_url),
            litellm_api_key=str(provider_raw.get("litellm_api_key", defaults.provider.litellm_api_key) or defaults.provider.litellm_api_key),
        )

        agents = AgentsConfig.from_dict(dict(raw.get("agents") or {}))

        providers = ProvidersConfig.from_dict(dict(raw.get("providers") or {}))
        gateway_raw = dict(raw.get("gateway") or {})
        gateway = GatewayConfig.from_dict(gateway_raw)
        scheduler_raw = dict(raw.get("scheduler") or {})
        scheduler = SchedulerConfig(
            heartbeat_interval_seconds=int(scheduler_raw.get("heartbeat_interval_seconds", defaults.scheduler.heartbeat_interval_seconds) or defaults.scheduler.heartbeat_interval_seconds),
            timezone=str(scheduler_raw.get("timezone", defaults.scheduler.timezone) or defaults.scheduler.timezone),
        )
        if (
            gateway.heartbeat.interval_s == defaults.gateway.heartbeat.interval_s
            and scheduler.heartbeat_interval_seconds != defaults.scheduler.heartbeat_interval_seconds
        ):
            gateway.heartbeat.interval_s = max(5, int(scheduler.heartbeat_interval_seconds or 1800))

        default_model = defaults.provider.model
        provider_model = str(provider.model or "").strip()
        agent_model = str(agents.defaults.model or "").strip()
        if provider_model != default_model and agent_model == default_model:
            agents.defaults.model = provider_model
        elif agent_model != default_model and provider_model == default_model:
            provider.model = agent_model
        elif agent_model != default_model and provider_model != default_model:
            provider.model = agent_model

        channels = ChannelsConfig.from_dict(dict(raw.get("channels") or {}))
        tools = ToolsConfig.from_dict(dict(raw.get("tools") or {}))
        return cls(
            workspace_path=str(raw.get("workspace_path") or defaults.workspace_path),
            state_path=str(raw.get("state_path") or defaults.state_path),
            provider=provider,
            providers=providers,
            agents=agents,
            gateway=gateway,
            scheduler=scheduler,
            channels=channels,
            tools=tools,
        )
