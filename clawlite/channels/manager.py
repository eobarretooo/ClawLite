from __future__ import annotations

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

    async def _handle_message(self, session_id: str, text: str) -> str:
        """
        Callback central para processar mensagens recebidas de qualquer canal.
        Roteia diretamente para o core LLM.
        """
        import asyncio
        # O run_task_with_meta é síncrono, então rodamos em uma thread
        prompt = text.strip()
        try:
            output, meta = await asyncio.to_thread(run_task_with_meta, prompt)
            return output
        except Exception as exc:
            logger.error(f"Erro no processamento da mensagem do canal: {exc}")
            return "Ocorreu um erro interno ao processar a requisição."

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
            return {
                "allowed_accounts": allow_from,
                "pairing_enabled": pairing_enabled,
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
                "pairing_enabled": pairing_enabled,
            }
        if channel_name == "signal":
            send_timeout_s = self._as_positive_float(
                ch_data.get("send_timeout_s", ch_data.get("sendTimeoutSec", 15.0)),
                15.0,
            )
            return {
                "account": str(ch_data.get("account", "")).strip(),
                "cli_path": str(ch_data.get("cli_path") or ch_data.get("cliPath") or "signal-cli").strip(),
                "http_url": str(ch_data.get("http_url") or ch_data.get("httpUrl") or "").strip(),
                "allowed_numbers": allow_from,
                "send_timeout_s": send_timeout_s,
                "pairing_enabled": pairing_enabled,
            }
        if channel_name == "imessage":
            send_timeout_s = self._as_positive_float(
                ch_data.get("send_timeout_s", ch_data.get("sendTimeoutSec", 15.0)),
                15.0,
            )
            return {
                "cli_path": str(ch_data.get("cli_path") or ch_data.get("cliPath") or "imsg").strip(),
                "service": str(ch_data.get("service", "auto")).strip().lower(),
                "allowed_handles": allow_from,
                "send_timeout_s": send_timeout_s,
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
                channel = channel_cls(token=cred["token"], name=normalized_channel, **channel_kwargs)
                channel.on_message(self._handle_message)
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
            rows.append(
                {
                    "instance_key": instance_key,
                    "channel": ch_name,
                    "account": str(meta.get("account", "")).strip(),
                    "running": bool(getattr(channel, "running", False)),
                }
            )
        rows.sort(key=lambda row: row["instance_key"])
        return rows

    async def start_all(self) -> None:
        """Inicia todos os canais configurados e habilitados."""
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

# Global manager instance
manager = ChannelManager()
