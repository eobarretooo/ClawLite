from __future__ import annotations

from typing import Any

from clawlite.providers.catalog import default_provider_model, provider_profile


def provider_transport_name(*, provider: str, spec: Any | None = None, auth_mode: str = "") -> str:
    provider_name = str(provider or "").strip().lower().replace("-", "_")
    auth_kind = str(auth_mode or "").strip().lower()
    if provider_name == "openai_codex" and auth_kind == "oauth":
        return "oauth_codex_responses"
    if auth_kind == "oauth":
        return "oauth_openai_compatible"
    if provider_name in {"ollama", "vllm"}:
        return "local_runtime"
    native_transport = str(getattr(spec, "native_transport", "") or "").strip().lower() if spec is not None else ""
    if native_transport:
        return native_transport
    if spec is not None and bool(getattr(spec, "openai_compatible", False)):
        return "openai_compatible"
    return "native"


def _append_hint(hints: list[str], text: str) -> None:
    value = str(text or "").strip()
    if value and value not in hints:
        hints.append(value)


def _networkish(error: str) -> bool:
    lowered = str(error or "").lower()
    if not lowered:
        return False
    return any(
        token in lowered
        for token in (
            "connection refused",
            "connecterror",
            "network",
            "timed out",
            "timeout",
            "dns",
            "unreachable",
            "socket",
            "refused",
            "reset by peer",
        )
    )


