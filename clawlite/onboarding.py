from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from clawlite.config.settings import load_config, save_config
from clawlite.core.model_catalog import get_model_or_default
from clawlite.core.providers import get_provider_spec, normalize_provider, provider_env_vars
from clawlite.runtime.daemon import DaemonError, install_systemd_user_service
from clawlite.runtime.doctor import run_doctor
from clawlite.runtime.session_memory import ensure_memory_layout
from clawlite.runtime.workspace import init_workspace
from clawlite.configure_menu import (
    _ensure_defaults,
    _section_channels,
    _section_gateway,
    _section_hooks,
    _section_language,
    _section_model,
    _section_security,
    _section_skills,
    _section_web_tools,
)

console = Console()


SKILL_PRESETS = {
    "dev": ["coding-agent", "github", "docker", "ssh", "web-search", "web-fetch", "skill-creator"],
    "creator": ["threads", "twitter", "youtube", "rss", "image-gen", "web-search", "web-fetch"],
    "ops": ["healthcheck", "cron", "tailscale", "ssh", "docker", "weather", "memory-search"],
}

CORE_MEMORY_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "IDENTITY.md", "MEMORY.md"]
_ONBOARDING_META_KEY = "__onboarding_meta"


def _mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 10:
        return "*" * len(token)
    return f"{token[:6]}...{token[-3:]}"


def _ensure_gateway_token_if_required(cfg: dict[str, Any]) -> bool:
    security = cfg.get("security", {}) if isinstance(cfg.get("security"), dict) else {}
    require_token = bool(security.get("require_gateway_token", True))
    if not require_token:
        return False

    gateway = cfg.setdefault("gateway", {})
    token = str(gateway.get("token", "")).strip()
    if token:
        return False

    gateway["token"] = secrets.token_urlsafe(24)
    return True


def _clone_config(cfg: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(cfg, ensure_ascii=False))


def _meta(cfg: dict[str, Any]) -> dict[str, Any]:
    existing = cfg.get(_ONBOARDING_META_KEY)
    if isinstance(existing, dict):
        return existing
    meta: dict[str, Any] = {}
    cfg[_ONBOARDING_META_KEY] = meta
    return meta


def _public_config(cfg: dict[str, Any]) -> dict[str, Any]:
    out = _clone_config(cfg)
    out.pop(_ONBOARDING_META_KEY, None)
    return out


def _record_extra_check(cfg: dict[str, Any], name: str, ok: bool, detail: str) -> None:
    bucket = _meta(cfg).setdefault("extra_checks", [])
    if not isinstance(bucket, list):
        bucket = []
        _meta(cfg)["extra_checks"] = bucket
    bucket.append({"name": name, "ok": "true" if ok else "false", "detail": detail})


def _collect_extra_checks(cfg: dict[str, Any]) -> list[dict[str, str]]:
    meta = cfg.get(_ONBOARDING_META_KEY, {})
    if not isinstance(meta, dict):
        return []
    raw = meta.get("extra_checks", [])
    if not isinstance(raw, list):
        return []
    checks: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        checks.append(
            {
                "name": str(item.get("name", "Wizard Check")),
                "ok": "true" if str(item.get("ok", "false")).lower() == "true" else "false",
                "detail": str(item.get("detail", "")),
            }
        )
    return checks


def _mask_secret_value(value: Any) -> Any:
    if isinstance(value, str):
        return _mask_token(value)
    if isinstance(value, list):
        return [_mask_secret_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _mask_secret_value(v) for k, v in value.items()}
    if value in (None, False, 0):
        return value
    return "***"


def _redacted_config_for_preview(cfg: dict[str, Any]) -> dict[str, Any]:
    sensitive_keys = ("token", "secret", "password", "api_key", "apikey")

    def _walk(value: Any, parent_key: str = "") -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, child in value.items():
                key_l = key.lower()
                if any(flag in key_l for flag in sensitive_keys):
                    out[key] = _mask_secret_value(child)
                else:
                    out[key] = _walk(child, key)
            return out
        if isinstance(value, list):
            return [_walk(item, parent_key) for item in value]
        return value

    return _walk(_public_config(cfg))


