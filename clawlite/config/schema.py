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
class GatewaySupervisorConfig:
    enabled: bool = True
    interval_s: int = 20
    cooldown_s: int = 30

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> GatewaySupervisorConfig:
        data = dict(raw or {})
        if "intervalS" in data:
            interval_raw = data.get("intervalS")
        else:
            interval_raw = data.get("interval_s", 20)
        if "cooldownS" in data:
            cooldown_raw = data.get("cooldownS")
        else:
            cooldown_raw = data.get("cooldown_s", 30)
        return cls(
            enabled=bool(data.get("enabled", True)),
            interval_s=max(1, int(interval_raw or 20)),
            cooldown_s=max(0, int(cooldown_raw or 30)),
        )


@dataclass(slots=True)
class GatewayAutonomyConfig:
    enabled: bool = False
    interval_s: int = 900
    cooldown_s: int = 300
    timeout_s: float = 45.0
    max_queue_backlog: int = 200
    session_id: str = "autonomy:system"
    max_actions_per_run: int = 1
    action_cooldown_s: float = 120.0
    action_rate_limit_per_hour: int = 20
    max_replay_limit: int = 50
    action_policy: str = "balanced"
    min_action_confidence: float = 0.55
    degraded_backlog_threshold: int = 300
    degraded_supervisor_error_threshold: int = 3
    audit_export_path: str = ""
    audit_max_entries: int = 200

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> GatewayAutonomyConfig:
        data = dict(raw or {})
        if "actionPolicy" in data:
            policy_raw = data.get("actionPolicy")
        else:
            policy_raw = data.get("action_policy", "balanced")
        policy = str(policy_raw or "balanced").strip().lower()
        if policy not in {"balanced", "conservative"}:
            policy = "balanced"

        conservative_defaults: dict[str, Any] = {
            "action_cooldown_s": 300.0,
            "action_rate_limit_per_hour": 8,
            "min_action_confidence": 0.75,
            "degraded_backlog_threshold": 150,
            "degraded_supervisor_error_threshold": 1,
        }

        def _raw_with_alias(snake: str, camel: str, default: Any) -> Any:
            if camel in data:
                return data.get(camel)
            if snake in data:
                return data.get(snake)
            if policy == "conservative" and snake in conservative_defaults:
                return conservative_defaults[snake]
            return default

        if "intervalS" in data:
            interval_raw = data.get("intervalS")
        else:
            interval_raw = data.get("interval_s", 900)
        if "cooldownS" in data:
            cooldown_raw = data.get("cooldownS")
        else:
            cooldown_raw = data.get("cooldown_s", 300)
        if "timeoutS" in data:
            timeout_raw = data.get("timeoutS")
        else:
            timeout_raw = data.get("timeout_s", 45.0)
        if "maxQueueBacklog" in data:
            max_backlog_raw = data.get("maxQueueBacklog")
        else:
            max_backlog_raw = data.get("max_queue_backlog", 200)
        if "sessionId" in data:
            session_raw = data.get("sessionId")
        else:
            session_raw = data.get("session_id", "autonomy:system")
        if "maxActionsPerRun" in data:
            max_actions_raw = data.get("maxActionsPerRun")
        else:
            max_actions_raw = data.get("max_actions_per_run", 1)
        if "actionCooldownS" in data:
            action_cooldown_raw = data.get("actionCooldownS")
        else:
            action_cooldown_raw = _raw_with_alias("action_cooldown_s", "actionCooldownS", 120.0)
        if "actionRateLimitPerHour" in data:
            action_rate_limit_raw = data.get("actionRateLimitPerHour")
        else:
            action_rate_limit_raw = _raw_with_alias("action_rate_limit_per_hour", "actionRateLimitPerHour", 20)
        if "maxReplayLimit" in data:
            max_replay_limit_raw = data.get("maxReplayLimit")
        else:
            max_replay_limit_raw = data.get("max_replay_limit", 50)
        min_action_confidence_raw = _raw_with_alias("min_action_confidence", "minActionConfidence", 0.55)
        degraded_backlog_threshold_raw = _raw_with_alias("degraded_backlog_threshold", "degradedBacklogThreshold", 300)
        degraded_supervisor_error_threshold_raw = _raw_with_alias(
            "degraded_supervisor_error_threshold",
            "degradedSupervisorErrorThreshold",
            3,
        )
        audit_export_path_raw = _raw_with_alias("audit_export_path", "auditExportPath", "")
        audit_max_entries_raw = _raw_with_alias("audit_max_entries", "auditMaxEntries", 200)

        action_cooldown_s = max(0.0, float(action_cooldown_raw or 120.0))
        action_rate_limit_per_hour = max(1, int(action_rate_limit_raw or 20))
        min_action_confidence = float(min_action_confidence_raw or 0.55)
        if min_action_confidence < 0.0:
            min_action_confidence = 0.0
        if min_action_confidence > 1.0:
            min_action_confidence = 1.0
        degraded_backlog_threshold = max(1, int(degraded_backlog_threshold_raw or 300))
        degraded_supervisor_error_threshold = max(1, int(degraded_supervisor_error_threshold_raw or 3))

        if policy == "conservative":
            if action_cooldown_s == 120.0:
                action_cooldown_s = 300.0
            if action_rate_limit_per_hour == 20:
                action_rate_limit_per_hour = 8
            if min_action_confidence == 0.55:
                min_action_confidence = 0.75
            if degraded_backlog_threshold == 300:
                degraded_backlog_threshold = 150
            if degraded_supervisor_error_threshold == 3:
                degraded_supervisor_error_threshold = 1

        return cls(
            enabled=bool(data.get("enabled", False)),
            interval_s=max(1, int(interval_raw or 900)),
            cooldown_s=max(0, int(cooldown_raw or 300)),
            timeout_s=max(0.1, float(timeout_raw or 45.0)),
            max_queue_backlog=max(0, int(max_backlog_raw or 200)),
            session_id=str(session_raw or "autonomy:system").strip() or "autonomy:system",
            max_actions_per_run=max(1, int(max_actions_raw or 1)),
            action_cooldown_s=action_cooldown_s,
            action_rate_limit_per_hour=action_rate_limit_per_hour,
            max_replay_limit=max(1, int(max_replay_limit_raw or 50)),
            action_policy=policy,
            min_action_confidence=min_action_confidence,
            degraded_backlog_threshold=degraded_backlog_threshold,
            degraded_supervisor_error_threshold=degraded_supervisor_error_threshold,
            audit_export_path=str(audit_export_path_raw or "").strip(),
            audit_max_entries=max(1, int(audit_max_entries_raw or 200)),
        )


