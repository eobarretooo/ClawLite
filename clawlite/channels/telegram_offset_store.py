from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STORE_SCHEMA_VERSION = 3


def _coerce_update_id(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("telegram update_id must be an integer") from exc
    if parsed < 0:
        raise ValueError("telegram update_id must be >= 0")
    return parsed


def _coerce_optional_update_id(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    return _coerce_update_id(value)


def _extract_bot_id(token: str) -> str:
    value = str(token or "").strip()
    if not value:
        return ""
    head, _, _tail = value.partition(":")
    return head if head.isdigit() else ""


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()[:16]


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True, frozen=True)
class TelegramOffsetSnapshot:
    path: str
    bot_id: str
    token_fingerprint: str
    safe_update_id: int | None
    highest_completed_update_id: int | None
    completed_update_ids: tuple[int, ...]
    pending_update_ids: tuple[int, ...]
    updated_at: str = ""

    @property
    def next_offset(self) -> int:
        if self.safe_update_id is None:
            return 0
        return self.safe_update_id + 1

    @property
    def pending_count(self) -> int:
        return len(self.pending_update_ids)

    @property
    def min_pending_update_id(self) -> int | None:
        if not self.pending_update_ids:
            return None
        return min(self.pending_update_ids)


class TelegramOffsetStore:
    def __init__(self, *, token: str, state_path: str | Path | None = None) -> None:
        self._token = str(token or "")
        self._bot_id = _extract_bot_id(self._token)
        self._token_fp = _token_fingerprint(self._token)
        self.path = self.resolve_path(token=self._token, state_path=state_path)
        self._safe_update_id: int | None = None
        self._highest_completed_update_id: int | None = None
        self._completed_update_ids: set[int] = set()
        self._pending_update_ids: set[int] = set()
        self._updated_at = ""

    @staticmethod
    def resolve_path(*, token: str, state_path: str | Path | None = None) -> Path:
        raw = str(state_path or "").strip()
        if raw:
            return Path(raw).expanduser()
        bot_id = _extract_bot_id(token)
        identity = bot_id or _token_fingerprint(token)
        return (
            Path.home() / ".clawlite" / "state" / "telegram" / f"offset-{identity}.json"
        )

    def reset_runtime_state(self) -> None:
        self._safe_update_id = None
        self._highest_completed_update_id = None
        self._completed_update_ids = set()
        self._pending_update_ids = set()
        self._updated_at = ""

    def snapshot(self) -> TelegramOffsetSnapshot:
        return TelegramOffsetSnapshot(
            path=str(self.path),
            bot_id=self._bot_id,
            token_fingerprint=self._token_fp,
            safe_update_id=self._safe_update_id,
            highest_completed_update_id=self._highest_completed_update_id,
            completed_update_ids=tuple(sorted(self._completed_update_ids)),
            pending_update_ids=tuple(sorted(self._pending_update_ids)),
            updated_at=self._updated_at,
        )

    @property
    def next_offset(self) -> int:
        return self.snapshot().next_offset

    @property
    def min_pending_update_id(self) -> int | None:
        return self.snapshot().min_pending_update_id

    def is_pending(self, update_id: int) -> bool:
        normalized = _coerce_update_id(update_id)
        return normalized in self._pending_update_ids

    def is_safe_committed(self, update_id: int) -> bool:
        normalized = _coerce_update_id(update_id)
        return self._safe_update_id is not None and normalized <= self._safe_update_id

    def refresh_from_disk(self) -> TelegramOffsetSnapshot:
        state = self._read_state()
        self._safe_update_id = state["safe_update_id"]
        self._highest_completed_update_id = state["highest_completed_update_id"]
        self._completed_update_ids = set(state["completed_update_ids"])
        self._pending_update_ids = set(state["pending_update_ids"])
        self._updated_at = state["updated_at"]
        return self.snapshot()

    def sync_next_offset(self, offset: int) -> TelegramOffsetSnapshot:
        normalized = _coerce_update_id(offset)
        if normalized <= 0:
            self._safe_update_id = None
            self._highest_completed_update_id = None
            self._completed_update_ids = set()
            self._pending_update_ids = set()
            self._updated_at = _now_iso()
            self._write_state()
            return self.snapshot()
        update_id = normalized - 1
        return self.force_commit(update_id)

    def begin(self, update_id: int) -> TelegramOffsetSnapshot:
        normalized = _coerce_update_id(update_id)
        if self.is_safe_committed(normalized):
            return self.snapshot()
        if normalized in self._pending_update_ids:
            return self.snapshot()
        self._pending_update_ids.add(normalized)
        self._updated_at = _now_iso()
        self._write_state()
        return self.snapshot()

    def _prune_sets_locked(self) -> bool:
        changed = False
        if self._safe_update_id is not None:
            safe = self._safe_update_id
            completed_kept = {
                item for item in self._completed_update_ids if item > safe
            }
            if completed_kept != self._completed_update_ids:
                self._completed_update_ids = completed_kept
                changed = True
            pending_kept = {item for item in self._pending_update_ids if item > safe}
            if pending_kept != self._pending_update_ids:
                self._pending_update_ids = pending_kept
                changed = True
            if (
                self._highest_completed_update_id is not None
                and self._highest_completed_update_id < safe
            ):
                self._highest_completed_update_id = safe
                changed = True
        return changed

    def _advance_safe_watermark_locked(self, *, allow_new_baseline: bool) -> bool:
        changed = False
        if self._safe_update_id is None:
            if allow_new_baseline and self._completed_update_ids:
                self._safe_update_id = max(self._completed_update_ids)
                changed = True
            else:
                return False

        while (
            self._safe_update_id is not None
            and (self._safe_update_id + 1) in self._completed_update_ids
        ):
            self._safe_update_id += 1
            changed = True

        return changed

    def mark_completed(
        self, update_id: int, *, tracked_pending: bool = True
    ) -> TelegramOffsetSnapshot:
        normalized = _coerce_update_id(update_id)
        changed = False

        if tracked_pending and normalized in self._pending_update_ids:
            self._pending_update_ids.discard(normalized)
            changed = True

        if self._safe_update_id is None or normalized > self._safe_update_id:
            if normalized not in self._completed_update_ids:
                self._completed_update_ids.add(normalized)
                changed = True
            next_highest = normalized
            if self._highest_completed_update_id is not None:
                next_highest = max(self._highest_completed_update_id, normalized)
            if next_highest != self._highest_completed_update_id:
                self._highest_completed_update_id = next_highest
                changed = True

        if self._advance_safe_watermark_locked(allow_new_baseline=tracked_pending):
            changed = True
        if self._prune_sets_locked():
            changed = True

        if changed:
            self._updated_at = _now_iso()
            self._write_state()
        return self.snapshot()

    def force_commit(self, update_id: int) -> TelegramOffsetSnapshot:
        normalized = _coerce_update_id(update_id)
        if self._safe_update_id is not None and normalized <= self._safe_update_id:
            return self.snapshot()
        self._safe_update_id = normalized
        self._highest_completed_update_id = normalized
        self._completed_update_ids.add(normalized)
        self._prune_sets_locked()
        self._updated_at = _now_iso()
        self._write_state()
        return self.snapshot()

    def _identity_matches(self, payload: dict[str, Any]) -> bool:
        payload_bot_id = str(payload.get("bot_id", "") or "").strip()
        if self._bot_id and payload_bot_id and payload_bot_id != self._bot_id:
            return False
        if not self._bot_id:
            payload_fp = str(payload.get("token_fingerprint", "") or "").strip()
            if payload_fp and payload_fp != self._token_fp:
                return False
        return True

    def _read_state(self) -> dict[str, Any]:
        path = self.path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return {
                "safe_update_id": None,
                "highest_completed_update_id": None,
                "completed_update_ids": [],
                "pending_update_ids": [],
                "updated_at": "",
            }

        if not path.exists():
            return {
                "safe_update_id": None,
                "highest_completed_update_id": None,
                "completed_update_ids": [],
                "pending_update_ids": [],
                "updated_at": "",
            }

        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, int):
            legacy_offset = max(0, int(raw))
            safe_update_id = legacy_offset - 1 if legacy_offset > 0 else None
            return {
                "safe_update_id": safe_update_id,
                "highest_completed_update_id": safe_update_id,
                "completed_update_ids": [],
                "pending_update_ids": [],
                "updated_at": "",
            }
        if not isinstance(raw, dict):
            raise ValueError("telegram offset payload must be an object or integer")

        if "safe_update_id" not in raw:
            legacy_offset = _coerce_update_id(raw.get("offset", 0))
            safe_update_id = legacy_offset - 1 if legacy_offset > 0 else None
            return {
                "safe_update_id": safe_update_id,
                "highest_completed_update_id": safe_update_id,
                "completed_update_ids": [],
                "pending_update_ids": [],
                "updated_at": str(raw.get("updated_at", "") or "").strip(),
            }

        if (
            int(raw.get("schema_version", STORE_SCHEMA_VERSION) or STORE_SCHEMA_VERSION)
            != STORE_SCHEMA_VERSION
        ):
            raise ValueError("telegram offset schema_version is unsupported")
        if not self._identity_matches(raw):
            return {
                "safe_update_id": None,
                "highest_completed_update_id": None,
                "completed_update_ids": [],
                "pending_update_ids": [],
                "updated_at": "",
            }

        safe_update_id = _coerce_optional_update_id(raw.get("safe_update_id"))
        highest_completed_update_id = _coerce_optional_update_id(
            raw.get("highest_completed_update_id")
        )
        completed_raw = raw.get("completed_update_ids", [])
        if not isinstance(completed_raw, list):
            raise ValueError("telegram completed_update_ids must be a list")
        completed_update_ids = sorted(
            {_coerce_update_id(item) for item in completed_raw}
        )
        pending_raw = raw.get("pending_update_ids", [])
        if not isinstance(pending_raw, list):
            raise ValueError("telegram pending_update_ids must be a list")
        pending_update_ids = sorted({_coerce_update_id(item) for item in pending_raw})
        if highest_completed_update_id is None:
            highest_completed_update_id = safe_update_id
        if safe_update_id is not None and highest_completed_update_id is not None:
            highest_completed_update_id = max(
                highest_completed_update_id, safe_update_id
            )
        pending_update_ids = [
            item
            for item in pending_update_ids
            if safe_update_id is None or item > safe_update_id
        ]
        completed_update_ids = [
            item
            for item in completed_update_ids
            if safe_update_id is None or item > safe_update_id
        ]
        return {
            "safe_update_id": safe_update_id,
            "highest_completed_update_id": highest_completed_update_id,
            "completed_update_ids": completed_update_ids,
            "pending_update_ids": pending_update_ids,
            "updated_at": str(raw.get("updated_at", "") or "").strip(),
        }

    def _write_state(self) -> None:
        path = self.path
        tmp_path = path.with_suffix(f"{path.suffix}.tmp.{secrets.token_hex(4)}")
        dir_fd: int | None = None
        payload = {
            "schema_version": STORE_SCHEMA_VERSION,
            "channel": "telegram",
            "bot_id": self._bot_id,
            "token_fingerprint": self._token_fp,
            "safe_update_id": self._safe_update_id,
            "highest_completed_update_id": self._highest_completed_update_id,
            "completed_update_ids": sorted(self._completed_update_ids),
            "pending_update_ids": sorted(self._pending_update_ids),
            "next_offset": self.snapshot().next_offset,
            "updated_at": self._updated_at or _now_iso(),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            encoded = (
                json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
            )
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
