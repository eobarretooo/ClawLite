from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from clawlite.runtime import SupervisorIncident
from clawlite.gateway.supervisor_recovery import (
    handle_supervisor_incident,
    recover_supervised_component,
)


def test_handle_supervisor_incident_respects_cooldown_and_notifies_once() -> None:
    async def _scenario() -> None:
        send_notice = AsyncMock(return_value="ok")
        recorded: list[tuple[tuple[object, ...], dict[str, object]]] = []
        notice_until: dict[str, float] = {}
        incident = SupervisorIncident(component="provider", reason="provider_circuit_open:failover", recoverable=False)

        await handle_supervisor_incident(
            incident=incident,
            notice_until=notice_until,
            cooldown_s=60.0,
            now_monotonic=lambda: 10.0,
            record_autonomy_event=lambda *args, **kwargs: recorded.append((args, kwargs)),
            send_autonomy_notice=send_notice,
        )
        await handle_supervisor_incident(
            incident=incident,
            notice_until=notice_until,
            cooldown_s=60.0,
            now_monotonic=lambda: 20.0,
            record_autonomy_event=lambda *args, **kwargs: recorded.append((args, kwargs)),
            send_autonomy_notice=send_notice,
        )

        assert send_notice.await_count == 1
        assert recorded[0][0][:3] == ("supervisor", "component_incident", "observed")

    asyncio.run(_scenario())


def test_recover_supervised_component_runs_selected_recoverer_and_reports_status() -> None:
    async def _scenario() -> None:
        send_notice = AsyncMock(return_value="ok")
        recorded: list[tuple[tuple[object, ...], dict[str, object]]] = []

        async def _recover() -> bool:
            return True

        recovered = await recover_supervised_component(
            component="heartbeat",
            reason="heartbeat_stopped",
            recoverers={"heartbeat": _recover},
            record_autonomy_event=lambda *args, **kwargs: recorded.append((args, kwargs)),
            send_autonomy_notice=send_notice,
        )

        assert recovered is True
        assert recorded[0][0][:3] == ("supervisor", "component_recovery", "recovered")
        assert send_notice.await_args.kwargs["metadata"]["component"] == "heartbeat"

    asyncio.run(_scenario())
