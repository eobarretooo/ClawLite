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
class GatewayAuthConfig:
    mode: str = "off"
    token: str = ""
    allow_loopback_without_auth: bool = True
    header_name: str = "Authorization"
    query_param: str = "token"
    protect_health: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> GatewayAuthConfig:
        data = dict(raw or {})
        mode = str(data.get("mode", "off") or "off").strip().lower()
        if mode not in {"off", "optional", "required"}:
            mode = "off"
        header_name = str(data.get("header_name", data.get("headerName", "Authorization")) or "Authorization").strip()
        query_param = str(data.get("query_param", data.get("queryParam", "token")) or "token").strip()
        return cls(
            mode=mode,
            token=str(data.get("token", "") or "").strip(),
            allow_loopback_without_auth=bool(data.get("allow_loopback_without_auth", data.get("allowLoopbackWithoutAuth", True))),
            header_name=header_name or "Authorization",
            query_param=query_param or "token",
            protect_health=bool(data.get("protect_health", data.get("protectHealth", False))),
        )


@dataclass(slots=True)
class GatewayDiagnosticsConfig:
    enabled: bool = True
    require_auth: bool = True
    include_config: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> GatewayDiagnosticsConfig:
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", True)),
            require_auth=bool(data.get("require_auth", data.get("requireAuth", True))),
            include_config=bool(data.get("include_config", data.get("includeConfig", False))),
        )


@dataclass(slots=True)
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    heartbeat: GatewayHeartbeatConfig = field(default_factory=GatewayHeartbeatConfig)
    auth: GatewayAuthConfig = field(default_factory=GatewayAuthConfig)
    diagnostics: GatewayDiagnosticsConfig = field(default_factory=GatewayDiagnosticsConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> GatewayConfig:
        data = dict(raw or {})
        return cls(
            host=str(data.get("host", "127.0.0.1") or "127.0.0.1"),
            port=int(data.get("port", 8787) or 8787),
            heartbeat=GatewayHeartbeatConfig.from_dict(dict(data.get("heartbeat") or {})),
            auth=GatewayAuthConfig.from_dict(dict(data.get("auth") or {})),
            diagnostics=GatewayDiagnosticsConfig.from_dict(dict(data.get("diagnostics") or {})),
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
    api_base: str = "https://discord.com/api/v10"
    timeout_s: float = 10.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> DiscordChannelConfig:
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            allow_from=cls._allow_from(data),
            token=str(data.get("token", "") or ""),
            api_base=str(data.get("api_base", data.get("apiBase", "https://discord.com/api/v10")) or "https://discord.com/api/v10"),
            timeout_s=max(0.1, float(data.get("timeout_s", data.get("timeoutS", 10.0)) or 10.0)),
        )


@dataclass(slots=True)
class SlackChannelConfig(BaseChannelConfig):
    bot_token: str = ""
    app_token: str = ""
    api_base: str = "https://slack.com/api"
    timeout_s: float = 10.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SlackChannelConfig:
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            allow_from=cls._allow_from(data),
            bot_token=str(data.get("bot_token", data.get("botToken", "")) or ""),
            app_token=str(data.get("app_token", data.get("appToken", "")) or ""),
            api_base=str(data.get("api_base", data.get("apiBase", "https://slack.com/api")) or "https://slack.com/api"),
            timeout_s=max(0.1, float(data.get("timeout_s", data.get("timeoutS", 10.0)) or 10.0)),
        )


@dataclass(slots=True)
class WhatsAppChannelConfig(BaseChannelConfig):
    bridge_url: str = "ws://localhost:3001"
    bridge_token: str = ""
    timeout_s: float = 10.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> WhatsAppChannelConfig:
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            allow_from=cls._allow_from(data),
            bridge_url=str(data.get("bridge_url", data.get("bridgeUrl", "ws://localhost:3001")) or "ws://localhost:3001"),
            bridge_token=str(data.get("bridge_token", data.get("bridgeToken", "")) or ""),
            timeout_s=max(0.1, float(data.get("timeout_s", data.get("timeoutS", 10.0)) or 10.0)),
        )


