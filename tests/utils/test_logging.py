from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from loguru import logger

from clawlite.channels.telegram import TelegramChannel
from clawlite.scheduler.cron import CronService
from clawlite.utils import logging as logging_utils


def _reset_logging_state() -> None:
    logger.remove()
    logging_utils._LOGGING_CONFIGURED = False


def test_plain_logger_uses_default_extra_fields(monkeypatch) -> None:
    _reset_logging_state()
    monkeypatch.setenv("CLAWLITE_LOG_STDERR", "0")
    logging_utils.setup_logging(level="INFO")

    rows: list[str] = []
    sink_id = logger.add(rows.append, format=logging_utils._text_format)
    logger.info("plain log line")
    logger.remove(sink_id)

    assert rows
    line = rows[0].strip()
    assert line.startswith("[")
    assert "] ┃ [" in line
    assert line.endswith(": plain log line")


def test_cron_and_telegram_plain_logger_calls_work(monkeypatch, tmp_path: Path) -> None:
    _reset_logging_state()
    monkeypatch.setenv("CLAWLITE_LOG_STDERR", "0")
    logging_utils.setup_logging(level="INFO")

    rows: list[str] = []
    sink_id = logger.add(rows.append, format=logging_utils._text_format)

    async def _run() -> None:
        service = CronService(tmp_path / "cron.json")

        async def _on_job(_job):
            return "ok"

        await service.start(_on_job)
        await service.stop()

        channel = TelegramChannel(config={"token": "x:token"})
        await channel.start()
        await channel.stop()

    asyncio.run(_run())
    logger.remove(sink_id)

    joined = "\n".join(rows)
    assert " ┃ [" in joined
    assert "cron service started" in joined
    assert "telegram channel starting" in joined


def test_logger_patcher_backfills_missing_extra_fields(monkeypatch) -> None:
    _reset_logging_state()
    monkeypatch.setenv("CLAWLITE_LOG_STDERR", "0")
    logging_utils.setup_logging(level="INFO")

    rows: list[str] = []
    sink_id = logger.add(rows.append, format=logging_utils._text_format)
    logger.patch(lambda record: record["extra"].clear()).info("record without extra")
    logger.remove(sink_id)

    assert rows
    assert " ┃ [" in rows[0]


def test_text_formatter_applies_level_and_event_colors() -> None:
    formatter = logging_utils._make_text_formatter(enable_color=True)
    record = {
        "time": datetime(2026, 1, 1, 10, 11, 12),
        "level": type("Level", (), {"name": "INFO"})(),
        "name": "clawlite.core.engine",
        "message": "agent turn completed",
        "extra": {"event": "agent.loop", "session": "s", "channel": "c", "tool": "-", "run": "-"},
        "exception": None,
    }

    line = formatter(record)
    assert "\x1b[36m┃\x1b[0m" in line
    assert "[Agent.Loop]" in line


def test_text_formatter_handles_braces_in_message_and_exception(monkeypatch) -> None:
    _reset_logging_state()
    monkeypatch.setenv("CLAWLITE_LOG_STDERR", "0")
    logging_utils.setup_logging(level="INFO")

    rows: list[str] = []
    sink_id = logger.add(rows.append, format=logging_utils._text_format)
    logger.info("provider detail payload={\"error\":\"quota\"} trailing={")
    try:
        raise RuntimeError("quota exhausted {insufficient_quota")
    except RuntimeError:
        logger.exception("provider exception with json={\"code\":\"insufficient_quota\"}")
    logger.remove(sink_id)

    joined = "\n".join(rows)
    assert "payload={\"error\":\"quota\"} trailing={" in joined
    assert "quota exhausted {insufficient_quota" in joined
