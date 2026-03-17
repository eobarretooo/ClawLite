from __future__ import annotations

import asyncio
from typing import Any

from clawlite.channels.base import BaseChannel, cancel_task


class IRCChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="irc", config=config, on_message=on_message)
        self.host = str(config.get("host", "irc.libera.chat") or "irc.libera.chat").strip()
        self.port = max(1, int(config.get("port", 6697) or 6697))
        self.nick = str(config.get("nick", "clawlite") or "clawlite").strip() or "clawlite"
        self.username = str(config.get("username", self.nick) or self.nick).strip() or self.nick
        self.realname = str(config.get("realname", "ClawLite") or "ClawLite").strip() or "ClawLite"
        channels_raw = config.get("channels_to_join", config.get("channelsToJoin", []))
        self.channels_to_join = [
            str(item or "").strip()
            for item in (channels_raw if isinstance(channels_raw, list) else [])
            if str(item or "").strip()
        ]
        self.use_ssl = bool(config.get("use_ssl", config.get("useSsl", True)))
        self.connect_timeout_s = max(
            0.1,
            float(config.get("connect_timeout_s", config.get("connectTimeoutS", 10.0)) or 10.0),
        )
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task[Any] | None = None

    async def _write_line(self, line: str) -> None:
        writer = self._writer
        if writer is None:
            raise RuntimeError("irc_not_running")
        writer.write(f"{line}\r\n".encode("utf-8"))
        drain = getattr(writer, "drain", None)
        if callable(drain):
            await drain()

    async def start(self) -> None:
        ssl_value: bool | None = True if self.use_ssl else None
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port, ssl=ssl_value),
            timeout=self.connect_timeout_s,
        )
        self._reader = reader
        self._writer = writer
        self._running = True
        await self._write_line(f"NICK {self.nick}")
        await self._write_line(f"USER {self.username} 0 * :{self.realname}")
        for channel in self.channels_to_join:
            await self._write_line(f"JOIN {channel}")
        self._task = asyncio.create_task(self._read_loop())

    async def stop(self) -> None:
        self._running = False
        try:
            if self._writer is not None:
                await self._write_line("QUIT :ClawLite shutdown")
        except Exception:
            pass
        await cancel_task(self._task)
        self._task = None
        writer = self._writer
        self._writer = None
        self._reader = None
        if writer is not None:
            close = getattr(writer, "close", None)
            if callable(close):
                close()
            wait_closed = getattr(writer, "wait_closed", None)
            if callable(wait_closed):
                try:
                    await wait_closed()
                except Exception:
                    pass

    async def send(self, *, target: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        del metadata
        if not self._running:
            raise RuntimeError("irc_not_running")
        channel = str(target or "").strip()
        if not channel:
            raise ValueError("irc target is required")
        await self._write_line(f"PRIVMSG {channel} :{str(text or '')}")
        return f"irc:sent:{channel}"

    async def _read_loop(self) -> None:
        reader = self._reader
        if reader is None:
            return
        while self._running:
            try:
                raw = await reader.readline()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = str(exc)
                return
            if not raw:
                return
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if line.startswith("PING "):
                try:
                    await self._write_line(f"PONG {line[5:]}")
                except Exception as exc:
                    self._last_error = str(exc)
                    return
                continue
            if " PRIVMSG " not in line or " :" not in line:
                continue
            prefix, _, remainder = line.partition(" PRIVMSG ")
            target, _, text = remainder.partition(" :")
            nick = prefix.split("!", 1)[0].lstrip(":").strip()
            clean_target = str(target or "").strip()
            clean_text = str(text or "").strip()
            if not nick or not clean_target or not clean_text:
                continue
            await self.emit(
                session_id=f"irc:{clean_target}",
                user_id=nick,
                text=clean_text,
                metadata={
                    "channel": "irc",
                    "chat_id": clean_target,
                    "target": clean_target,
                    "nick": nick,
                },
            )
