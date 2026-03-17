from __future__ import annotations

import datetime as dt

from clawlite.gateway.tuning_runtime import (
    build_tuning_action_entry,
    build_tuning_patch,
    count_recent_tuning_actions,
    record_tuning_runner_action,
)


def test_count_recent_tuning_actions_ignores_old_and_suppressed_statuses() -> None:
    now = dt.datetime(2026, 3, 17, 12, 0, tzinfo=dt.timezone.utc)
    count = count_recent_tuning_actions(
        [
            {"status": "ok", "at": "2026-03-17T11:30:00+00:00"},
            {"status": "cooldown_skipped", "at": "2026-03-17T11:40:00+00:00"},
            {"status": "ok", "at": "2026-03-17T09:00:00+00:00"},
        ],
        now=now,
        parse_iso=lambda value: dt.datetime.fromisoformat(value),
        ignored_statuses=frozenset({"cooldown_skipped", "rate_limited", "noop"}),
    )

    assert count == 1


def test_record_tuning_runner_action_tracks_layer_playbook_and_status_maps() -> None:
    state: dict[str, object] = {}
    record_tuning_runner_action(
        state,
        weakest_layer="decision",
        action="notify_operator",
        playbook_id="layer_decision_low_v1",
        action_status="ok",
        action_metadata={"template_id": "notify.decision.low.v1"},
        resolve_tuning_layer=lambda value: str(value or "unknown"),
    )

    assert state["actions_by_layer"] == {"decision": 1}
    assert state["actions_by_playbook"] == {"layer_decision_low_v1": 1}
    assert state["actions_by_action"] == {"notify_operator": 1}
    assert state["action_status_by_layer"] == {"decision": {"ok": 1}}
    assert state["last_action_metadata"] == {"template_id": "notify.decision.low.v1"}


def test_build_tuning_action_entry_and_patch_include_recent_actions() -> None:
    entry = build_tuning_action_entry(
        action="semantic_backfill",
        status="ok",
        reason="quality_drift_medium",
        at="2026-03-17T12:00:00+00:00",
        metadata={"backfill_limit": 24},
    )
    patch = build_tuning_patch(
        degrading_streak=2,
        now_iso="2026-03-17T12:00:00+00:00",
        interval_seconds=60,
        action_entry=entry,
    )

    assert entry is not None
    assert patch["degrading_streak"] == 2
    assert patch["last_action"] == "semantic_backfill"
    assert patch["recent_actions"] == [entry]
    assert patch["next_run_at"] == "2026-03-17T12:01:00+00:00"
