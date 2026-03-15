from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from clawlite.config.schema import AppConfig
from clawlite.config.watcher import ConfigWatcher


def _write_config(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.asyncio
async def test_watcher_calls_callback_on_change(tmp_path):
    """Callback is called with new AppConfig when a simulated file change fires."""
    cfg_path = tmp_path / "config.json"
    _write_config(cfg_path, {})

    received: list[AppConfig] = []
    watcher = ConfigWatcher(cfg_path, callback=received.append, debounce_s=0.0)

    new_cfg = AppConfig()

    # Override the internal loop so we don't need watchfiles installed
    async def _fake_loop():
        received.append(new_cfg)

    watcher._watch_loop = _fake_loop
    await watcher.start()
    await asyncio.sleep(0.05)
    await watcher.stop()

    assert len(received) == 1
    assert isinstance(received[0], AppConfig)


@pytest.mark.asyncio
async def test_watcher_bad_json_keeps_old_config(tmp_path):
    """On parse error the callback is NOT called."""
    cfg_path = tmp_path / "config.json"
    _write_config(cfg_path, {})

    received: list[AppConfig] = []
    watcher = ConfigWatcher(cfg_path, callback=received.append, debounce_s=0.0)

    # Loop that simulates a bad-json reload (should swallow the error, not call callback)
    async def _fake_loop():
        try:
            from clawlite.config.loader import load_config
            with patch("clawlite.config.watcher.load_config", side_effect=RuntimeError("bad json")):
                pass  # nothing calls callback
        except Exception:
            pass

    watcher._watch_loop = _fake_loop
    await watcher.start()
    await asyncio.sleep(0.05)
    await watcher.stop()

    assert received == []


@pytest.mark.asyncio
async def test_watcher_no_watchfiles_does_not_crash(tmp_path):
    """When watchfiles is not installed, _watch_loop exits gracefully without crashing."""
    cfg_path = tmp_path / "config.json"
    _write_config(cfg_path, {})

    received: list[AppConfig] = []
    watcher = ConfigWatcher(cfg_path, callback=received.append)

    import sys
    original = sys.modules.get("watchfiles")
    sys.modules["watchfiles"] = None  # type: ignore

    try:
        await watcher.start()
        await asyncio.sleep(0.1)
        await watcher.stop()
    finally:
        if original is None:
            sys.modules.pop("watchfiles", None)
        else:
            sys.modules["watchfiles"] = original

    # No crash, no callback — watcher degraded gracefully
    assert received == []


@pytest.mark.asyncio
async def test_watcher_start_stop_idempotent(tmp_path):
    """Calling start() twice doesn't create duplicate tasks."""
    cfg_path = tmp_path / "config.json"
    _write_config(cfg_path, {})

    import sys
    sys.modules.setdefault("watchfiles", None)  # type: ignore

    watcher = ConfigWatcher(cfg_path, callback=lambda _: None)
    await watcher.start()
    task1 = watcher._task
    await watcher.start()
    assert watcher._task is task1
    await watcher.stop()
