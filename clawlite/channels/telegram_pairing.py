from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import secrets
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

PAIRING_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIRING_CODE_LENGTH = 8
PAIRING_PENDING_TTL_S = 60 * 60
PAIRING_MAX_PENDING = 256


@dataclass(slots=True)
class TelegramPairingRequest:
    chat_id: str
    user_id: str
    username: str = ""
    first_name: str = ""
    code: str = ""
    created_at: str = ""
    last_seen_at: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TelegramPairingRequest" | None:
        if not isinstance(payload, dict):
            return None
        chat_id = str(payload.get("chat_id", "") or "").strip()
        user_id = str(payload.get("user_id", "") or "").strip()
        code = str(payload.get("code", "") or "").strip().upper()
        if not chat_id or not user_id or not code:
            return None
        created_at = str(payload.get("created_at", "") or "").strip()
        last_seen_at = str(payload.get("last_seen_at", "") or "").strip()
        return cls(
            chat_id=chat_id,
            user_id=user_id,
            username=str(payload.get("username", "") or "").strip(),
            first_name=str(payload.get("first_name", "") or "").strip(),
            code=code,
            created_at=created_at,
            last_seen_at=last_seen_at or created_at,
        )

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


class TelegramPairingStore:
    def __init__(self, *, token: str, state_path: str = "") -> None:
        self.path = self._resolve_path(token=token, state_path=state_path)

    @staticmethod
    def _resolve_path(*, token: str, state_path: str) -> Path:
        raw = str(state_path or "").strip()
        if raw:
            return Path(raw).expanduser()
        fingerprint = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()[:16]
        return Path.home() / ".clawlite" / "state" / "telegram" / f"pairing-{fingerprint}.json"

    @staticmethod
    def _now_iso() -> str:
        return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _parse_timestamp(value: str) -> float | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = dt.datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.timestamp()

    def _read_store(self) -> dict[str, Any]:
        path = self.path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return {"version": 1, "approved": [], "pending": []}
        if not path.exists():
            return {"version": 1, "approved": [], "pending": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("telegram pairing store read failed path={} error={}", path, exc)
            return {"version": 1, "approved": [], "pending": []}
        if not isinstance(payload, dict):
            return {"version": 1, "approved": [], "pending": []}
        approved_raw = payload.get("approved", [])
        pending_raw = payload.get("pending", [])
        approved = [str(entry).strip() for entry in approved_raw if str(entry).strip()] if isinstance(approved_raw, list) else []
        pending = pending_raw if isinstance(pending_raw, list) else []
        return {"version": 1, "approved": approved, "pending": pending}

    def _write_store(self, payload: dict[str, Any]) -> None:
        path = self.path
        tmp_path = path.with_suffix(f"{path.suffix}.tmp.{secrets.token_hex(4)}")
        dir_fd: int | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            with tmp_path.open("wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            try:
                open_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                dir_fd = os.open(str(path.parent), open_flags)
                os.fsync(dir_fd)
            except OSError:
                pass
        finally:
            if dir_fd is not None:
                try:
                    os.close(dir_fd)
                except OSError:
                    pass
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass

    def _normalize_approved(self, entries: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            value = str(entry or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _pending_requests(self, payload: dict[str, Any]) -> list[TelegramPairingRequest]:
        requests: list[TelegramPairingRequest] = []
        for raw in payload.get("pending", []):
            request = TelegramPairingRequest.from_payload(raw)
            if request is not None:
                requests.append(request)
        return requests

    def _prune_pending(self, requests: list[TelegramPairingRequest]) -> tuple[list[TelegramPairingRequest], bool]:
        now_ts = dt.datetime.now(dt.timezone.utc).timestamp()
        kept: list[TelegramPairingRequest] = []
        removed = False
        for request in requests:
            created_at_ts = self._parse_timestamp(request.created_at)
            if created_at_ts is None or (now_ts - created_at_ts) > PAIRING_PENDING_TTL_S:
                removed = True
                continue
            kept.append(request)
        if len(kept) > PAIRING_MAX_PENDING:
            kept.sort(key=lambda item: self._parse_timestamp(item.last_seen_at) or 0.0)
            kept = kept[-PAIRING_MAX_PENDING:]
            removed = True
        return kept, removed

    @staticmethod
    def _random_code() -> str:
        out = []
        for _ in range(PAIRING_CODE_LENGTH):
            idx = secrets.randbelow(len(PAIRING_CODE_ALPHABET))
            out.append(PAIRING_CODE_ALPHABET[idx])
        return "".join(out)

    def _generate_unique_code(self, existing: set[str]) -> str:
        for _ in range(500):
            code = self._random_code()
            if code not in existing:
                return code
        raise RuntimeError("failed to generate unique telegram pairing code")

    def list_pending(self) -> list[dict[str, Any]]:
        payload = self._read_store()
        requests, removed = self._prune_pending(self._pending_requests(payload))
        if removed:
            payload["pending"] = [request.to_payload() for request in requests]
            self._write_store(payload)
        return [request.to_payload() for request in requests]

    def approved_entries(self) -> list[str]:
        payload = self._read_store()
        approved = self._normalize_approved(list(payload.get("approved", [])))
        if approved != payload.get("approved", []):
            payload["approved"] = approved
            self._write_store(payload)
        return approved

    def issue_request(
        self,
        *,
        chat_id: str,
        user_id: str,
        username: str = "",
        first_name: str = "",
    ) -> tuple[dict[str, Any], bool]:
        payload = self._read_store()
        approved = self._normalize_approved(list(payload.get("approved", [])))
        requests, removed = self._prune_pending(self._pending_requests(payload))
        chat_value = str(chat_id or "").strip()
        user_value = str(user_id or "").strip()
        if not chat_value or not user_value:
            raise ValueError("chat_id and user_id are required for telegram pairing")

        for request in requests:
            if request.chat_id == chat_value and request.user_id == user_value:
                request.last_seen_at = self._now_iso()
                if username:
                    request.username = str(username).strip()
                if first_name:
                    request.first_name = str(first_name).strip()
                payload["approved"] = approved
                payload["pending"] = [item.to_payload() for item in requests]
                self._write_store(payload)
                return request.to_payload(), False

        code = self._generate_unique_code({request.code for request in requests})
        now_iso = self._now_iso()
        request = TelegramPairingRequest(
            chat_id=chat_value,
            user_id=user_value,
            username=str(username or "").strip(),
            first_name=str(first_name or "").strip(),
            code=code,
            created_at=now_iso,
            last_seen_at=now_iso,
        )
        requests.append(request)
        requests, removed = self._prune_pending(requests)
        payload["approved"] = approved
        payload["pending"] = [item.to_payload() for item in requests]
        self._write_store(payload)
        return request.to_payload(), True

    def approve(self, code: str) -> dict[str, Any] | None:
        normalized_code = str(code or "").strip().upper()
        if not normalized_code:
            return None
        payload = self._read_store()
        approved = self._normalize_approved(list(payload.get("approved", [])))
        requests, removed = self._prune_pending(self._pending_requests(payload))

        target: TelegramPairingRequest | None = None
        kept: list[TelegramPairingRequest] = []
        for request in requests:
            if target is None and request.code == normalized_code:
                target = request
                continue
            kept.append(request)

        if target is None:
            if removed:
                payload["approved"] = approved
                payload["pending"] = [item.to_payload() for item in kept]
                self._write_store(payload)
            return None

        next_approved = list(approved)
        next_approved.append(target.user_id)
        if target.username:
            next_approved.append(target.username)
            next_approved.append(f"@{target.username}")
        normalized_approved = self._normalize_approved(next_approved)

        payload["approved"] = normalized_approved
        payload["pending"] = [item.to_payload() for item in kept]
        self._write_store(payload)
        return {
            "approved_entries": normalized_approved,
            "request": target.to_payload(),
        }

    def reject(self, code: str) -> dict[str, Any] | None:
        normalized_code = str(code or "").strip().upper()
        if not normalized_code:
            return None
        payload = self._read_store()
        approved = self._normalize_approved(list(payload.get("approved", [])))
        requests, removed = self._prune_pending(self._pending_requests(payload))

        target: TelegramPairingRequest | None = None
        kept: list[TelegramPairingRequest] = []
        for request in requests:
            if target is None and request.code == normalized_code:
                target = request
                continue
            kept.append(request)

        if target is None:
            if removed:
                payload["approved"] = approved
                payload["pending"] = [item.to_payload() for item in kept]
                self._write_store(payload)
            return None

        payload["approved"] = approved
        payload["pending"] = [item.to_payload() for item in kept]
        self._write_store(payload)
        return {
            "approved_entries": approved,
            "request": target.to_payload(),
        }
