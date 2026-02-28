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
from clawlite.config.settings import CONFIG_DIR

REPO_URL = "https://github.com/eobarretooo/ClawLite.git"
REMOTE_PYPROJECT_URL = "https://raw.githubusercontent.com/eobarretooo/ClawLite/main/pyproject.toml"
DEFAULT_CHECK_INTERVAL_SECONDS = 6 * 60 * 60
UPDATE_CACHE_PATH = CONFIG_DIR / "update-cache.json"


@dataclass(frozen=True)
class UpdateStatus:
    current_version: str
    latest_version: str
    available: bool
    source: str


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


def _fetch_remote_version(timeout: float = 2.5) -> str:
    req = urllib.request.Request(
        REMOTE_PYPROJECT_URL,
        headers={"User-Agent": "clawlite-update-check/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return _extract_version_from_pyproject(body)


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


def check_for_updates(*, force_remote: bool = False, timeout: float = 2.5) -> UpdateStatus:
    current = _current_version()
    now = _now_ts()
    cache = _load_cache()

    latest = str(cache.get("latest_version", "")).strip()
    source = "cache"
    checked_at = int(cache.get("checked_at", 0) or 0)
    cached_current = str(cache.get("current_version", "")).strip()

    use_cache = (
        (not force_remote)
        and bool(latest)
        and cached_current == current
        and (now - checked_at) < _check_interval_seconds()
    )

    if not use_cache:
        try:
            latest = _fetch_remote_version(timeout=timeout)
            source = "remote"
            _save_cache(
                {
                    "current_version": current,
                    "latest_version": latest,
                    "checked_at": now,
                }
            )
        except (OSError, RuntimeError, urllib.error.URLError):
            if latest:
                source = "cache-stale"
            else:
                latest = current
                source = "unknown"

    available = _is_newer_version(latest, current)
    return UpdateStatus(
        current_version=current,
        latest_version=latest,
        available=available,
        source=source,
    )


def format_update_notice(status: UpdateStatus) -> str:
    if not status.available:
        return ""
    return (
        f"Atualizacao disponivel: {status.current_version} -> {status.latest_version}. "
        "Rode: clawlite update"
    )


def maybe_print_update_notice(print_fn=print) -> None:
    if os.getenv("CLAWLITE_SKIP_UPDATE_CHECK", "").strip() == "1":
        return
    status = check_for_updates(force_remote=False, timeout=1.8)
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


def run_self_update() -> tuple[bool, str]:
    python_bin = sys.executable or "python3"
    repo_root = _find_local_repo_root()

    if repo_root and _repo_is_clean(repo_root):
        ok, err = _run(["git", "-C", str(repo_root), "pull", "--rebase", "origin", "main"])
        if not ok:
            return False, f"Falha ao atualizar repositorio local: {err}"

        ok, err = _run([python_bin, "-m", "pip", "install", "--upgrade", "-e", str(repo_root)])
        if not ok:
            return False, f"Repositorio atualizado, mas falhou no pip install -e: {err}"

        target = ""
        try:
            target = _fetch_remote_version(timeout=2.5)
        except Exception:
            target = ""
        suffix = f" para {target}" if target else ""
        return True, f"ClawLite atualizado com sucesso{suffix} (modo local). Reinicie o processo atual."

    ok, err = _run([python_bin, "-m", "pip", "install", "--upgrade", f"git+{REPO_URL}"])
    if not ok:
        return False, f"Falha no self-update via pip/git: {err}"

    target = ""
    try:
        target = _fetch_remote_version(timeout=2.5)
    except Exception:
        target = ""
    suffix = f" para {target}" if target else ""
    return True, f"ClawLite atualizado com sucesso{suffix}. Reinicie o processo atual."
