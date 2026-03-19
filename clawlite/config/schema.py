from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Base":
        return cls.model_validate(data)


# ---------------------------------------------------------------------------
# Gateway sub-configs
# ---------------------------------------------------------------------------

class GatewayHeartbeatConfig(Base):
    enabled: bool = True
    interval_s: int = 1800

    @field_validator("interval_s", mode="before")
    @classmethod
    def _min_interval(cls, v: Any) -> int:
        v = v if v not in (None, "") else 1800
        return max(5, int(v))


class GatewayAuthConfig(Base):
    mode: str = "off"
    token: str = ""
    allow_loopback_without_auth: bool = True
    header_name: str = "Authorization"
    query_param: str = "token"
    protect_health: bool = False

    @field_validator("mode", mode="before")
    @classmethod
    def _validate_mode(cls, v: Any) -> str:
        v = str(v or "off").strip().lower()
        if v not in {"off", "optional", "required"}:
            v = "off"
        return v

    @field_validator("token", mode="before")
    @classmethod
    def _strip_token(cls, v: Any) -> str:
        return str(v or "").strip()

    @field_validator("header_name", mode="before")
    @classmethod
    def _header_name_default(cls, v: Any) -> str:
        return str(v or "Authorization").strip() or "Authorization"

    @field_validator("query_param", mode="before")
    @classmethod
    def _query_param_default(cls, v: Any) -> str:
        return str(v or "token").strip() or "token"


class GatewayDiagnosticsConfig(Base):
    enabled: bool = True
    require_auth: bool = True
    include_config: bool = False
    include_provider_telemetry: bool = True


class GatewaySupervisorConfig(Base):
    enabled: bool = True
    interval_s: int = 20
    cooldown_s: int = 30

    @field_validator("interval_s", mode="before")
    @classmethod
    def _min_interval(cls, v: Any) -> int:
        v = v if v not in (None, "") else 20
        return max(1, int(v))

    @field_validator("cooldown_s", mode="before")
    @classmethod
    def _min_cooldown(cls, v: Any) -> int:
        v = v if v not in (None, "") else 30
        return max(0, int(v))


