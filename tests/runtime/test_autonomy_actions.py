from __future__ import annotations

import asyncio
import json
from pathlib import Path

from clawlite.runtime.autonomy_actions import AutonomyActionController


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


def test_allowlisted_action_executes() -> None:
    clock = _Clock()
    calls = {"count": 0}

    async def _scenario() -> None:
        controller = AutonomyActionController(now_monotonic=clock.monotonic)

        def _validate_provider(**_: object) -> dict[str, bool]:
            calls["count"] += 1
            return {"ok": True}

        status = await controller.process('{"action":"validate_provider","args":{}}', {"validate_provider": _validate_provider})
        assert calls["count"] == 1
        assert status["totals"]["executed"] == 1
        assert status["totals"]["succeeded"] == 1

    asyncio.run(_scenario())


def test_unknown_and_denylisted_actions_blocked() -> None:
    clock = _Clock()

    async def _scenario() -> None:
        controller = AutonomyActionController(now_monotonic=clock.monotonic)

        status_unknown = await controller.process('{"action":"do_anything","args":{}}', {})
        assert status_unknown["totals"]["blocked"] == 1
        assert status_unknown["totals"]["unknown_blocked"] == 1

        status_denylisted = await controller.process('{"action":"delete_all","args":{}}', {})
        assert status_denylisted["totals"]["blocked"] == 2
        assert status_denylisted["totals"]["unknown_blocked"] == 2

    asyncio.run(_scenario())


def test_cooldown_blocks_repeat() -> None:
    clock = _Clock()

    async def _scenario() -> None:
        controller = AutonomyActionController(action_cooldown_s=120.0, now_monotonic=clock.monotonic)

        def _validate_provider(**_: object) -> dict[str, bool]:
            return {"ok": True}

        await controller.process('{"action":"validate_provider","args":{}}', {"validate_provider": _validate_provider})
        blocked = await controller.process('{"action":"validate_provider","args":{}}', {"validate_provider": _validate_provider})
        assert blocked["totals"]["cooldown_blocked"] == 1
        assert blocked["totals"]["blocked"] == 1

    asyncio.run(_scenario())


def test_rate_limit_blocks_after_threshold() -> None:
    clock = _Clock()

    async def _scenario() -> None:
        controller = AutonomyActionController(
            action_cooldown_s=0.0,
            action_rate_limit_per_hour=2,
            now_monotonic=clock.monotonic,
        )

        def _validate_provider(**_: object) -> dict[str, bool]:
            return {"ok": True}

        await controller.process('{"action":"validate_provider","args":{}}', {"validate_provider": _validate_provider})
        clock.now += 1.0
        await controller.process('{"action":"validate_provider","args":{}}', {"validate_provider": _validate_provider})
        clock.now += 1.0
        blocked = await controller.process('{"action":"validate_provider","args":{}}', {"validate_provider": _validate_provider})

        assert blocked["totals"]["rate_limited"] == 1
        assert blocked["totals"]["blocked"] == 1

    asyncio.run(_scenario())


def test_dead_letter_replay_clamps_limit_and_forces_dry_run() -> None:
    clock = _Clock()
    captured: dict[str, object] = {}

    async def _scenario() -> None:
        controller = AutonomyActionController(max_replay_limit=50, now_monotonic=clock.monotonic)

        async def _replay(**kwargs: object) -> dict[str, bool]:
            captured.update(kwargs)
            return {"ok": True}

        await controller.process(
            '{"action":"dead_letter_replay_dry_run","args":{"limit":999,"channel":"telegram","dry_run":false}}',
            {"dead_letter_replay_dry_run": _replay},
        )

        assert captured["limit"] == 50
        assert captured["dry_run"] is True
        assert captured["channel"] == "telegram"

    asyncio.run(_scenario())


def test_invalid_json_increments_parse_errors() -> None:
    clock = _Clock()

    async def _scenario() -> None:
        controller = AutonomyActionController(now_monotonic=clock.monotonic)
        status = await controller.process("this is not valid action payload", {})
        assert status["totals"]["parse_errors"] == 1

    asyncio.run(_scenario())


def test_low_confidence_quality_gate_blocks_action() -> None:
    clock = _Clock()
    calls = {"count": 0}

    async def _scenario() -> None:
        controller = AutonomyActionController(min_action_confidence=0.8, now_monotonic=clock.monotonic)

        def _validate_provider(**_: object) -> dict[str, bool]:
            calls["count"] += 1
            return {"ok": True}

        status = await controller.process(
            '{"action":"validate_provider","confidence":0.2,"args":{}}',
            {"validate_provider": _validate_provider},
        )
        assert calls["count"] == 0
        assert status["totals"]["quality_blocked"] == 1
        assert status["totals"]["blocked"] == 1
        assert status["totals"]["executed"] == 0

    asyncio.run(_scenario())


