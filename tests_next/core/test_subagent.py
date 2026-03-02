from __future__ import annotations

import asyncio

from clawlite.core.subagent import SubagentManager


async def _runner(_session_id: str, task: str) -> str:
    return f"done:{task}"


def test_subagent_manager_spawn_and_list() -> None:
    async def _scenario() -> None:
        mgr = SubagentManager()
        run = await mgr.spawn(session_id="s1", task="t1", runner=_runner)
        await asyncio.sleep(0)
        runs = mgr.list_runs(session_id="s1")
        assert runs
        assert runs[0].run_id == run.run_id

    asyncio.run(_scenario())