def provider_probe_hints(
    *,
    provider: str,
    error: str = "",
    error_detail: str = "",
    status_code: int = 0,
    auth_mode: str = "",
    transport: str = "",
    endpoint: str = "",
    default_base_url: str = "",
    key_envs: tuple[str, ...] | list[str] = (),
    model: str = "",
) -> list[str]:
    provider_name = str(provider or "").strip().lower().replace("-", "_")
    error_text = str(error or "").strip()
    detail_text = str(error_detail or "").strip()
    lowered = error_text.lower()
    detail_lowered = detail_text.lower()
    hints: list[str] = []

    if transport in {"anthropic", "anthropic_compatible"}:
        _append_hint(hints, "This provider uses Anthropic-compatible transport; the probe checks /messages or /models.")
    elif transport == "openai_compatible":
        _append_hint(hints, "This provider uses OpenAI-compatible transport; the probe checks /models.")
    elif transport == "oauth_codex_responses":
        _append_hint(hints, "This provider uses Codex Responses with OAuth; the probe checks /codex/responses.")
    elif transport == "oauth_openai_compatible":
        _append_hint(hints, "This provider uses OpenAI-compatible transport with OAuth authentication.")
    elif transport == "local_runtime" and provider_name == "ollama":
        _append_hint(hints, "The Ollama local probe checks /api/tags and verifies the configured model.")
    elif transport == "local_runtime" and provider_name == "vllm":
        _append_hint(hints, "The vLLM local probe checks /health and /v1/models.")

    if not error_text and int(status_code or 0) < 400:
        if provider_name == "ollama":
            _append_hint(hints, "The local Ollama runtime responded normally.")
        elif provider_name == "vllm":
            _append_hint(hints, "The local vLLM runtime responded normally.")
        return hints

    if error_text == "api_key_missing":
        if str(auth_mode or "").strip().lower() == "oauth":
            login_target = provider_name.replace("_", "-")
            _append_hint(hints, f"Run 'clawlite provider login {login_target}' to authenticate this OAuth provider.")
        else:
            _append_hint(hints, f"Configure the API key for provider '{provider_name}' in config or an environment variable before testing again.")
            if key_envs:
                _append_hint(hints, f"Suggested environment variables: {', '.join(str(item) for item in key_envs[:3])}.")
        return hints

    if error_text == "base_url_missing":
        _append_hint(hints, f"Configure the base URL for provider '{provider_name}' before running the probe again.")
        if default_base_url:
            _append_hint(hints, f"Expected default base URL: {default_base_url}.")
        return hints

    if lowered.startswith("provider_config_error:ollama_unreachable:") or (provider_name == "ollama" and _networkish(lowered)):
        _append_hint(hints, "Start the local runtime with 'ollama serve' and confirm port 11434.")
    if lowered.startswith("provider_config_error:ollama_model_missing:"):
        model_name = error_text.rsplit(":", 1)[-1]
        _append_hint(hints, f"Download or load the local model with 'ollama pull {model_name}'.")
    if lowered.startswith("provider_config_error:vllm_unreachable:") or (provider_name == "vllm" and _networkish(lowered)):
        _append_hint(hints, "Start the vLLM server and confirm the configured base URL.")
    if lowered.startswith("provider_config_error:vllm_model_missing:"):
        model_name = error_text.rsplit(":", 1)[-1]
        _append_hint(hints, f"Serve model '{model_name}' in vLLM or adjust the configured model.")

    if lowered.startswith("http_status:401") or lowered.startswith("http_status:403"):
        _append_hint(hints, "Authentication was rejected; review the configured key and the associated account.")
    if lowered.startswith("http_status:404"):
        if transport == "anthropic":
            _append_hint(hints, "The Anthropic-compatible endpoint was not found; review the api_base and provider compatibility.")
        elif provider_name in {"ollama", "vllm"}:
            _append_hint(hints, "The runtime responded without the expected route; review the base URL and server version.")
        elif default_base_url:
            _append_hint(hints, f"Review whether the api_base follows the expected pattern for this provider: {default_base_url}.")
    if lowered.startswith("http_status:429"):
        _append_hint(hints, "The provider rate-limited the request; check rate limits, quota, and billing.")
    if status_code >= 500:
        _append_hint(hints, "The remote provider returned a 5xx error; retry or use the configured fallback.")
    if _networkish(lowered):
        _append_hint(hints, "Could not connect to the provider; confirm DNS, port, firewall, and endpoint availability.")
    if "timeout" in lowered or "timed out" in lowered:
        _append_hint(hints, "The endpoint took too long to respond; increase the timeout or try another provider.")
    if detail_lowered:
        if "insufficient_quota" in detail_lowered or "billing" in detail_lowered or "quota" in detail_lowered:
            _append_hint(hints, "The provider detail indicates quota or billing is exhausted.")
        if "model" in detail_lowered and ("not found" in detail_lowered or "does not exist" in detail_lowered or "unknown" in detail_lowered):
            if model:
                _append_hint(hints, f"The provider rejected the configured model; review '{model}'.")
            else:
                _append_hint(hints, "The provider rejected the configured model; review the model name.")
        if "invalid api key" in detail_lowered or "unauthorized" in detail_lowered or "authentication" in detail_lowered:
            _append_hint(hints, "The returned detail points to an authentication or permission problem.")

    provider_base_url_hints: dict[str, str] = {
        "openrouter": "OpenRouter normally responds at https://openrouter.ai/api/v1.",
        "groq": "Groq normally responds at https://api.groq.com/openai/v1.",
        "gemini": "Gemini OpenAI-compatible normally responds at https://generativelanguage.googleapis.com/v1beta/openai.",
        "anthropic": "Anthropic normally responds at https://api.anthropic.com/v1.",
        "minimax": "MiniMax Anthropic-compatible usually uses a base URL ending with /anthropic.",
        "xiaomi": "Xiaomi Mimo Anthropic-compatible usually uses a base URL ending with /anthropic.",
        "kimi_coding": "Kimi Coding Anthropic-compatible usually uses a dedicated base under https://api.kimi.com/coding/.",
        "qianfan": "Qianfan normally responds at https://qianfan.baidubce.com/v2.",
        "zai": "Z.AI/GLM normally responds at https://api.z.ai/api/paas/v4.",
        "byteplus": "BytePlus Ark normally responds at https://ark.ap-southeast.bytepluses.com/api/v3.",
        "doubao": "Doubao Ark normally responds at https://ark.cn-beijing.volces.com/api/v3.",
        "volcengine": "Volcengine Ark normally responds at https://ark.cn-beijing.volces.com/api/v3.",
        "openai_codex": "OpenAI Codex OAuth normally responds at https://chatgpt.com/backend-api/codex/responses.",
    }
    if status_code >= 400 or error_text:
        if provider_name in provider_base_url_hints:
            _append_hint(hints, provider_base_url_hints[provider_name])

    if endpoint and not hints and error_text:
        _append_hint(hints, f"The probe failed on route '{endpoint}'; review the base URL, authentication, and provider availability.")
    return hints


def provider_status_hints(
    *,
    provider: str,
    configured: bool,
    auth_mode: str,
    transport: str,
    base_url: str = "",
    default_base_url: str = "",
    key_envs: tuple[str, ...] | list[str] = (),
) -> list[str]:
    provider_name = str(provider or "").strip().lower().replace("-", "_")
    hints = provider_probe_hints(
        provider=provider_name,
        error="" if configured else ("base_url_missing" if auth_mode == "none" and not base_url else "api_key_missing"),
        status_code=0,
        auth_mode=auth_mode,
        transport=transport,
        endpoint="",
        default_base_url=default_base_url,
        key_envs=key_envs,
    )
    if configured and auth_mode == "api_key":
        _append_hint(hints, "Provider credentials were detected; the next step is to validate them with a live provider probe.")
    if configured and auth_mode == "none" and provider_name in {"ollama", "vllm"}:
        _append_hint(hints, "Local runtime is configured; verify that the model is loaded before using it in production.")
    return hints


