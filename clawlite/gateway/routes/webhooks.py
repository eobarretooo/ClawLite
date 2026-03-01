import asyncio
import logging
from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from clawlite.channels.googlechat import GoogleChatChannel
from clawlite.channels.imessage import IMessageChannel
from clawlite.channels.irc import IrcChannel
from clawlite.channels.manager import manager
from clawlite.channels.signal import SignalChannel
from clawlite.channels.whatsapp import WhatsAppChannel

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)
TChannel = TypeVar("TChannel")


def _resolve_channel_instances(channel_name: str, expected_type: type[TChannel]) -> list[TChannel]:
    prefix = f"{channel_name}:"
    rows: list[TChannel] = []
    for key, channel in manager.active_channels.items():
        if key == channel_name or key.startswith(prefix):
            if isinstance(channel, expected_type):
                rows.append(channel)
    return rows


def _extract_phone_number_id(payload: dict[str, Any]) -> str:
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                value_id = str(metadata.get("phone_number_id", "")).strip()
                if value_id:
                    return value_id
    except Exception:
        return ""
    return ""


def _resolve_whatsapp_channel(payload: dict[str, Any]) -> WhatsAppChannel | None:
    active = _resolve_channel_instances("whatsapp", WhatsAppChannel)
    if not active:
        return None

    expected_phone_number_id = _extract_phone_number_id(payload)
    if expected_phone_number_id:
        for channel in active:
            configured = str(getattr(channel, "phone_number_id", "")).strip()
            if configured and configured == expected_phone_number_id:
                return channel

    preferred = manager.active_channels.get("whatsapp")
    if isinstance(preferred, WhatsAppChannel):
        return preferred
    return active[0]


def _resolve_googlechat_channel() -> GoogleChatChannel | None:
    active = _resolve_channel_instances("googlechat", GoogleChatChannel)
    if not active:
        return None
    preferred = manager.active_channels.get("googlechat")
    if isinstance(preferred, GoogleChatChannel):
        return preferred
    return active[0]


def _resolve_irc_channel() -> IrcChannel | None:
    active = _resolve_channel_instances("irc", IrcChannel)
    if not active:
        return None
    preferred = manager.active_channels.get("irc")
    if isinstance(preferred, IrcChannel):
        return preferred
    return active[0]


def _resolve_signal_channel() -> SignalChannel | None:
    active = _resolve_channel_instances("signal", SignalChannel)
    if not active:
        return None
    preferred = manager.active_channels.get("signal")
    if isinstance(preferred, SignalChannel):
        return preferred
    return active[0]


def _resolve_imessage_channel() -> IMessageChannel | None:
    active = _resolve_channel_instances("imessage", IMessageChannel)
    if not active:
        return None
    preferred = manager.active_channels.get("imessage")
    if isinstance(preferred, IMessageChannel):
        return preferred
    return active[0]


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """Valida o webhook originado do Meta."""
    if hub_mode == "subscribe" and hub_challenge:
        return int(hub_challenge)
    raise HTTPException(status_code=400, detail="Invalid verify token")


@router.post("/whatsapp")
async def handle_whatsapp_webhook(request: Request) -> dict[str, str]:
    payload = await request.json()

    wa_channel = _resolve_whatsapp_channel(payload)
    if not wa_channel:
        logger.warning("Webhook WhatsApp recebido mas o canal offline/não configurado.")
        return {"status": "ignored"}

    asyncio.create_task(wa_channel.process_webhook_payload(payload))
    return {"status": "ok"}


@router.post("/googlechat")
async def handle_googlechat_webhook(request: Request) -> JSONResponse:
    payload = await request.json()
    gc_channel = _resolve_googlechat_channel()
    if not gc_channel:
        logger.warning("Webhook Google Chat recebido mas o canal offline/não configurado.")
        return JSONResponse({"text": ""})

    response = await gc_channel.process_webhook_payload(payload)
    if not isinstance(response, dict):
        return JSONResponse({"text": ""})
    return JSONResponse(response or {"text": ""})


@router.post("/irc")
async def handle_irc_webhook(request: Request) -> dict[str, str]:
    payload = await request.json()
    irc_channel = _resolve_irc_channel()
    if not irc_channel:
        logger.warning("Webhook IRC recebido mas o canal offline/não configurado.")
        return {"status": "ignored"}
    asyncio.create_task(irc_channel.process_webhook_payload(payload))
    return {"status": "ok"}


@router.post("/signal")
async def handle_signal_webhook(request: Request) -> dict[str, str]:
    payload = await request.json()
    sig_channel = _resolve_signal_channel()
    if not sig_channel:
        logger.warning("Webhook Signal recebido mas o canal offline/não configurado.")
        return {"status": "ignored"}
    asyncio.create_task(sig_channel.process_webhook_payload(payload))
    return {"status": "ok"}


@router.post("/imessage")
async def handle_imessage_webhook(request: Request) -> dict[str, str]:
    payload = await request.json()
    imsg_channel = _resolve_imessage_channel()
    if not imsg_channel:
        logger.warning("Webhook iMessage recebido mas o canal offline/não configurado.")
        return {"status": "ignored"}
    asyncio.create_task(imsg_channel.process_webhook_payload(payload))
    return {"status": "ok"}
