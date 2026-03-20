from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.prompt import Prompt

from clawlite.config.loader import DEFAULT_CONFIG_PATH
from clawlite.config.loader import save_config
from clawlite.config.schema import AppConfig
from clawlite.gateway.dashboard_sessions import issue_dashboard_handoff
from clawlite.providers.catalog import ONBOARDING_PROVIDER_ORDER, default_provider_model, provider_profile
from clawlite.providers.codex import CODEX_DEFAULT_BASE_URL
from clawlite.providers.codex_auth import load_codex_auth_file
from clawlite.providers.codex_auth import resolve_codex_auth_snapshot
from clawlite.providers.discovery import normalize_local_runtime_base_url, probe_local_provider_runtime
from clawlite.providers.hints import provider_probe_hints, provider_transport_name
from clawlite.providers.model_probe import evaluate_remote_model_check, model_check_hints
from clawlite.providers.registry import SPECS
from clawlite.workspace.loader import WorkspaceLoader


def _provider_name_variants(spec_name: str, aliases: tuple[str, ...]) -> set[str]:
    values = {str(spec_name or "").strip().lower().replace("-", "_")}
    values.update(str(alias or "").strip().lower().replace("-", "_") for alias in aliases)
    return values


def _provider_spec(name: str) -> Any:
    provider_name = str(name or "").strip().lower().replace("-", "_")
    return next(
        (
            row
            for row in SPECS
            if provider_name in _provider_name_variants(row.name, row.aliases)
            and row.name not in {"custom"}
        ),
        None,
    )


_ONBOARDING_PROVIDER_IDS: list[str] = ["openai-codex", *ONBOARDING_PROVIDER_ORDER]
SUPPORTED_PROVIDERS: tuple[str, ...] = tuple(
    provider_id
    for provider_id in _ONBOARDING_PROVIDER_IDS
    if _provider_spec(provider_id) is not None
)
_PROVIDERS_REQUIRING_BASE_URL_INPUT: set[str] = {"azure_openai"}

DEFAULT_PROVIDER_BASE_URLS: dict[str, str] = {}
for provider_id in SUPPORTED_PROVIDERS:
    spec = _provider_spec(provider_id)
    if spec is None:
        continue
    default_base = str(spec.default_base_url or "").strip()
    if spec.name in {"ollama", "vllm"} and default_base:
        default_base = normalize_local_runtime_base_url(spec.name, default_base)
    DEFAULT_PROVIDER_BASE_URLS[spec.name] = default_base


def _probe_model_name(model: str, provider_key: str, aliases: tuple[str, ...]) -> str:
    normalized = str(model or "").strip()
    if "/" not in normalized:
        return normalized
    prefix, remainder = normalized.split("/", 1)
    if prefix.strip().lower().replace("-", "_") in _provider_name_variants(provider_key, aliases):
        return remainder
    return normalized


def _mask_secret(value: str, *, keep: int = 4) -> str:
    token = str(value or "").strip()
    if not token:
        return ""
    if len(token) <= keep:
        return "*" * len(token)
    return f"{'*' * max(3, len(token) - keep)}{token[-keep:]}"


def _provider_profile_payload(provider_name: str) -> dict[str, Any]:
    profile = provider_profile(provider_name)
    return {
        "family": profile.family,
        "recommended_model": default_provider_model(provider_name),
        "recommended_models": list(profile.recommended_models),
        "onboarding_hint": profile.onboarding_hint,
    }


def _model_matches_provider(model: str, provider_key: str, spec: Any | None) -> bool:
    normalized = str(model or "").strip()
    if not normalized or spec is None:
        return False

    variants = _provider_name_variants(provider_key, tuple(getattr(spec, "aliases", ()) or ()))
    lowered = normalized.lower()
    normalized_lowered = lowered.replace("-", "_")

    if "/" in lowered:
        prefix = lowered.split("/", 1)[0].strip().replace("-", "_")
        return prefix in variants

    for keyword in tuple(getattr(spec, "keywords", ()) or ()):
        keyword_text = str(keyword or "").strip().lower()
        if not keyword_text:
            continue
        if keyword_text in lowered or keyword_text.replace("-", "_") in normalized_lowered:
            return True
    return False


def _model_default_for_provider(config: AppConfig, provider_key: str, spec: Any | None) -> str:
    current_model = str(config.provider.model or "").strip()
    if current_model and _model_matches_provider(current_model, provider_key, spec):
        return current_model
    return default_provider_model(provider_key)


def _base_url_matches_provider(base_url: str, provider_key: str, spec: Any | None, default_base_url: str) -> bool:
    candidate = str(base_url or "").strip().lower().rstrip("/")
    if not candidate or spec is None:
        return False
    expected_default = str(default_base_url or "").strip().lower().rstrip("/")
    if expected_default and candidate == expected_default:
        return True
    for keyword in tuple(getattr(spec, "base_url_keywords", ()) or ()):
        keyword_text = str(keyword or "").strip().lower()
        if keyword_text and keyword_text in candidate:
            return True
    return False


def _provider_base_url_prompt_default(config: AppConfig, provider_key: str, default_base_url: str) -> str:
    current_base = str(config.provider.litellm_base_url or "").strip()
    spec = _provider_spec(provider_key)
    if current_base and _base_url_matches_provider(current_base, provider_key, spec, default_base_url):
        return current_base
    return str(default_base_url or "").strip()


def _render_provider_suggestions(provider_key: str, *, base_url: str = "", oauth_login: str = "") -> Panel:
    profile = provider_profile(provider_key)
    family = str(profile.family or "").replace("_", " ")
    recommended_models = [str(item) for item in tuple(profile.recommended_models)[:3] if str(item or "").strip()]
    body: list[str] = []
    body.append(f"[bold]Family:[/] {family or 'custom'}")
    if recommended_models:
        body.append(f"[bold]Suggested models:[/] {', '.join(recommended_models)}")
    if base_url:
        body.append(f"[bold]Base URL:[/] {base_url}")
    if oauth_login:
        body.append(f"[bold]Login:[/] {oauth_login}")
    body.append(f"[dim]{profile.onboarding_hint}[/]")
    title = f"{provider_key.replace('_', '-')} suggestions"
    return Panel.fit("\n".join(body), title=title, border_style="cyan")


def _parse_oauth_result(payload: Any) -> tuple[str, str]:
    if isinstance(payload, str):
        return payload.strip(), ""
    if isinstance(payload, dict):
        token = str(payload.get("access_token", payload.get("accessToken", payload.get("token", ""))) or "").strip()
        account = str(
            payload.get(
                "account_id",
                payload.get("accountId", payload.get("org_id", payload.get("orgId", payload.get("organization", "")))),
            )
            or ""
        ).strip()
        return token, account
    return "", ""


def resolve_codex_auth(config: AppConfig) -> dict[str, Any]:
    codex = config.auth.providers.openai_codex
    cfg_token = str(codex.access_token or "").strip()
    cfg_account = str(codex.account_id or "").strip()
    cfg_source = str(codex.source or "").strip()
    file_auth = load_codex_auth_file()

    env_token_candidates: tuple[tuple[str, str], ...] = (
        ("CLAWLITE_CODEX_ACCESS_TOKEN", os.getenv("CLAWLITE_CODEX_ACCESS_TOKEN", "").strip()),
        ("OPENAI_CODEX_ACCESS_TOKEN", os.getenv("OPENAI_CODEX_ACCESS_TOKEN", "").strip()),
        ("OPENAI_ACCESS_TOKEN", os.getenv("OPENAI_ACCESS_TOKEN", "").strip()),
    )
    env_account_candidates: tuple[tuple[str, str], ...] = (
        ("CLAWLITE_CODEX_ACCOUNT_ID", os.getenv("CLAWLITE_CODEX_ACCOUNT_ID", "").strip()),
        ("OPENAI_ORG_ID", os.getenv("OPENAI_ORG_ID", "").strip()),
    )

    env_token_name = ""
    env_token = ""
    for name, value in env_token_candidates:
        if value:
            env_token_name = name
            env_token = value
            break

    env_account = ""
    for _, value in env_account_candidates:
        if value:
            env_account = value
            break

    resolved = resolve_codex_auth_snapshot(
        config_token=cfg_token,
        config_account_id=cfg_account,
        config_source=cfg_source,
        env_token=env_token,
        env_token_name=env_token_name,
        env_account_id=env_account,
        file_auth=file_auth,
    )
    token = str(resolved.get("access_token", "") or "").strip()
    account_id = str(resolved.get("account_id", "") or "").strip()
    source = str(resolved.get("source", "") or "").strip()

    return {
        "configured": bool(token),
        "access_token": token,
        "account_id": account_id,
        "source": source,
        "token_masked": _mask_secret(token),
        "account_id_masked": _mask_secret(account_id),
    }