def _build_readiness_checks(
    cfg: dict[str, Any],
    channel_tests: list[str],
    extra_checks: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    model_key = str(cfg.get("model", "")).strip()
    if model_key:
        entry = get_model_or_default(model_key)
        checks.append(
            {
                "name": "Model Catalog",
                "ok": "true",
                "detail": f"{entry.provider}/{entry.id} · context {entry.context_window}",
            }
        )
    else:
        checks.append({"name": "Model Catalog", "ok": "false", "detail": "No model selected"})

    provider = _provider_from_model(model_key) if model_key else ""
    if provider and provider not in {"ollama", "local"}:
        spec = get_provider_spec(provider)
        token = _get_stored_token(cfg, provider)
        token_optional = bool(spec.token_optional) if spec else False
        if token:
            checks.append(
                {
                    "name": "Provider Auth",
                    "ok": "true",
                    "detail": f"{provider} key present ({_mask_token(token)})",
                }
            )
        elif token_optional:
            checks.append(
                {
                    "name": "Provider Auth",
                    "ok": "true",
                    "detail": f"{provider} token opcional (nao configurado)",
                }
            )
        else:
            checks.append(
                {
                    "name": "Provider Auth",
                    "ok": "false",
                    "detail": f"Missing API key for provider '{provider}'",
                }
            )
    else:
        checks.append(
            {
                "name": "Provider Auth",
                "ok": "true",
                "detail": "Local/ollama provider does not require API key",
            }
        )

    gateway = cfg.get("gateway", {}) if isinstance(cfg.get("gateway"), dict) else {}
    security = cfg.get("security", {}) if isinstance(cfg.get("security"), dict) else {}
    gw_host = str(gateway.get("host", "0.0.0.0"))
    gw_port = str(gateway.get("port", 8787))
    gw_token = str(gateway.get("token", "")).strip()
    require_token = bool(security.get("require_gateway_token", True))
    gateway_ok = bool(gw_token or not require_token)
    checks.append(
        {
            "name": "Gateway Security",
            "ok": "true" if gateway_ok else "false",
            "detail": (
                f"{gw_host}:{gw_port} · token {'set' if gw_token else 'missing'}"
                if require_token
                else f"{gw_host}:{gw_port} · token optional"
            ),
        }
    )

    channels = cfg.get("channels", {}) if isinstance(cfg.get("channels"), dict) else {}
    enabled_channels = [name for name, data in channels.items() if isinstance(data, dict) and data.get("enabled")]
    channels_ok = bool(enabled_channels)
    checks.append(
        {
            "name": "Channels",
            "ok": "true" if channels_ok else "false",
            "detail": ", ".join(enabled_channels) if enabled_channels else "No enabled channels",
        }
    )

    enabled_skills = cfg.get("skills", [])
    skill_count = len(enabled_skills) if isinstance(enabled_skills, list) else 0
    checks.append(
        {
            "name": "Skills Profile",
            "ok": "true" if skill_count >= 3 else "false",
            "detail": f"{skill_count} active skills",
        }
    )

    workspace = Path(init_workspace())
    missing_files = [name for name in CORE_MEMORY_FILES if not (workspace / name).exists()]
    checks.append(
        {
            "name": "Workspace Memory",
            "ok": "true" if not missing_files else "false",
            "detail": "All core memory files ready" if not missing_files else f"Missing: {', '.join(missing_files)}",
        }
    )

    security_ok = bool(security.get("redact_tokens_in_logs", True))
    checks.append(
        {
            "name": "Security Defaults",
            "ok": "true" if security_ok else "false",
            "detail": "Token redaction enabled" if security_ok else "Token redaction disabled",
        }
    )

    doctor_out = run_doctor()
    doctor_has_warnings = "warnings: none" not in doctor_out.lower()
    checks.append(
        {
            "name": "Doctor Healthcheck",
            "ok": "false" if doctor_has_warnings else "true",
            "detail": "Warnings found in doctor output" if doctor_has_warnings else "No doctor warnings",
        }
    )

    if channel_tests:
        lowered = [str(line).lower() for line in channel_tests]
        channel_ok = not any(
            ("falha" in line) or ("inválido" in line) or ("invalido" in line) or ("ausente" in line)
            for line in lowered
        )
        checks.append(
            {
                "name": "Live Channel Tests",
                "ok": "true" if channel_ok else "false",
                "detail": "; ".join(channel_tests[:3]),
            }
        )

    if extra_checks:
        checks.extend(extra_checks)

    return checks


def _readiness_score(checks: list[dict[str, str]]) -> int:
    if not checks:
        return 0
    passed = sum(1 for c in checks if c.get("ok") == "true")
    return int(round((passed / len(checks)) * 100))


def _write_onboarding_report(
    cfg: dict[str, Any],
    checks: list[dict[str, str]],
    channel_tests: list[str],
) -> Path:
    root = Path(init_workspace())
    report = root / "ONBOARDING_REPORT.md"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    score = _readiness_score(checks)

    lines = [
        "# ONBOARDING REPORT",
        "",
        f"- Generated at: {ts}",
        f"- Readiness score: {score}/100",
        f"- Model: {cfg.get('model', 'n/a')}",
        f"- Language: {cfg.get('language', 'pt-br')}",
        "",
        "## Readiness Checks",
    ]

    for check in checks:
        icon = "PASS" if check.get("ok") == "true" else "WARN"
        lines.append(f"- [{icon}] {check.get('name', 'Unnamed')}: {check.get('detail', '')}")

    lines.append("")
    lines.append("## Live Channel Tests")
    if channel_tests:
        lines.extend([f"- {line}" for line in channel_tests])
    else:
        lines.append("- No channel tests executed")

    lines.append("")
    lines.append("## Next Steps")
    lines.append("- Run `clawlite doctor`")
    lines.append("- Run `clawlite start`")
    lines.append("- Open the gateway dashboard and test `/ws/chat` flow")

    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def _show_readiness_panel(checks: list[dict[str, str]], report: Path, token_generated: bool) -> None:
    score = _readiness_score(checks)
    color = "green" if score >= 80 else "yellow" if score >= 60 else "red"
    lines = [f"[bold {color}]Readiness score: {score}/100[/bold {color}]"]
    if token_generated:
        lines.append("[bold cyan]Gateway token auto-generated for secure default setup.[/bold cyan]")
    lines.append("")

    for check in checks:
        ok = check.get("ok") == "true"
        prefix = "✅" if ok else "⚠️"
        lines.append(f"{prefix} {check.get('name', 'Check')}: {check.get('detail', '')}")

    lines.append("")
    lines.append(f"[dim]Report saved at: {report}[/dim]")
    console.print(Panel("\n".join(lines), title="ClawLite Readiness", border_style=color, padding=(1, 2)))


def _section_workspace(cfg: dict[str, Any]) -> None:
    console.print("\n[bold #00f5ff]Workspace[/bold #00f5ff]")
    root = Path(init_workspace())
    console.print(f"  [bold green]✓[/] Workspace pronto em [bold]{root}[/bold]")
    _record_extra_check(cfg, "Workspace Setup", True, f"Initialized at {root}")


def _section_daemon(cfg: dict[str, Any]) -> None:
    console.print("\n[bold #00f5ff]Daemon[/bold #00f5ff]")
    if os.name == "nt":
        console.print("  [bold yellow]⚠[/] install-daemon não é suportado no Windows sem WSL/systemd.")
        _record_extra_check(cfg, "Daemon", False, "Unsupported on this platform without WSL/systemd")
        return

    install_later = questionary.confirm(
        "Instalar daemon systemd user no passo Apply?",
        default=False,
    ).ask()
    if not install_later:
        _record_extra_check(cfg, "Daemon", True, "Skipped by user")
        return

    gateway = cfg.get("gateway", {}) if isinstance(cfg.get("gateway"), dict) else {}
    host = str(gateway.get("host", "127.0.0.1") or "127.0.0.1").strip()
    port_raw = gateway.get("port", 8787)
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        port = 8787

    service_name = (
        questionary.text(
            "Nome do serviço systemd user:",
            default="clawlite",
            validate=lambda t: bool(str(t).strip()) or "Informe um nome válido",
        ).ask()
        or "clawlite"
    ).strip()
    enable_now = bool(questionary.confirm("Habilitar para iniciar com usuário?", default=True).ask())
    start_now = bool(questionary.confirm("Iniciar/reiniciar agora após instalar?", default=True).ask())

    meta = _meta(cfg)
    meta["daemon_plan"] = {
        "install": True,
        "host": host,
        "port": port,
        "service_name": service_name,
        "enable_now": enable_now,
        "start_now": start_now,
    }
    console.print("  [dim]Daemon será aplicado no final (Review + Apply).[/dim]")


def _apply_daemon_setup(cfg: dict[str, Any]) -> None:
    meta = cfg.get(_ONBOARDING_META_KEY, {})
    if not isinstance(meta, dict):
        return
    plan = meta.get("daemon_plan", {})
    if not isinstance(plan, dict) or not plan.get("install"):
        return

    try:
        result = install_systemd_user_service(
            host=str(plan.get("host", "127.0.0.1")),
            port=int(plan.get("port", 8787)),
            service_name=str(plan.get("service_name", "clawlite")),
            enable_now=bool(plan.get("enable_now", True)),
            start_now=bool(plan.get("start_now", True)),
        )
        detail = (
            f"systemd user service '{result.get('service_name', 'clawlite')}' "
            f"configured at {result.get('unit_path', '')}"
        )
        _record_extra_check(cfg, "Daemon", True, detail)
        console.print(f"  [bold green]✓[/] {detail}")
    except DaemonError as exc:
        _record_extra_check(cfg, "Daemon", False, str(exc))
        console.print(f"  [bold yellow]⚠[/] Falha ao instalar daemon: {exc}")
    except Exception as exc:  # pragma: no cover - proteção extra
        _record_extra_check(cfg, "Daemon", False, str(exc))
        console.print(f"  [bold yellow]⚠[/] Falha inesperada no daemon: {exc}")


def _gateway_port_preflight(host: str, port: int) -> tuple[bool, str]:
    bind_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, port))
        return True, f"{bind_host}:{port} disponível"
    except OSError as exc:
        return False, f"{bind_host}:{port} indisponível ({exc})"