def test_contextual_penalty_can_block_high_base_confidence() -> None:
    clock = _Clock()
    calls = {"count": 0}

    async def _scenario() -> None:
        controller = AutonomyActionController(min_action_confidence=0.8, now_monotonic=clock.monotonic)

        def _validate_provider(**_: object) -> dict[str, bool]:
            calls["count"] += 1
            return {"ok": True}

        status = await controller.process(
            '{"action":"validate_provider","confidence":0.95,"args":{}}',
            {"validate_provider": _validate_provider},
            runtime_snapshot={
                "queue": {"outbound_size": 100, "dead_letter_size": 0},
                "supervisor": {"incident_count": 0, "consecutive_error_count": 0},
                "channels": {"enabled_count": 2, "running_count": 1},
                "provider": {"circuit_open": False},
                "heartbeat": {"running": True},
                "cron": {"running": True},
            },
        )

        assert calls["count"] == 0
        assert status["totals"]["quality_blocked"] == 1
        assert status["totals"]["quality_penalty_applied"] == 1
        audit = status["last_run"]["audits"][0]
        assert audit["base_confidence"] == 0.95
        assert audit["context_penalty"] > 0.0
        assert audit["effective_confidence"] < 0.8

    asyncio.run(_scenario())


def test_contextual_penalty_mild_still_allows_action_and_tracks_penalty() -> None:
    clock = _Clock()
    calls = {"count": 0}

    async def _scenario() -> None:
        controller = AutonomyActionController(min_action_confidence=0.8, now_monotonic=clock.monotonic)

        def _validate_provider(**_: object) -> dict[str, bool]:
            calls["count"] += 1
            return {"ok": True}

        status = await controller.process(
            '{"action":"validate_provider","confidence":0.95,"args":{}}',
            {"validate_provider": _validate_provider},
            runtime_snapshot={
                "queue": {"outbound_size": 25, "dead_letter_size": 0},
                "supervisor": {"incident_count": 0, "consecutive_error_count": 0},
                "channels": {"enabled_count": 2, "running_count": 2},
                "provider": {"circuit_open": False},
                "heartbeat": {"running": True},
                "cron": {"running": True},
            },
        )

        assert calls["count"] == 1
        assert status["totals"]["executed"] == 1
        assert status["totals"]["quality_penalty_applied"] == 1
        audit = status["last_run"]["audits"][0]
        assert audit["base_confidence"] == 0.95
        assert audit["context_penalty"] > 0.0
        assert audit["effective_confidence"] >= 0.8

    asyncio.run(_scenario())


def test_degraded_snapshot_blocks_non_diagnostics_and_allows_diagnostics() -> None:
    clock = _Clock()
    calls = {"diag": 0, "provider": 0}

    async def _scenario() -> None:
        controller = AutonomyActionController(
            max_actions_per_run=2,
            degraded_backlog_threshold=10,
            degraded_supervisor_error_threshold=3,
            now_monotonic=clock.monotonic,
        )

        def _diagnostics_snapshot(**_: object) -> dict[str, bool]:
            calls["diag"] += 1
            return {"ok": True}

        def _validate_provider(**_: object) -> dict[str, bool]:
            calls["provider"] += 1
            return {"ok": True}

        payload = json.dumps(
            {
                "actions": [
                    {"action": "validate_provider", "args": {}},
                    {"action": "diagnostics_snapshot", "args": {}},
                ]
            }
        )
        status = await controller.process(
            payload,
            {
                "validate_provider": _validate_provider,
                "diagnostics_snapshot": _diagnostics_snapshot,
            },
            runtime_snapshot={
                "queue": {"outbound_size": 20, "dead_letter_size": 1},
                "supervisor": {"incident_count": 0, "consecutive_error_count": 0},
            },
        )

        assert calls["provider"] == 0
        assert calls["diag"] == 1
        assert status["totals"]["degraded_blocked"] == 1
        assert status["totals"]["executed"] == 1

    asyncio.run(_scenario())


def test_audit_export_reads_persisted_entries(tmp_path: Path) -> None:
    clock = _Clock()

    async def _scenario() -> None:
        audit_path = tmp_path / "autonomy-actions-audit.jsonl"
        controller = AutonomyActionController(audit_path=str(audit_path), now_monotonic=clock.monotonic)

        def _validate_provider(**_: object) -> dict[str, bool]:
            return {"ok": True}

        await controller.process('{"action":"validate_provider","args":{}}', {"validate_provider": _validate_provider})

        exported = controller.export_audit(limit=10)
        assert exported["ok"] is True
        assert exported["path"] == str(audit_path)
        assert exported["count"] >= 1
        assert any(str(row.get("action", "")) == "validate_provider" for row in exported["entries"])

    asyncio.run(_scenario())
