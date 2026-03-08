from __future__ import annotations

import asyncio
import imaplib
import json
import re
import smtplib
import ssl
from email import policy
from email.header import decode_header
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from clawlite.channels.base import BaseChannel, cancel_task


class EmailChannel(BaseChannel):
    def __init__(self, *, config: dict[str, Any], on_message=None) -> None:
        super().__init__(name="email", config=config, on_message=on_message)
        self.allow_from = self._normalize_allow_from(config)
        self.imap_host = str(
            config.get("imap_host", config.get("imapHost", ""))
            or ""
        ).strip()
        self.imap_port = max(
            1,
            int(config.get("imap_port", config.get("imapPort", 993)) or 993),
        )
        self.imap_user = str(
            config.get("imap_user", config.get("imapUser", ""))
            or ""
        ).strip()
        self.imap_password = str(
            config.get("imap_password", config.get("imapPassword", ""))
            or ""
        )
        self.imap_use_ssl = bool(
            config.get("imap_use_ssl", config.get("imapUseSsl", True))
        )
        self.smtp_host = str(
            config.get("smtp_host", config.get("smtpHost", ""))
            or ""
        ).strip()
        self.smtp_port = max(
            1,
            int(config.get("smtp_port", config.get("smtpPort", 465)) or 465),
        )
        self.smtp_user = str(
            config.get("smtp_user", config.get("smtpUser", ""))
            or ""
        ).strip()
        self.smtp_password = str(
            config.get("smtp_password", config.get("smtpPassword", ""))
            or ""
        )
        self.smtp_use_ssl = bool(
            config.get("smtp_use_ssl", config.get("smtpUseSsl", True))
        )
        self.smtp_use_starttls = bool(
            config.get("smtp_use_starttls", config.get("smtpUseStarttls", True))
        )
        self.poll_interval_s = max(
            1.0,
            float(config.get("poll_interval_s", config.get("pollIntervalS", 30.0)) or 30.0),
        )
        self.mailbox = (
            str(config.get("mailbox", config.get("imapMailbox", "INBOX")) or "INBOX").strip()
            or "INBOX"
        )
        self.mark_seen = bool(config.get("mark_seen", config.get("markSeen", True)))
        self.max_body_chars = max(
            256,
            int(config.get("max_body_chars", config.get("maxBodyChars", 12000)) or 12000),
        )
        self.from_address = str(
            config.get("from_address", config.get("fromAddress", ""))
            or ""
        ).strip()
        self.dedupe_state_path = self._normalize_dedupe_state_path(
            str(
                config.get("dedupe_state_path", config.get("dedupeStatePath", ""))
                or ""
            )
        )
        self._processed_uids: set[str] = set()
        self._processed_uid_order: list[str] = []
        self._max_processed_uids = 2048
        self._poll_task: asyncio.Task[Any] | None = None
        self._last_subject_by_chat: dict[str, str] = {}
        self._last_message_id_by_chat: dict[str, str] = {}
        self._last_subject_by_sender = self._last_subject_by_chat
        self._last_message_id_by_sender = self._last_message_id_by_chat
        self._load_dedupe_state()

    @staticmethod
    def _normalize_allow_from(config: dict[str, Any]) -> list[str]:
        allow_raw = config.get("allow_from")
        if (not allow_raw) and ("allowFrom" in config):
            allow_raw = config.get("allowFrom")
        if not isinstance(allow_raw, list):
            return []
        return [str(item).strip() for item in allow_raw if str(item).strip()]

    @staticmethod
    def _normalize_dedupe_state_path(raw: str) -> Path:
        value = str(raw or "").strip()
        if value:
            return Path(value).expanduser()
        return Path.home() / ".clawlite" / "state" / "email-dedupe.json"

    def _load_dedupe_state(self) -> None:
        path = self.dedupe_state_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return
        uids_raw = raw.get("uids", []) if isinstance(raw, dict) else []
        if not isinstance(uids_raw, list):
            return
        for item in uids_raw:
            uid = str(item or "").strip()
            if uid and uid not in self._processed_uids:
                self._processed_uids.add(uid)
                self._processed_uid_order.append(uid)
        self._trim_processed_uids()

    def _save_dedupe_state(self) -> None:
        path = self.dedupe_state_path
        payload = {"uids": list(self._processed_uid_order[-self._max_processed_uids :])}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        except OSError:
            return

    def _trim_processed_uids(self) -> None:
        overflow = len(self._processed_uid_order) - self._max_processed_uids
        if overflow <= 0:
            return
        for uid in self._processed_uid_order[:overflow]:
            self._processed_uids.discard(uid)
        self._processed_uid_order = self._processed_uid_order[overflow:]

    def _remember_uid(self, uid: str) -> None:
        normalized_uid = str(uid or "").strip()
        if not normalized_uid or normalized_uid in self._processed_uids:
            return
        self._processed_uids.add(normalized_uid)
        self._processed_uid_order.append(normalized_uid)
        self._trim_processed_uids()
        self._save_dedupe_state()

    def _is_allowed_sender(self, sender: str) -> bool:
        if not self.allow_from:
            return True
        normalized_sender = str(sender or "").strip().lower()
        allowed = {
            str(item or "").strip().lower()
            for item in self.allow_from
            if str(item or "").strip()
        }
        return normalized_sender in allowed

    def _validate_receive_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("imap_host", self.imap_host),
                ("imap_user", self.imap_user),
                ("imap_password", self.imap_password),
            )
            if not str(value or "").strip()
        ]
        if missing:
            raise ValueError(f"email receive config missing: {', '.join(missing)}")

    def _validate_send_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("smtp_host", self.smtp_host),
                ("smtp_user", self.smtp_user),
                ("smtp_password", self.smtp_password),
            )
            if not str(value or "").strip()
        ]
        if missing:
            raise ValueError(f"email send config missing: {', '.join(missing)}")

    async def start(self) -> None:
        self._running = True
        if self.on_message is None:
            return
        self._validate_receive_config()
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        poll_task = self._poll_task
        self._poll_task = None
        await cancel_task(poll_task)

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                messages = await asyncio.to_thread(self._fetch_new_messages)
                for item in messages:
                    sender = str(
                        item.get("from", item.get("sender", "")) or ""
                    ).strip().lower()
                    if not sender or not self._is_allowed_sender(sender):
                        continue
                    text = str(item.get("text", "") or "").strip()
                    if not text:
                        continue
                    metadata = dict(item.get("metadata", {}) or {})
                    await self.emit(
                        session_id=f"email:{sender}",
                        user_id=sender,
                        text=text,
                        metadata=metadata,
                    )
                    subject = str(metadata.get("subject", "") or "").strip()
                    if subject:
                        self._last_subject_by_chat[sender] = subject
                    message_id = str(metadata.get("message_id", "") or "").strip()
                    if message_id:
                        self._last_message_id_by_chat[sender] = message_id
                self._last_error = ""
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = str(exc)
            await asyncio.sleep(self.poll_interval_s)

    async def send(
        self,
        *,
        target: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        self._validate_send_config()
        if not self._running:
            raise RuntimeError("email_not_running")
        recipient = str(target or "").strip().lower()
        if not recipient:
            raise ValueError("email target is required")
        payload = dict(metadata or {})
        subject_override = str(payload.get("subject", "") or "").strip()
        base_subject = subject_override or self._last_subject_by_chat.get(recipient, "")
        subject = self._reply_subject(base_subject or "ClawLite reply")
        if subject_override:
            subject = subject_override
        message = EmailMessage()
        message["From"] = self.from_address or self.smtp_user or self.imap_user
        message["To"] = recipient
        message["Subject"] = subject
        reply_to = str(payload.get("reply_to", "") or "").strip()
        if reply_to:
            message["Reply-To"] = reply_to
        in_reply_to = str(
            payload.get(
                "in_reply_to",
                self._last_message_id_by_chat.get(recipient, ""),
            )
            or ""
        ).strip()
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
        references = str(payload.get("references", "") or "").strip()
        if references:
            message["References"] = references
        elif in_reply_to:
            message["References"] = in_reply_to
        message.set_content(str(text or ""))
        await asyncio.to_thread(self._smtp_send, message)
        self._last_error = ""
        message_id = re.sub(r"[^a-zA-Z0-9]+", "-", recipient).strip("-") or "sent"
        return f"email:sent:{message_id}"

    def _connect_imap(self):
        if self.imap_use_ssl:
            return imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        return imaplib.IMAP4(self.imap_host, self.imap_port)

    def _fetch_new_messages(self) -> list[dict[str, Any]]:
        return self._fetch_messages(
            search_criteria=("UNSEEN",),
            mark_seen=self.mark_seen,
            dedupe=True,
            limit=0,
        )

    def _fetch_messages(
        self,
        search_criteria: tuple[str, ...],
        mark_seen: bool,
        dedupe: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        client = self._connect_imap()
        try:
            client.login(self.imap_user, self.imap_password)
            status, _ = client.select(self.mailbox)
            if status != "OK":
                return items
            status, data = client.search(None, *search_criteria)
            if status != "OK" or not data:
                return items
            message_ids = data[0].split()
            if limit > 0:
                message_ids = message_ids[-limit:]
            for imap_id_raw in message_ids:
                imap_id = imap_id_raw.decode("utf-8", errors="ignore").strip()
                status, fetched = client.fetch(imap_id_raw, "(BODY.PEEK[] UID)")
                if status != "OK" or not fetched:
                    continue
                raw_bytes = self._extract_message_bytes(fetched)
                if raw_bytes is None:
                    continue
                uid = self._extract_uid(fetched)
                if dedupe and uid and uid in self._processed_uids:
                    continue
                parsed = BytesParser(policy=policy.default).parsebytes(raw_bytes)
                sender = parseaddr(parsed.get("From", ""))[1].strip().lower()
                if not sender:
                    continue
                subject = self._decode_header_value(parsed.get("Subject", ""))
                body = self._extract_text_body(parsed).strip()
                if not body:
                    body = "[empty email body]"
                body = body[: self.max_body_chars]
                message_id = str(parsed.get("Message-ID", "") or "").strip()
                metadata = {
                    "channel": "email",
                    "chat_id": sender,
                    "from": sender,
                    "to": str(parsed.get("To", "") or "").strip(),
                    "subject": subject,
                    "message_id": message_id,
                    "uid": uid,
                    "date": str(parsed.get("Date", "") or "").strip(),
                    "reply_to": parseaddr(parsed.get("Reply-To", ""))[1].strip().lower(),
                }
                items.append(
                    {
                        "imap_id": imap_id,
                        "sender": sender,
                        "from": sender,
                        "text": body,
                        "metadata": metadata,
                    }
                )
                if uid:
                    self._remember_uid(uid)
                if mark_seen:
                    try:
                        client.store(imap_id_raw, "+FLAGS", "\\Seen")
                    except Exception:
                        pass
            return items
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def _mark_seen(self, imap_id: str) -> None:
        client = self._connect_imap()
        try:
            client.login(self.imap_user, self.imap_password)
            status, _ = client.select(self.mailbox)
            if status != "OK":
                return
            client.store(imap_id.encode("utf-8"), "+FLAGS", "\\Seen")
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def _smtp_send(self, msg: EmailMessage) -> None:
        last_exc: Exception | None = None
        if self.smtp_use_ssl:
            try:
                with smtplib.SMTP_SSL(
                    self.smtp_host,
                    self.smtp_port,
                    timeout=30,
                ) as smtp:
                    smtp.login(self.smtp_user, self.smtp_password)
                    smtp.send_message(msg)
                    return
            except (OSError, smtplib.SMTPException) as exc:
                last_exc = exc
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as smtp:
                if self.smtp_use_starttls:
                    try:
                        smtp.starttls(context=ssl.create_default_context())
                    except smtplib.SMTPException:
                        pass
                smtp.login(self.smtp_user, self.smtp_password)
                smtp.send_message(msg)
                return
        except (OSError, smtplib.SMTPException) as exc:
            last_exc = exc
        if last_exc is not None:
            raise last_exc

    @staticmethod
    def _extract_message_bytes(fetched: Any) -> bytes | None:
        if not isinstance(fetched, list):
            return None
        for row in fetched:
            if not isinstance(row, tuple) or len(row) < 2:
                continue
            payload = row[1]
            if isinstance(payload, bytes):
                return payload
        return None

    @staticmethod
    def _extract_uid(fetched: Any) -> str:
        if not isinstance(fetched, list):
            return ""
        for row in fetched:
            if not isinstance(row, tuple) or not row:
                continue
            header = row[0]
            if isinstance(header, bytes):
                text = header.decode("utf-8", errors="ignore")
            else:
                text = str(header or "")
            match = re.search(r"UID\s+(\d+)", text)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _decode_header_value(value: Any) -> str:
        if value is None:
            return ""
        parts = decode_header(str(value))
        out: list[str] = []
        for chunk, encoding in parts:
            if isinstance(chunk, bytes):
                try:
                    out.append(chunk.decode(encoding or "utf-8", errors="replace"))
                except LookupError:
                    out.append(chunk.decode("utf-8", errors="replace"))
            else:
                out.append(str(chunk))
        return "".join(out).strip()

    @staticmethod
    def _extract_text_body(msg: Message) -> str:
        if msg.is_multipart():
            html_body = ""
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", "") or "").lower()
                if "attachment" in content_disposition:
                    continue
                content_type = str(part.get_content_type() or "").lower()
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                if not payload:
                    continue
                try:
                    decoded = payload.decode(charset, errors="replace")
                except LookupError:
                    decoded = payload.decode("utf-8", errors="replace")
                if content_type == "text/plain":
                    return decoded.strip()
                if content_type == "text/html" and not html_body:
                    html_body = decoded
            if html_body:
                return EmailChannel._html_to_text(html_body)
            return ""
        payload = msg.get_payload(decode=True)
        if not payload:
            return ""
        charset = msg.get_content_charset() or "utf-8"
        try:
            decoded = payload.decode(charset, errors="replace")
        except LookupError:
            decoded = payload.decode("utf-8", errors="replace")
        if str(msg.get_content_type() or "").lower() == "text/html":
            return EmailChannel._html_to_text(decoded)
        return decoded.strip()

    @staticmethod
    def _html_to_text(raw_html: str) -> str:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", str(raw_html or ""))
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</p\s*>", "\n\n", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _reply_subject(base_subject: str) -> str:
        subject = str(base_subject or "").strip()
        if not subject:
            return "Re: ClawLite reply"
        if subject.lower().startswith("re:"):
            return subject
        return f"Re: {subject}"