def provider_telemetry_summary(payload: dict[str, Any]) -> dict[str, Any]:
    counters_raw = payload.get("counters")
    counters = counters_raw if isinstance(counters_raw, dict) else {}
    provider_name = str(payload.get("provider_name", payload.get("provider", "")) or "").strip().lower()
    profile_name = provider_name.replace("-", "_")
    if profile_name == "failover":
        model_name = str(payload.get("model", "") or "").strip()
        if "/" in model_name:
            profile_name = model_name.split("/", 1)[0].strip().lower().replace("-", "_")
    transport = str(payload.get("transport", "") or "").strip()
    profile = provider_profile(profile_name)
    summary: dict[str, Any] = {
        "state": "healthy",
        "transport": transport,
        "family": profile.family,
        "recommended_model": default_provider_model(profile_name),
        "recommended_models": list(profile.recommended_models),
        "onboarding_hint": profile.onboarding_hint,
        "hints": [],
    }
    hints: list[str] = []

    if transport:
        _append_hint(hints, f"Active transport: {transport}.")

    circuit_open = bool(payload.get("circuit_open", False) or counters.get("circuit_open", False))
    last_error_class = str(
        payload.get("last_error_class", counters.get("last_error_class", "")) or ""
    ).strip()

    if circuit_open:
        summary["state"] = "circuit_open"
        _append_hint(hints, "The provider circuit breaker is open after consecutive failures.")

    if provider_name == "failover":
        candidates = payload.get("candidates")
        cooling_candidates: list[dict[str, Any]] = []
        suppressed_candidates: list[dict[str, Any]] = []
        if isinstance(candidates, list):
            for row in candidates:
                if not isinstance(row, dict):
                    continue
                if not bool(row.get("in_cooldown", False)):
                    continue
                suppression_reason = str(row.get("suppression_reason", "") or row.get("last_error_class", "") or "").strip().lower()
                cooling_candidates.append(
                    {
                        "role": str(row.get("role", "") or ""),
                        "model": str(row.get("model", "") or ""),
                        "cooldown_remaining_s": float(row.get("cooldown_remaining_s", 0.0) or 0.0),
                    }
                )
                if suppression_reason in {"auth", "quota", "config"}:
                    suppressed_candidates.append(
                        {
                            "role": str(row.get("role", "") or ""),
                            "model": str(row.get("model", "") or ""),
                            "suppression_reason": suppression_reason,
                            "cooldown_remaining_s": float(row.get("cooldown_remaining_s", 0.0) or 0.0),
                        }
                    )
        if cooling_candidates:
            if summary["state"] == "healthy":
                summary["state"] = "cooldown"
            summary["cooling_candidates"] = cooling_candidates
            _append_hint(hints, "Failover currently has candidates in cooldown.")
        if suppressed_candidates:
            summary["suppressed_candidates"] = suppressed_candidates
            summary["suppression_reason"] = str(suppressed_candidates[0].get("suppression_reason", "") or "")
            reason_messages = {
                "auth": "One or more failover candidates are suppressed because of authentication failure.",
                "quota": "One or more failover candidates are suppressed because quota or billing is exhausted.",
                "config": "One or more failover candidates are suppressed because of invalid configuration.",
            }
            first_reason = summary["suppression_reason"]
            if first_reason in reason_messages:
                _append_hint(hints, reason_messages[first_reason])
        elif int(counters.get("fallback_attempts", 0) or 0) > 0 and summary["state"] == "healthy":
            summary["state"] = "degraded"
            _append_hint(hints, "Failover has already used a fallback in this telemetry window.")

    if last_error_class in {"auth", "quota", "rate_limit", "network", "http_transient", "retry_exhausted"}:
        if summary["state"] == "healthy":
            summary["state"] = "degraded"
        messages = {
            "auth": "The latest failure was authentication-related; review the provider key or session.",
            "quota": "The latest failure indicates exhausted quota or billing.",
            "rate_limit": "The latest failure indicates provider rate limiting.",
            "network": "The latest failure was network-related; confirm connectivity and endpoint availability.",
            "http_transient": "The latest failure was transient; retry or failover should absorb future attempts.",
            "retry_exhausted": "The provider exhausted retry attempts before responding successfully.",
        }
        _append_hint(hints, messages[last_error_class])

    if profile.onboarding_hint:
        _append_hint(hints, profile.onboarding_hint)

    summary["hints"] = hints
    return summary