def _section_healthcheck(cfg: dict[str, Any]) -> None:
    console.print("\n[bold #00f5ff]Health check (preflight)[/bold #00f5ff]")
    gateway = cfg.get("gateway", {}) if isinstance(cfg.get("gateway"), dict) else {}
    security = cfg.get("security", {}) if isinstance(cfg.get("security"), dict) else {}

    host = str(gateway.get("host", "127.0.0.1") or "127.0.0.1").strip()
    try:
        port = int(gateway.get("port", 8787))
    except (TypeError, ValueError):
        port = 8787

    require_token = bool(security.get("require_gateway_token", True))
    has_token = bool(str(gateway.get("token", "")).strip())

    with console.status("Rodando doctor...", spinner="dots"):
        doctor_out = run_doctor()
    doctor_ok = "warnings: none" in doctor_out.lower()
    port_ok, port_detail = _gateway_port_preflight(host, port)
    token_ok = (not require_token) or has_token

    console.print(f"- Doctor: {'ok' if doctor_ok else 'warnings detectados'}")
    console.print(f"- Porta gateway: {port_detail}")
    console.print(f"- Token gateway: {'ok' if token_ok else 'ausente'}")

    overall_ok = doctor_ok and port_ok and token_ok
    detail = (
        f"doctor={'ok' if doctor_ok else 'warn'}; "
        f"port={'ok' if port_ok else 'fail'}; "
        f"token={'ok' if token_ok else 'missing'}"
    )
    _record_extra_check(cfg, "Gateway Preflight", overall_ok, detail)