def _resolve_codex_auth_interactive(config: AppConfig) -> dict[str, Any]:
    token = ""
    account_id = ""
    source = ""

    try:
        import oauth_cli_kit  # type: ignore

        get_token = getattr(oauth_cli_kit, "get_token", None)
        login_oauth_interactive = getattr(oauth_cli_kit, "login_oauth_interactive", None)
        if callable(get_token):
            oauth_result = get_token()
            token, account_id = _parse_oauth_result(oauth_result)
            if token:
                source = "oauth_cli_kit:get_token"
        if (not token) and callable(login_oauth_interactive):
            oauth_result: Any = None
            try:
                oauth_result = login_oauth_interactive(provider="openai-codex")
            except TypeError:
                oauth_result = login_oauth_interactive("openai-codex")
            token, account_id = _parse_oauth_result(oauth_result)
            if token:
                source = "oauth_cli_kit:interactive"
    except Exception:
        pass

    if not token:
        status = resolve_codex_auth(config)
        token = str(status.get("access_token", "") or "").strip()
        account_id = str(status.get("account_id", "") or "").strip()
        source = str(status.get("source", "") or "").strip()

    return {
        "configured": bool(token),
        "access_token": token,
        "account_id": account_id,
        "source": source or "config",
        "token_masked": _mask_secret(token),
        "account_id_masked": _mask_secret(account_id),
    }


