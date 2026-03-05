from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class CronSchedule:
    kind: str = "every"  # every | cron | at
    every_seconds: int = 300
    cron_expr: str = ""
    run_at_iso: str = ""
    timezone: str = "UTC"


@dataclass(slots=True)
class CronPayload:
    prompt: str
    channel: str = ""
    target: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CronJob:
    id: str
    name: str
    session_id: str
    schedule: CronSchedule
    payload: CronPayload
    enabled: bool = True
    next_run_iso: str = ""
    last_run_iso: str = ""
    last_status: str = "idle"
    last_error: str = ""
    consecutive_failures: int = 0
    run_count: int = 0
    lease_token: str = ""
    lease_owner: str = ""
    lease_expires_iso: str = ""
    lease_claimed_iso: str = ""