def _finalize_onboarding(cfg: dict[str, Any], *, token_generated: bool | None = None) -> None:
    generated = _ensure_gateway_token_if_required(cfg) if token_generated is None else token_generated
    _apply_daemon_setup(cfg)
    _save_identity_files(cfg)

    public_cfg = _public_config(cfg)
    channel_tests = _live_channel_tests(public_cfg)
    checks = _build_readiness_checks(
        public_cfg,
        channel_tests,
        extra_checks=_collect_extra_checks(cfg),
    )
    report_path = _write_onboarding_report(public_cfg, checks, channel_tests)
    save_config(public_cfg)
    _show_readiness_panel(checks, report_path, generated)
    _show_completion_panel(public_cfg)


def _simple_prompt(prompt: str, default: str = "") -> str:
    try:
        value = input(prompt)
    except (EOFError, KeyboardInterrupt, OSError):
        # Em testes/captura (pytest) input() pode levantar OSError quando stdin não é interativo.
        return default
    text = value.strip()
    return text if text else default


def _fox_banner() -> str:
    return (
        "[bold #ff6b2b]      /\\_/\\[/bold #ff6b2b]\n"
        "[bold #ff6b2b]  =^.^=[/bold #ff6b2b] [bold #00f5ff]ClawLite Onboarding[/bold #00f5ff]\n"
        "[bold #ff6b2b]     > ^ <[/bold #ff6b2b]"
    )


def _is_valid_telegram_token_format(token: str) -> bool:
    token = token.strip()
    if not token or ":" not in token:
        return False
    left, right = token.split(":", 1)
    return left.isdigit() and len(left) >= 7 and len(right) >= 20


def _test_telegram(token: str) -> tuple[bool, str]:
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("ok"):
            username = data.get("result", {}).get("username", "bot")
            return True, f"Telegram conectado (@{username})"
        return False, "Token Telegram inválido"
    except Exception as exc:
        return False, f"Falha Telegram: {exc}"