@dataclass(slots=True)
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 8787
    heartbeat: GatewayHeartbeatConfig = field(default_factory=GatewayHeartbeatConfig)
    auth: GatewayAuthConfig = field(default_factory=GatewayAuthConfig)
    diagnostics: GatewayDiagnosticsConfig = field(default_factory=GatewayDiagnosticsConfig)
    supervisor: GatewaySupervisorConfig = field(default_factory=GatewaySupervisorConfig)
    autonomy: GatewayAutonomyConfig = field(default_factory=GatewayAutonomyConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> GatewayConfig:
        data = dict(raw or {})
        return cls(
            host=str(data.get("host", "127.0.0.1") or "127.0.0.1"),
            port=int(data.get("port", 8787) or 8787),
            heartbeat=GatewayHeartbeatConfig.from_dict(dict(data.get("heartbeat") or {})),
            auth=GatewayAuthConfig.from_dict(dict(data.get("auth") or {})),
            diagnostics=GatewayDiagnosticsConfig.from_dict(dict(data.get("diagnostics") or {})),
            supervisor=GatewaySupervisorConfig.from_dict(dict(data.get("supervisor") or {})),
            autonomy=GatewayAutonomyConfig.from_dict(dict(data.get("autonomy") or {})),
        )


@dataclass(slots=True)
class ProviderConfig:
    model: str = "gemini/gemini-2.5-flash"
    litellm_base_url: str = "https://api.openai.com/v1"
    litellm_api_key: str = ""
    retry_max_attempts: int = 3
    retry_initial_backoff_s: float = 0.5
    retry_max_backoff_s: float = 8.0
    retry_jitter_s: float = 0.2
    circuit_failure_threshold: int = 3
    circuit_cooldown_s: float = 30.0
    fallback_model: str = ""


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
    mode: str = "polling"
    webhook_enabled: bool = False
    webhook_secret: str = ""
    webhook_path: str = "/api/webhooks/telegram"
    poll_interval_s: float = 1.0
    poll_timeout_s: int = 20
    reconnect_initial_s: float = 2.0
    reconnect_max_s: float = 30.0
    send_timeout_s: float = 15.0
    send_retry_attempts: int = 3
    send_backoff_base_s: float = 0.35
    send_backoff_max_s: float = 8.0
    send_backoff_jitter: float = 0.2
    send_circuit_failure_threshold: int = 1
    send_circuit_cooldown_s: float = 60.0
    typing_enabled: bool = True
    typing_interval_s: float = 2.5
    typing_max_ttl_s: float = 120.0
    typing_timeout_s: float = 5.0
    typing_circuit_failure_threshold: int = 1
    typing_circuit_cooldown_s: float = 60.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> TelegramChannelConfig:
        data = dict(raw or {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            allow_from=cls._allow_from(data),
            token=str(data.get("token", "") or ""),
            mode=str(data.get("mode", "polling") or "polling"),
            webhook_enabled=bool(data.get("webhook_enabled", data.get("webhookEnabled", False))),
            webhook_secret=str(data.get("webhook_secret", data.get("webhookSecret", "")) or ""),
            webhook_path=str(data.get("webhook_path", data.get("webhookPath", "/api/webhooks/telegram")) or "/api/webhooks/telegram"),
            poll_interval_s=float(data.get("poll_interval_s", data.get("pollIntervalS", 1.0)) or 1.0),
            poll_timeout_s=int(data.get("poll_timeout_s", data.get("pollTimeoutS", 20)) or 20),
            reconnect_initial_s=float(data.get("reconnect_initial_s", data.get("reconnectInitialS", 2.0)) or 2.0),
            reconnect_max_s=float(data.get("reconnect_max_s", data.get("reconnectMaxS", 30.0)) or 30.0),
            send_timeout_s=float(data.get("send_timeout_s", data.get("sendTimeoutSec", 15.0)) or 15.0),
            send_retry_attempts=int(data.get("send_retry_attempts", data.get("sendRetryAttempts", 3)) or 3),
            send_backoff_base_s=float(data.get("send_backoff_base_s", data.get("sendBackoffBaseSec", 0.35)) or 0.35),
            send_backoff_max_s=float(data.get("send_backoff_max_s", data.get("sendBackoffMaxSec", 8.0)) or 8.0),
            send_backoff_jitter=float(data.get("send_backoff_jitter", data.get("sendBackoffJitter", 0.2)) or 0.2),
            send_circuit_failure_threshold=int(
                data.get("send_circuit_failure_threshold", data.get("sendCircuitFailureThreshold", 1)) or 1
            ),
            send_circuit_cooldown_s=float(data.get("send_circuit_cooldown_s", data.get("sendCircuitCooldownSec", 60.0)) or 60.0),
            typing_enabled=bool(data.get("typing_enabled", data.get("typingEnabled", True))),
            typing_interval_s=float(data.get("typing_interval_s", data.get("typingIntervalS", 2.5)) or 2.5),
            typing_max_ttl_s=float(data.get("typing_max_ttl_s", data.get("typingMaxTtlS", 120.0)) or 120.0),
            typing_timeout_s=float(data.get("typing_timeout_s", data.get("typingTimeoutS", 5.0)) or 5.0),
            typing_circuit_failure_threshold=int(
                data.get("typing_circuit_failure_threshold", data.get("typingCircuitFailureThreshold", 1)) or 1
            ),
            typing_circuit_cooldown_s=float(data.get("typing_circuit_cooldown_s", data.get("typingCircuitCooldownS", 60.0)) or 60.0),
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
class ToolsConfig:
    restrict_to_workspace: bool = False
    web: WebToolConfig = field(default_factory=WebToolConfig)
    exec: ExecToolConfig = field(default_factory=ExecToolConfig)
    mcp: MCPToolConfig = field(default_factory=MCPToolConfig)
    loop_detection: ToolLoopDetectionConfig = field(default_factory=ToolLoopDetectionConfig)

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
        return cls(
            restrict_to_workspace=restrict,
            web=web_cfg,
            exec=exec_cfg,
            mcp=mcp_cfg,
            loop_detection=loop_detection_cfg,
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
                retry_max_attempts=max(1, int(payload.get("retry_max_attempts", payload.get("retryMaxAttempts", 3)) or 3)),
                retry_initial_backoff_s=max(
                    0.0,
                    float(payload.get("retry_initial_backoff_s", payload.get("retryInitialBackoffS", 0.5)) or 0.5),
                ),
                retry_max_backoff_s=max(
                    0.0,
                    float(payload.get("retry_max_backoff_s", payload.get("retryMaxBackoffS", 8.0)) or 8.0),
                ),
                retry_jitter_s=max(0.0, float(payload.get("retry_jitter_s", payload.get("retryJitterS", 0.2)) or 0.2)),
                circuit_failure_threshold=max(
                    1,
                    int(payload.get("circuit_failure_threshold", payload.get("circuitFailureThreshold", 3)) or 3),
                ),
                circuit_cooldown_s=max(
                    0.0,
                    float(payload.get("circuit_cooldown_s", payload.get("circuitCooldownS", 30.0)) or 30.0),
                ),
                fallback_model=str(payload.get("fallback_model", payload.get("fallbackModel", "")) or "").strip(),
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
        def _provider_value(snake: str, camel: str, default: Any) -> Any:
            if camel in provider_raw:
                return provider_raw.get(camel)
            return provider_raw.get(snake, default)

        provider = ProviderConfig(
            model=str(_provider_value("model", "model", defaults.provider.model) or defaults.provider.model),
            litellm_base_url=str(
                _provider_value("litellm_base_url", "litellmBaseUrl", defaults.provider.litellm_base_url)
                or defaults.provider.litellm_base_url
            ),
            litellm_api_key=str(
                _provider_value("litellm_api_key", "litellmApiKey", defaults.provider.litellm_api_key)
                or defaults.provider.litellm_api_key
            ),
            retry_max_attempts=max(
                1,
                int(_provider_value("retry_max_attempts", "retryMaxAttempts", defaults.provider.retry_max_attempts) or defaults.provider.retry_max_attempts),
            ),
            retry_initial_backoff_s=max(
                0.0,
                float(
                    _provider_value("retry_initial_backoff_s", "retryInitialBackoffS", defaults.provider.retry_initial_backoff_s)
                    or defaults.provider.retry_initial_backoff_s
                ),
            ),
            retry_max_backoff_s=max(
                0.0,
                float(
                    _provider_value("retry_max_backoff_s", "retryMaxBackoffS", defaults.provider.retry_max_backoff_s)
                    or defaults.provider.retry_max_backoff_s
                ),
            ),
            retry_jitter_s=max(
                0.0,
                float(_provider_value("retry_jitter_s", "retryJitterS", defaults.provider.retry_jitter_s) or defaults.provider.retry_jitter_s),
            ),
            circuit_failure_threshold=max(
                1,
                int(
                    _provider_value("circuit_failure_threshold", "circuitFailureThreshold", defaults.provider.circuit_failure_threshold)
                    or defaults.provider.circuit_failure_threshold
                ),
            ),
            circuit_cooldown_s=max(
                0.0,
                float(_provider_value("circuit_cooldown_s", "circuitCooldownS", defaults.provider.circuit_cooldown_s) or defaults.provider.circuit_cooldown_s),
            ),
            fallback_model=str(_provider_value("fallback_model", "fallbackModel", defaults.provider.fallback_model) or defaults.provider.fallback_model).strip(),
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
