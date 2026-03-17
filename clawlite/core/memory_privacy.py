from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any, Callable


def privacy_settings(
    *,
    load_json_dict: Callable[[Path, dict[str, Any]], dict[str, Any]],
    privacy_path: Path,
    default_privacy: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    payload = load_json_dict(privacy_path, default_privacy())
    merged = default_privacy()
    merged.update(payload)
    return merged


def append_privacy_audit_event(
    *,
    action: str,
    reason: str,
    source: str,
    category: str,
    record_id: str,
    metadata: dict[str, Any] | None,
    diagnostics: dict[str, Any],
    privacy_settings_loader: Callable[[], dict[str, Any]],
    utcnow_iso: Callable[[], str],
    locked_file: Callable[..., Any],
    flush_and_fsync: Callable[[Any], None],
    privacy_audit_path: Path,
) -> None:
    settings = privacy_settings_loader()
    if not bool(settings.get("audit_log", True)):
        diagnostics["privacy_audit_skipped"] = int(diagnostics.get("privacy_audit_skipped", 0)) + 1
        return
    payload: dict[str, Any] = {
        "timestamp": utcnow_iso(),
        "action": str(action or "unknown"),
        "reason": str(reason or ""),
    }
    if source:
        payload["source"] = str(source)
    if category:
        payload["category"] = str(category)
    if record_id:
        payload["id"] = str(record_id)
    if isinstance(metadata, dict) and metadata:
        payload["metadata"] = metadata
    try:
        with locked_file(privacy_audit_path, "a", exclusive=True) as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            flush_and_fsync(fh)
        diagnostics["privacy_audit_writes"] = int(diagnostics.get("privacy_audit_writes", 0)) + 1
    except Exception as exc:
        diagnostics["privacy_audit_errors"] = int(diagnostics.get("privacy_audit_errors", 0)) + 1
        diagnostics["last_error"] = str(exc)


def encrypted_prefix() -> str:
    return "enc:v2:"


def legacy_encrypted_prefix() -> str:
    return "enc:v1:"


def xor_with_keystream(data: bytes, *, key: bytes, nonce: bytes) -> bytes:
    output = bytearray(len(data))
    counter = 0
    cursor = 0
    while cursor < len(data):
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        take = min(len(block), len(data) - cursor)
        for idx in range(take):
            output[cursor + idx] = data[cursor + idx] ^ block[idx]
        cursor += take
        counter += 1
    return bytes(output)


def load_or_create_privacy_key(
    *,
    cached_key: bytes | bytearray | None,
    privacy_key_path: Path,
    diagnostics: dict[str, Any],
) -> bytes | None:
    if isinstance(cached_key, (bytes, bytearray)) and len(cached_key) == 32:
        return bytes(cached_key)

    try:
        if privacy_key_path.exists():
            raw = privacy_key_path.read_bytes()
            if len(raw) == 32:
                diagnostics["privacy_key_load_events"] = int(diagnostics.get("privacy_key_load_events", 0)) + 1
                return raw
            stripped = raw.strip()
            try:
                decoded = base64.urlsafe_b64decode(stripped)
            except Exception:
                decoded = b""
            if len(decoded) == 32:
                diagnostics["privacy_key_load_events"] = int(diagnostics.get("privacy_key_load_events", 0)) + 1
                return decoded
    except Exception as exc:
        diagnostics["privacy_key_errors"] = int(diagnostics.get("privacy_key_errors", 0)) + 1
        diagnostics["last_error"] = str(exc)

    key = secrets.token_bytes(32)
    try:
        fd = os.open(str(privacy_key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(key)
                fh.flush()
                try:
                    os.fsync(fh.fileno())
                except Exception:
                    pass
        finally:
            try:
                os.chmod(privacy_key_path, 0o600)
            except Exception:
                pass
        diagnostics["privacy_key_create_events"] = int(diagnostics.get("privacy_key_create_events", 0)) + 1
        return key
    except Exception as exc:
        diagnostics["privacy_key_errors"] = int(diagnostics.get("privacy_key_errors", 0)) + 1
        diagnostics["last_error"] = str(exc)
        return None


def is_encrypted_category(
    category: str,
    *,
    settings: dict[str, Any] | None,
    privacy_settings_loader: Callable[[], dict[str, Any]],
) -> bool:
    payload = settings if isinstance(settings, dict) else privacy_settings_loader()
    raw_categories = payload.get("encrypted_categories", [])
    if not isinstance(raw_categories, list):
        return False
    categories = {str(item or "").strip().lower() for item in raw_categories if str(item or "").strip()}
    return str(category or "").strip().lower() in categories


def encrypt_text_for_category(
    text: str,
    category: str,
    *,
    settings: dict[str, Any] | None,
    privacy_settings_loader: Callable[[], dict[str, Any]],
    load_or_create_privacy_key_fn: Callable[[], bytes | None],
    xor_with_keystream_fn: Callable[..., bytes],
    diagnostics: dict[str, Any],
) -> str:
    clean = str(text or "")
    if not clean:
        return clean
    if not is_encrypted_category(category, settings=settings, privacy_settings_loader=privacy_settings_loader):
        return clean
    try:
        key = load_or_create_privacy_key_fn()
        if key is None:
            return clean
        nonce = secrets.token_bytes(16)
        ciphertext = xor_with_keystream_fn(clean.encode("utf-8"), key=key, nonce=nonce)
        tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        encoded = base64.urlsafe_b64encode(nonce + ciphertext + tag).decode("ascii")
        diagnostics["privacy_encrypt_events"] = int(diagnostics.get("privacy_encrypt_events", 0)) + 1
        return f"{encrypted_prefix()}{encoded}"
    except Exception as exc:
        diagnostics["privacy_encrypt_errors"] = int(diagnostics.get("privacy_encrypt_errors", 0)) + 1
        diagnostics["last_error"] = str(exc)
        return clean


def decrypt_text_for_category(
    text: str,
    category: str,
    *,
    settings: dict[str, Any] | None,
    load_or_create_privacy_key_fn: Callable[[], bytes | None],
    xor_with_keystream_fn: Callable[..., bytes],
    diagnostics: dict[str, Any],
) -> str:
    clean = str(text or "")
    if not clean:
        return clean
    prefix_v2 = encrypted_prefix()
    prefix_v1 = legacy_encrypted_prefix()
    if not clean.startswith(prefix_v2) and not clean.startswith(prefix_v1):
        return clean
    _ = category
    _ = settings
    try:
        if clean.startswith(prefix_v2):
            encoded = clean[len(prefix_v2) :]
            payload = base64.urlsafe_b64decode(encoded.encode("ascii"))
            if len(payload) < 16 + 32:
                raise ValueError("invalid_enc_v2_payload")
            nonce = payload[:16]
            ciphertext = payload[16:-32]
            tag = payload[-32:]
            key = load_or_create_privacy_key_fn()
            if key is None:
                return clean
            expected_tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected_tag):
                raise ValueError("invalid_enc_v2_tag")
            decoded = xor_with_keystream_fn(ciphertext, key=key, nonce=nonce).decode("utf-8")
        else:
            encoded = clean[len(prefix_v1) :]
            decoded = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
        diagnostics["privacy_decrypt_events"] = int(diagnostics.get("privacy_decrypt_events", 0)) + 1
        return decoded
    except Exception as exc:
        diagnostics["privacy_decrypt_errors"] = int(diagnostics.get("privacy_decrypt_errors", 0)) + 1
        diagnostics["last_error"] = str(exc)
        return clean


def privacy_block_reason(
    text: str,
    *,
    privacy_settings_loader: Callable[[], dict[str, Any]],
) -> str | None:
    privacy = privacy_settings_loader()
    patterns = privacy.get("never_memorize_patterns", [])
    if not isinstance(patterns, list):
        patterns = []
    lowered = str(text or "").lower()
    for item in patterns:
        pattern = str(item or "").strip().lower()
        if pattern and pattern in lowered:
            return f"pattern:{pattern}"
    return None


__all__ = [
    "append_privacy_audit_event",
    "decrypt_text_for_category",
    "encrypt_text_for_category",
    "encrypted_prefix",
    "is_encrypted_category",
    "legacy_encrypted_prefix",
    "load_or_create_privacy_key",
    "privacy_block_reason",
    "privacy_settings",
    "xor_with_keystream",
]
