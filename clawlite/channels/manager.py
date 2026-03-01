from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from clawlite.channels.base import BaseChannel
from clawlite.channels.telegram import TelegramChannel
from clawlite.channels.discord import DiscordChannel
from clawlite.channels.slack import SlackChannel
from clawlite.channels.whatsapp import WhatsAppChannel
from clawlite.channels.googlechat import GoogleChatChannel
from clawlite.channels.irc import IrcChannel
from clawlite.channels.signal import SignalChannel
from clawlite.channels.imessage import IMessageChannel
from clawlite.config.settings import load_config
from clawlite.core.agent import run_task_with_meta
from clawlite.runtime.channel_sessions import ChannelSessionManager
from clawlite.runtime.message_bus import InboundEnvelope, MessageBus, OutboundEnvelope

logger = logging.getLogger(__name__)

TOKEN_OPTIONAL_CHANNELS = {"googlechat", "irc", "signal", "imessage"}

# Registry of available channel classes
CHANNEL_CLASSES: dict[str, type[BaseChannel]] = {
    "telegram": TelegramChannel,
    "discord": DiscordChannel,
    "slack": SlackChannel,
    "whatsapp": WhatsAppChannel,
    "googlechat": GoogleChatChannel,
    "irc": IrcChannel,
    "signal": SignalChannel,
    "imessage": IMessageChannel,
}