def _live_channel_tests(cfg: dict) -> list[str]:
    out: list[str] = []
    channels = cfg.get("channels", {}) if isinstance(cfg.get("channels"), dict) else {}
    tg = channels.get("telegram", {}) if isinstance(channels.get("telegram"), dict) else {}
    if tg.get("enabled"):
        token = str(tg.get("token", "")).strip()
        if token:
            ok, msg = _test_telegram(token)
            out.append(("✅ " if ok else "⚠️ ") + msg)
        else:
            out.append("⚠️ Telegram habilitado sem token")

    for ch in ("slack", "discord", "whatsapp", "teams"):
        data = channels.get(ch, {}) if isinstance(channels.get(ch), dict) else {}
        if data.get("enabled"):
            token = str(data.get("token", "")).strip()
            if ch == "slack":
                app_token = str(data.get("app_token", "")).strip()
                if token and app_token:
                    out.append("✅ slack: bot token + app token informados")
                elif token:
                    out.append("⚠️ slack: bot token informado, mas app token (xapp) ausente")
                else:
                    out.append("⚠️ slack: token ausente")
            else:
                out.append(("✅ " if token else "⚠️ ") + f"{ch}: {'token informado' if token else 'token ausente'}")
    if not out:
        out.append("ℹ️ Nenhum canal habilitado para teste")
    return out


