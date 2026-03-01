from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import clawlite
from clawlite.config.settings import CONFIG_DIR, load_config

REPO_URL = "https://github.com/eobarretooo/ClawLite.git"
REMOTE_PYPROJECT_URL = "https://raw.githubusercontent.com/eobarretooo/ClawLite/refs/heads/main/pyproject.toml"
RELEASES_LATEST_URL = "https://api.github.com/repos/eobarretooo/ClawLite/releases/latest"
RELEASES_LIST_URL = "https://api.github.com/repos/eobarretooo/ClawLite/releases?per_page=30"
DEFAULT_CHECK_INTERVAL_SECONDS = 6 * 60 * 60
UPDATE_CACHE_PATH = CONFIG_DIR / "update-cache.json"
VALID_UPDATE_CHANNELS = {"stable", "beta", "dev"}
DEFAULT_UPDATE_CHANNEL = "stable"


@dataclass(frozen=True)
class UpdateStatus:
    current_version: str
    latest_version: str
    available: bool
    source: str
    channel: str = DEFAULT_UPDATE_CHANNEL
    target_ref: str = ""


@dataclass(frozen=True)
class UpdateTarget:
    version: str
    source: str
    ref: str


def _now_ts() -> int:
    return int(time.time())


def _check_interval_seconds() -> int:
    raw = os.getenv("CLAWLITE_UPDATE_CHECK_INTERVAL_SEC", "").strip()
    if not raw:
        return DEFAULT_CHECK_INTERVAL_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_CHECK_INTERVAL_SECONDS
    return value if value > 30 else DEFAULT_CHECK_INTERVAL_SECONDS


def _current_version() -> str:
    value = str(getattr(clawlite, "__version__", "")).strip()
    return value or "0.0.0"


def _normalize_update_channel(value: str | None) -> str:
    channel = str(value or "").strip().lower()
    if channel in VALID_UPDATE_CHANNELS:
        return channel
    return DEFAULT_UPDATE_CHANNEL


def _resolve_update_channel(explicit_channel: str | None = None) -> str:
    if explicit_channel:
        return _normalize_update_channel(explicit_channel)
    env_channel = os.getenv("CLAWLITE_UPDATE_CHANNEL", "").strip()
    if env_channel:
        return _normalize_update_channel(env_channel)
    try:
        cfg = load_config()
    except Exception:
        cfg = {}
    if isinstance(cfg, dict):
        update_cfg = cfg.get("update")
        if isinstance(update_cfg, dict):
            return _normalize_update_channel(str(update_cfg.get("channel", "")))
    return DEFAULT_UPDATE_CHANNEL


def _parse_version_components(value: str) -> tuple[tuple[int, object], ...]:
    if not value:
        return ((0, 0),)
    tokens = re.findall(r"\d+|[a-zA-Z]+", value.lower())
    parts: list[tuple[int, object]] = []
    for token in tokens:
        if token.isdigit():
            parts.append((0, int(token)))
        else:
            parts.append((1, token))
    return tuple(parts) if parts else ((0, 0),)


def _is_newer_version(latest: str, current: str) -> bool:
    return _parse_version_components(latest) > _parse_version_components(current)


def _extract_version_from_pyproject(pyproject_text: str) -> str:
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"\s*$', pyproject_text, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Nao foi possivel extrair version do pyproject remoto.")
    return match.group(1).strip()


def _extract_version_from_ref(ref_value: str) -> str:
    ref = str(ref_value or "").strip()
    if not ref:
        raise RuntimeError("Referencia de release/tag vazia.")
    ref = ref.removeprefix("refs/tags/")
    ref = ref.removeprefix("v")
    dot_beta = re.fullmatch(r"([0-9]+(?:\.[0-9]+){2})\.beta(?:\.([0-9A-Za-z.-]+))?", ref)
    if dot_beta:
        base = dot_beta.group(1)
        suffix = dot_beta.group(2)
        ref = f"{base}-beta.{suffix}" if suffix else f"{base}-beta"
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){2}(?:[-+][0-9A-Za-z.-]+)?", ref):
        raise RuntimeError(f"Tag de release invalida: {ref_value}")
    return ref


