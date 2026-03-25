from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clawlite.providers.discovery import normalize_local_runtime_base_url

PROVIDER_PROBE_CACHE_FILENAME = "provider-probes.json"
PROVIDER_PROBE_CACHE_VERSION = 1


def provider_probe_cache_path(state_path: str | Path | None) -> Path:
    base = Path(state_path).expanduser() if state_path else (Path.home() / ".clawlite" / "state")
    return base / PROVIDER_PROBE_CACHE_FILENAME


def normalize_provider_probe_base_url(provider: str, base_url: str) -> str:
    provider_key = str(provider or "").strip().lower().replace("-", "_")
    text = str(base_url or "").strip()
    if not text:
        return ""
    if provider_key in {"ollama", "vllm"}:
        text = normalize_local_runtime_base_url(provider_key, text)
    return text.rstrip("/")


def _empty_provider_probe_cache() -> dict[str, Any]:
    return {"version": PROVIDER_PROBE_CACHE_VERSION, "providers": {}}


def provider_probe_capability_summary(payload: dict[str, Any]) -> dict[str, Any]:
    provider_key = str(payload.get("provider", "") or "").strip().lower().replace("-", "_")
    model = str(payload.get("model", "") or "").strip()
    transport = str(payload.get("transport", "") or "").strip()
    checked_at = str(payload.get("checked_at", "") or "").strip()
    source = str(payload.get("source", "") or "").strip()
    model_check = dict(payload.get("model_check", {}) or {})
    available_models_raw = model_check.get("available_models", [])
    available_models: list[str] = []
    if isinstance(available_models_raw, list):
        seen: set[str] = set()
        for item in available_models_raw:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            available_models.append(value)
    checked = bool(model_check.get("checked", False))
    current_model_listed = checked and bool(model_check.get("ok", False))
    detail = str(model_check.get("detail", "") or "").strip()
    summary = {
        "provider": provider_key,
        "model": model,
        "transport": transport,
        "checked_at": checked_at,
        "source": source,
        "checked": checked,
        "current_model_listed": current_model_listed,
        "detail": detail or ("model_listed" if current_model_listed else ("model_not_listed" if checked else "model_list_unavailable")),
        "listed_model_count": len(available_models),
        "listed_model_sample": available_models[:5],
    }
    matched_model = str(model_check.get("matched_model", "") or "").strip()
    if matched_model:
        summary["matched_model"] = matched_model
    return summary


def _load_provider_probe_cache_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_provider_probe_cache()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_provider_probe_cache()
    if not isinstance(payload, dict):
        return _empty_provider_probe_cache()
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    return {
        "version": PROVIDER_PROBE_CACHE_VERSION,
        "providers": dict(providers),
    }


def load_provider_probe_snapshot(state_path: str | Path | None, provider: str) -> dict[str, Any] | None:
    provider_key = str(provider or "").strip().lower().replace("-", "_")
    if not provider_key:
        return None
    payload = _load_provider_probe_cache_payload(provider_probe_cache_path(state_path))
    snapshot = payload.get("providers", {}).get(provider_key)
    return dict(snapshot) if isinstance(snapshot, dict) else None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        handle.write("\n")
        temp_path = Path(handle.name)
    os.replace(str(temp_path), str(path))


def save_provider_probe_snapshot(
    state_path: str | Path | None,
    *,
    provider: str,
    payload: dict[str, Any],
    source: str = "provider_live_probe",
) -> dict[str, Any]:
    provider_key = str(provider or payload.get("provider", "") or "").strip().lower().replace("-", "_")
    checked_at = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "provider": provider_key,
        "model": str(payload.get("model", "") or "").strip(),
        "base_url": normalize_provider_probe_base_url(provider_key, str(payload.get("base_url", "") or "").strip()),
        "base_url_source": str(payload.get("base_url_source", "") or "").strip(),
        "transport": str(payload.get("transport", "") or "").strip(),
        "probe_method": str(payload.get("probe_method", "") or "").strip(),
        "endpoint": str(payload.get("endpoint", "") or "").strip(),
        "ok": bool(payload.get("ok", False)),
        "status_code": int(payload.get("status_code", 0) or 0),
        "error": str(payload.get("error", "") or "").strip(),
        # Keep the persisted snapshot free of remote/raw error bodies.
        "error_detail": "",
        "error_class": str(payload.get("error_class", "") or "").strip(),
        "family": str(payload.get("family", "") or "").strip(),
        "recommended_model": str(payload.get("recommended_model", "") or "").strip(),
        "recommended_models": list(payload.get("recommended_models", []) or []),
        "onboarding_hint": str(payload.get("onboarding_hint", "") or "").strip(),
        "hints": list(payload.get("hints", []) or []),
        "model_check": dict(payload.get("model_check", {}) or {}),
        "checked_at": checked_at,
        "source": str(source or "provider_live_probe").strip() or "provider_live_probe",
    }
    snapshot["capability_summary"] = provider_probe_capability_summary(snapshot)
    if not provider_key:
        return snapshot

    path = provider_probe_cache_path(state_path)
    try:
        cache_payload = _load_provider_probe_cache_payload(path)
        providers = dict(cache_payload.get("providers", {}) or {})
        providers[provider_key] = snapshot
        _atomic_write_json(
            path,
            {
                "version": PROVIDER_PROBE_CACHE_VERSION,
                "providers": providers,
            },
        )
    except Exception:
        return snapshot
    return snapshot