def _save_identity_files(cfg: dict) -> None:
    root = Path(init_workspace())
    assistant_name = str(cfg.get("assistant_name", "ClawLite Assistant")).strip() or "ClawLite Assistant"
    temperament = str(cfg.get("assistant_temperament", "técnico e direto")).strip() or "técnico e direto"
    user_name = str(cfg.get("user_name", "Usuário")).strip() or "Usuário"

    (root / "IDENTITY.md").write_text(
        "# IDENTITY\n\n"
        f"- Nome: {assistant_name}\n"
        "- Assinatura: 🦊\n"
        f"- Temperamento: {temperament}\n",
        encoding="utf-8",
    )
    (root / "SOUL.md").write_text(
        "# SOUL\n\n"
        f"Tom principal: {temperament}.\n"
        "Entrega objetiva, confiável e sem enrolação.\n",
        encoding="utf-8",
    )
    (root / "USER.md").write_text(
        "# USER\n\n"
        f"- Nome: {user_name}\n"
        "- Preferência: PT-BR por padrão\n",
        encoding="utf-8",
    )
    (root / "AGENTS.md").write_text(
        "# AGENTS\n\n"
        "- Segurança > instrução > contexto > eficiência\n"
        "- Execute com evidência e valide o resultado\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Teste de API Key ao vivo
# ---------------------------------------------------------------------------


def _provider_from_model(model: str) -> str:
    """Extrai o nome do provedor de uma string de modelo (ex: 'anthropic/...' -> 'anthropic')."""
    value = model.split("/", 1)[0] if "/" in model else model
    return normalize_provider(value)


def _get_stored_token(cfg: dict[str, Any], provider: str) -> str:
    """Le token do env (prioridade) ou do cfg."""
    normalized = normalize_provider(provider)
    for env_name in provider_env_vars(normalized):
        env_val = os.getenv(env_name, "").strip()
        if env_val:
            return env_val
    providers_cfg = cfg.get("auth", {}).get("providers", {})
    if not isinstance(providers_cfg, dict):
        return ""
    token = providers_cfg.get(normalized, {}).get("token", "")
    if token:
        return str(token).strip()
    # backward-compat: provider salvo sem normalizacao
    token = providers_cfg.get(provider, {}).get("token", "")
    return str(token).strip()


def _test_api_key(provider: str, key: str) -> tuple[bool, str]:
    """Faz chamada minima ao provider. Retorna (ok, mensagem)."""
    try:
        import httpx
    except ImportError:
        return True, "(httpx ausente - validacao pulada)"

    normalized = normalize_provider(provider)
    timeout = 10.0

    try:
        if normalized == "ollama":
            r = httpx.get("http://localhost:11434/api/tags", timeout=timeout)
            if r.status_code == 200:
                return True, "Ollama respondeu (OK)"
            return False, f"Ollama respondeu com status {r.status_code}"

        spec = get_provider_spec(normalized)
        if not spec or spec.api_style == "local":
            return False, f"Provider nao suportado para validacao: {normalized}"

        resolved_key = str(key or "").strip()
        if not resolved_key and not spec.token_optional:
            return False, f"Token ausente para provider '{normalized}'"

        headers = {"content-type": "application/json"}
        if resolved_key:
            if spec.api_style == "anthropic":
                headers["x-api-key"] = resolved_key
            else:
                headers["Authorization"] = f"Bearer {resolved_key}"

        if spec.api_style == "anthropic":
            headers["anthropic-version"] = "2023-06-01"
            payload = {
                "model": spec.default_model or "claude-haiku-4-5-20251001",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            }
        else:
            payload = {
                "model": spec.default_model or "gpt-4o-mini",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            }

        r = httpx.post(spec.request_url, headers=headers, json=payload, timeout=timeout)
        if r.status_code in (200, 201):
            return True, "Key valida ✓"
        if r.status_code == 401:
            return False, "Erro 401: key invalida ou sem permissao"
        if r.status_code == 429:
            return True, "Erro 429: rate limit - key valida mas sem quota agora"
        return False, f"Erro {r.status_code}: {r.text[:120]}"

    except Exception as exc:
        msg = str(exc)
        if "connect" in msg.lower() or "timeout" in msg.lower() or "network" in msg.lower():
            return False, f"Erro de conexao - verifique internet ou endpoint ({msg[:80]})"
        return False, f"Erro inesperado: {msg[:120]}"


def _step_test_api_key(cfg: dict[str, Any]) -> None:
    """Step do wizard: testa a API key do provedor escolhido. Até 3 tentativas."""
    # Em ambiente não interativo (ex.: CI/pytest com captura), não abrir prompt questionary.
    if not sys.stdin.isatty():
        return

    model = cfg.get("model", "")
    if not model:
        return

    provider = _provider_from_model(model)

    # Ollama não precisa de key
    if provider == "ollama":
        ok, msg = _test_api_key("ollama", "")
        if ok:
            console.print(f"  [bold green]✓[/] {msg}")
        else:
            console.print(f"  [bold yellow]⚠[/] {msg}")
        return

    spec = get_provider_spec(provider)
    if not spec or spec.api_style == "local":
        return

    key = _get_stored_token(cfg, provider)
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        if not key:
            console.print(f"\n[bold #00f5ff]API Key — {provider}[/bold #00f5ff]")
            key_input = questionary.password(
                f"Informe a API key para {provider} (tentativa {attempt}/{max_attempts}):"
            ).ask()
            if not key_input:
                console.print("  [dim]Pulando validação de key.[/dim]")
                return
            key = key_input.strip()

        with console.status(f"Testando key {provider}...", spinner="dots"):
            ok, msg = _test_api_key(provider, key)

        if ok:
            console.print(f"  [bold green]✓[/] {msg}")
            # Persiste a key válida no cfg
            cfg.setdefault("auth", {}).setdefault("providers", {}).setdefault(provider, {})["token"] = key
            return
        else:
            console.print(f"  [bold red]✗[/] {msg}")
            if attempt < max_attempts:
                retry = questionary.confirm(
                    f"Tentar novamente? ({attempt}/{max_attempts})", default=True
                ).ask()
                if not retry:
                    break
                key = ""  # força nova entrada na próxima volta
            else:
                skip = questionary.confirm(
                    "Máximo de tentativas atingido. Pular validação e continuar?", default=True
                ).ask()
                if not skip:
                    raise KeyboardInterrupt("Onboarding cancelado pelo usuário na validação de key.")


# ---------------------------------------------------------------------------
# Painel Rich de conclusão
# ---------------------------------------------------------------------------

def _show_completion_panel(cfg: dict[str, Any]) -> None:
    """Exibe painel final com gateway URL, token e canais configurados."""
    gw = cfg.get("gateway", {})
    host_raw = str(gw.get("host", "0.0.0.0")).strip()
    display_host = "127.0.0.1" if host_raw in ("0.0.0.0", "::") else host_raw
    port = int(gw.get("port", 8787))
    gateway_url = f"http://{display_host}:{port}"

    token = str(gw.get("token", "")).strip()
    token_display = token if token else "(gerado automaticamente no clawlite start)"

    lines = [
        f"[bold cyan]Gateway:[/] {gateway_url}",
        f"[bold cyan]Token:[/]   {token_display}",
    ]

    # Telegram
    tg = cfg.get("channels", {}).get("telegram", {})
    if tg.get("enabled") and tg.get("token"):
        try:
            tg_ok, tg_msg = _test_telegram(str(tg["token"]))
            username = tg_msg.split("@")[-1].rstrip(")") if "@" in tg_msg else "bot"
            lines.append(f"[bold cyan]Telegram:[/] @{username}" if tg_ok else f"[bold yellow]Telegram:[/] {tg_msg}")
        except Exception:
            lines.append("[bold cyan]Telegram:[/] configurado")
    elif tg.get("enabled"):
        lines.append("[bold yellow]Telegram:[/] ativo · token ausente")

    lines.append("")
    lines.append("[dim]Próximo: clawlite start[/]")

    console.print(
        Panel(
            "\n".join(lines),
            title="🦊 ClawLite está pronto!",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def _quickstart_telegram(cfg: dict[str, Any]) -> None:
    console.print("\n[bold #00f5ff]Telegram (QuickStart)[/bold #00f5ff]")
    enable = questionary.confirm("Conectar Telegram agora? (recomendado)", default=True).ask()
    tg = cfg.setdefault("channels", {}).setdefault("telegram", {})
    tg["enabled"] = bool(enable)
    if not enable:
        return

    console.print("1) Abra o Telegram e pesquise @BotFather")
    console.print("2) Envie /newbot e finalize a criação")

    attempts = 3
    token = str(tg.get("token", "")).strip()
    for i in range(1, attempts + 1):
        token = (
            questionary.text(
                f"Cole o token do bot (tentativa {i}/{attempts}):",
                default=token,
                validate=lambda t: _is_valid_telegram_token_format(str(t)) or "Formato inválido de token Telegram",
            ).ask()
            or ""
        ).strip()
        if not token:
            continue

        with console.status("Testando conexão Telegram...", spinner="dots"):
            ok, msg = _test_telegram(token)
        if ok:
            tg["token"] = token
            console.print(f"  [bold green]✓[/] {msg}")
            console.print("  [dim]Próximo passo: abra seu bot e envie /start[/dim]")
            return

        console.print(f"  [bold red]✗[/] {msg}")
        if i < attempts and not questionary.confirm("Tentar novamente?", default=True).ask():
            break

    console.print("  [bold yellow]⚠[/] Telegram ficou habilitado sem validação concluída.")
    tg["token"] = token


def _run_onboarding_quickstart(cfg: dict[str, Any]) -> None:
    console.print(
        "[bold #00f5ff]QuickStart[/bold #00f5ff] — fluxo recomendado: Model/Auth, Workspace, Gateway, Channels, Daemon e Health check."
    )
    _section_language(cfg)
    _section_identity(cfg)
    _section_model(cfg)
    _step_test_api_key(cfg)
    _section_workspace(cfg)

    cfg.setdefault("gateway", {})
    cfg["gateway"]["host"] = "127.0.0.1"
    cfg["gateway"].setdefault("port", 8787)
    cfg.setdefault("security", {})
    cfg["security"].setdefault("require_gateway_token", True)
    cfg["security"].setdefault("redact_tokens_in_logs", True)

    console.print("  [dim]Gateway local padrão: 127.0.0.1:8787[/dim]")
    _quickstart_telegram(cfg)
    _skills_quickstart_profile(cfg)
    _section_daemon(cfg)
    token_generated = _ensure_gateway_token_if_required(cfg)
    _section_healthcheck(cfg)
    _finalize_onboarding(cfg, token_generated=token_generated)


def _section_identity(cfg: dict) -> None:
    assistant_name = questionary.text(
        "Nome do assistente:",
        default=str(cfg.get("assistant_name", "ClawLite Assistant")),
        validate=lambda t: bool(str(t).strip()) or "Informe um nome válido",
    ).ask()
    temperament = questionary.select(
        "Temperamento do assistente:",
        choices=["Técnico e direto", "Calmo e didático", "Rápido e pragmático"],
        default="Técnico e direto",
    ).ask()
    user_name = questionary.text(
        "Seu nome:",
        default=str(cfg.get("user_name", "")),
        validate=lambda t: bool(str(t).strip()) or "Informe seu nome",
    ).ask()

    cfg["assistant_name"] = (assistant_name or "ClawLite Assistant").strip()
    cfg["assistant_temperament"] = (temperament or "Técnico e direto").strip()
    cfg["user_name"] = (user_name or "Usuário").strip()


def _skills_quickstart_profile(cfg: dict) -> None:
    choice = questionary.select(
        "Perfil inicial de skills (você ajusta na próxima etapa):",
        choices=[
            "Dev (automação + código)",
            "Creator (conteúdo + social)",
            "Ops (infra + monitoramento)",
            "Personalizado (começar do zero)",
        ],
        default="Dev (automação + código)",
    ).ask()

    if not choice or choice.startswith("Personalizado"):
        return

    if choice.startswith("Dev"):
        cfg["skills"] = SKILL_PRESETS["dev"]
    elif choice.startswith("Creator"):
        cfg["skills"] = SKILL_PRESETS["creator"]
    elif choice.startswith("Ops"):
        cfg["skills"] = SKILL_PRESETS["ops"]


def _run_onboarding_simple(cfg: dict) -> None:
    console.print("🛠️ Modo simples ativado (compatibilidade de terminal).")
    lang = _simple_prompt("Idioma [pt-br/en] (padrão pt-br): ", "pt-br").lower()
    cfg["language"] = "en" if lang.startswith("en") else "pt-br"

    cfg["assistant_name"] = _simple_prompt("Nome do assistente (ClawLite Assistant): ", "ClawLite Assistant")
    cfg["assistant_temperament"] = _simple_prompt("Temperamento (técnico e direto): ", "técnico e direto")
    cfg["user_name"] = _simple_prompt("Seu nome: ", "Usuário")

    model = _simple_prompt(f"Modelo [{cfg.get('model','openai/gpt-4o-mini')}]: ", "")
    if model:
        cfg["model"] = model

    tg_value = _simple_prompt("Ativar Telegram? [s/N]: ", "n").lower()
    tg = tg_value.startswith(("s", "y"))
    cfg.setdefault("channels", {}).setdefault("telegram", {})["enabled"] = tg
    if tg:
        tok = _simple_prompt("Token Telegram (opcional agora): ", "")
        if tok:
            cfg["channels"]["telegram"]["token"] = tok

    profile = _simple_prompt("Perfil de skills [dev/creator/ops/custom] (dev): ", "dev").lower()
    if profile in SKILL_PRESETS:
        cfg["skills"] = SKILL_PRESETS[profile]

    _section_workspace(cfg)
    token_generated = _ensure_gateway_token_if_required(cfg)
    _finalize_onboarding(cfg, token_generated=token_generated)
    console.print("✅ Onboarding simples concluído.")


def run_onboarding() -> None:
    ensure_memory_layout()
    cfg = load_config()
    _ensure_defaults(cfg)

    simple_ui = os.getenv("CLAWLITE_SIMPLE_UI") == "1" or os.getenv("TERM", "").lower() in {"", "dumb", "unknown"}
    if simple_ui or not sys.stdin.isatty():
        _run_onboarding_simple(cfg)
        return

    draft = _clone_config(cfg)

    mode = questionary.select(
        "Como você quer configurar?",
        choices=[
            "QuickStart — padrões recomendados (2 min)",
            "Avançado — fluxo completo (Model/Auth, Workspace, Gateway, Canais, Daemon, Health check, Skills)",
        ],
        default="QuickStart — padrões recomendados (2 min)",
    ).ask()

    if mode and mode.startswith("QuickStart"):
        _run_onboarding_quickstart(draft)
        return

    steps = [
        ("Idioma", _section_language),
        ("Identidade", _section_identity),
        ("Model/Auth", _section_model),
        ("Teste de API Key", _step_test_api_key),
        ("Workspace", _section_workspace),
        ("Gateway", _section_gateway),
        ("Canais", _section_channels),
        ("Daemon", _section_daemon),
        ("Health check", _section_healthcheck),
        ("Perfil de Skills", _skills_quickstart_profile),
        ("Skills", _section_skills),
        ("Hooks", _section_hooks),
        ("Web Tools", _section_web_tools),
        ("Security", _section_security),
    ]

    console.print(Panel.fit(_fox_banner(), border_style="#ff6b2b"))

    total_steps = len(steps)
    for idx, (name, fn) in enumerate(steps, start=1):
        console.print(Panel.fit(f"Etapa {idx}/{total_steps}: {name}", border_style="#00f5ff"))
        fn(draft)

    token_generated = _ensure_gateway_token_if_required(draft)
    public_preview = _public_config(draft)
    test_results = _live_channel_tests(public_preview)
    checks = _build_readiness_checks(
        public_preview,
        test_results,
        extra_checks=_collect_extra_checks(draft),
    )

    console.print(Panel("Review + Apply", border_style="#00f5ff"))
    console.print(Syntax(json.dumps(_redacted_config_for_preview(draft), ensure_ascii=False, indent=2), "json", line_numbers=False))
    console.print("\n[bold #00f5ff]Teste de conexões:[/bold #00f5ff]")
    for line in test_results:
        console.print(f"- {line}")
    console.print("\n[bold #00f5ff]Readiness parcial:[/bold #00f5ff]")
    console.print(f"- Score: {_readiness_score(checks)}/100")

    if questionary.confirm("Aplicar essas configurações agora?", default=True).ask():
        _finalize_onboarding(draft, token_generated=token_generated)
    else:
        console.print("🟡 Onboarding cancelado. Nenhuma alteração foi persistida.")