class GatewayAutonomyConfig(Base):
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
    environment_profile: str = "dev"
    min_action_confidence: float = 0.55
    degraded_backlog_threshold: int = 300
    degraded_supervisor_error_threshold: int = 3
    audit_export_path: str = ""
    audit_max_entries: int = 200
    tuning_loop_enabled: bool = False
    tuning_loop_interval_s: int = 1800
    tuning_loop_timeout_s: float = 45.0
    tuning_loop_cooldown_s: int = 300
    tuning_degrading_streak_threshold: int = 2
    tuning_recent_actions_limit: int = 20
    tuning_error_backoff_s: int = 900
    self_evolution_enabled: bool = False
    self_evolution_cooldown_s: int = 3600
    self_evolution_branch_prefix: str = "self-evolution"
    self_evolution_require_approval: bool = False

    @model_validator(mode="before")
    @classmethod
    def _apply_profile_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)

        # Resolve environment_profile
        if "environmentProfile" in data:
            ep_raw = data.get("environmentProfile")
        else:
            ep_raw = data.get("environment_profile", "dev")
        environment_profile = str(ep_raw or "dev").strip().lower()
        if environment_profile not in {"dev", "staging", "prod"}:
            environment_profile = "dev"
        data["environment_profile"] = environment_profile

        # Resolve action_policy
        policy_explicit = "actionPolicy" in data or "action_policy" in data
        if "actionPolicy" in data:
            policy_raw = data.get("actionPolicy")
        elif "action_policy" in data:
            policy_raw = data.get("action_policy")
        else:
            policy_raw = "conservative" if environment_profile == "prod" else "balanced"
        policy = str(policy_raw or ("conservative" if environment_profile == "prod" else "balanced")).strip().lower()
        if policy not in {"balanced", "conservative"}:
            policy = "conservative" if environment_profile == "prod" and not policy_explicit else "balanced"
        data["action_policy"] = policy

        conservative_defaults: dict[str, Any] = {
            "action_cooldown_s": 300.0,
            "action_rate_limit_per_hour": 8,
            "min_action_confidence": 0.75,
            "degraded_backlog_threshold": 150,
            "degraded_supervisor_error_threshold": 1,
        }
        staging_defaults: dict[str, Any] = {
            "action_cooldown_s": 180.0,
            "action_rate_limit_per_hour": 14,
            "min_action_confidence": 0.65,
            "degraded_backlog_threshold": 220,
            "degraded_supervisor_error_threshold": 2,
        }

        if environment_profile == "prod":
            profile_defaults = dict(conservative_defaults)
        elif environment_profile == "staging":
            profile_defaults = dict(staging_defaults)
        else:
            profile_defaults = {}

        if policy == "conservative":
            for key, value in conservative_defaults.items():
                profile_defaults.setdefault(key, value)

        def _raw_with_alias(snake: str, camel: str, default: Any) -> Any:
            if camel in data:
                return data[camel]
            if snake in data:
                return data[snake]
            if snake in profile_defaults:
                return profile_defaults[snake]
            return default

        # Apply profile defaults for fields NOT explicitly set in data
        for snake, camel, default in [
            ("action_cooldown_s", "actionCooldownS", 120.0),
            ("action_rate_limit_per_hour", "actionRateLimitPerHour", 20),
            ("min_action_confidence", "minActionConfidence", 0.55),
            ("degraded_backlog_threshold", "degradedBacklogThreshold", 300),
            ("degraded_supervisor_error_threshold", "degradedSupervisorErrorThreshold", 3),
        ]:
            resolved = _raw_with_alias(snake, camel, default)
            # Store as snake_case so Pydantic picks it up
            if camel in data:
                data[snake] = resolved
                del data[camel]
            elif snake not in data and snake in profile_defaults:
                data[snake] = resolved

        # session_id strip
        if "session_id" in data:
            data["session_id"] = str(data["session_id"] or "autonomy:system").strip() or "autonomy:system"
        elif "sessionId" in data:
            data["session_id"] = str(data["sessionId"] or "autonomy:system").strip() or "autonomy:system"
            del data["sessionId"]

        return data

    @field_validator("interval_s", mode="before")
    @classmethod
    def _min_interval(cls, v: Any) -> int:
        v = v if v not in (None, "") else 900
        return max(1, int(v))

    @field_validator("cooldown_s", mode="before")
    @classmethod
    def _min_cooldown(cls, v: Any) -> int:
        v = v if v not in (None, "") else 300
        return max(0, int(v))

    @field_validator("timeout_s", mode="before")
    @classmethod
    def _min_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 45.0
        return max(0.1, float(v))

    @field_validator("max_queue_backlog", mode="before")
    @classmethod
    def _min_backlog(cls, v: Any) -> int:
        v = v if v not in (None, "") else 200
        return max(0, int(v))

    @field_validator("max_actions_per_run", mode="before")
    @classmethod
    def _min_actions(cls, v: Any) -> int:
        v = v if v not in (None, "") else 1
        return max(1, int(v))

    @field_validator("action_cooldown_s", mode="before")
    @classmethod
    def _min_action_cooldown(cls, v: Any) -> float:
        v = v if v not in (None, "") else 120.0
        return max(0.0, float(v))

    @field_validator("action_rate_limit_per_hour", mode="before")
    @classmethod
    def _min_rate_limit(cls, v: Any) -> int:
        v = v if v not in (None, "") else 20
        return max(1, int(v))

    @field_validator("max_replay_limit", mode="before")
    @classmethod
    def _min_replay(cls, v: Any) -> int:
        v = v if v not in (None, "") else 50
        return max(1, int(v))

    @field_validator("min_action_confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: Any) -> float:
        v = v if v not in (None, "") else 0.55
        f = float(v)
        return max(0.0, min(1.0, f))

    @field_validator("degraded_backlog_threshold", mode="before")
    @classmethod
    def _min_deg_backlog(cls, v: Any) -> int:
        v = v if v not in (None, "") else 300
        return max(1, int(v))

    @field_validator("degraded_supervisor_error_threshold", mode="before")
    @classmethod
    def _min_deg_super(cls, v: Any) -> int:
        v = v if v not in (None, "") else 3
        return max(1, int(v))

    @field_validator("audit_max_entries", mode="before")
    @classmethod
    def _min_audit(cls, v: Any) -> int:
        v = v if v not in (None, "") else 200
        return max(1, int(v))

    @field_validator("tuning_loop_interval_s", mode="before")
    @classmethod
    def _min_tuning_interval(cls, v: Any) -> int:
        v = v if v not in (None, "") else 1800
        return max(30, int(v))

    @field_validator("tuning_loop_timeout_s", mode="before")
    @classmethod
    def _min_tuning_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 45.0
        return max(1.0, float(v))

    @field_validator("tuning_loop_cooldown_s", mode="before")
    @classmethod
    def _min_tuning_cooldown(cls, v: Any) -> int:
        v = v if v not in (None, "") else 300
        return max(0, int(v))

    @field_validator("tuning_degrading_streak_threshold", mode="before")
    @classmethod
    def _min_tuning_streak(cls, v: Any) -> int:
        v = v if v not in (None, "") else 2
        return max(1, int(v))

    @field_validator("tuning_recent_actions_limit", mode="before")
    @classmethod
    def _min_tuning_actions(cls, v: Any) -> int:
        v = v if v not in (None, "") else 20
        return max(1, int(v))

    @field_validator("tuning_error_backoff_s", mode="before")
    @classmethod
    def _min_tuning_backoff(cls, v: Any) -> int:
        v = v if v not in (None, "") else 900
        return max(1, int(v))

    @field_validator("self_evolution_cooldown_s", mode="before")
    @classmethod
    def _min_evo_cooldown(cls, v: Any) -> int:
        v = v if v not in (None, "") else 3600
        return max(60, int(v))

    @field_validator("self_evolution_branch_prefix", mode="before")
    @classmethod
    def _branch_prefix_default(cls, v: Any) -> str:
        value = str(v or "self-evolution").strip()
        return value or "self-evolution"


class GatewayWebSocketConfig(Base):
    coalesce_enabled: bool = True
    coalesce_min_chars: int = 24
    coalesce_max_chars: int = 120

    @field_validator("coalesce_min_chars", "coalesce_max_chars", mode="before")
    @classmethod
    def _coalesce_char_bounds(cls, v: Any, info: Any) -> int:
        defaults = {
            "coalesce_min_chars": 24,
            "coalesce_max_chars": 120,
        }
        value = v if v not in (None, "") else defaults.get(str(info.field_name), 1)
        return max(1, int(value))

    @model_validator(mode="after")
    def _normalize_coalesce_bounds(self) -> "GatewayWebSocketConfig":
        if self.coalesce_max_chars < self.coalesce_min_chars:
            self.coalesce_max_chars = self.coalesce_min_chars
        return self


class GatewayConfig(Base):
    host: str = "127.0.0.1"
    port: int = 8787
    startup_timeout_default_s: float = 15.0
    startup_timeout_channels_s: float = 30.0
    startup_timeout_autonomy_s: float = 10.0
    startup_timeout_supervisor_s: float = 5.0
    heartbeat: GatewayHeartbeatConfig = Field(default_factory=GatewayHeartbeatConfig)
    auth: GatewayAuthConfig = Field(default_factory=GatewayAuthConfig)
    diagnostics: GatewayDiagnosticsConfig = Field(default_factory=GatewayDiagnosticsConfig)
    supervisor: GatewaySupervisorConfig = Field(default_factory=GatewaySupervisorConfig)
    autonomy: GatewayAutonomyConfig = Field(default_factory=GatewayAutonomyConfig)
    websocket: GatewayWebSocketConfig = Field(default_factory=GatewayWebSocketConfig)

    @field_validator("host", mode="before")
    @classmethod
    def _host_default(cls, v: Any) -> str:
        return str(v or "127.0.0.1")

    @field_validator("port", mode="before")
    @classmethod
    def _port_default(cls, v: Any) -> int:
        return int(v or 8787)

    @field_validator(
        "startup_timeout_default_s",
        "startup_timeout_channels_s",
        "startup_timeout_autonomy_s",
        "startup_timeout_supervisor_s",
        mode="before",
    )
    @classmethod
    def _startup_timeout_default(cls, v: Any) -> float:
        v = v if v not in (None, "") else 15.0
        return max(0.1, float(v))


# ---------------------------------------------------------------------------
# Provider configs
# ---------------------------------------------------------------------------

class ProviderConfig(Base):
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

    @field_validator("model", mode="before")
    @classmethod
    def _model_default(cls, v: Any) -> str:
        return str(v or "gemini/gemini-2.5-flash")

    @field_validator("litellm_base_url", mode="before")
    @classmethod
    def _base_url_default(cls, v: Any) -> str:
        return str(v or "https://api.openai.com/v1")

    @field_validator("retry_max_attempts", mode="before")
    @classmethod
    def _min_retry(cls, v: Any) -> int:
        v = v if v not in (None, "") else 3
        return max(1, int(v))

    @field_validator("retry_initial_backoff_s", mode="before")
    @classmethod
    def _min_retry_backoff(cls, v: Any) -> float:
        v = v if v not in (None, "") else 0.5
        return max(0.0, float(v))

    @field_validator("retry_max_backoff_s", mode="before")
    @classmethod
    def _min_retry_max_backoff(cls, v: Any) -> float:
        v = v if v not in (None, "") else 8.0
        return max(0.0, float(v))

    @field_validator("retry_jitter_s", mode="before")
    @classmethod
    def _min_jitter(cls, v: Any) -> float:
        v = v if v not in (None, "") else 0.2
        return max(0.0, float(v))

    @field_validator("circuit_failure_threshold", mode="before")
    @classmethod
    def _min_circuit(cls, v: Any) -> int:
        v = v if v not in (None, "") else 3
        return max(1, int(v))

    @field_validator("circuit_cooldown_s", mode="before")
    @classmethod
    def _min_circuit_cooldown(cls, v: Any) -> float:
        v = v if v not in (None, "") else 30.0
        return max(0.0, float(v))

    @field_validator("fallback_model", mode="before")
    @classmethod
    def _strip_fallback(cls, v: Any) -> str:
        return str(v or "").strip()


class ProviderOverrideConfig(Base):
    api_key: str = ""
    api_base: str = ""
    extra_headers: dict[str, str] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_key": self.api_key,
            "api_base": self.api_base,
            "extra_headers": dict(self.extra_headers),
        }


