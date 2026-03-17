from __future__ import annotations

import asyncio
from typing import Any

from clawlite.channels.irc import IRCChannel


class _FakeReader:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        if self._lines:
            return self._lines.pop(0)
        return b""


class _FakeWriter:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data.decode("utf-8"))

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def test_irc_channel_connects_joins_responds_to_ping_and_emits_privmsg(monkeypatch) -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        reader = _FakeReader(
            [
                b"PING :server.example\r\n",
                b":alice!u@h PRIVMSG #clawlite :hello from irc\r\n",
                b"",
            ]
        )
        writer = _FakeWriter()

        async def _open_connection(host: str, port: int, ssl=None):
            del host, port, ssl
            return reader, writer

        monkeypatch.setattr(asyncio, "open_connection", _open_connection)

        channel = IRCChannel(
            config={
                "host": "irc.example.net",
                "port": 6697,
                "nick": "clawlite-bot",
                "channels_to_join": ["#clawlite"],
            },
            on_message=_on_message,
        )
        await channel.start()
        await asyncio.sleep(0.01)

        sent = await channel.send(target="#clawlite", text="reply from bot")
        await channel.stop()

        assert sent == "irc:sent:#clawlite"
        joined = "".join(writer.writes)
        assert "NICK clawlite-bot\r\n" in joined
        assert "USER clawlite-bot 0 * :ClawLite\r\n" in joined
        assert "JOIN #clawlite\r\n" in joined
        assert "PONG :server.example\r\n" in joined
        assert "PRIVMSG #clawlite :reply from bot\r\n" in joined
        assert "QUIT :ClawLite shutdown\r\n" in joined
        assert writer.closed is True
        assert emitted == [
            (
                "irc:#clawlite",
                "alice",
                "hello from irc",
                {
                    "channel": "irc",
                    "chat_id": "#clawlite",
                    "target": "#clawlite",
                    "nick": "alice",
                },
            )
        ]

    asyncio.run(_scenario())
