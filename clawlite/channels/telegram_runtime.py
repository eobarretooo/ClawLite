from __future__ import annotations

import asyncio
import hashlib
import json
from collections import deque
from pathlib import Path
from typing import Any

from clawlite.config.settings import CONFIG_DIR

try:
    from telegram import Bot

    HAS_TELEGRAM = True
except Exception:  # pragma: no cover - optional dependency at runtime
    HAS_TELEGRAM = False
    Bot = Any  # type: ignore[assignment]


TELEGRAM_TEXT_LIMIT = 4000
TELEGRAM_OFFSET_STORE_VERSION = 1


def _normalize_account_id(raw: str) -> str:
    value = (raw or "").strip().lower()
    if not value:
        return "default"
    sanitized = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_", "."}:
            sanitized.append(ch)
        else:
            sanitized.append("_")
    return "".join(sanitized) or "default"


def extract_bot_id_from_token(token: str) -> str:
    raw = (token or "").strip()
    if not raw:
        return ""
    return raw.split(":", 1)[0].strip()


def chunk_telegram_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    normalized = str(text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return []

    try:
        max_len = int(limit)
    except (TypeError, ValueError):
        max_len = TELEGRAM_TEXT_LIMIT
    max_len = max(1, max_len)

    chunks: list[str] = []
    remaining = normalized

    while len(remaining) > max_len:
        window = remaining[:max_len]
        split_at = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
        if split_at < max_len // 2:
            split_at = max_len
        piece = remaining[:split_at].rstrip()
        if not piece:
            split_at = max_len
            piece = remaining[:split_at]
        chunks.append(piece)
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)
    return chunks


class TelegramUpdateDedupe:
    def __init__(self, max_entries: int = 2048) -> None:
        self._max_entries = max(100, int(max_entries))
        self._queue: deque[int] = deque()
        self._known: set[int] = set()

    def seen(self, update_id: int) -> bool:
        return int(update_id) in self._known

    def add(self, update_id: int) -> None:
        value = int(update_id)
        if value in self._known:
            return
        self._queue.append(value)
        self._known.add(value)
        while len(self._queue) > self._max_entries:
            old = self._queue.popleft()
            self._known.discard(old)


class TelegramUpdateOffsetStore:
    def __init__(
        self,
        *,
        token: str,
        account_id: str = "",
        root_dir: Path | None = None,
    ) -> None:
        self._bot_id = extract_bot_id_from_token(token)
        account_key = account_id or self._bot_id or hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        base = Path(root_dir) if root_dir else Path(CONFIG_DIR) / "state" / "telegram"
        self.path = base / f"update-offset-{_normalize_account_id(account_key)}.json"

    def read(self) -> int | None:
        try:
            raw = self.path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        stored_bot = str(payload.get("bot_id", "")).strip()
        if self._bot_id and stored_bot and stored_bot != self._bot_id:
            return None
        value = payload.get("last_update_id")
        if isinstance(value, int):
            return value
        return None

    def write(self, update_id: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": TELEGRAM_OFFSET_STORE_VERSION,
            "last_update_id": int(update_id),
            "bot_id": self._bot_id or None,
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)


def normalize_telegram_chat_id(chat_id: str | int) -> str | int:
    raw = str(chat_id).strip()
    if raw and raw.lstrip("-").isdigit():
        try:
            return int(raw)
        except ValueError:
            return raw
    return raw


async def send_telegram_chunks_with_bot(
    bot: Bot,
    *,
    chat_id: str | int,
    text: str,
    chunk_limit: int = TELEGRAM_TEXT_LIMIT,
    message_thread_id: int | None = None,
    disable_notification: bool | None = None,
    send_timeout_s: float = 15.0,
) -> int:
    sent = 0
    target_chat_id = normalize_telegram_chat_id(chat_id)
    for chunk in chunk_telegram_text(text, chunk_limit):
        await asyncio.wait_for(
            bot.send_message(
                chat_id=target_chat_id,
                text=chunk,
                message_thread_id=message_thread_id,
                disable_notification=disable_notification,
            ),
            timeout=max(1.0, float(send_timeout_s)),
        )
        sent += 1
    return sent


async def send_telegram_text(
    *,
    token: str,
    chat_id: str | int,
    text: str,
    chunk_limit: int = TELEGRAM_TEXT_LIMIT,
    message_thread_id: int | None = None,
    disable_notification: bool | None = None,
    send_timeout_s: float = 15.0,
) -> int:
    if not HAS_TELEGRAM:
        raise RuntimeError("python-telegram-bot não instalado")
    bot = Bot(token=str(token).strip())
    return await send_telegram_chunks_with_bot(
        bot,
        chat_id=chat_id,
        text=text,
        chunk_limit=chunk_limit,
        message_thread_id=message_thread_id,
        disable_notification=disable_notification,
        send_timeout_s=send_timeout_s,
    )


def send_telegram_text_sync(
    *,
    token: str,
    chat_id: str | int,
    text: str,
    chunk_limit: int = TELEGRAM_TEXT_LIMIT,
    message_thread_id: int | None = None,
    disable_notification: bool | None = None,
    send_timeout_s: float = 15.0,
) -> int:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            send_telegram_text(
                token=token,
                chat_id=chat_id,
                text=text,
                chunk_limit=chunk_limit,
                message_thread_id=message_thread_id,
                disable_notification=disable_notification,
                send_timeout_s=send_timeout_s,
            )
        )
    raise RuntimeError("send_telegram_text_sync não pode ser chamado em loop asyncio ativo")
