from __future__ import annotations

import asyncio
import json
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from unittest.mock import patch

import clawlite.channels.email as email_module
from clawlite.channels.email import EmailChannel


def _raw_email(*, sender: str, subject: str, body: str, html_body: str | None = None) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "bot@example.com"
    message["Subject"] = subject
    message["Message-ID"] = "<msg-1@example.com>"
    if html_body is None:
        message.set_content(body)
    else:
        message.set_content(body)
        message.add_alternative(html_body, subtype="html")
    return message.as_bytes()


def test_email_channel_poll_emits_new_messages() -> None:
    async def _scenario() -> None:
        emitted: list[tuple[str, str, str, dict[str, Any]]] = []

        async def _on_message(
            session_id: str,
            user_id: str,
            text: str,
            metadata: dict[str, Any],
        ) -> None:
            emitted.append((session_id, user_id, text, metadata))

        channel = EmailChannel(
            config={
                "imap_host": "imap.example.com",
                "imap_user": "bot@example.com",
                "imap_password": "imap-secret",
            },
            on_message=_on_message,
        )

        def _fetch_once() -> list[dict[str, Any]]:
            return [
                {
                    "sender": "alice@example.com",
                    "subject": "Hello",
                    "message_id": "<msg-1@example.com>",
                    "text": "body from email",
                    "metadata": {
                        "channel": "email",
                        "subject": "Hello",
                        "message_id": "<msg-1@example.com>",
                    },
                }
            ]

        async def _to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        async def _sleep(_delay: float) -> None:
            channel._running = False

        channel._running = True
        with patch.object(channel, "_fetch_new_messages", side_effect=_fetch_once):
            with patch.object(email_module.asyncio, "to_thread", new=_to_thread):
                with patch.object(email_module.asyncio, "sleep", new=_sleep):
                    await channel._poll_loop()

        assert len(emitted) == 1
        session_id, user_id, text, metadata = emitted[0]
        assert session_id == "email:alice@example.com"
        assert user_id == "alice@example.com"
        assert text == "body from email"
        assert metadata["subject"] == "Hello"

    asyncio.run(_scenario())


def test_email_fetch_new_messages_dedupes_uid_and_marks_seen(tmp_path: Path) -> None:
    raw_bytes = _raw_email(
        sender="Alice <alice@example.com>",
        subject="Status",
        body="Tudo certo.",
    )

    class FakeIMAP:
        store_calls: list[tuple[Any, ...]] = []

        def __init__(self, host: str, port: int) -> None:
            self.host = host
            self.port = port

        def login(self, user: str, password: str):
            return ("OK", [user.encode(), password.encode()])

        def select(self, mailbox: str):
            assert mailbox == "INBOX"
            return ("OK", [b"1"])

        def search(self, charset: Any, *criteria: str):
            assert charset is None
            assert criteria == ("UNSEEN",)
            return ("OK", [b"1"])

        def fetch(self, imap_id: bytes, query: str):
            assert imap_id == b"1"
            assert query == "(BODY.PEEK[] UID)"
            return ("OK", [(b"1 (UID 77 BODY[] {100}", raw_bytes)])

        def store(self, imap_id: bytes, action: str, flag: str):
            self.store_calls.append((imap_id, action, flag))
            return ("OK", [b""])

        def logout(self):
            return ("BYE", [b""])

    channel = EmailChannel(
        config={
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_user": "bot@example.com",
            "imap_password": "imap-secret",
            "dedupe_state_path": str(tmp_path / "email-dedupe.json"),
            "mark_seen": True,
        }
    )

    with patch.object(email_module.imaplib, "IMAP4_SSL", FakeIMAP):
        first = channel._fetch_new_messages()
        second = channel._fetch_new_messages()

    assert len(first) == 1
    assert second == []
    assert first[0]["sender"] == "alice@example.com"
    assert first[0]["metadata"]["uid"] == "77"
    assert FakeIMAP.store_calls == [(b"1", "+FLAGS", "\\Seen")]
    dedupe_payload = json.loads((tmp_path / "email-dedupe.json").read_text(encoding="utf-8"))
    assert dedupe_payload["uids"] == ["77"]


def test_email_extract_text_body_falls_back_to_html() -> None:
    message = EmailMessage()
    message["From"] = "Alice <alice@example.com>"
    message["To"] = "bot@example.com"
    message["Subject"] = "HTML only"
    message.add_alternative("<p>Ola<br>mundo</p>", subtype="html")

    text = EmailChannel._extract_text_body(message)

    assert text == "Ola\nmundo"


def test_email_send_falls_back_from_ssl_to_starttls() -> None:
    async def _scenario() -> None:
        channel = EmailChannel(
            config={
                "smtp_host": "smtp.example.com",
                "smtp_port": 465,
                "smtp_user": "bot@example.com",
                "smtp_password": "smtp-secret",
                "smtp_use_ssl": True,
                "smtp_use_starttls": True,
            }
        )
        channel._running = True
        channel._last_subject_by_sender["alice@example.com"] = "Original subject"
        channel._last_message_id_by_sender["alice@example.com"] = "<prev@example.com>"

        class FailingSMTPSSL:
            def __init__(self, *args, **kwargs) -> None:
                del args, kwargs
                raise OSError("ssl failed")

        class FakeSMTP:
            def __init__(self, host: str, port: int, timeout: float) -> None:
                self.host = host
                self.port = port
                self.timeout = timeout
                self.started_tls = False
                self.logged_in: tuple[str, str] | None = None
                self.sent_message: EmailMessage | None = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                del exc_type, exc, tb
                return None

            def starttls(self, context=None) -> None:
                del context
                self.started_tls = True

            def login(self, user: str, password: str) -> None:
                self.logged_in = (user, password)

            def send_message(self, msg: EmailMessage) -> None:
                self.sent_message = msg

        smtp_instances: list[FakeSMTP] = []

        def _smtp_factory(host: str, port: int, timeout: float) -> FakeSMTP:
            instance = FakeSMTP(host, port, timeout)
            smtp_instances.append(instance)
            return instance

        async def _to_thread(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        with patch.object(email_module.smtplib, "SMTP_SSL", FailingSMTPSSL):
            with patch.object(email_module.smtplib, "SMTP", side_effect=_smtp_factory):
                with patch.object(email_module.asyncio, "to_thread", new=_to_thread):
                    out = await channel.send(target="alice@example.com", text="reply body")

        assert out.startswith("email:sent:")
        assert len(smtp_instances) == 1
        smtp = smtp_instances[0]
        assert smtp.started_tls is True
        assert smtp.logged_in == ("bot@example.com", "smtp-secret")
        assert smtp.sent_message is not None
        assert smtp.sent_message["To"] == "alice@example.com"
        assert smtp.sent_message["Subject"] == "Re: Original subject"
        assert smtp.sent_message["In-Reply-To"] == "<prev@example.com>"

    asyncio.run(_scenario())
