from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from clawlite.config.settings import load_config, save_config
from clawlite.gateway.state import (
    DASHBOARD_DIR,
    LOG_RING,
    SETTINGS_FILE,
    SESSIONS_FILE,
    TELEMETRY_FILE,
    _CONSOLE,
    _GATEWAY_LOG_FILE,
    _LOGS_DIR,
    log_connections,
)


def _version() -> str:
    try:
        from importlib.metadata import version as _pkg_version
        return _pkg_version("clawlite")
    except Exception:
        return "dev"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    if not slug:
        raise HTTPException(status_code=400, detail="Slug inválido")
    return slug


def _ensure_dashboard_store() -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    _ensure_dashboard_store()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except json.JSONDecodeError:
            continue
    return rows


def _load_dashboard_settings() -> dict[str, Any]:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {
        "theme": "dark",
        "hooks": {"pre": "", "post": ""},
    }


def _save_dashboard_settings(data: dict[str, Any]) -> None:
    _ensure_dashboard_store()
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.strip()) // 4)


def _looks_cheap_model(model: str) -> bool:
    return any(x in model.lower() for x in ("mini", "flash", "haiku", "nano"))


def _pricing_per_1k(model: str) -> tuple[float, float]:
    normalized = model.lower()
    if normalized.startswith("openai/"):
        return (0.00015, 0.0006) if _looks_cheap_model(model) else (0.005, 0.015)
    if normalized.startswith("openrouter/"):
        return (0.0005, 0.0015) if _looks_cheap_model(model) else (0.004, 0.012)
    if normalized.startswith("ollama/") or normalized.startswith("local/"):
        return 0.0, 0.0
    return (0.0005, 0.0015) if _looks_cheap_model(model) else (0.003, 0.009)


def _estimate_cost_parts_usd(prompt_tokens: int, completion_tokens: int, model: str) -> tuple[float, float]:
    in_rate, out_rate = _pricing_per_1k(model)
    prompt_cost = round((prompt_tokens / 1000.0) * in_rate, 6)
    completion_cost = round((completion_tokens / 1000.0) * out_rate, 6)
    return prompt_cost, completion_cost


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _period_start(period: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    p = period.strip().lower()
    if p in {"", "all"}:
        return None
    if p == "24h":
        return now - timedelta(hours=24)
    if p == "7d":
        return now - timedelta(days=7)
    if p == "30d":
        return now - timedelta(days=30)
    if p == "today":
        return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    if p == "week":
        base = now - timedelta(days=now.weekday())
        return datetime(base.year, base.month, base.day, tzinfo=timezone.utc)
    if p == "month":
        return datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    return None


def _format_log_line(entry: dict[str, Any]) -> tuple[str, str]:
    dt = _parse_ts(entry.get("ts")) or datetime.now(timezone.utc)
    ts = dt.strftime("%Y-%m-%d %H:%M:%S")
    level = str(entry.get("level", "info")).upper()
    event = str(entry.get("event", "system"))
    data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
    category = (event.split(".", 1)[0] if "." in event else event).lower()

    if event == "gateway.started":
        msg = f"gateway started on {data.get('host', '0.0.0.0')}:{data.get('port', '-') }"
        category = "gateway"
    elif event == "chat.message":
        msg = f"chat session={data.get('session_id','-')} model={data.get('model','-')} mode={data.get('mode','-')}"
        category = "chat"
    elif event.startswith("skills."):
        slug = data.get("slug", "-")
        verb = event.split(".", 1)[1] if "." in event else "action"
        msg = f"skill {slug}.{verb} → ok"
        category = "skill"
    else:
        suffix = ""
        if data:
            try:
                suffix = " " + json.dumps(data, ensure_ascii=False)
            except Exception:
                suffix = ""
        msg = f"{event}{suffix}"

    plain = f"[{ts}] {level} {category} {msg}".strip()

    color = "cyan"
    if level == "WARN":
        color = "yellow"
    elif level == "ERROR":
        color = "red"
    rich_line = f"[{ts}] [{color}]{level}[/{color}] [bold]{category}[/bold] {msg}"
    return plain, rich_line


def _persist_log_line(text: str) -> None:
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with _GATEWAY_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(text + "\n")


def _log(event: str, level: str = "info", data: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "ts": _iso_now(),
        "level": level,
        "event": event,
        "data": data or {},
    }
    LOG_RING.append(entry)

    plain, rich_line = _format_log_line(entry)
    _persist_log_line(plain)
    if _CONSOLE is not None:
        _CONSOLE.print(rich_line)
    else:
        print(plain)

    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return entry
    for ws, filters in list(log_connections.items()):
        if not _log_matches(
            entry,
            level=str(filters.get("level", "")),
            event=str(filters.get("event", "")),
            query=str(filters.get("q", "")),
        ):
            continue
        try:
            loop.create_task(ws.send_json({"type": "log", "payload": entry}))
        except Exception:
            log_connections.pop(ws, None)
    return entry


def _log_matches(entry: dict[str, Any], *, level: str = "", event: str = "", query: str = "") -> bool:
    if level and str(entry.get("level", "")).lower() != level.lower():
        return False
    if event and event.lower() not in str(entry.get("event", "")).lower():
        return False
    if query:
        haystack = json.dumps(entry, ensure_ascii=False).lower()
        if query.lower() not in haystack:
            return False
    return True


def _filter_logs(rows: list[dict[str, Any]], *, level: str = "", event: str = "", query: str = "") -> list[dict[str, Any]]:
    return [row for row in rows if _log_matches(row, level=level, event=event, query=query)]


def _token() -> str:
    cfg = load_config()
    t = os.getenv("CLAWLITE_GATEWAY_TOKEN") or cfg.get("gateway", {}).get("token", "")
    if not t:
        t = secrets.token_urlsafe(24)
        cfg.setdefault("gateway", {})["token"] = t
        save_config(cfg)
    return t


def _check_bearer(auth: str | None) -> None:
    expected = _token()
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    got = auth.removeprefix("Bearer ").strip()
    if got != expected:
        raise HTTPException(status_code=403, detail="Invalid token")

def _hub_manifest_path() -> Path:
    custom = os.getenv("CLAWLITE_HUB_MANIFEST")
    if custom:
        return Path(custom).expanduser()
    return Path.cwd() / "hub" / "marketplace" / "manifest.local.json"

def _skills_dir() -> Path:
    return Path.cwd() / "skills"


def _telemetry_tokens(row: dict[str, Any]) -> tuple[int, int, int]:
    prompt = int(row.get("prompt_tokens", 0) or 0)
    completion = int(row.get("completion_tokens", 0) or 0)
    total = int(row.get("tokens", 0) or 0)
    if prompt == 0 and completion == 0 and total > 0:
        prompt = total // 2
        completion = total - prompt
    if total == 0:
        total = prompt + completion
    return prompt, completion, total


def _telemetry_costs(row: dict[str, Any]) -> tuple[float, float, float]:
    prompt_cost = float(row.get("prompt_cost_usd", 0.0) or 0.0)
    completion_cost = float(row.get("completion_cost_usd", 0.0) or 0.0)
    total_cost = float(row.get("cost_usd", 0.0) or 0.0)
    if prompt_cost == 0.0 and completion_cost == 0.0 and total_cost > 0.0:
        prompt_cost = round(total_cost / 2.0, 6)
        completion_cost = round(total_cost - prompt_cost, 6)
    if total_cost == 0.0:
        total_cost = round(prompt_cost + completion_cost, 6)
    return prompt_cost, completion_cost, total_cost