def _fetch_json(url: str, timeout: float = 2.5) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "clawlite-update-check/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def _fetch_remote_version(timeout: float = 2.5) -> str:
    req = urllib.request.Request(
        REMOTE_PYPROJECT_URL,
        headers={"User-Agent": "clawlite-update-check/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return _extract_version_from_pyproject(body)


def _release_entry_to_target(entry: dict, source: str) -> UpdateTarget:
    tag = str(entry.get("tag_name", "")).strip()
    version = _extract_version_from_ref(tag)
    return UpdateTarget(version=version, source=source, ref=tag)


def _fetch_latest_stable_release_target(timeout: float = 2.5) -> UpdateTarget:
    payload = _fetch_json(RELEASES_LATEST_URL, timeout=timeout)
    if not isinstance(payload, dict):
        raise RuntimeError("Resposta invalida de releases/latest.")
    if payload.get("draft") is True:
        raise RuntimeError("Release latest esta marcado como draft.")
    if payload.get("prerelease") is True:
        raise RuntimeError("Release latest esta marcado como prerelease.")
    return _release_entry_to_target(payload, "release-stable")


def _fetch_latest_beta_release_target(timeout: float = 2.5) -> UpdateTarget:
    payload = _fetch_json(RELEASES_LIST_URL, timeout=timeout)
    if not isinstance(payload, list):
        raise RuntimeError("Resposta invalida de releases.")
    for item in payload:
        if not isinstance(item, dict):
            continue
        if item.get("draft") is True:
            continue
        if item.get("prerelease") is True:
            return _release_entry_to_target(item, "release-beta")
    raise RuntimeError("Nenhuma release beta encontrada.")


def _fetch_main_target(timeout: float = 2.5) -> UpdateTarget:
    version = _fetch_remote_version(timeout=timeout)
    return UpdateTarget(version=version, source="main", ref="main")


def _fetch_remote_target(channel: str, timeout: float = 2.5) -> UpdateTarget:
    resolved_channel = _normalize_update_channel(channel)
    if resolved_channel == "dev":
        return _fetch_main_target(timeout=timeout)

    stable_target: UpdateTarget | None = None
    if resolved_channel == "stable":
        try:
            return _fetch_latest_stable_release_target(timeout=timeout)
        except Exception:
            return UpdateTarget(
                version=_fetch_main_target(timeout=timeout).version,
                source="main-fallback-stable",
                ref="main",
            )

    # beta
    beta_target: UpdateTarget | None = None
    try:
        beta_target = _fetch_latest_beta_release_target(timeout=timeout)
    except Exception:
        beta_target = None
    try:
        stable_target = _fetch_latest_stable_release_target(timeout=timeout)
    except Exception:
        stable_target = None

    if beta_target and stable_target:
        if _is_newer_version(stable_target.version, beta_target.version):
            return UpdateTarget(
                version=stable_target.version,
                source="release-stable-fallback-beta",
                ref=stable_target.ref,
            )
        return beta_target
    if beta_target:
        return beta_target
    if stable_target:
        return UpdateTarget(
            version=stable_target.version,
            source="release-stable-fallback-beta",
            ref=stable_target.ref,
        )
    return UpdateTarget(
        version=_fetch_main_target(timeout=timeout).version,
        source="main-fallback-beta",
        ref="main",
    )


def _load_cache() -> dict:
    if not UPDATE_CACHE_PATH.exists():
        return {}
    try:
        raw = json.loads(UPDATE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_cache(payload: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        UPDATE_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _cache_get_channel(cache: dict, channel: str, field: str, fallback: str = "") -> str:
    key = f"{field}_{channel}"
    value = cache.get(key, cache.get(field, fallback))
    return str(value or "").strip()


def _cache_get_checked_at(cache: dict, channel: str) -> int:
    key = f"checked_at_{channel}"
    value = cache.get(key, cache.get("checked_at", 0))
    try:
        return int(value or 0)
    except Exception:
        return 0


def _cache_set_channel(cache: dict, channel: str, *, latest: str, target_ref: str, source: str, now: int, current: str) -> dict:
    payload = dict(cache)
    payload["current_version"] = current
    payload[f"latest_version_{channel}"] = latest
    payload[f"target_ref_{channel}"] = target_ref
    payload[f"source_{channel}"] = source
    payload[f"checked_at_{channel}"] = now
    return payload


def check_for_updates(
    *,
    force_remote: bool = False,
    timeout: float = 2.5,
    channel: str | None = None,
) -> UpdateStatus:
    resolved_channel = _resolve_update_channel(channel)
    current = _current_version()
    now = _now_ts()
    cache = _load_cache()

    latest = _cache_get_channel(cache, resolved_channel, "latest_version")
    target_ref = _cache_get_channel(cache, resolved_channel, "target_ref")
    cached_source = _cache_get_channel(cache, resolved_channel, "source")
    source = "cache"
    checked_at = _cache_get_checked_at(cache, resolved_channel)
    cached_current = str(cache.get("current_version", "")).strip()

    use_cache = (
        (not force_remote)
        and bool(latest)
        and cached_current == current
        and (now - checked_at) < _check_interval_seconds()
    )

    if not use_cache:
        try:
            target = _fetch_remote_target(resolved_channel, timeout=timeout)
            latest = target.version
            target_ref = target.ref
            source = target.source
            _save_cache(
                _cache_set_channel(
                    cache,
                    resolved_channel,
                    latest=latest,
                    target_ref=target_ref,
                    source=source,
                    now=now,
                    current=current,
                )
            )
        except (OSError, RuntimeError, urllib.error.URLError):
            if latest:
                source = "cache-stale"
            else:
                latest = current
                source = "unknown"
    else:
        source = cached_source or "cache"

    available = _is_newer_version(latest, current)
    return UpdateStatus(
        current_version=current,
        latest_version=latest,
        available=available,
        source=source,
        channel=resolved_channel,
        target_ref=target_ref,
    )


def format_update_notice(status: UpdateStatus) -> str:
    if not status.available:
        return ""
    channel_label = status.channel
    ref_hint = f" [{status.target_ref}]" if status.target_ref else ""
    return (
        f"Atualizacao ({channel_label}) disponivel: {status.current_version} -> {status.latest_version}{ref_hint}. "
        "Rode: clawlite update"
    )


def maybe_print_update_notice(print_fn=print) -> None:
    if os.getenv("CLAWLITE_SKIP_UPDATE_CHECK", "").strip() == "1":
        return
    try:
        cfg = load_config()
        update_cfg = cfg.get("update") if isinstance(cfg, dict) else None
        if isinstance(update_cfg, dict) and update_cfg.get("check_on_start") is False:
            return
    except Exception:
        pass
    status = check_for_updates(force_remote=False, timeout=1.8, channel=None)
    notice = format_update_notice(status)
    if notice:
        print_fn(f"ℹ️ {notice}")


def _find_local_repo_root() -> Path | None:
    package_file = Path(clawlite.__file__).resolve()
    for parent in package_file.parents:
        if (parent / ".git").exists() and (parent / "pyproject.toml").exists():
            return parent
    return None


def _run(cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        return True, (proc.stdout or "").strip()
    err = (proc.stderr or proc.stdout or "").strip()
    return False, err


def _repo_is_clean(repo_root: Path) -> bool:
    ok, out = _run(["git", "-C", str(repo_root), "status", "--porcelain"])
    if not ok:
        return False
    return out.strip() == ""


def run_self_update(*, channel: str | None = None) -> tuple[bool, str]:
    resolved_channel = _resolve_update_channel(channel)
    python_bin = sys.executable or "python3"
    repo_root = _find_local_repo_root()

    if resolved_channel == "dev" and repo_root and _repo_is_clean(repo_root):
        ok, err = _run(["git", "-C", str(repo_root), "pull", "--rebase", "origin", "main"])
        if not ok:
            return False, f"Falha ao atualizar repositorio local: {err}"

        ok, err = _run(
            [
                python_bin,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--force-reinstall",
                "--no-cache-dir",
                "--no-deps",
                "-e",
                str(repo_root),
            ]
        )
        if not ok:
            return False, f"Repositorio atualizado, mas falhou no pip install -e: {err}"

        target_version = ""
        try:
            target_version = _fetch_remote_target("dev", timeout=2.5).version
        except Exception:
            target_version = ""
        suffix = f" para {target_version}" if target_version else ""
        return (
            True,
            f"ClawLite ({resolved_channel}) atualizado com sucesso{suffix} (modo local). Reinicie o processo atual.",
        )

    target: UpdateTarget | None = None
    try:
        target = _fetch_remote_target(resolved_channel, timeout=2.5)
    except Exception:
        target = None

    install_spec = f"git+{REPO_URL}"
    if target and target.ref and target.ref != "main":
        install_spec = f"git+{REPO_URL}@{target.ref}"
    elif target and target.ref == "main":
        install_spec = f"git+{REPO_URL}@main"

    ok, err = _run(
        [
            python_bin,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--force-reinstall",
            "--no-cache-dir",
            "--no-deps",
            install_spec,
        ]
    )
    if not ok:
        return False, f"Falha no self-update via pip/git: {err}"

    target_version = target.version if target else ""
    suffix = f" para {target_version}" if target_version else ""
    source_hint = f" [{target.source}]" if target and target.source else ""
    return (
        True,
        f"ClawLite ({resolved_channel}) atualizado com sucesso{suffix}{source_hint}. Reinicie o processo atual.",
    )
