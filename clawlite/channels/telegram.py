from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from clawlite.channels.base import BaseChannel, cancel_task
from clawlite.config.schema import ChannelConfig
from clawlite.utils.logging import setup_logging

MAX_MESSAGE_LEN = 4000

setup_logging()


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


def markdown_to_telegram_html(text: str) -> str:
    if not text:
        return ""

    code_blocks: list[str] = []

    def save_code_block(match: re.Match[str]) -> str:
        code_blocks.append(match.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r"```[\w]*\n?([\s\S]*?)```", save_code_block, text)

    inline_codes: list[str] = []

    def save_inline_code(match: re.Match[str]) -> str:
        inline_codes.append(match.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", save_inline_code, text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"^>\s*(.*)$", r"\1", text, flags=re.MULTILINE)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)

    for idx, code in enumerate(inline_codes):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{idx}\x00", f"<code>{escaped}</code>")

    for idx, code in enumerate(code_blocks):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{idx}\x00", f"<pre><code>{escaped}</code></pre>")

    return text


def parse_command(text: str) -> tuple[str, str]:
    stripped = str(text or "").strip()
    if not stripped.startswith("/"):
        return "", ""
    head, _, tail = stripped.partition(" ")
    cmd = head[1:]
    if "@" in cmd:
        cmd = cmd.split("@", 1)[0]
    return cmd.lower(), tail.strip()


class TelegramChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="telegram", config=config, on_message=on_message)
        token = str(config.get("token", "")).strip()
        if not token:
            raise ValueError("telegram token is required")
        self.token = token
        self.allow_from = ChannelConfig.from_dict(config).allow_from
        self.bot: Any | None = None
        self.poll_interval_s = float(config.get("poll_interval_s", 1.0) or 1.0)
        self.poll_timeout_s = int(config.get("poll_timeout_s", 20) or 20)
        self.reconnect_initial_s = float(config.get("reconnect_initial_s", 2.0) or 2.0)
        self.reconnect_max_s = float(config.get("reconnect_max_s", 30.0) or 30.0)
        self.drop_pending_updates = bool(config.get("drop_pending_updates", config.get("dropPendingUpdates", True)))
        self.handle_commands = bool(config.get("handle_commands", config.get("handleCommands", True)))
        self._task: asyncio.Task[Any] | None = None
        self._offset = self._load_offset()
        self._connected = False
        self._startup_drop_done = False
        self._message_signatures: dict[tuple[str, int], str] = {}
        self._signature_limit = 4096

    async def _drop_pending_updates(self) -> None:
        if self.bot is None:
            return
        dropped = 0
        try:
            while True:
                updates = await self.bot.get_updates(
                    offset=self._offset,
                    timeout=0,
                    allowed_updates=["message", "edited_message"],
                )
                if not updates:
                    break
                dropped += len(updates)
                self._offset = max(self._offset, int(updates[-1].update_id) + 1)
            if dropped:
                self._save_offset()
            logger.info("telegram startup pending updates dropped={} offset={}", dropped, self._offset)
        except Exception as exc:  # pragma: no cover
            logger.warning("telegram startup drop pending updates failed error={}", exc)

    def _is_allowed_sender(self, user_id: str, username: str = "") -> bool:
        if not self.allow_from:
            return True
        allowed = {item.strip() for item in self.allow_from if item.strip()}
        candidates = {str(user_id).strip()}
        if username:
            uname = username.strip()
            if uname:
                candidates.add(uname)
                candidates.add(f"@{uname}")
        return any(candidate in allowed for candidate in candidates)

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
                    logger.info("telegram bot initialized poll_timeout_s={}", self.poll_timeout_s)
                    if self.drop_pending_updates and not self._startup_drop_done:
                        await self._drop_pending_updates()
                        self._startup_drop_done = True
                updates = await self.bot.get_updates(
                    offset=self._offset,
                    timeout=self.poll_timeout_s,
                    allowed_updates=["message", "edited_message"],
                )
                if not self._connected:
                    self._connected = True
                    logger.info("telegram connected polling=true")
                backoff = self.reconnect_initial_s
                for item in updates:
                    self._offset = max(self._offset, int(item.update_id) + 1)
                    self._save_offset()
                    await self._handle_update(item)
                await asyncio.sleep(self.poll_interval_s)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                self._last_error = str(exc)
                self._connected = False
                self.bot = None
                logger.error("telegram polling error error={} backoff_s={}", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self.reconnect_max_s)

    async def _handle_update(self, item: Any) -> None:
        message = getattr(item, "message", None)
        is_edit = False
        if message is None:
            message = getattr(item, "edited_message", None)
            is_edit = message is not None
        if message is None:
            message = getattr(item, "effective_message", None)
            is_edit = bool(getattr(item, "edited_message", None))
        if message is None:
            return

        media_info = self._extract_media_info(message)
        text = (getattr(message, "text", "") or getattr(message, "caption", "") or "").strip()
        if not text and media_info["has_media"]:
            text = self._build_media_placeholder(media_info)
        if not text:
            return

        chat_id = str(getattr(message, "chat_id", "") or "")
        if not chat_id:
            return
        user = getattr(message, "from_user", None)
        user_id = str(getattr(user, "id", "") or chat_id)
        username = str(getattr(user, "username", "") or "").strip()
        if not self._is_allowed_sender(user_id, username):
            logger.debug("telegram inbound blocked user={} chat={}", user_id, chat_id)
            return

        message_id = int(getattr(message, "message_id", 0) or 0)
        signature = hashlib.sha256(text.encode("utf-8")).hexdigest()
        msg_key = (chat_id, message_id)
        previous_signature = self._message_signatures.get(msg_key)
        if previous_signature == signature:
            logger.debug("telegram inbound duplicate skipped chat={} message_id={} is_edit={}", chat_id, message_id, is_edit)
            return
        self._message_signatures[msg_key] = signature
        if len(self._message_signatures) > self._signature_limit:
            oldest_key = next(iter(self._message_signatures))
            self._message_signatures.pop(oldest_key, None)

        command, command_args = parse_command(text)
        is_command = bool(command)
        if is_command and self.handle_commands:
            if command == "start":
                await self._send_start_message(chat_id=chat_id)
                return
            if command == "help":
                await self._send_help_message(chat_id=chat_id)
                return

        session_id = f"telegram:{chat_id}"
        metadata = self._build_metadata(
            item=item,
            message=message,
            text=text,
            is_edit=is_edit,
            command=command,
            command_args=command_args,
            media_info=media_info,
        )
        logger.info(
            "telegram inbound received chat={} user={} chars={} edit={} command={}",
            chat_id,
            user_id,
            len(text),
            is_edit,
            command or "",
        )
        await self.emit(session_id=session_id, user_id=user_id, text=text, metadata=metadata)

    def _build_metadata(
        self,
        *,
        item: Any,
        message: Any,
        text: str,
        is_edit: bool,
        command: str,
        command_args: str,
        media_info: dict[str, Any],
    ) -> dict[str, Any]:
        user = getattr(message, "from_user", None)
        chat = getattr(message, "chat", None)
        reply = getattr(message, "reply_to_message", None)
        reply_user = getattr(reply, "from_user", None) if reply else None

        metadata: dict[str, Any] = {
            "channel": "telegram",
            "chat_id": str(getattr(message, "chat_id", "") or ""),
            "chat_type": str(getattr(chat, "type", "") or ""),
            "is_group": str(getattr(chat, "type", "") or "") != "private",
            "message_id": int(getattr(message, "message_id", 0) or 0),
            "update_id": int(getattr(item, "update_id", 0) or 0),
            "is_edit": is_edit,
            "is_command": bool(command),
            "text": text,
            "user_id": int(getattr(user, "id", 0) or 0),
            "username": str(getattr(user, "username", "") or ""),
            "first_name": str(getattr(user, "first_name", "") or ""),
            "language_code": str(getattr(user, "language_code", "") or ""),
            "date": str(getattr(message, "date", "") or ""),
            "edit_date": str(getattr(message, "edit_date", "") or ""),
            "media_present": bool(media_info.get("has_media", False)),
            "media_types": list(media_info.get("types", [])),
            "media_counts": dict(media_info.get("counts", {})),
            "media_total_count": int(media_info.get("total_count", 0) or 0),
        }
        if command:
            metadata["command"] = command
            metadata["command_args"] = command_args
        if reply is not None:
            metadata["reply_to_message_id"] = int(getattr(reply, "message_id", 0) or 0)
            metadata["reply_to_text"] = (
                str(getattr(reply, "text", "") or getattr(reply, "caption", "") or "")[:500]
            )
            metadata["reply_to_user_id"] = int(getattr(reply_user, "id", 0) or 0)
            metadata["reply_to_username"] = str(getattr(reply_user, "username", "") or "")
        return metadata

    def _extract_media_info(self, message: Any) -> dict[str, Any]:
        counts: dict[str, int] = {}

        photos = getattr(message, "photo", None)
        if photos:
            counts["photo"] = len(photos)

        for media_type in ("voice", "audio", "document"):
            if getattr(message, media_type, None) is not None:
                counts[media_type] = counts.get(media_type, 0) + 1

        media_types = sorted(counts.keys())
        total_count = sum(counts.values())
        return {
            "has_media": bool(counts),
            "types": media_types,
            "counts": counts,
            "total_count": total_count,
        }

    def _build_media_placeholder(self, media_info: dict[str, Any]) -> str:
        if not media_info.get("has_media"):
            return ""
        counts = dict(media_info.get("counts", {}))
        details = ", ".join(
            f"{media_type}({counts[media_type]})" if counts[media_type] > 1 else media_type
            for media_type in sorted(counts.keys())
        )
        if not details:
            return "[telegram media message]"
        return f"[telegram media message: {details}]"

    async def _send_start_message(self, *, chat_id: str) -> None:
        if self.bot is None:
            return
        await self.bot.send_message(
            chat_id=chat_id,
            text=(
                "Hi! I am ClawLite.\\n\\n"
                "Send a message to start.\\n"
                "Commands: /help, /stop"
            ),
        )

    async def _send_help_message(self, *, chat_id: str) -> None:
        if self.bot is None:
            return
        await self.bot.send_message(
            chat_id=chat_id,
            text=(
                "ClawLite commands:\\n"
                "/help - Show this help\\n"
                "/stop - Stop active task"
            ),
        )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        logger.info("telegram channel starting")
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        await cancel_task(self._task)
        self._task = None
        self._connected = False
        logger.info("telegram channel stopped")

    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        chat_id = str(target).strip()
        if not chat_id:
            raise ValueError("telegram target(chat_id) is required")
        metadata = dict(metadata or {})
        if self.bot is None:
            from telegram import Bot

            self.bot = Bot(token=self.token)
        chunks = split_message(text)
        max_attempts = 3
        initial_backoff_s = 1.0
        reply_to_message_id = metadata.get("reply_to_message_id", metadata.get("message_id"))
        try:
            reply_to_message_id = int(reply_to_message_id) if reply_to_message_id is not None else None
        except (TypeError, ValueError):
            reply_to_message_id = None

        for idx, chunk in enumerate(chunks, start=1):
            backoff_s = initial_backoff_s
            for attempt in range(1, max_attempts + 1):
                try:
                    html = markdown_to_telegram_html(chunk)
                    try:
                        await self.bot.send_message(
                            chat_id=chat_id,
                            text=html,
                            parse_mode="HTML",
                            reply_to_message_id=reply_to_message_id,
                        )
                    except Exception:
                        await self.bot.send_message(
                            chat_id=chat_id,
                            text=chunk,
                            reply_to_message_id=reply_to_message_id,
                        )
                    break
                except Exception as exc:
                    logger.error(
                        "telegram outbound failed chat={} chunk={}/{} attempt={}/{} error={}",
                        chat_id,
                        idx,
                        len(chunks),
                        attempt,
                        max_attempts,
                        exc,
                    )
                    if attempt >= max_attempts:
                        raise
                    await asyncio.sleep(backoff_s)
                    backoff_s *= 2
        logger.info("telegram outbound sent chat={} chunks={} chars={}", chat_id, len(chunks), len(text))
        return f"telegram:sent:{len(chunks)}"