class ProvidersConfig(Base):
    BUILTIN_KEYS: ClassVar[tuple[str, ...]] = (
        "openrouter",
        "gemini",
        "openai",
        "anthropic",
        "deepseek",
        "groq",
        "ollama",
        "vllm",
        "custom",
    )

    openrouter: ProviderOverrideConfig = Field(default_factory=ProviderOverrideConfig)
    gemini: ProviderOverrideConfig = Field(default_factory=ProviderOverrideConfig)
    openai: ProviderOverrideConfig = Field(default_factory=ProviderOverrideConfig)
    anthropic: ProviderOverrideConfig = Field(default_factory=ProviderOverrideConfig)
    deepseek: ProviderOverrideConfig = Field(default_factory=ProviderOverrideConfig)
    groq: ProviderOverrideConfig = Field(default_factory=ProviderOverrideConfig)
    ollama: ProviderOverrideConfig = Field(default_factory=ProviderOverrideConfig)
    vllm: ProviderOverrideConfig = Field(default_factory=ProviderOverrideConfig)
    custom: ProviderOverrideConfig = Field(default_factory=ProviderOverrideConfig)
    extra: dict[str, ProviderOverrideConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _extract_extras(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        extras: dict[str, Any] = {}
        builtin = {
            "openrouter", "gemini", "openai", "anthropic",
            "deepseek", "groq", "ollama", "vllm", "custom",
        }
        for key, value in list(data.items()):
            if key in ("extra",):
                continue
            normalized = cls.normalize_name(key)
            if normalized in builtin or not isinstance(value, dict):
                continue
            # It's a custom provider
            extras[normalized] = value
        if extras:
            existing_extra = data.get("extra", {}) or {}
            merged = {**extras, **existing_extra}
            data["extra"] = merged
        return data

    @staticmethod
    def normalize_name(value: str) -> str:
        return str(value or "").strip().lower().replace("-", "_")

    def get(self, name: str) -> ProviderOverrideConfig | None:
        key = self.normalize_name(name)
        if key in self.BUILTIN_KEYS:
            return getattr(self, key)
        return self.extra.get(key)

    def ensure(self, name: str) -> ProviderOverrideConfig:
        key = self.normalize_name(name)
        existing = self.get(key)
        if existing is not None:
            return existing
        created = ProviderOverrideConfig()
        self.extra[key] = created
        return created

    def to_dict(self) -> dict[str, Any]:
        payload = {key: getattr(self, key).to_dict() for key in self.BUILTIN_KEYS}
        for key in sorted(self.extra):
            payload[key] = self.extra[key].to_dict()
        return payload


# ---------------------------------------------------------------------------
# Auth configs
# ---------------------------------------------------------------------------

class AuthProviderTokenConfig(Base):
    access_token: str = ""
    account_id: str = ""
    source: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # access_token aliases
        if "access_token" not in data and "accessToken" not in data:
            for alias in ("token",):
                if alias in data:
                    data["access_token"] = data[alias]
                    break
        # account_id aliases
        if "account_id" not in data and "accountId" not in data:
            for alias in ("org_id", "orgId", "organization"):
                if alias in data:
                    data["account_id"] = data[alias]
                    break
        return data

    @field_validator("access_token", "account_id", "source", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> str:
        return str(v or "").strip()


class AuthProvidersConfig(Base):
    openai_codex: AuthProviderTokenConfig = Field(default_factory=AuthProviderTokenConfig)
    gemini_oauth: AuthProviderTokenConfig = Field(default_factory=AuthProviderTokenConfig)
    qwen_oauth: AuthProviderTokenConfig = Field(default_factory=AuthProviderTokenConfig)

    @model_validator(mode="before")
    @classmethod
    def _normalize_codex_key(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "openai_codex" not in data and "openaiCodex" not in data:
            for key in ("openai-codex", "codex"):
                if key in data and isinstance(data[key], dict):
                    data["openai_codex"] = data[key]
                    break
        if "gemini_oauth" not in data and "geminiOAuth" not in data:
            for key in ("gemini-oauth", "gemini_oauth", "gemini"):
                if key in data and isinstance(data[key], dict):
                    data["gemini_oauth"] = data[key]
                    break
        if "qwen_oauth" not in data and "qwenOAuth" not in data:
            for key in ("qwen-oauth", "qwen_oauth", "qwen"):
                if key in data and isinstance(data[key], dict):
                    data["qwen_oauth"] = data[key]
                    break
        return data


class AuthConfig(Base):
    providers: AuthProvidersConfig = Field(default_factory=AuthProvidersConfig)


# ---------------------------------------------------------------------------
# Agent configs
# ---------------------------------------------------------------------------

class AgentMemoryConfig(Base):
    semantic_search: bool = False
    auto_categorize: bool = False
    proactive: bool = False
    proactive_retry_backoff_s: float = 300.0
    proactive_max_retry_attempts: int = 3
    emotional_tracking: bool = False
    backend: str = "sqlite"
    pgvector_url: str = ""

    @field_validator("backend", mode="before")
    @classmethod
    def _normalize_backend(cls, v: Any) -> str:
        v = str(v or "sqlite").strip().lower()
        if v == "jsonl":
            return "sqlite"
        if v in {"sqlite", "pgvector", "sqlite-vec", "sqlite_vec"}:
            if v == "sqlite_vec":
                return "sqlite-vec"
            return v
        return "sqlite"

    @field_validator("proactive_retry_backoff_s", mode="before")
    @classmethod
    def _min_backoff(cls, v: Any) -> float:
        v = v if v not in (None, "") else 300.0
        return max(0.0, float(v))

    @field_validator("proactive_max_retry_attempts", mode="before")
    @classmethod
    def _min_retry(cls, v: Any) -> int:
        v = v if v not in (None, "") else 3
        return max(1, int(v))


class AgentDefaultsConfig(Base):
    model: str = "gemini/gemini-2.5-flash"
    provider: str = "auto"
    max_tokens: int = 8192
    temperature: float = 0.1
    context_token_budget: int = 7000
    max_tool_iterations: int = 40
    memory_window: int = 100
    session_retention_messages: int | None = 2000
    session_retention_ttl_s: int | None = None
    reasoning_effort: str | None = None
    semantic_history_summary_enabled: bool = False
    tool_result_compaction_enabled: bool = False
    tool_result_compaction_threshold_chars: int = 3200
    workspace_prompt_file_max_bytes: int = 16384
    semantic_memory: bool = False
    memory_auto_categorize: bool = False
    memory: AgentMemoryConfig = Field(default_factory=AgentMemoryConfig)

    @model_validator(mode="before")
    @classmethod
    def _handle_legacy_memory_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # Handle session_retention_messages: explicit None is allowed
        if "sessionRetentionMessages" in data and "session_retention_messages" not in data:
            data["session_retention_messages"] = data["sessionRetentionMessages"]
        if "sessionRetentionTtlS" in data and "session_retention_ttl_s" not in data:
            data["session_retention_ttl_s"] = data["sessionRetentionTtlS"]
        # Propagate legacy top-level memory flags into the memory sub-config
        legacy_semantic = bool(data.get("semantic_memory", data.get("semanticMemory", False)))
        legacy_auto_cat = bool(data.get("memory_auto_categorize", data.get("memoryAutoCategorize", False)))
        mem_raw = data.get("memory", {})
        if not isinstance(mem_raw, dict):
            mem_raw = {}
        mem_raw = dict(mem_raw)
        if legacy_semantic and "semantic_search" not in mem_raw and "semanticSearch" not in mem_raw:
            mem_raw["semantic_search"] = legacy_semantic
        if legacy_auto_cat and "auto_categorize" not in mem_raw and "autoCategorize" not in mem_raw:
            mem_raw["auto_categorize"] = legacy_auto_cat
        data["memory"] = mem_raw
        return data

    @field_validator("model", mode="before")
    @classmethod
    def _model_default(cls, v: Any) -> str:
        return str(v or "gemini/gemini-2.5-flash")

    @field_validator("provider", mode="before")
    @classmethod
    def _provider_default(cls, v: Any) -> str:
        return str(v or "auto")

    @field_validator("max_tokens", mode="before")
    @classmethod
    def _min_max_tokens(cls, v: Any) -> int:
        v = v if v not in (None, "") else 8192
        return max(1, int(v))

    @field_validator("context_token_budget", mode="before")
    @classmethod
    def _min_context_budget(cls, v: Any) -> int:
        v = v if v not in (None, "") else 7000
        return max(512, int(v))

    @field_validator("temperature", mode="before")
    @classmethod
    def _temperature_default(cls, v: Any) -> float:
        v = v if v not in (None, "") else 0.1
        return float(v)

    @field_validator("max_tool_iterations", mode="before")
    @classmethod
    def _min_iterations(cls, v: Any) -> int:
        v = v if v not in (None, "") else 40
        return max(1, int(v))

    @field_validator("memory_window", mode="before")
    @classmethod
    def _min_window(cls, v: Any) -> int:
        v = v if v not in (None, "") else 100
        return max(1, int(v))

    @field_validator("tool_result_compaction_threshold_chars", "workspace_prompt_file_max_bytes", mode="before")
    @classmethod
    def _min_positive_budget(cls, v: Any) -> int:
        v = v if v not in (None, "") else 1
        return max(1, int(v))

    @field_validator("session_retention_messages", mode="before")
    @classmethod
    def _session_retention(cls, v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return 2000
        return max(1, int(v))

    @field_validator("session_retention_ttl_s", mode="before")
    @classmethod
    def _session_retention_ttl(cls, v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return max(1, int(v))

    @field_validator("reasoning_effort", mode="before")
    @classmethod
    def _reasoning_effort(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None

    # Keep semantic_memory and memory_auto_categorize in sync with memory sub-config
    @model_validator(mode="after")
    def _sync_memory_flags(self) -> "AgentDefaultsConfig":
        self.semantic_memory = bool(self.memory.semantic_search)
        self.memory_auto_categorize = bool(self.memory.auto_categorize)
        return self

    # AgentDefaultsConfig doesn't have context_window_tokens in the original,
    # but gateway references it via getattr so we don't need to add it.


class AgentsConfig(Base):
    defaults: AgentDefaultsConfig = Field(default_factory=AgentDefaultsConfig)


# ---------------------------------------------------------------------------
# Scheduler (legacy, keep for compat)
# ---------------------------------------------------------------------------

class SchedulerConfig(Base):
    heartbeat_interval_seconds: int = 1800
    timezone: str = "UTC"
    cron_max_concurrent_jobs: int = 2
    cron_completed_job_retention_seconds: int = 604800


# ---------------------------------------------------------------------------
# Channel configs
# ---------------------------------------------------------------------------

class TelegramChannelConfig(Base):
    enabled: bool = False
    allow_from: list[str] = Field(default_factory=list)
    token: str = ""
    mode: str = "polling"
    webhook_enabled: bool = False
    webhook_secret: str = ""
    webhook_path: str = "/api/webhooks/telegram"
    webhook_url: str = ""
    webhook_fail_fast_on_error: bool = False
    update_dedupe_limit: int = 4096
    dedupe_state_path: str = ""
    offset_state_path: str = ""
    media_download_dir: str = ""
    transcribe_voice: bool = True
    transcribe_audio: bool = True
    transcription_api_key: str = ""
    transcription_base_url: str = "https://api.groq.com/openai/v1"
    transcription_model: str = "whisper-large-v3-turbo"
    transcription_language: str = "pt"
    transcription_timeout_s: float = 90.0
    poll_interval_s: float = 1.0
    poll_timeout_s: int = 20
    reconnect_initial_s: float = 2.0
    reconnect_max_s: float = 30.0
    send_timeout_s: float = 15.0
    send_retry_attempts: int = 1
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
    reaction_notifications: str = "own"
    reaction_own_cache_limit: int = 4096
    dm_policy: str = "open"
    group_policy: str = "open"
    topic_policy: str = "open"
    dm_allow_from: list[str] = Field(default_factory=list)
    group_allow_from: list[str] = Field(default_factory=list)
    topic_allow_from: list[str] = Field(default_factory=list)
    group_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    pairing_state_path: str = ""
    pairing_notice_cooldown_s: float = 30.0
    callback_signing_enabled: bool = False
    callback_signing_secret: str = ""
    callback_require_signed: bool = False

    @field_validator("update_dedupe_limit", mode="before")
    @classmethod
    def _min_dedupe(cls, v: Any) -> int:
        v = v if v not in (None, "") else 4096
        return max(32, int(v))

    @field_validator("reaction_own_cache_limit", mode="before")
    @classmethod
    def _min_reaction_cache(cls, v: Any) -> int:
        v = v if v not in (None, "") else 4096
        return max(1, int(v))

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # allow_from alias
        if "allow_from" not in data and "allowFrom" in data:
            data["allow_from"] = data["allowFrom"]
        # update_dedupe_limit has extra alias
        if "update_dedupe_limit" not in data and "updateDedupeLimit" not in data:
            for alias in ("webhook_dedupe_limit", "webhookDedupeLimit"):
                if alias in data:
                    data["update_dedupe_limit"] = data[alias]
                    break
        # send_timeout_s alias
        if "send_timeout_s" not in data and "sendTimeoutS" not in data and "sendTimeoutSec" in data:
            data["send_timeout_s"] = data["sendTimeoutSec"]
        # send_backoff_base_s alias
        if "send_backoff_base_s" not in data and "sendBackoffBaseS" not in data and "sendBackoffBaseSec" in data:
            data["send_backoff_base_s"] = data["sendBackoffBaseSec"]
        # send_backoff_max_s alias
        if "send_backoff_max_s" not in data and "sendBackoffMaxS" not in data and "sendBackoffMaxSec" in data:
            data["send_backoff_max_s"] = data["sendBackoffMaxSec"]
        # send_circuit_cooldown_s alias
        if "send_circuit_cooldown_s" not in data and "sendCircuitCooldownS" not in data and "sendCircuitCooldownSec" in data:
            data["send_circuit_cooldown_s"] = data["sendCircuitCooldownSec"]
        # dm_allow_from alias
        if "dm_allow_from" not in data and "dmAllowFrom" not in data:
            pass  # Will be empty list
        # group_allow_from / topic_allow_from similar - aliases handled by alias_generator
        return data


class DiscordChannelConfig(Base):
    enabled: bool = False
    allow_from: list[str] = Field(default_factory=list)
    token: str = ""
    api_base: str = "https://discord.com/api/v10"
    timeout_s: float = 10.0
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    gateway_intents: int = 46593
    gateway_backoff_base_s: float = 2.0
    gateway_backoff_max_s: float = 30.0
    typing_enabled: bool = True
    typing_interval_s: float = 8.0
    dm_policy: str = "open"
    group_policy: str = "open"
    allow_bots: str = "disabled"
    require_mention: bool = False
    ignore_other_mentions: bool = False
    reply_to_mode: str = "all"
    slash_isolated_sessions: bool = True
    status: str = ""
    activity: str = ""
    activity_type: int = 4
    activity_url: str = ""
    guilds: dict[str, dict[str, Any]] = Field(default_factory=dict)
    thread_bindings_enabled: bool = True
    thread_binding_state_path: str = ""
    thread_binding_idle_timeout_s: float = 0.0
    thread_binding_max_age_s: float = 0.0
    auto_presence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("allow_from", mode="before")
    @classmethod
    def _parse_allow_from(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(item).strip() for item in v if str(item).strip()]

    @field_validator("dm_policy", mode="before")
    @classmethod
    def _parse_dm_policy(cls, v: Any) -> str:
        policy = str(v or "open").strip().lower()
        if policy not in {"open", "allowlist", "disabled"}:
            return "open"
        return policy

    @field_validator("group_policy", mode="before")
    @classmethod
    def _parse_group_policy(cls, v: Any) -> str:
        policy = str(v or "open").strip().lower()
        if policy not in {"open", "mention", "allowlist", "disabled"}:
            return "open"
        return policy

    @field_validator("allow_bots", mode="before")
    @classmethod
    def _parse_allow_bots(cls, v: Any) -> str:
        if isinstance(v, bool):
            return "all" if v else "disabled"
        policy = str(v or "disabled").strip().lower()
        if policy in {"true", "yes", "on", "open"}:
            return "all"
        if policy in {"mentions", "mention"}:
            return "mentions"
        return "disabled"

    @field_validator("reply_to_mode", mode="before")
    @classmethod
    def _parse_reply_to_mode(cls, v: Any) -> str:
        mode = str(v or "all").strip().lower()
        if mode not in {"off", "first", "all"}:
            return "all"
        return mode

    @field_validator("status", mode="before")
    @classmethod
    def _parse_status(cls, v: Any) -> str:
        status = str(v or "").strip().lower()
        if status not in {"", "online", "idle", "dnd", "invisible"}:
            return ""
        return status

    @field_validator("activity", "activity_url", mode="before")
    @classmethod
    def _strip_optional_text(cls, v: Any) -> str:
        return str(v or "").strip()

    @field_validator("timeout_s", mode="before")
    @classmethod
    def _min_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 10.0
        return max(0.1, float(v))

    @field_validator("gateway_intents", mode="before")
    @classmethod
    def _min_intents(cls, v: Any) -> int:
        v = v if v not in (None, "") else 37377
        return max(0, int(v))

    @field_validator("activity_type", mode="before")
    @classmethod
    def _activity_type_range(cls, v: Any) -> int:
        v = v if v not in (None, "") else 4
        return min(5, max(0, int(v)))

    @field_validator("auto_presence", mode="before")
    @classmethod
    def _normalize_auto_presence(cls, v: Any) -> dict[str, Any]:
        if not isinstance(v, dict):
            return {}
        return dict(v)

    @field_validator("gateway_backoff_base_s", mode="before")
    @classmethod
    def _min_backoff_base(cls, v: Any) -> float:
        v = v if v not in (None, "") else 2.0
        return max(0.1, float(v))

    @field_validator("gateway_backoff_max_s", mode="before")
    @classmethod
    def _min_backoff_max(cls, v: Any) -> float:
        v = v if v not in (None, "") else 30.0
        return max(0.1, float(v))

    @field_validator("typing_interval_s", mode="before")
    @classmethod
    def _min_typing_interval(cls, v: Any) -> float:
        v = v if v not in (None, "") else 8.0
        return max(0.5, float(v))

    @field_validator("thread_binding_idle_timeout_s", "thread_binding_max_age_s", mode="before")
    @classmethod
    def _min_thread_binding_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 0.0
        return max(0.0, float(v))

    @field_validator("thread_binding_state_path", mode="before")
    @classmethod
    def _normalize_thread_binding_state_path(cls, v: Any) -> str:
        return str(v or "").strip()

    @field_validator("guilds", mode="before")
    @classmethod
    def _parse_guilds(cls, v: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(v, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for key, value in v.items():
            if not isinstance(value, dict):
                continue
            cleaned_key = str(key or "").strip()
            if cleaned_key:
                out[cleaned_key] = dict(value)
        return out

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "allow_from" not in data and "allowFrom" in data:
            data["allow_from"] = data["allowFrom"]
        if "reply_to_mode" not in data and "replyToMode" in data:
            data["reply_to_mode"] = data["replyToMode"]
        if "slash_isolated_sessions" not in data and "slashIsolatedSessions" in data:
            data["slash_isolated_sessions"] = data["slashIsolatedSessions"]
        if "thread_bindings_enabled" not in data and "threadBindingsEnabled" in data:
            data["thread_bindings_enabled"] = data["threadBindingsEnabled"]
        if "thread_binding_state_path" not in data and "threadBindingStatePath" in data:
            data["thread_binding_state_path"] = data["threadBindingStatePath"]
        if "thread_binding_idle_timeout_s" not in data and "threadBindingIdleTimeoutS" in data:
            data["thread_binding_idle_timeout_s"] = data["threadBindingIdleTimeoutS"]
        if "thread_binding_max_age_s" not in data and "threadBindingMaxAgeS" in data:
            data["thread_binding_max_age_s"] = data["threadBindingMaxAgeS"]
        return data


class EmailChannelConfig(Base):
    enabled: bool = False
    allow_from: list[str] = Field(default_factory=list)
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    imap_use_ssl: bool = True
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_ssl: bool = True
    smtp_use_starttls: bool = True
    poll_interval_s: float = 30.0
    mailbox: str = "INBOX"
    mark_seen: bool = True
    dedupe_state_path: str = ""
    max_body_chars: int = 12000
    from_address: str = ""

    @field_validator("allow_from", mode="before")
    @classmethod
    def _parse_allow_from(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(item).strip() for item in v if str(item).strip()]

    @field_validator("imap_port", mode="before")
    @classmethod
    def _min_imap_port(cls, v: Any) -> int:
        v = v if v not in (None, "") else 993
        return max(1, int(v))

    @field_validator("smtp_port", mode="before")
    @classmethod
    def _min_smtp_port(cls, v: Any) -> int:
        v = v if v not in (None, "") else 465
        return max(1, int(v))

    @field_validator("poll_interval_s", mode="before")
    @classmethod
    def _min_poll(cls, v: Any) -> float:
        v = v if v not in (None, "") else 30.0
        return max(1.0, float(v))

    @field_validator("mailbox", mode="before")
    @classmethod
    def _mailbox_default(cls, v: Any) -> str:
        return str(v or "INBOX").strip() or "INBOX"

    @field_validator("max_body_chars", mode="before")
    @classmethod
    def _min_body_chars(cls, v: Any) -> int:
        v = v if v not in (None, "") else 12000
        return max(256, int(v))

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "allow_from" not in data and "allowFrom" in data:
            data["allow_from"] = data["allowFrom"]
        # mailbox alias
        if "mailbox" not in data and "imapMailbox" in data:
            data["mailbox"] = data["imapMailbox"]
        return data


class SlackChannelConfig(Base):
    enabled: bool = False
    allow_from: list[str] = Field(default_factory=list)
    bot_token: str = ""
    app_token: str = ""
    api_base: str = "https://slack.com/api"
    timeout_s: float = 10.0
    send_retry_attempts: int = 3
    send_retry_after_default_s: float = 1.0
    socket_mode_enabled: bool = True
    socket_backoff_base_s: float = 1.0
    socket_backoff_max_s: float = 30.0
    typing_enabled: bool = True
    working_indicator_enabled: bool = True
    working_indicator_emoji: str = "hourglass_flowing_sand"

    @field_validator("allow_from", mode="before")
    @classmethod
    def _parse_allow_from(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(item).strip() for item in v if str(item).strip()]

    @field_validator("timeout_s", mode="before")
    @classmethod
    def _min_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 10.0
        return max(0.1, float(v))

    @field_validator(
        "send_retry_after_default_s",
        "socket_backoff_base_s",
        "socket_backoff_max_s",
        mode="before",
    )
    @classmethod
    def _min_non_negative_float(cls, v: Any) -> float:
        v = v if v not in (None, "") else 0.0
        return max(0.0, float(v))

    @field_validator("send_retry_attempts", mode="before")
    @classmethod
    def _min_retry_attempts(cls, v: Any) -> int:
        v = v if v not in (None, "") else 1
        return max(1, int(v))

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "allow_from" not in data and "allowFrom" in data:
            data["allow_from"] = data["allowFrom"]
        if "send_retry_attempts" not in data and "sendRetryAttempts" in data:
            data["send_retry_attempts"] = data["sendRetryAttempts"]
        if "send_retry_after_default_s" not in data and "sendRetryAfterDefaultS" in data:
            data["send_retry_after_default_s"] = data["sendRetryAfterDefaultS"]
        if "socket_mode_enabled" not in data and "socketModeEnabled" in data:
            data["socket_mode_enabled"] = data["socketModeEnabled"]
        if "socket_backoff_base_s" not in data and "socketBackoffBaseS" in data:
            data["socket_backoff_base_s"] = data["socketBackoffBaseS"]
        if "socket_backoff_max_s" not in data and "socketBackoffMaxS" in data:
            data["socket_backoff_max_s"] = data["socketBackoffMaxS"]
        if "typing_enabled" not in data and "typingEnabled" in data:
            data["typing_enabled"] = data["typingEnabled"]
        if "working_indicator_enabled" not in data and "workingIndicatorEnabled" in data:
            data["working_indicator_enabled"] = data["workingIndicatorEnabled"]
        if "working_indicator_emoji" not in data and "workingIndicatorEmoji" in data:
            data["working_indicator_emoji"] = data["workingIndicatorEmoji"]
        return data


class WhatsAppChannelConfig(Base):
    enabled: bool = False
    allow_from: list[str] = Field(default_factory=list)
    bridge_url: str = "ws://localhost:3001"
    bridge_token: str = ""
    timeout_s: float = 10.0
    webhook_path: str = "/api/webhooks/whatsapp"
    webhook_secret: str = ""
    send_retry_attempts: int = 3
    send_retry_after_default_s: float = 1.0
    typing_enabled: bool = True
    typing_interval_s: float = 4.0

    @field_validator("allow_from", mode="before")
    @classmethod
    def _parse_allow_from(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(item).strip() for item in v if str(item).strip()]

    @field_validator("timeout_s", "send_retry_after_default_s", "typing_interval_s", mode="before")
    @classmethod
    def _min_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 10.0
        return max(0.1, float(v))

    @field_validator("send_retry_attempts", mode="before")
    @classmethod
    def _min_retry_attempts(cls, v: Any) -> int:
        v = v if v not in (None, "") else 3
        return max(1, int(v))

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "allow_from" not in data and "allowFrom" in data:
            data["allow_from"] = data["allowFrom"]
        if "send_retry_attempts" not in data and "sendRetryAttempts" in data:
            data["send_retry_attempts"] = data["sendRetryAttempts"]
        if "send_retry_after_default_s" not in data and "sendRetryAfterDefaultS" in data:
            data["send_retry_after_default_s"] = data["sendRetryAfterDefaultS"]
        if "typing_enabled" not in data and "typingEnabled" in data:
            data["typing_enabled"] = data["typingEnabled"]
        if "typing_interval_s" not in data and "typingIntervalS" in data:
            data["typing_interval_s"] = data["typingIntervalS"]
        return data


class IRCChannelConfig(Base):
    enabled: bool = False
    host: str = "irc.libera.chat"
    port: int = 6697
    nick: str = "clawlite"
    username: str = "clawlite"
    realname: str = "ClawLite"
    channels_to_join: list[str] = Field(default_factory=list)
    use_ssl: bool = True
    connect_timeout_s: float = 10.0

    @field_validator("channels_to_join", mode="before")
    @classmethod
    def _parse_channels(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(item).strip() for item in v if str(item).strip()]

    @field_validator("port", mode="before")
    @classmethod
    def _min_port(cls, v: Any) -> int:
        v = v if v not in (None, "") else 6697
        return max(1, int(v))

    @field_validator("connect_timeout_s", mode="before")
    @classmethod
    def _min_connect_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 10.0
        return max(0.1, float(v))

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "channels_to_join" not in data and "channelsToJoin" in data:
            data["channels_to_join"] = data["channelsToJoin"]
        if "use_ssl" not in data and "useSsl" in data:
            data["use_ssl"] = data["useSsl"]
        if "connect_timeout_s" not in data and "connectTimeoutS" in data:
            data["connect_timeout_s"] = data["connectTimeoutS"]
        return data


class ChannelsConfig(Base):
    send_progress: bool = False
    send_tool_hints: bool = False
    recovery_enabled: bool = True
    recovery_interval_s: float = 15.0
    recovery_cooldown_s: float = 30.0
    replay_dead_letters_on_startup: bool = True
    replay_dead_letters_limit: int = 50
    replay_dead_letters_reasons: list[str] = Field(
        default_factory=lambda: ["send_failed", "channel_unavailable"]
    )
    delivery_persistence_path: str = ""
    telegram: TelegramChannelConfig = Field(default_factory=TelegramChannelConfig)
    discord: DiscordChannelConfig = Field(default_factory=DiscordChannelConfig)
    email: EmailChannelConfig = Field(default_factory=EmailChannelConfig)
    slack: SlackChannelConfig = Field(default_factory=SlackChannelConfig)
    whatsapp: WhatsAppChannelConfig = Field(default_factory=WhatsAppChannelConfig)
    irc: IRCChannelConfig = Field(default_factory=IRCChannelConfig)
    extra: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _extract_extra_channels(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        known = {
            "send_progress", "sendProgress",
            "send_tool_hints", "sendToolHints",
            "recovery_enabled", "recoveryEnabled",
            "recovery_interval_s", "recoveryIntervalS",
            "recovery_cooldown_s", "recoveryCooldownS",
            "replay_dead_letters_on_startup", "replayDeadLettersOnStartup",
            "replay_dead_letters_limit", "replayDeadLettersLimit",
            "replay_dead_letters_reasons", "replayDeadLettersReasons",
            "delivery_persistence_path", "deliveryPersistencePath",
            "telegram", "discord", "email", "slack", "whatsapp", "irc", "extra",
        }
        extras: dict[str, Any] = {}
        for key, value in data.items():
            if key in known:
                continue
            if isinstance(value, dict):
                extras[str(key)] = dict(value)
        if extras:
            existing = data.get("extra", {}) or {}
            data["extra"] = {**extras, **existing}
        return data

    @field_validator("recovery_interval_s", mode="before")
    @classmethod
    def _min_recovery_interval(cls, v: Any) -> float:
        v = v if v not in (None, "") else 15.0
        return max(0.1, float(v))

    @field_validator("recovery_cooldown_s", mode="before")
    @classmethod
    def _min_recovery_cooldown(cls, v: Any) -> float:
        v = v if v not in (None, "") else 30.0
        return max(0.0, float(v))

    @field_validator("replay_dead_letters_limit", mode="before")
    @classmethod
    def _min_replay_limit(cls, v: Any) -> int:
        v = v if v not in (None, "") else 50
        return max(0, int(v))

    @field_validator("replay_dead_letters_reasons", mode="before")
    @classmethod
    def _parse_reasons(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return ["send_failed", "channel_unavailable"]
        result = [str(item).strip() for item in v]
        return result or ["send_failed", "channel_unavailable"]

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = self.model_dump(by_alias=False, exclude_none=False)
        # Remove 'extra' from top level and merge it in
        extra = out.pop("extra", {})
        out.update(extra)
        return out

    def enabled_names(self) -> list[str]:
        rows: list[str] = []
        for name in ("telegram", "discord", "email", "slack", "whatsapp", "irc"):
            payload = getattr(self, name)
            if bool(payload.enabled):
                rows.append(name)
        for name, payload in self.extra.items():
            if isinstance(payload, dict) and bool(payload.get("enabled", False)):
                rows.append(name)
        return sorted(rows)


# ---------------------------------------------------------------------------
# Tool configs
# ---------------------------------------------------------------------------

class WebToolConfig(Base):
    proxy: str = ""
    timeout: float = 15.0
    search_timeout: float = 10.0
    max_redirects: int = 5
    max_chars: int = 12000
    block_private_addresses: bool = True
    brave_api_key: str = ""
    brave_base_url: str = "https://api.search.brave.com/res/v1/web/search"
    searxng_base_url: str = ""
    allowlist: list[str] = Field(default_factory=list)
    denylist: list[str] = Field(default_factory=list)

    @field_validator("timeout", mode="before")
    @classmethod
    def _min_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 15.0
        return max(1.0, float(v))

    @field_validator("search_timeout", mode="before")
    @classmethod
    def _min_search_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 10.0
        return max(1.0, float(v))

    @field_validator("max_redirects", mode="before")
    @classmethod
    def _min_redirects(cls, v: Any) -> int:
        v = v if v not in (None, "") else 5
        return max(0, int(v))

    @field_validator("max_chars", mode="before")
    @classmethod
    def _min_chars(cls, v: Any) -> int:
        v = v if v not in (None, "") else 12000
        return max(128, int(v))

    @field_validator("brave_base_url", mode="before")
    @classmethod
    def _brave_url_default(cls, v: Any) -> str:
        return str(v or "https://api.search.brave.com/res/v1/web/search")

    @field_validator("allowlist", "denylist", mode="before")
    @classmethod
    def _parse_list(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(item).strip() for item in v if str(item).strip()]


class ExecToolConfig(Base):
    timeout: int = 60
    path_append: str = ""
    deny_patterns: list[str] = Field(default_factory=list)
    allow_patterns: list[str] = Field(default_factory=list)
    deny_path_patterns: list[str] = Field(default_factory=list)
    allow_path_patterns: list[str] = Field(default_factory=list)

    @field_validator("timeout", mode="before")
    @classmethod
    def _min_timeout(cls, v: Any) -> int:
        v = v if v not in (None, "") else 60
        return max(1, int(v))

    @field_validator("deny_patterns", "allow_patterns", "deny_path_patterns", "allow_path_patterns", mode="before")
    @classmethod
    def _parse_patterns(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(item).strip() for item in v if str(item).strip()]


class MCPTransportPolicyConfig(Base):
    allowed_schemes: list[str] = Field(default_factory=lambda: ["http", "https"])
    allowed_hosts: list[str] = Field(default_factory=list)
    denied_hosts: list[str] = Field(default_factory=list)

    @field_validator("allowed_schemes", mode="before")
    @classmethod
    def _parse_schemes(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return ["http", "https"]
        result = [str(item).strip().lower() for item in v if str(item).strip()]
        return result or ["http", "https"]

    @field_validator("allowed_hosts", "denied_hosts", mode="before")
    @classmethod
    def _parse_hosts(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(item).strip().lower() for item in v if str(item).strip()]


class MCPServerConfig(Base):
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_s: float = 20.0

    @model_validator(mode="before")
    @classmethod
    def _handle_timeout_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # Extra aliases: tool_timeout_s, toolTimeoutS
        if "timeout_s" not in data and "timeoutS" not in data:
            for alias in ("tool_timeout_s", "toolTimeoutS"):
                if alias in data:
                    data["timeout_s"] = data[alias]
                    break
        return data

    @field_validator("url", mode="before")
    @classmethod
    def _strip_url(cls, v: Any) -> str:
        return str(v or "").strip()

    @field_validator("timeout_s", mode="before")
    @classmethod
    def _min_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 20.0
        return max(0.1, float(v))


class MCPToolConfig(Base):
    default_timeout_s: float = 20.0
    policy: MCPTransportPolicyConfig = Field(default_factory=MCPTransportPolicyConfig)
    servers: dict[str, MCPServerConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # defaultTimeoutS handled by alias_generator; also handle "timeout" alias
        if "default_timeout_s" not in data and "defaultTimeoutS" not in data and "timeout" in data:
            data["default_timeout_s"] = data["timeout"]
        return data

    @field_validator("default_timeout_s", mode="before")
    @classmethod
    def _min_timeout(cls, v: Any) -> float:
        v = v if v not in (None, "") else 20.0
        return max(0.1, float(v))

    @model_validator(mode="after")
    def _build_servers_with_default_timeout(self) -> "MCPToolConfig":
        # Re-apply default_timeout_s to servers that were built without it
        # Actually servers are already built; MCPServerConfig uses its own default
        # We need to propagate the default_timeout_s to servers that haven't specified one
        # But since model_validator for servers runs before this, we just accept as-is.
        return self


class ToolLoopDetectionConfig(Base):
    enabled: bool = False
    history_size: int = 20
    repeat_threshold: int = 3
    critical_threshold: int = 6

    @field_validator("history_size", mode="before")
    @classmethod
    def _min_history(cls, v: Any) -> int:
        v = v if v not in (None, "") else 20
        return max(1, int(v))

    @field_validator("repeat_threshold", mode="before")
    @classmethod
    def _min_repeat(cls, v: Any) -> int:
        v = v if v not in (None, "") else 3
        return max(1, int(v))

    @field_validator("critical_threshold", mode="before")
    @classmethod
    def _min_critical(cls, v: Any) -> int:
        v = v if v not in (None, "") else 6
        return max(1, int(v))

    @model_validator(mode="after")
    def _ensure_critical_gt_repeat(self) -> "ToolLoopDetectionConfig":
        if self.critical_threshold <= self.repeat_threshold:
            self.critical_threshold = self.repeat_threshold + 1
        return self


class ToolSafetyLayerConfig(Base):
    risky_tools: list[str] | None = None
    risky_specifiers: list[str] | None = None
    approval_specifiers: list[str] | None = None
    approval_channels: list[str] | None = None
    blocked_channels: list[str] | None = None
    allowed_channels: list[str] | None = None

    @field_validator(
        "risky_tools",
        "risky_specifiers",
        "approval_specifiers",
        "approval_channels",
        "blocked_channels",
        "allowed_channels",
        mode="before",
    )
    @classmethod
    def _parse_optional_list(cls, v: Any) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            return []
        return [str(item).strip().lower() for item in v if str(item).strip()]


class ToolSafetyPolicyConfig(Base):
    enabled: bool = True
    risky_tools: list[str] = Field(
        default_factory=lambda: ["browser", "exec", "run_skill", "web_fetch", "web_search", "mcp"]
    )
    risky_specifiers: list[str] = Field(default_factory=list)
    approval_specifiers: list[str] = Field(default_factory=list)
    approval_channels: list[str] = Field(default_factory=list)
    approval_grant_ttl_s: float = 900.0
    blocked_channels: list[str] = Field(default_factory=list)
    allowed_channels: list[str] = Field(default_factory=list)
    profile: str = ""
    profiles: dict[str, ToolSafetyLayerConfig] = Field(default_factory=dict)
    by_agent: dict[str, ToolSafetyLayerConfig] = Field(default_factory=dict)
    by_channel: dict[str, ToolSafetyLayerConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _handle_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # by_agent aliases
        if "by_agent" not in data and "byAgent" not in data and "agents" in data:
            data["by_agent"] = data["agents"]
        # by_channel aliases
        if "by_channel" not in data and "byChannel" not in data and "channels" in data:
            data["by_channel"] = data["channels"]
        return data

    @field_validator(
        "risky_tools",
        "risky_specifiers",
        "approval_specifiers",
        "approval_channels",
        "blocked_channels",
        "allowed_channels",
        mode="before",
    )
    @classmethod
    def _parse_names(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(item).strip().lower() for item in v if str(item).strip()]

    @field_validator("approval_grant_ttl_s", mode="before")
    @classmethod
    def _min_approval_ttl(cls, v: Any) -> float:
        v = v if v not in (None, "") else 900.0
        return max(1.0, float(v))

    @field_validator("profile", mode="before")
    @classmethod
    def _strip_profile(cls, v: Any) -> str:
        return str(v or "").strip().lower()

    @field_validator("profiles", "by_agent", "by_channel", mode="before")
    @classmethod
    def _normalize_layer_map_keys(cls, v: Any) -> Any:
        if not isinstance(v, dict):
            return v
        out: dict[str, Any] = {}
        for key, value in v.items():
            normalized = str(key or "").strip().lower()
            if normalized and (isinstance(value, (dict, ToolSafetyLayerConfig))):
                out[normalized] = value
        return out


class ToolsConfig(Base):
    restrict_to_workspace: bool = False
    default_timeout_s: float = 20.0
    timeouts: dict[str, float] = Field(default_factory=dict)
    web: WebToolConfig = Field(default_factory=WebToolConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    mcp: MCPToolConfig = Field(default_factory=MCPToolConfig)
    loop_detection: ToolLoopDetectionConfig = Field(default_factory=ToolLoopDetectionConfig)
    safety: ToolSafetyPolicyConfig = Field(default_factory=ToolSafetyPolicyConfig)

    @field_validator("timeouts", mode="before")
    @classmethod
    def _normalize_tool_timeouts(cls, v: Any) -> dict[str, float]:
        if not isinstance(v, dict):
            return {}
        out: dict[str, float] = {}
        for key, value in v.items():
            name = str(key or "").strip().lower()
            if not name:
                continue
            try:
                timeout_s = float(value)
            except (TypeError, ValueError):
                continue
            if timeout_s <= 0:
                continue
            out[name] = timeout_s
        return out


# ---------------------------------------------------------------------------
# Root AppConfig
# ---------------------------------------------------------------------------

_DEFAULT_WORKSPACE = str(Path.home() / ".clawlite" / "workspace")
_DEFAULT_STATE = str(Path.home() / ".clawlite" / "state")
_DEFAULT_MODEL = "gemini/gemini-2.5-flash"


class BusConfig(Base):
    backend: str = "inprocess"
    redis_url: str = ""
    redis_prefix: str = "clawlite:bus"
    journal_enabled: bool = False
    journal_path: str = ""

    @field_validator("backend", mode="before")
    @classmethod
    def _normalize_backend(cls, v: Any) -> str:
        value = str(v or "inprocess").strip().lower()
        if value in {"inprocess", "memory", "local"}:
            return "inprocess"
        if value == "redis":
            return "redis"
        return "inprocess"

    @field_validator("journal_path", mode="before")
    @classmethod
    def _journal_path_default(cls, v: Any) -> str:
        return str(v or "").strip()

    @field_validator("redis_url", "redis_prefix", mode="before")
    @classmethod
    def _string_default(cls, v: Any) -> str:
        return str(v or "").strip()


class ObservabilityConfig(Base):
    enabled: bool = False
    otlp_endpoint: str = ""
    service_name: str = "clawlite"
    service_namespace: str = ""

    @field_validator("otlp_endpoint", "service_name", "service_namespace", mode="before")
    @classmethod
    def _normalize_strings(cls, v: Any) -> str:
        return str(v or "").strip()


class JobsConfig(Base):
    persist_enabled: bool = False
    persist_path: str = ""
    worker_concurrency: int = 2

    @field_validator("worker_concurrency", mode="before")
    @classmethod
    def _min_concurrency(cls, v: Any) -> int:
        return max(1, int(v or 2))

    @field_validator("persist_path", mode="before")
    @classmethod
    def _persist_path_default(cls, v: Any) -> str:
        return str(v or "").strip()


class AppConfig(Base):
    workspace_path: str = _DEFAULT_WORKSPACE
    state_path: str = _DEFAULT_STATE
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    bus: BusConfig = Field(default_factory=BusConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    jobs: JobsConfig = Field(default_factory=JobsConfig)

    @field_validator("workspace_path", mode="before")
    @classmethod
    def _workspace_default(cls, v: Any) -> str:
        return str(v or _DEFAULT_WORKSPACE)

    @field_validator("state_path", mode="before")
    @classmethod
    def _state_default(cls, v: Any) -> str:
        return str(v or _DEFAULT_STATE)

    @model_validator(mode="after")
    def _sync_provider_model(self) -> "AppConfig":
        default_model = _DEFAULT_MODEL
        provider_model = str(self.provider.model or "").strip()
        agent_model = str(self.agents.defaults.model or "").strip()

        if provider_model != default_model and agent_model == default_model:
            self.agents.defaults.model = provider_model
        elif agent_model != default_model and provider_model == default_model:
            self.provider.model = agent_model
        elif agent_model != default_model and provider_model != default_model:
            self.provider.model = agent_model
        return self

    def to_dict(self) -> dict[str, Any]:
        out = self.model_dump(by_alias=False, exclude_none=False)
        # Flatten providers.extra into providers top-level
        providers_dump = out.get("providers", {})
        extra_providers = providers_dump.pop("extra", {})
        for k, v in extra_providers.items():
            providers_dump[k] = v
        out["providers"] = providers_dump
        # Flatten channels.extra into channels top-level
        channels_dump = out.get("channels", {})
        extra_channels = channels_dump.pop("extra", {})
        for k, v in extra_channels.items():
            channels_dump[k] = v
        out["channels"] = channels_dump
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        return cls.model_validate(data)