def _join_base(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    suffix = str(path or "").strip()
    if not suffix.startswith("/"):
        suffix = f"/{suffix}"
    return f"{base}{suffix}"


def ensure_gateway_token(config: AppConfig) -> str:
    current = str(config.gateway.auth.token or "").strip()
    if current:
        return current
    generated = uuid.uuid4().hex
    config.gateway.auth.token = generated
    return generated


def _dashboard_url_with_handoff(gateway_url: str, token: str) -> str:
    clean_url = str(gateway_url or "").strip().rstrip("/")
    clean_token = str(token or "").strip()
    if not clean_url or not clean_token:
        return clean_url
    handoff = issue_dashboard_handoff(gateway_token=clean_token)
    return f"{clean_url}#handoff={handoff.token}"


def build_dashboard_handoff(
    config: AppConfig,
    *,
    config_path: str | Path | None = None,
    variables: dict[str, str] | None = None,
    ensure_token: bool = False,
    bootstrap_pending_override: bool | None = None,
    include_sensitive: bool = True,
) -> dict[str, Any]:
    token = str(config.gateway.auth.token or "").strip()
    if not token and ensure_token:
        token = ensure_gateway_token(config)
        if config_path:
            save_config(config, path=config_path)

    gateway_url = f"http://{config.gateway.host}:{config.gateway.port}"
    dashboard_url_with_handoff = _dashboard_url_with_handoff(gateway_url, token)

    workspace_loader = WorkspaceLoader(workspace_path=config.workspace_path)
    onboarding_status_fn = getattr(workspace_loader, "onboarding_status", None)
    onboarding_status = (
        onboarding_status_fn(variables=variables or {}, persist=True)
        if callable(onboarding_status_fn)
        else {"completed": False}
    )
    bootstrap_pending = bool(
        bootstrap_pending_override
        if bootstrap_pending_override is not None
        else onboarding_status.get("bootstrap_exists", False) and not onboarding_status.get("completed", False)
    )
    onboarding_label = (
        "completed"
        if onboarding_status.get("completed")
        else "bootstrap pending" if bootstrap_pending else "not seeded"
    )
    resolved_config_path = str(Path(config_path) if config_path else DEFAULT_CONFIG_PATH)
    brave_enabled = bool(str(config.tools.web.brave_api_key or "").strip())
    searxng_enabled = bool(str(config.tools.web.searxng_base_url or "").strip())

    if brave_enabled and searxng_enabled:
        web_search_body = (
            "Web search is available with DuckDuckGo first, plus Brave and your configured SearXNG fallback. "
            "See `docs/tools.md` for backend order and network policy controls."
        )
    elif brave_enabled:
        web_search_body = (
            "Web search is available with DuckDuckGo first and Brave configured as an additional backend. "
            "See `docs/tools.md` for backend order and network policy controls."
        )
    elif searxng_enabled:
        web_search_body = (
            "Web search is available with DuckDuckGo first and your configured SearXNG backend as an additional fallback. "
            "See `docs/tools.md` for backend order and network policy controls."
        )
    else:
        web_search_body = (
            "Web search works with DuckDuckGo by default. Add `tools.web.brave_api_key` or `tools.web.searxng_base_url` "
            "later if you want more controllable search backends."
        )

    dashboard_link = dashboard_url_with_handoff if include_sensitive else gateway_url

    guidance: list[dict[str, str]] = [
        {
            "id": "dashboard",
            "title": "Dashboard",
            "body": (
                f"Open the local control plane with `clawlite dashboard --no-open` or use {dashboard_link}."
            ),
        },
        {
            "id": "token",
            "title": "Gateway token",
            "body": (
                "The gateway token is shared auth for the API and dashboard, but the packaged browser shell now exchanges "
                "that short-lived dashboard handoff for a scoped dashboard session kept only for the current tab and strips `#handoff=` "
                "from the address bar after load."
            ),
        },
        {
            "id": "web_search",
            "title": "Web search",
            "body": web_search_body,
        },
        {
            "id": "workspace_backup",
            "title": "Workspace backup",
            "body": (
                f"Back up `{config.workspace_path}` and `{resolved_config_path}` after the first successful hatch. "
                "See `docs/workspace.md` for the runtime file layout."
            ),
        },
        {
            "id": "security",
            "title": "Security",
            "body": (
                "Keep the gateway token private, restrict permissions under `~/.clawlite/`, and review `SECURITY.md` "
                "before exposing the gateway or enabling risky skills."
            ),
        },
    ]
    if bootstrap_pending:
        guidance.insert(
            1,
            {
                "id": "hatch",
                "title": "First hatch",
                "body": (
                    f"Bootstrap is still pending. Open the dashboard and use `Hatch agent`, or run `clawlite hatch`, "
                    f'which sends "{_HATCH_MESSAGE}" through the dedicated `{_HATCH_SESSION_ID}` session.'
                ),
            },
        )

    payload = {
        "gateway_url": gateway_url,
        "gateway_token_masked": _mask_secret(token, keep=8),
        "bootstrap_pending": bootstrap_pending,
        "recommended_first_message": _HATCH_MESSAGE if bootstrap_pending else "",
        "hatch_session_id": _HATCH_SESSION_ID,
        "onboarding": onboarding_status,
        "onboarding_label": onboarding_label,
        "guidance": guidance,
    }
    if include_sensitive:
        payload["dashboard_url_with_handoff"] = dashboard_url_with_handoff
        payload["dashboard_url_with_token"] = dashboard_url_with_handoff
        payload["gateway_token"] = token
    return payload


def apply_provider_selection(
    config: AppConfig,
    *,
    provider: str,
    api_key: str,
    base_url: str,
    model: str = "",
    oauth_access_token: str = "",
    oauth_account_id: str = "",
    oauth_source: str = "",
) -> dict[str, Any]:
    spec = _provider_spec(provider)
    provider_key = spec.name if spec is not None else str(provider or "").strip().lower().replace("-", "_")
    if spec is None or provider_key not in {item.replace("-", "_") for item in SUPPORTED_PROVIDERS}:
        raise ValueError(f"unsupported_provider:{provider_key}")

    selected_model = str(model or "").strip() or default_provider_model(provider_key)
    if provider_key == "openai_codex":
        selected_token = str(oauth_access_token or "").strip()
        selected_account_id = str(oauth_account_id or "").strip()
        config.provider.model = selected_model
        config.agents.defaults.model = selected_model
        config.provider.litellm_api_key = ""
        config.provider.litellm_base_url = ""
        config.auth.providers.openai_codex.access_token = selected_token
        config.auth.providers.openai_codex.account_id = selected_account_id
        config.auth.providers.openai_codex.source = str(oauth_source or "config").strip() or "config"

        selected_override = config.providers.ensure(provider_key)
        selected_override.api_key = ""
        selected_override.api_base = CODEX_DEFAULT_BASE_URL
        return {
            "provider": provider_key,
            "model": selected_model,
            "base_url": CODEX_DEFAULT_BASE_URL,
            "api_key_masked": _mask_secret(selected_token),
            "account_id_masked": _mask_secret(selected_account_id),
            "source": str(config.auth.providers.openai_codex.source or ""),
        }

    raw_base_url = str(base_url or "").strip() or DEFAULT_PROVIDER_BASE_URLS.get(provider_key, "")
    selected_base_url = (
        normalize_local_runtime_base_url(provider_key, raw_base_url)
        if provider_key in {"ollama", "vllm"} and raw_base_url
        else raw_base_url
    )
    selected_api_key = str(api_key or "").strip()

    config.provider.model = selected_model
    config.agents.defaults.model = selected_model
    config.provider.litellm_base_url = selected_base_url
    config.provider.litellm_api_key = selected_api_key

    selected_override = config.providers.ensure(provider_key)
    selected_override.api_key = selected_api_key
    selected_override.api_base = selected_base_url

    return {
        "provider": provider_key,
        "model": selected_model,
        "base_url": selected_base_url,
        "api_key_masked": _mask_secret(selected_api_key),
    }


def probe_provider(
    provider: str,
    *,
    api_key: str,
    base_url: str,
    model: str = "",
    timeout_s: float = 8.0,
    oauth_access_token: str = "",
    oauth_account_id: str = "",
) -> dict[str, Any]:
    spec = _provider_spec(provider)
    provider_key = spec.name if spec is not None else str(provider or "").strip().lower().replace("-", "_")
    selected_model = str(model or "").strip() or default_provider_model(provider_key)
    profile_payload = _provider_profile_payload(provider_key)
    if spec is None:
        return {
            "ok": False,
            "provider": provider_key,
            "error": f"unsupported_provider:{provider_key}",
            "api_key_masked": _mask_secret(api_key),
            "base_url": str(base_url or "").strip(),
            "transport": "native",
            "probe_method": "",
            "error_detail": "",
            "default_base_url": "",
            "key_envs": [],
            "model_check": {"checked": False, "ok": True, "enforced": False},
            **profile_payload,
            "hints": [],
        }

    key = str(api_key or "").strip()
    resolved_base = str(base_url or "").strip() or DEFAULT_PROVIDER_BASE_URLS.get(provider_key, "")
    if provider_key == "ollama" and resolved_base.endswith("/v1"):
        resolved_base = resolved_base[: -len("/v1")]

    headers: dict[str, str] = {}
    payload: dict[str, Any] | None = None
    probe_method = "GET"
    transport = provider_transport_name(provider=provider_key, spec=spec, auth_mode="none" if provider_key in {"ollama", "vllm"} else "api_key")
    default_base_url = str(spec.default_base_url or "")
    key_envs = list(spec.key_envs)
    model_check: dict[str, Any] = {"checked": False, "ok": True, "enforced": False}

    if provider_key not in {"ollama", "vllm", "openai_codex"} and not resolved_base:
        error = "base_url_missing"
        return {
            "ok": False,
            "provider": provider_key,
            "error": error,
            "api_key_masked": _mask_secret(api_key),
            "base_url": "",
            "transport": transport,
            "probe_method": probe_method,
            "error_detail": "",
            "default_base_url": default_base_url,
            "key_envs": key_envs,
            "model_check": model_check,
            **profile_payload,
            "hints": provider_probe_hints(
                provider=provider_key,
                error=error,
                error_detail="",
                status_code=0,
                auth_mode="api_key",
                transport=transport,
                endpoint="",
                default_base_url=default_base_url,
                key_envs=key_envs,
                model=selected_model,
            ),
        }

    if provider_key == "openai_codex":
        endpoint = "/codex/responses"
        probe_method = "POST"
        transport = provider_transport_name(provider=provider_key, spec=spec, auth_mode="oauth")
        key = str(oauth_access_token or "").strip()
        if not key:
            return {
                "ok": False,
                "provider": provider_key,
                "error": "codex_access_token_missing",
                "api_key_masked": "",
                "base_url": CODEX_DEFAULT_BASE_URL,
                "transport": transport,
                "probe_method": probe_method,
                "error_detail": "",
                "default_base_url": CODEX_DEFAULT_BASE_URL,
                "key_envs": [],
                "model_check": {"checked": False, "ok": True, "enforced": False},
                **profile_payload,
                "hints": provider_probe_hints(
                    provider=provider_key,
                    error="codex_access_token_missing",
                    error_detail="",
                    status_code=0,
                    auth_mode="oauth",
                    transport=transport,
                    endpoint=endpoint,
                    default_base_url=CODEX_DEFAULT_BASE_URL,
                    key_envs=[],
                    model=selected_model,
                ),
            }
        resolved_base = str(base_url or "").strip() or CODEX_DEFAULT_BASE_URL
        url = _join_base(resolved_base, endpoint)
        headers = {
            "Authorization": f"Bearer {key}",
            "Accept": "text/event-stream",
        }
        resolved_model = selected_model.split("/", 1)[1] if "/" in selected_model else selected_model
        payload = {
            "model": resolved_model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "ping"}],
                }
            ],
            "instructions": "You are a concise assistant. Reply briefly.",
            "tools": [],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "store": False,
            "stream": True,
        }
        key_envs = []
        default_base_url = CODEX_DEFAULT_BASE_URL
        model_check = {"checked": False, "ok": True, "enforced": False}
    elif provider_key == "ollama":
        url = _join_base(resolved_base, "/api/tags")
    elif provider_key == "vllm":
        url = _join_base(resolved_base, "/models")
        if key:
            headers["Authorization"] = f"Bearer {key}"
    elif provider_key == "anthropic":
        url = _join_base(resolved_base, "/models")
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    elif spec.native_transport == "anthropic":
        resolved_model = _probe_model_name(
            selected_model,
            provider_key,
            spec.aliases,
        )
        url = _join_base(resolved_base, "/messages")
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        payload = {
            "model": resolved_model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        probe_method = "POST"
    elif spec.openai_compatible:
        url = _join_base(resolved_base, "/models")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
    else:
        return {
            "ok": False,
            "provider": provider_key,
            "error": f"unsupported_provider:{provider_key}",
            "api_key_masked": _mask_secret(key),
            "base_url": resolved_base,
            "transport": transport,
            "probe_method": probe_method,
            "error_detail": "",
            "default_base_url": default_base_url,
            "key_envs": key_envs,
            "model_check": model_check,
            **profile_payload,
            "hints": provider_probe_hints(
                provider=provider_key,
                error=f"unsupported_provider:{provider_key}",
                error_detail="",
                status_code=0,
                auth_mode="api_key",
                transport=transport,
                endpoint="",
                default_base_url=default_base_url,
                key_envs=key_envs,
                model=selected_model,
            ),
        }

    if provider_key not in {"ollama", "vllm"} and not key:
        error = "api_key_missing"
        return {
            "ok": False,
                "provider": provider_key,
                "status_code": 0,
                "url": url,
                "base_url": resolved_base,
            "api_key_masked": "",
            "error": error,
            "body": "",
            "transport": transport,
            "probe_method": probe_method,
            "error_detail": "",
            "default_base_url": default_base_url,
            "key_envs": key_envs,
            "model_check": model_check,
            **profile_payload,
            "hints": provider_probe_hints(
                provider=provider_key,
                error=error,
                error_detail="",
                status_code=0,
                auth_mode="api_key",
                transport=transport,
                endpoint=url,
                default_base_url=default_base_url,
                key_envs=key_envs,
                model=selected_model,
            ),
        }

    try:
        with httpx.Client(timeout=max(0.5, float(timeout_s))) as client:
            if payload is None:
                response = client.get(url, headers=headers)
            else:
                response = client.post(url, headers=headers, json=payload)
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text
        error = "" if response.is_success else f"http_status:{response.status_code}"
        error_detail = ""
        if not response.is_success:
            if isinstance(body, dict):
                error_obj = body.get("error")
                if isinstance(error_obj, dict):
                    error_detail = str(error_obj.get("message", "") or error_obj.get("detail", "") or "").strip()
                elif isinstance(error_obj, str):
                    error_detail = error_obj.strip()
                if not error_detail:
                    error_detail = str(body.get("message", "") or body.get("detail", "") or "").strip()
            elif isinstance(body, str):
                error_detail = body.strip()
        elif provider_key in {"ollama", "vllm"}:
            model_check = probe_local_provider_runtime(
                model=selected_model,
                base_url=resolved_base,
                timeout_s=max(0.5, float(timeout_s)),
            )
        elif payload is None:
            model_check = evaluate_remote_model_check(
                provider=provider_key,
                model=selected_model,
                aliases=spec.aliases,
                payload=body,
                is_gateway=bool(spec.is_gateway),
            )
        hints = provider_probe_hints(
            provider=provider_key,
            error=error,
            error_detail=error_detail,
            status_code=int(response.status_code),
            auth_mode="none" if provider_key in {"ollama", "vllm"} else "api_key",
            transport=transport,
            endpoint=url,
            default_base_url=default_base_url,
            key_envs=key_envs,
            model=selected_model,
        )
        for hint in model_check_hints(model_check, model=selected_model):
            if hint not in hints:
                hints.append(hint)
        ok = bool(response.is_success)
        if provider_key in {"ollama", "vllm"}:
            ok = ok and bool(model_check.get("ok", True))
        return {
            "ok": ok,
            "provider": provider_key,
            "status_code": int(response.status_code),
            "url": url,
            "base_url": resolved_base,
            "api_key_masked": _mask_secret(key),
            "error": error,
            "body": body if response.is_success else "",
            "transport": transport,
            "probe_method": probe_method,
            "error_detail": error_detail,
            "default_base_url": default_base_url,
            "key_envs": key_envs,
            "model_check": model_check,
            **profile_payload,
            "hints": hints,
        }
    except Exception as exc:
        error = str(exc)
        hints = provider_probe_hints(
            provider=provider_key,
            error=error,
            error_detail="",
            status_code=0,
            auth_mode="none" if provider_key in {"ollama", "vllm"} else "api_key",
            transport=transport,
            endpoint=url,
            default_base_url=default_base_url,
            key_envs=key_envs,
            model=selected_model,
        )
        return {
            "ok": False,
            "provider": provider_key,
            "status_code": 0,
            "url": url,
            "base_url": resolved_base,
            "api_key_masked": _mask_secret(key),
            "error": error,
            "body": "",
            "transport": transport,
            "probe_method": probe_method,
            "error_detail": "",
            "default_base_url": default_base_url,
            "key_envs": key_envs,
            "model_check": model_check,
            **profile_payload,
            "hints": hints,
        }


def probe_telegram(token: str, *, timeout_s: float = 8.0) -> dict[str, Any]:
    clean = str(token or "").strip()
    url = f"https://api.telegram.org/bot{clean}/getMe" if clean else ""
    if not clean:
        return {
            "ok": False,
            "status_code": 0,
            "url": "",
            "token_masked": "",
            "error": "telegram_token_missing",
            "body": "",
        }
    try:
        with httpx.Client(timeout=max(0.5, float(timeout_s))) as client:
            response = client.get(url)
        body: Any
        try:
            body = response.json()
        except Exception:
            body = response.text
        ok = bool(response.is_success) and bool(isinstance(body, dict) and body.get("ok", False))
        return {
            "ok": ok,
            "status_code": int(response.status_code),
            "url": url,
            "token_masked": _mask_secret(clean),
            "error": "" if ok else "telegram_probe_failed",
            "body": body if ok else "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "url": url,
            "token_masked": _mask_secret(clean),
            "error": str(exc),
            "body": "",
        }


# Provider API key pages — shown before prompting for the key
_PROVIDER_KEY_URLS: dict[str, str] = {
    "anthropic": "https://console.anthropic.com/settings/keys",
    "openai": "https://platform.openai.com/api-keys",
    "azure_openai": "https://portal.azure.com",
    "groq": "https://console.groq.com/keys",
    "gemini": "https://aistudio.google.com/app/apikey",
    "openrouter": "https://openrouter.ai/keys",
    "aihubmix": "https://aihubmix.com",
    "siliconflow": "https://siliconflow.cn",
    "cerebras": "https://cloud.cerebras.ai",
    "together": "https://api.together.xyz/settings/api-keys",
    "mistral": "https://console.mistral.ai/api-keys/",
    "deepseek": "https://platform.deepseek.com/api_keys",
    "xai": "https://console.x.ai/",
    "huggingface": "https://huggingface.co/settings/tokens",
    "nvidia": "https://build.nvidia.com/",
    "moonshot": "https://platform.moonshot.ai/console/api-keys",
    "kilocode": "https://app.kilo.ai/settings",
    "minimax": "https://platform.minimaxi.com/user-center/basic-information/interface-key",
}

_FOX_BANNER = """\
[bold yellow]  ╔═══════════════════════════════════════╗[/]
[bold yellow]  ║[/]  [bold white]🦊  ClawLite[/]  [dim]— Autonomous AI Agent[/]  [bold yellow]║[/]
[bold yellow]  ╚═══════════════════════════════════════╝[/]"""

_SECTIONS = [
    ("model",     "Model / Provider",  "Pick AI provider + API key"),
    ("gateway",   "Gateway",           "Host, port, auth token"),
    ("channels",  "Channels",          "Telegram, WhatsApp, etc."),
    ("workspace", "Workspace",         "Files + templates"),
    ("done",      "Done",              "Save config and exit"),
]

_FLOW_CHOICES = {
    "1": "quickstart",
    "quickstart": "quickstart",
    "quick-start": "quickstart",
    "2": "advanced",
    "advanced": "advanced",
    "manual": "advanced",
}

_SUPPORTED_FLOWS = {"quickstart", "advanced"}
_HATCH_MESSAGE = "Wake up, my friend!"
_HATCH_SESSION_ID = "hatch:operator"


def _print_banner(console: Console) -> None:
    console.print("")
    console.print(_FOX_BANNER)
    console.print("")


def _section_menu(console: Console, done_label: str = "Done") -> str:
    """Show a numbered section menu and return the chosen section key."""
    console.print("  [bold]What do you want to configure?[/]\n")
    for i, (key, label, hint) in enumerate(_SECTIONS, 1):
        lbl = done_label if key == "done" else label
        if key == "done":
            console.print(f"  [dim]{i}.[/]  [bold]{lbl}[/]")
        else:
            console.print(f"  [dim]{i}.[/]  [bold]{label}[/]  [dim]— {hint}[/]")
    console.print("")
    valid = {str(i): key for i, (key, _, _) in enumerate(_SECTIONS, 1)}
    valid.update({key: key for key, _, _ in _SECTIONS})
    while True:
        raw = Prompt.ask("  Choose", default="1").strip().lower()
        if raw in valid:
            return valid[raw]
        console.print(f"  [red]Invalid choice:[/] {raw!r}  (enter a number 1-{len(_SECTIONS)})")


def _flow_menu(console: Console) -> str:
    console.print("  [bold]Choose your setup flow:[/]\n")
    console.print("  [dim]1.[/]  [bold]QuickStart[/]  [dim]- provider, secure local gateway, optional Telegram, workspace[/]")
    console.print("  [dim]2.[/]  [bold]Advanced[/]    [dim]- configure sections manually[/]")
    console.print("")
    while True:
        raw = Prompt.ask("  Flow", default="1").strip().lower()
        flow = _FLOW_CHOICES.get(raw)
        if flow is not None:
            return flow
        console.print("  [red]Invalid choice:[/] enter 1 for QuickStart or 2 for Advanced")


def _normalize_flow(value: str | None) -> str | None:
    if value is None:
        return None
    return _FLOW_CHOICES.get(str(value).strip().lower())


def _probe_result(console: Console, probe: dict[str, Any], *, label: str) -> None:
    ok = bool(probe.get("ok", False))
    icon = "[green]✓[/]" if ok else "[red]✗[/]"
    console.print(f"  {icon} {label} probe: {'[green]OK[/]' if ok else '[red]FAILED[/]'}")
    if not ok:
        error = str(probe.get("error", "") or "")
        detail = str(probe.get("error_detail", "") or "")
        if error:
            console.print(f"    [yellow]Error:[/] {error}")
        if detail:
            console.print(f"    [yellow]Detail:[/] {detail[:200]}")
        for hint in list(probe.get("hints", []) or [])[:3]:
            console.print(f"    [dim]→ {hint}[/]")


def _section_header(console: Console, title: str, hint: str = "") -> None:
    sep = "─" * 42
    console.print(f"\n  [bold cyan]{sep}[/]")
    console.print(f"  [bold cyan]{title}[/]" + (f"  [dim]{hint}[/]" if hint else ""))
    console.print(f"  [bold cyan]{sep}[/]\n")


def _configure_model(
    console: Console,
    config: AppConfig,
    *,
    allow_continue_on_probe_failure: bool = True,
) -> tuple[str, str, str, str, dict[str, Any], dict[str, Any]]:
    """Interactive model section. Returns (provider, api_key, base_url, model, probe, oauth)."""
    _section_header(console, "Model / Provider", "pick your AI backend")

    # Show provider table
    console.print("  [bold]Available providers:[/]\n")
    rows: list[tuple[str, str]] = []
    for pid in SUPPORTED_PROVIDERS:
        url = _PROVIDER_KEY_URLS.get(pid, "")
        rows.append((pid, url))
    for pid, url in rows:
        url_part = f"  [dim]{url}[/]" if url else ""
        console.print(f"    [cyan]{pid:<18}[/]{url_part}")
    console.print("")

    current_provider = str(config.provider.litellm_api_key and "openai" or "openai")
    while True:
        provider = Prompt.ask("  Provider", default=current_provider).strip().lower()
        if _provider_spec(provider) is not None:
            break
        console.print(f"  [red]Unknown provider:[/] {provider!r}  (see list above)")
    provider_spec = _provider_spec(provider)
    provider_key = provider_spec.name if provider_spec is not None else provider

    # Show key URL if available
    key_url = _PROVIDER_KEY_URLS.get(provider_key, "")
    if key_url and provider_key not in {"ollama", "vllm"}:
        console.print(f"\n  [dim]Get your API key at:[/] [underline]{key_url}[/]\n")

    provider_default_base = DEFAULT_PROVIDER_BASE_URLS.get(provider_key, "")
    base_url = _provider_base_url_prompt_default(config, provider_key, provider_default_base)
    model_default = _model_default_for_provider(config, provider_key, provider_spec)
    oauth_login = f"clawlite provider login {provider_key.replace('_', '-')}" if provider_key in {
        "openai_codex",
        "gemini_oauth",
        "qwen_oauth",
    } else ""
    suggestion_base_url = (
        "your Azure OpenAI `/openai/v1` resource endpoint"
        if provider_key in _PROVIDERS_REQUIRING_BASE_URL_INPUT
        else base_url
    )
    console.print("")
    console.print(_render_provider_suggestions(provider_key, base_url=suggestion_base_url, oauth_login=oauth_login))
    console.print("")

    api_key = ""
    oauth_payload: dict[str, Any] = {"access_token": "", "account_id": "", "source": ""}
    if provider_key == "openai_codex":
        console.print("\n  [dim]Codex uses your local OAuth session (for example ~/.codex/auth.json).[/]")
        console.print("  [dim]ClawLite will reuse it or trigger interactive login if needed.[/]\n")
        oauth_status = _resolve_codex_auth_interactive(config)
        if bool(oauth_status.get("configured", False)):
            source_label = str(oauth_status.get("source", "") or "").strip()
            source_suffix = f"  [dim]({source_label})[/]" if source_label else ""
            console.print(f"  [green]✓[/] Codex auth found: {oauth_status.get('token_masked', '')}{source_suffix}")
        else:
            console.print("  [red]✗[/] Codex auth not found.")
        oauth_payload = {
            "access_token": str(oauth_status.get("access_token", "") or "").strip(),
            "account_id": str(oauth_status.get("account_id", "") or "").strip(),
            "source": str(oauth_status.get("source", "") or "").strip(),
        }
        base_url = CODEX_DEFAULT_BASE_URL
    elif provider_key not in {"ollama", "vllm"}:
        api_key = Prompt.ask(f"  {provider} API key", password=True)
        if provider_key in _PROVIDERS_REQUIRING_BASE_URL_INPUT or not provider_default_base:
            base_url = Prompt.ask(f"  {provider} base URL", default=base_url)
    else:
        base_url = Prompt.ask(f"  {provider} base URL", default=base_url)

    selected_model = Prompt.ask("  Model", default=model_default)

    console.print("\n  [dim]Probing provider...[/]")
    probe = probe_provider(
        provider,
        api_key=api_key,
        base_url=base_url,
        model=selected_model,
        oauth_access_token=str(oauth_payload.get("access_token", "") or ""),
        oauth_account_id=str(oauth_payload.get("account_id", "") or ""),
    )
    _probe_result(console, probe, label=provider)

    if not bool(probe.get("ok", False)):
        if not allow_continue_on_probe_failure:
            raise KeyboardInterrupt
        if not Confirm.ask("\n  Probe failed — continue anyway?", default=False):
            raise KeyboardInterrupt
    return provider, api_key, base_url, selected_model, probe, oauth_payload


def _configure_gateway(console: Console, config: AppConfig) -> None:
    _section_header(console, "Gateway", "host, port, auth")

    current_host = str(config.gateway.host or "127.0.0.1").strip()
    current_port = int(config.gateway.port or 8787)
    current_auth = str(config.gateway.auth.mode or "off").strip().lower()
    if current_auth not in {"off", "optional", "required"}:
        current_auth = "off"

    host = Prompt.ask("  Host", default=current_host)
    port_raw = Prompt.ask("  Port", default=str(current_port))
    auth_mode = Prompt.ask(
        "  Auth mode",
        choices=["off", "optional", "required"],
        default=current_auth,
    )

    try:
        port = int(port_raw)
    except Exception:
        port = 8787

    config.gateway.host = host.strip() or "127.0.0.1"
    config.gateway.port = max(1, port)
    config.gateway.auth.mode = auth_mode

    # Always ensure token exists
    token = ensure_gateway_token(config)
    console.print(f"\n  [dim]Gateway token:[/] {_mask_secret(token, keep=8)}")
    console.print(f"  [dim]Gateway URL:[/]   http://{config.gateway.host}:{config.gateway.port}\n")


def _configure_gateway_quickstart(console: Console, config: AppConfig) -> None:
    _section_header(console, "Gateway", "QuickStart defaults")

    host = str(config.gateway.host or "").strip() or "127.0.0.1"
    port = int(config.gateway.port or 8787)
    auth_mode = str(config.gateway.auth.mode or "").strip().lower()
    if auth_mode not in {"optional", "required"}:
        auth_mode = "required"

    config.gateway.host = host
    config.gateway.port = max(1, port)
    config.gateway.auth.mode = auth_mode
    token = ensure_gateway_token(config)

    console.print("  [green]✓[/] QuickStart keeps the gateway local and token-protected.")
    console.print(f"  [dim]Host:[/]          {config.gateway.host}")
    console.print(f"  [dim]Port:[/]          {config.gateway.port}")
    console.print(f"  [dim]Auth mode:[/]     {config.gateway.auth.mode}")
    console.print(f"  [dim]Gateway token:[/] {_mask_secret(token, keep=8)}")
    console.print(f"  [dim]Gateway URL:[/]   http://{config.gateway.host}:{config.gateway.port}\n")


def _configure_channels(
    console: Console,
    config: AppConfig,
    *,
    allow_continue_on_probe_failure: bool = True,
) -> dict[str, Any]:
    _section_header(console, "Channels", "messaging integrations")

    telegram_probe: dict[str, Any] = {"ok": True, "status_code": 0, "token_masked": "", "error": ""}
    telegram_enabled = Confirm.ask("  Enable Telegram bot?", default=bool(config.channels.telegram.enabled))

    if telegram_enabled:
        console.print("\n  [dim]Create a bot at:[/] [underline]https://t.me/BotFather[/]")
        console.print("  [dim]Send[/] /newbot [dim]and copy the token.\n[/]")
        telegram_token = Prompt.ask("  Telegram bot token", password=True)
        console.print("\n  [dim]Probing Telegram...[/]")
        telegram_probe = probe_telegram(telegram_token)
        _probe_result(console, telegram_probe, label="Telegram")
        if not bool(telegram_probe.get("ok", False)):
            if not allow_continue_on_probe_failure:
                raise KeyboardInterrupt
            if not Confirm.ask("\n  Probe failed — continue anyway?", default=False):
                raise KeyboardInterrupt
        config.channels.telegram.enabled = True
        config.channels.telegram.token = str(telegram_token or "").strip()
    else:
        config.channels.telegram.enabled = False

    return telegram_probe


def _configure_workspace(console: Console, config: AppConfig, *, overwrite: bool, variables: dict[str, str]) -> list[Any]:
    _section_header(console, "Workspace", "files + templates")
    console.print(f"  [dim]Current path:[/] {config.workspace_path}\n")
    loader = WorkspaceLoader(workspace_path=config.workspace_path)
    generated_files = loader.bootstrap(overwrite=bool(overwrite), variables=variables)
    if generated_files:
        console.print(f"  [green]✓[/] Created {len(generated_files)} file(s)")
        for f in generated_files[:5]:
            console.print(f"    [dim]{f}[/]")
    else:
        console.print("  [dim]Workspace already exists — no files changed.[/]")
    return generated_files


def _run_quickstart_flow(
    console: Console,
    config: AppConfig,
    *,
    overwrite: bool,
    variables: dict[str, str],
) -> dict[str, Any]:
    console.print(
        Panel(
            "[bold]QuickStart[/] sets up a local gateway, validates your provider live, "
            "offers Telegram, and generates the workspace files in one guided pass.",
            border_style="cyan",
            padding=(0, 2),
        )
    )

    provider_key = ""
    provider_probe: dict[str, Any] = {}
    provider_persisted: dict[str, Any] = {}
    telegram_probe: dict[str, Any] = {"ok": True, "status_code": 0, "token_masked": "", "error": ""}

    prov, api_key, base_url, sel_model, provider_probe, oauth_payload = _configure_model(
        console,
        config,
        allow_continue_on_probe_failure=False,
    )
    provider_key = prov
    provider_persisted = apply_provider_selection(
        config,
        provider=prov,
        api_key=api_key,
        base_url=base_url,
        model=sel_model,
        oauth_access_token=str(oauth_payload.get("access_token", "") or ""),
        oauth_account_id=str(oauth_payload.get("account_id", "") or ""),
        oauth_source=str(oauth_payload.get("source", "") or ""),
    )

    _configure_gateway_quickstart(console, config)
    telegram_probe = _configure_channels(
        console,
        config,
        allow_continue_on_probe_failure=False,
    )
    generated_files = _configure_workspace(console, config, overwrite=overwrite, variables=variables)

    return {
        "provider_key": provider_key,
        "provider_probe": provider_probe,
        "provider_persisted": provider_persisted,
        "telegram_probe": telegram_probe,
        "generated_files": generated_files,
        "visited_sections": ["model", "gateway", "channels", "workspace"],
    }


def _run_advanced_flow(
    console: Console,
    config: AppConfig,
    *,
    overwrite: bool,
    variables: dict[str, str],
) -> dict[str, Any]:
    provider_key: str = ""
    provider_probe: dict[str, Any] = {}
    telegram_probe: dict[str, Any] = {"ok": True, "status_code": 0, "token_masked": "", "error": ""}
    generated_files: list[Any] = []
    provider_persisted: dict[str, Any] = {}
    visited: set[str] = set()

    while True:
        console.print("")
        choice = _section_menu(console)

        if choice == "done":
            if not visited:
                console.print("  [yellow]No sections configured yet.[/]")
                if not Confirm.ask("  Exit without saving?", default=False):
                    continue
            break

        if choice == "model":
            try:
                prov, api_key, base_url, sel_model, probe, oauth_payload = _configure_model(console, config)
                provider_key = prov
                provider_probe = probe
                provider_persisted = apply_provider_selection(
                    config,
                    provider=prov,
                    api_key=api_key,
                    base_url=base_url,
                    model=sel_model,
                    oauth_access_token=str(oauth_payload.get("access_token", "") or ""),
                    oauth_account_id=str(oauth_payload.get("account_id", "") or ""),
                    oauth_source=str(oauth_payload.get("source", "") or ""),
                )
                visited.add("model")
                console.print("  [green]✓[/] Model section saved.\n")
            except KeyboardInterrupt:
                console.print("  [yellow]Model section cancelled.[/]")
            continue

        if choice == "gateway":
            _configure_gateway(console, config)
            visited.add("gateway")
            console.print("  [green]✓[/] Gateway section saved.\n")
            continue

        if choice == "channels":
            try:
                telegram_probe = _configure_channels(console, config)
                visited.add("channels")
                console.print("  [green]✓[/] Channels section saved.\n")
            except KeyboardInterrupt:
                console.print("  [yellow]Channels section cancelled.[/]")
            continue

        if choice == "workspace":
            generated_files = _configure_workspace(
                console,
                config,
                overwrite=overwrite,
                variables=variables,
            )
            visited.add("workspace")
            console.print("  [green]✓[/] Workspace section saved.\n")

    return {
        "provider_key": provider_key,
        "provider_probe": provider_probe,
        "provider_persisted": provider_persisted,
        "telegram_probe": telegram_probe,
        "generated_files": generated_files,
        "visited_sections": sorted(visited),
    }


def _configure_memory(console: Console, config: AppConfig) -> None:
    """Interactive memory configuration."""
    console.print("\n  [bold cyan]Memory Settings[/]\n")
    mem = config.agents.defaults.memory

    backend = Prompt.ask(
        "  Memory backend",
        choices=["sqlite", "pgvector"],
        default=mem.backend,
    )
    mem.backend = backend

    proactive = Confirm.ask(
        "  Enable proactive context loader",
        default=mem.proactive,
    )
    mem.proactive = proactive

    auto_cat = Confirm.ask(
        "  Enable auto-categorize",
        default=mem.auto_categorize,
    )
    mem.auto_categorize = auto_cat

    semantic = Confirm.ask(
        "  Enable semantic search",
        default=mem.semantic_search,
    )
    mem.semantic_search = semantic

    if proactive:
        backoff = Prompt.ask(
            "  Proactive retry backoff (seconds)",
            default=str(int(mem.proactive_retry_backoff_s)),
        )
        try:
            mem.proactive_retry_backoff_s = float(backoff)
        except ValueError:
            pass

    console.print("  [green]✓[/] Memory settings updated.\n")


def _configure_context_budget(console: Console, config: AppConfig) -> None:
    """Interactive context budget configuration."""
    console.print("\n  [bold cyan]Context Budget[/]\n")
    d = config.agents.defaults

    for field, label, cast in [
        ("max_tokens",          "Max tokens per turn",       int),
        ("temperature",         "Temperature (0.0-2.0)",     float),
        ("max_tool_iterations", "Max tool iterations",       int),
        ("memory_window",       "Memory window (messages)",  int),
    ]:
        current = getattr(d, field)
        raw = Prompt.ask(f"  {label}", default=str(current))
        try:
            setattr(d, field, cast(raw))
        except (ValueError, TypeError):
            pass

    console.print("  [green]✓[/] Context budget updated.\n")


def _configure_jobs(console: Console, config: AppConfig) -> None:
    """Interactive jobs configuration."""
    console.print("\n  [bold cyan]Job Workers[/]\n")

    workers = Prompt.ask("  Worker concurrency", default=str(config.jobs.worker_concurrency))
    try:
        config.jobs.worker_concurrency = max(1, int(workers))
    except (ValueError, TypeError):
        pass

    persist = Confirm.ask("  Persist jobs to disk (survive restart)", default=config.jobs.persist_enabled)
    config.jobs.persist_enabled = persist

    if persist:
        path = Prompt.ask("  Jobs persist path (blank = default)", default=config.jobs.persist_path or "")
        config.jobs.persist_path = path.strip()

    console.print("  [green]✓[/] Job settings updated.\n")


def _configure_bus(console: Console, config: AppConfig) -> None:
    """Interactive bus/journal configuration."""
    console.print("\n  [bold cyan]Event Bus[/]\n")

    enabled = Confirm.ask("  Enable bus journal (persist events to SQLite)", default=config.bus.journal_enabled)
    config.bus.journal_enabled = enabled

    if enabled:
        path = Prompt.ask("  Journal path (blank = default)", default=config.bus.journal_path or "")
        config.bus.journal_path = path.strip()

    console.print("  [green]✓[/] Bus settings updated.\n")


def _configure_tool_safety(console: Console, config: AppConfig) -> None:
    """Interactive tool safety configuration.

    Note: ExecToolConfig and WebToolConfig have no 'enabled' flag.
    Covers: safety policy, workspace restriction, loop detection, exec timeout.
    """
    console.print("\n  [bold cyan]Tool Safety[/]\n")

    config.tools.safety.enabled = Confirm.ask(
        "  Enable tool safety policy", default=config.tools.safety.enabled)
    config.tools.restrict_to_workspace = Confirm.ask(
        "  Restrict file access to workspace directory", default=config.tools.restrict_to_workspace)

    loop = Confirm.ask("  Enable tool loop detection", default=config.tools.loop_detection.enabled)
    config.tools.loop_detection.enabled = loop
    if loop:
        for field, label in [
            ("history_size",       "Loop detection history size"),
            ("repeat_threshold",   "Repeat threshold (warn)"),
            ("critical_threshold", "Critical threshold (block)"),
        ]:
            raw = Prompt.ask(f"  {label}", default=str(getattr(config.tools.loop_detection, field)))
            try:
                setattr(config.tools.loop_detection, field, int(raw))
            except (ValueError, TypeError):
                pass

    exec_timeout = Prompt.ask("  Exec tool timeout (seconds)", default=str(config.tools.exec.timeout))
    try:
        config.tools.exec.timeout = max(1, int(exec_timeout))
    except (ValueError, TypeError):
        pass

    console.print("  [green]✓[/] Tool safety settings updated.\n")


def _configure_autonomy(console: Console, config: AppConfig) -> None:
    """Interactive autonomy configuration."""
    console.print("\n  [bold cyan]Autonomy Controls[/]\n")

    aut = config.gateway.autonomy
    aut.enabled = Confirm.ask("  Enable autonomy loop", default=aut.enabled)
    if aut.enabled:
        for field, label, cast in [
            ("interval_s",          "Autonomy check interval (seconds)", int),
            ("cooldown_s",          "Cooldown between actions (seconds)", int),
            ("max_actions_per_run", "Max actions per run",                int),
        ]:
            raw = Prompt.ask(f"  {label}", default=str(getattr(aut, field)))
            try:
                setattr(aut, field, cast(raw))
            except (ValueError, TypeError):
                pass

    console.print("  [green]✓[/] Autonomy settings updated.\n")



def run_onboarding_wizard(
    config: AppConfig,
    *,
    config_path: str | Path | None,
    overwrite: bool = False,
    variables: dict[str, str] | None = None,
    flow: str | None = None,
) -> dict[str, Any]:
    console = Console(stderr=True, soft_wrap=True)

    # Accumulated state
    provider_key: str = ""
    provider_probe: dict[str, Any] = {}
    telegram_probe: dict[str, Any] = {"ok": True, "status_code": 0, "token_masked": "", "error": ""}
    generated_files: list[Any] = []
    provider_persisted: dict[str, Any] = {}

    # Track which sections were visited
    visited: set[str] = set()

    try:
        _print_banner(console)
        console.print(
            Panel(
                "[bold]Welcome to ClawLite![/]  This wizard helps you configure your agent.\n"
                "[dim]Choose QuickStart for the guided path or Advanced to configure sections manually. "
                "Press Ctrl+C at any time to cancel.[/]",
                border_style="cyan",
                padding=(0, 2),
            )
        )
        selected_flow = _normalize_flow(flow)
        if flow is not None and selected_flow is None:
            console.print(f"\n  [yellow]Unknown flow override:[/] {flow!r}. Falling back to interactive selection.\n")
        flow = selected_flow or _flow_menu(console)
        flow_result = (
            _run_quickstart_flow(
                console,
                config,
                overwrite=overwrite,
                variables=variables or {},
            )
            if flow == "quickstart"
            else _run_advanced_flow(
                console,
                config,
                overwrite=overwrite,
                variables=variables or {},
            )
        )
        provider_key = str(flow_result.get("provider_key", "") or "")
        provider_probe = dict(flow_result.get("provider_probe", {}) or {})
        telegram_probe = dict(flow_result.get("telegram_probe", telegram_probe) or {})
        generated_files = list(flow_result.get("generated_files", []) or [])
        provider_persisted = dict(flow_result.get("provider_persisted", {}) or {})
        visited = set(flow_result.get("visited_sections", []) or [])

        # Ensure gateway token always exists
        generated_token = ensure_gateway_token(config)
        saved_path = save_config(config, path=config_path)
        generated_bootstrap = any(Path(path).name == "BOOTSTRAP.md" for path in generated_files)
        handoff = build_dashboard_handoff(
            config,
            config_path=config_path,
            variables=variables or {},
            ensure_token=False,
            bootstrap_pending_override=generated_bootstrap or None,
        )
        gateway_url = str(handoff["gateway_url"])
        dashboard_url_with_handoff = str(handoff.get("dashboard_url_with_handoff") or handoff["dashboard_url_with_token"])
        onboarding_status = dict(handoff["onboarding"])
        bootstrap_pending = bool(generated_bootstrap or handoff["bootstrap_pending"])
        onboarding_label = "completed" if onboarding_status.get("completed") else "bootstrap pending" if bootstrap_pending else str(handoff["onboarding_label"])

        tg_status = "[green]enabled[/]" if config.channels.telegram.enabled else "[dim]disabled[/]"
        token_display = _mask_secret(generated_token, keep=8)
        provider_display = provider_key or str(config.provider.litellm_api_key and "configured" or "not set")
        model_display = str(config.provider.model or "default")

        sections_done = ", ".join(sorted(visited)) if visited else "none"
        summary_text = (
            f"[bold green]🦊 ClawLite is ready![/]\n\n"
            f"  [bold]Gateway URL:[/]   {gateway_url}\n"
            f"  [bold]Token:[/]         {token_display}\n"
            f"  [bold]Flow:[/]          {flow}\n"
            f"  [bold]Provider:[/]      {provider_display} / {model_display}\n"
            f"  [bold]Telegram:[/]      {tg_status}\n"
            f"  [bold]Sections:[/]      {sections_done}\n"
            f"  [bold]Onboarding:[/]    {onboarding_label}\n"
        )
        if bootstrap_pending:
            summary_text += (
                f"  [bold]First hatch:[/]    Open the dashboard and click Hatch agent  "
                f"[dim](sends \"{_HATCH_MESSAGE}\")[/]\n"
            )
        summary_text += (
            f"  [bold]Config saved:[/]  {saved_path}\n\n"
            f"[dim]Start the agent:[/]  [bold cyan]clawlite start[/]\n"
            f"[dim]Dashboard:[/]        [bold cyan]{gateway_url}[/]\n"
            f"[dim]Dashboard + handoff:[/] [bold cyan]{dashboard_url_with_handoff}[/]"
        )

        console.print(
            Panel(
                summary_text,
                title="[green]Setup complete[/]",
                border_style="green",
                padding=(1, 2),
            )
        )
        guidance_lines = [
            f"[bold]{item['title']}[/]\n{item['body']}"
            for item in list(handoff.get("guidance", []) or [])
            if item.get("title") and item.get("body")
        ]
        if guidance_lines:
            console.print(
                Panel(
                    "\n\n".join(guidance_lines),
                    title="[cyan]Next steps[/]",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )

        return {
            "ok": True,
            "mode": "wizard",
            "flow": flow,
            "saved_path": str(saved_path),
            "visited_sections": sorted(visited),
            "persisted": {
                "provider": provider_persisted,
                "gateway": {
                    "host": str(config.gateway.host),
                    "port": int(config.gateway.port),
                    "auth_mode": str(config.gateway.auth.mode),
                    "token_masked": _mask_secret(generated_token),
                },
                "telegram": {
                    "enabled": bool(config.channels.telegram.enabled),
                    "token_masked": _mask_secret(config.channels.telegram.token),
                },
            },
            "workspace": {
                "path": str(config.workspace_path),
                "created_files": [str(path) for path in generated_files],
                "onboarding": onboarding_status,
            },
            "probes": {
                "provider": {
                    "ok": bool(provider_probe.get("ok", False)),
                    "status_code": int(provider_probe.get("status_code", 0) or 0),
                    "error": str(provider_probe.get("error", "") or ""),
                    "api_key_masked": str(provider_probe.get("api_key_masked", "") or ""),
                    "transport": str(provider_probe.get("transport", "") or ""),
                    "probe_method": str(provider_probe.get("probe_method", "") or ""),
                    "hints": list(provider_probe.get("hints", []) or []),
                },
                "telegram": {
                    "ok": bool(telegram_probe.get("ok", False)),
                    "status_code": int(telegram_probe.get("status_code", 0) or 0),
                    "error": str(telegram_probe.get("error", "") or ""),
                    "token_masked": str(telegram_probe.get("token_masked", "") or ""),
                },
            },
            "final": {
                "gateway_url": gateway_url,
                "dashboard_url_with_handoff": dashboard_url_with_handoff,
                "dashboard_url_with_token": dashboard_url_with_handoff,
                "gateway_token": generated_token,
                "bootstrap_pending": bootstrap_pending,
                "recommended_first_message": _HATCH_MESSAGE if bootstrap_pending else str(handoff["recommended_first_message"]),
                "hatch_session_id": str(handoff["hatch_session_id"]),
                "guidance": list(handoff.get("guidance", []) or []),
            },
        }
    except KeyboardInterrupt:
        console.print("\n  [yellow]Wizard cancelled.[/]")
        return {
            "ok": False,
            "mode": "wizard",
            "flow": "cancelled",
            "error": "cancelled",
        }


_CONFIGURE_BASIC_SECTIONS = [
    ("1", "provider",   "Provider / Model / API Key"),
    ("2", "gateway",    "Gateway (host, port, auth token)"),
    ("3", "channels",   "Primary channel (Telegram)"),
    ("4", "workspace",  "Workspace"),
    ("5", "back",       "Back"),
]

_CONFIGURE_ADVANCED_SECTIONS = [
    ("1", "memory",         "Memory"),
    ("2", "context_budget", "Context budget"),
    ("3", "jobs",           "Jobs"),
    ("4", "bus",            "Event bus"),
    ("5", "channels_extra", "Extra channels (Discord, Slack, WhatsApp)"),
    ("6", "tool_safety",    "Tool safety"),
    ("7", "autonomy",       "Autonomy"),
    ("8", "back",           "Back"),
]


def _show_configure_menu(console: Console, items: list[tuple[str, str, str]], title: str) -> str:
    console.print(f"\n  [bold]{title}[/]\n")
    for num, _, label in items:
        console.print(f"    [{num}] {label}")
    console.print()
    choices = [num for num, _, _ in items]
    return Prompt.ask("  Select", choices=choices)


def _dispatch_section(
    console: Console,
    config: AppConfig,
    key: str,
    visited: set[str],
    *,
    overwrite: bool,
    variables: dict[str, Any],
) -> None:
    """Call the right section helper by key and track visited."""
    if key == "provider":
        prov, api_key, base_url, sel_model, _, oauth = _configure_model(console, config, allow_continue_on_probe_failure=True)
        apply_provider_selection(
            config, provider=prov, api_key=api_key, base_url=base_url, model=sel_model,
            oauth_access_token=str(oauth.get("access_token", "")),
            oauth_account_id=str(oauth.get("account_id", "")),
            oauth_source=str(oauth.get("source", "")),
        )
    elif key == "gateway":
        _configure_gateway_quickstart(console, config)
    elif key == "channels":
        _configure_channels(console, config, allow_continue_on_probe_failure=True)
    elif key == "workspace":
        _configure_workspace(console, config, overwrite=overwrite, variables=variables)
    elif key == "memory":
        _configure_memory(console, config)
    elif key == "context_budget":
        _configure_context_budget(console, config)
    elif key == "jobs":
        _configure_jobs(console, config)
    elif key == "bus":
        _configure_bus(console, config)
    elif key == "channels_extra":
        console.print("  [dim]Extra channels (Discord, Slack, WhatsApp) — configure via config file.[/]\n")
    elif key == "tool_safety":
        _configure_tool_safety(console, config)
    elif key == "autonomy":
        _configure_autonomy(console, config)
    visited.add(key)


def _run_configure_flow(
    console: Console,
    config: AppConfig,
    *,
    config_path: str | Path | None = None,
    section: str | None = None,
) -> dict[str, Any]:
    """Two-level configure wizard: Basic / Advanced."""
    import sys

    _print_banner(console)
    effective_path = str(config_path) if config_path else str(DEFAULT_CONFIG_PATH)
    visited: set[str] = set()

    # Existing config detection (interactive sessions only)
    if Path(effective_path).exists() and sys.stdin.isatty():
        proceed = Confirm.ask(
            f"  Existing config found at {effective_path}. Modify it?",
            default=True,
        )
        if not proceed:
            console.print("  [yellow]Configure cancelled. No changes made.[/]")
            return {"ok": False, "visited_sections": [], "saved_path": effective_path}

    # Section shortcut
    if section:
        _dispatch_section(console, config, section, visited, overwrite=False, variables={})
        save_config(config, path=effective_path)
        return {"ok": True, "visited_sections": sorted(visited), "saved_path": effective_path}

    _MAIN_MENU = [
        ("1", "basic",    "Basic Setup"),
        ("2", "advanced", "Advanced Settings"),
        ("3", "exit",     "Save & Exit"),
    ]

    while True:
        choice_num = _show_configure_menu(console, _MAIN_MENU, "Configure ClawLite")
        choice = _MAIN_MENU[int(choice_num) - 1][1]

        if choice == "exit":
            break

        if choice == "basic":
            while True:
                sub = _show_configure_menu(console, _CONFIGURE_BASIC_SECTIONS, "Basic Setup")
                _, key, _ = _CONFIGURE_BASIC_SECTIONS[int(sub) - 1]
                if key == "back":
                    break
                _dispatch_section(console, config, key, visited, overwrite=False, variables={})
                save_config(config, path=effective_path)

        elif choice == "advanced":
            while True:
                sub = _show_configure_menu(console, _CONFIGURE_ADVANCED_SECTIONS, "Advanced Settings")
                _, key, _ = _CONFIGURE_ADVANCED_SECTIONS[int(sub) - 1]
                if key == "back":
                    break
                _dispatch_section(console, config, key, visited, overwrite=False, variables={})
                save_config(config, path=effective_path)

    save_config(config, path=effective_path)
    console.print(
        Panel(
            f"  [bold green]Configuration saved![/]\n\n"
            f"  [bold]Config path:[/]    {effective_path}\n"
            f"  [bold]Sections visited:[/] {', '.join(sorted(visited)) or 'none'}\n\n"
            f"  [dim]Start the agent:[/]  [bold cyan]clawlite start[/]",
            title="[green]Done[/]",
            border_style="green",
            padding=(1, 2),
        )
    )
    return {"ok": True, "visited_sections": sorted(visited), "saved_path": effective_path}