@dataclass(slots=True)
class ChannelsConfig:
    send_progress: bool = False
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
            send_progress=bool(data.get("send_progress", data.get("sendProgress", False))),
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
class WebToolConfig:
    proxy: str = ""
    timeout: float = 15.0
    search_timeout: float = 10.0
    max_redirects: int = 5
    max_chars: int = 12000
    block_private_addresses: bool = True
    allowlist: list[str] = field(default_factory=list)
    denylist: list[str] = field(default_factory=list)

    @staticmethod
    def _parse_list(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [str(item).strip() for item in raw if str(item).strip()]

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> WebToolConfig:
        data = dict(raw or {})
        return cls(
            proxy=str(data.get("proxy", "") or ""),
            timeout=max(1.0, float(data.get("timeout", 15.0) or 15.0)),
            search_timeout=max(1.0, float(data.get("searchTimeout", data.get("search_timeout", 10.0)) or 10.0)),
            max_redirects=max(0, int(data.get("maxRedirects", data.get("max_redirects", 5)) or 5)),
            max_chars=max(128, int(data.get("maxChars", data.get("max_chars", 12000)) or 12000)),
            block_private_addresses=bool(data.get("blockPrivateAddresses", data.get("block_private_addresses", True))),
            allowlist=cls._parse_list(data.get("allowlist", [])),
            denylist=cls._parse_list(data.get("denylist", [])),
        )


@dataclass(slots=True)
class ExecToolConfig:
    timeout: int = 60
    path_append: str = ""
    deny_patterns: list[str] = field(default_factory=list)
    allow_patterns: list[str] = field(default_factory=list)
    deny_path_patterns: list[str] = field(default_factory=list)
    allow_path_patterns: list[str] = field(default_factory=list)

    @staticmethod
    def _parse_patterns(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [str(item).strip() for item in raw if str(item).strip()]

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ExecToolConfig:
        data = dict(raw or {})
        timeout = int(data.get("timeout", 60) or 60)
        if "pathAppend" in data:
            path_append = str(data.get("pathAppend", "") or "")
        else:
            path_append = str(data.get("path_append", "") or "")

        if "denyPatterns" in data:
            deny_patterns = cls._parse_patterns(data.get("denyPatterns"))
        else:
            deny_patterns = cls._parse_patterns(data.get("deny_patterns", []))

        if "allowPatterns" in data:
            allow_patterns = cls._parse_patterns(data.get("allowPatterns"))
        else:
            allow_patterns = cls._parse_patterns(data.get("allow_patterns", []))

        if "denyPathPatterns" in data:
            deny_path_patterns = cls._parse_patterns(data.get("denyPathPatterns"))
        else:
            deny_path_patterns = cls._parse_patterns(data.get("deny_path_patterns", []))

        if "allowPathPatterns" in data:
            allow_path_patterns = cls._parse_patterns(data.get("allowPathPatterns"))
        else:
            allow_path_patterns = cls._parse_patterns(data.get("allow_path_patterns", []))

        return cls(
            timeout=max(1, timeout),
            path_append=path_append,
            deny_patterns=deny_patterns,
            allow_patterns=allow_patterns,
            deny_path_patterns=deny_path_patterns,
            allow_path_patterns=allow_path_patterns,
        )


@dataclass(slots=True)
class MCPTransportPolicyConfig:
    allowed_schemes: list[str] = field(default_factory=lambda: ["http", "https"])
    allowed_hosts: list[str] = field(default_factory=list)
    denied_hosts: list[str] = field(default_factory=list)

    @staticmethod
    def _parse_hosts(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [str(item).strip().lower() for item in raw if str(item).strip()]

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> MCPTransportPolicyConfig:
        data = dict(raw or {})
        if "allowedSchemes" in data:
            schemes_raw = data.get("allowedSchemes")
        else:
            schemes_raw = data.get("allowed_schemes", ["http", "https"])
        if not isinstance(schemes_raw, list):
            schemes_raw = ["http", "https"]
        allowed_schemes = [str(item).strip().lower() for item in schemes_raw if str(item).strip()]
        if not allowed_schemes:
            allowed_schemes = ["http", "https"]
        if "allowedHosts" in data:
            allowed_hosts_raw = data.get("allowedHosts", [])
        else:
            allowed_hosts_raw = data.get("allowed_hosts", [])
        if "deniedHosts" in data:
            denied_hosts_raw = data.get("deniedHosts", [])
        else:
            denied_hosts_raw = data.get("denied_hosts", [])
        return cls(
            allowed_schemes=allowed_schemes,
            allowed_hosts=cls._parse_hosts(allowed_hosts_raw),
            denied_hosts=cls._parse_hosts(denied_hosts_raw),
        )


@dataclass(slots=True)
class MCPServerConfig:
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    timeout_s: float = 20.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None, *, default_timeout_s: float = 20.0) -> MCPServerConfig:
        data = dict(raw or {})
        timeout_raw = data.get("timeout_s", data.get("timeoutS", data.get("tool_timeout_s", data.get("toolTimeoutS", default_timeout_s))))
        headers_raw = data.get("headers", {})
        headers = dict(headers_raw) if isinstance(headers_raw, dict) else {}
        return cls(
            url=str(data.get("url", "") or "").strip(),
            headers={str(k): str(v) for k, v in headers.items()},
            timeout_s=max(0.1, float(timeout_raw or default_timeout_s)),
        )


@dataclass(slots=True)
class MCPToolConfig:
    default_timeout_s: float = 20.0
    policy: MCPTransportPolicyConfig = field(default_factory=MCPTransportPolicyConfig)
    servers: dict[str, MCPServerConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> MCPToolConfig:
        data = dict(raw or {})
        if "defaultTimeoutS" in data:
            timeout_raw = data.get("defaultTimeoutS")
        else:
            timeout_raw = data.get("default_timeout_s", data.get("timeout", 20.0))
        default_timeout = max(
            0.1,
            float(timeout_raw or 20.0),
        )
        policy = MCPTransportPolicyConfig.from_dict(dict(data.get("policy") or {}))
        servers_raw = data.get("servers", {})
        servers: dict[str, MCPServerConfig] = {}
        if isinstance(servers_raw, dict):
            for key, value in servers_raw.items():
                name = str(key).strip()
                if not name or not isinstance(value, dict):
                    continue
                servers[name] = MCPServerConfig.from_dict(dict(value), default_timeout_s=default_timeout)
        return cls(default_timeout_s=default_timeout, policy=policy, servers=servers)


@dataclass(slots=True)
class ToolLoopDetectionConfig:
    enabled: bool = False
    history_size: int = 20
    repeat_threshold: int = 3
    critical_threshold: int = 6

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ToolLoopDetectionConfig:
        data = dict(raw or {})
        history_raw = data.get("historySize") if "historySize" in data else data.get("history_size", 20)
        repeat_raw = data.get("repeatThreshold") if "repeatThreshold" in data else data.get("repeat_threshold", 3)
        critical_raw = data.get("criticalThreshold") if "criticalThreshold" in data else data.get("critical_threshold", 6)
        history_size = max(1, int(history_raw or 20))
        repeat_threshold = max(1, int(repeat_raw or 3))
        critical_threshold = max(1, int(critical_raw or 6))
        if critical_threshold <= repeat_threshold:
            critical_threshold = repeat_threshold + 1
        return cls(
            enabled=bool(data.get("enabled", False)),
            history_size=history_size,
            repeat_threshold=repeat_threshold,
            critical_threshold=critical_threshold,
        )


@dataclass(slots=True)
class ToolSafetyPolicyConfig:
    enabled: bool = True
    risky_tools: list[str] = field(default_factory=lambda: ["exec", "web_fetch", "web_search", "mcp"])
    blocked_channels: list[str] = field(default_factory=lambda: ["telegram", "discord", "slack", "whatsapp"])
    allowed_channels: list[str] = field(default_factory=list)

    @staticmethod
    def _parse_names(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        return [str(item).strip().lower() for item in raw if str(item).strip()]

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ToolSafetyPolicyConfig:
        data = dict(raw or {})
        if "riskyTools" in data:
            risky_raw = data.get("riskyTools")
        else:
            risky_raw = data.get("risky_tools", ["exec", "web_fetch", "web_search", "mcp"])
        if "blockedChannels" in data:
            blocked_raw = data.get("blockedChannels")
        else:
            blocked_raw = data.get("blocked_channels", ["telegram", "discord", "slack", "whatsapp"])
        if "allowedChannels" in data:
            allowed_raw = data.get("allowedChannels")
        else:
            allowed_raw = data.get("allowed_channels", [])
        return cls(
            enabled=bool(data.get("enabled", True)),
            risky_tools=cls._parse_names(risky_raw),
            blocked_channels=cls._parse_names(blocked_raw),
            allowed_channels=cls._parse_names(allowed_raw),
        )


@dataclass(slots=True)
class ToolsConfig:
    restrict_to_workspace: bool = False
    web: WebToolConfig = field(default_factory=WebToolConfig)
    exec: ExecToolConfig = field(default_factory=ExecToolConfig)
    mcp: MCPToolConfig = field(default_factory=MCPToolConfig)
    loop_detection: ToolLoopDetectionConfig = field(default_factory=ToolLoopDetectionConfig)
    safety: ToolSafetyPolicyConfig = field(default_factory=ToolSafetyPolicyConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ToolsConfig:
        data = dict(raw or {})
        if "restrictToWorkspace" in data:
            restrict = bool(data.get("restrictToWorkspace", False))
        else:
            restrict = bool(data.get("restrict_to_workspace", False))
        web_cfg = WebToolConfig.from_dict(dict(data.get("web") or {}))
        exec_cfg = ExecToolConfig.from_dict(dict(data.get("exec") or {}))
        mcp_cfg = MCPToolConfig.from_dict(dict(data.get("mcp") or {}))
        loop_detection_raw = data.get("loop_detection", data.get("loopDetection", {}))
        loop_detection_cfg = ToolLoopDetectionConfig.from_dict(dict(loop_detection_raw or {}))
        safety_raw = data.get("safety", {})
        safety_cfg = ToolSafetyPolicyConfig.from_dict(dict(safety_raw or {}))
        return cls(
            restrict_to_workspace=restrict,
            web=web_cfg,
            exec=exec_cfg,
            mcp=mcp_cfg,
            loop_detection=loop_detection_cfg,
            safety=safety_cfg,
        )


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