class ChannelManager:
    """Gerencia o ciclo de vida dos canais de comunicação."""

    def __init__(self) -> None:
        self.active_channels: dict[str, BaseChannel] = {}
        self.active_metadata: dict[str, dict[str, Any]] = {}
        self.sessions = ChannelSessionManager()
        self._bus = MessageBus(inbound_handler=self._process_inbound, outbound_handler=self._send_outbound)

    async def _process_inbound(self, env: InboundEnvelope) -> str:
        """
        Callback central para processar mensagens recebidas de qualquer canal.
        Roteia diretamente para o core LLM.
        """
        # O run_task_with_meta é síncrono, então rodamos em uma thread
        prompt = env.text.strip()
        try:
            output, meta = await asyncio.to_thread(run_task_with_meta, prompt)
            return output
        except Exception as exc:
            logger.error(f"Erro no processamento da mensagem do canal: {exc}")
            return "Ocorreu um erro interno ao processar a requisição."

    async def _send_outbound(self, env: OutboundEnvelope) -> None:
        instance_key = env.instance_key
        if instance_key:
            channel = self.active_channels.get(instance_key)
            if channel is not None:
                await channel.send_message(env.session_id, env.text)
                return

        for key, channel in self.active_channels.items():
            meta = self.active_metadata.get(key, {})
            ch_name = str(meta.get("channel", "")).strip().lower() or key.split(":", 1)[0]
            if ch_name != env.channel:
                continue
            await channel.send_message(env.session_id, env.text)
            return

        raise RuntimeError(f"canal outbound indisponível: {env.channel}")

    async def _handle_message(self, session_id: str, text: str, channel: str = "") -> str:
        return await self._bus.request_reply(channel=channel, session_id=session_id, text=text)

    def _build_message_handler(self, *, instance_key: str, channel_name: str):
        async def _handler(session_id: str, text: str) -> str:
            sid = str(session_id or "").strip()
            if sid:
                try:
                    self.sessions.bind(instance_key=instance_key, channel=channel_name, session_id=sid)
                except Exception:
                    pass

            cmd = str(text or "").strip().lower()
            if cmd in {"/stop", "stop", "/cancel"}:
                cancelled = self.sessions.cancel_session_tasks(sid)
                sub_cancelled = 0
                if sid:
                    try:
                        from clawlite.runtime.subagents import get_subagent_runtime

                        sub_cancelled = get_subagent_runtime().cancel_session(sid)
                    except Exception:
                        sub_cancelled = 0
                total = cancelled + sub_cancelled
                return f"⏹ Stopped {total} task(s)." if total > 0 else "No active task to stop."

            task = asyncio.create_task(self._handle_message(session_id, text, channel_name))
            if sid:
                self.sessions.register_task(sid, task)
            try:
                return await task
            except asyncio.CancelledError:
                return "⏹ Task cancelled."
            finally:
                if sid:
                    self.sessions.unregister_task(sid, task)

        return _handler

    @staticmethod
    def _as_str_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    @staticmethod
    def _as_positive_float(value: Any, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(default)
        if parsed <= 0:
            return float(default)
        return parsed

    @staticmethod
    def _as_positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return int(default)
        if parsed <= 0:
            return int(default)
        return parsed

    @staticmethod
    def _pairing_enabled_from_cfg(cfg: dict[str, Any]) -> bool:
        security = cfg.get("security", {}) if isinstance(cfg.get("security"), dict) else {}
        pairing = security.get("pairing", {}) if isinstance(security.get("pairing"), dict) else {}
        return bool(pairing.get("enabled", False))

    def _build_channel_kwargs(
        self,
        channel_name: str,
        ch_data: dict[str, Any],
        *,
        pairing_enabled: bool,
    ) -> dict[str, Any]:
        allow_from = self._as_str_list(ch_data.get("allowFrom"))
        allow_channels = self._as_str_list(ch_data.get("allowChannels"))
        if channel_name == "telegram":
            mode_raw = str(ch_data.get("mode") or "").strip().lower()
            webhook_enabled = bool(ch_data.get("webhook_enabled", ch_data.get("webhookEnabled", False)))
            mode = mode_raw if mode_raw in {"polling", "webhook"} else ("webhook" if webhook_enabled else "polling")
            poll_interval_s = self._as_positive_float(
                ch_data.get("poll_interval_s", ch_data.get("pollIntervalSec", 1.0)),
                1.0,
            )
            poll_timeout_s = self._as_positive_int(
                ch_data.get("poll_timeout_s", ch_data.get("pollTimeoutSec", 30)),
                30,
            )
            reconnect_initial_s = self._as_positive_float(
                ch_data.get("reconnect_initial_s", ch_data.get("reconnectInitialSec", 2.0)),
                2.0,
            )
            reconnect_max_s = self._as_positive_float(
                ch_data.get("reconnect_max_s", ch_data.get("reconnectMaxSec", 30.0)),
                30.0,
            )
            return {
                "allowed_accounts": allow_from,
                "pairing_enabled": pairing_enabled,
                "mode": mode,
                "webhook_secret": str(ch_data.get("webhook_secret") or ch_data.get("webhookSecret") or "").strip(),
                "webhook_path": str(ch_data.get("webhook_path") or ch_data.get("webhookPath") or "/api/webhooks/telegram").strip()
                or "/api/webhooks/telegram",
                "poll_interval_s": poll_interval_s,
                "poll_timeout_s": poll_timeout_s,
                "reconnect_initial_s": reconnect_initial_s,
                "reconnect_max_s": reconnect_max_s,
            }
        if channel_name == "discord":
            return {
                "allowed_users": allow_from,
                "allowed_channels": allow_channels,
                "pairing_enabled": pairing_enabled,
            }
        if channel_name == "slack":
            app_token = str(
                ch_data.get("app_token")
                or ch_data.get("socket_mode_token")
                or os.getenv("SLACK_APP_TOKEN", "")
            ).strip()
            return {
                "app_token": app_token,
                "allowed_users": allow_from,
                "allowed_channels": allow_channels,
                "pairing_enabled": pairing_enabled,
            }
        if channel_name == "whatsapp":
            phone_number_id = str(ch_data.get("phone_number_id") or ch_data.get("phone") or "").strip()
            return {
                "phone_number_id": phone_number_id,
                "allowed_numbers": allow_from,
                "pairing_enabled": pairing_enabled,
            }
        if channel_name == "googlechat":
            dm_cfg = ch_data.get("dm", {})
            dm_allow = self._as_str_list(dm_cfg.get("allowFrom")) if isinstance(dm_cfg, dict) else []
            bot_user = str(ch_data.get("botUser") or ch_data.get("bot_user") or "").strip()
            require_mention = bool(ch_data.get("requireMention", True))
            send_timeout_s = self._as_positive_float(
                ch_data.get("send_timeout_s", ch_data.get("sendTimeoutSec", 8.0)),
                8.0,
            )
            send_circuit_failure_threshold = self._as_positive_int(
                ch_data.get("send_circuit_failure_threshold", ch_data.get("sendCircuitFailureThreshold", 5)),
                5,
            )
            send_circuit_cooldown_s = self._as_positive_float(
                ch_data.get("send_circuit_cooldown_s", ch_data.get("sendCircuitCooldownSec", 30.0)),
                30.0,
            )
            outbound_webhook_url = str(
                ch_data.get("outbound_webhook_url")
                or ch_data.get("outboundWebhookUrl")
                or ch_data.get("webhookUrl")
                or ""
            ).strip()
            return {
                "allowed_users": dm_allow or allow_from,
                "allowed_spaces": allow_channels,
                "bot_user": bot_user,
                "require_mention": require_mention,
                "outbound_webhook_url": outbound_webhook_url,
                "send_timeout_s": send_timeout_s,
                "send_circuit_failure_threshold": send_circuit_failure_threshold,
                "send_circuit_cooldown_s": send_circuit_cooldown_s,
                "pairing_enabled": pairing_enabled,
            }
        if channel_name == "irc":
            group_allow = self._as_str_list(ch_data.get("groupAllowFrom"))
            configured_channels = self._as_str_list(ch_data.get("channels"))
            raw_port = ch_data.get("port", 6697)
            try:
                port = int(raw_port)
            except (TypeError, ValueError):
                port = 6697
            send_timeout_s = self._as_positive_float(
                ch_data.get("send_timeout_s", ch_data.get("sendTimeoutSec", 10.0)),
                10.0,
            )
            send_circuit_failure_threshold = self._as_positive_int(
                ch_data.get("send_circuit_failure_threshold", ch_data.get("sendCircuitFailureThreshold", 5)),
                5,
            )
            send_circuit_cooldown_s = self._as_positive_float(
                ch_data.get("send_circuit_cooldown_s", ch_data.get("sendCircuitCooldownSec", 30.0)),
                30.0,
            )
            return {
                "host": str(ch_data.get("host", "")).strip(),
                "port": port,
                "tls": bool(ch_data.get("tls", True)),
                "nick": str(ch_data.get("nick", "clawlite-bot")).strip() or "clawlite-bot",
                "channels": configured_channels,
                "allowed_senders": group_allow or allow_from,
                "allowed_channels": allow_channels or configured_channels,
                "require_mention": bool(ch_data.get("requireMention", True)),
                "relay_url": str(ch_data.get("relay_url") or ch_data.get("relayUrl") or "").strip(),
                "send_timeout_s": send_timeout_s,
                "send_circuit_failure_threshold": send_circuit_failure_threshold,
                "send_circuit_cooldown_s": send_circuit_cooldown_s,
                "pairing_enabled": pairing_enabled,
            }
        if channel_name == "signal":
            send_timeout_s = self._as_positive_float(
                ch_data.get("send_timeout_s", ch_data.get("sendTimeoutSec", 15.0)),
                15.0,
            )
            send_circuit_failure_threshold = self._as_positive_int(
                ch_data.get("send_circuit_failure_threshold", ch_data.get("sendCircuitFailureThreshold", 5)),
                5,
            )
            send_circuit_cooldown_s = self._as_positive_float(
                ch_data.get("send_circuit_cooldown_s", ch_data.get("sendCircuitCooldownSec", 30.0)),
                30.0,
            )
            return {
                "account": str(ch_data.get("account", "")).strip(),
                "cli_path": str(ch_data.get("cli_path") or ch_data.get("cliPath") or "signal-cli").strip(),
                "http_url": str(ch_data.get("http_url") or ch_data.get("httpUrl") or "").strip(),
                "allowed_numbers": allow_from,
                "send_timeout_s": send_timeout_s,
                "send_circuit_failure_threshold": send_circuit_failure_threshold,
                "send_circuit_cooldown_s": send_circuit_cooldown_s,
                "pairing_enabled": pairing_enabled,
            }
        if channel_name == "imessage":
            send_timeout_s = self._as_positive_float(
                ch_data.get("send_timeout_s", ch_data.get("sendTimeoutSec", 15.0)),
                15.0,
            )
            send_circuit_failure_threshold = self._as_positive_int(
                ch_data.get("send_circuit_failure_threshold", ch_data.get("sendCircuitFailureThreshold", 5)),
                5,
            )
            send_circuit_cooldown_s = self._as_positive_float(
                ch_data.get("send_circuit_cooldown_s", ch_data.get("sendCircuitCooldownSec", 30.0)),
                30.0,
            )
            return {
                "cli_path": str(ch_data.get("cli_path") or ch_data.get("cliPath") or "imsg").strip(),
                "service": str(ch_data.get("service", "auto")).strip().lower(),
                "allowed_handles": allow_from,
                "send_timeout_s": send_timeout_s,
                "send_circuit_failure_threshold": send_circuit_failure_threshold,
                "send_circuit_cooldown_s": send_circuit_cooldown_s,
                "pairing_enabled": pairing_enabled,
            }
        return {}

    @staticmethod
    def _credentials_list(channel_name: str, ch_data: dict[str, Any]) -> list[dict[str, Any]]:
        credentials: list[dict[str, Any]] = []
        primary_token = str(ch_data.get("token", "")).strip()
        if primary_token:
            credentials.append({
                "name": str(ch_data.get("account", "")).strip(),
                "token": primary_token,
                "cfg": dict(ch_data),
            })
        elif channel_name in TOKEN_OPTIONAL_CHANNELS:
            credentials.append({
                "name": str(ch_data.get("account", "")).strip(),
                "token": "",
                "cfg": dict(ch_data),
            })

        raw_accounts = ch_data.get("accounts", [])
        if isinstance(raw_accounts, list):
            for index, entry in enumerate(raw_accounts, start=1):
                if not isinstance(entry, dict):
                    continue
                token = str(entry.get("token", "")).strip()
                if not token and channel_name not in TOKEN_OPTIONAL_CHANNELS:
                    continue
                account_name = str(entry.get("account") or entry.get("name") or f"account-{index}").strip()
                merged_cfg = dict(ch_data)
                merged_cfg.update(entry)
                credentials.append({"name": account_name, "token": token, "cfg": merged_cfg})
        return credentials

    def _instance_keys_for_channel(self, channel_name: str) -> list[str]:
        base = str(channel_name or "").strip().lower()
        if not base:
            return []
        prefix = f"{base}:"
        return [key for key in self.active_channels.keys() if key == base or key.startswith(prefix)]

    @staticmethod
    def _fallback_session_id(channel_name: str, ch_data: dict[str, Any]) -> str:
        ch = str(channel_name or "").strip().lower()
        if ch == "telegram":
            chat_id = str(ch_data.get("chat_id") or ch_data.get("chatId") or "").strip()
            thread_id = str(ch_data.get("thread_id") or ch_data.get("threadId") or "").strip()
            if not chat_id:
                return ""
            return f"tg_{chat_id}:topic:{thread_id}" if thread_id else f"tg_{chat_id}"
        if ch == "discord":
            target = str(ch_data.get("channel_id") or ch_data.get("default_channel") or "").strip()
            if not target:
                channels = ch_data.get("allowChannels")
                if isinstance(channels, list) and channels:
                    target = str(channels[0]).strip()
            return f"dc_{target}" if target else ""
        if ch == "slack":
            target = str(ch_data.get("channel_id") or ch_data.get("default_channel") or "").strip()
            if not target:
                channels = ch_data.get("allowChannels")
                if isinstance(channels, list) and channels:
                    target = str(channels[0]).strip()
            return f"sl_{target}" if target else ""
        if ch == "whatsapp":
            target = str(ch_data.get("to") or ch_data.get("phone") or ch_data.get("chat_id") or "").strip()
            if not target:
                allow_from = ch_data.get("allowFrom")
                if isinstance(allow_from, list) and allow_from:
                    target = str(allow_from[0]).strip()
            return f"wa_{target}" if target else ""
        if ch == "googlechat":
            target = str(ch_data.get("space") or ch_data.get("default_space") or "").strip()
            if not target:
                allow_channels = ch_data.get("allowChannels")
                if isinstance(allow_channels, list) and allow_channels:
                    target = str(allow_channels[0]).strip()
            return f"gc_group_{target}" if target else ""
        if ch == "irc":
            target = str(ch_data.get("default_channel") or "").strip()
            if not target:
                channels = ch_data.get("channels")
                if isinstance(channels, list) and channels:
                    target = str(channels[0]).strip()
            return f"irc_group_{target}" if target else ""
        if ch == "signal":
            target = str(ch_data.get("to") or "").strip()
            if not target:
                allow_from = ch_data.get("allowFrom")
                if isinstance(allow_from, list) and allow_from:
                    target = str(allow_from[0]).strip()
            return f"signal_dm_{target}" if target else ""
        if ch == "imessage":
            target = str(ch_data.get("to") or "").strip()
            if not target:
                allow_from = ch_data.get("allowFrom")
                if isinstance(allow_from, list) and allow_from:
                    target = str(allow_from[0]).strip()
            return f"imessage_dm_{target}" if target else ""
        return ""

    @staticmethod
    def _default_outbound_metrics() -> dict[str, Any]:
        return {
            "sent_ok": 0,
            "retry_count": 0,
            "timeout_count": 0,
            "fallback_count": 0,
            "send_fail_count": 0,
            "dedupe_hits": 0,
            "circuit_open_count": 0,
            "circuit_half_open_count": 0,
            "circuit_blocked_count": 0,
            "circuit_state": "closed",
            "circuit_consecutive_failures": 0,
            "circuit_failure_threshold": 5,
            "circuit_cooldown_seconds": 30.0,
            "circuit_cooldown_remaining_s": 0.0,
            "circuit_open_until": None,
            "last_success_at": None,
        }

    @classmethod
    def _normalize_outbound_metrics(cls, value: Any) -> dict[str, Any]:
        row = cls._default_outbound_metrics()
        if not isinstance(value, dict):
            return row
        for key in (
            "sent_ok",
            "retry_count",
            "timeout_count",
            "fallback_count",
            "send_fail_count",
            "dedupe_hits",
            "circuit_open_count",
            "circuit_half_open_count",
            "circuit_blocked_count",
            "circuit_consecutive_failures",
            "circuit_failure_threshold",
        ):
            raw = value.get(key, row[key])
            try:
                row[key] = max(0, int(raw))
            except (TypeError, ValueError):
                row[key] = 0
        for key in ("circuit_cooldown_seconds", "circuit_cooldown_remaining_s"):
            raw = value.get(key, row[key])
            try:
                row[key] = max(0.0, float(raw))
            except (TypeError, ValueError):
                row[key] = 0.0
        state = str(value.get("circuit_state", "closed")).strip().lower()
        if state not in {"closed", "open", "half_open"}:
            state = "closed"
        row["circuit_state"] = state
        circuit_open_until = value.get("circuit_open_until")
        if isinstance(circuit_open_until, str) and circuit_open_until.strip():
            row["circuit_open_until"] = circuit_open_until.strip()
        last_success_at = value.get("last_success_at")
        if isinstance(last_success_at, str) and last_success_at.strip():
            row["last_success_at"] = last_success_at.strip()
        last_error = value.get("last_error")
        if isinstance(last_error, dict):
            row["last_error"] = {
                "provider": str(last_error.get("provider", "")).strip(),
                "code": str(last_error.get("code", "")).strip(),
                "severity": str(last_error.get("severity", "")).strip(),
                "category": str(last_error.get("category", "")).strip(),
                "policy_version": str(last_error.get("policy_version", "")).strip(),
                "reason": str(last_error.get("reason", "")).strip(),
                "attempts": int(last_error.get("attempts", 0) or 0),
                "at": str(last_error.get("at", "")).strip(),
            }
        return row

    async def _stop_instance(self, instance_key: str) -> bool:
        channel = self.active_channels.get(instance_key)
        if channel is None:
            return False
        try:
            await channel.stop()
            logger.info(f"Canal '{instance_key}' desconectado.")
        except Exception as exc:
            logger.error(f"Erro ao parar canal '{instance_key}': {exc}")
        finally:
            self.sessions.drop_instance(instance_key)
            self.active_channels.pop(instance_key, None)
            self.active_metadata.pop(instance_key, None)
        return True

    async def start_channel(
        self,
        channel_name: str,
        *,
        cfg: dict[str, Any] | None = None,
    ) -> list[str]:
        cfg_obj = cfg or load_config()
        channels_cfg = cfg_obj.get("channels", {})
        if not isinstance(channels_cfg, dict):
            return []

        normalized_channel = str(channel_name or "").strip().lower()
        ch_data = channels_cfg.get(normalized_channel, {})
        if not isinstance(ch_data, dict):
            return []
        if not bool(ch_data.get("enabled", False)):
            return []

        channel_cls = CHANNEL_CLASSES.get(normalized_channel)
        if channel_cls is None:
            logger.warning(f"Tipo de canal não suportado: {normalized_channel}")
            return []

        credentials = self._credentials_list(normalized_channel, ch_data)
        if not credentials:
            logger.warning(
                f"Canal '{normalized_channel}' está habilitado, mas sem credenciais/configuração mínima."
            )
            return []

        pairing_enabled = self._pairing_enabled_from_cfg(cfg_obj)
        started: list[str] = []
        for index, cred in enumerate(credentials):
            account_name = str(cred.get("name", "")).strip()
            instance_key = normalized_channel if index == 0 else f"{normalized_channel}:{account_name or index}"
            if instance_key in self.active_channels:
                continue
            try:
                channel_kwargs = self._build_channel_kwargs(
                    normalized_channel,
                    cred.get("cfg", ch_data),
                    pairing_enabled=pairing_enabled,
                )
                if normalized_channel == "telegram":
                    channel_kwargs["account_id"] = account_name
                channel = channel_cls(token=cred["token"], name=normalized_channel, **channel_kwargs)
                channel.on_message(
                    self._build_message_handler(instance_key=instance_key, channel_name=normalized_channel)
                )
                await channel.start()
                if not channel.running:
                    logger.error(
                        f"Falha ao iniciar canal '{instance_key}': inicialização incompleta. "
                        "Verifique token(s), dependências e logs do canal."
                    )
                    continue
                self.active_channels[instance_key] = channel
                self.active_metadata[instance_key] = {
                    "channel": normalized_channel,
                    "account": account_name,
                }
                started.append(instance_key)
                label = f"{normalized_channel} ({account_name})" if account_name else normalized_channel
                logger.info(f"Canal '{label}' habilitado e conectado.")
            except Exception as exc:
                logger.error(f"Falha ao iniciar canal '{instance_key}': {exc}")
        return started

    async def reconnect_channel(self, channel_name: str) -> dict[str, Any]:
        normalized_channel = str(channel_name or "").strip().lower()
        if not normalized_channel:
            raise ValueError("channel é obrigatório")

        stopped: list[str] = []
        for instance_key in list(self._instance_keys_for_channel(normalized_channel)):
            if await self._stop_instance(instance_key):
                stopped.append(instance_key)

        cfg = load_config()
        started = await self.start_channel(normalized_channel, cfg=cfg)
        ch_cfg = cfg.get("channels", {}).get(normalized_channel, {})
        return {
            "channel": normalized_channel,
            "enabled": bool(ch_cfg.get("enabled", False)) if isinstance(ch_cfg, dict) else False,
            "stopped": stopped,
            "started": started,
        }

    def describe_instances(self, channel_name: str | None = None) -> list[dict[str, Any]]:
        only_channel = str(channel_name or "").strip().lower()
        rows: list[dict[str, Any]] = []
        for instance_key, channel in self.active_channels.items():
            meta = self.active_metadata.get(instance_key, {})
            ch_name = str(meta.get("channel", "") or instance_key.split(":", 1)[0]).strip().lower()
            if only_channel and ch_name != only_channel:
                continue
            outbound_metrics: dict[str, Any] | None = None
            snapshot_fn = getattr(channel, "outbound_metrics_snapshot", None)
            if callable(snapshot_fn):
                try:
                    outbound_metrics = self._normalize_outbound_metrics(snapshot_fn())
                except Exception as exc:
                    logger.warning("Falha ao coletar métricas outbound de '%s': %s", instance_key, exc)
            rows.append(
                {
                    "instance_key": instance_key,
                    "channel": ch_name,
                    "account": str(meta.get("account", "")).strip(),
                    "running": bool(getattr(channel, "running", False)),
                    "outbound": outbound_metrics,
                }
            )
        rows.sort(key=lambda row: row["instance_key"])
        return rows

    def outbound_metrics(self, channel_name: str | None = None) -> dict[str, dict[str, Any]]:
        only_channel = str(channel_name or "").strip().lower()
        rows: dict[str, dict[str, Any]] = {}

        for instance_key, channel in self.active_channels.items():
            meta = self.active_metadata.get(instance_key, {})
            ch_name = str(meta.get("channel", "") or instance_key.split(":", 1)[0]).strip().lower()
            if not ch_name:
                continue
            if only_channel and ch_name != only_channel:
                continue
            snapshot_fn = getattr(channel, "outbound_metrics_snapshot", None)
            if not callable(snapshot_fn):
                continue
            try:
                snapshot = self._normalize_outbound_metrics(snapshot_fn())
            except Exception as exc:
                logger.warning("Falha ao coletar métricas outbound de '%s': %s", instance_key, exc)
                continue

            aggregate = rows.get(ch_name)
            if aggregate is None:
                aggregate = self._default_outbound_metrics()
                aggregate["instances_reporting"] = 0
                aggregate["circuit_instances_open"] = 0
                aggregate["circuit_instances_half_open"] = 0
                rows[ch_name] = aggregate

            aggregate["instances_reporting"] = int(aggregate.get("instances_reporting", 0)) + 1
            for key in (
                "sent_ok",
                "retry_count",
                "timeout_count",
                "fallback_count",
                "send_fail_count",
                "dedupe_hits",
                "circuit_open_count",
                "circuit_half_open_count",
                "circuit_blocked_count",
            ):
                aggregate[key] = int(aggregate.get(key, 0)) + int(snapshot.get(key, 0))

            state = str(snapshot.get("circuit_state", "closed")).strip().lower()
            if state == "open":
                aggregate["circuit_instances_open"] = int(aggregate.get("circuit_instances_open", 0)) + 1
            elif state == "half_open":
                aggregate["circuit_instances_half_open"] = int(aggregate.get("circuit_instances_half_open", 0)) + 1

            if state == "open":
                aggregate["circuit_state"] = "open"
            elif state == "half_open" and str(aggregate.get("circuit_state")) != "open":
                aggregate["circuit_state"] = "half_open"

            aggregate["circuit_consecutive_failures"] = max(
                int(aggregate.get("circuit_consecutive_failures", 0) or 0),
                int(snapshot.get("circuit_consecutive_failures", 0) or 0),
            )
            aggregate["circuit_failure_threshold"] = max(
                int(aggregate.get("circuit_failure_threshold", 0) or 0),
                int(snapshot.get("circuit_failure_threshold", 0) or 0),
            )
            aggregate["circuit_cooldown_seconds"] = max(
                float(aggregate.get("circuit_cooldown_seconds", 0.0) or 0.0),
                float(snapshot.get("circuit_cooldown_seconds", 0.0) or 0.0),
            )

            existing_remaining = float(aggregate.get("circuit_cooldown_remaining_s", 0.0) or 0.0)
            incoming_remaining = float(snapshot.get("circuit_cooldown_remaining_s", 0.0) or 0.0)
            if incoming_remaining > existing_remaining:
                aggregate["circuit_cooldown_remaining_s"] = incoming_remaining

            existing_open_until = str(aggregate.get("circuit_open_until") or "")
            incoming_open_until = str(snapshot.get("circuit_open_until") or "")
            if incoming_open_until and incoming_open_until > existing_open_until:
                aggregate["circuit_open_until"] = incoming_open_until

            if snapshot.get("last_success_at"):
                existing = str(aggregate.get("last_success_at") or "")
                incoming = str(snapshot.get("last_success_at") or "")
                if incoming and incoming > existing:
                    aggregate["last_success_at"] = incoming
            if snapshot.get("last_error"):
                aggregate["last_error"] = snapshot["last_error"]

        return rows

    async def start_all(self) -> None:
        """Inicia todos os canais configurados e habilitados."""
        await self._bus.start()
        cfg = load_config()
        channels_cfg = cfg.get("channels", {})
        if not isinstance(channels_cfg, dict):
            return
        for ch_name in channels_cfg.keys():
            await self.start_channel(str(ch_name), cfg=cfg)

    async def stop_all(self) -> None:
        """Para todos os canais ativos."""
        for instance_key in list(self.active_channels.keys()):
            await self._stop_instance(instance_key)
        await self._bus.stop()

    async def broadcast_proactive(self, message: str, prefix: str = "[heartbeat]") -> dict[str, Any]:
        """Envia mensagem proativa para todas as instâncias/canais ativos."""
        text = str(message or "").strip()
        if not text:
            return {"delivered": 0, "failed": 0, "skipped": len(self.active_channels), "targets": []}

        cfg = load_config()
        channels_cfg = cfg.get("channels", {}) if isinstance(cfg.get("channels"), dict) else {}
        payload = f"{prefix} {text}".strip() if prefix else text
        delivered = 0
        failed = 0
        skipped = 0
        targets: list[dict[str, str]] = []

        for instance_key, channel in list(self.active_channels.items()):
            meta = self.active_metadata.get(instance_key, {})
            ch_name = str(meta.get("channel", "")).strip().lower() or instance_key.split(":", 1)[0]
            session_id = self.sessions.last_session_id(instance_key)
            if not session_id:
                ch_data = channels_cfg.get(ch_name, {}) if isinstance(channels_cfg.get(ch_name), dict) else {}
                session_id = self._fallback_session_id(ch_name, ch_data)

            if not session_id:
                skipped += 1
                continue

            try:
                await channel.send_message(session_id, payload)
                delivered += 1
                targets.append({"instance": instance_key, "session_id": session_id})
            except Exception as exc:
                failed += 1
                logger.warning("Falha no envio proativo para %s (%s): %s", instance_key, session_id, exc)

        return {
            "delivered": delivered,
            "failed": failed,
            "skipped": skipped,
            "targets": targets,
        }

# Global manager instance
manager = ChannelManager()
