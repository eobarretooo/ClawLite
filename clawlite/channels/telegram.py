from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from clawlite.channels.base import BaseChannel, cancel_task

MAX_MESSAGE_LEN = 4000


def split_message(text: str, max_len: int = MAX_MESSAGE_LEN) -> list[str]:
    content = text or ""
    if len(content) <= max_len:
        return [content]
    parts: list[str] = []
    current = ""
    for line in content.splitlines(True):
        if len(current) + len(line) <= max_len:
            current += line
            continue
        if current:
            parts.append(current)
        if len(line) <= max_len:
            current = line
            continue
        start = 0
        while start < len(line):
            end = start + max_len
            parts.append(line[start:end])
            start = end
        current = ""
    if current:
        parts.append(current)
    return parts


class TelegramChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="telegram", config=config, on_message=on_message)
        token = str(config.get("token", "")).strip()
        if not token:
            raise ValueError("telegram token is required")
        self.token = token
        self.bot: Any | None = None
        self.poll_interval_s = float(config.get("poll_interval_s", 1.0) or 1.0)
        self.poll_timeout_s = int(config.get("poll_timeout_s", 20) or 20)
        self.reconnect_initial_s = float(config.get("reconnect_initial_s", 2.0) or 2.0)
        self.reconnect_max_s = float(config.get("reconnect_max_s", 30.0) or 30.0)
        self._task: asyncio.Task[Any] | None = None
        self._offset = self._load_offset()

    def _offset_path(self) -> Path:
        key = hashlib.sha256(self.token.encode("utf-8")).hexdigest()[:16]
        path = Path.home() / ".clawlite" / "state" / "telegram"
        path.mkdir(parents=True, exist_ok=True)
        return path / f"offset-{key}.json"

    def _load_offset(self) -> int:
        path = self._offset_path()
        if not path.exists():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0
        return int(data.get("offset", 0) or 0)

    def _save_offset(self) -> None:
        path = self._offset_path()
        path.write_text(json.dumps({"offset": self._offset}), encoding="utf-8")

    async def _poll_loop(self) -> None:
        backoff = self.reconnect_initial_s
        while self._running:
            try:
                if self.bot is None:
                    from telegram import Bot  # lazy import for environments without dependency during tests

                    self.bot = Bot(token=self.token)
                updates = await self.bot.get_updates(
                    offset=self._offset,
                    timeout=self.poll_timeout_s,
                    allowed_updates=["message", "edited_message"],
                )
                backoff = self.reconnect_initial_s
                for item in updates:
                    self._offset = max(self._offset, int(item.update_id) + 1)
                    self._save_offset()
                    message = item.effective_message
                    if message is None:
                        continue
                    text = (message.text or message.caption or "").strip()
                    if not text:
                        continue
                    chat_id = str(message.chat_id)
                    user_id = str(message.from_user.id) if message.from_user else chat_id
                    session_id = f"telegram:{chat_id}"
                    await self.emit(
                        session_id=session_id,
                        user_id=user_id,
                        text=text,
                        metadata={"chat_id": chat_id},
                    )
                await asyncio.sleep(self.poll_interval_s)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                self._last_error = str(exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.reconnect_max_s)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        await cancel_task(self._task)
        self._task = None

    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        chat_id = str(target).strip()
        if not chat_id:
            raise ValueError("telegram target(chat_id) is required")
        if self.bot is None:
            from telegram import Bot

            self.bot = Bot(token=self.token)
        chunks = split_message(text)
        for chunk in chunks:
            await self.bot.send_message(chat_id=chat_id, text=chunk)
        return f"telegram:sent:{len(chunks)}"
