from __future__ import annotations

import datetime as dt

from clawlite.gateway.tuning_decisions import plan_tuning_action


def test_plan_tuning_action_builds_executable_plan_for_medium_fact_drift() -> None:
    plan = plan_tuning_action(
        report={
            "drift": {"assessment": "degrading"},
            "score": 61,
            "reasoning_layers": {"weakest_layer": "factual"},
        },
        tuning_state={
            "degrading_streak": 1,
            "recent_actions": [],
        },
        now=dt.datetime(2026, 3, 17, 12, 0, tzinfo=dt.timezone.utc),
        parse_iso=lambda value: dt.datetime.fromisoformat(value) if value else None,
        degrading_streak_threshold=2,
        recent_actions_limit=20,
        cooldown_seconds=300,
        actions_per_hour_cap=20,
    )

    assert plan["severity"] == "medium"
    assert plan["weakest_layer"] == "fact"
    assert plan["action"] == "semantic_backfill"
    assert plan["playbook_id"] == "layer_fact_medium_v1"
    assert plan["action_status"] == "noop"
    assert plan["should_execute"] is True
    assert plan["action_metadata"] == {
        "severity": "medium",
        "playbook_id": "layer_fact_medium_v1",
        "weakest_layer": "fact",
        "action_variant": "layer_fact_medium_v1:semantic_backfill:v2",
    }


def test_plan_tuning_action_honors_cooldown_and_rate_limit() -> None:
    now = dt.datetime(2026, 3, 17, 12, 0, tzinfo=dt.timezone.utc)

    cooldown_plan = plan_tuning_action(
        report={
            "drift": {"assessment": "degrading"},
            "score": 30,
            "reasoning_layers": {"weakest_layer": "decision"},
        },
        tuning_state={
            "degrading_streak": 4,
            "last_action_at": "2026-03-17T11:58:00+00:00",
            "recent_actions": [],
        },
        now=now,
        parse_iso=lambda value: dt.datetime.fromisoformat(value) if value else None,
        degrading_streak_threshold=2,
        recent_actions_limit=20,
        cooldown_seconds=300,
        actions_per_hour_cap=20,
    )
    assert cooldown_plan["action_status"] == "cooldown_skipped"
    assert cooldown_plan["should_execute"] is False

    rate_limited_plan = plan_tuning_action(
        report={
            "drift": {"assessment": "degrading"},
            "score": 35,
            "reasoning_layers": {"weakest_layer": "decision"},
        },
        tuning_state={
            "degrading_streak": 4,
            "recent_actions": [
                {"status": "ok", "at": "2026-03-17T11:15:00+00:00"},
                {"status": "ok", "at": "2026-03-17T11:30:00+00:00"},
            ],
        },
        now=now,
        parse_iso=lambda value: dt.datetime.fromisoformat(value) if value else None,
        degrading_streak_threshold=2,
        recent_actions_limit=20,
        cooldown_seconds=0,
        actions_per_hour_cap=2,
    )
    assert rate_limited_plan["action_status"] == "rate_limited"
    assert rate_limited_plan["should_execute"] is False
