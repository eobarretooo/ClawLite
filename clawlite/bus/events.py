from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_correlation_id() -> str:
    return str(uuid.uuid4())


@dataclass(slots=True)
class InboundEvent:
    channel: str
    session_id: str
    user_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)
    envelope_version: int = 1
    correlation_id: str = field(default_factory=_new_correlation_id)


@dataclass(slots=True)
class OutboundEvent:
    channel: str
    session_id: str
    target: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    attempt: int = 1
    max_attempts: int = 1
    retryable: bool = True
    dead_lettered: bool = False
    dead_letter_reason: str = ""
    last_error: str = ""
    created_at: str = field(default_factory=_utc_now)
    envelope_version: int = 1
    correlation_id: str = field(default_factory=_new_correlation_id)
