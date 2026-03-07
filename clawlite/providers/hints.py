from __future__ import annotations

from typing import Any

from clawlite.providers.catalog import default_provider_model, provider_profile


def provider_transport_name(*, provider: str, spec: Any | None = None, auth_mode: str = "") -> str:
    provider_name = str(provider or "").strip().lower().replace("-", "_")
    auth_kind = str(auth_mode or "").strip().lower()
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
        _append_hint(hints, "Este provider usa transporte Anthropic-compatible; o probe consulta /messages ou /models.")
    elif transport == "openai_compatible":
        _append_hint(hints, "Este provider usa transporte OpenAI-compatible; o probe consulta /models.")
    elif transport == "oauth_openai_compatible":
        _append_hint(hints, "Este provider usa transporte OpenAI-compatible com autenticacao OAuth.")
    elif transport == "local_runtime" and provider_name == "ollama":
        _append_hint(hints, "O probe local do Ollama verifica /api/tags e confirma o modelo configurado.")
    elif transport == "local_runtime" and provider_name == "vllm":
        _append_hint(hints, "O probe local do vLLM verifica /health e /v1/models.")

    if not error_text and int(status_code or 0) < 400:
        if provider_name == "ollama":
            _append_hint(hints, "Runtime local do Ollama respondeu normalmente.")
        elif provider_name == "vllm":
            _append_hint(hints, "Runtime local do vLLM respondeu normalmente.")
        return hints

    if error_text == "api_key_missing":
        if str(auth_mode or "").strip().lower() == "oauth":
            _append_hint(hints, "Execute 'clawlite provider login openai-codex' para autenticar o Codex.")
        else:
            _append_hint(hints, f"Configure a chave do provider '{provider_name}' em config ou variavel de ambiente antes de testar novamente.")
            if key_envs:
                _append_hint(hints, f"Variaveis sugeridas: {', '.join(str(item) for item in key_envs[:3])}.")
        return hints

    if error_text == "base_url_missing":
        _append_hint(hints, f"Configure a base URL do provider '{provider_name}' antes de executar o probe novamente.")
        if default_base_url:
            _append_hint(hints, f"Base URL padrao esperada: {default_base_url}.")
        return hints

    if lowered.startswith("provider_config_error:ollama_unreachable:") or (provider_name == "ollama" and _networkish(lowered)):
        _append_hint(hints, "Inicie o runtime local com 'ollama serve' e confirme a porta 11434.")
    if lowered.startswith("provider_config_error:ollama_model_missing:"):
        model_name = error_text.rsplit(":", 1)[-1]
        _append_hint(hints, f"Baixe ou carregue o modelo local com 'ollama pull {model_name}'.")
    if lowered.startswith("provider_config_error:vllm_unreachable:") or (provider_name == "vllm" and _networkish(lowered)):
        _append_hint(hints, "Inicie o servidor vLLM e confirme a base URL configurada.")
    if lowered.startswith("provider_config_error:vllm_model_missing:"):
        model_name = error_text.rsplit(":", 1)[-1]
        _append_hint(hints, f"Suba o modelo '{model_name}' no vLLM ou ajuste o modelo configurado.")

    if lowered.startswith("http_status:401") or lowered.startswith("http_status:403"):
        _append_hint(hints, "A autenticacao foi rejeitada; revise a chave configurada e a conta associada.")
    if lowered.startswith("http_status:404"):
        if transport == "anthropic":
            _append_hint(hints, "O endpoint Anthropic-compatible nao foi encontrado; revise a api_base e a compatibilidade do provider.")
        elif provider_name in {"ollama", "vllm"}:
            _append_hint(hints, "O runtime respondeu sem a rota esperada; revise a base URL e a versao do servidor.")
        elif default_base_url:
            _append_hint(hints, f"Revise se a api_base segue o padrao esperado para este provider: {default_base_url}.")
    if lowered.startswith("http_status:429"):
        _append_hint(hints, "O provider limitou a requisicao; verifique rate limit, quota e billing.")
    if status_code >= 500:
        _append_hint(hints, "O provider remoto retornou erro 5xx; tente novamente ou use o fallback configurado.")
    if _networkish(lowered):
        _append_hint(hints, "Nao foi possivel conectar ao provider; confirme DNS, porta, firewall e disponibilidade do endpoint.")
    if "timeout" in lowered or "timed out" in lowered:
        _append_hint(hints, "O endpoint demorou para responder; aumente o timeout ou teste outro provider.")
    if detail_lowered:
        if "insufficient_quota" in detail_lowered or "billing" in detail_lowered or "quota" in detail_lowered:
            _append_hint(hints, "O detalhe do provider indica quota ou billing esgotado.")
        if "model" in detail_lowered and ("not found" in detail_lowered or "does not exist" in detail_lowered or "unknown" in detail_lowered):
            if model:
                _append_hint(hints, f"O provider rejeitou o modelo configurado; revise '{model}'.")
            else:
                _append_hint(hints, "O provider rejeitou o modelo configurado; revise o nome do modelo.")
        if "invalid api key" in detail_lowered or "unauthorized" in detail_lowered or "authentication" in detail_lowered:
            _append_hint(hints, "O detalhe retornado aponta problema de autenticacao ou permissao.")

    provider_base_url_hints: dict[str, str] = {
        "openrouter": "OpenRouter normalmente responde em https://openrouter.ai/api/v1.",
        "groq": "Groq normalmente responde em https://api.groq.com/openai/v1.",
        "gemini": "Gemini OpenAI-compatible normalmente responde em https://generativelanguage.googleapis.com/v1beta/openai.",
        "anthropic": "Anthropic normalmente responde em https://api.anthropic.com/v1.",
        "minimax": "MiniMax anthropic-compatible normalmente usa base terminando em /anthropic.",
        "xiaomi": "Xiaomi Mimo anthropic-compatible normalmente usa base terminando em /anthropic.",
        "kimi_coding": "Kimi Coding anthropic-compatible normalmente usa base em https://api.kimi.com/coding/.",
        "qianfan": "Qianfan normalmente responde em https://qianfan.baidubce.com/v2.",
        "zai": "Z.AI/GLM normalmente responde em https://api.z.ai/api/paas/v4.",
        "byteplus": "BytePlus Ark normalmente responde em https://ark.ap-southeast.bytepluses.com/api/v3.",
        "doubao": "Doubao Ark normalmente responde em https://ark.cn-beijing.volces.com/api/v3.",
        "volcengine": "Volcengine Ark normalmente responde em https://ark.cn-beijing.volces.com/api/v3.",
    }
    if status_code >= 400 or error_text:
        if provider_name in provider_base_url_hints:
            _append_hint(hints, provider_base_url_hints[provider_name])

    if endpoint and not hints and error_text:
        _append_hint(hints, f"O probe falhou na rota '{endpoint}'; revise base URL, autenticacao e disponibilidade do provider.")
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
        _append_hint(hints, "Credenciais do provider detectadas; o proximo passo e validar com provider live probe.")
    if configured and auth_mode == "none" and provider_name in {"ollama", "vllm"}:
        _append_hint(hints, "Runtime local configurado; valide se o modelo esta carregado antes de usar em producao.")
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
        _append_hint(hints, f"Transporte ativo: {transport}.")

    circuit_open = bool(payload.get("circuit_open", False) or counters.get("circuit_open", False))
    last_error_class = str(
        payload.get("last_error_class", counters.get("last_error_class", "")) or ""
    ).strip()

    if circuit_open:
        summary["state"] = "circuit_open"
        _append_hint(hints, "Circuit breaker do provider esta aberto por falhas consecutivas.")

    if provider_name == "failover":
        candidates = payload.get("candidates")
        cooling_candidates: list[dict[str, Any]] = []
        if isinstance(candidates, list):
            for row in candidates:
                if not isinstance(row, dict):
                    continue
                if not bool(row.get("in_cooldown", False)):
                    continue
                cooling_candidates.append(
                    {
                        "role": str(row.get("role", "") or ""),
                        "model": str(row.get("model", "") or ""),
                        "cooldown_remaining_s": float(row.get("cooldown_remaining_s", 0.0) or 0.0),
                    }
                )
        if cooling_candidates:
            if summary["state"] == "healthy":
                summary["state"] = "cooldown"
            summary["cooling_candidates"] = cooling_candidates
            _append_hint(hints, "Failover com candidatos temporariamente em cooldown.")
        elif int(counters.get("fallback_attempts", 0) or 0) > 0 and summary["state"] == "healthy":
            summary["state"] = "degraded"
            _append_hint(hints, "Failover ja precisou acionar fallback nesta janela de telemetria.")

    if last_error_class in {"auth", "quota", "rate_limit", "network", "http_transient", "retry_exhausted"}:
        if summary["state"] == "healthy":
            summary["state"] = "degraded"
        messages = {
            "auth": "Ultima falha foi de autenticacao; revise chave ou sessao do provider.",
            "quota": "Ultima falha indica quota ou billing esgotado.",
            "rate_limit": "Ultima falha indica rate limit no provider.",
            "network": "Ultima falha foi de rede; confirme conectividade e disponibilidade do endpoint.",
            "http_transient": "Ultima falha foi transitória no provider; o fallback ou retry deve absorver novas tentativas.",
            "retry_exhausted": "O provider esgotou tentativas de retry antes de responder com sucesso.",
        }
        _append_hint(hints, messages[last_error_class])

    if profile.onboarding_hint:
        _append_hint(hints, profile.onboarding_hint)

    summary["hints"] = hints
    return summary
