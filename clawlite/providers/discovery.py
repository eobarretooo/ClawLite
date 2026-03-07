from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx


def _join_base(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    suffix = str(path or "").strip()
    if not suffix.startswith("/"):
        suffix = f"/{suffix}"
    return f"{base}{suffix}"


def _origin(base_url: str) -> str:
    parsed = urlparse(str(base_url or "").strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return str(base_url or "").strip().rstrip("/")


def normalize_local_runtime_base_url(runtime: str, base_url: str) -> str:
    candidate = str(base_url or "").strip().rstrip("/")
    if not candidate:
        return candidate
    runtime_name = str(runtime or "").strip().lower()
    if runtime_name == "ollama":
        root = _origin(candidate)
        return f"{root}/v1"
    if runtime_name == "vllm":
        return candidate if candidate.endswith("/v1") else f"{candidate}/v1"
    return candidate


def _normalized_model_name(model: str) -> str:
    candidate = str(model or "").strip()
    if "/" in candidate:
        candidate = candidate.split("/", 1)[1]
    return candidate


def _canonical_model_name(model: str) -> str:
    candidate = _normalized_model_name(model)
    if ":" in candidate:
        candidate = candidate.split(":", 1)[0]
    return candidate


def _model_matches(target: str, candidate: str) -> bool:
    wanted = _canonical_model_name(target)
    offered = _canonical_model_name(candidate)
    return bool(wanted) and wanted == offered


def _loopback_host(host: str) -> bool:
    value = str(host or "").strip().lower()
    return value in {"localhost", "0.0.0.0", "::1", "host.docker.internal"} or value.startswith("127.")


def detect_local_runtime(base_url: str) -> str:
    parsed = urlparse(str(base_url or "").strip())
    raw = str(base_url or "").strip().lower()
    if not raw:
        return ""
    if parsed.port == 11434 or "ollama" in raw:
        return "ollama"
    if parsed.port == 8000 or "vllm" in raw:
        return "vllm"
    return ""


def _extract_names(payload: Any, *, list_key: str, field_names: tuple[str, ...]) -> list[str]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(list_key)
    if not isinstance(rows, list):
        return []
    names: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field_name in field_names:
            value = str(row.get(field_name, "") or "").strip()
            if value:
                names.append(value)
                break
    return names


def probe_local_provider_runtime(*, model: str, base_url: str, timeout_s: float = 2.0) -> dict[str, Any]:
    runtime = detect_local_runtime(base_url)
    target_model = _normalized_model_name(model)
    payload: dict[str, Any] = {
        "checked": bool(runtime),
        "ok": True,
        "runtime": runtime,
        "base_url": str(base_url or "").strip(),
        "model": target_model,
        "error": "",
        "detail": "",
        "available_models": [],
    }
    if not runtime:
        return payload

    try:
        with httpx.Client(timeout=max(0.5, float(timeout_s))) as client:
            if runtime == "ollama":
                origin = _origin(base_url)
                tags_response = client.get(_join_base(origin, "/api/tags"))
                if not tags_response.is_success:
                    payload["ok"] = False
                    payload["error"] = f"provider_config_error:ollama_unreachable:{base_url}"
                    payload["detail"] = f"http_status:{tags_response.status_code}"
                    return payload
                try:
                    tags_payload: Any = tags_response.json()
                except Exception:
                    tags_payload = {}
                available_models = _extract_names(tags_payload, list_key="models", field_names=("name", "model"))
                payload["available_models"] = available_models
                if any(_model_matches(target_model, row) for row in available_models):
                    return payload

                show_response = client.post(_join_base(origin, "/api/show"), json={"name": target_model})
                if show_response.is_success:
                    return payload

                payload["ok"] = False
                payload["error"] = f"provider_config_error:ollama_model_missing:{target_model}"
                payload["detail"] = f"http_status:{show_response.status_code}"
                return payload

            health_response = client.get(_join_base(_origin(base_url), "/health"))
            if not health_response.is_success:
                payload["ok"] = False
                payload["error"] = f"provider_config_error:vllm_unreachable:{base_url}"
                payload["detail"] = f"http_status:{health_response.status_code}"
                return payload

            models_path = "/models" if str(base_url or "").strip().rstrip("/").endswith("/v1") else "/v1/models"
            models_response = client.get(_join_base(base_url, models_path))
            if not models_response.is_success:
                payload["ok"] = False
                payload["error"] = f"provider_config_error:vllm_unreachable:{base_url}"
                payload["detail"] = f"http_status:{models_response.status_code}"
                return payload
            try:
                models_payload: Any = models_response.json()
            except Exception:
                models_payload = {}
            available_models = _extract_names(models_payload, list_key="data", field_names=("id", "model"))
            payload["available_models"] = available_models
            if any(_model_matches(target_model, row) for row in available_models):
                return payload

            payload["ok"] = False
            payload["error"] = f"provider_config_error:vllm_model_missing:{target_model}"
            payload["detail"] = "model_not_listed"
            return payload
    except Exception as exc:
        payload["ok"] = False
        payload["error"] = f"provider_config_error:{runtime}_unreachable:{base_url}"
        payload["detail"] = str(exc)
        return payload
